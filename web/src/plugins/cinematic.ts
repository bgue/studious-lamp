// Cinematic plugin: camera fly-to, staggered reveal, scene dressing, selective bloom, turntable,
// dolly-along-run, tour mode and edge glow, plus (second round) the sweep reveal, depth-graded
// ghosting, sightline visualisation, AO + vignette, exploded context and the recordable fly-through.
// Every feature is a toggle in the "Cinematic" folder and is a no-op when off.
// `?cinematic=off` in the URL starts with all of them off; `?cin2=off` switches off only the
// second-round features that default on (sweep reveal, depth grading).

import { Box3, Sphere, Vector3 } from 'three';
import type GUI from 'lil-gui';
import type { AppPlugin, ViewerApp } from '../app';
import type { ElementId } from '../types';
import { Flight, DEFAULT_FLY_MS, computeFlyView } from '../cinematic/flyto';
import type { FlyOptions, FlyView } from '../cinematic/flyto';
import { StaggerReveal, revealDelays } from '../cinematic/reveal';
import { PolylinePath, buildRunPath } from '../cinematic/polyline';
import { Tour, buildTourSteps } from '../cinematic/tour';
import { SceneDressing, hexToRgb } from '../cinematic/dressing';
import { SelectiveBloom } from '../cinematic/bloom';
import { PostFx } from '../cinematic/post';
import { PlaneSweep, DEFAULT_SWEEP_MS, DEFAULT_BAND_M, buildHold, projectionExtent, sweepNormal, sweepRangeFromExtent, usesStagger, usesSweep } from '../cinematic/sweep';
import type { RevealMode } from '../cinematic/sweep';
import { SightlineViz, buildSightRays, makeQueries } from '../cinematic/sightlineViz';
import type { RayFilter, RayStyle } from '../cinematic/sightlineViz';
import {
  ExplodeAnim,
  DEFAULT_EXPLODE_FACTOR,
  DEFAULT_EXPLODE_MS,
  DEFAULT_MIN_PUSH,
  DEFAULT_STOREY_GAP,
  EXPLODE_MODES,
  buildExplodeTable,
  explodeOffset,
  resolveExplodeSet,
  storeyRanks,
  unionCentre,
} from '../cinematic/explode';
import type { ExplodeMode, ExplodeSource, ExplodeTable } from '../cinematic/explode';
import {
  CanvasRecorder,
  DEFAULT_SEGMENT_S,
  FlyPlayer,
  downloadBlob,
  flythroughKey,
  parseKeyframes,
  serializeKeyframes,
} from '../cinematic/flythrough';
import type { Keyframe, KeyframeToggles, Recording } from '../cinematic/flythrough';
import { collectSamples, occluderSet } from '../algo';
import { DEFAULT_GLOW_SCOPE, GLOW_SCOPES, glowIds } from '../cinematic/glow';
import type { GlowScope } from '../cinematic/glow';
import { defaultSetsFor, globalIdsToIds, idsToGlobalIds, loadSets, unionBounds } from '../selectionSets';

export interface CinematicConfig {
  flyTo: boolean;
  flyMs: number;
  reveal: boolean;
  dressing: boolean;
  fogStrength: number;
  groundShadow: boolean;
  shadowStrength: number;
  bloom: boolean;
  bloomStrength: number;
  bloomRadius: number;
  autoOrbit: boolean;
  orbitSpeed: number;
  dollyPlaying: boolean;
  dollySpeed: number;
  dollyHeight: number;
  dollyProgress: number;
  tourHold: number;
  tourLoop: boolean;
  edgeGlow: boolean;
  glowStrength: number;
  glowColor: string;
  /** Which elements glow: the focus, focus + host + near, or every visible element. Replaces the old `glowNear` switch. */
  glowScope: GlowScope;
  glowAdditive: boolean;
  /** Sweep reveal: a plane travels from the camera through the occluders. */
  sweep: { enabled: boolean; mode: RevealMode; durationMs: number; bandWidth: number };
  /** Depth-graded ghosting. */
  grade: { enabled: boolean; strength: number };
  /** Sightline visualisation. */
  sightlines: { autoOnSelect: boolean; style: RayStyle; which: RayFilter; colorByHit: boolean; max: number; durationS: number };
  /** Exploded view: what explodes, how, and how far. */
  explode: { source: ExplodeSource; mode: ExplodeMode; factor: number; storeyGap: number; minPush: number; durationMs: number };
  /** Fly-through. */
  fly: { segmentS: number };
}

/** `allOff`: everything off (?cinematic=off). `newOff`: only the second-round features that default on (?cin2=off). */
export function defaultConfig(allOff = false, newOff = allOff): CinematicConfig {
  return {
    flyTo: !allOff,
    flyMs: DEFAULT_FLY_MS,
    reveal: !allOff,
    dressing: !allOff,
    fogStrength: 0.4,
    groundShadow: false,
    shadowStrength: 0.5,
    bloom: false,
    bloomStrength: 0.7,
    bloomRadius: 0.45,
    autoOrbit: false,
    orbitSpeed: 8,
    dollyPlaying: false,
    dollySpeed: 1.5,
    dollyHeight: 0.8,
    dollyProgress: 0,
    tourHold: 3,
    tourLoop: false,
    edgeGlow: false,
    glowStrength: 0.45,
    glowColor: '#ff7a1a',
    glowScope: DEFAULT_GLOW_SCOPE,
    glowAdditive: true,
    sweep: { enabled: !newOff, mode: 'both', durationMs: DEFAULT_SWEEP_MS, bandWidth: DEFAULT_BAND_M },
    grade: { enabled: !newOff, strength: 0.5 },
    sightlines: { autoOnSelect: false, style: 'lines', which: 'all', colorByHit: true, max: 200, durationS: 1.5 },
    explode: { source: 'auto', mode: 'radial', factor: DEFAULT_EXPLODE_FACTOR, storeyGap: DEFAULT_STOREY_GAP, minPush: DEFAULT_MIN_PUSH, durationMs: DEFAULT_EXPLODE_MS },
    fly: { segmentS: DEFAULT_SEGMENT_S },
  };
}

const UP = new Vector3(0, 1, 0);
const IDLE_RESUME_MS = 3000;
const POSE_EPS = 1e-3;

export class Cinematic {
  readonly cfg: CinematicConfig;
  readonly dressing: SceneDressing;
  readonly bloom: SelectiveBloom;
  readonly stagger = new StaggerReveal();
  readonly tour: Tour;
  readonly post: PostFx;
  readonly planeSweep = new PlaneSweep();
  readonly viz: SightlineViz;
  readonly explodeAnim = new ExplodeAnim();
  /** Fly-through keyframes (persisted per model in localStorage). */
  keys: Keyframe[] = [];
  /** The last finished recording, for scripts. */
  lastRecording: Recording | null = null;

  private flight: Flight | null = null;
  private flightSet: FlyView = { position: new Vector3(), target: new Vector3() };
  private lastSet: FlyView | null = null;
  private suppressFly = false;
  private lastSelKey = '';
  private lastXray = true;
  private lastInput = -Infinity;
  private pointerDown = false;
  private path: PolylinePath | null = null;
  private dollyS = 0;
  private lastGuiUpdate = 0;
  private gui: GUI | null = null;
  private tourButton: { name(n: string): unknown } | null = null;
  private dollyButton: { name(n: string): unknown } | null = null;
  private dollyProgressCtl: { updateDisplay(): unknown } | null = null;
  private messageTimer: ReturnType<typeof setTimeout> | null = null;
  private readonly tmp = new Vector3();
  private explodeTable: ExplodeTable | null = null;
  private explodeDirty = false;
  private explodeButton: { name(n: string): unknown } | null = null;
  private player: FlyPlayer | null = null;
  private playEnd: (() => void) | null = null;
  private readonly recorder = new CanvasRecorder();
  private recordTimer: ReturnType<typeof setTimeout> | null = null;
  private keyInfo = { keyframes: '0' };
  private keyInfoCtl: { updateDisplay(): unknown } | null = null;
  private readonly camPos = new Vector3();
  private readonly camTgt = new Vector3();

  constructor(private readonly app: ViewerApp, allOff: boolean, newOff = allOff) {
    this.cfg = defaultConfig(allOff, newOff);
    this.dressing = new SceneDressing(app.renderer);
    this.bloom = new SelectiveBloom(app.renderer, () => app.controller?.classification.focus.size ?? 0);
    this.post = new PostFx(app.renderer, this.bloom, {
      rawBackground: () => this.dressing.rawBackground(),
      focusDistance: () => this.focusViewDistance(),
    });
    this.viz = new SightlineViz(app.renderer.scene);
    this.tour = new Tour({
      holdMs: () => this.cfg.tourHold * 1000,
      flyMs: () => this.cfg.flyMs,
      loop: () => this.cfg.tourLoop,
      apply: (step) => {
        this.suppressFly = true;
        try {
          this.app.selectIds(step.ids);
        } finally {
          this.suppressFly = false;
        }
        this.flyToElements(this.focusIds().length > 0 ? this.focusIds() : step.ids);
      },
      onStop: () => this.tourButton?.name('Play tour'),
    });
  }

  // ------------------------------------------------------------------ helpers

  private get r() {
    return this.app.renderer;
  }

  private boxOf(ids: Iterable<ElementId>): Box3 {
    const box = new Box3();
    const els = this.app.loaded?.model.elements;
    if (!els) return box;
    for (const id of ids) {
      const b = els[id]?.bounds;
      if (b) box.union(new Box3(new Vector3(b[0], b[1], b[2]), new Vector3(b[3], b[4], b[5])));
    }
    return box;
  }

  /** Focus set to frame: the classified focus run, else the selection. */
  private focusIds(): ElementId[] {
    const c = this.app.controller;
    if (!c) return [];
    return c.classification.focus.size > 0 ? [...c.classification.focus] : [...c.selection];
  }

  private selKey(): string {
    const c = this.app.controller;
    return c ? [...c.selection].sort((a, b) => a - b).join(',') : '';
  }

  private note(text: string): void {
    this.app.showMessage(text);
    if (this.messageTimer) clearTimeout(this.messageTimer);
    this.messageTimer = setTimeout(() => this.app.showMessage(null), 2500);
  }

  // ------------------------------------------------------------------ fly-to

  get flying(): boolean {
    return this.flight !== null;
  }

  /** Ease the camera and orbit target to frame `box`. */
  flyTo(box: Box3, opts: FlyOptions = {}): void {
    if (box.isEmpty()) return;
    const { camera, controls } = this.r;
    const view = computeFlyView(box, {
      position: camera.position,
      target: controls.target,
      fovDeg: camera.fov,
      aspect: camera.aspect,
      minDistance: controls.minDistance,
      maxDistance: controls.maxDistance,
    }, opts);
    this.stopDolly();
    this.flight = new Flight(
      { position: camera.position, target: controls.target },
      view,
      opts.durationMs ?? this.cfg.flyMs,
      opts.ease,
    );
    this.lastSet = { position: camera.position.clone(), target: controls.target.clone() };
  }

  flyToElements(ids: Iterable<ElementId>, opts: FlyOptions = {}): void {
    this.flyTo(this.boxOf(ids), opts);
  }

  cancelFlight(): void {
    this.flight = null;
    this.lastSet = null;
  }

  private stepFlight(now: number): void {
    const f = this.flight;
    if (!f) return;
    const { camera, controls } = this.r;
    // Something else moved the camera since our last write (a script, or the sidebar): let go.
    const last = this.lastSet;
    if (last) {
      const tol = POSE_EPS * Math.max(1, camera.position.distanceTo(controls.target));
      if (camera.position.distanceTo(last.position) > tol || controls.target.distanceTo(last.target) > tol) {
        this.cancelFlight();
        return;
      }
    }
    const done = f.sample(now, this.flightSet);
    camera.position.copy(this.flightSet.position);
    controls.target.copy(this.flightSet.target);
    if (done) {
      // Close views of small focus sets need a nearer clip plane than the whole-model default.
      const d = camera.position.distanceTo(controls.target);
      if (camera.near > d * 0.05) {
        camera.near = Math.max(d * 0.05, 1e-3);
        camera.updateProjectionMatrix();
      }
      this.cancelFlight();
    } else if (last) {
      last.position.copy(camera.position);
      last.target.copy(controls.target);
    }
  }

  // ------------------------------------------------------------------ hooks

  onModel(): void {
    this.cancelFlight();
    this.stagger.clear();
    this.tour.stop();
    this.stopDolly();
    this.stopPlayback();
    this.endSweep();
    this.viz.clear();
    this.explodeTable = null;
    this.explodeAnim.reset();
    this.explodeButton?.name('Explode');
    this.path = null;
    this.lastSelKey = '';
    this.lastXray = this.app.settings.xray;
    const bounds = this.app.loaded?.geometry.totalBounds();
    if (this.cfg.dressing && bounds) this.dressing.enable(bounds);
    this.applyGlow();
    this.applyGrade();
    this.loadKeys();
  }

  onStatic(): void {
    const app = this.app;
    const key = this.selKey();
    const xray = app.settings.xray;
    const selChanged = key !== this.lastSelKey;
    const xrayOn = xray && !this.lastXray;
    this.lastSelKey = key;
    this.lastXray = xray;

    this.stagger.clear();
    this.endSweep();
    const reveal = key !== '' && (selChanged || xrayOn);
    const mode = this.cfg.sweep.mode;
    const sweepOn = this.cfg.sweep.enabled && usesSweep(mode);
    const staggerOn = this.cfg.reveal && (!this.cfg.sweep.enabled || usesStagger(mode));
    if (reveal && staggerOn) this.beginReveal();
    if (reveal && sweepOn) this.beginSweep();
    if (this.cfg.flyTo && selChanged && key !== '' && !this.suppressFly) this.flyToElements(this.focusIds());
    if (selChanged && this.explodeTable) this.collapse();
    if (selChanged && key !== '' && this.cfg.sightlines.autoOnSelect) this.showSightlines();
    this.applyGlow();
    this.applyGrade();
  }

  /** Focus bounds sphere and the occluder reach (focus radius + buffer radius), shared by the reveal and the grading. */
  private focusReach(): { centre: Vector3; radius: number; reach: number } | null {
    const fbox = this.boxOf(this.focusIds());
    if (fbox.isEmpty()) return null;
    const cls = this.app.controller.classification;
    let buffer = 0;
    for (const v of cls.bufferRadius.values()) buffer = Math.max(buffer, v);
    if (buffer === 0) buffer = this.app.settings.classification.bufferHi;
    const radius = fbox.getBoundingSphere(new Sphere()).radius;
    return { centre: fbox.getCenter(new Vector3()), radius, reach: radius + buffer };
  }

  private beginReveal(): void {
    const c = this.app.controller;
    const cls = c.classification;
    const fr = this.focusReach();
    if (!fr) return;
    const els = this.app.loaded!.model.elements;
    const items = [];
    for (const id of [...cls.host, ...cls.near]) {
      const b = els[id]?.bounds;
      if (b) items.push({ id, box: new Box3(new Vector3(b[0], b[1], b[2]), new Vector3(b[3], b[4], b[5])) });
    }
    if (items.length === 0) return;
    const delays = revealDelays(items, fr.centre, fr.reach);
    this.stagger.begin(performance.now(), delays, this.r.state.alpha);
  }

  // ------------------------------------------------------------------ sweep reveal

  /** Start the sweep plane at the camera side of the occluders (called right after a selection, before the alphas move). */
  beginSweep(): void {
    const app = this.app;
    const cls = app.controller.classification;
    const fr = this.focusReach();
    const els = app.loaded?.model.elements;
    if (!fr || !els) return;
    const occ = [...cls.host, ...cls.near];
    if (occ.length === 0) return;
    const cam = this.r.camera.position;
    const normal = sweepNormal(cam, fr.centre);
    const band = this.cfg.sweep.bandWidth;
    // Exact extent of the occluders along the plane normal, from their vertices.
    const merged = app.loaded!.geometry;
    const pos = merged.geometry.getAttribute('position').array;
    const ext = { lo: Infinity, hi: -Infinity };
    for (const id of occ) {
      const vr = merged.vertexRanges[id];
      if (vr && vr.count > 0) projectionExtent(pos, vr.start, vr.count, normal, ext);
    }
    const range = sweepRangeFromExtent(ext.lo, ext.hi, band);
    // From the camera (or the first occluder, when the camera is further away than that) to past the last one.
    const start = Math.max(range.start, Math.min(normal.dot(cam), range.end));
    if (range.end <= start) return;
    const hold = buildHold(els.length, occ, this.r.state.alpha);
    const now = performance.now();
    this.planeSweep.begin(now, normal, start, range.end, this.cfg.sweep.durationMs);
    this.r.setSweep(hold, app.settings.sightlines.alphaMin, band);
    this.r.setSweepPlane(normal, start);
  }

  private endSweep(): void {
    if (!this.planeSweep.running) return;
    this.planeSweep.stop();
    this.r.setSweep(null);
  }

  // ------------------------------------------------------------------ depth grading

  applyGrade(): void {
    const g = this.cfg.grade;
    const fr = this.app.controller && g.enabled ? this.focusReach() : null;
    // The shader normalises the along-view distance by this radius; with no focus there is nothing to grade.
    if (!fr || this.app.controller.classification.focus.size === 0) this.r.setDepthGrade(null, 0, 0);
    else this.r.setDepthGrade(fr.centre, fr.reach, g.strength);
  }

  // ------------------------------------------------------------------ sightline visualisation

  /** Draw the Algorithm 2 sample rays (sample point -> camera) for `durationS`, then fade them out. Returns the ray count. */
  showSightlines(): number {
    const app = this.app;
    const c = app.controller;
    const geom = app.geometry;
    if (!c || !geom || !app.loaded) return 0;
    const cls = c.classification;
    if (cls.focus.size === 0) {
      this.note('Sightlines: select something first.');
      return 0;
    }
    const o = this.cfg.sightlines;
    const samples = collectSamples(geom, cls.focus, app.settings.sightlines);
    const occ = occluderSet(cls, c.state);
    const q = makeQueries(geom, app.loaded.geometry, occ);
    const rays = buildSightRays(samples.points, this.r.camera.position.clone(), q, o.which, o.max);
    this.viz.show(rays, o.style, performance.now(), o.durationS * 1000, o.colorByHit);
    return rays.length;
  }

  // ------------------------------------------------------------------ exploded context

  get exploded(): boolean {
    return this.explodeAnim.target === 1;
  }

  /**
   * Explode the selection (several elements selected: a storey or class subtree) or the occluders around a
   * single selected element, per cfg.explode.source. Picking stays on the unexploded geometry.
   * Returns the number of elements that move.
   */
  explode(): number {
    const app = this.app;
    const model = app.loaded?.model;
    const c = app.controller;
    if (!model || !c) return 0;
    const els = model.elements;
    const cls = c.classification;
    const cfg = this.cfg.explode;
    const occluders = [...cls.host, ...cls.near];
    const sel = c.selection.size > 0 ? [...c.selection] : [...cls.focus];
    if (sel.length === 0) {
      this.note('Explode: select something first.');
      return 0;
    }
    const { ids, source } = resolveExplodeSet(cfg.source, sel, occluders);
    const bounds = (id: number) => els[id]?.bounds;
    // Around a single element the occluders move away from that element (they would otherwise be centred on themselves).
    let centre = null;
    if (source === 'occluders') {
      const fr = this.focusReach();
      centre = fr ? fr.centre : unionCentre(sel, bounds);
    }
    const table = buildExplodeTable(ids, {
      bounds,
      storeyOf: (id) => els[id]?.storey,
      ranks: storeyRanks(model.storeys),
      centre: centre ?? undefined,
    });
    if (table.ids.length === 0) {
      this.note(source === 'occluders' ? 'Explode: nothing is occluding the selection.' : 'Explode: nothing to explode.');
      return 0;
    }
    if (this.explodeTable) {
      // Elements of the previous table that are not in the new one go home at once.
      const keep = new Set(table.ids);
      for (const id of this.explodeTable.ids) if (!keep.has(id)) this.r.setElementOffset(id, 0, 0, 0);
    }
    this.explodeTable = table;
    this.explodeAnim.go(1, performance.now(), cfg.durationMs);
    this.explodeButton?.name('Collapse');
    return table.ids.length;
  }

  collapse(): void {
    if (!this.explodeTable) {
      this.explodeButton?.name('Explode');
      return;
    }
    this.explodeAnim.go(0, performance.now(), this.cfg.explode.durationMs);
    this.explodeButton?.name('Explode');
  }

  /** The explode source changed while exploded: rebuild the table for the new set. */
  private reexplode(): void {
    if (this.explodeTable && this.explodeAnim.target === 1) this.explode();
  }

  markExplodeDirty(): void {
    this.explodeDirty = true;
  }

  private stepExplode(now: number): void {
    const t = this.explodeTable;
    if (!t) return;
    if (!this.explodeAnim.moving && !this.explodeDirty) return;
    this.explodeDirty = false;
    const k = this.explodeAnim.update(now);
    const o = this.tmp;
    for (let i = 0; i < t.ids.length; i++) {
      explodeOffset(t, i, this.cfg.explode, k, o);
      this.r.setElementOffset(t.ids[i]!, o.x, o.y, o.z);
    }
    if (k === 0 && this.explodeAnim.target === 0) {
      this.explodeTable = null;
      this.r.clearElementOffsets();
    }
  }

  // ------------------------------------------------------------------ fly-through

  /** Distance along the view axis from the camera to the focus centre (null without a focus). */
  focusViewDistance(): number | null {
    if (!this.app.controller || this.app.controller.classification.focus.size === 0) return null;
    const fbox = this.boxOf(this.app.controller.classification.focus);
    if (fbox.isEmpty()) return null;
    const { camera, controls } = this.r;
    const fwd = this.tmp.subVectors(controls.target, camera.position);
    if (fwd.lengthSq() < 1e-12) return null;
    fwd.normalize();
    const d = new Vector3().subVectors(fbox.getCenter(new Vector3()), camera.position).dot(fwd);
    return d > 1e-3 ? d : null;
  }

  currentToggles(): KeyframeToggles {
    const c = this.cfg;
    return {
      reveal: c.reveal,
      sweep: c.sweep.enabled,
      depthGrade: c.grade.enabled,
      bloom: c.bloom,
      edgeGlow: c.edgeGlow,
      ao: this.post.settings.ao,
      vignette: this.post.settings.vignette,
    };
  }

  /** Apply stored toggles the way the GUI does (config, side effects, GUI refresh). */
  applyToggles(t: KeyframeToggles): void {
    const c = this.cfg;
    if (t.reveal !== undefined) c.reveal = t.reveal;
    if (t.sweep !== undefined) c.sweep.enabled = t.sweep;
    if (t.depthGrade !== undefined) {
      c.grade.enabled = t.depthGrade;
      this.applyGrade();
    }
    if (t.bloom !== undefined && t.bloom !== c.bloom) {
      c.bloom = t.bloom;
      if (t.bloom) this.bloom.enable();
      else this.bloom.disable();
    }
    if (t.edgeGlow !== undefined) {
      c.edgeGlow = t.edgeGlow;
      this.applyGlow();
    }
    if (t.ao !== undefined) this.post.settings.ao = t.ao;
    if (t.vignette !== undefined) this.post.settings.vignette = t.vignette;
    this.post.sync();
    this.gui?.controllersRecursive().forEach((ctl) => ctl.updateDisplay());
  }

  private storage(): Storage | null {
    try {
      return window.localStorage;
    } catch {
      return null;
    }
  }

  private refreshKeyInfo(): void {
    this.keyInfo.keyframes = `${this.keys.length}`;
    this.keyInfoCtl?.updateDisplay();
  }

  private saveKeys(): void {
    this.refreshKeyInfo();
    try {
      this.storage()?.setItem(flythroughKey(this.app.modelName), serializeKeyframes(this.app.modelName, this.keys, this.cfg.fly.segmentS));
    } catch {
      /* quota or private mode: keep the keyframes in memory */
    }
  }

  private loadKeys(): void {
    let raw: string | null = null;
    try {
      raw = this.storage()?.getItem(flythroughKey(this.app.modelName)) ?? null;
    } catch {
      raw = null;
    }
    this.keys = parseKeyframes(raw) ?? [];
    this.refreshKeyInfo();
  }

  addKeyframe(): Keyframe | null {
    const m = this.app.loaded?.model;
    if (!m) return null;
    const { camera, controls } = this.r;
    const k: Keyframe = {
      position: camera.position.toArray() as [number, number, number],
      target: controls.target.toArray() as [number, number, number],
      selection: idsToGlobalIds(m, this.app.selection),
      toggles: this.currentToggles(),
      name: `Keyframe ${this.keys.length + 1}`,
    };
    this.keys.push(k);
    this.saveKeys();
    return k;
  }

  clearKeys(): void {
    this.keys = [];
    this.saveKeys();
  }

  removeLastKey(): void {
    this.keys.pop();
    this.saveKeys();
  }

  exportJson(): string {
    return serializeKeyframes(this.app.modelName, this.keys, this.cfg.fly.segmentS);
  }

  /** Replace the keyframes with the ones in `text` (export file or bare array). Returns false for invalid input. */
  importJson(text: string): boolean {
    const keys = parseKeyframes(text);
    if (!keys) return false;
    this.keys = keys;
    this.saveKeys();
    return true;
  }

  /** One keyframe per stored selection set (xray.sets.<model>), the camera framed on the set with the fly-to fit maths. */
  loadFromSets(): number {
    const app = this.app;
    const model = app.loaded?.model;
    if (!model) return 0;
    const stored = (() => {
      try {
        const st = this.storage();
        return st ? loadSets(st, app.modelName) : null;
      } catch {
        return null;
      }
    })();
    const sets = stored && stored.length > 0 ? stored : defaultSetsFor(model, app.modelName);
    const { camera, controls } = this.r;
    const keys: Keyframe[] = [];
    for (const set of sets) {
      const ids = globalIdsToIds(model, set.globalIds);
      const ub = unionBounds(model, ids);
      if (!ub) continue;
      const view = computeFlyView(
        new Box3(new Vector3(ub[0], ub[1], ub[2]), new Vector3(ub[3], ub[4], ub[5])),
        { position: camera.position, target: controls.target, fovDeg: camera.fov, aspect: camera.aspect, minDistance: controls.minDistance, maxDistance: controls.maxDistance },
      );
      keys.push({
        position: view.position.toArray() as [number, number, number],
        target: view.target.toArray() as [number, number, number],
        selection: [...set.globalIds],
        toggles: this.currentToggles(),
        name: set.name,
      });
    }
    if (keys.length === 0) {
      this.note('No selection sets to build keyframes from.');
      return 0;
    }
    this.keys = keys;
    this.saveKeys();
    return keys.length;
  }

  get playing(): boolean {
    return this.player !== null;
  }

  /** Play the keyframes: Catmull-Rom through positions and targets, selection and toggles switching at each keyframe. */
  play(onEnd?: () => void): boolean {
    if (this.keys.length === 0) {
      this.note('Fly-through: add keyframes first.');
      return false;
    }
    this.stopTour();
    this.stopDolly();
    this.cancelFlight();
    this.stopPlayback();
    this.player = new FlyPlayer(this.keys, this.cfg.fly.segmentS * 1000);
    this.playEnd = onEnd ?? null;
    this.post.setPlaying(true);
    return true;
  }

  stopPlayback(): void {
    if (!this.player) return;
    this.player = null;
    this.post.setPlaying(false);
    const cb = this.playEnd;
    this.playEnd = null;
    cb?.();
  }

  private applyKeyframe(k: Keyframe): void {
    const m = this.app.loaded?.model;
    if (!m) return;
    this.applyToggles(k.toggles);
    const ids = globalIdsToIds(m, k.selection);
    const key = [...ids].sort((a, b) => a - b).join(',');
    if (key === this.selKey()) return;
    // The fly-through owns the camera: the usual fly-to is off while it plays.
    this.suppressFly = true;
    try {
      if (ids.length > 0) this.app.selectIds(ids);
      else this.app.clearSelection();
    } finally {
      this.suppressFly = false;
    }
  }

  private stepPlayback(now: number): void {
    const p = this.player;
    if (!p) return;
    const { camera, controls } = this.r;
    const s = p.sample(now, this.camPos, this.camTgt);
    camera.position.copy(this.camPos);
    controls.target.copy(this.camTgt);
    for (const i of p.reached(s)) {
      const k = this.keys[i];
      if (k) this.applyKeyframe(k);
    }
    if (s.done) this.stopPlayback();
  }

  /** Play while recording the canvas (MediaRecorder, 30 fps, webm vp9 else vp8) and download fly-through.webm at the end. */
  record(): boolean {
    if (this.recorder.recording) return false;
    if (this.keys.length === 0) {
      this.note('Fly-through: add keyframes first.');
      return false;
    }
    const ok = this.recorder.start(this.app.canvas, (rec) => {
      this.lastRecording = rec;
      if (rec && rec.bytes > 0) {
        downloadBlob(rec.blob, 'fly-through.webm');
        this.note(`Saved fly-through.webm (${(rec.bytes / 1024).toFixed(0)} KB, ${rec.mime}).`);
      } else {
        this.note('Recording produced no data.');
      }
    });
    if (!ok) {
      this.note('Recording is not available in this browser (MediaRecorder / canvas.captureStream / webm).');
      return false;
    }
    // Let the last frame land before stopping.
    const started = this.play(() => {
      if (this.recordTimer) clearTimeout(this.recordTimer);
      this.recordTimer = setTimeout(() => this.recorder.stop(), 300);
    });
    if (!started) this.recorder.stop();
    return started;
  }

  get recording(): boolean {
    return this.recorder.recording;
  }

  onFrame(now: number, dt: number): boolean {
    let dirty = false;
    if (this.stagger.size > 0) this.stagger.apply(now, this.r.state.alpha);
    if (this.planeSweep.running) {
      this.r.setSweepPlane(this.planeSweep.normal, this.planeSweep.offsetAt(now));
      if (this.planeSweep.doneAt(now)) this.endSweep();
    }
    if (this.player) this.stepPlayback(now);
    else if (this.flight) this.stepFlight(now);
    else if (this.cfg.dollyPlaying || this.dollyScrub) dirty = this.stepDolly(dt) || dirty;
    else if (this.cfg.autoOrbit) this.stepOrbit(now, dt);
    if (this.dressing.enabled) this.dressing.updateFog();
    if (this.explodeTable) this.stepExplode(now);
    if (this.viz.active) this.viz.update(now);
    return dirty;
  }

  // ------------------------------------------------------------------ turntable

  private stepOrbit(now: number, dt: number): void {
    if (this.pointerDown || now - this.lastInput < IDLE_RESUME_MS) return;
    const { camera, controls } = this.r;
    const angle = (this.cfg.orbitSpeed * Math.PI / 180) * Math.min(dt, 100) / 1000;
    const off = this.tmp.subVectors(camera.position, controls.target).applyAxisAngle(UP, angle);
    camera.position.copy(controls.target).add(off);
  }

  // ------------------------------------------------------------------ dolly

  private dollyScrub = false;

  private buildPath(): boolean {
    const app = this.app;
    const ids = this.focusIds();
    if (ids.length < 2 || !app.loaded) return false;
    const centres = new Map<number, Vector3>();
    const els = app.loaded.model.elements;
    for (const id of ids) {
      const b = els[id]?.bounds;
      if (b) centres.set(id, new Vector3((b[0] + b[3]) / 2, (b[1] + b[4]) / 2, (b[2] + b[5]) / 2));
    }
    const { path } = buildRunPath(ids, centres, app.loaded.model.relations.ports, this.r.camera.position);
    if (path.length <= 1e-6 || path.points.length < 2) return false;
    this.path = path;
    return true;
  }

  playDolly(): void {
    if (!this.path && !this.buildPath()) {
      this.note('Dolly needs a selected run of two or more elements.');
      this.cfg.dollyPlaying = false;
      return;
    }
    this.cancelFlight();
    if (this.dollyS >= this.path!.length - 1e-6) this.dollyS = 0;
    this.cfg.dollyPlaying = true;
    this.dollyButton?.name('Pause dolly');
  }

  pauseDolly(): void {
    this.cfg.dollyPlaying = false;
    this.dollyButton?.name('Play dolly');
  }

  private stopDolly(): void {
    this.pauseDolly();
  }

  /** Move to progress 0..1 along the path (builds the path if needed). */
  scrubDolly(p: number): void {
    if (!this.path && !this.buildPath()) return;
    this.cancelFlight();
    this.dollyS = Math.min(1, Math.max(0, p)) * this.path!.length;
    this.dollyScrub = true;
  }

  private stepDolly(dt: number): boolean {
    const path = this.path;
    if (!path) {
      this.pauseDolly();
      this.dollyScrub = false;
      return false;
    }
    const L = path.length;
    const playing = this.cfg.dollyPlaying;
    if (playing) this.dollyS = Math.min(L, this.dollyS + (this.cfg.dollySpeed * Math.min(dt, 100)) / 1000);
    const look = Math.min(6, Math.max(1.5, L * 0.1));
    const { camera, controls } = this.r;
    const pos = path.pointAt(this.dollyS, new Vector3());
    pos.y += this.cfg.dollyHeight;
    const tgt = path.pointAt(Math.min(L, this.dollyS + look), new Vector3());
    const k = this.dollyScrub ? 1 : 1 - Math.exp(-Math.min(dt, 100) / 1000 * 5);
    camera.position.lerp(pos, k);
    controls.target.lerp(tgt, k);
    this.dollyScrub = false;
    this.cfg.dollyProgress = L > 0 ? this.dollyS / L : 0;
    if (playing && this.dollyS >= L) this.pauseDolly();
    const t = performance.now();
    if (t - this.lastGuiUpdate > 120) {
      this.lastGuiUpdate = t;
      this.dollyProgressCtl?.updateDisplay();
    }
    return false;
  }

  // ------------------------------------------------------------------ tour

  startTour(): boolean {
    const app = this.app;
    if (!app.loaded) return false;
    const focusClasses = new Set(app.settings.classification.focusClasses);
    let storage: Storage | null = null;
    try {
      storage = window.localStorage;
    } catch {
      storage = null;
    }
    const steps = buildTourSteps(app.loaded.model, app.modelName, focusClasses, storage);
    if (steps.length === 0) {
      this.note('Tour: no stored sets and no storey focus elements.');
      return false;
    }
    this.stopDolly();
    const ok = this.tour.start(steps);
    if (ok) this.tourButton?.name('Stop tour');
    return ok;
  }

  stopTour(): void {
    this.tour.stop();
    this.tourButton?.name('Play tour');
  }

  // ------------------------------------------------------------------ glow

  applyGlow(): void {
    const app = this.app;
    if (!this.cfg.edgeGlow || !app.controller) {
      this.r.setEdgeGlow(null);
      return;
    }
    const ctl = app.controller;
    // Hidden elements need no filter here: the glow shader skips them, also after a later hide or unhide.
    const ids = glowIds(this.cfg.glowScope, ctl.classification, ctl.model.elements.length);
    this.r.setEdgeGlow(ids, hexToRgb(this.cfg.glowColor), { strength: this.cfg.glowStrength, additive: this.cfg.glowAdditive });
  }

  // ------------------------------------------------------------------ input

  userInput(): void {
    this.lastInput = performance.now();
    this.cancelFlight();
    if (this.cfg.dollyPlaying) this.pauseDolly();
    if (this.tour.running) this.stopTour();
    if (this.player) this.stopPlayback();
  }

  private pickImport(): void {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'application/json,.json';
    input.onchange = () => {
      const file = input.files?.[0];
      if (!file) return;
      void file.text().then((t) => {
        if (!this.importJson(t)) this.note('Import: not a fly-through JSON file.');
        else this.note(`Imported ${this.keys.length} keyframes.`);
      });
    };
    input.click();
  }

  // ------------------------------------------------------------------ install

  install(): void {
    const app = this.app;
    const canvas = app.canvas;
    canvas.addEventListener('pointerdown', () => {
      this.pointerDown = true;
      this.userInput();
    });
    const up = (): void => {
      this.pointerDown = false;
      this.lastInput = performance.now();
    };
    window.addEventListener('pointerup', up);
    window.addEventListener('pointercancel', up);
    canvas.addEventListener('wheel', () => this.userInput(), { passive: true });

    window.addEventListener('xray:frame', (e: Event) => {
      if (!this.cfg.flyTo) return; // leave it to the sender's own fallback
      const detail = (e as CustomEvent<{ box?: { min: Vector3; max: Vector3 } }>).detail;
      const b = detail?.box;
      if (!b || !b.min || !b.max) return;
      const box = b instanceof Box3 ? b : new Box3(new Vector3().copy(b.min), new Vector3().copy(b.max));
      if (box.isEmpty()) return;
      e.preventDefault();
      this.flyTo(box);
    });

    if (app.panel) this.buildGui(app.panel);
  }

  private buildGui(panel: GUI): void {
    const cfg = this.cfg;
    const f = panel.addFolder('Cinematic');
    f.close();
    this.gui = f;
    const fly = f.addFolder('Camera fly-to');
    fly.add(cfg, 'flyTo').name('Fly to selection');
    fly.add(cfg, 'flyMs', 200, 3000, 50).name('Duration (ms)');
    const actions = {
      frameFocus: () => this.flyToElements(this.focusIds()),
    };
    fly.add(actions, 'frameFocus').name('Fly to focus now');
    fly.add(cfg, 'reveal').name('Staggered reveal');

    const dress = f.addFolder('Scene dressing');
    dress.add(cfg, 'dressing').name('Sky, fog, lights').onChange((v: boolean) => {
      const b = this.app.loaded?.geometry.totalBounds();
      if (v && b) this.dressing.enable(b);
      else this.dressing.disable();
    });
    dress.add(cfg, 'fogStrength', 0, 0.8, 0.01).name('Fog strength').onChange((v: number) => this.dressing.setSettings({ fogStrength: v }));
    dress.add(cfg, 'groundShadow').name('Ground shadow plane (+1 draw)').onChange((v: boolean) => this.dressing.setSettings({ ground: v }));
    dress.add(cfg, 'shadowStrength', 0, 0.8, 0.01).name('Shadow strength').onChange((v: number) => this.dressing.setSettings({ shadowStrength: v }));

    const bl = f.addFolder('Focus bloom');
    bl.add(cfg, 'bloom').name('Selective bloom').onChange((v: boolean) => (v ? this.bloom.enable() : this.bloom.disable()));
    bl.add(cfg, 'bloomStrength', 0, 3, 0.05).name('Strength').onChange((v: number) => (this.bloom.settings.strength = v));
    bl.add(cfg, 'bloomRadius', 0, 1, 0.01).name('Radius').onChange((v: number) => (this.bloom.settings.radius = v));

    const eg = f.addFolder('Edge glow');
    eg.add(cfg, 'edgeGlow').name('Edge glow').onChange(() => this.applyGlow());
    eg.add(cfg, 'glowScope', [...GLOW_SCOPES]).name('glow scope').onChange(() => this.applyGlow());
    eg.add(cfg, 'glowAdditive').name('Additive').onChange(() => this.applyGlow());
    eg.add(cfg, 'glowStrength', 0, 2, 0.01).name('Strength').onChange(() => this.applyGlow());
    eg.addColor(cfg, 'glowColor').name('Colour').onChange(() => this.applyGlow());

    const sw = f.addFolder('Sweep reveal');
    sw.add(cfg.sweep, 'enabled').name('Sweep reveal').onChange(() => this.endSweep());
    sw.add(cfg.sweep, 'mode', ['stagger', 'sweep', 'both']).name('Mode');
    sw.add(cfg.sweep, 'durationMs', 200, 3000, 50).name('Duration (ms)');
    sw.add(cfg.sweep, 'bandWidth', 0.02, 0.6, 0.01).name('Band width (m)');
    sw.close();

    const dg = f.addFolder('Depth-graded ghosting');
    dg.add(cfg.grade, 'enabled').name('Depth grading').onChange(() => this.applyGrade());
    dg.add(cfg.grade, 'strength', 0, 1, 0.01).name('Strength').onChange(() => this.applyGrade());
    dg.close();

    const sl = f.addFolder('Sightlines');
    sl.add({ show: () => void this.showSightlines() }, 'show').name('Show sightlines');
    sl.add(cfg.sightlines, 'autoOnSelect').name('On selection');
    sl.add(cfg.sightlines, 'style', ['lines', 'dots', 'both']).name('Style');
    sl.add(cfg.sightlines, 'which', ['all', 'blocked', 'unblocked']).name('Which rays');
    sl.add(cfg.sightlines, 'colorByHit').name('Colour by hit');
    sl.add(cfg.sightlines, 'max', 10, 500, 10).name('Max rays');
    sl.add(cfg.sightlines, 'durationS', 0.2, 6, 0.1).name('Fade (s)');
    sl.close();

    const fx = f.addFolder('AO + vignette (extra GPU cost)');
    const ps = this.post.settings;
    fx.add(ps, 'ao').name('AO (GTAO, half res)').onChange(() => this.post.sync());
    fx.add(ps, 'aoRadius', 0.05, 3, 0.05).name('AO radius (m)');
    fx.add(ps, 'aoIntensity', 0, 2, 0.05).name('AO intensity');
    fx.add(ps, 'vignette').name('Vignette').onChange(() => this.post.sync());
    fx.add(ps, 'vignetteDarkness', 0, 1.5, 0.05).name('Vignette darkness');
    fx.close();

    const ex = f.addFolder('Exploded view (picking stays unexploded)');
    const exActions = { toggle: () => (this.exploded ? this.collapse() : void this.explode()) };
    this.explodeButton = ex.add(exActions, 'toggle').name('Explode') as never;
    ex.add(cfg.explode, 'source', { auto: 'auto', selection: 'selection', occluders: 'occluders', 'selection + occluders': 'both' }).name('explode')
      .onChange(() => this.reexplode());
    ex.add(cfg.explode, 'mode', [...EXPLODE_MODES]).name('Mode').onChange(() => this.markExplodeDirty());
    ex.add(cfg.explode, 'factor', 0, 3, 0.05).name('Radial factor').onChange(() => this.markExplodeDirty());
    ex.add(cfg.explode, 'storeyGap', 0, 10, 0.1).name('Storey gap (m)').onChange(() => this.markExplodeDirty());
    ex.add(cfg.explode, 'minPush', 0, 3, 0.05).name('Min push (m)').onChange(() => this.markExplodeDirty());
    ex.add(cfg.explode, 'durationMs', 100, 3000, 50).name('Duration (ms)');
    ex.close();

    const ft = f.addFolder('Fly-through');
    this.keyInfoCtl = ft.add(this.keyInfo, 'keyframes').name('Keyframes').disable() as never;
    ft.add({ add: () => void this.addKeyframe() }, 'add').name('Add keyframe');
    ft.add({ rm: () => this.removeLastKey() }, 'rm').name('Remove last');
    ft.add({ clear: () => this.clearKeys() }, 'clear').name('Clear');
    ft.add({ sets: () => void this.loadFromSets() }, 'sets').name('Load from selection sets');
    ft.add(cfg.fly, 'segmentS', 0.5, 10, 0.1).name('Seconds per segment');
    ft.add({ play: () => (this.playing ? this.stopPlayback() : void this.play()) }, 'play').name('Play / stop');
    ft.add({ rec: () => void this.record() }, 'rec').name('Record (webm download)');
    ft.add({ exp: () => downloadBlob(new Blob([this.exportJson()], { type: 'application/json' }), `fly-through-${this.app.modelName}.json`) }, 'exp').name('Export JSON');
    ft.add({ imp: () => this.pickImport() }, 'imp').name('Import JSON');
    ft.add(ps, 'dof').name('Depth of field (playback)').onChange(() => this.post.sync());
    ft.add(ps, 'dofAperture', 0, 1, 0.01).name('Aperture');
    ft.add(ps, 'motionBlur', 0, 0.9, 0.01).name('Motion blur (playback)').onChange(() => this.post.sync());
    ft.close();

    const orbit = f.addFolder('Turntable');
    orbit.add(cfg, 'autoOrbit').name('Auto-orbit');
    orbit.add(cfg, 'orbitSpeed', -60, 60, 0.5).name('Speed (deg/s)');

    const dolly = f.addFolder('Dolly along run');
    const dollyActions = { toggle: () => (cfg.dollyPlaying ? this.pauseDolly() : this.playDolly()) };
    this.dollyButton = dolly.add(dollyActions, 'toggle').name('Play dolly') as never;
    dolly.add(cfg, 'dollySpeed', 0.1, 10, 0.1).name('Speed (m/s)');
    dolly.add(cfg, 'dollyHeight', -2, 6, 0.1).name('Height offset (m)');
    this.dollyProgressCtl = dolly.add(cfg, 'dollyProgress', 0, 1, 0.001).name('Progress').onChange((v: number) => {
      this.pauseDolly();
      this.scrubDolly(v);
    }) as never;

    const tour = f.addFolder('Tour');
    const tourActions = { toggle: () => (this.tour.running ? this.stopTour() : void this.startTour()) };
    this.tourButton = tour.add(tourActions, 'toggle').name('Play tour') as never;
    tour.add(cfg, 'tourHold', 0.5, 15, 0.5).name('Hold (s)');
    tour.add(cfg, 'tourLoop').name('Loop');
  }
}

let instance: Cinematic | null = null;

/** The plugin's controller, once installed (for scripts: `window.__cinematic`). */
export function getCinematic(): Cinematic | null {
  return instance;
}

export const cinematicPlugin: AppPlugin = {
  name: 'cinematic',
  install(app) {
    const q = new URLSearchParams(location.search);
    const off = q.get('cinematic') === 'off';
    instance = new Cinematic(app, off, off || q.get('cin2') === 'off');
    instance.install();
    (window as unknown as { __cinematic?: Cinematic }).__cinematic = instance;
  },
  onModel() {
    instance?.onModel();
  },
  onStatic() {
    instance?.onStatic();
  },
  onFrame(_app, now, dt) {
    return instance ? instance.onFrame(now, dt) : false;
  },
};
