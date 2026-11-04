// XrayController: the non-DOM, non-GL state of the viewer.
//
// Owns settings, selection, classification, floors, sightline targets and the per-frame
// smoothing step. It takes the GeometryProvider and RenderState it writes to as inputs, so it
// can be driven by the box mock in tests and by the BVH geometry and renderer in the app.
//
// Update sequence:
//   selection / settings change  ->  reclassify()      Algorithm 1 + 7 (+ 8 in tiers mode)
//   camera change (debounced)    ->  updateSightlines() Algorithm 2 (or 9)
//   every animation frame        ->  tick()             smoothing (Algorithm 2, L10-11) + render state

import type { Vector3 } from 'three';
import {
  DEFAULT_CLASSIFICATION,
  DEFAULT_OVERRIDES,
  DEFAULT_SIGHTLINES,
  FLAG_FOCUS,
  FLAG_HIDDEN,
  FLAG_SELECTED,
  HIDDEN,
  type Classification,
  type ClassStyles,
  type ClassificationSettings,
  type ElementId,
  type FarMode,
  type OccluderScope,
  type GeometryProvider,
  type OverrideSettings,
  type RenderState,
  type SceneModel,
  type SightlineResult,
  type SightlineSettings,
} from './types';
import {
  DEFAULT_TIER_SETTINGS,
  applyRenderState,
  classify,
  classifyTiers,
  computeFloors,
  sightlines,
  sightlinesTiered,
  smoothAlpha,
  scopeOf,
  type TierSettings,
  type TieredClassification,
} from './algo';
import { resolveStyleIndex, styleKeyCounts, type MaterialAliases, type ResolvedStyle } from './styles';

export const CONVERGED_EPS = 1e-3;

export interface ControllerSettings {
  /** Master switch. Off: everything opaque, no focus, no ghosts. */
  xray: boolean;
  classification: ClassificationSettings;
  sightlines: SightlineSettings;
  overrides: OverrideSettings;
  farMode: FarMode;
  /** Use Algorithms 8/9 with `tiers` instead of Algorithms 1/2. */
  tiersMode: boolean;
  /** tiers[0] is the focus tier (most important). */
  tiers: string[][];
  /** Per-class base alpha cap, ghosting floor, colour and visibility. Key: ifcClass or alias. */
  classStyles: ClassStyles;
  /** alias -> ["IfcMember", "IfcBeam:steel", ...] (see styles.ts). */
  materialAliases: MaterialAliases;
}

export function defaultTiers(focusClasses: readonly string[]): string[][] {
  return [
    [...focusClasses],
    ['IfcBeam', 'IfcColumn'],
    ['IfcSlab', 'IfcWall', 'IfcWallStandardCase', 'IfcFooting'],
  ];
}

export function defaultSettings(): ControllerSettings {
  return {
    xray: true,
    classification: { ...DEFAULT_CLASSIFICATION, focusClasses: [...DEFAULT_CLASSIFICATION.focusClasses], ctxClasses: [...DEFAULT_CLASSIFICATION.ctxClasses] },
    sightlines: { ...DEFAULT_SIGHTLINES },
    overrides: {
      userPins: new Set(DEFAULT_OVERRIDES.userPins),
      userHides: new Set(DEFAULT_OVERRIDES.userHides),
      userPinFloor: DEFAULT_OVERRIDES.userPinFloor,
      categoryFloors: { ...DEFAULT_OVERRIDES.categoryFloors },
      projectPins: { ...DEFAULT_OVERRIDES.projectPins },
    },
    farMode: 'opaque',
    tiersMode: false,
    tiers: defaultTiers(DEFAULT_CLASSIFICATION.focusClasses),
    classStyles: {},
    materialAliases: {},
  };
}

export interface ControllerStats {
  elements: number;
  buckets: { focus: number; host: number; near: number; far: number };
  /** Last Algorithm 1 duration, ms. */
  classifyMs: number;
  classifyCount: number;
  /** Last Algorithm 2 duration, ms. */
  sightlinesMs: number;
  /** Rays cast by the last Algorithm 2 run. */
  rays: number;
  sightlinesCount: number;
  /** Per-run history, for the benchmark. */
  classifyHistory: number[];
  sightlinesHistory: Array<{ ms: number; rays: number }>;
  /** Frame timing, filled in by the app. */
  frameMs: number;
  /** Mean CPU time of tick + render over the same window, ms. */
  frameCpuMs: number;
}

export type Bucket = 'focus' | 'host' | 'near' | 'far' | 'none';

export interface ElementInfo {
  id: ElementId;
  ifcClass: string;
  name?: string;
  bucket: Bucket;
  proximityWeight: number;
  occlusion: number;
  targetAlpha: number;
  alpha: number;
}

function emptyClassification(): Classification {
  return { focus: new Set(), host: new Set(), near: new Set(), far: new Set(), proximityWeight: new Map(), bufferRadius: new Map() };
}

export class XrayController {
  readonly model: SceneModel;
  readonly state: RenderState;
  readonly settings: ControllerSettings;
  readonly stats: ControllerStats;

  selection = new Set<ElementId>();
  classification: Classification = emptyClassification();
  tiered: TieredClassification | null = null;
  floors = new Map<ElementId, number>();
  result: SightlineResult = { occlusion: new Map(), importance: new Map(), targetAlpha: new Map() };
  /** Target alpha per occluder (from the last sightline run). */
  get targets(): ReadonlyMap<ElementId, number> {
    return this.result.targetAlpha;
  }
  /** True when every alpha is within CONVERGED_EPS of its target (smoothing is skipped). */
  converged = true;

  private readonly geometry: GeometryProvider;
  private rayCount = 0;
  /** Elements that were occluders before the last reclassify and are easing back to opaque. */
  private readonly fading = new Map<ElementId, number>();
  private needsApply = true;
  private plainApplied = false;
  /** Resolved class style per element id (null: none). Rebuilt by rebuildStyleIndex. */
  private styleIndex: Array<ResolvedStyle | null> = [];
  /** Elements whose state.color currently holds a style colour (restored when the style goes). */
  private readonly styleColored = new Set<ElementId>();
  /** occluderScope the current floors/fading bookkeeping was built for. */
  private appliedScope: OccluderScope = 'all';

  constructor(model: SceneModel, geometry: GeometryProvider, state: RenderState, settings?: Partial<ControllerSettings>) {
    this.model = model;
    this.state = state;
    // Keep the caller's object by reference when it is a complete settings record, so GUI
    // bindings on app.settings (xray, farMode, tiersMode, ...) reach the controller. A partial
    // record (tests) is merged over the defaults into a fresh object.
    const merged: ControllerSettings = { ...defaultSettings(), ...settings };
    const complete = settings !== undefined && (Object.keys(merged) as Array<keyof ControllerSettings>).every((k) => k in settings);
    this.settings = complete ? (settings as ControllerSettings) : merged;
    this.rebuildStyleIndex();
    // Count rays by wrapping the provider (the sample cache is keyed by this wrapper, which is stable).
    this.geometry = {
      bounds: (id) => geometry.bounds(id),
      surfaceDistance: (a, b) => geometry.surfaceDistance(a, b),
      intersects: (a, b) => geometry.intersects(a, b),
      samplePoints: (id, n) => geometry.samplePoints(id, n),
      raycastAll: (o, d, m, c) => {
        this.rayCount++;
        return geometry.raycastAll(o, d, m, c);
      },
    };
    this.stats = {
      elements: model.elements.length,
      buckets: { focus: 0, host: 0, near: 0, far: 0 },
      classifyMs: 0,
      classifyCount: 0,
      sightlinesMs: 0,
      rays: 0,
      sightlinesCount: 0,
      classifyHistory: [],
      sightlinesHistory: [],
      frameMs: 0,
      frameCpuMs: 0,
    };
  }

  // ------------------------------------------------------------ class styles

  /**
   * Replace the class styles (and, when given, the aliases), re-resolve the per-element index and
   * mark the render state stale. Call reclassify() afterwards (app.reclassify()) so the new
   * alphaMin/floor values reach the sightline targets; alphaMax, colour and hidden apply at once.
   */
  setClassStyles(styles: ClassStyles, aliases?: MaterialAliases): void {
    this.settings.classStyles = styles;
    if (aliases) this.settings.materialAliases = aliases;
    this.rebuildStyleIndex();
    this.computeFloorsNow();
    this.restyleTargets();
    this.needsApply = true;
    this.converged = false;
    this.plainApplied = false;
  }

  /** Resolved style of one element (null when none applies). */
  styleOf(id: ElementId): Readonly<ResolvedStyle> | null {
    return this.styleIndex[id] ?? null;
  }

  /** Style keys that matter for this model with their element counts (classes present, live aliases). */
  styleKeys(): Array<{ key: string; count: number; kind: 'class' | 'alias' }> {
    return styleKeyCounts(this.model, this.settings.materialAliases);
  }

  private rebuildStyleIndex(): void {
    const s = this.settings;
    this.styleIndex = resolveStyleIndex(this.model, s.classStyles, s.materialAliases);
  }

  /** Effective cap for an element in its current bucket (1 when uncapped). */
  private capOf(id: ElementId): number {
    const st = this.styleIndex[id];
    if (!st) return 1;
    const cap = this.classification.focus.has(id) ? st.alphaMaxOwn : st.alphaMax;
    return cap === undefined ? 1 : Math.min(1, Math.max(0, cap));
  }

  /**
   * alphaMin override: targets were computed with sightlines.alphaMin; redo L9 for elements whose
   * class sets its own alphaMin, from the stored importance.
   */
  private restyleTargets(): void {
    const t = this.result.targetAlpha;
    if (t.size === 0) return;
    const alphaMax = this.settings.sightlines.alphaMax;
    const lo = this.settings.sightlines.alphaMin;
    const far = this.classification.far;
    for (const [id, imp] of this.result.importance) {
      const hi = far.has(id) ? 1 : alphaMax; // Far elements ghost from a ceiling of 1
      const own = this.styleIndex[id]?.alphaMin;
      if (own !== undefined) t.set(id, hi + (own - hi) * imp);
      else if (!this.settings.tiersMode) t.set(id, hi + (lo - hi) * imp); // tiers keep their per-tier minima
    }
  }

  /** Cap alpha, set the hidden flag and write colour overrides (also restores dropped colours). */
  private applyStyles(): void {
    const { alpha, flags, color } = this.state;
    const els = this.model.elements;
    for (const id of this.styleColored) {
      const st = this.styleIndex[id];
      if (st?.color) continue;
      const b = els[id]?.color;
      if (b) {
        color[id * 3] = b[0];
        color[id * 3 + 1] = b[1];
        color[id * 3 + 2] = b[2];
      }
      this.styleColored.delete(id);
    }
    for (let id = 0; id < this.styleIndex.length; id++) {
      const st = this.styleIndex[id];
      if (!st) continue;
      const cap = this.capOf(id);
      if (cap < 1 && (alpha[id] ?? 1) > cap) alpha[id] = cap;
      if (st.hidden) flags[id] = (flags[id] ?? 0) | FLAG_HIDDEN;
      if (st.color) {
        color[id * 3] = st.color[0];
        color[id * 3 + 1] = st.color[1];
        color[id * 3 + 2] = st.color[2];
        this.styleColored.add(id);
      }
    }
  }

  // ------------------------------------------------------------ selection

  setSelection(ids: Iterable<ElementId>): void {
    const next = new Set<ElementId>();
    for (const id of ids) if (id >= 0 && id < this.model.elements.length) next.add(id);
    for (const id of this.selection) this.state.flags[id] = (this.state.flags[id] ?? 0) & ~FLAG_SELECTED;
    this.selection = next;
    for (const id of next) this.state.flags[id] = (this.state.flags[id] ?? 0) | FLAG_SELECTED;
    this.reclassify();
  }

  addToSelection(ids: Iterable<ElementId>): void {
    this.setSelection([...this.selection, ...ids]);
  }

  clearSelection(): void {
    this.setSelection([]);
  }

  // ------------------------------------------------------------ overrides

  pinSelected(): void {
    for (const id of this.selection) {
      this.settings.overrides.userPins.add(id);
      this.settings.overrides.userHides.delete(id);
    }
    this.refreshOverrides();
  }

  hideSelected(): void {
    for (const id of this.selection) {
      this.settings.overrides.userHides.add(id);
      this.settings.overrides.userPins.delete(id);
    }
    this.refreshOverrides();
  }

  clearPinsAndHides(): void {
    this.settings.overrides.userPins.clear();
    this.settings.overrides.userHides.clear();
    this.refreshOverrides();
  }

  /** Overrides changed (pins, hides, floors): recompute Algorithm 7 only. */
  refreshOverrides(): void {
    this.computeFloorsNow();
    this.needsApply = true;
    this.converged = false;
  }

  /** Settings that only change how the next frame is applied (far mode, smoothing rate). */
  touch(): void {
    this.needsApply = true;
    this.converged = false;
  }

  // ------------------------------------------------------------ Algorithm 1 + 7

  /** Elements whose alpha Algorithm 2 may change: Host + Near, plus Far under occluderScope 'all'. */
  private occluders(c: Classification = this.classification): Set<ElementId> {
    const out = new Set<ElementId>([...c.host, ...c.near]);
    if (scopeOf(this.settings.sightlines) === 'all') for (const id of c.far) out.add(id);
    return out;
  }

  /** Algorithm 1 (or 8 in tiers mode), then Algorithm 7. Sightline targets are stale afterwards. */
  reclassify(): void {
    const s = this.settings;
    const prevOcc = this.occluders();

    const t0 = performance.now();
    if (!s.xray) {
      this.tiered = null;
      this.classification = emptyClassification();
    } else if (s.tiersMode) {
      this.tiered = classifyTiers(this.model, this.geometry, this.selection, s.tiers, s.classification);
      this.classification = this.tiered.flat;
    } else {
      this.tiered = null;
      this.classification = classify(this.model, this.geometry, this.selection, s.classification);
    }
    const ms = performance.now() - t0;
    this.stats.classifyMs = ms;
    this.stats.classifyCount++;
    this.stats.classifyHistory.push(ms);
    const c = this.classification;
    this.stats.buckets = { focus: c.focus.size, host: c.host.size, near: c.near.size, far: c.far.size };

    // Former occluders that are no longer ghosted ease back to opaque instead of popping.
    const nowOcc = this.occluders(c);
    this.appliedScope = scopeOf(s.sightlines);
    for (const id of prevOcc) {
      if (!nowOcc.has(id)) {
        const a = this.fading.get(id) ?? this.state.alpha[id] ?? 1;
        if (a < this.capOf(id) - CONVERGED_EPS) this.fading.set(id, a);
      }
    }
    for (const id of nowOcc) this.fading.delete(id);

    this.result = { occlusion: new Map(), importance: new Map(), targetAlpha: new Map() };
    this.computeFloorsNow();
    this.needsApply = true;
    this.converged = false;
    this.plainApplied = false;
  }

  private computeFloorsNow(): void {
    const occ = this.occluders();
    this.floors = computeFloors(occ, this.model, this.settings.overrides, {
      styleFloor: (id) => this.styleIndex[id]?.floor,
    });
  }

  // ------------------------------------------------------------ Algorithm 2

  /**
   * occluderScope changed since the last classification (GUI): Far elements joining or leaving the
   * occluder set get floors, and Far ghosts easing out of the set fade back instead of popping.
   */
  private syncScope(): void {
    const scope = scopeOf(this.settings.sightlines);
    if (scope === this.appliedScope) return;
    this.appliedScope = scope;
    if (scope === 'near') {
      for (const id of this.classification.far) {
        const a = this.state.alpha[id] ?? 1;
        if (a < this.capOf(id) - CONVERGED_EPS) this.fading.set(id, a);
      }
    } else {
      for (const id of this.classification.far) this.fading.delete(id);
    }
    this.computeFloorsNow();
    this.needsApply = true;
    this.converged = false;
  }

  /** Algorithm 2 (or 9): sample focus surfaces, cast to the camera, store the target alphas. */
  updateSightlines(cameraPosition: Vector3): void {
    const s = this.settings;
    if (!s.xray) return;
    this.syncScope();
    if (this.needsApply) this.applyNow(); // hidden flags must be in place before ray casting
    this.rayCount = 0;
    const t0 = performance.now();
    if (this.classification.focus.size === 0) {
      this.result = { occlusion: new Map(), importance: new Map(), targetAlpha: new Map() };
    } else if (s.tiersMode && this.tiered) {
      const ts: TierSettings = { ...DEFAULT_TIER_SETTINGS, ...s.sightlines };
      this.result = sightlinesTiered(this.tiered, this.geometry, cameraPosition, ts, this.state);
    } else {
      this.result = sightlines(this.classification, this.geometry, cameraPosition, s.sightlines, this.state);
    }
    this.restyleTargets();
    const ms = performance.now() - t0;
    this.stats.sightlinesMs = ms;
    this.stats.rays = this.rayCount;
    this.stats.sightlinesCount++;
    this.stats.sightlinesHistory.push({ ms, rays: this.rayCount });
    this.converged = false;
  }

  // ------------------------------------------------------------ per frame

  /**
   * One animation frame of smoothing. Returns true when the render state changed (the caller
   * should mark the renderer dirty). Cheap no-op once every alpha is within 1e-3 of its target.
   */
  tick(): boolean {
    const s = this.settings;
    if (!s.xray) {
      if (this.plainApplied) return false;
      this.state.alpha.fill(1);
      for (let i = 0; i < this.state.flags.length; i++) this.state.flags[i] = (this.state.flags[i] ?? 0) & FLAG_SELECTED;
      this.fading.clear();
      this.applyStyles();
      this.plainApplied = true;
      this.converged = true;
      this.needsApply = false;
      return true;
    }
    this.plainApplied = false;
    this.syncScope();
    if (this.converged && !this.needsApply) return false;

    const c = this.classification;
    const alphas = smoothAlpha(this.state.alpha, this.targets, this.floors, s.sightlines, s.farMode, c);
    this.applyAlphas(alphas);
    this.needsApply = false;
    const farStepped = scopeOf(s.sightlines) === 'all' && s.farMode !== 'hidden';

    // Convergence check over the occluders.
    let done = this.fading.size === 0;
    if (done) {
      const check = (id: ElementId, dflt: number): void => {
        const floor = this.floors.get(id) ?? 0;
        if (floor === HIDDEN) return;
        const cap = this.capOf(id);
        const target = Math.min(cap, Math.max(this.targets.get(id) ?? dflt, floor));
        if (Math.abs(Math.min(cap, alphas.get(id) ?? 1) - target) > CONVERGED_EPS) done = false;
      };
      for (const id of c.host) if (done) check(id, s.sightlines.alphaMax);
      for (const id of c.near) if (done) check(id, s.sightlines.alphaMax);
      if (farStepped) for (const id of c.far) if (done) check(id, 1);
    }
    this.converged = done;
    return true;
  }

  /** Write flags and alphas without moving them (used before ray casting). */
  private applyNow(): void {
    const alphas = new Map<ElementId, number>();
    for (const id of this.occluders()) alphas.set(id, this.state.alpha[id] ?? 1);
    this.applyAlphas(alphas, false);
  }

  private applyAlphas(alphas: ReadonlyMap<ElementId, number>, stepFading = true): void {
    const s = this.settings;
    applyRenderState(this.state, this.classification, alphas, s.overrides, s.farMode);
    // Fade former occluders back to opaque (smoothAlpha/applyRenderState set them to 1).
    const k = s.sightlines.smoothingRate;
    for (const [id, a] of this.fading) {
      let next = a;
      if (stepFading) next = a + k * (1 - a);
      if (next >= this.capOf(id) - CONVERGED_EPS || this.classification.focus.has(id)) {
        this.fading.delete(id);
        continue;
      }
      this.fading.set(id, next);
      this.state.alpha[id] = next;
    }
    this.applyStyles();
    if (this.selection.size > 0) for (const id of this.selection) this.state.flags[id] = (this.state.flags[id] ?? 0) | FLAG_SELECTED;
  }

  /** Run `tick` until converged (for tests and benchmarks). Returns the number of ticks used. */
  settle(maxTicks = 500): number {
    let n = 0;
    while (n < maxTicks) {
      n++;
      this.tick();
      if (this.converged) break;
    }
    return n;
  }

  // ------------------------------------------------------------ introspection

  bucketOf(id: ElementId): Bucket {
    const c = this.classification;
    if (c.focus.has(id)) return 'focus';
    if (c.host.has(id)) return 'host';
    if (c.near.has(id)) return 'near';
    if (c.far.has(id)) return 'far';
    return 'none';
  }

  describe(id: ElementId): ElementInfo | null {
    const e = this.model.elements[id];
    if (!e) return null;
    return {
      id,
      ifcClass: e.ifcClass,
      name: e.name,
      bucket: this.bucketOf(id),
      proximityWeight: this.classification.proximityWeight.get(id) ?? 0,
      occlusion: this.result.occlusion.get(id) ?? 0,
      targetAlpha: this.result.targetAlpha.get(id) ?? (this.classification.far.has(id) ? 1 : this.settings.sightlines.alphaMax),
      alpha: this.state.alpha[id] ?? 1,
    };
  }
}
