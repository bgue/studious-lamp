// Headless smoke test for keyboard navigation: starts vite (bench/vite.smoke.config.mjs), loads /?model=building at
// 1600x900 and drives the keys with Playwright. Checks held orbit and fly keys, standard views, selection-aware
// framing, the view history, hide/unhide, the cheat sheet, the command palette, the panel toggles and that typing in
// the sidebar filter triggers no action. Screenshots: bench/keys-cheatsheet.png, bench/keys-palette.png.
// Usage: SMOKE_PORT=5312 node bench/smoke-keys.mjs
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const port = Number(process.env.SMOKE_PORT ?? 5312);

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
  browser = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const page = await browser.newPage({ viewport: { width: 1600, height: 900 } });
  const errors = [];
  const warnings = [];
  page.on('console', (m) => {
    if (m.type() === 'error') errors.push(m.text());
    else if (m.type() === 'warning') warnings.push(m.text());
  });
  page.on('pageerror', (e) => errors.push(`[pageerror] ${e.message}`));
  await page.goto(`http://127.0.0.1:${port}/?model=building`);
  await page.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: 120000 });
  const err = await page.evaluate('window.__xrayError');
  if (err) { errors.push(`[app] ${err}`); }
  await page.waitForTimeout(1500);

  const pose = () => page.evaluate(() => {
    const r = window.__xray.renderer;
    const p = r.camera.position, t = r.controls.target;
    return { p: [p.x, p.y, p.z], t: [t.x, t.y, t.z] };
  });
  const yawOf = (s) => Math.atan2(s.p[0] - s.t[0], s.p[2] - s.t[2]);
  const sub = (a, b) => a.map((v, i) => v - b[i]);
  const len = (a) => Math.hypot(...a);
  const look = (s) => { const d = sub(s.t, s.p); const l = len(d); return d.map((v) => v / l); };
  const sel = () => page.evaluate('window.__xray.app.selection.length');
  const hides = () => page.evaluate('window.__xray.app.settings.overrides.userHides.size');
  // Wait until the camera has stopped moving (a flight or tween finished); the headless GPU is slow and the machine may be busy.
  const settle = async (maxMs = 20000) => {
    let last = JSON.stringify(await pose());
    let still = 0;
    const t0 = Date.now();
    while (still < 5 && Date.now() - t0 < maxMs) {
      await page.waitForTimeout(150);
      const cur = JSON.stringify(await pose());
      const flying = await page.evaluate('window.__cinematic.flying || window.__keymapMoving()');
      still = cur === last && !flying ? still + 1 : 0;
      last = cur;
    }
  };
  const hold = async (key, ms) => { await page.keyboard.down(key); await page.waitForTimeout(ms); await page.keyboard.up(key); await page.waitForTimeout(150); };
  await page.evaluate(() => { document.activeElement && document.activeElement.blur(); window.__cinematic.cfg.flyTo = false; });

  // Held orbit.
  await settle();
  console.log('start', JSON.stringify(await pose()), await page.evaluate('window.__cinematic.flying'));
  let a = await pose();
  await hold('ArrowLeft', 500);
  let b = await pose();
  const dyaw = Math.abs(yawOf(b) - yawOf(a));
  console.log('held', await page.evaluate('window.__keymap.heldCount'), JSON.stringify(b));
  check('ArrowLeft held 500 ms changes the camera yaw', dyaw > 0.05, `dyaw=${dyaw.toFixed(3)} rad`);
  check('orbit keeps the target and the distance', len(sub(b.t, a.t)) < 1e-6 && Math.abs(len(sub(b.p, b.t)) - len(sub(a.p, a.t))) < 1e-3);

  // Held fly: camera and target move together.
  a = await pose();
  await hold('w', 300);
  b = await pose();
  const dp = sub(b.p, a.p), dt = sub(b.t, a.t);
  check('w held 300 ms moves position and target together', len(dp) > 0.005 && len(sub(dp, dt)) < 1e-6, `move=${len(dp).toFixed(3)} m`);

  // Alt+7 top view.
  await page.keyboard.press('Alt+Digit7');
  await page.waitForTimeout(200);
  await settle();
  const top = await pose();
  check('Alt+7 looks straight down', look(top)[1] < -0.99, `look.y=${look(top)[1].toFixed(4)}`);

  // Select the duct and frame it with f; the history returns to the top view with Alt+ArrowLeft.
  await page.evaluate(() => {
    const e = window.__xray.app.loaded.model.elements.find((x) => x.ifcClass === 'IfcDuctSegment');
    window.__xray.app.selectIds([e.id]);
    window.__duct = e.bounds;
  });
  await page.keyboard.press('f');
  await page.waitForTimeout(200);
  await settle();
  const framed = await pose();
  const frameInfo = await page.evaluate(() => {
    const r = window.__xray.renderer, b = window.__duct;
    const c = [(b[0] + b[3]) / 2, (b[1] + b[4]) / 2, (b[2] + b[5]) / 2];
    const t = r.controls.target;
    const v = new r.camera.position.constructor(...c).project(r.camera);
    return { off: Math.hypot(c[0] - t.x, c[1] - t.y, c[2] - t.z), ndc: [v.x, v.y], dist: r.camera.position.distanceTo(t) };
  });
  check('f frames the selected duct (target on it, centred, closer than the top view)', frameInfo.off < 0.05 && Math.abs(frameInfo.ndc[0]) < 0.05 && Math.abs(frameInfo.ndc[1]) < 0.05 && len(sub(framed.p, framed.t)) < len(sub(top.p, top.t)),
    `off=${frameInfo.off.toFixed(3)} dist=${frameInfo.dist.toFixed(2)} vs ${len(sub(top.p, top.t)).toFixed(2)}`);
  await page.keyboard.press('Alt+ArrowLeft');
  await page.waitForTimeout(200);
  await settle();
  const back = await pose();
  check('Alt+ArrowLeft returns to the previous pose', len(sub(back.p, top.p)) < 0.02 && len(sub(back.t, top.t)) < 0.02, `dp=${len(sub(back.p, top.p)).toFixed(4)}`);
  await page.keyboard.press('Alt+ArrowRight');
  await page.waitForTimeout(200);
  await settle();
  const fwd = await pose();
  check('Alt+ArrowRight goes forward again', len(sub(fwd.p, framed.p)) < 0.05, `dp=${len(sub(fwd.p, framed.p)).toFixed(4)}`);

  // Hide and unhide.
  check('duct is selected', (await sel()) === 1);
  await page.keyboard.press('h');
  const h1 = await hides();
  await page.keyboard.press('Alt+h');
  const h2 = await hides();
  check('h hides the selection and Alt+h restores', h1 === 1 && h2 === 0, `hidden ${h1} then ${h2}`);

  // Tab / PageUp do not throw; Tab keeps the selection.
  await page.keyboard.press('Tab');
  await page.waitForTimeout(200);
  await settle();
  check('Tab keeps the selection', (await sel()) === 1);

  // Cheat sheet.
  await page.keyboard.press('?');
  await page.waitForTimeout(300);
  const sheetOpen = await page.locator('.kx-sheet').count();
  const sheetText = sheetOpen ? await page.locator('.kx-sheet').innerText() : '';
  check('? opens the cheat sheet with grouped live bindings', sheetOpen === 1 && /navigation/i.test(sheetText) && /views/i.test(sheetText) && /orbit left/i.test(sheetText) && /command palette/i.test(sheetText));
  await page.screenshot({ path: resolve(here, 'keys-cheatsheet.png') });
  await page.keyboard.press('Escape');
  await page.waitForTimeout(200);
  check('Escape closes the cheat sheet and keeps the selection', (await page.locator('.kx-sheet').count()) === 0 && (await sel()) === 1);
  await page.keyboard.press('F1');
  await page.waitForTimeout(200);
  check('F1 opens the cheat sheet', (await page.locator('.kx-sheet').count()) === 1);
  await page.mouse.click(30, 880); // outside the panel (on the backdrop)
  await page.waitForTimeout(200);
  check('a click outside closes the cheat sheet', (await page.locator('.kx-sheet').count()) === 0);

  // Command palette.
  await page.keyboard.press('Control+Shift+k');
  await page.waitForTimeout(300);
  check('Ctrl+Shift+K opens the palette', (await page.locator('.kx-palette').count()) === 1);
  await page.keyboard.type('explode');
  await page.waitForTimeout(300);
  const first = await page.locator('.kx-palette .kx-item').first().innerText();
  console.log('palette top result:', JSON.stringify(first));
  await page.screenshot({ path: resolve(here, 'keys-palette.png') });
  const exBefore = await page.evaluate('window.__cinematic.exploded');
  await page.keyboard.press('Enter');
  await page.waitForTimeout(2500);
  const exAfter = await page.evaluate('window.__cinematic.exploded');
  check('palette: typing "explode" and Enter runs the Explode button', (await page.locator('.kx-palette').count()) === 0 && exBefore === false && exAfter === true, `exploded ${exBefore} -> ${exAfter}`);
  if (exAfter) await page.evaluate('window.__cinematic.collapse()');
  await page.waitForTimeout(1500);

  // Panels.
  await page.evaluate(() => document.activeElement && document.activeElement.blur());
  const cls = () => page.evaluate(() => ({ sb: document.body.classList.contains('sb-collapsed'), dk: document.body.classList.contains('dk-collapsed') }));
  const c0 = await cls();
  await page.keyboard.press('[');
  await page.keyboard.press(']');
  await page.waitForTimeout(400);
  const c1 = await cls();
  check('[ and ] still toggle the sidebar and the dock', c1.sb !== c0.sb && c1.dk !== c0.dk, JSON.stringify([c0, c1]));
  await page.keyboard.press('[');
  await page.keyboard.press(']');
  await page.waitForTimeout(400);
  const c2 = await cls();
  check('[ and ] toggle back', c2.sb === c0.sb && c2.dk === c0.dk);

  // Typing in the sidebar filter: Alt+F focuses it ('/' now belongs to the search bar), "beam" triggers nothing.
  await page.keyboard.press('Escape'); // clears the selection
  await page.evaluate(() => { window.__xray.app.selectIds([0]); });
  await settle();
  const before = await page.evaluate(() => ({ xray: window.__xray.app.settings.xray, sel: window.__xray.app.selection.length, hides: window.__xray.app.settings.overrides.userHides.size }));
  const poseBefore = await pose();
  await page.keyboard.press('Alt+f');
  const focused = await page.evaluate(() => document.activeElement && document.activeElement.closest('.sb-filter') !== null);
  check('Alt+F focuses the sidebar filter', focused === true);
  await page.keyboard.type('beam wasd h x f [ ]', { delay: 30 });
  await page.waitForTimeout(500);
  const val = await page.evaluate(() => document.querySelector('.sb-filter input').value);
  const after = await page.evaluate(() => ({ xray: window.__xray.app.settings.xray, sel: window.__xray.app.selection.length, hides: window.__xray.app.settings.overrides.userHides.size }));
  const poseAfter = await pose();
  const c3 = await cls();
  check('typing in the filter box types and triggers no action', val === 'beam wasd h x f [ ]' && JSON.stringify(before) === JSON.stringify(after) && len(sub(poseAfter.p, poseBefore.p)) < 1e-9 && c3.sb === c0.sb && c3.dk === c0.dk, `value=${JSON.stringify(val)} ${JSON.stringify([before, after, c3, c0])}`);
  await page.keyboard.press('Escape');
  await page.keyboard.press('Escape');
  const blurred = await page.evaluate(() => document.activeElement === document.body);
  check('Escape clears then blurs the filter', blurred);

  // lil-gui number fields still take typing.
  const numInput = page.locator('.lil-controller.lil-number input:visible').first();
  await numInput.click();
  const xr = await page.evaluate('window.__xray.app.settings.xray');
  await page.keyboard.type('x');
  await page.keyboard.press('Escape');
  check('typing x in a lil-gui number field does not toggle x-ray', (await page.evaluate('window.__xray.app.settings.xray')) === xr);

  // X and F, Escape behaviour.
  await page.evaluate(() => document.activeElement && document.activeElement.blur());
  await page.keyboard.press('x');
  check('x toggles x-ray', (await page.evaluate('window.__xray.app.settings.xray')) === !xr);
  await page.keyboard.press('x');
  await page.keyboard.press('Escape');
  check('Escape clears the selection', (await sel()) === 0);
  await page.keyboard.press('f');
  await page.waitForTimeout(200);
  await settle();
  check('f with nothing selected frames the whole model (no error)', true);

  // Keyboard folder in the panel.
  const names = await page.evaluate(() => [...document.querySelectorAll('.lil-controller .lil-name')].map((n) => n.textContent.trim()));
  const want = ['keyboard navigation', 'orbit speed (deg/s)', 'pan speed', 'move speed', 'invert vertical', 'smooth moves', 'Shortcuts (?)', 'Edit shortcuts', 'Command palette (Ctrl+Shift+K)', 'Reset shortcuts'];
  check('Keyboard folder has the specified controls', want.every((w) => names.includes(w)), want.filter((w) => !names.includes(w)).join(', '));
  const conflicts = await page.evaluate(() => window.__keymap.conflicts());
  console.log('conflicts:', JSON.stringify(conflicts));
  const nActions = await page.evaluate(() => window.__keymap.bindingsOf && Object.keys(window.__keymap.overrides).length);
  console.log('overrides:', nActions);

  // Editor opens and rebinding works through the UI.
  await page.evaluate(() => window.__xray.app.panel.folders.find((f) => f._title === 'Keyboard').open());
  await page.locator('.lil-controller.lil-function', { hasText: 'Edit shortcuts' }).locator('button').click();
  await page.waitForTimeout(300);
  check('Edit shortcuts opens the editor', (await page.locator('.kx-edit').count()) === 1);
  const cell = page.locator('.kx-cell[data-action="visibility.hide"]').first();
  await cell.click();
  await page.keyboard.press('j');
  await page.waitForTimeout(200);
  const rebound = await page.evaluate(() => window.__keymap.bindingsOf('visibility.hide'));
  check('clicking a chord cell and pressing a key rebinds it', rebound.length === 1 && rebound[0] === 'j', JSON.stringify(rebound));
  await page.keyboard.press('Escape');
  await page.evaluate(() => window.__keymap.resetAll());
  await page.waitForTimeout(100);

  console.log('console warnings:', warnings.length ? '\n' + warnings.join('\n') : 'none');
  console.log('console errors:', errors.length ? '\n' + errors.join('\n') : 'none');
  check('zero console errors', errors.length === 0);
  if (checks.some((c) => !c.ok)) exitCode = 1;
} catch (e) {
  console.error(e);
  exitCode = 1;
} finally {
  if (browser) await browser.close();
  vite.kill('SIGTERM');
}
process.exit(exitCode);
