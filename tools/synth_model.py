#!/usr/bin/env python3
"""Synthetic benchmark model (boxes only) in the xray-model/1 glb + json format.

Usage: python3 tools/synth_model.py -n 5000 -o web/public/models/synth5k [--seed 1]

Layout (IFC frame, Z up, metres): a k x k grid of 6 m bays and `s` storeys of 3.5 m.
  - slabs   250 mm thick, one per bay per level (levels 0..s, top level is the roof)
  - beams   0.3 x 0.5 m under the slabs along every grid line
  - columns 0.4 x 0.4 m on every grid intersection, per storey
  - walls   0.2 m perimeter walls, per bay edge, per storey
  - MEP     in each bay up to two vertical risers (duct 600x300 and pipe 100x100) passing through the
            slab of every level, each with a horizontal branch under the beams; consecutive segments of a
            run are linked by `ports`.
Every duct/pipe whose box overlaps a slab box (positive volume) gets a synthetic opening: voids
[slab, opening], fills [opening, mep], hosts [mep, slab]. Slabs themselves stay solid boxes.
Exactly N elements are produced (structure first, MEP fills the remainder).

--debris D (a cleanup demo; use a small -n such as 400): the model is the same kind of building with D small floating items
scattered in its rooms (bolts: IfcFastener, 3 to 4 cm; offcuts: IfcMember, 12 to 45 cm; none touches anything) plus seven fixed
probes, all named "Debris ...": a stray cluster of three touching 12 cm boxes ("Debris cluster A/B/C"), one far stray 300 m away
("Debris far stray"), two exact copies of existing beams ("Debris duplicate beam 1/2") and one wall of zero thickness
("Debris zero-thickness wall"). The total is still N elements (the building is built with N - D - 7). Used for
web/public/models/debris-demo and the "Debris" selection set.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import glb_common  # noqa: E402

BAY = 6.0
STOREY_H = 3.5
SLAB_T = 0.25
BEAM_W, BEAM_D = 0.3, 0.5
COL = 0.4
WALL_T = 0.2
OPENING_BASE = 1_000_000  # synthetic express ids for openings

CONCRETE = [0.62, 0.62, 0.62, 1.0]
COLORS = {"IfcSlab": [0.66, 0.66, 0.66, 1.0], "IfcBeam": [0.58, 0.58, 0.60, 1.0], "IfcColumn": CONCRETE,
          "IfcWall": [0.72, 0.70, 0.66, 1.0], "IfcDuctSegment": [0.3, 0.6, 0.9, 1.0],
          "IfcPipeSegment": [0.2, 0.7, 0.4, 1.0]}
B64 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_$"


def guid(i: int, seed: int) -> str:
    n = int.from_bytes(hashlib.md5(f"{seed}:{i}".encode()).digest(), "big") & ((1 << 128) - 1)
    out = []
    for _ in range(22):
        out.append(B64[n & 63])
        n >>= 6
    return "".join(reversed(out))[:22]


def struct_count(s: int, k: int) -> int:
    return (s + 1) * k * k + (s + 1) * 2 * k * (k + 1) + s * (k + 1) ** 2 + s * 4 * k


def mep_capacity(s: int, k: int) -> int:
    return 2 * k * k * 2 * (s + 1)


def choose_dims(n: int) -> tuple[int, int]:
    """(storeys, bays per side): structure about 65 % of n, MEP capacity enough for the rest."""
    best, best_cost = (1, 1), float("inf")
    for s in range(1, 13):
        for k in range(1, 41):
            st = struct_count(s, k)
            if st > n:
                break
            if st + mep_capacity(s, k) < n:
                continue
            cost = abs(st / n - 0.65) + 0.02 * abs(s - round((n / 30.0) ** (1 / 3)))
            if cost < best_cost:
                best, best_cost = (s, k), cost
    return best


def generate(n: int, seed: int, debris: int = 0):
    rng = np.random.default_rng(seed)
    n_base = n - (debris + DEBRIS_FIXED) if debris > 0 else n
    if n_base < 20:
        raise SystemExit("--debris: -n must leave room for the building (n - debris - 7 >= 20)")
    n = n_base  # `add` stops at n; debris is appended after the building
    s, k = choose_dims(n)
    E = [i * STOREY_H for i in range(s + 1)]  # level elevations (top of slab)
    items: list[dict] = []
    boxes: list[tuple] = []  # (min, max) IFC frame

    def add(cls, name, mn, mx, storey, material, extra=None):
        if len(items) >= n:
            return None
        i = len(items)
        boxes.append((np.array(mn, float), np.array(mx, float)))
        items.append({"ifcClass": cls, "name": name, "storey": storey, "material": material,
                      "color": COLORS[cls], "expressId": 100 + i, "_role": extra})
        return i

    L = k * BAY
    # storey index = level index (storey i spans level i floor to level i+1 underside); roof level s is storey s
    for lv in range(s + 1):
        e = E[lv]
        for i in range(k):
            for j in range(k):
                add("IfcSlab", f"Slab L{lv} {i},{j}", (i * BAY, j * BAY, e - SLAB_T), ((i + 1) * BAY, (j + 1) * BAY, e),
                    lv, "Concrete", ("slab", lv, i, j))
        bz0, bz1 = e - SLAB_T - BEAM_D, e - SLAB_T
        for j in range(k + 1):
            for i in range(k):
                add("IfcBeam", f"Beam L{lv} X{i},{j}", (i * BAY + COL / 2, j * BAY - BEAM_W / 2, bz0),
                    ((i + 1) * BAY - COL / 2, j * BAY + BEAM_W / 2, bz1), lv, "Concrete")
        for i in range(k + 1):
            for j in range(k):
                add("IfcBeam", f"Beam L{lv} Y{i},{j}", (i * BAY - BEAM_W / 2, j * BAY + COL / 2, bz0),
                    (i * BAY + BEAM_W / 2, (j + 1) * BAY - COL / 2, bz1), lv, "Concrete")
        if lv < s:
            z0, z1 = e, E[lv + 1] - SLAB_T - BEAM_D
            for i in range(k + 1):
                for j in range(k + 1):
                    add("IfcColumn", f"Column S{lv} {i},{j}", (i * BAY - COL / 2, j * BAY - COL / 2, z0),
                        (i * BAY + COL / 2, j * BAY + COL / 2, z1), lv, "Concrete")
            wz1 = E[lv + 1] - SLAB_T
            for a in range(k):
                for (y, tag) in ((0.0, "S"), (L, "N")):
                    add("IfcWall", f"Wall S{lv} {tag}{a}", (a * BAY + COL / 2, y - WALL_T / 2, z0),
                        ((a + 1) * BAY - COL / 2, y + WALL_T / 2, wz1), lv, "Brick")
                for (x, tag) in ((0.0, "W"), (L, "E")):
                    add("IfcWall", f"Wall S{lv} {tag}{a}", (x - WALL_T / 2, a * BAY + COL / 2, z0),
                        (x + WALL_T / 2, (a + 1) * BAY - COL / 2, wz1), lv, "Brick")
    n_struct = len(items)

    # MEP runs: slot 0 = duct (600x300), slot 1 = pipe (100x100); one run per (bay, slot), shuffled
    slots = [(i, j, t) for i in range(k) for j in range(k) for t in (0, 1)]
    order = rng.permutation(len(slots))
    ports: list[list[int]] = []
    run_of: list[list[int]] = []
    for si in order:
        if len(items) >= n:
            break
        i, j, t = slots[si]
        cx, cy = i * BAY + BAY / 2, j * BAY + BAY / 2
        if t == 0:
            rx, ry, cls, w, h, ln = cx - 1.0, cy, "IfcDuctSegment", 0.6, 0.3, 2.5
        else:
            rx, ry, cls, w, h, ln = cx + 1.2, cy + 1.0, "IfcPipeSegment", 0.1, 0.1, 1.5
        run: list[int] = []
        for lv in range(s + 1):
            e = E[lv]
            # riser crossing the slab of this level
            r = add(cls, f"{'Duct' if t == 0 else 'Pipe'} riser L{lv} {i},{j}",
                    (rx - w / 2, ry - (h if t == 0 else w) / 2, e - 1.75),
                    (rx + w / 2, ry + (h if t == 0 else w) / 2, e + 1.75), min(lv, s), "Galvanised" if t == 0 else "PVC",
                    ("riser", lv))
            if r is not None:
                run.append(r)
            zc = e - SLAB_T - BEAM_D - 0.15 - h / 2  # hangs under the beams
            b = add(cls, f"{'Duct' if t == 0 else 'Pipe'} branch L{lv} {i},{j}",
                    (rx, ry - (h if t == 0 else w) / 2, zc - h / 2), (rx + ln, ry + (h if t == 0 else w) / 2, zc + h / 2),
                    min(lv, s), "Galvanised" if t == 0 else "PVC", ("branch", lv))
            if b is not None:
                run.append(b)
        for a, b in zip(run, run[1:]):
            ports.append([a, b])
    if len(items) < n_base:
        print(f"warning: only {len(items)} of {n_base} elements could be generated", file=sys.stderr)
    if debris > 0:
        add_debris(items, boxes, debris, seed, s, k, E)
    return items, boxes, ports, s, k, n_struct, E


DEBRIS_FIXED = 7  # cluster 3 + far stray 1 + duplicates 2 + zero-thickness 1
DEBRIS_COLOR = [0.85, 0.35, 0.2, 1.0]


def add_debris(items: list, boxes: list, d: int, seed: int, s: int, k: int, E: list) -> list[int]:
    """Append d scattered floating items and the fixed probes. Returns the ids added (all named 'Debris ...')."""
    rng = np.random.default_rng(seed + 1000)
    L = k * BAY
    zmax = E[s] - 1.0
    first = len(items)

    def put(cls, name, mn, mx, material, tag):
        z = 0.5 * (mn[2] + mx[2])
        storey = int(max(0, min(s, z // STOREY_H)))
        items.append({"ifcClass": cls, "name": name, "storey": storey, "material": material, "color": DEBRIS_COLOR,
                      "expressId": 100 + len(items), "_role": ("debris", tag)})
        boxes.append((np.array(mn, float), np.array(mx, float)))

    def clear(mn, mx, margin=0.08) -> bool:
        lo, hi = np.asarray(mn) - margin, np.asarray(mx) + margin
        for bmn, bmx in boxes:
            if np.all(np.minimum(hi, bmx) - np.maximum(lo, bmn) > 0):
                return False
        return True

    def free_spot(size):
        for _ in range(2000):
            c = np.array([rng.uniform(0.6, L - 0.6), rng.uniform(0.6, L - 0.6), rng.uniform(0.4, zmax)])
            mn, mx = c - np.asarray(size) / 2, c + np.asarray(size) / 2
            if clear(mn, mx):
                return mn, mx
        raise RuntimeError("no free spot for debris; use a larger model")

    n_bolts = (d * 3 + 2) // 5
    for i in range(d):
        if i < n_bolts:
            e = float(rng.uniform(0.03, 0.04))
            mn, mx = free_spot((e, e, e * float(rng.uniform(1.0, 1.6))))
            put("IfcFastener", f"Debris bolt {i + 1:02d}", mn, mx, "Steel", "bolt")
        else:
            sz = rng.uniform(0.05, 0.12, 3)
            sz[int(rng.integers(0, 3))] = rng.uniform(0.2, 0.45)
            mn, mx = free_spot(sz)
            put("IfcMember", f"Debris offcut {i - n_bolts + 1:02d}", mn, mx, "Timber", "offcut")
    # stray cluster: three boxes of 12 cm touching each other (a 0.36 m run), away from everything else. The default
    # cleanup mode ('single elements') keeps them (each has a contact); mode 'small clusters' matches all three.
    mn0, mx0 = free_spot((0.36, 0.12, 0.12))
    for j, tag in enumerate("ABC"):
        a = mn0 + np.array([0.12 * j, 0.0, 0.0])
        put("IfcBuildingElementProxy", f"Debris cluster {tag}", a, a + 0.12, "Timber", "cluster")
    # far stray, 300 m from the building
    put("IfcBuildingElementProxy", "Debris far stray", (L + 300.0, 0.0, 0.0), (L + 300.3, 0.3, 0.3), "Steel", "far")
    # two exact copies of existing beams (lowest id stays, the copies z-fight)
    beams = [i for i, it in enumerate(items[:first]) if it["ifcClass"] == "IfcBeam"]
    for j in range(2):
        src = beams[(j * 7 + 3) % len(beams)]
        put("IfcBeam", f"Debris duplicate beam {j + 1}", boxes[src][0], boxes[src][1], items[src]["material"], "duplicate")
        items[-1]["storey"] = items[src]["storey"]
    # one wall of zero thickness standing on the first slab, touching the structure
    z0 = E[0]
    put("IfcWall", "Debris zero-thickness wall", (BAY * 0.5, BAY * 0.5, z0), (BAY * 0.5 + 1.2, BAY * 0.5, z0 + 2.0), "Brick", "degenerate")
    items[-1]["storey"] = 0
    return list(range(first, len(items)))


def synth_props(it: dict, mn, mx, s: int) -> dict | None:
    """Plausible hover-info properties for a synthetic box element (same key format as ifc2glb.py --props common)."""
    cls = it["ifcClass"]
    dx, dy, dz = (float(x) for x in (mx - mn))
    r = lambda x: glb_common.normalize_number("IfcReal", x, {})  # noqa: E731 - 4 significant digits
    e: list = []
    A, C, Q = glb_common.GROUP_ATTR, glb_common.GROUP_COMMON, glb_common.GROUP_QTY
    role = it.get("_role")
    top = bool(role) and role[0] == "slab" and role[1] == s
    if cls == "IfcWall":
        e += [("Attr.ObjectType", f"Wall:{it['material']} 200", A), ("Attr.PredefinedType", "STANDARD", A),
              ("Pset_WallCommon.IsExternal", True, C), ("Pset_WallCommon.LoadBearing", False, C),
              ("Pset_WallCommon.FireRating", "EI60", C), ("Pset_WallCommon.Reference", "W-200-" + it["material"][:2].upper(), C)]
        ln = max(dx, dy)
        e += [("Qto_WallBaseQuantities.Length", r(ln), Q), ("Qto_WallBaseQuantities.Width", r(min(dx, dy)), Q),
              ("Qto_WallBaseQuantities.Height", r(dz), Q), ("Qto_WallBaseQuantities.NetVolume", r(dx * dy * dz), Q)]
    elif cls == "IfcSlab":
        e += [("Attr.ObjectType", "Floor:Concrete 250", A), ("Attr.PredefinedType", "ROOF" if top else "FLOOR", A),
              ("Pset_SlabCommon.IsExternal", top, C), ("Pset_SlabCommon.LoadBearing", True, C),
              ("Pset_SlabCommon.FireRating", "REI90", C), ("Pset_SlabCommon.Reference", "S-250", C)]
        e += [("Qto_SlabBaseQuantities.Length", r(max(dx, dy)), Q), ("Qto_SlabBaseQuantities.Width", r(min(dx, dy)), Q),
              ("Qto_SlabBaseQuantities.Depth", r(dz), Q), ("Qto_SlabBaseQuantities.NetArea", r(dx * dy), Q),
              ("Qto_SlabBaseQuantities.NetVolume", r(dx * dy * dz), Q)]
    elif cls == "IfcBeam":
        e += [("Attr.ObjectType", "Beam:Concrete 300x500", A), ("Attr.PredefinedType", "BEAM", A),
              ("Pset_BeamCommon.IsExternal", False, C), ("Pset_BeamCommon.LoadBearing", True, C),
              ("Pset_BeamCommon.FireRating", "R90", C), ("Pset_BeamCommon.Reference", "B-300x500", C)]
        e += [("Qto_BeamBaseQuantities.Length", r(max(dx, dy)), Q), ("Qto_BeamBaseQuantities.CrossSectionArea", r(min(dx, dy) * dz), Q),
              ("Qto_BeamBaseQuantities.NetVolume", r(dx * dy * dz), Q)]
    elif cls == "IfcColumn":
        e += [("Attr.ObjectType", "Column:Concrete 400x400", A), ("Attr.PredefinedType", "COLUMN", A),
              ("Pset_ColumnCommon.IsExternal", False, C), ("Pset_ColumnCommon.LoadBearing", True, C),
              ("Pset_ColumnCommon.FireRating", "R90", C), ("Pset_ColumnCommon.Reference", "C-400", C)]
        e += [("Qto_ColumnBaseQuantities.Length", r(dz), Q), ("Qto_ColumnBaseQuantities.CrossSectionArea", r(dx * dy), Q),
              ("Qto_ColumnBaseQuantities.NetVolume", r(dx * dy * dz), Q)]
    elif cls in ("IfcDuctSegment", "IfcPipeSegment"):
        duct = cls == "IfcDuctSegment"
        nm = "Duct" if duct else "Pipe"
        e += [("Attr.ObjectType", f"{nm} 600x300" if duct else "Pipe PVC 100", A), ("Attr.PredefinedType", "RIGIDSEGMENT", A),
              (f"Pset_{nm}SegmentTypeCommon.Reference", "D-600x300" if duct else "P-100", C),
              (f"Pset_{nm}SegmentTypeCommon.IsExternal", False, C)]
        ln = max(dx, dy, dz)
        e += [(f"Qto_{nm}SegmentBaseQuantities.Length", r(ln), Q)]
        if duct:
            e += [("Qto_DuctSegmentBaseQuantities.CrossSectionArea", r(0.6 * 0.3), Q)]
    return glb_common.finalize_props(e)


def debris_props(it: dict):
    return glb_common.finalize_props([("Attr.ObjectType", it["name"], glb_common.GROUP_ATTR)])


def build(n: int, seed: int, out_base: str, config: str | None = None, debris: int = 0) -> dict:
    items, boxes, ports, s, k, n_struct, E = generate(n, seed, debris)
    # hosts: MEP boxes that overlap a slab box with positive volume
    slab_ids = [i for i, it in enumerate(items) if it["ifcClass"] == "IfcSlab"]
    sl_min = np.array([boxes[i][0] for i in slab_ids]).reshape(-1, 3)
    sl_max = np.array([boxes[i][1] for i in slab_ids]).reshape(-1, 3)
    voids, fills, hosts = [], [], []
    openings = []   # {expressId, host, bounds (IFC frame; write_model converts)}: overlap box grown by 10 mm
    opening = OPENING_BASE
    for i, it in enumerate(items):
        if it["ifcClass"] not in ("IfcDuctSegment", "IfcPipeSegment"):
            continue
        mn, mx = boxes[i]
        ov = (np.minimum(sl_max, mx) - np.maximum(sl_min, mn)).min(1) > 1e-9
        for si in np.nonzero(ov)[0]:
            host = slab_ids[int(si)]
            opening += 1
            voids.append([host, opening])
            fills.append([opening, i])
            hosts.append([i, host])
            lo_b = np.maximum(sl_min[si], mn) - 0.01
            hi_b = np.minimum(sl_max[si], mx) + 0.01
            openings.append({"expressId": opening, "host": host,
                             "bounds": [float(x) for x in np.concatenate([lo_b, hi_b])]})

    # build meshes + storeys
    out_items = []
    for i, (it, (mn, mx)) in enumerate(zip(items, boxes)):
        v, f, nrm = glb_common.box_mesh(mn, mx)
        out_items.append({**it, "globalId": guid(i, seed), "verts": v, "faces": f, "normals": nrm,
                          "file": os.path.basename(out_base) + ".synth", "props": synth_props(it, mn, mx, s) if it["_role"] is None or it["_role"][0] != "debris" else debris_props(it)})
    storeys = [{"id": i, "name": f"Level {i}" if i < s else "Roof", "elevation": E[i]} for i in range(s + 1)]
    systems = [
        {"name": "Supply Air", "elements": [i for i, it in enumerate(items) if it["ifcClass"] == "IfcDuctSegment"]},
        {"name": "Domestic Water", "elements": [i for i, it in enumerate(items) if it["ifcClass"] == "IfcPipeSegment"]},
    ]
    systems = [x for x in systems if x["elements"]]
    relations = {"voids": voids, "fills": fills, "hosts": hosts, "ports": ports, "systems": systems}
    if openings:
        relations["openings"] = openings
    source = {"files": [f"synthetic(n={n},seed={seed}" + (f",debris={debris})" if debris else ")")], "converter": "synth_model.py", "ifcSchema": "none"}
    os.makedirs(os.path.dirname(os.path.abspath(out_base)), exist_ok=True)
    extra = glb_common.load_style_config(config) if config else None
    side = glb_common.write_model(out_base, out_items, storeys, relations, source, extra)
    side["_dims"] = (s, k, n_struct)
    return side


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="synthetic xray-model/1 benchmark generator")
    ap.add_argument("-n", type=int, default=5000, help="number of elements (default 5000)")
    ap.add_argument("-o", "--out", required=True, help="output base path (writes .glb and .json)")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--debris", type=int, default=0, metavar="D",
                    help="cleanup demo: add D small floating items plus 7 probes (cluster, far stray, duplicates, zero-thickness); "
                         "-n stays the total element count")
    ap.add_argument("--config", metavar="XRAY_CONFIG_JSON",
                    help="xray-config/1 file; classStyles and materialAliases are baked into model.json")
    a = ap.parse_args(argv)
    side = build(a.n, a.seed, a.out, a.config, a.debris)
    els = side["elements"]
    s, k, ns = side["_dims"]
    print(f"wrote {a.out}.glb ({os.path.getsize(a.out + '.glb')} bytes), {a.out}.json ({os.path.getsize(a.out + '.json')} bytes)")
    print(f"{len(els)} elements: {s} storeys (+roof level), {k}x{k} bays of {BAY} m, {ns} structural, {len(els) - ns} MEP")
    for c, n in sorted(collections.Counter(e["ifcClass"] for e in els).items()):
        print(f"  {c:20s} {n}")
    r = side["relations"]
    print("relations:", {kk: len(v) for kk, v in r.items()})
    b = np.array([e["bounds"] for e in els])
    print("bounds (glb frame): min", np.round(b[:, :3].min(0), 2).tolist(), "max", np.round(b[:, 3:].max(0), 2).tolist(),
          "originShift", side["originShift"])


if __name__ == "__main__":
    main()
