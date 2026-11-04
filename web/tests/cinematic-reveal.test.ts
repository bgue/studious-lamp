import { describe, expect, it } from 'vitest';
import { Box3, Vector3 } from 'three';
import { MAX_REVEAL_DELAY_MS, StaggerReveal, pointBoxDistance, revealDelays } from '../src/cinematic/reveal';

const box = (x0: number, y0: number, z0: number, x1: number, y1: number, z1: number): Box3 =>
  new Box3(new Vector3(x0, y0, z0), new Vector3(x1, y1, z1));

describe('pointBoxDistance', () => {
  it('is 0 inside and the euclidean gap outside', () => {
    const b = box(0, 0, 0, 2, 2, 2);
    expect(pointBoxDistance(new Vector3(1, 1, 1), b)).toBe(0);
    expect(pointBoxDistance(new Vector3(5, 1, 1), b)).toBe(3);
    expect(pointBoxDistance(new Vector3(5, 6, 1), b)).toBe(5);
  });
});

describe('revealDelays', () => {
  const centre = new Vector3(0, 0, 0);
  const items = [
    { id: 1, box: box(10, 0, 0, 11, 1, 1) }, // far
    { id: 2, box: box(-1, -1, -1, 1, 1, 1) }, // contains the centre
    { id: 3, box: box(2, 0, 0, 3, 1, 1) }, // near
    { id: 4, box: box(0, 5, 0, 1, 6, 1) }, // mid
  ];

  it('orders delays by distance from the focus centre', () => {
    const d = revealDelays(items, centre, 20);
    const byDelay = [...d.entries()].sort((a, b) => a[1] - b[1]).map(([id]) => id);
    expect(byDelay).toEqual([2, 3, 4, 1]);
    expect(d.get(2)).toBe(0);
  });

  it('is linear in distance and capped at the maximum', () => {
    const d = revealDelays(items, centre, 10);
    expect(d.get(3)).toBeCloseTo(MAX_REVEAL_DELAY_MS * 0.2, 9);
    expect(d.get(4)).toBeCloseTo(MAX_REVEAL_DELAY_MS * 0.5, 9);
    expect(d.get(1)).toBe(MAX_REVEAL_DELAY_MS); // 10 / 10 = 1
    const far = revealDelays([{ id: 9, box: box(500, 0, 0, 501, 1, 1) }], centre, 10);
    expect(far.get(9)).toBe(MAX_REVEAL_DELAY_MS);
  });

  it('gives zero delay for a degenerate reach', () => {
    expect(revealDelays(items, centre, 0).get(1)).toBe(0);
  });
});

describe('StaggerReveal', () => {
  it('holds the previous alpha until each start time, nearest first', () => {
    const alpha = new Float32Array([1, 1, 1, 1]);
    const delays = new Map([[0, 0], [1, 100], [2, 300]]);
    const s = new StaggerReveal();
    s.begin(1000, delays, alpha);
    expect(s.size).toBe(2); // zero delay is never held
    expect(s.has(0)).toBe(false);

    // the controller's tick moved everyone down this frame
    alpha.set([0.8, 0.8, 0.8, 0.8]);
    expect(s.apply(1050, alpha)).toBe(true);
    expect(Array.from(alpha).map((x) => +x.toFixed(2))).toEqual([0.8, 1, 1, 0.8]);

    alpha.set([0.7, 0.7, 0.7, 0.7]);
    s.apply(1150, alpha); // element 1 is released
    expect(Array.from(alpha).map((x) => +x.toFixed(2))).toEqual([0.7, 0.7, 1, 0.7]);
    expect(s.size).toBe(1);

    alpha.set([0.6, 0.6, 0.6, 0.6]);
    s.apply(1300, alpha);
    expect(alpha[2]).toBeCloseTo(0.6, 6);
    expect(s.size).toBe(0);
    expect(s.apply(1400, alpha)).toBe(false);
  });

  it('skips hidden elements and clears on demand', () => {
    const alpha = new Float32Array([-1, 0.5]);
    const s = new StaggerReveal();
    s.begin(0, new Map([[0, 200], [1, 200]]), alpha);
    expect(s.has(0)).toBe(false);
    expect(s.has(1)).toBe(true);
    expect(s.startTime(1)).toBe(200);
    s.clear();
    expect(s.size).toBe(0);
  });

  it('begin replaces earlier state', () => {
    const alpha = new Float32Array([1, 1]);
    const s = new StaggerReveal();
    s.begin(0, new Map([[0, 500]]), alpha);
    s.begin(0, new Map([[1, 500]]), alpha);
    expect(s.has(0)).toBe(false);
    expect(s.has(1)).toBe(true);
  });
});
