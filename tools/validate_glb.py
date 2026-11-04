#!/usr/bin/env python3
"""Independent validator for <base>.glb + <base>.json (xray-model/1).

Uses only json, struct and numpy: it re-parses the binary container and checks
accessors, min/max, per-node triangle counts and consistency with the sidecar.

Usage: python3 tools/validate_glb.py web/public/models/building [more bases...]
"""
import json
import struct
import sys

import numpy as np


def validate(base: str) -> list[str]:
    errs: list[str] = []
    raw = open(base + ".glb", "rb").read()
    magic, ver, total = struct.unpack_from("<III", raw, 0)
    if magic != 0x46546C67 or ver != 2:
        errs.append("bad glb header")
    if total != len(raw):
        errs.append(f"header length {total} != file {len(raw)}")
    off = 12
    jlen, jtype = struct.unpack_from("<II", raw, off)
    if jtype != 0x4E4F534A or jlen % 4:
        errs.append("bad JSON chunk")
    doc = json.loads(raw[off + 8: off + 8 + jlen])
    off += 8 + jlen
    blen, btype = struct.unpack_from("<II", raw, off)
    if btype != 0x004E4942 or blen % 4:
        errs.append("bad BIN chunk")
    bin_ = raw[off + 8: off + 8 + blen]
    if off + 8 + blen != len(raw):
        errs.append("trailing bytes after BIN chunk")
    if len(doc["buffers"]) != 1 or doc["buffers"][0]["byteLength"] > blen:
        errs.append("buffer byteLength mismatch")
    side = json.load(open(base + ".json"))
    els = side["elements"]
    nodes = doc["nodes"]
    if len(nodes) != len(els):
        errs.append(f"{len(nodes)} nodes vs {len(els)} elements")
    if doc["scenes"][doc["scene"]]["nodes"] != list(range(len(nodes))):
        errs.append("scene does not list all nodes in order")
    names = [n["name"] for n in nodes]
    if len(set(names)) != len(names):
        errs.append("duplicate node names")

    def read(ai: int, dtype, ncomp: int):
        a = doc["accessors"][ai]
        bv = doc["bufferViews"][a["bufferView"]]
        start = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
        n = a["count"] * ncomp
        sz = np.dtype(dtype).itemsize * n
        if start + sz > bv.get("byteOffset", 0) + bv["byteLength"]:
            errs.append(f"accessor {ai} overruns its bufferView")
        if start % 4:
            errs.append(f"accessor {ai} misaligned")
        arr = np.frombuffer(bin_, dtype=dtype, count=n, offset=start)
        return arr.reshape(-1, ncomp) if ncomp > 1 else arr

    tot_tris = 0
    all_lo, all_hi = np.full(3, np.inf), np.full(3, -np.inf)
    for i, (n, e) in enumerate(zip(nodes, els)):
        ex = n.get("extras", {})
        if ex.get("id") != i or e["id"] != i or ex.get("ifcClass") != e["ifcClass"] or n["name"] != e["globalId"]:
            errs.append(f"node {i}: extras/name do not match sidecar")
        m = doc["meshes"][n["mesh"]]
        if len(m["primitives"]) != 1:
            errs.append(f"node {i}: expected 1 primitive")
        p = m["primitives"][0]
        if p.get("mode", 4) != 4:
            errs.append(f"node {i}: not triangles")
        ap, an, ai = p["attributes"]["POSITION"], p["attributes"]["NORMAL"], p["indices"]
        A = doc["accessors"]
        if A[ap]["componentType"] != 5126 or A[an]["componentType"] != 5126 or A[ai]["componentType"] != 5125:
            errs.append(f"node {i}: component types")
        pos = read(ap, "<f4", 3)
        nor = read(an, "<f4", 3)
        idx = read(ai, "<u4", 1)
        if len(pos) != A[ap]["count"] or len(nor) != len(pos):
            errs.append(f"node {i}: count mismatch")
        if not (np.isfinite(pos).all() and np.isfinite(nor).all()):
            errs.append(f"node {i}: non-finite data")
        if not (np.allclose(pos.min(0), A[ap]["min"], atol=1e-6) and np.allclose(pos.max(0), A[ap]["max"], atol=1e-6)):
            errs.append(f"node {i}: POSITION min/max wrong")
        if len(idx) % 3 or len(idx) == 0:
            errs.append(f"node {i}: index count {len(idx)}")
        elif idx.max() >= len(pos):
            errs.append(f"node {i}: index out of range")
        ntri = len(idx) // 3
        tot_tris += ntri
        if ntri == 0:
            errs.append(f"node {i}: zero triangles")
        else:
            t = idx.reshape(-1, 3).astype(np.int64)
            cr = np.cross(pos[t[:, 1]] - pos[t[:, 0]], pos[t[:, 2]] - pos[t[:, 0]])
            if (np.linalg.norm(cr, axis=1) <= 1e-12).all():
                errs.append(f"node {i}: all triangles degenerate")
        ln = np.linalg.norm(nor, axis=1)
        if not np.allclose(ln, 1.0, atol=1e-3):
            errs.append(f"node {i}: normals not unit length")
        lo, hi = pos.min(0).astype(np.float64), pos.max(0).astype(np.float64)
        all_lo, all_hi = np.minimum(all_lo, lo), np.maximum(all_hi, hi)
        if not np.allclose(e["bounds"], np.concatenate([lo, hi]), atol=1e-3):
            errs.append(f"node {i}: sidecar bounds differ from mesh bounds")
        if not (hi > lo).any():
            errs.append(f"node {i}: degenerate bounds")
        if len(e["color"]) != 4 or not all(0 <= c <= 1 for c in e["color"]):
            errs.append(f"node {i}: bad colour")
    nel = len(els)
    centre = (all_lo + all_hi) / 2
    if len(els) and np.abs(centre).max() > 1e-2:
        errs.append(f"model centre not at origin: {centre}")
    r = side["relations"]
    for k in ("hosts", "ports"):
        for a, b in r[k]:
            if not (0 <= a < nel and 0 <= b < nel):
                errs.append(f"relation {k} {a},{b} out of range")
    for h, _o in r["voids"]:
        if not 0 <= h < nel:
            errs.append("void host out of range")
    for _o, f in r["fills"]:
        if not 0 <= f < nel:
            errs.append("fill element out of range")
    open_host = {o: h for h, o in r["voids"]}
    derived = {(f, open_host[o]) for o, f in r["fills"] if o in open_host}
    if derived != {tuple(x) for x in r["hosts"]}:
        errs.append("hosts not consistent with voids+fills")
    for s in r["systems"]:
        if not all(0 <= x < nel for x in s["elements"]):
            errs.append(f"system {s['name']} out of range")
    sids = {s["id"] for s in side["storeys"]}
    if any(e["storey"] is not None and e["storey"] not in sids for e in els):
        errs.append("element references unknown storey")
    el = [s["elevation"] for s in side["storeys"]]
    if el != sorted(el):
        errs.append("storeys not sorted by elevation")
    print(f"{base}: {len(nodes)} nodes, {len(doc['accessors'])} accessors, {tot_tris} triangles, "
          f"bin {blen} bytes, bounds {np.round(all_lo, 2).tolist()}..{np.round(all_hi, 2).tolist()} -> "
          f"{'OK' if not errs else str(len(errs)) + ' ERRORS'}")
    return errs


if __name__ == "__main__":
    bad = 0
    for b in sys.argv[1:]:
        e = validate(b[:-4] if b.endswith(".glb") else b)
        for x in e[:20]:
            print("  ERROR:", x)
        bad += bool(e)
    sys.exit(1 if bad else 0)
