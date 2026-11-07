// Presets plugin: named looks of the viewer (partial xray-params/1 documents). Owns
//   - the `presets` tool in the action panel (drawer of preset cards),
//   - the lil-gui folder `Presets`,
//   - actions preset.1 to preset.9 (the first nine presets) and presets.open,
//   - window.__xrayPresets = { list, apply, save, remove, active, ... } (the CLI packager calls apply(nameOrId)),
//   - the user presets in localStorage 'xray.presets' and the share link `#preset=<base64url>`.
// The data model is in src/presets/model.ts, applying and capturing in engine.ts, the list in store.ts.
// See docs-features/presets.md.

import type { AppPlugin, ViewerApp } from '../app';
import { registerAction } from '../input/actions';
import { DEFAULT_CAPTURE, applyPreset, capturePreset, captureSections, settingsHash } from '../presets/engine';
import type { ApplyResult, EngineEnv } from '../presets/engine';
import { findPreset, hashWithoutPreset, keyOf, parsePresetsDocument, presetFromHash, presetShareUrl } from '../presets/model';
import type { Preset } from '../presets/model';
import { presetsPanel } from '../presets/panel';
import type { PanelHost } from '../presets/panel';
import { PresetStore } from '../presets/store';
import { registerTool } from '../tools/registry';
import { copyText } from '../ui/dom';
import { collectParams, paramSectionNames } from '../ui/params';
import type { ParamsApp } from '../ui/params';
import { boxFromTuple, requestFrame } from '../ui/fit';
import { Box3 } from 'three';

export interface PresetSummary {
  id: string;
  name: string;
  description: string;
  group: string;
  /** '1' to '9', or null. */
  key: string | null;
  builtIn: boolean;
  base: Preset['base'];
  active: boolean;
}

export interface PresetsApi {
  list(): PresetSummary[];
  /** Apply by id, name (case-insensitive) or key number. Throws for an unknown preset. */
  apply(idOrName: string): ApplyResult;
  /** Save the named sections of the current state as a user preset. Sections this build does not have are listed in `missing`. */
  save(name: string, sections?: string[], description?: string): { preset: Preset; missing: string[] };
  remove(id: string): boolean;
  /** Id of the last applied preset, or null when none was applied or a setting changed since. */
  active(): string | null;
  /**
   * Mark a preset as the active one without applying it: a saved view that was taken with that preset active has
   * just put its settings back (src/plugins/views.ts). False for an unknown id. A later setting change clears the mark.
   */
  markActive(id: string, note?: string): boolean;
  lastResult(): ApplyResult | null;
  get(id: string): Preset | undefined;
  exportJson(all?: boolean): string;
  importJson(text: string): { added: string[]; errors: string[] };
  shareUrl(id: string): string | null;
}

declare global {
  interface Window {
    __xrayPresets?: PresetsApi;
    /** The build-time override: an `xray-presets/1` document embedded by tools/build-single-file.mjs. */
    __xrayEmbeddedPresets?: unknown;
  }
}

const ICON =
  '<svg viewBox="0 0 20 20" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
  '<path d="M3 5.5h8M14 5.5h3M3 10h3M9 10h8M3 14.5h9M15 14.5h2"/><circle cx="12.5" cy="5.5" r="1.5"/><circle cx="7.5" cy="10" r="1.5"/><circle cx="13.5" cy="14.5" r="1.5"/></svg>';

function localStore(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

let store: PresetStore | null = null;
let appRef: ViewerApp | null = null;
let activeId: string | null = null;
let lastResult: ApplyResult | null = null;
let activeHash = '';
let baselinePending = false;
let saveRequested = false;
let factory: Map<string, unknown> | null = null;
let pendingShare: Preset | null = null;
let msgTimer: ReturnType<typeof setTimeout> | null = null;
const listeners = new Set<() => void>();
let guiState = { preset: '', status: 'No preset applied' };
let guiRefresh: (() => void) | null = null;
let fileInput: HTMLInputElement | null = null;
let offKeyed: Array<() => void> = [];

const notifyAll = (): void => {
  for (const l of listeners) l();
  guiRefresh?.();
};

function notify(app: ViewerApp, text: string, ms = 5000): void {
  app.showMessage(text);
  if (msgTimer) clearTimeout(msgTimer);
  msgTimer = setTimeout(() => app.showMessage(null), ms);
}

function env(): EngineEnv {
  return { factory: (s) => factory?.get(s), frameSelection: () => (appRef ? frameSelection(appRef) : false) };
}

/** Preset `frame: 'selection'`: fit the camera to the bounds of the selection (the cinematic fly-to animates it). */
function frameSelection(app: ViewerApp): boolean {
  const els = app.loaded?.model.elements;
  if (!els) return false;
  const box = new Box3();
  for (const id of app.selection) {
    const b = els[id]?.bounds;
    if (b) box.union(boxFromTuple(b));
  }
  if (box.isEmpty()) return false;
  requestFrame(app.renderer.camera, app.renderer.controls, box);
  app.renderer.markDirty();
  return true;
}

const paramsApp = (app: ViewerApp): ParamsApp => app as unknown as ParamsApp;

/** Snapshot the factory values of the plugin sections (once, after the first model, before anything is applied). */
function snapshotFactory(app: ViewerApp): void {
  if (factory) return;
  factory = new Map();
  const doc = collectParams(paramsApp(app)) as Record<string, unknown>;
  for (const name of paramSectionNames().concat(['cinematic'])) {
    if (doc[name] !== undefined) factory.set(name, JSON.parse(JSON.stringify(doc[name])));
  }
}

function summarize(p: Preset, i: number): PresetSummary {
  return { id: p.id, name: p.name, description: p.description, group: p.group, key: keyOf(i), builtIn: p.builtIn, base: p.base, active: p.id === activeId };
}

function applyOne(app: ViewerApp, p: Preset): ApplyResult {
  snapshotFactory(app);
  const result = applyPreset(paramsApp(app), p, env());
  activeId = p.id;
  lastResult = result;
  baselinePending = true;
  guiState.preset = p.name;
  setStatus(result);
  if (result.partial) notify(app, `Preset "${p.name}" partly applied. Skipped: ${result.skipped.slice(0, 6).join(', ')}${result.skipped.length > 6 ? ', ...' : ''}`);
  notifyAll();
  return result;
}

function setStatus(r: ApplyResult | null): void {
  if (!activeId || !r) guiState.status = 'No preset applied';
  else guiState.status = r.partial ? `${r.name}: partly applied (${r.skipped.length} skipped)` : `${r.name}: applied`;
}

function registerKeyed(app: ViewerApp): void {
  for (const off of offKeyed) off();
  offKeyed = [];
  const list = store?.list() ?? [];
  for (let n = 1; n <= 9; n++) {
    const p = list[n - 1];
    const id = p?.id;
    offKeyed.push(
      registerAction({
        id: `preset.${n}`,
        label: p ? `Preset: ${p.name}` : `Preset ${n}`,
        group: 'Presets',
        keys: [`code:Digit${n}`],
        description: p?.description,
        run: () => {
          const q = id ? store?.get(id) : undefined;
          if (q) applyOne(app, q);
        },
      }),
    );
  }
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

async function loadOverrides(): Promise<Preset[]> {
  const embedded = window.__xrayEmbeddedPresets;
  if (embedded !== undefined && embedded !== null) return parsePresetsDocument(embedded, true).presets;
  try {
    const r = await fetch('/xray.presets.json');
    if (!r.ok) return [];
    const text = await r.text();
    if (!text.trimStart().startsWith('{')) return []; // a dev server answering with index.html
    return parsePresetsDocument(text, true).presets;
  } catch {
    return [];
  }
}

export const presetsPlugin: AppPlugin = {
  name: 'presets',

  install(app: ViewerApp): void {
    appRef = app;
    const embedded = window.__xrayEmbeddedPresets;
    const sync = embedded !== undefined && embedded !== null ? parsePresetsDocument(embedded, true).presets : [];
    const st = new PresetStore(localStore(), sync);
    store = st;
    guiState = { preset: st.list()[0]?.name ?? '', status: 'No preset applied' };

    pendingShare = presetFromHash(location.hash);
    if (!pendingShare && /(^|[#&])preset=/.test(location.hash)) console.warn('presets: could not decode the #preset= fragment');

    // No embedded override: ask the server for the build-time file; the TS built-ins are already in use meanwhile.
    if (embedded === undefined || embedded === null) {
      void loadOverrides().then((o) => {
        if (o.length > 0) st.setOverrides(o);
      });
    }

    const api: PresetsApi = {
      list: () => st.list().map(summarize),
      apply(idOrName) {
        const p = findPreset(st.list(), idOrName);
        if (!p) throw new Error(`unknown preset "${idOrName}"`);
        return applyOne(app, p);
      },
      save(name, sections = DEFAULT_CAPTURE, description = '') {
        snapshotFactory(app);
        const { preset, missing } = capturePreset(paramsApp(app), sections, { name, description, takenIds: new Set(st.list().map((p) => p.id)) }, env());
        const stored = st.add(preset);
        return { preset: stored, missing };
      },
      remove: (id) => st.remove(id),
      active: () => activeId,
      markActive(id, note) {
        const p = st.get(id);
        if (!p) return false;
        snapshotFactory(app);
        activeId = p.id;
        baselinePending = true;
        guiState.preset = p.name;
        guiState.status = `${p.name}: ${note ?? 'restored with a saved view'}`;
        notifyAll();
        return true;
      },
      lastResult: () => lastResult,
      get: (id) => st.get(id),
      exportJson: (all) => st.exportJson(all),
      importJson(text) {
        const r = st.importJson(text);
        return { added: r.added.map((p) => p.id), errors: r.errors };
      },
      shareUrl(id) {
        const p = st.get(id);
        return p ? presetShareUrl(p, { origin: location.origin, pathname: location.pathname, search: location.search }) : null;
      },
    };
    window.__xrayPresets = api;

    st.onChange(() => {
      registerKeyed(app);
      if (activeId && !st.get(activeId)) {
        activeId = null;
        setStatus(null);
      }
      notifyAll();
    });
    registerKeyed(app);
    registerAction({
      id: 'presets.open',
      label: 'Open the presets panel',
      group: 'Presets',
      keys: [],
      description: 'Open the presets drawer in the action panel',
      run: () => void window.__xrayToolbar?.open('presets'),
    });

    const host: PanelHost = {
      list: () => st.list(),
      activeId: () => activeId,
      lastResult: () => lastResult,
      apply: (id) => {
        const p = st.get(id);
        if (p) applyOne(app, p);
      },
      captureSections: () => ({ all: captureSections(paramsApp(app), env()), defaults: DEFAULT_CAPTURE }),
      save: (name, sections, description) => {
        const r = api.save(name, sections, description);
        if (r.missing.length > 0) notify(app, `Not stored (not in this build): ${r.missing.join(', ')}`, 4000);
        return { id: r.preset.id, missing: r.missing };
      },
      update: (id, patch) => void st.update(id, patch),
      duplicate: (id) => void st.duplicate(id),
      remove: (id) => void st.remove(id),
      share: (id) => {
        const url = api.shareUrl(id);
        if (!url) return;
        void copyText(url).then((ok) => notify(app, ok ? `Share link copied (${url.length} characters).` : 'Could not copy to the clipboard.', 2500));
      },
      exportFile: () => exportFile(app),
      importFile: () => fileInput?.click(),
      subscribe: (cb) => {
        listeners.add(cb);
        return () => listeners.delete(cb);
      },
      takeSaveRequest: () => {
        const v = saveRequested;
        saveRequested = false;
        return v;
      },
    };

    registerTool({
      id: 'presets',
      label: 'Presets',
      title: 'Named looks: apply with keys 1 to 9, or save your own',
      icon: ICON,
      order: 5,
      drawerWidth: 340,
      panel: (box) => presetsPanel(box, host),
    });

    fileInput = document.createElement('input');
    fileInput.type = 'file';
    fileInput.accept = 'application/json,.json';
    fileInput.style.display = 'none';
    fileInput.addEventListener('change', () => {
      const file = fileInput?.files?.[0];
      if (!file) return;
      void file.text().then((text) => {
        const r = st.importJson(text);
        notify(app, r.added.length > 0 ? `Imported ${r.added.length} preset${r.added.length === 1 ? '' : 's'}.${r.errors.length > 0 ? ` ${r.errors.length} problem(s): ${r.errors[0]}` : ''}` : `Import failed: ${r.errors[0] ?? 'no presets found'}`);
      });
      if (fileInput) fileInput.value = '';
    });
    document.body.appendChild(fileInput);

    buildGui(app, st, host);

    // The active mark is cleared when a setting changes afterwards: compare a cheap hash once a second.
    setInterval(() => {
      if (!appRef?.controller || !activeId) return;
      try {
        const h = settingsHash(paramsApp(app), env());
        if (baselinePending) {
          activeHash = h;
          baselinePending = false;
        } else if (h !== activeHash) {
          activeId = null;
          setStatus(null);
          notifyAll();
        }
      } catch {
        /* a failing section: keep the mark */
      }
    }, 1000);
  },

  onModel(app: ViewerApp): void {
    snapshotFactory(app);
    const share = pendingShare;
    if (!share) return;
    pendingShare = null;
    try {
      const h = hashWithoutPreset(location.hash);
      const u = new URL(location.href);
      u.hash = h;
      history.replaceState(null, '', u);
    } catch {
      /* ignore */
    }
    applyOne(app, { ...share, id: 'shared-preset', builtIn: false });
  },
};

function exportFile(app: ViewerApp): void {
  const st = store;
  if (!st) return;
  const user = st.userPresets();
  if (user.length === 0) {
    notify(app, 'No saved presets to export. Save one first.', 3000);
    return;
  }
  download(`xray-presets-${new Date().toISOString().slice(0, 10)}.json`, st.exportJson(false));
}

function buildGui(app: ViewerApp, st: PresetStore, host: PanelHost): void {
  const gui = app.panel;
  if (!gui) return;
  const f = gui.addFolder('Presets');
  f.close();
  const names = (): string[] => st.list().map((p) => p.name);
  let dropdown = f.add(guiState, 'preset', names()).name('preset');
  f.add({ apply: () => {
    const p = findPreset(st.list(), guiState.preset);
    if (p) applyOne(app, p);
  } }, 'apply').name('Apply preset');
  f.add({ save: () => {
    saveRequested = true;
    const tb = window.__xrayToolbar;
    if (tb?.open('presets')) {
      for (const l of listeners) l();
    } else notify(app, 'Open the Presets tool in the action panel to save a preset.', 3000);
  } }, 'save').name('Save current as preset');
  f.add({ exp: () => exportFile(app) }, 'exp').name('Export presets');
  f.add({ imp: () => host.importFile() }, 'imp').name('Import presets');
  const statusCtl = f.add(guiState, 'status').name('Preset status');
  statusCtl.disable();
  guiRefresh = () => {
    const list = names();
    if (!list.includes(guiState.preset)) guiState.preset = list[0] ?? '';
    // Rebuild the dropdown options when the list changed.
    const cur = (dropdown as unknown as { $select?: HTMLSelectElement }).$select;
    const have = cur ? Array.from(cur.options).map((o) => o.value) : [];
    if (have.join('\u0000') !== list.join('\u0000')) {
      dropdown = dropdown.options(list);
    }
    dropdown.updateDisplay();
    statusCtl.updateDisplay();
  };
}
