#!/usr/bin/env python3
"""IFC -> glb + model.json converter for the X-ray viewer (xray-model/1).

Usage:  python3 tools/ifc2glb.py a.ifc [b.ifc ...] -o web/public/models/name

Requires ifcopenshell (tested 0.9.0) and numpy. Works for IFC2x3 and IFC4.
"""
from __future__ import annotations

import argparse
import collections
import multiprocessing
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import glb_common  # noqa: E402

import ifcopenshell  # noqa: E402
import ifcopenshell.geom  # noqa: E402
import ifcopenshell.util.element as ue  # noqa: E402
import ifcopenshell.util.unit as uu  # noqa: E402

SKIP_CLASSES = ("IfcOpeningElement", "IfcSpace", "IfcSite", "IfcBuilding", "IfcBuildingStorey",
                "IfcAnnotation", "IfcSpatialZone", "IfcExternalSpatialElement", "IfcGrid",
                "IfcVirtualElement")

CONCRETE = [0.62, 0.62, 0.62, 1.0]
CLASS_COLORS = {
    "IfcWall": CONCRETE, "IfcWallStandardCase": CONCRETE, "IfcSlab": CONCRETE, "IfcBeam": CONCRETE,
    "IfcColumn": CONCRETE, "IfcFooting": CONCRETE,
    "IfcDuctSegment": [0.3, 0.6, 0.9, 1.0], "IfcDuctFitting": [0.3, 0.6, 0.9, 1.0],
    "IfcPipeSegment": [0.2, 0.7, 0.4, 1.0], "IfcPipeFitting": [0.2, 0.7, 0.4, 1.0],
    "IfcCableCarrierSegment": [0.9, 0.6, 0.2, 1.0], "IfcCableCarrierFitting": [0.9, 0.6, 0.2, 1.0],
}
DEFAULT_COLOR = [0.7, 0.7, 0.7, 1.0]


def safe_is_a(ent, cls: str) -> bool:
    try:
        return bool(ent.is_a(cls))
    except Exception:
        return False


def attr(ent, name, default=None):
    try:
        return getattr(ent, name)
    except Exception:
        return default


# ---------------------------------------------------------------- geometry

def smooth_mesh(v: np.ndarray, f: np.ndarray, crease_deg: float = 30.0):
    """Vertex normals averaged only over faces within crease_deg; vertices split where they differ.

    Returns (verts, faces, normals). Degenerate triangles are dropped.
    """
    v = np.asarray(v, np.float64)
    f = np.asarray(f, np.int64)
    c = np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]])
    a2 = np.linalg.norm(c, axis=1)
    keep = a2 > 1e-14
    f, c, a2 = f[keep], c[keep], a2[keep]
    if len(f) == 0:
        return v[:0], f.astype(np.uint32), v[:0]
    un = c / a2[:, None]
    nf = len(f)
    cv = f.reshape(-1)
    cf = np.repeat(np.arange(nf), 3)
    order = np.argsort(cv, kind="stable")
    sv, sf = cv[order], cf[order]
    _, start, counts = np.unique(sv, return_index=True, return_counts=True)
    gs = np.repeat(start, counts)
    gc = np.repeat(counts, counts)
    tot = int(gc.sum())
    left = np.repeat(np.arange(len(sv)), gc)
    within = np.arange(tot) - np.repeat(np.cumsum(gc) - gc, gc)
    right = gs[left] + within
    fl, fr = sf[left], sf[right]
    ok = (un[fl] * un[fr]).sum(1) >= np.cos(np.radians(crease_deg))
    acc = np.zeros((len(sv), 3))
    for k in range(3):
        acc[:, k] = np.bincount(left[ok], weights=c[fr[ok], k], minlength=len(sv))
    ln = np.linalg.norm(acc, axis=1)
    ln[ln == 0] = 1.0
    acc /= ln[:, None]
    corner_n = np.empty_like(acc)
    corner_n[order] = acc
    key = np.concatenate([cv[:, None].astype(np.float64), np.round(corner_n, 4)], axis=1)
    uk, inv = np.unique(key, axis=0, return_inverse=True)
    nv = v[uk[:, 0].astype(np.int64)]
    nn = uk[:, 1:4]
    nl = np.linalg.norm(nn, axis=1)
    nl[nl == 0] = 1.0
    return nv, inv.reshape(-1, 3).astype(np.uint32), nn / nl[:, None]


def style_color(geo, product_class: str):
    """RGBA from the shape's dominant (by face count) surface style; class default as fallback."""
    default = list(CLASS_COLORS.get(product_class, DEFAULT_COLOR))
    try:
        mats = list(geo.materials)
        if not mats:
            return default
        ids = np.asarray(list(geo.material_ids), dtype=np.int64)
        ids = ids[ids >= 0]
        best = int(np.bincount(ids).argmax()) if len(ids) else 0
        m = mats[min(best, len(mats) - 1)]
        col = m.get_color() if hasattr(m, "get_color") else m.diffuse
        if col is None:
            return default
        rgb = [float(col.r()), float(col.g()), float(col.b())]
        tr = float(getattr(m, "transparency", 0.0) or 0.0)
        if tr != tr:  # NaN
            tr = 0.0
        return [rgb[0], rgb[1], rgb[2], max(0.0, min(1.0, 1.0 - tr))]
    except Exception:
        return default


def make_settings():
    s = ifcopenshell.geom.settings()
    try:
        s.set("use-world-coords", True)
        s.set("weld-vertices", True)
    except Exception:  # pre-0.8 API
        s.set(s.USE_WORLD_COORDS, True)
        s.set(s.WELD_VERTICES, True)
    return s  # opening subtraction stays at its default (applied)


MARKER_NAMES = ("origin", "geo-reference")


def is_marker(p) -> bool:
    """buildingSMART Simple-Scene files carry 'origin' / 'geo-reference' proxy cubes in every file."""
    return safe_is_a(p, "IfcBuildingElementProxy") and str(attr(p, "Name") or "").strip().lower() in MARKER_NAMES


def exportable(ifc, keep_markers: bool = False) -> list:
    out = []
    for p in ifc.by_type("IfcProduct"):
        if not attr(p, "Representation"):
            continue
        if any(safe_is_a(p, c) for c in SKIP_CLASSES):
            continue
        if not keep_markers and is_marker(p):
            continue
        out.append(p)
    return out


# ---------------------------------------------------------------- IFC metadata

def storey_of(elem):
    """Walk up containers / aggregates until an IfcBuildingStorey is found."""
    seen = set()
    e = elem
    while e is not None and e.id() not in seen:
        seen.add(e.id())
        c = ue.get_container(e)
        if c is not None:
            if safe_is_a(c, "IfcBuildingStorey"):
                return c
            if safe_is_a(c, "IfcSpace"):  # element inside a space: climb via the space's container
                e = c
                continue
            # contained directly in site/building: try aggregate parent anyway
        e = ue.get_aggregate(e)
    return None


def storey_elevation(st, unit_scale: float) -> float:
    el = attr(st, "Elevation")
    if el is not None:
        return float(el) * unit_scale
    try:
        import ifcopenshell.util.placement as up
        return float(up.get_local_placement(st.ObjectPlacement)[2][3]) * unit_scale
    except Exception:
        return 0.0


def material_name(elem) -> str:
    try:
        m = ue.get_material(elem)
        if m is None:
            return ""
        n = attr(m, "Name")
        if n:
            return str(n)
        if safe_is_a(m, "IfcMaterialLayerSet") or safe_is_a(m, "IfcMaterialLayerSetUsage"):
            ls = m if safe_is_a(m, "IfcMaterialLayerSet") else m.ForLayerSet
            if attr(ls, "LayerSetName"):
                return str(ls.LayerSetName)
        names = [x.Name for x in ue.get_materials(elem) if attr(x, "Name")]
        return str(names[0]) if names else ""
    except Exception:
        return ""


def port_owner(port):
    try:
        for r in attr(port, "Nests", ()) or ():
            return r.RelatingObject
        for r in attr(port, "ContainedIn", ()) or ():  # IfcRelConnectsPortToElement (IFC2x3 / IFC4)
            return r.RelatedElement
    except Exception:
        pass
    return None


def expand_to_exported(obj, eid_by_ent: dict, depth: int = 0) -> list:
    """Element ids for obj: itself if exported, else exported descendants via IfcRelAggregates/Nests."""
    if obj.id() in eid_by_ent:
        return [eid_by_ent[obj.id()]]
    if depth > 6:
        return []
    out = []
    for rel in attr(obj, "IsDecomposedBy", ()) or ():
        for ch in rel.RelatedObjects:
            out.extend(expand_to_exported(ch, eid_by_ent, depth + 1))
    for rel in attr(obj, "IsNestedBy", ()) or ():
        for ch in rel.RelatedObjects:
            out.extend(expand_to_exported(ch, eid_by_ent, depth + 1))
    return out


# ---------------------------------------------------------------- main conversion

def convert(files: list[str], out_base: str, keep_markers: bool = False, config: str | None = None) -> dict:
    items: list[dict] = []
    storey_keys: dict[tuple, dict] = {}       # (name, elev) -> {name, elevation}
    per_file_storey: list[dict[int, tuple]] = []
    voids, fills, hosts, ports = [], [], [], []
    port_seen, host_seen = set(), set()
    systems: dict[str, list[int]] = collections.OrderedDict()
    schemas = []
    n_missing = 0
    used_gids: set[str] = set()
    settings = make_settings()
    nthreads = max(1, multiprocessing.cpu_count())

    pending_storey_ref: list[tuple[int, tuple | None]] = []  # (item index, storey key)
    n_fallback = 0
    seen_geom: dict[str, tuple] = {}  # globalId -> (class, rounded bounds), to drop cross-file duplicates

    for path in files:
        ifc = ifcopenshell.open(path)
        schemas.append(ifc.schema)
        scale = uu.calculate_unit_scale(ifc)
        fname = os.path.basename(path)
        prods = exportable(ifc, keep_markers)
        by_id = {p.id(): p for p in prods}
        st_map: dict[int, tuple] = {}
        for st in ifc.by_type("IfcBuildingStorey"):
            key = (str(st.Name or ""), round(storey_elevation(st, scale), 4))
            storey_keys.setdefault(key, {"name": key[0], "elevation": key[1]})
            st_map[st.id()] = key
        file_storeys = sorted(set(st_map.values()), key=lambda k: (k[1], k[0]))
        per_file_storey.append(st_map)

        # geometry (threaded iterator; result order is not guaranteed, so sort by express id)
        results = {}
        if prods:
            it = ifcopenshell.geom.iterator(settings, ifc, nthreads, include=prods)
            if it.initialize():
                while True:
                    sh = it.get()
                    pid = sh.id if isinstance(sh.id, int) else sh.product.id()
                    results[pid] = sh
                    if not it.next():
                        break
        eid_by_ent: dict[int, int] = {}
        for pid in sorted(by_id):
            p = by_id[pid]
            sh = results.get(pid)
            if sh is None:
                n_missing += 1
                print(f"  warn: no geometry for {p.is_a()} #{pid} {attr(p, 'Name')}", file=sys.stderr)
                continue
            geo = sh.geometry
            v = np.asarray(geo.verts, np.float64).reshape(-1, 3)
            f = np.asarray(geo.faces, np.int64).reshape(-1, 3)
            if len(v) == 0 or len(f) == 0:
                n_missing += 1
                print(f"  warn: empty mesh for {p.is_a()} #{pid}", file=sys.stderr)
                continue
            v, f, n = smooth_mesh(v, f)
            if len(f) == 0:
                n_missing += 1
                print(f"  warn: degenerate mesh for {p.is_a()} #{pid}", file=sys.stderr)
                continue
            gid = str(p.GlobalId)
            sig = (p.is_a(), tuple(np.round(np.concatenate([v.min(0), v.max(0)]), 3)))
            if gid in used_gids:
                if seen_geom.get(gid) == sig:
                    print(f"  note: {p.is_a()} {gid} in {fname} duplicates an earlier file's element; skipped",
                          file=sys.stderr)
                    continue
                gid = f"{gid}~{len(items)}"
                print(f"  warn: duplicate GlobalId with different geometry, renamed {gid}", file=sys.stderr)
            used_gids.add(gid)
            seen_geom[gid] = sig
            st = storey_of(p)
            skey = st_map.get(st.id()) if st is not None else None
            if skey is None and file_storeys:
                # not contained in a storey (e.g. roof parts contained in the site): nearest storey at or
                # below the element's lowest point, else the lowest storey
                zmin = float(v[:, 2].min())
                below = [k for k in file_storeys if k[1] <= zmin + 1e-6]
                skey = below[-1] if below else file_storeys[0]
                n_fallback += 1
            eid = len(items)
            eid_by_ent[pid] = eid
            items.append({
                "globalId": gid, "expressId": pid, "ifcClass": p.is_a(), "name": attr(p, "Name") or "",
                "storey": None, "material": material_name(p),
                "color": style_color(geo, p.is_a()),
                "verts": v, "faces": f, "normals": n, "file": fname,
            })
            pending_storey_ref.append((eid, skey))

        # relations (per file; express ids only meaningful inside one file)
        open_host: dict[int, int] = {}
        for r in ifc.by_type("IfcRelVoidsElement"):
            h = eid_by_ent.get(r.RelatingBuildingElement.id())
            if h is None:
                continue
            oid = r.RelatedOpeningElement.id()
            open_host[oid] = h
            voids.append([h, oid])
        for r in ifc.by_type("IfcRelFillsElement"):
            oid = r.RelatingOpeningElement.id()
            fe = eid_by_ent.get(r.RelatedBuildingElement.id())
            if fe is None:
                continue
            fills.append([oid, fe])
            h = open_host.get(oid)
            if h is not None and (fe, h) not in host_seen and fe != h:
                host_seen.add((fe, h))
                hosts.append([fe, h])
        for r in ifc.by_type("IfcRelConnectsPorts"):
            a = port_owner(r.RelatingPort)
            b = port_owner(r.RelatedPort)
            if a is None or b is None:
                continue
            ea, eb = eid_by_ent.get(a.id()), eid_by_ent.get(b.id())
            if ea is None or eb is None or ea == eb:
                continue
            k = (min(ea, eb), max(ea, eb))
            if k not in port_seen:
                port_seen.add(k)
                ports.append(list(k))
        for r in ifc.by_type("IfcRelAssignsToGroup"):
            g = r.RelatingGroup
            if not (safe_is_a(g, "IfcSystem") or safe_is_a(g, "IfcDistributionSystem")):
                continue
            ids = []
            for o in r.RelatedObjects:
                ids.extend(expand_to_exported(o, eid_by_ent))
            if ids:
                lst = systems.setdefault(str(g.Name or f"System #{g.id()}"), [])
                lst.extend(i for i in ids if i not in lst)

    if not items:
        raise SystemExit("no exportable geometry found")

    # storeys: merged by name+elevation, sorted by elevation
    skeys = sorted(storey_keys, key=lambda k: (k[1], k[0]))
    storeys = [{"id": i, "name": k[0], "elevation": k[1]} for i, k in enumerate(skeys)]
    sid = {k: i for i, k in enumerate(skeys)}
    for eid, skey in pending_storey_ref:
        items[eid]["storey"] = sid.get(skey) if skey is not None else None

    schema = schemas[0] if len(set(schemas)) == 1 else "+".join(sorted(set(schemas)))
    source = {"files": [os.path.basename(p) for p in files], "converter": "ifc2glb.py", "ifcSchema": schema}
    relations = {"voids": voids, "fills": fills, "hosts": hosts, "ports": ports,
                 "systems": [{"name": n, "elements": e} for n, e in systems.items()]}
    os.makedirs(os.path.dirname(os.path.abspath(out_base)), exist_ok=True)
    extra = glb_common.load_style_config(config) if config else None
    side = glb_common.write_model(out_base, items, storeys, relations, source, extra)
    side["_missing"] = n_missing
    side["_fallback"] = n_fallback
    return side


def summary(side: dict, out_base: str) -> None:
    els = side["elements"]
    print(f"wrote {out_base}.glb ({os.path.getsize(out_base + '.glb')} bytes), "
          f"{out_base}.json ({os.path.getsize(out_base + '.json')} bytes)")
    print(f"schema {side['source']['ifcSchema']}, files {side['source']['files']}")
    if "styles" in side:
        print("class styles baked in:", sorted(side["styles"]), " aliases:", sorted(side.get("materialAliases", {})))
    print(f"elements: {len(els)}  (skipped without usable geometry: {side.get('_missing', 0)})")
    for c, n in sorted(collections.Counter(e["ifcClass"] for e in els).items()):
        print(f"  {c:32s} {n}")
    print("storeys:", [(s["id"], s["name"], s["elevation"]) for s in side["storeys"]],
          " elements without storey:", sum(1 for e in els if e["storey"] is None),
          " storey assigned by elevation fallback:", side.get("_fallback", 0))
    b = np.array([e["bounds"] for e in els])
    print("bounds (glb frame): min", np.round(b[:, :3].min(0), 3).tolist(), "max", np.round(b[:, 3:].max(0), 3).tolist())
    print("originShift (IFC frame, m):", side["originShift"])
    r = side["relations"]
    print("relations:", {k: len(v) for k, v in r.items()},
          " systems:", [(s["name"], len(s["elements"])) for s in r["systems"]])


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="IFC -> glb + xray-model/1 json")
    ap.add_argument("ifc", nargs="+", help="input .ifc file(s)")
    ap.add_argument("-o", "--out", required=True, help="output base path (writes .glb and .json)")
    ap.add_argument("--keep-markers", action="store_true",
                    help="keep the 'origin'/'geo-reference' IfcBuildingElementProxy marker cubes (dropped by default)")
    ap.add_argument("--config", metavar="XRAY_CONFIG_JSON",
                    help="xray-config/1 file (web/public/xray.config.json); its classStyles and materialAliases "
                         "are baked into model.json as 'styles' and 'materialAliases'")
    a = ap.parse_args(argv)
    side = convert(a.ifc, a.out, a.keep_markers, a.config)
    summary(side, a.out)


if __name__ == "__main__":
    main()
