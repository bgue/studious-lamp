// The viewer side of the score player: starts a runner for each cue kind of src/anim/score.ts, keeps what a restore needs and
// puts it back. See src/anim/player.ts for the clock. Cue kinds: cameraPath, camera (pose, frame, view, orbitDeg), param, preset,
// view, visibility (fades the alpha of the elements that appear or disappear), select. caption, label and hover are drawn by the
// HUD layer (src/anim/hud), which gets the score from begin(); their runners here only report the cue start. Any cue kind this
// player does not know is skipped.

import { Box3, Vector3 } from 'three';
import type { ViewerApp } from '../app';
import type { ElementId } from '../types';
import { computeFlyView, framing } from '../cinematic/flyto';
import { isPseudoOrtho, setPseudoOrtho, cancelNavigationMoves } from '../input/navigation';
import { cancelGizmoMove } from '../gizmo/camera';
import { getCinematic } from '../plugins/cinematic';
import { PARAMS_SCHEMA, applyParams } from '../ui/params';
import type { ParamsApp } from '../ui/params';
import { loadSets, unionBounds } from '../selectionSets';
import type { SelectionSet } from '../selectionSets';
import { isCriteria } from '../selectionSets';
import { runQuery } from '../query';
import { applyPlan, captureCamera, currentViewParams } from '../views/capture';
import type { ViewsApp } from '../views/capture';
import { changedSections } from '../views/model';
import type { ViewCamera } from '../views/model';
import { CameraPathSampler } from './path';
import { blendNumbers, diffParams, easeValue, getAt, nest, pathKeys, switchPoint } from './blend';
import type { Keys } from './blend';
import type { CameraPose, Cue, ElementRef, Score, V3, ViewState } from './score';
import type { CueRunner, PlayerHost } from './player';
import { getHudLayer } from './hud';

const PARAM_APPLY_MS = 50;

type Cam = ViewCamera;
interface Snapshot {
  camera: Cam;
  selection: ElementId[];
  hides: ElementId[];
  pins: ElementId[];
  params: Record<string, unknown>;
  post: { ao: boolean; vignette: boolean } | null;
  exploded: boolean;
  preset: string | null;
}

/** One group of elements that fades in (shown now, alpha rises) or out (hidden at the end). */
interface FadeGroup {
  ids: ElementId[];
  mode: 'in' | 'out';
  f: number;
  base: Float32Array;
  /** Hidden set after the cue (applied when the fade ends). */
  commit: Set<ElementId> | null;
  done: boolean;
}

interface PresetsLike {
  get?(id: string): unknown;
  apply(id: string): unknown;
  active?(): string | null;
  markActive?(id: string): boolean;
}
interface TopBarLike {
  modes?(): Array<{ id: string }>;
  apply?(id: string): boolean;
}
interface ViewsLike {
  get(key: string): { camera: Cam } | null;
}
const win = (): { __xrayPresets?: PresetsLike; __xrayTopBar?: TopBarLike; __xrayViews?: ViewsLike } => window as never;

const toV3 = (v: Vector3): V3 => [v.x, v.y, v.z];

export class ViewerScoreHost implements PlayerHost {
  private snap: Snapshot | null = null;
  private refs = new Map<string, ElementId[]>();
  private pathSpans: Array<[number, number]> = [];
  private pending = new Map<string, { keys: Keys; value: unknown }>();
  private lastParamApply = -Infinity;
  private forceParams = false;
  private groups = new Set<FadeGroup>();
  private sightlinesDirty = false;
  private camSetup = false;
  readonly warned = new Set<string>();

  constructor(private readonly app: ViewerApp) {}

  private get model() {
    return this.app.controller.model;
  }
  private get vapp(): ViewsApp {
    return this.app as unknown as ViewsApp;
  }
  private get papp(): ParamsApp {
    return this.app as unknown as ParamsApp;
  }

  // ---------------------------------------------------------------- begin, finish, restore

  begin(score: Score): void {
    const app = this.app;
    const cin = getCinematic();
    const ov = app.settings.overrides;
    this.snap = {
      camera: captureCamera(this.vapp, isPseudoOrtho()),
      selection: [...app.controller.selection],
      hides: [...ov.userHides],
      pins: [...ov.userPins],
      params: currentViewParams(this.papp),
      post: cin ? { ao: cin.post.settings.ao, vignette: cin.post.settings.vignette } : null,
      exploded: cin?.exploded === true,
      preset: win().__xrayPresets?.active?.() ?? null,
    };
    this.refs.clear();
    this.pending.clear();
    this.groups.clear();
    this.forceParams = false;
    this.camSetup = false;
    this.pathSpans = [];
    getHudLayer()?.setScore?.(score);
    score.cues.forEach((c, i) => {
      if (c.kind === 'cameraPath') this.pathSpans.push([c.at, c.at + c.dur]);
      this.prewarm(c, i);
    });
    if (cin) {
      cin.tour.stop();
      cin.cancelFlight();
      cin.externalCamera = true;
      cin.post.setPlaying(true);
    }
    cancelNavigationMoves();
    cancelGizmoMove();
  }

  finish(): void {
    for (const g of [...this.groups]) this.endGroup(g);
    this.groups.clear();
    this.forceParams = true;
    this.flushParams(Infinity);
    getHudLayer()?.setScore?.(null);
    const cin = getCinematic();
    if (cin) {
      cin.externalCamera = false;
      cin.post.setPlaying(false);
    }
    if (this.sightlinesDirty) this.flushSightlines();
  }

  abandon(): void {
    this.groups.clear();
    this.pending.clear();
    this.forceParams = false;
    this.sightlinesDirty = false;
    this.snap = null;
    getHudLayer()?.setScore?.(null);
    const cin = getCinematic();
    if (cin) {
      cin.externalCamera = false;
      cin.post.setPlaying(false);
    }
  }

  restore(keepCamera: boolean): void {
    const s = this.snap;
    if (!s) return;
    const app = this.app;
    const cin = getCinematic();
    const model = this.model;
    const current = currentViewParams(this.papp);
    const params = changedSections(s.params, current);
    const run = (): void => void applyPlan(this.vapp, { params, selection: s.selection.filter((id) => id < model.elements.length), hides: s.hides, pins: s.pins, missing: [] });
    // A selection that comes back must not fly the camera to it.
    if (cin) cin.quietly(run);
    else run();
    if (cin && s.post) {
      cin.post.settings.ao = s.post.ao;
      cin.post.settings.vignette = s.post.vignette;
      cin.post.sync();
    }
    cin?.refreshFromConfig();
    if (cin) {
      if (s.exploded && !cin.exploded) cin.explode();
      else if (!s.exploded && cin.exploded) cin.collapse();
    }
    if (s.preset) {
      try {
        win().__xrayPresets?.markActive?.(s.preset);
      } catch {
        /* a presets plugin without the mark */
      }
    }
    if (!keepCamera) {
      this.writePose({ position: s.camera.position, target: s.camera.target, up: s.camera.up, fovDeg: s.camera.fov, ortho: s.camera.ortho }, true);
    }
    cin?.cancelFlight();
    app.runSightlinesNow();
    app.renderer.markDirty();
  }

  flush(): void {
    this.flushParams(performance.now());
    this.applyFades();
    if (this.sightlinesDirty) this.flushSightlines();
  }

  /** Re-write the fade alphas (the frame loop calls it while paused, when no tick runs). */
  applyFades(): void {
    const alpha = this.app.renderer.state.alpha;
    for (const g of this.groups) {
      const w = g.mode === 'in' ? g.f : 1 - g.f;
      for (let i = 0; i < g.ids.length; i++) {
        const b = g.base[i]!;
        if (b > 0) alpha[g.ids[i]!] = Math.max(0.02, b * w);
      }
    }
  }

  // ---------------------------------------------------------------- element references

  private prewarm(c: Cue, index: number): void {
    const pre = (ref: ElementRef | null | undefined, field: string): void => {
      if (ref) this.resolveRef(ref, `${index}:${field}`);
    };
    if (c.kind === 'visibility') {
      pre(c.show, 'show');
      pre(c.hide, 'hide');
      pre(c.isolate, 'isolate');
    } else if (c.kind === 'select') pre(c.elements, 'elements');
    else if (c.kind === 'label' || c.kind === 'hover') pre(c.elements, 'elements');
    else if (c.kind === 'camera') {
      if ('frame' in c.to) pre(c.to.frame, 'frame');
      if ('orbitDeg' in c.to) pre(c.to.about, 'about');
    }
  }

  /** The element ids of a reference. A query, a set and a list are resolved once per play; `selection` is read when asked. */
  resolveRef(ref: ElementRef, key: string): ElementId[] {
    if ('selection' in ref) return [...this.app.controller.selection];
    const hit = this.refs.get(key);
    if (hit) return hit;
    const model = this.model;
    let ids: ElementId[] = [];
    if ('all' in ref) ids = model.elements.map((_, i) => i);
    else if ('globalIds' in ref) {
      for (const g of ref.globalIds) {
        const id = model.byGlobalId.get(g);
        if (id !== undefined) ids.push(id);
      }
    } else if ('query' in ref) {
      const r = runQuery(model, ref.query);
      if (r.error) this.warnOnce(`query ${ref.query}`, `Score: query "${ref.query}" failed: ${r.error.message}`);
      else ids = r.ids;
    } else if ('set' in ref) {
      let sets: SelectionSet[] | null = null;
      try {
        sets = loadSets(window.localStorage, this.app.modelName);
      } catch {
        sets = null;
      }
      const want = ref.set.trim().toLowerCase();
      const s = sets?.find((x) => x.name.trim().toLowerCase() === want);
      if (!s) this.warnOnce(`set ${ref.set}`, `Score: no selection set named "${ref.set}".`);
      else if (isCriteria(s)) ids = runQuery(model, s.query).ids;
      else for (const g of s.globalIds) {
        const id = model.byGlobalId.get(g);
        if (id !== undefined) ids.push(id);
      }
    }
    this.refs.set(key, ids);
    return ids;
  }

  private warnOnce(key: string, msg: string): void {
    if (this.warned.has(key)) return;
    this.warned.add(key);
    console.warn(msg);
    this.app.showMessage(msg);
    setTimeout(() => this.app.showMessage(null), 4000);
  }

  private boxOf(ids: readonly ElementId[]): Box3 | null {
    const b = unionBounds(this.model, ids);
    return b ? new Box3(new Vector3(b[0], b[1], b[2]), new Vector3(b[3], b[4], b[5])) : null;
  }

  // ---------------------------------------------------------------- camera

  currentPose(): CameraPose {
    const c = captureCamera(this.vapp, isPseudoOrtho());
    return { position: c.position, target: c.target, up: c.up, fovDeg: c.fov, ortho: c.ortho };
  }

  /** Make the far plane and the orbit limits reach a camera at `dist` from its target. */
  private ensureReach(dist: number): void {
    const { camera, controls } = this.app.renderer;
    const b = this.app.loaded?.geometry.totalBounds();
    const diag = b && !b.isEmpty() ? b.min.distanceTo(b.max) : 10;
    if (camera.far < dist + diag * 2) {
      camera.far = dist + diag * 2;
      camera.updateProjectionMatrix();
    }
    if (controls.minDistance > dist) controls.minDistance = dist * 0.5;
    if (controls.maxDistance > 0 && Number.isFinite(controls.maxDistance) && controls.maxDistance < dist * 1.05) controls.maxDistance = dist * 1.05;
  }

  writePose(p: CameraPose, reach = false): void {
    const app = this.app;
    const { camera, controls } = app.renderer;
    if (p.ortho !== undefined && p.ortho !== isPseudoOrtho()) setPseudoOrtho(app, p.ortho);
    if (p.fovDeg !== undefined && !isPseudoOrtho() && Math.abs(camera.fov - p.fovDeg) > 1e-4) {
      camera.fov = p.fovDeg;
      camera.updateProjectionMatrix();
    }
    if (reach) this.ensureReach(Math.hypot(p.position[0] - p.target[0], p.position[1] - p.target[1], p.position[2] - p.target[2]));
    if (p.up) camera.up.set(p.up[0], p.up[1], p.up[2]);
    camera.position.set(p.position[0], p.position[1], p.position[2]);
    controls.target.set(p.target[0], p.target[1], p.target[2]);
    controls.update();
    app.renderer.markDirty();
  }

  /** True while a camera path covers the time of a view cue (its camera is then not used). */
  private cameraBusy(at: number, dur: number): boolean {
    const mid = at + dur / 2;
    return this.pathSpans.some(([a, b]) => mid >= a - 1e-9 && mid <= b + 1e-9);
  }

  private poseBlend(a: CameraPose, b: CameraPose, p: number): CameraPose {
    const L = (x: V3, y: V3): V3 => [x[0] + (y[0] - x[0]) * p, x[1] + (y[1] - x[1]) * p, x[2] + (y[2] - x[2]) * p];
    const out: CameraPose = { position: L(a.position, b.position), target: L(a.target, b.target) };
    const ua = a.up ?? [0, 1, 0];
    const ub = b.up ?? ua;
    const u = L(ua, ub);
    const len = Math.hypot(...u) || 1;
    out.up = [u[0] / len, u[1] / len, u[2] / len];
    if (a.fovDeg !== undefined && b.fovDeg !== undefined) out.fovDeg = a.fovDeg + (b.fovDeg - a.fovDeg) * p;
    else if (b.fovDeg !== undefined) out.fovDeg = b.fovDeg;
    const nearEnd = p >= 0.5 ? b : a;
    if (nearEnd.ortho !== undefined) out.ortho = nearEnd.ortho;
    return out;
  }

  private cameraRunner(cue: Extract<Cue, { kind: 'camera' }>, index: number): CueRunner | null {
    const from = this.currentPose();
    const to = cue.to;
    const { camera, controls } = this.app.renderer;
    let target: CameraPose | null = null;
    let orbit: { centre: V3; off: Vector3; rad: number; hasAbout: boolean } | null = null;
    if ('pose' in to) target = to.pose;
    else if ('frame' in to) {
      const box = this.boxOf(this.resolveRef(to.frame, `${index}:frame`));
      if (!box || box.isEmpty()) return null;
      const opts: { margin?: number; minDistance?: number } = {};
      if (to.margin !== undefined) opts.margin = to.margin;
      if (to.minDistance !== undefined) opts.minDistance = to.minDistance;
      const v = computeFlyView(box, { position: camera.position, target: controls.target, fovDeg: camera.fov, aspect: camera.aspect, minDistance: controls.minDistance, maxDistance: controls.maxDistance }, opts);
      target = { position: toV3(v.position), target: toV3(v.target), up: from.up };
    } else if ('view' in to) {
      const v = win().__xrayViews?.get(to.view);
      if (!v) {
        this.warnOnce(`view ${to.view}`, `Score: no saved view named "${to.view}".`);
        return null;
      }
      target = { position: v.camera.position, target: v.camera.target, up: v.camera.up, fovDeg: v.camera.fov, ortho: v.camera.ortho };
    } else if ('orbitDeg' in to) {
      let centre: V3 = from.target;
      let hasAbout = false;
      if (to.about) {
        const box = this.boxOf(this.resolveRef(to.about, `${index}:about`));
        if (box && !box.isEmpty()) {
          centre = toV3(box.getCenter(new Vector3()));
          hasAbout = true;
        }
      }
      orbit = { centre, off: new Vector3(from.position[0] - centre[0], from.position[1] - centre[1], from.position[2] - centre[2]), rad: (to.orbitDeg * Math.PI) / 180, hasAbout };
    }
    if (target) this.ensureReach(Math.hypot(target.position[0] - target.target[0], target.position[1] - target.target[1], target.position[2] - target.target[2]));
    const up = new Vector3(0, 1, 0);
    return {
      update: (raw) => {
        const p = easeValue(cue.ease, raw);
        if (target) this.writePose(this.poseBlend(from, target, p));
        else if (orbit) {
          const o = orbit.off.clone().applyAxisAngle(up, orbit.rad * p);
          const tgt: V3 = orbit.hasAbout ? [from.target[0] + (orbit.centre[0] - from.target[0]) * Math.min(1, p * 3), from.target[1] + (orbit.centre[1] - from.target[1]) * Math.min(1, p * 3), from.target[2] + (orbit.centre[2] - from.target[2]) * Math.min(1, p * 3)] : from.target;
          const base = orbit.hasAbout ? orbit.centre : orbit.centre;
          this.writePose({ position: [base[0] + o.x, base[1] + o.y, base[2] + o.z], target: tgt, up: from.up, ...(from.fovDeg !== undefined ? { fovDeg: from.fovDeg } : {}) });
        }
      },
    };
  }

  private pathRunner(cue: Extract<Cue, { kind: 'cameraPath' }>): CueRunner | null {
    if (cue.poses.length === 0) return null;
    const sampler = new CameraPathSampler(cue.poses, cue.times, { ease: cue.ease ?? 'inOut', ...(cue.easeAt ? { easeAt: cue.easeAt } : {}) });
    let maxDist = 0;
    for (const p of cue.poses) maxDist = Math.max(maxDist, Math.hypot(p.position[0] - p.target[0], p.position[1] - p.target[1], p.position[2] - p.target[2]));
    this.ensureReach(maxDist);
    return {
      update: (raw) => {
        const t = cue.at + raw * cue.dur;
        this.writePose(sampler.sample(t));
      },
    };
  }

  // ---------------------------------------------------------------- settings

  private currentParams(): Record<string, unknown> {
    const cur = currentViewParams(this.papp);
    const cin = getCinematic();
    if (cin) cur['post'] = { ao: cin.post.settings.ao, vignette: cin.post.settings.vignette };
    return cur;
  }

  private queue(keys: Keys, value: unknown, force: boolean): void {
    this.pending.set(keys.join('\u0000'), { keys, value });
    if (force) this.forceParams = true;
  }

  private flushParams(now: number): void {
    if (this.pending.size === 0) {
      this.forceParams = false;
      return;
    }
    if (!this.forceParams && now - this.lastParamApply < PARAM_APPLY_MS) return;
    this.lastParamApply = now;
    const items = [...this.pending.values()];
    this.pending.clear();
    const force = this.forceParams;
    this.forceParams = false;
    const post = items.filter((i) => i.keys[0] === 'post');
    const rest = items.filter((i) => i.keys[0] !== 'post');
    const cin = getCinematic();
    if (post.length && cin) {
      for (const i of post) {
        const k = i.keys[1];
        if ((k === 'ao' || k === 'vignette') && typeof i.value === 'boolean') cin.post.settings[k] = i.value;
      }
      cin.post.sync();
    }
    if (rest.length) {
      const bad = applyParams(this.papp, { schema: PARAMS_SCHEMA, ...nest(rest) }, { reclassify: false, skipCamera: true });
      if (bad.length && force) this.warnOnce(`bad ${bad.join(',')}`, `Score: could not apply ${bad.slice(0, 3).join(', ')}.`);
      if (rest.some((i) => i.keys[0] === 'cinematic')) cin?.refreshFromConfig();
      if (force && rest.some((i) => ['classification', 'sightlines', 'farMode', 'tiers', 'tiersMode', 'xray'].includes(i.keys[0]!))) this.app.reclassify();
    }
    this.app.renderer.markDirty();
  }

  private paramRunner(cue: Extract<Cue, { kind: 'param' }>): CueRunner {
    const keys = pathKeys(cue.path);
    const from = getAt(this.currentParams(), keys);
    const sw = switchPoint(cue.switchAt, 'end');
    return {
      update: (raw) => {
        const p = easeValue(cue.ease, raw);
        let v: unknown;
        if (typeof from === 'number' && typeof cue.to === 'number') v = raw >= 1 ? cue.to : from + (cue.to - from) * p;
        else v = raw >= sw ? cue.to : from;
        if (v !== undefined) this.queue(keys, v, raw >= 1);
      },
    };
  }

  private presetRunner(cue: Extract<Cue, { kind: 'preset' }>): CueRunner {
    const sw = switchPoint(cue.switchAt, 'end');
    let done = false;
    return {
      update: (raw) => {
        if (done || raw < sw) return;
        done = true;
        this.flushParams(Infinity);
        const pr = win().__xrayPresets;
        const tb = win().__xrayTopBar;
        try {
          if (pr?.get?.(cue.id)) pr.apply(cue.id);
          else if (tb?.modes?.().some((m) => m.id === cue.id) && tb.apply) tb.apply(cue.id);
          else this.warnOnce(`preset ${cue.id}`, `Score: no preset or mode "${cue.id}".`);
        } catch (e) {
          this.warnOnce(`preset ${cue.id}`, `Score: preset "${cue.id}" failed: ${e instanceof Error ? e.message : String(e)}`);
        }
        this.app.renderer.markDirty();
      },
    };
  }

  private viewRunner(cue: Extract<Cue, { kind: 'view' }>): CueRunner {
    const state: ViewState = cue.state;
    const diff = diffParams(this.currentParams(), state.params ?? {});
    const sw = switchPoint(cue.switchAt, 'end');
    const from = this.currentPose();
    const useCam = !this.cameraBusy(cue.at, cue.dur) && !!state.camera;
    let switched = false;
    return {
      update: (raw) => {
        const p = easeValue(cue.ease, raw);
        if (diff.nums.length) {
          const doc = blendNumbers(diff.nums, p);
          for (const n of diff.nums) this.queue(n.keys, getAt(doc, n.keys), raw >= 1);
        }
        if (useCam) this.writePose(this.poseBlend(from, state.camera, p));
        if (!switched && raw >= sw) {
          switched = true;
          for (const d of diff.discrete) this.queue(d.keys, d.value, true);
          this.flushParams(Infinity);
          if (state.presetId) {
            try {
              win().__xrayPresets?.markActive?.(state.presetId);
            } catch {
              /* ignore */
            }
          }
          if (state.hidden || state.isolate) this.setHiddenFromState(state);
          if (state.selection) this.selectIds(this.idsOfGlobal(state.selection));
          const cin = getCinematic();
          if (cin && typeof state.explode === 'boolean') {
            if (state.explode && !cin.exploded) cin.explode();
            else if (!state.explode && cin.exploded) cin.collapse();
          }
        }
      },
    };
  }

  private idsOfGlobal(g: readonly string[]): ElementId[] {
    const out: ElementId[] = [];
    for (const x of g) {
      const id = this.model.byGlobalId.get(x);
      if (id !== undefined) out.push(id);
    }
    return out;
  }

  private setHiddenFromState(state: ViewState): void {
    const hide = new Set<ElementId>();
    if (state.isolate) {
      const keep = new Set(this.idsOfGlobal(state.isolate));
      for (let i = 0; i < this.model.elements.length; i++) if (!keep.has(i)) hide.add(i);
    } else for (const id of this.idsOfGlobal(state.hidden ?? [])) hide.add(id);
    this.setHidden(hide);
  }

  // ---------------------------------------------------------------- visibility and selection

  private setHidden(set: ReadonlySet<ElementId>): void {
    const ov = this.app.settings.overrides;
    ov.userHides.clear();
    for (const id of set) {
      ov.userHides.add(id);
      ov.userPins.delete(id);
    }
    this.app.controller.refreshOverrides();
    this.sightlinesDirty = true;
  }

  private flushSightlines(): void {
    this.sightlinesDirty = false;
    this.app.runSightlinesNow();
  }

  private selectIds(ids: ElementId[]): void {
    const cin = getCinematic();
    const run = (): void => {
      if (ids.length) this.app.selectIds(ids);
      else this.app.clearSelection();
    };
    if (cin) cin.quietly(run);
    else run();
  }

  private endGroup(g: FadeGroup): void {
    if (g.done) return;
    g.done = true;
    this.groups.delete(g);
    if (g.commit) this.setHidden(g.commit);
  }

  private visibilityRunner(cue: Extract<Cue, { kind: 'visibility' }>, index: number): CueRunner {
    const model = this.model;
    const H = new Set(this.app.settings.overrides.userHides);
    let F = new Set(H);
    if (cue.showAll) F.clear();
    if (cue.isolate) {
      const keep = new Set(this.resolveRef(cue.isolate, `${index}:isolate`));
      F = new Set();
      for (let i = 0; i < model.elements.length; i++) if (!keep.has(i)) F.add(i);
    }
    if (cue.show) for (const id of this.resolveRef(cue.show, `${index}:show`)) F.delete(id);
    if (cue.hide) for (const id of this.resolveRef(cue.hide, `${index}:hide`)) F.add(id);
    const sw = switchPoint(cue.switchAt, 'end');
    if (cue.dur <= 0) {
      let done = false;
      return {
        update: (raw) => {
          if (done || raw < sw) return;
          done = true;
          this.setHidden(F);
        },
      };
    }
    const toShow: ElementId[] = [];
    const toHide: ElementId[] = [];
    for (const id of H) if (!F.has(id)) toShow.push(id);
    for (const id of F) if (!H.has(id)) toHide.push(id);
    const alpha = this.app.renderer.state.alpha;
    let gIn: FadeGroup | null = null;
    let gOut: FadeGroup | null = null;
    // Elements that fade out stay shown (at their alpha) until the fade ends; the ones that fade in are shown now, from alpha 0.
    if (toHide.length) {
      const base = new Float32Array(toHide.length);
      toHide.forEach((id, i) => (base[i] = alpha[id]! > 0 ? alpha[id]! : 0));
      gOut = { ids: toHide, mode: 'out', f: 0, base, commit: F, done: false };
      this.groups.add(gOut);
    }
    if (toShow.length) {
      const visible = new Set(H);
      for (const id of toShow) visible.delete(id);
      // Hidden now minus the ones that appear: those that stay hidden stay in the set; the ones that fade out are not hidden yet.
      this.setHidden(visible);
      this.app.controller.tick();
      const base = new Float32Array(toShow.length);
      toShow.forEach((id, i) => (base[i] = alpha[id]! > 0 ? alpha[id]! : 1));
      gIn = { ids: toShow, mode: 'in', f: 0, base, commit: gOut ? null : F, done: false };
      this.groups.add(gIn);
    }
    if (!gOut && gIn) gIn.commit = F;
    else if (gOut && !gIn) gOut.commit = F;
    else if (gOut && gIn) {
      gOut.commit = F;
      gIn.commit = null;
    }
    return {
      update: (raw) => {
        const f = easeValue(cue.ease, raw);
        if (gIn) gIn.f = f;
        if (gOut) gOut.f = f;
        if (raw >= 1) {
          if (gIn) this.endGroup(gIn);
          if (gOut) this.endGroup(gOut);
        }
      },
    };
  }

  private selectRunner(cue: Extract<Cue, { kind: 'select' }>, index: number): CueRunner {
    const sw = switchPoint(cue.switchAt, 'start');
    let done = false;
    return {
      update: (raw) => {
        if (done || raw < sw) return;
        done = true;
        this.selectIds(cue.elements ? this.resolveRef(cue.elements, `${index}:elements`) : []);
      },
    };
  }

  /** Captions, labels and the hover card are drawn by the HUD layer from the score; the runner only lets the player report the cue. */
  private hudRunner(): CueRunner {
    return { update: () => undefined };
  }

  // ---------------------------------------------------------------- cue dispatch

  start(cue: Cue, index: number): CueRunner | null {
    switch (cue.kind) {
      case 'cameraPath':
        return this.pathRunner(cue);
      case 'camera':
        return this.cameraRunner(cue, index);
      case 'param':
        return this.paramRunner(cue);
      case 'preset':
        return this.presetRunner(cue);
      case 'view':
        return this.viewRunner(cue);
      case 'visibility':
        return this.visibilityRunner(cue, index);
      case 'select':
        return this.selectRunner(cue, index);
      case 'caption':
      case 'label':
      case 'hover':
        return this.hudRunner();
      default:
        return null; // cue kinds from a newer score format
    }
  }
}
