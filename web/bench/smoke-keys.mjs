// Headless smoke test for keyboard navigation: starts vite (bench/vite.smoke.config.mjs), loads /?model=building at
// 1600x900 and drives the keys with Playwright. Checks held orbit and fly keys, standard views, selection-aware
// framing, the view history, hide/unhide, the cheat sheet, the command palette, the panel toggles and that typing in
// the sidebar filter triggers no action. Navigation (BIM style, Walk mode): w a s d inert by default, Shift+W Walk mode (chip, horizontal
// move at constant height, ArrowLeft turns, drag looks, Esc leaves), the Game style, wheel zoom to the cursor, double-click fly-to,
// middle-drag pan, Shift+middle orbit about the grabbed point, middle double-click frames all.
// Screenshots: bench/keys-cheatsheet.png, bench/keys-palette.png.
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
  // Hold for at least `ms` and until the camera has moved (at most 3 s): on a slow software renderer the page can stall for a moment
  // and draw no frame inside a short hold, which tests the frame rate, not the key.
  const holdUntilMoved = async (key, ms) => {
    const p0 = JSON.stringify(await pose());
    await page.keyboard.down(key);
    await page.waitForTimeout(ms);
    for (let i = 0; i < 27 && JSON.stringify(await pose()) === p0; i++) await page.waitForTimeout(100);
    await page.keyboard.up(key);
    await page.waitForTimeout(150);
  };
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

  // BIM style (the default): w a s d q e do nothing until Walk mode (or the Game style) is on.
  a = await pose();
  for (const k of ['w', 'a', 's', 'd', 'q', 'e']) await hold(k, 250);
  b = await pose();
  check('w a s d q e are inert in the default BIM style', len(sub(b.p, a.p)) < 1e-9 && len(sub(b.t, a.t)) < 1e-9, `moved ${len(sub(b.p, a.p)).toExponential(2)} m`);
  const actionsKept = await page.evaluate(() => ['nav.forward', 'nav.back', 'nav.left', 'nav.right', 'nav.up', 'nav.down'].map((id) => window.__keymap.bindingsOf(id).join()).join(' '));
  check('the fly actions keep their ids and chords (custom keymaps still work)', actionsKept === 'w s a d e q', actionsKept);

  // Game style: w a s d q e fly the camera and its target at all times (the old behaviour).
  const setStyle = (v) => page.evaluate((v) => {
    const f = window.__xray.app.panel.folders.find((x) => x._title === 'Keyboard');
    f.controllers.find((c) => c.property === 'style').setValue(v);
  }, v);
  await setStyle('game');
  a = await pose();
  await holdUntilMoved('w', 300);
  b = await pose();
  const dp = sub(b.p, a.p), dt = sub(b.t, a.t);
  check('Game style: w held moves position and target together', len(dp) > 0.005 && len(sub(dp, dt)) < 1e-6, `move=${len(dp).toFixed(3)} m`);
  check('the style is kept in localStorage xray.keynav only', (await page.evaluate(() => JSON.parse(localStorage.getItem('xray.keynav')).style)) === 'game' && !(await page.evaluate(() => JSON.stringify(window.__xrayParams?.collect?.() ?? {}).includes('"game"'))));
  await setStyle('bim');

  // Walk mode.
  const lookY = (s) => look(s)[1];
  const yawLook = (s) => { const l = look(s); return Math.atan2(-l[0], -l[2]); };
  await page.keyboard.press('Shift+w');
  await page.waitForTimeout(300);
  const walkInfo = () => page.evaluate(() => {
    const chip = document.getElementById('xray-walk-chip');
    const r = chip.getBoundingClientRect();
    return { shown: getComputedStyle(chip).display !== 'none', text: chip.textContent, rect: [r.left, r.top, r.right, r.bottom], walk: document.getElementById('c').dataset.walk, pressed: document.querySelector('#xray-gizmo .xg-walk')?.getAttribute('aria-pressed'), enabled: window.__xray.app.renderer.controls.enabled };
  });
  let wi = await walkInfo();
  check('Shift+W enters Walk mode: chip, cursor flag, gizmo button, orbit controls off', wi.shown && /Walk · Esc to exit/.test(wi.text) && wi.walk === '1' && wi.pressed === 'true' && wi.enabled === false, JSON.stringify(wi));
  a = await pose();
  const fwdH = (s) => { const l = look(s); const h = Math.hypot(l[0], l[2]) || 1; return [l[0] / h, l[2] / h]; };
  await holdUntilMoved('w', 400);
  b = await pose();
  const mv = sub(b.p, a.p);
  const f0 = fwdH(a);
  const along = (mv[0] * f0[0] + mv[2] * f0[1]) / (Math.hypot(mv[0], mv[2]) || 1);
  check('w in Walk mode moves along the horizontal view direction at constant height', Math.hypot(mv[0], mv[2]) > 0.01 && Math.abs(mv[1]) < 1e-6 && along > 0.99, `move=${len(mv).toFixed(3)} dy=${mv[1].toExponential(2)} cos=${along.toFixed(4)}`);
  check('Walk mode keeps the orbit target a fixed distance in front of the eye', Math.abs(len(sub(b.t, b.p)) - len(sub(a.t, a.p))) < 1e-3 && look(b).every((v, i) => Math.abs(v - look(a)[i]) < 1e-6));
  a = b;
  await hold('s', 300);
  b = await pose();
  check('s walks back', (sub(b.p, a.p)[0] * f0[0] + sub(b.p, a.p)[2] * f0[1]) < -0.005);
  a = await pose();
  await hold('d', 300);
  b = await pose();
  const sd = sub(b.p, a.p);
  check('d strafes to the right at constant height', Math.abs(sd[1]) < 1e-6 && len(sd) > 0.005 && (sd[0] * -f0[1] + sd[2] * f0[0]) > 0.005 * 0.99, `d=${sd.map((v) => v.toFixed(3))}`);
  a = await pose();
  await holdUntilMoved('e', 300);
  b = await pose();
  check('e raises the eye', sub(b.p, a.p)[1] > 0.005);
  await holdUntilMoved('q', 300);
  a = await pose();
  await holdUntilMoved('ArrowUp', 300);
  b = await pose();
  const up1 = sub(b.p, a.p);
  check('ArrowUp walks forward too', Math.hypot(up1[0], up1[2]) > 0.005 && Math.abs(up1[1]) < 1e-6);
  a = await pose();
  await holdUntilMoved('ArrowLeft', 300);
  b = await pose();
  let dyaw2 = yawLook(b) - yawLook(a);
  if (dyaw2 < -Math.PI) dyaw2 += 2 * Math.PI;
  check('ArrowLeft turns the view left about the eye', dyaw2 > 0.05 && len(sub(b.p, a.p)) < 1e-6 && Math.abs(lookY(b) - lookY(a)) < 1e-6, `dyaw=${dyaw2.toFixed(3)}`);
  a = await pose();
  await holdUntilMoved('ArrowRight', 300);
  b = await pose();
  let dyaw3 = yawLook(b) - yawLook(a);
  if (dyaw3 > Math.PI) dyaw3 -= 2 * Math.PI;
  check('ArrowRight turns the view right', dyaw3 < -0.05 && len(sub(b.p, a.p)) < 1e-6);
  // Shift is 3x faster: the same hold turns further.
  await page.keyboard.down('Shift');
  a = await pose();
  await page.keyboard.down('ArrowLeft');
  await page.waitForTimeout(400);
  await page.keyboard.up('ArrowLeft');
  await page.keyboard.up('Shift');
  b = await pose();
  let dyaw4 = yawLook(b) - yawLook(a);
  if (dyaw4 < -Math.PI) dyaw4 += 2 * Math.PI;
  check('Shift+ArrowLeft turns too, faster', dyaw4 > dyaw2 * 1.2, `${dyaw4.toFixed(3)} vs ${dyaw2.toFixed(3)} rad`);

  // A left drag looks around from the eye; the eye stays, the pitch is clamped to 85 degrees.
  const cvs = await page.evaluate(() => { const r = document.getElementById('c').getBoundingClientRect(); return { x: r.left, y: r.top, w: r.width, h: r.height }; });
  const cx0 = cvs.x + cvs.w * 0.45, cy0 = cvs.y + cvs.h * 0.45;
  a = await pose();
  await page.mouse.move(cx0, cy0);
  await page.mouse.down();
  await page.mouse.move(cx0 + 120, cy0 - 40, { steps: 6 });
  await page.mouse.up();
  await page.waitForTimeout(300);
  b = await pose();
  check('a left drag looks around from the eye (position fixed, yaw and pitch change)', len(sub(b.p, a.p)) < 1e-6 && Math.abs(yawLook(b) - yawLook(a)) > 0.05 && Math.abs(lookY(b) - lookY(a)) > 0.01, `dyaw=${(yawLook(b) - yawLook(a)).toFixed(3)} dy=${(lookY(b) - lookY(a)).toFixed(3)}`);
  const dragBy = async (dy) => {
    const y0 = dy > 0 ? cvs.y + 120 : cvs.y + cvs.h - 120; // below the 32 px top bar, clear of the Walk chip
    await page.mouse.move(cvs.x + cvs.w * 0.3, y0);
    await page.mouse.down();
    for (let i = 1; i <= 8; i++) await page.mouse.move(cvs.x + cvs.w * 0.3, y0 + (dy * i) / 8, { steps: 2 });
    await page.mouse.up();
    await page.waitForTimeout(200);
  };
  for (let i = 0; i < 4; i++) await dragBy(800);
  b = await pose();
  const pitchUp = (Math.asin(look(b)[1]) * 180) / Math.PI;
  for (let i = 0; i < 8; i++) await dragBy(-800);
  b = await pose();
  const pitchDown = (Math.asin(look(b)[1]) * 180) / Math.PI;
  check('the pitch is clamped to 85 degrees (up and down)', pitchUp > 84 && pitchUp <= 85.01 && pitchDown < -84 && pitchDown >= -85.01, `up=${pitchUp.toFixed(2)} down=${pitchDown.toFixed(2)}`);
  await dragBy(300);
  // The wheel walks forward and back.
  a = await pose();
  await page.evaluate(() => { const c = document.getElementById('c'); const r = c.getBoundingClientRect(); for (let i = 0; i < 4; i++) c.dispatchEvent(new WheelEvent('wheel', { deltaY: -100, bubbles: true, cancelable: true, clientX: r.left + r.width / 2, clientY: r.top + r.height / 2 })); });
  await page.waitForTimeout(300);
  b = await pose();
  check('the wheel walks forward in Walk mode (eye height kept)', Math.hypot(b.p[0] - a.p[0], b.p[2] - a.p[2]) > 0.01 && Math.abs(b.p[1] - a.p[1]) < 1e-6);
  // Walking is one camera history entry for the undo stack, not one per frame.
  await page.waitForTimeout(1800);
  const undoN0 = await page.evaluate(() => window.__xrayUndo.list().undo.length);
  await holdUntilMoved('w', 600);
  await page.waitForTimeout(2200);
  const undoN1 = await page.evaluate(() => window.__xrayUndo.list().undo.length);
  check('a walk is one undo entry', undoN1 === undoN0 + 1, `${undoN0} -> ${undoN1}`);
  // Walk mode is not in the params, nor the share link.
  const leak = await page.evaluate(() => /walk/i.test(JSON.stringify(window.__xrayParams?.collect?.() ?? {})) || /walk/i.test(location.hash));
  check('Walk mode is not in the params or the share link', leak === false);

  // Esc leaves Walk mode first, the selection stays; the next Esc clears it.
  await page.evaluate(() => { window.__xray.app.selectIds([0]); });
  await page.keyboard.press('Escape');
  await page.waitForTimeout(200);
  wi = await walkInfo();
  check('Esc leaves Walk mode and keeps the selection', !wi.shown && wi.walk === undefined && wi.pressed === 'false' && wi.enabled === true && (await sel()) === 1, JSON.stringify(wi));
  await page.keyboard.press('Escape');
  check('the next Esc clears the selection', (await sel()) === 0);
  // Shift+W and the gizmo button toggle it; leaving keeps a sane orbit (target in front of the eye).
  await page.keyboard.press('Shift+w');
  check('Shift+W enters again', (await walkInfo()).shown);
  await page.keyboard.press('Shift+w');
  check('Shift+W leaves', !(await walkInfo()).shown);
  await page.locator('#xray-gizmo .xg-walk').click();
  check('the gizmo button enters Walk mode', (await walkInfo()).shown);
  await page.locator('#xray-gizmo .xg-walk').click();
  check('the gizmo button leaves Walk mode', !(await walkInfo()).shown);
  await page.keyboard.press('Shift+w');
  a = await pose();
  await page.keyboard.press('Escape');
  await page.keyboard.down('ArrowLeft');
  await page.waitForTimeout(300);
  await page.keyboard.up('ArrowLeft');
  b = await pose();
  check('after Walk mode ArrowLeft orbits about the target again', Math.abs(len(sub(b.p, b.t)) - len(sub(a.p, a.t))) < 1e-3 && len(sub(b.p, a.p)) > 1e-4);
  // A playing film ends Walk mode and the walk keys do nothing.
  const filmOk = await page.evaluate(async () => {
    const fly = window.__xrayFlythrough;
    if (!fly) return 'no api';
    try {
      fly.add({});
      const r = window.__xray.renderer;
      r.camera.position.x += 3;
      r.controls.update();
      fly.add({});
      fly.play({});
    } catch (e) { return String(e); }
    return fly.state().playing ? 'playing' : 'not playing';
  });
  if (filmOk === 'playing') {
    await page.keyboard.press('Shift+w');
    await page.waitForTimeout(200);
    check('Shift+W does nothing while a film plays', !(await walkInfo()).shown);
    await page.evaluate(() => window.__xrayFlythrough.stop());
    await page.keyboard.press('Shift+w');
    await page.evaluate(() => { window.__xrayFlythrough.play({}); });
    await page.waitForTimeout(600);
    check('a film that starts ends Walk mode', !(await walkInfo()).shown);
    await page.evaluate(() => { window.__xrayFlythrough.stop(); window.__xrayFlythrough.clear(); });
  } else console.log('film check skipped:', filmOk);
  await settle();

  // Wheel zooms toward the cursor: the point under the cursor stays under it. Find a surface point off the centre.
  await page.keyboard.press('Home');
  await settle();
  const spot = await page.evaluate(() => {
    const r = window.__xray.renderer, c = document.getElementById('c'), cr = c.getBoundingClientRect();
    for (const fy of [0.55, 0.45, 0.65, 0.35, 0.5]) for (const fx of [0.7, 0.3, 0.62, 0.38, 0.8, 0.2]) {
      const x = cr.left + cr.width * fx, y = cr.top + cr.height * fy;
      const id = r.pick(fx * 2 - 1, -(fy * 2 - 1));
      if (id !== null) return { x, y, id, dist: r.lastPickDistance, fx, fy };
    }
    return null;
  });
  check('found a surface point off the centre for the cursor tests', !!spot);
  if (spot) {
    await page.evaluate(() => { window.__xray.app.clearSelection(); });
    const world = await page.evaluate((sp) => {
      const r = window.__xray.renderer; r.camera.updateMatrixWorld();
      const o = r.camera.position.clone();
      const d = new o.constructor(sp.fx * 2 - 1, -(sp.fy * 2 - 1), 0.5).unproject(r.camera).sub(o).normalize();
      const p = o.clone().addScaledVector(d, sp.dist);
      window.__probe = p;
      return [p.x, p.y, p.z];
    }, spot);
    const screenOf = () => page.evaluate(() => {
      const r = window.__xray.renderer, c = document.getElementById('c'), cr = c.getBoundingClientRect();
      r.camera.updateMatrixWorld();
      const v = window.__probe.clone().project(r.camera);
      return { x: cr.left + ((v.x + 1) / 2) * cr.width, y: cr.top + ((1 - v.y) / 2) * cr.height, d: r.camera.position.distanceTo(window.__probe) };
    });
    const s0 = await screenOf();
    await page.evaluate((sp) => {
      const c = document.getElementById('c');
      for (let i = 0; i < 5; i++) c.dispatchEvent(new WheelEvent('wheel', { deltaY: -120, bubbles: true, cancelable: true, clientX: sp.x, clientY: sp.y }));
    }, spot);
    await page.waitForTimeout(500);
    await settle();
    const s1 = await screenOf();
    check('wheel zooms toward the cursor: the point under it stays within 4 px', Math.hypot(s1.x - spot.x, s1.y - spot.y) < 4 && s1.d < s0.d * 0.9, `moved ${Math.hypot(s1.x - spot.x, s1.y - spot.y).toFixed(2)} px, dist ${s0.d.toFixed(2)} -> ${s1.d.toFixed(2)}`);

    // Middle drag pans: the view direction and the distance stay.
    await page.keyboard.press('Home');
    await settle();
    a = await pose();
    await page.mouse.move(cx0, cy0);
    await page.mouse.down({ button: 'middle' });
    await page.mouse.move(cx0 + 100, cy0 + 40, { steps: 6 });
    await page.mouse.up({ button: 'middle' });
    await page.waitForTimeout(600);
    await settle();
    b = await pose();
    check('middle drag pans (view direction and distance unchanged)', len(sub(b.p, a.p)) > 0.05 && look(b).every((v, i) => Math.abs(v - look(a)[i]) < 1e-3) && Math.abs(len(sub(b.p, b.t)) - len(sub(a.p, a.t))) < 1e-3, `pan=${len(sub(b.p, a.p)).toFixed(3)}`);

    // Shift + middle drag orbits about the point under the cursor: the target moves along the view ray to its depth, the view does not jump.
    await page.keyboard.press('Home');
    await settle();
    const spot2 = await page.evaluate(() => {
      const r = window.__xray.renderer, cr = document.getElementById('c').getBoundingClientRect();
      for (const fy of [0.5, 0.55, 0.45, 0.6, 0.4]) for (const fx of [0.5, 0.45, 0.55, 0.4, 0.6, 0.35]) {
        const id = r.pick(fx * 2 - 1, -(fy * 2 - 1));
        if (id !== null) {
          const o = r.camera.position.clone();
          r.camera.updateMatrixWorld();
          const d = new o.constructor(fx * 2 - 1, -(fy * 2 - 1), 0.5).unproject(r.camera).sub(o).normalize();
          const hit = o.clone().addScaledVector(d, r.lastPickDistance);
          const fwd = r.camera.getWorldDirection(new o.constructor());
          return { x: cr.left + cr.width * fx, y: cr.top + cr.height * fy, depth: hit.clone().sub(o).dot(fwd) };
        }
      }
      return null;
    });
    if (spot2) {
      a = await pose();
      await page.keyboard.down('Shift');
      await page.mouse.move(spot2.x, spot2.y);
      await page.mouse.down({ button: 'middle' });
      await page.waitForTimeout(100);
      const pressed2 = await pose();
      check('a press without a drag leaves the camera and the target alone (a click does not retarget)', len(sub(pressed2.p, a.p)) < 1e-9 && len(sub(pressed2.t, a.t)) < 1e-9);
      await page.mouse.move(spot2.x + 6, spot2.y, { steps: 2 });
      await page.waitForTimeout(400);
      const grabbed = await pose();
      check('orbit start: the target moves to the depth of the grabbed point and the view does not jump', len(sub(grabbed.p, a.p)) < 0.2 * spot2.depth && Math.abs(len(sub(grabbed.t, grabbed.p)) - spot2.depth) < Math.max(0.05, spot2.depth * 0.02), `target dist ${len(sub(grabbed.t, grabbed.p)).toFixed(3)} vs depth ${spot2.depth.toFixed(3)}, camera moved ${len(sub(grabbed.p, a.p)).toFixed(3)}`);
      await page.mouse.move(spot2.x + 90, spot2.y + 20, { steps: 6 });
      await page.mouse.up({ button: 'middle' });
      await page.keyboard.up('Shift');
      await page.waitForTimeout(500);
      await settle();
      b = await pose();
      check('Shift + middle drag orbits about that point (distance to it kept, view turned)', Math.abs(len(sub(b.p, b.t)) - len(sub(grabbed.p, grabbed.t))) < 0.02 && look(b).some((v, i) => Math.abs(v - look(a)[i]) > 0.02));
    }

    // Double-click on an element selects it and flies to it; on empty space nothing happens.
    await page.keyboard.press('Home');
    await settle();
    const hit = await page.evaluate(() => {
      const r = window.__xray.renderer, cr = document.getElementById('c').getBoundingClientRect();
      for (const fy of [0.5, 0.6, 0.4, 0.7, 0.3]) for (const fx of [0.5, 0.4, 0.6, 0.3, 0.7]) {
        const id = r.pick(fx * 2 - 1, -(fy * 2 - 1));
        if (id !== null) { const b = window.__xray.app.loaded.model.elements[id].bounds; return { x: cr.left + cr.width * fx, y: cr.top + cr.height * fy, id, c: [(b[0] + b[3]) / 2, (b[1] + b[4]) / 2, (b[2] + b[5]) / 2] }; }
      }
      return null;
    });
    const empty = await page.evaluate(() => {
      const r = window.__xray.renderer, cr = document.getElementById('c').getBoundingClientRect();
      for (const [fx, fy] of [[0.02, 0.1], [0.98, 0.1], [0.02, 0.5], [0.5, 0.02]]) if (r.pick(fx * 2 - 1, -(fy * 2 - 1)) === null) return { x: cr.left + cr.width * fx, y: cr.top + cr.height * fy };
      return null;
    });
    if (empty) {
      a = await pose();
      await page.mouse.dblclick(empty.x, empty.y);
      await page.waitForTimeout(600);
      await settle();
      b = await pose();
      check('double-click on empty space does nothing', len(sub(b.p, a.p)) < 1e-6 && (await sel()) === 0);
    }
    if (hit) {
      a = await pose();
      await page.mouse.dblclick(hit.x, hit.y);
      await page.waitForTimeout(300);
      await settle();
      b = await pose();
      const fl = await page.evaluate(() => ({ sel: window.__xray.app.selection.slice(), t: window.__xray.renderer.controls.target.toArray() }));
      check('double-click on an element selects it and flies to it (target on its centre)', fl.sel.length === 1 && fl.sel[0] === hit.id && len(sub(fl.t, hit.c)) < 0.3 && len(sub(b.p, a.p)) > 0.05, `sel=${fl.sel} off=${len(sub(fl.t, hit.c)).toFixed(3)}`);
      // Middle double-click frames everything (Home).
      await page.keyboard.press('Home');
      await settle();
      const home = await pose();
      await page.mouse.dblclick(hit.x, hit.y);
      await page.waitForTimeout(300);
      await settle();
      const near = await pose();
      await page.mouse.dblclick(cx0, cy0, { button: 'middle' });
      await page.waitForTimeout(300);
      await settle();
      const framed2 = await pose();
      check('middle double-click frames everything', len(sub(near.p, home.p)) > 0.5 && len(sub(framed2.p, home.p)) < 0.05 && len(sub(framed2.t, home.t)) < 0.05, `near=${len(sub(near.p, home.p)).toFixed(2)} back=${len(sub(framed2.p, home.p)).toFixed(3)}`);
    }
  }

  // Walk chip at phone width (a fresh phone page, so the sidebars start collapsed): inside the view, clear of the gizmo and the top bar.
  {
    const ph = await browser.newPage({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
    ph.on('pageerror', (e) => errors.push(`[phone pageerror] ${e.message}`));
    await ph.goto(`http://127.0.0.1:${port}/?model=building`);
    await ph.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: 120000 });
    await ph.waitForTimeout(1500);
    await ph.locator('#xray-gizmo .xg-walk').click();
    await ph.waitForTimeout(300);
    const phoneChip = await ph.evaluate(() => {
      const chip = document.getElementById('xray-walk-chip');
      const r = chip.getBoundingClientRect();
      const g = document.getElementById('xray-gizmo').getBoundingClientRect();
      const t = document.getElementById('xray-topbar').getBoundingClientRect();
      const hits = (o) => !(r.right <= o.left || r.left >= o.right || r.bottom <= o.top || r.top >= o.bottom);
      return { shown: getComputedStyle(chip).display !== 'none', l: r.left, r: r.right, t: r.top, w: r.width, overlapsGizmo: hits(g), overlapsTopbar: hits(t), vw: innerWidth };
    });
    check('the Walk chip fits at 390 px width and covers neither the gizmo nor the top bar', phoneChip.shown && phoneChip.l >= 0 && phoneChip.r <= phoneChip.vw && !phoneChip.overlapsGizmo && !phoneChip.overlapsTopbar, JSON.stringify(phoneChip));
    // One finger looks around (touch drag), the eye stays.
    const before = await ph.evaluate(() => { const c = window.__xray.renderer.camera; return [c.position.x, c.position.y, c.position.z, ...c.getWorldDirection(new c.position.constructor()).toArray()]; });
    const cdp = await ph.context().newCDPSession(ph);
    const touch = (type, x, y) => cdp.send('Input.dispatchTouchEvent', { type, touchPoints: type === 'touchEnd' ? [] : [{ x, y, id: 1 }] });
    await touch('touchStart', 120, 400);
    for (let i = 1; i <= 8; i++) await touch('touchMove', 120 + i * 10, 400 + i * 4);
    await touch('touchEnd', 200, 432);
    await ph.waitForTimeout(400);
    const after = await ph.evaluate(() => { const c = window.__xray.renderer.camera; return [c.position.x, c.position.y, c.position.z, ...c.getWorldDirection(new c.position.constructor()).toArray()]; });
    check('walk: one finger looks around from the eye', Math.hypot(after[0] - before[0], after[1] - before[1], after[2] - before[2]) < 1e-6 && Math.hypot(after[3] - before[3], after[4] - before[4], after[5] - before[5]) > 0.02, `dlook=${Math.hypot(after[3] - before[3], after[4] - before[4], after[5] - before[5]).toFixed(3)}`);
    await ph.screenshot({ path: resolve(here, 'keys-walk-phone.png') });
    await ph.close();
  }

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

  // lil-gui number fields still take typing. (The panel is the Parameters tab of the right sidebar; the default tab is Properties.)
  await page.evaluate(() => window.__xrayRightSidebar.open('parameters'));
  await page.waitForTimeout(300);
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
  const want = ['keyboard navigation', 'orbit speed (deg/s)', 'pan speed', 'move speed', 'invert vertical', 'smooth moves', 'navigation style', 'Shortcuts (?)', 'Edit shortcuts', 'Command palette (Ctrl+Shift+K)', 'Reset shortcuts'];
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
