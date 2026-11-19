// The revision walk: order and grouping pinned for fzk-v2, filters, bulk rules, and decisions turning into pending review changes.
import { beforeAll, describe, expect, it } from 'vitest';
import type { ClassifyResult } from '../src/classify/types';
import { bulkContextOf, selectBulk, shippedRules } from '../src/revision/bulk';
import { diffModels } from '../src/revision/diff';
import { SessionState, defaultClassification, newSession } from '../src/revision/session';
import type { DiffEntry, ModelSnapshot, RevisionDiff } from '../src/revision/types';
import { REVISION_ORDERS } from '../src/revision/types';
import { buildRevisionWalk, filterEntries } from '../src/revision/walkOrder';
import { fzk1, fzk2, loadIfc } from './revision-helpers';

let v1: ModelSnapshot, v2: ModelSnapshot;
let diff: RevisionDiff;

const rulesResult = (gid: string, needsReview = false): ClassifyResult => ({
  id: gid, discipline: { code: 'ARC', label: 'Architecture', confidence: 0.9, probabilities: { ARC: 0.9 } }, subDiscipline: null, masterformat: null, buildingElement: 1, source: 'rules', needsReview,
});

beforeAll(async () => {
  v1 = (await loadIfc(fzk1())).snap;
  v2 = (await loadIfc(fzk2(), { results: (g) => rulesResult(g, g === 'never') })).snap;
  diff = diffModels(v1, v2);
}, 120000);

const base = () => ({ base: v1, head: v2, diff });
const entryOf = (name: string): DiffEntry => diff.entries.find((e) => (e.head ? v2.name[v2.globalId.indexOf(e.head)] : v1.name[v1.globalId.indexOf(e.base!)]) === name)!;

describe('order and items', () => {
  it('has the default order pinned: deleted, rematched, changed, new; inside a kind by storey, class, location', () => {
    const items = buildRevisionWalk(base());
    expect(items.map((i) => `${i.category}|${i.flags.join('+')}|${i.title}`)).toEqual([
      'deleted||IfcWindow: EG-Fenster-6',
      'deleted||2 x IfcMember: Sparren-30',
      'deleted||IfcRailing: 00000000-0000-0000-00-00-000000000000',
      'rematched||IfcDoor: Haustuer',
      'rematched||IfcStair: Wendeltreppe',
      'rematched||IfcWallStandardCase: Wand-Int-ERDG-3',
      'rematched||IfcBeam: Pfette-2-1',
      'rematched||IfcMember: Sparren-7',
      'rematched||IfcSlab: Dach-2',
      'changed|placement|IfcBeam: Unterzug-1',
      'changed|geometry|2 x IfcWallStandardCase: Wand-Ext-ERDG-1',
      'changed|properties|3 x IfcWallStandardCase: Wand-Int-ERDG-5',
      'changed|placement|IfcBeam: Pfette-1-1',
      'changed|class|IfcBeam: Sparren-40',
      'changed|placement|IfcBeam: First',
      'changed|placement|IfcMember: Sparren-12',
      'changed|type|2 x IfcMember: Sparren-11',
      'changed|placement|2 x IfcMember: Sparren-8',
      'new||2 x IfcMember: Sparren-6 (copy)',
      'new||IfcSlab: Dach-1 (copy)',
    ]);
    // every listed entry is in exactly one item
    expect(items.flatMap((i) => i.entries.map((e) => e.key)).sort()).toEqual(diff.entries.map((e) => e.key).sort());
    for (const i of items) expect(i.entries).toHaveLength(i.elements.length);
  });

  it('is repeatable and independent of the diff entry order', () => {
    const a = buildRevisionWalk(base()).map((i) => i.key);
    const reversed: RevisionDiff = { ...diff, entries: [...diff.entries].reverse() };
    expect(buildRevisionWalk({ ...base(), diff: reversed }).map((i) => i.key)).toEqual(a);
  });

  it('has the storey order lowest first, and the class order alphabetical, with the other two as tie-breakers', () => {
    expect(REVISION_ORDERS).toEqual(['category', 'storey', 'class']);
    const byStorey = buildRevisionWalk({ ...base(), order: 'storey' });
    const first = byStorey.findIndex((i) => i.storeyName === 'Dachgeschoss');
    expect(byStorey.slice(0, first).every((i) => i.storeyName === 'Erdgeschoss')).toBe(true);
    expect(byStorey.slice(first).every((i) => i.storeyName === 'Dachgeschoss')).toBe(true);
    expect(byStorey[0]!.category).toBe('deleted');
    const byClass = buildRevisionWalk({ ...base(), order: 'class' });
    const classes = byClass.map((i) => i.ifcClass);
    expect([...classes].sort()).toEqual(classes);
    expect(byClass[0]!.ifcClass).toBe('IfcBeam');
  });

  it('groups alike changes into one item: 5 mm moves of two rafters, both deleted rafters, both new copies', () => {
    const items = buildRevisionWalk(base());
    const moves = items.find((i) => i.entries.some((e) => e.key === entryOf('Sparren-3').key))!;
    expect(moves.entries.map((e) => e.key).sort()).toEqual([entryOf('Sparren-3').key, entryOf('Sparren-8').key].sort());
    const d = moves.entries.map((e) => e.delta!);
    for (let k = 0; k < 3; k++) expect(Math.abs(d[0]![k]! - d[1]![k]!)).toBeLessThan(0.001);
    expect(items.filter((i) => i.category === 'deleted').map((i) => i.elements.length)).toEqual([1, 2, 1]);
    // different moves are different items
    expect(items.find((i) => i.entries.some((e) => e.key === entryOf('Sparren-12').key))!.entries).toHaveLength(1);
  });

  it('can show one item per element', () => {
    expect(buildRevisionWalk({ ...base(), group: false })).toHaveLength(27);
  });

  it('keeps the unchanged elements out of the items and counts them', () => {
    expect(diff.counts.unchanged).toBe(58);
    expect(buildRevisionWalk(base()).some((i) => i.category === 'unchanged')).toBe(false);
  });
});

describe('filters', () => {
  const entries = (f: Parameters<typeof filterEntries>[1]): DiffEntry[] => filterEntries(base(), f);
  it('filters by category, flag, storey, class and move', () => {
    expect(entries({ category: 'changed' })).toHaveLength(14);
    expect(entries({ category: 'deleted' })).toHaveLength(4);
    expect(entries({ flag: 'placement' })).toHaveLength(6);
    expect(entries({ storey: 'Erdgeschoss' }).every((e) => e.category !== 'new')).toBe(true);
    expect(entries({ ifcClass: 'IfcSlab' }).map((e) => e.category).sort()).toEqual(['new', 'rematched']);
    expect(entries({ minMove: 0.1 })).toHaveLength(3); // 2 x 250 mm and the turned beam
    expect(buildRevisionWalk({ ...base(), filters: { flag: 'properties' } })).toHaveLength(1);
  });

  it('filters by decision state, skips and attachments', () => {
    const s = new SessionState(newSession({ base: v1.identity, head: v2.identity, diff }));
    const a = entryOf('Sparren-12'), b = entryOf('Unterzug-1'), c = entryOf('Wendeltreppe');
    s.decide({ key: a.key, verdict: 'accepted', classification: 'kept', by: 'Ana' });
    s.decide({ key: b.key, verdict: 'accepted', classification: 'kept', by: 'Ana', unsure: true });
    s.skip([c.key]);
    const ctx = { ...base(), decisions: s.session.decisions, skipped: s.skippedKeys, attachments: (g: string) => (g === c.base ? 2 : 0) };
    expect(filterEntries(ctx, { undecided: true })).toHaveLength(27 - 2);
    expect(filterEntries(ctx, { unsure: true }).map((e) => e.key)).toEqual([b.key]);
    expect(filterEntries(ctx, { onlySkipped: true }).map((e) => e.key)).toEqual([c.key]);
    expect(filterEntries(ctx, { hasAttachments: true }).map((e) => e.key)).toEqual([c.key]);
  });
});

describe('bulk rules', () => {
  const ctx = (att: (g: string) => number = () => 0) => bulkContextOf(v1, v2, att);
  const rule = (id: string) => shippedRules().find((r) => r.id === id)!;

  it('"placement-only moves up to 10 mm" selects exactly the three small moves', () => {
    const picked = selectBulk(diff.entries, rule('placement-moves'), ctx());
    expect(picked.map((e) => e.key).sort()).toEqual(['Sparren-3', 'Sparren-8', 'Pfette-1-1'].map((n) => entryOf(n).key).sort());
    // the field is editable: 300 mm adds the two 250 mm moves, never the turned beam
    const wide = selectBulk(diff.entries, shippedRules({ maxMoveMm: 300 }).find((r) => r.id === 'placement-moves')!, ctx());
    expect(wide).toHaveLength(5);
    expect(wide.some((e) => e.rotated)).toBe(false);
  });

  it('"property-only changes" selects the three walls; "rematch score" the six; "deleted with nothing attached" respects attachments', () => {
    expect(selectBulk(diff.entries, rule('property-only'), ctx())).toHaveLength(3);
    expect(selectBulk(diff.entries, rule('rematch-high'), ctx())).toHaveLength(6);
    expect(selectBulk(diff.entries, shippedRules({ minScore: 1.01 }).find((r) => r.id === 'rematch-high')!, ctx())).toHaveLength(0);
    expect(selectBulk(diff.entries, rule('deleted-clean'), ctx())).toHaveLength(4);
    const window = entryOf('EG-Fenster-6');
    expect(selectBulk(diff.entries, rule('deleted-clean'), ctx((g) => (g === window.base ? 1 : 0)))).toHaveLength(3);
  });

  it('"new elements classified by a rule and not needing review" reads the head results', () => {
    expect(selectBulk(diff.entries, rule('new-by-rules'), ctx())).toHaveLength(3);
    const c = bulkContextOf(v1, { ...v2, results: v2.results.map((r) => (r ? { ...r, needsReview: true } : r)) }, () => 0);
    expect(selectBulk(diff.entries, rule('new-by-rules'), c)).toHaveLength(0);
  });

  it('"current filter" takes whatever it is given, and a rule can narrow by storey and class', () => {
    const some = diff.entries.slice(0, 5);
    expect(selectBulk(some, rule('current-filter'), ctx())).toEqual(some);
    expect(selectBulk(diff.entries, { id: 'x', label: 'x', ifcClass: 'IfcSlab', category: 'new' }, ctx())).toHaveLength(1);
    expect(selectBulk(diff.entries, { id: 'y', label: 'y', storey: 'Erdgeschoss', category: 'deleted' }, ctx())).toHaveLength(1);
  });

  it('applies as one undo step and leaves decided elements alone', () => {
    const s = new SessionState(newSession({ base: v1.identity, head: v2.identity, diff }));
    const manual = entryOf('Sparren-3');
    s.decide({ key: manual.key, verdict: 'rejected', classification: 'none', by: 'Ana' });
    const picked = selectBulk(diff.entries, rule('placement-moves'), ctx());
    const token = s.applyBulk(rule('placement-moves'), picked, { by: 'Ana', classification: (e) => defaultClassification(e) });
    expect(token.keys).toHaveLength(2);
    expect(s.session.decisions[manual.key]!.verdict).toBe('rejected');
    expect(s.session.decisions[entryOf('Sparren-8').key]).toMatchObject({ verdict: 'accepted', bulk: 'placement-moves', classification: 'kept' });
    expect(s.undoBulk(token)).toBe(2);
    expect(Object.keys(s.session.decisions)).toEqual([manual.key]);
  });
});

describe('decisions become pending review changes', () => {
  it('proposes every accepted decision without a commit, except those that make no classification', () => {
    const s = new SessionState(newSession({ base: v1.identity, head: v2.identity, diff }));
    const keys = ['Sparren-3', 'Sparren-10', 'EG-Fenster-6', 'Sparren-5 (copy)', 'Pfette-1-1'].map((n) => entryOf(n));
    s.decide({ key: keys[0]!.key, verdict: 'accepted', classification: defaultClassification(keys[0]!), by: 'Ana' });
    s.decide({ key: keys[1]!.key, verdict: 'accepted', classification: defaultClassification(keys[1]!), by: 'Ana' });
    s.decide({ key: keys[2]!.key, verdict: 'accepted', classification: defaultClassification(keys[2]!), by: 'Ana' }); // deleted: none
    s.decide({ key: keys[3]!.key, verdict: 'accepted', classification: defaultClassification(keys[3]!), by: 'Ana', unsure: true });
    s.decide({ key: keys[4]!.key, verdict: 'rejected', classification: 'none', by: 'Ana', note: 'the move is wrong' });
    expect(defaultClassification(keys[0]!)).toBe('kept'); // classification not affected
    expect(defaultClassification(keys[1]!)).toBe('new'); // type changed: the new proposal
    expect(defaultClassification(keys[1]!, 'A/B/06', 'A/B/06')).toBe('kept'); // unless it equals the base codes
    expect(s.pendingProposals().map((d) => d.key).sort()).toEqual([keys[0]!.key, keys[1]!.key, keys[3]!.key].sort());
    s.attachCommit([keys[0]!.key], 'c9');
    expect(s.pendingProposals().map((d) => d.key)).not.toContain(keys[0]!.key);
    // a decision takes the element off the skip list; progress counts
    s.skip([entryOf('Dach-2').key, keys[0]!.key]);
    expect(s.isSkipped(keys[0]!.key)).toBe(false);
    expect(s.progress()).toEqual({ total: 27, decided: 5, accepted: 4, rejected: 1, unsure: 1, skipped: 1, undecided: 22 });
    expect(s.resumeLabel()).toBe('Resume revision review (5 of 27 decided)');
    // a resume re-classifies only new and affected elements that have no result yet
    const has = new Set([keys[3]!.head!]);
    expect(s.needsClassify((g) => has.has(g)).length).toBe(3 - 1 + 3); // 3 affected + 3 new, minus the new copy that has a result
  });

  it('finishes a session when nothing is left undecided', () => {
    const s = new SessionState(newSession({ base: v1.identity, head: v2.identity, diff }));
    expect(s.updateStatus()).toBe('open');
    for (const e of diff.entries) s.decide({ key: e.key, verdict: 'accepted', classification: 'kept', by: 'Ana' });
    expect(s.updateStatus()).toBe('finished');
    s.undecide(diff.entries[0]!.key);
    expect(s.updateStatus()).toBe('open');
  });
});
