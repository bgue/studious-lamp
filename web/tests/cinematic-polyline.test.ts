import { describe, expect, it } from 'vitest';
import { Vector3 } from 'three';
import { PolylinePath, buildRunPath, orderRun } from '../src/cinematic/polyline';

const centresOf = (pts: Record<number, [number, number, number]>): Map<number, Vector3> =>
  new Map(Object.entries(pts).map(([k, p]) => [Number(k), new Vector3(...p)]));

describe('orderRun', () => {
  // A chain along x with ids deliberately out of order.
  const centres = centresOf({ 7: [0, 0, 0], 3: [1, 0, 0], 9: [2, 0, 0], 1: [3, 0, 0], 5: [4, 0, 0] });
  const ports: Array<[number, number]> = [[7, 3], [9, 3], [9, 1], [5, 1]];

  it('follows port connectivity end to end, starting at the lowest-id endpoint without a hint', () => {
    const o = orderRun([5, 1, 9, 3, 7], centres, ports);
    expect(o).toEqual([5, 1, 9, 3, 7]);
  });

  it('starts at the endpoint nearest the hint', () => {
    expect(orderRun([5, 1, 9, 3, 7], centres, ports, new Vector3(10, 0, 0))).toEqual([5, 1, 9, 3, 7]);
    expect(orderRun([5, 1, 9, 3, 7], centres, ports, new Vector3(-10, 0, 0))).toEqual([7, 3, 9, 1, 5]);
  });

  it('follows ports even when geometry would suggest otherwise', () => {
    // 1 and 2 are far apart but joined; 3 is near 1 but not connected to it
    const c = centresOf({ 1: [0, 0, 0], 2: [10, 0, 0], 3: [1, 0, 0] });
    const o = orderRun([1, 2, 3], c, [[1, 2]], new Vector3(0, 0, 0));
    expect(o.slice(0, 2)).toEqual([1, 2]);
    expect(o).toHaveLength(3);
  });

  it('falls back to nearest-neighbour ordering without ports', () => {
    const c = centresOf({ 4: [3, 0, 0], 2: [1, 0, 0], 8: [0, 0, 0], 6: [2, 0, 0] });
    expect(orderRun([4, 2, 8, 6], c, [])).toEqual([4, 6, 2, 8]); // starts at an end (farthest from centroid)
  });

  it('uses nearest-neighbour to cross a gap between two connected pieces', () => {
    const c = centresOf({ 1: [0, 0, 0], 2: [1, 0, 0], 3: [5, 0, 0], 4: [6, 0, 0] });
    const o = orderRun([1, 2, 3, 4], c, [[1, 2], [3, 4]]);
    expect(o).toEqual([1, 2, 3, 4]);
  });

  it('visits every element exactly once, including a branch, and ignores outside ports', () => {
    const c = centresOf({ 1: [0, 0, 0], 2: [1, 0, 0], 3: [2, 1, 0], 4: [2, -1, 0], 5: [9, 9, 9] });
    const o = orderRun([1, 2, 3, 4], c, [[1, 2], [2, 3], [2, 4], [4, 5]]);
    expect(o).toHaveLength(4);
    expect(new Set(o).size).toBe(4);
    expect(o[0]).toBe(1);
  });

  it('handles trivial inputs and a closed loop', () => {
    expect(orderRun([], new Map(), [])).toEqual([]);
    expect(orderRun([3], centresOf({ 3: [0, 0, 0] }), [])).toEqual([3]);
    const c = centresOf({ 1: [0, 0, 0], 2: [1, 0, 0], 3: [1, 1, 0], 4: [0, 1, 0] });
    const o = orderRun([1, 2, 3, 4], c, [[1, 2], [2, 3], [3, 4], [4, 1]]);
    expect(new Set(o).size).toBe(4);
    // consecutive elements are adjacent on the loop
    for (let i = 1; i < o.length; i++) expect(c.get(o[i]!)!.distanceTo(c.get(o[i - 1]!)!)).toBeCloseTo(1, 9);
  });

  it('skips ids without a centre', () => {
    expect(orderRun([1, 99], centresOf({ 1: [0, 0, 0] }), [])).toEqual([1]);
  });
});

describe('PolylinePath', () => {
  const path = new PolylinePath([new Vector3(0, 0, 0), new Vector3(3, 0, 0), new Vector3(3, 4, 0)]);

  it('has arc length and clamps', () => {
    expect(path.length).toBe(7);
    expect(path.pointAt(-1).toArray()).toEqual([0, 0, 0]);
    expect(path.pointAt(100).toArray()).toEqual([3, 4, 0]);
  });

  it('interpolates along segments', () => {
    expect(path.pointAt(1.5).toArray()).toEqual([1.5, 0, 0]);
    expect(path.pointAt(3).toArray()).toEqual([3, 0, 0]);
    expect(path.pointAt(5).toArray()).toEqual([3, 2, 0]);
  });

  it('drops consecutive duplicate points', () => {
    const p = new PolylinePath([new Vector3(0, 0, 0), new Vector3(0, 0, 0), new Vector3(1, 0, 0)]);
    expect(p.points).toHaveLength(2);
    expect(p.length).toBe(1);
  });

  it('buildRunPath goes through the centres in run order', () => {
    const c = centresOf({ 1: [0, 0, 0], 2: [2, 0, 0], 3: [2, 2, 0] });
    const { order, path: p } = buildRunPath([3, 1, 2], c, [[1, 2], [2, 3]], new Vector3(0, -5, 0));
    expect(order).toEqual([1, 2, 3]);
    expect(p.length).toBe(4);
  });
});
