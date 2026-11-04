// Sweep reveal: a plane travels from the camera side through the occluders along the view axis, and
// the ghosts behind it stay as they were until it reaches them. The shaders (render/shaders.ts)
// evaluate the same band and peel functions per fragment; this module holds the pure maths, the plane
// timeline and the hold-alpha table so they can be tested without a GPU.

import { Box3, Vector3 } from 'three';
import { clamp01 } from './easing';

export const DEFAULT_SWEEP_MS = 1000;
/** Width of the bright band at the plane, metres. */
export const DEFAULT_BAND_M = 0.15;
/** The peel (extra transparency behind the front) relaxes to nothing over this many band widths. */
export const PEEL_BANDS = 4;

export type RevealMode = 'stagger' | 'sweep' | 'both';

export function usesSweep(mode: RevealMode): boolean {
  return mode === 'sweep' || mode === 'both';
}
export function usesStagger(mode: RevealMode): boolean {
  return mode === 'stagger' || mode === 'both';
}

function glslSmoothstep(e0: number, e1: number, x: number): number {
  const t = clamp01((x - e0) / (e1 - e0));
  return t * t * (3 - 2 * t);
}

/** Signed distance of point p from the plane (normal n, offset d): n.p - d. <= 0: the plane has passed p. */
export function planeDistance(n: Vector3, offset: number, p: Vector3): number {
  return n.dot(p) - offset;
}

/**
 * Bright band at signed distance `s`: 1 at the plane, falling to 0 over `band` metres on the side the
 * plane has not reached, and over a quarter of that on the side it has passed (a thin rim).
 */
export function sweepBand(s: number, band: number): number {
  return s > 0 ? 1 - glslSmoothstep(0, band, s) : 1 - glslSmoothstep(0, 0.25 * band, -s);
}

/** Extra transparency just behind the front: 1 at the plane, 0 beyond PEEL_BANDS band widths; 0 ahead of the plane. */
export function sweepPeel(s: number, band: number): number {
  return s <= 0 ? 1 - glslSmoothstep(0, PEEL_BANDS * band, -s) : 0;
}

/**
 * Alpha of a ghost fragment at signed distance `s` during a sweep. `real` is the element's real
 * (smoothed) alpha, `hold` the alpha it had before the selection, `alphaMin` the ghosting floor.
 * Ahead of the plane: `hold`. Behind it: `real`, pulled toward alphaMin by up to 60% right at the
 * front. (The Fresnel boost is applied on top of this in the shader.)
 */
export function sweepAlpha(s: number, band: number, real: number, hold: number, alphaMin: number): number {
  if (s > 0) return hold;
  return Math.min(real, real + (alphaMin - real) * 0.6 * sweepPeel(s, band));
}

/** Range of plane offsets that covers every box along `normal`: [first contact - 0, last contact + peel + band]. */
export function sweepRange(boxes: readonly Box3[], normal: Vector3, band: number): { start: number; end: number } {
  let lo = Infinity;
  let hi = -Infinity;
  const c = new Vector3();
  const h = new Vector3();
  for (const b of boxes) {
    if (b.isEmpty()) continue;
    b.getCenter(c);
    b.getSize(h).multiplyScalar(0.5);
    const mid = normal.dot(c);
    const ext = Math.abs(normal.x) * h.x + Math.abs(normal.y) * h.y + Math.abs(normal.z) * h.z;
    lo = Math.min(lo, mid - ext);
    hi = Math.max(hi, mid + ext);
  }
  if (!Number.isFinite(lo)) return { start: 0, end: 0 };
  // Past the last box by the whole peel zone and the band, so the hand-over to the normal alphas is seamless.
  return { start: lo - 0.01, end: hi + (PEEL_BANDS + 1) * band };
}

/** Min and max of dot(normal, v) over the vertices `first .. first + count - 1` of an xyz-interleaved position array (merged into `acc`). */
export function projectionExtent(
  positions: ArrayLike<number>,
  first: number,
  count: number,
  normal: Vector3,
  acc: { lo: number; hi: number } = { lo: Infinity, hi: -Infinity },
): { lo: number; hi: number } {
  const nx = normal.x;
  const ny = normal.y;
  const nz = normal.z;
  const end = (first + count) * 3;
  for (let i = first * 3; i < end; i += 3) {
    const d = nx * positions[i]! + ny * positions[i + 1]! + nz * positions[i + 2]!;
    if (d < acc.lo) acc.lo = d;
    if (d > acc.hi) acc.hi = d;
  }
  return acc;
}

/**
 * Plane offsets that cover geometry whose projection onto the normal spans [lo, hi]: from just before
 * the first vertex to past the last by the whole peel zone and the band, so the hand-over to the normal
 * alphas is seamless. Exact when lo/hi come from vertices (projectionExtent), unlike the box version.
 */
export function sweepRangeFromExtent(lo: number, hi: number, band: number): { start: number; end: number } {
  if (!Number.isFinite(lo) || !Number.isFinite(hi)) return { start: 0, end: 0 };
  return { start: lo - 0.01, end: hi + (PEEL_BANDS + 1) * band };
}

/** The plane's travel in time. */
export class PlaneSweep {
  normal = new Vector3(0, 0, -1);
  start = 0;
  end = 0;
  durationMs = DEFAULT_SWEEP_MS;
  private t0 = Number.NaN;
  private active = false;

  get running(): boolean {
    return this.active;
  }

  begin(now: number, normal: Vector3, start: number, end: number, durationMs = DEFAULT_SWEEP_MS): void {
    this.normal.copy(normal).normalize();
    this.start = start;
    this.end = end;
    this.durationMs = Math.max(1, durationMs);
    this.t0 = now;
    this.active = true;
  }

  stop(): void {
    this.active = false;
  }

  /** 0..1 progress at clock time `now`. Linear: the plane already has to cross empty space before the first occluder. */
  progress(now: number): number {
    if (!this.active) return 1;
    return clamp01((now - this.t0) / this.durationMs);
  }

  /** Plane offset at `now`. */
  offsetAt(now: number): number {
    return this.start + (this.end - this.start) * this.progress(now);
  }

  /** True once `now` is past the end of the travel. */
  doneAt(now: number): boolean {
    return !this.active || now - this.t0 >= this.durationMs;
  }
}

/** Unit direction from the camera to the focus centre (falls back to -Z when they coincide). */
export function sweepNormal(camera: Vector3, focus: Vector3, out = new Vector3()): Vector3 {
  out.subVectors(focus, camera);
  if (out.lengthSq() < 1e-12) return out.set(0, 0, -1);
  return out.normalize();
}

/**
 * Hold table: for each id, the alpha it had before the selection (clamped to a small positive value,
 * 0 means "not in the sweep" in the shader).
 */
export function buildHold(n: number, ids: Iterable<number>, alpha: ArrayLike<number>): Float32Array {
  const hold = new Float32Array(n);
  for (const id of ids) {
    const a = alpha[id];
    if (a === undefined || a < 0) continue;
    hold[id] = Math.max(a, 0.001);
  }
  return hold;
}
