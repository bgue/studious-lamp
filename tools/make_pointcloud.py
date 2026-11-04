#!/usr/bin/env python3
"""Sample a converted model into a synthetic "as-built scan" for the point cloud feature.

Reads <model>.glb and <model>.json (tools/ifc2glb.py output, default web/public/models/building), samples the surfaces
with area-weighted random points, and writes a LAS 1.2 (point format 2) and a binary little endian PLY in IFC PROJECT
coordinates (Z up, metres, NOT shifted): the viewer maps them with `coordinates: project`.

What makes it an as-built scan rather than a copy of the model:
  * noise: Gaussian, sigma 5 mm per axis (--sigma)
  * the duct (every IfcDuctSegment) is displaced 80 mm horizontally, diagonal to the walls (--duct-shift), so every
    face of it is off by about 57 mm: the as-built check should flag it red at the default 2 cm tolerance
  * incomplete scan: 10 percent of the length of every wall is missing (a 10 percent wide band at 40..50 percent of
    its longer horizontal extent), as if something occluded the scanner (--wall-drop)

Per point: RGB from the element colour with a little shading, intensity from the incidence angle to a virtual scanner
above the model centre, and an ASPRS class code (walls 6 building, slabs and footings 2, ducts 19,
everything else, air terminals included, 1) so the viewer's classification colouring and per class statistics have something to show. Seeded:
the same arguments write the same files.

Usage (from the repository root):
  python3 tools/make_pointcloud.py                       # web/public/samples/building-scan.{las,ply}, 230000 sampled
  python3 tools/make_pointcloud.py --model web/public/models/fzk-haus --points 230000 --name fzk-haus-scan

About 230000 points (after the dropped wall band) keeps each file under 6 MB (LAS format 2 is 26 bytes per point). Needs numpy only.
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------- glb reading

def read_glb(path: Path):
    """Return (json, bin) of a .glb."""
    data = path.read_bytes()
    magic, version, length = struct.unpack_from("<III", data, 0)
    if magic != 0x46546C67:
        raise SystemExit(f"{path} is not a glb")
    off = 12
    js, binary = None, b""
    while off < length:
        clen, ctype = struct.unpack_from("<II", data, off)
        chunk = data[off + 8: off + 8 + clen]
        if ctype == 0x4E4F534A:
            js = json.loads(chunk)
        elif ctype == 0x004E4942:
            binary = chunk
        off += 8 + clen
    return js, binary


def accessor(js, binary, idx):
    a = js["accessors"][idx]
    bv = js["bufferViews"][a["bufferView"]]
    ncomp = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[a["type"]]
    dt = {5126: np.float32, 5125: np.uint32, 5123: np.uint16, 5121: np.uint8}[a["componentType"]]
    start = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
    stride = bv.get("byteStride")
    if stride and stride != ncomp * np.dtype(dt).itemsize:
        raw = np.frombuffer(binary, dtype=np.uint8, count=a["count"] * stride, offset=start).reshape(a["count"], stride)
        return np.ascontiguousarray(raw[:, : ncomp * np.dtype(dt).itemsize]).view(dt).reshape(a["count"], ncomp)
    return np.frombuffer(binary, dtype=dt, count=a["count"] * ncomp, offset=start).reshape(a["count"], ncomp)


def node_matrix(node) -> np.ndarray:
    if "matrix" in node:
        return np.array(node["matrix"], np.float64).reshape(4, 4).T
    m = np.eye(4)
    if "scale" in node:
        m = np.diag([*node["scale"], 1.0]) @ m
    if "rotation" in node:
        x, y, z, w = node["rotation"]
        r = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                      [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                      [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
        m = np.block([[r, np.zeros((3, 1))], [np.zeros((1, 3)), np.eye(4)[3:, 3:]]]) @ m
    if "translation" in node:
        t = np.eye(4)
        t[:3, 3] = node["translation"]
        m = t @ m
    return m


def load_triangles(base: Path):
    """Per element triangles in the VIEWER frame (Y up, shifted): list of (element_id, tris[n,3,3])."""
    js, binary = read_glb(base.with_suffix(".glb"))
    side = json.loads(base.with_suffix(".json").read_text())
    out = []
    for node in js["nodes"]:
        if "mesh" not in node:
            continue
        eid = (node.get("extras") or {}).get("id")
        if eid is None:
            eid = (js["meshes"][node["mesh"]].get("extras") or {}).get("id")
        if eid is None:
            continue
        m = node_matrix(node)
        for prim in js["meshes"][node["mesh"]]["primitives"]:
            pos = accessor(js, binary, prim["attributes"]["POSITION"]).astype(np.float64)
            pos = pos @ m[:3, :3].T + m[:3, 3]
            idx = accessor(js, binary, prim["indices"]).reshape(-1) if "indices" in prim else np.arange(len(pos))
            out.append((int(eid), pos[idx.reshape(-1, 3)]))
    return out, side


def viewer_to_ifc(v: np.ndarray, shift) -> np.ndarray:
    """Inverse of glb_common.write_model: v = (x - sx, z - sz, -(y - sy))."""
    sx, sy, sz = shift
    return np.stack([v[:, 0] + sx, -v[:, 2] + sy, v[:, 1] + sz], axis=1)


# ---------------------------------------------------------------- sampling

CLASS_OF = {"IfcWall": 6, "IfcWallStandardCase": 6, "IfcSlab": 2, "IfcFooting": 2, "IfcDuctSegment": 19}


def sample(base: Path, n_points: int, sigma: float, duct_shift: float, wall_drop: float, seed: int):
    rng = np.random.default_rng(seed)
    parts, side = load_triangles(base)
    shift = side["originShift"]
    elements = side["elements"]
    tris = np.concatenate([t for _, t in parts])
    owner = np.concatenate([np.full(len(t), eid, np.int64) for eid, t in parts])
    ifc_tris = viewer_to_ifc(tris.reshape(-1, 3), shift).reshape(-1, 3, 3)
    e1, e2 = ifc_tris[:, 1] - ifc_tris[:, 0], ifc_tris[:, 2] - ifc_tris[:, 0]
    cross = np.cross(e1, e2)
    area = 0.5 * np.linalg.norm(cross, axis=1)
    keep = area > 1e-9
    ifc_tris, owner, cross, area = ifc_tris[keep], owner[keep], cross[keep], area[keep]
    normal = cross / (2 * area[:, None])
    pick = rng.choice(len(area), size=n_points, p=area / area.sum())
    r1, r2 = rng.random(n_points), rng.random(n_points)
    s = np.sqrt(r1)
    a, b, c = ifc_tris[pick, 0], ifc_tris[pick, 1], ifc_tris[pick, 2]
    pts = (1 - s)[:, None] * a + (s * (1 - r2))[:, None] * b + (s * r2)[:, None] * c
    eid = owner[pick]
    nrm = normal[pick]

    classes_name = np.array([elements[i]["ifcClass"] for i in range(len(elements))])
    pcls = classes_name[eid]

    # incomplete scan: a band of every wall is missing
    keep = np.ones(n_points, bool)
    for i in np.unique(eid[np.isin(pcls, ["IfcWall", "IfcWallStandardCase"])]):
        m = eid == i
        lo, hi = pts[m].min(0), pts[m].max(0)
        axis = 0 if (hi[0] - lo[0]) >= (hi[1] - lo[1]) else 1
        u = (pts[m, axis] - lo[axis]) / max(hi[axis] - lo[axis], 1e-9)
        keep[np.flatnonzero(m)[(u >= 0.40) & (u < 0.40 + wall_drop)]] = False
    dropped = int((~keep).sum())

    # displaced duct: diagonal in plan, so no face slides along itself
    duct = pcls == "IfcDuctSegment"
    d = np.array([1.0, 1.0, 0.0]) / np.sqrt(2.0)
    pts[duct] += d * duct_shift

    pts = pts + rng.normal(0.0, sigma, pts.shape)

    # colour and intensity
    col = np.array([elements[i]["color"][:3] for i in range(len(elements))], np.float64)[eid]
    centre = (ifc_tris.reshape(-1, 3).min(0) + ifc_tris.reshape(-1, 3).max(0)) / 2.0
    scanner = centre + np.array([0.0, 0.0, 1.5])
    to_s = scanner - pts
    to_s /= np.linalg.norm(to_s, axis=1)[:, None] + 1e-12
    inc = np.abs((to_s * nrm).sum(1))
    shade = 0.75 + 0.25 * inc + rng.normal(0, 0.02, n_points)
    rgb = np.clip(col * shade[:, None] * 255.0, 0, 255).astype(np.uint8)
    intensity = np.clip(8000 + 50000 * inc + rng.normal(0, 1500, n_points), 0, 65535).astype(np.uint16)
    cls = np.array([CLASS_OF.get(n, 1) for n in classes_name], np.uint8)[eid]
    return pts[keep], rgb[keep], intensity[keep], cls[keep], dropped


# ---------------------------------------------------------------- writers

def write_las(path: Path, xyz, rgb, intensity, cls) -> None:
    """LAS 1.2, point data record format 2 (26 bytes), scale 1 mm, offset at the floored minimum."""
    n = len(xyz)
    scale = 0.001
    offset = np.floor(xyz.min(0))
    q = np.rint((xyz - offset) / scale).astype(np.int64)
    rec = np.zeros(n, dtype=[("x", "<i4"), ("y", "<i4"), ("z", "<i4"), ("i", "<u2"), ("flags", "u1"), ("cls", "u1"),
                              ("angle", "i1"), ("user", "u1"), ("src", "<u2"), ("r", "<u2"), ("g", "<u2"), ("b", "<u2")])
    rec["x"], rec["y"], rec["z"] = q[:, 0], q[:, 1], q[:, 2]
    rec["i"], rec["flags"], rec["cls"] = intensity, 0b00001001, cls  # return 1 of 1
    rec["r"], rec["g"], rec["b"] = rgb[:, 0].astype(np.uint16) * 257, rgb[:, 1].astype(np.uint16) * 257, rgb[:, 2].astype(np.uint16) * 257
    assert rec.itemsize == 26
    mn, mx = xyz.min(0), xyz.max(0)
    head = bytearray()
    head += b"LASF"
    head += struct.pack("<HH", 0, 0)  # file source id, global encoding
    head += struct.pack("<IHH8s", 0, 0, 0, b"\0" * 8)  # project GUID
    head += struct.pack("<BB", 1, 2)
    head += b"xray-ref".ljust(32, b"\0")  # system identifier
    head += b"make_pointcloud.py".ljust(32, b"\0")  # generating software
    head += struct.pack("<HH", 1, 2026)  # creation day, year
    head += struct.pack("<HIIBH", 227, 227, 0, 2, 26)  # header size, offset to points, VLR count, format, record length
    head += struct.pack("<I", n)
    head += struct.pack("<5I", n, 0, 0, 0, 0)
    head += struct.pack("<3d", scale, scale, scale)
    head += struct.pack("<3d", *offset)
    head += struct.pack("<6d", mx[0], mn[0], mx[1], mn[1], mx[2], mn[2])
    assert len(head) == 227, len(head)
    path.write_bytes(bytes(head) + rec.tobytes())


def write_ply(path: Path, xyz, rgb, intensity, cls) -> None:
    """Binary little endian PLY: float x y z, uchar red green blue, uchar intensity (high byte), uchar classification."""
    n = len(xyz)
    rec = np.zeros(n, dtype=[("x", "<f4"), ("y", "<f4"), ("z", "<f4"), ("r", "u1"), ("g", "u1"), ("b", "u1"), ("i", "u1"), ("c", "u1")])
    rec["x"], rec["y"], rec["z"] = xyz[:, 0], xyz[:, 1], xyz[:, 2]
    rec["r"], rec["g"], rec["b"] = rgb[:, 0], rgb[:, 1], rgb[:, 2]
    rec["i"], rec["c"] = (intensity >> 8).astype(np.uint8), cls
    head = ("ply\nformat binary_little_endian 1.0\ncomment make_pointcloud.py: synthetic as-built scan, IFC project coordinates\n"
            f"element vertex {n}\nproperty float x\nproperty float y\nproperty float z\nproperty uchar red\nproperty uchar green\n"
            "property uchar blue\nproperty uchar intensity\nproperty uchar classification\nend_header\n")
    path.write_bytes(head.encode("ascii") + rec.tobytes())


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--model", default=str(ROOT / "web/public/models/building"), help="path without extension of the .glb/.json pair")
    ap.add_argument("--out", default=str(ROOT / "web/public/samples"))
    ap.add_argument("--name", default=None, help="output base name (default: <model>-scan)")
    ap.add_argument("--points", type=int, default=230000)
    ap.add_argument("--sigma", type=float, default=0.005, help="noise sigma per axis, metres")
    ap.add_argument("--duct-shift", type=float, default=0.08, help="duct displacement, metres")
    ap.add_argument("--wall-drop", type=float, default=0.10, help="share of each wall's length left unscanned")
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args(argv)
    base = Path(a.model)
    name = a.name or f"{base.name}-scan"
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    xyz, rgb, inten, cls, dropped = sample(base, a.points, a.sigma, a.duct_shift, a.wall_drop, a.seed)
    write_las(out / f"{name}.las", xyz, rgb, inten, cls)
    write_ply(out / f"{name}.ply", xyz, rgb, inten, cls)
    for ext in ("las", "ply"):
        p = out / f"{name}.{ext}"
        print(f"{p.relative_to(ROOT) if p.is_relative_to(ROOT) else p}: {len(xyz)} points, {p.stat().st_size / 1e6:.2f} MB")
    print(f"dropped {dropped} wall points ({100 * dropped / a.points:.1f}% of all) to mimic an incomplete scan; duct displaced {a.duct_shift * 1000:.0f} mm")
    return 0


if __name__ == "__main__":
    sys.exit(main())
