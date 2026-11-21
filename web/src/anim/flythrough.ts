// Fly-throughs: keyframes that are full saved-view states plus timing, compiled to a score (src/anim/score.ts) that the score
// player plays. Pure module (no DOM, no three.js), tested in tests/anim-*.test.ts.
//
// A fly-through is a named list of keyframes. A keyframe holds a copy of a saved view (camera with up, field of view and
// projection, selection, hides and isolate, explode, params snapshot incl. the section, preset id, thumbnail) and the timing of
// the move that arrives at it: travel seconds (or the constant speed of the fly-through), the hold (pause) on arrival, ease,
// where a discrete change happens, a fade of the elements that appear or disappear, and an optional caption.
//
// Storage: localStorage `xray.flythroughs.<identityKey>` (src/markup/scope.ts identityKey: name, element count, GlobalId hash)
// -> `xray-flythroughs/1` document. Captions are user text: they stay in this store and its explicit export, never in params,
// share links, saved views or packed pages.

import type { SavedView, Vec3 } from '../views/model';
import { sanitizeView } from '../views/model';
import type { Cue, Score, SwitchAt, CameraPose, V3, ElementRef } from './score';
import { SCORE_SCHEMA, scoreEnd } from './score';
import { Spline3 } from './spline';
import { DEFAULT_LABEL_FIELDS, MAX_LABEL_FIELDS } from './hud/fields';
import { sanitizeHud } from './hud/settings';
import type { HudSettings } from './hud/settings';
import type { P3 } from './spline';

export const FLYTHROUGHS_SCHEMA = 'xray-flythroughs/1';
export const FLYTHROUGHS_KEY_PREFIX = 'xray.flythroughs.';
/** The key of the pre-timeline fly-through keyframes (`xray.flythrough.<modelName>`). */
export const LEGACY_KEY_PREFIX = 'xray.flythrough.';

export const DEFAULT_FADE_FRACTION = 0.4;
export const DEFAULT_SEGMENT_S = 3;
export const MIN_TRAVEL_S = 0.5;
/** A selection starts this long before the camera arrives (at most 30 % of the segment). */
export const SELECT_LEAD_S = 0.8;
export const DEFAULT_CAPTION_S = 2.5;
export const MAX_KEYFRAMES = 200;

export interface FlyCaption {
  title?: string;
  text?: string;
}

/** "Label the selection" of a keyframe: a tag per selected element with these fields (name, class, storey, material, globalid,
 *  type or a property key). */
export interface FlyLabels {
  fields: string[];
}

export interface FlyKeyframe {
  id: string;
  name: string;
  /** The state of this keyframe: a copy of a saved view. */
  view: SavedView;
  /** The saved view it was taken from, when it came from the list (informational). */
  viewId?: string;
  /** Seconds to travel from the previous keyframe. Absent: the fly-through's speed (or its seconds per segment). Not used by the first keyframe. */
  travel?: number;
  /** Seconds to stay on arrival. */
  hold: number;
  /** Ease the camera in and out around this keyframe when it is a stop (the first, the last or a held one). */
  ease: boolean;
  /** Elements that appear or disappear on the way to this keyframe fade (else they switch at `switchAt`). */
  fade: boolean;
  /** Length of the fade as a fraction of the travel (the last part of it). */
  fadeFraction: number;
  /** Where in the travel the discrete changes happen (settings, projection, explode, hides without fade). */
  switchAt: SwitchAt;
  caption?: FlyCaption;
  /** Tag each element of the keyframe's selection while the camera stays here (as long as the caption: the hold, else 2.5 s). */
  labels?: FlyLabels;
  /** Show the hover card of the first selected element while the camera stays here. */
  hover?: boolean;
}

export interface FlyThrough {
  id: string;
  name: string;
  keyframes: FlyKeyframe[];
  /** 'speed': constant speed by arc length (metres per second); 'seconds': a fixed time per segment. */
  timing: 'speed' | 'seconds';
  speed: number;
  segmentS: number;
  /** Keep the camera looking at the selection of each keyframe. */
  lookAtSelection: boolean;
  loop?: boolean;
}

export interface FlyDoc {
  schema: typeof FLYTHROUGHS_SCHEMA;
  flythroughs: FlyThrough[];
  /** Id of the one shown in the timeline. */
  active: string | null;
  /** What the HUD shows besides captions and labels (progress bar, compass, scale bar, label size, caption position). */
  hud?: HudSettings;
}

// ---------------------------------------------------------------- ids, defaults

let counter = 0;
export function newFlyId(prefix = 'f', now = Date.now()): string {
  return `${prefix}${now.toString(36)}${(counter++).toString(36)}${Math.floor(Math.random() * 1296).toString(36)}`;
}

/** Metres per second that cross the model in about 12 seconds. */
export function defaultSpeed(modelDiagonal: number): number {
  const v = modelDiagonal / 12;
  if (!Number.isFinite(v) || v <= 0) return 3;
  return Math.min(200, Math.max(0.5, Math.round(v * 10) / 10));
}

export function newFlyThrough(name: string, speed = 3, now = Date.now()): FlyThrough {
  return { id: newFlyId('ft', now), name: name || 'Fly-through', keyframes: [], timing: 'speed', speed, segmentS: DEFAULT_SEGMENT_S, lookAtSelection: false };
}

export function newKeyframe(view: SavedView, opts: Partial<Omit<FlyKeyframe, 'id' | 'view'>> = {}, now = Date.now()): FlyKeyframe {
  return {
    id: newFlyId('k', now),
    name: opts.name ?? view.name,
    view: JSON.parse(JSON.stringify(view)) as SavedView,
    hold: 0,
    ease: true,
    fade: true,
    fadeFraction: DEFAULT_FADE_FRACTION,
    switchAt: 'end',
    ...opts,
  };
}

export function uniqueFlyName(name: string, list: readonly { id: string; name: string }[], except?: string): string {
  const base = name.trim() || 'Fly-through';
  const taken = new Set(list.filter((f) => f.id !== except).map((f) => f.name.toLowerCase()));
  if (!taken.has(base.toLowerCase())) return base;
  const stem = base.replace(/\s+\d+$/, '');
  for (let n = 2; ; n++) {
    const c = `${stem} ${n}`;
    if (!taken.has(c.toLowerCase())) return c;
  }
}

// ---------------------------------------------------------------- compile

export interface CompileContext {
  /** Centre of the elements (GlobalIds), for "keep looking at the selection". Null when unknown. */
  selectionCenter?(globalIds: readonly string[]): V3 | null;
}

export interface Timing {
  /** Seconds of each keyframe's arrival. */
  arrive: number[];
  /** Seconds each keyframe is left (arrive + hold). */
  depart: number[];
  /** Travel seconds into each keyframe (index 0 is 0). */
  travel: number[];
  total: number;
}

const toP3 = (v: readonly number[]): P3 => [v[0]!, v[1]!, v[2]!];

/** The camera pose of a keyframe. With `lookAtSelection` and a selection, the target is the centre of the selection. */
export function keyframePose(k: FlyKeyframe, lookAt: boolean, ctx: CompileContext): CameraPose {
  const c = k.view.camera;
  let target: V3 = [c.target[0], c.target[1], c.target[2]];
  if (lookAt && k.view.selection.length > 0) {
    const centre = ctx.selectionCenter?.(k.view.selection);
    if (centre) target = [centre[0], centre[1], centre[2]];
  }
  return { position: [c.position[0], c.position[1], c.position[2]], target, up: [c.up[0], c.up[1], c.up[2]], fovDeg: c.fov, ortho: c.ortho };
}

function angleBetween(a: P3, b: P3): number {
  const la = Math.hypot(...a);
  const lb = Math.hypot(...b);
  if (la < 1e-12 || lb < 1e-12) return 0;
  const d = (a[0] * b[0] + a[1] * b[1] + a[2] * b[2]) / (la * lb);
  return Math.acos(Math.min(1, Math.max(-1, d)));
}

/** The travel seconds of each segment and the arrival, departure and total times. */
export function timingOf(ft: FlyThrough, poses: readonly CameraPose[]): Timing {
  const n = ft.keyframes.length;
  const pos = new Spline3(poses.map((p) => toP3(p.position)));
  const speed = Math.max(ft.speed, 1e-6);
  const travel: number[] = [0];
  for (let i = 1; i < n; i++) {
    const k = ft.keyframes[i]!;
    if (k.travel !== undefined && Number.isFinite(k.travel)) {
      travel.push(Math.max(0, k.travel));
    } else if (ft.timing === 'seconds') {
      travel.push(Math.max(0, ft.segmentS));
    } else {
      const a = poses[i - 1]!;
      const b = poses[i]!;
      const dir0: P3 = [a.target[0] - a.position[0], a.target[1] - a.position[1], a.target[2] - a.position[2]];
      const dir1: P3 = [b.target[0] - b.position[0], b.target[1] - b.position[1], b.target[2] - b.position[2]];
      const dist = (Math.hypot(...dir0) + Math.hypot(...dir1)) / 2;
      // Path length plus half the way the target moves relative to the camera plus the turn of the view direction at the viewing distance.
      const rel = Math.hypot(b.target[0] - a.target[0] - (b.position[0] - a.position[0]), b.target[1] - a.target[1] - (b.position[1] - a.position[1]), b.target[2] - a.target[2] - (b.position[2] - a.position[2]));
      const eff = (pos.segLen[i - 1] ?? 0) + 0.5 * rel + 0.5 * dist * angleBetween(dir0, dir1);
      travel.push(Math.max(MIN_TRAVEL_S, eff / speed));
    }
  }
  const arrive: number[] = [];
  const depart: number[] = [];
  let t = 0;
  for (let i = 0; i < n; i++) {
    t += travel[i]!;
    arrive.push(t);
    t += Math.max(0, ft.keyframes[i]!.hold);
    depart.push(t);
  }
  return { arrive, depart, travel, total: n > 0 ? depart[n - 1]! : 0 };
}

function hiddenOf(v: SavedView): { mode: 'hide' | 'show'; ids: string[] } {
  return v.hides ? { mode: v.hides.mode, ids: v.hides.ids } : { mode: 'hide', ids: [] };
}

function setDiff(a: readonly string[], b: readonly string[]): string[] {
  const s = new Set(b);
  return a.filter((x) => !s.has(x));
}

function sameList(a: readonly string[], b: readonly string[]): boolean {
  if (a.length !== b.length) return false;
  const s = new Set(a);
  return b.every((x) => s.has(x));
}

/**
 * The visibility cue that changes the hidden elements of view A into those of view B, or null when they are the same.
 * `a` null is the start: everything is first shown.
 */
export function visibilityChange(a: SavedView | null, b: SavedView): Omit<Extract<Cue, { kind: 'visibility' }>, 'at' | 'dur' | 'kind'> | null {
  const hb = hiddenOf(b);
  const ref = (ids: string[]): ElementRef => ({ globalIds: ids });
  if (!a) {
    if (hb.mode === 'show') return { isolate: ref(hb.ids), showAll: true };
    return hb.ids.length > 0 ? { showAll: true, hide: ref(hb.ids) } : { showAll: true };
  }
  const ha = hiddenOf(a);
  if (ha.mode === 'hide' && hb.mode === 'hide') {
    const hide = setDiff(hb.ids, ha.ids);
    const show = setDiff(ha.ids, hb.ids);
    if (hide.length === 0 && show.length === 0) return null;
    const out: Omit<Extract<Cue, { kind: 'visibility' }>, 'at' | 'dur' | 'kind'> = {};
    if (hide.length) out.hide = ref(hide);
    if (show.length) out.show = ref(show);
    return out;
  }
  if (ha.mode === 'show' && hb.mode === 'show') {
    if (sameList(ha.ids, hb.ids)) return null;
    const show = setDiff(hb.ids, ha.ids);
    const hide = setDiff(ha.ids, hb.ids);
    const out: Omit<Extract<Cue, { kind: 'visibility' }>, 'at' | 'dur' | 'kind'> = {};
    if (hide.length) out.hide = ref(hide);
    if (show.length) out.show = ref(show);
    return out;
  }
  // One isolates and the other hides: describe the target.
  if (hb.mode === 'show') return { isolate: ref(hb.ids) };
  return hb.ids.length > 0 ? { showAll: true, hide: ref(hb.ids) } : { showAll: true };
}

/** Compile a fly-through to a score: one camera path, a view cue per keyframe, visibility, selection and caption cues. */
export function compileFlyThrough(ft: FlyThrough, ctx: CompileContext = {}): Score {
  const keys = ft.keyframes;
  const score: Score = { schema: SCORE_SCHEMA, duration: 0, cues: [], source: { kind: 'keyframes', name: ft.name } };
  if (keys.length === 0) return score;
  if (ft.loop) score.loop = true;
  const poses = keys.map((k) => keyframePose(k, ft.lookAtSelection, ctx));
  const tm = timingOf(ft, poses);
  const cues: Cue[] = [];

  // The camera path: a held keyframe is listed twice (arrival, departure).
  const pathPoses: CameraPose[] = [];
  const times: number[] = [];
  const easeAt: boolean[] = [];
  keys.forEach((k, i) => {
    pathPoses.push(poses[i]!);
    times.push(tm.arrive[i]!);
    easeAt.push(k.ease);
    if (k.hold > 0) {
      pathPoses.push(poses[i]!);
      times.push(tm.depart[i]!);
      easeAt.push(k.ease);
    }
  });
  if (keys.length > 1 || keys[0]!.hold > 0) {
    cues.push({ kind: 'cameraPath', at: 0, dur: tm.total, ease: 'inOut', poses: pathPoses, times, easeAt, label: ft.name });
  }

  keys.forEach((k, i) => {
    const seg = tm.travel[i]!;
    const segStart = i === 0 ? 0 : tm.depart[i - 1]!;
    const arrive = tm.arrive[i]!;
    const prev = i === 0 ? null : keys[i - 1]!;
    const label = k.name;

    // Settings, section, explode, projection: blended over the travel, discrete changes at switchAt.
    const state = {
      camera: poses[i]!,
      params: JSON.parse(JSON.stringify(k.view.params ?? {})) as Record<string, unknown>,
      presetId: k.view.preset ?? null,
      explode: k.view.exploded === true,
    };
    cues.push({ kind: 'view', at: segStart, dur: i === 0 ? 0 : seg, ease: 'inOut', switchAt: k.switchAt, label, state: state as never });

    // Selection starts a little before the camera arrives.
    const selNow = k.view.selection;
    const selPrev = prev ? prev.view.selection : [];
    if (i === 0 || !sameList(selNow, selPrev)) {
      const lead = i === 0 ? 0 : Math.min(SELECT_LEAD_S, seg * 0.3);
      cues.push({ kind: 'select', at: Math.max(segStart, arrive - lead), dur: 0, elements: selNow.length ? { globalIds: [...selNow] } : null, label });
    }

    // Visibility: what differs between the two keyframes fades over the end of the travel.
    const change = visibilityChange(prev ? prev.view : null, k.view);
    if (change) {
      if (i > 0 && k.fade && seg > 0) {
        const len = Math.min(1, Math.max(0.05, k.fadeFraction)) * seg;
        cues.push({ kind: 'visibility', at: arrive - len, dur: len, ease: 'inOut', ...change, label });
      } else {
        const at = i === 0 ? 0 : segStart + seg * (k.switchAt === 'start' ? 0 : k.switchAt === 'mid' ? 0.5 : 1);
        cues.push({ kind: 'visibility', at, dur: 0, ...change, label });
      }
    }

    const c = k.caption;
    if (c && ((c.title ?? '').trim() || (c.text ?? '').trim())) {
      const cue: Extract<Cue, { kind: 'caption' }> = { kind: 'caption', at: arrive, dur: k.hold > 0 ? k.hold : DEFAULT_CAPTION_S, label };
      if (c.title?.trim()) cue.title = c.title;
      if (c.text?.trim()) cue.text = c.text;
      cues.push(cue);
    }

    // Labels and the hover card of the selection, for as long as a caption would show.
    const sel = k.view.selection;
    if (sel.length > 0 && (k.labels || k.hover)) {
      const dur = k.hold > 0 ? k.hold : DEFAULT_CAPTION_S;
      if (k.labels) cues.push({ kind: 'label', at: arrive, dur, elements: { globalIds: [...sel] }, fields: k.labels.fields.length ? [...k.labels.fields] : [...DEFAULT_LABEL_FIELDS], label });
      if (k.hover) cues.push({ kind: 'hover', at: arrive, dur, elements: { globalIds: [sel[0]!] }, label });
    }
  });

  score.cues = cues;
  score.duration = Math.max(tm.total, scoreEnd(cues));
  return score;
}

/** Seconds at which each keyframe is reached (for the timeline playhead and "play from keyframe"). */
export function keyframeTimes(ft: FlyThrough, ctx: CompileContext = {}): Timing {
  return timingOf(ft, ft.keyframes.map((k) => keyframePose(k, ft.lookAtSelection, ctx)));
}

// ---------------------------------------------------------------- legacy import

const LEGACY_TOGGLE_PATHS: Record<string, string[]> = {
  reveal: ['cinematic', 'reveal'],
  sweep: ['cinematic', 'sweep', 'enabled'],
  depthGrade: ['cinematic', 'grade', 'enabled'],
  bloom: ['cinematic', 'bloom'],
  edgeGlow: ['cinematic', 'edgeGlow'],
};

/** Settings paths a legacy keyframe toggle maps to (ao and vignette are playback extras that params do not hold). */
export function legacyParams(toggles: Record<string, unknown>): Record<string, unknown> {
  const params: Record<string, unknown> = {};
  for (const [k, keys] of Object.entries(LEGACY_TOGGLE_PATHS)) {
    const v = toggles[k];
    if (typeof v !== 'boolean') continue;
    let cur = params;
    keys.slice(0, -1).forEach((key) => {
      cur[key] = (cur[key] as Record<string, unknown> | undefined) ?? {};
      cur = cur[key] as Record<string, unknown>;
    });
    cur[keys[keys.length - 1]!] = v;
  }
  return params;
}

function isV3(v: unknown): v is Vec3 {
  return Array.isArray(v) && v.length === 3 && v.every((x) => typeof x === 'number' && Number.isFinite(x));
}

/**
 * The old fly-through keyframes (`xray.flythrough.<modelName>`: camera, selection, 7 toggles, name) as a fly-through named
 * "Imported". Equal time per segment as the old player had (its stored `segmentSeconds`). Null when there are none.
 */
export function migrateLegacy(text: string | null | undefined, fov = 50, now = new Date()): FlyThrough | null {
  if (!text) return null;
  let data: unknown;
  try {
    data = JSON.parse(text);
  } catch {
    return null;
  }
  const list = Array.isArray(data) ? data : (data as { keyframes?: unknown } | null)?.keyframes;
  if (!Array.isArray(list)) return null;
  const seg = !Array.isArray(data) && typeof (data as { segmentSeconds?: unknown }).segmentSeconds === 'number' ? (data as { segmentSeconds: number }).segmentSeconds : 2.5;
  const ft = newFlyThrough('Imported', 3, now.getTime());
  ft.timing = 'seconds';
  ft.segmentS = seg > 0 ? seg : 2.5;
  const iso = now.toISOString();
  list.forEach((raw, i) => {
    if (!raw || typeof raw !== 'object') return;
    const o = raw as Record<string, unknown>;
    if (!isV3(o['position']) || !isV3(o['target'])) return;
    const name = typeof o['name'] === 'string' && o['name'].trim() ? o['name'] : `Keyframe ${i + 1}`;
    const sel = Array.isArray(o['selection']) ? o['selection'].filter((x): x is string => typeof x === 'string') : [];
    const toggles = o['toggles'] && typeof o['toggles'] === 'object' ? (o['toggles'] as Record<string, unknown>) : {};
    const params = legacyParams(toggles);
    const extra: Record<string, boolean> = {};
    for (const k of ['ao', 'vignette'] as const) if (typeof toggles[k] === 'boolean') extra[k] = toggles[k] as boolean;
    if (Object.keys(extra).length) params['post'] = extra;
    const view: SavedView = {
      id: newFlyId('v', now.getTime()),
      name,
      created: iso,
      updated: iso,
      camera: { position: [...o['position']] as Vec3, target: [...o['target']] as Vec3, up: [0, 1, 0], fov, ortho: false },
      selection: sel,
      params,
    };
    ft.keyframes.push(newKeyframe(view, { name, fade: false, ease: false }, now.getTime()));
  });
  return ft.keyframes.length > 0 ? ft : null;
}

// ---------------------------------------------------------------- storage

export function flyStorageKey(identityKey: string): string {
  return FLYTHROUGHS_KEY_PREFIX + identityKey;
}

function num(v: unknown, d: number, min = 0, max = Infinity): number {
  return typeof v === 'number' && Number.isFinite(v) ? Math.min(max, Math.max(min, v)) : d;
}

function parseKeyframe(raw: unknown): FlyKeyframe | null {
  if (!raw || typeof raw !== 'object') return null;
  const o = raw as Record<string, unknown>;
  const v = sanitizeView(o['view']);
  if (typeof v === 'string') return null;
  const k = newKeyframe(v, {});
  if (typeof o['id'] === 'string') k.id = o['id'];
  if (typeof o['name'] === 'string' && o['name'].trim()) k.name = o['name'];
  if (typeof o['viewId'] === 'string') k.viewId = o['viewId'];
  if (typeof o['travel'] === 'number' && Number.isFinite(o['travel']) && o['travel'] >= 0) k.travel = o['travel'];
  k.hold = num(o['hold'], 0, 0, 3600);
  k.ease = o['ease'] !== false;
  k.fade = o['fade'] !== false;
  k.fadeFraction = num(o['fadeFraction'], DEFAULT_FADE_FRACTION, 0.05, 1);
  const sw = o['switchAt'];
  k.switchAt = sw === 'start' || sw === 'mid' || sw === 'end' ? sw : 'end';
  const c = o['caption'];
  if (c && typeof c === 'object') {
    const cap: FlyCaption = {};
    const t = (c as FlyCaption).title;
    const x = (c as FlyCaption).text;
    if (typeof t === 'string' && t) cap.title = t;
    if (typeof x === 'string' && x) cap.text = x;
    if (cap.title || cap.text) k.caption = cap;
  }
  const lb = o['labels'];
  if (lb && typeof lb === 'object') {
    const f = (lb as { fields?: unknown }).fields;
    k.labels = { fields: cleanFields(f) };
  }
  if (o['hover'] === true) k.hover = true;
  return k;
}

/** Label field names from stored data: strings, trimmed, no duplicates, at most 8; empty means the defaults. */
export function cleanFields(raw: unknown): string[] {
  const out: string[] = [];
  if (Array.isArray(raw)) {
    for (const f of raw) {
      if (typeof f !== 'string') continue;
      const t = f.trim();
      if (t && t.length <= 80 && !out.includes(t)) out.push(t);
      if (out.length >= MAX_LABEL_FIELDS) break;
    }
  }
  return out.length ? out : [...DEFAULT_LABEL_FIELDS];
}

export function parseFlyThrough(raw: unknown): FlyThrough | null {
  if (!raw || typeof raw !== 'object') return null;
  const o = raw as Record<string, unknown>;
  const ft = newFlyThrough(typeof o['name'] === 'string' ? o['name'] : 'Fly-through', num(o['speed'], 3, 0.01, 10000));
  if (typeof o['id'] === 'string') ft.id = o['id'];
  ft.timing = o['timing'] === 'seconds' ? 'seconds' : 'speed';
  ft.segmentS = num(o['segmentS'], DEFAULT_SEGMENT_S, 0, 3600);
  ft.lookAtSelection = o['lookAtSelection'] === true;
  if (o['loop'] === true) ft.loop = true;
  if (Array.isArray(o['keyframes'])) {
    for (const r of o['keyframes'].slice(0, MAX_KEYFRAMES)) {
      const k = parseKeyframe(r);
      if (k) ft.keyframes.push(k);
    }
  }
  return ft;
}

/** Read a stored or imported document. Bad entries are dropped; unreadable text gives null. */
export function parseFlyDoc(text: string | null | undefined): FlyDoc | null {
  if (!text) return null;
  let data: unknown;
  try {
    data = JSON.parse(text);
  } catch {
    return null;
  }
  if (!data || typeof data !== 'object') return null;
  const o = data as Record<string, unknown>;
  if (typeof o['schema'] === 'string' && !o['schema'].startsWith('xray-flythroughs/1')) return null;
  const list = Array.isArray(o['flythroughs']) ? o['flythroughs'] : Array.isArray(data) ? (data as unknown[]) : null;
  if (!list) return null;
  const flythroughs = list.map(parseFlyThrough).filter((f): f is FlyThrough => f !== null);
  const active = typeof o['active'] === 'string' && flythroughs.some((f) => f.id === o['active']) ? (o['active'] as string) : (flythroughs[0]?.id ?? null);
  const doc: FlyDoc = { schema: FLYTHROUGHS_SCHEMA, flythroughs, active };
  if (o['hud'] !== undefined) doc.hud = sanitizeHud(o['hud']);
  return doc;
}

export function serializeFlyDoc(doc: FlyDoc, withThumbs = true): string {
  const copy: FlyDoc = JSON.parse(JSON.stringify(doc)) as FlyDoc;
  if (!withThumbs) for (const f of copy.flythroughs) for (const k of f.keyframes) delete k.view.thumb;
  return JSON.stringify(copy);
}
