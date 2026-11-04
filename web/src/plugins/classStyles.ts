// Class styles plugin: loads /xray.config.json, merges the sidecar styles and the user's runtime
// edits, hands the result to the controller and exposes a lil-gui folder to edit them.
//
// Precedence (lowest to highest): xray.config.json < model sidecar `styles` < runtime edits
// (stored per model in localStorage under `xray.classStyles.<modelName>`).

import type GUI from 'lil-gui';
import type { AppPlugin, ViewerApp } from '../app';
import type { ClassStyle, ClassStyles } from '../types';
import {
  aliasMatches,
  mergeAliases,
  mergeStyles,
  parseConfig,
  toConfig,
  type MaterialAliases,
} from '../styles';

const CONFIG_URL = '/xray.config.json';
const STORAGE_PREFIX = 'xray.classStyles.';

interface Edits {
  classStyles: ClassStyles;
  materialAliases: MaterialAliases;
}

let configStyles: ClassStyles = {};
let configAliases: MaterialAliases = {};
let configReady: Promise<void> = Promise.resolve();
let configDone = false;

let folder: GUI | null = null;
let keysFolder: GUI | null = null;
let fileInput: HTMLInputElement | null = null;
let edits: Edits = { classStyles: {}, materialAliases: {} };

const storageKey = (app: ViewerApp): string => STORAGE_PREFIX + app.modelName;

function loadEdits(app: ViewerApp): Edits {
  try {
    const raw = localStorage.getItem(storageKey(app));
    if (raw) {
      const c = parseConfig(JSON.parse(raw));
      return { classStyles: c.classStyles, materialAliases: c.materialAliases };
    }
  } catch {
    /* unavailable or corrupt: start clean */
  }
  return { classStyles: {}, materialAliases: {} };
}

function saveEdits(app: ViewerApp): void {
  try {
    const empty = Object.keys(edits.classStyles).length === 0 && Object.keys(edits.materialAliases).length === 0;
    if (empty) localStorage.removeItem(storageKey(app));
    else localStorage.setItem(storageKey(app), JSON.stringify(toConfig(edits.classStyles, edits.materialAliases)));
  } catch {
    /* quota or privacy mode: edits stay in memory */
  }
}

/** The sidecar layer of the current model. */
function sidecar(app: ViewerApp): Edits {
  const m = app.controller.model;
  return { classStyles: parseConfig({ classStyles: m.styles }).classStyles, materialAliases: parseConfig({ materialAliases: m.materialAliases }).materialAliases };
}

function effective(app: ViewerApp): { styles: ClassStyles; aliases: MaterialAliases } {
  const side = sidecar(app);
  return {
    styles: mergeStyles(configStyles, side.classStyles, edits.classStyles),
    aliases: mergeAliases(configAliases, side.materialAliases, edits.materialAliases),
  };
}

/** Push the effective styles into the controller and re-run Algorithms 1, 7 and 2. */
function apply(app: ViewerApp, persist: boolean): void {
  const { styles, aliases } = effective(app);
  app.controller.setClassStyles(styles, aliases);
  app.reclassify();
  if (persist) saveEdits(app);
}

const to255 = (v: number): number => Math.round(Math.min(1, Math.max(0, v)) * 255);
export const rgbToHex = (c: readonly number[]): string =>
  '#' + [0, 1, 2].map((i) => to255(c[i] ?? 0).toString(16).padStart(2, '0')).join('');
export function hexToRgb(hex: string): [number, number, number] {
  const h = hex.replace('#', '');
  return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16) / 255) as [number, number, number];
}

function setField<K extends keyof ClassStyle>(app: ViewerApp, key: string, field: K, value: ClassStyle[K]): void {
  edits.classStyles[key] = { ...(edits.classStyles[key] ?? {}), [field]: value };
  apply(app, true);
}

function download(name: string, text: string): void {
  const url = URL.createObjectURL(new Blob([text], { type: 'application/json' }));
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function buildKeys(app: ViewerApp): void {
  if (!keysFolder) return;
  for (const f of [...keysFolder.folders]) f.destroy();
  const ctl = app.controller;
  const els = ctl.model.elements;
  const { styles, aliases } = effective(app);
  const defaults = app.settings.sightlines;

  for (const { key, count, kind } of ctl.styleKeys()) {
    const cur: ClassStyle = styles[key] ?? {};
    const sample = els.find((e) => (kind === 'class' ? e.ifcClass === key : aliasMatches(aliases[key] ?? [], e)));
    const obj = {
      alphaMax: cur.alphaMax ?? 1,
      alphaMin: cur.alphaMin ?? defaults.alphaMin,
      floor: cur.floor ?? 0,
      hidden: cur.hidden ?? false,
      color: rgbToHex(cur.color ?? sample?.color ?? [0.7, 0.7, 0.7]),
      reset: () => {
        delete edits.classStyles[key];
        apply(app, true);
        buildKeys(app);
      },
    };
    const f = keysFolder.addFolder(`${key} (${count})${kind === 'alias' ? ' [alias]' : ''}`);
    f.close();
    f.add(obj, 'alphaMax', 0, 1, 0.01).name('alpha max').onChange((v: number) => setField(app, key, 'alphaMax', v));
    f.add(obj, 'alphaMin', 0, 1, 0.01).name('alpha min').onChange((v: number) => setField(app, key, 'alphaMin', v));
    f.add(obj, 'floor', 0, 1, 0.01).onChange((v: number) => setField(app, key, 'floor', v));
    f.add(obj, 'hidden').onChange((v: boolean) => setField(app, key, 'hidden', v));
    f.addColor(obj, 'color').onChange((v: string) => setField(app, key, 'color', hexToRgb(v)));
    f.add(obj, 'reset').name('Reset this class');
  }
}

export const classStylesPlugin: AppPlugin = {
  name: 'classStyles',

  install(app) {
    // Single-file bundle: tools/build-single-file.mjs injects the config as window.__xrayEmbeddedConfig (no fetch).
    const embedded = (window as unknown as { __xrayEmbeddedConfig?: unknown }).__xrayEmbeddedConfig;
    configReady = (embedded ? Promise.resolve(embedded) : fetch(CONFIG_URL).then((r) => (r.ok ? r.json() : null)))
      .then((j: unknown) => {
        if (!j) return;
        const c = parseConfig(j);
        configStyles = c.classStyles;
        configAliases = c.materialAliases;
      })
      .catch(() => undefined)
      .finally(() => {
        configDone = true;
      });

    const panel = app.panel;
    if (!panel) return;
    folder = panel.addFolder('Class styles');
    folder.close();
    keysFolder = folder.addFolder('Classes');
    const actions = {
      reset: () => {
        edits = { classStyles: {}, materialAliases: {} };
        apply(app, true);
        buildKeys(app);
      },
      export: () => {
        const { styles, aliases } = effective(app);
        download('xray.config.json', JSON.stringify(toConfig(styles, aliases), null, 2) + '\n');
      },
      import: () => fileInput?.click(),
    };
    folder.add(actions, 'reset').name('Reset to config');
    folder.add(actions, 'export').name('Export JSON');
    folder.add(actions, 'import').name('Import JSON');

    fileInput = document.createElement('input');
    fileInput.type = 'file';
    fileInput.accept = 'application/json,.json';
    fileInput.style.display = 'none';
    fileInput.addEventListener('change', () => {
      const file = fileInput?.files?.[0];
      if (!file) return;
      void file.text().then((text) => {
        try {
          const c = parseConfig(JSON.parse(text));
          // An import is a runtime edit layer: it wins over the config file and the sidecar.
          edits = { classStyles: c.classStyles, materialAliases: c.materialAliases };
          apply(app, true);
          buildKeys(app);
        } catch (e) {
          app.showMessage(`Import failed: ${e instanceof Error ? e.message : String(e)}`);
          setTimeout(() => app.showMessage(null), 4000);
        }
      });
      if (fileInput) fileInput.value = '';
    });
    document.body.appendChild(fileInput);
  },

  onModel(app) {
    edits = loadEdits(app);
    const run = (): void => {
      apply(app, false);
      buildKeys(app);
    };
    if (configDone) run();
    else {
      const name = app.modelName;
      const ctl = app.controller;
      void configReady.then(() => {
        if (app.controller === ctl && app.modelName === name) run();
      });
    }
  },
};
