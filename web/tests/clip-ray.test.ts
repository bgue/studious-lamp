// Rays against section clipping (src/bcf/clipRay.ts): a ray through the clipped part hits the next surface, caps, section boxes.

import { describe, expect, it } from 'vitest';
import { castClipped, clipInterval, keptPoint, unitPlanes } from '../src/bcf/clipRay';
import type { ClipCast, Plane, RangeHit, RangeProbe } from '../src/bcf/clipRay';
import type { Vec3 } from '../src/bcf/model';
import type { Ray3 } from '../src/bcf/surface';

interface Box { id: number; lo: Vec3; hi: Vec3 }

/** First hit of a ray on the faces of axis-aligned boxes inside [near, far]: an entry face, or the exit face when the ray starts inside. */
function boxRange(boxes: Box[]): RangeProbe {
  return (r: Ray3, near: number, far: number): RangeHit | null => {
    let best: RangeHit | null = null;
    for (const b of boxes) {
      let t0 = -Infinity, t1 = Infinity, a0 = 0, a1 = 0, s0 = 1, s1 = 1;
      for (let a = 0; a < 3; a++) {
        const d = r.d[a]!;
        if (Math.abs(d) < 1e-12) { if (r.o[a]! < b.lo[a]! || r.o[a]! > b.hi[a]!) { t0 = Infinity; } continue; }
        let ta = (b.lo[a]! - r.o[a]!) / d, tb = (b.hi[a]! - r.o[a]!) / d;
        let sIn = -1; // outward normal of the face the ray enters through: -sign(d)
        if (ta > tb) { [ta, tb] = [tb, ta]; sIn = 1; }
        if (ta > t0) { t0 = ta; a0 = a; s0 = sIn; }
        if (tb < t1) { t1 = tb; a1 = a; s1 = -sIn; }
      }
      if (t0 > t1) continue;
      const cand = t0 >= near ? { t: t0, a: a0, s: s0 } : { t: t1, a: a1, s: s1 };
      if (cand.t < near || cand.t > far) continue;
      if (!best || cand.t < best.distance) {
        const n: Vec3 = [0, 0, 0];
        n[cand.a] = cand.s;
        best = { point: [r.o[0] + r.d[0] * cand.t, r.o[1] + r.d[1] * cand.t, r.o[2] + r.d[2] * cand.t], normal: n, element: b.id, distance: cand.t };
      }
    }
    return best;
  };
}

const same = (a: ArrayLike<number>, b: number[]): void => b.forEach((v, i) => expect(a[i]).toBeCloseTo(v));
const down: Ray3 = { o: [0, 0, 20], d: [0, 0, -1] };
/** Keeps z <= zc (normal -z). */
const keepBelow = (zc: number): Plane[] => unitPlanes([{ normal: [0, 0, -2], point: [0, 0, zc] }]);
const noCaps = (planes: Plane[]): ClipCast => ({ planes, caps: false, closed: () => true });

describe('clipInterval', () => {
  it('normalises planes and drops degenerate ones', () => {
    const p = unitPlanes([{ normal: [0, 0, -2], point: [0, 0, 3] }, { normal: [0, 0, 0], point: [0, 0, 0] }]);
    expect(p).toHaveLength(1);
    expect(p[0]!.normal).toEqual([0, 0, -1]);
  });
  it('no planes: the whole ray', () => {
    expect(clipInterval([], [0, 0, 0], [0, 0, -1])).toEqual({ near: 0, far: Infinity, enter: -1 });
  });
  it('enters through the plane the ray crosses from the removed side', () => {
    const iv = clipInterval(keepBelow(3), down.o, down.d)!;
    expect(iv.near).toBeCloseTo(17);
    expect(iv.far).toBe(Infinity);
    expect(iv.enter).toBe(0);
  });
  it('starting on the kept side and leaving it ends the interval', () => {
    const iv = clipInterval(keepBelow(3), [0, 0, 0], [0, 0, 1])!;
    expect(iv.near).toBe(0);
    expect(iv.far).toBeCloseTo(3);
  });
  it('a ray that never reaches the kept region, and one parallel on the removed side, give null', () => {
    expect(clipInterval(keepBelow(3), [0, 0, 20], [0, 0, 1])).toBeNull();
    expect(clipInterval(keepBelow(3), [0, 0, 5], [1, 0, 0])).toBeNull();
    expect(clipInterval(keepBelow(3), [0, 0, 1], [1, 0, 0])).toEqual({ near: 0, far: Infinity, enter: -1 });
  });
  it('a point is kept when it is on the kept side of every plane', () => {
    expect(keptPoint(keepBelow(3), [0, 0, 2])).toBe(true);
    expect(keptPoint(keepBelow(3), [0, 0, 4])).toBe(false);
    expect(keptPoint([], [9, 9, 9])).toBe(true);
  });
});

describe('castClipped', () => {
  // An outer wall near the camera (z 5..6) and an inner wall behind it (z -1..0); the cut keeps z <= 3.
  const walls: Box[] = [{ id: 1, lo: [-5, -5, 5], hi: [5, 5, 6] }, { id: 2, lo: [-5, -5, -1], hi: [5, 5, 0] }];
  it('without a section the outer wall is hit', () => {
    const h = castClipped(down, boxRange(walls), null)!;
    expect(h.element).toBe(1);
    expect(h.point[2]).toBeCloseTo(6);
    same(h.normal, [0, 0, 1]);
  });
  it('a ray through the clipped part hits the next surface, the inner wall, not the removed one', () => {
    const h = castClipped(down, boxRange(walls), noCaps(keepBelow(3)))!;
    expect(h.element).toBe(2);
    expect(h.point[2]).toBeCloseTo(0);
    expect(h.distance).toBeCloseTo(20);
    same(h.normal, [0, 0, 1]); // faces the ray origin
  });
  it('a ray that only meets removed geometry misses', () => {
    expect(castClipped(down, boxRange([walls[0]!]), noCaps(keepBelow(3)))).toBeNull();
  });
  it('a plane that keeps everything changes nothing', () => {
    expect(castClipped(down, boxRange(walls), noCaps(keepBelow(100)))!.element).toBe(1);
  });

  describe('caps', () => {
    // A closed solid z -2..2 cut at z = 0 (kept: z <= 0), seen from +z.
    const solid: Box[] = [{ id: 7, lo: [-3, -3, -2], hi: [3, 3, 2] }];
    const planes = keepBelow(0);
    it('with caps drawn a hit on the cut solid lands on the cap: the cut element at the cap point', () => {
      const h = castClipped(down, boxRange(solid), { planes, caps: true, closed: () => true })!;
      expect(h.element).toBe(7);
      same(h.point, [0, 0, 0]);
      expect(h.distance).toBeCloseTo(20);
      same(h.normal, [0, 0, 1]);
    });
    it('the cap point follows an oblique ray along the cut plane', () => {
      const d: Vec3 = [Math.sin(0.3), 0, -Math.cos(0.3)];
      const h = castClipped({ o: [0, 0, 5], d }, boxRange(solid), { planes, caps: true, closed: () => true })!;
      expect(h.point[2]).toBeCloseTo(0);
      expect(h.point[0]).toBeCloseTo(5 * Math.tan(0.3));
    });
    it('without caps the back face of the solid is the visible surface', () => {
      const h = castClipped(down, boxRange(solid), { planes, caps: false, closed: () => true })!;
      expect(h.element).toBe(7);
      expect(h.point[2]).toBeCloseTo(-2);
      same(h.normal, [0, 0, 1]);
    });
    it('an open (not closed) element has no cap', () => {
      const h = castClipped(down, boxRange(solid), { planes, caps: true, closed: () => false })!;
      expect(h.point[2]).toBeCloseTo(-2);
    });
    it('a front face behind the cut is hit as it is, not as a cap', () => {
      const behind: Box[] = [{ id: 8, lo: [-3, -3, -5], hi: [3, 3, -4] }];
      const h = castClipped(down, boxRange(behind), { planes, caps: true, closed: () => true })!;
      expect(h.element).toBe(8);
      expect(h.point[2]).toBeCloseTo(-4);
    });
    it('a solid in front of the cut, not touched by it, is hit normally', () => {
      const h = castClipped({ o: [0, 0, -10], d: [0, 0, 1] }, boxRange([{ id: 9, lo: [-1, -1, -6], hi: [1, 1, -5] }]), { planes, caps: true, closed: () => true })!;
      expect(h.element).toBe(9);
      expect(h.point[2]).toBeCloseTo(-6);
    });
  });

  describe('a section box', () => {
    // The box keeps x in [-2, 2]; the outer wall (x 3..4) is outside it, the inner wall (x -1..0) inside.
    const sb = unitPlanes([
      { normal: [1, 0, 0], point: [-2, 0, 0] }, { normal: [-1, 0, 0], point: [2, 0, 0] },
      { normal: [0, 1, 0], point: [0, -9, 0] }, { normal: [0, -1, 0], point: [0, 9, 0] },
      { normal: [0, 0, 1], point: [0, 0, -9] }, { normal: [0, 0, -1], point: [0, 0, 9] },
    ]);
    const east: Box[] = [{ id: 1, lo: [3, -5, -5], hi: [4, 5, 5] }, { id: 2, lo: [-1, -5, -5], hi: [0, 5, 5] }];
    it('a ray from outside the box passes the outside wall and hits the wall inside', () => {
      const h = castClipped({ o: [20, 0, 0], d: [-1, 0, 0] }, boxRange(east), noCaps(sb))!;
      expect(h.element).toBe(2);
      expect(h.point[0]).toBeCloseTo(0);
    });
    it('a ray that misses the section box altogether has no hit', () => {
      expect(castClipped({ o: [20, 50, 0], d: [-1, 0, 0] }, boxRange(east), noCaps(sb))).toBeNull();
    });
  });
});
