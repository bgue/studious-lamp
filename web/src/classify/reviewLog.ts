// The review log: confirmations and corrections that a person committed, kept as an append-only list of commit records per model
// fingerprint. No DOM (the walk panel is in plugins/classifyReview.ts), so tests drive it directly.
//
//   commit { id, author, time (ISO), note, modelName, modelFingerprint, schemaEdition, changes: [{ globalId, before, after, action, comment? }] }
//
// A commit is never edited. A reversal is a new commit (`reverts` names the commit it undoes) whose changes put the earlier state back.
// The effective state of an element is its latest change in time order: when that change ends in source "confirmed" or "corrected"
// the element has a committed result; when it ends in any other source (a reversal back to a rule or a model result) it has none.

import type { KeyValueStorage } from './cache';
import { makeManual } from './results';
import { overallConfidence } from './review';
import type { ClassificationSchema, ClassifyResult, ResultSource } from './types';

export const REVIEW_LOG_SCHEMA = 'xray-classification-review/1';
export const REVIEWER_STORAGE_KEY = 'xray.classify.reviewer.v1';
export const REVIEW_LOG_PREFIX = 'xray.classify.review.v1.';
/**
 * The confidence of a result that a person confirmed or corrected and flagged "Unsure (a guess)". The codes are set, but the result is not
 * as good as a sure one (confidence 1) and it still needs review, so it comes up again in "Needs review first" and "Only needs review".
 */
export const UNSURE_CONFIDENCE = 0.75;

/** The part of a result that a review records: the codes, where they came from and how sure the source was. */
export interface ReviewState {
  discipline: string;
  subDiscipline: string | null;
  division: string | null;
  source: ResultSource;
  confidence: number;
}

export type ReviewAction = 'confirm' | 'correct';

export interface ReviewChange {
  globalId: string;
  before: ReviewState;
  after: ReviewState;
  action: ReviewAction;
  comment?: string;
  /** Set (true) when the reviewer flagged the change as a guess. Absent means false: older logs and imports have no such field. */
  unsure?: true;
}

export interface ReviewCommit {
  id: string;
  author: string;
  time: string;
  note: string;
  modelName: string;
  modelFingerprint: string;
  schemaEdition: string;
  changes: ReviewChange[];
  /** Set when this commit reverses another one. */
  reverts?: string;
}

export interface ReviewLogDoc {
  schema: typeof REVIEW_LOG_SCHEMA;
  modelName: string;
  modelFingerprint: string;
  schemaEdition: string;
  exportedAt: string;
  commits: ReviewCommit[];
}

export const isCommittedSource = (s: ResultSource): boolean => s === 'confirmed' || s === 'corrected';

/** Does a state (the "before" of a change) come from a committed result that was flagged unsure? A sure commit has confidence 1. */
export const isUnsureState = (s: ReviewState): boolean => isCommittedSource(s.source) && s.confidence < 1;

/** A short hash (two 32-bit FNV-1a passes, 16 hex characters) of the sorted GlobalIds and the schema hash. */
export function modelFingerprint(globalIds: Iterable<string>, schemaHash: string): string {
  const ids = [...globalIds].sort();
  let h1 = 0x811c9dc5;
  let h2 = 0x01000193 ^ 0x9e3779b9;
  const feed = (text: string): void => {
    for (let i = 0; i < text.length; i++) {
      const c = text.charCodeAt(i);
      h1 = Math.imul(h1 ^ c, 16777619);
      h2 = Math.imul(h2 ^ c ^ (h1 >>> 7), 2246822519);
    }
    h1 = Math.imul(h1 ^ 0x1f, 16777619);
    h2 = Math.imul(h2 ^ 0x1f, 2246822519);
  };
  for (const id of ids) feed(id);
  feed(`schema:${schemaHash}`);
  const hex = (n: number): string => (n >>> 0).toString(16).padStart(8, '0');
  return `${hex(h1)}${hex(h2)}`;
}

/** The edition of a schema as the log records it: its edition, else its version, else its title. */
export const schemaEditionOf = (s: ClassificationSchema): string => s.edition ?? s.version ?? s.title;

export function stateOf(r: ClassifyResult): ReviewState {
  return { discipline: r.discipline.code, subDiscipline: r.subDiscipline?.code ?? null, division: r.masterformat?.division ?? null, source: r.source, confidence: overallConfidence(r) };
}

export const sameState = (a: ReviewState, b: ReviewState): boolean => a.discipline === b.discipline && a.subDiscipline === b.subDiscipline && a.division === b.division && a.source === b.source;

const deepFreeze = <T>(v: T): T => {
  if (v && typeof v === 'object') {
    for (const k of Object.keys(v)) deepFreeze((v as Record<string, unknown>)[k]);
    Object.freeze(v);
  }
  return v;
};

export interface Effective {
  change: ReviewChange;
  commit: ReviewCommit;
}

export interface LogInfo {
  modelName: string;
  modelFingerprint: string;
  schemaEdition: string;
}

export interface ImportOutcome {
  ok: boolean;
  /** Plain-language reason when `ok` is false. */
  error?: string;
  added: string[];
  duplicates: string[];
}

const newId = (now: Date): string => `c${now.getTime().toString(36)}${Math.floor(Math.random() * 36 ** 4).toString(36).padStart(4, '0')}`;

/** The commits of one model fingerprint. Append only. */
export class ReviewLog {
  private readonly list: ReviewCommit[] = [];
  private readonly ids = new Set<string>();

  constructor(readonly info: LogInfo, commits: readonly ReviewCommit[] = []) {
    for (const c of commits) this.add(c);
  }

  get commits(): readonly ReviewCommit[] {
    return this.list;
  }
  get fingerprint(): string {
    return this.info.modelFingerprint;
  }
  has(id: string): boolean {
    return this.ids.has(id);
  }
  get(id: string): ReviewCommit | undefined {
    return this.list.find((c) => c.id === id);
  }

  private add(c: ReviewCommit): boolean {
    if (this.ids.has(c.id)) return false;
    this.ids.add(c.id);
    this.list.push(deepFreeze(structuredCloneJson(c)));
    return true;
  }

  /** Build and append a commit. Throws a plain Error when there is nothing to commit or no author. */
  commit(o: { author: string; note?: string; changes: readonly ReviewChange[]; reverts?: string; now?: Date; id?: string }): ReviewCommit {
    const author = o.author.trim();
    if (!author) throw new Error('Enter your name or initials first: a commit records who made it.');
    if (o.changes.length === 0) throw new Error('There is nothing to commit.');
    const now = o.now ?? new Date();
    const c: ReviewCommit = {
      id: o.id ?? newId(now),
      author,
      time: now.toISOString(),
      note: (o.note ?? '').trim(),
      modelName: this.info.modelName,
      modelFingerprint: this.info.modelFingerprint,
      schemaEdition: this.info.schemaEdition,
      changes: o.changes.map((x) => ({ globalId: x.globalId, before: { ...x.before }, after: { ...x.after }, action: x.action, ...(x.comment ? { comment: x.comment } : {}), ...(x.unsure ? { unsure: true as const } : {}) })),
      ...(o.reverts ? { reverts: o.reverts } : {}),
    };
    if (!this.add(c)) throw new Error(`A commit with the id ${c.id} exists already.`);
    return this.get(c.id)!;
  }

  /**
   * The latest change of every element, replayed in time order (ties in the order of the list). An element whose latest change ends in a
   * source other than confirmed or corrected is not committed any more, and is absent.
   */
  effective(): Map<string, Effective> {
    const order = this.list.map((c, i) => ({ c, i })).sort((a, b) => (a.c.time < b.c.time ? -1 : a.c.time > b.c.time ? 1 : a.i - b.i));
    const latest = new Map<string, Effective>();
    for (const { c } of order) for (const change of c.changes) latest.set(change.globalId, { change, commit: c });
    for (const [gid, e] of latest) if (!isCommittedSource(e.change.after.source)) latest.delete(gid);
    return latest;
  }

  /** The state of an element now: its committed state, or null. */
  committedState(globalId: string): ReviewState | null {
    return this.effective().get(globalId)?.change.after ?? null;
  }

  /**
   * Append a commit that reverses `commitId`: for every element that the commit changed and that no later commit changed again, the
   * state before it comes back. Returns the new commit and the GlobalIds that were left alone because a later commit changed them.
   */
  revert(commitId: string, o: { author: string; note?: string; now?: Date; id?: string }): { commit: ReviewCommit; skipped: string[] } {
    const target = this.get(commitId);
    if (!target) throw new Error(`There is no commit ${commitId}.`);
    if (this.list.some((c) => c.reverts === commitId)) throw new Error(`The commit ${commitId} was reverted already.`);
    // The state of each element after the commit, replayed up to the end of the log.
    const eff = new Map<string, Effective | null>();
    const order = this.list.map((c, i) => ({ c, i })).sort((a, b) => (a.c.time < b.c.time ? -1 : a.c.time > b.c.time ? 1 : a.i - b.i));
    for (const { c } of order) for (const ch of c.changes) eff.set(ch.globalId, { change: ch, commit: c });
    const changes: ReviewChange[] = [];
    const skipped: string[] = [];
    for (const ch of target.changes) {
      const now = eff.get(ch.globalId);
      if (!now || now.commit.id !== target.id) {
        skipped.push(ch.globalId);
        continue;
      }
      changes.push({ globalId: ch.globalId, before: { ...ch.after }, after: { ...ch.before }, action: 'correct', comment: `Reverts ${target.id}`, ...(isUnsureState(ch.before) ? { unsure: true as const } : {}) });
    }
    if (changes.length === 0) throw new Error('Every element of that commit was changed again by a later commit, so there is nothing to revert.');
    const commit = this.commit({ author: o.author, note: o.note ?? `Reverts ${target.id}`, changes, reverts: target.id, ...(o.now ? { now: o.now } : {}), ...(o.id ? { id: o.id } : {}) });
    return { commit, skipped };
  }

  toDoc(now = new Date()): ReviewLogDoc {
    return { schema: REVIEW_LOG_SCHEMA, ...this.info, exportedAt: now.toISOString(), commits: this.list.map((c) => structuredCloneJson(c)) };
  }

  /** The text of "Export review log". */
  exportJson(now = new Date()): string {
    return JSON.stringify(this.toDoc(now), null, 2);
  }

  /**
   * Replay a review log exported earlier. A log of another model (the fingerprint differs) is refused, and nothing is added. Commits whose
   * id is in this log already are skipped, so importing the same file twice changes nothing.
   */
  importDoc(input: unknown): ImportOutcome {
    const p = parseReviewLog(input);
    if (!p.doc) return { ok: false, error: p.errors.join(' '), added: [], duplicates: [] };
    if (p.doc.modelFingerprint !== this.fingerprint) {
      return {
        ok: false,
        error: `This review log belongs to another model or schema: its fingerprint is ${p.doc.modelFingerprint} (${p.doc.modelName}), and this model's is ${this.fingerprint} (${this.info.modelName}). Nothing was imported.`,
        added: [],
        duplicates: [],
      };
    }
    const added: string[] = [];
    const duplicates: string[] = [];
    for (const c of p.doc.commits) {
      if (this.add(c)) added.push(c.id);
      else duplicates.push(c.id);
    }
    return { ok: true, added, duplicates };
  }
}

function structuredCloneJson<T>(v: T): T {
  return JSON.parse(JSON.stringify(v)) as T;
}

// ---------------------------------------------------------------- parsing (untrusted input)

const isObj = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
const SOURCES: readonly string[] = ['rules', 'cache', 'model', 'manual', 'confirmed', 'corrected'];

function parseState(v: unknown, where: string, errors: string[]): ReviewState | null {
  if (!isObj(v) || typeof v['discipline'] !== 'string' || typeof v['source'] !== 'string' || !SOURCES.includes(v['source']) || typeof v['confidence'] !== 'number') {
    errors.push(`${where} is not a state with a discipline, a source and a confidence.`);
    return null;
  }
  const opt = (k: string): string | null | undefined => (v[k] === null || v[k] === undefined ? null : typeof v[k] === 'string' ? (v[k] as string) : undefined);
  const sub = opt('subDiscipline');
  const div = opt('division');
  if (sub === undefined || div === undefined) {
    errors.push(`${where} has a sub-discipline or division that is not text or null.`);
    return null;
  }
  return { discipline: v['discipline'], subDiscipline: sub, division: div, source: v['source'] as ResultSource, confidence: v['confidence'] };
}

/** Check an untrusted review log (text or value). Never throws. */
export function parseReviewLog(input: unknown): { doc: ReviewLogDoc | null; errors: string[] } {
  let v: unknown = input;
  if (typeof input === 'string') {
    try {
      v = JSON.parse(input);
    } catch (e) {
      return { doc: null, errors: [`The file is not valid JSON: ${e instanceof Error ? e.message : String(e)}`] };
    }
  }
  const errors: string[] = [];
  if (!isObj(v) || v['schema'] !== REVIEW_LOG_SCHEMA) return { doc: null, errors: [`The file is not a review log: "schema" must be "${REVIEW_LOG_SCHEMA}".`] };
  if (typeof v['modelFingerprint'] !== 'string' || !v['modelFingerprint']) errors.push('"modelFingerprint" is missing.');
  if (!Array.isArray(v['commits'])) errors.push('"commits" must be a list.');
  if (errors.length) return { doc: null, errors };
  const commits: ReviewCommit[] = [];
  (v['commits'] as unknown[]).forEach((c, i) => {
    if (!isObj(c) || typeof c['id'] !== 'string' || !c['id'] || typeof c['author'] !== 'string' || typeof c['time'] !== 'string' || Number.isNaN(Date.parse(c['time'])) || !Array.isArray(c['changes'])) {
      errors.push(`Commit ${i + 1} needs an id, an author, an ISO time and a list of changes.`);
      return;
    }
    const changes: ReviewChange[] = [];
    (c['changes'] as unknown[]).forEach((ch, j) => {
      const at = `Commit ${c['id'] as string}, change ${j + 1}`;
      if (!isObj(ch) || typeof ch['globalId'] !== 'string' || (ch['action'] !== 'confirm' && ch['action'] !== 'correct')) {
        errors.push(`${at} needs a globalId and an action "confirm" or "correct".`);
        return;
      }
      const before = parseState(ch['before'], `${at}: "before"`, errors);
      const after = parseState(ch['after'], `${at}: "after"`, errors);
      const u = ch['unsure'];
      if (u !== undefined && u !== null && typeof u !== 'boolean') {
        errors.push(`${at} has an "unsure" that is not true or false.`);
        return;
      }
      if (before && after) changes.push({ globalId: ch['globalId'], before, after, action: ch['action'], ...(typeof ch['comment'] === 'string' && ch['comment'] ? { comment: ch['comment'] } : {}), ...(u === true ? { unsure: true as const } : {}) });
    });
    commits.push({
      id: c['id'],
      author: c['author'],
      time: c['time'],
      note: typeof c['note'] === 'string' ? c['note'] : '',
      modelName: typeof c['modelName'] === 'string' ? c['modelName'] : '',
      modelFingerprint: typeof c['modelFingerprint'] === 'string' ? c['modelFingerprint'] : (v['modelFingerprint'] as string),
      schemaEdition: typeof c['schemaEdition'] === 'string' ? c['schemaEdition'] : '',
      changes,
      ...(typeof c['reverts'] === 'string' && c['reverts'] ? { reverts: c['reverts'] } : {}),
    });
  });
  if (errors.length) return { doc: null, errors };
  return {
    doc: {
      schema: REVIEW_LOG_SCHEMA,
      modelName: typeof v['modelName'] === 'string' ? v['modelName'] : '',
      modelFingerprint: v['modelFingerprint'] as string,
      schemaEdition: typeof v['schemaEdition'] === 'string' ? v['schemaEdition'] : '',
      exportedAt: typeof v['exportedAt'] === 'string' ? v['exportedAt'] : '',
      commits,
    },
    errors: [],
  };
}

// ---------------------------------------------------------------- committed results

/** The result that a committed change gives its element. Throws a plain Error when a code is not in the schema. */
export function committedResult(schema: ClassificationSchema, e: Effective, prior?: ClassifyResult): ClassifyResult {
  const a = e.change.after;
  const base = makeManual(schema, e.change.globalId, { discipline: a.discipline, subDiscipline: a.subDiscipline, masterformat: a.division });
  const src: ResultSource = a.source === 'corrected' ? 'corrected' : 'confirmed';
  const unsure = e.change.unsure === true;
  if (unsure) {
    for (const c of [base.discipline, base.subDiscipline, base.masterformat]) {
      if (!c) continue;
      c.confidence = UNSURE_CONFIDENCE;
      const code = 'division' in c ? c.division : c.code;
      c.probabilities = { [code]: UNSURE_CONFIDENCE };
    }
  }
  return {
    ...base,
    buildingElement: prior?.buildingElement ?? base.buildingElement,
    source: src,
    needsReview: unsure,
    rationale: `${src === 'corrected' ? 'corrected' : 'confirmed'} in the review walk${unsure ? ' (unsure)' : ''}`,
    confirmedBy: e.commit.author,
    confirmedAt: e.commit.time,
    commitId: e.commit.id,
    ...(unsure ? { unsure: true } : {}),
  };
}

// ---------------------------------------------------------------- storage

/** Where a log is kept: loaded and saved per model fingerprint. Both calls may reject. */
export interface ReviewPersistence {
  load(fingerprint: string): Promise<ReviewCommit[]>;
  save(fingerprint: string, info: LogInfo, commits: readonly ReviewCommit[]): Promise<{ where: 'indexeddb' | 'localstorage' }>;
}

const IDB_NAME = 'xray-classification-review';
const IDB_STORE = 'logs';

function withTimeout<T>(p: Promise<T>, ms: number, what: string): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const t = setTimeout(() => reject(new Error(`${what} did not answer`)), ms);
    p.then((v) => { clearTimeout(t); resolve(v); }, (e) => { clearTimeout(t); reject(e); });
  });
}

function idbOpen(factory: IDBFactory): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = factory.open(IDB_NAME, 1);
    req.onupgradeneeded = () => { req.result.createObjectStore(IDB_STORE, { keyPath: 'fingerprint' }); };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error ?? new Error('IndexedDB could not be opened'));
    req.onblocked = () => reject(new Error('IndexedDB is blocked'));
  });
}

function idbRun<T>(db: IDBDatabase, mode: IDBTransactionMode, fn: (s: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    const tx = db.transaction(IDB_STORE, mode);
    const req = fn(tx.objectStore(IDB_STORE));
    tx.oncomplete = () => resolve(req.result);
    tx.onerror = () => reject(tx.error ?? new Error('IndexedDB failed'));
    tx.onabort = () => reject(tx.error ?? new Error('IndexedDB aborted'));
  });
}

const commitsOf = (v: unknown): ReviewCommit[] => {
  const p = parseReviewLog({ schema: REVIEW_LOG_SCHEMA, modelFingerprint: 'x', commits: isObj(v) ? v['commits'] : [] });
  return p.doc?.commits ?? [];
};

/** Merge two lists of commits by id (the first list wins), in time order. */
export function mergeCommits(a: readonly ReviewCommit[], b: readonly ReviewCommit[]): ReviewCommit[] {
  const seen = new Set<string>();
  const out: ReviewCommit[] = [];
  for (const c of [...a, ...b]) if (!seen.has(c.id)) { seen.add(c.id); out.push(c); }
  return out.sort((x, y) => (x.time < y.time ? -1 : x.time > y.time ? 1 : 0));
}

/**
 * IndexedDB first, localStorage when IndexedDB is missing, blocked or fails. Every call is wrapped: a load that fails answers with no
 * commits, and a save that fails in both places rejects, so the caller can say that the log is kept for this session only.
 */
export function createReviewPersistence(env: { indexedDB?: IDBFactory | null; local?: KeyValueStorage | null } = {}): ReviewPersistence {
  const factory = env.indexedDB === undefined ? (typeof indexedDB !== 'undefined' ? indexedDB : null) : env.indexedDB;
  const local = env.local === undefined ? null : env.local;
  const localKey = (fp: string): string => `${REVIEW_LOG_PREFIX}${fp}`;
  let db: Promise<IDBDatabase> | null = null;
  const open = (): Promise<IDBDatabase> => {
    if (!factory) return Promise.reject(new Error('no IndexedDB'));
    db ??= withTimeout(idbOpen(factory), 3000, 'IndexedDB');
    db.catch(() => { db = null; });
    return db;
  };
  return {
    async load(fp) {
      let fromIdb: ReviewCommit[] = [];
      let fromLocal: ReviewCommit[] = [];
      try {
        const d = await open();
        fromIdb = commitsOf(await withTimeout(idbRun(d, 'readonly', (s) => s.get(fp)), 3000, 'IndexedDB'));
      } catch { /* fall back to localStorage */ }
      try {
        const t = local?.getItem(localKey(fp));
        if (t) fromLocal = commitsOf(JSON.parse(t));
      } catch { /* ignore a broken entry */ }
      return mergeCommits(fromIdb, fromLocal);
    },
    async save(fp, info, commits) {
      const record = { fingerprint: fp, modelName: info.modelName, schemaEdition: info.schemaEdition, commits: JSON.parse(JSON.stringify(commits)) as ReviewCommit[] };
      try {
        const d = await open();
        await withTimeout(idbRun(d, 'readwrite', (s) => s.put(record)), 3000, 'IndexedDB');
        try { local?.removeItem(localKey(fp)); } catch { /* ignore */ }
        return { where: 'indexeddb' as const };
      } catch { /* try localStorage */ }
      if (!local) throw new Error('The log could not be stored: IndexedDB and localStorage are both unavailable.');
      try {
        local.setItem(localKey(fp), JSON.stringify(record));
        return { where: 'localstorage' as const };
      } catch (e) {
        throw new Error(`The log could not be stored: ${e instanceof Error ? e.message : String(e)}`);
      }
    },
  };
}
