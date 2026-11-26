// The concrete sets in the classify service: a run writes XR_Concrete* properties, the query engine sees them, exports gain the columns,
// a manual role wins and survives a run, the switch removes everything.

import { describe, expect, it } from 'vitest';
import { ClassifyService } from '../src/classify';
import { queryModel } from './facets-query';
import type { ElementRecord, SceneModel } from '../src/types';
import { boundsOf, box } from './facets-helpers';
import type { Mesh } from './facets-helpers';

interface Spec { cls: string; name: string; mesh: Mesh; props?: Record<string, string | number | boolean>; material?: string; storey?: number }

// viewer frame, y up
const SPECS: Spec[] = [
  { cls: 'IfcSlab', name: 'Ground slab', mesh: box(0, -0.1, 0, 8.4, 0.2, 6.4), material: 'Concrete C25/30', props: { 'Attr.PredefinedType': 'BASESLAB' } }, // 0
  { cls: 'IfcColumn', name: 'Col 1', mesh: box(2, 1.4, 1, 0.3, 2.8, 0.3), material: 'Concrete C25/30' }, // 1
  { cls: 'IfcColumn', name: 'Col 2', mesh: box(-2, 1.4, 1, 0.3, 2.8, 0.3), material: 'Concrete C25/30' }, // 2
  { cls: 'IfcSlab', name: 'Floor slab', mesh: box(0, 2.9, 0, 8.4, 0.2, 6.4), material: 'Concrete C25/30', props: { 'Attr.PredefinedType': 'FLOOR' }, storey: 1 }, // 3
  { cls: 'IfcWall', name: 'Brick wall', mesh: box(0, 1.4, -3, 8, 2.8, 0.2), material: 'Brick' }, // 4 (not concrete)
  { cls: 'IfcWall', name: 'Concrete wall', mesh: box(0, 1.4, 3, 8, 2.8, 0.2), material: 'Concrete C25/30' }, // 5
];

function build(): { model: SceneModel; meshes: Map<number, Mesh> } {
  const meshes = new Map<number, Mesh>();
  const elements: ElementRecord[] = SPECS.map((s, id) => {
    meshes.set(id, s.mesh);
    return { id, globalId: `G${id}`, ifcClass: s.cls, name: s.name, storey: s.storey ?? 0, ...(s.material ? { material: s.material } : {}), color: [1, 1, 1, 1], bounds: boundsOf(s.mesh), ...(s.props ? { props: { ...s.props } } : {}) };
  });
  const model: SceneModel = { schema: 'xray-model/1', units: 'm', originShift: [0, 0, 0], storeys: [{ id: 0, name: 'EG', elevation: 0 }, { id: 1, name: 'OG', elevation: 3 }], elements, relations: { voids: [], fills: [], hosts: [], ports: [], systems: [] }, byGlobalId: new Map(elements.map((e) => [e.globalId, e.id])) };
  return { model, meshes };
}

const service = (meshes: Map<number, Mesh>): ClassifyService => new ClassifyService({ storage: null, keyStorages: { session: null, local: null }, facetGeometry: { mesh: (id) => meshes.get(id) ?? null } });

describe('concrete in the service', () => {
  it('a run classifies the concrete elements, writes properties and exports them', async () => {
    const { model, meshes } = build();
    const svc = service(meshes);
    svc.setModel(model, 'house');
    await svc.classify('all');
    const c = (i: number) => svc.concreteOf(i);
    expect(c(0).ConcreteElement?.code).toBe('SLAB_ON_GRADE');
    expect(c(1).ConcreteElement?.code).toBe('COLUMN');
    expect(c(3).ConcreteElement?.code).toBe('SUSPENDED_SLAB');
    expect(c(5).ConcreteElement?.code).toBe('WALL');
    expect(c(4).ConcreteElement).toBeUndefined();
    expect(c(3).ConcreteGeometry?.fields['Volume']).toBeCloseTo(8.4 * 6.4 * 0.2, 2);
    expect(c(0).ConcreteElement?.fields['Mark']).toBe('SG0-01');
    expect(c(3).ConcreteElement?.fields['Mark']).toBe('S1-01');
    expect(model.elements[3]!.props!['XR_ConcreteElement.Code']).toBe('SUSPENDED_SLAB');
    expect(model.elements[3]!.props!['XR_ConcreteSpec.StrengthClass']).toBe('C25/30');
    expect(model.elements[4]!.props?.['XR_ConcreteElement.Code']).toBeUndefined();
    expect(queryModel(model, "ConcreteElement = 'COLUMN'")).toEqual([1, 2]);
    const csv = svc.export('csv');
    expect(csv.split('\r\n')[0]).toContain('XR_ConcreteGeometry.Volume');
    expect(csv).toContain('SUSPENDED_SLAB');
    const json = JSON.parse(svc.export('json')) as { concreteScheme?: string; concrete?: Record<string, unknown> };
    expect(json.concreteScheme).toBe('xr-concrete/1');
    expect(Object.keys(json.concrete!).sort()).toEqual(['G0', 'G1', 'G2', 'G3', 'G5']);
  });

  it('a manual role wins, changes the mark and survives another run', async () => {
    const { model, meshes } = build();
    const svc = service(meshes);
    svc.setModel(model, 'house');
    await svc.classify('all');
    await svc.overrideConcrete(3, 'ConcreteElement', 'TRANSFER_SLAB');
    expect(svc.concreteOf(3).ConcreteElement).toMatchObject({ code: 'TRANSFER_SLAB', source: 'manual' });
    expect(svc.concreteOf(3).ConcreteElement?.fields['Mark']).toBe('TS1-01');
    expect(model.elements[3]!.props!['XR_ConcreteElement.Code']).toBe('TRANSFER_SLAB');
    await svc.classify('all');
    expect(svc.concreteOf(3).ConcreteElement?.code).toBe('TRANSFER_SLAB');
    await expect(svc.overrideConcrete(3, 'ConcreteElement', 'COLUMNN')).rejects.toThrow(/not a Element code/);
  });

  it('the switch removes the sets and the properties; clear() removes them too', async () => {
    const { model, meshes } = build();
    const svc = service(meshes);
    svc.setModel(model, 'house');
    await svc.classify('all');
    expect(svc.concreteResults().size).toBe(5);
    svc.setConcreteEnabled(false);
    expect(svc.concreteResults().size).toBe(0);
    expect(model.elements[3]!.props!['XR_ConcreteElement.Code']).toBeUndefined();
    svc.setConcreteEnabled(true);
    await svc.classify('all');
    expect(svc.concreteResults().size).toBe(5);
    svc.clear();
    expect(svc.concreteResults().size).toBe(0);
    expect(model.elements[3]!.props!['XR_ConcreteElement.Code']).toBeUndefined();
  });

  it('writePset off: results kept, no properties', async () => {
    const { model, meshes } = build();
    const svc = service(meshes);
    svc.setModel(model, 'house');
    svc.patch({ writePset: false });
    await svc.classify('all');
    expect(svc.concreteResults().size).toBe(5);
    expect(model.elements[3]!.props!['XR_ConcreteElement.Code']).toBeUndefined();
  });
});
