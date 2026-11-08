// Providers behind one interface (DecisionModel): jev, webllm, mock. `off` means no provider: rules and cache only.

import { noulQuestion } from '../jevAdapter';
import type { Questions } from '../jevAdapter';
import type { ClassifySettings } from '../settings';
import { ProviderError } from '../types';
import type { DecisionModel } from '../types';
import { createJevProvider } from './jev';
import { createMockProvider } from './mock';
import { createWebLlmProvider } from './webllm';
import type { LoadProgress } from './webllm';

export interface ProviderDeps {
  /** The API key, read at call time. Never stored in the settings. */
  apiKey: () => string | null;
  fetchImpl?: typeof fetch;
  onWebLlmProgress?: (p: LoadProgress) => void;
}

export function createProvider(s: ClassifySettings, deps: ProviderDeps): DecisionModel | null {
  switch (s.provider) {
    case 'jev':
      return createJevProvider({ endpoint: s.endpoint, model: s.model, apiKey: deps.apiKey, timeoutMs: s.timeoutMs, ...(deps.fetchImpl ? { fetchImpl: deps.fetchImpl } : {}) });
    case 'webllm':
      return createWebLlmProvider({ model: s.webllmModel, ...(deps.onWebLlmProgress ? { onProgress: deps.onWebLlmProgress } : {}) });
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
    case 'webllm':
      return `webllm:${s.webllmModel}`;
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
  if (!provider) return { ok: false, ms: 0, message: 'No provider is selected. Choose Jev, Browser model or Mock first.' };
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
