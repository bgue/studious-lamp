// Headless check of sectioning (box with draggable handles, plane, caps, BCF clipping, picking).
//   SMOKE_PORT=5361 node bench/smoke-section.mjs
// fzk-haus with a window selected. Writes bench/section-*.png:
//   section-off, section-box (caps on), section-box-nocaps, section-plane, section-box-plane, section-handle-drag,
//   section-radiograph (section with the radiograph style), section-behind (behind-only with a box on), section-bcf-applied
// and prints the checks: standard pixel identity after clear (of the 3D view only, see below), handle drag, picking never returns a clipped hit,
// the BCF round trip (create a topic with planes, clear, apply, getClipPlanes matches), and undo and redo of a handle drag and of
// applying a BCF viewpoint (one step each).
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const port = Number(process.env.SMOKE_PORT ?? 5361);
const VIEW = { width: 1400, height: 760 };
const CLIP = { x: 300, y: 0, width: 800, height: 760 };

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

// `view` compares the 3D picture only: the screenshot also holds the top bar (its mode chip is off once the settings are not the factory
// ones), the tool rail and the gizmo with its Undo and Redo buttons (enabled once there is something to undo). Those are chrome that
// is meant to change; the picture under them is what the section must leave as it was.
async function diff(page, a, b, view = false) {
  return page.evaluate(async ([x, y, view]) => {
    const load = async (b64) => {
      const bmp = await createImageBitmap(await (await fetch('data:image/png;base64,' + b64)).blob());
      const c = new OffscreenCanvas(bmp.width, bmp.height);
      const g = c.getContext('2d');
      g.drawImage(bmp, 0, 0);
      return { data: g.getImageData(0, 0, bmp.width, bmp.height).data, width: bmp.width };
    };
    const { data: A, width: W } = await load(x);
    const { data: B } = await load(y);
    let sum = 0, big = 0, exact = 0, n = 0;
    for (let i = 0; i < A.length; i += 4) {
      if (view) {
        const px = (i / 4) % W, py = Math.floor(i / 4 / W);
        if (py < 40 || px < 50 || (px > 570 && py > 530)) continue;
      }
      n++;
      let m = 0;
      for (let c = 0; c < 3; c++) { const d = Math.abs(A[i + c] - B[i + c]); sum += d; if (d > m) m = d; }
      if (m > 12) big++;
      if (m === 0) exact++;
    }
    return { meanAbs: +(sum / (n * 3)).toFixed(3), fracOver12: +(big / n).toFixed(4), identical: exact === n };
  }, [a.toString('base64'), b.toString('base64'), view]);
}

let failed = false;
function check(name, ok, detail = '') {
  if (!ok) failed = true;
  console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${detail ? ` (${detail})` : ''}`);
}

let browser;
const errors = [];
try {
  await waitForServer();
  browser = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const page = await browser.newPage({ viewport: VIEW });
  page.on('console', (m) => {
    if (m.type() === 'error') errors.push(`[error] ${m.text()}`);
    if (m.type() === 'warning' && !m.text().startsWith('[help]')) errors.push(`[warning] ${m.text()}`);
  });
  page.on('pageerror', (e) => errors.push(`[pageerror] ${e.message}`));
  await page.goto(`http://127.0.0.1:${port}/?model=fzk-haus&cinematic=off`);
  await page.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: 180000 });
  const startErr = await page.evaluate('window.__xrayError');
  if (startErr) throw new Error(startErr);
  await page.addStyleTag({ content: '.lil-gui, #xray-overlay, #xray-message { visibility: hidden !important }' });

  const settle = (ms = 800) => page.evaluate(async (ms) => {
    for (let i = 0; i < 3; i++) await new Promise((r) => requestAnimationFrame(r));
    await new Promise((r) => setTimeout(r, ms));
    for (let i = 0; i < 2; i++) await new Promise((r) => requestAnimationFrame(r));
  }, ms);
  const shot = async (name, ms) => {
    await settle(ms);
    return page.screenshot({ path: resolve(here, `section-${name}.png`), clip: CLIP, timeout: 180000 });
  };
  const sec = (p) => page.evaluate((p) => window.__xraySection.set(p), p);

  const setup = await page.evaluate(async () => {
    const app = window.__xray.app;
    app.selectIds([22]);
    const r = app.renderer;
    const sleep = (ms) => new Promise((x) => setTimeout(x, ms));
    r.camera.position.set(6, 5.5, 13);
    r.controls.target.set(-3.95, -1.8, -4.8);
    r.camera.near = 0.1;
    r.camera.updateProjectionMatrix();
    r.controls.update();
    app.runSightlinesNow();
    for (let i = 0; i < 400 && !app.controller.converged; i++) await sleep(25);
    await sleep(200);
    return { api: !!window.__xraySection, clip: typeof r.setClipPlanes === 'function', bcf: !!window.__xrayBcf };
  });
  console.log('apis', JSON.stringify(setup));

  const base = await shot('off', 900);

  // ---- box fitted to the selection, caps on / off
  const fitted = await page.evaluate(() => { const b = window.__xraySection.fitToSelection(); return b; });
  console.log('fitted box', JSON.stringify(fitted));
  await sec({ box: { margin: 1.2 }, caps: true });
  await settle(300);
  check('box fit created planes', (await page.evaluate(() => window.__xray.app.renderer.getClipPlanes()?.length)) === 6);
  const capped = await shot('box', 1200);
  console.log('box + caps vs off', JSON.stringify(await diff(page, base, capped)));
  await sec({ caps: false });
  const nocaps = await shot('box-nocaps', 1000);
  console.log('box caps off vs caps on', JSON.stringify(await diff(page, capped, nocaps)));
  await sec({ caps: true });

  // ---- handle drag: drag the +x handle outward with the mouse (page coordinates)
  const before = await page.evaluate(() => JSON.parse(JSON.stringify(window.__xraySection.config.box)));
  const dots = await page.evaluate(() => [...document.querySelectorAll('.xray-svg-overlay [data-layer="section"] circle')].map((c) => { const r = c.getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2, vis: c.getAttribute('visibility') }; }));
  console.log('handles on screen', JSON.stringify(dots.map((d) => [Math.round(d.x), Math.round(d.y), d.vis])));
  check('six handles', dots.length === 6);
  // the +y handle (index 3): drag it straight up the screen
  const h = dots[3];
  await page.mouse.move(h.x, h.y);
  await page.mouse.down();
  await page.mouse.move(h.x, h.y - 40, { steps: 6 });
  await page.mouse.move(h.x, h.y - 80, { steps: 6 });
  await page.mouse.up();
  const after = await page.evaluate(() => JSON.parse(JSON.stringify(window.__xraySection.config.box)));
  console.log('box max y before/after drag', before.max[1].toFixed(3), after.max[1].toFixed(3), 'min y', before.min[1].toFixed(3), after.min[1].toFixed(3));
  check('dragging the +y handle moved only that face up', after.max[1] > before.max[1] + 0.05 && Math.abs(after.min[1] - before.min[1]) < 1e-9 && Math.abs(after.max[0] - before.max[0]) < 1e-9);
  check('renderer planes follow the drag', await page.evaluate((y) => { const p = window.__xray.app.renderer.getClipPlanes().find((q) => q.normal[1] === -1); return !!p && Math.abs(p.point[1] - y) < 1e-6; }, after.max[1]));
  const dragged = await shot('handle-drag', 900);
  console.log('after drag vs before', JSON.stringify(await diff(page, capped, dragged)));
  // the drag is one undo step: the box and the planes go back together, redo drags it again
  await settle(1500); // the step settles after the planes have been still for a moment (longer on slow frames)
  const lastUndo = await page.evaluate(() => window.__xrayUndo.list().undo.map((e) => `${e.kind}:${e.label}`).slice(-1)[0]);
  check('the handle drag is one undo step (a section move)', lastUndo === 'section:section move', String(lastUndo));
  await page.evaluate(() => window.__xrayUndo.undo());
  await settle(800);
  const undone = await page.evaluate(() => ({ box: JSON.parse(JSON.stringify(window.__xraySection.config.box)), planes: window.__xray.app.renderer.getClipPlanes().find((q) => q.normal[1] === -1)?.point[1] }));
  check('undo puts the box and the clip plane back', Math.abs(undone.box.max[1] - before.max[1]) < 1e-6 && Math.abs(undone.planes - before.max[1]) < 1e-6, JSON.stringify(undone));
  await page.evaluate(() => window.__xrayUndo.redo());
  await settle(800);
  check('redo drags it again', await page.evaluate((y) => Math.abs(window.__xraySection.config.box.max[1] - y) < 1e-6 && Math.abs(window.__xray.app.renderer.getClipPlanes().find((q) => q.normal[1] === -1).point[1] - y) < 1e-6, after.max[1]));
  await sec({ box: { min: before.min, max: before.max } });

  // ---- picking never returns a clipped hit
  const pickRes = await page.evaluate(async () => {
    await new Promise((r) => setTimeout(r, 300));
    const app = window.__xray.app;
    const r = app.renderer;
    const planes = r.getClipPlanes();
    const els = app.loaded.model.elements;
    let picked = 0, bad = 0, hidden = 0;
    for (let ix = -9; ix <= 9; ix++) for (let iy = -9; iy <= 9; iy++) {
      const id = r.pick(ix / 10, iy / 10);
      if (id === null) { hidden++; continue; }
      picked++;
      // the element must reach into the kept region: some corner of its bounds on the kept side of every plane, or straddling
      const b = els[id].bounds;
      const inside = planes.every((p) => {
        let best = -Infinity;
        for (let i = 0; i < 8; i++) {
          const q = [i & 1 ? b[3] : b[0], i & 2 ? b[4] : b[1], i & 4 ? b[5] : b[2]];
          best = Math.max(best, p.normal[0] * (q[0] - p.point[0]) + p.normal[1] * (q[1] - p.point[1]) + p.normal[2] * (q[2] - p.point[2]));
        }
        return best >= -1e-6;
      });
      if (!inside) bad++;
    }
    return { picked, bad, hidden };
  });
  console.log('pick grid', JSON.stringify(pickRes));
  check('picking only returns elements that reach the kept region', pickRes.bad === 0 && pickRes.picked > 0);

  // ---- plane section (box off)
  await sec({ box: { enabled: false } });
  await sec({ plane: { enabled: true, axis: 'y', offset: -0.5, flip: false } });
  const plane = await shot('plane', 1200);
  console.log('plane y vs off', JSON.stringify(await diff(page, base, plane)));
  await sec({ plane: { axis: 'x', offset: -4, flip: true } });
  await shot('plane-x', 1000);
  await sec({ plane: { axis: 'camera', offset: 0, flip: false } });
  await shot('plane-camera', 1000);
  await sec({ plane: { axis: 'y', offset: -0.5, flip: false }, box: { enabled: true } });
  await settle(300);
  check('box plus plane makes seven planes', (await page.evaluate(() => window.__xray.app.renderer.getClipPlanes()?.length)) === 7);
  await shot('box-plane', 1200);

  // ---- section with the radiograph style, and with behind-only
  await sec({ plane: { enabled: false } });
  await page.evaluate(() => window.__xrayImaging.set({ style: 'radiograph' }));
  await shot('radiograph', 1400);
  await page.evaluate(() => window.__xrayImaging.set({ style: 'standard' }));
  await page.evaluate(() => window.__xrayViewModes.setBehind({ enabled: true, frontTreatment: 'cut + cap', offset: 0.2 }));
  await shot('behind', 1400);
  await page.evaluate(() => window.__xrayViewModes.setBehind({ enabled: false }));

  // ---- BCF round trip
  await sec({ box: { enabled: true }, plane: { enabled: true, axis: 'x', offset: 0.5, flip: false } });
  await settle(500);
  const bcf = await page.evaluate(async () => {
    const r = window.__xray.app.renderer;
    const norm = (ps) => (ps ?? []).map((p) => ({ n: p.normal.map((v) => +(v / Math.hypot(...p.normal)).toFixed(5)), p: p.point.map((v) => +v.toFixed(4)) }));
    const have = norm(r.getClipPlanes());
    const topic = window.__xrayBcf.createTopic({ title: 'Section round trip', snapshot: false });
    const vp = topic.viewpoints[0].data;
    window.__xraySection.clear();
    await new Promise((x) => setTimeout(x, 4000)); // longer than the undo settle time even on slow frames: clearing and applying are two steps
    const cleared = r.getClipPlanes();
    const report = window.__xrayBcf.applyViewpoint(topic.guid);
    await new Promise((x) => setTimeout(x, 400));
    const applied = norm(r.getClipPlanes());
    return { have, applied, cleared, clipping: vp.clipping.length, report: report.applied, cap: r.renderer ? null : null };
  });
  console.log('bcf clipping planes captured', bcf.clipping, 'cleared ->', JSON.stringify(bcf.cleared), 'applied', JSON.stringify(bcf.report));
  check('topic captured the seven planes', bcf.clipping === 7);
  check('clearing the section removed the planes', bcf.cleared === null);
  const sameN = bcf.have.length === bcf.applied.length;
  const maxErr = sameN ? Math.max(...bcf.have.map((a, i) => Math.max(...a.n.map((v, k) => Math.abs(v - bcf.applied[i].n[k])), ...a.p.map((v, k) => Math.abs(v - bcf.applied[i].p[k]))))) : 1e9;
  check('applying the viewpoint restores the planes', sameN && maxErr < 1e-3, `max error ${maxErr}`);
  await shot('bcf-applied', 1500);
  // applying the viewpoint (its planes, with the pivot it moves) is one undo step; undo takes the planes off, redo puts them back, and
  // Clear viewpoint still removes them after that (the viewpoint keeps them as its own)
  await settle(1500);
  const bu = await page.evaluate(() => window.__xrayUndo.list().undo.map((e) => `${e.kind}:${e.label}`).slice(-1)[0]);
  check('applying a BCF viewpoint with planes is one undo step', /^(view|section):.*section/.test(String(bu)), String(bu));
  await page.evaluate(() => window.__xrayUndo.undo());
  await settle(800);
  check('undo takes the viewpoint planes off', (await page.evaluate(() => window.__xray.app.renderer.getClipPlanes())) === null, await page.evaluate(() => JSON.stringify({ planes: window.__xray.app.renderer.getClipPlanes()?.length ?? null, foreign: window.__xraySection.foreignPlanes(), box: window.__xraySection.config.box.enabled, list: window.__xrayUndo.list() })));
  await page.evaluate(() => window.__xrayUndo.redo());
  await settle(800);
  check('redo puts the viewpoint planes back', (await page.evaluate(() => window.__xray.app.renderer.getClipPlanes()?.length)) === 7);
  await page.evaluate(() => window.__xrayBcf.clearViewpoint());
  check('clearing the viewpoint removes the planes', (await page.evaluate(() => window.__xray.app.renderer.getClipPlanes())) === null);

  // ---- back to normal: pixel identical to the start
  await page.evaluate(() => window.__xraySection.clear());
  const end = await shot('off-again', 1200);
  const dEnd = await diff(page, base, end, true);
  console.log('after clear vs before', JSON.stringify(dEnd));
  // the BCF viewpoint re-ran the sightlines, so ghost alpha smoothing may differ in the last bits: no pixel may differ by more than 12
  check('cleared section matches the start (no pixel differs by more than 12)', dEnd.fracOver12 === 0 && dEnd.meanAbs < 0.1, `mean ${dEnd.meanAbs}`);

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
