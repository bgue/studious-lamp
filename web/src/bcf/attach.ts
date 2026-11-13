// Attachment model shared by the markup tool (src/markup) and the BCF annotations (src/bcf): what a drawn shape is bound to
// in 3D, or that it is view-locked. Pure: no DOM, no three.js. Tested in tests/markup-attach.test.ts.
//
// A shape is stored as fractions of the view of its set camera on a depth plane (BcfShape). That plane is only right from
// the authored view, so a shape also carries an attachment:
//
//   none         view-locked: only the fractions. Drawn in 3D by the view-lock rule (viewLockState), always in the 2D view and PDF.
//   elements     a list of IfcGuids; the shape is drawn as the user's outline projected onto them, plus a highlight of them.
//   surface      the outline's points were projected onto model surfaces: each point is {element, offset in that element's
//                local frame}, so it follows the element when a revised model moves it (anchorPoint). IFC point as fallback.
//   measurement  linked to a measurement (BcfMeasureLink, the same link a callout uses).
//   penetration  linked to a penetration of the penetrations tool, by the GlobalIds of its MEP element and host.
//   region       a 3D box (IFC frame, axis aligned) fitted to the depth range of the geometry inside the outline.
//   point        a point in empty space (text boxes); the shape kinds do not use it.
//   lines        world lines in the IFC frame (a foreign BCF viewpoint's <Lines>).
//
// Anchored markups (text, callout, pointer, measure) keep their `anchor`; attachmentOf maps it 1:1 into this model.

import { dirViewerToIfc, ifcToViewer } from './model';
import type { BcfAnchor, BcfMeasureLink, Vec3 } from './model';

export const ATTACH_KINDS = ['none', 'elements', 'surface', 'measurement', 'penetration', 'region', 'point', 'lines'] as const;
export type AttachKind = (typeof ATTACH_KINDS)[number];

/** One projected stroke point: the element it landed on (index into `guids`), the IFC point, and the local offset. */
export interface SurfacePoint {
  /** Index into SurfaceData.guids. */
  e: number;
  /** IFC project coordinates (metres): the fallback when the element is gone. */
  p: Vec3;
  /** Offset of the point from the element's bounds centre (IFC frame), like BcfAnchor.local: follows the element. */
  l?: Vec3;
  /** Unit normal of the surface at the point (IFC frame, facing the authoring camera): re-projection casts back along it. */
  n?: Vec3;
  /** How far the point was lifted off the surface along `n` (m). */
  g?: number;
}

/** Axis aligned bounds in the IFC frame: min x, y, z, max x, y, z. */
export type Box6 = [number, number, number, number, number, number];

export interface SurfaceData {
  guids: string[];
  /** The drawn path, densified: the outline of a closed shape, the points of an open one. */
  pts: SurfacePoint[];
  closed: boolean;
  /**
   * Fingerprint of the targets when the outline was projected: the bounds (IFC frame) of each element of `guids`, null where
   * unknown. A model revision that changes them makes the viewer project the points onto the current surface again
   * (src/bcf/reproject.ts). Absent in older data.
   */
  fp?: Array<Box6 | null>;
}

export interface Attachment {
  kind: AttachKind;
  /** Elements: the target GlobalIds. */
  guids?: string[];
  /** Surface (and elements, measurement, penetration when the outline projects cleanly): the projected path. */
  surface?: SurfaceData;
  measurement?: BcfMeasureLink;
  penetration?: { mep: string; host: string };
  region?: { min: Vec3; max: Vec3 };
  lines?: Array<[Vec3, Vec3]>;
}

export const NONE: Attachment = { kind: 'none' };

export function isAttachKind(k: unknown): k is AttachKind {
  return typeof k === 'string' && (ATTACH_KINDS as readonly string[]).includes(k);
}

/** True when the attachment draws the shape in 3D (anything but view-locked or a bare point). */
export function isSpatial(a: Attachment | undefined): a is Attachment {
  if (!a) return false;
  switch (a.kind) {
    case 'surface': return !!a.surface && a.surface.pts.length >= 2;
    case 'elements': case 'measurement': case 'penetration': return !!a.surface && a.surface.pts.length >= 2;
    case 'region': return !!a.region;
    case 'lines': return !!a.lines?.length;
    default: return false;
  }
}

/** The GlobalIds an attachment refers to (each once). */
export function attachGuids(a: Attachment | undefined): string[] {
  const out = new Set<string>();
  if (!a) return [];
  for (const g of a.guids ?? []) out.add(g);
  for (const g of a.surface?.guids ?? []) out.add(g);
  for (const g of a.measurement?.elementGuids ?? []) out.add(g);
  if (a.penetration) { out.add(a.penetration.mep); out.add(a.penetration.host); }
  return [...out];
}

/** The target elements of an attached shape: `elements` and `surface` name them directly, the links name theirs. */
export function targetGuids(a: Attachment | undefined): string[] {
  return a ? attachGuids(a) : [];
}

export function cloneAttachment(a: Attachment): Attachment {
  return JSON.parse(JSON.stringify(a)) as Attachment;
}

/** The attachment of an anchored markup (text, callout, pointer, measure): its anchor mapped 1:1. */
export function attachmentOfAnchor(a: Pick<BcfAnchor, 'kind' | 'elementGuid' | 'measurement'>): Attachment {
  if (a.kind === 'measurement' && a.measurement) return { kind: 'measurement', measurement: a.measurement };
  if (a.kind === 'element' && a.elementGuid) return { kind: 'elements', guids: [a.elementGuid] };
  return { kind: 'point' };
}

// ---------------------------------------------------------------- reading

const isObj = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
const isNum = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);
const vec = (v: unknown): Vec3 | null => (Array.isArray(v) && v.length === 3 && v.every(isNum) ? [v[0] as number, v[1] as number, v[2] as number] : null);
const guidArr = (v: unknown, max = 500): string[] => (Array.isArray(v) ? v.filter((g): g is string => typeof g === 'string' && g !== '' && g.length < 80).slice(0, max) : []);
export const MAX_SURFACE_POINTS = 2000;
export const MAX_LINES = 4000;

function box6(v: unknown): Box6 | null {
  return Array.isArray(v) && v.length === 6 && v.every(isNum) ? [v[0] as number, v[1] as number, v[2] as number, v[3] as number, v[4] as number, v[5] as number] : null;
}
/** The stored bounds fingerprint, or undefined when it is absent or does not match the element list. */
function box6List(v: unknown, n: number): Array<Box6 | null> | undefined {
  if (!Array.isArray(v) || v.length !== n) return undefined;
  const out = v.map(box6);
  return out.some((b) => b) ? out : undefined;
}

/** A stored attachment, cleaned; undefined when it is not usable (the shape is then view-locked). */
export function cleanAttachment(v: unknown): Attachment | undefined {
  if (!isObj(v) || !isAttachKind(v['kind'])) return undefined;
  const kind = v['kind'];
  const a: Attachment = { kind };
  const guids = guidArr(v['guids']);
  if (guids.length) a.guids = guids;
  const s = v['surface'];
  if (isObj(s) && Array.isArray(s['pts'])) {
    const sg = guidArr(s['guids']);
    const pts: SurfacePoint[] = [];
    for (const p of s['pts'].slice(0, MAX_SURFACE_POINTS)) {
      if (!isObj(p)) return undefined;
      const pp = vec(p['p']);
      const e = p['e'];
      if (!pp || !isNum(e) || e < 0 || e >= sg.length) return undefined;
      const sp: SurfacePoint = { e: Math.floor(e), p: pp };
      const l = vec(p['l']);
      if (l) sp.l = l;
      const n = vec(p['n']);
      if (n) sp.n = n;
      if (isNum(p['g'])) sp.g = p['g'];
      pts.push(sp);
    }
    if (pts.length >= 2) {
      a.surface = { guids: sg, pts, closed: s['closed'] === true };
      const fp = box6List(s['fp'], sg.length);
      if (fp) a.surface.fp = fp;
    }
  }
  const m = v['measurement'];
  if (isObj(m)) {
    const pa = vec(m['a']);
    const pb = vec(m['b']);
    if (pa && pb && isNum(m['distance'])) {
      const ml: BcfMeasureLink = { kind: m['kind'] === 'element' ? 'element' : 'point', a: pa, b: pb, distance: m['distance'], label: typeof m['label'] === 'string' ? m['label'].slice(0, 60) : '' };
      const eg = guidArr(m['elementGuids'], 2);
      if (eg.length) ml.elementGuids = eg;
      if (isNum(m['sourceId'])) ml.sourceId = m['sourceId'];
      a.measurement = ml;
    }
  }
  const pen = v['penetration'];
  if (isObj(pen) && typeof pen['mep'] === 'string' && typeof pen['host'] === 'string') a.penetration = { mep: pen['mep'], host: pen['host'] };
  const r = v['region'];
  if (isObj(r)) {
    const lo = vec(r['min']);
    const hi = vec(r['max']);
    if (lo && hi) a.region = { min: [Math.min(lo[0], hi[0]), Math.min(lo[1], hi[1]), Math.min(lo[2], hi[2])], max: [Math.max(lo[0], hi[0]), Math.max(lo[1], hi[1]), Math.max(lo[2], hi[2])] };
  }
  if (Array.isArray(v['lines'])) {
    const lines: Array<[Vec3, Vec3]> = [];
    for (const l of v['lines'].slice(0, MAX_LINES)) {
      const p0 = Array.isArray(l) ? vec(l[0]) : null;
      const p1 = Array.isArray(l) ? vec(l[1]) : null;
      if (p0 && p1) lines.push([p0, p1]);
    }
    if (lines.length) a.lines = lines;
  }
  // A kind without its data is not usable.
  if (kind === 'elements' && !a.guids?.length) return undefined;
  if (kind === 'measurement' && !a.measurement) return undefined;
  if (kind === 'penetration' && !a.penetration) return undefined;
  if (kind === 'region' && !a.region) return undefined;
  if (kind === 'lines' && !a.lines) return undefined;
  if (kind === 'surface' && !a.surface) return undefined;
  return a;
}

// ---------------------------------------------------------------- the chip text

const NOUN: Record<string, string> = { IfcPipeSegment: 'pipe', IfcPipeFitting: 'pipe fitting', IfcDuctSegment: 'duct', IfcDuctFitting: 'duct fitting', IfcCableCarrierSegment: 'cable tray' };

/** "pipe", "wall", "slab": the class without the Ifc prefix, in plain words. */
export function classNoun(ifcClass: string | undefined): string {
  if (!ifcClass) return 'element';
  if (NOUN[ifcClass]) return NOUN[ifcClass]!;
  const base = ifcClass.replace(/^Ifc/, '').replace(/StandardCase$/, '').replace(/([a-z])([A-Z])/g, '$1 $2').toLowerCase();
  return base || 'element';
}

function plural(n: number, noun: string): string {
  if (n === 1) return `1 ${noun}`;
  if (/(s|x|ch|sh)$/.test(noun)) return `${n} ${noun}es`;
  return `${n} ${noun}s`;
}

export interface AttachDescription {
  /** True when the shape is bound to something in 3D (and not detached). */
  attached: boolean;
  /** The chip text without the "change" link: "Attached to: 2 pipes" or "View-locked". */
  text: string;
  detached: boolean;
}

/**
 * The words of the attachment chip. `classOf` names the IFC class of a GlobalId (so "2 pipes" and not "2 elements").
 * `missing`: GlobalIds that the loaded model does not have: the shape is detached and shown view-locked.
 */
export function describeAttachment(a: Attachment | undefined, o: { classOf?: (guid: string) => string | undefined; missing?: readonly string[]; spatialOnly?: boolean; surfaceLost?: boolean; revised?: boolean } = {}): AttachDescription {
  if (!a || a.kind === 'none') return { attached: false, text: 'View-locked', detached: false };
  const design = o.revised ? ' The model is a revision: this may already be designed.' : '';
  if (o.surfaceLost && (o.missing?.length ?? 0) === 0) return { attached: false, text: `Detached, its surface changed in this model. View-locked.${design}`, detached: true };
  if ((o.missing?.length ?? 0) > 0) return { attached: false, text: `Detached, ${plural(o.missing!.length, 'element')} missing. View-locked${o.revised ? '.' : ''}${design}`, detached: true };
  switch (a.kind) {
    case 'elements':
    case 'surface': {
      const g = attachGuids(a);
      if (!g.length) return { attached: true, text: 'Attached to: surface', detached: false };
      const nouns = new Set(g.map((x) => classNoun(o.classOf?.(x))));
      return { attached: true, text: `Attached to: ${nouns.size === 1 ? plural(g.length, [...nouns][0]!) : plural(g.length, 'element')}`, detached: false };
    }
    case 'measurement': return { attached: true, text: `Attached to: measurement${a.measurement?.label ? ` ${a.measurement.label}` : ''}`, detached: false };
    case 'penetration': return { attached: true, text: 'Attached to: penetration', detached: false };
    case 'region': return { attached: true, text: 'Attached to: 3D region', detached: false };
    case 'lines': return { attached: true, text: `Attached to: ${a.lines?.length ?? 0} 3D lines`, detached: false };
    case 'point': return { attached: true, text: 'Attached to: a point', detached: false };
  }
}

// ---------------------------------------------------------------- view-locked display rule

/** What a view-locked markup does in 3D: "near view + pin" (default), "pin only", or "hidden". */
export const VIEWLOCK_MODES = ['near view + pin', 'pin only', 'hidden'] as const;
export type ViewLockMode = (typeof VIEWLOCK_MODES)[number];
/** The setting, shared by the markup tool and the BCF annotations (the Markup folder of the panel sets it). */
export const viewLockSetting: { mode: ViewLockMode } = { mode: 'near view + pin' };

/**
 * Thresholds of the view-lock rule. The outline is at full strength while the camera is close to the authored view:
 * view direction within `fullAngle` degrees and eye position within `fullShift` of the scene scale. It fades out smoothly
 * (smoothstep) up to `fadeAngle` degrees or `fadeShift` of the scene scale, whichever is further along. The scale is the
 * larger of the model diagonal and the distance of the authored eye from the model centre (sceneScale in the controllers), so
 * an orbit of 10 degrees about the model is a shift of about 0.17 of it and the two criteria agree. Beyond that only a
 * pin at the centroid of the shape on its old depth plane is left. The pin fades in as the outline fades out.
 */
export const VIEWLOCK = { fullAngle: 10, fadeAngle: 25, fullShift: 0.2, fadeShift: 0.5 } as const;

export interface LockState {
  /** `full`: outline at full strength, `fade`: both partly, `pin`: only the pin, `hidden`: nothing. */
  mode: 'full' | 'fade' | 'pin' | 'hidden';
  /** Outline opacity factor 0..1. */
  alpha: number;
  /** Pin opacity factor 0..1. */
  pinAlpha: number;
  /** Degrees between the live and the authored view direction. */
  angle: number;
  /** Eye distance from the authored eye over the scene scale. */
  shift: number;
}

const smooth = (t: number): number => {
  const x = Math.min(1, Math.max(0, t));
  return x * x * (3 - 2 * x);
};

export function angleDeg(a: Vec3, b: Vec3): number {
  const la = Math.hypot(a[0], a[1], a[2]) || 1;
  const lb = Math.hypot(b[0], b[1], b[2]) || 1;
  const c = (a[0] * b[0] + a[1] * b[1] + a[2] * b[2]) / (la * lb);
  return (Math.acos(Math.max(-1, Math.min(1, c))) * 180) / Math.PI;
}

/**
 * The display state of a view-locked markup from the live camera and the camera it was made in (same frame for both, the
 * viewer frame). `sceneScale` is the scale of the shift (metres, see VIEWLOCK).
 */
export function viewLockState(live: { position: Vec3; direction: Vec3 }, authored: { position: Vec3; direction: Vec3 }, sceneScale: number, mode: ViewLockMode = 'near view + pin'): LockState {
  const angle = angleDeg(live.direction, authored.direction);
  const d = Math.hypot(live.position[0] - authored.position[0], live.position[1] - authored.position[1], live.position[2] - authored.position[2]);
  const shift = d / Math.max(1e-6, sceneScale);
  if (mode === 'hidden') return { mode: 'hidden', alpha: 0, pinAlpha: 0, angle, shift };
  if (mode === 'pin only') return { mode: 'pin', alpha: 0, pinAlpha: 1, angle, shift };
  const t = Math.max((angle - VIEWLOCK.fullAngle) / (VIEWLOCK.fadeAngle - VIEWLOCK.fullAngle), (shift - VIEWLOCK.fullShift) / (VIEWLOCK.fadeShift - VIEWLOCK.fullShift));
  if (t <= 0) return { mode: 'full', alpha: 1, pinAlpha: 0, angle, shift };
  if (t >= 1 - 1e-9) return { mode: 'pin', alpha: 0, pinAlpha: 1, angle, shift };
  const s = smooth(t);
  return { mode: 'fade', alpha: 1 - s, pinAlpha: s, angle, shift };
}

// ---------------------------------------------------------------- world lines (BCF Lines)

const BOX_EDGES: ReadonlyArray<readonly [number, number]> = [[0, 1], [1, 3], [3, 2], [2, 0], [4, 5], [5, 7], [7, 6], [6, 4], [0, 4], [1, 5], [2, 6], [3, 7]];

/** The 8 corners of a region (index bit 0 = x, bit 1 = y, bit 2 = z). */
export function regionCorners(r: { min: Vec3; max: Vec3 }): Vec3[] {
  const out: Vec3[] = [];
  for (let i = 0; i < 8; i++) out.push([i & 1 ? r.max[0] : r.min[0], i & 2 ? r.max[1] : r.min[1], i & 4 ? r.max[2] : r.min[2]]);
  return out;
}

/** The 12 edges of a region as 3D line segments (IFC frame). */
export function regionEdges(r: { min: Vec3; max: Vec3 }): Array<[Vec3, Vec3]> {
  const c = regionCorners(r);
  return BOX_EDGES.map(([i, j]) => [c[i!]!, c[j!]!] as [Vec3, Vec3]);
}

/**
 * 3D line segments (IFC frame) of an attachment for a BCF viewpoint's <Lines>: the projected path of a surface shape, the
 * edges of a region. Other kinds, and `lines` (already in the viewpoint), give none.
 */
export function attachmentSegments(a: Attachment | undefined): Array<[Vec3, Vec3]> {
  if (!a) return [];
  const out: Array<[Vec3, Vec3]> = [];
  if (a.kind === 'region' && a.region) return regionEdges(a.region);
  if ((a.kind === 'surface' || a.kind === 'elements' || a.kind === 'measurement' || a.kind === 'penetration') && a.surface) {
    const p = a.surface.pts;
    for (let i = 0; i + 1 < p.length; i++) out.push([p[i]!.p, p[i + 1]!.p]);
    if (a.surface.closed && p.length > 2) out.push([p[p.length - 1]!.p, p[0]!.p]);
  }
  return out;
}

/** Rounded key of a segment, to tell our own lines from foreign ones when a viewpoint is read again. */
export function segmentKey(s: readonly [Vec3, Vec3]): string {
  const r = (v: number): string => (Math.round(v * 1000) / 1000).toString();
  const a = s[0].map(r).join(',');
  const b = s[1].map(r).join(',');
  return a < b ? `${a}|${b}` : `${b}|${a}`;
}

/** Local frame helpers shared by the projection and the layout: a viewer-frame point as IFC offset from a viewer-frame centre. */
export function localOffset(point: Vec3, centre: Vec3): Vec3 {
  const d = dirViewerToIfc([point[0] - centre[0], point[1] - centre[1], point[2] - centre[2]]);
  const r = (x: number): number => Math.round(x * 1e6) / 1e6;
  return [r(d[0]), r(d[1]), r(d[2])];
}

/** Centre of a region in the viewer frame. */
export function regionCentreViewer(r: { min: Vec3; max: Vec3 }, shift: Vec3): Vec3 {
  return ifcToViewer([(r.min[0] + r.max[0]) / 2, (r.min[1] + r.max[1]) / 2, (r.min[2] + r.max[2]) / 2], shift);
}

// ---------------------------------------------------------------- occlusion of attached outlines

/** More than this share of hidden samples: the outline is "behind" other geometry and is drawn dimmed and dashed. */
export const BEHIND_SHARE = 0.6;
/** At most this many samples on a path. */
export const BEHIND_SAMPLES = 12;

/** `n` points spread evenly along a list (all of them when there are fewer). */
export function pickSamples<T>(pts: readonly T[], n: number = BEHIND_SAMPLES): T[] {
  if (pts.length <= n) return [...pts];
  const out: T[] = [];
  for (let i = 0; i < n; i++) out.push(pts[Math.round((i * (pts.length - 1)) / (n - 1))]!);
  return out;
}

/**
 * True when most sample points are hidden from the camera. `occluded(p)` is the first-hit test of the viewer (a hit nearer
 * than the sample by a small tolerance; hidden and click-through ghost elements do not count, as in a pick).
 */
export function mostlyHidden(samples: readonly Vec3[], occluded: ((p: Vec3) => boolean) | undefined): boolean {
  if (!occluded || !samples.length) return false;
  const n = samples.length;
  let hidden = 0;
  let seen = 0;
  for (const p of samples) {
    if (occluded(p)) hidden++;
    seen++;
    // The answer is decided once the rest cannot change it: enough hidden already, or too many visible to reach the share.
    if (hidden / n > BEHIND_SHARE) return true;
    if ((hidden + (n - seen)) / n <= BEHIND_SHARE) return false;
  }
  return hidden / n > BEHIND_SHARE;
}

/**
 * What besides the camera changes the answer of the occlusion test: the viewer sets it (the section planes in force and whether a
 * view mode cuts), so switching a section on or off re-tests the outlines although the camera has not moved.
 */
export const occlusionWorld: { stamp: () => string } = { stamp: () => '' };

/**
 * Throttled `mostlyHidden` for the live view: the answer of a key is kept while the camera (camKey) is unchanged, and is
 * recomputed at most every `interval` ms after it moves; in between the last answer stands and `redraw` is called once the
 * wait is over, so the final position always gets a fresh test.
 */
export class OcclusionCache {
  private readonly m = new Map<string, { cam: string; val: boolean; t: number }>();
  private timer: ReturnType<typeof setTimeout> | null = null;
  /** Samples tested since the last microtask (one draw pass). */
  private spent = 0;
  private readonly counted: (p: Vec3) => boolean;
  /**
   * `budget`: at most this many sample rays are cast for refreshing stale answers in one draw pass; the other outlines keep their
   * last answer for a frame and are refreshed by the next pass (`redraw` is called), so a camera move never costs one frame the
   * rays of every outline at once. An outline never tested before is always tested at once.
   */
  constructor(
    occluded: (p: Vec3) => boolean,
    private readonly camKey: () => string,
    private readonly redraw: () => void,
    private readonly interval = 150,
    private readonly now: () => number = () => Date.now(),
    private readonly budget = 96,
  ) {
    this.counted = (p) => {
      if (this.spent++ === 0) queueMicrotask(() => { this.spent = 0; });
      return occluded(p);
    };
  }

  behind(key: string, samples: readonly Vec3[]): boolean {
    const cam = `${this.camKey()}#${occlusionWorld.stamp()}`;
    const e = this.m.get(key);
    if (e && e.cam === cam) return e.val;
    const t = this.now();
    if (e && t - e.t < this.interval) {
      this.later(this.interval - (t - e.t) + 5);
      return e.val;
    }
    if (e && this.spent >= this.budget) {
      this.later(16);
      return e.val;
    }
    const val = mostlyHidden(samples, this.counted);
    this.m.set(key, { cam, val, t });
    return val;
  }

  private later(ms: number): void {
    if (!this.timer) this.timer = setTimeout(() => { this.timer = null; this.redraw(); }, ms);
  }

  clear(): void {
    this.m.clear();
  }
}
