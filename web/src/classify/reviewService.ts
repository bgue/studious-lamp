// The review side of the classify service: pending changes, commits, reversals, the stored log and the committed results. No DOM.
//
// A confirmation or a correction first goes into the pending set (visible, undone item by item). "Commit" turns the pending set into one
// immutable commit record in the log; the log is stored per model fingerprint (IndexedDB, else localStorage, else this session only).
// The effective state of the log is the committed results of the store: they win over every run, and a run only tells whether the model
// now disagrees.

import type { KeyValueStorage } from './cache';
import { committedResult, createReviewPersistence, HUMAN_FACET_SOURCE, isCommittedSource, modelFingerprint, ReviewLog, REVIEW_LOG_SCHEMA, REVIEWER_STORAGE_KEY, sameState, schemaEditionOf, stateOf, UNSURE_CONFIDENCE } from './reviewLog';
import type { EffectiveFacet, ImportOutcome, ReviewAction, ReviewChange, ReviewCommit, ReviewFacetChange, ReviewPersistence, ReviewState, ReviewVia } from './reviewLog';
import type { FacetLike } from './facetWalk';
import type { FacetRef } from './reviewWalk';
import { makeManual } from './results';
import type { ManualPartial } from './results';
import type { ResultStore } from './results';
import { SkipList } from './reviewWalk';
import type { ClassificationSchema, ClassifyResult } from './types';
import type { SceneModel } from '../types';

/** What the review needs from the service. */
export interface ReviewHost {
  schema(): ClassificationSchema;
  schemaHash(): string;
  model(): SceneModel | null;
  modelName(): string;
  store(): ResultStore;
  /** Write results into the model properties, and remove them for the ids (when the setting is on). */
  write(results: readonly ClassifyResult[], clearIds: readonly string[]): void;
  emit(): void;
  /** The facet result of an element (facets and concrete sets), or undefined. Absent in a host without facets. */
  facetResult?(globalId: string, ref: FacetRef): FacetLike | undefined;
  /** The code list of a facet, or null when it has none (the measured concrete sets). */
  facetCodes?(ref: FacetRef): ReadonlyArray<{ code: string; label: string }> | null;
  /** The decided facet values of the log changed: put them into the facet results (and the model properties). */
  applyFacets?(effective: ReadonlyMap<string, EffectiveFacet>): void;
}

/** The session's review activity that the log does not hold (for the manifest): skips and undone pending items. */
export interface ReviewActivity {
  skipped: number;
  undone: number;
}

export interface PendingChange extends ReviewChange {
  /** The walk item that this change belongs to (undone together). */
  item: string;
}

export interface PendingFacetChange extends ReviewFacetChange {
  item: string;
}

export class ReviewManager {
  log: ReviewLog | null = null;
  private pendingMap = new Map<string, PendingChange>();
  /** Pending facet changes by `GlobalId|Facet`. */
  private pendingFacetMap = new Map<string, PendingFacetChange>();
  /** The item keys of the pending changes in the order they were made (the last one is what "Undo last" takes back). */
  private pendingOrder: string[] = [];
  /** What the log does not hold: skips and undone items of this session (counted for the manifest). */
  readonly activity: ReviewActivity = { skipped: 0, undone: 0 };
  /** The decided facets of the log now (key `GlobalId|Facet`). */
  private facetEff: ReadonlyMap<string, EffectiveFacet> = new Map();
  /** The elements that the reviewer skipped in this session. Not a change: it is not committed, not in the log and not stored. */
  readonly skips = new SkipList();
  /** Resolves when the stored log of the current model is loaded and applied. */
  ready: Promise<void> = Promise.resolve();
  /** Where the last save went, or the reason it failed. */
  storage: { where: 'indexeddb' | 'localstorage' | 'session' | 'none'; error: string } = { where: 'none', error: '' };
  private token = 0;
  private reviewerName = '';
  private persistence: ReviewPersistence;

  constructor(private readonly host: ReviewHost, private readonly local: KeyValueStorage | null, persistence?: ReviewPersistence) {
    this.persistence = persistence ?? createReviewPersistence({ local });
    try {
      this.reviewerName = local?.getItem(REVIEWER_STORAGE_KEY) ?? '';
    } catch {
      this.reviewerName = '';
    }
  }

  // ------------------------------------------------------------ reviewer

  /** The name or initials of the reviewer, kept on this device only. It is not a setting: it is in no params, link, view or preset. */
  reviewer(): string {
    return this.reviewerName;
  }
  setReviewer(name: string): void {
    this.reviewerName = name.trim().slice(0, 80);
    try {
      if (this.reviewerName) this.local?.setItem(REVIEWER_STORAGE_KEY, this.reviewerName);
      else this.local?.removeItem(REVIEWER_STORAGE_KEY);
    } catch {
      /* the name is kept for this session */
    }
    this.host.emit();
  }

  // ------------------------------------------------------------ the log of the model on screen

  fingerprint(): string {
    const m = this.host.model();
    return m ? modelFingerprint(m.elements.map((e) => e.globalId), this.host.schemaHash()) : '';
  }

  /** A model or a schema changed: start an empty log for the new fingerprint, load the stored one, apply it. Pending changes are dropped. */
  reload(): void {
    const m = this.host.model();
    this.pendingMap.clear();
    this.pendingFacetMap.clear();
    this.pendingOrder = [];
    this.skips.clear();
    this.facetEff = new Map();
    const token = ++this.token;
    if (!m) {
      this.log = null;
      this.ready = Promise.resolve();
      return;
    }
    const fp = this.fingerprint();
    const info = { modelName: this.host.modelName(), modelFingerprint: fp, schemaEdition: schemaEditionOf(this.host.schema()) };
    this.log = new ReviewLog(info);
    this.storage = { where: 'none', error: '' };
    this.ready = this.persistence.load(fp).then(
      (commits) => {
        if (token !== this.token) return;
        this.log = new ReviewLog(info, commits);
        this.apply();
      },
      () => undefined,
    );
  }

  /** Put the committed results of the log into the store (and the model properties). */
  apply(): void {
    const log = this.log;
    const store = this.host.store();
    const schema = this.host.schema();
    const before = new Set(store.committed.keys());
    const next = new Map<string, ClassifyResult>();
    if (log) {
      for (const [gid, e] of log.effective()) {
        try {
          next.set(gid, committedResult(schema, e, store.get(gid)));
        } catch {
          /* a code that the schema does not have: the element has no committed result */
        }
      }
    }
    this.facetEff = log ? log.effectiveFacets() : new Map();
    this.host.applyFacets?.(this.facetEff);
    store.setCommitted(next);
    const gone = [...before].filter((id) => !next.has(id));
    const back = gone.map((id) => store.get(id)).filter((r): r is ClassifyResult => !!r);
    this.host.write([...next.values(), ...back], gone.filter((id) => !store.get(id)));
    this.host.emit();
  }

  private async persist(): Promise<void> {
    const log = this.log;
    if (!log) return;
    try {
      const r = await this.persistence.save(log.fingerprint, log.info, log.commits);
      this.storage = { where: r.where, error: '' };
    } catch (e) {
      this.storage = { where: 'session', error: e instanceof Error ? e.message : String(e) };
    }
    this.host.emit();
  }

  // ------------------------------------------------------------ pending

  pending(): PendingChange[] {
    return [...this.pendingMap.values()];
  }
  pendingFor(globalId: string): PendingChange | undefined {
    return this.pendingMap.get(globalId);
  }

  pendingFacets(): PendingFacetChange[] {
    return [...this.pendingFacetMap.values()];
  }
  pendingFacetFor(globalId: string, facet: string): PendingFacetChange | undefined {
    return this.pendingFacetMap.get(`${globalId}|${facet}`);
  }
  /** Every pending item (classification and facets): the count the Pending tab and the Commit button show. */
  pendingCount(): number {
    return this.pendingMap.size + this.pendingFacetMap.size;
  }
  /** The decided facets of the log now, by `GlobalId|Facet`. */
  facetEffective(): ReadonlyMap<string, EffectiveFacet> {
    return this.facetEff;
  }
  /** A facet of an element: its pending decision, or the committed one. */
  facetDecision(globalId: string, facet: string): 'confirmed' | 'corrected' | null {
    const key = `${globalId}|${facet}`;
    const p = this.pendingFacetMap.get(key);
    if (p) return p.action === 'correct' ? 'corrected' : 'confirmed';
    const e = this.facetEff.get(key);
    return e ? (e.change.action === 'correct' ? 'corrected' : 'confirmed') : null;
  }

  /** The state that a result has now, or its pending state. */
  decision(globalId: string): 'confirmed' | 'corrected' | null {
    const p = this.pendingMap.get(globalId);
    if (p) return p.after.source === 'corrected' ? 'corrected' : 'confirmed';
    const s = this.host.store().get(globalId);
    return s && isCommittedSource(s.source) ? (s.source as 'confirmed' | 'corrected') : null;
  }

  /**
   * Put confirmations or corrections of elements into the pending set. `confirm` keeps the codes that the element has now; `correct`
   * takes `codes`. A confirmation of an element that is committed with these codes already is left out. Throws a plain Error for a code
   * that is not in the schema.
   */
  propose(globalIds: readonly string[], o: { action: ReviewAction; codes?: ManualPartial; item: string; comment?: string; unsure?: boolean; via?: ReviewVia }): PendingChange[] {
    const store = this.host.store();
    const schema = this.host.schema();
    const made: PendingChange[] = [];
    const unsure = o.unsure === true;
    const confidence = unsure ? UNSURE_CONFIDENCE : 1;
    for (const gid of globalIds) {
      const cur = store.get(gid);
      if (!cur) continue;
      const before = stateOf(cur);
      let after: ReviewState;
      if (o.action === 'confirm') {
        after = { discipline: before.discipline, subDiscipline: before.subDiscipline, division: before.division, source: 'confirmed', confidence };
      } else {
        const r = makeManual(schema, gid, o.codes ?? {}, cur);
        after = { discipline: r.discipline.code, subDiscipline: r.subDiscipline?.code ?? null, division: r.masterformat?.division ?? null, source: 'corrected', confidence };
        if (after.discipline === before.discipline && after.subDiscipline === before.subDiscipline && after.division === before.division) after = { ...after, source: 'confirmed' };
      }
      // The same codes again leave a committed element alone, unless the sureness changes: a sure confirmation replaces an unsure one.
      if (isCommittedSource(before.source) && sameState(before, after) && (cur.unsure === true) === unsure) {
        this.pendingMap.delete(gid);
        this.skips.remove([gid]);
        continue;
      }
      const ch: PendingChange = { globalId: gid, before, after, action: after.source === 'corrected' ? 'correct' : 'confirm', item: o.item, ...(o.comment ? { comment: o.comment } : {}), ...(unsure ? { unsure: true as const } : {}), ...(o.via && after.source === 'corrected' ? { via: o.via } : {}) };
      this.pendingMap.set(gid, ch);
      this.skips.remove([gid]); // a decision settles a skip
      made.push(ch);
    }
    if (made.length) this.noteItem(o.item);
    this.host.emit();
    return made;
  }

  private noteItem(item: string): void {
    this.pendingOrder = this.pendingOrder.filter((k) => k !== item);
    this.pendingOrder.push(item);
  }

  /**
   * Put the confirmation or correction of one facet of one element into the pending set. `confirm` keeps the code it has; `correct` takes
   * `code`, which must be in the facet's code list. The result becomes source `human` when the change is committed. Throws a plain Error
   * for a code that is not in the list, or for a facet that has no result. Returns null when nothing changes (the same human decision again).
   */
  proposeFacet(ref: FacetRef, globalId: string, o: { action: ReviewAction; code?: string; item: string; comment?: string; unsure?: boolean; via?: ReviewVia }): PendingFacetChange | null {
    const cur = this.host.facetResult?.(globalId, ref);
    if (!cur) throw new Error(`The element has no ${ref.id} result.`);
    const codes = this.host.facetCodes?.(ref) ?? null;
    let code = cur.code;
    if (o.action === 'correct') {
      if (!codes) throw new Error(`${ref.id} has no code list to pick from: confirm it or skip it.`);
      const pick = o.code ?? '';
      if (!codes.some((c) => c.code === pick)) throw new Error(`"${pick}" is not a ${ref.id} code. Use one of: ${codes.map((c) => c.code).join(', ')}.`);
      code = pick;
    }
    const unsure = o.unsure === true;
    const action: ReviewAction = code === cur.code ? 'confirm' : 'correct';
    const key = `${globalId}|${ref.id}`;
    if (cur.source === HUMAN_FACET_SOURCE && cur.code === code && (cur.confidence < 1) === unsure) {
      this.pendingFacetMap.delete(key);
      this.skips.remove([globalId]);
      return null;
    }
    const ch: PendingFacetChange = {
      globalId, facet: ref.id, item: o.item, action,
      before: { code: cur.code, source: cur.source, confidence: cur.confidence },
      after: { code, source: HUMAN_FACET_SOURCE, confidence: unsure ? UNSURE_CONFIDENCE : 1 },
      ...(o.comment ? { comment: o.comment } : {}), ...(unsure ? { unsure: true as const } : {}), ...(o.via && action === 'correct' ? { via: o.via } : {}),
    };
    this.pendingFacetMap.set(key, ch);
    this.skips.remove([globalId]);
    this.noteItem(o.item);
    this.host.emit();
    return ch;
  }

  /** The item key that "Undo last" takes back: the newest pending item (classification or facet). */
  lastPendingItem(): string | null {
    return this.pendingOrder[this.pendingOrder.length - 1] ?? null;
  }

  /** Take back the pending changes of one walk item (or of one element). */
  undoPending(itemOrGlobalId: string): number {
    let n = 0;
    for (const [gid, p] of [...this.pendingMap]) if (p.item === itemOrGlobalId || gid === itemOrGlobalId) { this.pendingMap.delete(gid); n++; }
    for (const [k, p] of [...this.pendingFacetMap]) if (p.item === itemOrGlobalId || p.globalId === itemOrGlobalId) { this.pendingFacetMap.delete(k); n++; }
    if (n) {
      this.pendingOrder = this.pendingOrder.filter((k) => k !== itemOrGlobalId);
      this.activity.undone += 1;
      this.host.emit();
    }
    return n;
  }
  discardPending(): void {
    if (this.pendingCount()) this.activity.undone += new Set([...this.pendingMap.values(), ...this.pendingFacetMap.values()].map((p) => p.item)).size;
    this.pendingMap.clear();
    this.pendingFacetMap.clear();
    this.pendingOrder = [];
    this.host.emit();
  }

  // ------------------------------------------------------------ commit, revert

  /** Write the pending changes as one commit. Throws a plain Error when there is no reviewer, no log or nothing pending. */
  commit(note = ''): ReviewCommit {
    const log = this.log;
    if (!log) throw new Error('Load a model first.');
    const changes = this.pending();
    const facetChanges = this.pendingFacets();
    if (changes.length === 0 && facetChanges.length === 0) throw new Error('There are no pending changes to commit.');
    const c = log.commit({ author: this.reviewerName, note, changes: changes.map(({ item: _i, ...ch }) => ch), facetChanges: facetChanges.map(({ item: _i, ...ch }) => ch) });
    this.pendingMap.clear();
    this.pendingFacetMap.clear();
    this.pendingOrder = [];
    this.apply();
    void this.persist();
    return c;
  }

  /** Append a commit that reverses an earlier one. Returns it and the elements that were left alone. */
  revert(commitId: string, note?: string): { commit: ReviewCommit; skipped: string[] } {
    const log = this.log;
    if (!log) throw new Error('Load a model first.');
    const r = log.revert(commitId, { author: this.reviewerName, ...(note ? { note } : {}) });
    this.apply();
    void this.persist();
    return r;
  }

  history(): ReviewCommit[] {
    return [...(this.log?.commits ?? [])].reverse();
  }

  // ------------------------------------------------------------ export, import

  exportLog(): string {
    if (!this.log) throw new Error('Load a model first.');
    return this.log.exportJson();
  }

  importLog(text: unknown): ImportOutcome {
    if (!this.log) return { ok: false, error: 'Load a model first.', added: [], duplicates: [] };
    const r = this.log.importDoc(text);
    if (r.ok && r.added.length) {
      this.apply();
      void this.persist();
    }
    return r;
  }

  /**
   * Add commits carried over from another model's log (the revision walk). They carry the head's fingerprint, so `importDoc` accepts
   * them; commits whose id is in the log already are skipped, so carrying twice adds nothing. Waits for the stored log first.
   */
  async appendCarried(commits: readonly ReviewCommit[]): Promise<ImportOutcome> {
    await this.ready;
    const log = this.log;
    if (!log) return { ok: false, error: 'Load a model first.', added: [], duplicates: [] };
    const r = log.importDoc({ schema: REVIEW_LOG_SCHEMA, ...log.info, exportedAt: new Date().toISOString(), commits });
    if (r.ok && r.added.length) {
      this.apply();
      await this.persist();
    }
    return r;
  }

  /** The stored commits of another model fingerprint (the base of a revision). Empty when there are none or storage fails. */
  async commitsOf(fingerprint: string): Promise<ReviewCommit[]> {
    if (this.log && this.log.fingerprint === fingerprint) return [...this.log.commits];
    try {
      return [...(await this.persistence.load(fingerprint))];
    } catch {
      return [];
    }
  }

  /** Elements that are committed and where the latest run says something else: id -> the run's result. */
  disagreements(): ReadonlyMap<string, ClassifyResult> {
    return this.host.store().disagreements;
  }
}
