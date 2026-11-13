// Rays against section clipping (planes whose normal points to the KEPT half-space: section planes, the six planes of a section
// box, BCF clipping planes). Pure maths, no three.js: tested in tests/clip-ray.test.ts.
//
// A section removes the geometry on the far side of every plane, so a ray only sees the part of it inside the kept region (a
// convex polyhedron: the intersection of the half-spaces). That part is one interval [near, far] along the ray, found in closed
// form, and the BVH is asked for the first hit inside the interval only: geometry on the clipped-away side is never visited, and
// the ray lands on what the renderer draws (the remaining geometry, or the cap).
//
// A cap is the back face of a closed solid that the cut reveals (the renderer paints it flat). A ray that enters the kept region
// through a plane and first meets a back face of a closed element has hit the cap: the point is where the ray crosses that plane,
// the normal is the plane's (facing the ray origin), and the element is the cut element.

import type { Vec3 } from './model';
import type { ProbeHit, Ray3 } from './surface';

export interface Plane {
  /** Unit normal, pointing to the kept half-space. */
  normal: Vec3;
  /** Any point on the plane. */
  point: Vec3;
}

/** The planes with unit normals (the renderer already keeps them so; BCF planes may not be). Drops degenerate ones. */
export function unitPlanes(planes: ReadonlyArray<{ normal: ArrayLike<number>; point: ArrayLike<number> }> | null | undefined): Plane[] {
  const out: Plane[] = [];
  for (const p of planes ?? []) {
    const l = Math.hypot(p.normal[0]!, p.normal[1]!, p.normal[2]!);
    if (!(l > 1e-9)) continue;
    out.push({ normal: [p.normal[0]! / l, p.normal[1]! / l, p.normal[2]! / l], point: [p.point[0]!, p.point[1]!, p.point[2]!] });
  }
  return out;
}

/** Signed distance of a point from a plane, positive on the kept side. */
export function planeDistance(pl: Plane, p: Vec3): number {
  return pl.normal[0] * (p[0] - pl.point[0]) + pl.normal[1] * (p[1] - pl.point[1]) + pl.normal[2] * (p[2] - pl.point[2]);
}

/** True when the point is on the kept side of every plane (nothing to clip: true). */
export function keptPoint(planes: ReadonlyArray<Plane>, p: Vec3): boolean {
  for (const pl of planes) if (planeDistance(pl, p) < 0) return false;
  return true;
}

export interface ClipInterval {
  /** Start of the visible part of the ray (distance from the origin, 0 or more). */
  near: number;
  /** End of it (`max` at most). */
  far: number;
  /** Index of the plane the ray enters the kept region through at `near` (the cap plane); -1 when it starts inside. */
  enter: number;
}

/**
 * The part of the ray `o + t d` (unit d) with 0 <= t <= `max` that lies in the kept region of all planes; null when none of it does.
 */
export function clipInterval(planes: ReadonlyArray<Plane>, o: Vec3, d: Vec3, max = Infinity): ClipInterval | null {
  let near = 0;
  let far = max;
  let enter = -1;
  for (let i = 0; i < planes.length; i++) {
    const pl = planes[i]!;
    const s0 = planeDistance(pl, o);
    const dn = pl.normal[0] * d[0] + pl.normal[1] * d[1] + pl.normal[2] * d[2];
    if (Math.abs(dn) < 1e-12) {
      if (s0 < 0) return null; // parallel to the plane and on the removed side
      continue;
    }
    const t = -s0 / dn;
    if (dn > 0) {
      // Kept for t >= tp.
      if (t > near) { near = t; enter = i; }
    } else if (t < far) far = t; // kept for t <= tp
    if (near > far) return null;
  }
  return { near, far, enter };
}

/** A first hit inside a range, before the normal is turned to face the ray (the geometric normal of the triangle). */
export interface RangeHit {
  point: Vec3;
  /** Unit normal of the hit triangle, either orientation. */
  normal: Vec3;
  element: number;
  distance: number;
}

/** The first hit of the ray inside `[near, far]` (view modes and hidden elements already skipped), or null. */
export type RangeProbe = (ray: Ray3, near: number, far: number) => RangeHit | null;

export interface ClipCast {
  planes: ReadonlyArray<Plane>;
  /** Caps are drawn (the renderer paints them when the camera looks in from the cut side). */
  caps: boolean;
  /** Per-element closed-solid flag: only closed solids get a cap. */
  closed: (element: number) => boolean;
}

const facing = (n: Vec3, d: Vec3): Vec3 => (n[0] * d[0] + n[1] * d[1] + n[2] * d[2] > 0 ? [-n[0], -n[1], -n[2]] : n);

/**
 * `probe` for a ray with clipping applied: the first visible surface, or the cap. Without planes it is the plain probe over
 * the whole ray. The returned normal faces the ray origin.
 */
export function castClipped(ray: Ray3, probe: RangeProbe, clip: ClipCast | null): ProbeHit | null {
  const planes = clip?.planes ?? [];
  const iv = planes.length ? clipInterval(planes, ray.o, ray.d) : { near: 0, far: Infinity, enter: -1 };
  if (!iv) return null;
  const h = probe(ray, iv.near, iv.far);
  if (!h) return null;
  const back = h.normal[0] * ray.d[0] + h.normal[1] * ray.d[1] + h.normal[2] * ray.d[2] > 0;
  if (clip && iv.enter >= 0 && iv.near > 0 && back && clip.caps && clip.closed(h.element)) {
    const pl = planes[iv.enter]!;
    const t = iv.near;
    return { point: [ray.o[0] + ray.d[0] * t, ray.o[1] + ray.d[1] * t, ray.o[2] + ray.d[2] * t], normal: facing(pl.normal, ray.d), element: h.element, distance: t };
  }
  return { point: h.point, normal: facing(h.normal, ray.d), element: h.element, distance: h.distance };
}
