// Headless check for sightlines.layerWeighting: select a duct riser that passes through several slabs, put the
// camera above the roof looking down the riser, and print the alpha of each slab hit by the riser's sightlines,
// top to bottom, for 'uniform', 'front' and 'budget'. Screenshots: bench/layers-<mode>.png.
// Usage: node bench/smoke-layers.mjs [model]      (default: synth5k)
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const model = process.argv[2] ?? 'synth5k';

const port = Number(process.env.SMOKE_PORT ?? 5198);

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
async function scenario(mode) {
  const app = window.__xray.app;
  const ctl = app.controller;
  const els = app.loaded.model.elements;
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const ext = (e) => e.bounds[4] - e.bounds[1];
  const risers = els.filter((e) => e.ifcClass === 'IfcDuctSegment' && /riser/i.test(e.name ?? ''));
  // No riser spans three storeys on its own (one per storey): take the largest and the others of the same column
  // (same plan position), i.e. the one riser as the model draws it through the building.
  const riser = [...risers].sort((a, b) => ext(b) - ext(a))[0];
  const col = risers.filter((e) => Math.abs(e.bounds[0] - riser.bounds[0]) < 0.01 && Math.abs(e.bounds[2] - riser.bounds[2]) < 0.01);
  // Keep Focus to exactly the selected segments: no ConnectedRun expansion through ports/systems.
  ctl.settings.classification.focusClasses = [];
  app.selectIds(col.map((e) => e.id));
  app.reclassify();
  const roofTop = Math.max(...els.map((e) => e.bounds[4]));
  const focus = [...ctl.classification.focus].map((id) => els[id]);
  const fx = (riser.bounds[0] + riser.bounds[3]) / 2;
  const fz = (riser.bounds[2] + riser.bounds[5]) / 2;
  const fy = focus.reduce((a, e) => a + (e.bounds[1] + e.bounds[4]) / 2, 0) / focus.length;
  const cam = app.renderer.camera;
  const controls = app.renderer.controls;
  controls.target.set(fx, fy, fz);
  cam.position.set(fx + 0.3, roofTop + 14, fz + 0.3);
  cam.near = 0.05;
  cam.updateProjectionMatrix();
  controls.update();
  ctl.settings.sightlines.layerWeighting = mode;
  app.runSightlinesNow();
  await sleep(1500);
  for (let i = 0; i < 40 && !ctl.converged; i++) await sleep(250); // swiftshader frames are slow; let the smoothing finish
  const c = ctl.classification;
  const inPlan = (e) => e.bounds[0] <= fx && fx <= e.bounds[3] && e.bounds[2] <= fz && fz <= e.bounds[5];
  const rows = [...c.host, ...c.near, ...c.far]
    .filter((id) => els[id].ifcClass === 'IfcSlab' && inPlan(els[id]))
    .map((id) => ({ id, name: els[id].name, cls: els[id].ifcClass, bucket: c.host.has(id) ? 'host' : c.near.has(id) ? 'near' : 'far',
      topY: +els[id].bounds[4].toFixed(2), occ: +ctl.result.occlusion.get(id).toFixed(3), target: +ctl.result.targetAlpha.get(id).toFixed(3), alpha: +ctl.state.alpha[id].toFixed(3) }))
    .sort((a, b) => b.topY - a.topY);
  return { mode, riser: { id: riser.id, name: riser.name, extent: ext(riser), column: col.length }, focusCount: focus.length,
    focusSpan: [Math.min(...focus.map((e) => e.bounds[1])), Math.max(...focus.map((e) => e.bounds[4]))], rows, converged: ctl.converged };
}

let browser;
let exitCode = 0;
try {
  await waitForServer();
  browser = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const page = await browser.newPage({ viewport: { width: 960, height: 600 } });
  const errors = [];
  page.on('console', (m) => { if (m.type() === 'error') errors.push(`[console.error] ${m.text()}`); });
  page.on('pageerror', (e) => errors.push(`[pageerror] ${e.message}`));
  const load = async () => {
    await page.goto(`http://127.0.0.1:${port}/?model=${model}`);
    await page.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: 120000 });
    const startupErr = await page.evaluate('window.__xrayError');
    if (startupErr) throw new Error(`startup error: ${startupErr}`);
  };
  await load();
  for (const mode of ['front', 'budget', 'uniform']) {
    let res;
    // Vite HMR reloads the page when another process edits a source file mid-run: reload and retry.
    for (let attempt = 0; ; attempt++) {
      try { res = await page.evaluate(scenario, mode); break; } catch (e) {
        if (attempt >= 3) throw e;
        console.log(`retry after page reload (${e.message.split('\n')[0]})`);
        await load();
      }
    }
    await page.waitForTimeout(500);
    const shot = resolve(here, `layers-${mode}.png`);
    await page.screenshot({ path: shot, timeout: 180000 });
    console.log(`mode ${res.mode}: riser ${res.riser.id} "${res.riser.name}" extent ${res.riser.extent} x ${res.riser.column} segments, focus ${res.focusCount} elements, y ${res.focusSpan.map((v) => v.toFixed(2)).join('..')}, converged ${res.converged}`);
    console.table(res.rows);
    console.log('screenshot:', shot);
  }
  console.log('console errors:', errors.length ? '\n' + errors.join('\n') : 'none');
  if (errors.length) exitCode = 1;
} catch (e) {
  console.error(e);
  exitCode = 1;
} finally {
  if (browser) await browser.close();
  vite.kill('SIGTERM');
}
process.exit(exitCode);
