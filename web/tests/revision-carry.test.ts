// The carry plan (design 3.4): what comes across from v1 to v2 when "Review changes" is clicked, and what does not.
import { beforeAll, describe, expect, it } from 'vitest';
import { ReviewLog, mergeCommits, parseReviewLog } from '../src/classify/reviewLog';
import type { ReviewChange, ReviewCommit, ReviewState } from '../src/classify/reviewLog';
import type { ClassifyResult } from '../src/classify/types';
import { carriedCommitId, carriedCommits, carryRematchCommits, planCarry } from '../src/revision/carry';
import type { CarryInput } from '../src/revision/carry';
import { diffModels } from '../src/revision/diff';
import type { ModelSnapshot, RevisionDiff } from '../src/revision/types';
import { fzk1, fzk2, loadIfc } from './revision-helpers';

let v1: ModelSnapshot, v2: ModelSnapshot;
let diff: RevisionDiff;
let baseCommits: ReviewCommit[];
const gidOf = (s: ModelSnapshot, name: string): string => s.globalId[s.name.indexOf(name)]!;

const state = (source: ReviewState['source'], disc = 'ARC'): ReviewState => ({ discipline: disc, subDiscipline: null, division: '06', source, confidence: source === 'confirmed' || source === 'corrected' ? 1 : 0.9 });
const result = (gid: string, source: ClassifyResult['source'], disc = 'ARC', commitId?: string): ClassifyResult => ({
  id: gid, discipline: { code: disc, label: disc, confidence: 0.9, probabilities: { [disc]: 0.9, XXX: 0.05, YYY: 0.03, ZZZ: 0.02 } }, subDiscipline: null,
  masterformat: { division: '06', title: 'Wood', confidence: 0.9, probabilities: { '06': 0.9 } }, buildingElement: 1, source, needsReview: false,
  ...(commitId ? { commitId, confirmedBy: 'Ana', confirmedAt: '2026-02-01T10:00:00.000Z' } : {}),
});
const change = (gid: string, action: 'confirm' | 'correct' = 'confirm', disc = 'ARC'): ReviewChange => ({ globalId: gid, before: state('rules'), after: state(action === 'confirm' ? 'confirmed' : 'corrected', disc), action });

const input = (): CarryInput => ({ base: v1, head: v2, diff, baseCommits });

beforeAll(async () => {
  const names = ['Sparren-1', 'Sparren-2', 'Sparren-4', 'Sparren-3', 'Sparren-10', 'Sparren-7', 'Haustuer', 'Sparren-30', 'Wand-Int-ERDG-2', 'Sparren-40'];
  // the log of v1: c1 confirms ten elements, c2 corrects Sparren-1 (so c1 no longer holds its effective change), c3 confirms Sparren-2 and is reverted by c4
  const probe = (await loadIfc(fzk1()));
  const fp = probe.snap.reviewFingerprint;
  const log = new ReviewLog({ modelName: 'AC20-FZK-Haus.ifc', modelFingerprint: fp, schemaEdition: 'ed1' });
  const g = (n: string): string => gidOf(probe.snap, n);
  log.commit({ author: 'Ana', id: 'c1', now: new Date('2026-02-01T10:00:00Z'), note: 'first pass', changes: names.filter((n) => n !== 'Sparren-2').map((n) => change(g(n))) });
  log.commit({ author: 'Ben', id: 'c2', now: new Date('2026-02-02T10:00:00Z'), changes: [change(g('Sparren-1'), 'correct', 'STR')] });
  log.commit({ author: 'Ana', id: 'c3', now: new Date('2026-02-03T10:00:00Z'), changes: [change(g('Sparren-2'))] });
  log.revert('c3', { author: 'Ana', id: 'c4', now: new Date('2026-02-04T10:00:00Z') });
  baseCommits = [...log.commits];
  const eff = log.effective();
  const results = (gid: string): ClassifyResult => {
    const e = eff.get(gid);
    return e ? result(gid, e.change.after.source as 'confirmed' | 'corrected', e.change.after.discipline, e.commit.id) : result(gid, 'rules');
  };
  v1 = (await loadIfc(fzk1(), { results })).snap;
  v2 = (await loadIfc(fzk2())).snap;
  diff = diffModels(v1, v2);
}, 120000);

describe('carry plan', () => {
  it('copies unchanged results as they are and carries their commits with author, time and carriedFrom', () => {
    const plan = planCarry(input());
    expect(plan.carry).toBe(true);
    const fp6 = v2.reviewFingerprint.slice(0, 6);
    const sp4 = plan.copy.find((c) => c.head === gidOf(v2, 'Sparren-4'))!;
    expect(sp4.kind).toBe('unchanged');
    expect(sp4.demoted).toBe(false);
    expect(sp4.result.source).toBe('confirmed');
    expect(sp4.result.commitId).toBe(`c1~${fp6}`);
    const c1 = plan.commits.find((c) => c.carriedFrom?.commitId === 'c1')!;
    expect(c1.id).toBe(carriedCommitId('c1', v2.reviewFingerprint));
    expect(c1).toMatchObject({ author: 'Ana', time: '2026-02-01T10:00:00.000Z', note: 'Carried over from AC20-FZK-Haus.ifc', modelFingerprint: v2.reviewFingerprint, carriedFrom: { fingerprint: v1.reviewFingerprint, commitId: 'c1' } });
    // only the unchanged element with an effective change in c1 comes across
    expect(c1.changes.map((x) => x.globalId)).toEqual([gidOf(v2, 'Sparren-4')]);
    // c2 corrected Sparren-1 (unchanged): author Ben, the correct action kept
    const c2 = plan.commits.find((c) => c.carriedFrom?.commitId === 'c2')!;
    expect(c2.author).toBe('Ben');
    expect(c2.changes[0]).toMatchObject({ globalId: gidOf(v2, 'Sparren-1'), action: 'correct', after: { discipline: 'STR', source: 'corrected' } });
    // c3 and its reversal leave Sparren-2 uncommitted: nothing of them is carried
    expect(plan.commits.map((c) => c.carriedFrom!.commitId).sort()).toEqual(['c1', 'c2']);
    expect(plan.counts.commits).toBe(2);
  });

  it('gives the head a log that parses, replays and shows only unchanged elements as committed', () => {
    const plan = planCarry(input());
    const log = new ReviewLog({ modelName: v2.identity.name, modelFingerprint: v2.reviewFingerprint, schemaEdition: 'ed1' }, plan.commits);
    expect(parseReviewLog(log.exportJson()).errors).toEqual([]);
    const committed = [...log.effective().keys()].sort();
    expect(committed).toEqual([gidOf(v2, 'Sparren-1'), gidOf(v2, 'Sparren-4')].sort());
    for (const c of plan.copy.filter((x) => !x.demoted && x.result.commitId)) expect(log.has(c.result.commitId!)).toBe(true);
  });

  it('adds no commit when run twice', () => {
    const a = planCarry(input());
    const b = planCarry(input());
    expect(b).toEqual(a);
    const merged = mergeCommits(a.commits, b.commits);
    expect(merged).toHaveLength(a.commits.length);
    const log = new ReviewLog({ modelName: 'x', modelFingerprint: v2.reviewFingerprint, schemaEdition: 'ed1' }, [...a.commits, ...b.commits]);
    expect(log.commits).toHaveLength(a.commits.length);
  });

  it('carries no commit for changed elements, only a suggestion, and demotes a committed result', () => {
    const plan = planCarry(input());
    const moved = gidOf(v2, 'Sparren-3'); // placement only, committed in v1
    const carriedIds = new Set(plan.commits.flatMap((c) => c.changes.map((x) => x.globalId)));
    for (const n of ['Sparren-3', 'Sparren-10', 'Sparren-7', 'Haustuer', 'Wand-Int-ERDG-2', 'Sparren-40']) expect(carriedIds.has(gidOf(v2, n)), n).toBe(false);
    expect(carriedIds.has(gidOf(v1, 'Sparren-30'))).toBe(false); // deleted
    const copy = plan.copy.find((c) => c.head === moved)!;
    expect(copy).toMatchObject({ kind: 'changed', demoted: true });
    expect(copy.result.source).toBe('cache');
    expect(copy.result.needsReview).toBe(true);
    expect(copy.result.commitId).toBeUndefined();
    expect(copy.result.confirmedBy).toBeUndefined();
    expect(copy.result.discipline.code).toBe('ARC'); // the base decision is the suggestion
    expect(plan.suggestions[moved]!.source).toBe('confirmed');
    expect(plan.suggestions[moved]!.id).toBe(moved);
  });

  it('lists for re-classification exactly the new and the classification-affected elements', () => {
    const plan = planCarry(input());
    const byReason = (r: string): string[] => plan.reclassify.filter((x) => x.reason === r).map((x) => x.head);
    expect(byReason('new').sort()).toEqual(diff.entries.filter((e) => e.category === 'new').map((e) => e.head!).sort());
    expect(byReason('affected').sort()).toEqual(['Sparren-10', 'Sparren-11', 'Sparren-40'].map((n) => gidOf(v2, n)).sort());
    expect(byReason('geometry')).toEqual([]);
    expect(plan.counts.reclassify).toBe(6);
    // an affected element is not copied: it will be classified again
    expect(plan.copy.some((c) => c.head === gidOf(v2, 'Sparren-10'))).toBe(false);
    // while the geometry settings are on, geometry and placement changes join the list
    const geo = planCarry({ ...input(), diff: diffModels(v1, v2, { geometryAffectsClassification: true }) });
    expect(geo.reclassify.filter((x) => x.reason === 'geometry')).toHaveLength(8);
    expect(geo.copy.some((c) => c.head === gidOf(v2, 'Sparren-3'))).toBe(false);
  });

  it('carries nothing with a different schema hash, and says why', () => {
    const other: ModelSnapshot = { ...v2, classificationSchemaHash: 'different' };
    const plan = planCarry({ ...input(), head: other });
    expect(plan.carry).toBe(false);
    expect(plan.reason).toMatch(/different classification schemas/);
    expect(plan.copy).toEqual([]);
    expect(plan.commits).toEqual([]);
    expect(plan.reclassify).toEqual([]);
    expect(carryRematchCommits({ ...input(), head: other }, diff.entries.map((e) => e.key))).toEqual([]);
  });

  it('carries the commits of a rematched element only after its match is accepted, under the head GlobalId', () => {
    const entry = diff.entries.find((e) => e.category === 'rematched' && e.head === gidOf(v2, 'Sparren-7'))!;
    expect(carryRematchCommits(input(), [])).toEqual([]);
    const first = carryRematchCommits(input(), [entry.key]);
    expect(first).toHaveLength(1);
    expect(first[0]!.changes[0]!.globalId).toBe(entry.head);
    expect(first[0]!.changes[0]!.globalId).not.toBe(entry.base);
    expect(first[0]!.carriedFrom).toEqual({ fingerprint: v1.reviewFingerprint, commitId: 'c1' });
    expect(first[0]!.id.startsWith(carriedCommitId('c1', v2.reviewFingerprint))).toBe(true);
    // not the id of the unchanged batch, so both fit in one log; the same batch twice is one commit
    const plan = planCarry(input());
    expect(plan.commits.map((c) => c.id)).not.toContain(first[0]!.id);
    expect(carryRematchCommits(input(), [entry.key])[0]!.id).toBe(first[0]!.id);
    const log = new ReviewLog({ modelName: 'x', modelFingerprint: v2.reviewFingerprint, schemaEdition: 'ed1' }, [...plan.commits, ...first, ...first]);
    expect(log.commits).toHaveLength(plan.commits.length + 1);
    expect(log.effective().has(entry.head!)).toBe(true);
    // a second element accepted later gets its own commit
    const other = diff.entries.find((e) => e.category === 'rematched' && e.head === gidOf(v2, 'Haustuer'))!;
    expect(carryRematchCommits(input(), [other.key])[0]!.id).not.toBe(first[0]!.id);
  });
});

describe('carriedCommits', () => {
  const info = { baseName: 'A.ifc', baseFingerprint: 'fpA', headName: 'B.ifc', headFingerprint: 'fpBfpBfp' };
  it('points a carried reversal at the carried commit it reverses, and drops the pointer when that one is not carried', () => {
    const commits: ReviewCommit[] = [
      { id: 'a', author: 'x', time: '2026-01-01T00:00:00Z', note: '', modelName: 'A', modelFingerprint: 'fpA', schemaEdition: '', changes: [change('q'), change('y')] },
      { id: 'r', author: 'x', time: '2026-01-02T00:00:00Z', note: '', modelName: 'A', modelFingerprint: 'fpA', schemaEdition: '', changes: [change('z', 'correct')], reverts: 'a' },
      { id: 's', author: 'x', time: '2026-01-03T00:00:00Z', note: '', modelName: 'A', modelFingerprint: 'fpA', schemaEdition: '', changes: [change('w', 'correct')], reverts: 'gone' },
    ];
    const out = carriedCommits(commits, new Map([['q', 'q2'], ['z', 'z2'], ['w', 'w2']]), info);
    expect(out.map((c) => c.id)).toEqual(['a~fpBfpB', 'r~fpBfpB', 's~fpBfpB']);
    expect(out[1]!.reverts).toBe('a~fpBfpB');
    expect(out[2]!.reverts).toBeUndefined();
    expect(out[0]!.changes.map((x) => x.globalId)).toEqual(['q2']);
  });
  it('is empty for an empty map or log', () => {
    expect(carriedCommits([], new Map([['a', 'b']]), info)).toEqual([]);
    expect(carriedCommits([{ id: 'a', author: 'x', time: '2026-01-01T00:00:00Z', note: '', modelName: '', modelFingerprint: '', schemaEdition: '', changes: [change('a')] }], new Map(), info)).toEqual([]);
  });
});
