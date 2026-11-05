// ICP and 3-point alignment on real data: the building model (public/models/building.glb, its merged BVH as the viewer
// builds it) and the phone LiDAR style sample public/samples/building-phone-scan.ply (tools/make_pointcloud.py
// --phone: one room, Y up, heading 37 degrees, 1.5 cm noise; the true transform is in the PLY header).

import { readFileSync } from 'node:fs';
import { Vector3 } from 'three';
import { describe, expect, it } from 'vitest';
import { parseModel } from '../src/model/loader';
import { icp, voxelSample } from '../src/pointcloud/icp';
import type { ClosestFn } from '../src/pointcloud/icp';
import { parsePointCloud } from '../src/pointcloud/readers';
import { apply, compose, mul, rotationY, solvePairs, transformError, translation } from '../src/pointcloud/register';
import type { Mat4 } from '../src/pointcloud/register';
import type { Vec3 } from '../src/pointcloud/types';

const file = (p: string): Uint8Array => readFileSync(new URL(p, import.meta.url).pathname);

async function setup(): Promise<{ closest: ClosestFn; truth: Mat4; cloud: Float64Array; positions: Float32Array; origin: Vec3 }> {
  const glb = file('../public/models/building.glb');
  const side = JSON.parse(readFileSync(new URL('../public/models/building.json', import.meta.url).pathname, 'utf8')) as unknown;
  const { geometry } = await parseModel(glb.buffer.slice(glb.byteOffset, glb.byteOffset + glb.byteLength) as ArrayBuffer, side);
  const bvh = geometry.bvh;
  const pos = bvh.geometry.getAttribute('position');
  const idx = bvh.geometry.getIndex()!;
  const p = new Vector3();
  const tgt = { point: new Vector3(), distance: 0, faceIndex: 0 };
  const closest: ClosestFn = (x, y, z, max, out) => {
    p.set(x, y, z);
    const r = bvh.closestPointToPoint(p, tgt, 0, max);
    if (!r) return Infinity;
    const f = r.faceIndex;
    const a = idx.getX(f * 3), b = idx.getX(f * 3 + 1), c = idx.getX(f * 3 + 2);
    const ux = pos.getX(b) - pos.getX(a), uy = pos.getY(b) - pos.getY(a), uz = pos.getZ(b) - pos.getZ(a);
    const vx = pos.getX(c) - pos.getX(a), vy = pos.getY(c) - pos.getY(a), vz = pos.getZ(c) - pos.getZ(a);
    const nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
    const l = Math.hypot(nx, ny, nz) || 1;
    out.p[0] = r.point.x; out.p[1] = r.point.y; out.p[2] = r.point.z;
    out.n[0] = nx / l; out.n[1] = ny / l; out.n[2] = nz / l;
    return r.distance;
  };
  const bytes = file('../public/samples/building-phone-scan.ply');
  const head = new TextDecoder().decode(bytes.subarray(0, 600));
  const m = /comment truth: viewer = Ry\(([-\d.]+) deg\) \* p \+ \(([-\d.]+), ([-\d.]+), ([-\d.]+)\)/.exec(head)!;
  const truth = mul(translation(+m[2]!, +m[3]!, +m[4]!), rotationY((+m[1]! * Math.PI) / 180));
  const data = parsePointCloud(bytes, 'building-phone-scan.ply');
  // the controller's cloud frame in viewer mode: c = origin + relative position
  const pick = voxelSample(data.positions, 20_000);
  const cloud = new Float64Array(pick.length * 3);
  pick.forEach((i, k) => cloud.set([data.positions[i * 3]! + data.origin[0], data.positions[i * 3 + 1]! + data.origin[1], data.positions[i * 3 + 2]! + data.origin[2]], k * 3));
  return { closest, truth, cloud, positions: data.positions, origin: data.origin };
}

const fast = { sliceMs: 1e9, yieldFn: () => Promise.resolve() };
const ROOM: Vec3 = [0, -1.5, -1]; // viewer frame, the scanned room
/** Error of `m` against the truth, measured at the room centre (cloud frame point that the truth puts there). */
const errAt = (truth: Mat4, m: Mat4): { rotationDeg: number; translation: number } => {
  const at = apply(compose([1, 0, 0, 0, 1, 0, 0, 0, 1], 1, [0, 0, 0]), ROOM);
  // cloud frame point that the truth maps to the room centre
  const inv = [truth[0]!, truth[4]!, truth[8]!, 0, truth[1]!, truth[5]!, truth[9]!, 0, truth[2]!, truth[6]!, truth[10]!, 0, 0, 0, 0, 1];
  const c = apply(inv, [at[0] - truth[12]!, at[1] - truth[13]!, at[2] - truth[14]!]);
  return transformError(truth, m, c);
};
/** Start error: rotate about the room centre (yaw, optional tilt about x) and move, on top of the truth. */
const perturb = (truth: Mat4, yawDeg: number, move: Vec3, tiltDeg = 0): Mat4 => {
  const t = (tiltDeg * Math.PI) / 180;
  const tilt: Mat4 = [1, 0, 0, 0, 0, Math.cos(t), Math.sin(t), 0, 0, -Math.sin(t), Math.cos(t), 0, 0, 0, 0, 1];
  const R = mul(rotationY((yawDeg * Math.PI) / 180), tilt);
  return mul(translation(ROOM[0] + move[0], ROOM[1] + move[1], ROOM[2] + move[2]), mul(R, mul(translation(-ROOM[0], -ROOM[1], -ROOM[2]), truth)));
};

describe('alignment on the building model with a phone scan', () => {
  it('ICP converges from rough starts (keep vertical and full 3D)', { timeout: 120_000 }, async () => {
    const s = await setup();
    const runs: Array<[number, Vec3, number, boolean]> = [
      [0, [0, 0, 0], 0, true],
      [10, [0.21, 0.05, -0.2], 0, true],
      [-15, [-0.35, 0, 0.35], 0, true],
      [10, [0.2, 0.1, 0.2], 1, false],
    ];
    for (const [yaw, move, tilt, keepVertical] of runs) {
      const start = perturb(s.truth, yaw, move, tilt);
      const r = (await icp({ points: s.cloud, initial: start, closest: s.closest, keepVertical, ...fast }))!;
      const e0 = errAt(s.truth, start), e = errAt(s.truth, r.matrix);
      const msg = `start ${e0.rotationDeg.toFixed(1)} deg / ${(e0.translation * 1000).toFixed(0)} mm -> ${e.rotationDeg.toFixed(4)} deg / ${(e.translation * 1000).toFixed(2)} mm, ${r.iterations} it, RMS ${(r.before.rms * 1000).toFixed(1)} -> ${(r.after.rms * 1000).toFixed(1)} mm (${keepVertical ? 'keep vertical' : 'full 3D'})`;
      console.log(msg);
      expect(r.ok, msg).toBe(true);
      expect(e.rotationDeg, msg).toBeLessThan(0.05);
      expect(e.translation, msg).toBeLessThan(0.006);
    }
  });
  it('3 picked pairs with 2 cm picking error give a start that ICP finishes', { timeout: 60_000 }, async () => {
    const s = await setup();
    const model: Vec3[] = [[-2.2, -2.55, -2.5], [-2.2, -2.55, 0.14], [1.6, -2.55, -2.5], [1.75, -1.65, 0.5]];
    const inv = (v: Vec3): Vec3 => {
      const d = [v[0] - s.truth[12]!, v[1] - s.truth[13]!, v[2] - s.truth[14]!];
      return [s.truth[0]! * d[0]! + s.truth[1]! * d[1]! + s.truth[2]! * d[2]!, s.truth[4]! * d[0]! + s.truth[5]! * d[1]! + s.truth[6]! * d[2]!, s.truth[8]! * d[0]! + s.truth[9]! * d[1]! + s.truth[10]! * d[2]!];
    };
    const jitter: Vec3[] = [[0.02, 0, -0.01], [-0.015, 0.01, 0.02], [0.01, -0.01, 0.015], [-0.02, 0.005, -0.01]];
    const cloud = model.map((v, i) => inv([v[0] + jitter[i]![0], v[1] + jitter[i]![1], v[2] + jitter[i]![2]]));
    const sol = solvePairs(cloud.slice(0, 3), model.slice(0, 3), { keepVertical: true, allowScale: false });
    const e3 = errAt(s.truth, sol.matrix);
    const r = (await icp({ points: s.cloud, initial: sol.matrix, closest: s.closest, keepVertical: true, ...fast }))!;
    const e = errAt(s.truth, r.matrix);
    console.log(`3-point ${e3.rotationDeg.toFixed(3)} deg / ${(e3.translation * 1000).toFixed(1)} mm -> ICP ${e.rotationDeg.toFixed(4)} deg / ${(e.translation * 1000).toFixed(2)} mm`);
    expect(e3.translation).toBeLessThan(0.04);
    expect(e.rotationDeg).toBeLessThan(0.05);
    expect(e.translation).toBeLessThan(0.006);
  });
});
