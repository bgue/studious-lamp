// Frame cost of weighted blended OIT versus the sorted ghost pass, in headless Chromium with swiftshader.
//
//   node bench/bench-oit.mjs [model ...]        default: synth5k building
//
// Same page, selection and orbit as bench/bench.mjs (first IfcDuctSegment selected, camera orbited through 36
// azimuths, 1920x1080), once with OIT off and once with it on, plus a static "ghost heavy" scene (every slab and
// wall within reach forced to alpha 0.4). Writes bench/RESULTS-oit.md. It does not touch bench/RESULTS.md.
// Swiftshader rasterises on the CPU: the frame interval is not a GPU number; frame CPU is the JS time per frame.
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const models = process.argv.slice(2).filter((a) => !a.startsWith('--'));
if (models.length === 0) models.push('synth5k', 'building');
const port = Number(process.env.BENCH_PORT ?? 5189);
const POSITIONS = 36;
const VIEWPORT = { width: 1920, height: 1080 };

function loadPlaywright() {
  const candidates = [process.env.PLAYWRIGHT_MODULE, resolve(root, 'node_modules/playwright'), '/opt/node-tools/node_modules/playwright', '/opt/node22/lib/node_modules/playwright'].filter(Boolean);
  for (const c of candidates) { try { return createRequire(import.meta.url)(c); } catch { /* next */ } }
  throw new Error('playwright not found; set PLAYWRIGHT_MODULE');
}
const { chromium } = loadPlaywright();
const mean = (a) => (a.length ? a.reduce((x, y) => x + y, 0) / a.length : NaN);
const p95 = (a) => { if (!a.length) return NaN; const s = [...a].sort((x, y) => x - y); return s[Math.min(s.length - 1, Math.ceil(0.95 * s.length) - 1)]; };
const f = (x, d = 1) => (Number.isFinite(x) ? x.toFixed(d) : '-');

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

/** In page: orbit like bench.mjs (maxSamples 300), return frame intervals and CPU times. */
async function orbitInPage({ positions }) {
  const app = window.__xray.app;
  const ctl = app.controller;
  const cam = app.renderer.camera;
  const controls = app.renderer.controls;
  ctl.settings.sightlines.maxSamples = 300;
  app.runSightlinesNow();
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  for (let i = 0; i < 400 && !ctl.converged; i++) await sleep(25);
  const target = controls.target.clone();
  const offset = cam.position.clone().sub(target);
  const radius = offset.length();
  const elevation = Math.asin(offset.y / radius);
  const az0 = Math.atan2(offset.x, offset.z);
  app.frameLog.intervals.length = 0;
  app.frameLog.cpu.length = 0;
  for (let i = 0; i < positions; i++) {
    const az = az0 + (i / positions) * Math.PI * 2;
    cam.position.set(target.x + radius * Math.cos(elevation) * Math.sin(az), target.y + radius * Math.sin(elevation), target.z + radius * Math.cos(elevation) * Math.cos(az));
    const before = ctl.stats.sightlinesCount;
    controls.update();
    for (let t = 0; t < 120 && ctl.stats.sightlinesCount === before; t++) await sleep(25);
    await sleep(150);
  }
  await sleep(300);
  return { intervals: app.frameLog.intervals.slice(), cpu: app.frameLog.cpu.slice() };
}

function framePage(id) {
  const app = window.__xray.app;
  const b = app.loaded.model.elements[id].bounds;
  const c = [(b[0] + b[3]) / 2, (b[1] + b[4]) / 2, (b[2] + b[5]) / 2];
  const cam = app.renderer.camera;
  const dist = app.modelName === 'synth5k' ? 16 : 11;
  const lift = app.modelName === 'synth5k' ? 0.6 : 0.3;
  app.renderer.controls.target.set(c[0], c[1], c[2]);
  cam.position.set(c[0] + dist * 0.55, c[1] + dist * lift, c[2] + dist * 0.6);
  cam.near = 0.05;
  cam.updateProjectionMatrix();
  app.renderer.controls.update();
}

/** In page: static ghost-heavy scene: alpha 0.4 on every slab and wall, camera fixed, then 12 s of frames. */
async function heavyInPage() {
  const app = window.__xray.app;
  const r = app.renderer;
  const sleep = (ms) => new Promise((x) => setTimeout(x, ms));
  for (let i = 0; i < 400 && !app.controller.converged; i++) await sleep(25);
  await sleep(300);
  let n = 0;
  app.loaded.model.elements.forEach((e, id) => { if (e.ifcClass === 'IfcSlab' || e.ifcClass === 'IfcWall' || e.ifcClass === 'IfcWallStandardCase') { if (r.state.alpha[id] > 0.4) { r.state.alpha[id] = 0.4; n++; } } });
  r.markDirty();
  await sleep(6000); // shader compile and warm-up
  app.frameLog.intervals.length = 0;
  app.frameLog.cpu.length = 0;
  await sleep(10000);
  return { intervals: app.frameLog.intervals.slice(), cpu: app.frameLog.cpu.slice(), ghosts: n };
}

const rows = [];
let browser;
let exitCode = 0;
let webgl = 'unknown';
try {
  await waitForServer();
  browser = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const version = browser.version();
  for (const model of models) {
    for (const mode of ['off', 'on', 'on-msaa4']) {
      const page = await browser.newPage({ viewport: VIEWPORT });
      const errors = [];
      page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
      page.on('pageerror', (e) => errors.push(e.message));
      await page.goto(`http://127.0.0.1:${port}/?model=${model}&oit=${mode === 'off' ? 'off' : 'on'}`);
      await page.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: 180000 });
      if (await page.evaluate('window.__xrayError')) throw new Error(await page.evaluate('window.__xrayError'));
      const info = await page.evaluate((mode) => {
        const app = window.__xray.app;
        const duct = app.loaded.model.elements.find((e) => e.ifcClass === 'IfcDuctSegment');
        const gl = app.renderer.renderer.getContext();
        const ext = gl.getExtension('WEBGL_debug_renderer_info');
        return { ductId: duct.id, oit: app.renderer.oitEnabled, want: mode, count: app.loaded.model.elements.length, gl: ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : 'unknown' };
      }, mode);
      webgl = info.gl;
      if (info.oit !== (mode !== 'off')) throw new Error(`OIT state ${info.oit} != ${mode}`);
      if (mode === 'on-msaa4') await page.evaluate(() => window.__xray.renderer.setOitSamples(4));
      await page.evaluate((id) => window.__xray.app.selectIds([id]), info.ductId);
      await page.evaluate(framePage, info.ductId);
      // warm-up: compile the programs for this state before timing
      await page.evaluate(() => new Promise((r) => setTimeout(r, 5000)));
      const orbit = await page.evaluate(orbitInPage, { positions: POSITIONS });
      const heavy = await page.evaluate(heavyInPage);
      rows.push({ model, mode, orbit, heavy, count: info.count });
      console.log(`${model} OIT ${mode}: orbit ${orbit.intervals.length} frames, interval ${f(mean(orbit.intervals))} ms, cpu ${f(mean(orbit.cpu), 2)} ms; heavy (${heavy.ghosts} ghosts) interval ${f(mean(heavy.intervals))} ms, cpu ${f(mean(heavy.cpu), 2)} ms; errors ${errors.length}`);
      if (errors.length) { console.log(errors.join('\n')); exitCode = 1; }
      await page.close();
    }
  }
  const table = rows.map((r) => `| ${r.model} | ${r.count} | ${r.mode} | orbit (36 azimuths, duct selected) | ${r.orbit.intervals.length} | ${f(mean(r.orbit.intervals))} / ${f(p95(r.orbit.intervals))} | ${f(mean(r.orbit.cpu), 2)} / ${f(p95(r.orbit.cpu), 2)} |\n| ${r.model} | ${r.count} | ${r.mode} | ghost heavy (${r.heavy.ghosts} slabs/walls at alpha 0.4, static) | ${r.heavy.intervals.length} | ${f(mean(r.heavy.intervals))} / ${f(p95(r.heavy.intervals))} | ${f(mean(r.heavy.cpu), 2)} / ${f(p95(r.heavy.cpu), 2)} |`).join('\n');
  const md = `# OIT benchmark

Generated by \`node bench/bench-oit.mjs\` on ${new Date().toISOString().slice(0, 10)}. Does not replace \`bench/RESULTS.md\`.

**Swiftshader numbers are CPU rasterisation, not GPU numbers** (${webgl}, Chromium ${version}, viewport ${VIEWPORT.width}x${VIEWPORT.height}). The frame interval
is dominated by software rasterisation and by whatever else the machine was running (other agents were using the CPU), so only
the on/off ratio is meaningful, and only roughly. Frame CPU is the JS time of the frame (smoothing, uploads and the draw calls; it excludes
the rasteriser's asynchronous work).

- OIT off: the sorted ghost pass (premultiplied normal blending in triangle order). OIT on: weighted blended OIT (default: no MSAA on the OIT target),
  \`paper\` depth weight. on-msaa4: the same with 4x MSAA on the OIT target (renderer.setOitSamples(4)). Same page, camera, selection and orbit as \`bench/bench.mjs\` (maxSamples 300), one fresh page per row, 5 s warm-up before timing.
- "ghost heavy": every slab and wall forced to alpha 0.4, camera fixed, 10 s of frames after a 6 s warm-up.

| model | elements | OIT | scenario | frames | frame interval ms (mean / p95) | frame CPU ms (mean / p95) |
| --- | --- | --- | --- | --- | --- | --- |
${table}
`;
  writeFileSync(resolve(here, 'RESULTS-oit.md'), md);
  console.log('wrote', resolve(here, 'RESULTS-oit.md'));
} catch (e) {
  console.error(e);
  console.error(viteLog.slice(-1500));
  exitCode = 1;
} finally {
  if (browser) await browser.close();
  vite.kill('SIGTERM');
}
process.exit(exitCode);
