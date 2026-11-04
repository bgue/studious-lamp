// Ghost legibility screenshots: every ghost (Host + Near) is forced to one alpha and the frame is saved.
//   node bench/smoke-cinematic-ghost.mjs <prefix> [model]     e.g. ghost-before / ghost-after
// Writes bench/<prefix>-1.0.png, -0.99.png, -0.5.png, -0.15.png (plus <prefix>.png = the 0.15 frame).
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const port = Number(process.env.SMOKE_PORT ?? 5197);
const prefix = process.argv[2] ?? 'ghost-after';
const model = process.argv[3] ?? 'building';
// GHOST_ALL=1: stress test, every non-focus element is ghosted (not only Host + Near) and the camera pulls back.
const all = process.env.GHOST_ALL === '1';

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
  const page = await (await browser.newContext({ viewport: { width: 1280, height: 800 } })).newPage();
  const errors = [];
  page.on('console', (m) => { if (m.type() === 'error' || m.type() === 'warning') errors.push(`[${m.type()}] ${m.text()}`); });
  page.on('pageerror', (e) => errors.push(`[pageerror] ${e.message}`));
  await page.goto(`http://127.0.0.1:${port}/?model=${model}`);
  await page.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: 120000 });
  const err = await page.evaluate('window.__xrayError');
  if (err) throw new Error(err);

  await page.evaluate((v) => { window.__all = v; }, all);
  const info = await page.evaluate(async () => {
    const app = window.__xray.app;
    const cin = window.__cinematic;
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
    cin.cfg.flyTo = false;
    const duct = app.loaded.model.elements.find((e) => e.ifcClass === 'IfcDuctSegment');
    app.selectIds([duct.id]);
    cin.flyToElements([duct.id], { durationMs: 1 });
    await sleep(300);
    for (let i = 0; i < 300 && (cin.planeSweep.running || cin.stagger.size > 0 || !app.controller.converged); i++) await sleep(25);
    // Fixed camera: the default whole-model framing, a little closer, looking at the duct.
    app.renderer.frameAll();
    const cam = app.renderer.camera, tgt = app.renderer.controls.target;
    const dir = cam.position.clone().sub(tgt);
    tgt.fromArray(app.loaded.model.elements[duct.id].bounds.slice(0, 3).map((v, i) => (v + app.loaded.model.elements[duct.id].bounds[i + 3]) / 2));
    cam.position.copy(tgt).addScaledVector(dir, window.__all ? 1.0 : 0.55);
    app.renderer.controls.update();
    const cls = app.controller.classification;
    return { duct: duct.id, host: cls.host.size, near: cls.near.size, cam: cam.position.toArray(), tgt: tgt.toArray() };
  });
  console.log('setup', JSON.stringify(info));

  for (const a of [1.0, 0.99, 0.5, 0.15]) {
    const stats = await page.evaluate(async (alpha) => {
      const app = window.__xray.app;
      const r = app.renderer;
      const cls = app.controller.classification;
      // Freeze the controller's smoothing so the forced alphas stay.
      app.controller.tick = () => false;
      const ids = window.__all ? app.loaded.model.elements.map((e) => e.id).filter((id) => !cls.focus.has(id)) : [...cls.host, ...cls.near];
      for (const id of ids) r.state.alpha[id] = alpha;
      r.markDirty();
      await new Promise((res) => setTimeout(res, 400));
      for (const id of ids) r.state.alpha[id] = alpha;
      r.markDirty();
      await new Promise((res) => setTimeout(res, 400));
      return { ghosts: ids.length, min: Math.min(...ids.map((i) => r.state.alpha[i])), max: Math.max(...ids.map((i) => r.state.alpha[i])) };
    }, a);
    console.log(a, JSON.stringify(stats));
    await page.locator('#c').screenshot({ path: resolve(here, `${prefix}-${a === 1 ? "1.0" : String(a)}.png`) });
    if (a === 0.15) await page.locator('#c').screenshot({ path: resolve(here, `${prefix}.png`) });
  }
  if (errors.length) { console.log('console problems:\n' + errors.join('\n')); }
} catch (e) {
  console.error(e);
  exitCode = 1;
} finally {
  await browser?.close();
  vite.kill();
  process.exit(exitCode);
}
