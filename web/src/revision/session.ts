// A revision session (design 4.2): the diff, the user's decisions, the skips and the cursor of one walk. Pure state with no storage:
// store.ts keeps it. Unlike the review walk, skips are stored (a revision walk spans days). `SessionState` mutates in place (a
// session holds up to hundreds of thousands of decisions) and bumps `updatedAt`; every mutation calls `onChange`, which the app
// uses to schedule the debounced save.

import type { ClassifyResult } from '../classify/types';
import { DEFAULT_REVISION_OPTIONS, REVISION_ORDERS } from './types';
import type { DiffEntry, ModelIdentity, RevisionDecision, RevisionDiff, RevisionFilters, RevisionOptions, RevisionOrder, RevisionSession } from './types';
import { identityKey } from '../markup/scope';

export const SESSION_SCHEMA = 'xray-revision/1';

export const sessionKey = (base: ModelIdentity, head: ModelIdentity): string => `${identityKey(base)}>${identityKey(head)}`;

export interface NewSessionInput {
  base: ModelIdentity;
  head: ModelIdentity;
  baseName?: string;
  diff: RevisionDiff;
  options?: RevisionOptions;
  carried?: RevisionSession['carried'];
  now?: Date;
}

export function newSession(i: NewSessionInput): RevisionSession {
  const t = (i.now ?? new Date()).toISOString();
  return {
    schema: SESSION_SCHEMA,
    key: sessionKey(i.base, i.head),
    base: i.base,
    head: i.head,
    baseName: i.baseName ?? i.base.name,
    createdAt: t,
    updatedAt: t,
    status: 'open',
    options: i.options ?? i.diff.options ?? DEFAULT_REVISION_OPTIONS,
    diff: i.diff,
    carried: i.carried ?? null,
    decisions: {},
    skipped: [],
    cursor: { order: 'category', filters: {}, itemKey: null, elementIndex: 0 },
  };
}

/**
 * The classification a plain Accept (Enter) records (design 3.6): a new element takes its proposal, a deleted one has none, a changed
 * one keeps the base codes when the classification is not affected or the new proposal equals them, else takes the new proposal.
 */
export function defaultClassification(e: DiffEntry, baseCodes?: string, headCodes?: string): RevisionDecision['classification'] {
  if (e.category === 'new') return 'new';
  if (e.category === 'deleted') return 'none';
  if (!e.classifyAffected || (baseCodes !== undefined && baseCodes === headCodes)) return 'kept';
  return 'new';
}

export const codesKey = (r: ClassifyResult | null | undefined): string => (r ? `${r.discipline.code}/${r.subDiscipline?.code ?? ''}/${r.masterformat?.division ?? ''}` : '');

export interface Progress {
  total: number;
  decided: number;
  accepted: number;
  rejected: number;
  unsure: number;
  skipped: number;
  undecided: number;
}

export interface BulkToken {
  rule: string;
  keys: string[];
  previous: Array<RevisionDecision | undefined>;
  previousSkipped: string[];
}

export class SessionState {
  private readonly skippedSet: Set<string>;

  constructor(readonly session: RevisionSession, private readonly o: { onChange?: () => void; now?: () => Date } = {}) {
    this.skippedSet = new Set(session.skipped);
  }

  private touch(): void {
    this.session.updatedAt = (this.o.now?.() ?? new Date()).toISOString();
    this.o.onChange?.();
  }
  private sync(): void {
    this.session.skipped = [...this.skippedSet];
  }

  get key(): string {
    return this.session.key;
  }
  decisionOf(key: string): RevisionDecision | undefined {
    return this.session.decisions[key];
  }
  isSkipped(key: string): boolean {
    return this.skippedSet.has(key);
  }
  get skippedKeys(): ReadonlySet<string> {
    return this.skippedSet;
  }

  /** Record a decision. A decision takes the element off the skip list. */
  decide(d: Omit<RevisionDecision, 'at'> & { at?: string }): RevisionDecision {
    const full: RevisionDecision = { ...d, at: d.at ?? (this.o.now?.() ?? new Date()).toISOString() };
    if (full.unsure !== true) delete full.unsure;
    this.session.decisions[full.key] = full;
    this.skippedSet.delete(full.key);
    this.sync();
    this.touch();
    return full;
  }

  /** Take a decision back (undo). Returns it. */
  undecide(key: string): RevisionDecision | undefined {
    const d = this.session.decisions[key];
    if (d) { delete this.session.decisions[key]; this.touch(); }
    return d;
  }

  /** Record the review commit that an accepted decision became. */
  attachCommit(keys: readonly string[], commitId: string): void {
    for (const k of keys) { const d = this.session.decisions[k]; if (d) d.commitId = commitId; }
    this.touch();
  }

  skip(keys: Iterable<string>): number {
    let n = 0;
    for (const k of keys) if (!this.session.decisions[k] && !this.skippedSet.has(k)) { this.skippedSet.add(k); n++; }
    this.sync();
    this.touch();
    return n;
  }
  unskip(keys: Iterable<string>): number {
    let n = 0;
    for (const k of keys) if (this.skippedSet.delete(k)) n++;
    this.sync();
    this.touch();
    return n;
  }

  /** Apply a bulk rule: every selected entry that is not decided yet is accepted. One undo step: keep the token. */
  applyBulk(rule: { id: string; label?: string }, entries: readonly DiffEntry[], o: { by: string; classification: (e: DiffEntry) => RevisionDecision['classification']; attachments?: RevisionDecision['attachments']; at?: string }): BulkToken {
    const token: BulkToken = { rule: rule.id, keys: [], previous: [], previousSkipped: [] };
    for (const e of entries) {
      if (this.session.decisions[e.key]) continue;
      token.keys.push(e.key);
      token.previous.push(undefined);
      if (this.skippedSet.has(e.key)) token.previousSkipped.push(e.key);
      this.session.decisions[e.key] = {
        key: e.key, verdict: 'accepted', classification: o.classification(e), ...(o.attachments ? { attachments: o.attachments } : {}),
        at: o.at ?? (this.o.now?.() ?? new Date()).toISOString(), by: o.by, bulk: rule.id,
      };
      this.skippedSet.delete(e.key);
    }
    this.sync();
    this.touch();
    return token;
  }

  undoBulk(t: BulkToken): number {
    let n = 0;
    t.keys.forEach((k, i) => {
      const cur = this.session.decisions[k];
      if (cur && cur.bulk === t.rule) {
        const prev = t.previous[i];
        if (prev) this.session.decisions[k] = prev; else delete this.session.decisions[k];
        n++;
      }
    });
    for (const k of t.previousSkipped) this.skippedSet.add(k);
    this.sync();
    this.touch();
    return n;
  }

  setCursor(c: Partial<RevisionSession['cursor']>): void {
    this.session.cursor = { ...this.session.cursor, ...c };
    this.touch();
  }

  progress(): Progress {
    const entries = this.session.diff.entries;
    let accepted = 0, rejected = 0, unsure = 0, skipped = 0;
    for (const e of entries) {
      const d = this.session.decisions[e.key];
      if (d) { if (d.verdict === 'accepted') accepted++; else rejected++; if (d.unsure) unsure++; } else if (this.skippedSet.has(e.key)) skipped++;
    }
    const decided = accepted + rejected;
    return { total: entries.length, decided, accepted, rejected, unsure, skipped, undecided: entries.length - decided };
  }

  /** "Resume revision review (123 of 410 decided)". */
  resumeLabel(): string {
    const p = this.progress();
    return `Resume revision review (${p.decided} of ${p.total} decided)`;
  }

  /** Mark the session finished when nothing is undecided or skipped, open again otherwise. Returns the new status. */
  updateStatus(): RevisionSession['status'] {
    const p = this.progress();
    const next = p.total > 0 && p.undecided === 0 ? 'finished' : 'open';
    if (next !== this.session.status) { this.session.status = next; this.touch(); }
    return next;
  }

  /**
   * What a resume re-does (design 4.2): every accepted decision that has no commit yet is proposed again as pending (the review walk's
   * pending set is session-only). Decisions with classification 'none' make no review change.
   */
  pendingProposals(): RevisionDecision[] {
    return Object.values(this.session.decisions).filter((d) => d.verdict === 'accepted' && d.classification !== 'none' && !d.commitId);
  }

  /** Head GlobalIds of new and classification-affected entries that have no result: the only elements a resume re-classifies. */
  needsClassify(hasResult: (headGlobalId: string) => boolean): string[] {
    return this.session.diff.entries.filter((e) => e.head && (e.category === 'new' || e.classifyAffected) && !hasResult(e.head)).map((e) => e.head!);
  }

  toJSON(): RevisionSession {
    return this.session;
  }
}

// ---------------------------------------------------------------- reading a stored session (untrusted: IndexedDB can hold anything)

const isObj = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);

export function parseSession(v: unknown): { session: RevisionSession | null; errors: string[] } {
  const errors: string[] = [];
  if (!isObj(v) || v['schema'] !== SESSION_SCHEMA) return { session: null, errors: [`Not a revision session: "schema" must be "${SESSION_SCHEMA}".`] };
  if (typeof v['key'] !== 'string' || !v['key']) errors.push('"key" is missing.');
  if (!isObj(v['diff']) || !Array.isArray((v['diff'] as Record<string, unknown>)['entries'])) errors.push('"diff.entries" must be a list.');
  if (!isObj(v['base']) || !isObj(v['head'])) errors.push('"base" and "head" must be model identities.');
  if (!isObj(v['decisions'])) errors.push('"decisions" must be an object.');
  if (!Array.isArray(v['skipped'])) errors.push('"skipped" must be a list.');
  if (errors.length) return { session: null, errors };
  const decisions: Record<string, RevisionDecision> = {};
  for (const [k, d] of Object.entries(v['decisions'] as Record<string, unknown>)) {
    if (!isObj(d) || (d['verdict'] !== 'accepted' && d['verdict'] !== 'rejected') || typeof d['at'] !== 'string' || typeof d['by'] !== 'string') continue;
    const cls = d['classification'];
    decisions[k] = {
      key: k,
      verdict: d['verdict'],
      classification: cls === 'kept' || cls === 'new' || cls === 'edited' || cls === 'none' ? cls : 'none',
      at: d['at'],
      by: d['by'],
      ...(d['unsure'] === true ? { unsure: true as const } : {}),
      ...(isObj(d['edited']) && typeof d['edited']['discipline'] === 'string' ? { edited: { discipline: d['edited']['discipline'], subDiscipline: typeof d['edited']['subDiscipline'] === 'string' ? d['edited']['subDiscipline'] : null, division: typeof d['edited']['division'] === 'string' ? d['edited']['division'] : null } } : {}),
      ...(d['attachments'] === 'keep' || d['attachments'] === 'reattach' || d['attachments'] === 'resolve' ? { attachments: d['attachments'] } : {}),
      ...(typeof d['reattachTo'] === 'string' ? { reattachTo: d['reattachTo'] } : {}),
      ...(typeof d['note'] === 'string' ? { note: d['note'] } : {}),
      ...(typeof d['bulk'] === 'string' ? { bulk: d['bulk'] } : {}),
      ...(typeof d['commitId'] === 'string' ? { commitId: d['commitId'] } : {}),
    };
  }
  const c = isObj(v['cursor']) ? v['cursor'] : {};
  const order: RevisionOrder = (REVISION_ORDERS as readonly string[]).includes(c['order'] as string) ? (c['order'] as RevisionOrder) : 'category';
  const session: RevisionSession = {
    ...(v as unknown as RevisionSession),
    decisions,
    skipped: (v['skipped'] as unknown[]).filter((x): x is string => typeof x === 'string'),
    status: v['status'] === 'finished' ? 'finished' : 'open',
    options: { ...DEFAULT_REVISION_OPTIONS, ...(isObj(v['options']) ? (v['options'] as Partial<RevisionOptions>) : {}) },
    carried: isObj(v['carried']) ? (v['carried'] as unknown as RevisionSession['carried']) : null,
    cursor: {
      order,
      filters: isObj(c['filters']) ? (c['filters'] as RevisionFilters) : {},
      itemKey: typeof c['itemKey'] === 'string' ? c['itemKey'] : null,
      elementIndex: typeof c['elementIndex'] === 'number' && c['elementIndex'] >= 0 ? Math.floor(c['elementIndex']) : 0,
    },
  };
  return { session, errors: [] };
}
