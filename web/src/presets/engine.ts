// Applying and capturing presets. A preset is a partial xray-params/1 document, so applying goes through
// applyParams (ui/params.ts); this module adds the `defaults` base (reset the touched sections first), the
// empty-object "touch" markers, the clearance switch (which is not a params field), the action list and the
// skipped-keys report. No DOM: the app is a ParamsApp, the environment is injected (see EngineEnv).

import { runAction } from '../input/actions';
import type { ViewerApp } from '../app';
import { PARAMS_SCHEMA, applyParams, collectParams, defaultParams } from '../ui/params';
import type { ParamsApp, ParamsEnv } from '../ui/params';
import { USER_GROUP, uniqueId, slugify } from './model';
import type { Preset } from './model';

export interface ClearanceSwitch {
  readonly enabled: boolean;
  setEnabled(on: boolean): void;
}

export interface EngineEnv {
  paramsEnv?: ParamsEnv;
  /**
   * Factory value of a plugin-owned section (viewModes, imaging, section, cinematic, clearance, ...), or undefined when
   * unknown. The core sections (sightlines, display, ...) come from defaultParams and do not need this.
   */
  factory?(section: string): unknown;
  /** Default: window.__xrayClearance. Pass null to say there is none. */
  clearance?: ClearanceSwitch | null;
  /** Default: runAction from input/actions. */
  runAction?(app: ViewerApp, id: string): boolean;
  /** Frame the selection (preset `frame: 'selection'`); returns false when there is nothing to frame. Default: none. */
  frameSelection?(app: ParamsApp): boolean;
}

export interface ApplyResult {
  id: string;
  name: string;
  /** Top-level keys that were applied (at least partly). */
  applied: string[];
  /** Dotted names of everything that could not be applied: unknown sections or keys, bad values, missing actions. */
  skipped: string[];
  actions: Array<{ id: string; ran: boolean }>;
  /** True when something was skipped. */
  partial: boolean;
  /** Preset `frame: 'selection'`: true when the camera was moved to the selection (false: no selection). */
  framed?: boolean;
}

/** Top-level params keys that a preset never resets (they are not "settings of a look"). */
const NEVER_RESET = new Set(['schema', 'exportedAt', 'model', 'viewer', 'camera', 'overrides', 'selectionSets', 'classStyles', 'materialAliases', 'classification', 'rendering']);
/** Core sections reset from defaultParams. */
const CORE_RESET = new Set(['xray', 'sightlines', 'farMode', 'tiersMode', 'tiers', 'display']);
/** Config trees too big to reset as a whole: only the first-level keys the preset names are reset. */
const NESTED_RESET = new Set(['cinematic']);

const isObj = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
const clone = <T>(v: T): T => JSON.parse(JSON.stringify(v)) as T;

function clearanceOf(env: EngineEnv): ClearanceSwitch | null {
  if (env.clearance !== undefined) return env.clearance;
  const c = typeof window !== 'undefined' ? (window as unknown as { __xrayClearance?: ClearanceSwitch }).__xrayClearance : undefined;
  return c && typeof c.setEnabled === 'function' ? c : null;
}

/** The sections a `defaults` preset resets: its top-level keys, minus the ones that are never reset. */
export function touchedSections(params: Record<string, unknown>): string[] {
  return Object.keys(params).filter((k) => !NEVER_RESET.has(k));
}

/** The factory values for the touched sections, as a params document (what base `defaults` applies first). */
export function resetDocument(app: ParamsApp, params: Record<string, unknown>, env: EngineEnv = {}): Record<string, unknown> {
  const doc: Record<string, unknown> = { schema: PARAMS_SCHEMA };
  const core = defaultParams(app) as Record<string, unknown>;
  for (const k of touchedSections(params)) {
    if (CORE_RESET.has(k)) {
      if (core[k] !== undefined) doc[k] = clone(core[k]);
      continue;
    }
    if (k === 'clearance') {
      const f = env.factory?.(k);
      if (isObj(f)) doc[k] = clone(f);
      continue;
    }
    const f = env.factory?.(k);
    if (f === undefined) continue;
    if (NESTED_RESET.has(k) && isObj(f)) {
      const src = params[k];
      if (!isObj(src)) continue;
      const part: Record<string, unknown> = {};
      for (const sub of Object.keys(src)) if (f[sub] !== undefined) part[sub] = clone(f[sub]);
      doc[k] = part;
    } else doc[k] = clone(f);
  }
  return doc;
}

/** The params to apply: markers (empty objects) dropped, clearance.enabled split off, schema set. */
function splitParams(params: Record<string, unknown>): { doc: Record<string, unknown>; clearanceEnabled: boolean | undefined } {
  const doc: Record<string, unknown> = {};
  let clearanceEnabled: boolean | undefined;
  for (const [k, v] of Object.entries(clone(params))) {
    if (isObj(v) && Object.keys(v).length === 0) continue;
    if (k === 'clearance' && isObj(v) && 'enabled' in v) {
      if (typeof v['enabled'] === 'boolean') clearanceEnabled = v['enabled'];
      delete v['enabled'];
      if (Object.keys(v).length === 0) continue;
    }
    doc[k] = v;
  }
  doc['schema'] = PARAMS_SCHEMA;
  return { doc, clearanceEnabled };
}

export function applyPreset(app: ParamsApp, preset: Preset, env: EngineEnv = {}): ApplyResult {
  const skipped: string[] = [];
  const { doc, clearanceEnabled } = splitParams(preset.params);
  const sw = clearanceOf(env);
  const hasCamera = 'camera' in doc;

  if (preset.base === 'defaults') {
    const reset = resetDocument(app, preset.params, env);
    // Failures while resetting (a section this build does not have) are not reported: the preset itself reports what it needs.
    applyParams(app, reset, { env: env.paramsEnv, reclassify: false, skipCamera: true });
    if (touchedSections(preset.params).includes('clearance') && sw && clearanceEnabled !== true) sw.setEnabled(false);
  }

  const bad = applyParams(app, doc, { env: env.paramsEnv, skipCamera: !hasCamera });
  for (const b of bad) if (b !== 'schema') skipped.push(b);

  if (clearanceEnabled !== undefined) {
    if (sw) sw.setEnabled(clearanceEnabled);
    else skipped.push('clearance.enabled');
  }

  const run = env.runAction ?? runAction;
  const actions: ApplyResult['actions'] = [];
  for (const id of preset.actions ?? []) {
    let ran = false;
    try {
      ran = run(app as unknown as ViewerApp, id);
    } catch {
      ran = false;
    }
    actions.push({ id, ran });
    if (!ran) skipped.push(`action:${id}`);
  }

  const applied = Object.keys(doc).filter((k) => k !== 'schema' && !skipped.includes(k));
  if (clearanceEnabled !== undefined && !applied.includes('clearance') && sw) applied.push('clearance');
  const out: ApplyResult = { id: preset.id, name: preset.name, applied, skipped, actions, partial: skipped.length > 0 };
  // Last, after the actions (section.fitSelection): the only camera move a preset makes without a `camera` key.
  if (preset.frame === 'selection') {
    let framed = false;
    try {
      framed = env.frameSelection?.(app) ?? false;
    } catch {
      framed = false;
    }
    out.framed = framed;
  }
  return out;
}

// ---------------------------------------------------------------- capture

/** Sections offered in the save form by default. */
export const DEFAULT_CAPTURE = ['sightlines', 'display', 'farMode', 'viewModes', 'imaging', 'section', 'cinematic'];

const NOT_CAPTURABLE = new Set(['schema', 'exportedAt', 'model', 'viewer', 'selectionSets', 'overrides', 'views']);

/** Section names that can be captured now: the keys of a collected params document (so only plugins that are present). */
export function captureSections(app: ParamsApp, env: EngineEnv = {}): string[] {
  const doc = collectParams(app, env.paramsEnv);
  return Object.keys(doc).filter((k) => !NOT_CAPTURABLE.has(k));
}

export interface CaptureOptions {
  name: string;
  description?: string;
  /** Default: 'current'. */
  base?: Preset['base'];
  actions?: string[];
  /** Ids already in use (the new id is made unique against them). */
  takenIds?: ReadonlySet<string>;
  frame?: Preset['frame'];
}

/** Capture the ticked sections of the current state as a user preset. `missing` lists ticked sections this build does not have. */
export function capturePreset(app: ParamsApp, sections: readonly string[], opts: CaptureOptions, env: EngineEnv = {}): { preset: Preset; missing: string[] } {
  const doc = collectParams(app, env.paramsEnv) as Record<string, unknown>;
  const params: Record<string, unknown> = { schema: PARAMS_SCHEMA };
  const missing: string[] = [];
  for (const s of sections) {
    if (NOT_CAPTURABLE.has(s)) continue;
    if (doc[s] === undefined) {
      missing.push(s);
      continue;
    }
    params[s] = clone(doc[s]);
  }
  const sw = clearanceOf(env);
  if (isObj(params['clearance']) && sw) params['clearance'] = { ...params['clearance'], enabled: sw.enabled };
  const name = opts.name.trim() || 'My preset';
  const preset: Preset = {
    id: uniqueId(slugify(name), opts.takenIds ?? new Set()),
    name,
    description: (opts.description ?? '').trim(),
    group: USER_GROUP,
    base: opts.base ?? 'current',
    params,
    builtIn: false,
  };
  if (opts.actions && opts.actions.length > 0) preset.actions = [...opts.actions];
  if (opts.frame) preset.frame = opts.frame;
  return { preset, missing };
}

// ---------------------------------------------------------------- "is the preset still what is set?"

/** Paths left out of the settings hash: they change without the user changing a setting. */
const HASH_IGNORE = ['exportedAt', 'model', 'viewer', 'camera', 'selectionSets', 'views', 'cinematic.dollyProgress', 'cinematic.dollyPlaying', 'imaging.mri.position'];

function strip(obj: unknown, path: string): void {
  const parts = path.split('.');
  let cur: unknown = obj;
  for (let i = 0; i < parts.length - 1; i++) {
    if (!isObj(cur)) return;
    cur = cur[parts[i]!];
  }
  if (isObj(cur)) delete cur[parts[parts.length - 1]!];
}

/** A short string that changes when any setting changes (camera, selection sets and playback progress excluded). */
export function settingsHash(app: ParamsApp, env: EngineEnv = {}): string {
  const doc = collectParams(app, env.paramsEnv);
  for (const p of HASH_IGNORE) strip(doc, p);
  const sw = clearanceOf(env);
  const text = JSON.stringify(doc) + (sw ? `|c${sw.enabled ? 1 : 0}` : '');
  let h = 5381;
  for (let i = 0; i < text.length; i++) h = ((h << 5) + h + text.charCodeAt(i)) | 0;
  return `${text.length}:${(h >>> 0).toString(36)}`;
}
