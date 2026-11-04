// Headless check of the WebXR mode with the emulated device iwer (Meta's MIT-licensed WebXR emulation runtime, a dev
// dependency used here only: it is injected into the page by this script and is not part of the app or its bundle).
//   SMOKE_PORT=5411 node bench/smoke-xr.mjs [fzk|synth]
// Steps: detect support, enter VR from the GUI button, check the rig puts the head on the orbit camera, aim the emulated
// right controller at the element under the screen centre and pull the trigger (the element must become the selection),
// squeeze (x-ray toggles), push the thumbstick (a 30 degree snap turn), look at the stereo frame, exit and check that the
// normal renderer is back and the frame loop still runs; then enter AR, place the model, switch the scale to tabletop 1:50.
// Writes bench/xr-*.png and prints PASS / FAIL lines. Exit code 1 on any failure or console error.
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const port = Number(process.env.SMOKE_PORT ?? 5411);
const which = process.argv[2] ?? 'fzk';
const VIEW = { width: 1400, height: 760 };
const SCENES = {
  fzk: { model: 'fzk-haus', pos: [6, 5.5, 13], tgt: [-3.95, -1.8, -4.8] },
  synth: { model: 'synth5k', pos: null, tgt: null },
};
const sc = SCENES[which];

function loadPlaywright() {
  const candidates = [process.env.PLAYWRIGHT_MODULE, resolve(root, 'node_modules/playwright'), '/opt/node-tools/node_modules/playwright', '/opt/node22/lib/node_modules/playwright'].filter(Boolean);
  for (const c of candidates) { try { return createRequire(import.meta.url)(c); } catch { /* next */ } }
  throw new Error('playwright not found; set PLAYWRIGHT_MODULE');
}
const { chromium } = loadPlaywright();
const iwerSrc = readFileSync(resolve(root, 'node_modules/iwer/build/iwer.js'), 'utf8');

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

let failed = false;
function check(name, ok, detail = '') {
  if (!ok) failed = true;
  console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${detail ? ` (${detail})` : ''}`);
}

let browser;
const errors = [];
const helpWarnings = [];
try {
  await waitForServer();
  browser = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const page = await browser.newPage({ viewport: VIEW });
  page.on('console', (m) => {
    if (m.type() === 'error') errors.push(`[error] ${m.text()}`);
    if (m.type() === 'warning' && m.text().startsWith('[help]')) helpWarnings.push(m.text());
    else if (m.type() === 'warning') errors.push(`[warning] ${m.text()}`);
  });
  page.on('pageerror', (e) => errors.push(`[pageerror] ${e.message}`));

  // The emulated device is installed before any page script runs, as a real headset's navigator.xr would be.
  await page.addInitScript({ content: iwerSrc });
  await page.addInitScript({
    content: `(() => {
      const { XRDevice, metaQuest3 } = window.IWER;
      const device = new XRDevice(metaQuest3);
      device.installRuntime({ forceInstall: true });
      device.stereoEnabled = true; // two views side by side, as a headset draws them
      window.__iwer = device;
    })();`,
  });
  await page.goto(`http://127.0.0.1:${port}/?model=${sc.model}&cinematic=off`);
  await page.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: 180000 });
  const startErr = await page.evaluate('window.__xrayError');
  if (startErr) throw new Error(startErr);
  await page.addStyleTag({ content: '#xray-overlay, #xray-message { visibility: hidden !important }' });

  const settle = (ms = 400) => page.evaluate(async (ms) => {
    for (let i = 0; i < 3; i++) await new Promise((r) => requestAnimationFrame(r));
    await new Promise((r) => setTimeout(r, ms));
  }, ms);
  const frames = () => page.evaluate(() => window.__xray.app.frameLog.intervals.length);
  const st = () => page.evaluate(() => window.__xrayXr.state());

  // ---- camera, selection state, support
  const setup = await page.evaluate(async ([pos, tgt]) => {
    const app = window.__xray.app;
    const r = app.renderer;
    if (pos) {
      r.camera.position.set(...pos);
      r.controls.target.set(...tgt);
    } else {
      const b = r.loaded?.geometry.totalBounds?.();
      r.frameAll();
    }
    r.camera.near = 0.1;
    r.camera.updateProjectionMatrix();
    r.controls.update();
    app.clearSelection();
    await new Promise((x) => setTimeout(x, 600));
    return { api: !!window.__xrayXr, support: window.__xrayXr?.state().supported };
  }, [sc.pos, sc.tgt]);
  console.log('setup', JSON.stringify(setup));
  check('xr api present and both modes supported by the emulated device', setup.api && setup.support?.vr === true && setup.support?.ar === true);
  const toolVisible = await page.evaluate(() => !!document.querySelector('.xt-btn-tool[data-tool="xr"]'));
  check('the WebXR tool shows in the strip when supported', toolVisible);
  const folder = await page.evaluate(() => {
    const t = [...document.querySelectorAll('.lil-gui .lil-title')].find((e) => e.textContent.trim() === 'WebXR');
    if (!t) return null;
    const f = t.closest('.lil-gui');
    return [...f.querySelectorAll('.lil-name')].map((n) => n.textContent.trim());
  });
  console.log('WebXR folder controls', JSON.stringify(folder));
  check('WebXR folder has exactly Enter VR, Enter AR, AR scale, XR status, pointer rays', JSON.stringify(folder) === JSON.stringify(['Enter VR', 'Enter AR', 'AR scale', 'XR status', 'pointer rays']));

  // the drawer of the tool: every widget must have a help text (the help layer warns "[help] no help text" otherwise)
  const drawer = await page.evaluate(async () => {
    window.__xrayToolbar.open('xr');
    await new Promise((r) => setTimeout(r, 700));
    const names = [...document.querySelectorAll('.xt-drawer .xt-btn, .xt-drawer .xt-select .xt-lbl, .xt-drawer .xt-check span, .xt-drawer .xt-status')].map((e) => e.textContent.trim());
    return names;
  });
  console.log('drawer widgets', JSON.stringify(drawer));
  check('the drawer has the Enter VR and Enter AR buttons, AR scale, pointer rays and the status line', ['Enter VR', 'Enter AR', 'AR scale', 'pointer rays', 'Leave XR session'].every((n) => drawer.includes(n)));
  await page.screenshot({ path: resolve(here, `xr-${which}-drawer.png`) });
  await page.evaluate(() => window.__xrayToolbar.close());
  await settle(400);

  const before = await page.screenshot({ clip: { x: 300, y: 0, width: 800, height: 760 } });
  const pre = await page.evaluate(() => {
    const app = window.__xray.app;
    const r = app.renderer;
    const id = r.pick(0, 0);
    const d = r.camera.getWorldDirection(new r.camera.position.constructor());
    return { id, pos: r.camera.position.toArray(), dir: d.toArray(), xray: app.settings.xray };
  });
  console.log('element under the screen centre', JSON.stringify(pre));
  check('there is an element under the screen centre', pre.id !== null);

  // ---- enter VR from the GUI button
  const f0 = await frames();
  await page.evaluate(() => {
    const t = [...document.querySelectorAll('.lil-gui .lil-name')].find((e) => e.textContent.trim() === 'Enter VR');
    t.closest('.lil-controller').querySelector('button').click();
  });
  await page.waitForFunction('window.__xray.renderer.renderer.xr.isPresenting === true', null, { timeout: 60000 }).catch(() => {});
  await settle(800);
  const vr = await st();
  console.log('VR state', JSON.stringify(vr));
  check('VR session is presenting', vr.presenting === true && vr.mode === 'vr');
  const camWorld = await page.evaluate(() => window.__xray.renderer.cameraWorldPosition().toArray());
  const d3 = Math.hypot(camWorld[0] - pre.pos[0], camWorld[1] - pre.pos[1], camWorld[2] - pre.pos[2]);
  check('the XR camera starts at the orbit camera position (real scale)', d3 < 0.005 && vr.rig.scale === 1, `distance ${d3.toFixed(3)} m`);
  const f1 = await frames();
  await settle(500);
  const f2 = await frames();
  check('the frame loop runs inside the session (timing stats keep counting)', f2 > f1 + 2, `${f1} -> ${f2}`);
  await page.screenshot({ path: resolve(here, `xr-${which}-vr.png`) });

  // ---- aim the right controller along the orbit view direction and pull the trigger
  const aim = await page.evaluate(([dir]) => {
    const x = window.__xrayXr.state();
    const yaw = x.rig.yaw;
    // world direction -> local direction (undo the rig yaw), then a quaternion that turns -Z onto it
    const c = Math.cos(-yaw), s = Math.sin(-yaw);
    const l = [c * dir[0] + s * dir[2], dir[1], -s * dir[0] + c * dir[2]];
    const ya = Math.atan2(-l[0], -l[2]);
    const pi = Math.asin(l[1]);
    const qy = [0, Math.sin(ya / 2), 0, Math.cos(ya / 2)];
    const qx = [Math.sin(pi / 2), 0, 0, Math.cos(pi / 2)];
    const q = [qy[3] * qx[0] + qy[0] * qx[3] + qy[1] * qx[2] - qy[2] * qx[1], qy[3] * qx[1] - qy[0] * qx[2] + qy[1] * qx[3] + qy[2] * qx[0], qy[3] * qx[2] + qy[0] * qx[1] - qy[1] * qx[0] + qy[2] * qx[3], qy[3] * qx[3] - qy[0] * qx[0] - qy[1] * qx[1] - qy[2] * qx[2]];
    const dev = window.__iwer;
    const hp = dev.position;
    const ctl = dev.controllers.right;
    ctl.position.set(hp.x, hp.y, hp.z);
    ctl.quaternion.set(q[0], q[1], q[2], q[3]);
    return { local: l, q };
  }, [pre.dir]);
  await settle(500);
  const beforeSel = await page.evaluate(() => window.__xray.app.selection);
  await page.evaluate(() => window.__iwer.controllers.right.updateButtonValue('trigger', 1));
  await settle(300);
  await page.evaluate(() => window.__iwer.controllers.right.updateButtonValue('trigger', 0));
  await settle(600);
  const afterSel = await page.evaluate(() => window.__xray.app.selection);
  const vrAfter = await st();
  console.log('aim', JSON.stringify(aim), 'selection before/after', JSON.stringify(beforeSel), JSON.stringify(afterSel), 'select events', vrAfter.selects);
  check('the trigger selects the element under the controller ray', afterSel.length === 1 && afterSel[0] === pre.id, `expected ${pre.id}`);
  await page.screenshot({ path: resolve(here, `xr-${which}-vr-selected.png`) });

  // ---- imaging, peel and behind-only inside the session: imaging and peel fall back (and say so), behind-only and sections draw per eye
  await page.evaluate(() => {
    window.__xrayImaging.set({ style: 'radiograph' });
    window.__xrayViewModes.setPeel({ enabled: true, radius: 0.5, slope: 0.25, animate: false });
    window.__xrayViewModes.setBehind({ enabled: true, frontTreatment: 'cut + cap', offset: 0.2 });
    window.__xraySection.set({ plane: { enabled: true, axis: 'y', offset: 0.5, flip: false }, caps: true });
  });
  const imgFrames0 = await page.evaluate(() => window.__xray.renderer.imagingFrames);
  await settle(1500);
  const modes = await st();
  const imgFrames1 = await page.evaluate(() => window.__xray.renderer.imagingFrames);
  console.log('modes inside the session', JSON.stringify(modes.fallbacks), 'imaging frames', imgFrames0, '->', imgFrames1);
  check('imaging draws no frame inside the session (standard renderer instead) and the status says so', imgFrames1 === imgFrames0 && modes.fallbacks.some((f) => f.includes('imaging radiograph')));
  check('the peel window is reported as off inside the session', modes.fallbacks.some((f) => f.includes('peelback')) && (await page.evaluate(() => window.__xray.renderer.peelPath)) === 'off');
  await page.screenshot({ path: resolve(here, `xr-${which}-vr-modes.png`) });
  await page.evaluate(() => {
    window.__xrayImaging.set({ style: 'standard' });
    window.__xrayViewModes.setPeel({ enabled: false });
    window.__xrayViewModes.setBehind({ enabled: false });
    window.__xraySection.clear();
  });
  await settle(600);

  // ---- squeeze toggles x-ray
  const xr0 = await page.evaluate(() => window.__xray.app.settings.xray);
  await page.evaluate(() => window.__iwer.controllers.right.updateButtonValue('squeeze', 1));
  await settle(300);
  await page.evaluate(() => window.__iwer.controllers.right.updateButtonValue('squeeze', 0));
  await settle(500);
  const xr1 = await page.evaluate(() => window.__xray.app.settings.xray);
  check('squeeze toggles x-ray', xr0 !== xr1, `${xr0} -> ${xr1}`);
  await page.evaluate(() => window.__xray.app.setXray(true));

  // ---- thumbstick snap turn (right controller, push right then release)
  const yaw0 = (await st()).rig.yaw;
  const head0 = await page.evaluate(() => window.__xray.renderer.cameraWorldPosition().toArray());
  await page.evaluate(() => window.__iwer.controllers.right.updateAxes('thumbstick', 1, 0));
  await settle(500);
  await page.evaluate(() => window.__iwer.controllers.right.updateAxes('thumbstick', 0, 0));
  await settle(500);
  const yaw1 = (await st()).rig.yaw;
  const head1 = await page.evaluate(() => window.__xray.renderer.cameraWorldPosition().toArray());
  const dyaw = Math.atan2(Math.sin(yaw1 - yaw0), Math.cos(yaw1 - yaw0)) * 180 / Math.PI;
  check('the thumbstick snaps the view by 30 degrees once', Math.abs(Math.abs(dyaw) - 30) < 0.5, `${dyaw.toFixed(1)} degrees`);
  check('a snap turn keeps the head where it was', Math.hypot(head1[0] - head0[0], head1[1] - head0[1], head1[2] - head0[2]) < 0.02);

  // ---- walking with the left stick moves the rig
  const p0 = (await st()).rig.position;
  await page.evaluate(() => window.__iwer.controllers.left.updateAxes('thumbstick', 0, -1));
  await settle(700);
  await page.evaluate(() => window.__iwer.controllers.left.updateAxes('thumbstick', 0, 0));
  await settle(300);
  const p1 = (await st()).rig.position;
  const walked = Math.hypot(p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]);
  check('the left stick walks', walked > 0.3, `${walked.toFixed(2)} m`);

  // ---- sightlines run from the XR camera (the head moved, so the camera-based Algorithm 2 must have run again)
  const slBefore = await page.evaluate(() => window.__xray.app.stats.sightlinesCount);
  await page.evaluate(() => window.__iwer.controllers.left.updateAxes('thumbstick', 0, -1));
  await settle(500);
  await page.evaluate(() => window.__iwer.controllers.left.updateAxes('thumbstick', 0, 0));
  await settle(300);
  const slAfter = await page.evaluate(() => window.__xray.app.stats.sightlinesCount);
  check('sightlines run again from the moving XR camera', slAfter > slBefore, `${slBefore} -> ${slAfter}`);

  // ---- passes that do not work with the stereo target are off and said so
  const fb = (await st()).fallbacks;
  console.log('fallbacks', JSON.stringify(fb));
  check('the status names the passes that fall back', Array.isArray(fb) && fb.length > 0);

  // ---- exit
  await page.evaluate(() => window.__xrayXr.exit());
  await page.waitForFunction('window.__xray.renderer.renderer.xr.isPresenting === false', null, { timeout: 30000 });
  await settle(900);
  const out = await page.evaluate(() => {
    const r = window.__xray.renderer;
    return {
      presenting: r.renderer.xr.isPresenting, enabled: r.renderer.xr.enabled, parent: r.camera.parent === null, scale: r.camera.scale.toArray(),
      controls: r.controls.enabled, pos: r.camera.position.toArray(), near: r.camera.near, state: window.__xrayXr.state(),
    };
  });
  console.log('after exit', JSON.stringify({ ...out, state: undefined }));
  check('exit: normal renderer restored (xr off, no rig, scale 1, orbit controls on)', !out.presenting && !out.enabled && out.parent && out.scale.every((v) => v === 1) && out.controls && out.state.mode === null);
  check('exit: the camera is back at the orbit position', Math.hypot(out.pos[0] - pre.pos[0], out.pos[1] - pre.pos[1], out.pos[2] - pre.pos[2]) < 1e-6);
  const g1 = await frames();
  await settle(600);
  const g2 = await frames();
  check('exit: the frame loop still runs', g2 > g1 + 2, `${g1} -> ${g2}`);
  await page.evaluate(() => window.__xray.app.clearSelection());
  // The ghost alphas ease toward the sightline result of the orbit camera again: wait until they have settled.
  await page.evaluate(async () => { const app = window.__xray.app; for (let i = 0; i < 600 && !app.controller.converged; i++) await new Promise((r) => setTimeout(r, 50)); });
  await settle(1500);
  const after = await page.screenshot({ clip: { x: 300, y: 0, width: 800, height: 760 }, path: resolve(here, `xr-${which}-after.png`) });
  const identical = await page.evaluate(async ([a, b]) => {
    const load = async (b64) => { const bmp = await createImageBitmap(await (await fetch('data:image/png;base64,' + b64)).blob()); const c = new OffscreenCanvas(bmp.width, bmp.height); const g = c.getContext('2d'); g.drawImage(bmp, 0, 0); return g.getImageData(0, 0, bmp.width, bmp.height).data; };
    const A = await load(a), B = await load(b);
    let diff = 0; for (let i = 0; i < A.length; i++) if (A[i] !== B[i]) diff++;
    return diff;
  }, [before.toString('base64'), after.toString('base64')]);
  check('exit: the picture is pixel identical to the one before entering', identical === 0, `${identical} differing channel values`);

  // ---- AR: place with a select, then switch to tabletop 1:50
  await page.evaluate(() => {
    const t = [...document.querySelectorAll('.lil-gui .lil-name')].find((e) => e.textContent.trim() === 'Enter AR');
    t.closest('.lil-controller').querySelector('button').click();
  });
  await page.waitForFunction('window.__xray.renderer.renderer.xr.isPresenting === true', null, { timeout: 60000 }).catch(() => {});
  await settle(800);
  const ar0 = await st();
  console.log('AR state', JSON.stringify(ar0));
  check('AR session is presenting and waits for the placement', ar0.presenting && ar0.mode === 'ar' && ar0.placed === false);
  await page.screenshot({ path: resolve(here, `xr-${which}-ar-1to1.png`) });
  await page.evaluate(() => window.__iwer.controllers.right.updateButtonValue('trigger', 1));
  await settle(300);
  await page.evaluate(() => window.__iwer.controllers.right.updateButtonValue('trigger', 0));
  await settle(500);
  const ar1 = await st();
  check('a select places the model', ar1.placed === true, JSON.stringify(ar1.rig));
  await page.evaluate(() => window.__xrayXr.setArScale('tabletop 1:50'));
  await settle(700);
  const ar2 = await st();
  check('tabletop 1:50 scales the viewer by 50 (the model looks 50 times smaller)', ar2.rig.scale === 50 && ar2.arScale === 'tabletop 1:50', JSON.stringify(ar2.rig));
  await page.screenshot({ path: resolve(here, `xr-${which}-ar-tabletop.png`) });
  await page.evaluate(() => window.__xrayXr.exit());
  await page.waitForFunction('window.__xray.renderer.renderer.xr.isPresenting === false', null, { timeout: 30000 });
  await settle(500);
  check('AR exit restores the renderer', await page.evaluate(() => { const r = window.__xray.renderer; return !r.renderer.xr.enabled && r.camera.parent === null && r.camera.scale.x === 1; }));
  const h1 = await frames();
  await settle(600);
  check('the frame loop runs after AR exit', (await frames()) > h1 + 2);
} catch (e) {
  console.error(e);
  failed = true;
} finally {
  await browser?.close();
  vite.kill();
}
check('every control of the WebXR folder and drawer has a help text', helpWarnings.length === 0, helpWarnings.join(' | '));
if (errors.length) { console.log('\nconsole problems:'); errors.forEach((e) => console.log(' ', e)); failed = true; }
else console.log('\nno console errors or warnings');
process.exit(failed ? 1 : 0);
