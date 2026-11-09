// The decision provider (a zero-shot NLI model with transformers.js) against a FAKE transformers module: the mapping of
// options to hypotheses, probabilities and codes, the noul answer from entailment, batching, premise truncation, device and
// data type selection, the checks of the model id and of a custom model, the token, the cache and the service. No real model,
// no network, no WebGPU.

import { beforeEach, describe, expect, it } from 'vitest';
import { classifyInputs, defaultDraft, defaultSchema, providerId, toSettings, validateSettings } from '../src/classify';
import { choiceQuestion, noulQuestion } from '../src/classify/jevAdapter';
import type { ChoiceAnswer, NoulAnswer } from '../src/classify/jevAdapter';
import { mainQuestions, subQuestions } from '../src/classify/questions';
import { ClassifyService } from '../src/classify/service';
import {
  buildPremise, checkNliConfig, chooseRuntime, clearModelCache, createDecisionProvider, DECISION_DEFAULT_MODEL, DECISION_MODELS, DEFAULT_HYPOTHESES, DEFAULT_PREMISE_TOKENS,
  hfModelProblem, humanizeClass, hypothesisProblem, inspectModel, modelCacheInfo, optionPhrase, probeGpu, progressTracker, softmax, TRANSFORMERS_CDN_URL, TRANSFORMERS_VERSION,
} from '../src/classify/providers/decision';
import type { CacheStorageLike, DecisionOptions, GpuProbe, TransformersModule } from '../src/classify/providers/decision';
import { MemoryStorage } from '../src/selectionSets';
import * as fake from '../bench/fake-transformers.mjs';
import { jsonResponse, sidecarModel } from './classify-helpers';

const lib = fake as unknown as TransformersModule;
const SIGNAL = new AbortController().signal;
const NO_GPU: GpuProbe = { present: false, adapter: false, f16: false };
const GPU: GpuProbe = { present: true, adapter: true, f16: true };
const GPU_NO_F16: GpuProbe = { present: true, adapter: true, f16: false };
const HF = 'https://huggingface.co';

function make(over: Partial<DecisionOptions> = {}) {
  return createDecisionProvider({
    model: DECISION_DEFAULT_MODEL, device: 'auto', dtype: 'auto', hfEndpoint: HF, hypothesis: { ...DEFAULT_HYPOTHESES },
    loadLib: async () => lib, gpu: async () => NO_GPU, ...over,
  });
}

const DUCT = { class: 'IfcDuctSegment', name: 'Duct 300x200', type: { class: 'IfcDuctSegmentType', name: 'Duct rect 300x200' }, building_context: true };
const choice = (a: unknown): ChoiceAnswer => a as ChoiceAnswer;

beforeEach(() => fake.__reset());

describe('the pinned library and the model list', () => {
  it('loads transformers.js from an exact pinned version on the CDN, never a range', () => {
    expect(TRANSFORMERS_VERSION).toMatch(/^\d+\.\d+\.\d+$/);
    expect(TRANSFORMERS_CDN_URL).toBe(`https://cdn.jsdelivr.net/npm/@huggingface/transformers@${TRANSFORMERS_VERSION}/dist/transformers.min.js`);
    expect(TRANSFORMERS_CDN_URL).not.toMatch(/[\^~*]|@latest/);
  });

  it('lists models with sizes, the default first, all valid ids', () => {
    expect(DECISION_MODELS[0]!.id).toBe(DECISION_DEFAULT_MODEL);
    expect(DECISION_DEFAULT_MODEL).toBe('MoritzLaurer/deberta-v3-xsmall-zeroshot-v1.1-all-33');
    for (const m of DECISION_MODELS) {
      expect(hfModelProblem(m.id), m.id).toBeNull();
      expect(Object.keys(m.sizesMB).length, m.id).toBeGreaterThan(0);
    }
    expect(DECISION_MODELS.find((m) => m.id.includes('deberta-v3-base-zeroshot-v1.1'))!.sizesMB.q8).toBe(244);
  });
});

describe('choice questions: options become hypotheses, probabilities and codes', () => {
  it('maps each option code to a probability that sums to 1, with confidence = the top probability', async () => {
    const p = make();
    const q = mainQuestions(defaultSchema());
    const a = await p.decide(DUCT, q, SIGNAL);
    expect(a.model).toBe(`decision:${DECISION_DEFAULT_MODEL}`);
    const d = choice(a.answers['discipline']);
    const codes = defaultSchema().disciplines.map((x) => x.code);
    expect(Object.keys(d.probabilities)).toEqual(codes); // every option, in order, under its code
    expect(Object.values(d.probabilities).reduce((s, x) => s + x, 0)).toBeCloseTo(1, 10);
    expect(d.choice).toBe('MEC');
    expect(d.confidence).toBe(d.probabilities['MEC']);
    expect(Math.max(...Object.values(d.probabilities))).toBe(d.confidence);
    const m = choice(a.answers['masterformat']);
    expect(Object.keys(m.probabilities)).toHaveLength(35);
    expect(Object.values(m.probabilities).reduce((s, x) => s + x, 0)).toBeCloseTo(1, 10);
    expect(m.choice).toBe('23'); // HVAC
  });

  it('softmaxes the entailment logits over all options (multi_label: false), not each option alone', async () => {
    const p = make();
    const q = { pick: choiceQuestion('x', { MEC: 'Mechanical. Ducts and fans.', ARC: 'Architectural. Walls and doors.', PLB: 'Plumbing. Pipes.' }) };
    const a = choice((await p.decide(DUCT, q, SIGNAL)).answers['pick']);
    const batch = fake.__log.batches[0]!;
    const logits = batch.hyps.map((h) => fake.entailLogit(batch.premise, h));
    const want = softmax(logits);
    ['MEC', 'ARC', 'PLB'].forEach((c, i) => expect(a.probabilities[c]).toBeCloseTo(want[i]!, 10));
  });

  it('builds the hypothesis from the template, the label and a short description', async () => {
    const p = make();
    const q = mainQuestions(defaultSchema());
    await p.decide(DUCT, q, SIGNAL);
    const hyps = fake.__log.batches.flatMap((b) => b.hyps);
    const mec = hyps.find((h) => h.includes('Mechanical and HVAC'))!;
    expect(mec).toMatch(/^This building element belongs to the Mechanical and HVAC \(heating, ventilation and air conditioning/);
    expect(mec).toMatch(/\) discipline\.$/);
    const desc = /\((.*)\) discipline\.$/.exec(mec)![1]!;
    expect(desc.length).toBeLessThanOrEqual(90);
    expect(hyps.some((h) => /^The work of this building element falls under /.test(h))).toBe(true);
  });

  it('uses a template of the settings, and the id of the cache changes with it', async () => {
    const hypothesis = { ...DEFAULT_HYPOTHESES, discipline: 'The trade {} owns this part.' };
    const p = make({ hypothesis });
    await p.decide(DUCT, { discipline: choiceQuestion('x', { MEC: 'Mechanical. Ducts.', ARC: 'Architectural. Walls.' }) }, SIGNAL);
    expect(fake.__log.batches[0]!.hyps[0]).toBe('The trade Mechanical (ducts) owns this part.');
    const base = providerId(toSettings({ ...defaultDraft(), provider: 'decision' }));
    const custom = providerId(toSettings({ ...defaultDraft(), provider: 'decision', hypothesis }));
    expect(base).toBe(`decision:${DECISION_DEFAULT_MODEL}`);
    expect(custom).toMatch(new RegExp(`^decision:${DECISION_DEFAULT_MODEL}@h[0-9a-f]{8}$`));
  });

  it('shortens option texts at a word boundary and keeps the title', () => {
    expect(optionPhrase('Mechanical and HVAC. Heating, ventilation and air conditioning: ducts, fans.')).toBe('Mechanical and HVAC (heating, ventilation and air conditioning: ducts, fans)');
    expect(optionPhrase('Plain title only')).toBe('Plain title only');
    expect(optionPhrase('Title. Description that is cut', false)).toBe('Title');
    const long = optionPhrase(`Title. ${'word '.repeat(60)}`);
    expect(long.length).toBeLessThanOrEqual('Title ()'.length + 90);
    expect(long.endsWith(' )')).toBe(false);
  });

  it('rejects a score question and an empty choice in plain words', async () => {
    const p = make();
    await expect(p.decide(DUCT, { s: { type: 'score', instructions: 'x', criteria: ['a', 'b'] } }, SIGNAL)).rejects.toThrow(/does not answer score questions/);
    await expect(p.decide(DUCT, { c: choiceQuestion('x', {}) }, SIGNAL)).rejects.toThrow(/has no options/);
  });
});

describe('noul questions: p(yes) from entailment against contradiction', () => {
  it('is softmax([contradiction, entailment])[1] of the statement', async () => {
    const p = make({ model: 'Xenova/nli-deberta-v3-xsmall' }); // three labels: contradiction, entailment, neutral
    const q = { building_element: noulQuestion('This element is part of a building (not of a road).') };
    const yes = (await p.decide({ ...DUCT, building_context: true }, q, SIGNAL)).answers['building_element'] as NoulAnswer;
    const no = (await p.decide({ ...DUCT, building_context: false }, q, SIGNAL)).answers['building_element'] as NoulAnswer;
    expect(yes.type).toBe('noul');
    expect(yes.noul).toBeCloseTo(1 / (1 + Math.exp(-8)), 10); // logits +4 against -4
    expect(no.noul).toBeCloseTo(1 / (1 + Math.exp(8)), 10);
    expect(yes.noul).toBeGreaterThan(0.99);
    expect(no.noul).toBeLessThan(0.01);
  });

  it('uses not_entailment as the "against" score of a binary zero-shot model', async () => {
    // the fake gives the binary layout {entailment: 0, not_entailment: 1} to ids with "zeroshot" in them
    const p = make({ model: 'MoritzLaurer/deberta-v3-base-zeroshot-v1.1-all-33' });
    const a = (await p.decide(DUCT, { building_element: noulQuestion('This element is part of a building (not of a road).') }, SIGNAL)).answers['building_element'] as NoulAnswer;
    expect(a.noul).toBeGreaterThan(0.99);
    const c = choice((await p.decide(DUCT, { x: choiceQuestion('x', { MEC: 'Mechanical. Ducts.', PLB: 'Plumbing. Pipes.' }) }, SIGNAL)).answers['x']);
    expect(c.choice).toBe('MEC'); // the indexes of entailment (0) and not_entailment (1) were read from the model labels
  });

  it('keeps a probability inside 0 and 1 for any statement', async () => {
    const p = make();
    for (const s of ['Anything at all.', 'This element is part of a building.', '']) {
      const a = (await p.decide(DUCT, { s: noulQuestion(s || 'x') }, SIGNAL)).answers['s'] as NoulAnswer;
      expect(a.noul).toBeGreaterThanOrEqual(0);
      expect(a.noul).toBeLessThanOrEqual(1);
    }
  });
});

describe('passes: batches, the pair cache, one request per signature', () => {
  const main = mainQuestions(defaultSchema()); // 11 disciplines + 1 statement + 35 divisions = 47 pairs

  it('runs the 47 pairs of the first request in 6 batches of 8 on WASM, 3 batches of 16 on WebGPU', async () => {
    const wasm = make();
    await wasm.decide(DUCT, main, SIGNAL);
    expect(wasm.stats()).toMatchObject({ requests: 1, pairs: 47, passes: 6, cachedPairs: 0 });
    expect(fake.__log.batches.map((b) => b.size)).toEqual([8, 8, 8, 8, 8, 7]); // questions share batches: not 3 + 1 + 5 = 9 passes
    fake.__reset();
    const gpu = make({ gpu: async () => GPU });
    await gpu.decide(DUCT, main, SIGNAL);
    expect(gpu.stats()).toMatchObject({ pairs: 47, passes: 3 });
    expect(fake.__log.batches.map((b) => b.size)).toEqual([16, 16, 15]);
  });

  it('shares the premise: every pair of a request has the same premise', async () => {
    const p = make();
    await p.decide(DUCT, main, SIGNAL);
    expect(new Set(fake.__log.batches.map((b) => b.premise)).size).toBe(1);
  });

  it('answers a repeated pair from the pair cache (no pass)', async () => {
    const p = make();
    await p.decide(DUCT, main, SIGNAL);
    const again = await p.decide(DUCT, main, SIGNAL);
    expect(p.stats()).toMatchObject({ requests: 2, pairs: 47, passes: 6, cachedPairs: 47 });
    expect(choice(again.answers['discipline']).choice).toBe('MEC');
  });

  it('reports the cost of a run of the pipeline per signature (synth5k, rules off)', async () => {
    const m = sidecarModel('synth5k');
    const { buildInputs } = await import('../src/classify');
    const inputs = buildInputs(m, m.elements.map((e) => e.id));
    const p = make();
    const r = await classifyInputs(inputs, { schema: defaultSchema(), provider: p, rules: false, concurrency: 1 });
    const st = p.stats();
    expect(r.stats.failed).toBe(0);
    expect(r.stats.signatures).toBe(9);
    // 1 first request and at most 1 sub-discipline request per signature; about 47 + 5 to 12 pairs and 7 to 8 passes each
    expect(st.requests).toBeGreaterThanOrEqual(9);
    expect(st.requests).toBeLessThanOrEqual(18);
    expect(st.pairs / 9).toBeGreaterThan(47);
    expect(st.pairs / 9).toBeLessThan(47 + 13);
    expect(st.passes / 9).toBeGreaterThanOrEqual(6);
    expect(st.passes / 9).toBeLessThanOrEqual(9);
    expect(r.results.every((x) => x.model?.startsWith('decision:'))).toBe(true);
  });

  it('asks the sub-discipline question with only the sub-codes of the discipline', async () => {
    const p = make();
    const q = subQuestions(defaultSchema(), ['MEC'])!;
    const a = choice((await p.decide(DUCT, q, SIGNAL)).answers['sub_discipline']);
    const subs = defaultSchema().disciplines.find((d) => d.code === 'MEC')!.subDisciplines.map((s) => s.code);
    expect(Object.keys(a.probabilities)).toEqual(subs);
    expect(p.stats().pairs).toBe(subs.length);
  });

  it('works through the public pipeline call when the pipeline has no tokenizer and model (one pair per pass)', async () => {
    const calls: Array<{ labels: string[]; multi: boolean | undefined; tpl: string | undefined }> = [];
    const pipe = Object.assign(
      async (text: string, labels: string[], o: { hypothesis_template?: string; multi_label?: boolean } = {}) => {
        calls.push({ labels, multi: o.multi_label, tpl: o.hypothesis_template });
        const raw = labels.map((l) => fake.entailLogit(text, l));
        const sc = o.multi_label || labels.length === 1 ? raw.map((x) => 1 / (1 + Math.exp(-2 * x))) : softmax(raw);
        const order = sc.map((s, i) => [s, i] as const).sort((a, b) => b[0] - a[0]);
        return { labels: order.map(([, i]) => labels[i]!), scores: order.map(([s]) => s) };
      },
      {},
    );
    const p = make({ loadLib: async () => ({ env: {}, pipeline: async () => pipe as never }) });
    const q = { pick: choiceQuestion('x', { MEC: 'Mechanical. Ducts.', ARC: 'Architectural. Walls.' }), b: noulQuestion('This element is part of a building.') };
    const a = await p.decide(DUCT, q, SIGNAL);
    const c = choice(a.answers['pick']);
    expect(c.choice).toBe('MEC');
    expect(c.probabilities['MEC']! + c.probabilities['ARC']!).toBeCloseTo(1, 10);
    expect(calls[0]).toMatchObject({ multi: false, tpl: '{}' });
    expect(calls[1]).toMatchObject({ multi: true });
    expect(p.stats()).toMatchObject({ pairs: 3, passes: 3 });
  });

  it('stops between batches when the signal aborts', async () => {
    const p = make();
    const ctl = new AbortController();
    const first = p.decide(DUCT, main, ctl.signal);
    ctl.abort();
    await expect(first).rejects.toMatchObject({ name: 'AbortError' });
  });
});

describe('the premise: what the model reads', () => {
  const rich = {
    class: 'IfcPipeSegment', name: 'Pipe riser L0',
    type: { class: 'IfcPipeSegmentType', name: 'Pipe PVC 100', psets: { P: { Reference: 'P-100' } } },
    psets: { Attr: { PredefinedType: 'RIGIDSEGMENT', ObjectType: 'Pipe PVC 100' }, Pset_X: { IsExternal: false, NoiseValue: 12 } },
    material: 'PVC', systems: ['Domestic Water'], hierarchy: ['IfcBuildingStorey: Level 0'],
    parents: [{ class: 'IfcSlab', name: 'Slab L0' }], building_context: true,
  };

  it('puts the class, the type and the name first, then properties, system, material, storey and parent', () => {
    const t = buildPremise(rich);
    expect(t.startsWith('Element class IfcPipeSegment (pipe segment).')).toBe(true);
    const at = (s: string): number => t.indexOf(s);
    expect([at('Type Pipe PVC 100'), at('Name Pipe riser'), at('Properties:'), at('System Domestic Water'), at('Material PVC'), at('Storey Level 0'), at('Hosted in slab Slab L0'), at('inside a building')].every((x) => x >= 0)).toBe(true);
    expect(at('Type')).toBeLessThan(at('Name'));
    expect(at('Name')).toBeLessThan(at('Properties:'));
    expect(at('Properties:')).toBeLessThan(at('System'));
    expect(at('System')).toBeLessThan(at('Material'));
    expect(at('Material')).toBeLessThan(at('Storey'));
    expect(at('Storey')).toBeLessThan(at('Hosted in'));
    expect(t).toContain('PredefinedType RIGIDSEGMENT');
    expect(t).not.toContain('NoiseValue'); // not a key property
  });

  it('is cut to the token budget at a field boundary, class first', () => {
    const budget = 40; // tokens, about 120 characters
    const t = buildPremise(rich, budget);
    expect(t.length).toBeLessThanOrEqual(budget * 3);
    expect(t.startsWith('Element class IfcPipeSegment')).toBe(true);
    expect(t).not.toContain('Hosted in'); // the last fields go first
    expect(t.endsWith('.')).toBe(true);
    expect(buildPremise(rich).length).toBeLessThanOrEqual(DEFAULT_PREMISE_TOKENS * 3);
  });

  it('shortens a single huge field and keeps the class when the budget is tiny', () => {
    const long = { class: 'IfcWall', name: 'N'.repeat(2000) };
    const t = buildPremise(long, 30);
    expect(t.length).toBeLessThanOrEqual(30 * 3);
    expect(t.startsWith('Element class IfcWall (wall).')).toBe(true);
    const tiny = buildPremise({ class: 'IfcBuildingElementProxyAndSomethingVeryVeryLong', name: 'x' }, 5);
    expect(tiny.length).toBeGreaterThan(0);
    expect(tiny.length).toBeLessThanOrEqual(20 * 3); // the floor of the budget is 20 tokens
  });

  it('handles a state with only a class, and humanizes class names', () => {
    expect(buildPremise({ class: 'IfcSlab' })).toBe('Element class IfcSlab (slab).');
    expect(buildPremise({})).toBe('');
    expect(humanizeClass('IfcBuildingElementProxy')).toBe('building element proxy');
    expect(humanizeClass('IfcHVACFan')).toBe('hvac fan');
  });

  it('is what the model gets: the premise of the batches is the premise of the state, cut to the budget', async () => {
    const p = make({ maxPremiseTokens: 50 });
    await p.decide(rich, { x: choiceQuestion('x', { A: 'Alpha. a', B: 'Beta. b' }) }, SIGNAL);
    expect(fake.__log.batches[0]!.premise).toBe(buildPremise(rich, 50));
  });
});

describe('device and data type', () => {
  it('auto: WebGPU with fp16 when the adapter has shader-f16 and the model has fp16', () => {
    expect(chooseRuntime('auto', 'auto', 'Xenova/nli-deberta-v3-xsmall', GPU)).toMatchObject({ device: 'webgpu', dtype: 'fp16', note: '' });
    expect(chooseRuntime('auto', 'auto', 'Some/custom-model', GPU)).toMatchObject({ device: 'webgpu', dtype: 'fp16', fallbacks: ['fp32'] });
  });

  it('auto: fp32 on WebGPU when there is no shader-f16, or the model has no fp16 weights', () => {
    expect(chooseRuntime('auto', 'auto', 'Xenova/nli-deberta-v3-xsmall', GPU_NO_F16)).toMatchObject({ device: 'webgpu', dtype: 'fp32' });
    expect(chooseRuntime('auto', 'auto', DECISION_DEFAULT_MODEL, GPU)).toMatchObject({ device: 'webgpu', dtype: 'fp32' }); // 284 MB, no fp16 file
  });

  it('auto: WASM with q8 and a plain "slower, no WebGPU" note when navigator.gpu is missing', () => {
    const r = chooseRuntime('auto', 'auto', DECISION_DEFAULT_MODEL, NO_GPU);
    expect(r).toMatchObject({ device: 'wasm', dtype: 'q8' });
    expect(r.note).toMatch(/^Slower: this browser has no WebGPU/);
    expect(chooseRuntime('auto', 'auto', 'MoritzLaurer/deberta-v3-base-zeroshot-v2.0', NO_GPU).dtype).toBe('fp32'); // only fp32 weights
    expect(chooseRuntime('auto', 'auto', DECISION_DEFAULT_MODEL, { present: true, adapter: false, f16: false }).note).toMatch(/no GPU adapter/);
  });

  it('a forced device is honoured or refused with a plain message, never switched silently', () => {
    expect(chooseRuntime('wasm', 'auto', DECISION_DEFAULT_MODEL, GPU)).toMatchObject({ device: 'wasm', dtype: 'q8' });
    expect(chooseRuntime('webgpu', 'q4', 'Some/custom', GPU)).toMatchObject({ device: 'webgpu', dtype: 'q4' });
    expect(() => chooseRuntime('webgpu', 'auto', DECISION_DEFAULT_MODEL, NO_GPU)).toThrow(/set to WebGPU, but this browser has no WebGPU. Set the device to Auto or WASM/);
    expect(() => chooseRuntime('webgpu', 'auto', DECISION_DEFAULT_MODEL, { present: true, adapter: false, f16: false })).toThrow(/no GPU adapter/);
  });

  it('probes navigator.gpu', async () => {
    expect(await probeGpu(undefined)).toEqual(NO_GPU);
    expect(await probeGpu({})).toEqual(NO_GPU);
    expect(await probeGpu({ gpu: { requestAdapter: async () => ({ features: { has: (f: string) => f === 'shader-f16' } }) } })).toEqual(GPU);
    expect(await probeGpu({ gpu: { requestAdapter: async () => null } })).toEqual({ present: true, adapter: false, f16: false });
    expect(await probeGpu({ gpu: { requestAdapter: async () => { throw new Error('x'); } } })).toEqual({ present: true, adapter: false, f16: false });
  });

  it('passes the device and the data type to the pipeline, and reports them', async () => {
    const wasm = make();
    const rep = await wasm.load();
    expect(rep).toMatchObject({ device: 'wasm', dtype: 'q8' });
    expect(rep.note).toMatch(/Slower/);
    expect(fake.__log.pipelines.at(-1)).toMatchObject({ task: 'zero-shot-classification', model: DECISION_DEFAULT_MODEL, device: 'wasm', dtype: 'q8' });
    const gpu = make({ gpu: async () => GPU, model: 'Xenova/nli-deberta-v3-xsmall' });
    expect(await gpu.load()).toMatchObject({ device: 'webgpu', dtype: 'fp16' });
    expect(fake.__log.pipelines.at(-1)).toMatchObject({ device: 'webgpu', dtype: 'fp16' });
    expect(rep.labels).toEqual(['entailment', 'not_entailment']);
  });

  it('maps the endpoint to env.remoteHost, with one trailing slash', async () => {
    const env: Record<string, unknown> = {};
    const p = make({ hfEndpoint: 'https://mirror.example.org/hf///', loadLib: async () => ({ env, pipeline: lib.pipeline }) });
    await p.load();
    expect(env['remoteHost']).toBe('https://mirror.example.org/hf/');
  });

  it('retries fp32 when an auto data type has no weights, and explains a forced one', async () => {
    const seen: string[] = [];
    const flaky: TransformersModule = {
      env: {},
      pipeline: async (t, m, o) => {
        seen.push(String(o?.['dtype']));
        if (o?.['dtype'] !== 'fp32') throw new Error('Could not locate file: "onnx/model_quantized.onnx".');
        return lib.pipeline(t, m, o);
      },
    };
    const auto = make({ loadLib: async () => flaky });
    expect((await auto.load()).dtype).toBe('fp32');
    expect(seen).toEqual(['q8', 'fp32']);
    const forced = make({ loadLib: async () => flaky, dtype: 'q4' });
    await expect(forced.load()).rejects.toThrow(/has no q4 weights at https:\/\/huggingface.co.*Choose another data type/);
  });

  it('does not repeat a failing load for every request, but load() tries again', async () => {
    let n = 0;
    const down: TransformersModule = { env: {}, pipeline: async () => { n++; throw new Error('Failed to fetch'); } };
    const p = make({ loadLib: async () => down });
    await expect(p.decide(DUCT, { x: choiceQuestion('x', { A: 'a. a', B: 'b. b' }) }, SIGNAL)).rejects.toThrow(/Could not download the model from https:\/\/huggingface.co/);
    await expect(p.decide(DUCT, { x: choiceQuestion('x', { A: 'a. a', B: 'b. b' }) }, SIGNAL)).rejects.toThrow(/Could not download/);
    expect(n).toBe(1);
    await expect(p.load()).rejects.toThrow(/Could not download/);
    expect(n).toBe(2);
  });

  it('says plainly when the library cannot be loaded', async () => {
    const p = make({ loadLib: async () => { throw new Error('boom'); } });
    await expect(p.load()).rejects.toThrow(/boom/);
  });
});

describe('model ids and settings', () => {
  it('checks the format of a Hugging Face model id', () => {
    for (const ok of ['MoritzLaurer/deberta-v3-xsmall-zeroshot-v1.1-all-33', 'Xenova/nli-deberta-v3-xsmall', 'org_1/my.model-2', 'a/b']) expect(hfModelProblem(ok), ok).toBeNull();
    for (const bad of ['', '   ', 'no-slash', 'a/b/c', 'https://huggingface.co/a/b', '/a', 'a/', '../a/b', 'a/..', 'a b/c', 'a/b?x=1', 'a/b#c', 'a\\b', 'owner/na me', 'a/'.repeat(5)]) expect(hfModelProblem(bad), bad).not.toBeNull();
    expect(hfModelProblem('https://huggingface.co/a/b')).toMatch(/web address/);
    expect(hfModelProblem(42)).toMatch(/empty/);
  });

  it('validates the decision settings with a plain message and a default for each bad value', () => {
    const c = validateSettings({ provider: 'decision', hfModel: 'not a model', device: 'cuda', dtype: 'int3', hfEndpoint: 'ftp://x', hypothesis: { discipline: 'no placeholder', bogus: 'x {}', sub_discipline: 'two {} and {}' } });
    expect(c.settings).toMatchObject({ provider: 'decision', hfModel: DECISION_DEFAULT_MODEL, device: 'auto', dtype: 'auto', hfEndpoint: 'https://huggingface.co' });
    expect((c.settings as { hypothesis: unknown }).hypothesis).toEqual(DEFAULT_HYPOTHESES);
    expect(c.errors).toHaveLength(6);
    expect(c.errors[0]).toMatch(/^hfModel: "not a model" is not a model id\. Use owner\/name/);
    expect(c.errors.join(' ')).toMatch(/device must be one of auto, webgpu, wasm/);
    expect(c.errors.join(' ')).toMatch(/dtype must be one of auto, fp32, fp16, q8, q4/);
    expect(c.errors.join(' ')).toMatch(/hfEndpoint "ftp:\/\/x"|must use https/);
    expect(c.errors.join(' ')).toMatch(/discipline hypothesis must contain \{\} exactly once, where the option goes\. It has 0/);
    expect(c.errors.join(' ')).toMatch(/sub_discipline hypothesis must contain \{\} exactly once.*It has 2/);
    expect(c.warnings.join(' ')).toMatch(/Unknown hypothesis "bogus"/);
  });

  it('accepts a custom model, device, data type, endpoint and hypotheses', () => {
    const c = validateSettings({
      provider: 'decision', hfModel: 'org/custom-nli', device: 'wasm', dtype: 'q4', hfEndpoint: 'https://mirror.example.org/', hypothesis: { masterformat: 'It is work of {}.' },
    });
    expect(c.errors).toEqual([]);
    expect(c.settings).toMatchObject({ hfModel: 'org/custom-nli', device: 'wasm', dtype: 'q4', hfEndpoint: 'https://mirror.example.org' });
    expect((c.settings as { hypothesis: { masterformat: string; discipline: string } }).hypothesis.masterformat).toBe('It is work of {}.');
    expect((c.settings as { hypothesis: { discipline: string } }).hypothesis.discipline).toBe(DEFAULT_HYPOTHESES.discipline);
  });

  it('allows a same-origin proxy path as the endpoint and warns about plain http', () => {
    expect(validateSettings({ provider: 'decision', hfEndpoint: '/hf' }).errors).toEqual([]);
    expect(validateSettings({ provider: 'decision', hfEndpoint: 'http://models.example.org' }).warnings.join(' ')).toMatch(/without encryption/);
    expect(validateSettings({ provider: 'decision', hfEndpoint: 'http://localhost:8080' }).warnings).toEqual([]);
    expect(validateSettings({ provider: 'decision', hfEndpoint: 'https://user:pw@x.org' }).errors.join(' ')).toMatch(/must not contain a user name or password/);
  });

  it('refuses a token in the settings', () => {
    const c = validateSettings({ provider: 'decision', hfToken: 'hf_secret', hf_token: 'x', huggingfaceToken: 'y' });
    expect(c.errors.filter((e) => /looks like a secret/.test(e))).toHaveLength(3);
    expect(JSON.stringify(c.settings)).not.toContain('hf_secret');
  });

  it('has the decision provider first among the local ones', async () => {
    const { PROVIDERS } = await import('../src/classify');
    expect(PROVIDERS.indexOf('decision')).toBe(1);
    expect(PROVIDERS.indexOf('decision')).toBeLessThan(PROVIDERS.indexOf('webllm'));
    expect(hypothesisProblem('a {} b', 'x')).toBeNull();
  });
});

describe('a model that is not a zero-shot or NLI model', () => {
  const cfgFetch = (cfg: unknown, status = 200, api?: unknown): typeof fetch =>
    (async (url: string) => {
      if (String(url).includes('/api/models/')) return api ? jsonResponse(api) : new Response('{}', { status: 404 });
      return status === 200 ? jsonResponse(cfg) : new Response('', { status });
    }) as unknown as typeof fetch;

  it('accepts entailment with contradiction, and entailment with not_entailment', () => {
    expect(checkNliConfig({ architectures: ['DebertaV2ForSequenceClassification'], id2label: { 0: 'contradiction', 1: 'entailment', 2: 'neutral' }, label2id: { contradiction: 0, entailment: 1, neutral: 2 } })).toMatchObject({ ok: true, entailmentId: 1, againstId: 0, binary: false });
    expect(checkNliConfig({ id2label: { 0: 'entailment', 1: 'not_entailment' }, label2id: { entailment: 0, not_entailment: 1 } })).toMatchObject({ ok: true, entailmentId: 0, againstId: 1, binary: true });
    expect(checkNliConfig({ id2label: { 0: 'ENTAILMENT', 1: 'NEUTRAL', 2: 'CONTRADICTION' } })).toMatchObject({ ok: true, entailmentId: 0, againstId: 2 });
  });

  it('explains plainly for a sentiment model, a language model and a config without labels', () => {
    const s = checkNliConfig({ id2label: { 0: 'NEGATIVE', 1: 'POSITIVE' } }, '"org/sentiment"');
    expect(s.ok).toBe(false);
    expect(s.message).toMatch(/"org\/sentiment" is not a zero-shot or NLI model: its labels are negative, positive, and none is "entailment"\./);
    expect(s.message).toMatch(/needs a sequence-classification \(NLI\) model with an "entailment" label/);
    const llm = checkNliConfig({ architectures: ['Qwen2ForCausalLM'], model_type: 'qwen2' }, '"org/chat"');
    expect(llm.ok).toBe(false);
    expect(llm.message).toMatch(/is not a classifier \(its architecture is Qwen2ForCausalLM\), so it cannot decide among options/);
    expect(checkNliConfig({ id2label: { 0: 'entailment', 1: 'neutral' } }).message).toMatch(/no "contradiction" or "not_entailment" label/);
    expect(checkNliConfig({}).ok).toBe(false);
    expect(checkNliConfig(null).message).toMatch(/no readable config.json/);
  });

  it('is checked from config.json before any weights are downloaded', async () => {
    const bad = await inspectModel('org/chat', { endpoint: HF, fetchImpl: cfgFetch({ architectures: ['LlamaForCausalLM'] }) });
    expect(bad.ok).toBe(false);
    let libLoaded = 0;
    const p = make({ model: 'org/chat', fetchImpl: cfgFetch({ architectures: ['LlamaForCausalLM'] }), loadLib: async () => { libLoaded++; return lib; } });
    await expect(p.load()).rejects.toThrow(/is not a classifier/);
    expect(libLoaded).toBe(0); // no library, no model, no download
    expect(fake.__log.pipelines).toHaveLength(0);
  });

  it('says what is wrong for a missing model, a gated model and an unreachable host', async () => {
    expect((await inspectModel('org/none', { endpoint: HF, fetchImpl: cfgFetch(null, 404) })).message).toMatch(/"org\/none" was not found at https:\/\/huggingface.co\. Check the spelling/);
    expect((await inspectModel('org/gated', { endpoint: HF, fetchImpl: cfgFetch(null, 401) })).message).toMatch(/needs a Hugging Face token \(HTTP 401\)/);
    expect((await inspectModel('org/gated', { endpoint: HF, fetchImpl: cfgFetch(null, 403) })).message).toMatch(/accept its terms/);
    expect((await inspectModel('org/x', { endpoint: HF, fetchImpl: cfgFetch(null, 500) })).message).toMatch(/answered HTTP 500/);
    const down = (async () => { throw new TypeError('Failed to fetch'); }) as unknown as typeof fetch;
    expect((await inspectModel('org/x', { endpoint: 'https://mirror.example.org/', fetchImpl: down })).message).toMatch(/Could not reach https:\/\/mirror.example.org \(Failed to fetch\)/);
  });

  it('reads the file sizes of a good custom model from the Hub API', async () => {
    const api = { siblings: [{ rfilename: 'onnx/model.onnx', size: 738_563_249 }, { rfilename: 'onnx/model_quantized.onnx', size: 244_291_155 }, { rfilename: 'README.md', size: 10 }] };
    const r = await inspectModel('org/nli', { endpoint: HF, fetchImpl: cfgFetch({ id2label: { 0: 'entailment', 1: 'not_entailment' } }, 200, api) });
    expect(r).toMatchObject({ ok: true, sizesMB: { fp32: 739, q8: 244 } });
    const noApi = await inspectModel('org/nli', { endpoint: HF, fetchImpl: cfgFetch({ id2label: { 0: 'entailment', 1: 'not_entailment' } }) });
    expect(noApi.ok).toBe(true);
    expect(noApi.sizesMB).toBeUndefined();
  });

  it('checks the labels of the loaded model too (the authority)', async () => {
    const wrong: TransformersModule = {
      env: {},
      pipeline: async () => {
        const pipe = await lib.pipeline('zero-shot-classification', 'x/nli', {});
        (pipe as unknown as { model: { config: { label2id: Record<string, number> } } }).model.config.label2id = { LABEL_0: 0, LABEL_1: 1 };
        return pipe;
      },
    };
    const p = make({ model: DECISION_DEFAULT_MODEL, loadLib: async () => wrong });
    await expect(p.load()).rejects.toThrow(/is not a zero-shot or NLI model: its labels are label_0, label_1/);
  });

  it('skips the pre-check for a model of the list (they were checked against the Hub)', async () => {
    let fetched = 0;
    const p = make({ fetchImpl: (async () => { fetched++; return jsonResponse({}); }) as unknown as typeof fetch });
    await p.load();
    expect(fetched).toBe(0);
  });
});

describe('the Hugging Face token', () => {
  const TOKEN = 'hf_ABCDEFGHIJKLMNOP0123456789';

  it('is sent to the Hugging Face endpoint only, and env.fetch is restored after the load', async () => {
    const sent: Array<{ url: string; auth: string | null }> = [];
    const base = async (url: string | URL, init: Record<string, unknown> = {}): Promise<unknown> => {
      sent.push({ url: String(url), auth: new Headers(init['headers'] as HeadersInit | undefined).get('Authorization') });
      return new Response('{}');
    };
    const env: Record<string, unknown> = { fetch: base };
    const spy: TransformersModule = {
      env,
      pipeline: async (t, m, o) => {
        const f = env['fetch'] as (u: string, i?: Record<string, unknown>) => Promise<unknown>;
        await f('https://huggingface.co/org/nli/resolve/main/config.json', { headers: { Accept: 'x' } });
        await f('https://cdn.jsdelivr.net/npm/onnxruntime-web@1.0.0/dist/ort.wasm');
        await f('https://huggingface.co.evil.example/org/nli/resolve/main/config.json');
        return lib.pipeline(t, m, o);
      },
    };
    const p = make({ loadLib: async () => spy, token: () => TOKEN });
    await p.load();
    expect(sent.map((s) => [new URL(s.url).host, s.auth])).toEqual([
      ['huggingface.co', `Bearer ${TOKEN}`],
      ['cdn.jsdelivr.net', null],
      ['huggingface.co.evil.example', null], // a look-alike host gets no token
    ]);
    expect(env['fetch']).toBe(base); // the wrapper is gone
  });

  it('sends nothing when there is no token, and the token is not in the report, the answers or the stats', async () => {
    const env: Record<string, unknown> = { fetch: async () => new Response('') };
    const original = env['fetch'];
    const p = make({ loadLib: async () => ({ env, pipeline: lib.pipeline }), token: () => null });
    await p.load();
    expect(env['fetch']).toBe(original);
    const q = make({ token: () => TOKEN });
    const rep = await q.load();
    const a = await q.decide(DUCT, mainQuestions(defaultSchema()), SIGNAL);
    expect(JSON.stringify([rep, a, q.stats(), q.runtime()])).not.toContain(TOKEN);
  });

  it('is used for the config check of a custom model, to the endpoint only', async () => {
    const auth: Array<string | null> = [];
    const f = (async (url: string, init: RequestInit) => {
      auth.push(new Headers(init.headers).get('Authorization'));
      return String(url).includes('/api/') ? new Response('{}', { status: 404 }) : jsonResponse({ id2label: { 0: 'entailment', 1: 'not_entailment' } });
    }) as unknown as typeof fetch;
    await inspectModel('org/gated', { endpoint: HF, token: TOKEN, fetchImpl: f });
    expect(auth).toEqual([`Bearer ${TOKEN}`, `Bearer ${TOKEN}`]);
    await inspectModel('org/gated', { endpoint: HF, fetchImpl: f });
    expect(auth.slice(2)).toEqual([null, null]);
  });
});

describe('download progress and the browser cache', () => {
  it('adds the progress of all files into one figure', () => {
    const seen: Array<{ progress: number; loadedMB: number; totalMB: number; text: string }> = [];
    const t = progressTracker((p) => seen.push(p));
    t({ status: 'initiate', file: 'a.onnx' });
    t({ status: 'progress', file: 'a.onnx', loaded: 25_000_000, total: 100_000_000 });
    t({ status: 'progress', file: 'config.json', loaded: 1_000, total: 1_000 });
    t({ status: 'progress', file: 'a.onnx', loaded: 50_000_000, total: 100_000_000 });
    t({ status: 'done', file: 'a.onnx' });
    t({ status: 'ready' });
    t(null);
    expect(seen[0]!.text).toBe('Starting the download');
    expect(seen[1]).toMatchObject({ loadedMB: 25, totalMB: 100 });
    expect(seen[3]!.progress).toBeCloseTo(0.5, 2);
    expect(seen.at(-1)).toMatchObject({ progress: 1, loadedMB: 100, text: 'Downloading 100 of 100 MB' });
  });

  it('feeds the progress of the load to the callback', async () => {
    const got: number[] = [];
    const p = make({ onProgress: (x) => got.push(x.progress) });
    const rep = await p.load();
    expect(got.at(-1)).toBe(1);
    expect(got).toEqual([...got].sort((a, b) => a - b));
    expect(rep.sizeMB).toBe(87);
  });

  const fakeCaches = (entries: Record<string, number | null>): CacheStorageLike & { deleted: string[] } => {
    const deleted: string[] = [];
    return {
      deleted,
      has: async (n) => n === 'transformers-cache' && !deleted.includes(n),
      open: async () => ({
        keys: async () => Object.keys(entries).map((url) => ({ url })),
        match: async (r) => {
          const url = (r as { url: string }).url;
          const len = entries[url];
          return { headers: { get: (h: string) => (h.toLowerCase() === 'content-length' && len ? String(len) : null) }, clone: () => ({ blob: async () => ({ size: 1234 }) }) };
        },
      }),
      delete: async (n) => { deleted.push(n); return true; },
    };
  };

  it('sums the size of the cached files (Content-Length, else the body) and clears the cache', async () => {
    const c = fakeCaches({ 'https://huggingface.co/a/model.onnx': 87_000_000, 'https://huggingface.co/a/tokenizer.json': null });
    expect(await modelCacheInfo(c)).toEqual({ available: true, files: 2, bytes: 87_001_234 });
    expect(await clearModelCache(c)).toBe(true);
    expect(c.deleted).toEqual(['transformers-cache']);
    expect(await modelCacheInfo(c)).toEqual({ available: true, files: 0, bytes: 0 });
    expect(await modelCacheInfo(null)).toEqual({ available: false, files: 0, bytes: 0 });
    expect(await clearModelCache(null)).toBe(false);
  });
});

describe('the service with the decision provider', () => {
  function service(extra: Partial<ConstructorParameters<typeof ClassifyService>[0]> = {}) {
    const mem = () => new MemoryStorage() as never;
    return new ClassifyService({ storage: mem(), keyStorages: { session: mem(), local: mem() }, decisionLoad: async () => lib, decisionGpu: async () => NO_GPU, cacheStorage: null, ...extra });
  }

  it('classifies synth5k with the rules off, one decision per signature, and counts the passes', async () => {
    fake.__reset();
    const svc = service();
    svc.setModel(sidecarModel('synth5k'), 'synth5k');
    svc.patch({ provider: 'decision' });
    const r = await svc.classify('all', { rules: false });
    expect(r).toHaveLength(5000);
    const st = svc.stats();
    expect(st.signatures).toBe(9);
    expect(st.models).toMatchObject({ [`decision:${DECISION_DEFAULT_MODEL}`]: expect.any(Number) });
    expect(st.bySource.model + st.bySource.cache).toBe(5000);
    const ds = svc.decisionStats()!;
    expect(ds.requests).toBe(st.calls);
    expect(ds.pairs).toBeGreaterThan(9 * 47);
    // a second run is answered by the signature cache: no new pass
    const passes = ds.passes;
    await svc.classify('all', { rules: false });
    expect(svc.decisionStats()!.passes).toBe(passes);
  });

  it('tests the model: load time, device, data type, size and one tiny choice', async () => {
    fake.__reset();
    const svc = service();
    svc.patch({ provider: 'decision' });
    const t = await svc.testModel();
    expect(t.ok).toBe(true);
    expect(t).toMatchObject({ device: 'wasm', dtype: 'q8', model: DECISION_DEFAULT_MODEL, sizeMB: 87 });
    expect(t.choice).toMatchObject({ code: 'MEC' });
    expect(t.choice!.probability).toBeGreaterThan(0.5);
    expect(t.message).toMatch(/Ready: MoritzLaurer\/deberta-v3-xsmall-zeroshot-v1\.1-all-33 on wasm \(q8\) in [\d.]+ s, 87 MB of files\. Test question: chose MEC/);
    expect(t.message).toMatch(/Slower: this browser has no WebGPU/);
    expect(svc.runtimeNote()).toMatch(/Device wasm, data type q8/);
  });

  it('tests a custom model: a model that is not an NLI model never downloads, with a plain message', async () => {
    fake.__reset();
    const f = (async (url: string) => (String(url).includes('/api/') ? new Response('{}', { status: 404 }) : jsonResponse({ architectures: ['GPT2LMHeadModel'] }))) as unknown as typeof fetch;
    const svc = service({ fetchImpl: f });
    const c = svc.patch({ provider: 'decision', hfModel: 'openai-community/gpt2' });
    expect(c.errors).toEqual([]);
    const t = await svc.testModel();
    expect(t.ok).toBe(false);
    expect(t.message).toMatch(/"openai-community\/gpt2" is not a classifier \(its architecture is GPT2LMHeadModel\)/);
    expect(fake.__log.pipelines).toHaveLength(0);
  });

  it('keeps a bad model id out of the settings, with a message', () => {
    const svc = service();
    const c = svc.patch({ provider: 'decision', hfModel: 'https://huggingface.co/a/b' });
    expect(c.errors[0]).toMatch(/web address/);
    expect(svc.settings()).toMatchObject({ hfModel: DECISION_DEFAULT_MODEL });
  });

  it('clears the model cache and frees the loaded model', async () => {
    const entries = { 'https://huggingface.co/a/m.onnx': 5_000_000 };
    let cleared = false;
    const caches: CacheStorageLike = {
      has: async () => !cleared,
      open: async () => ({ keys: async () => (cleared ? [] : Object.keys(entries).map((url) => ({ url }))), match: async () => ({ headers: { get: () => '5000000' }, clone: () => ({ blob: async () => ({ size: 0 }) }) }) }),
      delete: async () => { cleared = true; return true; },
    };
    const svc = service({ cacheStorage: caches });
    svc.patch({ provider: 'decision' });
    expect((await svc.modelCacheInfo()).bytes).toBe(5_000_000);
    await svc.testModel();
    expect(svc.lastLoad).not.toBeNull();
    expect(await svc.clearModelCache()).toBe(true);
    expect(svc.lastLoad).toBeNull();
    expect((await svc.modelCacheInfo()).files).toBe(0);
  });
});
