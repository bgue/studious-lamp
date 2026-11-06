// Capture the viewer state into a SavedView, and plan / apply the state part of a restore. No DOM and no three.js:
// the camera move, the projection switch, the explode and the clip planes are done by src/plugins/views.ts.
// Tested with a fake app in tests/views-capture.test.ts.

import { PARAMS_SCHEMA, applyParams, collectParams } from '../ui/params';
import type { ParamsApp, ParamsEnv } from '../ui/params';
import {
  changedSections,
  compactHides,
  expandHides,
  filterParams,
  mergeParams,
  newViewId,
  resolveGlobalIds,
  roundVec,
} from './model';
import type { SavedView, Vec3, ViewCamera } from './model';

interface Vec3Like {
  x: number;
  y: number;
  z: number;
  set(x: number, y: number, z: number): unknown;
}

/** ViewerApp satisfies this; tests pass a plain object. */
export type ViewsApp = ParamsApp & {
  renderer: ParamsApp['renderer'] & {
    camera: { position: Vec3Like; up?: Vec3Like; fov?: number; quaternion?: { x: number; y: number; z: number; w: number } };
  };
  controller: ParamsApp['controller'] & {
    selection: ReadonlySet<number>;
  };
  /** Replace the selection and rerun the classification (ViewerApp.selectIds). */
  selectIds?(ids: number[]): void;
};

export interface CaptureOptions {
  paramsEnv?: ParamsEnv;
  /** The pseudo-orthographic projection is on. */
  ortho?: boolean;
  exploded?: boolean;
  /** Id of the active preset. */
  preset?: string | null;
  /** Clip planes that the section tool does not own (a BCF viewpoint); null or empty for none. */
  clip?: Array<{ normal: Vec3; point: Vec3 }> | null;
  thumb?: string | null;
  now?: Date;
  /** Ids already used, so the new id is unique. */
  takenIds?: ReadonlySet<string>;
}

function vec(v: Vec3Like): Vec3 {
  return roundVec([v.x, v.y, v.z]);
}

/** The current params, reduced to the sections a view keeps. */
export function currentViewParams(app: ParamsApp, env?: ParamsEnv): Record<string, unknown> {
  return filterParams(collectParams(app, env) as Record<string, unknown>);
}

export function captureCamera(app: ViewsApp, ortho = false): ViewCamera {
  const cam = app.renderer.camera;
  const tgt = app.renderer.controls?.target;
  // The screen up (from the orientation when known): it says how the view cube rolled the camera, and a top view
  // needs it to keep its azimuth. camera.up is world up for an unrolled camera.
  let up: Vec3 = cam.up ? vec(cam.up) : [0, 1, 0];
  const q = cam.quaternion;
  if (q) up = roundVec([2 * (q.x * q.y - q.w * q.z), 1 - 2 * (q.x * q.x + q.z * q.z), 2 * (q.y * q.z + q.w * q.x)]);
  return {
    position: vec(cam.position),
    target: tgt ? vec(tgt) : [0, 0, 0],
    up,
    fov: typeof cam.fov === 'number' ? cam.fov : 50,
    ortho,
  };
}

/** A new SavedView from the current state. */
export function captureView(app: ViewsApp, name: string, opts: CaptureOptions = {}): SavedView {
  const model = app.controller.model;
  const els = model.elements;
  const gid = (id: number): string | undefined => els[id]?.globalId;
  const toGids = (ids: Iterable<number>): string[] => {
    const out: string[] = [];
    for (const id of ids) {
      const g = gid(id);
      if (g !== undefined) out.push(g);
    }
    return out;
  };
  const ov = app.settings.overrides;
  const iso = (opts.now ?? new Date()).toISOString();
  const v: SavedView = {
    id: newViewId(opts.takenIds),
    name: name.trim() || 'View',
    created: iso,
    updated: iso,
    camera: captureCamera(app, opts.ortho ?? false),
    selection: toGids([...app.controller.selection].sort((a, b) => a - b)),
    params: currentViewParams(app, opts.paramsEnv),
  };
  const hidden = toGids([...ov.userHides].sort((a, b) => a - b));
  const hides = compactHides(hidden, els.map((e) => e.globalId));
  if (hides) v.hides = hides;
  const pins = toGids([...ov.userPins].sort((a, b) => a - b));
  if (pins.length) v.pins = pins;
  if (opts.exploded) v.exploded = true;
  if (opts.clip && opts.clip.length) v.clip = opts.clip.map((p) => ({ normal: roundVec(p.normal), point: roundVec(p.point) }));
  if (opts.preset) v.preset = opts.preset;
  if (opts.thumb) v.thumb = opts.thumb;
  return v;
}

/** Everything a restore changes apart from the camera, computed against the current state. */
export interface RestorePlan {
  /** Sections whose target value differs from the current one (the only ones applied). */
  params: Record<string, unknown>;
  selection: number[];
  hides: number[];
  pins: number[];
  /** GlobalIds of the view that the loaded model lacks (each once). */
  missing: string[];
}

/**
 * Plan a restore. `current` is the current filtered params (currentViewParams), `factory` the filtered params as they
 * were after the first model loaded: the view's params are merged over it, so a partial view (a share link, a packed
 * views file) resets what it does not name.
 */
export function planRestore(
  view: SavedView,
  model: { byGlobalId: ReadonlyMap<string, number>; elements: { length: number } },
  current: Record<string, unknown>,
  factory: Record<string, unknown> | null,
): RestorePlan {
  const target = (factory ? mergeParams(factory, view.params) : view.params) as Record<string, unknown>;
  const params = changedSections(target, current);
  const sel = resolveGlobalIds(model.byGlobalId, view.selection);
  const hides = expandHides(view.hides, model.byGlobalId, model.elements.length);
  const pins = resolveGlobalIds(model.byGlobalId, view.pins ?? []);
  const hidden = new Set(hides.ids);
  const missing = [...new Set([...sel.missing, ...hides.missing, ...pins.missing])];
  return { params, selection: sel.ids, hides: hides.ids, pins: pins.ids.filter((id) => !hidden.has(id)), missing };
}

/**
 * Apply the state part of a plan: the changed params sections (one applyParams call, no camera, no reclassify), the
 * hides and pins, then the selection (which reclassifies once). Returns the params keys that could not be applied.
 */
export function applyPlan(app: ViewsApp, plan: RestorePlan, env?: ParamsEnv): string[] {
  let bad: string[] = [];
  if (Object.keys(plan.params).length > 0) {
    bad = applyParams(app, { schema: PARAMS_SCHEMA, ...plan.params }, { reclassify: false, skipCamera: true, ...(env ? { env } : {}) });
  }
  const ov = app.settings.overrides;
  ov.userHides.clear();
  for (const id of plan.hides) ov.userHides.add(id);
  ov.userPins.clear();
  for (const id of plan.pins) ov.userPins.add(id);
  app.controller.refreshOverrides?.();
  if (app.selectIds) app.selectIds(plan.selection);
  else app.reclassify();
  return bad;
}
