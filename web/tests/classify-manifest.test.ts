// The classification manifest builder: counts by source, code and band, review actions, the correction matrix, and the opt-in fields.

import { describe, expect, it } from 'vitest';
import { buildManifest, classifierOf, manifestJson, manifestMarkdown, MANIFEST_SCHEMA, sourceFamily, bandOf } from '../src/classify/manifest';
import type { ManifestInput } from '../src/classify/manifest';
import { defaultDraft, toSettings } from '../src/classify/settings';
import type { ReviewCommit } from '../src/classify/reviewLog';
import type { ClassifyResult } from '../src/classify/types';

const res = (id: string, disc: string, conf: number, source: ClassifyResult['source'], needs = false): ClassifyResult => ({
  id, discipline: { code: disc, label: disc, confidence: conf, probabilities: { [disc]: conf } }, subDiscipline: null, masterformat: null, buildingElement: 1, source, needsReview: needs,
});
const st = (d: string, source: string, confidence = 0.6, sub: string | null = null, division: string | null = null) => ({ discipline: d, subDiscipline: sub, division, source: source as 'model', confidence });
const commit = (id: string, time: string, o: Partial<ReviewCommit> = {}): ReviewCommit => ({ id, author: 'RF', time, note: '', modelName: 'm', modelFingerprint: 'fp', schemaEdition: 'e', changes: [], ...o });

const commits: ReviewCommit[] = [
  commit('c1', '2026-03-01T10:00:00.000Z', {
    changes: [
      { globalId: 'A', before: st('MEC', 'model'), after: st('PLB', 'corrected', 1), action: 'correct', comment: 'pipe', via: 'runner-up' },
      { globalId: 'B', before: st('MEC', 'model'), after: st('PLB', 'corrected', 1), action: 'correct', via: 'candidate' },
      { globalId: 'C', before: st('STR', 'rules', 0.9), after: st('STR', 'confirmed', 1), action: 'confirm' },
      { globalId: 'D', before: st('ELE', 'model', 0.5, 'LGT'), after: st('ELE', 'confirmed', 0.75, 'PWR'), action: 'correct', unsure: true },
    ],
    facetChanges: [
      { globalId: 'A', facet: 'Trade', before: { code: 'MECH', source: 'model', confidence: 0.5 }, after: { code: 'PLUMB', source: 'human', confidence: 1 }, action: 'correct', comment: 'by hand' },
      { globalId: 'C', facet: 'Material', before: { code: 'STEEL', source: 'rule', confidence: 0.9 }, after: { code: 'STEEL', source: 'human', confidence: 1 }, action: 'confirm' },
    ],
  }),
  commit('c2', '2026-03-02T09:00:00.000Z', { author: 'KL', changes: [{ globalId: 'E', before: st('MEC', 'model'), after: st('PLB', 'corrected', 1), action: 'correct' }] }),
  commit('c3', '2026-03-03T09:00:00.000Z', { reverts: 'c2', changes: [{ globalId: 'E', before: st('PLB', 'corrected', 1), after: st('MEC', 'model'), action: 'correct' }] }),
];

const input = (o: Partial<ManifestInput> = {}): ManifestInput => ({
  now: new Date('2026-03-04T00:00:00.000Z'),
  modelName: 'plant.ifc',
  reviewFingerprint: 'fp',
  schema: { id: 'xray-classification-schema/1', title: 'Default', version: '1.2', edition: 'ed1' },
  settings: toSettings({ ...defaultDraft(), provider: 'decision', hfModel: 'org/nli', decisionMode: 'nli' }),
  minConfidence: 0.6,
  facetsOn: ['Trade', 'Material'],
  concreteOn: true,
  results: [res('A', 'PLB', 1, 'corrected'), res('B', 'PLB', 1, 'corrected'), res('C', 'STR', 1, 'confirmed'), res('D', 'ELE', 0.75, 'confirmed', true), res('F', 'MEC', 0.4, 'model', true), res('G', 'MEC', 0.95, 'rules'), res('H', 'ARC', 0.8, 'cache')],
  facetResults: [
    { globalId: 'A', result: { facet: 'Trade', code: 'PLUMB', label: 'Plumbing', confidence: 1, source: 'human', needsReview: false } },
    { globalId: 'F', result: { facet: 'Trade', code: 'MECH', label: 'Mech', confidence: 0.5, source: 'model', needsReview: true } },
    { globalId: 'G', result: { facet: 'Material', code: 'STEEL', label: 'Steel', confidence: 0.95, source: 'geometry', needsReview: false } },
  ],
  commits,
  activity: { skipped: 4, undone: 2 },
  elementInfo: (g) => ({ ifcClass: 'IfcPipeSegment', name: `Pipe ${g}` }),
  ...o,
});

describe('manifest builder', () => {
  it('names the format, the model, the schema, the provider and the thresholds', () => {
    const m = buildManifest(input());
    expect(m.schema).toBe(MANIFEST_SCHEMA);
    expect(m.schema).toBe('xray-classification-manifest/1');
    expect(m.exportedAt).toBe('2026-03-04T00:00:00.000Z');
    expect(m.model).toEqual({ name: 'plant.ifc', reviewFingerprint: 'fp' });
    expect(m.classifier).toMatchObject({ schema: { id: 'xray-classification-schema/1', title: 'Default', version: '1.2', edition: 'ed1' }, provider: 'decision', modelIds: ['org/nli'], decisionMode: 'nli', rulesMode: 'final', minConfidence: 0.6, facetsOn: ['Trade', 'Material'], concreteOn: true });
  });

  it('counts the results by source family, code, confidence band and review need', () => {
    const c = buildManifest(input()).classification;
    expect(c.total).toBe(7);
    expect(c.bySource).toEqual({ rule: 1, model: 2, human: 4 }); // rules; model and cache; corrected and confirmed
    expect(c.bySourceDetail).toEqual({ cache: 1, confirmed: 2, corrected: 2, model: 1, rules: 1 });
    expect(c.byCode[0]).toEqual({ code: 'MEC', count: 2 }); // ties by code: MEC and PLB both 2
    expect(c.byCode.map((x) => x.code)).toEqual(['MEC', 'PLB', 'ARC', 'ELE', 'STR']);
    expect(c.byConfidenceBand).toEqual([{ band: '<0.50', count: 1 }, { band: '0.50-0.74', count: 0 }, { band: '0.75-0.89', count: 2 }, { band: '>=0.90', count: 4 }]);
    expect(c.needsReview).toBe(2);
    expect(buildManifest(input({ topN: 2 })).classification.byCode).toHaveLength(2);
  });

  it('counts the facets in total and by facet', () => {
    const f = buildManifest(input()).facets;
    expect(f.total).toBe(3);
    expect(f.bySource).toEqual({ rule: 1, model: 1, human: 1 }); // geometry counts as measured, with the rules
    expect(f.needsReview).toBe(1);
    expect(Object.keys(f.byFacet)).toEqual(['Material', 'Trade']);
    expect(f.byFacet['Trade']!.byCode).toEqual([{ code: 'MECH', count: 1 }, { code: 'PLUMB', count: 1 }]);
  });

  it('counts the decisions that stand: a reverted commit and its reversal are left out', () => {
    const a = buildManifest(input()).review.actions;
    expect(a).toEqual({ confirmed: 2, corrected: 4, runnerUp: 1, candidate: 1, unsure: 1, facetConfirmed: 1, facetCorrected: 1, commitsReverted: 1, skippedThisSession: 4, undoneThisSession: 2 });
    const r = buildManifest(input()).review;
    expect(r.commits).toBe(3);
    expect(r.reviewers).toBe(2);
    expect(r.firstDecision).toBe('2026-03-01T10:00:00.000Z');
    expect(r.lastDecision).toBe('2026-03-01T10:00:00.000Z'); // c2 was reverted and c3 is the reversal
  });

  it('builds the from-to matrix of corrections, most frequent first, classification and facets apart', () => {
    const mx = buildManifest(input()).review.matrix;
    expect(mx.classification).toEqual([{ from: 'MEC', to: 'PLB', count: 2 }, { from: 'ELE/LGT', to: 'ELE/PWR', count: 1 }]);
    expect(mx.facets).toEqual([{ facet: 'Trade', from: 'MECH', to: 'PLUMB', count: 1 }]);
    expect(mx.truncated).toBe(false);
  });

  it('has no per-element list and no reviewer names by default', () => {
    const m = buildManifest(input());
    expect(m.corrections).toBeUndefined();
    expect(m.reviewerNames).toBeUndefined();
    expect(m.options).toEqual({ perElement: false, reviewerNames: false, topN: 10 });
    const text = manifestJson(m);
    expect(text).not.toContain('RF');
    expect(text).not.toContain('KL');
    expect(text).not.toContain('Pipe A');
    expect(text).not.toContain('globalId');
    expect(manifestMarkdown(m)).not.toContain('RF');
  });

  it('lists the human corrections element by element with the option, one row per changed part, without names', () => {
    const m = buildManifest(input({ perElement: true }));
    const rows = m.corrections!;
    expect(rows.map((r) => `${r.globalId}:${r.kind}:${r.part}`)).toEqual(['A:classification:discipline', 'A:facet:Trade', 'B:classification:discipline', 'D:classification:subDiscipline']);
    expect(rows[0]).toEqual({ globalId: 'A', ifcClass: 'IfcPipeSegment', name: 'Pipe A', kind: 'classification', part: 'discipline', before: { code: 'MEC', confidence: 0.6, source: 'model' }, after: { code: 'PLB' }, action: 'correct', via: 'runner-up', note: 'pipe', time: '2026-03-01T10:00:00.000Z' });
    expect(rows[1]).toMatchObject({ part: 'Trade', before: { code: 'MECH', source: 'model', confidence: 0.5 }, after: { code: 'PLUMB' }, note: 'by hand' });
    expect(rows.every((r) => r.reviewer === undefined)).toBe(true);
    expect(manifestJson(m)).not.toContain('"RF"');
    // confirmations are not in the list, and neither is the reverted correction of E
    expect(rows.some((r) => r.globalId === 'C' || r.globalId === 'E')).toBe(false);
  });

  it('adds reviewer names only with their own option', () => {
    const m = buildManifest(input({ perElement: true, reviewerNames: true }));
    expect(m.reviewerNames).toEqual(['KL', 'RF']);
    expect(m.corrections![0]!.reviewer).toBe('RF');
    expect(buildManifest(input({ reviewerNames: true })).corrections).toBeUndefined();
  });

  it('never holds an API key, a token or an endpoint', () => {
    const s = toSettings({ ...defaultDraft(), provider: 'jev', endpoint: 'https://example.test/v1?key=SECRET123', model: 'jev-1' });
    const text = manifestJson(buildManifest(input({ settings: s, perElement: true, reviewerNames: true })));
    expect(text).not.toContain('SECRET123');
    expect(text).not.toContain('example.test');
    expect(text).toContain('jev-1');
    expect(text).not.toMatch(/apikey|api_key|token|authorization|bearer/i);
  });

  it('says the same in Markdown', () => {
    const md = manifestMarkdown(buildManifest(input({ perElement: true })));
    expect(md).toContain('# Classification manifest: plant.ifc');
    expect(md).toContain('xray-classification-manifest/1');
    expect(md).toContain('| MEC | PLB | 2 |');
    expect(md).toContain('Confirmed 2');
    expect(md).toContain('4 corrections element by element');
  });

  it('maps sources and bands', () => {
    expect(['rules', 'rule', 'geometry', 'ifc', 'cache', 'model', 'batch-learned', 'manual', 'confirmed', 'corrected', 'human'].map(sourceFamily)).toEqual(['rule', 'rule', 'rule', 'rule', 'model', 'model', 'model', 'human', 'human', 'human', 'human']);
    expect([0.1, 0.5, 0.74, 0.75, 0.89, 0.9, 1].map(bandOf)).toEqual(['<0.50', '0.50-0.74', '0.50-0.74', '0.75-0.89', '0.75-0.89', '>=0.90', '>=0.90']);
    expect(classifierOf(toSettings({ ...defaultDraft(), provider: 'decision', decisionMode: 'embed', embedModel: 'org/emb' }))).toEqual({ provider: 'decision', modelIds: ['org/emb'], decisionMode: 'embed' });
    expect(classifierOf(toSettings({ ...defaultDraft(), provider: 'off' }))).toEqual({ provider: 'off', modelIds: [], decisionMode: null });
  });

  it('an empty review gives zeros and null times', () => {
    const m = buildManifest(input({ commits: [], results: [], facetResults: [] }));
    expect(m.review).toMatchObject({ commits: 0, firstDecision: null, lastDecision: null });
    expect(m.classification.total).toBe(0);
  });
});
