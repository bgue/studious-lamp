// Settings of the classifier, as a discriminated union on `provider`. Validated on load with plain messages.
// The API key is NOT a setting: it never enters this object, a params document, a share link, a saved view or a preset.
// It lives in keyStore.ts.

import { JEV_DEFAULT_ENDPOINT, JEV_DEFAULT_MODEL, isMovingAlias } from './jevAdapter';
import { WEBLLM_DEFAULT_MODEL, WEBLLM_MODELS } from './providers/webllm';

export const PROVIDERS = ['off', 'jev', 'webllm', 'mock'] as const;
export type ProviderId = (typeof PROVIDERS)[number];

export interface ClassifyShared {
  /** URL of a schema file (`xray-classification-schema/1`). Empty: the built-in placeholder schema. */
  schemaUrl: string;
  /** Results below this need review. null: the value of the schema. */
  minConfidence: number | null;
  /** Write the results as properties under the pset name of the schema. */
  writePset: boolean;
}
export interface JevSettings {
  provider: 'jev';
  /** An absolute http(s) URL, or a same-origin path such as /api/jev (a proxy). */
  endpoint: string;
  model: string;
  timeoutMs: number;
  /** Requests in flight. */
  concurrency: number;
  /** Cap of the JSON state that is sent, in bytes. */
  maxStateBytes: number;
}
export interface WebLlmSettings {
  provider: 'webllm';
  webllmModel: string;
}
export type ClassifySettings = ClassifyShared & ({ provider: 'off' } | JevSettings | WebLlmSettings | { provider: 'mock' });

export const JEV_DEFAULTS = {
  endpoint: JEV_DEFAULT_ENDPOINT,
  model: JEV_DEFAULT_MODEL,
  timeoutMs: 30_000,
  concurrency: 4,
  maxStateBytes: 4000,
} as const;

/** Every field at once: the form behind the union. The drawer edits this; `toSettings` picks the part that the provider uses. */
export interface ClassifyDraft extends ClassifyShared {
  provider: ProviderId;
  endpoint: string;
  model: string;
  timeoutMs: number;
  concurrency: number;
  maxStateBytes: number;
  webllmModel: string;
}

export function defaultDraft(): ClassifyDraft {
  return { provider: 'off', schemaUrl: '', minConfidence: null, writePset: true, ...JEV_DEFAULTS, webllmModel: WEBLLM_DEFAULT_MODEL };
}

export function toSettings(d: ClassifyDraft): ClassifySettings {
  const shared: ClassifyShared = { schemaUrl: d.schemaUrl, minConfidence: d.minConfidence, writePset: d.writePset };
  switch (d.provider) {
    case 'jev':
      return { ...shared, provider: 'jev', endpoint: d.endpoint, model: d.model, timeoutMs: d.timeoutMs, concurrency: d.concurrency, maxStateBytes: d.maxStateBytes };
    case 'webllm':
      return { ...shared, provider: 'webllm', webllmModel: d.webllmModel };
    case 'mock':
      return { ...shared, provider: 'mock' };
    default:
      return { ...shared, provider: 'off' };
  }
}

export function toDraft(s: ClassifySettings, base: ClassifyDraft = defaultDraft()): ClassifyDraft {
  const d: ClassifyDraft = { ...base, provider: s.provider, schemaUrl: s.schemaUrl, minConfidence: s.minConfidence, writePset: s.writePset };
  if (s.provider === 'jev') Object.assign(d, { endpoint: s.endpoint, model: s.model, timeoutMs: s.timeoutMs, concurrency: s.concurrency, maxStateBytes: s.maxStateBytes });
  if (s.provider === 'webllm') d.webllmModel = s.webllmModel;
  return d;
}

export interface SettingsCheck {
  /** The settings with every bad value replaced by its default. */
  settings: ClassifySettings;
  /** Plain-language problems. Each names the setting and what was done. */
  errors: string[];
  /** Things that work but deserve a second look. */
  warnings: string[];
}

const isObj = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
const SECRET_NAME = /key|token|secret|password|authorization|bearer/i;
const KNOWN = new Set(['provider', 'schemaUrl', 'minConfidence', 'writePset', 'endpoint', 'model', 'timeoutMs', 'concurrency', 'maxStateBytes', 'webllmModel']);

/** Problem with an endpoint or schema URL, or null. Accepts an absolute http(s) URL or a path on the same origin. */
export function urlProblem(u: string, what: string): string | null {
  const t = u.trim();
  if (!t) return `${what} is empty.`;
  if (t.startsWith('//')) return `${what} must not start with "//". Use a full https:// address or a path that starts with a single "/".`;
  if (t.startsWith('/') || t.startsWith('./') || t.startsWith('../')) return null;
  let p: URL;
  try {
    p = new URL(t);
  } catch {
    return `${what} "${t}" is not a web address. Write it as https://host/path, or as a path such as /api/jev.`;
  }
  if (p.protocol !== 'https:' && p.protocol !== 'http:') return `${what} must use https:// or http://, not ${p.protocol}.`;
  if (p.username || p.password) return `${what} must not contain a user name or password. Put the API key in the key box.`;
  return null;
}

const isLocal = (u: string): boolean => {
  try {
    const h = new URL(u, 'http://localhost').hostname;
    return h === 'localhost' || h === '127.0.0.1' || h === '[::1]' || !/^https?:/i.test(u);
  } catch {
    return false;
  }
};

function int(o: Record<string, unknown>, k: string, def: number, lo: number, hi: number, errors: string[]): number {
  const v = o[k];
  if (v === undefined) return def;
  if (typeof v !== 'number' || !Number.isInteger(v) || v < lo || v > hi) {
    errors.push(`${k} must be a whole number from ${lo} to ${hi}. Using ${def}.`);
    return def;
  }
  return v;
}

/** Check untrusted settings (from a params document, a share link or storage). Never throws. */
export function validateSettings(raw: unknown): SettingsCheck {
  const errors: string[] = [];
  const warnings: string[] = [];
  const d = defaultDraft();
  if (raw === undefined || raw === null) return { settings: toSettings(d), errors, warnings };
  if (!isObj(raw)) return { settings: toSettings(d), errors: ['The classify settings must be an object. Using the defaults.'], warnings };
  for (const k of Object.keys(raw)) {
    if (SECRET_NAME.test(k)) errors.push(`"${k}" looks like a secret. Settings never hold an API key, so it was ignored. Type the key in the key box of the Classify drawer.`);
    else if (!KNOWN.has(k)) warnings.push(`Unknown setting "${k}" was ignored.`);
  }
  const prov = raw['provider'];
  if (prov !== undefined) {
    if ((PROVIDERS as readonly unknown[]).includes(prov)) d.provider = prov as ProviderId;
    else errors.push(`provider must be one of ${PROVIDERS.join(', ')}. Using "off".`);
  }
  if (raw['schemaUrl'] !== undefined) {
    if (typeof raw['schemaUrl'] !== 'string') errors.push('schemaUrl must be text. Using the built-in schema.');
    else if (raw['schemaUrl'].trim() === '') d.schemaUrl = '';
    else {
      const p = urlProblem(raw['schemaUrl'], 'schemaUrl');
      if (p) errors.push(`${p} Using the built-in schema.`);
      else d.schemaUrl = raw['schemaUrl'].trim();
    }
  }
  if (raw['minConfidence'] !== undefined && raw['minConfidence'] !== null) {
    const v = raw['minConfidence'];
    if (typeof v !== 'number' || !Number.isFinite(v) || v < 0 || v > 1) errors.push('minConfidence must be a number from 0 to 1. Using the value of the schema.');
    else d.minConfidence = v;
  }
  if (raw['writePset'] !== undefined) {
    if (typeof raw['writePset'] === 'boolean') d.writePset = raw['writePset'];
    else errors.push('writePset must be true or false. Using true.');
  }
  // Fields of the providers are checked when they are given, and always when the provider uses them.
  const usesJev = d.provider === 'jev';
  if (usesJev || raw['endpoint'] !== undefined) {
    if (raw['endpoint'] !== undefined) {
      if (typeof raw['endpoint'] !== 'string') errors.push(`endpoint must be text. Using ${JEV_DEFAULTS.endpoint}.`);
      else {
        const p = urlProblem(raw['endpoint'], 'endpoint');
        if (p) errors.push(`${p} Using ${JEV_DEFAULTS.endpoint}.`);
        else d.endpoint = raw['endpoint'].trim();
      }
    }
    if (usesJev && /^http:/i.test(d.endpoint) && !isLocal(d.endpoint)) warnings.push('The endpoint uses http://, so the API key and the element data travel without encryption. Use https://.');
  }
  if (usesJev || raw['model'] !== undefined) {
    if (raw['model'] !== undefined) {
      const m = raw['model'];
      if (typeof m !== 'string' || !m.trim() || m.length > 100) errors.push(`model must be a model id of 1 to 100 characters. Using ${JEV_DEFAULTS.model}.`);
      else d.model = m.trim();
    }
    if (usesJev && isMovingAlias(d.model)) warnings.push(`"${d.model}" is a moving alias: the answers can change when the vendor ships a new version. Use a pinned id such as ${JEV_DEFAULTS.model} when results must be repeatable.`);
  }
  d.timeoutMs = int(raw, 'timeoutMs', d.timeoutMs, 1000, 300_000, errors);
  d.concurrency = int(raw, 'concurrency', d.concurrency, 1, 16, errors);
  d.maxStateBytes = int(raw, 'maxStateBytes', d.maxStateBytes, 500, 64_000, errors);
  if (raw['webllmModel'] !== undefined) {
    const m = raw['webllmModel'];
    if (typeof m !== 'string' || !m.trim()) errors.push(`webllmModel must be a model id. Using ${WEBLLM_DEFAULT_MODEL}.`);
    else {
      d.webllmModel = m.trim();
      if (!WEBLLM_MODELS.some((x) => x.id === d.webllmModel)) warnings.push(`webllmModel "${d.webllmModel}" is not one of the tested models (${WEBLLM_MODELS.map((x) => x.id).join(', ')}).`);
    }
  }
  return { settings: toSettings(d), errors, warnings };
}

/** The label that a person sees for the effective minimum confidence. */
export function effectiveMinConfidence(s: ClassifyShared, schemaMin: number): number {
  return s.minConfidence ?? schemaMin;
}
