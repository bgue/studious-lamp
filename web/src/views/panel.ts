// DOM of the "Views" tab of the sidebar: save, play, export / import, a filter box and the list of saved views.
// One-line rows (grip · number · name · summary · ⋯) with the thumbnail shown next to the row on hover, or a compact
// grid of thumbnails (the grid toggle; the choice and the dwell time persist in localStorage `xray.views.ui`).
// Rows are reordered by dragging the grip (pointer events, so touch works too) or with Alt+ArrowUp / Alt+ArrowDown.
// State lives in the plugin (src/plugins/views.ts); the panel calls back through ViewsHost and re-renders on render().

import { debounce, el, esc } from '../ui/dom';
import { closeMenu, openMenu } from '../ui/popupMenu';
import type { MenuItem } from '../ui/popupMenu';
import { filterViews, viewSummary } from './model';
import type { SavedView } from './model';

export interface ViewsHost {
  views(): readonly SavedView[];
  activeId(): string | null;
  playing(): boolean;
  /** BCF topics can be created (window.__xrayBcf.createTopic exists). */
  canBcf(): boolean;
  save(name: string): void;
  restore(index: number): void;
  update(index: number): void;
  rename(index: number, name: string): void;
  duplicate(index: number): void;
  copyLink(index: number): void;
  bcf(index: number): void;
  remove(index: number): void;
  move(from: number, to: number): void;
  togglePlay(): void;
  exportFile(): void;
  importFile(file: File): void;
  dwellMs(): number;
  setDwellMs(ms: number): void;
}

const UI_KEY = 'xray.views.ui';
export const DWELL_CHOICES = [2000, 4000, 6000, 10000];
const STYLE_ID = 'xray-views-style';
const CSS = `
.vw { flex: 1 1 auto; min-height: 0; display: flex; flex-direction: column; }
.vw-top { padding: 6px; display: flex; flex-direction: column; gap: 6px; flex: 0 0 auto; }
.vw-top .row { display: flex; gap: 6px; align-items: center; }
.vw-top .row .inp { flex: 1 1 auto; min-width: 0; }
.vw-top select.inp { flex: 0 0 auto; height: 22px; padding: 0 2px; color: inherit; font: inherit; }
.vw-top select.inp option { background: #141820; color: #dfe6ee; }
.vw-spacer { flex: 1 1 auto; }
.vw-msg { color: var(--sb-dim); min-height: 14px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.vw-filter { display: flex; align-items: center; gap: 6px; padding: 0 6px 4px; flex: 0 0 auto; }
.vw-filter .inp { flex: 1 1 auto; min-width: 0; }
.vw-filter-info { color: var(--sb-dim); white-space: nowrap; font-size: 11px; }
.vw-list { flex: 1 1 auto; min-height: 0; overflow-y: auto; padding: 0 4px 6px; }
.vw-row { position: relative; display: flex; align-items: center; gap: 2px; height: 26px; padding: 0 2px; border-radius: 3px; }
.vw-row:hover, .vw-row:focus-within { background: var(--sb-hover); }
.vw-row.active::before, .vw-card.active::before { content: ''; position: absolute; left: 0; top: 4px; bottom: 4px; width: 2px; background: var(--sb-accent); border-radius: 1px; z-index: 1; }
.vw-row.active .vw-name, .vw-card.active .vw-name { color: var(--sb-accent); }
.vw-grip { flex: 0 0 14px; width: 14px; height: 22px; display: flex; align-items: center; justify-content: center; color: #5d6878; cursor: grab;
  touch-action: none; user-select: none; font-size: 12px; letter-spacing: -2px; }
.vw-grip:hover { color: var(--sb-fg); }
.vw-num { flex: 0 0 18px; text-align: right; color: var(--sb-dim); font-size: 11px; font-variant-numeric: tabular-nums; padding-right: 2px; }
.vw-name { flex: 1 1 auto; min-width: 0; text-align: left; background: transparent; border: 0; padding: 3px 4px; cursor: pointer;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 600; border-radius: 3px; }
.vw-name:hover { color: var(--sb-accent); }
.vw-name:focus-visible, .vw-ico:focus-visible { outline: 1px solid var(--sb-accent); outline-offset: -1px; }
.vw-meta { flex: 0 1 auto; min-width: 0; max-width: 34%; color: var(--sb-dim); font-size: 11px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.vw-ico { flex: 0 0 24px; width: 24px; height: 22px; padding: 0; background: transparent; border: 1px solid transparent; border-radius: 3px;
  cursor: pointer; color: var(--sb-dim); font-size: 15px; line-height: 18px; }
.vw-ico:hover, .vw-ico[aria-expanded="true"] { color: var(--sb-fg); border-color: #3a4558; background: #1b2230; }
.vw-row .inp.vw-rename { flex: 1 1 auto; min-width: 0; height: 22px; }
.vw-row.drop-before, .vw-card.drop-before { box-shadow: inset 0 2px 0 var(--sb-accent); }
.vw-row.drop-after, .vw-card.drop-after { box-shadow: inset 0 -2px 0 var(--sb-accent); }
.vw-row.dragging, .vw-card.dragging { opacity: 0.45; }
.vw-list.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(124px, 1fr)); gap: 6px; padding: 0 6px 6px; align-content: start; }
.vw-card { position: relative; border: 1px solid var(--sb-line); border-radius: 4px; overflow: hidden; background: #0e1218; }
.vw-card:hover, .vw-card:focus-within { border-color: #3a4a66; }
.vw-card .vw-shot { display: block; width: 100%; padding: 0; border: 0; background: #1b2230; cursor: pointer; aspect-ratio: 16 / 10; }
.vw-card .vw-shot img { display: block; width: 100%; height: 100%; object-fit: cover; }
.vw-card .vw-cap { display: flex; align-items: center; gap: 2px; padding: 1px 2px 1px 4px; }
.vw-card .vw-name { padding: 2px 2px; font-size: 11px; }
.vw-card .vw-grip { position: absolute; left: 3px; top: 3px; background: rgba(14, 18, 24, 0.7); border-radius: 3px; height: 18px; }
.vw-card .vw-num { position: absolute; right: 4px; top: 3px; background: rgba(14, 18, 24, 0.7); border-radius: 3px; padding: 0 3px; flex: none; }
.vw-noshot { display: flex; align-items: center; justify-content: center; width: 100%; height: 100%; color: var(--sb-dim); font-size: 11px; }
.vw-peek { position: fixed; z-index: 900; pointer-events: none; background: #1a202b; color: var(--sb-fg, #dfe6ee); border: 1px solid #344055;
  border-radius: 5px; padding: 4px; box-shadow: 0 6px 20px rgba(0, 0, 0, 0.45); width: 170px; font: 11px/1.35 system-ui, -apple-system, 'Segoe UI', sans-serif; }
.vw-peek img { display: block; width: 160px; height: 100px; border-radius: 3px; background: #1b2230; }
.vw-peek .t { font-weight: 600; margin-top: 3px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.vw-peek .s { color: var(--sb-dim, #8d99a8); }
.btn.vw-play.on { background: #1f4a7a; border-color: #2d6aa8; }
.btn.vw-grid-btn { padding: 2px 5px; }
.btn.vw-grid-btn[aria-pressed="true"] { background: #243049; border-color: #3a4a66; }
@media (hover: none) { .vw-row { height: 34px; } .vw-ico { flex-basis: 32px; width: 32px; height: 30px; } .vw-grip { flex-basis: 22px; width: 22px; } }
`;

function ensureStyle(): void {
  if (document.getElementById(STYLE_ID)) return;
  const st = document.createElement('style');
  st.id = STYLE_ID;
  st.textContent = CSS;
  document.head.appendChild(st);
}

interface UiPrefs {
  grid: boolean;
  dwell: number;
}

function readPrefs(): UiPrefs {
  const def: UiPrefs = { grid: false, dwell: 4000 };
  try {
    const v = JSON.parse(window.localStorage.getItem(UI_KEY) ?? 'null') as Partial<UiPrefs> | null;
    if (v) return { grid: v.grid === true, dwell: typeof v.dwell === 'number' && v.dwell >= 500 ? v.dwell : def.dwell };
  } catch {
    /* ignore */
  }
  return def;
}

function writePrefs(p: UiPrefs): void {
  try {
    window.localStorage.setItem(UI_KEY, JSON.stringify(p));
  } catch {
    /* ignore */
  }
}

const GRID_ICON = '<svg viewBox="0 0 16 16" width="12" height="12" aria-hidden="true" fill="currentColor"><rect x="1" y="1" width="6" height="6" rx="1"/><rect x="9" y="1" width="6" height="6" rx="1"/><rect x="1" y="9" width="6" height="6" rx="1"/><rect x="9" y="9" width="6" height="6" rx="1"/></svg>';

const help = (key: string, title: string): Record<string, string> => ({ 'data-help-key': `Sidebar/${key}`, 'data-help-title': title });

export class ViewsPanel {
  readonly root: HTMLDivElement;
  private readonly nameInput: HTMLInputElement;
  private readonly playBtn: HTMLButtonElement;
  private readonly dwellSel: HTMLSelectElement;
  private readonly gridBtn: HTMLButtonElement;
  private readonly msg: HTMLDivElement;
  private readonly filterRow: HTMLDivElement;
  private readonly filterInput: HTMLInputElement;
  private readonly filterInfo: HTMLSpanElement;
  private readonly list: HTMLDivElement;
  private readonly fileInput: HTMLInputElement;
  private readonly peek: HTMLDivElement;
  private prefs: UiPrefs;
  private filter = '';
  private editing = -1;
  private drag: { from: number; to: number; pointer: number; el: HTMLElement } | null = null;

  constructor(private readonly host: ViewsHost) {
    ensureStyle();
    this.prefs = readPrefs();
    host.setDwellMs(this.prefs.dwell);
    this.root = el('div', 'vw');
    const top = el('div', 'vw-top');
    this.nameInput = el('input', 'inp', { type: 'text', placeholder: 'View name (optional)', 'aria-label': 'New view name', ...help('View name box', 'View name box') });
    const save = el('button', 'btn primary', { type: 'button', title: 'Save the camera, cuts, modes and selection as a view (Ctrl+Shift+S)', ...help('Save view', 'Save view') }, 'Save view');
    const row1 = el('div', 'row');
    row1.append(this.nameInput, save);

    this.playBtn = el('button', 'btn vw-play', { type: 'button', title: 'Step through the saved views', ...help('Play views', 'Play views') }, '▶ Play');
    this.dwellSel = el('select', 'inp', { 'aria-label': 'Time on each view', title: 'Time on each view while playing', ...help('View dwell time', 'View dwell time') });
    for (const ms of DWELL_CHOICES) {
      const o = el('option', '', { value: String(ms) }, `${ms / 1000} s`);
      this.dwellSel.append(o);
    }
    if (!DWELL_CHOICES.includes(this.prefs.dwell)) this.dwellSel.append(el('option', '', { value: String(this.prefs.dwell) }, `${this.prefs.dwell / 1000} s`));
    this.dwellSel.value = String(this.prefs.dwell);
    this.gridBtn = el('button', 'btn vw-grid-btn', { type: 'button', 'aria-pressed': String(this.prefs.grid), 'aria-label': 'Show thumbnails as a grid', title: 'Grid of thumbnails', ...help('View grid toggle', 'Grid toggle') });
    this.gridBtn.innerHTML = GRID_ICON;
    const exp = el('button', 'btn', { type: 'button', title: 'Download the views of this model as JSON', ...help('Export views', 'Export views') }, 'Export');
    const imp = el('button', 'btn', { type: 'button', title: 'Add views from a JSON file', ...help('Import views', 'Import views') }, 'Import');
    this.fileInput = el('input', '', { type: 'file', accept: 'application/json,.json' });
    this.fileInput.style.display = 'none';
    const row2 = el('div', 'row');
    row2.append(this.playBtn, this.dwellSel, el('span', 'vw-spacer'), this.gridBtn, exp, imp, this.fileInput);
    this.msg = el('div', 'vw-msg', { 'aria-live': 'polite' });
    top.append(row1, row2, this.msg);

    this.filterRow = el('div', 'vw-filter');
    this.filterInput = el('input', 'inp', { type: 'search', placeholder: 'Filter views', 'aria-label': 'Filter the views by name', ...help('View filter box', 'Filter views') });
    this.filterInfo = el('span', 'vw-filter-info');
    this.filterRow.append(this.filterInput, this.filterInfo);
    this.list = el('div', 'vw-list', { role: 'list', 'aria-label': 'Saved views' });
    this.root.append(top, this.filterRow, this.list);
    this.peek = el('div', 'vw-peek');
    this.peek.style.display = 'none';
    document.body.appendChild(this.peek);

    const doSave = (): void => {
      host.save(this.nameInput.value.trim());
      this.nameInput.value = '';
    };
    save.addEventListener('click', doSave);
    this.nameInput.addEventListener('keydown', (e) => {
      e.stopPropagation();
      if (e.key === 'Enter') doSave();
      else if (e.key === 'Escape') this.nameInput.blur();
    });
    this.playBtn.addEventListener('click', () => host.togglePlay());
    this.dwellSel.addEventListener('change', () => {
      this.prefs.dwell = Number(this.dwellSel.value);
      writePrefs(this.prefs);
      host.setDwellMs(this.prefs.dwell);
    });
    this.gridBtn.addEventListener('click', () => {
      this.prefs.grid = !this.prefs.grid;
      writePrefs(this.prefs);
      this.render();
    });
    exp.addEventListener('click', () => host.exportFile());
    imp.addEventListener('click', () => this.fileInput.click());
    this.fileInput.addEventListener('change', () => {
      const f = this.fileInput.files?.[0];
      if (f) host.importFile(f);
      this.fileInput.value = '';
    });

    const applyFilter = debounce(() => {
      this.filter = this.filterInput.value;
      this.render();
    }, 100);
    this.filterInput.addEventListener('input', applyFilter);
    this.filterInput.addEventListener('keydown', (e) => {
      e.stopPropagation();
      if (e.key === 'Escape' && this.filterInput.value) {
        this.filterInput.value = '';
        this.filter = '';
        this.render();
      } else if (e.key === 'Escape') this.filterInput.blur();
      else if (e.key === 'ArrowDown') {
        e.preventDefault();
        this.focusPos(0);
      } else if (e.key === 'Enter') {
        const first = this.list.querySelector<HTMLElement>('[data-i]');
        if (first) host.restore(Number(first.dataset['i']));
      }
    });

    this.list.addEventListener('click', (e) => this.onClick(e));
    this.list.addEventListener('keydown', (e) => this.onKey(e));
    this.list.addEventListener('pointerdown', (e) => this.onGripDown(e));
    this.list.addEventListener('pointerover', (e) => this.onHover(e));
    this.list.addEventListener('pointerleave', () => this.hidePeek());
    this.list.addEventListener('scroll', () => this.hidePeek());
    this.list.addEventListener('focusout', (e) => {
      const t = e.target as HTMLElement;
      if (t.classList.contains('vw-rename') && this.editing >= 0) this.finishRename(t as HTMLInputElement, true);
    });
  }

  say(text: string): void {
    this.msg.textContent = text;
    this.msg.title = text;
  }

  get grid(): boolean {
    return this.prefs.grid;
  }

  /** Start renaming view `i` (used by the menu). */
  startRename(i: number): void {
    this.editing = i;
    if (this.prefs.grid) {
      this.prefs.grid = false; // rename happens in a row
      writePrefs(this.prefs);
    }
    this.render();
  }

  render(): void {
    const views = this.host.views();
    const active = this.host.activeId();
    const playing = this.host.playing();
    this.playBtn.textContent = playing ? '■ Stop' : '▶ Play';
    this.playBtn.classList.toggle('on', playing);
    this.playBtn.disabled = views.length < 1;
    this.playBtn.setAttribute('aria-pressed', String(playing));
    this.gridBtn.setAttribute('aria-pressed', String(this.prefs.grid));
    this.list.classList.toggle('grid', this.prefs.grid);
    this.filterRow.style.display = views.length > 0 ? '' : 'none';
    this.hidePeek();
    if (views.length === 0) {
      this.list.innerHTML = '<div class="tv-empty">No views yet. Set up the camera, cuts and modes, then press Save view.</div>';
      this.filterInfo.textContent = '';
      return;
    }
    const shown = filterViews(views, this.filter);
    if (this.editing >= 0 && !shown.includes(this.editing)) shown.push(this.editing);
    const html: string[] = [];
    for (const i of shown) {
      const v = views[i]!;
      const cls = v.id === active ? ' active' : '';
      const sum = viewSummary(v);
      const grip = `<span class="vw-grip" data-grip="1" title="Drag to reorder (Alt+Up, Alt+Down)" aria-hidden="true" data-help-key="Sidebar/View drag handle" data-help-title="Drag handle">⋮⋮</span>`;
      const menu = `<button type="button" class="vw-ico" data-act="menu" aria-haspopup="menu" aria-expanded="false" aria-label="More actions for ${esc(v.name)}" title="More actions" data-help-key="Sidebar/View menu" data-help-title="View menu">⋯</button>`;
      if (this.prefs.grid) {
        const img = v.thumb ? `<img src="${v.thumb}" alt="" width="160" height="100" loading="lazy">` : '<span class="vw-noshot">no picture</span>';
        html.push(
          `<div class="vw-card${cls}" role="listitem" data-i="${i}" title="${esc(sum)}">` +
            `<button type="button" class="vw-shot" data-act="restore" aria-label="Restore ${esc(v.name)}" data-help-key="Sidebar/Restore view" data-help-title="Restore view">${img}</button>` +
            `${grip}<span class="vw-num">${i + 1}</span>` +
            `<div class="vw-cap"><button type="button" class="vw-name" data-act="restore" title="${esc(v.name)}" data-help-key="Sidebar/Restore view" data-help-title="Restore view">${esc(v.name)}</button>${menu}</div>` +
            `</div>`,
        );
        continue;
      }
      const name =
        this.editing === i
          ? `<input class="inp vw-rename" type="text" value="${esc(v.name)}" aria-label="Rename view">`
          : `<button type="button" class="vw-name" data-act="restore" title="${esc(v.name)}: restore" data-help-key="Sidebar/Restore view" data-help-title="Restore view">${esc(v.name)}</button>`;
      html.push(
        `<div class="vw-row${cls}" role="listitem" data-i="${i}">${grip}<span class="vw-num">${i + 1}</span>${name}` +
          `<span class="vw-meta" title="${esc(sum)}">${esc(sum)}</span>${menu}</div>`,
      );
    }
    this.list.innerHTML = shown.length ? html.join('') : '<div class="tv-empty">No view matches the filter.</div>';
    this.filterInfo.textContent = this.filter.trim() ? `${shown.length} of ${views.length}` : `${views.length}`;
    const inp = this.list.querySelector<HTMLInputElement>('.vw-rename');
    if (inp) {
      inp.focus();
      inp.select();
    }
  }

  private items(): HTMLElement[] {
    return Array.from(this.list.querySelectorAll<HTMLElement>('[data-i]'));
  }

  private focusPos(pos: number): void {
    const items = this.items();
    if (!items.length) return;
    const it = items[Math.max(0, Math.min(items.length - 1, pos))]!;
    it.querySelector<HTMLElement>('.vw-name')?.focus();
    it.scrollIntoView({ block: 'nearest' });
  }

  focusView(i: number): void {
    const it = this.items().find((x) => Number(x.dataset['i']) === i);
    it?.querySelector<HTMLElement>('.vw-name')?.focus();
  }

  private onClick(e: MouseEvent): void {
    const t = e.target as HTMLElement;
    const btn = t.closest<HTMLElement>('[data-act]');
    const item = t.closest<HTMLElement>('[data-i]');
    if (!btn || !item) return;
    const i = Number(item.dataset['i']);
    if (btn.dataset['act'] === 'restore') this.host.restore(i);
    else if (btn.dataset['act'] === 'menu') this.openRowMenu(i, btn);
  }

  private openRowMenu(i: number, btn: HTMLElement): void {
    const v = this.host.views()[i];
    if (!v) return;
    this.hidePeek();
    const items: MenuItem[] = [
      { label: 'Update from current', act: 'update', help: 'Sidebar/Update view', title: 'Replace this view with the current camera and state' },
      { label: 'Rename', act: 'rename', help: 'Sidebar/Rename view' },
      { label: 'Duplicate', act: 'duplicate', help: 'Sidebar/Duplicate view' },
      { label: 'Copy link', act: 'link', help: 'Sidebar/Copy view link', title: 'Copy a link that opens this view' },
      {
        label: 'Save as BCF topic',
        act: 'bcf',
        help: 'Sidebar/View as BCF topic',
        disabled: !this.host.canBcf(),
        title: this.host.canBcf() ? 'Restore the view and create a BCF topic from it' : 'The BCF tool is not in this build',
      },
      { label: 'Delete', act: 'delete', danger: true, confirm: 'Click again to delete', help: 'Sidebar/Delete view' },
    ];
    btn.setAttribute('aria-expanded', 'true');
    openMenu({
      at: btn,
      items,
      heading: v.name,
      label: `Actions for view ${v.name}`,
      onPick: (act) => {
        switch (act) {
          case 'update':
            this.host.update(i);
            break;
          case 'rename':
            this.startRename(i);
            break;
          case 'duplicate':
            this.host.duplicate(i);
            break;
          case 'link':
            this.host.copyLink(i);
            break;
          case 'bcf':
            this.host.bcf(i);
            break;
          case 'delete':
            this.host.remove(i);
            break;
        }
      },
      onClose: () => btn.setAttribute('aria-expanded', 'false'),
    });
  }

  private finishRename(inp: HTMLInputElement, commit: boolean): void {
    const i = this.editing;
    this.editing = -1;
    const name = inp.value.trim();
    if (commit && name && this.host.views()[i] && name !== this.host.views()[i]!.name) this.host.rename(i, name);
    else this.render();
    this.focusView(i);
  }

  private onKey(e: KeyboardEvent): void {
    const t = e.target as HTMLElement;
    if (t.classList.contains('vw-rename')) {
      e.stopPropagation();
      if (e.key === 'Enter') this.finishRename(t as HTMLInputElement, true);
      else if (e.key === 'Escape') this.finishRename(t as HTMLInputElement, false);
      return;
    }
    const item = t.closest<HTMLElement>('[data-i]');
    if (!item) return;
    const items = this.items();
    const pos = items.indexOf(item);
    const i = Number(item.dataset['i']);
    let handled = true;
    if (e.altKey && (e.key === 'ArrowUp' || e.key === 'ArrowDown')) {
      const to = i + (e.key === 'ArrowUp' ? -1 : 1);
      if (to >= 0 && to < this.host.views().length) {
        this.host.move(i, to);
        this.focusView(to);
      }
    } else if (e.key === 'ArrowDown') this.focusPos(pos + 1);
    else if (e.key === 'ArrowUp') {
      if (pos === 0) this.filterInput.focus();
      else this.focusPos(pos - 1);
    } else if (e.key === 'Home') this.focusPos(0);
    else if (e.key === 'End') this.focusPos(items.length - 1);
    else if (e.key === 'F2') this.startRename(i);
    else if (e.key === 'Delete') {
      const b = item.querySelector<HTMLElement>('[data-act="menu"]');
      if (b) this.openRowMenu(i, b);
    } else handled = false;
    if (handled) {
      e.preventDefault();
      e.stopPropagation();
    } else if (e.key === 'Enter' || e.key === ' ') e.stopPropagation();
  }

  // ---------------------------------------------------------------- drag to reorder

  private onGripDown(e: PointerEvent): void {
    const t = e.target as HTMLElement;
    if (!t.closest('[data-grip]') || e.button !== 0) return;
    const item = t.closest<HTMLElement>('[data-i]');
    if (!item) return;
    e.preventDefault();
    closeMenu();
    this.hidePeek();
    const from = Number(item.dataset['i']);
    this.drag = { from, to: from, pointer: e.pointerId, el: item };
    item.classList.add('dragging');
    const grip = t.closest<HTMLElement>('[data-grip]')!;
    try {
      grip.setPointerCapture(e.pointerId);
    } catch {
      /* synthetic events in tests */
    }
    const move = (ev: PointerEvent): void => this.onGripMove(ev);
    const up = (ev: PointerEvent): void => {
      grip.removeEventListener('pointermove', move);
      grip.removeEventListener('pointerup', up);
      grip.removeEventListener('pointercancel', up);
      this.onGripUp(ev.type === 'pointerup');
    };
    grip.addEventListener('pointermove', move);
    grip.addEventListener('pointerup', up);
    grip.addEventListener('pointercancel', up);
  }

  private onGripMove(e: PointerEvent): void {
    const d = this.drag;
    if (!d || e.pointerId !== d.pointer) return;
    const items = this.items();
    for (const it of items) it.classList.remove('drop-before', 'drop-after');
    // Nearest item centre to the pointer; before or after it by the side of the centre (grid: by x within a row).
    let best: HTMLElement | null = null;
    let bestD = Infinity;
    for (const it of items) {
      const r = it.getBoundingClientRect();
      const dx = e.clientX < r.left ? r.left - e.clientX : e.clientX > r.right ? e.clientX - r.right : 0;
      const dy = e.clientY < r.top ? r.top - e.clientY : e.clientY > r.bottom ? e.clientY - r.bottom : 0;
      const dist = dx * dx + dy * dy;
      if (dist < bestD) {
        bestD = dist;
        best = it;
      }
    }
    if (!best) return;
    const r = best.getBoundingClientRect();
    const after = this.prefs.grid ? e.clientX > r.left + r.width / 2 : e.clientY > r.top + r.height / 2;
    const bi = Number(best.dataset['i']);
    let to = after ? bi + 1 : bi;
    if (to > d.from) to--; // index after removing the dragged view
    d.to = to;
    if (bi !== d.from) best.classList.add(after ? 'drop-after' : 'drop-before');
    // Auto-scroll near the list edges.
    const lr = this.list.getBoundingClientRect();
    if (e.clientY < lr.top + 16) this.list.scrollTop -= 8;
    else if (e.clientY > lr.bottom - 16) this.list.scrollTop += 8;
  }

  private onGripUp(commit: boolean): void {
    const d = this.drag;
    this.drag = null;
    if (!d) return;
    for (const it of this.items()) it.classList.remove('drop-before', 'drop-after', 'dragging');
    if (commit && d.to !== d.from) this.host.move(d.from, d.to);
  }

  // ---------------------------------------------------------------- hover thumbnail

  private onHover(e: PointerEvent): void {
    if (this.prefs.grid || this.drag || e.pointerType === 'touch') return;
    const t = e.target as HTMLElement;
    const row = t.closest<HTMLElement>('.vw-row');
    if (!row || row.querySelector('.vw-rename')) {
      this.hidePeek();
      return;
    }
    const v = this.host.views()[Number(row.dataset['i'])];
    if (!v) return;
    const r = row.getBoundingClientRect();
    const img = v.thumb ? `<img src="${v.thumb}" alt="" width="160" height="100">` : '';
    this.peek.innerHTML = `${img}<div class="t">${esc(v.name)}</div><div class="s">${esc(viewSummary(v) || 'default look')}</div>`;
    this.peek.style.display = '';
    const sb = this.root.closest('#sidebar')?.getBoundingClientRect();
    const left = Math.min((sb ? sb.right : r.right) + 6, window.innerWidth - 176);
    const top = Math.max(4, Math.min(r.top - 20, window.innerHeight - this.peek.offsetHeight - 4));
    this.peek.style.left = `${Math.max(4, left)}px`;
    this.peek.style.top = `${top}px`;
  }

  hidePeek(): void {
    this.peek.style.display = 'none';
  }
}
