#!/usr/bin/env python3
"""Synthetic IFC4 process unit for the X-ray viewer (sample model `process-plant`).

Usage: python3 tools/make_process_plant_ifc.py -o models/Process-Plant.ifc [--seed 1]
Writes the IFC and, next to it, the ground-truth classification file (models/Process-Plant.truth.json).

A small feed / pump / heat-exchanger process unit around a two-tier steel pipe rack (60 m long plus a 5 m battery-limit
bay, 6 m bays, levels +5.0 and +8.0), a single-level platform (+3.5) with stair and railings, and a control/MCC building
(24 x 11 x 5.5 m). Metres, Z up. Four disciplines: civil (site, paving, foundations, roads, drain trench), structural
(rack columns, beams, struts, bracing, platform), architectural (control building: walls with openings, doors,
windows, floor, roof, spaces) and MEPI (equipment, process and utility piping by service with fittings, valves,
instruments, supports, cable tray, luminaires, switchboards, motors). Every element has a placement relative to its
storey, an IfcExtrudedAreaSolid body (rectangle or circle profile), a surface style per class or service, a property
set and containment in a storey. Pipes, fittings and valves are assigned to one IfcDistributionSystem per service.

Process (all equipment south of the rack, y < 17):
  crude feed -> V-301 feed drum -> P-101A/B -> E-201 (steam heater, process in the channel) -> V-302 separator ->
  P-102A/B -> E-202 (cooler, process on the shell, cooling water in the channel) -> product to the battery limit.
  Steam to E-201, condensate back; cooling water to E-202 and back; V-302 vapour to the flare header.

Battery limit: the west end of the rack (frame BL at x = -5). Every line that leaves the unit ends there on an
isolation valve and a spectacle blind at x = -5.4, on the marked battery-limit board between the two BL columns.
Flare: the flare header goes to the battery limit (off-site flare), so the unit has no stack of its own.

Deterministic: GlobalIds come from the seeded generator and the header time stamp is fixed, so the same seed gives the
same file. The model is a demo, not a design: sizes follow typical proportions, but there is no hydraulics, stress or
code work behind it. The generator checks its own result and exits with an error when a pipe end dangles, two bodies
overlap by more than the modelling tolerance, or a run is unsupported over more than 6 m.

IFC4 has no PAVEMENT class, so paving is IfcSlab (BASESLAB). IFC4 pipe fittings have BEND, CONNECTOR, JUNCTION (tee) and
TRANSITION (reducer), and valves have no GATE or GLOBE: gate valves are ISOLATING and globe control valves REGULATING.
A spectacle blind is an IfcPipeFitting USERDEFINED.

Ground truth: the discipline, sub-discipline and division of every element are passed at its creation (design
intent, from the descriptions in web/public/classification/default-schema.json). They are never derived from the
classifier rules and never written into the IFC.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import re
import sys
from collections import Counter

import numpy as np

import ifcopenshell
import ifcopenshell.guid

SPOOL = 2.0          # pipe spool length between flanged joints (m)
BAY = 6.0            # pipe-rack bay (m)
BL_X = -5.0          # battery-limit frame (column line)
COL_X = [BL_X] + [i * BAY for i in range(11)]  # column lines: BL frame, then 0 .. 60 m
ROW_Y = (17.0, 23.0)                          # rack column rows
TILE = 6.0           # paving tile (m)
BL_END = -5.4        # x of the spectacle blinds (battery-limit line)
ZF = 0.4             # top of equipment foundations
TOL_CLASH = 0.03     # a body may sink this far into another (flange on a beam, valve on a pipe) before it counts as a clash
TOL_END = 0.02       # a pipe end must lie within this of the thing it connects to
OFFSETS = [0.0] + [sg * 0.35 * i for i in range(1, 13) for sg in (1, -1)]   # support search around the wanted spot
SPAN_MAX = 6.0       # largest unsupported length of a line (m)

GRADE, PLAT, T1, T2 = "Grade +0.0", "Platform +3.5", "Rack tier 1 +5.0", "Rack tier 2 +8.0"
STOREYS = {GRADE: 0.0, PLAT: 3.5, T1: 5.0, T2: 8.0}
RADIUS = {50: 0.04, 80: 0.05, 100: 0.06, 150: 0.09, 250: 0.14}   # outside radius by nominal diameter (mm)
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
UTILITY = {"Cooling water supply", "Cooling water return", "Steam", "Condensate"}   # PIP/UTL; the rest is PIP/PRC
SENSOR = {  # ISA kind -> (IfcSensorTypeEnum, measurand text)
    "PT": ("PRESSURESENSOR", "Pressure transmitter"), "PG": ("PRESSURESENSOR", "Pressure gauge"),
    "TT": ("TEMPERATURESENSOR", "Temperature transmitter"), "FT": ("FLOWSENSOR", "Flow transmitter"),
    "LT": ("LEVELSENSOR", "Level transmitter"),
}

# ---- equipment layout (all south of the rack). Pumps: shaft along x, motor on the east end, suction on the west end face.
DRUM_R, SKIRT_TOP, SHELL_TOP = 1.2, 2.0, 7.0         # vertical drum: dia 2.4, skirt 0.4..2.0, shell 2.0..7.0 (5.0 tan-tan)
V301, V302 = (12.7, 11.0), (36.7, 11.0)   # drum axes 0.7 m beside a column line, so the rack branches clear the columns
PUMP_R, PUMP_ZS = 0.4, 1.1                           # casing and motor radius, shaft height (0.7 above the foundation)
PUMP_GROUPS = {  # xw = casing west face; ya, yb = shaft lines of A and B; yo = discharge main y; ne = exchanger nozzle x
    "101": dict(xw=17.3, ya=8.0, yb=4.0, drum=V301, xh=15.5, zd=3.2),
    "102": dict(xw=41.3, ya=8.0, yb=4.0, drum=V302, xh=39.5, zd=3.2),
}
HX_R, HX_CH_R, HX_L, HX_ZC = 0.5, 0.55, 5.5, 1.65    # shell dia 1.0, channel dia 1.1, shell 5.5 long, axis height
E201 = dict(tag="E-201", x0=22.0, cy=10.72, saddles=(1.4, 4.6))          # channel on the west end [x0-0.6, x0], shell [x0, x0+5.5]
E202 = dict(tag="E-202", x0=49.0, cy=10.72, saddles=(2.0, 4.8))
CH_DY = 0.28                                         # channel nozzles sit at cy -/+ CH_DY on top of the channel
CH_TOP = HX_ZC + math.sqrt(HX_CH_R ** 2 - CH_DY ** 2)
NOZ_LEN, NOZ_IN = 0.2, 0.05                          # nozzle flange: 0.05 into the body, 0.15 out

# Rack levels for a pipe of nominal size dn (pipe resting on the beam top)


def zt(tier, dn):
    return (5.0 if tier == 1 else 8.0) + RADIUS[dn] + 0.005


# Architectural building: walls by key, endpoints (x, y); openings: (wall, t along wall, width, sill, height, kind)
BLD = (-34.0, -10.0, 5.0, 16.0)     # x0, x1, y0, y1  (24 x 11 m)
BLD_H = 5.5
WALLS = {
    "S": ((-34.0, 5.0), (-10.0, 5.0)), "N": ((-10.0, 16.0), (-34.0, 16.0)),
    "W": ((-34.0, 16.0), (-34.0, 5.0)), "E": ((-10.0, 5.0), (-10.0, 16.0)), "I": ((-22.0, 5.0), (-22.0, 16.0)),
}
OPENINGS = [
    ("S", 0.12, 1.0, 0.0, 2.1, "door"),            # control room door
    ("S", 0.78, 2.0, 0.0, 2.4, "door2"),           # MCC room double door 2.0 x 2.4
    ("S", 0.35, 1.6, 1.0, 1.2, "window"),
    ("N", 0.55, 1.6, 1.0, 1.2, "window"), ("N", 0.72, 1.6, 1.0, 1.2, "window"), ("N", 0.89, 1.6, 1.0, 1.2, "window"),
    ("W", 0.50, 1.6, 1.0, 1.2, "window"),
    ("I", 0.20, 1.0, 0.0, 2.1, "door"),            # control room to MCC room
    ("E", 7.0 / 11.0, 0.9, 4.05, 0.7, "pen"),      # cable tray penetration (MCC room east wall, z 4.4, y 12)
]

STYLE = {
    "civil": ("Civil - concrete", (0.66, 0.66, 0.66)),
    "trench": ("Civil - drain trench", (0.50, 0.50, 0.50)),
    "road": ("Civil - road", (0.40, 0.40, 0.42)),
    "steel": ("Structural - steel", (0.42, 0.50, 0.60)),
    "support": ("Piping - support steel", (0.30, 0.40, 0.30)),
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
    "blind": ("Piping - spectacle blind", (0.15, 0.15, 0.15)),
    "marker": ("Piping - battery limit marker", (1.00, 0.85, 0.00)),
}
SKIP_TRUTH = ("IfcSpace", "IfcOpeningElement")   # products the converter (tools/ifc2glb.py) does not keep


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


def vcross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def perp(z):
    """A unit X axis perpendicular to z: horizontal for a horizontal z, world X for a vertical z."""
    if abs(z[2]) > 0.9999:
        return (1.0, 0.0, 0.0)
    return vunit((-z[1], z[0], 0.0))


def mid(a, b):
    return vscale(vadd(a, b), 0.5)


# ---------------------------------------------------------------- shapes (for the self-checks)

def shape_cyl(p0, a, length, r):
    return dict(t="cyl", p0=np.array(p0, float), a=np.array(a, float), L=float(length), r=float(r))


def shape_box(c, axes, half):
    return dict(t="box", c=np.array(c, float), ax=np.array(axes, float), h=np.array(half, float))


def shape_aabb(s):
    if s["t"] == "cyl":
        p1 = s["p0"] + s["a"] * s["L"]
        ext = s["r"] * np.sqrt(np.maximum(0.0, 1.0 - s["a"] ** 2))
        return np.minimum(s["p0"], p1) - ext, np.maximum(s["p0"], p1) + ext
    ext = np.abs(s["ax"]).T @ s["h"]
    return s["c"] - ext, s["c"] + ext


def dist_point(p, s):
    """Distance from a point to the solid (0 inside)."""
    p = np.asarray(p, float)
    if s["t"] == "cyl":
        d = p - s["p0"]
        ax = float(d @ s["a"])
        rad = float(np.linalg.norm(d - ax * s["a"]))
        return math.hypot(max(-ax, ax - s["L"], 0.0), max(rad - s["r"], 0.0))
    q = np.abs(s["ax"] @ (p - s["c"])) - s["h"]
    return float(np.linalg.norm(np.maximum(q, 0.0)))


def inside(pts, s, shrink):
    if s["t"] == "cyl":
        d = pts - s["p0"]
        ax = d @ s["a"]
        rad = np.linalg.norm(d - np.outer(ax, s["a"]), axis=1)
        return (ax > shrink) & (ax < s["L"] - shrink) & (rad < s["r"] - shrink)
    loc = np.abs((pts - s["c"]) @ s["ax"].T)
    return np.all(loc < s["h"] - shrink, axis=1)


def sample_points(s):
    """Points on and in the solid, spaced about 5 cm along cylinders and 8 cm on boxes."""
    if s["t"] == "cyl":
        n = max(2, int(s["L"] / 0.05) + 1)
        a = s["a"]
        u = np.cross(a, [0.0, 0.0, 1.0]) if abs(a[2]) < 0.99 else np.array([1.0, 0.0, 0.0])
        u = u / np.linalg.norm(u)
        v = np.cross(a, u)
        ring = [(0.0, 0.0)]
        for rr, k in ((s["r"], 16), (s["r"] * 0.5, 8)):
            for i in range(k):
                ang = 2 * math.pi * i / k
                ring.append((rr * math.cos(ang), rr * math.sin(ang)))
        ring = np.array(ring)
        t = np.linspace(0.0, s["L"], n)
        base = s["p0"][None, :] + t[:, None] * a[None, :]
        off = ring[:, 0:1] * u[None, :] + ring[:, 1:2] * v[None, :]
        return (base[:, None, :] + off[None, :, :]).reshape(-1, 3)
    h = s["h"]
    grids = [np.unique(np.concatenate([np.linspace(-h[i], h[i], max(2, int(2 * h[i] / 0.08) + 1)), [0.0]])) for i in range(3)]
    gx, gy, gz = np.meshgrid(*grids, indexing="ij")
    loc = np.stack([gx.ravel(), gy.ravel(), gz.ravel()], axis=1)
    on_face = np.any(np.isclose(np.abs(loc), h[None, :]), axis=1) | np.all(np.isclose(loc, 0.0), axis=1)
    return s["c"] + loc[on_face] @ s["ax"]


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
        self.recs = []             # one record per product, for the checks and the truth file
        self.runs = []             # pipe runs
        self.trays = []            # cable tray runs
        self.nozzles = []
        self.tee_pairs = set()    # pairs of runs that meet at a tee (their pipes overlap there by design)
        self.nsup = Counter()
        self.schema_codes = self.load_schema()

    @staticmethod
    def load_schema():
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, "..", "web", "public", "classification", "default-schema.json"), encoding="utf-8") as fh:
            sch = json.load(fh)
        subs = {d["code"]: {s["code"] for s in d.get("subDisciplines", [])} for d in sch["disciplines"]}
        divs = {d["division"] for d in sch["masterformat"]["divisions"]}
        return subs, divs

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

    def make_shape(self, profile, depth, anchor, z, x):
        zu = vunit(z)
        xu = vunit(x) if x is not None else perp(zu)
        yu = vcross(zu, xu)
        if profile.is_a("IfcCircleProfileDef"):
            return shape_cyl(anchor, zu, depth, profile.Radius)
        w, d = profile.XDim, profile.YDim
        c = vadd(anchor, vscale(zu, depth / 2))
        return shape_box(c, [xu, yu, zu], (w / 2, d / 2, depth / 2))

    def elem(self, storey, cls, name, tag, obj_type, profile, depth, style, anchor=None, z=(0.0, 0.0, 1.0),
             x=None, predef=None, pset=None, props=(), service=None, pl=None, transparency=0.0,
             truth=None, alt=None, tags=(), cat="mepi", run=None, kind=None):
        """One product: body extruded from the anchor along z (profile centred on the anchor).

        truth is the design-intent label "DISC/SUB/DIV" (see default-schema.json); alt lists the other codes a
        reasonable reviewer could give: {"subDiscipline": [...], "division": [...]}. Both go to the truth file only."""
        given_pl = pl is not None
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
        shape = None if given_pl or cat == "skip" else self.make_shape(profile, depth, anchor, z, x)
        if cls in SKIP_TRUTH:
            truth = None
        elif truth is None:
            raise SystemExit(f"no truth label for {cls} {name}")
        rec = dict(el=el, gid=el.GlobalId, name=name, cls=cls, shape=shape, cat=cat, tags=set(tags), run=run,
                   kind=kind, truth=truth, alt=alt, aabb=shape_aabb(shape) if shape else None)
        self.recs.append(rec)
        return rec

    def group(self, service_or_name, system_enum, els):
        sysobj = self.f.createIfcDistributionSystem(self.guid(), self.owner, service_or_name, None, None, None,
                                                    system_enum)
        self.f.createIfcRelAssignsToGroup(self.guid(), self.owner, None, None, els, None, sysobj)

    def assign(self, recs, name, system_enum):
        self.group(name, system_enum, [r["el"] for r in recs])

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
            for ci, x in enumerate(range(-36, 66, int(TILE))):
                self.elem(GRADE, "IfcSlab", f"Paving slab PAV-{ri + 1:02d}-{ci + 1:02d}", f"PAV-{ri + 1:02d}-{ci + 1:02d}",
                          "Paving (concrete)", self.rect(TILE, TILE), 0.3, "civil",
                          anchor=(x + TILE / 2, y + TILE / 2, -0.3), predef="BASESLAB", pset="Pset_SlabCommon",
                          props=[("Reference", "PAV-6"), ("IsExternal", True), ("LoadBearing", True)],
                          truth="CIV/PAV/32", cat="ground")
        self.elem(GRADE, "IfcSlab", "Perimeter road south", "ROAD-S", "Road (concrete)", self.rect(90.0, 4.0), 0.4,
                  "road", anchor=(21.0, -16.0, -0.4), predef="BASESLAB", pset="Pset_SlabCommon",
                  props=[("Reference", "RD-1"), ("IsExternal", True), ("LoadBearing", True)],
                  truth="CIV/PAV/32", cat="ground")
        self.elem(GRADE, "IfcSlab", "Perimeter road east", "ROAD-E", "Road (concrete)", self.rect(4.0, 52.0), 0.4,
                  "road", anchor=(70.0, 10.0, -0.4), predef="BASESLAB", pset="Pset_SlabCommon",
                  props=[("Reference", "RD-2"), ("IsExternal", True), ("LoadBearing", True)],
                  truth="CIV/PAV/32", cat="ground")
        for i in range(10):
            x = i * BAY
            self.elem(GRADE, "IfcBuildingElementProxy", f"Drain trench DT-{i + 1:02d}", f"DT-{i + 1:02d}",
                      "Drain trench (concrete channel)", self.rect(BAY, 0.6), 0.3, "trench",
                      anchor=(x + BAY / 2, -6.0, -0.3), pset="Pset_DrainTrenchCommon",
                      props=[("Reference", "DT"), ("Width", 0.6), ("Depth", 0.3), ("Medium", "Process drain")],
                      truth="CIV/DRN/33", cat="ground")

    def footing(self, x, y, w, d, tag, equipment=False, tags=()):
        name = f"Equipment foundation {tag}" if equipment else f"Footing {tag}"
        otype = f"Equipment foundation {w:.1f} x {d:.1f} m" if equipment else f"Pad footing {w:.1f} x {d:.1f} m"
        # a footing under rack or platform steel is structural; a base under equipment is civil (schema: CIV FND)
        self.elem(GRADE, "IfcFooting", name, f"F-{tag}", otype,
                  self.rect(w, d), 0.7, "civil", anchor=(x, y, -0.3), predef="PAD_FOOTING",
                  pset="Pset_FootingCommon", props=[("ConcreteGrade", "C32/40"), ("Reference", tag)],
                  truth="CIV/FND/03" if equipment else "STR/FND/03", cat="ground", tags=(tag,))

    # ------------------------------------------------------------ structural
    def structural(self):
        for x in COL_X:
            for y in ROW_Y:
                tag = f"RC-{COL_X.index(x):02d}{'A' if y == ROW_Y[0] else 'B'}"
                self.elem(GRADE, "IfcColumn", f"Rack column {tag}", tag, "UC 305x305x97", self.rect(0.305, 0.305),
                          8.0, "steel", anchor=(x, y, 0.0), predef="COLUMN",
                          pset="Pset_ColumnCommon", props=[("Reference", "UC 305x305x97"), ("LoadBearing", True)],
                          truth="STR/COL/05", cat="struct")
                self.footing(x, y, 0.8, 0.8, tag)
        bays = [(COL_X[i], COL_X[i + 1]) for i in range(len(COL_X) - 1)]    # first bay is the 5 m battery-limit bay
        for tier, z_top, storey in ((1, 5.0, T1), (2, 8.0, T2)):
            zc = z_top - 0.23
            for y in ROW_Y:
                for b, (x0, x1) in enumerate(bays):
                    tag = f"B-T{tier}-{'A' if y == ROW_Y[0] else 'B'}{b + 1:02d}"
                    self.elem(storey, "IfcBeam", f"Tier {tier} beam X {tag}", tag, "UB 457x191x67",
                              self.rect(0.19, 0.46), x1 - x0, "steel", anchor=(x0, y, zc), z=(1.0, 0.0, 0.0),
                              predef="BEAM", pset="Pset_BeamCommon",
                              props=[("Reference", "UB 457x191x67"), ("Span", x1 - x0), ("LoadBearing", True)],
                              truth="STR/BEM/05", cat="struct")
            for i, x in enumerate(COL_X):
                tag = f"B-T{tier}-X{i + 1:02d}"
                self.elem(storey, "IfcBeam", f"Tier {tier} cross beam {tag}", tag, "UB 457x191x67",
                          self.rect(0.19, 0.46), ROW_Y[1] - ROW_Y[0], "steel", anchor=(x, ROW_Y[0], zc),
                          z=(0.0, 1.0, 0.0), predef="BEAM", pset="Pset_BeamCommon",
                          props=[("Reference", "UB 457x191x67"), ("Span", ROW_Y[1] - ROW_Y[0]), ("LoadBearing", True)],
                          truth="STR/BEM/05", cat="struct")
        for b, (x0, x1) in enumerate(bays):
            tag = f"ST-{b + 1:02d}"
            self.elem(GRADE, "IfcBeam", f"Longitudinal strut {tag}", tag, "RHS 200x300", self.rect(0.2, 0.3), x1 - x0,
                      "steel", anchor=(x0, 20.0, 2.5), z=(1.0, 0.0, 0.0), predef="BEAM",
                      pset="Pset_BeamCommon", props=[("Reference", "RHS 200x300"), ("Span", x1 - x0)],
                      truth="STR/BEM/05", cat="struct")
        for y in ROW_Y:
            for b, (x0, x1) in enumerate(bays):
                p0, p1 = (x0, y, 0.3), (x1, y, 4.77)
                if b % 2:
                    p0, p1 = (p1[0], y, p0[2]), (p0[0], y, p1[2])
                tag = f"BR-{'A' if y == ROW_Y[0] else 'B'}{b + 1:02d}"
                self.elem(GRADE, "IfcMember", f"Rack bracing {tag}", tag, "CHS 150x150", self.rect(0.15, 0.15),
                          vlen(vsub(p1, p0)), "steel", anchor=p0, z=vsub(p1, p0), predef="BRACE",
                          pset="Pset_MemberCommon", props=[("Reference", "SHS 150x150"), ("LoadBearing", True)],
                          truth="STR/BRC/05", cat="struct")
        self.platform()

    def platform(self):
        px0, px1, py0, py1 = 24.0, 36.0, 24.5, 28.5
        for x in (px0, 30.0, px1):
            for y in (py0, py1):
                tag = f"PC-{int(x)}{int(y)}"
                self.elem(GRADE, "IfcColumn", f"Platform column {tag}", tag, "SHS 300x300", self.rect(0.3, 0.3), 3.2,
                          "steel", anchor=(x, y, 0.0), predef="COLUMN", pset="Pset_ColumnCommon",
                          props=[("Reference", "SHS 300x300"), ("LoadBearing", True)], truth="STR/COL/05", cat="struct")
                self.footing(x, y, 0.8, 0.8, tag)
        for y in (py0, py1):
            self.elem(PLAT, "IfcBeam", f"Platform beam {y:.0f}", f"PB-{y:.0f}", "UB 305x165x40", self.rect(0.165, 0.305),
                      px1 - px0, "steel", anchor=(px0, y, 3.2), z=(1.0, 0.0, 0.0), predef="BEAM",
                      pset="Pset_BeamCommon", props=[("Reference", "UB 305x165x40"), ("Span", px1 - px0)],
                      truth="STR/BEM/05", cat="struct")
        for x in (px0, 30.0, px1):
            self.elem(PLAT, "IfcBeam", f"Platform cross beam {x:.0f}", f"PX-{x:.0f}", "UB 305x165x40",
                      self.rect(0.165, 0.305), py1 - py0, "steel", anchor=(x, py0, 3.2), z=(0.0, 1.0, 0.0),
                      predef="BEAM", pset="Pset_BeamCommon", props=[("Reference", "UB 305x165x40"), ("Span", py1 - py0)],
                      truth="STR/BEM/05", cat="struct")
        for i in range(6):
            for j in range(2):
                cx, cy = px0 + 1 + 2 * i, py0 + 1 + 2 * j
                tag = f"GP-{i + 1}{j + 1}"
                self.elem(PLAT, "IfcSlab", f"Grating panel {tag}", tag, "Steel grating 2.0 x 2.0", self.rect(2.0, 2.0),
                          0.1, "grating", anchor=(cx, cy, 3.4), predef="FLOOR", pset="Pset_SlabCommon",
                          props=[("Reference", "GRT-25"), ("LoadBearing", True), ("IsExternal", False)],
                          truth="STR/SLB/05", cat="struct")
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
                      props=[("Height", rail_h), ("Reference", "RL-1")], truth="ARC/STA/05", cat="struct")
        # stair from grade (x 20) up to the platform edge at x 24
        p0, p1 = (20.0, 26.5, 0.0), (px0, 26.5, 3.5)
        self.elem(PLAT, "IfcStair", "Platform stair ST-01", "ST-01", "Straight stair 1.0 m", self.rect(1.0, 0.3),
                  vlen(vsub(p1, p0)), "steel", anchor=p0, z=vsub(p1, p0), predef="STRAIGHT_RUN_STAIR",
                  pset="Pset_StairCommon", props=[("NumberOfRiser", 12), ("RiserHeight", 0.29), ("Width", 1.0)],
                  truth="ARC/STA/05", cat="struct")

    # ------------------------------------------------------------ architectural
    def control_building(self):
        H, T = BLD_H, 0.3
        wall_el = {}
        for key, (q0, q1) in WALLS.items():
            p0, p1 = (q0[0], q0[1], 0.0), (q1[0], q1[1], 0.0)
            L = vlen(vsub(p1, p0))
            x = vunit(vsub(p1, p0))
            partition = key == "I"
            rec = self.elem(GRADE, "IfcWall", f"Control building wall {key}", f"W-{key}",
                            "Block partition 300 mm" if partition else "Masonry 300 mm",
                            self.rect(L, T), H, "wall", anchor=mid(p0, p1), z=(0.0, 0.0, 1.0), x=x,
                            predef="STANDARD", pset="Pset_WallCommon",
                            props=[("IsExternal", not partition), ("LoadBearing", not partition), ("FireRating", "EI30")],
                            truth="ARC/WAL/04" if partition else "STR/WLS/04", cat="bldg", tags=(f"W-{key}",))
            wall_el[key] = (rec["el"], L, x)
            self.wall_pl[key] = rec["el"].ObjectPlacement
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
            self.recs.append(dict(el=op, gid=op.GlobalId, name=op.Name, cls="IfcOpeningElement", shape=None, cat="skip",
                                  tags=set(), run=None, kind=None, truth=None, alt=None, aabb=None))
            body_pl = self.place_rel(wpl, (ox, -0.05, ocenter), frame_z, frame_x)
            if kind in ("door", "door2"):
                tag = f"D-{n + 1:02d}"
                otype = "Double leaf 2.0 x 2.4 m" if kind == "door2" else "Single leaf 1.0 m"
                door = self.elem(GRADE, "IfcDoor", f"Door {tag}", tag, otype, self.rect(w, h), 0.1, "door",
                                 pl=body_pl, predef="DOOR", pset="Pset_DoorCommon",
                                 props=[("FireRating", "FD30"), ("IsExternal", key in ("S", "E")), ("Reference", "D-90")],
                                 truth="ARC/DOR/08", cat="skip")
                self.f.createIfcRelFillsElement(self.guid(), self.owner, None, None, op, door["el"])
            elif kind == "window":
                tag = f"WIN-{n + 1:02d}"
                win = self.elem(GRADE, "IfcWindow", f"Window {tag}", tag, "Double glazing 1.6 x 1.2", self.rect(w, h),
                                0.1, "window", pl=body_pl, predef="WINDOW", pset="Pset_WindowCommon",
                                props=[("GlazingAreaFraction", 0.8), ("IsExternal", key != "I"), ("Reference", "W-16")],
                                truth="ARC/WIN/08", cat="skip")
                self.f.createIfcRelFillsElement(self.guid(), self.owner, None, None, op, win["el"])
        # floor, roof, spaces
        cx, cy = (BLD[0] + BLD[1]) / 2, (BLD[2] + BLD[3]) / 2
        bw, bd = BLD[1] - BLD[0], BLD[3] - BLD[2]
        self.elem(GRADE, "IfcSlab", "Control building floor", "FL-CB", "Floor slab 200 mm", self.rect(bw, bd), 0.2,
                  "civil", anchor=(cx, cy, 0.0), predef="FLOOR", pset="Pset_SlabCommon",
                  props=[("IsExternal", False), ("LoadBearing", True)], truth="STR/SLB/03",
                  alt={"subDiscipline": ["FND"], "division": []}, cat="bldg")
        self.elem(GRADE, "IfcSlab", "Control building roof", "RF-CB", "Roof slab 250 mm", self.rect(bw, bd), 0.25,
                  "roof", anchor=(cx, cy, H), predef="ROOF", pset="Pset_SlabCommon",
                  props=[("IsExternal", True), ("LoadBearing", True)], truth="STR/SLB/03",
                  alt={"subDiscipline": [], "division": ["07"]}, cat="bldg")
        spaces = []
        for name, sx, tag in (("Control room", -28.0, "SP-CR"), ("MCC room", -16.0, "SP-MCC")):
            sp = self.elem(GRADE, "IfcSpace", name, None, name, self.rect(11.7, bd - 0.3), H - 0.3, "space",
                           anchor=(sx, cy, 0.0), predef="SPACE", pset="Pset_SpaceCommon",
                           props=[("Reference", tag), ("OccupancyType", "Office" if "Control" in name else "Electrical")],
                           transparency=0.85, cat="skip")
            spaces.append(sp["el"])
        self.f.createIfcRelAggregates(self.guid(), self.owner, None, None, self.storey[GRADE], spaces)
        self.aggregated[GRADE] += spaces

    def electrical_rooms(self):
        # MCC line-up along the east wall of the MCC room; the cable tray lands on its top
        self.elem(GRADE, "IfcElectricDistributionBoard", "MCC panel MCC-101 (415 V)", "MCC-101",
                  "Motor control centre 415 V", self.rect(0.8, 5.0), 2.2, "board", anchor=(-10.6, 12.0, 0.2),
                  predef="MOTORCONTROLCENTRE", pset="Pset_ElectricDistributionBoardTypeCommon",
                  props=[("Voltage", 415.0), ("RatedCurrent", 400.0), ("System", "Electrical - MCC")],
                  truth="ELE/PWR/26", tags=("MCC-101",))
        self.elem(GRADE, "IfcElectricDistributionBoard", "Lighting panel LP-101", "LP-101", "Lighting panel 230 V",
                  self.rect(0.6, 0.3), 1.8, "board", anchor=(-33.3, 15.55, 0.2), predef="DISTRIBUTIONBOARD",
                  pset="Pset_ElectricDistributionBoardTypeCommon",
                  props=[("Voltage", 230.0), ("RatedCurrent", 63.0), ("System", "Lighting")], truth="ELE/PWR/26")

    # ------------------------------------------------------------ equipment (bodies, foundations, nozzles)
    def nozzle(self, equip, p, n, dn, service, line, label):
        """A flanged nozzle on an equipment surface point p, pointing along n. Returns the free end of the flange."""
        r = max(RADIUS[dn] * 1.4, 0.07)
        nn = vunit(n)
        start = vsub(p, vscale(nn, NOZ_IN))
        sub = "UTL" if service in UTILITY else "PRC"
        rec = self.elem(GRADE, "IfcPipeFitting", f"Nozzle {label} on {equip}", f"{equip}/{label}", f"Nozzle flange DN{dn}",
                        self.circ(r), NOZ_LEN, (f"Fitting - {service}", tuple(c * 0.8 for c in SERVICE_RGB[service])),
                        anchor=start, z=nn, predef="CONNECTOR", pset="Pset_PipeFittingTypeCommon",
                        props=[("NominalDiameter", float(dn)), ("Material", "Carbon steel"), ("LineNumber", line)],
                        service=service, truth=f"PIP/{sub}/40",
                        alt={"subDiscipline": [{"P": "PMP", "E": "HTX", "V": "VES"}[equip[0]]], "division": []},
                        tags=(equip, line), kind="nozzle")
        self.nozzles.append((rec, equip, p))
        return vadd(p, vscale(nn, NOZ_LEN - NOZ_IN))

    def equipment(self):
        self.nz = {}      # (equipment tag, nozzle label) -> free end point
        for grp, g in PUMP_GROUPS.items():
            xw = g["xw"]
            for suffix, y in (("A", g["ya"]), ("B", g["yb"])):
                tag = f"P-{grp}{suffix}"
                kw = 55.0 if suffix == "A" else 37.0
                self.footing(xw + 1.0, y, 3.0, 1.6, tag, equipment=True)
                self.elem(GRADE, "IfcBuildingElementProxy", f"Pump baseplate {tag}", f"BP-{tag}", "Pump baseplate 2.3 x 1.0 m",
                          self.rect(2.3, 1.0), 0.3, "steel", anchor=(xw + 1.0, y, ZF), pset="Pset_BuildingElementProxyCommon",
                          props=[("Reference", f"BP-{tag}")], truth="PIP/PMP/43",
                          alt={"subDiscipline": ["EQP", "SUP"], "division": ["05"]}, tags=(tag,), kind="equip")
                self.elem(GRADE, "IfcPump", f"Pump {tag}", tag, "End-suction centrifugal pump", self.circ(PUMP_R), 0.8,
                          "pump", anchor=(xw, y, PUMP_ZS), z=(1.0, 0.0, 0.0), predef="ENDSUCTION",
                          pset="Pset_PumpCommon", props=[("Duty kW", kw), ("Medium", "Crude / cooling water"),
                                                         ("Reference", tag)],
                          truth="PIP/PMP/43", tags=(tag,), kind="equip")
                self.elem(GRADE, "IfcElectricMotor", f"Motor M-{tag[2:]}", f"M-{tag[2:]}", "Motor 3-phase 415 V",
                          self.circ(PUMP_R), 1.1, "motor", anchor=(xw + 0.9, y, PUMP_ZS), z=(1.0, 0.0, 0.0),
                          predef="INDUCTION", pset="Pset_ElectricMotorCommon",
                          props=[("Voltage", 415.0), ("Driver", tag)], truth="PIP/PMP/43",
                          alt={"subDiscipline": [], "division": ["26"]}, tags=(tag,), kind="equip")
        for e in (E201, E202):
            tag, x0, cy = e["tag"], e["x0"], e["cy"]
            self.footing(x0 + HX_L / 2 - 0.3, cy, HX_L + 0.9, 1.8, tag, equipment=True)
            self.elem(GRADE, "IfcHeatExchanger", f"Heat exchanger {tag}", tag, "Shell and tube heat exchanger",
                      self.circ(HX_R), HX_L, "hx", anchor=(x0, cy, HX_ZC), z=(1.0, 0.0, 0.0), predef="SHELLANDTUBE",
                      pset="Pset_HeatExchangerCommon", props=[("Duty kW", 1200.0), ("Reference", tag)],
                      truth="PIP/HTX/42", tags=(tag,), kind="equip")
            self.elem(GRADE, "IfcBuildingElementProxy", f"Exchanger channel {tag}", f"CH-{tag}", "Channel (front head)",
                      self.circ(HX_CH_R), 0.6, "hx", anchor=(x0 - 0.6, cy, HX_ZC), z=(1.0, 0.0, 0.0),
                      pset="Pset_BuildingElementProxyCommon", props=[("Reference", f"CH-{tag}")],
                      truth="PIP/HTX/42", tags=(tag,), kind="equip")
            for k, xs in enumerate(x0 + dx for dx in e["saddles"]):
                self.elem(GRADE, "IfcBuildingElementProxy", f"Exchanger saddle {tag}-{k + 1}", f"SD-{tag}-{k + 1}",
                          "Saddle support", self.rect(0.3, 1.0), HX_ZC - 0.7 - ZF, "steel", anchor=(xs, cy, ZF),
                          pset="Pset_BuildingElementProxyCommon", props=[("Reference", f"SD-{tag}")],
                          truth="PIP/HTX/42", alt={"subDiscipline": ["SUP"], "division": ["05", "40"]},
                          tags=(tag,), kind="equip")
        for n, (tag, (x, y)) in enumerate((("V-301", V301), ("V-302", V302))):
            self.footing(x, y, 3.2, 3.2, tag, equipment=True)
            self.elem(GRADE, "IfcBuildingElementProxy", f"Vessel skirt {tag}", f"SK-{tag}", "Vessel skirt",
                      self.circ(DRUM_R), SKIRT_TOP - ZF, "vessel", anchor=(x, y, ZF), pset="Pset_BuildingElementProxyCommon",
                      props=[("Reference", f"SK-{tag}")], truth="PIP/VES/43",
                      alt={"subDiscipline": [], "division": ["05"]}, tags=(tag,), kind="equip")
            self.elem(GRADE, "IfcTank", f"Vessel {tag}", tag, "Vertical drum", self.circ(DRUM_R), SHELL_TOP - SKIRT_TOP,
                      "vessel", anchor=(x, y, SKIRT_TOP), z=(0.0, 0.0, 1.0), predef="VESSEL", pset="Pset_TankCommon",
                      props=[("Volume m3", 22.6), ("Reference", tag)], truth="PIP/VES/43", tags=(tag,), kind="equip")
            # level transmitter on the shell (east side for V-301, west for V-302 would collide with the inlet: use north)
            self.elem(GRADE, "IfcSensor", f"Level transmitter LT-{3001 + n} on {tag}", f"LT-{3001 + n}", "LEVELSENSOR",
                      self.circ(0.05), 0.35, "sensor", anchor=(x, y - DRUM_R, 4.0), z=(0.0, -1.0, 0.0),
                      predef="LEVELSENSOR", pset="Pset_SensorTypeCommon",
                      props=[("Measurand", "Level transmitter"), ("Range", "0-5 m")], truth="INS/SNS/40",
                      tags=(tag,))

    # ------------------------------------------------------------ pipe runs
    def run(self, name, service, dn, mat, pts, valves=(), instr=(), bl=None, storey=GRADE):
        """A pipe run along the polyline pts: spools with flange joints, elbows at the corners, valves and instruments
        at spool middles. valves: (leg, s along the leg in m (negative from the end), IfcValveTypeEnum, tag);
        instr: (ISA kind, leg, s, tag[, direction]). bl='start'/'end': that end is a battery-limit tie-in (the pipe
        ends on a spectacle blind; the run must hold an isolation valve)."""
        r = RADIUS[dn]
        SR = (f"Pipe - {service}", SERVICE_RGB[service])
        FR = (f"Fitting - {service}", tuple(c * 0.8 for c in SERVICE_RGB[service]))
        VR = (f"Valve - {service}", tuple(c * 0.65 for c in SERVICE_RGB[service]))
        sub = "UTL" if service in UTILITY else "PRC"
        alt_p = {"subDiscipline": ["UTL"], "division": []} if service == "Flare" else None
        truth_p = f"PIP/{sub}/40"
        ins = INSULATION[service]
        obj = f"Pipe {mat} DN{dn}"
        pts = [tuple(float(c) for c in p) for p in pts]
        run = dict(name=name, service=service, dn=dn, r=r, pts=pts, bl=bl, spools=[], legs=[], valves=[], storey=storey)
        legs = []
        for si in range(len(pts) - 1):
            a, b = pts[si], pts[si + 1]
            L = vlen(vsub(b, a))
            if L < 0.2:
                raise SystemExit(f"run {name}: leg {si} is only {L:.2f} m long")
            d = vunit(vsub(b, a))
            n = max(1, math.ceil(L / SPOOL - 1e-9))
            legs.append((a, b, L, d, n, L / n))
        run["legs"] = legs
        common = dict(service=service, tags=(name,), run=name)
        # spools and the flange joints between them
        for si, (a, b, L, d, n, step) in enumerate(legs):
            for k in range(n):
                start = vadd(a, vscale(d, k * step))
                rec = self.elem(storey, "IfcPipeSegment", f"Pipe {name} spool {len(run['spools']) + 1:02d}",
                                f"{name}/S{len(run['spools']) + 1:02d}", obj, self.circ(r), step, SR, anchor=start, z=d,
                                predef="RIGIDSEGMENT", pset="Pset_PipeSegmentTypeCommon",
                                props=[("NominalDiameter", float(dn)), ("Material", mat), ("Insulation", ins),
                                       ("LineNumber", name), ("Service", service)],
                                truth=truth_p, alt=alt_p, kind="pipe", **common)
                run["spools"].append((rec, si, k, start, vadd(start, vscale(d, step))))
        jn = 0
        for si, (a, b, L, d, n, step) in enumerate(legs):
            for k in range(n - 1):
                jn += 1
                p = vadd(a, vscale(d, (k + 1) * step))
                self.elem(storey, "IfcPipeFitting", f"Flange joint {name} J{jn:02d}", f"{name}/J{jn:02d}", obj,
                          self.circ(r * 1.2), 0.12, FR, anchor=vsub(p, vscale(d, 0.06)), z=d, predef="CONNECTOR",
                          pset="Pset_PipeFittingTypeCommon",
                          props=[("NominalDiameter", float(dn)), ("Material", mat), ("LineNumber", name)],
                          truth=truth_p, alt=alt_p, kind="joint", **common)
            if si < len(legs) - 1:
                jn += 1
                p = b
                self.elem(storey, "IfcPipeFitting", f"Elbow {name} E{jn:02d}", f"{name}/E{jn:02d}", obj,
                          self.circ(r * 1.25), 0.3, FR, anchor=vsub(p, vscale(d, 0.15)), z=d, predef="BEND",
                          pset="Pset_PipeFittingTypeCommon",
                          props=[("NominalDiameter", float(dn)), ("Material", mat), ("LineNumber", name)],
                          truth=truth_p, alt=alt_p, kind="elbow", **common)

        def snap(leg, s):
            a, b, L, d, n, step = legs[leg]
            if s < 0:
                s = L + s
            k = min(n - 1, max(0, int(s / step)))
            return vadd(a, vscale(d, (k + 0.5) * step)), d, (leg, k), L

        used = set()
        for leg, s, vtype, tag in valves:
            p, d, key, L = snap(leg, s)
            if key in used:
                raise SystemExit(f"run {name}: two items on spool {key}")
            used.add(key)
            if legs[leg][5] < 0.85:
                raise SystemExit(f"run {name}: no room for valve {tag} on leg {leg}")
            control = vtype == "REGULATING"
            self.elem(storey, "IfcValve", f"Valve {tag} ({vtype.lower().replace('pressurerelief', 'relief')})", tag,
                      f"{vtype.title()} valve DN{dn}", self.circ(r * 1.6), 0.5, VR, anchor=vsub(p, vscale(d, 0.25)), z=d,
                      predef=vtype, pset="Pset_ValveTypeCommon",
                      props=[("NominalDiameter", float(dn)), ("Material", mat), ("LineNumber", name),
                             ("Service", service)],
                      truth="INS/CTL/40" if control else "PIP/VLV/40", kind="valve", **common)
            run["valves"].append((tag, vtype, leg))
        for item in instr:
            kind, leg, s, tag = item[:4]
            p, d, key, L = snap(leg, s)
            if key in used:
                raise SystemExit(f"run {name}: two items on spool {key}")
            used.add(key)
            nrm = item[4] if len(item) > 4 else ((0.0, 0.0, 1.0) if abs(d[2]) < 0.5 else (0.0, -1.0, 0.0))
            cls_pred, measurand = SENSOR[kind]
            self.elem(storey, "IfcSensor", f"{measurand} {tag} on {name}", tag, measurand, self.circ(0.05), 0.35,
                      "sensor", anchor=vadd(p, vscale(nrm, r)), z=nrm, predef=cls_pred,
                      pset="Pset_SensorTypeCommon",
                      props=[("Measurand", measurand), ("LineNumber", name), ("Service", service)],
                      truth="INS/SNS/40", kind="sensor", tags=(name,), run=name)
        if bl:
            i_end, i_in = (0, 1) if bl == "start" else (-1, -2)
            p_end = pts[i_end]
            out = vunit(vsub(p_end, pts[i_in]))
            self.elem(storey, "IfcPipeFitting", f"Spectacle blind BL {name}", f"{name}/BL", f"Spectacle blind DN{dn}",
                      self.circ(r * 1.7), 0.12, "blind", anchor=p_end, z=out, predef="USERDEFINED",
                      pset="Pset_PipeFittingTypeCommon",
                      props=[("NominalDiameter", float(dn)), ("Material", mat), ("LineNumber", name),
                             ("BatteryLimit", "BL-W")],
                      service=service, truth=truth_p, alt=alt_p, tags=(), run=None, kind="blind")
            if not any(v[1] == "ISOLATING" for v in run["valves"]):
                raise SystemExit(f"run {name}: battery-limit tie-in without an isolation valve")
        self.runs.append(run)
        return run

    def tee(self, p, axis, dn, service, line, runs, label):
        r = RADIUS[dn]
        sub = "UTL" if service in UTILITY else "PRC"
        ax = vunit(axis)
        for i, a in enumerate(runs):
            for b in runs[i + 1:]:
                self.tee_pairs.add(frozenset((a, b)))
        self.elem(GRADE, "IfcPipeFitting", f"Tee {label}", f"{line}/T{label}", f"Tee DN{dn}", self.circ(r * 1.3), 0.3,
                  (f"Fitting - {service}", tuple(c * 0.8 for c in SERVICE_RGB[service])),
                  anchor=vsub(p, vscale(ax, 0.15)), z=ax, predef="JUNCTION", pset="Pset_PipeFittingTypeCommon",
                  props=[("NominalDiameter", float(dn)), ("Material", "Carbon steel"), ("LineNumber", line)],
                  service=service, truth=f"PIP/{sub}/40", tags=tuple(runs), run=None, kind="tee")

    def piping(self):
        N = self.nz
        # ---- nozzle positions on the equipment (free end of each flange)
        # V-301: feed on the north face at rack tier 1 height, liquid outlet east, low
        N["V-301", "N1"] = self.nozzle("V-301", (V301[0], V301[1] + DRUM_R, zt(1, 150)), (0, 1, 0), 150,
                                       "Process - Crude feed", "150-PR-1101-A1A", "N1")
        N["V-301", "N2"] = self.nozzle("V-301", (V301[0] + DRUM_R, V301[1], 2.6), (1, 0, 0), 150,
                                       "Process - Crude feed", "150-PR-1121-A1A", "N2")
        N["V-302", "N1"] = self.nozzle("V-302", (V302[0], V302[1] + DRUM_R, 4.0), (0, 1, 0), 150,
                                       "Process - Exchanger outlet", "150-PR-1131-A1A", "N1")
        N["V-302", "N2"] = self.nozzle("V-302", (V302[0] + DRUM_R, V302[1], 2.6), (1, 0, 0), 150,
                                       "Process - Exchanger outlet", "150-PR-1132-A1A", "N2")
        N["V-302", "N3"] = self.nozzle("V-302", (V302[0], V302[1], SHELL_TOP), (0, 0, 1), 150, "Flare",
                                       "150-FL-1301-A1A", "N3")
        # exchangers
        e1, e2 = E201, E202
        xc1, xc2 = e1["x0"] - 0.3, e2["x0"] - 0.3        # channel nozzle x
        N["E-201", "C1"] = self.nozzle("E-201", (xc1, e1["cy"] - CH_DY, CH_TOP), (0, 0, 1), 100, "Process - Pump discharge",
                                       "100-PR-1112-A1A", "C1")
        N["E-201", "C2"] = self.nozzle("E-201", (xc1, e1["cy"] + CH_DY, CH_TOP), (0, 0, 1), 150, "Process - Exchanger outlet",
                                       "150-PR-1131-A1A", "C2")
        N["E-201", "S1"] = self.nozzle("E-201", (e1["x0"] + 2.7, e1["cy"], HX_ZC + HX_R), (0, 0, 1), 150, "Steam",
                                       "150-ST-1201-A1A", "S1")
        N["E-201", "S2"] = self.nozzle("E-201", (e1["x0"] + 3.0, e1["cy"], HX_ZC - HX_R), (0, 0, -1), 80, "Condensate",
                                       "080-CD-1202-A1A", "S2")
        N["E-202", "C1"] = self.nozzle("E-202", (xc2, e2["cy"] - CH_DY, CH_TOP), (0, 0, 1), 150, "Cooling water supply",
                                       "150-CW-1203-A1A", "C1")
        N["E-202", "C2"] = self.nozzle("E-202", (xc2, e2["cy"] + CH_DY, CH_TOP), (0, 0, 1), 150, "Cooling water return",
                                       "150-CW-1204-A1A", "C2")
        N["E-202", "S1"] = self.nozzle("E-202", (e2["x0"] + 3.4, e2["cy"], HX_ZC + HX_R), (0, 0, 1), 100,
                                       "Process - Pump discharge", "100-PR-1142-A1A", "S1")
        N["E-202", "S2"] = self.nozzle("E-202", (e2["x0"] + 1.0, e2["cy"], HX_ZC - HX_R), (0, 0, -1), 100,
                                       "Process - Product", "100-PR-1205-A1A", "S2")
        # pumps: suction on the west end face at shaft height, discharge on top of the casing
        for grp, g in PUMP_GROUPS.items():
            for suf, y in (("A", g["ya"]), ("B", g["yb"])):
                tag = f"P-{grp}{suf}"
                N[tag, "S"] = self.nozzle(tag, (g["xw"], y, PUMP_ZS), (-1, 0, 0), 150,
                                          "Process - Crude feed" if grp == "101" else "Process - Exchanger outlet",
                                          f"150-PR-{grp}{'1' if suf == 'A' else '2'}-A1A", "S")
                N[tag, "D"] = self.nozzle(tag, (g["xw"] + 0.4, y, PUMP_ZS + PUMP_R), (0, 0, 1), 100,
                                          "Process - Pump discharge", f"100-PR-{grp}{'3' if suf == 'A' else '4'}-A1A", "D")

        zb = lambda dn: zt(1, dn)          # noqa: E731  tier 1 pipe centre height
        RY = 16.5                           # riser line, outboard of the south column row

        # ---- crude feed: battery limit -> rack tier 1 (y 18.0) -> V-301 inlet on its north face
        x1 = V301[0]
        self.run("150-PR-1101-A1A", "Process - Crude feed", 150, "Carbon steel",
                 [(BL_END, 18.0, zb(150)), (x1, 18.0, zb(150)), N["V-301", "N1"]],
                 valves=[(0, 2.9, "ISOLATING", "XV-1101"), (1, -3.2, "ISOLATING", "XV-1102")],
                 instr=[("PT", 0, 9.0, "PT-1101"), ("FT", 0, 14.0, "FT-1101")], bl="start", storey=T1)
        # ---- V-301 -> P-101A/B suction
        for grp, g in PUMP_GROUPS.items():
            drum = g["drum"]
            xh, ya, yb = g["xh"], g["ya"], g["yb"]
            svc = "Process - Crude feed" if grp == "101" else "Process - Exchanger outlet"
            pre = "150-PR-1121-A1A" if grp == "101" else "150-PR-1132-A1A"
            drum_tag = "V-301" if grp == "101" else "V-302"
            n_out = N[drum_tag, "N2"]
            self.run(pre, svc, 150, "Carbon steel", [n_out, (xh, drum[1], n_out[2]), (xh, drum[1], PUMP_ZS), (xh, ya, PUMP_ZS)],
                     valves=[(1, 0.6, "ISOLATING", f"XV-{grp}1")], instr=[("PT", 2, 1.2, f"PT-{grp}1")])
            self.tee((xh, ya, PUMP_ZS), (0, 1, 0), 150, svc, pre, [pre, f"150-PR-{grp}1-A1A", f"150-PR-{grp}2-A1A"], f"S{grp}")
            self.run(f"150-PR-{grp}2-A1A", svc, 150, "Carbon steel",
                     [(xh, ya, PUMP_ZS), (xh, yb, PUMP_ZS), N[f"P-{grp}B", "S"]],
                     valves=[(1, -0.9, "ISOLATING", f"XV-{grp}3")])
            self.run(f"150-PR-{grp}1-A1A", svc, 150, "Carbon steel",
                     [(xh, ya, PUMP_ZS), N[f"P-{grp}A", "S"]], valves=[(0, 0.9, "ISOLATING", f"XV-{grp}2")])
            # discharge: A and B risers, header to the tee above A, main to the exchanger
            xn, zd = g["xw"] + 0.4, g["zd"]
            dsvc = "Process - Pump discharge"
            tgt = ("E-201", "C1") if grp == "101" else ("E-202", "S1")
            ex = N[tgt]
            yo = ex[1]
            dA, dB, dM = f"100-PR-{grp}3-A1A", f"100-PR-{grp}4-A1A", f"100-PR-{'1112' if grp == '101' else '1142'}-A1A"
            self.run(dA, dsvc, 100, "Stainless steel", [N[f"P-{grp}A", "D"], (xn, ya, zd)],
                     valves=[(0, 0.8, "CHECK", f"CV-{grp}1")])
            self.run(dB, dsvc, 100, "Stainless steel", [N[f"P-{grp}B", "D"], (xn, yb, zd), (xn, ya, zd)],
                     valves=[(0, 0.8, "CHECK", f"CV-{grp}2")], instr=[("PG", 1, 1.0, f"PG-{grp}1")])
            self.tee((xn, ya, zd), (0, 1, 0), 100, dsvc, dM, [dA, dB, dM], f"D{grp}")
            pts = [(xn, ya, zd), (xn, yo, zd), (ex[0], yo, zd), ex]
            self.run(dM, dsvc, 100, "Stainless steel", pts,
                     valves=[(2, -0.55, "ISOLATING", f"XV-{grp}4"), (1, 1.0 if grp == "101" else 3.0, "REGULATING" if grp == "102" else "ISOLATING",
                                                                   f"FV-{grp}5" if grp == "102" else f"XV-{grp}5")],
                     instr=[("PT", 1, 3.0 if grp == "101" else 6.5, f"PT-{grp}2")])
        # ---- E-201 process outlet -> V-302 inlet
        o = N["E-201", "C2"]
        i2 = N["V-302", "N1"]
        self.run("150-PR-1131-A1A", "Process - Exchanger outlet", 150, "Carbon steel",
                 [o, (o[0], o[1], 4.0), (o[0], 13.5, 4.0), (i2[0], 13.5, 4.0), i2],
                 valves=[(2, 3.0, "ISOLATING", "XV-1131")], instr=[("TT", 2, 6.5, "TT-2001"), ("FT", 2, 11.0, "FT-1131")])
        # ---- steam: BL -> rack tier 2 (y 18.0) -> riser at x 24 -> E-201 shell
        s1 = N["E-201", "S1"]
        zs2 = zt(2, 150)
        self.run("150-ST-1201-A1A", "Steam", 150, "Carbon steel",
                 [(BL_END, 18.0, zs2), (s1[0], 18.0, zs2), (s1[0], RY, zs2), (s1[0], RY, 3.6), (s1[0], s1[1], 3.6), s1],
                 valves=[(0, 2.9, "ISOLATING", "XV-1201"), (3, 2.0, "REGULATING", "FV-1201")],
                 instr=[("PT", 0, 9.0, "PT-1201"), ("FT", 0, 14.0, "FT-1201")], bl="start", storey=T2)
        # ---- condensate: E-201 shell bottom -> riser -> rack tier 1 (y 18.6) -> BL
        c = N["E-201", "S2"]
        zc80 = zt(1, 80)
        self.run("080-CD-1202-A1A", "Condensate", 80, "Stainless steel",
                 [c, (c[0], c[1], 0.7), (c[0], RY, 0.7), (c[0], RY, zc80), (c[0], 18.6, zc80), (BL_END, 18.6, zc80)],
                 valves=[(1, 1.0, "STEAMTRAP", "ST-1202"), (1, 4.3, "ISOLATING", "XV-1203"), (4, -2.9, "ISOLATING", "XV-1204")],
                 instr=[("TT", 4, 12.0, "TT-1202")], bl="end", storey=T1)
        # ---- cooling water supply: BL -> rack tier 1 (y 19.2) -> x 42 -> E-202 channel
        cs, cr = N["E-202", "C1"], N["E-202", "C2"]
        self.run("150-CW-1203-A1A", "Cooling water supply", 150, "Carbon steel",
                 [(BL_END, 19.2, zb(150)), (42.7, 19.2, zb(150)), (42.7, RY, zb(150)), (42.7, RY, 3.8),
                  (42.7, cs[1], 3.8), (cs[0], cs[1], 3.8), cs],
                 valves=[(0, 2.9, "ISOLATING", "XV-1301"), (4, 3.0, "ISOLATING", "XV-1302")],
                 instr=[("PT", 0, 12.0, "PT-1301"), ("FT", 0, 27.0, "FT-1301")], bl="start", storey=T1)
        # ---- cooling water return: E-202 channel -> riser at x 48 -> rack tier 1 (y 19.8) -> BL
        self.run("150-CW-1204-A1A", "Cooling water return", 150, "Carbon steel",
                 [cr, (cr[0], cr[1], 3.2), (cr[0], RY, 3.2), (cr[0], RY, zb(150)), (cr[0], 19.8, zb(150)), (BL_END, 19.8, zb(150))],
                 valves=[(1, 2.2, "REGULATING", "FV-1302"), (4, -3.0, "ISOLATING", "XV-1303")],
                 instr=[("TT", 1, 4.0, "TT-1302"), ("PG", 4, 12.0, "PG-1302")], bl="end", storey=T1)
        # ---- product: E-202 shell bottom -> riser at x 51.2 -> rack tier 1 (y 20.4) -> BL
        p = N["E-202", "S2"]
        zp = zt(1, 100)
        self.run("100-PR-1205-A1A", "Process - Product", 100, "Stainless steel",
                 [p, (p[0], p[1], 0.7), (p[0], RY, 0.7), (p[0], RY, zp), (p[0], 20.4, zp), (BL_END, 20.4, zp)],
                 valves=[(1, 1.2, "ISOLATING", "XV-1205"), (4, -2.9, "ISOLATING", "XV-1206")],
                 instr=[("FT", 4, 17.0, "FT-1205"), ("PT", 4, 28.0, "PT-1205"), ("TT", 2, 3.0, "TT-2002", (-1.0, 0.0, 0.0))],
                 bl="end", storey=T1)
        # ---- flare: V-302 vapour outlet -> rack tier 2 (y 19.2) -> BL (off-site flare)
        v = N["V-302", "N3"]
        self.run("150-FL-1301-A1A", "Flare", 150, "Carbon steel",
                 [v, (v[0], v[1], zs2), (v[0], 19.2, zs2), (BL_END, 19.2, zs2)],
                 valves=[(2, -2.9, "ISOLATING", "XV-1401"), (1, 3.0, "ISOLATING", "XV-1402")],
                 instr=[("PT", 2, 12.0, "PT-1401"), ("FT", 2, 28.0, "FT-1401")], bl="end", storey=T2)

    # ------------------------------------------------------------ line supports
    def hits(self, shapes, ignore_run=None, ignore_tags=()):
        """True if any of the candidate shapes overlaps an existing body (beyond the contact tolerance)."""
        cand = [r for r in self.recs if r["aabb"] is not None]
        lo = np.array([r["aabb"][0] for r in cand])
        hi = np.array([r["aabb"][1] for r in cand])
        for s in shapes:
            slo, shi = shape_aabb(s)
            m = np.all(lo <= shi, axis=1) & np.all(hi >= slo, axis=1)
            for i in np.nonzero(m)[0]:
                r = cand[i]
                if ignore_run and r["run"] == ignore_run and r["kind"] == "pipe":
                    continue
                if r["tags"] & set(ignore_tags):
                    continue
                if self.clash(s, r["shape"], both=r["cat"] not in ("ground", "bldg")):
                    self.last_hit = r["name"]
                    return True
        return False

    def clash(self, a, b, cache=None, both=True):
        pa = cache(a) if cache else sample_points(a)
        if np.any(inside(pa, b, TOL_CLASH)):
            return True
        if not both:
            return False
        pb = cache(b) if cache else sample_points(b)
        return bool(np.any(inside(pb, a, TOL_CLASH)))

    def support_t(self, run, p, across, zbot, style="support", tag_prefix="Pipe", sub="SUP", width=0.6, cat="mepi",
                  truth="PIP/SUP/40", alt=None, tags=None, cls="IfcMember", kind="support"):
        """Try to build a T-support (or a sleeper when low) under pipe point p; returns False when it would clash."""
        tags = tags if tags is not None else (run["name"],)
        low = zbot <= 0.9 and tag_prefix == "Pipe"
        ax = vunit(across)
        along = vcross((0, 0, 1), ax)
        if low:
            w_x, w_y = (0.9, 0.3) if abs(ax[0]) > 0.5 else (0.3, 0.9)
            shapes = [shape_box((p[0], p[1], zbot / 2), [(1, 0, 0), (0, 1, 0), (0, 0, 1)], (w_x / 2, w_y / 2, zbot / 2))]
            if self.hits(shapes, ignore_run=run["name"]):
                return False
            self.nsup["sleeper"] += 1
            n = self.nsup["sleeper"]
            self.elem(GRADE, "IfcBuildingElementProxy", f"Pipe sleeper PSL-{n:02d}", f"PSL-{n:02d}", "Concrete pipe sleeper",
                      self.rect(w_x, w_y), zbot, "civil", anchor=(p[0], p[1], 0.0), pset="Pset_BuildingElementProxyCommon",
                      props=[("Reference", "PSL-1")], truth="PIP/SUP/40", alt={"subDiscipline": [], "division": ["03"]},
                      tags=tags, run=run["name"], kind="support")
            return True
        post_w = 0.2 if zbot > 3.0 else 0.15
        bar_t = 0.1
        post_h = zbot - bar_t
        shapes = [shape_box((p[0], p[1], post_h / 2), [(1, 0, 0), (0, 1, 0), (0, 0, 1)], (post_w / 2, post_w / 2, post_h / 2)),
                  shape_box((p[0], p[1], zbot - bar_t / 2), [along, ax, (0, 0, 1)], (0.075, width / 2, bar_t / 2))]
        if self.hits(shapes, ignore_run=run["name"], ignore_tags=tags if tag_prefix == "Tray" else ()):
            return False
        self.nsup[tag_prefix] += 1
        n = self.nsup[tag_prefix]
        key = "TS" if tag_prefix == "Pipe" else "CS"
        self.elem(GRADE, cls, f"{tag_prefix} T-support post {key}-{n:02d}", f"{key}-{n:02d}A", f"{tag_prefix} support post",
                  self.rect(post_w, post_w), post_h, style, anchor=(p[0], p[1], 0.0), predef="POST",
                  pset="Pset_MemberCommon", props=[("Reference", f"{key}-POST"), ("LoadBearing", True)],
                  truth=truth, alt=alt or {"subDiscipline": [], "division": ["05"]}, tags=tags, run=run["name"], kind="support")
        a0 = vsub((p[0], p[1], zbot - bar_t), vscale(ax, width / 2))
        self.elem(GRADE, cls, f"{tag_prefix} T-support crossbar {key}-{n:02d}", f"{key}-{n:02d}B", f"{tag_prefix} support crossbar",
                  self.rect(0.15, bar_t), width, style, anchor=vadd(a0, (0, 0, bar_t / 2)), z=ax, predef="MEMBER",
                  pset="Pset_MemberCommon", props=[("Reference", f"{key}-BAR"), ("LoadBearing", True)],
                  truth=truth, alt=alt or {"subDiscipline": [], "division": ["05"]}, tags=tags, run=run["name"], kind="support")
        return True

    @staticmethod
    def on_rack(p, r):
        return (BL_X - 0.2 <= p[0] <= 60.2 and 16.9 <= p[1] <= 23.1
                and (abs(p[2] - (5.0 + r + 0.005)) < 0.02 or abs(p[2] - (8.0 + r + 0.005)) < 0.02))

    def supports(self):
        """T-supports and sleepers under every horizontal leg off the rack, guides beside every long riser."""
        for run in self.runs:
            r = run["r"]
            for li, (a, b, L, d, n, step) in enumerate(run["legs"]):
                if abs(d[2]) > 0.5:
                    self.riser_supports(run, a, b, L, d)
                    continue
                # intervals of the leg that are not resting on the rack
                ss = np.arange(0.0, L + 1e-9, 0.05)
                off = [not self.on_rack(vadd(a, vscale(d, float(s))), r) for s in ss]
                i = 0
                while i < len(ss):
                    if not off[i]:
                        i += 1
                        continue
                    j = i
                    while j + 1 < len(ss) and off[j + 1]:
                        j += 1
                    s0, s1 = float(ss[i]), float(ss[j])
                    i = j + 1
                    # the interval is bounded by the rack (a support) or by the leg ends (elbow or nozzle)
                    Lc = s1 - s0
                    if Lc < 1.3:
                        continue
                    m = max(1, math.ceil(Lc / 4.0))
                    across = (0.0, 1.0, 0.0) if abs(d[0]) > 0.5 else (1.0, 0.0, 0.0)
                    for k in range(m):
                        s_want = s0 + (k + 0.5) * Lc / m
                        placed = False
                        for off_s in OFFSETS:
                            s = s_want + off_s
                            if s < s0 + 0.3 or s > s1 - 0.3:
                                continue
                            q = vadd(a, vscale(d, s))
                            if self.support_t(run, q, across, q[2] - r - 0.0):
                                placed = True
                                break
                        if not placed:
                            raise SystemExit(f"run {run['name']}: no free place for a support on leg {li} near s={s_want:.2f}")

    def riser_supports(self, run, a, b, L, d):
        """A vertical leg of 2 m or more gets a post beside it (east or west side, clear of the legs that leave the riser) with guide arms at 1 to 2 levels."""
        if L < 2.0:
            return
        r = run["r"]
        zlo = min(a[2], b[2])
        nar = 1 if L < 3.4 else 2
        zs0 = [zlo + L * (k + 1) / (nar + 1) for k in range(nar)]
        pw = 0.2 if max(zs0) + 0.25 > 4.0 else 0.15
        for dz, dx, sx in ((dz, dx, sx) for dz in (0.0, 0.3, -0.3, 0.6, -0.6) for dx in (0.33, 0.45) for sx in (1, -1)):
            zs = [z + dz for z in zs0]
            post_h = max(zs) + 0.25
            px, py = a[0] + sx * dx, a[1]
            arm_len = dx - r - pw / 2
            shapes = [shape_box((px, py, post_h / 2), [(1, 0, 0), (0, 1, 0), (0, 0, 1)], (pw / 2, pw / 2, post_h / 2))]
            for z in zs:
                shapes.append(shape_box((px - sx * (pw / 2 + arm_len / 2), py, z), [(1, 0, 0), (0, 1, 0), (0, 0, 1)],
                                        (arm_len / 2, 0.05, 0.05)))
            if self.hits(shapes, ignore_run=run["name"]):
                continue
            self.nsup["Riser"] += 1
            n = self.nsup["Riser"]
            self.elem(GRADE, "IfcMember", f"Riser guide post RG-{n:02d}", f"RG-{n:02d}A", "Riser guide post", self.rect(pw, pw),
                      post_h, "support", anchor=(px, py, 0.0), predef="POST", pset="Pset_MemberCommon",
                      props=[("Reference", "RG-POST"), ("LoadBearing", True)], truth="PIP/SUP/40",
                      alt={"subDiscipline": [], "division": ["05"]}, tags=(run["name"],), run=run["name"], kind="support")
            for k, z in enumerate(zs):
                self.elem(GRADE, "IfcMember", f"Riser guide arm RG-{n:02d}{'bc'[k]}", f"RG-{n:02d}{'BC'[k]}", "Riser guide arm",
                          self.rect(0.1, 0.1), arm_len, "support", anchor=(px - sx * pw / 2, py, z), z=(-float(sx), 0.0, 0.0),
                          predef="MEMBER", pset="Pset_MemberCommon", props=[("Reference", "RG-ARM"), ("LoadBearing", True)],
                          truth="PIP/SUP/40", alt={"subDiscipline": [], "division": ["05"]},
                          tags=(run["name"],), run=run["name"], kind="support")
            return
        raise SystemExit(f"run {run['name']}: no free place for riser guides at {a[0]:.1f},{a[1]:.1f} (hit {getattr(self, 'last_hit', '?')})")

    # ------------------------------------------------------------ electrical: cable tray, luminaires
    def tray_run(self, name, pts, tags=(), tier=GRADE, support=True, seg=2.0):
        """A cable tray run along pts (500 x 100 tray). Corner pieces overlap; the run is one system."""
        recs = []
        total = 0
        for si in range(len(pts) - 1):
            a, b = pts[si], pts[si + 1]
            L = vlen(vsub(b, a))
            d = vunit(vsub(b, a))
            n = max(1, math.ceil(L / seg - 1e-9))
            step = L / n
            for k in range(n):
                total += 1
                st = vadd(a, vscale(d, k * step))
                # profile 0.5 wide x 0.1 high; for a vertical segment the 0.5 is along x
                rec = self.elem(tier, "IfcCableCarrierSegment", f"Cable tray {name} {total:02d}", f"{name}-{total:02d}",
                                "Cable tray 500 x 100", self.rect(0.5, 0.1), step, "tray", anchor=st, z=d,
                                predef="CABLETRAYSEGMENT", pset="Pset_CableCarrierSegmentTypeCommon",
                                props=[("Width", 500.0), ("Height", 100.0), ("Material", "Galvanised steel")],
                                truth="ELE/CND/26", tags=("tray", name) + tuple(tags), run=None, kind="tray")
                recs.append(rec)
        self.trays.append(dict(name=name, pts=pts, recs=recs))
        return recs

    def cable_tray_runs(self):
        tray_all = []
        TZ = 4.4
        # spine: MCC room -> through the east wall -> x -7 -> north to y 22 -> up to the rack tier 2 tray
        tray_all += self.tray_run("CT-A", [(-10.6, 12.0, TZ), (-7.0, 12.0, TZ), (-7.0, 22.0, TZ)], tags=("W-E", "MCC-101"))
        tray_all += self.tray_run("CT-B", [(-10.6, 12.0, 2.4), (-10.6, 12.0, TZ + 0.05)], tags=("W-E", "MCC-101"))
        tray_all += self.tray_run("CT-C", [(-7.0, 22.0, TZ - 0.05), (-7.0, 22.0, 8.0)], seg=3.7)
        # rack tray at tier 2, y 22: continuous from the riser to the east end
        tray_all += self.tray_run("CT-R", [(-7.0, 22.0, 8.05), (60.0, 22.0, 8.05)], tier=T2)
        # south trunk and the branches to the motors
        tray_all += self.tray_run("CT-S", [(-7.0, 15.6, TZ), (PUMP_GROUPS["102"]["xw"] + 1.45, 15.6, TZ)])
        for grp, g in PUMP_GROUPS.items():
            xm = g["xw"] + 0.9 + 0.55
            tray_all += self.tray_run(f"CT-M{grp}", [(xm, 15.6, TZ), (xm, g["yb"], TZ)], tags=(f"P-{grp}A", f"P-{grp}B"))
            for suf, y in (("A", g["ya"]), ("B", g["yb"])):
                tray_all += self.tray_run(f"CT-D{grp}{suf}", [(xm, y, PUMP_ZS + PUMP_R), (xm, y, TZ + 0.05)],
                                          tags=(f"P-{grp}{suf}",), seg=3.0)
        self.assign(tray_all, "Electrical - cable tray", "ELECTRICAL")

    def tray_supports_and_lights(self):
        TZ = 4.4
        # tray supports: T-supports along the free runs, a stanchion beside the vertical riser
        dummy = lambda nm: dict(name=nm)                                    # noqa: E731
        for t in self.trays:
            if t["name"] in ("CT-A", "CT-S") or t["name"].startswith("CT-M"):
                for si in range(len(t["pts"]) - 1):
                    a, b = t["pts"][si], t["pts"][si + 1]
                    L = vlen(vsub(b, a))
                    d = vunit(vsub(b, a))
                    if t["name"] == "CT-A" and si == 0:
                        a = (-9.6, 12.0, TZ)     # first metres are inside the building and the wall
                        L = vlen(vsub(b, a))
                    m = max(1, math.ceil(L / 4.0))
                    across = (0.0, 1.0, 0.0) if abs(d[0]) > 0.5 else (1.0, 0.0, 0.0)
                    for k in range(m):
                        s_want = (k + 0.5) * L / m
                        for off_s in OFFSETS:
                            s = s_want + off_s
                            if s < 0.3 or s > L - 0.3:
                                continue
                            q = vadd(a, vscale(d, s))
                            if self.support_t(dummy(t["name"]), q, across, TZ - 0.05, tag_prefix="Tray", width=0.8,
                                              style="steel", truth="ELE/CND/26",
                                              alt={"subDiscipline": [], "division": ["05"]}, tags=("tray",)):
                                break
                        else:
                            raise SystemExit(f"tray {t['name']}: no free place for a support near s={s_want:.1f}")
        # stanchion for the vertical riser at x -7, y 22 (north side), arms at two levels
        px, py = -7.0, 22.4
        self.elem(GRADE, "IfcMember", "Tray riser stanchion TR-01", "TR-01A", "Tray riser stanchion", self.rect(0.15, 0.15), 7.6,
                  "steel", anchor=(px, py, 0.0), predef="POST", pset="Pset_MemberCommon",
                  props=[("Reference", "TR-POST"), ("LoadBearing", True)], truth="ELE/CND/26",
                  alt={"subDiscipline": [], "division": ["05"]}, tags=("tray",))
        for k, z in enumerate((5.6, 7.4)):
            self.elem(GRADE, "IfcMember", f"Tray riser arm TR-01{'bc'[k]}", f"TR-01{'BC'[k]}", "Tray riser arm", self.rect(0.1, 0.1),
                      0.275 - 0.0, "steel", anchor=(px, py - 0.075, z), z=(0.0, -1.0, 0.0), predef="MEMBER",
                      pset="Pset_MemberCommon", props=[("Reference", "TR-ARM"), ("LoadBearing", True)],
                      truth="ELE/CND/26", alt={"subDiscipline": [], "division": ["05"]}, tags=("tray",))
        # luminaires on the rack columns, both faces, under tier 1
        lights = []
        for i, x in enumerate(COL_X):
            for k, (y, sgn) in enumerate(((ROW_Y[0], -1), (ROW_Y[1], 1))):
                tag = f"LU-{i + 1:02d}{'A' if k == 0 else 'B'}"
                yc = y + sgn * (0.1525 + 0.1)
                lights.append(self.elem(GRADE, "IfcLightFixture", f"Luminaire {tag}", tag, "LED luminaire 60 W",
                                        self.rect(0.5, 0.2), 0.2, "light", anchor=(x, yc, 3.9),
                                        pset="Pset_LightFixtureTypeCommon",
                                        props=[("Power W", 60.0), ("Lumens", 6500.0)], truth="ELE/LTG/26"))
        self.assign(lights, "Lighting", "LIGHTING")

    def battery_limit_marker(self):
        """The marked battery-limit line: a board between the two BL columns, just below the lines' spectacle blinds."""
        self.elem(GRADE, "IfcBuildingElementProxy", "Battery limit marker board BL-W", "BL-W", "Battery limit marker board",
                  self.rect(0.04, ROW_Y[1] - ROW_Y[0] - 0.4), 1.0, "marker", anchor=(BL_X, 20.0, 3.0),
                  pset="Pset_BuildingElementProxyCommon",
                  props=[("Reference", "BL-W"), ("Text", "BATTERY LIMIT - UNIT 100 / OFF-SITE")],
                  truth="GEN/UNC/10")

    def extras(self):
        """Kerbs and fence posts along the roads, base plates."""
        for i in range(30):
            x = -24.0 + 3.0 * i
            self.elem(GRADE, "IfcBuildingElementProxy", f"Kerb KB-S-{i + 1:02d}", f"KB-S-{i + 1:02d}",
                      "Kerb (concrete, 3 m)", self.rect(3.0, 0.3), 0.15, "civil", anchor=(x + 1.5, -14.0, 0.0),
                      pset="Pset_KerbCommon", props=[("Reference", "KB-1"), ("Length", 3.0)],
                      truth="CIV/PAV/32", cat="ground")
        for i in range(18):
            y = -16.0 + 3.0 * i
            self.elem(GRADE, "IfcBuildingElementProxy", f"Kerb KB-E-{i + 1:02d}", f"KB-E-{i + 1:02d}",
                      "Kerb (concrete, 3 m)", self.rect(0.3, 3.0), 0.15, "civil", anchor=(68.0, y + 1.5, 0.0),
                      pset="Pset_KerbCommon", props=[("Reference", "KB-2"), ("Length", 3.0)],
                      truth="CIV/PAV/32", cat="ground")
        for i in range(16):
            x = -24.0 + 6.0 * i
            self.elem(GRADE, "IfcBuildingElementProxy", f"Fence post FP-S-{i + 1:02d}", f"FP-S-{i + 1:02d}",
                      "Fence post 2.4 m", self.rect(0.1, 0.1), 2.4, "civil", anchor=(x, -18.5, 0.0),
                      pset="Pset_FenceCommon", props=[("Height", 2.4), ("Reference", "FN-1")],
                      truth="CIV/LND/32", cat="ground")
        for i in range(10):
            y = -18.0 + 6.0 * i
            self.elem(GRADE, "IfcBuildingElementProxy", f"Fence post FP-E-{i + 1:02d}", f"FP-E-{i + 1:02d}",
                      "Fence post 2.4 m", self.rect(0.1, 0.1), 2.4, "civil", anchor=(74.0, y, 0.0),
                      pset="Pset_FenceCommon", props=[("Height", 2.4), ("Reference", "FN-2")],
                      truth="CIV/LND/32", cat="ground")
        for i, x in enumerate(COL_X):
            for y in ROW_Y:
                tag = f"BP-{i + 1:02d}{'A' if y == ROW_Y[0] else 'B'}"
                self.elem(GRADE, "IfcPlate", f"Column base plate {tag}", tag, "Base plate 450 x 450 x 20",
                          self.rect(0.45, 0.45), 0.02, "steel", anchor=(x, y, 0.4), pset="Pset_PlateCommon",
                          props=[("Reference", "BP-450"), ("Thickness", 0.02)], truth="STR/BRC/05", cat="struct")

    # ------------------------------------------------------------ checks
    def checks(self):
        problems = []
        out = []
        recs = [r for r in self.recs if r["shape"] is not None]
        by_run = {}
        for r in recs:
            if r["run"]:
                by_run.setdefault(r["run"], []).append(r)
        pipeish = [r for r in recs if r["kind"] in ("pipe", "joint", "elbow", "valve", "blind", "tee", "nozzle")]
        arr_lo = np.array([r["aabb"][0] for r in pipeish])
        arr_hi = np.array([r["aabb"][1] for r in pipeish])

        def near(p, exclude):
            p = np.asarray(p, float)
            m = np.all(arr_lo - 0.05 <= p, axis=1) & np.all(arr_hi + 0.05 >= p, axis=1)
            for i in np.nonzero(m)[0]:
                r = pipeish[i]
                if r is exclude:
                    continue
                if dist_point(p, r["shape"]) <= TOL_END:
                    yield r

        # 1. every spool endpoint coincides with another pipe element, a fitting or valve, a nozzle, a tee or a blind
        n_end = 0
        for run in self.runs:
            for rec, si, k, p0, p1 in run["spools"]:
                for p in (p0, p1):
                    n_end += 1
                    if not any(True for _ in near(p, rec)):
                        problems.append(f"dangling end: {rec['name']} at ({p[0]:.2f},{p[1]:.2f},{p[2]:.2f})")
        # 2. the free ends of each run: a nozzle on a body, a tee on another line, or a spectacle blind (not a bare pipe)
        n_free, n_noz, n_tee, n_bl = 0, 0, 0, 0
        for run in self.runs:
            for end, p in (("start", run["pts"][0]), ("end", run["pts"][-1])):
                n_free += 1
                kinds = set()
                for r in pipeish:
                    if r["kind"] in ("nozzle", "tee", "blind") and dist_point(p, r["shape"]) <= TOL_END:
                        kinds.add(r["kind"])
                if not kinds:
                    problems.append(f"run {run['name']} ends in the air at {end} ({p[0]:.2f},{p[1]:.2f},{p[2]:.2f})")
                n_noz += "nozzle" in kinds
                n_tee += "tee" in kinds
                n_bl += "blind" in kinds
                if run["bl"] == end and "blind" not in kinds:
                    problems.append(f"run {run['name']}: battery-limit end without a spectacle blind")
                if "blind" in kinds and run["bl"] != end:
                    problems.append(f"run {run['name']}: spectacle blind on the wrong end")
        # 3. every nozzle touches its equipment body
        bodies = {}
        for r in recs:
            if r["kind"] == "equip":
                for t in r["tags"]:
                    bodies.setdefault(t, []).append(r)
        for rec, equip, p in self.nozzles:
            if min(dist_point(p, b["shape"]) for b in bodies[equip]) > TOL_END:
                problems.append(f"nozzle {rec['name']} does not touch {equip}")
        out.append(f"connectivity: {len(self.runs)} runs, {n_end} spool ends all on another pipe element; {n_free} run ends = "
                   f"{n_noz} on nozzles, {n_tee} on tees, {n_bl} on spectacle blinds; {len(self.nozzles)} nozzles touch their equipment")
        # 4. battery limit: valve + blind on a marked line
        bls = [r for r in self.runs if r["bl"]]
        xs = {round((r["pts"][0] if r["bl"] == "start" else r["pts"][-1])[0], 2) for r in bls}
        out.append(f"battery limit: {len(bls)} tie-ins (isolation valve + spectacle blind) at x = {sorted(xs)}, marker board BL-W "
                   f"at x = {BL_X}")
        if len(xs) != 1:
            problems.append("battery-limit tie-ins are not on one line")
        # 5. bodies must not overlap (beyond the contact tolerance), except intended contacts
        cache = {}

        def pts_of(s):
            k = id(s)
            if k not in cache:
                cache[k] = sample_points(s)
            return cache[k]

        lo = np.array([r["aabb"][0] for r in recs])
        hi = np.array([r["aabb"][1] for r in recs])
        n_pairs = 0
        clashes = []
        for i, a in enumerate(recs):
            if a["cat"] != "mepi":
                continue
            m = np.all(lo <= a["aabb"][1], axis=1) & np.all(hi >= a["aabb"][0], axis=1)
            for j in np.nonzero(m)[0]:
                b = recs[j]
                if b is a or b["cat"] == "skip":
                    continue
                if b["cat"] == "mepi" and j < i:
                    continue
                if a["tags"] & b["tags"] or (a["run"] and a["run"] == b["run"]):
                    kinds = {a["kind"], b["kind"]}
                    # a support touches its own pipe, but must stay clear of the run's valves, elbows and joints
                    if not ("support" in kinds and kinds & {"valve", "elbow", "joint", "sensor"}):
                        continue
                if a["run"] and b["run"] and frozenset((a["run"], b["run"])) in self.tee_pairs:
                    continue
                n_pairs += 1
                if self.clash(a["shape"], b["shape"], cache=pts_of, both=b["cat"] not in ("ground", "bldg")):
                    clashes.append((a["name"], b["name"]))
        for a, b in clashes[:40]:
            problems.append(f"clash: {a}  x  {b}")
        out.append(f"clashes: {n_pairs} candidate pairs of bodies tested, {len(clashes)} overlaps beyond {TOL_CLASH * 1000:.0f} mm")
        # 6. support: along every run the free span between supports/beams/equipment is 6 m or less
        worst = 0.0
        sup = [r for r in recs if r["kind"] == "support" or r["cat"] == "struct"]
        s_lo = np.array([r["aabb"][0] for r in sup])
        s_hi = np.array([r["aabb"][1] for r in sup])
        for run in self.runs:
            pts = run["pts"]
            seg = [vlen(vsub(pts[i + 1], pts[i])) for i in range(len(pts) - 1)]
            total = sum(seg)
            contacts = [0.0, total]
            arc = 0.0
            for i, (a, b, L, d, n, step) in enumerate(run["legs"]):
                for s in np.arange(0.0, L + 1e-9, 0.05):
                    q = np.array(vadd(a, vscale(d, float(s))))
                    m = np.all(s_lo - run["r"] - 0.05 <= q, axis=1) & np.all(s_hi + run["r"] + 0.05 >= q, axis=1)
                    for j in np.nonzero(m)[0]:
                        r = sup[j]
                        if dist_point(q, r["shape"]) <= run["r"] + 0.05:
                            contacts.append(arc + float(s))
                            break
                arc += L
            contacts = sorted(set(round(c, 2) for c in contacts))
            # merge contact samples that belong to one support (within 0.4 m)
            gaps = [contacts[i + 1] - contacts[i] for i in range(len(contacts) - 1)]
            g = max(gaps)
            worst = max(worst, g)
            if g > SPAN_MAX + 0.1:
                k = gaps.index(g)
                problems.append(f"unsupported span: {run['name']} {g:.1f} m between s={contacts[k]:.1f} and {contacts[k + 1]:.1f}")
        out.append(f"supports: {sum(self.nsup.values())} support sets ({', '.join(f'{k} {v}' for k, v in sorted(self.nsup.items()))}); "
                   f"largest free span on any run {worst:.1f} m (limit {SPAN_MAX:.0f} m)")
        # 7. the cable tray is one connected run from the MCC panel to every pump motor; lights sit on columns;
        #    equipment rests on its base
        def gap(x, y, step=4):
            return min(dist_point(q, y) for q in sample_points(x)[::step])

        tray = [r for r in recs if r["kind"] == "tray"]
        comp = list(range(len(tray)))

        def find(i):
            while comp[i] != i:
                comp[i] = comp[comp[i]]
                i = comp[i]
            return i

        tlo = np.array([r["aabb"][0] for r in tray]) - 0.05
        thi = np.array([r["aabb"][1] for r in tray]) + 0.05
        for i, a in enumerate(tray):
            m = np.all(tlo <= a["aabb"][1], axis=1) & np.all(thi >= a["aabb"][0], axis=1)
            for j in np.nonzero(m)[0]:
                if j > i and gap(a["shape"], tray[j]["shape"], 1) <= 0.05:
                    comp[find(i)] = find(j)
        n_comp = len({find(i) for i in range(len(tray))})
        by_name = {r["name"]: r for r in recs}
        touch = {"MCC-101": by_name["MCC panel MCC-101 (415 V)"]}
        for r in recs:
            if r["cls"] == "IfcElectricMotor":
                touch[r["name"]] = r
        for nm, r in touch.items():
            if min(gap(t["shape"], r["shape"]) for t in tray if np.all(t["aabb"][0] <= r["aabb"][1] + 0.05) and np.all(t["aabb"][1] >= r["aabb"][0] - 0.05)
                   ) > 0.03 if any(np.all(t["aabb"][0] <= r["aabb"][1] + 0.05) and np.all(t["aabb"][1] >= r["aabb"][0] - 0.05) for t in tray) else True:
                problems.append(f"cable tray does not reach {nm}")
        if n_comp != 1:
            problems.append(f"cable tray is in {n_comp} pieces, not one run")
        wall = by_name["Control building wall E"]
        if not any(np.all(t["aabb"][0] <= wall["aabb"][1]) and np.all(t["aabb"][1] >= wall["aabb"][0]) for t in tray):
            problems.append("cable tray does not pass through the MCC room wall")
        cols = [r for r in recs if r["cls"] == "IfcColumn"]
        n_light = 0
        for r in recs:
            if r["cls"] == "IfcLightFixture":
                n_light += 1
                if min(gap(r["shape"], c["shape"], 2) for c in cols if np.all(c["aabb"][0] <= r["aabb"][1] + 0.05) and np.all(c["aabb"][1] >= r["aabb"][0] - 0.05)
                       ) > 0.02:
                    problems.append(f"{r['name']} is not on a column")
        n_eq = 0
        bases = [r for r in recs if r["cat"] == "ground" and r["cls"] == "IfcFooting"]
        parts = [r for r in recs if r["kind"] == "equip"]
        for r in parts:
            if r["cls"] in ("IfcPump", "IfcElectricMotor", "IfcTank", "IfcHeatExchanger", "IfcBuildingElementProxy"):
                others = bases + [q for q in parts if q is not r]
                n_eq += 1
                if min(gap(r["shape"], q["shape"], 2) for q in others if np.all(q["aabb"][0] <= r["aabb"][1] + 0.05)
                       and np.all(q["aabb"][1] >= r["aabb"][0] - 0.05)) > 0.03:
                    problems.append(f"{r['name']} floats")
        out.append(f"cable tray: {len(tray)} segments in {n_comp} connected run, reaches MCC-101, the east wall opening and "
                   f"{sum(1 for r in recs if r['cls'] == 'IfcElectricMotor')} motors; {n_light} luminaires on columns; "
                   f"{n_eq} equipment bodies rest on a base")
        return problems, out

    # ------------------------------------------------------------ truth
    def truth_doc(self, seed):
        subs, divs = self.schema_codes
        elements = {}
        bad = []
        for r in self.recs:
            if r["cls"] in SKIP_TRUTH:
                continue
            d, s, v = r["truth"].split("/")
            if d not in subs or s not in subs[d] or v not in divs:
                bad.append(f"{r['name']}: {r['truth']}")
            alt = r["alt"]
            e = {"name": r["name"], "ifcClass": r["cls"], "discipline": d, "subDiscipline": s, "division": v}
            if alt:
                a = {}
                if alt.get("subDiscipline"):
                    a["subDiscipline"] = list(alt["subDiscipline"])
                if alt.get("division"):
                    a["division"] = list(alt["division"])
                for sc in a.get("subDiscipline", []):
                    if sc not in subs[d]:
                        bad.append(f"{r['name']}: alt sub {sc} not in {d}")
                for dv in a.get("division", []):
                    if dv not in divs:
                        bad.append(f"{r['name']}: alt division {dv}")
                if a:
                    e["alt"] = a
            elements[r["gid"]] = e
        if bad:
            raise SystemExit("truth labels not in the schema:\n  " + "\n  ".join(bad[:20]))
        return {
            "format": "xray-truth/1", "model": "process-plant",
            "generator": f"tools/make_process_plant_ifc.py --seed {seed}",
            "schema": "local:xray-throughline-aligned-default@1.0.0",
            "convention": CONVENTION, "elements": elements,
        }

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


CONVENTION = (
    "Labels are the design intent set when each element was created, from the schema descriptions; no classifier output "
    "was used. Piping: process services and the flare line are PIP/PRC, cooling water, steam and condensate are PIP/UTL "
    "(flare alt UTL), all with division 40; fittings, spool joints, nozzle flanges, tees and spectacle blinds follow "
    "their line (a nozzle flange alt: the equipment's sub-discipline). Valves are PIP/VLV; a regulating valve with an "
    "F-tag is a control valve, INS/CTL; transmitters and gauges are INS/SNS. Pumps, their motors and baseplates are "
    "PIP/PMP division 43 (motor alt division 26, baseplate alt EQP, SUP); exchangers with channel and saddles are PIP/HTX "
    "division 42; drums and skirts are PIP/VES division 43. Pipe sleepers, T-supports and riser guides are PIP/SUP division "
    "40 (alt 05 steel or 03 concrete); cable tray supports and the tray riser stanchion follow the tray, ELE/CND (alt division 05). Foundations under equipment are "
    "CIV/FND, under rack and platform steel STR/FND, both division 03. Rack steel is STR (COL, BEM, BRC; base plates BRC), "
    "platform grating STR/SLB, stair and railings ARC/STA division 05. Masonry exterior walls are load bearing, STR/WLS 04; the "
    "block partition is ARC/WAL 04; floor and roof slabs are STR/SLB 03 (roof alt division 07). Doors ARC/DOR and windows "
    "ARC/WIN, division 08. Paving, roads and kerbs CIV/PAV 32, fence posts CIV/LND 32, drain trench CIV/DRN 33. Switchboards "
    "ELE/PWR, cable tray ELE/CND, luminaires ELE/LTG, division 26. The battery-limit marker board is a sign that fits no "
    "discipline: GEN/UNC with division 10. IfcSpace and IfcOpeningElement are not kept by the converter and have no entry."
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--no-checks", action="store_true", help="skip the self-checks (for debugging only)")
    args = ap.parse_args()
    p = Plant(args.seed)
    p.spatial()
    p.civil()
    p.structural()
    p.control_building()
    p.electrical_rooms()
    p.equipment()
    p.piping()
    p.cable_tray_runs()
    p.supports()
    p.tray_supports_and_lights()
    p.battery_limit_marker()
    p.extras()
    if not args.no_checks:
        problems, summary = p.checks()
        for line in summary:
            print(line, file=sys.stderr)
        if problems:
            print(f"{len(problems)} problems:", file=sys.stderr)
            for pr in problems[:60]:
                print("  " + pr, file=sys.stderr)
            return 1
    doc = p.truth_doc(args.seed)
    p.write(args.out)
    truth_path = re.sub(r"\.ifc$", "", args.out) + ".truth.json"
    with open(truth_path, "w", encoding="utf-8") as fh:
        head = {k: v for k, v in doc.items() if k != "elements"}
        fh.write(json.dumps(head, separators=(",", ":"), ensure_ascii=True)[:-1] + ',"elements":{\n')
        items = [json.dumps(k) + ":" + json.dumps(v, separators=(",", ":"), ensure_ascii=True) for k, v in doc["elements"].items()]
        fh.write(",\n".join(items) + "\n}}\n")
    total = sum(p.counts.values())
    print(f"{args.out}: {total} elements; {truth_path}: {len(doc['elements'])} labels", file=sys.stderr)
    for cls, n in sorted(p.counts.items(), key=lambda kv: -kv[1]):
        print(f"  {cls}: {n}", file=sys.stderr)
    dist = Counter(e["discipline"] for e in doc["elements"].values())
    print("truth by discipline: " + ", ".join(f"{k} {v}" for k, v in sorted(dist.items())), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
