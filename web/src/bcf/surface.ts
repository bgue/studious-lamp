// Surface projection and attachment inference for a finished shape. Pure: rays and a probe come in, an Attachment goes out
// (the viewer supplies the BVH probe, tests a box scene). Tested in tests/markup-attach.test.ts.
//
// The stroke (a path in canvas pixels) is densified, a ray is cast through every point, and the hits are cleaned:
// misses, and short runs that jump to a far surface across a silhouette (a depth discontinuity), are moved onto the surface
// of the nearest good hit along the stroke (the point stays on its own ray, so the authored view does not change). When
// more than `MAX_BAD` of the points need that, the stroke does not project cleanly and surface mode is not used.

import { dirViewerToIfc, viewerToIfc } from './model';
import type { Vec3 } from './model';
import { cleanAttachment } from './attach';
import type { Attachment, SurfaceData, SurfacePoint } from './attach';

export interface Ray3 {
  /** Viewer frame. */
  o: Vec3;
  /** Unit direction. */
  d: Vec3;
}
export interface ProbeHit {
  point: Vec3;
  /** Unit normal facing the ray origin. */
  normal: Vec3;
  /** Element id of the viewer. */
  element: number;
  distance: number;
}
export type Probe = (r: Ray3) => ProbeHit | null;

/** Thresholds, documented in docs-features/markup.md. */
export const SURFACE = {
  /** Pixels between rays along a stroke. */
  step: 14,
  /** At most this many rays along the outline. */
  maxPath: 320,
  /** At most this many rays inside a closed outline. */
  maxInterior: 140,
  /** More than this fraction of failed points: no surface mode. */
  maxBad: 0.3,
  /** A run of fewer hits than this between two jumps is a silhouette spike. */
  minRun: 3,
  /** Share of the points that must land on at most `fewElements` elements for `surface`. */
  surfaceShare: 0.7,
  fewElements: 5,
  /** Region: at least this many distinct elements inside, and this much depth spread (m). */
  regionElements: 4,
  regionSpread: 0.15,
} as const;

const sub = (a: Vec3, b: Vec3): Vec3 => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const dot = (a: Vec3, b: Vec3): number => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];

// ---------------------------------------------------------------- paths in pixels

/** Insert points so that no segment is longer than `step` (open or closed flat path); then thin to `max` points. */
export function densifyPath(p: ReadonlyArray<number>, closed: boolean, step: number = SURFACE.step, max: number = SURFACE.maxPath): number[] {
  const n = p.length / 2;
  if (n < 2) return Array.from(p);
  const out: number[] = [];
  const last = closed ? n : n - 1;
  for (let i = 0; i < last; i++) {
    const j = (i + 1) % n;
    const x0 = p[2 * i]!, y0 = p[2 * i + 1]!, x1 = p[2 * j]!, y1 = p[2 * j + 1]!;
    const k = Math.max(1, Math.ceil(Math.hypot(x1 - x0, y1 - y0) / step));
    for (let s = 0; s < k; s++) out.push(x0 + ((x1 - x0) * s) / k, y0 + ((y1 - y0) * s) / k);
  }
  if (!closed) out.push(p[2 * (n - 1)]!, p[2 * (n - 1) + 1]!);
  const m = out.length / 2;
  if (m <= max) return out;
  const thin: number[] = [];
  for (let i = 0; i < max; i++) {
    const k = Math.min(m - 1, Math.round((i * (m - 1)) / (max - 1)));
    thin.push(out[2 * k]!, out[2 * k + 1]!);
  }
  return thin;
}

function inside(x: number, y: number, poly: ReadonlyArray<number>): boolean {
  let c = false;
  const n = poly.length / 2;
  for (let i = 0, j = n - 1; i < n; j = i++) {
    const xi = poly[2 * i]!, yi = poly[2 * i + 1]!, xj = poly[2 * j]!, yj = poly[2 * j + 1]!;
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) c = !c;
  }
  return c;
}

/** A grid of sample points inside a closed flat polygon, at most `max` of them. */
export function interiorSamples(poly: ReadonlyArray<number>, max: number = SURFACE.maxInterior): number[] {
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (let i = 0; i < poly.length; i += 2) { x0 = Math.min(x0, poly[i]!); x1 = Math.max(x1, poly[i]!); y0 = Math.min(y0, poly[i + 1]!); y1 = Math.max(y1, poly[i + 1]!); }
  const w = x1 - x0, h = y1 - y0;
  if (!(w > 4 && h > 4)) return [];
  const cell = Math.max(6, Math.sqrt((w * h) / max));
  const out: number[] = [];
  for (let y = y0 + cell / 2; y < y1; y += cell) for (let x = x0 + cell / 2; x < x1; x += cell) if (inside(x, y, poly)) out.push(x, y);
  return out;
}

// ---------------------------------------------------------------- casting and cleaning

export function castPath(path: ReadonlyArray<number>, rayAt: (x: number, y: number) => Ray3 | null, probe: Probe): Array<{ ray: Ray3; hit: ProbeHit | null } | null> {
  const out: Array<{ ray: Ray3; hit: ProbeHit | null } | null> = [];
  for (let i = 0; i < path.length; i += 2) {
    const ray = rayAt(path[i]!, path[i + 1]!);
    out.push(ray ? { ray, hit: probe(ray) } : null);
  }
  return out;
}

export interface CleanPoint {
  point: Vec3;
  normal: Vec3;
  element: number;
  distance: number;
  /** Moved onto a neighbour's surface (a miss or a silhouette spike). */
  snapped: boolean;
}

export interface Cleaned {
  pts: CleanPoint[];
  /** Fraction of the points that were misses or spikes. */
  bad: number;
}

const coplanar = (pa: Vec3, na: Vec3, pb: Vec3, tol: number): boolean => Math.abs(dot(na, sub(pb, pa))) <= tol;

/** Clean the hits of a path: see the file header. Returns null when there is not one good run. */
export function cleanHits(cast: ReadonlyArray<{ ray: Ray3; hit: ProbeHit | null } | null>, closed: boolean): Cleaned | null {
  const n = cast.length;
  if (n < 2) return null;
  const hit = (i: number): ProbeHit | null => cast[i]?.hit ?? null;
  // Runs of hits without a miss or a depth jump between neighbours.
  const runId = new Array<number>(n).fill(-1);
  const runLen: number[] = [];
  let cur = -1;
  for (let i = 0; i < n; i++) {
    const h = hit(i);
    if (!h) { cur = -1; continue; }
    const p = i > 0 ? hit(i - 1) : null;
    let jump = !p;
    if (p) {
      const dd = Math.abs(h.distance - p.distance);
      const thr = Math.max(0.25, 0.2 * Math.min(h.distance, p.distance));
      const tol = Math.max(0.02, 0.01 * Math.min(h.distance, p.distance));
      jump = dd > thr && !(coplanar(p.point, p.normal, h.point, tol) || coplanar(h.point, h.normal, p.point, tol));
    }
    if (jump || cur < 0) { cur = runLen.length; runLen.push(0); }
    runId[i] = cur;
    runLen[cur]!++;
  }
  const good = runId.map((r) => r >= 0 && runLen[r]! >= SURFACE.minRun);
  const goodIdx: number[] = [];
  for (let i = 0; i < n; i++) if (good[i]) goodIdx.push(i);
  if (!goodIdx.length) return null;
  const pts: CleanPoint[] = [];
  let bad = 0;
  for (let i = 0; i < n; i++) {
    const h = hit(i);
    if (good[i] && h) { pts.push({ point: h.point, normal: h.normal, element: h.element, distance: h.distance, snapped: false }); continue; }
    bad++;
    // Nearest good hit along the stroke (round the corner of a closed one).
    let best = -1, bd = Infinity;
    for (const j of goodIdx) {
      let d = Math.abs(i - j);
      if (closed) d = Math.min(d, n - d);
      if (d < bd) { bd = d; best = j; }
    }
    const g = hit(best)!;
    const ray = cast[i]?.ray;
    let point = g.point;
    let distance = g.distance;
    if (ray) {
      const den = dot(g.normal, ray.d);
      if (Math.abs(den) > 0.15) {
        const t = dot(g.normal, sub(g.point, ray.o)) / den;
        if (t > 0) { point = [ray.o[0] + ray.d[0] * t, ray.o[1] + ray.d[1] * t, ray.o[2] + ray.d[2] * t]; distance = t; }
      }
    }
    pts.push({ point, normal: g.normal, element: g.element, distance, snapped: true });
  }
  return { pts, bad: bad / n };
}

// ---------------------------------------------------------------- inference

/** Shape kinds drawn as a closed outline with an inside (region candidates). */
export const BOX_LIKE = ['cloud', 'rect', 'ellipse', 'polygon', 'highlightBox'] as const;
export const LINE_LIKE = ['line', 'arrow', 'pen', 'polyline', 'highlight'] as const;
export const isBoxLike = (k: string): boolean => (BOX_LIKE as readonly string[]).includes(k);

export interface InferInput {
  kind: string;
  /** The drawn path in canvas pixels, flat, not yet densified; closed for box-like kinds. */
  path: ReadonlyArray<number>;
  closed: boolean;
  rayAt: (x: number, y: number) => Ray3 | null;
  probe: Probe;
  /** GlobalId of an element id (undefined: no GlobalId, the point cannot follow it). */
  guidOf: (id: number) => string | undefined;
  /** Bounds centre of an element id, viewer frame. */
  centreOf: (id: number) => Vec3 | null;
  shift: Vec3;
  /** A measurement or penetration under the cursor or the centre of the shape (decided by the caller from the screen). */
  hint?: { measurement?: NonNullable<Attachment['measurement']>; penetration?: NonNullable<Attachment['penetration']> };
  /** Lift of the path off the surface along the normal (m); default 0.2% of the distance, 5 mm to 5 cm. */
  lift?: (distance: number) => number;
}

export interface InferInfo {
  rays: number;
  bad: number;
  elements: number;
  topShare: number;
  interiorHits: number;
  interiorElements: number;
  spread: number;
  reason: string;
}

export interface Inference {
  attach: Attachment;
  info: InferInfo;
}

const defaultLift = (d: number): number => Math.min(0.05, Math.max(0.005, d * 0.002));

/** The surface data of cleaned points: guids by use, IFC points, local offsets. */
export function toSurfaceData(c: Cleaned, o: Pick<InferInput, 'guidOf' | 'centreOf' | 'shift' | 'lift'>, closed: boolean): SurfaceData | null {
  const guids: string[] = [];
  const idx = new Map<string, number>();
  const pts: SurfacePoint[] = [];
  const lift = o.lift ?? defaultLift;
  for (const q of c.pts) {
    const g = o.guidOf(q.element);
    if (!g) continue;
    let e = idx.get(g);
    if (e === undefined) { e = guids.length; guids.push(g); idx.set(g, e); }
    const l = lift(q.distance);
    const v: Vec3 = [q.point[0] + q.normal[0] * l, q.point[1] + q.normal[1] * l, q.point[2] + q.normal[2] * l];
    const r = (x: number): number => Math.round(x * 1e4) / 1e4;
    const ifc = viewerToIfc(v, o.shift).map(r) as Vec3;
    const sp: SurfacePoint = { e, p: ifc };
    const c0 = o.centreOf(q.element);
    if (c0) {
      const d = dirViewerToIfc([v[0] - c0[0], v[1] - c0[1], v[2] - c0[2]]);
      sp.l = [r(d[0]), r(d[1]), r(d[2])];
    }
    pts.push(sp);
  }
  if (pts.length < 2 || pts.length < c.pts.length * 0.9) return null;
  return { guids, pts, closed };
}

function percentile(sorted: number[], q: number): number {
  return sorted[Math.min(sorted.length - 1, Math.max(0, Math.round(q * (sorted.length - 1))))]!;
}

/**
 * Decide what a finished shape is attached to. Order: a measurement or penetration under the shape (the hint); at least 70%
 * of the projected points on at most 5 elements: `surface`; many elements inside with some depth spread: `region` (box-like
 * kinds) or `surface` when a line projects cleanly; else `none` (view-locked).
 */
export function inferAttachment(inp: InferInput): Inference {
  const info: InferInfo = { rays: 0, bad: 1, elements: 0, topShare: 0, interiorHits: 0, interiorElements: 0, spread: 0, reason: '' };
  const none = (reason: string): Inference => ({ attach: { kind: 'none' }, info: { ...info, reason } });
  const path = densifyPath(inp.path, inp.closed);
  const cast = castPath(path, inp.rayAt, inp.probe);
  info.rays = cast.length;
  const clean = cleanHits(cast, inp.closed);
  let surf: SurfaceData | null = null;
  if (clean) {
    info.bad = clean.bad;
    if (clean.bad <= SURFACE.maxBad) surf = toSurfaceData(clean, inp, inp.closed);
  }
  const counts = new Map<string, number>();
  if (surf) for (const p of surf.pts) counts.set(surf.guids[p.e]!, (counts.get(surf.guids[p.e]!) ?? 0) + 1);
  const sorted = [...counts.values()].sort((a, b) => b - a);
  info.elements = counts.size;
  if (surf) info.topShare = sorted.slice(0, SURFACE.fewElements).reduce((a, b) => a + b, 0) / surf.pts.length;

  if (inp.hint?.measurement) {
    const a: Attachment = { kind: 'measurement', measurement: inp.hint.measurement };
    if (surf) a.surface = surf;
    return { attach: a, info: { ...info, reason: 'measurement under the shape' } };
  }
  if (inp.hint?.penetration) {
    const a: Attachment = { kind: 'penetration', penetration: inp.hint.penetration };
    if (surf) a.surface = surf;
    return { attach: a, info: { ...info, reason: 'penetration under the shape' } };
  }
  if (surf && info.topShare >= SURFACE.surfaceShare) return { attach: { kind: 'surface', surface: surf }, info: { ...info, reason: `${Math.round(info.topShare * 100)}% of the points on ${Math.min(counts.size, SURFACE.fewElements)} element(s)` } };

  const box = isBoxLike(inp.kind);
  if (box && inp.closed) {
    // Interior: what is inside the outline, and how deep.
    const inner = interiorSamples(inp.path.length ? densifyPath(inp.path, true, SURFACE.step, 400) : []);
    const els = new Map<number, number>();
    const dist: number[] = [];
    const pts: Vec3[] = [];
    for (let i = 0; i < inner.length; i += 2) {
      const ray = inp.rayAt(inner[i]!, inner[i + 1]!);
      const h = ray ? inp.probe(ray) : null;
      if (!h) continue;
      els.set(h.element, (els.get(h.element) ?? 0) + 1);
      dist.push(h.distance);
      pts.push(h.point);
    }
    info.interiorHits = pts.length;
    const solid = [...els.values()].filter((c) => c >= Math.max(2, pts.length * 0.03)).length;
    info.interiorElements = solid;
    dist.sort((a, b) => a - b);
    info.spread = dist.length ? percentile(dist, 0.9) - percentile(dist, 0.1) : 0;
    if (pts.length >= 6 && solid >= SURFACE.regionElements && info.spread >= SURFACE.regionSpread) {
      const all = [...pts, ...(clean?.pts.map((q) => q.point) ?? [])];
      const lo: Vec3 = [Infinity, Infinity, Infinity];
      const hi: Vec3 = [-Infinity, -Infinity, -Infinity];
      for (const p of all) {
        const q = viewerToIfc(p, inp.shift);
        for (let k = 0; k < 3; k++) { lo[k] = Math.min(lo[k]!, q[k]!); hi[k] = Math.max(hi[k]!, q[k]!); }
      }
      const pad = 0.02 + 0.02 * Math.max(hi[0]! - lo[0]!, hi[1]! - lo[1]!, hi[2]! - lo[2]!);
      const r = (x: number): number => Math.round(x * 1e3) / 1e3;
      return { attach: { kind: 'region', region: { min: [r(lo[0]! - pad), r(lo[1]! - pad), r(lo[2]! - pad)], max: [r(hi[0]! + pad), r(hi[1]! + pad), r(hi[2]! + pad)] } }, info: { ...info, reason: `${solid} elements inside, ${info.spread.toFixed(2)} m deep` } };
    }
  } else if (!box && surf) {
    return { attach: { kind: 'surface', surface: surf }, info: { ...info, reason: 'line projects cleanly' } };
  }
  return none(clean ? (clean.bad > SURFACE.maxBad ? 'too many points miss or jump' : 'no dominant surface') : 'no hit');
}

/** The attachment of a re-run projection of the same shape forced to `surface` (the chip's Surface choice); null when it fails. */
export function projectSurface(inp: InferInput): Attachment | null {
  const path = densifyPath(inp.path, inp.closed);
  const clean = cleanHits(castPath(path, inp.rayAt, inp.probe), inp.closed);
  if (!clean || clean.bad > SURFACE.maxBad) return null;
  const s = toSurfaceData(clean, inp, inp.closed);
  return s ? { kind: 'surface', surface: s } : null;
}

/** The surface data of a shape for the other attachments that draw the outline (elements, measurement, penetration). */
export function projectSurfaceData(inp: InferInput): SurfaceData | null {
  return projectSurface(inp)?.surface ?? null;
}

/** A region fitted around a shape (the chip's Region choice); null when nothing is inside. */
export function projectRegion(inp: InferInput): Attachment | null {
  const inner = interiorSamples(densifyPath(inp.path, true, SURFACE.step, 400));
  const pts: Vec3[] = [];
  for (let i = 0; i < inner.length; i += 2) {
    const ray = inp.rayAt(inner[i]!, inner[i + 1]!);
    const h = ray ? inp.probe(ray) : null;
    if (h) pts.push(h.point);
  }
  const path = castPath(densifyPath(inp.path, inp.closed), inp.rayAt, inp.probe);
  for (const c of path) if (c?.hit) pts.push(c.hit.point);
  if (pts.length < 3) return null;
  const lo: Vec3 = [Infinity, Infinity, Infinity];
  const hi: Vec3 = [-Infinity, -Infinity, -Infinity];
  for (const p of pts) {
    const q = viewerToIfc(p, inp.shift);
    for (let k = 0; k < 3; k++) { lo[k] = Math.min(lo[k]!, q[k]!); hi[k] = Math.max(hi[k]!, q[k]!); }
  }
  const pad = 0.02 + 0.02 * Math.max(hi[0]! - lo[0]!, hi[1]! - lo[1]!, hi[2]! - lo[2]!);
  const r = (x: number): number => Math.round(x * 1e3) / 1e3;
  return cleanAttachment({ kind: 'region', region: { min: [r(lo[0]! - pad), r(lo[1]! - pad), r(lo[2]! - pad)], max: [r(hi[0]! + pad), r(hi[1]! + pad), r(hi[2]! + pad)] } }) ?? null;
}
