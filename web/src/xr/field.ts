// Pure maths and data of the field AR mode (no three.js, no DOM, no WebXR types): site registration by point pairs, the fine
// nudges, following a WebXR anchor, the storey under the user, the cut box around the user, the field looks, and the saved
// registration format. src/xr/fieldSession.ts uses it inside a session; tests/xr-field.test.ts checks it.
//
// Registration: the user picks points on the model (world, viewer coordinates) and taps the same features in the room (the
// hit-test results, in the XR reference space, physical metres). The solve finds the rig (xr/maths.ts) that maps the room
// points onto the model points: world = rigPosition + Ry(yaw) * local, scale 1. The device frames of ARCore and Quest are
// gravity aligned, so the rotation is a yaw only ("keep vertical"); the least squares fit is the point cloud solver's
// (pointcloud/register.ts, imported read-only).

import { solvePairs } from '../pointcloud/register';
import type { ClassStyles } from '../types';
import { add, mul, quatRotate, rigPoint, rotateY, sub, wrapAngle } from './maths';
import type { Q4, Rig, V3 } from './maths';

// ---------------------------------------------------------------- registration

export interface FieldPair {
  /** Point on the model, world (viewer) coordinates. */
  model: V3 | null;
  /** The same feature in the room, XR reference space (physical metres). */
  real: V3 | null;
}

export interface FieldSolution {
  ok: boolean;
  rig: Rig;
  /** |model - rig(real)| per complete pair, metres. */
  residuals: number[];
  /** Horizontal and vertical parts of each residual, metres. */
  horizontal: number[];
  vertical: number[];
  rms: number;
  warnings: string[];
  /** Complete pairs used. */
  used: number;
}

/** Minimum number of complete pairs (yaw and translation from 2 points). */
export const FIELD_MIN_PAIRS = 2;

/** The rig of a yaw-only column-major matrix (local -> world). */
export function rigFromMatrix(m: ArrayLike<number>): Rig {
  return { position: [m[12]!, m[13]!, m[14]!], yaw: Math.atan2(m[8]!, m[0]!), scale: 1 };
}

/** Least squares rig from the complete pairs (keep vertical: yaw plus translation, real scale). */
export function solveFieldRegistration(pairs: readonly FieldPair[]): FieldSolution {
  const done = pairs.filter((p): p is { model: V3; real: V3 } => !!p.model && !!p.real);
  const real = done.map((p) => p.real);
  const model = done.map((p) => p.model);
  const s = solvePairs(real, model, { keepVertical: true, allowScale: false });
  const rig = s.ok ? rigFromMatrix(s.matrix) : { position: [0, 0, 0] as V3, yaw: 0, scale: 1 };
  const horizontal: number[] = [];
  const vertical: number[] = [];
  const residuals: number[] = [];
  if (s.ok) {
    for (const p of done) {
      const w = rigPoint(rig, p.real);
      const d = sub(p.model, w);
      horizontal.push(Math.hypot(d[0], d[2]));
      vertical.push(Math.abs(d[1]));
      residuals.push(Math.hypot(d[0], d[1], d[2]));
    }
  }
  const rms = residuals.length ? Math.sqrt(residuals.reduce((a, r) => a + r * r, 0) / residuals.length) : NaN;
  return { ok: s.ok, rig, residuals, horizontal, vertical, rms, warnings: s.warnings, used: done.length };
}

// ---------------------------------------------------------------- nudges and anchors

/** Horizontal forward and right unit vectors (XR reference space) of a head orientation. */
export function viewAxes(headQuat: Q4): { forward: V3; right: V3 } {
  const f = quatRotate(headQuat, [0, 0, -1]);
  let fx = f[0];
  let fz = f[2];
  const l = Math.hypot(fx, fz);
  if (l < 1e-6) {
    // looking straight up or down: use the head's up vector projected instead
    const u = quatRotate(headQuat, [0, 1, 0]);
    const s = f[1] < 0 ? 1 : -1;
    fx = u[0] * s;
    fz = u[2] * s;
  }
  const n = Math.hypot(fx, fz) || 1;
  const forward: V3 = [fx / n, 0, fz / n];
  return { forward, right: [-forward[2], 0, forward[0]] };
}

/** Move the model by `delta` (physical metres, XR reference space): it then appears `delta` further along in the room. */
export function nudgeTranslate(rig: Rig, delta: V3): Rig {
  return { position: sub(rig.position, rotateY(mul(delta, rig.scale), rig.yaw)), yaw: rig.yaw, scale: rig.scale };
}

/** Turn the model by `angle` (radians, counter-clockwise from above) about the vertical through `pivot` (XR reference space). */
export function nudgeRotate(rig: Rig, pivot: V3, angle: number): Rig {
  const keep = rigPoint(rig, pivot);
  const next: Rig = { position: [0, 0, 0], yaw: wrapAngle(rig.yaw - angle), scale: rig.scale };
  next.position = sub(keep, rigPoint(next, pivot));
  return next;
}

/** Shift the model up or down so that the world height `modelY` (a storey floor) appears at the room height `realY` (a floor hit). */
export function setFloorHeight(rig: Rig, realY: number, modelY: number): Rig {
  return { position: [rig.position[0], modelY - realY * rig.scale, rig.position[2]], yaw: rig.yaw, scale: rig.scale };
}

export interface Pose {
  position: V3;
  quaternion: Q4;
}

/** Rotation about +Y of an orientation (its x axis projected on the horizontal plane). */
export function yawOfQuat(q: Q4): number {
  const x = quatRotate(q, [1, 0, 0]);
  if (Math.hypot(x[0], x[2]) > 1e-6) return Math.atan2(-x[2], x[0]);
  const f = quatRotate(q, [0, 0, -1]);
  return Math.atan2(-f[0], -f[2]);
}

/**
 * The anchor moved (the device corrected its map): turn and shift the rig so that the room around the anchor keeps its model
 * position. `rigAtAnchor` is the rig when the anchor had the pose `then`; `now` is the anchor's pose this frame.
 */
export function followAnchor(rigAtAnchor: Rig, then: Pose, now: Pose): Rig {
  const dYaw = wrapAngle(yawOfQuat(now.quaternion) - yawOfQuat(then.quaternion));
  const yaw = wrapAngle(rigAtAnchor.yaw - dYaw);
  const s = rigAtAnchor.scale;
  const position = sub(add(rigAtAnchor.position, rotateY(mul(then.position, s), rigAtAnchor.yaw)), rotateY(mul(now.position, s), yaw));
  return { position, yaw, scale: s };
}

// ---------------------------------------------------------------- snapping a model point

/**
 * Snap a picked point to the nearest vertex of the element in plan (x, z) within `radius`, keeping the picked height: a pick
 * on a wall face near its corner lands on the vertical corner edge. `positions` is the merged xyz array.
 */
export function snapToVertexInPlan(positions: ArrayLike<number>, start: number, count: number, p: V3, radius: number): { point: V3; snapped: boolean; distance: number } {
  let best = radius;
  let bx = 0;
  let bz = 0;
  let found = false;
  for (let v = start; v < start + count; v++) {
    const x = positions[v * 3]!;
    const z = positions[v * 3 + 2]!;
    const d = Math.hypot(x - p[0], z - p[2]);
    if (d <= best) {
      best = d;
      bx = x;
      bz = z;
      found = true;
    }
  }
  return found ? { point: [bx, p[1], bz], snapped: true, distance: best } : { point: [...p], snapped: false, distance: 0 };
}

// ---------------------------------------------------------------- storeys

export interface FieldLevel {
  id: number;
  name: string;
  /** Floor height in world (viewer) coordinates. */
  floorY: number;
}

interface ModelLike {
  storeys: ReadonlyArray<{ id: number; name: string; elevation: number }>;
  elements: ReadonlyArray<{ storey: number | null; bounds: readonly number[] }>;
  originShift: readonly number[];
}

const median = (a: number[]): number => {
  const s = [...a].sort((x, y) => x - y);
  const m = s.length >> 1;
  return s.length % 2 ? s[m]! : (s[m - 1]! + s[m]!) / 2;
};

/**
 * Storey floors in world coordinates, lowest first. The IFC elevation becomes a viewer height by the vertical origin shift
 * (Z up in IFC is Y up in the viewer); when that disagrees by more than 1.5 m with the median bottom of the storey's
 * elements (a model without a matching shift), the median bottom is used.
 */
export function storeyFloors(model: ModelLike): FieldLevel[] {
  const bottoms = new Map<number, number[]>();
  for (const e of model.elements) {
    if (e.storey === null || e.storey === undefined) continue;
    const l = bottoms.get(e.storey) ?? [];
    l.push(e.bounds[1]!);
    bottoms.set(e.storey, l);
  }
  const shift = model.originShift[2] ?? 0;
  const out: FieldLevel[] = [];
  for (const s of model.storeys) {
    let y = s.elevation - shift;
    const b = bottoms.get(s.id);
    if (b && b.length && Math.abs(median(b) - y) > 1.5) y = median(b);
    if (!b && !Number.isFinite(y)) continue;
    out.push({ id: s.id, name: s.name, floorY: y });
  }
  return out.sort((a, b) => a.floorY - b.floorY || a.id - b.id);
}

/** Typical height of a phone or headset above the floor when no floor was found, metres. */
export const DEFAULT_EYE_HEIGHT = 1.5;

/**
 * The storey the user stands on: the highest floor at or below the feet (plus `tolerance`, so a slab top a little above the
 * floor level still counts). Index -1 when there are no storeys; the lowest storey when the feet are below every floor.
 */
export function storeyAt(levels: readonly FieldLevel[], feetY: number, tolerance = 0.5): { index: number; level: FieldLevel | null; ceilingY: number | null } {
  if (!levels.length) return { index: -1, level: null, ceilingY: null };
  let index = 0;
  for (let i = 0; i < levels.length; i++) if (levels[i]!.floorY <= feetY + tolerance) index = i;
  const next = levels[index + 1];
  return { index, level: levels[index]!, ceilingY: next ? next.floorY : null };
}

export interface CutSettings {
  /** Half size of the cut box around the user in plan, metres; 0 = no radius cut. */
  radius: number;
  /** Cut at the ceiling of the current storey (the floor of the next one) and 1 m below its floor. */
  storeyCut: boolean;
}

/** Depth below the storey floor that the storey cut keeps (services under the floor stay visible), metres. */
export const CUT_BELOW_FLOOR = 1.0;

/**
 * The section box of the field cut: `radius` around the head in plan, and with the storey cut from 1 m below the storey
 * floor up to its ceiling. `bounds` (the model box, min then max) fills the sides that are not cut. Null when nothing cuts.
 */
export function fieldCutBox(head: V3, cut: CutSettings, storey: { floorY: number; ceilingY: number | null } | null, bounds: [V3, V3]): { min: V3; max: V3 } | null {
  const pad = 1;
  const min: V3 = [bounds[0][0] - pad, bounds[0][1] - pad, bounds[0][2] - pad];
  const max: V3 = [bounds[1][0] + pad, bounds[1][1] + pad, bounds[1][2] + pad];
  let any = false;
  if (cut.radius > 0) {
    min[0] = head[0] - cut.radius;
    max[0] = head[0] + cut.radius;
    min[2] = head[2] - cut.radius;
    max[2] = head[2] + cut.radius;
    any = true;
  }
  if (cut.storeyCut && storey) {
    min[1] = storey.floorY - CUT_BELOW_FLOOR;
    if (storey.ceilingY !== null) max[1] = storey.ceilingY;
    any = true;
  }
  return any ? { min, max } : null;
}

// ---------------------------------------------------------------- field looks

export const FIELD_VIEWS = ['x-ray', 'ghosted', 'full'] as const;
export type FieldView = (typeof FIELD_VIEWS)[number];

/** Opacity cap of walls, slabs and the other structure classes in the ghosted look: nearly invisible. */
export const FIELD_STRUCTURE_ALPHA = 0.06;
/** Opacity cap of the remaining non-services classes (doors, windows, furniture) in the ghosted look. */
export const FIELD_OTHER_ALPHA = 0.2;

/**
 * Class styles of a field look laid over the user's `base` styles. 'x-ray': only the services classes stay (the others are
 * hidden); 'ghosted': services as they are, structure nearly invisible, the rest faint; 'full': `base` unchanged (same object).
 */
export function fieldClassStyles(base: ClassStyles, present: readonly string[], focusClasses: readonly string[], ctxClasses: readonly string[], view: FieldView): ClassStyles {
  if (view === 'full') return base;
  const focus = new Set(focusClasses);
  const ctx = new Set(ctxClasses);
  const out: ClassStyles = {};
  for (const [k, v] of Object.entries(base)) out[k] = { ...v, ...(v.color ? { color: [...v.color] as [number, number, number] } : {}) };
  for (const cls of present) {
    if (focus.has(cls)) continue;
    const s = { ...(out[cls] ?? {}) };
    if (view === 'x-ray') s.hidden = true;
    else s.alphaMax = Math.min(s.alphaMax ?? 1, ctx.has(cls) ? FIELD_STRUCTURE_ALPHA : FIELD_OTHER_ALPHA);
    out[cls] = s;
  }
  return out;
}

// ---------------------------------------------------------------- saved registrations

export const SITE_SCHEMA = 'xray-xr-site/1';

export interface SiteRegistration {
  schema: typeof SITE_SCHEMA;
  id: string;
  name: string;
  /** Model name in the viewer and a short fingerprint (element count and first and last GlobalId). */
  model: string;
  modelKey: string;
  created: string;
  /** Model points (world) and the room points of the session that saved it (XR reference space; only meaningful with the anchor). */
  pairs: Array<{ model: V3; real: V3 | null }>;
  rig: { position: V3; yaw: number };
  residuals: number[];
  rms: number;
  /** The WebXR anchor at the time of saving: its pose then, and a persistent handle where the browser offers one. */
  anchor?: { pose: Pose; handle?: string };
}

/** Short fingerprint of a model: a saved site of another model is not offered. */
export function modelKeyOf(model: { elements: ReadonlyArray<{ globalId: string }> }): string {
  const e = model.elements;
  return `${e.length}:${e[0]?.globalId ?? ''}:${e[e.length - 1]?.globalId ?? ''}`;
}

const isNum = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);
const isV3 = (v: unknown): v is V3 => Array.isArray(v) && v.length === 3 && v.every(isNum);
const isQ4 = (v: unknown): v is Q4 => Array.isArray(v) && v.length === 4 && v.every(isNum);

/** Check and normalise a saved registration (from storage or an imported file). */
export function parseSite(v: unknown): { site: SiteRegistration | null; errors: string[] } {
  const errors: string[] = [];
  if (v === null || typeof v !== 'object') return { site: null, errors: ['not an object'] };
  const o = v as Record<string, unknown>;
  if (o.schema !== SITE_SCHEMA) errors.push(`schema is not ${SITE_SCHEMA}`);
  for (const k of ['id', 'name', 'model', 'modelKey', 'created'] as const) if (typeof o[k] !== 'string') errors.push(`${k} is not a string`);
  const pairs: SiteRegistration['pairs'] = [];
  if (!Array.isArray(o.pairs)) errors.push('pairs is not a list');
  else
    o.pairs.forEach((p, i) => {
      const q = p as Record<string, unknown> | null;
      if (!q || !isV3(q.model) || !(q.real === null || q.real === undefined || isV3(q.real))) errors.push(`pairs[${i}] is not { model, real }`);
      else pairs.push({ model: [...q.model], real: q.real ? [...(q.real as V3)] : null });
    });
  if (pairs.length < FIELD_MIN_PAIRS) errors.push(`fewer than ${FIELD_MIN_PAIRS} pairs`);
  const rig = o.rig as Record<string, unknown> | undefined;
  if (!rig || !isV3(rig.position) || !isNum(rig.yaw)) errors.push('rig is not { position, yaw }');
  const residuals = Array.isArray(o.residuals) && o.residuals.every(isNum) ? (o.residuals as number[]) : [];
  let anchor: SiteRegistration['anchor'];
  if (o.anchor !== undefined) {
    const a = o.anchor as Record<string, unknown> | null;
    const pose = a?.pose as Record<string, unknown> | undefined;
    if (!a || !pose || !isV3(pose.position) || !isQ4(pose.quaternion) || (a.handle !== undefined && typeof a.handle !== 'string')) errors.push('anchor is not { pose, handle? }');
    else anchor = { pose: { position: [...pose.position], quaternion: [...pose.quaternion] }, ...(typeof a.handle === 'string' ? { handle: a.handle } : {}) };
  }
  if (errors.length) return { site: null, errors };
  const site: SiteRegistration = {
    schema: SITE_SCHEMA,
    id: o.id as string,
    name: o.name as string,
    model: o.model as string,
    modelKey: o.modelKey as string,
    created: o.created as string,
    pairs,
    rig: { position: [...(rig!.position as V3)], yaw: rig!.yaw as number },
    residuals: [...residuals],
    rms: isNum(o.rms) ? o.rms : NaN,
    ...(anchor ? { anchor } : {}),
  };
  return { site, errors };
}

/** Storage key of the saved sites of a model. */
export const siteStorageKey = (model: string): string => `xray.xr.sites.${model}`;

interface StorageLike {
  getItem(k: string): string | null;
  setItem(k: string, v: string): void;
}

/** Saved sites of a model, newest first; unreadable entries are skipped. Never throws. */
export function loadSites(storage: StorageLike | null, model: string, modelKey?: string): SiteRegistration[] {
  try {
    const raw = storage?.getItem(siteStorageKey(model));
    if (!raw) return [];
    const list = JSON.parse(raw) as unknown;
    if (!Array.isArray(list)) return [];
    return list
      .map((x) => parseSite(x).site)
      .filter((s): s is SiteRegistration => !!s && (!modelKey || s.modelKey === modelKey))
      .sort((a, b) => (a.created < b.created ? 1 : a.created > b.created ? -1 : 0));
  } catch {
    return [];
  }
}

/** Add or replace (same id) a site; keeps the newest `max`. Returns false when the storage refused. */
export function saveSiteTo(storage: StorageLike | null, site: SiteRegistration, max = 20): boolean {
  if (!storage) return false;
  try {
    const list = loadSites(storage, site.model).filter((s) => s.id !== site.id);
    list.unshift(site);
    storage.setItem(siteStorageKey(site.model), JSON.stringify(list.slice(0, max)));
    return true;
  } catch {
    return false;
  }
}

/** "1.2 cm" style length for the overlay. */
export function cm(m: number): string {
  if (!Number.isFinite(m)) return '-';
  return Math.abs(m) < 1 ? `${(m * 100).toFixed(1)} cm` : `${m.toFixed(2)} m`;
}

/** Signed height "+1.23 m". */
export function signedM(m: number): string {
  return `${m >= 0 ? '+' : '-'}${Math.abs(m).toFixed(2)} m`;
}
