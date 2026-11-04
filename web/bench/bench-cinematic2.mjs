// Second-round cinematic benchmark (sweep reveal, depth grading, AO + vignette, ...). Runs every model in four modes:
//   off      /?cinematic=off   every cinematic feature off (the plugin is a no-op)
//   cin2off  /?cin2=off        the first-round defaults (fly-to, reveal, dressing) with the second-round ones off
//   on       /                 all defaults (adds sweep reveal and depth grading)
//   aoVig    defaults + AO and vignette switched on after load (the costly post pipeline)
// and writes bench/RESULTS-cinematic2.md, including a comparison with the frame CPU numbers in bench/RESULTS.md.
// It does not touch RESULTS.md, RESULTS-cinematic.md or app-*.png.
//
// Headless benchmark and screenshot harness for the X-ray viewer.
//
//   node bench/bench.mjs [model ...]        default: synth5k building
//
// Starts vite on 127.0.0.1, opens /?model=<name> in Chromium with swiftshader (CPU rasterisation),
// selects the first IfcDuctSegment, orbits the camera through 36 positions and records Algorithm 1
// and 2 timings, rays per update and frame times. Writes bench/RESULTS.md and
// bench/app-<model>.png. Swiftshader numbers are CPU rasterisation, not GPU numbers.
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const models = process.argv.slice(2).filter((a) => !a.startsWith('--'));
if (models.length === 0) models.push('synth5k', 'building');
const port = Number(process.env.BENCH_PORT ?? 5189);
const modes = ['off', 'cin2off', 'on', 'aoVig'];
const POSITIONS = 36;
const ALG1_RUNS = 10;
const VIEWPORT = { width: 1920, height: 1080 };

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

const mean = (a) => (a.length ? a.reduce((x, y) => x + y, 0) / a.length : NaN);
const p95 = (a) => {
  if (!a.length) return NaN;
  const s = [...a].sort((x, y) => x - y);
  return s[Math.min(s.length - 1, Math.ceil(0.95 * s.length) - 1)];
};
const f = (x, d = 2) => (Number.isFinite(x) ? x.toFixed(d) : '-');

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

/** Runs inside the page. Orbits and collects numbers for one maxSamples setting. */
async function orbitInPage({ positions, maxSamples }) {
  const x = window.__xray;
  const app = x.app;
  const ctl = app.controller;
  const cam = app.renderer.camera;
  const controls = app.renderer.controls;
  ctl.settings.sightlines.maxSamples = maxSamples;
  app.runSightlinesNow();
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  // Let smoothing finish at the start position.
  for (let i = 0; i < 400 && !ctl.converged; i++) await sleep(25);

  const target = controls.target.clone();
  const offset = cam.position.clone().sub(target);
  const radius = offset.length();
  const elevation = Math.asin(offset.y / radius);
  const az0 = Math.atan2(offset.x, offset.z);

  ctl.stats.sightlinesHistory.length = 0;
  app.frameLog.intervals.length = 0;
  app.frameLog.cpu.length = 0;
  for (let i = 0; i < positions; i++) {
    const az = az0 + (i / positions) * Math.PI * 2;
    cam.position.set(
      target.x + radius * Math.cos(elevation) * Math.sin(az),
      target.y + radius * Math.sin(elevation),
      target.z + radius * Math.cos(elevation) * Math.cos(az),
    );
    const before = ctl.stats.sightlinesCount;
    controls.update(); // fires the change event -> debounced Algorithm 2
    for (let t = 0; t < 120 && ctl.stats.sightlinesCount === before; t++) await sleep(25);
    await sleep(150); // settle: a few frames of smoothing
  }
  await sleep(300);
  return {
    sightlines: ctl.stats.sightlinesHistory.slice(),
    frameIntervals: app.frameLog.intervals.slice(),
    frameCpu: app.frameLog.cpu.slice(),
  };
}

/** Runs inside the page: frame the selected focus element for the screenshot. */
function framePage(id) {
  const app = window.__xray.app;
  const e = app.loaded.model.elements[id];
  const b = e.bounds;
  const c = [(b[0] + b[3]) / 2, (b[1] + b[4]) / 2, (b[2] + b[5]) / 2];
  const cam = app.renderer.camera;
  const controls = app.renderer.controls;
  const dist = app.modelName === 'synth5k' ? 16 : 11;
  const lift = app.modelName === 'synth5k' ? 0.6 : 0.3; // lower view on the small building: walls between camera and duct
  controls.target.set(c[0], c[1], c[2]);
  cam.position.set(c[0] + dist * 0.55, c[1] + dist * lift, c[2] + dist * 0.6);
  cam.near = 0.05;
  cam.updateProjectionMatrix();
  controls.update();
}

const results = [];
let browser;
let exitCode = 0;
try {
  await waitForServer();
  browser = await chromium.launch({
    args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'],
  });
  const version = browser.version();

  for (const mode of modes) for (const model of models) {
    const page = await browser.newPage({ viewport: VIEWPORT });
    const errors = [];
    page.on('console', (m) => { if (m.type() === 'error') errors.push(`[console.error] ${m.text()}`); });
    page.on('pageerror', (e) => errors.push(`[pageerror] ${e.message}`));
    const t0 = Date.now();
    const query = mode === 'off' ? '&cinematic=off' : mode === 'cin2off' ? '&cin2=off' : '';
    await page.goto(`http://127.0.0.1:${port}/?model=${model}${query}`);
    await page.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: 180000 });
    const startupErr = await page.evaluate('window.__xrayError');
    if (startupErr) throw new Error(`startup error: ${startupErr}`);
    const loadMs = Date.now() - t0;
    if (mode === 'aoVig') {
      await page.evaluate(() => {
        const cin = window.__cinematic;
        cin.post.settings.ao = true;
        cin.post.settings.vignette = true;
        cin.post.sync();
      });
    }

    const info = await page.evaluate(() => {
      const app = window.__xray.app;
      const els = app.loaded.model.elements;
      const duct = els.find((e) => e.ifcClass === 'IfcDuctSegment');
      return { count: els.length, ductId: duct ? duct.id : -1, modelName: app.modelName };
    });
    if (info.ductId < 0) throw new Error(`no IfcDuctSegment in ${model}`);

    // Algorithm 1: cold-cache runs.
    const alg1 = await page.evaluate(async ({ id, runs }) => {
      const app = window.__xray.app;
      const ctl = app.controller;
      ctl.stats.classifyHistory.length = 0;
      for (let i = 0; i < runs; i++) {
        app.clearGeometryCaches();
        app.selectIds([id]);
        await new Promise((r) => setTimeout(r, 30));
      }
      return ctl.stats.classifyHistory.slice();
    }, { id: info.ductId, runs: ALG1_RUNS });

    const buckets = await page.evaluate(() => ({ ...window.__xray.app.controller.stats.buckets }));
    const variants = [];
    for (const maxSamples of [500, 300]) {
      const r = await page.evaluate(orbitInPage, { positions: POSITIONS, maxSamples });
      variants.push({ maxSamples, ...r });
    }
    await page.evaluate(() => { window.__xray.app.controller.settings.sightlines.maxSamples = 500; });

    // Screenshot: X-ray on, duct selected, framed on the duct, settled.
    await page.evaluate(framePage, info.ductId);
    await page.evaluate(async () => {
      const ctl = window.__xray.app.controller;
      window.__xray.app.runSightlinesNow();
      for (let i = 0; i < 600 && !ctl.converged; i++) await new Promise((r) => setTimeout(r, 25));
      await new Promise((r) => setTimeout(r, 400));
    });
    const png = resolve(here, `cinematic2-app-${model}-${mode}.png`);
    if (mode === 'on' || mode === 'aoVig') await page.screenshot({ path: png });
    const alphaSummary = await page.evaluate(() => {
      const app = window.__xray.app;
      const c = app.controller;
      const a = c.state.alpha;
      const occ = [...c.classification.host, ...c.classification.near];
      const ghosted = occ.filter((id) => a[id] < 0.99).length;
      let min = 1;
      for (const id of occ) min = Math.min(min, a[id]);
      return { occluders: occ.length, ghosted, minAlpha: min };
    });
    const webgl = await page.evaluate(() => {
      const gl = window.__xray.renderer.renderer.getContext();
      const ext = gl.getExtension('WEBGL_debug_renderer_info');
      return ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : 'unknown';
    });
    results.push({ model, mode, info, alg1, buckets, variants, loadMs, errors, png, alphaSummary, webgl });
    console.log(`${model} [cinematic ${mode}]: ${info.count} elements, buckets ${JSON.stringify(buckets)}, ghosted ${alphaSummary.ghosted}/${alphaSummary.occluders}, errors ${errors.length}`);
    if (errors.length) { console.log(errors.join('\n')); exitCode = 1; }
    await page.close();
  }

  // ---- RESULTS.md
  const rows = [];
  for (const r of results) {
    for (const v of r.variants) {
      const ms = v.sightlines.map((s) => s.ms);
      const rays = v.sightlines.map((s) => s.rays);
      rows.push(
        `| ${r.model} | ${r.mode} | ${r.info.count} | ${r.buckets.focus}/${r.buckets.host}/${r.buckets.near}/${r.buckets.far} | ` +
        `${f(mean(r.alg1))} / ${f(p95(r.alg1))} | ${v.maxSamples} | ${v.sightlines.length} | ` +
        `${f(mean(ms), 3)} / ${f(p95(ms), 3)} | ${f(mean(rays), 0)} / ${f(p95(rays), 0)} | ` +
        `${f(mean(v.frameIntervals), 1)} / ${f(p95(v.frameIntervals), 1)} | ${f(mean(v.frameCpu), 1)} / ${f(p95(v.frameCpu), 1)} |`,
      );
    }
  }
  // ---- comparison with the committed baseline (RESULTS.md, frame CPU mean) and with the plugin switched off
  const baseline = new Map();
  try {
    for (const line of readFileSync(resolve(here, 'RESULTS.md'), 'utf8').split('\n')) {
      const c = line.split('|').map((x) => x.trim());
      if (c.length > 10 && /^\d+$/.test(c[5] ?? '')) baseline.set(`${c[1]}/${c[5]}`, parseFloat((c[10] ?? '').split('/')[0]));
    }
  } catch { /* no baseline file */ }
  const cmpRows = [];
  const pct = (a, b) => (Number.isFinite(a) && Number.isFinite(b) && b > 0 ? `${((a / b - 1) * 100).toFixed(0)}%` : '-');
  for (const on of results.filter((r) => r.mode === 'on')) {
    const by = (mode) => results.find((r) => r.mode === mode && r.model === on.model);
    for (const v of on.variants) {
      const cpu = (r) => (r ? mean(r.variants.find((x) => x.maxSamples === v.maxSamples)?.frameCpu ?? []) : NaN);
      const base = baseline.get(`${on.model}/${v.maxSamples}`);
      const [mOff, mC2, mOn, mAo] = [cpu(by('off')), cpu(by('cin2off')), cpu(on), cpu(by('aoVig'))];
      cmpRows.push(`| ${on.model} | ${v.maxSamples} | ${f(base, 1)} | ${f(mOff, 2)} | ${f(mC2, 2)} | ${f(mOn, 2)} | ${f(mAo, 2)} | ${pct(mOff, base)} | ${pct(mC2, base)} | ${pct(mOn, base)} | ${pct(mOn, mC2)} |`);
    }
  }
  const cmp = `## Frame CPU: modes versus baseline

Mean frame CPU in ms (JS time of smoothing, plugin hooks and the \`renderer.render()\` call). "RESULTS.md" is the committed baseline
(one decimal place). Modes: **off** = \`?cinematic=off\` (every cinematic feature off), **cin2 off** = \`?cin2=off\` (first-round defaults,
second-round features off), **on** = all defaults (sweep reveal and depth grading on), **AO+vig** = defaults with AO and vignette switched on.
At 0.4 to 1.2 ms the numbers are dominated by run-to-run noise, so compare the columns within one run rather than against the committed one-decimal baseline.

| model | maxSamples | RESULTS.md | off | cin2 off | on | AO+vig | off vs RESULTS.md | cin2 off vs RESULTS.md | on vs RESULTS.md | on vs cin2 off |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
${cmpRows.join('\n')}
`;
  const md = `# Benchmark results: cinematic plugin, second round

Generated by \`node bench/bench-cinematic2.mjs\` on ${new Date().toISOString().slice(0, 10)}.

**Swiftshader numbers are CPU rasterisation, not GPU numbers.** The headless Chromium (${results[0]?.webgl ? 'WebGL renderer: ' + results[0].webgl : 'swiftshader'}) draws
the 1920x1080 frame on the CPU, so the frame times below are far above what a laptop GPU would give. Algorithm 1 and 2 timings are
pure JavaScript (three-mesh-bvh on the CPU) and are the meaningful part of this table; they are unaffected by the rasteriser except that
the main thread shares the machine with it.

- Browser: Chromium ${version}, viewport ${VIEWPORT.width}x${VIEWPORT.height}, \`--use-angle=swiftshader --enable-unsafe-swiftshader --ignore-gpu-blocklist\`
- Scene: \`/?model=<name>\`, first IfcDuctSegment selected programmatically (\`app.selectIds([id])\`), X-ray on, default settings
- Algorithm 1: ${ALG1_RUNS} runs, geometry distance/intersection caches cleared before each (cold), mean / p95 ms
- Algorithm 2: camera orbited through ${POSITIONS} azimuths (elevation fixed), runs triggered by the app's own debounced camera handler (at most one per 50 ms), mean / p95
- Frame interval: requestAnimationFrame deltas during the orbit; frame CPU: JS time of smoothing + \`renderer.render()\` call (excludes asynchronous GPU/raster work)
- Focus / host / near / far are bucket sizes from Algorithm 1

| model | mode | elements | focus/host/near/far | Alg 1 ms (mean / p95) | maxSamples | Alg 2 runs | Alg 2 ms (mean / p95) | rays per update (mean / p95) | frame interval ms (mean / p95) | frame CPU ms (mean / p95) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
${rows.join('\n')}

Targets from SPEC (laptop GPU): 16 ms frame, 5 ms sightlines (300 samples), 50 ms classification.

${cmp}
Screenshots: ${results.filter((r) => r.mode === 'on' || r.mode === 'aoVig').map((r) => `\`bench/${r.png.split('/').pop()}\``).join(', ')}.
${results.map((r) => `\n- ${r.model} (cinematic ${r.mode}): ${r.alphaSummary.ghosted} of ${r.alphaSummary.occluders} occluders ghosted after settling, minimum alpha ${f(r.alphaSummary.minAlpha)}; page load to ready ${r.loadMs} ms`).join('')}
`;
  writeFileSync(resolve(here, 'RESULTS-cinematic2.md'), md);
  console.log('wrote', resolve(here, 'RESULTS-cinematic2.md'));

} catch (e) {
  console.error(e);
  exitCode = 1;
} finally {
  if (browser) await browser.close();
  vite.kill('SIGTERM');
}
process.exit(exitCode);
