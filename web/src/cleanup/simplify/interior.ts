// Hidden interior elements: elements that no ray from outside the model can reach. For each element, sample points on its
// surface and shoot rays from them in many directions (a Fibonacci sphere, the same idea as the viewer's sightline
// sampling in algo/sightlines.ts, but checking for escape instead of occlusion). An element counts as hidden only when
// EVERY ray from EVERY sample point is blocked by another element, so a single gap (an open end, a door opening, a window)
// keeps it. Windows and other transparent classes never block. Pure: the caller supplies the ray caster.

import type { MeshData } from './types';
import { runChunked } from './types';
import type { ChunkOptions } from './types';

export interface RayHit {
  /** Element that owns the hit triangle. */
  id: number;
  /** Distance along the ray. */
  t: number;
}

export interface RayCaster {
  /** Nearest hit of the ray (both triangle sides count), or null when it leaves the model. */
  firstHit(ox: number, oy: number, oz: number, dx: number, dy: number, dz: number): RayHit | null;
}

export interface InteriorItem {
  id: number;
  ifcClass: string;
  /** World-space mesh of the element, or null (then it is never reported). */
  mesh: () => MeshData | null;
}

export interface InteriorOptions {
  /** Rays per sample point (default 24). */
  directions: number;
  /** Sample points per element (default 6). */
  samples: number;
  /** Classes that do not block sight (glazing, spaces, openings). */
  transparentClasses: readonly string[];
  /** Offset of ray origins from the surface, metres. */
  epsilon: number;
}

export const TRANSPARENT_CLASSES = ['IfcWindow', 'IfcSpace', 'IfcOpeningElement', 'IfcVirtualElement', 'IfcAnnotation', 'IfcSpatialZone'];

export function defaultInteriorOptions(): InteriorOptions {
  return { directions: 24, samples: 6, transparentClasses: TRANSPARENT_CLASSES, epsilon: 5e-4 };
}

/** n unit vectors spread evenly over the sphere. */
export function fibonacciDirections(n: number): Array<[number, number, number]> {
  const out: Array<[number, number, number]> = [];
  const golden = Math.PI * (3 - Math.sqrt(5));
  for (let i = 0; i < n; i++) {
    const y = 1 - (2 * (i + 0.5)) / n;
    const r = Math.sqrt(Math.max(0, 1 - y * y));
    const th = golden * i;
    out.push([Math.cos(th) * r, y, Math.sin(th) * r]);
  }
  return out;
}

export interface SurfaceSample {
  p: [number, number, number];
  n: [number, number, number];
}

/** Up to `count` points at triangle centroids, evenly strided over the triangle list, with the face normal. */
export function surfaceSamples(mesh: MeshData, count: number): SurfaceSample[] {
  const nt = Math.floor(mesh.indices.length / 3);
  const out: SurfaceSample[] = [];
  if (nt === 0 || count <= 0) return out;
  const n = Math.min(count, nt);
  const P = mesh.positions;
  for (let k = 0; k < n; k++) {
    const t = Math.min(nt - 1, Math.floor(((k + 0.5) * nt) / n));
    const a = mesh.indices[t * 3]!, b = mesh.indices[t * 3 + 1]!, c = mesh.indices[t * 3 + 2]!;
    const ux = P[b * 3]! - P[a * 3]!, uy = P[b * 3 + 1]! - P[a * 3 + 1]!, uz = P[b * 3 + 2]! - P[a * 3 + 2]!;
    const vx = P[c * 3]! - P[a * 3]!, vy = P[c * 3 + 1]! - P[a * 3 + 1]!, vz = P[c * 3 + 2]! - P[a * 3 + 2]!;
    let nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
    const l = Math.hypot(nx, ny, nz);
    if (l < 1e-18) continue;
    nx /= l; ny /= l; nz /= l;
    out.push({
      p: [(P[a * 3]! + P[b * 3]! + P[c * 3]!) / 3, (P[a * 3 + 1]! + P[b * 3 + 1]! + P[c * 3 + 1]!) / 3, (P[a * 3 + 2]! + P[b * 3 + 2]! + P[c * 3 + 2]!) / 3],
      n: [nx, ny, nz],
    });
  }
  return out;
}

/** True when a ray from the sample escapes the model (it reaches no blocking element). Self hits and glazing are passed through. */
function escapes(cast: RayCaster, self: number, s: SurfaceSample, d: [number, number, number], transparent: ReadonlySet<number>, eps: number): boolean {
  const side = s.n[0] * d[0] + s.n[1] * d[1] + s.n[2] * d[2] >= 0 ? 1 : -1;
  let ox = s.p[0] + side * s.n[0] * eps, oy = s.p[1] + side * s.n[1] * eps, oz = s.p[2] + side * s.n[2] * eps;
  for (let hop = 0; hop < 8; hop++) {
    const h = cast.firstHit(ox, oy, oz, d[0], d[1], d[2]);
    if (!h) return true;
    if (h.id !== self && !transparent.has(h.id)) return false;
    const t = h.t + eps;
    ox += d[0] * t; oy += d[1] * t; oz += d[2] * t;
  }
  return true; // too many pass-through hops: do not claim it is enclosed
}

/**
 * Ids of elements that every sampled ray finds enclosed. Runs in chunks so the page stays responsive; returns null when
 * aborted. `skip` ids are never reported (e.g. elements that are already hidden).
 */
export async function findHiddenInterior(
  items: readonly InteriorItem[],
  cast: RayCaster,
  opts: Partial<InteriorOptions> = {},
  chunk: ChunkOptions = {},
): Promise<number[] | null> {
  const o = { ...defaultInteriorOptions(), ...opts };
  const dirs = fibonacciDirections(Math.max(6, o.directions));
  const transparentIds = new Set<number>();
  for (const it of items) if (o.transparentClasses.includes(it.ifcClass)) transparentIds.add(it.id);
  const hidden: number[] = [];
  const ok = await runChunked(
    items,
    (it) => {
      if (transparentIds.has(it.id)) return; // never remove glazing on the strength of "enclosed"
      const mesh = it.mesh();
      if (!mesh) return;
      const samples = surfaceSamples(mesh, o.samples);
      if (samples.length === 0) return;
      for (const s of samples) for (const d of dirs) if (escapes(cast, it.id, s, d, transparentIds, o.epsilon)) return;
      hidden.push(it.id);
    },
    chunk,
  );
  return ok ? hidden.sort((a, b) => a - b) : null;
}
