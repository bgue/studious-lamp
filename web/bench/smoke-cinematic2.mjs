// Headless screenshots and checks for the second round of cinematic features, on the building model.
//   node bench/smoke-cinematic2.mjs
// Writes bench/smoke-cin2-sweep.png (mid-sweep, ~400 ms after the selection), smoke-cin2-sightlines.png,
// smoke-cin2-explode.png, smoke-cin2-ao.png (AO + vignette) and smoke-cin2-dof.png (depth of field during
// a fly-through play), and runs a short MediaRecorder test. Prints the checks and any console errors.
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
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
  const context = await browser.newContext({ viewport: { width: 1280, height: 800 }, acceptDownloads: true });
  const page = await context.newPage();
  const errors = [];
  page.on('console', (m) => { if (m.type() === 'error' || m.type() === 'warning') errors.push(`[${m.type()}] ${m.text()}`); });
  page.on('pageerror', (e) => errors.push(`[pageerror] ${e.message}`));
  const downloads = [];
  page.on('download', (d) => downloads.push(d));
  await page.goto(`http://127.0.0.1:${port}/?model=building`);
  await page.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: 120000 });
  const err = await page.evaluate('window.__xrayError');
  if (err) throw new Error(err);

  // ---- setup: a fixed view of the duct through the slabs, nothing selected yet
  const setup = await page.evaluate(async () => {
    const app = window.__xray.app;
    const cin = window.__cinematic;
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
    const duct = app.loaded.model.elements.find((e) => e.ifcClass === 'IfcDuctSegment');
    cin.cfg.flyTo = false;
    app.selectIds([duct.id]);
    cin.flyToElements([duct.id], { durationMs: 1 });
    await sleep(300);
    // Settle, remember the framed view, then clear so the sweep starts from opaque.
    for (let i = 0; i < 200 && (cin.planeSweep.running || !app.controller.converged); i++) await sleep(25);
    window.__view = { p: app.renderer.camera.position.toArray(), t: app.renderer.controls.target.toArray() };
    app.clearSelection();
    for (let i = 0; i < 200 && !app.controller.converged; i++) await sleep(25);
    return { ductId: duct.id, view: window.__view, buckets: { ...app.controller.stats.buckets } };
  });
  console.log('setup:', JSON.stringify(setup));

  // ---- 1. sweep, mid-way
  const sweep = await page.evaluate(async () => {
    const app = window.__xray.app;
    const cin = window.__cinematic;
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
    const t0 = performance.now();
    app.selectIds([window.__ductId ?? app.loaded.model.elements.find((e) => e.ifcClass === 'IfcDuctSegment').id]);
    const started = cin.planeSweep.running;
    await sleep(380);
    return { started, progressAt380: +cin.planeSweep.progress(performance.now()).toFixed(2), elapsed: Math.round(performance.now() - t0), mode: cin.cfg.sweep.mode };
  });
  await page.screenshot({ path: resolve(here, 'smoke-cin2-sweep.png') });
  const sweepAfter = await page.evaluate(async () => {
    const cin = window.__cinematic;
    const app = window.__xray.app;
    const at = +cin.planeSweep.progress(performance.now()).toFixed(2);
    for (let i = 0; i < 200 && (cin.planeSweep.running || cin.stagger.size > 0 || !app.controller.converged); i++) await new Promise((r) => setTimeout(r, 25));
    return { progressAtScreenshotEnd: at, finished: !cin.planeSweep.running };
  });
  console.log('sweep:', JSON.stringify(sweep), JSON.stringify(sweepAfter));
  await page.screenshot({ path: resolve(here, 'smoke-cin2-after-sweep.png') });

  // ---- 3. sightlines
  const rays = await page.evaluate(async () => {
    const cin = window.__cinematic;
    cin.cfg.sightlines.durationS = 6;
    cin.cfg.sightlines.style = 'both';
    cin.cfg.sightlines.max = 120;
    const n = cin.showSightlines(); // rays toward the camera position now
    // Orbit to the side so the rays (drawn in world space) are seen from the side, not end-on.
    const cam = window.__xray.app.renderer.camera;
    const tgt = window.__xray.app.renderer.controls.target;
    const off = cam.position.clone().sub(tgt);
    const a = 1.1;
    cam.position.set(tgt.x + off.x * Math.cos(a) + off.z * Math.sin(a), tgt.y + off.y * 0.35, tgt.z - off.x * Math.sin(a) + off.z * Math.cos(a));
    window.__xray.app.renderer.controls.update();
    await new Promise((r) => setTimeout(r, 250));
    return n;
  });
  await page.screenshot({ path: resolve(here, 'smoke-cin2-sightlines.png') });
  console.log('sightline rays drawn:', rays);
  await page.evaluate(() => {
    const v = window.__view;
    window.__cinematic.viz.clear();
    const app = window.__xray.app;
    app.renderer.camera.position.fromArray(v.p);
    app.renderer.controls.target.fromArray(v.t);
    app.renderer.controls.update();
  });

  // ---- 5. explode
  const ex = await page.evaluate(async () => {
    const cin = window.__cinematic;
    Object.assign(cin.cfg.explode, { mode: "radial", factor: 2.5 });
    cin.explode();
    await new Promise((r) => setTimeout(r, 1500));
    return { exploded: cin.exploded, anim: +cin.explodeAnim.value.toFixed(2) };
  });
  await page.screenshot({ path: resolve(here, 'smoke-cin2-explode.png') });
  console.log('explode:', JSON.stringify(ex));
  const col = await page.evaluate(async () => {
    const cin = window.__cinematic;
    cin.collapse();
    await new Promise((r) => setTimeout(r, 1200));
    return { exploded: cin.exploded, tableCleared: cin.explodeAnim.value === 0 };
  });
  console.log('collapse:', JSON.stringify(col));

  // ---- 4. AO + vignette, and a direct-versus-composed pixel check
  const px = await page.evaluate(async () => {
    const cin = window.__cinematic;
    const r = window.__xray.renderer;
    const gl = r.renderer.getContext();
    const read = () => {
      r.markDirty();
      r.render();
      const w = gl.drawingBufferWidth, h = gl.drawingBufferHeight;
      const buf = new Uint8Array(w * h * 4);
      gl.readPixels(0, 0, w, h, gl.RGBA, gl.UNSIGNED_BYTE, buf);
      return buf;
    };
    const direct = read();
    cin.post.settings.vignette = true;
    cin.post.settings.vignetteDarkness = 0; // composer path with no visible effect
    cin.post.sync();
    const composed = read();
    let sum = 0, max = 0;
    for (let i = 0; i < direct.length; i += 4) for (let c = 0; c < 3; c++) { const d = Math.abs(direct[i + c] - composed[i + c]); sum += d; if (d > max) max = d; }
    return { meanAbsDiff: +(sum / (direct.length / 4 * 3)).toFixed(3), maxDiff: max };
  });
  console.log('composed vs direct pixels:', JSON.stringify(px));
  await page.evaluate(async () => {
    const cin = window.__cinematic;
    cin.post.settings.ao = true;
    cin.post.settings.aoRadius = 0.8;
    cin.post.settings.aoIntensity = 1;
    cin.post.settings.vignette = true;
    cin.post.settings.vignetteDarkness = 0.8;
    cin.post.sync();
    for (let i = 0; i < 6; i++) await new Promise((r) => requestAnimationFrame(r));
    await new Promise((r) => setTimeout(r, 500));
  });
  await page.screenshot({ path: resolve(here, 'smoke-cin2-ao.png') });
  // Switching the post pipeline on or off changes the render-target state of every material, so swiftshader
  // recompiles the shaders for a few seconds each time: let that settle before timing frames.
  const cost = await page.evaluate(async () => {
    const app = window.__xray.app;
    const cin = window.__cinematic;
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
    const measure = async () => {
      await sleep(8000);
      app.frameLog.intervals.length = 0; app.frameLog.cpu.length = 0;
      await sleep(4000);
      const m = (a) => (a.length ? a.reduce((x, y) => x + y, 0) / a.length : NaN);
      return { frameMs: +m(app.frameLog.intervals).toFixed(1), cpuMs: +m(app.frameLog.cpu).toFixed(2), frames: app.frameLog.intervals.length };
    };
    const on = await measure();
    cin.post.settings.ao = false; cin.post.settings.vignette = false; cin.post.sync();
    const off = await measure();
    return { aoVignetteOn: on, off };
  });
  console.log('AO + vignette cost (swiftshader):', JSON.stringify(cost));

  // ---- 6/7. fly-through with DoF; then a short recording
  const fly = await page.evaluate(async () => {
    const app = window.__xray.app;
    const cin = window.__cinematic;
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
    const v = window.__view;
    cin.clearKeys();
    // Keyframe 1: the framed view of the duct; keyframe 2: pulled back and higher; keyframe 3: back near the first.
    const duct = app.loaded.model.elements.find((e) => e.ifcClass === 'IfcDuctSegment');
    app.renderer.camera.position.fromArray(v.p);
    app.renderer.controls.target.fromArray(v.t);
    app.renderer.controls.update();
    app.selectIds([duct.id]);
    cin.addKeyframe();
    const p2 = v.p.map((x, i) => x + (i === 1 ? 2.5 : (x - v.t[i]) * 0.5));
    app.renderer.camera.position.fromArray(p2);
    app.renderer.controls.update();
    cin.addKeyframe();
    app.renderer.camera.position.fromArray(v.p);
    app.renderer.controls.update();
    cin.addKeyframe();
    const stored = localStorage.getItem('xray.flythrough.' + app.modelName);
    const json = cin.exportJson();
    cin.importJson(json);
    cin.cfg.fly.segmentS = 4;
    cin.post.settings.dof = true;
    cin.post.settings.dofAperture = 0.7;
    cin.post.sync();
    cin.play();
    await sleep(1800);
    return { keys: cin.keys.length, persisted: !!stored && JSON.parse(stored).keyframes.length, playing: cin.playing };
  });
  await page.screenshot({ path: resolve(here, 'smoke-cin2-dof.png') });
  console.log('fly-through:', JSON.stringify(fly));
  await page.evaluate(async () => {
    const cin = window.__cinematic;
    for (let i = 0; i < 400 && cin.playing; i++) await new Promise((r) => setTimeout(r, 50));
    cin.post.settings.dof = false; cin.post.sync();
  });

  // keyframes from stored selection sets (xray.sets.building is seeded by the sidebar)
  const sets = await page.evaluate(() => {
    const cin = window.__cinematic;
    const app = window.__xray.app;
    const raw = localStorage.getItem('xray.sets.' + app.modelName);
    const stored = raw ? (JSON.parse(raw).sets ?? JSON.parse(raw)).length : 0;
    const before = cin.keys.length;
    const n = cin.loadFromSets();
    return { storedSets: stored, keysBefore: before, keysAfter: cin.keys.length, built: n, names: cin.keys.map((k) => k.name), selSizes: cin.keys.map((k) => k.selection.length) };
  });
  console.log('keyframes from sets:', JSON.stringify(sets));
  // restore three keyframes for the recording test
  await page.evaluate(() => {
    const cin = window.__cinematic;
    const v = window.__view;
    const app = window.__xray.app;
    cin.clearKeys();
    for (const f of [1, 2.2, 1]) {
      app.renderer.camera.position.fromArray(v.p.map((x, i) => v.t[i] + (x - v.t[i]) * f));
      app.renderer.controls.update();
      cin.addKeyframe();
    }
  });

  const rec = await page.evaluate(async () => {
    const cin = window.__cinematic;
    cin.cfg.fly.segmentS = 1; // 3 keyframes -> 2 s
    const supported = typeof MediaRecorder !== 'undefined' && 'captureStream' in HTMLCanvasElement.prototype;
    const types = supported ? ['video/webm;codecs=vp9', 'video/webm;codecs=vp8'].map((t) => [t, MediaRecorder.isTypeSupported(t)]) : [];
    cin.lastRecording = null;
    const started = cin.record();
    for (let i = 0; i < 200 && !cin.lastRecording; i++) await new Promise((r) => setTimeout(r, 100));
    const r = cin.lastRecording;
    return { supported, types, started, bytes: r ? r.bytes : null, mime: r ? r.mime : null };
  });
  await page.waitForTimeout(500);
  console.log('record:', JSON.stringify(rec), 'downloads:', downloads.map((d) => d.suggestedFilename()));
  if (downloads[0]) {
    const path = await downloads[0].path();
    const { statSync } = await import('node:fs');
    console.log('downloaded file size:', path ? statSync(path).size : null);
  }

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
