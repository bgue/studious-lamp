// Point budget. Uniform random sampling without replacement (Knuth's selection sampling, "Algorithm S"):
//   - exact: always returns min(budget, n) points, in original order;
//   - O(n), one pass, no spatial structure, a few milliseconds per million points;
//   - deterministic for a given seed (mulberry32), so tests and repeated loads agree;
//   - an unbiased sample, so shares and percentiles measured on it estimate those of the full cloud.
// Trade-off against a voxel grid: random sampling keeps the density of the scan (dense near the scanner, sparse far
// away) while a voxel grid evens it out and keeps thin features, but needs a cell size search to hit a budget and is
// an order of magnitude slower. For an as-built check the unbiased sample wins; the budget slider is the density knob.

import type { PointCloudData, Shown } from './types';

export function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Indices (ascending) of `k` points chosen uniformly from `n`. */
export function sampleIndices(n: number, k: number, seed = 1): Uint32Array {
  if (k >= n) {
    const all = new Uint32Array(n);
    for (let i = 0; i < n; i++) all[i] = i;
    return all;
  }
  const out = new Uint32Array(k);
  const rnd = mulberry32(seed);
  let chosen = 0;
  for (let i = 0; i < n && chosen < k; i++) {
    if (rnd() * (n - i) < k - chosen) out[chosen++] = i;
  }
  return out;
}

/** The input arrays themselves when the cloud already fits the budget (no copy), else a copy of the sample. */
export function decimate(data: PointCloudData | Shown, budget: number, seed = 1): Shown {
  const n = data.count;
  const b = Math.max(1, Math.floor(budget));
  if (n <= b) {
    return { count: n, positions: data.positions, colors: data.colors, intensity: data.intensity, classification: data.classification };
  }
  const idx = sampleIndices(n, b, seed);
  const out: Shown = { count: b, positions: new Float32Array(b * 3) };
  if (data.colors) out.colors = new Uint8Array(b * 3);
  if (data.intensity) out.intensity = new Float32Array(b);
  if (data.classification) out.classification = new Uint8Array(b);
  const p = data.positions;
  for (let k = 0; k < b; k++) {
    const i = idx[k]!;
    out.positions[k * 3] = p[i * 3]!;
    out.positions[k * 3 + 1] = p[i * 3 + 1]!;
    out.positions[k * 3 + 2] = p[i * 3 + 2]!;
    if (out.colors) {
      out.colors[k * 3] = data.colors![i * 3]!;
      out.colors[k * 3 + 1] = data.colors![i * 3 + 1]!;
      out.colors[k * 3 + 2] = data.colors![i * 3 + 2]!;
    }
    if (out.intensity) out.intensity[k] = data.intensity![i]!;
    if (out.classification) out.classification[k] = data.classification![i]!;
  }
  return out;
}
