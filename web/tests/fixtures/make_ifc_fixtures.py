#!/usr/bin/env python3
"""Generates the small IFC fixtures in tests/fixtures/ifc (IFC4 and IFC2X3) with ifcopenshell.

    python3 web/tests/fixtures/make_ifc_fixtures.py

Each file has two storeys (Level 1 at 0 m, Level 2 at 3 m), a wall with a door in an opening (void + fill), three duct
elements joined by ports (IFC4: IfcRelNests + IfcRelConnectsPorts, IFC2X3: IfcRelConnectsPortToElement), an
IfcDistributionSystem, a slab with an IfcMaterial, a beam contained in the building (storey fallback) and an unstyled
duct next to a styled wall. The reference result is whatever tools/ifc2glb.py makes of the same files.
"""
import os
import sys

import ifcopenshell
import ifcopenshell.api
import ifcopenshell.guid

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ifc")


def box(f, ctx, size, at):
    prof = f.create_entity("IfcRectangleProfileDef", ProfileType="AREA", XDim=size[0], YDim=size[1])
    if f.schema == "IFC2X3":  # Position is mandatory in IFC2X3
        prof.Position = f.create_entity("IfcAxis2Placement2D", Location=f.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0)))
    rep = ifcopenshell.api.run("geometry.add_profile_representation", f, context=ctx, profile=prof, depth=size[2])
    return rep


def place(f, elem, xyz):
    ifcopenshell.api.run("geometry.edit_object_placement", f, product=elem,
                         matrix=[[1, 0, 0, xyz[0]], [0, 1, 0, xyz[1]], [0, 0, 1, xyz[2]], [0, 0, 0, 1]])


def make(schema: str, path: str) -> None:
    f = ifcopenshell.api.run("project.create_file", version=schema)
    if schema == "IFC2X3":  # IFC2X3 entities need an IfcOwnerHistory
        import ifcopenshell.api.owner.settings as osettings
        person = f.create_entity("IfcPerson", FamilyName="Fixture")
        org = f.create_entity("IfcOrganization", Name="Fixture")
        user = f.create_entity("IfcPersonAndOrganization", ThePerson=person, TheOrganization=org)
        app = f.create_entity("IfcApplication", ApplicationDeveloper=org, Version="1", ApplicationFullName="fixture", ApplicationIdentifier="fixture")
        osettings.get_user = lambda ifc: user
        osettings.get_application = lambda ifc: app
    proj = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcProject", name="Fixture")
    ifcopenshell.api.run("unit.assign_unit", f, length={"is_metric": True, "raw": "METERS"})
    mctx = ifcopenshell.api.run("context.add_context", f, context_type="Model")
    body = ifcopenshell.api.run("context.add_context", f, context_type="Model", context_identifier="Body",
                                target_view="MODEL_VIEW", parent=mctx)
    site = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcSite", name="Site")
    bld = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcBuilding", name="Building")
    ifcopenshell.api.run("aggregate.assign_object", f, products=[site], relating_object=proj)
    ifcopenshell.api.run("aggregate.assign_object", f, products=[bld], relating_object=site)
    st1 = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcBuildingStorey", name="Level 1")
    st2 = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcBuildingStorey", name="Level 2")
    st1.Elevation = 0.0
    st2.Elevation = 3.0
    ifcopenshell.api.run("aggregate.assign_object", f, products=[st1, st2], relating_object=bld)

    # styled wall with an opening and a door
    wall = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcWall", name="Wall A")
    wall.Representation = f.create_entity("IfcProductDefinitionShape", Representations=[box(f, body, (4.0, 0.2, 2.8), None)])
    place(f, wall, (2.0, 0.0, 0.0))
    ifcopenshell.api.run("spatial.assign_container", f, products=[wall], relating_structure=st1)
    style = ifcopenshell.api.run("style.add_style", f, name="Brick")
    ifcopenshell.api.run("style.add_surface_style", f, style=style, ifc_class="IfcSurfaceStyleShading",
                         attributes={"SurfaceColour": {"Red": 0.8, "Green": 0.3, "Blue": 0.2}})
    ifcopenshell.api.run("style.assign_representation_styles", f, shape_representation=wall.Representation.Representations[0], styles=[style])
    opening = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcOpeningElement", name="Opening")
    opening.Representation = f.create_entity("IfcProductDefinitionShape", Representations=[box(f, body, (0.9, 0.5, 2.0), None)])
    place(f, opening, (2.0, 0.0, 0.0))
    ifcopenshell.api.run("feature.add_feature", f, feature=opening, element=wall)
    door = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcDoor", name="Door")
    door.Representation = f.create_entity("IfcProductDefinitionShape", Representations=[box(f, body, (0.8, 0.1, 2.0), None)])
    place(f, door, (2.0, 0.0, 0.0))
    ifcopenshell.api.run("spatial.assign_container", f, products=[door], relating_structure=st1)
    ifcopenshell.api.run("feature.add_filling", f, opening=opening, element=door)

    SEG, FIT = ("IfcDuctSegment", "IfcDuctFitting") if schema != "IFC2X3" else ("IfcFlowSegment", "IfcFlowFitting")
    # three unstyled duct elements joined by ports, in one system
    seg1 = ifcopenshell.api.run("root.create_entity", f, ifc_class=SEG, name="Duct 1")
    seg2 = ifcopenshell.api.run("root.create_entity", f, ifc_class=SEG, name="Duct 2")
    fit = ifcopenshell.api.run("root.create_entity", f, ifc_class=FIT, name="Elbow")
    for i, e in enumerate((seg1, seg2, fit)):
        e.Representation = f.create_entity("IfcProductDefinitionShape", Representations=[box(f, body, (0.4, 0.3, 2.0), None)])
        place(f, e, (1.0 + 2.5 * i, 2.0, 2.5))
        ifcopenshell.api.run("spatial.assign_container", f, products=[e], relating_structure=st1)
    pa = ifcopenshell.api.run("system.add_port", f, element=seg1)
    pb = ifcopenshell.api.run("system.add_port", f, element=seg2)
    pc = ifcopenshell.api.run("system.add_port", f, element=seg2)
    pd = ifcopenshell.api.run("system.add_port", f, element=fit)
    ifcopenshell.api.run("system.connect_port", f, port1=pa, port2=pb)
    ifcopenshell.api.run("system.connect_port", f, port1=pc, port2=pd)
    sysm = ifcopenshell.api.run("system.add_system", f, ifc_class="IfcDistributionSystem" if schema != "IFC2X3" else "IfcSystem")
    sysm.Name = "Supply Air"
    ifcopenshell.api.run("system.assign_system", f, products=[seg1, seg2, fit], system=sysm)

    # slab on Level 2 with a material
    slab = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcSlab", name="Slab")
    slab.Representation = f.create_entity("IfcProductDefinitionShape", Representations=[box(f, body, (6.0, 5.0, 0.25), None)])
    place(f, slab, (3.0, 2.5, 3.0))
    ifcopenshell.api.run("spatial.assign_container", f, products=[slab], relating_structure=st2)
    mat = ifcopenshell.api.run("material.add_material", f, name="Concrete C30")
    ifcopenshell.api.run("material.assign_material", f, products=[slab], material=mat)

    # beam contained in the building only: the converter falls back to the nearest storey at or below its lowest point
    beam = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcBeam", name="Beam")
    beam.Representation = f.create_entity("IfcProductDefinitionShape", Representations=[box(f, body, (3.0, 0.3, 0.4), None)])
    place(f, beam, (3.0, 4.0, 3.4))
    ifcopenshell.api.run("spatial.assign_container", f, products=[beam], relating_structure=bld)

    add_props(f, wall, slab, schema)
    f.write(path)


def add_props(f, wall, slab, schema: str) -> None:
    """Hover-info properties: attributes, a Pset_*Common, a custom set (long string, integer, measure), base quantities."""
    wall.ObjectType = "Wall:Brick 200"
    wall.Tag = "W-001"
    wall.Description = "Exterior brick wall"
    pset = ifcopenshell.api.run("pset.add_pset", f, product=wall, name="Pset_WallCommon")
    ifcopenshell.api.run("pset.edit_pset", f, pset=pset, properties={
        "IsExternal": True, "LoadBearing": False, "FireRating": "EI60", "ThermalTransmittance": 1.234567})
    extra = ifcopenshell.api.run("pset.add_pset", f, product=wall, name="Acme_Custom")
    ifcopenshell.api.run("pset.edit_pset", f, pset=extra, properties={
        "Note": "x" * 100, "Count": 12345, "Flag": False, "Ratio": 0.000123456})
    qto = ifcopenshell.api.run("pset.add_qto", f, product=wall, name="Qto_WallBaseQuantities")
    ifcopenshell.api.run("pset.edit_qto", f, qto=qto, properties={
        "Length": 4.0, "Height": 2.8, "Width": 0.2, "NetVolume": 2.2399999, "Mystery": 7.0})
    pset2 = ifcopenshell.api.run("pset.add_pset", f, product=slab, name="Pset_SlabCommon")
    ifcopenshell.api.run("pset.edit_pset", f, pset=pset2, properties={"LoadBearing": True, "Reference": "S-250"})
    qto2 = ifcopenshell.api.run("pset.add_qto", f, product=slab, name="BaseQuantities")
    ifcopenshell.api.run("pset.edit_qto", f, qto=qto2, properties={"GrossArea": 30.0, "NetVolume": 7.5})


def make_mm(path: str) -> None:
    """One wall in a millimetre project (area and volume units SI metres): the reader must convert to SI."""
    f = ifcopenshell.api.run("project.create_file", version="IFC4")
    proj = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcProject", name="Millimetres")
    ifcopenshell.api.run("unit.assign_unit", f, length={"is_metric": True, "raw": "MILLIMETERS"},
                         area={"is_metric": True, "raw": "SQUARE_METERS"}, volume={"is_metric": True, "raw": "CUBIC_METERS"})
    mctx = ifcopenshell.api.run("context.add_context", f, context_type="Model")
    body = ifcopenshell.api.run("context.add_context", f, context_type="Model", context_identifier="Body",
                                target_view="MODEL_VIEW", parent=mctx)
    site = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcSite", name="Site")
    bld = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcBuilding", name="Building")
    st = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcBuildingStorey", name="Level 1")
    st.Elevation = 0.0
    ifcopenshell.api.run("aggregate.assign_object", f, products=[site], relating_object=proj)
    ifcopenshell.api.run("aggregate.assign_object", f, products=[bld], relating_object=site)
    ifcopenshell.api.run("aggregate.assign_object", f, products=[st], relating_object=bld)
    wall = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcWall", name="Wall mm")
    wall.Representation = f.create_entity("IfcProductDefinitionShape", Representations=[box(f, body, (4000.0, 200.0, 2800.0), None)])
    place(f, wall, (2000.0, 0.0, 0.0))
    ifcopenshell.api.run("spatial.assign_container", f, products=[wall], relating_structure=st)
    wall.PredefinedType = "SOLIDWALL"
    pset = ifcopenshell.api.run("pset.add_pset", f, product=wall, name="Pset_WallCommon")
    ifcopenshell.api.run("pset.edit_pset", f, pset=pset, properties={"IsExternal": True, "Reference": "mm-1"})
    extra = ifcopenshell.api.run("pset.add_pset", f, product=wall, name="Acme_Dims")
    ifcopenshell.api.run("pset.edit_pset", f, pset=extra, properties={
        "Thickness": f.create_entity("IfcPositiveLengthMeasure", 200.0), "Area": f.create_entity("IfcAreaMeasure", 11.2)})
    qto = ifcopenshell.api.run("pset.add_qto", f, product=wall, name="Qto_WallBaseQuantities")
    ifcopenshell.api.run("pset.edit_qto", f, qto=qto, properties={"Length": 4000.0, "Height": 2800.0, "NetSideArea": 11.2})
    f.write(path)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    for schema, name in (("IFC4", "ports-ifc4.ifc"), ("IFC2X3", "ports-ifc2x3.ifc")):
        make(schema, os.path.join(OUT, name))
        print("wrote", name, file=sys.stderr)
    make_mm(os.path.join(OUT, "props-mm-ifc4.ifc"))
    print("wrote props-mm-ifc4.ifc", file=sys.stderr)
