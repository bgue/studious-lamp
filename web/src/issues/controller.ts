// Issues: the controller that joins the two controllers. BCF is the container (issues: status, priority, assignee, comments,
// viewpoints) and the markup drawing engine is the drawing layer (sketches: a view, drawings and a note). An issue's
// viewpoints ARE sketches, linked by id (link.ts). This class
//   - raises a sketch as an issue (new, or added to an existing one) and keeps the viewpoint's drawing in step with the sketch,
//   - makes sketches of the viewpoints of an opened BCF file, linked to their issue,
//   - converts legacy sketch comments and status to issues (the migration banner),
//   - guards removing a sketch that belongs to an issue, and
//   - holds the state of the Issues panel (segment, open detail, filter) and the counts of the status bar.
// DOM lives in ui.ts and the plugin in src/plugins/issues.ts. Docs: docs-features/issues.md.

import type { ViewerApp } from '../app';
import type { BcfController } from '../bcf/controller';
import type { MarkupController } from '../markup/controller';
import { hasLegacyReview } from '../markup/model';
import type { MarkupSet } from '../markup/model';
import { newGuid, nowIso } from '../bcf/model';
import type { BcfAnnotation, BcfTopic, BcfViewpointRef } from '../bcf/model';
import { addMarkup } from '../markup/model';
import { annotationToMarkup, clearLegacyReview, issueOfSketch, legacyIssueOf, legacySketches, linkSketch, reconcileLinks, sketchFromViewpoint, sketchesOfIssue, syncViewpoint, unlinkSketch } from './link';
import type { IssueRef, LegacyIssue } from './link';
import { searchIssues } from './search';
import type { IssueHit } from './search';

export type Segment = 'issues' | 'sketches';
export type Detail = { kind: 'issue' | 'sketch'; id: string } | null;

/** Statuses that count as closed: the status bar counts the others as open. */
const CLOSED_RE = /^(resolved|closed|done|solved|completed|rejected|cancel+ed|fixed|verified)$/i;
export function isOpenStatus(status: string): boolean {
  return !CLOSED_RE.test(status.trim());
}

/** The status chips of the issue list. */
export type StatusFilter = 'all' | 'open' | 'closed';

export class IssuesController {
  segment: Segment = 'issues';
  detail: Detail = null;
  statusFilter: StatusFilter = 'all';
  query = '';
  /** A sketch that belongs to an issue is about to be removed: the panel asks first. */
  confirmRemove: string | null = null;
  /** Whether the panel is up (the plugin sets it): status text and the phone sheet follow it. */
  panelOpen = false;
  /** The result of the last migration, for the panel and scripts. */
  lastMigration: { issues: number; failed: number } | null = null;
  private readonly listeners = new Set<() => void>();
  private syncing = false;
  private queued = false;
  private adopting = false;
  private lastTopicCount = 0;
  private lastApplied = '';
  /** The sketch state each linked viewpoint was last projected from: an unchanged sketch leaves an imported drawing as it was read. */
  private readonly synced = new WeakMap<BcfViewpointRef, string>();
  private migrating = false;
  /** A sketch is being raised: the new issue does not take over the panel (the sketch detail shows the link). */
  private raising = false;

  constructor(readonly app: ViewerApp, readonly markup: MarkupController, readonly bcf: BcfController) {
    markup.raise = (id, o) => this.raise(id, o);
    markup.viewpointRestore = (set) => this.restoreFromViewpoint(set);
    markup.companion = () => {
      const s = this.sketchOfApplied();
      return s && markup.visibleSets().some((x) => x.set.id === s.id) ? s : null;
    };
    bcf.beforeExport = () => this.syncAll();
    bcf.linked = {
      add: (ref, a) => this.annotationAdded(ref, a),
      update: (ref, guid, patch) => this.annotationUpdated(ref, guid, patch),
      remove: (ref, guid) => this.annotationRemoved(ref, guid),
    };
    markup.onRemoved((set) => this.sketchRemoved(set));
    markup.onViewUpdated((set) => this.viewUpdated(set));
    markup.onChange(() => {
      this.scheduleSync();
      this.emit();
    });
    bcf.onChange(() => {
      this.afterBcfChange();
      this.emit();
    });
  }

  onChange(cb: () => void): () => void {
    this.listeners.add(cb);
    return () => this.listeners.delete(cb);
  }
  emit(): void {
    for (const l of this.listeners) l();
  }

  // ---------------------------------------------------------------- links

  get topics(): BcfTopic[] {
    return this.bcf.topics;
  }
  get sets(): MarkupSet[] {
    return this.markup.sets;
  }
  issueOf(setId: string): IssueRef | null {
    return issueOfSketch(this.topics, setId);
  }
  sketchesOf(topic: BcfTopic): MarkupSet[] {
    return sketchesOfIssue(topic, this.sets);
  }
  /** The viewpoint of an issue that a sketch is, with its sketch. */
  viewpointSketch(ref: BcfViewpointRef): MarkupSet | undefined {
    return ref.sketchId ? this.sets.find((s) => s.id === ref.sketchId) : undefined;
  }

  // ---------------------------------------------------------------- keeping the issue in step with the sketch

  /** Rebuild the drawing of every linked viewpoint from its sketch. Returns how many changed. */
  syncAll(): number {
    if (this.syncing) return 0;
    this.syncing = true;
    let n = 0;
    try {
      const shift = this.bcf.shift;
      for (const t of this.topics) {
        for (const v of t.viewpoints) {
          if (!v.sketchId) continue;
          const s = this.sets.find((x) => x.id === v.sketchId);
          if (!s) continue;
          const sig = JSON.stringify([s.markups, s.camera]);
          if (this.synced.get(v) === sig) continue;
          this.synced.set(v, sig);
          if (syncViewpoint(s, v, shift)) {
            n++;
            this.bcf.touch(t);
          }
        }
      }
    } finally {
      this.syncing = false;
    }
    return n;
  }

  private scheduleSync(): void {
    if (this.queued) return;
    this.queued = true;
    queueMicrotask(() => {
      this.queued = false;
      this.syncAll();
    });
  }

  /** Update view on a sketch: the issue viewpoint is captured again from the same live view, so both stay one. */
  private viewUpdated(set: MarkupSet): void {
    const ref = this.issueOf(set.id);
    if (!ref) return;
    this.bcf.recaptureViewpoint(ref.topic.guid, ref.viewpoint.guid);
    this.syncAll();
  }

  private sketchRemoved(set: MarkupSet): void {
    const ref = issueOfSketch(this.topics, set.id);
    unlinkSketch(this.topics, [set], set.id);
    if (ref) this.bcf.touch(ref.topic);
    if (this.detail?.kind === 'sketch' && this.detail.id === set.id) this.detail = null;
    if (this.confirmRemove === set.id) this.confirmRemove = null;
  }

  /** Apply the imported viewpoint of an issue for a sketch made from it. */
  private restoreFromViewpoint(set: MarkupSet): boolean {
    const ref = set.issue;
    if (!ref) return false;
    const r = this.bcf.applyViewpoint(ref.topic, ref.viewpoint);
    return r.ok;
  }

  // ---------------------------------------------------------------- annotation calls on a linked viewpoint go through the sketch

  private sketchOfRef(ref: BcfViewpointRef): MarkupSet | undefined {
    return ref.sketchId ? this.sets.find((s) => s.id === ref.sketchId) : undefined;
  }

  private annotationAdded(ref: BcfViewpointRef, a: BcfAnnotation): boolean {
    const set = this.sketchOfRef(ref);
    if (!set) return false;
    const m = annotationToMarkup(a, Math.max(set.nextNumber, 1), a.author || this.markup.author.trim() || 'unknown');
    if (!m) return false;
    this.markup.record(set);
    addMarkup(set, m);
    this.markup.emit();
    this.syncAll();
    return true;
  }

  private annotationUpdated(ref: BcfViewpointRef, guid: string, patch: { text?: string; offset?: [number, number] }): boolean {
    const set = this.sketchOfRef(ref);
    const m = set?.markups.find((x) => x.id === guid);
    if (!set || !m) return false;
    this.markup.record(set);
    if (patch.text !== undefined) m.text = patch.text.startsWith(`${m.number}. `) ? patch.text.slice(String(m.number).length + 2) : patch.text === `${m.number}.` ? '' : patch.text;
    if (patch.offset) m.offset = [patch.offset[0], patch.offset[1]];
    set.updated = nowIso();
    this.markup.emit();
    this.syncAll();
    return true;
  }

  private annotationRemoved(ref: BcfViewpointRef, guid: string): boolean {
    const set = this.sketchOfRef(ref);
    if (!set || !set.markups.some((x) => x.id === guid)) return false;
    this.markup.remove(guid);
    this.syncAll();
    return true;
  }

  // ---------------------------------------------------------------- BCF changes: reconcile links, sketches of imported viewpoints

  private afterBcfChange(): void {
    // A new issue (the New issue dialog, a script) opens in the detail.
    const n = this.topics.length;
    if (!this.raising && n === this.lastTopicCount + 1 && this.bcf.selectedTopic && this.bcf.topic(this.bcf.selectedTopic)) {
      this.segment = 'issues';
      this.detail = { kind: 'issue', id: this.bcf.selectedTopic };
    }
    this.lastTopicCount = n;
    const ap = this.bcf.applied?.viewpoint ?? '';
    if (ap !== this.lastApplied) {
      this.lastApplied = ap;
      this.markup.emit(true); // the sketch of the applied viewpoint draws next to the active one (markup.companion)
    }
    if (!this.adopting) {
      this.adopting = true;
      try {
        reconcileLinks(this.topics, this.sets);
        this.adopt();
      } finally {
        this.adopting = false;
      }
    }
  }

  private sketchOfApplied(): MarkupSet | undefined {
    const ap = this.bcf.applied;
    const t = ap ? this.bcf.topic(ap.topic) : undefined;
    const v = t?.viewpoints.find((x) => x.guid === ap?.viewpoint);
    return v ? this.viewpointSketch(v) : undefined;
  }

  /**
   * Make a sketch of every viewpoint that carries annotations and has no sketch (an opened BCF file, or annotations added
   * through the scripting API), linked to its issue. A viewpoint with a drawing that cannot become a sketch keeps it as it is.
   */
  adopt(): number {
    let n = 0;
    const shift = this.bcf.shift;
    for (const t of this.topics) {
      for (const v of t.viewpoints) {
        if (v.sketchId || !v.annotations?.length) continue;
        const cam = this.bcf.shapeView(v);
        if (!cam) continue;
        const set = sketchFromViewpoint(t, v, { author: t.creationAuthor || 'unknown', shift, camera: cam, model: t.model });
        if (!set) continue;
        this.sets.push(set);
        this.synced.set(v, JSON.stringify([set.markups, set.camera])); // the file's drawing stays as read until the sketch changes
        n++;
      }
    }
    if (n) this.markup.emit();
    return n;
  }

  // ---------------------------------------------------------------- raise as issue

  /**
   * Raise a sketch as an issue: a new one (title and note of the sketch, its view as the viewpoint) or, with `topic`, one more
   * viewpoint of an existing issue. The viewpoint links to the sketch by id: it is not a copy. Returns the issue guid.
   */
  async raise(setId: string, o: { topic?: string; legacy?: LegacyIssue } = {}): Promise<string> {
    const set = this.markup.get(setId);
    if (!set) throw new Error(`No sketch ${setId}`);
    if (!this.markup.loaded) throw new Error('No model loaded');
    const have = this.issueOf(setId);
    if (have) throw new Error(`"${set.title}" already belongs to the issue "${have.topic.title}". Open that issue instead.`);
    this.raising = true;
    let topic: BcfTopic | undefined;
    try {
      this.markup.restore(set.id, false);
      await this.markup.settleView();
      // A sketch that still carries comments or a status moves them to the issue (nothing is left stranded on the sketch).
      const legacy: LegacyIssue | undefined = o.legacy ?? (hasLegacyReview(set) ? legacyIssueOf(set) : undefined);
      let ref: BcfViewpointRef;
      const author = this.markup.author.trim() || 'unknown';
      if (o.topic) {
        topic = this.bcf.topic(o.topic);
        if (!topic) throw new Error(`No issue ${o.topic}`);
        ref = this.bcf.addViewpoint(topic.guid);
      } else {
        const l = legacy;
        topic = this.bcf.createTopic({
          title: l?.title ?? set.title,
          description: l?.description ?? set.note ?? '',
          status: l?.status ?? 'Open',
          author,
          ...(l?.assignedTo ? { assignedTo: l.assignedTo } : {}),
          ...(l?.dueDate ? { dueDate: l.dueDate } : {}),
        });
        ref = topic.viewpoints[0]!;
        if (!ref) throw new Error('The view could not be captured');
      }
      const r = linkSketch(this.topics, this.sets, set.id, topic.guid, ref.guid);
      if (!r.ok) throw new Error(r.error);
      if (legacy) {
        for (const c of legacy.comments) topic.comments.push({ guid: newGuid(), date: c.date, author: c.author, text: c.text });
        if (legacy.comments.length) topic.modifiedDate = nowIso();
        clearLegacyReview(set);
      }
    } finally {
      this.raising = false;
    }
    this.syncAll();
    this.bcf.touch(topic);
    this.bcf.selectedTopic = topic.guid;
    this.markup.setStatus(`Sketch "${set.title}" raised as the issue "${topic.title}"`);
    this.emit();
    return topic.guid;
  }

  // ---------------------------------------------------------------- legacy comments and status

  /** The sketches of the loaded model that still carry comments, a resolved status, an assignee or a due date. */
  legacy(): MarkupSet[] {
    return legacySketches(this.markup.visibleSets().map((x) => x.set), hasLegacyReview);
  }

  /**
   * Convert each legacy sketch to an issue that links to the sketch, moving its comments, status, assignee and due date.
   * Returns how many were converted. Nothing is left out: a sketch that cannot be converted keeps its data.
   */
  async migrateLegacy(): Promise<{ issues: number; failed: number }> {
    if (this.migrating) return { issues: 0, failed: 0 };
    this.migrating = true;
    let issues = 0;
    let failed = 0;
    try {
      for (const s of this.legacy()) {
        try {
          await this.raise(s.id, { legacy: legacyIssueOf(s) });
          issues++;
        } catch (e) {
          failed++;
          this.markup.setStatus(`"${s.title}" could not be raised: ${e instanceof Error ? e.message : String(e)}`);
        }
      }
    } finally {
      this.migrating = false;
    }
    this.lastMigration = { issues, failed };
    if (issues) this.markup.setStatus(`${issues} sketch${issues === 1 ? '' : 'es'} raised as issues${failed ? `; ${failed} could not be` : ''}`);
    this.emit();
    return this.lastMigration;
  }

  // ---------------------------------------------------------------- removing a sketch

  /** The issue a removal would cut a viewpoint of, or null when the sketch is loose. */
  removalNeedsConfirm(setId: string): IssueRef | null {
    return this.issueOf(setId);
  }

  /** Remove a sketch. One that belongs to an issue asks first: it returns `confirm` until called again with `confirmed`. */
  removeSketch(setId: string, confirmed = false): 'removed' | 'confirm' | 'none' {
    const set = this.markup.get(setId);
    if (!set) return 'none';
    if (this.issueOf(setId) && !confirmed) {
      this.confirmRemove = setId;
      this.emit();
      return 'confirm';
    }
    this.confirmRemove = null;
    this.markup.deleteSet(setId);
    return 'removed';
  }

  cancelRemove(): void {
    this.confirmRemove = null;
    this.emit();
  }

  // ---------------------------------------------------------------- issues of other models

  openOtherIssue(guid: string): boolean {
    const t = this.bcf.topic(guid);
    if (!t) return false;
    this.bcf.openOther(guid);
    for (const s of this.sketchesOf(t)) this.markup.openOther(s.id);
    return true;
  }
  moveIssueToModel(guid: string): boolean {
    const t = this.bcf.topic(guid);
    if (!t) return false;
    for (const s of this.sketchesOf(t)) this.markup.moveToModel(s.id);
    return this.bcf.moveToModel(guid);
  }
  deleteIssue(guid: string): boolean {
    const ok = this.bcf.deleteTopic(guid);
    if (this.detail?.kind === 'issue' && this.detail.id === guid) this.detail = null;
    return ok;
  }

  // ---------------------------------------------------------------- opening

  setSegment(s: Segment): void {
    if (this.segment === s) return;
    this.segment = s;
    this.detail = null;
    this.emit();
  }

  /** Open an issue in the detail and apply the view of its first sketch (else its first viewpoint). */
  openIssue(guid: string, o: { apply?: boolean } = {}): boolean {
    const t = this.bcf.topic(guid);
    if (!t) return false;
    this.segment = 'issues';
    this.detail = { kind: 'issue', id: guid };
    this.bcf.select(guid);
    if (o.apply !== false) {
      const vp = t.viewpoints.find((v) => v.data);
      if (vp) this.applyViewpoint(t, vp);
    }
    this.emit();
    return true;
  }

  /**
   * Apply a viewpoint of an issue the BCF way (camera, selection, hides, colours, clip planes; Clear viewpoint undoes it). Its
   * sketch becomes the active one: drawn, not yet edited. A viewpoint without data falls back to the view of its sketch.
   */
  applyViewpoint(t: BcfTopic, vp: BcfViewpointRef): boolean {
    const s = this.viewpointSketch(vp);
    const here = !!s && this.markup.visibleSets().some((x) => x.set.id === s.id);
    let ok = false;
    if (vp.data) ok = this.bcf.applyViewpoint(t.guid, vp.guid).ok;
    else if (s && here) {
      this.markup.restore(s.id, true);
      ok = true;
    }
    if (s && here) {
      this.markup.activeId = s.id;
      this.markup.selected = null;
    }
    this.markup.emit();
    return ok;
  }

  /** Open a sketch in the detail and bring its view back. */
  openSketch(id: string, o: { restore?: boolean } = {}): boolean {
    const s = this.markup.get(id);
    if (!s) return false;
    this.segment = 'sketches';
    this.detail = { kind: 'sketch', id };
    void this.markup.select(id, { restore: o.restore !== false });
    this.emit();
    return true;
  }

  /** Edit the drawing of a sketch: it becomes active and the drawing toolbar comes up. */
  editSketch(id: string): boolean {
    const s = this.markup.get(id);
    if (!s) return false;
    if (this.markup.activeId !== id) {
      this.markup.activeId = id;
      this.markup.selected = null;
    }
    this.markup.setEditing(true);
    this.emit();
    return this.markup.editing;
  }

  /** The sketch of a viewpoint, made (empty, linked) when it has none: the drawing layer of every viewpoint. Null when it cannot carry shapes. */
  sketchForViewpoint(topic: BcfTopic, vp: BcfViewpointRef): MarkupSet | null {
    const have = this.viewpointSketch(vp);
    if (have) return have;
    const cam = this.bcf.shapeView(vp);
    if (!cam) return null;
    const set = sketchFromViewpoint(topic, vp, { author: this.markup.author.trim() || topic.creationAuthor || 'unknown', shift: this.bcf.shift, camera: cam, empty: true });
    if (!set) return null;
    this.sets.push(set);
    this.synced.set(vp, JSON.stringify([set.markups, set.camera]));
    this.markup.emit();
    return set;
  }

  /** Edit the drawing of an issue viewpoint (its sketch, made when the viewpoint has none), applying the viewpoint first. */
  editViewpoint(topic: BcfTopic, vp: BcfViewpointRef): boolean {
    const s = this.sketchForViewpoint(topic, vp);
    if (!s) return false;
    this.applyViewpoint(topic, vp);
    return this.editSketch(s.id);
  }

  /** A new sketch from the current view, open in the detail and ready to draw on. */
  newSketch(title?: string): MarkupSet {
    const s = this.markup.newSet(title);
    this.segment = 'sketches';
    this.detail = { kind: 'sketch', id: s.id };
    this.markup.setEditing(true);
    this.emit();
    return s;
  }

  // ---------------------------------------------------------------- lists, counts, search

  /** The issues of the loaded model (and those opened from other models), filtered by the chips and the search field. */
  visibleIssues(): BcfTopic[] {
    const q = this.query.trim().toLowerCase();
    const terms = q.split(/\s+/).filter(Boolean);
    return this.bcf.currentTopics
      .filter((t) => {
        if (this.statusFilter === 'open' && !isOpenStatus(t.topicStatus)) return false;
        if (this.statusFilter === 'closed' && isOpenStatus(t.topicStatus)) return false;
        if (!terms.length) return true;
        const hay = [t.title, t.description ?? '', t.topicStatus, t.priority ?? '', t.assignedTo ?? '', t.labels.join(' '), ...t.comments.map((c) => c.text)].join(' ').toLowerCase();
        return terms.every((x) => hay.includes(x));
      })
      .sort((a, b) => (b.creationDate || '').localeCompare(a.creationDate || ''));
  }

  visibleSketches(): MarkupSet[] {
    const terms = this.query.trim().toLowerCase().split(/\s+/).filter(Boolean);
    return this.markup.visibleSets().map((x) => x.set).filter((s) => {
      if (!terms.length) return true;
      const hay = [s.title, s.note ?? ''].join(' ').toLowerCase();
      return terms.every((x) => hay.includes(x));
    });
  }

  /** How many issues of the loaded model are open (the status bar). */
  openCount(): number {
    return this.bcf.currentTopics.filter((t) => isOpenStatus(t.topicStatus)).length;
  }

  /** Search for the top-bar search: issues and sketches of the loaded model by title, note and comment text. */
  search(query: string): IssueHit[] {
    return searchIssues({ topics: this.bcf.currentTopics, sets: this.markup.visibleSets().map((x) => x.set) }, query);
  }

  /** The search row of one issue or sketch (for recents in the search bar), or null when it is gone or of another model. */
  hitOf(kind: 'issue' | 'sketch', id: string): IssueHit | null {
    if (kind === 'issue') {
      const t = this.bcf.currentTopics.find((x) => x.guid === id);
      return t ? { kind, id, title: t.title, sub: `Issue${t.topicStatus ? `, ${t.topicStatus}` : ''}`, field: 'title', positions: [], score: 50 } : null;
    }
    const s = this.markup.visibleSets().find((x) => x.set.id === id)?.set;
    return s ? { kind, id, title: s.title, sub: `Sketch, ${s.markups.length} drawing${s.markups.length === 1 ? '' : 's'}`, field: 'title', positions: [], score: 50 } : null;
  }

  /** Open a search hit: an issue applies its view, a sketch restores its own. */
  openHit(hit: Pick<IssueHit, 'kind' | 'id'>): boolean {
    return hit.kind === 'issue' ? this.openIssue(hit.id) : this.openSketch(hit.id);
  }

  onModel(): void {
    this.detail = null;
    this.confirmRemove = null;
    this.markup.setEditing(false);
    this.emit();
  }
}
