// The carry plan (design 3.4): what moves from the base to the head when the user clicks "Review changes". Pure: it only computes
// lists; the caller applies them (adoptResults, appendCarried, classify). Nothing here touches a store or the classifier.
//
//   unchanged   result copied as is (source kept), commits carried
//   changed     classification not affected: result copied but demoted to a suggestion that the walk visits; no commit carried
//               classification affected (or geometry/placement while the geometry settings are on): re-run list; base result = suggestion
//   rematched   as changed or unchanged by its flags, and its commits carried only after the match is accepted (carryRematchCommits)
//   new         re-run list
//   deleted     nothing (the base log is never edited)
// A different classification schema hash carries nothing: the diff and the report still work.

import { ReviewLog } from '../classify/reviewLog';
import type { ReviewChange, ReviewCommit } from '../classify/reviewLog';
import type { ClassifyResult, ResultSource } from '../classify/types';
import { stripFederation } from './snapshot';
import type { DiffEntry, ModelSnapshot, RevisionDiff } from './types';

/** The source of a base decision that is only a suggestion in the head: it is not committed there until the walk accepts it. */
export const DEMOTED_SOURCE: ResultSource = 'cache';
/** Length of the head fingerprint prefix in a carried commit id. */
export const CARRY_ID_CHARS = 6;

export interface CarryInput {
  base: ModelSnapshot;
  head: ModelSnapshot;
  diff: RevisionDiff;
  baseCommits: readonly ReviewCommit[];
}

export interface CarriedResult {
  head: string;
  base: string;
  result: ClassifyResult;
  kind: 'unchanged' | 'changed' | 'rematched';
  /** True: the base decision came along as a suggestion only (source 'cache', needs review). */
  demoted: boolean;
}

export interface CarryPlan {
  carry: boolean;
  /** Plain-language reason when `carry` is false. */
  reason?: string;
  baseName: string;
  baseFingerprint: string;
  headFingerprint: string;
  copy: CarriedResult[];
  reclassify: Array<{ head: string; reason: 'new' | 'affected' | 'geometry' }>;
  /** Head GlobalId -> the base result, for every changed or rematched element that has one. */
  suggestions: Record<string, ClassifyResult>;
  /** Commits for the unchanged elements, to append to the head log (mergeCommits dedupes by id). */
  commits: ReviewCommit[];
  counts: { copied: number; demoted: number; reclassify: number; commits: number; committedElements: number };
}

export const carriedCommitId = (baseCommitId: string, headFingerprint: string): string => `${baseCommitId}~${headFingerprint.slice(0, CARRY_ID_CHARS)}`;

function demote(r: ClassifyResult, baseName: string): ClassifyResult {
  const { confirmedBy: _by, confirmedAt: _at, commitId: _c, ...rest } = r;
  const committed = r.source === 'confirmed' || r.source === 'corrected';
  return { ...rest, source: committed ? DEMOTED_SOURCE : r.source, needsReview: true, rationale: `suggested from ${baseName}; confirm it in the revision walk` };
}

function retarget(r: ClassifyResult, headGid: string): ClassifyResult {
  return { ...r, id: headGid };
}

/**
 * The carried commits: for every base commit that still holds the effective change of a mapped element, one commit in the head with
 * the same author and time, only those changes, GlobalIds rewritten through `map` (base -> head).
 * `idSuffix` is added to the id so a later batch (accepted rematches) does not collide with the first.
 */
export function carriedCommits(baseCommits: readonly ReviewCommit[], map: ReadonlyMap<string, string>, o: { baseName: string; baseFingerprint: string; headName: string; headFingerprint: string; idSuffix?: string }): ReviewCommit[] {
  if (map.size === 0 || baseCommits.length === 0) return [];
  const log = new ReviewLog({ modelName: o.baseName, modelFingerprint: o.baseFingerprint, schemaEdition: '' }, baseCommits);
  const effective = log.effective();
  const byCommit = new Map<string, ReviewChange[]>();
  for (const [gid, e] of effective) {
    const head = map.get(gid);
    if (head === undefined) continue;
    const list = byCommit.get(e.commit.id) ?? byCommit.set(e.commit.id, []).get(e.commit.id)!;
    list.push({ ...e.change, globalId: head });
  }
  const ids = new Map<string, string>();
  const out: ReviewCommit[] = [];
  for (const c of log.commits) {
    const changes = byCommit.get(c.id);
    if (changes) ids.set(c.id, `${carriedCommitId(c.id, o.headFingerprint)}${o.idSuffix ?? ''}`);
    if (!changes) continue;
    out.push({
      id: ids.get(c.id)!,
      author: c.author,
      time: c.time,
      note: `Carried over from ${o.baseName}`,
      modelName: o.headName,
      modelFingerprint: o.headFingerprint,
      schemaEdition: c.schemaEdition,
      changes: changes.map((x) => ({ ...x, before: { ...x.before }, after: { ...x.after } })),
      carriedFrom: { fingerprint: o.baseFingerprint, commitId: c.id },
    });
  }
  // a carried reversal points at the carried commit it reverses; when that one was not carried the pointer is dropped
  for (const c of out) {
    const target = baseCommits.find((b) => b.id === c.carriedFrom!.commitId)?.reverts;
    if (target && ids.has(target)) c.reverts = ids.get(target)!;
  }
  return out;
}

const indexByGid = (s: ModelSnapshot): Map<string, number> => {
  const m = new Map<string, number>();
  for (let i = 0; i < s.globalId.length; i++) { const g = stripFederation(s.globalId[i]!); if (g && !m.has(g)) m.set(g, i); }
  return m;
};

/** Rewrite the commitId of a result that a carried commit now stands for. */
function withCarriedCommit(r: ClassifyResult, headFp: string, carried: ReadonlySet<string>): ClassifyResult {
  return r.commitId && carried.has(r.commitId) ? { ...r, commitId: carriedCommitId(r.commitId, headFp) } : r;
}

export function planCarry(inp: CarryInput): CarryPlan {
  const { base, head, diff } = inp;
  const plan: CarryPlan = {
    carry: true, baseName: base.identity.name, baseFingerprint: base.reviewFingerprint, headFingerprint: head.reviewFingerprint,
    copy: [], reclassify: [], suggestions: {}, commits: [], counts: { copied: 0, demoted: 0, reclassify: 0, commits: 0, committedElements: 0 },
  };
  if (base.classificationSchemaHash !== head.classificationSchemaHash) {
    return { ...plan, carry: false, reason: 'The two models were reviewed with different classification schemas, so decisions cannot be carried over. The changes and the report are still available.' };
  }
  const baseIx = indexByGid(base);
  const entryOf = new Map<string, DiffEntry>();
  for (const e of diff.entries) if (e.head) entryOf.set(e.head, e);
  const geometryDriven = diff.options.geometryAffectsClassification;
  const unchangedMap = new Map<string, string>();

  for (let j = 0; j < head.globalId.length; j++) {
    const hg = head.globalId[j]!;
    const e = entryOf.get(hg);
    if (e?.category === 'new') { plan.reclassify.push({ head: hg, reason: 'new' }); continue; }
    const bi = e ? baseIx.get(stripFederation(e.base!)) : baseIx.get(stripFederation(hg));
    if (bi === undefined) continue;
    const bg = base.globalId[bi]!;
    const r = base.results[bi];
    if (!e) {
      // unchanged: result as is, its commits are carried below
      if (r) { plan.copy.push({ head: hg, base: bg, result: retarget(r, hg), kind: 'unchanged', demoted: false }); unchangedMap.set(bg, hg); }
      continue;
    }
    if (r) plan.suggestions[hg] = retarget(r, hg);
    const geometric = e.flags.includes('geometry') || e.flags.includes('placement');
    if (e.classifyAffected || (geometryDriven && geometric)) {
      plan.reclassify.push({ head: hg, reason: e.classifyAffected ? 'affected' : 'geometry' });
    } else if (r) {
      plan.copy.push({ head: hg, base: bg, result: retarget(demote(r, base.identity.name), hg), kind: e.category === 'rematched' ? 'rematched' : 'changed', demoted: true });
    }
  }

  plan.commits = carriedCommits(inp.baseCommits, unchangedMap, { baseName: base.identity.name, baseFingerprint: base.reviewFingerprint, headName: head.identity.name, headFingerprint: head.reviewFingerprint });
  const carried = new Set(plan.commits.map((c) => c.carriedFrom!.commitId));
  plan.copy = plan.copy.map((c) => (c.demoted ? c : { ...c, result: withCarriedCommit(c.result, head.reviewFingerprint, carried) }));
  plan.counts = {
    copied: plan.copy.length,
    demoted: plan.copy.filter((c) => c.demoted).length,
    reclassify: plan.reclassify.length,
    commits: plan.commits.length,
    committedElements: plan.commits.reduce((n, c) => n + c.changes.length, 0),
  };
  return plan;
}

/**
 * The commits of rematched elements whose match the user accepted (`acceptedKeys` are DiffEntry keys), under the head GlobalIds.
 * The commit id carries a hash of the accepted set, so a second batch does not collide with the first and the same batch twice adds nothing.
 */
export function carryRematchCommits(inp: CarryInput, acceptedKeys: Iterable<string>): ReviewCommit[] {
  const { base, head, diff } = inp;
  if (base.classificationSchemaHash !== head.classificationSchemaHash) return [];
  const accepted = new Set(acceptedKeys);
  const map = new Map<string, string>();
  for (const e of diff.entries) if (e.category === 'rematched' && accepted.has(e.key) && e.base && e.head) map.set(e.base, e.head);
  const tag = [...map.values()].sort().join('|');
  let h = 0x811c9dc5;
  for (let i = 0; i < tag.length; i++) h = Math.imul(h ^ tag.charCodeAt(i), 0x01000193);
  return carriedCommits(inp.baseCommits, map, { baseName: base.identity.name, baseFingerprint: base.reviewFingerprint, headName: head.identity.name, headFingerprint: head.reviewFingerprint, idSuffix: `r${(h >>> 0).toString(36)}` });
}
