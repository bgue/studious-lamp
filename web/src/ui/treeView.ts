// DOM renderer for the model tree. Virtualised: the flat list of visible rows is windowed, so only rows in (or just
// around) the viewport exist in the DOM, however many branches are expanded. Row height is fixed.

import type { ElementId, SceneModel } from '../types';
import { allParentKeys, buildTree, defaultExpanded, elementPath, filterTree, flattenTree } from './treeModel';
import type { FlatRow, TreeNode } from './treeModel';
import { esc } from './dom';

export const ROW_H = 22;
const OVERSCAN = 6;

export interface TreeHost {
  selection(): ReadonlySet<ElementId>;
  bucketOf(id: ElementId): string;
  hidden(): ReadonlySet<ElementId>;
  select(ids: ElementId[], additive: boolean): void;
  setHidden(ids: ElementId[], hide: boolean): void;
  hover(id: ElementId | null): void;
}

const EYE =
  '<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path d="M1 8s2.5-4.5 7-4.5S15 8 15 8s-2.5 4.5-7 4.5S1 8 1 8z" fill="none" stroke="currentColor" stroke-width="1.3"/><circle cx="8" cy="8" r="2" fill="currentColor"/></svg>';
const EYE_OFF =
  '<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path d="M1 8s2.5-4.5 7-4.5S15 8 15 8s-2.5 4.5-7 4.5S1 8 1 8z" fill="none" stroke="currentColor" stroke-width="1.3"/><path d="M2 14L14 2" stroke="currentColor" stroke-width="1.5"/></svg>';

export class TreeView {
  readonly root: HTMLDivElement;
  private readonly scroller: HTMLDivElement;
  private readonly spacer: HTMLDivElement;
  private readonly win: HTMLDivElement;
  private model: SceneModel | null = null;
  private roots: TreeNode[] = [];
  private rows: FlatRow[] = [];
  private expanded = new Set<string>();
  private savedExpanded: Set<string> | null = null;
  private query = '';
  private lastHtml = '';
  private lastStart = -1;
  private raf = 0;

  constructor(private readonly host: TreeHost) {
    this.root = document.createElement('div');
    this.root.className = 'tv';
    this.scroller = document.createElement('div');
    this.scroller.className = 'tv-scroll';
    this.scroller.setAttribute('role', 'tree');
    this.spacer = document.createElement('div');
    this.spacer.className = 'tv-spacer';
    this.win = document.createElement('div');
    this.win.className = 'tv-win';
    this.spacer.appendChild(this.win);
    this.scroller.appendChild(this.spacer);
    this.root.appendChild(this.scroller);

    this.scroller.addEventListener('scroll', () => {
      if (this.raf) return;
      this.raf = requestAnimationFrame(() => {
        this.raf = 0;
        this.render();
      });
    });
    this.win.addEventListener('click', (e) => this.onClick(e));
    this.win.addEventListener('mouseover', (e) => this.onHover(e));
    this.scroller.addEventListener('mouseleave', () => host.hover(null));
  }

  /** Rebuild for a new model. */
  setModel(model: SceneModel): void {
    this.model = model;
    this.query = '';
    this.savedExpanded = null;
    this.roots = buildTree(model);
    this.expanded = defaultExpanded(this.roots);
    this.rebuildRows();
    this.scroller.scrollTop = 0;
    this.render(true);
  }

  /** Filter by name, globalId or class substring. Empty restores the full tree and the previous expansion. */
  setFilter(query: string): void {
    if (!this.model) return;
    const q = query.trim().toLowerCase();
    if (q === this.query) return;
    const wasFiltered = this.query !== '';
    this.query = q;
    if (q) {
      if (!wasFiltered) this.savedExpanded = this.expanded;
      this.roots = filterTree(this.model, q);
      this.expanded = allParentKeys(this.roots);
    } else {
      this.roots = buildTree(this.model);
      this.expanded = this.savedExpanded ?? defaultExpanded(this.roots);
      this.savedExpanded = null;
    }
    this.rebuildRows();
    this.scroller.scrollTop = 0;
    this.render(true);
  }

  get filtered(): boolean {
    return this.query !== '';
  }

  /** Number of elements shown (matches while filtering, else all). */
  visibleElementCount(): number {
    let n = 0;
    for (const r of this.roots) if (r.kind === 'storey') n += r.count;
    return n;
  }

  /** Expand storey and class of the element and scroll its row into view. Returns false when it is not shown. */
  reveal(id: ElementId): boolean {
    if (!this.model) return false;
    const p = elementPath(this.model, id);
    if (!p) return false;
    this.expanded.add(p.storey);
    this.expanded.add(p.cls);
    this.rebuildRows();
    const i = this.rows.findIndex((r) => r.node.key === p.element);
    if (i < 0) {
      this.render(true);
      return false;
    }
    const h = this.scroller.clientHeight || 300;
    const top = i * ROW_H;
    if (top < this.scroller.scrollTop || top + ROW_H > this.scroller.scrollTop + h) {
      this.scroller.scrollTop = Math.max(0, top - h / 2 + ROW_H / 2);
    }
    this.render(true);
    return true;
  }

  /** Re-render the visible window if anything it shows changed. Cheap enough for a 250 ms timer. */
  refresh(): void {
    this.render();
  }

  private rebuildRows(): void {
    this.rows = flattenTree(this.roots, (k) => this.expanded.has(k));
    this.spacer.style.height = `${this.rows.length * ROW_H}px`;
    this.lastHtml = '';
  }

  private render(force = false): void {
    const h = this.scroller.clientHeight || 400;
    const top = this.scroller.scrollTop;
    const start = Math.max(0, Math.floor(top / ROW_H) - OVERSCAN);
    const end = Math.min(this.rows.length, Math.ceil((top + h) / ROW_H) + OVERSCAN);
    const sel = this.host.selection();
    const hid = this.host.hidden();
    let html = '';
    for (let i = start; i < end; i++) html += this.rowHtml(i, this.rows[i]!, sel, hid);
    if (this.rows.length === 0) html = `<div class="tv-empty">${this.query ? 'No matching elements' : 'No elements'}</div>`;
    if (!force && start === this.lastStart && html === this.lastHtml) return;
    this.lastStart = start;
    this.lastHtml = html;
    this.win.style.transform = `translateY(${start * ROW_H}px)`;
    this.win.innerHTML = html;
  }

  private rowHtml(i: number, row: FlatRow, sel: ReadonlySet<ElementId>, hid: ReadonlySet<ElementId>): string {
    const n = row.node;
    let selected = false;
    let hiddenAll = false;
    let hiddenSome = false;
    let dot = '';
    if (n.elementId !== null) {
      selected = sel.has(n.elementId);
      hiddenAll = hid.has(n.elementId);
      dot = `<span class="dot b-${this.host.bucketOf(n.elementId)}" title="${this.host.bucketOf(n.elementId)}"></span>`;
    } else {
      if (sel.size > 0 && n.count > 0) selected = n.ids.every((id) => sel.has(id));
      if (hid.size > 0) {
        let some = false;
        let all = true;
        for (const id of n.ids) {
          if (hid.has(id)) some = true;
          else all = false;
          if (some && !all) break;
        }
        hiddenAll = all && n.count > 0;
        hiddenSome = some && !all;
      }
      dot = '<span class="dot"></span>';
    }
    const caret = row.hasChildren
      ? `<span class="caret${row.expanded ? ' open' : ''}" data-act="caret"></span>`
      : '<span class="caret none"></span>';
    const eyeCls = hiddenAll ? ' off' : hiddenSome ? ' part' : '';
    const cnt = n.elementId === null ? `<span class="cnt">${n.count}</span>` : '';
    const attrs = row.hasChildren ? ` aria-expanded="${row.expanded}"` : '';
    return (
      `<div class="tr k-${n.kind}${selected ? ' sel' : ''}${hiddenAll ? ' hid' : ''}" role="treeitem" data-i="${i}" data-key="${esc(n.key)}"${attrs}` +
      ` style="padding-left:${4 + row.depth * 14}px" title="${esc(n.title)}">` +
      `${caret}<span class="lbl">${esc(n.label)}</span>${cnt}` +
      `<span class="eye${eyeCls}" data-act="eye" title="${hiddenAll ? 'Show' : 'Hide'}">${hiddenAll ? EYE_OFF : EYE}</span>${dot}</div>`
    );
  }

  private rowOf(target: EventTarget | null): { row: FlatRow; act: string | null } | null {
    const t = (target as HTMLElement | null)?.closest<HTMLElement>('.tr');
    if (!t) return null;
    const row = this.rows[Number(t.dataset['i'])];
    if (!row) return null;
    const a = (target as HTMLElement).closest<HTMLElement>('[data-act]');
    return { row, act: a ? (a.dataset['act'] ?? null) : null };
  }

  private onClick(e: MouseEvent): void {
    const hit = this.rowOf(e.target);
    if (!hit) return;
    const { row, act } = hit;
    const n = row.node;
    if (act === 'caret') {
      this.toggle(n.key);
    } else if (act === 'eye') {
      const hidden = this.host.hidden();
      const allHidden = n.ids.length > 0 && n.ids.every((id) => hidden.has(id));
      this.host.setHidden(n.ids, !allHidden);
      this.render(true);
    } else {
      this.host.select(n.ids, e.shiftKey);
    }
  }

  private toggle(key: string): void {
    if (this.expanded.has(key)) this.expanded.delete(key);
    else this.expanded.add(key);
    this.rebuildRows();
    this.render(true);
  }

  private onHover(e: MouseEvent): void {
    const hit = this.rowOf(e.target);
    this.host.hover(hit && hit.row.node.elementId !== null ? hit.row.node.elementId : null);
  }
}
