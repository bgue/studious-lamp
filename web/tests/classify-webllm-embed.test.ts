// WebLLM embed and hybrid modes with a FAKE engine: cosine, softmax with a temperature, the top-2 margin, the top-k tie-break,
// the choice of the chat model among the top options only, the Qwen3 thinking switch, the custom model checks and the pin of 0.2.87.

import { describe, expect, it } from 'vitest';
import { defaultDraft, defaultSchema, providerId, toSettings, validateSettings } from '../src/classify';
import { choiceQuestion, noulQuestion } from '../src/classify/jevAdapter';
import type { ChoiceAnswer, NoulAnswer } from '../src/classify/jevAdapter';
import { createProvider } from '../src/classify/providers';
import {
  ARCTIC_QUERY_PREFIX, cosine, createWebLlmProvider, customModelCheck, customModelId, DEFAULT_EMBED_TEMPERATURE, DEFAULT_HYBRID_MARGIN, marginOf, normalise, softmaxTemp, topK,
  WEBLLM_CDN_URL, WEBLLM_DEFAULT_EMBED_MODEL, WEBLLM_DEFAULT_MODEL, WEBLLM_EMBED_MODELS, WEBLLM_MODELS, WEBLLM_VERSION,
} from '../src/classify/providers/webllm';
import type { LoadProgress, TopLogprob, WebLlmEngine } from '../src/classify/providers/webllm';

const SIGNAL = new AbortController().signal;
const top = (pairs: Array<[string, number]>): TopLogprob[] => pairs.map(([token, p]) => ({ token, logprob: Math.log(p) }));

// A bag-of-words embedding: one dimension per topic word. Texts that share topic words are close.
const TOPICS = ['duct', 'fan', 'pipe', 'water', 'wall', 'door', 'beam', 'slab'];
const embedText = (t: string): number[] => TOPICS.map((w) => (t.toLowerCase().includes(w) ? 1 : 0));

interface Spy {
  engine: WebLlmEngine;
  embedInputs: string[][];
  chat: Array<Record<string, unknown>>;
  loaded: Array<{ ids: string[]; custom?: unknown }>;
}
function spy(chatAnswer: (user: string) => Array<[string, number]> = () => [['A', 0.9], ['B', 0.05]]): Spy {
  const s: Spy = { embedInputs: [], chat: [], loaded: [], engine: undefined as never };
  s.engine = {
    chat: {
      completions: {
        create: async (req) => {
          s.chat.push(req);
          const user = (req['messages'] as Array<{ content: string }>)[1]!.content;
          return { choices: [{ logprobs: { content: [{ top_logprobs: top(chatAnswer(user)) }] } }] };
        },
      },
    },
    embeddings: {
      create: async ({ input }) => {
        const arr = Array.isArray(input) ? input : [input];
        s.embedInputs.push(arr);
        return { data: arr.map((t) => ({ embedding: embedText(t) })) };
      },
    },
  };
  return s;
}
const load = (s: Spy) => async (ids: string[], _p?: (x: LoadProgress) => void, custom?: unknown): Promise<WebLlmEngine> => { s.loaded.push({ ids, custom }); return s.engine; };

const Q = {
  pick: choiceQuestion('Choose.', {
    MEC: 'Mechanical. Heating and ventilation: duct, fan, air handling.',
    PLB: 'Plumbing. Water supply: pipe, water, drainage.',
    ARC: 'Architectural. Wall, door, finishes.',
    STR: 'Structural. Beam, slab, column.',
  }),
};
const ductState = { class: 'IfcDuctSegment', name: 'Duct fan coil', building_context: true };
const ch = (a: unknown): ChoiceAnswer => a as ChoiceAnswer;

describe('the pure maths', () => {
  it('cosine similarity', () => {
    expect(cosine([1, 0], [1, 0])).toBeCloseTo(1);
    expect(cosine([1, 0], [0, 1])).toBeCloseTo(0);
    expect(cosine([2, 0], [-3, 0])).toBeCloseTo(-1);
    expect(cosine([1, 1], [1, 0])).toBeCloseTo(Math.SQRT1_2);
    expect(normalise([3, 4])).toEqual([0.6, 0.8]);
    expect(cosine([0, 0], [1, 1])).toBe(0); // a zero vector does not give NaN
  });

  it('softmax with a temperature sums to 1, is sharper when colder, and is the argmax when very cold', () => {
    const cos = [0.62, 0.55, 0.3, 0.1];
    for (const t of [0.01, 0.05, 0.2, 1]) expect(softmaxTemp(cos, t).reduce((a, b) => a + b, 0)).toBeCloseTo(1, 12);
    expect(softmaxTemp(cos, 0.02)[0]!).toBeGreaterThan(softmaxTemp(cos, 0.2)[0]!);
    expect(softmaxTemp(cos, 1).every((p) => p > 0.1)).toBe(true);
    const cold = softmaxTemp(cos, 0.0001);
    expect(cold[0]).toBeCloseTo(1, 6);
    expect(softmaxTemp(cos, 0)[0]).toBeCloseTo(1, 6); // a zero temperature does not divide by zero
    const p = softmaxTemp([0.6, 0.5], 0.05);
    expect(p[0]! / p[1]!).toBeCloseTo(Math.exp(0.1 / 0.05), 10);
    expect(softmaxTemp([], 0.05)).toEqual([]);
  });

  it('top-k: largest first, a tie keeps the option order, k larger than the list is fine', () => {
    expect(topK([0.1, 0.4, 0.4, 0.1], 2)).toEqual([1, 2]);
    expect(topK([0.25, 0.25, 0.25, 0.25], 3)).toEqual([0, 1, 2]);
    expect(topK([0.2, 0.8], 5)).toEqual([1, 0]);
    expect(topK([], 3)).toEqual([]);
  });

  it('the top-2 margin', () => {
    expect(marginOf([0.5, 0.3, 0.2])).toBeCloseTo(0.2);
    expect(marginOf([0.4, 0.4, 0.2])).toBe(0);
    expect(marginOf([1])).toBe(1);
    expect(marginOf([])).toBe(0);
  });
});

describe('embed mode', () => {
  it('scores every option by similarity, sums to 1, and chooses the nearest option', async () => {
    const s = spy();
    const p = createWebLlmProvider({ model: 'm', mode: 'embed', load: load(s) });
    const a = await p.decide(ductState, Q, SIGNAL);
    const d = ch(a.answers['pick']);
    expect(d.choice).toBe('MEC');
    expect(Object.keys(d.probabilities)).toEqual(['MEC', 'PLB', 'ARC', 'STR']);
    expect(Object.values(d.probabilities).reduce((x, y) => x + y, 0)).toBeCloseTo(1, 3);
    expect(d.confidence).toBe(d.probabilities['MEC']);
    expect(a.model).toBe(`webllm:${WEBLLM_DEFAULT_EMBED_MODEL}`);
    expect(s.chat).toHaveLength(0); // the chat model is not used
  });

  it('loads the embedding model only, and uses the query prefix on the element text and none on the options', async () => {
    const s = spy();
    const p = createWebLlmProvider({ model: 'chat-model', embedModel: 'snowflake-arctic-embed-m-q0f32-MLC-b4', mode: 'embed', load: load(s) });
    await p.decide(ductState, Q, SIGNAL);
    expect(s.loaded[0]!.ids).toEqual(['snowflake-arctic-embed-m-q0f32-MLC-b4']);
    expect(s.embedInputs[0]![0]!.startsWith(ARCTIC_QUERY_PREFIX)).toBe(true);
    expect(s.embedInputs[0]![0]).toContain('IfcDuctSegment');
    expect(s.embedInputs[1]!.every((t) => !t.startsWith(ARCTIC_QUERY_PREFIX))).toBe(true);
  });

  it('embeds the options once: the next element costs one embedding', async () => {
    const s = spy();
    const p = createWebLlmProvider({ model: 'm', mode: 'embed', load: load(s) });
    await p.decide(ductState, Q, SIGNAL);
    expect(p.stats().embeddedTexts).toBe(1 + 4);
    await p.decide({ class: 'IfcWall', name: 'Wall door', building_context: true }, Q, SIGNAL);
    expect(p.stats().embeddedTexts).toBe(1 + 4 + 1);
    expect(ch((await p.decide({ class: 'IfcBeam', name: 'Beam slab' }, Q, SIGNAL)).answers['pick']).choice).toBe('STR');
  });

  it('a lower temperature gives a higher confidence for the same text', async () => {
    const run = async (temperature: number): Promise<number> => ch((await createWebLlmProvider({ model: 'm', mode: 'embed', temperature, load: load(spy()) }).decide(ductState, Q, SIGNAL)).answers['pick']).confidence;
    expect(await run(0.02)).toBeGreaterThan(await run(0.2));
    expect(DEFAULT_EMBED_TEMPERATURE).toBe(0.05);
  });

  it('breaks an exact tie by option order', async () => {
    const same = { type: 'choice' as const, instructions: 'x', criteria: { B: 'Wall.', A: 'Wall.', C: 'Beam.' } };
    const p = createWebLlmProvider({ model: 'm', mode: 'embed', load: load(spy()) });
    const d = ch((await p.decide({ class: 'IfcWall', name: 'wall' }, { pick: same }, SIGNAL)).answers['pick']);
    expect(d.probabilities['B']).toBe(d.probabilities['A']);
    expect(d.choice).toBe('B'); // the first of the tied options
  });

  it('answers a yes/no question weakly from the statement against its negation, inside 0 and 1', async () => {
    const p = createWebLlmProvider({ model: 'm', mode: 'embed', load: load(spy()) });
    const a = (await p.decide(ductState, { b: noulQuestion('This element is part of a building.') }, SIGNAL)).answers['b'] as NoulAnswer;
    expect(a.type).toBe('noul');
    expect(a.noul).toBeGreaterThanOrEqual(0);
    expect(a.noul).toBeLessThanOrEqual(1);
  });

  it('says plainly when the engine has no embedding model', async () => {
    const s = spy();
    delete (s.engine as { embeddings?: unknown }).embeddings;
    const p = createWebLlmProvider({ model: 'm', mode: 'embed', load: load(s) });
    await expect(p.decide(ductState, Q, SIGNAL)).rejects.toThrow(/embedding model did not load/);
  });
});

describe('hybrid mode', () => {
  // two options that the embedding cannot tell apart (same words), and two far ones
  const close = {
    pick: choiceQuestion('Choose.', {
      MEC: 'Mechanical. Duct and fan.',
      PLB: 'Plumbing. Duct and fan.',
      ARC: 'Architectural. Wall, door.',
      STR: 'Structural. Beam, slab.',
      X1: 'Other one. Water.',
      X2: 'Other two. Pipe.',
    }),
  };

  it('keeps the embedding answer when the margin is large (the chat model is not asked)', async () => {
    const s = spy();
    const p = createWebLlmProvider({ model: 'chat', mode: 'hybrid', load: load(s) });
    const d = ch((await p.decide(ductState, Q, SIGNAL)).answers['pick']);
    expect(d.choice).toBe('MEC');
    expect(s.chat).toHaveLength(0);
    expect(p.stats()).toMatchObject({ escalated: 0, embedOnly: 1, chatCalls: 0 });
  });

  it('loads the chat model and the embedding model, and names both in the model id', async () => {
    const s = spy();
    const p = createWebLlmProvider({ model: 'chat', mode: 'hybrid', load: load(s) });
    const a = await p.decide(ductState, Q, SIGNAL);
    expect(s.loaded[0]!.ids).toEqual(['chat', WEBLLM_DEFAULT_EMBED_MODEL]);
    expect(a.model).toBe(`webllm:${WEBLLM_DEFAULT_EMBED_MODEL}+chat`);
  });

  it('asks the chat model among the top 5 options only, and the chat answer decides a close call', async () => {
    const s = spy(() => [['B', 0.9], ['A', 0.05], ['C', 0.02]]); // the chat model prefers the second of the top options
    const p = createWebLlmProvider({ model: 'chat', mode: 'hybrid', hybridMargin: 0.3, load: load(s) });
    const a = await p.decide({ class: 'IfcDuctSegment', name: 'duct fan' }, close, SIGNAL);
    expect(p.stats().escalated).toBe(1);
    expect(s.chat).toHaveLength(1);
    const prompt = (s.chat[0]!['messages'] as Array<{ content: string }>)[1]!.content;
    const optionLines = prompt.split('\n').filter((l) => /^[A-Z]\. /.test(l));
    expect(optionLines).toHaveLength(5); // 6 options, the chat model sees the top 5
    expect(prompt).not.toContain('Other two'); // the option that ranks last (a tie of four goes by option order) is left out
    expect(prompt).toContain('Mechanical');
    expect(prompt).toContain('Plumbing');
    const d = ch(a.answers['pick']);
    expect(Object.values(d.probabilities).reduce((x, y) => x + y, 0)).toBeCloseTo(1, 3);
    // MEC and PLB tie in the embedding, so the order is MEC (A), PLB (B): the chat answer B picks PLB
    expect(d.choice).toBe('PLB');
    expect(d.probabilities['PLB']!).toBeGreaterThan(d.probabilities['MEC']!);
  });

  it('keeps the probability mass of the options that the chat model did not see', async () => {
    const s = spy(() => [['A', 0.8], ['B', 0.1], ['C', 0.05], ['D', 0.03], ['E', 0.01]]);
    const emb = createWebLlmProvider({ model: 'chat', mode: 'embed', load: load(spy()) });
    const base = ch((await emb.decide({ class: 'IfcDuctSegment', name: 'duct fan' }, close, SIGNAL)).answers['pick']);
    const hyb = createWebLlmProvider({ model: 'chat', mode: 'hybrid', hybridMargin: 0.3, load: load(s) });
    const d = ch((await hyb.decide({ class: 'IfcDuctSegment', name: 'duct fan' }, close, SIGNAL)).answers['pick']);
    // X2 ranks last (four options tie at 0 and the order breaks the tie): it is outside the top 5 and keeps its embedding probability
    expect(d.probabilities['X2']).toBeCloseTo(base.probabilities['X2']!, 3);
    // the top 5 share the mass that the embedding gave them: the chat model moved it between them, not out of them
    const topMass = ['MEC', 'PLB', 'ARC', 'STR', 'X1'].reduce((sum, k) => sum + d.probabilities[k]!, 0);
    const baseTop = ['MEC', 'PLB', 'ARC', 'STR', 'X1'].reduce((sum, k) => sum + base.probabilities[k]!, 0);
    expect(topMass).toBeCloseTo(baseTop, 3);
    expect(d.probabilities['MEC']!).toBeGreaterThan(base.probabilities['MEC']!); // the chat model chose A (MEC) with 0.8
    const left = ['X2'];
    expect(left.length).toBeGreaterThan(0);
    expect(Object.values(d.probabilities).reduce((x, y) => x + y, 0)).toBeCloseTo(1, 3);
  });

  it('falls back to the embedding order (the top-k tie-break) when the chat model names no option', async () => {
    const s = spy(() => [['The', 0.9]]);
    const p = createWebLlmProvider({ model: 'chat', mode: 'hybrid', hybridMargin: 0.3, load: load(s) });
    const d = ch((await p.decide({ class: 'IfcDuctSegment', name: 'duct fan' }, close, SIGNAL)).answers['pick']);
    expect(d.choice).toBe('MEC'); // tied with PLB: the earlier option
    expect(p.stats()).toMatchObject({ escalated: 1, embedOnly: 1 });
  });

  it('does not escalate a question with a single option, and a margin of 0 never escalates', async () => {
    const s = spy();
    const p = createWebLlmProvider({ model: 'chat', mode: 'hybrid', hybridMargin: 0, load: load(s) });
    await p.decide(ductState, close, SIGNAL);
    await p.decide(ductState, { one: choiceQuestion('x', { ONLY: 'Single. option.' }) }, SIGNAL);
    expect(s.chat).toHaveLength(0);
    expect(DEFAULT_HYBRID_MARGIN).toBe(0.15);
  });

  it('always asks the chat model a yes/no question, with its Y and N tokens', async () => {
    const s = spy(() => [['Y', 0.7], ['N', 0.1]]);
    const p = createWebLlmProvider({ model: 'chat', mode: 'hybrid', load: load(s) });
    const a = (await p.decide(ductState, { b: noulQuestion('Is it?') }, SIGNAL)).answers['b'] as NoulAnswer;
    expect(a.noul).toBeCloseTo(0.875, 3);
    expect(s.chat).toHaveLength(1);
    expect(s.embedInputs).toHaveLength(0);
  });

  it('puts the model id in the request of a multi-model engine, and switches thinking off for Qwen3', async () => {
    const s = spy();
    const q3 = createWebLlmProvider({ model: 'Qwen3-0.6B-q4f16_1-MLC', mode: 'hybrid', hybridMargin: 1, load: load(s) });
    await q3.decide({ class: 'IfcDuctSegment', name: 'duct fan' }, close, SIGNAL);
    expect(s.chat[0]).toMatchObject({ model: 'Qwen3-0.6B-q4f16_1-MLC', extra_body: { enable_thinking: false }, max_tokens: 1, top_logprobs: 5 });
    const s2 = spy();
    await createWebLlmProvider({ model: 'Qwen2.5-0.5B-Instruct-q4f16_1-MLC', mode: 'chat', load: load(s2) }).decide(ductState, Q, SIGNAL);
    expect(s2.chat[0]!['extra_body']).toBeUndefined();
    expect(s2.chat[0]!['model']).toBeUndefined(); // a single-model engine needs none
    const s3 = spy();
    await createWebLlmProvider({ model: 'Qwen3.5-0.8B-q4f16_1-MLC', mode: 'chat', load: load(s3) }).decide(ductState, Q, SIGNAL);
    expect(s3.chat[0]!['extra_body']).toEqual({ enable_thinking: false });
  });
});

describe('chat mode is unchanged', () => {
  it('still reads the top-5 log probabilities of one token and keeps the plain model id', async () => {
    const s = spy(() => [['B', 0.8], ['A', 0.1]]);
    const p = createWebLlmProvider({ model: 'Qwen2.5-0.5B-Instruct-q4f16_1-MLC', load: load(s) });
    const a = await p.decide(ductState, Q, SIGNAL);
    expect(a.model).toBe('webllm:Qwen2.5-0.5B-Instruct-q4f16_1-MLC');
    expect(ch(a.answers['pick']).choice).toBe('PLB');
    expect(s.loaded[0]!.ids).toEqual(['Qwen2.5-0.5B-Instruct-q4f16_1-MLC']);
    expect(s.embedInputs).toHaveLength(0);
  });
});

describe('version, model list and defaults', () => {
  it('pins WebLLM 0.2.87 on the CDN', () => {
    expect(WEBLLM_VERSION).toBe('0.2.87');
    expect(WEBLLM_CDN_URL).toBe('https://cdn.jsdelivr.net/npm/@mlc-ai/web-llm@0.2.87/+esm');
  });

  it('lists the new models with the vram_required_MB of the package', () => {
    const vram = Object.fromEntries(WEBLLM_MODELS.map((m) => [m.id, m.vramMB]));
    expect(vram['Qwen3-0.6B-q4f16_1-MLC']).toBe(1403);
    expect(vram['Qwen3-1.7B-q4f16_1-MLC']).toBe(2037);
    expect(vram['Qwen3.5-0.8B-q4f16_1-MLC']).toBe(1629);
    expect(vram['gemma3-1b-it-q4f16_1-MLC']).toBe(711);
    expect(vram['SmolLM2-360M-Instruct-q4f16_1-MLC']).toBe(376);
    expect(vram['Qwen2.5-0.5B-Instruct-q4f16_1-MLC']).toBe(945);
    expect(vram['Qwen2.5-1.5B-Instruct-q4f16_1-MLC']).toBe(1630);
    expect(WEBLLM_EMBED_MODELS.map((m) => m.id)).toEqual(['snowflake-arctic-embed-s-q0f32-MLC-b4', 'snowflake-arctic-embed-m-q0f32-MLC-b4']);
    expect(WEBLLM_DEFAULT_MODEL).toBe('Qwen3-0.6B-q4f16_1-MLC');
    expect(defaultDraft().webllmModel).toBe('Qwen3-0.6B-q4f16_1-MLC');
  });

  it('keeps old settings valid (a stored Qwen2.5 model, no mode)', () => {
    const c = validateSettings({ provider: 'webllm', webllmModel: 'Qwen2.5-0.5B-Instruct-q4f16_1-MLC' });
    expect(c.errors).toEqual([]);
    expect(c.warnings).toEqual([]);
    expect(c.settings).toMatchObject({ webllmMode: 'chat', webllmEmbedModel: WEBLLM_DEFAULT_EMBED_MODEL, embedTemperature: 0.05, hybridMargin: 0.15 });
    expect(providerId(c.settings)).toBe('webllm:Qwen2.5-0.5B-Instruct-q4f16_1-MLC'); // the cache of earlier runs is still valid
  });
});

describe('settings of the modes', () => {
  it('validates the mode, the embedding model, the temperature and the margin with plain messages', () => {
    const c = validateSettings({ provider: 'webllm', webllmMode: 'fast', webllmEmbedModel: '', embedTemperature: 5, hybridMargin: -1 });
    expect(c.errors).toHaveLength(4);
    expect(c.errors[0]).toBe('webllmMode must be one of chat, embed, hybrid. Using "chat".');
    expect(c.errors.join(' ')).toMatch(/embedTemperature must be a number from 0.005 to 1. Using 0.05/);
    expect(c.errors.join(' ')).toMatch(/hybridMargin must be a number from 0 to 1. Using 0.15/);
    expect(validateSettings({ provider: 'webllm', webllmEmbedModel: 'other-embed-model' }).warnings[0]).toMatch(/not one of the tested embedding models/);
    expect(validateSettings({ provider: 'webllm', webllmMode: 'hybrid', embedTemperature: 0.1, hybridMargin: 0.2 }).errors).toEqual([]);
  });

  it('puts the mode and its knobs in the id of the cache, so decisions of another mode are not reused', () => {
    const id = (patch: Record<string, unknown>): string => providerId(toSettings({ ...defaultDraft(), provider: 'webllm', ...patch }));
    expect(id({})).toBe(`webllm:${WEBLLM_DEFAULT_MODEL}`);
    expect(id({ webllmMode: 'embed' })).toBe('webllm:embed:snowflake-arctic-embed-s-q0f32-MLC-b4@T0.05');
    expect(id({ webllmMode: 'embed', embedTemperature: 0.1 })).not.toBe(id({ webllmMode: 'embed' }));
    expect(id({ webllmMode: 'hybrid' })).toBe(`webllm:hybrid:snowflake-arctic-embed-s-q0f32-MLC-b4+${WEBLLM_DEFAULT_MODEL}@T0.05,m0.15`);
    expect(id({ webllmMode: 'hybrid', hybridMargin: 0.3 })).not.toBe(id({ webllmMode: 'hybrid' }));
  });
});

describe('a custom MLC model from Hugging Face (advanced)', () => {
  const MODEL = 'https://huggingface.co/mlc-ai/Qwen3-0.6B-q4f16_1-MLC';
  const LIB = 'https://raw.githubusercontent.com/mlc-ai/binary-mlc-llm-libs/main/web-llm-models/v0_2_80/Qwen3-0.6B-q4f16_1-ctx4k_cs1k-webgpu.wasm';

  it('accepts a Hugging Face repository and a https .wasm library, and warns that a library runs as code', () => {
    const c = customModelCheck(MODEL, LIB);
    expect(c.errors).toEqual([]);
    expect(c.warnings[0]).toMatch(/runs as code in this page/);
    expect(customModelCheck('', '')).toEqual({ errors: [], warnings: [] });
    expect(customModelCheck(`${MODEL}/`, LIB).errors).toEqual([]);
  });

  it('explains each problem in plain words', () => {
    expect(customModelCheck(MODEL, '').errors[0]).toMatch(/needs both its model URL and its model library URL/);
    expect(customModelCheck('', LIB).errors[0]).toMatch(/needs both/);
    expect(customModelCheck('https://example.com/a/b', LIB).errors.join(' ')).toMatch(/must be a Hugging Face repository/);
    expect(customModelCheck('https://huggingface.co/a/b/resolve/main/x', LIB).errors.join(' ')).toMatch(/Hugging Face repository/);
    expect(customModelCheck('http://huggingface.co/a/b', LIB).errors.join(' ')).toMatch(/Hugging Face repository/);
    expect(customModelCheck(MODEL, 'http://x.org/m.wasm').errors[0]).toMatch(/must start with https/);
    expect(customModelCheck(MODEL, 'https://x.org/m.bin').errors[0]).toMatch(/must end with \.wasm/);
    expect(customModelCheck(MODEL, 'https://u:p@x.org/m.wasm').errors[0]).toMatch(/user name or password/);
    expect(customModelCheck(MODEL, 'not a url').errors[0]).toMatch(/must start with https/);
    expect(customModelCheck(MODEL, 'https://unknown.example.org/m.wasm').warnings[0]).toMatch(/comes from unknown\.example\.org/);
  });

  it('is dropped from the settings with a message when it is wrong, and kept when it is right', () => {
    const bad = validateSettings({ provider: 'webllm', webllmCustomModel: MODEL });
    expect(bad.errors[0]).toMatch(/needs both.*The custom model was ignored/);
    expect(bad.settings).toMatchObject({ webllmCustomModel: '', webllmCustomLib: '' });
    const ok = validateSettings({ provider: 'webllm', webllmCustomModel: MODEL, webllmCustomLib: LIB });
    expect(ok.errors).toEqual([]);
    expect(ok.settings).toMatchObject({ webllmCustomModel: MODEL, webllmCustomLib: LIB });
    expect(ok.warnings.join(' ')).toMatch(/runs as code/);
  });

  it('gets the id "custom-<repository>" and is handed to the loader as an appConfig entry source', async () => {
    expect(customModelId(MODEL)).toBe('custom-Qwen3-0.6B-q4f16_1-MLC');
    expect(customModelId(`${MODEL}/`)).toBe('custom-Qwen3-0.6B-q4f16_1-MLC');
    const s = spy();
    const seen: unknown[] = [];
    const provider = createProvider(validateSettings({ provider: 'webllm', webllmCustomModel: MODEL, webllmCustomLib: LIB }).settings, {
      apiKey: () => null,
      webllmLoad: async (ids, _p, custom) => { seen.push([ids, custom]); return s.engine; },
    })!;
    await provider.decide(ductState, Q, SIGNAL);
    expect(seen[0]).toEqual([['custom-Qwen3-0.6B-q4f16_1-MLC'], { model: MODEL, lib: LIB }]);
    expect(providerId(validateSettings({ provider: 'webllm', webllmCustomModel: MODEL, webllmCustomLib: LIB }).settings)).toBe('webllm:custom-Qwen3-0.6B-q4f16_1-MLC');
    expect(defaultSchema().disciplines.length).toBeGreaterThan(0);
  });
});
