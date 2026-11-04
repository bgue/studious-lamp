#!/usr/bin/env python3
"""Realistic synthetic IFC4 building of N elements, for load benchmarks (web/bench/bench-large-ifc.mjs).

Usage: python3 tools/make_big_ifc.py -n 20000 -o /tmp/big-20k.ifc [--seed 1]

Layout (IFC frame, Z up, metres): storeys of 3.5 m, each with a grid of 6 m bays. Per bay, in this order, until the
storey holds its share of N: a slab tile, a column, a beam along x, a beam along y, a wall, a rectangular duct segment,
a pipe segment, a second duct, a second pipe and a second wall. That gives roughly 10 % slabs, 20 % walls, 10 %
columns, 20 % beams, 20 % ducts and 20 % pipes. Every element has a placement relative to its storey, an
IfcExtrudedAreaSolid body (rectangle or circle profile), a surface style per class, a property set (Pset_*Common
style, 3 to 4 single values, plus an IfcQuantity-free name/tag/description), and containment in its storey. Ducts and
pipes of a storey are assigned to one IfcDistributionSystem each. The storey count grows with N (about 2500 elements
per storey) so the model keeps a plausible shape. Exactly N elements are written (the count excludes the project,
site, building, storeys and styles).
"""
from __future__ import annotations

import argparse
import math
import random
import sys

import ifcopenshell
import ifcopenshell.guid

BAY = 6.0
STOREY_H = 3.5


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-n", "--elements", type=int, required=True)
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--per-storey", type=int, default=2500)
    args = ap.parse_args()
    rnd = random.Random(args.seed)
    n_total = args.elements
    n_storeys = max(3, round(n_total / args.per_storey))

    f = ifcopenshell.file(schema="IFC4")
    guid = ifcopenshell.guid.new
    owner = f.createIfcOwnerHistory(
        f.createIfcPersonAndOrganization(f.createIfcPerson(None, "Bench", "Gen"), f.createIfcOrganization(None, "xray-ref", None)),
        f.createIfcApplication(f.createIfcOrganization(None, "xray-ref", None), "1", "make_big_ifc", "mbi"),
        None, "ADDED", None, None, None, 0,
    )
    unit = f.createIfcUnitAssignment([
        f.createIfcSIUnit(None, "LENGTHUNIT", None, "METRE"),
        f.createIfcSIUnit(None, "AREAUNIT", None, "SQUARE_METRE"),
        f.createIfcSIUnit(None, "VOLUMEUNIT", None, "CUBIC_METRE"),
    ])
    wcs = f.createIfcAxis2Placement3D(f.createIfcCartesianPoint((0.0, 0.0, 0.0)), None, None)
    ctx = f.createIfcGeometricRepresentationContext(None, "Model", 3, 1e-5, wcs, None)
    body = f.createIfcGeometricRepresentationSubContext("Body", "Model", None, None, None, None, ctx, None, "MODEL_VIEW", None)
    project = f.createIfcProject(guid(), owner, "Bench project", None, None, None, None, [ctx], unit)

    def placement(rel, xyz=(0.0, 0.0, 0.0), z_dir=None, x_dir=None):
        a = f.createIfcAxis2Placement3D(
            f.createIfcCartesianPoint(tuple(float(v) for v in xyz)),
            f.createIfcDirection(z_dir) if z_dir else None,
            f.createIfcDirection(x_dir) if x_dir else None,
        )
        return f.createIfcLocalPlacement(rel, a)

    site_pl = placement(None)
    site = f.createIfcSite(guid(), owner, "Site", None, None, site_pl, None, None, "ELEMENT", None, None, None, None, None)
    bld_pl = placement(site_pl)
    building = f.createIfcBuilding(guid(), owner, "Building", None, None, bld_pl, None, None, "ELEMENT", None, None, None)
    f.createIfcRelAggregates(guid(), owner, None, None, project, [site])
    f.createIfcRelAggregates(guid(), owner, None, None, site, [building])

    styles = {}

    def style(name, rgb):
        if name not in styles:
            col = f.createIfcColourRgb(None, *rgb)
            rend = f.createIfcSurfaceStyleRendering(col, 0.0, None, None, None, None, None, None, "FLAT")
            ss = f.createIfcSurfaceStyle(name, "BOTH", [rend])
            styles[name] = ss
        return styles[name]

    palette = {
        "IfcSlab": (0.66, 0.66, 0.66), "IfcWall": (0.85, 0.82, 0.76), "IfcColumn": (0.62, 0.62, 0.62),
        "IfcBeam": (0.58, 0.58, 0.60), "IfcDuctSegment": (0.30, 0.60, 0.90), "IfcPipeSegment": (0.20, 0.70, 0.40),
    }

    rect_cache, circ_cache, dir_cache = {}, {}, {}

    def direction(v):
        if v not in dir_cache:
            dir_cache[v] = f.createIfcDirection(v)
        return dir_cache[v]

    def rect(w, d):
        k = (round(w, 3), round(d, 3))
        if k not in rect_cache:
            rect_cache[k] = f.createIfcRectangleProfileDef("AREA", None, None, k[0], k[1])
        return rect_cache[k]

    def circ(r):
        k = round(r, 3)
        if k not in circ_cache:
            circ_cache[k] = f.createIfcCircleProfileDef("AREA", None, None, k)
        return circ_cache[k]

    origin_axis = f.createIfcAxis2Placement3D(f.createIfcCartesianPoint((0.0, 0.0, 0.0)), None, None)

    def solid(cls, profile, depth, up=(0.0, 0.0, 1.0)):
        sol = f.createIfcExtrudedAreaSolid(profile, origin_axis, direction(up), float(depth))
        f.createIfcStyledItem(sol, [style(cls, palette[cls])], None)
        rep = f.createIfcShapeRepresentation(body, "Body", "SweptSolid", [sol])
        return f.createIfcProductDefinitionShape(None, None, [rep])

    def pset(el, setname, props):
        vals = []
        for k, v in props:
            if isinstance(v, bool):
                nv = f.createIfcBoolean(v)
            elif isinstance(v, (int, float)):
                nv = f.createIfcReal(float(v))
            else:
                nv = f.createIfcLabel(str(v))
            vals.append(f.createIfcPropertySingleValue(k, None, nv, None))
        ps = f.createIfcPropertySet(guid(), owner, setname, None, vals)
        f.createIfcRelDefinesByProperties(guid(), owner, None, None, [el], ps)

    storeys, contained, systems = [], [], []
    made = 0
    per = [n_total // n_storeys + (1 if i < n_total % n_storeys else 0) for i in range(n_storeys)]
    for si in range(n_storeys):
        z0 = si * STOREY_H
        st_pl = placement(bld_pl, (0.0, 0.0, z0))
        st = f.createIfcBuildingStorey(guid(), owner, f"Level {si + 1:02d}", None, None, st_pl, None, None, "ELEMENT", z0)
        storeys.append(st)
        want = per[si]
        # bay grid sized so that ~want/10 bays fill the storey
        bays = max(1, math.ceil(want / 10))
        nx = max(1, round(math.sqrt(bays * 1.5)))
        ny = max(1, math.ceil(bays / nx))
        els, duct_run, pipe_run = [], [], []

        def add(cls, ifc_create, name, pl, shape, pset_name, props):
            nonlocal made
            el = ifc_create(guid(), owner, name, None, None, pl, shape, f"T{made}")
            pset(el, pset_name, props)
            els.append(el)
            made += 1
            return el

        count = 0
        for b in range(nx * ny):
            bx, by = (b % nx) * BAY, (b // nx) * BAY
            jitter = rnd.random()
            for kind in ("slab", "column", "beam_x", "beam_y", "wall", "duct", "pipe", "duct2", "pipe2", "wall2"):
                if count >= want:
                    break
                count += 1
                if kind == "slab":
                    add("IfcSlab", f.createIfcSlab, f"Slab {si}-{b}", placement(st_pl, (bx + BAY / 2, by + BAY / 2, -0.25)),
                        solid("IfcSlab", rect(BAY, BAY), 0.25), "Pset_SlabCommon",
                        [("Reference", f"SL-{b % 12}"), ("IsExternal", si == n_storeys - 1), ("LoadBearing", True), ("FireRating", "REI60")])
                elif kind == "column":
                    add("IfcColumn", f.createIfcColumn, f"Column {si}-{b}", placement(st_pl, (bx, by, 0.0)),
                        solid("IfcColumn", rect(0.4, 0.4), STOREY_H - 0.25), "Pset_ColumnCommon",
                        [("Reference", f"C-{b % 8}"), ("LoadBearing", True), ("FireRating", "R90")])
                elif kind == "beam_x":
                    add("IfcBeam", f.createIfcBeam, f"Beam X {si}-{b}",
                        placement(st_pl, (bx, by, STOREY_H - 0.25 - 0.5), z_dir=(1.0, 0.0, 0.0), x_dir=(0.0, 0.0, -1.0)),
                        solid("IfcBeam", rect(0.5, 0.3), BAY), "Pset_BeamCommon", [("Reference", f"B-{b % 6}"), ("Span", BAY), ("LoadBearing", True)])
                elif kind == "beam_y":
                    add("IfcBeam", f.createIfcBeam, f"Beam Y {si}-{b}",
                        placement(st_pl, (bx, by, STOREY_H - 0.25 - 0.5), z_dir=(0.0, 1.0, 0.0), x_dir=(0.0, 0.0, -1.0)),
                        solid("IfcBeam", rect(0.5, 0.3), BAY), "Pset_BeamCommon", [("Reference", f"B-{b % 6}"), ("Span", BAY), ("LoadBearing", True)])
                elif kind in ("wall", "wall2"):
                    horizontal = kind == "wall"
                    add("IfcWall", f.createIfcWall, f"Wall {si}-{b}{'' if horizontal else 'b'}",
                        placement(st_pl, (bx, by + (0 if horizontal else 0.0), 0.0),
                                  z_dir=(0.0, 0.0, 1.0), x_dir=(1.0, 0.0, 0.0) if horizontal else (0.0, 1.0, 0.0)),
                        solid("IfcWall", rect(BAY, 0.2), STOREY_H - 0.25), "Pset_WallCommon",
                        [("Reference", f"W-{b % 10}"), ("IsExternal", jitter < 0.2), ("LoadBearing", jitter < 0.5), ("FireRating", "EI30")])
                elif kind in ("duct", "duct2"):
                    off = 1.5 if kind == "duct" else 4.0
                    w, h = 0.6 + 0.2 * rnd.random(), 0.3
                    d = add("IfcDuctSegment", f.createIfcDuctSegment, f"Duct {si}-{b}-{kind[-1]}",
                            placement(st_pl, (bx, by + off, STOREY_H - 0.25 - 0.5 - 0.45), z_dir=(1.0, 0.0, 0.0), x_dir=(0.0, 0.0, -1.0)),
                            solid("IfcDuctSegment", rect(h, w), BAY * 0.9), "Pset_DuctSegmentTypeCommon",
                            [("Reference", f"D-{b % 5}"), ("Width", w), ("Height", h), ("Roughness", 0.15)])
                    duct_run.append(d)
                else:
                    off = 2.5 if kind == "pipe" else 5.0
                    r = 0.05 + 0.03 * rnd.random()
                    p = add("IfcPipeSegment", f.createIfcPipeSegment, f"Pipe {si}-{b}-{kind[-1]}",
                            placement(st_pl, (bx + off, by, STOREY_H - 0.25 - 0.5 - 0.2), z_dir=(0.0, 1.0, 0.0), x_dir=(0.0, 0.0, -1.0)),
                            solid("IfcPipeSegment", circ(r), BAY * 0.9), "Pset_PipeSegmentTypeCommon",
                            [("Reference", f"P-{b % 5}"), ("NominalDiameter", 2 * r), ("PressureRating", 1600.0)])
                    pipe_run.append(p)
            if count >= want:
                break
        contained.append((st, els))
        if duct_run:
            systems.append((f"Supply air {si + 1:02d}", duct_run))
        if pipe_run:
            systems.append((f"Chilled water {si + 1:02d}", pipe_run))

    f.createIfcRelAggregates(guid(), owner, None, None, building, storeys)
    for st, els in contained:
        if els:
            f.createIfcRelContainedInSpatialStructure(guid(), owner, None, None, els, st)
    for name, els in systems:
        sysobj = f.createIfcDistributionSystem(guid(), owner, name, None, None, None, "AIRCONDITIONING" if name.startswith("Supply") else "CHILLEDWATER")
        f.createIfcRelAssignsToGroup(guid(), owner, None, None, els, None, sysobj)

    f.write(args.out)
    print(f"{args.out}: {made} elements, {n_storeys} storeys, {len(f.by_type('IfcRepresentationItem'))} items", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
