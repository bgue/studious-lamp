// Headless screenshots of the cinematic plugin on the building model.
//   node bench/smoke-cinematic.mjs
// Writes bench/smoke-cinematic-building.png (defaults on, duct selected) and
// bench/smoke-cinematic-bloom.png (selective bloom on). Also prints a few checks.
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
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

const vite = spawn(resolve(root, 'node_modules/.bin/vite'), ['--config', resolve(here, 'vite.smoke.config.mjs'), '--host', '127.0.0.1', '--port', String(port), '--strictPort'], {
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

let browser;
let exitCode = 0;
try {
  await waitForServer();
  browser = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  const errors = [];
  page.on('console', (m) => { if (m.type() === 'error' || m.type() === 'warning') errors.push(`[${m.type()}] ${m.text()}`); });
  page.on('pageerror', (e) => errors.push(`[pageerror] ${e.message}`));
  await page.goto(`http://127.0.0.1:${port}/?model=building`);
  await page.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: 120000 });
  const err = await page.evaluate('window.__xrayError');
  if (err) throw new Error(err);

  const info = await page.evaluate(async () => {
    const app = window.__xray.app;
    const cin = window.__cinematic;
    const duct = app.loaded.model.elements.find((e) => e.ifcClass === 'IfcDuctSegment');
    const before = app.renderer.camera.position.toArray();
    app.selectIds([duct.id]);
    const flewImmediately = cin.flying;
    // wait for the flight and the reveal to finish
    for (let i = 0; i < 400 && (cin.flying || cin.stagger.size > 0 || !app.controller.converged); i++) await new Promise((r) => setTimeout(r, 25));
    await new Promise((r) => setTimeout(r, 300));
    return {
      ductId: duct.id,
      flewImmediately,
      cameraBefore: before.map((x) => +x.toFixed(2)),
      cameraAfter: app.renderer.camera.position.toArray().map((x) => +x.toFixed(2)),
      target: app.renderer.controls.target.toArray().map((x) => +x.toFixed(2)),
      buckets: { ...app.controller.stats.buckets },
      alphas: [...app.controller.classification.near].map((id) => +app.renderer.state.alpha[id].toFixed(2)),
      dressing: cin.dressing.enabled,
    };
  });
  console.log('state:', JSON.stringify(info));
  await page.screenshot({ path: resolve(here, 'smoke-cinematic-building.png') });

  const t = Date.now();
  await page.evaluate(async () => {
    const cin = window.__cinematic;
    cin.cfg.bloom = true;
    cin.bloom.enable();
    for (let i = 0; i < 6; i++) await new Promise((r) => requestAnimationFrame(r));
  });
  await page.waitForTimeout(500);
  await page.screenshot({ path: resolve(here, 'smoke-cinematic-bloom.png') });
  // Overview (frame all, selection kept): sky gradient, ground shadow and fog are visible.
  await page.evaluate(async () => {
    const cin = window.__cinematic;
    cin.cfg.bloom = false;
    cin.bloom.disable();
    window.__xray.app.frameAll();
    await new Promise((r) => setTimeout(r, 400));
  });
  await page.screenshot({ path: resolve(here, 'smoke-cinematic-overview.png') });
  // Exercise the rest: edge glow, turntable, dolly, tour. Nothing should throw.
  const extras = await page.evaluate(async () => {
    const app = window.__xray.app;
    const cin = window.__cinematic;
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
    const out = {};
    cin.cfg.edgeGlow = true;
    cin.applyGlow();
    await sleep(300);
    out.glowRequested = true;
    cin.cfg.edgeGlow = false;
    cin.applyGlow();
    // turntable: needs 3 s idle after the last input; fake the idle time instead of waiting
    cin.cfg.autoOrbit = true;
    cin.cfg.orbitSpeed = 30;
    cin.userInput();
    cin.lastInput = -Infinity;
    const p0 = app.renderer.camera.position.clone();
    await sleep(600);
    out.orbitMoved = +app.renderer.camera.position.distanceTo(p0).toFixed(3);
    cin.cfg.autoOrbit = false;
    // dolly: the building has a single duct, so it should refuse politely; the synthetic run test is in unit tests
    cin.playDolly();
    out.dollyPlaying = cin.cfg.dollyPlaying;
    // tour over storeys (no stored sets)
    out.tourStarted = cin.startTour();
    await sleep(1200);
    out.tourIndex = cin.tour.index;
    out.tourSelection = app.selection.length;
    cin.stopTour();
    out.tourRunning = cin.tour.running;
    return out;
  });
  console.log('extras:', JSON.stringify(extras));
  console.log('bloom screenshot ms', Date.now() - t);
  console.log('console errors/warnings:', errors.length ? '\n' + errors.join('\n') : 'none');
  if (errors.some((e) => !e.startsWith('[warning]'))) exitCode = 1;
} catch (e) {
  console.error(e);
  exitCode = 1;
} finally {
  if (browser) await browser.close();
  vite.kill('SIGTERM');
}
process.exit(exitCode);
