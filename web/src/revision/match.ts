// Matching and comparing the elements of two snapshots (design 3.2). Pure. Two jobs:
//   compareShape   the geometry and placement test of one matched pair
//   matchLeftovers pair up the elements whose GlobalIds did not meet: global offset, grid candidates, score, greedy one-to-one
//
// Both snapshots are read through a `Frame`: Float64 copies of the signature columns, with the centroids moved into one common
// reference (the head's origin shift), so a base and a head with different shifts compare in metres, not in shifted units.

import { nameStem } from '../classify/state';
import { rel } from './geomSig';
import { hash32 } from './snapshot';
import { SIG_STRIDE } from './types';
import type { ChangeFlag, ModelSnapshot, RevisionOptions, Vec3 } from './types';

export interface Frame {
  n: number;
  /** Centroid, extent, area, volume, moments (Float64) in the common reference. */
  cx: Float64Array; cy: Float64Array; cz: Float64Array;
  area: Float64Array; vol: Float64Array;
  m1: Float64Array; m2: Float64Array; m3: Float64Array;
  ex: Float64Array; ey: Float64Array; ez: Float64Array;
  /** Bounding box diagonal. */
  diag: Float64Array;
}

/** The columns of a snapshot as Float64 arrays; centroids relative to `ref` (IFC world frame, usually the head's origin shift). */
export function frameOf(s: ModelSnapshot, ref: Vec3): Frame {
  const n = s.globalId.length;
  const f: Frame = {
    n, cx: new Float64Array(n), cy: new Float64Array(n), cz: new Float64Array(n), area: new Float64Array(n), vol: new Float64Array(n),
    m1: new Float64Array(n), m2: new Float64Array(n), m3: new Float64Array(n), ex: new Float64Array(n), ey: new Float64Array(n), ez: new Float64Array(n),
    diag: new Float64Array(n),
  };
  const dx = s.originShift[0] - ref[0], dy = s.originShift[1] - ref[1], dz = s.originShift[2] - ref[2];
  for (let i = 0; i < n; i++) {
    const o = i * SIG_STRIDE;
    f.area[i] = s.sig[o]!;
    f.vol[i] = s.sig[o + 1]!;
    f.cx[i] = s.sig[o + 2]! + dx; f.cy[i] = s.sig[o + 3]! + dy; f.cz[i] = s.sig[o + 4]! + dz;
    f.m1[i] = s.sig[o + 5]!; f.m2[i] = s.sig[o + 6]!; f.m3[i] = s.sig[o + 7]!;
    f.ex[i] = s.sig[o + 8]!; f.ey[i] = s.sig[o + 9]!; f.ez[i] = s.sig[o + 10]!;
    f.diag[i] = Math.hypot(f.ex[i]!, f.ey[i]!, f.ez[i]!);
  }
  return f;
}

/** The largest relative difference of the three moment eigenvalues. */
export const momentDiff = (a: Frame, i: number, b: Frame, j: number): number => Math.max(rel(a.m1[i]!, b.m1[j]!), rel(a.m2[i]!, b.m2[j]!), rel(a.m3[i]!, b.m3[j]!));

export interface ShapeCompare {
  flags: ChangeFlag[];
  move?: number;
  delta?: Vec3;
  rotated?: boolean;
}

/**
 * The geometry and placement test of one pair. `offset` is the global offset that was removed before matching (head minus base).
 *   shape differs                       -> geometry
 *   else centroid moved or extent turned -> placement (rotated when the extent changed)
 */
export const SAME_SHAPE: ShapeCompare = Object.freeze({ flags: Object.freeze([]) as unknown as ChangeFlag[] });

export function compareShape(a: Frame, i: number, b: Frame, j: number, o: RevisionOptions, offset: Vec3 = [0, 0, 0]): ShapeCompare {
  const shapeSame = rel(a.area[i]!, b.area[j]!) <= o.areaTol && momentDiff(a, i, b, j) <= o.momentTol;
  if (!shapeSame) return { flags: ['geometry'] };
  const dx = b.cx[j]! - a.cx[i]! - offset[0], dy = b.cy[j]! - a.cy[i]! - offset[1], dz = b.cz[j]! - a.cz[i]! - offset[2];
  const move = Math.hypot(dx, dy, dz);
  const biggest = Math.max(a.ex[i]!, a.ey[i]!, a.ez[i]!, b.ex[j]!, b.ey[j]!, b.ez[j]!);
  const dExt = Math.max(Math.abs(a.ex[i]! - b.ex[j]!), Math.abs(a.ey[i]! - b.ey[j]!), Math.abs(a.ez[i]! - b.ez[j]!));
  const rotated = dExt > Math.max(o.extentTolAbs, o.extentTolRel * biggest);
  if (move > o.moveTol || rotated) return { flags: ['placement'], move, delta: [dx, dy, dz], ...(rotated ? { rotated: true } : {}) };
  return SAME_SHAPE;
}

// ---------------------------------------------------------------- matching of leftovers

/** About how many elements the global-offset estimate looks at. */
const OFFSET_SAMPLE = 6000;
const clamp01 = (x: number): number => (x < 0 ? 0 : x > 1 ? 1 : x);
const bucket = (area: number): number => Math.round(Math.log(area + 1e-9) / 0.04);
const baseClass = (c: string): string => c.replace(/(StandardCase|ElementedCase)$/, '');

/** Cells are packed into one safe integer: 17 bits per axis (+-65 km of 1 m cells around the head's origin). */
const cellKey = (x: number, y: number, z: number, cell: number): number => {
  const cl = (v: number): number => Math.max(0, Math.min(131071, Math.floor(v / cell) + 65536));
  return (cl(x) * 131072 + cl(y)) * 131072 + cl(z);
};

export interface MatchPair {
  d: number;
  n: number;
  score: number;
}

/**
 * The global offset between two models whose GUIDs share almost nothing: the most frequent centroid delta among elements that are
 * unique on both sides by (class, name, shape bucket). [0,0,0] when there is too little evidence.
 */
export function estimateOffset(base: ModelSnapshot, head: ModelSnapshot, a: Frame, b: Frame, D: readonly number[], N: readonly number[]): Vec3 {
  const key = (s: ModelSnapshot, f: Frame, i: number): string => `${s.ifcClass[i]}|${s.name[i]}|${bucket(f.area[i]!)}`;
  // Evidence from about OFFSET_SAMPLE elements is plenty: a content-based sample (the same names on both sides) keeps the cost flat
  const keep = Math.max(1, Math.ceil(Math.max(D.length, N.length) / OFFSET_SAMPLE));
  const mapOf = (s: ModelSnapshot, f: Frame, ids: readonly number[]): Map<string, number> => {
    const m = new Map<string, number>();
    for (const i of ids) {
      if (f.area[i]! <= 0 || !s.name[i]) continue;
      if (keep > 1 && hash32(s.name[i]!) % keep !== 0) continue;
      const k = key(s, f, i);
      m.set(k, m.has(k) ? -1 : i);
    }
    return m;
  };
  const mb = mapOf(base, a, D), mh = mapOf(head, b, N);
  const deltas: Vec3[] = [];
  for (const [k, i] of mb) {
    const j = mh.get(k);
    if (i < 0 || j === undefined || j < 0) continue;
    deltas.push([b.cx[j]! - a.cx[i]!, b.cy[j]! - a.cy[i]!, b.cz[j]! - a.cz[i]!]);
  }
  if (deltas.length === 0) return [0, 0, 0];
  const votes = new Map<string, number>();
  const r = (v: number): number => Math.round(v * 100);
  for (const d of deltas) { const k = `${r(d[0])},${r(d[1])},${r(d[2])}`; votes.set(k, (votes.get(k) ?? 0) + 1); }
  let best = '', top = 0;
  for (const [k, c] of votes) if (c > top || (c === top && k < best)) { best = k; top = c; }
  if (top < Math.min(3, Math.ceil(deltas.length / 2))) return [0, 0, 0];
  const [bx, by, bz] = best.split(',').map((x) => Number(x) / 100) as Vec3;
  const near = deltas.filter((d) => Math.hypot(d[0] - bx, d[1] - by, d[2] - bz) <= 0.05);
  const med = (k: 0 | 1 | 2): number => { const v = near.map((d) => d[k]).sort((x, y) => x - y); return v[Math.floor(v.length / 2)]!; };
  return [med(0), med(1), med(2)];
}

export interface MatchContext {
  base: ModelSnapshot;
  head: ModelSnapshot;
  a: Frame;
  b: Frame;
  options: RevisionOptions;
  /** Head minus base, removed from every centroid delta. */
  offset: Vec3;
}

/**
 * One-to-one pairs between D (base indices) and N (head indices):
 *   candidates  head elements in the 27 grid cells around the base centroid, plus the same non-empty Tag, plus the same (name, shape)
 *   score       0.30 g + 0.25 p + 0.20 m + 0.15 c + 0.10 s (see the design)
 *   take        greedily by score while score >= matchMin and the margin over the next best candidate of either side >= matchMargin
 */
export function matchLeftovers(ctx: MatchContext, D: readonly number[], N: readonly number[]): MatchPair[] {
  const { base, head, a, b, options: o, offset } = ctx;
  if (D.length === 0 || N.length === 0) return [];
  const cell = o.gridCell;
  // Buckets as linked lists in typed arrays (no array per cell): first.get(key) is the newest head index, next[j] the one before it.
  class Buckets<K> {
    readonly first = new Map<K, number>();
    readonly next: Int32Array;
    constructor(n: number) { this.next = new Int32Array(n).fill(-1); }
    add(k: K, j: number): void { const f = this.first.get(k); if (f !== undefined) this.next[j] = f; this.first.set(k, j); }
    /** The members, or null when there are more than `max` (a bucket that big says nothing). */
    each(k: K, max: number, fn: (j: number) => void): void {
      let j = this.first.get(k) ?? -1;
      if (max < Infinity) { let c = 0; for (let x = j; x >= 0; x = this.next[x]!) if (++c > max) return; }
      for (; j >= 0; j = this.next[j]!) fn(j);
    }
  }
  const nN = head.globalId.length;
  const grid = new Buckets<number>(nN), byTag = new Buckets<string>(nN), byNameShape = new Buckets<string>(nN);
  for (const j of N) {
    if (b.area[j]! <= 0) continue;
    grid.add(cellKey(b.cx[j]!, b.cy[j]!, b.cz[j]!, cell), j);
    if (head.tag[j]) byTag.add(head.tag[j]!, j);
    if (head.name[j]) byNameShape.add(`${head.name[j]}|${bucket(b.area[j]!)}`, j);
  }
  const stemB = new Map<number, string>();
  const stemOf = (s: ModelSnapshot, cache: Map<number, string>, i: number): string => { let v = cache.get(i); if (v === undefined) { v = nameStem(s.name[i]!); cache.set(i, v); } return v; };
  const stemA = new Map<number, string>();

  // top two scores per side, with the partner of the best
  const nD = base.globalId.length;
  const best1d = new Float64Array(nD), best2d = new Float64Array(nD), bestPd = new Int32Array(nD).fill(-1);
  const best1n = new Float64Array(nN), best2n = new Float64Array(nN), bestPn = new Int32Array(nN).fill(-1);
  const stamp = new Int32Array(nN);
  const pairs: MatchPair[] = [];
  let stampId = 0;

  const consider = (i: number, j: number): void => {
    const area = rel(a.area[i]!, b.area[j]!);
    if (area >= o.matchShapeTol) return;
    const mom = momentDiff(a, i, b, j);
    if (mom >= o.matchShapeTol) return;
    const g = 1 - clamp01(Math.max(area, mom) / o.matchShapeTol);
    const dist = Math.hypot(b.cx[j]! - a.cx[i]! - offset[0], b.cy[j]! - a.cy[i]! - offset[1], b.cz[j]! - a.cz[i]! - offset[2]);
    const p = 1 - clamp01(dist / Math.max(0.5, 0.5 * a.diag[i]!));
    let m = 0;
    if ((base.tag[i] && base.tag[i] === head.tag[j]) || (base.name[i] && base.name[i] === head.name[j])) m = 1;
    else if (base.name[i] && head.name[j]) { const sa = stemOf(base, stemA, i); if (sa && sa === stemOf(head, stemB, j)) m = 0.7; }
    const ca = base.ifcClass[i]!, cb = head.ifcClass[j]!;
    const c = ca === cb ? 1 : baseClass(ca) === baseClass(cb) ? 0.5 : 0;
    const sa = base.storey[i], sb = head.storey[j];
    const s = (!sa && !sb) || (sa && sb && (sa.name === sb.name || Math.abs(sa.elevation - sb.elevation) <= o.elevationTol)) ? 1 : 0;
    const score = 0.3 * g + 0.25 * p + 0.2 * m + 0.15 * c + 0.1 * s;
    if (score > best1d[i]!) { best2d[i] = best1d[i]!; best1d[i] = score; bestPd[i] = j; } else if (score > best2d[i]!) best2d[i] = score;
    if (score > best1n[j]!) { best2n[j] = best1n[j]!; best1n[j] = score; bestPn[j] = i; } else if (score > best2n[j]!) best2n[j] = score;
    if (score >= o.matchMin) pairs.push({ d: i, n: j, score });
  };

  const lo = (v: number, r: number): number => Math.floor((v - r) / cell);
  const hi = (v: number, r: number): number => Math.floor((v + r) / cell);
  for (const i of D) {
    if (a.area[i]! <= 0) continue;
    stampId++;
    const x = a.cx[i]! + offset[0], y = a.cy[i]! + offset[1], z = a.cz[i]! + offset[2];
    const visit = (j: number): void => { if (stamp[j] === stampId) return; stamp[j] = stampId; consider(i, j); };
    // The cells that a pair can still score matchMin in: the position term p is the only one that falls with distance, and a pair
    // needs p >= 0.2 (all other terms at 1 give 0.75), so its distance is at most 0.8 x max(0.5 m, half the diagonal). At most the 27
    // cells around the centroid (design 3.2), usually 8.
    const r = Math.min(0.8 * Math.max(0.5, 0.5 * a.diag[i]!), 1.5 * cell);
    const x0 = lo(x, r), x1 = hi(x, r), y0 = lo(y, r), y1 = hi(y, r), z0 = lo(z, r), z1 = hi(z, r);
    for (let ix = x0; ix <= x1; ix++) for (let iy = y0; iy <= y1; iy++) for (let iz = z0; iz <= z1; iz++) {
      grid.each(cellKey((ix + 0.5) * cell, (iy + 0.5) * cell, (iz + 0.5) * cell, cell), Infinity, visit);
    }
    if (base.tag[i]) byTag.each(base.tag[i]!, 64, visit);
    if (base.name[i]) byNameShape.each(`${base.name[i]}|${bucket(a.area[i]!)}`, 64, visit);
  }

  pairs.sort((p, q) => q.score - p.score || p.d - q.d || p.n - q.n);
  const usedD = new Uint8Array(nD), usedN = new Uint8Array(nN);
  const out: MatchPair[] = [];
  for (const pr of pairs) {
    if (usedD[pr.d] || usedN[pr.n]) continue;
    const nextD = bestPd[pr.d] === pr.n ? best2d[pr.d]! : best1d[pr.d]!;
    const nextN = bestPn[pr.n] === pr.d ? best2n[pr.n]! : best1n[pr.n]!;
    if (pr.score - Math.max(nextD, nextN) < o.matchMargin - 1e-12) continue;
    usedD[pr.d] = 1; usedN[pr.n] = 1;
    out.push(pr);
  }
  return out;
}
