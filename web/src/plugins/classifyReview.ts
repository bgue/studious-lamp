// The review walk: a panel over the viewer that visits the classified elements in a logical order, shows the proposal with its confidence
// and source, and records a confirmation, a runner-up pick or a correction as a pending change. "Commit" turns the pending changes into
// one commit of the review log (classify/reviewLog.ts). The panel works with the keyboard (Enter or Y, 1 to 9, E, N or the right arrow, the
// left arrow, F, Z) and with buttons, so it also works on a phone. Facet results that need review are walk items too (classify/facetWalk.ts). The reviewer's name is kept in this browser and nowhere else.
// Docs: docs-features/classify.md, section "Review walk".

import { Box3, Vector3 } from 'three';
import type { ViewerApp } from '../app';
import { getKeymap } from '../input/keymap';
import { currentPose, moveToBox, moveToPose, navSettings } from '../input/navigation';
import type { Pose } from '../input/navigation';
import { overallConfidence } from '../classify/review';
import { CONCRETE_FACET_IDS } from '../classify/concrete/defs';
import { FACET_IDS } from '../classify/facets/defs';
import { buildFacetItems, facetCandidates, WALK_KINDS, WALK_KIND_LABEL } from '../classify/facetWalk';
import type { FacetEntry, FacetLike, WalkKind } from '../classify/facetWalk';
import { nextReviewZoom, REVIEW_ZOOMS, REVIEW_ZOOM_LABEL, resolveZoom, roomOf, storeyBox } from '../classify/reviewZoom';
import type { ReviewZoom, SpaceBox } from '../classify/reviewZoom';
import { escAction, filterCodes, walkKeyAction, ESC_CLOSE_MS } from '../classify/walkKeys';
import type { EscFocus } from '../classify/walkKeys';
import type { ReviewVia } from '../classify/reviewLog';
import { buildManifestPanel } from './classifyManifest';
import { divisionTitle, findDiscipline, findSub } from '../classify/schema';
import { buildWalk, classCandidates, runnerUp, walkElementsOf, walkProgress, walkScope, WALK_ORDER_LABEL, WALK_ORDERS } from '../classify/reviewWalk';
import type { FacetRef, RunnerUp, WalkElement, WalkItem, WalkOrder } from '../classify/reviewWalk';
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
.xrw:focus{outline:none}
.xrw-box[data-role=manifest-panel] label{flex-direction:row;align-items:center;gap:6px}
.xrw-box input[data-role=code-filter]{width:100%;box-sizing:border-box}
.xrw-hint{background:#3a2d12;color:#ffd98a;border:1px solid #8a6a1f;border-radius:4px;padding:4px 8px;margin:4px 0;font-size:12px}
.xrw-cands{display:flex;flex-direction:column;gap:3px;margin:4px 0}
.xrw-cand{display:flex;gap:8px;align-items:center;text-align:left;background:#121a26;color:inherit;border:1px solid #2a3647;border-radius:4px;padding:3px 7px;cursor:pointer;font:inherit}
.xrw-cand.cur{border-color:#2d6aa8}
.xrw-cand:hover{background:#1a2535}
.xrw-cand kbd{min-width:1.2em;text-align:center}
.xrw-acts{display:grid;grid-template-columns:repeat(auto-fit,minmax(104px,1fr));gap:6px}
.xrw-btn{background:#1b2230;color:inherit;border:1px solid #2d3748;border-radius:4px;padding:5px 8px;cursor:pointer;font:inherit;text-align:center;line-height:1.2}
.xrw-btn:hover:not(:disabled){background:#243049;border-color:#3a4a66}
.xrw-btn:disabled{opacity:.45;cursor:default}
.xrw-btn.primary{background:#1f4a7a;border-color:#2d6aa8;color:#fff}
.xrw-btn kbd{font:inherit;font-size:10px;color:var(--sb-dim,#8d99a8);margin-left:4px;border:1px solid #2d3748;border-radius:3px;padding:0 3px}
.xrw-dock{flex:0 0 auto;display:flex;flex-direction:column;gap:6px;padding:6px 8px;border-top:1px solid var(--sb-line,#262d3a);background:#10141b}
.xrw-dock:empty{display:none}
.xrw-dock label.xrw-unsure{display:flex;align-items:center;gap:6px;color:#e0b252;cursor:pointer}
.xrw-dock label.xrw-unsure kbd{font:inherit;font-size:10px;color:var(--sb-dim,#8d99a8);border:1px solid #2d3748;border-radius:3px;padding:0 3px}
.xrw-tag{display:inline-block;font-size:10px;line-height:1.3;padding:0 5px;border:1px solid #8a6d2b;border-radius:8px;color:#e0b252;margin-left:4px;white-space:nowrap}
.xrw-skipped{flex:0 0 auto;background:transparent;border:1px solid #2d3748;border-radius:10px;color:var(--sb-dim,#8d99a8);cursor:pointer;font:inherit;font-size:11px;padding:1px 8px}
.xrw-skipped:hover:not(:disabled){color:#fff;border-color:#3a4a66}
.xrw-skipped[aria-pressed=true]{background:#1f4a7a;border-color:#2d6aa8;color:#fff}
.xrw-skipped:disabled{opacity:.45;cursor:default}
.xrw-foot{display:flex;flex-wrap:wrap;gap:6px;align-items:center;padding:6px 8px;border-top:1px solid var(--sb-line,#262d3a)}
.xrw-foot input[type=text]{flex:1 1 120px;width:auto}
.xrw-row{display:flex;gap:6px;align-items:center;flex-wrap:wrap}
.xrw-row .grow{flex:1 1 auto;min-width:0}
.xrw-commit{border:1px solid #1a202b;border-radius:4px;padding:5px 6px;display:flex;flex-direction:column;gap:4px}
.xrw-commit.rev{border-style:dashed}
/* In the Classification tab of the right sidebar: part of the column, not a panel over the view. */
.xrw.xrw-in{position:static;left:auto;bottom:auto;width:auto;max-height:none;flex:1 1 auto;min-height:0;z-index:auto;border:0;border-radius:0;box-shadow:none;background:transparent}
.xrw.xrw-in .xrw-head,.xrw.xrw-in .xrw-tabs{padding-left:0;padding-right:0}
.xrw-changes{font-size:11px;color:var(--sb-dim,#8d99a8);display:flex;flex-direction:column;gap:2px;max-height:160px;overflow:auto}
@media (max-width:760px){
  .xrw{left:var(--sb-rail,28px);right:var(--dk-rail,28px);width:auto;bottom:${STATUS_H}px;max-height:70%;border-radius:10px 10px 0 0;font-size:13px}
  .xrw-btn{padding:9px 4px;font-size:13px}
  .xrw-acts{grid-template-columns:repeat(3,1fr);gap:5px}
  .xrw-dock{padding:5px 8px}
  .xrw-dock label.xrw-unsure{min-height:30px}
  .xrw-dock label.xrw-unsure input{width:20px;height:20px}
  .xrw-foot{padding:5px 8px}
  .xrw-btn kbd,.xrw-keys{display:none}
  .xrw select,.xrw input[type=text]{height:32px;font-size:14px}
  .xrw-x{font-size:24px;padding:0 8px}
}
`;

/** Installs the review walk's styles (`.xrw…`); the revision walk shares them. */
export function ensureReviewWalkStyle(): void {
  if (document.getElementById(STYLE_ID)) return;
  const st = document.createElement('style');
  st.id = STYLE_ID;
  st.textContent = CSS;
  document.head.appendChild(st);
}

const pct = (x: number): string => `${Math.round(x * 100)}%`;
const when = (iso: string): string => (iso.length >= 16 ? `${iso.slice(0, 10)} ${iso.slice(11, 16)}` : iso);

/**
 * Where the walk lives. The Classification tab of the right sidebar gives a container (`mount`), shows itself on `opened` and takes its
 * panel back on `closed`; with no container the walk floats over the stage as before.
 */
export interface WalkHost {
  /** The container for the walk, or null to float over the stage. */
  mount(): HTMLElement | null;
  /** The walk is about to open (show the tab, hide what it replaces). */
  opened(): void;
  /** The walk closed. */
  closed(): void;
}

export interface WalkState {
  open: boolean;
  order: WalkOrder;
  /** Which items the walk visits: classification, facets or both. */
  kind: WalkKind;
  /** How far the walk frames the element in view. */
  zoom: ReviewZoom;
  /** The first Esc armed the second (the "Esc again to close" hint is up). */
  escArmed: boolean;
  filters: { needsReview: boolean; unconfirmed: boolean; discipline: string; unsure: boolean; onlySkipped: boolean };
  scope: 'all' | 'one';
  tab: 'walk' | 'pending' | 'history';
  itemIndex: number;
  items: number;
  elementIndex: number;
  item: { key: string; title: string; elements: number; facet?: string } | null;
  progress: { confirmed: number; corrected: number; remaining: number; total: number };
  pending: number;
  editing: boolean;
  /** The "Unsure (a guess)" switch for the next Confirm, Runner-up or Correct. */
  unsure: boolean;
  /** Elements skipped in this session. */
  skipped: number;
}

export class ReviewWalk {
  private root: HTMLElement | null = null;
  private body!: HTMLElement;
  private head!: HTMLElement;
  private foot!: HTMLElement;
  private tabs!: HTMLElement;
  private dock!: HTMLElement;
  private opened = false;
  private order: WalkOrder = 'type';
  private kind: WalkKind = 'classification';
  private escAt: number | null = null;
  private hintEl: HTMLElement | null = null;
  private hintTimer: ReturnType<typeof setTimeout> | null = null;
  private spacesCache: { model: unknown; list: SpaceBox[] } | null = null;
  private manifestOpen = false;
  private filters = { needsReview: false, unconfirmed: false, discipline: '', unsure: false, onlySkipped: false };
  private unsure = false;
  private scope: 'all' | 'one' = 'all';
  private tab: WalkState['tab'] = 'walk';
  private items: WalkItem[] = [];
  private itemIndex = 0;
  private elementIndex = 0;
  private editing: { disc: string; sub: string; div: string; filter: string; code: string } | null = null;
  private comment = '';
  private commitNote = '';
  private message: { text: string; error: boolean } | null = null;
  private expanded = new Set<string>();
  private saved: { pose: Pose; selection: number[] } | null = null;
  private elementsCache: { model: unknown; list: WalkElement[] } | null = null;
  private off: (() => void) | null = null;
  private importFile: HTMLInputElement | null = null;

  constructor(private readonly app: ViewerApp, private readonly svc: ClassifyService, private readonly host: WalkHost) {}

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
      isCommitted: (g) => { const c = this.svc.store.committed.get(g); return !!c && c.unsure !== true; }, // an unsure commit is not settled
      skipped: this.svc.review.skips,
      disciplineOrder: this.svc.schema.disciplines.map((d) => d.code),
      order,
      filters: { ...(filters.needsReview ? { needsReview: true } : {}), ...(filters.unconfirmed ? { unconfirmed: true } : {}), ...(filters.discipline ? { discipline: filters.discipline } : {}), ...(filters.unsure ? { unsure: true } : {}), ...(filters.onlySkipped ? { onlySkipped: true } : {}) },
    };
  }

  /** Rebuild the list of items, keeping the position on the same item when it is still there. */
  private rebuild(keep = true): void {
    const key = keep ? this.items[this.itemIndex]?.key : undefined;
    this.items = this.buildItems();
    const at = key ? this.items.findIndex((i) => i.key === key) : -1;
    this.itemIndex = at >= 0 ? at : Math.min(this.itemIndex, Math.max(0, this.items.length - 1));
    if (at < 0) this.elementIndex = 0;
  }

  /** The classification items and the facet items that the Kind filter asks for. */
  private buildItems(): WalkItem[] {
    const cls = this.kind === 'facets' ? [] : buildWalk(this.walkInput());
    const fac = this.kind === 'classification' ? [] : buildFacetItems({ elements: this.elements(), entriesOf: (g) => this.facetEntries(g), skipped: this.svc.review.skips, filters: { ...(this.filters.unconfirmed ? { unconfirmed: true } : {}), ...(this.filters.unsure ? { unsure: true } : {}), ...(this.filters.onlySkipped ? { onlySkipped: true } : {}) } });
    return [...cls, ...fac];
  }

  /** The facet and concrete results of an element, as walk entries. */
  private facetEntries(globalId: string): FacetEntry[] {
    const out: FacetEntry[] = [];
    const fs = this.svc.facetsOf(globalId);
    for (const id of FACET_IDS) { const r = fs[id]; if (r) out.push({ ref: { id, family: 'facet' }, result: r }); }
    const cs = this.svc.concreteOf(globalId);
    for (const id of CONCRETE_FACET_IDS) { const r = cs[id]; if (r) out.push({ ref: { id, family: 'concrete' }, result: r }); }
    return out;
  }

  /** The facet of the item in view: its reference and result (a facet item), or null. */
  private curFacet(): { ref: FacetRef; result: FacetLike } | null {
    const it = this.item();
    const cur = this.current();
    if (!it?.facet || !cur) return null;
    const result = this.facetEntries(cur.globalId).find((e) => e.ref.id === it.facet!.id)?.result;
    return result ? { ref: it.facet, result } : null;
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
    return this.scope === 'all' && !it.facet ? it.elements : [this.current()!].filter(Boolean);
  }

  state(): WalkState {
    const it = this.item();
    return {
      open: this.opened,
      order: this.order,
      kind: this.kind,
      zoom: this.svc.reviewZoom(),
      escArmed: this.escAt !== null,
      filters: { ...this.filters },
      scope: this.scope,
      tab: this.tab,
      itemIndex: this.itemIndex,
      items: this.items.length,
      elementIndex: this.elementIndex,
      item: it ? { key: it.key, title: it.title, elements: it.elements.length, ...(it.facet ? { facet: it.facet.id } : {}) } : null,
      progress: this.progress(),
      pending: this.svc.review.pendingCount(),
      editing: this.editing !== null,
      unsure: this.unsure,
      skipped: this.svc.review.skips.size,
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
    const p = { confirmed: 0, corrected: 0, remaining: 0, total: 0 };
    if (this.kind !== 'facets') {
      const scope = walkScope({ elements: this.elements(), resultOf: (g) => this.svc.store.get(g), filters: this.walkInput().filters, skipped: this.svc.review.skips });
      Object.assign(p, walkProgress(scope, (g) => this.svc.review.decision(g)));
    }
    if (this.kind !== 'classification') {
      for (const it of this.items) {
        if (!it.facet) continue;
        const d = this.svc.review.facetDecision(it.elements[0]!.globalId, it.facet.id);
        p.total++;
        if (d === 'confirmed') p.confirmed++;
        else if (d === 'corrected') p.corrected++;
        else p.remaining++;
      }
    }
    return p;
  }

  // ------------------------------------------------------------ open, close

  open(o: { order?: WalkOrder; kind?: WalkKind } = {}): void {
    if (!this.svc.model) return;
    ensureReviewWalkStyle();
    ensureKeyStyles();
    this.host.opened(); // the Classification tab shows the walk in place of its panel (the walk has its own Classify button)
    if (!this.opened) {
      const sel = this.app.selection;
      this.saved = { pose: currentPose(this.app), selection: sel };
      this.opened = true;
      this.build();
      window.addEventListener('keydown', this.onKey, true);
      this.off = this.svc.onChange(() => this.onService());
    }
    if (o.order) this.order = o.order;
    if (o.kind) this.kind = o.kind;
    this.message = null;
    this.tab = 'walk';
    this.editing = null;
    this.unsure = false;
    this.rebuild(false);
    this.elementIndex = 0;
    this.render();
    this.focus();
  }

  close(): void {
    if (!this.opened) return;
    this.opened = false;
    window.removeEventListener('keydown', this.onKey, true);
    this.clearHint();
    this.off?.();
    this.off = null;
    this.root?.remove();
    this.root = null;
    this.host.closed();
    const s = this.saved;
    this.saved = null;
    if (s) {
      // the selection first: selecting starts the cinematic fly-to-selection, which the camera move below then cancels
      this.app.selectIds(s.selection);
      const smooth = navSettings.smoothMoves;
      navSettings.smoothMoves = false; // put the camera back at once: an eased move can be cut short by a flight that is still running
      try {
        moveToPose(this.app, s.pose);
      } finally {
        navSettings.smoothMoves = smooth;
      }
    }
    const n = this.svc.review.pendingCount();
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

  /** The IfcSpace elements of the model (for the Room zoom). */
  private spaces(): SpaceBox[] {
    const m = this.svc.model;
    if (!m) return [];
    if (this.spacesCache?.model !== m) this.spacesCache = { model: m, list: m.elements.filter((e) => e.ifcClass === 'IfcSpace').map((e) => ({ bounds: e.bounds, storey: e.storey })) };
    return this.spacesCache.list;
  }

  /** Frame the item in view (not the whole model) at the review zoom: Close, With surroundings, Room or Storey. The element stays selected. */
  private focus(): void {
    const it = this.item();
    if (!it) return;
    const targets = this.targets();
    const ids = targets.map((e) => e.id);
    if (ids.length === 0) return;
    this.app.selectIds(ids);
    const first = targets[0]!;
    const view = resolveZoom(this.svc.reviewZoom(), targets.map((e) => e.bounds), { room: roomOf(first.bounds, first.storey, this.spaces()), storey: storeyBox(first.storey, this.elements()) });
    if (!view) return;
    const b = view.box;
    moveToBox(this.app, new Box3(new Vector3(b[0], b[1], b[2]), new Vector3(b[3], b[4], b[5])), { margin: view.margin, minDistance: view.minDistance, tag: 'review' });
  }

  /** Z: the next zoom (Close, With surroundings, Room, Storey), saved with the settings. */
  private cycleZoom(): void {
    this.svc.setReviewZoom(nextReviewZoom(this.svc.reviewZoom()));
    this.render();
    this.focus();
  }

  // ------------------------------------------------------------ steps

  private goItem(i: number): void {
    if (this.items.length === 0) return;
    this.itemIndex = Math.max(0, Math.min(this.items.length, i)); // one past the last is "end of walk"
    this.elementIndex = 0;
    this.editing = null;
    this.comment = '';
    this.unsure = false; // the flag belongs to the element in view
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
    this.comment = '';
    this.unsure = false;
    this.render();
    this.focus();
  }

  // ------------------------------------------------------------ skip

  /**
   * Leave this element as it is and go on. In a type group the walk steps to the next element of the group (or on to the next item after
   * the last one). An open correction is dropped unsaved. A skip is not a change: it is not pending, not committed and not in the log.
   */
  private skipElement(): void {
    const it = this.item();
    const cur = this.current();
    if (!it || !cur) return;
    this.noteSkip([cur.globalId]);
    if (it.elements.length > 1 && this.elementIndex < it.elements.length - 1) this.goElement(this.elementIndex + 1);
    else this.goItem(this.itemIndex + 1);
  }

  /** Leave every element of this type as it is and go to the next item. */
  private skipGroup(): void {
    const it = this.item();
    if (!it) return;
    this.noteSkip(it.elements.map((e) => e.globalId));
    this.goItem(this.itemIndex + 1);
  }

  private noteSkip(ids: string[]): void {
    this.svc.review.activity.skipped += this.svc.review.skips.add(ids);
  }

  private groupSkipFirst(): boolean {
    const it = this.item();
    return !!it && it.elements.length > 1 && this.scope === 'all';
  }

  /** The Skip key (N, right arrow): the whole type when the scope is All, this element when it is "This element only". */
  private skipByScope(): void {
    if (this.groupSkipFirst()) this.skipGroup();
    else this.skipElement();
  }

  /** Shift+N: the other of the two. */
  private skipOther(): void {
    if (this.groupSkipFirst()) this.skipElement();
    else this.skipGroup();
  }

  private toggleUnsure(): void {
    this.unsure = !this.unsure;
    this.renderDock();
  }

  /** Show only the elements that were skipped (or all again). */
  private toggleOnlySkipped(): void {
    this.filters.onlySkipped = !this.filters.onlySkipped;
    this.tab = 'walk';
    this.itemIndex = 0;
    this.rebuild(false);
    this.elementIndex = 0;
    this.render();
    this.focus();
  }

  // ------------------------------------------------------------ decisions

  private decide(action: 'confirm' | 'correct', codes?: { discipline?: string; subDiscipline?: string | null; masterformat?: string | null }, o: { via?: ReviewVia; facetCode?: string } = {}): void {
    const it = this.item();
    if (!it) return;
    try {
      const f = it.facet;
      const opts = { action, item: it.key, ...(this.comment.trim() ? { comment: this.comment.trim() } : {}), ...(this.unsure ? { unsure: true } : {}), ...(o.via ? { via: o.via } : {}) };
      if (f) {
        const cur = this.current();
        if (!cur) return;
        this.svc.review.proposeFacet(f, cur.globalId, { ...opts, ...(o.facetCode ? { code: o.facetCode } : {}) });
      } else {
        const gids = this.targets().map((e) => e.globalId);
        this.svc.review.propose(gids, { ...opts, ...(codes ? { codes } : {}) });
      }
      this.message = null;
    } catch (e) {
      this.message = { text: e instanceof Error ? e.message : String(e), error: true };
      this.render();
      return;
    }
    this.comment = '';
    this.editing = null;
    this.unsure = false; // one action only
    this.next();
  }

  private confirm(): void {
    this.decide('confirm');
  }

  private classValid(r: ClassifyResult): (part: RunnerUp['part'], code: string) => boolean {
    const schema = this.svc.schema;
    return (part, code) => {
      if (part === 'discipline') return !!findDiscipline(schema, code);
      if (part === 'subDiscipline') {
        const d = findDiscipline(schema, r.discipline.code);
        return !!d && !!findSub(d, code);
      }
      return !!divisionTitle(schema, code);
    };
  }

  private runner(): RunnerUp | null {
    const cur = this.current();
    const r = cur ? this.svc.store.get(cur.globalId) : undefined;
    if (!r || this.item()?.facet) return null;
    return runnerUp(r, this.classValid(r));
  }

  /**
   * The numbered candidates of the item in view. Key 1 is the proposal (Confirm), key 2 the runner-up, keys 3 to 9 the next options of the
   * same part (a classification) or of the facet. Empty when only one option was scored.
   */
  private candidates(): Array<{ code: string; label: string; probability: number | null; part?: RunnerUp['part'] }> {
    const f = this.curFacet();
    if (f) return facetCandidates(f.result, this.svc.facetCodesOf(f.ref)).map((c) => ({ ...c }));
    const cur = this.current();
    const r = cur ? this.svc.store.get(cur.globalId) : undefined;
    if (!r) return [];
    const cc = classCandidates(r, this.classValid(r));
    if (!cc) return [];
    const schema = this.svc.schema;
    const label = (code: string): string => (cc.part === 'discipline' ? findDiscipline(schema, code)?.label : cc.part === 'subDiscipline' ? findSub(findDiscipline(schema, r.discipline.code)!, code)?.label : divisionTitle(schema, code)) ?? '';
    return cc.list.map((c) => ({ code: c.code, label: label(c.code), probability: c.probability, part: cc.part }));
  }

  /** Keys 1 to 9: take candidate `rank` (1 confirms; 2 is the runner-up; the rest are corrections). */
  private takeCandidate(rank: number): void {
    if (rank === 1) { this.confirm(); return; }
    const c = this.candidates()[rank - 1];
    if (!c) return;
    const via: ReviewVia = rank === 2 ? 'runner-up' : 'candidate';
    if (this.item()?.facet) this.decide('correct', undefined, { via, facetCode: c.code });
    else this.decide('correct', c.part === 'discipline' ? { discipline: c.code } : c.part === 'subDiscipline' ? { subDiscipline: c.code } : { masterformat: c.code }, { via });
  }

  private useRunnerUp(): void {
    this.takeCandidate(2);
  }

  private startEdit(): void {
    const cur = this.current();
    if (!cur) return;
    const f = this.curFacet();
    if (f) {
      if (!this.svc.facetCodesOf(f.ref)) { this.message = { text: `${f.ref.id} has no code list to pick from: confirm it or skip it.`, error: true }; this.render(); return; }
      this.editing = { disc: '', sub: '', div: '', filter: '', code: f.result.code };
    } else {
      const r = this.svc.store.get(cur.globalId);
      if (!r) return;
      this.editing = { disc: r.discipline.code, sub: r.subDiscipline?.code ?? '', div: r.masterformat?.division ?? '', filter: '', code: '' };
    }
    this.message = null;
    this.render();
    this.root?.querySelector<HTMLElement>('[data-role=code-filter]')?.focus();
  }

  private applyEdit(): void {
    const e = this.editing;
    if (!e) return;
    if (this.item()?.facet) this.decide('correct', undefined, { facetCode: e.code });
    else this.decide('correct', { discipline: e.disc, subDiscipline: e.sub || null, masterformat: e.div || null });
  }

  private undoLast(): void {
    const last = this.svc.review.lastPendingItem();
    if (!last) return;
    const n = this.svc.review.undoPending(last);
    const at = this.items.findIndex((i) => i.key === last);
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

  private clearHint(): void {
    this.escAt = null;
    if (this.hintTimer) clearTimeout(this.hintTimer);
    this.hintTimer = null;
    this.hintEl?.remove();
    this.hintEl = null;
  }

  /** The first Esc: say that a second one closes the walk, for a moment. */
  private armEsc(): void {
    this.clearHint();
    this.escAt = Date.now();
    this.hintEl = el('div', 'xrw-hint', { role: 'status', 'data-role': 'esc-hint' }, 'Esc again to close (or press Q)');
    this.head.after(this.hintEl);
    this.hintTimer = setTimeout(() => this.clearHint(), ESC_CLOSE_MS);
  }

  /** Where the keyboard is, for Esc: on the walk (or the page), in a text field or list of the walk, or on a control elsewhere. */
  private focusKind(t: HTMLElement | null): EscFocus {
    if (!t || t === document.body || t.tagName === 'CANVAS') return 'walk';
    const inside = !!this.root?.contains(t);
    const tag = t.tagName;
    const field = tag === 'SELECT' || tag === 'TEXTAREA' || (tag === 'INPUT' && !['checkbox', 'radio'].includes((t as HTMLInputElement).type)) || t.isContentEditable;
    if (inside) return field ? 'field' : 'walk';
    return field || tag === 'BUTTON' || tag === 'A' ? 'elsewhere' : 'walk';
  }

  private readonly onKey = (e: KeyboardEvent): void => {
    if (!this.opened || e.defaultPrevented) return;
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    if (getKeymap()?.anyOverlayOpen()) return;
    const t = e.target as HTMLElement | null;
    const tag = t?.tagName ?? '';
    const inputType = tag === 'INPUT' ? (t as HTMLInputElement).type : '';
    const typing = (tag === 'INPUT' && inputType !== 'checkbox' && inputType !== 'radio') || tag === 'TEXTAREA' || !!t?.isContentEditable; // a ticked box or a radio keeps the walk keys
    const onButton = tag === 'BUTTON';
    const take = (): void => { e.preventDefault(); e.stopPropagation(); };
    if (e.key === 'Escape') {
      take();
      // Esc leaves a correction, or brings the focus back to the walk; the walk closes with Q or a second Esc
      const act = escAction({ editing: this.editing !== null, focus: this.focusKind(t), armedAt: this.escAt, now: Date.now() });
      if (act === 'leave-edit') { this.clearHint(); this.editing = null; this.render(); this.root?.focus(); }
      else if (act === 'focus-walk') { this.clearHint(); this.root?.focus(); }
      else if (act === 'arm') this.armEsc();
      else this.close();
      return;
    }
    if (this.escAt !== null) this.clearHint(); // another key: the second Esc is not "again" any more
    if (typing || this.tab !== 'walk') return;
    if (onButton && (e.key === 'Enter' || e.key === ' ')) return; // a focused button keeps its own key
    const k = e.key.length === 1 ? e.key.toLowerCase() : e.key;
    if (this.editing) {
      if (k === 'Enter') { take(); this.applyEdit(); }
      else if (k === '?') { take(); this.toggleUnsure(); }
      else if ((k === 'n' || k === 'ArrowRight') && tag !== 'SELECT') { take(); e.shiftKey && k === 'n' ? this.skipOther() : this.skipByScope(); } // a picker keeps its letters and arrows
      return;
    }
    if (!this.item()) {
      if (k === 'q') { take(); this.close(); }
      return;
    }
    const a = walkKeyAction({ key: e.key, shift: e.shiftKey });
    if (!a) return;
    take();
    switch (a.action) {
      case 'confirm': this.confirm(); break;
      case 'candidate': this.takeCandidate(a.rank ?? 2); break;
      case 'correct': this.startEdit(); break;
      case 'skip': this.skipByScope(); break;
      case 'skip-other': this.skipOther(); break;
      case 'unsure': this.toggleUnsure(); break;
      case 'back': this.back(); break;
      case 'step-next': this.goElement(this.elementIndex + 1); break;
      case 'step-prev': this.goElement(this.elementIndex - 1); break;
      case 'scope': this.scope = this.scope === 'all' ? 'one' : 'all'; this.render(); this.focus(); break;
      case 'undo': this.undoLast(); break;
      case 'frame': this.focus(); break;
      case 'zoom': this.cycleZoom(); break;
      case 'close': this.close(); break;
    }
  };

  // ------------------------------------------------------------ DOM

  private build(): void {
    const inTab = this.host.mount();
    const stage = inTab ?? this.app.canvas.parentElement ?? document.body;
    const root = el('section', inTab ? 'xrw xrw-in' : 'xrw', { 'aria-label': 'Review walk', role: 'dialog', tabindex: '-1', 'data-testid': 'review-walk' });
    this.head = el('div', 'xrw-head');
    this.tabs = el('div', 'xrw-tabs', { role: 'tablist' });
    this.body = el('div', 'xrw-body');
    this.dock = el('div', 'xrw-dock', { 'data-role': 'dock' });
    this.foot = el('div', 'xrw-foot');
    root.append(this.head, this.tabs, this.body, this.dock, this.foot);
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
    this.dock.replaceChildren();
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
    const n = this.svc.review.skips.size;
    const sk = el('button', 'xrw-skipped', { type: 'button', 'data-role': 'skipped-count', 'aria-pressed': String(this.filters.onlySkipped), title: this.filters.onlySkipped ? 'Showing only the skipped elements: click to show all again' : n ? 'Revisit the elements that you skipped in this session (only skipped)' : 'Nothing was skipped yet' }, `Skipped (${n})`);
    sk.disabled = n === 0 && !this.filters.onlySkipped;
    sk.addEventListener('click', () => this.toggleOnlySkipped());
    this.head.appendChild(sk);
    const x = el('button', 'xrw-x', { type: 'button', 'aria-label': 'End the review walk', title: 'End the walk and restore the view (Q, or Esc twice)' }, '×');
    x.addEventListener('click', () => this.close());
    this.head.appendChild(x);
  }

  private renderTabs(): void {
    const n = this.svc.review.pendingCount();
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
    bar.append(this.select('Show', this.kind, WALK_KINDS.map((k): [string, string] => [k, WALK_KIND_LABEL[k]]), (v) => { this.kind = v as WalkKind; this.itemIndex = 0; this.rebuild(false); this.elementIndex = 0; this.render(); this.focus(); }, 'kind'));
    bar.append(this.select('Review zoom', this.svc.reviewZoom(), REVIEW_ZOOMS.map((z): [string, string] => [z, REVIEW_ZOOM_LABEL[z]]), (v) => { this.svc.setReviewZoom(v as ReviewZoom); this.render(); this.focus(); }, 'zoom'));
    bar.append(this.select('Order', this.order, WALK_ORDERS.map((o): [string, string] => [o, WALK_ORDER_LABEL[o]]), (v) => { this.order = v as WalkOrder; this.rebuild(false); this.render(); this.focus(); }, 'order'));
    const chk = (label: string, key: 'needsReview' | 'unconfirmed' | 'unsure' | 'onlySkipped', title: string, role: string = key): HTMLElement => {
      const l = el('label');
      l.title = title;
      const i = el('input', undefined, { type: 'checkbox', 'data-role': role });
      i.checked = this.filters[key];
      i.addEventListener('change', () => { this.filters[key] = i.checked; this.rebuild(false); this.render(); this.focus(); });
      l.append(i, el('span', undefined, undefined, label));
      return l;
    };
    bar.append(chk('Only needs review', 'needsReview', 'Visit only elements whose result needs review'), chk('Only unconfirmed', 'unconfirmed', 'Leave out kinds that are committed already (a commit flagged unsure does not count: it is still a guess)'), chk('Only unsure', 'unsure', 'Visit only the elements that you committed as unsure (a guess)', 'filter-unsure'), chk('Only skipped', 'onlySkipped', 'Revisit only the elements that you skipped in this session', 'filter-skipped'));
    const discs = this.svc.schema.disciplines;
    bar.append(this.select('Discipline', this.filters.discipline, [['', 'All'], ...discs.map((d): [string, string] => [d.code, `${d.code} ${d.label}`])], (v) => { this.filters.discipline = v; this.rebuild(false); this.render(); this.focus(); }, 'discipline'));
    b.appendChild(bar);

    if (this.kind !== 'facets' && this.elements().filter((e) => this.svc.store.get(e.globalId)).length === 0 && !(this.kind === 'both' && this.items.length > 0)) {
      b.append(el('div', 'xrw-warn', undefined, 'There are no results to review yet. The walk visits classified elements.'), this.btn('Classify all', 'classify', () => { void this.svc.classify('all').then(() => { this.rebuild(false); this.render(); this.focus(); }, (e: unknown) => { this.message = { text: e instanceof Error ? e.message : String(e), error: true }; this.render(); }); }, { primary: true }));
      return;
    }
    const it = this.item();
    if (this.items.length === 0) {
      b.append(el('div', 'xrw-warn', undefined, this.kind === 'facets' ? 'No facet result needs review. Run the facets from the Classification tab, or choose Classification.' : 'No element matches these filters.'));
      return;
    }
    if (!it) {
      const p = this.progress();
      b.append(
        el('div', 'xrw-item', undefined, 'End of the walk'),
        el('div', 'xrw-meta', undefined, `${p.confirmed} confirmed, ${p.corrected} corrected, ${p.remaining} remaining of ${p.total}. ${this.svc.review.pendingCount()} pending change(s) wait for a commit.`),
        row(this.btn('Back to the last item', 'back', () => this.back()), this.btn('Review pending changes', 'to-pending', () => { this.tab = 'pending'; this.render(); }), ...(this.svc.review.skips.size > 0 && !this.filters.onlySkipped ? [this.btn(`Revisit skipped (${this.svc.review.skips.size})`, 'revisit-skipped', () => this.toggleOnlySkipped())] : [])),
      );
      const m = this.msgLine();
      if (m) b.appendChild(m);
      return;
    }
    const el0 = this.current()!;
    const r = it.facet ? undefined : this.svc.store.get(el0.globalId);
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

    if (it.facet) this.renderFacetCard(b, el0);
    else if (r) this.renderClassCard(b, el0, r);

    // comment and actions
    const c = el('input', undefined, { type: 'text', placeholder: 'Comment (optional)', 'aria-label': 'Comment', 'data-role': 'comment', maxlength: '300' });
    c.value = this.comment;
    c.addEventListener('input', () => { this.comment = c.value; });
    b.appendChild(c);
    if (this.editing) {
      const e = this.editing;
      const facet = this.curFacet();
      const box = el('div', 'xrw-box xrw-edit');
      const filter = el('input', undefined, { type: 'text', placeholder: 'Type to filter the codes', 'aria-label': 'Filter the code list', 'data-role': 'code-filter', autocomplete: 'off', maxlength: '60' });
      filter.value = e.filter;
      const lists = el('div');
      const opts = <T extends { code: string; label: string }>(all: readonly T[], keep: string, head: Array<[string, string]> = []): Array<[string, string]> => {
        // a list with no match is shown whole: the filter only narrows what it can
        const use = e.filter.trim() && filterCodes(all, e.filter).length === 0 ? [...all] : filterCodes(all, e.filter, keep);
        return [...head, ...use.map((x): [string, string] => [x.code, `${x.code} ${x.label}`])];
      };
      const fill = (): void => {
        const kids: HTMLElement[] = [];
        if (facet) {
          const codes = this.svc.facetCodesOf(facet.ref) ?? [];
          kids.push(this.select('Code', e.code, opts(codes, e.code), (v) => { e.code = v; }, 'edit-code'));
        } else {
          const d = findDiscipline(this.svc.schema, e.disc);
          kids.push(
            this.select('Discipline', e.disc, opts(this.svc.schema.disciplines, e.disc), (v) => { e.disc = v; e.sub = ''; fill(); }, 'edit-discipline'),
            this.select('Sub-discipline', e.sub, opts(d?.subDisciplines ?? [], e.sub, [['', '(none)']]), (v) => { e.sub = v; }, 'edit-sub'),
            this.select('Division', e.div, opts(this.svc.schema.masterformat.divisions.map((x) => ({ code: x.division, label: x.title })), e.div, [['', '(none)']]), (v) => { e.div = v; }, 'edit-division'),
          );
        }
        lists.replaceChildren(...kids);
      };
      filter.addEventListener('input', () => {
        e.filter = filter.value;
        // typing picks the first match of the main list (the discipline, or the facet's code); the other lists only narrow
        if (e.filter.trim()) {
          if (facet) { const m = filterCodes(this.svc.facetCodesOf(facet.ref) ?? [], e.filter)[0]; if (m) e.code = m.code; }
          else { const m = filterCodes(this.svc.schema.disciplines, e.filter)[0]; if (m && m.code !== e.disc) { e.disc = m.code; e.sub = ''; } }
        }
        fill();
      });
      filter.addEventListener('keydown', (ev) => {
        if (ev.key === 'Enter') { ev.preventDefault(); ev.stopPropagation(); this.applyEdit(); }
        else if (ev.key === 'ArrowDown') { ev.preventDefault(); lists.querySelector<HTMLElement>('select')?.focus(); }
      });
      box.append(el('div', 'xrw-meta', undefined, `Correct ${facet ? `${facet.ref.id} of this element` : this.scope === 'all' && it.elements.length > 1 ? `all ${it.elements.length}` : 'this element'}`), filter, lists);
      fill();
      b.appendChild(box);
    }
    const m = this.msgLine();
    if (m) b.appendChild(m);
    this.renderDock();
  }

  /** The proposal of a classification item: codes, confidence and source, the runner-up and the candidates, and the states. */
  private renderClassCard(b: HTMLElement, el0: WalkElement, r: ClassifyResult): void {
    // the proposal
    const tbl = el('table', 'xrw-tbl');
    tbl.appendChild(el('thead')).append(...[el('tr')].map((tr) => { for (const h of ['', 'Proposed', 'Confidence', 'Source']) tr.appendChild(el('th', undefined, undefined, h)); return tr; }));
    const srcText = (res: ClassifyResult): string =>
      res.source === 'model' ? `model ${res.model ?? ''}` : res.source === 'cache' ? `model ${res.model ?? ''} (cached)` : res.source === 'rules' ? 'rule' : res.source === 'manual' ? 'manual' : `${res.source}${res.unsure ? ' (unsure)' : ''} by ${res.confirmedBy ?? '?'}, ${when(res.confirmedAt ?? '')}`;
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
    this.renderCandidates(b);
    if (r.needsReview) b.appendChild(el('div', 'xrw-warn', undefined, `Needs review (overall confidence ${pct(overallConfidence(r))}).`));
    if (r.unsure) b.appendChild(el('div', 'xrw-warn', { 'data-role': 'unsure-state' }, `Committed as unsure (a guess, confidence ${pct(r.discipline.confidence)}). It still needs review.`));
    if (this.svc.review.skips.has(el0.globalId)) b.appendChild(el('div', 'xrw-dim', { 'data-role': 'skipped-state' }, 'You skipped this element earlier in this session.'));
    const dis = this.svc.review.disagreements().get(el0.globalId);
    if (dis) b.appendChild(el('div', 'xrw-warn', { 'data-role': 'disagree' }, `The model now disagrees: ${dis.discipline.code}${dis.subDiscipline ? `/${dis.subDiscipline.code}` : ''}${dis.masterformat ? `/${dis.masterformat.division}` : ''} (${dis.source === 'rules' ? 'rule' : dis.model ?? dis.source}), the committed value is ${r.discipline.code}${r.subDiscipline ? `/${r.subDiscipline.code}` : ''}${r.masterformat ? `/${r.masterformat.division}` : ''}.`));
    const pend = this.svc.review.pendingFor(el0.globalId);
    if (pend) b.appendChild(el('div', 'xrw-ok', { 'data-role': 'pending-state' }, `Pending: ${pend.action === 'confirm' ? 'confirmed' : `corrected to ${pend.after.discipline}${pend.after.subDiscipline ? `/${pend.after.subDiscipline}` : ''}${pend.after.division ? `/${pend.after.division}` : ''}`}${pend.unsure ? ' (unsure)' : ''}. It is written when you commit.`));
  }

  /** The numbered candidates: key 1 the proposal, key 2 the runner-up, keys 3 to 9 the next options. Clicking one is the same as the key. */
  private renderCandidates(b: HTMLElement): void {
    const list = this.candidates();
    if (list.length < 2) return;
    const box = el('div', 'xrw-cands', { 'data-role': 'candidates', role: 'list', 'aria-label': 'Candidates' });
    list.slice(0, 9).forEach((c, i) => {
      const rank = i + 1;
      const row = el('button', `xrw-cand${rank === 1 ? ' cur' : ''}`, { type: 'button', 'data-rank': String(rank), 'data-code': c.code, title: rank === 1 ? 'The proposal: the same as Confirm' : rank === 2 ? 'The runner-up' : `Candidate ${rank}` });
      row.append(el('kbd', undefined, undefined, String(rank)), el('span', undefined, undefined, `${c.code}${c.label ? ` ${c.label}` : ''}${c.probability === null ? '' : ` ${pct(c.probability)}`}${rank === 1 ? ' (proposed)' : ''}`));
      row.addEventListener('click', () => this.takeCandidate(rank));
      box.appendChild(row);
    });
    b.appendChild(box);
  }

  /** The proposal of a facet item: the facet's code, confidence and source, its fields, and the states. */
  private renderFacetCard(b: HTMLElement, el0: WalkElement): void {
    const f = this.curFacet();
    if (!f) { b.appendChild(el('div', 'xrw-warn', undefined, 'This facet has no result any more (it was switched off or the facets ran again).')); return; }
    const r = f.result;
    const tbl = el('table', 'xrw-tbl');
    tbl.appendChild(el('thead')).appendChild(el('tr')).append(...['', 'Proposed', 'Confidence', 'Source'].map((h) => el('th', undefined, undefined, h)));
    const tb = el('tbody');
    const src = r.source === 'human' ? `human${r.confidence < 1 ? ' (unsure)' : ''}` : r.source === 'model' ? `model ${r.model ?? ''}` : r.source;
    tb.appendChild(el('tr')).append(el('td', 'xrw-dim', undefined, f.ref.id.replace('Concrete', 'Concrete ')), el('td', undefined, { 'data-role': 'facet-value' }, `${r.code} ${r.label}`), el('td', undefined, undefined, pct(r.confidence)), el('td', undefined, undefined, src));
    tbl.appendChild(tb);
    b.appendChild(tbl);
    if (r.rationale) b.appendChild(el('div', 'xrw-meta', { 'data-role': 'rationale' }, `Why: ${r.rationale}`));
    this.renderCandidates(b);
    if (!this.svc.facetCodesOf(f.ref)) b.appendChild(el('div', 'xrw-dim', { 'data-role': 'no-codes' }, 'This set has no code list: confirm it or skip it.'));
    if (r.needsReview) b.appendChild(el('div', 'xrw-warn', undefined, `Needs review (confidence ${pct(r.confidence)}).`));
    if (this.svc.review.skips.has(el0.globalId)) b.appendChild(el('div', 'xrw-dim', { 'data-role': 'skipped-state' }, 'You skipped this element earlier in this session.'));
    const pend = this.svc.review.pendingFacetFor(el0.globalId, f.ref.id);
    if (pend) b.appendChild(el('div', 'xrw-ok', { 'data-role': 'pending-state' }, `Pending: ${pend.action === 'confirm' ? 'confirmed' : `corrected to ${pend.after.code}`}${pend.unsure ? ' (unsure)' : ''}. It is written when you commit.`));
  }

  /** The decision controls, outside the scrolling part so that they are on screen on a phone: the Unsure switch and the buttons. */
  private renderDock(): void {
    this.dock.replaceChildren();
    const it = this.tab === 'walk' ? this.item() : null;
    if (!it || !this.current()) return;
    const unsureBox = el('label', 'xrw-unsure');
    unsureBox.title = 'Optional. Tick it when this is a guess: the next Confirm, Runner-up or Correct is recorded as unsure (confidence 75%, still needs review, left out of Calibrate on confirmed). It clears after each action.';
    const chk = el('input', undefined, { type: 'checkbox', 'data-role': 'unsure', 'aria-label': 'Unsure (a guess)' });
    chk.checked = this.unsure;
    chk.addEventListener('change', () => { this.unsure = chk.checked; });
    unsureBox.append(chk, el('span', undefined, undefined, 'Unsure (a guess)'), el('kbd', undefined, undefined, '?'));
    const n = it.elements.length;
    if (this.editing) {
      const acts = el('div', 'xrw-acts');
      acts.append(
        this.btn('Apply correction', 'apply-correct', () => this.applyEdit(), { primary: true, key: 'Enter' }),
        this.btn('Skip', 'skip-edit', () => this.skipByScope(), { key: 'N', title: 'Drop this correction unsaved and go to the next. A skip is not a change.' }),
        this.btn('Cancel', 'cancel-correct', () => { this.editing = null; this.render(); }, { key: 'Esc' }),
      );
      this.dock.append(unsureBox, acts);
      return;
    }
    const cands = this.candidates();
    const up = cands[1] ?? null;
    const acts = el('div', 'xrw-acts');
    acts.append(
      this.btn('Confirm', 'confirm', () => this.confirm(), { primary: true, key: 'Enter' }),
      this.btn(up ? `Use ${up.code}` : 'Runner-up', 'runner-up', () => this.useRunnerUp(), { key: '2', disabled: !up, title: up ? `Take the runner-up ${up.code}${up.part ? ` for the ${up.part === 'subDiscipline' ? 'sub-discipline' : up.part}` : ''}` : 'There is no second option' }),
      this.btn('Correct…', 'correct', () => this.startEdit(), { key: 'E', title: 'Pick the codes by hand (type to filter the list)' }),
    );
    if (n > 1) {
      const first = this.groupSkipFirst();
      acts.append(
        this.btn('Skip this one', 'skip-element', () => this.skipElement(), { key: first ? '⇧N' : 'N', title: 'Leave this element as it is and go to the next element of the type. Not a change.' }),
        this.btn(`Skip all ${n}`, 'skip-group', () => this.skipGroup(), { key: first ? 'N' : '⇧N', title: `Leave all ${n} elements of this type as they are and go to the next item. Not a change.` }),
      );
    } else {
      acts.append(this.btn('Skip', 'skip', () => this.skipElement(), { key: 'N', title: 'Leave it as it is and go to the next (right arrow). Not a change.' }));
    }
    acts.append(
      this.btn('Back', 'back', () => this.back(), { key: '←', disabled: this.itemIndex === 0 && this.elementIndex === 0 }),
      this.btn('Undo last', 'undo', () => this.undoLast(), { key: 'U', disabled: this.svc.review.pendingCount() === 0, title: 'Take back the last pending item' }),
      this.btn('Frame', 'frame', () => this.focus(), { key: 'F', title: 'Frame this item again at the review zoom' }),
    );
    this.dock.append(unsureBox, acts, el('div', 'xrw-dim xrw-keys', { 'data-role': 'keys' }, `Zoom: ${REVIEW_ZOOM_LABEL[this.svc.reviewZoom()]} (Z). Keys: Enter or Y confirm, 1 to 9 take a candidate (2 runner-up), E correct, N or right arrow skip (Shift+N the other skip), ? unsure, left arrow back, [ ] step, A all/one, U undo, F frame, Z zoom, Esc leave Correct, Q or Esc twice close.`));
  }

  private describe(a: { discipline: string; subDiscipline: string | null; division: string | null }): string {
    return `${a.discipline}${a.subDiscipline ? `/${a.subDiscipline}` : ''}${a.division ? `/${a.division}` : ''}`;
  }

  private renderPending(): void {
    const b = this.body;
    const pend = this.svc.review.pending();
    const pendF = this.svc.review.pendingFacets();
    if (pend.length === 0 && pendF.length === 0) {
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
      const nUnsure = list.filter((x) => x.unsure).length;
      const label = el('div', 'grow', undefined, `${title}: ${list.length} element${list.length === 1 ? '' : 's'}, ${this.describe(first.before)} to ${this.describe(first.after)} (${first.action === 'confirm' ? 'confirm' : 'correct'})`);
      if (nUnsure > 0) label.appendChild(el('span', 'xrw-tag', { 'data-role': 'unsure-tag', title: 'Flagged as a guess' }, nUnsure === list.length ? 'unsure' : `unsure ${nUnsure} of ${list.length}`));
      top.append(label, this.btn('Undo', 'undo-item', () => { this.svc.review.undoPending(key); this.message = null; this.render(); }, { title: 'Take this item back out of the pending changes' }));
      if (first.comment) r.append(el('div', 'xrw-dim', undefined, `Comment: ${first.comment}`));
      b.appendChild(r);
    }
    for (const p of pendF) {
      const e = this.elements().find((x) => x.globalId === p.globalId);
      const title = this.items.find((i) => i.key === p.item)?.title ?? `${p.facet}: ${e?.ifcClass ?? ''} ${e?.name ?? p.globalId}`;
      const r = el('div', 'xrw-commit', { 'data-item': p.item });
      const top = el('div', 'xrw-row');
      const label = el('div', 'grow', undefined, `${title}: ${p.before.code} to ${p.after.code} (${p.action === 'confirm' ? 'confirm' : 'correct'})`);
      if (p.unsure) label.appendChild(el('span', 'xrw-tag', { 'data-role': 'unsure-tag', title: 'Flagged as a guess' }, 'unsure'));
      top.append(label, this.btn('Undo', 'undo-item', () => { this.svc.review.undoPending(p.item); this.message = null; this.render(); }, { title: 'Take this item back out of the pending changes' }));
      r.appendChild(top);
      if (p.comment) r.append(el('div', 'xrw-dim', undefined, `Comment: ${p.comment}`));
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
      this.btn('Export manifest…', 'export-manifest', () => { this.manifestOpen = !this.manifestOpen; this.render(); }, { title: 'Save a summary of the classification and the review as an xray-classification-manifest/1 file, or as Markdown' }),
      this.btn('Import review log', 'import-log', () => this.importFile?.click(), { title: 'Replay the commits of a review log file. Commits that are in the log already are skipped.' }),
    ));
    if (this.manifestOpen) {
      b.appendChild(buildManifestPanel(this.svc, {
        cls: { box: 'xrw-box', btn: 'xrw-btn', primary: 'xrw-btn primary', row: 'xrw-row' },
        modelName: this.app.modelName,
        done: (r) => { this.manifestOpen = false; this.message = r?.error ? { text: r.error, error: true } : r?.message ? { text: r.message, error: false } : null; this.render(); },
      }));
    }
    const m = this.msgLine();
    if (m) b.appendChild(m);
  }

  private commitRow(c: ReviewCommit): HTMLElement {
    const r = el('div', `xrw-commit${c.reverts ? ' rev' : ''}`, { 'data-commit': c.id });
    const open = this.expanded.has(c.id);
    const top = el('div', 'xrw-row');
    top.append(
      el('div', 'grow', undefined, `${when(c.time)}, ${c.author}${c.note ? `: ${c.note}` : ''} (${c.changes.length + (c.facetChanges?.length ?? 0)} change${c.changes.length + (c.facetChanges?.length ?? 0) === 1 ? '' : 's'}${c.changes.some((x) => x.unsure) || c.facetChanges?.some((x) => x.unsure) ? `, ${c.changes.filter((x) => x.unsure).length + (c.facetChanges?.filter((x) => x.unsure).length ?? 0)} unsure` : ''}${c.reverts ? `, reverts ${c.reverts}` : ''})`),
      this.btn(open ? 'Close' : 'Open', 'open-commit', () => { if (open) this.expanded.delete(c.id); else this.expanded.add(c.id); this.render(); }),
      this.btn('Revert', 'revert', () => this.revert(c), { disabled: !!c.reverts || this.svc.review.history().some((x) => x.reverts === c.id), title: 'Add a commit that puts the earlier results back. This commit stays in the log.' }),
    );
    r.appendChild(top);
    if (open) {
      const list = el('div', 'xrw-changes');
      for (const ch of c.changes.slice(0, 200)) {
        const line = el('div', undefined, undefined, `${ch.globalId}: ${this.describe(ch.before)} (${ch.before.source}) to ${this.describe(ch.after)} (${ch.action})${ch.comment ? `, "${ch.comment}"` : ''}`);
        if (ch.unsure) line.appendChild(el('span', 'xrw-tag', { 'data-role': 'unsure-tag', title: 'Flagged as a guess' }, 'unsure'));
        list.appendChild(line);
      }
      if (c.changes.length > 200) list.appendChild(el('div', undefined, undefined, `... and ${c.changes.length - 200} more`));
      for (const ch of (c.facetChanges ?? []).slice(0, 200)) {
        const line = el('div', undefined, undefined, `${ch.globalId}: ${ch.facet} ${ch.before.code} (${ch.before.source}) to ${ch.after.code} (${ch.action})${ch.comment ? `, "${ch.comment}"` : ''}`);
        if (ch.unsure) line.appendChild(el('span', 'xrw-tag', { 'data-role': 'unsure-tag', title: 'Flagged as a guess' }, 'unsure'));
        list.appendChild(line);
      }
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
    const n = review.pendingCount();
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
