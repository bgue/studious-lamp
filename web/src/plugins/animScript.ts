// Animation script plugin: the Script tab of the right sidebar (editor, errors, Run / Pause / Stop, examples, saved scripts per
// model, .xrayanim files) and window.__xrayScript for smoke tests. The language is in src/anim/script (pure modules); playback is
// the score player of the fly-through work (src/anim/score.ts getScorePlayer), which is registered separately: without it the
// Run button says so.
//
//   window.__xrayScript = { compile(text), run(text), stop(), list(), save(name, text), load(name), remove(name), examples(), text(),
//                           setText(text), state(), paramPaths(), open() }
//
// Scripts are the person's own text: they stay in localStorage `xray.anim.<model identity>` and in exported files. They are not in
// the params document, share links, saved views, presets or packed pages.

import type { AppPlugin, ViewerApp } from '../app';
import { getScorePlayer } from '../anim/score';
import type { ElementRef, Score } from '../anim/score';
import { compileScript } from '../anim/script/compiler';
import type { CompileOptions } from '../anim/script/compiler';
import type { ScriptDiagnostic } from '../anim/script/diagnostics';
import { EXAMPLES } from '../anim/script/examples';
import { runScript } from '../anim/script/runner';
import type { RunResult } from '../anim/script/runner';
import { ScriptPanel } from '../anim/scriptPanel';
import type { ScriptPanelState } from '../anim/scriptPanel';
import { cleanName, findScript, loadDoc, removeScript, saveDoc, upsertScript } from '../anim/scriptStore';
import type { ScriptStorage } from '../anim/scriptStore';
import { identityKey, loadedIdentity } from '../markup/scope';
import { runQuery } from '../query';
import { defaultSetsFor, isCriteria, loadSets, MemoryStorage } from '../selectionSets';
import type { SelectionSet } from '../selectionSets';
import { showToast } from '../ui/keymapView';
import { collectParams } from '../ui/params';
import { addRightSidebarTab } from './rightSidebar';

export interface ScriptApi {
  /** Compile a script text against the loaded model. */
  compile(text: string): { score: Score | null; errors: ScriptDiagnostic[] };
  /** Compile and play a script text (through the editor when the tab is built). */
  run(text: string): RunResult;
  stop(): void;
  list(): Array<{ name: string; chars: number }>;
  save(name: string, text: string): boolean;
  load(name: string): string | null;
  remove(name: string): boolean;
  examples(): Array<{ id: string; title: string }>;
  /** The text in the editor ('' before the tab is first shown). */
  text(): string;
  setText(text: string): void;
  state(): ScriptPanelState | null;
  /** The settings paths the compiler checks `set` statements against. */
  paramPaths(): string[];
  open(): void;
}

declare global {
  interface Window {
    __xrayScript?: ScriptApi;
  }
}

/** Params keys that are lists of the user's data or whole tables, not settings to animate. */
const SKIP_KEYS = new Set(['schema', 'exportedAt', 'model', 'viewer', 'classStyles', 'materialAliases', 'selectionSets', 'overrides', 'camera', 'keymap', 'views', 'tiers', 'classification']);
const MAX_PATHS = 4000;

/** The leaf paths of a params document (numbers, booleans, strings and number lists). */
export function flattenPaths(doc: unknown): string[] {
  const out: string[] = [];
  const walk = (v: unknown, path: string, depth: number): void => {
    if (out.length >= MAX_PATHS || depth > 6) return;
    if (v !== null && typeof v === 'object' && !Array.isArray(v)) {
      for (const [k, x] of Object.entries(v as Record<string, unknown>)) {
        if (depth === 0 && SKIP_KEYS.has(k)) continue;
        walk(x, path ? `${path}.${k}` : k, depth + 1);
      }
    } else if (path && (typeof v === 'number' || typeof v === 'boolean' || typeof v === 'string' || Array.isArray(v))) out.push(path);
  };
  walk(doc, '', 0);
  return out;
}

function storage(): ScriptStorage {
  try {
    const s = window.localStorage;
    s.getItem('xray.probe');
    return s;
  } catch {
    return new MemoryStorage();
  }
}

let onModelHook: (() => void) | null = null;

export const animScriptPlugin: AppPlugin = {
  name: 'animScript',

  install(app: ViewerApp) {
    const store = storage();
    let panel: ScriptPanel | null = null;
    let tab: ReturnType<typeof addRightSidebarTab> | null = null;
    let pathCache: { at: number; paths: string[] } | null = null;

    const modelKey = (): string => identityKey(loadedIdentity(app));

    const paramPaths = (): string[] => {
      const now = Date.now();
      if (pathCache && now - pathCache.at < 3000) return pathCache.paths;
      let paths: string[] = [];
      try {
        if (app.loaded) paths = flattenPaths(collectParams(app as never));
      } catch {
        paths = [];
      }
      pathCache = { at: now, paths };
      return paths;
    };

    const sets = (): SelectionSet[] => {
      const model = app.controller.model;
      let stored: SelectionSet[] | null = null;
      try {
        stored = loadSets(store, app.modelName);
      } catch {
        stored = null;
      }
      return stored && stored.length > 0 ? stored : defaultSetsFor(model as never, app.modelName);
    };

    const gidsOf = (ids: Iterable<number>): string[] => {
      const els = app.controller.model.elements;
      const out: string[] = [];
      for (const id of ids) {
        const g = els[id]?.globalId;
        if (g) out.push(g);
      }
      return out;
    };

    const resolve = (ref: ElementRef): string[] | null => {
      if (!app.loaded) return null;
      const model = app.controller.model;
      if ('globalIds' in ref) return ref.globalIds.filter((g) => model.byGlobalId.has(g));
      if ('all' in ref) return model.elements.map((e) => e.globalId).filter(Boolean);
      if ('selection' in ref) return gidsOf(app.selection);
      if ('query' in ref) {
        const r = runQuery(model, ref.query);
        return r.error ? null : gidsOf(r.ids);
      }
      if ('schedule' in ref) return null; // the elements of a running 4D schedule are known only while it plays
      const s = sets().find((x) => x.name === ref.set);
      if (!s) return [];
      if (isCriteria(s)) {
        const r = runQuery(model, s.query);
        if (!r.error) return gidsOf(r.ids);
      }
      return s.globalIds.filter((g) => model.byGlobalId.has(g));
    };

    const compileOptions = (): CompileOptions => {
      const w = window as unknown as {
        __xrayPresets?: { list(): Array<{ id: string; name: string }> };
        __xrayViews?: { list(): Array<{ name: string }> };
      };
      let presets: Array<{ id: string; name: string }> | null = null;
      let views: string[] | null = null;
      try {
        presets = w.__xrayPresets?.list().map((p) => ({ id: p.id, name: p.name })) ?? null;
      } catch {
        presets = null;
      }
      try {
        views = w.__xrayViews?.list().map((v) => v.name) ?? null;
      } catch {
        views = null;
      }
      const loaded = !!app.loaded;
      return {
        resolve,
        setNames: () => (loaded ? sets().map((s) => s.name) : null),
        paramPaths: loaded ? paramPaths() : null,
        presets,
        views,
      };
    };

    const ensurePanel = (pane: HTMLElement, ctx: { onVisible(cb: (v: boolean) => void): () => void; setBadge(t: string): void; visible(): boolean }): (() => void) => {
      const p = new ScriptPanel({
        compileOptions,
        player: () => getScorePlayer(),
        modelKey,
        storage: store,
        setBadge: (t) => ctx.setBadge(t),
        toast: (t, ms) => showToast(t, ms),
        record: (text, name) => {
          const rec = window.__xrayRecord;
          const r = compileScript(text, compileOptions());
          if (!rec || !r.score) return;
          void rec.dialog(`Script "${name}"`, r.score, name);
        },
      });
      panel = p;
      const off = p.mount(pane);
      const unsub = ctx.onVisible((v) => p.setVisible(v));
      p.setVisible(ctx.visible());
      return () => {
        unsub();
        off();
        panel = null;
      };
    };

    tab = addRightSidebarTab({
      id: 'script',
      label: 'Script',
      order: 40,
      width: 420,
      title: 'Write an animation script and play it',
      helpKey: 'Right sidebar/Script tab',
      mount: (pane, ctx) => ensurePanel(pane, ctx),
    });

    const api: ScriptApi = {
      compile: (text) => {
        const r = compileScript(text, compileOptions());
        return { score: r.score, errors: r.errors };
      },
      run: (text) => {
        if (panel) {
          panel.setText(text);
          return panel.run();
        }
        return runScript(text, compileOptions(), getScorePlayer());
      },
      stop: () => {
        if (panel) panel.stop();
        else getScorePlayer()?.stop();
      },
      list: () => (panel ? panel.list() : loadDoc(store, modelKey()).scripts.map((s) => ({ name: s.name, chars: s.text.length }))),
      save: (name, text) => {
        const n = cleanName(name);
        if (!n) return false;
        if (panel) {
          panel.setText(text, n);
          panel.save(n);
          return true;
        }
        const key = modelKey();
        return saveDoc(store, key, upsertScript(loadDoc(store, key), n, text));
      },
      load: (name) => {
        if (panel) return panel.load(name) ? panel.text : null;
        return findScript(loadDoc(store, modelKey()), name)?.text ?? null;
      },
      remove: (name) => {
        if (panel) return panel.remove(name);
        const key = modelKey();
        const doc = loadDoc(store, key);
        if (!findScript(doc, name)) return false;
        return saveDoc(store, key, removeScript(doc, name));
      },
      examples: () => EXAMPLES.map((e) => ({ id: e.id, title: e.title })),
      text: () => panel?.text ?? '',
      setText: (text) => panel?.setText(text),
      state: () => panel?.state() ?? null,
      paramPaths: () => paramPaths(),
      open: () => tab?.show(),
    };
    window.__xrayScript = api;
    onModelHook = () => {
      pathCache = null;
      panel?.refreshModel();
    };
  },

  onModel() {
    onModelHook?.();
  },
};
