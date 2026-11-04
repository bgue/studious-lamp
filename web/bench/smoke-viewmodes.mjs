// Headless check of the view modes (behind-only, partial peelback, hover highlight).
//   SMOKE_PORT=5311 node bench/smoke-viewmodes.mjs [fzk|synth|all]
// fzk-haus: an IfcWindow is the focus. synth5k: a duct riser is the focus. For each model the same camera gives
//   vm-off, vm-behind-cut, vm-behind-cap, vm-behind-ghost, vm-behind-horizontal, vm-peel, vm-peel-only, vm-both
// (fzk-haus files are named vm-*.png, synth5k files vm-synth-*.png), plus an orbit pair vm-peel-orbit-a/b.png,
// the CPU-fallback peel (vm-peel-cpu.png), a hover-highlight shot and the checks printed at the end.
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const port = Number(process.env.SMOKE_PORT ?? 5311);
const which = process.argv[2] ?? 'all';
const VIEW = { width: 1400, height: 760 };
const CLIP = { x: 300, y: 0, width: 800, height: 760 };
const ONLY = process.env.SMOKE_CASES ? process.env.SMOKE_CASES.split(',') : null;

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

/** Mean absolute difference (0..255 per channel) and the fraction of pixels differing by more than 12. */
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
    let sum = 0, big = 0;
    const n = A.length / 4;
    for (let i = 0; i < A.length; i += 4) {
      let m = 0;
      for (let c = 0; c < 3; c++) { const d = Math.abs(A[i + c] - B[i + c]); sum += d; if (d > m) m = d; }
      if (m > 12) big++;
    }
    return { meanAbs: +(sum / (n * 3)).toFixed(3), fracOver12: +(big / n).toFixed(4) };
  }, [a.toString('base64'), b.toString('base64')]);
}

const SCENES = {
  fzk: {
    model: 'fzk-haus',
    prefix: 'vm',
    // The focus: window 22 in the north wall (z = -4.84). The camera sits south-east, outside, so the south wall, the roof and the floor slab are in front of it.
    select: `(els) => els.filter((e) => e.ifcClass === 'IfcWindow' && e.id === 22).map((e) => e.id)`,
    view: { pos: [6, 5.5, 13], tgt: [-3.95, -1.8, -4.8] },
    orbit: [{ pos: [6, 5.5, 13], tgt: [-3.95, -1.8, -4.8] }, { pos: [-13, 5.5, 8], tgt: [-3.95, -1.8, -4.8] }],
    behind: { offset: 0.2 },
    peel: { radius: 0.5, slope: 0.25 },
  },
  synth: {
    model: 'synth5k',
    prefix: 'vm-synth',
    select: `(els) => { const ducts = els.filter((e) => e.ifcClass === 'IfcDuctSegment'); const ext = (e) => e.bounds[4] - e.bounds[1]; const best = ducts.reduce((a, b) => (ext(b) > ext(a) ? b : a)); return ducts.filter((e) => Math.abs(e.bounds[0] - best.bounds[0]) < 0.01 && Math.abs(e.bounds[2] - best.bounds[2]) < 0.01).map((e) => e.id); }`,
    view: null, // computed from the riser
    orbit: null,
    behind: { offset: 0.2 },
    peel: { radius: 0.6, slope: 0.3 },
  },
};

let browser;
let exitCode = 0;
const out = [];
const log = (...a) => { const s = a.join(' '); out.push(s); console.log(s); };
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
      if (process.env.SMOKE_VERBOSE && m.type() !== 'warning') console.log('  console', m.type(), m.text().slice(0, 300));
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
      // A duct belongs to a system of hundreds of elements that the focus would expand to; keep just the riser
      // (selection plus its connected run) so that the context in front of it is something to cut.
      if (els.length > 1000) app.settings.classification.focusClasses = [];
      app.selectIds(ids);
      const b = ids.map((i) => els[i].bounds);
      const lo = [0, 1, 2].map((a) => Math.min(...b.map((x) => x[a])));
      const hi = [3, 4, 5].map((a) => Math.max(...b.map((x) => x[a])));
      return { ids, lo, hi, vm: !!window.__xrayViewModes, focus: app.controller.classification.focus.size };
    }, [sc.select]);
    log('focus ids', JSON.stringify(setup.ids.slice(0, 12)), setup.ids.length > 12 ? `(${setup.ids.length})` : '', 'bounds', JSON.stringify(setup.lo.map((x) => +x.toFixed(2))), JSON.stringify(setup.hi.map((x) => +x.toFixed(2))), 'api', setup.vm, 'focus set', setup.focus);
    let view = sc.view;
    let orbit = sc.orbit;
    if (!view) {
      const c = setup.lo.map((l, i) => (l + setup.hi[i]) / 2);
      view = { pos: [c[0] + 13, c[1] + 9, c[2] + 16], tgt: c };
      orbit = [view, { pos: [c[0] - 14, c[1] + 8, c[2] + 14], tgt: c }];
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
    const reset = () => page.evaluate(() => {
      const vm = window.__xrayViewModes;
      vm.setBehind({ enabled: false, frontTreatment: 'cut', orientation: 'camera', applyTo: 'all context', keepXrayBehind: false, offset: 0.2, frontAlpha: 0.12 });
      vm.setPeel({ enabled: false, outside: 'x-ray', applyTo: 'all context', animate: true, radius: 0.4, slope: 0.6, feather: 0.08 });
      window.__xray.renderer.setPeelPath('auto');
    });
    const shot = async (name, ms) => {
      await settle(ms);
      return page.screenshot({ path: resolve(here, `${sc.prefix}-${name}.png`), clip: CLIP, timeout: 180000 });
    };
    const mode = async (b, p) => {
      await reset();
      await page.evaluate(([b, p]) => {
        const vm = window.__xrayViewModes;
        if (b) vm.setBehind({ enabled: true, ...b });
        if (p) vm.setPeel({ enabled: true, ...p });
      }, [b, p]);
    };

    await setView(view);
    await reset();
    const off = await shot('off');
    const shots = { off };
    const bh = sc.behind;
    const pe = sc.peel;
    const cases = [
      ['behind-cut', { ...bh, frontTreatment: 'cut' }, null],
      ['behind-cap', { ...bh, frontTreatment: 'cut + cap' }, null],
      ['behind-ghost', { ...bh, frontTreatment: 'ghost' }, null],
      ['behind-horizontal', { ...bh, frontTreatment: 'cut + cap', orientation: 'horizontal' }, null],
      ['peel', null, { ...pe }],
      ['peel-only', null, { ...pe, outside: 'solid' }],
      ['both', { ...bh, frontTreatment: 'ghost' }, { ...pe }],
    ];
    for (const [name, b, p] of cases) {
      if (ONLY && !ONLY.includes(name)) continue;
      await mode(b, p);
      shots[name] = await shot(name, 1400);
      const st = await page.evaluate(() => window.__xrayViewModes.status());
      let still = '';
      if (p) {
        // a still camera must not rebuild the mask every frame
        const a = (await page.evaluate(() => window.__xrayViewModes.status())).peelRefreshes;
        await settle(1500);
        const b = (await page.evaluate(() => window.__xrayViewModes.status())).peelRefreshes;
        still = `mask rebuilds while still: ${b - a}`;
      }
      log(name.padEnd(18), 'vs off', JSON.stringify(await diff(page, off, shots[name])), 'peelPath', st.peelPath, 'refreshes', st.peelRefreshes, st.plane ? `plane d=${st.plane.d.toFixed(2)}` : '', still);
    }

    if (ONLY && !process.env.SMOKE_TAIL) { await page.close(); continue; }
    // CPU fallback
    await mode(null, { ...pe });
    await page.evaluate(() => window.__xray.renderer.setPeelPath('cpu'));
    shots.cpu = await shot('peel-cpu', 1400);
    log('peel (CPU ellipses)  vs off', JSON.stringify(await diff(page, off, shots.cpu)), 'vs gpu', JSON.stringify(await diff(page, shots.peel, shots.cpu)), 'path', (await page.evaluate(() => window.__xrayViewModes.status())).peelPath);

    // Orbit: the window stays on the focus
    await mode(null, { ...pe });
    for (const [i, v] of orbit.entries()) {
      await setView(v);
      shots[`orbit${i}`] = await shot(`peel-orbit-${'ab'[i]}`, 1400);
    }
    // Picking inside the window: probe the pick at the focus centre with peel on and off
    const pick = await page.evaluate(async ([ids]) => {
      const r = window.__xray.renderer;
      const app = window.__xray.app;
      const sleep = (ms) => new Promise((x) => setTimeout(x, ms));
      const els = app.loaded.model.elements;
      const c = [0, 1, 2].map((a) => ids.reduce((s, i) => s + (els[i].bounds[a] + els[i].bounds[a + 3]) / 2, 0) / ids.length);
      const v = r.camera.position.constructor;
      const p = new v(...c).project(r.camera);
      const res = {};
      // x-ray off: every context element is opaque, so only the cut rule can let the pick through
      app.setXray(false);
      await sleep(400);
      window.__xrayViewModes.setPeel({ enabled: true, animate: false });
      await sleep(400);
      res.peelOn = r.pick(p.x, p.y);
      window.__xrayViewModes.setPeel({ enabled: false, animate: true });
      await sleep(200);
      res.peelOff = r.pick(p.x, p.y);
      window.__xrayViewModes.setBehind({ enabled: true, frontTreatment: 'cut' });
      await sleep(200);
      res.behindOn = r.pick(p.x, p.y);
      window.__xrayViewModes.setBehind({ enabled: false });
      app.setXray(true);
      res.focus = ids.includes(res.peelOn) ? 'focus' : els[res.peelOn]?.ifcClass ?? null;
      res.focusOff = ids.includes(res.peelOff) ? 'focus' : els[res.peelOff]?.ifcClass ?? null;
      res.behind = ids.includes(res.behindOn) ? 'focus' : els[res.behindOn]?.ifcClass ?? null;
      return res;
    }, [setup.ids]);
    log('pick at the focus centre (x-ray off): peel on ->', pick.focus, ', peel off ->', pick.focusOff, ', behind-only cut on ->', pick.behind);

    // Hover highlight
    await mode(null, null);
    await setView(view);
    await page.evaluate((id) => window.__xray.renderer.setHoverHighlight(id, [1, 0.2, 0.6]), setup.ids[0]);
    shots.hover = await shot('hover');
    log('hover highlight vs off', JSON.stringify(await diff(page, off, shots.hover)));
    await page.evaluate(() => window.__xray.renderer.setHoverHighlight(null));

    // Both off: identical to the original frame
    await reset();
    const off2 = await shot('off-again');
    log('off again vs off (must be about 0)', JSON.stringify(await diff(page, off, off2)));
    await page.close();
  }
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
