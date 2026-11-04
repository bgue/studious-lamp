"""Shared helpers for ifc2glb.py and synth_model.py.

Hand-rolled glTF 2.0 binary writer (JSON chunk + one BIN chunk) and the
xray-model/1 sidecar assembly. Only numpy is required.

Input meshes are in the IFC frame (Z up, metres). `write_model` rotates them
-90 degrees about X (x, y, z) -> (x, z, -y) directly in the vertex data,
shifts the overall bounds centre to the origin and records the shift (IFC
frame) as `originShift`.
"""
from __future__ import annotations

import json
import re
import struct
from typing import Any

import numpy as np

SCHEMA = "xray-model/1"


# ---------------------------------------------------------------- element properties (hover info)
# Rules mirrored by web/src/model/ifcProps.ts; keep both in sync (web/tests/ifc-import-parity.test.ts checks them).
# Key format: Attr.ObjectType|Tag|Description|PredefinedType, <PsetName>.<PropName>, <QtoName>.<QuantityName>.
# Groups in output order: 0 attributes, 1 Pset_*Common single values, 2 whitelisted base quantities, 3 others (--props all).

PROPS_CAP = 24
PROPS_STR_MAX = 80
COMMON_QTY_NAMES = frozenset((
    "Length", "Width", "Height", "Depth", "Perimeter", "NetArea", "GrossArea", "NetVolume", "GrossVolume",
    "NetSideArea", "GrossSideArea", "CrossSectionArea", "OuterSurfaceArea", "NetWeight"))
GROUP_ATTR, GROUP_COMMON, GROUP_QTY, GROUP_OTHER = 0, 1, 2, 3
_LENGTH_TYPES = frozenset(("ifclengthmeasure", "ifcpositivelengthmeasure", "ifcnonnegativelengthmeasure"))
_INTEGER_TYPES = frozenset(("ifcinteger", "ifccountmeasure", "ifctimestamp"))


def is_common_pset(name: str) -> bool:
    return re.match(r"^Pset_.*Common$", name) is not None


def is_base_qto_set(name: str) -> bool:
    return re.match(r"^Qto_.*BaseQuantities$", name) is not None or name == "BaseQuantities"


def property_group(set_name: str, mode: str):
    if mode == "none":
        return None
    if is_common_pset(set_name):
        return GROUP_COMMON
    return GROUP_OTHER if mode == "all" else None


def quantity_group(set_name: str, qty_name: str, mode: str):
    if mode == "none":
        return None
    if is_base_qto_set(set_name) and qty_name in COMMON_QTY_NAMES:
        return GROUP_QTY
    return GROUP_OTHER if mode == "all" else None


def normalize_number(type_name: str, x, scales: dict):
    """Number of an IFC value of type `type_name`: measures in SI, integers exact, reals to 4 significant digits."""
    t = type_name.lower()
    if isinstance(x, float) and (x != x or x in (float("inf"), float("-inf"))):
        return None
    if t in _INTEGER_TYPES:
        return int(x) if float(x).is_integer() else float(x)
    v = float(x)
    if t in _LENGTH_TYPES:
        v = v * scales["length"]
    elif t == "ifcareameasure":
        v = v * scales["area"]
    elif t == "ifcvolumemeasure":
        v = v * scales["volume"]
    elif t == "ifcmassmeasure":
        v = v * scales["mass"]
    if v != v or v in (float("inf"), float("-inf")):
        return None
    r = float(f"{v:.4g}")
    return int(r) if r.is_integer() and abs(r) < 1e15 else r


def attribute_entries(object_type, tag, description, predefined_type) -> list:
    out = []
    for k, v in (("ObjectType", object_type), ("Tag", tag), ("Description", description),
                 ("PredefinedType", predefined_type)):
        if isinstance(v, str) and v != "" and v != "NOTDEFINED":
            out.append((f"Attr.{k}", v, GROUP_ATTR))
    return out


def finalize_props(entries: list, cap: int = PROPS_CAP):
    """entries: (key, value, group). Stable by group, first key wins, capped, strings clipped. None when empty."""
    out: dict = {}
    for key, value, _g in sorted(entries, key=lambda e: e[2]):
        if len(out) >= cap:
            break
        if key in out:
            continue
        out[key] = value[:PROPS_STR_MAX] if isinstance(value, str) else value
    return out or None


def box_mesh(mn, mx):
    """Flat-shaded box (24 verts, 12 tris, outward CCW) in whatever frame mn/mx are in."""
    x0, y0, z0 = mn
    x1, y1, z1 = mx
    faces = [  # (normal, 4 corners CCW seen from outside)
        ((1, 0, 0), [(x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)]),
        ((-1, 0, 0), [(x0, y1, z0), (x0, y0, z0), (x0, y0, z1), (x0, y1, z1)]),
        ((0, 1, 0), [(x1, y1, z0), (x0, y1, z0), (x0, y1, z1), (x1, y1, z1)]),
        ((0, -1, 0), [(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)]),
        ((0, 0, 1), [(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]),
        ((0, 0, -1), [(x0, y1, z0), (x1, y1, z0), (x1, y0, z0), (x0, y0, z0)]),
    ]
    v, n, f = [], [], []
    for nrm, quad in faces:
        b = len(v)
        v.extend(quad)
        n.extend([nrm] * 4)
        f.extend([(b, b + 1, b + 2), (b, b + 2, b + 3)])
    return (np.asarray(v, np.float64), np.asarray(f, np.uint32), np.asarray(n, np.float64))


def _pad4(b: bytes, pad: bytes) -> bytes:
    r = (-len(b)) % 4
    return b + pad * r


def write_glb(path: str, meshes: list[dict]) -> None:
    """meshes: list of dicts {name, extras, verts (n,3), normals (n,3), faces (m,3)}, glb frame.

    One node + one mesh + one primitive per entry; one buffer; bufferViews and
    accessors per primitive (POSITION w/ min/max, NORMAL, uint32 indices).
    """
    chunks: list[bytes] = []
    offset = 0
    buffer_views, accessors, gl_meshes, nodes = [], [], [], []

    def add_view(data: bytes, target: int) -> int:
        nonlocal offset
        assert offset % 4 == 0
        buffer_views.append({"buffer": 0, "byteOffset": offset, "byteLength": len(data), "target": target})
        chunks.append(data)
        offset += len(data)
        return len(buffer_views) - 1

    for i, m in enumerate(meshes):
        v = np.ascontiguousarray(m["verts"], dtype="<f4")
        nrm = np.ascontiguousarray(m["normals"], dtype="<f4")
        idx = np.ascontiguousarray(m["faces"], dtype="<u4").reshape(-1)
        bv_p = add_view(v.tobytes(), 34962)
        bv_n = add_view(nrm.tobytes(), 34962)
        bv_i = add_view(idx.tobytes(), 34963)
        accessors.append({"bufferView": bv_p, "componentType": 5126, "count": int(len(v)), "type": "VEC3",
                          "min": [float(x) for x in v.min(0)], "max": [float(x) for x in v.max(0)]})
        a_p = len(accessors) - 1
        accessors.append({"bufferView": bv_n, "componentType": 5126, "count": int(len(nrm)), "type": "VEC3"})
        a_n = len(accessors) - 1
        accessors.append({"bufferView": bv_i, "componentType": 5125, "count": int(len(idx)), "type": "SCALAR"})
        a_i = len(accessors) - 1
        gl_meshes.append({"name": m["name"],
                          "primitives": [{"attributes": {"POSITION": a_p, "NORMAL": a_n}, "indices": a_i, "mode": 4}]})
        nodes.append({"name": m["name"], "mesh": i, "extras": m["extras"]})

    doc: dict[str, Any] = {
        "asset": {"version": "2.0", "generator": "xray-ref tools"},
        "scene": 0,
        "scenes": [{"name": "xray", "nodes": list(range(len(nodes)))}],
        "nodes": nodes,
        "meshes": gl_meshes,
        "accessors": accessors,
        "bufferViews": buffer_views,
        "buffers": [{"byteLength": offset}],
    }
    js = _pad4(json.dumps(doc, separators=(",", ":")).encode("utf-8"), b" ")
    bin_ = b"".join(chunks)
    bin_ = _pad4(bin_, b"\x00")
    total = 12 + 8 + len(js) + 8 + len(bin_)
    with open(path, "wb") as fh:
        fh.write(struct.pack("<III", 0x46546C67, 2, total))
        fh.write(struct.pack("<II", len(js), 0x4E4F534A))
        fh.write(js)
        fh.write(struct.pack("<II", len(bin_), 0x004E4942))
        fh.write(bin_)


def load_style_config(path: str) -> dict:
    """Read an xray-config/1 file and return the sidecar fields {"styles", "materialAliases"}."""
    with open(path) as fh:
        cfg = json.load(fh)
    if cfg.get("schema") != "xray-config/1":
        raise SystemExit(f"{path}: expected schema 'xray-config/1', got {cfg.get('schema')!r}")
    styles = cfg.get("classStyles") or {}
    if not isinstance(styles, dict):
        raise SystemExit(f"{path}: classStyles must be an object")
    out = {"styles": styles}
    if cfg.get("materialAliases"):
        out["materialAliases"] = cfg["materialAliases"]
    return out


def write_model(out_base: str, items: list[dict], storeys: list[dict], relations: dict,
                source: dict, extra: dict | None = None) -> dict:
    """items: per element dict with keys
        globalId, expressId, ifcClass, name, storey (id|None), material, color(4),
        verts (IFC frame, metres), faces, normals (IFC frame), file
    The element id is the list index. Writes <out_base>.glb and <out_base>.json.
    `extra` holds additional top-level sidecar fields (e.g. load_style_config output).
    Returns the sidecar dict.
    """
    allv = np.concatenate([it["verts"] for it in items]) if items else np.zeros((1, 3))
    lo, hi = allv.min(0), allv.max(0)
    centre = (lo + hi) / 2.0
    shift = [round(float(c), 6) for c in centre]
    c = np.asarray(shift)

    def to_glb(a: np.ndarray, translate: bool) -> np.ndarray:
        a = np.asarray(a, np.float64)
        if translate:
            a = a - c
        return np.stack([a[:, 0], a[:, 2], -a[:, 1]], axis=1)  # -90 deg about X

    meshes, elements = [], []
    for i, it in enumerate(items):
        v = to_glb(it["verts"], True)
        n = to_glb(it["normals"], False)
        meshes.append({"name": it["globalId"], "extras": {"id": i, "ifcClass": it["ifcClass"]},
                       "verts": v, "normals": n, "faces": it["faces"]})
        b = np.concatenate([v.min(0), v.max(0)])
        elements.append({
            "id": i,
            "globalId": it["globalId"],
            "expressId": it.get("expressId"),
            "ifcClass": it["ifcClass"],
            "name": it.get("name") or "",
            "storey": it.get("storey"),
            "material": it.get("material") or "",
            "color": [round(float(x), 4) for x in it["color"]],
            "bounds": [round(float(x), 5) for x in b],
            "file": it.get("file"),
        })
        if it.get("props"):
            elements[-1]["props"] = it["props"]
    write_glb(out_base + ".glb", meshes)
    if relations.get("openings"):
        # opening bounds arrive in the IFC frame (min xyz, max xyz); same shift and Y-up rotation as the elements
        op = []
        for o in relations["openings"]:
            b = np.asarray(o["bounds"], np.float64)
            corners = np.array([[x, y, z] for x in (b[0], b[3]) for y in (b[1], b[4]) for z in (b[2], b[5])])
            g = to_glb(corners, True)
            op.append({"expressId": o["expressId"], "host": o["host"],
                       "bounds": [round(float(x), 5) for x in np.concatenate([g.min(0), g.max(0)])]})
        relations = {**relations, "openings": op}
    side = {
        "schema": SCHEMA,
        "source": source,
        "units": "m",
        "originShift": shift,
        "storeys": storeys,
        "elements": elements,
        "relations": relations,
    }
    if extra:
        side.update(extra)
    with open(out_base + ".json", "w") as fh:
        json.dump(side, fh, separators=(",", ":"))
    return side
