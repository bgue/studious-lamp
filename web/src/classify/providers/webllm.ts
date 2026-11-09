// A tiny language model in the browser (WebLLM, WebGPU) that answers the same typed questions as Jev.
//
// The library is NOT bundled. It is loaded at run time from a CDN, from an exact pinned version, so that the single-file
// viewer does not grow and nothing downloads until the user turns this provider on.
//
// Jev semantics: a choice question gets one probability per option. Each option gets a one-character label (A to Z, then a
// to z). The model answers with one token, and the probabilities are the log probabilities of the label tokens at that
// position (WebLLM returns the top 5), renormalised over the labels. An option outside the top 5 gets probability 0.
// confidence = top probability x the probability mass that fell on labels. A noul question uses the tokens Y and N.
//
// Three modes (setting `webllmMode`):
//   chat    the chat model answers every question with one token (above)
//   embed   an embedding model (Snowflake Arctic Embed): cosine similarity of the element text against each option text,
//           then a softmax with a temperature -> a probability for EVERY option (no top-5 limit). A yes/no question is
//           answered weakly (the statement against its negation): use hybrid or the decision provider for those
//   hybrid  embed first. When the top-2 margin is small, the chat model chooses among the top 5 options only, where its
//           top-5 log probabilities are complete. A yes/no question always goes to the chat model

import { ProviderError } from '../types';
import type { DecisionModel } from '../types';
import type { Answer, Answers, ChoiceQuestion, JsonObject, NoulQuestion, Questions } from '../jevAdapter';
import { buildPremise } from './decision';

export const WEBLLM_VERSION = '0.2.87';
export const WEBLLM_CDN_URL = `https://cdn.jsdelivr.net/npm/@mlc-ai/web-llm@${WEBLLM_VERSION}/+esm`;

export interface WebLlmModelInfo {
  /** The model id in the WebLLM prebuilt list (version above). */
  id: string;
  label: string;
  /** Download in MB: the size of the weight shards and the tokenizer in the model repository on huggingface.co. */
  approxDownloadMB: number;
  /** vram_required_MB from the WebLLM prebuilt list. */
  vramMB: number;
}

export const WEBLLM_MODELS: readonly WebLlmModelInfo[] = [
  { id: 'gemma3-1b-it-q4f16_1-MLC', label: 'Gemma 3 1B Instruct (least GPU memory of the new ones)', approxDownloadMB: 602, vramMB: 711 },
  { id: 'SmolLM2-360M-Instruct-q4f16_1-MLC', label: 'SmolLM2 360M (smallest)', approxDownloadMB: 206, vramMB: 376 },
  { id: 'Qwen2.5-0.5B-Instruct-q4f16_1-MLC', label: 'Qwen2.5 0.5B Instruct', approxDownloadMB: 285, vramMB: 945 },
  { id: 'Qwen3-0.6B-q4f16_1-MLC', label: 'Qwen3 0.6B (default)', approxDownloadMB: 347, vramMB: 1403 },
  { id: 'Qwen3.5-0.8B-q4f16_1-MLC', label: 'Qwen3.5 0.8B', approxDownloadMB: 437, vramMB: 1629 },
  { id: 'Qwen2.5-1.5B-Instruct-q4f16_1-MLC', label: 'Qwen2.5 1.5B Instruct', approxDownloadMB: 876, vramMB: 1630 },
  { id: 'Qwen3-1.7B-q4f16_1-MLC', label: 'Qwen3 1.7B (best of the small ones)', approxDownloadMB: 979, vramMB: 2037 },
];
export const WEBLLM_DEFAULT_MODEL = 'Qwen3-0.6B-q4f16_1-MLC';

/** Embedding models of the WebLLM prebuilt list. The `-b4` builds take 4 texts per batch and need the least GPU memory. */
export const WEBLLM_EMBED_MODELS: readonly WebLlmModelInfo[] = [
  { id: 'snowflake-arctic-embed-s-q0f32-MLC-b4', label: 'Snowflake Arctic Embed S (default)', approxDownloadMB: 67, vramMB: 239 },
  { id: 'snowflake-arctic-embed-m-q0f32-MLC-b4', label: 'Snowflake Arctic Embed M', approxDownloadMB: 218, vramMB: 540 },
];
export const WEBLLM_DEFAULT_EMBED_MODEL = 'snowflake-arctic-embed-s-q0f32-MLC-b4';

export const WEBLLM_MODES = ['chat', 'embed', 'hybrid'] as const;
export type WebLlmMode = (typeof WEBLLM_MODES)[number];
/** Temperature of the softmax over the cosine similarities. Cosines of related texts differ by about 0.05 to 0.2. */
export const DEFAULT_EMBED_TEMPERATURE = 0.05;
/** Hybrid: below this top-2 probability margin the chat model decides among the top 5. */
export const DEFAULT_HYBRID_MARGIN = 0.15;
/** Hybrid: the chat model chooses among at most this many options (its top log probabilities are complete for 5). */
export const HYBRID_TOP_K = 5;

export const webllmModelInfo = (id: string): WebLlmModelInfo | undefined => WEBLLM_MODELS.find((m) => m.id === id);
export const webllmEmbedInfo = (id: string): WebLlmModelInfo | undefined => WEBLLM_EMBED_MODELS.find((m) => m.id === id);

export function describeModel(id: string): string {
  const m = webllmModelInfo(id) ?? webllmEmbedInfo(id);
  return m ? `${m.label}: download about ${m.approxDownloadMB} MB, GPU memory about ${m.vramMB} MB` : id;
}

// ---------------------------------------------------------------- a custom model from Hugging Face (advanced)

const CUSTOM_MODEL_URL = /^https:\/\/huggingface\.co\/[A-Za-z0-9][A-Za-z0-9._-]*\/[A-Za-z0-9][A-Za-z0-9._-]*\/?$/;
/** Hosts where the MLC libraries and models are normally published. */
const USUAL_LIB_HOSTS = ['huggingface.co', 'raw.githubusercontent.com', 'github.com'];

/** Problems with a custom MLC model (repository URL and compiled library URL), as plain messages, and warnings. */
export function customModelCheck(model: string, lib: string): { errors: string[]; warnings: string[] } {
  const errors: string[] = [];
  const warnings: string[] = [];
  const m = model.trim();
  const l = lib.trim();
  if (!m && !l) return { errors, warnings };
  if (!m || !l) errors.push('A custom browser model needs both its model URL and its model library URL. Fill in both, or clear both.');
  if (m && !CUSTOM_MODEL_URL.test(m)) errors.push(`The custom model URL must be a Hugging Face repository, such as https://huggingface.co/mlc-ai/Qwen3-0.6B-q4f16_1-MLC. "${m}" is not.`);
  if (l) {
    let u: URL | null = null;
    try { u = new URL(l); } catch { /* checked below */ }
    if (!u || u.protocol !== 'https:') errors.push(`The custom model library URL must start with https://. "${l}" does not.`);
    else if (u.username || u.password) errors.push('The custom model library URL must not contain a user name or password.');
    else if (!/\.wasm$/i.test(u.pathname)) errors.push('The custom model library URL must end with .wasm (a compiled WebGPU model library).');
    else if (!USUAL_LIB_HOSTS.includes(u.hostname)) warnings.push(`The model library comes from ${u.hostname}. A library runs as code in this page: use one only from a source that you trust.`);
    else warnings.push('A model library runs as code in this page: use one only from a source that you trust.');
  }
  return { errors, warnings };
}

/** The id that a custom model gets in the engine: "custom-<repository name>". */
export function customModelId(model: string): string {
  const name = model.trim().replace(/\/+$/, '').split('/').pop() ?? 'model';
  return `custom-${name}`;
}

export interface CustomModel {
  model: string;
  lib: string;
}

// ---------------------------------------------------------------- WebGPU

export interface GpuSupport {
  ok: boolean;
  /** Plain-language reason when not ok. */
  reason: string;
}

/** Is WebGPU usable? `nav` is injectable for tests. */
export async function detectWebGpu(nav: { gpu?: { requestAdapter(): Promise<unknown> } } | undefined = typeof navigator === 'undefined' ? undefined : (navigator as never)): Promise<GpuSupport> {
  if (!nav || !nav.gpu) {
    return {
      ok: false,
      reason: 'WebGPU is not available in this browser, so the browser model cannot run. Use a recent Chrome or Edge on a computer with a GPU, or choose the Jev provider or the rules only.',
    };
  }
  try {
    const a = await nav.gpu.requestAdapter();
    if (!a) return { ok: false, reason: 'WebGPU is present but the browser found no GPU adapter (a software or blocked GPU). The browser model cannot run here. Choose the Jev provider or the rules only.' };
  } catch (e) {
    return { ok: false, reason: `WebGPU failed to start (${e instanceof Error ? e.message : String(e)}). The browser model cannot run here.` };
  }
  return { ok: true, reason: '' };
}

// ---------------------------------------------------------------- labels and parsing (pure)

const LABELS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz';

export function labelsFor(options: readonly string[]): string[] {
  if (options.length > LABELS.length) throw new ProviderError(`The browser model cannot choose among ${options.length} options (the limit is ${LABELS.length}).`);
  return options.map((_, i) => LABELS[i]!);
}

export interface TopLogprob {
  token: string;
  logprob: number;
}

/** Probabilities per label from the top log probabilities of the first token. Null when no label appears. */
export function probsFromTop(top: readonly TopLogprob[], labels: readonly string[]): { p: number[]; mass: number } | null {
  const p = labels.map(() => 0);
  let mass = 0;
  for (const t of top) {
    const k = labels.indexOf(t.token.trim());
    if (k < 0) continue;
    const v = Math.exp(t.logprob);
    if (v > p[k]!) {
      mass += v - p[k]!;
      p[k] = v;
    }
  }
  if (mass <= 0) return null;
  return { p: p.map((x) => x / mass), mass: Math.min(1, mass) };
}

export function yesFromTop(top: readonly TopLogprob[]): number | null {
  let y = 0;
  let n = 0;
  for (const t of top) {
    const w = t.token.trim().toLowerCase();
    const v = Math.exp(t.logprob);
    if (w === 'y' || w === 'yes') y = Math.max(y, v);
    else if (w === 'n' || w === 'no') n = Math.max(n, v);
  }
  return y + n > 0 ? y / (y + n) : null;
}

const clip = (s: string, n: number): string => (s.length <= n ? s : `${s.slice(0, n - 1)}…`);

export function choicePrompt(state: JsonObject, instructions: string, options: readonly string[], texts: readonly string[], labels: readonly string[]): string {
  const list = options.map((o, i) => `${labels[i]}. ${o}${texts[i] ? ` - ${clip(texts[i]!, 110)}` : ''}`).join('\n');
  return `BIM ELEMENT (JSON):\n${JSON.stringify(state)}\n\nQUESTION: ${instructions}\n\nOPTIONS:\n${list}\n\nAnswer with the one letter of the best option. No other text.`;
}

export function noulPrompt(state: JsonObject, statement: string): string {
  return `BIM ELEMENT (JSON):\n${JSON.stringify(state)}\n\nSTATEMENT: ${statement}\n\nIs the statement true? Answer Y for yes or N for no. No other text.`;
}

const SYSTEM = 'You are a careful BIM data classifier. You read one element and answer a multiple-choice question about it.';

// ---------------------------------------------------------------- embeddings (pure)

/** Snowflake Arctic Embed retrieves with this prefix on the QUERY side (the options are the documents and have none). */
export const ARCTIC_QUERY_PREFIX = 'Represent this sentence for searching relevant passages: ';

export function normalise(v: readonly number[]): number[] {
  let s = 0;
  for (const x of v) s += x * x;
  const n = Math.sqrt(s) || 1;
  return v.map((x) => x / n);
}

/** Cosine similarity. */
export function cosine(a: readonly number[], b: readonly number[]): number {
  const x = normalise(a);
  const y = normalise(b);
  let s = 0;
  for (let i = 0; i < x.length; i++) s += x[i]! * (y[i] ?? 0);
  return s;
}

/** Softmax of `xs / temperature`. Sums to 1. A temperature at or below 0 is treated as 0.001 (nearly argmax). */
export function softmaxTemp(xs: readonly number[], temperature: number): number[] {
  if (xs.length === 0) return [];
  const t = temperature > 0 ? temperature : 0.001;
  const m = Math.max(...xs);
  const e = xs.map((x) => Math.exp((x - m) / t));
  const s = e.reduce((a, b) => a + b, 0);
  return e.map((x) => x / s);
}

/** Indexes of the k largest values, largest first. A tie keeps the option order (the earlier option wins). */
export function topK(p: readonly number[], k: number): number[] {
  return p.map((v, i) => [v, i] as const).sort((a, b) => b[0] - a[0] || a[1] - b[1]).slice(0, k).map(([, i]) => i);
}

/** Probability difference of the best two options (1 when there is only one). */
export function marginOf(p: readonly number[]): number {
  const [a, b] = topK(p, 2);
  return a === undefined ? 0 : b === undefined ? 1 : p[a]! - p[b]!;
}

// ---------------------------------------------------------------- engine

/** The part of the WebLLM engine that this provider uses. */
export interface WebLlmEngine {
  chat: { completions: { create(req: Record<string, unknown>): Promise<{ choices: Array<{ logprobs?: { content?: Array<{ top_logprobs?: TopLogprob[] }> | null } | null }> }> } };
  /** Present when an embedding model is loaded. */
  embeddings?: { create(req: { input: string | string[]; model?: string }): Promise<{ data: Array<{ embedding: number[] }> }> };
  interruptGenerate?(): void;
}

export interface LoadProgress {
  text: string;
  /** 0 to 1 */
  progress: number;
}

/**
 * Load the library from the CDN and create the engine with every model that the mode needs (a chat model, an embedding
 * model or both). Downloads the weights on first use (the browser caches them). A custom model is added to the model list.
 */
export async function loadWebLlmEngine(modelIds: readonly string[], onProgress?: (p: LoadProgress) => void, custom?: CustomModel): Promise<WebLlmEngine> {
  const gpu = await detectWebGpu();
  if (!gpu.ok) throw new ProviderError(gpu.reason);
  let lib: { CreateMLCEngine(id: string | string[], cfg: Record<string, unknown>): Promise<WebLlmEngine>; prebuiltAppConfig?: { model_list: Array<Record<string, unknown>> } };
  try {
    lib = await import(/* @vite-ignore */ WEBLLM_CDN_URL);
  } catch (e) {
    throw new ProviderError(`Could not load the browser model library from the CDN (${e instanceof Error ? e.message : String(e)}). Check the network or a content security policy.`);
  }
  const cfg: Record<string, unknown> = { initProgressCallback: (p: LoadProgress) => onProgress?.({ text: p.text, progress: p.progress }) };
  if (custom) {
    const base = lib.prebuiltAppConfig?.model_list ?? [];
    cfg['appConfig'] = { ...(lib.prebuiltAppConfig ?? {}), model_list: [...base, { model: custom.model.trim().replace(/\/+$/, ''), model_id: customModelId(custom.model), model_lib: custom.lib.trim() }] };
  }
  return lib.CreateMLCEngine(modelIds.length === 1 ? modelIds[0]! : [...modelIds], cfg);
}

export interface WebLlmOptions {
  /** The chat model id (or the id of the custom model). */
  model: string;
  mode?: WebLlmMode;
  embedModel?: string;
  /** Softmax temperature of the embedding similarities. */
  temperature?: number;
  /** Hybrid: the top-2 margin below which the chat model decides. */
  hybridMargin?: number;
  custom?: CustomModel;
  /** Replace the engine loader (tests). Gets the ids of every model to load. */
  load?: (modelIds: string[], onProgress?: (p: LoadProgress) => void, custom?: CustomModel) => Promise<WebLlmEngine>;
  onProgress?: (p: LoadProgress) => void;
}

/** Counts of the embed and hybrid modes, for the drawer and the tests. */
export interface WebLlmStats {
  embeddedTexts: number;
  /** Choice questions that the chat model decided in hybrid mode (margin too small). */
  escalated: number;
  /** Choice questions that the embedding alone decided. */
  embedOnly: number;
  chatCalls: number;
}

const THINKING = /^Qwen3/i;

export interface WebLlmProvider extends DecisionModel {
  stats(): WebLlmStats;
}

const r4 = (x: number): number => Math.round(x * 1e4) / 1e4;

export function createWebLlmProvider(o: WebLlmOptions): WebLlmProvider {
  const mode: WebLlmMode = o.mode ?? 'chat';
  const temperature = o.temperature ?? DEFAULT_EMBED_TEMPERATURE;
  const hybridMargin = o.hybridMargin ?? DEFAULT_HYBRID_MARGIN;
  const embedId = o.embedModel ?? WEBLLM_DEFAULT_EMBED_MODEL;
  const stats: WebLlmStats = { embeddedTexts: 0, escalated: 0, embedOnly: 0, chatCalls: 0 };
  let engine: Promise<WebLlmEngine> | null = null;
  const get = (): Promise<WebLlmEngine> => {
    if (!engine) {
      const ids = mode === 'chat' ? [o.model] : mode === 'embed' ? [embedId] : [o.model, embedId];
      engine = (o.load ?? loadWebLlmEngine)(ids, o.onProgress, o.custom);
      engine.catch(() => { engine = null; });
    }
    return engine;
  };
  // One request at a time: the engine runs a single generation.
  let chain: Promise<unknown> = Promise.resolve();
  const modelField = (): Record<string, unknown> => (mode === 'chat' ? {} : { model: o.model });
  const firstTop = async (e: WebLlmEngine, user: string, signal: AbortSignal): Promise<TopLogprob[]> => {
    if (signal.aborted) throw new DOMException('Aborted', 'AbortError');
    const onAbort = (): void => e.interruptGenerate?.();
    signal.addEventListener('abort', onAbort, { once: true });
    try {
      stats.chatCalls++;
      const r = await e.chat.completions.create({
        messages: [{ role: 'system', content: SYSTEM }, { role: 'user', content: user }],
        max_tokens: 1, temperature: 0, logprobs: true, top_logprobs: 5, stream: false,
        // Qwen3 models think first unless told not to: the first token would be <think>, not an answer.
        ...(THINKING.test(o.model) ? { extra_body: { enable_thinking: false } } : {}),
        ...modelField(),
      });
      if (signal.aborted) throw new DOMException('Aborted', 'AbortError');
      const top = r.choices[0]?.logprobs?.content?.[0]?.top_logprobs;
      if (!top || top.length === 0) throw new ProviderError('The browser model returned no log probabilities.');
      return top;
    } finally {
      signal.removeEventListener('abort', onAbort);
    }
  };

  // ---- the embedding side: option vectors are cached (the options are the same for every element)
  const optionVecs = new Map<string, number[]>();
  const embed = async (e: WebLlmEngine, texts: string[]): Promise<number[][]> => {
    if (!e.embeddings) throw new ProviderError('The embedding model did not load, so the embed mode cannot run.');
    const r = await e.embeddings.create({ input: texts, model: embedId });
    stats.embeddedTexts += texts.length;
    if (!r.data || r.data.length !== texts.length) throw new ProviderError(`The embedding model returned ${r.data?.length ?? 0} vectors for ${texts.length} texts.`);
    return r.data.map((d) => normalise(d.embedding));
  };
  const optionVectors = async (e: WebLlmEngine, texts: string[]): Promise<number[][]> => {
    const missing = [...new Set(texts.filter((t) => !optionVecs.has(t)))];
    if (missing.length) (await embed(e, missing)).forEach((v, i) => optionVecs.set(missing[i]!, v));
    return texts.map((t) => optionVecs.get(t)!);
  };
  const queryText = (state: JsonObject): string => `${ARCTIC_QUERY_PREFIX}${buildPremise(state, 200)}`;
  /** Probabilities of the options by embedding similarity, and the cosines. */
  const embedChoice = async (e: WebLlmEngine, q: string, texts: string[]): Promise<number[]> => {
    const [qv] = await embed(e, [q]);
    const ov = await optionVectors(e, texts);
    return softmaxTemp(ov.map((v) => cosine(qv!, v)), temperature);
  };
  const choiceTexts = (q: ChoiceQuestion): { options: string[]; texts: string[] } => {
    const options = Object.keys(q.criteria);
    return { options, texts: options.map((k) => q.criteria[k]!.slice(0, 600)) };
  };
  const embedYes = async (e: WebLlmEngine, q: string, s: NoulQuestion): Promise<number> => {
    const [qv] = await embed(e, [q]);
    const [pos, neg] = await optionVectors(e, [s.instructions, `It is not true that ${s.instructions.charAt(0).toLowerCase()}${s.instructions.slice(1)}`]);
    return softmaxTemp([cosine(qv!, pos!), cosine(qv!, neg!)], temperature)[0]!;
  };

  const choiceAnswer = (options: string[], p: number[], mass = 1): Answer => {
    const probabilities: Record<string, number> = {};
    options.forEach((opt, i) => { probabilities[opt] = r4(p[i]!); });
    const best = topK(p, 1)[0]!;
    return { type: 'choice', choice: options[best]!, confidence: r4(p[best]! * mass), probabilities };
  };

  const chatChoice = async (e: WebLlmEngine, state: JsonObject, q: ChoiceQuestion, signal: AbortSignal): Promise<Answer> => {
    const options = Object.keys(q.criteria);
    const labels = labelsFor(options);
    const top = await firstTop(e, choicePrompt(state, q.instructions, options, options.map((k) => q.criteria[k]!), labels), signal);
    const r = probsFromTop(top, labels);
    if (!r) throw new ProviderError('The browser model did not answer with an option letter.');
    return choiceAnswer(options, r.p, r.mass);
  };

  const embedOnlyChoice = async (e: WebLlmEngine, state: JsonObject, q: ChoiceQuestion): Promise<Answer> => {
    const { options, texts } = choiceTexts(q);
    stats.embedOnly++;
    return choiceAnswer(options, await embedChoice(e, queryText(state), texts));
  };

  /** Embed first. Below the margin, the chat model chooses among the top options only (its top 5 are then complete). */
  const hybridChoice = async (e: WebLlmEngine, state: JsonObject, q: ChoiceQuestion, signal: AbortSignal): Promise<Answer> => {
    const { options, texts } = choiceTexts(q);
    const p = await embedChoice(e, queryText(state), texts);
    if (options.length <= 1 || marginOf(p) >= hybridMargin) {
      stats.embedOnly++;
      return choiceAnswer(options, p);
    }
    stats.escalated++;
    const idx = topK(p, Math.min(HYBRID_TOP_K, options.length));
    const subOptions = idx.map((i) => options[i]!);
    const labels = labelsFor(subOptions);
    const top = await firstTop(e, choicePrompt(state, q.instructions, subOptions, idx.map((i) => q.criteria[options[i]!]!), labels), signal);
    const r = probsFromTop(top, labels);
    if (!r) {
      // The chat model named no letter: keep the embedding answer (the top-k order breaks the tie).
      stats.embedOnly++;
      return choiceAnswer(options, p);
    }
    // The top options share the probability mass that the embedding gave them; the chat model splits it. Others keep theirs.
    const mass = idx.reduce((s, i) => s + p[i]!, 0);
    const out = [...p];
    idx.forEach((i, k) => { out[i] = r.p[k]! * mass; });
    return choiceAnswer(options, out);
  };

  const run = async (state: JsonObject, questions: Questions, signal: AbortSignal): Promise<Answers> => {
    const e = await get();
    const answers: Record<string, Answer> = {};
    for (const [name, q] of Object.entries(questions)) {
      if (signal.aborted) throw new DOMException('Aborted', 'AbortError');
      if (q.type === 'choice') {
        answers[name] = mode === 'chat' ? await chatChoice(e, state, q, signal) : mode === 'embed' ? await embedOnlyChoice(e, state, q) : await hybridChoice(e, state, q, signal);
      } else if (q.type === 'noul') {
        if (mode === 'embed') answers[name] = { type: 'noul', noul: r4(await embedYes(e, queryText(state), q)) };
        else {
          const y = yesFromTop(await firstTop(e, noulPrompt(state, q.instructions), signal));
          if (y === null) throw new ProviderError('The browser model did not answer Y or N.');
          answers[name] = { type: 'noul', noul: r4(y) };
        }
      } else {
        const options = q.criteria.map((_, i) => String(i));
        const labels = labelsFor(options);
        const top = await firstTop(e, choicePrompt(state, q.instructions, options, q.criteria, labels), signal);
        const r = probsFromTop(top, labels);
        if (!r) throw new ProviderError('The browser model did not answer with a level letter.');
        const probabilities: Record<string, number> = {};
        let best = 0;
        options.forEach((opt, i) => {
          probabilities[opt] = r4(r.p[i]!);
          if (r.p[i]! > r.p[best]!) best = i;
        });
        answers[name] = { type: 'score', score: best, confidence: r4(r.p[best]! * r.mass), probabilities };
      }
    }
    const tag = mode === 'chat' ? o.model : mode === 'embed' ? embedId : `${embedId}+${o.model}`;
    return { model: `webllm:${tag}`, answers };
  };
  return {
    provider: 'webllm',
    stats: () => ({ ...stats }),
    decide(state, questions, signal): Promise<Answers> {
      const next = chain.then(() => run(state, questions, signal));
      chain = next.catch(() => undefined);
      return next;
    },
  };
}
