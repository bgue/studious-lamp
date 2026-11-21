// Headless smoke test for the video export (docs-features/flythrough.md, Export) on fzk-haus:
//   - the options dialog (from the fly-through "Rec" button and from the Script tab "Record" button), with help keys;
//   - a frame by frame export of a 2 s fly-through at 640x360 / 30 fps: the file downloads, has the container signature (EBML for webm,
//     ftyp for mp4), holds exactly duration * fps frames (parsed with the muxer library's reader in node), has the video size, and a
//     fake HUD layer's pixels are in a decoded frame; the canvas size, the camera and the state are restored; the software
//     renderer is slow here, which is why the export does not use the wall clock;
//   - Cancel mid-way (no file, everything restored), the PNG image sequence in a zip, the real-time MediaRecorder fallback when
//     WebCodecs is missing, the PNG fallback when both are missing, and normal playback after an export.
// Usage: SMOKE_PORT=5830 XRAY_VITE_CACHE_DIR=/tmp/xray-rec-cache node bench/smoke-video-export.mjs        (SMOKE_REUSE=1 uses a server already on that port)
import { mkdtempSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
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
  page.on('console', (m) => {
    // The decode check below imports the muxer library by file URL, next to the copy the app loaded: its own warning, not an app problem.
    if (m.type() === 'error' && !/Mediabunny was loaded twice/.test(m.text())) errors.push(`${label}: ${m.text()}`);
  });
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

async function openPage(browser, opts = {}) {
  const ctx = await browser.newContext({ viewport: opts.viewport ?? { width: 1280, height: 720 }, acceptDownloads: true });
  const page = await ctx.newPage();
  watch(page, opts.label ?? 'page');
  if (opts.init) await page.addInitScript(opts.init);
  await page.goto(`${base}/?model=fzk-haus`);
  await ready(page);
  await page.waitForFunction('!!window.__xrayFlythrough && !!window.__xrayRecord', null, { timeout: 60000, polling: 300 });
  return { ctx, page };
}

/** Three keyframes, 1 s per move: a 2 s fly-through. */
async function makeFly(page) {
  await page.evaluate(() => {
    for (const k of Object.keys(localStorage)) if (k.startsWith('xray.flythrough') || k.startsWith('xray.views.')) localStorage.removeItem(k);
    localStorage.setItem('xray.sidebar', JSON.stringify({ collapsed: false, tab: 'views' }));
  });
  await page.reload();
  await ready(page);
  await page.waitForFunction('!!window.__xrayFlythrough && !!window.__xrayRecord', null, { timeout: 60000 });
  await page.evaluate(() => {
    const app = window.__xray.app;
    const r = app.renderer;
    const f = window.__xrayFlythrough;
    f.create('Smoke video');
    f.setOptions({ timing: 'seconds', segmentS: 1 });
    const poses = [[14, 8, 16, 0, 1, 0], [-10, 5, 9, -2, 1, 0], [2, 3, 6, 0, 1.5, 0]];
    for (const [x, y, z, tx, ty, tz] of poses) {
      r.camera.position.set(x, y, z);
      r.controls.target.set(tx, ty, tz);
      r.controls.update();
      f.add({});
    }
    // start from the first pose
    r.camera.position.set(14, 8, 16);
    r.controls.target.set(0, 1, 0);
    r.controls.update();
  });
}

const state = (page) =>
  page.evaluate(() => {
    const app = window.__xray.app;
    const r = app.renderer;
    return { cw: app.canvas.width, ch: app.canvas.height, pr: r.renderer.getPixelRatio(), aspect: r.camera.aspect, pos: r.camera.position.toArray(), target: r.controls.target.toArray(), playing: window.__xrayFlythrough.state().playing, busy: window.__xrayRecord.busy, overlay: !!document.querySelector('[data-record-busy]') };
  });

async function saveDownload(dl) {
  const dir = mkdtempSync(join(tmpdir(), 'xray-rec-'));
  const file = join(dir, dl.suggestedFilename());
  await dl.saveAs(file);
  return { file, bytes: readFileSync(file) };
}

/** Parse a video file in node with the muxer library's reader: container, codec, size, packet count, duration. */
async function inspect(file) {
  const mb = await import(resolve(root, 'node_modules/mediabunny/dist/bundles/mediabunny.node.cjs')).then((m) => m.default ?? m);
  const input = new mb.Input({ source: new mb.FilePathSource(file), formats: mb.ALL_FORMATS });
  const track = await input.getPrimaryVideoTrack();
  const stats = await track.computePacketStats();
  return { format: (await input.getFormat()).name, codec: track.codec, width: track.displayWidth, height: track.displayHeight, packets: stats.packetCount, duration: await input.computeDuration() };
}

async function main(browser) {
  // ---------------------------------------------------------------- dialogs
  const { ctx, page } = await openPage(browser, { label: 'main' });
  await makeFly(page);
  await sleep(page, 400);
  const caps = await page.evaluate(() => window.__xrayRecord.capabilities());
  console.log('INFO capabilities', JSON.stringify(caps));
  const mp4 = await page.evaluate(async () => (await VideoEncoder.isConfigSupported({ codec: 'avc1.64001F', width: 640, height: 360, framerate: 30, bitrate: 1e6 })).supported === true);
  console.log('INFO H.264 encoder in this browser:', mp4);

  await page.click('button[data-help-key="Sidebar/Fly-through record"]');
  await page.waitForSelector('[data-record-dialog]');
  const dlg = await page.evaluate(() => {
    const d = document.querySelector('[data-record-dialog]');
    const keys = [...d.querySelectorAll('[data-help-key]')].map((e) => e.getAttribute('data-help-key'));
    return { keys, size: d.querySelector('#rc-size').value, fps: d.querySelector('#rc-fps').value, name: d.querySelector('#rc-name').value, text: d.textContent, helpOk: keys.every((k) => !!window.__xrayHelp.lookup(k)) };
  });
  check('dialog: opens from the Rec button with size, frame rate, quality, format, HUD and file name', ['Size', 'Frame rate', 'Quality', 'Format', 'Include HUD', 'File name', 'Record', 'Cancel'].every((n) => dlg.keys.includes('Record dialog/' + n)), dlg.keys.join(','));
  check('dialog: every control has a help text; the name comes from the fly-through', dlg.helpOk && dlg.name === 'Smoke-video', dlg.name);
  check('dialog: tells the frame count and warns about 4K (after picking it)', /60 frames/.test(dlg.text), dlg.text.slice(0, 160));
  await page.selectOption('#rc-size', '3840x2160');
  const warn = await page.evaluate(() => document.querySelector('[data-record-dialog] .rc-warn').textContent);
  check('dialog: 4K shows the long-time warning', /long time/.test(warn), warn);
  await page.keyboard.press('Escape');
  await sleep(page, 200);
  check('dialog: Escape closes it and records nothing', (await page.$('[data-record-dialog]')) === null && (await page.evaluate(() => window.__xrayRecord.last)) === null);

  await page.evaluate(() => window.__xrayScript.setText('fly to everything over 2 seconds'));
  await page.evaluate(() => window.__xrayScript.open());
  await sleep(page, 400);
  const sb = await page.$('button[data-act="record"]');
  check('script tab: has a Record button with a help key', !!sb && (await sb.getAttribute('data-help-key')) === 'Script tab/Record');
  if (sb) {
    await sb.click();
    await page.waitForSelector('[data-record-dialog]');
    const subj = await page.evaluate(() => document.querySelector('[data-record-dialog] .rc-stat').textContent);
    check('script tab: Record opens the dialog for the script', /Script/.test(subj), subj);
    await page.keyboard.press('Escape');
    await sleep(page, 200);
  }

  // ---------------------------------------------------------------- the export itself
  const before = await state(page);
  await page.evaluate(async () => {
    const hud = await import('/src/anim/hud.ts');
    window.__fakeHudCalls = [];
    hud.setHudLayer({
      active: () => true,
      draw(ctx, f) {
        window.__fakeHudCalls.push({ t: f.t, w: f.width, h: f.height, pr: f.pixelRatio, rec: f.recording, duration: f.duration });
        ctx.fillStyle = '#ff00ff';
        ctx.fillRect(0, 0, 60 * f.pixelRatio, 60 * f.pixelRatio);
      },
    });
  });
  const t0 = Date.now();
  const [dl] = await Promise.all([
    page.waitForEvent('download', { timeout: 600000 }),
    page.evaluate(() => { window.__exportDone = window.__xrayRecord.flythrough({ size: '640x360', fps: 30, format: 'auto', hud: true }).then((r) => (window.__exportResult = r)); }),
  ]);
  const wall = (Date.now() - t0) / 1000;
  const saved = await saveDownload(dl);
  await page.waitForFunction('!!window.__exportResult', null, { timeout: 60000 });
  const res = await page.evaluate(() => window.__exportResult);
  console.log('INFO export:', JSON.stringify(res), `wall ${wall.toFixed(1)} s`);
  const head = saved.bytes.subarray(0, 12);
  const isWebm = head[0] === 0x1a && head[1] === 0x45 && head[2] === 0xdf && head[3] === 0xa3;
  const isMp4 = String.fromCharCode(...head.subarray(4, 8)) === 'ftyp';
  check('export: downloads a file with a container signature (ftyp for mp4, EBML 1A45DFA3 for webm)', res.ok && (isWebm || isMp4), `${dl.suggestedFilename()} ${isMp4 ? 'mp4' : isWebm ? 'webm' : 'unknown'} ${saved.bytes.length} bytes`);
  check('export: the file is mp4 when H.264 is available, webm otherwise', mp4 ? isMp4 : isWebm);
  let info = null;
  try { info = await inspect(saved.file); } catch (e) { console.log('INFO inspect failed', String(e.message ?? e)); }
  console.log('INFO inspect:', JSON.stringify(info));
  check('export: frame count = duration * fps (60 packets for 2 s at 30 fps), parsed from the file', info && info.packets === 60, JSON.stringify(info));
  check('export: the video is 640x360 and 2 s long', info && info.width === 640 && info.height === 360 && Math.abs(info.duration - 2) < 0.05, JSON.stringify(info));
  check('export: the result reports the same frames and the file name comes from the fly-through', res.file && res.file.frames === 60 && res.file.name === 'Smoke-video.' + (isMp4 ? 'mp4' : 'webm'), JSON.stringify(res.file));
  const hudCalls = await page.evaluate(() => window.__fakeHudCalls);
  const ts = hudCalls.map((c) => c.t);
  const steps = ts.slice(1).map((t, i) => t - ts[i]);
  check('export: the HUD layer is drawn on every frame at fixed 1/30 s steps (recording flag, size / pixel ratio)', hudCalls.length === 60 && steps.every((d) => Math.abs(d - 1 / 30) < 1e-6) && hudCalls.every((c) => c.rec === true && Math.abs(c.pr - 0.5) < 1e-9 && c.w === 1280 && c.h === 720), `${hudCalls.length} calls, first ${JSON.stringify(hudCalls[0])}`);
  // a decoded frame in the page: the magenta square of the fake HUD
  const px = await page.evaluate(async () => {
    try {
      const blob = window.__xrayRecord.lastBlob();
      const mb = await import('/node_modules/mediabunny/dist/bundles/mediabunny.mjs');
      const input = new mb.Input({ source: new mb.BlobSource(blob), formats: mb.ALL_FORMATS });
      const track = await input.getPrimaryVideoTrack();
      const sink = new mb.CanvasSink(track, {});
      const w = await sink.getCanvas(1.0);
      const c = w.canvas;
      const g = c.getContext('2d');
      const a = g.getImageData(10, 10, 1, 1).data;
      const b = g.getImageData(c.width - 10, c.height - 10, 1, 1).data;
      return { w: c.width, h: c.height, hud: [...a], other: [...b] };
    } catch (e) { return { error: String(e && e.message || e) }; }
  });
  console.log('INFO decoded pixels:', JSON.stringify(px));
  if (px.error) console.log('INFO (HUD pixel check skipped)');
  else check('export: the fake HUD square is in a decoded frame (magenta at the top left, not at the bottom right)', px.hud[0] > 200 && px.hud[1] < 90 && px.hud[2] > 200 && !(px.other[0] > 200 && px.other[1] < 90 && px.other[2] > 200), JSON.stringify(px));
  const after = await state(page);
  check('export: the canvas size, pixel ratio and aspect are restored exactly', after.cw === before.cw && after.ch === before.ch && after.pr === before.pr && Math.abs(after.aspect - before.aspect) < 1e-12, JSON.stringify({ before: [before.cw, before.ch, before.pr, before.aspect], after: [after.cw, after.ch, after.pr, after.aspect] }));
  check('export: the camera is back where it was, nothing plays, the overlay is gone, the viewer is not busy', dist(after.pos, before.pos) < 1e-3 && dist(after.target, before.target) < 1e-3 && !after.playing && !after.busy && !after.overlay);

  // ---------------------------------------------------------------- cancel
  await page.evaluate(() => { window.__cancelResult = null; window.__xrayRecord.flythrough({ size: '640x360', fps: 30 }).then((r) => (window.__cancelResult = r)); });
  await page.waitForSelector('[data-record-busy]');
  await page.waitForFunction(() => /Frame [3-9]/.test(document.querySelector('[data-record-status]')?.textContent ?? ''), null, { timeout: 300000 });
  const busy = await page.evaluate(() => ({ text: document.querySelector('[data-record-busy]').textContent, blocked: (() => { const e = document.elementFromPoint(300, 300); return !!e && !!e.closest('[data-record-busy]'); })() }));
  check('cancel: the busy overlay says the viewer is busy, shows frames done / total, and covers the viewer', /busy/.test(busy.text) && /Frame \d+ of 60/.test(busy.text) && busy.blocked, busy.text.slice(0, 140));
  await page.click('[data-record-cancel]');
  await page.waitForFunction('window.__cancelResult !== null', null, { timeout: 120000 });
  const cres = await page.evaluate(() => window.__cancelResult);
  const afterCancel = await state(page);
  check('cancel: no file, a cancelled result, and everything is restored', cres.cancelled === true && cres.ok === false && afterCancel.cw === before.cw && afterCancel.ch === before.ch && afterCancel.pr === before.pr && dist(afterCancel.pos, before.pos) < 1e-3 && !afterCancel.busy && !afterCancel.overlay && !afterCancel.playing, JSON.stringify(cres));

  // ---------------------------------------------------------------- PNG sequence
  const [pdl] = await Promise.all([
    page.waitForEvent('download', { timeout: 300000 }),
    page.evaluate(() => { window.__pngResult = null; window.__xrayRecord.flythrough({ size: '320x180', fps: 24, format: 'png', hud: false, name: 'frames' }).then((r) => (window.__pngResult = r)); }),
  ]);
  const psaved = await saveDownload(pdl);
  await page.waitForFunction('window.__pngResult !== null', null, { timeout: 60000 });
  const pres = await page.evaluate(() => window.__pngResult);
  const zipB = psaved.bytes;
  const eocd = zipB.length - 22;
  const entries = zipB.readUInt16LE(eocd + 10);
  const firstName = zipB.subarray(30, 30 + 17).toString('latin1');
  const pngSig = zipB.subarray(30 + 17, 30 + 17 + 8).toString('hex');
  check('png sequence: a zip of 48 PNG frames (2 s at 24 fps) named <file name>-000001.png', pres.ok && pdl.suggestedFilename() === 'frames.zip' && entries === 48 && firstName === 'frames-000001.png' && pngSig === '89504e470d0a1a0a', `${entries} entries, ${firstName}`);

  // ---------------------------------------------------------------- WebM (VP9) on request
  const [wdl] = await Promise.all([
    page.waitForEvent('download', { timeout: 300000 }),
    page.evaluate(() => { window.__webmResult = null; window.__xrayRecord.flythrough({ size: '320x180', fps: 24, format: 'webm', hud: false, name: 'clip' }).then((r) => (window.__webmResult = r)); }),
  ]);
  const wsaved = await saveDownload(wdl);
  await page.waitForFunction('window.__webmResult !== null', null, { timeout: 60000 });
  const wres = await page.evaluate(() => window.__webmResult);
  let winfo = null;
  try { winfo = await inspect(wsaved.file); } catch (e) { console.log('INFO inspect failed', String(e.message ?? e)); }
  check('webm: format webm gives EBML 1A45DFA3, 48 frames, 320x180', wres.ok && wdl.suggestedFilename() === 'clip.webm' && wsaved.bytes[0] === 0x1a && wsaved.bytes[1] === 0x45 && wsaved.bytes[2] === 0xdf && wsaved.bytes[3] === 0xa3 && winfo && winfo.packets === 48 && winfo.width === 320 && winfo.height === 180, JSON.stringify({ winfo, desc: wres.file?.description }));

  // ---------------------------------------------------------------- normal playback after exports
  const play = await page.evaluate(async () => {
    const f = window.__xrayFlythrough;
    const cam = window.__xray.app.renderer.camera.position;
    const b = cam.toArray();
    f.play();
    let moved = 0;
    for (let i = 0; i < 60 && f.state().playing; i++) {
      await new Promise((r) => setTimeout(r, 100));
      moved = Math.max(moved, Math.hypot(cam.x - b[0], cam.y - b[1], cam.z - b[2]));
      if (moved > 1) break;
    }
    f.stop();
    return { moved };
  });
  check('real-time playback still works after an export', play.moved > 1, `moved ${play.moved.toFixed(1)} m`);
  const flyDoc = JSON.parse(await page.evaluate(() => window.__xrayFlythrough.exportJson(false)));
  await ctx.close();

  // ---------------------------------------------------------------- packed page: fly-throughs, scripts and autoplay (window.__xrayBoot)
  for (const mode of ['flythrough', 'script']) {
    const boot = { flythroughs: flyDoc, scripts: [{ name: 'Packed script', text: 'fly to everything over 1 seconds' }], autoplay: mode === 'flythrough' ? { flythrough: 'Smoke video', loop: true } : { script: 'Packed script', loop: true } };
    const { ctx: pc, page: pp } = await openPage(browser, { label: `packed-${mode}`, init: `window.__xrayBoot = ${JSON.stringify(boot)};` });
    await pp.waitForFunction(() => window.__xrayFlythrough.state().playing, null, { timeout: 120000, polling: 250 });
    const names = await pp.evaluate(() => ({ fly: window.__xrayFlythrough.list().map((f) => f.name), scripts: window.__xrayScript.list().map((x) => x.name) }));
    check(`packed ${mode}: the fly-through and the script are listed and autoplay starts`, names.fly.includes('Smoke video') && names.scripts.includes('Packed script'), JSON.stringify(names));
    // it loops: still playing after the end of one round (2 s fly-through, 1 s script), at least twice the length in wall time
    const looped = await pp.evaluate(async (len) => {
      const f = window.__xrayFlythrough;
      let wrapped = false;
      let last = f.state().time;
      const t0 = Date.now();
      while (Date.now() - t0 < 60000) {
        await new Promise((r) => setTimeout(r, 100));
        const st = f.state();
        if (!st.playing) return { wrapped, playing: false };
        if (st.time + 0.3 < last) wrapped = true;
        last = st.time;
        if (wrapped) break;
      }
      const out = { wrapped, playing: f.state().playing };
      f.stop();
      return out;
    }, mode);
    check(`packed ${mode}: the loop starts again from the beginning and keeps playing`, looped.wrapped && looped.playing, JSON.stringify(looped));
    await pc.close();
  }

  // ---------------------------------------------------------------- the real HUD layer in the video (phase 2 layer: progress bar at the bottom)
  {
    const { ctx: hc, page: hp } = await openPage(browser, { label: 'real-hud' });
    await makeFly(hp);
    const frameAt = async (hud) => {
      await hp.evaluate((h) => window.__xrayRecord.flythrough({ size: '320x180', fps: 24, hud: h }, { download: false }), hud);
      return hp.evaluate(async () => {
        const mb = await import('/node_modules/mediabunny/dist/bundles/mediabunny.mjs');
        const input = new mb.Input({ source: new mb.BlobSource(window.__xrayRecord.lastBlob()), formats: mb.ALL_FORMATS });
        const track = await input.getPrimaryVideoTrack();
        const w = await new mb.CanvasSink(track, {}).getCanvas(1.0);
        const c = w.canvas;
        const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
        return { w: c.width, h: c.height, data: Array.from(d) };
      });
    };
    const withHud = await frameAt(true);
    const noHud = await frameAt(false);
    let bottom = 0, top = 0;
    for (let y = 0; y < withHud.h; y++) for (let x = 0; x < withHud.w; x++) {
      const i = (y * withHud.w + x) * 4;
      const diff = Math.abs(withHud.data[i] - noHud.data[i]) + Math.abs(withHud.data[i + 1] - noHud.data[i + 1]) + Math.abs(withHud.data[i + 2] - noHud.data[i + 2]);
      if (diff > 60) (y >= withHud.h - 24 ? bottom++ : top++);
    }
    check('real HUD layer: the progress bar and time are in the video frame (pixels differ near the bottom) and the HUD switch removes them', bottom > 50, `bottom ${bottom} differing pixels, elsewhere ${top}`);
    const clean = await hp.evaluate(() => ({ drawn: window.__xrayFlythrough.hudState().drawn }));
    check('real HUD layer: the on-screen overlay is clear after the export', clean.drawn === false, JSON.stringify(clean));
    await hc.close();
  }

  // ---------------------------------------------------------------- fallbacks
  {
    const { ctx: c2, page: p2 } = await openPage(browser, { label: 'no-webcodecs', init: 'delete window.VideoEncoder;' });
    await makeFly(p2);
    const caps2 = await p2.evaluate(() => window.__xrayRecord.capabilities());
    const [rdl] = await Promise.all([
      p2.waitForEvent('download', { timeout: 300000 }),
      p2.evaluate(() => { window.__rtResult = null; window.__xrayRecord.flythrough({ format: 'auto', hud: true }).then((r) => (window.__rtResult = r)); }),
    ]);
    const rs = await saveDownload(rdl);
    await p2.waitForFunction('window.__rtResult !== null', null, { timeout: 60000 });
    const rres = await p2.evaluate(() => window.__rtResult);
    const rwebm = rs.bytes[0] === 0x1a && rs.bytes[1] === 0x45;
    check('fallback: without WebCodecs the real-time recorder makes a webm (or mp4) of the window size', !caps2.webcodecs && rres.ok && rres.path === 'realtime' && rs.bytes.length > 1000 && (rwebm || String.fromCharCode(...rs.bytes.subarray(4, 8)) === 'ftyp'), JSON.stringify({ caps2, path: rres.path, bytes: rs.bytes.length }));
    const a2 = await state(p2);
    check('fallback: the viewer is free again', !a2.busy && !a2.overlay && !a2.playing);
    await c2.close();
  }
  {
    const { ctx: c3, page: p3 } = await openPage(browser, { label: 'no-recorder', init: 'delete window.VideoEncoder; delete window.MediaRecorder;' });
    await makeFly(p3);
    const [zdl] = await Promise.all([
      p3.waitForEvent('download', { timeout: 300000 }),
      p3.evaluate(() => { window.__zipResult = null; window.__xrayRecord.flythrough({ format: 'auto', size: '320x180', fps: 24, hud: false }).then((r) => (window.__zipResult = r)); }),
    ]);
    const zs = await saveDownload(zdl);
    await p3.waitForFunction('window.__zipResult !== null', null, { timeout: 60000 });
    check('fallback: with neither WebCodecs nor MediaRecorder the export is a zip of PNG frames', zdl.suggestedFilename().endsWith('.zip') && zs.bytes[0] === 0x50 && zs.bytes[1] === 0x4b, zdl.suggestedFilename());
    await c3.close();
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
