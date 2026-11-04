// Command palette (Ctrl+K): fuzzy search over every registered action plus every button and checkbox of the lil-gui
// panel. The ranking (fuzzyScore, rankItems) is pure and tested; PaletteView is the DOM.

import type { ViewerApp } from '../app';
import { el } from './dom';
import { ensureKeyStyles, renderChords } from './keymapView';
import type { Keymap, Overlay } from '../input/keymap';
import { getActions, runAction } from '../input/actions';

export interface FuzzyMatch {
  score: number;
  /** Indices of the matched characters in the text. */
  positions: number[];
}

const isWordStart = (t: string, i: number): boolean => {
  if (i === 0) return true;
  const p = t[i - 1]!;
  const c = t[i]!;
  return !/[a-z0-9]/i.test(p) || (p === p.toLowerCase() && c !== c.toLowerCase());
};

/** Subsequence match of `query` in `text` (case-insensitive). Higher is better; null when it does not match. */
export function fuzzyScore(query: string, text: string): FuzzyMatch | null {
  const q = query.toLowerCase().replace(/\s+/g, '');
  const t = text.toLowerCase();
  if (q.length === 0) return { score: 0, positions: [] };
  if (q.length > t.length) return null;
  const n = q.length;
  const m = t.length;
  const NEG = -1e9;
  // best[i][j]: best score matching q[0..i] with q[i] placed at text index j.
  const best: number[][] = Array.from({ length: n }, () => new Array<number>(m).fill(NEG));
  const from: number[][] = Array.from({ length: n }, () => new Array<number>(m).fill(-1));
  for (let i = 0; i < n; i++) {
    for (let j = i; j < m; j++) {
      if (t[j] !== q[i]) continue;
      const here = 1 + (isWordStart(text, j) ? 10 : 0) + (j === 0 ? 6 : 0);
      if (i === 0) {
        best[i]![j] = here - Math.min(j, 6) * 0.5;
        continue;
      }
      let bs = NEG;
      let bk = -1;
      for (let k = i - 1; k < j; k++) {
        const prev = best[i - 1]![k]!;
        if (prev <= NEG / 2) continue;
        const s = prev + (k === j - 1 ? 8 : -Math.min((j - k - 1) * 3, 15));
        if (s > bs) {
          bs = s;
          bk = k;
        }
      }
      if (bk >= 0) {
        best[i]![j] = bs + here;
        from[i]![j] = bk;
      }
    }
  }
  let bj = -1;
  let bs = NEG;
  for (let j = 0; j < m; j++) {
    if (best[n - 1]![j]! > bs) {
      bs = best[n - 1]![j]!;
      bj = j;
    }
  }
  if (bj < 0) return null;
  const positions: number[] = [];
  for (let i = n - 1, j = bj; i >= 0; i--) {
    positions.unshift(j);
    j = from[i]![j]!;
  }
  let score = bs - m * 0.1;
  if (t === q) score += 60;
  else if (t.startsWith(q)) score += 30;
  else if (t.includes(q)) score += 15;
  return { score, positions };
}

export interface PaletteItem {
  /** Stable key for the recent list: 'a:<action id>' or 'g:<folder path>/<name>'. */
  key: string;
  label: string;
  /** Folder path for panel controls, group for actions. */
  path: string;
  chords: string[];
  kind: 'action' | 'button' | 'toggle';
  run(): void;
}

export interface RankedItem {
  item: PaletteItem;
  score: number;
  positions: number[];
}

/** Rank items for a query. Empty query: recent items first (most recent first), then the rest by label. */
export function rankItems(items: readonly PaletteItem[], query: string, recent: readonly string[] = [], limit = 80): RankedItem[] {
  const rec = new Map(recent.map((k, i) => [k, i]));
  const boost = (k: string): number => {
    const i = rec.get(k);
    return i === undefined ? 0 : Math.max(0, 14 - i);
  };
  const out: RankedItem[] = [];
  const q = query.trim();
  for (const item of items) {
    if (!q) {
      out.push({ item, score: boost(item.key), positions: [] });
      continue;
    }
    const a = fuzzyScore(q, item.label);
    const b = fuzzyScore(q, `${item.path} ${item.label}`);
    if (!a && !b) continue;
    const score = Math.max(a ? a.score + 5 : NaN, b ? b.score * 0.6 : NaN) + boost(item.key);
    out.push({ item, score, positions: a ? a.positions : [] });
  }
  out.sort((x, y) => y.score - x.score || x.item.label.localeCompare(y.item.label));
  return out.slice(0, limit);
}

// ---------------------------------------------------------------------------- items from the app

interface GuiCtl {
  _name?: string;
  property?: string;
  _disabled?: boolean;
  $button?: HTMLElement;
  $input?: HTMLInputElement;
  parent?: GuiFolder;
  getValue(): unknown;
  setValue(v: unknown): unknown;
}
interface GuiFolder {
  _title?: string;
  parent?: GuiFolder;
}

function folderPath(c: GuiCtl): string {
  const names: string[] = [];
  for (let f = c.parent; f && f.parent; f = f.parent) names.unshift((f._title ?? '').trim());
  return names.filter(Boolean).join(' / ');
}

/** Actions with a key binding or not, plus the buttons and checkboxes of the panel. */
export function collectItems(app: ViewerApp, km: Keymap, selfLabel = 'Command palette'): PaletteItem[] {
  const items: PaletteItem[] = [];
  for (const a of getActions()) {
    if (a.hold && !a.keys.length) continue;
    if (a.hold) continue; // held camera keys are not commands
    if (a.enabled && !a.enabled(app)) continue;
    items.push({ key: `a:${a.id}`, label: a.label, path: a.group, chords: km.bindingsOf(a.id), kind: 'action', run: () => void runAction(app, a.id) });
  }
  const ctls = (app.panel?.controllersRecursive() ?? []) as unknown as GuiCtl[];
  for (const c of ctls) {
    const label = (c._name ?? c.property ?? '').trim();
    if (!label || c._disabled || label.startsWith(selfLabel)) continue;
    const path = folderPath(c);
    if (c.$button) {
      items.push({ key: `g:${path}/${label}`, label, path, chords: [], kind: 'button', run: () => c.$button!.click() });
    } else if (c.$input && c.$input.type === 'checkbox' && typeof c.getValue() === 'boolean') {
      items.push({ key: `g:${path}/${label}`, label: `Toggle ${label}`, path, chords: [], kind: 'toggle', run: () => void c.setValue(!(c.getValue() as boolean)) });
    }
  }
  return items;
}

// ---------------------------------------------------------------------------- DOM

const RECENT_KEY = 'xray.palette.recent';
const RECENT_MAX = 12;

function readRecent(): string[] {
  try {
    const v = JSON.parse(window.localStorage.getItem(RECENT_KEY) ?? '[]') as unknown;
    return Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string').slice(0, RECENT_MAX) : [];
  } catch {
    return [];
  }
}

function writeRecent(list: string[]): void {
  try {
    window.localStorage.setItem(RECENT_KEY, JSON.stringify(list.slice(0, RECENT_MAX)));
  } catch {
    /* ignore */
  }
}

export class PaletteView implements Overlay {
  private root: HTMLElement | null = null;
  private list: HTMLElement | null = null;
  private input: HTMLInputElement | null = null;
  private items: PaletteItem[] = [];
  private shown: RankedItem[] = [];
  private sel = 0;

  constructor(private readonly app: ViewerApp, private readonly km: Keymap) {
    km.registerOverlay(this);
  }

  isOpen(): boolean {
    return this.root !== null;
  }

  toggle(): void {
    if (this.root) this.close();
    else this.open();
  }

  open(): void {
    if (this.root) return;
    ensureKeyStyles();
    this.items = collectItems(this.app, this.km);
    const back = el('div', 'kx-backdrop', { role: 'dialog', 'aria-label': 'Command palette' });
    const panel = el('div', 'kx-panel kx-palette');
    const head = el('div', 'kx-head');
    this.input = el('input', 'kx-input', { type: 'text', placeholder: 'Type a command or a setting', 'aria-label': 'Command palette', autocomplete: 'off', spellcheck: 'false' });
    head.append(this.input);
    this.list = el('ul', 'kx-list', { role: 'listbox' });
    panel.append(head, this.list, el('div', 'kx-foot', {}, 'Up and Down choose, Enter runs, Esc closes.'));
    back.append(panel);
    document.body.appendChild(back);
    this.root = back;
    back.addEventListener('mousedown', (e) => {
      if (e.target === back) this.close();
    });
    this.input.addEventListener('input', () => {
      this.sel = 0;
      this.render();
    });
    this.input.addEventListener('keydown', (e) => this.onKey(e));
    this.sel = 0;
    this.render();
    this.input.focus();
  }

  close(): void {
    if (!this.root) return;
    this.root.remove();
    this.root = null;
    this.list = null;
    this.input = null;
  }

  private onKey(e: KeyboardEvent): void {
    e.stopPropagation();
    if (e.key === 'Escape') {
      e.preventDefault();
      this.close();
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      this.move(1);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      this.move(-1);
    } else if (e.key === 'Enter') {
      e.preventDefault();
      this.runSelected();
    }
  }

  private move(d: number): void {
    if (this.shown.length === 0) return;
    this.sel = (this.sel + d + this.shown.length) % this.shown.length;
    this.paintSelection();
  }

  private runSelected(): void {
    const r = this.shown[this.sel];
    if (!r) return;
    this.run(r.item);
  }

  private run(item: PaletteItem): void {
    const recent = [item.key, ...readRecent().filter((k) => k !== item.key)];
    writeRecent(recent);
    this.close();
    item.run();
  }

  private render(): void {
    const list = this.list;
    if (!list) return;
    this.shown = rankItems(this.items, this.input?.value ?? '', readRecent());
    list.textContent = '';
    if (this.shown.length === 0) {
      list.append(el('li', 'kx-item kx-dim', {}, 'No match.'));
      return;
    }
    this.shown.forEach((r, i) => {
      const li = el('li', 'kx-item', { role: 'option', 'data-key': r.item.key });
      const label = el('span', 'kx-label');
      this.highlight(label, r.item.label, r.positions);
      const path = el('span', 'kx-path', {}, r.item.path);
      const keys = el('span', 'kx-keys');
      renderChords(keys, r.item.chords.slice(0, 2));
      if (r.item.chords.length === 0) keys.textContent = '';
      li.append(label, path, keys);
      li.addEventListener('mousemove', () => {
        if (this.sel !== i) {
          this.sel = i;
          this.paintSelection();
        }
      });
      li.addEventListener('mousedown', (e) => {
        e.preventDefault();
        this.run(r.item);
      });
      list.append(li);
    });
    this.paintSelection();
  }

  private highlight(host: HTMLElement, text: string, positions: number[]): void {
    const set = new Set(positions);
    let run = '';
    let marked = false;
    const flush = (): void => {
      if (!run) return;
      if (marked) host.append(el('mark', '', {}, run));
      else host.append(document.createTextNode(run));
      run = '';
    };
    for (let i = 0; i < text.length; i++) {
      const m = set.has(i);
      if (m !== marked) {
        flush();
        marked = m;
      }
      run += text[i];
    }
    flush();
  }

  private paintSelection(): void {
    const kids = this.list?.children;
    if (!kids) return;
    for (let i = 0; i < kids.length; i++) {
      const k = kids[i] as HTMLElement;
      const on = i === this.sel;
      k.classList.toggle('kx-sel', on);
      if (on) k.scrollIntoView({ block: 'nearest' });
    }
  }
}
