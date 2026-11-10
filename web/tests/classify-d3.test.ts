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
function makeExport(over: { manifest?: (m: Record<string, unknown>) => void; config?: (c: Record<string, unknown>) => void; vision?: boolean } = {}) {
  const files: Record<string, Uint8Array> = {
    [D3_FILES.tokenizer]: enc('{"fake":"tokenizer"}'),
    [D3_FILES.tokenizerConfig]: enc('{"fake":"config"}'),
    [D3_FILES.readout]: enc('READOUT fake readout graph'),
    [over.vision ? 'onnx/torso_mm.onnx' : D3_FILES.torso]: enc(over.vision ? 'TORSOMM fake multimodal torso graph with some more bytes' : 'TORSO fake torso graph with some more bytes'),
    ...(over.vision ? { 'onnx/vision_encoder.onnx': enc('VISION fake vision graph') } : {}),
  };
  const config: Record<string, unknown> = { format_id: 'd3-code-readout-v1', codes: [...D3_CODES] };
  over.config?.(config);
  files[D3_FILES.config] = enc(JSON.stringify(config));
  const manifest: Record<string, unknown> = {
    model: 'd3-edge-web', scope: over.vision ? 'text and images' : 'text-only v1; images/videos are not part of the browser export yet',
    graphs: over.vision ? { torso: 'onnx/torso_mm.onnx (fake)', vision: 'onnx/vision_encoder.onnx (fake)', readout: 'onnx/readout.onnx (fake)' } : { torso: 'torso', readout: 'readout' },
    ...(over.vision ? { mm: { image_token_id: 248056 } } : {}),
    files: Object.fromEntries(Object.entries(files).map(([k, v]) => [k, { bytes: v.byteLength, sha256: sha(v) }])),
  };
  over.manifest?.(manifest);
  files[D3_FILES.manifest] = enc(JSON.stringify(manifest));
  const requests: Array<{ url: string; auth: string | undefined }> = [];
  const fetchImpl = (async (url: string, init?: RequestInit) => {
    requests.push({ url, auth: (init?.headers as Record<string, string> | undefined)?.['Authorization'] });
    const name = (url.includes('/resolve/') ? url.split('/resolve/')[1]!.split('/').slice(1).join('/') : url.split('/export/')[1] ?? '').split('?')[0]!;
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
    expect(d3RepoProblem('https://host.example/a/b')).toBeNull(); // a web address is a base URL: the folder of an export
    expect(d3RepoProblem('ftp://host/a')).toMatch(/owner\/name/);
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
  it('detects a vision graph, with its file in the manifest, and reads the graph paths from the manifest', async () => {
    const exp = makeExport({ vision: true });
    const r = await inspectD3Repo({ repo: 'a/b', revision: 'main', endpoint: 'https://huggingface.co', fetchImpl: exp.fetchImpl });
    expect(r.ok).toBe(true);
    expect(r.vision).toBe(true);
    expect(r.graphs).toEqual({ torso: 'onnx/torso_mm.onnx', readout: 'onnx/readout.onnx', vision: 'onnx/vision_encoder.onnx' });
    expect(r.mm).toMatchObject({ patchSize: 16, mergeSize: 2, posGrid: 48, imageTokenId: 248056 });
    expect(r.scope).toBe('text and images');
    expect(Object.keys(r.files)).toContain('onnx/vision_encoder.onnx');
    const text = await inspectD3Repo({ repo: 'a/b', revision: 'main', endpoint: 'https://huggingface.co', fetchImpl: makeExport().fetchImpl });
    expect(text.vision).toBe(false);
    expect(text.graphs).toEqual({ torso: D3_FILES.torso, readout: D3_FILES.readout, vision: null });
  });
  it('refuses a manifest that declares a vision graph but does not list its file', async () => {
    const exp = makeExport({ manifest: (m) => { (m['graphs'] as Record<string, string>)['vision'] = 'onnx/vision.onnx'; } });
    const r = await inspectD3Repo({ repo: 'a/b', revision: 'main', endpoint: 'https://huggingface.co', fetchImpl: exp.fetchImpl });
    expect(r.ok).toBe(false);
    expect(r.message).toMatch(/does not list onnx\/vision\.onnx/);
  });
  it('accepts a plain base URL instead of a repository id, reads the files from it and never sends a token there', async () => {
    const exp = makeExport({ vision: true });
    const base = 'http://localhost:8123/export';
    expect(d3RepoProblem(base)).toBeNull();
    expect(d3RepoProblem('http://user:pw@host/x')).toMatch(/user name/);
    expect(d3RepoProblem('http://host/x?a=1')).toMatch(/no query/);
    const r = await inspectD3Repo({ repo: base, revision: 'v1', endpoint: 'https://huggingface.co', token: 'hf_TOKEN', fetchImpl: exp.fetchImpl });
    expect(r.ok).toBe(true);
    expect(exp.requests.map((q) => q.url)).toEqual([`${base}/MANIFEST.json?v=v1`, `${base}/decision_config.json?v=v1`]);
    expect(exp.requests.every((q) => q.auth === undefined)).toBe(true);
    const src = browserSource({ repo: `${base}/`, revision: 'v1', endpoint: 'https://huggingface.co', token: () => 'hf_TOKEN', fetchImpl: exp.fetchImpl, storage: makeCaches() });
    await src.read('onnx/readout.onnx');
    expect(exp.requests.at(-1)).toEqual({ url: `${base}/onnx/readout.onnx?v=v1`, auth: undefined });
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
  it('is idempotent to load twice and refuses pictures on a text-only export', async () => {
    const { p } = make();
    await p.load();
    await p.load();
    expect(fakeOrt.__log.sessions).toHaveLength(2);
    await expect(p.decide(DUCT, PICK, SIGNAL, { images: ['data:image/png;base64,AAAA'] })).rejects.toThrow(/This d3 export reads text only: its manifest has no vision graph/);
  });
  describe('with a vision graph', () => {
    // A 256 x 256 picture (a multiple of 32 and the smallest size the processor keeps: no resize): 16 x 16 patches of 16 pixels, 8 x 8 tokens after the merge.
    const grey = (v: number, w = 256, h = 256) => ({ data: new Uint8Array(w * h * 4).fill(v), width: w, height: h });
    const decode = async (u: string) => (u.endsWith('A') ? grey(255) : grey(0));
    const mm = (over: Partial<D3BrowserOptions> = {}) => make({ repo: 'me/d3-mm', revision: 'main', decodeImage: decode, ...over }, makeExport({ vision: true }));

    it('loads the vision graph on the same device as the torso, and reports that pictures are read', async () => {
      const { p } = mm();
      const rep = await p.load();
      expect(rep.vision).toBe(true);
      expect(fakeOrt.__log.sessions).toHaveLength(3);
      expect(fakeOrt.__log.sessions[0]!.options['executionProviders']).toEqual(['webgpu']); // torso
      expect(fakeOrt.__log.sessions[2]!.options['executionProviders']).toEqual(['webgpu']); // vision
    });
    it('runs the pictures through the vision graph once per request, expands the placeholders and gives 3-row positions', async () => {
      const { p } = mm();
      const a = await p.decide(DUCT, PICK, SIGNAL, { images: ['data:image/png;base64,AAAA', 'data:image/png;base64,BBBB'] });
      expect(Object.keys(a.answers)).toEqual(['pick', 'inside']);
      // 2 pictures x 1 vision call each, even though there are 2 questions
      expect(fakeOrt.__log.vision).toHaveLength(2);
      expect(fakeOrt.__log.vision[0]).toMatchObject({ patches: 256, maxRow: 15 });
      expect(fakeOrt.__log.vision[0]!.mean).toBeCloseTo(1, 5); // white, normalised to (255/255 - 0.5)/0.5 = 1
      expect(fakeOrt.__log.vision[1]!.mean).toBeCloseTo(-1, 5);
      expect(fakeOrt.__log.vision[0]!.weightMean).toBeCloseTo(1, 4); // bilinear weights sum to 1
      const run = fakeOrt.__log.runs[0]!;
      expect(run.imageTokens).toBe(128); // 64 tokens per picture
      expect(run.rows).toBe(128);
      expect(run.embedSlot0).toEqual([...Array(64).fill(1), ...Array(64).fill(-1)]);
      // positions: rows T, H, W, L entries each. The first picture starts after the text before it: t equal, h and w count rows and columns.
      const L = run.tokens;
      const pos = run.pos!;
      expect(pos).toHaveLength(3 * L);
      const T = pos.slice(0, L), H = pos.slice(L, 2 * L), W = pos.slice(2 * L);
      const first = T.findIndex((_, i) => (fakeOrt.__log.runs[0]!.imageTokens ?? 0) > 0 && H[i] !== T[i]);
      expect(first).toBeGreaterThan(0);
      expect(p.stats()).toMatchObject({ pictures: 2 });
      expect(W.length).toBe(L);
    });
    it('does not run the vision graph again for the second request of a signature (same pictures)', async () => {
      const { p } = mm();
      const imgs = ['data:image/png;base64,AAAA'];
      await p.decide(DUCT, PICK, SIGNAL, { images: imgs });
      await p.decide(DUCT, PICK, SIGNAL, { images: imgs });
      expect(fakeOrt.__log.vision).toHaveLength(1);
      await p.decide(DUCT, PICK, SIGNAL, { images: ['data:image/png;base64,BBBB'] });
      expect(fakeOrt.__log.vision).toHaveLength(2);
    });
    it('answers text-only requests with the same graph (no picture token: a dummy embedding row, text positions)', async () => {
      const { p } = mm();
      const a = await p.decide(DUCT, PICK, SIGNAL);
      expect(a.answers['pick']).toMatchObject({ type: 'choice', choice: 'MEC' });
      const run = fakeOrt.__log.runs[0]!;
      expect(run.imageTokens).toBe(0);
      expect(run.rows).toBe(1);
      const L = run.tokens;
      expect(run.pos!.slice(0, L)).toEqual(Array.from({ length: L }, (_, i) => i));
      expect(run.pos!.slice(2 * L)).toEqual(Array.from({ length: L }, (_, i) => i));
      expect(fakeOrt.__log.vision).toHaveLength(0);
    });
    it('turns a picture that cannot be decoded into a plain message', async () => {
      const { p } = mm({ decodeImage: async () => { throw new Error('bad bytes'); } });
      await expect(p.decide(DUCT, PICK, SIGNAL, { images: ['data:image/png;base64,AAAA'] })).rejects.toThrow(/A picture could not be decoded \(bad bytes\)/);
    });
  });
  it('refuses a question with more than 255 options', async () => {
    const { p } = make();
    const criteria = Object.fromEntries(Array.from({ length: 256 }, (_, i) => [`k${i}`, 'x']));
    await expect(p.decide(DUCT, { big: { type: 'choice', instructions: 'x', criteria } }, SIGNAL)).rejects.toThrow(/255 answer codes/);
  });
  it('turns an out-of-memory failure into a plain message', async () => {
    const failing = { ...fakeOrt, InferenceSession: { create: async () => { throw new Error('out of memory: alloc failed'); } } };
    const { p } = make({ loadOrt: async () => failing as never });
    await expect(p.load()).rejects.toThrow(/ran out of memory while it loaded the model/);
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
    const bad = validateSettings({ provider: 'd3', d3Backend: 'x', d3Repo: 'no', d3Revision: '', d3HfEndpoint: 'ftp://x', d3Device: 'tpu', d3Endpoint: 'nope', d3Model: '', d3MaxStateBytes: 3, images: 'all', imageStyle: 'sketch', imagePlan: 'yes', imageMargin: 500, imageSize: 100, jevImages: 'yes' });
    expect(bad.errors.map((e) => e.split(' ')[0]).sort()).toEqual(['d3Backend', 'd3Repo:', 'd3Revision:', 'd3HfEndpoint', 'd3Device', 'd3Endpoint', 'd3Model', 'd3MaxStateBytes', 'images', 'imageStyle', 'imagePlan', 'imageMargin', 'imageSize', 'jevImages'].sort());
    expect(bad.settings).toMatchObject({ d3Backend: 'browser', d3Repo: D3_REPO_DEFAULT, images: 'off', imageStyle: 'render', imagePlan: false, imageMargin: 25, imageSize: 384 });
  });
  it('warns about a moving revision, an http endpoint and pictures on the browser backend', () => {
    const w = validateSettings({ provider: 'd3', d3Revision: 'main', d3HfEndpoint: 'http://mirror.example.org', images: 'both' }).warnings.join(' ');
    expect(w).toMatch(/not a commit hash/);
    expect(w).toMatch(/d3 file address uses http/);
    expect(w).toMatch(/default browser export of d3-edge reads text only, so the pictures are not sent/);
    expect(validateSettings({ provider: 'd3', images: 'both', d3Repo: 'me/d3-mm' }).warnings.join(' ')).not.toMatch(/reads text only/);
    expect(validateSettings({ provider: 'd3', d3Backend: 'endpoint', d3Endpoint: 'http://example.org/v1/systemone' }).warnings.join(' ')).toMatch(/element data travel without encryption/);
    expect(validateSettings({ provider: 'd3', d3Backend: 'endpoint', d3Endpoint: 'http://localhost:8899/v1/systemone' }).warnings).toEqual([]);
  });
  it('the cache identity names the backend, the repository and revision, and the picture settings only when pictures are sent', () => {
    const id = (p: Record<string, unknown>, vision = false) => providerId(validateSettings({ provider: 'd3', ...p }).settings, { vision });
    expect(id({})).toBe(`d3:browser:${D3_REPO_DEFAULT}@117fb255`);
    expect(id({ d3Backend: 'endpoint' })).toBe('d3:endpoint:vllm-sr/d3-edge');
    expect(id({ d3Backend: 'endpoint', images: 'isolated' })).toMatch(/^d3:endpoint:vllm-sr\/d3-edge@i[0-9a-f]{8}$/);
    const ep = (p: Record<string, unknown>) => id({ d3Backend: 'endpoint', images: 'isolated', ...p });
    const all = [ep({}), ep({ images: 'context' }), ep({ images: 'both' }), ep({ imageStyle: 'vector' }), ep({ imagePlan: true }), ep({ imageSize: 512 }), ep({ images: 'context', imageMargin: 50 })];
    expect(new Set(all).size).toBe(all.length);
    // what does not change a picture does not change the identity: no plan view in the context picture, no margin in the isolated one
    expect(ep({ images: 'context', imagePlan: true })).toBe(ep({ images: 'context' }));
    expect(ep({ imageMargin: 99 })).toBe(ep({}));
    expect(id({ images: 'isolated' })).toBe(id({})); // the default browser export sends no pictures: the identity does not change
    expect(id({ images: 'isolated' }, true)).toMatch(/@i[0-9a-f]{8}$/); // an export with a vision graph does
    // SVG geometry in the state: part of the identity on both backends, and of Jev's, and only for the providers that send it
    const g = (p: Record<string, unknown>) => id({ geometryText: 'svg', ...p });
    expect(g({})).toBe(`${id({})}@g${g({}).split('@g')[1]}`);
    expect(g({})).not.toBe(id({}));
    expect(new Set([g({}), g({ geometryContext: false }), g({ imageMargin: 50 })]).size).toBe(3);
    expect(g({ geometryContext: false, imageMargin: 50 })).toBe(g({ geometryContext: false })); // the margin only counts with the context
    expect(providerId(validateSettings({ provider: 'jev', geometryText: 'svg' }).settings)).toMatch(/@g[0-9a-f]{8}$/);
    expect(providerId(validateSettings({ provider: 'decision', geometryText: 'svg' }).settings)).not.toMatch(/@g/);
    expect(validateSettings({ provider: 'decision', geometryText: 'svg' }).warnings.join(' ')).toMatch(/geometryText is not used by this provider/);
    expect(validateSettings({ provider: 'd3', geometryText: 'pdf', geometryContext: 'yes' }).errors.map((e) => e.split(' ')[0])).toEqual(['geometryText', 'geometryContext']);
    expect(id({ d3MaxStateBytes: 3000 })).toBe(`d3:browser:${D3_REPO_DEFAULT}@117fb255@s3000`);
    // Jev: pictures only when its switch is on
    const jev = (p: Record<string, unknown>) => providerId(validateSettings({ provider: 'jev', ...p }).settings);
    expect(jev({ images: 'isolated' })).toBe(jev({}));
    expect(jev({ images: 'isolated', jevImages: true })).toMatch(/@i[0-9a-f]{8}$/);
  });
  it('moves the settings of the first picture design to the nearest new value, and ignores the old view count', () => {
    const c = validateSettings({ provider: 'd3', d3Backend: 'endpoint', images: 'element', imageViews: 3 });
    expect(c.errors).toEqual([]);
    expect(c.settings).toMatchObject({ images: 'isolated' });
    expect(c.warnings.join(' ')).toMatch(/images "element" is from an older version. Using "isolated"/);
    expect(c.warnings.join(' ')).toMatch(/imageViews is from an older version and was ignored/);
    const n = validateSettings({ provider: 'd3', d3Backend: 'endpoint', images: 'element+neighbours' });
    expect(n.settings).toMatchObject({ images: 'context' });
    expect(Object.keys(n.settings)).not.toContain('imageViews');
  });
  it('keeps the image size on a multiple of 32, because the vision model reads blocks of 32 pixels', () => {
    const c = validateSettings({ provider: 'd3', imageSize: 300 });
    expect(c.settings).toMatchObject({ imageSize: 288 });
    expect(c.warnings.join(' ')).toMatch(/imageSize 300 is not a multiple of 32/);
    expect(validateSettings({ provider: 'd3', imageSize: 384 }).warnings.join(' ')).not.toMatch(/imageSize/);
    expect(validateSettings({ provider: 'd3', imageSize: 511 }).settings).toMatchObject({ imageSize: 512 });
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
    const on = createProvider(settings({ images: 'isolated' }), { apiKey: () => null, fetchImpl: endpointFetch(seen) })!;
    await on.decide(DUCT, PICK, SIGNAL, { images: IMG });
    expect(seen[1]!.body.images).toEqual(IMG);
    await on.decide(DUCT, PICK, SIGNAL);
    expect(seen[2]!.body.images).toBeUndefined();
  });
  it('Jev sends images only with its own switch, which is off by default', async () => {
    const IMG = ['data:image/png;base64,AAAA'];
    const seen: Seen[] = [];
    const f = endpointFetch(seen);
    const jev = (p: Record<string, unknown>) => createProvider(validateSettings({ provider: 'jev', images: 'isolated', ...p }).settings, { apiKey: () => null, fetchImpl: f })!;
    await jev({}).decide(DUCT, PICK, SIGNAL, { images: IMG });
    await jev({ jevImages: true }).decide(DUCT, PICK, SIGNAL, { images: IMG });
    expect(seen[0]!.body.images).toBeUndefined();
    expect(seen[1]!.body.images).toEqual(IMG);
    expect(validateSettings({ provider: 'jev' }).settings).toMatchObject({ jevImages: false });
  });
});

// ---------------------------------------------------------------- the service

describe('the service with d3', () => {
  function service(over: Record<string, unknown> = {}, exp = makeExport()) {
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

  describe('pictures in the browser', () => {
    const PIC = 'data:image/png;base64,AAAA';
    // a fake picture source: 2 pictures of 384 px, and the note; the decoder reads the pixels from the data URL (A = white)
    const thumbnails = async (id: number, st: { size: number }) => ({
      id, settings: st as never, neighbours: [], note: 'Picture 1: the element alone. Picture 2: the element in its box.',
      thumbs: ['isolated', 'context'].map((view) => ({ view: view as 'isolated', label: view, dataUrl: PIC, width: st.size, height: st.size, scaleBarM: 1, neighbours: [] })),
    });
    const decodeImage = async () => ({ data: new Uint8Array(384 * 384 * 4).fill(255), width: 384, height: 384 });
    const mmService = () => {
      // the browser backend reads a base URL with a vision export; the service gets the decoder through the provider factory options
      const exp = makeExport({ vision: true });
      const r = service({ thumbnails, d3Decode: decodeImage }, exp);
      r.svc.patch({ d3Repo: 'https://d3.example.test/export', d3Revision: 'mm-1', images: 'both', calibration: 'off' });
      return r;
    };

    it('sends pictures only once the export is known to read them, and the identity then names them', async () => {
      const { svc } = mmService();
      expect(svc.imageSettings()).toBeNull(); // the manifest has not been read yet
      expect(svc.modelId()).toBe('d3:browser:https://d3.example.test/export@mm-1');
      await svc.inspectD3();
      expect(svc.visionNow()).toBe(true);
      expect(svc.imageSettings()).toMatchObject({ mode: 'both', style: 'render', plan: false, size: 384, margin: 25 });
      expect(svc.modelId()).toMatch(/^d3:browser:https:\/\/d3\.example\.test\/export@mm-1@i[0-9a-f]{8}$/);
    });
    it('runs the vision graph for the pictures of a classification and puts the note in the state', async () => {
      const { svc } = mmService();
      svc.confirmD3Download();
      const out = await svc.classify('all', { rules: false });
      expect(out.length).toBeGreaterThan(0);
      expect(fakeOrt.__log.vision.length).toBeGreaterThan(0);
      expect(fakeOrt.__log.vision.every((v) => v.patches === 576)).toBe(true);
      expect(fakeOrt.__log.runs.every((r) => r.imageTokens === 288)).toBe(true); // 2 pictures x 144 tokens
      expect(svc.stats().bySource.model).toBeGreaterThan(0);
    });
    it('keeps a text-only export text-only even with pictures switched on, and the identity says so', async () => {
      const { svc } = service({ thumbnails });
      svc.patch({ images: 'both', calibration: 'off' });
      await svc.inspectD3();
      expect(svc.visionNow()).toBe(false);
      expect(svc.imageSettings()).toBeNull();
      expect(svc.modelId()).toBe(`d3:browser:${D3_REPO_DEFAULT}@117fb255`);
      svc.confirmD3Download();
      await svc.classify('all', { rules: false });
      expect(fakeOrt.__log.vision).toHaveLength(0);
    });
  });
});
