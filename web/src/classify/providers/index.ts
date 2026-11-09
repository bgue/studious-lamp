// Providers behind one interface (DecisionModel): decision (a small NLI model in the browser), webllm, jev, mock.
// `off` means no provider: rules and cache only.

import { noulQuestion } from '../jevAdapter';
import type { Questions } from '../jevAdapter';
import { customHypotheses } from '../settings';
import type { ClassifySettings } from '../settings';
import { ProviderError } from '../types';
import type { DecisionModel } from '../types';
import { createDecisionProvider } from './decision';
import type { DecisionOptions, DecisionProgress } from './decision';
import { createJevProvider } from './jev';
import { createMockProvider } from './mock';
import { createWebLlmProvider, customModelId } from './webllm';
import type { LoadProgress, WebLlmOptions } from './webllm';

export interface ProviderDeps {
  /** The API key, read at call time. Never stored in the settings. */
  apiKey: () => string | null;
  /** The Hugging Face token, read at load time. Never stored in the settings. */
  hfToken?: () => string | null;
  fetchImpl?: typeof fetch;
  onWebLlmProgress?: (p: LoadProgress) => void;
  onDecisionProgress?: (p: DecisionProgress) => void;
  /** Replace the loaders (tests). */
  decisionLoad?: DecisionOptions['loadLib'];
  decisionGpu?: DecisionOptions['gpu'];
  webllmLoad?: WebLlmOptions['load'];
}

/** The chat model id of the webllm settings: the custom model when one is set. */
export function webllmChatModel(s: { webllmModel: string; webllmCustomModel: string; webllmCustomLib: string }): string {
  return s.webllmCustomModel && s.webllmCustomLib ? customModelId(s.webllmCustomModel) : s.webllmModel;
}

function shortHash(text: string): string {
  let h = 2166136261;
  for (let i = 0; i < text.length; i++) h = Math.imul(h ^ text.charCodeAt(i), 16777619);
  return (h >>> 0).toString(16).padStart(8, '0');
}

export function createProvider(s: ClassifySettings, deps: ProviderDeps): DecisionModel | null {
  switch (s.provider) {
    case 'jev':
      return createJevProvider({ endpoint: s.endpoint, model: s.model, apiKey: deps.apiKey, timeoutMs: s.timeoutMs, ...(deps.fetchImpl ? { fetchImpl: deps.fetchImpl } : {}) });
    case 'webllm':
      return createWebLlmProvider({
        model: webllmChatModel(s), mode: s.webllmMode, embedModel: s.webllmEmbedModel, temperature: s.embedTemperature, hybridMargin: s.hybridMargin,
        ...(s.webllmCustomModel && s.webllmCustomLib ? { custom: { model: s.webllmCustomModel, lib: s.webllmCustomLib } } : {}),
        ...(deps.onWebLlmProgress ? { onProgress: deps.onWebLlmProgress } : {}),
        ...(deps.webllmLoad ? { load: deps.webllmLoad } : {}),
      });
    case 'decision':
      return createDecisionProvider({
        model: s.hfModel, device: s.device, dtype: s.dtype, hfEndpoint: s.hfEndpoint, hypothesis: s.hypothesis,
        ...(deps.hfToken ? { token: deps.hfToken } : {}),
        ...(deps.onDecisionProgress ? { onProgress: deps.onDecisionProgress } : {}),
        ...(deps.decisionLoad ? { loadLib: deps.decisionLoad } : {}),
        ...(deps.decisionGpu ? { gpu: deps.decisionGpu } : {}),
        ...(deps.fetchImpl ? { fetchImpl: deps.fetchImpl } : {}),
      });
    case 'mock':
      return createMockProvider();
    default:
      return null;
  }
}

/** Id of the provider and model, for the cache key and the messages: "jev:jev-1.13.0", "webllm:Qwen2.5-...", "mock", "rules". */
export function providerId(s: ClassifySettings): string {
  switch (s.provider) {
    case 'jev':
      return `jev:${s.model}`;
    case 'webllm': {
      const chat = webllmChatModel(s);
      if (s.webllmMode === 'chat') return `webllm:${chat}`;
      const knobs = `T${s.embedTemperature}${s.webllmMode === 'hybrid' ? `,m${s.hybridMargin}` : ''}`;
      return s.webllmMode === 'embed' ? `webllm:embed:${s.webllmEmbedModel}@${knobs}` : `webllm:hybrid:${s.webllmEmbedModel}+${chat}@${knobs}`;
    }
    case 'decision':
      // Other hypothesis sentences give other decisions, so they are part of the identity.
      return `decision:${s.hfModel}${customHypotheses(s.hypothesis) ? `@h${shortHash(JSON.stringify(s.hypothesis))}` : ''}`;
    case 'mock':
      return 'mock:mock-1';
    default:
      return 'rules';
  }
}

export interface ConnectionTest {
  ok: boolean;
  /** The model id that the endpoint reported. */
  model?: string;
  ms: number;
  message: string;
}

/** Send one tiny yes/no question and report what came back. Never throws. */
export async function testConnection(provider: DecisionModel | null, signal: AbortSignal = new AbortController().signal): Promise<ConnectionTest> {
  if (!provider) return { ok: false, ms: 0, message: 'No provider is selected. Choose the Decision model, the Browser model, Jev or Mock first.' };
  const q: Questions = { ping: noulQuestion('The number 2 is smaller than the number 3.') };
  const t0 = Date.now();
  try {
    const a = await provider.decide({ test: true }, q, signal);
    const ms = Date.now() - t0;
    return { ok: true, model: a.model, ms, message: `Connected. Model ${a.model} answered in ${ms} ms.` };
  } catch (e) {
    return { ok: false, ms: Date.now() - t0, message: e instanceof ProviderError || e instanceof Error ? e.message : String(e) };
  }
}
