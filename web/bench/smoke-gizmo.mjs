// Headless check of the gizmo (navigation cube + section strip + section plane handles).
//   SMOKE_PORT=5624 node bench/smoke-gizmo.mjs
// fzk-haus at 1400x800: cube in several orientations (home, top, edge, corner, rolled), a drag on the cube, the plane
// arrow and ring drags (no pick while dragging), a box fitted to the selection, the visibility key; synth5k with the
// cube; a phone viewport of 390x844 (collapsed, then opened). Writes bench/gizmo-*.png and prints the checks.
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const port = Number(process.env.SMOKE_PORT ?? 5624);

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

let failed = false;
function check(name, ok, detail = '') {
  if (!ok) failed = true;
  console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${detail ? ` (${detail})` : ''}`);
}
const errors = [];
function watch(page) {
  page.on('console', (m) => {
    if (m.type() === 'error') errors.push(`[error] ${m.text()}`);
    if (m.type() === 'warning' && !m.text().startsWith('[help]')) errors.push(`[warning] ${m.text()}`);
    if (m.type() === 'warning' && m.text().startsWith('[help]') && /Gizmo/.test(m.text())) errors.push(`[help] ${m.text()}`);
  });
  page.on('pageerror', (e) => errors.push(`[pageerror] ${e.message}`));
}
async function open(page, model) {
  await page.goto(`http://127.0.0.1:${port}/?model=${model}&cinematic=off`, { timeout: 240000 }); // a loaded box is slow to serve
  await page.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: 240000 });
  const err = await page.evaluate('window.__xrayError');
  if (err) throw new Error(err);
  await page.addStyleTag({ content: '#xray-overlay, #xray-message { visibility: hidden !important }' });
}
const settle = (page, ms = 300) => page.evaluate(async (ms) => {
  for (let i = 0; i < 3; i++) await new Promise((r) => requestAnimationFrame(r));
  for (let i = 0; i < 200 && window.__xrayGizmo?.isMoving(); i++) await new Promise((r) => setTimeout(r, 30));
  await new Promise((r) => setTimeout(r, ms));
  for (let i = 0; i < 2; i++) await new Promise((r) => requestAnimationFrame(r));
}, ms);
const view = (page) => page.evaluate(() => {
  const { camera, controls } = window.__xray.app.renderer;
  const d = camera.position.clone().sub(controls.target).normalize();
  camera.updateMatrixWorld();
  const up = camera.up.clone();
  const screenUp = { x: camera.matrixWorld.elements[4], y: camera.matrixWorld.elements[5], z: camera.matrixWorld.elements[6] };
  return { d: [d.x, d.y, d.z].map((v) => +v.toFixed(4)), up: [up.x, up.y, up.z].map((v) => +v.toFixed(4)), screenUp: [screenUp.x, screenUp.y, screenUp.z].map((v) => +v.toFixed(3)) };
});
const near = (a, b, eps = 0.01) => a.every((v, i) => Math.abs(v - b[i]) < eps);
async function cubeShot(page, name) {
  const box = await page.locator('#xray-gizmo').boundingBox();
  await page.screenshot({ path: resolve(here, `gizmo-${name}.png`), clip: { x: box.x - 6, y: box.y - 6, width: box.width + 12, height: box.height + 12 }, timeout: 180000 });
}
/** Centre of the visible cube cell of a region (page coordinates). */
const cellAt = (page, region) => page.evaluate((region) => {
  const cells = [...document.querySelectorAll(`#xray-gizmo [data-region="${region}"]`)].filter((p) => p.style.display !== 'none');
  if (!cells.length) return null;
  // The largest visible cell of the region.
  let best = null;
  for (const c of cells) { const r = c.getBoundingClientRect(); if (!best || r.width * r.height > best.w * best.h) best = { x: r.x + r.width / 2, y: r.y + r.height / 2, w: r.width, h: r.height }; }
  return best;
}, region);

let browser;
try {
  await waitForServer();
  browser = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });

  // ------------------------------------------------------------ fzk-haus, desktop
  const page = await browser.newPage({ viewport: { width: 1400, height: 800 } });
  watch(page);
  await open(page, 'fzk-haus');
  const g = await page.evaluate(() => {
    const el = document.getElementById('xray-gizmo');
    const r = el.getBoundingClientRect();
    const st = document.getElementById('stage').getBoundingClientRect();
    return { exists: !!el, hidden: el.hidden, right: st.right - r.right, bottom: st.bottom - r.bottom, w: r.width, h: r.height, cells: el.querySelectorAll('[data-region]').length, labels: [...el.querySelectorAll('.xg-label')].filter((t) => t.style.display !== 'none').map((t) => t.textContent), buttons: [...el.querySelectorAll('button')].map((b) => b.getAttribute('aria-label')).filter(Boolean).length, helpKeys: [...el.querySelectorAll('[data-help-key]')].map((b) => b.getAttribute('data-help-key')).filter((k) => !window.__xrayHelp?.lookup(k)) };
  });
  console.log('gizmo', JSON.stringify(g));
  check('gizmo in the bottom-right corner of the stage, above the status bar', g.exists && !g.hidden && g.right >= 4 && g.right < 60 && g.bottom >= 24 && g.bottom < 60, `right ${g.right}, bottom ${g.bottom}`);
  check('54 cube cells and 3 labels from the home corner', g.cells === 54 && g.labels.length === 3, g.labels.join(','));
  check('every button has an aria-label and a help text', g.buttons >= 15 && g.helpKeys.length === 0, g.helpKeys.join(','));
  await settle(page, 500);
  await cubeShot(page, 'cube-home');

  // Click faces, an edge and a corner.
  for (const [region, name, dir] of [['0,0,1', 'front', [0, 0, 1]], ['1,0,1', 'edge', [0.7071, 0, 0.7071]], ['1,1,1', 'corner', [0.5774, 0.5774, 0.5774]], ['0,1,0', 'top', [0, 1, 0]]]) {
    const c = await cellAt(page, region);
    if (!c) { check(`cell ${region} visible`, false); continue; }
    await page.mouse.click(c.x, c.y);
    await settle(page, 300);
    const v = await view(page);
    check(`click ${name} looks from ${region}`, near(v.d, dir, 0.01), JSON.stringify(v));
    if (name === 'top') check('top view: back (-Z) at the top of the screen', near(v.screenUp, [0, 0, -1], 0.01), JSON.stringify(v.screenUp));
    await cubeShot(page, `cube-${name}`);
  }
  await page.locator('.xg-tr').click();
  await settle(page, 300);
  let v = await view(page);
  check('turn right moves the camera a quarter about the vertical (top view: the up turns)', near(v.d, [0, 1, 0], 0.01) && near(v.screenUp, [-1, 0, 0], 0.01), JSON.stringify(v));
  await page.mouse.click(...Object.values(await cellAt(page, '1,1,1')).slice(0, 2));
  await settle(page, 300);
  // Back to front (through the edge view, from where the front is visible), then roll.
  await page.mouse.click(...Object.values(await cellAt(page, '1,0,-1')).slice(0, 2));
  await settle(page, 300);
  await page.locator('.xg-tl').click();
  await settle(page, 300);
  await page.locator('.xg-tl').click();
  await settle(page, 300);
  v = await view(page);
  check('two left turns from the back right edge reach the front left edge', near(v.d, [-0.7071, 0, 0.7071], 0.01), JSON.stringify(v.d));
  await page.mouse.click(...Object.values(await cellAt(page, '0,0,1')).slice(0, 2));
  await settle(page, 300);
  await page.locator('.xg-rcw').click();
  await settle(page, 300);
  v = await view(page);
  check('roll clockwise: camera up turns to the screen left (-X)', near(v.d, [0, 0, 1], 0.01) && near(v.screenUp, [-1, 0, 0], 0.01), JSON.stringify(v));
  await cubeShot(page, 'cube-rolled');
  await page.locator('.xg-home').click();
  await settle(page, 300);
  v = await view(page);
  check('home returns to world up', near(v.up, [0, 1, 0], 1e-6) && v.screenUp[1] > 0.5, JSON.stringify(v));

  // Drag the cube to orbit; no selection change.
  await page.evaluate(() => window.__xray.app.selectIds([22]));
  await settle(page, 200);
  const before = await view(page);
  const cb = await page.locator('#xray-gizmo .xg-cube').boundingBox();
  await page.mouse.move(cb.x + cb.width / 2, cb.y + cb.height / 2);
  await page.mouse.down();
  await page.mouse.move(cb.x + cb.width / 2 + 30, cb.y + cb.height / 2 + 10, { steps: 6 });
  await page.mouse.up();
  await settle(page, 200);
  const after = await view(page);
  const sel = await page.evaluate(() => window.__xray.app.selection);
  check('dragging the cube orbits the camera', !near(before.d, after.d, 0.02), `${JSON.stringify(before.d)} -> ${JSON.stringify(after.d)}`);
  check('dragging the cube keeps the selection', sel.length === 1 && sel[0] === 22, JSON.stringify(sel));
  await cubeShot(page, 'cube-dragged');

  // ------------------------------------------------------------ section strip and plane handles
  await page.evaluate(async () => {
    const r = window.__xray.app.renderer;
    r.camera.up.set(0, 1, 0);
    r.camera.position.set(6, 5.5, 13);
    r.controls.target.set(-3.95, -1.8, -4.8);
    r.controls.update();
  });
  await settle(page, 300);
  await page.locator('#xray-gizmo .xg-ax-y').click();
  await settle(page, 400);
  const pl = await page.evaluate(() => ({ cfg: JSON.parse(JSON.stringify(window.__xraySection.config.plane)), n: window.__xray.app.renderer.getClipPlanes()?.length ?? 0, pressed: document.querySelector('#xray-gizmo .xg-ax-y').getAttribute('aria-pressed'), centre: (() => { const e = window.__xray.app.loaded.model.elements[22].bounds; return [(e[0] + e[3]) / 2, (e[1] + e[4]) / 2, (e[2] + e[5]) / 2]; })(), sc: window.__xraySection.centre() }));
  console.log('plane', JSON.stringify(pl));
  check('Y button: a horizontal plane through the selection centre', pl.n === 1 && pl.cfg.axis === 'y' && pl.cfg.enabled && Math.abs(pl.sc[1] + pl.cfg.offset - pl.centre[1]) < 1e-6 && pl.pressed === 'true');
  const hp = await page.evaluate(() => window.__xrayGizmo.handles.positions());
  check('plane handles on screen', !!hp, JSON.stringify(hp));
  await page.screenshot({ path: resolve(here, 'gizmo-plane.png'), clip: { x: 300, y: 0, width: 800, height: 800 }, timeout: 180000 });
  // Drag the arrow head.
  const head = await page.evaluate(() => { const r = document.querySelector('.xg-arrow-head').getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2 }; });
  const off0 = pl.cfg.offset;
  await page.mouse.move(head.x, head.y);
  await page.mouse.down();
  await page.mouse.move(head.x, head.y - 30, { steps: 5 });
  await page.mouse.move(head.x, head.y - 60, { steps: 5 });
  await settle(page, 300);
  const mid = await page.evaluate(() => ({ text: document.querySelector('.xg-readout').textContent, vis: document.querySelector('.xg-readout').getAttribute('visibility'), off: window.__xraySection.config.plane.offset }));
  await page.screenshot({ path: resolve(here, 'gizmo-plane-drag.png'), clip: { x: 300, y: 0, width: 800, height: 800 }, timeout: 180000 });
  await page.mouse.up();
  await settle(page, 200);
  const sel2 = await page.evaluate(() => window.__xray.app.selection);
  check('arrow drag pushes the plane up along its normal with a live readout', mid.off > off0 + 0.1 && mid.vis === 'visible' && /^offset [+-]\d+\.\d\d m$/.test(mid.text), `${off0.toFixed(2)} -> ${mid.off.toFixed(2)}, "${mid.text}"`);
  check('no pick while dragging a handle (selection kept)', sel2.length === 1 && sel2[0] === 22, JSON.stringify(sel2));
  // Drag a ring.
  // positions() are stage coordinates: add the stage offset. Ring 0 turns about the in-plane axis seen face on.
  const ring = await page.evaluate(() => { const p = window.__xrayGizmo.handles.positions(); const st = document.getElementById('stage').getBoundingClientRect(); return [p.rings[0][0] + st.left, p.rings[0][1] + st.top]; });
  await page.mouse.move(ring[0] + 0, ring[1]);
  await page.mouse.down();
  await page.mouse.move(ring[0] - 20, ring[1] + 25, { steps: 6 });
  await page.mouse.move(ring[0] - 30, ring[1] + 50, { steps: 6 });
  await settle(page, 200);
  const rt = await page.evaluate(() => ({ text: document.querySelector('.xg-readout').textContent, cfg: JSON.parse(JSON.stringify(window.__xraySection.config.plane)) }));
  await page.screenshot({ path: resolve(here, 'gizmo-plane-ring.png'), clip: { x: 300, y: 0, width: 800, height: 800 }, timeout: 180000 });
  await page.mouse.up();
  const tiltDeg = rt.cfg.normal ? (Math.acos(Math.min(1, Math.abs(rt.cfg.normal[1]))) * 180) / Math.PI : 0;
  const snapped = Math.abs(tiltDeg / 15 - Math.round(tiltDeg / 15)) < 1e-3;
  check('ring drag tilts the plane in 15 degree steps', rt.cfg.axis !== 'y' && tiltDeg > 1 && snapped, `${rt.cfg.axis} ${JSON.stringify(rt.cfg.normal)} tilt ${tiltDeg.toFixed(2)}, "${rt.text}"`);
  const sel3 = await page.evaluate(() => window.__xray.app.selection);
  check('no pick after the ring drag', sel3.length === 1 && sel3[0] === 22);

  // Box fitted to the selection.
  await page.evaluate(() => window.__xraySection.set({ plane: { enabled: false } }));
  await page.locator('#xray-gizmo [data-help-key="Gizmo/Section box"]').click();
  await settle(page, 600);
  const bx = await page.evaluate(() => ({ n: window.__xray.app.renderer.getClipPlanes()?.length ?? 0, box: window.__xraySection.config.box, b: window.__xray.app.loaded.model.elements[22].bounds }));
  check('box button fits a box to the selection', bx.n === 6 && bx.box.enabled && Math.abs(bx.box.min[0] - (bx.b[0] - bx.box.margin)) < 1e-6, JSON.stringify({ n: bx.n, min: bx.box.min }));
  await page.screenshot({ path: resolve(here, 'gizmo-box-selection.png'), clip: { x: 300, y: 0, width: 800, height: 800 }, timeout: 180000 });
  await page.locator('#xray-gizmo [data-help-key="Gizmo/Clear section"]').click();
  await settle(page, 300);
  check('clear removes every plane', (await page.evaluate(() => window.__xray.app.renderer.getClipPlanes())) === null);

  // Visibility key and panel checkbox.
  await page.mouse.click(700, 60); // focus the page (empty sky: clears the selection)
  await page.keyboard.press('v');
  const hid = await page.evaluate(() => document.getElementById('xray-gizmo').hidden);
  await page.keyboard.press('v');
  const shown = await page.evaluate(() => !document.getElementById('xray-gizmo').hidden);
  check('V hides and shows the gizmo', hid && shown);

  // ------------------------------------------------------------ synth5k
  await open(page, 'synth5k');
  await settle(page, 500);
  const c5 = await cellAt(page, '0,0,1');
  if (c5) await page.mouse.click(c5.x, c5.y);
  await settle(page, 400);
  v = await view(page);
  check('synth5k: front face click', near(v.d, [0, 0, 1], 0.01), JSON.stringify(v.d));
  await page.locator('#xray-gizmo .xg-ax-x').click();
  await settle(page, 600);
  await page.screenshot({ path: resolve(here, 'gizmo-synth5k.png'), clip: { x: 300, y: 0, width: 800, height: 800 }, timeout: 180000 });
  await page.locator('#xray-gizmo [data-help-key="Gizmo/Clear section"]').click();

  // ------------------------------------------------------------ phone
  const phone = await browser.newPage({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  watch(phone);
  await phone.evaluate(() => { try { localStorage.removeItem('xray.gizmo'); } catch { /* ignore */ } }).catch(() => {});
  await open(phone, 'fzk-haus');
  await settle(phone, 500);
  const ph = await phone.evaluate(() => {
    const el = document.getElementById('xray-gizmo');
    const openBtn = el.querySelector('.xg-open').getBoundingClientRect();
    const st = document.getElementById('stage').getBoundingClientRect();
    return { collapsed: el.classList.contains('collapsed'), w: el.getBoundingClientRect().width, openRight: st.right - openBtn.right, openBottom: st.bottom - openBtn.bottom };
  });
  check('phone: collapsed to a small button clear of the dock rail and the status bar', ph.collapsed && ph.w < 60 && ph.openRight >= 28 && ph.openBottom >= 24, JSON.stringify(ph));
  await phone.screenshot({ path: resolve(here, 'gizmo-phone-collapsed.png'), timeout: 180000 });
  await phone.locator('#xray-gizmo .xg-open').tap();
  await settle(phone, 300);
  const ph2 = await phone.evaluate(() => { const r = document.getElementById('xray-gizmo').getBoundingClientRect(); return { collapsed: document.getElementById('xray-gizmo').classList.contains('collapsed'), left: r.left, w: r.width }; });
  check('phone: the button opens the gizmo inside the screen', !ph2.collapsed && ph2.left > 0, JSON.stringify(ph2));
  await phone.screenshot({ path: resolve(here, 'gizmo-phone-open.png'), timeout: 180000 });
  const t = await cellAt(phone, '0,1,0');
  if (t) await phone.touchscreen.tap(t.x, t.y);
  await settle(phone, 400);
  const pv = await view(phone);
  check('phone: tap on Top looks down', near(pv.d, [0, 1, 0], 0.01), JSON.stringify(pv.d));

  if (errors.length) { console.log('\nconsole problems:'); errors.forEach((e) => console.log(' ', e)); failed = true; }
  else console.log('\nno console errors or warnings');
} catch (e) {
  console.error(e);
  failed = true;
} finally {
  await browser?.close();
  vite.kill();
}
process.exit(failed ? 1 : 0);
