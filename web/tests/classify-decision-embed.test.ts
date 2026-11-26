// The label mapping of the NLI models (entailment / not_entailment, entailment / neutral / contradiction) and the embed mode
// (label prototypes): the scoring maths are pure functions, and the provider runs against a fake feature-extraction pipeline.

import { describe, expect, it } from 'vitest';
import {
  checkNliConfig, createDecisionProvider, DECISION_MODELS, DEFAULT_HYPOTHESES, nliLabelIds, optionPhrase,
  cosineSim, EMBED_MODELS, embedModelInfo, embedScores, embedYes, negation, normaliseVec, softmaxTemperature, tensorRows, describeEmbedModel,
} from '../src/classify/providers/decision';
import type { TransformersModule } from '../src/classify/providers/decision';
import { providerId, toSettings, defaultDraft, validateSettings } from '../src/classify';

describe('NLI label mapping', () => {
  it('maps the zero-shot labels (entailment / not_entailment) as binary', () => {
    expect(nliLabelIds({ entailment: 0, not_entailment: 1 })).toEqual({ entailmentId: 0, againstId: 1, binary: true });
    expect(nliLabelIds({ not_entailment: 0, entailment: 1 })).toEqual({ entailmentId: 1, againstId: 0, binary: true });
  });
  it('maps the plain NLI labels, whatever their order and case', () => {
    expect(nliLabelIds({ ENTAILMENT: 0, Neutral: 1, Contradiction: 2 })).toEqual({ entailmentId: 0, againstId: 2, binary: false });
    expect(nliLabelIds({ contradiction: 0, neutral: 1, entailment: 2 })).toEqual({ entailmentId: 2, againstId: 0, binary: false });
  });
  it('prefers contradiction over not_entailment when both exist', () => {
    expect(nliLabelIds({ entailment: 0, not_entailment: 1, contradiction: 2 })?.againstId).toBe(2);
  });
  it('refuses a model without entailment or without anything to set it against', () => {
    expect(nliLabelIds({ positive: 0, negative: 1 })).toBeNull();
    expect(nliLabelIds({ entailment: 0, neutral: 1 })).toBeNull();
    expect(nliLabelIds(undefined)).toBeNull();
  });
  it('checkNliConfig accepts the ModernBERT zero-shot and NLI configs', () => {
    const zs = checkNliConfig({ architectures: ['ModernBertForSequenceClassification'], id2label: { 0: 'entailment', 1: 'not_entailment' }, label2id: { entailment: 0, not_entailment: 1 } });
    expect(zs).toMatchObject({ ok: true, entailmentId: 0, againstId: 1, binary: true });
    const nli = checkNliConfig({ architectures: ['ModernBertForSequenceClassification'], id2label: { 0: 'entailment', 1: 'neutral', 2: 'contradiction' } });
    expect(nli).toMatchObject({ ok: true, entailmentId: 0, againstId: 2, binary: false });
  });
  it('checkNliConfig refuses a bare backbone (Von ONNX is a ModernBertModel without a head)', () => {
    expect(checkNliConfig({ architectures: ['ModernBertModel'], id2label: { 0: 'entailment', 1: 'neutral', 2: 'contradiction' } }).ok).toBe(false);
  });
  it('every catalog id is a repository id with sizes', () => {
    for (const m of [...DECISION_MODELS, ...EMBED_MODELS]) {
      expect(m.id).toMatch(/^[\w.-]+\/[\w.-]+$/);
      expect(Object.keys(m.sizesMB).length).toBeGreaterThan(0);
    }
  });
});

describe('embed scoring maths', () => {
  it('normalises and takes cosines', () => {
    expect(normaliseVec([3, 4])).toEqual([0.6, 0.8]);
    expect(normaliseVec([0, 0])).toEqual([0, 0]);
    expect(cosineSim([1, 0], [1, 0])).toBeCloseTo(1);
    expect(cosineSim([1, 0], [0, 5])).toBeCloseTo(0);
    expect(cosineSim([2, 0], [-1, 0])).toBeCloseTo(-1);
  });
  it('softmax with a temperature sums to 1 and sharpens as it falls', () => {
    const hot = softmaxTemperature([0.5, 0.4, 0.1], 1);
    const cold = softmaxTemperature([0.5, 0.4, 0.1], 0.05);
    expect(hot.reduce((a, b) => a + b, 0)).toBeCloseTo(1);
    expect(cold.reduce((a, b) => a + b, 0)).toBeCloseTo(1);
    expect(cold[0]!).toBeGreaterThan(hot[0]!);
    expect(softmaxTemperature([], 0.1)).toEqual([]);
    expect(softmaxTemperature([1, 0], 0)[0]!).toBeCloseTo(1); // a zero temperature is nearly argmax, not NaN
  });
  it('embedScores: probabilities follow the cosines, logits are cosine / T', () => {
    const s = embedScores([1, 0], [[1, 0], [0.6, 0.8], [0, 1]], 0.1);
    expect(s.cosines[0]).toBeCloseTo(1);
    expect(s.cosines[1]).toBeCloseTo(0.6);
    expect(s.probs.reduce((a, b) => a + b, 0)).toBeCloseTo(1);
    expect(s.probs[0]!).toBeGreaterThan(s.probs[1]!);
    expect(s.probs[1]!).toBeGreaterThan(s.probs[2]!);
    expect(s.logits[0]).toBeCloseTo(10);
    const e = Math.exp(0.6 / 0.1 - 10) + 1 + Math.exp(-10);
    expect(s.probs[0]).toBeCloseTo(1 / e);
  });
  it('embedYes: the statement against its negation', () => {
    const y = embedYes([1, 0], [1, 0], [0, 1], 0.1);
    expect(y.p).toBeGreaterThan(0.99);
    expect(y.logit).toBeCloseTo(10);
    expect(embedYes([1, 0], [0, 1], [1, 0], 0.1).p).toBeLessThan(0.01);
    expect(embedYes([1, 1], [1, 0], [0, 1], 0.1).p).toBeCloseTo(0.5);
    expect(negation('The element is a wall.')).toBe('It is not true that the element is a wall.');
  });
  it('tensorRows reads a flat [n, d] tensor', () => {
    expect(tensorRows(new Float32Array([1, 2, 3, 4, 5, 6]), [2, 3])).toEqual([[1, 2, 3], [4, 5, 6]]);
  });
  it('describes embed models', () => {
    expect(describeEmbedModel('onnx-community/granite-embedding-97m-multilingual-r2-ONNX', 'q8')).toContain('98 MB (q8)');
    expect(describeEmbedModel('a/b')).toContain('a/b');
    expect(embedModelInfo('onnx-community/embeddinggemma-300m-ONNX')?.queryPrefix).toContain('query');
  });
});

// A fake feature-extraction pipeline: 3 axes, the text decides the vector ("duct" -> axis 0, "beam" -> axis 1, else axis 2).
function fakeLib(calls: string[][] = []): TransformersModule {
  const vec = (t: string): number[] => (/duct|mechanical/i.test(t) ? [1, 0.1, 0] : /beam|structural/i.test(t) ? [0.1, 1, 0] : [0, 0.1, 1]);
  return {
    env: {},
    pipeline: async (task: string) => {
      expect(task).toBe('feature-extraction');
      const pipe = async (texts: string[], opts: { pooling: string; normalize: boolean }) => {
        calls.push(texts);
        expect(opts.normalize).toBe(true);
        const rows = texts.map(vec);
        return { data: new Float32Array(rows.flat()), dims: [rows.length, 3] };
      };
      return pipe as never;
    },
  } as unknown as TransformersModule;
}

describe('the embed mode of the provider', () => {
  const state = { class: 'IfcDuctSegment', name: 'Supply duct' };
  const q = { type: 'choice' as const, instructions: 'Choose.', criteria: { MEC: 'Mechanical. Ducts and fans.', STR: 'Structural. Beams and columns.', ARC: 'Architectural. Walls.' } };
  const opts = { model: 'MoritzLaurer/deberta-v3-xsmall-zeroshot-v1.1-all-33', mode: 'embed' as const, embedModel: EMBED_MODELS[0]!.id, temperature: 0.1, device: 'wasm' as const, dtype: 'q8' as const, hfEndpoint: 'https://huggingface.co', hypothesis: { ...DEFAULT_HYPOTHESES }, gpu: async () => ({ present: false, adapter: false, f16: false }) };

  it('returns probabilities that sum to 1, the best option, and logits for calibration', async () => {
    const calls: string[][] = [];
    const p = createDecisionProvider({ ...opts, loadLib: async () => fakeLib(calls) });
    const r = await p.decide(state, { pick: q }, new AbortController().signal);
    expect(r.model).toBe(`decision:embed:${EMBED_MODELS[0]!.id}`);
    const a = r.answers['pick']!;
    if (a.type !== 'choice') throw new Error('choice expected');
    expect(a.choice).toBe('MEC');
    expect(Object.values(a.probabilities).reduce((x, y) => x + y, 0)).toBeCloseTo(1);
    expect(a.confidence).toBe(a.probabilities['MEC']);
    expect(Object.keys(a.logits ?? {})).toEqual(['MEC', 'STR', 'ARC']);
    // the option texts are embedded once: a second element does not embed them again
    const before = calls.length;
    await p.decide({ class: 'IfcBeam', name: 'Beam' }, { pick: q }, new AbortController().signal);
    const docCalls = calls.slice(before).filter((c) => c.length > 1);
    expect(docCalls).toHaveLength(0);
    expect((await p.decide({ class: 'IfcBeam', name: 'beam' }, { pick: q }, new AbortController().signal)).answers['pick']).toMatchObject({ choice: 'STR' });
  });

  it('answers a yes/no question with p(yes) and a logit', async () => {
    const p = createDecisionProvider({ ...opts, loadLib: async () => fakeLib() });
    const r = await p.decide(state, { yes: { type: 'noul', instructions: 'It is a mechanical duct.' } }, new AbortController().signal);
    const a = r.answers['yes']!;
    if (a.type !== 'noul') throw new Error('noul expected');
    expect(a.noul).toBeGreaterThanOrEqual(0);
    expect(a.noul).toBeLessThanOrEqual(1);
    expect(typeof a.logit).toBe('number');
  });

  it('puts the model prefixes on the element and the options', async () => {
    const calls: string[][] = [];
    const p = createDecisionProvider({ ...opts, embedModel: 'onnx-community/embeddinggemma-300m-ONNX', loadLib: async () => fakeLib(calls) });
    await p.decide(state, { pick: q }, new AbortController().signal);
    expect(calls[0]![0]).toMatch(/^task: search result \| query: Element class IfcDuctSegment/);
    expect(calls[1]!.every((t) => t.startsWith('title: none | text: '))).toBe(true);
    expect(optionPhrase(q.criteria.MEC)).toContain('Mechanical');
  });
});

describe('settings and identity of the embed mode', () => {
  it('round-trips decisionMode and embedModel and keys the cache by model and temperature', () => {
    const d = { ...defaultDraft(), provider: 'decision' as const, decisionMode: 'embed' as const, embedModel: EMBED_MODELS[1]!.id, embedTemperature: 0.03 };
    const s = toSettings(d);
    expect(s).toMatchObject({ provider: 'decision', decisionMode: 'embed', embedModel: EMBED_MODELS[1]!.id, embedTemperature: 0.03 });
    expect(providerId(s)).toBe(`decision:embed:${EMBED_MODELS[1]!.id}@T0.03`);
    expect(providerId(toSettings({ ...d, decisionMode: 'nli' }))).toMatch(/^decision:MoritzLaurer\//);
  });
  it('validates the new settings', () => {
    const ok = validateSettings({ provider: 'decision', decisionMode: 'embed', embedModel: 'a/b', embedTemperature: 0.1 });
    expect(ok.errors).toEqual([]);
    expect(ok.warnings.join(' ')).toContain('not one of the tested');
    const bad = validateSettings({ provider: 'decision', decisionMode: 'x', embedModel: 'nope' });
    expect(bad.errors).toHaveLength(2);
    expect(bad.settings).toMatchObject({ decisionMode: 'nli' });
  });
});
