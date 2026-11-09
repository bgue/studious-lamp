// Headless smoke test of the LOCAL decision provider: starts vite (bench/vite.smoke.config.mjs) on port 5695, loads synth5k at
// 1600x900 and drives the Classify drawer with Playwright. There is no WebGPU here and no download: page.route serves
// bench/fake-transformers.mjs in place of the CDN module of transformers.js, and answers the config.json requests of Hugging Face.
// It covers: the provider list (the decision model first among the local ones), nothing fetched before use, the WASM fallback
// message, Test model (load time, device, data type, download progress), the model cache size and Clear model cache, classify
// all on synth5k with the rules off and passes per signature and per element type, a custom Hugging Face id that fails (a plain
// message, never downloaded), the Hugging Face token (masked, in no params or link, sent to Hugging Face only), the Throughline
// import and export (a download), the phone layout, and zero console errors.
// Screenshots: bench/classify-local-*.png.
// Usage: SMOKE_PORT=5695 node bench/smoke-classify-local.mjs
import { spawn } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const port = Number(process.env.SMOKE_PORT ?? 5695);

function loadPlaywright() {
  const candidates = [
    process.env.PLAYWRIGHT_MODULE,
    resolve(root, 'node_modules/playwright'),
    '/opt/node-tools/node_modules/playwright',
    '/opt/node22/lib/node_modules/playwright',
  ].filter(Boolean);
  for (const c of candidates) {
    try { return createRequire(import.meta.url)(c); } catch { /* try next */ }
  }
  throw new Error('playwright not found; set PLAYWRIGHT_MODULE');
}
const { chromium } = loadPlaywright();

const vite = spawn(resolve(root, 'node_modules/.bin/vite'), ['--config', resolve(here, 'vite.smoke.config.mjs'), '--host', '127.0.0.1', '--port', String(port), '--strictPort'], {
  cwd: root, stdio: ['ignore', 'pipe', 'pipe'],
});
let viteLog = '';
vite.stdout.on('data', (d) => (viteLog += d));
vite.stderr.on('data', (d) => (viteLog += d));

async function waitForServer() {
  for (let i = 0; i < 100; i++) {
    try { const r = await fetch(`http://127.0.0.1:${port}/`); if (r.ok) return; } catch { /* retry */ }
    await new Promise((r) => setTimeout(r, 200));
  }
  throw new Error('vite did not start:\n' + viteLog);
}

const checks = [];
function check(name, ok, detail = '') {
  checks.push({ name, ok });
  console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${detail ? ` (${detail})` : ''}`);
}

const GL = ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'];
const CDN = 'https://cdn.jsdelivr.net/npm/@huggingface/transformers@4.3.2/dist/transformers.min.js';
const FAKE_LIB = readFileSync(resolve(here, 'fake-transformers.mjs'), 'utf8');
const HF_TOKEN = 'hf_SmokeTestToken0123456789abcdef';
const shot = (page, name) => page.screenshot({ path: resolve(here, name), timeout: 180000 });
const CORS = { 'access-control-allow-origin': '*', 'access-control-allow-headers': '*', 'access-control-allow-methods': 'GET, POST, OPTIONS' };

// What Hugging Face answers for a model's config.json: an NLI model, or a chat model that must be refused.
const NLI_CONFIG = { architectures: ['DebertaV2ForSequenceClassification'], id2label: { 0: 'contradiction', 1: 'entailment', 2: 'neutral' }, label2id: { contradiction: 0, entailment: 1, neutral: 2 } };
const LLM_CONFIG = { architectures: ['Qwen2ForCausalLM'], model_type: 'qwen2' };
const CONFIGS = { 'org/custom-nli': NLI_CONFIG, 'org/chat-llm': LLM_CONFIG };

async function open(browser, opts = {}) {
  const ctx = await browser.newContext({ viewport: opts.viewport ?? { width: 1600, height: 900 }, acceptDownloads: true });
  await ctx.addInitScript(() => { try { localStorage.setItem('xray.help', 'off'); } catch { /* no storage */ } }); // no hover tooltip over the screenshots
  const page = await ctx.newPage();
  const errors = [];
  const net = { cdn: [], hf: [], foreign: [] };
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', (e) => errors.push(`[pageerror] ${e.message}`));
  await page.route(/^https?:\/\/(?!127\.0\.0\.1)/, async (route) => {
    const req = route.request();
    const url = req.url();
    if (req.method() === 'OPTIONS') return route.fulfill({ status: 204, headers: CORS });
    if (url === CDN) {
      net.cdn.push({ url, auth: req.headers()['authorization'] ?? null });
      return route.fulfill({ status: 200, headers: { ...CORS, 'content-type': 'text/javascript' }, body: FAKE_LIB });
    }
    const m = /^https:\/\/huggingface\.co\/(.+?)\/(.+?)\/resolve\/main\/config\.json$/.exec(url);
    if (m) {
      const id = `${m[1]}/${m[2]}`;
      net.hf.push({ url, auth: req.headers()['authorization'] ?? null });
      const cfg = CONFIGS[id];
      return cfg ? route.fulfill({ status: 200, headers: { ...CORS, 'content-type': 'application/json' }, body: JSON.stringify(cfg) }) : route.fulfill({ status: 404, headers: CORS, body: '' });
    }
    if (/^https:\/\/huggingface\.co\/api\/models\//.test(url)) {
      net.hf.push({ url, auth: req.headers()['authorization'] ?? null });
      return route.fulfill({ status: 200, headers: { ...CORS, 'content-type': 'application/json' }, body: JSON.stringify({ siblings: [{ rfilename: 'onnx/model.onnx', size: 738563249 }, { rfilename: 'onnx/model_quantized.onnx', size: 244291155 }] }) });
    }
    net.foreign.push(url);
    return route.abort();
  });
  await page.goto(`http://127.0.0.1:${port}/?model=synth5k`);
  await page.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: 120000 });
  const err = await page.evaluate('window.__xrayError');
  if (err) errors.push(`[app] ${err}`);
  await page.waitForFunction('window.__xraySearch && window.__xraySearch.indexReady() && window.__xrayClassify', null, { timeout: 60000 });
  await page.waitForTimeout(500);
  return { ctx, page, errors, net };
}

const openDrawer = async (page) => {
  await page.locator('.xt-btn-tool[data-tool="classify"]').click();
  await page.waitForSelector('.xt-drawer:not(.hidden) .xt-table');
  await page.waitForTimeout(300);
};
const drawerText = (page) => page.locator('.xt-drawer').textContent();
const field = (page, label) => page.locator('.xt-drawer label.xt-select', { has: page.locator('.xt-lbl', { hasText: new RegExp(`^${label}$`) }) });
const btn = (page, text) => page.locator('.xt-drawer .xt-btn', { hasText: text });

// ---------------------------------------------------------------- desktop

async function runDesktop(browser) {
  const tag = '[synth5k]';
  const { ctx, page, errors, net } = await open(browser);
  try {
    await openDrawer(page);

    // ---- the provider list: the decision model is the first local option
    const opts = await page.locator('.xt-drawer label.xt-select', { has: page.locator('.xt-lbl', { hasText: /^Provider$/ }) }).locator('option').allTextContents();
    console.log(tag, 'providers:', opts.join(' | '));
    check(`${tag} the provider list shows "Decision model (in browser, WebGPU)" first among the local options`, opts[1] === 'Decision model (in browser, WebGPU)' && opts.indexOf('Decision model (in browser, WebGPU)') < opts.findIndex((o) => /WebLLM/.test(o)), opts.slice(0, 3).join(' | '));
    await page.locator('.xt-drawer label.xt-select', { has: page.locator('.xt-lbl', { hasText: /^Provider$/ }) }).locator('select').selectOption('decision');
    await page.waitForTimeout(400);
    const t0 = await drawerText(page);
    check(`${tag} the decision model shows its settings: model list, Hugging Face id, device, data type, Test model, Clear model cache`,
      (await field(page, 'Decision model').count()) === 1 && (await field(page, 'Hugging Face model id').isVisible()) && (await field(page, 'Device').isVisible()) && (await field(page, 'Data type').isVisible())
      && (await btn(page, 'Test model').isVisible()) && (await btn(page, 'Clear model cache').isVisible()) && !(await btn(page, 'Test connection').isVisible()));
    check(`${tag} the model list shows download sizes`, /download 87 MB \(q8\)|fp32 284 MB, q8 87 MB|download fp32 284 MB, q8 87 MB/.test(t0), t0.match(/DeBERTa[^.]*\. [^.]*MB[^.]*\./)?.[0] ?? '');
    check(`${tag} the default is the xsmall zero-shot model`, (await field(page, 'Hugging Face model id').locator('input').inputValue()) === 'MoritzLaurer/deberta-v3-xsmall-zeroshot-v1.1-all-33');
    check(`${tag} nothing was fetched from the CDN or Hugging Face before the model is used`, net.cdn.length === 0 && net.hf.length === 0, `cdn ${net.cdn.length}, hf ${net.hf.length}`);
    const adv = await page.locator('.xt-drawer details.xc-adv summary').allTextContents();
    check(`${tag} the advanced section holds the endpoint and the hypotheses`, adv.some((s) => /endpoint and hypotheses/.test(s)));
    await shot(page, 'classify-local-decision.png');

    // ---- Test model: WASM fallback, load time, device, data type, download progress
    const gpu = await page.evaluate(async () => !!navigator.gpu && !!(await navigator.gpu.requestAdapter().catch(() => null)));
    await btn(page, 'Test model').click();
    await page.waitForFunction(() => /Ready:|could not|Could not/.test(document.querySelector('.xt-drawer')?.textContent ?? ''), null, { timeout: 30000 });
    await page.waitForTimeout(300);
    const t1 = await drawerText(page);
    const ready = /Ready: MoritzLaurer\/deberta-v3-xsmall-zeroshot-v1\.1-all-33 on (\w+) \((\w+)\) in ([\d.]+) s/.exec(t1);
    console.log(tag, 'test model:', t1.match(/Ready:[^\n]*?\. Test question[^\n]*?ms\./)?.[0] ?? t1.slice(0, 300));
    check(`${tag} Test model loads the model and reports the load time, device and data type`, !!ready, ready?.slice(1).join(' '));
    if (!gpu) {
      check(`${tag} without WebGPU the device is wasm with q8, and the note says "Slower" in plain words`, ready?.[1] === 'wasm' && ready?.[2] === 'q8' && /Slower: .*(no WebGPU|no GPU adapter)/.test(t1));
    } else {
      check(`${tag} WebGPU is present here: the device is webgpu`, ready?.[1] === 'webgpu');
    }
    check(`${tag} Test model runs one tiny choice and names the answer`, /Test question: chose MEC \(0\.\d\d\) in \d+ ms/.test(t1));
    const prog = await page.evaluate(() => ({ line: [...document.querySelectorAll('.xt-drawer .xt-status')].map((e) => e.textContent).find((t) => /Downloading/.test(t)) ?? '', w: [...document.querySelectorAll('.xt-drawer .xc-prog > i')].map((i) => i.style.width) }));
    check(`${tag} the download progress reaches 100 percent and shows the size`, /Downloading 87 of 87 MB/.test(prog.line) && prog.w.includes('100%'), `${prog.line} ${prog.w.join(',')}`);
    check(`${tag} the library came from the pinned CDN URL, once, with no token`, net.cdn.length === 1 && net.cdn[0].url === CDN && net.cdn[0].auth === null);
    const log1 = await page.evaluate(() => window.__fakeTransformersLog.pipelines);
    check(`${tag} the pipeline was created for zero-shot-classification with the device and data type`, log1.length === 1 && log1[0].task === 'zero-shot-classification' && log1[0].model === 'MoritzLaurer/deberta-v3-xsmall-zeroshot-v1.1-all-33' && log1[0].device === (gpu ? 'webgpu' : 'wasm'), JSON.stringify(log1[0]));
    const gpuLine = await page.locator('.xt-drawer .xt-note[role=status]').allTextContents();
    check(`${tag} the drawer says where the model runs`, /Device (wasm|webgpu), data type (q8|fp32|fp16)/.test(gpuLine.join(' ')), gpuLine.join(' | ').slice(0, 160));

    // ---- the model cache: size and Clear model cache
    await page.evaluate(async () => { const c = await caches.open('transformers-cache'); await c.put('https://huggingface.co/x/y/resolve/main/model.onnx', new Response(new Uint8Array(5_000_000), { headers: { 'Content-Length': '5000000' } })); });
    await btn(page, 'Test model').click();
    await page.waitForFunction(() => /Model cache: 5 MB in 1 file/.test(document.querySelector('.xt-drawer')?.textContent ?? ''), null, { timeout: 15000 });
    check(`${tag} the drawer shows the cache size`, /Model cache: 5 MB in 1 file/.test(await drawerText(page)));
    await btn(page, 'Clear model cache').click();
    await page.waitForFunction(() => /Model cache: empty/.test(document.querySelector('.xt-drawer')?.textContent ?? ''), null, { timeout: 15000 });
    check(`${tag} Clear model cache empties it`, (await page.evaluate(async () => (await window.__xrayClassify.modelCache()).files)) === 0 && /deleted from the browser cache/.test(await drawerText(page)));
    await btn(page, 'Test model').click();
    await page.waitForFunction(() => /Ready:/.test(document.querySelector('.xt-drawer')?.textContent ?? ''), null, { timeout: 15000 });

    // ---- classify all, rules off: the decision model decides every signature
    const est = await page.evaluate(() => window.__xrayClassify.estimate('all', { rules: false }));
    console.log(tag, 'estimate (rules off)', JSON.stringify(est));
    const s0 = await page.evaluate(() => window.__xrayClassify.decisionStats());
    const t2 = Date.now();
    await page.evaluate(() => window.__xrayClassify.classify('all', { rules: false }));
    const ms = Date.now() - t2;
    const stats = await page.evaluate(() => window.__xrayClassify.stats());
    const s1 = await page.evaluate(() => window.__xrayClassify.decisionStats());
    const run = { requests: s1.requests - s0.requests, pairs: s1.pairs - s0.pairs, passes: s1.passes - s0.passes, cached: s1.cachedPairs - s0.cachedPairs };
    console.log(tag, `classify all, rules off: ${ms} ms`, JSON.stringify({ signatures: stats.signatures, bySource: stats.bySource, models: stats.models, ...run, pairsPerSignature: +(run.pairs / stats.signatures).toFixed(1), passesPerSignature: +(run.passes / stats.signatures).toFixed(1) }));
    check(`${tag} classify all with the rules off: 5000 results from the decision model, 9 signatures, the cache answers the rest`, stats.total === 5000 && stats.signatures === 9 && stats.bySource.model + stats.bySource.cache === 5000 && stats.bySource.rules === 0 && stats.failed === 0);
    check(`${tag} every result carries the model id of the decision model`, await page.evaluate(() => window.__xrayClassify.results().every((r) => r.model === 'decision:MoritzLaurer/deberta-v3-xsmall-zeroshot-v1.1-all-33')));
    check(`${tag} passes per signature: 6 to 9 forward passes, 52 to 64 text pairs (batches of 8)`, run.passes / stats.signatures >= 6 && run.passes / stats.signatures <= 9 && run.pairs / stats.signatures >= 52 && run.pairs / stats.signatures <= 64, `${(run.passes / stats.signatures).toFixed(1)} passes, ${(run.pairs / stats.signatures).toFixed(1)} pairs`);
    const reported = await page.waitForFunction(() => /Decision model: \d+ text pairs in \d+ passes/.test(document.querySelector('.xt-drawer')?.textContent ?? ''), null, { timeout: 20000 }).then(() => true, () => false);
    check(`${tag} the drawer reports the pairs and passes of the run`, reported);
    const again = await page.evaluate(async () => { const a = window.__xrayClassify.decisionStats().passes; await window.__xrayClassify.classify('all', { rules: false }); return window.__xrayClassify.decisionStats().passes - a; });
    check(`${tag} a second run is answered from the signature cache (0 passes)`, again === 0);
    const dist = await page.evaluate(() => { const o = {}; for (const r of window.__xrayClassify.results()) o[r.discipline.code] = (o[r.discipline.code] ?? 0) + 1; return o; });
    console.log(tag, 'disciplines', JSON.stringify(dist));
    check(`${tag} the fake model puts ducts in MEC and slabs in STR`, await page.evaluate(() => {
      const m = window.__xray.app.controller.model;
      const by = (c) => { const e = m.elements.find((x) => x.ifcClass === c); return window.__xrayClassify.results().find((r) => r.id === e.globalId)?.discipline.code; };
      return by('IfcDuctSegment') === 'MEC' && by('IfcSlab') === 'STR';
    }));

    // ---- passes per element type: one element of each class, on a fresh provider (an empty pair cache) and an empty signature cache
    const known = await page.evaluate(async () => {
      const m = window.__xray.app.controller.model;
      const a = window.__xrayClassify.decisionStats().passes;
      await window.__xrayClassify.classify([m.elements[0].globalId], { rules: false });
      return window.__xrayClassify.decisionStats().passes - a;
    });
    check(`${tag} an element of a known signature needs no pass`, known === 0);
    await page.evaluate(() => window.__xrayClassify.clear());
    await page.locator('.xt-drawer .xt-btn', { hasText: 'Clear cache' }).click();
    await page.evaluate(() => { window.__xrayClassify.configure({ device: 'wasm' }); window.__xrayClassify.decisionStats(); window.__xrayClassify.configure({ device: 'auto' }); window.__xrayClassify.decisionStats(); }); // a new provider: no pair cache
    const perType = await page.evaluate(async () => {
      const api = window.__xrayClassify;
      const m = window.__xray.app.controller.model;
      const classes = [...new Set(m.elements.map((e) => e.ifcClass))];
      const out = [];
      for (const c of classes) {
        const e = m.elements.find((x) => x.ifcClass === c);
        const before = api.decisionStats();
        await api.classify([e.globalId], { rules: false });
        const after = api.decisionStats();
        const r = api.results().find((x) => x.id === e.globalId);
        out.push({ class: c, discipline: r?.discipline.code, sub: r?.subDiscipline?.code, requests: after.requests - before.requests, pairs: after.pairs - before.pairs, passes: after.passes - before.passes, ms: after.ms - before.ms });
      }
      return out;
    });
    console.log(tag, 'passes per element type (a fresh provider, an empty cache, batches of 8):');
    for (const x of perType) console.log(`  ${x.class.padEnd(20)} ${x.discipline}/${x.sub}  requests ${x.requests}, text pairs ${x.pairs}, forward passes ${x.passes}`);
    check(`${tag} each element type costs 2 requests, 52 to 64 text pairs and 7 to 9 forward passes`, perType.length === 6 && perType.every((x) => x.requests === 2 && x.pairs >= 52 && x.pairs <= 64 && x.passes >= 7 && x.passes <= 9), JSON.stringify(perType.map((x) => [x.pairs, x.passes])));
    await page.evaluate(() => window.__xrayClassify.classify('all', { rules: false }));
    await page.evaluate(() => window.__xray.app.selectIds(window.__xray.app.controller.model.elements.slice(0, 40).map((e) => e.id)));
    await page.waitForTimeout(400);
    await page.locator('.xt-drawer .xt-table-wrap').scrollIntoViewIfNeeded();
    await page.evaluate(() => { const b = document.querySelector('.xt-body'); b.scrollTop = b.scrollHeight * 0.5; });
    await page.waitForTimeout(250);
    await shot(page, 'classify-local-results.png');
    await page.evaluate(() => { document.querySelector('.xt-body').scrollTop = 0; });

    // ---- a custom Hugging Face id that fails: a plain message
    const idInput = field(page, 'Hugging Face model id').locator('input');
    await idInput.fill('not a model');
    await idInput.press('Enter');
    await page.waitForFunction(() => [...document.querySelectorAll('.xt-drawer .xt-note')].some((n) => /hfModel: "not a model" is not a model id/.test(n.textContent)), null, { timeout: 20000 });
    const bad = await page.locator('.xt-drawer .xt-note.xc-err').allTextContents();
    check(`${tag} a malformed custom id gives a plain message and keeps the default`, bad.some((x) => /hfModel: "not a model" is not a model id\. Use owner\/name/.test(x)) && (await page.evaluate(() => window.__xrayClassify.settings().hfModel)) === 'MoritzLaurer/deberta-v3-xsmall-zeroshot-v1.1-all-33', bad.join(' | ').slice(0, 200));
    await shot(page, 'classify-local-invalid-id.png');
    await idInput.fill('org/chat-llm');
    await idInput.press('Enter');
    await idInput.blur();
    await page.evaluate(() => window.__fakeTransformersLog.pipelines.length = 0);
    const hf0 = net.hf.length;
    await btn(page, 'Test model').click();
    await page.waitForFunction(() => /is not a classifier/.test(document.querySelector('.xt-drawer')?.textContent ?? ''), null, { timeout: 15000 });
    const t3 = await drawerText(page);
    check(`${tag} a chat model as the custom id is refused in plain words before any download`, /"org\/chat-llm" is not a classifier \(its architecture is Qwen2ForCausalLM\), so it cannot decide among options/.test(t3) && /sequence-classification \(NLI\) model/.test(t3));
    check(`${tag} the refused model created no pipeline (nothing downloaded)`, (await page.evaluate(() => window.__fakeTransformersLog.pipelines.length)) === 0 && net.hf.length > hf0);
    await idInput.fill('org/does-not-exist');
    await idInput.press('Enter');
    await idInput.blur();
    await btn(page, 'Test model').click();
    await page.waitForFunction(() => /was not found at https:\/\/huggingface\.co/.test(document.querySelector('.xt-drawer')?.textContent ?? ''), null, { timeout: 15000 });
    check(`${tag} an id that does not exist says so, with the endpoint`, /"org\/does-not-exist" was not found at https:\/\/huggingface\.co\. Check the spelling/.test(await drawerText(page)));

    // ---- a good custom model, and the token goes to Hugging Face only
    await field(page, 'Hugging Face token').locator('input').fill(HF_TOKEN);
    await btn(page, 'Save token').click();
    const tokenText = await page.locator('.xt-drawer .xt-status', { hasText: 'Hugging Face token' }).textContent();
    check(`${tag} the token is masked in the drawer and the box empties`, !tokenText.includes(HF_TOKEN) && /hidden/.test(tokenText) && (await field(page, 'Hugging Face token').locator('input').inputValue()) === '', tokenText);
    await idInput.fill('org/custom-nli');
    await idInput.press('Enter');
    await idInput.blur();
    const hf1 = net.hf.length;
    await btn(page, 'Test model').click();
    await page.waitForFunction(() => /Ready: org\/custom-nli/.test(document.querySelector('.xt-drawer')?.textContent ?? ''), null, { timeout: 15000 });
    const t4 = await drawerText(page);
    check(`${tag} a custom NLI model loads, with its file sizes from the Hub shown`, /Ready: org\/custom-nli on (wasm|webgpu) \((q8|fp32|fp16)\)/.test(t4) && /Files: fp32 739 MB, q8 244 MB/.test(t4));
    const hfReqs = net.hf.slice(hf1);
    check(`${tag} the token went to huggingface.co (the config check)`, hfReqs.length >= 1 && hfReqs.every((r) => r.auth === `Bearer ${HF_TOKEN}`), JSON.stringify(hfReqs.map((r) => !!r.auth)));
    check(`${tag} the token went nowhere else (CDN and foreign hosts)`, net.cdn.every((r) => r.auth === null) && net.foreign.length === 0, net.foreign.join(' '));
    const stored = await page.evaluate(() => ({ s: Object.keys(sessionStorage).filter((k) => /classify/.test(k)), l: Object.keys(localStorage).filter((k) => /hfToken|apiKey/i.test(k)) }));
    check(`${tag} the token is in sessionStorage under its own name, not in localStorage`, stored.s.includes('xray.classify.hfToken') && stored.l.length === 0, JSON.stringify(stored));
    const doc = await page.evaluate(() => JSON.stringify(window.__xray.exportParams?.collect?.() ?? window.__xrayParams?.collect?.() ?? {}));
    const share = await page.evaluate(() => (window.__xrayParams?.shareUrl ?? window.__xray.exportParams?.shareUrl)?.() ?? '');
    const dump = await page.evaluate(() => JSON.stringify({ ...localStorage }));
    const leaks = (s) => s.includes(HF_TOKEN) || s.includes(btoa(HF_TOKEN).replace(/=+$/, ''));
    check(`${tag} the token is not in the exported params, the share link or localStorage`, !leaks(doc) && !leaks(share) && !leaks(dump) && /org\/custom-nli/.test(doc), `params ${doc.length} chars`);
    check(`${tag} the settings hold no token field`, !(await page.evaluate(() => JSON.stringify(window.__xrayClassify.settings()))).match(/hf_|token/i));
    await btn(page, 'Forget token').click();
    check(`${tag} Forget token removes it`, !(await page.evaluate(() => window.__xrayClassify.hfTokenState().set)));
    await idInput.fill('MoritzLaurer/deberta-v3-xsmall-zeroshot-v1.1-all-33');
    await idInput.press('Enter');
    await idInput.blur();

    // ---- the Throughline export (a download) and import
    await page.evaluate(() => window.__xrayClassify.clear());
    await page.evaluate(() => window.__xrayClassify.classify('all', { rules: false }));
    const dl = page.waitForEvent('download', { timeout: 15000 });
    await btn(page, 'Export Throughline JSON').click();
    const d = await dl;
    const ex = JSON.parse(readFileSync(await d.path(), 'utf8'));
    console.log(tag, 'throughline export', d.suggestedFilename(), `${ex.count} elements, ${ex.code_values.length} code values, needs_crosswalk ${JSON.stringify(ex.needs_crosswalk)}`);
    check(`${tag} the Throughline export downloads with a discipline code per element and attributes`, d.suggestedFilename().endsWith('.throughline.json') && ex.format === 'xray-throughline-classification/1' && ex.count === 5000 && ex.elements.every((e) => typeof e.discipline === 'string' && 'sub_discipline' in e.attributes && 'masterformat_division' in e.attributes));
    check(`${tag} the export carries the Discipline code list with Throughline fields, and says which codes need a crosswalk`, ex.code_list.code_list === 'Discipline' && ex.code_values.length === 11 && ['code_list', 'code', 'label', 'meaning', 'crosswalk', 'origin', 'sort_order', 'edition', 'attributes'].every((k) => k in ex.code_values[0]) && Array.isArray(ex.needs_crosswalk));
    const apiEx = await page.evaluate(() => window.__xrayClassify.export('throughline'));
    check(`${tag} export('throughline') returns the same text`, apiEx === readFileSync(await d.path(), 'utf8'));

    // import a company list
    const company = [
      { code_list: 'Discipline', code: 'M', label: 'Mechanical', sort_order: 10, origin: 'company', edition: 'co.acme.standards@2.0.0', attributes: { rules_key: 'MEC', description: 'Ducts, fans, HVAC.' } },
      { code_list: 'Discipline', code: 'S', label: 'Structural', sort_order: 20, origin: 'company', edition: 'co.acme.standards@2.0.0', attributes: { rules_key: 'STR' } },
      { code_list: 'Discipline', code: 'G', label: 'General', sort_order: 99, origin: 'company', edition: 'co.acme.standards@2.0.0', attributes: { fallback: true } },
    ];
    await page.locator('.xt-drawer input[type=file]').nth(1).setInputFiles({ name: 'discipline.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(company)) });
    await page.waitForFunction(() => /Throughline Discipline list \(co\.acme\.standards@2\.0\.0\)/.test(document.querySelector('.xt-drawer')?.textContent ?? ''), null, { timeout: 10000 });
    const t5 = await drawerText(page);
    check(`${tag} Import Throughline list replaces the schema and the drawer shows notes`, /3 disciplines/.test(t5) && /have no description/.test(t5) && !/Load the Discipline code list of your company standards/.test(t5));
    await page.evaluate(() => window.__xrayClassify.classify('all'));
    const imp = await page.evaluate(() => { const o = {}; for (const r of window.__xrayClassify.results()) o[`${r.discipline.code}:${r.source}`] = (o[`${r.discipline.code}:${r.source}`] ?? 0) + 1; return o; });
    console.log(tag, 'with the imported list', JSON.stringify(imp));
    check(`${tag} the rules still work with the company codes: ducts are M, slabs and beams are S`, (imp['M:rules'] ?? 0) === 870 && (imp['S:rules'] ?? 0) > 0);
    await btn(page, 'Use built-in schema').click();
    await page.waitForFunction(() => /Throughline-aligned default \(built in\)/.test(document.querySelector('.xt-drawer')?.textContent ?? ''), null, { timeout: 20000 }).catch(() => {});
    check(`${tag} Use built-in schema returns to the Throughline-aligned default`, /Throughline-aligned default \(built in\)/.test(await drawerText(page)));
    await page.locator('.xt-drawer input[type=file]').nth(1).setInputFiles({ name: 'bad.json', mimeType: 'application/json', buffer: Buffer.from('{"nope": 1}') });
    await page.waitForFunction(() => /JSON list of Discipline entries/.test(document.querySelector('.xt-drawer')?.textContent ?? ''), null, { timeout: 10000 });
    check(`${tag} a file that is not a Discipline list is refused in plain words`, true);
    await page.evaluate(() => window.__xrayClassify.configure({ provider: 'off' }));

    // ---- the WebLLM modes show their settings, without WebGPU a plain message
    await page.evaluate(() => window.__xrayClassify.clear());
    await page.evaluate(() => window.__xrayClassify.configure({ provider: 'webllm', webllmMode: 'hybrid' }));
    await page.waitForSelector('.xt-drawer .xc-group[data-for=webllm]:not([hidden])', { timeout: 20000 });
    await page.waitForTimeout(300);
    const t6 = await drawerText(page);
    check(`${tag} WebLLM hybrid shows the mode, both models and the margin`, (await field(page, 'Mode').isVisible()) && (await field(page, 'Embedding model').isVisible()) && (await field(page, 'Hybrid margin').isVisible()) && /Qwen3 0\.6B/.test(t6) && /Snowflake Arctic Embed S/.test(t6) && /download about 347 MB, GPU memory about 1403 MB/.test(t6));
    await page.evaluate(() => window.__xrayClassify.configure({ provider: 'off' }));
  } finally {
    // The one 404 is the probe of a model id that does not exist: the browser logs every failed fetch, and the app handles it.
    const notFound = errors.filter((e) => /status of 404/.test(e));
    const real = errors.filter((e) => !/favicon|status of 404/i.test(e));
    check(`${tag} zero console errors (apart from the one 404 of the missing-model probe)`, real.length === 0 && notFound.length === 1, real.slice(0, 3).join(' | ') || `404s: ${notFound.length}`);
    await ctx.close();
  }
}

// ---------------------------------------------------------------- phone

async function runPhone(browser) {
  const tag = '[phone]';
  const { ctx, page, errors } = await open(browser, { viewport: { width: 390, height: 844 } });
  try {
    await openDrawer(page);
    await page.evaluate(() => window.__xrayClassify.configure({ provider: 'decision' }));
    await page.waitForTimeout(400);
    await btn(page, 'Test model').click();
    await page.waitForFunction(() => /Ready:/.test(document.querySelector('.xt-drawer')?.textContent ?? ''), null, { timeout: 30000 });
    await page.evaluate(() => window.__xrayClassify.classify('all', { rules: false }));
    await page.waitForTimeout(500);
    const box = await page.evaluate(() => {
      const dr = document.querySelector('.xt-drawer').getBoundingClientRect();
      return { right: dr.right, vw: window.innerWidth, scrollW: document.documentElement.scrollWidth };
    });
    check(`${tag} the drawer fits inside the phone width`, box.right <= box.vw + 1 && box.scrollW <= box.vw + 1, JSON.stringify(box));
    const inside = await page.evaluate(() => [...document.querySelectorAll('.xt-drawer .xt-btn, .xt-drawer input, .xt-drawer select')].filter((e) => e.offsetParent !== null).every((b) => b.getBoundingClientRect().right <= window.innerWidth + 1));
    check(`${tag} every visible button and field is inside the screen`, inside);
    await shot(page, 'classify-local-phone.png');
  } finally {
    const real = errors.filter((e) => !/favicon/i.test(e));
    check(`${tag} zero console errors`, real.length === 0, real.slice(0, 3).join(' | '));
    await ctx.close();
  }
}

let browser;
let exitCode = 0;
try {
  await waitForServer();
  browser = await chromium.launch({ args: GL });
  await runDesktop(browser);
  await runPhone(browser);
  if (checks.some((c) => !c.ok)) exitCode = 1;
  console.log(`\n${checks.filter((c) => c.ok).length}/${checks.length} checks passed`);
} catch (e) {
  console.error(e);
  exitCode = 1;
} finally {
  if (browser) await browser.close();
  vite.kill('SIGTERM');
}
process.exit(exitCode);
