// Headless check for occluderScope 'all': select the duct, put the camera outside an exterior wall that lies
// between camera and duct, and assert that a Far element ghosts. Screenshot: bench/smoke-scope-all.png.
// Usage: node bench/smoke-scope.mjs [model]      (default: building)
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const model = process.argv[2] ?? 'building';
const out = resolve(here, 'smoke-scope-all.png');
const port = Number(process.env.SMOKE_PORT ?? 5197);

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

const vite = spawn(resolve(root, 'node_modules/.bin/vite'), ['--host', '127.0.0.1', '--port', String(port), '--strictPort'], {
  cwd: root, stdio: ['ignore', 'pipe', 'pipe'],
});
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

/** Runs in the page. */
async function scenario() {
  const app = window.__xray.app;
  const ctl = app.controller;
  const els = app.loaded.model.elements;
  const duct = els.find((e) => e.ifcClass === 'IfcDuctSegment');
  app.selectIds([duct.id]);
  const mid = (e) => [(e.bounds[0] + e.bounds[3]) / 2, (e.bounds[1] + e.bounds[4]) / 2, (e.bounds[2] + e.bounds[5]) / 2];
  const c = mid(duct);
  const far = [...ctl.classification.far].map((id) => els[id]).filter((e) => e.ifcClass.includes('Wall'));
  // Exterior wall = Far wall with the largest horizontal distance (ground plane x/z) from the duct that is >= 2 m away;
  // try each Far wall and keep the first one that actually ghosts at its outside.
  const cands = far
    .map((e) => ({ e, d: Math.hypot(mid(e)[0] - c[0], mid(e)[2] - c[2]) }))
    .sort((a, b) => b.d - a.d);
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const cam = app.renderer.camera;
  const controls = app.renderer.controls;
  const tried = [];
  for (const { e, d } of cands) {
    const w = mid(e);
    const dx = w[0] - c[0], dz = w[2] - c[2];
    const len = Math.hypot(dx, dz) || 1;
    // 6 m beyond the wall centre along duct -> wall, at the duct height plus 0.5 m
    const p = [w[0] + (dx / len) * 6, c[1] + 0.5, w[2] + (dz / len) * 6];
    controls.target.set(c[0], c[1], c[2]);
    cam.position.set(p[0], p[1], p[2]);
    cam.near = 0.05;
    cam.updateProjectionMatrix();
    controls.update();
    app.runSightlinesNow();
    await sleep(1000);
    const a = ctl.state.alpha[e.id];
    tried.push({ id: e.id, name: e.name, distance: +d.toFixed(2), alpha: +a.toFixed(3), occlusion: +(ctl.result.occlusion.get(e.id) ?? 0).toFixed(3) });
    if (a < 0.9) break;
  }
  const farAlphas = [...ctl.classification.far].map((id) => ({ id, cls: els[id].ifcClass, alpha: ctl.state.alpha[id] }));
  const ghostedFar = farAlphas.filter((f) => f.alpha < 0.9);
  return {
    ductId: duct.id,
    scope: ctl.settings.sightlines.occluderScope,
    buckets: { ...ctl.stats.buckets },
    tried,
    ghostedFar,
    minFarAlpha: Math.min(...farAlphas.map((f) => f.alpha)),
    converged: ctl.converged,
  };
}

let browser;
let exitCode = 0;
try {
  await waitForServer();
  browser = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  const errors = [];
  page.on('console', (m) => { if (m.type() === 'error') errors.push(`[console.error] ${m.text()}`); });
  page.on('pageerror', (e) => errors.push(`[pageerror] ${e.message}`));
  await page.goto(`http://127.0.0.1:${port}/?model=${model}`);
  await page.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: 120000 });
  const startupErr = await page.evaluate('window.__xrayError');
  if (startupErr) throw new Error(`startup error: ${startupErr}`);
  const res = await page.evaluate(scenario);
  await page.waitForTimeout(500);
  await page.screenshot({ path: out });
  console.log(JSON.stringify(res, null, 2));
  console.log('screenshot:', out);
  console.log('console errors:', errors.length ? '\n' + errors.join('\n') : 'none');
  if (res.scope !== 'all') { console.error('FAIL: default occluderScope is not all'); exitCode = 1; }
  if (res.ghostedFar.length === 0) { console.error('FAIL: no Far element has alpha below 0.9'); exitCode = 1; }
  else console.log(`PASS: ${res.ghostedFar.length} Far element(s) with alpha < 0.9 (min ${res.minFarAlpha.toFixed(3)})`);
  if (errors.length) exitCode = 1;
} catch (e) {
  console.error(e);
  exitCode = 1;
} finally {
  if (browser) await browser.close();
  vite.kill('SIGTERM');
}
process.exit(exitCode);
