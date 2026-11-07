// Saved views: named viewpoints that people come back to. Pure module (no DOM, no three.js), tested in
// tests/views-*.test.ts.
//
// A saved view holds the camera (position, target, up, field of view, pseudo-orthographic flag), the selection, the
// user hides and pins (an isolate is stored as the short list of the elements that stay visible), the exploded flag,
// the active preset id (for display), a params snapshot (`xray-params/1` subset: x-ray, sightlines, display, view
// modes, imaging, section, cinematic, ...) and a small JPEG thumbnail. Elements are referred to by IFC GlobalId, so a
// view survives a reconversion or a reload of the model; GlobalIds that the loaded model lacks are reported.
//
// Storage layout: localStorage key `xray.views.<modelName>` -> `xray-views/1` document
//   { schema: "xray-views/1", model, views: [SavedView, ...] }
// A share link carries one view: `#view=<base64url of JSON { schema: "xray-view/1", model, view }>`, with the params
// reduced to the leaves that differ from the factory state and no thumbnail.

export const VIEWS_SCHEMA = 'xray-views/1';
export const VIEW_SHARE_SCHEMA = 'xray-view/1';
export const VIEWS_KEY_PREFIX = 'xray.views.';
/** Thumbnail size in CSS pixels (the JPEG is this size). */
export const THUMB_W = 160;
export const THUMB_H = 100;

export type Vec3 = [number, number, number];

export interface ViewCamera {
  position: Vec3;
  target: Vec3;
  /** Screen up in world space (the view cube can roll the camera). */
  up: Vec3;
  /** Vertical field of view in degrees (the perspective one when `ortho` is true). */
  fov: number;
  /** The pseudo-orthographic projection (src/input/navigation.ts) was on. */
  ortho: boolean;
}

/** User hides: `hide` lists the hidden elements; `show` (an isolate) lists the only elements left visible. */
export interface ViewHides {
  mode: 'hide' | 'show';
  ids: string[];
}

export interface SavedView {
  id: string;
  name: string;
  created: string;
  updated: string;
  camera: ViewCamera;
  /** Selected GlobalIds (the selection is the focus). */
  selection: string[];
  hides?: ViewHides;
  pins?: string[];
  exploded?: boolean;
  /** Clip planes set by something other than the section tool (a BCF viewpoint), viewer frame. */
  clip?: Array<{ normal: Vec3; point: Vec3 }>;
  /** Id of the preset that was marked active when the view was saved (display only). */
  preset?: string;
  /** Params subset (`xray-params/1` keys). Restoring merges it over the factory state, so a partial one is fine. */
  params: Record<string, unknown>;
  /** data:image/jpeg URL, THUMB_W x THUMB_H. */
  thumb?: string;
}

export interface ViewsDocument {
  schema: typeof VIEWS_SCHEMA;
  model: string;
  views: SavedView[];
}

/**
 * Params sections that a view never stores: document metadata, the camera and overrides (stored by the view itself),
 * per-model data (sets, class styles), user preferences that are not part of a look (keys, panels, cube), and tools with
 * their own documents (BCF topics, point clouds, measurements, XR). `views` itself is left out to avoid recursion.
 */
export const VIEW_EXCLUDED_SECTIONS: readonly string[] = [
  'schema', 'exportedAt', 'model', 'viewer', 'camera', 'overrides', 'selectionSets', 'classStyles', 'materialAliases',
  'keymap', 'views', 'bcf', 'xr', 'pointcloud', 'measure', 'hoverInfo', 'gizmo', 'penetrations', 'cleanup', 'topBar',
];

// ---------------------------------------------------------------- small helpers

export function isObj(v: unknown): v is Record<string, unknown> {
  return !!v && typeof v === 'object' && !Array.isArray(v);
}

function clone<T>(v: T): T {
  return JSON.parse(JSON.stringify(v)) as T;
}

function isNum(v: unknown): v is number {
  return typeof v === 'number' && Number.isFinite(v);
}

function isVec3(v: unknown): v is Vec3 {
  return Array.isArray(v) && v.length === 3 && v.every(isNum);
}

export function round(n: number, step = 1e-6): number {
  return Math.round(n / step) * step;
}

export function roundVec(v: readonly number[], step = 1e-6): Vec3 {
  return [round(v[0]!, step), round(v[1]!, step), round(v[2]!, step)];
}

/** The params sections a view keeps, from a collected params document. */
export function filterParams(doc: Record<string, unknown>, excluded: readonly string[] = VIEW_EXCLUDED_SECTIONS): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(doc)) if (!excluded.includes(k) && v !== undefined) out[k] = clone(v);
  return out;
}

// ---------------------------------------------------------------- ids and names

let idCounter = 0;

/** A short id, unique among `taken`. */
export function newViewId(taken: ReadonlySet<string> = new Set(), now = Date.now()): string {
  for (;;) {
    const id = `v${now.toString(36)}${(idCounter++).toString(36)}${Math.floor(Math.random() * 1296).toString(36)}`;
    if (!taken.has(id)) return id;
  }
}

/** `name`, or `name 2`, `name 3`, ... when the name is taken (case-insensitive). */
export function uniqueName(name: string, views: readonly SavedView[], except?: string): string {
  const base = name.trim() || 'View';
  const taken = new Set(views.filter((v) => v.id !== except).map((v) => v.name.toLowerCase()));
  if (!taken.has(base.toLowerCase())) return base;
  const stem = base.replace(/\s+\d+$/, '');
  for (let n = 2; ; n++) {
    const c = `${stem} ${n}`;
    if (!taken.has(c.toLowerCase())) return c;
  }
}

/** The next default name: "View 1", "View 2", ... */
export function defaultName(views: readonly SavedView[]): string {
  return uniqueName(`View ${views.length + 1}`, views);
}

// ---------------------------------------------------------------- hides and isolate

/**
 * Store the hides compactly: when more than half of the model is hidden (an isolate), store the visible elements.
 * `hidden` and `all` are GlobalIds.
 */
export function compactHides(hidden: readonly string[], all: readonly string[]): ViewHides | undefined {
  if (hidden.length === 0) return undefined;
  if (hidden.length * 2 <= all.length) return { mode: 'hide', ids: [...hidden] };
  const h = new Set(hidden);
  return { mode: 'show', ids: all.filter((g) => !h.has(g)) };
}

export interface Resolved {
  ids: number[];
  missing: string[];
}

/** GlobalIds to element ids of the loaded model; the GlobalIds it lacks go to `missing`. */
export function resolveGlobalIds(byGlobalId: ReadonlyMap<string, number>, gids: readonly string[]): Resolved {
  const ids: number[] = [];
  const missing: string[] = [];
  for (const g of gids) {
    const id = byGlobalId.get(g);
    if (id === undefined) missing.push(g);
    else ids.push(id);
  }
  return { ids, missing };
}

/** The hidden element ids of `hides` in a model of `count` elements. */
export function expandHides(hides: ViewHides | undefined, byGlobalId: ReadonlyMap<string, number>, count: number): Resolved {
  if (!hides) return { ids: [], missing: [] };
  const r = resolveGlobalIds(byGlobalId, hides.ids);
  if (hides.mode === 'hide') return r;
  const shown = new Set(r.ids);
  const ids: number[] = [];
  for (let i = 0; i < count; i++) if (!shown.has(i)) ids.push(i);
  return { ids, missing: r.missing };
}

// ---------------------------------------------------------------- params: diff, merge, changed sections

function sameJson(a: unknown, b: unknown): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

/** Leaves of `full` that differ from `base` (objects recurse; arrays and scalars are leaves). Undefined when equal. */
export function diffParams(full: unknown, base: unknown): unknown {
  if (isObj(full) && isObj(base)) {
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(full)) {
      if (!(k in base)) {
        out[k] = clone(v);
        continue;
      }
      const d = diffParams(v, base[k]);
      if (d !== undefined) out[k] = d;
    }
    return Object.keys(out).length > 0 ? out : undefined;
  }
  return sameJson(full, base) ? undefined : clone(full);
}

/** `over` merged into a copy of `base` (objects recurse; arrays and scalars replace). */
export function mergeParams(base: unknown, over: unknown): unknown {
  if (!isObj(base) || !isObj(over)) return over === undefined ? clone(base) : clone(over);
  const out: Record<string, unknown> = clone(base);
  for (const [k, v] of Object.entries(over)) out[k] = k in out ? mergeParams(out[k], v) : clone(v);
  return out;
}

/** Top-level sections of `target` whose value differs from `current`: the only ones a restore needs to apply. */
export function changedSections(target: Record<string, unknown>, current: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(target)) if (!sameJson(v, current[k])) out[k] = clone(v);
  return out;
}

// ---------------------------------------------------------------- validation and versioning

function str(v: unknown): string | undefined {
  return typeof v === 'string' ? v : undefined;
}

function strList(v: unknown): string[] | null {
  return Array.isArray(v) && v.every((x) => typeof x === 'string') ? [...(v as string[])] : null;
}

/**
 * A clean copy of one view, or a reason why it cannot be used. Unknown fields are dropped; a missing id, time or up
 * vector is filled in. Older or foreign shapes accepted: `camera` with only position and target, `selection` absent.
 */
export function sanitizeView(raw: unknown, now = new Date()): SavedView | string {
  if (!isObj(raw)) return 'not an object';
  const name = str(raw['name'])?.trim();
  if (!name) return 'no name';
  const c = raw['camera'];
  if (!isObj(c) || !isVec3(c['position']) || !isVec3(c['target'])) return `"${name}": camera needs position and target`;
  const iso = now.toISOString();
  const v: SavedView = {
    id: str(raw['id']) || newViewId(),
    name,
    created: str(raw['created']) ?? iso,
    updated: str(raw['updated']) ?? str(raw['created']) ?? iso,
    camera: {
      position: [...c['position']] as Vec3,
      target: [...c['target']] as Vec3,
      up: isVec3(c['up']) ? ([...c['up']] as Vec3) : [0, 1, 0],
      fov: isNum(c['fov']) && c['fov'] > 0 && c['fov'] < 180 ? c['fov'] : 50,
      ortho: c['ortho'] === true,
    },
    selection: strList(raw['selection']) ?? [],
    params: isObj(raw['params']) ? clone(raw['params']) : {},
  };
  const h = raw['hides'];
  if (isObj(h) && (h['mode'] === 'hide' || h['mode'] === 'show')) {
    const ids = strList(h['ids']);
    if (ids) v.hides = { mode: h['mode'], ids };
  }
  const pins = strList(raw['pins']);
  if (pins && pins.length) v.pins = pins;
  if (raw['exploded'] === true) v.exploded = true;
  const clip = raw['clip'];
  if (Array.isArray(clip)) {
    const planes = clip.filter((p) => isObj(p) && isVec3(p['normal']) && isVec3(p['point'])).map((p) => ({
      normal: [...(p as { normal: Vec3 }).normal] as Vec3,
      point: [...(p as { point: Vec3 }).point] as Vec3,
    }));
    if (planes.length) v.clip = planes;
  }
  const preset = str(raw['preset']);
  if (preset) v.preset = preset;
  const thumb = str(raw['thumb']);
  if (thumb && /^data:image\/(jpeg|png|webp);base64,/.test(thumb)) v.thumb = thumb;
  return v;
}

export interface ParsedViews {
  views: SavedView[];
  /** Entries that were left out, with the reason. */
  bad: string[];
  /** The model the document names, when it names one. */
  model?: string;
  /** Set when the whole document was refused (wrong schema, newer version, not JSON). */
  error?: string;
}

/**
 * Read a views document: an `xray-views/1` document, a bare array of views (accepted as version 1), or a single shared
 * view (`xray-view/1`). A newer major version (`xray-views/2`) is refused with a message rather than misread.
 */
export function parseViewsDocument(input: unknown, now = new Date()): ParsedViews {
  let doc = input;
  if (typeof doc === 'string') {
    try {
      doc = JSON.parse(doc);
    } catch (e) {
      return { views: [], bad: [], error: `not JSON (${e instanceof Error ? e.message : String(e)})` };
    }
  }
  let list: unknown[];
  let model: string | undefined;
  if (Array.isArray(doc)) list = doc;
  else if (isObj(doc)) {
    const schema = str(doc['schema']);
    if (schema === VIEW_SHARE_SCHEMA) {
      list = [doc['view']];
      model = str(doc['model']);
    } else if (schema === VIEWS_SCHEMA || (schema === undefined && Array.isArray(doc['views']))) {
      if (!Array.isArray(doc['views'])) return { views: [], bad: [], error: 'no "views" list' };
      list = doc['views'];
      model = str(doc['model']);
    } else if (schema && /^xray-views?\/\d+$/.test(schema)) {
      return { views: [], bad: [], error: `schema ${schema} is newer than this viewer reads (${VIEWS_SCHEMA})` };
    } else return { views: [], bad: [], error: `not a views document (schema ${schema ?? 'missing'})` };
  } else return { views: [], bad: [], error: 'not a views document' };
  const views: SavedView[] = [];
  const bad: string[] = [];
  const ids = new Set<string>();
  list.forEach((raw, i) => {
    const v = sanitizeView(raw, now);
    if (typeof v === 'string') bad.push(`#${i + 1}: ${v}`);
    else {
      if (ids.has(v.id)) v.id = newViewId(ids);
      ids.add(v.id);
      views.push(v);
    }
  });
  return model === undefined ? { views, bad } : { views, bad, model };
}

export function viewsDocument(model: string, views: readonly SavedView[], withThumbs = true): ViewsDocument {
  return { schema: VIEWS_SCHEMA, model, views: views.map((v) => stripView(v, withThumbs)) };
}

/** A copy of the view, optionally without the thumbnail. */
export function stripView(v: SavedView, withThumb = true): SavedView {
  const c = clone(v);
  if (!withThumb) delete c.thumb;
  return c;
}

// ---------------------------------------------------------------- list operations (all return new arrays)

/** Move the view at `from` to position `to` (indices in the list before the move). */
export function moveView(views: readonly SavedView[], from: number, to: number): SavedView[] {
  const out = [...views];
  if (from < 0 || from >= out.length) return out;
  const [v] = out.splice(from, 1);
  out.splice(Math.max(0, Math.min(out.length, to)), 0, v!);
  return out;
}

export function duplicateView(views: readonly SavedView[], index: number, now = new Date()): SavedView[] {
  const src = views[index];
  if (!src) return [...views];
  const iso = now.toISOString();
  const copy: SavedView = { ...clone(src), id: newViewId(new Set(views.map((v) => v.id))), name: uniqueName(`${src.name} copy`, views), created: iso, updated: iso };
  const out = [...views];
  out.splice(index + 1, 0, copy);
  return out;
}

/**
 * Merge imported views into a list: a view with an id already in the list replaces it only when it is newer
 * (`updated`); other views are added at the end with a unique name. Ids in `skip` (deleted this session) are ignored.
 */
export function mergeViews(
  views: readonly SavedView[],
  incoming: readonly SavedView[],
  skip: ReadonlySet<string> = new Set(),
): { views: SavedView[]; added: number; replaced: number } {
  const out = [...views];
  let added = 0;
  let replaced = 0;
  for (const v of incoming) {
    if (skip.has(v.id)) continue;
    const i = out.findIndex((x) => x.id === v.id);
    if (i >= 0) {
      if (v.updated > out[i]!.updated) {
        out[i] = clone(v);
        replaced++;
      }
      continue;
    }
    out.push({ ...clone(v), name: uniqueName(v.name, out) });
    added++;
  }
  return { views: out, added, replaced };
}

/** Indices of the views whose name (or preset id) contains `filter`, case-insensitive. */
export function filterViews(views: readonly SavedView[], filter: string): number[] {
  const f = filter.trim().toLowerCase();
  const out: number[] = [];
  views.forEach((v, i) => {
    if (!f || v.name.toLowerCase().includes(f) || (v.preset ?? '').toLowerCase().includes(f)) out.push(i);
  });
  return out;
}

/** Find a view by id, then exact name, then case-insensitive name, then 1-based position ("3"). */
export function findView(views: readonly SavedView[], key: string): number {
  let i = views.findIndex((v) => v.id === key);
  if (i < 0) i = views.findIndex((v) => v.name === key);
  if (i < 0) i = views.findIndex((v) => v.name.toLowerCase() === key.trim().toLowerCase());
  if (i < 0 && /^\d+$/.test(key.trim())) {
    const n = Number(key.trim()) - 1;
    if (n >= 0 && n < views.length) i = n;
  }
  return i;
}

/** The index after `current` going `dir` (wraps; -1 current starts at the first or the last). */
export function stepIndex(current: number, count: number, dir: 1 | -1): number {
  if (count <= 0) return -1;
  if (current < 0 || current >= count) return dir > 0 ? 0 : count - 1;
  return (current + dir + count) % count;
}

// ---------------------------------------------------------------- a one-line summary

/** "x-ray · box · plane · behind · radiograph · 3 selected" */
export function viewSummary(v: SavedView): string {
  const p = v.params;
  const parts: string[] = [];
  if (p['xray'] === false) parts.push('plain');
  else if (p['xray'] === true) parts.push('x-ray');
  const sec = isObj(p['section']) ? p['section'] : null;
  if (sec && isObj(sec['box']) && sec['box']['enabled'] === true) parts.push('box');
  if (sec && isObj(sec['plane']) && sec['plane']['enabled'] === true) parts.push('plane');
  if (v.clip?.length) parts.push(`${v.clip.length} clip`);
  const vm = isObj(p['viewModes']) ? p['viewModes'] : null;
  if (vm && isObj(vm['behind']) && vm['behind']['enabled'] === true) parts.push('behind');
  if (vm && isObj(vm['peel']) && vm['peel']['enabled'] === true) parts.push('peel');
  const im = isObj(p['imaging']) ? p['imaging'] : null;
  if (im && typeof im['style'] === 'string' && im['style'] !== 'standard') parts.push(String(im['style']));
  if (v.exploded) parts.push('exploded');
  if (v.camera.ortho) parts.push('ortho');
  if (v.hides) parts.push(v.hides.mode === 'show' ? `isolate ${v.hides.ids.length}` : `${v.hides.ids.length} hidden`);
  if (v.selection.length) parts.push(`${v.selection.length} selected`);
  return parts.join(' · ');
}

// ---------------------------------------------------------------- share link

export function toBase64Url(bytes: Uint8Array): string {
  let bin = '';
  for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

export function fromBase64Url(s: string): Uint8Array {
  const b64 = s.replace(/-/g, '+').replace(/_/g, '/') + '==='.slice((s.length + 3) % 4);
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

/**
 * The share payload of one view: no thumbnail, the camera rounded to 0.1 mm, and the params reduced to the leaves that
 * differ from `base` (the factory state of the page). The receiver merges them over its own factory state.
 */
export function shareView(v: SavedView, base: Record<string, unknown> | null): SavedView {
  const c = stripView(v, false);
  c.camera = {
    ...c.camera,
    position: roundVec(c.camera.position, 1e-4),
    target: roundVec(c.camera.target, 1e-4),
    up: roundVec(c.camera.up, 1e-5),
    fov: round(c.camera.fov, 1e-4),
  };
  if (base) c.params = (diffParams(c.params, base) as Record<string, unknown> | undefined) ?? {};
  return c;
}

export function encodeViewShare(model: string, v: SavedView, base: Record<string, unknown> | null): string {
  const doc = { schema: VIEW_SHARE_SCHEMA, model, view: shareView(v, base) };
  return toBase64Url(new TextEncoder().encode(JSON.stringify(doc)));
}

export function decodeViewShare(s: string): { model?: string; view: SavedView } | null {
  try {
    const doc = JSON.parse(new TextDecoder().decode(fromBase64Url(s))) as unknown;
    if (!isObj(doc) || doc['schema'] !== VIEW_SHARE_SCHEMA) return null;
    const v = sanitizeView(doc['view']);
    if (typeof v === 'string') return null;
    const model = str(doc['model']);
    return model === undefined ? { view: v } : { model, view: v };
  } catch {
    return null;
  }
}

/** The `view=` value of a location hash (`#view=...`, also after other `&`-separated entries), or null. */
export function viewShareFromHash(hash: string): string | null {
  const m = /(?:^#?|&)view=([A-Za-z0-9_-]+)/.exec(hash);
  return m ? m[1]! : null;
}

/** The hash without its `view=` entry (other entries such as `p=` stay). */
export function hashWithoutView(hash: string): string {
  const parts = hash.replace(/^#/, '').split('&').filter((p) => p && !p.startsWith('view='));
  return parts.length ? `#${parts.join('&')}` : '';
}

export function viewShareUrl(base: { origin: string; pathname: string; search?: string }, model: string, encoded: string): string {
  const q = new URLSearchParams(base.search ?? '');
  q.set('model', model);
  return `${base.origin}${base.pathname}?${q.toString()}#view=${encoded}`;
}

// ---------------------------------------------------------------- storage

export interface StorageLike {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem?(key: string): void;
}

export function storageKey(model: string): string {
  return `${VIEWS_KEY_PREFIX}${model}`;
}

/** The stored views of a model; an empty list when there are none or the stored text cannot be read. */
export function loadViews(storage: StorageLike | null, model: string): ParsedViews {
  if (!storage) return { views: [], bad: [] };
  let text: string | null = null;
  try {
    text = storage.getItem(storageKey(model));
  } catch {
    return { views: [], bad: [], error: 'storage unavailable' };
  }
  if (!text) return { views: [], bad: [] };
  return parseViewsDocument(text);
}

/** Persist the views of a model. False when the storage refused (quota, private mode). */
export function saveViews(storage: StorageLike | null, model: string, views: readonly SavedView[]): boolean {
  if (!storage) return false;
  try {
    if (views.length === 0 && storage.removeItem) storage.removeItem(storageKey(model));
    else storage.setItem(storageKey(model), JSON.stringify(viewsDocument(model, views)));
    return true;
  } catch {
    return false;
  }
}

// ---------------------------------------------------------------- packed views seen

// A packed page (xray-pack --views) carries views in its boot document. They join the stored list once; the ids and
// `updated` stamps offered so far are kept under `xray.viewsPacked.<model>` (another prefix than the views, so a model
// called "x.y" cannot collide). A packed view the user deleted or edited does not come back on the next open; a
// packed view with a newer `updated` (the page was packed again with a changed view) is offered again.

export const PACKED_SEEN_PREFIX = 'xray.viewsPacked.';

export function packedSeenKey(model: string): string {
  return `${PACKED_SEEN_PREFIX}${model}`;
}

/** Packed view id -> the `updated` stamp offered last. Empty when nothing is stored or the text cannot be read. */
export function loadPackedSeen(storage: StorageLike | null, model: string): Record<string, string> {
  if (!storage) return {};
  try {
    const v = JSON.parse(storage.getItem(packedSeenKey(model)) ?? 'null') as unknown;
    if (!isObj(v)) return {};
    const out: Record<string, string> = {};
    for (const [k, s] of Object.entries(v)) if (typeof s === 'string') out[k] = s;
    return out;
  } catch {
    return {};
  }
}

export function savePackedSeen(storage: StorageLike | null, model: string, seen: Readonly<Record<string, string>>): boolean {
  if (!storage) return false;
  try {
    storage.setItem(packedSeenKey(model), JSON.stringify(seen));
    return true;
  } catch {
    return false;
  }
}

/**
 * Merge the views of a packed page into the stored list, skipping those already offered with the same or a newer
 * `updated` stamp (`seen`): a deleted packed view stays deleted. Returns the new list and the new `seen` record.
 */
export function mergePackedViews(
  views: readonly SavedView[],
  packed: readonly SavedView[],
  seen: Readonly<Record<string, string>>,
): { views: SavedView[]; seen: Record<string, string>; added: number; replaced: number; skipped: number } {
  const next: Record<string, string> = { ...seen };
  const fresh: SavedView[] = [];
  let skipped = 0;
  for (const v of packed) {
    const last = seen[v.id];
    if (last !== undefined && last >= v.updated) {
      skipped++;
      continue;
    }
    fresh.push(v);
    next[v.id] = v.updated;
  }
  const r = mergeViews(views, fresh);
  return { views: r.views, seen: next, added: r.added, replaced: r.replaced, skipped };
}
