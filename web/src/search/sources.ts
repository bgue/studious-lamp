// What the search bar searches besides elements: commands, presets, saved views, selection sets and settings. Each source
// turns the query into rows (label, score, a run function). The DOM and the keys are in src/ui/awesomeBar.ts.

import type { ViewerApp } from '../app';
import { getAction, runAction } from '../input/actions';
import { getKeymap } from '../input/keymap';
import { moveToBox } from '../input/navigation';
import { lookupHelp, controllerKey } from '../ui/help';
import type { ControllerLike } from '../ui/help';
import { collectItems, rankItems } from '../ui/palette';
import { runQuery } from '../query';
import { defaultSetsFor, globalIdsToIds, isCriteria, loadSets, unionBounds } from '../selectionSets';
import type { SelectionSet } from '../selectionSets';
import { boxFromTuple } from '../ui/fit';
import type { ElementId } from '../types';
import { ElementIndex } from './elementIndex';
import { fuzzyScore, quickScore, termsOf } from './fuzzy';
import { normalizeFuzzy, rankByText } from './rank';
import type { SectionId } from './rank';
import type { IssueHit } from '../issues/search';

export interface Row {
  /** Stable key: 'e:<GlobalId>', 'a:<action id>', 'p:<preset id>', 'v:<view id>', 's:<set name>', 'g:<path>/<label>', 'q:'. */
  key: string;
  section: SectionId;
  label: string;
  positions: number[];
  sub?: string;
  subPositions?: number[];
  via?: string;
  viaPositions?: number[];
  chords?: string[];
  /** 0 to 100. */
  score: number;
  elementId?: ElementId;
  /** Act on the row. `add` is true for Shift+Enter: add to the selection instead of replacing it. */
  run(add: boolean): void;
}

type Win = Window & {
  __xrayPresets?: { list(): Array<{ id: string; name: string; description: string; group: string; key: string | null }>; apply(id: string): unknown };
  __xrayViews?: { list(): Array<{ id: string; name: string; summary: string }>; restore(key: string): unknown };
  __xrayIssues?: { search(query: string): IssueHit[]; hit(kind: 'issue' | 'sketch', id: string): IssueHit | null; openHit(hit: Pick<IssueHit, 'kind' | 'id'>): boolean };
};
const win = (): Win => window as Win;

export interface Toaster {
  (text: string): void;
}

// ---------------------------------------------------------------------------- framing and selecting

/** Select element ids and frame them (not when `add` is set: the camera stays). */
export function selectAndFrame(app: ViewerApp, ids: ElementId[], add: boolean): void {
  if (ids.length === 0) return;
  app.selectIds(ids, add);
  if (add) return;
  const model = app.controller.model;
  const b = unionBounds(model, ids);
  if (b) moveToBox(app, boxFromTuple(b), { margin: 1.25, tag: 'search' });
}

// ---------------------------------------------------------------------------- settings

interface GuiCtl extends ControllerLike {
  _disabled?: boolean;
  domElement?: HTMLElement;
  $button?: HTMLElement;
}
interface GuiFolder {
  _title?: string;
  parent?: GuiFolder | null;
  open?(v?: boolean): unknown;
  domElement?: HTMLElement;
}

export interface SettingItem {
  key: string;
  label: string;
  path: string;
  /** Intent line of the help text, lower case, for matching. */
  helpL: string;
  ctl: GuiCtl;
}

function folderPath(c: GuiCtl): string {
  const names: string[] = [];
  for (let f = c.parent as GuiFolder | null | undefined; f && f.parent; f = f.parent) names.unshift((f._title ?? '').trim());
  return names.filter(Boolean).join(' / ');
}

/** Every named control of the parameter panel. */
export function collectSettings(app: ViewerApp): SettingItem[] {
  const out: SettingItem[] = [];
  const ctls = (app.panel?.controllersRecursive() ?? []) as unknown as GuiCtl[];
  for (const c of ctls) {
    const label = (c._name ?? c.property ?? '').trim();
    if (!label) continue;
    const path = folderPath(c);
    let helpL = '';
    try {
      const h = lookupHelp(controllerKey(c));
      if (h) helpL = `${h.intent} ${h.impact}`.toLowerCase();
    } catch {
      /* no help text for this control */
    }
    out.push({ key: `g:${path}/${label}`, label, path, helpL, ctl: c });
  }
  return out;
}

let flashTimer: ReturnType<typeof setTimeout> | null = null;
let flashed: HTMLElement | null = null;

/** Open the folders above a control, make the dock visible, scroll to the control and flash it. */
export function jumpToSetting(app: ViewerApp, ctl: GuiCtl): void {
  const chain: GuiFolder[] = [];
  for (let f = ctl.parent as GuiFolder | null | undefined; f; f = f.parent) chain.push(f);
  for (const f of chain.reverse()) f.open?.(true);
  if (document.body.classList.contains('dk-collapsed')) runAction(app, 'panel.right');
  const dom = ctl.domElement;
  if (!dom) return;
  const show = (): void => {
    dom.scrollIntoView({ block: 'center', behavior: 'auto' });
  };
  show();
  // The folder animates open: scroll again when it has settled.
  setTimeout(show, 320);
  if (flashed) flashed.classList.remove('ab-flash');
  if (flashTimer) clearTimeout(flashTimer);
  void dom.offsetWidth;
  dom.classList.add('ab-flash');
  flashed = dom;
  flashTimer = setTimeout(() => {
    dom.classList.remove('ab-flash');
    if (flashed === dom) flashed = null;
  }, 2200);
}

// ---------------------------------------------------------------------------- the sources

export class SearchSources {
  private settings: SettingItem[] | null = null;
  index: ElementIndex | null = null;

  constructor(
    private readonly app: ViewerApp,
    private readonly toast: Toaster,
  ) {}

  /** Forget cached lists (the panel or the model changed). */
  invalidate(): void {
    this.settings = null;
  }

  private settingList(): SettingItem[] {
    return (this.settings ??= collectSettings(this.app));
  }

  // ----- elements

  elements(query: string, keep = 200): { rows: Row[]; total: number; ms: number; indexing: boolean } {
    const idx = this.index;
    const terms = termsOf(query);
    if (!idx || terms.length === 0) return { rows: [], total: 0, ms: 0, indexing: !!idx && !idx.ready };
    const t0 = performance.now();
    const r = idx.search(terms, keep);
    const ms = performance.now() - t0;
    const els = this.app.controller.model.elements;
    const rows = r.hits.map((h) => this.elementRow(h.id, terms, Math.min(100, h.score), els[h.id]!.globalId));
    return { rows, total: r.total, ms, indexing: !idx.ready };
  }

  elementRow(id: ElementId, terms: readonly string[], score: number, globalId: string): Row {
    const idx = this.index;
    const ex = idx?.explain(id, terms);
    const e = this.app.controller.model.elements[id]!;
    const label = ex?.label ?? (e.name || e.ifcClass);
    return {
      key: `e:${globalId}`,
      section: 'elements',
      label,
      positions: ex?.labelPositions ?? [],
      sub: ex?.sub ?? e.ifcClass,
      subPositions: ex?.subPositions ?? [],
      via: ex?.via,
      viaPositions: ex?.viaPositions,
      score,
      elementId: id,
      run: (add) => selectAndFrame(this.app, [id], add),
    };
  }

  // ----- commands

  commands(query: string): Row[] {
    const km = getKeymap();
    if (!km) return [];
    const items = collectItems(this.app, km).filter((i) => i.kind === 'action' && i.key !== 'a:search.focus');
    const ranked = rankItems(items, query, [], 400);
    return ranked.map((r) => ({
      key: r.item.key,
      section: 'commands' as const,
      label: r.item.label,
      positions: r.positions,
      sub: r.item.path,
      chords: r.item.chords.slice(0, 2),
      score: normalizeFuzzy(r.score),
      run: () => r.item.run(),
    }));
  }

  // ----- presets, views, sets

  presets(query: string): Row[] {
    const api = win().__xrayPresets;
    if (!api) return [];
    const list = api.list();
    return rankByText(list, query, (p) => ({ label: p.name, extra: `${p.description} ${p.group}` })).map((r) => ({
      key: `p:${r.item.id}`,
      section: 'presets' as const,
      label: r.item.name,
      positions: r.positions,
      sub: r.item.description || r.item.group,
      chords: r.item.key ? [r.item.key] : undefined,
      score: r.score,
      run: () => {
        try {
          api.apply(r.item.id);
        } catch (e) {
          this.toast(`Preset not applied: ${e instanceof Error ? e.message : String(e)}`);
        }
      },
    }));
  }

  views(query: string): Row[] {
    const api = win().__xrayViews;
    if (!api) return [];
    return rankByText(api.list(), query, (v) => ({ label: v.name, extra: v.summary })).map((r) => ({
      key: `v:${r.item.id}`,
      section: 'views' as const,
      label: r.item.name,
      positions: r.positions,
      sub: r.item.summary,
      score: r.score,
      run: () => {
        try {
          api.restore(r.item.id);
        } catch (e) {
          this.toast(`View not restored: ${e instanceof Error ? e.message : String(e)}`);
        }
      },
    }));
  }

  /** Issues and sketches of the loaded model, by title, note, description and comment text (src/issues/search.ts). */
  issues(query: string): Row[] {
    const api = win().__xrayIssues;
    if (!api || !query.trim()) return [];
    return api.search(query).map((h) => this.issueRow(h));
  }

  private issueRow(h: IssueHit): Row {
    return {
      key: `i:${h.kind}:${h.id}`,
      section: 'issues' as const,
      label: h.title,
      positions: h.positions,
      sub: h.sub,
      score: h.score,
      run: () => {
        if (!win().__xrayIssues?.openHit(h)) this.toast(`The ${h.kind} is no longer there`);
      },
    };
  }

  private setList(): SelectionSet[] {
    const model = this.app.controller.model;
    let stored: SelectionSet[] | null = null;
    try {
      stored = loadSets(window.localStorage, this.app.modelName);
    } catch {
      stored = null;
    }
    return stored ?? defaultSetsFor(model, this.app.modelName);
  }

  sets(query: string): Row[] {
    const model = this.app.controller.model;
    return rankByText(this.setList(), query, (s) => ({ label: s.name, extra: isCriteria(s) ? s.query : '' })).map((r) => {
      const s = r.item;
      const crit = isCriteria(s);
      return {
        key: `s:${s.name}`,
        section: 'sets' as const,
        label: s.name,
        positions: r.positions,
        sub: crit ? `Criteria set: ${s.query}` : `${s.globalIds.length} elements`,
        score: r.score,
        run: (add: boolean) => {
          const ids = crit ? runQuery(model, s.query).ids : globalIdsToIds(model, s.globalIds);
          if (ids.length === 0) this.toast(`The set "${s.name}" has no elements in this model`);
          else selectAndFrame(this.app, ids, add);
        },
      };
    });
  }

  // ----- settings

  settingsRows(query: string): Row[] {
    const q = query.trim();
    const terms = termsOf(q);
    const out: Row[] = [];
    for (const s of this.settingList()) {
      const a = fuzzyScore(q, s.label);
      let score = a ? normalizeFuzzy(a.score) : -1;
      if (score < 0) {
        // Folder path, then the help text: every term must appear.
        const pathL = s.path.toLowerCase();
        const inPath = terms.every((t) => quickScore(t, pathL, false) >= 0 || s.label.toLowerCase().includes(t));
        if (inPath) score = 18;
        else if (s.helpL && terms.every((t) => s.helpL.includes(t))) score = 12;
      }
      if (score < 0) continue;
      out.push({
        key: s.key,
        section: 'settings',
        label: s.label,
        positions: a ? a.positions : [],
        sub: s.path,
        score,
        run: () => jumpToSetting(this.app, s.ctl),
      });
    }
    out.sort((x, y) => y.score - x.score || x.label.localeCompare(y.label));
    return out.slice(0, 200);
  }

  // ----- recents

  /** The live row for a stored key, or null when it no longer exists. */
  resolve(key: string): Row | null {
    const model = this.app.controller.model;
    const kind = key.slice(0, 2);
    const ref = key.slice(2);
    switch (kind) {
      case 'e:': {
        const id = model.byGlobalId.get(ref);
        return id === undefined ? null : this.elementRow(id, [], 0, ref);
      }
      case 'a:': {
        const a = getAction(ref);
        if (!a) return null;
        return this.commands('').find((r) => r.key === key) ?? null;
      }
      case 'p:':
        return this.presets('').find((r) => r.key === key) ?? null;
      case 'v:':
        return this.views('').find((r) => r.key === key) ?? null;
      case 's:':
        return this.sets('').find((r) => r.key === key) ?? null;
      case 'i:': {
        const [k, ...rest] = ref.split(':');
        const hit = win().__xrayIssues?.hit(k === 'sketch' ? 'sketch' : 'issue', rest.join(':'));
        return hit ? this.issueRow(hit) : null;
      }
      case 'g:':
        return this.settingsRows('').find((r) => r.key === key) ?? null;
      default:
        return null;
    }
  }
}
