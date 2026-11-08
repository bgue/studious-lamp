// A tiny language model in the browser (WebLLM, WebGPU) that answers the same typed questions as Jev.
//
// The library is NOT bundled. It is loaded at run time from a CDN, from an exact pinned version, so that the single-file
// viewer does not grow and nothing downloads until the user turns this provider on.
//
// Jev semantics: a choice question gets one probability per option. Each option gets a one-character label (A to Z, then a
// to z). The model answers with one token, and the probabilities are the log probabilities of the label tokens at that
// position (WebLLM returns the top 5), renormalised over the labels. An option outside the top 5 gets probability 0.
// confidence = top probability x the probability mass that fell on labels. A noul question uses the tokens Y and N.

import { ProviderError } from '../types';
import type { DecisionModel } from '../types';
import type { Answer, Answers, JsonObject, Questions } from '../jevAdapter';

export const WEBLLM_VERSION = '0.2.82';
export const WEBLLM_CDN_URL = `https://cdn.jsdelivr.net/npm/@mlc-ai/web-llm@${WEBLLM_VERSION}/+esm`;

export interface WebLlmModelInfo {
  /** The model id in the WebLLM prebuilt list (version above). */
  id: string;
  label: string;
  /** Approximate download, MB. WebLLM does not list the download size; this is an estimate for the 4-bit weights. */
  approxDownloadMB: number;
  /** vram_required_MB from the WebLLM prebuilt list. */
  vramMB: number;
}

export const WEBLLM_MODELS: readonly WebLlmModelInfo[] = [
  { id: 'SmolLM2-360M-Instruct-q4f16_1-MLC', label: 'SmolLM2 360M (smallest)', approxDownloadMB: 210, vramMB: 376 },
  { id: 'Qwen2.5-0.5B-Instruct-q4f16_1-MLC', label: 'Qwen2.5 0.5B Instruct (default)', approxDownloadMB: 300, vramMB: 945 },
  { id: 'Qwen2.5-1.5B-Instruct-q4f16_1-MLC', label: 'Qwen2.5 1.5B Instruct (best of the tiny ones)', approxDownloadMB: 900, vramMB: 1630 },
];
export const WEBLLM_DEFAULT_MODEL = 'Qwen2.5-0.5B-Instruct-q4f16_1-MLC';

export const webllmModelInfo = (id: string): WebLlmModelInfo | undefined => WEBLLM_MODELS.find((m) => m.id === id);

export function describeModel(id: string): string {
  const m = webllmModelInfo(id);
  return m ? `${m.label}: download about ${m.approxDownloadMB} MB (estimate), GPU memory about ${m.vramMB} MB` : id;
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

// ---------------------------------------------------------------- engine

/** The part of the WebLLM engine that this provider uses. */
export interface WebLlmEngine {
  chat: { completions: { create(req: Record<string, unknown>): Promise<{ choices: Array<{ logprobs?: { content?: Array<{ top_logprobs?: TopLogprob[] }> | null } | null }> }> } };
  interruptGenerate?(): void;
}

export interface LoadProgress {
  text: string;
  /** 0 to 1 */
  progress: number;
}

/** Load the library from the CDN and create the engine. Downloads the model on first use (the browser caches it). */
export async function loadWebLlmEngine(modelId: string, onProgress?: (p: LoadProgress) => void): Promise<WebLlmEngine> {
  const gpu = await detectWebGpu();
  if (!gpu.ok) throw new ProviderError(gpu.reason);
  let lib: { CreateMLCEngine(id: string, cfg: Record<string, unknown>): Promise<WebLlmEngine> };
  try {
    lib = await import(/* @vite-ignore */ WEBLLM_CDN_URL);
  } catch (e) {
    throw new ProviderError(`Could not load the browser model library from the CDN (${e instanceof Error ? e.message : String(e)}). Check the network or a content security policy.`);
  }
  return lib.CreateMLCEngine(modelId, { initProgressCallback: (p: LoadProgress) => onProgress?.({ text: p.text, progress: p.progress }) });
}

export interface WebLlmOptions {
  model: string;
  /** Replace the engine loader (tests). */
  load?: (modelId: string, onProgress?: (p: LoadProgress) => void) => Promise<WebLlmEngine>;
  onProgress?: (p: LoadProgress) => void;
}

export function createWebLlmProvider(o: WebLlmOptions): DecisionModel {
  let engine: Promise<WebLlmEngine> | null = null;
  const get = (): Promise<WebLlmEngine> => {
    if (!engine) {
      engine = (o.load ?? loadWebLlmEngine)(o.model, o.onProgress);
      engine.catch(() => { engine = null; });
    }
    return engine;
  };
  // One request at a time: the engine runs a single generation.
  let chain: Promise<unknown> = Promise.resolve();
  const firstTop = async (e: WebLlmEngine, user: string, signal: AbortSignal): Promise<TopLogprob[]> => {
    if (signal.aborted) throw new DOMException('Aborted', 'AbortError');
    const onAbort = (): void => e.interruptGenerate?.();
    signal.addEventListener('abort', onAbort, { once: true });
    try {
      const r = await e.chat.completions.create({
        messages: [{ role: 'system', content: SYSTEM }, { role: 'user', content: user }],
        max_tokens: 1, temperature: 0, logprobs: true, top_logprobs: 5, stream: false,
      });
      if (signal.aborted) throw new DOMException('Aborted', 'AbortError');
      const top = r.choices[0]?.logprobs?.content?.[0]?.top_logprobs;
      if (!top || top.length === 0) throw new ProviderError('The browser model returned no log probabilities.');
      return top;
    } finally {
      signal.removeEventListener('abort', onAbort);
    }
  };
  const run = async (state: JsonObject, questions: Questions, signal: AbortSignal): Promise<Answers> => {
    const e = await get();
    const answers: Record<string, Answer> = {};
    for (const [name, q] of Object.entries(questions)) {
      if (q.type === 'choice') {
        const options = Object.keys(q.criteria);
        const labels = labelsFor(options);
        const top = await firstTop(e, choicePrompt(state, q.instructions, options, options.map((k) => q.criteria[k]!), labels), signal);
        const r = probsFromTop(top, labels);
        if (!r) throw new ProviderError('The browser model did not answer with an option letter.');
        const probabilities: Record<string, number> = {};
        let best = 0;
        options.forEach((opt, i) => {
          probabilities[opt] = Math.round(r.p[i]! * 1e4) / 1e4;
          if (r.p[i]! > r.p[best]!) best = i;
        });
        answers[name] = { type: 'choice', choice: options[best]!, confidence: Math.round(r.p[best]! * r.mass * 1e4) / 1e4, probabilities };
      } else if (q.type === 'noul') {
        const y = yesFromTop(await firstTop(e, noulPrompt(state, q.instructions), signal));
        if (y === null) throw new ProviderError('The browser model did not answer Y or N.');
        answers[name] = { type: 'noul', noul: Math.round(y * 1e4) / 1e4 };
      } else {
        const options = q.criteria.map((_, i) => String(i));
        const labels = labelsFor(options);
        const top = await firstTop(e, choicePrompt(state, q.instructions, options, q.criteria, labels), signal);
        const r = probsFromTop(top, labels);
        if (!r) throw new ProviderError('The browser model did not answer with a level letter.');
        const probabilities: Record<string, number> = {};
        let best = 0;
        options.forEach((opt, i) => {
          probabilities[opt] = Math.round(r.p[i]! * 1e4) / 1e4;
          if (r.p[i]! > r.p[best]!) best = i;
        });
        answers[name] = { type: 'score', score: best, confidence: Math.round(r.p[best]! * r.mass * 1e4) / 1e4, probabilities };
      }
    }
    return { model: `webllm:${o.model}`, answers };
  };
  return {
    provider: 'webllm',
    decide(state, questions, signal): Promise<Answers> {
      const next = chain.then(() => run(state, questions, signal));
      chain = next.catch(() => undefined);
      return next;
    },
  };
}
