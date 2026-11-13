// Sheet placement: where a PDF sheet sits in the model. Pure maths: no DOM, no PDF library, no three.js. Tested in
// tests/sheets-placement.test.ts. Docs: docs-features/sheets.md.
//
// A plan sheet maps to the horizontal plane at a level (an elevation, metres, IFC frame). The mapping is a 2D similarity (uniform
// scale, rotation, translation, no mirror) from PDF user-space points (x right, y up, the units of the page) to the model's plan
// coordinates (IFC frame, X east, Y north, metres). In complex form a point z = x + iy goes to w = c z + d, with c = s e^(i theta).
// Two point pairs fix it, more pairs are fitted by least squares, and a drawing scale (1:100) with one pair and a rotation fixes
// it too. A sheet may also stand in a vertical plane (elevations and sections): the 2D point then runs along the plane's
// horizontal axis and up it. The manual flow of the viewer places plans; `plane` keeps the model ready for the others.

import type { Vec3 } from '../bcf/model';

export type Vec2 = [number, number];

/** PDF user space to model plan metres: x' = s (cos t x - sin t y) + tx, y' = s (sin t x + cos t y) + ty. */
export interface Similarity {
  /** Model metres per PDF point (always > 0). */
  scale: number;
  /** Radians, counter-clockwise. */
  rotation: number;
  tx: number;
  ty: number;
}

export interface PointPair {
  /** The point on the sheet, PDF user space. */
  sheet: Vec2;
  /** The same point in the model, plan metres (IFC X, Y). */
  model: Vec2;
}

export interface SheetLevel {
  /** The storey the sheet belongs to, when the model gives one. */
  storeyGuid?: string;
  /** The storey name, for the panel. */
  name?: string;
  /** Metres, IFC frame (Z up): the plane of a plan sheet. */
  elevation: number;
}

/** A vertical plane for elevation and section sheets: the sheet's x runs along `axis` (horizontal), its y up. */
export interface SheetPlane {
  normal: Vec3;
  point: Vec3;
}

export interface SheetPlacement {
  kind: 'manual' | 'geo';
  level: SheetLevel;
  /** 'plan' (default): the horizontal plane at the level. Else a vertical plane. */
  plane?: 'plan' | SheetPlane;
  transform: Similarity;
  /** Root mean square of the pair misfits, metres: only with 3 or more pairs. */
  residual?: number;
  /** How it was made: "2 points", "3 points", "scale 1:100", "geo-PDF EPSG:25832". */
  source: string;
  /** The pairs a manual placement was made from (kept so the viewer can show and edit them). */
  pairs?: PointPair[];
  /** The scale a "use drawing scale" placement was made with. */
  drawingScale?: number;
}

// ---------------------------------------------------------------- the similarity

export const IDENTITY: Similarity = { scale: 1, rotation: 0, tx: 0, ty: 0 };

const finite = (n: unknown): n is number => typeof n === 'number' && Number.isFinite(n);

export function applySim(t: Similarity, p: Vec2): Vec2 {
  const c = t.scale * Math.cos(t.rotation);
  const s = t.scale * Math.sin(t.rotation);
  return [c * p[0] - s * p[1] + t.tx, s * p[0] + c * p[1] + t.ty];
}

export function invertSim(t: Similarity): Similarity {
  const inv = 1 / t.scale;
  const c = inv * Math.cos(-t.rotation);
  const s = inv * Math.sin(-t.rotation);
  // z = (w - d) / c
  return { scale: inv, rotation: -t.rotation, tx: -(c * t.tx - s * t.ty), ty: -(s * t.tx + c * t.ty) };
}

/** `a` after `b`: x -> a(b(x)). */
export function composeSim(a: Similarity, b: Similarity): Similarity {
  const ca = [a.scale * Math.cos(a.rotation), a.scale * Math.sin(a.rotation)] as const;
  const cb = [b.scale * Math.cos(b.rotation), b.scale * Math.sin(b.rotation)] as const;
  const c = [ca[0] * cb[0] - ca[1] * cb[1], ca[0] * cb[1] + ca[1] * cb[0]] as const;
  const d = applySim(a, [b.tx, b.ty]);
  return { scale: Math.hypot(c[0], c[1]), rotation: Math.atan2(c[1], c[0]), tx: d[0], ty: d[1] };
}

export function isSimilarity(t: unknown): t is Similarity {
  return !!t && typeof t === 'object' && finite((t as Similarity).scale) && (t as Similarity).scale > 0 && finite((t as Similarity).rotation) && finite((t as Similarity).tx) && finite((t as Similarity).ty);
}

/** Similarity of the complex form w = c z + d. */
function fromComplex(cr: number, ci: number, dx: number, dy: number): Similarity {
  return { scale: Math.hypot(cr, ci), rotation: Math.atan2(ci, cr), tx: dx, ty: dy };
}

export type FitResult = { ok: true; transform: Similarity; residual?: number; misfits: number[] } | { ok: false; error: string };

/**
 * The similarity through point pairs. Two pairs give the exact transform (no residual: nothing is left over); three or more are
 * fitted by least squares and `residual` is the root mean square of the misfits, in model metres. Pairs that coincide on the
 * sheet, or a degenerate spread, are refused with a reason.
 */
export function fitSimilarity(pairs: readonly PointPair[]): FitResult {
  const n = pairs.length;
  if (n < 2) return { ok: false, error: 'Two point pairs are needed' };
  for (const p of pairs) if (![...p.sheet, ...p.model].every(finite)) return { ok: false, error: 'A point is not a number' };
  let sx = 0, sy = 0, mx = 0, my = 0;
  for (const p of pairs) { sx += p.sheet[0]; sy += p.sheet[1]; mx += p.model[0]; my += p.model[1]; }
  sx /= n; sy /= n; mx /= n; my /= n;
  // c = sum conj(z) w / sum |z|^2, with z, w centred.
  let numR = 0, numI = 0, den = 0;
  for (const p of pairs) {
    const zx = p.sheet[0] - sx, zy = p.sheet[1] - sy, wx = p.model[0] - mx, wy = p.model[1] - my;
    numR += zx * wx + zy * wy;
    numI += zx * wy - zy * wx;
    den += zx * zx + zy * zy;
  }
  if (!(den > 1e-9)) return { ok: false, error: 'The points on the sheet are too close together' };
  const cr = numR / den, ci = numI / den;
  if (!(Math.hypot(cr, ci) > 1e-12)) return { ok: false, error: 'The points in the model are too close together' };
  const dx = mx - (cr * sx - ci * sy);
  const dy = my - (ci * sx + cr * sy);
  const transform = fromComplex(cr, ci, dx, dy);
  const misfits = pairs.map((p) => {
    const q = applySim(transform, p.sheet);
    return Math.hypot(q[0] - p.model[0], q[1] - p.model[1]);
  });
  const res = n >= 3 ? Math.sqrt(misfits.reduce((a, b) => a + b * b, 0) / n) : undefined;
  return { ok: true, transform, ...(res !== undefined ? { residual: res } : {}), misfits };
}

/** Metres in the model per PDF point for a drawing scale 1:`denominator` (a point is 1/72 inch). */
export function metresPerPoint(denominator: number): number {
  return (25.4 / 72 / 1000) * denominator;
}

/** The scale denominator of a similarity: 1:N. */
export function denominatorOf(t: Similarity): number {
  return t.scale / metresPerPoint(1);
}

/**
 * "Use drawing scale": the scale (1:100), one point pair and the rotation of the drawing against the model (degrees, counter-clockwise
 * from the sheet's x axis to the model's X axis) give the whole transform.
 */
export function fromScale(denominator: number, rotationDeg: number, pair: PointPair): FitResult {
  if (!finite(denominator) || denominator <= 0) return { ok: false, error: 'The scale must be a positive number, like 100 for 1:100' };
  if (!finite(rotationDeg)) return { ok: false, error: 'The rotation must be a number of degrees' };
  if (![...pair.sheet, ...pair.model].every(finite)) return { ok: false, error: 'A point is not a number' };
  const scale = metresPerPoint(denominator);
  const rotation = (rotationDeg * Math.PI) / 180;
  const t: Similarity = { scale, rotation, tx: 0, ty: 0 };
  const q = applySim(t, pair.sheet);
  t.tx = pair.model[0] - q[0];
  t.ty = pair.model[1] - q[1];
  return { ok: true, transform: t, misfits: [0] };
}

// ---------------------------------------------------------------- placement helpers

export const planeOf = (p: SheetPlacement): 'plan' | SheetPlane => p.plane ?? 'plan';
export const isPlan = (p: SheetPlacement): boolean => planeOf(p) === 'plan';

/** A sheet point (user space) in model coordinates: plan sheets at the level elevation, vertical-plane sheets in their plane. */
export function sheetToModel(p: SheetPlacement, pt: Vec2): Vec3 {
  const q = applySim(p.transform, pt);
  const pl = planeOf(p);
  if (pl === 'plan') return [q[0], q[1], p.level.elevation];
  // Vertical plane: x runs along the horizontal in-plane axis (normal x up is the other horizontal), y is height above the plane point.
  const h = Math.hypot(pl.normal[0], pl.normal[1]) || 1;
  const ax: Vec2 = [-pl.normal[1] / h, pl.normal[0] / h];
  return [pl.point[0] + ax[0] * q[0], pl.point[1] + ax[1] * q[0], pl.point[2] + q[1]];
}

/** A model plan point back to the sheet (user space) of a plan placement. */
export function modelToSheet(p: SheetPlacement, xy: Vec2): Vec2 {
  return applySim(invertSim(p.transform), xy);
}

export function mm(m: number): string {
  const v = m * 1000;
  return v < 10 ? v.toFixed(1) : String(Math.round(v));
}

/** The status words of the Sheets segment. */
export function placementStatus(p: SheetPlacement | undefined): string {
  if (!p) return 'Not placed';
  if (p.kind === 'geo') return p.residual !== undefined && p.residual > 0 ? `Placed (geo, ±${mm(p.residual)} mm)` : 'Placed (geo)';
  if (p.residual !== undefined) return `Placed (manual, ±${mm(p.residual)} mm)`;
  if (p.drawingScale) return `Placed (manual, scale 1:${Math.round(p.drawingScale)})`;
  return `Placed (manual, ${p.pairs?.length ?? 2} points)`;
}

/** Whether two placements put the sheet in the same place (within 1 mm at the page origin and 1e-6 in scale and angle). */
export function samePlacement(a: SheetPlacement | undefined, b: SheetPlacement | undefined): boolean {
  if (!a || !b) return !a && !b;
  const p = applySim(a.transform, [0, 0]);
  const q = applySim(b.transform, [0, 0]);
  return a.level.elevation === b.level.elevation && Math.hypot(p[0] - q[0], p[1] - q[1]) < 1e-3 && Math.abs(a.transform.scale / b.transform.scale - 1) < 1e-6 && Math.abs(a.transform.rotation - b.transform.rotation) < 1e-6;
}

// ---------------------------------------------------------------- reading a stored placement

const str = (v: unknown, max = 200): string | undefined => (typeof v === 'string' && v.length <= max ? v : undefined);
const vec2 = (v: unknown): Vec2 | null => (Array.isArray(v) && v.length === 2 && v.every(finite) ? [v[0] as number, v[1] as number] : null);
const vec3 = (v: unknown): Vec3 | null => (Array.isArray(v) && v.length === 3 && v.every(finite) ? [v[0] as number, v[1] as number, v[2] as number] : null);

/** A stored placement, cleaned; undefined when it is not usable (the sheet is then not placed). */
export function sanitizePlacement(raw: unknown): SheetPlacement | undefined {
  if (!raw || typeof raw !== 'object') return undefined;
  const r = raw as Record<string, unknown>;
  if (r['kind'] !== 'manual' && r['kind'] !== 'geo') return undefined;
  const lv = r['level'] as Record<string, unknown> | undefined;
  if (!lv || typeof lv !== 'object' || !finite(lv['elevation'])) return undefined;
  const tr = r['transform'];
  if (!isSimilarity(tr)) return undefined;
  const level: SheetLevel = { elevation: lv['elevation'] };
  const g = str(lv['storeyGuid'], 80);
  if (g) level.storeyGuid = g;
  const nm = str(lv['name'], 120);
  if (nm) level.name = nm;
  const p: SheetPlacement = { kind: r['kind'], level, transform: { scale: tr.scale, rotation: tr.rotation, tx: tr.tx, ty: tr.ty }, source: str(r['source']) ?? (r['kind'] === 'geo' ? 'geo-PDF' : 'manual') };
  const pl = r['plane'];
  if (pl === 'plan') p.plane = 'plan';
  else if (pl && typeof pl === 'object') {
    const n = vec3((pl as Record<string, unknown>)['normal']);
    const pt = vec3((pl as Record<string, unknown>)['point']);
    if (n && pt && Math.hypot(n[0], n[1]) > 1e-9) p.plane = { normal: n, point: pt };
  }
  if (finite(r['residual']) && r['residual'] >= 0) p.residual = r['residual'];
  if (Array.isArray(r['pairs'])) {
    const pairs: PointPair[] = [];
    for (const x of r['pairs'].slice(0, 12)) {
      const s = vec2((x as Record<string, unknown>)?.['sheet']);
      const m = vec2((x as Record<string, unknown>)?.['model']);
      if (s && m) pairs.push({ sheet: s, model: m });
    }
    if (pairs.length) p.pairs = pairs;
  }
  if (finite(r['drawingScale']) && r['drawingScale'] > 0) p.drawingScale = r['drawingScale'];
  return p;
}
