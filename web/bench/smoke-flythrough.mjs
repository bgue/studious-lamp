// Headless smoke test for the fly-through timeline (docs-features/flythrough.md) on fzk-haus, 1280x720 and a phone:
//   - the "Fly-through" section of the Views tab, keyframes added from the current view (thumbnails, camera, hides, selection),
//     the compiled score (camera path, view, select, visibility fades, caption cues) and the keyframe times;
//   - the 3D camera path overlay: drawn with the Views tab open, off during playback;
//   - playback: the camera moves between the keyframes, a selection starts before arrival, hidden elements fade (alpha between
//     0 and its base), a caption shows during a hold, pause / Space / Left / Right / Escape, restore of camera, selection, hides;
//     a press on the canvas stops it and the camera stays;
//   - the score player takes a hand-written score with every cue kind (param, preset, camera frame by query, visibility, select);
//   - migration of the old `xray.flythrough.<modelName>` keyframes into "Imported", persistence under the identity key,
//     keyframes from selection sets, window.__cinematic.keys / record, a recording;
//   - the phone layout (cards wrap, no horizontal scroll).
// Screenshots: bench/flythrough-panel.png, flythrough-play.png, flythrough-phone.png. No console errors.
// Usage: SMOKE_PORT=5800 XRAY_VITE_CACHE_DIR=/tmp/xray-ft-cache node bench/smoke-flythrough.mjs        (SMOKE_REUSE=1 uses a server already on that port)
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const port = Number(process.env.SMOKE_PORT ?? 5800);
const base = `http://127.0.0.1:${port}`;

function loadPlaywright() {
  const candidates = [process.env.PLAYWRIGHT_MODULE, resolve(root, 'node_modules/playwright'), '/opt/node-tools/node_modules/playwright', '/opt/node22/lib/node_modules/playwright', 'playwright'].filter(Boolean);
  for (const c of candidates) {
    try { return createRequire(import.meta.url)(c); } catch { /* try next */ }
  }
  throw new Error('playwright not found; set PLAYWRIGHT_MODULE');
}
const { chromium } = loadPlaywright();

let vite = null;
let viteLog = '';
if (!process.env.SMOKE_REUSE) {
  vite = spawn(resolve(root, 'node_modules/.bin/vite'), ['--config', resolve(here, 'vite.smoke.config.mjs'), '--host', '127.0.0.1', '--port', String(port), '--strictPort'], { cwd: root, stdio: ['ignore', 'pipe', 'pipe'] });
  vite.stdout.on('data', (d) => (viteLog += d));
  vite.stderr.on('data', (d) => (viteLog += d));
}
async function waitForServer() {
  for (let i = 0; i < 100; i++) {
    try { const r = await fetch(`${base}/`); if (r.ok) return; } catch { /* retry */ }
    await new Promise((r) => setTimeout(r, 200));
  }
  throw new Error('vite did not start:\n' + viteLog);
}

const checks = [];
function check(name, ok, detail = '') {
  checks.push({ name, ok: !!ok });
  console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${detail ? ` (${detail})` : ''}`);
}

const errors = [];
function watch(page, label) {
  page.setDefaultTimeout(240000); // software rendering: one frame can take seconds
  page.on('console', (m) => { if (m.type() === 'error') errors.push(`${label}: ${m.text()}`); });
  page.on('pageerror', (e) => errors.push(`${label}: pageerror ${e.message}`));
}

async function ready(page) {
  await page.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: 240000, polling: 500 });
  const err = await page.evaluate('window.__xrayError');
  if (err) throw new Error(`startup failed: ${err}`);
  await page.waitForFunction('!!window.__xrayViews', null, { timeout: 60000, polling: 500 });
}

/** Wait until the camera holds still (two samples 300 ms apart within 1e-5). */
async function settle(page, maxMs = 12000) {
  const t0 = Date.now();
  let last = null;
  while (Date.now() - t0 < maxMs) {
    const c = await page.evaluate(() => window.__xrayViews.camera());
    if (last && dist(c.position, last.position) < 1e-5 && dist(c.target, last.target) < 1e-5) return c;
    last = c;
    await page.waitForTimeout(300);
  }
  return last;
}

/** A screenshot that waits long for a software-rendered frame and never aborts the run. */
async function shot(page, file, opts = {}) {
  try {
    await page.screenshot({ path: resolve(here, file), timeout: 240000, ...opts });
  } catch (e) {
    console.log(`(screenshot ${file} skipped: ${String(e.message ?? e).split('\n')[0]})`);
  }
}

const dist = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);


const FLY = () => window.__xrayFlythrough;

async function openPage(browser, opts = {}) {
  const ctx = await browser.newContext({ viewport: opts.viewport ?? { width: 1280, height: 720 }, ...(opts.ctx ?? {}) });
  const page = await ctx.newPage();
  watch(page, opts.label ?? 'page');
  if (opts.init) await page.addInitScript(opts.init);
  await page.goto(`${base}/?model=fzk-haus`);
  await ready(page);
  await page.waitForFunction('!!window.__xrayFlythrough', null, { timeout: 60000, polling: 300 });
  return { ctx, page };
}

const sleep = (page, ms) => page.waitForTimeout(ms);

async function waitIdle(page, maxMs = 120000) {
  await page.waitForFunction(() => !window.__xrayFlythrough.state().playing, null, { timeout: maxMs, polling: 250 });
}

async function main(browser) {
  // ---------------------------------------------------------------- migration (a context with the old key before the page loads)
  {
    const legacy = JSON.stringify({ schema: 'xray-flythrough/1', model: 'fzk-haus', segmentSeconds: 3, keyframes: [
      { position: [10, 6, 12], target: [0, 1, 0], selection: [], toggles: { reveal: true, ao: true, vignette: false }, name: 'Old A' },
      { position: [-9, 5, 8], target: [0, 1, 0], selection: [], toggles: {}, name: 'Old B' },
    ] });
    const { ctx, page } = await openPage(browser, { label: 'migrate', init: `if (!localStorage.getItem('xray.flythrough.fzk-haus') && !sessionStorage.getItem('ft-seeded')) { localStorage.setItem('xray.flythrough.fzk-haus', ${JSON.stringify(legacy)}); sessionStorage.setItem('ft-seeded', '1'); }` });
    await sleep(page, 800);
    const m = await page.evaluate(() => {
      const f = window.__xrayFlythrough;
      const keys = Object.keys(localStorage).filter((k) => k.startsWith('xray.flythroughs.'));
      return { list: f.list(), keys, legacyKept: localStorage.getItem('xray.flythrough.fzk-haus') !== null, cinKeys: window.__cinematic.keys.map((k) => k.name), params: f.store.active?.keyframes[0].view.params };
    });
    check('migration: the old keyframes become a fly-through named Imported', m.list.length === 1 && m.list[0].name === 'Imported' && m.list[0].keyframes === 2, JSON.stringify(m.list));
    check('migration: stored under the identity key (name|count|hash), not the model name', m.keys.length === 1 && /^xray\.flythroughs\.fzk-haus\|\d+\|/.test(m.keys[0]), m.keys.join(','));
    check('migration: the toggles became settings paths; the old key stays', m.params?.cinematic?.reveal === true && m.params?.post?.ao === true && m.legacyKept, JSON.stringify(m.params));
    check('migration: window.__cinematic.keys still lists the keyframes', JSON.stringify(m.cinKeys) === JSON.stringify(['Old A', 'Old B']), m.cinKeys.join(','));
    await page.reload();
    await ready(page);
    await page.waitForFunction('!!window.__xrayFlythrough', null, { timeout: 60000 });
    await sleep(page, 500);
    const again = await page.evaluate(() => window.__xrayFlythrough.list().map((f) => f.name));
    check('persistence: the fly-through is back after a reload (not imported twice)', again.length === 1 && again[0] === 'Imported', again.join(','));
    // play the imported one briefly: camera moves between the two old keyframes
    const played = await page.evaluate(async () => {
      const f = window.__xrayFlythrough;
      const cam = window.__xray.app.renderer.camera.position;
      const before = cam.toArray();
      const ok = f.play();
      let moved = 0;
      for (let i = 0; i < 120 && f.state().playing; i++) {
        await new Promise((r) => setTimeout(r, 100));
        moved = Math.max(moved, Math.hypot(cam.x - before[0], cam.y - before[1], cam.z - before[2]));
      }
      return { ok, moved, after: cam.toArray(), before, playing: f.state().playing };
    });
    check('migration: the imported fly-through plays and the camera moves', played.ok && played.moved > 1, `moved ${played.moved.toFixed(1)} m`);
    check('migration: the camera is back where it was after the end', dist(played.after, played.before) < 1e-3 && !played.playing, `d ${dist(played.after, played.before).toExponential(1)}`);
    await ctx.close();
  }

  // ---------------------------------------------------------------- the timeline, a new fly-through
  const { ctx, page } = await openPage(browser, { label: 'main' });
  await page.evaluate(() => {
    for (const k of Object.keys(localStorage)) if (k.startsWith('xray.flythrough') || k.startsWith('xray.views.')) localStorage.removeItem(k);
    localStorage.setItem('xray.sidebar', JSON.stringify({ collapsed: false, tab: 'views' }));
  });
  await page.reload();
  await ready(page);
  await page.waitForFunction('!!window.__xrayFlythrough', null, { timeout: 60000 });
  await sleep(page, 500);
  check('the Fly-through section is in the Views tab', await page.evaluate(() => !!document.querySelector('.fl .fl-title') && document.querySelector('.sb-tab.active')?.textContent === 'Views'));

  // Keyframes: A (wide), B (selection + two hidden elements), C (close, hold, caption).
  const view0 = await page.evaluate(() => {
    const app = window.__xray.app;
    window.__xraySection?.clear?.();
    app.clearSelection();
    const r = app.renderer;
    r.camera.position.set(14, 8, 16);
    r.controls.target.set(0, 1, 0);
    r.controls.update();
    return window.__xrayViews.camera();
  });
  await settle(page);
  await page.evaluate(() => window.__xrayFlythrough.create('Smoke'));
  await page.evaluate(() => window.__xrayFlythrough.setOptions({ timing: 'seconds', segmentS: 2 }));
  await page.evaluate(() => window.__xrayFlythrough.add({ name: 'Wide' }));
  await page.evaluate(() => {
    const app = window.__xray.app;
    const r = app.renderer;
    r.camera.position.set(-10, 5, 9);
    r.controls.target.set(-2, 1, 0);
    r.controls.update();
    app.selectIds([22]);
    const h = app.controller.settings.overrides.userHides;
    h.add(0);
    h.add(1);
    app.controller.refreshOverrides();
  });
  await settle(page);
  await page.evaluate(() => window.__xrayFlythrough.add({ name: 'Window', hold: 1, caption: { title: 'The window', text: 'Selected, with two elements hidden' } }));
  await page.evaluate(() => {
    const app = window.__xray.app;
    const r = app.renderer;
    r.camera.position.set(2, 3, 6);
    r.controls.target.set(0, 1.5, 0);
    r.controls.update();
    app.clearSelection();
    const h = app.controller.settings.overrides.userHides;
    h.clear();
    h.add(1);
    h.add(2);
    app.controller.refreshOverrides();
  });
  await settle(page);
  await page.evaluate(() => window.__xrayFlythrough.add({ name: 'Close' }));
  const kf = await page.evaluate(() => ({ keys: window.__xrayFlythrough.keyframes(), tm: window.__xrayFlythrough.timing(), cards: document.querySelectorAll('.fl-card').length, thumbs: document.querySelectorAll('.fl-card img').length, sum: document.querySelector('.fl-sum')?.textContent, stored: Object.keys(localStorage).filter((k) => k.startsWith('xray.flythroughs.')) }));
  check('3 keyframes: cards with pictures, name, summary', kf.keys.length === 3 && kf.cards === 3 && kf.thumbs === 3 && /3 keyframes/.test(kf.sum), `${kf.cards} cards, ${kf.thumbs} pictures, ${kf.sum}`);
  check('keyframe times: 2 s moves and a 1 s hold', Math.abs(kf.tm.arrive[1] - 2) < 1e-6 && Math.abs(kf.tm.depart[1] - 3) < 1e-6 && Math.abs(kf.tm.total - 5) < 1e-6, JSON.stringify(kf.tm));
  const score = await page.evaluate(() => window.__xrayFlythrough.compile());
  const kinds = {};
  for (const c of score.cues) kinds[c.kind] = (kinds[c.kind] ?? 0) + 1;
  const fades = score.cues.filter((c) => c.kind === 'visibility' && c.dur > 0);
  check('compiled score: one camera path, a view cue per keyframe, select, visibility fades, one caption', kinds.cameraPath === 1 && kinds.view === 3 && kinds.select >= 2 && fades.length === 2 && kinds.caption === 1, JSON.stringify(kinds));
  check('compiled score: the fades are the last 40 % of the 2 s moves', fades.every((c) => Math.abs(c.dur - 0.8) < 1e-6), fades.map((c) => `${c.at.toFixed(2)}+${c.dur.toFixed(2)}`).join(' '));
  const sc = score.cues.find((c) => c.kind === 'select' && c.elements);
  check('compiled score: the selection starts before the camera arrives at the keyframe', sc && sc.at < kf.tm.arrive[1] && sc.at > kf.tm.arrive[1] - 1, `select at ${sc?.at}, arrives ${kf.tm.arrive[1]}`);

  // Overlay and panel.
  await sleep(page, 600);
  const ov = await page.evaluate(() => ({ visible: window.__xrayFlythrough.pathVisible, children: window.__xray.app.renderer.scene.children.filter((c) => c.type === 'Group' && c.children.some((x) => x.type === 'Line')).length }));
  check('the camera path is drawn with the Views tab open and the section expanded', ov.visible && ov.children === 1, JSON.stringify(ov));
  await shot(page, 'flythrough-panel.png');
  await page.evaluate(() => document.querySelector('.fl-head').click());
  await sleep(page, 600);
  const closed = await page.evaluate(() => window.__xrayFlythrough.pathVisible);
  check('the path hides when the section is collapsed', closed === false);
  await page.evaluate(() => document.querySelector('.fl-head').click());
  await sleep(page, 600);

  // Reorder by button, then back.
  const order = await page.evaluate(() => {
    document.querySelectorAll('.fl-card')[0].querySelector('[data-act="right"]').click();
    const a = window.__xrayFlythrough.keyframes().map((k) => k.name);
    window.__xrayFlythrough.move(1, 0);
    return { a, b: window.__xrayFlythrough.keyframes().map((k) => k.name) };
  });
  check('reorder: the right button moves a keyframe later; move() moves it back', JSON.stringify(order.a) === JSON.stringify(['Window', 'Wide', 'Close']) && JSON.stringify(order.b) === JSON.stringify(['Wide', 'Window', 'Close']), JSON.stringify(order));
  // Edit through the panel: rename, hold, travel.
  await page.evaluate(() => document.querySelectorAll('.fl-card .fl-shot')[1].click());
  await sleep(page, 500);
  await page.locator('.fl-edit input[aria-label="Keyframe name"]').fill('The window');
  await page.locator('.fl-edit input[aria-label="Keyframe name"]').press('Enter');
  await page.locator('.fl-edit input[aria-label="Keyframe name"]').blur();
  await sleep(page, 300);
  check('editor: rename and the caption survive', await page.evaluate(() => { const k = window.__xrayFlythrough.keyframes()[1]; return k.name === 'The window' && k.caption?.title === 'The window' && k.hold === 1; }));
  await page.evaluate(() => window.__xrayFlythrough.update(1, { name: 'Window' }));

  // ---------------------------------------------------------------- playback
  await page.evaluate(() => {
    const app = window.__xray.app;
    const r = app.renderer;
    r.camera.position.set(30, 20, 30);
    r.controls.target.set(0, 0, 0);
    r.controls.update();
    app.selectIds([20]);
    const h = app.controller.settings.overrides.userHides;
    h.clear();
    h.add(5);
    app.controller.refreshOverrides();
  });
  await settle(page); // the selection flies the camera to it (fly-to): the state before play is the settled one
  const pre = await page.evaluate(() => ({ cam: window.__xrayViews.camera(), sel: window.__xray.app.selection.slice(), hides: [...window.__xray.app.controller.settings.overrides.userHides] }));
  const run = await page.evaluate(async () => {
    const f = window.__xrayFlythrough;
    const app = window.__xray.app;
    const r = app.renderer;
    const els = app.controller.model.elements;
    const log = { cams: [], sel: [], alpha0: [], alpha1: [], caption: [], overlay: [], playing: [], t: [] };
    const sleep = (ms) => new Promise((x) => setTimeout(x, ms));
    const ok = f.play();
    const t0 = performance.now();
    while (f.state().playing && performance.now() - t0 < 120000) {
      const s = f.state();
      log.t.push(s.time);
      log.cams.push(r.camera.position.toArray());
      log.sel.push([s.time, app.selection.slice()]);
      log.alpha0.push([s.time, r.state.alpha[0], r.state.flags[0]]);
      log.alpha1.push([s.time, r.state.alpha[2]]);
      log.caption.push([s.time, document.querySelector('.fl-caption') && !document.querySelector('.fl-caption').hidden ? document.querySelector('.fl-caption .fl-cap-title').textContent : '']);
      log.overlay.push(f.pathVisible);
      await sleep(60);
    }
    return { ok, log };
  });
  const L = run.log;
  check('play: starts and ends on its own', run.ok && L.t.length > 4, `${L.t.length} samples, last t ${L.t.at(-1)?.toFixed(2)}`);
  const first = L.cams[0], mid = L.cams[Math.floor(L.cams.length / 2)];
  check('play: the camera moves (starts at the first keyframe, not where it was)', dist(first, [14, 8, 16]) < 3 && dist(first, [30, 20, 30]) > 5 && dist(first, mid) > 1, `first ${first.map((x) => x.toFixed(1))}`);
  const selBefore = L.sel.filter(([t, s]) => t > 1.0 && t < 2.0 && s.includes(22)).length;
  check('play: the selection is made shortly before the camera arrives at the second keyframe (t < 2)', L.sel.some(([t, s]) => t < 2.0 && t > 1.0 && s.includes(22)), `${selBefore} samples with the selection before t = 2`);
  // Element 0 is hidden at keyframe 2 (fades out in the last 40 % of the 1st move, t 1.2 to 2) then shown again at keyframe 3.
  const mid0 = L.alpha0.filter(([t, a, fl]) => t > 1.3 && t < 1.9 && a > 0.02 && a < 0.98 && !(fl & 2));
  check('play: an element that gets hidden fades (its alpha is between 0 and 1 during the fade)', mid0.length > 0, `${mid0.length} samples, e.g. ${mid0[0]?.map((x) => +x.toFixed?.(2) ?? x)}`);
  check('play: a caption shows during the hold', L.caption.some(([t, c]) => c === 'The window'), `${L.caption.filter(([, c]) => c).length} samples`);
  check('play: the path overlay is off during playback', L.overlay.every((v) => v === false));
  await waitIdle(page);
  const post = await page.evaluate(() => {
    const app = window.__xray.app;
    return { cam: window.__xrayViews.camera(), sel: app.selection.slice(), hides: [...app.controller.settings.overrides.userHides], caption: document.querySelector('.fl-caption') ? !document.querySelector('.fl-caption').hidden : false };
  });
  check('restore after the end: camera, selection and hides as before play', dist(post.cam.position, pre.cam.position) < 1e-3 && dist(post.cam.target, pre.cam.target) < 1e-3 && JSON.stringify(post.sel) === JSON.stringify(pre.sel) && JSON.stringify(post.hides) === JSON.stringify(pre.hides) && !post.caption, `dp ${dist(post.cam.position, pre.cam.position).toExponential(1)} sel ${post.sel} hides ${post.hides}`);
  await sleep(page, 600);
  check('the path overlay is back after playback', await page.evaluate(() => window.__xrayFlythrough.pathVisible));

  // Pause, Space, Left / Right, Escape (slow moves, so the keys have time).
  await page.evaluate(() => window.__xrayFlythrough.setOptions({ segmentS: 10 }));
  await page.evaluate(() => { document.activeElement?.blur?.(); window.__xrayFlythrough.play(); });
  await page.waitForFunction(() => window.__xrayFlythrough.state().time > 0.4, null, { timeout: 60000, polling: 100 });
  await page.keyboard.press('Space');
  const paused = await page.evaluate(async () => { const f = window.__xrayFlythrough; const a = f.state().time; await new Promise((r) => setTimeout(r, 800)); return { paused: f.state().paused, a, b: f.state().time }; });
  check('Space pauses: the clock holds', paused.paused && Math.abs(paused.b - paused.a) < 1e-6, JSON.stringify(paused));
  await page.keyboard.press('Space');
  const resumed = await page.evaluate(async () => { const f = window.__xrayFlythrough; const a = f.state().time; await new Promise((r) => setTimeout(r, 1500)); return { paused: f.state().paused, a, b: f.state().time }; });
  check('Space resumes', !resumed.paused && resumed.b > resumed.a, JSON.stringify(resumed));
  await page.keyboard.press('ArrowRight');
  await sleep(page, 400);
  const afterRight = await page.evaluate(() => ({ t: window.__xrayFlythrough.state().time, kf: window.__xrayFlythrough.state().keyframe, tm: window.__xrayFlythrough.timing() }));
  check('Right goes to the next keyframe', Math.abs(afterRight.t - afterRight.tm.arrive[afterRight.kf]) < 0.9 && afterRight.kf >= 1, JSON.stringify({ t: afterRight.t, kf: afterRight.kf }));
  await page.keyboard.press('ArrowLeft');
  await sleep(page, 400);
  const afterLeft = await page.evaluate(() => window.__xrayFlythrough.state());
  check('Left goes back a keyframe', afterLeft.keyframe < afterRight.kf || afterLeft.time < afterRight.t, JSON.stringify({ kf: afterLeft.keyframe, t: afterLeft.time }));
  await shot(page, 'flythrough-play.png');
  await page.keyboard.press('Escape');
  await sleep(page, 400);
  const esc = await page.evaluate(() => ({ playing: window.__xrayFlythrough.state().playing, cam: window.__xrayViews.camera(), sel: window.__xray.app.selection.slice() }));
  check('Escape stops and restores the view', !esc.playing && dist(esc.cam.position, pre.cam.position) < 1e-3 && JSON.stringify(esc.sel) === JSON.stringify(pre.sel), `d ${dist(esc.cam.position, pre.cam.position).toExponential(1)}`);

  // A press on the canvas stops playback and leaves the camera.
  await sleep(page, 600);
  await page.evaluate(() => window.__xrayFlythrough.play());
  await page.waitForFunction(() => window.__xrayFlythrough.state().time > 1.0, null, { timeout: 60000, polling: 100 });
  await page.mouse.move(800, 400);
  await page.mouse.down();
  await page.mouse.up();
  await sleep(page, 400);
  const drag = await page.evaluate(() => ({ playing: window.__xrayFlythrough.state().playing, cam: window.__xrayViews.camera() }));
  check('a press on the canvas stops playback and the camera stays there', !drag.playing && dist(drag.cam.position, pre.cam.position) > 0.5, `d ${dist(drag.cam.position, pre.cam.position).toFixed(1)}`);
  // Restore the starting state for what follows.
  await page.evaluate((p) => {
    const app = window.__xray.app;
    app.renderer.camera.position.set(...p.cam.position);
    app.renderer.controls.target.set(...p.cam.target);
    app.renderer.controls.update();
  }, pre);

  // ---------------------------------------------------------------- the player takes any score
  const sp = await page.evaluate(async () => {
    const mod = await import('/src/anim/score.ts');
    const p = mod.getScorePlayer();
    const app = window.__xray.app;
    const sleep = (ms) => new Promise((x) => setTimeout(x, ms));
    const presets = window.__xrayPresets.list();
    const presetId = presets.find((x) => x.id !== window.__xrayPresets.active())?.id;
    const alphaMax0 = app.settings.sightlines.alphaMax;
    const score = {
      schema: 'xray-score/1',
      duration: 4,
      cues: [
        { kind: 'param', at: 0, dur: 2, path: 'sightlines.alphaMax', to: 0.2, ease: 'linear' },
        { kind: 'param', at: 0, dur: 2, path: 'display.inFront', to: false },
        { kind: 'camera', at: 0, dur: 2, to: { frame: { query: 'ifcClass = "IfcWindow"' } }, ease: 'inOut' },
        { kind: 'select', at: 1, dur: 0, elements: { query: 'ifcClass = "IfcWindow"' } },
        { kind: 'visibility', at: 2, dur: 0, isolate: { query: 'ifcClass = "IfcWindow"' } },
        { kind: 'caption', at: 0.5, dur: 3, title: 'Score', text: 'Every cue kind' },
        { kind: 'preset', at: 3, dur: 0, id: presetId },
        { kind: 'label', at: 0, dur: 1, elements: { all: true }, fields: ['name'] },
        { kind: 'unknown-kind', at: 0, dur: 1 },
      ],
    };
    const before = { cam: window.__xrayViews.camera(), alphaMax: alphaMax0, inFront: app.display.inFront, hides: app.controller.settings.overrides.userHides.size, sel: app.selection.length };
    const ended = [];
    const ok = p.play(score, { onEnd: () => ended.push(true) });
    const samples = [];
    const t0 = performance.now();
    while (p.playing && performance.now() - t0 < 120000) {
      samples.push({ t: p.time, a: app.settings.sightlines.alphaMax, f: app.display.inFront, sel: app.selection.length, hides: app.controller.settings.overrides.userHides.size, cap: !!document.querySelector('.fl-caption') && !document.querySelector('.fl-caption').hidden, active: window.__xrayPresets.active() });
      await sleep(80);
    }
    const after = { cam: window.__xrayViews.camera(), alphaMax: app.settings.sightlines.alphaMax, inFront: app.display.inFront, hides: app.controller.settings.overrides.userHides.size, sel: app.selection.length };
    return { ok, ended, samples, before, after, presetId };
  });
  const S = sp.samples;
  // Frames are slow here (software rendering) and a tick moves the clock by at most 250 ms: look at what the samples show, not at exact times.
  const blend = S.filter((s) => s.t > 0.1 && s.t < 1.9 && s.a < sp.before.alphaMax - 0.01 && s.a > 0.2 + 0.01);
  check('score: a number param blends (alphaMax between its start and 0.2 during the cue), a boolean switches at the end', blend.length > 0 && S.filter((s) => s.t < 1.9).every((s) => s.f === sp.before.inFront), `${blend.length} samples in between, from ${sp.before.alphaMax}; e.g. ${blend[0]?.a?.toFixed(2)}`);
  check('score: select by query, isolate by query, caption, preset', S.some((s) => s.sel > 0) && S.some((s) => s.hides > 40) && S.some((s) => s.cap) && S.some((s) => s.active === sp.presetId), `sel ${Math.max(...S.map((s) => s.sel))} hides ${Math.max(...S.map((s) => s.hides))} preset ${sp.presetId} active ${[...new Set(S.map((s) => s.active))]}`);
  check('score: unknown and phase 2 cue kinds are skipped, onEnd runs, everything is restored', sp.ok && sp.ended.length === 1 && Math.abs(sp.after.alphaMax - sp.before.alphaMax) < 1e-9 && sp.after.inFront === sp.before.inFront && sp.after.hides === sp.before.hides && sp.after.sel === sp.before.sel && dist(sp.after.cam.position, sp.before.cam.position) < 1e-3, JSON.stringify({ before: sp.before.alphaMax, after: sp.after.alphaMax }));

  // ---------------------------------------------------------------- selection sets, cinematic proxies, recording
  const sets = await page.evaluate(() => {
    const f = window.__xrayFlythrough;
    const n = f.buildFromSets();
    const keys = window.__cinematic.keys;
    return { n, names: keys.map((k) => k.name), sel: keys.map((k) => k.selection.length) };
  });
  check('build from selection sets: one keyframe per set, framed on the set (kept feature)', sets.n >= 2 && sets.names.length === sets.n && sets.sel.every((x) => x > 0), JSON.stringify(sets));
  const views = await page.evaluate(() => {
    const v = window.__xrayViews;
    v.save('Va');
    v.save('Vb');
    return { n: window.__xrayFlythrough.buildFromViews(), names: window.__xrayFlythrough.keyframes().map((k) => k.name) };
  });
  check('build from saved views: one keyframe per saved view', views.n === 2 && views.names.join() === 'Va,Vb', JSON.stringify(views));
  const rec = await page.evaluate(async () => {
    const cin = window.__cinematic;
    window.__xrayFlythrough.setOptions({ timing: 'seconds', segmentS: 1 });
    const supported = typeof MediaRecorder !== 'undefined' && 'captureStream' in HTMLCanvasElement.prototype;
    cin.lastRecording = null;
    const started = cin.record();
    for (let i = 0; i < 400 && !cin.lastRecording; i++) await new Promise((r) => setTimeout(r, 100));
    const r = cin.lastRecording;
    return { supported, started, bytes: r ? r.bytes : null, mime: r ? r.mime : null };
  });
  if (rec.supported) check('record: webm on the new player', rec.started && rec.bytes > 1000, JSON.stringify(rec));
  else console.log('INFO record: MediaRecorder is not available in this browser', JSON.stringify(rec));
  await sleep(page, 500);
  const spill = await page.evaluate(() => ({ stored: Object.keys(localStorage).filter((k) => k.startsWith('xray.flythroughs.')), text: Object.entries(localStorage).filter(([k]) => !k.startsWith('xray.flythroughs.')).map(([, v]) => v).join(' ') }));
  check('captions stay in the fly-through store (none in other storage)', spill.stored.length === 1 && !spill.text.includes('Selected, with two elements hidden'));
  const params = await page.evaluate(() => JSON.stringify(window.__xrayParams.collect()));
  check('captions and fly-throughs are not in the params', !params.includes('Selected, with two') && !params.includes('Smoke'));
  await ctx.close();

  // ---------------------------------------------------------------- phone
  {
    const { ctx: pc, page: pp } = await openPage(browser, { label: 'phone', viewport: { width: 390, height: 844 }, ctx: { hasTouch: true, isMobile: true } });
    await pp.evaluate(() => {
      for (const k of Object.keys(localStorage)) if (k.startsWith('xray.flythrough') || k.startsWith('xray.views.')) localStorage.removeItem(k);
      localStorage.setItem('xray.sidebar', JSON.stringify({ collapsed: false, tab: 'views' }));
    });
    await pp.reload();
    await ready(pp);
    await pp.waitForFunction('!!window.__xrayFlythrough', null, { timeout: 60000 });
    await pp.evaluate(() => { const f = window.__xrayFlythrough; f.create('Phone'); for (let i = 0; i < 6; i++) { window.__xray.app.renderer.camera.position.x += 2; window.__xray.app.renderer.controls.update(); f.add({ name: `Stop ${i + 1}` }); } });
    await sleep(pp, 800);
    const lay = await pp.evaluate(() => {
      const cards = document.querySelector('.fl-cards');
      const rows = new Set([...document.querySelectorAll('.fl-card')].map((c) => Math.round(c.getBoundingClientRect().top)));
      return { scroll: cards ? cards.scrollWidth : -1, client: cards ? cards.clientWidth : -1, rows: rows.size, pageScroll: document.documentElement.scrollWidth, inner: window.innerWidth };
    });
    check('phone: the cards wrap onto several rows, no horizontal scroll', lay.rows >= 2 && lay.scroll <= lay.client + 1 && lay.pageScroll <= lay.inner + 1, JSON.stringify(lay));
    await pp.evaluate(() => document.querySelector('.fl').scrollIntoView());
    await shot(pp, 'flythrough-phone.png');
    await pc.close();
  }
}

let failed = false;
try {
  await waitForServer();
  const browser = await chromium.launch();
  await main(browser);
  await browser.close();
} catch (e) {
  failed = true;
  console.error(e);
} finally {
  if (vite) vite.kill();
}
check('no console errors', errors.length === 0, errors.slice(0, 5).join(' || '));
const bad = checks.filter((c) => !c.ok);
console.log(`\n${checks.length - bad.length}/${checks.length} checks passed`);
process.exit(failed || bad.length ? 1 : 0);
