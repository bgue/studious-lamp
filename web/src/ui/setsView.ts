// DOM renderer for the "Sets" tab: a filterable one-line-per-set list of named selection sets (static or criteria),
// "save current selection as", "new criteria set", and JSON import/export. Persistence and id mapping live in
// ../selectionSets; criteria queries in ../query.
//
// Each row: [funnel for criteria sets] name (click: select and frame) · count · + (add to the selection) · ⋯ (menu:
// Update or Re-evaluate, Rename, Edit criteria, Duplicate, Delete with a second click to confirm).
// Keyboard: Up/Down/Home/End move between rows, Enter/Space on ⋯ opens the menu, Escape closes it.

import type { ElementId, SceneModel } from '../types';
import {
  addCriteriaSet,
  addSet,
  duplicateSet,
  exportSets,
  globalIdsToIds,
  idsToGlobalIds,
  isCriteria,
  loadOrSeed,
  mergeImported,
  parseImport,
  removeSet,
  renameSet,
  saveSets,
  setQuery,
  updateSet,
} from '../selectionSets';
import type { SelectionSet, StorageLike } from '../selectionSets';
import { modelTable, runQuery } from '../query';
import { CriteriaEditor } from './criteriaEditor';
import { debounce, el, esc } from './dom';
import { closeMenu, openMenu } from './popupMenu';
import type { MenuItem } from './popupMenu';

export interface SetsHost {
  selection(): ElementId[];
  select(ids: ElementId[], additive: boolean): void;
  /** Frame the camera on these elements. */
  frame(ids: ElementId[]): void;
}

const STYLE_ID = 'xray-sets-style';
const CSS = `
.sets-filter { display: flex; align-items: center; gap: 6px; padding: 0 6px 4px; flex: 0 0 auto; }
.sets-filter .inp { flex: 1 1 auto; min-width: 0; }
.sets-filter-info { color: var(--sb-dim); white-space: nowrap; font-size: 11px; }
.sets-list { padding: 0 4px 6px; }
.set-row { display: flex; align-items: center; gap: 2px; height: 26px; padding: 0 2px 0 4px; border-radius: 3px;
  content-visibility: auto; contain-intrinsic-size: auto 26px; }
.set-row:hover, .set-row:focus-within { background: var(--sb-hover); }
.set-row .set-badge { flex: 0 0 14px; width: 14px; height: 14px; color: #e0b252; display: flex; align-items: center; justify-content: center; }
.set-row .set-badge svg { width: 11px; height: 11px; fill: currentColor; }
.set-row .set-name { flex: 1 1 auto; min-width: 0; text-align: left; background: transparent; border: 0; padding: 3px 4px; cursor: pointer;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 600; border-radius: 3px; }
.set-row .set-name:hover { color: var(--sb-accent); }
.set-row .set-name:focus-visible, .set-row .set-ico:focus-visible { outline: 1px solid var(--sb-accent); outline-offset: -1px; }
.set-row .cnt { flex: 0 0 auto; color: var(--sb-dim); font-size: 11px; padding: 0 4px; font-variant-numeric: tabular-nums; }
.set-row .cnt.part { color: #e0b252; }
.set-row .set-ico { flex: 0 0 24px; width: 24px; height: 22px; padding: 0; background: transparent; border: 1px solid transparent; border-radius: 3px;
  cursor: pointer; color: var(--sb-dim); font-size: 15px; line-height: 18px; }
.set-row .set-ico:hover, .set-row .set-ico[aria-expanded="true"] { color: var(--sb-fg); border-color: #3a4558; background: #1b2230; }
.set-row .inp.rename-inp { flex: 1 1 auto; min-width: 0; height: 22px; }
.sets-pane-editor { flex: 1 1 auto; min-height: 0; overflow-y: auto; }
@media (hover: none) { .set-row { height: 34px; contain-intrinsic-size: auto 34px; } .set-row .set-ico { flex-basis: 32px; width: 32px; height: 30px; } }
`;

function ensureStyle(): void {
  if (document.getElementById(STYLE_ID)) return;
  const st = document.createElement('style');
  st.id = STYLE_ID;
  st.textContent = CSS;
  document.head.appendChild(st);
}

const FUNNEL = '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M1 2h14l-5.5 6.5V14l-3-1.5v-4z"/></svg>';

export class SetsView {
  readonly root: HTMLDivElement;
  private readonly list: HTMLDivElement;
  private readonly nameInput: HTMLInputElement;
  private readonly msg: HTMLDivElement;
  private readonly fileInput: HTMLInputElement;
  private readonly filterRow: HTMLDivElement;
  private readonly filterInput: HTMLInputElement;
  private readonly filterInfo: HTMLSpanElement;
  private readonly editorPane: HTMLDivElement;
  private readonly editor: CriteriaEditor;
  private model: SceneModel | null = null;
  private modelName = '';
  private sets: SelectionSet[] = [];
  private editing = -1;
  /** Index of the set the criteria editor changes; -1 for a new set; null when the editor is closed. */
  private editorFor: number | null = null;
  private filter = '';
  private readonly counts = new WeakMap<SelectionSet, { resolved: number; total: number }>();

  constructor(
    private readonly host: SetsHost,
    private readonly storage: StorageLike,
  ) {
    ensureStyle();
    this.root = el('div', 'sets');
    const top = el('div', 'sets-top');
    this.nameInput = el('input', 'inp', { type: 'text', placeholder: 'Set name', 'aria-label': 'New set name' });
    const save = el('button', 'btn primary', { type: 'button', title: 'Save the current selection as a new set' }, 'Save selection as…');
    const row1 = el('div', 'row');
    row1.append(this.nameInput, save);
    const row2 = el('div', 'row');
    const crit = el(
      'button',
      'btn',
      { type: 'button', title: 'Make a set from rules, such as class and property values', 'data-help-key': 'Sidebar/New criteria set', 'data-help-title': 'New criteria set' },
      'New criteria set',
    );
    const exp = el('button', 'btn', { type: 'button', title: 'Download the sets of this model as JSON' }, 'Export');
    const imp = el('button', 'btn', { type: 'button', title: 'Load sets from a JSON file (same names are replaced)' }, 'Import');
    this.fileInput = el('input', '', { type: 'file', accept: 'application/json,.json' });
    this.fileInput.style.display = 'none';
    row2.append(crit, exp, imp, this.fileInput);
    this.msg = el('div', 'sets-msg', { 'aria-live': 'polite' });
    top.append(row1, row2, this.msg);

    this.filterRow = el('div', 'sets-filter');
    this.filterInput = el('input', 'inp', {
      type: 'search',
      placeholder: 'Filter sets',
      'aria-label': 'Filter the sets by name or query',
      'data-help-key': 'Sidebar/Set filter box',
      'data-help-title': 'Filter sets',
    });
    this.filterInfo = el('span', 'sets-filter-info');
    this.filterRow.append(this.filterInput, this.filterInfo);
    this.list = el('div', 'sets-list', { role: 'list', 'aria-label': 'Selection sets' });

    this.editor = new CriteriaEditor({
      model: () => this.model,
      table: () => (this.model ? modelTable(this.model) : null),
      preview: (ids) => {
        if (ids.length === 0) return;
        this.host.select(ids, false);
        this.host.frame(ids);
      },
      save: (name, query) => this.saveCriteria(name, query),
      cancel: () => this.closeEditor(),
    });
    this.editorPane = el('div', 'sets-pane-editor');
    this.editorPane.append(this.editor.root);
    this.editorPane.style.display = 'none';
    this.root.append(top, this.editorPane, this.filterRow, this.list);

    const doSave = (): void => {
      const sel = this.host.selection();
      if (sel.length === 0) return this.say('Nothing selected.');
      const name = this.nameInput.value.trim();
      if (!name) {
        this.say('Enter a name for the set.');
        this.nameInput.focus();
        return;
      }
      this.commit(addSet(this.sets, name, idsToGlobalIds(this.model!, sel)));
      this.nameInput.value = '';
      this.say(`Saved "${this.sets[this.sets.length - 1]!.name}" (${sel.length}).`);
    };
    save.addEventListener('click', doSave);
    this.nameInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') doSave();
      e.stopPropagation(); // do not trigger viewer shortcuts
    });
    crit.addEventListener('click', () => this.openEditor());
    exp.addEventListener('click', () => this.download());
    imp.addEventListener('click', () => this.fileInput.click());
    this.fileInput.addEventListener('change', () => void this.importFile());

    const applyFilter = debounce(() => {
      this.filter = this.filterInput.value.trim().toLowerCase();
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
        this.focusRow(0, 'apply');
      } else if (e.key === 'Enter') {
        // Enter applies the only (or first) match.
        const first = this.list.querySelector<HTMLElement>('.set-row');
        if (first) this.act(Number(first.dataset['i']), 'apply', false, null);
      }
    });

    this.list.addEventListener('click', (e) => this.onClick(e));
    this.list.addEventListener('keydown', (e) => this.onListKey(e));
    this.list.addEventListener('focusout', (e) => {
      const t = e.target as HTMLElement;
      if (t.classList.contains('rename-inp') && this.editing >= 0) this.finishRename(t as HTMLInputElement, true, false);
    });
  }

  /** Load (or seed) the sets for the model that was just installed; criteria sets are re-evaluated against it. */
  setModel(model: SceneModel, modelName: string): void {
    closeMenu();
    this.model = model;
    this.modelName = modelName;
    this.sets = loadOrSeed(this.storage, model, modelName);
    this.editing = -1;
    this.msg.textContent = '';
    let changed = false;
    this.sets = this.sets.map((s) => {
      if (!isCriteria(s)) return s;
      const next = this.evaluated(s);
      if (next !== s) changed = true;
      return next;
    });
    if (changed) saveSets(this.storage, modelName, this.sets);
    if (this.editorFor !== null) this.closeEditor();
    else this.render();
  }

  getSets(): readonly SelectionSet[] {
    return this.sets;
  }

  /** Open the criteria editor for a new set (prefilled) - used by the property context menu. */
  newCriteriaSet(query: string, name: string): void {
    this.openEditor(undefined, { query, name });
  }

  /** Re-run a criteria set's query. Returns the same object when the members did not change. */
  private evaluated(s: SelectionSet): SelectionSet {
    if (!isCriteria(s) || !this.model) return s;
    const r = runQuery(this.model, s.query);
    if (r.error) return s;
    const gids = idsToGlobalIds(this.model, r.ids);
    if (gids.length === s.globalIds.length && gids.every((g, i) => g === s.globalIds[i])) return s;
    return { ...s, globalIds: gids };
  }

  private commit(next: SelectionSet[]): void {
    this.sets = next;
    if (!saveSets(this.storage, this.modelName, next)) this.say('Could not persist sets (storage unavailable).');
    this.render();
  }

  private say(text: string): void {
    this.msg.textContent = text;
  }

  private countOf(s: SelectionSet): { resolved: number; total: number } {
    let c = this.counts.get(s);
    if (!c) {
      c = { resolved: this.model ? globalIdsToIds(this.model, s.globalIds).length : 0, total: s.globalIds.length };
      this.counts.set(s, c);
    }
    return c;
  }

  private matchesFilter(s: SelectionSet): boolean {
    if (!this.filter) return true;
    return s.name.toLowerCase().includes(this.filter) || (isCriteria(s) && s.query.toLowerCase().includes(this.filter));
  }

  private render(): void {
    const model = this.model;
    if (!model) return;
    this.filterRow.style.display = this.sets.length > 0 ? '' : 'none';
    if (this.sets.length === 0) {
      this.list.innerHTML = '<div class="tv-empty">No sets yet. Select elements, name them and save, or make a criteria set.</div>';
      this.filterInfo.textContent = '';
      return;
    }
    const html: string[] = [];
    let shown = 0;
    this.sets.forEach((s, i) => {
      if (!this.matchesFilter(s) && this.editing !== i) return;
      shown++;
      const { resolved, total } = this.countOf(s);
      const crit = isCriteria(s);
      const cnt = resolved === total ? `${resolved}` : `${resolved}/${total}`;
      const cntTitle = resolved === total ? `${resolved} element${resolved === 1 ? '' : 's'}` : `${total - resolved} elements of this set are not in the loaded model`;
      const badge = crit
        ? `<span class="set-badge" title="Criteria set: ${esc(s.query)}" data-help-key="Sidebar/Criteria badge" data-help-title="Criteria set">${FUNNEL}</span>`
        : '';
      const name =
        this.editing === i
          ? `<input class="inp rename-inp" type="text" value="${esc(s.name)}" aria-label="Rename set">`
          : `<button type="button" class="set-name" data-act="apply" title="${esc(s.name)}: select and frame (Shift: add)" data-help-key="Sidebar/Apply set" data-help-title="Apply set">${esc(s.name)}</button>`;
      html.push(
        `<div class="set-row${crit ? ' crit' : ''}" role="listitem" data-i="${i}">${badge}${name}` +
          `<span class="cnt${resolved === total ? '' : ' part'}" title="${cntTitle}">${cnt}</span>` +
          `<button type="button" class="set-ico" data-act="add" aria-label="Add ${esc(s.name)} to the selection" title="Add to the selection" data-help-key="Sidebar/Add set" data-help-title="Add set">+</button>` +
          `<button type="button" class="set-ico" data-act="menu" aria-haspopup="menu" aria-expanded="false" aria-label="More actions for ${esc(s.name)}" title="More actions" data-help-key="Sidebar/Set menu" data-help-title="Set menu">⋯</button>` +
          `</div>`,
      );
    });
    this.list.innerHTML = shown ? html.join('') : '<div class="tv-empty">No set matches the filter.</div>';
    this.filterInfo.textContent = this.filter ? `${shown} of ${this.sets.length}` : `${this.sets.length}`;
    const inp = this.list.querySelector<HTMLInputElement>('.rename-inp');
    if (inp) {
      inp.focus();
      inp.select();
    }
  }

  private rowEls(): HTMLElement[] {
    return Array.from(this.list.querySelectorAll<HTMLElement>('.set-row'));
  }

  private focusRow(pos: number, act: string): void {
    const rows = this.rowEls();
    if (rows.length === 0) return;
    const r = rows[Math.max(0, Math.min(rows.length - 1, pos))]!;
    r.querySelector<HTMLElement>(`[data-act="${act}"]`)?.focus();
    r.scrollIntoView({ block: 'nearest' });
  }

  /** Focus the control `act` of the row of set `i` after a re-render (falls back to the nearest row). */
  private focusSet(i: number, act: string): void {
    const rows = this.rowEls();
    const exact = rows.find((r) => Number(r.dataset['i']) === i);
    if (exact) {
      exact.querySelector<HTMLElement>(`[data-act="${act}"]`)?.focus();
      return;
    }
    const after = rows.findIndex((r) => Number(r.dataset['i']) > i);
    this.focusRow(after < 0 ? rows.length - 1 : after, act);
  }

  private onListKey(e: KeyboardEvent): void {
    const t = e.target as HTMLElement;
    if (t.classList.contains('rename-inp')) {
      e.stopPropagation();
      if (e.key === 'Enter') this.finishRename(t as HTMLInputElement, true, true);
      else if (e.key === 'Escape') this.finishRename(t as HTMLInputElement, false, true);
      return;
    }
    const row = t.closest<HTMLElement>('.set-row');
    if (!row) return;
    const rows = this.rowEls();
    const pos = rows.indexOf(row);
    const act = t.dataset['act'] ?? 'apply';
    let handled = true;
    switch (e.key) {
      case 'ArrowDown':
        this.focusRow(pos + 1, act);
        break;
      case 'ArrowUp':
        if (pos === 0) this.filterInput.focus();
        else this.focusRow(pos - 1, act);
        break;
      case 'Home':
        this.focusRow(0, act);
        break;
      case 'End':
        this.focusRow(rows.length - 1, act);
        break;
      case 'ArrowRight':
      case 'ArrowLeft': {
        const ctrls = Array.from(row.querySelectorAll<HTMLElement>('button'));
        const k = ctrls.indexOf(t);
        ctrls[Math.max(0, Math.min(ctrls.length - 1, k + (e.key === 'ArrowRight' ? 1 : -1)))]?.focus();
        break;
      }
      case 'Delete':
        this.openRowMenu(Number(row.dataset['i']), row.querySelector<HTMLElement>('[data-act="menu"]')!);
        break;
      default:
        handled = false; // Enter and Space activate the focused button natively
    }
    if (handled) {
      e.preventDefault();
      e.stopPropagation();
    } else if (e.key === 'Enter' || e.key === ' ') e.stopPropagation();
  }

  private onClick(e: MouseEvent): void {
    const t = e.target as HTMLElement;
    const btn = t.closest<HTMLElement>('[data-act]');
    const rowEl = t.closest<HTMLElement>('.set-row');
    if (!btn || !rowEl || !this.model) return;
    this.act(Number(rowEl.dataset['i']), btn.dataset['act']!, e.shiftKey, btn);
  }

  private act(i: number, act: string, shift: boolean, btn: HTMLElement | null): void {
    const set = this.sets[i];
    if (!set || !this.model) return;
    switch (act) {
      case 'apply':
      case 'add': {
        let s = set;
        if (isCriteria(set)) {
          s = this.evaluated(set);
          if (s !== set) this.commit(this.sets.map((x, k) => (k === i ? s : x)));
        }
        const ids = globalIdsToIds(this.model, s.globalIds);
        if (ids.length === 0) return this.say(`"${s.name}" has no elements in this model.`);
        this.host.select(ids, act === 'add' || shift);
        this.host.frame(ids);
        this.say(act === 'add' || shift ? `Added "${s.name}" (${ids.length}).` : '');
        if (s !== set) this.focusSet(i, act);
        break;
      }
      case 'menu':
        if (btn) this.openRowMenu(i, btn);
        break;
      case 'update': {
        if (isCriteria(set)) {
          const s = this.evaluated(set);
          if (s !== set) this.commit(this.sets.map((x, k) => (k === i ? s : x)));
          this.say(`Re-evaluated "${set.name}": ${s.globalIds.length} element${s.globalIds.length === 1 ? '' : 's'}.`);
          this.focusSet(i, 'menu');
          break;
        }
        const sel = this.host.selection();
        if (sel.length === 0) return this.say('Nothing selected to update from.');
        this.commit(updateSet(this.sets, i, idsToGlobalIds(this.model, sel)));
        this.say(`Updated "${set.name}" (${sel.length}).`);
        this.focusSet(i, 'menu');
        break;
      }
      case 'rename':
        this.editing = i;
        this.render();
        break;
      case 'edit':
        this.openEditor(i);
        break;
      case 'duplicate':
        this.commit(duplicateSet(this.sets, i));
        this.say(`Duplicated "${set.name}".`);
        this.focusSet(i + 1, 'apply');
        break;
      case 'delete':
        this.commit(removeSet(this.sets, i));
        this.say(`Deleted "${set.name}".`);
        this.focusSet(i, 'menu');
        break;
    }
  }

  private openRowMenu(i: number, btn: HTMLElement): void {
    const set = this.sets[i];
    if (!set) return;
    const crit = isCriteria(set);
    const items: MenuItem[] = [
      crit
        ? { label: 'Re-evaluate now', act: 'update', help: 'Sidebar/Re-evaluate set', title: 'Run the query again against the model' }
        : { label: 'Update from selection', act: 'update', help: 'Sidebar/Update set', title: "Replace the set's contents with the current selection" },
      { label: 'Rename', act: 'rename', help: 'Sidebar/Rename set' },
      ...(crit ? [{ label: 'Edit criteria…', act: 'edit', help: 'Sidebar/Edit criteria' }] : []),
      { label: 'Duplicate', act: 'duplicate', help: 'Sidebar/Duplicate set' },
      { label: 'Delete', act: 'delete', danger: true, confirm: 'Click again to delete', help: 'Sidebar/Delete set' },
    ];
    openMenu({
      at: btn,
      items,
      heading: set.name,
      label: `Actions for ${set.name}`,
      onPick: (act) => this.act(i, act, false, null),
    });
  }

  /** End the inline rename. `refocus`: put the focus on the renamed set (keyboard); a click elsewhere keeps its focus. */
  private finishRename(input: HTMLInputElement, accept: boolean, refocus: boolean): void {
    const i = this.editing;
    this.editing = -1;
    const name = input.value.trim();
    if (accept && name && this.sets[i] && name !== this.sets[i]!.name) this.commit(renameSet(this.sets, i, name));
    else this.render();
    if (refocus) this.focusSet(i, 'apply');
  }

  // ---------------------------------------------------------------- criteria editor

  private openEditor(index?: number, init?: { query: string; name: string }): void {
    closeMenu();
    const set = index === undefined ? undefined : this.sets[index];
    this.editorFor = set ? index! : -1;
    this.editorPane.style.display = '';
    this.filterRow.style.display = 'none';
    this.list.style.display = 'none';
    this.editor.open(
      set
        ? { name: set.name, query: set.query ?? '', heading: 'Edit criteria set', saveLabel: 'Save changes' }
        : { name: init?.name ?? '', query: init?.query ?? '', heading: 'New criteria set', saveLabel: 'Save set' },
    );
  }

  private closeEditor(): void {
    const was = this.editorFor;
    this.editorFor = null;
    this.editorPane.style.display = 'none';
    this.list.style.display = '';
    this.render();
    if (was !== null && was >= 0) this.focusSet(was, 'menu');
  }

  private saveCriteria(name: string, query: string): string | null {
    if (!this.model) return 'No model loaded.';
    const r = runQuery(this.model, query);
    if (r.error) return r.error.message;
    const gids = idsToGlobalIds(this.model, r.ids);
    const at = this.editorFor;
    let index: number;
    if (at !== null && at >= 0 && this.sets[at]) {
      let next = setQuery(this.sets, at, query, gids);
      if (name !== this.sets[at]!.name) next = renameSet(next, at, name);
      this.commit(next);
      index = at;
    } else {
      this.commit(addCriteriaSet(this.sets, name, query, gids));
      index = this.sets.length - 1;
    }
    const saved = this.sets[index]!;
    this.closeEditor();
    this.say(`Saved criteria set "${saved.name}" (${gids.length}).`);
    this.focusSet(index, 'apply');
    return null;
  }

  // ---------------------------------------------------------------- import / export

  private download(): void {
    const blob = new Blob([exportSets(this.modelName, this.sets)], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `xray-sets-${this.modelName}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }

  private async importFile(): Promise<void> {
    const f = this.fileInput.files?.[0];
    this.fileInput.value = '';
    if (!f) return;
    const parsed = parseImport(await f.text());
    if (!parsed) return this.say('Not a valid sets file.');
    this.commit(mergeImported(this.sets, parsed).map((s) => this.evaluated(s)));
    this.say(`Imported ${parsed.length} set${parsed.length === 1 ? '' : 's'}.`);
  }
}
