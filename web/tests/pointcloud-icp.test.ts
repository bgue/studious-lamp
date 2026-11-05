// Point-to-plane ICP on a synthetic room: convergence from a 10 degree / 0.3 m start (keep vertical and full 3D),
// trimming of clutter, the divergence guard, cancellation, and the spatially uniform voxel sample.

import { describe, expect, it } from 'vitest';
import { icp, rodrigues, solveLinear, voxelSample } from '../src/pointcloud/icp';
import type { ClosestFn } from '../src/pointcloud/icp';
import { apply, compose, invertSimilarity, mul, rotationY, transformError, translation } from '../src/pointcloud/register';
import type { Mat4 } from '../src/pointcloud/register';
import type { Vec3 } from '../src/pointcloud/types';

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

// The model: the inside of a 6 x 2.8 x 4.5 m room with a 0.6 x 0.9 x 1.2 m cupboard on the floor (both as box surfaces).
const ROOM = { min: [0, 0, 0] as Vec3, max: [6, 2.8, 4.5] as Vec3 };
const BOX = { min: [4.4, 0, 0.3] as Vec3, max: [5.0, 0.9, 1.5] as Vec3 };

/** Closest point on the surface of an axis aligned box, its outward normal and the distance. */
function boxSurface(b: { min: Vec3; max: Vec3 }, p: Vec3): { q: Vec3; n: Vec3; d: number } {
  const inside = p.every((v, k) => v >= b.min[k]! && v <= b.max[k]!);
  if (!inside) {
    const q = p.map((v, k) => Math.min(b.max[k]!, Math.max(b.min[k]!, v))) as Vec3;
    // normal of the face the clamp landed on (largest outside component)
    let ax = 0, best = -1;
    for (let k = 0; k < 3; k++) {
      const o = Math.max(b.min[k]! - p[k]!, p[k]! - b.max[k]!);
      if (o > best) { best = o; ax = k; }
    }
    const n: Vec3 = [0, 0, 0];
    n[ax] = p[ax]! > b.max[ax]! ? 1 : -1;
    return { q, n, d: Math.hypot(p[0] - q[0], p[1] - q[1], p[2] - q[2]) };
  }
  let ax = 0, side = 0, best = Infinity;
  for (let k = 0; k < 3; k++) {
    if (p[k]! - b.min[k]! < best) { best = p[k]! - b.min[k]!; ax = k; side = -1; }
    if (b.max[k]! - p[k]! < best) { best = b.max[k]! - p[k]!; ax = k; side = 1; }
  }
  const q: Vec3 = [p[0], p[1], p[2]];
  q[ax] = side < 0 ? b.min[ax]! : b.max[ax]!;
  const n: Vec3 = [0, 0, 0];
  n[ax] = side;
  return { q, n, d: best };
}

const roomClosest: ClosestFn = (x, y, z, max, out) => {
  const a = boxSurface(ROOM, [x, y, z]);
  const b = boxSurface(BOX, [x, y, z]);
  const h = b.d < a.d ? b : a;
  if (h.d > max) return Infinity;
  out.p[0] = h.q[0]; out.p[1] = h.q[1]; out.p[2] = h.q[2];
  out.n[0] = h.n[0]; out.n[1] = h.n[1]; out.n[2] = h.n[2];
  return h.d;
};

/** Scan of the room in model coordinates: floor, 3 of 4 walls, the cupboard, no ceiling (partial), with noise. */
function roomScan(seed: number, sigma: number, clutter = 0): Vec3[] {
  const r = rng(seed);
  const out: Vec3[] = [];
  const add = (p: Vec3): void => void out.push([p[0] + sigma * r.g(), p[1] + sigma * r.g(), p[2] + sigma * r.g()]);
  for (let i = 0; i < 1500; i++) add([r.u() * 6, 0, r.u() * 4.5]); // floor
  for (let i = 0; i < 900; i++) add([r.u() * 6, r.u() * 2.8, 0]); // back wall
  for (let i = 0; i < 700; i++) add([0, r.u() * 2.8, r.u() * 4.5]); // left wall
  for (let i = 0; i < 400; i++) add([6, r.u() * 2.0, 1.5 + r.u() * 3]); // part of the right wall
  for (let i = 0; i < 300; i++) add([4.4 + r.u() * 0.6, 0.9, 0.3 + r.u() * 1.2]); // cupboard top
  for (let i = 0; i < 300; i++) add([4.4, r.u() * 0.9, 0.3 + r.u() * 1.2]); // cupboard front
  for (let i = 0; i < clutter; i++) add([1 + r.u() * 3, 0.2 + r.u() * 1.5, 1 + r.u() * 2.5]); // furniture not in the model
  return out;
}

/** Cloud frame points: the scan moved by the inverse of `truth` (so truth maps the cloud back onto the model). */
function toCloud(scan: Vec3[], truth: Mat4): Float64Array {
  const inv = invertSimilarity(truth);
  const out = new Float64Array(scan.length * 3);
  scan.forEach((p, i) => out.set(apply(inv, p), i * 3));
  return out;
}

const fast = { sliceMs: 1e9, yieldFn: () => Promise.resolve() };
const centre: Vec3 = [3, 1.4, 2.25];

describe('point-to-plane ICP', () => {
  it('converges with keep vertical from a 10 degree / 0.3 m start to sub-millimetre and hundredths of a degree', async () => {
    // truth = the start error the ICP must undo: 10 degrees about the vertical through the room centre and 0.3 m
    const truth = mul(translation(centre[0] + 0.21, centre[1] + 0.05, centre[2] - 0.2), mul(rotationY((10 * Math.PI) / 180), translation(-centre[0], -centre[1], -centre[2])));
    const pts = toCloud(roomScan(1, 0.015), truth);
    const r = await icp({ points: pts, initial: compose([1, 0, 0, 0, 1, 0, 0, 0, 1], 1, [0, 0, 0]), closest: roomClosest, keepVertical: true, ...fast });
    expect(r).not.toBeNull();
    const e = transformError(truth, r!.matrix, centre);
    expect(r!.ok).toBe(true);
    expect(r!.converged).toBe(true);
    expect(r!.iterations).toBeLessThanOrEqual(30);
    expect(e.rotationDeg).toBeLessThan(0.03);
    expect(e.translation).toBeLessThan(0.002);
    expect(r!.after.rms).toBeLessThan(0.02);
    expect(r!.after.rms).toBeLessThan(r!.before.rms / 5);
    expect(r!.history.length).toBe(r!.iterations);
  });
  it('converges in full 3D with a small tilt in the start error', async () => {
    const rot = rodrigues(0.02, (10 * Math.PI) / 180, -0.015);
    const truth = mul(translation(centre[0] - 0.2, centre[1] + 0.1, centre[2] + 0.2), mul(rot, translation(-centre[0], -centre[1], -centre[2])));
    const pts = toCloud(roomScan(2, 0.015), truth);
    const r = await icp({ points: pts, initial: [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1], closest: roomClosest, keepVertical: false, ...fast });
    const e = transformError(truth, r!.matrix, centre);
    expect(r!.ok).toBe(true);
    expect(e.rotationDeg).toBeLessThan(0.05);
    expect(e.translation).toBeLessThan(0.003);
  });
  it('trims clutter: 20 percent furniture points that are not in the model barely move the result', async () => {
    const truth = mul(translation(0.3, 0, -0.1), mul(translation(centre[0], 0, centre[2]), mul(rotationY(0.12), translation(-centre[0], 0, -centre[2]))));
    const pts = toCloud(roomScan(3, 0.01, 1100), truth);
    const r = await icp({ points: pts, initial: [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1], closest: roomClosest, keepVertical: true, ...fast });
    const e = transformError(truth, r!.matrix, centre);
    expect(e.rotationDeg).toBeLessThan(0.05);
    expect(e.translation).toBeLessThan(0.003);
    // without the trim and the shrinking cut the clutter pulls the fit
    const loose = await icp({ points: pts, initial: [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1], closest: roomClosest, keepVertical: true, trim: 1, minDistance: 0.5, ...fast });
    const el = transformError(truth, loose!.matrix, centre);
    expect(el.translation + el.rotationDeg * 0.01).toBeGreaterThan(e.translation + e.rotationDeg * 0.01);
  });
  it('reverts when the fit gets worse and says so', async () => {
    // a surface that runs away: after the first pass every closest point is 0.3 m further off
    let calls = 0;
    const n = 400;
    const pts = new Float64Array(n * 3);
    for (let i = 0; i < n; i++) pts.set([i * 0.01, (i % 20) * 0.1, (i % 7) * 0.2], i * 3);
    const runaway: ClosestFn = (x, y, z, max, out) => {
      calls++;
      const off = calls <= 2 * n ? 0.01 : 0.3 + calls * 1e-5;
      if (off > max) return Infinity;
      out.p[0] = x; out.p[1] = y - off; out.p[2] = z;
      out.n[0] = 0; out.n[1] = 1; out.n[2] = 0;
      return off;
    };
    const start: Mat4 = translation(1, 2, 3);
    const r = await icp({ points: pts, initial: start, closest: runaway, keepVertical: true, startDistance: 0.5, maxIterations: 5, ...fast });
    expect(r!.reverted).toBe(true);
    expect(r!.ok).toBe(false);
    expect(r!.matrix).toEqual(start);
    expect(r!.reason).toMatch(/worse|kept the previous/);
  });
  it('refuses to start when the cloud is nowhere near the model', async () => {
    const pts = toCloud(roomScan(4, 0.01), translation(50, 0, 0));
    const r = await icp({ points: pts, initial: [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1], closest: roomClosest, keepVertical: true, ...fast });
    expect(r!.ok).toBe(false);
    expect(r!.iterations).toBe(0);
    expect(r!.reason).toMatch(/align roughly first/);
  });
  it('yields between time slices and can be cancelled', async () => {
    const pts = toCloud(roomScan(5, 0.01), translation(0.1, 0, 0));
    let yields = 0;
    const r = await icp({
      points: pts, initial: [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1], closest: roomClosest, keepVertical: true, sliceMs: 0,
      yieldFn: () => { yields++; return Promise.resolve(); }, isCancelled: () => yields > 3,
    });
    expect(r).toBeNull();
    expect(yields).toBe(4);
  });
});

describe('helpers', () => {
  it('solves a linear system and builds rotations', () => {
    const x = solveLinear([4, 1, 0, 1, 3, 1, 0, 1, 2], [1, 2, 3], 3)!;
    expect(4 * x[0]! + x[1]!).toBeCloseTo(1, 12);
    expect(x[0]! + 3 * x[1]! + x[2]!).toBeCloseTo(2, 12);
    expect(solveLinear([1, 2, 2, 4], [1, 2], 2)).toBeNull();
    const ry = rodrigues(0, 0.4, 0);
    rotationY(0.4).forEach((v, i) => expect(ry[i]).toBeCloseTo(v, 12));
  });
  it('voxel sample: about the target count, spread evenly, deterministic', () => {
    // a dense strip (half the points in 10 percent of the area) plus a sparse plane
    const r = rng(7);
    const n = 200_000;
    const pos = new Float32Array(n * 3);
    for (let i = 0; i < n; i++) {
      const dense = i % 2 === 0;
      pos[i * 3] = dense ? r.u() * 1 : r.u() * 10;
      pos[i * 3 + 1] = 0;
      pos[i * 3 + 2] = r.u() * 10;
    }
    const s = voxelSample(pos, 5000);
    expect(s.length).toBeGreaterThan(3500);
    expect(s.length).toBeLessThanOrEqual(5000);
    let inStrip = 0;
    for (const i of s) if (pos[i * 3]! < 1) inStrip++;
    // a random sample would put about 55 percent in the strip; an even one about 10 percent
    expect(inStrip / s.length).toBeLessThan(0.2);
    expect(Array.from(voxelSample(pos, 5000))).toEqual(Array.from(s));
    expect(voxelSample(pos.subarray(0, 300), 5000).length).toBe(100);
  });
  it('voxel sample keeps the noise of a surface symmetric (no offset from where the grid cells fall)', () => {
    // a 10 x 10 m floor with 1.5 cm noise and a few points above it (so the grid starts at different heights)
    for (const lift of [0, 0.004, 0.011, 0.023]) {
      const r = rng(11);
      const n = 150_000;
      const pos = new Float32Array(n * 3);
      for (let i = 0; i < n; i++) pos.set([r.u() * 10, 0.015 * r.g(), r.u() * 10], i * 3);
      pos[1] = -0.06 - lift; // the lowest point decides where the cells start
      const s = voxelSample(pos, 8000);
      let mean = 0;
      for (const i of s) mean += pos[i * 3 + 1]! / s.length;
      expect(Math.abs(mean), `lift ${lift}`).toBeLessThan(0.0015);
    }
  });
});
