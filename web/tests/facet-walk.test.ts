// Facet items of the review walk: which results are items, candidates, and the whole decision path through the review log
// (propose, commit, human result, revert, additive log format).

import { describe, expect, it } from 'vitest';
import { ClassifyService, ReviewLog, parseReviewLog, REVIEW_LOG_SCHEMA } from '../src/classify';
import type { ReviewCommit, ReviewPersistence } from '../src/classify';
import { buildFacetItems, facetCandidates, inFacetWalk } from '../src/classify/facetWalk';
import type { FacetEntry, FacetLike } from '../src/classify/facetWalk';
import { classCandidates } from '../src/classify/reviewWalk';
import type { WalkElement } from '../src/classify/reviewWalk';
import { MemoryStorage } from '../src/selectionSets';
import type { FacetResult } from '../src/classify/facets/defs';
import type { ConcreteFacetResult } from '../src/classify/concrete/defs';
import type { ClassifyResult } from '../src/classify/types';
import { sidecarModel } from './classify-helpers';

const fr = (o: Partial<FacetLike> & { facet: string; code: string }): FacetLike => ({ label: o.code, confidence: 0.5, source: 'model', needsReview: true, ...o });
const el = (i: number, o: Partial<WalkElement> = {}): WalkElement => ({ id: i, globalId: `G${i}`, ifcClass: 'IfcWall', name: `W${i}`, tag: '', storey: 0, storeyName: 'L0', elevation: 0, system: '', signature: 's', bounds: [i, 0, 0, i + 1, 1, 1], ...o });

describe('facet items', () => {
  it('are the results that need review or that a person decided, one item per element and facet', () => {
    const els = [el(0), el(1), el(2)];
    const by: Record<string, FacetEntry[]> = {
      G0: [{ ref: { id: 'Trade', family: 'facet' }, result: fr({ facet: 'Trade', code: 'CONC' }) }, { ref: { id: 'Material', family: 'facet' }, result: fr({ facet: 'Material', code: 'STEEL', needsReview: false, source: 'rule', confidence: 1 }) }],
      G1: [{ ref: { id: 'Material', family: 'facet' }, result: fr({ facet: 'Material', code: 'CONCRETE', source: 'human', needsReview: false, confidence: 1 }) }],
      G2: [{ ref: { id: 'ConcreteElement', family: 'concrete' }, result: fr({ facet: 'ConcreteElement', code: 'BEAM' }) }, { ref: { id: 'Trade', family: 'facet' }, result: fr({ facet: 'Trade', code: 'STEEL' }) }],
    };
    const items = buildFacetItems({ elements: els, entriesOf: (g) => by[g] ?? [] });
    // facets in the order Trade, Material, ..., Concrete*; inside one facet by location
    expect(items.map((i) => i.key)).toEqual(['facet:Trade:G0', 'facet:Trade:G2', 'facet:Material:G1', 'facet:ConcreteElement:G2']);
    expect(items[0]!.facet).toEqual({ id: 'Trade', family: 'facet' });
    expect(items[3]!.title).toBe('Concrete Element: IfcWall: W2');
    expect(items.every((i) => i.elements.length === 1)).toBe(true);
    expect(inFacetWalk(fr({ facet: 'Trade', code: 'X', needsReview: false }))).toBe(false);
  });

  it('honours the unsure, unconfirmed and skipped filters', () => {
    const els = [el(0), el(1)];
    const by: Record<string, FacetEntry[]> = {
      G0: [{ ref: { id: 'Trade', family: 'facet' }, result: fr({ facet: 'Trade', code: 'A', source: 'human', needsReview: true, confidence: 0.75 }) }],
      G1: [{ ref: { id: 'Trade', family: 'facet' }, result: fr({ facet: 'Trade', code: 'B', source: 'human', needsReview: false, confidence: 1 }) }],
    };
    const mk = (filters: Parameters<typeof buildFacetItems>[0]['filters']) => buildFacetItems({ elements: els, entriesOf: (g) => by[g] ?? [], ...(filters ? { filters } : {}) }).map((i) => i.key);
    expect(mk(undefined)).toEqual(['facet:Trade:G0', 'facet:Trade:G1']);
    expect(mk({ unsure: true })).toEqual(['facet:Trade:G0']);
    expect(mk({ unconfirmed: true })).toEqual(['facet:Trade:G0']);
    expect(buildFacetItems({ elements: els, entriesOf: (g) => by[g] ?? [], skipped: { has: (g) => g === 'G1' }, filters: { onlySkipped: true } }).map((i) => i.key)).toEqual(['facet:Trade:G1']);
  });

  it('numbers the candidates: the proposal is 1, the runner-up 2, the rest by probability, only codes of the list', () => {
    const codes = [{ code: 'A', label: 'Alpha' }, { code: 'B', label: 'Beta' }, { code: 'C', label: 'Gamma' }];
    const r = fr({ facet: 'Trade', code: 'B', label: 'Beta', probabilities: { A: 0.2, B: 0.5, C: 0.25, Z: 0.05 } });
    expect(facetCandidates(r, codes).map((c) => c.code)).toEqual(['B', 'C', 'A']);
    expect(facetCandidates(r, codes)[1]).toEqual({ code: 'C', label: 'Gamma', probability: 0.25 });
    expect(facetCandidates(fr({ facet: 'Trade', code: 'B' }), codes).map((c) => c.code)).toEqual(['B']);
    expect(facetCandidates(r, codes, 2).length).toBe(2);
  });

  it('numbers the candidates of a classification on the part with the narrowest margin', () => {
    const r = { id: 'x', discipline: { code: 'MEC', label: 'M', confidence: 0.5, probabilities: { MEC: 0.5, PLB: 0.3, ELE: 0.15, XXX: 0.05 } }, subDiscipline: null, masterformat: null, buildingElement: 1, source: 'model', needsReview: true } as ClassifyResult;
    const c = classCandidates(r, (_p, code) => code !== 'XXX')!;
    expect(c.part).toBe('discipline');
    expect(c.list.map((x) => x.code)).toEqual(['MEC', 'PLB', 'ELE']);
  });
});

function memoryPersistence(): ReviewPersistence {
  const saved = new Map<string, ReviewCommit[]>();
  return {
    load: async (fp) => JSON.parse(JSON.stringify(saved.get(fp) ?? [])) as ReviewCommit[],
    save: async (fp, _i, commits) => { saved.set(fp, JSON.parse(JSON.stringify(commits)) as ReviewCommit[]); return { where: 'indexeddb' as const }; },
  };
}

function setup() {
  const svc = new ClassifyService({ storage: new MemoryStorage() as never, keyStorages: { session: new MemoryStorage() as never, local: new MemoryStorage() as never }, reviewPersistence: memoryPersistence() });
  const model = sidecarModel('process-plant');
  svc.setModel(model, 'process-plant');
  for (const f of ['Trade', 'Placement', 'Material', 'Phase', 'Orientation', 'ClassRepair'] as const) svc.setFacetEnabled(f, false);
  svc.review.setReviewer('RF');
  const g = model.elements[0]!.globalId;
  const trade: FacetResult = { facet: 'Trade', code: 'MECH', label: 'Mechanical (HVAC)', confidence: 0.55, source: 'model', model: 'm1', needsReview: true, fields: {}, probabilities: { MECH: 0.55, PLUMB: 0.3, ELEC: 0.15 } };
  svc.facetStore.set(g, { Trade: trade });
  const role: ConcreteFacetResult = { facet: 'ConcreteElement', code: 'BEAM', label: 'Beam', confidence: 0.5, source: 'rule', needsReview: true, fields: {} };
  svc.concreteStore.set(g, { ConcreteElement: role });
  return { svc, g, model };
}

describe('facet decisions in the review log', () => {
  it('a confirmation is pending, then a commit makes the result human with no review', () => {
    const { svc, g } = setup();
    const ref = { id: 'Trade', family: 'facet' as const };
    const p = svc.review.proposeFacet(ref, g, { action: 'confirm', item: `facet:Trade:${g}` })!;
    expect(p).toMatchObject({ action: 'confirm', before: { code: 'MECH', source: 'model' }, after: { code: 'MECH', source: 'human', confidence: 1 } });
    expect(svc.review.pendingCount()).toBe(1);
    expect(svc.review.facetDecision(g, 'Trade')).toBe('confirmed');
    expect(svc.facetsOf(g).Trade!.needsReview).toBe(true); // nothing changes until the commit
    const c = svc.review.commit('walk');
    expect(c.changes).toEqual([]);
    expect(c.facetChanges).toHaveLength(1);
    const r = svc.facetsOf(g).Trade!;
    expect(r).toMatchObject({ code: 'MECH', source: 'human', needsReview: false, confidence: 1 });
    expect(r.model).toBeUndefined();
    expect(svc.review.pendingCount()).toBe(0);
  });

  it('a correction by candidate carries via, takes the new code and keeps the probabilities', () => {
    const { svc, g } = setup();
    svc.review.proposeFacet({ id: 'Trade', family: 'facet' }, g, { action: 'correct', code: 'PLUMB', item: 'i1', via: 'runner-up', comment: 'pipes' });
    const c = svc.review.commit();
    expect(c.facetChanges![0]).toMatchObject({ facet: 'Trade', action: 'correct', via: 'runner-up', comment: 'pipes', after: { code: 'PLUMB', source: 'human' } });
    expect(svc.facetsOf(g).Trade).toMatchObject({ code: 'PLUMB', label: 'Plumbing', source: 'human', needsReview: false });
    expect(svc.facetsOf(g).Trade!.probabilities).toBeDefined();
  });

  it('unsure keeps the review flag and a confidence of 0.75; a code outside the list is refused', () => {
    const { svc, g } = setup();
    svc.review.proposeFacet({ id: 'Trade', family: 'facet' }, g, { action: 'confirm', item: 'i', unsure: true });
    svc.review.commit();
    expect(svc.facetsOf(g).Trade).toMatchObject({ source: 'human', confidence: 0.75, needsReview: true });
    expect(() => svc.review.proposeFacet({ id: 'Trade', family: 'facet' }, g, { action: 'correct', code: 'NOPE', item: 'j' })).toThrow(/not a Trade code/);
  });

  it('concrete: the role is corrected, a measured set without a code list can only be confirmed', () => {
    const { svc, g } = setup();
    svc.review.proposeFacet({ id: 'ConcreteElement', family: 'concrete' }, g, { action: 'correct', code: 'DOWNSTAND_BEAM', item: 'k' });
    svc.review.commit();
    expect(svc.concreteOf(g).ConcreteElement).toMatchObject({ code: 'DOWNSTAND_BEAM', source: 'human', needsReview: false });
    svc.concreteStore.set(g, { ...svc.concreteOf(g), ConcreteGeometry: { facet: 'ConcreteGeometry', code: 'ESTIMATED', label: 'Estimated', confidence: 0.5, source: 'geometry', needsReview: true, fields: {} } });
    expect(() => svc.review.proposeFacet({ id: 'ConcreteGeometry', family: 'concrete' }, g, { action: 'correct', code: 'MEASURED', item: 'l' })).toThrow(/no code list/);
    expect(svc.review.proposeFacet({ id: 'ConcreteGeometry', family: 'concrete' }, g, { action: 'confirm', item: 'l' })).not.toBeNull();
  });

  it('undo takes back the newest pending item, classification or facet', () => {
    const { svc, g } = setup();
    svc.review.proposeFacet({ id: 'Trade', family: 'facet' }, g, { action: 'confirm', item: 'a' });
    svc.review.proposeFacet({ id: 'ConcreteElement', family: 'concrete' }, g, { action: 'confirm', item: 'b' });
    expect(svc.review.lastPendingItem()).toBe('b');
    svc.review.undoPending('b');
    expect(svc.review.lastPendingItem()).toBe('a');
    expect(svc.review.pendingCount()).toBe(1);
    expect(svc.review.activity.undone).toBe(1);
  });

  it('a revert puts the earlier facet result back; a re-run of the facets keeps a decision', async () => {
    const { svc, g } = setup();
    svc.review.proposeFacet({ id: 'Trade', family: 'facet' }, g, { action: 'correct', code: 'ELEC', item: 'a' });
    const c = svc.review.commit();
    expect(svc.facetsOf(g).Trade!.code).toBe('ELEC');
    // a run replaces the store entry with an engine result; the overlay puts the human value back
    svc.facetStore.set(g, { Trade: { facet: 'Trade', code: 'MECH', label: 'Mechanical (HVAC)', confidence: 0.55, source: 'model', needsReview: true, fields: {} } });
    (svc as unknown as { overlayHuman(e: unknown): void }).overlayHuman(svc.review.facetEffective());
    expect(svc.facetsOf(g).Trade).toMatchObject({ code: 'ELEC', source: 'human' });
    const rv = svc.review.revert(c.id);
    expect(rv.commit.facetChanges![0]).toMatchObject({ before: { source: 'human', code: 'ELEC' }, after: { source: 'model', code: 'MECH' } });
    expect(svc.facetsOf(g).Trade).toMatchObject({ code: 'MECH', source: 'model', needsReview: true });
    expect(svc.review.facetEffective().size).toBe(0);
  });

  it('the log stays xray-classification-review/1: facet changes are an optional list that a round trip keeps', () => {
    const { svc, g } = setup();
    svc.review.proposeFacet({ id: 'Trade', family: 'facet' }, g, { action: 'confirm', item: 'a' });
    svc.review.commit();
    const doc = JSON.parse(svc.review.exportLog()) as { schema: string; commits: Array<Record<string, unknown>> };
    expect(doc.schema).toBe(REVIEW_LOG_SCHEMA);
    expect(doc.schema).toBe('xray-classification-review/1');
    expect(doc.commits[0]!['changes']).toEqual([]);
    expect(Array.isArray(doc.commits[0]!['facetChanges'])).toBe(true);
    const p = parseReviewLog(JSON.stringify(doc));
    expect(p.errors).toEqual([]);
    expect(p.doc!.commits[0]!.facetChanges![0]).toMatchObject({ facet: 'Trade', globalId: g });
    // an old log (no facetChanges) parses as before, and a bad facet change is named
    const old = { schema: REVIEW_LOG_SCHEMA, modelFingerprint: 'f', commits: [{ id: 'c1', author: 'x', time: '2026-01-01T00:00:00Z', changes: [] }] };
    expect(parseReviewLog(old).errors).toEqual([]);
    const bad = { ...old, commits: [{ ...old.commits[0], facetChanges: [{ globalId: 'g' }] }] };
    expect(parseReviewLog(bad).errors[0]).toMatch(/facet change 1/);
  });

  it('an empty commit is still refused, and a facet-only commit is allowed', () => {
    const log = new ReviewLog({ modelName: 'm', modelFingerprint: 'f', schemaEdition: 'e' });
    expect(() => log.commit({ author: 'a', changes: [] })).toThrow(/nothing to commit/);
    const c = log.commit({ author: 'a', changes: [], facetChanges: [{ globalId: 'g', facet: 'Trade', before: { code: 'A', source: 'model', confidence: 0.5 }, after: { code: 'B', source: 'human', confidence: 1 }, action: 'correct' }] });
    expect(c.facetChanges).toHaveLength(1);
    expect(log.effectiveFacets().get('g|Trade')?.change.after.code).toBe('B');
  });
});
