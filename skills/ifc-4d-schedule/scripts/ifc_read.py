#!/usr/bin/env python3
"""Read the building elements of an IFC into JSON for linking: GlobalId, class, name, type, storey, material, bounding box,
selected properties (always the Xray_4D set), and 4D links already in the file (IfcTask assignments).

    python ifc_read.py model.ifc [--props Pset_WallCommon.IsExternal,Pset_X.Zone] [--all-props] [-o model.json]

Needs ifcopenshell (0.8.x). Output schema 'xray-ifc-json/1' (../reference/data-formats.md). stdout carries only JSON.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

OUT = sys.stdout
sys.stdout = sys.stderr  # ifcopenshell may print notes; keep stdout for the JSON
import ifcopenshell
import ifcopenshell.util.element as uel
import ifcopenshell.util.placement as upl

SKIP = ('IfcOpeningElement', 'IfcVirtualElement', 'IfcAnnotation', 'IfcSpace', 'IfcGrid', 'IfcSite', 'IfcBuilding', 'IfcBuildingStorey', 'IfcProject')


def storey_of(el) -> str | None:
    c = uel.get_container(el)
    while c is not None and not c.is_a('IfcBuildingStorey'):
        c = uel.get_aggregate(c) if hasattr(uel, 'get_aggregate') else None
    return c.Name if c is not None else None


def zones_of(el) -> list[str]:
    out = []
    for rel in getattr(el, 'HasAssignments', []) or []:
        if rel.is_a('IfcRelAssignsToGroup') and rel.RelatingGroup and rel.RelatingGroup.is_a('IfcZone'):
            out.append(rel.RelatingGroup.Name or '')
    return out


def material_of(el) -> str | None:
    m = uel.get_material(el, should_skip_usage=True)
    if m is None:
        return None
    for attr in ('Name',):
        if getattr(m, attr, None):
            return getattr(m, attr)
    layers = getattr(m, 'MaterialLayers', None) or getattr(m, 'Materials', None)
    if layers:
        first = layers[0]
        mat = getattr(first, 'Material', first)
        return getattr(mat, 'Name', None)
    return None


def bbox_of(el):
    """Axis-aligned box of the element's placement origin and its representation's bounding box if one is stored; None if unknown.
    (Exact geometry is not computed: the box is only used for ordering elements inside an activity.)"""
    try:
        m = upl.get_local_placement(el.ObjectPlacement)
        x, y, z = float(m[0][3]), float(m[1][3]), float(m[2][3])
        return [round(x, 3), round(y, 3), round(z, 3), round(x, 3), round(y, 3), round(z, 3)]
    except Exception:
        return None


def existing_links(f) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for rel in f.by_type('IfcRelAssignsToProduct'):
        for t in rel.RelatedObjects or []:
            if t.is_a('IfcTask') and t.Identification:
                out.setdefault(rel.RelatingProduct.GlobalId, []).append({'task': t.Identification, 'role': 'build'})
    for rel in f.by_type('IfcRelAssignsToProcess'):
        t = rel.RelatingProcess
        if t is not None and t.is_a('IfcTask') and t.Identification:
            role = 'remove' if (t.PredefinedType or '') in ('DEMOLITION', 'DISMANTLE', 'REMOVAL') else 'build'
            for o in rel.RelatedObjects or []:
                out.setdefault(o.GlobalId, []).append({'task': t.Identification, 'role': role})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description='Read IFC elements into JSON for 4D linking.')
    ap.add_argument('ifc')
    ap.add_argument('--props', default='', help='comma-separated Pset.Prop names to include')
    ap.add_argument('--all-props', action='store_true', help='include every property (large)')
    ap.add_argument('-o', '--out')
    a = ap.parse_args()
    raw = open(a.ifc, 'rb').read()
    f = ifcopenshell.open(a.ifc)
    wanted = {p.strip() for p in a.props.split(',') if p.strip()}
    links = existing_links(f)
    elements = []
    for el in f.by_type('IfcElement'):
        if el.is_a() in SKIP or any(el.is_a(s) for s in SKIP):
            continue
        psets = uel.get_psets(el)
        props: dict[str, object] = {}
        for pname, pvals in psets.items():
            for k, v in pvals.items():
                if k == 'id':
                    continue
                key = f'{pname}.{k}'
                if a.all_props or pname == 'Xray_4D' or key in wanted:
                    props[key] = v
        t = uel.get_type(el)
        e = {'globalId': el.GlobalId, 'class': el.is_a(), 'name': el.Name, 'type': t.Name if t is not None else None,
             'storey': storey_of(el), 'zones': zones_of(el), 'material': material_of(el), 'bbox': bbox_of(el), 'props': props}
        if el.GlobalId in links:
            e['tasks'] = links[el.GlobalId]
        elements.append({k: v for k, v in e.items() if v not in (None, [], {})})
    storeys = [{'name': s.Name, 'elevation': s.Elevation} for s in f.by_type('IfcBuildingStorey')]
    data = {'schema': 'xray-ifc-json/1', 'file': os.path.basename(a.ifc), 'fileHash': hashlib.sha256(raw).hexdigest(), 'ifcSchema': f.schema,
            'storeys': storeys, 'zones': sorted({z.Name for z in f.by_type('IfcZone') if z.Name}), 'elements': elements,
            'existingTasks': sorted({t.Identification for t in f.by_type('IfcTask') if t.Identification})}
    text = json.dumps(data, indent=2, ensure_ascii=False, default=str)
    if a.out:
        open(a.out, 'w', encoding='utf-8').write(text + '\n')
        classes: dict[str, int] = {}
        for e in elements:
            classes[e['class']] = classes.get(e['class'], 0) + 1
        print(json.dumps({'output': a.out, 'ifcSchema': f.schema, 'elements': len(elements), 'storeys': [s['name'] for s in storeys], 'classes': classes,
                          'elementsWithTasks': sum(1 for e in elements if 'tasks' in e)}, indent=2), file=OUT)
    else:
        OUT.write(text + '\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
