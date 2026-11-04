// Compact editor for a criteria set: a row builder (column, operator, value) that writes the query text, a raw query
// box for hand-written queries, a live match count with inline errors, Preview, Save and Cancel.
// The query language lives in ../query; this module only builds the DOM and keeps the two views in step.

import {
  BUILDER_OPS,
  NO_VALUE_OPS,
  conditionsText,
  runQuery,
  toConditions,
} from '../query';
import type { BuilderOp, Condition, ConditionList, ModelTable, QueryResult, Value } from '../query';
import type { ElementId, SceneModel } from '../types';
import { debounce, el } from './dom';

export interface CriteriaEditorHost {
  model(): SceneModel | null;
  table(): ModelTable | null;
  /** Select (and frame) the matches without saving. */
  preview(ids: ElementId[]): void;
  /** Save; returns an error message to show, or null when saved (the host then closes the editor). */
  save(name: string, query: string): string | null;
  cancel(): void;
}

export interface EditorInit {
  name: string;
  query: string;
  /** Heading text. */
  heading: string;
  saveLabel?: string;
}

const STYLE_ID = 'xray-criteria-editor-style';
const CSS = `
.ce { display: flex; flex-direction: column; gap: 6px; padding: 6px; }
.ce-head { display: flex; align-items: center; gap: 6px; font-weight: 600; }
.ce-head span { flex: 1 1 auto; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ce-x { width: 22px; height: 22px; padding: 0; background: transparent; border: 1px solid transparent; border-radius: 3px; cursor: pointer; color: var(--sb-dim); }
.ce-x:hover { border-color: var(--sb-line); color: var(--sb-fg); }
.ce label.ce-lbl { color: var(--sb-dim); font-size: 11px; }
.ce .inp { min-width: 0; }
.ce-namerow { display: flex; gap: 6px; align-items: center; }
.ce-namerow .inp { flex: 1 1 auto; }
.ce-join { display: flex; gap: 6px; align-items: center; color: var(--sb-dim); }
.ce-join select, .ce-row select { background: #0e1218; border: 1px solid var(--sb-line); border-radius: 3px; height: 24px; color: inherit; font: inherit; }
.ce-rows { display: flex; flex-direction: column; gap: 5px; }
.ce-rows.off { opacity: 0.45; pointer-events: none; }
.ce-row { display: grid; grid-template-columns: 84px 1fr 22px; grid-template-areas: "f f x" "o v v"; gap: 3px 4px;
  padding: 4px; border: 1px solid var(--sb-line); border-radius: 4px; background: #10141b; }
.ce-row .ce-f { grid-area: f; }
.ce-row .ce-o { grid-area: o; min-width: 0; }
.ce-row .ce-v { grid-area: v; }
.ce-row .ce-v:disabled { opacity: 0.4; }
.ce-row .ce-x { grid-area: x; }
.ce-tools { display: flex; gap: 6px; align-items: center; }
.ce-text { width: 100%; min-height: 54px; resize: vertical; background: #0e1218; border: 1px solid var(--sb-line); border-radius: 3px;
  padding: 4px 6px; color: inherit; font: 11.5px/1.4 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; outline: none; }
.ce-text:focus { border-color: var(--sb-accent); }
.ce-text.bad { border-color: #c0504d; }
.ce-status { min-height: 16px; color: var(--sb-dim); }
.ce-status.ok b { color: var(--sb-fg); }
.ce-status.err { color: #ff8a80; white-space: pre-wrap; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 11px; }
.ce-status .ce-warn { display: block; color: #e0b252; font-family: inherit; }
.ce-note { color: #e0b252; font-size: 11px; }
.ce-btns { display: flex; gap: 6px; flex-wrap: wrap; }
.ce-btns .btn { flex: 1 1 auto; }
`;

function ensureStyle(): void {
  if (document.getElementById(STYLE_ID)) return;
  const st = document.createElement('style');
  st.id = STYLE_ID;
  st.textContent = CSS;
  document.head.appendChild(st);
}

let uid = 0;

const valueLabel = (v: Value): string => (typeof v === 'boolean' ? (v ? 'TRUE' : 'FALSE') : String(v));

export class CriteriaEditor {
  readonly root: HTMLFormElement;
  private readonly headEl: HTMLSpanElement;
  private readonly nameInput: HTMLInputElement;
  private readonly joinRow: HTMLDivElement;
  private readonly joinSel: HTMLSelectElement;
  private readonly rowsEl: HTMLDivElement;
  private readonly addBtn: HTMLButtonElement;
  private readonly note: HTMLDivElement;
  private readonly text: HTMLTextAreaElement;
  private readonly status: HTMLDivElement;
  private readonly saveBtn: HTMLButtonElement;
  private readonly previewBtn: HTMLButtonElement;
  private readonly colList: HTMLDataListElement;
  private readonly id = ++uid;
  private conds: Condition[] = [];
  private last: QueryResult | null = null;
  private builderOn = true;

  constructor(private readonly host: CriteriaEditorHost) {
    ensureStyle();
    this.root = el('form', 'ce', { 'aria-label': 'Criteria set editor', novalidate: '' });
    const head = el('div', 'ce-head');
    this.headEl = el('span');
    const x = el('button', 'ce-x', { type: 'button', 'aria-label': 'Close the editor', title: 'Close without saving' }, '×');
    head.append(this.headEl, x);

    const nameRow = el('div', 'ce-namerow');
    this.nameInput = el('input', 'inp', { type: 'text', placeholder: 'Set name', 'aria-label': 'Criteria set name', 'data-help-key': 'Sidebar/Criteria set name', 'data-help-title': 'Name' });
    nameRow.append(this.nameInput);

    this.joinRow = el('div', 'ce-join');
    this.joinSel = el('select', '', { 'aria-label': 'Combine the conditions with', 'data-help-key': 'Sidebar/Match all or any', 'data-help-title': 'Match all or any' });
    this.joinSel.append(el('option', '', { value: 'AND' }, 'all'), el('option', '', { value: 'OR' }, 'any'));
    this.joinRow.append(document.createTextNode('Match'), this.joinSel, document.createTextNode('of these conditions'));

    this.colList = el('datalist', '', { id: `ce-cols-${this.id}` });
    this.rowsEl = el('div', 'ce-rows');
    const tools = el('div', 'ce-tools');
    this.addBtn = el('button', 'btn', { type: 'button', 'data-help-key': 'Sidebar/Add condition', 'data-help-title': 'Add condition' }, '+ Condition');
    tools.append(this.addBtn);
    this.note = el('div', 'ce-note');
    this.note.style.display = 'none';

    const qLbl = el('label', 'ce-lbl', { for: `ce-q-${this.id}` }, 'Query (SQL WHERE)');
    this.text = el('textarea', 'ce-text', {
      id: `ce-q-${this.id}`,
      spellcheck: 'false',
      autocomplete: 'off',
      rows: '3',
      placeholder: `class = 'IfcWall' AND "Pset_WallCommon.IsExternal" = TRUE`,
      'data-help-key': 'Sidebar/Query box',
      'data-help-title': 'Query box',
    });
    this.status = el('div', 'ce-status', { 'aria-live': 'polite' });
    const btns = el('div', 'ce-btns');
    this.previewBtn = el('button', 'btn', { type: 'button', 'data-help-key': 'Sidebar/Preview matches', 'data-help-title': 'Preview' }, 'Preview');
    this.saveBtn = el('button', 'btn primary', { type: 'submit', 'data-help-key': 'Sidebar/Save criteria set', 'data-help-title': 'Save' }, 'Save');
    const cancel = el('button', 'btn', { type: 'button' }, 'Cancel');
    btns.append(this.previewBtn, this.saveBtn, cancel);
    this.root.append(head, nameRow, this.joinRow, this.rowsEl, tools, this.note, qLbl, this.text, this.status, btns, this.colList);

    const recount = debounce(() => this.evaluate(), 120);
    x.addEventListener('click', () => this.host.cancel());
    cancel.addEventListener('click', () => this.host.cancel());
    this.addBtn.addEventListener('click', () => {
      this.conds.push({ column: '', op: '=', value: '' });
      this.renderRows();
      this.rowsEl.querySelector<HTMLInputElement>('.ce-row:last-child .ce-f')?.focus();
    });
    this.joinSel.addEventListener('change', () => this.fromBuilder());
    this.text.addEventListener('input', () => {
      this.fromText();
      recount();
    });
    this.rowsEl.addEventListener('input', (e) => this.onRowInput(e));
    this.rowsEl.addEventListener('change', (e) => this.onRowInput(e));
    this.rowsEl.addEventListener('focusin', (e) => {
      const t = e.target as HTMLElement;
      if (t.classList.contains('ce-v')) this.fillValues(t.closest<HTMLElement>('.ce-row')!);
    });
    this.rowsEl.addEventListener('click', (e) => {
      const b = (e.target as HTMLElement).closest<HTMLElement>('.ce-x');
      if (!b) return;
      const i = Number(b.closest<HTMLElement>('.ce-row')!.dataset['i']);
      this.conds.splice(i, 1);
      if (this.conds.length === 0) this.conds.push({ column: '', op: '=', value: '' });
      this.renderRows();
      this.fromBuilder();
    });
    this.previewBtn.addEventListener('click', () => {
      this.evaluate();
      if (this.last && !this.last.error) this.host.preview(this.last.ids);
    });
    this.root.addEventListener('submit', (e) => {
      e.preventDefault();
      this.doSave();
    });
    // Text fields: viewer shortcuts already ignore typing targets; Enter in a one-line field must not submit by accident
    // in the condition rows (it saves only from the name box or with Ctrl+Enter in the query box).
    this.root.addEventListener('keydown', (e) => {
      const t = e.target as HTMLElement;
      if (e.key === 'Enter' && t === this.text && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        this.doSave();
      } else if (e.key === 'Enter' && t.closest('.ce-row')) {
        e.preventDefault();
      }
      if (e.key !== 'Escape') e.stopPropagation();
    });
  }

  /** Fill the editor and focus it. */
  open(init: EditorInit): void {
    this.headEl.textContent = init.heading;
    this.saveBtn.textContent = init.saveLabel ?? 'Save';
    this.nameInput.value = init.name;
    this.text.value = init.query;
    this.fillColumns();
    const list = init.query.trim() ? toConditions(init.query) : { join: 'AND' as const, conditions: [] };
    this.applyList(list);
    this.evaluate();
    (init.query.trim() ? this.nameInput : (this.rowsEl.querySelector<HTMLInputElement>('.ce-f') ?? this.nameInput)).focus();
  }

  get query(): string {
    return this.text.value;
  }

  private doSave(): void {
    this.evaluate();
    const name = this.nameInput.value.trim();
    if (!name) {
      this.setStatusError('Enter a name for the set.');
      this.nameInput.focus();
      return;
    }
    if (!this.last || this.last.error) {
      this.text.focus();
      return;
    }
    const err = this.host.save(name, this.text.value.trim());
    if (err) this.setStatusError(err);
  }

  private setStatusError(msg: string): void {
    this.status.className = 'ce-status err';
    this.status.textContent = msg;
  }

  private fillColumns(): void {
    const t = this.host.table();
    this.colList.textContent = '';
    if (!t) return;
    for (const c of t.columns()) {
      this.colList.append(el('option', '', { value: c.name, label: c.core ? `${c.doc ?? ''}` : `${c.count} element${c.count === 1 ? '' : 's'}` }));
    }
  }

  private fillValues(row: HTMLElement): void {
    const i = Number(row.dataset['i']);
    const c = this.conds[i];
    const dl = row.querySelector('datalist');
    const t = this.host.table();
    if (!c || !dl || !t) return;
    if (dl.dataset['col'] === c.column) return;
    dl.dataset['col'] = c.column;
    dl.textContent = '';
    for (const d of t.distinct(c.column, 150)) dl.append(el('option', '', { value: valueLabel(d.value), label: `${d.count}` }));
  }

  private applyList(list: ConditionList | null): void {
    this.builderOn = list !== null;
    this.rowsEl.classList.toggle('off', !this.builderOn);
    this.addBtn.disabled = !this.builderOn;
    this.joinSel.disabled = !this.builderOn;
    this.note.style.display = this.builderOn ? 'none' : '';
    this.note.textContent = this.builderOn ? '' : 'The rows cannot show this query (groups, NOT, BETWEEN or a syntax error). Edit the text.';
    if (list) {
      this.conds = list.conditions.length ? list.conditions.map((c) => ({ ...c })) : [{ column: '', op: '=', value: '' }];
      this.joinSel.value = list.join;
      this.renderRows();
    }
  }

  private renderRows(): void {
    this.rowsEl.textContent = '';
    this.joinRow.style.display = this.conds.length > 1 ? '' : 'none';
    this.conds.forEach((c, i) => {
      const row = el('div', 'ce-row', { 'data-i': String(i) });
      const f = el('input', 'inp ce-f', {
        type: 'text',
        list: this.colList.id,
        placeholder: 'Field: class, name, "Pset_…"',
        'aria-label': `Condition ${i + 1} field`,
        autocomplete: 'off',
        spellcheck: 'false',
        'data-help-key': 'Sidebar/Condition field',
        'data-help-title': 'Field',
      });
      f.value = c.column;
      const o = el('select', 'ce-o', { 'aria-label': `Condition ${i + 1} operator`, 'data-help-key': 'Sidebar/Condition operator', 'data-help-title': 'Operator' });
      for (const op of BUILDER_OPS) o.append(el('option', '', { value: op }, op === '!=' ? '≠' : op));
      o.value = c.op;
      const dlId = `ce-vals-${this.id}-${i}`;
      const v = el('input', 'inp ce-v', {
        type: 'text',
        list: dlId,
        placeholder: c.op === 'IN' || c.op === 'NOT IN' ? 'a, b, c' : c.op.includes('LIKE') ? '%text%' : 'Value',
        'aria-label': `Condition ${i + 1} value`,
        autocomplete: 'off',
        spellcheck: 'false',
        'data-help-key': 'Sidebar/Condition value',
        'data-help-title': 'Value',
      });
      v.value = c.value;
      v.disabled = NO_VALUE_OPS.has(c.op);
      const x = el('button', 'ce-x', { type: 'button', 'aria-label': `Remove condition ${i + 1}`, title: 'Remove this condition' }, '×');
      row.append(f, o, v, x, el('datalist', '', { id: dlId }));
      this.rowsEl.append(row);
    });
  }

  private onRowInput(e: Event): void {
    const t = e.target as HTMLElement;
    const row = t.closest<HTMLElement>('.ce-row');
    if (!row) return;
    const i = Number(row.dataset['i']);
    const c = this.conds[i];
    if (!c) return;
    if (t.classList.contains('ce-f')) c.column = (t as HTMLInputElement).value.trim();
    else if (t.classList.contains('ce-o')) {
      c.op = (t as HTMLSelectElement).value as BuilderOp;
      const v = row.querySelector<HTMLInputElement>('.ce-v')!;
      v.disabled = NO_VALUE_OPS.has(c.op);
      v.placeholder = c.op === 'IN' || c.op === 'NOT IN' ? 'a, b, c' : c.op.includes('LIKE') ? '%text%' : 'Value';
    } else if (t.classList.contains('ce-v')) c.value = (t as HTMLInputElement).value;
    this.fromBuilder();
  }

  /** Builder rows -> query text. */
  private fromBuilder(): void {
    const t = this.host.table();
    const list: ConditionList = { join: this.joinSel.value === 'OR' ? 'OR' : 'AND', conditions: this.conds };
    this.text.value = conditionsText(list, (col) => t?.kind(col) ?? 'mixed');
    this.evaluateSoon();
  }

  private evaluateSoon = debounce(() => this.evaluate(), 120);

  /** Query text -> builder rows (when the builder can show it). */
  private fromText(): void {
    const q = this.text.value;
    if (!q.trim()) {
      this.applyList({ join: 'AND', conditions: [] });
      return;
    }
    const list = toConditions(q);
    if (list) this.applyList(list);
    else this.applyList(null);
  }

  /** Run the query, show the count or the error. */
  evaluate(): void {
    const model = this.host.model();
    const q = this.text.value;
    if (!model) return;
    if (!q.trim()) {
      this.last = null;
      this.status.className = 'ce-status';
      this.status.textContent = 'Add a condition or type a query.';
      this.text.classList.remove('bad');
      this.previewBtn.disabled = true;
      this.saveBtn.disabled = true;
      return;
    }
    const r = runQuery(model, q);
    this.last = r;
    this.previewBtn.disabled = !!r.error || r.ids.length === 0;
    this.saveBtn.disabled = !!r.error;
    this.text.classList.toggle('bad', !!r.error);
    if (r.error) {
      // The message, then the query line with a caret under the position.
      const pos = Math.min(r.error.pos, q.length);
      const lineStart = q.lastIndexOf('\n', pos - 1) + 1;
      const lineEnd = q.indexOf('\n', pos) < 0 ? q.length : q.indexOf('\n', pos);
      const from = Math.max(lineStart, pos - 28);
      const to = Math.min(lineEnd, pos + 28);
      const snippet = `${from > lineStart ? '…' : ''}${q.slice(from, to)}${to < lineEnd ? '…' : ''}`;
      const caret = `${' '.repeat(pos - from + (from > lineStart ? 1 : 0))}^`;
      this.status.className = 'ce-status err';
      this.status.textContent = `${r.error.message}\n${snippet}\n${caret}`;
      return;
    }
    this.status.className = 'ce-status ok';
    this.status.textContent = '';
    const n = r.ids.length;
    const b = el('b', '', {}, n.toLocaleString('en-US'));
    this.status.append(b, document.createTextNode(` match${n === 1 ? '' : 'es'} of ${model.elements.length.toLocaleString('en-US')} elements`));
    if (r.unknown.length) {
      this.status.append(el('span', 'ce-warn', {}, `No element has ${r.unknown.map((u) => `"${u}"`).join(', ')}: it reads as NULL.`));
    }
  }
}
