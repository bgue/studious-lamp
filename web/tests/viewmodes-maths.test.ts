import { describe, expect, it } from 'vitest';
import {
  JFA_START,
  PEEL_CAP_SLACK,
  behindFragment,
  boxScreenEllipse,
  bruteNearest,
  ellipseDistancePx,
  jfaNearest,
  jfaSteps,
  metresToPixels,
  minDotBox,
  nearestEllipse,
  nextPow2,
  peelAnimScale,
  peelCoverage,
  peelCutsPoint,
  peelFragment,
  peelRadius,
  peelRim,
  pixelsToMetres,
  planeFromCamera,
  planeHorizontal,
  planeSide,
} from '../src/viewModes/maths';
import type { Box6, PeelMaths } from '../src/viewModes/maths';

const box = (a: number, b: number, c: number, d: number, e: number, f: number): Box6 => [a, b, c, d, e, f];

describe('behind-only plane', () => {
  it('passes through the nearest focus point along the view direction, pushed toward the camera by the offset', () => {
    // camera looks along +x; the focus box spans x 4..6, so its nearest point is at x = 4
    const pl = planeFromCamera([1, 0, 0], [box(4, 0, 0, 6, 1, 1)], 0)!;
    expect(pl.nx).toBeCloseTo(1);
    expect(pl.d).toBeCloseTo(4);
    const off = planeFromCamera([1, 0, 0], [box(4, 0, 0, 6, 1, 1)], 0.2)!;
    expect(off.d).toBeCloseTo(3.8);
    const into = planeFromCamera([1, 0, 0], [box(4, 0, 0, 6, 1, 1)], -0.5)!;
    expect(into.d).toBeCloseTo(4.5); // negative offset cuts into the focus
  });

  it('uses the nearest corner over all boxes, for an oblique and a non-unit direction', () => {
    const boxes = [box(5, 5, 5, 6, 6, 6), box(2, 3, 4, 3, 4, 5)];
    const pl = planeFromCamera([2, 0, 2], boxes, 0)!; // normalised to (1,0,1)/sqrt2
    const s = Math.SQRT1_2;
    expect(pl.nx).toBeCloseTo(s);
    expect(pl.nz).toBeCloseTo(s);
    expect(pl.d).toBeCloseTo(Math.min(s * 5 + s * 5, s * 2 + s * 4));
  });

  it('minDotBox picks the corner by the sign of each component', () => {
    expect(minDotBox([1, -1, 0], box(0, 0, 0, 2, 3, 1))).toBeCloseTo(0 - 3);
    expect(minDotBox([-1, -1, -1], box(1, 1, 1, 2, 2, 2))).toBeCloseTo(-6);
  });

  it('returns null without focus or without a direction', () => {
    expect(planeFromCamera([1, 0, 0], [], 0)).toBeNull();
    expect(planeFromCamera([0, 0, 0], [box(0, 0, 0, 1, 1, 1)], 0)).toBeNull();
    expect(planeHorizontal([], 0)).toBeNull();
  });

  it('a horizontal plane sits at the focus top plus the offset and the front side is above it', () => {
    const pl = planeHorizontal([box(0, 1, 0, 1, 2.5, 1), box(0, 0, 0, 1, 1, 1)], 0.3)!;
    expect(planeSide(pl, [0, 2.8, 0])).toBeCloseTo(0); // on the plane
    expect(planeSide(pl, [0, 3.5, 0])).toBeGreaterThan(0); // above: front side (cut)
    expect(planeSide(pl, [0, 1, 0])).toBeLessThan(0); // below: kept
  });

  it('planeSide is positive on the camera side', () => {
    const pl = planeFromCamera([0, 0, -1], [box(0, 0, -6, 1, 1, -4)], 0)!; // looking along -z; nearest focus point at z = -4
    expect(planeSide(pl, [0, 0, 0])).toBeCloseTo(4); // the camera side, 4 m in front
    expect(planeSide(pl, [0, 0, -5])).toBeLessThan(0);
  });

  it('splits a fragment by side: cut, ghost at the front alpha, solid behind unless x-ray is kept, cap on back faces', () => {
    const o = { treatment: 'cut' as const, frontAlpha: 0.12, keepXray: false };
    expect(behindFragment(1, 0.3, false, o)).toEqual({ cover: 0, alpha: 0.3, cap: false });
    expect(behindFragment(-1, 0.3, false, o)).toEqual({ cover: 1, alpha: 1, cap: false });
    expect(behindFragment(-1, 0.3, false, { ...o, keepXray: true }).alpha).toBe(0.3);
    expect(behindFragment(1, 1, false, { ...o, treatment: 'ghost' })).toEqual({ cover: 1, alpha: 0.12, cap: false });
    expect(behindFragment(-1, 1, true, { ...o, treatment: 'cut + cap' }).cap).toBe(true);
    expect(behindFragment(-1, 1, false, { ...o, treatment: 'cut + cap' }).cap).toBe(false);
    expect(behindFragment(1, 1, true, { ...o, treatment: 'cut + cap' })).toEqual({ cover: 0, alpha: 1, cap: false });
  });
});

describe('peelback radius, feather and projection', () => {
  const p: PeelMaths = { r0: 0.4, slope: 0.6, feather: 0.08, eps: 0.05 };

  it('r(z) = r0 + slope * (zFocus - z), growing toward the viewer, and r0 at or behind the focus', () => {
    expect(peelRadius(0.4, 0.6, 10, 10)).toBeCloseTo(0.4);
    expect(peelRadius(0.4, 0.6, 10, 8)).toBeCloseTo(0.4 + 0.6 * 2);
    expect(peelRadius(0.4, 0.6, 10, 12)).toBeCloseTo(0.4);
  });

  it('metres and pixels convert with the pinhole projection and round-trip', () => {
    const fov = (45 * Math.PI) / 180;
    // at 10 m a 1080 px tall frame sees 2 * 10 * tan(22.5 deg) = 8.284 m
    expect(metresToPixels(1, 10, fov, 1080)).toBeCloseTo(1080 / 8.2843, 1);
    expect(pixelsToMetres(metresToPixels(0.4, 7, fov, 720), 7, fov, 720)).toBeCloseTo(0.4);
    expect(metresToPixels(1, 5, fov, 1080)).toBeCloseTo(2 * metresToPixels(1, 10, fov, 1080));
  });

  it('feather: 0 inside the radius, smoothly 1 at radius + feather, monotone; zero feather is a hard edge', () => {
    expect(peelCoverage(0.3, 0.4, 0.08)).toBe(0);
    expect(peelCoverage(0.4, 0.4, 0.08)).toBe(0);
    expect(peelCoverage(0.44, 0.4, 0.08)).toBeCloseTo(0.5, 5);
    expect(peelCoverage(0.48, 0.4, 0.08)).toBe(1);
    let prev = -1;
    for (let d = 0.3; d < 0.6; d += 0.01) {
      const c = peelCoverage(d, 0.4, 0.08);
      expect(c).toBeGreaterThanOrEqual(prev);
      prev = c;
    }
    expect(peelCoverage(0.399, 0.4, 0)).toBe(0);
    expect(peelCoverage(0.401, 0.4, 0)).toBe(1);
  });

  it('rim band: 0 inside, 1 at the edge, fading to 0 beyond feather + 3 cm', () => {
    expect(peelRim(0.3, 0.4, 0.08)).toBe(0);
    expect(peelRim(0.4, 0.4, 0.08)).toBeCloseTo(1);
    expect(peelRim(0.4 + 0.08 + 0.03, 0.4, 0.08)).toBeCloseTo(0);
    expect(peelRim(0.45, 0.4, 0.08)).toBeGreaterThan(0);
  });

  it('a fragment in front of the focus inside the window is cut; beside it, outside the window, it is kept', () => {
    const fov = (45 * Math.PI) / 180;
    const resY = 1000;
    // focus at 10 m, fragment at 8 m (2 m in front): R = 0.4 + 0.6 * 2 = 1.6 m, measured on screen at the focus depth
    const inside = peelFragment(metresToPixels(1.0, 10, fov, resY), 10, 8, false, p, fov, resY);
    expect(inside.cover).toBe(0);
    expect(inside.inFront).toBe(true);
    const outside = peelFragment(metresToPixels(2.0, 10, fov, resY), 10, 8, false, p, fov, resY);
    expect(outside.cover).toBe(1);
    // the same screen offset is outside when the fragment is closer to the focus depth (R shrinks): the window is angled
    const nearFocus = peelFragment(metresToPixels(1.0, 10, fov, resY), 10, 9.9, false, p, fov, resY);
    expect(nearFocus.cover).toBe(1);
  });

  it('never cuts what is at or behind the focus depth (within eps)', () => {
    const fov = 0.8;
    expect(peelFragment(0, 10, 10, false, p, fov, 1000).cover).toBe(1);
    expect(peelFragment(0, 10, 10.5, false, p, fov, 1000).cover).toBe(1);
    expect(peelFragment(0, 10, 9.96, false, p, fov, 1000).cover).toBe(1); // within eps = 0.05
    expect(peelFragment(0, 10, 9.9, false, p, fov, 1000).cover).toBe(0);
  });

  it('the depth tolerance grows with the screen distance, so a flush oblique wall beside the focus is not cut', () => {
    const fov = 0.8;
    const resY = 1000;
    const d = (m: number): number => metresToPixels(m, 10, fov, resY);
    // 0.4 m beside the focus, 0.55 m nearer (a wall seen at 54 degrees): tolerance 0.2 + 1.0 * 0.4 = 0.6, kept
    const q: PeelMaths = { ...p, eps: 0.2 };
    expect(peelFragment(d(0.4), 10, 9.45, false, q, fov, resY).cover).toBe(1);
    // an obstruction 2 m in front is cut at the same offset
    expect(peelFragment(d(0.4), 10, 8, false, q, fov, resY).cover).toBe(0);
    // far outside the window nothing is cut anyway
    expect(peelFragment(d(5), 10, 8, false, q, fov, resY).cover).toBe(1);
  });

  it('caps back faces near the window that were not cut', () => {
    const fov = 0.8;
    const behind = peelFragment(0, 10, 10.2, true, p, fov, 1000);
    expect(behind.cover).toBe(1);
    expect(behind.cap).toBe(true);
    const front = peelFragment(0, 10, 9, true, p, fov, 1000); // cut: no cap
    expect(front.cover).toBe(0);
    expect(front.cap).toBe(false);
    // far from the window: no cap
    expect(peelFragment(5000, 10, 10.2, true, p, fov, 1000).cap).toBe(false);
    expect(PEEL_CAP_SLACK).toBeGreaterThan(0);
  });

  it('grow animation: 0 at the start, 1 after 500 ms, ease-out in between', () => {
    expect(peelAnimScale(0)).toBe(0);
    expect(peelAnimScale(500)).toBe(1);
    expect(peelAnimScale(900)).toBe(1);
    expect(peelAnimScale(-5)).toBe(0);
    expect(peelAnimScale(250)).toBeGreaterThan(0.5); // ease out
    expect(peelAnimScale(100, 0)).toBe(1);
  });
});

describe('jump flooding', () => {
  it('steps halve down to 1 and repeat 1 once', () => {
    expect(jfaSteps(8)).toEqual([8, 4, 2, 1, 1]);
    expect(jfaSteps(1)).toEqual([1, 1]);
    expect(jfaSteps(JFA_START)[0]).toBe(JFA_START);
    expect(nextPow2(33)).toBe(64);
    expect(nextPow2(1)).toBe(1);
  });

  const makeMask = (w: number, h: number, seeds: Array<[number, number]>): Uint8Array => {
    const m = new Uint8Array(w * h);
    for (const [x, y] of seeds) m[y * w + x] = 1;
    return m;
  };
  const d2 = (i: number, j: number, w: number): number => {
    const ix = i % w;
    const jx = j % w;
    return (ix - jx) ** 2 + ((i - ix) / w - (j - jx) / w) ** 2;
  };

  it('finds exactly the nearest seed for a single seed', () => {
    const w = 33;
    const h = 21;
    const mask = makeMask(w, h, [[7, 5]]);
    const a = jfaNearest(mask, w, h);
    expect(Array.from(a).every((v) => v === 5 * w + 7)).toBe(true);
  });

  it('matches brute force closely for random seed sets (distance error within 1 px, almost everywhere exact)', () => {
    const w = 64;
    const h = 40;
    let state = 12345;
    const rnd = (): number => {
      state = (state * 1664525 + 1013904223) >>> 0;
      return state / 4294967296;
    };
    for (const count of [1, 3, 12, 40]) {
      const seeds: Array<[number, number]> = [];
      for (let i = 0; i < count; i++) seeds.push([Math.floor(rnd() * w), Math.floor(rnd() * h)]);
      const mask = makeMask(w, h, seeds);
      const a = jfaNearest(mask, w, h);
      const b = bruteNearest(mask, w, h);
      let exact = 0;
      let worst = 0;
      for (let i = 0; i < w * h; i++) {
        expect(a[i]).toBeGreaterThanOrEqual(0);
        const e = Math.sqrt(d2(i, a[i]!, w)) - Math.sqrt(d2(i, b[i]!, w));
        worst = Math.max(worst, e);
        if (e < 1e-9) exact++;
      }
      expect(worst).toBeLessThan(1.5);
      expect(exact / (w * h)).toBeGreaterThan(0.97);
    }
  });

  it('leaves pixels without any seed at -1', () => {
    expect(Array.from(jfaNearest(new Uint8Array(12), 4, 3)).every((v) => v === -1)).toBe(true);
  });
});

describe('screen ellipses and the CPU pick test', () => {
  // an identity-like orthographic setup: viewProj maps x,y in [-1,1] to the screen, w = 1; view looks down -z
  const ident = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];
  const persp = (() => {
    // perspective, fov such that tan(fov/2) = 1, aspect 1, near 0.1 far 100; camera at the origin looking down -z
    const n = 0.1;
    const f = 100;
    return [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, -(f + n) / (f - n), -1, 0, 0, (-2 * f * n) / (f - n), 0];
  })();

  it('projects a box in front of the camera to an ellipse around its screen rectangle, with the centre depth', () => {
    const e = boxScreenEllipse(persp, ident, box(-1, -1, -11, 1, 1, -9), 200, 200)!;
    expect(e).not.toBeNull();
    expect(e.cx).toBeCloseTo(100, 0);
    expect(e.cy).toBeCloseTo(100, 0);
    expect(e.z).toBeCloseTo(10, 5);
    // the nearest face at z = -9 spans +-1/9 of the half screen: 100/9 = 11.1 px; the far face is smaller
    expect(e.ax).toBeCloseTo((100 / 9) * Math.SQRT2, 0);
  });

  it('a box wholly behind the camera gives null; one crossing the camera plane covers the screen', () => {
    expect(boxScreenEllipse(persp, ident, box(-1, -1, 5, 1, 1, 7), 200, 200)).toBeNull();
    const e = boxScreenEllipse(persp, ident, box(-1, -1, -3, 1, 1, 3), 200, 200)!;
    expect(e.ax).toBeGreaterThanOrEqual(200);
  });

  it('distance to an ellipse is 0 inside and grows outside; the nearest of several wins', () => {
    const e1 = { cx: 100, cy: 100, ax: 20, ay: 10, z: 5 };
    const e2 = { cx: 300, cy: 100, ax: 10, ay: 10, z: 9 };
    expect(ellipseDistancePx(e1, 100, 100)).toBe(0);
    expect(ellipseDistancePx(e1, 110, 100)).toBe(0);
    expect(ellipseDistancePx(e1, 140, 100)).toBeCloseTo(10, 5); // one semi-axis (min = 10) beyond: k = 2
    expect(nearestEllipse([e1, e2], 290, 100)!.z).toBe(9);
    expect(nearestEllipse([], 0, 0)).toBeNull();
  });

  it('peelCutsPoint: cuts a surface point in front of the focus inside the window, keeps it behind or far to the side', () => {
    const fov = (45 * Math.PI) / 180;
    const p: PeelMaths = { r0: 0.4, slope: 0.6, feather: 0.08, eps: 0.05 };
    const list = [{ cx: 500, cy: 400, ax: 30, ay: 30, z: 10 }];
    expect(peelCutsPoint(list, 500, 400, 8, p, fov, 800)).toBe(true); // straight in front
    expect(peelCutsPoint(list, 500, 400, 10.5, p, fov, 800)).toBe(false); // behind the focus
    expect(peelCutsPoint(list, 900, 400, 8, p, fov, 800)).toBe(false); // far to the side
    expect(peelCutsPoint([], 500, 400, 8, p, fov, 800)).toBe(false);
    // the window widens toward the viewer: a point at the same screen offset is cut when nearer, kept when at the focus
    const off = 30 + metresToPixels(0.9, 10, fov, 800);
    expect(peelCutsPoint(list, 500 + off, 400, 9.5, p, fov, 800)).toBe(false);
    expect(peelCutsPoint(list, 500 + 30 + metresToPixels(1.0, 5, fov, 800), 400, 5, p, fov, 800)).toBe(true);
  });
});
