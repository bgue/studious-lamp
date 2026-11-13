// Headless check for PDF drawing sheets (src/sheets) on /?model=fzk-haus, with bench/fixtures/sample-sheet.pdf:
//   - nothing PDF-related loads before a PDF is opened (network requests are watched), also not when the Sheets segment is shown;
//   - the PDF opens through the file input as a sheet set (2 pages), listed with thumbnails; the model stays loaded;
//   - the sheet viewer covers the 3D canvas area, "Back to model" returns; the page is drawn and re-drawn sharp after a zoom settles;
//   - the annotations the PDF already has come in as one read-only "Imported annotations" sketch (author and contents shown);
//   - a cloud and a text are drawn with the floating toolbar; pan and zoom keep the shapes on the same PDF points;
//   - Export marked-up PDF: the layer "X-ray markups", real annotations that point at it (read back with pdf-lib in node), the
//     foreign annotations untouched; a second export does not double them; opening the exported PDF gives the markups back
//     editable and the foreign annotations read-only;
//   - Raise as issue: snapshot, DocumentReference to the PDF in the bcfzip (3.0 and 2.1), sheet record in the side file; opening
//     the bcfzip again restores the sketch and its sheet link by the SHA-256 of the PDF;
//   - the phone width (360 px) and no console errors.
// Screenshots: bench/sheets-view.png, sheets-phone.png, sheets-imported.png.
// Usage: SMOKE_PORT=5714 node bench/smoke-sheets.mjs
import { spawn } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const port = Number(process.env.SMOKE_PORT ?? 5714);
const FIXTURE = resolve(here, 'fixtures/sample-sheet.pdf');

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

/** The names in a zip (central directory). */
function zipNames(bytes) {
  const b = Buffer.from(bytes);
  let eocd = -1;
  for (let i = b.length - 22; i >= 0; i--) if (b.readUInt32LE(i) === 0x06054b50) { eocd = i; break; }
  const n = b.readUInt16LE(eocd + 10);
  let p = b.readUInt32LE(eocd + 16);
  const names = [];
  for (let i = 0; i < n; i++) {
    const nl = b.readUInt16LE(p + 28), el = b.readUInt16LE(p + 30), cl = b.readUInt16LE(p + 32);
    names.push(b.toString('utf8', p + 46, p + 46 + nl));
    p += 46 + nl + el + cl;
  }
  return names;
}

const PDF_URL = /pdfjs-dist|pdf-lib|pdf\.worker|\/sheets\/(pdfSession|pdfRuntime|pdfRead|pdfWrite|viewer)/;
const errors = [];
let browser;
try {
  await waitForServer();
  browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1500, height: 820 } });
  const page = await ctx.newPage();
  page.setDefaultTimeout(Number(process.env.SMOKE_TIMEOUT ?? 120000));
  const requests = [];
  page.on('request', (r) => requests.push(r.url()));
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', (e) => errors.push(`[pageerror] ${e.message}`));
  const pdfRequests = () => requests.filter((u) => PDF_URL.test(u));
  const toB64 = (arr) => Buffer.from(arr).toString('base64');
  /** Bytes out of the page as a Buffer. */
  const bytesOf = async (fn, ...args) => Buffer.from(await page.evaluate(async ([src, a]) => {
    const u8 = await (0, eval)(`(${src})`)(...a);
    let s = '';
    for (let i = 0; i < u8.length; i += 8192) s += String.fromCharCode(...u8.subarray(i, i + 8192));
    return btoa(s);
  }, [fn.toString(), args]), 'base64');

  // ------------------------------------------------------------------ boot: nothing PDF loads
  await page.goto(`http://127.0.0.1:${port}/?model=fzk-haus`);
  await page.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: 240000 });
  const err0 = await page.evaluate('window.__xrayError');
  if (err0) throw new Error(`startup failed: ${err0}`);
  await page.waitForTimeout(500);
  check('no PDF chunk loads at start up', pdfRequests().length === 0, pdfRequests().join(', '));
  await page.evaluate(() => window.__xrayIssues.open('sheets'));
  await page.waitForSelector('#issues-panel [data-seg=sheets][aria-selected=true]');
  check('the Issues panel has a Sheets segment', (await page.textContent('#issues-panel')).includes('No sheets yet'));
  await page.waitForTimeout(400);
  check('showing the Sheets segment loads no PDF chunk either', pdfRequests().length === 0, pdfRequests().join(', '));

  // ------------------------------------------------------------------ open the fixture through the file input
  await page.setInputFiles('input[data-sheets=open]', FIXTURE);
  await page.waitForFunction(() => window.__xraySheets.docs().length === 1 && /opened/.test(window.__xraySheets.status), null, { timeout: 90000 });
  check('the PDF libraries load once a PDF is opened', pdfRequests().length > 0, `${pdfRequests().length} requests`);
  const modelStill = await page.evaluate(() => ({ name: window.__xray.app.modelName, n: window.__xray.app.controller.model.elements.length }));
  check('opening the PDF did not replace the model', modelStill.name === 'fzk-haus' && modelStill.n > 0, JSON.stringify(modelStill));
  const docs = await page.evaluate(() => window.__xraySheets.docs());
  const sheets = await page.evaluate(() => window.__xraySheets.sheets());
  check('one doc with two sheets (a page each)', docs.length === 1 && docs[0].pageCount === 2 && sheets.length === 2 && sheets[0].page === 1 && sheets[1].page === 2 && sheets[0].placement === undefined, JSON.stringify(sheets.map((s) => [s.id, s.widthPt, s.heightPt])));
  check('the doc names its bytes and hash', /^[0-9a-f]{64}$/.test(docs[0].sha256) && docs[0].bytesKey === docs[0].sha256);
  await page.waitForSelector('#issues-panel [data-doc] .sh-page');
  const cards = await page.evaluate(() => [...document.querySelectorAll('#issues-panel [data-sheet-pages] .sh-page')].map((c) => ({ img: !!c.querySelector('img[src^="data:image/jpeg"]'), t: c.textContent })));
  check('the Sheets segment lists the doc, then its pages with thumbnails', cards.length === 2 && cards.every((c) => c.img), JSON.stringify(cards));
  const stored = await page.evaluate(() => ({ ls: Object.keys(localStorage).filter((k) => /pdf|sheet/i.test(k)), size: JSON.stringify(localStorage).length, hash: location.hash, search: location.search }));
  check('no PDF data in localStorage or the URL', stored.ls.length === 0 && stored.size < 50000 && !/pdf|JVBER/i.test(stored.hash + stored.search), JSON.stringify(stored).slice(0, 200));
  const idb = await page.evaluate(async () => {
    const db = await new Promise((res, rej) => { const o = indexedDB.open('xray-sheets'); o.onsuccess = () => res(o.result); o.onerror = () => rej(o.error); });
    const n = await new Promise((res) => { const r = db.transaction('bytes').objectStore('bytes').count(); r.onsuccess = () => res(r.result); });
    db.close();
    return n;
  });
  check('the PDF bytes are kept in IndexedDB', idb === 1, `${idb} record(s)`);

  // ------------------------------------------------------------------ the viewer
  const sheetId = sheets[0].id;
  await page.click(`#issues-panel [data-sheet="${sheetId}"]`);
  await page.waitForSelector('#sheet-view.on');
  await page.waitForFunction(() => window.__xraySheets.view()?.renders.base >= 1, null, { timeout: 60000 });
  const geo = await page.evaluate(() => {
    const r = (s) => { const b = document.querySelector(s).getBoundingClientRect(); return { x: b.left, y: b.top, w: b.width, h: b.height, r: b.right, b: b.bottom }; };
    return { view: r('#sheet-view'), canvas: r('#stage canvas:not(.sv-base):not(.sv-detail)'), bar: r('#xray-topbar'), status: r('#xray-overlay') };
  });
  check('the sheet view covers the canvas area between the top bar and the status bar', geo.view.r >= geo.canvas.r - 1 && geo.view.y >= geo.bar.b - 1 && geo.view.b <= geo.status.y + 1 && geo.view.h > geo.canvas.h * 0.8, JSON.stringify(geo.view));
  check('a clear Back to model control is there', (await page.textContent('#sheet-view [data-act=back]')) === 'Back to model');
  check('the model is still loaded under the sheet', await page.evaluate(() => !!window.__xray.app.loaded && window.__xraySheets.openSheet !== null));
  await page.waitForTimeout(500);
  const px = await page.evaluate(() => {
    const cv = document.querySelector('#sheet-view canvas.sv-base');
    const g = cv.getContext('2d');
    const d = g.getImageData(0, 0, cv.width, cv.height).data;
    let dark = 0;
    for (let i = 0; i < d.length; i += 4 * 97) if (d[i] < 100) dark++;
    return { w: cv.width, h: cv.height, dark };
  });
  check('the page is drawn by pdf.js', px.w > 800 && px.dark > 50, JSON.stringify(px));

  // imported annotations: one read-only sketch with author and contents
  const imported = await page.evaluate((id) => window.__xraySheets.sketches(id), sheetId);
  check('the annotations of the PDF come in as one read-only "Imported annotations" sketch', imported.length === 1 && imported[0].readonly === true && /Imported annotations/.test(imported[0].title) && imported[0].markups.length === 3, JSON.stringify(imported.map((s) => [s.title, s.markups.length])));
  check('the imported markups keep their author and contents', imported[0].markups.some((m) => m.author === 'Reviewer A' && /clearance/.test(m.text)) && imported[0].markups.some((m) => m.kind === 'pen') && imported[0].markups.some((m) => m.kind === 'text'));

  // ------------------------------------------------------------------ pan and zoom: the picture sharpens when the zoom settles
  const stageBox = async () => page.evaluate(() => { const b = document.querySelector('#sheet-view [data-sv=stage]').getBoundingClientRect(); return { x: b.left, y: b.top, w: b.width, h: b.height }; });
  const sb = await stageBox();
  const fitView = await page.evaluate(() => window.__xraySheets.view());
  check('at fit the whole page is shown at a scale below the page picture', fitView.scale > 0 && fitView.detailShown === false, JSON.stringify(fitView));
  const sq = [310, 395, 400, 450]; // the foreign Square, PDF user space
  const squareBox = async () => page.evaluate(() => { const g = [...document.querySelectorAll('#sheet-view svg [data-mk]')].find((e) => window.__xraySheets.controller.markup.markup(e.getAttribute('data-mk'))?.m.kind === 'rect' && window.__xraySheets.controller.markup.markup(e.getAttribute('data-mk'))?.set.readonly); const path = g.querySelector('[data-role=shape]'); const b = path.getBoundingClientRect(); return { x0: b.left, y0: b.top, x1: b.right, y1: b.bottom }; });
  const expectSquare = async () => page.evaluate(([x0, y0, x1, y1]) => { const p = window.__xraySheets.toStage(x0, y0); const q = window.__xraySheets.toStage(x1, y1); const r = document.querySelector('#sheet-view [data-sv=stage]').getBoundingClientRect(); return { x0: r.left + Math.min(p[0], q[0]), y0: r.top + Math.min(p[1], q[1]), x1: r.left + Math.max(p[0], q[0]), y1: r.top + Math.max(p[1], q[1]) }; }, sq);
  const near = (a, b, tol) => Math.abs(a.x0 - b.x0) <= tol && Math.abs(a.y0 - b.y0) <= tol && Math.abs(a.x1 - b.x1) <= tol && Math.abs(a.y1 - b.y1) <= tol;
  const e0 = await expectSquare();
  const s0 = await squareBox();
  check('the imported square sits on its PDF points (fit)', near(e0, s0, 6), `${JSON.stringify(e0)} vs ${JSON.stringify(s0)}`);
  // zoom in with the wheel on the square, then wait for the sharp picture
  const cx = sb.x + sb.w / 2;
  const cy = sb.y + sb.h / 2;
  await page.mouse.move(cx, cy);
  for (let i = 0; i < 3; i++) await page.mouse.wheel(0, -300);
  await page.waitForFunction(() => window.__xraySheets.view().detailShown, null, { timeout: 30000 });
  const zv = await page.evaluate(() => window.__xraySheets.view());
  check('the wheel zooms in and the picture is drawn again sharp once the zoom settles', zv.scale > fitView.scale * 2 && zv.detailShown && Math.abs(zv.detailScale - zv.scale * Math.min(2, 1)) < zv.scale * 0.6 && zv.renders.detail >= 1, JSON.stringify(zv));
  // drag to pan, then pinch (touch events are not available here: pinch is checked through the transform below)
  await page.mouse.move(cx, cy);
  await page.mouse.down();
  await page.mouse.move(cx + 120, cy + 70, { steps: 5 });
  await page.mouse.up();
  const pv = await page.evaluate(() => window.__xraySheets.view());
  check('a drag pans the page', Math.abs(pv.tx - zv.tx - 120) < 3 && Math.abs(pv.ty - zv.ty - 70) < 3, `${zv.tx},${zv.ty} -> ${pv.tx},${pv.ty}`);
  await page.waitForFunction(() => window.__xraySheets.view().detailShown, null, { timeout: 30000 });
  const e1 = await expectSquare();
  const s1 = await squareBox();
  check('the imported square stays on its PDF points after pan and zoom', near(e1, s1, 6), `${JSON.stringify(e1)} vs ${JSON.stringify(s1)}`);
  await page.click('#sheet-view [data-act=fit]');

  // ------------------------------------------------------------------ draw a cloud and a text
  await page.click('#sheet-view [data-act=draw]');
  await page.waitForSelector('#sheet-float', { state: 'visible' });
  const toolIds = await page.evaluate(() => [...document.querySelectorAll('#sheet-float [data-tool-id]')].map((b) => b.dataset.toolId));
  check('the same toolbar, with every tool that makes sense on a page', ['cloud', 'cloudFree', 'rect', 'ellipse', 'arrow', 'line', 'polyline', 'polygon', 'pen', 'text', 'callout', 'highlight', 'highlightBox'].every((t) => toolIds.includes(t)) && !toolIds.includes('pointer'), toolIds.join(','));
  const barBox = await page.evaluate(() => { const b = document.querySelector('#sheet-float').getBoundingClientRect(); const v = document.querySelector('#sheet-view [data-sv=stage]').getBoundingClientRect(); return { inside: b.left >= v.left - 1 && b.right <= v.right + 1 && b.top >= v.top - 1 && b.bottom <= v.bottom + 1 }; });
  check('the toolbar sits inside the sheet view', barBox.inside);
  const set0 = await page.evaluate((id) => window.__xraySheets.sketches(id).find((s) => !s.readonly), sheetId);
  check('choosing Draw made an editable sketch on the sheet', !!set0 && set0.frame.kind === 'sheet' && set0.frame.sheet === sheetId);
  const toPx = async (ux, uy) => page.evaluate(([x, y]) => { const p = window.__xraySheets.toStage(x, y); const r = document.querySelector('#sheet-view [data-sv=stage]').getBoundingClientRect(); return [r.left + p[0], r.top + p[1]]; }, [ux, uy]);
  const drag = async (a, b) => {
    await page.mouse.move(a[0], a[1]);
    await page.mouse.down();
    for (let i = 1; i <= 4; i++) await page.mouse.move(a[0] + ((b[0] - a[0]) * i) / 4, a[1] + ((b[1] - a[1]) * i) / 4);
    await page.mouse.up();
  };
  await page.click('#sheet-float [data-tool-id=cloud]');
  const c0 = await toPx(100, 100);
  const c1 = await toPx(230, 180);
  await drag(c0, c1);
  await page.click('#sheet-float [data-tool-id=text]');
  await page.fill('#sheet-float [aria-label="Text for the next markup"]', 'Move wall 50 mm');
  const tp = await toPx(560, 300);
  await page.mouse.click(tp[0], tp[1]);
  const mine = await page.evaluate((id) => window.__xraySheets.sketches(id).find((s) => !s.readonly), sheetId);
  const cloud = mine.markups.find((m) => m.kind === 'cloud');
  const text = mine.markups.find((m) => m.kind === 'text');
  check('a cloud and a text are drawn', !!cloud && !!text && mine.markups.length === 2, mine.markups.map((m) => m.kind).join(','));
  const near2 = (a, b, tol) => Math.abs(a - b) <= tol;
  check('shapes are stored in PDF points of the page, not view fractions', cloud.shape.points.length === 2 && near2(cloud.shape.points[0][0], 100, 3) && near2(cloud.shape.points[0][1], 100, 3) && near2(cloud.shape.points[1][0], 230, 3) && near2(cloud.shape.points[1][1], 180, 3) && near2(text.anchor.point[0], 560, 3) && near2(text.anchor.point[1], 300, 3), JSON.stringify([cloud.shape.points, text.anchor.point]));
  check('the text has the typed words', text.text === 'Move wall 50 mm');
  // pan and zoom: the points do not change and the drawing follows the page
  const before = JSON.stringify([cloud.shape, text.anchor]);
  const markBox = (kind) => page.evaluate((k) => { const g = [...document.querySelectorAll('#sheet-view svg [data-mk]')].find((e) => { const f = window.__xraySheets.controller.markup.markup(e.getAttribute('data-mk')); return f && f.m.kind === k && !f.set.readonly; }); const b = g.querySelector('[data-role=shape],[data-role=anchor]').getBoundingClientRect(); return [(b.left + b.right) / 2, (b.top + b.bottom) / 2]; }, kind);
  const cloudCentre = async () => { const p = await markBox('cloud'); return p; };
  const expectCentre = async () => toPx((cloud.shape.points[0][0] + cloud.shape.points[1][0]) / 2, (cloud.shape.points[0][1] + cloud.shape.points[1][1]) / 2);
  const d0 = await cloudCentre();
  const x0 = await expectCentre();
  check('the cloud is drawn where it was stored', Math.hypot(d0[0] - x0[0], d0[1] - x0[1]) < 4, `${d0} vs ${x0}`);
  await page.click('#sheet-float [data-tool-id=select]');
  await page.mouse.move(cx, cy);
  for (let i = 0; i < 3; i++) await page.mouse.wheel(0, -260);
  await page.mouse.move(cx - 200, cy - 100);
  await page.mouse.down();
  await page.mouse.move(cx - 80, cy - 30, { steps: 4 });
  await page.mouse.up();
  await page.waitForFunction(() => window.__xraySheets.view().detailShown, null, { timeout: 30000 });
  const after = await page.evaluate((id) => { const s = window.__xraySheets.sketches(id).find((q) => !q.readonly); return JSON.stringify([s.markups.find((m) => m.kind === 'cloud').shape, s.markups.find((m) => m.kind === 'text').anchor]); }, sheetId);
  check('pan and zoom leave the stored PDF points alone', after === before);
  const d1 = await cloudCentre();
  const x1 = await expectCentre();
  check('after pan and zoom the cloud is still on the same PDF points', Math.hypot(d1[0] - x1[0], d1[1] - x1[1]) < 4 && Math.hypot(d1[0] - d0[0], d1[1] - d0[1]) > 20, `${d1} vs ${x1}`);
  await page.click('#sheet-view [data-act=fit]');
  await page.waitForTimeout(300);
  // the rest of the tools: every one draws a markup (the point of "every tool that makes sense in 2D")
  const toolDraw = [['rect', 'drag'], ['ellipse', 'drag'], ['line', 'drag'], ['arrow', 'drag'], ['cloudFree', 'free'], ['pen', 'free'], ['highlight', 'free'], ['highlightBox', 'drag'], ['polyline', 'poly'], ['polygon', 'poly'], ['callout', 'click']];
  let yy = 330;
  for (const [tool, how] of toolDraw) {
    await page.click(`#sheet-float [data-tool-id=${tool}]`);
    const a = await toPx(60, yy);
    const b = await toPx(160, yy - 30);
    if (how === 'drag') await drag(a, b);
    else if (how === 'free') {
      await page.mouse.move(a[0], a[1]);
      await page.mouse.down();
      for (let i = 1; i <= 8; i++) await page.mouse.move(a[0] + i * 12, a[1] + (i % 2 ? 10 : -10) + (tool === 'cloudFree' ? i * 3 : 0));
      await page.mouse.move(a[0] + 20, a[1] + 40);
      await page.mouse.up();
    } else if (how === 'poly') {
      const m = await toPx(110, yy - 60);
      await page.mouse.click(a[0], a[1]);
      await page.mouse.click(b[0], b[1]);
      await page.mouse.click(m[0], m[1] + 20);
      await page.keyboard.press('Enter');
    } else {
      await page.fill('#sheet-float [aria-label="Text for the next markup"]', 'Callout text');
      await page.mouse.click(a[0], a[1]);
    }
    yy += 16;
  }
  const allKinds = await page.evaluate((id) => window.__xraySheets.sketches(id).find((s) => !s.readonly).markups.map((m) => m.kind), sheetId);
  const want = ['cloud', 'text', 'rect', 'ellipse', 'line', 'arrow', 'cloud', 'pen', 'highlight', 'highlightBox', 'polyline', 'polygon', 'callout'];
  check('every tool makes a markup on the sheet', JSON.stringify(allKinds.slice().sort()) === JSON.stringify(want.slice().sort()), allKinds.join(','));
  await page.click('#sheet-float [data-tool-id=select]');
  // undo and redo work on the sheet sketch
  const n0 = allKinds.length;
  await page.keyboard.press('Control+z');
  const n1 = await page.evaluate((id) => window.__xraySheets.sketches(id).find((s) => !s.readonly).markups.length, sheetId);
  await page.keyboard.press('Control+Shift+z');
  const n2 = await page.evaluate((id) => window.__xraySheets.sketches(id).find((s) => !s.readonly).markups.length, sheetId);
  check('undo and redo work on a sheet sketch', n1 === n0 - 1 && n2 === n0, `${n0} ${n1} ${n2}`);
  // keep the sketch to what the later checks expect: a cloud and a text, plus a callout and a rectangle
  const keep = await page.evaluate((id) => { const s = window.__xraySheets.sketches(id).find((q) => !q.readonly); return s.markups.filter((m) => ['cloud', 'text', 'callout', 'rect', 'arrow', 'pen', 'highlightBox'].includes(m.kind)).map((m) => m.id); }, sheetId);
  await page.evaluate(([id, k]) => { const mk = window.__xraySheets.controller.markup; const s = mk.get(window.__xraySheets.sketches(id).find((q) => !q.readonly).id); for (const m of [...s.markups]) if (!k.includes(m.id)) mk.remove(m.id); }, [sheetId, keep]);
  await page.click('#sheet-float [data-act=done]');
  await page.waitForTimeout(500);
  await page.screenshot({ path: resolve(here, 'sheets-view.png') });

  // ------------------------------------------------------------------ export the marked-up PDF
  const sketchNow = await page.evaluate((id) => window.__xraySheets.sketches(id).find((s) => !s.readonly), sheetId);
  const nOwn = sketchNow.markups.length;
  const doc0 = docs[0];
  const out1 = await bytesOf(async (docId) => (await window.__xraySheets.exportMarkedUp(docId)).bytes, doc0.id);
  const read = async (buf) => {
    const d = await PdfLib.PDFDocument.load(buf, { updateMetadata: false });
    const N = PdfLib.PDFName.of;
    const ocp = d.catalog.lookup(N('OCProperties'), PdfLib.PDFDict);
    const ocgs = ocp.lookup(N('OCGs'), PdfLib.PDFArray);
    const ref = ocgs.get(0);
    const ocg = d.context.lookup(ref, PdfLib.PDFDict);
    const dd = ocp.lookup(N('D'), PdfLib.PDFDict);
    const inArr = (a) => { for (let i = 0; i < a.size(); i++) if (a.get(i).objectNumber === ref.objectNumber) return true; return false; };
    const annots = d.getPages()[0].node.lookup(N('Annots'), PdfLib.PDFArray);
    const list = [];
    for (let i = 0; i < annots.size(); i++) {
      const a = d.context.lookup(annots.get(i), PdfLib.PDFDict);
      const nm = a.lookup(N('NM'));
      list.push({ nm: nm ? nm.decodeText() : '', sub: a.lookup(N('Subtype')).decodeText(), oc: a.get(N('OC'))?.objectNumber, ap: a.has(N('AP')), t: a.lookup(N('T'))?.decodeText(), be: a.has(N('BE')), it: a.lookup(N('IT'))?.decodeText(), cl: a.has(N('CL')), le: a.has(N('LE')) });
    }
    return { layerName: ocg.lookup(N('Name')).decodeText(), nOcgs: ocgs.size(), order: inArr(dd.lookup(N('Order'), PdfLib.PDFArray)), on: inArr(dd.lookup(N('ON'), PdfLib.PDFArray)), ocgNum: ref.objectNumber, list };
  };
  const r1 = await read(out1);
  const mineA = r1.list.filter((a) => a.nm.startsWith('xray-'));
  check('the export has one layer named "X-ray markups" in /OCGs, /Order and /ON', r1.layerName === 'X-ray markups' && r1.nOcgs === 1 && r1.order && r1.on);
  check('every added annotation points at the layer and has an appearance stream', mineA.length === nOwn && mineA.every((a) => a.oc === r1.ocgNum && a.ap && a.t === 'X-ray'), `${mineA.length} of ${nOwn}`);
  check('the cloud is a /Polygon with the cloud border effect, the text a /FreeText, the callout a FreeTextCallout with /CL', mineA.some((a) => a.sub === 'Polygon' && a.be && a.it === 'PolygonCloud') && mineA.some((a) => a.sub === 'FreeText' && !a.it) && mineA.some((a) => a.sub === 'FreeText' && a.it === 'FreeTextCallout' && a.cl), JSON.stringify(mineA.map((a) => a.sub)));
  check('the annotations that are not ours are still there', r1.list.filter((a) => a.nm.startsWith('foreign-')).length === 3);
  const out2 = await bytesOf(async (docId) => (await window.__xraySheets.exportMarkedUp(docId)).bytes, doc0.id);
  const r2 = await read(out2);
  check('exporting again replaces the X-ray annotations instead of doubling them', r2.list.filter((a) => a.nm.startsWith('xray-')).length === nOwn && r2.list.length === r1.list.length && r2.nOcgs === 1);
  const dl = page.waitForEvent('download');
  await page.click('#issues-panel [data-act=export-pdf]').catch(() => undefined);
  const dlf = await Promise.race([dl, new Promise((r) => setTimeout(() => r(null), 15000))]);
  check('the Export marked-up PDF button downloads the file', !!dlf && /markup\.pdf$/.test(dlf.suggestedFilename()), dlf ? dlf.suggestedFilename() : 'no download');

  // ------------------------------------------------------------------ open the exported PDF again
  await page.setInputFiles('input[data-sheets=open]', { name: 'sample-sheet-markup.pdf', mimeType: 'application/pdf', buffer: out1 });
  await page.waitForFunction(() => window.__xraySheets.docs().length === 2 && /opened/.test(window.__xraySheets.status), null, { timeout: 90000 });
  const docs2 = await page.evaluate(() => window.__xraySheets.docs());
  const reDoc = docs2.find((d) => d.name === 'sample-sheet-markup.pdf');
  const reSheet = (await page.evaluate((id) => window.__xraySheets.sheets(id), reDoc.id))[0];
  const reSets = await page.evaluate((id) => window.__xraySheets.sketches(id), reSheet.id);
  const reOwn = reSets.find((s) => !s.readonly);
  const reForeign = reSets.find((s) => s.readonly);
  check('the markups of the exported PDF come back as an editable sketch', !!reOwn && reOwn.markups.length === nOwn && reOwn.title.startsWith(sketchNow.title), `${reOwn?.markups.length} of ${nOwn}`);
  check('the shapes come back exactly (kind and points)', JSON.stringify(reOwn.markups.map((m) => [m.kind, m.shape?.points ?? m.anchor.point.slice(0, 2)]).sort()) === JSON.stringify(sketchNow.markups.map((m) => [m.kind, m.shape?.points ?? m.anchor.point.slice(0, 2)]).sort()));
  check('the foreign annotations stay read-only', !!reForeign && reForeign.markups.length === 3 && reForeign.readonly === true);
  const ro = await page.evaluate(([setId, mid]) => { const mk = window.__xraySheets.controller.markup; return { removed: mk.remove(mid), patched: mk.patch(mid, { text: 'x' }), count: mk.get(setId).markups.length }; }, [reForeign.id, reForeign.markups[0].id]);
  check('a read-only sketch refuses edits', ro.removed === false && ro.patched === false && ro.count === 3);
  // the imported sketch can be copied to an editable one
  const copy = await page.evaluate((id) => { const c = window.__xraySheets.copyToEditable(id); return c ? { ro: !!c.readonly, n: c.markups.length } : null; }, reForeign.id);
  check('a read-only sketch can be copied to an editable one', !!copy && copy.ro === false && copy.n === 3);
  await page.evaluate((id) => window.__xraySheets.open(id), reSheet.id);
  await page.waitForFunction(() => window.__xraySheets.view()?.renders.base >= 2, null, { timeout: 60000 });
  await page.evaluate((id) => { window.__xraySheets.controller.markup.selectMarkup(window.__xraySheets.sketches(id).find((s) => s.readonly).markups.find((m) => m.author === 'Reviewer A' && m.kind === 'rect').id); }, reSheet.id);
  await page.waitForTimeout(600);
  const infoTxt = await page.evaluate(() => document.querySelector('#sheet-view [data-sv=info]').textContent);
  check('selecting an imported shape shows its author and contents', /Reviewer A/.test(infoTxt) && /clearance/.test(infoTxt), infoTxt);
  await page.screenshot({ path: resolve(here, 'sheets-imported.png') });

  // ------------------------------------------------------------------ raise as issue, BCF export, re-import
  const mkId = reOwn.id;
  const guid = await page.evaluate((id) => window.__xraySheets.raise(id), mkId);
  const topic = await page.evaluate((g) => { const t = window.__xrayBcf.topics.find((x) => x.guid === g); return { vps: t.viewpoints.length, snap: !!t.viewpoints[0].snapshot, data: t.viewpoints[0].data, sheet: t.viewpoints[0].sheet && { page: t.viewpoints[0].sheet.page, sha: t.viewpoints[0].sheet.sha256, n: t.viewpoints[0].sheet.markups.length }, docs: t.documentReferences.length, sketch: t.viewpoints[0].sketchId }; }, guid);
  check('raising a sheet sketch makes an issue with a snapshot of the sheet region and a document reference', topic.vps === 1 && topic.snap && topic.data === null && topic.docs === 1 && topic.sheet.page === 1 && topic.sheet.sha === reDoc.sha256 && topic.sheet.n === nOwn && topic.sketch === mkId, JSON.stringify(topic));
  check('the sketch links to its issue', await page.evaluate((id) => window.__xrayIssues.issueOf(id)?.topic, mkId) === guid);
  const png = await page.evaluate((g) => { const s = window.__xrayBcf.topics.find((x) => x.guid === g).viewpoints[0].snapshot; return [s[0], s[1], s[2], s[3]]; }, guid);
  check('the snapshot is a PNG', png[0] === 0x89 && png[1] === 0x50);
  for (const version of ['3.0', '2.1']) {
    const zip = await bytesOf(async (v) => window.__xrayBcf.exportZip(v), version);
    const names = zipNames(zip);
    const pdfIn = names.filter((n) => /\.pdf$/i.test(n) || /^Documents\//i.test(n));
    check(`BCF ${version}: the bcfzip carries the PDF`, pdfIn.length >= 1, names.join(', '));
    check(`BCF ${version}: the side file is there`, names.some((n) => /xray-markup\.json$/.test(n)));
    const info = await page.evaluate(async ([v]) => {
      const bytes = await window.__xrayBcf.exportZip(v);
      const proj = await (await import('/src/bcf/parse.ts')).parseBcf(bytes);
      const t = proj.topics[0];
      return { refs: t.documentReferences.map((r) => ({ external: r.external, target: r.target })), docs: proj.documents.map((d) => ({ filename: d.filename, len: d.data?.length ?? 0 })), sheet: t.viewpoints[0].sheet ? { page: t.viewpoints[0].sheet.page, sha: t.viewpoints[0].sheet.sha256, markups: t.viewpoints[0].sheet.markups.length, name: t.viewpoints[0].sheet.name } : null, snap: !!t.viewpoints[0].snapshot };
    }, [version]);
    check(`BCF ${version}: the DocumentReference points at the PDF inside the zip and the side file names sheet, page and shapes`, info.refs.length === 1 && info.refs[0].external === false && info.docs.length === 1 && info.docs[0].len === out1.length && info.sheet?.page === 1 && info.sheet.sha === reDoc.sha256 && info.sheet.markups === nOwn && info.snap, JSON.stringify(info));
  }
  // re-import: remove the PDF and its sketch, then open the bcfzip: the PDF comes from the zip and the sketch finds its sheet by hash
  const zip30 = await bytesOf(async () => window.__xrayBcf.exportZip('3.0'));
  await page.evaluate(async () => { window.__xraySheets.close(); });
  await page.evaluate(async (docId) => { await window.__xraySheets.removeDoc(docId); const b = window.__xrayBcf; for (const t of [...b.topics]) window.__xrayIssues.controller.deleteIssue(t.guid); }, reDoc.id);
  const gone = await page.evaluate((d) => ({ docs: window.__xraySheets.docs().length, has: window.__xraySheets.docs().some((x) => x.id === d), topics: window.__xrayBcf.topics.length }), reDoc.id);
  check('the PDF and the issue are gone before the re-import', !gone.has && gone.topics === 0, JSON.stringify(gone));
  await page.evaluate(async (b64) => { const bin = atob(b64); const u8 = new Uint8Array(bin.length); for (let i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i); await window.__xrayBcf.load(u8); }, toB64(zip30));
  await page.waitForFunction((d) => window.__xraySheets.docs().some((x) => x.id === d), reDoc.id, { timeout: 60000 });
  await page.waitForTimeout(500);
  const back = await page.evaluate(([d, sid]) => {
    const t = window.__xrayBcf.topics[0];
    const sk = window.__xraySheets.controller.markup.get(t.viewpoints[0].sketchId);
    return { sheetKnown: !!window.__xraySheets.controller.sheetOfSet(sk), frame: sk.frame.sheet, want: sid, n: sk.markups.length, issue: sk.issue?.topic === t.guid, same: window.__xraySheets.docs().find((x) => x.id === d)?.sha256 };
  }, [reDoc.id, reSheet.id]);
  check('opening the bcfzip again restores the sketch and its sheet link by the SHA-256 of the PDF', back.sheetKnown && back.frame === back.want && back.n === nOwn && back.issue, JSON.stringify(back));

  // ------------------------------------------------------------------ back to the model
  await page.evaluate((id) => window.__xraySheets.open(id), reSheet.id);
  await page.waitForSelector('#sheet-view.on');
  await page.click('#sheet-view [data-act=back]');
  await page.waitForFunction(() => !document.querySelector('#sheet-view.on'));
  check('Back to model returns to the 3D view', await page.evaluate(() => window.__xraySheets.openSheet === null && !!window.__xray.app.loaded && !window.__xrayMarkup.editing));

  // ------------------------------------------------------------------ the phone
  const pctx = await browser.newContext({ viewport: { width: 360, height: 740 }, hasTouch: true, isMobile: true });
  const phone = await pctx.newPage();
  phone.setDefaultTimeout(Number(process.env.SMOKE_TIMEOUT ?? 120000));
  phone.on('console', (m) => { if (m.type() === 'error') errors.push(`[phone] ${m.text()}`); });
  phone.on('pageerror', (e) => errors.push(`[phone pageerror] ${e.message}`));
  await phone.goto(`http://127.0.0.1:${port}/?model=fzk-haus`);
  await phone.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: 240000 });
  await phone.evaluate(() => window.__xrayIssues.open('sheets'));
  await phone.setInputFiles('input[data-sheets=open]', FIXTURE);
  await phone.waitForFunction(() => window.__xraySheets.docs().length === 1 && /opened/.test(window.__xraySheets.status), null, { timeout: 90000 });
  await phone.waitForSelector('#issues-sheet.on [data-sheet]');
  await phone.tap('#issues-sheet [data-sheet]:first-of-type');
  await phone.waitForSelector('#sheet-view.on');
  await phone.waitForFunction(() => window.__xraySheets.view()?.renders.base >= 1, null, { timeout: 60000 });
  await phone.click('#sheet-view [data-act=draw]');
  await phone.waitForSelector('#sheet-float', { state: 'visible' });
  await phone.waitForTimeout(600);
  const pg = await phone.evaluate(() => {
    const v = document.querySelector('#sheet-view').getBoundingClientRect();
    const b = document.querySelector('#sheet-float').getBoundingClientRect();
    const bar = document.querySelector('#sheet-view .sv-bar');
    const back = document.querySelector('#sheet-view [data-act=back]').getBoundingClientRect();
    return { vw: innerWidth, view: [v.left, v.right], bar: [b.left, b.right, b.top, b.bottom], barScroll: bar.scrollWidth <= bar.clientWidth + 1, back: [back.left, back.right], docScroll: document.documentElement.scrollWidth <= innerWidth + 1, clear: ['#sidebar', '#xray-toolbar', '#dock'].every((q) => { const e = document.querySelector(q); if (!e || !e.getClientRects().length) return true; const b = e.getBoundingClientRect(); return b.right <= v.left + 1 || b.left >= v.right - 1 || b.bottom <= v.top + 1 || b.top >= v.bottom - 1; }), sheetPanelOpen: !!document.querySelector('#issues-sheet.on'), cardsGone: true };
  });
  check('on a 360 px phone the sheet view fits the width, with Back to model and the toolbar in reach', pg.view[1] <= pg.vw + 1 && pg.bar[0] >= pg.view[0] - 1 && pg.bar[1] <= pg.view[1] + 1 && pg.barScroll && pg.back[0] >= pg.view[0] - 1 && pg.back[1] <= pg.view[1] + 1 && pg.docScroll && pg.clear, JSON.stringify(pg));
  check('opening a sheet on the phone closes the issues bottom sheet', !pg.sheetPanelOpen);
  // a touch pinch: two pointers through the CDP, as the viewer reads pointer events
  const cdp = await pctx.newCDPSession(phone);
  const st = await phone.evaluate(() => { const b = document.querySelector('#sheet-view [data-sv=stage]').getBoundingClientRect(); return { x: b.left + b.width / 2, y: b.top + b.height / 2 }; });
  const s0v = await phone.evaluate(() => window.__xraySheets.view().scale);
  await phone.click('#sheet-float [data-act=done]');
  await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x: st.x - 20, y: st.y, id: 1 }, { x: st.x + 20, y: st.y, id: 2 }] });
  for (let i = 1; i <= 6; i++) await cdp.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x: st.x - 20 - i * 12, y: st.y, id: 1 }, { x: st.x + 20 + i * 12, y: st.y, id: 2 }] });
  await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
  await phone.waitForTimeout(300);
  const s1v = await phone.evaluate(() => window.__xraySheets.view().scale);
  check('a two finger pinch zooms the page', s1v > s0v * 1.5, `${s0v.toFixed(3)} -> ${s1v.toFixed(3)}`);
  await phone.evaluate(() => window.__xraySheets.fit());
  await phone.waitForTimeout(300);
  await phone.click('#sheet-view [data-act=draw]');
  await phone.waitForTimeout(400);
  await phone.screenshot({ path: resolve(here, 'sheets-phone.png') });
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
