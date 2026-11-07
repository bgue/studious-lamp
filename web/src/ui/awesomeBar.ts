// The search bar ("awesome bar"): one box that searches elements, commands, presets, saved views, selection sets and
// settings, and runs WHERE queries. This file is the DOM and the keys; the matching is in src/search, the registration
// and the mount point in src/plugins/awesomeBar.ts. Docs: docs-features/search.md.
//
// DOM: .ab-root > .ab-icon (phone: the collapsed form) + .ab-field > input (role combobox). The result list
// (.ab-pop > ul role listbox) hangs off document.body and is positioned under the input, so a thin top bar cannot clip it.

import type { ViewerApp } from '../app';
import { SearchSources, selectAndFrame } from '../search/sources';
import type { Row } from '../search/sources';
import { detectQuery, runLive } from '../search/queryMode';
import { EXPANDED_CAP, SECTION_CAP, SECTION_TITLES, orderGroups } from '../search/rank';
import type { SectionId } from '../search/rank';
import { el } from './dom';
import { ensureKeyStyles, renderChords } from './keymapView';

export const RECENT_KEY = 'xray.search.recent';
const RECENT_MAX = 8;
const DEBOUNCE_MS = 30;
const PHONE_QUERY = '(max-width: 700px)';

const CSS = `
.ab-root { position: relative; display: flex; align-items: center; min-width: 0; width: 100%; max-width: 520px; box-sizing: border-box; font: 12px/1.35 system-ui, sans-serif; color: var(--sb-fg, #dfe6ee); }
.ab-root[hidden] { display: none; }
.ab-root * { box-sizing: border-box; }
.ab-root.ab-fallback { position: absolute; top: 6px; left: 50%; transform: translateX(-50%); width: min(460px, calc(100% - 140px)); z-index: 13; }
.ab-field { position: relative; display: flex; align-items: center; flex: 1 1 auto; min-width: 0; }
.ab-glyph { position: absolute; left: 8px; top: 50%; width: 14px; height: 14px; margin-top: -7px; color: var(--sb-dim, #8d99a8); pointer-events: none; }
.ab-input { width: 100%; height: 26px; padding: 0 30px 0 28px; background: #0e1218; color: inherit; border: 1px solid var(--sb-line, #262d3a); border-radius: 13px; font: inherit; outline: none; user-select: text; -webkit-user-select: text; }
.ab-input::placeholder { color: var(--sb-dim, #8d99a8); }
.ab-input:focus { border-color: var(--sb-accent, #3b9cff); box-shadow: 0 0 0 2px rgba(59,156,255,0.25); }
.ab-hint { position: absolute; right: 8px; top: 50%; transform: translateY(-50%); pointer-events: none; padding: 0 5px; border: 1px solid #3a4558; border-radius: 4px; color: var(--sb-dim, #8d99a8); font-size: 10px; line-height: 14px; }
.ab-root.ab-has-text .ab-hint, .ab-root.ab-focus .ab-hint { display: none; }
.ab-icon { display: none; width: 30px; height: 26px; padding: 0; align-items: center; justify-content: center; background: transparent; color: inherit; border: 1px solid var(--sb-line, #262d3a); border-radius: 13px; cursor: pointer; }
.ab-icon:hover { background: var(--sb-hover, #1c2230); }
.ab-icon svg { width: 15px; height: 15px; }
.ab-root.ab-phone .ab-icon { display: flex; }
.ab-root.ab-phone:not(.ab-open) .ab-field { display: none; }
.ab-root.ab-phone.ab-open { position: fixed; left: 8px; right: 8px; top: 6px; width: auto; max-width: none; z-index: 58; }
.ab-root.ab-phone.ab-open .ab-icon { display: none; }
.ab-root.ab-phone .ab-hint { display: none; }
.ab-root.ab-phone.ab-open .ab-input { height: 32px; font-size: 16px; }
.ab-pop { position: fixed; z-index: 59; display: none; flex-direction: column; max-height: min(70vh, 560px); background: var(--sb-bg, #141820); color: var(--sb-fg, #dfe6ee); border: 1px solid var(--sb-line, #262d3a); border-radius: 8px; box-shadow: 0 10px 30px rgba(0,0,0,0.45); font: 12px/1.35 system-ui, sans-serif; overflow: hidden; }
.ab-pop.ab-on { display: flex; }
.ab-list { list-style: none; margin: 0; padding: 4px; overflow: auto; flex: 1 1 auto; min-height: 0; }
.ab-head { padding: 7px 8px 2px; font-size: 10px; letter-spacing: 0.07em; text-transform: uppercase; color: var(--sb-dim, #8d99a8); font-weight: 600; }
.ab-opt { display: flex; align-items: baseline; gap: 8px; padding: 5px 8px; border-radius: 4px; cursor: pointer; }
.ab-opt.ab-active { background: var(--sb-sel, #1f4a7a); }
.ab-main { flex: 1 1 auto; min-width: 0; display: flex; flex-direction: column; }
.ab-label { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ab-sub, .ab-via { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--sb-dim, #8d99a8); font-size: 11px; }
.ab-via { color: #a9b6c6; }
.ab-opt mark { background: transparent; color: #ffd479; font-weight: 600; }
.ab-side { flex: 0 0 auto; display: flex; gap: 2px; align-items: center; color: var(--sb-dim, #8d99a8); font-size: 11px; }
.ab-more { color: var(--sb-accent, #3b9cff); }
.ab-note { padding: 6px 10px; color: var(--sb-dim, #8d99a8); }
.ab-note.ab-err { color: #ffb3ad; background: #2a1618; border-radius: 4px; margin: 2px 4px; }
.ab-foot { padding: 5px 10px; border-top: 1px solid var(--sb-line, #262d3a); color: var(--sb-dim, #8d99a8); font-size: 11px; flex: 0 0 auto; }
.ab-flash { animation: ab-flash 2.2s ease-out; }
@keyframes ab-flash { 0%, 35% { box-shadow: inset 0 0 0 2px #ffd479; background: rgba(255,212,121,0.28); } 100% { box-shadow: inset 0 0 0 2px rgba(255,212,121,0); background: transparent; } }
@media (max-width: 700px) { .ab-sub { display: none; } .ab-opt { padding: 8px 8px; } }
`;

const SEARCH_SVG =
  '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" aria-hidden="true"><circle cx="8.5" cy="8.5" r="5.5"/><path d="M12.8 12.8 17 17"/></svg>';

function ensureStyles(): void {
  if (typeof document === 'undefined' || document.getElementById('xray-ab-style')) return;
  const s = document.createElement('style');
  s.id = 'xray-ab-style';
  s.textContent = CSS;
  document.head.appendChild(s);
}

// ---------------------------------------------------------------------------- recents

export function readRecent(storage: Pick<Storage, 'getItem'> | null): string[] {
  try {
    const v = JSON.parse(storage?.getItem(RECENT_KEY) ?? '[]') as unknown;
    return Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string').slice(0, RECENT_MAX) : [];
  } catch {
    return [];
  }
}

/** The recent list after using `key`: it comes first, duplicates go, the list is capped. */
export function pushRecent(list: readonly string[], key: string): string[] {
  return [key, ...list.filter((k) => k !== key)].slice(0, RECENT_MAX);
}

function storage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

// ---------------------------------------------------------------------------- view model

type Item =
  | { type: 'head'; title: string }
  | { type: 'row'; row: Row; recent: boolean }
  | { type: 'more'; section: SectionId; hidden: number }
  | { type: 'note'; text: string; err?: boolean };

interface Group {
  section: SectionId;
  title: string;
  rows: Row[];
  total: number;
}

function appendHighlighted(host: HTMLElement, text: string, positions: readonly number[]): void {
  if (positions.length === 0) {
    host.textContent = text;
    return;
  }
  const set = new Set(positions);
  let run = '';
  let marked = false;
  const flush = (): void => {
    if (!run) return;
    host.append(marked ? el('mark', '', {}, run) : document.createTextNode(run));
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

export class AwesomeBar {
  readonly root: HTMLElement;
  readonly input: HTMLInputElement;
  readonly icon: HTMLButtonElement;
  private readonly pop: HTMLElement;
  private readonly list: HTMLElement;
  private readonly foot: HTMLElement;
  private readonly sources: SearchSources;
  private readonly phoneMq: MediaQueryList | null;
  private items: Item[] = [];
  private options: number[] = []; // indexes into items that can be chosen
  private active = -1; // position in options
  private expanded = new Set<SectionId>();
  private timer: ReturnType<typeof setTimeout> | null = null;
  private previewId: number | null = null;
  private focused = false;
  private lastCount = -1;
  private readonly uid = Math.random().toString(36).slice(2, 7);
  /** Wall time of the last search (ms), for the benchmark and the footer. */
  lastSearchMs = 0;
  private hiddenByHost = false;

  constructor(
    private readonly app: ViewerApp,
    sources: SearchSources,
  ) {
    this.sources = sources;
    ensureStyles();
    ensureKeyStyles();
    const listId = `ab-list-${this.uid}`;
    this.root = el('div', 'ab-root', { role: 'search' });
    this.icon = el('button', 'ab-icon', { type: 'button', 'aria-label': 'Search', 'data-help-key': 'Search bar/Search button', 'data-help-title': 'Search button' });
    this.icon.innerHTML = SEARCH_SVG;
    const field = el('div', 'ab-field');
    const glyph = el('span', 'ab-glyph');
    glyph.innerHTML = SEARCH_SVG;
    this.input = el('input', 'ab-input', {
      type: 'text',
      role: 'combobox',
      id: `ab-input-${this.uid}`,
      placeholder: 'Search elements, commands, settings',
      'aria-label': 'Search elements, commands and settings',
      'aria-autocomplete': 'list',
      'aria-haspopup': 'listbox',
      'aria-expanded': 'false',
      'aria-controls': listId,
      autocomplete: 'off',
      spellcheck: 'false',
      enterkeyhint: 'go',
      'data-help-key': 'Search bar/Search box',
      'data-help-title': 'Search box',
    });
    const hint = el('span', 'ab-hint', { 'aria-hidden': 'true' }, '/');
    field.append(glyph, this.input, hint);
    this.root.append(this.icon, field);

    this.pop = el('div', 'ab-pop');
    this.list = el('ul', 'ab-list', { role: 'listbox', id: listId, 'aria-label': 'Search results' });
    this.foot = el('div', 'ab-foot', { role: 'status', 'aria-live': 'polite' });
    this.pop.append(this.list, this.foot);
    document.body.appendChild(this.pop);

    this.input.addEventListener('input', () => this.schedule());
    this.input.addEventListener('focus', () => this.onFocus());
    this.input.addEventListener('blur', () => this.onBlur());
    this.input.addEventListener('keydown', (e) => this.onKey(e));
    this.icon.addEventListener('click', () => this.focus());
    this.list.addEventListener('mousedown', (e) => e.preventDefault()); // keep the focus in the input
    window.addEventListener('resize', () => this.place());

    this.phoneMq = typeof window.matchMedia === 'function' ? window.matchMedia(PHONE_QUERY) : null;
    const onMq = (): void => {
      this.root.classList.toggle('ab-phone', !!this.phoneMq?.matches);
      if (!this.phoneMq?.matches) this.root.classList.remove('ab-open');
    };
    onMq();
    this.phoneMq?.addEventListener?.('change', onMq);
  }

  // ---------------------------------------------------------------------- public

  get isOpen(): boolean {
    return this.pop.classList.contains('ab-on');
  }

  /** Hide or show the whole bar (kiosk mode, XR session). */
  setHidden(hidden: boolean): void {
    if (hidden === this.hiddenByHost) return;
    this.hiddenByHost = hidden;
    this.root.hidden = hidden;
    if (hidden) this.dismiss();
  }

  get hidden(): boolean {
    return this.hiddenByHost;
  }

  /** Focus the box (phone: expand it first) and select its text. */
  focus(): void {
    if (this.hiddenByHost) return;
    if (this.root.classList.contains('ab-phone')) this.root.classList.add('ab-open');
    this.input.focus();
    this.input.select();
  }

  /** Clear the text, close the list, give the focus back to the page. */
  dismiss(): void {
    this.input.value = '';
    this.root.classList.remove('ab-has-text');
    this.close();
    this.input.blur();
    this.root.classList.remove('ab-open');
  }

  setQuery(text: string): void {
    this.input.value = text;
    this.run();
  }

  /** Snapshot for scripts and the smoke test. */
  state(): { open: boolean; query: string; active: number; rows: Array<{ section: string; key: string; label: string; sub: string; via: string }>; notes: string[]; footer: string; hidden: boolean } {
    const rows: Array<{ section: string; key: string; label: string; sub: string; via: string }> = [];
    const notes: string[] = [];
    for (const it of this.items) {
      if (it.type === 'row') rows.push({ section: it.row.section, key: it.row.key, label: it.row.label, sub: it.row.sub ?? '', via: it.row.via ?? '' });
      else if (it.type === 'note') notes.push(it.text);
      else if (it.type === 'more') rows.push({ section: it.section, key: `more:${it.section}`, label: `${it.hidden} more…`, sub: '', via: '' });
    }
    return { open: this.isOpen, query: this.input.value, active: this.active, rows, notes, footer: this.foot.textContent ?? '', hidden: this.hiddenByHost };
  }

  /** Re-run the search now (the model or the panel changed while the list is open). */
  refresh(): void {
    if (this.isOpen) this.run();
  }

  // ---------------------------------------------------------------------- events

  private onFocus(): void {
    this.focused = true;
    this.root.classList.add('ab-focus');
    this.sources.invalidate();
    this.run();
  }

  private onBlur(): void {
    this.focused = false;
    this.root.classList.remove('ab-focus');
    this.close();
    if (this.root.classList.contains('ab-phone') && this.input.value === '') this.root.classList.remove('ab-open');
  }

  private onKey(e: KeyboardEvent): void {
    e.stopPropagation(); // the keymap ignores text fields anyway; keep other window listeners out
    if (e.isComposing) return;
    const mod = e.ctrlKey || e.metaKey;
    if (mod && e.key.toLowerCase() === 'k') {
      e.preventDefault();
      this.input.select();
      return;
    }
    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        if (!this.isOpen) this.run();
        this.move(1);
        break;
      case 'ArrowUp':
        e.preventDefault();
        if (!this.isOpen) this.run();
        this.move(-1);
        break;
      case 'Enter':
        e.preventDefault();
        this.flushPending();
        this.activate(e.shiftKey);
        break;
      case 'Escape':
        e.preventDefault();
        this.dismiss();
        break;
      default:
    }
  }

  private schedule(): void {
    this.root.classList.toggle('ab-has-text', this.input.value !== '');
    if (this.timer) clearTimeout(this.timer);
    this.timer = setTimeout(() => {
      this.timer = null;
      this.run();
    }, DEBOUNCE_MS);
  }

  private flushPending(): void {
    if (!this.timer) return;
    clearTimeout(this.timer);
    this.timer = null;
    this.run();
  }

  // ---------------------------------------------------------------------- search

  private run(): void {
    if (this.timer) {
      clearTimeout(this.timer);
      this.timer = null;
    }
    this.root.classList.toggle('ab-has-text', this.input.value !== '');
    const t0 = performance.now();
    this.items = this.build(this.input.value);
    this.lastSearchMs = performance.now() - t0;
    this.options = [];
    this.items.forEach((it, i) => {
      if (it.type === 'row' || it.type === 'more') this.options.push(i);
    });
    this.active = this.options.length > 0 ? 0 : -1;
    this.paint();
    this.updatePreview();
  }

  private build(raw: string): Item[] {
    const q = raw.trim();
    const items: Item[] = [];
    if (!this.app.controller) return items;
    const st = storage();
    if (q === '') {
      const rows: Row[] = [];
      for (const key of readRecent(st)) {
        const r = this.sources.resolve(key);
        if (r) rows.push(r);
      }
      if (rows.length > 0) {
        items.push({ type: 'head', title: SECTION_TITLES.recent });
        for (const r of rows) items.push({ type: 'row', row: r, recent: true });
      } else {
        items.push({ type: 'note', text: 'Type to find elements, commands, presets, views, sets and settings. Start with where to run a query.' });
      }
      this.lastCount = -1;
      return items;
    }

    const det = detectQuery(raw);
    if (det.mode === 'query') {
      const live = runLive(this.app.controller.model, det.expr);
      this.lastCount = live.error ? -1 : live.count;
      if (det.expr.trim() === '') {
        items.push({ type: 'note', text: `Type a condition, for example class = 'IfcWall' and storey like '%1%'.` });
        return items;
      }
      if (live.error) {
        items.push({ type: 'note', text: live.error, err: true });
        if (det.forced) return items;
        // It looked like a query but is not one: search as text too, below the message.
      } else {
        const classes = new Map<string, number>();
        const els = this.app.controller.model.elements;
        for (const id of live.ids) classes.set(els[id]!.ifcClass, (classes.get(els[id]!.ifcClass) ?? 0) + 1);
        const top = [...classes.entries()].sort((a, b) => b[1] - a[1]).slice(0, 3).map(([c, n]) => `${n} ${c}`).join(', ');
        const label = live.count === 1 ? '1 element matches' : `${live.count} elements match`;
        const ids = live.ids;
        const row: Row = {
          key: 'q:',
          section: 'query',
          label,
          positions: [],
          sub: live.count > 0 ? `Enter selects ${live.count === 1 ? 'it' : 'them all'}. Shift+Enter adds to the selection.${top ? ` ${top}.` : ''}` : 'Nothing to select.',
          score: 100,
          run: (add) => {
            if (ids.length === 0) return;
            selectAndFrame(this.app, ids, add);
          },
        };
        items.push({ type: 'head', title: SECTION_TITLES.query });
        items.push({ type: 'row', row, recent: false });
        if (live.unknown.length > 0) items.push({ type: 'note', text: `No element has a property named ${live.unknown.map((u) => `"${u}"`).join(', ')}. It reads as empty.` });
        return items;
      }
    } else {
      this.lastCount = -1;
    }

    // Plain text. A leading ">" limits the search to commands and settings, like the palette.
    const cmdOnly = q.startsWith('>');
    const text = cmdOnly ? q.slice(1).trim() : q;
    const groups: Group[] = [];
    const add = (section: SectionId, rows: Row[], total = rows.length): void => {
      if (rows.length > 0) groups.push({ section, title: SECTION_TITLES[section], rows, total });
    };
    let footer = '';
    if (!cmdOnly) {
      const e = this.sources.elements(text);
      add('elements', e.rows, e.total);
      footer = e.indexing ? 'Indexing the model: results may be incomplete.' : '';
      this.lastElementMs = e.ms;
    }
    add('commands', this.sources.commands(text));
    if (!cmdOnly) {
      add('presets', this.sources.presets(text));
      add('views', this.sources.views(text));
      add('sets', this.sources.sets(text));
    }
    add('settings', this.sources.settingsRows(text));
    this.footNote = footer;

    const ordered = orderGroups(groups);
    for (const g of ordered) {
      const expanded = this.expanded.has(g.section);
      const cap = expanded ? EXPANDED_CAP : SECTION_CAP[g.section];
      const shown = g.rows.slice(0, cap);
      items.push({ type: 'head', title: g.title });
      for (const r of shown) items.push({ type: 'row', row: r, recent: false });
      const hidden = g.total - shown.length;
      if (hidden > 0) {
        if (!expanded && g.rows.length > shown.length) items.push({ type: 'more', section: g.section, hidden });
        else items.push({ type: 'note', text: `${hidden} more not shown. Type more letters to narrow the list.` });
      }
    }
    if (ordered.length === 0) items.push({ type: 'note', text: 'No match.' });
    return items;
  }

  private footNote = '';
  lastElementMs = 0;

  // ---------------------------------------------------------------------- paint

  private paint(): void {
    const list = this.list;
    list.textContent = '';
    this.items.forEach((it, i) => {
      if (it.type === 'head') {
        list.append(el('li', 'ab-head', { role: 'presentation' }, it.title));
        return;
      }
      if (it.type === 'note') {
        list.append(el('li', `ab-note${it.err ? ' ab-err' : ''}`, { role: 'presentation' }, it.text));
        return;
      }
      const li = el('li', 'ab-opt', { role: 'option', id: `ab-opt-${this.uid}-${i}`, 'aria-selected': 'false', 'data-help-key': 'Search bar/Result row', 'data-help-title': 'Result row' });
      if (it.type === 'more') {
        li.classList.add('ab-more');
        li.append(el('span', 'ab-main ab-label', {}, `${it.hidden} more…`));
        li.addEventListener('click', () => this.expand(it.section));
      } else {
        const r = it.row;
        const main = el('span', 'ab-main');
        const label = el('span', 'ab-label');
        appendHighlighted(label, r.label, r.positions);
        main.append(label);
        if (r.sub) {
          const sub = el('span', 'ab-sub');
          appendHighlighted(sub, r.sub, r.subPositions ?? []);
          main.append(sub);
        }
        if (r.via) {
          const via = el('span', 'ab-via');
          appendHighlighted(via, r.via, r.viaPositions ?? []);
          main.append(via);
        }
        const side = el('span', 'ab-side');
        if (r.chords && r.chords.length > 0) renderChords(side, r.chords);
        else if (it.recent) side.textContent = SECTION_TITLES[r.section].replace(/s$/, '');
        li.append(main, side);
        li.addEventListener('click', (e) => this.act(r, e.shiftKey));
      }
      li.addEventListener('mousemove', () => {
        const pos = this.options.indexOf(i);
        if (pos >= 0 && pos !== this.active) {
          this.active = pos;
          this.paintActive();
          this.updatePreview();
        }
      });
      list.append(li);
    });
    this.foot.textContent = this.footerText();
    this.paintActive(false);
    this.openList();
  }

  private footerText(): string {
    const parts: string[] = [];
    if (this.footNote) parts.push(this.footNote);
    if (this.lastCount >= 0) parts.push(`${this.lastCount} ${this.lastCount === 1 ? 'element' : 'elements'} match the query`);
    if (this.options.length > 0) parts.push('Up and Down choose, Enter acts, Shift+Enter adds, Esc closes');
    return parts.join(' · ');
  }

  private paintActive(scroll = true): void {
    const kids = this.list.children;
    for (let i = 0; i < kids.length; i++) {
      const k = kids[i] as HTMLElement;
      if (k.getAttribute('role') !== 'option') continue;
      const on = this.options[this.active] === i;
      k.classList.toggle('ab-active', on);
      k.setAttribute('aria-selected', on ? 'true' : 'false');
      if (on) {
        this.input.setAttribute('aria-activedescendant', k.id);
        if (scroll) k.scrollIntoView({ block: 'nearest' });
      }
    }
    if (this.active < 0) this.input.removeAttribute('aria-activedescendant');
  }

  private openList(): void {
    if (!this.focused) return;
    this.pop.classList.add('ab-on');
    this.input.setAttribute('aria-expanded', 'true');
    this.place();
  }

  private close(): void {
    this.pop.classList.remove('ab-on');
    this.input.setAttribute('aria-expanded', 'false');
    this.input.removeAttribute('aria-activedescendant');
    this.setPreview(null);
    if (this.timer) {
      clearTimeout(this.timer);
      this.timer = null;
    }
  }

  private place(): void {
    if (!this.isOpen) return;
    const r = (this.root.classList.contains('ab-phone') ? this.root : this.input).getBoundingClientRect();
    const vw = window.innerWidth;
    const phone = this.root.classList.contains('ab-phone');
    const width = phone ? vw - 16 : Math.min(Math.max(r.width, 440), vw - 16);
    const left = phone ? 8 : Math.max(8, Math.min(r.left + r.width / 2 - width / 2, vw - width - 8));
    this.pop.style.left = `${left}px`;
    this.pop.style.top = `${r.bottom + 4}px`;
    this.pop.style.width = `${width}px`;
    this.pop.style.maxHeight = `${Math.max(160, window.innerHeight - r.bottom - 16)}px`;
  }

  // ---------------------------------------------------------------------- selection and acting

  private move(d: number): void {
    if (this.options.length === 0) return;
    this.active = (this.active + d + this.options.length) % this.options.length;
    this.paintActive();
    this.updatePreview();
  }

  private expand(section: SectionId): void {
    this.expanded.add(section);
    this.run();
  }

  private activate(add: boolean): void {
    const idx = this.options[this.active];
    const it = idx === undefined ? undefined : this.items[idx];
    if (!it) return;
    if (it.type === 'more') this.expand(it.section);
    else if (it.type === 'row') this.act(it.row, add);
  }

  private act(row: Row, add: boolean): void {
    if (row.key !== 'q:') {
      const st = storage();
      try {
        st?.setItem(RECENT_KEY, JSON.stringify(pushRecent(readRecent(st), row.key)));
      } catch {
        /* storage refused: the recent list is a convenience */
      }
    }
    // Close first, so the keys go back to the page and a flash or a frame move is not hidden by the list.
    this.expanded.clear();
    this.dismiss();
    try {
      row.run(add);
    } catch (e) {
      console.error('[search] action failed', e);
    }
  }

  // ---------------------------------------------------------------------- hover preview

  private updatePreview(): void {
    const idx = this.options[this.active];
    const it = idx === undefined ? undefined : this.items[idx];
    this.setPreview(it && it.type === 'row' && it.row.elementId !== undefined && this.isOpen ? it.row.elementId : null);
  }

  private setPreview(id: number | null): void {
    if (this.previewId === id) return;
    this.previewId = id;
    const r = this.app.renderer as unknown as { setHoverHighlight?: (id: number | null) => void; markDirty?: () => void };
    r.setHoverHighlight?.(id);
    r.markDirty?.();
  }
}
