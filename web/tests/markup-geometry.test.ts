import { describe, expect, it } from 'vitest';
import { arrowHead, cloudBase, cloudOutline, distToPolyline, ellipsePoints, perimeter, pointInPolygon, rectCorners, resampleClosed, signedArea, simplify } from '../src/markup/geometry';

const square = rectCorners([0, 0], [100, 100]);
const ccw = [0, 0, 100, 0, 100, 100, 0, 100];

describe('revision cloud scallops', () => {
  it('builds whole scallops of about the wanted size around a rectangle', () => {
    const out = cloudOutline(square, { arc: 20, steps: 9 });
    const n = Math.round(perimeter(square, true) / 20); // 20 scallops
    expect(out.length / 2).toBe(n * 8); // steps - 1 points per scallop, the shared end is the next start
    expect(n).toBe(20);
  });

  it('bulges outward for either winding', () => {
    for (const poly of [ccw, [...ccw].reverse().reduce<number[]>((a, _v, i, arr) => (i % 2 === 0 ? [...a, arr[arr.length - 2 - i]!, arr[arr.length - 1 - i]!] : a), [])]) {
      const out = cloudOutline(poly, { arc: 16 });
      let outside = 0;
      let inside = 0;
      for (let i = 0; i < out.length; i += 2) {
        const x = out[i]!, y = out[i + 1]!;
        const onEdge = distToPolyline(x, y, poly, true) < 0.5;
        if (onEdge) continue;
        if (pointInPolygon(x, y, poly)) inside++; else outside++;
      }
      expect(outside).toBeGreaterThan(40);
      // The corner arcs may dip slightly inside where the resampled chord cuts the corner; almost all points are outside.
      expect(inside).toBeLessThan(outside * 0.08);
    }
  });

  it('starts every scallop on the outline and the apex lies bulge * chord away', () => {
    const out = cloudOutline(square, { arc: 25, bulge: 0.5, steps: 9 });
    // First scallop: along the top edge from (0,0) to (25,0): the apex (middle sample) is 12.5 away from the edge.
    const mid = 4; // steps 9: samples 0..7 here (the end belongs to the next scallop), the apex is between 3 and 4
    const a = out.slice(mid * 2, mid * 2 + 2);
    expect(Math.abs(a[1]!)).toBeGreaterThan(11);
    expect(Math.abs(a[1]!)).toBeLessThan(13.5);
    expect(a[1]!).toBeLessThan(0); // outward is up (negative y) for this winding
    expect(out[0]).toBeCloseTo(0, 6);
    expect(out[1]).toBeCloseTo(0, 6);
  });

  it('returns the points of a degenerate polygon', () => {
    expect(cloudOutline([0, 0, 10, 0], { arc: 5 })).toEqual([0, 0, 10, 0]);
    expect(cloudOutline([0, 0, 10, 0, 20, 0], { arc: 5 })).toEqual([0, 0, 10, 0, 20, 0]);
  });

  it('takes 2 points as the corners and more as a freehand outline', () => {
    expect(cloudBase([[0, 0], [10, 20]])).toEqual([0, 0, 10, 0, 10, 20, 0, 20]);
    expect(cloudBase([[0, 0], [10, 0], [5, 8]])).toEqual([0, 0, 10, 0, 5, 8]);
  });

  it('resamples evenly along the perimeter', () => {
    const q = resampleClosed(square, 8);
    expect(q.length).toBe(16);
    expect(q.slice(0, 4)).toEqual([0, 0, 50, 0]);
    expect(perimeter(q, true)).toBeCloseTo(400, 6);
  });
});

describe('other shape geometry', () => {
  it('samples an ellipse inside its box', () => {
    const e = ellipsePoints([0, 0], [200, 100], 40);
    expect(e.length).toBe(80);
    for (let i = 0; i < e.length; i += 2) {
      expect(e[i]!).toBeGreaterThanOrEqual(-1e-9); expect(e[i]!).toBeLessThanOrEqual(200 + 1e-9);
      expect(((e[i]! - 100) / 100) ** 2 + ((e[i + 1]! - 50) / 50) ** 2).toBeCloseTo(1, 9);
    }
    expect(Math.abs(signedArea(e))).toBeGreaterThan(Math.PI * 100 * 50 * 0.98);
  });
  it('simplifies a noisy line and keeps the ends', () => {
    const p: number[] = [];
    for (let i = 0; i <= 50; i++) p.push(i * 2, (i % 2) * 0.3);
    const s = simplify(p, 1);
    expect(s.length).toBe(4);
    expect(s.slice(0, 2)).toEqual([0, 0]);
    expect(s.slice(-2)).toEqual([100, 0]);
  });
  it('makes an arrow head at the tip', () => {
    const h = arrowHead(0, 0, 100, 0, 20, 8)!;
    expect(h.slice(0, 2)).toEqual([100, 0]);
    expect(h[2]).toBeCloseTo(80, 9);
    expect(Math.abs(h[3]!)).toBeCloseTo(8, 9);
    expect(arrowHead(5, 5, 5, 5, 20, 8)).toBeNull();
  });
});
