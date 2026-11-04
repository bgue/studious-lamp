// Headless check of the imaging styles (radiograph, MRI) and of the standard-style pixel identity.
//   SMOKE_PORT=5361 node bench/smoke-imaging.mjs [fzk|synth|all]
// fzk-haus: an IfcWindow is the focus. synth5k: a duct riser is the focus. Writes bench/imaging-*.png:
//   imaging-standard.png, imaging-radiograph-{classic,negative,fluoro}.png, imaging-radiograph-peel.png,
//   imaging-synth-mri-{y,camera}.png, imaging-synth-mri-scan.png, imaging-synth-radiograph.png
// and prints the checks (standard style is pixel identical to the renderer without the feature).
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const port = Number(process.env.SMOKE_PORT ?? 5361);
const which = process.argv[2] ?? 'all';
const VIEW = { width: 1400, height: 760 };
const CLIP = { x: 300, y: 0, width: 800, height: 760 };

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
    let sum = 0, big = 0, exact = 0;
    const n = A.length / 4;
    for (let i = 0; i < A.length; i += 4) {
      let m = 0;
      for (let c = 0; c < 3; c++) { const d = Math.abs(A[i + c] - B[i + c]); sum += d; if (d > m) m = d; }
      if (m > 12) big++;
      if (m === 0) exact++;
    }
    return { meanAbs: +(sum / (n * 3)).toFixed(3), fracOver12: +(big / n).toFixed(4), identical: exact === n };
  }, [a.toString('base64'), b.toString('base64')]);
}

/** Mean RGB of a screenshot, for a rough "is this dark / light" check. */
async function meanRgb(page, a) {
  return page.evaluate(async (x) => {
    const bmp = await createImageBitmap(await (await fetch('data:image/png;base64,' + x)).blob());
    const c = new OffscreenCanvas(bmp.width, bmp.height);
    const g = c.getContext('2d');
    g.drawImage(bmp, 0, 0);
    const d = g.getImageData(0, 0, bmp.width, bmp.height).data;
    const s = [0, 0, 0];
    for (let i = 0; i < d.length; i += 4) for (let k = 0; k < 3; k++) s[k] += d[i + k];
    return s.map((v) => +(v / (d.length / 4)).toFixed(1));
  }, a.toString('base64'));
}

/** Luminance statistics of a screenshot (the tool strip on the left is skipped): mean, 10th and 90th percentile, share of near-white pixels. */
async function lumaStats(page, a) {
  return page.evaluate(async (x) => {
    const bmp = await createImageBitmap(await (await fetch('data:image/png;base64,' + x)).blob());
    const c = new OffscreenCanvas(bmp.width, bmp.height);
    const g = c.getContext('2d');
    g.drawImage(bmp, 0, 0);
    const d = g.getImageData(60, 0, bmp.width - 60, bmp.height).data;
    const L = [];
    let white = 0;
    for (let i = 0; i < d.length; i += 4) { L.push(0.299 * d[i] + 0.587 * d[i + 1] + 0.114 * d[i + 2]); if (d[i] >= 245 && d[i + 1] >= 245 && d[i + 2] >= 245) white++; }
    L.sort((p, q) => p - q);
    const q = (f) => L[Math.floor(f * (L.length - 1))];
    return { mean: +(L.reduce((p, v) => p + v, 0) / L.length).toFixed(1), p10: +q(0.1).toFixed(1), p50: +q(0.5).toFixed(1), p90: +q(0.9).toFixed(1), nearWhite: +(white / L.length).toFixed(4) };
  }, a.toString('base64'));
}

const SCENES = {
  fzk: {
    model: 'fzk-haus',
    prefix: 'imaging',
    select: `(els) => els.filter((e) => e.ifcClass === 'IfcWindow' && e.id === 22).map((e) => e.id)`,
    view: { pos: [6, 5.5, 13], tgt: [-3.95, -1.8, -4.8] },
    peel: { radius: 0.5, slope: 0.25 },
  },
  synth: {
    model: 'synth5k',
    prefix: 'imaging-synth',
    select: `(els) => { const ducts = els.filter((e) => e.ifcClass === 'IfcDuctSegment'); const ext = (e) => e.bounds[4] - e.bounds[1]; const best = ducts.reduce((a, b) => (ext(b) > ext(a) ? b : a)); return ducts.filter((e) => Math.abs(e.bounds[0] - best.bounds[0]) < 0.01 && Math.abs(e.bounds[2] - best.bounds[2]) < 0.01).map((e) => e.id); }`,
    view: null,
    peel: { radius: 0.6, slope: 0.3 },
  },
};

let browser;
let exitCode = 0;
const log = (...a) => console.log(a.join(' '));
const fail = (m) => { exitCode = 1; log('FAIL', m); };
try {
  await waitForServer();
  browser = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const errors = [];
  for (const key of which === 'all' ? ['fzk', 'synth'] : [which]) {
    const sc = SCENES[key];
    const page = await browser.newPage({ viewport: VIEW });
    page.on('console', (m) => {
      if (m.type() === 'error') errors.push(`[${key}][error] ${m.text()}`);
      if (m.type() === 'warning' && !m.text().startsWith('[help]')) errors.push(`[${key}][warning] ${m.text()}`);
    });
    page.on('pageerror', (e) => errors.push(`[${key}][pageerror] ${e.message}`));
    await page.goto(`http://127.0.0.1:${port}/?model=${sc.model}&cinematic=off`);
    await page.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: 180000 });
    const startErr = await page.evaluate('window.__xrayError');
    if (startErr) throw new Error(startErr);
    await page.addStyleTag({ content: '.lil-gui, #xray-overlay, #xray-message { visibility: hidden !important }' });
    log(`\n== ${sc.model}`);

    const setup = await page.evaluate(async ([selectSrc]) => {
      const app = window.__xray.app;
      const els = app.loaded.model.elements;
      const ids = (0, eval)(selectSrc)(els);
      if (els.length > 1000) app.settings.classification.focusClasses = [];
      app.selectIds(ids);
      const b = ids.map((i) => els[i].bounds);
      const lo = [0, 1, 2].map((a) => Math.min(...b.map((x) => x[a])));
      const hi = [3, 4, 5].map((a) => Math.max(...b.map((x) => x[a])));
      return { ids, lo, hi, api: !!window.__xrayImaging, focus: app.controller.classification.focus.size };
    }, [sc.select]);
    log('focus ids', JSON.stringify(setup.ids.slice(0, 8)), `(${setup.ids.length})`, 'api', setup.api, 'focus set', setup.focus);
    let view = sc.view;
    if (!view) {
      const c = setup.lo.map((l, i) => (l + setup.hi[i]) / 2);
      view = { pos: [c[0] + 13, c[1] + 9, c[2] + 16], tgt: c };
    }
    const setView = async (v) => {
      await page.evaluate(async ([v]) => {
        const app = window.__xray.app;
        const r = app.renderer;
        const sleep = (ms) => new Promise((x) => setTimeout(x, ms));
        r.camera.position.set(...v.pos);
        r.controls.target.set(...v.tgt);
        r.camera.near = 0.1;
        r.camera.updateProjectionMatrix();
        r.controls.update();
        app.runSightlinesNow();
        for (let i = 0; i < 400 && !app.controller.converged; i++) await sleep(25);
        await sleep(200);
      }, [v]);
    };
    const settle = (ms = 700) => page.evaluate(async (ms) => {
      for (let i = 0; i < 3; i++) await new Promise((r) => requestAnimationFrame(r));
      await new Promise((r) => setTimeout(r, ms));
      for (let i = 0; i < 2; i++) await new Promise((r) => requestAnimationFrame(r));
    }, ms);
    const shot = async (name, ms) => {
      await settle(ms);
      return page.screenshot({ path: resolve(here, `${sc.prefix}-${name}.png`), clip: CLIP, timeout: 180000 });
    };
    const img = (p) => page.evaluate((p) => window.__xrayImaging.set(p), p);
    const reset = () => img({ style: 'standard', palette: 'classic', exposure: 1, contrast: 1, boneGlow: 1, tissueEdges: true, mri: { axis: 'camera', thickness: 0.3, position: 0.5, scan: false, scanSpeed: 0.25 } });
    const peel = (on) => page.evaluate(([on, p]) => window.__xrayViewModes.setPeel({ enabled: on, ...p, animate: false }), [on, sc.peel]);

    await setView(view);
    await reset();
    const base = await shot('standard', 900);

    // Standard again after visiting radiograph and MRI: pixel identical.
    await img({ style: 'radiograph' });
    await settle(500);
    await img({ style: 'mri' });
    await settle(500);
    await img({ style: 'standard' });
    const again = await shot('standard-again', 900);
    const d0 = await diff(page, base, again);
    log('standard after imaging vs standard before', JSON.stringify(d0));
    if (!d0.identical) fail(`${key}: standard style is not pixel identical`);
    const st = await page.evaluate(() => window.__xrayImaging.status());
    log('imaging status', JSON.stringify({ supported: st.supported, status: st.status }));

    if (key === 'fzk') {
      for (const pal of ['classic', 'negative', 'fluoro']) {
        await img({ style: 'radiograph', palette: pal });
        const s = await shot(`radiograph-${pal}`, 1200);
        if (pal === 'classic') {
          const st = await page.evaluate(() => window.__xrayImaging.status());
          const on = await lumaStats(page, s);
          log('radiograph classic, auto exposure on: factor', st.autoExposure.toFixed(3), 'measures', st.measures, 'luma', JSON.stringify(on));
          if (!(st.measures > 0)) fail(`${key}: the automatic exposure never measured`);
          if (on.p90 - on.p10 < 20 || on.nearWhite > 0.1) fail(`${key}: the radiograph has no readable structure (${JSON.stringify(on)})`);
        }
        log(`radiograph ${pal}`.padEnd(24), 'mean rgb', JSON.stringify(await meanRgb(page, s)), 'vs standard', JSON.stringify(await diff(page, base, s)));
      }
      await img({ style: 'radiograph', palette: 'classic' });
      const noPeel = await shot('radiograph-nopeel', 900);
      await peel(true);
      const withPeel = await shot('radiograph-peel', 1500);
      log('radiograph peel vs no peel', JSON.stringify(await diff(page, noPeel, withPeel)));
      await peel(false);
      await img({ style: 'radiograph', boneGlow: 0 });
      const noGlow = await shot('radiograph-noglow', 900);
      await img({ boneGlow: 1.5 });
      const glow = await shot('radiograph-glow', 900);
      log('bone glow 0 vs 1.5', JSON.stringify(await diff(page, noGlow, glow)));
      await img({ boneGlow: 1, exposure: 2.2, contrast: 1.4 });
      await shot('radiograph-hot', 900);
    } else {
      await img({ style: 'radiograph', palette: 'classic' });
      const radio = await shot('radiograph', 1200);
      {
        const st = await page.evaluate(() => window.__xrayImaging.status());
        const on = await lumaStats(page, radio);
        await img({ autoExposure: false });
        const off = await lumaStats(page, await shot('radiograph-noauto', 1200));
        await img({ autoExposure: true });
        log('radiograph classic, auto exposure on: factor', st.autoExposure.toFixed(3), 'measures', st.measures, 'luma', JSON.stringify(on));
        log('radiograph classic, auto exposure off (exposure 1):', 'luma', JSON.stringify(off));
        if (!(st.measures > 0)) fail(`${key}: the automatic exposure never measured`);
        if (st.autoExposure > 0.5) fail(`${key}: the tall model should need a much lower exposure than 1 (factor ${st.autoExposure})`);
        if (on.p90 - on.p10 < 20 || on.nearWhite > 0.1) fail(`${key}: the radiograph has no readable structure (${JSON.stringify(on)})`);
        if (!(off.p10 > on.p10 + 10)) log('note: without the automatic exposure the picture is not much flatter here');
      }
      // MRI through the riser, horizontal slice (axis y)
      await img({ style: 'mri', palette: 'classic', mri: { axis: 'y', thickness: 0.3, position: 0.5, scan: false } });
      const my = await shot('mri-y', 1500);
      log('mri axis y', JSON.stringify(await page.evaluate(() => window.__xrayImaging.status().slab)), 'mean rgb', JSON.stringify(await meanRgb(page, my)));
      await img({ style: 'mri', mri: { axis: 'camera', thickness: 0.5, position: 0.5, scan: false } });
      const mc = await shot('mri-camera', 1500);
      log('mri axis camera', JSON.stringify(await page.evaluate(() => window.__xrayImaging.status().slab)), 'mean rgb', JSON.stringify(await meanRgb(page, mc)));
      // scan: sample the position over time and take a shot mid-sweep
      await img({ style: 'mri', mri: { axis: 'y', thickness: 0.4, position: 0.0, scan: true, scanSpeed: 0.25 } });
      const samples = [];
      for (let i = 0; i < 6; i++) {
        await settle(700);
        samples.push(await page.evaluate(() => +window.__xrayImaging.config.mri.position.toFixed(3)));
      }
      log('scan positions', JSON.stringify(samples));
      const sc1 = await shot('mri-scan', 100);
      log('scan shot position', await page.evaluate(() => window.__xrayImaging.config.mri.position.toFixed(2)), 'vs mri-y', JSON.stringify(await diff(page, my, sc1)));
      if (new Set(samples).size < 4) fail('scan did not move');
      await img({ mri: { scan: false } });
    }
    await reset();
    await page.close();
  }
  if (errors.length) { log('\nconsole problems:'); errors.forEach((e) => log(' ', e)); exitCode = 1; }
  else log('\nno console errors or warnings');
} catch (e) {
  console.error(e);
  exitCode = 1;
} finally {
  await browser?.close();
  vite.kill();
}
process.exit(exitCode);
