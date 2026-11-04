// Keyboard UI shared by the cheat sheet, the command palette and the shortcut editor: the stylesheet (injected from
// this module, index.html is not edited), the toast, and the shortcut editor modal.

import { el } from './dom';
import { eventToChord, formatChord } from '../input/keymap';
import type { Keymap, Overlay } from '../input/keymap';
import { getActions } from '../input/actions';

const STYLE_ID = 'xray-keys-style';

const CSS = `
.kx-backdrop { position: fixed; inset: 0; z-index: 60; background: rgba(6,8,12,0.55); display: flex; align-items: flex-start; justify-content: center; padding: 8vh 16px 16px; }
.kx-panel { background: var(--sb-bg, #141820); color: var(--sb-fg, #dfe6ee); border: 1px solid var(--sb-line, #262d3a); border-radius: 8px;
  box-shadow: 0 18px 60px rgba(0,0,0,0.55); font: 12px/1.4 system-ui, sans-serif; max-height: 82vh; display: flex; flex-direction: column; min-width: 0; }
.kx-head { display: flex; gap: 8px; align-items: center; padding: 10px 12px; border-bottom: 1px solid var(--sb-line, #262d3a); flex: 0 0 auto; }
.kx-title { font-weight: 600; font-size: 13px; flex: 0 0 auto; }
.kx-head .kx-grow { flex: 1 1 auto; }
.kx-input { flex: 1 1 auto; min-width: 0; background: #0e1218; color: inherit; border: 1px solid var(--sb-line, #262d3a); border-radius: 4px; padding: 5px 8px; font: inherit; outline: none; }
.kx-input:focus { border-color: var(--sb-accent, #3b9cff); }
.kx-btn { background: transparent; color: inherit; border: 1px solid var(--sb-line, #262d3a); border-radius: 4px; padding: 4px 9px; font: inherit; cursor: pointer; }
.kx-btn:hover { background: var(--sb-hover, #1c2230); border-color: #3a4558; }
.kx-body { overflow: auto; padding: 8px 12px 12px; flex: 1 1 auto; min-height: 0; }
.kx-foot { padding: 6px 12px; color: var(--sb-dim, #8d99a8); border-top: 1px solid var(--sb-line, #262d3a); flex: 0 0 auto; }
.kx-dim { color: var(--sb-dim, #8d99a8); }
kbd.kx-key { display: inline-block; min-width: 18px; padding: 1px 6px; margin: 0 2px 0 0; text-align: center; border: 1px solid #3a4558; border-bottom-width: 2px;
  border-radius: 4px; background: #10141b; color: #dfe6ee; font: 11px ui-monospace, Menlo, Consolas, monospace; white-space: nowrap; }
kbd.kx-key.kx-bad { border-color: #d9534f; color: #ff8a84; }
.kx-sheet { width: min(980px, 100%); }
.kx-cols { columns: 3 280px; column-gap: 22px; }
.kx-group { break-inside: avoid; margin-bottom: 12px; }
.kx-group h3 { margin: 0 0 4px; font-size: 10px; letter-spacing: 0.07em; text-transform: uppercase; color: var(--sb-dim, #8d99a8); font-weight: 600; }
.kx-row { display: flex; align-items: baseline; gap: 8px; padding: 2px 0; }
.kx-row .kx-label { flex: 1 1 auto; min-width: 0; }
.kx-row .kx-keys { flex: 0 0 auto; text-align: right; }
.kx-palette { width: min(640px, 100%); }
.kx-list { list-style: none; margin: 0; padding: 4px; overflow: auto; flex: 1 1 auto; min-height: 0; }
.kx-item { display: flex; align-items: baseline; gap: 8px; padding: 5px 8px; border-radius: 4px; cursor: pointer; }
.kx-item.kx-sel { background: var(--sb-sel, #1f4a7a); }
.kx-item .kx-label { flex: 1 1 auto; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.kx-item .kx-path { color: var(--sb-dim, #8d99a8); font-size: 11px; flex: 0 1 auto; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 40%; }
.kx-item mark { background: transparent; color: #ffd479; font-weight: 600; }
.kx-edit { width: min(860px, 100%); }
.kx-edit table { width: 100%; border-collapse: collapse; }
.kx-edit td { padding: 3px 6px 3px 0; vertical-align: middle; border-bottom: 1px solid #1a202b; }
.kx-edit tr.kx-grouprow td { padding-top: 10px; font-size: 10px; letter-spacing: 0.07em; text-transform: uppercase; color: var(--sb-dim, #8d99a8); border-bottom: 0; }
.kx-cell { background: #10141b; border: 1px solid #3a4558; border-radius: 4px; color: inherit; font: 11px ui-monospace, Menlo, Consolas, monospace; padding: 2px 7px; margin-right: 4px; cursor: pointer; }
.kx-cell:hover { border-color: var(--sb-accent, #3b9cff); }
.kx-cell.kx-bad { border-color: #d9534f; color: #ff8a84; background: #2a1618; }
.kx-cell.kx-rec { border-color: #ffd479; color: #ffd479; }
.kx-cell.kx-add { opacity: 0.6; }
.kx-cell.kx-changed { box-shadow: inset 0 0 0 1px #3b9cff; }
.kx-conf { margin: 0 0 8px; padding: 6px 8px; border: 1px solid #7a2b1f; background: #2a1618; border-radius: 4px; color: #ffb3ad; }
.kx-toast { position: fixed; left: 50%; bottom: 56px; transform: translateX(-50%); z-index: 70; background: rgba(20,24,32,0.94); color: #dfe6ee; border: 1px solid #262d3a;
  padding: 6px 12px; border-radius: 6px; font: 12px system-ui, sans-serif; pointer-events: none; opacity: 0; transition: opacity 0.15s; max-width: 70vw; text-align: center; }
.kx-toast.kx-on { opacity: 1; }
@media (max-width: 700px) { .kx-backdrop { padding-top: 2vh; } .kx-item .kx-path { display: none; } }
`;

/** Add the keyboard UI stylesheet once. */
export function ensureKeyStyles(): void {
  if (typeof document === 'undefined' || document.getElementById(STYLE_ID)) return;
  const s = document.createElement('style');
  s.id = STYLE_ID;
  s.textContent = CSS;
  document.head.appendChild(s);
}

let toastEl: HTMLDivElement | null = null;
let toastTimer: ReturnType<typeof setTimeout> | null = null;

/** A small message at the bottom of the screen for 1.4 s. */
export function showToast(text: string, ms = 1400): void {
  if (typeof document === 'undefined') return;
  ensureKeyStyles();
  if (!toastEl) {
    toastEl = document.createElement('div');
    toastEl.className = 'kx-toast';
    toastEl.setAttribute('role', 'status');
    document.body.appendChild(toastEl);
  }
  toastEl.textContent = text;
  toastEl.classList.add('kx-on');
  if (toastTimer) clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toastEl?.classList.remove('kx-on'), ms);
}

/** Render chords as <kbd> elements into `host`. */
export function renderChords(host: HTMLElement, chords: readonly string[], bad?: ReadonlySet<string>): void {
  host.textContent = '';
  if (chords.length === 0) {
    host.append(el('span', 'kx-dim', {}, 'unbound'));
    return;
  }
  for (const c of chords) {
    const k = el('kbd', 'kx-key', {}, formatChord(c));
    if (bad?.has(c.toLowerCase())) k.classList.add('kx-bad');
    host.append(k);
  }
}

/** Group order of the cheat sheet and the editor. Unknown groups follow, before Other. */
export const GROUP_ORDER = ['Navigation', 'Views', 'Selection', 'Visibility', 'Modes', 'Panels', 'Presets', 'Other'];

export function groupedActions(): Array<{ group: string; actions: ReturnType<typeof getActions> }> {
  const by = new Map<string, ReturnType<typeof getActions>>();
  for (const a of getActions()) {
    const g = a.group || 'Other';
    const l = by.get(g) ?? [];
    l.push(a);
    by.set(g, l);
  }
  const known = GROUP_ORDER.filter((g) => by.has(g) && g !== 'Other');
  const extra = [...by.keys()].filter((g) => !GROUP_ORDER.includes(g)).sort();
  const order = [...known, ...extra, ...(by.has('Other') ? ['Other'] : [])];
  return order.map((group) => ({ group, actions: by.get(group)! }));
}

// ---------------------------------------------------------------------------- shortcut editor

export class KeymapEditor implements Overlay {
  private root: HTMLElement | null = null;
  private body: HTMLElement | null = null;
  private filter: HTMLInputElement | null = null;
  private recording: { id: string; index: number; cell: HTMLElement } | null = null;
  private unsub: (() => void) | null = null;
  private readonly onKey = (e: KeyboardEvent): void => this.handleKey(e);

  constructor(private readonly km: Keymap) {
    km.registerOverlay(this);
  }

  isOpen(): boolean {
    return this.root !== null;
  }

  open(): void {
    if (this.root) return;
    ensureKeyStyles();
    const back = el('div', 'kx-backdrop', { role: 'dialog', 'aria-label': 'Edit shortcuts' });
    const panel = el('div', 'kx-panel kx-edit');
    const head = el('div', 'kx-head');
    this.filter = el('input', 'kx-input', { type: 'search', placeholder: 'Filter actions', 'aria-label': 'Filter actions' });
    const exportBtn = el('button', 'kx-btn', { type: 'button' }, 'Export JSON');
    const importBtn = el('button', 'kx-btn', { type: 'button' }, 'Import JSON');
    const resetBtn = el('button', 'kx-btn', { type: 'button' }, 'Reset all');
    const closeBtn = el('button', 'kx-btn', { type: 'button', 'aria-label': 'Close' }, 'Close');
    const file = el('input', '', { type: 'file', accept: 'application/json,.json' });
    file.style.display = 'none';
    head.append(el('span', 'kx-title', {}, 'Edit shortcuts'), this.filter, exportBtn, importBtn, resetBtn, closeBtn, file);
    this.body = el('div', 'kx-body');
    const foot = el('div', 'kx-foot', {}, 'Click a key cell, then press the new keys. Backspace removes it, Escape cancels. Red cells share a chord with another action.');
    panel.append(head, this.body, foot);
    back.append(panel);
    document.body.appendChild(back);
    this.root = back;

    back.addEventListener('mousedown', (e) => {
      if (e.target === back) this.close();
    });
    closeBtn.addEventListener('click', () => this.close());
    resetBtn.addEventListener('click', () => {
      this.km.resetAll();
      showToast('Shortcuts reset to the defaults');
    });
    exportBtn.addEventListener('click', () => {
      const blob = new Blob([this.km.exportJson()], { type: 'application/json' });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = 'xray-keymap.json';
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    });
    importBtn.addEventListener('click', () => file.click());
    file.addEventListener('change', () => {
      const f = file.files?.[0];
      if (!f) return;
      void f.text().then((t) => {
        const r = this.km.importJson(t);
        showToast(r.ok ? `Imported ${r.applied} shortcut${r.applied === 1 ? '' : 's'}${r.bad.length ? `, ${r.bad.length} ignored` : ''}` : `Import failed: ${r.bad[0] ?? 'invalid file'}`, 3000);
      });
      file.value = '';
    });
    this.filter.addEventListener('input', () => this.render());
    window.addEventListener('keydown', this.onKey, true);
    this.unsub = this.km.onChange(() => {
      if (!this.recording) this.render();
    });
    this.render();
    this.filter.focus();
  }

  close(): void {
    if (!this.root) return;
    window.removeEventListener('keydown', this.onKey, true);
    this.unsub?.();
    this.unsub = null;
    this.root.remove();
    this.root = null;
    this.body = null;
    this.recording = null;
  }

  private render(): void {
    const body = this.body;
    if (!body) return;
    const scroll = body.scrollTop;
    body.textContent = '';
    const bad = this.km.conflictKeys();
    const conflicts = this.km.conflicts();
    if (conflicts.length) {
      const ids = new Map(getActions().map((a) => [a.id, a.label]));
      const box = el('div', 'kx-conf');
      box.append(el('strong', '', {}, `${conflicts.length} conflict${conflicts.length === 1 ? '' : 's'}: `));
      box.append(document.createTextNode(conflicts.map((c) => `${formatChord(c.chord)} is used by ${c.ids.map((i) => ids.get(i) ?? i).join(' and ')}`).join('; ')));
      body.append(box);
    }
    const q = (this.filter?.value ?? '').trim().toLowerCase();
    const table = el('table');
    for (const g of groupedActions()) {
      const rows = g.actions.filter((a) => !q || `${a.label} ${a.id} ${g.group} ${this.km.bindingsOf(a.id).map(formatChord).join(' ')}`.toLowerCase().includes(q));
      if (rows.length === 0) continue;
      const gr = el('tr', 'kx-grouprow');
      gr.append(el('td', '', { colspan: '3' }, g.group));
      table.append(gr);
      for (const a of rows) {
        const tr = el('tr');
        const name = el('td', '', {}, a.label);
        name.title = a.id;
        const cells = el('td');
        const chords = this.km.bindingsOf(a.id);
        chords.forEach((c, i) => {
          const b = el('button', 'kx-cell', { type: 'button', 'data-action': a.id, 'data-index': String(i) }, formatChord(c));
          if (bad.has(c.toLowerCase())) b.classList.add('kx-bad');
          if (this.km.isOverridden(a.id)) b.classList.add('kx-changed');
          b.addEventListener('click', () => this.startRecording(a.id, i, b));
          cells.append(b);
        });
        const add = el('button', 'kx-cell kx-add', { type: 'button', 'data-action': a.id, 'data-index': String(chords.length), title: 'Add a shortcut' }, chords.length ? '+' : 'unbound (click to set)');
        add.addEventListener('click', () => this.startRecording(a.id, chords.length, add));
        cells.append(add);
        const reset = el('td');
        if (this.km.isOverridden(a.id)) {
          const rb = el('button', 'kx-btn', { type: 'button', title: 'Back to the default' }, 'Reset');
          rb.addEventListener('click', () => this.km.resetBinding(a.id));
          reset.append(rb);
        }
        tr.append(name, cells, reset);
        table.append(tr);
      }
    }
    body.append(table);
    body.scrollTop = scroll;
  }

  private startRecording(id: string, index: number, cell: HTMLElement): void {
    if (this.recording) this.recording.cell.classList.remove('kx-rec');
    this.recording = { id, index, cell };
    cell.classList.add('kx-rec');
    cell.textContent = 'press keys...';
  }

  private handleKey(e: KeyboardEvent): void {
    if (!this.root) return;
    const rec = this.recording;
    if (!rec) {
      if (e.key === 'Escape') {
        e.preventDefault();
        e.stopPropagation();
        this.close();
      }
      return; // typing in the filter field and tabbing between cells work as usual
    }
    e.preventDefault();
    e.stopPropagation();
    if (e.repeat) return;
    if (e.key === 'Escape') {
      this.recording = null;
      this.render();
      return;
    }
    const chords = this.km.bindingsOf(rec.id);
    if (e.key === 'Backspace' && !e.ctrlKey && !e.altKey && !e.metaKey && !e.shiftKey) {
      chords.splice(rec.index, 1);
      this.recording = null;
      this.km.setBinding(rec.id, chords);
      this.render();
      return;
    }
    const chord = eventToChord(e);
    if (!chord) return; // a bare modifier: wait for the key
    if (rec.index >= chords.length) chords.push(chord);
    else chords[rec.index] = chord;
    this.recording = null;
    this.km.setBinding(rec.id, chords);
    this.render();
  }
}
