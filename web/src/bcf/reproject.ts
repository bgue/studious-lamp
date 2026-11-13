// Following reshaped elements: a surface-attached outline stores its points in the local frame of each element (the offset
// from the bounds centre, see SurfacePoint.l), so it follows an element that a revised model MOVES. An element that is
// RESHAPED (a longer wall, a re-routed pipe) has a new bounds centre and the outline would float off the surface. This module
// projects every stored point back onto the element's current surface. Pure: the surface comes in through ElementProbe (the
// viewer backs it with the per-element BVH, src/markup/reprojectScene.ts). Tested in tests/markup-reproject.test.ts.
//
// Where a point is expected: with the stored bounds (the fingerprint), per axis: a side of the element that did not move keeps
// the point where it was (a wall lengthened at one end), both sides moved by the same amount move it with them (a moved
// element), anything else stretches it with the bounds. That is the only start. Without a fingerprint (older data) the rigid
// follow is tried first (current bounds centre plus the stored offset, the old behaviour), then the stored IFC point. From each
// start a ray is cast along the stored surface normal (the authoring camera direction for data from before
// normals were stored) onto the element's own triangles; when that misses, the nearest point of the element's triangles within
// the tolerance is used. The start that lands closest wins (the first one when it lands cleanly).
// When more than `REPROJECT.maxLost` of the points cannot land, the outline is detached: view-locked and flagged, not drawn
// floating. An element that moved by more than `moveMin` metres or `moveRel` times its size is treated as replaced, so a
// markup does not chase it across the building.

import type { Vec3 } from './model';
import type { Box6, SurfaceData, SurfacePoint } from './attach';

export interface ProbeHit {
  point: Vec3;
  /** Unit normal facing the side the ray came from (or the query point). */
  normal: Vec3;
  distance: number;
}

/** The current model as the re-projection sees it. All points in the IFC frame. */
export interface ElementProbe {
  /** Current bounds of the element, null when the model does not have it. */
  bounds(guid: string): Box6 | null;
  /** First hit of a ray on the triangles of this element only (both sides). */
  cast(guid: string, origin: Vec3, dir: Vec3): ProbeHit | null;
  /** Nearest point of the element's triangles to `p`. */
  nearest(guid: string, p: Vec3): ProbeHit | null;
}

/** Thresholds, documented in docs-features/markup.md ("Reshaped elements"). */
export const REPROJECT = {
  /** More than this share of points that cannot land: the outline is detached. */
  maxLost: 0.3,
  /** Landing tolerance: this share of the element diagonal, between `tolMin` and `tolMax` metres. */
  tolRel: 0.03,
  tolMin: 0.05,
  tolMax: 0.3,
  /** An element whose centre moved further than max(moveMin, moveRel x its old diagonal) counts as replaced. */
  moveMin: 3,
  moveRel: 1.5,
  /** Bounds that differ by less than this (m) are the same bounds. */
  boundsEps: 0.005,
  /** A point that moved less than this (m) is left where it was. */
  pointEps: 0.002,
  /** Lift used for data without a stored `g` (m). */
  defaultLift: 0.01,
} as const;

const add = (a: Vec3, b: Vec3): Vec3 => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
const sub = (a: Vec3, b: Vec3): Vec3 => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const mul = (a: Vec3, k: number): Vec3 => [a[0] * k, a[1] * k, a[2] * k];
const len = (a: Vec3): number => Math.hypot(a[0], a[1], a[2]);
const dot = (a: Vec3, b: Vec3): number => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const unit = (a: Vec3): Vec3 => {
  const l = len(a);
  return l > 1e-12 ? mul(a, 1 / l) : [0, 0, 1];
};
const r4 = (x: number): number => Math.round(x * 1e4) / 1e4;
const round3 = (v: Vec3): Vec3 => [r4(v[0]), r4(v[1]), r4(v[2])];

export const boxCentre = (b: Box6): Vec3 => [(b[0] + b[3]) / 2, (b[1] + b[4]) / 2, (b[2] + b[5]) / 2];
export const boxDiagonal = (b: Box6): number => Math.hypot(b[3] - b[0], b[4] - b[1], b[5] - b[2]);

/** Where the point `p` of an element with bounds `was` is expected to be now that the element has bounds `now` (see the file header). */
export function expectedPoint(p: Vec3, was: Box6, now: Box6, eps: number = REPROJECT.boundsEps): Vec3 {
  const out: Vec3 = [p[0], p[1], p[2]];
  for (let k = 0; k < 3; k++) {
    const dmin = now[k]! - was[k]!;
    const dmax = now[k + 3]! - was[k + 3]!;
    if (Math.abs(dmin) <= eps || Math.abs(dmax) <= eps) continue; // a side stayed: the point stays
    if (Math.abs(dmin - dmax) <= eps) { out[k] = p[k]! + dmin; continue; } // moved as a whole
    const size = was[k + 3]! - was[k]!;
    out[k] = size > eps ? now[k]! + ((p[k]! - was[k]!) / size) * (now[k + 3]! - now[k]!) : p[k]! + (dmin + dmax) / 2;
  }
  return out;
}

/** True when two bounds are the same box (within `boundsEps`). */
export function sameBounds(a: Box6, b: Box6, eps: number = REPROJECT.boundsEps): boolean {
  for (let i = 0; i < 6; i++) if (Math.abs(a[i]! - b[i]!) > eps) return false;
  return true;
}

/**
 * True when the targets of a surface differ from the fingerprint stored with it: an element is gone or has other bounds.
 * Data without a fingerprint never differs (nothing to compare; a revised model re-projects regardless).
 */
export function targetsChanged(s: SurfaceData, probe: ElementProbe): boolean {
  if (!s.fp) return false;
  for (let i = 0; i < s.guids.length; i++) {
    const was = s.fp[i];
    if (!was) continue;
    const now = probe.bounds(s.guids[i]!);
    if (!now || !sameBounds(was, now)) return true;
  }
  return false;
}

export interface ReprojectResult {
  /** `detached`: too many points cannot land, the outline is view-locked and flagged. */
  state: 'ok' | 'detached';
  /** The points that moved; absent when nothing moved (or detached). */
  surface?: SurfaceData;
  total: number;
  /** Points that landed on the current surface. */
  landed: number;
  /** Targets the model does not have. */
  missing: string[];
  reason: string;
}

interface Landing {
  point: Vec3;
  normal: Vec3;
  /** Distance from the start position. */
  disp: number;
}

/** Project one start position `c` (lifted by `g` along `n`) onto the element. */
function land(probe: ElementProbe, guid: string, c: Vec3, n: Vec3, g: number, tol: number): Landing | null {
  // From `tol` above the point, along -n: unchanged surface is hit after tol + g.
  const origin = add(c, mul(n, tol));
  const hit = probe.cast(guid, origin, mul(n, -1));
  let best: Landing | null = null;
  if (hit) {
    const nh = dot(hit.normal, n) >= 0 ? hit.normal : mul(hit.normal, -1);
    const point = add(hit.point, mul(nh, g));
    const disp = len(sub(point, c));
    if (disp <= tol + g) best = { point, normal: nh, disp };
  }
  if (!best) {
    const nr = probe.nearest(guid, c);
    if (nr && nr.distance <= tol + g) {
      const side = sub(c, nr.point);
      const nh = dot(nr.normal, side) >= 0 ? nr.normal : mul(nr.normal, -1);
      const point = add(nr.point, mul(nh, g));
      best = { point, normal: nh, disp: len(sub(point, c)) };
    }
  }
  return best;
}

/**
 * Project the points of a surface onto the current surfaces of their elements. `fallbackDir`: the authoring camera direction
 * (IFC frame), the cast direction for points without a stored normal.
 */
export function reprojectSurface(s: SurfaceData, probe: ElementProbe, o: { fallbackDir?: Vec3 } = {}): ReprojectResult {
  const total = s.pts.length;
  const now = s.guids.map((g) => probe.bounds(g));
  const missing = s.guids.filter((_g, i) => !now[i]);
  const camN: Vec3 | null = o.fallbackDir ? mul(unit(o.fallbackDir), -1) : null;
  const out: SurfacePoint[] = [];
  let landed = 0;
  let moved = false;
  // Replaced elements: moved further than they are big.
  const replaced = s.guids.map((_g, i) => {
    const b = now[i];
    const was = s.fp?.[i];
    if (!b || !was) return false;
    return len(sub(boxCentre(b), boxCentre(was))) > Math.max(REPROJECT.moveMin, REPROJECT.moveRel * boxDiagonal(was));
  });
  for (const sp of s.pts) {
    const guid = s.guids[sp.e]!;
    const cur = now[sp.e] ?? null;
    if (!cur) { out.push(sp); continue; }
    const tol = Math.min(REPROJECT.tolMax, Math.max(REPROJECT.tolMin, REPROJECT.tolRel * boxDiagonal(cur)));
    const n = sp.n ? unit(sp.n) : camN;
    const g = sp.g ?? REPROJECT.defaultLift;
    const centre = boxCentre(cur);
    // Starts, in order of preference.
    const was = s.fp?.[sp.e] ?? null;
    const starts: Vec3[] = [];
    const push = (c: Vec3): void => { if (!starts.some((x) => len(sub(x, c)) < 1e-6)) starts.push(c); };
    if (was) {
      // The fingerprint says how the element changed: the expected place is the only start (a replaced element: where it was).
      push(replaced[sp.e] ? sp.p : expectedPoint(sp.p, was, cur));
    } else {
      // Older data: the rigid follow, as the layout always did, then the stored point.
      if (sp.l) push(add(centre, sp.l));
      push(sp.p);
    }
    let best: Landing | null = null;
    if (n) {
      for (const c of starts) {
        const l = land(probe, guid, c, n, g, tol);
        if (l && (!best || l.disp < best.disp)) best = l;
        if (best && best.disp <= tol * 0.25) break; // landed cleanly: the earlier start is the better guess
      }
    } else {
      // No normal and no camera: only the nearest point of the triangles.
      for (const c of starts) {
        const nr = probe.nearest(guid, c);
        if (nr && nr.distance <= tol + g && (!best || nr.distance < best.disp)) best = { point: add(nr.point, mul(nr.normal, g)), normal: nr.normal, disp: nr.distance };
      }
    }
    if (!best) {
      // Did not land: keep the rigid follow (or the stored point); it counts as lost.
      const at = starts[0] ?? sp.p;
      out.push({ ...sp, p: round3(at), l: round3(sub(at, centre)) });
      if (len(sub(at, sp.p)) > REPROJECT.pointEps) moved = true;
      continue;
    }
    landed++;
    const p = round3(best.point);
    if (len(sub(p, sp.p)) > REPROJECT.pointEps) moved = true;
    const np: SurfacePoint = { e: sp.e, p, l: round3(sub(p, centre)), n: round3(best.normal) };
    if (sp.g !== undefined) np.g = sp.g;
    out.push(np);
  }
  const lost = total - landed;
  if (!total || lost / total > REPROJECT.maxLost) {
    const why = missing.length ? `${missing.length} target element${missing.length === 1 ? '' : 's'} missing` : `${lost} of ${total} points do not land on the surface`;
    return { state: 'detached', total, landed, missing, reason: why };
  }
  const base: SurfaceData = { guids: [...s.guids], pts: out, closed: s.closed, fp: now.map((b) => (b ? ([...b] as Box6) : null)) };
  return { state: 'ok', ...(moved || targetsDiffer(s, now) ? { surface: base } : {}), total, landed, missing, reason: moved ? 'points moved onto the current surface' : 'surface unchanged' };
}

function targetsDiffer(s: SurfaceData, now: ReadonlyArray<Box6 | null>): boolean {
  if (!s.fp) return false;
  return s.fp.some((was, i) => !!was && !!now[i] && !sameBounds(was, now[i]!));
}
