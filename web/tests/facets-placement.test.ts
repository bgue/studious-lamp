// Placement facet, geometric part: envelope test with horizontal rays on a synthetic house.

import { describe, expect, it } from 'vitest';
import { createPlacementProbe, meshRayHits } from '../src/classify/facets/placementGeometry';
import type { PlacementElement } from '../src/classify/facets/placementGeometry';
import { boundsOf, box } from './facets-helpers';
import type { Mesh } from './facets-helpers';

interface E { cls: string; mesh: Mesh; storey?: number | null; pre?: string }

function scene(list: E[], hosts: Array<[number, number]> = []) {
  const meshes = new Map<number, Mesh>(list.map((e, i) => [i, e.mesh]));
  const elements: PlacementElement[] = list.map((e, i) => ({ id: i, ifcClass: e.cls, bounds: boundsOf(e.mesh), storey: e.storey === undefined ? 0 : e.storey, ...(e.pre ? { predefinedType: e.pre } : {}) }));
  const hostOf = new Map(hosts.map(([f, w]) => [f, w]));
  const hostedBy = new Map<number, number[]>();
  for (const [f, w] of hosts) (hostedBy.get(w) ?? hostedBy.set(w, []).get(w)!).push(f);
  return createPlacementProbe({ elements, castHits: meshRayHits((id) => meshes.get(id)), hostOf: (id) => hostOf.get(id), hostedBy: (id) => hostedBy.get(id) ?? [] });
}

// A 8 x 6 m house, 3 m high, walls 0.2 m thick, centred on the origin in plan (viewer x, z).
const house = (): E[] => [
  { cls: 'IfcWall', mesh: box(0, 1.5, -3, 8, 3, 0.2) }, // 0 north
  { cls: 'IfcWall', mesh: box(0, 1.5, 3, 8, 3, 0.2) }, // 1 south
  { cls: 'IfcWall', mesh: box(4, 1.5, 0, 0.2, 3, 6) }, // 2 east
  { cls: 'IfcWall', mesh: box(-4, 1.5, 0, 0.2, 3, 6) }, // 3 west
  { cls: 'IfcWall', mesh: box(0, 1.5, 0, 0.2, 3, 5.8) }, // 4 interior partition along z
  { cls: 'IfcSlab', mesh: box(0, -0.1, 0, 8.4, 0.2, 6.4), pre: 'BASESLAB' }, // 5 ground slab
  { cls: 'IfcSlab', mesh: box(0, 3.1, 0, 8.4, 0.2, 6.4), pre: 'ROOF' }, // 6 roof slab
  { cls: 'IfcColumn', mesh: box(2, 1.5, 1, 0.3, 3, 0.3) }, // 7 inside
  { cls: 'IfcColumn', mesh: box(9, 1.5, 1, 0.3, 3, 0.3) }, // 8 outside
  { cls: 'IfcWindow', mesh: box(0, 1.5, -3, 1.2, 1.2, 0.1) }, // 9 in the north wall
  { cls: 'IfcWall', mesh: box(14, 1.5, 0, 4, 2, 0.2) }, // 10 free-standing garden wall, far away
];

describe('placement by geometry', () => {
  const p = scene(house(), [[9, 0]]);
  const ex = (id: number): string | undefined => p.probe(id)?.exposure;

  it('exterior walls are BOUNDARY, the partition is INT', () => {
    expect([0, 1, 2, 3].map(ex)).toEqual(['BOUNDARY', 'BOUNDARY', 'BOUNDARY', 'BOUNDARY']);
    expect(ex(4)).toBe('INT');
    expect(p.probe(0)!.confidence).toBeGreaterThanOrEqual(0.7);
  });

  it('a window in an exterior wall is BOUNDARY (its own host does not block it)', () => {
    expect(ex(9)).toBe('BOUNDARY');
  });

  it('a column inside is INT, a column outside the plan is EXT', () => {
    expect(ex(7)).toBe('INT');
    expect(p.probe(7)!.confidence).toBeGreaterThanOrEqual(0.6);
    expect(ex(8)).toBe('EXT');
  });

  it('the roof slab and the ground slab are BOUNDARY; the top is told from the predefined type or the level', () => {
    expect(ex(5)).toBe('BOUNDARY');
    expect(ex(6)).toBe('BOUNDARY');
  });

  it('an intermediate floor slab is INT', () => {
    const list = house();
    list.push({ cls: 'IfcSlab', mesh: box(0, 1.5, 0, 7.8, 0.2, 5.8) });
    const q = scene(list, [[9, 0]]);
    expect(q.probe(11)!.exposure).toBe('INT');
  });

  it('a free-standing wall far from the house is EXT or BOUNDARY-free: clear on both faces', () => {
    expect(ex(10)).toBe('EXT');
  });

  it('knows the building box and returns null for an unknown element', () => {
    expect(p.building).not.toBeNull();
    expect(p.probe(99)).toBeNull();
  });

  it('probeAll works in slices and reports progress', async () => {
    let yields = 0;
    const seen: number[] = [];
    const all = await p.probeAll(undefined, { sliceMs: 0, yieldFn: async () => { yields++; }, onProgress: (d) => seen.push(d) });
    expect(all.size).toBe(11);
    expect(yields).toBeGreaterThan(0);
    expect(seen[seen.length - 1]).toBe(11);
  });

  it('with no envelope in the model nothing is claimed with confidence', () => {
    const q = scene([{ cls: 'IfcColumn', mesh: box(0, 1.5, 0, 0.3, 3, 0.3) }]);
    expect(q.probe(0)!.confidence).toBeLessThan(0.5);
  });
});
