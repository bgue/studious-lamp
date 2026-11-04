import { describe, expect, it } from 'vitest';
import { BoxGeometry, Matrix4, Vector3 } from 'three';
import { parseModel } from '../src/model/loader';
import { MergedGeometry } from '../src/model/merged';
import { buildProceduralGlb, proceduralSidecar } from '../src/model/procedural';
import { BvhGeometryProvider } from '../src/render/geometry';

describe('loader (no sidecar)', () => {
  it('synthesises elements, classes and colours from the glb', async () => {
    const { model, geometry } = await parseModel(buildProceduralGlb());
    expect(model.elements.map((e) => e.ifcClass)).toEqual(['IfcSlab', 'IfcDuctSegment', 'IfcBeam']);
    expect(model.byGlobalId.get('duct-0001')).toBe(1);
    expect(model.elements[0]!.storey).toBeNull();
    expect(model.elements[1]!.color[2]).toBeGreaterThan(0.8);
    expect(geometry.ranges.map((r) => r.count)).toEqual([36, 36, 36]);
    expect(geometry.elementOfTriangle(0)).toBe(0);
    expect(geometry.elementOfTriangle(12)).toBe(1);
    expect(geometry.elementOfTriangle(35)).toBe(2);
    expect(geometry.elementOfTriangle(36)).toBe(-1);
    expect(geometry.bounds[0]!.max.x).toBeCloseTo(5);
    expect(model.elements[0]!.bounds[3]).toBeCloseTo(5);
    expect(geometry.edgeRanges.every((r) => r.count === 24)).toBe(true); // 12 box edges * 2 vertices
  });
});

describe('loader (sidecar)', () => {
  it('maps nodes by extras.id and keeps sidecar fields', async () => {
    const side = proceduralSidecar();
    side.elements.reverse().forEach((e, i) => ((e as { id: number }).id = [2, 1, 0][i]!)); // ids stay unique, order reversed
    const { model, geometry } = await parseModel(buildProceduralGlb(), side);
    // records are in array order (beam, duct, slab) with ids 2,1,0 -> extras.id 0 (slab) maps to record index 2
    expect(model.elements[2]!.ifcClass).toBe('IfcSlab');
    expect(geometry.ranges[2]!.count).toBe(36);
    expect(model.elements[2]!.storey).toBe(0);
    expect(model.storeys).toHaveLength(1);
  });
});

describe('BvhGeometryProvider', async () => {
  const { geometry } = await parseModel(buildProceduralGlb());
  const p = new BvhGeometryProvider(geometry);

  it('bounds', () => {
    expect(p.bounds(1).min.y).toBeCloseTo(-1);
    expect(p.bounds(1).max.y).toBeCloseTo(2);
  });

  it('raycastAll sorts by distance, filters candidates, dedupes, honours maxDistance', () => {
    const o = new Vector3(1, 5, 0.5);
    const d = new Vector3(0, -1, 0);
    expect(p.raycastAll(o, d, 100, new Set([0, 1, 2]))).toEqual([1, 0]); // duct top at y=2 first, then slab
    expect(p.raycastAll(o, d, 100, new Set([0]))).toEqual([0]);
    expect(p.raycastAll(o, d, 3.5, new Set([0, 1, 2]))).toEqual([1]); // slab top is 4.85 away
    const o2 = new Vector3(0, 5, 2); // over the beam, through the slab
    expect(p.raycastAll(o2, d, 100, new Set([0, 1, 2]))).toEqual([0, 2]);
  });

  it('intersects and surfaceDistance', () => {
    expect(p.intersects(0, 1)).toBe(true); // duct pierces slab
    expect(p.intersects(0, 2)).toBe(false);
    expect(p.surfaceDistance(0, 1)).toBe(0);
    expect(p.surfaceDistance(0, 2)).toBeCloseTo(0.2, 5);
    expect(p.surfaceDistance(2, 0)).toBeCloseTo(0.2, 5);
    expect(p.boundsDistance(0, 2)).toBeCloseTo(0.2, 5);
    expect(p.surfaceDistance(1, 2, 0.1)).toBeGreaterThan(0.1);
    expect(p.surfaceDistance(1, 2)).toBeCloseTo(p.boundsDistance(1, 2) > 0 ? p.surfaceDistance(1, 2) : 0);
  });

  it('samplePoints is deterministic, area weighted and on the surface', () => {
    const a = p.samplePoints(0, 64);
    const b = new BvhGeometryProvider(geometry).samplePoints(0, 64);
    expect(a).toHaveLength(64);
    expect(a.map((v) => v.toArray())).toEqual(b.map((v) => v.toArray()));
    expect(p.samplePoints(0, 10).map((v) => v.toArray())).toEqual(a.slice(0, 10).map((v) => v.toArray()));
    const bb = p.bounds(0).clone().expandByScalar(1e-4);
    for (const v of p.samplePoints(0, 200)) {
      const onFace = [Math.abs(v.x) - 5, Math.abs(v.y) - 0.15, Math.abs(v.z) - 4].some((e) => Math.abs(e) < 1e-5);
      expect(onFace).toBe(true);
      expect(bb.containsPoint(v)).toBe(true);
    }
    // top/bottom faces carry 2*10*8 of 2*(80+3+2.4)=170.8 m2: ~94% of samples have |y|=0.15
    const tb = p.samplePoints(0, 2000).filter((v) => Math.abs(Math.abs(v.y) - 0.15) < 1e-5).length / 2000;
    expect(tb).toBeGreaterThan(0.9);
    expect(tb).toBeLessThan(0.98);
  });
});

describe('containment', () => {
  it('detects one closed mesh fully inside another', () => {
    const big = new BoxGeometry(10, 10, 10);
    const small = new BoxGeometry(1, 1, 1);
    const far = new BoxGeometry(1, 1, 1);
    const merged = new MergedGeometry([
      [{ geometry: big, matrix: new Matrix4() }],
      [{ geometry: small, matrix: new Matrix4().makeTranslation(1, 1, 1) }],
      [{ geometry: far, matrix: new Matrix4().makeTranslation(3, 0, 0) }], // inside bounds of big? 3 +-0.5 < 5: inside too
      [{ geometry: far, matrix: new Matrix4().makeTranslation(7, 0, 0) }], // outside
    ]);
    const p = new BvhGeometryProvider(merged);
    expect(p.intersects(0, 1)).toBe(true);
    expect(p.intersects(1, 0)).toBe(true);
    expect(p.intersects(0, 2)).toBe(true);
    expect(p.intersects(0, 3)).toBe(false);
    expect(p.surfaceDistance(0, 3)).toBeCloseTo(1.5, 5);
  });
});
