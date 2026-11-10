// The d3 provider ("Decision 3.0 d3-edge"): a 0.6B Qwen3.5 decision model that answers typed questions with a probability for every
// option and generates no text. The wire shape is the one of Jev (System One), so the pipeline does not know the difference.
//
// Two backends:
//   endpoint  a System One server (`vllm-sr serve -e vllm-sr/d3-edge`, default http://localhost:8899/v1/systemone). It is the Jev
//             HTTP provider with another id and another default (see jev.ts). The only backend that can send pictures.
//   browser   onnxruntime-web with the WebGPU backend, from the THIRD-PARTY export warsang/d3-edge-web (pinned revision): a torso
//             graph (fp16, 1.04 GB, last-position hidden state) and a readout graph (fp32, 255 x 1024). The prompt is built here by
//             d3Format.ts (a port of d3_format.py), tokenised with the Qwen tokenizer, and run once per question.
//
// Neither onnxruntime-web nor transformers.js is bundled: both load at run time from jsDelivr at exact versions, only when this
// provider is used. The 1.04 GB of weights come from huggingface.co (or a mirror) after an explicit confirmation and are kept in
// the Cache API.

import { ProviderError } from '../types';
import type { DecideExtra, DecisionModel } from '../types';
import type { Answers, JsonObject, Questions } from '../jevAdapter';
import { loadTransformers, progressTracker } from './decision';
import type { DecisionProgress, GpuProbe } from './decision';
import { D3_CODES, D3_FORMAT_ID, D3_MAX_OPTIONS, d3Answer, d3Options, d3Render } from './d3Format';
import { D3_CACHE_NAME, D3_FILES, ORT_CDN_URL, ORT_WASM_BASE, isBaseUrl } from './d3Config';
import { VISION_DEFAULTS, expandImagePads, mropePositions, preprocessPicture, textPositions, visionInputs } from './d3Vision';
import type { Rgba, VisionParams } from './d3Vision';

// ---------------------------------------------------------------- the parts that are injected (fakes in the tests)

export interface OrtTensor {
  data: ArrayLike<number> | ArrayLike<bigint>;
  dims: readonly number[];
  type?: string;
}
export interface OrtSession {
  inputNames: readonly string[];
  outputNames: readonly string[];
  run(feeds: Record<string, OrtTensor>): Promise<Record<string, OrtTensor>>;
  release?(): Promise<void>;
}
/** The part of onnxruntime-web that this provider uses. */
export interface OrtModule {
  env: { wasm?: Record<string, unknown>; [k: string]: unknown };
  InferenceSession: { create(model: Uint8Array | string, options?: Record<string, unknown>): Promise<OrtSession> };
  Tensor: new (type: string, data: ArrayLike<number> | ArrayLike<bigint> | BigInt64Array | Float32Array, dims: readonly number[]) => OrtTensor;
}
export interface TokenizerLike {
  encode(text: string, opts?: Record<string, unknown>): number[];
}
interface TokenizerLib {
  PreTrainedTokenizer: new (tokenizerJson: unknown, tokenizerConfig: unknown) => TokenizerLike;
}

/** Where the bytes of the files come from: the browser cache and the network (default), or a folder (the Node bench). */
export interface D3FileSource {
  has(file: string): Promise<boolean>;
  read(file: string, o?: { signal?: AbortSignal; onProgress?: (loaded: number, total: number) => void }): Promise<Uint8Array>;
}

// ---------------------------------------------------------------- the repository check (before any weights are downloaded)

export interface D3FileInfo {
  bytes: number;
  sha256: string;
}
export interface D3GraphFiles {
  torso: string;
  readout: string;
  vision: string | null;
}
export interface D3Inspection {
  ok: boolean;
  /** Plain reason when not ok. */
  message: string;
  files: Record<string, D3FileInfo>;
  /** Bytes that the browser must download in total (torso, readout, tokenizer, configs). */
  totalBytes: number;
  torsoBytes: number;
  /** The manifest declares a vision graph (and lists its file): the export reads pictures. */
  vision: boolean;
  /** Paths of the graphs, from the manifest (`graphs`), or the defaults of the text-only export. */
  graphs: D3GraphFiles;
  /** Numbers of the picture side, from the manifest (`mm`), or the defaults of d3-edge. */
  mm: VisionParams & { imageTokenId: number | null };
  /** Free text of the manifest, shown as it is (the scope of the export). */
  scope: string;
}

const isObj = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);

const baseUrl = (endpoint: string, repo: string, revision: string): string =>
  isBaseUrl(repo) ? `${repo.trim().replace(/\/+$/, '')}/` : `${endpoint.replace(/\/+$/, '')}/${repo}/resolve/${revision}/`;
/** The address of one file. A plain base URL gets `?v=<revision>` so that a new export under the same address is not served from an old cache entry. */
const fileUrl = (repo: string, revision: string, base: string, name: string): string => (isBaseUrl(repo) ? `${base}${name}?v=${encodeURIComponent(revision)}` : base + name);

/**
 * Read MANIFEST.json and decision_config.json of a repository and check that it is a d3 code-readout export with a torso, a readout and a
 * tokenizer: before 1 GB is downloaded. Never throws.
 */
export async function inspectD3Repo(o: { repo: string; revision: string; endpoint: string; token?: string | null; fetchImpl?: typeof fetch; signal?: AbortSignal }): Promise<D3Inspection> {
  const noGraphs: D3GraphFiles = { torso: D3_FILES.torso, readout: D3_FILES.readout, vision: null };
  const noMm = { ...VISION_DEFAULTS, imageTokenId: null };
  const bad = (message: string): D3Inspection => ({ ok: false, message, files: {}, totalBytes: 0, torsoBytes: 0, vision: false, graphs: noGraphs, mm: noMm, scope: '' });
  const f = o.fetchImpl ?? globalThis.fetch.bind(globalThis);
  const base = baseUrl(o.endpoint, o.repo, o.revision);
  const where = isBaseUrl(o.repo) ? o.repo.trim() : o.endpoint;
  const headers: Record<string, string> = {};
  // A Hugging Face token goes to the Hugging Face endpoint only, never to a plain base URL.
  if (o.token && !isBaseUrl(o.repo)) headers['Authorization'] = `Bearer ${o.token}`;
  const get = async (name: string): Promise<{ json?: unknown; problem?: string }> => {
    try {
      const r = await f(fileUrl(o.repo, o.revision, base, name), { headers, credentials: 'omit', ...(o.signal ? { signal: o.signal } : {}) });
      if (r.status === 404) return { problem: isBaseUrl(o.repo) ? `${where} has no ${name}. Check the address of the folder.` : `"${o.repo}" at revision "${o.revision}" has no ${name}. Check the repository id and the revision.` };
      if (r.status === 401 || r.status === 403) return { problem: `"${o.repo}" needs a Hugging Face token (HTTP ${r.status}). Save a token with access to it.` };
      if (!r.ok) return { problem: `${where} answered HTTP ${r.status} for ${name} of "${o.repo}".` };
      return { json: await r.json() };
    } catch (e) {
      if (o.signal?.aborted) throw e;
      return { problem: `Could not reach ${where} (${e instanceof Error ? e.message : String(e)}). Check the network${isBaseUrl(o.repo) ? ', the address and that the server allows cross-origin requests' : ' and the endpoint setting'}.` };
    }
  };
  const man = await get(D3_FILES.manifest);
  if (man.problem) return bad(man.problem);
  const cfg = await get(D3_FILES.config);
  if (cfg.problem) return bad(cfg.problem);
  if (!isObj(cfg.json) || cfg.json['format_id'] !== D3_FORMAT_ID) {
    return bad(`"${o.repo}" is not a d3 export: its decision_config.json has format "${isObj(cfg.json) ? String(cfg.json['format_id']) : 'none'}", not "${D3_FORMAT_ID}".`);
  }
  const codes = cfg.json['codes'];
  if (!Array.isArray(codes) || codes.length !== D3_MAX_OPTIONS || codes.some((c, i) => c !== D3_CODES[i])) {
    return bad(`"${o.repo}" uses other answer codes than d3-edge (${Array.isArray(codes) ? codes.length : 0} codes). The prompt of this viewer would not match the model.`);
  }
  if (!isObj(man.json) || !isObj(man.json['files'])) return bad(`The MANIFEST.json of "${o.repo}" has no file list.`);
  const listed = man.json['files'];
  const graphMap = isObj(man.json['graphs']) ? man.json['graphs'] : {};
  // `graphs` values start with the path of the file ("onnx/torso_mm.onnx (Qwen3.5, ...)"); no entry means the layout of the text-only export.
  const pathOf = (v: unknown, dflt: string | null): string | null => (typeof v === 'string' && /^\S+\.onnx\b/.test(v.trim()) ? v.trim().split(/\s+/)[0]! : dflt);
  const graphs: D3GraphFiles = { torso: pathOf(graphMap['torso'], D3_FILES.torso)!, readout: pathOf(graphMap['readout'], D3_FILES.readout)!, vision: pathOf(graphMap['vision'], null) };
  const wanted = [D3_FILES.config, D3_FILES.tokenizer, D3_FILES.tokenizerConfig, graphs.readout, graphs.torso, ...(graphs.vision ? [graphs.vision] : [])];
  const files: Record<string, D3FileInfo> = {};
  for (const name of wanted) {
    const e = listed[name];
    if (!isObj(e) || typeof e['bytes'] !== 'number' || typeof e['sha256'] !== 'string' || !/^[0-9a-f]{64}$/.test(e['sha256'])) {
      if (name === D3_FILES.tokenizerConfig || name === D3_FILES.config) continue;
      return bad(`The MANIFEST.json of "${o.repo}" does not list ${name} with its size and sha256, so the files cannot be checked.`);
    }
    files[name] = { bytes: e['bytes'], sha256: e['sha256'] };
  }
  const vision = graphs.vision !== null;
  const mmRaw = isObj(man.json['mm']) ? man.json['mm'] : {};
  const num = (k: string, d: number): number => (typeof mmRaw[k] === 'number' && Number.isFinite(mmRaw[k]) && (mmRaw[k] as number) > 0 ? (mmRaw[k] as number) : d);
  const mm = {
    patchSize: num('patch_size', VISION_DEFAULTS.patchSize), mergeSize: num('merge_size', VISION_DEFAULTS.mergeSize), posGrid: num('pos_grid', VISION_DEFAULTS.posGrid),
    minPixels: num('min_pixels', VISION_DEFAULTS.minPixels), maxPixels: num('max_pixels', VISION_DEFAULTS.maxPixels),
    imageTokenId: typeof mmRaw['image_token_id'] === 'number' ? (mmRaw['image_token_id'] as number) : null,
  };
  const scope = typeof man.json['scope'] === 'string' ? man.json['scope'] : '';
  const totalBytes = Object.values(files).reduce((s, x) => s + x.bytes, 0);
  return { ok: true, message: '', files, totalBytes, torsoBytes: files[graphs.torso]?.bytes ?? 0, vision, graphs, mm, scope };
}

// ---------------------------------------------------------------- files: Cache API and integrity

export interface CacheLike {
  match(req: string): Promise<{ arrayBuffer(): Promise<ArrayBuffer>; headers: { get(n: string): string | null } } | undefined>;
  put(req: string, res: Response): Promise<void>;
  keys(): Promise<Array<{ url: string }>>;
}
export interface CacheStorageForD3 {
  open(name: string): Promise<CacheLike>;
  delete(name: string): Promise<boolean>;
  has(name: string): Promise<boolean>;
}

export async function sha256Hex(bytes: Uint8Array): Promise<string> {
  const c = (globalThis as { crypto?: Crypto }).crypto;
  if (!c?.subtle) throw new ProviderError('This browser cannot check file hashes (no crypto.subtle). Open the viewer over https or on localhost.');
  const buf = await c.subtle.digest('SHA-256', bytes as unknown as ArrayBuffer);
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

/** A file is checked by its size, and by its sha256 when it is small enough to hash quickly (the torso is 1 GB: size only). */
export const HASH_LIMIT_BYTES = 64 * 1024 * 1024;

export async function verifyFile(name: string, bytes: Uint8Array, info: D3FileInfo | undefined): Promise<void> {
  if (!info) return;
  if (bytes.byteLength !== info.bytes) throw new ProviderError(`${name} has ${bytes.byteLength} bytes, but the manifest says ${info.bytes}. The download is incomplete or the file changed. Clear the cache and try again.`);
  if (info.bytes <= HASH_LIMIT_BYTES) {
    const h = await sha256Hex(bytes);
    if (h !== info.sha256) throw new ProviderError(`${name} does not match the sha256 of the manifest. Clear the cache and try again, or check the revision.`);
  }
}

/** The browser source: Cache API first, then the network, with the token sent to the endpoint only. The response is streamed into the cache. */
export function browserSource(o: { repo: string; revision: string; endpoint: string; token?: () => string | null; fetchImpl?: typeof fetch; storage?: CacheStorageForD3 | null; cacheName?: string }): D3FileSource {
  const base = baseUrl(o.endpoint, o.repo, o.revision);
  const storage = o.storage === undefined ? (typeof caches === 'undefined' ? null : (caches as unknown as CacheStorageForD3)) : o.storage;
  const name = o.cacheName ?? D3_CACHE_NAME;
  const opened = async (): Promise<CacheLike | null> => (storage ? storage.open(name) : null);
  return {
    async has(file) {
      try {
        const c = await opened();
        return !!c && !!(await c.match(fileUrl(o.repo, o.revision, base, file)));
      } catch {
        return false;
      }
    },
    async read(file, io = {}) {
      const url = fileUrl(o.repo, o.revision, base, file);
      const c = await opened().catch(() => null);
      const hit = c ? await c.match(url).catch(() => undefined) : undefined;
      if (hit) return new Uint8Array(await hit.arrayBuffer());
      const f = o.fetchImpl ?? globalThis.fetch.bind(globalThis);
      const token = isBaseUrl(o.repo) ? null : (o.token?.() ?? null);
      let res: Response;
      try {
        res = await f(url, { credentials: 'omit', ...(token ? { headers: { Authorization: `Bearer ${token}` } } : {}), ...(io.signal ? { signal: io.signal } : {}) });
      } catch (e) {
        if (io.signal?.aborted) throw e;
        throw new ProviderError(`Could not download ${file} from ${isBaseUrl(o.repo) ? o.repo : o.endpoint} (${e instanceof Error ? e.message : String(e)}). Check the network and the endpoint setting.`);
      }
      if (!res.ok) throw new ProviderError(`${isBaseUrl(o.repo) ? o.repo : o.endpoint} answered HTTP ${res.status} for ${file}.`);
      const total = Number(res.headers.get('content-length')) || 0;
      let loaded = 0;
      const body = res.body;
      if (!body) {
        const buf = new Uint8Array(await res.arrayBuffer());
        io.onProgress?.(buf.byteLength, buf.byteLength);
        return buf;
      }
      // Count the bytes while they pass into the cache; the cache then holds the file and a second read gives the bytes.
      const counted = body.pipeThrough(
        new TransformStream<Uint8Array, Uint8Array>({
          transform(chunk, ctl) {
            loaded += chunk.byteLength;
            io.onProgress?.(loaded, total);
            ctl.enqueue(chunk);
          },
        }),
      );
      if (c) {
        try {
          await c.put(url, new Response(counted, { headers: { 'content-length': String(total || '') } }));
          const stored = await c.match(url);
          if (stored) return new Uint8Array(await stored.arrayBuffer());
        } catch (e) {
          if (io.signal?.aborted) throw e;
          // A full disk or a blocked cache: fall through and read the network once more is wasteful, so report it plainly.
          throw new ProviderError(`The browser could not keep ${file} in its cache (${e instanceof Error ? e.message : String(e)}). Free some disk space or allow site storage.`);
        }
      }
      return new Uint8Array(await new Response(counted).arrayBuffer());
    },
  };
}

export interface D3CacheInfo {
  available: boolean;
  files: number;
  bytes: number;
}

export async function d3CacheInfo(storage: CacheStorageForD3 | null = typeof caches === 'undefined' ? null : (caches as unknown as CacheStorageForD3), name = D3_CACHE_NAME): Promise<D3CacheInfo> {
  if (!storage) return { available: false, files: 0, bytes: 0 };
  try {
    if (!(await storage.has(name))) return { available: true, files: 0, bytes: 0 };
    const c = await storage.open(name);
    const keys = await c.keys();
    let bytes = 0;
    for (const k of keys) {
      const r = await c.match(k.url);
      const len = Number(r?.headers.get('content-length'));
      bytes += Number.isFinite(len) && len > 0 ? len : r ? (await r.arrayBuffer()).byteLength : 0;
    }
    return { available: true, files: keys.length, bytes };
  } catch {
    return { available: false, files: 0, bytes: 0 };
  }
}

export async function clearD3Cache(storage: CacheStorageForD3 | null = typeof caches === 'undefined' ? null : (caches as unknown as CacheStorageForD3), name = D3_CACHE_NAME): Promise<boolean> {
  try {
    return storage ? await storage.delete(name) : false;
  } catch {
    return false;
  }
}

// ---------------------------------------------------------------- device

export interface D3Runtime {
  device: 'webgpu' | 'wasm';
  note: string;
}

export const D3_NO_WEBGPU =
  'The d3-edge model in the browser needs WebGPU with 16-bit float support (shader-f16). This browser or device does not offer it. ' +
  'Use the endpoint backend (vllm-sr serve -e vllm-sr/d3-edge), or choose the Decision model, which also runs without a GPU.';
export const D3_WASM_NOTE = 'Very slow: the model runs on the CPU with WebAssembly, about 25 tokens per second, so one element takes minutes. It holds the 1 GB of weights and about 5 GB of memory in all, and a browser may refuse that.';

/**
 * Pick the device. WebGPU needs an adapter with `shader-f16`: the torso is fp16. WASM is offered only when asked for by name
 * (device `wasm`), with a plain warning; `auto` refuses without WebGPU rather than start a download that the device cannot use.
 */
export function chooseD3Runtime(device: 'auto' | 'webgpu' | 'wasm', gpu: GpuProbe): D3Runtime {
  const ok = gpu.present && gpu.adapter && gpu.f16;
  if (device === 'wasm') return { device: 'wasm', note: D3_WASM_NOTE };
  if (ok) return { device: 'webgpu', note: '' };
  if (device === 'webgpu') {
    if (!gpu.present) throw new ProviderError(`The device is set to WebGPU, but this browser has no WebGPU. ${D3_NO_WEBGPU}`);
    if (!gpu.adapter) throw new ProviderError(`The device is set to WebGPU, but the browser found no GPU adapter. ${D3_NO_WEBGPU}`);
    throw new ProviderError(`The GPU adapter has no 16-bit float support (shader-f16). ${D3_NO_WEBGPU}`);
  }
  throw new ProviderError(D3_NO_WEBGPU);
}

// ---------------------------------------------------------------- the engine (tokenizer, torso, readout)

const half = (h: number): number => {
  const s = (h & 0x8000) >> 15;
  const e = (h & 0x7c00) >> 10;
  const f = h & 0x03ff;
  if (e === 0) return (s ? -1 : 1) * Math.pow(2, -14) * (f / 1024);
  if (e === 0x1f) return f ? NaN : s ? -Infinity : Infinity;
  return (s ? -1 : 1) * Math.pow(2, e - 15) * (1 + f / 1024);
};

/**
 * The last-position hidden state as float32, from a torso output of shape [1, d] (the export gives the last position already) or
 * [1, L, d]. The pinned export outputs float32; a float16 output arrives as raw half floats and is converted.
 */
export function lastHidden(t: OrtTensor, dim: number): Float32Array {
  const data = t.data as ArrayLike<number>;
  const n = data.length;
  if (n < dim || n % dim !== 0) throw new ProviderError(`The torso gave ${n} values, which is not a multiple of the hidden size ${dim}.`);
  const out = new Float32Array(dim);
  const from = n - dim;
  const raw16 = t.type === 'float16' && data instanceof Uint16Array;
  for (let i = 0; i < dim; i++) out[i] = raw16 ? half(data[from + i]!) : Number(data[from + i]!);
  return out;
}

export const D3_HIDDEN = 1024;

export interface D3EngineOptions {
  source: D3FileSource;
  inspection: D3Inspection;
  runtime: D3Runtime;
  signal?: AbortSignal;
  /** Replace the library loaders (tests, the Node bench). */
  loadOrt?: () => Promise<OrtModule>;
  loadTokenizerLib?: () => Promise<TokenizerLib>;
  onProgress?: (p: DecisionProgress) => void;
  /** Extra onnxruntime session options (the Node bench passes its execution provider here). */
  sessionOptions?: (device: 'webgpu' | 'wasm') => Record<string, unknown>;
}

/** The pictures of one request, run through the vision encoder once (every question of the request sees the same pictures). */
export interface PreparedPictures {
  /** Embeddings of the pictures, [tokens, 1024] each, float32. */
  embeds: Float32Array[];
  /** Tokens each picture takes in the prompt. */
  tokens: number[];
  /** Merged grids [rows, columns] of the pictures. */
  grids: Array<[number, number]>;
  ms: number;
}

export interface D3Engine {
  /** Code logits (the first `count` entries are the options) of one prompt, and the number of tokens. `pictures` come from `prepare`. */
  scores(prompt: string, count: number, pictures?: PreparedPictures): Promise<{ logits: Float32Array; tokens: number }>;
  /** True when the export has a vision graph, so `prepare` works. */
  vision: boolean;
  /** Run the vision encoder on decoded pictures (one call per picture). Throws on an export without a vision graph. */
  prepare(pictures: readonly Rgba[]): Promise<PreparedPictures>;
  dispose(): Promise<void>;
  inputNames: readonly string[];
}

export async function loadOrt(): Promise<OrtModule> {
  try {
    const ort = (await import(/* @vite-ignore */ ORT_CDN_URL)) as OrtModule;
    ort.env.wasm ??= {};
    ort.env.wasm['wasmPaths'] = ORT_WASM_BASE;
    return ort;
  } catch (e) {
    throw new ProviderError(`Could not load onnxruntime-web from the CDN (${e instanceof Error ? e.message : String(e)}). Check the network or a content security policy.`);
  }
}

async function loadTokenizerLib(): Promise<TokenizerLib> {
  const lib = (await loadTransformers()) as unknown as Partial<TokenizerLib>;
  if (!lib.PreTrainedTokenizer) throw new ProviderError('The tokenizer library has no PreTrainedTokenizer.');
  return lib as TokenizerLib;
}

export async function loadD3Engine(o: D3EngineOptions): Promise<D3Engine> {
  const { source, inspection: ins } = o;
  const track = progressTracker(o.onProgress);
  const read = async (file: string): Promise<Uint8Array> => {
    const info = ins.files[file];
    const bytes = await source.read(file, {
      ...(o.signal ? { signal: o.signal } : {}),
      onProgress: (loaded, total) => track({ status: 'progress', file, loaded, total: total || info?.bytes || 0 }),
    });
    await verifyFile(file, bytes, info);
    track({ status: 'done', file, total: bytes.byteLength });
    return bytes;
  };
  const text = (b: Uint8Array): string => new TextDecoder().decode(b);

  const tokJson = JSON.parse(text(await read(D3_FILES.tokenizer))) as unknown;
  let tokCfg: unknown = {};
  try {
    tokCfg = JSON.parse(text(await read(D3_FILES.tokenizerConfig)));
  } catch {
    /* the tokenizer config is optional: a missing file is not fatal */
  }
  const readout = await read(ins.graphs.readout);
  const torso = await read(ins.graphs.torso);
  const visionBytes = ins.graphs.vision ? await read(ins.graphs.vision) : null;

  const ort = await (o.loadOrt ?? loadOrt)();
  const tokLib = await (o.loadTokenizerLib ?? loadTokenizerLib)();
  const tokenizer = new tokLib.PreTrainedTokenizer(tokJson, tokCfg);
  const opts = (d: 'webgpu' | 'wasm'): Record<string, unknown> => ({
    executionProviders: [d === 'webgpu' ? 'webgpu' : 'wasm'],
    graphOptimizationLevel: 'all',
    ...(o.sessionOptions?.(d) ?? {}),
  });
  let torsoSession: OrtSession;
  let readoutSession: OrtSession;
  let visionSession: OrtSession | null = null;
  try {
    torsoSession = await ort.InferenceSession.create(torso, opts(o.runtime.device));
    readoutSession = await ort.InferenceSession.create(readout, { executionProviders: ['wasm'], ...(o.sessionOptions?.('wasm') ?? {}) });
    if (visionBytes) visionSession = await ort.InferenceSession.create(visionBytes, opts(o.runtime.device));
  } catch (e) {
    const m = e instanceof Error ? e.message : String(e);
    if (/memory|alloc|oom/i.test(m)) throw new ProviderError(`The device ran out of memory while it loaded the model (${m}). Close other tabs, or use the endpoint backend.`);
    throw new ProviderError(`Could not start the d3 model on ${o.runtime.device} (${m}).`);
  }
  const names = torsoSession.inputNames;
  const find = (re: RegExp): string | undefined => names.find((n) => re.test(n));
  const idsName = find(/input_ids|^ids$|tokens/i) ?? names[0]!;
  const maskName = find(/attention_mask|^mask$/i);
  const posName = find(/position_ids|positions/i);
  const imgName = find(/image_embeds/i);
  const outName = torsoSession.outputNames[0]!;
  const multimodal = !!imgName;
  if (visionSession && !multimodal) throw new ProviderError('The manifest declares a vision graph, but the torso graph has no image_embeds input. The export is not complete.');
  const mm = ins.mm;
  const imageTokenId = mm.imageTokenId ?? (tokenizer.encode(VISION_DEFAULTS.imageToken, { add_special_tokens: false })[0] ?? -1);
  const big = (xs: ArrayLike<number>): BigInt64Array => BigInt64Array.from(Array.from(xs, (x) => BigInt(x)));

  return {
    inputNames: names,
    vision: !!visionSession,
    async prepare(pictures) {
      if (!visionSession) throw new ProviderError('This d3 export reads text only: its manifest has no vision graph.');
      const t0 = Date.now();
      const embeds: Float32Array[] = [];
      const tokens: number[] = [];
      const grids: Array<[number, number]> = [];
      const vin = visionSession.inputNames;
      const pick = (re: RegExp, i: number): string => vin.find((n) => re.test(n)) ?? vin[i]!;
      for (const rgba of pictures) {
        const pre = preprocessPicture(rgba, mm);
        const taps = visionInputs(pre.gridH, pre.gridW, pre.hw, mm.posGrid);
        const n = pre.gridH * pre.gridW;
        const out = await visionSession.run({
          [pick(/pixel/i, 0)]: new ort.Tensor('float32', pre.pixels, [n, 3 * mm.patchSize * mm.patchSize]),
          [pick(/pos_hw|hw/i, 1)]: new ort.Tensor('int64', pre.hw, [n, 2]),
          [pick(/pos_idx|idx/i, 2)]: new ort.Tensor('int64', taps.idx, [n, 4]),
          [pick(/pos_w|weight/i, 3)]: new ort.Tensor('float32', taps.w, [n, 4]),
        });
        const e = out[visionSession.outputNames[0]!]!;
        const data = Float32Array.from(e.data as ArrayLike<number>);
        if (data.length !== pre.tokens * D3_HIDDEN) throw new ProviderError(`The vision graph gave ${data.length} values for ${pre.tokens} picture tokens.`);
        embeds.push(data);
        tokens.push(pre.tokens);
        grids.push([pre.gridH / mm.mergeSize, pre.gridW / mm.mergeSize]);
      }
      return { embeds, tokens, grids, ms: Date.now() - t0 };
    },
    async scores(prompt, count, pictures) {
      const withPictures = !!pictures && pictures.tokens.length > 0;
      const rendered = withPictures ? expandImagePads(prompt, pictures!.tokens) : prompt;
      const ids = tokenizer.encode(rendered, { add_special_tokens: false });
      if (!ids.length) throw new ProviderError('The tokenizer gave no tokens for the prompt.');
      const L = ids.length;
      const feeds: Record<string, OrtTensor> = { [idsName]: new ort.Tensor('int64', big(ids), [1, L]) };
      if (multimodal) {
        let embed: Float32Array;
        let rows: number;
        let positions: BigInt64Array;
        if (withPictures) {
          rows = pictures!.tokens.reduce((a, b) => a + b, 0);
          embed = new Float32Array(rows * D3_HIDDEN);
          let at = 0;
          for (const e of pictures!.embeds) { embed.set(e, at); at += e.length; }
          positions = mropePositions(ids, imageTokenId, pictures!.grids);
        } else {
          rows = 1;
          embed = new Float32Array(D3_HIDDEN); // no picture token in the prompt: the graph never reads it
          positions = textPositions(L);
        }
        feeds[imgName!] = new ort.Tensor('float32', embed, [rows, D3_HIDDEN]);
        feeds[posName!] = new ort.Tensor('int64', positions, [3, 1, L]);
        if (maskName) feeds[maskName] = new ort.Tensor('int64', big(new Array<number>(L).fill(1)), [1, L]);
      } else {
        if (withPictures) throw new ProviderError('This d3 export reads text only. It cannot take pictures.');
        if (maskName) feeds[maskName] = new ort.Tensor('int64', big(new Array<number>(L).fill(1)), [1, L]);
        if (posName) feeds[posName] = new ort.Tensor('int64', big(Array.from({ length: L }, (_, i) => i)), [1, L]);
      }
      const out = await torsoSession.run(feeds);
      const hidden = lastHidden(out[outName]!, D3_HIDDEN);
      const r = await readoutSession.run({
        last: new ort.Tensor('float32', hidden, [1, D3_HIDDEN]),
        counts: new ort.Tensor('int64', BigInt64Array.from([BigInt(count)]), [1]),
      });
      const logits = Float32Array.from(r['logits']!.data as ArrayLike<number>);
      return { logits, tokens: L };
    },
    async dispose() {
      try { await torsoSession.release?.(); await readoutSession.release?.(); await visionSession?.release?.(); } catch { /* ignore */ }
    },
  };
}

// ---------------------------------------------------------------- the browser provider

export interface D3BrowserOptions {
  repo: string;
  revision: string;
  endpoint: string;
  device: 'auto' | 'webgpu' | 'wasm';
  token?: () => string | null;
  /** Called before any file is downloaded that is not in the cache. Return true to go on: the viewer asks the person first. */
  confirmDownload?: (info: { bytes: number; files: string[] }) => boolean | Promise<boolean>;
  onProgress?: (p: DecisionProgress) => void;
  fetchImpl?: typeof fetch;
  gpu?: () => Promise<GpuProbe>;
  source?: D3FileSource;
  loadOrt?: D3EngineOptions['loadOrt'];
  loadTokenizerLib?: D3EngineOptions['loadTokenizerLib'];
  sessionOptions?: D3EngineOptions['sessionOptions'];
  cacheStorage?: CacheStorageForD3 | null;
  /** Decode a picture (a data URL) into RGBA pixels. The default uses the browser (createImageBitmap and a canvas); Node tests and benches pass their own. */
  decodeImage?: (dataUrl: string) => Promise<Rgba>;
}

export interface D3LoadReport {
  device: 'webgpu' | 'wasm';
  note: string;
  loadMs: number;
  /** Bytes that came over the network in this load (0 when all came from the cache). */
  downloadedBytes: number;
  totalBytes: number;
  /** The export has a vision graph and the engine loaded it: pictures are read. */
  vision: boolean;
}

export interface D3Stats {
  requests: number;
  passes: number;
  tokens: number;
  ms: number;
  /** Pictures run through the vision encoder, and the time that took. */
  pictures: number;
  pictureMs: number;
}

export interface D3BrowserProvider extends DecisionModel {
  readonly provider: 'd3';
  load(signal?: AbortSignal): Promise<D3LoadReport>;
  runtime(): D3LoadReport | null;
  stats(): D3Stats;
  dispose(): Promise<void>;
}

export const D3_TEXT_ONLY =
  'This d3 export reads text only: its manifest has no vision graph. Use the endpoint backend, or an export with a vision graph (tools/export_d3_web.py), to send pictures.';

/** Decode a picture (a data URL, WebP or PNG) into RGBA pixels with the browser's own decoder. */
export async function browserDecodeImage(dataUrl: string): Promise<Rgba> {
  const blob = await (await fetch(dataUrl)).blob();
  const bmp = await createImageBitmap(blob, { colorSpaceConversion: 'none', premultiplyAlpha: 'none' });
  try {
    const c = typeof OffscreenCanvas !== 'undefined' ? new OffscreenCanvas(bmp.width, bmp.height) : Object.assign(document.createElement('canvas'), { width: bmp.width, height: bmp.height });
    const g = (c as OffscreenCanvas).getContext('2d', { willReadFrequently: true }) as OffscreenCanvasRenderingContext2D | null;
    if (!g) throw new ProviderError('The browser could not read the pixels of a picture.');
    g.drawImage(bmp, 0, 0);
    const d = g.getImageData(0, 0, bmp.width, bmp.height);
    return { data: d.data, width: d.width, height: d.height };
  } finally {
    bmp.close();
  }
}

/** Plain text for a model that is not cached yet: the confirm dialog and the drawer use it. */
export const D3_DOWNLOAD_NEEDED = 'The d3-edge model is not downloaded yet. Confirm the download of about 1 GB in the Classify drawer first.';

export function createD3BrowserProvider(o: D3BrowserOptions): D3BrowserProvider {
  const stats: D3Stats = { requests: 0, passes: 0, tokens: 0, ms: 0, pictures: 0, pictureMs: 0 };
  let report: D3LoadReport | null = null;
  let loaded: Promise<D3Engine> | null = null;
  let failure: { error: unknown; at: number } | null = null;

  const doLoad = async (signal?: AbortSignal): Promise<D3Engine> => {
    const t0 = Date.now();
    const gpu = await (o.gpu ?? (async (): Promise<GpuProbe> => ({ present: false, adapter: false, f16: false })))();
    const rt = chooseD3Runtime(o.device, gpu);
    const token = o.token?.() ?? null;
    const ins = await inspectD3Repo({ repo: o.repo, revision: o.revision, endpoint: o.endpoint, token, ...(o.fetchImpl ? { fetchImpl: o.fetchImpl } : {}), ...(signal ? { signal } : {}) });
    if (!ins.ok) throw new ProviderError(ins.message);
    const source = o.source ?? browserSource({ repo: o.repo, revision: o.revision, endpoint: o.endpoint, ...(o.token ? { token: o.token } : {}), ...(o.fetchImpl ? { fetchImpl: o.fetchImpl } : {}), ...(o.cacheStorage !== undefined ? { storage: o.cacheStorage } : {}) });
    const missing: string[] = [];
    // The files that the engine reads (decision_config.json is read and checked above, with the manifest).
    for (const f of [D3_FILES.tokenizer, D3_FILES.tokenizerConfig, ins.graphs.readout, ins.graphs.torso, ...(ins.graphs.vision ? [ins.graphs.vision] : [])]) if (f in ins.files && !(await source.has(f))) missing.push(f);
    const needBytes = missing.reduce((s, f) => s + (ins.files[f]?.bytes ?? 0), 0);
    if (missing.length) {
      const ok = o.confirmDownload ? await o.confirmDownload({ bytes: needBytes, files: missing }) : false;
      if (!ok) throw new ProviderError(D3_DOWNLOAD_NEEDED);
    }
    const eng = await loadD3Engine({
      source, inspection: ins, runtime: rt, ...(signal ? { signal } : {}),
      ...(o.loadOrt ? { loadOrt: o.loadOrt } : {}), ...(o.loadTokenizerLib ? { loadTokenizerLib: o.loadTokenizerLib } : {}),
      ...(o.onProgress ? { onProgress: o.onProgress } : {}), ...(o.sessionOptions ? { sessionOptions: o.sessionOptions } : {}),
    });
    report = { device: rt.device, note: rt.note, loadMs: Date.now() - t0, downloadedBytes: needBytes, totalBytes: ins.totalBytes, vision: ins.vision };
    return eng;
  };
  const ensure = (signal?: AbortSignal, retry = true): Promise<D3Engine> => {
    if (!loaded) {
      if (!retry && failure && Date.now() - failure.at < 30_000) return Promise.reject(failure.error);
      loaded = doLoad(signal);
      loaded.then(() => { failure = null; }, (e) => {
        loaded = null;
        if (!signal?.aborted) failure = { error: e, at: Date.now() };
      });
    }
    return loaded;
  };

  const memo = new Map<string, PreparedPictures>();
  /** The pictures of a request through the vision encoder, once: both requests of a signature (main and sub-discipline) send the same pictures. */
  const picturesOf = async (eng: D3Engine, urls: readonly string[], signal: AbortSignal): Promise<PreparedPictures> => {
    const key = urls.join('\n');
    const hit = memo.get(key);
    if (hit) return hit;
    const decode = o.decodeImage ?? browserDecodeImage;
    const rgba: Rgba[] = [];
    for (const u of urls) {
      if (signal.aborted) throw new DOMException('Aborted', 'AbortError');
      try { rgba.push(await decode(u)); } catch (e) { throw new ProviderError(`A picture could not be decoded (${e instanceof Error ? e.message : String(e)}).`); }
    }
    const p = await eng.prepare(rgba);
    stats.pictures += urls.length;
    stats.pictureMs += p.ms;
    memo.set(key, p);
    if (memo.size > 4) memo.delete(memo.keys().next().value as string);
    return p;
  };

  let chain: Promise<unknown> = Promise.resolve();
  const run = async (state: JsonObject, questions: Questions, signal: AbortSignal, extra?: DecideExtra): Promise<Answers> => {
    if (signal.aborted) throw new DOMException('Aborted', 'AbortError');
    const eng = await ensure(signal, false);
    if (extra?.images?.length && !eng.vision) throw new ProviderError(D3_TEXT_ONLY);
    stats.requests++;
    const pictures = extra?.images?.length ? await picturesOf(eng, extra.images, signal) : undefined;
    const answers: Answers['answers'] = {};
    let tokens = 0;
    for (const [name, q] of Object.entries(questions)) {
      if (signal.aborted) throw new DOMException('Aborted', 'AbortError');
      const n = d3Options(q).keys.length;
      if (n > D3_MAX_OPTIONS) throw new ProviderError(`The question "${name}" has ${n} options. d3 has ${D3_MAX_OPTIONS} answer codes.`);
      const t0 = Date.now();
      const s = await eng.scores(pictures ? d3Render(state, q, D3_CODES, pictures.tokens.length) : d3Render(state, q), n, pictures);
      stats.passes++;
      stats.tokens += s.tokens;
      stats.ms += Date.now() - t0;
      tokens += s.tokens;
      answers[name] = d3Answer(q, s.logits);
    }
    return { model: `d3:${o.repo}@${o.revision.slice(0, 8)}`, answers, usage: { input_tokens: tokens, output_tokens: 0 } };
  };

  return {
    provider: 'd3',
    load: (signal) => ensure(signal).then(() => report!),
    runtime: () => report,
    stats: () => ({ ...stats }),
    async dispose() {
      const l = loaded;
      loaded = null;
      report = null;
      memo.clear();
      try { await (await l)?.dispose(); } catch { /* ignore */ }
    },
    decide(state, questions, signal, extra): Promise<Answers> {
      const next = chain.then(() => run(state, questions, signal, extra));
      chain = next.catch(() => undefined);
      return next;
    },
  };
}
