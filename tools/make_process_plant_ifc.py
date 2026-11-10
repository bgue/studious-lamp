#!/usr/bin/env python3
"""Synthetic IFC4 process unit for the X-ray viewer (sample model `process-plant`).

Usage: python3 tools/make_process_plant_ifc.py -o models/Process-Plant.ifc [--seed 1]

A small pump and heat-exchanger skid area with a two-tier steel pipe rack (about 60 m long, 6 m bays, levels +5.0 and
+8.0), a single-level equipment platform (+3.5) with stair and railings, and a small control/MCC building. Metres, Z up.
Four disciplines: civil (site, paving, pad and pier footings, roads, drain trench), structural (rack columns, beams,
struts, bracing, platform), architectural (control building: walls with openings, doors, windows, floor, roof, spaces)
and MEPI (equipment, process and utility piping by service with fittings, valves, instruments, cable tray, luminaires,
switchboards, motors). Every element has a placement relative to its storey, an IfcExtrudedAreaSolid body (rectangle
or circle profile), a surface style per class or service, a property set and containment in a storey. Pipes, fittings
and valves are assigned to one IfcDistributionSystem per service.

Deterministic: GlobalIds come from the seeded generator and the header time stamp is fixed, so the same seed gives the
same file. The output is a demo model, not a design; line routes are approximate and some elements touch.

IFC4 has no PAVEMENT class, so paving is IfcSlab (BASESLAB). IFC4 pipe fittings have BEND, CONNECTOR, JUNCTION (tee) and
TRANSITION (reducer), and valves have no GATE or GLOBE: gate valves are ISOLATING and globe control valves REGULATING.
"""
from __future__ import annotations

import argparse
import math
import random
import re
import sys
from collections import Counter

import ifcopenshell
import ifcopenshell.guid

SPOOL = 2.0          # pipe spool length between flanged joints (m)
BAY = 6.0            # pipe-rack bay (m)
COL_X = [i * BAY for i in range(11)]          # column lines, 0 .. 60 m
ROW_Y = (17.0, 23.0)                          # rack column rows
TILE = 6.0           # paving tile (m)

GRADE, PLAT, T1, T2 = "Grade +0.0", "Platform +3.5", "Rack tier 1 +5.0", "Rack tier 2 +8.0"
STOREYS = {GRADE: 0.0, PLAT: 3.5, T1: 5.0, T2: 8.0}
RADIUS = {50: 0.04, 80: 0.05, 150: 0.09, 250: 0.14}   # outside radius by nominal diameter (mm)
INSULATION = {"Process - Crude feed": "Mineral wool 50 mm", "Process - Pump discharge": "Mineral wool 50 mm",
              "Process - Exchanger outlet": "Mineral wool 50 mm", "Process - Product": "Mineral wool 50 mm",
              "Cooling water supply": "None", "Cooling water return": "None", "Steam": "Mineral wool 75 mm",
              "Condensate": "Mineral wool 25 mm", "Flare": "None"}
SERVICE_RGB = {
    "Process - Crude feed": (0.95, 0.80, 0.15), "Process - Pump discharge": (0.95, 0.80, 0.15),
    "Process - Exchanger outlet": (0.95, 0.80, 0.15), "Process - Product": (0.95, 0.80, 0.15),
    "Cooling water supply": (0.20, 0.70, 0.35), "Cooling water return": (0.10, 0.52, 0.30),
    "Steam": (0.85, 0.15, 0.15), "Condensate": (0.95, 0.55, 0.55), "Flare": (0.35, 0.35, 0.35),
}
SERVICE_SYSTEM = {  # IfcDistributionSystemEnum value per service
    "Process - Crude feed": "USERDEFINED", "Process - Pump discharge": "USERDEFINED",
    "Process - Exchanger outlet": "USERDEFINED", "Process - Product": "USERDEFINED",
    "Cooling water supply": "CONDENSERWATER", "Cooling water return": "CONDENSERWATER",
    "Steam": "HEATING", "Condensate": "USERDEFINED", "Flare": "USERDEFINED",
}
SENSOR = {  # ISA kind -> (IfcSensorTypeEnum, measurand text)
    "PT": ("PRESSURESENSOR", "Pressure transmitter"), "PG": ("PRESSURESENSOR", "Pressure gauge"),
    "TT": ("TEMPERATURESENSOR", "Temperature transmitter"), "FT": ("FLOWSENSOR", "Flow transmitter"),
    "LT": ("LEVELSENSOR", "Level transmitter"),
}

# Rack lines: tier, y (m), DN, service, line number, material. Tier 1 on the +5.0 beams, tier 2 on the +8.0 beams.
RACK_LINES = [
    ("T1", 18.0, 250, "Cooling water supply", "250-CW-1101-A1A", "Carbon steel"),
    ("T1", 18.6, 250, "Cooling water return", "250-CW-1102-A1A", "Carbon steel"),
    ("T1", 19.2, 150, "Cooling water supply", "150-CW-1103-A1A", "Carbon steel"),
    ("T1", 19.8, 150, "Cooling water return", "150-CW-1104-A1A", "Carbon steel"),
    ("T1", 20.4, 150, "Process - Crude feed", "150-PR-1105-A1A", "Carbon steel"),
    ("T1", 21.0, 80, "Condensate", "80-CD-1106-A1A", "Stainless steel"),
    ("T2", 18.0, 150, "Steam", "150-ST-1201-A1A", "Carbon steel"),
    ("T2", 18.6, 80, "Steam", "80-ST-1202-A1A", "Carbon steel"),
    ("T2", 19.2, 250, "Flare", "250-FL-1301-A1A", "Carbon steel"),
    ("T2", 19.8, 150, "Flare", "150-FL-1302-A1A", "Carbon steel"),
]

# Equipment process lines at grade (z 1.6). Each: name, service, DN, line, material, polyline, valves, instruments.
# valves: (fraction along the line, IfcValveTypeEnum, tag). instruments: (ISA kind, fraction, tag).
PROCESS_LINES = [
    dict(service="Process - Crude feed", dn=150, line="150-PR-1001-A1A", mat="Carbon steel", storey=GRADE,
         pts=[(14.0, 29.2, 1.6), (14.0, 13.0, 1.6), (4.5, 13.0, 1.6), (4.5, 3.5, 1.6), (5.5, 3.5, 1.6)],
         valves=[(0.30, "ISOLATING", "XV-1001")], instr=[("PT", 0.60, "PT-1001")]),
    dict(service="Process - Crude feed", dn=150, line="150-PR-1002-A1A", mat="Carbon steel", storey=GRADE,
         pts=[(4.5, 8.5, 1.6), (5.5, 8.5, 1.6)], valves=[], instr=[]),
    dict(service="Process - Crude feed", dn=150, line="150-PR-1003-A1A", mat="Carbon steel", storey=GRADE,
         pts=[(14.0, 13.0, 1.6), (45.5, 13.0, 1.6), (45.5, 8.5, 1.6)],
         valves=[(0.50, "ISOLATING", "XV-1003")], instr=[("FT", 0.80, "FT-1003")]),
    dict(service="Process - Crude feed", dn=150, line="150-PR-1004-A1A", mat="Carbon steel", storey=GRADE,
         pts=[(45.5, 8.5, 1.6), (45.5, 3.5, 1.6), (46.5, 3.5, 1.6)], valves=[], instr=[]),
    dict(service="Process - Pump discharge", dn=80, line="080-PR-1005-A1A", mat="Stainless steel", storey=GRADE,
         pts=[(6.0, 2.6, 1.6), (17.0, 2.6, 1.6), (17.0, 9.0, 1.6), (21.5, 9.0, 1.6)],
         valves=[(0.10, "CHECK", "CV-1005"), (0.55, "ISOLATING", "XV-1006"), (0.75, "REGULATING", "FV-2001")],
         instr=[("PT", 0.40, "PT-1002")]),
    dict(service="Process - Pump discharge", dn=80, line="080-PR-1007-A1A", mat="Stainless steel", storey=GRADE,
         pts=[(6.0, 9.4, 1.6), (17.0, 9.4, 1.6), (17.0, 9.0, 1.6)], valves=[(0.30, "CHECK", "CV-1007")], instr=[]),
    dict(service="Process - Exchanger outlet", dn=80, line="080-PR-1008-A1A", mat="Carbon steel", storey=GRADE,
         pts=[(26.5, 9.0, 1.6), (31.5, 9.0, 1.6)], valves=[(0.50, "REGULATING", "GV-1008")],
         instr=[("TT", 0.50, "TT-2001")]),
    dict(service="Process - Product", dn=80, line="080-PR-1009-A1A", mat="Carbon steel", storey=GRADE,
         pts=[(36.5, 9.0, 1.6), (37.5, 9.0, 1.6), (37.5, 30.0, 1.6), (26.8, 30.0, 1.6)],
         valves=[(0.50, "ISOLATING", "XV-1010")], instr=[("FT", 0.70, "FT-1004")]),
    dict(service="Process - Pump discharge", dn=80, line="080-PR-1011-A1A", mat="Stainless steel", storey=GRADE,
         pts=[(46.0, 2.6, 1.6), (55.0, 2.6, 1.6), (55.0, 11.0, 1.6)], valves=[(0.50, "CHECK", "CV-1011")],
         instr=[("PG", 0.50, "PG-1011")]),
    dict(service="Process - Pump discharge", dn=80, line="080-PR-1012-A1A", mat="Stainless steel", storey=GRADE,
         pts=[(46.0, 9.4, 1.6), (55.0, 9.4, 1.6), (55.0, 11.0, 1.6)], valves=[(0.50, "CHECK", "CV-1012")], instr=[]),
]
# Tees (junctions) and reducers (transitions) on the process lines: (point, DN, service, line, IfcPipeFitting type)
PROCESS_FITTINGS = [
    ((14.0, 13.0, 1.6), 150, "Process - Crude feed", "150-PR-1001-A1A", "JUNCTION", "Tee"),
    ((4.5, 8.5, 1.6), 150, "Process - Crude feed", "150-PR-1001-A1A", "JUNCTION", "Tee"),
    ((45.5, 8.5, 1.6), 150, "Process - Crude feed", "150-PR-1003-A1A", "JUNCTION", "Tee"),
    ((17.0, 9.0, 1.6), 80, "Process - Pump discharge", "080-PR-1005-A1A", "JUNCTION", "Tee"),
    ((46.0, 2.6, 1.6), 80, "Process - Pump discharge", "080-PR-1011-A1A", "TRANSITION", "Reducer DN80 to DN50"),
    ((26.5, 9.0, 1.6), 80, "Process - Exchanger outlet", "080-PR-1008-A1A", "TRANSITION", "Reducer DN80 to DN50"),
]

# Equipment: (tag, x, y) pumps (IfcPump ENDSUCTION, horizontal along x, motor on the outboard end)
PUMPS = [("P-101A", 6.0, 3.5), ("P-101B", 6.0, 8.5), ("P-102A", 46.0, 3.5), ("P-102B", 46.0, 8.5)]
EXCHANGERS = [("E-201", 24.0, 9.0), ("E-202", 34.0, 9.0)]   # shell and tube, horizontal, axis along x
VESSELS = [("V-301", 14.0, 30.0), ("V-302", 26.0, 30.0)]    # vertical drums

# Architectural building: walls by key, endpoints (x, y); openings: (wall, t along wall, width, sill, height, kind)
BLD = (-22.0, -10.0, 0.0, 8.0)     # x0, x1, y0, y1
WALLS = {
    "S": ((-22.0, 0.0), (-10.0, 0.0)), "N": ((-10.0, 8.0), (-22.0, 8.0)),
    "W": ((-22.0, 8.0), (-22.0, 0.0)), "E": ((-10.0, 0.0), (-10.0, 8.0)), "I": ((-16.0, 0.0), (-16.0, 8.0)),
}
OPENINGS = [
    ("S", 0.25, 1.0, 0.0, 2.1, "door"), ("N", 0.30, 1.6, 1.0, 1.2, "window"), ("N", 0.70, 1.6, 1.0, 1.2, "window"),
    ("W", 0.50, 1.6, 1.0, 1.2, "window"), ("E", 0.50, 1.0, 0.0, 2.1, "door"), ("I", 0.20, 0.9, 0.0, 2.1, "door"),
]

STYLE = {
    "civil": ("Civil - concrete", (0.66, 0.66, 0.66)),
    "trench": ("Civil - drain trench", (0.50, 0.50, 0.50)),
    "road": ("Civil - road", (0.40, 0.40, 0.42)),
    "steel": ("Structural - steel", (0.42, 0.50, 0.60)),
    "grating": ("Structural - grating", (0.30, 0.36, 0.44)),
    "rail": ("Structural - railing", (0.55, 0.62, 0.72)),
    "wall": ("Architecture - wall", (0.90, 0.84, 0.70)),
    "roof": ("Architecture - roof slab", (0.84, 0.76, 0.62)),
    "door": ("Architecture - door", (0.55, 0.38, 0.22)),
    "window": ("Architecture - window", (0.62, 0.82, 0.95)),
    "pump": ("MEPI - pump", (0.10, 0.40, 0.85)),
    "motor": ("MEPI - motor", (0.85, 0.40, 0.05)),
    "hx": ("MEPI - heat exchanger", (0.30, 0.20, 0.70)),
    "vessel": ("MEPI - vessel", (0.10, 0.60, 0.65)),
    "board": ("MEPI - switchboard", (0.80, 0.35, 0.05)),
    "tray": ("Electrical - cable tray", (0.95, 0.60, 0.20)),
    "light": ("Electrical - luminaire", (1.00, 0.85, 0.40)),
    "sensor": ("Instrumentation - sensor", (0.60, 0.30, 0.80)),
    "space": ("Architecture - space", (0.95, 0.95, 0.80)),
}


# ---------------------------------------------------------------- vector helpers

def vadd(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def vsub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def vscale(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def vlen(a):
    return math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2])


def vunit(a):
    n = vlen(a)
    return (a[0] / n, a[1] / n, a[2] / n)


def perp(z):
    """A unit X axis perpendicular to z: horizontal for a horizontal z, world X for a vertical z."""
    if abs(z[2]) > 0.9999:
        return (1.0, 0.0, 0.0)
    return vunit((-z[1], z[0], 0.0))


def mid(a, b):
    return vscale(vadd(a, b), 0.5)


def polyline_point(pts, frac):
    """Point and unit direction at a fraction of the polyline length."""
    seg = [vlen(vsub(pts[i + 1], pts[i])) for i in range(len(pts) - 1)]
    target = frac * sum(seg)
    for i, length in enumerate(seg):
        if target <= length or i == len(seg) - 1:
            t = min(1.0, target / length) if length else 0.0
            p = vadd(pts[i], vscale(vsub(pts[i + 1], pts[i]), t))
            return p, vunit(vsub(pts[i + 1], pts[i]))
        target -= length
    raise ValueError("empty polyline")


# ---------------------------------------------------------------- builder

class Plant:
    def __init__(self, seed: int):
        self.rnd = random.Random(seed)
        self.f = f = ifcopenshell.file(schema="IFC4")
        self.owner = f.createIfcOwnerHistory(
            f.createIfcPersonAndOrganization(f.createIfcPerson(None, "Synthetic", "Generator"),
                                             f.createIfcOrganization(None, "xray-ref", None)),
            f.createIfcApplication(f.createIfcOrganization(None, "xray-ref", None), "1", "make_process_plant_ifc",
                                   "mpp"),
            None, "ADDED", None, None, None, 0)
        unit = f.createIfcUnitAssignment([
            f.createIfcSIUnit(None, "LENGTHUNIT", None, "METRE"),
            f.createIfcSIUnit(None, "AREAUNIT", None, "SQUARE_METRE"),
            f.createIfcSIUnit(None, "VOLUMEUNIT", None, "CUBIC_METRE"),
        ])
        wcs = f.createIfcAxis2Placement3D(f.createIfcCartesianPoint((0.0, 0.0, 0.0)), None, None)
        ctx = f.createIfcGeometricRepresentationContext(None, "Model", 3, 1e-5, wcs, None)
        self.body = f.createIfcGeometricRepresentationSubContext(
            "Body", "Model", None, None, None, None, ctx, None, "MODEL_VIEW", None)
        self.origin = f.createIfcAxis2Placement3D(f.createIfcCartesianPoint((0.0, 0.0, 0.0)), None, None)
        self.project = f.createIfcProject(self.guid(), self.owner, "Process Plant demo", None, None, None, None,
                                          [ctx], unit)
        self.styles, self.rect_c, self.circ_c = {}, {}, {}
        self.contained = {name: [] for name in STOREYS}
        self.aggregated = {name: [] for name in STOREYS}
        self.systems = {}          # service name -> (IfcDistributionSystemEnum, [elements])
        self.counts = Counter()
        self.storey_pl = {}
        self.storey = {}
        self.wall_el, self.wall_pl = {}, {}

    # ------------------------------------------------------------ basics
    def guid(self) -> str:
        return ifcopenshell.guid.compress("%032x" % self.rnd.getrandbits(128))

    def dir(self, v):
        return self.f.createIfcDirection(tuple(float(c) for c in v))

    def place(self, storey: str, p, z=(0.0, 0.0, 1.0), x=None):
        """Local placement in a storey frame; p is a global point."""
        a = self.f.createIfcAxis2Placement3D(
            self.f.createIfcCartesianPoint((float(p[0]), float(p[1]), float(p[2]) - STOREYS[storey])),
            self.dir(vunit(z)), self.dir(vunit(x if x is not None else perp(z))))
        return self.f.createIfcLocalPlacement(self.storey_pl[storey], a)

    def place_rel(self, rel, p, z, x):
        """Local placement relative to another placement (wall-local frames for openings, doors, windows)."""
        a = self.f.createIfcAxis2Placement3D(self.f.createIfcCartesianPoint(tuple(float(c) for c in p)),
                                             self.dir(vunit(z)), self.dir(vunit(x)))
        return self.f.createIfcLocalPlacement(rel, a)

    def style(self, key, transparency=0.0):
        name, rgb = STYLE[key] if key in STYLE else key
        if name not in self.styles:
            col = self.f.createIfcColourRgb(None, *rgb)
            rend = self.f.createIfcSurfaceStyleRendering(col, transparency, None, None, None, None, None, None, "FLAT")
            self.styles[name] = self.f.createIfcSurfaceStyle(name, "BOTH", [rend])
        return self.styles[name]

    def rect(self, w, d):
        k = (round(w, 4), round(d, 4))
        if k not in self.rect_c:
            self.rect_c[k] = self.f.createIfcRectangleProfileDef("AREA", None, None, k[0], k[1])
        return self.rect_c[k]

    def circ(self, r):
        k = round(r, 4)
        if k not in self.circ_c:
            self.circ_c[k] = self.f.createIfcCircleProfileDef("AREA", None, None, k)
        return self.circ_c[k]

    def solid(self, profile, depth, style_key, transparency=0.0):
        f = self.f
        sol = f.createIfcExtrudedAreaSolid(profile, self.origin, self.dir((0.0, 0.0, 1.0)), float(depth))
        f.createIfcStyledItem(sol, [self.style(style_key, transparency)], None)
        rep = f.createIfcShapeRepresentation(self.body, "Body", "SweptSolid", [sol])
        return f.createIfcProductDefinitionShape(None, None, [rep])

    def pset(self, el, name, props):
        f = self.f
        vals = []
        for k, v in props:
            if isinstance(v, bool):
                nv = f.createIfcBoolean(v)
            elif isinstance(v, (int, float)):
                nv = f.createIfcReal(float(v))
            else:
                nv = f.createIfcLabel(str(v))
            vals.append(f.createIfcPropertySingleValue(k, None, nv, None))
        ps = f.createIfcPropertySet(self.guid(), self.owner, name, None, vals)
        f.createIfcRelDefinesByProperties(self.guid(), self.owner, None, None, [el], ps)

    def elem(self, storey, cls, name, tag, obj_type, profile, depth, style, anchor=None, z=(0.0, 0.0, 1.0),
             x=None, predef=None, pset=None, props=(), service=None, pl=None, transparency=0.0):
        """One product: body extruded from the anchor along z (profile centred on the anchor)."""
        if pl is None:
            pl = self.place(storey, anchor, z, x)
        kw = dict(GlobalId=self.guid(), OwnerHistory=self.owner, Name=name, ObjectType=obj_type,
                  ObjectPlacement=pl, Representation=self.solid(profile, depth, style, transparency))
        if tag is not None:
            kw["Tag"] = tag
        if predef is not None:
            kw["PredefinedType"] = predef
        el = self.f.create_entity(cls, **kw)
        if pset:
            self.pset(el, pset, list(props))
        self.counts[cls] += 1
        if cls != "IfcSpace":
            self.contained[storey].append(el)
        if service:
            self.systems.setdefault(service, (SERVICE_SYSTEM[service], []))[1].append(el)
        return el

    def group(self, service_or_name, system_enum, els):
        sysobj = self.f.createIfcDistributionSystem(self.guid(), self.owner, service_or_name, None, None, None,
                                                    system_enum)
        self.f.createIfcRelAssignsToGroup(self.guid(), self.owner, None, None, els, None, sysobj)

    def assign(self, els, name, system_enum):
        self.group(name, system_enum, els)

    # ------------------------------------------------------------ spatial structure
    def spatial(self):
        f = self.f
        site_pl = f.createIfcLocalPlacement(None, self.origin)
        site = f.create_entity("IfcSite", GlobalId=self.guid(), OwnerHistory=self.owner, Name="Site",
                               ObjectPlacement=site_pl, CompositionType="ELEMENT")
        bld_pl = f.createIfcLocalPlacement(site_pl, self.origin)
        building = f.create_entity("IfcBuilding", GlobalId=self.guid(), OwnerHistory=self.owner,
                                   Name="Process Unit 100", ObjectPlacement=bld_pl, CompositionType="ELEMENT")
        f.createIfcRelAggregates(self.guid(), self.owner, None, None, self.project, [site])
        f.createIfcRelAggregates(self.guid(), self.owner, None, None, site, [building])
        self.building = building
        for name, z in STOREYS.items():
            pl = f.createIfcLocalPlacement(bld_pl, f.createIfcAxis2Placement3D(
                f.createIfcCartesianPoint((0.0, 0.0, z)), None, None))
            self.storey_pl[name] = pl
            self.storey[name] = f.create_entity("IfcBuildingStorey", GlobalId=self.guid(), OwnerHistory=self.owner,
                                                Name=name, ObjectPlacement=pl, CompositionType="ELEMENT",
                                                Elevation=float(z))
        f.createIfcRelAggregates(self.guid(), self.owner, None, None, building, list(self.storey.values()))

    # ------------------------------------------------------------ civil
    def civil(self):
        for ri, y in enumerate(range(-12, 36, int(TILE))):
            for ci, x in enumerate(range(-24, 66, int(TILE))):
                self.elem(GRADE, "IfcSlab", f"Paving slab PAV-{ri + 1:02d}-{ci + 1:02d}", f"PAV-{ri + 1:02d}-{ci + 1:02d}",
                          "Paving (concrete)", self.rect(TILE, TILE), 0.3, "civil",
                          anchor=(x + TILE / 2, y + TILE / 2, -0.3), predef="BASESLAB", pset="Pset_SlabCommon",
                          props=[("Reference", "PAV-6"), ("IsExternal", True), ("LoadBearing", True)])
        self.elem(GRADE, "IfcSlab", "Perimeter road south", "ROAD-S", "Road (concrete)", self.rect(90.0, 4.0), 0.4,
                  "road", anchor=(21.0, -16.0, -0.4), predef="BASESLAB", pset="Pset_SlabCommon",
                  props=[("Reference", "RD-1"), ("IsExternal", True), ("LoadBearing", True)])
        self.elem(GRADE, "IfcSlab", "Perimeter road east", "ROAD-E", "Road (concrete)", self.rect(4.0, 52.0), 0.4,
                  "road", anchor=(70.0, 10.0, -0.4), predef="BASESLAB", pset="Pset_SlabCommon",
                  props=[("Reference", "RD-2"), ("IsExternal", True), ("LoadBearing", True)])
        for i in range(10):
            x = i * BAY
            self.elem(GRADE, "IfcBuildingElementProxy", f"Drain trench DT-{i + 1:02d}", f"DT-{i + 1:02d}",
                      "Drain trench (concrete channel)", self.rect(BAY, 0.6), 0.3, "trench",
                      anchor=(x + BAY / 2, -6.0, -0.3), pset="Pset_DrainTrenchCommon",
                      props=[("Reference", "DT"), ("Width", 0.6), ("Depth", 0.3), ("Medium", "Process drain")])

    def footing(self, x, y, w, d, tag):
        self.elem(GRADE, "IfcFooting", f"Footing {tag}", f"F-{tag}", f"Pad footing {w:.1f} x {d:.1f} m",
                  self.rect(w, d), 0.7, "civil", anchor=(x, y, -0.3), predef="PAD_FOOTING",
                  pset="Pset_FootingCommon", props=[("ConcreteGrade", "C32/40"), ("Reference", tag)])

    # ------------------------------------------------------------ structural
    def structural(self):
        for x in COL_X:
            for y in ROW_Y:
                tag = f"RC-{int(x / BAY) + 1:02d}{'A' if y == ROW_Y[0] else 'B'}"
                self.elem(GRADE, "IfcColumn", f"Rack column {tag}", tag, "UC 305x305x97", self.rect(0.305, 0.305),
                          8.0, "steel", anchor=(x, y, 0.0), predef="COLUMN",
                          pset="Pset_ColumnCommon", props=[("Reference", "UC 305x305x97"), ("LoadBearing", True)])
                self.footing(x, y, 0.8, 0.8, tag)
        for tier, z_top, storey in ((1, 5.0, T1), (2, 8.0, T2)):
            zc = z_top - 0.23
            for y in ROW_Y:
                for b in range(10):
                    tag = f"B-T{tier}-{'A' if y == ROW_Y[0] else 'B'}{b + 1:02d}"
                    self.elem(storey, "IfcBeam", f"Tier {tier} beam X {tag}", tag, "UB 457x191x67",
                              self.rect(0.19, 0.46), BAY, "steel", anchor=(b * BAY, y, zc), z=(1.0, 0.0, 0.0),
                              predef="BEAM", pset="Pset_BeamCommon",
                              props=[("Reference", "UB 457x191x67"), ("Span", BAY), ("LoadBearing", True)])
            for x in COL_X:
                tag = f"B-T{tier}-X{int(x / BAY) + 1:02d}"
                self.elem(storey, "IfcBeam", f"Tier {tier} cross beam {tag}", tag, "UB 457x191x67",
                          self.rect(0.19, 0.46), ROW_Y[1] - ROW_Y[0], "steel", anchor=(x, ROW_Y[0], zc),
                          z=(0.0, 1.0, 0.0), predef="BEAM", pset="Pset_BeamCommon",
                          props=[("Reference", "UB 457x191x67"), ("Span", ROW_Y[1] - ROW_Y[0]), ("LoadBearing", True)])
        for b in range(10):
            tag = f"ST-{b + 1:02d}"
            self.elem(GRADE, "IfcBeam", f"Longitudinal strut {tag}", tag, "RHS 200x300", self.rect(0.2, 0.3), BAY,
                      "steel", anchor=(b * BAY, 20.0, 2.5), z=(1.0, 0.0, 0.0), predef="BEAM",
                      pset="Pset_BeamCommon", props=[("Reference", "RHS 200x300"), ("Span", BAY)])
        for y in ROW_Y:
            for b in range(10):
                p0, p1 = (b * BAY, y, 0.3), ((b + 1) * BAY, y, 4.77)
                if b % 2:
                    p0, p1 = (p1[0], y, p0[2]), (p0[0], y, p1[2])
                tag = f"BR-{'A' if y == ROW_Y[0] else 'B'}{b + 1:02d}"
                self.elem(GRADE, "IfcMember", f"Rack bracing {tag}", tag, "CHS 150x150", self.rect(0.15, 0.15),
                          vlen(vsub(p1, p0)), "steel", anchor=p0, z=vsub(p1, p0), predef="BRACE",
                          pset="Pset_MemberCommon", props=[("Reference", "SHS 150x150"), ("LoadBearing", True)])
        self.platform()

    def platform(self):
        px0, px1, py0, py1 = 24.0, 36.0, 24.0, 28.0
        for x in (px0, 30.0, px1):
            for y in (py0, py1):
                tag = f"PC-{int(x)}{int(y)}"
                self.elem(GRADE, "IfcColumn", f"Platform column {tag}", tag, "SHS 300x300", self.rect(0.3, 0.3), 3.2,
                          "steel", anchor=(x, y, 0.0), predef="COLUMN", pset="Pset_ColumnCommon",
                          props=[("Reference", "SHS 300x300"), ("LoadBearing", True)])
                self.footing(x, y, 0.8, 0.8, tag)
        for y in (py0, py1):
            self.elem(PLAT, "IfcBeam", f"Platform beam {y:.0f}", f"PB-{y:.0f}", "UB 305x165x40", self.rect(0.165, 0.305),
                      px1 - px0, "steel", anchor=(px0, y, 3.2), z=(1.0, 0.0, 0.0), predef="BEAM",
                      pset="Pset_BeamCommon", props=[("Reference", "UB 305x165x40"), ("Span", px1 - px0)])
        for x in (px0, 30.0, px1):
            self.elem(PLAT, "IfcBeam", f"Platform cross beam {x:.0f}", f"PX-{x:.0f}", "UB 305x165x40",
                      self.rect(0.165, 0.305), py1 - py0, "steel", anchor=(x, py0, 3.2), z=(0.0, 1.0, 0.0),
                      predef="BEAM", pset="Pset_BeamCommon", props=[("Reference", "UB 305x165x40"), ("Span", py1 - py0)])
        for i in range(6):
            for j in range(2):
                cx, cy = px0 + 1 + 2 * i, py0 + 1 + 2 * j
                tag = f"GP-{i + 1}{j + 1}"
                self.elem(PLAT, "IfcSlab", f"Grating panel {tag}", tag, "Steel grating 2.0 x 2.0", self.rect(2.0, 2.0),
                          0.1, "grating", anchor=(cx, cy, 3.4), predef="FLOOR", pset="Pset_SlabCommon",
                          props=[("Reference", "GRT-25"), ("LoadBearing", True), ("IsExternal", False)])
        rail_h = 1.0
        rails = []
        for i in range(6):
            rails.append(((px0 + 2 * i, py1, 4.0), (1.0, 0.0, 0.0), 2.0))
            rails.append(((px0 + 2 * i, py0, 4.0), (1.0, 0.0, 0.0), 2.0))
        rails.append(((px1, py0, 4.0), (0.0, 1.0, 0.0), 2.0))
        rails.append(((px1, py0 + 2, 4.0), (0.0, 1.0, 0.0), 2.0))
        rails.append(((px0, py0, 4.0), (0.0, 1.0, 0.0), 1.5))
        rails.append(((px0, py0 + 2.5, 4.0), (0.0, 1.0, 0.0), 1.5))
        for k, (p, d, length) in enumerate(rails):
            tag = f"RL-{k + 1:02d}"
            self.elem(PLAT, "IfcRailing", f"Platform railing {tag}", tag, "Handrail 1.0 m", self.rect(0.05, rail_h),
                      length, "rail", anchor=p, z=d, predef=None, pset="Pset_RailingCommon",
                      props=[("Height", rail_h), ("Reference", "RL-1")])
        # stair from grade (x 20) up to the platform edge at x 24
        p0, p1 = (20.0, 26.0, 0.0), (px0, 26.0, 3.5)
        self.elem(PLAT, "IfcStair", "Platform stair ST-01", "ST-01", "Straight stair 1.0 m", self.rect(1.0, 0.3),
                  vlen(vsub(p1, p0)), "steel", anchor=p0, z=vsub(p1, p0), predef="STRAIGHT_RUN_STAIR",
                  pset="Pset_StairCommon", props=[("NumberOfRiser", 12), ("RiserHeight", 0.29), ("Width", 1.0)])

    # ------------------------------------------------------------ architectural
    def control_building(self):
        H, T = 4.0, 0.3
        wall_el = {}
        for key, (q0, q1) in WALLS.items():
            p0, p1 = (q0[0], q0[1], 0.0), (q1[0], q1[1], 0.0)
            L = vlen(vsub(p1, p0))
            x = vunit(vsub(p1, p0))
            el = self.elem(GRADE, "IfcWall", f"Control building wall {key}", f"W-{key}", "Masonry 300 mm",
                           self.rect(L, T), H, "wall", anchor=mid(p0, p1), z=(0.0, 0.0, 1.0), x=x,
                           predef="STANDARD", pset="Pset_WallCommon",
                           props=[("IsExternal", key != "I"), ("LoadBearing", True), ("FireRating", "EI30")])
            wall_el[key] = (el, L, x)
            self.wall_pl[key] = el.ObjectPlacement
        openings = []
        for n, (key, t, w, sill, h, kind) in enumerate(OPENINGS):
            el, L, x = wall_el[key]
            ox = (t - 0.5) * L
            wpl = self.wall_pl[key]
            frame_z, frame_x = (0.0, 1.0, 0.0), (1.0, 0.0, 0.0)
            ocenter = sill + h / 2
            opl = self.place_rel(wpl, (ox, -0.6, ocenter), frame_z, frame_x)
            op = self.f.create_entity("IfcOpeningElement", GlobalId=self.guid(), OwnerHistory=self.owner,
                                      Name=f"Opening OP-{n + 1:02d}", ObjectType="Opening",
                                      ObjectPlacement=opl, Representation=self.solid(self.rect(w, h), 1.2, "wall"),
                                      PredefinedType="OPENING")
            self.f.createIfcRelVoidsElement(self.guid(), self.owner, None, None, el, op)
            self.contained[GRADE].append(op)
            self.counts["IfcOpeningElement"] += 1
            openings.append((op, kind, w, h, sill, ox))
            if kind == "door":
                tag, cls, style, pt, pred = f"D-{n + 1:02d}", "IfcDoor", "door", "DOOR", "DOOR"
                body_pl = self.place_rel(wpl, (ox, -0.05, ocenter), frame_z, frame_x)
                door = self.elem(GRADE, cls, f"Door {tag}", tag, "Single leaf 0.9 m", self.rect(w, h), 0.1, style,
                                 pl=body_pl, predef=pred, pset="Pset_DoorCommon",
                                 props=[("FireRating", "FD30"), ("IsExternal", key in ("S", "E")), ("Reference", "D-90")])
                self.f.createIfcRelFillsElement(self.guid(), self.owner, None, None, op, door)
            else:
                tag = f"WIN-{n + 1:02d}"
                body_pl = self.place_rel(wpl, (ox, -0.05, ocenter), frame_z, frame_x)
                win = self.elem(GRADE, "IfcWindow", f"Window {tag}", tag, "Double glazing 1.6 x 1.2", self.rect(w, h),
                                0.1, "window", pl=body_pl, predef="WINDOW", pset="Pset_WindowCommon",
                                props=[("GlazingAreaFraction", 0.8), ("IsExternal", key != "I"), ("Reference", "W-16")])
                self.f.createIfcRelFillsElement(self.guid(), self.owner, None, None, op, win)
        # floor, roof, spaces
        cx, cy = -16.0, 4.0
        self.elem(GRADE, "IfcSlab", "Control building floor", "FL-CB", "Floor slab 200 mm", self.rect(12.0, 8.0), 0.2,
                  "civil", anchor=(cx, cy, 0.0), predef="FLOOR", pset="Pset_SlabCommon",
                  props=[("IsExternal", False), ("LoadBearing", True)])
        self.elem(GRADE, "IfcSlab", "Control building roof", "RF-CB", "Roof slab 250 mm", self.rect(12.0, 8.0), 0.25,
                  "roof", anchor=(cx, cy, H), predef="ROOF", pset="Pset_SlabCommon",
                  props=[("IsExternal", True), ("LoadBearing", True)])
        spaces = []
        for name, sx, sy, tag in (("Control room", -19.0, 4.0, "SP-CR"), ("MCC room", -13.0, 4.0, "SP-MCC")):
            sp = self.elem(GRADE, "IfcSpace", name, None, name, self.rect(5.7, 7.7), H - 0.3, "space",
                           anchor=(sx, sy, 0.0), predef="SPACE", pset="Pset_SpaceCommon",
                           props=[("Reference", tag), ("OccupancyType", "Office" if "Control" in name else "Electrical")],
                           transparency=0.85)
            spaces.append(sp)
        self.f.createIfcRelAggregates(self.guid(), self.owner, None, None, self.storey[GRADE], spaces)
        self.aggregated[GRADE] += spaces

    def electrical_rooms(self):
        self.elem(GRADE, "IfcElectricDistributionBoard", "MCC panel MCC-101 (415 V)", "MCC-101",
                  "Motor control centre 415 V", self.rect(0.8, 0.4), 2.0, "board", anchor=(-13.0, 4.0, 0.0),
                  predef="MOTORCONTROLCENTRE", pset="Pset_ElectricDistributionBoardTypeCommon",
                  props=[("Voltage", 415.0), ("RatedCurrent", 400.0), ("System", "Electrical - MCC")],
                  service=None)
        self.elem(GRADE, "IfcElectricDistributionBoard", "Lighting panel LP-101", "LP-101", "Lighting panel 230 V",
                  self.rect(0.6, 0.3), 1.8, "board", anchor=(-19.2, 6.5, 0.0), predef="DISTRIBUTIONBOARD",
                  pset="Pset_ElectricDistributionBoardTypeCommon",
                  props=[("Voltage", 230.0), ("RatedCurrent", 63.0), ("System", "Lighting")])

    # ------------------------------------------------------------ MEPI
    def equipment(self):
        for tag, x, y in PUMPS:
            self.footing(x, y, 1.6, 1.2, tag)
            self.elem(GRADE, "IfcPump", f"Pump {tag}", tag, "End-suction centrifugal pump", self.circ(0.35), 1.0,
                      "pump", anchor=(x - 0.5, y, 0.85), z=(1.0, 0.0, 0.0), predef="ENDSUCTION",
                      pset="Pset_PumpCommon", props=[("Duty kW", 55.0 if tag.endswith("A") else 37.0),
                                                     ("Medium", "Crude / cooling water"), ("Reference", tag)])
            self.elem(GRADE, "IfcElectricMotor", f"Motor M-{tag[2:]}", f"M-{tag[2:]}", "Motor 3-phase 415 V",
                      self.circ(0.3), 0.8, "motor", anchor=(x + 0.5, y, 0.85), z=(1.0, 0.0, 0.0), predef="INDUCTION",
                      pset="Pset_ElectricMotorCommon", props=[("Voltage", 415.0), ("Driver", tag)])
        for tag, x, y in EXCHANGERS:
            self.footing(x, y, 5.0, 1.6, tag)
            self.elem(GRADE, "IfcHeatExchanger", f"Heat exchanger {tag}", tag, "Shell and tube heat exchanger",
                      self.circ(0.5), 4.0, "hx", anchor=(x - 2.0, y, 1.3), z=(1.0, 0.0, 0.0), predef="SHELLANDTUBE",
                      pset="Pset_HeatExchangerCommon", props=[("Duty kW", 1200.0), ("Reference", tag)])
        for tag, x, y in VESSELS:
            self.footing(x, y, 2.4, 2.4, tag)
            self.elem(GRADE, "IfcTank", f"Vessel {tag}", tag, "Vertical drum", self.circ(0.8), 4.0, "vessel",
                      anchor=(x, y, 0.4), z=(0.0, 0.0, 1.0), predef="VESSEL", pset="Pset_TankCommon",
                      props=[("Volume m3", 15.0), ("Reference", tag)])
        for n, (tag, x, y) in enumerate(VESSELS):
            self.elem(GRADE, "IfcSensor", f"Level transmitter LT-{3001 + n} on {tag}", f"LT-{3001 + n}", "LEVELSENSOR",
                      self.circ(0.05), 0.35, "sensor", anchor=(x + 0.8, y, 2.0), z=(1.0, 0.0, 0.0),
                      predef="LEVELSENSOR", pset="Pset_SensorTypeCommon",
                      props=[("Measurand", "Level transmitter"), ("Range", "0-4 m")], service=None)

    def pipe_line(self, service, dn, line, mat, storey, pts, valves=(), instr=()):
        r = RADIUS[dn]
        style_pipe = f"Pipe - {service}"
        style_fit = f"Fitting - {service}"
        SR = (style_pipe, tuple(c for c in SERVICE_RGB[service]))
        FR = (style_fit, tuple(c * 0.8 for c in SERVICE_RGB[service]))
        VR = (f"Valve - {service}", tuple(c * 0.65 for c in SERVICE_RGB[service]))
        ins = INSULATION[service]
        obj = f"Pipe {mat} DN{dn}"
        spools, joints = [], []
        for si in range(len(pts) - 1):
            a, b = pts[si], pts[si + 1]
            L = vlen(vsub(b, a))
            d = vunit(vsub(b, a))
            n = max(1, math.ceil(L / SPOOL - 1e-9))
            step = L / n
            for k in range(n):
                spools.append((vadd(a, vscale(d, k * step)), d, step))
                if k < n - 1:
                    joints.append((vadd(a, vscale(d, (k + 1) * step)), d, "CONNECTOR"))
            if si < len(pts) - 2:
                joints.append((b, d, "BEND"))
        for i, (start, d, L) in enumerate(spools):
            self.elem(storey, "IfcPipeSegment", f"Pipe {line} spool {i + 1:02d}", f"{line}/S{i + 1:02d}", obj,
                      self.circ(r), L, SR, anchor=start, z=d, predef="RIGIDSEGMENT", pset="Pset_PipeSegmentTypeCommon",
                      props=[("NominalDiameter", float(dn)), ("Material", mat), ("Insulation", ins),
                             ("LineNumber", line), ("Service", service)], service=service)
        for j, (p, d, kind) in enumerate(joints):
            if kind == "BEND":
                self.elem(storey, "IfcPipeFitting", f"Elbow {line} E{j + 1:02d}", f"{line}/E{j + 1:02d}", obj,
                          self.circ(r * 1.25), 0.3, FR, anchor=vsub(p, vscale(d, 0.15)), z=d, predef="BEND",
                          pset="Pset_PipeFittingTypeCommon",
                          props=[("NominalDiameter", float(dn)), ("Material", mat), ("LineNumber", line)],
                          service=service)
            else:
                self.elem(storey, "IfcPipeFitting", f"Flange joint {line} J{j + 1:02d}", f"{line}/J{j + 1:02d}", obj,
                          self.circ(r * 1.2), 0.12, FR, anchor=vsub(p, vscale(d, 0.06)), z=d, predef="CONNECTOR",
                          pset="Pset_PipeFittingTypeCommon",
                          props=[("NominalDiameter", float(dn)), ("Material", mat), ("LineNumber", line)],
                          service=service)
        for frac, vtype, tag in valves:
            p, d = polyline_point(pts, frac)
            self.elem(storey, "IfcValve", f"Valve {tag} ({vtype.lower()})", tag, f"{vtype.title()} valve DN{dn}",
                      self.circ(r * 1.6), 0.5, VR, anchor=vsub(p, vscale(d, 0.25)), z=d, predef=vtype,
                      pset="Pset_ValveTypeCommon",
                      props=[("NominalDiameter", float(dn)), ("Material", mat), ("LineNumber", line),
                             ("Service", service)], service=service)
        for kind, frac, tag in instr:
            p, _ = polyline_point(pts, frac)
            cls_pred, measurand = SENSOR[kind]
            self.elem(storey, "IfcSensor", f"{measurand} {tag} on {line}", tag, measurand, self.circ(0.05), 0.35,
                      "sensor", anchor=(p[0], p[1], p[2] + r), z=(0.0, 0.0, 1.0), predef=cls_pred,
                      pset="Pset_SensorTypeCommon",
                      props=[("Measurand", measurand), ("LineNumber", line), ("Service", service)])

    def process_piping(self):
        for ln in PROCESS_LINES:
            self.pipe_line(ln["service"], ln["dn"], ln["line"], ln["mat"], ln["storey"], ln["pts"],
                           ln["valves"], ln["instr"])
        for p, dn, service, line, predef, label in PROCESS_FITTINGS:
            self.elem(GRADE, "IfcPipeFitting", f"{label} {line}", f"{line}/F{int(p[0]):02d}{int(p[1]):02d}",
                      f"{label} DN{dn}", self.circ(RADIUS[dn] * 1.3), 0.25, (f"Fitting - {service}",
                                                                              tuple(c * 0.8 for c in SERVICE_RGB[service])),
                      anchor=vsub(p, (0.0, 0.0, 0.0)), z=(1.0, 0.0, 0.0) if predef == "JUNCTION" else (0.0, 1.0, 0.0),
                      predef=predef, pset="Pset_PipeFittingTypeCommon",
                      props=[("NominalDiameter", float(dn)), ("Material", "Carbon steel"), ("LineNumber", line)],
                      service=service)

    def rack_piping(self):
        for k, (tier, y, dn, service, line, mat) in enumerate(RACK_LINES):
            zt = (5.0 if tier == "T1" else 8.0) + RADIUS[dn] + 0.005
            storey = T1 if tier == "T1" else T2
            xr = -1.0 if tier == "T1" else -3.0
            pts = [(xr, y, 1.0), (xr, y, zt), (61.0, y, zt)]
            kind = ["PT", "TT", "FT", "PG", "PT", "TT", "PG", "FT", "PT", "TT"][k]
            instr = [(kind, 0.75, f"{kind}-{1101 + k}")]
            valves = [(0.35, self.rnd.choice(["ISOLATING", "REGULATING", "CHECK"]), f"XV-{1110 + k}"),
                      (0.65, self.rnd.choice(["ISOLATING", "ISOLATING", "REGULATING"]), f"XV-{1120 + k}")]
            self.pipe_line(service, dn, line, mat, storey, pts, valves=valves, instr=instr)
        # flare stack from the tier 2 header end to +14 m
        zt = 8.0 + RADIUS[250] + 0.005
        self.pipe_line("Flare", 250, "250-FL-1303-A1A", "Carbon steel", T2, [(61.0, 19.2, zt), (61.0, 19.2, 14.0)],
                       valves=[(0.5, "CHECK", "CV-1303")], instr=[])

    def cable_tray_and_lights(self):
        els = []
        for i in range(30):
            x = i * 2.0
            tag = f"CT-{i + 1:02d}"
            els.append(self.elem(T2, "IfcCableCarrierSegment", f"Cable tray {tag}", tag, "Cable tray 500 x 100",
                                 self.rect(0.5, 0.1), 2.0, "tray", anchor=(x, 22.0, 8.05), z=(1.0, 0.0, 0.0),
                                 predef="CABLETRAYSEGMENT", pset="Pset_CableCarrierSegmentTypeCommon",
                                 props=[("Width", 500.0), ("Height", 100.0), ("Material", "Galvanised steel")]))
        self.assign(els, "Electrical - cable tray", "ELECTRICAL")
        lights = []
        for b in range(10):
            for k, y in enumerate((15.5, 24.5)):
                tag = f"LU-{b + 1:02d}{'A' if k == 0 else 'B'}"
                lights.append(self.elem(T1, "IfcLightFixture", f"Luminaire {tag}", tag, "LED luminaire 60 W",
                                        self.rect(0.6, 0.25), 0.06, "light", anchor=(b * BAY + 3.0, y, 4.25),
                                        z=(0.0, 0.0, 1.0), pset="Pset_LightFixtureTypeCommon",
                                        props=[("Power W", 60.0), ("Lumens", 6500.0)]))
        self.assign(lights, "Lighting", "LIGHTING")

    def route_all(self):
        self.process_piping()
        self.rack_piping()

    def control_instruments(self):
        # equipment-mounted transmitters (levels and temperatures) for the vessels and the exchangers
        self.elem(GRADE, "IfcSensor", "Temperature transmitter TT-2002 on E-202", "TT-2002", "Temperature transmitter",
                  self.circ(0.05), 0.35, "sensor", anchor=(34.0, 9.0, 1.9), z=(0.0, 0.0, 1.0),
                  predef="TEMPERATURESENSOR", pset="Pset_SensorTypeCommon",
                  props=[("Measurand", "Temperature transmitter"), ("Reference", "TT-2002")])

    def extras(self):
        """Kerbs and fence posts along the roads, base plates, pipe-support posts and tray brackets."""
        for i in range(30):
            x = -24.0 + 3.0 * i
            self.elem(GRADE, "IfcBuildingElementProxy", f"Kerb KB-S-{i + 1:02d}", f"KB-S-{i + 1:02d}",
                      "Kerb (concrete, 3 m)", self.rect(3.0, 0.3), 0.15, "civil", anchor=(x + 1.5, -14.0, 0.0),
                      pset="Pset_KerbCommon", props=[("Reference", "KB-1"), ("Length", 3.0)])
        for i in range(18):
            y = -16.0 + 3.0 * i
            self.elem(GRADE, "IfcBuildingElementProxy", f"Kerb KB-E-{i + 1:02d}", f"KB-E-{i + 1:02d}",
                      "Kerb (concrete, 3 m)", self.rect(0.3, 3.0), 0.15, "civil", anchor=(68.0, y + 1.5, 0.0),
                      pset="Pset_KerbCommon", props=[("Reference", "KB-2"), ("Length", 3.0)])
        for i in range(16):
            x = -24.0 + 6.0 * i
            self.elem(GRADE, "IfcBuildingElementProxy", f"Fence post FP-S-{i + 1:02d}", f"FP-S-{i + 1:02d}",
                      "Fence post 2.4 m", self.rect(0.1, 0.1), 2.4, "civil", anchor=(x, -18.5, 0.0),
                      pset="Pset_FenceCommon", props=[("Height", 2.4), ("Reference", "FN-1")])
        for i in range(10):
            y = -18.0 + 6.0 * i
            self.elem(GRADE, "IfcBuildingElementProxy", f"Fence post FP-E-{i + 1:02d}", f"FP-E-{i + 1:02d}",
                      "Fence post 2.4 m", self.rect(0.1, 0.1), 2.4, "civil", anchor=(74.0, y, 0.0),
                      pset="Pset_FenceCommon", props=[("Height", 2.4), ("Reference", "FN-2")])
        for x in COL_X:
            for y in ROW_Y:
                tag = f"BP-{int(x / BAY) + 1:02d}{'A' if y == ROW_Y[0] else 'B'}"
                self.elem(GRADE, "IfcPlate", f"Column base plate {tag}", tag, "Base plate 450 x 450 x 20",
                          self.rect(0.45, 0.45), 0.02, "steel", anchor=(x, y, 0.4), pset="Pset_PlateCommon",
                          props=[("Reference", "BP-450"), ("Thickness", 0.02)])
        for tier, z_top, storey in ((1, 5.0, T1), (2, 8.0, T2)):
            for b in range(10):
                for k, dx in enumerate((1.0, 3.0, 5.0)):
                    tag = f"PS-T{tier}-{b + 1:02d}{'ABC'[k]}"
                    self.elem(storey, "IfcMember", f"Pipe support post {tag}", tag, "Pipe support post 0.5 m",
                              self.rect(0.1, 0.1), 0.5, "steel", anchor=(b * BAY + dx, 17.5, z_top),
                              predef="POST", pset="Pset_MemberCommon",
                              props=[("Reference", "PS-POST"), ("LoadBearing", True)])
        for b in range(10):
            for k, dx in enumerate((1.0, 5.0)):
                tag = f"TB-{b + 1:02d}{'AB'[k]}"
                self.elem(T2, "IfcMember", f"Cable tray bracket {tag}", tag, "Tray bracket 1.0 m",
                          self.rect(0.05, 0.1), 1.0, "steel", anchor=(b * BAY + dx, 21.5, 7.9),
                          z=(0.0, 1.0, 0.0), predef="MEMBER", pset="Pset_MemberCommon",
                          props=[("Reference", "TB-50"), ("LoadBearing", False)])

    def write(self, out: str):
        self.spatial_containment()
        self.f.write(out)
        with open(out, "r", encoding="utf-8") as fh:
            text = fh.read()
        text = re.sub(r"(FILE_NAME\('[^']*',')[^']*(')", r"\g<1>1970-01-01T00:00:00\2", text, count=1)
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(text)

    def spatial_containment(self):
        f = self.f
        for name, st in self.storey.items():
            if self.aggregated[name]:
                f.createIfcRelAggregates(self.guid(), self.owner, None, None, st, self.aggregated[name])
            els = self.contained[name]
            if els:
                f.createIfcRelContainedInSpatialStructure(self.guid(), self.owner, None, None, els, st)
        for service, (system, els) in self.systems.items():
            if els:
                self.group(service, system, els)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()
    p = Plant(args.seed)
    p.spatial()
    p.civil()
    p.structural()
    p.control_building()
    p.electrical_rooms()
    p.equipment()
    p.route_all()
    p.cable_tray_and_lights()
    p.control_instruments()
    p.extras()
    p.write(args.out)
    total = sum(p.counts.values())
    print(f"{args.out}: {total} elements", file=sys.stderr)
    for cls, n in sorted(p.counts.items(), key=lambda kv: -kv[1]):
        print(f"  {cls}: {n}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
