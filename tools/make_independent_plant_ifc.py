#!/usr/bin/env python3
"""Independent test facility: a small surface-water treatment works (IFC4) plus its ground truth (xray-truth/1).

Usage:  python3 tools/make_independent_plant_ifc.py [--seed N] [-o models/independent/Water-Works.ifc]

Writes the IFC and, next to it, <name>.truth.json. Same seed, same bytes.

Why it exists: the classifier rules were tuned on the process plant, so their score there is circular. This facility was built
without looking at the rules or at the first generator. The labels are design intent, decided from the descriptions in
web/public/classification/default-schema.json alone, and passed as an argument where each element is created. They are never in
the IFC. The naming is deliberately messy and tool-like (CONVENTION below says how the labels were decided).

Facility ("Riverbend Water Treatment Works"): raw water -> rapid mix (alum, polymer, hypochlorite) -> flocculation -> two
sedimentation basins -> four pressure filters in a filter and pump hall (backwash pumps, air-scour blowers, instrument air) ->
clearwell -> high-lift pumps -> distribution main. Plus a chemical building (dosing pumps, eyewash, ventilation), a two-storey
administration and control building (HVAC, domestic plumbing, sprinklers, power, telecom, fire alarm), site civil works and yard
utilities. IFC4, metres, Z up.

Self-checks (the script exits non-zero when one fails): every pipe/duct/tray run end lies within 0.03 m of another element
(equipment, tee, tie-in chamber or the like); the touch graph of all elements (gap <= 0.03 m) is one connected component, so
nothing floats; every element has a truth entry whose codes exist in the schema.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import math
import os
import random
import sys
import uuid

import numpy as np

import ifcopenshell
import ifcopenshell.guid

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA_PATH = os.path.join(HERE, "..", "web", "public", "classification", "default-schema.json")

CONVENTION = (
    "Labels are design intent, set where each element is created, from the descriptions in default-schema.json only (not from any "
    "classifier rule, and not in the IFC). A pipe, fitting or valve takes the line it belongs to: process and chemical lines inside the "
    "works are PIP/PRC (division 40), instrument air and air-scour lines PIP/UTL, manual valves PIP/VLV, hangers and sleepers PIP/SUP; "
    "buried yard mains and sewers are CIV/UTL or CIV/DRN (division 33); piping inside the administration building follows its trade "
    "(MEC/HYD, PLB/SUP, PLB/DRN, PLB/STM, FPR/SPR). Process pumps, blowers, filters and chemical tanks are PIP (division 43; 46 for "
    "treatment equipment such as filters, mixers and scrapers). Motors are ELE/PWR. Control valves, transmitters and analysers are INS "
    "(division 40; 25 for controllers and junction boxes). Equipment plinths outside buildings are CIV/FND, inside buildings STR/FND. "
    "Concrete basin floors are STR/SLB and basin walls STR/WLS. Paving and kerbs are CIV/PAV (32), fence, gate and trees CIV/LND. "
    "Wherever a second answer is defensible it is listed in alt: subDiscipline (same discipline) and division are used by the lenient column; "
    "alt.discipline and alt.also (cross-discipline \"DISC/sub\" pairs) are informational only. Elements with no name, or a proxy class where a proper one exists, keep the label of what "
    "they really are."
)

SCHEMA = json.load(open(SCHEMA_PATH))
VALID_SUBS = {d["code"]: {s["code"] for s in d["subDisciplines"]} for d in SCHEMA["disciplines"]}
VALID_DIVS = {d["division"] for d in SCHEMA["masterformat"]["divisions"]}


def L(d, s, v, **alt):
    return (d, s, v, alt or None)


PRC = L("PIP", "PRC", "40", subDiscipline=["UTL"], division=["46"])
UTL = L("PIP", "UTL", "40", subDiscipline=["PRC"])
VLV = L("PIP", "VLV", "40")
CTRLV = L("INS", "CTL", "40", subDiscipline=["SNS"], discipline=["PIP"], also=["PIP/VLV"], division=["25"])
SUPP = L("PIP", "SUP", "40", division=["05", "22", "23"])
PMP = L("PIP", "PMP", "43", division=["46"])
MOTOR = L("ELE", "PWR", "26", discipline=["PIP"], also=["PIP/PMP"], division=["43"])
VES46 = L("PIP", "VES", "46", division=["43"])
VES43 = L("PIP", "VES", "43", division=["46"])
EQP46 = L("PIP", "EQP", "46", division=["43", "41"])
SNS = L("INS", "SNS", "40", division=["25"])
JBI = L("INS", "NET", "25", discipline=["ELE"], also=["ELE/WIR"], division=["26"])
PLC = L("INS", "CTL", "25", division=["40"])
FNDO = L("CIV", "FND", "03", discipline=["STR"], also=["STR/FND"])
FNDI = L("STR", "FND", "03", discipline=["CIV"], also=["CIV/FND"])
SLB = L("STR", "SLB", "03")
WLS = L("STR", "WLS", "03")
COL03 = L("STR", "COL", "03")
COL05 = L("STR", "COL", "05")
BEM03 = L("STR", "BEM", "03")
BEM05 = L("STR", "BEM", "05")
BRC05 = L("STR", "BRC", "05")
CIVGRADE = L("CIV", "ERT", "31")
ROAD = L("CIV", "PAV", "32", division=["34"])
KERB = L("CIV", "PAV", "32")
LND = L("CIV", "LND", "32")
SDRN = L("CIV", "DRN", "33")
SUTL = L("CIV", "UTL", "33")
WALX = L("ARC", "WAL", "04", division=["03"])
WALP = L("ARC", "WAL", "09", division=["05"])
CLAD = L("ARC", "WAL", "07", division=["05"])
DOR = L("ARC", "DOR", "08")
WIN = L("ARC", "WIN", "08")
ROF = L("ARC", "ROF", "07")
CEIL = L("ARC", "FIN", "09")
FUR = L("ARC", "FUR", "12")
CONV = L("ARC", "FUR", "14", discipline=["PIP"], also=["PIP/EQP"], division=["41"])
STAIR = L("ARC", "STA", "05", discipline=["STR"], also=["STR/BRC"])
DUCT = L("MEC", "DUC", "23")
TRM = L("MEC", "TRM", "23")
ACC = L("MEC", "ACC", "23")
MEQP = L("MEC", "EQP", "23")
HYD = L("MEC", "HYD", "23", discipline=["PIP"], also=["PIP/UTL"], division=["22"])
HVLV = L("MEC", "HYD", "23", discipline=["PIP"], also=["PIP/VLV"], division=["40"])
HPMP = L("MEC", "EQP", "23", subDiscipline=["HYD"], discipline=["PIP"], also=["PIP/PMP"])
PSUP = L("PLB", "SUP", "22")
PDRN = L("PLB", "DRN", "22")
PSTM = L("PLB", "STM", "22")
PFIX = L("PLB", "FIX", "22")
PEQP = L("PLB", "EQP", "22")
PVLV = L("PLB", "SUP", "22", discipline=["PIP"], also=["PIP/VLV"], division=["40"])
SPR = L("FPR", "SPR", "21")
EXT = L("FPR", "EXT", "10", division=["21"])
STP = L("FPR", "STP", "33", division=["21"])
PWR = L("ELE", "PWR", "26")
CND = L("ELE", "CND", "26")
WIR = L("ELE", "WIR", "26")
LTG = L("ELE", "LTG", "26")
DEV = L("ELE", "DEV", "26")
GEN = L("ELE", "GEN", "26")
DAT = L("TEL", "DAT", "27")
SEC = L("TEL", "SEC", "28")
ALM = L("TEL", "ALM", "28")
BAS = L("INS", "SNS", "25", discipline=["MEC"], division=["23"])

NPS = {0.5: .0213, 0.75: .0267, 1: .0334, 1.5: .0483, 2: .0603, 2.5: .0730, 3: .0889, 4: .1143, 6: .1683, 8: .2191, 10: .2731,
       12: .3238, 14: .3556, 16: .4064, 20: .508, 24: .610}


def nps(n):
    return NPS[n]


def dn(mm):
    return mm / 1000.0


def unit(v):
    n = np.linalg.norm(v)
    return v / n if n else v


class G:
    def __init__(self, seed):
        self.seed = seed
        self.rng = random.Random(seed)
        self.n = 0
        self.f = f = ifcopenshell.file(schema="IFC4")
        f.header.file_name.name = "Water-Works.ifc"
        f.header.file_name.time_stamp = "2026-01-01T00:00:00"
        f.header.file_name.author = ("",)
        f.header.file_name.organization = ("",)
        f.header.file_name.originating_system = "independent plant generator"
        f.header.file_description.description = ("ViewDefinition [CoordinationView]",)
        self.truth = {}
        self.boxes = []
        self.runs = []
        self.ents = []
        self.contain = {}
        self.sysmap = {}
        self.matmap = {}
        self.tagn = {}
        self.run_n = 0
        self.ax2d = f.create_entity("IfcAxis2Placement2D", Location=self.cp((0, 0)))
        self._project()

    # ------------------------------------------------------------ IFC plumbing
    def gid(self):
        self.n += 1
        h = hashlib.md5(f"indep-{self.seed}-{self.n}".encode()).hexdigest()
        return ifcopenshell.guid.compress(uuid.UUID(h).hex)

    def cp(self, p):
        return self.f.create_entity("IfcCartesianPoint", Coordinates=[float(x) for x in p])

    def dr(self, d):
        return self.f.create_entity("IfcDirection", DirectionRatios=[float(x) for x in d])

    def axis(self, loc, z=(0, 0, 1), x=(1, 0, 0)):
        return self.f.create_entity("IfcAxis2Placement3D", Location=self.cp(loc), Axis=self.dr(z), RefDirection=self.dr(x))

    def lp(self, loc, rel=None):
        return self.f.create_entity("IfcLocalPlacement", PlacementRelTo=rel, RelativePlacement=self.axis(loc))

    def _project(self):
        f = self.f
        units = [f.create_entity("IfcSIUnit", UnitType=u, Name=n) for u, n in
                 (("LENGTHUNIT", "METRE"), ("AREAUNIT", "SQUARE_METRE"), ("VOLUMEUNIT", "CUBIC_METRE"), ("PLANEANGLEUNIT", "RADIAN"))]
        ctx = f.create_entity("IfcGeometricRepresentationContext", ContextType="Model", CoordinateSpaceDimension=3, Precision=1e-5,
                              WorldCoordinateSystem=self.axis((0, 0, 0)))
        self.body = f.create_entity("IfcGeometricRepresentationSubContext", ContextIdentifier="Body", ContextType="Model",
                                    ParentContext=ctx, TargetView="MODEL_VIEW")
        self.project = f.create_entity("IfcProject", GlobalId=self.gid(), Name="Riverbend WTW", RepresentationContexts=[ctx],
                                       UnitsInContext=f.create_entity("IfcUnitAssignment", Units=units))
        self.site_pl = self.lp((0, 0, 0))
        self.site = f.create_entity("IfcSite", GlobalId=self.gid(), Name="Riverbend WTW Site", ObjectPlacement=self.site_pl,
                                    CompositionType="ELEMENT")
        self.rel_agg(self.project, [self.site])
        self.cont_ent = {"site": self.site}

    def rel_agg(self, parent, kids):
        self.f.create_entity("IfcRelAggregates", GlobalId=self.gid(), RelatingObject=parent, RelatedObjects=kids)

    def building(self, name, storeys):
        f = self.f
        bpl = self.lp((0, 0, 0), self.site_pl)
        b = f.create_entity("IfcBuilding", GlobalId=self.gid(), Name=name, ObjectPlacement=bpl, CompositionType="ELEMENT")
        self.rel_agg(self.site, [b])
        sts = []
        for k, (sname, el) in storeys.items():
            st = f.create_entity("IfcBuildingStorey", GlobalId=self.gid(), Name=sname, ObjectPlacement=self.lp((0, 0, el), bpl),
                                 CompositionType="ELEMENT", Elevation=float(el))
            sts.append(st)
            self.cont_ent[k] = st
        self.rel_agg(b, sts)

    # ------------------------------------------------------------ geometry items
    def solid(self, it, base):
        f = self.f
        if it[0] == "box":
            _, c, sz, rot = it
            pos = self.axis((c[0] - base[0], c[1] - base[1], c[2] - sz[2] / 2 - base[2]), (0, 0, 1), (math.cos(rot), math.sin(rot), 0))
            prof = f.create_entity("IfcRectangleProfileDef", ProfileType="AREA", Position=self.ax2d, XDim=float(sz[0]), YDim=float(sz[1]))
            depth = sz[2]
        else:
            _, p0, p1, d = it
            p0 = np.array(p0, float)
            p1 = np.array(p1, float)
            v = p1 - p0
            ln = float(np.linalg.norm(v))
            u = v / ln
            ref = (1, 0, 0) if abs(u[2]) > 0.9 else tuple(unit(np.array([-u[1], u[0], 0.0])))
            pos = self.axis(tuple(p0 - np.array(base)), tuple(u), ref)
            prof = f.create_entity("IfcCircleProfileDef", ProfileType="AREA", Position=self.ax2d, Radius=float(d) / 2)
            depth = ln
        return f.create_entity("IfcExtrudedAreaSolid", SweptArea=prof, Position=pos, ExtrudedDirection=self.dr((0, 0, 1)), Depth=float(depth))

    @staticmethod
    def aabb(it):
        if it[0] == "box":
            _, c, sz, rot = it
            ex = abs(math.cos(rot)) * sz[0] / 2 + abs(math.sin(rot)) * sz[1] / 2
            ey = abs(math.sin(rot)) * sz[0] / 2 + abs(math.cos(rot)) * sz[1] / 2
            return (np.array([c[0] - ex, c[1] - ey, c[2] - sz[2] / 2], float), np.array([c[0] + ex, c[1] + ey, c[2] + sz[2] / 2], float))
        _, p0, p1, d = it
        p0 = np.array(p0, float)
        p1 = np.array(p1, float)
        u = unit(p1 - p0)
        r = d / 2
        e = np.array([r * math.sqrt(max(0.0, 1 - u[i] ** 2)) for i in range(3)])
        return (np.minimum(p0, p1) - e, np.maximum(p0, p1) + e)

    def mat(self, name):
        if name not in self.matmap:
            self.matmap[name] = (self.f.create_entity("IfcMaterial", Name=name), [])
        return self.matmap[name]

    def system(self, code):
        if code not in self.sysmap:
            self.sysmap[code] = (self.f.create_entity("IfcDistributionSystem", GlobalId=self.gid(), Name=code), [])
        return self.sysmap[code]

    def tag(self, prefix, base=1101):
        self.tagn[prefix] = self.tagn.get(prefix, base - 1) + 1
        return f"{prefix}-{self.tagn[prefix]}"

    def rid(self):
        return self.rng.randint(100000, 9999999)

    # ------------------------------------------------------------ the one way to create an element
    def add(self, cls, name, items, T, cont="site", ptype=None, objtype=None, tag=None, desc=None, psets=None, system=None,
            material=None, proxy=0.0, nameless=0.012):
        disc, sub, div, alt = T
        assert sub in VALID_SUBS[disc], (name, T)
        assert div in VALID_DIVS, (name, T)
        # random draws always happen, so the stream does not depend on the branch taken
        r1, r2 = self.rng.random(), self.rng.random()
        if proxy and r1 < proxy:
            cls, ptype = "IfcBuildingElementProxy", None
        if nameless and r2 < nameless:
            name = None
        f = self.f
        a0 = self.aabb(items[0])
        base = tuple((a0[0] + a0[1]) / 2) if items[0][0] == "box" else tuple(items[0][1])
        sol = [self.solid(it, base) for it in items]
        rep = f.create_entity("IfcShapeRepresentation", ContextOfItems=self.body, RepresentationIdentifier="Body", RepresentationType="SweptSolid", Items=sol)
        pds = f.create_entity("IfcProductDefinitionShape", Representations=[rep])
        e = f.create_entity(cls, GlobalId=self.gid(), Name=name, Description=desc, ObjectType=objtype, ObjectPlacement=self.lp(base),
                            Representation=pds, Tag=tag)
        if ptype:
            try:
                e.PredefinedType = ptype
            except Exception:
                pass
        eid = len(self.ents)
        self.ents.append((e, cls))
        for it in items:
            mn, mx = self.aabb(it)
            self.boxes.append((mn, mx, eid))
        self.contain.setdefault(cont, []).append(e)
        if material:
            self.mat(material)[1].append(e)
        for code in ([system] if isinstance(system, str) else (system or [])):
            self.system(code)[1].append(e)
        for pname, props in (psets or {}).items():
            vals = []
            for k, v in props.items():
                if isinstance(v, bool):
                    nv = f.create_entity("IfcBoolean", v)
                elif isinstance(v, int):
                    nv = f.create_entity("IfcInteger", v)
                elif isinstance(v, float):
                    nv = f.create_entity("IfcReal", v)
                else:
                    nv = f.create_entity("IfcLabel", str(v))
                vals.append(f.create_entity("IfcPropertySingleValue", Name=k, NominalValue=nv))
            ps = f.create_entity("IfcPropertySet", GlobalId=self.gid(), Name=pname, HasProperties=vals)
            f.create_entity("IfcRelDefinesByProperties", GlobalId=self.gid(), RelatedObjects=[e], RelatingPropertyDefinition=ps)
        entry = {"name": name or "", "ifcClass": cls, "discipline": disc, "subDiscipline": sub, "division": div}
        if alt:
            entry["alt"] = alt
        self.truth[e.GlobalId] = entry
        return eid

    def ent(self, eid):
        return self.ents[eid][0]

    def opening_for(self, host, filler, c, sz, cont="site"):
        f = self.f
        base = tuple(c)
        rep = f.create_entity("IfcShapeRepresentation", ContextOfItems=self.body, RepresentationIdentifier="Body", RepresentationType="SweptSolid",
                              Items=[self.solid(("box", c, sz, 0.0), base)])
        op = f.create_entity("IfcOpeningElement", GlobalId=self.gid(), Name="Opening", ObjectPlacement=self.lp(base),
                             Representation=f.create_entity("IfcProductDefinitionShape", Representations=[rep]))
        f.create_entity("IfcRelVoidsElement", GlobalId=self.gid(), RelatingBuildingElement=self.ent(host), RelatedOpeningElement=op)
        f.create_entity("IfcRelFillsElement", GlobalId=self.gid(), RelatingOpeningElement=op, RelatedBuildingElement=self.ent(filler))
        self.contain.setdefault(cont, []).append(op)

    # ------------------------------------------------------------ pipe, duct and tray runs
    def run(self, pts, od, T, cont="site", namer=None, system=None, material=None, kind="pipe", vT=None, cT=None, support=None,
            zsup=None, maxlen=9.0, psets=None, vpfx="HV", proxy=0.0, hang_every=2, bracket_y=None):
        """A run of segments and fittings through the points. A point may carry a 4th item: 'tee', 'valve', 'ctrl', 'check', or a
        dict {cls, len, T, name, tag, ptype} for an inline device (meter, damper, VAV box). The first and last point are run ends;
        valves and devices must sit on straight stretches."""
        P = [np.array(p[:3], float) for p in pts]
        tags = [p[3] if len(p) > 3 else None for p in pts]
        n = len(P)
        w, h = (od, od) if kind == "pipe" else od
        dmax = max(w, h)
        dirs = [unit(P[i + 1] - P[i]) for i in range(n - 1)]
        hl = [0.0] * n
        roles = [None] * n
        for i in range(1, n - 1):
            t = tags[i]
            straight = np.allclose(dirs[i - 1], dirs[i])
            if isinstance(t, dict):
                assert straight, f"inline device at a corner {pts[i]}"
                hl[i] = t["len"] / 2
                roles[i] = "inline"
            elif t in ("valve", "ctrl", "check"):
                assert straight, f"valve at a corner {pts[i]}"
                hl[i] = max(0.2, 1.5 * dmax)
                roles[i] = t
            elif t == "tee":
                hl[i] = 0.7 * dmax
                roles[i] = "tee"
            elif not straight:
                hl[i] = 0.65 * dmax
                roles[i] = "elbow"
        self.run_n += 1
        rid = self.run_n
        mine = set()
        cls_seg, cls_fit = {"pipe": ("IfcPipeSegment", "IfcPipeFitting"), "duct": ("IfcDuctSegment", "IfcDuctFitting"),
                            "tray": ("IfcCableCarrierSegment", "IfcCableCarrierFitting")}[kind]
        nm = namer or (lambda role, i: {})

        def seg_item(a, b):
            if kind == "pipe":
                return ("cyl", a, b, od)
            d = unit(b - a)
            c = (a + b) / 2
            ln = float(np.linalg.norm(b - a))
            if abs(d[2]) > 0.9:
                return ("box", c, (w, h, ln), 0.0)
            if abs(d[0]) > 0.9:
                return ("box", c, (ln, w, h), 0.0)
            return ("box", c, (w, ln, h), 0.0)

        def info(role, i):
            r = nm(role, i)
            return dict(name=r.get("name"), tag=r.get("tag"), objtype=r.get("objtype"), desc=r.get("desc"))

        for i in range(n - 1):
            a = P[i] + dirs[i] * hl[i]
            b = P[i + 1] - dirs[i] * hl[i + 1]
            L_ = float(np.linalg.norm(b - a))
            if L_ < 0.02:
                continue
            k = max(1, int(math.ceil(L_ / maxlen - 1e-9)))
            for j in range(k):
                s0 = a + (b - a) * (j / k)
                s1 = a + (b - a) * ((j + 1) / k)
                eid = self.add(cls_seg, T=T, cont=cont, items=[seg_item(s0, s1)], system=system, material=material, psets=psets,
                               ptype="CABLETRAY" if kind == "tray" else "RIGIDSEGMENT", proxy=proxy, **info("seg", i))
                mine.add(eid)
                mid = (s0 + s1) / 2
                horiz = abs(dirs[i][2]) < 0.1
                if horiz and support and float(np.linalg.norm(s1 - s0)) >= 4.0 if support == "sleeper" else float(np.linalg.norm(s1 - s0)) >= 1.5:
                    along_x = abs(dirs[i][0]) > 0.9
                    if support == "sleeper":
                        bottom = mid[2] - h / 2
                        if bottom > 0.08:
                            sz = (0.3, max(0.9, w + 0.5), bottom) if along_x else (max(0.9, w + 0.5), 0.3, bottom)
                            self.add("IfcBuildingElementProxy", f"Pipe Sleeper PS-{self.rid() % 10000}", [("box", (mid[0], mid[1], bottom / 2), sz, 0.0)],
                                     SUPP, cont, objtype="Concrete sleeper", material="Concrete, Cast-in-Place gray")
                    elif support == "hang" and zsup and j % hang_every == 0:
                        top = mid[2] + h / 2
                        if zsup - top > 0.05:
                            self.add("IfcBuildingElementProxy", self.rng.choice(["Hanger - Threaded Rod 3/8\"", "Hanger Rod M10", "Support:Trapeze Hanger:%d" % self.rid()]),
                                     [("box", (mid[0], mid[1], (top + zsup) / 2), (0.04, 0.04, zsup - top), 0.0)], SUPP, cont, material="Galvanized Steel")
                    elif support == "bracket" and bracket_y and along_x:
                        y0 = mid[1] + w / 2
                        if bracket_y - y0 > 0.05:
                            self.add("IfcMember", "Tray Bracket", [("box", (mid[0], (y0 + bracket_y) / 2, mid[2]), (0.1, bracket_y - y0, 0.1), 0.0)],
                                     CND, cont, ptype="BRACE", material="Galvanized Steel")
        for i in range(1, n - 1):
            role = roles[i]
            if role is None:
                continue
            c = P[i]
            d = dirs[i]
            if role in ("elbow", "tee"):
                side = (1.3 if role == "elbow" else 1.4) * dmax
                eid = self.add(cls_fit, T=T, cont=cont, items=[("box", c, (side, side, side), 0.0)], system=system, material=material, psets=psets,
                               ptype="BEND" if role == "elbow" else "JUNCTION", proxy=proxy, **info(role, i))
                mine.add(eid)
            elif role == "inline":
                t = tags[i]
                ln = t["len"]
                if kind == "pipe":
                    items = [("cyl", c - d * ln / 2, c + d * ln / 2, max(1.6 * od, 0.2))]
                else:
                    sz = (ln, w * 1.15, h * 1.15) if abs(d[0]) > 0.9 else ((w * 1.15, ln, h * 1.15) if abs(d[1]) > 0.9 else (w * 1.15, h * 1.15, ln))
                    items = [("box", c, sz, 0.0)]
                eid = self.add(t["cls"], t.get("name"), items, t["T"], cont, ptype=t.get("ptype"), tag=t.get("tag"), objtype=t.get("objtype"),
                               desc=t.get("desc"), system=system)
                mine.add(eid)
            else:
                Lv = 2 * hl[i]
                dia = max(1.5 * od, 0.12)
                z_up = np.array([0, 0, dia / 2 + 0.3])
                items = [("cyl", c - d * Lv / 2, c + d * Lv / 2, dia), ("cyl", c, c + z_up, 0.04), ("box", c + z_up, (0.22, 0.04, 0.22), 0.0)]
                if role == "ctrl":
                    items[1] = ("cyl", c, c + np.array([0, 0, dia / 2 + 0.1]), 0.05)
                    items[2] = ("box", c + np.array([0, 0, dia / 2 + 0.2]), (0.3, 0.3, 0.3), 0.0)
                tg = self.tag({"valve": vpfx, "ctrl": "FCV", "check": "NRV"}[role])
                style = self.rng.random()
                kindtxt = {"valve": "Butterfly", "check": "Check", "ctrl": "Control"}[role]
                if style < 0.55:
                    name = tg
                elif style < 0.8:
                    name = f"Valve - {kindtxt} - {od * 39.37:.0f}\""
                else:
                    name = f"Valves:{kindtxt} Lug:{self.rid()}"
                vt = (cT or T) if role == "ctrl" else (vT or T)
                eid = self.add("IfcValve", name, items, vt, cont, tag=tg, system=system, material=material,
                               ptype="REGULATING" if role == "ctrl" else ("CHECK" if role == "check" else "ISOLATING"), proxy=0.1 if proxy else 0.0)
                mine.add(eid)
        self.runs.append((rid, [(tuple(P[0]), 0), (tuple(P[-1]), 1)], mine, [x[:3] for x in pts]))
        return mine

    # ------------------------------------------------------------ checks
    def check(self):
        errs = []
        mn = np.array([b[0] for b in self.boxes])
        mx = np.array([b[1] for b in self.boxes])
        ids = np.array([b[2] for b in self.boxes])
        tol = 0.03
        for rid, ends, mine, pts in self.runs:
            for p, _ in ends:
                p = np.array(p)
                hit = np.all(mn - tol <= p, axis=1) & np.all(mx + tol >= p, axis=1)
                if not any(i not in mine for i in ids[hit]):
                    nm = self.truth[self.ent(min(mine)).GlobalId]["name"] if mine else "?"
                    errs.append(f"run end {np.round(p, 2).tolist()} touches nothing ({nm})")
        n = len(self.ents)
        parent = list(range(n))

        def find(a):
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a
        for k in range(len(self.boxes)):
            hit = np.all(mn - tol <= mx[k], axis=1) & np.all(mx + tol >= mn[k], axis=1)
            for j in np.nonzero(hit)[0]:
                ra, rb = find(int(ids[k])), find(int(ids[j]))
                if ra != rb:
                    parent[ra] = rb
        comp = {}
        for i in range(n):
            comp.setdefault(find(i), []).append(i)
        biggest = max(comp.values(), key=len)
        floats = sorted(i for c in comp.values() if c is not biggest for i in c)
        first_box = {}
        for k, b in enumerate(self.boxes):
            first_box.setdefault(b[2], k)
        for i in floats[:40]:
            e = self.ents[i]
            errs.append(f"floating: {e[1]} '{self.truth[e[0].GlobalId]['name']}' at {np.round(self.boxes[first_box[i]][0], 1).tolist()}")
        if len(floats) > 40:
            errs.append(f"... {len(floats) - 40} more floating")
        return errs

    # ------------------------------------------------------------ write
    def finish(self, path, truth_path, name):
        f = self.f
        for cont, ents in self.contain.items():
            f.create_entity("IfcRelContainedInSpatialStructure", GlobalId=self.gid(), RelatingStructure=self.cont_ent[cont], RelatedElements=ents)
        for code, (sysent, members) in sorted(self.sysmap.items()):
            if members:
                f.create_entity("IfcRelAssignsToGroup", GlobalId=self.gid(), RelatedObjects=members, RelatingGroup=sysent)
        for mname, (ment, members) in self.matmap.items():
            if members:
                f.create_entity("IfcRelAssociatesMaterial", GlobalId=self.gid(), RelatedObjects=members, RelatingMaterial=ment)
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        f.write(path)
        doc = {"format": "xray-truth/1", "model": name,
               "generator": f"tools/make_independent_plant_ifc.py --seed {self.seed} (independent water treatment works; labels set at element creation, not in the IFC)",
               "schema": SCHEMA["edition"], "convention": CONVENTION, "elements": dict(sorted(self.truth.items()))}
        with open(truth_path, "w") as fh:
            json.dump(doc, fh, indent=1)
            fh.write("\n")


# ====================================================================== naming styles
def nm_line(g, nom, svc, num, spec):
    """Plant-design line numbers: 6"-FW-1301-A1A."""
    lab = f'{nom}"-{svc}-{num}-{spec}'
    tx = {"elbow": "ELL 90 LR", "tee": "TEE"}

    def f(role, i):
        if role == "seg":
            return dict(name=lab, objtype=f"PIPE {spec}")
        return dict(name=f'{tx.get(role, role)} {nom}" {spec}', objtype=f"{tx.get(role, role)} {spec}")
    return f


def nm_revit(g, typ):
    def f(role, i):
        if role == "seg":
            return dict(name=f"Pipe Types:{typ}:{g.rid()}", objtype=typ)
        fam = {"elbow": "Elbow - Generic", "tee": "Tee - Generic"}.get(role, role)
        return dict(name=f"{fam}:Standard:{g.rid()}", objtype="Standard")
    return f


def nm_tool(g, mat, nom):
    def f(role, i):
        if role == "seg":
            return dict(name=f'Pipe - {mat} - {nom}"')
        return dict(name=f'{ {"elbow": "Elbow", "tee": "Tee"}.get(role, role) } - {mat} - {nom}"')
    return f


def nm_plain(txt):
    def f(role, i):
        if role == "seg":
            return dict(name=txt)
        return dict(name=f'{txt} {"elbow" if role == "elbow" else "tee"}')
    return f


def nm_duct(g):
    def f(role, i):
        if role == "seg":
            return dict(name=f"Rectangular Duct:Mitered Elbows / Tees:{g.rid()}")
        return dict(name=f"Rectangular {'Elbow' if role == 'elbow' else 'Tee'}:Mitered:{g.rid()}")
    return f


def nm_tray(g, w_in):
    def f(role, i):
        if role == "seg":
            return dict(name=f'Cable Tray with Fittings:Ladder {w_in}"x4":{g.rid()}')
        return dict(name=f'Cable Tray Fitting:{"Horizontal Elbow" if role == "elbow" else "Tee"}:{g.rid()}')
    return f


def nm_conduit(g):
    def f(role, i):
        if role == "seg":
            return dict(name=f"Conduit:Rigid Nonmetallic Conduit (Sch 40 PVC):{g.rid()}")
        return dict(name=f"Conduit Fitting:Elbow - PVC:{g.rid()}")
    return f


def meter(tag_, x_len=0.6, objtype="Magmeter"):
    return {"cls": "IfcFlowMeter", "len": x_len, "T": SNS, "name": tag_, "tag": tag_, "ptype": "ELECTROMAGNETIC", "objtype": objtype}


# ====================================================================== the facility
def build(seed):
    g = G(seed)
    rng = g.rng
    g.building("Administration and Control Building", {"admin1": ("L1", 0.0), "admin2": ("L2", 4.2), "adminR": ("Roof", 8.4)})
    g.building("Filter and Pump Hall", {"hall": ("Ground Floor", 0.0)})
    g.building("Chemical Building", {"chem": ("Ground Floor", 0.0)})
    CONC = "Concrete, Cast-in-Place gray"
    CS = "Carbon Steel"
    HEAVE = 8.0

    def box(c, s, rot=0.0):
        return ("box", c, s, rot)

    def cyl(p0, p1, d):
        return ("cyl", p0, p1, d)

    def pick(*xs):
        return rng.choice(xs)

    # --------------------------------------------------------------- site civil
    SX0, SX1, SY0, SY1 = -8.0, 146.0, -8.0, 78.0
    g.add("IfcBuildingElementProxy", "Finished Grade - Compacted Gravel", [box(((SX0 + SX1) / 2, (SY0 + SY1) / 2, -0.2), (SX1 - SX0 + 4, SY1 - SY0 + 4, 0.4))],
          CIVGRADE, "site", objtype="Site Grading", material="Gravel")
    for k in range(4):
        g.add("IfcBuildingElementProxy", pick("Berm", "Embankment Fill - North", f"Earth Bund {k + 1}"), [box((10 + 35 * k, 76.6, 0.4), (30, 2.4, 0.8))],
              CIVGRADE, "site", material="Earth Fill")

    def road(name, c, sz):
        g.add("IfcSlab", name, [box(c, sz)], ROAD, "site", ptype="BASESLAB", objtype="Asphalt Paving 200mm", material="Asphalt",
              psets={"Pset_SlabCommon": {"IsExternal": True, "LoadBearing": False}})
    for i in range(8):
        road(f"Asphalt Road 6.0m - Rd-A{i + 1:02d}", (2 + i * 20, -2, 0.0), (20, 6, 0.2))
    for i in range(3):
        road(f"Asphalt Road 6.0m - Rd-B{i + 1:02d}", (-4, 6.5 + i * 17, 0.0), (6, 17, 0.2))
    for i in range(8):
        road(f"Asphalt Road 5.0m - Rd-C{i + 1:02d}", (2 + i * 20, 50.5, 0.0), (20, 5, 0.2))
    for i in range(8):
        x = 2 + i * 20
        for yk, y in ((1, 1.1), (2, 48.0)):
            g.add("IfcBuildingElementProxy", pick(f"Kerb - Precast 150x300 - K{i + 1}", "Curb Type A", f"Basic Kerb:Standard:{g.rid()}"), [box((x, y, 0.12), (20, 0.15, 0.3))],
                  KERB, "site", objtype="Precast concrete kerb", material=CONC)
    # fence: panels and posts, a gate at the west end of road A
    fx = list(np.arange(SX0, SX1 + 0.1, 19.25))
    for i in range(len(fx) - 1):
        cx = (fx[i] + fx[i + 1]) / 2
        for yy in (SY0, SY1):
            g.add("IfcBuildingElementProxy", pick("Security Fence 2.4m", f"Fence Panel FP-{i}", "Chain Link Fence"), [box((cx, yy, 1.2), (19.1, 0.06, 2.4))],
                  LND, "site", objtype="Welded mesh panel", material="Galvanized Steel")
            g.add("IfcBuildingElementProxy", pick("Fence Post", "Post 80x80 SHS", f"Posts:Fence Post:{g.rid()}"), [box((fx[i], yy, 1.25), (0.1, 0.1, 2.5))], LND, "site",
                  material="Galvanized Steel")
    for yy in (SY0, SY1):
        g.add("IfcBuildingElementProxy", "Fence Post", [box((fx[-1], yy, 1.25), (0.1, 0.1, 2.5))], LND, "site", material="Galvanized Steel")
    fy = list(np.arange(SY0, SY1 + 0.1, 21.5))
    for i in range(len(fy) - 1):
        cy = (fy[i] + fy[i + 1]) / 2
        for xx in (SX0, SX1):
            if xx == SX0 and abs(cy + 2) < 6.0:
                continue
            g.add("IfcBuildingElementProxy", pick("Security Fence 2.4m", f"Fence Panel FP-W{i}", "Chain Link Fence"), [box((xx, cy, 1.2), (0.06, 21.4, 2.4))],
                  LND, "site", objtype="Welded mesh panel", material="Galvanized Steel")
            g.add("IfcBuildingElementProxy", pick("Fence Post", "Post 80x80 SHS"), [box((xx, fy[i], 1.25), (0.1, 0.1, 2.5))], LND, "site", material="Galvanized Steel")
    g.add("IfcDoor", "Sliding Gate 6m", [box((SX0, -2.0, 1.1), (0.15, 6.0, 2.2))], LND, "site", ptype="GATE", objtype="Gate - Sliding", material="Galvanized Steel")
    for yy in (-5.1, 1.1):
        g.add("IfcBuildingElementProxy", "Gate Post", [box((SX0, yy, 1.25), (0.2, 0.2, 2.5))], LND, "site", material="Galvanized Steel")
    for i in range(9):
        x = 2 + i * 16
        g.add("IfcGeographicElement", pick(f"Tree - Eucalyptus {i + 1}", "Planting:Tree:%d" % g.rid(), "Eucalyptus"),
              [cyl((x, 73.5, 0.0), (x, 73.5, 3.0), 0.35), cyl((x, 73.5, 3.0), (x, 73.5, 7.5), 4.0)], LND, "site", ptype="TREE")

    def manhole(name, x, y, T=SDRN, d=1.2):
        return g.add("IfcBuildingElementProxy", name, [cyl((x, y, -2.2), (x, y, 0.1), d)], T, "site", objtype="Precast manhole 1200", material=CONC)

    for line, y, nmh in (("S1", 4.0, 7), ("S2", 70.0, 4)):
        xs = [8 + 22 * k for k in range(nmh)]
        for k, x in enumerate(xs):
            manhole(f"MH-{line}{k + 1:02d}", x, y)
        for k in range(nmh - 1):
            g.run([(xs[k], y, -1.5), (xs[k + 1], y, -1.5)], dn(300), SDRN, "site", nm_plain("Storm 300 PVC"), system="SWD", maxlen=12.0)

    def chamber(name, x, y):
        g.add("IfcBuildingElementProxy", name, [box((x, y, -0.9), (2.4, 2.4, 2.2))], SUTL, "site", objtype="Valve chamber", material=CONC)
    chamber("Tie-in Chamber TC-1", -6.0, 30)
    chamber("Valve Chamber VC-RW", 6.0, 30)
    g.run([(-6.0, 30, -1.4), (-3.0, 30, -1.4, "valve"), (6.0, 30, -1.4)], dn(600), SUTL, "site", nm_tool(g, "Ductile Iron", 24), system="RW", vT=SUTL, vpfx="GV")
    chamber("Fire Water Tie-in Chamber FC-1", 58.0, 47)
    chamber("Valve Chamber FC-2", 118.0, 47)
    hx = [64, 80, 96, 112]
    g.run([(58, 47, -1.2), (60.5, 47, -1.2, "valve"), (64, 47, -1.2, "tee"), (80, 47, -1.2, "tee"), (87, 47, -1.2, "tee"), (96, 47, -1.2, "tee"), (112, 47, -1.2, "tee"),
           (118, 47, -1.2)], dn(200), SUTL, "site", nm_plain("Fire Main DN200 DI"), system="FM", vT=SUTL, vpfx="GV")
    for k, x in enumerate(hx):
        g.add("IfcFireSuppressionTerminal", pick(f"Hydrant H-{k + 1:02d}", f"Fire Hydrant {k + 1}", f"FH-{k + 1}"), [cyl((x, 47, 0.0), (x, 47, 1.0), 0.3)], STP, "site",
              ptype="FIREHYDRANT", material="Ductile Iron")
        g.run([(x, 47, -1.2), (x, 47, 0.5)], dn(100), STP, "site", nm_plain("Hydrant Lead DN100"), system="FM")

    # --------------------------------------------------------------- shared builders
    def plinth(c, size, T=FNDO, cont="site", name=None):
        return g.add("IfcFooting", name or pick("Equipment Plinth", f"Pad PD-{g.rid() % 1000}", "Footing:Pad:%d" % g.rid()),
                     [box((c[0], c[1], -0.15), (size[0], size[1], 0.3))], T, cont, ptype="PAD_FOOTING", material=CONC)

    def pump(c, tag, T=PMP, cont="site", fnd=FNDO, system=None):
        cx, cy = c
        plinth((cx, cy), (2.4, 1.3), fnd, cont)
        style = rng.random()
        pname = tag if style < 0.5 else (f"Pump - {tag}" if style < 0.75 else f"Centrifugal Pump:{tag}:{g.rid()}")
        g.add("IfcPump", pname, [box((cx, cy, 0.1), (2.0, 0.9, 0.2)), box((cx - 0.55, cy, 0.55), (0.7, 0.7, 0.7))], T, cont, ptype="ENDSUCTION", tag=tag, system=system,
              material="Cast Iron", proxy=0.1, desc=pick(None, "Centrifugal pump", None),
              psets=pick({"Pset_PumpCommon": {"Reference": tag, "Status": "NEW"}}, {"Vendor Data": {"Mark": tag, "Model": "SX-%d" % rng.randint(100, 900)}}))
        g.add("IfcElectricMotor", pick(f"M-{tag.split('-', 1)[-1]}", f"Motor for {tag}"), [cyl((cx - 0.25, cy, 0.6), (cx + 0.9, cy, 0.6), 0.5)],
              MOTOR, cont, ptype="INDUCTION", system=system, proxy=0.1, material="Cast Iron")

    def sensor(pt, kind, cont="site", tag=None, system=None, up=0.35, T=SNS):
        x, y, z = pt
        t = tag or g.tag(kind)
        words = {"FIT": "Flow Transmitter", "LIT": "Level Transmitter", "PIT": "Pressure Transmitter", "AIT": "Analyzer", "TIT": "Temperature Transmitter",
                 "PDIT": "Differential Pressure Transmitter"}
        style = rng.random()
        nme = t if style < 0.6 else (f"{words.get(kind, 'Instrument')} {t}" if style < 0.85 else f"Instrument:{kind}:{g.rid()}")
        pt_ = {"LIT": "LEVELSENSOR", "PIT": "PRESSURESENSOR", "PDIT": "PRESSURESENSOR", "TIT": "TEMPERATURESENSOR", "AIT": "USERDEFINED", "FIT": "FLOWSENSOR"}.get(kind)
        g.add("IfcSensor", nme, [box((x, y, z + up / 2), (0.16, 0.16, up + 0.02))], T, cont, ptype=pt_, tag=t, system=system, proxy=0.12, nameless=0.05,
              psets=pick(None, {"Pset_SensorTypeCommon": {"Reference": t}}, {"Vendor": {"TagNo": t, "Loop": t[-4:]}}))

    def basin(name, x0, y0, x1, y1, h=3.5, th=0.3):
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        g.add("IfcSlab", f"{name} Floor", [box((cx, cy, -0.35), (x1 - x0, y1 - y0, 0.3))], SLB, "site", ptype="BASESLAB", material=CONC, objtype="Slab 12 in",
              psets=pick(None, {"Pset_SlabCommon": {"IsExternal": True, "LoadBearing": True}}))
        zc = (h - 0.5) / 2
        for nm_, c, s in (("S", (cx, y0 + th / 2, zc), (x1 - x0, th, h + 0.5)), ("N", (cx, y1 - th / 2, zc), (x1 - x0, th, h + 0.5)),
                          ("W", (x0 + th / 2, cy, zc), (th, y1 - y0, h + 0.5)), ("E", (x1 - th / 2, cy, zc), (th, y1 - y0, h + 0.5))):
            g.add("IfcWall", pick(f"{name} Wall {nm_}", f"Basic Wall:Concrete 300mm:{g.rid()}", f"Retaining Wall RW-{nm_}"), [box(c, s)], WLS, "site",
                  ptype="SOLIDWALL", material=CONC, objtype="Concrete 300mm", psets={"Pset_WallCommon": {"IsExternal": True, "LoadBearing": True}})

    # --------------------------------------------------------------- rapid mix and the chemical building
    plinth((14, 30), (3.6, 3.6), FNDO, "site", "Tank Ring Foundation")
    g.add("IfcTank", pick("TK-1201 Rapid Mix", "Rapid Mix Tank", "Tank:Steel Tank:%d" % g.rid()), [cyl((14, 30, 0.0), (14, 30, 4.0), 3.0)], VES46, "site",
          ptype="PREFORMED", tag="TK-1201", material="Carbon Steel", system="RW", psets={"Vendor Data": {"Volume": "28 m3"}})
    g.add("IfcBuildingElementProxy", "Rapid Mixer MX-1201", [box((14, 30, 4.3), (1.0, 0.6, 0.6)), cyl((14, 30, 1.0), (14, 30, 4.0), 0.1), box((14, 30, 1.2), (1.4, 0.15, 0.1))],
          EQP46, "site", tag="MX-1201", objtype="Mixer", material="Stainless Steel 316L", system="RW")
    g.run([(6.0, 30, 0.0), (6.0, 30, 1.0), (13.0, 30, 1.0)], nps(24), PRC, "site", nm_line(g, 24, "RW", 1101, "A1A"), system="RW", material=CS, support="sleeper",
          psets={"Plant3D": {"LineNumber": "24-RW-1101-A1A", "Spec": "A1A"}})
    sensor((9.0, 30, 1.0 + nps(24) / 2), "FIT", "site", tag="FIT-1101", system="RW", up=0.5)
    sensor((10.0, 30, 1.0 + nps(24) / 2), "AIT", "site", tag="AIT-1101", system="RW", up=0.5)

    cy0, cy1 = 6.0, 16.0
    g.add("IfcSlab", "Chemical Building Floor Slab", [box((13, 11, -0.15), (14, 10, 0.3))], SLB, "chem", ptype="BASESLAB", material=CONC, objtype="Slab on grade 6 in")
    for nm_, c, s in (("S", (13, cy0 + 0.125, 2.25), (14, 0.25, 4.5)), ("N", (13, cy1 - 0.125, 2.25), (14, 0.25, 4.5)),
                      ("W", (6.125, 11, 2.25), (0.25, 10, 4.5)), ("E", (19.875, 11, 2.25), (0.25, 10, 4.5))):
        wid = g.add("IfcWall", pick(f"Basic Wall:Exterior - CMU 10in:{g.rid()}", f"Chem Bldg Wall {nm_}"), [box(c, s)], WALX, "chem", ptype="STANDARD",
                    material="Concrete Masonry Unit", objtype="Exterior - CMU 10in", psets={"Pset_WallCommon": {"IsExternal": True, "FireRating": "2HR"}})
        if nm_ == "S":
            did = g.add("IfcDoor", "Single-Flush:36\" x 84\":%d" % g.rid(), [box((9, cy0 + 0.125, 1.05), (0.9, 0.12, 2.1))], DOR, "chem", ptype="DOOR", material="Steel, Painted",
                        psets={"Pset_DoorCommon": {"FireExit": True}})
            g.opening_for(wid, did, (9, cy0 + 0.125, 1.05), (0.95, 0.4, 2.15), cont="chem")
            wn = g.add("IfcWindow", "Window - Fixed - 4'-0\" x 3'-0\"", [box((15, cy0 + 0.125, 2.2), (1.2, 0.1, 0.9))], WIN, "chem", ptype="WINDOW", material="Aluminium",
                       psets={"Pset_WindowCommon": {"IsExternal": True}})
            g.opening_for(wid, wn, (15, cy0 + 0.125, 2.2), (1.25, 0.4, 0.95), cont="chem")
        if nm_ == "N":
            lv = g.add("IfcWindow", "Louver 24x24", [box((17, cy1 - 0.125, 3.2), (0.6, 0.1, 0.6))], WIN, "chem", ptype="WINDOW", objtype="Louver", material="Aluminium")
            g.opening_for(wid, lv, (17, cy1 - 0.125, 3.2), (0.65, 0.4, 0.65), cont="chem")
    g.add("IfcRoof", "Roof - Concrete Slab 8in", [box((13, 11, 4.6), (14.4, 10.4, 0.2))], ROF, "chem", ptype="FLAT_ROOF", material=CONC, objtype="Flat roof")
    for x in (6.6, 13, 19.4):
        g.add("IfcFooting", f"Strip Footing SF-{int(x)}", [box((x, 11, -0.5), (0.6, 10.4, 0.4))], FNDI, "chem", ptype="STRIP_FOOTING", material=CONC)
    plinth((27, 11.5), (8.0, 12.0), FNDO, "site", "Bund Floor Slab")
    for nm_, c, s in (("W", (23.15, 11.5, 0.6), (0.3, 12.0, 1.2)), ("E", (30.85, 11.5, 0.6), (0.3, 12.0, 1.2)),
                      ("S", (27, 5.65, 0.6), (8.0, 0.3, 1.2)), ("N", (27, 17.35, 0.6), (8.0, 0.3, 1.2))):
        g.add("IfcWall", f"Bund Wall {nm_}", [box(c, s)], WLS, "site", ptype="SOLIDWALL", material=CONC, objtype="Concrete 300mm")
    chems = [("Alum", "AL", 8.0, "T-1601", 1.5), ("Polymer", "PA", 11.5, "T-1602", 1), ("Sodium Hypochlorite", "HY", 15.0, "T-1603", 1.5)]
    dis_x = {"AL": 12.0, "PA": 10.5, "HY": 9.0}
    inj = {"AL": (14.8, 26.0), "PA": (14.0, 27.0), "HY": (13.0, 28.0)}
    for k, (cname, svc, yc, tk, sz) in enumerate(chems):
        g.add("IfcTank", pick(f"{tk} {cname}", f"{cname} Storage Tank", f"Tank:HDPE {cname}:{g.rid()}"), [cyl((27, yc, 0.0), (27, yc, 4.0), 3.0)], VES43, "site",
              ptype="STORAGE", tag=tk, material="HDPE", system=svc, psets={"Vendor Data": {"Content": cname}})
        pys = (yc - 0.6, yc + 0.6) if svc == "AL" else (yc,)
        for j, py in enumerate(pys):
            pt = f"DP-16{k + 1}{'AB'[j]}" if svc == "AL" else f"DP-16{k + 1}"
            plinth((17.0, py), (1.4, 0.7), FNDI, "chem", f"Pump Base {pt}")
            g.add("IfcPump", pt if rng.random() < 0.6 else f"Dosing Pump {pt}", [box((17.0, py, 0.45), (0.9, 0.4, 0.9))], PMP, "chem", ptype="ENDSUCTION", tag=pt,
                  system=svc, proxy=0.15, material="Stainless Steel 316L")
        od = nps(sz)
        g.run([(25.6, yc, 0.8), (18.0, yc, 0.8)], od, PRC, "chem", nm_line(g, sz, svc, 1601 + k, "PVC"), system=svc, material="PVC-U",
              psets={"Plant3D": {"LineNumber": f'{sz}"-{svc}-{1601 + k}-PVC', "Service": cname}})
        for py in pys:
            g.run([(18.0, yc, 0.8), (18.0, py, 0.8), (17.0, py, 0.8)], nps(1), PRC, "chem", nm_line(g, 1, svc, 1601 + k, "PVC"), system=svc, material="PVC-U")
            g.run([(17.0, py, 0.5), (17.0, py, 1.6)], nps(1), PRC, "chem", nm_line(g, 1, svc, 1631 + k, "PVC"), system=svc, material="PVC-U")
        if len(pys) == 2:
            g.run([(17.0, pys[0], 1.6), (17.0, yc, 1.6, "tee"), (17.0, pys[1], 1.6)], nps(1), PRC, "chem", nm_line(g, 1, svc, 1631 + k, "PVC"), system=svc, material="PVC-U")
        dx = dis_x[svc]
        ix, iy = inj[svc]
        g.run([(17.0, yc, 1.6), (dx + 1.0, yc, 1.6, "valve"), (dx, yc, 1.6), (dx, iy, 1.6), (ix, iy, 1.6), (ix, 29.0, 1.6)], nps(1), PRC, "site",
              nm_line(g, 1, svc, 1661 + k, "PVC"), system=svc, material="PVC-U", vT=VLV, vpfx="XV")
    g.add("IfcFan", "EF-1601 Exhaust Fan", [cyl((17, 11, 4.7), (17, 11, 5.3), 0.8)], MEQP, "chem", ptype="CENTRIFUGALAIRFOIL", tag="EF-1601", system="EA-02", material="Galvanized Steel")
    g.add("IfcAirTerminal", "Exhaust Grille 12x12", [box((17, 11, 3.9), (0.4, 0.4, 0.2))], TRM, "chem", ptype="GRILLE", system="EA-02")
    g.run([(17, 11, 4.0), (17, 11, 4.7)], (0.3, 0.3), DUCT, "chem", nm_duct(g), system="EA-02", kind="duct", material="Galvanized Steel")
    g.add("IfcSanitaryTerminal", pick("Emergency Shower / Eyewash ES-1", "Plumbing Fixture:Eyewash:%d" % g.rid()), [box((6.9, 12.0, 0.9), (0.6, 0.6, 1.8))], PFIX, "chem",
          ptype="SHOWER", system="DCW", tag="ES-1")
    chamber("Potable Water Chamber PWC-1", 3.5, 10)
    g.run([(3.5, 10, -1.0), (6.9, 10, -1.0), (6.9, 10, -0.2, "valve"), (6.9, 10, 0.5), (6.9, 11.8, 0.5)], dn(25), PSUP, "chem", nm_plain("Potable Water DN25 Copper"), system="DCW",
          material="Copper", vT=PVLV)
    g.add("IfcSanitaryTerminal", "Wash Sink SK-1", [box((6.6, 15.1, 0.45), (0.8, 0.6, 0.9))], PFIX, "chem", ptype="SINK", system="DCW", tag="SK-1")
    g.run([(3.5, 10.3, -1.0), (3.5, 15.1, -1.0), (6.5, 15.1, -1.0), (6.5, 15.1, 0.6)], dn(20), PSUP, "chem", nm_plain("Potable Water DN20 Copper"), system="DCW", material="Copper")
    g.add("IfcElectricDistributionBoard", "MCC-2", [box((19.4, 8.0, 1.1), (0.8, 1.4, 2.2))], PWR, "chem", ptype="MOTORCONTROLCENTRE", tag="MCC-2", system="PWR-B")

    # --------------------------------------------------------------- flocculation and sedimentation
    basin("Flocculation Basin FB-1", 24.0, 26.0, 36.0, 34.0, h=3.5)
    g.run([(15.2, 30, 1.0), (24.1, 30, 1.0)], nps(20), PRC, "site", nm_line(g, 20, "FC", 1201, "A1A"), system="FC", material=CS, support="sleeper")
    for k, x in enumerate((28, 32)):
        g.add("IfcBuildingElementProxy", f"Flocculator FL-120{k + 1}", [cyl((x, 30, -0.3), (x, 30, 3.6), 0.3), box((x, 30, 2.0), (2.4, 0.2, 0.15)), box((x, 30, 1.0), (2.4, 0.2, 0.15)),
                                                                       box((x, 30, 3.8), (0.8, 0.6, 0.4))], EQP46, "site", tag=f"FL-120{k + 1}", objtype="Paddle Flocculator", material="Stainless Steel 316L")
    g.run([(35.9, 30, 1.0), (41.0, 30, 1.0)], nps(20), PRC, "site", nm_line(g, 20, "FC", 1202, "A1A"), system="FC", material=CS, support="sleeper")
    for k, yb in enumerate((18.0, 42.0)):
        basin(f"Sedimentation Basin SB-{k + 1}", 46.0, yb - 4, 66.0, yb + 4, h=4.0)
        for j, lx in enumerate((50, 54, 58, 62)):
            g.add("IfcBuildingElementProxy", pick(f"Launder {j + 1}", f"Effluent Launder SB{k + 1}-{j + 1}"), [box((lx, yb, 3.0), (0.5, 7.6, 0.4))], EQP46, "site",
                  objtype="Launder trough", material="Stainless Steel 304")
        g.add("IfcBuildingElementProxy", f"Scraper Bridge SC-{k + 1}", [box((56, yb, 4.15), (0.8, 8.2, 0.3)), box((56, yb - 3.9, 4.45), (1.2, 0.6, 0.6))], EQP46, "site",
              tag=f"SC-{k + 1}", objtype="Travelling bridge scraper", material=CS)
        for s in (-3.95, 3.95):
            g.add("IfcRailing", pick("Handrail - Pipe 1.1m", f"Railing:Handrail:{g.rid()}"), [box((56, yb + s, 4.8), (1.0, 0.05, 1.0))], STAIR, "site", ptype="HANDRAIL", material="Galvanized Steel")
        g.run([(41.0, 30, 1.0), (41.0, yb, 1.0), (46.1, yb, 1.0)], nps(14), PRC, "site", nm_line(g, 14, "FC", 1203 + k, "A1A"), system="FC", material=CS, support="sleeper")
        g.run([(65.9, yb, 1.0), (70, yb, 1.0), (70, 30, 1.0)], nps(14), PRC, "site", nm_revit(g, "Carbon Steel - Welded") if k else nm_line(g, 14, "SD", 1205 + k, "A1A"),
              system="SD", material=CS, support="sleeper")
        sensor((65.75, yb + 3.0, 4.0), "LIT", "site", system="SD", up=0.4)
    sensor((41.0, 24.0, 1.0 + nps(14) / 2), "AIT", "site", system="FC", up=0.4)

    # --------------------------------------------------------------- filter and pump hall: steel frame
    HX0, HX1, HY0, HY1 = 74.0, 112.0, 18.0, 42.0
    bays = 6
    bx = [HX0 + i * (HX1 - HX0) / bays for i in range(bays + 1)]
    g.add("IfcSlab", "Hall Floor Slab", [box(((HX0 + HX1) / 2, (HY0 + HY1) / 2, -0.15), (HX1 - HX0, HY1 - HY0, 0.3))], SLB, "hall", ptype="FLOOR", material=CONC,
          objtype="Floor slab 8 in", psets={"Pset_SlabCommon": {"IsExternal": False, "LoadBearing": True}})
    for i, x in enumerate(bx):
        for y in (HY0, HY1):
            sd = "S" if y == HY0 else "N"
            g.add("IfcColumn", pick("Column W12x26", "Structural Columns:W-Wide Flange-Column:W12x26:%d" % g.rid(), f"C-{i}{sd}"), [box((x, y, HEAVE / 2), (0.3, 0.3, HEAVE))], COL05, "hall",
                  ptype="COLUMN", objtype="W12x26", material="Steel, Carbon")
            g.add("IfcPlate", pick("Base Plate 16x16x1", "Plate:Base Plate:%d" % g.rid()), [box((x, y, 0.02), (0.45, 0.45, 0.04))], BRC05, "hall", ptype="BASE_PLATE", material="Steel, Carbon")
            g.add("IfcFooting", f"Pad Footing PF-{i}{sd}", [box((x, y, -0.6), (1.4, 1.4, 0.6))], FNDI, "hall", ptype="PAD_FOOTING", material=CONC)
        g.add("IfcBeam", pick("Rafter W10x33", "Structural Framing:W-Wide Flange:W10x33:%d" % g.rid(), f"RF-{i}"), [box((x, (HY0 + HY1) / 2, HEAVE + 0.2), (0.3, HY1 - HY0, 0.4))], BEM05, "hall",
              ptype="BEAM", objtype="W10x33", material="Steel, Carbon")
    for i in range(bays):
        xm = (bx[i] + bx[i + 1]) / 2
        wb = bx[i + 1] - bx[i]
        for y in (HY0, HY1):
            g.add("IfcBeam", pick(f"Eave Beam {i}", "Eave Strut C10x15", f"Structural Framing:C-Channel:C10x15:{g.rid()}"), [box((xm, y, HEAVE - 0.1), (wb, 0.2, 0.2))], BEM05, "hall",
                  ptype="BEAM", objtype="C10x15", material="Steel, Carbon")
            for zg in (4.0,):
                g.add("IfcMember", pick("Wall Girt Z8x2.5", f"Girt {i}", "Girts:Z-Purlin:%d" % g.rid()), [box((xm, y, zg), (wb, 0.1, 0.2))], BEM05, "hall", ptype="STRINGER",
                      objtype="Z8x2.5", material="Steel, Galvanized")
        for yp in (24.0, 32.0, 40.0):
            g.add("IfcMember", pick("Roof Purlin Z8x2.5", f"Purlin {i}", "Purlins:Z-Purlin:%d" % g.rid()), [box((xm, yp, HEAVE + 0.5), (wb, 0.1, 0.2))], BEM05, "hall",
                  ptype="PURLIN", objtype="Z8x2.5", material="Steel, Galvanized")
        for yp in (22.0, 30.0, 38.0):
            g.add("IfcCovering", pick("Roof Sheeting 0.8mm", f"Roof Panel RP-{i}-{int(yp)}", "Roof:Metal Deck:%d" % g.rid()), [box((xm, yp, HEAVE + 0.65), (wb, 8.0, 0.08))], ROF, "hall",
                  ptype="ROOFING", material="Steel, Galvanized", objtype="Standing seam")
    for k, (xa, xb, y) in enumerate(((bx[0], bx[1], HY0), (bx[5], bx[6], HY0), (bx[0], bx[1], HY1), (bx[5], bx[6], HY1))):
        g.add("IfcMember", f"Diagonal Brace {k + 1}", [cyl((xa, y, 0.3), (xb, y, HEAVE - 0.3), 0.08)], BRC05, "hall", ptype="BRACE", objtype="L4x4x1/4", material="Steel, Carbon")
    for k in range(3):
        g.add("IfcMember", f"Roof Brace {k + 1}", [cyl((bx[2 * k], HY0, HEAVE + 0.2), (bx[2 * k + 1], 30.0, HEAVE + 0.2), 0.05)], BRC05, "hall", ptype="BRACE", material="Steel, Carbon")
    for y in (HY0 + 1.0, HY1 - 1.0):
        for i in range(bays):
            g.add("IfcBeam", "Crane Runway Beam W16x40", [box(((bx[i] + bx[i + 1]) / 2, y, 6.2), (bx[i + 1] - bx[i], 0.25, 0.4))], BEM05, "hall", ptype="BEAM", material="Steel, Carbon")
        for x in (bx[0], bx[3], bx[6]):
            g.add("IfcMember", "Crane Bracket", [box((x, y + (-0.5 if y < 30 else 0.5), 5.9), (0.3, 1.0, 0.3))], BEM05, "hall", ptype="BRACE", material="Steel, Carbon")
    g.add("IfcTransportElement", pick("Overhead Crane 5t", "Bridge Crane CR-1"), [box((90, 30, 6.65), (0.5, 22.0, 0.6)), box((90, 30, 6.35), (2.0, 1.0, 0.4))], CONV, "hall",
          ptype="CRANEWAY", tag="CR-1", material="Steel, Carbon")
    # cladding with openings
    for i in range(bays):
        xm = (bx[i] + bx[i + 1]) / 2
        for y, sd in ((HY0, "S"), (HY1, "N")):
            yy = y + (0.1 if sd == "S" else -0.1)
            wid = g.add("IfcWall", pick(f"Wall Cladding {sd}{i}", f"Basic Wall:Insulated Metal Panel:{g.rid()}", "Metal Wall Panel"), [box((xm, yy, 4.0), (bx[i + 1] - bx[i], 0.15, 8.0))],
                        CLAD, "hall", ptype="STANDARD", material="Steel, Galvanized", objtype="Insulated Metal Panel 3in", psets=pick(None, {"Pset_WallCommon": {"IsExternal": True}}))
            if i % 2 == 1:
                wn = g.add("IfcWindow", pick("Clerestory Window 5'x3'", f"Window:Fixed:{g.rid()}"), [box((xm, yy, 6.0), (1.6, 0.1, 1.0))], WIN, "hall", ptype="WINDOW", material="Aluminium")
                g.opening_for(wid, wn, (xm, yy, 6.0), (1.65, 0.4, 1.05), cont="hall")
            elif i in (2, 6):
                lv = g.add("IfcWindow", pick("Louver 48x24", f"Louvers:Wall Louver:{g.rid()}"), [box((xm, yy, 6.4), (1.2, 0.1, 0.6))], WIN, "hall", ptype="WINDOW", objtype="Louver", material="Aluminium")
                g.opening_for(wid, lv, (xm, yy, 6.4), (1.25, 0.4, 0.65), cont="hall")
    for x, sd in ((HX0, "W"), (HX1, "E")):
        for k in range(4):
            yc_ = HY0 + 3.0 + 6.0 * k
            xx = x + (0.1 if sd == "W" else -0.1)
            wid = g.add("IfcWall", pick(f"End Wall Cladding {sd}{k}", f"Basic Wall:Insulated Metal Panel:{g.rid()}"), [box((xx, yc_, 4.0), (0.15, 6.0, 8.0))], CLAD, "hall", ptype="STANDARD",
                        material="Steel, Galvanized", objtype="Insulated Metal Panel 3in")
            if k in (1, 3) or (sd == "W" and k == 2):
                big = sd == "W" and k == 2
                zc = 2.0 if big else 1.05
                sz = (0.1, 3.6, 4.0) if big else (0.1, 0.9, 2.1)
                dr = g.add("IfcDoor", "Roller Shutter Door 12'x14'" if big else f"Single-Flush:36\" x 84\":{g.rid()}", [box((xx, yc_, zc), sz)], DOR, "hall", ptype="DOOR",
                           material="Steel, Painted", objtype="Roller Shutter" if big else "Single-Flush")
                g.opening_for(wid, dr, (xx, yc_, zc), (0.4, sz[1] + 0.05, sz[2] + 0.05), cont="hall")
    for x in (80, 96, 108):
        g.add("IfcFan", f"Roof Ventilator RV-{int(x)}", [cyl((x, 30, HEAVE + 0.7), (x, 30, HEAVE + 1.6), 1.0)], MEQP, "hall", ptype="PROPELLORAXIAL", tag=f"EF-14{int(x) % 100}", material="Steel, Galvanized")
    for k in range(8):
        x = 76 + k * 5.2
        yl = 24.0 if k % 2 else 32.0
        g.add("IfcLightFixture", pick(f"High Bay LED {k + 1}", f"Light Fixture:Highbay:{g.rid()}", f"LT-{k + 1}"), [box((x, yl, 7.9), (0.6, 0.6, 0.3)), box((x, yl, 8.175), (0.1, 0.1, 0.55))],
              LTG, "hall", ptype="POINTSOURCE", system="LTG-H")

    # --------------------------------------------------------------- hall process: settled water in, filters, headers
    g.run([(70, 30, 1.0), (73.0, 30, 1.0, meter("FIT-1301", 0.7)), (75.5, 30, 1.0), (75.5, 24, 1.0), (75.5, 24, 5.0), (80.0, 24, 5.0, "tee"), (86.0, 24, 5.0, "tee"),
           (92.0, 24, 5.0, "tee"), (98.0, 24, 5.0)], nps(20), PRC, "hall", nm_line(g, 20, "SD", 1301, "A1A"), system="SD", material=CS, support="hang", zsup=HEAVE + 0.4, hang_every=1)
    fxs = [80.0, 86.0, 92.0, 98.0]
    for k, x in enumerate(fxs):
        letter = "ABCD"[k]
        plinth((x, 30), (3.4, 3.4), FNDI, "hall", f"Filter Plinth {letter}")
        g.add("IfcTank", pick(f"F-130{k + 1}{letter}", f"Pressure Filter F-130{k + 1}", "Tank:Filter Vessel:%d" % g.rid()), [cyl((x, 30, 0.0), (x, 30, 4.3), 2.8)], VES46, "hall",
              ptype="PREFORMED", tag=f"F-130{k + 1}", material="Carbon Steel", system="FW", psets={"Vendor Data": {"MediaDepth": "36 in"}})
        g.run([(x, 24, 5.0), (x, 30, 5.0), (x, 30, 4.2)], nps(10), PRC, "hall", nm_line(g, 10, "SD", 1311 + k, "A1A"), system="SD", material=CS, support="hang", zsup=HEAVE + 0.4, hang_every=1)
        g.run([(x, 30, 0.8), (x, 32.0, 0.8, meter(f"FIT-132{k + 1}", 0.5)), (x, 33.5, 0.8, "ctrl"), (x, 36, 0.8)], nps(8), PRC, "hall", nm_line(g, 8, "FW", 1321 + k, "A1A"), system="FW",
              material=CS, cT=CTRLV, vpfx="FCV", support="sleeper")
        g.run([(x, 32.0, 2.0), (x, 31.0, 2.0)], nps(4), UTL, "hall", nm_line(g, 4, "AS", 1331 + k, "A1A"), system="AS", material=CS)
        g.run([(x - 0.9, 19.5, 0.8), (x - 0.9, 30.0, 0.8)], nps(8), PRC, "hall", nm_line(g, 8, "BW", 1341 + k, "A1A"), system="BW", material=CS, support="sleeper")
        g.run([(x + 0.9, 30.0, 3.5), (x + 0.9, 40.0, 3.5)], nps(8), PRC, "hall", nm_line(g, 8, "BWW", 1351 + k, "A1A"), system="BWW", material=CS)
        sensor((x + 1.45, 30.0, 2.0), "PDIT", "hall", system="FW", up=0.3)
        sensor((x, 30.0, 4.3), "LIT", "hall", system="FW")
    g.run([(80.0, 36, 0.8), (86.0, 36, 0.8, "tee"), (92.0, 36, 0.8, "tee"), (98.0, 36, 0.8, "tee"), (105.0, 36, 0.8, meter("FIT-1401", 0.7)), (116.1, 36, 0.8)], nps(14), PRC, "hall",
          nm_line(g, 14, "FW", 1401, "A1A"), system="FW", material=CS, support="sleeper")
    sensor((101.5, 36, 0.8 + nps(14) / 2), "AIT", "hall", tag="AIT-1401", system="FW", up=0.4)
    sensor((95.0, 36, 0.8 + nps(14) / 2), "AIT", "hall", system="FW", up=0.4)
    # air scour header (y=32) with blowers
    g.run([(108.0, 32.0, 2.0), (104.0, 32.0, 2.0, "tee"), (98.0, 32.0, 2.0, "tee"), (92.0, 32.0, 2.0, "tee"), (86.0, 32.0, 2.0, "tee"), (80.0, 32.0, 2.0)], nps(6), UTL, "hall",
          nm_line(g, 6, "AS", 1330, "A1A"), system="AS", material=CS, support="hang", zsup=HEAVE + 0.4, hang_every=2)
    for k, x in enumerate((104.0, 108.0)):
        plinth((x + 0.4, 38.0), (3.0, 1.4), FNDI, "hall", f"Blower Base B{k + 1}")
        g.add("IfcCompressor", pick(f"B-140{k + 1}", f"Air Scour Blower B-140{k + 1}", f"Blower:Rotary Lobe:{g.rid()}"), [box((x, 38.0, 0.6), (1.6, 0.9, 1.1))], PMP, "hall", ptype="ROTARY",
              tag=f"B-140{k + 1}", system="AS", proxy=0.1, material="Cast Iron")
        g.add("IfcElectricMotor", f"M-140{k + 1}", [box((x + 1.0, 38.0, 0.5), (0.7, 0.6, 0.8))], MOTOR, "hall", ptype="INDUCTION", system="AS", material="Cast Iron")
        g.run([(x, 38.0, 0.9), (x, 38.0, 2.0), (x, 32.0, 2.0)], nps(6), UTL, "hall", nm_line(g, 6, "AS", 1340 + k, "A1A"), system="AS", material=CS)
    # backwash pumps and headers
    for k, x in enumerate((103.0, 107.0)):
        pump((x, 21.0), f"P-141{k + 1}", PMP, "hall", FNDI, "BW")
    g.run([(116.1, 24.5, 0.5), (106.45, 24.5, 0.5, "tee"), (102.45, 24.5, 0.5)], nps(10), PRC, "hall", nm_line(g, 10, "BW", 1411, "A1A"), system="BW", material=CS, support="sleeper")
    for x in (106.45, 102.45):
        g.run([(x, 24.5, 0.5), (x, 21.3, 0.5)], nps(8), PRC, "hall", nm_line(g, 8, "BW", 1412, "A1A"), system="BW", material=CS)
    g.run([(106.45, 21.0, 0.8), (106.45, 19.5, 0.8), (102.45, 19.5, 0.8)], nps(8), PRC, "hall", nm_line(g, 8, "BW", 1413, "A1A"), system="BW", material=CS)
    g.run([(102.45, 21.0, 0.8), (102.45, 19.5, 0.8)], nps(8), PRC, "hall", nm_line(g, 8, "BW", 1414, "A1A"), system="BW", material=CS)
    g.run([(102.45, 19.5, 0.8), (97.1, 19.5, 0.8, "tee"), (91.1, 19.5, 0.8, "tee"), (85.1, 19.5, 0.8, "tee"), (79.1, 19.5, 0.8)], nps(10), PRC, "hall",
          nm_line(g, 10, "BW", 1415, "A1A"), system="BW", material=CS, support="sleeper")
    # backwash waste to the recovery tank
    g.run([(80.9, 40.0, 3.5), (86.9, 40.0, 3.5, "tee"), (92.9, 40.0, 3.5, "tee"), (98.9, 40.0, 3.5, "tee"), (126, 40.0, 3.5), (126, 45.0, 3.5)], nps(12), PRC, "hall",
          nm_line(g, 12, "BWW", 1450, "A1A"), system="BWW", material=CS, support="hang", zsup=HEAVE + 0.4, hang_every=1)
    plinth((126, 47), (5.6, 5.6), FNDO, "site", "Tank Ring Foundation")
    g.add("IfcTank", "BWR Tank TK-1451", [cyl((126, 47, 0.0), (126, 47, 5.0), 5.0)], VES46, "site", ptype="PREFORMED", tag="TK-1451", material="Carbon Steel", system="BWW")
    # instrument air
    g.add("IfcCompressor", "Instrument Air Compressor AC-1301", [box((77.5, 38.5, 0.5), (1.2, 0.8, 1.0))], PMP, "hall", ptype="ROTARY", tag="AC-1301", system="IA", material="Cast Iron")
    g.add("IfcTank", "IA Receiver V-1302", [cyl((80.0, 39.0, 0.0), (80.0, 39.0, 1.8), 0.7)], VES43, "hall", ptype="PRESSUREVESSEL", tag="V-1302", system="IA", material="Carbon Steel")
    g.run([(80.0, 38.8, 1.5), (80.0, 37.5, 1.5), (86.0, 37.5, 1.5, "tee"), (92.0, 37.5, 1.5, "tee"), (98.0, 37.5, 1.5)], nps(1), UTL, "hall", nm_tool(g, "Stainless Steel", 1),
          system="IA", material="Stainless Steel 316L")
    for x in fxs:
        g.run([(x, 37.5, 1.5), (x, 33.5, 1.5), (x, 33.5, 1.25)], nps(0.5), UTL, "hall", nm_tool(g, "Stainless Steel", 0.5), system="IA", material="Stainless Steel 316L")
    # hall drains
    g.add("IfcBuildingElementProxy", "Manhole MH-D1", [cyl((70, 20.2, -2.2), (70, 20.2, 0.1), 1.2)], SDRN, "site", objtype="Precast manhole 1200", material=CONC)
    g.run([(110.0, 20.2, -0.8), (70.0, 20.2, -0.8)], dn(150), PDRN, "hall", nm_plain("Drain 150 PVC"), system="DR-H", material="PVC-U")
    for x in (82.0, 92.0, 100.0, 110.0):
        g.add("IfcWasteTerminal", pick(f"Floor Drain FD-{int(x)}", f"Floor Drain:Round:{g.rid()}"), [cyl((x, 20.2, -0.1), (x, 20.2, 0.02), 0.2)], PDRN, "hall", ptype="FLOORTRAP", system="DR-H")
        g.run([(x, 20.2, -0.05), (x, 20.2, -0.8)], dn(100), PDRN, "hall", nm_plain("Drain Stub 100 PVC"), system="DR-H", material="PVC-U")
    # MCC, tray and conduits inside the hall
    g.add("IfcElectricDistributionBoard", "MCC-1", [box((76.5, 40.6, 1.1), (2.4, 0.8, 2.2))], PWR, "hall", ptype="MOTORCONTROLCENTRE", tag="MCC-1", system="PWR-A")
    g.add("IfcElectricDistributionBoard", "LP-1 Lighting Panel", [box((74.2, 36.0, 1.5), (0.2, 0.6, 0.9))], PWR, "hall", ptype="DISTRIBUTIONBOARD", tag="LP-1", system="PWR-A")
    g.run([(77.5, 40.6, 2.0), (77.5, 40.6, 3.0), (96.0, 40.6, 3.0, "tee"), (104.5, 40.6, 3.0, "tee"), (108.5, 40.6, 3.0)], (0.3, 0.1), CND, "hall", nm_tray(g, 12), system="PWR-A",
          kind="tray", material="Galvanized Steel", support="bracket", bracket_y=41.85, hang_every=2)
    for x in (104.5, 108.5):
        g.run([(x, 40.6, 3.0), (x, 38.2, 3.0), (x, 38.2, 1.0)], (0.1, 0.1), CND, "hall", nm_conduit(g), system="PWR-A", kind="tray", material="PVC-U")
    g.run([(96.0, 40.6, 3.0), (96.0, 40.6, 2.0)], (0.1, 0.1), CND, "hall", nm_conduit(g), system="PWR-A", kind="tray", material="PVC-U")
    g.add("IfcJunctionBox", "JB-1301", [box((96.0, 40.6, 1.85), (0.3, 0.2, 0.3))], JBI, "hall", ptype="DATA", tag="JB-1301", system="PWR-A")
    g.add("IfcJunctionBox", "JB-1302", [box((74.2, 30.0, 1.5), (0.3, 0.3, 0.3))], JBI, "hall", ptype="DATA", tag="JB-1302")

    # --------------------------------------------------------------- clearwell, high-lift pumps, distribution
    basin("Clearwell CW-1501", 116.0, 24.0, 130.0, 38.0, h=3.5)
    g.add("IfcSlab", "Clearwell Roof Slab", [box((123, 31, 3.65), (14.3, 14.3, 0.3))], SLB, "site", ptype="ROOF", material=CONC, objtype="Cover slab")
    g.add("IfcBuildingElementProxy", "Access Hatch AH-1", [box((120, 31, 3.95), (1.0, 1.0, 0.3))], L("PIP", "EQP", "46", division=["05"]), "site", objtype="Hatch", material="Aluminium")
    sensor((123, 31, 3.8), "LIT", "site", tag="LIT-1501", system="FW", up=0.5)
    sensor((127, 31, 3.8), "AIT", "site", tag="AIT-1501", system="FW", up=0.5)
    g.run([(122.45, 24.1, 0.8), (122.45, 14.5, 0.8)], nps(24), PRC, "site", nm_line(g, 24, "FW", 1501, "A1A"), system="FW", material=CS, support="sleeper")
    g.run([(118.45, 14.5, 0.8), (122.45, 14.5, 0.8, "tee"), (126.45, 14.5, 0.8)], nps(24), PRC, "site", nm_line(g, 24, "FW", 1502, "A1A"), system="FW", material=CS, support="sleeper")
    for k, xp in enumerate((119.0, 123.0, 127.0)):
        pump((xp, 12.5), f"P-150{k + 1}", PMP, "site", FNDO, "TW")
        cxn = xp - 0.55
        g.run([(cxn, 14.5, 0.8), (cxn, 12.8, 0.8)], nps(12), PRC, "site", nm_line(g, 12, "FW", 1503 + k, "A1A"), system="FW", material=CS)
        g.run([(cxn, 12.5, 0.8), (cxn, 10.0, 0.8, "check"), (cxn, 8.5, 0.8)], nps(12), PRC, "site", nm_line(g, 12, "TW", 1511 + k, "A1A"), system="TW", material=CS, vT=VLV)
    g.run([(118.45, 8.5, 0.8), (122.45, 8.5, 0.8, "tee"), (126.45, 8.5, 0.8, "tee"), (134.0, 8.5, 0.8, meter("FIT-1521", 0.7)), (144.5, 8.5, 0.8), (144.5, 8.5, -0.5)], nps(24), PRC, "site",
          nm_line(g, 24, "TW", 1520, "A1A"), system="TW", material=CS, support="sleeper")
    chamber("Distribution Tie-in Chamber TC-2", 144.5, 8.5)
    sensor((130.0, 8.5, 0.8 + nps(24) / 2), "PIT", "site", tag="PIT-1521", system="TW", up=0.4)
    sensor((138.0, 8.5, 0.8 + nps(24) / 2), "AIT", "site", tag="AIT-1522", system="TW", up=0.4)

    # --------------------------------------------------------------- yard electrical
    for k in range(8):
        x = 4 + k * 17
        y = 3.5 if k % 2 == 0 else 48.5
        g.add("IfcLightFixture", pick(f"Area Light Pole LP-{k + 1}", f"Pole Light:8m:{g.rid()}", f"LTP-{k + 1}"), [cyl((x, y, 0.0), (x, y, 8.0), 0.2), box((x, y, 8.1), (1.0, 0.4, 0.2))],
              LTG, "site", ptype="POINTSOURCE", system="LTG-Y", material="Galvanized Steel")
    plinth((95, 66), (3.2, 2.6), FNDO, "site", "Transformer Pad")
    g.add("IfcTransformer", pick("TR-1 11kV/415V 500kVA", "Transformer TR-1", f"Transformer:Pad Mount:{g.rid()}"), [box((95, 66, 1.1), (2.2, 1.6, 2.2))], PWR, "site", ptype="VOLTAGE", tag="TR-1", system="PWR-A")
    plinth((100, 58), (5.4, 2.4), FNDO, "site", "Generator Pad")
    g.add("IfcElectricGenerator", pick("G-1 Standby Generator 400kW", "Generator G-1"), [box((100, 58, 1.1), (4.0, 1.6, 2.2))], GEN, "site", ptype="ENGINEGENERATOR", tag="G-1", system="PWR-A", material="Steel, Painted")
    g.add("IfcTank", "Diesel Day Tank", [cyl((103.6, 58, 0.0), (103.6, 58, 1.6), 1.2)], L("ELE", "GEN", "26", discipline=["PIP"], also=["PIP/VES"], division=["43"]), "site", ptype="PREFORMED", tag="T-1801", material="Carbon Steel")
    g.add("IfcElectricFlowStorageDevice", "UPS-1", [box((91.7, 56.5, 0.9), (0.8, 0.8, 1.8))], GEN, "site", ptype="UPS", tag="UPS-1", system="PWR-B")

    # --------------------------------------------------------------- Administration and Control Building
    AX0, AX1, AY0, AY1 = 60.0, 90.0, 54.0, 68.0
    FL = {"admin1": (0.0, 3.95), "admin2": (4.2, 8.15)}
    gx = [61.0, 69.0, 77.0, 85.0]
    gy = [55.0, 61.0, 67.0]
    g.add("IfcSlab", "Ground Floor Slab", [box((75, 61, -0.15), (30, 14, 0.3))], SLB, "admin1", ptype="BASESLAB", material=CONC, objtype="Slab on grade 6 in", psets={"Pset_SlabCommon": {"LoadBearing": True}})
    g.add("IfcSlab", "Level 2 Floor", [box((75, 61, 4.075), (30, 14, 0.25))], SLB, "admin2", ptype="FLOOR", material=CONC, objtype="Floor: Concrete 10in", psets={"Pset_SlabCommon": {"LoadBearing": True}})
    g.add("IfcSlab", "Roof Slab", [box((75, 61, 8.275), (30, 14, 0.25))], SLB, "adminR", ptype="ROOF", material=CONC, objtype="Roof: Concrete 10in", psets={"Pset_SlabCommon": {"IsExternal": True}})
    for x in gx:
        for y in gy:
            g.add("IfcFooting", f"Pad Footing {int(x)}-{int(y)}", [box((x, y, -0.75), (1.6, 1.6, 0.9))], FNDI, "admin1", ptype="PAD_FOOTING", material=CONC)
            for st, (z0, z1) in FL.items():
                g.add("IfcColumn", pick(f"Concrete Column 400x400 {st[-1]}", f"Structural Columns:Concrete-Rectangular:400 x 400:{g.rid()}", f"C{int(x)}{int(y)}"),
                      [box((x, y, (z0 + z1) / 2), (0.4, 0.4, z1 - z0))], COL03, st, ptype="COLUMN", material=CONC, objtype="400 x 400")
    for st, (z0, z1) in FL.items():
        for y in gy:
            for i in range(3):
                g.add("IfcBeam", pick("Concrete Beam 300x400", f"Structural Framing:Concrete-Rectangular Beam:300 x 400:{g.rid()}"),
                      [box(((gx[i] + gx[i + 1]) / 2, y, z1 - 0.2), (gx[i + 1] - gx[i], 0.3, 0.4))], BEM03, st, ptype="BEAM", material=CONC)
        for x in gx[1:3]:
            for j in range(2):
                g.add("IfcBeam", pick("Concrete Beam 300x400 X", f"Structural Framing:Concrete-Rectangular Beam:300 x 400:{g.rid()}"),
                      [box((x, (gy[j] + gy[j + 1]) / 2, z1 - 0.2), (0.3, gy[j + 1] - gy[j], 0.4))], BEM03, st, ptype="BEAM", material=CONC)
    for st, (z0, z1) in FL.items():
        zc = (z0 + z1) / 2
        hgt = z1 - z0
        for sd, y in (("S", AY0 + 0.125), ("N", AY1 - 0.125)):
            for i in range(4):
                xm = AX0 + 3.75 + 7.5 * i
                wid = g.add("IfcWall", pick(f"Basic Wall:Exterior - CMU 10in:{g.rid()}", f"Basic Wall:Generic - 200mm:{g.rid()}", f"Ext Wall {sd}{i + 1}"), [box((xm, y, zc), (7.5, 0.25, hgt))],
                            WALX, st, ptype="STANDARD", material="Concrete Masonry Unit", objtype=pick("Exterior - CMU 10in", "Generic - 200mm"),
                            psets=pick({"Pset_WallCommon": {"IsExternal": True, "FireRating": "1HR", "LoadBearing": False}}, {"Identity Data": {"Type Mark": "EW-1"}}))
                wins = [xm] if (sd == "S" or st == "admin2") else []
                if st == "admin1" and sd == "S" and i in (1, 2):
                    dr = g.add("IfcDoor", pick(f"Single-Flush:36\" x 84\":{g.rid()}", "Entrance Door 6'-0\" x 7'-0\"", "Storefront Door"), [box((xm, y, z0 + 1.05), (1.8, 0.1, 2.1))], DOR, st,
                               ptype="DOOR", material="Aluminium", psets={"Pset_DoorCommon": {"IsExternal": True}})
                    g.opening_for(wid, dr, (xm, y, z0 + 1.05), (1.85, 0.4, 2.15), cont=st)
                    wins = []
                for wx in wins:
                    wn = g.add("IfcWindow", pick("Window - Fixed - 4'-0\" x 5'-0\"", f"M_Fixed:0915 x 1830mm:{g.rid()}", "Window 1200x1500"), [box((wx, y, z0 + 1.9), (1.2, 0.1, 1.5))], WIN, st,
                               ptype="WINDOW", material="Aluminium", psets=pick(None, {"Pset_WindowCommon": {"IsExternal": True}}))
                    g.opening_for(wid, wn, (wx, y, z0 + 1.9), (1.25, 0.4, 1.55), cont=st)
        for sd, x in (("W", AX0 + 0.125), ("E", AX1 - 0.125)):
            for j in range(2):
                ym = AY0 + 3.5 + 7.0 * j
                wid = g.add("IfcWall", pick(f"Basic Wall:Exterior - CMU 10in:{g.rid()}", f"Ext Wall {sd}{j + 1}"), [box((x, ym, zc), (0.25, 7.0, hgt))], WALX, st, ptype="STANDARD",
                            material="Concrete Masonry Unit", objtype="Exterior - CMU 10in")
                if sd == "E" and st == "admin1" and j == 0:
                    dr = g.add("IfcDoor", "Single-Flush:36\" x 84\":%d" % g.rid(), [box((x, ym, z0 + 1.05), (0.1, 0.9, 2.1))], DOR, st, ptype="DOOR", material="Steel, Painted", psets={"Pset_DoorCommon": {"FireExit": True}})
                    g.opening_for(wid, dr, (x, ym, z0 + 1.05), (0.4, 0.95, 2.15), cont=st)
    # lift shaft walls (concrete core), partitions
    for k, (c, s) in enumerate((((61.3, 58.1, 4.075), (2.3, 0.25, 8.15)), ((62.4, 56.2, 4.075), (0.25, 3.9, 8.15)))):
        g.add("IfcWall", pick(f"Shear Wall SW-{k + 1}", f"Basic Wall:Concrete 250mm:{g.rid()}"), [box(c, s)], WLS, "admin1", ptype="SHEAR", material=CONC, objtype="Concrete 250mm",
              psets={"Pset_WallCommon": {"LoadBearing": True}})
    for st, (z0, z1) in FL.items():
        zc = (z0 + z1) / 2
        hgt = z1 - z0
        segs = [(y, 66.0 + 8 * i, 74.0 + 8 * i) for y in (58.0, 62.0) for i in range(3)]
        for y, x0_, x1_ in segs:
            xm = (x0_ + x1_) / 2
            wid = g.add("IfcWall", pick(f"Interior - Partition 3-5/8\":{g.rid()}", f"Basic Wall:Interior - 138mm Partition:{g.rid()}", f"Partition {int(y)}-{int(x0_)}"), [box((xm, y, zc), (8.0, 0.14, hgt))],
                        WALP, st, ptype="PARTITIONING", material="Gypsum Board", objtype="Interior - 138mm Partition", psets=pick(None, {"Pset_WallCommon": {"IsExternal": False, "FireRating": "1HR"}}))
            dr = g.add("IfcDoor", pick(f"Single-Flush:36\" x 84\":{g.rid()}", "Door 900x2100", f"D-{st[-1]}{int(y)}{int(x0_)}"), [box((xm, y, z0 + 1.05), (0.9, 0.08, 2.1))], DOR, st, ptype="DOOR",
                       material="Wood, Oak", psets=pick(None, {"Pset_DoorCommon": {"IsExternal": False}}), proxy=0.03)
            g.opening_for(wid, dr, (xm, y, z0 + 1.05), (0.95, 0.4, 2.15), cont=st)
        g.add("IfcWall", pick("WC Core Wall", f"Basic Wall:Interior - 138mm Partition:{g.rid()}"), [box((63.1, 62.0, zc), (5.75, 0.14, hgt))], WALP, st, ptype="PARTITIONING", material="Gypsum Board", objtype="Interior - 138mm Partition")
        for x in (66.0, 74.0, 82.0):
            for (ya, yb) in ((54.25, 58.0), (62.0, 67.75)):
                g.add("IfcWall", pick(f"Partition {int(x)}", f"Interior - Partition 3-5/8\":{g.rid()}", f"Basic Wall:Interior - 138mm Partition:{g.rid()}"), [box((x, (ya + yb) / 2, zc), (0.14, yb - ya, hgt))], WALP, st,
                      ptype="PARTITIONING", material="Gypsum Board", objtype="Interior - 138mm Partition")
    ceil_rooms = [(66, 74, 54.25, 58), (74, 82, 54.25, 58), (82, 89.75, 54.25, 58), (66, 74, 62, 67.75), (74, 82, 62, 67.75), (82, 89.75, 62, 67.75), (66, 89.75, 58, 62),
                  (60.25, 66, 62, 67.75)]
    for st, (z0, z1) in FL.items():
        for k, (xa, xb, ya, yb) in enumerate(ceil_rooms):
            g.add("IfcCovering", pick(f"Compound Ceiling:600 x 600mm Grid:{g.rid()}", f"ACT Ceiling {k + 1}", "Suspended Ceiling"), [box(((xa + xb) / 2, (ya + yb) / 2, z0 + 3.0), (xb - xa, yb - ya, 0.04))],
                  CEIL, st, ptype="CEILING", material="Acoustic Tile", objtype="600 x 600mm Grid")
        for k, (xa, xb, ya, yb) in enumerate(ceil_rooms[:3]):
            g.add("IfcCovering", pick(f"Floor:Carpet Tile {k + 1}", f"Finish Floor FF-{k + 1}", "Floor Finish"), [box(((xa + xb) / 2, (ya + yb) / 2, z0 + 0.01), (xb - xa, yb - ya, 0.02))], CEIL, st,
                  ptype="FLOORING", material="Carpet", objtype="Carpet Tile")
    for k in range(6):
        st, z0 = ("admin1", 0.0) if k < 3 else ("admin2", 4.2)
        x = 68 + (k % 3) * 8
        y = 56.0 if k % 2 == 0 else 65.0
        g.add("IfcFurniture", pick(f"Desk 1500x750 {k + 1}", f"Furniture:Desk:{g.rid()}", f"Workstation WS-{k + 1}"), [box((x, y, z0 + 0.375), (1.5, 0.75, 0.75))], FUR, st, ptype="DESK", material="Wood")
        g.add("IfcFurniture", pick(f"Chair {k + 1}", f"Furniture:Office Chair:{g.rid()}"), [box((x, y + (0.7 if y < 60 else -0.7), z0 + 0.45), (0.5, 0.5, 0.9))], FUR, st, ptype="CHAIR", material="Plastic")
    for k in range(3):
        g.add("IfcFurniture", pick(f"Lab Bench LB-{k + 1}", f"Casework:Base Cabinet:{g.rid()}"), [box((78 + 4 * k, 66.9, 4.2 + 0.45), (3.0, 0.8, 0.9))], FUR, "admin2", ptype="USERDEFINED", material="Laminate", objtype="Casework")
    g.add("IfcRoof", "Roof - Flat - Membrane", [box((75, 61, 8.5), (30.4, 14.4, 0.2))], ROF, "adminR", ptype="FLAT_ROOF", material="EPDM", objtype="Flat roof: EPDM on insulation")
    g.add("IfcCovering", "Roof Insulation 150mm", [box((75, 61, 8.675), (30, 14, 0.15))], ROF, "adminR", ptype="INSULATION", material="XPS Insulation", objtype="Insulation 6in")
    g.add("IfcStair", "Stair ST-1", [box((62.5, 58.625 + 0.25 * i, 0.175 + 0.35 * i), (1.2, 0.25, 0.35)) for i in range(12)], STAIR, "admin1", ptype="STRAIGHT_RUN_STAIR", material="Concrete",
          psets={"Pset_StairCommon": {"NumberOfRiser": 12}})
    for xr in (61.85, 63.15):
        g.add("IfcRailing", pick("Railing - Stair 1.1m", f"Railing:Handrail - Pipe:{g.rid()}"), [box((xr, 60.0, 1.15), (0.05, 3.0, 2.3))], STAIR, "admin1", ptype="HANDRAIL", material="Stainless Steel")
    g.add("IfcTransportElement", "Elevator EL-1", [box((61.0, 56.5, 1.35), (1.6, 1.6, 2.7))], L("ARC", "FUR", "14"), "admin1", ptype="ELEVATOR", tag="EL-1", material="Stainless Steel")
    g.add("IfcCurtainWall", "Curtain Wall CW-1", [box((75, 54.0, 3.55), (5.6, 0.05, 0.1))], WIN, "admin1", ptype="USERDEFINED", material="Aluminium")
    for k in range(6):
        g.add("IfcPlate", pick(f"Curtain Panel {k + 1}", f"Curtain Wall Panels:Glazed:{g.rid()}"), [box((72.665 + 0.93 * k, 54.0, 1.9), (0.93, 0.04, 3.4))], WIN, "admin1", ptype="CURTAIN_PANEL", material="Glass, Clear")
    for k in range(7):
        g.add("IfcMember", pick(f"Mullion {k + 1}", f"Curtain Wall Mullions:Rectangular:{g.rid()}"), [box((72.2 + 0.93 * k, 54.0, 1.9), (0.06, 0.08, 3.4))], WIN, "admin1", ptype="MULLION", material="Aluminium")

    # --- HVAC
    g.add("IfcUnitaryEquipment", pick("AHU-01", "Air Handling Unit AHU-1", "Mechanical Equipment:AHU:%d" % g.rid()), [box((85.0, 65.0, 0.9), (3.0, 1.4, 1.8))], MEQP, "admin1", ptype="AIRHANDLER", tag="AHU-01",
          system="SA-01", material="Galvanized Steel", proxy=0.1, psets={"Pset_UnitaryEquipmentTypeCommon": {"Reference": "AHU-01"}})
    g.add("IfcBoiler", "B-01", [cyl((88.8, 66.9, 0.0), (88.8, 66.9, 1.7), 0.9)], MEQP, "admin1", ptype="WATER", tag="B-01", system="HHW", material="Steel, Painted", psets={"Pset_BoilerTypeCommon": {"Reference": "B-01"}})
    plinth((94.5, 60.0), (3.6, 2.0), FNDO, "site", "Chiller Pad")
    g.add("IfcChiller", pick("CH-01 Air-Cooled Chiller", "Chiller CH-1"), [box((94.5, 60.0, 1.1), (3.0, 1.5, 2.2))], MEQP, "site", ptype="AIRCOOLED", tag="CH-01", system="CW-01", material="Steel, Painted")
    for k, py in enumerate((63.6, 64.6)):
        plinth((87.0, py), (1.0, 0.7), FNDI, "admin1", f"Pump Base HHWP-0{k + 1}")
        g.add("IfcPump", pick(f"HHWP-0{k + 1}", f"Pump:Inline:{g.rid()}", f"Hot Water Pump {k + 1}"), [box((87.0, py, 0.3), (0.7, 0.4, 0.6))], HPMP, "admin1", ptype="CIRCULATOR", tag=f"HHWP-0{k + 1}", system="HHW")
    g.add("IfcTank", "ET-01 Expansion Tank", [cyl((89.3, 63.2, 0.0), (89.3, 63.2, 1.0), 0.5)], MEQP, "admin1", ptype="EXPANSION", tag="ET-01", system="HHW")
    g.add("IfcTank", pick("WH-01 Water Heater", "Domestic Water Heater"), [cyl((83.3, 66.5, 0.0), (83.3, 66.5, 1.5), 0.6)], PEQP, "admin1", ptype="STORAGE", tag="WH-01", system="DHW", material="Steel, Glass-lined")
    g.add("IfcPump", "Domestic Booster Pump BP-1", [box((83.5, 62.8, 0.3), (0.7, 0.4, 0.6))], PEQP, "admin1", ptype="ENDSUCTION", tag="BP-1", system="DCW")

    def trunk(zc, st, zceil, z0):
        pts = ([(85.5, 65.0, 1.7), (85.5, 65.0, zc), (85.5, 60.0, zc, "tee")] if st == "admin1" else [(85.5, 60.0, zc)])
        pts += [(80.0, 60.0, zc, "tee"), (74.0, 60.0, zc, "tee"), (68.0, 60.0, zc)]
        g.run(pts, (0.6, 0.4), DUCT, st, nm_duct(g), system="SA-01", kind="duct", material="Galvanized Steel", support="hang", zsup=zceil, maxlen=3.0)
        for x, yds in ((80.0, (56.0, 64.0)), (74.0, (56.0,)), (68.0, (64.0,))):
            for yd in yds:
                dmp = {"cls": "IfcDamper", "len": 0.35, "T": ACC, "name": pick(f"Damper {int(x)}", f"Duct Accessory:Volume Damper:{g.rid()}", "VD-%d" % rng.randint(1, 99)), "ptype": "CONTROLDAMPER"}
                vav = {"cls": "IfcAirTerminalBox", "len": 0.9, "T": TRM, "name": pick(f"VAV-{int(x)}", "VAV Box"), "ptype": "VARIABLEFLOWPRESSUREINDEPENDANT"}
                dev = vav if int(x) == 74 else dmp
                g.run([(x, 60.0, zc), (x, 60.0 + (yd - 60.0) * 0.45, zc, dev), (x, yd, zc), (x, yd, zc - 0.2)], (0.3, 0.2), DUCT, st, nm_duct(g), system="SA-01", kind="duct",
                      material="Galvanized Steel", maxlen=3.0)
                g.add("IfcAirTerminal", pick(f"Supply Diffuser {int(x)}-{int(yd)}", f"Air Terminal:Square Diffuser 600x600:{g.rid()}", f"SD-{int(x)}"), [box((x, yd, z0 + 3.0), (0.6, 0.6, 0.4))],
                      TRM, st, ptype="DIFFUSER", system="SA-01", material="Aluminium", proxy=0.05)
    trunk(3.3, "admin1", 3.95, 0.0)
    g.run([(85.5, 60.0, 3.3), (85.5, 60.0, 7.5)], (0.6, 0.4), DUCT, "admin2", nm_duct(g), system="SA-01", kind="duct", material="Galvanized Steel", maxlen=3.0)
    trunk(7.5, "admin2", 8.15, 4.2)
    g.add("IfcAirTerminal", "Exhaust Grille L1", [box((63.0, 67.0, 3.0), (0.4, 0.4, 0.2))], TRM, "admin1", ptype="GRILLE", system="EA-01")
    g.add("IfcAirTerminal", "Exhaust Grille L2", [box((63.0, 67.0, 7.2), (0.4, 0.4, 0.2))], TRM, "admin2", ptype="GRILLE", system="EA-01")
    g.add("IfcFan", "EF-01 Roof Exhaust Fan", [cyl((63.0, 67.0, 8.6), (63.0, 67.0, 9.3), 0.8)], MEQP, "adminR", ptype="CENTRIFUGALAIRFOIL", tag="EF-01", system="EA-01", material="Galvanized Steel")
    g.run([(63.0, 67.0, 3.1), (63.0, 67.0, 7.1, "tee"), (63.0, 67.0, 8.7)], (0.3, 0.3), DUCT, "admin1", nm_duct(g), system="EA-01", kind="duct", material="Galvanized Steel", maxlen=3.0)
    # hydronic
    g.run([(93.2, 60.0, 1.2), (89.0, 60.0, 1.2, "valve"), (85.0, 60.0, 1.2), (85.0, 64.4, 1.2)], dn(80), HYD, "admin1", nm_tool(g, "Carbon Steel", 3), system="CW-01", material=CS, vT=HVLV, support="sleeper")
    g.run([(93.2, 60.4, 1.0), (85.4, 60.4, 1.0), (85.4, 64.4, 1.0)], dn(80), HYD, "admin1", nm_tool(g, "Carbon Steel", 3), system="CW-01", material=CS, support="sleeper")
    g.run([(88.8, 66.9, 0.35), (88.8, 67.5, 0.35), (80.0, 67.5, 0.35, "tee"), (76.0, 67.5, 0.35, "tee"), (70.0, 67.5, 0.35, "tee"), (68.0, 67.5, 0.35)], dn(40), HYD, "admin1",
          nm_revit(g, "Carbon Steel - Welded"), system="HHW", material=CS)
    g.run([(68.0, 67.5, 0.35), (68.0, 67.5, 4.55)], dn(40), HYD, "admin2", nm_plain("HHW Riser DN40"), system="HHW", material=CS)
    g.run([(68.0, 67.5, 4.55), (70.0, 67.5, 4.55, "tee"), (76.0, 67.5, 4.55, "tee"), (80.0, 67.5, 4.55)], dn(40), HYD, "admin2", nm_plain("HHW Supply DN40"), system="HHW", material=CS)
    for st, z in (("admin1", 0.35), ("admin2", 4.55)):
        for x in (80.0, 70.0):
            g.run([(x, 67.5, z), (x, 67.7, z)], dn(20), HYD, st, nm_plain("HHW Branch DN20"), system="HHW", material=CS)
            g.add("IfcSpaceHeater", pick(f"Radiator R-{int(x)}", f"Fin Tube Radiator {int(x)}", f"Baseboard Heat:Fintube:{g.rid()}"), [box((x, 67.7, z + 0.05), (1.0, 0.2, 0.6))], MEQP, st, ptype="CONVECTOR",
                  system="HHW", material="Steel, Painted")
    g.run([(88.8, 66.9, 0.35), (88.0, 66.9, 0.35, "valve"), (87.0, 66.9, 0.35), (87.0, 64.6, 0.35)], dn(40), HYD, "admin1", nm_plain("HHW Pump Suction DN40"), system="HHW", material=CS, vT=HVLV)
    g.run([(87.0, 63.6, 0.35), (87.0, 62.9, 0.35), (85.6, 62.9, 0.35), (85.6, 64.4, 0.35)], dn(40), HYD, "admin1", nm_plain("HHW Coil Supply DN40"), system="HHW", material=CS)
    g.run([(88.8, 66.9, 0.5), (89.3, 66.9, 0.5), (89.3, 63.2, 0.5)], dn(25), HYD, "admin1", nm_plain("Expansion Line DN25"), system="HHW", material=CS)
    for k in range(6):
        st, z0 = ("admin1", 0.0) if k < 3 else ("admin2", 4.2)
        g.add("IfcSensor", pick(f"TS-{k + 1}", "Thermostat", f"Sensor:Thermostat:{g.rid()}"), [box((70 + 6 * (k % 3), 58.1, z0 + 1.4), (0.1, 0.06, 0.12))], BAS, st, ptype="TEMPERATURESENSOR", tag=f"TS-{k + 1}")
    g.add("IfcController", "DDC-1", [box((83.5, 61.9, 1.5), (0.5, 0.15, 0.6))], PLC, "admin1", ptype="PROGRAMMABLE", tag="DDC-1", system="SA-01")
    # --- plumbing: WC cores on both floors
    fx_ = [(61.8 + 0.8 * i, kind) for i, kind in enumerate(["WC", "WC", "URINAL", "BASIN", "BASIN"])]
    for st, z0, zh in (("admin1", 0.0, 3.4), ("admin2", 4.2, 7.6)):
        zq = 3.95 if st == "admin1" else 8.15
        for xf, kind in fx_:
            dims = {"WC": (0.4, 0.7, 0.8), "URINAL": (0.4, 0.4, 0.9), "BASIN": (0.5, 0.45, 0.85)}[kind]
            word = {"WC": "Water Closet", "URINAL": "Urinal", "BASIN": "Lavatory"}[kind]
            g.add("IfcSanitaryTerminal", pick(f"{kind} {st[-1]}-{xf:.1f}", f"Plumbing Fixture:{kind.title()}:{g.rid()}", f"{word} {st[-1]}{int(xf)}"), [box((xf, 67.5, z0 + dims[2] / 2), dims)], PFIX, st,
                  ptype={"WC": "WCSEAT", "URINAL": "URINAL", "BASIN": "WASHHANDBASIN"}[kind], system="DCW", proxy=0.05,
                  psets=pick(None, {"Pset_SanitaryTerminalTypeCommon": {"Reference": kind}}))
            g.run([(xf, 67.3, zh), (xf, 67.3, z0 + 0.7)], dn(20), PSUP, st, nm_plain("Copper Type L 3/4\""), system="DCW", material="Copper")
            g.run([(xf, 67.5, z0 + 0.05), (xf, 67.5, -0.8 if st == "admin1" else 3.5)], dn(50), PDRN, st, nm_plain("Sanitary 50 PVC"), system="SAN", material="PVC-U", maxlen=5.0)
        g.run([(60.6, 67.3, zh)] + [(xf, 67.3, zh, "tee") for xf, _ in fx_[:-1]] + [(fx_[-1][0], 67.3, zh)], dn(25), PSUP, st, nm_tool(g, "Copper", 1), system="DCW", material="Copper", support="hang", zsup=zq)
        g.run([(fx_[3][0], 67.4, zh - 0.2), (fx_[4][0], 67.4, zh - 0.2)], dn(20), PSUP, st, nm_plain("Copper Type L 3/4\" HW"), system="DHW", material="Copper")
        for xb in (fx_[3][0], fx_[4][0]):
            g.run([(xb, 67.4, zh - 0.2), (xb, 67.4, z0 + 0.7)], dn(20), PSUP, st, nm_plain("Copper Type L 3/4\" HW"), system="DHW", material="Copper")
    chamber("Water Service Chamber WSC-1", 57.0, 66.2)
    g.run([(57.0, 66.2, -1.0), (60.6, 66.2, -1.0), (60.6, 66.2, -0.3, "valve"), (60.6, 66.2, 0.5), (60.6, 67.3, 0.5), (60.6, 67.3, 3.4, "tee"), (60.6, 67.3, 7.6)], dn(40), PSUP, "admin1",
          nm_plain("Water Service 40 Copper"), system="DCW", material="Copper", vT=PVLV)
    g.run([(83.3, 66.5, 1.4), (83.3, 66.5, 3.2), (83.3, 67.4, 3.2), (64.6, 67.4, 3.2)], dn(20), PSUP, "admin1", nm_plain("DHW 20 Copper"), system="DHW", material="Copper", support="hang", zsup=3.95)
    g.run([(64.6, 67.4, 3.2), (64.6, 67.4, 7.4)], dn(20), PSUP, "admin2", nm_plain("DHW Riser 20 Copper"), system="DHW", material="Copper")
    # drains: collectors, stack, vent
    manhole("Manhole MH-SAN1", 56.0, 67.5)
    g.run([(65.0, 67.5, -0.8), (56.0, 67.5, -0.8)], dn(100), PDRN, "admin1", nm_plain("Sanitary 100 PVC"), system="SAN", material="PVC-U")
    g.run([(65.0, 67.5, 3.5), (60.4, 67.5, 3.5), (60.4, 67.5, -0.8)], dn(100), PDRN, "admin1", nm_plain("Sanitary 100 PVC"), system="SAN", material="PVC-U", support="hang", zsup=3.95, hang_every=1, maxlen=5.0)
    g.run([(60.8, 67.5, 3.5), (60.8, 67.5, 8.6)], dn(75), PDRN, "admin1", nm_plain("Vent 75 PVC"), system="VTR", material="PVC-U", maxlen=5.0)
    for k, x in enumerate((62.5, 63.5)):
        g.add("IfcWasteTerminal", pick(f"Floor Drain FD-{k + 1}", f"Floor Drain:Round:{g.rid()}"), [cyl((x, 65.0, -0.1), (x, 65.0, 0.02), 0.2)], PDRN, "admin1", ptype="FLOORTRAP", system="SAN")
        g.run([(x, 65.0, -0.05), (x, 65.0, -0.8), (x, 67.5, -0.8)], dn(75), PDRN, "admin1", nm_plain("Sanitary 75 PVC"), system="SAN", material="PVC-U")
    for k, (x, y, yo) in enumerate(((66.0, 54.6, 53.4), (84.0, 54.6, 53.4))):
        g.add("IfcWasteTerminal", pick(f"Roof Drain RD-{k + 1}", f"Roof Drain:Dome:{g.rid()}"), [cyl((x, y, 8.4), (x, y, 8.62), 0.3)], PSTM, "adminR", ptype="ROOFDRAIN", system="STM")
        manhole(f"Manhole MH-ST{k + 1}", x, yo)
        g.run([(x, y, 8.5), (x, y, -0.8), (x, yo, -0.8)], dn(100), PSTM, "admin1", nm_plain("Storm 100 PVC"), system="STM", material="PVC-U", maxlen=5.0)
    # --- fire protection
    g.run([(87, 47, -1.2), (87, 56, -1.2), (87, 56, 3.5, "tee"), (87, 56, 7.7)], dn(150), SPR, "admin1", nm_plain("Fire Riser DN150"), system="FP-01", material=CS, maxlen=5.0)
    for st, zm in (("admin1", 3.5), ("admin2", 7.7)):
        xs_ = [82.0, 76.0, 70.0]
        brs = {82.0: (), 76.0: (56.0, 64.0), 70.0: ()}
        g.run([(87, 56, zm), (87, 59.0, zm)] + [(x, 59.0, zm, "tee") for x in xs_[:-1]] + [(xs_[-1], 59.0, zm)], dn(65), SPR, st, nm_tool(g, "Carbon Steel", 2.5), system="FP-01", material=CS, support="hang",
              zsup=zm + 0.45, hang_every=2)
        for x in xs_:
            for yd in (brs[x] or (59.0,)):
                g.run([(x, 59.0, zm), (x, yd, zm), (x, yd, zm - 0.5)], dn(25), SPR, st, nm_plain("Sprinkler Branch 1\""), system="FP-01", material=CS)
                g.add("IfcFireSuppressionTerminal", pick(f"Sprinkler {int(x)}-{int(yd)}", f"Sprinkler:Pendent:{g.rid()}", f"SP-{int(x)}{int(yd)}"), [cyl((x, yd, zm - 0.75), (x, yd, zm - 0.45), 0.06)], SPR, st,
                      ptype="SPRINKLER", system="FP-01", proxy=0.03)
    for k in range(8):
        st, z0 = ("admin1", 0.0) if k < 4 else ("admin2", 4.2)
        g.add("IfcBuildingElementProxy", pick(f"Fire Extinguisher FE-{k + 1}", f"Extinguisher Cabinet {k + 1}", "Fire Extinguisher"), [box((68 + 6 * (k % 4), 58.15, z0 + 1.2), (0.3, 0.2, 0.6))], EXT, st,
              objtype="ABC 10lb", material="Steel, Painted")
    # --- electrical
    g.add("IfcElectricDistributionBoard", pick("SWBD-1", "Main Switchboard SWBD-1"), [box((86.0, 55.2, 1.0), (2.4, 0.8, 2.0))], PWR, "admin1", ptype="SWITCHBOARD", tag="SWBD-1", system="PWR-A",
          psets={"Pset_ElectricDistributionBoardTypeCommon": {"Reference": "SWBD-1"}})
    for k, (x, y, z0, st) in enumerate(((66.2, 56.0, 0.0, "admin1"), (66.2, 65.0, 0.0, "admin1"), (66.2, 56.0, 4.2, "admin2"), (66.2, 65.0, 4.2, "admin2"))):
        g.add("IfcElectricDistributionBoard", f"LP-{k + 2}", [box((x - 0.12, y, z0 + 1.5), (0.2, 0.6, 0.9))], PWR, st, ptype="DISTRIBUTIONBOARD", tag=f"LP-{k + 2}", system="PWR-A")
    g.run([(86.0, 55.2, 1.9), (86.0, 55.2, 3.2), (86.0, 60.8, 3.2), (80.0, 60.8, 3.2, "tee"), (74.0, 60.8, 3.2, "tee"), (66.5, 60.8, 3.2)], (0.3, 0.1), CND, "admin1", nm_tray(g, 12), system="PWR-A", kind="tray",
          material="Galvanized Steel", support="hang", zsup=3.95, hang_every=2, maxlen=3.0)
    g.run([(66.5, 60.8, 3.2), (66.5, 60.8, 7.4), (88.0, 60.8, 7.4)], (0.3, 0.1), CND, "admin2", nm_tray(g, 12), system="PWR-A", kind="tray", material="Galvanized Steel", support="hang", zsup=8.15,
          hang_every=2, maxlen=3.0)
    g.add("IfcJunctionBox", "JB-L2", [box((88.0, 60.8, 7.5), (0.25, 0.2, 0.3))], WIR, "admin2", ptype="DATA", tag="JB-L2")
    for st, z0, zt, xs_ in (("admin1", 0.0, 3.2, (80.0, 74.0)), ("admin2", 4.2, 7.4, (80.0, 72.0))):
        for x in xs_:
            g.run([(x, 60.8, zt), (x, 64.5, zt), (x, 64.5, zt - 0.25)], (0.05, 0.05), CND, st, nm_conduit(g), system="LTG-A", kind="tray", material="PVC-U")
            g.add("IfcLightFixture", f"Troffer 2x4 {st[-1]}C{int(x)}", [box((x, 64.5, z0 + 2.95), (1.2, 0.6, 0.12))], LTG, st, ptype="POINTSOURCE", system="LTG-A")
        for j in range(6):
            x = 67 + j * 3.6
            y = (56.0, 58.5 + 0.0, 60.0)[j % 3] if False else (56.0, 60.0, 56.0)[j % 3]
            g.add("IfcLightFixture", pick(f"Troffer 2x4 {st[-1]}{j}", f"Light Fixture:Troffer:{g.rid()}", f"LF-{st[-1]}-{j + 1}"), [box((x, y, z0 + 2.95), (1.2, 0.6, 0.12))], LTG, st, ptype="POINTSOURCE", system="LTG-A")
    for k in range(14):
        st, z0 = ("admin1", 0.0) if k < 7 else ("admin2", 4.2)
        x = 67.0 + (k % 7) * 3.0
        side = 58.0 if (k % 2) else 62.0
        face = side + (0.1 if side == 62.0 else -0.1)
        g.add("IfcOutlet", pick(f"Duplex Receptacle {k + 1}", f"Electrical Fixtures:Receptacle:{g.rid()}", f"R-{k + 1}"), [box((x, face, z0 + 0.4), (0.08, 0.06, 0.12))], DEV, st, ptype="POWEROUTLET", proxy=0.05)
    for k in range(6):
        st, z0 = ("admin1", 0.0) if k < 3 else ("admin2", 4.2)
        g.add("IfcSwitchingDevice", pick(f"Light Switch S-{k + 1}", f"Lighting Switch:Single:{g.rid()}"), [box((66.8 + 8 * (k % 3), 62.1, z0 + 1.2), (0.08, 0.06, 0.12))], DEV, st, ptype="TOGGLESWITCH")
    for k in range(5):
        g.add("IfcJunctionBox", f"JB-{k + 1}", [box((71 + 3 * k, 60.8, 3.35), (0.25, 0.2, 0.2))], WIR, "admin1", ptype="DATA", tag=f"JB-{k + 1}")
    # --- telecom, security, fire alarm
    for k in range(8):
        st, z0 = ("admin1", 0.0) if k < 4 else ("admin2", 4.2)
        g.add("IfcCommunicationsAppliance", pick(f"Data Outlet DO-{k + 1}", f"Communication Devices:Data Outlet:{g.rid()}", f"RJ45 {k + 1}"), [box((68 + 4 * (k % 4), 67.72, z0 + 0.4), (0.08, 0.06, 0.1))], DAT, st,
              ptype="NETWORK", proxy=0.05)
    g.add("IfcCommunicationsAppliance", "Network Rack NR-1", [box((88.9, 56.5, 1.0), (0.6, 0.6, 2.0))], DAT, "admin1", ptype="NETWORK", tag="NR-1")
    for k in range(5):
        g.add("IfcCommunicationsAppliance", pick(f"CCTV Camera CAM-{k + 1}", f"Security Devices:Camera:{g.rid()}", f"CAM-{k + 1}"), [box((66 + 4.5 * k, 53.9, 3.6), (0.2, 0.2, 0.2))], SEC, "admin1", ptype="NETWORK", proxy=0.05)
    for k, x in enumerate((69.9, 77.4)):
        g.add("IfcCommunicationsAppliance", pick(f"Card Reader CR-{k + 1}", f"Security Devices:Card Reader:{g.rid()}"), [box((x, 53.96, 1.2), (0.1, 0.06, 0.12))], SEC, "admin1", ptype="NETWORK")
    for k in range(10):
        st, z0 = ("admin1", 0.0) if k < 5 else ("admin2", 4.2)
        g.add("IfcSensor", pick(f"Smoke Detector SD-{k + 1}", f"Fire Alarm Devices:Smoke Detector:{g.rid()}", f"SMK-{k + 1}"), [box((68 + 4 * (k % 5), 60.3, z0 + 3.04), (0.15, 0.15, 0.1))], ALM, st,
              ptype="SMOKESENSOR", proxy=0.05)
    for k in range(3):
        g.add("IfcAlarm", pick(f"Horn Strobe HS-{k + 1}", f"Fire Alarm Devices:Horn Strobe:{g.rid()}"), [box((70 + 8 * k, 58.1, 2.4), (0.15, 0.08, 0.15))], ALM, "admin1", ptype="SIREN")
    g.add("IfcCommunicationsAppliance", "FACP-1 Fire Alarm Panel", [box((89.0, 58.15, 1.4), (0.5, 0.2, 0.7))], ALM, "admin1", ptype="NETWORK", tag="FACP-1")
    g.add("IfcController", "PLC-1", [box((70, 56.0, 0.8), (1.8, 0.7, 1.6))], PLC, "admin1", ptype="PROGRAMMABLE", tag="PLC-1")
    g.add("IfcController", "RTU-1", [box((74, 56.0, 0.8), (0.8, 0.4, 1.6))], PLC, "admin1", ptype="PROGRAMMABLE", tag="RTU-1")
    return g


def main(argv=None):
    ap = argparse.ArgumentParser(description="Independent water treatment works IFC and truth")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("-o", "--out", default=os.path.join(HERE, "..", "models", "independent", "Water-Works.ifc"))
    ap.add_argument("--no-check", action="store_true", help="write the files even when a self-check fails")
    a = ap.parse_args(argv)
    g = build(a.seed)
    name = os.path.splitext(os.path.basename(a.out))[0]
    truth_path = os.path.splitext(a.out)[0] + ".truth.json"
    errs = g.check()
    assert len(g.ents) == len(g.truth)
    if errs and not a.no_check:
        print("SELF-CHECK FAILED:", file=sys.stderr)
        for e in errs:
            print("  " + e, file=sys.stderr)
        print(f"({len(g.ents)} products so far)", file=sys.stderr)
        sys.exit(1)
    g.finish(a.out, truth_path, name)
    print(f"wrote {a.out} and {truth_path}")
    print(f"{len(g.ents)} products")
    for c, n in sorted(collections.Counter(c for _, c in g.ents).items(), key=lambda x: (-x[1], x[0])):
        print(f"  {c:32s} {n}")
    print("truth by discipline:", dict(sorted(collections.Counter(t["discipline"] for t in g.truth.values()).items())))
    print(f"unnamed {sum(1 for t in g.truth.values() if not t['name'])}, proxies {sum(1 for t in g.truth.values() if t['ifcClass'] == 'IfcBuildingElementProxy')}, systems {sorted(g.sysmap)}")
    print("self-checks passed" if not errs else f"{len(errs)} self-check problems ignored (--no-check)")


if __name__ == "__main__":
    main()
