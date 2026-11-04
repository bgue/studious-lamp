// Properties footer: details of the first selected element.
//
// Every attribute row (Class, Name, Storey, Material, GlobalId) and property row has a context menu (right-click, or the
// "⋯" button that shows on hover and always on touch screens): select or add all elements with the same value, select
// all with the property, copy the value, save the equivalent criteria query as a set. Queries run through ../query.

import { equalsQuery, quoteIdent } from '../query';
import { copyText, el } from './dom';
import { propLabel } from './hoverCard';
import { openMenu } from './popupMenu';
import type { MenuItem } from './popupMenu';

/** What the property context menu does; the sidebar implements it. */
export interface PropsActions {
  /** Select the elements that match a criteria query (additive: add them to the selection). */
  selectWhere(query: string, additive: boolean): void;
  /** Open the criteria-set editor with this query and name. */
  saveCriteria(query: string, name: string): void;
}

/** The query column of an attribute row, for the context menu. Rows without one only offer Copy value. */
const FIELD_COLUMN: Partial<Record<keyof PropsData, string>> = {
  globalId: 'globalId',
  ifcClass: 'class',
  name: 'name',
  storey: 'storey',
  material: 'material',
};

export type PropRow = [key: string, value: string | number | boolean];

/**
 * Where the collapsible "Properties" list gets its rows: the hover-info plugin installs a provider (it owns the
 * property filter and the `all properties in sidebar` setting). `null` means the element has no properties.
 */
export type PropRowsProvider = (globalId: string) => { rows: PropRow[]; total: number } | null;
let rowsProvider: PropRowsProvider | null = null;
const liveViews = new Set<PropsView>();

export function setPropRowsProvider(p: PropRowsProvider | null): void {
  rowsProvider = p;
  refreshPropsViews();
}

/** Re-render the properties list of every sidebar (after a setting changed). */
export function refreshPropsViews(): void {
  for (const v of liveViews) v.renderRows();
}

const LIST_STYLE_ID = 'xray-props-list-style';
const OPEN_KEY = 'xray.propsListOpen';

function ensureListStyle(): void {
  if (document.getElementById(LIST_STYLE_ID)) return;
  const st = document.createElement('style');
  st.id = LIST_STYLE_ID;
  st.textContent = `
    .props-list { margin-top: 6px; border-top: 1px solid var(--sb-line, #2d3748); padding-top: 4px; }
    .props-list > summary { cursor: pointer; color: var(--sb-dim, #8b9bb0); user-select: none; }
    .props-list-rows { display: grid; grid-template-columns: minmax(60px, 40%) 1fr; gap: 1px 8px; margin: 3px 0 0; max-height: 150px; overflow-y: auto; }
    .props-list-rows dt { color: var(--sb-dim, #8b9bb0); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; cursor: pointer; }
    .props-list-rows dd { margin: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; cursor: pointer; font-variant-numeric: tabular-nums; }
    .props-list-rows .pl-hit { color: var(--sb-accent, #4c9aff); }
    .props-list-rows dt:hover, .props-list-rows dd:hover { color: var(--sb-fg, #dfe6ee); }
    .props-grid dd, .props-list-rows dd { display: flex; align-items: center; gap: 2px; }
    .props .pv-t { flex: 1 1 auto; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .props .pv-more { flex: 0 0 auto; width: 20px; height: 16px; padding: 0; line-height: 12px; font-size: 13px; background: transparent;
      border: 1px solid transparent; border-radius: 3px; color: var(--sb-dim, #8b9bb0); cursor: pointer; visibility: hidden; }
    .props .pv-more:hover, .props .pv-more:focus-visible, .props .pv-more[aria-expanded="true"] { color: var(--sb-fg, #dfe6ee); border-color: #3a4558; background: #1b2230; outline: none; }
    .props dd:hover .pv-more, .props dt:hover + dd .pv-more, .props .pv-more:focus, .props .pv-more[aria-expanded="true"] { visibility: visible; }
    .props .pv-row-hit { background: var(--sb-hover, #1c2230); }
    @media (hover: none) { .props .pv-more { visibility: visible; width: 26px; height: 22px; } }
  `;
  document.head.appendChild(st);
}

export interface PropsData {
  globalId: string;
  ifcClass: string;
  name: string;
  storey: string;
  material: string;
  bucket: string;
  proximityWeight: number;
  occlusion: number;
  targetAlpha: number;
  alpha: number;
  /** Selected elements beyond the first. */
  more: number;
  /** Raw storey name for queries (null: no storey). Defaults to `storey`. */
  storeyName?: string | null;
}

const FIELDS: Array<[keyof PropsData, string]> = [
  ['globalId', 'GlobalId'],
  ['ifcClass', 'Class'],
  ['name', 'Name'],
  ['storey', 'Storey'],
  ['material', 'Material'],
  ['bucket', 'Bucket'],
  ['proximityWeight', 'Proximity weight'],
  ['occlusion', 'Occlusion'],
  ['targetAlpha', 'Target alpha'],
  ['alpha', 'Alpha'],
];

function fmtVal(v: unknown): string {
  if (typeof v === 'number') return Number.isFinite(v) ? v.toFixed(2) : '-';
  return v === undefined || v === '' ? '-' : String(v);
}

export class PropsView {
  readonly root: HTMLDivElement;
  private readonly values = new Map<string, HTMLElement>();
  private readonly empty: HTMLDivElement;
  private readonly grid: HTMLDListElement;
  private readonly copyBtn: HTMLButtonElement;
  private readonly moreEl: HTMLDivElement;
  private readonly listEl: HTMLDetailsElement;
  private readonly listSummary: HTMLElement;
  private readonly listRows: HTMLDListElement;
  private last: PropsData | null = null;
  private gid = '';
  private flash: ReturnType<typeof setTimeout> | null = null;
  private readonly texts = new Map<string, HTMLSpanElement>();
  private rowRaw: Array<[string, string | number | boolean]> = [];

  constructor(private readonly actions: PropsActions | null = null) {
    this.root = el('div', 'props');
    const head = el('div', 'props-head');
    head.append(el('span', 'props-title', {}, 'Properties'));
    this.copyBtn = el('button', 'btn', { type: 'button', title: 'Copy the GlobalId of the first selected element' }, 'Copy GlobalId');
    this.copyBtn.disabled = true;
    head.append(this.copyBtn);
    this.empty = el('div', 'props-empty', {}, 'No selection');
    this.grid = el('dl', 'props-grid');
    for (const [key, label] of FIELDS) {
      const dt = el('dt', '', { 'data-field': key }, label);
      const dd = el('dd', '', { 'data-field': key });
      const t = el('span', 'pv-t');
      dd.append(t, this.moreBtn(label));
      this.values.set(key, dd);
      this.texts.set(key, t);
      this.grid.append(dt, dd);
    }
    this.moreEl = el('div', 'props-more');
    ensureListStyle();
    this.listEl = el('details', 'props-list');
    this.listSummary = el('summary', '', {}, 'Properties');
    this.listRows = el('dl', 'props-list-rows');
    this.listEl.append(this.listSummary, this.listRows);
    this.listEl.style.display = 'none';
    try {
      this.listEl.open = localStorage.getItem(OPEN_KEY) !== '0';
    } catch {
      this.listEl.open = true;
    }
    this.listEl.addEventListener('toggle', () => {
      try {
        localStorage.setItem(OPEN_KEY, this.listEl.open ? '1' : '0');
      } catch { /* private mode */ }
    });
    this.root.addEventListener('contextmenu', (ev) => {
      const cell = (ev.target as HTMLElement).closest<HTMLElement>('.props-grid dt, .props-grid dd, .props-list-rows dt[data-row], .props-list-rows dd[data-row]');
      if (!cell || !this.last) return;
      ev.preventDefault();
      this.openRowMenu(cell, { x: ev.clientX, y: ev.clientY });
    });
    this.root.addEventListener('click', (ev) => {
      const b = (ev.target as HTMLElement).closest<HTMLElement>('.pv-more');
      if (!b) return;
      ev.stopPropagation();
      this.openRowMenu(b.closest<HTMLElement>('dd')!, b);
    });
    this.listRows.addEventListener('click', async (ev) => {
      if ((ev.target as HTMLElement).closest('.pv-more')) return;
      const t = (ev.target as HTMLElement).closest('dt, dd') as HTMLElement | null;
      if (!t) return;
      const row = t.dataset.row;
      const value = row === undefined ? undefined : this.rowValues[Number(row)];
      if (value === undefined) return;
      const ok = await copyText(value);
      for (const n of Array.from(this.listRows.querySelectorAll(`[data-row="${row}"]`))) n.classList.toggle('pl-hit', ok);
      setTimeout(() => { for (const n of Array.from(this.listRows.querySelectorAll(".pl-hit"))) n.classList.remove('pl-hit'); }, 700);
    });
    liveViews.add(this);
    this.root.append(head, this.empty, this.grid, this.moreEl, this.listEl);
    this.copyBtn.addEventListener('click', async () => {
      if (!this.gid) return;
      const ok = await copyText(this.gid);
      this.copyBtn.textContent = ok ? 'Copied' : 'Copy failed';
      if (this.flash) clearTimeout(this.flash);
      this.flash = setTimeout(() => (this.copyBtn.textContent = 'Copy GlobalId'), 1200);
    });
  }

  /** Update the shown values; only touches the DOM for fields that changed. */
  update(d: PropsData | null): void {
    this.last = d;
    this.renderRows();
    this.empty.style.display = d ? 'none' : '';
    this.grid.style.display = d ? '' : 'none';
    this.copyBtn.disabled = !d;
    this.gid = d?.globalId ?? '';
    if (!d) {
      this.moreEl.textContent = '';
      return;
    }
    for (const [key] of FIELDS) {
      const dd = this.values.get(key)!;
      const t = this.texts.get(key)!;
      const text = fmtVal(d[key]);
      if (t.textContent !== text) {
        t.textContent = text;
        dd.title = text;
      }
    }
    const more = d.more > 0 ? `+ ${d.more} more selected` : '';
    if (this.moreEl.textContent !== more) this.moreEl.textContent = more;
  }

  private rowValues: string[] = [];
  private rowsKey = '';

  /** The collapsible list of the first selected element's properties (rows come from the provider). */
  renderRows(): void {
    const res = this.last && rowsProvider ? rowsProvider(this.last.globalId) : null;
    if (!this.last || !res) {
      this.listEl.style.display = 'none';
      this.rowsKey = '';
      return;
    }
    this.listEl.style.display = '';
    const key = `${this.last.globalId}|${res.total}|${res.rows.map(([k, v]) => `${k}=${String(v)}`).join('\n')}`;
    if (key === this.rowsKey) return;
    this.rowsKey = key;
    this.listSummary.textContent = res.rows.length === res.total ? `Properties (${res.total})` : `Properties (${res.rows.length} of ${res.total})`;
    this.listRows.textContent = '';
    this.rowValues = [];
    this.rowRaw = res.rows.map(([k, v]) => [k, v]);
    const labelCount = new Map<string, number>();
    for (const [k] of res.rows) labelCount.set(propLabel(k), (labelCount.get(propLabel(k)) ?? 0) + 1);
    res.rows.forEach(([k, v], i) => {
      const label = labelCount.get(propLabel(k)) === 1 ? propLabel(k) : k; // the set name only where the bare name is ambiguous
      const text = typeof v === 'boolean' ? (v ? 'Yes' : 'No') : String(v);
      const dt = el('dt', '', { 'data-row': String(i), title: `${k} (click to copy the value)` }, label);
      const dd = el('dd', '', { 'data-row': String(i), title: text });
      dd.append(el('span', 'pv-t', {}, text), this.moreBtn(label));
      this.rowValues.push(text);
      this.listRows.append(dt, dd);
    });
    if (res.rows.length === 0) this.listRows.append(el('dt', '', {}, 'No property matches the filter'));
  }

  private moreBtn(label: string): HTMLButtonElement {
    return el(
      'button',
      'pv-more',
      { type: 'button', 'aria-haspopup': 'menu', 'aria-expanded': 'false', 'aria-label': `Actions for ${label}`, title: 'Select by this value, copy, save as set', 'data-help-key': 'Sidebar/Property menu', 'data-help-title': 'Property menu' },
      '⋯',
    );
  }

  /** The query column, raw value and labels of an attribute or property cell; null when the cell has none. */
  private cellInfo(cell: HTMLElement): { column: string | null; value: string | number | boolean | null; label: string; text: string } | null {
    const d = this.last;
    if (!d) return null;
    const field = cell.dataset['field'] as keyof PropsData | undefined;
    if (field) {
      const label = FIELDS.find(([k]) => k === field)?.[1] ?? field;
      const col = FIELD_COLUMN[field] ?? null;
      let value: string | number | boolean | null = d[field] as string | number;
      if (field === 'storey') value = d.storeyName !== undefined ? d.storeyName : d.storey;
      if ((field === 'name' || field === 'material') && value === '') value = null;
      return { column: col, value, label, text: fmtVal(d[field]) };
    }
    const row = cell.dataset['row'];
    const raw = row === undefined ? undefined : this.rowRaw[Number(row)];
    if (!raw) return null;
    const [k, v] = raw;
    return { column: k, value: v, label: propLabel(k), text: typeof v === 'boolean' ? (v ? 'Yes' : 'No') : String(v) };
  }

  private openRowMenu(cell: HTMLElement, at: HTMLElement | { x: number; y: number }): void {
    const info = this.cellInfo(cell);
    if (!info) return;
    const { column, value, label, text } = info;
    const pair = Array.from(cell.parentElement?.children ?? []).filter(
      (n) => (n as HTMLElement).dataset['row'] === cell.dataset['row'] && (n as HTMLElement).dataset['field'] === cell.dataset['field'],
    ) as HTMLElement[];
    for (const n of pair) n.classList.add('pv-row-hit');
    const eq = column !== null && this.actions ? equalsQuery(column, value) : null;
    const nullable = column !== null && column !== 'class' && column !== 'globalId';
    const items: MenuItem[] = [];
    if (eq) {
      items.push(
        { label: 'Select all with this value', act: 'eq', title: eq },
        { label: 'Add to selection all with this value', act: 'eqAdd', title: eq },
      );
      if (nullable) items.push({ label: 'Select all with this property', act: 'has', title: `${quoteIdent(column!)} IS NOT NULL` });
    }
    items.push({ label: 'Copy value', act: 'copy', disabled: text === '-' });
    if (eq) items.push({ label: 'Save as criteria set…', act: 'save', title: eq });
    const heading = column && !FIELD_COLUMN[cell.dataset['field'] as keyof PropsData] ? column : `${label}: ${text}`;
    openMenu({
      at,
      items,
      heading,
      label: `Actions for ${label}`,
      returnFocus: at instanceof HTMLElement ? at : null,
      onClose: () => {
        for (const n of pair) n.classList.remove('pv-row-hit');
      },
      onPick: (act) => {
        if (act === 'copy') {
          void copyText(text);
          return;
        }
        if (!eq || !this.actions || column === null) return;
        if (act === 'eq' || act === 'eqAdd') this.actions.selectWhere(eq, act === 'eqAdd');
        else if (act === 'has') this.actions.selectWhere(`${quoteIdent(column)} IS NOT NULL`, false);
        else if (act === 'save') {
          const name = cell.dataset['field'] === 'ifcClass' ? text : value === null ? `No ${label.toLowerCase()}` : `${label} = ${text}`;
          this.actions.saveCriteria(eq, name);
        }
      },
    });
  }
}
