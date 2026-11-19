// The revision walk's brain (design 3): snapshot triggers, detection, the carry-over, the session, decisions, bulk rules, the report.
// No DOM here: the banner and the panel (plugins/revision.ts, plugins/revisionWalk.ts) read it and call it. Everything that decides is in
// the pure modules of this folder (diff, carry, walkOrder, bulk, session, report); this class only joins them to the live app and the
// classify service.

import type { ViewerApp } from '../app';
import { USER_MODELS } from '../app';
import type { ClassifyService } from '../classify/service';
import type { ReviewCommit } from '../classify/reviewLog';
import { loadedIdentity, identityKey } from '../markup/scope';
import type { ModelIdentity } from '../markup/model';
import { importIfc } from '../model/ifcImport';
import type { AttachmentHost } from './attachHost';
import { attachmentHost } from './attachHost';
import { captureSnapshot, ghostMeshesFor, liveGhostSource, storedGhostSource } from './capture';
import { selectBulk, shippedRules } from './bulk';
import type { BulkContext, BulkInfo } from './bulk';
import { carryRematchCommits, planCarry } from './carry';
import type { CarryInput, CarryPlan } from './carry';
import { createDiffWorker } from './diffRuntime';
import { runDiff } from './diffWorker';
import type { DiffWorkerLike } from './diffWorker';
import { decodeGhosts, encodeGhosts, GhostOverlay } from './ghost';
import type { GhostFrames, GhostTarget } from './ghost';
import { reportFileNames, revisionReportCsv, revisionSummaryMd } from './report';
import { codesKey, defaultClassification, newSession, SessionState } from './session';
import type { BulkToken } from './session';
import { classHistogramOf, guidSketch, stripFederation } from './snapshot';
import type { RevisionCandidate } from './snapshot';
import { openRevisionBackend, RevisionStore, SessionSaver } from './store';
import { revisionStatusMap } from './status';
import type { RevisionStatus } from './status';
import { buildRevisionWalk, filterEntries } from './walkOrder';
import type { RevisionItem } from './walkOrder';
import type { BulkRule, DiffEntry, ModelSnapshot, RevisionDecision, RevisionFilters, RevisionOrder, RevisionSession } from './types';
import { bcfController } from '../plugins/bcf';
import { markupController } from '../plugins/markup';
import type { ClassifyResult } from '../classify/types';

/** What the banner says. */
export type Banner =
  | { kind: 'candidate'; candidate: RevisionCandidate; message: string }
  | { kind: 'resume'; session: RevisionSession; message: string }
  | { kind: 'notice'; message: string; error?: boolean };

export interface UndoEntry {
  label: string;
  keys: string[];
  previous: Array<RevisionDecision | undefined>;
  previousSkipped: string[];
  bulk?: BulkToken;
}

type Edited = NonNullable<RevisionDecision['edited']>;

export interface DecideOptions {
  verdict: 'accepted' | 'rejected';
  classification?: RevisionDecision['classification'];
  edited?: Edited;
  unsure?: boolean;
  note?: string;
  attachments?: RevisionDecision['attachments'];
  reattachTo?: string;
}

const SNAPSHOT_DELAY_MS = 900;
export const REVISION_ITEM_PREFIX = 'rev:';
const sidelined = (d: RevisionDecision | undefined): boolean => !!d && d.commitId !== undefined;

export class RevisionController {
  store: RevisionStore | null = null;
  saver: SessionSaver | null = null;
  state: SessionState | null = null;
  base: ModelSnapshot | null = null;
  head: ModelSnapshot | null = null;
  plan: CarryPlan | null = null;
  banner: Banner | null = null;
  /** Text while something long runs ("Comparing..."); '' when idle. */
  busy = '';
  readonly ghost: GhostOverlay;
  bulkApplied: Array<{ id: string; label: string; count: number }> = [];
  undoStack: UndoEntry[] = [];
  /** Called when the session is ready to walk (the plugin opens the panel). */
  onWalkReady: (() => void) | null = null;
  /** Called when the model on screen changed and the walk must close. */
  onWalkClose: (() => void) | null = null;

  private readonly listeners = new Set<() => void>();
  private baseCommits: ReviewCommit[] = [];
  private token = 0;
  private snapTimer: ReturnType<typeof setTimeout> | null = null;
  private lastSnapKey = '';
  private snapBusy = false;
  private readonly notRevision = new Set<string>();
  private worker: (DiffWorkerLike & { terminate(): void }) | null = null;
  private headIx = new Map<string, number>();
  private baseIx = new Map<string, number>();
  private attach: AttachmentHost;
  private frames: GhostFrames = { baseShift: [0, 0, 0], headShift: [0, 0, 0], offset: [0, 0, 0] };
  readonly ready: Promise<void>;

  constructor(readonly app: ViewerApp, readonly svc: ClassifyService) {
    this.ghost = new GhostOverlay(app);
    this.attach = attachmentHost({
      topics: () => bcfController()?.currentTopics ?? [],
      sets: () => markupController()?.visibleSets().map((x) => x.set) ?? [],
      touched: ({ topics, sets }) => {
        const b = bcfController();
        for (const t of topics) b?.touch(t);
        if (sets.length) markupController()?.emit();
      },
      addComment: (g, text) => { bcfController()?.addComment(g, text); },
      setStatus: (g, status) => { bcfController()?.setTopicStatus(g, status); },
    });
    this.ready = openRevisionBackend().then((b) => {
      this.store = new RevisionStore(b);
      this.saver = new SessionSaver(this.store, () => this.state?.session ?? null);
    });
    svc.onChange(() => this.scheduleSnapshot());
  }

  // ------------------------------------------------------------ events

  onChange(cb: () => void): () => void {
    this.listeners.add(cb);
    return () => this.listeners.delete(cb);
  }
  private emit(): void {
    for (const l of this.listeners) l();
  }
  private setBusy(text: string): void {
    this.busy = text;
    this.emit();
  }
  private notice(message: string, error = false): void {
    this.banner = { kind: 'notice', message, ...(error ? { error: true } : {}) };
    this.emit();
  }

  get persistent(): boolean {
    return this.store?.persistent ?? false;
  }
  get walking(): boolean {
    return this.state !== null;
  }
  get diff(): RevisionSession['diff'] | null {
    return this.state?.session.diff ?? null;
  }

  // ------------------------------------------------------------ snapshots (3.1: when something is worth carrying)

  private snapKeyNow(): string {
    const svc = this.svc;
    const committed = svc.store.committed.size;
    return `${identityKey(loadedIdentity(this.app as never))}|${svc.store.size}|${committed}|${svc.review.history().length}`;
  }

  /** After a classify run ends or a review commit: the model has something to carry. Debounced. */
  private scheduleSnapshot(): void {
    if (this.snapTimer) clearTimeout(this.snapTimer);
    if (!this.svc.model || this.svc.running || this.svc.store.size === 0) return;
    this.snapTimer = setTimeout(() => { this.snapTimer = null; void this.snapshotNow(); }, SNAPSHOT_DELAY_MS);
  }

  /** Store a snapshot of the model on screen now (when it has results and nothing changed since the last one). Returns true when one was stored. */
  async snapshotNow(force = false): Promise<boolean> {
    const loaded = this.app.loaded;
    if (!loaded || this.snapBusy || this.busy || !this.svc.model || this.svc.running) return false;
    if (this.svc.store.size === 0) return false;
    const key = this.snapKeyNow();
    if (!force && key === this.lastSnapKey) return false;
    this.snapBusy = true;
    try {
      await this.ready;
      const snap = await captureSnapshot({
        name: this.app.modelName, loaded, results: (g) => this.svc.store.get(g), schemaHash: this.svc.schemaHashValue, reviewFingerprint: this.svc.review.fingerprint(),
      });
      if (!snap || this.app.loaded !== loaded) return false;
      await this.store!.saveSnapshot(snap);
      this.lastSnapKey = key;
      return true;
    } catch {
      return false;
    } finally {
      this.snapBusy = false;
    }
  }

  // ------------------------------------------------------------ a model arrived (3.1 detection, 4.2 resume)

  async onModel(): Promise<void> {
    const my = ++this.token;
    this.closeWalk();
    this.banner = null;
    this.base = this.head = this.plan = null;
    this.lastSnapKey = '';
    this.emit();
    await this.ready;
    if (my !== this.token || !this.app.loaded) return;
    const id = loadedIdentity(this.app as never);
    if (!id) return;
    const els = this.app.controller.model.elements;
    const resume = await this.store!.openSessionFor(id);
    if (my !== this.token) return;
    if (resume) {
      this.banner = { kind: 'resume', session: resume, message: `Resume revision review of ${resume.baseName} (${this.progressOf(resume)})` };
      this.emit();
      return;
    }
    const cands = (await this.store!.candidates({ identity: id, guidSketch: guidSketch(els.map((e) => e.globalId)), classHistogram: classHistogramOf(els.map((e) => e.ifcClass)) }))
      .filter((c) => !this.notRevision.has(`${c.key}>${identityKey(id)}`));
    if (my !== this.token) return;
    const first = cands[0];
    if (first) this.banner = { kind: 'candidate', candidate: first, message: first.message };
    this.emit();
  }

  private progressOf(s: RevisionSession): string {
    const st = new SessionState(s);
    const p = st.progress();
    return `${p.decided} of ${p.total} decided`;
  }

  /** The open review of the model on screen (a reload left it unfinished), or null. */
  async findResumable(): Promise<RevisionSession | null> {
    await this.ready;
    const id = loadedIdentity(this.app as never);
    return id && this.store ? this.store.openSessionFor(id) : null;
  }

  /** "Not a revision": this banner does not come back for this pair in this page. */
  dismissBanner(): void {
    const b = this.banner;
    const id = loadedIdentity(this.app as never);
    if (b?.kind === 'candidate' && id) this.notRevision.add(`${b.candidate.key}>${identityKey(id)}`);
    this.banner = null;
    this.emit();
  }

  /** Every stored snapshot, newest first, for "Compare with…". */
  async snapshots(): Promise<Array<{ key: string; name: string; savedAt: string; elements: number; reviewed: number }>> {
    await this.ready;
    const here = identityKey(loadedIdentity(this.app as never));
    return (await this.store!.records()).filter((r) => r.key !== here).sort((a, b) => (a.savedAt < b.savedAt ? 1 : -1)).map((r) => ({ key: r.key, name: r.name, savedAt: r.savedAt, elements: r.counts.elements, reviewed: r.counts.committed }));
  }

  // ------------------------------------------------------------ starting a walk

  private async captureHead(withResults: boolean, label = 'Reading the new model'): Promise<ModelSnapshot | null> {
    const loaded = this.app.loaded;
    if (!loaded) return null;
    return captureSnapshot({
      name: this.app.modelName, loaded, ...(withResults ? { results: (g: string) => this.svc.store.get(g) } : {}),
      schemaHash: this.svc.schemaHashValue, reviewFingerprint: this.svc.review.fingerprint(),
      onProgress: (d, t) => this.setBusy(`${label}: ${d} of ${t} elements`),
    });
  }

  private diffOptions(): { geometryAffectsClassification: boolean } {
    return { geometryAffectsClassification: !!(this.svc.imageSettings() || this.svc.geometrySettings()) };
  }

  /**
   * "Review changes": compare the stored snapshot `baseKey` with the model on screen, carry the unchanged decisions over, classify the
   * new and affected elements, and open the walk. Nothing is carried before this is called.
   */
  async start(baseKey: string, o: { base?: ModelSnapshot } = {}): Promise<RevisionSession | null> {
    if (this.busy) return null;
    const my = ++this.token;
    this.closeWalk();
    try {
      await this.ready;
      await this.svc.review.ready;
      this.setBusy('Loading the earlier model');
      const base = o.base ?? (await this.store!.loadSnapshot(baseKey));
      if (!base) { this.busy = ''; this.notice('That earlier model is no longer stored.', true); return null; }
      let head = await this.captureHead(false);
      if (!head || my !== this.token) { this.busy = ''; return null; }
      this.setBusy('Comparing the two models');
      this.worker ??= createDiffWorker();
      const diff = await runDiff(base, head, { options: this.diffOptions(), worker: this.worker, transfer: false });
      this.baseCommits = await this.svc.review.commitsOf(base.reviewFingerprint);
      const plan = planCarry({ base, head, diff, baseCommits: this.baseCommits });
      await this.applyCarry(plan);
      head = (await this.captureHead(true, 'Updating')) ?? head;
      if (my !== this.token) { this.busy = ''; return null; }
      const session = newSession({
        base: base.identity, head: head.identity, baseName: base.identity.name, diff,
        carried: plan.carry ? { commits: plan.commits.map((c) => c.id), results: plan.counts.copied } : null,
      });
      this.plan = plan;
      await this.open(session, base, head, { storeGhosts: true });
      if (!plan.carry) this.notice(plan.reason ?? 'Decisions cannot be carried over.');
      return session;
    } catch (e) {
      this.busy = '';
      this.notice(e instanceof Error ? e.message : String(e), true);
      return null;
    }
  }

  /** "Compare with an IFC file…": read a file without showing it, snapshot it (no decisions) and compare. */
  async startFromFile(file: File): Promise<RevisionSession | null> {
    if (this.busy) return null;
    try {
      this.setBusy(`Reading ${file.name}`);
      const res = await importIfc([{ name: file.name, data: await file.arrayBuffer() }], { edges: 'none', props: 'common' });
      const snap = await captureSnapshot({ name: `file:${file.name}`, loaded: res.loaded, schemaHash: this.svc.schemaHashValue, reviewFingerprint: '' });
      if (!snap) { this.busy = ''; return null; }
      await this.ready;
      await this.store!.saveSnapshot(snap);
      this.busy = '';
      return this.start(identityKey(snap.identity), { base: snap });
    } catch (e) {
      this.busy = '';
      this.notice(e instanceof Error ? e.message : String(e), true);
      return null;
    }
  }

  /** The base results and commits that carry into the head (idempotent: carrying twice adds nothing). */
  private async applyCarry(plan: CarryPlan): Promise<void> {
    if (plan.carry) {
      this.svc.adoptResults(plan.copy.map((c) => c.result));
      await this.svc.review.appendCarried(plan.commits);
    }
    const ids = plan.carry ? plan.reclassify.map((r) => r.head) : [];
    if (ids.length) {
      this.setBusy(`Classifying ${ids.length} new or affected element${ids.length === 1 ? '' : 's'}`);
      try { await this.svc.classify(ids); } catch (e) { this.notice(`Some elements could not be classified: ${e instanceof Error ? e.message : String(e)}`, true); }
    }
  }

  // ------------------------------------------------------------ resume

  async resume(session?: RevisionSession): Promise<boolean> {
    if (this.busy) return false;
    const my = ++this.token;
    try {
      await this.ready;
      await this.svc.review.ready;
      const s = session ?? (this.banner?.kind === 'resume' ? this.banner.session : null);
      if (!s) return false;
      this.setBusy('Resuming the revision review');
      const base = await this.store!.loadSnapshot(identityKey(s.base));
      if (!base) { this.busy = ''; this.notice('The earlier model of this review is no longer stored, so it cannot be resumed.', true); return false; }
      const head0 = await this.captureHead(false);
      if (!head0 || my !== this.token) { this.busy = ''; return false; }
      this.baseCommits = await this.svc.review.commitsOf(base.reviewFingerprint);
      const plan = planCarry({ base, head: head0, diff: s.diff, baseCommits: this.baseCommits });
      if (plan.carry) { this.svc.adoptResults(plan.copy.map((c) => c.result)); await this.svc.review.appendCarried(plan.commits); }
      const st = new SessionState(s);
      const need = st.needsClassify((g) => !!this.svc.store.get(g));
      if (need.length) {
        this.setBusy(`Classifying ${need.length} element${need.length === 1 ? '' : 's'}`);
        try { await this.svc.classify(need); } catch { /* the walk still opens */ }
      }
      const head = (await this.captureHead(true, 'Updating')) ?? head0;
      this.plan = plan;
      await this.open(s, base, head, { storeGhosts: false });
      return true;
    } catch (e) {
      this.busy = '';
      this.notice(e instanceof Error ? e.message : String(e), true);
      return false;
    }
  }

  /** Make a session the live one: indexes, ghost source, autosave, pending proposals, then open the panel. */
  private async open(session: RevisionSession, base: ModelSnapshot, head: ModelSnapshot, o: { storeGhosts: boolean }): Promise<void> {
    this.base = base;
    this.head = head;
    this.headIx = new Map(head.globalId.map((g, i) => [g, i]));
    this.baseIx = new Map(base.globalId.map((g, i) => [g, i]));
    this.state = new SessionState(session, { onChange: () => this.saver?.schedule() });
    this.undoStack = [];
    this.bulkApplied = [];
    this.frames = { baseShift: [...base.originShift] as GhostFrames['baseShift'], headShift: [...head.originShift] as GhostFrames['headShift'], offset: session.diff.offset };
    await this.setupGhosts(session, base, o.storeGhosts);
    // the pending set is session-only: propose again what was accepted and not yet committed
    for (const d of this.state.pendingProposals()) { const e = this.entry(d.key); if (e) this.applyToReview(e, d); }
    this.banner = null;
    this.busy = '';
    this.saver?.schedule();
    void this.saver?.flush();
    this.emit();
    this.onWalkReady?.();
  }

  private async setupGhosts(session: RevisionSession, base: ModelSnapshot, store: boolean): Promise<void> {
    const live = USER_MODELS.get(base.identity.name);
    const baseGids = session.diff.entries.filter((e) => e.base && (e.category === 'deleted' || e.category === 'rematched' || e.flags.includes('geometry') || e.flags.includes('placement'))).map((e) => e.base!);
    if (live && live.model.elements.length === base.globalId.length) {
      const src = liveGhostSource(live, base);
      this.ghost.setSource(src, this.frames);
      if (store && this.store) {
        try { await this.store.backend.putGhosts(session.key, new Blob([encodeGhosts(ghostMeshesFor(src, baseGids)).data as BlobPart])); } catch { /* boxes then */ }
      }
      return;
    }
    let meshes: ReturnType<typeof decodeGhosts> = [];
    try { const b = await this.store?.backend.getGhosts(session.key); if (b) meshes = decodeGhosts(await b.arrayBuffer()); } catch { /* boxes */ }
    this.ghost.setSource(storedGhostSource(meshes, base), this.frames);
  }

  closeWalk(): void {
    this.onWalkClose?.();
    this.ghost.hide();
    if (this.state) { void this.saver?.flush(); }
    this.state = null;
    this.undoStack = [];
    this.emit();
  }

  // ------------------------------------------------------------ reading the walk

  entry(key: string): DiffEntry | undefined {
    return this.state?.session.diff.entries.find((e) => e.key === key);
  }
  baseIndexOf(e: DiffEntry): number | undefined {
    return e.base !== undefined ? this.baseIx.get(e.base) : undefined;
  }
  headIndexOf(e: DiffEntry): number | undefined {
    return e.head !== undefined ? this.headIx.get(e.head) : undefined;
  }
  baseResult(e: DiffEntry): ClassifyResult | null {
    const i = this.baseIndexOf(e);
    return i === undefined || !this.base ? null : this.base.results[i] ?? null;
  }
  headResult(e: DiffEntry): ClassifyResult | null {
    return e.head ? this.svc.store.get(e.head) ?? null : null;
  }
  attachCount(globalId: string): number {
    const c = this.attach.countFor(globalId);
    return c.issues + c.sketches;
  }
  attachCountOf(e: DiffEntry): { issues: number; sketches: number } {
    const a = this.attach.countFor(e.base ?? e.head ?? '');
    if (e.base && e.head && e.base !== e.head) { const b = this.attach.countFor(e.head); return { issues: a.issues + b.issues, sketches: a.sketches + b.sketches }; }
    return a;
  }

  items(order: RevisionOrder, filters: RevisionFilters, group = true): RevisionItem[] {
    const s = this.state, b = this.base, h = this.head;
    if (!s || !b || !h) return [];
    return buildRevisionWalk({ base: b, head: h, diff: s.session.diff, order, filters, group, decisions: s.session.decisions, skipped: s.skippedKeys, attachments: (g) => this.attachCount(g) });
  }

  /** The entries that pass a set of filters, in diff order. */
  filtered(filters: RevisionFilters): DiffEntry[] {
    const s = this.state, b = this.base, h = this.head;
    if (!s || !b || !h) return [];
    return filterEntries({ base: b, head: h, diff: s.session.diff, decisions: s.session.decisions, skipped: s.skippedKeys, attachments: (g) => this.attachCount(g) }, filters);
  }

  // ------------------------------------------------------------ decisions

  private by(): string {
    return this.svc.review.reviewer();
  }

  private baseCommitted(e: DiffEntry): boolean {
    const r = this.baseResult(e);
    return !!r && (r.source === 'confirmed' || r.source === 'corrected');
  }

  /** The unflagged rematch whose base decision is carried when it is committed (the base's commits are rewritten to the head GlobalId). */
  private carriesCommits(e: DiffEntry): boolean {
    return e.category === 'rematched' && e.flags.length === 0 && !e.classifyAffected && this.baseCommitted(e);
  }

  /** The default classification of a plain Accept for an entry. */
  defaultFor(e: DiffEntry): RevisionDecision['classification'] {
    return defaultClassification(e, codesKey(this.baseResult(e)), codesKey(this.headResult(e)));
  }

  /** The non-default one of {base codes, new proposal} (the `2` key), or null when they are the same or there is only one. */
  otherFor(e: DiffEntry): RevisionDecision['classification'] | null {
    if (e.category !== 'changed' && e.category !== 'rematched') return null;
    const b = this.baseResult(e), h = this.headResult(e);
    if (!b || !h || codesKey(b) === codesKey(h)) return null;
    return this.defaultFor(e) === 'kept' ? 'new' : 'kept';
  }

  /** Put an accepted decision into the review's pending set (confirm or correct), through the review service. */
  private applyToReview(e: DiffEntry, d: RevisionDecision): void {
    if (d.verdict !== 'accepted' || d.classification === 'none' || !e.head || e.category === 'deleted' || this.carriesCommits(e)) return;
    const cur = this.svc.store.get(e.head);
    if (!cur) return;
    const item = `${REVISION_ITEM_PREFIX}${e.key}`;
    const base = { item, ...(d.note ? { comment: d.note } : {}), ...(d.unsure ? { unsure: true } : {}) };
    try {
      if (d.classification === 'edited' && d.edited) {
        this.svc.review.propose([e.head], { action: 'correct', codes: { discipline: d.edited.discipline, subDiscipline: d.edited.subDiscipline, masterformat: d.edited.division }, ...base });
      } else if (d.classification === 'kept') {
        const b = this.baseResult(e);
        if (b && codesKey(b) !== codesKey(cur)) {
          this.svc.review.propose([e.head], { action: 'correct', codes: { discipline: b.discipline.code, subDiscipline: b.subDiscipline?.code ?? null, masterformat: b.masterformat?.division ?? null }, ...base });
        } else this.svc.review.propose([e.head], { action: 'confirm', ...base });
      } else {
        this.svc.review.propose([e.head], { action: 'confirm', ...base });
      }
    } catch (err) {
      this.notice(err instanceof Error ? err.message : String(err), true);
    }
  }

  /** Accept or reject these entries. One undo step. Returns the decisions made. */
  decide(entries: readonly DiffEntry[], o: DecideOptions): RevisionDecision[] {
    const st = this.state;
    if (!st) return [];
    const undo: UndoEntry = { label: `${o.verdict} ${entries.length}`, keys: [], previous: [], previousSkipped: [] };
    const out: RevisionDecision[] = [];
    for (const e of entries) {
      undo.keys.push(e.key);
      undo.previous.push(st.decisionOf(e.key));
      if (st.isSkipped(e.key)) undo.previousSkipped.push(e.key);
      const classification = o.verdict === 'rejected' ? 'none' : o.classification ?? this.defaultFor(e);
      const d = st.decide({
        key: e.key, verdict: o.verdict, classification, by: this.by(),
        ...(o.unsure ? { unsure: true as const } : {}), ...(o.note ? { note: o.note } : {}),
        ...(o.edited && classification === 'edited' ? { edited: o.edited } : {}),
        ...(o.attachments && e.category === 'deleted' ? { attachments: o.attachments } : {}),
        ...(o.reattachTo ? { reattachTo: o.reattachTo } : {}),
      });
      this.svc.review.undoPending(`${REVISION_ITEM_PREFIX}${e.key}`);
      if (o.verdict === 'accepted') this.applyToReview(e, d);
      out.push(d);
    }
    this.undoStack.push(undo);
    st.updateStatus();
    this.emit();
    return out;
  }

  skip(entries: readonly DiffEntry[]): void {
    const st = this.state;
    if (!st) return;
    st.skip(entries.map((e) => e.key));
    this.emit();
  }

  /** Take the last decision step (single or bulk) back. */
  undoLast(): string | null {
    const st = this.state;
    const u = this.undoStack.pop();
    if (!st || !u) return null;
    if (u.bulk) st.undoBulk(u.bulk);
    else u.keys.forEach((k, i) => { const p = u.previous[i]; if (p) st.decide({ ...p }); else st.undecide(k); });
    for (const k of u.keys) {
      this.svc.review.undoPending(`${REVISION_ITEM_PREFIX}${k}`);
      const d = st.decisionOf(k), e = this.entry(k);
      if (d && e) this.applyToReview(e, d);
    }
    if (u.previousSkipped.length) st.skip(u.previousSkipped);
    st.updateStatus();
    this.emit();
    return u.label;
  }

  // ------------------------------------------------------------ bulk

  bulkRules(p: { maxMoveMm?: number; minScore?: number } = {}): BulkRule[] {
    return shippedRules(p);
  }

  private bulkContext(): BulkContext {
    return {
      infoOf: (e): BulkInfo => {
        const inHead = e.category !== 'deleted';
        const i = inHead ? this.headIndexOf(e) : this.baseIndexOf(e);
        const snap = inHead ? this.head : this.base;
        const r = inHead ? this.headResult(e) : this.baseResult(e);
        return {
          ifcClass: i !== undefined && snap ? snap.ifcClass[i]! : '',
          storey: (i !== undefined && snap ? snap.storey[i]?.name : '') ?? '',
          attachments: this.attachCount(stripFederation(e.base ?? e.head ?? '')) + (e.base && e.head && e.base !== e.head ? this.attachCount(e.head) : 0),
          needsReview: r ? r.needsReview : true,
          ...(r ? { source: r.source } : {}),
        };
      },
    };
  }

  /** The undecided entries a rule would take. `current-filter` needs the panel's filters. */
  bulkSelect(rule: BulkRule, filters: RevisionFilters = {}): DiffEntry[] {
    const st = this.state;
    if (!st) return [];
    const pool = rule.id === 'current-filter' ? this.filtered(filters) : st.session.diff.entries;
    return selectBulk(pool, rule, this.bulkContext()).filter((e) => !st.decisionOf(e.key));
  }

  applyBulk(rule: BulkRule, filters: RevisionFilters = {}): number {
    const st = this.state;
    if (!st) return 0;
    const entries = this.bulkSelect(rule, filters);
    if (entries.length === 0) return 0;
    const token = st.applyBulk(rule, entries, { by: this.by(), classification: (e) => this.defaultFor(e), attachments: 'keep' });
    this.undoStack.push({ label: `bulk ${rule.id}`, keys: token.keys, previous: [], previousSkipped: [], bulk: token });
    for (const k of token.keys) { const d = st.decisionOf(k), e = this.entry(k); if (d && e) this.applyToReview(e, d); }
    this.bulkApplied.push({ id: rule.id, label: rule.label, count: token.keys.length });
    st.updateStatus();
    this.emit();
    return token.keys.length;
  }

  // ------------------------------------------------------------ commit

  /** Decisions that wait for a commit: pending review changes plus carried rematches and attachment choices. */
  pendingCount(): { changes: number; other: number } {
    const st = this.state;
    if (!st) return { changes: 0, other: 0 };
    const changes = this.svc.review.pending().filter((p) => p.item.startsWith(REVISION_ITEM_PREFIX)).length;
    let other = 0;
    for (const d of Object.values(st.session.decisions)) {
      if (d.verdict !== 'accepted' || sidelined(d)) continue;
      const e = this.entry(d.key);
      if (e && (this.carriesCommits(e) || e.category === 'deleted' || (e.category === 'rematched' && e.base !== e.head))) other++;
    }
    return { changes, other };
  }

  /**
   * Write what the walk accepted: the pending changes as one commit of the review log; the base decisions of accepted rematches under
   * their new GlobalIds; the choices for attachments. Throws a plain Error when there is no reviewer name and changes are pending.
   */
  async commit(note = ''): Promise<{ commitId: string | null; changes: number; carried: number; attachments: number }> {
    const st = this.state, base = this.base, head = this.head;
    if (!st || !base || !head) throw new Error('No revision review is open.');
    const pend = this.svc.review.pending().filter((p) => p.item.startsWith(REVISION_ITEM_PREFIX));
    let commitId: string | null = null;
    if (pend.length) {
      const c = this.svc.review.commit(note.trim() || `Revision review: ${base.identity.name} to ${head.identity.name}`);
      commitId = c.id;
      st.attachCommit(pend.map((p) => p.item.slice(REVISION_ITEM_PREFIX.length)), c.id);
    }
    // accepted decisions whose effect is not a pending change
    const sideKeys: string[] = [];
    const rematchMap = new Map<string, string>();
    let attachments = 0;
    const rematchKeys: string[] = [];
    for (const d of Object.values(st.session.decisions)) {
      if (d.verdict !== 'accepted' || sidelined(d)) continue;
      const e = this.entry(d.key);
      if (!e) continue;
      if (this.carriesCommits(e)) rematchKeys.push(e.key);
      if (e.category === 'rematched' && e.base && e.head && e.base !== e.head) rematchMap.set(e.base, e.head);
      if (e.category === 'deleted' && e.base) {
        const n = this.attach.countFor(e.base);
        if (n.issues + n.sketches > 0) {
          if (d.attachments === 'resolve') attachments += this.attach.resolveIssues([e.base], 'element removed in revision');
          else if (d.attachments === 'reattach' && d.reattachTo) attachments += this.attach.retarget(new Map([[e.base, d.reattachTo]]));
          else attachments += this.attach.flagDeleted([e.base], `element deleted in ${head.identity.name}`);
        }
        sideKeys.push(e.key);
      }
      if (e.category === 'rematched') sideKeys.push(e.key);
    }
    let carried = 0;
    if (rematchKeys.length) {
      const input: CarryInput = { base, head, diff: st.session.diff, baseCommits: this.baseCommits };
      const commits = carryRematchCommits(input, rematchKeys);
      const r = await this.svc.review.appendCarried(commits);
      carried = r.added.length;
      if (commits[0]) st.attachCommit(rematchKeys, commits[0].id);
      else st.attachCommit(rematchKeys, 'applied');
    }
    if (rematchMap.size) attachments += this.attach.retarget(rematchMap);
    st.attachCommit(sideKeys.filter((k) => st.decisionOf(k)?.commitId === undefined), 'applied');
    st.updateStatus();
    this.emit();
    return { commitId, changes: pend.length, carried, attachments };
  }

  // ------------------------------------------------------------ issues (the user's call, never automatic)

  /** Raise one issue for rejected (or any) entries, with the element GlobalIds as components. Returns the issue guid, or null. */
  raiseIssue(entries: readonly DiffEntry[], text?: string): string | null {
    const b = window.__xrayIssues?.controller.bcf ?? bcfController();
    if (!b || !this.state || entries.length === 0) return null;
    const first = entries[0]!;
    const ids = entries.map((e) => e.head ?? e.base!).filter(Boolean);
    const verb: Record<DiffEntry['category'], string> = { new: 'should not be here', deleted: 'should not be gone', changed: 'change is wrong', rematched: 'is not the same element', unchanged: '' };
    const label = (e: DiffEntry): string => { const i = e.category === 'deleted' ? this.baseIndexOf(e) : this.headIndexOf(e); const s = e.category === 'deleted' ? this.base : this.head; return i !== undefined && s ? `${s.ifcClass[i]} ${s.name[i] || ''}`.trim() : e.key; };
    const title = `Revision: ${entries.length > 1 ? `${entries.length} elements, ` : ''}${label(first)} ${verb[first.category]}`;
    const description = [text, `Revision review ${this.base?.identity.name} to ${this.head?.identity.name}.`, ...entries.slice(0, 20).map((e) => `${e.category}${e.flags.length ? ` (${e.flags.join(', ')})` : ''}: ${label(e)} ${e.head ?? e.base}`)].filter(Boolean).join('\n');
    let pin: [number, number, number] | undefined;
    if (first.category === 'deleted' && this.base) {
      const i = this.baseIndexOf(first)!;
      const bb = this.base.bounds.subarray(i * 6, i * 6 + 6);
      const c: [number, number, number] = [(bb[0]! + bb[3]!) / 2, (bb[1]! + bb[4]!) / 2, (bb[2]! + bb[5]!) / 2];
      const f = this.frames;
      const w = [c[0] + f.baseShift[0] + f.offset[0] - f.headShift[0], c[1] + f.baseShift[1] + f.offset[1] - f.headShift[1], c[2] + f.baseShift[2] + f.offset[2] - f.headShift[2]];
      pin = [w[0]!, w[2]!, -w[1]!];
    }
    const topic = b.createTopic({ title, description, globalIds: ids, ...(pin ? { pin } : {}), ...(this.by() ? { author: this.by() } : {}) });
    const st = this.state;
    for (const e of entries) { const d = st.decisionOf(e.key); if (d) st.decide({ ...d, note: [d.note, `Issue ${topic.guid}`].filter(Boolean).join('; '), at: d.at }); }
    this.emit();
    return topic.guid;
  }

  // ------------------------------------------------------------ ghosts and camera frames

  ghostTargets(item: RevisionItem | null, only?: number): GhostTarget[] {
    if (!item) return [];
    const out: GhostTarget[] = [];
    item.entries.forEach((e, k) => {
      if (only !== undefined && k !== only) return;
      const el = item.elements[k]!;
      out.push({ kind: e.category as GhostTarget['kind'], ...(e.base ? { base: e.base } : {}), ...(e.category !== 'deleted' ? { headBox: el.bounds } : {}) });
    });
    return out;
  }

  // ------------------------------------------------------------ report (3.7)

  private reportInput(): Parameters<typeof revisionReportCsv>[0] | null {
    const st = this.state;
    if (!st || !this.base || !this.head) return null;
    return {
      base: this.base, head: this.head, diff: st.session.diff, decisions: st.session.decisions, skipped: st.session.skipped,
      carried: st.session.carried, bulk: this.bulkApplied, generatedAt: new Date().toISOString(),
    };
  }

  report(): { csv: string; summary: string; names: { csv: string; summary: string } } | null {
    const i = this.reportInput();
    if (!i) return null;
    return { csv: revisionReportCsv(i), summary: revisionSummaryMd(i), names: reportFileNames(i.base.identity.name, i.head.identity.name) };
  }

  /** The `extra.revision` of the save plan: the status of every element of the revised model, and the baseline's name. */
  status(): Map<string, RevisionStatus> | null {
    const st = this.state;
    if (!st) return null;
    return revisionStatusMap(st.session, this.app.controller.model.elements.map((e) => e.globalId));
  }

  /** The status of the model on screen from the stored session (open or finished), for Save IFC after a reload. */
  async storedStatus(): Promise<Map<string, RevisionStatus> | null> {
    if (this.state) return this.status();
    await this.ready;
    const id = loadedIdentity(this.app as never);
    if (!id || !this.store) return null;
    const k = identityKey(id);
    const list = (await this.store.sessions()).filter((s) => identityKey(s.head) === k).sort((a, b) => (a.updatedAt < b.updatedAt ? 1 : -1));
    const s = list[0];
    return s ? revisionStatusMap(s, this.app.controller.model.elements.map((e) => e.globalId)) : null;
  }

  identity(): ModelIdentity | null {
    return loadedIdentity(this.app as never);
  }
}
