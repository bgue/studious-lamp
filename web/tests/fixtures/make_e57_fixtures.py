#!/usr/bin/env python3
"""Generates the E57 fixtures in tests/fixtures/pointcloud with an independent writer: libE57Format through pye57.

    python3 -m venv /tmp/e57env && /tmp/e57env/bin/pip install pye57 numpy
    /tmp/e57env/bin/python web/tests/fixtures/make_e57_fixtures.py

pye57 (MIT) wraps libE57Format (Boost Software License 1.0). Both are test-time tools only; nothing of them is in the
viewer. The expected values in e57-expected.json are what libE57Format READS BACK from each file (so Float32 rounding
and ScaledInteger quantisation are included), with the scan pose applied here in float64 and cross-checked against
pye57's own read_scan(transform=True). Seeded: reruns give the same points (guids differ).

Files:
  e57-cart-float.e57     pye57's high level writer (Float single xyz, Float intensity, Integer rgb), georeferenced
                         coordinates around (2 600 000, 1 200 000), identity pose
  e57-cart-scaled.e57    ScaledInteger xyz (1 mm, large offset), Integer intensity 0..4095 with intensityLimits,
                         16-bit colour with colorLimits 0..65535, cartesianInvalidState (0, 1, 2): 12 000 records, so
                         every bytestream spans several data packets; a long non-ASCII description makes the XML span
                         pages at a non-1020 aligned length
  e57-spherical.e57      Float double sphericalRange/Azimuth/Elevation, sphericalInvalidState as an Integer without
                         bounds (a 64-bit bytestream), Float single intensity, a pose
Third-party files, copied from https://github.com/asmaloney/libE57Format-test-data (only their expected values are
computed here, with libE57Format):
  e57-ref-bunny-int32.e57  reference/bunnyInt32.e57 from the E57 example data of libe57.org (the reference
                         implementation's writer): 30 571 points, ScaledInteger xyz, cartesianInvalidState. "Test Data
                         License" (MIT style; no notice needed for copies in binary form)
  e57-las2e57-colour.e57   3rdParty/las2e57/ColourRepresentation.e57, written by LAStools' las2e57: no colorLimits
                         (the colour fields' own 16-bit bounds apply), LAS extension elements, Blob and
                         pointGroupingSchemes sections. CC0 1.0
  e57-two-scans.e57      two scans with different rotations and translations, Integer rgb: the first Float double xyz,
                         the second a 27 bit ScaledInteger (0.1 micrometre)
"""
import json
import math
import os
import uuid

import numpy as np
import pye57
from pye57 import libe57

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pointcloud")
rng = np.random.default_rng(57)


def header(imf):
    root = imf.root()
    imf.extensionsAdd("", libe57.E57_V1_0_URI)
    root.set("formatName", libe57.StringNode(imf, "ASTM E57 3D Imaging Data File"))
    root.set("guid", libe57.StringNode(imf, "{%s}" % uuid.uuid4()))
    root.set("versionMajor", libe57.IntegerNode(imf, 1))
    root.set("versionMinor", libe57.IntegerNode(imf, 0))
    root.set("data3D", libe57.VectorNode(imf, True))
    root.set("images2D", libe57.VectorNode(imf, True))
    return root


def quat(axis, deg):
    a = np.asarray(axis, float)
    a = a / np.linalg.norm(a)
    h = math.radians(deg) / 2
    return np.array([math.cos(h), *(a * math.sin(h))])


def rotate(q, p):
    """Rotate points p (n,3) by the unit quaternion q = (w, x, y, z), float64."""
    w, x, y, z = q
    r = np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
        [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
        [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)],
    ])
    return p @ r.T


def add_scan(imf, name, proto_fields, arrays, *, pose=None, limits=None, description=None):
    """proto_fields: list of (field, node factory); arrays: field -> numpy array (scaled values)."""
    root = imf.root()
    scan = libe57.StructureNode(imf)
    scan.set("guid", libe57.StringNode(imf, "{%s}" % uuid.uuid4()))
    scan.set("name", libe57.StringNode(imf, name))
    if description:
        scan.set("description", libe57.StringNode(imf, description))
    for key, fields in (limits or {}).items():
        box = libe57.StructureNode(imf)
        for k, v in fields.items():
            box.set(k, v(imf))
        scan.set(key, box)
    if pose is not None:
        q, t = pose
        p = libe57.StructureNode(imf)
        r = libe57.StructureNode(imf)
        for k, v in zip("wxyz", q):
            r.set(k, libe57.FloatNode(imf, float(v)))
        tr = libe57.StructureNode(imf)
        for k, v in zip("xyz", t):
            tr.set(k, libe57.FloatNode(imf, float(v)))
        p.set("rotation", r)
        p.set("translation", tr)
        scan.set("pose", p)
    proto = libe57.StructureNode(imf)
    for f, make in proto_fields:
        proto.set(f, make(imf))
    points = libe57.CompressedVectorNode(imf, proto, libe57.VectorNode(imf, True))
    scan.set("points", points)
    root["data3D"].append(scan)
    n = len(next(iter(arrays.values())))
    bufs = libe57.VectorSourceDestBuffer()
    keep = []
    WRITTEN.setdefault(imf.fileName(), []).append(arrays)
    for f, _ in proto_fields:
        # float64 buffers for every field: pye57 hands an int64 numpy buffer to libE57Format as 32-bit integers
        # (every other value then reads 0), float64 with conversion is exact for these integers
        a = np.ascontiguousarray(arrays[f], dtype=np.float64)
        keep.append(a)
        bufs.append(libe57.SourceDestBuffer(imf, f, a, n, True, True))
    w = points.writer(bufs)
    w.write(n)
    w.close()


WRITTEN = {}


def verify_written(path, scans):
    """The values libE57Format reads back are the ones that were written (within the ScaledInteger quantum)."""
    e = pye57.E57(path)
    assert e.scan_count == len(scans), path
    for i, arrays in enumerate(scans):
        raw = read_raw(e, e.get_header(i))
        for f, a in arrays.items():
            tol = 0.6e-3 if "cartesian" in f and "State" not in f else 1e-5 * max(1.0, float(np.abs(a).max()))
            assert np.allclose(raw[f], np.asarray(a, np.float64), rtol=0, atol=tol), (path, f, raw[f][:6], a[:6])
    e.close()


def read_raw(e, h):
    """All fields of a scan as float64 (pye57's read_scan_raw reads colours as uint8, too small for 16-bit colour)."""
    n = h.point_count
    bufs = libe57.VectorSourceDestBuffer()
    raw = {}
    for f in h.point_fields:
        raw[f] = np.empty(n, np.float64)
        bufs.append(libe57.SourceDestBuffer(e.image_file, f, raw[f], n, True, True))
    h.points.reader(bufs).read()
    return raw


def read_back(path):
    """Every scan as libE57Format reads it: raw fields, the pose applied in float64, plus pye57's transform for checking."""
    e = pye57.E57(path)
    scans = []
    for i in range(e.scan_count):
        h = e.get_header(i)
        raw = read_raw(e, h)
        if "cartesianX" in raw:
            p = np.stack([raw["cartesianX"], raw["cartesianY"], raw["cartesianZ"]], 1).astype(np.float64)
            inv = raw.get("cartesianInvalidState")
        else:
            r, az, el = raw["sphericalRange"], raw["sphericalAzimuth"], raw["sphericalElevation"]
            p = np.stack([r * np.cos(el) * np.cos(az), r * np.cos(el) * np.sin(az), r * np.sin(el)], 1)
            inv = raw.get("sphericalInvalidState")
        node = h.node
        q = np.array([1.0, 0, 0, 0])
        t = np.zeros(3)
        if node.isDefined("pose"):
            q = np.array([float(node["pose"]["rotation"][k].value()) for k in "wxyz"])
            t = np.array([float(node["pose"]["translation"][k].value()) for k in "xyz"])
        world = rotate(q, p) + t
        # cross-check the pose maths against pye57 (pyquaternion) on the valid points
        if "cartesianX" in raw:
            ref = e.read_scan(i, transform=True, ignore_missing_fields=True)
            refp = np.stack([ref["cartesianX"], ref["cartesianY"], ref["cartesianZ"]], 1)
            ok = inv == 0 if inv is not None else slice(None)  # read_scan drops invalid states 1 and 2 as well
            assert np.allclose(refp, world[ok], atol=1e-6 * max(1, np.abs(world).max())), path
        valid = np.ones(len(p), bool) if inv is None else (inv == 0)
        out = {"world": world, "valid": valid}
        if "intensity" in raw:
            lo, hi = h.intensityMinimum, h.intensityMaximum
            out["intensity"] = (raw["intensity"].astype(np.float64) - lo) / (hi - lo)
        if "colorRed" in raw:
            def lim(c):
                if node.isDefined("colorLimits"):
                    return node["colorLimits"][f"color{c}Minimum"].value(), node["colorLimits"][f"color{c}Maximum"].value()
                el = libe57.StructureNode(node["points"].prototype())[f"color{c}"]  # no colorLimits (LAStools): the field's own bounds
                return el.minimum(), el.maximum()
            out["rgb"] = np.stack([
                np.rint((raw[f"color{c}"].astype(np.float64) - lim(c)[0]) / (lim(c)[1] - lim(c)[0]) * 255)
                for c in ("Red", "Green", "Blue")], 1).astype(int)
        scans.append(out)
    e.close()
    return scans


def expected(path, sample_every=1):
    scans = read_back(path)
    world = np.concatenate([s["world"][s["valid"]] for s in scans])
    rgb = np.concatenate([s["rgb"][s["valid"]] for s in scans]) if all("rgb" in s for s in scans) else None
    inten = np.concatenate([s["intensity"][s["valid"]] for s in scans]) if all("intensity" in s for s in scans) else None
    idx = list(range(0, len(world), sample_every))
    if idx[-1] != len(world) - 1:
        idx.append(len(world) - 1)
    pts = []
    for i in idx:
        rec = {"i": i, "xyz": [float(v) for v in world[i]]}
        if rgb is not None:
            rec["rgb"] = [int(v) for v in rgb[i]]
        if inten is not None:
            rec["intensity"] = float(inten[i])
        pts.append(rec)
    return {
        "count": int(len(world)),
        "records": int(sum(len(s["valid"]) for s in scans)),
        "scans": len(scans),
        "sum": [float(v) for v in world.sum(0)],
        "min": [float(v) for v in world.min(0)],
        "max": [float(v) for v in world.max(0)],
        "points": pts,
    }


def main():
    os.makedirs(OUT, exist_ok=True)
    result = {}

    # 1. pye57's own high level writer: what most Python tools produce
    path = os.path.join(OUT, "e57-cart-float.e57")
    n = 60
    base = np.array([2_600_000.0, 1_200_000.0, 420.0])
    xyz = base + rng.uniform(0, 20, (n, 3))
    e = pye57.E57(path, "w")
    written = {
        "cartesianX": xyz[:, 0], "cartesianY": xyz[:, 1], "cartesianZ": xyz[:, 2],
        "intensity": rng.uniform(0.1, 0.9, n).astype("f"),
        "colorRed": rng.integers(0, 256, n).astype("B"), "colorGreen": rng.integers(0, 256, n).astype("B"),
        "colorBlue": rng.integers(0, 256, n).astype("B"),
    }
    e.write_scan_raw(written, name="georeferenced")
    e.close()
    verify_written(path, [{k: v for k, v in written.items() if not k.startswith("cartesian")}])
    result["e57-cart-float.e57"] = expected(path)

    # 2. ScaledInteger xyz, multi-packet, invalid states, XML across pages
    path = os.path.join(OUT, "e57-cart-scaled.e57")
    n = 12000
    off = np.array([512_000.0, 5_400_000.0, 300.0])
    xyz = off + np.rint(rng.uniform(0, 16, (n, 3)) * 1000) / 1000
    state = np.where(np.arange(n) % 13 == 5, 2, np.where(np.arange(n) % 17 == 3, 1, 0)).astype(np.int8)
    inten = rng.integers(0, 4096, n).astype(np.int64)
    rgb16 = rng.integers(0, 65536, (n, 3)).astype(np.int64)
    if os.path.exists(path):
        os.remove(path)
    imf = libe57.ImageFile(path, "w")
    header(imf)
    sc = lambda k: (lambda f: libe57.ScaledIntegerNode(f, 0, 0, 16000, 0.001, float(off[k])))
    add_scan(imf, "scaled integer", [
        ("cartesianX", sc(0)), ("cartesianY", sc(1)), ("cartesianZ", sc(2)),
        ("cartesianInvalidState", lambda f: libe57.IntegerNode(f, 0, 0, 2)),
        ("intensity", lambda f: libe57.IntegerNode(f, 0, 0, 4095)),
        ("colorRed", lambda f: libe57.IntegerNode(f, 0, 0, 65535)),
        ("colorGreen", lambda f: libe57.IntegerNode(f, 0, 0, 65535)),
        ("colorBlue", lambda f: libe57.IntegerNode(f, 0, 0, 65535)),
    ], {
        "cartesianX": xyz[:, 0].copy(), "cartesianY": xyz[:, 1].copy(), "cartesianZ": xyz[:, 2].copy(),
        "cartesianInvalidState": state, "intensity": inten,
        "colorRed": rgb16[:, 0].copy(), "colorGreen": rgb16[:, 1].copy(), "colorBlue": rgb16[:, 2].copy(),
    }, limits={
        "intensityLimits": {"intensityMinimum": lambda f: libe57.IntegerNode(f, 0), "intensityMaximum": lambda f: libe57.IntegerNode(f, 4095)},
        "colorLimits": {
            "colorRedMinimum": lambda f: libe57.IntegerNode(f, 0), "colorRedMaximum": lambda f: libe57.IntegerNode(f, 65535),
            "colorGreenMinimum": lambda f: libe57.IntegerNode(f, 0), "colorGreenMaximum": lambda f: libe57.IntegerNode(f, 65535),
            "colorBlueMinimum": lambda f: libe57.IntegerNode(f, 0), "colorBlueMaximum": lambda f: libe57.IntegerNode(f, 65535),
        },
    }, description="Façade scan, Zürich – " + "Prüfung der Bauausführung ✓ " * 90)
    imf.close()
    verify_written(path, WRITTEN.pop(path))
    result["e57-cart-scaled.e57"] = expected(path, sample_every=97)

    # 3. spherical coordinates
    path = os.path.join(OUT, "e57-spherical.e57")
    n = 400
    rr = rng.uniform(1, 30, n)
    az = rng.uniform(-math.pi, math.pi, n)
    el = rng.uniform(-1.2, 1.2, n)
    sstate = np.where(np.arange(n) % 9 == 4, 2, np.where(np.arange(n) % 23 == 7, 1, 0)).astype(np.int8)
    if os.path.exists(path):
        os.remove(path)
    imf = libe57.ImageFile(path, "w")
    header(imf)
    add_scan(imf, "spherical", [
        ("sphericalRange", lambda f: libe57.FloatNode(f, 0.0, libe57.E57_DOUBLE, 0.0, 100.0)),
        ("sphericalAzimuth", lambda f: libe57.FloatNode(f, 0.0, libe57.E57_DOUBLE, -4.0, 4.0)),
        ("sphericalElevation", lambda f: libe57.FloatNode(f, 0.0, libe57.E57_DOUBLE, -2.0, 2.0)),
        ("sphericalInvalidState", lambda f: libe57.IntegerNode(f, 0)),  # default int64 bounds: a 64-bit bytestream
        ("intensity", lambda f: libe57.FloatNode(f, 0.0, libe57.E57_SINGLE, 0.0, 2.0)),
    ], {
        "sphericalRange": rr, "sphericalAzimuth": az, "sphericalElevation": el, "sphericalInvalidState": sstate,
        "intensity": rng.uniform(0, 2, n).astype(np.float64),
    }, pose=(quat([0, 0, 1], 30), [10.0, -5.0, 1.5]), limits={
        "intensityLimits": {"intensityMinimum": lambda f: libe57.FloatNode(f, 0.0), "intensityMaximum": lambda f: libe57.FloatNode(f, 2.0)},
    })
    imf.close()
    verify_written(path, WRITTEN.pop(path))
    result["e57-spherical.e57"] = expected(path)

    # 4. two scans with poses
    path = os.path.join(OUT, "e57-two-scans.e57")
    if os.path.exists(path):
        os.remove(path)
    imf = libe57.ImageFile(path, "w")
    header(imf)
    poses = [(quat([0, 0, 1], 90), [100.0, 200.0, 3.0]), (quat([1, 2, 3], 37), [-4.25, 7.5, 0.125])]
    for k, pose in enumerate(poses):
        n = 150 + 50 * k
        p = rng.uniform(-5, 5, (n, 3))
        cols = rng.integers(0, 256, (n, 3)).astype(np.int64)
        if k == 0:
            fl = lambda f: libe57.FloatNode(f, 0.0, libe57.E57_DOUBLE)
        else:  # 0.1 micrometre over 10 m: a 27 bit ScaledInteger
            fl = lambda f: libe57.ScaledIntegerNode(f, 0, -50_000_000, 50_000_000, 1e-7, 0.0)
        add_scan(imf, f"station {k + 1}", [
            ("cartesianX", fl), ("cartesianY", fl), ("cartesianZ", fl),
            ("colorRed", lambda f: libe57.IntegerNode(f, 0, 0, 255)),
            ("colorGreen", lambda f: libe57.IntegerNode(f, 0, 0, 255)),
            ("colorBlue", lambda f: libe57.IntegerNode(f, 0, 0, 255)),
        ], {
            "cartesianX": p[:, 0].copy(), "cartesianY": p[:, 1].copy(), "cartesianZ": p[:, 2].copy(),
            "colorRed": cols[:, 0].copy(), "colorGreen": cols[:, 1].copy(), "colorBlue": cols[:, 2].copy(),
        }, pose=pose, limits={"colorLimits": {
            "colorRedMinimum": lambda f: libe57.IntegerNode(f, 0), "colorRedMaximum": lambda f: libe57.IntegerNode(f, 255),
            "colorGreenMinimum": lambda f: libe57.IntegerNode(f, 0), "colorGreenMaximum": lambda f: libe57.IntegerNode(f, 255),
            "colorBlueMinimum": lambda f: libe57.IntegerNode(f, 0), "colorBlueMaximum": lambda f: libe57.IntegerNode(f, 255),
        }})
    imf.close()
    verify_written(path, WRITTEN.pop(path))
    result["e57-two-scans.e57"] = expected(path)

    for f, every in (("e57-ref-bunny-int32.e57", 101), ("e57-las2e57-colour.e57", 1)):
        result[f] = expected(os.path.join(OUT, f), sample_every=every)

    with open(os.path.join(OUT, "e57-expected.json"), "w") as fh:
        json.dump(result, fh, indent=0)
    for k, v in result.items():
        print(f"{k}: {os.path.getsize(os.path.join(OUT, k))} bytes, {v['records']} records, {v['count']} valid points, {v['scans']} scan(s)")


if __name__ == "__main__":
    main()
