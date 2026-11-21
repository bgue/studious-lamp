import { describe, expect, it } from 'vitest';
import { Spline3, centripetal } from '../src/anim/spline';
import type { P3 } from '../src/anim/spline';
import { CameraPathSampler, rampedFraction } from '../src/anim/path';
import type { CameraPose } from '../src/anim/score';

const d = (a: P3, b: P3): number => Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
const pose = (x: number, y = 0, z = 0): CameraPose => ({ position: [x, y, z], target: [x, y, z - 5], up: [0, 1, 0], fovDeg: 50 });

describe('centripetal Catmull-Rom', () => {
  it('hits the end points of a segment exactly', () => {
    const p: P3[] = [[0, 0, 0], [1, 2, 3], [4, 1, -2], [6, 6, 6]];
    expect(centripetal(p[0]!, p[1]!, p[2]!, p[3]!, 0)).toEqual(p[1]);
    expect(centripetal(p[0]!, p[1]!, p[2]!, p[3]!, 1)).toEqual(p[2]);
  });

  it('passes through every point, first and last exactly', () => {
    const pts: P3[] = [[0, 0, 0], [2, 1, 0], [5, 4, 1], [9, 4, 3], [12, 0, 0]];
    const s = new Spline3(pts);
    pts.forEach((p, i) => expect(d(s.at(i), p)).toBeLessThan(1e-9));
    expect(s.at(0)).toEqual(pts[0]);
    expect(s.at(pts.length - 1)).toEqual(pts[pts.length - 1]);
  });

  it('does not overshoot on unevenly spaced points on a line', () => {
    // Spacing 0.1, 10, 0.1: the uniform form swings out of [0, 10.2] here.
    const pts: P3[] = [[0, 0, 0], [0.1, 0, 0], [10.1, 0, 0], [10.2, 0, 0]];
    const s = new Spline3(pts);
    let prev = -Infinity;
    for (let u = 0; u <= 3; u += 0.01) {
      const p = s.at(u);
      expect(p[0]).toBeGreaterThanOrEqual(-1e-9);
      expect(p[0]).toBeLessThanOrEqual(10.2 + 1e-9);
      expect(p[0]).toBeGreaterThanOrEqual(prev - 1e-9); // monotone: no loop-back
      prev = p[0];
      expect(Math.abs(p[1])).toBeLessThan(1e-9);
    }
  });

  it('stays inside the bounds of the points on a corner with uneven spacing', () => {
    const pts: P3[] = [[0, 0, 0], [0.2, 0, 0], [0.2, 20, 0], [0.4, 20, 0]];
    const s = new Spline3(pts);
    for (let u = 0; u <= 3; u += 0.02) {
      const p = s.at(u);
      expect(p[0]).toBeGreaterThan(-0.2);
      expect(p[0]).toBeLessThan(0.6);
      expect(p[1]).toBeGreaterThan(-0.5);
      expect(p[1]).toBeLessThan(20.5);
    }
  });

  it('handles one point, two points and coincident points', () => {
    expect(new Spline3([[1, 2, 3]]).at(0)).toEqual([1, 2, 3]);
    const two = new Spline3([[0, 0, 0], [10, 0, 0]]);
    expect(d(two.at(0.5), [5, 0, 0])).toBeLessThan(1e-9);
    const dup = new Spline3([[0, 0, 0], [0, 0, 0], [5, 0, 0]]);
    expect(Number.isFinite(dup.at(0.5)[0])).toBe(true);
  });

  it('reports arc lengths that add up, and maps a length fraction to a local t', () => {
    const s = new Spline3([[0, 0, 0], [3, 0, 0], [3, 4, 0]]);
    expect(s.length).toBeGreaterThan(6.9);
    expect(s.segLen).toHaveLength(2);
    const t = s.localTAtFraction(0, 0.5);
    const half = s.segmentAt(0, t);
    const start = s.segmentAt(0, 0);
    expect(d(start, half)).toBeCloseTo(s.segLen[0]! / 2, 1);
    expect(s.localTAtFraction(0, 0)).toBe(0);
    expect(s.localTAtFraction(0, 1)).toBeCloseTo(1, 9);
  });
});

describe('ramped fraction (ease in and out)', () => {
  it('runs 0 to 1, is monotone, and is linear without ramps', () => {
    expect(rampedFraction(0, 0.3, 0.3)).toBeCloseTo(0, 12);
    expect(rampedFraction(1, 0.3, 0.3)).toBeCloseTo(1, 12);
    expect(rampedFraction(0.37, 0, 0)).toBeCloseTo(0.37, 12);
    let prev = -1;
    for (let s = 0; s <= 1; s += 0.01) {
      const f = rampedFraction(s, 0.3, 0.2);
      expect(f).toBeGreaterThanOrEqual(prev - 1e-12);
      prev = f;
    }
  });

  it('starts slowly at an eased end and at full pace at a free end', () => {
    const slow = rampedFraction(0.02, 0.4, 0);
    const free = rampedFraction(0.02, 0, 0);
    expect(slow).toBeLessThan(free / 4);
    // Mid-run speed with an out ramp only: the start is not slowed.
    const e = 1e-4;
    const v0 = (rampedFraction(e, 0, 0.4) - rampedFraction(0, 0, 0.4)) / e;
    expect(v0).toBeGreaterThan(1);
  });
});

describe('CameraPathSampler', () => {
  it('starts and ends exactly at the first and last pose', () => {
    const s = new CameraPathSampler([pose(0), pose(10), pose(10, 5, 5)], [0, 4, 8]);
    expect(s.sample(0).position).toEqual([0, 0, 0]);
    expect(s.sample(8).position).toEqual([10, 5, 5]);
    expect(s.sample(-3).position).toEqual([0, 0, 0]);
    expect(s.sample(99).position).toEqual([10, 5, 5]);
  });

  it('reaches every keyframe at its time', () => {
    const poses = [pose(0), pose(4, 2), pose(9, -1, 3), pose(12, 0, 8)];
    const s = new CameraPathSampler(poses, [0, 3, 7, 12], { ease: 'inOut' });
    [0, 3, 7, 12].forEach((t, i) => expect(d(s.sample(t).position, poses[i]!.position as P3)).toBeLessThan(1e-6));
  });

  it('moves at constant speed between pass-through keyframes when the times follow the arc length', () => {
    const poses = [pose(0), pose(10), pose(20)];
    const s = new CameraPathSampler(poses, [0, 5, 10], { ease: 'linear' });
    const x1 = s.sample(1).position[0];
    const x2 = s.sample(2).position[0];
    const x7 = s.sample(7).position[0];
    const x8 = s.sample(8).position[0];
    expect(x2 - x1).toBeCloseTo(x8 - x7, 3);
  });

  it('eases in and out of the ends and holds the pose during a hold', () => {
    // Hold at the middle pose from t = 5 to t = 8.
    const poses = [pose(0), pose(10), pose(10), pose(20)];
    const s = new CameraPathSampler(poses, [0, 5, 8, 13], { ease: 'inOut' });
    expect(s.sample(5).position[0]).toBeCloseTo(10, 6);
    expect(s.sample(6.5).position[0]).toBeCloseTo(10, 6);
    expect(s.sample(8).position[0]).toBeCloseTo(10, 6);
    // Slow near the start (ease in), faster in the middle of the first move.
    const slow = s.sample(0.3).position[0] - s.sample(0).position[0];
    const mid = s.sample(2.8).position[0] - s.sample(2.5).position[0];
    expect(slow).toBeLessThan(mid / 2);
    // Slow when it arrives at the hold and when it leaves it.
    const into = s.sample(5).position[0] - s.sample(4.7).position[0];
    expect(into).toBeLessThan(mid / 2);
    const out = s.sample(8.3).position[0] - s.sample(8).position[0];
    expect(out).toBeLessThan(mid / 2);
  });

  it('does not slow down at a pass-through keyframe', () => {
    const poses = [pose(0), pose(10), pose(20)];
    const s = new CameraPathSampler(poses, [0, 5, 10], { ease: 'inOut' });
    const before = s.sample(5).position[0] - s.sample(4.8).position[0];
    const after = s.sample(5.2).position[0] - s.sample(5).position[0];
    expect(before).toBeGreaterThan(0.3);
    expect(Math.abs(before - after)).toBeLessThan(0.05);
  });

  it('keeps the ends free of ease when the cue says linear, and honours easeAt', () => {
    const lin = new CameraPathSampler([pose(0), pose(10)], [0, 10], { ease: 'linear' });
    expect(lin.sample(1).position[0]).toBeCloseTo(1, 6);
    const off = new CameraPathSampler([pose(0), pose(10)], [0, 10], { ease: 'inOut', easeAt: [false, false] });
    expect(off.sample(1).position[0]).toBeCloseTo(1, 6);
  });

  it('turns in place (an orbit with the camera fixed) by the knot parameter', () => {
    const a: CameraPose = { position: [0, 0, 0], target: [0, 0, -5] };
    const b: CameraPose = { position: [0, 0, 0], target: [5, 0, 0] };
    const s = new CameraPathSampler([a, b], [0, 4], { ease: 'linear' });
    const t = s.sample(2).target;
    expect(t[0]).toBeGreaterThan(0);
    expect(t[2]).toBeLessThan(0);
  });

  it('blends up and field of view and keeps up a unit vector', () => {
    const a: CameraPose = { position: [0, 0, 0], target: [0, 0, -1], up: [0, 1, 0], fovDeg: 40 };
    const b: CameraPose = { position: [4, 0, 0], target: [4, 0, -1], up: [1, 0, 0], fovDeg: 60 };
    const s = new CameraPathSampler([a, b], [0, 4], { ease: 'linear' });
    const m = s.sample(2);
    expect(m.fovDeg).toBeCloseTo(50, 6);
    expect(Math.hypot(...(m.up as P3))).toBeCloseTo(1, 9);
  });
});
