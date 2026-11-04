// As-built deviation: distance from each cloud point to the nearest model surface, banded by a tolerance.
//
//   within tolerance (<= tol)        green
//   up to twice the tolerance        amber
//   beyond (<= max = 5 x tol)        red
//   further than max                 grey: not this element (clutter, other objects, a different model)
//
// The distance function is injected (the viewer uses the merged BVH's closestPointToPoint), so this module is
// pure and testable on a synthetic plane. computeDeviation yields to the event loop between time slices.

import type { CloudFrame } from './align';
import { bandOf } from './colour';

/** Distance to the nearest surface, or Infinity when none lies within `maxDist`. */
export type DistanceFn = (x: number, y: number, z: number, maxDist: number) => number;

export const MAX_FACTOR = 5;
export const DEFAULT_SAMPLE_CAP = 500_000;

export interface DeviationStats {
  /** Points measured. */
  sampled: number;
  /** Points within max = 5 x tolerance of a surface. */
  related: number;
  unrelated: number;
  /** Counts per band: within, amber, red, unrelated. */
  bands: [number, number, number, number];
  /** Share of related points within the tolerance, 0..1. */
  shareWithin: number;
  /** Share of all measured points within the tolerance, 0..1. */
  shareWithinOfAll: number;
  unrelatedShare: number;
  /** Mean, median and 95th percentile distance of the related points, metres. NaN when none. */
  mean: number;
  median: number;
  p95: number;
  tolerance: number;
  maxDistance: number;
  /** Per classification code (only when the cloud has classes). */
  byClass?: Record<number, { n: number; related: number; shareWithin: number; shareRed: number; median: number }>;
}

function pct(sorted: Float32Array, p: number): number {
  const n = sorted.length;
  if (!n) return NaN;
  const pos = (n - 1) * p;
  const i = Math.floor(pos);
  const f = pos - i;
  return i + 1 < n ? sorted[i]! * (1 - f) + sorted[i + 1]! * f : sorted[i]!;
}

/** Statistics of a distance array (Infinity / NaN count as unrelated). `classes` is parallel to `dist`. */
export function summarise(dist: Float32Array, tolerance: number, classes?: Uint8Array | null): DeviationStats {
  const n = dist.length;
  const max = MAX_FACTOR * tolerance;
  const bands: [number, number, number, number] = [0, 0, 0, 0];
  const rel = new Float32Array(n);
  let m = 0;
  let sum = 0;
  for (let i = 0; i < n; i++) {
    const b = bandOf(dist[i]!, tolerance);
    bands[b as 0 | 1 | 2 | 3]++;
    if (b < 3) {
      rel[m++] = dist[i]!;
      sum += dist[i]!;
    }
  }
  const sorted = rel.slice(0, m).sort();
  const stats: DeviationStats = {
    sampled: n,
    related: m,
    unrelated: bands[3],
    bands,
    shareWithin: m ? bands[0] / m : NaN,
    shareWithinOfAll: n ? bands[0] / n : NaN,
    unrelatedShare: n ? bands[3] / n : NaN,
    mean: m ? sum / m : NaN,
    median: pct(sorted, 0.5),
    p95: pct(sorted, 0.95),
    tolerance,
    maxDistance: max,
  };
  if (classes) {
    const groups = new Map<number, number[]>();
    for (let i = 0; i < n; i++) {
      const c = classes[i]!;
      let g = groups.get(c);
      if (!g) groups.set(c, (g = []));
      g.push(i);
    }
    stats.byClass = {};
    for (const [c, idx] of groups) {
      const d = new Float32Array(idx.length);
      let w = 0, r = 0, red = 0, k = 0;
      for (const i of idx) {
        const v = dist[i]!;
        const b = bandOf(v, tolerance);
        if (b < 3) { d[k++] = v; r++; }
        if (b === 0) w++;
        else if (b === 2) red++;
      }
      stats.byClass[c] = { n: idx.length, related: r, shareWithin: r ? w / r : NaN, shareRed: idx.length ? red / idx.length : NaN, median: pct(d.slice(0, k).sort(), 0.5) };
    }
  }
  return stats;
}

/** Evenly spread sample of at most `cap` indices out of `n` (all of them when n <= cap). */
export function sampleStride(n: number, cap: number): Uint32Array {
  const k = Math.min(n, cap);
  const out = new Uint32Array(k);
  if (k === n) { for (let i = 0; i < n; i++) out[i] = i; return out; }
  const step = n / k;
  for (let i = 0; i < k; i++) out[i] = Math.min(n - 1, Math.floor(i * step));
  return out;
}

export interface DeviationRun {
  /** Axis-mapped positions relative to the cloud origin (3 per point). */
  positions: Float32Array;
  frame: CloudFrame;
  /** Points to measure, indices into `positions`. */
  indices: Uint32Array;
  distance: DistanceFn;
  tolerance: number;
  /** Time slice before yielding, ms. */
  sliceMs?: number;
  onProgress?(f: number): void;
  isCancelled?(): boolean;
  yieldFn?(): Promise<void>;
}

const defaultYield = (): Promise<void> => new Promise((r) => setTimeout(r, 0));

/** Distances for `indices` (parallel array). Returns null when cancelled. */
export async function computeDeviation(run: DeviationRun): Promise<Float32Array | null> {
  const n = run.indices.length;
  const out = new Float32Array(n);
  const e = run.frame.matrix.elements;
  const p = run.positions;
  const max = MAX_FACTOR * run.tolerance;
  const base = run.sliceMs ?? 8;
  const y = run.yieldFn ?? defaultYield;
  let i = 0;
  let slice = base;
  let lastEnd = performance.now();
  while (i < n) {
    const t0 = performance.now();
    // Adaptive slice: when the time between our slices is long (a heavy frame was drawn in between), take a longer
    // slice so the check still makes progress; on a fast machine the gap is ~0 and slices stay at the base length.
    slice = Math.min(250, Math.max(base, (t0 - lastEnd) * 0.5));
    while (i < n) {
      const k = run.indices[i]! * 3;
      const gx = p[k]!, gy = p[k + 1]!, gz = p[k + 2]!;
      const d = run.distance(
        e[0]! * gx + e[4]! * gy + e[8]! * gz + e[12]!,
        e[1]! * gx + e[5]! * gy + e[9]! * gz + e[13]!,
        e[2]! * gx + e[6]! * gy + e[10]! * gz + e[14]!,
        max,
      );
      out[i++] = d;
      if ((i & 15) === 0 && performance.now() - t0 > slice) break;
    }
    lastEnd = performance.now();
    run.onProgress?.(i / n);
    if (i < n) {
      await y();
      if (run.isCancelled?.()) return null;
    }
  }
  return out;
}
