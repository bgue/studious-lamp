// Settings, the API key, the service (written properties, persistence, manual overrides), the WebLLM provider with a fake
// engine, and the query engine on the written properties. No real network, no real model.

import { afterEach, describe, expect, it } from 'vitest';
import { ApiKeyStore, ClassifyService, createMockProvider, defaultDraft, parseSchema, providerId, schemaHash, toSettings, validateSettings } from '../src/classify';
import type { KeyValueStorage } from '../src/classify';
import { defaultSchema } from '../src/classify/schema';
import { mainQuestions } from '../src/classify/questions';
import { createWebLlmProvider, detectWebGpu, labelsFor, probsFromTop, yesFromTop, WEBLLM_CDN_URL, WEBLLM_VERSION } from '../src/classify/providers/webllm';
import type { WebLlmEngine } from '../src/classify/providers/webllm';
import { runQuery, freshTable } from '../src/query';
import { modelTable } from '../src/query/table';
import { MemoryStorage } from '../src/selectionSets';
import { encodeShare, collectParams, registerParamSection, shareSubset, shareUrl } from '../src/ui/params';
import { captureView } from '../src/views/capture';
import type { ViewsApp } from '../src/views/capture';
import { encodeViewShare, VIEW_EXCLUDED_SECTIONS } from '../src/views/model';
import { buildBoot, injectTemplate, injectionScript, parseArgs, INJECT_BEGIN, INJECT_END } from '../tools/pack/lib.mjs';
import { fakeApp } from './presets-helpers';
import { jsonResponse, sidecarModel } from './classify-helpers';

const KEY = 'sk-live-ABCDEF-0123456789';
const HF_TOKEN = 'hf_QWERTYUIOPasdfghjkl0123456789';
const D3_KEY = 'd3-live-ZXCVBN-9876543210';
const THUMB = 'data:image/webp;base64,UklGRlRIVU1CTkFJTEJZVEVT'; // what a picture looks like: it must never leave the request

function storages(): { session: MemoryStorage; local: MemoryStorage } {
  return { session: new MemoryStorage(), local: new MemoryStorage() };
}
const kv = (m: MemoryStorage): KeyValueStorage => m as unknown as KeyValueStorage;

function makeService(opts: { storage?: MemoryStorage; k?: ReturnType<typeof storages>; fetchImpl?: typeof fetch; thumbnails?: ConstructorParameters<typeof ClassifyService>[0]['thumbnails'] } = {}): { svc: ClassifyService; storage: MemoryStorage; k: ReturnType<typeof storages> } {
  const storage = opts.storage ?? new MemoryStorage();
  const k = opts.k ?? storages();
  const svc = new ClassifyService({ storage: kv(storage), keyStorages: { session: kv(k.session), local: kv(k.local) }, ...(opts.fetchImpl ? { fetchImpl: opts.fetchImpl } : {}), ...(opts.thumbnails ? { thumbnails: opts.thumbnails } : {}) });
  return { svc, storage, k };
}

describe('settings validation', () => {
  it('has safe defaults: off, pinned model, the Jev endpoint', () => {
    const c = validateSettings(undefined);
    expect(c.errors).toEqual([]);
    expect(c.settings).toEqual({ provider: 'off', schemaUrl: '', minConfidence: null, writePset: true, calibration: 'auto', temperatures: {}, images: 'off', imageViews: 1, imageSize: 384 });
    const d = defaultDraft();
    expect(d.endpoint).toBe('https://api.typesafe.ai/v1/systemone');
    expect(d.model).toBe('jev-1.13.0');
  });

  it('is a union: only the fields of the provider are kept', () => {
    const j = toSettings({ ...defaultDraft(), provider: 'jev' });
    const SHARED = ['calibration', 'imageSize', 'imageViews', 'images', 'minConfidence', 'provider', 'schemaUrl', 'temperatures', 'writePset'];
    expect(Object.keys(j).sort()).toEqual([...SHARED, 'concurrency', 'endpoint', 'jevImages', 'maxStateBytes', 'model', 'timeoutMs'].sort());
    const w = toSettings({ ...defaultDraft(), provider: 'webllm' });
    expect(Object.keys(w).sort()).toEqual([...SHARED, 'embedTemperature', 'hybridMargin', 'webllmCustomLib', 'webllmCustomModel', 'webllmEmbedModel', 'webllmMode', 'webllmModel'].sort());
    const dm = toSettings({ ...defaultDraft(), provider: 'decision' });
    expect(Object.keys(dm).sort()).toEqual([...SHARED, 'device', 'dtype', 'hfEndpoint', 'hfModel', 'hypothesis'].sort());
    const d3 = toSettings({ ...defaultDraft(), provider: 'd3' });
    expect(Object.keys(d3).sort()).toEqual([...SHARED, 'concurrency', 'd3Backend', 'd3Device', 'd3Endpoint', 'd3HfEndpoint', 'd3MaxStateBytes', 'd3Model', 'd3Repo', 'd3Revision', 'timeoutMs'].sort());
    expect(Object.keys(toSettings({ ...defaultDraft(), provider: 'mock' })).sort()).toEqual(SHARED);
  });

  it('gives a plain message for each bad value and falls back to the default', () => {
    const c = validateSettings({ provider: 'gpt', minConfidence: 2, writePset: 'yes', schemaUrl: 'javascript:alert(1)' });
    expect(c.errors).toHaveLength(4);
    expect(c.errors[0]).toBe('provider must be one of off, decision, d3, webllm, jev, mock. Using "off".');
    expect(c.errors.join(' ')).toMatch(/minConfidence must be a number from 0 to 1/);
    expect(c.errors.join(' ')).toMatch(/writePset must be true or false/);
    expect(c.errors.join(' ')).toMatch(/schemaUrl must use https:\/\/ or http:\/\//);
    expect(c.settings).toMatchObject({ provider: 'off', minConfidence: null, writePset: true, schemaUrl: '' });
  });

  it('checks the Jev fields', () => {
    const bad = validateSettings({ provider: 'jev', endpoint: 'not a url', model: '', timeoutMs: 5, concurrency: 99, maxStateBytes: 1.5 });
    expect(bad.errors.map((e) => e.split(' ')[0])).toEqual(['endpoint', 'model', 'timeoutMs', 'concurrency', 'maxStateBytes']);
    expect(bad.errors[0]).toMatch(/Write it as https:\/\/host\/path, or as a path such as \/api\/jev/);
    expect(bad.settings).toMatchObject({ provider: 'jev', endpoint: 'https://api.typesafe.ai/v1/systemone', model: 'jev-1.13.0', timeoutMs: 30000, concurrency: 4, maxStateBytes: 4000 });
    const ok = validateSettings({ provider: 'jev', endpoint: '/api/jev', model: 'typesafe-jev-1.13.0', concurrency: 8 });
    expect(ok.errors).toEqual([]);
    expect(ok.settings).toMatchObject({ endpoint: '/api/jev', model: 'typesafe-jev-1.13.0', concurrency: 8 });
  });

  it('refuses credentials in a URL and warns about http and the moving alias', () => {
    expect(validateSettings({ provider: 'jev', endpoint: 'https://user:pw@host/x' }).errors[0]).toMatch(/must not contain a user name or password/);
    expect(validateSettings({ provider: 'jev', endpoint: 'http://example.com/x' }).warnings.join(' ')).toMatch(/without encryption/);
    expect(validateSettings({ provider: 'jev', endpoint: 'http://localhost:8787/x' }).warnings).toEqual([]);
    const alias = validateSettings({ provider: 'jev', model: 'jev-latest' });
    expect(alias.errors).toEqual([]);
    expect(alias.warnings.join(' ')).toMatch(/moving alias/);
    expect(validateSettings({ provider: 'jev' }).warnings).toEqual([]);
  });

  it('never accepts an API key as a setting', () => {
    const c = validateSettings({ provider: 'jev', apiKey: KEY, authorization: `Bearer ${KEY}` });
    expect(c.errors.join(' ')).toMatch(/"apiKey" looks like a secret/);
    expect(JSON.stringify(c.settings)).not.toContain(KEY);
    expect(Object.keys(c.settings)).not.toContain('apiKey');
  });

  it('checks the WebLLM model and warns about one that is not tested', () => {
    expect(validateSettings({ provider: 'webllm', webllmModel: 'Qwen2.5-0.5B-Instruct-q4f16_1-MLC' }).warnings).toEqual([]);
    expect(validateSettings({ provider: 'webllm', webllmModel: 'Llama-70B' }).warnings[0]).toMatch(/not one of the tested models/);
  });
});

describe('the API key', () => {
  it('stays in sessionStorage by default, in localStorage only on opt-in', () => {
    const s = storages();
    const store = new ApiKeyStore({ session: kv(s.session), local: kv(s.local) });
    store.set(KEY);
    expect(store.get()).toBe(KEY);
    expect(s.session.getItem('xray.classify.apiKey')).toBe(KEY);
    expect(s.local.getItem('xray.classify.apiKey')).toBeNull();
    expect(store.remembered()).toBe(false);
    store.set(KEY, true);
    expect(s.local.getItem('xray.classify.apiKey')).toBe(KEY);
    expect(s.session.getItem('xray.classify.apiKey')).toBeNull();
    expect(store.remembered()).toBe(true);
    store.clear();
    expect(store.get()).toBeNull();
    expect(s.local.getItem('xray.classify.apiKey')).toBeNull();
  });

  it('shows no part of the key in the mask', () => {
    const store = new ApiKeyStore({ session: kv(new MemoryStorage()), local: null });
    store.set(KEY);
    expect(store.mask()).not.toContain('ABCDEF');
    expect(store.mask()).toContain(`${KEY.length} characters`);
    store.clear();
    expect(store.mask()).toBe('not set');
  });

  it('works when storage is blocked (the key stays in memory for the page)', () => {
    const blocked: KeyValueStorage = { getItem: () => { throw new Error('blocked'); }, setItem: () => { throw new Error('blocked'); }, removeItem: () => { throw new Error('blocked'); } };
    const store = new ApiKeyStore({ session: blocked, local: blocked });
    store.set(KEY);
    expect(store.get()).toBe(KEY);
  });
});

describe('the API key never leaves the key store', () => {
  const offs: Array<() => void> = [];
  afterEach(() => { while (offs.length) offs.pop()!(); });

  // All three secrets are set at once (the Jev key, the Hugging Face token and the d3 key) under each provider: none may appear anywhere.
  // A picture of an element (a data URL) is sent in the request only: it is in no params, link, view, packed page or storage either.
  const PATCH = {
    jev: { provider: 'jev', endpoint: 'https://api.typesafe.ai/v1/systemone', jevImages: true, images: 'element+neighbours' },
    decision: { provider: 'decision', hfModel: 'org/custom-nli', hfEndpoint: 'https://mirror.example.org' },
    'd3-endpoint': { provider: 'd3', d3Backend: 'endpoint', d3Endpoint: 'https://d3.example.org/v1/systemone', images: 'element+neighbours', imageViews: 3, imageSize: 512 },
    'd3-browser': { provider: 'd3', d3Backend: 'browser', d3HfEndpoint: 'https://mirror.example.org', calibration: 'manual', temperatures: { discipline: 0.3 } },
  } as const;
  for (const provider of ['jev', 'decision', 'd3-endpoint', 'd3-browser'] as const) it(`is absent from collectParams, the share URL, saved views and packed output (provider ${provider}, keys, token and pictures)`, async () => {
    const bodies: string[] = [];
    const fetchImpl = (async (_url: string, init: RequestInit) => {
      bodies.push(String(init.body));
      const body = JSON.parse(String(init.body)) as { questions: Record<string, { type: string; criteria?: Record<string, string> }> };
      const answers: Record<string, unknown> = {};
      for (const [n, q] of Object.entries(body.questions)) {
        if (q.type === 'choice') { const ks = Object.keys(q.criteria!); answers[n] = { type: 'choice', choice: ks[0], confidence: 0.5, probabilities: Object.fromEntries(ks.map((c, i) => [c, i === 0 ? 0.5 : 0.5 / (ks.length - 1)])) }; } else answers[n] = { type: 'noul', noul: 0.9 };
      }
      return jsonResponse({ model: 'm', answers });
    }) as unknown as typeof fetch;
    const { svc, storage, k } = makeService({ fetchImpl, thumbnails: async (id, st) => ({ id, settings: st, neighbours: [], thumbs: [{ view: 'plan', dataUrl: THUMB, width: st.size, height: st.size, scaleBarM: 1, neighbours: [] }] }) });
    const f = fakeApp();
    svc.setModel(sidecarModel('fzk-haus'), 'fzk-haus');
    svc.patch(PATCH[provider] as never);
    svc.keys.set(KEY, true); // even with "remember on this device"
    svc.hfToken.set(HF_TOKEN, true);
    svc.d3Key.set(D3_KEY, true);
    offs.push(registerParamSection('classify', {
      collect: () => svc.collect(),
      apply: (v, bad, path) => { for (const e of svc.applySettings(v).errors) bad.push(`${path} (${e})`); },
      share: true, // even when a deployment shares the section
    }));
    await svc.classify('all', provider === 'd3-endpoint' || provider === 'jev' ? { rules: false } : {}); // results, cache and manual data are written to storage
    if (provider === 'd3-endpoint' || provider === 'jev') expect(bodies.some((b) => b.includes(THUMB)), 'the picture is in the request').toBe(true); // the one place it may be
    await svc.thumbnails(0, { mode: 'element', views: 1, size: 256 }).catch(() => undefined); // the drawer preview
    svc.override(svc.model!.elements[0]!.globalId, { discipline: 'ARC' });

    const doc = collectParams(f.app, f.env);
    const docText = JSON.stringify(doc);
    expect(doc['classify']).toMatchObject(PATCH[provider] as never);
    const b64 = (s: string): string => btoa(s).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
    const hasKey = (text: string): boolean => [KEY, HF_TOKEN, D3_KEY, THUMB, 'UklGRlRIVU1CTkFJTEJZVEVT', 'data:image'].some((k) => text.includes(k) || text.includes(b64(k)) || text.includes(encodeURIComponent(k)));
    expect(hasKey(docText)).toBe(false);

    // share URL (#p=) and the encoded share document
    const url = shareUrl(doc, { origin: 'https://x.test', pathname: '/viewer' });
    expect(url).toContain('#p=');
    expect(hasKey(url)).toBe(false);
    expect(hasKey(encodeShare(shareSubset(doc)))).toBe(false);
    expect(JSON.stringify(shareSubset(doc))).toContain('"classify"'); // the section is in the share, the key is not

    // exported params JSON (what the Export button writes)
    expect(hasKey(JSON.stringify(doc, null, 2))).toBe(false);

    // saved views: the section is excluded, and the view text has no key either
    expect(VIEW_EXCLUDED_SECTIONS).toContain('classify');
    const va = f.app as ViewsApp;
    (va.controller as unknown as { selection: Set<number> }).selection = new Set();
    const cam = va.renderer.camera as unknown as Record<string, unknown>;
    cam['up'] = { x: 0, y: 1, z: 0, set() {} };
    cam['fov'] = 45;
    const view = captureView(va, 'v', { paramsEnv: f.env });
    expect(view.params['classify']).toBeUndefined();
    expect(hasKey(JSON.stringify(view))).toBe(false);
    expect(hasKey(encodeViewShare('building', view, null))).toBe(false);

    // packed output: a boot document built from the params, and the injected page
    const { options } = parseArgs(['a.glb', '-o', 'x.html', '--tools', 'classify', '--open-tool', 'classify']);
    const boot = buildBoot('m', options, doc, [view]);
    const page = injectTemplate(`<!doctype html><html><head><title>old</title></head><body><script>\n${INJECT_BEGIN}\n${INJECT_END}\n</script></body></html>`, { models: {}, boot, title: 't' });
    expect(hasKey(page)).toBe(false);
    expect(hasKey(injectionScript({}, boot))).toBe(false);
    expect(page).toContain('"classify"');

    // everything that the classifier stored in localStorage (cache, results, schema), apart from the key entry itself
    const dump = JSON.stringify([...storage.map.entries()]);
    expect(hasKey(dump)).toBe(false);
    expect(k.local.getItem('xray.classify.apiKey')).toBe(KEY); // it is only here
    expect(k.local.getItem('xray.classify.hfToken')).toBe(HF_TOKEN); // the token too, in its own entry
    expect(k.local.getItem('xray.classify.d3Key')).toBe(D3_KEY); // the d3 key too, in its own entry
    expect(JSON.stringify(svc.collect())).not.toMatch(/data:image/); // no picture in the settings
    expect(JSON.stringify(svc.settings())).not.toMatch(/token|apiKey|d3Key/i); // not a field of the settings
    expect(Object.keys(svc.collect())).not.toEqual(expect.arrayContaining(['hfToken']));
  });

  it('is sent to the configured endpoint only, and not when the endpoint is a proxy with no key', async () => {
    const seen: Array<{ url: string; auth: string | undefined }> = [];
    const fetchImpl = (async (url: string, init: RequestInit) => {
      seen.push({ url, auth: (init.headers as Record<string, string>)['Authorization'] });
      const body = JSON.parse(String(init.body)) as { questions: Record<string, { type: string }> };
      return jsonResponse({ model: 'jev-1.13.0', answers: { ping: { type: 'noul', noul: 0.99 } }, ...(body ? {} : {}) });
    }) as unknown as typeof fetch;
    const { svc } = makeService({ fetchImpl });
    svc.patch({ provider: 'jev', endpoint: 'https://api.typesafe.ai/v1/systemone' });
    svc.keys.set(KEY);
    const r = await svc.testConnection();
    expect(r.ok).toBe(true);
    expect(r.message).toContain('jev-1.13.0');
    expect(seen).toEqual([{ url: 'https://api.typesafe.ai/v1/systemone', auth: `Bearer ${KEY}` }]);
    expect(r.message).not.toContain(KEY);
    seen.length = 0;
    svc.keys.clear();
    svc.patch({ endpoint: '/proxy/jev' });
    await svc.testConnection();
    expect(seen).toEqual([{ url: '/proxy/jev', auth: undefined }]);
  });

  it('is not in the error message of a failed connection test', async () => {
    const fetchImpl = (async () => jsonResponse({ detail: `invalid key ${KEY}` }, 400)) as unknown as typeof fetch;
    const { svc } = makeService({ fetchImpl });
    svc.patch({ provider: 'jev' });
    svc.keys.set(KEY);
    const r = await svc.testConnection();
    expect(r.ok).toBe(false);
    expect(r.message).toMatch(/HTTP 400/);
    expect(r.message).not.toContain(KEY);
    expect(r.message).toContain('[key]');
  });
});

describe('the service: properties, persistence, overrides', () => {
  it('writes the results as properties that the query engine and the search bar see', async () => {
    const { svc } = makeService();
    const m = sidecarModel('synth5k');
    svc.setModel(m, 'synth5k');
    const before = modelTable(m);
    expect(before.resolve('discipline')).toBeNull();
    await svc.classify('all');
    const t = modelTable(m);
    expect(t).not.toBe(before); // the cached table was reset
    expect(t.propKeys()).toEqual(expect.arrayContaining(['XR_Classification.Discipline', 'XR_Classification.SubDiscipline', 'XR_Classification.MasterFormatDivision', 'XR_Classification.MasterFormatTitle', 'XR_Classification.Confidence', 'XR_Classification.Source', 'XR_Classification.NeedsReview']));
    expect(t.resolve('discipline')).toBe('XR_Classification.Discipline');
    expect(runQuery(m, "discipline = 'MEC'").ids).toHaveLength(870);
    expect(runQuery(m, "XR_Classification.Discipline = 'MEC'").ids).toHaveLength(870);
    expect(runQuery(m, "\"XR_Classification.Discipline\" = 'STR' AND class = 'IfcBeam'").ids).toHaveLength(1540);
    expect(runQuery(m, 'XR_Classification.NeedsReview = TRUE').ids).toHaveLength(0);
    expect(runQuery(m, "MasterFormatDivision = '23'").ids).toHaveLength(870);
    expect(runQuery(m, 'nosuchproperty = 1').unknown).toEqual(['nosuchproperty']);
    const e = m.elements.find((x) => x.ifcClass === 'IfcDuctSegment')!;
    expect(e.props!['XR_Classification.Source']).toBe('rules');
    expect(e.props!['XR_Classification.MasterFormatTitle']).toBe('Heating, Ventilating, and Air Conditioning (HVAC)');
    expect(e.props!['XR_Classification.Confidence']).toBe(0.95);
  });

  it('answers count and sum by discipline through the aggregate engine', async () => {
    const { svc } = makeService();
    const m = sidecarModel('synth5k');
    svc.setModel(m, 'synth5k');
    await svc.classify('all');
    const { runAggregate } = await import('../src/query');
    const c = runAggregate(modelTable(m), "count where discipline = 'MEC'");
    expect(c.matched).toBe(870);
    expect(c.unknown).toEqual([]);
    const s = runAggregate(modelTable(m), 'sum length by discipline');
    const keys = (s.groups ?? []).map((g) => g.key).sort();
    expect(keys).toEqual(['ARC', 'MEC', 'PLB', 'STR']);
    const mec = (s.groups ?? []).find((g) => g.key === 'MEC')!;
    let sum = 0;
    for (const e of m.elements) if (e.ifcClass === 'IfcDuctSegment') sum += e.props!['Qto_DuctSegmentBaseQuantities.Length'] as number;
    expect(mec.count).toBe(870);
    expect(mec.aggs[0]!.value).toBeCloseTo(sum, 6);
  });

  it('does not write properties when writePset is off, and removes them on clear', async () => {
    const { svc } = makeService();
    const m = sidecarModel('fzk-haus');
    svc.setModel(m, 'fzk-haus');
    svc.patch({ writePset: false });
    await svc.classify('all');
    expect(freshTable(m).propKeys().some((k) => k.startsWith('XR_Classification.'))).toBe(false);
    svc.patch({ writePset: true });
    expect(freshTable(m).propKeys().some((k) => k.startsWith('XR_Classification.'))).toBe(true); // existing results are written when it turns on
    svc.clear();
    expect(freshTable(m).propKeys().some((k) => k.startsWith('XR_Classification.'))).toBe(false);
    expect(svc.results()).toHaveLength(0);
  });

  it('keeps the signature cache per model, schema hash and model id', async () => {
    const storage = new MemoryStorage();
    const m = sidecarModel('fzk-haus');
    const a = makeService({ storage });
    a.svc.setModel(m, 'fzk-haus');
    a.svc.patch({ provider: 'mock' });
    await a.svc.classify('all', { rules: false });
    const calls1 = a.svc.stats().calls;
    expect(calls1).toBeGreaterThan(0);
    // a new session with the same storage: no request
    const b = makeService({ storage });
    b.svc.setModel(sidecarModel('fzk-haus'), 'fzk-haus');
    b.svc.patch({ provider: 'mock' });
    await b.svc.classify('all', { rules: false });
    expect(b.svc.stats().calls).toBe(0);
    expect(b.svc.stats().bySource.cache).toBe(82);
    // another model name, another schema, another provider: separate caches
    const c = makeService({ storage });
    c.svc.setModel(sidecarModel('fzk-haus'), 'other-model');
    c.svc.patch({ provider: 'mock' });
    await c.svc.classify('all', { rules: false });
    expect(c.svc.stats().calls).toBeGreaterThan(0);
    const d = makeService({ storage });
    d.svc.setModel(sidecarModel('fzk-haus'), 'fzk-haus');
    const custom = JSON.parse(JSON.stringify(defaultSchema()));
    custom.disciplines[0].description += ' (changed)';
    expect(d.svc.setSchema(custom)).toEqual([]);
    d.svc.patch({ provider: 'mock' });
    await d.svc.classify('all', { rules: false });
    expect(d.svc.stats().calls).toBeGreaterThan(0);
    expect(schemaHash(custom)).not.toBe(schemaHash(defaultSchema()));
    expect(providerId(d.svc.settings())).toBe('mock:mock-1');
    const keys = [...storage.map.keys()].filter((x) => x.startsWith('xray.classify.cache.'));
    expect(keys.length).toBeGreaterThanOrEqual(3);
  });

  it('keeps a manual override over everything, writes it, and stores it per model', async () => {
    const storage = new MemoryStorage();
    const m = sidecarModel('fzk-haus');
    const { svc } = makeService({ storage });
    svc.setModel(m, 'fzk-haus');
    await svc.classify('all');
    const door = m.elements.find((e) => e.ifcClass === 'IfcDoor')!;
    const r = svc.override(door.globalId, { discipline: 'STR', subDiscipline: 'BRC', masterformat: '05' });
    expect(r).toMatchObject({ source: 'manual', needsReview: false });
    expect(r.discipline).toEqual({ code: 'STR', label: 'Structural', confidence: 1, probabilities: { STR: 1 } });
    expect(door.props!['XR_Classification.Discipline']).toBe('STR');
    expect(door.props!['XR_Classification.Source']).toBe('manual');
    await svc.classify('all'); // a new run does not touch it
    expect(svc.store.get(door.globalId)!.discipline.code).toBe('STR');
    expect(door.props!['XR_Classification.Discipline']).toBe('STR');
    expect(() => svc.override(door.globalId, { discipline: 'MEC', subDiscipline: 'BRC' })).toThrow(/sub-discipline "BRC" is not in the schema for MEC/);
    expect(() => svc.override(door.globalId, { masterformat: '99' })).toThrow(/division "99" is not in the schema/);
    // after a reload with the same storage the override is back, and it still wins
    const again = makeService({ storage });
    const m2 = sidecarModel('fzk-haus');
    again.svc.setModel(m2, 'fzk-haus');
    expect(again.svc.results().map((x) => x.id)).toEqual([door.globalId]);
    await again.svc.classify('all');
    expect(again.svc.store.get(door.globalId)!.source).toBe('manual');
    expect(again.svc.stats().bySource.manual).toBe(1);
    // clear keeps it, removeOverride drops it
    again.svc.clear();
    expect(again.svc.results()).toHaveLength(1);
    again.svc.removeOverride(door.globalId);
    expect(again.svc.results()).toHaveLength(0);
  });

  it('marks and selects needs-review elements and exports CSV and JSON', async () => {
    const { svc } = makeService();
    const m = sidecarModel('fzk-haus');
    svc.setModel(m, 'fzk-haus');
    svc.patch({ provider: 'mock' });
    await svc.classify('all'); // the 42 IfcMember go to the mock model
    const nr = svc.needsReviewIds();
    expect(nr.length).toBeGreaterThan(0);
    expect(nr.every((id) => m.elements[id]!.ifcClass === 'IfcMember')).toBe(true);
    expect(runQuery(m, 'XR_Classification.NeedsReview = TRUE').ids.sort()).toEqual([...nr].sort());
    const csv = svc.export('csv');
    const lines = csv.trim().split('\r\n');
    expect(lines[0]).toBe('GlobalId,Discipline,DisciplineLabel,DisciplineConfidence,DisciplineTop2,SubDiscipline,SubDisciplineConfidence,MasterFormatDivision,MasterFormatTitle,MasterFormatConfidence,BuildingElement,Confidence,Source,Model,NeedsReview,Rationale');
    expect(lines).toHaveLength(83);
    const json = JSON.parse(svc.export('json')) as { schema: string; results: unknown[]; stats: { models: Record<string, number> } };
    expect(json.schema).toBe('xray-classification/1');
    expect(json.results).toHaveLength(82);
    expect(json.stats.models).toEqual({ 'mock-1': svc.stats().calls });
  });

  it('shows the exact payload through questions() and estimates the requests before a run', () => {
    const { svc } = makeService();
    const m = sidecarModel('synth5k');
    svc.setModel(m, 'synth5k');
    const q = svc.questions(svc.buildInput(m.elements.find((e) => e.ifcClass === 'IfcPipeSegment')!.id)!);
    expect(q.model).toBe('jev-1.13.0');
    expect(q.main.questions).toEqual(mainQuestions(svc.schema));
    expect(q.main.state['class']).toBe('IfcPipeSegment');
    expect(q.subFor).toBe('PLB');
    expect(Object.keys((q.sub!.questions['sub_discipline'] as { criteria: object }).criteria)).toEqual(['SUP', 'DRN', 'FIX', 'EQP', 'STM']);
    const e1 = svc.estimate('all');
    expect(e1).toMatchObject({ elements: 5000, byRules: 5000, signatures: 0, calls: 0 });
    const e2 = svc.estimate('all', { rules: false });
    expect(e2.signatures).toBeLessThan(30);
    expect(e2.calls).toBe(e2.signatures * 2);
  });

  it('rejects a schema that is not usable, in plain words, and keeps the old one', () => {
    const { svc } = makeService();
    const hash = svc.schemaHashValue;
    expect(svc.setSchema('{nope')).toEqual([expect.stringMatching(/not valid JSON/)]);
    const errs = svc.setSchema({ schema: 'x', psetName: 'bad name', disciplines: [], masterformat: { divisions: [] } });
    expect(errs.join(' ')).toMatch(/"schema" must be "xray-classification-schema\/1"/);
    expect(errs.join(' ')).toMatch(/"psetName" must be a name/);
    expect(errs.join(' ')).toMatch(/disciplines" must be a list/);
    expect(svc.schemaHashValue).toBe(hash);
    expect(parseSchema(defaultSchema()).errors).toEqual([]);
  });

  it('uses a custom schema end to end: the questions, the pset name and the property names', async () => {
    const { svc } = makeService();
    const m = sidecarModel('fzk-haus');
    svc.setModel(m, 'fzk-haus');
    const s = JSON.parse(JSON.stringify(defaultSchema()));
    s.psetName = 'Throughline_Class';
    s.properties = { discipline: 'Disc', subDiscipline: 'Sub' };
    s.title = 'Test schema';
    s.disciplines.find((d: { code: string }) => d.code === 'ARC').code = 'A';
    s.disciplines.find((d: { code: string }) => d.code === 'A').rulesKey = 'ARC';
    expect(svc.setSchema(s)).toEqual([]);
    expect(svc.questions(svc.buildInput(0)!).main.questions['discipline']).toMatchObject({ type: 'choice' });
    expect(Object.keys((svc.questions(svc.buildInput(0)!).main.questions['discipline'] as { criteria: object }).criteria)).toContain('A');
    await svc.classify('all');
    const door = m.elements.find((e) => e.ifcClass === 'IfcDoor')!;
    expect(door.props!['Throughline_Class.Disc']).toBe('A');
    expect(door.props!['Throughline_Class.Sub']).toBe('DOR');
    expect(door.props!['XR_Classification.Discipline']).toBeUndefined();
  });
});

describe('the WebLLM provider (fake engine, no download)', () => {
  const top = (pairs: Array<[string, number]>): { token: string; logprob: number }[] => pairs.map(([token, p]) => ({ token, logprob: Math.log(p) }));

  it('pins an exact version on the CDN', () => {
    expect(WEBLLM_VERSION).toMatch(/^\d+\.\d+\.\d+$/);
    expect(WEBLLM_CDN_URL).toBe(`https://cdn.jsdelivr.net/npm/@mlc-ai/web-llm@${WEBLLM_VERSION}/+esm`);
  });

  it('turns token log probabilities into option probabilities', () => {
    const labels = labelsFor(['MEC', 'PLB', 'ARC']);
    expect(labels).toEqual(['A', 'B', 'C']);
    const r = probsFromTop(top([['A', 0.6], [' B', 0.2], ['The', 0.1], ['C', 0.05]]), labels)!;
    expect(r.mass).toBeCloseTo(0.85);
    expect(r.p[0]).toBeCloseTo(0.6 / 0.85);
    expect(r.p.reduce((a, b) => a + b, 0)).toBeCloseTo(1);
    expect(probsFromTop(top([['The', 0.9]]), labels)).toBeNull();
    expect(yesFromTop(top([['Y', 0.7], ['N', 0.1]]))).toBeCloseTo(0.875);
    expect(yesFromTop(top([['Maybe', 0.5]]))).toBeNull();
    expect(labelsFor(Array.from({ length: 52 }, (_, i) => String(i)))).toHaveLength(52);
    expect(() => labelsFor(Array.from({ length: 53 }, (_, i) => String(i)))).toThrow(/limit is 52/);
  });

  it('answers a choice, a noul and a score question in the Jev shape, and works under the pipeline', async () => {
    const prompts: string[] = [];
    const engine: WebLlmEngine = {
      chat: {
        completions: {
          create: async (req) => {
            const user = (req['messages'] as Array<{ content: string }>)[1]!.content;
            prompts.push(user);
            expect(req['max_tokens']).toBe(1);
            expect(req['logprobs']).toBe(true);
            expect(req['top_logprobs']).toBe(5);
            const label = /STATEMENT:/.test(user) ? 'Y' : 'B';
            return { choices: [{ logprobs: { content: [{ top_logprobs: top([[label, 0.8], [label === 'Y' ? 'N' : 'A', 0.1]]) }] } }] };
          },
        },
      },
    };
    const p = createWebLlmProvider({ model: 'Qwen2.5-0.5B-Instruct-q4f16_1-MLC', load: async () => engine });
    const q = mainQuestions(defaultSchema());
    const a = await p.decide({ class: 'IfcPump', name: 'P-1' }, q, new AbortController().signal);
    expect(a.model).toBe('webllm:Qwen2.5-0.5B-Instruct-q4f16_1-MLC');
    const d = a.answers['discipline']!;
    expect(d.type === 'choice' && d.choice).toBe('STR'); // option B of the default schema
    expect(d.type === 'choice' && d.confidence).toBeCloseTo(0.8889 * 0.9, 3);
    expect(Object.keys((d as { probabilities: object }).probabilities)).toEqual(Object.keys((q['discipline'] as { criteria: object }).criteria));
    expect(a.answers['building_element']).toMatchObject({ type: 'noul' });
    expect(prompts[0]).toContain('"class":"IfcPump"');
    expect(prompts[0]).toMatch(/A\. ARC - /);
    // it plugs into the pipeline like any provider
    const { classifyInputs } = await import('../src/classify');
    const r = await classifyInputs([{ id: 'x', ifcClass: 'IfcBuildingElementProxy', name: 'Thing', psets: {} }], { schema: defaultSchema(), provider: p, rules: false });
    expect(r.results[0]!.model).toMatch(/^webllm:/);
  });

  it('explains plainly when WebGPU is missing', async () => {
    const none = await detectWebGpu(undefined);
    expect(none.ok).toBe(false);
    expect(none.reason).toMatch(/WebGPU is not available in this browser/);
    expect(none.reason).toMatch(/Jev provider or the rules only/);
    const noAdapter = await detectWebGpu({ gpu: { requestAdapter: async () => null } });
    expect(noAdapter.ok).toBe(false);
    expect(noAdapter.reason).toMatch(/no GPU adapter/);
    expect((await detectWebGpu({ gpu: { requestAdapter: async () => ({}) } })).ok).toBe(true);
    // the provider reports it instead of loading anything
    const p = createWebLlmProvider({ model: 'Qwen2.5-0.5B-Instruct-q4f16_1-MLC' });
    const saved = (globalThis as { navigator?: unknown }).navigator;
    await expect(p.decide({}, mainQuestions(defaultSchema()), new AbortController().signal)).rejects.toThrow(/WebGPU/);
    expect((globalThis as { navigator?: unknown }).navigator).toBe(saved);
  });

  it('the mock provider is deterministic', async () => {
    const q = mainQuestions(defaultSchema());
    const a = await createMockProvider().decide({ class: 'IfcDuctSegment', name: 'Duct' }, q, new AbortController().signal);
    const b = await createMockProvider().decide({ class: 'IfcDuctSegment', name: 'Duct' }, q, new AbortController().signal);
    expect(a).toEqual(b);
    expect(a.answers['discipline']).toMatchObject({ choice: 'MEC' });
  });
});
