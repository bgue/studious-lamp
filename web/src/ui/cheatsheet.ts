// Cheat sheet overlay: every registered action, grouped, with its current key bindings. Opens on `?` and F1.

import { el } from './dom';
import { ensureKeyStyles, groupedActions, renderChords } from './keymapView';
import type { Keymap, Overlay } from '../input/keymap';
import { formatChord } from '../input/keymap';

export class CheatSheet implements Overlay {
  private root: HTMLElement | null = null;
  private body: HTMLElement | null = null;
  private search: HTMLInputElement | null = null;
  private unsub: (() => void) | null = null;
  private readonly onKey = (e: KeyboardEvent): void => {
    if (e.key === 'Escape') {
      e.preventDefault();
      e.stopPropagation();
      this.close();
    }
  };

  constructor(private readonly km: Keymap, private readonly onEdit?: () => void) {
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
    const back = el('div', 'kx-backdrop', { role: 'dialog', 'aria-label': 'Keyboard shortcuts' });
    const panel = el('div', 'kx-panel kx-sheet');
    const head = el('div', 'kx-head');
    this.search = el('input', 'kx-input', { type: 'search', placeholder: 'Search shortcuts', 'aria-label': 'Search shortcuts' });
    const edit = el('button', 'kx-btn', { type: 'button' }, 'Edit shortcuts');
    const close = el('button', 'kx-btn', { type: 'button', 'aria-label': 'Close' }, 'Close');
    head.append(el('span', 'kx-title', {}, 'Keyboard shortcuts'), this.search, edit, close);
    this.body = el('div', 'kx-body');
    panel.append(head, this.body, el('div', 'kx-foot', {}, 'Esc or a click outside closes this list. Ctrl+K opens the search bar. Ctrl+Shift+K opens the command palette. Hold Ctrl for slow camera moves.'));
    back.append(panel);
    document.body.appendChild(back);
    this.root = back;
    back.addEventListener('mousedown', (e) => {
      if (e.target === back) this.close();
    });
    close.addEventListener('click', () => this.close());
    edit.addEventListener('click', () => {
      this.close();
      this.onEdit?.();
    });
    this.search.addEventListener('input', () => this.render());
    window.addEventListener('keydown', this.onKey, true);
    this.unsub = this.km.onChange(() => this.render());
    this.render();
    this.search.focus();
  }

  close(): void {
    if (!this.root) return;
    window.removeEventListener('keydown', this.onKey, true);
    this.unsub?.();
    this.unsub = null;
    this.root.remove();
    this.root = null;
    this.body = null;
  }

  private render(): void {
    const body = this.body;
    if (!body) return;
    body.textContent = '';
    const q = (this.search?.value ?? '').trim().toLowerCase();
    const bad = this.km.conflictKeys();
    const cols = el('div', 'kx-cols');
    let shown = 0;
    for (const g of groupedActions()) {
      const rows = g.actions.filter((a) => {
        if (!q) return true;
        const text = `${a.label} ${a.id} ${g.group} ${a.description ?? ''} ${this.km.bindingsOf(a.id).map(formatChord).join(' ')}`.toLowerCase();
        return q.split(/\s+/).every((w) => text.includes(w));
      });
      if (rows.length === 0) continue;
      const sec = el('section', 'kx-group');
      sec.append(el('h3', '', {}, g.group));
      for (const a of rows) {
        const row = el('div', 'kx-row');
        const label = el('span', 'kx-label', {}, a.label);
        if (a.description) label.title = a.description;
        const keys = el('span', 'kx-keys');
        renderChords(keys, this.km.bindingsOf(a.id), bad);
        row.append(label, keys);
        sec.append(row);
        shown++;
      }
      cols.append(sec);
    }
    if (shown === 0) body.append(el('div', 'kx-dim', {}, 'No shortcut matches.'));
    else body.append(cols);
  }
}
