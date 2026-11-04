// Properties footer: details of the first selected element.

import { copyText, el } from './dom';
import { propLabel } from './hoverCard';

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

  constructor() {
    this.root = el('div', 'props');
    const head = el('div', 'props-head');
    head.append(el('span', 'props-title', {}, 'Properties'));
    this.copyBtn = el('button', 'btn', { type: 'button', title: 'Copy the GlobalId of the first selected element' }, 'Copy GlobalId');
    this.copyBtn.disabled = true;
    head.append(this.copyBtn);
    this.empty = el('div', 'props-empty', {}, 'No selection');
    this.grid = el('dl', 'props-grid');
    for (const [key, label] of FIELDS) {
      const dt = el('dt', '', {}, label);
      const dd = el('dd');
      this.values.set(key, dd);
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
    this.listRows.addEventListener('click', async (ev) => {
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
      const text = fmtVal(d[key]);
      if (dd.textContent !== text) {
        dd.textContent = text;
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
    const labelCount = new Map<string, number>();
    for (const [k] of res.rows) labelCount.set(propLabel(k), (labelCount.get(propLabel(k)) ?? 0) + 1);
    res.rows.forEach(([k, v], i) => {
      const label = labelCount.get(propLabel(k)) === 1 ? propLabel(k) : k; // the set name only where the bare name is ambiguous
      const text = typeof v === 'boolean' ? (v ? 'Yes' : 'No') : String(v);
      const dt = el('dt', '', { 'data-row': String(i), title: `${k} (click to copy the value)` }, label);
      const dd = el('dd', '', { 'data-row': String(i), title: text }, text);
      this.rowValues.push(text);
      this.listRows.append(dt, dd);
    });
    if (res.rows.length === 0) this.listRows.append(el('dt', '', {}, 'No property matches the filter'));
  }
}
