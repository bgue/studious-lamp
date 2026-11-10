// The d3 provider (Decision 3.0 d3-edge): the repository check, the integrity of the files, the confirmed download and the Cache API,
// the device choice, the engine against a FAKE onnxruntime-web and a FAKE tokenizer, the endpoint backend (Jev wire format plus images),
// the pictures, the cache identity, and the keys. No real model, no network.

import { createHash } from 'node:crypto';
import { describe, expect, it, beforeEach } from 'vitest';
import { ClassifyService, createProvider, defaultDraft, providerId, toSettings, validateSettings } from '../src/classify';
import type { Questions } from '../src/classify';
import {
  browserSource, chooseD3Runtime, clearD3Cache, createD3BrowserProvider, d3CacheInfo, D3_DOWNLOAD_NEEDED, inspectD3Repo, lastHidden, sha256Hex, verifyFile,
} from '../src/classify/providers/d3';
import type { CacheStorageForD3, D3BrowserOptions } from '../src/classify/providers/d3';
import {
  D3_ENDPOINT_DEFAULT, D3_FILES, D3_MODEL_DEFAULT, D3_REPO_DEFAULT, D3_REVISION_DEFAULT, ORT_CDN_URL, ORT_VERSION, ORT_WASM_BASE, d3RepoProblem, d3RevisionProblem,
} from '../src/classify/providers/d3Config';
import { D3_CODES } from '../src/classify/providers/d3Format';
import type { GpuProbe } from '../src/classify/providers/decision';
import { MemoryStorage } from '../src/selectionSets';
import * as fakeOrt from '../bench/fake-ort.mjs';
import * as fakeTok from '../bench/fake-transformers.mjs';
import { jsonResponse, sidecarModel } from './classify-helpers';

const SIGNAL = new AbortController().signal;
const GPU: GpuProbe = { present: true, adapter: true, f16: true };
const enc = (s: string): Uint8Array => new TextEncoder().encode(s);
const sha = (b: Uint8Array): string => createHash('sha256').update(b).digest('hex');

/** A fake export: tiny text files with a correct manifest. `torso` and `readout` start with the words that fake-ort.mjs looks for. */
function makeExport(over: { manifest?: (m: Record<string, unknown>) => void; config?: (c: Record<string, unknown>) => void } = {}) {
  const files: Record<string, Uint8Array> = {
    [D3_FILES.tokenizer]: enc('{"fake":"tokenizer"}'),
    [D3_FILES.tokenizerConfig]: enc('{"fake":"config"}'),
    [D3_FILES.readout]: enc('READOUT fake readout graph'),
    [D3_FILES.torso]: enc('TORSO fake torso graph with some more bytes'),
  };
  const config: Record<string, unknown> = { format_id: 'd3-code-readout-v1', codes: [...D3_CODES] };
  over.config?.(config);
  files[D3_FILES.config] = enc(JSON.stringify(config));
  const manifest: Record<string, unknown> = {
    model: 'd3-edge-web', scope: 'text-only v1; images/videos are not part of the browser export yet', graphs: { torso: 'torso', readout: 'readout' },
    files: Object.fromEntries(Object.entries(files).map(([k, v]) => [k, { bytes: v.byteLength, sha256: sha(v) }])),
  };
  over.manifest?.(manifest);
  files[D3_FILES.manifest] = enc(JSON.stringify(manifest));
  const requests: Array<{ url: string; auth: string | undefined }> = [];
  const fetchImpl = (async (url: string, init?: RequestInit) => {
    requests.push({ url, auth: (init?.headers as Record<string, string> | undefined)?.['Authorization'] });
    const name = url.split('/resolve/')[1]?.split('/').slice(1).join('/') ?? '';
    const f = files[name];
    return f ? new Response(f as unknown as BodyInit, { status: 200, headers: { 'content-length': String(f.byteLength) } }) : new Response('', { status: 404 });
  }) as unknown as typeof fetch;
  return { files, manifest, fetchImpl, requests };
}

/** A Cache API in memory. */
function makeCaches(): CacheStorageForD3 & { stores: Map<string, Map<string, Uint8Array>> } {
  const stores = new Map<string, Map<string, Uint8Array>>();
  return {
    stores,
    async has(n) { return stores.has(n); },
    async delete(n) { return stores.delete(n); },
    async open(n) {
      if (!stores.has(n)) stores.set(n, new Map());
      const m = stores.get(n)!;
      return {
        async match(req) {
          const b = m.get(req);
          return b ? { arrayBuffer: async () => b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength) as ArrayBuffer, headers: { get: (h: string) => (h === 'content-length' ? String(b.byteLength) : null) } } : undefined;
        },
        async put(req, res) { m.set(req, new Uint8Array(await res.arrayBuffer())); },
        async keys() { return [...m.keys()].map((url) => ({ url })); },
      };
    },
  };
}

function make(over: Partial<D3BrowserOptions> = {}, exp = makeExport()) {
  const caches = makeCaches();
  const p = createD3BrowserProvider({
    repo: D3_REPO_DEFAULT, revision: D3_REVISION_DEFAULT, endpoint: 'https://huggingface.co', device: 'auto', fetchImpl: exp.fetchImpl, gpu: async () => GPU, cacheStorage: caches,
    loadOrt: async () => fakeOrt as never, loadTokenizerLib: async () => fakeTok as never, confirmDownload: () => true, ...over,
  });
  return { p, exp, caches };
}

const PICK: Questions = {
  pick: { type: 'choice', instructions: 'Choose the discipline.', criteria: { MEC: 'Mechanical. Heating, ventilation and air conditioning: ducts, fans.', ARC: 'Architectural. Walls, doors, windows, finishes.', PLB: 'Plumbing. Water supply and drainage pipes.' } },
  inside: { type: 'noul', instructions: 'This element is part of a building.' },
};
const DUCT = { class: 'IfcDuctSegment', name: 'Duct 300x200', type: { class: 'IfcDuctSegmentType', name: 'Duct rect 300x200' }, building_context: true };

beforeEach(() => { fakeOrt.__reset(); fakeTok.__reset(); });

describe('pins and checks', () => {
  it('pins onnxruntime-web to an exact version on jsDelivr and the export to a commit', () => {
    expect(ORT_VERSION).toMatch(/^\d+\.\d+\.\d+$/);
    expect(ORT_CDN_URL).toBe(`https://cdn.jsdelivr.net/npm/onnxruntime-web@${ORT_VERSION}/dist/ort.webgpu.min.mjs`);
    expect(ORT_WASM_BASE).toBe(`https://cdn.jsdelivr.net/npm/onnxruntime-web@${ORT_VERSION}/dist/`);
    expect(ORT_CDN_URL).not.toMatch(/[\^~*]|@latest/);
    expect(D3_REVISION_DEFAULT).toBe('117fb255e630667ae1736666497e8a1c69c7a066');
    expect(D3_REPO_DEFAULT).toBe('warsang/d3-edge-web');
    expect(D3_ENDPOINT_DEFAULT).toBe('http://localhost:8899/v1/systemone');
    expect(D3_MODEL_DEFAULT).toBe('vllm-sr/d3-edge');
  });
  it('checks the repository id and the revision', () => {
    expect(d3RepoProblem('warsang/d3-edge-web')).toBeNull();
    expect(d3RepoProblem('https://huggingface.co/a/b')).toMatch(/web address/);
    expect(d3RepoProblem('nope')).toMatch(/owner\/name/);
    expect(d3RevisionProblem('117fb255e630667ae1736666497e8a1c69c7a066')).toBeNull();
    expect(d3RevisionProblem('main')).toBeNull();
    expect(d3RevisionProblem('a..b')).toMatch(/not a revision/);
    expect(d3RevisionProblem('')).toMatch(/empty/);
  });
});

describe('checking a repository before any weights are downloaded', () => {
  it('reads only MANIFEST.json and decision_config.json, and gives the sizes', async () => {
    const exp = makeExport();
    const r = await inspectD3Repo({ repo: D3_REPO_DEFAULT, revision: D3_REVISION_DEFAULT, endpoint: 'https://huggingface.co', fetchImpl: exp.fetchImpl });
    expect(r.ok).toBe(true);
    expect(exp.requests.map((q) => q.url.split('/resolve/')[1]!.split('/').slice(1).join('/')).sort()).toEqual(['MANIFEST.json', 'decision_config.json']);
    expect(r.torsoBytes).toBe(exp.files[D3_FILES.torso]!.byteLength);
    expect(r.totalBytes).toBeGreaterThan(r.torsoBytes);
    expect(r.vision).toBe(false);
    expect(r.scope).toMatch(/text-only/);
  });
  it('refuses a repository that is not a d3 export, with another format, other codes or no file list', async () => {
    const run = (e: ReturnType<typeof makeExport>) => inspectD3Repo({ repo: 'a/b', revision: 'main', endpoint: 'https://huggingface.co', fetchImpl: e.fetchImpl });
    expect((await run(makeExport({ config: (c) => { c['format_id'] = 'other'; } }))).message).toMatch(/not a d3 export/);
    expect((await run(makeExport({ config: (c) => { c['codes'] = ['A', 'B']; } }))).message).toMatch(/other answer codes/);
    expect((await run(makeExport({ manifest: (m) => { delete m['files']; } }))).message).toMatch(/no file list/);
    expect((await run(makeExport({ manifest: (m) => { delete (m['files'] as Record<string, unknown>)[D3_FILES.torso]; } }))).message).toMatch(/does not list onnx\/torso_fp16\.onnx/);
    const notFound = (async () => new Response('', { status: 404 })) as unknown as typeof fetch;
    expect((await inspectD3Repo({ repo: 'a/b', revision: 'main', endpoint: 'https://huggingface.co', fetchImpl: notFound })).message).toMatch(/has no MANIFEST\.json/);
    const denied = (async () => new Response('', { status: 401 })) as unknown as typeof fetch;
    expect((await inspectD3Repo({ repo: 'a/b', revision: 'main', endpoint: 'https://huggingface.co', fetchImpl: denied })).message).toMatch(/needs a Hugging Face token/);
  });
  it('detects a declared vision graph and says that it is not supported', async () => {
    const exp = makeExport({ manifest: (m) => { (m['graphs'] as Record<string, string>)['vision'] = 'onnx/vision.onnx'; } });
    const r = await inspectD3Repo({ repo: 'a/b', revision: 'main', endpoint: 'https://huggingface.co', fetchImpl: exp.fetchImpl });
    expect(r.vision).toBe(true);
    const { p } = make({ repo: 'a/b', revision: 'main' }, exp);
    const rep = await p.load();
    expect(rep.vision).toBe(true);
    expect(rep.note).toMatch(/vision graph. The viewer does not support it yet/);
  });
  it('sends the token to the endpoint only', async () => {
    const exp = makeExport();
    await inspectD3Repo({ repo: 'a/b', revision: 'main', endpoint: 'https://mirror.example.org', token: 'hf_TOKEN', fetchImpl: exp.fetchImpl });
    expect(exp.requests.every((q) => q.url.startsWith('https://mirror.example.org/') && q.auth === 'Bearer hf_TOKEN')).toBe(true);
  });
});

describe('files: integrity and the Cache API', () => {
  it('checks the size of every file and the sha256 of the small ones', async () => {
    const b = enc('hello');
    await verifyFile('x', b, { bytes: 5, sha256: sha(b) });
    await expect(verifyFile('x', b, { bytes: 6, sha256: sha(b) })).rejects.toThrow(/has 5 bytes, but the manifest says 6/);
    await expect(verifyFile('x', b, { bytes: 5, sha256: '0'.repeat(64) })).rejects.toThrow(/does not match the sha256/);
    await verifyFile('x', b, undefined);
    expect(await sha256Hex(b)).toBe(sha(b));
  });
  it('a corrupted download is refused with a plain message', async () => {
    const exp = makeExport();
    exp.files[D3_FILES.readout] = enc('READOUT tampered bytes of the same size!');
    const { p } = make({}, exp);
    await expect(p.load()).rejects.toThrow(/onnx\/readout\.onnx has \d+ bytes|does not match the sha256/);
  });
  it('downloads once into the cache, then reads from it', async () => {
    const exp = makeExport();
    const { p, caches } = make({}, exp);
    await p.load();
    const fileFetches = () => exp.requests.filter((q) => !/MANIFEST|decision_config/.test(q.url)).length;
    expect(fileFetches()).toBe(4);
    const info = await d3CacheInfo(caches);
    expect(info).toMatchObject({ available: true, files: 4 });
    expect(info.bytes).toBeGreaterThan(50);
    await p.dispose();
    const second = make({ cacheStorage: caches }, exp);
    await second.p.load();
    expect(fileFetches()).toBe(4); // nothing new came over the network
    expect(await clearD3Cache(caches)).toBe(true);
    expect(await d3CacheInfo(caches)).toMatchObject({ files: 0 });
  });
  it('browserSource reports progress while it streams a file into the cache', async () => {
    const exp = makeExport();
    const caches = makeCaches();
    const src = browserSource({ repo: D3_REPO_DEFAULT, revision: D3_REVISION_DEFAULT, endpoint: 'https://huggingface.co', fetchImpl: exp.fetchImpl, storage: caches });
    expect(await src.has(D3_FILES.readout)).toBe(false);
    const seen: number[] = [];
    const bytes = await src.read(D3_FILES.readout, { onProgress: (l) => seen.push(l) });
    expect(bytes.byteLength).toBe(exp.files[D3_FILES.readout]!.byteLength);
    expect(seen.at(-1)).toBe(bytes.byteLength);
    expect(await src.has(D3_FILES.readout)).toBe(true);
  });
});

describe('the confirmed download', () => {
  it('does not download without a confirmation, and says what to do', async () => {
    const exp = makeExport();
    const { p } = make({ confirmDownload: undefined }, exp);
    await expect(p.load()).rejects.toThrow(D3_DOWNLOAD_NEEDED);
    expect(exp.requests.filter((q) => !/MANIFEST|decision_config/.test(q.url))).toHaveLength(0);
    const asked: Array<{ bytes: number; files: string[] }> = [];
    const q = make({ confirmDownload: (i) => { asked.push(i); return false; } }, exp);
    await expect(q.p.load()).rejects.toThrow(/not downloaded yet/);
    expect(asked[0]!.files).toHaveLength(4);
    expect(asked[0]!.bytes).toBeGreaterThan(100);
  });
  it('does not ask again for files that are already cached', async () => {
    const exp = makeExport();
    const caches = makeCaches();
    await make({ cacheStorage: caches }, exp).p.load();
    let asked = 0;
    await make({ cacheStorage: caches, confirmDownload: () => { asked++; return false; } }, exp).p.load();
    expect(asked).toBe(0);
  });
});

describe('the device', () => {
  it('uses WebGPU when the adapter has shader-f16', () => {
    expect(chooseD3Runtime('auto', GPU)).toEqual({ device: 'webgpu', note: '' });
  });
  it('refuses with a plain message when WebGPU or shader-f16 is missing (auto), rather than start a download that cannot run', () => {
    expect(() => chooseD3Runtime('auto', { present: false, adapter: false, f16: false })).toThrow(/needs WebGPU with 16-bit float support/);
    expect(() => chooseD3Runtime('auto', { present: true, adapter: true, f16: false })).toThrow(/shader-f16/);
    expect(() => chooseD3Runtime('webgpu', { present: false, adapter: false, f16: false })).toThrow(/no WebGPU/);
    expect(() => chooseD3Runtime('webgpu', { present: true, adapter: false, f16: false })).toThrow(/no GPU adapter/);
    expect(() => chooseD3Runtime('webgpu', { present: true, adapter: true, f16: false })).toThrow(/no 16-bit float/);
  });
  it('offers WASM only by name, with the memory warning', () => {
    const r = chooseD3Runtime('wasm', { present: false, adapter: false, f16: false });
    expect(r.device).toBe('wasm');
    expect(r.note).toMatch(/Very slow/);
    expect(r.note).toMatch(/5 GB/);
  });
  it('does not start a download when the device cannot run the model', async () => {
    const exp = makeExport();
    const { p } = make({ gpu: async () => ({ present: false, adapter: false, f16: false }) }, exp);
    await expect(p.load()).rejects.toThrow(/WebGPU/);
    expect(exp.requests).toHaveLength(0);
  });
});

describe('the engine (fake onnxruntime-web, fake tokenizer)', () => {
  it('loads the torso on WebGPU and the readout on WASM, with the library from the injected loader', async () => {
    const { p } = make();
    const rep = await p.load();
    expect(rep.device).toBe('webgpu');
    expect(fakeOrt.__log.sessions).toHaveLength(2);
    expect(fakeOrt.__log.sessions[0]!.options['executionProviders']).toEqual(['webgpu']);
    expect(fakeOrt.__log.sessions[1]!.options['executionProviders']).toEqual(['wasm']);
  });
  it('answers choice and yes/no questions, one torso pass per question, with probabilities, raw logits and token counts', async () => {
    const { p } = make();
    const a = await p.decide(DUCT, PICK, SIGNAL);
    expect(a.model).toBe(`d3:${D3_REPO_DEFAULT}@117fb255`);
    const pick = a.answers['pick']!;
    expect(pick.type).toBe('choice');
    if (pick.type === 'choice') {
      expect(pick.choice).toBe('MEC');
      expect(Object.values(pick.probabilities).reduce((x, y) => x + y, 0)).toBeCloseTo(1, 10);
      expect(Object.keys(pick.logits ?? {})).toEqual(['MEC', 'ARC', 'PLB']);
    }
    const inside = a.answers['inside']!;
    expect(inside.type === 'noul' && inside.noul).toBeGreaterThan(0.9);
    expect(inside.type === 'noul' && typeof inside.logit).toBe('number');
    expect(fakeOrt.__log.runs).toHaveLength(2);
    expect(a.usage?.input_tokens).toBe(fakeOrt.__log.runs[0]!.tokens + fakeOrt.__log.runs[1]!.tokens);
    expect(p.stats()).toMatchObject({ requests: 1, passes: 2 });
  });
  it('is idempotent to load twice and refuses images, text only', async () => {
    const { p } = make();
    await p.load();
    await p.load();
    expect(fakeOrt.__log.sessions).toHaveLength(2);
    await expect(p.decide(DUCT, PICK, SIGNAL, { images: ['data:image/png;base64,AAAA'] })).rejects.toThrow(/reads text only. Use the endpoint backend to send images/);
  });
  it('refuses a question with more than 255 options', async () => {
    const { p } = make();
    const criteria = Object.fromEntries(Array.from({ length: 256 }, (_, i) => [`k${i}`, 'x']));
    await expect(p.decide(DUCT, { big: { type: 'choice', instructions: 'x', criteria } }, SIGNAL)).rejects.toThrow(/255 answer codes/);
  });
  it('turns an out-of-memory failure into a plain message', async () => {
    const failing = { ...fakeOrt, InferenceSession: { create: async () => { throw new Error('out of memory: alloc failed'); } } };
    const { p } = make({ loadOrt: async () => failing as never });
    await expect(p.load()).rejects.toThrow(/ran out of memory while it loaded the 1 GB model/);
  });
  it('reads a hidden state of shape [1, d] or [1, L, d] and converts half floats', () => {
    expect(Array.from(lastHidden({ data: new Float32Array([1, 2, 3, 4]), dims: [1, 4] }, 4))).toEqual([1, 2, 3, 4]);
    expect(Array.from(lastHidden({ data: new Float32Array([1, 2, 3, 4, 5, 6, 7, 8]), dims: [1, 2, 4] }, 4))).toEqual([5, 6, 7, 8]);
    expect(Array.from(lastHidden({ data: new Uint16Array([0x3c00, 0xc000]), dims: [1, 2], type: 'float16' }, 2))).toEqual([1, -2]);
    expect(() => lastHidden({ data: new Float32Array(3), dims: [1, 3] }, 4)).toThrow(/not a multiple/);
  });
});

describe('settings and identity', () => {
  it('has the d3 defaults and validates its fields with plain messages', () => {
    const c = validateSettings({ provider: 'd3' });
    expect(c.errors).toEqual([]);
    expect(c.settings).toMatchObject({ provider: 'd3', d3Backend: 'browser', d3Repo: D3_REPO_DEFAULT, d3Revision: D3_REVISION_DEFAULT, d3Endpoint: D3_ENDPOINT_DEFAULT, d3Model: D3_MODEL_DEFAULT, d3Device: 'auto', d3MaxStateBytes: 2000 });
    const bad = validateSettings({ provider: 'd3', d3Backend: 'x', d3Repo: 'no', d3Revision: '', d3HfEndpoint: 'ftp://x', d3Device: 'tpu', d3Endpoint: 'nope', d3Model: '', d3MaxStateBytes: 3, images: 'all', imageViews: 5, imageSize: 100, jevImages: 'yes' });
    expect(bad.errors.map((e) => e.split(' ')[0]).sort()).toEqual(['d3Backend', 'd3Repo:', 'd3Revision:', 'd3HfEndpoint', 'd3Device', 'd3Endpoint', 'd3Model', 'd3MaxStateBytes', 'images', 'imageViews', 'imageSize', 'jevImages'].sort());
    expect(bad.settings).toMatchObject({ d3Backend: 'browser', d3Repo: D3_REPO_DEFAULT, images: 'off', imageViews: 1, imageSize: 384 });
  });
  it('warns about a moving revision, an http endpoint and pictures on the browser backend', () => {
    const w = validateSettings({ provider: 'd3', d3Revision: 'main', d3HfEndpoint: 'http://mirror.example.org', images: 'element' }).warnings.join(' ');
    expect(w).toMatch(/not a commit hash/);
    expect(w).toMatch(/d3 file address uses http/);
    expect(w).toMatch(/reads text only, so the pictures are not sent/);
    expect(validateSettings({ provider: 'd3', d3Backend: 'endpoint', d3Endpoint: 'http://example.org/v1/systemone' }).warnings.join(' ')).toMatch(/element data travel without encryption/);
    expect(validateSettings({ provider: 'd3', d3Backend: 'endpoint', d3Endpoint: 'http://localhost:8899/v1/systemone' }).warnings).toEqual([]);
  });
  it('the cache identity names the backend, the repository and revision, and the picture settings only when pictures are sent', () => {
    const id = (p: Record<string, unknown>) => providerId(validateSettings({ provider: 'd3', ...p }).settings);
    expect(id({})).toBe(`d3:browser:${D3_REPO_DEFAULT}@117fb255`);
    expect(id({ d3Backend: 'endpoint' })).toBe('d3:endpoint:vllm-sr/d3-edge');
    expect(id({ d3Backend: 'endpoint', images: 'element' })).toMatch(/^d3:endpoint:vllm-sr\/d3-edge@i[0-9a-f]{8}$/);
    expect(id({ d3Backend: 'endpoint', images: 'element' })).not.toBe(id({ d3Backend: 'endpoint', images: 'element+neighbours' }));
    expect(id({ d3Backend: 'endpoint', images: 'element', imageSize: 512 })).not.toBe(id({ d3Backend: 'endpoint', images: 'element' }));
    expect(id({ images: 'element' })).toBe(id({})); // the browser build sends no pictures: the identity does not change
    expect(id({ d3MaxStateBytes: 3000 })).toBe(`d3:browser:${D3_REPO_DEFAULT}@117fb255@s3000`);
    // Jev: pictures only when its switch is on
    const jev = (p: Record<string, unknown>) => providerId(validateSettings({ provider: 'jev', ...p }).settings);
    expect(jev({ images: 'element' })).toBe(jev({}));
    expect(jev({ images: 'element', jevImages: true })).toMatch(/@i[0-9a-f]{8}$/);
  });
  it('is a provider id in the union, and the calibration does not enter the cache identity', () => {
    expect(validateSettings({ provider: 'd3', calibration: 'manual', temperatures: { discipline: 0.3 } }).settings).toMatchObject({ calibration: 'manual' });
    const a = providerId(validateSettings({ provider: 'd3', calibration: 'off' }).settings);
    const b = providerId(validateSettings({ provider: 'd3', calibration: 'manual', temperatures: { discipline: 0.3 } }).settings);
    expect(a).toBe(b);
    expect(Object.keys(toSettings({ ...defaultDraft(), provider: 'd3' }))).toContain('d3Backend');
  });
});

// ---------------------------------------------------------------- the endpoint backend

interface Seen { url: string; auth: string | undefined; body: { model: string; images?: string[]; questions: Questions } }

function endpointFetch(seen: Seen[]): typeof fetch {
  return (async (url: string, init: RequestInit) => {
    const body = JSON.parse(String(init.body)) as Seen['body'];
    seen.push({ url, auth: (init.headers as Record<string, string>)['Authorization'], body });
    const answers: Record<string, unknown> = {};
    for (const [name, q] of Object.entries(body.questions)) {
      if (q.type === 'choice') {
        const keys = Object.keys(q.criteria);
        answers[name] = { type: 'choice', choice: keys[0], confidence: 0.7, probabilities: Object.fromEntries(keys.map((k, i) => [k, i === 0 ? 0.7 : 0.3 / (keys.length - 1)])) };
      } else answers[name] = { type: 'noul', noul: 0.9 };
    }
    return jsonResponse({ model: 'vllm-sr/d3-edge', answers });
  }) as unknown as typeof fetch;
}

describe('the endpoint backend', () => {
  const settings = (p: Record<string, unknown> = {}) => validateSettings({ provider: 'd3', d3Backend: 'endpoint', ...p }).settings;

  it('is the Jev wire format at the System One URL with the d3 model id, and reports itself as d3', async () => {
    const seen: Seen[] = [];
    const prov = createProvider(settings(), { apiKey: () => 'JEV-KEY', d3ApiKey: () => 'D3-KEY', fetchImpl: endpointFetch(seen) })!;
    expect(prov.provider).toBe('d3');
    const a = await prov.decide(DUCT, PICK, SIGNAL);
    expect(a.model).toBe('vllm-sr/d3-edge');
    expect(seen[0]!.url).toBe('http://localhost:8899/v1/systemone');
    expect(seen[0]!.body.model).toBe('vllm-sr/d3-edge');
    expect(Object.keys(seen[0]!.body.questions)).toEqual(['pick', 'inside']);
    expect(seen[0]!.body.images).toBeUndefined();
  });
  it('uses its own API key, never the Jev key, and Jev never gets the d3 key', async () => {
    const seen: Seen[] = [];
    const f = endpointFetch(seen);
    await createProvider(settings(), { apiKey: () => 'JEV-KEY', d3ApiKey: () => 'D3-KEY', fetchImpl: f })!.decide(DUCT, PICK, SIGNAL);
    await createProvider(validateSettings({ provider: 'jev' }).settings, { apiKey: () => 'JEV-KEY', d3ApiKey: () => 'D3-KEY', fetchImpl: f })!.decide(DUCT, PICK, SIGNAL);
    expect(seen[0]!.auth).toBe('Bearer D3-KEY');
    expect(seen[1]!.auth).toBe('Bearer JEV-KEY');
    const none = await (async () => { const s: Seen[] = []; await createProvider(settings(), { apiKey: () => 'JEV-KEY', fetchImpl: endpointFetch(s) })!.decide(DUCT, PICK, SIGNAL); return s[0]!.auth; })();
    expect(none).toBeUndefined(); // no d3 key: no Authorization header, and certainly not the Jev key
  });
  it('sends images as data URLs only when pictures are on', async () => {
    const IMG = ['data:image/webp;base64,AAAA', 'data:image/webp;base64,BBBB'];
    const seen: Seen[] = [];
    const off = createProvider(settings(), { apiKey: () => null, fetchImpl: endpointFetch(seen) })!;
    await off.decide(DUCT, PICK, SIGNAL, { images: IMG });
    expect(seen[0]!.body.images).toBeUndefined();
    const on = createProvider(settings({ images: 'element' }), { apiKey: () => null, fetchImpl: endpointFetch(seen) })!;
    await on.decide(DUCT, PICK, SIGNAL, { images: IMG });
    expect(seen[1]!.body.images).toEqual(IMG);
    await on.decide(DUCT, PICK, SIGNAL);
    expect(seen[2]!.body.images).toBeUndefined();
  });
  it('Jev sends images only with its own switch, which is off by default', async () => {
    const IMG = ['data:image/png;base64,AAAA'];
    const seen: Seen[] = [];
    const f = endpointFetch(seen);
    const jev = (p: Record<string, unknown>) => createProvider(validateSettings({ provider: 'jev', images: 'element', ...p }).settings, { apiKey: () => null, fetchImpl: f })!;
    await jev({}).decide(DUCT, PICK, SIGNAL, { images: IMG });
    await jev({ jevImages: true }).decide(DUCT, PICK, SIGNAL, { images: IMG });
    expect(seen[0]!.body.images).toBeUndefined();
    expect(seen[1]!.body.images).toEqual(IMG);
    expect(validateSettings({ provider: 'jev' }).settings).toMatchObject({ jevImages: false });
  });
});

// ---------------------------------------------------------------- the service

describe('the service with d3', () => {
  function service(over: Record<string, unknown> = {}) {
    const exp = makeExport();
    const caches = makeCaches();
    const storage = new MemoryStorage();
    const svc = new ClassifyService({
      storage: storage as never, keyStorages: { session: new MemoryStorage() as never, local: new MemoryStorage() as never }, fetchImpl: exp.fetchImpl,
      d3LoadOrt: async () => fakeOrt as never, d3LoadTokenizerLib: async () => fakeTok as never, d3CacheStorage: caches, d3Gpu: async () => GPU, ...over,
    });
    svc.setModel(sidecarModel('fzk-haus'), 'fzk-haus');
    svc.patch({ provider: 'd3' });
    return { svc, exp, caches, storage };
  }

  it('shows the size from the manifest before anything is downloaded, then needs a confirmation', async () => {
    const { svc, exp } = service();
    const ins = await svc.inspectD3();
    expect(ins.ok).toBe(true);
    expect(ins.totalBytes).toBeGreaterThan(0);
    expect(exp.requests.filter((q) => !/MANIFEST|decision_config/.test(q.url))).toHaveLength(0);
    const t = await svc.testModel();
    expect(t.ok).toBe(false);
    expect(t.message).toMatch(/not downloaded yet/);
    svc.confirmD3Download();
    const ok = await svc.testModel();
    expect(ok.ok).toBe(true);
    expect(ok.device).toBe('webgpu');
    expect(ok.message).toMatch(/Ready: warsang\/d3-edge-web on webgpu/);
    expect(ok.choice?.code).toBe('MEC');
    expect((await svc.modelCacheInfo()).files).toBe(4);
    expect(await svc.clearModelCache()).toBe(true);
    expect((await svc.modelCacheInfo()).files).toBe(0);
    expect(svc.d3Confirmed).toBe(false); // a new download needs a new confirmation
  });

  it('classifies with raw logits in the cache and re-scores when the calibration changes, without the model', async () => {
    const { svc } = service();
    svc.confirmD3Download();
    svc.patch({ calibration: 'off' });
    const before = await svc.classify('all', { rules: false });
    expect(before.length).toBeGreaterThan(0);
    const passes = (svc.provider() as unknown as { stats(): { passes: number } }).stats().passes;
    const r0s = svc.results();
    svc.patch({ calibration: 'manual', temperatures: { discipline: 0.1, sub_discipline: 0.1, masterformat: 0.1, building_element: 0.1 } });
    const r1s = new Map(svc.results().map((r) => [r.id, r]));
    // the fake model scores some elements flat (no shared words): those cannot change; the others are sharper, none has another code
    expect(r0s.some((r) => r1s.get(r.id)!.discipline.confidence > r.discipline.confidence + 0.1)).toBe(true);
    expect(r0s.every((r) => r1s.get(r.id)!.discipline.code === r.discipline.code && r1s.get(r.id)!.discipline.confidence >= r.discipline.confidence - 1e-9)).toBe(true);
    expect((svc.provider() as unknown as { stats(): { passes: number } }).stats().passes).toBe(passes); // no new model run
    expect(svc.calibration().label).toBe('manual');
    expect(svc.modelId()).toBe(providerId(svc.settings())); // the calibration is not in the identity
  });
});
