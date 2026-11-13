// Headless check for the Markup tool on /?model=fzk-haus:
//   - open the Issues tab (Sketches segment; the Markup drawer is gone), make a sketch from the view, draw every tool of the floating
//     drawing toolbar with the mouse (the orbit must not move), undo and redo with the keys, seed legacy comments and status through a
//     JSON import and read them back read-only (sketches have no status or comments any more), screenshots of the toolbar and the marked view;
//   - export the PDF and the JSON (downloads captured); validate the PDF with pypdf / pdfinfo / pdftoppm when present,
//     extract the embedded JSON and compare it with the reader of the viewer;
//   - reload, drop the PDF onto the page: the view and the markups come back (camera within tolerance, same markups);
//     reload again and open the JSON through the file input; drop it on another model (warning, still restored);
//   - raise a sketch as an issue (its legacy comments move to the issue); "Return to markup view" after orbiting away; phone layout with touch drawing;
//   - fails on any console error.
// Screenshots: bench/markup-drawer.png, markup-tools.png, markup-pdf-1.png ... (new files only).
// Usage: SMOKE_PORT=5710 node bench/smoke-markup.mjs
import { spawn, spawnSync } from 'node:child_process';
import { createRequire } from 'node:module';
import { mkdtempSync, mkdirSync, readFileSync, writeFileSync, existsSync, copyFileSync, statSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const port = Number(process.env.SMOKE_PORT ?? 5710);
const tmp = mkdtempSync(join(tmpdir(), 'smoke-markup-'));

function loadPlaywright() {
  const candidates = [process.env.PLAYWRIGHT_MODULE, resolve(root, 'node_modules/playwright'), '/opt/node-tools/node_modules/playwright', '/opt/node22/lib/node_modules/playwright', 'playwright'].filter(Boolean);
  for (const c of candidates) {
    try { return createRequire(import.meta.url)(c); } catch { /* next */ }
  }
  throw new Error('playwright not found; set PLAYWRIGHT_MODULE');
}
const { chromium } = loadPlaywright();

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
const sha = (b) => createHash('sha256').update(b).digest('hex');
const py = (code, ...args) => spawnSync('python3', ['-I', '-c', code, ...args], { encoding: 'utf8' });
const hasPypdf = py('import pypdf').status === 0;

const errors = [];
const keep = []; // screenshots to keep, written next to the other bench PNGs
let browser;
try {
  await waitForServer();
  browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1500, height: 780 }, acceptDownloads: true });
  const page = await ctx.newPage();
  page.setDefaultTimeout(Number(process.env.SMOKE_TIMEOUT ?? 180000));
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', (e) => errors.push(`[pageerror] ${e.message}`));

  async function boot(model = 'fzk-haus', pg = page) {
    await pg.goto(`http://127.0.0.1:${port}/?model=${model}`);
    await pg.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: 240000 });
    const err = await pg.evaluate('window.__xrayError');
    if (err) throw new Error(`startup failed: ${err}`);
  }
  const settle = (pg = page) => pg.evaluate(() => window.__xray.app.controller.settle());
  async function setCamera(pg = page) {
    await pg.evaluate(() => {
      const app = window.__xray.app;
      window.__cinematic?.cancelFlight?.();
      app.renderer.camera.position.set(9.5, 5.5, 11.5);
      app.renderer.controls.target.set(0.5, 1.2, -0.5);
      app.renderer.controls.update();
      app.controller.settle();
    });
  }
  const cam = (pg = page) => pg.evaluate(() => {
    const c = window.__xray.app.renderer.camera;
    const t = window.__xray.app.renderer.controls.target;
    return { p: [c.position.x, c.position.y, c.position.z], t: [t.x, t.y, t.z], fov: c.fov };
  });
  const dist3 = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
  async function screenOf(p, pg = page) {
    return pg.evaluate((p) => {
      const app = window.__xray.app;
      const cm = app.renderer.camera;
      cm.updateMatrixWorld();
      const v = cm.position.clone().set(p[0], p[1], p[2]).project(cm);
      const r = app.canvas.getBoundingClientRect();
      return { x: r.left + (v.x * 0.5 + 0.5) * r.width, y: r.top + (1 - (v.y * 0.5 + 0.5)) * r.height };
    }, p);
  }
  const openDrawer = (pg = page) => pg.evaluate(() => window.__xrayIssues.open('sketches'));
  const tool = (id, pg = page) => pg.click(`#markup-float [data-tool-id=${id}]`);
  async function drag(x0, y0, x1, y1, pg = page) {
    await pg.mouse.move(x0, y0);
    await pg.mouse.down();
    for (let i = 1; i <= 3; i++) await pg.mouse.move(x0 + ((x1 - x0) * i) / 3, y0 + ((y1 - y0) * i) / 3);
    await pg.mouse.up();
  }
  async function path(pts, pg = page) {
    await pg.mouse.move(pts[0][0], pts[0][1]);
    await pg.mouse.down();
    for (const p of pts.slice(1)) await pg.mouse.move(p[0], p[1]);
    await pg.mouse.up();
  }
  const count = (pg = page) => pg.evaluate(() => window.__xrayMarkup.get(window.__xrayMarkup.list().find((s) => s.active).id).markups.length);

  // ------------------------------------------------------------------ part 1: draw
  await boot();
  await setCamera();
  await page.waitForTimeout(600);
  await settle();
  // Assertion changed: the Markup tool left the tool strip; sketches live in the Issues tab and key K still opens them.
  check('markup API present, the tool left the tool strip', await page.evaluate(() => !window.__xrayToolbar.tools().includes('markup') && !!window.__xrayMarkup && !!window.__xrayIssues));
  // key K opens the Issues tab on the Sketches segment
  await page.keyboard.press('k');
  await page.waitForSelector('#issues-panel');
  check('key K opens the Issues tab on Sketches', await page.evaluate(() => window.__xrayIssues.segment === 'sketches' && window.__xrayIssues.visible));
  // The sidebar covers the left of the view: pan the model into the free part (right of the sidebar) before the sketch is made.
  await page.evaluate(() => {
    const app = window.__xray.app;
    const cm = app.renderer.camera;
    const win = app.controller.model.elements.find((e) => e.ifcClass === 'IfcWindow');
    const b = win.bounds;
    const p = cm.position.clone().set((b[0] + b[3]) / 2, (b[1] + b[4]) / 2, (b[2] + b[5]) / 2);
    cm.updateMatrixWorld();
    const ndc = p.clone().project(cm);
    const dr = document.querySelector('#sidebar').getBoundingClientRect();
    const cv = app.canvas.getBoundingClientRect();
    const wantX = (dr.right + 12 + cv.right - 260) / 2 - cv.left; // CSS px in the canvas
    const nowX = (ndc.x * 0.5 + 0.5) * cv.width;
    const dist = cm.position.distanceTo(p);
    const perPx = (2 * dist * Math.tan((cm.fov * Math.PI) / 360)) / cv.height;
    const right = new cm.position.constructor(1, 0, 0).applyQuaternion(cm.quaternion);
    right.multiplyScalar(-(wantX - nowX) * perPx);
    cm.position.add(right);
    app.renderer.controls.target.add(right);
    app.renderer.controls.update();
    app.controller.settle();
  });
  await page.waitForTimeout(400);
  await page.fill('#issues-panel [data-keep=author]', 'smoke@example.org');
  await page.dispatchEvent('#issues-panel [data-keep=author]', 'change');
  await page.click('#issues-panel [data-act=new-sketch]');
  await page.waitForFunction(() => window.__xrayMarkup.list().length === 1);
  await page.fill('#issues-panel [aria-label="Sketch title"]', 'Level 1 routing');
  await page.dispatchEvent('#issues-panel [aria-label="Sketch title"]', 'change');
  const author = await page.evaluate(() => localStorage.getItem('xray.bcf.author'));
  check('author is shared with the BCF key', author === 'smoke@example.org', String(author));
  const cam0 = await cam();

  const box = await page.evaluate(() => { const r = window.__xray.app.canvas.getBoundingClientRect(); return { x: r.left, y: r.top, w: r.width, h: r.height }; });
  // The free part of the canvas: right of the drawer, left of the parameter panel, below the top bar.
  const freeArea = await page.evaluate(() => {
    const cv = window.__xray.app.canvas.getBoundingClientRect();
    const dr = document.querySelector('#sidebar')?.getBoundingClientRect();
    const gui = document.querySelector('.lil-gui.root')?.getBoundingClientRect();
    // x0 clears the tool strip (44 px), y1 the floating drawing toolbar at the bottom centre (about 150 px with its text row).
    return { x0: Math.max(cv.left, dr ? dr.right : 0) + 60, x1: Math.min(cv.right, gui && gui.width ? gui.left : cv.right) - 12, y0: cv.top + 60, y1: cv.bottom - 200 };
  });
  console.log('free area', JSON.stringify(freeArea));
  const X0 = freeArea.x0, X1 = freeArea.x1, Y0 = freeArea.y0, Y1 = freeArea.y1;
  const info = await page.evaluate((fa) => {
    const app = window.__xray.app;
    const els = app.controller.model.elements;
    const cm = app.renderer.camera;
    cm.updateMatrixWorld();
    const cen = (e) => { const b = e.bounds; return [(b[0] + b[3]) / 2, (b[1] + b[4]) / 2, (b[2] + b[5]) / 2]; };
    const cv = app.canvas.getBoundingClientRect();
    const mid = (fa.x0 + fa.x1) / 2;
    const sx = (c) => Math.abs(cv.left + (cm.position.clone().set(c[0], c[1], c[2]).project(cm).x * 0.5 + 0.5) * cv.width - mid);
    const mk = (e) => ({ gid: e.globalId, c: cen(e) });
    // the wall that shows furthest right (clear of the drawer) and a window
    const walls = els.filter((x) => x.ifcClass === 'IfcWallStandardCase').sort((a, b) => sx(cen(a)) - sx(cen(b)));
    return { win: mk(els.find((x) => x.ifcClass === 'IfcWindow')), wall: mk(walls[0]) };
  }, freeArea);
  const cell = (i, j, n = 5, m = 3) => ({ x: X0 + ((X1 - X0) * i) / n + 8, y: Y0 + ((Y1 - Y0) * j) / m + 8, w: (X1 - X0) / n - 16, h: (Y1 - Y0) / m - 16 });

  const done = [];
  let n = 0;
  async function made(label, fn) {
    await fn();
    const now = await count();
    check(`${label} adds a markup`, now === n + 1, `count ${now}`);
    n = now;
    done.push(label);
  }
  // row 0
  let c = cell(0, 0);
  await tool('cloud'); await made('cloud (drag a box)', () => drag(c.x, c.y, c.x + c.w, c.y + c.h));
  c = cell(1, 0);
  await tool('cloudFree'); await made('cloud (draw an outline)', () => path([[c.x + c.w / 2, c.y], [c.x + c.w, c.y + c.h * 0.3], [c.x + c.w * 0.8, c.y + c.h], [c.x + c.w * 0.2, c.y + c.h], [c.x, c.y + c.h * 0.3], [c.x + c.w / 2, c.y + 2]]));
  c = cell(2, 0);
  await tool('highlightBox'); await made('highlight box', () => drag(c.x, c.y + 10, c.x + c.w, c.y + c.h - 10));
  c = cell(3, 0);
  await tool('highlight'); await made('marker highlight', () => path([[c.x, c.y + c.h / 2], [c.x + c.w * 0.3, c.y + c.h * 0.3], [c.x + c.w * 0.6, c.y + c.h * 0.7], [c.x + c.w, c.y + c.h * 0.5]]));
  c = cell(4, 0);
  await tool('rect'); await made('rectangle', () => drag(c.x, c.y, c.x + c.w, c.y + c.h));
  // row 1
  c = cell(0, 1);
  await tool('ellipse'); await made('ellipse', () => drag(c.x, c.y, c.x + c.w, c.y + c.h));
  c = cell(1, 1);
  await tool('line'); await made('line', () => drag(c.x, c.y + c.h, c.x + c.w, c.y));
  c = cell(2, 1);
  await tool('arrow'); await made('arrow', () => drag(c.x, c.y + c.h, c.x + c.w, c.y));
  c = cell(3, 1);
  await tool('polyline');
  await made('polyline (clicks, double click)', async () => {
    await page.mouse.click(c.x, c.y + c.h);
    await page.mouse.click(c.x + c.w * 0.35, c.y + 6);
    await page.mouse.click(c.x + c.w * 0.7, c.y + c.h * 0.8);
    await page.mouse.dblclick(c.x + c.w, c.y + c.h * 0.2);
  });
  c = cell(4, 1);
  await tool('polygon');
  await made('polygon (clicks, Enter)', async () => {
    await page.mouse.click(c.x, c.y + c.h * 0.8);
    await page.mouse.click(c.x + c.w * 0.2, c.y);
    await page.mouse.click(c.x + c.w, c.y + c.h * 0.2);
    await page.mouse.click(c.x + c.w * 0.8, c.y + c.h);
    await page.keyboard.press('Enter');
  });
  // row 2
  c = cell(0, 2);
  await tool('pen'); await made('pen', () => path([[c.x, c.y + c.h], [c.x + c.w * 0.25, c.y], [c.x + c.w * 0.5, c.y + c.h], [c.x + c.w * 0.75, c.y], [c.x + c.w, c.y + c.h]]));
  const win = await screenOf(info.win.c);
  await tool('callout');
  await page.fill('#markup-float [aria-label="Text for the next markup"]', 'Window reveal too small'); await made('callout on an element', () => page.mouse.click(win.x, win.y));
  const wall = await screenOf([info.wall.c[0], info.wall.c[1], info.wall.c[2]]);
  await tool('pointer');
  await page.fill('#markup-float [aria-label="Text for the next markup"]', 'Check fire rating'); await made('pointer on an element', () => page.mouse.click(wall.x, wall.y));
  c = cell(3, 2);
  await tool('text');
  await page.fill('#markup-float [aria-label="Text for the next markup"]', 'North side'); await made('text box', () => page.mouse.click(c.x + c.w / 2, c.y + c.h / 2));
  // measurement link
  await page.evaluate((cc) => { const m = window.__xrayMeasure; m.click([cc[0] - 0.4, cc[1], cc[2]], 0); m.click([cc[0] + 0.4, cc[1], cc[2]], 0); }, info.win.c);
  await tool('select');
  await page.waitForSelector('#issues-panel select[aria-label="Link a measurement"]');
  await page.selectOption('#issues-panel select[aria-label="Link a measurement"]', { index: 1 });
  await page.waitForFunction((k) => window.__xrayMarkup.get(window.__xrayMarkup.list().find((s) => s.active).id).markups.length === k, n + 1);
  n++;
  check('measurement link adds a markup', true);

  const cam1 = await cam();
  check('the orbit did not move while drawing', dist3(cam0.p, cam1.p) < 1e-6 && dist3(cam0.t, cam1.t) < 1e-6, `${dist3(cam0.p, cam1.p)}`);
  const set1 = await page.evaluate(() => window.__xrayMarkup.get(window.__xrayMarkup.list()[0].id));
  const kinds = set1.markups.map((m) => m.kind);
  check('all 15 markup kinds were made', n === 15 && new Set(kinds).size === 14 && kinds.includes('measure'), kinds.join(','));
  check('markups are numbered 1..15', set1.markups.map((m) => m.number).join() === Array.from({ length: 15 }, (_v, i) => i + 1).join());
  await settle();
  await page.waitForTimeout(500);
  const drawn = await page.evaluate(() => document.querySelectorAll('svg.xray-svg-overlay [data-mk]').length);
  check('the overlay draws every markup', drawn === 15, `drawn ${drawn}`);
  await page.mouse.move(box.x + box.w * 0.5, box.y + 4); // no help popover over the toolbar
  await page.waitForTimeout(400);
  await page.screenshot({ path: resolve(here, 'markup-tools.png') });
  keep.push('markup-tools.png');

  // select tool: click a shape selects it, drag moves it
  const firstRect = await page.evaluate(() => {
    const id = window.__xrayMarkup.get(window.__xrayMarkup.list()[0].id).markups.find((m) => m.kind === 'rect').id;
    const g = document.querySelector(`svg.xray-svg-overlay [data-mk="${id}"] [data-hit]`);
    const r = g.getBoundingClientRect();
    return { id, x: r.left + 1, y: r.top + r.height / 2, before: window.__xrayMarkup.get(window.__xrayMarkup.list()[0].id).markups.find((m) => m.id === id).shape.points };
  });
  await page.mouse.move(firstRect.x, firstRect.y);
  await page.mouse.down();
  await page.mouse.move(firstRect.x - 18, firstRect.y + 12, { steps: 4 });
  await page.mouse.up();
  const moved = await page.evaluate((id) => ({ sel: window.__xrayMarkup.selected, pts: window.__xrayMarkup.get(window.__xrayMarkup.list()[0].id).markups.find((m) => m.id === id).shape.points }), firstRect.id);
  check('select tool: a drag moves the shape and selects it', moved.sel === firstRect.id && Math.abs(moved.pts[0][0] - firstRect.before[0][0]) > 0.003, JSON.stringify(moved.pts[0]) + JSON.stringify(firstRect.before[0]));
  const cam2 = await cam();
  check('the orbit did not move while moving a markup', dist3(cam0.p, cam2.p) < 1e-6);

  // undo / redo with the keys (focus on the canvas side)
  await page.evaluate(() => document.activeElement?.blur?.());
  await page.keyboard.press('Control+z');
  const afterUndo = await page.evaluate((id) => window.__xrayMarkup.get(window.__xrayMarkup.list()[0].id).markups.find((m) => m.id === id).shape.points[0], firstRect.id);
  check('Ctrl+Z undoes the move', Math.abs(afterUndo[0] - firstRect.before[0][0]) < 1e-9);
  await page.keyboard.press('Control+Shift+Z');
  const afterRedo = await page.evaluate((id) => window.__xrayMarkup.get(window.__xrayMarkup.list()[0].id).markups.find((m) => m.id === id).shape.points[0], firstRect.id);
  check('Ctrl+Shift+Z redoes it', Math.abs(afterRedo[0] - moved.pts[0][0]) < 1e-9);
  // delete + undo
  await page.keyboard.press('Delete');
  check('Delete removes the selected markup', (await count()) === n - 1);
  await page.keyboard.press('Control+z');
  check('Ctrl+Z brings it back', (await count()) === n);
  // Escape cancels a drawing in progress
  await tool('polygon');
  await page.mouse.click(box.x + box.w * 0.6, box.y + box.h * 0.3);
  await page.mouse.click(box.x + box.w * 0.7, box.y + box.h * 0.3);
  await page.keyboard.press('Escape');
  check('Escape cancels a polygon in progress', (await page.evaluate(() => document.querySelectorAll('svg.xray-svg-overlay [data-mk-preview]').length)) === 0 && (await count()) === n);
  await page.keyboard.press('Escape');
  check('a second Escape goes back to the select tool', (await page.evaluate(() => window.__xrayMarkup.tool)) === 'select');

  // Sketches have a text per drawing and nothing else to edit: no status, assignee, due date or comment thread (those belong to an
  // issue). Assertions changed from the drawer version: edit the text in the panel, check that no review controls exist, then seed
  // legacy data the way old files carry it (a JSON with comments, a resolved status, an assignee and a due date) and read it back.
  const ids = set1.markups.map((m) => m.id);
  await page.click(`#issues-panel [data-mk-item="${ids[0]}"] .is-mk-h`);
  await page.fill(`#issues-panel [data-mk-item="${ids[0]}"] [data-field=text]`, 'Clash: duct through beam');
  check('a drawing has a text and no review controls', !!(await page.$(`#issues-panel [data-mk-item="${ids[0]}"] [data-field=text]`)) && !(await page.$('#issues-panel [data-act=status], #issues-panel [data-field=assignee], #issues-panel [data-field=due], #issues-panel [data-field=comment]')));
  check('a sketch refuses comments and keeps the status of its drawings', await page.evaluate((id) => !window.__xrayMarkup.comment(id, 'x') && window.__xrayMarkup.update(id, { status: 'resolved' }) !== undefined && window.__xrayMarkup.get(window.__xrayMarkup.list()[0].id).markups.every((m) => m.status === 'open' && m.comments.length === 0), ids[0]));
  await page.evaluate(async (ids) => {
    const m = window.__xrayMarkup;
    const sid = m.list()[0].id;
    const doc = JSON.parse(new TextDecoder().decode(m.exportJson({ ids: [sid] }).bytes));
    const ms = doc.sets[0].markups;
    ms[0].assignee = 'Ben';
    ms[0].due = '2026-12-24';
    ms[0].comments = [{ id: 'c1', author: 'smoke@example.org', date: '2026-01-02T08:00:00.000Z', text: 'Needs a sleeve (see detail 4)' }, { id: 'c2', author: 'smoke@example.org', date: '2026-01-03T08:00:00.000Z', text: 'Agreed, Ben will update the model' }];
    ms[1].status = 'resolved';
    ms[1].comments = [{ id: 'c3', author: 'smoke@example.org', date: '2026-01-04T08:00:00.000Z', text: 'Done in revision B' }];
    m.deleteSet(sid);
    await m.importJson(JSON.stringify(doc));
    void ids;
  }, ids);
  await page.waitForFunction(() => window.__xrayMarkup.list().length === 1);
  const s2 = await page.evaluate(() => window.__xrayMarkup.get(window.__xrayMarkup.list()[0].id));
  check('legacy text, assignee, due date, comments and status are kept in the data',
    s2.markups[0].text === 'Clash: duct through beam' && s2.markups[0].assignee === 'Ben' && s2.markups[0].due === '2026-12-24' && s2.markups[0].comments.length === 2 && s2.markups[0].comments[0].author === 'smoke@example.org' && s2.markups[1].status === 'resolved' && s2.markups[1].comments.length === 1);
  await page.click('#issues-panel [data-sketch]'); // the removed sketch closed the detail: open the imported one
  await page.waitForSelector('#issues-panel [data-legacy]');
  check('and show read-only on the sketch', (await page.textContent('#issues-panel [data-legacy]')).includes('Needs a sleeve') && !(await page.$('#issues-panel [data-legacy] input, #issues-panel [data-legacy] textarea')));
  await page.mouse.move(box.x + box.w * 0.5, box.y + 4);
  await page.waitForTimeout(500);
  await page.screenshot({ path: resolve(here, 'markup-drawer.png') });
  keep.push('markup-drawer.png');

  // a second set, to test several sets
  await page.evaluate(() => { const app = window.__xray.app; app.renderer.camera.position.set(-8, 6, 9); app.renderer.controls.target.set(0, 1.5, 0); app.renderer.controls.update(); app.controller.settle(); });
  await page.evaluate(() => window.__xrayIssues.newSketch()); // the sketch detail has no New sketch button; the list has
  await page.waitForFunction(() => window.__xrayMarkup.list().length === 2);
  await page.waitForTimeout(200);
  await page.click('#issues-panel [data-act=back]');
  const thumbs = await page.evaluate(() => [...document.querySelectorAll('#issues-panel .is-card img')].map((i) => i.src.startsWith('data:image/jpeg')));
  // Assertion changed: the first sketch went through the legacy-data JSON round trip above and the JSON carries no thumbnail, so it
  // lists as "no picture"; the sketch made from the view has its picture.
  check('two sketches are listed, the new one with a thumbnail', (await page.$$('#issues-panel .is-card')).length === 2 && thumbs.length >= 1 && thumbs.every(Boolean));
  await tool('cloud');
  await drag(box.x + box.w * 0.55, box.y + box.h * 0.4, box.x + box.w * 0.75, box.y + box.h * 0.6);
  check('the second sketch has its own markup', (await page.evaluate(() => window.__xrayMarkup.get(window.__xrayMarkup.list()[1].id).markups.length)) === 1 && (await page.evaluate(() => window.__xrayMarkup.get(window.__xrayMarkup.list()[0].id).markups.length)) === 15);
  // selecting sketch 1 restores its view
  await page.click(`#issues-panel [data-set="${set1.id}"]`);
  await page.waitForTimeout(1500);
  await settle();
  const camBack = await cam();
  check('selecting a sketch restores its view', dist3(camBack.p, cam0.p) < 0.05 && dist3(camBack.t, cam0.t) < 0.05, `${dist3(camBack.p, cam0.p).toFixed(4)}`);

  // away from the view: markups stay on their plane in 3D, the "Return to markup view" button shows
  const before = await page.evaluate(() => document.querySelector('#markup-return').style.display);
  await page.evaluate(() => { const app = window.__xray.app; app.renderer.camera.position.set(14, 8, 3); app.renderer.controls.update(); app.controller.settle(); });
  await page.waitForTimeout(500);
  const away = await page.evaluate(() => ({ away: window.__xrayMarkup.away, chip: document.querySelector('#markup-return').style.display, drawn: document.querySelectorAll('svg.xray-svg-overlay [data-mk]').length }));
  check('away from the view the button shows and the markups still draw', before === 'none' && away.away && away.chip !== 'none' && away.drawn === 15, JSON.stringify(away));
  await page.screenshot({ path: resolve(here, 'markup-away.png') });
  keep.push('markup-away.png');
  await page.click('#markup-return');
  await page.waitForTimeout(1500);
  const camRet = await cam();
  check('Return to markup view brings the camera back', dist3(camRet.p, cam0.p) < 0.05, `${dist3(camRet.p, cam0.p).toFixed(4)}`);

  // ------------------------------------------------------------------ part 2: export
  const [pdfDl] = await Promise.all([page.waitForEvent('download'), page.click('#issues-panel >> text=Export PDF')]);
  const pdfPath = join(tmp, 'set1.pdf');
  await pdfDl.saveAs(pdfPath);
  const [jsonDl] = await Promise.all([page.waitForEvent('download'), page.click('#issues-panel >> text=Export JSON')]);
  const jsonPath = join(tmp, 'set1.json');
  await jsonDl.saveAs(jsonPath);
  check('download names', /^xray-markup-fzk-haus-Level_1_routing-\d{8}-\d{4}\.pdf$/.test(pdfDl.suggestedFilename()) && /\.json$/.test(jsonDl.suggestedFilename()), `${pdfDl.suggestedFilename()} ${jsonDl.suggestedFilename()}`);
  const pdf = readFileSync(pdfPath);
  const jsonText = readFileSync(jsonPath, 'utf8');
  check('PDF header and size', pdf.slice(0, 8).toString() === '%PDF-1.7' && pdf.length > 20000, `${(pdf.length / 1024).toFixed(0)} KB`);
  const doc = JSON.parse(jsonText);
  check('JSON document', doc.schema === 'xray-markup-set/1' && doc.sets.length === 1 && doc.sets[0].markups.length === 15 && doc.model.name === 'fzk-haus' && /^[0-9a-f]{16}$/.test(doc.model.guidHash) && typeof doc.instructions === 'string' && doc.instructions.includes('drop'), `${doc.model.name} ${doc.model.elementCount} ${doc.model.guidHash}`);
  check('JSON anchors are in the IFC frame with GlobalIds', doc.sets[0].markups.some((m) => m.anchor?.elementGuid && m.anchor.local) && doc.sets[0].markups.every((m) => m.shape || m.anchor));
  check('JSON has no thumbnail and no secrets', !jsonText.includes('data:image') && !/api[_-]?key|token|password|secret/i.test(jsonText));
  // PDF validation
  if (spawnSync('pdfinfo', [pdfPath]).status === 0) {
    const r = spawnSync('pdfinfo', [pdfPath], { encoding: 'utf8' });
    check('pdfinfo reads the PDF (3 pages, A4 landscape)', /Pages:\s+3/.test(r.stdout) && /Page size:\s+841\.89 x 595\.28/.test(r.stdout), r.stdout.split('\n').filter((l) => /Pages|Page size|Title/.test(l)).join(' | '));
    for (const p of [1, 2, 3]) {
      spawnSync('pdftoppm', ['-png', '-r', '80', '-f', String(p), '-l', String(p), '-singlefile', pdfPath, join(tmp, `page${p}`)]);
      if (existsSync(join(tmp, `page${p}.png`))) { copyFileSync(join(tmp, `page${p}.png`), resolve(here, `markup-pdf-${p}.png`)); keep.push(`markup-pdf-${p}.png`); }
    }
    check('pdftoppm renders the pages', [1, 2, 3].every((p) => existsSync(join(tmp, `page${p}.png`))));
  } else console.log('SKIP pdfinfo / pdftoppm not installed');
  if (hasPypdf) {
    const script = `
import sys, hashlib, json
from pypdf import PdfReader
r = PdfReader(sys.argv[1])
print('pages', len(r.pages))
txt = ' '.join((p.extract_text() or '') for p in r.pages)
print('text-ok', all(s in txt for s in ['fzk-haus', 'Level 1 routing', 'How to get back to this view', 'Clash: duct through beam', 'Needs a sleeve', 'Resolved', 'smoke@example.org']))
print('images', sum(len(p.images) for p in r.pages))
files = r.attachments
print('attachments', ','.join(files.keys()))
for k, v in files.items():
    data = v[0]
    open(sys.argv[2], 'wb').write(data)
    print('sha', hashlib.sha256(data).hexdigest())
print('meta-title', r.metadata.title)
print('uri', sum(1 for p in r.pages for a in (p.get('/Annots') or []) if '/URI' in (a.get_object().get('/A') or {})))
`;
    const r = py(script, pdfPath, join(tmp, 'extracted.json'));
    const out = Object.fromEntries(r.stdout.trim().split('\n').map((l) => [l.split(' ')[0], l.split(' ').slice(1).join(' ')]));
    check('pypdf opens the PDF: 3 pages, 2 images, text found', r.status === 0 && out.pages === '3' && out.images === '2' && out['text-ok'] === 'True', r.stderr.slice(0, 200) + JSON.stringify(out));
    check('pypdf lists the attachment', /xray-markup-fzk-haus.*\.json/.test(out.attachments ?? ''), out.attachments);
    const extracted = existsSync(join(tmp, 'extracted.json')) ? readFileSync(join(tmp, 'extracted.json')) : Buffer.alloc(0);
    const viaViewer = await page.evaluate(async (b64) => {
      const { extractAttachments } = await import('/src/markup/pdf.ts');
      const bin = atob(b64); const u = new Uint8Array(bin.length); for (let i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i);
      const f = await extractAttachments(u);
      const h = await crypto.subtle.digest('SHA-256', f[0].data);
      return Array.from(new Uint8Array(h), (x) => x.toString(16).padStart(2, '0')).join('');
    }, pdf.toString('base64'));
    check('the embedded file extracts byte-identical with pypdf and with the viewer reader', sha(extracted) === out.sha && out.sha === viaViewer && extracted.length > 1000, `${sha(extracted).slice(0, 12)} ${viaViewer.slice(0, 12)}`);
    const emb = JSON.parse(extracted.toString('utf8'));
    check('the embedded JSON is the markup set of the PDF', emb.sets.length === 1 && emb.sets[0].id === doc.sets[0].id && emb.sets[0].markups.length === 15 && emb.model.guidHash === doc.model.guidHash);
  } else console.log('SKIP pypdf not installed');
  // Letter size and all sets
  const letter = await page.evaluate(async () => {
    const f = await window.__xrayMarkup.exportPdf({ page: 'Letter' });
    let s = ''; for (let i = 0; i < f.bytes.length; i += 0x8000) s += String.fromCharCode(...f.bytes.subarray(i, i + 0x8000));
    return { n: f.bytes.length, name: f.name, letter: /\/MediaBox \[0 0 792 612\]/.test(s) };
  });
  check('all sets in one PDF, Letter landscape', letter.letter && /2-sets/.test(letter.name) && letter.n > 20000, JSON.stringify(letter));
  // ---- picture resolution: the embedded JPEG width follows the setting; burned markups line up with the screen
  const css = await page.evaluate(() => ({ w: window.__xray.app.canvas.clientWidth, h: window.__xray.app.canvas.clientHeight, cw: window.__xray.app.canvas.width }));
  const want = await page.evaluate(async ({ w, h }) => {
    const { pictureWidthFor } = await import('/src/markup/report.ts');
    return { 150: pictureWidthFor('A4', w, h, 150), 200: pictureWidthFor('A4', w, h, 200), 300: pictureWidthFor('A4', w, h, 300) };
  }, css);
  const imgSizes = (file) => {
    const r = py(`
import sys
from pypdf import PdfReader
r = PdfReader(sys.argv[1])
print(' '.join('%dx%d' % (p.images[i].image.size) for p in r.pages for i in range(len(p.images))))
`, file);
    return r.stdout.trim().split(' ').filter(Boolean).map((t) => t.split('x').map(Number));
  };
  const resRuns = {};
  for (const res of ['screen', 150, 300]) {
    const t0 = Date.now();
    const out = await page.evaluate(async (res) => {
      const f = await window.__xrayMarkup.exportPdf({ resolution: res, ids: [window.__xrayMarkup.list()[0].id] });
      let bin = ''; for (let i = 0; i < f.bytes.length; i += 0x8000) bin += String.fromCharCode(...f.bytes.subarray(i, i + 0x8000));
      return { b64: btoa(bin), info: f.info, status: window.__xrayMarkup.status };
    }, res);
    const file = join(tmp, `res-${res}.pdf`);
    writeFileSync(file, Buffer.from(out.b64, 'base64'));
    resRuns[res] = { file, info: out.info, size: statSync(file).size, wall: Date.now() - t0, sizes: hasPypdf ? imgSizes(file) : [] };
    console.log(`    ${res}: ${JSON.stringify(out.info)} file ${(resRuns[res].size / 1024).toFixed(0)} KB, images ${JSON.stringify(resRuns[res].sizes)}`);
  }
  const pdf200 = { sizes: hasPypdf ? imgSizes(pdfPath) : [], size: pdf.length };
  console.log(`    200: file ${(pdf200.size / 1024).toFixed(0)} KB, images ${JSON.stringify(pdf200.sizes)}`);
  if (hasPypdf) {
    check('screen resolution: pictures are the canvas size', resRuns.screen.sizes.every(([w]) => w === css.cw), JSON.stringify(resRuns.screen.sizes));
    check('150 dpi: embedded JPEG width matches the setting', resRuns[150].sizes.every(([w]) => Math.abs(w - want[150]) <= 2) && resRuns[150].info.pictureWidth === resRuns[150].sizes[0][0], `${JSON.stringify(resRuns[150].sizes)} want ${want[150]}`);
    check('200 dpi (default): embedded JPEG width matches the setting', pdf200.sizes.every(([w]) => Math.abs(w - want[200]) <= 2), `${JSON.stringify(pdf200.sizes)} want ${want[200]}`);
    check('300 dpi: embedded JPEG width matches the setting (or the GPU limit is said)', resRuns[300].sizes.every(([w]) => Math.abs(w - want[300]) <= 2) || (resRuns[300].info.note && resRuns[300].sizes[0][0] === resRuns[300].info.pictureWidth), `${JSON.stringify(resRuns[300].sizes)} want ${want[300]} note ${resRuns[300].info.note}`);
    check('the pictures grow with the resolution and the file stays small', resRuns[300].sizes[0][0] > pdf200.sizes[0][0] && pdf200.sizes[0][0] > resRuns[150].sizes[0][0] && resRuns[150].sizes[0][0] > resRuns.screen.sizes[0][0] * 0.99, `${(resRuns[300].size / 1048576).toFixed(2)} MB at 300 dpi`);
    // alignment: the highlight box in page 2 (diff to page 1) against its screen box scaled to the picture
    const hb = await page.evaluate(() => {
      const set = window.__xrayMarkup.get(window.__xrayMarkup.list()[0].id);
      const m = set.markups.find((x) => x.kind === 'highlightBox');
      const el = document.querySelector(`svg.xray-svg-overlay [data-mk="${m.id}"] [data-role=shape]`);
      const r = el.getBoundingClientRect();
      const c = window.__xray.app.canvas.getBoundingClientRect();
      return { x: r.left - c.left, y: r.top - c.top, w: r.width, h: r.height, cw: c.width, ch: c.height };
    });
    const al = py(`
import sys, json, io
from pypdf import PdfReader
import numpy as np
box = json.loads(sys.argv[2])
r = PdfReader(sys.argv[1])
a = np.asarray(r.pages[0].images[0].image.convert('RGB')).astype(int)
b = np.asarray(r.pages[1].images[0].image.convert('RGB')).astype(int)
H, W = a.shape[:2]
k = W / box['cw']
d = (np.abs(a - b).sum(axis=2) > 40)
x0, y0, x1, y1 = [int(round(v * k)) for v in (box['x'], box['y'], box['x'] + box['w'], box['y'] + box['h'])]
inner = d[y0 + 6:y1 - 6, x0 + 6:x1 - 6].mean()
ym0, ym1 = y0 + (y1 - y0) // 4, y1 - (y1 - y0) // 4
left = d[ym0:ym1, max(0, x0 - int(12 * k)):max(1, x0 - int(4 * k))].mean()
right = d[ym0:ym1, min(W - 1, x1 + int(4 * k)):min(W, x1 + int(12 * k))].mean()
print(json.dumps({'k': k, 'inner': float(inner), 'left': float(left), 'right': float(right), 'box': [x0, y0, x1, y1]}))
`, pdfPath, JSON.stringify(hb));
    let alj = {};
    try { alj = JSON.parse(al.stdout.trim()); } catch { /* reported below */ }
    check('burned markups line up with the screen (highlight box position scaled to the picture)', alj.inner > 0.85 && alj.left < 0.2 && alj.right < 0.2 && alj.k > 1.2, JSON.stringify(alj) + al.stderr.slice(0, 200));
  }
  const stillSet1 = await page.evaluate(() => window.__xrayMarkup.list().filter((s) => s.active).length);
  check('exporting leaves the view and the active set as they were', stillSet1 === 1);

  // ------------------------------------------------------------------ part 3: reload, drop the PDF
  const stateBefore = { set: set1, cam: cam0 };
  await boot();
  check('after reload there are no sets', (await page.evaluate(() => window.__xrayMarkup.list().length)) === 0);
  const dropFile = (name, b64, type) => page.evaluate(async ({ name, b64, type }) => {
    const bin = atob(b64); const u = new Uint8Array(bin.length); for (let i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i);
    const dt = new DataTransfer();
    dt.items.add(new File([u], name, { type }));
    document.body.dispatchEvent(new DragEvent('drop', { dataTransfer: dt, bubbles: true, cancelable: true }));
  }, { name, b64, type });
  await dropFile('markup.pdf', pdf.toString('base64'), 'application/pdf');
  await page.waitForFunction(() => window.__xrayMarkup.list().length === 1, null, { timeout: 30000 });
  await page.waitForTimeout(1200);
  await settle();
  const back = await page.evaluate(() => ({ set: window.__xrayMarkup.get(window.__xrayMarkup.list()[0].id), status: window.__xrayMarkup.status, drawn: document.querySelectorAll('svg.xray-svg-overlay [data-mk]').length }));
  const camAfter = await cam();
  check('dropping the PDF restores the view (camera within tolerance)', dist3(camAfter.p, cam0.p) < 0.01 && dist3(camAfter.t, cam0.t) < 0.01 && Math.abs(camAfter.fov - cam0.fov) < 1e-6, `${dist3(camAfter.p, cam0.p).toFixed(5)}`);
  check('dropping the PDF restores all markups at the same positions', back.set.markups.length === 15 && JSON.stringify(back.set.markups.map((m) => m.shape ?? m.anchor)) === JSON.stringify(s2.markups.map((m) => m.shape ?? m.anchor)), `${back.set.markups.length}`);
  check('legacy comments, status, assignee and numbers survive', back.set.markups[0].comments.length === 2 && back.set.markups[1].status === 'resolved' && back.set.markups[0].assignee === 'Ben' && back.set.markups.map((m) => m.number).join() === s2.markups.map((m) => m.number).join());
  check('the restored markups are drawn', back.drawn === 15, `drawn ${back.drawn}`);
  check('no warning for the same model', !/warning/i.test(back.status), back.status);
  await page.screenshot({ path: resolve(here, 'markup-restored.png') });
  keep.push('markup-restored.png');
  // pixel positions of the restored overlay against the drawn one: compare bounding boxes of the shapes by id
  // (the camera is the same, so the same pixels)

  // reload again: open the JSON through the file input
  await boot();
  await page.setInputFiles('input[data-markup=open]', jsonPath);
  await page.waitForFunction(() => window.__xrayMarkup.list().length === 1, null, { timeout: 30000 });
  const viaJson = await page.evaluate(() => window.__xrayMarkup.get(window.__xrayMarkup.list()[0].id).markups.length);
  check('opening the JSON restores the markups', viaJson === 15);

  // another model: a warning, and the set is kept but hidden under "Other models" (markup scope: it does not belong to this model)
  await boot('synth5k');
  await dropFile('markup.json', Buffer.from(jsonText).toString('base64'), 'application/json');
  await page.waitForFunction(() => window.__xrayMarkup.list({ all: true }).length === 1, null, { timeout: 30000 });
  const other = await page.evaluate(() => ({ status: window.__xrayMarkup.status, n: window.__xrayMarkup.get(window.__xrayMarkup.list({ all: true })[0].id).markups.length, cur: window.__xrayMarkup.list().length, others: window.__xrayMarkup.otherModels().length, drawn: document.querySelectorAll('svg.xray-svg-overlay [data-mk]').length }));
  check('a different model: warning, markups kept under Other models and not drawn', /different|not in this model|Warning/i.test(other.status) && other.n === 15 && other.cur === 0 && other.others === 1 && other.drawn === 0, other.status.slice(0, 160));
  const rep = await page.evaluate(async (t) => (await window.__xrayMarkup.importJson(t)), jsonText);
  check('the import report counts unknown GlobalIds and flags the model', rep.ok && rep.match === 'different' && rep.unknownGuids > 0 && rep.replaced === 1 && rep.warnings.length >= 2, JSON.stringify({ m: rep.match, u: rep.unknownGuids, w: rep.warnings.length }));
  const bad = await page.evaluate(async () => (await window.__xrayMarkup.importJson('{"schema":"xray-markup-set/2","sets":[]}')));
  check('a newer version is refused with a message', !bad.ok && /version 2/.test(bad.error));
  const badPdf = await page.evaluate(async () => (await window.__xrayMarkup.importFile(new File([new TextEncoder().encode('%PDF-1.4\n1 0 obj\n<< >>\nendobj\n%%EOF\n')], 'plain.pdf'))));
  check('a PDF without markup data is refused', !badPdf.ok && /does not carry markup/.test(badPdf.error));

  // ------------------------------------------------------------------ part 4: convert to BCF, phone
  await boot();
  await setCamera();
  await page.waitForTimeout(500);
  await page.setInputFiles('input[data-markup=open]', jsonPath);
  await page.waitForFunction(() => window.__xrayMarkup.list().length === 1, null, { timeout: 30000 });
  await openDrawer();
  await page.click('#issues-panel [data-sketch]'); // the detail of the only sketch (and its view comes back)
  await page.waitForTimeout(2000);
  // ---- Update view: capture again from another camera; shapes stay on the model; undo brings the old view back
  const uv = await page.evaluate(() => {
    const m = window.__xrayMarkup;
    const set = m.get(m.list()[0].id);
    const rect = set.markups.find((x) => x.kind === 'rect');
    const bb = () => { const r = document.querySelector(`svg.xray-svg-overlay [data-mk="${rect.id}"] [data-role=shape]`).getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom]; };
    const app = window.__xray.app;
    app.renderer.camera.position.set(14, 9, 4);
    app.renderer.controls.update();
    app.controller.settle();
    return { id: set.id, rect: rect.id, anchors: set.markups.filter((x) => x.anchor).map((x) => x.anchor), pts: rect.shape.points, cam: set.camera, before: bb() };
  });
  await page.waitForTimeout(800);
  // A view-locked shape seen from a camera far from its own is a pin at its centroid (markup attachments): then the pin tip is
  // the place on the model to compare with; an attached or near shape is compared by its whole box, as before.
  const bbBefore = await page.evaluate((id) => {
    const svg = document.querySelector('svg.xray-svg-overlay').getBoundingClientRect();
    const sh = document.querySelector(`svg.xray-svg-overlay [data-mk="${id}"] [data-role=shape]`);
    if (sh) { const r = sh.getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom]; }
    const pin = document.querySelector(`svg.xray-svg-overlay [data-mk="${id}"] polygon[data-role=pin]`);
    const n = pin.getAttribute('points').split(' ').map(Number);
    return { pin: [svg.left + n[0], svg.top + n[1]] };
  }, uv.rect);
  // Ctrl+Z undoes it while the sketch is being edited (the toolbar is up): the markup history owns the keys then, not the global stack.
  await page.click('#issues-panel [data-act=edit-drawing]');
  await page.click('#issues-panel >> text=Update view');
  await page.waitForTimeout(800);
  const upd = await page.evaluate((u) => {
    const m = window.__xrayMarkup;
    const set = m.get(u.id);
    const rect = set.markups.find((x) => x.id === u.rect);
    const el = document.querySelector(`svg.xray-svg-overlay [data-mk="${u.rect}"] [data-role=shape]`).getBoundingClientRect();
    return { cam: set.camera, pts: rect.shape.points, anchors: set.markups.filter((x) => x.anchor).map((x) => x.anchor), bb: [el.left, el.top, el.right, el.bottom], status: m.status, away: m.away, vcam: set.view.camera.position };
  }, uv);
  check('Update view re-captures the camera of the set', Math.abs(upd.cam.position[0] - uv.cam.position[0]) > 0.5 && /updated/.test(upd.status) && !upd.away, upd.status);
  check('Update view keeps the 3D anchors', JSON.stringify(upd.anchors) === JSON.stringify(uv.anchors));
  const sameSpot = Array.isArray(bbBefore)
    ? bbBefore.every((v, i) => Math.abs(v - upd.bb[i]) < 2.5)
    : Math.hypot(bbBefore.pin[0] - (upd.bb[0] + upd.bb[2]) / 2, bbBefore.pin[1] - (upd.bb[1] + upd.bb[3]) / 2) < 12;
  check('Update view keeps shapes on the model: same place on screen, new fractions', sameSpot && JSON.stringify(upd.pts) !== JSON.stringify(uv.pts), `${JSON.stringify(bbBefore)} vs ${JSON.stringify(upd.bb.map(Math.round))}`);
  await page.evaluate(() => document.activeElement?.blur?.());
  await page.keyboard.press('Control+z');
  const undone = await page.evaluate((u) => { const set = window.__xrayMarkup.get(u.id); return { cam: set.camera.position, pts: set.markups.find((x) => x.id === u.rect).shape.points }; }, uv);
  check('Ctrl+Z undoes Update view (old camera and old shape points)', JSON.stringify(undone.cam) === JSON.stringify(uv.cam.position) && JSON.stringify(undone.pts) === JSON.stringify(uv.pts));
  await page.keyboard.press('Control+Shift+Z');
  const redone = await page.evaluate((u) => window.__xrayMarkup.get(u.id).camera.position, uv);
  check('Ctrl+Shift+Z redoes it', JSON.stringify(redone) === JSON.stringify(upd.cam.position));
  const scr = await page.evaluate((u) => {
    const m = window.__xrayMarkup;
    const app = window.__xray.app;
    app.renderer.camera.position.set(8, 3, 12); app.renderer.controls.update(); app.controller.settle();
    const before = m.get(u.id).markups.find((x) => x.id === u.rect).shape.points;
    const r = m.updateView(u.id, { keep: 'screen' });
    return { r, same: JSON.stringify(before) === JSON.stringify(m.get(u.id).markups.find((x) => x.id === u.rect).shape.points) };
  }, uv);
  check('Update view with "stay on the screen" keeps the shape fractions', scr.same && scr.r.moved === 0 && scr.r.shapes >= 10, JSON.stringify(scr));
  await page.evaluate((u) => window.__xrayMarkup.restore(u.id, { animate: false }), uv);
  await page.click('#issues-panel [data-act=raise]');
  await page.waitForFunction(() => window.__xrayBcf.topics.length === 1, null, { timeout: 30000 });
  const bcf = await page.evaluate(() => {
    const t = window.__xrayBcf.topics[0];
    const anns = window.__xrayBcf.annotations(t.guid);
    const list = Object.values(anns).flat();
    return { title: t.title, vps: t.viewpoints.length, snap: !!t.viewpoints[0].snapshot, types: list.map((a) => a.type), comments: t.comments.length, status: t.topicStatus };
  });
  // Assertion changed: Raise as issue links the viewpoint to the sketch (the drawing is projected from it) and moves the legacy comments.
  check('Raise as issue: viewpoint, snapshot, drawing as annotations, legacy comments moved', bcf.title === 'Level 1 routing' && bcf.vps === 1 && bcf.snap && bcf.types.length >= 14 && bcf.types.includes('freehand') && bcf.types.includes('callout') && bcf.comments >= 3 && bcf.status === 'Open', JSON.stringify(bcf));
  // Assertion changed: the single-markup conversion is gone (an issue is made of a sketch). Raising the same sketch again is refused.
  const again = await page.evaluate(async () => { try { await window.__xrayMarkup.toBcf(window.__xrayMarkup.list()[0].id); return 'no error'; } catch (e) { return e.message; } });
  check('a sketch belongs to at most one issue: raising it again is refused', /already belongs to the issue/.test(again) && (await page.evaluate(() => window.__xrayBcf.topics.length)) === 1, again);
  check('the link shows from both sides', await page.evaluate(() => { const t = window.__xrayBcf.topics[0]; const sid = window.__xrayMarkup.list()[0].id; return t.viewpoints[0].sketchId === sid && window.__xrayMarkup.get(sid).issue?.topic === t.guid; }));

  // phone layout with touch drawing
  const phone = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true, acceptDownloads: true });
  const pp = await phone.newPage();
  pp.setDefaultTimeout(180000);
  pp.on('console', (m) => { if (m.type() === 'error') errors.push(`[phone] ${m.text()}`); });
  pp.on('pageerror', (e) => errors.push(`[phone pageerror] ${e.message}`));
  await boot('fzk-haus', pp);
  await setCamera(pp);
  await pp.waitForTimeout(600);
  await openDrawer(pp);
  await pp.waitForSelector('#issues-sheet.on');
  await pp.waitForTimeout(300);
  await pp.screenshot({ path: resolve(here, 'markup-phone-drawer.png') });
  keep.push('markup-phone-drawer.png');
  const noScroll = await pp.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1);
  check('phone: no horizontal page scroll with the sheet open', noScroll);
  const dr = await pp.evaluate(() => { const r = document.querySelector('#issues-panel').getBoundingClientRect(); return { w: r.width, vw: window.innerWidth, over: [...document.querySelectorAll('#issues-panel *')].filter((e) => e.getBoundingClientRect().right > window.innerWidth + 1).length }; });
  check('phone: the sheet content fits the screen', dr.over === 0, JSON.stringify(dr));
  await pp.click('#issues-panel [data-act=new-sketch]');
  await pp.waitForFunction(() => window.__xrayMarkup.list().length === 1);
  await pp.waitForTimeout(300);
  // New sketch starts editing: on a phone the sheet steps aside and the floating bar shows (it used to be: choosing a tool closed the drawer)
  await tool('cloud', pp);
  await pp.waitForTimeout(600);
  check('phone: drawing hides the sheet and shows the floating bar', (await pp.evaluate(() => !document.querySelector('#issues-sheet').classList.contains('on') && getComputedStyle(document.querySelector('#markup-float')).display !== 'none')));
  await pp.screenshot({ path: resolve(here, 'markup-phone-float.png') });
  keep.push('markup-phone-float.png');
  const cdp = await phone.newCDPSession(pp);
  const touch = async (type, x, y) => cdp.send('Input.dispatchTouchEvent', { type, touchPoints: type === 'touchEnd' ? [] : [{ x, y, id: 1 }] });
  const pbox = await pp.evaluate(() => { const r = window.__xray.app.canvas.getBoundingClientRect(); return { x: r.left, y: r.top, w: r.width, h: r.height }; });
  const camP0 = await cam(pp);
  const x0 = pbox.x + pbox.w * 0.2, y0 = pbox.y + pbox.h * 0.15, x1 = pbox.x + pbox.w * 0.8, y1 = pbox.y + pbox.h * 0.35;
  await touch('touchStart', x0, y0);
  for (let i = 1; i <= 8; i++) await touch('touchMove', x0 + ((x1 - x0) * i) / 8, y0 + ((y1 - y0) * i) / 8);
  await touch('touchEnd');
  await pp.waitForFunction(() => window.__xrayMarkup.get(window.__xrayMarkup.list()[0].id).markups.length === 1, null, { timeout: 5000 }).catch(() => undefined);
  const touchN = await pp.evaluate(() => window.__xrayMarkup.get(window.__xrayMarkup.list()[0].id).markups.length);
  const camP1 = await cam(pp);
  check('phone: a finger drag draws a cloud and does not orbit', touchN === 1 && dist3(camP0.p, camP1.p) < 1e-6, `n ${touchN}`);
  // pen input (pointer events with pointerType pen)
  await pp.evaluate(() => {
    const cv = window.__xray.app.canvas; const r = cv.getBoundingClientRect();
    const mk = (type, x, y) => cv.dispatchEvent(new PointerEvent(type, { pointerId: 7, pointerType: 'pen', isPrimary: true, button: 0, buttons: type === 'pointerup' ? 0 : 1, clientX: r.left + x, clientY: r.top + y, bubbles: true, cancelable: true }));
    window.__xrayMarkup.setTool('rect');
    mk('pointerdown', r.width * 0.3, r.height * 0.5);
    for (let i = 1; i <= 6; i++) window.dispatchEvent(new PointerEvent('pointermove', { pointerId: 7, pointerType: 'pen', isPrimary: true, buttons: 1, clientX: r.left + r.width * 0.3 + i * 18, clientY: r.top + r.height * 0.5 + i * 10, bubbles: true }));
    window.dispatchEvent(new PointerEvent('pointerup', { pointerId: 7, pointerType: 'pen', isPrimary: true, button: 0, buttons: 0, clientX: r.left + r.width * 0.3 + 108, clientY: r.top + r.height * 0.5 + 60, bubbles: true }));
  });
  check('phone: pen input draws a rectangle', (await pp.evaluate(() => window.__xrayMarkup.get(window.__xrayMarkup.list()[0].id).markups.length)) === 2);
  await pp.waitForTimeout(300);
  await pp.screenshot({ path: resolve(here, 'markup-phone-marked.png') });
  keep.push('markup-phone-marked.png');
  await phone.close();

  check('no console errors', errors.length === 0, errors.slice(0, 4).join(' | '));
  console.log('new screenshots:', keep.map((k) => `bench/${k}`).join(' '));
} catch (e) {
  failed = true;
  console.log('ERROR', e instanceof Error ? e.stack ?? e.message : e);
} finally {
  await browser?.close();
  vite.kill();
}
process.exit(failed ? 1 : 0);
