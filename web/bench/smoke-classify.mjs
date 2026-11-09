// Headless smoke test for the Classify tool: starts vite (bench/vite.smoke.config.mjs) on port 5691, loads synth5k at
// 1600x900 and drives the drawer and window.__xrayClassify with Playwright. The Jev endpoint is a page.route that returns
// Jev-shaped answers (no real network). It covers: classify all with the rules (0 requests) and with the rules off (requests
// against elements), a WHERE on discipline in the search bar, colour by discipline, a manual override, the CSV export,
// the WebLLM provider without WebGPU (a plain message), the phone layout, and zero console errors.
// Screenshots: bench/classify-*.png.
// Usage: SMOKE_PORT=5691 node bench/smoke-classify.mjs
import { spawn } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const port = Number(process.env.SMOKE_PORT ?? 5691);

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
const KEY = 'sk-smoke-test-key-123';
const JEV = 'https://api.typesafe.ai/v1/systemone';
const shot = (page, name) => page.screenshot({ path: resolve(here, name), timeout: 180000 });

// ---------------------------------------------------------------- the fake Jev endpoint

/** IFC classes that the fake endpoint answers with a low confidence and a close runner-up. */
const lowFor = new Set();

/** Decide by the IFC class in the state, like a model that knows IFC. Returns the Jev response for a request. */
function fakeJev(req) {
  const cls = String(req.state.class ?? '');
  const map = {
    IfcDuctSegment: ['MEC', '23', 'DUC'], IfcPipeSegment: ['PLB', '22', 'SUP'], IfcBeam: ['STR', '05', 'BEM'],
    IfcColumn: ['STR', '05', 'COL'], IfcSlab: ['STR', '03', 'SLB'], IfcWall: ['ARC', '09', 'WAL'],
  };
  const [disc, div, sub] = map[cls] ?? ['GEN', '01', 'UNC'];
  const answers = {};
  for (const [name, q] of Object.entries(req.questions)) {
    if (q.type === 'noul') { answers[name] = { type: 'noul', noul: 0.97 }; continue; }
    const options = Object.keys(q.criteria);
    const want = name === 'discipline' ? disc : name === 'masterformat' ? div : options.find((o) => o === sub || o.endsWith(`/${sub}`)) ?? options[0];
    const probabilities = {};
    const rest = options.filter((o) => o !== want);
    const low = lowFor.has(cls) && name === 'discipline';
    probabilities[want] = low ? 0.5 : 0.9;
    rest.forEach((o, i) => { probabilities[o] = low ? (i === 0 ? 0.42 : 0.08 / Math.max(1, rest.length - 1)) : i === 0 ? 0.05 : 0.05 / Math.max(1, rest.length - 1); });
    answers[name] = { type: 'choice', choice: want, confidence: probabilities[want], probabilities };
  }
  return { model: req.model, answers, usage: { input_tokens: 700, output_tokens: 5 } };
}

async function open(browser, opts = {}) {
  const ctx = await browser.newContext({ viewport: opts.viewport ?? { width: 1600, height: 900 }, acceptDownloads: true });
  const page = await ctx.newPage();
  const errors = [];
  const jev = { calls: 0, auth: [], models: new Set(), foreign: [] };
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', (e) => errors.push(`[pageerror] ${e.message}`));
  await page.route(/^https?:\/\/(?!127\.0\.0\.1)/, async (route) => {
    const req = route.request();
    const cors = { 'access-control-allow-origin': '*', 'access-control-allow-headers': '*', 'access-control-allow-methods': 'POST, OPTIONS' };
    if (req.method() === 'OPTIONS') return route.fulfill({ status: 204, headers: cors });
    if (req.url() === JEV) {
      jev.calls++;
      jev.auth.push(req.headers()['authorization'] ?? '');
      const body = JSON.parse(req.postData() ?? '{}');
      jev.models.add(body.model);
      return route.fulfill({ status: 200, headers: { ...cors, 'content-type': 'application/json' }, body: JSON.stringify(fakeJev(body)) });
    }
    jev.foreign.push(req.url());
    return route.abort();
  });
  await page.goto(`http://127.0.0.1:${port}/?model=synth5k`);
  await page.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: 120000 });
  const err = await page.evaluate('window.__xrayError');
  if (err) errors.push(`[app] ${err}`);
  await page.waitForFunction('window.__xraySearch && window.__xraySearch.indexReady() && window.__xrayClassify', null, { timeout: 60000 });
  await page.waitForTimeout(500);
  return { ctx, page, errors, jev };
}

const openDrawer = async (page) => {
  await page.locator('.xt-btn-tool[data-tool="classify"]').click();
  await page.waitForSelector('.xt-drawer:not(.hidden) .xt-table');
  await page.waitForTimeout(300);
};
const ensureDrawer = async (page) => {
  if (await page.locator('.xt-drawer.hidden').count()) await openDrawer(page);
};
const typeInBar = async (page, text) => {
  await page.keyboard.press('/');
  await page.locator('.ab-input').fill('');
  await page.keyboard.type(text);
  await page.waitForTimeout(250);
};

// ---------------------------------------------------------------- desktop

async function runDesktop(browser) {
  const tag = '[synth5k]';
  const { ctx, page, errors, jev } = await open(browser);
  try {
    check(`${tag} the Classify tool is in the action panel`, (await page.locator('.xt-btn-tool[data-tool="classify"]').count()) === 1);
    await openDrawer(page);
    {
      const dt = await page.locator('.xt-drawer').textContent();
      check(`${tag} the drawer names the Throughline-aligned default schema and says how to replace it`, /Throughline-aligned default/.test(dt) && /Load the Discipline code list of your company standards/.test(dt) && !/PLACEHOLDER/.test(dt));
    }

    // ---- the settings: jev, key, test connection
    await page.evaluate(() => window.__xrayClassify.configure({ provider: 'jev' }));
    await page.waitForTimeout(200);
    await page.locator('.xt-drawer input[aria-label="API key"]').fill(KEY);
    await page.locator('.xt-drawer .xt-btn', { hasText: 'Save key' }).click();
    const keyText = await page.locator('.xt-drawer .xt-status', { hasText: 'API key' }).textContent();
    check(`${tag} the key is masked in the drawer`, !keyText.includes(KEY) && /hidden/.test(keyText), keyText);
    check(`${tag} the key box is a password field and empty after saving`, (await page.locator('.xt-drawer input[aria-label="API key"]').inputValue()) === '');
    await page.locator('.xt-drawer .xt-btn', { hasText: 'Test connection' }).click();
    await page.waitForFunction(() => /Connected/.test(document.querySelector('.xt-drawer')?.textContent ?? ''), null, { timeout: 15000 });
    check(`${tag} test connection reaches the fake endpoint and reports the model`, jev.calls === 1 && /jev-1\.13\.0/.test(await page.locator('.xt-drawer').textContent()), `calls ${jev.calls}`);
    check(`${tag} the key goes in the Authorization header of the endpoint`, jev.auth[0] === `Bearer ${KEY}`);
    const stored = await page.evaluate(() => ({ s: Object.keys(sessionStorage), l: Object.keys(localStorage).filter((k) => /key/i.test(k)) }));
    check(`${tag} the key is in sessionStorage and not in localStorage by default`, stored.s.some((k) => /apiKey/.test(k)) && stored.l.length === 0, JSON.stringify(stored));
    const doc = await page.evaluate(() => JSON.stringify(window.__xray.exportParams?.collect?.() ?? window.__xrayParams?.collect?.() ?? {}));
    check(`${tag} the key is not in the exported params`, !doc.includes(KEY));
    const shareUrl = await page.evaluate(() => (window.__xrayParams?.shareUrl ?? window.__xray.exportParams?.shareUrl)?.() ?? '');
    check(`${tag} the key is not in the share link`, !shareUrl.includes(KEY) && !shareUrl.includes(btoa(KEY).replace(/=+$/, '')));

    // ---- estimate and classify all with the rules (no request)
    const est = await page.evaluate(() => window.__xrayClassify.estimate('all'));
    console.log(tag, 'estimate (rules on)', JSON.stringify(est));
    check(`${tag} the estimate: every element has a final rule, 0 requests`, est.byRules === 5000 && est.calls === 0);
    const callsBefore = jev.calls;
    const t0 = Date.now();
    await page.evaluate(() => window.__xrayClassify.classify('all'));
    const s1 = await page.evaluate(() => window.__xrayClassify.stats());
    console.log(tag, `classify all with rules: ${Date.now() - t0} ms`, JSON.stringify({ bySource: s1.bySource, calls: s1.calls, needsReview: s1.needsReview }));
    check(`${tag} classify all: 5000 results, all by rules, no request`, s1.total === 5000 && s1.bySource.rules === 5000 && jev.calls === callsBefore && s1.calls === 0);

    // ---- WHERE in the search bar and a quantity summary by discipline
    await typeInBar(page, "where discipline = 'MEC'");
    let st = await page.evaluate(() => window.__xraySearch.state());
    check(`${tag} the search bar counts where discipline = 'MEC' (870 ducts)`, st.rows[0]?.section === 'query' && st.rows[0].label === '870 elements match', st.rows[0]?.label);
    await page.keyboard.press('Escape');
    await page.evaluate(() => document.activeElement && document.activeElement.blur());
    const sum = await page.evaluate(() => { const x = window.__xraySearch.summarize('sum length by discipline'); return { total: x.total, groups: x.groups.map((g) => [g.key, Math.round(g.total)]) }; });
    console.log(tag, 'sum length by discipline', JSON.stringify(sum));
    check(`${tag} sum length by discipline groups by the written property`, sum.groups.length >= 4 && sum.groups.some(([k]) => k === 'MEC') && sum.groups.some(([k]) => k === 'STR'));
    const cnt = await page.evaluate(() => window.__xraySearch.summarize("count where discipline = 'PLB'").total);
    check(`${tag} count where discipline = 'PLB' gives 924 pipes`, cnt === 924, String(cnt));

    // ---- classify all with the rules off: requests against elements
    await ensureDrawer(page); // Escape in the search bar closed it
    await page.evaluate(() => window.__xrayClassify.clear());
    const est2 = await page.evaluate(() => window.__xrayClassify.estimate('all', { rules: false }));
    console.log(tag, 'estimate (rules off)', JSON.stringify(est2));
    const c0 = jev.calls;
    await page.evaluate(() => window.__xrayClassify.classify('all', { rules: false }));
    const s2 = await page.evaluate(() => window.__xrayClassify.stats());
    const made = jev.calls - c0;
    console.log(tag, 'rules off:', JSON.stringify({ elements: s2.total, calls: made, signatures: s2.signatures, bySource: s2.bySource, models: s2.models, usage: s2.usage }));
    check(`${tag} rules off: ${made} requests for ${s2.total} elements (cache answers the rest)`, s2.total === 5000 && made === s2.calls && made <= est2.calls && made > 0 && made < 60 && s2.bySource.model + s2.bySource.cache === 5000);
    check(`${tag} the endpoint saw only the pinned model id`, [...jev.models].join() === 'jev-1.13.0');
    check(`${tag} every result carries the model id of the answer`, await page.evaluate(() => window.__xrayClassify.results().every((r) => r.model === 'jev-1.13.0')));
    const again = jev.calls;
    await page.evaluate(() => window.__xrayClassify.classify('all', { rules: false }));
    check(`${tag} a second run is answered from the cache (0 requests)`, jev.calls === again);
    check(`${tag} no request went to any other host`, jev.foreign.length === 0, jev.foreign.join(' '));
    await page.evaluate(() => window.__xray.app.selectIds(window.__xray.app.controller.model.elements.slice(0, 40).map((e) => e.id)));
    await page.waitForTimeout(400);
    await shot(page, 'classify-drawer-settings.png');
    await page.locator('.xt-drawer .xt-table-wrap').scrollIntoViewIfNeeded();
    await page.evaluate(() => { const b = document.querySelector('.xt-body'); b.scrollTop = b.scrollHeight * 0.45; });
    await page.waitForTimeout(200);
    await shot(page, 'classify-drawer-results.png');

    // ---- colour by discipline
    const colours = await page.evaluate(() => {
      const m = window.__xray.app.controller.model;
      const col = window.__xray.app.renderer.state.color;
      const ids = ['IfcDuctSegment', 'IfcSlab'].map((c) => m.elements.find((e) => e.ifcClass === c).id);
      const read = () => ids.map((i) => [col[i * 3], col[i * 3 + 1], col[i * 3 + 2]].map((v) => Math.round(v * 100) / 100));
      const before = read();
      window.__xrayClassify.colourByDiscipline(true);
      const after = read();
      return { before, after };
    });
    check(`${tag} colour by discipline tints a duct blue (MEC) and a slab red (STR)`, colours.after[0][2] > colours.after[0][0] && colours.after[1][0] > colours.after[1][2] && JSON.stringify(colours.before) !== JSON.stringify(colours.after), JSON.stringify(colours));
    await page.evaluate(() => { window.__xray.app.selectIds([]); window.__xray.app.frameAll?.(); });
    await page.waitForTimeout(600);
    await shot(page, 'classify-colour-by-discipline.png');
    check(`${tag} the legend lists the disciplines`, (await page.locator('.xc-legend span').count()) >= 4);
    await page.evaluate(() => window.__xrayClassify.colourByDiscipline(false));

    // ---- manual override from the drawer
    const firstRow = page.locator('.xt-drawer tbody tr').first();
    const editedGid = await firstRow.getAttribute('data-gid');
    await firstRow.locator('.xc-edit').click();
    await page.waitForSelector('.xc-editor:not([hidden])');
    await page.locator('.xc-editor select').first().selectOption('CIV');
    await page.locator('.xc-editor .xt-btn', { hasText: 'Apply override' }).click();
    await page.waitForTimeout(300);
    const manual = await page.evaluate(() => {
      const r = window.__xrayClassify.results().filter((x) => x.source === 'manual');
      const m = window.__xray.app.controller.model;
      return { n: r.length, code: r[0]?.discipline.code, conf: r[0]?.discipline.confidence, prop: r[0] && m.elements[m.byGlobalId.get(r[0].id)].props['XR_Classification.Discipline'], gid: r[0]?.id };
    });
    check(`${tag} a manual override sets source manual, confidence 1 and the written property`, manual.n === 1 && manual.code === 'CIV' && manual.conf === 1 && manual.prop === 'CIV' && manual.gid === editedGid, JSON.stringify(manual));
    await page.evaluate(() => window.__xrayClassify.classify('all', { rules: false }));
    check(`${tag} a manual override survives a new run`, await page.evaluate((g) => window.__xrayClassify.results().find((r) => r.id === g)?.source === 'manual', manual.gid));
    await page.evaluate(() => window.__xrayClassify.clear());
    check(`${tag} a manual override survives Clear (it is kept per model)`, await page.evaluate(() => window.__xrayClassify.results().length === 1));
    const bad = await page.evaluate((g) => { try { window.__xrayClassify.override(g, { discipline: 'ZZZ' }); return 'no error'; } catch (e) { return e.message; } }, manual.gid);
    check(`${tag} an override with a code that is not in the schema is refused in plain words`, /not in the schema/.test(bad), bad);
    await page.evaluate(() => window.__xrayClassify.classify('all'));

    // ---- the needs-review set and the exact payload
    const nr = await page.evaluate(() => window.__xrayClassify.selectNeedsReview());
    console.log(tag, 'needs review', nr);
    const q = await page.evaluate(() => window.__xrayClassify.questions(window.__xray.app.controller.model.elements.find((e) => e.ifcClass === 'IfcDuctSegment').globalId));
    check(`${tag} questions() shows the exact Jev request`, q.main.model === 'jev-1.13.0' && Object.keys(q.main.questions).join() === 'discipline,building_element,masterformat' && q.main.state.class === 'IfcDuctSegment', JSON.stringify(Object.keys(q.main)));

    // ---- low confidence: needs review, the top-2 combined sub-discipline question, the set and the filter chips
    lowFor.add('IfcBeam');
    await ensureDrawer(page);
    await page.locator('.xt-drawer .xt-btn', { hasText: 'Clear cache' }).click();
    const c1 = jev.calls;
    await page.evaluate(() => window.__xrayClassify.classify('all', { rules: false }));
    const s3 = await page.evaluate(() => window.__xrayClassify.stats());
    const beams = await page.evaluate(() => window.__xray.app.controller.model.elements.filter((e) => e.ifcClass === 'IfcBeam').length);
    console.log(tag, 'low confidence for IfcBeam:', JSON.stringify({ calls: jev.calls - c1, needsReview: s3.needsReview, beams }));
    check(`${tag} a low-confidence answer marks its elements needsReview (all ${beams} beams)`, s3.needsReview === beams, `${s3.needsReview}`);
    const nrCount = await page.evaluate(() => window.__xrayClassify.selectNeedsReview());
    check(`${tag} Select needs review selects them`, nrCount === beams && (await page.evaluate(() => window.__xray.app.selection.length)) === beams);
    check(`${tag} the query engine sees XR_Classification.NeedsReview`, (await page.evaluate(() => window.__xraySearch.summarize('count where NeedsReview = TRUE').matched)) === beams);
    await page.locator('.xt-drawer .xt-chip', { hasText: 'Needs review' }).click();
    await page.waitForTimeout(300);
    const shown = await page.evaluate(() => [...document.querySelectorAll('.xt-drawer tbody tr')].every((tr) => tr.querySelector('.xc-review')));
    check(`${tag} the Needs review chip filters the table to amber rows`, shown && (await page.locator('.xt-drawer tbody tr').count()) === 200);
    await page.locator('.xt-drawer tbody tr').first().scrollIntoViewIfNeeded();
    await shot(page, 'classify-needs-review.png');
    await page.locator('.xt-drawer .xt-chip', { hasText: 'Needs review' }).click();
    lowFor.clear();
    await page.locator('.xt-drawer .xt-btn', { hasText: 'Clear cache' }).click();
    await page.evaluate(() => window.__xrayClassify.classify('all', { rules: false }));

    // ---- CSV export
    const dl = page.waitForEvent('download', { timeout: 15000 });
    await page.locator('.xt-drawer .xt-btn', { hasText: 'Export CSV' }).click();
    const d = await dl;
    const csv = readFileSync(await d.path(), 'utf8');
    const lines = csv.trim().split(/\r?\n/);
    console.log(tag, 'csv', d.suggestedFilename(), `${lines.length - 1} rows`, lines[0]);
    check(`${tag} the CSV has a header and one row per result`, lines[0].startsWith('GlobalId,Discipline') && lines.length === 5001 && d.suggestedFilename().endsWith('.csv'));
    const apiCsv = await page.evaluate(() => window.__xrayClassify.export('csv'));
    check(`${tag} export('csv') returns the same text`, apiCsv === csv);
    const json = JSON.parse(await page.evaluate(() => window.__xrayClassify.export('json')));
    check(`${tag} export('json') carries the results and the stats`, json.schema === 'xray-classification/1' && json.results.length === 5000 && json.stats.models);

    // ---- WebLLM without WebGPU
    await page.evaluate(() => window.__xrayClassify.configure({ provider: 'webllm' }));
    await page.waitForTimeout(800);
    const hasGpu = await page.evaluate(async () => !!navigator.gpu && !!(await navigator.gpu.requestAdapter().catch(() => null)));
    const drawerText = await page.locator('.xt-drawer').textContent();
    if (!hasGpu) {
      check(`${tag} WebLLM without WebGPU shows a plain message`, /WebGPU/.test(drawerText) && /cannot run/.test(drawerText) && /Jev provider|rules only/.test(drawerText), '');
      await page.locator('.xt-drawer .xt-btn', { hasText: 'Test connection' }).click();
      await page.waitForTimeout(500);
      check(`${tag} Test connection under WebLLM gives the same message, no crash`, /WebGPU/.test(await page.locator('.xt-drawer .xt-status.xc-err').first().textContent().catch(() => '')));
    } else {
      check(`${tag} WebGPU is present here, so the missing-GPU message is not shown`, !/not available/.test(drawerText));
    }
    check(`${tag} the drawer shows the model download size for WebLLM`, /download about \d+ MB/.test(drawerText));
    await shot(page, 'classify-webllm-no-webgpu.png');
    const cdn = jev.foreign.filter((u) => /jsdelivr/.test(u));
    check(`${tag} nothing was fetched from the CDN until a model run needs it`, cdn.length === 0, cdn.join(' '));
    await page.evaluate(() => window.__xrayClassify.configure({ provider: 'off' }));
  } finally {
    const real = errors.filter((e) => !/favicon/i.test(e));
    check(`${tag} zero console errors`, real.length === 0, real.slice(0, 3).join(' | '));
    await ctx.close();
  }
}

// ---------------------------------------------------------------- phone

async function runPhone(browser) {
  const tag = '[phone]';
  const { ctx, page, errors } = await open(browser, { viewport: { width: 390, height: 844 } });
  try {
    await page.locator('.xt-btn-tool[data-tool="classify"]').click();
    await page.waitForSelector('.xt-drawer:not(.hidden) .xt-table');
    await page.evaluate(() => window.__xrayClassify.classify('all'));
    await page.waitForTimeout(500);
    const box = await page.evaluate(() => {
      const d = document.querySelector('.xt-drawer').getBoundingClientRect();
      return { left: d.left, right: d.right, vw: window.innerWidth, scrollW: document.documentElement.scrollWidth };
    });
    check(`${tag} the drawer fits inside the phone width`, box.right <= box.vw + 1 && box.scrollW <= box.vw + 1, JSON.stringify(box));
    const btns = await page.evaluate(() => [...document.querySelectorAll('.xt-drawer .xt-btn')].every((b) => b.getBoundingClientRect().right <= window.innerWidth));
    check(`${tag} every button is inside the screen`, btns);
    await shot(page, 'classify-phone.png');
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
