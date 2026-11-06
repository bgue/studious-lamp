// Point normals for ICP (src/pointcloud/normals.ts) and normal compatible correspondences (icp.ts): PCA normals on a
// noisy plane, orientation towards a viewpoint and by occlusion, the thin-wall bias with and without normals, the
// orientation convention check (a model whose faces point inwards), the drift diagnostic and screen picking behind
// an opaque surface (src/pointcloud/pick.ts maxDepth).

import { describe, expect, it } from 'vitest';
import { driftNote, regionName } from '../src/pointcloud/controller';
import { icp } from '../src/pointcloud/icp';
import type { ClosestFn, RegionResidual } from '../src/pointcloud/icp';
import { estimateNormals, smallestEigen } from '../src/pointcloud/normals';
import { buildScreenIndex, pickNearest } from '../src/pointcloud/pick';
import { identity } from '../src/pointcloud/register';
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

/** An axis aligned rectangle of the model: `axis` 0/1/2 is its normal axis at `at`, `sign` the facing, the rest its extent. */
interface Rect { axis: 0 | 1 | 2; at: number; sign: 1 | -1; min: Vec3; max: Vec3 }

/** Closest point on a set of rectangles, honouring the normal filter like src/pointcloud/surface.ts does. */
function rectClosest(rects: Rect[], honour = true): ClosestFn {
  return (x, y, z, max, out, filter) => {
    let best = max;
    let hit = false;
    for (const r of rects) {
      const n: Vec3 = [0, 0, 0];
      n[r.axis] = r.sign;
      if (filter && honour) {
        const dot = n[0] * filter.n[0]! + n[1] * filter.n[1]! + n[2] * filter.n[2]!;
        if (filter.oriented ? dot < filter.cos : Math.abs(dot) < filter.cos) continue;
      }
      const q: Vec3 = [x, y, z].map((v, k) => (k === r.axis ? r.at : Math.min(r.max[k]!, Math.max(r.min[k]!, v)))) as Vec3;
      const d = Math.hypot(q[0] - x, q[1] - y, q[2] - z);
      if (d <= best) {
        best = d;
        hit = true;
        out.p[0] = q[0]; out.p[1] = q[1]; out.p[2] = q[2];
        out.n[0] = n[0]; out.n[1] = n[1]; out.n[2] = n[2];
      }
    }
    return hit ? best : Infinity;
  };
}

// A room corner with a thin wall: floor (y = 0, up), back wall (z = 0, facing +z), side wall (x = 0, facing +x) and a
// 2.4 cm thin wall at x = 3 (face A at 3.000 facing -x, towards the room; face B at 3.024 facing +x, away from it).
const RECTS: Rect[] = [
  { axis: 1, at: 0, sign: 1, min: [0, 0, 0], max: [3, 0, 4] },
  { axis: 2, at: 0, sign: 1, min: [0, 0, 0], max: [3, 2.5, 0] },
  { axis: 0, at: 0, sign: 1, min: [0, 0, 0], max: [0, 2.5, 4] },
  { axis: 0, at: 3, sign: -1, min: [3, 0, 0], max: [3, 2.5, 4] },
  { axis: 0, at: 3.024, sign: 1, min: [3.024, 0, 0], max: [3.024, 2.5, 4] },
];
const VIEW: Vec3 = [1.5, 1.3, 2];

/** What a scanner at VIEW sees of the room: every face but B, 1.5 cm noise, about 1 point per 1.5 cm. */
function scan(seed: number, sigma = 0.015): Float64Array {
  const r = rng(seed);
  const out: number[] = [];
  const add = (x: number, y: number, z: number): void => void out.push(x + sigma * r.g(), y + sigma * r.g(), z + sigma * r.g());
  for (let i = 0; i < 6000; i++) add(r.u() * 3, 0, r.u() * 4);
  for (let i = 0; i < 4000; i++) add(r.u() * 3, r.u() * 2.5, 0);
  for (let i = 0; i < 5000; i++) add(0, r.u() * 2.5, r.u() * 4);
  for (let i = 0; i < 5000; i++) add(3, r.u() * 2.5, r.u() * 4);
  return Float64Array.from(out);
}

const fast = { sliceMs: 1e9, yieldFn: () => Promise.resolve(), yawSearchDeg: [0] };

describe('normals', () => {
  it('smallestEigen gives the normal of a flat covariance', () => {
    const e = smallestEigen(4, 0, 0, 0.01, 0, 9);
    expect(Math.abs(e.n[1])).toBeCloseTo(1, 6);
    expect(e.l0).toBeCloseTo(0.01, 6);
    const t = smallestEigen(1, 0.5, 0, 1, 0, 2); // eigenvalues 0.5, 1.5, 2: vector (1, -1, 0) / sqrt 2
    expect(Math.abs(t.n[0] + t.n[1])).toBeLessThan(1e-9);
    expect(t.l0).toBeCloseTo(0.5, 9);
  });

  it('estimates plane normals, orients them towards the viewpoint and by occlusion', { timeout: 30_000 }, () => {
    const pts = scan(1);
    const n = estimateNormals(pts, { viewpoint: VIEW });
    expect(n.valid / (pts.length / 3)).toBeGreaterThan(0.8);
    let good = 0, oriented = 0, axisOk = 0, valid = 0;
    for (let i = 0; i < pts.length / 3; i++) {
      const v: Vec3 = [n.normals[i * 3]!, n.normals[i * 3 + 1]!, n.normals[i * 3 + 2]!];
      if (!v[0] && !v[1] && !v[2]) continue;
      valid++;
      // the true normal from the face the point was drawn from (index ranges of scan())
      const t: Vec3 = i < 6000 ? [0, 1, 0] : i < 10000 ? [0, 0, 1] : i < 15000 ? [1, 0, 0] : [-1, 0, 0];
      const dot = v[0] * t[0] + v[1] * t[1] + v[2] * t[2];
      if (Math.abs(dot) > Math.cos((15 * Math.PI) / 180)) axisOk++;
      if (n.oriented[i]) {
        oriented++;
        if (dot > 0) good++;
      }
    }
    expect(axisOk / valid).toBeGreaterThan(0.95);
    expect(oriented / valid).toBeGreaterThan(0.9);
    expect(good / oriented).toBeGreaterThan(0.99);
    expect(n.noise).toBeGreaterThan(0.005);
    expect(n.noise).toBeLessThan(0.02);
  });

  it('orients both faces of a thick slab outwards by occlusion, without a viewpoint', { timeout: 30_000 }, () => {
    // a 20 cm slab scanned on both faces (an outer wall scanned from inside and outside): no viewpoint helps
    const r = rng(5);
    const out: number[] = [];
    for (let i = 0; i < 8000; i++) {
      const top = i % 2 === 0;
      out.push(r.u() * 3 + 0.003 * r.g(), (top ? 0.2 : 0) + 0.003 * r.g(), r.u() * 3 + 0.003 * r.g());
    }
    const pts = Float64Array.from(out);
    const n = estimateNormals(pts);
    let good = 0, bad = 0;
    for (let i = 0; i < 8000; i++) {
      if (!n.oriented[i]) continue;
      const up = n.normals[i * 3 + 1]! > 0;
      if (up === (i % 2 === 0)) good++;
      else bad++;
    }
    expect(n.byOcclusion).toBeGreaterThan(5000);
    expect(bad).toBeLessThan(0.01 * good);
  });
});

describe('ICP with normal compatible pairs', () => {
  const thinWallBias = async (normals: boolean, honour = true, rects = RECTS): Promise<{ x: number; mode: string; agreement: number }> => {
    const pts = scan(2);
    const n = normals ? estimateNormals(pts, { viewpoint: VIEW }) : null;
    const r = (await icp({ points: pts, normals: n?.normals, oriented: n?.oriented, initial: identity(), closest: rectClosest(rects, honour), keepVertical: true, ...fast }))!;
    // sideways displacement of the thin wall (the point in the middle of face A)
    const m = r.matrix;
    return { x: m[0]! * 3 + m[4]! * 1.25 + m[8]! * 2 + m[12]! - 3, mode: r.normalMode, agreement: r.agreement };
  };

  it('removes the sideways pull of a thin wall whose far face lies within the noise', { timeout: 60_000 }, async () => {
    const before = await thinWallBias(false);
    const after = await thinWallBias(true);
    const ideal = await thinWallBias(false, true, RECTS.slice(0, 4)); // the same scan without the far face in the model
    console.log(`thin wall: moved ${(before.x * 1000).toFixed(2)} mm sideways without normals, ${(after.x * 1000).toFixed(2)} mm with (${after.mode}, agreement ${after.agreement.toFixed(2)}); ${(ideal.x * 1000).toFixed(2)} mm without the far face`);
    expect(Math.abs(before.x)).toBeGreaterThan(0.0015);
    expect(after.mode).toBe('oriented');
    expect(Math.abs(after.x)).toBeLessThan(0.0005);
  });

  it('still works with a closest point query that ignores the filter (incompatible pairs are dropped)', { timeout: 60_000 }, async () => {
    // dropping the pairs on the far face truncates the noise on one side: less bias than none, more than a filtered query
    const r = await thinWallBias(true, false);
    const before = await thinWallBias(false);
    expect(r.mode).toBe('oriented');
    expect(Math.abs(r.x)).toBeLessThan(0.8 * Math.abs(before.x));
  });

  it('detects a model whose faces point inwards and flips the convention', { timeout: 60_000 }, async () => {
    const inward = RECTS.map((q) => ({ ...q, sign: -q.sign as 1 | -1 }));
    const r = await thinWallBias(true, true, inward);
    expect(r.mode).toBe('oriented');
    expect(r.agreement).toBeLessThan(0.2);
    expect(Math.abs(r.x)).toBeLessThan(0.0005);
  });

  it('reports the residual per plan region', { timeout: 60_000 }, async () => {
    const pts = scan(3);
    const n = estimateNormals(pts, { viewpoint: VIEW });
    const r = (await icp({ points: pts, normals: n.normals, oriented: n.oriented, initial: identity(), closest: rectClosest(RECTS), keepVertical: true, ...fast }))!;
    expect(r.regions.length).toBe(9);
    expect(r.regions.reduce((a, c) => a + c.count, 0)).toBe(r.after.count);
    for (const c of r.regions) if (c.count > 50) {
      expect(c.median).toBeLessThan(0.02);
      expect(c.misfit).toBeLessThan(0.004);
    }
    expect(driftNote(r.regions)).toBe('');
  });
});

describe('drift diagnostic', () => {
  const cell = (ix: number, iz: number, misfit: number, count = 100): RegionResidual => ({ ix, iz, min: [0, 0], max: [1, 1], count, rms: 0.013, median: 0.01, bias: 0, shift: [misfit, 0, 0], misfit });
  it('names the region where the fit degrades', () => {
    const regs = [cell(0, 0, 0.001), cell(1, 0, 0.002), cell(2, 0, 0.012), cell(0, 1, 0.001), cell(1, 1, 0.0005), cell(2, 1, 0.006), cell(0, 2, 0.002), cell(1, 2, 0.001), cell(2, 2, 0.03, 10)];
    const note = driftNote(regs);
    expect(note).toContain('north-east');
    expect(regionName({ ix: 0, iz: 2 })).toBe('south-west');
  });
  it('stays quiet on an even fit and on thin cells', () => {
    expect(driftNote([cell(0, 0, 0.001), cell(1, 0, 0.002), cell(2, 0, 0.0035)])).toBe(''); // under 4 mm
    expect(driftNote([cell(0, 0, 0.004), cell(1, 0, 0.005), cell(2, 0, 0.008)])).toBe(''); // under 2.5 x typical
    expect(driftNote([cell(0, 0, 0.001), cell(1, 0, 0.001), cell(2, 0, 0.05, 5)])).toBe(''); // too few points
  });
});

describe('picking behind an opaque surface', () => {
  it('skips cloud points deeper than the model surface under the cursor', () => {
    // camera at the origin looking down -z: a near point at 2 m and a far one at 6 m on the same pixel ray, and a
    // far point a few pixels aside
    const f = 1 / Math.tan(Math.PI / 6), near = 0.1, far = 100;
    const proj = [f, 0, 0, 0, 0, f, 0, 0, 0, 0, -(far + near) / (far - near), -1, 0, 0, (-2 * far * near) / (far - near), 0];
    const pos = new Float32Array([0, 0, -6, 0.01, 0, -2, 0.06, 0, -6]);
    const idx = buildScreenIndex({ positions: pos, clip: proj, view: identity(), width: 400, height: 400 });
    expect(pickNearest(idx, 200, 200)).toBe(1); // frontmost wins
    expect(pickNearest(idx, 200, 200, { maxDepth: 4 })).toBe(1); // in front of a wall at 4 m: still pickable
    expect(pickNearest(idx, 200, 200, { maxDepth: 1.5 })).toBe(-1); // a wall at 1.5 m hides all of them
    const p2 = new Float32Array([0, 0, -6, 0.06, 0, -6]);
    const idx2 = buildScreenIndex({ positions: p2, clip: proj, view: identity(), width: 400, height: 400 });
    expect(pickNearest(idx2, 200, 200)).toBe(0);
    expect(pickNearest(idx2, 200, 200, { maxDepth: 5 })).toBe(-1); // behind the wall at 5 m
    expect(pickNearest(idx2, 200, 200, { maxDepth: 5.98 })).toBe(0); // within the depth band of the surface: a point on it
  });
});
