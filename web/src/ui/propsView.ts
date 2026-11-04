// Properties footer: details of the first selected element.

import { copyText, el } from './dom';

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
    this.root.append(head, this.empty, this.grid, this.moreEl);
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
}
