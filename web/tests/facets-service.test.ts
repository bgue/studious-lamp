// The facets in the classify service: a run measures and rules the facets after the discipline, writes XR_<Facet> properties,
// keeps manual choices, honours the switches, and exports the columns.

import { describe, expect, it } from 'vitest';
import { ClassifyService, signatureOf } from '../src/classify';
import { meshRayHits } from '../src/classify/facets/placementGeometry';
import { queryModel } from './facets-query';
import type { ElementRecord, SceneModel } from '../src/types';
import { boundsOf, box } from './facets-helpers';
import type { Mesh } from './facets-helpers';

interface Spec { cls: string; name: string; mesh: Mesh; props?: Record<string, string | number | boolean>; material?: string }

const SPECS: Spec[] = [
  { cls: 'IfcWall', name: 'North', mesh: box(0, 1.5, -3, 8, 3, 0.2), material: 'Brick', props: { 'Pset_WallCommon.IsExternal': true } }, // 0
  { cls: 'IfcWall', name: 'South', mesh: box(0, 1.5, 3, 8, 3, 0.2), material: 'Brick', props: { 'Pset_WallCommon.IsExternal': true } }, // 1
  { cls: 'IfcWall', name: 'East', mesh: box(4, 1.5, 0, 0.2, 3, 6), material: 'Brick' }, // 2 no property: geometry decides
  { cls: 'IfcWall', name: 'West', mesh: box(-4, 1.5, 0, 0.2, 3, 6), material: 'Brick' }, // 3
  { cls: 'IfcWall', name: 'Partition', mesh: box(0, 1.5, 0, 0.1, 3, 5.8), material: 'Gypsum plasterboard' }, // 4
  { cls: 'IfcSlab', name: 'Ground slab', mesh: box(0, -0.1, 0, 8.4, 0.2, 6.4), material: 'Concrete C25/30' }, // 5
  { cls: 'IfcSlab', name: 'Roof slab', mesh: box(0, 3.1, 0, 8.4, 0.2, 6.4), material: 'Concrete C25/30', props: { 'Attr.PredefinedType': 'ROOF' } }, // 6
  { cls: 'IfcColumn', name: 'Col 1', mesh: box(2, 1.5, 1, 0.3, 3, 0.3), material: 'Concrete' }, // 7
  { cls: 'IfcBuildingElementProxy', name: 'Col 2', mesh: box(-2, 1.5, 1, 0.3, 3, 0.3) }, // 8
  { cls: 'IfcWall', name: 'Flat wall', mesh: box(12, 0.1, 0, 5, 0.2, 3), material: 'Brick' }, // 9: lying flat
];

function build(): { model: SceneModel; meshes: Map<number, Mesh> } {
  const meshes = new Map<number, Mesh>();
  const elements: ElementRecord[] = SPECS.map((s, id) => {
    meshes.set(id, s.mesh);
    return { id, globalId: `G${id}`, ifcClass: s.cls, name: s.name, storey: 0, ...(s.material ? { material: s.material } : {}), color: [1, 1, 1, 1], bounds: boundsOf(s.mesh), ...(s.props ? { props: { ...s.props } } : {}) };
  });
  const model: SceneModel = { schema: 'xray-model/1', units: 'm', originShift: [0, 0, 0], storeys: [{ id: 0, name: 'EG', elevation: 0 }], elements, relations: { voids: [], fills: [], hosts: [], ports: [], systems: [] }, byGlobalId: new Map(elements.map((e) => [e.globalId, e.id])) };
  return { model, meshes };
}

function service(meshes: Map<number, Mesh>): ClassifyService {
  return new ClassifyService({
    storage: null,
    keyStorages: { session: null, local: null },
    facetGeometry: { mesh: (id) => meshes.get(id) ?? null, raycast: meshRayHits((id) => meshes.get(id)) },
  });
}

/** Split one CSV line (quoted cells may hold commas). */
const cells = (line: string): string[] => [...line.matchAll(/(?:^|,)("(?:[^"]|"")*"|[^,]*)/g)].map((m) => m[1]!.replace(/^"|"$/g, '').replace(/""/g, '"'));

describe('facets in the service', () => {
  it('a run gives every element an Orientation, exterior walls BOUNDARY, slabs HORIZONTAL, and writes XR_ properties', async () => {
    const { model, meshes } = build();
    const svc = service(meshes);
    svc.setModel(model, 'house');
    await svc.classify('all');
    for (const e of model.elements) expect(svc.facetsOf(e.id).Orientation, e.name).toBeDefined();
    const f = (i: number) => svc.facetsOf(i);
    expect([0, 1, 2, 3].map((i) => f(i).Placement?.code)).toEqual(['BOUNDARY', 'BOUNDARY', 'BOUNDARY', 'BOUNDARY']);
    expect(f(0).Placement?.source).toBe('ifc');
    expect(f(2).Placement?.source).toBe('geometry');
    expect(f(4).Placement?.code).toBe('INT');
    expect(f(5).Orientation?.code).toBe('HORIZONTAL');
    expect(f(6).Orientation?.code).toBe('HORIZONTAL');
    expect(f(7).Orientation?.code).toBe('VERTICAL');
    expect(f(7).Placement?.code).toBe('INT');
    expect(f(0).Trade?.code).toBe('MASON');
    expect(f(4).Trade?.code).toBe('DRYLN');
    expect(f(5).Trade?.code).toBe('CONC');
    expect(f(0).Phase?.code).toBe('ENVELOPE');
    expect(f(4).Phase?.code).toBe('FITOUT');
    expect(f(7).Phase?.code).toBe('FRAME');
    expect(f(8).ClassRepair).toMatchObject({ code: 'IfcColumn' });
    expect(f(9).Orientation).toMatchObject({ code: 'HORIZONTAL', needsReview: true });
    expect(f(9).Orientation?.fields['Plausible']).toBe(false);
    // properties are written, and the query engine sees them
    expect(model.elements[0]!.props!['XR_Trade.Code']).toBe('MASON');
    expect(model.elements[0]!.props!['XR_Placement.Code']).toBe('BOUNDARY');
    expect(model.elements[0]!.props!['XR_Classification.SchemeVersion']).toBe('xr-facets/1');
    expect(queryModel(model, "Trade = 'CONC'").length).toBe(3); // two slabs and the column
    expect(queryModel(model, 'XR_Orientation.Plausible = FALSE')).toEqual([9]);
    expect(queryModel(model, "Placement = 'BOUNDARY' and class = 'IfcWall'").length).toBe(4);
  });

  it('a switched-off facet writes nothing; switching on again and re-running brings it back', async () => {
    const { model, meshes } = build();
    const svc = service(meshes);
    svc.setModel(model, 'house');
    svc.setFacetEnabled('Trade', false);
    await svc.classify('all');
    expect(svc.facetsOf(0).Trade).toBeUndefined();
    expect(Object.keys(model.elements[0]!.props!).some((k) => k.startsWith('XR_Trade.'))).toBe(false);
    expect(model.elements[0]!.props!['XR_Phase.Code']).toBe('ENVELOPE'); // Phase still works from the rules
    svc.setFacetEnabled('Trade', true);
    await svc.classifyFacets('all');
    expect(model.elements[0]!.props!['XR_Trade.Code']).toBe('MASON');
    svc.setFacetEnabled('Phase', false);
    expect(Object.keys(model.elements[0]!.props!).some((k) => k.startsWith('XR_Phase.'))).toBe(false);
  });

  it('writePset off writes no facet properties; clear removes them', async () => {
    const { model, meshes } = build();
    const svc = service(meshes);
    svc.setModel(model, 'house');
    svc.patch({ writePset: false });
    await svc.classify('all');
    expect(svc.facetsOf(0).Trade?.code).toBe('MASON');
    expect(Object.keys(model.elements[0]!.props ?? {}).some((k) => k.startsWith('XR_'))).toBe(false);
    svc.patch({ writePset: true });
    expect(model.elements[0]!.props!['XR_Trade.Code']).toBe('MASON');
    svc.clear();
    expect(Object.keys(model.elements[0]!.props!).some((k) => k.startsWith('XR_'))).toBe(false);
  });

  it('a manual facet override wins, is written with source manual, and survives a new run', async () => {
    const { model, meshes } = build();
    const svc = service(meshes);
    svc.setModel(model, 'house');
    await svc.classify('all');
    const r = svc.overrideFacet(0, 'Trade', { code: 'FACADE' });
    expect(r.source).toBe('manual');
    expect(model.elements[0]!.props!['XR_Trade.Source']).toBe('manual');
    expect(model.elements[0]!.props!['XR_Trade.Code']).toBe('FACADE');
    await svc.classify('all');
    expect(svc.facetsOf(0).Trade).toMatchObject({ code: 'FACADE', source: 'manual' });
    expect(() => svc.overrideFacet(0, 'Trade', { code: 'NOPE' })).toThrow(/Trade code/);
    await svc.removeFacetOverride(0, 'Trade');
    expect(svc.facetsOf(0).Trade).toMatchObject({ code: 'MASON', source: 'rule' });
  });

  it('the exports carry the facet columns', async () => {
    const { model, meshes } = build();
    const svc = service(meshes);
    svc.setModel(model, 'house');
    await svc.classify('all');
    const csv = svc.export('csv').split('\r\n');
    const header = cells(csv[0]!);
    expect(header).toContain('XR_Trade.Code');
    expect(header).toContain('XR_Orientation.Tilt');
    const row = cells(csv.find((l) => l.startsWith('G0,'))!);
    expect(row[header.indexOf('XR_Trade.Code')]).toBe('MASON');
    const json = JSON.parse(svc.export('json')) as { facets: Record<string, { Placement: { code: string } }> };
    expect(json.facets['G0']!.Placement.code).toBe('BOUNDARY');
  });

  it('without geometry, Orientation is not measured and Placement comes from the element\'s own property only', async () => {
    const { model } = build();
    const svc = new ClassifyService({ storage: null, keyStorages: { session: null, local: null } });
    svc.setModel(model, 'house');
    await svc.classify('all');
    expect(svc.facetsOf(0).Orientation).toBeUndefined();
    expect(svc.facetsOf(0).Placement?.source).toBe('ifc');
    expect(svc.facetsOf(2).Placement).toBeUndefined();
  });
});

describe('facet results are never inputs', () => {
  it('written XR_ properties do not change the signature or the state of an element', async () => {
    const { model, meshes } = build();
    const svc = service(meshes);
    svc.setModel(model, 'house');
    const before = signatureOf(svc.buildInput(7)!);
    await svc.classify('all');
    expect(signatureOf(svc.buildInput(7)!)).toBe(before);
    expect(Object.keys(svc.buildInput(7)!.psets).some((k) => /^XR_(Trade|Placement|Material|Phase|Orientation|ClassRepair)$/.test(k))).toBe(false);
  });
});
