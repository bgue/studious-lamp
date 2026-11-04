// Headless smoke test for the right-hand parameter dock and the params export:
// starts vite (bench/vite.smoke.config.mjs), loads /?model=building at 1600x900 and checks the layout
// (dock 300 px, canvas = viewport - sidebar - dock), `]` collapse to the 28 px rail, canvas growth, persistence
// across a reload, lil-gui scrolling inside the dock, window.__xrayParams.collect() keys and a share-URL round trip.
// Screenshots: bench/smoke-dock-open.png, bench/smoke-dock-closed.png.
// Usage: node bench/smoke-dock.mjs
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const port = Number(process.env.SMOKE_PORT ?? 5197);

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
  for (let i = 0; i < 100; i++) {
    try { const r = await fetch(`http://127.0.0.1:${port}/`); if (r.ok) return; } catch { /* retry */ }
    await new Promise((r) => setTimeout(r, 200));
  }
  throw new Error('vite did not start:\n' + viteLog);
}

const checks = [];
function check(name, ok, detail = '') {
  checks.push({ name, ok });
  console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${detail ? ` (${detail})` : ''}`);
}

let browser;
let exitCode = 0;
try {
  await waitForServer();
  browser = await chromium.launch({
    args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'],
  });
  const context = await browser.newContext({ viewport: { width: 1600, height: 900 } });
  const page = await context.newPage();
  const errors = [];
  page.on('console', (m) => { if (m.type() === 'error' || m.type() === 'warning') errors.push(`[${m.type()}] ${m.text()}`); });
  page.on('pageerror', (e) => errors.push(`[pageerror] ${e.message}`));
  const url = `http://127.0.0.1:${port}/?model=building`;
  const ready = async () => {
    await page.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: 120000 });
    const err = await page.evaluate('window.__xrayError');
    if (err) { errors.push(`[app] ${err}`); exitCode = 1; }
  };
  await page.goto(url);
  await ready();

  const geo = async () => page.evaluate(() => {
    const r = (id) => document.querySelector(id).getBoundingClientRect();
    const c = document.getElementById('c');
    const gui = document.querySelector('.lil-gui.lil-root');
    const kids = gui.querySelector(':scope > .lil-children');
    return {
      sb: r('#sidebar').width, dock: r('#dock').width, stage: r('#stage').width, cw: c.clientWidth, ch: c.clientHeight,
      bw: c.width, dpr: window.devicePixelRatio, vw: window.innerWidth, vh: window.innerHeight,
      guiParent: gui.parentElement.className, guiPos: getComputedStyle(gui).position, guiW: gui.getBoundingClientRect().width,
      guiH: gui.getBoundingClientRect().height, dockH: r('#dock').height,
      scrolls: kids.scrollHeight > kids.clientHeight, kidsOverflowY: getComputedStyle(kids).overflowY,
      dockLeft: r('#dock').left,
    };
  });
  // The width transition runs on the (slow, software-rendered) frame clock: wait until the dock has its final width.
  const settle = (w) => page.waitForFunction((x) => Math.round(document.querySelector('#dock').getBoundingClientRect().width) === x, w, { timeout: 15000 });
  let g = await geo();
  console.log('layout (open):', JSON.stringify(g));
  check('dock is 300 px', Math.round(g.dock) === 300);
  check('dock sits at the right edge', Math.round(g.dockLeft + g.dock) === g.vw);
  check('canvas is the viewport minus both panels', g.cw === g.vw - g.sb - g.dock && g.ch === g.vh, `cw=${g.cw}, expected ${g.vw - g.sb - g.dock}`);
  check('canvas drawing buffer matches CSS size', Math.abs(g.bw - g.cw * g.dpr) <= 1);
  check('lil-gui lives in the dock body, not fixed', g.guiParent === 'dk-body' && g.guiPos !== 'fixed', `${g.guiParent} ${g.guiPos}`);
  check('lil-gui fills the dock width', Math.abs(g.guiW - 299) <= 2, `w=${g.guiW}`);
  check('lil-gui is not taller than the dock', g.guiH <= g.dockH, `gui=${g.guiH} dock=${g.dockH}`);

  // Open the folders so the list is taller than the viewport, then check scrolling and sticky titles.
  await page.evaluate(() => window.__xray.app.panel.folders.forEach((f) => f.open()));
  await page.waitForTimeout(500);
  g = await geo();
  check('lil-gui scrolls inside the dock when taller than the viewport', g.scrolls && g.kidsOverflowY === 'auto', `scrolls=${g.scrolls}`);
  const sticky = await page.evaluate(() => {
    const t = document.querySelector('.lil-gui.lil-root > .lil-children > .lil-gui > .lil-title');
    return getComputedStyle(t).position;
  });
  check('top-level folder titles are sticky', sticky === 'sticky');
  await page.evaluate(() => {
    const k = document.querySelector('.lil-gui.lil-root > .lil-children');
    k.scrollTop = 0;
    window.__xray.app.panel.folders.forEach((f) => f.close());
  });
  await page.waitForTimeout(400);
  await page.mouse.click(700, 450); // focus the page away from inputs (also clears the selection)
  await page.screenshot({ path: resolve(here, 'smoke-dock-open.png') });

  // Collapse with "]".
  await page.keyboard.press(']');
  await settle(28);
  await page.waitForTimeout(400);
  g = await geo();
  console.log('layout (closed):', JSON.stringify({ dock: g.dock, cw: g.cw, bw: g.bw }));
  check('collapsed dock is a 28 px rail', Math.round(g.dock) === 28);
  check('canvas grew by 272 px and the buffer was resized', g.cw === 1600 - g.sb - 28 && Math.abs(g.bw - g.cw * g.dpr) <= 1, `cw=${g.cw}`);
  check('rail label is shown, panel hidden', await page.evaluate(() => getComputedStyle(document.querySelector('.dk-rail-label')).display !== 'none' && document.querySelector('.dk-body').offsetParent === null));
  await page.screenshot({ path: resolve(here, 'smoke-dock-closed.png') });

  await page.reload();
  await ready();
  check('collapsed state persisted in localStorage', await page.evaluate(() => JSON.parse(localStorage.getItem('xray.dock')).collapsed === true && document.body.classList.contains('dk-collapsed')));
  g = await geo();
  check('reloaded page shows the 28 px rail', Math.round(g.dock) === 28);
  await page.click('.dk-toggle');
  await settle(300);
  await page.waitForTimeout(400);
  g = await geo();
  check('toggle button expands it again', Math.round(g.dock) === 300 && g.cw === g.vw - g.sb - 300);
  await page.mouse.click(700, 450);
  await page.keyboard.press(']');
  await settle(28);
  await page.keyboard.press(']');
  await settle(300);
  check('"]" toggles both ways', true);

  // lil-gui's own title button still opens/closes the list.
  const rootClosed = async () => page.evaluate(() => document.querySelector('.lil-gui.lil-root').classList.contains('lil-closed'));
  await page.waitForTimeout(500);
  await page.click('.lil-gui.lil-root > .lil-title');
  await page.waitForFunction(() => document.querySelector('.lil-gui.lil-root').classList.contains('lil-closed'), null, { timeout: 5000 }).catch(() => {});
  const closed1 = await rootClosed();
  await page.click('.lil-gui.lil-root > .lil-title');
  await page.waitForFunction(() => !document.querySelector('.lil-gui.lil-root').classList.contains('lil-closed'), null, { timeout: 5000 }).catch(() => {});
  check('lil-gui title still collapses and expands the list', closed1 && !(await rootClosed()));

  // Params export.
  const params = await page.evaluate(() => window.__xrayParams.collect());
  console.log('params keys:', Object.keys(params).join(', '));
  console.log('sightlines keys:', Object.keys(params.sightlines).join(', '));
  console.log('overrides keys:', Object.keys(params.overrides).join(', '));
  console.log('cinematic:', params.cinematic ? Object.keys(params.cinematic).length + ' keys' : 'absent', '| rendering:', JSON.stringify(params.rendering ?? null), '| selectionSets:', params.selectionSets?.length ?? 'absent');
  check('params carry the schema, model and viewer version', params.schema === 'xray-params/1' && params.model === 'building' && typeof params.viewer.version === 'string');
  check('params carry a camera', Array.isArray(params.camera?.position));
  check('GUI folder "Export / import" exists with 6 buttons', await page.evaluate(() => {
    const f = window.__xray.app.panel.folders.find((x) => x._title === 'Export / import');
    return !!f && f.controllers.length === 6;
  }));
  const py = await page.evaluate(() => window.__xrayParams.python());
  check('python export defines XRAY_PARAMS', /^XRAY_PARAMS = \{/m.test(py) && !/\b(true|false|null)\b/.test(py.replace(/"(?:[^"\\]|\\.)*"/g, '""')));

  // Share URL round trip: change settings and camera, build the URL, open it, compare.
  await page.evaluate(() => {
    const a = window.__xray.app;
    a.settings.classification.bufferBase = 0.55;
    a.settings.sightlines.gamma = 1.1;
    a.display.edgeAlpha = 0.33;
    a.renderer.camera.position.set(7.5, 6.25, -4.5);
    a.renderer.controls.target.set(1, 0.5, 0.25);
    a.renderer.controls.update();
  });
  const share = await page.evaluate(() => window.__xrayParams.shareUrl());
  console.log('share URL length:', share.length);
  const before = await page.evaluate(() => window.__xrayParams.collect());
  await page.goto('about:blank'); // a fragment-only change would not reload the page
  await page.goto(share.replace(/^https?:\/\/[^/]+/, `http://127.0.0.1:${port}`));
  await ready();
  await page.waitForTimeout(500);
  const after = await page.evaluate(() => ({ p: window.__xrayParams.collect(), hash: location.hash }));
  check('share URL restores classification, sightlines and display',
    after.p.classification.bufferBase === 0.55 && after.p.sightlines.gamma === 1.1 && after.p.display.edgeAlpha === 0.33);
  const close = (a, b) => a.every((v, i) => Math.abs(v - b[i]) < 2e-3);
  check('share URL restores the camera', close(after.p.camera.position, before.camera.position) && close(after.p.camera.target, before.camera.target),
    `${JSON.stringify(after.p.camera)} vs ${JSON.stringify(before.camera)}`);
  check('the #p= fragment is removed after applying', after.hash === '');

  // Export JSON / Import JSON through the apply function.
  const unapplied = await page.evaluate(() => window.__xrayParams.apply(JSON.parse(window.__xrayParams.json())));
  check('applying our own export reports nothing unapplied', unapplied.length === 0, JSON.stringify(unapplied));

  // Does the controller see GUI-bound settings? (controller.settings is a shallow copy of app.settings.)
  const link = await page.evaluate(() => {
    const a = window.__xray.app;
    a.settings.farMode = 'hidden';
    return { app: a.settings.farMode, controller: a.controller.settings.farMode };
  });
  console.log('note: app.settings.farMode set to hidden -> controller.settings.farMode =', link.controller);

  console.log('console errors/warnings:', errors.length ? '\n' + errors.join('\n') : 'none');
  if (errors.some((e) => !e.startsWith('[warning]'))) exitCode = 1;
  if (checks.some((c) => !c.ok)) exitCode = 1;
} catch (e) {
  console.error(e);
  exitCode = 1;
} finally {
  if (browser) await browser.close();
  vite.kill('SIGTERM');
}
process.exit(exitCode);
