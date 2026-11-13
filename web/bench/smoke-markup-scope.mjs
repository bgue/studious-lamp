// Headless check that markups and BCF topics belong to the model they were made on (see docs-features/markup.md and bcf.md,
// "Which model an item belongs to"):
//   - on sample A (fzk-haus) a markup set (a cloud, a rectangle, a callout) and a BCF topic (pin, rectangle) are drawn;
//   - the surface outlines carry the normal and the bounds of their target (what the re-projection of a revision needs);
//   - on sample B (building) the overlay has no old pin, shape or annotation; the lists are empty and the panels say
//     "Other models (n)" (the Sketches and Issues segments of the Issues tab; the drawers are gone), naming the model;
//     (the topic's rectangle is a viewpoint drawing, so it is a sketch linked to the issue: the Sketches segment counts 2, the Issues segment 1)
//   - back on A they are drawn again; on B once more, Move to this model re-binds the set and the topic (detached targets show view-locked);
//   - a different IFC opened through the file loader does the same (the sets of the sample are hidden);
//   - an exported markup file made on A, opened on B, says so and lists its set under Other models;
//   - zero console errors.
// Usage: SMOKE_PORT=5707 node bench/smoke-markup-scope.mjs
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const port = Number(process.env.SMOKE_PORT ?? 5707);

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

const errors = [];
let browser;
try {
  await waitForServer();
  browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1500, height: 780 }, acceptDownloads: true });
  const page = await ctx.newPage();
  page.setDefaultTimeout(Number(process.env.SMOKE_TIMEOUT ?? 180000));
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', (e) => errors.push(`[pageerror] ${e.message}`));

  await page.goto(`http://127.0.0.1:${port}/?model=fzk-haus`);
  await page.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: 240000 });
  const startErr = await page.evaluate('window.__xrayError');
  if (startErr) throw new Error(`startup failed: ${startErr}`);

  const settle = () => page.evaluate(() => window.__xray.app.controller.settle());
  async function switchTo(name) {
    await page.evaluate((n) => window.__xray.app.loadScene(n), name);
    await page.waitForFunction((n) => window.__xray.app.modelName === n && !!window.__xray.app.loaded, name);
    await settle();
    await page.waitForTimeout(500);
  }
  /** Counts of what the overlay draws: markup shapes and anchors, BCF pins and annotations. */
  const overlay = () => page.evaluate(() => ({
    mk: document.querySelectorAll('[data-mk]').length,
    pin: document.querySelectorAll('[data-bcf-pin]').length,
    ann: document.querySelectorAll('[data-bcf-ann]').length,
  }));
  const drawn = (o) => o.mk + o.pin + o.ann;

  // The free part of the canvas: right of the sidebar.
  await page.keyboard.press('k');
  await page.waitForSelector('#issues-panel');
  await page.fill('#issues-panel [data-keep=author]', 'smoke@example.org');
  await page.dispatchEvent('#issues-panel [data-keep=author]', 'change');
  const box = await page.evaluate(() => {
    const cv = window.__xray.app.canvas.getBoundingClientRect();
    const dr = document.querySelector('#sidebar')?.getBoundingClientRect();
    return { x0: Math.max(cv.left, dr ? dr.right : 0) + 40, x1: cv.right - 300, y0: cv.top + 120, y1: cv.bottom - 120, ox: cv.left, oy: cv.top };
  });
  // Frame the model from the front so that the shapes land on elements.
  const wall = await page.evaluate(() => {
    const els = window.__xray.app.controller.model.elements;
    const w = els.filter((e) => e.ifcClass === 'IfcWallStandardCase' && e.globalId).sort((a, b) => ((b.bounds[3] - b.bounds[0]) * (b.bounds[4] - b.bounds[1])) - ((a.bounds[3] - a.bounds[0]) * (a.bounds[4] - a.bounds[1])))[0];
    const b = w.bounds;
    return { guid: w.globalId, c: [(b[0] + b[3]) / 2, (b[1] + b[4]) / 2, (b[2] + b[5]) / 2], size: [b[3] - b[0], b[4] - b[1], b[5] - b[2]] };
  });
  const along = wall.size[0] > wall.size[2] ? [0, 0, 1] : [1, 0, 0];
  await page.evaluate(([pos, target]) => {
    const app = window.__xray.app;
    window.__cinematic?.cancelFlight?.();
    app.renderer.camera.position.set(...pos);
    app.renderer.controls.target.set(...target);
    app.renderer.controls.update();
    app.controller.settle();
  }, [[wall.c[0] + along[0] * 12 + 3, wall.c[1] + 2, wall.c[2] + along[2] * 12 + 3], wall.c]);
  await page.waitForTimeout(400);

  // ---------------------------------------------------------------- items on A
  const cx = (box.x0 + box.x1) / 2, cy = (box.y0 + box.y1) / 2;
  const setA = await page.evaluate(([cx, cy]) => {
    const mk = window.__xrayMarkup;
    const s = mk.create('Set on A');
    mk.add({ kind: 'cloud', points: [[cx - 90, cy - 60], [cx + 90, cy + 60]], text: 'cloud' });
    mk.add({ kind: 'rect', points: [[cx - 40, cy - 25], [cx + 40, cy + 25]] });
    mk.add({ kind: 'callout', at: [cx, cy], text: 'check this' });
    return s.id;
  }, [cx, cy]);
  const setInfo = await page.evaluate((id) => window.__xrayMarkup.get(id), setA);
  check('set A has 3 markups', setInfo.markups.length === 3);
  check('the set records its model', setInfo.model?.name === 'fzk-haus' && setInfo.model.elementCount > 50 && !!setInfo.model.guidHash, JSON.stringify(setInfo.model));
  const surf = setInfo.markups.find((m) => m.attach?.kind === 'surface');
  check('a surface outline stores normals, lift and the bounds of its targets', !!surf && surf.attach.surface.pts.every((p) => Array.isArray(p.n) && typeof p.g === 'number') && Array.isArray(surf.attach.surface.fp) && surf.attach.surface.fp.length === surf.attach.surface.guids.length && surf.attach.surface.fp.every((b) => b && b.length === 6), surf ? JSON.stringify(surf.attach.surface.fp) : 'no surface markup');

  const topic = await page.evaluate(([cx, cy]) => {
    const b = window.__xrayBcf;
    const t = b.createTopic({ title: 'Topic on A', snapshot: false });
    b.applyViewpoint(t.guid);
    b.addShape(t.guid, 'rect', [[cx - 60, cy - 40], [cx + 60, cy + 40]], 'topic rect');
    return t.guid;
  }, [cx, cy]);
  await page.waitForTimeout(500);
  const o1 = await overlay();
  // Assertion changed: the topic's rectangle is the drawing of a sketch linked to the issue. The markup view draws it (data-mk, next to
  // the active set), the BCF overlay draws no annotation of a linked viewpoint, so there are 4 markup shapes and no data-bcf-ann.
  check('A: the overlay draws the markups, the topic pin and its drawing', o1.mk >= 4 && o1.pin >= 1 && o1.ann === 0, JSON.stringify(o1));
  check('the topic records its model', (await page.evaluate((g) => window.__xrayBcf.topics.find((t) => t.guid === g)?.model?.name, topic)) === 'fzk-haus');
  const list1 = await page.evaluate(() => ({ mk: window.__xrayMarkup.list().length, bcf: window.__xrayBcf.currentTopics.length, other: window.__xrayMarkup.otherModels().length }));
  // Assertion changed: 2 sketches (the set, and the sketch of the topic's viewpoint).
  check('A: two sketches, one issue, nothing under Other models', list1.mk === 2 && list1.bcf === 1 && list1.other === 0, JSON.stringify(list1));

  // ---------------------------------------------------------------- B: building
  await switchTo('building');
  const o2 = await overlay();
  check('B: no old pin, shape or annotation in the overlay', drawn(o2) === 0, JSON.stringify(o2));
  const list2 = await page.evaluate(() => ({ mk: window.__xrayMarkup.list().length, all: window.__xrayMarkup.list({ all: true }).length, bcf: window.__xrayBcf.currentTopics.length, allBcf: window.__xrayBcf.topics.length, active: window.__xrayMarkup.list({ all: true }).some((s) => s.active), sel: window.__xrayMarkup.selected, scope: window.__xrayMarkup.list({ all: true })[0]?.scope }));
  check('B: the old set and topic are not listed as current', list2.mk === 0 && list2.bcf === 0 && list2.all === 2 && list2.allBcf === 1 && !list2.active && list2.scope === 'different', JSON.stringify(list2));
  check('B: the topic is not applied', (await page.evaluate(() => window.__xrayBcf.applied)) === null);

  await page.evaluate(() => window.__xrayIssues.open('sketches'));
  await page.waitForSelector('#issues-panel');
  const otherSummary = await page.textContent('#issues-panel details[data-other-models] > summary');
  check('B: the Sketches segment shows "Other models (2)"', otherSummary?.trim() === 'Other models (2)', String(otherSummary));
  check('B: the group starts collapsed', (await page.getAttribute('#issues-panel details[data-other-models]', 'open')) === null);
  await page.click('#issues-panel details[data-other-models] > summary');
  const groupText = await page.textContent('#issues-panel details[data-other-models]');
  check('B: the group names the model and offers Open, Move to this model and Delete', /fzk-haus/.test(groupText ?? '') && !!(await page.$('#issues-panel [data-act=other-open]')) && !!(await page.$('#issues-panel [data-act=other-move]')) && !!(await page.$('#issues-panel [data-act=other-delete]')), String(groupText).slice(0, 120));
  check('B: no sketch card of A in the sketches grid', (await page.$$('#issues-panel .is-card')).length === 0);
  await page.evaluate(() => window.__xrayIssues.open('issues'));
  await page.waitForSelector('#issues-panel [data-seg=issues][aria-selected=true]');
  const bcfSummary = await page.textContent('#issues-panel details[data-other-models] > summary');
  check('B: the BCF panel shows "Other models (1)"', bcfSummary?.trim() === 'Other models (1)', String(bcfSummary));
  check('B: the issue list has no issue row', (await page.$$('#issues-panel [data-issue]')).length === 0);
  check('B: the Issues panel open draws no pin of A', drawn(await overlay()) === 0);

  // ---------------------------------------------------------------- back to A
  await switchTo('fzk-haus');
  await page.evaluate((id) => window.__xrayMarkup.restore(id, { animate: false }), setA);
  await page.evaluate((g) => window.__xrayBcf.applyViewpoint(g), topic);
  await page.waitForTimeout(600);
  const o3 = await overlay();
  const list3 = await page.evaluate(() => ({ mk: window.__xrayMarkup.list().length, bcf: window.__xrayBcf.currentTopics.length, other: window.__xrayMarkup.otherModels().length, otherB: window.__xrayBcf.otherModels().length }));
  check('A again: the sketches and the issue are current and drawn', list3.mk === 2 && list3.bcf === 1 && list3.other === 0 && list3.otherB === 0 && o3.mk >= 4 && o3.pin >= 1 && o3.ann === 0, JSON.stringify({ list3, o3 }));

  // ---------------------------------------------------------------- Move to this model
  await switchTo('building');
  await page.evaluate(() => window.__xrayIssues.open('sketches'));
  await page.waitForSelector('#issues-panel details[data-other-models]');
  // Assertion changed: the panel keeps the group open once opened (it is one panel now, not a drawer rebuilt on every open).
  await page.evaluate(() => { const d = document.querySelector('#issues-panel details[data-other-models]'); if (!d.open) d.open = true; });
  await page.click('#issues-panel [data-act=other-move]');
  await page.waitForFunction(() => window.__xrayMarkup.list().length === 1);
  const moved = await page.evaluate(() => {
    const l = window.__xrayMarkup.list();
    const set = window.__xrayMarkup.get(l[0].id);
    const att = set.markups.filter((m) => m.shape).map((m) => window.__xrayMarkup.attachment(m.id));
    return { scope: l[0].scope, model: set.model.name, other: window.__xrayMarkup.otherModels().length, detached: att.filter((a) => a.description.detached).length, shapes: att.length, status: window.__xrayMarkup.status };
  });
  // Assertion changed: the sketch of the topic's viewpoint stays on A until its issue moves (1 other model group member left, not 0).
  check('Move to this model: the set belongs to building, only the issue sketch stays behind', moved.scope === 'same' && moved.model === 'building' && moved.other === 1, JSON.stringify(moved));
  check('Move to this model: targets this model lacks show detached (view-locked)', moved.detached >= 1 && /now belongs/.test(moved.status), JSON.stringify(moved));
  // Assertion changed: the sketch of the topic is still on the other model (the issue moves it, below).
  check('the Other models group keeps only the sketch of the issue', (await page.textContent('#issues-panel details[data-other-models] > summary'))?.trim() === 'Other models (1)');
  await page.click('#issues-panel .is-card');
  await page.waitForTimeout(600);
  const o4 = await overlay();
  check('the moved set is drawn on B (view-locked)', o4.mk >= 1, JSON.stringify(o4));

  await page.evaluate(() => window.__xrayIssues.open('issues'));
  await page.waitForSelector('#issues-panel details[data-other-models]');
  // Assertion changed: the panel keeps the group open once opened (it is one panel now, not a drawer rebuilt on every open).
  await page.evaluate(() => { const d = document.querySelector('#issues-panel details[data-other-models]'); if (!d.open) d.open = true; });
  await page.click('#issues-panel [data-act=other-move]');
  await page.waitForFunction(() => window.__xrayBcf.currentTopics.length === 1);
  const mv = await page.evaluate(() => ({ scope: window.__xrayBcf.scopeOf(window.__xrayBcf.currentTopics[0].guid), other: window.__xrayBcf.otherModels().length, row: document.querySelectorAll('#issues-panel [data-issue]').length, sketches: window.__xrayMarkup.list().length, sketchOther: window.__xrayMarkup.otherModels().length }));
  check('Move to this model (issue): the issue and its sketch belong to building', mv.scope === 'same' && mv.other === 0 && mv.row === 1 && mv.sketches === 2 && mv.sketchOther === 0, JSON.stringify(mv));

  // ---------------------------------------------------------------- Open, on purpose; a file opened on another model
  const exported = await page.evaluate(async () => {
    const f = window.__xrayMarkup.exportJson();
    return new TextDecoder().decode(f.bytes);
  });
  const doc = JSON.parse(exported);
  check('the exported file names the model of each set', doc.model.name === 'building' && doc.sets.every((s) => s.model?.name === 'building'));
  // A file made on A (the set re-bound above is B's, so edit the file to say fzk-haus): opened on B it says so.
  const fromA = JSON.parse(exported);
  fromA.model = { name: 'fzk-haus', elementCount: 999, guidCount: 999, guidHash: '0123456789abcdef' };
  for (const s of fromA.sets) { s.id = `${s.id}-imp`; s.title = `${s.title} (file)`; s.model = fromA.model; }
  const rep = await page.evaluate((t) => window.__xrayMarkup.importJson(t), JSON.stringify(fromA));
  check('opening a file made on another model warns and lists its sets under Other models', rep.ok && rep.match === 'different' && rep.warnings.some((w) => /Other models/.test(w)) && !rep.restored, JSON.stringify({ match: rep.match, restored: rep.restored, w: rep.warnings }));
  const l5 = await page.evaluate(() => ({ cur: window.__xrayMarkup.list().length, other: window.__xrayMarkup.otherModels() }));
  check('the imported sets are under Other models and not current', l5.cur === 2 && l5.other.length === 1 && l5.other[0].sets.length === 2, JSON.stringify(l5));
  const opened = await page.evaluate((id) => { window.__xrayMarkup.openOther(id); return window.__xrayMarkup.list().map((s) => [s.id.endsWith('-imp'), s.scope, s.active]); }, (await page.evaluate(() => window.__xrayMarkup.otherModels()[0].sets[0].id)));
  check('Open shows it on purpose (active, still marked as another model)', opened.some((x) => x[0] && x[1] === 'different' && x[2]), JSON.stringify(opened));

  // ---------------------------------------------------------------- a different IFC through the file loader
  await page.setInputFiles('#xray-open-file-input', [resolve(root, '../models/Building-Hvac.ifc')]);
  await page.waitForFunction(() => window.__xray.app.modelName.startsWith('file:'), null, { timeout: 120000 });
  await settle();
  await page.waitForTimeout(600);
  const o6 = await overlay();
  const l6 = await page.evaluate(() => ({ cur: window.__xrayMarkup.list().length, all: window.__xrayMarkup.list({ all: true }).length, other: window.__xrayMarkup.otherModels().length, bcf: window.__xrayBcf.currentTopics.length, allBcf: window.__xrayBcf.topics.length, bcfOther: window.__xrayBcf.otherModels().length, name: window.__xray.app.modelName }));
  check('a different IFC from the file loader: nothing of the previous models is drawn', drawn(o6) === 0, JSON.stringify(o6));
  check('and the sets and topics are all under Other models', l6.cur === 0 && l6.all >= 2 && l6.bcf === 0 && l6.allBcf === 1 && l6.bcfOther >= 1, JSON.stringify(l6));

  // Delete from the group.
  await page.evaluate(() => window.__xrayIssues.open('sketches'));
  await page.waitForSelector('#issues-panel details[data-other-models]');
  const before = await page.evaluate(() => window.__xrayMarkup.list({ all: true }).length);
  // Assertion changed: the panel keeps the group open once opened (it is one panel now, not a drawer rebuilt on every open).
  await page.evaluate(() => { const d = document.querySelector('#issues-panel details[data-other-models]'); if (!d.open) d.open = true; });
  await page.click('#issues-panel [data-act=other-delete]');
  await page.click('#issues-panel [data-act=other-delete]');
  await page.waitForFunction((n) => window.__xrayMarkup.list({ all: true }).length === n - 1, before);
  check('Delete removes a set of another model (second click confirms)', true);

  check('no console errors', errors.length === 0, errors.slice(0, 3).join(' | '));
} catch (e) {
  failed = true;
  console.log('FAIL smoke crashed:', e instanceof Error ? e.stack ?? e.message : e);
  if (errors.length) console.log('console errors:', errors.slice(0, 5).join(' | '));
} finally {
  await browser?.close();
  vite.kill();
}
process.exit(failed ? 1 : 0);
