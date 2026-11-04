// View modes plugin: behind-only views and partial peelback (per-fragment techniques in the renderer; see
// docs-features/view-modes.md). This file owns the settings, the lil-gui folder, the actions, the params section
// and the per-frame hand-over to the renderer (plane from camera and focus bounds, grow animation, occluder mask).

import type { AppPlugin, ViewerApp } from '../app';
import { registerAction } from '../input/actions';
import { registerParamSection } from '../ui/params';
import type { Plane } from '../viewModes/maths';
import { APPLY_TO, FRONT_TREATMENTS, PLANE_ORIENTATIONS, peelAnimScale, planeFromCamera, planeHorizontal } from '../viewModes/maths';
import type { Box6 } from '../viewModes/maths';
import { PEEL_OUTSIDE, cloneViewModes, defaultViewModes, mergeBehind, mergePeel } from '../viewModes/config';
import type { BehindConfig, PeelConfig, ViewModesConfig } from '../viewModes/config';
import { occluderMask } from '../viewModes/occluders';
import { Vector3 } from 'three';

export interface ViewModesApi {
  config: ViewModesConfig;
  setBehind(partial: Partial<BehindConfig>): string[];
  setPeel(partial: Partial<PeelConfig>): string[];
  /** Renderer-side state: which peel path ran, GPU status, how often the mask was rebuilt, the current plane. */
  status(): { peelPath: string; peelGpuStatus: string; peelRefreshes: number; plane: Plane | null; radiusScale: number };
}

declare global {
  interface Window {
    __xrayViewModes?: ViewModesApi;
  }
}

const config = defaultViewModes();

let appRef: ViewerApp | null = null;
let folderRoot: { controllersRecursive(): Array<{ updateDisplay(): unknown }> } | null = null;
let lockedPlane: Plane | null = null;
let lastPlane: Plane | null = null;
let focusSig = '';
let focusIds: number[] = [];
let focusBoxes: Box6[] = [];
let peelStart = -1e9;
let radiusScale = 1;
let maskKey = '';
let maskOn = false;
let loggedPath = '';
const fwd = new Vector3();

function refreshGui(): void {
  folderRoot?.controllersRecursive().forEach((c) => c.updateDisplay());
}

function restartPeelAnim(): void {
  peelStart = performance.now();
}

/** The focus set and its bounds, refreshed when the focus changed. */
function syncFocus(app: ViewerApp): void {
  const c = app.controller;
  if (!c || !app.loaded) {
    focusIds = [];
    focusBoxes = [];
    focusSig = '';
    return;
  }
  const f = c.classification.focus;
  let sig = `${app.modelName}:${f.size}`;
  let h = 0;
  for (const id of f) h = (h * 31 + id) % 1000003;
  sig += `:${h}`;
  if (sig === focusSig) return;
  focusSig = sig;
  focusIds = [...f];
  const els = app.loaded.model.elements;
  focusBoxes = focusIds.map((id) => els[id]!.bounds as Box6);
  lockedPlane = null; // a new focus: freeze the plane afresh
  maskKey = '';
  if (config.peel.enabled) restartPeelAnim();
}

function syncMask(app: ViewerApp): void {
  const want = config.behind.applyTo === 'occluders only' || config.peel.applyTo === 'occluders only';
  const c = app.controller;
  if (!want || !c || !app.loaded) {
    if (maskOn) {
      app.renderer.setViewModeMask(null);
      maskOn = false;
    }
    maskKey = '';
    return;
  }
  const key = `${focusSig}:${c.stats.sightlinesCount}:${c.stats.classifyCount}`;
  if (key === maskKey && maskOn) return;
  maskKey = key;
  maskOn = true;
  app.renderer.setViewModeMask(occluderMask(app.loaded.model.elements.length, c.classification, c.result.occlusion));
}

function behindPlane(app: ViewerApp, b: BehindConfig): Plane | null {
  if (focusBoxes.length === 0) return null;
  if (b.orientation === 'horizontal') return planeHorizontal(focusBoxes, b.offset);
  const cam = app.renderer.camera;
  if (b.orientation === 'locked' && lockedPlane) return lockedPlane;
  cam.getWorldDirection(fwd);
  const pl = planeFromCamera([fwd.x, fwd.y, fwd.z], focusBoxes, b.offset);
  if (b.orientation === 'locked') lockedPlane = pl;
  return pl;
}

function push(app: ViewerApp, now: number): void {
  const r = app.renderer;
  syncFocus(app);
  syncMask(app);
  const b = config.behind;
  const p = config.peel;
  if (b.enabled && focusBoxes.length > 0) {
    const plane = behindPlane(app, b);
    lastPlane = plane;
    if (plane) {
      r.setBehind({
        plane,
        treatment: b.frontTreatment,
        frontAlpha: b.frontAlpha,
        keepXray: b.keepXrayBehind,
        occludersOnly: b.applyTo === 'occluders only',
        capColour: b.capColour,
      });
    } else r.setBehind(null);
  } else {
    lastPlane = null;
    r.setBehind(null);
  }
  if (b.orientation !== 'locked') lockedPlane = null;
  if (p.enabled && focusIds.length > 0) {
    radiusScale = p.animate ? peelAnimScale(now - peelStart) : 1;
    r.setPeel({
      r0: p.radius * radiusScale,
      slope: p.slope,
      feather: p.feather,
      eps: p.depthEps,
      rim: p.rimBand,
      rimColour: p.rimColour,
      capColour: p.capColour,
      solidOutside: p.outside === 'solid',
      occludersOnly: p.applyTo === 'occluders only',
      focus: focusIds,
    });
    if (r.peelPath !== loggedPath) {
      loggedPath = r.peelPath;
      console.info(`[viewModes] peelback path: ${r.peelPath}${r.peelGpuStatus ? ` (${r.peelGpuStatus})` : ''}`);
    }
  } else {
    loggedPath = '';
    r.setPeel(null);
  }
}

const api: ViewModesApi = {
  config,
  setBehind(partial) {
    const wasOn = config.behind.enabled;
    const bad = mergeBehind(config.behind, partial);
    if (config.behind.orientation !== 'locked' || (!wasOn && config.behind.enabled)) lockedPlane = null;
    refreshGui();
    return bad;
  },
  setPeel(partial) {
    const wasOn = config.peel.enabled;
    const bad = mergePeel(config.peel, partial);
    if (!wasOn && config.peel.enabled) restartPeelAnim();
    refreshGui();
    return bad;
  },
  status() {
    const r = appRef?.renderer;
    return { peelPath: r?.peelPath ?? 'off', peelGpuStatus: r?.peelGpuStatus ?? '', peelRefreshes: r?.peelRefreshes ?? 0, plane: lastPlane, radiusScale };
  },
};

function toggleBehind(): void {
  api.setBehind({ enabled: !config.behind.enabled });
}

function togglePeel(): void {
  api.setPeel({ enabled: !config.peel.enabled });
}

function scaleRadius(k: number): void {
  api.setPeel({ radius: Math.min(10, Math.max(0.02, config.peel.radius * k)) });
}

export const viewModesPlugin: AppPlugin = {
  name: 'viewModes',

  install(app: ViewerApp): void {
    appRef = app;
    window.__xrayViewModes = api;

    registerAction({ id: 'mode.behind', label: 'Behind-only view', group: 'Modes', keys: ['b'], run: toggleBehind });
    registerAction({
      id: 'mode.behind.cycleTreatment',
      label: 'Behind-only: next front treatment',
      group: 'Modes',
      keys: ['Shift+b'],
      run: () => {
        const i = FRONT_TREATMENTS.indexOf(config.behind.frontTreatment);
        api.setBehind({ frontTreatment: FRONT_TREATMENTS[(i + 1) % FRONT_TREATMENTS.length]! });
      },
    });
    registerAction({ id: 'mode.peel', label: 'Partial peelback', group: 'Modes', keys: ['p'], run: togglePeel });
    registerAction({ id: 'mode.peel.grow', label: 'Peelback: grow window', group: 'Modes', keys: ['Alt+='], run: () => scaleRadius(1.25) });
    registerAction({ id: 'mode.peel.shrink', label: 'Peelback: shrink window', group: 'Modes', keys: ['Alt+-'], run: () => scaleRadius(0.8) });

    registerParamSection('viewModes', {
      share: true,
      collect: () => cloneViewModes(config),
      apply(value, bad, path) {
        if (value === null || typeof value !== 'object') {
          bad.push(path);
          return;
        }
        const v = value as Record<string, unknown>;
        const wasPeel = config.peel.enabled;
        bad.push(...mergeBehind(config.behind, v.behind, `${path}.behind`));
        bad.push(...mergePeel(config.peel, v.peel, `${path}.peel`));
        if (!wasPeel && config.peel.enabled) restartPeelAnim();
        lockedPlane = null;
        refreshGui();
      },
    });

    const gui = app.panel;
    if (!gui) return;
    const root = gui.addFolder('View modes');
    folderRoot = root;
    root.close();

    const b = config.behind;
    const fb = root.addFolder('Behind only');
    fb.add(b, 'enabled').name('enabled').onChange(() => {
      lockedPlane = null;
    });
    fb.add(b, 'frontTreatment', [...FRONT_TREATMENTS]).name('front treatment');
    fb.add(b, 'offset', -2, 3, 0.01).name('offset (m)');
    fb.add(b, 'frontAlpha', 0, 1, 0.01).name('front alpha');
    fb.add(b, 'orientation', [...PLANE_ORIENTATIONS]).name('orientation').onChange(() => {
      lockedPlane = null;
    });
    fb.add(b, 'applyTo', [...APPLY_TO]).name('apply to');
    fb.add(b, 'keepXrayBehind').name('keep x-ray behind');
    fb.addColor(b, 'capColour').name('cap colour');
    fb.close();

    const p = config.peel;
    const fp = root.addFolder('Peelback');
    fp.add(p, 'enabled').name('enabled').onChange((v: boolean) => {
      if (v) restartPeelAnim();
    });
    fp.add(p, 'radius', 0.05, 3, 0.01).name('radius (m)');
    fp.add(p, 'slope', 0, 3, 0.01).name('slope');
    fp.add(p, 'feather', 0, 0.5, 0.005).name('feather (m)');
    fp.add(p, 'rimBand').name('rim band');
    fp.addColor(p, 'rimColour').name('rim colour');
    fp.addColor(p, 'capColour').name('cap colour');
    fp.add(p, 'outside', [...PEEL_OUTSIDE]).name('outside');
    fp.add(p, 'applyTo', [...APPLY_TO]).name('apply to');
    fp.add(p, 'animate').name('animate');
    fp.close();
  },

  onModel(app: ViewerApp): void {
    focusSig = '';
    lockedPlane = null;
    maskKey = '';
    maskOn = false;
    app.renderer.setViewModeMask(null);
    if (config.peel.enabled) restartPeelAnim();
  },

  onStatic(app: ViewerApp): void {
    syncFocus(app);
  },

  onFrame(app: ViewerApp, now: number): boolean | void {
    if (!config.behind.enabled && !config.peel.enabled) {
      // Both off: leave the renderer exactly as it is without view modes (one cheap check per frame).
      if (lastPlane !== null || app.renderer.peelPath !== 'off') push(app, now);
      return;
    }
    push(app, now);
  },
};
