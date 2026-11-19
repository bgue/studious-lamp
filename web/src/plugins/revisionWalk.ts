// The revision walk panel (design 3.6): a card per change with what changed, the base decision beside the new proposal, the ghost of the
// earlier shape in the view, and decision buttons that also work on a phone. Same visual language and `.xrw…` classes as the review walk
// (plugins/classifyReview.ts); the panel is mounted through the PanelHost, never into the page directly.
// Keys: Enter or Y accept, 2 the other classification, E edit, R reject, N or right arrow skip (Shift+N the rest of the item), ? unsure,
// left arrow back, [ ] step inside an item, A all or one, U undo, G ghost, B bulk, Esc close. Docs: docs-features/revision.md.

import { Box3, Vector3 } from 'three';
import type { ViewerApp } from '../app';
import { getKeymap } from '../input/keymap';
import { currentPose, moveToBox, moveToPose, navSettings } from '../input/navigation';
import type { Pose } from '../input/navigation';
import { overallConfidence } from '../classify/review';
import { findDiscipline } from '../classify/schema';
import type { ClassifyResult } from '../classify/types';
import { baseToViewer, GHOST_MODE_LABEL, nextGhostMode } from '../revision/ghost';
import type { GhostMode } from '../revision/ghost';
import { changeRows, CATEGORY_LABEL, FLAG_LABEL } from '../revision/card';
import type { RevisionController, UndoEntry } from '../revision/controller';
import { downloadText } from '../tools/csv';
import { ensureKeyStyles, showToast } from '../ui/keymapView';
import { el } from '../ui/dom';
import type { PanelHost } from '../ui/panelHost';
import { STATUS_H } from '../ui/statusBar';
import { ensureReviewWalkStyle } from './classifyReview';
import { REVISION_ORDER_LABEL, REVISION_ORDERS } from '../revision/walkOrder';
import type { RevisionItem } from '../revision/walkOrder';
import { CATEGORIES, CHANGE_FLAGS } from '../revision/types';
import type { BulkRule, DiffEntry, RevisionDecision, RevisionFilters, RevisionOrder } from '../revision/types';

const STYLE_ID = 'xray-revision-walk-style';
const PANEL_ID = 'revision-walk';
const CSS = `
.xrw.xrr{z-index:17}
.xrr .xrr-badge{display:inline-block;font-size:10px;line-height:1.4;padding:0 6px;border-radius:8px;border:1px solid #2d3748;margin-right:5px;text-transform:uppercase;letter-spacing:.04em}
.xrr .xrr-badge.new{color:#9fe3b0;border-color:#2f7a4d}
.xrr .xrr-badge.deleted{color:#ff8f8f;border-color:#8a3b3b}
.xrr .xrr-badge.changed{color:#e0b252;border-color:#8a6d2b}
.xrr .xrr-badge.rematched{color:#8fc3ff;border-color:#2d6aa8}
.xrr .xrr-chip{display:inline-block;font:inherit;font-size:11px;padding:1px 8px;margin:0 4px 4px 0;border:1px solid #2d3748;border-radius:10px;background:#141a24;color:inherit;cursor:default}
.xrr .xrr-chip[role=button]{cursor:pointer}
.xrr .xrr-state{border-left:3px solid #2d6aa8;padding:3px 8px;background:#0e141d}
.xrr .xrr-state.rejected{border-color:#8a3b3b}
.xrr .xrr-state.accepted{border-color:#2f7a4d}
.xrr .xrr-cols{display:grid;grid-template-columns:1fr 1fr;gap:6px}
.xrr .xrr-col{border:1px solid #1a202b;border-radius:4px;padding:5px 6px;min-width:0;overflow-wrap:anywhere}
.xrr .xrr-col h4{margin:0 0 3px;font-size:10px;text-transform:uppercase;letter-spacing:.05em;color:var(--sb-dim,#8d99a8)}
.xrr .xrr-rule{display:grid;grid-template-columns:1fr auto;gap:4px 8px;align-items:center;border:1px solid #1a202b;border-radius:4px;padding:5px 6px}
.xrr .xrr-rule .xrr-n{color:var(--sb-dim,#8d99a8);font-variant-numeric:tabular-nums}
.xrr .xrr-rule input[type=number]{width:64px;background:#0e1218;color:inherit;border:1px solid var(--sb-line,#262d3a);border-radius:3px;height:24px;font:inherit}
.xrr .xrr-handle{display:none;flex:0 0 auto;height:18px;cursor:ns-resize;touch-action:none;align-items:center;justify-content:center}
.xrr .xrr-handle::before{content:'';width:42px;height:4px;border-radius:2px;background:#3a4a66}
.xrr .xrr-bar{display:flex;gap:2px;padding:4px 8px 0;flex-wrap:wrap}
.xrr .xrr-more{display:none}
.xrr-banner{position:absolute;left:50%;transform:translateX(-50%);top:8px;z-index:18;max-width:min(720px,calc(100% - 24px));box-sizing:border-box;display:flex;flex-wrap:wrap;gap:8px;align-items:center;padding:8px 12px;background:rgba(20,24,32,.97);color:#dfe6ee;border:1px solid #2d6aa8;border-radius:6px;font:12px/1.35 system-ui,-apple-system,'Segoe UI',sans-serif;box-shadow:0 6px 24px rgba(0,0,0,.45)}
.xrr-banner[hidden]{display:none}
.xrr-banner.err{border-color:#8a3b3b}
.xrr-banner .xrr-msg{flex:1 1 260px;min-width:0;overflow-wrap:anywhere}
.xrr-banner select{background:#0e1218;color:inherit;border:1px solid #262d3a;border-radius:3px;height:26px;font:inherit;max-width:260px}
@media (max-width:640px),(pointer:coarse){
  .xrw.xrr{left:var(--sb-rail,28px);right:var(--dk-rail,28px);width:auto;bottom:${STATUS_H}px;height:45%;max-height:85%;border-radius:12px 12px 0 0;font-size:13px}
  .xrr .xrr-handle{display:flex}
  .xrr .xrr-acts{grid-template-columns:repeat(2,1fr)}
  .xrr .xrr-tbl:not(.open){display:none}
  .xrr .xrr-cols{grid-template-columns:1fr}
  .xrr .xrr-keys{display:none}
  .xrr .xrr-desk{display:none}
  .xrr .xrr-more{display:block}
  .xrr .xrr-btn,.xrr .xrw-btn{min-height:40px}
  .xrr .xrw-foot{display:none}
  .xrr .xrw-foot.on{display:flex}
  .xrr-banner{top:auto;bottom:calc(${STATUS_H}px + 6px);left:8px;right:8px;transform:none;max-width:none}
}
@media (min-width:641px) and (pointer:fine){
  .xrr .xrr-tbl{display:table}
  .xrr .xrr-chips{display:none}
}
`;

/** The styles of the panel and the banner (on top of the review walk's `.xrw…`). */
export function ensureRevisionWalkStyle(): void {
  ensureReviewWalkStyle();
  if (document.getElementById(STYLE_ID)) return;
  const st = document.createElement('style');
  st.id = STYLE_ID;
  st.textContent = CSS;
  document.head.appendChild(st);
}

const pct = (x: number): string => `${Math.round(x * 100)}%`;
const when = (iso: string): string => (iso.length >= 16 ? `${iso.slice(0, 10)} ${iso.slice(11, 16)}` : iso);
const codesText = (r: ClassifyResult | null | undefined): string => (r ? `${r.discipline.code}${r.subDiscipline ? `/${r.subDiscipline.code}` : ''}${r.masterformat ? `/${r.masterformat.division}` : ''}` : '(none)');

export interface RevisionWalkState {
  open: boolean;
  tab: 'walk' | 'bulk' | 'filters' | 'report';
  order: RevisionOrder;
  filters: RevisionFilters;
  scope: 'all' | 'one';
  ghost: GhostMode;
  itemIndex: number;
  items: number;
  elementIndex: number;
  item: { key: string; title: string; category: string; elements: number } | null;
  progress: { total: number; decided: number; accepted: number; rejected: number; unsure: number; skipped: number; undecided: number } | null;
  pending: number;
  editing: boolean;
  unsure: boolean;
  phone: boolean;
  ghostDrawn: { meshes: number; boxes: number; frames: number };
}

export class RevisionWalkPanel {
  private root: HTMLElement | null = null;
  private head!: HTMLElement;
  private tabsEl!: HTMLElement;
  private body!: HTMLElement;
  private dock!: HTMLElement;
  private foot!: HTMLElement;
  private opened = false;
  private mounted = false;
  private tab: RevisionWalkState['tab'] = 'walk';
  private order: RevisionOrder = 'category';
  private filters: RevisionFilters = {};
  private scope: 'all' | 'one' = 'all';
  private items: RevisionItem[] = [];
  private itemIndex = 0;
  private elementIndex = 0;
  private editing: { disc: string; sub: string; div: string } | null = null;
  private unsure = false;
  private note = '';
  private commitNote = '';
  private message: { text: string; error: boolean } | null = null;
  private expanded = new Set<string>();
  private attachChoice: RevisionDecision['attachments'] = 'keep';
  private saved: { pose: Pose; selection: number[] } | null = null;
  private off: (() => void) | null = null;
  private bulkParams = { maxMoveMm: 10, minScore: 0.95 };
  private footOpen = false;
  private touch: { x: number; y: number; t: number } | null = null;

  constructor(private readonly app: ViewerApp, private readonly ctl: RevisionController, private readonly host: PanelHost) {}

  get isOpen(): boolean {
    return this.opened;
  }
  private get phone(): boolean {
    return typeof window !== 'undefined' && (window.matchMedia?.('(max-width:640px), (pointer:coarse)').matches ?? false);
  }

  state(): RevisionWalkState {
    const it = this.item();
    return {
      open: this.opened, tab: this.tab, order: this.order, filters: { ...this.filters }, scope: this.scope, ghost: this.ctl.ghost.mode,
      itemIndex: this.itemIndex, items: this.items.length, elementIndex: this.elementIndex,
      item: it ? { key: it.key, title: it.title, category: it.category, elements: it.elements.length } : null,
      progress: this.ctl.state?.progress() ?? null, pending: this.ctl.pendingCount().changes + this.ctl.pendingCount().other,
      editing: this.editing !== null, unsure: this.unsure, phone: this.phone, ghostDrawn: { ...this.ctl.ghost.lastDrawn },
    };
  }
  list(): Array<{ key: string; title: string; category: string; elements: number }> {
    return this.items.map((i) => ({ key: i.key, title: i.title, category: i.category, elements: i.elements.length }));
  }
  goto(i: number): void {
    if (this.opened) this.goItem(i);
  }

  // ------------------------------------------------------------ data

  private item(): RevisionItem | null {
    return this.items[this.itemIndex] ?? null;
  }
  private entry(): DiffEntry | null {
    const it = this.item();
    return it ? it.entries[Math.min(this.elementIndex, it.entries.length - 1)] ?? null : null;
  }
  private targets(): DiffEntry[] {
    const it = this.item();
    if (!it) return [];
    return this.scope === 'all' ? it.entries : [this.entry()!].filter(Boolean);
  }
  private rebuild(keep = true): void {
    const key = keep ? this.items[this.itemIndex]?.key : undefined;
    this.items = this.ctl.items(this.order, this.filters);
    const at = key ? this.items.findIndex((i) => i.key === key) : -1;
    this.itemIndex = at >= 0 ? at : Math.min(this.itemIndex, Math.max(0, this.items.length - 1));
    if (at < 0) this.elementIndex = 0;
  }
  private saveCursor(): void {
    this.ctl.state?.setCursor({ order: this.order, filters: { ...this.filters }, itemKey: this.item()?.key ?? null, elementIndex: this.elementIndex });
  }

  // ------------------------------------------------------------ open, close

  open(): void {
    const st = this.ctl.state;
    if (!st) return;
    ensureReviewWalkStyle();
    ensureKeyStyles();
    this.ensureStyle();
    if (!this.opened) {
      this.saved = { pose: currentPose(this.app), selection: this.app.selection };
      this.opened = true;
      this.build();
      window.addEventListener('keydown', this.onKey, true);
      this.off = this.ctl.onChange(() => this.onController());
    }
    const c = st.session.cursor;
    this.order = c.order;
    this.filters = { ...c.filters };
    this.items = this.ctl.items(this.order, this.filters);
    const at = c.itemKey ? this.items.findIndex((i) => i.key === c.itemKey) : -1;
    this.itemIndex = at >= 0 ? at : this.firstOpen();
    this.elementIndex = at >= 0 ? Math.min(c.elementIndex, Math.max(0, (this.items[at]?.entries.length ?? 1) - 1)) : 0;
    this.tab = 'walk';
    this.message = null;
    this.host.show(PANEL_ID);
    this.render();
    this.focus();
  }

  /** The first item with an entry that is neither decided nor skipped; item 0 when there is none. */
  private firstOpen(): number {
    const st = this.ctl.state;
    if (!st) return 0;
    const i = this.items.findIndex((it) => it.entries.some((e) => !st.decisionOf(e.key) && !st.isSkipped(e.key)));
    return i >= 0 ? i : 0;
  }

  close(): void {
    if (!this.opened) return;
    this.opened = false;
    window.removeEventListener('keydown', this.onKey, true);
    this.off?.();
    this.off = null;
    this.saveCursor();
    this.host.hide(PANEL_ID);
    this.ctl.ghost.hide();
    const s = this.saved;
    this.saved = null;
    if (s) {
      const smooth = navSettings.smoothMoves;
      navSettings.smoothMoves = false;
      try { moveToPose(this.app, s.pose); } finally { navSettings.smoothMoves = smooth; }
      this.app.selectIds(s.selection);
    }
    const n = this.ctl.pendingCount();
    if (n.changes + n.other > 0) showToast(`${n.changes + n.other} accepted decision${n.changes + n.other === 1 ? '' : 's'} wait for a commit: open the revision walk again`, 3200);
  }

  /** The model was replaced or the session ended: close without touching the camera of the new model. */
  dispose(): void {
    this.saved = null;
    this.close();
  }

  private onController(): void {
    if (!this.opened) return;
    const a = document.activeElement;
    if (a && this.root?.contains(a) && (a.tagName === 'INPUT' || a.tagName === 'TEXTAREA' || a.tagName === 'SELECT')) { this.renderHead(); return; }
    this.render();
  }

  // ------------------------------------------------------------ view: select, frame, ghost

  private focus(): void {
    const it = this.item();
    if (!it) { this.ctl.ghost.hide(); return; }
    const targets = this.targets();
    const idxs = targets.map((e) => it.entries.indexOf(e));
    const head = this.ctl.head;
    const ids: number[] = [];
    const box = new Box3();
    for (const e of targets) {
      const k = it.entries.indexOf(e);
      const b = it.elements[k]!.bounds;
      const f = this.ctl.state!.session.diff.offset;
      // a deleted element's frame comes without the diff offset: add it (viewer axes: x, z, -y)
      const o = e.category === 'deleted' ? [f[0], f[2], -f[1]] : [0, 0, 0];
      box.union(new Box3(new Vector3(b[0]! + o[0]!, b[1]! + o[1]!, b[2]! + o[2]!), new Vector3(b[3]! + o[0]!, b[4]! + o[1]!, b[5]! + o[2]!)));
      const hi = e.head && head ? this.app.controller.model.byGlobalId.get(e.head) : undefined;
      if (hi !== undefined) ids.push(hi);
    }
    this.app.selectIds(ids);
    this.ctl.ghost.show(idxs.flatMap((k) => this.ctl.ghostTargets(it, k)));
    if (!box.isEmpty()) moveToBox(this.app, box, { margin: ids.length > 1 ? 1.2 : 1.8, tag: 'revision' });
  }

  // ------------------------------------------------------------ steps

  private goItem(i: number): void {
    if (this.items.length === 0) return;
    this.itemIndex = Math.max(0, Math.min(this.items.length, i));
    this.elementIndex = 0;
    this.editing = null;
    this.unsure = false;
    this.note = '';
    this.message = null;
    this.attachChoice = 'keep';
    this.saveCursor();
    this.render();
    this.body.scrollTop = 0;
    this.focus();
  }
  private goElement(i: number): void {
    const it = this.item();
    if (!it) return;
    this.elementIndex = Math.max(0, Math.min(it.entries.length - 1, i));
    this.editing = null;
    this.unsure = false;
    this.saveCursor();
    this.render();
    this.focus();
  }
  private next(): void {
    const it = this.item();
    if (!it) return;
    if (this.scope === 'one' && this.elementIndex < it.entries.length - 1) { this.goElement(this.elementIndex + 1); return; }
    this.goItem(this.itemIndex + 1);
  }
  private back(): void {
    if (this.itemIndex >= this.items.length) { this.goItem(this.items.length - 1); return; }
    if (this.scope === 'one' && this.elementIndex > 0) { this.goElement(this.elementIndex - 1); return; }
    if (this.itemIndex > 0) this.goItem(this.itemIndex - 1);
  }

  // ------------------------------------------------------------ decisions

  private accept(which: 'default' | 'other' = 'default', edited?: { discipline: string; subDiscipline: string | null; division: string | null }): void {
    const ts = this.targets();
    if (ts.length === 0) return;
    const e0 = ts[0]!;
    const cls = edited ? 'edited' as const : which === 'other' ? this.ctl.otherFor(e0) ?? undefined : undefined;
    if (which === 'other' && !cls) return;
    this.ctl.decide(ts, {
      verdict: 'accepted', ...(cls ? { classification: cls } : {}), ...(edited ? { edited } : {}), ...(this.unsure ? { unsure: true } : {}), ...(this.note.trim() ? { note: this.note.trim() } : {}),
      ...(e0.category === 'deleted' ? { attachments: this.attachChoice, ...(this.attachChoice === 'reattach' ? { reattachTo: this.pickedGuid() } : {}) } : {}),
    });
    this.message = null;
    this.editing = null;
    this.unsure = false;
    this.note = '';
    this.next();
  }
  private reject(): void {
    const ts = this.targets();
    if (ts.length === 0) return;
    this.ctl.decide(ts, { verdict: 'rejected', ...(this.unsure ? { unsure: true } : {}), ...(this.note.trim() ? { note: this.note.trim() } : {}) });
    this.message = { text: `${ts.length === 1 ? 'Rejected' : `Rejected ${ts.length}`}. It is in the report. Use "Raise issue" to open an issue for it.`, error: false };
    this.editing = null;
    this.unsure = false;
    this.note = '';
    this.next();
  }
  private pickedGuid(): string | undefined {
    const sel = this.app.selection;
    return sel.length === 1 ? this.app.controller.model.elements[sel[0]!]?.globalId : undefined;
  }
  private skipByScope(): void {
    const it = this.item();
    if (!it) return;
    if (this.scope === 'all' && it.entries.length > 1) this.ctl.skip(it.entries); else this.ctl.skip(this.entry() ? [this.entry()!] : []);
    this.next();
  }
  private skipOther(): void {
    const it = this.item();
    if (!it) return;
    if (this.scope === 'all' && it.entries.length > 1) this.ctl.skip(this.entry() ? [this.entry()!] : []); else this.ctl.skip(it.entries);
    this.next();
  }
  private undoLast(): void {
    const label = this.ctl.undoLast();
    this.message = label ? { text: `Undid: ${label}.`, error: false } : { text: 'Nothing to undo.', error: false };
    this.rebuild();
    this.render();
    this.focus();
  }
  private startEdit(): void {
    const e = this.entry();
    if (!e || e.category === 'deleted') return;
    const r = this.ctl.headResult(e) ?? this.ctl.baseResult(e);
    if (!r) return;
    this.editing = { disc: r.discipline.code, sub: r.subDiscipline?.code ?? '', div: r.masterformat?.division ?? '' };
    this.render();
    this.root?.querySelector<HTMLElement>('.xrw-edit select')?.focus();
  }
  private applyEdit(): void {
    const e = this.editing;
    if (!e) return;
    this.accept('default', { discipline: e.disc, subDiscipline: e.sub || null, division: e.div || null });
  }
  private cycleGhost(): void {
    this.ctl.ghost.setMode(nextGhostMode(this.ctl.ghost.mode));
    showToast(GHOST_MODE_LABEL[this.ctl.ghost.mode], 900);
    this.render();
  }
  private raise(): void {
    const ts = this.targets();
    const g = this.ctl.raiseIssue(ts);
    this.message = g ? { text: 'Issue raised. It is in the Issues tab.', error: false } : { text: 'The issue could not be raised.', error: true };
    this.render();
  }
  private async commit(): Promise<void> {
    const input = this.foot.querySelector<HTMLInputElement>('input[data-role=reviewer]');
    if (input && input.value.trim()) this.ctl.svc.review.setReviewer(input.value);
    try {
      const r = await this.ctl.commit(this.commitNote);
      this.commitNote = '';
      const parts = [r.changes ? `${r.changes} change${r.changes === 1 ? '' : 's'} committed as ${r.commitId}` : '', r.carried ? `${r.carried} carried decision commit${r.carried === 1 ? '' : 's'}` : '', r.attachments ? `${r.attachments} issue${r.attachments === 1 ? '' : 's'} updated` : ''].filter(Boolean);
      this.message = { text: parts.length ? `${parts.join('; ')}.` : 'Nothing to commit.', error: false };
    } catch (e) {
      this.message = { text: e instanceof Error ? e.message : String(e), error: true };
    }
    this.render();
  }
  private exportReport(): void {
    const r = this.ctl.report();
    if (!r) return;
    downloadText(r.names.csv, r.csv);
    setTimeout(() => downloadText(r.names.summary, r.summary, 'text/markdown;charset=utf-8'), 300);
    this.message = { text: `Saved ${r.names.csv} and ${r.names.summary}.`, error: false };
    this.render();
  }

  // ------------------------------------------------------------ keys and touch

  private readonly onKey = (e: KeyboardEvent): void => {
    if (!this.opened || e.defaultPrevented) return;
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    if (getKeymap()?.anyOverlayOpen()) return;
    const t = e.target as HTMLElement | null;
    const tag = t?.tagName ?? '';
    const inputType = tag === 'INPUT' ? (t as HTMLInputElement).type : '';
    const typing = (tag === 'INPUT' && inputType !== 'checkbox' && inputType !== 'radio') || tag === 'TEXTAREA' || !!t?.isContentEditable;
    const take = (): void => { e.preventDefault(); e.stopPropagation(); };
    if (e.key === 'Escape') {
      take();
      if (this.editing) { this.editing = null; this.render(); } else if (this.tab !== 'walk') { this.tab = 'walk'; this.render(); } else this.close();
      return;
    }
    if (typing || this.tab !== 'walk') return;
    if (tag === 'BUTTON' && (e.key === 'Enter' || e.key === ' ')) return;
    const k = e.key.length === 1 ? e.key.toLowerCase() : e.key;
    if (this.editing) {
      if (k === 'Enter') { take(); this.applyEdit(); } else if (k === '?') { take(); this.toggleUnsure(); } else if ((k === 'n' || k === 'ArrowRight') && tag !== 'SELECT') { take(); if (e.shiftKey && k === 'n') this.skipOther(); else this.skipByScope(); }
      return;
    }
    if (!this.item()) { if (k === 'ArrowLeft') { take(); this.back(); } else if (k === 'u') { take(); this.undoLast(); } return; }
    switch (k) {
      case 'Enter': case 'y': take(); this.accept(); break;
      case '2': take(); this.accept('other'); break;
      case 'e': take(); this.startEdit(); break;
      case 'r': take(); this.reject(); break;
      case 'n': take(); if (e.shiftKey) this.skipOther(); else this.skipByScope(); break;
      case 'ArrowRight': take(); this.skipByScope(); break;
      case '?': take(); this.toggleUnsure(); break;
      case 'ArrowLeft': take(); this.back(); break;
      case ']': take(); this.goElement(this.elementIndex + 1); break;
      case '[': take(); this.goElement(this.elementIndex - 1); break;
      case 'a': take(); this.scope = this.scope === 'all' ? 'one' : 'all'; this.render(); this.focus(); break;
      case 'u': take(); this.undoLast(); break;
      case 'g': take(); this.cycleGhost(); break;
      case 'b': take(); this.tab = 'bulk'; this.render(); break;
      default: break;
    }
  };

  private toggleUnsure(): void {
    this.unsure = !this.unsure;
    this.renderDock();
  }

  private bindTouch(b: HTMLElement): void {
    b.addEventListener('touchstart', (ev) => { const t = ev.touches[0]; if (t) this.touch = { x: t.clientX, y: t.clientY, t: Date.now() }; }, { passive: true });
    b.addEventListener('touchend', (ev) => {
      const s = this.touch;
      this.touch = null;
      const t = ev.changedTouches[0];
      if (!s || !t || this.tab !== 'walk' || this.editing) return;
      const dx = t.clientX - s.x, dy = t.clientY - s.y;
      if (Math.abs(dx) > 70 && Math.abs(dy) < 45 && Date.now() - s.t < 900) { if (dx < 0) this.skipByScope(); else this.back(); }
    }, { passive: true });
  }

  private bindHandle(h: HTMLElement): void {
    let start: { y: number; h: number } | null = null;
    h.addEventListener('pointerdown', (ev) => { if (!this.root) return; start = { y: ev.clientY, h: this.root.getBoundingClientRect().height }; h.setPointerCapture(ev.pointerId); });
    h.addEventListener('pointermove', (ev) => {
      if (!start || !this.root) return;
      const host = this.root.parentElement?.getBoundingClientRect().height ?? window.innerHeight;
      const px = Math.max(host * 0.3, Math.min(host * 0.85, start.h + (start.y - ev.clientY)));
      this.root.style.height = `${Math.round((px / host) * 100)}%`;
    });
    const end = (): void => { start = null; };
    h.addEventListener('pointerup', end);
    h.addEventListener('pointercancel', end);
    h.addEventListener('dblclick', () => { if (this.root) this.root.style.height = this.root.style.height === '85%' ? '45%' : '85%'; });
  }

  // ------------------------------------------------------------ DOM

  private ensureStyle(): void {
    ensureRevisionWalkStyle();
  }

  private build(): void {
    const root = el('section', 'xrw xrr', { role: 'dialog', 'data-testid': 'revision-walk' });
    const handle = el('div', 'xrr-handle', { 'aria-label': 'Drag to resize', title: 'Drag up for more room, double tap to switch' });
    this.head = el('div', 'xrw-head');
    this.tabsEl = el('div', 'xrw-tabs', { role: 'tablist' });
    this.body = el('div', 'xrw-body');
    this.dock = el('div', 'xrw-dock', { 'data-role': 'dock' });
    this.foot = el('div', 'xrw-foot');
    root.append(handle, this.head, this.tabsEl, this.body, this.dock, this.foot);
    this.bindTouch(this.body);
    this.bindHandle(handle);
    this.host.mount(PANEL_ID, 'Revision walk', root);
    this.mounted = true;
    this.root = root;
  }

  private btn(label: string, act: string, onClick: () => void, o: { primary?: boolean; key?: string; title?: string; disabled?: boolean; help?: string; cls?: string } = {}): HTMLButtonElement {
    const b = el('button', `xrw-btn${o.primary ? ' primary' : ''}${o.cls ? ` ${o.cls}` : ''}`, { type: 'button', 'data-act': act, ...(o.help ? { 'data-help': o.help } : {}) }, label);
    if (o.key) b.appendChild(el('kbd', undefined, undefined, o.key));
    if (o.title) b.title = o.title;
    b.disabled = o.disabled === true;
    b.addEventListener('click', onClick);
    return b;
  }

  private select(label: string, value: string, options: Array<[string, string]>, onChange: (v: string) => void, role?: string): HTMLElement {
    const l = el('label');
    const s = el('select', undefined, { 'aria-label': label, ...(role ? { 'data-role': role } : {}) });
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
    else if (this.tab === 'bulk') this.renderBulk();
    else if (this.tab === 'filters') this.renderFilters();
    else this.renderReport();
    this.renderFoot();
  }

  private renderHead(): void {
    const p = this.ctl.state?.progress();
    this.head.replaceChildren(
      el('div', 'xrw-title', undefined, 'Revision'),
      el('div', 'xrw-prog', { 'data-role': 'progress', 'aria-live': 'polite' }, p ? `${p.decided} of ${p.total} decided · ${p.skipped} skipped` : ''),
    );
    const x = el('button', 'xrw-x', { type: 'button', 'aria-label': 'Close the revision walk', title: 'Close the panel. Your decisions are kept (Esc)' }, '×');
    x.addEventListener('click', () => this.close());
    this.head.appendChild(x);
  }

  private renderTabs(): void {
    const mk = (id: RevisionWalkState['tab'], label: string): HTMLButtonElement => {
      const b = el('button', `xrw-tab${this.tab === id ? ' on' : ''}`, { type: 'button', role: 'tab', 'data-tab': id, 'aria-selected': String(this.tab === id) }, label);
      b.addEventListener('click', () => { this.tab = id; this.editing = null; this.render(); });
      return b;
    };
    this.tabsEl.replaceChildren(mk('walk', 'Walk'), mk('bulk', 'Bulk'), mk('filters', 'Filters'), mk('report', 'Report'));
  }

  private msgLine(): HTMLElement | null {
    return this.message ? el('div', this.message.error ? 'xrw-err' : 'xrw-ok', { role: 'status', 'data-role': 'message' }, this.message.text) : null;
  }

  private renderWalk(): void {
    const b = this.body;
    const ctl = this.ctl;
    const st = ctl.state!;
    const it = this.item();
    if (this.items.length === 0) {
      b.append(el('div', 'xrw-warn', undefined, st.session.diff.entries.length === 0 ? 'The two models have no differences.' : 'No change matches these filters.'));
      return;
    }
    if (!it) {
      const p = st.progress();
      b.append(
        el('div', 'xrw-item', { 'data-role': 'end' }, 'End of the walk'),
        el('div', 'xrw-meta', undefined, `${p.accepted} accepted, ${p.rejected} rejected, ${p.skipped} skipped, ${p.undecided - p.skipped} undecided of ${p.total}.`),
        el('div', 'xrr-row xrw-row'),
      );
      (b.lastChild as HTMLElement).append(this.btn('Back to the last item', 'back', () => this.back()), this.btn('Export report', 'export-report', () => this.exportReport(), { primary: true, help: 'Revision walk/Export report' }));
      const m = this.msgLine();
      if (m) b.appendChild(m);
      this.renderDock();
      return;
    }
    const e = this.entry()!;
    const k = it.entries.indexOf(e);
    const el0 = it.elements[k]!;
    const bi = ctl.baseIndexOf(e), hi = ctl.headIndexOf(e);
    const d = st.decisionOf(e.key);
    b.appendChild(el('div', 'xrw-item', { 'data-role': 'item' }, `${this.itemIndex + 1} of ${this.items.length}: ${it.title}`));
    const badges = el('div', undefined, { 'data-role': 'badges' });
    badges.appendChild(el('span', `xrr-badge ${e.category}`, { 'data-role': 'category' }, CATEGORY_LABEL[e.category]));
    if (e.score !== undefined) badges.appendChild(el('span', 'xrw-dim', undefined, `match ${e.score.toFixed(2)}`));
    b.appendChild(badges);
    const where = [el0.storeyName && `Storey ${el0.storeyName}`, el0.system && `System ${el0.system}`].filter(Boolean).join(', ');
    b.appendChild(el('div', 'xrw-meta', { 'data-role': 'element' }, `${el0.ifcClass}, ${el0.name || '(no name)'}${el0.tag ? `, tag ${el0.tag}` : ''}${where ? `. ${where}` : ''}`));
    if (it.entries.length > 1) {
      const r = el('div', 'xrw-bar');
      const mkRadio = (v: 'all' | 'one', label: string): HTMLElement => {
        const l = el('label');
        const i = el('input', undefined, { type: 'radio', name: 'xrr-scope', value: v, 'data-role': `scope-${v}` });
        i.checked = this.scope === v;
        i.addEventListener('change', () => { this.scope = v; this.render(); this.focus(); });
        l.append(i, el('span', undefined, undefined, label));
        return l;
      };
      r.append(mkRadio('all', `All ${it.entries.length} alike`), mkRadio('one', 'This element only'),
        this.btn('‹', 'prev-element', () => this.goElement(this.elementIndex - 1), { title: 'Previous element of this item ([)', disabled: this.elementIndex === 0 }),
        el('span', 'xrw-dim', { 'data-role': 'element-count' }, `${this.elementIndex + 1} / ${it.entries.length}`),
        this.btn('›', 'next-element', () => this.goElement(this.elementIndex + 1), { title: 'Next element of this item (])', disabled: this.elementIndex >= it.entries.length - 1 }));
      b.appendChild(r);
    }

    // what changed
    const rows = changeRows(e, ctl.base, ctl.head, bi, hi);
    if (e.category === 'changed' || e.category === 'rematched') {
      const chips = el('div', 'xrr-chips', { 'data-role': 'chips' });
      const open = this.expanded.has(e.key);
      for (const f of e.flags) { const c = el('button', 'xrr-chip', { type: 'button', role: 'button', 'data-flag': f, 'aria-expanded': String(open) }, FLAG_LABEL[f]); c.addEventListener('click', () => { if (open) this.expanded.delete(e.key); else this.expanded.add(e.key); this.render(); }); chips.appendChild(c); }
      if (e.flags.length === 0) chips.appendChild(el('span', 'xrr-chip', undefined, 'Same, new GlobalId'));
      b.appendChild(chips);
      const tbl = el('table', `xrw-tbl xrr-tbl${this.expanded.has(e.key) ? ' open' : ''}`, { 'data-role': 'what-changed' });
      const head = el('thead');
      const hr = el('tr');
      for (const h of ['What', 'Before', 'After']) hr.appendChild(el('th', undefined, undefined, h));
      head.appendChild(hr);
      const tb = el('tbody');
      for (const r of rows) {
        const tr = el('tr');
        tr.appendChild(el('td', 'xrw-dim', undefined, r.label ? `${FLAG_LABEL[r.flag]}: ${r.label}` : FLAG_LABEL[r.flag]));
        if (r.text !== undefined) { const td = el('td', undefined, undefined, r.text); td.colSpan = 2; tr.appendChild(td); } else tr.append(el('td', undefined, undefined, r.before ?? ''), el('td', undefined, undefined, r.after ?? ''));
        tb.appendChild(tr);
      }
      if (e.flags.length === 0) { const tr = el('tr'); const td = el('td', 'xrw-dim', undefined, 'The shape, place and properties are the same. Only the GlobalId differs.'); td.colSpan = 3; tr.appendChild(td); tb.appendChild(tr); }
      tbl.append(head, tb);
      b.appendChild(tbl);
    } else if (e.category === 'deleted') {
      b.appendChild(el('div', 'xrw-warn', undefined, 'This element is in the earlier model and not in this one. The red ghost shows where it was.'));
    } else {
      b.appendChild(el('div', 'xrw-ok', undefined, 'This element is new in this model. The green frame marks it.'));
    }

    // classification: the base decision beside the new proposal
    const baseR = ctl.baseResult(e), headR = ctl.headResult(e);
    const col = (title: string, r: ClassifyResult | null, extra?: string): HTMLElement => {
      const c = el('div', 'xrr-col');
      c.appendChild(el('h4', undefined, undefined, title));
      if (!r) { c.appendChild(el('div', 'xrw-dim', undefined, 'none')); return c; }
      c.appendChild(el('div', undefined, { 'data-role': title.toLowerCase().replace(/\s+/g, '-') }, `${codesText(r)} (${pct(overallConfidence(r))})`));
      const src = r.source === 'confirmed' || r.source === 'corrected' ? `${r.source}${r.unsure ? ' (unsure)' : ''} by ${r.confirmedBy ?? '?'}, ${when(r.confirmedAt ?? '')}` : r.source === 'rules' ? 'rule' : r.source === 'cache' && r.rationale?.startsWith('suggested') ? 'suggested from the earlier model' : `model ${r.model ?? r.source}`;
      c.appendChild(el('div', 'xrw-dim', undefined, src));
      if (extra) c.appendChild(el('div', 'xrw-warn', undefined, extra));
      return c;
    };
    if (e.category === 'new') {
      b.appendChild(col('Proposal', headR, headR?.needsReview ? 'Needs review' : undefined));
    } else if (e.category === 'deleted') {
      b.appendChild(col('Earlier decision', baseR));
    } else {
      const cols = el('div', 'xrr-cols', { 'data-role': 'classification' });
      cols.append(col('Earlier decision', baseR), col('Now', headR, headR?.needsReview ? 'Needs review' : undefined));
      b.appendChild(cols);
      const def = ctl.defaultFor(e), other = ctl.otherFor(e);
      b.appendChild(el('div', 'xrw-dim', { 'data-role': 'default-note' }, `Enter takes ${def === 'kept' ? 'the earlier decision' : 'the new proposal'}${other ? `. 2 takes ${other === 'kept' ? 'the earlier decision' : 'the new proposal'}` : ''}.`));
    }

    // attachments
    const att = ctl.attachCountOf(e);
    if (att.issues + att.sketches > 0) {
      b.appendChild(el('div', 'xrw-meta', { 'data-role': 'attachments' }, `${att.issues} issue${att.issues === 1 ? '' : 's'}, ${att.sketches} sketch${att.sketches === 1 ? '' : 'es'} attached${e.category === 'rematched' ? '. Accepting the match moves them to the new GlobalId.' : ''}`));
      if (e.category === 'deleted') {
        const box = el('div', 'xrw-box', { 'data-role': 'attach-choice' });
        for (const [v, label] of [['keep', 'Keep, flagged'], ['reattach', 'Re-attach to the selected element'], ['resolve', 'Resolve issues']] as const) {
          const l = el('label');
          const i = el('input', undefined, { type: 'radio', name: 'xrr-attach', value: v });
          i.checked = this.attachChoice === v;
          i.addEventListener('change', () => { this.attachChoice = v; });
          l.append(i, el('span', undefined, undefined, label));
          box.appendChild(l);
        }
        b.appendChild(box);
      }
    }

    if (d) {
      const s = el('div', `xrr-state ${d.verdict}`, { 'data-role': 'decision' }, `${d.verdict === 'accepted' ? 'Accepted' : 'Rejected'}${d.classification !== 'none' ? ` (${d.classification === 'kept' ? 'earlier classification' : d.classification === 'new' ? 'new classification' : 'edited classification'})` : ''}${d.unsure ? ', unsure' : ''}${d.commitId && d.commitId !== 'applied' ? `, committed as ${d.commitId}` : d.commitId ? ', applied' : ''}${d.bulk ? `, by a bulk rule` : ''}.${d.note ? ` ${d.note}` : ''}`);
      b.appendChild(s);
    } else if (st.isSkipped(e.key)) b.appendChild(el('div', 'xrw-dim', undefined, 'You skipped this one earlier.'));
    const pend = ctl.svc.review.pendingFor(e.head ?? '');
    if (pend) b.appendChild(el('div', 'xrw-ok', { 'data-role': 'pending-state' }, `Pending: ${pend.action === 'confirm' ? 'confirmed' : `corrected to ${pend.after.discipline}${pend.after.subDiscipline ? `/${pend.after.subDiscipline}` : ''}${pend.after.division ? `/${pend.after.division}` : ''}`}. It is written when you commit.`));

    const c = el('input', undefined, { type: 'text', placeholder: 'Note (optional)', 'aria-label': 'Note', 'data-role': 'note-text', maxlength: '300' });
    c.value = this.note;
    c.addEventListener('input', () => { this.note = c.value; });
    b.appendChild(c);

    if (this.editing) {
      const ed = this.editing;
      const box = el('div', 'xrw-box xrw-edit');
      const fill = (): void => {
        const dsc = findDiscipline(ctl.svc.schema, ed.disc);
        box.replaceChildren(
          el('div', 'xrw-meta', undefined, `Correct ${this.scope === 'all' && it.entries.length > 1 ? `all ${it.entries.length}` : 'this element'}`),
          this.select('Discipline', ed.disc, ctl.svc.schema.disciplines.map((x): [string, string] => [x.code, `${x.code} ${x.label}`]), (v) => { ed.disc = v; ed.sub = ''; fill(); }, 'edit-discipline'),
          this.select('Sub-discipline', ed.sub, [['', '(none)'], ...(dsc?.subDisciplines ?? []).map((s): [string, string] => [s.code, `${s.code} ${s.label}`])], (v) => { ed.sub = v; }, 'edit-sub'),
          this.select('Division', ed.div, [['', '(none)'], ...ctl.svc.schema.masterformat.divisions.map((x): [string, string] => [x.division, `${x.division} ${x.title}`])], (v) => { ed.div = v; }, 'edit-division'),
        );
      };
      fill();
      b.appendChild(box);
    }
    const m = this.msgLine();
    if (m) b.appendChild(m);
    this.renderDock();
  }

  private renderDock(): void {
    this.dock.replaceChildren();
    const it = this.tab === 'walk' ? this.item() : null;
    const e = this.entry();
    if (!it || !e) return;
    const unsureBox = el('label', 'xrw-unsure');
    unsureBox.title = 'Optional. Tick it when this is a guess: the decision is recorded as unsure.';
    const chk = el('input', undefined, { type: 'checkbox', 'data-role': 'unsure', 'aria-label': 'Unsure (a guess)', 'data-help': 'Revision walk/Unsure' });
    chk.checked = this.unsure;
    chk.addEventListener('change', () => { this.unsure = chk.checked; });
    unsureBox.append(chk, el('span', undefined, undefined, 'Unsure'), el('kbd', undefined, undefined, '?'));
    const acts = el('div', 'xrw-acts xrr-acts');
    if (this.editing) {
      acts.append(
        this.btn('Apply correction', 'apply-edit', () => this.applyEdit(), { primary: true, key: 'Enter' }),
        this.btn('Skip', 'skip-edit', () => this.skipByScope(), { key: 'N' }),
        this.btn('Cancel', 'cancel-edit', () => { this.editing = null; this.render(); }, { key: 'Esc' }),
      );
      this.dock.append(unsureBox, acts);
      return;
    }
    const other = this.ctl.otherFor(e);
    const n = it.entries.length;
    const verb = e.category === 'deleted' ? 'Acknowledge' : e.category === 'new' ? 'Accept new' : e.category === 'rematched' ? 'Same element' : 'Accept';
    acts.append(
      this.btn(verb, 'accept', () => this.accept(), { primary: true, key: 'Enter', help: 'Revision walk/Accept' }),
      this.btn('Reject', 'reject', () => this.reject(), { key: 'R', title: e.category === 'deleted' ? 'This should not be gone' : e.category === 'new' ? 'This should not be here' : e.category === 'rematched' ? 'This is not the same element' : 'This change is wrong', help: 'Revision walk/Reject' }),
      this.btn(n > 1 && this.scope === 'all' ? `Skip all ${n}` : 'Skip', 'skip', () => this.skipByScope(), { key: 'N', help: 'Revision walk/Skip', title: 'Leave it undecided and go on. A skip is kept with the session.' }),
    );
    const more = this.btn('More', 'more', () => { this.tab = 'bulk'; this.render(); }, { cls: 'xrr-more', title: 'Bulk rules, filters and the report', help: 'Revision walk/More' });
    acts.append(
      this.btn(other ? (other === 'kept' ? 'Use earlier' : 'Use new') : 'Other', 'other', () => this.accept('other'), { key: '2', cls: 'xrr-desk', disabled: !other, help: 'Revision walk/Other', title: other ? 'Accept with the other classification' : 'There is no other classification to take' }),
      this.btn('Edit…', 'edit', () => this.startEdit(), { key: 'E', cls: 'xrr-desk', disabled: e.category === 'deleted', help: 'Revision walk/Edit', title: 'Pick the codes by hand, then accept' }),
      this.btn('Back', 'back', () => this.back(), { key: '←', cls: 'xrr-desk', disabled: this.itemIndex === 0 && this.elementIndex === 0 }),
      this.btn('Undo', 'undo', () => this.undoLast(), { key: 'U', cls: 'xrr-desk', disabled: this.ctl.undoStack.length === 0 }),
      this.btn(GHOST_MODE_LABEL[this.ctl.ghost.mode].replace('Ghost: ', 'Ghost '), 'ghost', () => this.cycleGhost(), { key: 'G', cls: 'xrr-desk', help: 'Revision walk/Ghost', title: 'Show the earlier shape, the new one, or both' }),
      this.btn('Bulk', 'bulk', () => { this.tab = 'bulk'; this.render(); }, { key: 'B', cls: 'xrr-desk', help: 'Revision walk/Bulk' }),
      more,
    );
    const d = this.ctl.state?.decisionOf(e.key);
    if (d?.verdict === 'rejected') acts.append(this.btn('Raise issue', 'raise-issue', () => this.raise(), { help: 'Revision walk/Raise issue', title: 'Open an issue for this element. Rejecting never does it by itself.' }));
    this.dock.append(unsureBox, acts, el('div', 'xrw-dim xrr-keys', undefined, 'Keys: Enter or Y accept, 2 other, E edit, R reject, N or right arrow skip (Shift+N the rest), ? unsure, left arrow back, [ ] step, A all/one, U undo, G ghost, B bulk, Esc close.'));
  }

  private renderBulk(): void {
    const b = this.body;
    const ctl = this.ctl;
    b.appendChild(el('div', 'xrw-meta', undefined, 'Each rule shows how many undecided changes it takes. Point at one to see them in the view. A rule is one undo step (U).'));
    const rules = ctl.bulkRules(this.bulkParams);
    for (const rule of rules) {
      const entries = ctl.bulkSelect(rule, this.filters);
      const r = el('div', 'xrr-rule', { 'data-rule': rule.id });
      const label = el('div', undefined, undefined, rule.label);
      const right = el('div', 'xrw-row');
      right.appendChild(el('span', 'xrr-n', { 'data-role': 'rule-count' }, `${entries.length}`));
      if (rule.id === 'placement-moves') {
        const i = el('input', undefined, { type: 'number', min: '1', max: '1000', step: '1', 'aria-label': 'Largest move in millimetres', value: String(this.bulkParams.maxMoveMm), 'data-role': 'rule-mm' });
        i.addEventListener('change', () => { const v = Number(i.value); if (Number.isFinite(v) && v > 0) { this.bulkParams.maxMoveMm = v; this.render(); } });
        right.appendChild(i);
      }
      if (rule.id === 'rematch-high') {
        const i = el('input', undefined, { type: 'number', min: '0.5', max: '1', step: '0.01', 'aria-label': 'Lowest match score', value: String(this.bulkParams.minScore), 'data-role': 'rule-score' });
        i.addEventListener('change', () => { const v = Number(i.value); if (Number.isFinite(v) && v > 0 && v <= 1) { this.bulkParams.minScore = v; this.render(); } });
        right.appendChild(i);
      }
      const show = (): void => { const ids = entries.map((e) => (e.head ? this.app.controller.model.byGlobalId.get(e.head) : undefined)).filter((x): x is number => x !== undefined); this.app.selectIds(ids); };
      right.appendChild(this.btn('Show', 'rule-show', show, { title: 'Select these elements in the view' }));
      right.appendChild(this.btn('Apply', 'rule-apply', () => { const n = ctl.applyBulk(rule, this.filters); this.message = { text: `${rule.label}: ${n} accepted. Press U to undo the whole rule.`, error: false }; this.rebuild(); this.tab = 'bulk'; this.render(); }, { primary: true, disabled: entries.length === 0, help: 'Revision walk/Apply rule' }));
      r.append(label, right);
      r.addEventListener('pointerenter', show);
      b.appendChild(r);
    }
    b.appendChild(this.btn('Back to the walk', 'to-walk', () => { this.tab = 'walk'; this.render(); this.focus(); }));
    const m = this.msgLine();
    if (m) b.appendChild(m);
  }

  private renderFilters(): void {
    const b = this.body;
    const st = this.ctl.state!;
    const f = this.filters;
    const set = (patch: Partial<RevisionFilters>, drop: Array<keyof RevisionFilters> = []): void => { this.filters = { ...this.filters, ...patch }; for (const k of drop) delete this.filters[k]; this.itemIndex = 0; this.rebuild(false); this.saveCursor(); this.render(); };
    const storeys = [...new Set(st.session.diff.entries.map((e) => { const i = this.ctl.headIndexOf(e) ?? this.ctl.baseIndexOf(e); const s = e.category === 'deleted' ? this.ctl.base : this.ctl.head; return i === undefined || !s ? '' : s.storey[i]?.name ?? ''; }).filter(Boolean))];
    const classes = [...new Set(st.session.diff.entries.map((e) => { const i = this.ctl.headIndexOf(e) ?? this.ctl.baseIndexOf(e); const s = e.category === 'deleted' ? this.ctl.base : this.ctl.head; return i === undefined || !s ? '' : s.ifcClass[i]!; }).filter(Boolean))].sort();
    const bar = el('div', 'xrw-bar');
    bar.append(
      this.select('Order', this.order, REVISION_ORDERS.map((o): [string, string] => [o, REVISION_ORDER_LABEL[o]]), (v) => { this.order = v as RevisionOrder; this.rebuild(false); this.saveCursor(); this.render(); }, 'order'),
      this.select('Kind', f.category ?? '', [['', 'All'], ...CATEGORIES.filter((c) => c !== 'unchanged').map((c): [string, string] => [c, CATEGORY_LABEL[c]])], (v) => (v ? set({ category: v as DiffEntry['category'] }) : set({}, ['category'])), 'filter-category'),
      this.select('Change', f.flag ?? '', [['', 'All'], ...CHANGE_FLAGS.map((c): [string, string] => [c, FLAG_LABEL[c]])], (v) => (v ? set({ flag: v as NonNullable<RevisionFilters['flag']> }) : set({}, ['flag'])), 'filter-flag'),
      this.select('Storey', f.storey ?? '', [['', 'All'], ...storeys.map((s): [string, string] => [s, s])], (v) => (v ? set({ storey: v }) : set({}, ['storey'])), 'filter-storey'),
      this.select('Class', f.ifcClass ?? '', [['', 'All'], ...classes.map((s): [string, string] => [s, s])], (v) => (v ? set({ ifcClass: v }) : set({}, ['ifcClass'])), 'filter-class'),
    );
    b.appendChild(bar);
    const chk = (label: string, key: 'undecided' | 'unsure' | 'onlySkipped' | 'hasAttachments', role: string): HTMLElement => {
      const l = el('label');
      const i = el('input', undefined, { type: 'checkbox', 'data-role': role });
      i.checked = f[key] === true;
      i.addEventListener('change', () => (i.checked ? set({ [key]: true }) : set({}, [key])));
      l.append(i, el('span', undefined, undefined, label));
      return l;
    };
    const bar2 = el('div', 'xrw-bar');
    bar2.append(chk('Only undecided', 'undecided', 'filter-undecided'), chk('Only unsure', 'unsure', 'filter-unsure'), chk('Only skipped', 'onlySkipped', 'filter-skipped'), chk('Only with issues or sketches', 'hasAttachments', 'filter-attach'));
    const mv = el('label');
    const mi = el('input', undefined, { type: 'number', min: '0', step: '1', 'aria-label': 'Smallest move in millimetres', 'data-role': 'filter-minmove', value: f.minMove !== undefined ? String(Math.round(f.minMove * 1000)) : '' });
    mi.addEventListener('change', () => { const v = Number(mi.value); if (mi.value === '' || !Number.isFinite(v)) set({}, ['minMove']); else set({ minMove: v / 1000 }); });
    mv.append(el('span', undefined, undefined, 'Moved at least (mm)'), mi);
    bar2.appendChild(mv);
    b.appendChild(bar2);
    const unchanged = st.session.diff.counts.unchanged;
    const row = el('div', 'xrw-row');
    row.append(el('span', 'xrr-chip', { 'data-role': 'unchanged-chip' }, `${unchanged} unchanged (not visited)`), this.btn('Select them in the view', 'select-unchanged', () => {
      const listed = new Set(st.session.diff.entries.map((e) => e.head).filter(Boolean));
      this.app.selectIds(this.app.controller.model.elements.filter((e) => !listed.has(e.globalId)).map((e) => e.id));
    }, { title: 'Select the elements that did not change, to see them' }));
    b.appendChild(row);
    b.appendChild(el('div', 'xrw-meta', { 'data-role': 'filter-count' }, `${this.items.length} item${this.items.length === 1 ? '' : 's'} match.`));
    b.appendChild(this.btn('Back to the walk', 'to-walk', () => { this.tab = 'walk'; this.render(); this.focus(); }, { primary: true }));
  }

  private renderReport(): void {
    const b = this.body;
    const st = this.ctl.state!;
    const p = st.progress();
    const s = st.session;
    b.appendChild(el('div', 'xrw-item', undefined, `${s.baseName} to ${s.head.name}`));
    const tbl = el('table', 'xrw-tbl', { 'data-role': 'report-counts' });
    const tb = el('tbody');
    const line = (a: string, n: number | string): void => { const tr = el('tr'); tr.append(el('td', 'xrw-dim', undefined, a), el('td', undefined, undefined, String(n))); tb.appendChild(tr); };
    for (const c of CATEGORIES) line(CATEGORY_LABEL[c], s.diff.counts[c]);
    line('Accepted', p.accepted); line('Rejected', p.rejected); line('Skipped', p.skipped); line('Undecided', p.undecided - p.skipped);
    if (s.carried) line('Carried over', `${s.carried.results} results, ${s.carried.commits.length} commits`);
    tbl.appendChild(tb);
    b.appendChild(tbl);
    b.appendChild(el('div', 'xrw-meta', undefined, `The report has one row for each of the ${p.total} changed elements, with the verdict and who decided. Status: ${s.status}.${this.ctl.persistent ? '' : ' The session is kept for this page only (no browser storage).'}`));
    b.appendChild(el('div', 'xrw-row'));
    (b.lastChild as HTMLElement).append(this.btn('Export report', 'export-report', () => this.exportReport(), { primary: true, help: 'Revision walk/Export report' }));
    const m = this.msgLine();
    if (m) b.appendChild(m);
  }

  private renderFoot(): void {
    const review = this.ctl.svc.review;
    const n = this.ctl.pendingCount();
    const f = this.foot;
    f.replaceChildren();
    f.classList.toggle('on', this.footOpen);
    const name = el('input', undefined, { type: 'text', 'data-role': 'reviewer', placeholder: 'Your name or initials', 'aria-label': 'Reviewer name or initials', autocomplete: 'off', maxlength: '80' });
    name.value = review.reviewer();
    if (review.reviewer()) {
      const who = el('span', 'xrw-dim', { 'data-role': 'reviewer-label' }, `Reviewer: ${review.reviewer()}`);
      const change = el('button', 'xrw-btn', { type: 'button', 'data-act': 'change-reviewer' }, 'Change');
      change.addEventListener('click', () => { review.setReviewer(''); this.render(); });
      f.append(who, change);
    } else f.append(name);
    const total = n.changes + n.other;
    const note = el('input', undefined, { type: 'text', 'data-role': 'commit-note', placeholder: 'Note for the commit (optional)', 'aria-label': 'Commit note', maxlength: '300' });
    note.value = this.commitNote;
    note.addEventListener('input', () => { this.commitNote = note.value; });
    f.append(note, this.btn(`Commit ${total} decision${total === 1 ? '' : 's'}`, 'commit', () => void this.commit(), { primary: true, disabled: total === 0, help: 'Revision walk/Commit', title: total === 0 ? 'Nothing is waiting' : 'Write the accepted changes as one commit of the review log, carry the decisions of accepted matches and update attached issues' }));
    // on a phone the foot is hidden until asked for: a single button in the dock row toggles it
    if (this.phone) {
      const t = el('button', 'xrw-btn', { type: 'button', 'data-act': 'foot-toggle' }, this.footOpen ? 'Hide commit' : `Commit (${total})`);
      t.addEventListener('click', () => { this.footOpen = !this.footOpen; this.renderFoot(); });
      this.tabsEl.appendChild(t);
    }
  }

  // exposed for the plugin: the banner and the walk share the host
  get mountedNow(): boolean {
    return this.mounted;
  }

  /** Where a base point lands in the head's viewer frame (for tests). */
  viewerPoint(p: [number, number, number]): [number, number, number] | null {
    const s = this.ctl.state;
    if (!s || !this.ctl.base || !this.ctl.head) return null;
    return baseToViewer(p, this.ctl.base.originShift, this.ctl.head.originShift, s.session.diff.offset);
  }
}

export type { UndoEntry, BulkRule };
