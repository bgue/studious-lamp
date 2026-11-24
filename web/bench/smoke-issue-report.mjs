// Headless check for the issue report (PDF and CSV) on /?model=fzk-haus (docs-features/issues.md, "Issue report"):
//   - the Issues tab has a collapsed "Export report" block with a page size (A4) and "Plan/Section images" (on), and PDF and CSV
//     buttons that count the issues of the list;
//   - the PDF has a cover and a page per issue, links from the cover rows to the pages, the comments with their authors, a snapshot
//     per issue and a Plan and Section for the issue whose view is tied to the model;
//   - the Plan and Section are rendered on the live view without a flicker (a still copy of the canvas covers it while it switches),
//     and the camera, the clip planes and the projection are back after;
//   - Letter and "Plan/Section images" off give Letter pages and no Plan or Section;
//   - the CSV has one row per issue with a Comments column, and follows the status chip and the search of the list;
//   - fails on any console error.
// Screenshot: bench/issue-report-panel.png. Downloads are read back with pdf-lib.
// Usage: SMOKE_PORT=5731 node bench/smoke-issue-report.mjs
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const port = Number(process.env.SMOKE_PORT ?? 5731);

function loadPlaywright() {
  const candidates = [process.env.PLAYWRIGHT_MODULE, resolve(root, 'node_modules/playwright'), '/opt/node-tools/node_modules/playwright', '/opt/node22/lib/node_modules/playwright', 'playwright'].filter(Boolean);
  for (const c of candidates) {
    try { return createRequire(import.meta.url)(c); } catch { /* next */ }
  }
  throw new Error('playwright not found; set PLAYWRIGHT_MODULE');
}
const { chromium } = loadPlaywright();
const { PDFDocument, PDFDict, PDFName } = createRequire(import.meta.url)(resolve(root, 'node_modules/pdf-lib'));

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

/** Rows of a CSV text (RFC 4180: quoted cells, doubled quotes, line breaks inside quotes). */
function parseCsv(text) {
  const rows = [];
  let row = [], cell = '', q = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (q) {
      if (c === '"') { if (text[i + 1] === '"') { cell += '"'; i++; } else q = false; } else cell += c;
    } else if (c === '"') q = true;
    else if (c === ',') { row.push(cell); cell = ''; }
    else if (c === '\r') { /* CRLF */ }
    else if (c === '\n') { row.push(cell); rows.push(row); row = []; cell = ''; }
    else cell += c;
  }
  if (cell || row.length) { row.push(cell); rows.push(row); }
  return rows;
}
const latin1 = (b) => Buffer.from(b).toString('latin1');

async function pdfInfo(bytes) {
  const pdf = await PDFDocument.load(bytes);
  const pages = pdf.getPages();
  const cover = pages[0].node.Annots();
  const dests = [];
  for (let i = 0; cover && i < cover.size(); i++) {
    const a = cover.lookup(i, PDFDict);
    const act = a.lookup(PDFName.of('A'), PDFDict);
    const d = act.get(PDFName.of('D'));
    const ref = d?.get?.(0);
    dests.push(pages.findIndex((p) => p.ref === ref));
  }
  const s = latin1(bytes);
  return { pages: pages.length, size: pages[0].getSize(), dests, images: (s.match(/\/Subtype \/Image/g) ?? []).length, text: s };
}

const errors = [];
let browser;
try {
  await waitForServer();
  browser = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const ctx = await browser.newContext({ viewport: { width: 1500, height: 800 }, acceptDownloads: true });
  const page = await ctx.newPage();
  page.setDefaultTimeout(Number(process.env.SMOKE_TIMEOUT ?? 120000));
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', (e) => errors.push(`[pageerror] ${e.message}`));

  await page.goto(`http://127.0.0.1:${port}/?model=fzk-haus`);
  await page.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: 240000 });
  const err = await page.evaluate('window.__xrayError');
  if (err) throw new Error(`startup failed: ${err}`);
  await page.evaluate(() => {
    const app = window.__xray.app;
    window.__cinematic?.cancelFlight?.();
    app.renderer.camera.position.set(9.5, 5.5, 11.5);
    app.renderer.controls.target.set(0.5, 1.2, -0.5);
    app.renderer.controls.update();
    app.controller.settle();
  });
  await page.waitForTimeout(500);

  // ---------------------------------------------------------------- three issues: tied view + comments, closed with odd text, plain
  const made = await page.evaluate(async () => {
    const c = window.__xrayIssues.controller;
    c.markup.setAuthor('Ana Smoke');
    const els = window.__xray.app.controller.model.elements.filter((e) => e.globalId && /Wall/.test(e.ifcClass));
    const [w1, w2] = [els[0].globalId, els[1].globalId];
    const set = window.__xrayMarkup.create('Tied view');
    const m = window.__xrayMarkup.add({ kind: 'rect', fractions: { points: [[0.3, 0.3], [0.6, 0.55]], depth: 8 } });
    window.__xrayMarkup.setAttachment(m.id, 'penetration', { penetration: { mep: w1, host: w2 } });
    const g1 = await window.__xrayIssues.raise(set.id);
    c.bcf.setTopicFields(g1, { priority: 'High', assignedTo: 'Carla Builder', dueDate: '2026-03-01' });
    c.bcf.addComment(g1, 'First comment from Ana, with a comma', { author: 'Ana Smoke' });
    c.bcf.addComment(g1, 'Second comment from Ben\nwith a line break and "quotes"', { author: 'Ben Baumeister' });
    const t2 = c.bcf.createTopic({ title: 'Closed, with "quotes" and =formula', status: 'Closed', description: 'Löwenstraße: déjà vu', labels: ['a', 'b'] });
    c.bcf.addComment(t2.guid, 'Done.', { author: 'Dora' });
    const t3 = c.bcf.createTopic({ title: 'Plain open issue', status: 'Open' });
    return { g1, g2: t2.guid, g3: t3.guid, tied: window.__xrayIssues.viewSwitchAvailable(set.id) };
  });
  check('the first issue has a view tied to the model (it has the Plan/Section switch)', made.tied);
  await page.evaluate(() => { const c = window.__xrayIssues.controller; c.detail = null; c.segment = 'issues'; window.__xrayIssues.open('issues'); c.emit(); });
  await page.waitForSelector('#issues-panel [data-report]');
  check('Issues tab has the "Export report" block, collapsed', await page.evaluate(() => { const d = document.querySelector('#issues-panel [data-report]'); return !!d && d.tagName === 'DETAILS' && !d.open; }));
  await page.evaluate(() => { document.querySelector('#issues-panel [data-report]').open = true; });
  const opts = await page.evaluate(() => ({ page: document.querySelector('#issues-panel [data-field=report-page]').value, ps: document.querySelector('#issues-panel [data-field=report-plan-section]').checked, pdf: document.querySelector('#issues-panel [data-act=report-pdf]').textContent, csv: document.querySelector('#issues-panel [data-act=report-csv]').textContent }));
  check('page size A4 and Plan/Section images are on by default', opts.page === 'A4' && opts.ps === true, JSON.stringify(opts));
  check('the buttons count the issues of the list', opts.pdf === 'PDF report (3)' && opts.csv === 'CSV (3)', JSON.stringify(opts));
  await page.screenshot({ path: resolve(here, 'issue-report-panel.png') });

  // ---------------------------------------------------------------- the PDF through the API, with the view checked around it
  const before = await page.evaluate(() => {
    const r = window.__xray.app.renderer;
    return { pos: r.camera.position.toArray().map((x) => Math.round(x * 1e4) / 1e4), clip: r.getClipPlanes()?.length ?? 0, ortho: window.__xrayIssues.controller.views.mode(window.__xrayMarkup.list()[0]) };
  });
  const run = await page.evaluate(async () => {
    let freezes = 0, maxFreezeRect = null;
    const poll = setInterval(() => {
      const f = document.querySelector('[data-report-freeze]');
      if (f) { freezes++; const r = f.getBoundingClientRect(); const cv = window.__xray.app.canvas.getBoundingClientRect(); maxFreezeRect = { same: Math.abs(r.left - cv.left) < 1 && Math.abs(r.width - cv.width) < 1 && Math.abs(r.height - cv.height) < 1 }; }
    }, 20);
    const r = await window.__xrayIssueReport.pdf({ download: false });
    clearInterval(poll);
    window.__lastPdf = Array.from(r.bytes);
    return { name: r.name, issues: r.issues, pages: r.pages, images: r.images, bytes: r.bytes.length, freezes, maxFreezeRect, covered: !document.querySelector('[data-report-freeze]') };
  });
  console.log('report:', JSON.stringify(run));
  check('the report has 3 issues, a cover and a page each (4 pages)', run.issues === 3 && run.pages === 4, `${run.issues} issues, ${run.pages} pages`);
  check('a snapshot per issue, and a Plan and a Section for the tied one only', run.images.snapshot === 3 && run.images.plan === 1 && run.images.section === 1, JSON.stringify(run.images));
  check('a still copy of the canvas covered the live view while it was switched, and is gone', run.freezes > 0 && run.maxFreezeRect?.same === true && run.covered, `${run.freezes} polls`);
  const after = await page.evaluate(() => {
    const r = window.__xray.app.renderer;
    return { pos: r.camera.position.toArray().map((x) => Math.round(x * 1e4) / 1e4), clip: r.getClipPlanes()?.length ?? 0, ortho: window.__xrayIssues.controller.views.mode(window.__xrayMarkup.list()[0]) };
  });
  check('the camera, the clip planes and the view mode are as they were', JSON.stringify(before) === JSON.stringify(after), `${JSON.stringify(before)} vs ${JSON.stringify(after)}`);
  const bytes = Buffer.from(await page.evaluate(() => window.__lastPdf));
  const info = await pdfInfo(bytes);
  check('pdf-lib reads the file: 4 pages, portrait A4', info.pages === 4 && info.size.height > info.size.width && Math.abs(info.size.width - 595.28) < 0.5, JSON.stringify([info.pages, info.size]));
  check('the cover has a link to each issue page', JSON.stringify(info.dests) === JSON.stringify([1, 2, 3]), JSON.stringify(info.dests));
  check('the comments carry their authors', info.text.includes('Ana Smoke') && info.text.includes('Ben Baumeister') && info.text.includes('Dora'), '');
  check('the pictures are embedded: 3 snapshots, a Plan and a Section', info.images === 5, String(info.images));
  check('the target elements are listed with their class and GlobalId', info.text.includes('(Elements \\(') && info.text.includes('(Wall'), '');

  // ---------------------------------------------------------------- the buttons, Letter and no Plan/Section
  const dl1 = page.waitForEvent('download');
  await page.click('#issues-panel [data-act=report-pdf]');
  const d1 = await dl1;
  check('the PDF button downloads a file named after the model', /^xray-issues-fzk-haus-\d{8}-\d{4}\.pdf$/.test(d1.suggestedFilename()), d1.suggestedFilename());
  const p1 = await pdfInfo(readFileSync(await d1.path()));
  check('the downloaded PDF has Plan and Section (default options)', p1.images === 5 && p1.pages === 4, `${p1.images} images, ${p1.pages} pages`);
  await page.waitForFunction(() => !document.querySelector('[data-report-freeze]') && !window.__xrayIssueReport.options.busy);
  await page.evaluate(() => { document.querySelector('#issues-panel [data-report]').open = true; });
  await page.selectOption('#issues-panel [data-field=report-page]', 'Letter');
  await page.uncheck('#issues-panel [data-field=report-plan-section]');
  check('the options are remembered across redraws', await page.evaluate(() => { window.__xrayIssues.controller.emit(); const o = window.__xrayIssueReport.options; return o.page === 'Letter' && o.planSection === false && document.querySelector('#issues-panel [data-field=report-page]').value === 'Letter' && document.querySelector('#issues-panel [data-field=report-plan-section]').checked === false; }));
  const dl2 = page.waitForEvent('download');
  await page.click('#issues-panel [data-act=report-pdf]');
  const p2 = await pdfInfo(readFileSync(await (await dl2).path()));
  check('Letter with Plan/Section off: Letter pages and 3 pictures', Math.abs(p2.size.width - 612) < 0.5 && p2.images === 3, `${JSON.stringify(p2.size)} ${p2.images}`);

  // ---------------------------------------------------------------- the CSV follows the list
  const dl3 = page.waitForEvent('download');
  await page.click('#issues-panel [data-act=report-csv]');
  const d3 = await dl3;
  const csv = readFileSync(await d3.path(), 'utf8').replace(/^﻿/, '');
  const rows = parseCsv(csv);
  const head = rows[0];
  check('the CSV has a header and one row per issue', rows.length === 4 && head[0] === 'Number' && head.includes('Comments'), `${rows.length} rows`);
  const col = (r, n) => r[head.indexOf(n)];
  const tied = rows.find((r) => col(r, 'Priority') === 'High');
  check('Comments column holds each comment with its author, line breaks kept', !!tied && col(tied, 'Comment count') === '2' && col(tied, 'Comments').includes('Ana Smoke (') && col(tied, 'Comments').includes('Ben Baumeister (') && col(tied, 'Comments').includes('\n') && col(tied, 'Comments').includes('"quotes"'), tied ? col(tied, 'Comments') : '');
  const odd = rows.find((r) => col(r, 'Title').includes('formula'));
  check('a title that starts like a formula keeps its quotes and is guarded; unicode survives', !!odd && col(odd, 'Title') === 'Closed, with "quotes" and =formula' && col(odd, 'Description') === 'Löwenstraße: déjà vu' && col(odd, 'Labels') === 'a; b', odd ? JSON.stringify(col(odd, 'Title')) : '');
  await page.evaluate(() => window.__xrayIssues.setStatusFilter('open'));
  const open = parseCsv(await page.evaluate(() => window.__xrayIssueReport.csv({ download: false }).text));
  check('with the Open chip the CSV has the 2 open issues', open.length === 3, `${open.length - 1}`);
  await page.evaluate(() => { window.__xrayIssues.setStatusFilter('all'); window.__xrayIssues.setQuery('plain'); });
  const q = await page.evaluate(() => ({ csv: window.__xrayIssueReport.csv({ download: false }).issues, model: window.__xrayIssueReport.model().filter }));
  check('with a search the CSV and the report say so', q.csv === 1 && q.model === 'All issues, search "plain"', JSON.stringify(q));
  await page.evaluate(() => window.__xrayIssues.setQuery(''));

  check('no console errors', errors.length === 0, errors.slice(0, 4).join(' | '));
} catch (e) {
  failed = true;
  console.log('ERROR', e instanceof Error ? e.stack ?? e.message : e);
} finally {
  await browser?.close();
  vite.kill();
}
process.exit(failed ? 1 : 0);
