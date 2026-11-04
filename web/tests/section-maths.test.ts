import { describe, expect, it } from 'vitest';
import {
  BOX_EDGES, MAX_CLIP_PLANES, MIN_BOX_SIZE, boxCentre, boxCorners, boxHandles, boxPlanes, closestParamOnLine, dragHandle, fitBox, moveFace, normalizePlane, planeToVec4, planesEqual, planesFor, pointKept, sectionPlane, signedDistance,
} from '../src/section/maths';
import type { Box6, ClipPlane, SectionBox, Vec3 } from '../src/section/maths';
import { cloneSection, defaultSection, mergeSection } from '../src/section/config';
import { captureViewpoint, planViewpoint } from '../src/bcf/plan';
import type { PlanContext } from '../src/bcf/plan';

describe('clip planes', () => {
  const p: ClipPlane = { normal: [0, 2, 0], point: [0, 3, 0] };
  it('normalises and evaluates the kept side', () => {
    expect(normalizePlane(p)!.normal).toEqual([0, 1, 0]);
    expect(normalizePlane({ normal: [0, 0, 0], point: [0, 0, 0] })).toBeNull();
    expect(signedDistance(p, [5, 4, 5])).toBeCloseTo(1, 12);
    expect(signedDistance(p, [5, 1, 5])).toBeCloseTo(-2, 12);
    expect(pointKept([p], [0, 3.0001, 0])).toBe(true);
    expect(pointKept([p], [0, 2.9, 0])).toBe(false);
  });
  it('planeToVec4 matches n . p + w >= 0', () => {
    const v = planeToVec4(p);
    expect(v[1]).toBe(1);
    expect(v[3]).toBeCloseTo(-3, 12);
    expect(v[1] * 4 + v[3]).toBeGreaterThan(0);
  });
  it('pointKept needs every plane', () => {
    const a: ClipPlane = { normal: [1, 0, 0], point: [0, 0, 0] };
    const b: ClipPlane = { normal: [-1, 0, 0], point: [2, 0, 0] };
    expect(pointKept([a, b], [1, 9, 9])).toBe(true);
    expect(pointKept([a, b], [3, 0, 0])).toBe(false);
    expect(pointKept([a, b], [-1, 0, 0])).toBe(false);
    expect(pointKept([], [1e9, 0, 0])).toBe(true);
  });
  it('planesEqual compares with a tolerance', () => {
    expect(planesEqual([p], [{ normal: [0, 2.001, 0], point: [0, 3, 0] }], 1e-6)).toBe(false);
    expect(planesEqual([{ normal: [0, 1, 0], point: [0, 3, 0] }], [{ normal: [0, 1, 1e-9], point: [0, 3, 0] }])).toBe(true);
    expect(planesEqual(null, [])).toBe(true);
    expect(planesEqual([p], null)).toBe(false);
  });
});

describe('section box', () => {
  const boxes: Box6[] = [[0, 0, 0, 2, 1, 1], [3, -1, 0.5, 4, 2, 2]];
  it('fits the union plus margin', () => {
    expect(fitBox(boxes, 0.5)).toEqual({ min: [-0.5, -1.5, -0.5], max: [4.5, 2.5, 2.5] });
    expect(fitBox(boxes, 0)).toEqual({ min: [0, -1, 0], max: [4, 2, 2] });
    expect(fitBox([], 1)).toBeNull();
    expect(fitBox(boxes, -3)!.min).toEqual([0, -1, 0]);
  });
  const b: SectionBox = { min: [0, 0, 0], max: [2, 4, 6] };
  it('six planes keep exactly the inside', () => {
    const planes = boxPlanes(b);
    expect(planes).toHaveLength(6);
    expect(pointKept(planes, [1, 2, 3])).toBe(true);
    expect(pointKept(planes, boxCentre(b))).toBe(true);
    for (const out of [[-0.01, 2, 3], [2.01, 2, 3], [1, -0.01, 3], [1, 4.01, 3], [1, 2, -0.01], [1, 2, 6.01]] as Vec3[]) expect(pointKept(planes, out)).toBe(false);
    for (const c of boxCorners({ min: [0.01, 0.01, 0.01], max: [1.99, 3.99, 5.99] })) expect(pointKept(planes, c)).toBe(true);
  });
  it('has 8 corners, 12 edges of unit length axis-aligned, 6 handles at face centres', () => {
    expect(boxCorners(b)).toHaveLength(8);
    expect(BOX_EDGES).toHaveLength(12);
    const c = boxCorners(b);
    for (const [i, j] of BOX_EDGES) {
      const d = [0, 1, 2].filter((k) => c[i]![k] !== c[j]![k]);
      expect(d).toHaveLength(1);
    }
    const h = boxHandles(b);
    expect(h).toHaveLength(6);
    expect(h[0]!.point).toEqual([0, 2, 3]);
    expect(h[1]!.point).toEqual([2, 2, 3]);
    expect(h[2]!.point).toEqual([1, 0, 3]);
    expect(h[5]!.point).toEqual([1, 2, 6]);
    expect(h[4]!).toMatchObject({ axis: 2, side: 'min', index: 4 });
  });
  it('the 6 box planes and the plane fit the renderer limit', () => {
    expect(MAX_CLIP_PLANES).toBeGreaterThanOrEqual(7);
    const plane = sectionPlane('y', [0, 0, 0], 0, false, [0, 0, -1]);
    expect(planesFor(b, true, plane)).toHaveLength(7);
    expect(planesFor(b, false, plane)).toHaveLength(1);
    expect(planesFor(b, true, null)).toHaveLength(6);
    expect(planesFor(null, true, null)).toHaveLength(0);
  });
});

describe('handle drag projection', () => {
  it('closest point of a ray to an axis line', () => {
    // line along x through the origin; the ray looks down -z at x = 3.5, y = 0.2: closest param is 3.5
    expect(closestParamOnLine([3.5, 0.2, 10], [0, 0, -1], [0, 0, 0], [1, 0, 0])).toBeCloseTo(3.5, 12);
    // an oblique ray through (2, 0, 0)
    expect(closestParamOnLine([2, 5, 5], [0, -1, -1], [0, 0, 0], [1, 0, 0])).toBeCloseTo(2, 12);
    // parallel: no answer
    expect(closestParamOnLine([0, 1, 0], [1, 0, 0], [0, 0, 0], [1, 0, 0])).toBeNull();
    // non unit direction vectors give the parameter in units of the line direction
    expect(closestParamOnLine([3, 0, 10], [0, 0, -7], [0, 0, 0], [2, 0, 0])).toBeCloseTo(1.5, 12);
  });
  const b: SectionBox = { min: [0, 0, 0], max: [4, 4, 4] };
  it('drags a face along its axis and keeps the other faces', () => {
    const h = boxHandles(b)[1]!; // +x
    const nb = dragHandle(b, h, [6, 2, 10], [0, 0, -1])!;
    expect(nb.max).toEqual([6, 4, 4]);
    expect(nb.min).toEqual([0, 0, 0]);
    const h2 = boxHandles(b)[2]!; // -y
    const nb2 = dragHandle(b, h2, [2, -1, 10], [0, 0, -1])!;
    expect(nb2.min).toEqual([0, -1, 0]);
  });
  it('grab offset: the face does not jump when the pointer is not on the handle centre', () => {
    const h = boxHandles(b)[1]!;
    const grab = closestParamOnLine([4.3, 2, 10], [0, 0, -1], h.point, h.dir)!;
    expect(grab).toBeCloseTo(0.3, 12);
    const same = dragHandle(b, h, [4.3, 2, 10], [0, 0, -1], grab)!;
    expect(same.max[0]).toBeCloseTo(4, 12);
    const moved = dragHandle(b, h, [5.3, 2, 10], [0, 0, -1], grab)!;
    expect(moved.max[0]).toBeCloseTo(5, 12);
  });
  it('never inverts the box: a face stops MIN_BOX_SIZE from the opposite one', () => {
    const h = boxHandles(b)[1]!;
    expect(moveFace(b, h, -10).max[0]).toBeCloseTo(MIN_BOX_SIZE, 12);
    const hmin = boxHandles(b)[0]!;
    expect(moveFace(b, hmin, 99).min[0]).toBeCloseTo(4 - MIN_BOX_SIZE, 12);
  });
  it('a ray along the axis gives no drag', () => {
    expect(dragHandle(b, boxHandles(b)[1]!, [-5, 2, 2], [1, 0, 0])).toBeNull();
  });
});

describe('section plane', () => {
  const c: Vec3 = [1, 2, 3];
  it('axis planes pass through the centre plus offset and keep the positive side', () => {
    const p = sectionPlane('y', c, 0.5, false, [0, 0, -1]);
    expect(p.normal).toEqual([0, 1, 0]);
    expect(p.point).toEqual([1, 2.5, 3]);
    expect(pointKept([p], [0, 2.6, 0])).toBe(true);
    expect(pointKept([p], [0, 2.4, 0])).toBe(false);
  });
  it('flip keeps the other side through the same point', () => {
    const p = sectionPlane('x', c, 1, true, [0, 0, -1]);
    expect(p.normal).toEqual([-1, 0, 0]);
    expect(p.point).toEqual([2, 2, 3]);
    expect(pointKept([p], [1.9, 0, 0])).toBe(true);
    expect(pointKept([p], [2.1, 0, 0])).toBe(false);
  });
  it('camera plane follows the view direction (unit length) and keeps what is far from the viewer', () => {
    const p = sectionPlane('camera', c, 2, false, [0, 0, -3]);
    expect(p.normal[2]).toBeCloseTo(-1, 12);
    expect(p.point[2]).toBeCloseTo(1, 12);
    // camera at z = +10 looking down -z: points with smaller z are farther and kept
    expect(pointKept([p], [0, 0, 0])).toBe(true);
    expect(pointKept([p], [0, 0, 5])).toBe(false);
  });
});

describe('section config', () => {
  it('has the documented defaults', () => {
    const d = defaultSection();
    expect(d.box).toMatchObject({ enabled: false, fit: 'selection', margin: 0.5 });
    expect(d.plane).toEqual({ enabled: false, axis: 'y', offset: 0, flip: false });
    expect(d.caps).toBe(true);
    expect(d.capColor).toHaveLength(3);
  });
  it('merges presets, flags a refit when only fit or margin changes, keeps explicit min / max', () => {
    const c = defaultSection();
    let r = mergeSection(c, { box: { enabled: true, fit: 'model', margin: 1 }, plane: { enabled: true, axis: 'camera', offset: -2, flip: true }, caps: false });
    expect(r.bad).toEqual([]);
    expect(r.refit).toBe(true);
    expect(c.box).toMatchObject({ enabled: true, fit: 'model', margin: 1 });
    expect(c.plane).toEqual({ enabled: true, axis: 'camera', offset: -2, flip: true });
    expect(c.caps).toBe(false);
    r = mergeSection(c, { box: { margin: 2, min: [0, 0, 0], max: [1, 1, 1] } });
    expect(r.refit).toBe(false);
    expect(c.box.min).toEqual([0, 0, 0]);
    r = mergeSection(c, { box: { enabled: false } });
    expect(c.box.min).toEqual([0, 0, 0]);
    expect(r.refit).toBe(false);
  });
  it('reports unusable fields and clones deeply', () => {
    const c = defaultSection();
    const r = mergeSection(c, { box: { fit: 'everything', min: [1, 2] }, plane: { axis: 'w' }, capColor: [2, -1, 0.5], junk: 1 });
    expect(r.bad.sort()).toEqual(['section.box.fit', 'section.box.min', 'section.junk', 'section.plane.axis']);
    expect(c.capColor).toEqual([1, 0, 0.5]);
    const k = cloneSection(c);
    k.capColor[0] = 0;
    expect(c.capColor[0]).toBe(1);
  });
});

describe('BCF plane round trip through the pure API', () => {
  const SHIFT: Vec3 = [10, 20, 3];
  const ctx = (): PlanContext => ({ shift: SHIFT, resolve: () => undefined, count: 0, classOf: () => '', modelBounds: [-5, 0, -5, 5, 3, 5], fov: 45, aspect: 1.5, canClip: true });
  it('the six planes of a box and a plane survive capture then plan (what the viewer stores in a topic and applies back)', () => {
    const box: SectionBox = { min: [-2, 0.5, -1], max: [3, 2.5, 4] };
    const planes = [...boxPlanes(box), sectionPlane('x', [0, 0, 0], 0.25, true, [0, 0, -1])];
    const r = captureViewpoint({
      shift: SHIFT, position: [1, 2, 3], target: [1, 2, -7], up: [0, 1, 0], fov: 45, aspect: 1.5,
      selection: [], count: 0, globalId: () => '', hidden: new Set(), clip: planes,
    });
    expect(r.viewpoint.clipping).toHaveLength(7);
    const plan = planViewpoint(r.viewpoint, ctx());
    expect(plan.clip).toHaveLength(7);
    expect(planesEqual(planes, plan.clip, 1e-9)).toBe(true);
    // the same points are kept before and after
    for (const q of [[0, 1, 0], [-3, 1, 0], [1, 3, 1], [0.2, 1, 1], [0.3, 1, 1]] as Vec3[]) expect(pointKept(plan.clip, q)).toBe(pointKept(planes, q));
  });
});
