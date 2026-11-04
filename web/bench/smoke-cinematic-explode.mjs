// Exploded-view screenshots.
//   node bench/smoke-cinematic-explode.mjs
// bench/explode-storeys.png : synth5k, every element of storeys 0..2 selected, mode "storeys" (3 m gap)
// bench/explode-radial.png  : fzk-haus, whole model selected, mode "radial", factor 0.6
// Prints how many elements move and the largest offsets; exits non-zero on console errors.
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const port = Number(process.env.SMOKE_PORT ?? 5196);

function loadPlaywright() {
  const candidates = [process.env.PLAYWRIGHT_MODULE, resolve(root, 'node_modules/playwright'), '/opt/node-tools/node_modules/playwright', '/opt/node22/lib/node_modules/playwright'].filter(Boolean);
  for (const c of candidates) { try { return createRequire(import.meta.url)(c); } catch { /* next */ } }
  throw new Error('playwright not found; set PLAYWRIGHT_MODULE');
}
const { chromium } = loadPlaywright();
const vite = spawn(resolve(root, 'node_modules/.bin/vite'), ['--config', resolve(here, 'vite.smoke.config.mjs'), '--host', '127.0.0.1', '--port', String(port), '--strictPort'], { cwd: root, stdio: ['ignore', 'pipe', 'pipe'] });
let viteLog = '';
vite.stdout.on('data', (d) => (viteLog += d));
vite.stderr.on('data', (d) => (viteLog += d));
async function waitForServer() {
  for (let i = 0; i < 150; i++) {
    try { const r = await fetch(`http://127.0.0.1:${port}/`); if (r.ok) return; } catch { /* retry */ }
    await new Promise((r) => setTimeout(r, 200));
  }
  throw new Error('vite did not start:\n' + viteLog);
}

let browser;
let exitCode = 0;
try {
  await waitForServer();
  browser = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const errors = [];
  async function open(model) {
    const page = await (await browser.newContext({ viewport: { width: 1280, height: 800 } })).newPage();
    page.on('console', (m) => { if (m.type() === 'error') errors.push(`[${m.type()}] ${m.text()}`); });
    page.on('pageerror', (e) => errors.push(`[pageerror] ${e.message}`));
    await page.goto(`http://127.0.0.1:${port}/?model=${model}`);
    await page.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: 120000 });
    const err = await page.evaluate('window.__xrayError');
    if (err) throw new Error(err);
    return page;
  }
  // Selects `pick(elements)`, frames the whole model from a raised 3/4 view, explodes and waits for the animation.
  async function run(page, name, cfg, pickSrc) {
    const res = await page.evaluate(async ({ cfg, pickSrc }) => {
      const app = window.__xray.app;
      const cin = window.__cinematic;
      const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
      const pick = new Function('els', `return (${pickSrc})(els);`);
      cin.cfg.flyTo = false;
      cin.cfg.reveal = false;
      cin.cfg.sweep.enabled = false;
      Object.assign(cin.cfg.explode, cfg, { durationMs: 200 });
      const ids = pick(app.controller.model.elements);
      app.selectIds(ids);
      for (let i = 0; i < 400 && !app.controller.converged; i++) await sleep(25);
      const n = cin.explode();
      for (let i = 0; i < 400 && cin.explodeAnim.value !== 1; i++) await sleep(25);
      const table = cin.explodeTable;
      return { selected: ids.length, moved: n, anim: cin.explodeAnim.value, exploded: cin.exploded, table: table ? table.ids.length : 0, centre: table ? table.centre.toArray() : null };
    }, { cfg, pickSrc });
    console.log(name, JSON.stringify(res));
  }

  // ---- synth5k: storeys 0..2, storeys mode
  let page = await open('synth5k');
  await run(page, 'storeys', { source: 'auto', mode: 'storeys', storeyGap: 3, factor: 1 }, '(els) => els.filter((e) => e.storey !== null && e.storey <= 2).map((e) => e.id)');
  await page.evaluate(() => {
    const r = window.__xray.app.renderer;
    r.frameAll();
    const t = r.controls.target, c = r.camera.position;
    // Side-on 3/4 view, a little further out so the separated floors fit.
    const d = c.clone().sub(t); d.y *= 0.45; t.copy(window.__cinematic.explodeTable.centre); c.copy(t).addScaledVector(d, 1.8);
    r.controls.update(); r.markDirty();
  });
  await page.waitForTimeout(600);
  await page.screenshot({ path: resolve(here, 'explode-storeys.png') });
  if (process.env.COLLAPSED) {
    await page.evaluate(async () => { window.__cinematic.collapse(); for (let i = 0; i < 400 && window.__cinematic.explodeAnim.value !== 0; i++) await new Promise((r) => setTimeout(r, 25)); });
    await page.waitForTimeout(400);
    await page.screenshot({ path: resolve(process.env.COLLAPSED) });
  }
  await page.context().close();

  // ---- fzk-haus: everything selected, radial 0.6
  page = await open('fzk-haus');
  await run(page, 'radial', { source: 'auto', mode: 'radial', factor: 0.6, minPush: 0 }, '(els) => els.map((e) => e.id)');
  console.log('cam', await page.evaluate(() => {
    const r = window.__xray.app.renderer;
    r.frameAll();
    const t = r.controls.target, c = r.camera.position;
    const d = c.clone().sub(t); c.copy(t).addScaledVector(d, 1.5);
    r.controls.update(); r.markDirty();
    return (JSON.stringify({ p: c.toArray(), t: t.toArray(), b: window.__xray.app.loaded.geometry.totalBounds().max.toArray(), near: r.camera.near, far: r.camera.far }));
  }));
  await page.waitForTimeout(600);
  await page.screenshot({ path: resolve(here, 'explode-radial.png') });
  await page.context().close();

  if (errors.length) { console.log('console errors:\n' + errors.join('\n')); exitCode = 1; }
} catch (e) {
  console.error(e);
  exitCode = 1;
} finally {
  await browser?.close();
  vite.kill();
  process.exit(exitCode);
}
