// DOM renderer for the model tree. Virtualised: the flat list of visible rows is windowed, so only rows in (or just
// around) the viewport exist in the DOM, however many branches are expanded. Row height is fixed.

import type { ElementId, SceneModel } from '../types';
import { allParentKeys, buildTree, defaultExpanded, elementPath, filterTree, flattenTree } from './treeModel';
import type { FlatRow, TreeNode } from './treeModel';
import { esc } from './dom';
import { EMPTY_TYPE_AHEAD, TYPE_AHEAD_MS, isTypeAheadChar, leftMove, moveActive, rightMove, siblingKeysToOpen, typeAhead } from './treeKeys';
import type { TypeAheadState } from './treeKeys';

export const ROW_H = 22;
const OVERSCAN = 6;

export interface TreeHost {
  selection(): ReadonlySet<ElementId>;
  bucketOf(id: ElementId): string;
  hidden(): ReadonlySet<ElementId>;
  select(ids: ElementId[], additive: boolean): void;
  setHidden(ids: ElementId[], hide: boolean): void;
  hover(id: ElementId | null): void;
  /** Classification tree: "Save as set" on a group row. */
  saveSet?(node: TreeNode): void;
  /** True when an enabled global action would take this key: the tree then leaves the letter to it instead of type-ahead. */
  isGlobalKey?(e: KeyboardEvent): boolean;
}

let uidCounter = 0;

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
  /** True while the rows come from setRoots (the classification tree) and not from the model. */
  private custom = false;
  private modelState: { expanded: Set<string> } | null = null;
  private query = '';
  private lastHtml = '';
  private lastStart = -1;
  private raf = 0;
  /** Key of the active row (keyboard cursor). Survives virtualisation and rebuilds; the row is found by key. */
  private activeKey: string | null = null;
  private ta: TypeAheadState = EMPTY_TYPE_AHEAD;
  private readonly uid = `tv${++uidCounter}`;

  constructor(private readonly host: TreeHost) {
    this.root = document.createElement('div');
    this.root.className = 'tv';
    this.scroller = document.createElement('div');
    this.scroller.className = 'tv-scroll';
    this.scroller.setAttribute('role', 'tree');
    this.scroller.setAttribute('aria-label', 'Model tree');
    this.scroller.setAttribute('aria-multiselectable', 'true');
    this.scroller.tabIndex = 0;
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
    this.scroller.addEventListener('keydown', (e) => this.onKey(e));
    this.scroller.addEventListener('focus', () => this.onFocus());
    // A pointer press sets the active row before the focus event, so the focus handler does not re-render under the click.
    this.win.addEventListener('mousedown', (e) => {
      const key = (e.target as HTMLElement | null)?.closest<HTMLElement>('.tr')?.dataset['key'];
      if (key) this.activeKey = key;
    });
    this.win.addEventListener('click', (e) => this.onClick(e));
    this.win.addEventListener('mouseover', (e) => this.onHover(e));
    this.scroller.addEventListener('mouseleave', () => host.hover(null));
  }

  /** Rebuild for a new model. */
  setModel(model: SceneModel): void {
    this.model = model;
    this.custom = false;
    this.modelState = null;
    this.scroller.setAttribute('aria-label', 'Model tree');
    this.activeKey = null;
    this.query = '';
    this.savedExpanded = null;
    this.roots = buildTree(model);
    this.expanded = defaultExpanded(this.roots);
    this.rebuildRows();
    this.scroller.scrollTop = 0;
    this.render(true);
  }

  /**
   * Show a ready-made tree (the classification tree) instead of the model tree; null returns to the model tree. `expand` replaces
   * the expansion (a new grouping); without it the expansion and the active row stay (the same grouping, new values).
   */
  setRoots(roots: TreeNode[] | null, expand?: Set<string>): void {
    if (!this.model) return;
    if (roots) {
      if (!this.custom) {
        this.modelState = { expanded: this.expanded };
        this.custom = true;
        this.activeKey = null;
        this.expanded = expand ?? new Set();
        this.scroller.setAttribute('aria-label', 'Classification tree');
        this.scroller.scrollTop = 0;
      } else if (expand) {
        this.expanded = expand;
        this.scroller.scrollTop = 0;
      }
      this.roots = roots;
    } else if (this.custom) {
      this.custom = false;
      this.query = '';
      this.savedExpanded = null;
      this.roots = buildTree(this.model);
      this.expanded = this.modelState?.expanded ?? defaultExpanded(this.roots);
      this.modelState = null;
      this.activeKey = null;
      this.scroller.setAttribute('aria-label', 'Model tree');
      this.scroller.scrollTop = 0;
    } else return;
    this.rebuildRows();
    this.render(true);
  }

  get showsClassification(): boolean {
    return this.custom;
  }

  /** Filter by name, globalId or class substring. Empty restores the full tree and the previous expansion. */
  setFilter(query: string): void {
    if (!this.model || this.custom) return;
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
    for (const r of this.roots) if (r.kind === 'storey' || this.custom) n += r.count;
    return n;
  }

  /** Expand storey and class of the element and scroll its row into view. Returns false when it is not shown. */
  reveal(id: ElementId): boolean {
    if (!this.model) return false;
    if (this.custom) return this.revealCustom(id);
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
    this.activeKey = p.element;
    const h = this.scroller.clientHeight || 300;
    const top = i * ROW_H;
    if (top < this.scroller.scrollTop || top + ROW_H > this.scroller.scrollTop + h) {
      this.scroller.scrollTop = Math.max(0, top - h / 2 + ROW_H / 2);
    }
    this.render(true);
    return true;
  }

  private revealCustom(id: ElementId): boolean {
    const path: string[] = [];
    const find = (n: TreeNode): string | null => {
      if (n.elementId === id) return n.key;
      if (n.children.length === 0 || !n.ids.includes(id)) return null;
      path.push(n.key);
      for (const c of n.children) {
        const k = find(c);
        if (k) return k;
      }
      path.pop();
      return null;
    };
    let key: string | null = null;
    for (const r of this.roots) if ((key = find(r))) break;
    if (!key) return false;
    for (const k of path) this.expanded.add(k);
    this.rebuildRows();
    const i = this.rows.findIndex((r) => r.node.key === key);
    if (i < 0) return false;
    this.activeKey = key;
    const h = this.scroller.clientHeight || 300;
    const top = i * ROW_H;
    if (top < this.scroller.scrollTop || top + ROW_H > this.scroller.scrollTop + h) this.scroller.scrollTop = Math.max(0, top - h / 2 + ROW_H / 2);
    this.render(true);
    return true;
  }

  /** The scroller element (the one Tab stop of the tree). */
  get focusEl(): HTMLElement {
    return this.scroller;
  }

  /** Move keyboard focus into the tree. The active row stays, else the first selected row, else the first row. */
  focus(): void {
    this.scroller.focus({ preventScroll: true });
  }

  /** Key of the active row, or null. For tests and scripts. */
  get activeRowKey(): string | null {
    return this.activeIndex() >= 0 ? this.activeKey : null;
  }

  private activeIndex(): number {
    if (this.activeKey === null) return -1;
    return this.rows.findIndex((r) => r.node.key === this.activeKey);
  }

  private onFocus(): void {
    const had = this.activeIndex() >= 0;
    if (!had) {
      const sel = this.host.selection();
      let i = sel.size > 0 ? this.rows.findIndex((r) => r.node.elementId !== null && sel.has(r.node.elementId)) : -1;
      if (i < 0 && sel.size > 0) i = this.rows.findIndex((r) => r.node.count > 0 && r.node.ids.every((id) => sel.has(id)));
      if (i < 0) i = this.rows.length > 0 ? 0 : -1;
      this.activeKey = i >= 0 ? this.rows[i]!.node.key : null;
      if (i >= 0) this.ensureVisible(i);
    }
    // The ring shows through CSS (:focus .tr.act); render only when the active row had to be chosen.
    if (!had) this.render(true);
  }

  private ensureVisible(i: number): void {
    const h = this.scroller.clientHeight || 300;
    const top = i * ROW_H;
    const st = this.scroller.scrollTop;
    if (top < st) this.scroller.scrollTop = top;
    else if (top + ROW_H > st + h) this.scroller.scrollTop = top + ROW_H - h;
  }

  private setActive(i: number): void {
    const r = this.rows[i];
    if (!r) return;
    this.activeKey = r.node.key;
    this.ensureVisible(i);
    this.render(true);
  }

  private page(): number {
    return Math.max(1, Math.floor((this.scroller.clientHeight || 300) / ROW_H) - 1);
  }

  private selectRow(i: number, how: 'replace' | 'toggle' | 'extend'): void {
    const n = this.rows[i]?.node;
    if (!n) return;
    if (how === 'replace') this.host.select(n.ids, false);
    else if (how === 'extend') this.host.select(n.ids, true);
    else {
      const sel = this.host.selection();
      const all = n.ids.length > 0 && n.ids.every((id) => sel.has(id));
      const drop = new Set(n.ids);
      const next = all ? [...sel].filter((id) => !drop.has(id)) : [...sel, ...n.ids.filter((id) => !sel.has(id))];
      this.host.select(next, false);
    }
    this.render(true);
  }

  private onKey(e: KeyboardEvent): void {
    if (e.target !== this.scroller || e.isComposing || this.rows.length === 0) return;
    if (e.ctrlKey && !e.altKey && !e.metaKey && e.key === ' ') {
      this.consume(e);
      this.ensureActive();
      const i = this.activeIndex();
      if (i >= 0) this.selectRow(i, 'toggle');
      return;
    }
    if (e.ctrlKey || e.metaKey) return;
    const k = e.key;
    if (this.ensureActive() < 0) return;
    const i = this.activeIndex();
    if (e.altKey) {
      if (isTypeAheadChar(k) && !this.host.isGlobalKey?.(e)) this.typeAheadKey(e, i);
      return;
    }
    if (e.shiftKey) {
      if (k === 'ArrowUp' || k === 'ArrowDown') {
        this.consume(e);
        const j = moveActive(this.rows, i, k, 1);
        this.setActive(j);
        this.selectRow(j, 'extend');
      } else if (isTypeAheadChar(k) && !this.host.isGlobalKey?.(e)) this.typeAheadKey(e, i);
      else if (k === '*') {
        this.consume(e);
        this.setExpanded(siblingKeysToOpen(this.rows, i), true);
      }
      return;
    }
    switch (k) {
      case 'ArrowDown':
      case 'ArrowUp':
      case 'Home':
      case 'End':
      case 'PageDown':
      case 'PageUp':
        this.consume(e);
        this.setActive(moveActive(this.rows, i, k, this.page()));
        return;
      case 'ArrowRight':
      case 'ArrowLeft': {
        this.consume(e);
        const m = k === 'ArrowRight' ? rightMove(this.rows, i) : leftMove(this.rows, i);
        if (m.type === 'open' || m.type === 'close') this.setExpanded([m.key], m.type === 'open');
        else if (m.type === 'move') this.setActive(m.index);
        return;
      }
      case 'Enter':
      case ' ':
        this.consume(e);
        this.selectRow(i, 'replace');
        return;
      case '*':
        this.consume(e);
        this.setExpanded(siblingKeysToOpen(this.rows, i), true);
        return;
      default:
        if (isTypeAheadChar(k)) {
          const continuing = this.ta.buffer !== '' && performance.now() - this.ta.at <= TYPE_AHEAD_MS;
          if (continuing || !this.host.isGlobalKey?.(e)) this.typeAheadKey(e, i);
        }
    }
  }

  private ensureActive(): number {
    if (this.activeIndex() < 0) this.onFocus();
    return this.activeIndex();
  }

  private typeAheadKey(e: KeyboardEvent, i: number): void {
    this.consume(e);
    const r = typeAhead(this.rows, i, this.ta, e.key, performance.now());
    this.ta = r.state;
    if (r.index >= 0) this.setActive(r.index);
  }

  private consume(e: KeyboardEvent): void {
    e.preventDefault();
    e.stopPropagation();
  }

  private setExpanded(keys: string[], open: boolean): void {
    if (keys.length === 0) return;
    for (const k of keys) {
      if (open) this.expanded.add(k);
      else this.expanded.delete(k);
    }
    this.rebuildRows();
    this.render(true);
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
    const act = this.activeIndex();
    for (let i = start; i < end; i++) html += this.rowHtml(i, this.rows[i]!, sel, hid, i === act);
    if (this.rows.length === 0) html = `<div class="tv-empty">${this.query ? 'No matching elements' : this.custom ? 'No elements to show' : 'No elements'}</div>`;
    if (!force && start === this.lastStart && html === this.lastHtml) return;
    this.lastStart = start;
    this.lastHtml = html;
    this.win.style.transform = `translateY(${start * ROW_H}px)`;
    this.win.innerHTML = html;
    this.syncActiveDescendant();
  }

  private syncActiveDescendant(): void {
    const i = this.activeIndex();
    if (i >= 0 && this.win.querySelector(`#${this.uid}-${i}`)) this.scroller.setAttribute('aria-activedescendant', `${this.uid}-${i}`);
    else this.scroller.removeAttribute('aria-activedescendant');
  }

  private rowHtml(i: number, row: FlatRow, sel: ReadonlySet<ElementId>, hid: ReadonlySet<ElementId>, active: boolean): string {
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
    let cnt = n.elementId === null ? `<span class="cnt">${n.count}</span>` : '';
    if (this.custom && n.review) {
      const pct = Math.max(1, Math.round((100 * n.review) / Math.max(1, n.count)));
      if (n.elementId === null) cnt = `<span class="rv" title="${n.review} of ${n.count} need review">${pct}%</span>${cnt}`;
      else cnt = '<span class="rv" title="Needs review">!</span>';
    }
    const save = this.custom && n.elementId === null && this.host.saveSet ? '<span class="sv" data-act="save" title="Save as set">+set</span>' : '';
    const attrs = row.hasChildren ? ` aria-expanded="${row.expanded}"` : '';
    return (
      `<div class="tr k-${n.kind}${selected ? ' sel' : ''}${hiddenAll ? ' hid' : ''}${active ? ' act' : ''}" role="treeitem" id="${this.uid}-${i}" aria-selected="${selected}" aria-level="${row.depth + 1}" data-i="${i}" data-key="${esc(n.key)}"${attrs}` +
      ` style="padding-left:${4 + row.depth * 14}px" title="${esc(n.title)}">` +
      `${caret}<span class="lbl">${esc(n.label)}</span>${cnt}${save}` +
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
    this.activeKey = n.key;
    if (act === 'caret') {
      this.toggle(n.key);
    } else if (act === 'save') {
      this.host.saveSet?.(n);
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
