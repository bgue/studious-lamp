// The review walk: a panel over the viewer that visits the classified elements in a logical order, shows the proposal with its confidence
// and source, and records a confirmation, a runner-up pick or a correction as a pending change. "Commit" turns the pending changes into
// one commit of the review log (classify/reviewLog.ts). The panel works with the keyboard (Enter or Y, 2, E, N or the right arrow, the left
// arrow) and with buttons, so it also works on a phone. The reviewer's name is kept in this browser and nowhere else.
// Docs: docs-features/classify.md, section "Review walk".

import { Box3, Vector3 } from 'three';
import type { ViewerApp } from '../app';
import { getKeymap } from '../input/keymap';
import { currentPose, moveToBox, moveToPose, navSettings } from '../input/navigation';
import type { Pose } from '../input/navigation';
import { overallConfidence } from '../classify/review';
import { divisionTitle, findDiscipline, findSub } from '../classify/schema';
import { buildWalk, runnerUp, walkElementsOf, walkProgress, walkScope, WALK_ORDER_LABEL, WALK_ORDERS } from '../classify/reviewWalk';
import type { RunnerUp, WalkElement, WalkItem, WalkOrder } from '../classify/reviewWalk';
import type { ReviewCommit } from '../classify/reviewLog';
import type { ClassifyService } from '../classify/service';
import type { ClassifyResult } from '../classify/types';
import { downloadText } from '../tools/csv';
import { ensureKeyStyles, showToast } from '../ui/keymapView';
import { el } from '../ui/dom';
import { STATUS_H } from '../ui/statusBar';

const STYLE_ID = 'xray-review-walk-style';
const CSS = `
.xrw{position:absolute;left:52px;bottom:${STATUS_H + 10}px;width:min(420px,calc(100% - 64px));max-height:calc(100% - ${STATUS_H + 70}px);z-index:16;box-sizing:border-box;display:flex;flex-direction:column;background:rgba(20,24,32,.97);color:var(--sb-fg,#dfe6ee);border:1px solid #2d3748;border-radius:6px;font:12px/1.35 system-ui,-apple-system,'Segoe UI',sans-serif;box-shadow:0 6px 24px rgba(0,0,0,.45)}
.xrw[hidden]{display:none}
.xrw *{box-sizing:border-box}
.xrw-head{display:flex;align-items:center;gap:8px;padding:6px 8px;border-bottom:1px solid var(--sb-line,#262d3a)}
.xrw-title{font-weight:600;flex:0 0 auto}
.xrw-prog{flex:1 1 auto;color:var(--sb-dim,#8d99a8);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.xrw-x{background:transparent;border:0;color:var(--sb-dim,#8d99a8);cursor:pointer;font-size:18px;line-height:1;padding:0 4px}
.xrw-x:hover{color:#fff}
.xrw-tabs{display:flex;gap:2px;padding:4px 8px 0}
.xrw-tab{background:transparent;border:1px solid transparent;border-bottom:0;color:var(--sb-dim,#8d99a8);padding:3px 10px;border-radius:4px 4px 0 0;cursor:pointer;font:inherit}
.xrw-tab.on{background:#10141b;border-color:var(--sb-line,#262d3a);color:#fff}
.xrw-body{flex:1 1 auto;min-height:0;overflow:auto;padding:8px;display:flex;flex-direction:column;gap:7px;background:#10141b}
.xrw-bar{display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.xrw-bar label{display:flex;align-items:center;gap:4px;color:var(--sb-dim,#8d99a8)}
.xrw select,.xrw input[type=text]{background:#0e1218;color:inherit;border:1px solid var(--sb-line,#262d3a);border-radius:3px;height:24px;padding:0 5px;font:inherit;min-width:0}
.xrw input[type=text]{width:100%}
.xrw select:focus-visible,.xrw input:focus-visible,.xrw button:focus-visible{outline:1px solid var(--sb-accent,#3b9cff)}
.xrw-item{font-weight:600;font-size:13px;overflow-wrap:anywhere}
.xrw-meta{color:var(--sb-dim,#8d99a8);overflow-wrap:anywhere}
.xrw-tbl{border-collapse:collapse;width:100%}
.xrw-tbl th{color:var(--sb-dim,#8d99a8);text-align:left;font-weight:600;font-size:10px;text-transform:uppercase;letter-spacing:.05em;padding:2px 4px}
.xrw-tbl td{padding:3px 4px;border-top:1px solid #1a202b;vertical-align:top;overflow-wrap:anywhere}
.xrw-warn{color:#e0b252}
.xrw-err{color:#ff8f8f}
.xrw-ok{color:#9fe3b0}
.xrw-dim{color:var(--sb-dim,#8d99a8)}
.xrw-box{border:1px solid #2d6aa8;border-radius:4px;background:#0e141d;padding:7px;display:flex;flex-direction:column;gap:6px}
.xrw-box label{display:flex;flex-direction:column;gap:2px;align-items:stretch;color:var(--sb-dim,#8d99a8)}
.xrw-box select{width:100%}
.xrw-acts{display:grid;grid-template-columns:repeat(auto-fit,minmax(104px,1fr));gap:6px}
.xrw-btn{background:#1b2230;color:inherit;border:1px solid #2d3748;border-radius:4px;padding:5px 8px;cursor:pointer;font:inherit;text-align:center;line-height:1.2}
.xrw-btn:hover:not(:disabled){background:#243049;border-color:#3a4a66}
.xrw-btn:disabled{opacity:.45;cursor:default}
.xrw-btn.primary{background:#1f4a7a;border-color:#2d6aa8;color:#fff}
.xrw-btn kbd{font:inherit;font-size:10px;color:var(--sb-dim,#8d99a8);margin-left:4px;border:1px solid #2d3748;border-radius:3px;padding:0 3px}
.xrw-foot{display:flex;flex-wrap:wrap;gap:6px;align-items:center;padding:6px 8px;border-top:1px solid var(--sb-line,#262d3a)}
.xrw-foot input[type=text]{flex:1 1 120px;width:auto}
.xrw-row{display:flex;gap:6px;align-items:center;flex-wrap:wrap}
.xrw-row .grow{flex:1 1 auto;min-width:0}
.xrw-commit{border:1px solid #1a202b;border-radius:4px;padding:5px 6px;display:flex;flex-direction:column;gap:4px}
.xrw-commit.rev{border-style:dashed}
.xrw-changes{font-size:11px;color:var(--sb-dim,#8d99a8);display:flex;flex-direction:column;gap:2px;max-height:160px;overflow:auto}
@media (max-width:760px){
  .xrw{left:var(--sb-rail,28px);right:var(--dk-rail,28px);width:auto;bottom:${STATUS_H}px;max-height:62%;border-radius:10px 10px 0 0;font-size:13px}
  .xrw-btn{padding:10px 8px;font-size:14px}
  .xrw-acts{grid-template-columns:1fr 1fr}
  .xrw-btn kbd{display:none}
  .xrw select,.xrw input[type=text]{height:34px;font-size:14px}
  .xrw-x{font-size:24px;padding:0 8px}
}
`;

function ensureStyle(): void {
  if (document.getElementById(STYLE_ID)) return;
  const st = document.createElement('style');
  st.id = STYLE_ID;
  st.textContent = CSS;
  document.head.appendChild(st);
}

const pct = (x: number): string => `${Math.round(x * 100)}%`;
const when = (iso: string): string => (iso.length >= 16 ? `${iso.slice(0, 10)} ${iso.slice(11, 16)}` : iso);

export interface WalkState {
  open: boolean;
  order: WalkOrder;
  filters: { needsReview: boolean; unconfirmed: boolean; discipline: string };
  scope: 'all' | 'one';
  tab: 'walk' | 'pending' | 'history';
  itemIndex: number;
  items: number;
  elementIndex: number;
  item: { key: string; title: string; elements: number } | null;
  progress: { confirmed: number; corrected: number; remaining: number; total: number };
  pending: number;
  editing: boolean;
}

export class ReviewWalk {
  private root: HTMLElement | null = null;
  private body!: HTMLElement;
  private head!: HTMLElement;
  private foot!: HTMLElement;
  private tabs!: HTMLElement;
  private opened = false;
  private order: WalkOrder = 'type';
  private filters = { needsReview: false, unconfirmed: false, discipline: '' };
  private scope: 'all' | 'one' = 'all';
  private tab: WalkState['tab'] = 'walk';
  private items: WalkItem[] = [];
  private itemIndex = 0;
  private elementIndex = 0;
  private editing: { disc: string; sub: string; div: string } | null = null;
  private comment = '';
  private commitNote = '';
  private message: { text: string; error: boolean } | null = null;
  private expanded = new Set<string>();
  private saved: { pose: Pose; selection: number[] } | null = null;
  private elementsCache: { model: unknown; list: WalkElement[] } | null = null;
  private off: (() => void) | null = null;
  private importFile: HTMLInputElement | null = null;

  constructor(private readonly app: ViewerApp, private readonly svc: ClassifyService, private readonly closeDrawer: () => void) {}

  get isOpen(): boolean {
    return this.opened;
  }

  // ------------------------------------------------------------ data

  private elements(): WalkElement[] {
    const m = this.svc.model;
    if (!m) return [];
    if (this.elementsCache?.model !== m) this.elementsCache = { model: m, list: walkElementsOf(m) };
    return this.elementsCache.list;
  }

  private walkInput(order = this.order, filters = this.filters): Parameters<typeof buildWalk>[0] {
    return {
      elements: this.elements(),
      resultOf: (g) => this.svc.store.get(g),
      isCommitted: (g) => this.svc.store.committed.has(g),
      disciplineOrder: this.svc.schema.disciplines.map((d) => d.code),
      order,
      filters: { ...(filters.needsReview ? { needsReview: true } : {}), ...(filters.unconfirmed ? { unconfirmed: true } : {}), ...(filters.discipline ? { discipline: filters.discipline } : {}) },
    };
  }

  /** Rebuild the list of items, keeping the position on the same item when it is still there. */
  private rebuild(keep = true): void {
    const key = keep ? this.items[this.itemIndex]?.key : undefined;
    this.items = buildWalk(this.walkInput());
    const at = key ? this.items.findIndex((i) => i.key === key) : -1;
    this.itemIndex = at >= 0 ? at : Math.min(this.itemIndex, Math.max(0, this.items.length - 1));
    if (at < 0) this.elementIndex = 0;
  }

  private item(): WalkItem | null {
    return this.items[this.itemIndex] ?? null;
  }
  private current(): WalkElement | null {
    const it = this.item();
    return it ? it.elements[Math.min(this.elementIndex, it.elements.length - 1)] ?? null : null;
  }
  private targets(): WalkElement[] {
    const it = this.item();
    if (!it) return [];
    return this.scope === 'all' ? it.elements : [this.current()!].filter(Boolean);
  }

  state(): WalkState {
    const it = this.item();
    return {
      open: this.opened,
      order: this.order,
      filters: { ...this.filters },
      scope: this.scope,
      tab: this.tab,
      itemIndex: this.itemIndex,
      items: this.items.length,
      elementIndex: this.elementIndex,
      item: it ? { key: it.key, title: it.title, elements: it.elements.length } : null,
      progress: this.progress(),
      pending: this.svc.review.pending().length,
      editing: this.editing !== null,
    };
  }

  /** The items of the walk, for scripts. */
  list(): Array<{ key: string; title: string; elements: number }> {
    return this.items.map((i) => ({ key: i.key, title: i.title, elements: i.elements.length }));
  }

  /** Go to an item by index (scripts and tests). */
  goto(i: number): void {
    if (this.opened) this.goItem(i);
  }

  private progress(): ReturnType<typeof walkProgress> {
    const scope = walkScope({ elements: this.elements(), resultOf: (g) => this.svc.store.get(g), filters: this.walkInput().filters });
    return walkProgress(scope, (g) => this.svc.review.decision(g));
  }

  // ------------------------------------------------------------ open, close

  open(o: { order?: WalkOrder } = {}): void {
    if (!this.svc.model) return;
    ensureStyle();
    ensureKeyStyles();
    this.closeDrawer(); // the drawer would cover the panel: close it (the walk has its own Classify button)
    if (!this.opened) {
      const sel = this.app.selection;
      this.saved = { pose: currentPose(this.app), selection: sel };
      this.opened = true;
      this.build();
      window.addEventListener('keydown', this.onKey, true);
      this.off = this.svc.onChange(() => this.onService());
    }
    if (o.order) this.order = o.order;
    this.message = null;
    this.tab = 'walk';
    this.editing = null;
    this.rebuild(false);
    this.elementIndex = 0;
    this.render();
    this.focus();
  }

  close(): void {
    if (!this.opened) return;
    this.opened = false;
    window.removeEventListener('keydown', this.onKey, true);
    this.off?.();
    this.off = null;
    this.root?.remove();
    this.root = null;
    const s = this.saved;
    this.saved = null;
    if (s) {
      const smooth = navSettings.smoothMoves;
      navSettings.smoothMoves = false; // put the camera back at once: an eased move can be cut short by a flight that is still running
      try {
        moveToPose(this.app, s.pose);
      } finally {
        navSettings.smoothMoves = smooth;
      }
      this.app.selectIds(s.selection);
    }
    const n = this.svc.review.pending().length;
    if (n > 0) showToast(`${n} pending change${n === 1 ? '' : 's'} kept: open the review walk again to commit them`, 3000);
  }

  /** The model was replaced: the walk of the old one is over (without moving the camera of the new one). */
  onModel(): void {
    if (!this.opened) return;
    this.saved = null;
    this.close();
  }

  private onService(): void {
    if (!this.opened) return;
    const a = document.activeElement;
    if (a && this.root?.contains(a) && (a.tagName === 'INPUT' || a.tagName === 'TEXTAREA')) {
      this.renderHead();
      return;
    }
    this.render();
  }

  // ------------------------------------------------------------ view of the model

  private focus(): void {
    const it = this.item();
    if (!it) return;
    const ids = this.targets().map((e) => e.id);
    if (ids.length === 0) return;
    this.app.selectIds(ids);
    const box = new Box3();
    for (const e of this.targets()) box.union(new Box3(new Vector3(e.bounds[0], e.bounds[1], e.bounds[2]), new Vector3(e.bounds[3], e.bounds[4], e.bounds[5])));
    moveToBox(this.app, box, { margin: ids.length > 1 ? 1.15 : 1.6, tag: 'review' });
  }

  // ------------------------------------------------------------ steps

  private goItem(i: number): void {
    if (this.items.length === 0) return;
    this.itemIndex = Math.max(0, Math.min(this.items.length, i)); // one past the last is "end of walk"
    this.elementIndex = 0;
    this.editing = null;
    this.comment = '';
    this.message = null;
    this.render();
    this.body.scrollTop = 0;
    this.focus();
  }
  private next(): void {
    const it = this.item();
    if (!it) return;
    if (this.scope === 'one' && this.elementIndex < it.elements.length - 1) {
      this.goElement(this.elementIndex + 1);
      return;
    }
    this.goItem(this.itemIndex + 1);
  }
  private back(): void {
    if (this.itemIndex >= this.items.length) {
      this.goItem(this.items.length - 1);
      return;
    }
    if (this.scope === 'one' && this.elementIndex > 0) {
      this.goElement(this.elementIndex - 1);
      return;
    }
    if (this.itemIndex > 0) this.goItem(this.itemIndex - 1);
  }
  private goElement(i: number): void {
    const it = this.item();
    if (!it) return;
    this.elementIndex = Math.max(0, Math.min(it.elements.length - 1, i));
    this.editing = null;
    this.render();
    this.focus();
  }

  // ------------------------------------------------------------ decisions

  private decide(action: 'confirm' | 'correct', codes?: { discipline?: string; subDiscipline?: string | null; masterformat?: string | null }): void {
    const it = this.item();
    if (!it) return;
    const gids = this.targets().map((e) => e.globalId);
    try {
      this.svc.review.propose(gids, { action, ...(codes ? { codes } : {}), item: it.key, ...(this.comment.trim() ? { comment: this.comment.trim() } : {}) });
      this.message = null;
    } catch (e) {
      this.message = { text: e instanceof Error ? e.message : String(e), error: true };
      this.render();
      return;
    }
    this.comment = '';
    this.editing = null;
    this.next();
  }

  private confirm(): void {
    this.decide('confirm');
  }

  private runner(): RunnerUp | null {
    const cur = this.current();
    const r = cur ? this.svc.store.get(cur.globalId) : undefined;
    if (!r) return null;
    const schema = this.svc.schema;
    return runnerUp(r, (part, code) => {
      if (part === 'discipline') return !!findDiscipline(schema, code);
      if (part === 'subDiscipline') {
        const d = findDiscipline(schema, r.discipline.code);
        return !!d && !!findSub(d, code);
      }
      return !!divisionTitle(schema, code);
    });
  }

  private useRunnerUp(): void {
    const up = this.runner();
    if (!up) return;
    this.decide('correct', up.part === 'discipline' ? { discipline: up.code } : up.part === 'subDiscipline' ? { subDiscipline: up.code } : { masterformat: up.code });
  }

  private startEdit(): void {
    const cur = this.current();
    const r = cur ? this.svc.store.get(cur.globalId) : undefined;
    if (!r) return;
    this.editing = { disc: r.discipline.code, sub: r.subDiscipline?.code ?? '', div: r.masterformat?.division ?? '' };
    this.render();
    this.root?.querySelector<HTMLElement>('.xrw-edit select')?.focus();
  }

  private applyEdit(): void {
    const e = this.editing;
    if (!e) return;
    this.decide('correct', { discipline: e.disc, subDiscipline: e.sub || null, masterformat: e.div || null });
  }

  private undoLast(): void {
    const p = this.svc.review.pending();
    const last = p[p.length - 1];
    if (!last) return;
    const n = this.svc.review.undoPending(last.item);
    const at = this.items.findIndex((i) => i.key === last.item);
    this.message = { text: `Undid ${n} pending change${n === 1 ? '' : 's'}.`, error: false };
    if (at >= 0) this.goItem(at);
    else this.render();
  }

  private commit(): void {
    const review = this.svc.review;
    const input = this.foot.querySelector<HTMLInputElement>('input[data-role=reviewer]');
    if (input && input.value.trim()) review.setReviewer(input.value);
    try {
      const c = review.commit(this.commitNote);
      this.commitNote = '';
      this.message = { text: `Committed ${c.changes.length} change${c.changes.length === 1 ? '' : 's'} as ${c.id}.`, error: false };
      this.rebuild();
    } catch (e) {
      this.message = { text: e instanceof Error ? e.message : String(e), error: true };
    }
    this.render();
  }

  // ------------------------------------------------------------ keys

  private readonly onKey = (e: KeyboardEvent): void => {
    if (!this.opened || e.defaultPrevented) return;
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    if (getKeymap()?.anyOverlayOpen()) return;
    const t = e.target as HTMLElement | null;
    const tag = t?.tagName ?? '';
    const typing = tag === 'INPUT' || tag === 'TEXTAREA' || !!t?.isContentEditable;
    const onButton = tag === 'BUTTON';
    const take = (): void => { e.preventDefault(); e.stopPropagation(); };
    if (e.key === 'Escape') {
      take();
      if (this.editing) { this.editing = null; this.render(); } else this.close();
      return;
    }
    if (typing || this.tab !== 'walk') return;
    if (onButton && (e.key === 'Enter' || e.key === ' ')) return; // a focused button keeps its own key
    const k = e.key.length === 1 ? e.key.toLowerCase() : e.key;
    if (this.editing) {
      if (k === 'Enter') { take(); this.applyEdit(); }
      return;
    }
    if (!this.item()) return;
    switch (k) {
      case 'Enter': case 'y': take(); this.confirm(); break;
      case '2': take(); this.useRunnerUp(); break;
      case 'e': take(); this.startEdit(); break;
      case 'n': case 'ArrowRight': take(); this.next(); break;
      case 'ArrowLeft': take(); this.back(); break;
      case ']': take(); { const it = this.item(); if (it) this.goElement(this.elementIndex + 1); } break;
      case '[': take(); this.goElement(this.elementIndex - 1); break;
      case 'a': take(); this.scope = this.scope === 'all' ? 'one' : 'all'; this.render(); this.focus(); break;
      case 'u': take(); this.undoLast(); break;
      default: break;
    }
  };

  // ------------------------------------------------------------ DOM

  private build(): void {
    const stage = this.app.canvas.parentElement ?? document.body;
    const root = el('section', 'xrw', { 'aria-label': 'Review walk', role: 'dialog', 'data-testid': 'review-walk' });
    this.head = el('div', 'xrw-head');
    this.tabs = el('div', 'xrw-tabs', { role: 'tablist' });
    this.body = el('div', 'xrw-body');
    this.foot = el('div', 'xrw-foot');
    root.append(this.head, this.tabs, this.body, this.foot);
    stage.appendChild(root);
    this.root = root;
  }

  private btn(label: string, act: string, onClick: () => void, o: { primary?: boolean; key?: string; title?: string; disabled?: boolean } = {}): HTMLButtonElement {
    const b = el('button', `xrw-btn${o.primary ? ' primary' : ''}`, { type: 'button', 'data-act': act }, label);
    if (o.key) b.appendChild(el('kbd', undefined, undefined, o.key));
    if (o.title) b.title = o.title;
    b.disabled = o.disabled === true;
    b.addEventListener('click', onClick);
    return b;
  }

  private select(label: string, value: string, options: Array<[string, string]>, onChange: (v: string) => void, role?: string): HTMLElement {
    const l = el('label');
    const s = el('select', undefined, role ? { 'data-role': role, 'aria-label': label } : { 'aria-label': label });
    for (const [v, t] of options) s.appendChild(el('option', undefined, { value: v }, t));
    s.value = value;
    s.addEventListener('change', () => onChange(s.value));
    l.append(el('span', undefined, undefined, label), s);
    return l;
  }

  private render(): void {
    if (!this.root) return;
    this.renderHead();
    this.renderTabs();
    this.body.replaceChildren();
    if (this.tab === 'walk') this.renderWalk();
    else if (this.tab === 'pending') this.renderPending();
    else this.renderHistory();
    this.renderFoot();
  }

  private renderHead(): void {
    const p = this.progress();
    this.head.replaceChildren(
      el('div', 'xrw-title', undefined, 'Review walk'),
      el('div', 'xrw-prog', { 'data-role': 'progress', 'aria-live': 'polite' }, `${p.confirmed} confirmed, ${p.corrected} corrected, ${p.remaining} remaining`),
    );
    const x = el('button', 'xrw-x', { type: 'button', 'aria-label': 'End the review walk', title: 'End the walk and restore the view (Esc)' }, '×');
    x.addEventListener('click', () => this.close());
    this.head.appendChild(x);
  }

  private renderTabs(): void {
    const n = this.svc.review.pending().length;
    const h = this.svc.review.history().length;
    const mk = (id: WalkState['tab'], label: string): HTMLButtonElement => {
      const b = el('button', `xrw-tab${this.tab === id ? ' on' : ''}`, { type: 'button', role: 'tab', 'data-tab': id, 'aria-selected': String(this.tab === id) }, label);
      b.addEventListener('click', () => { this.tab = id; this.editing = null; this.render(); });
      return b;
    };
    this.tabs.replaceChildren(mk('walk', 'Walk'), mk('pending', `Pending (${n})`), mk('history', `History (${h})`));
  }

  private msgLine(): HTMLElement | null {
    if (!this.message) return null;
    return el('div', this.message.error ? 'xrw-err' : 'xrw-ok', { role: 'status' }, this.message.text);
  }

  private renderWalk(): void {
    const b = this.body;
    // order and filters
    const bar = el('div', 'xrw-bar');
    bar.append(this.select('Order', this.order, WALK_ORDERS.map((o): [string, string] => [o, WALK_ORDER_LABEL[o]]), (v) => { this.order = v as WalkOrder; this.rebuild(false); this.render(); this.focus(); }, 'order'));
    const chk = (label: string, key: 'needsReview' | 'unconfirmed', title: string): HTMLElement => {
      const l = el('label');
      l.title = title;
      const i = el('input', undefined, { type: 'checkbox', 'data-role': key });
      i.checked = this.filters[key];
      i.addEventListener('change', () => { this.filters[key] = i.checked; this.rebuild(false); this.render(); this.focus(); });
      l.append(i, el('span', undefined, undefined, label));
      return l;
    };
    bar.append(chk('Only needs review', 'needsReview', 'Visit only elements whose result needs review'), chk('Only unconfirmed', 'unconfirmed', 'Leave out kinds that are committed already'));
    const discs = this.svc.schema.disciplines;
    bar.append(this.select('Discipline', this.filters.discipline, [['', 'All'], ...discs.map((d): [string, string] => [d.code, `${d.code} ${d.label}`])], (v) => { this.filters.discipline = v; this.rebuild(false); this.render(); this.focus(); }, 'discipline'));
    b.appendChild(bar);

    if (this.elements().filter((e) => this.svc.store.get(e.globalId)).length === 0) {
      b.append(el('div', 'xrw-warn', undefined, 'There are no results to review yet. The walk visits classified elements.'), this.btn('Classify all', 'classify', () => { void this.svc.classify('all').then(() => { this.rebuild(false); this.render(); this.focus(); }, (e: unknown) => { this.message = { text: e instanceof Error ? e.message : String(e), error: true }; this.render(); }); }, { primary: true }));
      return;
    }
    const it = this.item();
    if (this.items.length === 0) {
      b.append(el('div', 'xrw-warn', undefined, 'No element matches these filters.'));
      return;
    }
    if (!it) {
      const p = this.progress();
      b.append(
        el('div', 'xrw-item', undefined, 'End of the walk'),
        el('div', 'xrw-meta', undefined, `${p.confirmed} confirmed, ${p.corrected} corrected, ${p.remaining} remaining of ${p.total}. ${this.svc.review.pending().length} pending change(s) wait for a commit.`),
        row(this.btn('Back to the last item', 'back', () => this.back()), this.btn('Review pending changes', 'to-pending', () => { this.tab = 'pending'; this.render(); })),
      );
      const m = this.msgLine();
      if (m) b.appendChild(m);
      return;
    }
    const el0 = this.current()!;
    const r = this.svc.store.get(el0.globalId)!;
    b.appendChild(el('div', 'xrw-item', { 'data-role': 'item' }, `${this.itemIndex + 1} of ${this.items.length}: ${it.title}`));
    const where = [el0.storeyName && `Storey ${el0.storeyName}`, el0.system && `System ${el0.system}`].filter(Boolean).join(', ');
    b.appendChild(el('div', 'xrw-meta', { 'data-role': 'element' }, `${el0.ifcClass}, ${el0.name || '(no name)'}${el0.tag ? `, tag ${el0.tag}` : ''}${where ? `. ${where}` : ''}`));

    // scope and element stepping
    const scopeRow = el('div', 'xrw-bar');
    if (it.elements.length > 1) {
      const mkRadio = (v: 'all' | 'one', label: string): HTMLElement => {
        const l = el('label');
        const i = el('input', undefined, { type: 'radio', name: 'xrw-scope', value: v, 'data-role': `scope-${v}` });
        i.checked = this.scope === v;
        i.addEventListener('change', () => { this.scope = v; this.render(); this.focus(); });
        l.append(i, el('span', undefined, undefined, label));
        return l;
      };
      scopeRow.append(mkRadio('all', `All ${it.elements.length} of this type`), mkRadio('one', 'This element only'));
      scopeRow.append(this.btn('‹', 'prev-element', () => this.goElement(this.elementIndex - 1), { title: 'Previous element of this type ([)', disabled: this.elementIndex === 0 }), el('span', 'xrw-dim', { 'data-role': 'element-count' }, `${this.elementIndex + 1} / ${it.elements.length}`), this.btn('›', 'next-element', () => this.goElement(this.elementIndex + 1), { title: 'Next element of this type (])', disabled: this.elementIndex >= it.elements.length - 1 }));
    } else {
      scopeRow.append(el('span', 'xrw-dim', undefined, 'One element.'));
    }
    b.appendChild(scopeRow);

    // the proposal
    const tbl = el('table', 'xrw-tbl');
    tbl.appendChild(el('thead')).append(...[el('tr')].map((tr) => { for (const h of ['', 'Proposed', 'Confidence', 'Source']) tr.appendChild(el('th', undefined, undefined, h)); return tr; }));
    const srcText = (res: ClassifyResult): string =>
      res.source === 'model' ? `model ${res.model ?? ''}` : res.source === 'cache' ? `model ${res.model ?? ''} (cached)` : res.source === 'rules' ? 'rule' : res.source === 'manual' ? 'manual' : `${res.source} by ${res.confirmedBy ?? '?'}, ${when(res.confirmedAt ?? '')}`;
    const tb = el('tbody');
    const line = (name: string, code: string, label: string, conf: number | null): void => {
      const tr = el('tr');
      tr.append(el('td', 'xrw-dim', undefined, name), el('td', undefined, { 'data-role': name }, code ? `${code} ${label}` : '-'), el('td', undefined, undefined, conf === null ? '' : pct(conf)), el('td', undefined, undefined, code ? srcText(r) : ''));
      tb.appendChild(tr);
    };
    line('Discipline', r.discipline.code, r.discipline.label, r.discipline.confidence);
    line('Sub-discipline', r.subDiscipline?.code ?? '', r.subDiscipline?.label ?? '', r.subDiscipline?.confidence ?? null);
    line('Division', r.masterformat?.division ?? '', r.masterformat?.title ?? '', r.masterformat?.confidence ?? null);
    tbl.appendChild(tb);
    b.appendChild(tbl);
    if (r.rationale) b.appendChild(el('div', 'xrw-meta', { 'data-role': 'rationale' }, `Why: ${r.rationale}`));
    const up = this.runner();
    b.appendChild(el('div', up ? 'xrw-meta' : 'xrw-dim', { 'data-role': 'runner-up' }, up ? `Runner-up: ${up.code} instead of ${up.proposed} (${up.part === 'subDiscipline' ? 'sub-discipline' : up.part}, ${pct(up.probability)} against ${pct(up.proposedProbability)})` : 'No runner-up: only one option was scored.'));
    if (r.needsReview) b.appendChild(el('div', 'xrw-warn', undefined, `Needs review (overall confidence ${pct(overallConfidence(r))}).`));
    const dis = this.svc.review.disagreements().get(el0.globalId);
    if (dis) b.appendChild(el('div', 'xrw-warn', { 'data-role': 'disagree' }, `The model now disagrees: ${dis.discipline.code}${dis.subDiscipline ? `/${dis.subDiscipline.code}` : ''}${dis.masterformat ? `/${dis.masterformat.division}` : ''} (${dis.source === 'rules' ? 'rule' : dis.model ?? dis.source}), the committed value is ${r.discipline.code}${r.subDiscipline ? `/${r.subDiscipline.code}` : ''}${r.masterformat ? `/${r.masterformat.division}` : ''}.`));
    const pend = this.svc.review.pendingFor(el0.globalId);
    if (pend) b.appendChild(el('div', 'xrw-ok', { 'data-role': 'pending-state' }, `Pending: ${pend.action === 'confirm' ? 'confirmed' : `corrected to ${pend.after.discipline}${pend.after.subDiscipline ? `/${pend.after.subDiscipline}` : ''}${pend.after.division ? `/${pend.after.division}` : ''}`}. It is written when you commit.`));

    // comment and actions
    const c = el('input', undefined, { type: 'text', placeholder: 'Comment (optional)', 'aria-label': 'Comment', 'data-role': 'comment', maxlength: '300' });
    c.value = this.comment;
    c.addEventListener('input', () => { this.comment = c.value; });
    b.appendChild(c);
    if (this.editing) {
      const e = this.editing;
      const box = el('div', 'xrw-box xrw-edit');
      const fill = (): void => {
        const d = findDiscipline(this.svc.schema, e.disc);
        box.replaceChildren(
          el('div', 'xrw-meta', undefined, `Correct ${this.scope === 'all' && it.elements.length > 1 ? `all ${it.elements.length}` : 'this element'}`),
          this.select('Discipline', e.disc, this.svc.schema.disciplines.map((x): [string, string] => [x.code, `${x.code} ${x.label}`]), (v) => { e.disc = v; e.sub = ''; fill(); }, 'edit-discipline'),
          this.select('Sub-discipline', e.sub, [['', '(none)'], ...(d?.subDisciplines ?? []).map((s): [string, string] => [s.code, `${s.code} ${s.label}`])], (v) => { e.sub = v; }, 'edit-sub'),
          this.select('Division', e.div, [['', '(none)'], ...this.svc.schema.masterformat.divisions.map((x): [string, string] => [x.division, `${x.division} ${x.title}`])], (v) => { e.div = v; }, 'edit-division'),
          row(this.btn('Apply correction', 'apply-correct', () => this.applyEdit(), { primary: true, key: 'Enter' }), this.btn('Cancel', 'cancel-correct', () => { this.editing = null; this.render(); }, { key: 'Esc' })),
        );
      };
      fill();
      b.appendChild(box);
    } else {
      const acts = el('div', 'xrw-acts');
      acts.append(
        this.btn('Confirm', 'confirm', () => this.confirm(), { primary: true, key: 'Enter' }),
        this.btn(up ? `Use ${up.code}` : 'Runner-up', 'runner-up', () => this.useRunnerUp(), { key: '2', disabled: !up, title: up ? `Take the runner-up ${up.code} for the ${up.part}` : 'There is no second option' }),
        this.btn('Correct…', 'correct', () => this.startEdit(), { key: 'E', title: 'Pick the codes by hand' }),
        this.btn('Skip', 'skip', () => this.next(), { key: 'N', title: 'Leave it and go to the next (right arrow)' }),
        this.btn('Back', 'back', () => this.back(), { key: '←', disabled: this.itemIndex === 0 && this.elementIndex === 0 }),
        this.btn('Undo last', 'undo', () => this.undoLast(), { key: 'U', disabled: this.svc.review.pending().length === 0, title: 'Take back the last pending item' }),
      );
      b.appendChild(acts);
      b.appendChild(el('div', 'xrw-dim', undefined, 'Keys: Enter or Y confirm, 2 runner-up, E correct, N or right arrow skip, left arrow back, A all/one, U undo.'));
    }
    const m = this.msgLine();
    if (m) b.appendChild(m);
  }

  private describe(a: { discipline: string; subDiscipline: string | null; division: string | null }): string {
    return `${a.discipline}${a.subDiscipline ? `/${a.subDiscipline}` : ''}${a.division ? `/${a.division}` : ''}`;
  }

  private renderPending(): void {
    const b = this.body;
    const pend = this.svc.review.pending();
    if (pend.length === 0) {
      b.append(el('div', 'xrw-dim', undefined, 'No pending changes. Confirmations and corrections wait here until you commit them.'));
      const m0 = this.msgLine();
      if (m0) b.appendChild(m0);
      return;
    }
    const byItem = new Map<string, typeof pend>();
    for (const p of pend) (byItem.get(p.item) ?? byItem.set(p.item, []).get(p.item)!).push(p);
    const elementOf = new Map(this.elements().map((e) => [e.globalId, e]));
    for (const [key, list] of byItem) {
      const first = list[0]!;
      const e = elementOf.get(first.globalId);
      const title = this.items.find((i) => i.key === key)?.title ?? `${e?.ifcClass ?? ''}: ${e?.name ?? first.globalId}`;
      const r = el('div', 'xrw-commit', { 'data-item': key });
      r.append(
        el('div', 'xrw-row'),
      );
      const top = r.firstChild as HTMLElement;
      top.append(el('div', 'grow', undefined, `${title}: ${list.length} element${list.length === 1 ? '' : 's'}, ${this.describe(first.before)} to ${this.describe(first.after)} (${first.action === 'confirm' ? 'confirm' : 'correct'})`), this.btn('Undo', 'undo-item', () => { this.svc.review.undoPending(key); this.message = null; this.render(); }, { title: 'Take this item back out of the pending changes' }));
      if (first.comment) r.append(el('div', 'xrw-dim', undefined, `Comment: ${first.comment}`));
      b.appendChild(r);
    }
    b.appendChild(row(this.btn('Discard all pending changes', 'discard', () => { this.svc.review.discardPending(); this.render(); })));
    const m = this.msgLine();
    if (m) b.appendChild(m);
  }

  private renderHistory(): void {
    const b = this.body;
    const hist = this.svc.review.history();
    const st = this.svc.review.storage;
    b.appendChild(el('div', st.where === 'session' ? 'xrw-warn' : 'xrw-dim', { 'data-role': 'storage' }, st.where === 'session' ? `Not saved on this device (${st.error}). The log is kept for this session; export it to keep it.` : st.where === 'localstorage' ? 'Saved in this browser (localStorage).' : st.where === 'indexeddb' ? 'Saved in this browser (IndexedDB).' : 'Saved in this browser when you commit.'));
    if (hist.length === 0) b.appendChild(el('div', 'xrw-dim', undefined, 'No commits yet for this model.'));
    for (const c of hist) b.appendChild(this.commitRow(c));
    this.ensureImport();
    b.appendChild(row(
      this.btn('Export review log', 'export-log', () => this.exportLog(), { title: 'Save the commits of this model as an xray-classification-review/1 file' }),
      this.btn('Import review log', 'import-log', () => this.importFile?.click(), { title: 'Replay the commits of a review log file. Commits that are in the log already are skipped.' }),
    ));
    const m = this.msgLine();
    if (m) b.appendChild(m);
  }

  private commitRow(c: ReviewCommit): HTMLElement {
    const r = el('div', `xrw-commit${c.reverts ? ' rev' : ''}`, { 'data-commit': c.id });
    const open = this.expanded.has(c.id);
    const top = el('div', 'xrw-row');
    top.append(
      el('div', 'grow', undefined, `${when(c.time)}, ${c.author}${c.note ? `: ${c.note}` : ''} (${c.changes.length} change${c.changes.length === 1 ? '' : 's'}${c.reverts ? `, reverts ${c.reverts}` : ''})`),
      this.btn(open ? 'Close' : 'Open', 'open-commit', () => { if (open) this.expanded.delete(c.id); else this.expanded.add(c.id); this.render(); }),
      this.btn('Revert', 'revert', () => this.revert(c), { disabled: !!c.reverts || this.svc.review.history().some((x) => x.reverts === c.id), title: 'Add a commit that puts the earlier results back. This commit stays in the log.' }),
    );
    r.appendChild(top);
    if (open) {
      const list = el('div', 'xrw-changes');
      for (const ch of c.changes.slice(0, 200)) list.appendChild(el('div', undefined, undefined, `${ch.globalId}: ${this.describe(ch.before)} (${ch.before.source}) to ${this.describe(ch.after)} (${ch.action})${ch.comment ? `, "${ch.comment}"` : ''}`));
      if (c.changes.length > 200) list.appendChild(el('div', undefined, undefined, `... and ${c.changes.length - 200} more`));
      r.appendChild(list);
    }
    return r;
  }

  private revert(c: ReviewCommit): void {
    const input = this.foot.querySelector<HTMLInputElement>('input[data-role=reviewer]');
    if (input && input.value.trim()) this.svc.review.setReviewer(input.value);
    try {
      const r = this.svc.review.revert(c.id);
      this.message = { text: `Reverted ${c.id} with ${r.commit.id}${r.skipped.length ? `; ${r.skipped.length} element(s) were changed again later and were left alone` : ''}.`, error: false };
      this.rebuild();
    } catch (e) {
      this.message = { text: e instanceof Error ? e.message : String(e), error: true };
    }
    this.render();
  }

  private exportLog(): void {
    try {
      downloadText(`classification-review-${this.app.modelName}.json`, this.svc.review.exportLog(), 'application/json');
    } catch (e) {
      this.message = { text: e instanceof Error ? e.message : String(e), error: true };
      this.render();
    }
  }

  private ensureImport(): void {
    if (this.importFile) return;
    const f = el('input', undefined, { type: 'file', accept: '.json,application/json', hidden: '', 'data-role': 'import-file' });
    f.addEventListener('change', async () => {
      const file = f.files?.[0];
      f.value = '';
      if (!file) return;
      const r = this.svc.review.importLog(await file.text());
      this.message = r.ok ? { text: `Imported ${r.added.length} commit${r.added.length === 1 ? '' : 's'}; ${r.duplicates.length} already in the log.`, error: false } : { text: r.error ?? 'The log could not be imported.', error: true };
      if (r.ok) this.rebuild();
      this.render();
    });
    this.importFile = f;
    (this.root ?? document.body).appendChild(f);
  }

  private renderFoot(): void {
    const review = this.svc.review;
    const n = review.pending().length;
    const f = this.foot;
    f.replaceChildren();
    const name = el('input', undefined, { type: 'text', 'data-role': 'reviewer', placeholder: 'Your name or initials', 'aria-label': 'Reviewer name or initials', autocomplete: 'off', maxlength: '80' });
    name.value = review.reviewer();
    if (review.reviewer()) {
      const who = el('span', 'xrw-dim', { 'data-role': 'reviewer-label' }, `Reviewer: ${review.reviewer()}`);
      const change = el('button', 'xrw-btn', { type: 'button', 'data-act': 'change-reviewer', title: 'Change the name kept on this device' }, 'Change');
      change.addEventListener('click', () => { review.setReviewer(''); this.render(); });
      f.append(who, change);
    } else {
      f.append(name);
    }
    const note = el('input', undefined, { type: 'text', 'data-role': 'note', placeholder: 'Note for the commit (optional)', 'aria-label': 'Commit note', maxlength: '300' });
    note.value = this.commitNote;
    note.addEventListener('input', () => { this.commitNote = note.value; });
    f.append(note, this.btn(`Commit ${n} change${n === 1 ? '' : 's'}`, 'commit', () => this.commit(), { primary: true, disabled: n === 0, title: n === 0 ? 'Nothing is pending' : 'Write the pending changes as one commit of the review log' }));
    const cls = el('button', 'xrw-btn', { type: 'button', 'data-act': 'classify-drawer', title: 'Open the Classify drawer' }, 'Classify');
    cls.addEventListener('click', () => { this.close(); window.__xrayToolbar?.open('classify'); });
    f.append(cls);
  }
}

function row(...c: HTMLElement[]): HTMLElement {
  const r = el('div', 'xrw-row');
  r.append(...c);
  return r;
}
