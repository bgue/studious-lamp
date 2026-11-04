// Headless check of weighted blended OIT for the ghost pass, on /?model=synth5k.
//   node bench/smoke-oit.mjs
// Selects a duct riser (the chain of IfcDuctSegments that share the footprint of the one with the largest
// vertical extent), forces the slabs around it to alpha 0.4 and screenshots OIT off and on from the same camera:
//   bench/oit-off.png / oit-on.png                 camera above, looking down
//   bench/oit-oblique-off.png / oit-oblique-on.png low oblique angle, slab edges overlap in screen space
//   bench/oit-below-off.png / oit-below-on.png     from below (the draw order of the merged geometry is then back to front inverted)
// The three central slabs are tinted red, green, blue so the layer order can be read off the images.
// It also checks order independence (reversing the triangle order of the merged geometry), and the regression
// cases: focus in front / behind, a frozen sweep band, exploded context, AO + vignette (composed path), bloom.
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { rmSync, writeFileSync } from 'node:fs';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const port = Number(process.env.SMOKE_PORT ?? 5197);
const VIEW = { width: 1400, height: 860 };
const CLIP = { x: 300, y: 0, width: 800, height: 860 };

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

/** Mean absolute difference (0..255 per channel) and the fraction of pixels differing by more than 12, between two PNGs. */
async function diff(page, a, b) {
  return page.evaluate(async ([x, y]) => {
    const load = async (b64) => {
      const bmp = await createImageBitmap(await (await fetch('data:image/png;base64,' + b64)).blob());
      const c = new OffscreenCanvas(bmp.width, bmp.height);
      const g = c.getContext('2d');
      g.drawImage(bmp, 0, 0);
      return g.getImageData(0, 0, bmp.width, bmp.height).data;
    };
    const A = await load(x);
    const B = await load(y);
    let sum = 0, big = 0, max = 0;
    const n = A.length / 4;
    for (let i = 0; i < A.length; i += 4) {
      let m = 0;
      for (let c = 0; c < 3; c++) { const d = Math.abs(A[i + c] - B[i + c]); sum += d; if (d > m) m = d; }
      if (m > 12) big++;
      if (m > max) max = m;
    }
    return { meanAbs: +(sum / (n * 3)).toFixed(3), fracOver12: +(big / n).toFixed(4), max };
  }, [a.toString('base64'), b.toString('base64')]);
}

let browser;
let exitCode = 0;
const out = [];
const log = (...a) => { const s = a.join(' '); out.push(s); console.log(s); };
try {
  await waitForServer();
  browser = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const page = await browser.newPage({ viewport: VIEW });
  const errors = [];
  page.on('console', (m) => { if (m.type() === 'error') errors.push(`[error] ${m.text()}`); if (m.type() === 'warning' && !m.text().startsWith('[help]')) errors.push(`[warning] ${m.text()}`); });
  page.on('framenavigated', (f) => { if (process.env.SMOKE_VERBOSE && f === page.mainFrame()) console.log('  navigated', f.url()); });
  page.on('console', (m) => { if (process.env.SMOKE_VERBOSE && m.type() !== 'warning') console.log('  console', m.type(), m.text().slice(0, 300)); });
  page.on('pageerror', (e) => errors.push(`[pageerror] ${e.message}`));
  await page.goto(`http://127.0.0.1:${port}/?model=synth5k&cinematic=off`);
  await page.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: 180000 });
  const startErr = await page.evaluate('window.__xrayError');
  if (startErr) throw new Error(startErr);
  const caps = await page.evaluate(() => ({ supported: window.__xray.renderer.oitSupported, on: window.__xray.renderer.oitEnabled, status: window.__xray.renderer.oitStatus }));
  log('capabilities:', JSON.stringify(caps));
  if (!caps.supported) throw new Error('OIT not supported in this context');

  // ---- setup: select the riser, find the slabs
  const setup = await page.evaluate(() => {
    const app = window.__xray.app;
    const r = app.renderer;
    const els = app.loaded.model.elements;
    const ducts = els.filter((e) => e.ifcClass === 'IfcDuctSegment');
    const ext = (e) => e.bounds[4] - e.bounds[1];
    const best = ducts.reduce((a, b) => (ext(b) > ext(a) ? b : a));
    const chain = ducts.filter((e) => Math.abs(e.bounds[0] - best.bounds[0]) < 0.01 && Math.abs(e.bounds[2] - best.bounds[2]) < 0.01);
    const yMin = Math.min(...chain.map((e) => e.bounds[1]));
    const yMax = Math.max(...chain.map((e) => e.bounds[4]));
    const cx = (best.bounds[0] + best.bounds[3]) / 2, cz = (best.bounds[2] + best.bounds[5]) / 2, cy = (yMin + yMax) / 2;
    const near = els.filter((e) => e.ifcClass === 'IfcSlab' && Math.hypot((e.bounds[0] + e.bounds[3]) / 2 - cx, (e.bounds[2] + e.bounds[5]) / 2 - cz) < 12);
    // the three slabs around the riser's middle: the ones whose footprint covers the duct, nearest in y to the middle
    const cover = els.filter((e) => e.ifcClass === 'IfcSlab' && e.bounds[0] <= cx && e.bounds[3] >= cx && e.bounds[2] <= cz && e.bounds[5] >= cz).sort((a, b) => Math.abs((a.bounds[1] + a.bounds[4]) / 2 - cy) - Math.abs((b.bounds[1] + b.bounds[4]) / 2 - cy));
    window.__t = { clutterIds: els.filter((e) => e.ifcClass !== 'IfcSlab' && !chain.includes(e)).map((e) => e.id), cx, cy, cz, ductIds: chain.map((e) => e.id), nearIds: near.map((e) => e.id), mid: cover.slice(0, 3).map((e) => e.id).sort((a, b) => a - b) };
    app.selectIds(chain.map((e) => e.id));
    return { bestId: best.id, bestExtent: ext(best), chain: chain.length, chainYRange: [yMin, yMax], centre: [cx, cy, cz], slabsForced: near.length, mid: window.__t.mid, midY: window.__t.mid.map((id) => [els[id].bounds[1], els[id].bounds[4]]) };
  });
  log('setup:', JSON.stringify(setup));

  const hideUi = () => page.addStyleTag({ content: '.lil-gui, #xray-overlay, #xray-message { visibility: hidden !important }' });
  await hideUi();

  // Camera, settle the sightlines, then force the slab alphas (the controller rewrites them while it converges).
  const setView = async (pos, tgt, tint = true, clutter = false) => {
    await page.evaluate(async ([pos, tgt, tint, clutter]) => {
      const app = window.__xray.app;
      const r = app.renderer;
      const sleep = (ms) => new Promise((x) => setTimeout(x, ms));
      r.camera.position.set(...pos);
      r.controls.target.set(...tgt);
      r.camera.near = 0.1;
      r.camera.updateProjectionMatrix();
      r.controls.update();
      app.runSightlinesNow();
      for (let i = 0; i < 400 && !app.controller.converged; i++) await sleep(25);
      await sleep(300);
      const T = window.__t;
      const st = r.state;
      r.resetColors();
      for (const id of T.nearIds) st.alpha[id] = 0.4;
      // clutter: every non-slab, non-riser element (beams, columns, walls, other ducts and pipes) is hidden so the layers read
      if (!clutter) for (const id of T.clutterIds) st.alpha[id] = -1;
      if (tint) {
        const cols = [[1, 0.1, 0.1], [0.1, 1, 0.1], [0.15, 0.3, 1]];
        T.mid.forEach((id, i) => { for (let c = 0; c < 3; c++) st.color[id * 3 + c] = cols[i][c]; });
      }
      // tinted views: no desaturation and faint edges so the colour of each layer reads; the others keep the defaults
      r.setGhostDesaturate(tint ? 0 : app.display.ghostDesaturate);
      r.setEdgeAlpha(tint ? 0.25 : app.display.edgeAlpha);
      r.markDirty();
    }, [pos, tgt, tint, clutter]);
  };
  const settle = (ms = 900) => page.evaluate(async (ms) => {
    for (let i = 0; i < 3; i++) await new Promise((r) => requestAnimationFrame(r));
    await new Promise((r) => setTimeout(r, ms));
    for (let i = 0; i < 2; i++) await new Promise((r) => requestAnimationFrame(r));
  }, ms);
  const shot = async (name) => {
    await settle();
    const buf = await page.screenshot({ path: resolve(here, name), clip: CLIP, timeout: 180000 });
    const fr = await page.evaluate(() => { const f = window.__xray.app.frameLog; return +(f.intervals.slice(-5).reduce((a, b) => a + b, 0) / Math.max(1, f.intervals.slice(-5).length)).toFixed(0); });
    if (process.env.SMOKE_VERBOSE) console.log('  shot', name, 'frame interval ms', fr);
    return buf;
  };
  const setOit = (on) => page.evaluate((on) => window.__xray.renderer.setOit(on), on);

  const T = await page.evaluate(() => window.__t);
  const views = {
    above: { pos: [T.cx + 3, T.cy + 22, T.cz + 5], tgt: [T.cx, T.cy, T.cz], file: '' },
    oblique: { pos: [T.cx + 15, T.cy + 1.2, T.cz + 17], tgt: [T.cx - 2, T.cy, T.cz - 2], file: '-oblique' },
    below: { pos: [T.cx + 3, T.cy - 22, T.cz + 5], tgt: [T.cx, T.cy, T.cz], file: '-below' },
  };
  const shots = {};
  for (const [name, v] of Object.entries(views)) {
    await setView(v.pos, v.tgt);
    await setOit(false);
    const off = await shot(`oit${v.file}-off.png`);
    await setOit(true);
    const on = await shot(`oit${v.file}-on.png`);
    shots[name] = { off, on };
    log(`view ${name}: off vs on`, JSON.stringify(await diff(page, off, on)));
  }

  // the realistic scene: nothing hidden, the same slabs forced to 0.4, uncoloured, oblique
  await setView(views.oblique.pos, views.oblique.tgt, false, true);
  await setOit(false);
  const fullOff = await shot('oit-oblique-full-off.png');
  await setOit(true);
  const fullOn = await shot('oit-oblique-full-on.png');
  log('oblique with all clutter visible: off vs on', JSON.stringify(await diff(page, fullOff, fullOn)));

  // ---- order independence: reverse the triangle order of the merged geometry
  const flip = (on) => page.evaluate((on) => {
    const g = window.__xray.app.loaded.geometry.geometry;
    const idx = g.index;
    if (on) {
      window.__origIndex = idx.array;
      const src = idx.array, n = src.length / 3;
      const rev = new src.constructor(src.length);
      for (let i = 0; i < n; i++) rev.set(src.subarray((n - 1 - i) * 3, (n - i) * 3), i * 3);
      idx.array = rev;
    } else idx.array = window.__origIndex;
    idx.needsUpdate = true;
  }, on);
  await setView(views.oblique.pos, views.oblique.tgt);
  const indep = {};
  for (const mode of [false, true]) {
    await setOit(mode);
    const a = await shot(`oit-tmp.png`);
    await flip(true);
    const b = await shot(`oit-tmp.png`);
    await flip(false);
    indep[mode ? 'on' : 'off'] = await diff(page, a, b);
    if (!mode) writeFileSync(resolve(here, 'oit-oblique-reversed-off.png'), b);
    else writeFileSync(resolve(here, 'oit-oblique-reversed-on.png'), b);
  }
  log('order independence (oblique view, original vs reversed triangle order): off', JSON.stringify(indep.off), ' on', JSON.stringify(indep.on));
  await setOit(true);

  // ---- depth weight: flat versus paper (oblique)
  await page.evaluate(() => window.__xray.renderer.setOitWeight('flat'));
  const flat = await shot('oit-oblique-flat.png');
  await page.evaluate(() => window.__xray.renderer.setOitWeight('paper'));
  log('oblique paper vs flat weight', JSON.stringify(await diff(page, shots.oblique.on, flat)));

  // ---- regression: focus in front / behind (view above, uncoloured)
  await setView(views.above.pos, views.above.tgt, false);
  for (const front of [true, false]) {
    await page.evaluate((f) => { window.__xray.app.display.inFront = f; window.__xray.renderer.setInFront(f); }, front);
    await setOit(false);
    const off = await shot(`oit-focus-${front ? 'front' : 'behind'}-off.png`);
    await setOit(true);
    const on = await shot(`oit-focus-${front ? 'front' : 'behind'}-on.png`);
    log(`focus ${front ? 'in front' : 'behind'}: off vs on`, JSON.stringify(await diff(page, off, on)));
  }
  await page.evaluate(() => { window.__xray.app.display.inFront = true; window.__xray.renderer.setInFront(true); });

  // ---- regression: frozen sweep band (plane through the slab at y ~ +3.4), oblique, uncoloured
  await setView(views.oblique.pos, views.oblique.tgt, false);
  await page.evaluate((T) => {
    const r = window.__xray.renderer;
    const V = r.camera.position.constructor;
    const hold = new Float32Array(r.state.alpha.length);
    for (const id of T.nearIds) hold[id] = 1; // they were opaque before the selection
    r.setSweep(hold, 0.15, 0.25);
    r.setSweepPlane(new V(0, -1, 0), -(T.cy + 3.4)); // reached (peeled) above y = cy + 3.4
    r.markDirty();
  }, T);
  await setOit(false);
  const swOff = await shot('oit-sweep-off.png');
  await setOit(true);
  const swOn = await shot('oit-sweep-on.png');
  log('sweep band: off vs on', JSON.stringify(await diff(page, swOff, swOn)));
  await page.evaluate(() => { window.__xray.renderer.setSweep(null); window.__xray.renderer.markDirty(); });

  // ---- regression: exploded context (default cinematic features are off in this page: use the explode offsets directly)
  await page.evaluate((T) => {
    const app = window.__xray.app;
    const r = app.renderer;
    const els = app.loaded.model.elements;
    for (const id of T.nearIds) { const e = els[id]; const y = (e.bounds[1] + e.bounds[4]) / 2 - T.cy; r.setElementOffset(id, 0, y * 0.9, 0); }
    r.markDirty();
  }, T);
  await setOit(false);
  const exOff = await shot('oit-explode-off.png');
  await setOit(true);
  const exOn = await shot('oit-explode-on.png');
  log('explode (slabs pushed apart vertically): off vs on', JSON.stringify(await diff(page, exOff, exOn)));
  await page.evaluate(() => { window.__xray.renderer.clearElementOffsets(); window.__xray.renderer.markDirty(); });

  // ---- composed path (AO + vignette + DoF off) and bloom
  const post = await page.evaluate(async () => {
    const cin = window.__cinematic;
    const r = window.__xray.renderer;
    const gl = r.renderer.getContext();
    const sleep = (ms) => new Promise((x) => setTimeout(x, ms));
    const read = async () => {
      r.markDirty();
      await sleep(600);
      r.markDirty();
      r.render();
      const w = gl.drawingBufferWidth, h = gl.drawingBufferHeight;
      const buf = new Uint8Array(w * h * 4);
      gl.readPixels(0, 0, w, h, gl.RGBA, gl.UNSIGNED_BYTE, buf);
      return buf;
    };
    const cmp = (a, b) => { let s = 0, m = 0; for (let i = 0; i < a.length; i += 4) for (let c = 0; c < 3; c++) { const d = Math.abs(a[i + c] - b[i + c]); s += d; if (d > m) m = d; } return { meanAbs: +(s / (a.length / 4 * 3)).toFixed(3), max: m }; };
    if (!cin) return { error: 'no cinematic plugin' };
    r.setOit(true);
    const direct = await read();
    cin.post.settings.vignette = true;
    cin.post.settings.vignetteDarkness = 0; // composer path, no visible effect
    cin.post.sync();
    const composed = await read();
    return { directVsComposedOn: cmp(direct, composed) };
  });
  log('composed path (vignette 0) vs direct path, OIT on:', JSON.stringify(post));
  await setOit(false);
  const composedOff = await shot('oit-composed-off.png');
  await setOit(true);
  await page.evaluate(() => { const c = window.__cinematic; c.post.settings.ao = true; c.post.settings.aoRadius = 0.8; c.post.settings.vignette = true; c.post.settings.vignetteDarkness = 0.6; c.post.sync(); });
  const composedOn = await shot('oit-composed-ao-on.png');
  await page.evaluate(() => { const c = window.__cinematic; c.post.settings.ao = false; c.post.settings.vignette = false; c.post.sync(); c.bloom.enable(); });
  const bloomOn = await shot('oit-bloom-on.png');
  await page.evaluate(() => { window.__cinematic.bloom.disable(); });
  log('composed path screenshots written: oit-composed-off.png (composer on, vignette 0, OIT off), oit-composed-ao-on.png (AO + vignette, OIT on), oit-bloom-on.png (bloom, OIT on)');
  void composedOff; void composedOn; void bloomOn;

  rmSync(resolve(here, 'oit-tmp.png'), { force: true });
  log('console errors/warnings:', errors.length ? '\n' + errors.join('\n') : 'none');
  if (errors.length) exitCode = 1;
} catch (e) {
  console.error(e);
  if (process.env.SMOKE_VERBOSE) console.error('vite log:\n' + viteLog);
  exitCode = 1;
} finally {
  if (browser) await browser.close();
  vite.kill('SIGTERM');
}
process.exit(exitCode);
