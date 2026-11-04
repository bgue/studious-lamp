// Large-IFC load benchmark: opens synthetic IFC files (tools/make_big_ifc.py) through the file input of the viewer, in the dev
// app and in the single-file build, and records per-stage timings, the longest main-thread task, peak JS heap and the peak
// resident memory of the whole browser process tree.
//
//   node bench/bench-large-ifc.mjs --n 20000,100000                 dev app (vite, bench/vite.smoke.config.mjs)
//   node bench/bench-large-ifc.mjs --n 20000 --single               dist-single/xray-viewer.html from file:// (npm run bundle first)
//   options: --label after          name of the result file bench/large-ifc-<label>-<mode>-<n>.json
//            --edges auto|all|none  value of the `edges` dropdown (builds without the dropdown ignore it)
//            --props common|none    value of the `properties` dropdown
//            --dir /path            where the generated IFC files live (default $XRAY_BIG_DIR or /tmp/xray-big-ifc)
//            --root /path           web/ directory to serve (default: this repository; a snapshot copy works too)
//   env: BENCH_PORT (default 5351), PLAYWRIGHT_MODULE
// The IFC files are generated on demand with tools/make_big_ifc.py when missing.
import { spawn, execFileSync } from 'node:child_process';
import { existsSync, mkdirSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, resolve } from 'node:path';
import { loadavg } from 'node:os';
import { fileURLToPath, pathToFileURL } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const args = process.argv.slice(2);
const flag = (k) => args.includes(k);
const arg = (k, d) => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : d; };
const root = resolve(arg('--root', resolve(here, '..')));
const repo = resolve(root, '..');
const sizes = arg('--n', '20000').split(',').map(Number);
const single = flag('--single');
const label = arg('--label', 'run');
const edgesOpt = arg('--edges', '');
const propsOpt = arg('--props', '');
const dir = resolve(arg('--dir', process.env.XRAY_BIG_DIR ?? '/tmp/xray-big-ifc'));
const port = Number(process.env.BENCH_PORT ?? 5351);
const outDir = resolve(arg('--out-dir', here));

const req = createRequire(import.meta.url);
let pw;
for (const c of [process.env.PLAYWRIGHT_MODULE, resolve(root, 'node_modules/playwright'), '/opt/node-tools/node_modules/playwright', '/opt/node22/lib/node_modules/playwright'].filter(Boolean)) {
  try { pw = req(c); break; } catch { /* next */ }
}
if (!pw) throw new Error('playwright not found; set PLAYWRIGHT_MODULE');

mkdirSync(dir, { recursive: true });
for (const n of sizes) {
  const f = resolve(dir, `big-${n}.ifc`);
  if (!existsSync(f)) {
    console.log(`generating ${f}`);
    execFileSync('python3', [resolve(repo, 'tools/make_big_ifc.py'), '-n', String(n), '-o', f], { stdio: 'inherit' });
  }
}

let vite = null;
if (!single) {
  vite = spawn(resolve(root, 'node_modules/.bin/vite'), ['--config', resolve(root, 'bench/vite.smoke.config.mjs'), '--host', '127.0.0.1', '--port', String(port), '--strictPort'], { cwd: root, stdio: ['ignore', 'pipe', 'pipe'] });
  let ok = false;
  for (let i = 0; i < 100 && !ok; i++) {
    try { ok = (await fetch(`http://127.0.0.1:${port}/`)).ok; } catch { await new Promise((r) => setTimeout(r, 200)); }
  }
  if (!ok) { console.error('vite did not start'); vite.kill('SIGTERM'); process.exit(1); }
}

/** Sum of the resident set (MB) of a process and all its descendants. */
function treeRssMb(pid) {
  try {
    const rows = execFileSync('ps', ['-eo', 'pid=,ppid=,rss=']).toString().trim().split('\n').map((l) => l.trim().split(/\s+/).map(Number));
    const kids = new Map();
    for (const [p, pp, rss] of rows) { if (!kids.has(pp)) kids.set(pp, []); kids.get(pp).push([p, rss]); }
    const own = rows.find((r) => r[0] === pid);
    let sum = own ? own[2] : 0;
    const stack = [pid];
    while (stack.length) for (const [p, rss] of kids.get(stack.pop()) ?? []) { sum += rss; stack.push(p); }
    return sum / 1024;
  } catch { return 0; }
}

/** The browser (main) process of the chromium we launched: it carries our unique flag and no --type=. */
function browserPid(tag) {
  try {
    for (const l of execFileSync('ps', ['-eo', 'pid=,args=']).toString().split('\n')) {
      if (l.includes(tag) && !l.includes('--type=')) return Number(l.trim().split(/\s+/)[0]);
    }
  } catch { /* none */ }
  return 0;
}

const STAGES = [
  ['reading', /^(Large input.*)?Reading .*MB$/], ['opening', /^Opening /], ['meshing', /^Meshing /], ['relations', /^Reading relations/],
  ['merging', /^(Building model|Merging)/], ['edges', /^Edges/], ['bvh', /^(BVH|Building BVH)/], ['uploading', /^Uploading/], ['loaded', /^Loaded /],
];

async function run(n, file) {
  const tag = `--xray-bench-${process.pid}-${n}`;
  const browser = await pw.chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist', '--enable-precise-memory-info', tag] });
  const pid = browserPid(tag);
  const out = { n, mode: single ? 'single' : 'dev', label, edges: edgesOpt || 'default', props: propsOpt || 'default', loadAvgAtStart: Math.round(loadavg()[0] * 10) / 10 };
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
    const errors = [];
    const infos = [];
    page.on('console', (m) => {
      if (m.type() === 'error' || m.type() === 'warning') errors.push(`[${m.type()}] ${m.text()}`);
      else if (m.text().startsWith('[ifc-import]')) infos.push(m.text());
    });
    page.on('pageerror', (e) => errors.push(`[pageerror] ${e.message}`));
    await page.addInitScript(() => {
      const b = { long: [], status: [], heap: [], tool: null };
      window.__bench = b;
      try {
        new PerformanceObserver((list) => { for (const e of list.getEntries()) b.long.push([e.startTime, e.duration]); }).observe({ type: 'longtask', buffered: true });
      } catch { /* no longtask support */ }
      setInterval(() => {
        const t = performance.now();
        const m = performance.memory;
        if (m) b.heap.push([t, m.usedJSHeapSize]);
        const app = window.__xray?.app;
        const c = app?.panel?.controllersRecursive().find((x) => x.property === 'status');
        const s = c ? c.getValue() : '';
        if (s && (b.status.length === 0 || b.status[b.status.length - 1][1] !== s)) b.status.push([t, s]);
      }, 25);
    });
    const url = single ? pathToFileURL(resolve(root, 'dist-single/xray-viewer.html')).href : `http://127.0.0.1:${port}/?model=building`;
    await page.goto(url);
    await page.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: 120000 });
    await page.waitForTimeout(1500);
    out.baselineRssMb = Math.round(treeRssMb(pid));
    out.baselineHeapMb = Math.round((await page.evaluate('performance.memory ? performance.memory.usedJSHeapSize : 0')) / 1048576);

    const opts = await page.evaluate(([e, p]) => {
      const app = window.__xray.app;
      const find = (prop) => app.panel.controllersRecursive().find((c) => c.property === prop);
      const r = { hasEdges: !!find('edges'), hasProps: !!find('properties') };
      if (e && find('edges')) find('edges').setValue(e);
      if (p && find('properties')) find('properties').setValue(p);
      return r;
    }, [edgesOpt, propsOpt]);
    out.options = opts;

    let peakRss = out.baselineRssMb;
    const rssSeries = [];
    const wallStart = Date.now();
    const sampler = setInterval(() => { const r = treeRssMb(pid); peakRss = Math.max(peakRss, r); rssSeries.push([Date.now() - wallStart, Math.round(r)]); }, 300);

    const t0 = await page.evaluate(() => performance.now());
    const wall0 = Date.now();
    await page.setInputFiles('#xray-open-file-input', [file]);
    let status = '';
    for (;;) {
      status = await page.evaluate(() => window.__xray.app.panel.controllersRecursive().find((c) => c.property === 'status').getValue());
      if (/^Loaded /.test(status) || (!/^(Reading|Opening|Meshing|Building|Merging|Edges|BVH|Uploading|Large)/.test(status) && status !== '' && !/^Ready/.test(status))) break;
      if (Date.now() - wall0 > 20 * 60 * 1000) throw new Error('timed out: ' + status);
      await new Promise((r) => setTimeout(r, 200));
    }
    const wallMs = Date.now() - wall0;
    out.loadAvgAtEnd = Math.round(loadavg()[0] * 10) / 10;
    // first frame after the load
    const frameMs = await page.evaluate(() => new Promise((res) => { const a = performance.now(); requestAnimationFrame(() => requestAnimationFrame(() => res(performance.now() - a))); }));
    clearInterval(sampler);
    out.status = status;
    out.wallMs = wallMs;
    out.firstFramesMs = Math.round(frameMs);

    const b = await page.evaluate(() => window.__bench);
    const tail = b.long.filter(([s]) => s >= t0);
    out.longestTaskMs = Math.round(Math.max(0, ...tail.map(([, d]) => d)));
    out.longTasksOver200 = tail.filter(([, d]) => d > 200).length;
    out.longTasksOver1000 = tail.filter(([, d]) => d > 1000).length;
    out.longTaskTop = tail.map(([s, d]) => [Math.round(s - t0), Math.round(d)]).sort((a, c) => c[1] - a[1]).slice(0, 5);
    out.peakHeapMb = Math.round(Math.max(0, ...b.heap.filter(([t]) => t >= t0).map(([, h]) => h)) / 1048576);
    out.peakRssMb = Math.round(peakRss);
    out.rssSeries = rssSeries.filter((_, i) => i % Math.max(1, Math.ceil(rssSeries.length / 50)) === 0);
    const peakAt = rssSeries.reduce((a, b) => (b[1] > a[1] ? b : a), [0, 0])[0];
    out.rssAfterMb = Math.round(treeRssMb(pid));
    out.heapAfterMb = Math.round((await page.evaluate('performance.memory ? performance.memory.usedJSHeapSize : 0')) / 1048576);

    // stage starts from the status timeline
    const stages = {};
    for (const [t, text] of b.status) {
      if (t < t0) continue;
      for (const [name, re] of STAGES) if (re.test(text) && !(name in stages)) stages[name] = Math.round(t - t0);
    }
    const names = STAGES.map(([k]) => k).filter((k) => k in stages);
    out.stageStartMs = stages;
    out.peakRssAtStage = [...names].reverse().find((k) => stages[k] <= peakAt) ?? null;
    out.stageMs = {};
    for (let i = 0; i < names.length - 1; i++) out.stageMs[names[i]] = stages[names[i + 1]] - stages[names[i]];
    out.statusCount = b.status.length;

    // first use of the BVH (ray cast / hover): built lazily on the main thread when the load did not bring one
    out.bvhFirstUseMs = await page.evaluate(() => {
      const g = window.__xray.app.loaded?.geometry ?? window.__xray.app.geometry?.merged;
      if (!g) return null;
      const a = performance.now();
      void g.bvh;
      return Math.round(performance.now() - a);
    });
    out.elements = await page.evaluate('window.__xray.app.controller.model.elements.length');
    out.triangles = await page.evaluate(() => {
      const g = window.__xray.app.loaded?.geometry;
      return g ? g.geometry.getIndex().count / 3 : null;
    });
    out.edgeVertices = await page.evaluate(() => {
      const g = window.__xray.app.loaded?.geometry;
      return g ? g.edges.getAttribute('position').count : null;
    });
    out.consoleInfo = infos;
    out.errors = errors.slice(0, 5);
    out.fileMb = Math.round((await import('node:fs')).statSync(file).size / 1048576 * 10) / 10;
  } catch (e) {
    out.failure = String(e instanceof Error ? e.stack : e);
  } finally {
    await browser.close();
  }
  return out;
}

const results = [];
try {
  for (const n of sizes) {
    const file = resolve(dir, `big-${n}.ifc`);
    console.log(`--- ${n} elements, ${single ? 'single-file build' : 'dev app'}, label ${label}`);
    const r = await run(n, file);
    results.push(r);
    writeFileSync(resolve(outDir, `large-ifc-${label}-${r.mode}-${n}.json`), JSON.stringify(r, null, 2));
    console.log(JSON.stringify({ ...r, consoleInfo: undefined, longTaskTop: undefined, rssSeries: undefined, errors: undefined }, null, 1));
    console.log('longest tasks (start ms, duration ms):', JSON.stringify(r.longTaskTop));
  }
} finally {
  vite?.kill('SIGTERM');
}
process.exit(results.some((r) => r.failure) ? 1 : 0);
