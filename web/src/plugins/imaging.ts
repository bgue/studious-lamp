// Imaging plugin: radiograph and MRI looks for the x-ray focus (see docs-features/imaging.md). The renderer does the
// drawing (renderer.setImaging); this file owns the settings, the lil-gui folder, the drawer, the actions, the params
// section, the MRI slab (from the focus bounds) and the scan animation.

import { Vector3 } from 'three';
import type { AppPlugin, ViewerApp } from '../app';
import { registerAction } from '../input/actions';
import { cloneImaging, defaultImaging, mergeImaging } from '../imaging/config';
import type { ImagingConfig } from '../imaging/config';
import { MRI_AXES, PALETTES, STYLES, advanceScan, phaseToPosition, positionToPhase, slabFor } from '../imaging/maths';
import type { Box6 } from '../imaging/maths';
import { registerTool } from '../tools/registry';
import { button, check, note, section, select, slider, statusLine } from '../tools/ui';
import type { Widget } from '../tools/ui';
import { registerParamSection } from '../ui/params';

export interface ImagingApi {
  config: ImagingConfig;
  /** Merge any subset of the settings; returns the dotted names it could not use. */
  set(partial: unknown): string[];
  /** Renderer-side state for tests: supported, status line, frames drawn through the imaging path, current slab. */
  status(): { supported: boolean; status: string; frames: number; slab: unknown; autoExposure: number; measures: number };
}

declare global {
  interface Window {
    __xrayImaging?: ImagingApi;
  }
}

const config = defaultImaging();
let appRef: ViewerApp | null = null;
let folderRoot: { controllersRecursive(): Array<{ updateDisplay(): unknown }> } | null = null;
let active = false;
let scanPhase = 0;
let scanWasOn = false;
let lastGuiRefresh = 0;
let lastSlab: unknown = null;
let focusSig = '';
let focusBoxes: Box6[] = [];
let modelBox: Box6[] = [];
const fwd = new Vector3();
const listeners = new Set<() => void>();

function refreshGui(): void {
  folderRoot?.controllersRecursive().forEach((c) => c.updateDisplay());
  for (const l of listeners) l();
}

/** Bounds of the focus set (the slab sweeps across them); the whole model when nothing is focused. */
function syncBounds(app: ViewerApp): void {
  const c = app.controller;
  if (!c || !app.loaded) {
    focusBoxes = [];
    modelBox = [];
    focusSig = '';
    return;
  }
  const f = c.classification.focus;
  let h = 0;
  for (const id of f) h = (h * 31 + id) % 1000003;
  const sig = `${app.modelName}:${f.size}:${h}`;
  if (sig === focusSig) return;
  focusSig = sig;
  const els = app.loaded.model.elements;
  focusBoxes = [...f].map((id) => els[id]!.bounds as Box6);
  if (focusBoxes.length === 0) {
    const b = app.loaded.geometry.totalBounds();
    modelBox = b.isEmpty() ? [] : [[b.min.x, b.min.y, b.min.z, b.max.x, b.max.y, b.max.z]];
  } else modelBox = [];
}

function push(app: ViewerApp, dt: number): void {
  const r = app.renderer;
  const c = config;
  if (c.style === 'standard') {
    if (active) {
      r.setImaging(null);
      active = false;
    }
    scanWasOn = false;
    return;
  }
  active = true;
  syncBounds(app);
  const m = c.mri;
  if (c.style === 'mri' && m.scan) {
    if (!scanWasOn) scanPhase = positionToPhase(m.position);
    scanWasOn = true;
    scanPhase = advanceScan(scanPhase, Math.min(dt, 250) / 1000, m.scanSpeed);
    m.position = phaseToPosition(scanPhase);
    const now = performance.now();
    if (now - lastGuiRefresh > 200) {
      lastGuiRefresh = now;
      refreshGui();
    }
  } else scanWasOn = false;
  let slab = null;
  if (c.style === 'mri') {
    r.camera.getWorldDirection(fwd);
    slab = slabFor(m.axis, [fwd.x, fwd.y, fwd.z], focusBoxes.length ? focusBoxes : modelBox, m.position, m.thickness);
    lastSlab = slab;
  }
  r.setImaging({
    style: c.style,
    palette: c.palette,
    exposure: c.exposure,
    autoExposure: c.autoExposure,
    contrast: c.contrast,
    boneGlow: c.boneGlow,
    tissueEdges: c.tissueEdges,
    slab,
    scan: m.scan,
  });
}

const api: ImagingApi = {
  config,
  set(partial) {
    const bad = mergeImaging(config, partial);
    refreshGui();
    return bad;
  },
  status() {
    const r = appRef?.renderer;
    return { supported: r?.imagingSupported ?? false, status: r?.imagingStatus ?? '', frames: r?.imagingFrames ?? 0, slab: lastSlab, autoExposure: r?.imagingAutoExposure ?? 1, measures: r?.imagingAutoMeasures ?? 0 };
  },
};

function cycle(): void {
  const i = STYLES.indexOf(config.style);
  api.set({ style: STYLES[(i + 1) % STYLES.length] });
}

const ICON =
  '<svg viewBox="0 0 20 20" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
  '<rect x="3" y="3" width="14" height="14" rx="2"/><path d="M8 6.5v7M12 6.5v7M6.5 8.5h7M6.5 11.5h7" stroke-width="1.3"/></svg>';

function drawer(box: HTMLElement): (() => void) | void {
  const widgets: Widget[] = [];
  const add = (w: Widget): void => {
    widgets.push(w);
    box.appendChild(w.root);
    w.update();
  };
  const f2 = (v: number): string => v.toFixed(2);
  box.appendChild(section('Style'));
  add(select('style', STYLES, () => config.style, (v) => api.set({ style: v })));
  add(select('palette', PALETTES, () => config.palette, (v) => api.set({ palette: v })));
  add(check('auto exposure', () => config.autoExposure, (v) => api.set({ autoExposure: v })));
  add(slider('exposure', 0.05, 4, 0.01, () => config.exposure, (v) => api.set({ exposure: v }), f2));
  add(slider('contrast', 0.2, 3, 0.01, () => config.contrast, (v) => api.set({ contrast: v }), f2));
  add(slider('bone glow', 0, 3, 0.01, () => config.boneGlow, (v) => api.set({ boneGlow: v }), f2));
  add(check('tissue edges', () => config.tissueEdges, (v) => api.set({ tissueEdges: v })));
  box.appendChild(section('MRI slice'));
  add(select('axis', MRI_AXES, () => config.mri.axis, (v) => api.set({ mri: { axis: v } })));
  add(slider('thickness (m)', 0.02, 3, 0.01, () => config.mri.thickness, (v) => api.set({ mri: { thickness: v } }), f2));
  add(slider('position', 0, 1, 0.005, () => config.mri.position, (v) => api.set({ mri: { position: v } }), f2));
  add(check('scan', () => config.mri.scan, (v) => api.set({ mri: { scan: v } })));
  add(slider('scan speed', 0.02, 1, 0.01, () => config.mri.scanSpeed, (v) => api.set({ mri: { scanSpeed: v } }), f2));
  const st = statusLine('');
  box.appendChild(st);
  box.appendChild(note('Radiograph: soft tissue by accumulated density x thickness, the focus as bright bone. Auto exposure fits the brightness to the model, the exposure slider then scales it. MRI: a crisp slice through the focus bounds with faint tissue around it. Key M cycles the style.'));
  box.appendChild(button('Standard view', () => api.set({ style: 'standard' }), { title: 'Back to the normal renderer' }));
  const upd = (): void => {
    widgets.forEach((w) => w.update());
    const s = api.status();
    st.set(s.supported ? s.status : `Imaging unavailable here: ${s.status}`);
  };
  listeners.add(upd);
  const t = setInterval(upd, 500);
  upd();
  return () => {
    clearInterval(t);
    listeners.delete(upd);
  };
}

export const imagingPlugin: AppPlugin = {
  name: 'imaging',

  install(app: ViewerApp): void {
    appRef = app;
    window.__xrayImaging = api;

    registerAction({ id: 'imaging.cycle', label: 'Imaging: next style (standard, radiograph, MRI)', group: 'Modes', keys: ['m'], run: cycle });

    registerTool({
      id: 'imaging',
      label: 'Imaging',
      title: 'Radiograph and MRI looks: bone focus inside soft tissue (M)',
      icon: ICON,
      order: 45,
      drawerWidth: 330,
      panel: (box) => drawer(box),
      toggle: (_a, on) => api.set({ style: on ? (config.style === 'standard' ? 'radiograph' : config.style) : 'standard' }),
      isActive: () => config.style !== 'standard',
    });

    registerParamSection('imaging', {
      share: true,
      collect: () => cloneImaging(config),
      apply(value, bad, path) {
        if (value === null || typeof value !== 'object') {
          bad.push(path);
          return;
        }
        bad.push(...mergeImaging(config, value, path));
        refreshGui();
      },
    });

    const gui = app.panel;
    if (!gui) return;
    const root = gui.addFolder('Imaging');
    folderRoot = root;
    root.close();
    root.add(config, 'style', [...STYLES]).name('style');
    root.add(config, 'palette', [...PALETTES]).name('palette');
    root.add(config, 'autoExposure').name('auto exposure');
    root.add(config, 'exposure', 0.05, 4, 0.01).name('exposure');
    root.add(config, 'contrast', 0.2, 3, 0.01).name('contrast');
    root.add(config, 'boneGlow', 0, 3, 0.01).name('bone glow');
    root.add(config, 'tissueEdges').name('tissue edges');
    const mri = root.addFolder('MRI slice');
    mri.close();
    mri.add(config.mri, 'axis', [...MRI_AXES]).name('axis');
    mri.add(config.mri, 'thickness', 0.02, 3, 0.01).name('thickness (m)');
    mri.add(config.mri, 'position', 0, 1, 0.005).name('position');
    mri.add(config.mri, 'scan').name('scan');
    mri.add(config.mri, 'scanSpeed', 0.02, 1, 0.01).name('scan speed');
  },

  onModel(): void {
    focusSig = '';
  },

  onStatic(): void {
    focusSig = '';
  },

  onFrame(app: ViewerApp, _now: number, dt: number): boolean | void {
    // Style standard and never switched on: leave the renderer alone (one comparison per frame).
    if (config.style === 'standard' && !active) return;
    push(app, dt);
  },
};
