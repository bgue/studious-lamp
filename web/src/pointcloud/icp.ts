// Fine registration of a point cloud to the model surface: trimmed point-to-plane ICP. Pure, testable; the closest
// point query is injected (the viewer uses the merged geometry's BVH, see controller.ts).
//
// Per iteration:
//   1. transform the sample with the current matrix
//   2. closest model surface point q and its normal n for each sample point p, up to a maximum distance
//   3. trim: drop pairs beyond the maximum distance, then keep the best `trim` share (default 85 percent)
//   4. linearised point-to-plane least squares about the inlier centroid: minimise sum (n . (p + w x p + t - q))^2,
//      6 unknowns (w, t); with keepVertical 4 (yaw, t). Small damping keeps a flat scene (1 plane) solvable.
//   5. apply the exact rotation of w (Rodrigues) and t on the left of the matrix
//   6. the maximum distance shrinks to 3 x the inlier RMS, by at most 15 percent per iteration (not below minDist)
// Before that, a heading search: short runs on a 2500 point subsample from the start turned by 0, +-5, +-10, +-15
// degrees about the vertical; the one with the most points within 4 cm becomes the start (see the note in icp()).
// It stops when the step is below 0.1 mm and 0.01 degrees, or after maxIterations. Divergence guard: the start and
// the end are scored with the same maximum distance and trim; when the end is worse (RMS up, or the inlier share
// halved) the start matrix is returned with reverted = true.
//
// Work runs in time slices (default 8 ms) with a yield between them, so the page stays responsive; cancellable.

import { apply, identity, mul, rotationY, translation } from './register';
import type { Mat4 } from './register';

/** Closest surface point within maxDist: writes point and unit normal into `out`, returns the distance or Infinity. */
export type ClosestFn = (x: number, y: number, z: number, maxDist: number, out: { p: number[]; n: number[] }) => number;

export interface IcpRun {
  /** Sample in the cloud's own frame (what `initial` maps to the viewer frame), 3 doubles per point. */
  points: Float64Array;
  initial: Mat4;
  closest: ClosestFn;
  keepVertical: boolean;
  maxIterations?: number;
  /** Share of the pairs within the maximum distance that is kept, 0..1. */
  trim?: number;
  /** First maximum distance, metres. Default: max(0.5, 3 x the RMS of the start within 2 m). */
  startDistance?: number;
  /** Lower bound of the shrinking maximum distance, metres. */
  minDistance?: number;
  /** Stop when the step moves less than this, metres. */
  stopTranslation?: number;
  /** Stop when the step turns less than this, degrees. */
  stopRotationDeg?: number;
  /**
   * Heading offsets (degrees about the vertical) tried as starts before the full run, each refined by a short run on a
   * subsample. Default [0, 5, -5, 10, -10, 15, -15]; [0] or [] skips the search.
   */
  yawSearchDeg?: number[];
  sliceMs?: number;
  onProgress?(iteration: number, rms: number): void;
  /** Heading search progress: start k of n. */
  onSearch?(k: number, n: number): void;
  isCancelled?(): boolean;
  yieldFn?(): Promise<void>;
}

export interface IcpScore {
  rms: number;
  /** Inliers (after the distance cut and the trim) / sample size. */
  inlierFraction: number;
  /** Within the maximum distance, before the trim / sample size. */
  withinFraction: number;
  count: number;
}

export interface IcpResult {
  matrix: Mat4;
  /** False when reverted or nothing to work with. */
  ok: boolean;
  reverted: boolean;
  reason: string;
  iterations: number;
  converged: boolean;
  before: IcpScore;
  after: IcpScore;
  /** Maximum distance used to score before and after, metres. */
  scoreDistance: number;
  /** RMS of the inliers per iteration. */
  history: number[];
  /** Heading offset of the start that the search kept, degrees (0: the given start). */
  searchYawDeg: number;
}

const defaultYield = (): Promise<void> => new Promise((r) => setTimeout(r, 0));

interface Pairs {
  p: Float64Array;
  q: Float64Array;
  n: Float64Array;
  d: Float64Array;
  count: number;
  within: number;
}

/** Solve A x = b (n x n, row-major) by Gaussian elimination with partial pivoting. null when singular. */
export function solveLinear(A: number[], b: number[], n: number): number[] | null {
  const M = A.slice();
  const x = b.slice();
  for (let c = 0; c < n; c++) {
    let piv = c;
    for (let r = c + 1; r < n; r++) if (Math.abs(M[r * n + c]!) > Math.abs(M[piv * n + c]!)) piv = r;
    if (Math.abs(M[piv * n + c]!) < 1e-300) return null;
    if (piv !== c) {
      for (let k = 0; k < n; k++) [M[c * n + k], M[piv * n + k]] = [M[piv * n + k]!, M[c * n + k]!];
      [x[c], x[piv]] = [x[piv]!, x[c]!];
    }
    for (let r = c + 1; r < n; r++) {
      const f = M[r * n + c]! / M[c * n + c]!;
      if (!f) continue;
      for (let k = c; k < n; k++) M[r * n + k]! -= f * M[c * n + k]!;
      x[r]! -= f * x[c]!;
    }
  }
  for (let r = n - 1; r >= 0; r--) {
    let s = x[r]!;
    for (let k = r + 1; k < n; k++) s -= M[r * n + k]! * x[k]!;
    x[r] = s / M[r * n + r]!;
  }
  return x.every(Number.isFinite) ? x : null;
}

/** Rotation by the vector w (axis * angle, radians), column-major 4x4. */
export function rodrigues(wx: number, wy: number, wz: number): Mat4 {
  const th = Math.hypot(wx, wy, wz);
  if (th < 1e-15) return identity();
  const x = wx / th, y = wy / th, z = wz / th;
  const c = Math.cos(th), s = Math.sin(th), C = 1 - c;
  // row-major R, then to column-major
  const R = [
    c + x * x * C, x * y * C - z * s, x * z * C + y * s,
    y * x * C + z * s, c + y * y * C, y * z * C - x * s,
    z * x * C - y * s, z * y * C + x * s, c + z * z * C,
  ];
  return [R[0]!, R[3]!, R[6]!, 0, R[1]!, R[4]!, R[7]!, 0, R[2]!, R[5]!, R[8]!, 0, 0, 0, 0, 1];
}

/** Trimmed RMS of a distance list: keep those <= maxDist, then the best `trim` share. */
function trimmed(d: Float64Array, count: number, trim: number): { keep: number; cut: number; rms: number } {
  if (!count) return { keep: 0, cut: Infinity, rms: NaN };
  const s = d.slice(0, count).sort();
  const keep = Math.max(1, Math.floor(count * trim));
  let sum = 0;
  for (let i = 0; i < keep; i++) sum += s[i]! * s[i]!;
  return { keep, cut: s[keep - 1]!, rms: Math.sqrt(sum / keep) };
}

/**
 * Trimmed point-to-plane ICP. Resolves with the refined matrix, or null when cancelled.
 */
export async function icp(run: IcpRun): Promise<IcpResult | null> {
  const pts = run.points;
  const N = Math.floor(pts.length / 3);
  const trim = run.trim ?? 0.85;
  const maxIt = run.maxIterations ?? 30;
  const minDist = run.minDistance ?? 0.02;
  const stopT = run.stopTranslation ?? 1e-4;
  const stopR = ((run.stopRotationDeg ?? 0.01) * Math.PI) / 180;
  const sliceMs = run.sliceMs ?? 8;
  const yieldFn = run.yieldFn ?? defaultYield;
  const dof = run.keepVertical ? 4 : 6;
  const buf: Pairs = { p: new Float64Array(N * 3), q: new Float64Array(N * 3), n: new Float64Array(N * 3), d: new Float64Array(N), count: 0, within: 0 };
  const out = { p: [0, 0, 0], n: [0, 1, 0] };
  let sliceStart = performance.now();
  let slice = sliceMs;
  let cancelled = false;

  /** Correspondences of the points P under matrix m within maxDist (time sliced). */
  const gather = async (P: Float64Array, m: Mat4, maxDist: number): Promise<boolean> => {
    const n = Math.floor(P.length / 3);
    let k = 0;
    for (let i = 0; i < n; i++) {
      const p = apply(m, [P[i * 3]!, P[i * 3 + 1]!, P[i * 3 + 2]!]);
      const d = run.closest(p[0], p[1], p[2], maxDist, out);
      if (d <= maxDist && Number.isFinite(d)) {
        buf.p[k * 3] = p[0]; buf.p[k * 3 + 1] = p[1]; buf.p[k * 3 + 2] = p[2];
        buf.q[k * 3] = out.p[0]!; buf.q[k * 3 + 1] = out.p[1]!; buf.q[k * 3 + 2] = out.p[2]!;
        buf.n[k * 3] = out.n[0]!; buf.n[k * 3 + 1] = out.n[1]!; buf.n[k * 3 + 2] = out.n[2]!;
        buf.d[k] = d;
        k++;
      }
      if ((i & 63) === 63 && performance.now() - sliceStart > slice) {
        const end = performance.now();
        await yieldFn();
        sliceStart = performance.now();
        // adaptive slice, as in deviation.ts: when the gap was long (a heavy frame was drawn in between), take a
        // longer slice so the work still makes progress; on a fast machine the gap is ~0 and slices stay short
        slice = Math.min(250, Math.max(sliceMs, (sliceStart - end) * 0.5));
        if (run.isCancelled?.()) {
          cancelled = true;
          return false;
        }
      }
    }
    buf.count = k;
    buf.within = k;
    return true;
  };

  const score = async (m: Mat4, maxDist: number): Promise<IcpScore | null> => {
    if (!(await gather(pts, m, maxDist))) return null;
    const t = trimmed(buf.d, buf.count, trim);
    return { rms: t.rms, inlierFraction: N ? t.keep / N : 0, withinFraction: N ? buf.count / N : 0, count: t.keep };
  };

  /** One linearised point-to-plane step on the pairs in `buf`. */
  const solveStep = (m: Mat4): { m: Mat4; rms: number; w: number; t: number } | string => {
    const t = trimmed(buf.d, buf.count, trim);
    // inliers: d <= cut (the trim)
    let cx = 0, cy = 0, cz = 0, k = 0;
    for (let i = 0; i < buf.count; i++) {
      if (buf.d[i]! > t.cut) continue;
      cx += buf.p[i * 3]!; cy += buf.p[i * 3 + 1]!; cz += buf.p[i * 3 + 2]!;
      k++;
    }
    cx /= k; cy /= k; cz /= k;
    const A = new Array<number>(dof * dof).fill(0);
    const b = new Array<number>(dof).fill(0);
    const J = new Array<number>(dof);
    for (let i = 0; i < buf.count; i++) {
      if (buf.d[i]! > t.cut) continue;
      const px = buf.p[i * 3]! - cx, py = buf.p[i * 3 + 1]! - cy, pz = buf.p[i * 3 + 2]! - cz;
      const nx = buf.n[i * 3]!, ny = buf.n[i * 3 + 1]!, nz = buf.n[i * 3 + 2]!;
      const e = nx * (buf.p[i * 3]! - buf.q[i * 3]!) + ny * (buf.p[i * 3 + 1]! - buf.q[i * 3 + 1]!) + nz * (buf.p[i * 3 + 2]! - buf.q[i * 3 + 2]!);
      // p x n
      const ax = py * nz - pz * ny, ay = pz * nx - px * nz, az = px * ny - py * nx;
      if (run.keepVertical) {
        J[0] = ay; J[1] = nx; J[2] = ny; J[3] = nz;
      } else {
        J[0] = ax; J[1] = ay; J[2] = az; J[3] = nx; J[4] = ny; J[5] = nz;
      }
      for (let r = 0; r < dof; r++) {
        b[r]! -= J[r]! * e;
        for (let c = r; c < dof; c++) A[r * dof + c]! += J[r]! * J[c]!;
      }
    }
    let tr = 0;
    for (let r = 0; r < dof; r++) {
      for (let c = 0; c < r; c++) A[r * dof + c] = A[c * dof + r]!;
      tr += A[r * dof + r]!;
    }
    const damp = (1e-6 * tr) / dof;
    for (let r = 0; r < dof; r++) A[r * dof + r]! += damp;
    const x = solveLinear(A, b, dof);
    if (!x) return 'singular system';
    const [wx, wy, wz, tx, ty, tz] = run.keepVertical ? [0, x[0]!, 0, x[1]!, x[2]!, x[3]!] : (x as [number, number, number, number, number, number]);
    const step = mul(translation(cx + tx, cy + ty, cz + tz), mul(rodrigues(wx, wy, wz), translation(-cx, -cy, -cz)));
    return { m: mul(step, m), rms: t.rms, w: Math.hypot(wx, wy, wz), t: Math.hypot(tx, ty, tz) };
  };

  /**
   * Iterate on the points P from m with the first maximum distance d0. The maximum distance then shrinks to 3 x the
   * inlier RMS, but by at most 15 percent per iteration (a quick shrink locks in a local minimum when large flat
   * areas, such as a floor, fit at once and pull the RMS down while the walls still disagree).
   */
  const loop = async (P: Float64Array, m0: Mat4, d0: number, iterations: number, report: boolean) => {
    let m = m0;
    let dist = d0;
    const history: number[] = [];
    let it = 0;
    let converged = false;
    let fail = '';
    for (; it < iterations; it++) {
      if (!(await gather(P, m, dist))) break;
      if (buf.count < dof * 3) {
        fail = `too few pairs within ${(dist * 100).toFixed(1)} cm`;
        break;
      }
      const r = solveStep(m);
      if (typeof r === 'string') {
        fail = r;
        break;
      }
      history.push(r.rms);
      if (report) run.onProgress?.(it + 1, r.rms);
      m = r.m;
      dist = Math.max(minDist, Math.min(dist, Math.max(3 * r.rms, dist * 0.85)));
      if (r.t < stopT && r.w < stopR) {
        it++;
        converged = true;
        break;
      }
    }
    return { m, it, converged, fail, history, dist };
  };

  // start distance: given, or from the RMS of the start within 2 m
  let dist = run.startDistance ?? 0;
  if (!dist) {
    const probe = await score(run.initial, 2);
    if (!probe) return null;
    dist = Math.max(0.5, Number.isFinite(probe.rms) ? 3 * probe.rms : 0.5);
  }
  const scoreDistance = dist;
  const before = await score(run.initial, scoreDistance);
  if (!before) return null;
  const empty: IcpScore = { rms: NaN, inlierFraction: 0, withinFraction: 0, count: 0 };
  if (before.count < dof * 3) {
    return {
      matrix: run.initial.slice(), ok: false, reverted: false, iterations: 0, converged: false, before, after: before, scoreDistance, history: [], searchYawDeg: 0,
      reason: `Only ${before.count} sample points lie within ${(scoreDistance * 100).toFixed(0)} cm of the model: align roughly first (Auto-align or Align by 3 points).`,
    };
  }

  // heading search: short runs on a subsample from the start turned by a few angles about the vertical through the
  // sample centre; the best (most points within 4 cm) is where the full run starts. Two-sided walls are the reason:
  // turned 10 degrees, the half of a wall that moved behind its inner face matches the outer face and cancels the
  // turn, so a single run from there stops in a local minimum.
  let start = run.initial.slice();
  let startDist = dist;
  let searchYawDeg = 0;
  const offsets = run.yawSearchDeg ?? [0, 5, -5, 10, -10, 15, -15];
  if (offsets.length > 1 && N >= 200) {
    const every = Math.max(1, Math.floor(N / 2500));
    const sub = new Float64Array(Math.floor(N / every) * 3);
    for (let k = 0; k < sub.length / 3; k++) sub.set(pts.subarray(k * every * 3, k * every * 3 + 3), k * 3);
    let cx = 0, cy = 0, cz = 0;
    const ns = sub.length / 3;
    for (let k = 0; k < ns; k++) {
      const p = apply(run.initial, [sub[k * 3]!, sub[k * 3 + 1]!, sub[k * 3 + 2]!]);
      cx += p[0] / ns; cy += p[1] / ns; cz += p[2] / ns;
    }
    let bestScore = -1;
    for (let k = 0; k < offsets.length; k++) {
      run.onSearch?.(k + 1, offsets.length);
      const off = offsets[k]!;
      const m0 = mul(translation(cx, cy, cz), mul(rotationY((off * Math.PI) / 180), mul(translation(-cx, -cy, -cz), run.initial)));
      const r = await loop(sub, m0, dist, 10, false);
      if (cancelled) return null;
      if (!(await gather(sub, r.m, 0.04))) return null;
      const sc = buf.count / ns;
      // a turned start must win clearly: on a tie the smaller turn stays
      if (sc > bestScore + 0.02) {
        bestScore = sc;
        start = r.m;
        searchYawDeg = off;
        startDist = Math.min(dist, Math.max(0.1, r.dist * 1.5));
      }
    }
  }

  const main = await loop(pts, start, startDist, maxIt, true);
  if (cancelled) return null;
  const { m, it, converged, history } = main;
  const failReason = main.fail;
  const after = (await score(m, scoreDistance)) ?? empty;
  if (cancelled) return null;
  const worse = !(after.rms <= before.rms * 1.02 + 1e-5) || after.inlierFraction < 0.5 * before.inlierFraction || m.some((v) => !Number.isFinite(v));
  const base = { before, after, scoreDistance, history, searchYawDeg, iterations: it };
  if (worse || failReason) {
    const why = failReason
      ? `stopped: ${failReason}`
      : `the fit got worse (RMS ${(before.rms * 100).toFixed(2)} -> ${(after.rms * 100).toFixed(2)} cm, inliers ${(before.inlierFraction * 100).toFixed(0)} -> ${(after.inlierFraction * 100).toFixed(0)}%)`;
    if (failReason && !worse) {
      // stopped early but better than the start: keep it
      return { ...base, matrix: m, ok: true, reverted: false, converged: false, reason: why };
    }
    return { ...base, matrix: run.initial.slice(), ok: false, reverted: true, converged, reason: `${why}; kept the previous alignment` };
  }
  return { ...base, matrix: m, ok: true, reverted: false, converged, reason: converged ? 'converged' : `stopped after ${it} iterations` };
}

// ---------------------------------------------------------------- spatially uniform sample

/**
 * About `target` points spread evenly over the surface (a Poisson-disk thinning on a voxel hash grid): visit the points
 * in a fixed pseudo-random order and keep a point when no kept point lies within `r`; `r` is searched so the count
 * lands near the target (surface clouds: count ~ area / r^2). Returns sorted indices into `positions`.
 *
 * Why not "one point per occupied voxel": on a noisy surface a voxel boundary that runs inside the noise band splits
 * the points of a column into two voxels, and each half gets one representative, so the tail beyond the boundary is
 * over-represented and the sample sits off the surface by a good part of the noise (8 mm for 1.5 cm noise in the
 * building test): ICP then registers that offset. The disk rule does not depend on where a grid starts, so the
 * sample keeps the noise symmetric.
 *
 * `positions` are 3 floats per point in any frame (only relative spacing matters). Deterministic.
 */
export function voxelSample(positions: Float32Array, target: number, preCap = 400_000): Uint32Array {
  const n = Math.floor(positions.length / 3);
  if (n <= target) return Uint32Array.from({ length: n }, (_, i) => i);
  // pre-thin very large clouds with a stride (keeps the work bounded; the shown points are a random sample already)
  const stride = Math.max(1, Math.floor(n / preCap));
  const m = Math.ceil(n / stride);
  let mnx = Infinity, mny = Infinity, mnz = Infinity, mxx = -Infinity, mxy = -Infinity, mxz = -Infinity;
  for (let i = 0; i < n; i += stride) {
    const x = positions[i * 3]!, y = positions[i * 3 + 1]!, z = positions[i * 3 + 2]!;
    if (x < mnx) mnx = x; if (x > mxx) mxx = x;
    if (y < mny) mny = y; if (y > mxy) mxy = y;
    if (z < mnz) mnz = z; if (z > mxz) mxz = z;
  }
  const ex = Math.max(mxx - mnx, 1e-6), ey = Math.max(mxy - mny, 1e-6), ez = Math.max(mxz - mnz, 1e-6);
  // visiting order: a fixed pseudo-random permutation of the strided points (Fisher-Yates with an LCG)
  const order = new Uint32Array(m);
  for (let k = 0; k < m; k++) order[k] = k * stride;
  let seed = 0x9e3779b9;
  for (let k = m - 1; k > 0; k--) {
    seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
    const j = seed % (k + 1);
    const t = order[k]!;
    order[k] = order[j]!;
    order[j] = t;
  }
  // start from a surface estimate: area ~ 2 (xy + yz + zx) of the box; a disk of radius r covers about 0.9 r^2
  let r = Math.sqrt((2 * (ex * ey + ey * ez + ez * ex)) / (target * 0.9));
  let picks: number[] = [];
  for (let round = 0; round < 6; round++) {
    const nx = Math.floor(ex / r) + 1, ny = Math.floor(ey / r) + 1, nz = Math.floor(ez / r) + 1;
    const grid = new Map<number, number[]>();
    const r2 = r * r;
    picks = [];
    for (let k = 0; k < m; k++) {
      const i = order[k]!;
      const x = positions[i * 3]!, y = positions[i * 3 + 1]!, z = positions[i * 3 + 2]!;
      const ix = Math.floor((x - mnx) / r), iy = Math.floor((y - mny) / r), iz = Math.floor((z - mnz) / r);
      let free = true;
      for (let dz = -1; dz <= 1 && free; dz++) {
        const cz = iz + dz;
        if (cz < 0 || cz >= nz) continue;
        for (let dy = -1; dy <= 1 && free; dy++) {
          const cy = iy + dy;
          if (cy < 0 || cy >= ny) continue;
          for (let dx = -1; dx <= 1 && free; dx++) {
            const cx = ix + dx;
            if (cx < 0 || cx >= nx) continue;
            const cell = grid.get(cx + nx * (cy + ny * cz));
            if (!cell) continue;
            for (const j of cell) {
              const ax = positions[j * 3]! - x, ay = positions[j * 3 + 1]! - y, az = positions[j * 3 + 2]! - z;
              if (ax * ax + ay * ay + az * az < r2) { free = false; break; }
            }
          }
        }
      }
      if (!free) continue;
      const key = ix + nx * (iy + ny * iz);
      const cell = grid.get(key);
      if (cell) cell.push(i);
      else grid.set(key, [i]);
      picks.push(i);
    }
    const ratio = picks.length / target;
    if ((ratio > 0.85 && ratio <= 1.15) || picks.length >= m) break;
    r *= Math.sqrt(ratio);
  }
  picks.sort((a, b) => a - b);
  if (picks.length > target) {
    const step = picks.length / target;
    const out = new Uint32Array(target);
    for (let i = 0; i < target; i++) out[i] = picks[Math.floor(i * step)]!;
    return out;
  }
  return Uint32Array.from(picks);
}
