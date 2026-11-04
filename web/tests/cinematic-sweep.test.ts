import { describe, expect, it } from 'vitest';
import { Box3, Vector3 } from 'three';
import {
  PEEL_BANDS,
  PlaneSweep,
  buildHold,
  planeDistance,
  projectionExtent,
  sweepAlpha,
  sweepBand,
  sweepNormal,
  sweepPeel,
  sweepRange,
  sweepRangeFromExtent,
  usesStagger,
  usesSweep,
} from '../src/cinematic/sweep';
import { alongViewDistance, depthGradeMix } from '../src/cinematic/depthGrade';

const box = (x0: number, y0: number, z0: number, x1: number, y1: number, z1: number): Box3 =>
  new Box3(new Vector3(x0, y0, z0), new Vector3(x1, y1, z1));

describe('sweep plane progression', () => {
  it('starts at the start offset, ends at the end offset, linear in time', () => {
    const s = new PlaneSweep();
    s.begin(1000, new Vector3(0, 0, -2), 2, 12, 1000);
    expect(s.normal.length()).toBeCloseTo(1, 9); // normalised
    expect(s.offsetAt(1000)).toBeCloseTo(2, 9);
    expect(s.offsetAt(1500)).toBeCloseTo(7, 9);
    expect(s.offsetAt(2000)).toBeCloseTo(12, 9);
    expect(s.offsetAt(5000)).toBeCloseTo(12, 9); // clamped after the end
    expect(s.offsetAt(0)).toBeCloseTo(2, 9); // and before the start
  });

  it('reports done only after the duration and when stopped', () => {
    const s = new PlaneSweep();
    expect(s.doneAt(0)).toBe(true); // never started
    s.begin(0, new Vector3(1, 0, 0), 0, 1, 800);
    expect(s.running).toBe(true);
    expect(s.doneAt(799)).toBe(false);
    expect(s.doneAt(800)).toBe(true);
    s.stop();
    expect(s.running).toBe(false);
    expect(s.progress(10)).toBe(1);
  });

  it('is at about 38% after 380 ms of a 1 s sweep', () => {
    const s = new PlaneSweep();
    s.begin(0, new Vector3(0, 1, 0), 0, 1, 1000);
    expect(s.progress(380)).toBeCloseTo(0.38, 9);
  });
});

describe('sweep range', () => {
  it('covers boxes along the normal: contact start, end past the last box by the peel zone and band', () => {
    const n = new Vector3(1, 0, 0);
    const band = 0.15;
    const r = sweepRange([box(2, 0, 0, 3, 1, 1), box(5, 0, 0, 6, 1, 1)], n, band);
    expect(r.start).toBeCloseTo(2 - 0.01, 9);
    expect(r.end).toBeCloseTo(6 + (PEEL_BANDS + 1) * band, 9);
  });

  it('uses the box support along a diagonal normal', () => {
    const n = new Vector3(1, 1, 0).normalize();
    const r = sweepRange([box(0, 0, 0, 2, 2, 2)], n, 0.1);
    // projections of corners: 0 .. 4/sqrt2
    expect(r.start).toBeCloseTo(-0.01, 9);
    expect(r.end).toBeCloseTo(4 / Math.SQRT2 + 5 * 0.1, 9);
  });

  it('empty input gives a zero range', () => {
    expect(sweepRange([], new Vector3(0, 0, 1), 0.1)).toEqual({ start: 0, end: 0 });
    expect(sweepRangeFromExtent(Infinity, -Infinity, 0.1)).toEqual({ start: 0, end: 0 });
  });

  it('projectionExtent is exact over a vertex range', () => {
    // 4 vertices; look at vertices 1..3 only
    const pos = [100, 0, 0, /**/ 1, 0, 0, 3, 2, 0, -2, 0, 5];
    const e = projectionExtent(pos, 1, 3, new Vector3(1, 0, 0));
    expect(e.lo).toBe(-2);
    expect(e.hi).toBe(3);
    const r = sweepRangeFromExtent(e.lo, e.hi, 0.2);
    expect(r.start).toBeCloseTo(-2.01, 9);
    expect(r.end).toBeCloseTo(3 + 5 * 0.2, 9);
  });

  it('the last point of the travel leaves no band or peel on any vertex (seamless hand-over)', () => {
    const band = 0.15;
    const hi = 3;
    const r = sweepRangeFromExtent(0, hi, band);
    const s = planeDistance(new Vector3(1, 0, 0), r.end, new Vector3(hi, 0, 0));
    expect(s).toBeLessThanOrEqual(-PEEL_BANDS * band);
    expect(sweepPeel(s, band)).toBe(0);
    expect(sweepBand(s, band)).toBe(0);
  });
});

describe('band maths', () => {
  const w = 0.15;
  it('band is 1 at the plane and 0 a band width ahead of it', () => {
    expect(sweepBand(0, w)).toBeCloseTo(1, 9);
    expect(sweepBand(w, w)).toBeCloseTo(0, 9);
    expect(sweepBand(w * 2, w)).toBe(0);
    expect(sweepBand(w / 2, w)).toBeCloseTo(0.5, 9); // smoothstep midpoint
  });
  it('band is a thin rim on the swept side (a quarter width)', () => {
    expect(sweepBand(-0.25 * w, w)).toBeCloseTo(0, 9);
    expect(sweepBand(-0.125 * w, w)).toBeCloseTo(0.5, 9);
    expect(sweepBand(-w, w)).toBe(0);
  });
  it('band is non-increasing away from the plane on both sides', () => {
    let prev = 1;
    for (let s = 0; s <= w; s += w / 20) {
      const b = sweepBand(s, w);
      expect(b).toBeLessThanOrEqual(prev + 1e-12);
      prev = b;
    }
  });
  it('peel is 0 ahead of the plane, 1 at it, 0 beyond four bands behind', () => {
    expect(sweepPeel(0.01, w)).toBe(0);
    expect(sweepPeel(0, w)).toBeCloseTo(1, 9);
    expect(sweepPeel(-PEEL_BANDS * w, w)).toBeCloseTo(0, 9);
    expect(sweepPeel(-10, w)).toBe(0);
  });
  it('planeDistance is n.p - offset', () => {
    expect(planeDistance(new Vector3(0, 0, 1), 2, new Vector3(5, 5, 3))).toBe(1);
  });
});

describe('sweep alpha', () => {
  it('ahead of the plane an element keeps its hold alpha', () => {
    expect(sweepAlpha(0.5, 0.15, 0.3, 1, 0.15)).toBe(1);
    expect(sweepAlpha(0.5, 0.15, 0.3, 0.7, 0.15)).toBe(0.7);
  });
  it('behind the plane it is pulled toward alphaMin at the front and relaxes to the real alpha', () => {
    const w = 0.15;
    const real = 0.6;
    const atFront = sweepAlpha(0, w, real, 1, 0.15);
    expect(atFront).toBeCloseTo(real + (0.15 - real) * 0.6, 9);
    expect(atFront).toBeLessThan(real);
    expect(sweepAlpha(-PEEL_BANDS * w, w, real, 1, 0.15)).toBeCloseTo(real, 9);
    expect(sweepAlpha(-100, w, real, 1, 0.15)).toBe(real);
  });
  it('never raises an alpha already below the floor', () => {
    expect(sweepAlpha(0, 0.15, 0.05, 1, 0.15)).toBeCloseTo(0.05, 9);
  });
});

describe('sweep helpers', () => {
  it('normal points from the camera to the focus, with a fallback', () => {
    const n = sweepNormal(new Vector3(0, 0, 10), new Vector3(0, 0, 0));
    expect(n.toArray()).toEqual([0, 0, -1]);
    expect(sweepNormal(new Vector3(1, 2, 3), new Vector3(1, 2, 3)).toArray()).toEqual([0, 0, -1]);
    const d = sweepNormal(new Vector3(0, 0, 0), new Vector3(3, 4, 0));
    expect(d.x).toBeCloseTo(0.6, 9);
    expect(d.y).toBeCloseTo(0.8, 9);
  });
  it('hold table: previous alpha for the given ids, 0 elsewhere, hidden skipped, never exactly 0 for members', () => {
    const alpha = Float32Array.from([1, 0.4, -1, 0, 0.9]);
    const h = buildHold(5, [1, 2, 3], alpha);
    expect(h[0]).toBe(0);
    expect(h[1]).toBeCloseTo(0.4, 6);
    expect(h[2]).toBe(0); // hidden (alpha < 0)
    expect(h[3]).toBeGreaterThan(0); // alpha 0 is clamped up so the shader still sees a member
    expect(h[4]).toBe(0);
  });
  it('mode selector', () => {
    expect([usesSweep('stagger'), usesSweep('sweep'), usesSweep('both')]).toEqual([false, true, true]);
    expect([usesStagger('stagger'), usesStagger('sweep'), usesStagger('both')]).toEqual([true, false, true]);
  });
});

describe('depth-graded ghosting', () => {
  it('is zero at or behind the focus, with no focus radius, or with no strength', () => {
    expect(depthGradeMix(0, 1, 0.5)).toBe(0);
    expect(depthGradeMix(-3, 1, 0.5)).toBe(0);
    expect(depthGradeMix(2, 0, 0.5)).toBe(0);
    expect(depthGradeMix(2, -1, 0.5)).toBe(0);
    expect(depthGradeMix(2, 1, 0)).toBe(0);
  });
  it('grows monotonically with distance in front and saturates at the strength', () => {
    const r = 2;
    let prev = 0;
    for (let d = 0.1; d < 30; d += 0.7) {
      const m = depthGradeMix(d, r, 0.5);
      expect(m).toBeGreaterThan(prev);
      expect(m).toBeLessThanOrEqual(0.5);
      prev = m;
    }
    expect(depthGradeMix(1000, r, 0.5)).toBeCloseTo(0.5, 6);
  });
  it('normalises by the radius: one radius in front gives strength * (1 - 1/e)', () => {
    expect(depthGradeMix(3, 3, 0.8)).toBeCloseTo(0.8 * (1 - Math.exp(-1)), 9);
    // same ratio, different scale -> same mix
    expect(depthGradeMix(6, 6, 0.8)).toBeCloseTo(depthGradeMix(3, 3, 0.8), 9);
  });
  it('stacked slabs at increasing distance read as layers (strictly increasing mix)', () => {
    const cam = new Vector3(0, 10, 0);
    const focus = new Vector3(0, 0, 0);
    const mixes = [3, 6, 9].map((y) => depthGradeMix(alongViewDistance(cam, focus, new Vector3(0, y, 0)), 4, 0.5));
    expect(mixes[0]!).toBeLessThan(mixes[1]!);
    expect(mixes[1]!).toBeLessThan(mixes[2]!);
  });
  it('along-view distance: positive toward the camera, negative behind the focus, ignores sideways offset', () => {
    const cam = new Vector3(0, 0, 10);
    const focus = new Vector3(0, 0, 0);
    expect(alongViewDistance(cam, focus, new Vector3(0, 0, 4))).toBeCloseTo(4, 9); // 4 in front of the focus (toward the camera)
    expect(alongViewDistance(cam, focus, new Vector3(0, 0, -2))).toBeCloseTo(-2, 9);
    expect(alongViewDistance(cam, focus, new Vector3(5, 7, 0))).toBeCloseTo(0, 9);
    expect(alongViewDistance(cam, cam, new Vector3(1, 2, 3))).toBe(0);
  });
});
