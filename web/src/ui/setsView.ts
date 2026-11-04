// DOM renderer for the "Sets" tab: list of named selection sets with apply/add/update/rename/delete,
// "save current selection as", and JSON import/export. Persistence and id mapping live in ../selectionSets.

import type { ElementId, SceneModel } from '../types';
import {
  addSet,
  exportSets,
  globalIdsToIds,
  idsToGlobalIds,
  loadOrSeed,
  mergeImported,
  parseImport,
  removeSet,
  renameSet,
  saveSets,
  updateSet,
} from '../selectionSets';
import type { SelectionSet, StorageLike } from '../selectionSets';
import { el, esc } from './dom';

export interface SetsHost {
  selection(): ElementId[];
  select(ids: ElementId[], additive: boolean): void;
  /** Frame the camera on these elements. */
  frame(ids: ElementId[]): void;
}

export class SetsView {
  readonly root: HTMLDivElement;
  private readonly list: HTMLDivElement;
  private readonly nameInput: HTMLInputElement;
  private readonly msg: HTMLDivElement;
  private readonly fileInput: HTMLInputElement;
  private model: SceneModel | null = null;
  private modelName = '';
  private sets: SelectionSet[] = [];
  private editing = -1;

  constructor(
    private readonly host: SetsHost,
    private readonly storage: StorageLike,
  ) {
    this.root = el('div', 'sets');
    const top = el('div', 'sets-top');
    this.nameInput = el('input', 'inp', { type: 'text', placeholder: 'Set name', 'aria-label': 'New set name' });
    const save = el('button', 'btn primary', { type: 'button', title: 'Save the current selection as a new set' }, 'Save selection as…');
    const row1 = el('div', 'row');
    row1.append(this.nameInput, save);
    const row2 = el('div', 'row');
    const exp = el('button', 'btn', { type: 'button', title: 'Download the sets of this model as JSON' }, 'Export');
    const imp = el('button', 'btn', { type: 'button', title: 'Load sets from a JSON file (same names are replaced)' }, 'Import');
    this.fileInput = el('input', '', { type: 'file', accept: 'application/json,.json' });
    this.fileInput.style.display = 'none';
    row2.append(exp, imp, this.fileInput);
    this.msg = el('div', 'sets-msg');
    top.append(row1, row2, this.msg);
    this.list = el('div', 'sets-list');
    this.root.append(top, this.list);

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
    exp.addEventListener('click', () => this.download());
    imp.addEventListener('click', () => this.fileInput.click());
    this.fileInput.addEventListener('change', () => void this.importFile());
    this.list.addEventListener('click', (e) => this.onClick(e));
    this.list.addEventListener('keydown', (e) => {
      const t = e.target as HTMLElement;
      if (t.classList.contains('rename-inp')) {
        e.stopPropagation();
        if (e.key === 'Enter') this.finishRename(t as HTMLInputElement, true);
        else if (e.key === 'Escape') this.finishRename(t as HTMLInputElement, false);
      }
    });
    this.list.addEventListener('focusout', (e) => {
      const t = e.target as HTMLElement;
      if (t.classList.contains('rename-inp') && this.editing >= 0) this.finishRename(t as HTMLInputElement, true);
    });
  }

  /** Load (or seed) the sets for the model that was just installed. */
  setModel(model: SceneModel, modelName: string): void {
    this.model = model;
    this.modelName = modelName;
    this.sets = loadOrSeed(this.storage, model, modelName);
    this.editing = -1;
    this.msg.textContent = '';
    this.render();
  }

  getSets(): readonly SelectionSet[] {
    return this.sets;
  }

  private commit(next: SelectionSet[]): void {
    this.sets = next;
    if (!saveSets(this.storage, this.modelName, next)) this.say('Could not persist sets (storage unavailable).');
    this.render();
  }

  private say(text: string): void {
    this.msg.textContent = text;
  }

  private render(): void {
    const model = this.model;
    if (!model) return;
    if (this.sets.length === 0) {
      this.list.innerHTML = '<div class="tv-empty">No sets yet. Select elements, name them and save.</div>';
      return;
    }
    this.list.innerHTML = this.sets
      .map((s, i) => {
        const resolved = globalIdsToIds(model, s.globalIds).length;
        const cnt = resolved === s.globalIds.length ? `${resolved}` : `${resolved}/${s.globalIds.length}`;
        const title =
          resolved === s.globalIds.length ? '' : ` title="${s.globalIds.length - resolved} elements of this set are not in the loaded model"`;
        const name =
          this.editing === i
            ? `<input class="inp rename-inp" type="text" value="${esc(s.name)}" aria-label="Rename set">`
            : `<span class="name" data-act="apply" title="Select and frame">${esc(s.name)}</span>`;
        return (
          `<div class="set" data-i="${i}"><div class="set-head">${name}<span class="cnt"${title}>${cnt}</span></div>` +
          `<div class="set-btns">` +
          `<button class="btn" type="button" data-act="apply" title="Replace the selection with this set and frame it">Apply</button>` +
          `<button class="btn" type="button" data-act="add" title="Add this set to the selection">Add</button>` +
          `<button class="btn" type="button" data-act="update" title="Replace the set's contents with the current selection">Update</button>` +
          `<button class="btn" type="button" data-act="rename">Rename</button>` +
          `<button class="btn danger" type="button" data-act="delete">Delete</button>` +
          `</div></div>`
        );
      })
      .join('');
    const inp = this.list.querySelector<HTMLInputElement>('.rename-inp');
    if (inp) {
      inp.focus();
      inp.select();
    }
  }

  private onClick(e: MouseEvent): void {
    const t = e.target as HTMLElement;
    const act = t.closest<HTMLElement>('[data-act]')?.dataset['act'];
    const rowEl = t.closest<HTMLElement>('.set');
    if (!act || !rowEl || !this.model) return;
    const i = Number(rowEl.dataset['i']);
    const set = this.sets[i];
    if (!set) return;
    const ids = globalIdsToIds(this.model, set.globalIds);
    switch (act) {
      case 'apply':
      case 'add':
        if (ids.length === 0) return this.say(`"${set.name}" has no elements in this model.`);
        this.host.select(ids, act === 'add' || e.shiftKey);
        this.host.frame(ids);
        this.say('');
        break;
      case 'update': {
        const sel = this.host.selection();
        if (sel.length === 0) return this.say('Nothing selected to update from.');
        this.commit(updateSet(this.sets, i, idsToGlobalIds(this.model, sel)));
        this.say(`Updated "${set.name}" (${sel.length}).`);
        break;
      }
      case 'rename':
        this.editing = i;
        this.render();
        break;
      case 'delete':
        this.commit(removeSet(this.sets, i));
        this.say(`Deleted "${set.name}".`);
        break;
    }
  }

  private finishRename(input: HTMLInputElement, accept: boolean): void {
    const i = this.editing;
    this.editing = -1;
    const name = input.value.trim();
    if (accept && name && this.sets[i] && name !== this.sets[i]!.name) this.commit(renameSet(this.sets, i, name));
    else this.render();
  }

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
    this.commit(mergeImported(this.sets, parsed));
    this.say(`Imported ${parsed.length} set${parsed.length === 1 ? '' : 's'}.`);
  }
}
