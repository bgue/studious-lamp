import { describe, expect, it } from 'vitest';
import { BoxGeometry, Matrix4, PerspectiveCamera, Ray, Vector3 } from 'three';
import { MergedGeometry } from '../src/model/merged';
import { BvhGeometryProvider } from '../src/render/geometry';
import { cameraRay, elementDistance, firstSurfaceHit } from '../src/measure/geometry';
import { distance, formatLength, MEASURE_CSV_HEADER, measurementRows, snapToVertex, toIfcWorld } from '../src/measure/maths';
import type { V3 } from '../src/measure/maths';
import { projectToScreen } from '../src/ui/overlay';
import { toCsv } from '../src/tools/csv';

describe('formatLength', () => {
  it('metres with 3 decimals, millimetres whole', () => {
    expect(formatLength(1.23456, 'm')).toBe('1.235 m');
    expect(formatLength(0.5, 'm')).toBe('0.500 m');
    expect(formatLength(1.23456, 'mm')).toBe('1235 mm');
    expect(formatLength(0.0004, 'mm')).toBe('0 mm');
    expect(formatLength(NaN, 'm')).toBe('-');
  });
  it('distance', () => expect(distance([0, 0, 0], [3, 4, 12])).toBe(13));
});

describe('snapToVertex', () => {
  // identity-like projection: world x,y are pixels
  const proj = (p: V3) => ({ x: p[0], y: p[1], visible: true });
  const tri: V3[] = [[0, 0, 0], [100, 0, 0], [0, 100, 0]];
  it('snaps to the nearest vertex within the radius', () => {
    const r = snapToVertex([5, 6, 0], tri, { x: 5, y: 6 }, proj, 12);
    expect(r.snapped).toBe(true);
    expect(r.point).toEqual([0, 0, 0]);
    expect(r.index).toBe(0);
    expect(r.px).toBeCloseTo(Math.hypot(5, 6), 9);
  });
  it('picks the nearest of several in range', () => {
    const r = snapToVertex([95, 4, 0], tri, { x: 95, y: 4 }, proj, 12);
    expect(r.index).toBe(1);
  });
  it('keeps the hit point when no vertex is within 12 px', () => {
    const r = snapToVertex([50, 50, 0], tri, { x: 50, y: 50 }, proj, 12);
    expect(r.snapped).toBe(false);
    expect(r.point).toEqual([50, 50, 0]);
    expect(r.index).toBe(-1);
  });
  it('the radius is inclusive and vertices behind the camera are ignored', () => {
    expect(snapToVertex([12, 0, 0], tri, { x: 12, y: 0 }, proj, 12).snapped).toBe(true);
    expect(snapToVertex([12.01, 0, 0], tri, { x: 12.01, y: 0 }, proj, 12).snapped).toBe(false);
    const hidden = (p: V3) => ({ x: p[0], y: p[1], visible: p[0] !== 0 });
    expect(snapToVertex([1, 1, 0], tri, { x: 1, y: 1 }, hidden, 12).snapped).toBe(false);
  });
  it('works with the real projection', () => {
    const cam = new PerspectiveCamera(50, 1.5, 0.1, 100);
    cam.position.set(0, 0, 5);
    cam.lookAt(0, 0, 0);
    cam.updateMatrixWorld();
    const m = new Matrix4().multiplyMatrices(cam.projectionMatrix, cam.matrixWorldInverse).elements;
    const project = (p: V3) => projectToScreen(m, 900, 600, p[0], p[1], p[2]);
    const corner: V3 = [1, 1, 0];
    const c = project(corner);
    const r = snapToVertex([1.02, 1.02, 0], [corner, [-1, -1, 0]], { x: c.x + 6, y: c.y - 5 }, project, 12);
    expect(r.snapped).toBe(true);
    expect(r.point).toEqual(corner);
  });
});

describe('coordinates and CSV', () => {
  it('viewer frame to IFC world', () => {
    expect(toIfcWorld([1, 2, 3], [10, 20, 30])).toEqual([11, 17, 32]);
  });
  it('rows are IFC world metres with deltas', () => {
    const rows = measurementRows([{ id: 1, kind: 'point', a: [0, 0, 0], b: [1, 2, 0], distance: Math.hypot(1, 2) }], [0, 0, 0], () => '');
    expect(rows[0]!.slice(0, 7)).toEqual([1, 'point to point', 2.236, 2236, 1, 0, 2]);
    const csv = toCsv(MEASURE_CSV_HEADER, rows);
    expect(csv.split('\r\n')[0]!.split(',')).toHaveLength(MEASURE_CSV_HEADER.length);
  });
});

describe('mesh queries on box meshes', () => {
  const box = (cx: number, cy: number, cz: number, sx: number, sy: number, sz: number) => ({
    geometry: new BoxGeometry(sx, sy, sz),
    matrix: new Matrix4().makeTranslation(cx, cy, cz),
  });
  // 0: unit cube at the origin, 1: unit cube 0.5 m away along x, 2: overlapping cube, 3: cube behind 0 along z
  const merged = new MergedGeometry([[box(0, 0, 0, 1, 1, 1)], [box(2, 0, 0, 1, 1, 1)], [box(0.5, 0.5, 0.5, 1, 1, 1)], [box(0, 0, -3, 1, 1, 1)]]);
  const prov = new BvhGeometryProvider(merged);

  it('first hit: nearest front surface, with the hit triangle', () => {
    const hit = firstSurfaceHit(merged, new Ray(new Vector3(0.2, 0.1, 10), new Vector3(0, 0, -1)), () => false)!;
    expect(hit.element === 0 || hit.element === 2).toBe(true);
    expect(hit.point.z).toBeCloseTo(hit.element === 2 ? 1 : 0.5, 6);
    expect(hit.triangle).toHaveLength(3);
  });
  it('hidden elements are skipped: the ray continues behind them', () => {
    const ray = new Ray(new Vector3(0, 0, 10), new Vector3(0, 0, -1));
    const first = firstSurfaceHit(merged, ray, () => false)!;
    const skipped = firstSurfaceHit(merged, ray, (id) => id === first.element || id === 0 || id === 2)!;
    expect(skipped.element).toBe(3);
    expect(skipped.point.z).toBeCloseTo(-2.5, 6);
    expect(firstSurfaceHit(merged, ray, () => true)).toBeNull();
    expect(firstSurfaceHit(merged, new Ray(new Vector3(50, 50, 10), new Vector3(0, 0, -1)), () => false)).toBeNull();
  });
  it('cameraRay passes through the pixel it was built for', () => {
    const cam = new PerspectiveCamera(60, 1, 0.1, 100);
    cam.position.set(0, 0, 8);
    cam.lookAt(0, 0, 0);
    cam.updateMatrixWorld();
    const ray = cameraRay(cam, 0, 0);
    expect(ray.direction.z).toBeCloseTo(-1, 6);
    expect(ray.origin.z).toBeCloseTo(8, 6);
  });
  it('element to element: minimum distance and closest points', () => {
    const r = elementDistance(merged, 0, 1, (a, b) => prov.intersects(a, b))!;
    expect(r.touching).toBe(false);
    expect(r.distance).toBeCloseTo(1, 6); // faces at x=0.5 and x=1.5
    expect(r.a[0]).toBeCloseTo(0.5, 6);
    expect(r.b[0]).toBeCloseTo(1.5, 6);
    expect(Math.hypot(r.a[0] - r.b[0], r.a[1] - r.b[1], r.a[2] - r.b[2])).toBeCloseTo(r.distance, 6);
    const r2 = elementDistance(merged, 0, 3, (a, b) => prov.intersects(a, b))!;
    expect(r2.distance).toBeCloseTo(2, 6);
  });
  it('overlapping elements: distance 0, touching', () => {
    const r = elementDistance(merged, 0, 2, (a, b) => prov.intersects(a, b))!;
    expect(r.distance).toBe(0);
    expect(r.touching).toBe(true);
  });
  it('same element: null', () => {
    expect(elementDistance(merged, 1, 1, () => false)).toBeNull();
  });
});
