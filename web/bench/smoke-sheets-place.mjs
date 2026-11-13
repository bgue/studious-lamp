// Headless check for placing PDF sheets in the model (src/sheets placement, stage 2) on /?model=fzk-haus:
//   - a sheet is made from FZK-Haus's own ground-floor plan cut (the outlines of what a plane 1.2 m above the storey slices), drawn with
//     a known scale (1:100) and a 20 degree turn, so the overlay check means something; it opens as an unplaced sheet ("Not placed")
//     that works as in stage 1 (a sketch on it stays on the sheet, no attachment, nothing in 3D);
//   - "Place in model..." opens the split view: the sheet and the plan of the storey; two real clicks on the sheet and two on the model
//     (snapping to wall corners) give a transform close to the known one, shown at once as the model overlay on the sheet;
//   - Accept: the sheet is placed; the model overlay lines up with the drawing (the overlay pixels lie on dark pixels of the page); a
//     third point gives a least-squares fit with a misfit in millimetres; "Use drawing scale" gives the same transform from one pair;
//   - a cloud drawn over a wall on the sheet is attached to that wall's GlobalId; a text on a wall is a `point`; a rectangle over
//     nothing is a `region`;
//   - Show in 3D: a quad at the level; picks ignore it; the sketches are drawn on it; the 3D · Plan · Section switch works for the
//     sketch;
//   - raised as an issue the viewpoint has the wall's GlobalId as a component and a camera, the bcfzip has Plan and Section views;
//   - geo auto placement (the model gets an IfcMapConversion in the page: FZK-Haus has none) from bench/fixtures/geo-sheet.pdf, and the
//     refusal when the CRS differ;
//   - the placement survives a reload (IndexedDB) and is in no URL or localStorage;
//   - the phone width (360 px): the two sides one after the other, in steps; no console errors.
// Screenshots: bench/sheets-place.png, sheets-overlay.png, sheets-3d.png, sheets-place-phone.png.
// Usage: SMOKE_PORT=5715 node bench/smoke-sheets-place.mjs
import { spawn } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const port = Number(process.env.SMOKE_PORT ?? 5715);
const GEO_FIXTURE = resolve(here, 'fixtures/geo-sheet.pdf');

function loadPlaywright() {
  const candidates = [process.env.PLAYWRIGHT_MODULE, resolve(root, 'node_modules/playwright'), '/opt/node-tools/node_modules/playwright', '/opt/node22/lib/node_modules/playwright', 'playwright'].filter(Boolean);
  for (const c of candidates) {
    try { return createRequire(import.meta.url)(c); } catch { /* next */ }
  }
  throw new Error('playwright not found; set PLAYWRIGHT_MODULE');
}
const { chromium } = loadPlaywright();
const PdfLib = createRequire(import.meta.url)(resolve(root, 'node_modules/pdf-lib'));

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

// The known placement of the generated sheet: metres per point at 1:100, turned 20 degrees counter-clockwise, sheet centre on the plan centre.
const MPP = (25.4 / 72 / 1000) * 100;
const THETA = (20 * Math.PI) / 180;
const PW = 842;
const PH = 595;

const errors = [];
let browser;
try {
  await waitForServer();
  browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1500, height: 820 } });
  const page = await ctx.newPage();
  page.setDefaultTimeout(Number(process.env.SMOKE_TIMEOUT ?? 120000));
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', (e) => errors.push(`[pageerror] ${e.message}`));
  const toB64 = (arr) => Buffer.from(arr).toString('base64');
  const bytesOf = async (fn, ...args) => Buffer.from(await page.evaluate(async ([src, a]) => {
    const u8 = await (0, eval)(`(${src})`)(...a);
    let s = '';
    for (let i = 0; i < u8.length; i += 8192) s += String.fromCharCode(...u8.subarray(i, i + 8192));
    return btoa(s);
  }, [fn.toString(), args]), 'base64');

  await page.goto(`http://127.0.0.1:${port}/?model=fzk-haus`);
  await page.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: 240000 });
  const err0 = await page.evaluate('window.__xrayError');
  if (err0) throw new Error(`startup failed: ${err0}`);
  await page.waitForTimeout(500);

  // ------------------------------------------------------------------ the model: levels and the plan cut
  const levels = await page.evaluate(() => window.__xraySheets.levels());
  check('the model has storeys to choose from (FZK-Haus: Erdgeschoss, Dachgeschoss)', levels.length === 2 && levels[0].elevation === 0 && levels[1].elevation > 2, JSON.stringify(levels));
  const polys = await page.evaluate((z) => window.__xraySheets.cutPolys(z), levels[0].elevation);
  const cutSummary = await page.evaluate((z) => window.__xraySheets.cut(z), levels[0].elevation);
  check('the plan cut of the ground floor is vector outlines of walls', polys.length >= 8 && polys.some((e) => /Wall/.test(e.cls)) && cutSummary.polylines >= polys.length, `${polys.length} elements, ${cutSummary.polylines} outlines, z=${cutSummary.z}`);
  let bx0 = Infinity, by0 = Infinity, bx1 = -Infinity, by1 = -Infinity;
  for (const e of polys) { bx0 = Math.min(bx0, e.box[0]); by0 = Math.min(by0, e.box[1]); bx1 = Math.max(bx1, e.box[2]); by1 = Math.max(by1, e.box[3]); }
  const C = [(bx0 + bx1) / 2, (by0 + by1) / 2];
  // truth: model = s R(theta) user + t, the page centre on the plan centre
  const cs = MPP * Math.cos(THETA), sn = MPP * Math.sin(THETA);
  const truth = { scale: MPP, rotation: THETA, tx: C[0] - (cs * PW / 2 - sn * PH / 2), ty: C[1] - (sn * PW / 2 + cs * PH / 2) };
  const toModel = ([x, y]) => [cs * x - sn * y + truth.tx, sn * x + cs * y + truth.ty];
  const toUser = ([X, Y]) => { const dx = X - truth.tx, dy = Y - truth.ty; return [(cs * dx + sn * dy) / (MPP * MPP), (-sn * dx + cs * dy) / (MPP * MPP)]; };

  // ------------------------------------------------------------------ the sheet: the plan cut drawn on a page at the known placement
  const doc = await PdfLib.PDFDocument.create();
  const font = await doc.embedFont(PdfLib.StandardFonts.Helvetica);
  const pg = doc.addPage([PW, PH]);
  const ink = PdfLib.rgb(0.08, 0.08, 0.1);
  const line = (a, b, t) => pg.drawLine({ start: { x: a[0], y: a[1] }, end: { x: b[0], y: b[1] }, thickness: t, color: ink });
  for (const e of polys) {
    for (const q of e.polys) {
      const n = q.pts.length / 2;
      for (let i = 0; i < n - (q.closed ? 0 : 1); i++) {
        const j = (i + 1) % n;
        line(toUser([q.pts[i * 2], q.pts[i * 2 + 1]]), toUser([q.pts[j * 2], q.pts[j * 2 + 1]]), 1.1);
      }
    }
  }
  pg.drawRectangle({ x: 20, y: 20, width: PW - 40, height: PH - 40, borderWidth: 1, borderColor: ink });
  pg.drawText('FZK-Haus, Erdgeschoss, 1:100 (from the model plan cut)', { x: 30, y: 30, size: 10, font, color: ink });
  const sheetBytes = Buffer.from(await doc.save({ useObjectStreams: false }));

  await page.evaluate(() => window.__xrayIssues.open('sheets'));
  await page.setInputFiles('input[data-sheets=open]', { name: 'fzk-erdgeschoss.pdf', mimeType: 'application/pdf', buffer: sheetBytes });
  await page.waitForFunction(() => window.__xraySheets.docs().length === 1 && /opened/.test(window.__xraySheets.status), null, { timeout: 90000 });
  const sheet = (await page.evaluate(() => window.__xraySheets.sheets()))[0];
  const sheetId = sheet.id;
  check('the new sheet is "Not placed" and has no geo data', sheet.placement === undefined && !sheet.geo);
  await page.waitForSelector(`#issues-panel [data-sheet-place="${sheetId}"]`);
  const status0 = await page.textContent(`#issues-panel [data-placement-status="${sheetId}"]`);
  check('the Sheets segment says "Not placed" and offers Place in model...', status0 === 'Not placed' && !!(await page.$(`#issues-panel [data-sheet-place="${sheetId}"] [data-act=place]`)));
  const noOthers = await page.evaluate((id) => ({ show: !!document.querySelector(`#issues-panel [data-sheet-place="${id}"] [data-act=show3d]`), rm: !!document.querySelector(`#issues-panel [data-sheet-place="${id}"] [data-act=remove-placement]`) }), sheetId);
  check('an unplaced sheet offers no Show in 3D, overlay or Remove placement', !noOthers.show && !noOthers.rm);

  // an unplaced sheet works exactly as before: a sketch stays on the sheet, with no attachment and nothing in 3D
  await page.click(`#issues-panel [data-sheet="${sheetId}"]`);
  await page.waitForSelector('#sheet-view.on');
  await page.waitForFunction(() => window.__xraySheets.view()?.renders.base >= 1, null, { timeout: 60000 });
  const plain = await page.evaluate((id) => { const s = window.__xraySheets.newSketch(id, 'Plain'); const m = window.__xraySheets.add(s.id, { kind: 'rect', points: [[300, 300], [380, 360]] }); return { set: s.id, attach: m.attach?.kind, status: window.__xraySheets.view().overlayDrawn }; }, sheetId);
  check('on an unplaced sheet a sketch is sheet-only: view-locked, no attachment', plain.attach === 'none');
  check('the viewer shows the stage 1 controls: no overlay or misfit on an unplaced sheet', await page.evaluate(() => { const q = (s) => document.querySelector(`#sheet-view ${s}`); return q('[data-act=overlay]').hidden && q('[data-sv=misfit]').hidden && q('[data-sv=placement]').textContent.startsWith('Not placed'); }));
  await page.evaluate((id) => window.__xraySheets.controller.markup.deleteSet(id), plain.set);

  // ------------------------------------------------------------------ Place in model...: two clicks on the sheet, two on the model
  await page.click('#sheet-view [data-act=place]');
  await page.waitForSelector('#sheet-place.on');
  await page.waitForFunction(() => { const s = window.__xraySheets.place.state(); return s && s.open && s.elements > 5; }, null, { timeout: 60000 });
  await page.waitForTimeout(700);
  const ps0 = await page.evaluate(() => window.__xraySheets.place.state());
  check('the placement view has the storey list, the sheet on one side and the plan cut on the other', ps0.level === 'Erdgeschoss' && ps0.elements >= 8 && (await page.evaluate(() => [...document.querySelectorAll('#sheet-place [data-pv=level] option')].length)) === 2 && /Click point A on the sheet/.test(ps0.hint), JSON.stringify([ps0.level, ps0.elements, ps0.hint]));
  const geom = await page.evaluate(() => { const r = (s) => { const b = document.querySelector(s).getBoundingClientRect(); return { x: b.left, w: b.width, h: b.height }; }; return { s: r('#sheet-place [data-pv=sheet-stage]'), m: r('#sheet-place [data-pv=model-stage]') }; });
  check('both sides are shown at once on a wide screen', geom.s.w > 300 && geom.m.w > 300 && Math.abs(geom.s.x + geom.s.w - geom.m.x) < 4, JSON.stringify(geom));
  // two far corners of the plan, picked at the wall corners (the model click snaps to them)
  const corners = [];
  for (const e of polys) for (const q of e.polys) for (let i = 0; i < q.pts.length; i += 2) corners.push([q.pts[i], q.pts[i + 1]]);
  const A = corners.reduce((b, p) => (p[0] + p[1] < b[0] + b[1] ? p : b));
  const B = corners.reduce((b, p) => (p[0] + p[1] > b[0] + b[1] ? p : b));
  const clickPair = async (M, off = [0, 0]) => {
    const U = toUser(M);
    const sp = await page.evaluate(([x, y]) => window.__xraySheets.place.clientOfSheet(x, y), U);
    await page.mouse.click(sp[0] + off[0], sp[1] + off[1]);
    const mp = await page.evaluate(([x, y]) => window.__xraySheets.place.clientOfModel(x, y), M);
    await page.mouse.move(mp[0] + 3, mp[1] + 2); // a little off the corner: the snap finds it
    await page.mouse.click(mp[0] + 3, mp[1] + 2);
  };
  await clickPair(A);
  const afterA = await page.evaluate(() => window.__xraySheets.place.state());
  check('picking A on the sheet and A in the model records the pair, and asks for B', afterA.pairs.length === 2 || (afterA.pairs.length === 1 && afterA.pairs[0].sheet && afterA.pairs[0].model), JSON.stringify(afterA.pairs));
  check('the model pick snapped to the wall corner', Math.hypot(afterA.pairs[0].model[0] - A[0], afterA.pairs[0].model[1] - A[1]) < 1e-3, JSON.stringify([afterA.pairs[0].model, A]));
  check('Accept waits for two pairs', await page.evaluate(() => document.querySelector('#sheet-place [data-act=accept]').disabled));
  await clickPair(B);
  await page.waitForTimeout(300);
  const ps2 = await page.evaluate(() => window.__xraySheets.place.state());
  const dRot = Math.abs(((ps2.transform.rotation - THETA + Math.PI * 3) % (Math.PI * 2)) - Math.PI);
  const tm = [applyT(ps2.transform, [PW / 2, PH / 2]), applyT(truth, [PW / 2, PH / 2])];
  function applyT(t, p) { const c = t.scale * Math.cos(t.rotation), s = t.scale * Math.sin(t.rotation); return [c * p[0] - s * p[1] + t.tx, s * p[0] + c * p[1] + t.ty]; }
  check('two pairs give a transform close to the known one (scale 1%, rotation 1 degree, centre 0.15 m)', Math.abs(ps2.transform.scale / MPP - 1) < 0.01 && dRot < 0.018 && Math.hypot(tm[0][0] - tm[1][0], tm[0][1] - tm[1][1]) < 0.15, `${(ps2.transform.scale / MPP).toFixed(4)} ${(dRot * 57.3).toFixed(2)}deg ${Math.hypot(tm[0][0] - tm[1][0], tm[0][1] - tm[1][1]).toFixed(3)} m`);
  check('the result shows scale, rotation and that two points are exact', /Scale 1:100/.test(ps2.result) && /2 points/.test(ps2.result), ps2.result);
  // the overlay preview: its pixels lie on dark pixels of the page
  const align = (sel) => page.evaluate((s) => {
    const base = document.querySelector(s.base);
    const ov = document.querySelector(s.ov);
    const st = window.__xraySheets.place.state();
    const view = s.placeView ? st.sheetView : window.__xraySheets.view();
    const bs = s.placeView ? 1 : view.baseScale;
    const dpr = ov.width / parseFloat(ov.style.width);
    const og = ov.getContext('2d').getImageData(0, 0, ov.width, ov.height).data;
    const bg = base.getContext('2d').getImageData(0, 0, base.width, base.height).data;
    const pageScale = base.width / s.pageW;
    let n = 0, on = 0;
    for (let y = 0; y < ov.height; y += 2) for (let x = 0; x < ov.width; x += 2) {
      if (og[(y * ov.width + x) * 4 + 3] < 60) continue;
      n++;
      const cx = x / dpr, cy = y / dpr;
      const px = ((cx - view.tx) / view.scale) * pageScale, py = ((cy - view.ty) / view.scale) * pageScale;
      let hit = false;
      const r = Math.max(2, Math.round((3 / view.scale) * pageScale));
      for (let dy = -r; dy <= r && !hit; dy++) for (let dx = -r; dx <= r && !hit; dx++) {
        const bx = Math.round(px + dx), by = Math.round(py + dy);
        if (bx < 0 || by < 0 || bx >= base.width || by >= base.height) continue;
        if (bg[(by * base.width + bx) * 4] < 120) hit = true;
      }
      if (hit) on++;
    }
    void bs;
    return { n, on, share: n ? on / n : 0 };
  }, sel);
  const a1 = await align({ base: '#sheet-place canvas[data-pv=page]', ov: '#sheet-place canvas[data-pv=preview]', placeView: true, pageW: PW });
  check('the preview overlay in the placement view lines up with the drawing', a1.n > 300 && a1.share > 0.6, JSON.stringify(a1));
  await page.screenshot({ path: resolve(here, 'sheets-place.png') });

  // Redo clears the points; the same two come back; Cancel closes without placing
  await page.click('#sheet-place [data-act=redo]');
  check('Redo starts the points again', (await page.evaluate(() => window.__xraySheets.place.state())).pairs.every((p) => !p.sheet && !p.model));
  await page.click('#sheet-place [data-act=cancel]');
  await page.waitForFunction(() => !document.querySelector('#sheet-place.on'));
  check('Cancel closes the view and leaves the sheet unplaced', (await page.evaluate((id) => window.__xraySheets.placement(id), sheetId)) === null);
  await page.click('#sheet-view [data-act=place]');
  await page.waitForSelector('#sheet-place.on');
  await page.waitForTimeout(500);
  await clickPair(A);
  await clickPair(B);
  await page.click('#sheet-place [data-act=accept]');
  await page.waitForFunction(() => !document.querySelector('#sheet-place.on') && window.__xraySheets.openSheet !== null);
  const placed = await page.evaluate((id) => window.__xraySheets.placement(id), sheetId);
  check('Accept places the sheet: manual, at the level of the storey, a plan placement with its pairs', placed && placed.kind === 'manual' && placed.level.elevation === 0 && placed.level.name === 'Erdgeschoss' && placed.pairs.length === 2 && placed.residual === undefined && /2 points/.test(placed.source), JSON.stringify(placed)?.slice(0, 200));
  const tm2 = [applyT(placed.transform, [PW / 2, PH / 2]), applyT(truth, [PW / 2, PH / 2])];
  check('the placement is close to the known transform', Math.abs(placed.transform.scale / MPP - 1) < 0.01 && Math.hypot(tm2[0][0] - tm2[1][0], tm2[0][1] - tm2[1][1]) < 0.15);
  const status1 = await page.textContent(`#sheet-view [data-sv=placement]`);
  check('the viewer says the sheet is placed (manual, 2 points)', /^Placed \(manual, 2 points\)/.test(status1), status1);

  // ------------------------------------------------------------------ the model overlay on the sheet
  await page.waitForTimeout(500);
  const ov1 = await page.evaluate(() => window.__xraySheets.overlayState());
  check('after Accept the model overlay is on and has drawn outlines', ov1.on && ov1.drawn >= 8, JSON.stringify(ov1));
  const a2 = await align({ base: '#sheet-view canvas.sv-base', ov: '#sheet-view canvas.sv-ovl', placeView: false, pageW: PW });
  check('the model overlay lines up with the drawing on the sheet', a2.n > 300 && a2.share > 0.6, JSON.stringify(a2));
  // a pixel region of the screenshot is non-empty (overlay colour #d6336c over the page)
  await page.mouse.move(760, 520);
  await page.waitForTimeout(400);
  const shot = await page.screenshot({ path: resolve(here, 'sheets-overlay.png') });
  const reg = await page.evaluate(async (b64) => {
    const img = new Image();
    img.src = `data:image/png;base64,${b64}`;
    await img.decode();
    const st = document.querySelector('#sheet-view [data-sv=stage]').getBoundingClientRect();
    const cv = document.createElement('canvas');
    cv.width = Math.round(st.width); cv.height = Math.round(st.height);
    const g = cv.getContext('2d');
    g.drawImage(img, st.left, st.top, st.width, st.height, 0, 0, st.width, st.height);
    const d = g.getImageData(0, 0, cv.width, cv.height).data;
    let pink = 0;
    for (let i = 0; i < d.length; i += 4) if (d[i] > 170 && d[i + 1] < 130 && d[i + 2] > 60 && d[i + 2] < 170) pink++;
    return pink;
  }, shot.toString('base64'));
  check('the screenshot region of the overlay is not empty', reg > 150, `${reg} overlay pixels`);
  // the toggle and the opacity slider
  await page.click('#sheet-view [data-act=overlay]');
  await page.waitForTimeout(200);
  check('the Model overlay toggle switches it off', (await page.evaluate(() => window.__xraySheets.overlayState())).drawn === 0);
  await page.click('#sheet-view [data-act=overlay]');
  await page.fill('#sheet-view [data-sv=opacity]', '30');
  await page.waitForTimeout(200);
  check('the opacity slider sets the opacity', Math.abs((await page.evaluate(() => window.__xraySheets.overlayState())).opacity - 0.3) < 0.01);
  check('there is no misfit readout with two pairs', await page.evaluate(() => document.querySelector('#sheet-view [data-sv=misfit]').hidden));

  // ------------------------------------------------------------------ a third point: least squares and the misfit in mm
  await page.click('#sheet-view [data-act=place]');
  await page.waitForSelector('#sheet-place.on');
  await page.waitForTimeout(500);
  const prefilled = await page.evaluate(() => window.__xraySheets.place.state());
  check('placing again starts from the points of the placement', prefilled.pairs.filter((p) => p.sheet && p.model).length === 2);
  await page.click('#sheet-place [data-act=add]');
  // the third corner: the one furthest from the line A-B
  const Cc = corners.reduce((b, p) => { const d = Math.abs((B[0] - A[0]) * (A[1] - p[1]) - (A[0] - p[0]) * (B[1] - A[1])); return d > b.d ? { p, d } : b; }, { p: corners[0], d: -1 }).p;
  await clickPair(Cc, [1, 1]); // a clumsy click on the sheet: a pixel is about 7 cm of the model here
  await page.waitForTimeout(300);
  const ps3 = await page.evaluate(() => window.__xraySheets.place.state());
  check('three pairs are fitted by least squares and show the misfit in mm (a clumsy third click leaves a few cm)', ps3.residual !== null && ps3.residual > 0.004 && ps3.residual < 0.12 && /misfit ±[\d.]+ mm/.test(ps3.result), ps3.result);
  await page.click('#sheet-place [data-act=accept]');
  await page.waitForFunction(() => !document.querySelector('#sheet-place.on'));
  await page.waitForTimeout(400);
  const mis = await page.evaluate(() => { const e = document.querySelector('#sheet-view [data-sv=misfit]'); return { hidden: e.hidden, t: e.textContent }; });
  check('the viewer shows the Misfit readout with three or more pairs', !mis.hidden && /^Misfit ±[\d.]+ mm$/.test(mis.t), JSON.stringify(mis));
  check('the status says Placed (manual, ±N mm)', /^Placed \(manual, ±[\d.]+ mm\)/.test(await page.textContent('#sheet-view [data-sv=placement]')));
  // Use drawing scale: one pair, the scale and the rotation give the same transform
  await page.click('#sheet-view [data-act=place]');
  await page.waitForSelector('#sheet-place.on');
  await page.waitForTimeout(400);
  await page.click('#sheet-place [data-act=mode-scale]');
  await page.click('#sheet-place [data-act=redo]');
  await page.fill('#sheet-place [data-pv=scale]', '100');
  await page.fill('#sheet-place [data-pv=rotation]', '20');
  await clickPair(A);
  await page.waitForTimeout(300);
  const psS = await page.evaluate(() => window.__xraySheets.place.state());
  const tmS = [applyT(psS.transform, [PW / 2, PH / 2]), applyT(truth, [PW / 2, PH / 2])];
  check('"Use drawing scale" (1:100, 20 degrees, one pair) gives the known transform', psS.mode === 'scale' && Math.abs(psS.transform.scale / MPP - 1) < 1e-9 && Math.abs(psS.transform.rotation - THETA) < 1e-9 && Math.hypot(tmS[0][0] - tmS[1][0], tmS[0][1] - tmS[1][1]) < 0.15, `${psS.result}`);
  await page.click('#sheet-place [data-act=cancel]');
  await page.waitForFunction(() => !document.querySelector('#sheet-place.on'));

  // ------------------------------------------------------------------ sketches attach to the elements under them
  // a wall that nothing else comes near: a cloud over the middle of it
  const walls = polys.filter((e) => /Wall/.test(e.cls));
  const near = (a, b, m) => !(a[2] + m < b[0] || b[2] + m < a[0] || a[3] + m < b[1] || b[3] + m < a[1]);
  let target = null;
  for (const w of walls) {
    const L = Math.max(w.box[2] - w.box[0], w.box[3] - w.box[1]);
    if (L < 3) continue;
    const c = [(w.box[0] + w.box[2]) / 2, (w.box[1] + w.box[3]) / 2];
    const rect = [c[0] - 0.5, c[1] - 0.5, c[0] + 0.5, c[1] + 0.5];
    if (polys.some((o) => o.guid !== w.guid && near(rect, o.box, 0.3))) continue;
    target = { guid: w.guid, c };
    break;
  }
  check('FZK-Haus has a wall to put a cloud on', !!target);
  await page.evaluate((id) => { const mk = window.__xraySheets.controller.markup; mk.setEditing(false); }, sheetId);
  await page.click('#sheet-view [data-act=draw]');
  await page.waitForSelector('#sheet-float', { state: 'visible' });
  const toPx = async (ux, uy) => page.evaluate(([x, y]) => { const p = window.__xraySheets.toStage(x, y); const r = document.querySelector('#sheet-view [data-sv=stage]').getBoundingClientRect(); return [r.left + p[0], r.top + p[1]]; }, [ux, uy]);
  const drag = async (a, b) => {
    await page.mouse.move(a[0], a[1]);
    await page.mouse.down();
    for (let i = 1; i <= 4; i++) await page.mouse.move(a[0] + ((b[0] - a[0]) * i) / 4, a[1] + ((b[1] - a[1]) * i) / 4);
    await page.mouse.up();
  };
  const wu = toUser(target.c);
  const hx = 0.45 / MPP, hy = 0.2 / MPP;
  await page.click('#sheet-float [data-tool-id=cloud]');
  await drag(await toPx(wu[0] - hx, wu[1] - hy), await toPx(wu[0] + hx, wu[1] + hy));
  const setNow = await page.evaluate((id) => window.__xraySheets.sketches(id).find((s) => !s.readonly), sheetId);
  const cloud = setNow.markups.find((m) => m.kind === 'cloud');
  check('a cloud drawn over a wall on the sheet is attached to that wall (its GlobalId)', cloud?.attach?.kind === 'elements' && JSON.stringify(cloud.attach.guids) === JSON.stringify([target.guid]) && cloud.attach.surface.pts.length >= 4, JSON.stringify({ kind: cloud?.attach?.kind, guids: cloud?.attach?.guids, want: target.guid }));
  check('the shape itself is still in PDF points of the sheet', cloud.shape.points.length === 2 && Math.abs(cloud.shape.points[0][0] - (wu[0] - hx)) < 4);
  await page.click('#sheet-float [data-tool-id=text]');
  await page.fill('#sheet-float [aria-label="Text for the next markup"]', 'Wall to be rendered');
  const tp = await toPx(wu[0], wu[1]);
  await page.mouse.click(tp[0], tp[1]);
  await page.click('#sheet-float [data-tool-id=rect]');
  const far = toUser([bx1 + 1.6, C[1]]);
  await drag(await toPx(far[0] - 12, far[1] - 8), await toPx(far[0] + 12, far[1] + 8));
  const setAfter = await page.evaluate((id) => window.__xraySheets.sketches(id).find((s) => !s.readonly), sheetId);
  const text = setAfter.markups.find((m) => m.kind === 'text');
  const rect = setAfter.markups.find((m) => m.kind === 'rect');
  check('a text placed on a wall is attached to it (a point on that element)', text?.anchor?.kind === 'element' && text.anchor.elementGuid === target.guid, JSON.stringify(text?.anchor));
  check('a rectangle over nothing is a region at the level (bounds of the shape, up to the storey top)', rect?.attach?.kind === 'region' && rect.attach.region.min[2] === 0 && Math.abs(rect.attach.region.max[2] - levels[1].elevation) < 1e-6, JSON.stringify(rect?.attach));
  await page.click('#sheet-float [data-tool-id=select]');
  // moving a shape attaches it again where it lands
  const cloudCentre = await toPx(wu[0], wu[1]);
  const empty = toUser([bx1 + 1.6, by1 - 1]);
  const dest = await toPx(empty[0], empty[1]);
  await drag(cloudCentre, dest);
  const moved = await page.evaluate((id) => window.__xraySheets.sketches(id).find((s) => !s.readonly).markups.find((m) => m.kind === 'cloud'), sheetId);
  check('moving a shape on the sheet attaches it again where it lands (off the wall: not that wall any more)', moved.attach.kind !== 'elements' || !moved.attach.guids.includes(target.guid), JSON.stringify(moved.attach.kind));
  await page.keyboard.press('Control+z');
  const undone = await page.evaluate((id) => window.__xraySheets.sketches(id).find((s) => !s.readonly).markups.find((m) => m.kind === 'cloud'), sheetId);
  check('undo puts the shape and its attachment back', undone.attach.kind === 'elements' && undone.attach.guids[0] === target.guid, JSON.stringify(undone.attach.guids));
  await page.click('#sheet-float [data-act=done]');
  const setId = setAfter.id;

  // ------------------------------------------------------------------ Show in 3D: the quad, picks, the sketches on it
  await page.click('#sheet-view [data-act=back]');
  await page.waitForFunction(() => !document.querySelector('#sheet-view.on'));
  const grid = [];
  for (let i = 1; i <= 5; i++) for (let j = 1; j <= 5; j++) grid.push([-0.8 + i * 0.27, -0.8 + j * 0.27]);
  const picks = () => page.evaluate((g) => g.map(([x, y]) => window.__xray.app.renderer.pick(x, y)), grid);
  const picksBefore = await picks();
  await page.evaluate(() => window.__xrayIssues.open('sheets'));
  await page.waitForSelector(`#issues-panel [data-sheet-place="${sheetId}"] [data-act=show3d]`);
  await page.click(`#issues-panel [data-sheet-place="${sheetId}"] [data-act=show3d]`);
  await page.waitForFunction((id) => window.__xraySheets.quad(id).exists, sheetId, { timeout: 60000 });
  const q = await page.evaluate((id) => window.__xraySheets.quad(id), sheetId);
  check('Show in 3D makes a quad in the scene at the elevation of the level', q.exists && q.inScene && Math.abs(q.elevation - 0.03) < 1e-6 && q.corners.length === 4, JSON.stringify([q.elevation, q.opacity]));
  const nowP = await page.evaluate((id) => window.__xraySheets.placement(id), sheetId);
  check('the quad has the size of the page at 1:100 (about 29.7 by 21 m)', (() => { const d = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]); return Math.abs(d(q.corners[0], q.corners[1]) - PW * nowP.transform.scale) < 0.02 && Math.abs(d(q.corners[1], q.corners[2]) - PH * nowP.transform.scale) < 0.02 && Math.abs(nowP.transform.scale / MPP - 1) < 0.03; })(), JSON.stringify(q.corners));
  check('the quad takes no raycast', q.pickable === false);
  const picksAfter = await picks();
  check('picks ignore the quad (the same element under every pick point with and without it)', JSON.stringify(picksBefore) === JSON.stringify(picksAfter) && picksAfter.some((p) => p !== null), `${picksAfter.filter((p) => p !== null).length} hits`);
  await page.setViewportSize({ width: 1500, height: 821 });
  await page.evaluate(() => window.__xraySheets.setQuadOpacity(0.55));
  check('the global opacity control sets the quad opacity', Math.abs((await page.evaluate((id) => window.__xraySheets.quad(id).opacity, sheetId)) - 0.55) < 1e-6);
  // 3D view of the sketch: the switch frames what it is attached to
  const tied = await page.evaluate((id) => window.__xrayIssues.controller.views.tied(window.__xraySheets.controller.markup.get(id)), setId);
  check('the sketch on the placed sheet has the 3D · Plan · Section switch', tied === true);
  await page.evaluate((id) => window.__xrayIssues.controller.views.apply(id, '3d'), setId);
  await page.waitForTimeout(900);
  const drawn = await page.evaluate(() => window.__xraySheets.scene3d());
  check('the sketches are drawn in 3D on the quad, with the attached-markup layout', drawn.drawn >= 3, JSON.stringify(drawn));
  check('the quad texture was drawn once at least', drawn.renders.base >= 1);
  // an oblique view from outside: the quad lies on the ground floor around the house, the sketches on it
  await page.evaluate(() => { const r = window.__xray.app.renderer; r.camera.position.set(16, 17, 24); r.controls.target.set(2, 0, -2); r.controls.update(); r.markDirty(); });
  await page.waitForTimeout(700);
  await page.screenshot({ path: resolve(here, 'sheets-3d.png') });
  await page.evaluate(() => window.__xraySheets.show3d(window.__xraySheets.sheets()[0].id, false));
  await page.waitForTimeout(200);
  check('hiding the sheet removes the quad', (await page.evaluate((id) => window.__xraySheets.quad(id).exists, sheetId)) === false);

  // ------------------------------------------------------------------ raise as an issue: a real 3D viewpoint
  const vpPreview = await page.evaluate((id) => window.__xraySheets.viewpointOf(id), setId);
  check('the viewpoint would have the wall as a component and a camera that frames it', vpPreview?.components.includes(target.guid) && vpPreview.hasCamera, JSON.stringify(vpPreview));
  const topicGuid = await page.evaluate((id) => window.__xraySheets.raise(id), setId);
  const topic = await page.evaluate((g) => { const t = window.__xrayBcf.topics.find((x) => x.guid === g); const v = t.viewpoints[0]; return { n: t.viewpoints.length, sel: v.data?.selection.map((s) => s.ifcGuid), cam: v.data?.camera ? { kind: v.data.camera.kind, fov: v.data.camera.fov } : null, snap: !!v.snapshot, docs: t.documentReferences.length, sheet: !!v.sheet, sketch: v.sketchId }; }, topicGuid);
  check('the issue has the DocumentReference, the sheet snapshot and a 3D viewpoint with the wall as a component', topic.docs === 1 && topic.snap && topic.sheet && topic.sel?.includes(target.guid) && topic.cam?.kind === 'perspective', JSON.stringify(topic));
  const sw = await page.evaluate((id) => { const v = window.__xrayIssues.controller.views; const s = window.__xraySheets.controller.markup.get(id); const out = {}; for (const m of ['plan', 'section', '3d']) { out[m] = v.apply(id, m); out[`${m}Mode`] = v.mode(s); } return out; }, setId);
  check('the 3D · Plan · Section switch works for it (Plan, Section and back to 3D)', sw.plan && sw.planMode === 'plan' && sw.section && sw.sectionMode === 'section' && sw['3d'] && sw['3dMode'] === '3d', JSON.stringify(sw));
  const zipInfo = await page.evaluate(async () => {
    const bytes = await window.__xrayBcf.exportZip('3.0');
    const proj = await (await import('/src/bcf/parse.ts')).parseBcf(bytes);
    const t = proj.topics[0];
    return t.viewpoints.map((v) => ({ derived: v.derived?.kind ?? null, sheet: !!v.sheet, hasData: !!v.data, sel: v.data?.selection.length ?? 0, clip: v.data?.clipping.length ?? 0 }));
  });
  check('the bcfzip has the sheet viewpoint with its camera and the Plan and Section views derived from it', zipInfo.some((v) => v.sheet && v.hasData && v.sel >= 1) && zipInfo.some((v) => v.derived === 'plan' && v.clip >= 1) && zipInfo.some((v) => v.derived === 'section' && v.clip >= 2), JSON.stringify(zipInfo));

  // ------------------------------------------------------------------ re-placing asks first when shapes would move off their elements
  const moveTry = await page.evaluate((id) => {
    const sh = window.__xraySheets.placement(id);
    const p = JSON.parse(JSON.stringify(sh));
    p.transform.tx += 3;
    return window.__xraySheets.setPlacement(id, p);
  }, sheetId);
  check('placing again asks first when shapes would leave their elements (nothing changes until confirmed)', moveTry.ok === false && moveTry.moved >= 1 && (await page.evaluate((id) => window.__xraySheets.sketches(id).find((s) => !s.readonly).markups.find((m) => m.kind === 'cloud').attach.guids[0], sheetId)) === target.guid, JSON.stringify(moveTry));

  // ------------------------------------------------------------------ geo-PDF: automatic placement and the refusal
  const geoBytes = readFileSync(GEO_FIXTURE);
  const hadMap = await page.evaluate(() => !!window.__xray.app.loaded.model.mapConversion);
  check('FZK-Haus carries no IfcMapConversion (a unit test reads one from an IFC; the page is given one here)', hadMap === false);
  // a model with no map conversion: the geo-PDF is found, not placed, and says why
  await page.setInputFiles('input[data-sheets=open]', { name: 'geo-sheet.pdf', mimeType: 'application/pdf', buffer: geoBytes });
  await page.waitForFunction(() => window.__xraySheets.docs().length === 2 && /geo-sheet\.pdf opened/.test(window.__xraySheets.status), null, { timeout: 90000 });
  const geoSheet0 = await page.evaluate(() => { const d0 = window.__xraySheets.docs()[0].id; return window.__xraySheets.sheets().find((s) => s.docId !== d0); });
  const g0 = await page.evaluate((id) => window.__xraySheets.geo(id), geoSheet0.id);
  check('a geo-PDF is detected (ISO 32000 geospatial, EPSG:25832); a model without IfcMapConversion cannot place it', /ISO 32000.*EPSG:25832/.test(g0.found ?? '') && /no IfcMapConversion/.test(g0.note ?? '') && !geoSheet0.placement, JSON.stringify(g0));
  await page.evaluate((id) => window.__xraySheets.removeDoc(id), geoSheet0.docId);
  // the model gets the map conversion of that fixture (origin 100 m west and 10 m south of the sheet's lower left corner)
  await page.evaluate(() => { window.__xray.app.loaded.model.mapConversion = { eastings: 500000, northings: 5400000, height: 0, xAxisAbscissa: 1, xAxisOrdinate: 0, scale: 1, crs: { epsg: 25832, name: 'EPSG:25832' } }; });
  await page.setInputFiles('input[data-sheets=open]', { name: 'geo-sheet.pdf', mimeType: 'application/pdf', buffer: geoBytes });
  await page.waitForFunction(() => window.__xraySheets.docs().length === 2 && /geo-sheet\.pdf opened/.test(window.__xraySheets.status), null, { timeout: 90000 });
  const geoSheet = (await page.evaluate(() => window.__xraySheets.sheets())).find((s) => s.geo);
  const gp = await page.evaluate((id) => window.__xraySheets.placement(id), geoSheet.id);
  check('with the same projected CRS in the PDF and the model the sheet is placed by itself and marked geo', gp && gp.kind === 'geo' && /EPSG:25832/.test(gp.source), JSON.stringify(gp)?.slice(0, 160));
  const o = applyT(gp.transform, [0, 0]);
  check('the geo transform puts the sheet corner 100 m east and 10 m north of the model origin', Math.abs(o[0] - 100) < 0.01 && Math.abs(o[1] - 10) < 0.01 && Math.abs(gp.transform.scale / MPP - 1) < 1e-4, JSON.stringify(o));
  await page.evaluate(() => window.__xrayIssues.open('sheets'));
  check('the status says Placed (geo)', (await page.textContent(`#issues-panel [data-placement-status="${geoSheet.id}"]`)) === 'Placed (geo)');
  await page.evaluate((id) => window.__xraySheets.removeDoc(id), geoSheet.docId);
  // the CRS differ: not placed, the detected info is shown, manual placement is offered
  await page.evaluate(() => { window.__xray.app.loaded.model.mapConversion.crs = { epsg: 31467, name: 'EPSG:31467' }; });
  await page.setInputFiles('input[data-sheets=open]', { name: 'geo-sheet.pdf', mimeType: 'application/pdf', buffer: geoBytes });
  await page.waitForFunction(() => window.__xraySheets.docs().length === 2 && /geo-sheet\.pdf opened/.test(window.__xraySheets.status), null, { timeout: 90000 });
  const geoSheet2 = (await page.evaluate(() => window.__xraySheets.sheets())).find((s) => s.geo);
  const g2 = await page.evaluate((id) => window.__xraySheets.geo(id), geoSheet2.id);
  check('a PDF in another CRS than the model is not placed and says so, with what it found', !geoSheet2.placement && /EPSG:25832/.test(g2.note) && /EPSG:31467/.test(g2.note) && /Place it by hand/.test(g2.note), g2.note);
  await page.evaluate(() => window.__xrayIssues.open('sheets'));
  await page.waitForSelector(`#issues-panel [data-sheet-place="${geoSheet2.id}"] [data-geo-note]`);
  check('the panel shows the detected info next to Place in model...', /ISO 32000/.test(await page.evaluate((id) => document.querySelector(`#issues-panel [data-sheet-place="${id}"] [data-geo-note]`).textContent, geoSheet2.id)) || /EPSG:25832/.test(await page.textContent(`#issues-panel [data-sheet-place="${geoSheet2.id}"] [data-geo-note]`)));
  await page.evaluate((id) => window.__xraySheets.removeDoc(id), geoSheet2.docId);
  await page.evaluate(() => { delete window.__xray.app.loaded.model.mapConversion; });

  // ------------------------------------------------------------------ persistence and the leak
  await page.evaluate(() => window.__xraySheets.save());
  await page.waitForTimeout(600);
  const leak = await page.evaluate(() => ({ ls: JSON.stringify(Object.assign({}, localStorage)), ss: JSON.stringify(Object.assign({}, sessionStorage)), url: location.href }));
  check('the placement is in no localStorage, sessionStorage or URL', !/placement|"transform"|elevation|"pairs"/i.test(leak.ls + leak.ss + leak.url), leak.url);
  const shareLink = await page.evaluate(() => { const v = window.__xray.shareUrl?.() ?? ''; return String(v); }).catch(() => '');
  check('a share link carries no placement', !/placement|transform|pairs/i.test(shareLink));
  await page.reload();
  await page.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: 240000 });
  await page.waitForFunction(() => window.__xraySheets.docs().length >= 1, null, { timeout: 30000 });
  const back = await page.evaluate((id) => { const s = window.__xraySheets.sheets().find((x) => x.id === id); const set = window.__xraySheets.sketches(id).find((q) => !q.readonly); return { p: s?.placement && { kind: s.placement.kind, el: s.placement.level.elevation, res: s.placement.residual, tx: s.placement.transform.tx }, cloud: set?.markups.find((m) => m.kind === 'cloud')?.attach?.guids }; }, sheetId);
  check('after a reload the placement and the attachments are back (IndexedDB)', back.p && back.p.kind === 'manual' && back.p.el === 0 && back.p.res !== undefined && JSON.stringify(back.cloud) === JSON.stringify([target.guid]), JSON.stringify(back));

  // ------------------------------------------------------------------ the phone: the two sides one after the other, in steps
  const pctx = await browser.newContext({ viewport: { width: 360, height: 740 }, hasTouch: true, isMobile: true });
  const phone = await pctx.newPage();
  phone.setDefaultTimeout(Number(process.env.SMOKE_TIMEOUT ?? 120000));
  phone.on('console', (m) => { if (m.type() === 'error') errors.push(`[phone] ${m.text()}`); });
  phone.on('pageerror', (e) => errors.push(`[phone pageerror] ${e.message}`));
  await phone.goto(`http://127.0.0.1:${port}/?model=fzk-haus`);
  await phone.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: 240000 });
  await phone.evaluate(() => window.__xrayIssues.open('sheets'));
  await phone.setInputFiles('input[data-sheets=open]', { name: 'fzk-erdgeschoss.pdf', mimeType: 'application/pdf', buffer: sheetBytes });
  await phone.waitForFunction(() => window.__xraySheets.docs().length === 1 && /opened/.test(window.__xraySheets.status), null, { timeout: 90000 });
  await phone.waitForSelector('#issues-sheet.on [data-sheet-place] [data-act=place]');
  const rowFit = await phone.evaluate(() => { const r = document.querySelector('#issues-sheet [data-sheet-place]'); const b = r.getBoundingClientRect(); const v = document.querySelector('#issues-sheet').getBoundingClientRect(); return { inside: b.left >= v.left - 1 && b.right <= v.right + 1, noScroll: r.scrollWidth <= r.clientWidth + 1 }; });
  check('on a 360 px phone the placement row of the Sheets segment fits', rowFit.inside && rowFit.noScroll, JSON.stringify(rowFit));
  await phone.tap('#issues-sheet [data-sheet-place] [data-act=place]');
  await phone.waitForSelector('#sheet-place.on');
  await phone.waitForFunction(() => { const s = window.__xraySheets.place.state(); return s && s.elements > 5; }, null, { timeout: 60000 });
  await phone.waitForTimeout(800);
  const ph1 = await phone.evaluate(() => {
    const vis = (s) => { const e = document.querySelector(s); const r = e.getBoundingClientRect(); return r.width > 20 && r.height > 20 && getComputedStyle(e.closest('.pv-pane')).display !== 'none'; };
    const root = document.querySelector('#sheet-place');
    const bar = document.querySelector('#sheet-place .pv-bar');
    return { sheet: vis('#sheet-place [data-pv=sheet-stage]'), model: vis('#sheet-place [data-pv=model-stage]'), focus: root.dataset.focus, fits: root.getBoundingClientRect().right <= innerWidth + 1 && root.getBoundingClientRect().left >= -1 && bar.scrollWidth <= bar.clientWidth + 1 && [...bar.children].every((c) => { const b = c.getBoundingClientRect(); const rr = root.getBoundingClientRect(); return b.left >= rr.left - 1 && b.right <= rr.right + 1; }), steps: getComputedStyle(document.querySelector('#sheet-place .pv-steps')).display !== 'none', doc: document.documentElement.scrollWidth <= innerWidth + 1, hint: window.__xraySheets.place.state().hint };
  });
  check('on a phone only one side shows, in steps: the sheet first (point A on the sheet)', ph1.sheet && !ph1.model && ph1.focus === 'sheet' && ph1.steps && ph1.fits && ph1.doc && /point A on the sheet/.test(ph1.hint), JSON.stringify(ph1));
  const sp0 = await phone.evaluate(() => window.__xraySheets.place.clientOfSheet(300, 300));
  await phone.touchscreen.tap(sp0[0], sp0[1]);
  await phone.waitForTimeout(300);
  const ph2 = await phone.evaluate(() => {
    const vis = (s) => { const e = document.querySelector(s); const r = e.getBoundingClientRect(); return r.width > 20 && r.height > 20 && getComputedStyle(e.closest('.pv-pane')).display !== 'none'; };
    return { sheet: vis('#sheet-place [data-pv=sheet-stage]'), model: vis('#sheet-place [data-pv=model-stage]'), focus: document.querySelector('#sheet-place').dataset.focus, hint: window.__xraySheets.place.state().hint };
  });
  check('after the sheet point the model side comes up (step 2: the same point in the model)', !ph2.sheet && ph2.model && ph2.focus === 'model' && /Now click the same point A in the model/.test(ph2.hint), JSON.stringify(ph2));
  await phone.screenshot({ path: resolve(here, 'sheets-place-phone.png') });
  await pctx.close();

  check('no console errors', errors.length === 0, errors.slice(0, 5).join(' | '));
} catch (e) {
  failed = true;
  console.error(e);
  console.error(viteLog.slice(-1500));
} finally {
  if (browser) await browser.close();
  vite.kill();
}
process.exit(failed ? 1 : 0);
