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
  python3 tools/make_pointcloud.py                       # web/public/samples/building-scan.{las,ply,e57}, 230000 sampled
  python3 tools/make_pointcloud.py --model web/public/models/fzk-haus --points 230000 --name fzk-haus-scan
  python3 tools/make_pointcloud.py --phone               # web/public/samples/building-phone-scan.ply (see below)

--phone writes what an iPhone / iPad LiDAR app (Polycam, Scaniverse, 3d Scanner App, SiteScape) exports for one room:
only the surfaces a walk through the back room of the house sees (a box crop of the room, faces turned towards the
walk path, no ceiling above --phone-top), Y up in the scan's own frame, the origin where the scan started and a
heading of --heading degrees, 1.5 cm noise (the default --sigma in this mode), optionally a slow heading drift
(--drift degrees per metre away from the start). Binary little endian PLY, float x y z and uchar rgb, no intensity or
classes. The true transform is in a header comment, so tests can score a registration:
  comment truth: viewer = Ry(<heading> deg) * p + (tx, ty, tz)      (coordinates viewer, model building)
About 150000 points, 2.3 MB.

About 230000 points (after the dropped wall band) keeps each file under 6 MB (LAS format 2 is 26 bytes per point). Needs numpy;
the E57 copy (ScaledInteger 1 mm, about 2.5 MB) also needs pye57 (`pip install pye57`, MIT, wraps libE57Format, BSL-1.0)
and is skipped without it (`--formats las,ply` to write only those).
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


def write_e57(path: Path, xyz, rgb, intensity) -> bool:
    """E57 through pye57 (libE57Format), when installed: ScaledInteger x y z at 1 mm (offset at the floored minimum),
    16-bit intensity with intensityLimits, 8-bit colour with colorLimits, identity pose. E57 has no standard
    classification field, so the classes are not written. Returns False when pye57 is missing."""
    try:
        import uuid
        from pye57 import libe57
    except ImportError:
        print("pye57 is not installed (pip install pye57): E57 sample skipped")
        return False
    if path.exists():
        path.unlink()
    n = len(xyz)
    scale = 0.001
    offset = np.floor(xyz.min(0))
    top = np.rint((xyz.max(0) - offset) / scale).astype(np.int64) + 1
    imf = libe57.ImageFile(str(path), "w")
    root = imf.root()
    imf.extensionsAdd("", libe57.E57_V1_0_URI)
    root.set("formatName", libe57.StringNode(imf, "ASTM E57 3D Imaging Data File"))
    root.set("guid", libe57.StringNode(imf, "{%s}" % uuid.UUID(int=0x5ca7)))
    root.set("versionMajor", libe57.IntegerNode(imf, 1))
    root.set("versionMinor", libe57.IntegerNode(imf, 0))
    root.set("data3D", libe57.VectorNode(imf, True))
    root.set("images2D", libe57.VectorNode(imf, True))
    scan = libe57.StructureNode(imf)
    scan.set("guid", libe57.StringNode(imf, "{%s}" % uuid.UUID(int=0x5ca8)))
    scan.set("name", libe57.StringNode(imf, path.stem))
    scan.set("description", libe57.StringNode(imf, "make_pointcloud.py: synthetic as-built scan, IFC project coordinates"))
    lim = libe57.StructureNode(imf)
    lim.set("intensityMinimum", libe57.IntegerNode(imf, 0))
    lim.set("intensityMaximum", libe57.IntegerNode(imf, 65535))
    scan.set("intensityLimits", lim)
    col = libe57.StructureNode(imf)
    for c in ("Red", "Green", "Blue"):
        col.set(f"color{c}Minimum", libe57.IntegerNode(imf, 0))
        col.set(f"color{c}Maximum", libe57.IntegerNode(imf, 255))
    scan.set("colorLimits", col)
    proto = libe57.StructureNode(imf)
    for k, axis in enumerate("XYZ"):
        proto.set(f"cartesian{axis}", libe57.ScaledIntegerNode(imf, 0, 0, int(top[k]), scale, float(offset[k])))
    proto.set("intensity", libe57.IntegerNode(imf, 0, 0, 65535))
    for c in ("Red", "Green", "Blue"):
        proto.set(f"color{c}", libe57.IntegerNode(imf, 0, 0, 255))
    points = libe57.CompressedVectorNode(imf, proto, libe57.VectorNode(imf, True))
    scan.set("points", points)
    root["data3D"].append(scan)
    arrays = {f"cartesian{a}": np.ascontiguousarray(xyz[:, k], dtype=np.float64) for k, a in enumerate("XYZ")}
    # float64 buffers throughout: pye57 passes an int64 numpy buffer to libE57Format as 32-bit integers (every other
    # value would read 0); float64 with conversion is exact for these integers
    arrays["intensity"] = intensity.astype(np.float64)
    for k, c in enumerate(("Red", "Green", "Blue")):
        arrays[f"color{c}"] = rgb[:, k].astype(np.float64)
    bufs = libe57.VectorSourceDestBuffer()
    for name, a in arrays.items():
        bufs.append(libe57.SourceDestBuffer(imf, name, a, n, True, True))
    w = points.writer(bufs)
    w.write(n)
    w.close()
    imf.close()
    return True


# ---------------------------------------------------------------- phone scan

# The back room of web/public/models/building in the viewer frame: inside faces of the back, left and inner walls,
# the floor slab top, the kitchen, the plumbing wall, the chimney and the duct; cropped below --phone-top.
PHONE_ROOM = (np.array([-2.62, -2.56, -2.82]), np.array([2.37, 0.6, 1.02]))
PHONE_START = np.array([-0.6, -1.25, -0.6])  # where the scan starts (device height about 1.3 m above the floor)


def ry(deg: float) -> np.ndarray:
    """Rotation about Y like three's makeRotationY: x' = c x + s z, z' = -s x + c z."""
    t = np.radians(deg)
    c, s = np.cos(t), np.sin(t)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def sample_phone(base: Path, n_points: int, sigma: float, heading: float, top: float, drift: float, seed: int):
    rng = np.random.default_rng(seed)
    parts, side = load_triangles(base)
    elements = side["elements"]
    tris = np.concatenate([t for _, t in parts])
    owner = np.concatenate([np.full(len(t), eid, np.int64) for eid, t in parts])
    lo, hi = PHONE_ROOM[0].copy(), PHONE_ROOM[1].copy()
    hi[1] = min(hi[1], top)
    e1, e2 = tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0]
    cross = np.cross(e1, e2)
    area = 0.5 * np.linalg.norm(cross, axis=1)
    keep = area > 1e-9
    tris, owner, cross, area = tris[keep], owner[keep], cross[keep], area[keep]
    normal = cross / (2 * area[:, None])
    # oversample, then keep points inside the room crop whose face turns towards one of the stops of a short walk
    # through the room: the far side of a wall or the underside of the floor is never seen
    m = n_points * 8
    pick = rng.choice(len(area), size=m, p=area / area.sum())
    r1, r2 = rng.random(m), rng.random(m)
    s = np.sqrt(r1)
    a, b, c = tris[pick, 0], tris[pick, 1], tris[pick, 2]
    pts = (1 - s)[:, None] * a + (s * (1 - r2))[:, None] * b + (s * r2)[:, None] * c
    nrm = normal[pick]
    eid = owner[pick]
    inside = np.all((pts >= lo) & (pts <= hi), axis=1)
    path = np.array([[-1.6, -1.25, -1.8], [0.9, -1.25, -1.8], [0.9, -1.25, 0.2], [-1.6, -1.25, 0.2]])
    see = np.zeros(m, bool)
    for q in path:
        see |= ((q - pts) * nrm).sum(1) > 0.02
    ok = np.flatnonzero(inside & see)
    if len(ok) < n_points:
        raise SystemExit(f"phone scan: only {len(ok)} visible points, ask for fewer")
    ok = ok[:n_points]
    pts, nrm, eid = pts[ok], nrm[ok], eid[ok]
    pts = pts + rng.normal(0.0, sigma, pts.shape)
    col = np.array([elements[i]["color"][:3] for i in range(len(elements))], np.float64)[eid]
    light = np.array([0.3, 0.8, 0.5]) / np.linalg.norm([0.3, 0.8, 0.5])
    shade = 0.7 + 0.3 * np.abs(nrm @ light) + rng.normal(0, 0.03, len(pts))
    rgb = np.clip(col * shade[:, None] * 255.0, 0, 255).astype(np.uint8)
    # into the scan frame: viewer = Ry(heading) p + start  ->  p = Ry(-heading) (viewer - start); row vectors: v R
    local = (pts - PHONE_START) @ ry(heading)
    if drift:
        # the heading drifts slowly with the horizontal distance from the start
        ang = np.radians(drift * np.hypot(local[:, 0], local[:, 2]))
        cs, sn = np.cos(ang), np.sin(ang)
        x, z = local[:, 0].copy(), local[:, 2].copy()
        local[:, 0], local[:, 2] = cs * x + sn * z, -sn * x + cs * z
    order = rng.permutation(len(local))  # scanners do not write points sorted by element
    return local[order], rgb[order]


def write_phone_ply(path: Path, xyz, rgb, heading: float, drift: float) -> None:
    n = len(xyz)
    rec = np.zeros(n, dtype=[("x", "<f4"), ("y", "<f4"), ("z", "<f4"), ("r", "u1"), ("g", "u1"), ("b", "u1")])
    rec["x"], rec["y"], rec["z"] = xyz[:, 0], xyz[:, 1], xyz[:, 2]
    rec["r"], rec["g"], rec["b"] = rgb[:, 0], rgb[:, 1], rgb[:, 2]
    t = PHONE_START
    head = ("ply\nformat binary_little_endian 1.0\n"
            "comment make_pointcloud.py --phone: synthetic phone LiDAR scan of one room, Y up, own origin and heading\n"
            f"comment truth: viewer = Ry({heading:.6f} deg) * p + ({t[0]:.6f}, {t[1]:.6f}, {t[2]:.6f})\n"
            f"comment drift: {drift:.6f} deg per m\n"
            f"element vertex {n}\nproperty float x\nproperty float y\nproperty float z\nproperty uchar red\nproperty uchar green\n"
            "property uchar blue\nend_header\n")
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
    ap.add_argument("--formats", default="las,ply,e57", help="comma separated subset of las, ply, e57 (e57 needs pye57)")
    ap.add_argument("--phone", action="store_true", help="write a phone LiDAR style scan of one room instead (PLY only)")
    ap.add_argument("--heading", type=float, default=37.0, help="--phone: heading of the scan frame, degrees")
    ap.add_argument("--phone-top", type=float, default=0.6, help="--phone: no points above this viewer height (no ceiling)")
    ap.add_argument("--drift", type=float, default=0.0, help="--phone: heading drift, degrees per metre from the start")
    a = ap.parse_args(argv)
    if a.phone:
        return main_phone(a, argv)
    formats = [f.strip() for f in a.formats.split(",") if f.strip()]
    base = Path(a.model)
    name = a.name or f"{base.name}-scan"
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    xyz, rgb, inten, cls, dropped = sample(base, a.points, a.sigma, a.duct_shift, a.wall_drop, a.seed)
    if "las" in formats:
        write_las(out / f"{name}.las", xyz, rgb, inten, cls)
    if "ply" in formats:
        write_ply(out / f"{name}.ply", xyz, rgb, inten, cls)
    if "e57" in formats and not write_e57(out / f"{name}.e57", xyz, rgb, inten):
        formats.remove("e57")
    for ext in formats:
        p = out / f"{name}.{ext}"
        print(f"{p.relative_to(ROOT) if p.is_relative_to(ROOT) else p}: {len(xyz)} points, {p.stat().st_size / 1e6:.2f} MB")
    print(f"dropped {dropped} wall points ({100 * dropped / a.points:.1f}% of all) to mimic an incomplete scan; duct displaced {a.duct_shift * 1000:.0f} mm")
    return 0


def main_phone(a, argv) -> int:
    base = Path(a.model)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    given = argv if argv is not None else sys.argv[1:]
    name = a.name or f"{base.name}-phone-scan"
    sigma = a.sigma if any(x.startswith("--sigma") for x in given) else 0.015
    n = a.points if any(x.startswith("--points") for x in given) else 150000
    xyz, rgb = sample_phone(base, n, sigma, a.heading, a.phone_top, a.drift, a.seed)
    p = out / f"{name}.ply"
    write_phone_ply(p, xyz, rgb, a.heading, a.drift)
    print(f"{p.relative_to(ROOT) if p.is_relative_to(ROOT) else p}: {len(xyz)} points, {p.stat().st_size / 1e6:.2f} MB, heading {a.heading} deg, "
          f"start {PHONE_START.tolist()}, noise {sigma * 1000:.1f} mm, drift {a.drift} deg/m")
    return 0


if __name__ == "__main__":
    sys.exit(main())
