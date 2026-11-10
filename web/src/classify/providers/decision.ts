// The decision model: a small zero-shot NLI classifier (DeBERTa-v3 family) that runs in the browser with transformers.js
// (WebGPU, or WASM when there is no WebGPU). It DECIDES, it does not generate: every choice answer has a probability for
// every option, and a yes/no answer has p(yes). That is the Jev shape, so the pipeline does not know which provider it uses.
//
// The library is NOT bundled. It is loaded at run time from a CDN, from an exact pinned version, and only when this
// provider is used, so the single-file viewer does not grow. The weights come from huggingface.co (or `hfEndpoint`), on
// first use, and the browser keeps them in the Cache API.
//
// How a question becomes NLI passes (premise = a compact text of the element, hypothesis = one sentence per option):
//   choice  one pair per option; the entailment logits are softmaxed over ALL options (multi_label: false in the pipeline)
//           -> probabilities that sum to 1; confidence = the top probability
//   noul    one pair for the statement; p(yes) = softmax([contradiction, entailment])[1]. A binary zero-shot model
//           (labels entailment / not_entailment) uses not_entailment as the "against" score
// All pairs of one request share the premise, so they run in batches (one forward pass per batch, not per pair).

import { ProviderError } from '../types';
import type { DecisionModel } from '../types';
import type { Answer, Answers, JsonObject, JsonValue, Questions } from '../jevAdapter';

// ---------------------------------------------------------------- the library

/** Exact version, never a range. The viewer never bundles it. */
export const TRANSFORMERS_VERSION = '4.3.2';
/** The self-contained build of the package (it bundles onnxruntime-web). jsDelivr, exact version. */
export const TRANSFORMERS_CDN_URL = `https://cdn.jsdelivr.net/npm/@huggingface/transformers@${TRANSFORMERS_VERSION}/dist/transformers.min.js`;
export const HF_DEFAULT_ENDPOINT = 'https://huggingface.co';
/** The Cache API entry that transformers.js writes the weights (and the WASM runtime) to. */
export const TRANSFORMERS_CACHE_NAME = 'transformers-cache';

export type DecisionDevice = 'auto' | 'webgpu' | 'wasm';
export type DecisionDtype = 'auto' | 'fp32' | 'fp16' | 'q8' | 'q4';
export const DECISION_DEVICES: readonly DecisionDevice[] = ['auto', 'webgpu', 'wasm'];
export const DECISION_DTYPES: readonly DecisionDtype[] = ['auto', 'fp32', 'fp16', 'q8', 'q4'];

/** The part of transformers.js that this provider uses (a fake in the tests). */
export interface TransformersModule {
  pipeline(task: string, model: string, opts?: Record<string, unknown>): Promise<ZeroShotPipe>;
  env: Record<string, unknown>;
}
export interface ZeroShotPipe {
  /** The public call of the zero-shot pipeline. */
  (text: string, labels: string[], opts?: { hypothesis_template?: string; multi_label?: boolean }): Promise<{ labels: string[]; scores: number[] }>;
  /** Present in transformers.js: used for batched pairs (raw logits). Absent: the public call is used instead. */
  tokenizer?: (text: string[], opts: Record<string, unknown>) => unknown;
  model?: ((inputs: unknown) => Promise<{ logits: { data: ArrayLike<number>; dims?: number[] } }>) & { config?: { label2id?: Record<string, number>; id2label?: Record<string, string> } };
  dispose?(): Promise<void> | void;
}

// ---------------------------------------------------------------- the model catalog

export interface DecisionModelInfo {
  id: string;
  label: string;
  /** Download in MB for each data type that the repository has (the ONNX file sizes on huggingface.co). */
  sizesMB: Partial<Record<Exclude<DecisionDtype, 'auto'>, number>>;
  note: string;
}

/** Checked against huggingface.co (the model API with file sizes): every id has a config with an entailment label and ONNX weights. */
export const DECISION_MODELS: readonly DecisionModelInfo[] = [
  { id: 'MoritzLaurer/deberta-v3-xsmall-zeroshot-v1.1-all-33', label: 'DeBERTa-v3 xsmall zero-shot (default)', sizesMB: { fp32: 284, q8: 87 }, note: 'Trained for zero-shot on 33 datasets. Small and fast.' },
  { id: 'MoritzLaurer/xtremedistil-l6-h256-zeroshot-v1.1-all-33', label: 'xtremedistil L6 zero-shot (tiniest)', sizesMB: { fp32: 51, q8: 13 }, note: 'The smallest and fastest. Less exact.' },
  { id: 'Xenova/nli-deberta-v3-xsmall', label: 'DeBERTa-v3 xsmall NLI (has fp16)', sizesMB: { fp32: 284, fp16: 143, q8: 87 }, note: 'Plain NLI (SNLI and MNLI). Has fp16 weights for WebGPU.' },
  { id: 'MoritzLaurer/deberta-v3-base-zeroshot-v1.1-all-33', label: 'DeBERTa-v3 base zero-shot (better)', sizesMB: { fp32: 739, q8: 244 }, note: 'More exact, about 3 times slower.' },
  { id: 'MoritzLaurer/deberta-v3-base-zeroshot-v2.0', label: 'DeBERTa-v3 base zero-shot v2.0', sizesMB: { fp32: 739 }, note: 'Only fp32 weights: a large download.' },
];
export const DECISION_DEFAULT_MODEL = DECISION_MODELS[0]!.id;
export const decisionModelInfo = (id: string): DecisionModelInfo | undefined => DECISION_MODELS.find((m) => m.id === id);

/** Is the text shaped like a Hugging Face repository id, "owner/name"? Returns a plain problem, or null. */
export function hfModelProblem(id: unknown): string | null {
  if (typeof id !== 'string' || !id.trim()) return 'The Hugging Face model id is empty. Write it as owner/name, for example MoritzLaurer/deberta-v3-xsmall-zeroshot-v1.1-all-33.';
  const t = id.trim();
  if (/^https?:\/\//i.test(t)) return `"${t}" is a web address. Write only the model id, as owner/name.`;
  if (t.length > 200) return 'The Hugging Face model id is too long.';
  if (!/^[A-Za-z0-9][A-Za-z0-9._-]*\/[A-Za-z0-9][A-Za-z0-9._-]*$/.test(t) || t.includes('..')) {
    return `"${t}" is not a model id. Use owner/name with letters, digits, dots, dashes and underscores, for example MoritzLaurer/deberta-v3-xsmall-zeroshot-v1.1-all-33.`;
  }
  return null;
}

export function describeDecisionModel(id: string, dtype: DecisionDtype = 'auto'): string {
  const m = decisionModelInfo(id);
  if (!m) return `${id}: a model from Hugging Face. The download size is shown when the model is checked.`;
  const sizes = Object.entries(m.sizesMB).map(([k, v]) => `${k} ${v} MB`).join(', ');
  const one = dtype !== 'auto' ? m.sizesMB[dtype] : undefined;
  return `${m.label}: download ${one !== undefined ? `${one} MB (${dtype})` : sizes}. ${m.note}`;
}

// ---------------------------------------------------------------- the model config check

export interface NliConfigCheck {
  ok: boolean;
  /** Plain-language reason when not ok. */
  message: string;
  /** Labels of the model in the order of their ids. */
  labels: string[];
  entailmentId?: number;
  /** The id of the "against" label: contradiction, else not_entailment. */
  againstId?: number;
  binary?: boolean;
}

/**
 * A zero-shot model is an NLI model: its config has an `entailment` label and a label to set it against (`contradiction`, or
 * `not_entailment` in the binary zero-shot models). Anything else (an LLM, an embedding model, a sentiment model) cannot decide.
 */
export function checkNliConfig(cfg: unknown, id = 'This model'): NliConfigCheck {
  const c = cfg && typeof cfg === 'object' ? (cfg as Record<string, unknown>) : null;
  if (!c) return { ok: false, message: `${id} has no readable config.json.`, labels: [] };
  const arch = Array.isArray(c['architectures']) ? (c['architectures'] as unknown[]).map(String) : [];
  const l2i = c['label2id'] && typeof c['label2id'] === 'object' ? (c['label2id'] as Record<string, unknown>) : {};
  const i2l = c['id2label'] && typeof c['id2label'] === 'object' ? (c['id2label'] as Record<string, unknown>) : {};
  const byId = new Map<number, string>();
  for (const [k, v] of Object.entries(i2l)) if (Number.isInteger(Number(k))) byId.set(Number(k), String(v).toLowerCase());
  for (const [k, v] of Object.entries(l2i)) if (typeof v === 'number') byId.set(v, k.toLowerCase());
  const labels = [...byId.entries()].sort((a, b) => a[0] - b[0]).map(([, v]) => v);
  const want = 'It needs a sequence-classification (NLI) model with an "entailment" label and a "contradiction" or "not_entailment" label, such as a DeBERTa zero-shot model.';
  if (arch.length && !arch.some((a) => /SequenceClassification/i.test(a))) {
    return { ok: false, message: `${id} is not a classifier (its architecture is ${arch.join(', ')}), so it cannot decide among options. ${want}`, labels };
  }
  const ent = [...byId.entries()].find(([, v]) => v === 'entailment');
  if (!ent) {
    return { ok: false, message: `${id} is not a zero-shot or NLI model: its labels are ${labels.length ? labels.join(', ') : 'missing'}, and none is "entailment". ${want}`, labels };
  }
  const against = [...byId.entries()].find(([, v]) => v === 'contradiction') ?? [...byId.entries()].find(([, v]) => v === 'not_entailment');
  if (!against) {
    return { ok: false, message: `${id} has an "entailment" label but no "contradiction" or "not_entailment" label (its labels are ${labels.join(', ')}). ${want}`, labels };
  }
  return { ok: true, message: '', labels, entailmentId: ent[0], againstId: against[0], binary: against[1] === 'not_entailment' };
}

export interface ModelInspection extends NliConfigCheck {
  /** Download sizes in MB from the Hub API, when it could be read. */
  sizesMB?: Partial<Record<Exclude<DecisionDtype, 'auto'>, number>>;
}

const DTYPE_FILE: Record<Exclude<DecisionDtype, 'auto'>, string> = { fp32: 'model.onnx', fp16: 'model_fp16.onnx', q8: 'model_quantized.onnx', q4: 'model_q4.onnx' };

/** Read config.json (and, when the Hub API answers, the file sizes) of a model, before any weights are downloaded. Never throws. */
export async function inspectModel(
  id: string,
  o: { endpoint: string; token?: string | null; fetchImpl?: typeof fetch; signal?: AbortSignal },
): Promise<ModelInspection> {
  const f = o.fetchImpl ?? globalThis.fetch.bind(globalThis);
  const base = o.endpoint.replace(/\/+$/, '');
  const headers: Record<string, string> = {};
  if (o.token) headers['Authorization'] = `Bearer ${o.token}`;
  let cfg: unknown;
  try {
    const r = await f(`${base}/${id}/resolve/main/config.json`, { headers, credentials: 'omit', ...(o.signal ? { signal: o.signal } : {}) });
    if (r.status === 404) return { ok: false, message: `"${id}" was not found at ${base}. Check the spelling of the model id and the Hugging Face endpoint.`, labels: [] };
    if (r.status === 401 || r.status === 403) return { ok: false, message: `"${id}" needs a Hugging Face token (HTTP ${r.status}). It is a private or gated model. Save a token with access to it, and accept its terms on the model page.`, labels: [] };
    if (!r.ok) return { ok: false, message: `${base} answered HTTP ${r.status} for the config of "${id}".`, labels: [] };
    cfg = await r.json();
  } catch (e) {
    if (o.signal?.aborted) throw e;
    return { ok: false, message: `Could not reach ${base} (${e instanceof Error ? e.message : String(e)}). Check the network, the endpoint setting and any content security policy.`, labels: [] };
  }
  const check = checkNliConfig(cfg, `"${id}"`);
  if (!check.ok) return check;
  const out: ModelInspection = { ...check };
  try {
    const r = await f(`${base}/api/models/${id}?blobs=true`, { headers, credentials: 'omit', ...(o.signal ? { signal: o.signal } : {}) });
    if (r.ok) {
      const j = (await r.json()) as { siblings?: Array<{ rfilename?: string; size?: number }> };
      const sizes: NonNullable<ModelInspection['sizesMB']> = {};
      for (const s of j.siblings ?? []) {
        for (const [dt, file] of Object.entries(DTYPE_FILE)) if (s.rfilename === `onnx/${file}` && typeof s.size === 'number') sizes[dt as keyof typeof sizes] = Math.round(s.size / 1e6);
      }
      if (Object.keys(sizes).length) out.sizesMB = sizes;
    }
  } catch {
    /* the API is optional (a mirror may not have it) */
  }
  if (out.sizesMB && Object.keys(out.sizesMB).length === 0) delete out.sizesMB;
  return out;
}

// ---------------------------------------------------------------- device and data type

export interface RuntimeChoice {
  device: 'webgpu' | 'wasm';
  /** Concrete data type, or `auto` -> chosen below. */
  dtype: Exclude<DecisionDtype, 'auto'>;
  /** A plain note for the drawer. Empty when there is nothing to say. */
  note: string;
  /** Data types to try in order when the dtype was `auto` and a file is missing. */
  fallbacks: Array<Exclude<DecisionDtype, 'auto'>>;
}

export interface GpuProbe {
  present: boolean;
  /** An adapter was obtained. */
  adapter: boolean;
  f16: boolean;
}

export const WASM_NOTE = 'Slower: this browser has no WebGPU, so the model runs on the CPU with WebAssembly. Expect a few seconds per element type.';

/**
 * Pick the device and data type. Pure: the GPU probe is an argument.
 *  - device auto: WebGPU when the browser has it (and gives an adapter), else WASM
 *  - dtype auto: fp16 on WebGPU when the adapter supports it (and the model has it), else fp32; q8 on WASM
 * A forced device that is not there is an error with a plain message (no silent switch).
 */
export function chooseRuntime(device: DecisionDevice, dtype: DecisionDtype, model: string, gpu: GpuProbe): RuntimeChoice {
  let dev: 'webgpu' | 'wasm';
  let note = '';
  if (device === 'webgpu') {
    if (!gpu.present) throw new ProviderError('The device is set to WebGPU, but this browser has no WebGPU. Set the device to Auto or WASM, or use a recent Chrome or Edge on a computer with a GPU.');
    if (!gpu.adapter) throw new ProviderError('The device is set to WebGPU, but the browser found no GPU adapter. Set the device to Auto or WASM.');
    dev = 'webgpu';
  } else if (device === 'wasm') {
    dev = 'wasm';
    note = WASM_NOTE.replace('this browser has no WebGPU, so the model runs', 'the device is set to WASM, so the model runs');
  } else if (gpu.present && gpu.adapter) {
    dev = 'webgpu';
  } else {
    dev = 'wasm';
    note = gpu.present ? 'Slower: WebGPU is present but the browser found no GPU adapter, so the model runs on the CPU with WebAssembly.' : WASM_NOTE;
  }
  const info = decisionModelInfo(model);
  const has = (d: Exclude<DecisionDtype, 'auto'>): boolean => !info || info.sizesMB[d] !== undefined;
  let pick: Exclude<DecisionDtype, 'auto'>;
  const fallbacks: RuntimeChoice['fallbacks'] = [];
  if (dtype !== 'auto') pick = dtype;
  else if (dev === 'webgpu') {
    pick = gpu.f16 && has('fp16') ? 'fp16' : 'fp32';
    if (pick === 'fp16') fallbacks.push('fp32');
  } else {
    pick = has('q8') ? 'q8' : 'fp32';
    if (pick === 'q8') fallbacks.push('fp32');
  }
  return { device: dev, dtype: pick, note, fallbacks };
}

/** Look at the browser GPU. `nav` is injectable. */
export async function probeGpu(nav: { gpu?: { requestAdapter(): Promise<{ features?: { has(f: string): boolean } } | null> } } | undefined = typeof navigator === 'undefined' ? undefined : (navigator as never)): Promise<GpuProbe> {
  if (!nav || !nav.gpu) return { present: false, adapter: false, f16: false };
  try {
    const a = await nav.gpu.requestAdapter();
    return { present: true, adapter: !!a, f16: !!a?.features?.has('shader-f16') };
  } catch {
    return { present: true, adapter: false, f16: false };
  }
}

// ---------------------------------------------------------------- the premise (what the model reads)

/** Rough token estimate for English-and-identifier text with the DeBERTa SentencePiece vocabulary: 1 token per 3 characters. */
export const CHARS_PER_TOKEN = 3;
/** Tokens of the premise. The hypothesis needs about 40 more; the model limit is 512. A short premise is also faster. */
export const DEFAULT_PREMISE_TOKENS = 160;

const KEY_PROPS = ['PredefinedType', 'ObjectType', 'LoadBearing', 'IsExternal', 'FireRating', 'Function', 'Category', 'Application', 'Description', 'Reference', 'Status', 'NominalDiameter', 'FlowDirection', 'PipeSegmentType', 'System'];

/** "IfcDuctSegment" -> "duct segment". */
export function humanizeClass(c: string): string {
  return c.replace(/^Ifc/, '').replace(/([a-z0-9])([A-Z])/g, '$1 $2').replace(/([A-Z]+)([A-Z][a-z])/g, '$1 $2').toLowerCase();
}

const isObj = (v: JsonValue | undefined): v is { [k: string]: JsonValue } => !!v && typeof v === 'object' && !Array.isArray(v);
const text = (v: JsonValue | undefined): string => (typeof v === 'string' ? v.trim() : typeof v === 'number' || typeof v === 'boolean' ? String(v) : '');

function keyProps(psets: JsonValue | undefined, max: number): string[] {
  if (!isObj(psets)) return [];
  const found = new Map<string, string>();
  for (const set of Object.values(psets)) {
    if (!isObj(set)) continue;
    for (const [k, v] of Object.entries(set)) {
      const t = text(v);
      if (!t) continue;
      const hit = KEY_PROPS.find((p) => p.toLowerCase() === k.toLowerCase());
      if (hit && !found.has(hit)) found.set(hit, t);
    }
  }
  return KEY_PROPS.filter((k) => found.has(k)).slice(0, max).map((k) => `${k} ${found.get(k)}`);
}

/**
 * A compact premise from the element state. The most informative fields come first (class, type, name, key properties,
 * system), then context (material, storey, parent). Cut to `maxTokens` at a field boundary; one field is shortened when
 * it alone is too long. Class and name always stay.
 */
export function buildPremise(state: JsonObject, maxTokens = DEFAULT_PREMISE_TOKENS): string {
  const parts: string[] = [];
  const cls = text(state['class']);
  if (cls) parts.push(`Element class ${cls}${/^Ifc/.test(cls) ? ` (${humanizeClass(cls)})` : ''}.`);
  const type = isObj(state['type']) ? state['type'] : null;
  if (type) {
    const n = text(type['name']);
    const c = text(type['class']);
    if (n) parts.push(`Type ${n}${c ? ` (${humanizeClass(c)})` : ''}.`);
  }
  const name = text(state['name']);
  if (name) parts.push(`Name ${name}.`);
  const props = [...keyProps(state['psets'], 5), ...(type ? keyProps(type['psets'], 2) : [])];
  const seen = new Set<string>();
  const uniq = props.filter((p) => (seen.has(p) ? false : (seen.add(p), true)));
  if (uniq.length) parts.push(`Properties: ${uniq.join(', ')}.`);
  const systems = Array.isArray(state['systems']) ? (state['systems'] as JsonValue[]).map(text).filter(Boolean) : [];
  if (systems.length) parts.push(`System ${systems.slice(0, 2).join(', ')}.`);
  const material = text(state['material']);
  if (material) parts.push(`Material ${material}.`);
  const hier = Array.isArray(state['hierarchy']) ? (state['hierarchy'] as JsonValue[]).map(text).filter(Boolean) : [];
  const storey = [...hier].reverse().find((h) => /storey|level/i.test(h)) ?? hier[hier.length - 1];
  if (storey) parts.push(`Storey ${storey.replace(/^[A-Za-z]+:\s*/, '')}.`);
  const parents = Array.isArray(state['parents']) ? (state['parents'] as JsonValue[]).filter(isObj) : [];
  if (parents[0]) {
    const pc = text(parents[0]['class']);
    const pn = text(parents[0]['name']);
    if (pc) parts.push(`Hosted in ${humanizeClass(pc)}${pn ? ` ${pn}` : ''}.`);
  }
  if (state['building_context'] === true) parts.push('It is inside a building.');
  else if (state['building_context'] === false) parts.push('It is not inside a building.');

  const budget = Math.max(20, Math.floor(maxTokens)) * CHARS_PER_TOKEN;
  const out: string[] = [];
  let used = 0;
  for (const p of parts) {
    const add = (out.length ? 1 : 0) + p.length;
    if (used + add <= budget) {
      out.push(p);
      used += add;
      continue;
    }
    const room = budget - used - (out.length ? 1 : 0);
    // Shorten this field only when it is one of the first two (class, type) or nothing is there yet; otherwise stop.
    if (out.length < 2 && room > 12) out.push(`${p.slice(0, room - 1).trimEnd()}…`);
    break;
  }
  return out.join(' ');
}

// ---------------------------------------------------------------- hypotheses

export interface HypothesisTemplates {
  discipline: string;
  sub_discipline: string;
  masterformat: string;
  /** For a yes/no statement: `{}` is replaced by the statement. */
  building_element: string;
}
export const DEFAULT_HYPOTHESES: HypothesisTemplates = {
  discipline: 'This building element belongs to the {} discipline.',
  sub_discipline: 'This building element is part of {}.',
  masterformat: 'The work of this building element falls under {}.',
  building_element: '{}',
};
/** For a question that has no template of its own. */
export const FALLBACK_HYPOTHESIS = 'This building element is {}.';
export const HYPOTHESIS_KEYS = Object.keys(DEFAULT_HYPOTHESES) as Array<keyof HypothesisTemplates>;

/** Problem with a hypothesis template, or null. It must hold `{}` exactly once. */
export function hypothesisProblem(t: unknown, name: string): string | null {
  if (typeof t !== 'string' || !t.trim()) return `The ${name} hypothesis is empty.`;
  if (t.length > 300) return `The ${name} hypothesis is too long (300 characters at most).`;
  const n = t.split('{}').length - 1;
  if (n !== 1) return `The ${name} hypothesis must contain {} exactly once, where the option goes. It has ${n}.`;
  return null;
}

const DESC_CHARS = 90;

function lowerFirst(s: string): string {
  return /^[A-Z][a-z]/.test(s) ? s.charAt(0).toLowerCase() + s.slice(1) : s;
}

/**
 * The phrase for one option from its criteria text ("Title. Description ..."): the title and a short description cut at a
 * word boundary. "Mechanical and HVAC. Heating, ventilation: ducts, fans." -> "Mechanical and HVAC (heating, ventilation: ducts, fans)".
 */
export function optionPhrase(textOfOption: string, withDescription = true): string {
  const t = textOfOption.replace(/\s+/g, ' ').trim();
  const dot = t.search(/\.\s|\.$/);
  const title = (dot > 0 ? t.slice(0, dot) : t).trim();
  if (!withDescription || dot < 0) return title;
  let rest = t.slice(dot + 1).trim().replace(/\.$/, '');
  if (!rest) return title;
  if (rest.length > DESC_CHARS) {
    rest = rest.slice(0, DESC_CHARS);
    const sp = rest.lastIndexOf(' ');
    rest = `${sp > 40 ? rest.slice(0, sp) : rest}`.replace(/[,;:\s]+$/, '');
  }
  return `${title} (${lowerFirst(rest)})`;
}

export function hypothesisFor(template: string, phrase: string): string {
  return template.replace('{}', phrase);
}

// ---------------------------------------------------------------- the scorer: NLI pairs in batches

/** Counts that the drawer and the smoke test report. */
export interface DecisionStats {
  /** decide() calls (requests of the pipeline). */
  requests: number;
  /** (premise, hypothesis) pairs that went through the model. */
  pairs: number;
  /** Pairs that the pair cache answered. */
  cachedPairs: number;
  /** Forward passes (batches). */
  passes: number;
  /** Time in the model, ms. */
  ms: number;
}
export const emptyDecisionStats = (): DecisionStats => ({ requests: 0, pairs: 0, cachedPairs: 0, passes: 0, ms: 0 });

export function softmax(xs: readonly number[]): number[] {
  if (xs.length === 0) return [];
  const m = Math.max(...xs);
  const e = xs.map((x) => Math.exp(x - m));
  const s = e.reduce((a, b) => a + b, 0);
  return e.map((x) => x / s);
}

/** Entailment and "against" logits of one pair. */
export type PairLogits = [against: number, entail: number];

interface Scorer {
  /** Probability per hypothesis, softmaxed over the entailment logits (multi_label: false). */
  choice(premise: string, hyps: readonly string[], signal: AbortSignal): Promise<number[]>;
  /** p(the hypothesis is true): softmax of [against, entailment]. */
  yes(premise: string, hyp: string, signal: AbortSignal): Promise<number>;
  /** Several pairs of one premise at once (one pass per batch). Used by decide() to share batches across questions. */
  logits(premise: string, hyps: readonly string[], signal: AbortSignal): Promise<PairLogits[]>;
  readonly batched: boolean;
}

const PAIR_CACHE_MAX = 4000;

function rawScorer(pipe: ZeroShotPipe, stats: DecisionStats, batch: number): Scorer | null {
  const tok = pipe.tokenizer;
  const model = pipe.model;
  const l2i = model?.config?.label2id;
  if (typeof tok !== 'function' || typeof model !== 'function' || !l2i) return null;
  const lower = Object.fromEntries(Object.entries(l2i).map(([k, v]) => [k.toLowerCase(), v]));
  const entId = lower['entailment'];
  const againstId = lower['contradiction'] ?? lower['not_entailment'];
  if (entId === undefined || againstId === undefined) return null;
  const cache = new Map<string, PairLogits>();
  const logits = async (premise: string, hyps: readonly string[], signal: AbortSignal): Promise<PairLogits[]> => {
    const out: Array<PairLogits | undefined> = hyps.map((h) => cache.get(`${premise}\u0000${h}`));
    const todo: number[] = [];
    out.forEach((v, i) => { if (!v) todo.push(i); });
    stats.cachedPairs += hyps.length - todo.length;
    for (let s = 0; s < todo.length; s += batch) {
      if (signal.aborted) throw new DOMException('Aborted', 'AbortError');
      const idx = todo.slice(s, s + batch);
      const t0 = Date.now();
      const inputs = tok(idx.map(() => premise), { text_pair: idx.map((i) => hyps[i]!), padding: true, truncation: true });
      const res = await model(inputs);
      const data = res.logits.data;
      const L = res.logits.dims?.[1] ?? Math.round(data.length / idx.length);
      idx.forEach((hi, k) => {
        const v: PairLogits = [Number(data[k * L + againstId]), Number(data[k * L + entId])];
        out[hi] = v;
        if (cache.size >= PAIR_CACHE_MAX) cache.delete(cache.keys().next().value as string);
        cache.set(`${premise}\u0000${hyps[hi]!}`, v);
      });
      stats.passes++;
      stats.pairs += idx.length;
      stats.ms += Date.now() - t0;
    }
    return out as PairLogits[];
  };
  return {
    batched: true,
    logits,
    async choice(premise, hyps, signal) {
      return softmax((await logits(premise, hyps, signal)).map((x) => x[1]));
    },
    async yes(premise, hyp, signal) {
      const [l] = await logits(premise, [hyp], signal);
      return softmax(l!)[1]!;
    },
  };
}

/** The public pipeline call, one pair per pass: used when the pipeline does not expose its tokenizer and model. */
function publicScorer(pipe: ZeroShotPipe, stats: DecisionStats): Scorer {
  const timed = async <T>(pairs: number, f: () => Promise<T>): Promise<T> => {
    const t0 = Date.now();
    const r = await f();
    stats.pairs += pairs;
    stats.passes += pairs;
    stats.ms += Date.now() - t0;
    return r;
  };
  return {
    batched: false,
    async logits() {
      throw new ProviderError('This pipeline does not expose raw scores.');
    },
    async choice(premise, hyps, signal) {
      if (signal.aborted) throw new DOMException('Aborted', 'AbortError');
      const uniq = [...new Set(hyps)];
      const r = await timed(uniq.length, () => pipe(premise, uniq, { hypothesis_template: '{}', multi_label: false }));
      const byLabel = new Map(r.labels.map((l, i) => [l, r.scores[i]!]));
      return hyps.map((h) => byLabel.get(h) ?? 0);
    },
    async yes(premise, hyp, signal) {
      if (signal.aborted) throw new DOMException('Aborted', 'AbortError');
      const r = await timed(1, () => pipe(premise, [hyp], { hypothesis_template: '{}', multi_label: true }));
      return r.scores[0] ?? 0;
    },
  };
}

// ---------------------------------------------------------------- errors in plain words

export function explainLoadError(e: unknown, ctx: { model: string; dtype: string; endpoint: string; device: string }): ProviderError {
  if (e instanceof ProviderError) return e;
  const m = e instanceof Error ? e.message : String(e);
  if (/401|403|unauthorized|forbidden/i.test(m)) return new ProviderError(`Hugging Face refused "${ctx.model}" (${m}). It is private or gated. Save a Hugging Face token with access to it.`);
  if (/404|not found|could not locate|no such file|unable to get model file/i.test(m)) {
    return new ProviderError(`"${ctx.model}" has no ${ctx.dtype} weights at ${ctx.endpoint} (${m}). Choose another data type (fp32 exists for most models), or check the model id.`);
  }
  if (/failed to fetch|networkerror|load failed|fetch failed/i.test(m)) return new ProviderError(`Could not download the model from ${ctx.endpoint} (${m}). Check the network, the endpoint setting and any content security policy.`);
  if (/out of memory|oom|allocation|memory/i.test(m)) return new ProviderError(`The device ran out of memory (${m}). Choose a smaller model or a smaller data type such as q8.`);
  return new ProviderError(`Could not load the decision model on ${ctx.device} (${m}).`);
}

// ---------------------------------------------------------------- download progress

export interface DecisionProgress {
  /** 0 to 1 over all files seen so far. */
  progress: number;
  loadedMB: number;
  totalMB: number;
  /** Plain text for the drawer. */
  text: string;
}

/** Aggregates the progress events of transformers.js (per file) into one figure. */
export function progressTracker(onProgress?: (p: DecisionProgress) => void): (ev: unknown) => void {
  const files = new Map<string, { loaded: number; total: number }>();
  return (ev) => {
    const e = ev as { status?: string; file?: string; name?: string; loaded?: number; total?: number; progress?: number } | null;
    if (!e || !e.file) return;
    if (e.status === 'progress' || e.status === 'download' || e.status === 'done') {
      const prev = files.get(e.file) ?? { loaded: 0, total: 0 };
      const total = typeof e.total === 'number' && e.total > 0 ? e.total : prev.total;
      const loaded = e.status === 'done' ? total || prev.loaded : typeof e.loaded === 'number' ? e.loaded : prev.loaded;
      files.set(e.file, { loaded, total });
    } else if (e.status === 'initiate' && !files.has(e.file)) files.set(e.file, { loaded: 0, total: 0 });
    let loaded = 0;
    let total = 0;
    for (const f of files.values()) { loaded += f.loaded; total += f.total; }
    const mb = (n: number): number => Math.round(n / 1e5) / 10;
    onProgress?.({
      progress: total > 0 ? Math.min(1, loaded / total) : 0,
      loadedMB: mb(loaded),
      totalMB: mb(total),
      text: total > 0 ? `Downloading ${mb(loaded)} of ${mb(total)} MB` : 'Starting the download',
    });
  };
}

// ---------------------------------------------------------------- the browser cache (Cache API)

export interface CacheStorageLike {
  open(name: string): Promise<{ keys(): Promise<Array<{ url: string }>>; match(req: unknown): Promise<{ headers: { get(n: string): string | null }; clone(): { blob(): Promise<{ size: number }> } } | undefined> }>;
  delete(name: string): Promise<boolean>;
  has?(name: string): Promise<boolean>;
}

export interface ModelCacheInfo {
  available: boolean;
  files: number;
  bytes: number;
}

const browserCaches = (): CacheStorageLike | null => (typeof caches === 'undefined' ? null : (caches as unknown as CacheStorageLike));

/** Size of the weights (and the WASM runtime) that transformers.js stored in the Cache API. Uses Content-Length, else the body size. */
export async function modelCacheInfo(store: CacheStorageLike | null = browserCaches(), name = TRANSFORMERS_CACHE_NAME): Promise<ModelCacheInfo> {
  if (!store) return { available: false, files: 0, bytes: 0 };
  try {
    if (store.has && !(await store.has(name))) return { available: true, files: 0, bytes: 0 };
    const c = await store.open(name);
    const keys = await c.keys();
    let bytes = 0;
    for (const k of keys) {
      const r = await c.match(k);
      if (!r) continue;
      const len = Number(r.headers.get('content-length'));
      bytes += Number.isFinite(len) && len > 0 ? len : (await r.clone().blob()).size;
    }
    return { available: true, files: keys.length, bytes };
  } catch {
    return { available: false, files: 0, bytes: 0 };
  }
}

export async function clearModelCache(store: CacheStorageLike | null = browserCaches(), name = TRANSFORMERS_CACHE_NAME): Promise<boolean> {
  if (!store) return false;
  try {
    return await store.delete(name);
  } catch {
    return false;
  }
}

// ---------------------------------------------------------------- loading the library

export async function loadTransformers(): Promise<TransformersModule> {
  try {
    return (await import(/* @vite-ignore */ TRANSFORMERS_CDN_URL)) as TransformersModule;
  } catch (e) {
    throw new ProviderError(`Could not load the decision model library from the CDN (${e instanceof Error ? e.message : String(e)}). Check the network or a content security policy.`);
  }
}

// ---------------------------------------------------------------- the provider

export interface DecisionOptions {
  model: string;
  device: DecisionDevice;
  dtype: DecisionDtype;
  hfEndpoint: string;
  hypothesis: HypothesisTemplates;
  /** The Hugging Face token, read at load time. Never stored in the settings. */
  token?: () => string | null;
  onProgress?: (p: DecisionProgress) => void;
  /** Replace the library loader (tests). */
  loadLib?: () => Promise<TransformersModule>;
  /** Replace the GPU probe (tests). */
  gpu?: () => Promise<GpuProbe>;
  fetchImpl?: typeof fetch;
  maxPremiseTokens?: number;
  /** Pairs per forward pass. Default 8 on WASM and 16 on WebGPU. */
  batch?: number;
  /** Skip the config check before the download (tests of the loader itself). */
  skipInspect?: boolean;
}

export interface LoadReport {
  device: 'webgpu' | 'wasm';
  dtype: string;
  note: string;
  loadMs: number;
  /** Total size of the files that the loader reported, MB (0 when it reported none, for example when all came from the cache). */
  sizeMB: number;
  labels: string[];
}

export interface DecisionProvider extends DecisionModel {
  readonly provider: 'decision';
  /** Load the library and the model now. Idempotent: a second call returns the first report. */
  load(signal?: AbortSignal): Promise<LoadReport>;
  /** The device and data type that are in use, or null before the first load. */
  runtime(): LoadReport | null;
  stats(): DecisionStats;
  /** Free the model. */
  dispose(): Promise<void>;
}

export function createDecisionProvider(o: DecisionOptions): DecisionProvider {
  const stats = emptyDecisionStats();
  let loaded: Promise<{ scorer: Scorer; report: LoadReport; pipe: ZeroShotPipe }> | null = null;
  let report: LoadReport | null = null;
  let downloadedBytes = 0;

  const doLoad = async (signal?: AbortSignal): Promise<{ scorer: Scorer; report: LoadReport; pipe: ZeroShotPipe }> => {
    const t0 = Date.now();
    const bad = hfModelProblem(o.model);
    if (bad) throw new ProviderError(bad);
    const token = o.token?.() ?? null;
    const gpu = await (o.gpu ?? probeGpu)();
    const rt = chooseRuntime(o.device, o.dtype, o.model, gpu);
    // A custom model is checked before its weights are downloaded: a wrong model should not cost 700 MB.
    if (!o.skipInspect && !decisionModelInfo(o.model)) {
      const ins = await inspectModel(o.model, { endpoint: o.hfEndpoint, token, ...(o.fetchImpl ? { fetchImpl: o.fetchImpl } : {}), ...(signal ? { signal } : {}) });
      if (!ins.ok) throw new ProviderError(ins.message);
    }
    const lib = await (o.loadLib ?? loadTransformers)();
    const env = lib.env;
    const endpoint = o.hfEndpoint.replace(/\/+$/, '');
    env['remoteHost'] = `${endpoint}/`;
    if (typeof window !== 'undefined') env['allowLocalModels'] = false; // the browser has no local model folder: do not probe /models/
    if (typeof caches !== 'undefined') env['useBrowserCache'] = true;
    // The token goes to the Hugging Face endpoint only: not to the CDN, not to any other host.
    const origFetch = env['fetch'];
    if (token) {
      const base = (typeof origFetch === 'function' ? origFetch : globalThis.fetch.bind(globalThis)) as (u: string | URL, i?: Record<string, unknown>) => Promise<unknown>;
      let origin = '';
      try { origin = new URL(endpoint).origin; } catch { /* not a URL: no token is sent */ }
      env['fetch'] = (url: string | URL, init: Record<string, unknown> = {}) => {
        let same = false;
        try { same = !!origin && new URL(String(url)).origin === origin; } catch { /* relative */ }
        if (!same) return base(url, init);
        const h = new Headers(init['headers'] as HeadersInit | undefined);
        h.set('Authorization', `Bearer ${token}`);
        return base(url, { ...init, headers: h });
      };
    }
    const track = progressTracker((p) => {
      downloadedBytes = Math.max(downloadedBytes, p.totalMB * 1e6);
      o.onProgress?.(p);
    });
    const tryTypes = [rt.dtype, ...(o.dtype === 'auto' ? rt.fallbacks : [])];
    let pipe: ZeroShotPipe | null = null;
    let used: string = rt.dtype;
    let lastErr: unknown;
    try {
      for (const dtype of tryTypes) {
        try {
          pipe = await lib.pipeline('zero-shot-classification', o.model, { device: rt.device, dtype, progress_callback: track });
          used = dtype;
          break;
        } catch (e) {
          lastErr = e;
          if (signal?.aborted) throw e;
          if (!/404|not found|could not locate|unable to get model file/i.test(e instanceof Error ? e.message : String(e))) break;
        }
      }
    } finally {
      if (token) env['fetch'] = origFetch;
    }
    if (!pipe) throw explainLoadError(lastErr, { model: o.model, dtype: rt.dtype, endpoint, device: rt.device });
    // The label check on the loaded model is the authority (the catalog and the config check come first, but a mirror can differ).
    const l2i = pipe.model?.config?.label2id;
    if (l2i) {
      const chk = checkNliConfig({ label2id: l2i }, `"${o.model}"`);
      if (!chk.ok) throw new ProviderError(chk.message);
    }
    const batch = o.batch ?? (rt.device === 'webgpu' ? 16 : 8);
    const scorer = rawScorer(pipe, stats, batch) ?? publicScorer(pipe, stats);
    const labels = l2i ? Object.keys(l2i) : [];
    const rep: LoadReport = { device: rt.device, dtype: used, note: rt.note, loadMs: Date.now() - t0, sizeMB: Math.round(downloadedBytes / 1e5) / 10, labels };
    report = rep;
    return { scorer, report: rep, pipe };
  };

  // A load that failed is not retried for a while by decide(): a run over many signatures must not repeat a failing download.
  let failure: { error: unknown; at: number } | null = null;
  const FAILURE_MS = 30_000;
  const ensure = (signal?: AbortSignal, retry = true): Promise<{ scorer: Scorer; report: LoadReport; pipe: ZeroShotPipe }> => {
    if (!loaded) {
      if (!retry && failure && Date.now() - failure.at < FAILURE_MS) return Promise.reject(failure.error);
      loaded = doLoad(signal);
      loaded.then(() => { failure = null; }, (e) => {
        loaded = null;
        if (!signal?.aborted) failure = { error: e, at: Date.now() };
      });
    }
    return loaded;
  };

  const maxPremise = o.maxPremiseTokens ?? DEFAULT_PREMISE_TOKENS;
  const templateOf = (name: string): string => (o.hypothesis as unknown as Record<string, string>)[name] ?? FALLBACK_HYPOTHESIS;

  // One request at a time: the model runs one batch at a time anyway.
  let chain: Promise<unknown> = Promise.resolve();
  const run = async (state: JsonObject, questions: Questions, signal: AbortSignal): Promise<Answers> => {
    if (signal.aborted) throw new DOMException('Aborted', 'AbortError');
    const { scorer } = await ensure(signal, false);
    stats.requests++;
    const premise = buildPremise(state, maxPremise);
    const answers: Record<string, Answer> = {};

    // Plan: the hypotheses of every question. With raw logits all questions share the batches.
    interface Plan { name: string; kind: 'choice' | 'noul'; options: string[]; hyps: string[] }
    const plans: Plan[] = [];
    for (const [name, q] of Object.entries(questions)) {
      if (q.type === 'choice') {
        const options = Object.keys(q.criteria);
        if (options.length === 0) throw new ProviderError(`The question "${name}" has no options.`);
        const tpl = templateOf(name);
        plans.push({ name, kind: 'choice', options, hyps: options.map((k) => hypothesisFor(tpl, optionPhrase(q.criteria[k]!))) });
      } else if (q.type === 'noul') {
        plans.push({ name, kind: 'noul', options: [], hyps: [hypothesisFor(templateOf(name), q.instructions.trim())] });
      } else {
        throw new ProviderError('The decision model does not answer score questions.');
      }
    }
    const probsByPlan: number[][] = [];
    /** Raw scores per plan (entailment logits of a choice; the log-odds of a statement): kept for calibration. */
    const rawByPlan: number[][] = [];
    if (scorer.batched) {
      const all = plans.flatMap((p) => p.hyps);
      const lg = await scorer.logits(premise, all, signal);
      let at = 0;
      for (const p of plans) {
        const part = lg.slice(at, at + p.hyps.length);
        at += p.hyps.length;
        if (p.kind === 'choice') {
          rawByPlan.push(part.map((x) => x[1]));
          probsByPlan.push(softmax(part.map((x) => x[1])));
        } else {
          rawByPlan.push([part[0]![1] - part[0]![0]]);
          probsByPlan.push([softmax(part[0]!)[1]!]);
        }
      }
    } else {
      for (const p of plans) probsByPlan.push(p.kind === 'choice' ? await scorer.choice(premise, p.hyps, signal) : [await scorer.yes(premise, p.hyps[0]!, signal)]);
    }
    plans.forEach((p, k) => {
      const probs = probsByPlan[k]!;
      const raw = rawByPlan[k];
      if (p.kind === 'noul') {
        answers[p.name] = { type: 'noul', noul: probs[0]!, ...(raw ? { logit: raw[0]! } : {}) };
        return;
      }
      const probabilities: Record<string, number> = {};
      let best = 0;
      p.options.forEach((opt, i) => {
        probabilities[opt] = probs[i]!;
        if (probs[i]! > probs[best]!) best = i;
      });
      answers[p.name] = {
        type: 'choice', choice: p.options[best]!, confidence: probs[best]!, probabilities,
        ...(raw ? { logits: Object.fromEntries(p.options.map((opt, i) => [opt, raw[i]!])) } : {}),
      };
    });
    return { model: `decision:${o.model}`, answers };
  };

  return {
    provider: 'decision',
    load: (signal) => ensure(signal).then((x) => x.report),
    runtime: () => report,
    stats: () => ({ ...stats }),
    async dispose() {
      const l = loaded;
      loaded = null;
      report = null;
      try { await (await l)?.pipe.dispose?.(); } catch { /* ignore */ }
    },
    decide(state, questions, signal): Promise<Answers> {
      const next = chain.then(() => run(state, questions, signal));
      chain = next.catch(() => undefined);
      return next;
    },
  };
}

/** A plain description of what a run on this device costs, for the drawer. */
export function runtimeText(r: LoadReport | null, gpu: GpuProbe | null): string {
  if (r) return `Device ${r.device}, data type ${r.dtype}.${r.note ? ` ${r.note}` : ''}`;
  if (!gpu) return '';
  if (gpu.present && gpu.adapter) return 'WebGPU is available: the model runs on the GPU.';
  return WASM_NOTE;
}

