// Top bar plugin: the 32 px strip along the top of #stage with the four visualisation modes (Ghost, Radiograph, Glow,
// Cutaway) and the host element #xray-topbar-search for the search bar. See src/ui/topBar.ts and docs-features/topbar.md.
//
//   window.__xrayTopBar = { modes(), active(), apply(id), setVisible(v), visible(), host }
//   actions: topbar.mode.ghost|radiograph|glow|cutaway (Shift+1..4), topbar.toggle (Shift+T)
//   params section `topBar` { visible } (default true; not in the share link, not in saved views, not in the presets hash)
//
// A mode applies a built-in preset through window.__xrayPresets. The highlight follows `__xrayPresets.active()`, which the
// presets engine clears when a setting changes, so a preset picked in the drawer, a restored saved view (markActive) or a
// key shows the right mode, and a changed setting clears it. The bar is hidden in a kiosk page (xray-pack --kiosk), in a
// WebXR session and with `topBar.visible: false`. It registers its rect with the overlay, so labels and pins avoid it.

import type { AppPlugin, ViewerApp } from '../app';
import { registerAction } from '../input/actions';
import { settingsHash } from '../presets/engine';
import { bootConfig } from '../tools/registry';
import { getOverlay } from '../ui/overlay';
import { registerParamSection } from '../ui/params';
import type { ParamsApp } from '../ui/params';
import { MODES, TOPBAR_H, TopBarView, barVisible, clickPlan, modeForPreset } from '../ui/topBar';
import type { ModeId } from '../ui/topBar';

export interface TopBarApi {
  modes(): Array<{ id: ModeId; label: string; presetId: string; key: string }>;
  /** The highlighted mode, or null. */
  active(): ModeId | null;
  /** Click a mode: apply its preset, or (when it is the active one) return to the normal view. False without a presets plugin. */
  apply(id: ModeId): boolean;
  /** The `topBar.visible` setting. The bar can still be hidden by a kiosk page or an XR session (see `shown()`). */
  setVisible(v: boolean): void;
  visible(): boolean;
  /** True while the bar is on screen. */
  shown(): boolean;
  /** The element the search bar mounts into. */
  host: HTMLElement | null;
}

declare global {
  interface Window {
    __xrayTopBar?: TopBarApi;
  }
}

interface PresetsLike {
  active(): string | null;
  apply(id: string): unknown;
  markActive?(id: string, note?: string): boolean;
}

const STORE_KEY = 'xray.topbar';
const state = { visible: true };
let view: TopBarView | null = null;
let factoryHash = '';
let first = true;
let gui: { updateDisplay(): unknown } | null = null;

const presets = (): PresetsLike | undefined => (window as unknown as { __xrayPresets?: PresetsLike }).__xrayPresets;

function readStored(): boolean | null {
  try {
    const v = JSON.parse(window.localStorage.getItem(STORE_KEY) ?? 'null') as { visible?: unknown } | null;
    return typeof v?.visible === 'boolean' ? v.visible : null;
  } catch {
    return null;
  }
}

function saveStored(): void {
  try {
    window.localStorage.setItem(STORE_KEY, JSON.stringify({ visible: state.visible }));
  } catch {
    /* ignore */
  }
}

function xrRunning(): boolean {
  const x = (window as unknown as { __xrayXr?: { manager?: { active?: boolean } | null } }).__xrayXr;
  return !!x?.manager?.active;
}

function shownNow(): boolean {
  const boot = bootConfig() as { kiosk?: boolean; topBar?: boolean };
  return barVisible({ visible: state.visible, kiosk: boot.kiosk === true, xr: xrRunning(), disabledByBoot: boot.topBar === false });
}

function currentMode(): ModeId | null {
  return modeForPreset(presets()?.active());
}

function sync(): void {
  if (!view) return;
  const show = shownNow();
  if (show !== view.visible) view.setVisible(show);
  view.setActive(currentMode());
}

function hashOf(app: ViewerApp): string {
  try {
    // Class styles and material aliases load from xray.config.json after the first model: they are data, not a look.
    return settingsHash(app as unknown as ParamsApp, {}, ['classStyles', 'materialAliases']);
  } catch {
    return '';
  }
}

function applyMode(id: ModeId): boolean {
  const p = presets();
  if (!p) return false;
  const plan = clickPlan(currentMode(), id);
  try {
    p.apply(plan.presetId);
  } catch (e) {
    console.warn(`[topbar] preset "${plan.presetId}" failed: ${e instanceof Error ? e.message : String(e)}`);
    return false;
  }
  sync();
  return true;
}

function setVisible(v: boolean): void {
  state.visible = v;
  saveStored();
  gui?.updateDisplay();
  sync();
}

const api: TopBarApi = {
  modes: () => MODES.map((m) => ({ id: m.id, label: m.label, presetId: m.presetId, key: m.keyLabel })),
  active: () => currentMode(),
  apply: applyMode,
  setVisible,
  visible: () => state.visible,
  shown: () => !!view?.visible,
  host: null,
};

export const topBarPlugin: AppPlugin = {
  name: 'topBar',

  install(app: ViewerApp): void {
    const stage = app.canvas.parentElement ?? document.body;
    state.visible = readStored() ?? true;
    view = new TopBarView(stage, { click: applyMode });
    api.host = view.searchHost;
    window.__xrayTopBar = api;
    view.setVisible(shownNow());
    view.setActive(null);

    registerParamSection('topBar', {
      collect: () => ({ visible: state.visible }),
      factory: () => ({ visible: true }),
      apply(value, bad, path) {
        if (value === null || typeof value !== 'object' || Array.isArray(value)) {
          bad.push(path);
          return;
        }
        for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
          if (k === 'visible' && typeof v === 'boolean') {
            state.visible = v;
            saveStored();
          } else bad.push(`${path}.${k}`);
        }
        gui?.updateDisplay();
        sync();
      },
    });

    for (const m of MODES) {
      registerAction({
        id: `topbar.mode.${m.id}`,
        label: `Top bar: ${m.label} mode`,
        group: 'Modes',
        keys: [m.key],
        description: `Apply the ${m.label} look (the ${m.presetId} preset). Press it again to return to the normal view.`,
        run: () => void applyMode(m.id),
      });
    }
    registerAction({
      id: 'topbar.toggle',
      label: 'Show or hide the top bar',
      group: 'Panels',
      keys: ['Shift+t'],
      description: 'Show or hide the strip with the visualisation modes and the search bar',
      run: () => setVisible(!state.visible),
    });

    // Reserve the bar's rect for labels and pins on the shared overlay (the overlay also counts it as a top inset).
    const ov = getOverlay(app);
    ov.reserve('topbar', () => {
      if (!view?.visible) return null;
      const r = view.root.getBoundingClientRect();
      const c = app.canvas.getBoundingClientRect();
      return r.width > 0 && r.height > 0 ? { x: r.left - c.left, y: r.top - c.top, w: r.width, h: Math.min(r.height, TOPBAR_H) } : null;
    });

    setInterval(sync, 250);
  },

  onModel(app: ViewerApp): void {
    if (!first) return;
    first = false;
    // The folder is made here, not in install(): topBar is the first plugin and its folder belongs at the end of the panel.
    const panel = app.panel;
    if (panel) {
      const f = panel.addFolder('Top bar');
      f.close();
      f.add(state, 'visible').name('Show top bar').onChange((v: boolean) => setVisible(v));
      gui = f.controllers[0] ?? null;
    }
    // The factory look is the Ghost mode (preset "coordination"): when nothing was changed after the first model, mark
    // it, so the bar shows the baseline. A boot preset, a #p= link or a boot params document changes the hash or the
    // active preset and so skips this.
    factoryHash = hashOf(app);
    setTimeout(() => {
      const p = presets();
      if (!p || p.active() || !factoryHash || hashOf(app) !== factoryHash) return;
      try {
        p.markActive?.('coordination', 'factory settings');
      } catch {
        /* a presets plugin without the mark */
      }
      sync();
    }, 1500);
  },

  onStatic(): void {
    sync();
  },
};
