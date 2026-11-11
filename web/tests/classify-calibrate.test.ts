// Logit scaling: the maths, the fit (a known temperature is recovered from synthetic data), the cache that keeps raw scores so that a
// change of temperature re-scores without the model, the calibration on the rules, and the settings.

import { describe, expect, it } from 'vitest';
import {
  CALIBRATION_MODES, argmax, calibrateAnswers, chooseTemperatures, crossValidate, fitQuestion, fitTemperature, inHeldOut, isIdentity, logOf, measure, nll,
  rawOfAnswer, softmaxT, sigmoidT, answersFromRaw,
} from '../src/classify/calibrate';
import type { Sample } from '../src/classify/calibrate';
import { ClassifyService, MemoryCache, classifyInputs, defaultSchema, validateSettings, buildInputs } from '../src/classify';
import { MemoryStorage } from '../src/selectionSets';
import type { Answers, DecisionModel, Questions } from '../src/classify';
import { collectSamples, fitFromSamples, pickTruths, ruleTruths } from '../src/classify/calibrateRules';
import { rescoreDecision } from '../src/classify/pipeline';
import { sidecarModel } from './classify-helpers';

/** mulberry32: a small seeded generator, so that the synthetic data are the same on every run. */
function rng(seed: number): () => number {
  let s = seed >>> 0;
  return () => {
    s = (s + 0x6d2b79f5) >>> 0;
    let t = s;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const gauss = (r: () => number): number => Math.sqrt(-2 * Math.log(1 - r())) * Math.cos(2 * Math.PI * r());

/** Samples whose labels are drawn from softmax(logits / T0): the model is calibrated at temperature T0 exactly. */
function synthetic(n: number, k: number, T0: number, seed: number): Sample[] {
  const r = rng(seed);
  const out: Sample[] = [];
  for (let i = 0; i < n; i++) {
    const logits = Array.from({ length: k }, () => 3 * gauss(r));
    const p = softmaxT(logits, T0);
    let u = r();
    let label = k - 1;
    for (let j = 0; j < k; j++) { u -= p[j]!; if (u <= 0) { label = j; break; } }
    out.push({ logits, label });
  }
  return out;
}

describe('the scaling maths', () => {
  it('T = 1 is the plain softmax and the result sums to 1', () => {
    const p = softmaxT([1, 2, 3], 1);
    expect(p.reduce((a, b) => a + b, 0)).toBeCloseTo(1, 12);
    expect(p[0]).toBeCloseTo(Math.exp(1) / (Math.exp(1) + Math.exp(2) + Math.exp(3)), 12);
  });
  it('p_i is proportional to exp(l_i / T): T below 1 sharpens, above 1 flattens, the order never changes', () => {
    const l = [0.2, 1.5, -0.7, 1.4];
    const sharp = softmaxT(l, 0.25);
    const flat = softmaxT(l, 4);
    const base = softmaxT(l, 1);
    expect(sharp[1]!).toBeGreaterThan(base[1]!);
    expect(flat[1]!).toBeLessThan(base[1]!);
    expect(argmax(sharp)).toBe(1);
    expect(argmax(flat)).toBe(1);
    // the ratio of two options follows exp(delta / T)
    expect(sharp[1]! / sharp[3]!).toBeCloseTo(Math.exp((1.5 - 1.4) / 0.25), 10);
  });
  it('scales log-probabilities the same way: p_i ∝ exp(log p_i / T)', () => {
    const p = [0.7, 0.2, 0.1];
    const scaled = softmaxT(p.map(logOf), 0.5);
    const direct = p.map((x) => x ** 2);
    const z = direct.reduce((a, b) => a + b, 0);
    scaled.forEach((x, i) => expect(x).toBeCloseTo(direct[i]! / z, 12));
  });
  it('keeps a zero probability finite', () => {
    expect(softmaxT([0, 1, 0].map(logOf), 1).every(Number.isFinite)).toBe(true);
  });
  it('scales a yes/no log-odds with a sigmoid', () => {
    expect(sigmoidT(0, 3)).toBe(0.5);
    expect(sigmoidT(2, 1)).toBeCloseTo(1 / (1 + Math.exp(-2)), 12);
    expect(sigmoidT(2, 0.5)).toBeGreaterThan(sigmoidT(2, 1));
    expect(sigmoidT(-800, 1)).toBe(0);
  });
});

describe('calibrateAnswers', () => {
  const answers: Answers = {
    model: 'm',
    answers: {
      discipline: { type: 'choice', choice: 'A', confidence: 0.5, probabilities: { A: 0.5, B: 0.3, C: 0.2 } },
      building_element: { type: 'noul', noul: 0.8 },
    },
  };
  it('returns the very same object when nothing is scaled', () => {
    expect(calibrateAnswers(answers, {})).toBe(answers);
    expect(calibrateAnswers(answers, { discipline: 1 })).toBe(answers);
    expect(isIdentity({ discipline: 1, masterformat: undefined })).toBe(true);
  });
  it('scales the confidence, keeps the choice, and leaves a question without a temperature alone', () => {
    const c = calibrateAnswers(answers, { discipline: 0.5 });
    const d = c.answers['discipline']!;
    expect(d.type === 'choice' && d.choice).toBe('A');
    expect(d.type === 'choice' && d.confidence).toBeGreaterThan(0.5);
    expect(c.answers['building_element']).toBe(answers.answers['building_element']);
    const n = calibrateAnswers(answers, { building_element: 2 }).answers['building_element']!;
    expect(n.type === 'noul' && n.noul).toBeLessThan(0.8);
    expect(n.type === 'noul' && n.noul).toBeGreaterThan(0.5);
  });
  it('uses the logits of a provider when it gives them', () => {
    const a: Answers = { model: 'm', answers: { discipline: { type: 'choice', choice: 'A', confidence: 0.6, probabilities: { A: 0.6, B: 0.4 }, logits: { A: 5, B: 4 } } } };
    const c = calibrateAnswers(a, { discipline: 0.5 }).answers['discipline']!;
    expect(c.type === 'choice' && c.confidence).toBeCloseTo(softmaxT([5, 4], 0.5)[0]!, 12);
  });
  it('rebuilds answers from raw scores', () => {
    const raw = rawOfAnswer(answers.answers['discipline']!)!;
    expect(raw).toHaveProperty('logits');
    const a = answersFromRaw({ model: 'm', questions: { discipline: raw } }, { discipline: 1 }).answers['discipline']!;
    expect(a.type === 'choice' && a.confidence).toBeCloseTo(0.5, 3);
  });
});

describe('fitting a temperature', () => {
  for (const T0 of [0.3, 1, 2.5]) {
    it(`recovers T = ${T0} from synthetic data that are calibrated at that temperature`, () => {
      const fit = fitTemperature(synthetic(4000, 8, T0, 7));
      expect(fit.T / T0).toBeGreaterThan(0.92);
      expect(fit.T / T0).toBeLessThan(1.08);
      expect(fit.nll).toBeLessThanOrEqual(fit.nllRaw + 1e-9);
    });
  }
  it('lowers the NLL and the ECE of an under-confident model, without changing its accuracy', () => {
    // flat predictions (true T0 = 0.25 means the model's logits are 4 times too small)
    const data = synthetic(3000, 10, 0.25, 11);
    const fit = fitTemperature(data);
    expect(fit.T).toBeLessThan(0.4);
    const before = measure(data, 1, 0.6);
    const after = measure(data, fit.T, 0.6);
    expect(after.accuracy).toBe(before.accuracy);
    expect(after.nll).toBeLessThan(before.nll);
    expect(after.ece).toBeLessThan(before.ece);
    expect(after.ece).toBeLessThan(0.05);
    expect(after.meanConfidence).toBeGreaterThan(before.meanConfidence);
    expect(after.clearShare).toBeGreaterThan(before.clearShare);
  });
  it('makes confidence track accuracy: the answers that clear 0.6 are more accurate than 0.6', () => {
    const data = synthetic(3000, 10, 0.25, 12);
    const T = fitTemperature(data).T;
    const m = measure(data, T, 0.6);
    expect(m.clearAccuracy).toBeGreaterThan(0.6);
    expect(Math.abs(m.accuracy - m.meanConfidence)).toBeLessThan(0.03);
  });
  it('stays inside the bounds and is 1 for too few samples', () => {
    expect(fitTemperature([]).T).toBe(1);
    expect(fitTemperature([{ logits: [1, 0], label: 0 }]).T).toBe(1);
    // perfectly separable and always right: the NLL keeps falling as T falls, so T stops at the lower bound
    const sure: Sample[] = Array.from({ length: 20 }, () => ({ logits: [10, 0, 0], label: 0 }));
    expect(fitTemperature(sure).T).toBeCloseTo(0.05, 3);
    // always wrong: T grows to the upper bound
    const wrong: Sample[] = Array.from({ length: 20 }, () => ({ logits: [10, 0, 0], label: 1 }));
    expect(fitTemperature(wrong).T).toBeCloseTo(50, 3);
  });
  it('minimises the NLL: no nearby temperature does better', () => {
    const data = synthetic(1500, 6, 0.6, 5);
    const T = fitTemperature(data).T;
    for (const f of [0.9, 0.95, 1.05, 1.1]) expect(nll(data, T * f)).toBeGreaterThanOrEqual(nll(data, T) - 1e-12);
  });
  it('reports held-out numbers: the split is by key and the same every time', () => {
    const items = synthetic(600, 6, 0.4, 3).map((sample, i) => ({ key: `sig-${i}`, sample }));
    const a = fitQuestion('discipline', items, 0.6);
    const b = fitQuestion('discipline', items, 0.6);
    expect(a.T).toBe(b.T);
    expect(a.nTrain + a.nTest).toBe(600);
    expect(a.nTest).toBeGreaterThan(120);
    expect(a.nTest).toBeLessThan(240);
    expect(a.after.ece).toBeLessThan(a.before.ece);
    expect(inHeldOut('x', 0.3)).toBe(inHeldOut('x', 0.3));
  });
  it('cross-validation scores every sample with a temperature fitted without it', () => {
    const items = synthetic(400, 6, 0.4, 9).map((sample, i) => ({ key: `s${i}`, sample }));
    const cv = crossValidate('discipline', items, 0.6, 5);
    expect(cv.n).toBe(400);
    expect(cv.foldT).toHaveLength(5);
    expect(cv.T / 0.4).toBeGreaterThan(0.85);
    expect(cv.T / 0.4).toBeLessThan(1.15);
    expect(cv.after.nll).toBeLessThan(cv.before.nll);
  });
});

describe('choosing the temperatures in use', () => {
  const fitted = { temperatures: { discipline: 0.2 }, n: {}, at: '2026-11-09T00:00:00.000Z', source: 'fzk-haus' };
  it('off means no scaling, manual means your numbers, auto the shipped ones, fitted your fit', () => {
    const base = { manual: { discipline: 0.5 }, shipped: { discipline: 0.3, masterformat: 0.4 }, fitted };
    expect(chooseTemperatures({ ...base, mode: 'off' }).temperatures).toEqual({});
    expect(chooseTemperatures({ ...base, mode: 'manual' }).temperatures).toEqual({ discipline: 0.5 });
    expect(chooseTemperatures({ ...base, mode: 'auto' }).temperatures).toEqual({ discipline: 0.3, masterformat: 0.4 });
    expect(chooseTemperatures({ ...base, mode: 'fitted' }).temperatures).toEqual({ discipline: 0.2 });
  });
  it('says so when the fit or the shipped numbers are missing', () => {
    const c = chooseTemperatures({ mode: 'fitted', manual: {}, shipped: null, fitted: null });
    expect(c.temperatures).toEqual({});
    expect(c.note).toMatch(/Calibrate on rules/);
    expect(chooseTemperatures({ mode: 'auto', manual: {}, shipped: null, fitted: null }).note).toMatch(/no shipped temperatures/);
    expect(CALIBRATION_MODES).toEqual(['auto', 'fitted', 'manual', 'off']);
  });
});

// ---------------------------------------------------------------- the cache keeps raw scores

/** A provider with logits: option k of a question has the score `scale * (n - k)`, so the first option wins and the spread is `scale`. */
function logitProvider(scale: number, calls: { n: number }): DecisionModel {
  return {
    provider: 'mock',
    async decide(_state, questions: Questions): Promise<Answers> {
      calls.n++;
      const answers: Answers['answers'] = {};
      for (const [name, q] of Object.entries(questions)) {
        if (q.type === 'choice') {
          const keys = Object.keys(q.criteria);
          const logits = Object.fromEntries(keys.map((k, i) => [k, scale * (keys.length - i)]));
          const p = softmaxT(keys.map((k) => logits[k]!), 1);
          answers[name] = { type: 'choice', choice: keys[0]!, confidence: p[0]!, probabilities: Object.fromEntries(keys.map((k, i) => [k, p[i]!])), logits };
        } else if (q.type === 'noul') answers[name] = { type: 'noul', noul: sigmoidT(scale, 1), logit: scale };
      }
      return { model: 'logit-model', answers };
    },
  };
}

describe('the result cache and calibration', () => {
  const model = sidecarModel('fzk-haus');
  const schema = defaultSchema();
  const inputs = buildInputs(model, model.elements.slice(0, 40).map((e) => e.id));

  it('stores raw scores, applies the temperature on read, and does not run the model again', async () => {
    const calls = { n: 0 };
    const cache = new MemoryCache();
    const provider = logitProvider(0.05, calls); // flat: the top option has well under 0.6
    const flat = await classifyInputs(inputs, { schema, provider, rules: false, cache });
    const callsAfterFirst = calls.n;
    expect(callsAfterFirst).toBeGreaterThan(0);
    const first = flat.results[0]!;
    expect(first.discipline.confidence).toBeLessThan(0.3);
    expect(first.needsReview).toBe(true);
    expect([...cache.entries()][0]![1].raw).toBeDefined();
    // the raw scores are in the cache, a result does not carry them
    expect(first).not.toHaveProperty('raw');

    // sharpen with T = 0.05: the same raw scores now clear the minimum confidence; the cache answers, the model does not run
    const sharp = await classifyInputs(inputs, { schema, provider, rules: false, cache, temperatures: { discipline: 0.05, sub_discipline: 0.05, masterformat: 0.05, building_element: 0.05 } });
    expect(calls.n).toBe(callsAfterFirst);
    const r = sharp.results[0]!;
    expect(r.source).toBe('cache');
    expect(r.discipline.confidence).toBeGreaterThan(0.6);
    expect(r.discipline.code).toBe(first.discipline.code);
    expect(r).not.toHaveProperty('raw');
    expect(sharp.stats.needsReview).toBeLessThan(flat.stats.needsReview);

    // back to no scaling: the first numbers again, from the same cache
    const again = await classifyInputs(inputs, { schema, provider, rules: false, cache });
    expect(again.results[0]!.discipline.confidence).toBeCloseTo(first.discipline.confidence, 6);
    expect(calls.n).toBe(callsAfterFirst);
  });

  it('rescoreDecision leaves a decision without raw scores (a rule, an old entry) as it is', () => {
    const d = { discipline: { code: 'ARC', label: 'Architectural', confidence: 0.9, probabilities: { ARC: 0.9 } }, subDiscipline: null, masterformat: null, buildingElement: 1 };
    expect(rescoreDecision(schema, d, { discipline: 0.1 })).toBe(d);
  });

  it('with temperatures, the sub-discipline question sees the scaled confidence: a sharp discipline asks for one discipline only', async () => {
    const questions: string[][] = [];
    const base = logitProvider(0.05, { n: 0 });
    const spy: DecisionModel = {
      provider: 'mock',
      decide: async (s, q, sig) => {
        if (q['sub_discipline'] && q['sub_discipline'].type === 'choice') questions.push(Object.keys(q['sub_discipline'].criteria));
        return base.decide(s, q, sig);
      },
    };
    await classifyInputs(inputs.slice(0, 3), { schema, provider: spy, rules: false, cache: new MemoryCache() });
    await classifyInputs(inputs.slice(0, 3), { schema, provider: spy, rules: false, cache: new MemoryCache(), temperatures: { discipline: 0.01 } });
    const combined = questions.filter((k) => k.some((x) => x.includes('/')));
    const plain = questions.filter((k) => k.every((x) => !x.includes('/')));
    expect(combined.length).toBeGreaterThan(0); // flat: top-2 combined
    expect(plain.length).toBeGreaterThan(0); // sharp: one discipline
  });
});

describe('calibration on the rules', () => {
  const model = sidecarModel('synth5k');
  const schema = defaultSchema();
  const all = buildInputs(model, model.elements.map((e) => e.id));

  it('takes one truth per signature from the elements that a final rule decides', () => {
    const t = ruleTruths(all, schema);
    expect(t.length).toBeGreaterThan(5);
    expect(new Set(t.map((x) => x.signature)).size).toBe(t.length);
    expect(t.every((x) => schema.disciplines.some((d) => d.code === x.discipline))).toBe(true);
    expect(pickTruths(t, 4)).toHaveLength(4);
    expect(pickTruths(t, 4).map((x) => x.signature)).toEqual(pickTruths(t, 4).map((x) => x.signature));
  });

  it('fits from cached raw scores, and the fit is a number in range with a held-out report', async () => {
    const cache = new MemoryCache();
    // a provider that knows the truth: it puts the rule answer first with a spread, so the fit has something to learn
    const truths = ruleTruths(all, schema);
    const provider: DecisionModel = {
      provider: 'mock',
      async decide(state: Record<string, unknown>, questions: Questions): Promise<Answers> {
        const t = truths.find((x) => x.input.name === state['name'] && x.input.ifcClass === state['class']);
        const answers: Answers['answers'] = {};
        for (const [name, q] of Object.entries(questions)) {
          if (q.type === 'choice') {
            const keys = Object.keys(q.criteria);
            const want = name === 'discipline' ? t?.discipline : name === 'masterformat' ? t?.division : t?.subDiscipline;
            const logits = Object.fromEntries(keys.map((k, i) => [k, (k === want ? 1.2 : 0) + 0.01 * (i % 3)]));
            const p = softmaxT(keys.map((k) => logits[k]!), 1);
            const b = argmax(p);
            answers[name] = { type: 'choice', choice: keys[b]!, confidence: p[b]!, probabilities: Object.fromEntries(keys.map((k, i) => [k, p[i]!])), logits };
          } else if (q.type === 'noul') answers[name] = { type: 'noul', noul: 0.9, logit: 2.2 };
        }
        return { model: 'oracle', answers };
      },
    };
    await classifyInputs(truths.map((t) => t.input), { schema, provider, rules: false, cache });
    const sets = collectSamples(truths, (sig) => cache.get(sig));
    expect(sets.discipline.length).toBeGreaterThan(5);
    const rep = fitFromSamples(sets, { modelId: 'mock:mock-1', source: 'synth5k', minConfidence: 0.6, signatures: truths.length, scored: truths.length });
    const d = rep.questions.find((q) => q.question === 'discipline')!;
    expect(d).toBeDefined();
    expect(rep.temperatures.discipline).toBeGreaterThanOrEqual(0.05);
    expect(rep.temperatures.discipline).toBeLessThanOrEqual(50);
    // the truth is always first with a spread of 1.2: accuracy is 100%, so the fit sharpens (T below 1)
    expect(d.before.accuracy).toBe(1);
    expect(rep.temperatures.discipline!).toBeLessThan(1);
    expect(d.after.meanConfidence).toBeGreaterThan(d.before.meanConfidence);
    expect(d.after.clearShare).toBeGreaterThanOrEqual(d.before.clearShare);
  });
});

describe('calibration settings', () => {
  it('has the four modes and defaults to auto', () => {
    expect(validateSettings(undefined).settings).toMatchObject({ calibration: 'auto', temperatures: {} });
    for (const m of CALIBRATION_MODES) expect(validateSettings({ calibration: m }).settings).toMatchObject({ calibration: m });
  });
  it('refuses an unknown mode and bad temperatures with a plain message and keeps the defaults', () => {
    const c = validateSettings({ calibration: 'sharp', temperatures: { discipline: 0, masterformat: 'x', sub_discipline: 100, other: 1 } });
    expect(c.errors[0]).toBe('calibration must be one of auto, fitted, manual, off. Using "auto".');
    expect(c.errors.filter((e) => /temperatures\.\w+ must be a number from 0.05 to 50/.test(e))).toHaveLength(3);
    expect(c.warnings.join(' ')).toMatch(/Unknown temperature "other"/);
    expect(c.settings).toMatchObject({ calibration: 'auto', temperatures: {} });
  });
  it('keeps good manual temperatures and warns when manual has none', () => {
    const ok = validateSettings({ calibration: 'manual', temperatures: { discipline: 0.4, masterformat: 0.7 } });
    expect(ok.errors).toEqual([]);
    expect(ok.settings).toMatchObject({ calibration: 'manual', temperatures: { discipline: 0.4, masterformat: 0.7 } });
    expect(validateSettings({ calibration: 'manual' }).warnings.join(' ')).toMatch(/no temperature is set/);
    expect(validateSettings({ temperatures: 'x' }).errors[0]).toMatch(/temperatures must be an object/);
  });
});

describe('the service: Calibrate on rules, persistence and the drawer numbers', () => {
  const storages = () => ({ session: new MemoryStorage(), local: new MemoryStorage() });
  const make = (storage = new MemoryStorage(), k = storages()) => {
    const svc = new ClassifyService({ storage: storage as never, keyStorages: { session: k.session as never, local: k.local as never } });
    svc.setModel(sidecarModel('fzk-haus'), 'fzk-haus');
    svc.patch({ provider: 'mock' });
    return { svc, storage, k };
  };

  it('fits on the rules, stores the fit per model id, switches to fitted, and reports before and after', async () => {
    const { svc, storage } = make();
    expect(svc.calibration().label).toMatch(/off \(no shipped numbers/);
    const rep = await svc.calibrateOnRules();
    expect(rep.modelId).toBe('mock:mock-1');
    expect(rep.source).toBe('fzk-haus');
    expect(rep.scored).toBeGreaterThanOrEqual(8);
    expect(rep.questions.some((q) => q.question === 'discipline')).toBe(true);
    for (const q of rep.questions) {
      expect(q.T).toBeGreaterThanOrEqual(0.05);
      expect(q.T).toBeLessThanOrEqual(50);
      expect(q.trainAfter.nll).toBeLessThanOrEqual(q.trainBefore.nll + 1e-9); // the fit minimises the NLL where it was fitted
    }
    expect(svc.settings().calibration).toBe('fitted');
    expect(svc.calibration().label).toMatch(/^fitted on fzk-haus/);
    expect(svc.calibrationStatus().questions.length).toBeGreaterThan(0);
    // persisted per model id, not secret, and not in the settings
    const stored = JSON.parse(storage.getItem('xray.classify.calibration.v1')!) as Record<string, { temperatures: Record<string, number> }>;
    expect(Object.keys(stored)).toEqual(['mock:mock-1']);
    expect(stored['mock:mock-1']!.temperatures['discipline']).toBeCloseTo(rep.temperatures.discipline!, 6);
    expect(JSON.stringify(svc.collect())).not.toContain('temperatures":{"discipline"');
    // a new service on the same storage finds the fit
    const again = make(storage);
    again.svc.patch({ calibration: 'fitted' });
    expect(again.svc.calibration().temperatures.discipline).toBeCloseTo(rep.temperatures.discipline!, 6);
    // forgetting
    svc.forgetFit();
    expect(svc.fits.get('mock:mock-1')).toBeNull();
    expect(svc.calibration().note).toMatch(/Calibrate on rules/);
  });

  it('refuses with a plain message when there is nothing to fit', async () => {
    const { svc } = make();
    svc.patch({ provider: 'off' });
    await expect(svc.calibrateOnRules()).rejects.toThrow(/Choose a decision model first/);
    const empty = new ClassifyService({ storage: null, keyStorages: { session: null, local: null } });
    await expect(empty.calibrateOnRules()).rejects.toThrow(/Load a model first/);
  });

  it('re-scores the results when the mode changes, and the cache id does not change', async () => {
    const { svc } = make();
    svc.patch({ calibration: 'off' });
    await svc.classify('all', { rules: false });
    const before = svc.results().find((r) => r.source === 'model' || r.source === 'cache')!;
    const id = svc.modelId();
    svc.patch({ calibration: 'manual', temperatures: { discipline: 0.2 } });
    const after = svc.results().find((r) => r.id === before.id)!;
    expect(after.discipline.confidence).toBeGreaterThanOrEqual(before.discipline.confidence);
    expect(after.discipline.code).toBe(before.discipline.code);
    expect(svc.modelId()).toBe(id);
    const calls = svc.stats().calls;
    svc.patch({ calibration: 'off' });
    expect(svc.stats().calls).toBe(calls);
    expect(svc.results().find((r) => r.id === before.id)!.discipline.confidence).toBeCloseTo(before.discipline.confidence, 6);
  });
});

describe('shipped temperatures after the truth refit', () => {
  it('keep a per-question record of where each number came from, for the truth-bench models', async () => {
    const { SHIPPED_TEMPERATURES } = await import('../src/classify/calibrationDefaults');
    for (const id of ['decision:MoritzLaurer/deberta-v3-xsmall-zeroshot-v1.1-all-33', 'decision:MoritzLaurer/deberta-v3-base-zeroshot-v2.0', 'd3']) {
      const fit = SHIPPED_TEMPERATURES[id]!;
      expect(fit.n).toBe(114);
      for (const q of ['discipline', 'sub_discipline', 'masterformat', 'building_element'] as const) expect(fit.detail?.[q], `${id} ${q}`).toMatch(/\S/);
      for (const t of Object.values(fit.temperatures)) expect(t).toBeGreaterThanOrEqual(0.05);
    }
    // d3: the discipline question is not scaled any more (it was under-confident on the truth), the sub-discipline is
    expect(SHIPPED_TEMPERATURES['d3']!.temperatures.discipline).toBeUndefined();
    expect(SHIPPED_TEMPERATURES['d3']!.temperatures.sub_discipline).toBe(1.99);
  });
});
