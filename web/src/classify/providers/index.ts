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
import { createD3BrowserProvider } from './d3';
import type { D3BrowserOptions } from './d3';
import { D3_STATE_BYTES_DEFAULT } from './d3Config';
import { createJevProvider } from './jev';
import { createMockProvider } from './mock';
import { createWebLlmProvider, customModelId } from './webllm';
import type { LoadProgress, WebLlmOptions } from './webllm';

export interface ProviderDeps {
  /** The API key, read at call time. Never stored in the settings. */
  apiKey: () => string | null;
  /** The Hugging Face token, read at load time. Never stored in the settings. */
  hfToken?: () => string | null;
  /** The API key of the d3 endpoint (its own entry: a Jev key is never sent to a d3 server). Read at call time. */
  d3ApiKey?: () => string | null;
  fetchImpl?: typeof fetch;
  onD3Progress?: (p: DecisionProgress) => void;
  /** The d3 browser backend asks this before it downloads files that are not cached. */
  d3Confirm?: D3BrowserOptions['confirmDownload'];
  d3Gpu?: D3BrowserOptions['gpu'];
  d3LoadOrt?: D3BrowserOptions['loadOrt'];
  d3LoadTokenizerLib?: D3BrowserOptions['loadTokenizerLib'];
  d3Source?: D3BrowserOptions['source'];
  /** Decode a picture into pixels (tests and Node benches; the page uses the browser's decoder). */
  d3Decode?: D3BrowserOptions['decodeImage'];
  d3CacheStorage?: D3BrowserOptions['cacheStorage'];
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

/**
 * A short hash of the picture settings: pictures change what the model sees, so they belong to the identity of a decision. Only what changes a
 * picture counts: the plan view only matters with the isolated picture, the margin only with the context picture.
 */
export function imageHash(s: { images: string; imageStyle: string; imagePlan: boolean; imageSize: number; imageMargin: number }): string {
  const iso = s.images === 'isolated' || s.images === 'both';
  const ctx = s.images === 'context' || s.images === 'both';
  return shortHash(`${s.images}|${s.imageStyle}|${iso && s.imagePlan ? 'plan' : '-'}|${s.imageSize}|${ctx ? s.imageMargin : '-'}`);
}

/** A short hash of what changes the SVG text: it belongs to the identity of a decision when it is sent. */
export function geometryHash(s: { geometryContext: boolean; imageMargin: number }): string {
  return shortHash(`svg|${s.geometryContext ? `ctx${s.imageMargin}` : '-'}`);
}

/** Does this provider put SVG geometry into the state? Jev and d3-edge (either backend); the short-premise providers (decision, webllm) never do. */
export function sendsGeometry(s: ClassifySettings): boolean {
  return s.geometryText === 'svg' && (s.provider === 'jev' || s.provider === 'd3');
}

/**
 * Does this provider send pictures with the current settings? d3 on the endpoint, d3 in the browser when its export has a vision graph
 * (`vision`, known after the repository is inspected), and Jev when its switch is on.
 */
export function sendsImages(s: ClassifySettings, vision = false): boolean {
  if (s.images === 'off') return false;
  if (s.provider === 'd3') return s.d3Backend === 'endpoint' || vision;
  return s.provider === 'jev' && s.jevImages;
}

export function createProvider(s: ClassifySettings, deps: ProviderDeps): DecisionModel | null {
  switch (s.provider) {
    case 'jev':
      return createJevProvider({ endpoint: s.endpoint, model: s.model, apiKey: deps.apiKey, timeoutMs: s.timeoutMs, sendImages: sendsImages(s), ...(deps.fetchImpl ? { fetchImpl: deps.fetchImpl } : {}) });
    case 'd3':
      if (s.d3Backend === 'endpoint') {
        return createJevProvider({ provider: 'd3', endpoint: s.d3Endpoint, model: s.d3Model, apiKey: deps.d3ApiKey ?? (() => null), timeoutMs: s.timeoutMs, sendImages: sendsImages(s), ...(deps.fetchImpl ? { fetchImpl: deps.fetchImpl } : {}) });
      }
      return createD3BrowserProvider({
        repo: s.d3Repo, revision: s.d3Revision, endpoint: s.d3HfEndpoint, device: s.d3Device,
        ...(deps.hfToken ? { token: deps.hfToken } : {}),
        ...(deps.d3Confirm ? { confirmDownload: deps.d3Confirm } : {}),
        ...(deps.onD3Progress ? { onProgress: deps.onD3Progress } : {}),
        ...(deps.d3Gpu ? { gpu: deps.d3Gpu } : {}),
        ...(deps.d3LoadOrt ? { loadOrt: deps.d3LoadOrt } : {}),
        ...(deps.d3LoadTokenizerLib ? { loadTokenizerLib: deps.d3LoadTokenizerLib } : {}),
        ...(deps.d3Source ? { source: deps.d3Source } : {}),
        ...(deps.d3Decode ? { decodeImage: deps.d3Decode } : {}),
        ...(deps.d3CacheStorage !== undefined ? { cacheStorage: deps.d3CacheStorage } : {}),
        ...(deps.fetchImpl ? { fetchImpl: deps.fetchImpl } : {}),
      });
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
export function providerId(s: ClassifySettings, o: { vision?: boolean } = {}): string {
  switch (s.provider) {
    case 'jev':
      return `jev:${s.model}${sendsImages(s) ? `@i${imageHash(s)}` : ''}${sendsGeometry(s) ? `@g${geometryHash(s)}` : ''}`;
    case 'd3': {
      const state = s.d3MaxStateBytes !== D3_STATE_BYTES_DEFAULT ? `@s${s.d3MaxStateBytes}` : '';
      if (s.d3Backend === 'endpoint') return `d3:endpoint:${s.d3Model}${state}${sendsImages(s) ? `@i${imageHash(s)}` : ''}${sendsGeometry(s) ? `@g${geometryHash(s)}` : ''}`;
      return `d3:browser:${s.d3Repo}@${s.d3Revision.slice(0, 8)}${state}${sendsImages(s, o.vision === true) ? `@i${imageHash(s)}` : ''}${sendsGeometry(s) ? `@g${geometryHash(s)}` : ''}`;
    }
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
