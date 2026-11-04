// Export / import of the viewer parameters as a versioned JSON document (schema `xray-params/1`).
//
// The document is meant to be read elsewhere too (the Python converter, a Bonsai add-on): every field is plain
// JSON, elements are referred to by IFC globalId (never by the numeric element id, which is an array index and
// changes when the model is reconverted), and the sightline block is copied generically so new settings are
// carried without a code change here.
//
// No DOM access except the optional `window` fallbacks in ParamsEnv; the module is testable with a fake app.

import pkg from '../../package.json';
import { idsToGlobalIds, loadSets, saveSets } from '../selectionSets';
import type { SelectionSet, StorageLike } from '../selectionSets';
import type { ControllerSettings } from '../controller';
import { defaultSettings } from '../controller';
import type { ClassStyles } from '../types';
import { mergeAliases, mergeStyles, parseConfig } from '../styles';
import type { MaterialAliases } from '../styles';

export const PARAMS_SCHEMA = 'xray-params/1';

/**
 * Plugin-owned sections of the params document. A plugin registers a section in install() and
 * the section is exported, imported, used by presets and (when `share` is true) carried in the
 * share URL, without this module knowing its shape. Keys must not clash with the built-in keys.
 */
export interface ParamSection {
  /** Return the section value, or undefined to omit it (feature unavailable). Must be JSON-safe. */
  collect(): unknown;
  /** Apply a value from a document. Push dotted paths of anything it could not apply onto `bad`. */
  apply(value: unknown, bad: string[], path: string): void;
  /** Include in the share URL (keep it small). Default false. */
  share?: boolean;
}

const SECTIONS = new Map<string, ParamSection>();

export function registerParamSection(name: string, section: ParamSection): () => void {
  SECTIONS.set(name, section);
  return () => {
    if (SECTIONS.get(name) === section) SECTIONS.delete(name);
  };
}

export function paramSectionNames(): string[] {
  return [...SECTIONS.keys()];
}
export const VIEWER_VERSION: string = pkg.version;

type Vec3 = [number, number, number];

export interface XrayParams {
  schema: typeof PARAMS_SCHEMA;
  exportedAt: string;
  model: string;
  viewer: { version: string };
  xray: boolean;
  classification: Record<string, unknown>;
  /** Every key of app.settings.sightlines (samplesPerObject, alphaMin, ..., occluderScope, farWeight, layer*, ...). */
  sightlines: Record<string, unknown>;
  overrides: {
    userPinFloor: number;
    categoryFloors: Record<string, number>;
    /** GlobalIds. */
    userPins: string[];
    userHides: string[];
    /** globalId -> floor. */
    projectPins: Record<string, number>;
  };
  farMode: string;
  tiersMode: boolean;
  tiers: string[][];
  display: { edgeAlpha: number; ghostDesaturate: number; inFront: boolean };
  classStyles: ClassStyles;
  materialAliases: MaterialAliases;
  /** The cinematic plugin's config object (transient playback fields removed). Absent when the plugin is off. */
  cinematic?: Record<string, unknown>;
  /** Present only when the renderer has OIT (renderer.getOit/setOit). depthWeight: 1 = 'paper', 0 = 'flat'. */
  rendering?: { orderIndependent: boolean; depthWeight: number };
  /** Selection sets stored for this model (localStorage `xray.sets.<model>`). Absent when none are stored. */
  selectionSets?: SelectionSet[];
  camera?: { position: Vec3; target: Vec3 };
  /** Plugin sections registered with registerParamSection (viewModes, imaging, cleanup, hoverInfo, keymap, ...). */
  [section: string]: unknown;
}

// ---------------------------------------------------------------- the app, as far as this module needs it

interface Vec3Like {
  x: number;
  y: number;
  z: number;
  set(x: number, y: number, z: number): unknown;
}

interface GuiControllerLike {
  object: object;
  property: string;
  setValue(v: unknown): unknown;
  updateDisplay(): unknown;
}

/** ViewerApp satisfies this; tests pass a plain object. */
export interface ParamsApp {
  modelName: string;
  /** The GUI-bound settings object. */
  settings: ControllerSettings;
  display: { edgeAlpha: number; ghostDesaturate: number; inFront: boolean };
  controller: {
    model: { byGlobalId: Map<string, number>; elements: ReadonlyArray<{ globalId: string }>; styles?: unknown; materialAliases?: unknown };
    settings: ControllerSettings;
    setClassStyles?(styles: ClassStyles, aliases?: MaterialAliases): void;
    touch?(): void;
    refreshOverrides?(): void;
  };
  renderer: {
    camera: { position: Vec3Like };
    controls?: { target: Vec3Like; update?(): unknown };
    setEdgeAlpha?(v: number): void;
    setGhostDesaturate?(v: number): void;
    setInFront?(v: boolean): void;
    markDirty?(): void;
  };
  panel?: { controllersRecursive(): GuiControllerLike[] } | null;
  plugins?: ReadonlyArray<{ name: string; onModel?: (app: never) => void }>;
  reclassify(): void;
}

export interface ParamsEnv {
  storage?: StorageLike | null;
  /** The cinematic config object; default `window.__cinematic.cfg`. Pass null to say there is none. */
  cinematic?: object | null;
  /** Date for exportedAt. */
  now?: Date;
  version?: string;
}

function defaultStorage(): StorageLike | null {
  try {
    return typeof window !== 'undefined' ? window.localStorage : null;
  } catch {
    return null;
  }
}

function cinematicCfg(env: ParamsEnv): Record<string, unknown> | null {
  if (env.cinematic !== undefined) return env.cinematic as Record<string, unknown> | null;
  if (typeof window === 'undefined') return null;
  const c = (window as unknown as { __cinematic?: { cfg?: unknown; config?: unknown } }).__cinematic;
  const cfg = c?.cfg ?? c?.config;
  return cfg && typeof cfg === 'object' ? (cfg as Record<string, unknown>) : null;
}

/** Cinematic config fields that are playback state, not parameters. */
const TRANSIENT_CINEMATIC = new Set(['dollyPlaying', 'dollyProgress']);

// ---------------------------------------------------------------- OIT (renderer.setOit, owned by another agent)

interface OitRenderer {
  setOit?: (...a: never[]) => unknown;
  getOit?: () => unknown;
  oit?: unknown;
  oitSettings?: unknown;
}

function oitRenderer(app: ParamsApp): OitRenderer | null {
  const r = app.renderer as unknown as OitRenderer;
  if (typeof r.setOit === 'function') return r;
  const w = typeof window !== 'undefined' ? (window as unknown as { __xray?: { renderer?: OitRenderer } }).__xray?.renderer : undefined;
  return w && typeof w.setOit === 'function' ? w : null;
}

function guiControllers(app: ParamsApp): GuiControllerLike[] {
  try {
    return app.panel?.controllersRecursive() ?? [];
  } catch {
    return [];
  }
}

function num(v: unknown): number | undefined {
  return typeof v === 'number' && Number.isFinite(v) ? v : undefined;
}

function readOit(app: ParamsApp): { orderIndependent: boolean; depthWeight: number } | undefined {
  const r = oitRenderer(app);
  if (!r) return undefined;
  let o: unknown;
  try {
    o = typeof r.getOit === 'function' ? r.getOit() : (r.oitSettings ?? r.oit);
  } catch {
    o = undefined;
  }
  let on: boolean | undefined;
  let w: number | undefined;
  if (o && typeof o === 'object') {
    const q = o as Record<string, unknown>;
    const flag = q['orderIndependent'] ?? q['enabled'] ?? q['on'];
    if (typeof flag === 'boolean') on = flag;
    w = num(q['depthWeight'] ?? q['weight']);
  } else if (typeof o === 'boolean') on = o;
  // Fall back to the GUI controllers the OIT plugin registers under these property names.
  for (const c of guiControllers(app)) {
    const v = (c.object as Record<string, unknown>)[c.property];
    if (on === undefined && c.property === 'orderIndependent' && typeof v === 'boolean') on = v;
    if (w === undefined && c.property === 'depthWeight') w = num(v) ?? (v === 'paper' ? 1 : v === 'flat' ? 0 : undefined);
  }
  if (on === undefined && w === undefined) return undefined;
  return { orderIndependent: on ?? false, depthWeight: w ?? 0 };
}

// ---------------------------------------------------------------- collect

function clone<T>(v: T): T {
  return JSON.parse(JSON.stringify(v)) as T;
}

function round(n: number): number {
  return Math.round(n * 1e6) / 1e6;
}

function vec(v: { x: number; y: number; z: number }): Vec3 {
  return [round(v.x), round(v.y), round(v.z)];
}

export function collectParams(app: ParamsApp, env: ParamsEnv = {}): XrayParams {
  const s = app.settings;
  const cs = app.controller.settings;
  const model = app.controller.model;
  const ov = s.overrides;

  const projectPins: Record<string, number> = {};
  for (const [k, floor] of Object.entries(ov.projectPins)) {
    const g = model.elements[Number(k)]?.globalId;
    if (g !== undefined) projectPins[g] = floor;
  }

  const out: XrayParams = {
    schema: PARAMS_SCHEMA,
    exportedAt: (env.now ?? new Date()).toISOString(),
    model: app.modelName,
    viewer: { version: env.version ?? VIEWER_VERSION },
    xray: cs.xray,
    classification: clone(s.classification) as unknown as Record<string, unknown>,
    sightlines: clone(s.sightlines) as unknown as Record<string, unknown>,
    overrides: {
      userPinFloor: ov.userPinFloor,
      categoryFloors: clone(ov.categoryFloors),
      userPins: idsToGlobalIds(model as never, ov.userPins),
      userHides: idsToGlobalIds(model as never, ov.userHides),
      projectPins,
    },
    farMode: s.farMode,
    tiersMode: s.tiersMode,
    tiers: clone(s.tiers),
    display: { edgeAlpha: app.display.edgeAlpha, ghostDesaturate: app.display.ghostDesaturate, inFront: app.display.inFront },
    classStyles: clone(cs.classStyles),
    materialAliases: clone(cs.materialAliases),
  };

  const cin = cinematicCfg(env);
  if (cin) {
    const c = clone(cin);
    for (const k of TRANSIENT_CINEMATIC) delete c[k];
    out.cinematic = c;
  }

  const oit = readOit(app);
  if (oit) out.rendering = oit;

  const storage = env.storage === undefined ? defaultStorage() : env.storage;
  if (storage) {
    const sets = loadSets(storage, app.modelName);
    if (sets) out.selectionSets = sets;
  }

  const cam = app.renderer.camera.position;
  const tgt = app.renderer.controls?.target;
  if (cam && tgt) out.camera = { position: vec(cam), target: vec(tgt) };
  for (const [name, sec] of SECTIONS) {
    try {
      const v = sec.collect();
      if (v !== undefined) out[name] = clone(v);
    } catch {
      /* a failing section is left out rather than breaking the export */
    }
  }
  return out;
}

// ---------------------------------------------------------------- apply

export interface ApplyOptions {
  env?: ParamsEnv;
  /** Run app.reclassify() afterwards (default true). */
  reclassify?: boolean;
  /** Do not touch the camera (e.g. when the parameters belong to another model). */
  skipCamera?: boolean;
}

function isObj(v: unknown): v is Record<string, unknown> {
  return !!v && typeof v === 'object' && !Array.isArray(v);
}

function sameKind(cur: unknown, v: unknown): boolean {
  if (cur === undefined || cur === null) return v !== undefined && v !== null && typeof v !== 'object';
  if (Array.isArray(cur)) return Array.isArray(v);
  if (typeof cur === 'number') return num(v) !== undefined;
  return typeof cur === typeof v;
}

/** Copy `src` keys onto `dst` when the key exists there with a compatible type; the rest is reported. */
function assignKnown(dst: object, src: unknown, path: string, bad: string[]): void {
  if (!isObj(src)) {
    bad.push(path);
    return;
  }
  const d = dst as Record<string, unknown>;
  for (const [k, v] of Object.entries(src)) {
    if (!(k in d) || !sameKind(d[k], v)) {
      bad.push(`${path}.${k}`);
      continue;
    }
    d[k] = Array.isArray(v) ? clone(v) : v;
  }
}

function isVec3(v: unknown): v is Vec3 {
  return Array.isArray(v) && v.length === 3 && v.every((x) => num(x) !== undefined);
}

const MAX_LISTED = 12;

function mapGlobalIds(model: ParamsApp['controller']['model'], gids: unknown, path: string, bad: string[]): number[] | null {
  if (!Array.isArray(gids)) {
    bad.push(path);
    return null;
  }
  const out: number[] = [];
  let missing = 0;
  for (const g of gids) {
    const id = typeof g === 'string' ? model.byGlobalId.get(g) : undefined;
    if (id === undefined) {
      if (missing++ < MAX_LISTED) bad.push(`${path}[${String(g)}]`);
    } else out.push(id);
  }
  if (missing > MAX_LISTED) bad.push(`${path}[... ${missing - MAX_LISTED} more]`);
  return out;
}

/** Set a cinematic config tree, going through the GUI controller (so its onChange side effects run) when there is one. */
function applyCinematic(cfg: Record<string, unknown>, src: unknown, path: string, bad: string[], ctls: GuiControllerLike[]): void {
  if (!isObj(src)) {
    bad.push(path);
    return;
  }
  for (const [k, v] of Object.entries(src)) {
    if (TRANSIENT_CINEMATIC.has(k) && path === 'cinematic') continue;
    const cur = cfg[k];
    if (!(k in cfg)) {
      bad.push(`${path}.${k}`);
    } else if (isObj(cur)) {
      applyCinematic(cur, v, `${path}.${k}`, bad, ctls);
    } else if (!sameKind(cur, v)) {
      bad.push(`${path}.${k}`);
    } else if (cur !== v) {
      const c = ctls.find((x) => x.object === cfg && x.property === k);
      if (c) c.setValue(v);
      else cfg[k] = v;
    }
  }
}

/**
 * Apply a parameter document. Only keys that are present are touched, so a partial document (the share URL
 * subset) is fine. Returns the keys that could not be applied (unknown keys, wrong types, unknown globalIds,
 * missing renderer hooks); it never throws for bad content.
 */
export function applyParams(app: ParamsApp, params: unknown, opts: ApplyOptions = {}): string[] {
  const bad: string[] = [];
  const env = opts.env ?? {};
  if (!isObj(params)) return ['<root>'];
  const p = params;
  const s = app.settings;
  const cs = app.controller.settings;
  const model = app.controller.model;

  const known = new Set([
    'schema', 'exportedAt', 'model', 'viewer', 'xray', 'classification', 'sightlines', 'overrides', 'farMode', 'tiersMode',
    'tiers', 'display', 'classStyles', 'materialAliases', 'cinematic', 'rendering', 'selectionSets', 'camera',
  ]);
  for (const k of SECTIONS.keys()) known.add(k);
  for (const k of Object.keys(p)) if (!known.has(k)) bad.push(k);
  for (const [name, sec] of SECTIONS) {
    if (!(name in p)) continue;
    try {
      sec.apply(p[name], bad, name);
    } catch {
      bad.push(name);
    }
  }
  if (p['schema'] !== PARAMS_SCHEMA) bad.push('schema');

  if ('xray' in p) {
    if (typeof p['xray'] === 'boolean') s.xray = cs.xray = p['xray'];
    else bad.push('xray');
  }
  if ('classification' in p) assignKnown(s.classification, p['classification'], 'classification', bad);
  if ('sightlines' in p) assignKnown(s.sightlines, p['sightlines'], 'sightlines', bad);

  if ('farMode' in p) {
    if (p['farMode'] === 'opaque' || p['farMode'] === 'hidden') s.farMode = cs.farMode = p['farMode'];
    else bad.push('farMode');
  }
  if ('tiersMode' in p) {
    if (typeof p['tiersMode'] === 'boolean') s.tiersMode = cs.tiersMode = p['tiersMode'];
    else bad.push('tiersMode');
  }
  if ('tiers' in p) {
    const t = p['tiers'];
    if (Array.isArray(t) && t.every((r) => Array.isArray(r) && r.every((x) => typeof x === 'string'))) {
      s.tiers = cs.tiers = clone(t as string[][]);
    } else bad.push('tiers');
  }

  if ('overrides' in p) {
    const o = p['overrides'];
    if (!isObj(o)) bad.push('overrides');
    else {
      const ov = s.overrides;
      for (const k of Object.keys(o)) {
        if (!['userPinFloor', 'categoryFloors', 'userPins', 'userHides', 'projectPins'].includes(k)) bad.push(`overrides.${k}`);
      }
      if ('userPinFloor' in o) {
        const f = num(o['userPinFloor']);
        if (f === undefined) bad.push('overrides.userPinFloor');
        else {
          ov.userPinFloor = f;
          // The GUI slider is bound to a private copy; keep it in step without firing its onChange.
          for (const c of guiControllers(app)) {
            if (c.property === 'pinFloor') (c.object as Record<string, unknown>)[c.property] = f;
          }
        }
      }
      if ('categoryFloors' in o) {
        const cf = o['categoryFloors'];
        if (isObj(cf) && Object.values(cf).every((v) => num(v) !== undefined)) {
          for (const k of Object.keys(ov.categoryFloors)) delete ov.categoryFloors[k];
          Object.assign(ov.categoryFloors, cf);
        } else bad.push('overrides.categoryFloors');
      }
      if ('userPins' in o) {
        const ids = mapGlobalIds(model, o['userPins'], 'overrides.userPins', bad);
        if (ids) {
          ov.userPins.clear();
          for (const id of ids) ov.userPins.add(id);
        }
      }
      if ('userHides' in o) {
        const ids = mapGlobalIds(model, o['userHides'], 'overrides.userHides', bad);
        if (ids) {
          ov.userHides.clear();
          for (const id of ids) ov.userHides.add(id);
        }
      }
      if ('projectPins' in o) {
        const pp = o['projectPins'];
        if (!isObj(pp)) bad.push('overrides.projectPins');
        else {
          for (const k of Object.keys(ov.projectPins)) delete ov.projectPins[Number(k)];
          let missing = 0;
          for (const [g, f] of Object.entries(pp)) {
            const id = model.byGlobalId.get(g);
            if (id === undefined || num(f) === undefined) {
              if (missing++ < MAX_LISTED) bad.push(`overrides.projectPins[${g}]`);
            } else ov.projectPins[id] = f as number;
          }
        }
      }
    }
  }

  if ('display' in p) {
    const d = p['display'];
    if (!isObj(d)) bad.push('display');
    else {
      for (const k of Object.keys(d)) if (!['edgeAlpha', 'ghostDesaturate', 'inFront'].includes(k)) bad.push(`display.${k}`);
      const r = app.renderer;
      if ('edgeAlpha' in d) {
        const v = num(d['edgeAlpha']);
        if (v === undefined) bad.push('display.edgeAlpha');
        else {
          app.display.edgeAlpha = v;
          r.setEdgeAlpha?.(v);
        }
      }
      if ('ghostDesaturate' in d) {
        const v = num(d['ghostDesaturate']);
        if (v === undefined) bad.push('display.ghostDesaturate');
        else {
          app.display.ghostDesaturate = v;
          r.setGhostDesaturate?.(v);
        }
      }
      if ('inFront' in d) {
        if (typeof d['inFront'] === 'boolean') {
          app.display.inFront = d['inFront'];
          r.setInFront?.(d['inFront']);
        } else bad.push('display.inFront');
      }
    }
  }

  if ('classStyles' in p || 'materialAliases' in p) {
    const hasS = isObj(p['classStyles']);
    const hasA = isObj(p['materialAliases']);
    if ('classStyles' in p && !hasS) bad.push('classStyles');
    if ('materialAliases' in p && !hasA) bad.push('materialAliases');
    if (hasS || hasA) {
      // parseConfig sanitises both (drops malformed entries).
      const parsed = parseConfig({ classStyles: hasS ? p['classStyles'] : {}, materialAliases: hasA ? p['materialAliases'] : {} });
      const styles = hasS ? parsed.classStyles : cs.classStyles;
      const aliases = hasA ? parsed.materialAliases : cs.materialAliases;
      if (app.controller.setClassStyles) app.controller.setClassStyles(styles, aliases);
      else {
        cs.classStyles = styles;
        cs.materialAliases = aliases;
      }
    }
  }

  if ('rendering' in p) {
    const r = p['rendering'];
    const oit = oitRenderer(app);
    if (!isObj(r) || !oit) bad.push('rendering');
    else {
      for (const k of Object.keys(r)) if (!['orderIndependent', 'depthWeight'].includes(k)) bad.push(`rendering.${k}`);
      const on = typeof r['orderIndependent'] === 'boolean' ? r['orderIndependent'] : undefined;
      const w = num(r['depthWeight']);
      if ('orderIndependent' in r && on === undefined) bad.push('rendering.orderIndependent');
      if ('depthWeight' in r && w === undefined) bad.push('rendering.depthWeight');
      try {
        (oit.setOit as unknown as (o: { orderIndependent?: boolean; depthWeight?: number }) => unknown).call(oit, {
          ...(on !== undefined ? { orderIndependent: on } : {}),
          ...(w !== undefined ? { depthWeight: w } : {}),
        });
        // The renderer refuses OIT when the context cannot do it; say so.
        if (on !== undefined && typeof oit.getOit === 'function') {
          const now = (oit.getOit() as { orderIndependent?: boolean } | undefined)?.orderIndependent;
          if (now !== undefined && now !== on) bad.push('rendering.orderIndependent');
        }
      } catch {
        bad.push('rendering');
      }
      for (const c of guiControllers(app)) {
        if (c.property === 'orderIndependent' && on !== undefined) (c.object as Record<string, unknown>)[c.property] = on;
        if (c.property === 'depthWeight' && w !== undefined) {
          const cur = (c.object as Record<string, unknown>)[c.property];
          (c.object as Record<string, unknown>)[c.property] = typeof cur === 'string' ? (w > 0 ? 'paper' : 'flat') : w;
        }
      }
    }
  }

  if ('cinematic' in p) {
    const cfg = cinematicCfg(env);
    if (!cfg) bad.push('cinematic');
    else applyCinematic(cfg, p['cinematic'], 'cinematic', bad, guiControllers(app));
  }

  if ('selectionSets' in p) {
    const storage = env.storage === undefined ? defaultStorage() : env.storage;
    const list = p['selectionSets'];
    const ok =
      Array.isArray(list) &&
      list.every((x) => isObj(x) && typeof x['name'] === 'string' && Array.isArray(x['globalIds']) && x['globalIds'].every((g) => typeof g === 'string'));
    if (!ok || !storage) bad.push('selectionSets');
    else if (!saveSets(storage, app.modelName, (list as SelectionSet[]).map((x) => ({ name: x.name, globalIds: [...x.globalIds] })))) bad.push('selectionSets');
    else {
      // The sets view reads storage in onModel; run just the sidebar's hook so it shows the imported sets.
      const sb = app.plugins?.find((q) => q.name === 'sidebar');
      try {
        sb?.onModel?.(app as never);
      } catch {
        /* the sets are stored; the view refreshes on the next model load */
      }
    }
  }

  if ('camera' in p && !opts.skipCamera) {
    const c = p['camera'];
    if (!isObj(c) || !isVec3(c['position']) || !isVec3(c['target'])) bad.push('camera');
    else {
      app.renderer.camera.position.set(...c['position']);
      const ctl = app.renderer.controls;
      if (ctl) {
        ctl.target.set(...c['target']);
        ctl.update?.();
      }
      app.renderer.markDirty?.();
    }
  }

  app.controller.touch?.();
  app.controller.refreshOverrides?.();
  if (opts.reclassify !== false) app.reclassify();
  for (const c of guiControllers(app)) {
    try {
      c.updateDisplay();
    } catch {
      /* a controller whose object vanished */
    }
  }
  return bad;
}

// ---------------------------------------------------------------- defaults

/** Mirrors ViewerApp.display initial values (app.ts). */
export const DEFAULT_DISPLAY = { edgeAlpha: 0.8, ghostDesaturate: 0.8, inFront: true };

/**
 * The factory parameters: controller.defaultSettings() plus the app's display defaults and the class styles of
 * config < sidecar (pass the parsed /xray.config.json as `config`). Camera, cinematic, rendering and selection
 * sets are left out (reset does not touch them); pins and hides are cleared.
 */
export function defaultParams(app: ParamsApp, config?: unknown): Partial<XrayParams> {
  const d = defaultSettings();
  const cfg = parseConfig(config ?? {});
  const side = parseConfig({ classStyles: app.controller.model.styles, materialAliases: app.controller.model.materialAliases });
  return {
    schema: PARAMS_SCHEMA,
    xray: d.xray,
    classification: clone(d.classification) as unknown as Record<string, unknown>,
    sightlines: clone(d.sightlines) as unknown as Record<string, unknown>,
    overrides: { userPinFloor: d.overrides.userPinFloor, categoryFloors: clone(d.overrides.categoryFloors), userPins: [], userHides: [], projectPins: {} },
    farMode: d.farMode,
    tiersMode: d.tiersMode,
    tiers: d.tiers,
    display: { ...DEFAULT_DISPLAY },
    classStyles: mergeStyles(cfg.classStyles, side.classStyles),
    materialAliases: mergeAliases(cfg.materialAliases, side.materialAliases),
  };
}

// ---------------------------------------------------------------- share URL

/** The keys carried in a share URL. */
export const SHARE_KEYS = ['model', 'classification', 'sightlines', 'display', 'farMode', 'tiersMode', 'rendering', 'camera'] as const;

export function shareSubset(p: Partial<XrayParams>): Partial<XrayParams> {
  const out: Record<string, unknown> = { schema: PARAMS_SCHEMA };
  for (const k of SHARE_KEYS) if (p[k] !== undefined) out[k] = p[k];
  for (const [name, sec] of SECTIONS) if (sec.share && p[name] !== undefined) out[name] = p[name];
  const cam = p.camera;
  if (cam) {
    const r = (v: Vec3): Vec3 => v.map((x) => Math.round(x * 1000) / 1000) as Vec3;
    out['camera'] = { position: r(cam.position), target: r(cam.target) };
  }
  return out as Partial<XrayParams>;
}

function toBase64Url(bytes: Uint8Array): string {
  let bin = '';
  for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function fromBase64Url(s: string): Uint8Array {
  const b = s.replace(/-/g, '+').replace(/_/g, '/');
  const bin = atob(b + '='.repeat((4 - (b.length % 4)) % 4));
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

/** base64url(JSON of the share subset), without the leading `p=`. */
export function encodeShare(p: Partial<XrayParams>): string {
  return toBase64Url(new TextEncoder().encode(JSON.stringify(shareSubset(p))));
}

/** Inverse of encodeShare. Returns null for anything that does not decode to a JSON object. */
export function decodeShare(s: string): Partial<XrayParams> | null {
  try {
    const v: unknown = JSON.parse(new TextDecoder().decode(fromBase64Url(s.trim())));
    return isObj(v) ? (v as Partial<XrayParams>) : null;
  } catch {
    return null;
  }
}

/** Extract the `p=` value from a location hash like `#p=...` (also accepts `#a=1&p=...`). */
export function shareFromHash(hash: string): Partial<XrayParams> | null {
  const h = hash.startsWith('#') ? hash.slice(1) : hash;
  for (const part of h.split('&')) {
    if (part.startsWith('p=')) return decodeShare(part.slice(2));
  }
  return null;
}

export function shareUrl(p: Partial<XrayParams>, base: { origin: string; pathname: string }): string {
  const q = new URLSearchParams({ model: p.model ?? '' });
  return `${base.origin}${base.pathname}?${q.toString()}#p=${encodeShare(p)}`;
}

// ---------------------------------------------------------------- Python dict

function pyValue(v: unknown, indent: number): string {
  const pad = '    '.repeat(indent + 1);
  const end = '    '.repeat(indent);
  if (v === null || v === undefined) return 'None';
  if (typeof v === 'boolean') return v ? 'True' : 'False';
  if (typeof v === 'number') return Number.isFinite(v) ? String(v) : 'None';
  if (typeof v === 'string') return JSON.stringify(v); // JSON string syntax is a valid Python str literal
  if (Array.isArray(v)) {
    if (v.length === 0) return '[]';
    const flat = v.every((x) => x === null || typeof x !== 'object');
    if (flat && v.length <= 8) return `[${v.map((x) => pyValue(x, 0)).join(', ')}]`;
    return `[\n${v.map((x) => `${pad}${pyValue(x, indent + 1)},\n`).join('')}${end}]`;
  }
  if (typeof v === 'object') {
    const e = Object.entries(v as Record<string, unknown>).filter(([, x]) => x !== undefined);
    if (e.length === 0) return '{}';
    return `{\n${e.map(([k, x]) => `${pad}${JSON.stringify(k)}: ${pyValue(x, indent + 1)},\n`).join('')}${end}}`;
  }
  return 'None';
}

/** A Python source file defining `XRAY_PARAMS`, for Bonsai / ifcopenshell scripts. true/false/null become True/False/None. */
export function toPython(p: Partial<XrayParams>): string {
  const head = [
    '# X-ray viewer parameters (schema xray-params/1). Generated by the viewer; same keys as the JSON export.',
    '# Elements are referred to by IFC GlobalId.',
    '',
  ];
  return `${head.join('\n')}XRAY_PARAMS = ${pyValue(p, 0)}\n`;
}
