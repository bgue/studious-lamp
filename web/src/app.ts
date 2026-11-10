// X-ray viewer: wires the loader, renderer, XrayController, lil-gui panel and the status bar (src/ui/statusBar.ts).
//   /?model=building|fzk-haus|plumbing|process-plant|synth5k|debris-demo|procedural

import GUI from 'lil-gui';
import { loadModel, parseModel } from './model/loader';
import type { LoadedModel } from './model/loader';
import { buildProceduralGlb, proceduralSidecar } from './model/procedural';
import { BvhGeometryProvider } from './render/geometry';
import { XrayRenderer } from './render/renderer';
import { XrayController, defaultSettings } from './controller';
import type { ControllerSettings, ControllerStats, ElementInfo } from './controller';
import type { Classification, ElementId } from './types';
import { PLUGINS } from './plugins';
import { registerAction } from './input/actions';
import { getKeymap } from './input/keymap';
import { bootConfig } from './tools/registry';
import { StatusBar } from './ui/statusBar';

/**
 * Extension point. A plugin owns its own module and DOM; it must not edit app.ts.
 * Hooks fire in registration order. All are optional.
 */
export interface AppPlugin {
  name: string;
  /** Once, after the GUI exists and before the first model loads. Add GUI folders and DOM here. */
  install?(app: ViewerApp): void;
  /** After every model install (controller, geometry and renderer state are fresh). */
  onModel?(app: ViewerApp): void;
  /** After the selection, classification or settings changed (Algorithm 1 has run). */
  onStatic?(app: ViewerApp): void;
  /**
   * First hook of every frame, before the controller tick and every onFrame. dt in ms. Runs also inside a WebXR session, where
   * the plugin moves the XR rig and brings the camera up to date for the hooks that follow (plugins/xr.ts).
   */
  beforeFrame?(app: ViewerApp, now: number, dt: number): void;
  /** Before the frame renders. dt in ms. Return true to force a render state upload. */
  onFrame?(app: ViewerApp, now: number, dt: number): boolean | void;
  /** After the frame rendered. */
  afterFrame?(app: ViewerApp, now: number): void;
}

export const MODEL_NAMES = ['building', 'fzk-haus', 'plumbing', 'process-plant', 'synth5k', 'debris-demo', 'procedural'] as const;

/** Model names offered in the picker: the built-in list plus any embedded models (single-file bundle). */
/** Models the user opened from a file picker or by drag and drop, in this session only. */
export const USER_MODELS = new Map<string, LoadedModel>();

export function availableModelNames(): string[] {
  const embedded = window.__xrayEmbeddedModels;
  // A single-file bundle cannot fetch /models/*, so offer only what it carries plus the procedural demo.
  const base = embedded ? [...Object.keys(embedded), 'procedural'] : [...MODEL_NAMES];
  return [...base, ...USER_MODELS.keys()];
}

function base64ToArrayBuffer(b64: string): ArrayBuffer {
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out.buffer;
}
export type ModelName = (typeof MODEL_NAMES)[number];

/** Minimum spacing of Algorithm 2 runs while the camera moves. */
export const SIGHTLINE_INTERVAL_MS = 50;
const FRAME_WINDOW = 60;

declare global {
  interface Window {
    __xray?: {
      app: ViewerApp;
      renderer: XrayRenderer;
      readonly classification: Classification;
      readonly stats: ControllerStats;
    };
    __xrayReady?: boolean;
    __xrayError?: string;
    /** Single-file bundles register models here: name -> { glb: base64 string, json: sidecar object }. */
    __xrayEmbeddedModels?: Record<string, { glb: string; json: unknown }>;
  }
}

export class ViewerApp {
  readonly canvas: HTMLCanvasElement;
  readonly renderer: XrayRenderer;
  readonly settings: ControllerSettings = defaultSettings();
  controller!: XrayController;
  loaded: LoadedModel | null = null;
  geometry: BvhGeometryProvider | null = null;
  modelName: string = 'building';
  hoverId: ElementId | null = null;

  /** Frame timing log, for the benchmark. */
  readonly frameLog = { intervals: [] as number[], cpu: [] as number[] };

  // Display parameters that live in the renderer rather than the controller.
  readonly display = { edgeAlpha: 0.8, ghostDesaturate: 0.8, inFront: true, debugBuckets: false };

  private gui: GUI | null = null;
  /** The thin status bar along the bottom of #stage (id xray-overlay); it also shows showMessage() as a red segment. */
  readonly status: StatusBar;
  private readonly floorParams = {
    pinFloor: this.settings.overrides.userPinFloor,
  };
  private loadToken = 0;
  private slTimer: ReturnType<typeof setTimeout> | null = null;
  private slLast = 0;
  private lastFrameTime = 0;
  private lastOverlay = 0;
  private recent: number[] = [];
  private recentCpu: number[] = [];
  private unsubscribeCamera: (() => void) | null = null;
  readonly plugins: AppPlugin[] = [];

  /** Register a plugin. Call before start(); plugins registered later get install() immediately. */
  use(plugin: AppPlugin): this {
    this.plugins.push(plugin);
    if (this.gui) plugin.install?.(this);
    return this;
  }

  /** The lil-gui root, for plugins that add folders. Null before start(). */
  get panel(): GUI | null {
    return this.gui;
  }

  /** The current selection as an array (plugins read; use selectIds to write). */
  get selection(): ElementId[] {
    return [...this.controller.selection];
  }

  constructor(canvas: HTMLCanvasElement) {
    this.canvas = canvas;
    this.renderer = new XrayRenderer(canvas);
    // Inside #stage, so the bar follows the sidebar, the dock and the phone layout (index.html). A page without #stage
    // (a test harness) gets it on the body.
    const stage = document.getElementById('stage') ?? canvas.parentElement ?? document.body;
    this.status = new StatusBar(stage);
  }

  /** Show a message as the red segment of the status bar (with a dismiss button); null clears it. */
  showMessage(text: string | null): void {
    this.status.setMessage(text);
  }

  // ---------------------------------------------------------------- loading

  async start(initialModel: string): Promise<void> {
    this.buildGui();
    this.bindInput();
    for (const p of this.plugins) p.install?.(this);
    await this.loadScene(initialModel);
    this.lastFrameTime = performance.now();
    this.renderer.render();
    this.renderer.renderer.getContext().finish();
    window.__xrayReady = true;
    // three's animation loop: window.requestAnimationFrame outside an XR session, the session's own inside one.
    this.renderer.renderer.setAnimationLoop(this.frame);
  }

  /** Load a model by name. Falls back to the procedural model with a visible message on failure. */
  async loadScene(name: string): Promise<void> {
    const token = ++this.loadToken;
    this.showMessage(`Loading ${name}...`);
    let loaded: LoadedModel;
    let used = name;
    try {
      const embedded = window.__xrayEmbeddedModels?.[name];
      const user = USER_MODELS.get(name);
      if (user) loaded = user;
      else if (name === 'procedural') loaded = await parseModel(buildProceduralGlb(), proceduralSidecar());
      else if (embedded) loaded = await parseModel(base64ToArrayBuffer(embedded.glb), embedded.json as Parameters<typeof parseModel>[1]);
      else loaded = await loadModel(`/models/${name}.glb`, `/models/${name}.json`);
      this.showMessage(null);
    } catch (e) {
      const why = e instanceof Error ? e.message : String(e);
      console.error(e);
      loaded = await parseModel(buildProceduralGlb(), proceduralSidecar());
      used = 'procedural';
      this.showMessage(`Could not load model "${name}" (${why}). Showing the procedural demo model.`);
    }
    if (token !== this.loadToken) return;
    this.installModel(loaded, used);
  }

  /**
   * Install a model the user opened from a file (see plugins/fileLoader.ts). The model is kept in
   * USER_MODELS for the session, added to the model picker, and its settings are stored under `name`.
   */
  openLoaded(loaded: LoadedModel, name: string): void {
    USER_MODELS.set(name, loaded);
    this.rebuildModelPicker();
    this.installModel(loaded, name);
  }

  private rebuildModelPicker(): void {
    const ctrl = this.gui?.controllers.find((c) => c.property === 'model');
    if (!ctrl) return;
    const names = availableModelNames();
    const opts = ctrl as unknown as { options?: (values: string[]) => unknown };
    opts.options?.(names);
  }

  private installModel(loaded: LoadedModel, name: string): void {
    this.loaded = loaded;
    this.modelName = name;
    this.renderer.setModel(loaded);
    this.geometry = new BvhGeometryProvider(loaded.geometry);
    // Same settings object across models, so the GUI stays bound.
    this.settings.overrides.userPins.clear();
    this.settings.overrides.userHides.clear();
    this.controller = new XrayController(loaded.model, this.geometry, this.renderer.state, this.settings);
    this.renderer.setEdgeAlpha(this.display.edgeAlpha);
    this.renderer.setGhostDesaturate(this.display.ghostDesaturate);
    this.renderer.setInFront(this.display.inFront);
    this.unsubscribeCamera?.();
    this.unsubscribeCamera = this.renderer.onCameraChange(() => this.scheduleSightlines());
    this.hoverId = null;
    this.renderer.resize();
    this.renderer.markDirty();
    // A model opened from a file cannot be reloaded from a URL, so keep the address bar on the last named model.
    if (!USER_MODELS.has(name)) {
      const p = new URL(location.href);
      p.searchParams.set('model', name);
      history.replaceState(null, '', p);
    }
    if (this.guiModel) this.guiModel.model = name;
    this.gui?.controllersRecursive().forEach((c) => c.updateDisplay());
    for (const p of this.plugins) p.onModel?.(this);
  }

  /** Stats record (owned by the current controller; frame timings are written into it). */
  get stats(): ControllerStats {
    return this.controller.stats;
  }

  // ---------------------------------------------------------------- actions

  /** Replace the selection (or add to it) and rerun Algorithms 1, 7 and 2. */
  selectIds(ids: ElementId[], additive = false): void {
    if (additive) this.controller.addToSelection(ids);
    else this.controller.setSelection(ids);
    this.afterStatic();
  }

  clearSelection(): void {
    this.controller.clearSelection();
    this.afterStatic();
  }

  /** Re-run Algorithm 1 and 2 with the current settings (after a settings change). */
  reclassify(): void {
    this.controller.reclassify();
    this.afterStatic();
  }

  private afterStatic(): void {
    if (this.display.debugBuckets) this.applyDebugColors();
    this.runSightlinesNow();
    for (const p of this.plugins) p.onStatic?.(this);
  }

  /** Cold-cache Algorithm 1 timing support. */
  clearGeometryCaches(): void {
    this.geometry?.clearCaches();
  }

  setXray(on: boolean): void {
    this.settings.xray = on;
    this.reclassify();
    this.gui?.controllersRecursive().forEach((c) => c.updateDisplay());
  }

  frameAll(): void {
    this.renderer.frameAll();
    this.runSightlinesNow();
  }

  pinSelected(): void {
    this.controller.pinSelected();
    this.runSightlinesNow();
  }

  hideSelected(): void {
    this.controller.hideSelected();
    this.runSightlinesNow();
  }

  clearPinsAndHides(): void {
    this.controller.clearPinsAndHides();
    this.runSightlinesNow();
  }

  /** Algorithm 2 now, for the current camera. */
  runSightlinesNow(): void {
    if (this.slTimer) {
      clearTimeout(this.slTimer);
      this.slTimer = null;
    }
    this.slLast = performance.now();
    // The camera's world position: the orbit camera itself, or the head inside a WebXR session (the camera then sits in a rig).
    this.controller.updateSightlines(this.renderer.cameraWorldPosition());
  }

  /** Camera moved: run Algorithm 2 at most once per SIGHTLINE_INTERVAL_MS, plus once after the last move. */
  private scheduleSightlines(): void {
    if (this.slTimer) return;
    const wait = Math.max(0, SIGHTLINE_INTERVAL_MS - (performance.now() - this.slLast));
    this.slTimer = setTimeout(() => {
      this.slTimer = null;
      this.runSightlinesNow();
    }, wait);
  }

  private applyDebugColors(): void {
    if (this.display.debugBuckets) this.renderer.debugColorByBucket(this.controller.classification);
    else this.renderer.resetColors();
  }

  // ---------------------------------------------------------------- frame loop

  private frame = (now: number): void => {
    const t0 = performance.now();
    const dt = now - this.lastFrameTime;
    this.lastFrameTime = now;
    for (const p of this.plugins) p.beforeFrame?.(this, now, dt);
    let dirty = this.controller.tick();
    for (const p of this.plugins) if (p.onFrame?.(this, now, dt)) dirty = true;
    if (dirty) this.renderer.markDirty();
    this.renderer.render();
    for (const p of this.plugins) p.afterFrame?.(this, now);
    const cpu = performance.now() - t0;

    if (dt > 0 && dt < 5000) {
      this.recent.push(dt);
      this.recentCpu.push(cpu);
      if (this.recent.length > FRAME_WINDOW) this.recent.shift();
      if (this.recentCpu.length > FRAME_WINDOW) this.recentCpu.shift();
      if (this.frameLog.intervals.length < 20000) {
        this.frameLog.intervals.push(dt);
        this.frameLog.cpu.push(cpu);
      }
      const mean = (a: number[]): number => a.reduce((x, y) => x + y, 0) / a.length;
      this.stats.frameMs = mean(this.recent);
      this.stats.frameCpuMs = mean(this.recentCpu);
    }
    if (now - this.lastOverlay > 250) {
      this.lastOverlay = now;
      this.updateOverlay();
    }
  };

  private updateOverlay(): void {
    const c = this.controller;
    const s = c.stats;
    const id = this.hoverId ?? (c.selection.size > 0 ? c.selection.values().next().value! : null);
    const info: ElementInfo | null = id === null ? null : c.describe(id);
    this.status.update({
      model: this.modelName,
      elements: s.elements,
      xray: c.settings.xray,
      tiers: c.settings.tiersMode,
      buckets: s.buckets,
      element: info ? { ...info, name: info.name ?? null, hovered: this.hoverId !== null } : null,
      classifyMs: s.classifyMs,
      sightlinesMs: s.sightlinesMs,
      rays: s.rays,
      frameMs: s.frameMs,
      frameCpuMs: s.frameCpuMs,
      frames: this.recent.length,
    });
  }

  // ---------------------------------------------------------------- input

  private bindInput(): void {
    const canvas = this.canvas;
    let down: { x: number; y: number; t: number } | null = null;
    canvas.addEventListener('pointerdown', (e) => {
      down = { x: e.clientX, y: e.clientY, t: performance.now() };
    });
    canvas.addEventListener('pointerup', (e) => {
      if (!down || e.button !== 0) return;
      const moved = Math.hypot(e.clientX - down.x, e.clientY - down.y);
      down = null;
      if (moved > 5) return;
      const id = this.pickAt(e.clientX, e.clientY);
      if (id === null) {
        if (!e.shiftKey) this.clearSelection();
      } else {
        this.selectIds([id], e.shiftKey);
      }
    });
    let lastHover = 0;
    canvas.addEventListener('pointermove', (e) => {
      if (e.buttons !== 0) return;
      const now = performance.now();
      if (now - lastHover < 80) return;
      lastHover = now;
      this.hoverId = this.pickAt(e.clientX, e.clientY);
    });
    canvas.addEventListener('pointerleave', () => {
      this.hoverId = null;
    });
    window.addEventListener('resize', () => this.renderer.resize());
    // Keys go through the action registry (src/input/actions.ts); the keymap plugin owns dispatch, rebinding and
    // the navigation actions. These are the viewer's own base actions; plugins/keymap.ts refines `view.frame`.
    registerAction({ id: 'xray.toggle', label: 'Toggle x-ray', group: 'Visibility', keys: ['x'], run: (app) => app.setXray(!app.settings.xray) });
    registerAction({ id: 'view.frame', label: 'Frame all', group: 'Views', keys: ['f'], run: (app) => app.frameAll() });
    registerAction({
      id: 'select.clear',
      label: 'Clear selection',
      group: 'Selection',
      keys: ['Escape'],
      run: (app) => {
        if (getKeymap()?.closeOverlays()) return;
        app.clearSelection();
      },
    });
  }

  private pickAt(clientX: number, clientY: number): ElementId | null {
    const r = this.canvas.getBoundingClientRect();
    const x = ((clientX - r.left) / r.width) * 2 - 1;
    const y = -((clientY - r.top) / r.height) * 2 + 1;
    return this.renderer.pick(x, y);
  }

  // ---------------------------------------------------------------- GUI

  private guiModel: { model: string } | null = null;

  private buildGui(): void {
    const gui = new GUI({ title: 'X-ray' });
    this.gui = gui;
    const s = this.settings;
    const re = (): void => this.reclassify();
    const sl = (): void => this.runSightlinesNow();
    const touch = (): void => this.controller.touch();

    this.guiModel = { model: this.modelName };
    gui.add(this.guiModel, 'model', availableModelNames()).name('Model').onChange((v: string) => void this.loadScene(v));
    gui.add(s, 'xray').name('X-ray (X)').onChange(() => this.setXray(s.xray));
    gui.add(s, 'tiersMode').name('Tiers mode').onChange(re);

    const fc = gui.addFolder('Classification (Alg 1)');
    fc.add(s.classification, 'bufferBase', 0, 2, 0.01).name('bufferBase (m)').onChange(re);
    fc.add(s.classification, 'bufferScale', 0, 2, 0.01).onChange(re);
    fc.add(s.classification, 'bufferLo', 0, 2, 0.01).name('bufferLo (m)').onChange(re);
    fc.add(s.classification, 'bufferHi', 0, 5, 0.01).name('bufferHi (m)').onChange(re);
    fc.add(s.classification, 'storeyBand', 0, 5, 1).onChange(re);

    const fs = gui.addFolder('Sightlines (Alg 2)');
    fs.add(s.sightlines, 'samplesPerObject', 1, 256, 1).onChange(sl);
    fs.add(s.sightlines, 'maxSamples', 10, 2000, 10).onChange(sl);
    fs.add(s.sightlines, 'alphaMin', 0, 1, 0.01).onChange(sl);
    fs.add(s.sightlines, 'alphaMax', 0, 1, 0.01).onChange(sl);
    fs.add(s.sightlines, 'gamma', 0.1, 3, 0.01).onChange(sl);
    fs.add(s.sightlines, 'occluderScope', ['all', 'near']).name('occluder scope').onChange(sl);
    fs.add(s.sightlines, 'farWeight', 0, 1, 0.01).name('far weight').onChange(sl);
    fs.add(s.sightlines, 'layerWeighting', ['front', 'budget', 'uniform']).name('layer weighting').onChange(sl);
    fs.add(s.sightlines, 'layerFalloff', 0.1, 1, 0.01).name('layer falloff').onChange(sl);
    fs.add(s.sightlines, 'layerBudget', 1, 6, 1).name('layer budget').onChange(sl);
    fs.add(s.sightlines, 'smoothingRate', 0.01, 1, 0.01).onChange(touch);

    const fd = gui.addFolder('Display');
    fd.add(this.display, 'edgeAlpha', 0, 1, 0.01).onChange((v: number) => this.renderer.setEdgeAlpha(v));
    fd.add(this.display, 'ghostDesaturate', 0, 1, 0.01).name('ghost desaturate').onChange((v: number) => this.renderer.setGhostDesaturate(v));
    fd.add(this.display, 'inFront').name('focus in front').onChange((v: boolean) => this.renderer.setInFront(v));
    fd.add(s, 'farMode', ['opaque', 'hidden']).name('far mode').onChange(touch);
    fd.add(this.display, 'debugBuckets').name('debug colour by bucket').onChange(() => this.applyDebugColors());

    const fo = gui.addFolder('Overrides (Alg 7)');
    fo.add(this.floorParams, 'pinFloor', 0, 1, 0.01).name('user pin floor').onChange((v: number) => {
      s.overrides.userPinFloor = v;
      this.controller.refreshOverrides();
    });
    // Per-class floors live in the Class styles panel (plugins/classStyles.ts).

    const actions = {
      pin: () => this.pinSelected(),
      hide: () => this.hideSelected(),
      clear: () => this.clearPinsAndHides(),
      frame: () => this.frameAll(),
    };
    gui.add(actions, 'pin').name('Pin selected');
    gui.add(actions, 'hide').name('Hide selected');
    gui.add(actions, 'clear').name('Clear pins/hides');
    gui.add(actions, 'frame').name('Frame all (F)');
  }
}

async function main(): Promise<void> {
  const params = new URLSearchParams(location.search);
  // Initial model: a packaged page's boot model, else ?model=, else the first embedded model, else 'building'.
  const embedded = window.__xrayEmbeddedModels ? Object.keys(window.__xrayEmbeddedModels) : [];
  const name = bootConfig().model ?? params.get('model') ?? embedded[0] ?? 'building';
  const canvas = document.getElementById('c') as HTMLCanvasElement;
  const app = new ViewerApp(canvas);
  for (const p of PLUGINS) app.use(p);
  window.__xray = {
    app,
    renderer: app.renderer,
    get classification() {
      return app.controller.classification;
    },
    get stats() {
      return app.stats;
    },
  };
  await app.start(name);
}

main().catch((e: unknown) => {
  window.__xrayError = String(e instanceof Error ? e.stack ?? e.message : e);
  console.error(window.__xrayError);
  const d = document.createElement('div');
  d.style.cssText = 'position:fixed;left:10px;top:10px;padding:8px;background:#7a2b1f;color:#fff;font:13px sans-serif';
  d.textContent = `Startup failed: ${window.__xrayError.split('\n')[0]}`;
  document.body.appendChild(d);
});
