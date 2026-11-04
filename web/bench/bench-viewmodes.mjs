// Frame cost of the view modes on synth5k (swiftshader: CPU rasterisation, so only ratios mean something).
//   BENCH_PORT=5321 node bench/bench-viewmodes.mjs
// A duct riser is selected; per scenario the frame interval and the JS time of the frame are recorded over a still
// camera and, for the peel, over an orbiting camera (the mask and the flood are rebuilt every frame then).
// Writes bench/RESULTS-viewmodes.md (it does not touch bench/RESULTS.md).
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const port = Number(process.env.BENCH_PORT ?? 5321);
const VIEWPORT = { width: Number(process.env.BENCH_W ?? 1280), height: Number(process.env.BENCH_H ?? 720) };
const SECONDS = Number(process.env.BENCH_SECONDS ?? 8);

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

const mean = (a) => (a.length ? a.reduce((x, y) => x + y, 0) / a.length : NaN);
const p95 = (a) => { if (!a.length) return NaN; const s = [...a].sort((x, y) => x - y); return s[Math.min(s.length - 1, Math.ceil(0.95 * s.length) - 1)]; };
const f = (x, d = 1) => (Number.isFinite(x) ? x.toFixed(d) : '-');

const SCENARIOS = [
  ['off', {}, false],
  ['behind cut', { behind: { enabled: true, frontTreatment: 'cut' } }, false],
  ['behind cut + cap', { behind: { enabled: true, frontTreatment: 'cut + cap' } }, false],
  ['behind ghost', { behind: { enabled: true, frontTreatment: 'ghost' } }, false],
  ['peel (still camera)', { peel: { enabled: true, animate: false } }, false],
  ['peel (orbiting camera)', { peel: { enabled: true, animate: false } }, true],
  ['peel (CPU ellipses, orbiting)', { peel: { enabled: true, animate: false }, cpu: true }, true],
  ['off (again)', {}, false],
];

let browser;
let exitCode = 0;
try {
  await waitForServer();
  browser = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const version = browser.version();
  const page = await browser.newPage({ viewport: VIEWPORT });
  const errors = [];
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', (e) => errors.push(e.message));
  await page.goto(`http://127.0.0.1:${port}/?model=synth5k&cinematic=off`);
  await page.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: 180000 });
  const err = await page.evaluate('window.__xrayError');
  if (err) throw new Error(err);
  await page.addStyleTag({ content: '#xray-overlay { display: none !important }' });
  const rows = [];
  await page.evaluate(async () => {
    const app = window.__xray.app;
    const els = app.loaded.model.elements;
    const ducts = els.filter((e) => e.ifcClass === 'IfcDuctSegment');
    const ext = (e) => e.bounds[4] - e.bounds[1];
    const best = ducts.reduce((a, b) => (ext(b) > ext(a) ? b : a));
    const chain = ducts.filter((e) => Math.abs(e.bounds[0] - best.bounds[0]) < 0.01 && Math.abs(e.bounds[2] - best.bounds[2]) < 0.01);
    app.selectIds(chain.map((e) => e.id));
    const b = chain.map((e) => e.bounds);
    const c = [0, 1, 2].map((a) => (Math.min(...b.map((x) => x[a])) + Math.max(...b.map((x) => x[a + 3]))) / 2);
    const r = app.renderer;
    r.controls.target.set(...c);
    r.camera.position.set(c[0] + 13, c[1] + 9, c[2] + 16);
    r.camera.near = 0.1;
    r.camera.updateProjectionMatrix();
    r.controls.update();
    app.runSightlinesNow();
    for (let i = 0; i < 400 && !app.controller.converged; i++) await new Promise((x) => setTimeout(x, 25));
    window.__bench = { c };
  });
  for (const [name, cfg, orbit] of SCENARIOS) {
    const res = await page.evaluate(async ([cfg, orbit, seconds]) => {
      const app = window.__xray.app;
      const r = app.renderer;
      const vm = window.__xrayViewModes;
      const sleep = (ms) => new Promise((x) => setTimeout(x, ms));
      vm.setBehind({ enabled: false });
      vm.setPeel({ enabled: false });
      r.setPeelPath(cfg.cpu ? 'cpu' : 'auto');
      if (cfg.behind) vm.setBehind(cfg.behind);
      if (cfg.peel) vm.setPeel(cfg.peel);
      await sleep(2500);
      const target = r.controls.target.clone();
      const off = r.camera.position.clone().sub(target);
      const radius = off.length();
      const el = Math.asin(off.y / radius);
      const az0 = Math.atan2(off.x, off.z);
      app.frameLog.intervals.length = 0;
      app.frameLog.cpu.length = 0;
      const rebuilds0 = r.peelRefreshes;
      const t0 = performance.now();
      let k = 0;
      while (performance.now() - t0 < seconds * 1000) {
        if (orbit) {
          const az = az0 + (k++) * 0.012;
          r.camera.position.set(target.x + radius * Math.cos(el) * Math.sin(az), target.y + radius * Math.sin(el), target.z + radius * Math.cos(el) * Math.cos(az));
          r.controls.update();
        }
        await new Promise((x) => requestAnimationFrame(x));
      }
      const out = { intervals: app.frameLog.intervals.slice(), cpu: app.frameLog.cpu.slice(), rebuilds: r.peelRefreshes - rebuilds0, path: r.peelPath };
      r.camera.position.copy(target).add(off);
      r.controls.update();
      return out;
    }, [cfg, orbit, SECONDS]);
    rows.push({ name, ...res });
    console.log(name.padEnd(32), `frames ${res.intervals.length}`, `interval ${f(mean(res.intervals))} / ${f(p95(res.intervals))} ms`, `cpu ${f(mean(res.cpu), 2)} / ${f(p95(res.cpu), 2)} ms`, `mask rebuilds ${res.rebuilds}`, res.path);
  }
  const info = await page.evaluate(() => ({ elements: window.__xray.app.loaded.model.elements.length, oit: window.__xray.renderer.oitStatus, peel: window.__xrayViewModes.status() }));
  const md = `# View modes benchmark

Generated by \`node bench/bench-viewmodes.mjs\`. Does not replace \`bench/RESULTS.md\`.

**Swiftshader numbers are CPU rasterisation, not GPU numbers** (Chromium ${version}, viewport ${VIEWPORT.width}x${VIEWPORT.height}, synth5k with ${info.elements} elements, a duct riser selected, ${SECONDS} s per row after 2.5 s warm-up).
The frame interval is dominated by software rasterisation and by whatever else the machine runs (other agents were using the CPU), so compare rows of
the same run, and read small differences as noise. Frame CPU is the JS time of the frame (it excludes the rasteriser's asynchronous work).
Peel mask rebuilds: how often the focus mask and the 10 flood passes ran (they are skipped while camera and state are unchanged).

| scenario | frames | frame interval ms (mean / p95) | frame CPU ms (mean / p95) | peel mask rebuilds | peel path |
| --- | --- | --- | --- | --- | --- |
${rows.map((r) => `| ${r.name} | ${r.intervals.length} | ${f(mean(r.intervals))} / ${f(p95(r.intervals))} | ${f(mean(r.cpu), 2)} / ${f(p95(r.cpu), 2)} | ${r.rebuilds} | ${r.path} |`).join('\n')}
`;
  writeFileSync(resolve(here, 'RESULTS-viewmodes.md'), md);
  console.log('wrote bench/RESULTS-viewmodes.md', errors.length ? `errors: ${errors.join(' | ')}` : 'no console errors');
  if (errors.length) exitCode = 1;
} catch (e) {
  console.error(e);
  exitCode = 1;
} finally {
  if (browser) await browser.close();
  vite.kill('SIGTERM');
}
process.exit(exitCode);
