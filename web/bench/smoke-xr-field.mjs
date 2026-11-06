// Headless check of field AR with the emulated Meta Quest 3 of iwer (dev dependency, injected by this script only) and a
// stub synthetic environment: the hit test of every ray is its crossing with one horizontal plane whose height the script
// sets per target (window.__semPlaneY), so the "real" points are known exactly in iwer's global frame.
//   SMOKE_PORT=5652 node bench/smoke-xr-field.mjs
// The true site transform maps iwer's global frame onto the model (yaw 0.6 rad plus a shift). Steps: pick a model point in the
// normal view; enter field AR from the GUI; the phone panel is there; tap 3 room points with the controller (exact), check the
// recovered transform at 2 check points; register again with 1 cm tap noise and report the accuracy; anchor held; looks; the
// storey cut (walk up a storey); tap an element (card and clearance); nudge; save the site; exit (pixel identical normal
// view); second session restores the site from its persistent anchor, snapshot, exit (BCF topic); third session without the
// anchors feature (re-tap fallback); USDZ export and the AR Quick Look link path; the QR link.
// Writes bench/xr-field-*.png and prints PASS / FAIL lines. Exit code 1 on any failure or console error.
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const port = Number(process.env.SMOKE_PORT ?? 5652);
const VIEW = { width: 1400, height: 760 };

function loadPlaywright() {
  const candidates = [process.env.PLAYWRIGHT_MODULE, resolve(root, 'node_modules/playwright'), '/opt/node-tools/node_modules/playwright', '/opt/node22/lib/node_modules/playwright', 'playwright'].filter(Boolean);
  for (const c of candidates) { try { return createRequire(import.meta.url)(c); } catch { /* next */ } }
  throw new Error('playwright not found; set PLAYWRIGHT_MODULE');
}
const { chromium } = loadPlaywright();
const iwerSrc = readFileSync(resolve(root, 'node_modules/iwer/build/iwer.js'), 'utf8');

const external = process.env.SMOKE_EXTERNAL === '1';
const vite = external ? null : spawn(resolve(root, 'node_modules/.bin/vite'), ['--config', resolve(here, 'vite.smoke.config.mjs'), '--host', '127.0.0.1', '--port', String(port), '--strictPort'], { cwd: root, stdio: ['ignore', 'pipe', 'pipe'] });
let viteLog = '';
vite?.stdout.on('data', (d) => (viteLog += d));
vite?.stderr.on('data', (d) => (viteLog += d));
async function waitForServer() {
  for (let i = 0; i < 150; i++) {
    try { const r = await fetch(`http://127.0.0.1:${port}/`); if (r.ok) return; } catch { /* retry */ }
    await new Promise((r) => setTimeout(r, 200));
  }
  throw new Error('vite did not start:\n' + viteLog);
}

let failed = false;
function check(name, ok, detail = '') {
  if (!ok) failed = true;
  console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${detail ? ` (${detail})` : ''}`);
}

// ---- the true site transform: model = Ry(THETA) * global + SHIFT (the ground floor of fzk-haus lands on iwer's floor y = 0)
const THETA = 0.6;
const SHIFT = [1.5, -3.0588, -0.8];
const rotY = (p, a) => [Math.cos(a) * p[0] + Math.sin(a) * p[2], p[1], -Math.sin(a) * p[0] + Math.cos(a) * p[2]];
const toModel = (g) => { const r = rotY(g, THETA); return [r[0] + SHIFT[0], r[1] + SHIFT[1], r[2] + SHIFT[2]]; };
const toGlobal = (m) => rotY([m[0] - SHIFT[0], m[1] - SHIFT[1], m[2] - SHIFT[2]], -THETA);
const dist = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
// model points: two on the ground floor, one on the upper floor (2.7 m up)
const MODEL_PTS = [[-4.2, -3.0588, -3.4], [4.1, -3.0588, -2.2], [0.9, -0.3588, 3.1]];
const CHECK_G = [[1.0, 0, 1.5], [-6, 0, -5]];

let browser;
const errors = [];
const helpWarnings = [];
try {
  if (!external) await waitForServer();
  browser = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const ctx = await browser.newContext({ viewport: VIEW, acceptDownloads: true });
  const page = await ctx.newPage();
  page.setDefaultTimeout(180000);
  page.on('console', (m) => {
    if (m.type() === 'error') errors.push(`[error] ${m.text()}`);
    if (m.type() === 'warning' && m.text().startsWith('[help]')) { if (/WebXR/.test(m.text())) helpWarnings.push(m.text()); }
    else if (m.type() === 'warning' && !/USDZExporter/.test(m.text())) errors.push(`[warning] ${m.text()}`);
  });
  page.on('pageerror', (e) => errors.push(`[pageerror] ${e.message}`));

  await page.addInitScript({ content: iwerSrc });
  await page.addInitScript({
    content: `(() => {
      const { XRDevice, metaQuest3 } = window.IWER;
      const device = new XRDevice(metaQuest3);
      class StubSem {
        constructor() { this.version = 'stub'; this.planesVisible = false; this.boundingBoxesVisible = false; this.meshesVisible = false;
          this.trackedPlanes = new Set(); this.trackedMeshes = new Set(); this.environmentCanvas = document.createElement('canvas'); this.environmentCanvas.style.display = 'none'; }
        render() {}
        loadEnvironment() {}
        async loadDefaultEnvironment() {}
        deleteAll() {}
        computeDepthBuffer() { return null; }
        computeHitTestResults(m) {
          const o = [m[12], m[13], m[14]];
          const d = [-m[8], -m[9], -m[10]];
          const y = window.__semPlaneY ?? 0;
          if (Math.abs(d[1]) < 1e-9) return [];
          const t = (y - o[1]) / d[1];
          if (!(t > 0)) return [];
          return [new Float32Array([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, o[0] + d[0] * t, y, o[2] + d[2] * t, 1])];
        }
      }
      device.installSEM(StubSem);
      device.installRuntime({ forceInstall: true });
      device.stereoEnabled = true;
      window.__iwer = device;
    })();`,
  });
  await page.goto(`http://127.0.0.1:${port}/?model=fzk-haus&cinematic=off`);
  await page.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: 180000 });
  const startErr = await page.evaluate('window.__xrayError');
  if (startErr) throw new Error(startErr);
  await page.addStyleTag({ content: '#xray-overlay, #xray-message { visibility: hidden !important }' });
  await page.evaluate(() => { for (const k of Object.keys(localStorage)) if (k.startsWith('xray.xr.') || k.includes('anchor')) localStorage.removeItem(k); });

  const settle = (ms = 400) => page.evaluate(async (ms) => {
    for (let i = 0; i < 3; i++) await new Promise((r) => requestAnimationFrame(r));
    await new Promise((r) => setTimeout(r, ms));
  }, ms);
  const st = () => page.evaluate(() => window.__xrayXr.state());
  const fst = async () => (await st()).field;
  const act = (a, arg) => page.evaluate(([a, arg]) => {
    const b = document.querySelector(`#xray-xr-field button[data-act="${arg ? `${a}:${arg}` : a}"]`);
    if (!b) throw new Error(`no panel button ${a} ${arg ?? ''}`);
    b.click();
  }, [a, arg]);
  /** Aim the right controller from where it is at a global point (with the plane of the stub environment at its height). */
  const aim = (g) => page.evaluate((g) => {
    window.__semPlaneY = g[1];
    const ctl = window.__iwer.controllers.right;
    const p = ctl.position;
    const d = [g[0] - p.x, g[1] - p.y, g[2] - p.z];
    const l = Math.hypot(...d);
    const u = d.map((v) => v / l);
    const ya = Math.atan2(-u[0], -u[2]);
    const pi = Math.asin(u[1]);
    const qy = [0, Math.sin(ya / 2), 0, Math.cos(ya / 2)];
    const qx = [Math.sin(pi / 2), 0, 0, Math.cos(pi / 2)];
    const q = [qy[3] * qx[0] + qy[0] * qx[3] + qy[1] * qx[2] - qy[2] * qx[1], qy[3] * qx[1] - qy[0] * qx[2] + qy[1] * qx[3] + qy[2] * qx[0], qy[3] * qx[2] + qy[0] * qx[1] - qy[1] * qx[0] + qy[2] * qx[3], qy[3] * qx[3] - qy[0] * qx[0] - qy[1] * qx[1] - qy[2] * qx[2]];
    ctl.quaternion.set(q[0], q[1], q[2], q[3]);
  }, g);
  const trigger = async () => {
    await page.evaluate(() => window.__iwer.controllers.right.updateButtonValue('trigger', 1));
    await settle(250);
    await page.evaluate(() => window.__iwer.controllers.right.updateButtonValue('trigger', 0));
    await settle(350);
  };
  const tapReal = async (g) => { await aim(g); await settle(350); await trigger(); };
  /** World point the app sees at a global point: aim there and map the hit (local) through the rig. */
  const seen = async (g) => {
    await aim(g);
    await settle(450);
    return page.evaluate(() => {
      const s = window.__xrayXr.state();
      const h = s.field.lastHit;
      if (!h) return null;
      const r = s.rig;
      const c = Math.cos(r.yaw), n = Math.sin(r.yaw);
      return [r.position[0] + c * h[0] + n * h[2], r.position[1] + h[1], r.position[2] - n * h[0] + c * h[2]];
    });
  };
  const enterFieldFromGui = async () => {
    await page.evaluate(() => {
      const t = [...document.querySelectorAll('.lil-gui .lil-name')].find((e) => e.textContent.trim() === 'Enter field AR');
      t.closest('.lil-controller').querySelector('button').click();
    });
    await page.waitForFunction('window.__xray.renderer.renderer.xr.isPresenting === true', null, { timeout: 60000 }).catch(() => {});
    await settle(900);
  };
  const exitSession = async () => {
    await page.evaluate(() => window.__xrayXr.exit());
    await page.waitForFunction('window.__xray.renderer.renderer.xr.isPresenting === false', null, { timeout: 30000 });
    await settle(700);
  };

  // ---- normal view: camera, the drawer, a model point picked with a click
  await page.evaluate(async () => {
    const r = window.__xray.renderer;
    r.camera.position.set(6, 5.5, 13);
    r.controls.target.set(-3.95, -1.8, -4.8);
    r.camera.near = 0.1;
    r.camera.updateProjectionMatrix();
    r.controls.update();
    window.__xray.app.clearSelection();
    await new Promise((x) => setTimeout(x, 600));
  });
  const drawer = await page.evaluate(async () => {
    window.__xrayToolbar.open('xr');
    await new Promise((r) => setTimeout(r, 700));
    return [...document.querySelectorAll('.xt-drawer .xt-btn, .xt-drawer .xt-select .xt-lbl, .xt-drawer .xt-check span, .xt-drawer .xt-slider .xt-lbl, .xt-drawer .xt-sec')].map((e) => e.textContent.trim());
  });
  console.log('drawer', JSON.stringify(drawer));
  check('the drawer has the field AR section and the iPhone section', ['Field AR on site', 'Enter field AR', 'Pick model points', 'field look', 'cut radius (m)', 'storey cut', 'Export site', 'Import site', 'iPhone and iPad', 'Download USDZ', 'Share link as QR'].every((n) => drawer.includes(n)));
  await page.evaluate(() => [...document.querySelectorAll('.xt-drawer .xt-btn')].find((b) => b.textContent.trim() === 'Pick model points').click());
  const box = await page.evaluate(() => { const r = window.__xray.app.canvas.getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; });
  await page.mouse.click(box.x, box.y);
  await settle(300);
  const draft1 = await page.evaluate(() => window.__xrayXr.field.draft.map((p) => [...p]));
  check('a click in pick mode adds a model point on the surface', draft1.length === 1 && draft1[0].every(Number.isFinite), JSON.stringify(draft1));
  await page.screenshot({ path: resolve(here, 'xr-field-pick.png') });
  await page.evaluate(() => [...document.querySelectorAll('.xt-drawer .xt-btn')].find((b) => b.textContent.trim() === 'Pick model points').click());
  // the field test uses known model points
  await page.evaluate((pts) => { window.__xrayXr.field.clearDraft(); for (const p of pts) window.__xrayXr.field.addModelPoint(p); }, MODEL_PTS);
  const qrSvg = await page.evaluate(async () => {
    [...document.querySelectorAll('.xt-drawer .xt-btn')].find((b) => b.textContent.trim() === 'Share link as QR').click();
    await new Promise((r) => setTimeout(r, 200));
    const q = document.querySelector('.xt-drawer .xr-qr');
    return q && !q.hidden ? q.innerHTML.slice(0, 80) : null;
  });
  check('Share link as QR shows an SVG code', !!qrSvg && qrSvg.startsWith('<svg'));
  await page.evaluate(() => window.__xrayToolbar.close());
  await page.mouse.move(2, 2); // no hover highlight from the pick click in the reference picture (a session ends with no hover)
  await page.evaluate(() => { window.__xray.app.hoverId = null; window.__xray.app.clearSelection(); });
  await page.evaluate(async () => { const app = window.__xray.app; for (let i = 0; i < 600 && !app.controller.converged; i++) await new Promise((r) => setTimeout(r, 50)); });
  await settle(1500);
  const before = await page.screenshot({ clip: { x: 300, y: 0, width: 800, height: 760 } });
  const pre = await page.evaluate(() => ({
    styles: window.__xray.app.controller.settings.classStyles,
    section: JSON.stringify(window.__xraySection.config),
  }));
  await page.evaluate(() => { window.__preStyles = window.__xray.app.controller.settings.classStyles; });

  // ---- session 1: enter, the panel, register with exact taps
  await enterFieldFromGui();
  let s = await st();
  console.log('field state', JSON.stringify({ mode: s.mode, presenting: s.presenting, field: { ...s.field, pairs: s.field?.pairs.length } }));
  check('field AR session presents (immersive-ar) and waits for the room points', s.presenting && s.mode === 'field' && s.field?.step === 'real' && s.field.pairs.length === 3);
  check('the hit test runs from the controllers (stub environment)', s.field.hitTest.pointers >= 1 || s.field.hitTest.centre, JSON.stringify(s.field.hitTest));
  const panel = await page.evaluate(() => {
    const r = document.getElementById('xray-xr-field');
    if (!r || r.hidden) return null;
    const btns = [...r.querySelectorAll('button')];
    const small = btns.filter((b) => { const q = b.getBoundingClientRect(); return q.width > 0 && (q.height < 44 || q.width < 44); }).map((b) => b.dataset.act);
    return { buttons: btns.map((b) => b.dataset.act), small, z: getComputedStyle(r).zIndex };
  });
  console.log('panel', JSON.stringify(panel));
  check('the phone panel (DOM overlay root) shows with register, nudge, look, cut, snapshot and exit buttons', !!panel && ['mark', 'undo', 'reregister', 'floor', 'save', 'view:x-ray', 'view:ghosted', 'view:full', 'cut', 'nudge:left', 'nudge:cw', 'snapshot', 'exit'].every((a) => panel.buttons.includes(a)));
  check('the visible panel buttons are at least 44 px touch targets', !!panel && panel.small.length === 0, JSON.stringify(panel?.small));
  check('the emulated headset has no dom-overlay: the in-scene text panel is used', s.field.domOverlay === null && (await page.evaluate(() => !!window.__xrayXr.manager.rigObject.getObjectByName('xray-xr-hud')?.visible)));
  await page.screenshot({ path: resolve(here, 'xr-field-panel.png') });

  for (const m of MODEL_PTS) await tapReal(toGlobal(m));
  s = await st();
  console.log('after 3 taps', JSON.stringify({ step: s.field.step, registered: s.field.registered, residuals: s.field.residuals, rig: s.rig }));
  check('3 room taps register the model (keep vertical)', s.field.registered && s.field.step === 'done');
  check('exact taps: residuals below 1 mm', s.field.residuals.length === 3 && Math.max(...s.field.residuals) < 0.001, s.field.residuals.map((r) => (r * 1000).toFixed(3) + ' mm').join(', '));
  const checks1 = [];
  for (const g of CHECK_G) { const w = await seen(g); checks1.push(w ? dist(w, toModel(g)) : Infinity); }
  check('the recovered transform puts 2 check points (2 m and 9 m away) on the model within 1 mm', checks1.every((e) => e < 0.001), checks1.map((e) => (e * 1000).toFixed(3) + ' mm').join(', '));

  // ---- register again with 1 cm tap noise (a fixed pattern) and report the accuracy
  await act('reregister');
  await settle(300);
  const noise = [[0.008, 0, -0.006], [-0.005, 0, 0.009], [0.007, 0, 0.004]];
  for (let i = 0; i < 3; i++) { const g = toGlobal(MODEL_PTS[i]); await tapReal([g[0] + noise[i][0], g[1], g[2] + noise[i][2]]); }
  s = await st();
  const checks2 = [];
  for (const g of CHECK_G) { const w = await seen(g); checks2.push(w ? dist(w, toModel(g)) : Infinity); }
  console.log(`ACCURACY 1 cm tap noise: residuals ${s.field.residuals.map((r) => (r * 100).toFixed(2)).join(', ')} cm, rms ${(s.field.rms * 100).toFixed(2)} cm; check points ${checks2.map((e) => (e * 100).toFixed(2)).join(', ')} cm`);
  check('noisy taps: registered, residuals and rms shown, check points within 3 cm', s.field.registered && s.field.rms > 0.001 && s.field.rms < 0.02 && checks2.every((e) => e < 0.03));
  await settle(800);
  s = await st();
  check('a WebXR anchor holds the registration', s.field.anchor === 'tracked', s.field.anchor);

  // ---- looks
  await act('view', 'x-ray');
  await settle(500);
  const xr = await page.evaluate(() => { const c = window.__xray.app.controller; const st = c.settings.classStyles; return { wall: st.IfcWallStandardCase?.hidden, slab: st.IfcSlab?.hidden, view: window.__xrayXr.state().field.appliedView }; });
  check('look x-ray hides everything but the services (fzk-haus has none: walls and slabs hidden)', xr.view === 'x-ray' && xr.wall === true && xr.slab === true, JSON.stringify(xr));
  await act('view', 'ghosted');
  await settle(500);
  const gh = await page.evaluate(() => { const st = window.__xray.app.controller.settings.classStyles; return { wall: st.IfcWallStandardCase?.alphaMax, door: st.IfcDoor?.alphaMax }; });
  check('look ghosted: walls nearly invisible (0.06), doors faint (0.2)', gh.wall === 0.06 && gh.door === 0.2, JSON.stringify(gh));
  await page.screenshot({ path: resolve(here, 'xr-field-ghosted.png') });
  await act('view', 'full');
  await settle(500);
  check('look full: the user styles are back', await page.evaluate(() => window.__xray.app.controller.settings.classStyles === window.__preStyles));

  // ---- the storey cut
  await settle(500);
  s = await st();
  const levels = { eg: -3.058846, dg: 2.7 - 3.058846 }; // fzk-haus originShift z
  console.log('cut', JSON.stringify(s.field.cut), s.field.storey, 'feet', s.field.feetY);
  check('the cut box: storey Erdgeschoss, top at the floor of the next storey, bottom 1 m below this floor, 6 m around the head', s.field.storey === 'Erdgeschoss' && s.field.cut && Math.abs(s.field.cut.max[1] - levels.dg) < 1e-6 && Math.abs(s.field.cut.min[1] - (levels.eg - 1)) < 1e-6 && Math.abs(s.field.cut.max[0] - s.field.cut.min[0] - 12) < 1e-6);
  const secBox = await page.evaluate(() => ({ ...window.__xraySection.config.box, planes: window.__xraySection.planes().length }));
  check('the cut goes through the section box (6 planes)', secBox.enabled && secBox.planes === 6);
  await page.evaluate(() => { const p = window.__iwer.position; window.__iwer.position.set(p.x, p.y + 2.7, p.z); });
  await settle(900);
  s = await st();
  check('walking up a storey moves the cut: storey Dachgeschoss, no ceiling cut (top storey)', s.field.storey === 'Dachgeschoss' && s.field.cut && s.field.cut.min[1] > levels.dg - 1.01 && s.field.cut.max[1] > 3, `${s.field.storey} ${JSON.stringify(s.field.cut)}`);
  await page.evaluate(() => { const p = window.__iwer.position; window.__iwer.position.set(p.x, p.y - 2.7, p.z); });
  await settle(600);
  await act('cut');
  await settle(500);
  check('the cut switch turns it off and gives the section back', (await fst()).cut === null && !(await page.evaluate(() => window.__xraySection.config.box.enabled)));
  await act('cut');
  await settle(400);

  // ---- tap an element: card and clearance (look full: walls are not click-through)
  const target = await page.evaluate(() => {
    const els = window.__xray.app.loaded.model.elements;
    const w = els.find((e) => e.ifcClass === 'IfcWallStandardCase' && e.bounds[4] - e.bounds[1] > 2);
    return { id: w.id, centre: [(w.bounds[0] + w.bounds[3]) / 2, (w.bounds[1] + w.bounds[4]) / 2, (w.bounds[2] + w.bounds[5]) / 2] };
  });
  await page.evaluate(() => (window.__semPlaneY = -100));
  const tg = toGlobal(target.centre);
  await aim([tg[0], tg[1], tg[2]]);
  await settle(400);
  await trigger();
  s = await st();
  const card = await page.evaluate(() => { const c = document.querySelector('#xray-xr-field .xf-card'); return c && !c.hidden ? c.textContent : null; });
  console.log('selected', JSON.stringify(s.field.selected), 'clearance', JSON.stringify(s.field.clearance), 'card', card);
  check('a trigger on a wall selects it and the card shows its name and clearance', s.field.selected !== null && !!card && /clearance from the device/.test(card) && s.field.clearance.device > 0 && Number.isFinite(s.field.clearance.point));
  await page.screenshot({ path: resolve(here, 'xr-field-selected.png') });

  // ---- nudge
  const r0 = (await st()).rig;
  await act('nudge', 'right');
  await settle(300);
  const r1 = (await st()).rig;
  const moved = Math.hypot(r1.position[0] - r0.position[0], r1.position[2] - r0.position[2]);
  check('a nudge moves the model by 1 cm', Math.abs(moved - 0.01) < 1e-6 && r1.yaw === r0.yaw, `${(moved * 100).toFixed(3)} cm`);
  await act('nudge', 'ccw');
  await settle(300);
  const r2 = (await st()).rig;
  check('a turn nudge turns the model by 0.5 degrees', Math.abs(Math.abs(r2.yaw - r1.yaw) * 180 / Math.PI - 0.5) < 1e-6);
  await act('nudge', 'cw');
  await act('nudge', 'left');
  await settle(300);

  // ---- save the site (persistent anchor where the browser offers one; iwer does, like Quest Browser)
  await act('save');
  await settle(800);
  s = await st();
  const saved = await page.evaluate(() => window.__xrayXr.field.sites());
  check('Save site stores the registration with a persistent anchor handle', saved.length === 1 && !!saved[0].anchor?.handle && s.field.anchorHandle === saved[0].anchor.handle, JSON.stringify(saved[0]?.anchor));
  const rigSaved = (await st()).rig;

  // ---- exit: the normal view is back, pixel identical
  await exitSession();
  const out = await page.evaluate(() => {
    const r = window.__xray.renderer;
    return { enabled: r.renderer.xr.enabled, parent: r.camera.parent === null, styles: window.__xray.app.controller.settings.classStyles === window.__preStyles, section: JSON.stringify(window.__xraySection.config), panel: !!document.getElementById('xray-xr-field')?.isConnected };
  });
  check('exit: renderer, camera, class styles and section settings restored; the panel removed', !out.enabled && out.parent && out.styles && out.section === pre.section && !out.panel, JSON.stringify({ ...out, section: out.section === pre.section }));
  await page.evaluate(() => window.__xray.app.clearSelection());
  await page.evaluate(async () => { const app = window.__xray.app; for (let i = 0; i < 600 && !app.controller.converged; i++) await new Promise((r) => setTimeout(r, 50)); });
  await settle(1500);
  const after = await page.screenshot({ clip: { x: 300, y: 0, width: 800, height: 760 }, path: resolve(here, 'xr-field-after.png') });
  const diff = await page.evaluate(async ([a, b]) => {
    const load = async (b64) => { const bmp = await createImageBitmap(await (await fetch('data:image/png;base64,' + b64)).blob()); const c = new OffscreenCanvas(bmp.width, bmp.height); const g = c.getContext('2d'); g.drawImage(bmp, 0, 0); return g.getImageData(0, 0, bmp.width, bmp.height).data; };
    const A = await load(a), B = await load(b);
    let d = 0; for (let i = 0; i < A.length; i++) if (A[i] !== B[i]) d++;
    return d;
  }, [before.toString('base64'), after.toString('base64')]);
  check('exit: the picture is pixel identical to the one before entering', diff === 0, `${diff} differing channel values`);

  // ---- session 2: restore from the persistent anchor, snapshot, BCF topic on exit
  const topics0 = await page.evaluate(() => window.__xrayBcf?.topics.length ?? -1);
  await page.evaluate(() => window.__iwer.position.set(0.7, 1.6, -0.4)); // stand somewhere else
  await enterFieldFromGui();
  await settle(900);
  s = await st();
  console.log('restored', JSON.stringify({ restoredFrom: s.field.restoredFrom, anchor: s.field.anchor, registered: s.field.registered, rig: s.rig, saved: rigSaved }));
  check('session 2 restores the saved site from its persistent anchor (no taps)', s.field.registered && s.field.anchor === 'tracked' && !!s.field.restoredFrom);
  const checks3 = [];
  for (const g of CHECK_G) { const w = await seen(g); checks3.push(w ? dist(w, toModel(g)) : Infinity); }
  check('the restored registration keeps the check points within 3 cm (as saved, with the noisy taps and the nudges undone)', checks3.every((e) => e < 0.03), checks3.map((e) => (e * 100).toFixed(2) + ' cm').join(', '));
  await act('snapshot');
  await settle(900);
  s = await st();
  const note = await page.evaluate(() => { const n = window.__xrayXr.manager.field?.notes[0]; return n ? { png: n.png?.slice(0, 22), len: n.png?.length ?? 0, w: n.width, h: n.height, head: n.head } : null; });
  check('Snapshot keeps the rendered overlay (PNG) and the head pose', s.field.notes === 1 && !!note && note.png === 'data:image/png;base64,' && note.len > 2000 && note.w > 0, JSON.stringify(note && { ...note, head: undefined }));
  await page.screenshot({ path: resolve(here, 'xr-field-restored.png') });
  await exitSession();
  const topics1 = await page.evaluate(() => window.__xrayBcf?.topics.length ?? -1);
  const lastTopic = await page.evaluate(() => { const t = window.__xrayBcf?.topics.at(-1); return t ? { title: t.title, labels: t.labels, pin: !!t.pin, vp: t.viewpoints.length } : null; });
  check('the snapshot became a BCF topic with a viewpoint at the head pose', topics0 >= 0 && topics1 === topics0 + 1 && /^Field note 1/.test(lastTopic?.title ?? '') && lastTopic.vp === 1, JSON.stringify(lastTopic));
  check('the notes stay downloadable', await page.evaluate(() => window.__xrayXr.field.notes().length === 1));

  // ---- session 3: no anchors feature: the saved site asks for the 3 points again
  await page.evaluate(() => { const f = window.__iwer.supportedFeatures; const i = f.indexOf('anchors'); if (i >= 0) f.splice(i, 1); });
  await enterFieldFromGui();
  s = await st();
  check('without anchors the saved site falls back to re-tapping its points', s.field.step === 'real' && !s.field.registered && s.field.pairs.length === 3 && /again/.test(s.status + JSON.stringify(s.field)), s.field.instruction);
  const g3 = await page.evaluate(() => [window.__iwer.position.x, window.__iwer.position.y, window.__iwer.position.z]);
  for (const m of MODEL_PTS) await tapReal(toGlobal(m));
  await settle(600);
  s = await st();
  check('re-tapped: registered, anchor reported as unsupported', s.field.registered && s.field.anchor === 'unsupported' && Math.max(...s.field.residuals) < 0.001, `${s.field.anchor} ${JSON.stringify(g3)}`);
  await exitSession();
  check('exit after the fallback session restores the renderer', await page.evaluate(() => { const r = window.__xray.renderer; return !r.renderer.xr.enabled && r.camera.parent === null; }));

  // ---- USDZ for AR Quick Look
  const usdz = await page.evaluate(async () => {
    const r = await window.__xrayXr.usdz.build();
    return { n: r.bytes.length, pk: r.bytes[0] === 0x50 && r.bytes[1] === 0x4b, elements: r.elements, meshes: r.meshes, supported: window.__xrayXr.usdz.supported };
  });
  console.log('usdz', JSON.stringify(usdz));
  check('USDZ export of the visible model (zip, elements, materials)', usdz.pk && usdz.n > 10000 && usdz.elements > 50 && usdz.meshes >= 2);
  const dl = page.waitForEvent('download', { timeout: 30000 }).catch(() => null);
  const url0 = page.url();
  await page.evaluate(() => window.__xrayXr.usdz.open());
  const d = await dl;
  await settle(300);
  check('the AR Quick Look link (rel=ar) downloads the file in Chromium and keeps the page', !!d && /\.usdz$/.test(d.suggestedFilename()) && page.url() === url0 && usdz.supported === false, d?.suggestedFilename());
} catch (e) {
  console.error(e);
  failed = true;
} finally {
  await browser?.close();
  vite?.kill();
}
check('every control of the WebXR folder and drawer has a help text', helpWarnings.length === 0, helpWarnings.join(' | '));
if (errors.length) { console.log('\nconsole problems:'); errors.forEach((e) => console.log(' ', e)); failed = true; }
else console.log('\nno console errors or warnings');
process.exit(failed ? 1 : 0);
