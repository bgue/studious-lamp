// Headless smoke test for 4D playback (docs-features/4d-playback.md) on fzk-haus: the demo plan of the loaded model plays in a score
// with schedule4d + explode + focus + sectionBox + tint + collapse cues:
//   - visibility counts at several plan times match the plan's own state counts (hidden = future, active = tinted = glowing), and fall
//     monotonically; tints are in the renderer colours of the active elements; the explode lifts the top storey and the collapse
//     returns it; the section box is on while its cue runs; the focus follows the active elements; the HUD draws the schedule date,
//     the S-curve and the legend (the overlay canvas has pixels where they sit);
//   - at the end everything is restored (hides, colours, alpha, glow, selection, explode offsets, section box) and the camera is
//     where it was; a seek gives the picture of a plan time; the cost of the state update;
//   - a frame by frame video export of a 2 s schedule clip (640x360, 24 fps): the schedule renders in it (first and last frame
//     differ a lot), the HUD date panel is in it (pixels differ with the HUD switch) and the viewer is restored.
// The software renderer is slow, so every wait is on the player's clock (window.__xrayFlythrough.state().time), never on wall time.
// Usage: SMOKE_PORT=5860 XRAY_VITE_CACHE_DIR=/tmp/xray-4d-cache node bench/smoke-4d-play.mjs        (SMOKE_REUSE=1 uses a server already on that port)
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const port = Number(process.env.SMOKE_PORT ?? 5860);
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
  // The decode check imports the muxer library by file URL next to the copy the app loaded: its own warning, not an app problem.
  page.on('console', (m) => { if (m.type() === 'error' && !/Mediabunny was loaded twice/.test(m.text())) errors.push(`${label}: ${m.text()}`); });
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



const sleep = (page, ms) => page.waitForTimeout(ms);

async function openPage(browser, label) {
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 720 } });
  const page = await ctx.newPage();
  watch(page, label);
  await page.goto(`${base}/?model=${process.env.SMOKE_MODEL ?? 'fzk-haus'}`);
  await ready(page);
  await page.waitForFunction('!!window.__xrayFlythrough && !!window.__xray4d && !!window.__xrayRecord', null, { timeout: 60000, polling: 300 });
  return { ctx, page };
}

/** Wait until the player clock reaches `t` (or the play ended). */
const waitClock = (page, t, maxMs = 600000) => page.waitForFunction((tt) => { const s = window.__xrayFlythrough.state(); return !s.playing || s.time >= tt; }, t, { timeout: maxMs, polling: 150 });

/** What the viewer looks like now, read in one synchronous evaluate (no frame runs in between). */
const page_snapshot = () => {
  const app = window.__xray.app;
  const r = app.renderer;
  const m = app.controller.model;
  const live = window.__xray4d.live();
  const st = live.planMs === null ? null : window.__xray4d.state(live.planMs);
  const base = (i) => m.elements[i].color;
  let colourDiff = 0;
  const col = r.state.color;
  for (let i = 0; i < m.elements.length; i++) {
    const b = base(i);
    if (Math.abs(col[i * 3] - b[0]) + Math.abs(col[i * 3 + 1] - b[1]) + Math.abs(col[i * 3 + 2] - b[2]) > 1e-3) colourDiff++;
  }
  let lowAlpha = 0;
  for (let i = 0; i < r.state.alpha.length; i++) if (r.state.alpha[i] < 0.99) lowAlpha++;
  let maxLift = 0;
  for (let i = 0; i < m.elements.length; i++) maxLift = Math.max(maxLift, r.elementOffset(i)[1]);
  const hs = window.__xrayFlythrough.hudState();
  return {
    time: window.__xrayFlythrough.state().time,
    live, counts: st?.counts ?? null,
    userHides: app.controller.settings.overrides.userHides.size,
    colourDiff, lowAlpha, maxLift,
    selection: app.controller.selection.size,
    focus: app.controller.classification.focus.size,
    sectionOn: !!window.__xraySection?.config.box.enabled,
    glowMask: r.glowMask ? Array.from(r.glowMask).filter((v) => v > 0).length : 0,
    glowRed: r.glowMask ? Array.from(r.glowMask).filter((v) => v === 2).length : 0,
    hud: hs.last?.fourd ? { date: hs.last.fourd.date, week: hs.last.fourd.week, planned: hs.last.fourd.plannedPct, curve: !!hs.last.fourd.curve, legend: hs.last.fourd.legend?.entries ?? null, activities: hs.last.fourd.activities?.rows.length ?? 0, milestone: hs.last.fourd.milestone?.name ?? null, panel: hs.last.fourd.panel, clock: hs.last.fourd.clockText } : null,
    hudDrawn: hs.drawn,
    camera: r.camera.position.toArray(),
  };
};

async function main(browser) {
  const { ctx, page } = await openPage(browser, 'main');
  await page.evaluate(() => { window.__xraySection?.clear?.(); window.__xray.app.clearSelection(); });
  await sleep(page, 1500);
  const info = await page.evaluate(() => {
    const m = window.__xray.app.controller.model;
    const plan = window.__xray4d.demoPlan();
    return { n: m.elements.length, storeys: m.storeys.map((s) => s.name), planned: plan.elements.length, tasks: plan.tasks.length, milestones: plan.milestones.length, critical: plan.tasks.filter((t) => t.critical).length, window: plan.window, trades: [...new Set(plan.tasks.map((t) => t.trade))] };
  });
  console.log('INFO model', JSON.stringify(info));
  check('the demo plan covers every element with tasks, milestones and a critical chain', info.planned === info.n && info.tasks >= 4 && info.milestones >= 2 && info.critical >= 1 && info.trades.length >= 2, JSON.stringify(info));

  const before = await page.evaluate(page_snapshot);
  const storeyName = info.storeys.length > 1 ? info.storeys[Math.min(1, info.storeys.length - 1)] : info.storeys[0];
  const DUR = 30;
  const extra = [
    { at: 4, dur: 3, kind: 'explode', mode: 'storeys', factor: 1, ease: 'inOut' },
    { at: 9, dur: 0, kind: 'focus', elements: { schedule: 'active' } },
    { at: 11, dur: 2, kind: 'sectionBox', around: storeyName ? { storey: storeyName } : { schedule: 'active' }, margin: 0.5, ease: 'inOut' },
    { at: 16, dur: 2, kind: 'sectionBox', around: null, ease: 'inOut' },
    { at: 19, dur: 2, kind: 'collapse', ease: 'inOut' },
    { at: 22, dur: 2, kind: 'tint', elements: { query: 'class = IfcWindow' }, colour: '#00aaff' },
    { at: 26, dur: 1, kind: 'tint', elements: { query: 'class = IfcWindow' }, colour: null },
    { at: 3, dur: 3, kind: 'caption', title: 'Schedule', text: 'A caption beside the schedule HUD' },
  ];
  const t0 = Date.now();
  const ok = await page.evaluate(([d, e]) => { const plan = window.__xray4d.demoPlan(); return window.__xray4d.play(plan, d, e); }, [DUR, extra]);
  check('the score with schedule4d, explode, focus, sectionBox, tint and collapse cues starts', ok === true);

  // ---- checkpoints on the player clock
  const shots = [];
  for (const t of [0.5, 3, 7, 10, 12, 14, 17.5, 20, 23, 25, 28]) {
    await waitClock(page, t);
    const s = await page.evaluate(page_snapshot);
    shots.push({ t, s });
    console.log(`INFO t=${s.time.toFixed(2)}s plan=${s.live.planMs === null ? '-' : new Date(s.live.planMs).toISOString().slice(0, 10)} hidden=${s.live.hidden} tinted=${s.live.tinted} glow=${s.live.glow} active=${s.live.active} completed=${s.live.completed} hides=${s.userHides} lift=${s.maxLift.toFixed(2)} section=${s.sectionOn} sel=${s.selection} focus=${s.focus} hud=${s.hud?.date ?? '-'}`);
  }
  for (const { t, s } of shots) {
    check(`t=${t}: hidden elements = the plan's future elements at that plan time (${s.counts?.future})`, s.counts && s.live.hidden === s.counts.future && s.userHides === s.live.hidden, `live ${s.live.hidden}, plan ${s.counts?.future}, hides ${s.userHides}`);
    check(`t=${t}: active = tinted = glowing elements (${s.counts?.active}), tints are in the renderer colours`, s.counts && s.live.active === s.counts.active && s.live.glow === s.counts.active && s.live.tinted >= s.counts.active && (s.counts.active === 0 || s.colourDiff >= s.counts.active), `active ${s.live.active}, glow ${s.live.glow}, tinted ${s.live.tinted}, colours changed ${s.colourDiff}, mask ${s.glowMask}`);
  }
  const hiddenSeries = shots.map((x) => x.s.live.hidden);
  check('hidden elements only fall as the schedule plays (the building goes up)', hiddenSeries.every((h, i) => i === 0 || h <= hiddenSeries[i - 1]) && hiddenSeries[0] > hiddenSeries[hiddenSeries.length - 1], hiddenSeries.join(' > '));
  check('some plan time passes: the plan date is later at each checkpoint', shots.every((x, i) => i === 0 || x.s.live.planMs >= shots[i - 1].s.live.planMs), '');
  const at = (t) => shots.find((x) => x.t === t).s;
  check('the first frames hide most of the building, the late ones show it all or almost', at(0.5).live.hidden > info.n * 0.6 && at(28).live.hidden <= info.n * 0.05, `${at(0.5).live.hidden} -> ${at(28).live.hidden} of ${info.n}`);
  check('explode (storeys): the top storey is lifted while exploded and has come back after the collapse cue', at(10).maxLift > 0.5 && at(23).maxLift < 1e-6, `lift ${at(10).maxLift.toFixed(2)} m, after ${at(23).maxLift.toExponential(1)}`);
  check('sectionBox: on while its cue runs and held after it', at(12).sectionOn && at(14).sectionOn, `12:${at(12).sectionOn} 14:${at(14).sectionOn}`);
  check('section box is off again after the off cue', !at(20).sectionOn && !at(23).sectionOn, `20:${at(20).sectionOn} 23:${at(23).sectionOn}`);
  check('focus: the active elements are the x-ray focus (a selection of them and a focus set in the classification)', at(10).selection > 0 && at(10).focus > 0, `selection ${at(10).selection}, focus ${at(10).focus}`);
  check('critical work has a red edge glow while it is active', shots.some((x) => x.s.glowRed > 0), shots.map((x) => x.s.glowRed).join(','));
  check('the HUD shows the schedule date and ISO week, % complete, the S-curve, the activities and the legend', shots.every((x) => x.s.hud && /^\d{4}-\d{2}-\d{2}$/.test(x.s.hud.date) && x.s.hud.week > 0 && x.s.hud.curve && x.s.hud.legend && x.s.hud.legend.length >= 2) && shots.some((x) => x.s.hud.activities > 0), JSON.stringify(at(10).hud));
  check('the HUD date replaces the m:ss clock on the progress bar', /^\d{4}-\d{2}-\d{2} {2}W\d{2}$/.test(at(10).hud.clock) && at(10).hudDrawn === true, at(10).hud.clock);
  check('a milestone caption is held in some frame', shots.some((x) => x.s.hud?.milestone), shots.map((x) => x.s.hud?.milestone).filter(Boolean).join(' | ') || 'none seen at the checkpoints (held for 1 s of video)');
  const px = await page.evaluate(() => {
    const hs = window.__xrayFlythrough.hudState();
    const o = document.querySelector('canvas.xray-hud');
    if (!o || !hs.last?.fourd?.panel) return null;
    const r = hs.last.fourd.panel;
    const d = o.getContext('2d').getImageData(Math.floor(r.x * hs.pixelRatio), Math.floor(r.y * hs.pixelRatio), Math.ceil(r.w * hs.pixelRatio), Math.ceil(r.h * hs.pixelRatio)).data;
    let n = 0;
    for (let i = 3; i < d.length; i += 4) if (d[i] > 0) n++;
    return { n, total: d.length / 4 };
  });
  check('the date panel is drawn on the HUD canvas', px && px.n > px.total * 0.5, JSON.stringify(px));

  // ---- the end: everything restored
  await page.waitForFunction(() => !window.__xrayFlythrough.state().playing, null, { timeout: 600000, polling: 250 });
  console.log(`INFO played ${DUR} s of score in ${((Date.now() - t0) / 1000).toFixed(0)} s wall`);
  // the x-ray ghosts of the occluders ease back over a few frames (slow here): wait until the count of translucent elements settles
  let after = await page.evaluate(page_snapshot);
  for (let i = 0; i < 60 && after.lowAlpha !== before.lowAlpha; i++) { await sleep(page, 1000); after = await page.evaluate(page_snapshot); }
  check('at the end: nothing hidden by the schedule is left (the hides are as before)', after.userHides === before.userHides && after.live.hidden === 0, `hides ${after.userHides} (before ${before.userHides}), live ${after.live.hidden}`);
  check('at the end: colours and alpha are back, no tint left', after.colourDiff === before.colourDiff && after.lowAlpha === before.lowAlpha && after.live.tinted === 0, `colours ${after.colourDiff}/${before.colourDiff}, alpha<1 ${after.lowAlpha}/${before.lowAlpha}`);
  check('at the end: the edge glow of the schedule is off', after.glowMask === before.glowMask, `${after.glowMask} (before ${before.glowMask})`);
  check('at the end: the selection, the explode offsets and the section box are back', after.selection === before.selection && after.maxLift < 1e-6 && after.sectionOn === before.sectionOn, JSON.stringify({ sel: after.selection, lift: after.maxLift, sec: after.sectionOn }));
  check('at the end: the camera is where it was and the HUD is clear', Math.hypot(...after.camera.map((v, i) => v - before.camera[i])) < 1e-3 && after.hudDrawn === false, JSON.stringify({ cam: after.camera, drawn: after.hudDrawn }));

  // ---- seek: the picture of a plan time
  await page.evaluate(() => { const plan = window.__xray4d.demoPlan(); window.__xray4d.play(plan, 20, []); });
  await waitClock(page, 12);
  await page.evaluate(() => window.__xrayFlythrough.pause());
  const fwd = await page.evaluate(page_snapshot);
  await page.evaluate(() => window.__xrayFlythrough.seek(5));
  await sleep(page, 300);
  const back = await page.evaluate(page_snapshot);
  await page.evaluate(() => window.__xrayFlythrough.seek(12));
  await sleep(page, 300);
  const again = await page.evaluate(page_snapshot);
  check('seek back shows an earlier picture (more hidden), seek forward again the same as playing there', back.live.hidden > fwd.live.hidden && back.counts && back.live.hidden === back.counts.future && Math.abs(again.live.hidden - fwd.live.hidden) <= Math.max(2, info.n * 0.02), `12 s: ${fwd.live.hidden}, seek 5 s: ${back.live.hidden}, seek 12 s: ${again.live.hidden}`);
  await page.evaluate(() => window.__xrayFlythrough.stop());
  await sleep(page, 500);

  // ---- cost of the state update
  const bench = await page.evaluate(() => window.__xray4d.bench(window.__xray4d.demoPlan(), 240));
  console.log('INFO state update', JSON.stringify(bench));
  check('the state update costs well under a frame (ms per frame)', bench.msPerFrame < 8, JSON.stringify(bench));

  // ---- video export
  const cam0 = await page.evaluate(() => window.__xray.app.renderer.camera.position.toArray());
  const exportOnce = (hud) => page.evaluate(async (h) => {
    const plan = window.__xray4d.demoPlan();
    const score = window.__xray4d.score(plan, 2, []);
    const frames = [];
    const app = window.__xray.app;
    const orig = app.stepFrame.bind(app);
    app.stepFrame = (now) => { orig(now); frames.push({ hidden: window.__xray4d.live().hidden, date: window.__xrayFlythrough.hudState().last?.fourd?.date ?? null }); };
    let res;
    try { res = await window.__xrayRecord.run(score, { size: '640x360', fps: 24, format: 'auto', hud: h }, { download: false }); } finally { app.stepFrame = orig; }
    return { res, frames };
  }, hud);
  const frameAt = (sec) => page.evaluate(async (s) => {
    const mb = await import('/node_modules/mediabunny/dist/bundles/mediabunny.mjs');
    const input = new mb.Input({ source: new mb.BlobSource(window.__xrayRecord.lastBlob()), formats: mb.ALL_FORMATS });
    const track = await input.getPrimaryVideoTrack();
    const w = await new mb.CanvasSink(track, {}).getCanvas(s);
    const c = w.canvas;
    return { w: c.width, h: c.height, data: Array.from(c.getContext('2d').getImageData(0, 0, c.width, c.height).data) };
  }, sec);
  const withHud = await exportOnce(true);
  console.log('INFO export', JSON.stringify(withHud.res));
  check('video export of the schedule clip succeeds with duration x fps frames (2 s at 24 fps = 48)', withHud.res.ok && withHud.res.file?.frames === 48, JSON.stringify(withHud.res.file ?? withHud.res.message));
  const hid = withHud.frames.map((f) => f.hidden);
  check('video export: the schedule is evaluated frame by frame (hidden elements fall from most to few)', withHud.frames.length === 48 && hid[0] > info.n * 0.6 && hid[hid.length - 1] <= info.n * 0.05 && hid.every((h, i) => i === 0 || h <= hid[i - 1]), hid.join(','));
  const first = await frameAt(0.0);
  const last = await frameAt(1.9);
  let diff = 0;
  for (let i = 0; i < first.data.length; i += 4) if (Math.abs(first.data[i] - last.data[i]) + Math.abs(first.data[i + 1] - last.data[i + 1]) + Math.abs(first.data[i + 2] - last.data[i + 2]) > 60) diff++;
  check('video export: the first and the last frame differ (the building goes up in the video)', diff > first.w * first.h * 0.01, `${diff} of ${first.w * first.h} pixels`);
  const withData = await frameAt(1.0);
  const noHud = await exportOnce(false);
  const clean = await frameAt(1.0);
  let hudPx = 0;
  for (let y = 0; y < Math.floor(withData.h * 0.4); y++) for (let x = 0; x < Math.floor(withData.w * 0.3); x++) {
    const i = (y * withData.w + x) * 4;
    if (Math.abs(withData.data[i] - clean.data[i]) + Math.abs(withData.data[i + 1] - clean.data[i + 1]) + Math.abs(withData.data[i + 2] - clean.data[i + 2]) > 60) hudPx++;
  }
  check('video export: the date panel and activities are in the video frame (top left pixels differ with the HUD switch)', noHud.res.ok && hudPx > 200, `${hudPx} differing pixels in the top-left`);
  check('video export: the HUD layer drew the schedule date on the frames', withHud.frames.filter((f) => f.date).length >= 40, withHud.frames.slice(0, 3).map((f) => f.date).join(','));
  const post = await page.evaluate(page_snapshot);
  check('video export: the viewer is restored (hides, colours, camera, nothing playing)', post.userHides === before.userHides && post.colourDiff === before.colourDiff && post.live.tinted === 0 && Math.hypot(...post.camera.map((v, i) => v - cam0[i])) < 1e-3, JSON.stringify({ hides: post.userHides, colours: post.colourDiff, tinted: post.live.tinted }));
  await ctx.close();
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
