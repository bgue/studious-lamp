import { describe, expect, it } from 'vitest';
import { Box3, Vector3 } from 'three';
import { clamp01, easeInOutCubic, lerp, smoothStep } from '../src/cinematic/easing';
import { Flight, computeFlyView, fitDistance, isBehindCamera } from '../src/cinematic/flyto';
import type { FlyView } from '../src/cinematic/flyto';

const v = (x: number, y: number, z: number): Vector3 => new Vector3(x, y, z);

describe('easing', () => {
  it('hits 0, 0.5 and 1 and is monotonic', () => {
    for (const f of [smoothStep, easeInOutCubic]) {
      expect(f(0)).toBe(0);
      expect(f(1)).toBe(1);
      expect(f(0.5)).toBeCloseTo(0.5, 12);
      let prev = -1;
      for (let i = 0; i <= 100; i++) {
        const y = f(i / 100);
        expect(y).toBeGreaterThanOrEqual(prev);
        prev = y;
      }
    }
  });
  it('is flat at both ends (eases in and out)', () => {
    expect(easeInOutCubic(0.05)).toBeLessThan(0.05 * 0.1);
    expect(1 - easeInOutCubic(0.95)).toBeLessThan(0.05 * 0.1);
    expect(smoothStep(0.05)).toBeLessThan(0.05);
  });
  it('clamps outside 0..1', () => {
    expect(clamp01(-3)).toBe(0);
    expect(easeInOutCubic(2)).toBe(1);
    expect(lerp(2, 4, 0.25)).toBe(2.5);
  });
});

describe('computeFlyView', () => {
  const cam = { position: v(10, 0, 0), target: v(0, 0, 0), fovDeg: 60, aspect: 1 };
  const box = new Box3(v(-1, -1, -1), v(1, 1, 1));

  it('targets the box centre and fits the bounding sphere with the margin', () => {
    const view = computeFlyView(new Box3(v(3, 0, 0), v(5, 2, 2)), cam, { margin: 1 });
    expect(view.target.toArray()).toEqual([4, 1, 1]);
    const r = Math.sqrt(3);
    expect(view.position.distanceTo(view.target)).toBeCloseTo(fitDistance(r, 60, 1, 1), 9);
    // the sphere subtends exactly the field of view at margin 1
    expect(Math.asin(r / view.position.distanceTo(view.target))).toBeCloseTo((30 * Math.PI) / 180, 9);
  });

  it('keeps the current view direction', () => {
    const view = computeFlyView(box, cam);
    // camera at +x looking at -x: still on +x of the target
    const d = view.position.clone().sub(view.target).normalize();
    expect(d.x).toBeCloseTo(1, 9);
    expect(d.y).toBeCloseTo(0, 9);
  });

  it('keeps the view direction for an oblique view', () => {
    const c = { ...cam, position: v(3, 4, 0), target: v(0, 0, 0) };
    const view = computeFlyView(new Box3(v(-12, -12, -12), v(-10, -10, -10)), c);
    const d = view.position.clone().sub(view.target).normalize();
    expect(d.dot(v(3, 4, 0).normalize())).toBeCloseTo(1, 9);
  });

  it('approaches from the camera side when the focus is behind the camera', () => {
    // camera at +x looking toward -x; focus far behind it at x = 30
    const behind = new Box3(v(29, -1, -1), v(31, 1, 1));
    expect(isBehindCamera(cam.position, cam.target, v(30, 0, 0))).toBe(true);
    const view = computeFlyView(behind, cam);
    const d = view.position.clone().sub(view.target).normalize();
    // camera ends up on the -x side of the focus (the side it was already on), so it need not turn around
    expect(d.x).toBeCloseTo(-1, 9);
  });

  it('is not behind when the focus is ahead', () => {
    expect(isBehindCamera(cam.position, cam.target, v(-5, 3, 0))).toBe(false);
  });

  it('clamps the distance to the control limits', () => {
    const tiny = new Box3(v(0, 0, 0), v(0.001, 0.001, 0.001));
    const view = computeFlyView(tiny, { ...cam, minDistance: 2, maxDistance: 50 });
    expect(view.position.distanceTo(view.target)).toBeGreaterThanOrEqual(2);
    const huge = new Box3(v(-1e4, -1e4, -1e4), v(1e4, 1e4, 1e4));
    expect(computeFlyView(huge, { ...cam, maxDistance: 50 }).position.distanceTo(v(0, 0, 0))).toBeLessThanOrEqual(50);
  });

  it('uses an explicit direction and a default when degenerate', () => {
    const view = computeFlyView(box, cam, { direction: v(0, 5, 0) });
    expect(view.position.x).toBeCloseTo(0, 9);
    expect(view.position.y).toBeGreaterThan(0);
    const degenerate = computeFlyView(box, { ...cam, position: v(0, 0, 0), target: v(0, 0, 0) });
    expect(degenerate.position.distanceTo(degenerate.target)).toBeGreaterThan(0);
  });
});

describe('Flight', () => {
  const from: FlyView = { position: v(0, 0, 10), target: v(0, 0, 0) };
  const to: FlyView = { position: v(10, 0, 0), target: v(10, 0, -10) };
  const out: FlyView = { position: new Vector3(), target: new Vector3() };

  it('starts at from, ends at to, and the first sample starts the clock', () => {
    const f = new Flight(from, to, 900);
    expect(f.sample(5000, out)).toBe(false);
    expect(out.position.toArray()).toEqual([0, 0, 10]);
    expect(f.sample(5000 + 900, out)).toBe(true);
    expect(out.position.toArray()).toEqual([10, 0, 0]);
    expect(out.target.toArray()).toEqual([10, 0, -10]);
  });

  it('eases position and target together, symmetrically', () => {
    const f = new Flight(from, to, 1000);
    f.sample(0, out);
    f.sample(500, out);
    expect(out.position.x).toBeCloseTo(5, 9);
    expect(out.target.z).toBeCloseTo(-5, 9);
    f.sample(100, out);
    expect(out.position.x).toBeLessThan(1); // slow start: well under the linear 1.0
    f.sample(900, out);
    expect(out.position.x).toBeGreaterThan(9);
  });

  it('is monotonic in time and handles zero duration', () => {
    const f = new Flight(from, to, 900);
    let prev = -1;
    f.sample(0, out);
    for (let t = 0; t <= 900; t += 30) {
      f.sample(t, out);
      expect(out.position.x).toBeGreaterThanOrEqual(prev);
      prev = out.position.x;
    }
    expect(new Flight(from, to, 0).sample(0, out)).toBe(true);
  });

  it('does not alias the inputs', () => {
    const a: FlyView = { position: v(1, 1, 1), target: v(0, 0, 0) };
    const f = new Flight(a, to, 100);
    a.position.set(9, 9, 9);
    f.sample(0, out);
    expect(out.position.toArray()).toEqual([1, 1, 1]);
  });
});
