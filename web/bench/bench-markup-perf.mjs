// Markup attachment performance on large models (process-plant 1,294 elements, synth5k 5,000), with the section variants.
//   BENCH_PORT=5330 node bench/bench-markup-perf.mjs            (BENCH_MODELS=process-plant,synth5k to choose)
// Per model it measures, with performance.now around the hot paths (the app's own modules are wrapped through dynamic imports
// of the dev server, so nothing in src/ is instrumented):
//   - the time to finish a shape (projection + inference): a screen-filling cloud, a 400-point pen stroke, a rect over the dense middle;
//   - the same with a section plane active (rays skip the clipped side);
//   - frame time with 20 attached markups visible while the camera orbits: the JS time of the markup overlay per frame, and
//     the occlusion re-test after the camera stops (per frame and in total);
//   - box select over most of the model (window and crossing), also with a section box;
//   - restore of the markup set and migration of old shapes (import of a document without attachments).
// Swiftshader renders on the CPU: only the JS times of the markup code (not the frame interval) say anything about the markup cost.
// Writes bench/markup-perf.md.
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const port = Number(process.env.BENCH_PORT ?? 5330);
const MODELS = (process.env.BENCH_MODELS ?? 'process-plant,synth5k').split(',');
const VIEWPORT = { width: 1280, height: 720 };

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
const f = (x, d = 1) => (Number.isFinite(x) ? x.toFixed(d) : '-');

/** Everything that runs in the page. Returns plain data. */
async function measure(model) {
  const app = window.__xray.app;
  const r = app.renderer;
  const sleep = (ms) => new Promise((x) => setTimeout(x, ms));
  const raf = () => new Promise((x) => requestAnimationFrame(x));
  const med = (a) => { const s = [...a].sort((x, y) => x - y); return s.length ? s[Math.floor(s.length / 2)] : NaN; };
  const bcfMod = await import('/src/bcf/controller.ts');
  const viewMod = await import('/src/markup/view.ts');
  const markup = window.__xrayMarkup;
  const out = { model, elements: app.loaded.model.elements.length };

  // ---- instrumentation
  const T = { cast: 0, castN: 0, occ: 0, occN: 0, draw: 0, drawN: 0 };
  const P = bcfMod.BcfController.prototype;
  const oCast = P.castRay, oOcc = P.occluded;
  P.castRay = function (...a) { const t = performance.now(); try { return oCast.apply(this, a); } finally { T.cast += performance.now() - t; T.castN++; } };
  P.occluded = function (...a) { const t = performance.now(); try { return oOcc.apply(this, a); } finally { T.occ += performance.now() - t; T.occN++; } };
  const V = viewMod.MarkupView.prototype;
  const oDraw = V.draw;
  V.draw = function (...a) { const t = performance.now(); try { return oDraw.apply(this, a); } finally { T.draw += performance.now() - t; T.drawN++; } };

  // ---- the view: the whole model in view
  const W = app.canvas.clientWidth, H = app.canvas.clientHeight;
  out.canvas = [W, H];
  // A close three-quarter view of the dense middle of the model (about 0.45 of its half diagonal away), so rays hit geometry.
  const eb = app.loaded.model.elements.reduce((b, e) => e.bounds ? [Math.min(b[0], e.bounds[0]), Math.min(b[1], e.bounds[1]), Math.min(b[2], e.bounds[2]), Math.max(b[3], e.bounds[3]), Math.max(b[4], e.bounds[4]), Math.max(b[5], e.bounds[5])] : b, [1e9, 1e9, 1e9, -1e9, -1e9, -1e9]);
  const ctr = [(eb[0] + eb[3]) / 2, (eb[1] + eb[4]) / 2, (eb[2] + eb[5]) / 2];
  const half = Math.hypot(eb[3] - eb[0], eb[4] - eb[1], eb[5] - eb[2]) / 2;
  const view = process_view(ctr, half);
  function process_view(c, h) { return { pos: [c[0] + h * 0.35, c[1] + h * 0.22, c[2] + h * 0.42], target: c }; }
  r.camera.position.set(...view.pos);
  r.controls.target.set(...view.target);
  r.camera.near = Math.max(0.05, half * 0.002);
  r.camera.updateProjectionMatrix();
  r.controls.update();
  await sleep(500);
  const set = markup.create('perf');
  await sleep(300);

  const shapes = {
    'cloud, whole screen': () => ({ kind: 'cloud', points: [[W * 0.1, H * 0.1], [W * 0.9, H * 0.9]] }),
    'pen stroke, 400 points': () => ({ kind: 'pen', points: Array.from({ length: 400 }, (_, i) => [W * (0.08 + 0.84 * i / 399), H * (0.5 + 0.3 * Math.sin(i / 14))]) }),
    'rect, dense middle': () => ({ kind: 'rect', points: [[W * 0.35, H * 0.3], [W * 0.65, H * 0.7]] }),
  };
  async function finish(label) {
    const rows = [];
    for (const [name, spec] of Object.entries(shapes)) {
      const ts = [];
      let kind = '', rays = 0, rayMs = 0;
      for (let k = 0; k < 6; k++) {
        T.cast = 0; T.castN = 0; T.occ = 0; T.occN = 0;
        const t = performance.now();
        const m = markup.add(spec());
        ts.push(performance.now() - t);
        if (k > 0) { rays = T.castN; rayMs = T.cast; }
        kind = markup.attachment(m.id)?.attach.kind;
        markup.remove(m.id);
      }
      rows.push({ name, ms: med(ts.slice(1)), max: Math.max(...ts.slice(1)), kind, rays, rayMs });
    }
    return { label, rows };
  }
  out.finish = [await finish('no section')];

  // ---- section plane through the middle of the model (keeps the +x half... normal to the kept side)
  const sec = window.__xraySection;
  const mb = app.loaded.model.elements.reduce((b, e) => e.bounds ? [Math.min(b[0], e.bounds[0]), Math.min(b[1], e.bounds[1]), Math.min(b[2], e.bounds[2]), Math.max(b[3], e.bounds[3]), Math.max(b[4], e.bounds[4]), Math.max(b[5], e.bounds[5])] : b, [1e9, 1e9, 1e9, -1e9, -1e9, -1e9]);
  out.bounds = mb;
  const centre = [(mb[0] + mb[3]) / 2, (mb[1] + mb[4]) / 2, (mb[2] + mb[5]) / 2];
  r.setClipPlanes([{ normal: [0, -1, 0], point: [centre[0], mb[1] + (mb[4] - mb[1]) * 0.6, centre[2]] }], { cap: true });
  await sleep(300);
  out.finish.push(await finish('section plane (60% height)'));
  r.setClipPlanes(null);
  await sleep(200);

  // ---- 20 attached markups
  const made = [];
  const cols = 6, rowsN = 5;
  for (let j = 0; j < rowsN && made.length < 20; j++) {
    for (let i = 0; i < cols && made.length < 20; i++) {
      const cx = W * (0.15 + 0.7 * (i + 0.5) / cols), cy = H * (0.2 + 0.6 * (j + 0.5) / rowsN);
      const m = markup.add({ kind: j % 2 ? 'rect' : 'cloud', points: [[cx - 36, cy - 24], [cx + 36, cy + 24]] });
      if (markup.attachment(m.id)?.attach.kind !== 'none') made.push(m.id); else markup.remove(m.id);
    }
  }
  // Fill up with the rest of the grid at other sizes if too few attached.
  for (let k = 0; made.length < 20 && k < 60; k++) {
    const cx = W * (0.1 + 0.8 * Math.random()), cy = H * (0.15 + 0.7 * Math.random());
    const m = markup.add({ kind: 'rect', points: [[cx - 50, cy - 30], [cx + 50, cy + 30]] });
    if (markup.attachment(m.id)?.attach.kind !== 'none') made.push(m.id); else markup.remove(m.id);
  }
  out.attached = made.length;
  await sleep(500);

  // ---- the occlusion batch in isolation: 20 outlines x 12 samples, cold (every key stale at once, as when the interval is over)
  {
    const geo = new bcfMod.BcfController(app);
    const cam = r.camera.position;
    const pts = [];
    for (let k = 0; pts.length < 240 && k < 2000; k++) {
      const h = geo.pick((Math.random() * 2 - 1) * 0.9, (Math.random() * 2 - 1) * 0.9);
      if (h) pts.push(h.point);
    }
    const ts = [];
    let hid = 0;
    for (let rep = 0; rep < 8; rep++) {
      const t = performance.now();
      hid = 0;
      for (const p of pts) if (geo.occluded(p)) hid++;
      ts.push(performance.now() - t);
    }
    out.occBatch = { samples: pts.length, ms: med(ts.slice(1)), max: Math.max(...ts.slice(1)), hidden: hid };
    const tc = [];
    for (let rep = 0; rep < 8; rep++) {
      const t = performance.now();
      for (let k = 0; k < 300; k++) geo.castRay({ o: [cam.x, cam.y, cam.z], d: (() => { const a = (Math.random() - 0.5) * 1.2, b = (Math.random() - 0.5) * 0.9; const v = [Math.sin(a) * -1 + view.target[0] - cam.x, view.target[1] - cam.y + b * 4, view.target[2] - cam.z]; const l = Math.hypot(...v); return [v[0] / l, v[1] / l, v[2] / l]; })() });
      tc.push(performance.now() - t);
    }
    out.castBatch = { rays: 300, ms: med(tc.slice(1)) };
  }

  // ---- orbit with the markups visible, and the re-test after the camera stops
  async function orbitRun(seconds) {
    const target = r.controls.target.clone();
    const off = r.camera.position.clone().sub(target);
    const radius = off.length();
    const el = Math.asin(off.y / radius);
    const az0 = Math.atan2(off.x, off.z);
    const frames = [];
    let k = 0;
    const t0 = performance.now();
    let last = performance.now();
    while (performance.now() - t0 < seconds * 1000) {
      const az = az0 + (k++) * 0.012;
      r.camera.position.set(target.x + radius * Math.cos(el) * Math.sin(az), target.y + radius * Math.sin(el), target.z + radius * Math.cos(el) * Math.cos(az));
      r.controls.update();
      r.markDirty();
      const d0 = T.draw, o0 = T.occ, on0 = T.occN;
      await raf();
      const now = performance.now();
      frames.push({ dt: now - last, draw: T.draw - d0, occ: T.occ - o0, rays: T.occN - on0 });
      last = now;
    }
    // The camera stops: the re-test of every outline.
    const stop = [];
    const s0 = performance.now();
    while (performance.now() - s0 < 2500) {
      const d0 = T.draw, o0 = T.occ, on0 = T.occN;
      await raf();
      stop.push({ draw: T.draw - d0, occ: T.occ - o0, rays: T.occN - on0 });
    }
    r.camera.position.copy(target).add(off);
    r.controls.update();
    return { frames, stop };
  }
  const run = await orbitRun(8);
  const fr = run.frames;
  out.orbit = {
    frames: fr.length,
    drawMean: fr.reduce((a, b) => a + b.draw, 0) / fr.length,
    drawMax: Math.max(...fr.map((x) => x.draw)),
    drawP95: [...fr.map((x) => x.draw)].sort((a, b) => a - b)[Math.floor(fr.length * 0.95)],
    occMax: Math.max(...fr.map((x) => x.occ)),
    raysPerFrameMax: Math.max(...fr.map((x) => x.rays)),
    intervalMean: fr.reduce((a, b) => a + b.dt, 0) / fr.length,
    stopOccMax: Math.max(...run.stop.map((x) => x.occ)),
    stopOccTotal: run.stop.reduce((a, b) => a + b.occ, 0),
    stopDrawMax: Math.max(...run.stop.map((x) => x.draw)),
    stopRays: run.stop.reduce((a, b) => a + b.rays, 0),
    stopFramesWithRays: run.stop.filter((x) => x.rays > 0).length,
  };
  // Orbit with a section active: the occluded test also tests the clip.
  r.setClipPlanes([{ normal: [0, -1, 0], point: [centre[0], mb[1] + (mb[4] - mb[1]) * 0.6, centre[2]] }], { cap: true });
  await sleep(300);
  const run2 = await orbitRun(4);
  out.orbitSection = {
    drawMean: run2.frames.reduce((a, b) => a + b.draw, 0) / run2.frames.length,
    drawMax: Math.max(...run2.frames.map((x) => x.draw)),
    stopOccMax: Math.max(...run2.stop.map((x) => x.occ)),
    stopOccTotal: run2.stop.reduce((a, b) => a + b.occ, 0),
  };
  r.setClipPlanes(null);
  await sleep(200);

  // ---- restore and migration
  const rs = [];
  for (let k = 0; k < 5; k++) { const t = performance.now(); markup.restore(set.id, { animate: false }); rs.push(performance.now() - t); await raf(); }
  out.restore = med(rs);
  const file = markup.exportJson({ ids: [set.id] });
  const doc = JSON.parse(new TextDecoder().decode(file.bytes));
  let stripped = 0;
  const strip = (o) => { if (Array.isArray(o)) o.forEach(strip); else if (o && typeof o === 'object') { if ('attach' in o && 'shape' in o) { delete o.attach; stripped++; } Object.values(o).forEach(strip); } };
  strip(doc);
  const text = JSON.stringify(doc);
  T.castN = 0;
  const t1 = performance.now();
  await markup.importJson(text);
  out.migrate = { ms: performance.now() - t1, shapes: stripped, rays: T.castN };

  // ---- box select (the pure part, over the real model and camera)
  const box = async (label, rect, mode) => {
    const ts = [];
    let n = 0;
    for (let k = 0; k < 7; k++) { const t = performance.now(); n = window.__xrayPointer.pick(rect, mode).length; ts.push(performance.now() - t); }
    return { label, ms: med(ts.slice(1)), picked: n };
  };
  const all = { x0: 0, y0: 0, x1: W, y1: H };
  out.box = [await box('crossing, whole view', all, 'crossing'), await box('window, whole view', all, 'window'), await box('crossing, 80% of the view', { x0: W * 0.1, y0: H * 0.1, x1: W * 0.9, y1: H * 0.9 }, 'crossing')];
  r.setClipPlanes([{ normal: [1, 0, 0], point: [centre[0], centre[1], centre[2]] }, { normal: [-1, 0, 0], point: [centre[0] + (mb[3] - mb[0]) * 0.2, centre[1], centre[2]] }], { cap: true });
  await sleep(200);
  out.box.push(await box('crossing, whole view, section slab', all, 'crossing'));
  r.setClipPlanes(null);

  P.castRay = oCast; P.occluded = oOcc; V.draw = oDraw;
  return out;
}

let browser;
let code = 0;
try {
  await waitForServer();
  browser = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const version = browser.version();
  const results = [];
  const errors = [];
  for (const model of MODELS) {
    const page = await browser.newPage({ viewport: VIEWPORT });
    page.on('console', (m) => { if (m.type() === 'error') errors.push(`${model}: ${m.text()}`); });
    page.on('pageerror', (e) => errors.push(`${model}: ${e.message}`));
    await page.goto(`http://127.0.0.1:${port}/?model=${model}&cinematic=off`);
    await page.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: 240000 });
    const err = await page.evaluate('window.__xrayError');
    if (err) throw new Error(err);
    await page.evaluate(async () => { for (let i = 0; i < 200 && !window.__xray.app.controller.converged; i++) await new Promise((x) => setTimeout(x, 25)); });
    const res = await page.evaluate(measure, model);
    results.push(res);
    console.log(JSON.stringify(res));
    await page.close();
  }
  const T = { finish: 150, orbitFrame: 33, occBatch: 20, box: 100 };
  const lines = [];
  lines.push('# Markup attachment performance', '');
  lines.push(`Generated by \`node bench/bench-markup-perf.mjs\`. Chromium ${version} with swiftshader (CPU rasterisation): the frame interval is not meaningful, the JS times of the markup code are. Viewport ${VIEWPORT.width}x${VIEWPORT.height}. Medians of 5 runs unless noted.`, '');
  lines.push(`Targets: shape finish < ${T.finish} ms on synth5k; markup JS per frame while orbiting < ${T.orbitFrame} ms; occlusion re-test < ${T.occBatch} ms per frame of the batch; box select < ${T.box} ms.`, '');
  for (const r of results) {
    lines.push(`## ${r.model} (${r.elements} elements, ${r.attached} attached markups in the orbit run)`, '');
    lines.push('| shape finish | attached as | ms (median / max) | rays | ray ms |', '| --- | --- | --- | --- | --- |');
    for (const s of r.finish) for (const row of s.rows) lines.push(`| ${row.name}, ${s.label} | ${row.kind} | ${f(row.ms)} / ${f(row.max)} | ${row.rays} | ${f(row.rayMs)} |`);
    lines.push('');
    const o = r.orbit;
    lines.push(`Occlusion batch cold, ${r.occBatch.samples} samples (20 outlines x 12): ${f(r.occBatch.ms, 2)} ms median / ${f(r.occBatch.max, 2)} max (${r.occBatch.hidden} hidden). 300 rays through the dense view: ${f(r.castBatch.ms, 2)} ms.`, '');
    lines.push('| orbit with attached markups | value |', '| --- | --- |');
    lines.push(`| frames | ${o.frames} |`, `| markup overlay JS per frame, mean / p95 / max (ms) | ${f(o.drawMean, 2)} / ${f(o.drawP95, 2)} / ${f(o.drawMax, 2)} |`, `| occlusion ms in the worst orbit frame (rays) | ${f(o.occMax, 2)} (${o.raysPerFrameMax}) |`, `| after the stop: worst frame / total occlusion ms | ${f(o.stopOccMax, 2)} / ${f(o.stopOccTotal, 2)} |`, `| after the stop: worst overlay frame ms | ${f(o.stopDrawMax, 2)} |`, `| after the stop: rays in ${o.stopFramesWithRays} frame(s) | ${o.stopRays} |`);
    lines.push(`| with a section plane: overlay mean / max, re-test worst frame / total (ms) | ${f(r.orbitSection.drawMean, 2)} / ${f(r.orbitSection.drawMax, 2)}, ${f(r.orbitSection.stopOccMax, 2)} / ${f(r.orbitSection.stopOccTotal, 2)} |`, '');
    lines.push('| box select | picked | ms |', '| --- | --- | --- |');
    for (const b of r.box) lines.push(`| ${b.label} | ${b.picked} | ${f(b.ms, 2)} |`);
    lines.push('', `Restore of the set: ${f(r.restore, 2)} ms. Migration of ${r.migrate.shapes} old shapes (import of a document without attachments): ${f(r.migrate.ms)} ms, ${r.migrate.rays} rays.`, '');
  }
  writeFileSync(resolve(here, 'markup-perf.md'), lines.join('\n'));
  console.log('wrote bench/markup-perf.md', errors.length ? `errors: ${errors.join(' | ')}` : 'no console errors');
} catch (e) {
  console.error(e);
  code = 1;
} finally {
  await browser?.close();
  vite.kill();
  process.exit(code);
}
