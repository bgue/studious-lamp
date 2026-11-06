// Headless end-to-end check of point cloud alignment on /?model=building (1600x900), with the phone LiDAR style
// sample public/samples/building-phone-scan.ply (tools/make_pointcloud.py --phone: one room, Y up, own origin,
// heading 37 degrees, 1.5 cm noise; the true transform is in its header):
//   - open the Scan drawer, load the file through the drawer's file input, coordinates = viewer
//   - move the cloud aside (offset x), hide the roof, look down into the room
//   - Align by 3 points by real mouse clicks: cloud point, model point, x 4 (floor spots near the room corners and a
//     kitchen corner); Escape and Undo last on the way; residuals and RMS in the drawer; Apply alignment
//   - Refine (ICP) from the drawer button, then Compute deviation
//   - prints the recovered vs true transform error after each step and the median deviation; writes
//     bench/pointcloud-align-pairs.png (markers) and bench/pointcloud-align-icp.png (deviation colours)
//   - Undo alignment restores the previous transform
//   - picking ignores cloud points behind an opaque wall (alpha 1), and picks them through the same wall ghosted (0.15)
//   - Stop ICP by a real click while a run is in progress (the button does not move, the alignment stays)
//   - align within = section box: ICP fits only the points in the box; the drift grid (3 x 3 plan regions) shows
//   - zero console errors
// Usage: SMOKE_PORT=5641 node bench/smoke-pointcloud-align.mjs
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const port = Number(process.env.SMOKE_PORT ?? 5641);
const PLY = resolve(root, 'public/samples/building-phone-scan.ply');

function loadPlaywright() {
  const candidates = [process.env.PLAYWRIGHT_MODULE, resolve(root, 'node_modules/playwright'), '/opt/node-tools/node_modules/playwright', '/opt/node22/lib/node_modules/playwright', 'playwright'].filter(Boolean);
  for (const c of candidates) {
    try { return createRequire(import.meta.url)(c); } catch { /* next */ }
  }
  throw new Error('playwright not found; set PLAYWRIGHT_MODULE');
}
const { chromium } = loadPlaywright();

// truth from the header: viewer = Ry(h) * p + t
const head = readFileSync(PLY).subarray(0, 600).toString('latin1');
const tm = /comment truth: viewer = Ry\(([-\d.]+) deg\) \* p \+ \(([-\d.]+), ([-\d.]+), ([-\d.]+)\)/.exec(head);
if (!tm) throw new Error('no truth comment in the PLY header');
const H = Number(tm[1]), T = [Number(tm[2]), Number(tm[3]), Number(tm[4])];
const c = Math.cos((H * Math.PI) / 180), s = Math.sin((H * Math.PI) / 180);
const TRUE = [c, 0, -s, 0, 0, 1, 0, 0, s, 0, c, 0, T[0], T[1], T[2], 1];
/** model (viewer) point -> scan frame point: p = Ry(-h) (v - t) */
const toScan = (v) => {
  const d = [v[0] - T[0], v[1] - T[1], v[2] - T[2]];
  return [c * d[0] - s * d[2], d[1], s * d[0] + c * d[2]];
};

const vite = spawn(resolve(root, 'node_modules/.bin/vite'), ['--config', 'bench/vite.smoke.config.mjs', '--host', '127.0.0.1', '--port', String(port), '--strictPort'], { cwd: root, stdio: ['ignore', 'pipe', 'pipe'] });
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
let browser;
try {
  await waitForServer();
  browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1600, height: 900 } });
  const page = await ctx.newPage();
  page.setDefaultTimeout(180000);
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', (e) => errors.push(`[pageerror] ${e.message}`));

  await page.goto(`http://127.0.0.1:${port}/?model=building`);
  await page.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: 240000 });
  const err = await page.evaluate('window.__xrayError');
  if (err) throw new Error(`startup failed: ${err}`);

  // helpers in the page: transform error against the truth, screen position of a viewer point
  await page.evaluate((TRUE) => {
    window.__t = {
      TRUE,
      err(m, at) {
        const ap = (M, p) => [M[0] * p[0] + M[4] * p[1] + M[8] * p[2] + M[12], M[1] * p[0] + M[5] * p[1] + M[9] * p[2] + M[13], M[2] * p[0] + M[6] * p[1] + M[10] * p[2] + M[14]];
        let tr = 0;
        for (let i = 0; i < 3; i++) for (let k = 0; k < 3; k++) tr += TRUE[i * 4 + k] * m[i * 4 + k];
        const rot = (Math.acos(Math.min(1, Math.max(-1, (tr - 1) / 2))) * 180) / Math.PI;
        const a = ap(TRUE, at), b = ap(m, at);
        return { rotationDeg: rot, translation: Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]), vector: [b[0] - a[0], b[1] - a[1], b[2] - a[2]].map((v) => +(v * 1000).toFixed(1)) };
      },
      screen(v) {
        const r = window.__xray.renderer;
        const cam = r.camera;
        cam.updateMatrixWorld();
        const P = cam.projectionMatrix.elements, V = cam.matrixWorldInverse.elements;
        const mul4 = (M, p) => [0, 1, 2, 3].map((i) => M[i] * p[0] + M[4 + i] * p[1] + M[8 + i] * p[2] + M[12 + i] * p[3]);
        const q = mul4(P, mul4(V, [v[0], v[1], v[2], 1]));
        const rect = window.__xray.app.canvas.getBoundingClientRect();
        return { x: rect.left + (q[0] / q[3] * 0.5 + 0.5) * rect.width, y: rect.top + (0.5 - q[1] / q[3] * 0.5) * rect.height };
      },
      view(pos, target) {
        const r = window.__xray.renderer;
        r.camera.position.set(...pos);
        r.controls.target.set(...target);
        r.camera.lookAt(...target);
        r.controls.update();
        r.markDirty();
      },
    };
  }, TRUE);

  // ---------------------------------------------------------------- load in the drawer
  await page.evaluate(() => window.__xrayToolbar.open('pointcloud'));
  await page.waitForSelector('#pointcloud-drawer');
  await page.setInputFiles('#pointcloud-drawer ~ input[data-pointcloud="open"], input[data-pointcloud="open"]', PLY);
  await page.waitForFunction(() => window.__xrayPointCloud.stats.loaded && !window.__xrayPointCloud.controller.busy, null, { timeout: 120000 });
  const st = await page.evaluate(() => ({ ...window.__xrayPointCloud.stats }));
  check('phone scan loads', st.shownCount === 150000, `${st.shownCount} points, ${st.format}, ${st.mode}`);
  const coord = page.locator('#pointcloud-drawer .xt-select', { hasText: 'coordinates' }).locator('select');
  await coord.selectOption('viewer');
  // offset x moves the cloud aside so its points and the model's can be told apart on screen
  const offx = page.locator('#pointcloud-drawer .xt-select', { hasText: 'offset x' }).locator('input');
  await offx.fill('7');
  await offx.dispatchEvent('change');
  const start = await page.evaluate(() => window.__t.err(window.__xrayPointCloud.matrix, [0, -1.5, -1]));
  console.log(`start: rotation error ${start.rotationDeg.toFixed(2)} deg, translation error ${start.translation.toFixed(3)} m`);

  // ---------------------------------------------------------------- 3-point alignment by clicks
  await page.evaluate(() => {
    const c = window.__xray.app.controller;
    const roof = c.model.elements.filter((e) => /roof/.test(e.name ?? '')).map((e) => e.id);
    c.setSelection(roof);
    c.hideSelected();
    c.clearSelection();
  });
  // look down into the room so that every target, on the model and on the moved cloud, lies in the part of the canvas
  // that the drawer leaves free
  // candidates: a grid of floor spots in the room and the front corner of the kitchen top; the user clicks what they
  // see, so the test keeps the ones visible on both the model and the cloud in this view
  const cands = [[1.75, -1.65, 0.5]];
  for (let x = -2.2; x <= 1.6; x += 0.38) for (let z = -2.5; z <= 0.8; z += 0.33) cands.push([+x.toFixed(2), -2.55, +z.toFixed(2)]);
  const worldTargets = [...cands, ...(await page.evaluate((cs) => cs.map((p) => window.__xrayPointCloud.controller.toViewer(p)), cands.map(toScan)))];
  await page.evaluate((pts) => {
    const cv = window.__xray.app.canvas.getBoundingClientRect();
    const dr = document.getElementById('xray-toolbar-drawer')?.getBoundingClientRect();
    const freeL = Math.max(cv.left, dr && dr.width ? dr.right : cv.left) + 30, freeR = cv.right - 30;
    let cx = pts.reduce((s, p) => s + p[0], 0) / pts.length, cz = pts.reduce((s, p) => s + p[2], 0) / pts.length, d = 14;
    for (let it = 0; it < 12; it++) {
      window.__t.view([cx, -2.5 + d * 0.99, cz + d * 0.12], [cx, -2.5, cz]);
      const sp = pts.map((p) => window.__t.screen(p));
      const lo = Math.min(...sp.map((q) => q.x)), hi = Math.max(...sp.map((q) => q.x));
      const top = Math.min(...sp.map((q) => q.y)), bot = Math.max(...sp.map((q) => q.y));
      const pxPerM = (hi - lo) / (Math.max(...pts.map((p) => p[0])) - Math.min(...pts.map((p) => p[0])));
      cx -= ((freeL + freeR) / 2 - (lo + hi) / 2) / pxPerM;
      cz -= (cv.top + cv.height / 2 - (top + bot) / 2) / pxPerM;
      d *= Math.max(0.6, Math.min(1.6, (hi - lo) / (0.8 * (freeR - freeL))));
    }
  }, worldTargets);
  await page.waitForTimeout(800);
  const vis = await page.evaluate(({ cands, scan }) => {
    const pc = window.__xrayPointCloud;
    return cands.map((v, i) => {
      const s = window.__t.screen(v);
      const m = pc.controller.pickModelAt(s.x, s.y);
      const w = pc.controller.toViewer(scan[i]);
      const sc = window.__t.screen(w);
      const c = pc.pickCloudAt(sc.x, sc.y);
      const em = m ? Math.hypot(m.point[0] - v[0], m.point[1] - v[1], m.point[2] - v[2]) : Infinity;
      const ec = c ? Math.hypot(c.world[0] - w[0], c.world[1] - w[1], c.world[2] - w[2]) : Infinity;
      return em < 0.02 && ec < 0.06;
    });
  }, { cands, scan: cands.map(toScan) });
  const seen = cands.filter((_, i) => vis[i]);
  const floor = seen.filter((v) => v[1] < -2.5);
  const ext = (f) => floor.reduce((b, v) => (f(v) > f(b) ? v : b), floor[0]);
  const targets = [ext((v) => -v[0] - v[2]), ext((v) => -v[0] + v[2]), ext((v) => v[0] - v[2]), vis[0] ? cands[0] : ext((v) => v[0] + v[2])];
  console.log(`visible candidates: ${seen.length} of ${cands.length}; targets ${JSON.stringify(targets)}`);
  await page.locator('#pointcloud-drawer .xt-btn', { hasText: 'Align by 3 points' }).click();
  check('3-point mode starts', await page.evaluate(() => window.__xrayPointCloud.pairs.active));
  const clickCloud = async (v) => {
    const w = await page.evaluate((cs) => window.__xrayPointCloud.controller.toViewer(cs), toScan(v));
    const p = await page.evaluate((w) => window.__t.screen(w), w);
    await page.mouse.click(p.x, p.y);
  };
  const clickModel = async (v) => {
    const p = await page.evaluate((v) => window.__t.screen(v), v);
    await page.mouse.click(p.x, p.y);
  };
  // Escape undoes a pending cloud point
  await clickCloud(targets[0]);
  const pend = await page.evaluate(() => window.__xrayPointCloud.pairs.step);
  await page.keyboard.press('Escape');
  const afterEsc = await page.evaluate(() => ({ step: window.__xrayPointCloud.pairs.step, n: window.__xrayPointCloud.controller.pairs.length, active: window.__xrayPointCloud.pairs.active }));
  check('Escape undoes the pending cloud point', pend === 'model' && afterEsc.step === 'cloud' && afterEsc.n === 0 && afterEsc.active);
  for (const [i, v] of targets.entries()) {
    await clickCloud(v);
    await clickModel(v);
    if (i === 1) {
      // Undo last takes the model point back; pick it again
      await page.locator('#pointcloud-drawer .xt-btn', { hasText: 'Undo last' }).click();
      const st2 = await page.evaluate(() => window.__xrayPointCloud.pairs.step);
      check('Undo last removes the model point', st2 === 'model');
      await clickModel(v);
    }
  }
  const pairs = await page.evaluate(() => {
    const c = window.__xrayPointCloud.controller;
    const sol = c.pairSolution;
    return { n: c.completePairs.length, rms: sol?.rms, residuals: sol?.residuals, warnings: sol?.warnings, list: document.querySelector('.pc-pair-list')?.textContent, markers: document.querySelectorAll('[data-pair-cloud]').length + document.querySelectorAll('[data-pair-model]').length };
  });
  check('4 pairs picked by clicks, residuals listed', pairs.n === 4 && pairs.residuals?.length === 4 && /RMS/.test(pairs.list ?? ''), `RMS ${(pairs.rms * 100).toFixed(1)} cm, residuals ${pairs.residuals?.map((r) => (r * 100).toFixed(1)).join(' / ')} cm`);
  console.log(`  drawer: ${pairs.list}`);
  await page.waitForTimeout(300);
  check('numbered markers in two colours drawn', pairs.markers === 8, `${pairs.markers} markers`);
  await page.screenshot({ path: resolve(here, 'pointcloud-align-pairs.png') });
  await page.locator('#pointcloud-drawer .xt-btn', { hasText: 'Apply alignment' }).click();
  const m3 = await page.evaluate(() => ({ m: window.__xrayPointCloud.matrix, s: { ...window.__xrayPointCloud.settings }, status: window.__xrayPointCloud.status }));
  const e3 = await page.evaluate((m) => window.__t.err(m, [0, -1.5, -1]), m3.m);
  console.log(`3-point: rotation error ${e3.rotationDeg.toFixed(3)} deg, translation error ${(e3.translation * 1000).toFixed(1)} mm; offset ${m3.s.offsetX.toFixed(3)}, ${m3.s.offsetY.toFixed(3)}, ${m3.s.offsetZ.toFixed(3)}, rotation ${m3.s.rotationDeg.toFixed(2)}`);
  console.log(`  status: ${m3.status}`);
  check('3-point alignment lands within 5 cm / 1 deg', e3.translation < 0.05 && e3.rotationDeg < 1);
  check('keep vertical result shows as offset + rotation', m3.s.matrix.every((v, i) => Math.abs(v - (i % 5 === 0 ? 1 : 0)) < 1e-12));

  // ---------------------------------------------------------------- ICP
  await page.locator('#pointcloud-drawer .xt-btn', { hasText: 'Refine (ICP)' }).click();
  await page.waitForFunction(() => window.__xrayPointCloud.stats.icp && !window.__xrayPointCloud.controller.busy, null, { timeout: 300000 });
  const icp = await page.evaluate(() => ({ m: window.__xrayPointCloud.matrix, icp: window.__xrayPointCloud.stats.icp, status: window.__xrayPointCloud.status }));
  const ei = await page.evaluate((m) => window.__t.err(m, [0, -1.5, -1]), icp.m);
  console.log(`ICP: rotation error ${ei.rotationDeg.toFixed(4)} deg, translation error ${(ei.translation * 1000).toFixed(2)} mm; ${icp.icp.iterations} iterations, inliers ${(icp.icp.inlierFraction * 100).toFixed(0)}%, RMS ${(icp.icp.rmsBefore * 100).toFixed(2)} -> ${(icp.icp.rmsAfter * 100).toFixed(2)} cm, ${(icp.icp.ms / 1000).toFixed(1)} s`);
  console.log(`  status: ${icp.status}`);
  console.log(`  error vector (mm, viewer x y z): 3-point ${JSON.stringify(e3.vector)}, ICP ${JSON.stringify(ei.vector)}`);
  check('ICP improves on the 3-point result and lands within 5 mm / 0.1 deg', !icp.icp.reverted && ei.translation < 0.005 && ei.rotationDeg < 0.1 && ei.translation <= e3.translation);
  check('ICP used oriented normals', icp.icp.normalMode === 'oriented', `${icp.icp.withNormal} of ${icp.icp.samples} sample points with a normal, ${icp.icp.oriented} oriented`);
  const grid = await page.evaluate(() => ({ cells: [...document.querySelectorAll('[data-pc-regions] [data-region]')].map((e) => e.textContent), text: document.querySelector('[data-pc-regions]')?.textContent ?? '' }));
  check('drift grid: 9 plan regions under the ICP button', grid.cells.length === 9, grid.cells.join(' | '));

  // ---------------------------------------------------------------- deviation
  await page.evaluate(() => window.__t.view([5.5, 7.5, 6.5], [0, -2, -1])); // the roof stays hidden: look into the room
  await page.locator('#pointcloud-drawer .xt-btn', { hasText: 'Compute deviation' }).click();
  await page.waitForFunction(() => window.__xrayPointCloud.stats.deviation && !window.__xrayPointCloud.controller.busy, null, { timeout: 300000 });
  const dev = await page.evaluate(() => window.__xrayPointCloud.stats.deviation);
  console.log(`deviation: median ${(dev.median * 1000).toFixed(1)} mm, mean ${(dev.mean * 1000).toFixed(1)} mm, p95 ${(dev.p95 * 1000).toFixed(1)} mm, within 2 cm ${(dev.shareWithin * 100).toFixed(1)}%, unrelated ${(dev.unrelatedShare * 100).toFixed(1)}%`);
  check('median deviation near the noise level (< 15 mm)', dev.median < 0.015);
  await page.mouse.move(1250, 260); // off the controls: no help popover in the picture
  await page.waitForTimeout(800);
  await page.screenshot({ path: resolve(here, 'pointcloud-align-icp.png') });
  await page.evaluate(() => window.__xray.app.controller.clearPinsAndHides());

  // ---------------------------------------------------------------- undo
  await page.locator('#pointcloud-drawer .xt-btn', { hasText: 'Undo alignment' }).click();
  const mu = await page.evaluate(() => ({ m: window.__xrayPointCloud.matrix, dev: window.__xrayPointCloud.stats.deviation }));
  const du = Math.max(...mu.m.map((v, i) => Math.abs(v - m3.m[i])));
  check('Undo alignment restores the 3-point transform and clears the deviation', du < 1e-9 && mu.dev === null, `max element change ${du.toExponential(1)}`);

  // ---------------------------------------------------------------- picking behind an opaque wall
  // look at the room from the west, through the left outer wall; a floor spot of the room lies behind that wall
  await page.evaluate(() => window.__t.view([-7.5, -1.6, -1.0], [0, -2.3, -1.0]));
  await page.waitForTimeout(500);
  const occ = await page.evaluate(() => {
    const pc = window.__xrayPointCloud, c = window.__xray.app.controller;
    const wall = c.model.elements.find((e) => /outer wall - house left/.test(e.name ?? ''));
    const floor = [-1.2, -2.55, -1.0];
    const sp = window.__t.screen(floor);
    const depthOf = (v) => { const cam = window.__xray.renderer.camera; cam.updateMatrixWorld(); const e = cam.matrixWorldInverse.elements; return -(e[2] * v[0] + e[6] * v[1] + e[10] * v[2] + e[14]); };
    const run = () => { const p = pc.pickCloudAt(sp.x, sp.y); return p ? { d: depthOf(p.world), x: p.world[0] } : null; };
    // the pick reads the alpha the X-ray classification gives each element: opaque (focus, 1) or a ghost (below 0.5);
    // set it directly for the wall (no frame runs inside this call, so nothing smooths it back)
    const alpha = window.__xray.app.renderer.state.alpha;
    const keep = alpha[wall.id];
    alpha[wall.id] = 1;
    const alphaSel = alpha[wall.id];
    const hidden = run(), wallDepth = pc.controller.occluderDepth(sp.x, sp.y);
    alpha[wall.id] = 0.15;
    const alphaGhost = alpha[wall.id];
    const through = run();
    alpha[wall.id] = keep;
    return { alphaSel, alphaGhost, hidden, through, wallDepth, floorDepth: depthOf(floor) };
  });
  check('pick skips cloud points behind an opaque wall', occ.alphaSel >= 0.5 && Number.isFinite(occ.wallDepth) && (occ.hidden === null || occ.hidden.d <= occ.wallDepth + 0.1), JSON.stringify(occ));
  check('pick finds them through the same wall ghosted', occ.alphaGhost < 0.5 && occ.through !== null && occ.through.d > occ.wallDepth + 0.1, `alpha ${occ.alphaGhost}, picked at depth ${occ.through?.d?.toFixed(2)} m, wall at ${occ.wallDepth.toFixed(2)} m`);

  // ---------------------------------------------------------------- Stop ICP by a real click
  await page.evaluate(() => window.__t.view([5.5, 7.5, 6.5], [0, -2, -1]));
  await page.mouse.move(1250, 260);
  const rough = await page.evaluate((TRUE) => {
    const pc = window.__xrayPointCloud;
    const c = Math.cos(0.2), s = Math.sin(0.2);
    const R = [c, 0, -s, 0, 0, 1, 0, 0, s, 0, c, 0, 0.3, 0, -0.3, 1];
    const mul = (A, B) => { const o = new Array(16).fill(0); for (let cc = 0; cc < 4; cc++) for (let rr = 0; rr < 4; rr++) for (let q = 0; q < 4; q++) o[cc * 4 + rr] += A[q * 4 + rr] * B[cc * 4 + q]; return o; };
    pc.setMatrix(mul(R, TRUE), 'rough start for Stop ICP');
    const m0 = pc.matrix;
    window.__stopRun = pc.refine({ samples: 60000, maxIterations: 60 }).then((r) => (r === null ? 'cancelled' : 'finished'));
    return m0;
  }, TRUE);
  const stopBtn = page.locator('#pointcloud-drawer .xt-btn[data-mode="stop"]');
  await stopBtn.waitFor({ state: 'visible', timeout: 60000 });
  const box0 = await stopBtn.boundingBox();
  const tClick = Date.now();
  await stopBtn.click({ timeout: 120000 });
  const clickMs = Date.now() - tClick;
  const stopped = await page.evaluate(async () => ({ how: await window.__stopRun, status: window.__xrayPointCloud.status, m: window.__xrayPointCloud.matrix, label: document.querySelector('#pointcloud-drawer .xt-btn[data-mode]')?.textContent }));
  const box1 = await page.locator('#pointcloud-drawer .xt-btn[data-mode]').boundingBox();
  const same = Math.max(...stopped.m.map((v, i) => Math.abs(v - rough[i])));
  check('Stop ICP stops the run by a real click and keeps the alignment', stopped.how === 'cancelled' && /stopped/.test(stopped.status) && same < 1e-12 && stopped.label === 'Refine (ICP)', `${stopped.how}, click took ${clickMs} ms, "${stopped.status}"`);
  check('the ICP button does not move while the status changes', Math.abs(box0.y - box1.y) < 0.5, `y ${box0.y.toFixed(1)} -> ${box1.y.toFixed(1)}`);

  // ---------------------------------------------------------------- align within the section box
  await page.evaluate((TRUE) => window.__xrayPointCloud.setMatrix(TRUE.map((v, i) => (i === 12 ? v + 0.02 : v)), 'truth + 2 cm'), TRUE);
  const sec = await page.evaluate(() => {
    const api = window.__xraySection;
    if (!api) return null;
    api.set({ box: { enabled: true, min: [-2.7, -2.7, -2.9], max: [0, 0.7, 1.1] } });
    return api.config.box.enabled;
  });
  if (sec) {
    await page.locator('#pointcloud-drawer .xt-select', { hasText: 'align within' }).locator('select').selectOption('section box');
    await page.locator('#pointcloud-drawer .xt-btn[data-mode="refine"]').click();
    await page.waitForFunction(() => /in the section box/.test(window.__xrayPointCloud.status) && !window.__xrayPointCloud.controller.busy, null, { timeout: 300000 });
    const reg = await page.evaluate(() => ({ icp: window.__xrayPointCloud.stats.icp, m: window.__xrayPointCloud.matrix, grid: document.querySelector('[data-pc-regions]')?.textContent ?? '' }));
    const er = await page.evaluate((m) => window.__t.err(m, [-1.3, -2, -1]), reg.m);
    console.log(`ICP within the section box: ${(er.translation * 1000).toFixed(2)} mm / ${er.rotationDeg.toFixed(4)} deg at the west half; ${reg.icp.samples} sample points; ${reg.grid.slice(0, 160)}`);
    check('align within section box: ICP fits the points in the box', reg.icp.region?.label === 'section box' && !reg.icp.reverted && er.translation < 0.006, `${(er.translation * 1000).toFixed(2)} mm`);
    await page.locator('#pointcloud-drawer .xt-select', { hasText: 'align within' }).locator('select').selectOption('whole cloud');
    await page.evaluate(() => window.__xraySection.clear());
  } else {
    check('section plugin present for align within', false);
  }

  // ---------------------------------------------------------------- ICP basin: rough starts on the real model
  for (const [label, yaw, move, keepVertical] of [['10 deg / 0.3 m, keep vertical', 10, [0.21, 0.05, -0.2], true], ['10 deg / 0.3 m + 1 deg tilt, full 3D', 10, [0.2, 0.1, 0.2], false], ['-15 deg / 0.5 m, keep vertical', -15, [-0.35, 0, 0.35], true]]) {
    const r = await page.evaluate(async ({ TRUE, yaw, move, keepVertical }) => {
      const pc = window.__xrayPointCloud;
      const c = Math.cos((yaw * Math.PI) / 180), s = Math.sin((yaw * Math.PI) / 180);
      const k = [0, -1.5, -1]; // about the room centre
      // P = T(k + move) * R * T(-k), R = Ry(yaw) (with a 1 degree tilt about x for the full 3D run)
      const tc = keepVertical ? 1 : Math.cos(Math.PI / 180), ts = keepVertical ? 0 : Math.sin(Math.PI / 180);
      const Ry = [[c, 0, s], [0, 1, 0], [-s, 0, c]], Rx = [[1, 0, 0], [0, tc, -ts], [0, ts, tc]];
      const R = Ry.map((row) => [0, 1, 2].map((j) => row[0] * Rx[0][j] + row[1] * Rx[1][j] + row[2] * Rx[2][j]));
      const t = [0, 1, 2].map((i) => k[i] + move[i] - (R[i][0] * k[0] + R[i][1] * k[1] + R[i][2] * k[2]));
      const P = [R[0][0], R[1][0], R[2][0], 0, R[0][1], R[1][1], R[2][1], 0, R[0][2], R[1][2], R[2][2], 0, t[0], t[1], t[2], 1];
      const mul = (A, B) => { const o = new Array(16).fill(0); for (let cc = 0; cc < 4; cc++) for (let rr = 0; rr < 4; rr++) for (let q = 0; q < 4; q++) o[cc * 4 + rr] += A[q * 4 + rr] * B[cc * 4 + q]; return o; };
      pc.settings.keepVertical = keepVertical;
      pc.setMatrix(mul(P, TRUE), 'perturbed');
      const e0 = window.__t.err(pc.matrix, k);
      const res = await pc.refine();
      const e1 = window.__t.err(pc.matrix, k);
      pc.settings.keepVertical = true;
      return { e0, e1, it: res.iterations, rms: [res.before.rms, res.after.rms], inl: res.after.inlierFraction, reverted: res.reverted, ms: pc.stats.icp.ms };
    }, { TRUE, yaw, move, keepVertical });
    console.log(`ICP from ${label}: start ${r.e0.rotationDeg.toFixed(2)} deg / ${(r.e0.translation * 1000).toFixed(0)} mm -> ${r.e1.rotationDeg.toFixed(4)} deg / ${(r.e1.translation * 1000).toFixed(2)} mm, ${r.it} iterations, RMS ${(r.rms[0] * 100).toFixed(2)} -> ${(r.rms[1] * 100).toFixed(2)} cm, inliers ${(r.inl * 100).toFixed(0)}%, ${(r.ms / 1000).toFixed(1)} s`);
    check(`ICP from ${label} converges`, r.e1.translation < 0.01 && r.e1.rotationDeg < 0.1 && !r.reverted);
  }

  // params round trip of the matrix through the document
  const pr = await page.evaluate(() => {
    const doc = window.__xrayParams?.collect?.();
    return doc ? { has: Array.isArray(doc.sections?.pointcloud?.matrix ?? doc.pointcloud?.matrix), keys: Object.keys(doc.sections?.pointcloud ?? doc.pointcloud ?? {}) } : null;
  });
  if (pr) check('params document has the registration matrix', pr.has, pr.keys.join(','));

  check('no console errors', errors.length === 0, errors.slice(0, 3).join(' | '));
} catch (e) {
  failed = true;
  console.error(e);
} finally {
  await browser?.close();
  vite.kill('SIGTERM');
}
process.exit(failed ? 1 : 0);
