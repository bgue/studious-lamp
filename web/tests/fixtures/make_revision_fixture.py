#!/usr/bin/env python3
"""Generates the revision fixtures in tests/fixtures/ifc from models/AC20-FZK-Haus.ifc (the "base", v1) with ifcopenshell.

    python3 web/tests/fixtures/make_revision_fixture.py            # fzk-v2.ifc, fzk-v2.truth.json and fzk-v2-reguid.ifc

fzk-v2.ifc (seed 1) changes the base like a real revision:
  * moves 3 elements by 5 mm and 2 by 250 mm, turns 1 by 90 degrees (placement only)
  * deletes 4 elements: one window together with its opening (its wall's geometry changes), two rafters, one railing
  * adds 3 elements (copies of existing ones with new GlobalIds at new places)
  * re-GUIDs 6 elements that are otherwise unchanged (the diff must rematch them)
  * changes the class of 1 element, the type name (ObjectType) of 2, the Pset_WallCommon value of 3 walls, and lengthens 1 wall
fzk-v2-reguid.ifc is fzk-v2.ifc with every GlobalId regenerated and the whole model shifted by (1000, 0, 0) m: it exercises the
global-offset step of the match. fzk-v2.truth.json lists every expected category and flag set, and the old -> new GlobalId map.
Everything is deterministic: the same inputs give the same bytes.
"""
import json
import math
import os
import random
import sys
import time
import uuid

import ifcopenshell
import ifcopenshell.api
import ifcopenshell.guid
import ifcopenshell.util.element
import ifcopenshell.util.schema

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.dirname(os.path.dirname(HERE))
SRC = os.path.join(WEB, "..", "models", "AC20-FZK-Haus.ifc")
OUT = os.path.join(HERE, "ifc")
SEED = 1
STAMP = "2026-01-01T00:00:00"

rng = random.Random(SEED)
time.time = lambda: 1767225600.0  # ifcopenshell stamps new IfcOwnerHistory with the clock: freeze it so the bytes repeat


def new_guid() -> str:
    return ifcopenshell.guid.compress(uuid.UUID(int=rng.getrandbits(128)).hex)


# every GUID that the api makes (new relationships) comes from the seeded generator, so the output is reproducible
ifcopenshell.guid.new = new_guid


def by_name(f):
    return {p.Name: p for p in f.by_type("IfcProduct") if p.Name and not p.is_a("IfcOpeningElement")}


def relocate(f, product, dx=0.0, dy=0.0, dz=0.0, turn90=False):
    """Move an element in its parent's frame and/or turn it by 90 degrees about its own vertical axis (new placement entities, so a
    shared point or axis is never edited in place)."""
    lp = product.ObjectPlacement
    ax = lp.RelativePlacement
    x, y, z = ax.Location.Coordinates
    loc = f.create_entity("IfcCartesianPoint", Coordinates=(x + dx, y + dy, z + dz))
    axis = ax.Axis
    ref = ax.RefDirection
    if turn90:
        zax = axis.DirectionRatios if axis else (0.0, 0.0, 1.0)
        xax = ref.DirectionRatios if ref else (1.0, 0.0, 0.0)
        # z cross x
        nx = (zax[1] * xax[2] - zax[2] * xax[1], zax[2] * xax[0] - zax[0] * xax[2], zax[0] * xax[1] - zax[1] * xax[0])
        ref = f.create_entity("IfcDirection", DirectionRatios=nx)
        axis = f.create_entity("IfcDirection", DirectionRatios=tuple(zax))
    lp.RelativePlacement = f.create_entity("IfcAxis2Placement3D", Location=loc, Axis=axis, RefDirection=ref)


def container_of(f, p):
    for r in f.get_inverse(p):
        if r.is_a("IfcRelContainedInSpatialStructure"):
            return r.RelatingStructure
    return None


def build_v2():
    f = ifcopenshell.open(SRC)
    f.header.file_name.time_stamp = STAMP
    n = by_name(f)
    truth = []

    def note(p, category, flags, **extra):
        truth.append({"name": p.Name, "ifcClass": p.is_a(), "baseGuid": extra.pop("baseGuid", p.GlobalId), "headGuid": extra.pop("headGuid", p.GlobalId), "category": category, "flags": flags, **extra})

    # --- moves (placement only)
    for name in ("Sparren-3", "Sparren-8", "Pfette-1-1"):
        relocate(f, n[name], dx=0.005)
        note(n[name], "changed", ["placement"], moveMm=5.0)
    for name in ("Sparren-12", "Unterzug-1"):
        relocate(f, n[name], dy=0.25)
        note(n[name], "changed", ["placement"], moveMm=250.0)
    relocate(f, n["First"], turn90=True)
    note(n["First"], "changed", ["placement"], rotated=True)

    # --- type name (ObjectType) of two rafters
    for name in ("Sparren-10", "Sparren-11"):
        n[name].ObjectType = "Sparren 80 x 160 (revised)"
        note(n[name], "changed", ["type"])

    # --- Pset_WallCommon.ThermalTransmittance of three walls, nothing else
    ue = ifcopenshell.util.element
    for name in ("Wand-Int-ERDG-1", "Wand-Int-ERDG-4", "Wand-Int-ERDG-5"):
        w = n[name]
        ps = ue.get_psets(w)["Pset_WallCommon"]
        rel = [r for r in f.get_inverse(w) if r.is_a("IfcRelDefinesByProperties") and r.RelatingPropertyDefinition.Name == "Pset_WallCommon"][0]
        for prop in rel.RelatingPropertyDefinition.HasProperties:
            if prop.Name == "ThermalTransmittance":
                prop.NominalValue = f.create_entity(prop.NominalValue.is_a(), 0.9)
        note(w, "changed", ["properties"], before=ps["ThermalTransmittance"], after=0.9)

    # --- lengthen one wall: the profile points at the far end move 0.5 m (Wand-Int-ERDG-2 has no door or window)
    wall = n["Wand-Int-ERDG-2"]
    solid = [i for r in wall.Representation.Representations for i in r.Items if i.is_a("IfcExtrudedAreaSolid")][0]
    pts = solid.SweptArea.OuterCurve.Points
    far = max(p.Coordinates[0] for p in pts)
    for p in pts:
        if abs(p.Coordinates[0] - far) < 1e-9:
            p.Coordinates = (far + 0.5, p.Coordinates[1])
    note(wall, "changed", ["geometry"])

    # --- class change: a rafter becomes a beam
    m = n["Sparren-40"]
    old = m.GlobalId
    m = ifcopenshell.util.schema.reassign_class(f, m, "IfcBeam")  # this occurrence only (the api version also retypes every sibling)
    note(m, "changed", ["class"], baseGuid=old)

    # --- deletions: a window and its opening (the host wall loses its hole), two rafters, one railing
    window = n["EG-Fenster-6"]
    opening = window.FillsVoids[0].RelatingOpeningElement
    host = opening.VoidsElements[0].RelatingBuildingElement
    note(window, "deleted", [], headGuid=None)
    note(host, "changed", ["geometry"], becauseOf="opening of the deleted window removed")
    ifcopenshell.api.run("root.remove_product", f, product=window)
    ifcopenshell.api.run("root.remove_product", f, product=opening)
    for name in ("Sparren-30", "Sparren-31"):
        note(n[name], "deleted", [], headGuid=None)
        ifcopenshell.api.run("root.remove_product", f, product=n[name])
    rail = [r for r in f.by_type("IfcRailing") if r.GlobalId == "09axaKU7X1_O8n6dmmiZ1E"][0]
    note(rail, "deleted", [], headGuid=None)
    ifcopenshell.api.run("root.remove_product", f, product=rail)

    # --- additions: copies with new GlobalIds at new places
    for name, d in (("Sparren-5", (0.0, 3.1, 0.0)), ("Sparren-6", (0.0, 3.1, 0.0)), ("Dach-1", (0.0, 0.0, 4.0))):
        src = n[name]
        cp = ifcopenshell.api.run("root.copy_class", f, product=src)
        cp.GlobalId = new_guid()
        cp.Representation = ifcopenshell.util.element.copy_deep(f, src.Representation)  # copy_class leaves the copy without a shape
        cp.Name = f"{src.Name} (copy)"
        relocate(f, cp, *d)
        if container_of(f, cp) is None and container_of(f, src) is not None:
            ifcopenshell.api.run("spatial.assign_container", f, products=[cp], relating_structure=container_of(f, src))
        note(cp, "new", [], baseGuid=None)

    # --- re-GUID six unchanged elements
    for name in ("Sparren-7", "Pfette-2-1", "Dach-2", "Haustuer", "Wendeltreppe", "Wand-Int-ERDG-3"):
        p = n[name]
        old = p.GlobalId
        p.GlobalId = new_guid()
        note(p, "rematched", [], baseGuid=old, headGuid=p.GlobalId)

    return f, truth


def reguid_all(f):
    """Every GlobalId regenerated, the whole model shifted by (1000, 0, 0) m (the site placement carries everything)."""
    mapping = {}
    for e in f.by_type("IfcRoot"):
        old = e.GlobalId
        e.GlobalId = new_guid()
        mapping[old] = e.GlobalId
    site = f.by_type("IfcSite")[0]
    ax = site.ObjectPlacement.RelativePlacement
    x, y, z = ax.Location.Coordinates
    ax.Location = f.create_entity("IfcCartesianPoint", Coordinates=(x + 1000.0, y, z))
    return mapping


def main():
    os.makedirs(OUT, exist_ok=True)
    f, truth = build_v2()
    p2 = os.path.join(OUT, "fzk-v2.ifc")
    f.write(p2)
    mapping = reguid_all(f)
    f.write(os.path.join(OUT, "fzk-v2-reguid.ifc"))
    doc = {
        "format": "xray-revision-truth/1",
        "generator": "tests/fixtures/make_revision_fixture.py (seed 1)",
        "base": "models/AC20-FZK-Haus.ifc",
        "head": "fzk-v2.ifc",
        "reguidHead": "fzk-v2-reguid.ifc",
        "reguidShift": [1000.0, 0.0, 0.0],
        "convention": "changes lists every element of fzk-v2 that is not unchanged. category new has no baseGuid; deleted has no head element (headGuid is the base GlobalId). flags are the expected ChangeFlags. moveMm is the placement move. reguidMap maps every GlobalId of fzk-v2 to its GlobalId in fzk-v2-reguid.",
        "changes": truth,
        "reguidMap": mapping,
    }
    with open(os.path.join(OUT, "fzk-v2.truth.json"), "w") as fh:
        json.dump(doc, fh, indent=1, sort_keys=True)
        fh.write("\n")
    print("wrote", p2, len(truth), "changes")


if __name__ == "__main__":
    sys.exit(main())
