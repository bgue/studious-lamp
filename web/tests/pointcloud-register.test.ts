// 3-point (n-point) registration: Horn / Kabsch, the keep-vertical 2D solve, Umeyama scale, warnings; the general
// transform of the cloud frame (registration + nudge), its yaw decomposition; the params section with old documents;
// screen-space point picking.

import { describe, expect, it } from 'vitest';
import { applyFrame, cloudFrame, decomposeTotal } from '../src/pointcloud/align';
import { defaultPointCloudSettings } from '../src/pointcloud/controller';
import { applyPointCloudParams, collectPointCloudParams, validRegistration } from '../src/pointcloud/params';
import { buildScreenIndex, pickNearest } from '../src/pointcloud/pick';
import {
  apply, compose, identity, invertSimilarity, isIdentity, isYawOnly, mul, rotationY, scaleOf, solvePairs, spreadOf, transformError, translation, yawDeg,
} from '../src/pointcloud/register';
import type { Mat4 } from '../src/pointcloud/register';
import type { Vec3 } from '../src/pointcloud/types';

/** Deterministic pseudo random numbers (mulberry32) and a Gaussian from them. */
function rng(seed: number): { u(): number; g(): number } {
  let a = seed >>> 0;
  const u = (): number => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
  return { u, g: () => Math.sqrt(-2 * Math.log(u() + 1e-12)) * Math.cos(2 * Math.PI * u()) };
}

/** Rotation by angle about a unit axis, row-major 3x3. */
function axisAngle(ax: Vec3, deg: number): number[] {
  const l = Math.hypot(...ax);
  const [x, y, z] = ax.map((v) => v / l) as Vec3;
  const t = (deg * Math.PI) / 180, c = Math.cos(t), s = Math.sin(t), C = 1 - c;
  return [c + x * x * C, x * y * C - z * s, x * z * C + y * s, y * x * C + z * s, c + y * y * C, y * z * C - x * s, z * x * C - y * s, z * y * C + x * s, c + z * z * C];
}

const pts = (r: ReturnType<typeof rng>, n: number, size = 5): Vec3[] => Array.from({ length: n }, () => [(r.u() - 0.5) * size, (r.u() - 0.5) * size * 0.6, (r.u() - 0.5) * size] as Vec3);
const noisy = (r: ReturnType<typeof rng>, p: Vec3, sigma: number): Vec3 => [p[0] + sigma * r.g(), p[1] + sigma * r.g(), p[2] + sigma * r.g()];

describe('matrix helpers', () => {
  it('composes, applies and inverts similarity transforms', () => {
    const m = compose(axisAngle([1, 2, 3], 40), 1.3, [4, -5, 6]);
    const p: Vec3 = [0.3, -1.2, 2];
    const back = apply(invertSimilarity(m), apply(m, p));
    back.forEach((v, i) => expect(v).toBeCloseTo(p[i]!, 12));
    expect(scaleOf(m)).toBeCloseTo(1.3, 12);
    expect(isIdentity(mul(m, invertSimilarity(m)), 1e-12)).toBe(true);
  });
  it('recognises a yaw and reads its angle like three makeRotationY', () => {
    const m = mul(translation(1, 2, 3), rotationY((37 * Math.PI) / 180));
    expect(isYawOnly(m)).toBe(true);
    expect(yawDeg(m)).toBeCloseTo(37, 12);
    // makeRotationY(+90) sends +x to -z
    const q = apply(rotationY(Math.PI / 2), [1, 0, 0]);
    [0, 0, -1].forEach((v, i) => expect(q[i]).toBeCloseTo(v, 12));
    expect(isYawOnly(compose(axisAngle([1, 0, 0], 1), 1, [0, 0, 0]))).toBe(false);
    expect(isYawOnly(compose(axisAngle([0, 1, 0], 10), 1.01, [0, 0, 0]))).toBe(false);
  });
});

describe('solvePairs (Horn / Kabsch / Umeyama)', () => {
  it('recovers a full 3D rigid transform exactly from 3 pairs and in least squares from many noisy ones', () => {
    const r = rng(1);
    const T = compose(axisAngle([0.3, 1, -0.4], 63), 1, [12.5, -3.25, 7]);
    const src = pts(r, 3);
    const s3 = solvePairs(src, src.map((p) => apply(T, p)), { keepVertical: false, allowScale: false });
    expect(s3.ok).toBe(true);
    expect(s3.rms).toBeLessThan(1e-9);
    const e3 = transformError(T, s3.matrix);
    expect(e3.rotationDeg).toBeLessThan(1e-6);
    expect(e3.translation).toBeLessThan(1e-9);
    const many = pts(r, 40);
    const s = solvePairs(many, many.map((p) => noisy(r, apply(T, p), 0.01)), { keepVertical: false, allowScale: false });
    const e = transformError(T, s.matrix);
    expect(e.rotationDeg).toBeLessThan(0.3);
    expect(e.translation).toBeLessThan(0.01);
    expect(s.rms).toBeGreaterThan(0.01);
    expect(s.rms).toBeLessThan(0.025);
    expect(s.scale).toBe(1);
    expect(s.residuals).toHaveLength(40);
  });
  it('handles a half turn (the quaternion method has no reflection or 180 degree problem)', () => {
    const r = rng(2);
    const T = compose(axisAngle([0, 0, 1], 180), 1, [1, 2, 3]);
    const src = pts(r, 5);
    const s = solvePairs(src, src.map((p) => apply(T, p)), { keepVertical: false, allowScale: false });
    expect(transformError(T, s.matrix).rotationDeg).toBeLessThan(1e-6);
  });
  it('keep vertical: recovers yaw and translation, also from 2 pairs, and stays upright on tilted data', () => {
    const r = rng(3);
    const T = mul(translation(-4.2, 1.15, 9.8), rotationY((37 * Math.PI) / 180));
    const src = pts(r, 2);
    const s2 = solvePairs(src, src.map((p) => apply(T, p)), { keepVertical: true, allowScale: false });
    expect(s2.ok).toBe(true);
    expect(s2.needed).toBe(2);
    expect(transformError(T, s2.matrix).rotationDeg).toBeLessThan(1e-9);
    expect(isYawOnly(s2.matrix)).toBe(true);
    const many = pts(r, 30);
    const sn = solvePairs(many, many.map((p) => noisy(r, apply(T, p), 0.015)), { keepVertical: true, allowScale: false });
    expect(Math.abs(yawDeg(sn.matrix) - 37)).toBeLessThan(0.3);
    expect(transformError(T, sn.matrix).translation).toBeLessThan(0.01);
    expect(isYawOnly(sn.matrix, 1e-12)).toBe(true);
    // data with a 2 degree tilt: the solve stays a pure yaw, the residual carries the tilt
    const tilted = mul(T, compose(axisAngle([1, 0, 0], 2), 1, [0, 0, 0]));
    const st = solvePairs(many, many.map((p) => apply(tilted, p)), { keepVertical: true, allowScale: false });
    expect(isYawOnly(st.matrix, 1e-12)).toBe(true);
    expect(Math.abs(yawDeg(st.matrix) - 37)).toBeLessThan(0.5);
  });
  it('estimates a uniform scale only when allowed (Umeyama), with and without keep vertical', () => {
    const r = rng(4);
    const T = compose(axisAngle([0, 1, 0], -20), 1.25, [3, 0.5, -2]);
    const src = pts(r, 6);
    const dst = src.map((p) => apply(T, p));
    for (const keepVertical of [false, true]) {
      const s = solvePairs(src, dst, { keepVertical, allowScale: true });
      expect(s.scale).toBeCloseTo(1.25, 9);
      expect(transformError(T, s.matrix).translation).toBeLessThan(1e-9);
      expect(s.warnings.some((w) => /scale/.test(w))).toBe(true);
      const rigid = solvePairs(src, dst, { keepVertical, allowScale: false });
      expect(rigid.scale).toBe(1);
      expect(scaleOf(rigid.matrix)).toBeCloseTo(1, 12);
      expect(rigid.rms).toBeGreaterThan(0.1);
    }
  });
  it('detects collinear and nearly collinear points, and points stacked on plan', () => {
    const line: Vec3[] = [[0, 0, 0], [1, 0.5, 0], [2, 1, 0]];
    const T = compose(axisAngle([0, 1, 0], 30), 1, [1, 1, 1]);
    const s = solvePairs(line, line.map((p) => apply(T, p)), { keepVertical: false, allowScale: false });
    expect(s.ok).toBe(false);
    expect(s.warnings[0]).toMatch(/line/);
    const near: Vec3[] = [[0, 0, 0], [2, 0, 0], [1, 0.1, 0]];
    const sn = solvePairs(near, near.map((p) => apply(T, p)), { keepVertical: false, allowScale: false });
    expect(sn.ok).toBe(true);
    expect(sn.warnings.some((w) => /nearly on a line/.test(w))).toBe(true);
    expect(spreadOf(near).planarity).toBeLessThan(0.08);
    // collinear points are fine with keep vertical (the line is not vertical): 2 points fix a yaw
    const sv = solvePairs(line, line.map((p) => apply(mul(translation(1, 2, 3), rotationY(0.5)), p)), { keepVertical: true, allowScale: false });
    expect(sv.ok).toBe(true);
    expect(sv.rms).toBeLessThan(1e-9);
    const stacked: Vec3[] = [[1, 0, 1], [1, 2, 1], [1.01, 3, 1]];
    expect(solvePairs(stacked, stacked, { keepVertical: true, allowScale: false }).ok).toBe(false);
    expect(solvePairs(line.slice(0, 2), line.slice(0, 2), { keepVertical: false, allowScale: false }).warnings[0]).toMatch(/at least 3/);
  });
  it('warns about a large residual and names the pair', () => {
    const r = rng(5);
    const T = mul(translation(2, 0, 1), rotationY(0.3));
    const src = pts(r, 4);
    const dst = src.map((p) => apply(T, p));
    dst[2] = [dst[2]![0] + 0.4, dst[2]![1], dst[2]![2]];
    const s = solvePairs(src, dst, { keepVertical: true, allowScale: false });
    expect(s.warnings.some((w) => /pair 3/.test(w))).toBe(true);
    expect(s.residuals[2]).toBeGreaterThan(0.2);
  });
});

describe('cloud frame with a registration', () => {
  const info = { origin: [10, 2, -3] as Vec3, boundsMin: [8, 0, -6] as Vec3, boundsMax: [14, 3, 0] as Vec3 };
  const shift: Vec3 = [5.8, 6, 2.55];
  it('is the original offset + yaw transform when the registration is the identity', () => {
    for (const mode of ['viewer', 'project'] as const) {
      const f0 = cloudFrame(info, { mode, shift, offset: [0.5, -0.25, 1], rotationDeg: 33 });
      const f1 = cloudFrame(info, { mode, shift, offset: [0.5, -0.25, 1], rotationDeg: 33, registration: identity() });
      expect(f1.matrix.elements).toEqual(f0.matrix.elements);
      // total maps c = g + base the same way
      const g: Vec3 = [0.3, 1.1, -0.7];
      const c: Vec3 = [g[0] + f0.base[0], g[1] + f0.base[1], g[2] + f0.base[2]];
      apply(f0.total, c).forEach((v, i) => expect(v).toBeCloseTo(applyFrame(f0, g)[i]!, 9));
    }
  });
  it('applies the nudge on top of the registration, about the registered bounds centre', () => {
    const A = compose(axisAngle([1, 1, 0], 5), 1, [3, -1, 2]);
    const f = cloudFrame(info, { mode: 'viewer', shift, offset: [0.2, 0, 0], rotationDeg: 90, registration: A });
    const g: Vec3 = [1, 0, 0];
    const c: Vec3 = [g[0] + f.base[0], g[1] + f.base[1], g[2] + f.base[2]];
    const ac = apply(A, c), ap = apply(A, f.pivot);
    // expected: Ry(90) (A c - A pivot) + A pivot + offset
    const d = apply(rotationY(Math.PI / 2), [ac[0] - ap[0], ac[1] - ap[1], ac[2] - ap[2]]);
    const want: Vec3 = [d[0] + ap[0] + 0.2, d[1] + ap[1], d[2] + ap[2]];
    applyFrame(f, g).forEach((v, i) => expect(v).toBeCloseTo(want[i]!, 9));
  });
  it('decomposes a yaw-only total into offset + rotation (identity registration) and keeps a tilt as the matrix', () => {
    const f0 = cloudFrame(info, { mode: 'project', shift, offset: [0, 0, 0], rotationDeg: 0 });
    const T: Mat4 = mul(translation(-1.5, 0.25, 4), rotationY((-123.4 * Math.PI) / 180));
    const parts = decomposeTotal(T, f0.pivot);
    expect(isIdentity(parts.registration)).toBe(true);
    expect(parts.rotationDeg).toBeCloseTo(-123.4, 9);
    const f1 = cloudFrame(info, { mode: 'project', shift, offset: parts.offset, rotationDeg: parts.rotationDeg, registration: parts.registration });
    for (let i = 0; i < 16; i++) expect(f1.total[i]).toBeCloseTo(T[i]!, 9);
    const tilt = mul(T, compose(axisAngle([1, 0, 0], 1), 1, [0, 0, 0]));
    const p2 = decomposeTotal(tilt, f0.pivot);
    expect(p2.offset).toEqual([0, 0, 0]);
    expect(p2.rotationDeg).toBe(0);
    const f2 = cloudFrame(info, { mode: 'project', shift, offset: p2.offset, rotationDeg: p2.rotationDeg, registration: p2.registration });
    for (let i = 0; i < 16; i++) expect(f2.total[i]).toBeCloseTo(tilt[i]!, 12);
  });
  it('keeps millimetres for a georeferenced cloud under a full rotation', () => {
    const origin: Vec3 = [2_600_000.001, 1_200_000.002, 500];
    const gi = { origin, boundsMin: origin, boundsMax: [origin[0] + 10, origin[1] + 10, origin[2] + 3] as Vec3 };
    // registration: bring the cloud to the viewer origin and tilt it a little
    const A = mul(compose(axisAngle([1, 0.2, 0], 0.7), 1, [0, 0, 0]), translation(-origin[0], -origin[1], -origin[2]));
    const f = cloudFrame(gi, { mode: 'viewer', shift, offset: [0, 0, 0], rotationDeg: 0, registration: A });
    const a = applyFrame(f, [0, 0, 0]);
    const b = applyFrame(f, [0.003, 0, 0]);
    expect(Math.hypot(b[0] - a[0], b[1] - a[1], b[2] - a[2])).toBeCloseTo(0.003, 7);
    expect(Math.hypot(...a)).toBeLessThan(1e-6);
  });
});

describe('params section', () => {
  it('round trips through JSON, matrix and alignment switches included', () => {
    const s = defaultPointCloudSettings();
    s.offsetX = 1.5; s.offsetY = -2; s.offsetZ = 0.25; s.rotationDeg = 12.5; s.keepVertical = false; s.allowScale = true; s.coordinates = 'viewer';
    s.matrix = compose(axisAngle([1, 0, 1], 3), 1.01, [100, 2, -3]);
    const doc = JSON.parse(JSON.stringify(collectPointCloudParams(s))) as Record<string, unknown>;
    expect((doc['matrix'] as number[]).length).toBe(16);
    const t = defaultPointCloudSettings();
    const bad: string[] = [];
    applyPointCloudParams(t, doc, bad, 'pointcloud');
    expect(bad).toEqual([]);
    expect(t).toEqual(s);
  });
  it('reads an old document (offset and rotationDeg, no matrix) as no registration', () => {
    const t = defaultPointCloudSettings();
    t.matrix = compose(axisAngle([0, 1, 0], 10), 1, [1, 2, 3]);
    const bad: string[] = [];
    applyPointCloudParams(t, { visible: true, coordinates: 'project', offset: [1, 2, 3], rotationDeg: 45, tolerance: 0.03, scope: 'focus only' }, bad, 'pc');
    expect(bad).toEqual([]);
    expect(isIdentity(t.matrix)).toBe(true);
    expect([t.offsetX, t.offsetY, t.offsetZ, t.rotationDeg, t.keepVertical, t.allowScale]).toEqual([1, 2, 3, 45, true, false]);
    // a document without any alignment key leaves the registration alone
    const u = defaultPointCloudSettings();
    u.matrix = translation(1, 0, 0);
    applyPointCloudParams(u, { pointSize: 3 }, bad, 'pc');
    expect(u.matrix).toEqual(translation(1, 0, 0));
  });
  it('rejects a matrix that is not a rotation times a uniform scale', () => {
    const bad: string[] = [];
    const t = defaultPointCloudSettings();
    const shear = identity();
    shear[4] = 0.5;
    applyPointCloudParams(t, { matrix: shear }, bad, 'pc');
    applyPointCloudParams(t, { matrix: [1, 2, 3] }, bad, 'pc');
    applyPointCloudParams(t, { matrix: identity().map((v, i) => (i === 3 ? 1 : v)) }, bad, 'pc');
    applyPointCloudParams(t, { keepVertical: 'yes' }, bad, 'pc');
    expect(bad).toEqual(['pc.matrix', 'pc.matrix', 'pc.matrix', 'pc.keepVertical']);
    expect(isIdentity(t.matrix)).toBe(true);
    expect(validRegistration(compose(axisAngle([1, 2, 3], 77), 0.5, [1e6, 2e6, 3]))).toBe(true);
  });
});

describe('screen-space point picking', () => {
  // orthographic camera looking down -z: clip = (x/5, y/5, ...), view depth = -z
  const clip = [0.2, 0, 0, 0, 0, 0.2, 0, 0, 0, 0, -0.01, 0, 0, 0, 0, 1];
  const view = identity();
  const W = 500, H = 500; // 1 px = 0.02 world units, screen x = (x / 5 * 0.5 + 0.5) * 500
  const sx = (x: number): number => (x / 5 * 0.5 + 0.5) * W;
  const sy = (y: number): number => (0.5 - y / 5 * 0.5) * H;
  it('takes what covers the cursor first, else the frontmost surface within the radius, then the nearest on screen', () => {
    // a back plane at z = -10 (dense) and a front patch at z = -2; cursor over both
    const p: number[] = [];
    for (let i = -20; i <= 20; i++) for (let j = -20; j <= 20; j++) p.push(i * 0.05, j * 0.05, -10);
    const front = p.length / 3;
    p.push(0.06, 0.0, -2, 1.5, 0, -2, 0.6, 0.6, -2, 0.6005, 0.6, -2.5, 1.63, 0, -3);
    const idx = buildScreenIndex({ positions: new Float32Array(p), clip, view, width: W, height: H });
    // the back point under the cursor is what the user sees there: it beats the front point 3 px away
    expect(pickNearest(idx, sx(0), sx(0), { radiusPx: 8 })).toBeLessThan(front);
    // without the cover step, the front point 0.06 away (3 px) beats the back point under the cursor
    expect(pickNearest(idx, sx(0), sx(0), { radiusPx: 8, innerPx: 0 })).toBe(front);
    // a gap: 4 px from the front point, nothing covers the cursor, so the frontmost within 8 px wins
    expect(pickNearest(idx, sx(1.58), sx(0), { radiusPx: 8 })).toBe(front + 1);
    // 2 points under the cursor: the front one
    expect(pickNearest(idx, sx(0.6), sy(0.6), { radiusPx: 8 })).toBe(front + 2);
    // outside the front patch's reach the back plane wins
    expect(pickNearest(idx, sx(-0.5), sx(0), { radiusPx: 8 })).toBeGreaterThanOrEqual(0);
    expect(pickNearest(idx, sx(-0.5), sx(0), { radiusPx: 8 })).toBeLessThan(front);
    // nothing within the radius
    expect(pickNearest(idx, sx(4), sx(4), { radiusPx: 8 })).toBe(-1);
  });
  it('respects the drawn subset and the keep filter, and is fast on 2 million points', () => {
    const n = 2_000_000;
    const pos = new Float32Array(n * 3);
    const r = rng(9);
    for (let i = 0; i < n; i++) { pos[i * 3] = (r.u() - 0.5) * 9; pos[i * 3 + 1] = (r.u() - 0.5) * 9; pos[i * 3 + 2] = -1 - r.u() * 5; }
    pos.set([0, 0, -0.5], 0);
    const t0 = performance.now();
    const idx = buildScreenIndex({ positions: pos, clip, view, width: W, height: H });
    const build = performance.now() - t0;
    const t1 = performance.now();
    for (let k = 0; k < 1000; k++) pickNearest(idx, 100 + (k % 300), 100 + ((k * 7) % 300));
    const q = (performance.now() - t1) / 1000;
    expect(pickNearest(idx, sx(0), sx(0))).toBe(0);
    expect(build).toBeLessThan(2000);
    expect(q).toBeLessThan(2);
    const sub = buildScreenIndex({ positions: pos, clip, view, width: W, height: H, indices: Uint32Array.from([5, 6, 7]) });
    expect(sub.items.length).toBeLessThanOrEqual(3);
    const kept = buildScreenIndex({ positions: pos.subarray(0, 300), clip, view, width: W, height: H, keep: (x) => x > 0 });
    for (const i of kept.items) expect(pos[i * 3]!).toBeGreaterThan(0);
  });
});
