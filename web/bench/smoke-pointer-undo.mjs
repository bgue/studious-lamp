// Headless smoke test for the pointer modes (Arrow select / Hand move) and the undo stack. Starts vite (bench/vite.smoke.config.mjs),
// loads the building and drives it with Playwright: the gizmo toggle (aria-pressed, cursor, keys R and G, kept in localStorage but not
// in the params or the share link), hand drag orbits and does not select, arrow drag draws a window or crossing box that selects
// (Shift adds, Esc cancels, right drag and the wheel still move the camera), wheel zoom then Ctrl+Z restores the camera and Ctrl+Shift+Z
// brings it back, a setting change and a selection undone, home is undoable, keys left alone in an input, a phone viewport
// (toggle and undo buttons inside the screen), and no console errors.
// Screenshots: bench/pointer-modes-desktop.png, pointer-box-select.png, pointer-modes-phone.png.
// Usage: SMOKE_PORT=5701 node bench/smoke-pointer-undo.mjs
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const port = Number(process.env.SMOKE_PORT ?? 5701);

function loadPlaywright() {
  const candidates = [process.env.PLAYWRIGHT_MODULE, resolve(root, 'node_modules/playwright'), '/opt/node-tools/node_modules/playwright', '/opt/node22/lib/node_modules/playwright'].filter(Boolean);
  for (const c of candidates) {
    try { return createRequire(import.meta.url)(c); } catch { /* try next */ }
  }
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
const GL = ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'];
const shot = (page, name, opts = {}) => page.screenshot({ path: resolve(here, name), timeout: 180000, ...opts });

async function open(browser, opts = {}) {
  const ctx = await browser.newContext({ viewport: opts.viewport ?? { width: 1400, height: 800 }, isMobile: !!opts.mobile, hasTouch: !!opts.mobile });
  const page = await ctx.newPage();
  page.on('console', (m) => {
    if (m.type() === 'error') errors.push(`[error] ${m.text()}`);
    if (m.type() === 'warning' && !m.text().startsWith('[help]')) errors.push(`[warning] ${m.text()}`);
    if (m.type() === 'warning' && m.text().startsWith('[help]') && /Gizmo/.test(m.text())) errors.push(`[help] ${m.text()}`);
  });
  page.on('pageerror', (e) => errors.push(`[pageerror] ${e.message}`));
  await page.route(/^https?:\/\/(?!127\.0\.0\.1)/, (route) => route.abort());
  await page.goto(`http://127.0.0.1:${port}/?model=${opts.model ?? 'building'}&cinematic=off`, { timeout: 240000 });
  await page.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: 240000 });
  const err = await page.evaluate('window.__xrayError');
  if (err) throw new Error(err);
  await page.waitForTimeout(2200); // the undo plugin treats the first 1.5 s as loading
  return { ctx, page };
}

const pose = (page) => page.evaluate(() => {
  const r = window.__xray.app.renderer;
  return [r.camera.position.x, r.camera.position.y, r.camera.position.z, r.controls.target.x, r.controls.target.y, r.controls.target.z];
});
const dist = (a, b) => Math.hypot(...a.map((v, i) => v - b[i]));
const camDist = (p) => Math.hypot(p[0] - p[3], p[1] - p[4], p[2] - p[5]);
const selSize = (page) => page.evaluate(() => window.__xray.app.controller.selection.size);
const cursor = (page) => page.evaluate(() => getComputedStyle(document.getElementById('c')).cursor);
const pressed = (page, cls) => page.evaluate((c) => document.querySelector(`#xray-gizmo .${c}`)?.getAttribute('aria-pressed'), cls);
const undoList = (page) => page.evaluate(() => window.__xrayUndo.list());
const settle = (page, ms = 1200) => page.waitForTimeout(ms);
/** Wait until the camera has stopped (a headless frame is slow, so the orbit damping takes seconds), then past the undo debounce. */
async function still(page, extra = 900) {
  let last = null;
  let calm = 0;
  for (let i = 0; i < 80 && calm < 3; i++) {
    await page.waitForTimeout(300);
    const p = await page.evaluate(() => { const r = window.__xray.app.renderer; return [r.camera.position.x, r.camera.position.y, r.camera.position.z, r.controls.target.x, r.controls.target.y, r.controls.target.z]; });
    calm = last && p.every((v, k) => Math.abs(v - last[k]) < 1e-5) ? calm + 1 : 0;
    last = p;
  }
  await page.waitForTimeout(extra);
}
/** A wheel gesture inside the page: `n` events 25 ms apart over the canvas centre (a headless frame takes long enough to stretch playwright's own wheel). */
const wheel = (page, n, deltaY) => page.evaluate(async ([n, deltaY]) => {
  const c = document.getElementById('c');
  const r = c.getBoundingClientRect();
  for (let i = 0; i < n; i++) {
    c.dispatchEvent(new WheelEvent('wheel', { deltaY, bubbles: true, cancelable: true, clientX: r.left + r.width / 2, clientY: r.top + r.height / 2 }));
    await new Promise((res) => setTimeout(res, 25));
  }
}, [n, deltaY]);
const canvasBox = (page) => page.locator('#c').boundingBox();

let browser;
try {
  await waitForServer();
  browser = await chromium.launch({ args: GL });

  // ------------------------------------------------------------ desktop
  const { page } = await open(browser);
  const cb = await canvasBox(page);
  const cx = cb.x + cb.width / 2;
  const cy = cb.y + cb.height / 2;

  // ---- the toggle
  const ui = await page.evaluate(() => {
    const g = document.getElementById('xray-gizmo');
    const q = (c) => g.querySelector(`.${c}`);
    const vis = (e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && r.left >= 0 && r.top >= 0 && r.right <= innerWidth && r.bottom <= innerHeight; };
    return {
      sel: !!q('xg-ptr-select'), hand: !!q('xg-ptr-hand'), undo: !!q('xg-undo'), redo: !!q('xg-redo'),
      allVisible: ['xg-ptr-select', 'xg-ptr-hand', 'xg-undo', 'xg-redo'].every((c) => vis(q(c))),
      titles: ['xg-ptr-select', 'xg-ptr-hand'].map((c) => q(c).title),
      labels: ['xg-ptr-select', 'xg-ptr-hand', 'xg-undo', 'xg-redo'].map((c) => q(c).getAttribute('aria-label')),
      undoDisabled: q('xg-undo').disabled, redoDisabled: q('xg-redo').disabled,
      helpMissing: [...g.querySelectorAll('[data-help-key]')].map((b) => b.getAttribute('data-help-key')).filter((k) => !window.__xrayHelp?.lookup(k)),
    };
  });
  check('toggle and history buttons exist and are on screen', ui.sel && ui.hand && ui.undo && ui.redo && ui.allVisible);
  check('tooltips name the keys', /\(R\)/.test(ui.titles[0]) && /\(G\)/.test(ui.titles[1]), ui.titles.map((t) => t.slice(-12)).join(' | '));
  check('every new button has a help text', ui.helpMissing.length === 0, ui.helpMissing.join(','));
  check('undo and redo start disabled with plain labels', ui.undoDisabled && ui.redoDisabled && ui.labels[2] === 'Nothing to undo', ui.labels.join(' | '));
  check('hand is the default: aria-pressed and the grab cursor', (await pressed(page, 'xg-ptr-hand')) === 'true' && (await pressed(page, 'xg-ptr-select')) === 'false' && (await cursor(page)) === 'grab', await cursor(page));
  await shot(page, 'pointer-modes-desktop.png');

  // ---- keys
  await page.keyboard.press('r');
  check('R sets arrow mode: aria-pressed and the default cursor', (await pressed(page, 'xg-ptr-select')) === 'true' && (await pressed(page, 'xg-ptr-hand')) === 'false' && (await cursor(page)) === 'default', await cursor(page));
  check('arrow mode is kept in localStorage only', (await page.evaluate(() => localStorage.getItem('xray.pointerMode'))) === 'arrow');
  const leak = await page.evaluate(() => {
    const json = JSON.stringify(window.__xrayParams.collect());
    const url = window.__xrayParams.shareUrl();
    const enc = url.split('p=')[1] ?? '';
    const b64 = enc.replace(/-/g, '+').replace(/_/g, '/');
    const shared = atob(b64 + '='.repeat((4 - (b64.length % 4)) % 4));
    const bad = /pointerMode|pointer_mode|"arrow"|"hand"/i;
    return { json: bad.test(json), url: bad.test(shared) || shared.length < 20, sharedLen: shared.length };
  });
  check('the mode is not in the params or the share link', !leak.json && !leak.url, JSON.stringify(leak));
  await page.keyboard.press('g');
  check('G sets hand mode', (await pressed(page, 'xg-ptr-hand')) === 'true' && (await cursor(page)) === 'grab');
  await page.locator('#xray-gizmo .xg-ptr-select').click();
  check('the button sets arrow mode', (await pressed(page, 'xg-ptr-select')) === 'true');
  await page.locator('#xray-gizmo .xg-ptr-hand').click();
  check('the button sets hand mode', (await pressed(page, 'xg-ptr-hand')) === 'true');

  // ---- hand mode: a drag orbits, does not select; a click selects
  await settle(page);
  const p0 = await pose(page);
  await page.mouse.move(cx, cy);
  await page.mouse.down();
  await page.mouse.move(cx + 60, cy + 20, { steps: 5 });
  const during = await cursor(page);
  await page.mouse.move(cx + 140, cy + 40, { steps: 5 });
  await page.mouse.up();
  await still(page);
  const p1 = await pose(page);
  check('hand: left drag orbits', dist(p0, p1) > 0.05, `moved ${dist(p0, p1).toFixed(2)}`);
  check('hand: the cursor is grabbing while dragging', during === 'grabbing', during);
  check('hand: a drag does not select', (await selSize(page)) === 0);
  check('the orbit is one undo entry named for it', (await undoList(page)).undo.length === 1 && /orbit|view/.test((await undoList(page)).undo[0].label), JSON.stringify((await undoList(page)).undo));

  // A click selects: find a pixel with an element.
  const hit = await page.evaluate(() => {
    const { app } = window.__xray;
    const r = document.getElementById('c').getBoundingClientRect();
    for (let y = 0.2; y <= 0.8; y += 0.05) for (let x = 0.2; x <= 0.8; x += 0.05) {
      const id = app.renderer.pick(x * 2 - 1, -(y * 2 - 1));
      if (id !== null) return { x: r.left + x * r.width, y: r.top + y * r.height, id };
    }
    return null;
  });
  await page.mouse.click(hit.x, hit.y);
  await settle(page, 600);
  check('hand: a click selects', (await selSize(page)) === 1);
  const selList = await undoList(page);
  check('the selection is an undo entry', selList.undo.at(-1)?.kind === 'selection', JSON.stringify(selList.undo.at(-1)));
  await page.keyboard.press('Escape');
  await settle(page, 600);

  // ---- arrow mode: boxes
  await page.keyboard.press('r');
  const bx0 = cb.x + cb.width * 0.2;
  const by0 = cb.y + cb.height * 0.25;
  const bx1 = cb.x + cb.width * 0.8;
  const by1 = cb.y + cb.height * 0.8;
  await page.mouse.move(bx0, by0);
  await page.mouse.down();
  await page.mouse.move((bx0 + bx1) / 2, (by0 + by1) / 2, { steps: 4 });
  await page.mouse.move(bx1, by1, { steps: 4 });
  const boxW = await page.evaluate(() => { const b = document.getElementById('xray-boxselect'); const s = getComputedStyle(b); return { shown: s.display !== 'none', mode: b.dataset.box, style: s.borderTopStyle }; });
  check('arrow: a drag left to right draws a solid window box', boxW.shown && boxW.mode === 'window' && boxW.style === 'solid', JSON.stringify(boxW));
  await shot(page, 'pointer-box-select.png');
  await page.mouse.up();
  await settle(page, 300);
  const nWindow = await selSize(page);
  check('arrow: the window box selected elements fully inside', nWindow > 0, `${nWindow}`);
  check('arrow: the box is gone after release', await page.evaluate(() => getComputedStyle(document.getElementById('xray-boxselect')).display === 'none'));
  check('arrow: the model tree marks the picked elements (the box uses the selection API)', (await page.evaluate(() => document.querySelectorAll('.tr.sel').length)) > 0);

  // crossing: right to left over the same region
  await page.mouse.move(bx1, by1);
  await page.mouse.down();
  await page.mouse.move((bx0 + bx1) / 2, (by0 + by1) / 2, { steps: 4 });
  await page.mouse.move(bx0, by0, { steps: 4 });
  const boxC = await page.evaluate(() => { const b = document.getElementById('xray-boxselect'); const s = getComputedStyle(b); return { mode: b.dataset.box, style: s.borderTopStyle }; });
  check('arrow: a drag right to left draws a dashed crossing box', boxC.mode === 'crossing' && boxC.style === 'dashed', JSON.stringify(boxC));
  await page.mouse.up();
  await settle(page, 300);
  const nCross = await selSize(page);
  check('arrow: the crossing box picks at least as many, and more here', nCross >= nWindow && nCross > nWindow, `${nWindow} -> ${nCross}`);
  const selList2 = await undoList(page);
  check('box selects are undo entries', selList2.undo.filter((e) => e.kind === 'selection').length >= 3, JSON.stringify(selList2.undo.map((e) => e.kind)));

  // Esc cancels
  await page.keyboard.press('Escape'); // clear the selection first
  await settle(page, 200);
  await page.mouse.move(bx0, by0);
  await page.mouse.down();
  await page.mouse.move(bx1, by1, { steps: 6 });
  await page.keyboard.press('Escape');
  await page.mouse.up();
  await settle(page, 200);
  check('arrow: Esc cancels the box (nothing selected, box hidden)', (await selSize(page)) === 0 && (await page.evaluate(() => getComputedStyle(document.getElementById('xray-boxselect')).display === 'none')));

  // Shift adds
  await page.mouse.move(bx0, by0);
  await page.mouse.down();
  await page.mouse.move(bx1, by1, { steps: 5 });
  await page.mouse.up();
  await settle(page, 300);
  const a1 = await selSize(page);
  await page.keyboard.down('Shift');
  await page.mouse.move(cb.x + cb.width * 0.97, cb.y + cb.height * 0.97);
  await page.mouse.down();
  await page.mouse.move(cb.x + cb.width * 0.7, cb.y + cb.height * 0.2, { steps: 5 });
  await page.mouse.up();
  await page.keyboard.up('Shift');
  await settle(page, 300);
  const a2 = await selSize(page);
  check('arrow: Shift adds a second box to the selection', a1 > 0 && a2 > a1, `${a1} -> ${a2}`);

  // hidden elements are not picked
  const hiddenCheck = await page.evaluate(() => {
    const { app } = window.__xray;
    const api = window.__xrayPointer;
    const r = document.getElementById('c').getBoundingClientRect();
    const rect = { x0: 0, y0: 0, x1: r.width, y1: r.height };
    const all = api.pick(rect, 'crossing');
    app.settings.overrides.userHides.add(all[0]);
    app.controller.refreshOverrides?.();
    app.reclassify();
    const after = api.pick(rect, 'crossing');
    app.settings.overrides.userHides.delete(all[0]);
    app.controller.refreshOverrides?.();
    app.reclassify();
    return { all: all.length, after: after.length, gone: !after.includes(all[0]) };
  });
  check('hidden elements are not picked by a box', hiddenCheck.gone && hiddenCheck.after === hiddenCheck.all - 1, JSON.stringify(hiddenCheck));

  // right drag and the wheel still move the camera in arrow mode
  await page.keyboard.press('Escape');
  await still(page);
  const q0 = await pose(page);
  await page.mouse.move(cx, cy);
  await page.mouse.down({ button: 'right' });
  await page.mouse.move(cx + 80, cy + 30, { steps: 6 });
  await page.mouse.up({ button: 'right' });
  await still(page);
  const q1 = await pose(page);
  check('arrow: right drag pans the camera', dist(q0, q1) > 0.02 && (await selSize(page)) === 0, `moved ${dist(q0, q1).toFixed(2)}`);
  await page.mouse.move(cx, cy);
  await page.mouse.wheel(0, -300);
  await still(page);
  const q2 = await pose(page);
  check('arrow: the wheel zooms', camDist(q2) < camDist(q1) - 0.01, `${camDist(q1).toFixed(2)} -> ${camDist(q2).toFixed(2)}`);
  await page.keyboard.press('g');

  // ---- undo: wheel zoom then Ctrl+Z
  await page.keyboard.press('Escape');
  await still(page);
  const z0 = await pose(page);
  await page.mouse.move(cx, cy);
  await wheel(page, 6, -120);
  await still(page);
  const z1 = await pose(page);
  check('wheel zoom moved the camera in', camDist(z1) < camDist(z0) * 0.85, `${camDist(z0).toFixed(2)} -> ${camDist(z1).toFixed(2)}`);
  const lst = await undoList(page);
  check('the whole wheel gesture is one "zoom" entry', lst.undo.at(-1)?.label === 'zoom', JSON.stringify(lst.undo.slice(-2)));
  check('the undo button names it', await page.evaluate(() => document.querySelector('#xray-gizmo .xg-undo').getAttribute('aria-label')) === 'Undo zoom');
  await page.keyboard.press('Control+z');
  await still(page, 300);
  const z2 = await pose(page);
  check('Ctrl+Z restores the earlier camera', dist(z0, z2) < 0.02 * camDist(z0) + 0.02, `off by ${dist(z0, z2).toFixed(3)}`);
  check('redo is enabled after the undo', await page.evaluate(() => !document.querySelector('#xray-gizmo .xg-redo').disabled));
  await page.keyboard.press('Control+Shift+z');
  await still(page, 300);
  const z3 = await pose(page);
  check('Ctrl+Shift+Z brings the zoom back', dist(z1, z3) < 0.02 * camDist(z1) + 0.02, `off by ${dist(z1, z3).toFixed(3)}`);
  await page.keyboard.press('Control+z');
  await still(page, 300);
  await page.keyboard.press('Control+y');
  await still(page, 300);
  check('Ctrl+Y redoes too', dist(z1, await pose(page)) < 0.02 * camDist(z1) + 0.02);
  await page.keyboard.press('Control+z');
  await still(page, 300);
  // a new action clears the redo list
  await wheel(page, 2, 120);
  await still(page);
  check('a new action clears redo', await page.evaluate(() => !window.__xrayUndo.canRedo));

  // ---- home is undoable and frames everything
  await wheel(page, 12, -120);
  await still(page);
  const h0 = await pose(page);
  await page.locator('#xray-gizmo .xg-home').click();
  await still(page);
  const h1 = await pose(page);
  const homeDist = await page.evaluate(() => { const { app } = window.__xray; const r = app.renderer; const c = r.camera.position.clone(); app.renderer.frameAll(); const d = r.camera.position.distanceTo(r.controls.target); r.camera.position.copy(c); return d; });
  check('home zooms out to fit the whole model', camDist(h1) > camDist(h0) * 1.3 && Math.abs(camDist(h1) - homeDist) / homeDist < 0.05, `${camDist(h0).toFixed(1)} -> ${camDist(h1).toFixed(1)} (frame all ${homeDist.toFixed(1)})`);
  check('home is an undo entry', (await undoList(page)).undo.at(-1)?.kind === 'view');
  await page.keyboard.press('Control+z');
  await still(page, 300);
  check('Ctrl+Z after home returns to the zoomed view', dist(h0, await pose(page)) < 0.03 * camDist(h0) + 0.05, `off by ${dist(h0, await pose(page)).toFixed(3)}`);

  // ---- a setting
  await settle(page, 600);
  const e0 = await page.evaluate(() => window.__xray.app.display.edgeAlpha);
  await page.evaluate(async () => {
    const c = window.__xray.app.panel.controllersRecursive().find((x) => x.property === 'edgeAlpha');
    for (const v of [0.6, 0.5, 0.4, 0.3]) { c.setValue(v); await new Promise((r) => setTimeout(r, 120)); }
  });
  await settle(page, 400);
  const sl = await undoList(page);
  check('a slider drag is one setting entry named for the setting', sl.undo.at(-1)?.kind === 'setting' && sl.undo.at(-1)?.label === 'edgeAlpha' && sl.undo.filter((e) => e.label === 'edgeAlpha').length === 1, JSON.stringify(sl.undo.slice(-2)));
  check('the undo button says "Undo edgeAlpha"', await page.evaluate(() => document.querySelector('#xray-gizmo .xg-undo').title.startsWith('Undo edgeAlpha')));
  await page.keyboard.press('Control+z');
  await settle(page, 300);
  const e1 = await page.evaluate(() => window.__xray.app.display.edgeAlpha);
  check('Ctrl+Z puts the setting back, in one step', Math.abs(e1 - e0) < 1e-9, `${e0} -> ${e1}`);
  await settle(page, 400);
  check('the undo did not record itself', (await undoList(page)).redo.length === 1);
  await page.keyboard.press('Control+Shift+z');
  await settle(page, 300);
  check('redo sets it again', Math.abs((await page.evaluate(() => window.__xray.app.display.edgeAlpha)) - 0.3) < 1e-9);
  await page.keyboard.press('Control+z');
  await settle(page, 300);

  // ---- selection undo
  await page.evaluate(() => window.__xray.app.clearSelection());
  await settle(page, 300);
  await page.mouse.click(hit.x, hit.y);
  await settle(page, 300);
  const sBefore = await selSize(page);
  check('a click selected one element before the undo', sBefore === 1);
  check('the undo button says "Undo selection"', await page.evaluate(() => document.querySelector('#xray-gizmo .xg-undo').getAttribute('aria-label')) === 'Undo selection');
  await page.keyboard.press('Control+z');
  await settle(page, 300);
  check('Ctrl+Z undoes the selection', (await selSize(page)) === 0);

  // ---- keys left alone
  const sizeBefore = (await undoList(page)).undo.length;
  const filter = page.locator('.sb-filter input').first();
  if (await filter.count()) {
    await filter.focus();
    await page.keyboard.press('Control+z');
    await settle(page, 200);
    check('Ctrl+Z in a text field is left to the field', (await undoList(page)).undo.length === sizeBefore);
    await page.evaluate(() => document.activeElement?.blur());
  } else check('the sidebar filter exists for the key test', false);

  // ---- fit layout: the row stays with the nav buttons
  const fits = await page.evaluate(() => {
    const g = document.getElementById('xray-gizmo');
    const out = {};
    for (const f of ['nav']) {
      g.classList.add(`fit-${f}`);
      const q = (c) => g.querySelector(`.${c}`).getBoundingClientRect();
      out[f] = ['xg-ptr-select', 'xg-undo'].every((c) => q(c).width > 0);
      g.classList.remove(`fit-${f}`);
    }
    return out;
  });
  check('the toggle and history row show in the nav fit layout', fits.nav, JSON.stringify(fits));

  // ---- reload: the mode is remembered
  await page.keyboard.press('r');
  await page.reload();
  await page.waitForFunction('window.__xrayReady === true', null, { timeout: 240000 });
  check('arrow mode is remembered after a reload', (await pressed(page, 'xg-ptr-select')) === 'true');
  await page.keyboard.press('g');

  // ------------------------------------------------------------ phone
  const { page: phone } = await open(browser, { viewport: { width: 390, height: 844 }, mobile: true });
  const ph = await phone.evaluate(() => {
    const g = document.getElementById('xray-gizmo');
    const out = {};
    for (const c of ['xg-ptr-select', 'xg-ptr-hand', 'xg-undo', 'xg-redo']) {
      const r = g.querySelector(`.${c}`).getBoundingClientRect();
      out[c] = r.width > 0 && r.height > 0 && r.left >= 0 && r.top >= 0 && r.right <= innerWidth && r.bottom <= innerHeight;
    }
    return { out, collapsed: g.classList.contains('collapsed') };
  });
  check('phone: the toggle and the undo buttons are visible and inside the screen', Object.values(ph.out).every(Boolean), JSON.stringify(ph));
  await phone.locator('#xray-gizmo .xg-ptr-select').tap();
  check('phone: tapping the arrow sets the mode', (await pressed(phone, 'xg-ptr-select')) === 'true');
  await shot(phone, 'pointer-modes-phone.png');

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
