// Point normals of an ICP sample, for normal compatible correspondences (icp.ts). Pure, no DOM, no three.js.
//
//   estimateNormals   PCA over the k nearest neighbours of each sample point in a denser copy of the cloud (grid hash):
//                     the normal is the eigenvector of the smallest eigenvalue of the neighbourhood covariance.
//                     Points with too few neighbours or no plane around them (corners, edges, clutter: the smallest
//                     eigenvalue is a large share of the total) get no normal and do not take part in ICP.
//   orientation       a normal is an axis until something says which side the sensor saw the surface from:
//                     1. the viewpoint (sensor position), when known: the normal turns towards it, unless it grazes
//                        the line of sight or the tube along the normal on the sensor's side holds points (then the
//                        point was seen from elsewhere, past something in front of it).
//                     2. without a viewpoint, occlusion: a scanner cannot see a point through other points, so a thin
//                        tube along the normal that holds points on one side (the other face of a wall, the slab
//                        under a floor) and none on the other side is seen from the empty side. Tested on a denser
//                        copy of the cloud. Not used when a viewpoint is known: in a cluttered room a wall seen
//                        obliquely past a chimney has the chimney in its tube, and the rule would flip it.
//                     3. otherwise the normal stays an axis (`oriented` 0): ICP then only compares |dot|.
//
// Why: on a thin wall whose two faces lie within the scan noise of each other (the 2.4 cm plumbing wall of the sample
// house) the closest model surface of a noise point beyond the wall centre is the far face. Point-to-plane ICP then
// pulls the cloud sideways by a few millimetres; on a 20 cm wall, turned 10 degrees, the far face even cancels the
// turn. With oriented normals, the closest surface that faces the same way is taken instead.

import type { Vec3 } from './types';

export interface NormalOptions {
  /** Neighbours used for the PCA. */
  k?: number;
  /** Sensor position in the frame of the points, when known (a single scan, or the start of a phone scan). */
  viewpoint?: Vec3 | null;
  /** A denser copy of the cloud (same frame: positions + base) for the occlusion test; the sample itself otherwise. */
  dense?: { positions: Float32Array; base: Vec3 } | null;
  /** Largest share of the variance along the normal for a usable plane (0..1/3). */
  maxCurvature?: number;
}

export interface CloudNormals {
  /** 3 floats per point, unit length; (0, 0, 0) where no plane was found. */
  normals: Float32Array;
  /** 1 where the sign is known (the normal points to the side the surface was seen from), 0 for an axis only. */
  oriented: Uint8Array;
  /** Median spacing of the sample, metres. */
  spacing: number;
  /** Median spread along the normals (the noise estimate), metres. */
  noise: number;
  valid: number;
  orientedCount: number;
  byOcclusion: number;
  byViewpoint: number;
}

/**
 * One number for integer cell coordinates: 2^17 cells per axis (from -65536), so the key stays below 2^51 and exact
 * in a double (2^20 per axis overflowed 2^53 and merged neighbouring cells). Cells beyond are clamped: 1.3 km per axis
 * at 2 cm cells.
 */
export function cellKey3(x: number, y: number, z: number): number {
  const c = (v: number): number => (v < -65536 ? 0 : v > 65535 ? 131071 : v + 65536);
  return c(x) + 131072 * (c(y) + 131072 * c(z));
}

/** Points in square cells of `cell` metres, looked up by integer cell coordinates. */
export class GridHash {
  private readonly map = new Map<number, number>();
  readonly start: Uint32Array;
  readonly items: Uint32Array;
  constructor(
    private readonly get: (i: number, k: number) => number,
    readonly count: number,
    readonly cell: number,
    readonly origin: Vec3,
  ) {
    const keys = new Float64Array(count);
    const counts: number[] = [];
    const cellOf = new Uint32Array(count);
    for (let i = 0; i < count; i++) {
      const key = this.keyOf(this.ix(get(i, 0), 0), this.ix(get(i, 1), 1), this.ix(get(i, 2), 2));
      keys[i] = key;
      let c = this.map.get(key);
      if (c === undefined) {
        c = counts.length;
        this.map.set(key, c);
        counts.push(0);
      }
      counts[c]!++;
      cellOf[i] = c;
    }
    this.start = new Uint32Array(counts.length + 1);
    for (let c = 0; c < counts.length; c++) this.start[c + 1] = this.start[c]! + counts[c]!;
    const fill = this.start.slice(0, counts.length);
    this.items = new Uint32Array(count);
    for (let i = 0; i < count; i++) this.items[fill[cellOf[i]!]!++] = i;
  }
  ix(v: number, axis: number): number {
    return Math.floor((v - this.origin[axis]!) / this.cell);
  }
  private keyOf(x: number, y: number, z: number): number {
    return cellKey3(x, y, z);
  }
  /** Index of cell (x, y, z) into `start`, or -1 when it is empty. */
  cellAt(x: number, y: number, z: number): number {
    return this.map.get(this.keyOf(x, y, z)) ?? -1;
  }
  /** Calls fn with the indices in cell (x, y, z); stops early when fn returns true. Returns true when stopped. */
  forEach(x: number, y: number, z: number, fn: (i: number) => boolean | void): boolean {
    const c = this.map.get(this.keyOf(x, y, z));
    if (c === undefined) return false;
    for (let k = this.start[c]!; k < this.start[c + 1]!; k++) if (fn(this.items[k]!)) return true;
    return false;
  }
}

/** Eigenvector of the smallest eigenvalue of a symmetric 3x3 (a00 a01 a02 a11 a12 a22), with the eigenvalues. */
export function smallestEigen(a00: number, a01: number, a02: number, a11: number, a12: number, a22: number): { n: Vec3; l0: number; sum: number } {
  // eigenvalues of a symmetric 3x3 in closed form (trigonometric), then the eigenvector from the cross products
  const sum = a00 + a11 + a22;
  const q = sum / 3;
  const p1 = a01 * a01 + a02 * a02 + a12 * a12;
  const b00 = a00 - q, b11 = a11 - q, b22 = a22 - q;
  const p2 = b00 * b00 + b11 * b11 + b22 * b22 + 2 * p1;
  const p = Math.sqrt(p2 / 6);
  if (p < 1e-30) return { n: [0, 0, 1], l0: q, sum };
  const det = (b00 * (b11 * b22 - a12 * a12) - a01 * (a01 * b22 - a12 * a02) + a02 * (a01 * a12 - b11 * a02)) / (p * p * p);
  const r = Math.min(1, Math.max(-1, det / 2));
  const phi = Math.acos(r) / 3;
  const l0 = q + 2 * p * Math.cos(phi + (2 * Math.PI) / 3); // smallest
  // rows of (A - l0 I); the eigenvector is the largest cross product of two rows
  const r0: Vec3 = [a00 - l0, a01, a02], r1: Vec3 = [a01, a11 - l0, a12], r2: Vec3 = [a02, a12, a22 - l0];
  const cr = (u: Vec3, v: Vec3): Vec3 => [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]];
  const c = [cr(r0, r1), cr(r0, r2), cr(r1, r2)];
  let best = c[0]!, bl = 0;
  for (const v of c) {
    const l = v[0] * v[0] + v[1] * v[1] + v[2] * v[2];
    if (l > bl) { bl = l; best = v; }
  }
  if (bl < 1e-60) return { n: [0, 0, 1], l0, sum };
  const il = 1 / Math.sqrt(bl);
  return { n: [best[0] * il, best[1] * il, best[2] * il], l0: Math.max(0, l0), sum };
}

function bounds(get: (i: number, k: number) => number, n: number): { min: Vec3; max: Vec3 } {
  const min: Vec3 = [Infinity, Infinity, Infinity], max: Vec3 = [-Infinity, -Infinity, -Infinity];
  for (let i = 0; i < n; i++) {
    for (let k = 0; k < 3; k++) {
      const v = get(i, k);
      if (v < min[k]!) min[k] = v;
      if (v > max[k]!) max[k] = v;
    }
  }
  return { min, max };
}

/**
 * Noise estimate: the median spread along the normal (square root of the smallest eigenvalue) of the k nearest of up
 * to 2000 points of the dense set. Low by a factor of about 1.5 (the plane is fitted into the noise), and dense
 * neighbourhoods do not reach the other face of a wall, as a sparse sample's would.
 */
function noiseOf(get: (i: number, k: number) => number, n: number, origin: Vec3, spacing: number, k: number): { noise: number; rk: number } {
  if (n < 8) return { noise: 0, rk: spacing * 2 };
  const rks: number[] = [];
  const R = Math.max(4 * spacing, 1e-3);
  const g = new GridHash(get, n, R, origin);
  const step = Math.max(1, Math.floor(n / 2000));
  const out: number[] = [];
  const nd = new Float64Array(k), ni = new Int32Array(k);
  for (let i = 0; i < n; i += step) {
    const x = get(i, 0), y = get(i, 1), z = get(i, 2);
    const cx = g.ix(x, 0), cy = g.ix(y, 1), cz = g.ix(z, 2);
    let m = 0;
    for (let dz = -1; dz <= 1; dz++) for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) {
      const c = g.cellAt(cx + dx, cy + dy, cz + dz);
      if (c < 0) continue;
      for (let q = g.start[c]!; q < g.start[c + 1]!; q++) {
        const j = g.items[q]!;
        const d = (get(j, 0) - x) ** 2 + (get(j, 1) - y) ** 2 + (get(j, 2) - z) ** 2;
        if (d > R * R) continue;
        if (m < k) {
          let at = m++;
          while (at > 0 && nd[at - 1]! > d) { nd[at] = nd[at - 1]!; ni[at] = ni[at - 1]!; at--; }
          nd[at] = d; ni[at] = j;
        } else if (d < nd[m - 1]!) {
          let at = m - 1;
          while (at > 0 && nd[at - 1]! > d) { nd[at] = nd[at - 1]!; ni[at] = ni[at - 1]!; at--; }
          nd[at] = d; ni[at] = j;
        }
      }
    }
    if (m < 6) continue;
    let mx = 0, my = 0, mz = 0;
    for (let t = 0; t < m; t++) { mx += get(ni[t]!, 0); my += get(ni[t]!, 1); mz += get(ni[t]!, 2); }
    mx /= m; my /= m; mz /= m;
    let a00 = 0, a01 = 0, a02 = 0, a11 = 0, a12 = 0, a22 = 0;
    for (let t = 0; t < m; t++) {
      const u = get(ni[t]!, 0) - mx, v = get(ni[t]!, 1) - my, w = get(ni[t]!, 2) - mz;
      a00 += u * u; a01 += u * v; a02 += u * w; a11 += v * v; a12 += v * w; a22 += w * w;
    }
    const e = smallestEigen(a00 / m, a01 / m, a02 / m, a11 / m, a12 / m, a22 / m);
    if (e.sum > 0) out.push(Math.sqrt(e.l0));
    if (m === k) rks.push(Math.sqrt(nd[k - 1]!));
  }
  out.sort((a, b) => a - b);
  rks.sort((a, b) => a - b);
  return { noise: out.length ? out[out.length >> 1]! : 0, rk: rks.length ? rks[rks.length >> 1]! : 4 * spacing };
}

/** Median nearest neighbour distance of up to 1000 points (spread over the set), via a grid of `guess` cells. */
function medianSpacing(get: (i: number, k: number) => number, n: number, origin: Vec3, guess: number): number {
  if (n < 2) return guess;
  const g = new GridHash(get, n, guess, origin);
  const step = Math.max(1, Math.floor(n / 1000));
  const ds: number[] = [];
  for (let i = 0; i < n; i += step) {
    const x = get(i, 0), y = get(i, 1), z = get(i, 2);
    const cx = g.ix(x, 0), cy = g.ix(y, 1), cz = g.ix(z, 2);
    let best = Infinity;
    for (let dz = -1; dz <= 1; dz++) for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) {
      g.forEach(cx + dx, cy + dy, cz + dz, (j) => {
        if (j === i) return;
        const d = (get(j, 0) - x) ** 2 + (get(j, 1) - y) ** 2 + (get(j, 2) - z) ** 2;
        if (d < best) best = d;
      });
    }
    if (Number.isFinite(best)) ds.push(Math.sqrt(best));
  }
  if (!ds.length) return guess;
  ds.sort((a, b) => a - b);
  return ds[ds.length >> 1]!;
}

/** Normals of `points` (3 doubles per point, any frame). Deterministic. Runs in one piece; see estimateNormalsAsync. */
export function estimateNormals(points: Float64Array, opt: NormalOptions = {}): CloudNormals {
  const job = normalsJob(points, opt);
  for (;;) {
    const r = job.next();
    if (r.done) return r.value;
  }
}

/**
 * The same, in time slices of `sliceMs` with `yieldFn` between them (the page stays responsive: about 1 to 3 s for
 * 20 000 sample points with a dense copy of 100 000 on a slow machine). Null when `isCancelled` says so.
 */
export async function estimateNormalsAsync(
  points: Float64Array,
  opt: NormalOptions & { sliceMs?: number; yieldFn?: () => Promise<void>; isCancelled?: () => boolean } = {},
): Promise<CloudNormals | null> {
  const job = normalsJob(points, opt);
  const sliceMs = opt.sliceMs ?? 12;
  const yieldFn = opt.yieldFn ?? ((): Promise<void> => new Promise((r) => setTimeout(r, 0)));
  let t0 = performance.now();
  let slice = sliceMs;
  for (;;) {
    const r = job.next();
    if (r.done) return r.value;
    if (performance.now() - t0 > slice) {
      const end = performance.now();
      await yieldFn();
      if (opt.isCancelled?.()) return null;
      t0 = performance.now();
      // adaptive slice, as in icp.ts: when a heavy frame was drawn in the gap (a software renderer: 150 to 300 ms per
      // frame), take a longer slice so the work still makes progress. A fixed 12 ms slice spent about 95 percent of
      // the time in frames (11.5 s for 0.7 s of work); on a fast machine the gap is ~0 and slices stay short.
      slice = Math.min(250, Math.max(sliceMs, (t0 - end) * 0.5));
    }
  }
}

function* normalsJob(points: Float64Array, opt: NormalOptions): Generator<void, CloudNormals, void> {
  const n = Math.floor(points.length / 3);
  const k = opt.k ?? 16;
  const maxCurv = opt.maxCurvature ?? 0.06;
  const normals = new Float32Array(n * 3);
  const oriented = new Uint8Array(n);
  const empty: CloudNormals = { normals, oriented, spacing: 0, noise: 0, valid: 0, orientedCount: 0, byOcclusion: 0, byViewpoint: 0 };
  if (n < 8) return empty;
  const get = (i: number, a: number): number => points[i * 3 + a]!;
  const b = bounds(get, n);
  const ex = Math.max(b.max[0] - b.min[0], 1e-3), ey = Math.max(b.max[1] - b.min[1], 1e-3), ez = Math.max(b.max[2] - b.min[2], 1e-3);
  const guess = Math.sqrt((2 * (ex * ey + ey * ez + ez * ex)) / (0.9 * n));
  const spacing = medianSpacing(get, n, b.min, guess);
  // the denser copy (the sample itself without one): its spacing sizes the occlusion tube, its noise the neighbourhoods
  const dense = opt.dense;
  const dn = dense ? Math.floor(dense.positions.length / 3) : n;
  const dget = dense ? (i: number, a: number): number => dense.positions[i * 3 + a]! + dense.base[a]! : get;
  const dSpacing = dense ? medianSpacing(dget, dn, b.min, Math.max(spacing / 3, 1e-3)) : spacing;
  yield;
  // Neighbourhoods, in the dense copy: the k nearest within 3 dense spacings, unless they lie closer than Rmin = 16 x
  // the noise estimate (about 10 x the real noise; at most 8 dense spacings): then up to 48 points spread over Rmin
  // instead (an even stride through the candidates). A neighbourhood about as wide as the noise is thick has no plane
  // to find (a dense raw scan); one much wider than the wall thickness reaches the other face (the sample of a whole
  // building has 12 cm spacing against 20 cm walls, so its own 16 nearest straddle them: the dense copy does not).
  const dpos = dense ? dense.positions : null, dbase = dense ? dense.base : [0, 0, 0];
  let valid = 0;
  const cand = new Int32Array(4096), cd = new Float64Array(4096);
  const nd = new Float64Array(64), ni = new Int32Array(64);
  const pass = function* (R: number, rMin: number, write: boolean): Generator<void, void, void> {
    const grid = new GridHash(dget, dn, R, b.min);
    const R2 = R * R, rMin2 = rMin * rMin;
    for (let i = 0; i < n; i++) {
      if ((i & 255) === 255) yield;
      const x = get(i, 0), y = get(i, 1), z = get(i, 2);
      const cx = grid.ix(x, 0), cy = grid.ix(y, 1), cz = grid.ix(z, 2);
      let m = 0;
      let c = 0;
      const st = grid.start, it = grid.items;
      for (let dz = -1; dz <= 1; dz++) for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) {
        const cc = grid.cellAt(cx + dx, cy + dy, cz + dz);
        if (cc < 0) continue;
        for (let q = st[cc]!, qe = st[cc + 1]!; q < qe; q++) {
          const j = it[q]!;
          const ux = dpos ? dpos[j * 3]! + dbase[0]! - x : points[j * 3]! - x;
          const uy = dpos ? dpos[j * 3 + 1]! + dbase[1]! - y : points[j * 3 + 1]! - y;
          const uz = dpos ? dpos[j * 3 + 2]! + dbase[2]! - z : points[j * 3 + 2]! - z;
          const d = ux * ux + uy * uy + uz * uz;
          if (d > R2) continue;
          if (d <= rMin2 && c < cand.length) { cand[c] = j; cd[c++] = d; }
          // keep the k nearest (insertion into a sorted list)
          if (m < k) {
            let at = m++;
            while (at > 0 && nd[at - 1]! > d) { nd[at] = nd[at - 1]!; ni[at] = ni[at - 1]!; at--; }
            nd[at] = d; ni[at] = j;
          } else if (d < nd[m - 1]!) {
            let at = m - 1;
            while (at > 0 && nd[at - 1]! > d) { nd[at] = nd[at - 1]!; ni[at] = ni[at - 1]!; at--; }
            nd[at] = d; ni[at] = j;
          }
        }
      }
      if (m === k && nd[m - 1]! < rMin2 && c > k) {
        // the k nearest are packed too tight: spread up to 48 over the Rmin ball instead
        const stride = Math.max(1, c / 48);
        m = 0;
        for (let t = 0; t < c && m < 48; t++) if (Math.floor(t / stride) === m) ni[m++] = cand[t]!;
      }
      if (m < 6) continue;
      let mx = 0, my = 0, mz = 0;
      for (let t = 0; t < m; t++) { const j = ni[t]!; mx += dget(j, 0); my += dget(j, 1); mz += dget(j, 2); }
      mx /= m; my /= m; mz /= m;
      let a00 = 0, a01 = 0, a02 = 0, a11 = 0, a12 = 0, a22 = 0;
      for (let t = 0; t < m; t++) {
        const j = ni[t]!;
        const u = dget(j, 0) - mx, v = dget(j, 1) - my, w = dget(j, 2) - mz;
        a00 += u * u; a01 += u * v; a02 += u * w; a11 += v * v; a12 += v * w; a22 += w * w;
      }
      const e = smallestEigen(a00 / m, a01 / m, a02 / m, a11 / m, a12 / m, a22 / m);
      if (!write) continue;
      if (!(e.sum > 0) || e.l0 / e.sum > maxCurv) continue;
      normals[i * 3] = e.n[0]; normals[i * 3 + 1] = e.n[1]; normals[i * 3 + 2] = e.n[2];
      valid++;
    }
  };
  const { noise, rk } = noiseOf(dget, dn, b.min, dSpacing, k);
  yield;
  const rMin = Math.min(16 * noise, 8 * dSpacing);
  yield* pass(Math.max(3 * dSpacing, rMin, 1e-3), rMin, true);

  // ---- orientation
  let byOcc = 0, byView = 0;
  // tube: balls of radius rho along the normal, in half-radius steps from `near` (beyond the noise of the surface
  // itself, even with the normal off by 25 degrees) to `far`. rho = 0.9 x the median distance to the k-th nearest
  // dense point, so a ball crossing a surface holds about 4 of its points (the nearest-neighbour spacing of a random
  // scan is much smaller than that and would make the balls too small to notice the other face of a wall)
  const rho = Math.max(0.02, 0.9 * rk);
  const near = Math.max(0.05, (4 * noise + rho) / 0.9);
  const far = Math.max(0.6, near + 4 * rho);
  const tube = new GridHash(dget, dn, rho, b.min);
  yield;
  const r2 = rho * rho;
  const occupied = (x: number, y: number, z: number, nx: number, ny: number, nz: number, need: number): number => {
    let hits = 0;
    for (let t = near; t <= far; t += rho / 2) {
      const qx = x + nx * t, qy = y + ny * t, qz = z + nz * t;
      // the 2 x 2 x 2 cells nearest to q cover the ball of radius rho around it
      const x0 = Math.round((qx - b.min[0]) / rho) - 1, y0 = Math.round((qy - b.min[1]) / rho) - 1, z0 = Math.round((qz - b.min[2]) / rho) - 1;
      for (let dz = 0; dz < 2; dz++) for (let dy = 0; dy < 2; dy++) for (let dx = 0; dx < 2; dx++) {
        const c = tube.cellAt(x0 + dx, y0 + dy, z0 + dz);
        if (c < 0) continue;
        for (let q = tube.start[c]!, qe = tube.start[c + 1]!; q < qe; q++) {
          const j = tube.items[q]!;
          const ux = dget(j, 0) - qx, uy = dget(j, 1) - qy, uz = dget(j, 2) - qz;
          if (ux * ux + uy * uy + uz * uz <= r2 && ++hits >= need) return hits;
        }
      }
    }
    return hits;
  };
  const vp = opt.viewpoint ?? null;
  for (let i = 0; i < n; i++) {
    let nx = normals[i * 3]!, ny = normals[i * 3 + 1]!, nz = normals[i * 3 + 2]!;
    if (!nx && !ny && !nz) continue;
    const x = get(i, 0), y = get(i, 1), z = get(i, 2);
    const NEED = 4;
    let sign = 0;
    if ((i & 511) === 511) yield;
    if (vp) {
      // towards the sensor, unless the normal grazes the line of sight (the side is then a guess) or the tube on the
      // sensor's side holds points (the point was seen from elsewhere, past something in front of it)
      const vx = vp[0] - x, vy = vp[1] - y, vz = vp[2] - z;
      const dot = (vx * nx + vy * ny + vz * nz) / (Math.hypot(vx, vy, vz) || 1);
      if (Math.abs(dot) > 0.15) {
        const s2 = dot > 0 ? 1 : -1;
        if (occupied(x, y, z, s2 * nx, s2 * ny, s2 * nz, 1) === 0) { sign = s2; byView++; }
      }
    } else {
      // no sensor: the occlusion rule (the side with points behind is the far side)
      const front = occupied(x, y, z, nx, ny, nz, NEED);
      // the back tube only matters when the front one is decisive (then 1 point is enough) or empty
      const back = front >= NEED ? occupied(x, y, z, -nx, -ny, -nz, 1) : front === 0 ? occupied(x, y, z, -nx, -ny, -nz, NEED) : NEED;
      if (front >= NEED && back === 0) { sign = -1; byOcc++; }
      else if (back >= NEED && front === 0) { sign = 1; byOcc++; }
    }
    if (sign) {
      if (sign < 0) { nx = -nx; ny = -ny; nz = -nz; }
      normals[i * 3] = nx; normals[i * 3 + 1] = ny; normals[i * 3 + 2] = nz;
      oriented[i] = 1;
    }
  }
  return { normals, oriented, spacing, noise, valid, orientedCount: byOcc + byView, byOcclusion: byOcc, byViewpoint: byView };
}
