// ICP and 3-point alignment on real data: the building model (public/models/building.glb, its merged BVH as the viewer
// builds it) and the phone LiDAR style sample public/samples/building-phone-scan.ply (tools/make_pointcloud.py
// --phone: one room, Y up, heading 37 degrees, 1.5 cm noise; the true transform is in the PLY header), and the
// synthetic survey scan public/samples/building-scan.ply (project coordinates, the truth is the identity).
// Also: oriented normals against the thin-wall bias and the wrong-face stall, and the drift diagnostic with a
// region-limited fit on a phone scan bent by a heading drift.

import { readFileSync } from 'node:fs';
import { Vector3 } from 'three';
import { describe, expect, it } from 'vitest';
import { parseModel } from '../src/model/loader';
import { driftNote, regionName } from '../src/pointcloud/controller';
import { mapPositions, projectToViewer } from '../src/pointcloud/align';
import { icp, voxelSample } from '../src/pointcloud/icp';
import type { ClosestFn } from '../src/pointcloud/icp';
import { estimateNormals } from '../src/pointcloud/normals';
import { bvhClosestFn } from '../src/pointcloud/surface';
import { parsePointCloud } from '../src/pointcloud/readers';
import { apply, compose, identity, mul, rotationY, solvePairs, transformError, translation } from '../src/pointcloud/register';
import type { Mat4 } from '../src/pointcloud/register';
import type { Vec3 } from '../src/pointcloud/types';

const file = (p: string): Uint8Array => readFileSync(new URL(p, import.meta.url).pathname);

async function setup(): Promise<{ closest: ClosestFn; filtered: ClosestFn; truth: Mat4; cloud: Float64Array; positions: Float32Array; origin: Vec3; shift: Vec3 }> {
  const glb = file('../public/models/building.glb');
  const side = JSON.parse(readFileSync(new URL('../public/models/building.json', import.meta.url).pathname, 'utf8')) as { originShift: Vec3 };
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
  return { closest, filtered: bvhClosestFn([bvh]), truth, cloud, positions: data.positions, origin: data.origin, shift: side.originShift };
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

/** Cloud frame sample (and its normals) of mapped positions + base; `viewpoint` as the controller passes it. */
function sampleWithNormals(mapped: Float32Array, base: Vec3, viewpoint: Vec3 | null): { pts: Float64Array; normals: Float32Array; oriented: Uint8Array } {
  const pick = voxelSample(mapped, 20_000);
  const pts = new Float64Array(pick.length * 3);
  pick.forEach((i, k) => pts.set([mapped[i * 3]! + base[0], mapped[i * 3 + 1]! + base[1], mapped[i * 3 + 2]! + base[2]], k * 3));
  const n = estimateNormals(pts, { dense: { positions: mapped, base }, viewpoint });
  return { pts, normals: n.normals, oriented: n.oriented };
}

describe('normal compatible ICP on the building model', () => {
  it('oriented normals remove the thin-wall bias of the phone scan', { timeout: 120_000 }, async () => {
    const s = await setup();
    const smp = sampleWithNormals(s.positions, s.origin, [0, 0, 0]); // the scan starts at its own origin
    let worstOld = 0, worstNew = 0;
    for (const [yaw, move] of [[0, [0, 0, 0]], [10, [0.21, 0.05, -0.2]], [-15, [-0.35, 0, 0.35]]] as Array<[number, Vec3]>) {
      const start = perturb(s.truth, yaw, move);
      const old = (await icp({ points: smp.pts, initial: start, closest: s.filtered, keepVertical: true, ...fast }))!;
      const now = (await icp({ points: smp.pts, normals: smp.normals, oriented: smp.oriented, initial: start, closest: s.filtered, keepVertical: true, ...fast }))!;
      const eo = errAt(s.truth, old.matrix), en = errAt(s.truth, now.matrix);
      worstOld = Math.max(worstOld, eo.translation);
      worstNew = Math.max(worstNew, en.translation);
      console.log(`phone scan, translation error without -> with normals: ${yaw} deg: ${(eo.translation * 1000).toFixed(2)} -> ${(en.translation * 1000).toFixed(2)} mm (${now.normalMode}, agreement ${now.agreement.toFixed(2)}, ${now.iterations} it)`);
      expect(now.normalMode).toBe('oriented');
      expect(en.rotationDeg).toBeLessThan(0.02);
    }

    expect(worstOld).toBeGreaterThan(0.0018);
    expect(worstNew).toBeLessThan(0.0012);
  });

  it('normals stop the wrong-face stall on the survey scan without the heading search', { timeout: 120_000 }, async () => {
    const s = await setup();
    const d = parsePointCloud(file('../public/samples/building-scan.ply'), 'building-scan.ply');
    const mapped = mapPositions(d.positions, 'project');
    const base = projectToViewer(d.origin, s.shift);
    const smp = sampleWithNormals(mapped, base, null);
    const at: Vec3 = [0, 0, 0];
    const start = mul(translation(0.2, 0.05, -0.2), rotationY((10 * Math.PI) / 180));
    const noSearch = { ...fast, yawSearchDeg: [0] };
    const old = (await icp({ points: smp.pts, initial: start, closest: s.filtered, keepVertical: true, ...noSearch }))!;
    const now = (await icp({ points: smp.pts, normals: smp.normals, oriented: smp.oriented, initial: start, closest: s.filtered, keepVertical: true, ...noSearch }))!;
    const eo = transformError(identity(), old.matrix, at), en = transformError(identity(), now.matrix, at);
    console.log(`survey scan from 10 deg without the heading search: ${eo.rotationDeg.toFixed(3)} deg / ${(eo.translation * 1000).toFixed(1)} mm without normals, ${en.rotationDeg.toFixed(4)} deg / ${(en.translation * 1000).toFixed(2)} mm with (${now.normalMode})`);
    expect(eo.translation).toBeGreaterThan(0.01);
    expect(en.translation).toBeLessThan(0.001);
    expect(en.rotationDeg).toBeLessThan(0.01);
  });

  it('a heading drift shows in the plan regions, and a region-limited fit repairs that part', { timeout: 180_000 }, async () => {
    const s = await setup();
    // bend the scan: the heading drifts by DRIFT deg per metre of horizontal distance from the start (its origin)
    const DRIFT = 1;
    const P = new Float32Array(s.positions.length);
    for (let i = 0; i < P.length; i += 3) {
      const x = s.positions[i]! + s.origin[0], y = s.positions[i + 1]! + s.origin[1], z = s.positions[i + 2]! + s.origin[2];
      const a = (DRIFT * Math.PI / 180) * Math.hypot(x, z);
      P[i] = Math.cos(a) * x + Math.sin(a) * z - s.origin[0];
      P[i + 1] = y - s.origin[1];
      P[i + 2] = -Math.sin(a) * x + Math.cos(a) * z - s.origin[2];
    }
    const smp = sampleWithNormals(P, s.origin, [0, 0, 0]);
    const whole = (await icp({ points: smp.pts, normals: smp.normals, oriented: smp.oriented, initial: s.truth, closest: s.filtered, keepVertical: true, ...fast }))!;
    const note = driftNote(whole.regions);
    const cells = whole.regions.map((r) => (r.count >= 40 ? (r.median * 1000).toFixed(1) : '-'));
    console.log(`drifted scan, whole-cloud fit: medians (mm, north row first) ${cells.join(' ')}; ${note || 'no note'}`);
    expect(note).not.toBe('');
    // the region of the worst cell (plus 25 cm), as align within limits it, fitted on its own
    const worst = whole.regions.filter((r) => r.count >= 40).reduce((a, b) => (b.misfit > a.misfit ? b : a));
    const lo = [worst.min[0] - 0.25, worst.min[1] - 0.25], hi = [worst.max[0] + 0.25, worst.max[1] + 0.25];
    const inBox = (m: Mat4, i: number): boolean => {
      const v = apply(m, [smp.pts[i * 3]!, smp.pts[i * 3 + 1]!, smp.pts[i * 3 + 2]!]);
      return v[0] >= lo[0]! && v[0] <= hi[0]! && v[2] >= lo[1]! && v[2] <= hi[1]!;
    };
    const keep = Array.from({ length: smp.pts.length / 3 }, (_, i) => i).filter((i) => inBox(whole.matrix, i));
    const sub = new Float64Array(keep.length * 3), subN = new Float32Array(keep.length * 3), subO = new Uint8Array(keep.length);
    keep.forEach((i, k) => {
      sub.set(smp.pts.subarray(i * 3, i * 3 + 3), k * 3);
      subN.set(smp.normals.subarray(i * 3, i * 3 + 3), k * 3);
      subO[k] = smp.oriented[i]!;
    });
    const local = (await icp({ points: sub, normals: subN, oriented: subO, initial: whole.matrix, closest: s.filtered, keepVertical: true, ...fast }))!;
    // median distance of the region's points to the model (what the deviation check shows; about 10 mm is the noise)
    const med = (m: Mat4): number => {
      const o = { p: [0, 0, 0], n: [0, 0, 0] };
      const d: number[] = [];
      for (let k = 0; k < keep.length; k++) {
        const v = apply(m, [sub[k * 3]!, sub[k * 3 + 1]!, sub[k * 3 + 2]!]);
        const r = s.closest(v[0], v[1], v[2], 0.3, o);
        if (Number.isFinite(r)) d.push(r);
      }
      d.sort((a, b) => a - b);
      return d[d.length >> 1]!;
    };
    const mw = med(whole.matrix), ml = med(local.matrix);
    console.log(`${regionName(worst)} region, ${keep.length} points: median distance ${(mw * 1000).toFixed(1)} mm with the whole-cloud fit, ${(ml * 1000).toFixed(1)} mm fitted on its own`);
    expect(local.ok).toBe(true);
    expect(ml).toBeLessThan(mw - 0.001);
  });
});
