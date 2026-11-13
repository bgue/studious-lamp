// Headless check for the Issues tab (BCF is the container, markups are the drawing layer) on /?model=fzk-haus:
//   - the sidebar tab "Issues" (after Model, Sets, Views) with the segments Issues and Sketches; the old Markup and BCF
//     drawers are gone from the tool strip, key K opens the Sketches segment;
//   - New sketch shows the floating drawing toolbar, clear of the gizmo and the top bar; a drawing is made with it; Done hides it;
//   - Raise as issue links the sketch to a new issue (both ways); editing the sketch changes the issue's drawing and its
//     burned snapshot; the BCF export carries the current drawing and opens again as a sketch linked to its issue;
//   - removing a sketch of an issue asks first; the status bar says "N open issues" and opens the tab; the top-bar search
//     finds an issue by title and by comment text;
//   - the migration banner for a legacy markup JSON with comments and a resolved status, and its conversion to an issue;
//   - the phone layout: the list is a bottom sheet and the toolbar fits 390 px;
//   - fails on any console error.
// Screenshots: bench/issues-panel.png, issues-sketch-toolbar.png, issues-phone.png.
// Usage: SMOKE_PORT=5710 node bench/smoke-issues.mjs
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const port = Number(process.env.SMOKE_PORT ?? 5710);

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
  const ctx = await browser.newContext({ viewport: { width: 1500, height: 800 } });
  const page = await ctx.newPage();
  page.setDefaultTimeout(Number(process.env.SMOKE_TIMEOUT ?? 120000));
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', (e) => errors.push(`[pageerror] ${e.message}`));

  async function boot(pg = page) {
    await pg.goto(`http://127.0.0.1:${port}/?model=fzk-haus`);
    await pg.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: 240000 });
    const err = await pg.evaluate('window.__xrayError');
    if (err) throw new Error(`startup failed: ${err}`);
  }
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
  const rect = (sel, pg = page) => pg.evaluate((s) => { const e = document.querySelector(s); if (!e) return null; const r = e.getBoundingClientRect(); return { x: r.left, y: r.top, w: r.width, h: r.height, r: r.right, b: r.bottom }; }, sel);
  const overlap = (a, b) => !!a && !!b && a.x < b.r && b.x < a.r && a.y < b.b && b.y < a.b;
  async function drag(x0, y0, x1, y1, pg = page) {
    await pg.mouse.move(x0, y0);
    await pg.mouse.down();
    for (let i = 1; i <= 3; i++) await pg.mouse.move(x0 + ((x1 - x0) * i) / 3, y0 + ((y1 - y0) * i) / 3);
    await pg.mouse.up();
  }
  const sketchCount = (id, pg = page) => pg.evaluate((i) => window.__xrayMarkup.get(i).markups.length, id);
  /** The free part of the canvas: right of the sidebar, left of the parameter panel, clear of the top bar and the toolbar. */
  const freeArea = (pg = page) => pg.evaluate(() => {
    const cv = window.__xray.app.canvas.getBoundingClientRect();
    const sb = document.querySelector('#sidebar')?.getBoundingClientRect();
    const gui = document.querySelector('.lil-gui.root')?.getBoundingClientRect();
    return { x0: Math.max(cv.left, sb ? sb.right : 0) + 20, x1: Math.min(cv.right, gui && gui.width ? gui.left : cv.right) - 20, y0: cv.top + 90, y1: cv.bottom - 200 };
  });

  // ------------------------------------------------------------------ part 1: tab, segments, tool strip
  await boot();
  await setCamera();
  await page.waitForTimeout(500);
  const tabs = await page.evaluate(() => [...document.querySelectorAll('#sidebar .sb-tab')].map((b) => b.textContent));
  check('sidebar tabs: Model, Sets, Views, Issues', JSON.stringify(tabs) === JSON.stringify(['Model', 'Sets', 'Views', 'Issues']), tabs.join(','));
  const tools = await page.evaluate(() => window.__xrayToolbar.tools());
  check('the BCF and Markup drawers left the tool strip', !tools.includes('bcf') && !tools.includes('markup'), tools.join(','));
  await page.keyboard.press('k');
  await page.waitForSelector('#issues-panel [data-seg=sketches][aria-selected=true]');
  check('key K opens the Issues tab on the Sketches segment', await page.evaluate(() => window.__xrayIssues.segment === 'sketches' && window.__xrayIssues.visible));
  await page.click('#issues-panel [data-seg=issues]');
  check('the segmented switch goes to Issues', await page.evaluate(() => window.__xrayIssues.segment === 'issues'));
  check('empty issue list says how to start', (await page.textContent('#issues-panel')).includes('No issues for this model'));
  check('status bar says 0 open issues', (await page.textContent('#xray-overlay .xs-issues')) === '0 open issues');

  // ------------------------------------------------------------------ part 2: a sketch with the floating toolbar
  await page.fill('#issues-panel [data-keep=author]', 'smoke-author');
  await page.dispatchEvent('#issues-panel [data-keep=author]', 'change');
  await page.click('#issues-panel [data-seg=sketches]');
  await page.click('#issues-panel [data-act=new-sketch]');
  await page.waitForFunction(() => window.__xrayMarkup.list().length === 1);
  await page.waitForSelector('#markup-float', { state: 'visible' });
  check('New sketch shows the drawing toolbar', await page.evaluate(() => window.__xrayMarkup.editing));
  await page.waitForTimeout(300);
  const bar = await rect('#markup-float');
  const giz = await rect('#xray-gizmo');
  const top = await rect('#xray-topbar');
  check('the toolbar covers neither the gizmo nor the top bar', !overlap(bar, giz) && !overlap(bar, top), JSON.stringify({ bar, giz, top }));
  const kinds = await page.evaluate(() => [...document.querySelectorAll('#markup-float [data-tool-id]')].map((b) => b.dataset.toolId));
  check('the toolbar has the drawing tools, colours, weights, undo, redo and Done', kinds.length >= 14 && !!(await page.$('#markup-float [data-colour=blue]')) && !!(await page.$('#markup-float [data-weight="3"]')) && !!(await page.$('#markup-float [data-act=undo]')) && !!(await page.$('#markup-float [data-act=redo]')) && !!(await page.$('#markup-float [data-act=done]')), `${kinds.length} tools`);
  const fa = await freeArea();
  const sid = await page.evaluate(() => window.__xrayMarkup.list()[0].id);
  await page.click('#markup-float [data-tool-id=rect]');
  await page.click('#markup-float [data-colour=blue]');
  const cam0 = await page.evaluate(() => { const c = window.__xray.app.renderer.camera; return [c.position.x, c.position.y, c.position.z]; });
  await drag(fa.x0 + 60, fa.y0 + 40, fa.x0 + 260, fa.y0 + 160);
  check('a rectangle is drawn with the toolbar', (await sketchCount(sid)) === 1);
  check('the orbit did not move while drawing', await page.evaluate((c0) => { const c = window.__xray.app.renderer.camera; return Math.hypot(c.position.x - c0[0], c.position.y - c0[1], c.position.z - c0[2]) < 1e-6; }, cam0));
  check('undo is enabled after drawing', await page.evaluate(() => !document.querySelector('#markup-float [data-act=undo]').disabled));
  // the global undo stack stays out of it while the toolbar is up
  const globalBefore = await page.evaluate(() => window.__xrayUndo?.list?.().undo.length ?? 0);
  await page.keyboard.press('Control+z');
  check('Ctrl+Z undoes the drawing, not the global stack, while the toolbar is up', (await sketchCount(sid)) === 0 && (await page.evaluate(() => window.__xrayUndo?.list?.().undo.length ?? 0)) === globalBefore);
  await page.keyboard.press('Control+Shift+z');
  check('redo brings it back', (await sketchCount(sid)) === 1);
  await page.click('#markup-float [data-tool-id=ellipse]');
  await drag(fa.x0 + 300, fa.y0 + 40, fa.x0 + 480, fa.y0 + 140);
  check('a second drawing (ellipse)', (await sketchCount(sid)) === 2);
  await page.screenshot({ path: resolve(here, 'issues-sketch-toolbar.png') });
  // pointer modes still work while drawing: hand mode, then back to arrow
  const mode0 = await page.evaluate(() => window.__xray.app.canvas.dataset.pointerMode);
  await page.keyboard.press('g');
  const modeH = await page.evaluate(() => window.__xray.app.canvas.dataset.pointerMode);
  await page.keyboard.press('r');
  const modeA = await page.evaluate(() => window.__xray.app.canvas.dataset.pointerMode);
  check('pointer modes Arrow and Hand switch while the toolbar is up', modeH === 'hand' && modeA === 'arrow', `${mode0} ${modeH} ${modeA}`);
  await page.click('#markup-float [data-act=done]');
  await page.waitForFunction(() => !window.__xrayMarkup.editing);
  check('Done hides the toolbar', await page.evaluate(() => getComputedStyle(document.querySelector('#markup-float')).display === 'none'));
  await page.fill('#issues-panel [data-field=title]', 'Duct clash level 1');
  await page.dispatchEvent('#issues-panel [data-field=title]', 'change');
  await page.fill('#issues-panel [data-field=note]', 'Duct crosses the beam');
  await page.waitForTimeout(100);
  check('the sketch holds a one-line note, no status, no comment box', (await page.evaluate((i) => window.__xrayMarkup.get(i).note, sid)) === 'Duct crosses the beam' && !(await page.$('#issues-panel [data-field=status]')) && !(await page.$('#issues-panel textarea')));

  // ------------------------------------------------------------------ part 3: raise as issue, edit, link both ways
  await page.click('#issues-panel [data-act=raise]');
  await page.waitForFunction(() => window.__xrayBcf.topics.length === 1);
  const link = await page.evaluate((i) => ({ issue: window.__xrayIssues.issueOf(i), topic: window.__xrayBcf.topics[0] && { guid: window.__xrayBcf.topics[0].guid, title: window.__xrayBcf.topics[0].title, status: window.__xrayBcf.topics[0].topicStatus, vp: window.__xrayBcf.topics[0].viewpoints.map((v) => ({ guid: v.guid, sketchId: v.sketchId, ann: v.annotations?.length ?? 0 })) }, set: window.__xrayMarkup.get(i).issue }), sid);
  check('Raise as issue made an issue titled like the sketch', link.topic?.title === 'Duct clash level 1' && link.topic.status === 'Open', JSON.stringify(link.topic));
  check('the viewpoint links to the sketch by id, and the sketch links back', link.topic.vp[0].sketchId === sid && link.issue?.topic === link.topic.guid && link.issue.viewpoint === link.topic.vp[0].guid && link.set?.topic === link.topic.guid);
  check('the issue viewpoint holds the sketch drawing (2 annotations)', link.topic.vp[0].ann === 2, String(link.topic.vp[0].ann));
  check('the sketch detail shows the link to its issue, and the issue detail shows its sketch row', !!(await page.$(`#issues-panel [data-issue-link="${link.topic.guid}"]`)));
  await page.click('#issues-panel [data-act=open-issue]');
  await page.waitForSelector('#issues-panel [data-viewpoint] [data-act=edit-drawing]');
  check('Open issue goes to the issue, whose sketch row names the sketch', (await page.textContent('#issues-panel [data-viewpoint]')).includes('Duct clash level 1'));
  check('status bar counts 1 open issue', (await page.textContent('#xray-overlay .xs-issues')) === '1 open issue');
  const snap0 = await page.evaluate(async () => { const t = window.__xrayBcf.topics[0]; const b = await window.__xrayBcf.composeSnapshot(t.guid); return b ? b.length : 0; });
  // edit the sketch: one more drawing through the issue's Edit drawing button
  await page.click('#issues-panel [data-viewpoint] [data-act=edit-drawing]');
  await page.waitForSelector('#markup-float', { state: 'visible' });
  check('Edit drawing on an issue viewpoint shows the toolbar', await page.evaluate(() => window.__xrayMarkup.editing));
  const fa2 = await freeArea();
  await page.click('#markup-float [data-tool-id=arrow]');
  await drag(fa2.x0 + 60, fa2.y0 + 200, fa2.x0 + 240, fa2.y0 + 260);
  await page.click('#markup-float [data-act=done]');
  await page.waitForTimeout(200);
  const after = await page.evaluate((i) => ({ n: window.__xrayMarkup.get(i).markups.length, ann: window.__xrayBcf.topics[0].viewpoints[0].annotations?.length ?? 0 }), sid);
  check('editing the sketch updates the issue viewpoint', after.n === 3 && after.ann === 3, JSON.stringify(after));
  const snap1 = await page.evaluate(async () => { const t = window.__xrayBcf.topics[0]; const b = await window.__xrayBcf.composeSnapshot(t.guid); return b ? b.length : 0; });
  check('the burned snapshot reflects the edit', snap0 > 0 && snap1 > 0 && snap1 !== snap0, `${snap0} -> ${snap1}`);
  await page.screenshot({ path: resolve(here, 'issues-panel.png') });
  // the BCF export serialises the current drawing and opens as a sketch linked to its issue
  const rt = await page.evaluate(async () => {
    const bytes = await window.__xrayBcf.exportZip('2.1');
    await window.__xrayBcf.load(bytes);
    const t = window.__xrayBcf.topics[0];
    const sk = window.__xrayMarkup.list();
    const v = t.viewpoints[0];
    return { topics: window.__xrayBcf.topics.length, ann: v.annotations?.length ?? 0, sketches: sk.length, linked: !!v.sketchId, back: sk.some((s) => window.__xrayIssues.issueOf(s.id)?.topic === t.guid), kinds: window.__xrayMarkup.get(v.sketchId)?.markups.map((m) => m.kind) };
  });
  check('BCF export and re-import: 3 drawings come back as a sketch linked to the issue', rt.topics === 1 && rt.ann === 3 && rt.linked && rt.back, JSON.stringify(rt));
  // removing a sketch of an issue asks first
  const sk2 = await page.evaluate(() => window.__xrayMarkup.list().map((s) => s.id));
  const target = await page.evaluate(() => window.__xrayBcf.topics[0].viewpoints[0].sketchId);
  const first = await page.evaluate((id) => window.__xrayIssues.removeSketch(id), target);
  check('removing a sketch that belongs to an issue asks first', first === 'confirm' && (await page.evaluate((id) => !!window.__xrayMarkup.get(id), target)), first);
  await page.click('#issues-panel [data-seg=sketches]');
  await page.click(`#issues-panel [data-sketch="${target}"]`);
  await page.waitForSelector('#issues-panel [data-confirm-remove]');
  check('the confirmation says which issue the sketch belongs to', (await page.textContent('#issues-panel [data-confirm-remove]')).includes('Duct clash level 1'));
  await page.click('#issues-panel [data-act=remove-confirm]');
  await page.waitForFunction((id) => !window.__xrayMarkup.get(id), target);
  check('after confirming, the sketch is gone and the viewpoint lost its link', await page.evaluate(() => !window.__xrayBcf.topics[0].viewpoints[0].sketchId && !window.__xrayBcf.topics[0].viewpoints[0].annotations));
  void sk2;

  // ------------------------------------------------------------------ part 4: search
  await page.evaluate(() => window.__xrayBcf.addComment(window.__xrayBcf.topics[0].guid, 'Reroute below the girder', { author: 'someone' }));
  const byTitle = await page.evaluate(() => window.__xrayIssues.search('duct clash').map((h) => `${h.kind}:${h.field}`));
  const byComment = await page.evaluate(() => window.__xrayIssues.search('girder').map((h) => `${h.kind}:${h.field}`));
  check('search finds an issue by title and by comment text', byTitle.includes('issue:title') && byComment.includes('issue:comment'), `${byTitle} | ${byComment}`);
  await page.evaluate(() => { document.activeElement?.blur?.(); window.__xraySearch.bar.focus(); });
  await page.locator('.ab-input').fill('');
  await page.keyboard.type('girder', { delay: 30 });
  await page.waitForTimeout(1200);
  const st = await page.evaluate(() => window.__xraySearch.state());
  const hitRow = st.rows.find((r) => r.section === 'issues');
  check('the top-bar search lists the issue under "Issues and sketches"', !!hitRow && hitRow.label === 'Duct clash level 1' && /comment/.test(hitRow.sub), JSON.stringify(st.rows.slice(0, 3)));
  for (let i = 0; i < 12; i++) {
    const a = await page.evaluate(() => { const x = window.__xraySearch.state(); return x.rows[x.active]?.section; });
    if (a === 'issues') break;
    await page.keyboard.press('ArrowDown');
  }
  await page.keyboard.press('Enter'); // Enter opens the active row: the issue, with its view
  await page.waitForTimeout(300);
  check('Enter on the row opens the issue in the tab', await page.evaluate(() => window.__xrayIssues.segment === 'issues' && window.__xrayIssues.detail?.kind === 'issue'));
  await page.keyboard.press('Escape');
  await page.evaluate(() => { document.activeElement?.blur?.(); });
  await page.click('#xray-overlay .xs-issues');
  check('the status bar count opens the tab on the open issues', await page.evaluate(() => window.__xrayIssues.segment === 'issues' && window.__xrayIssues.visible));

  // ------------------------------------------------------------------ part 5: migration banner for a legacy markup JSON
  await page.evaluate(() => { for (const s of window.__xrayMarkup.list()) window.__xrayMarkup.deleteSet(s.id); });
  const legacyJson = await page.evaluate(() => {
    const s = window.__xrayMarkup.create('Legacy review');
    const c = document.querySelector('#xray-toolbar-drawer'); void c;
    window.__xrayMarkup.add({ kind: 'cloud', fractions: { points: [[0.3, 0.3], [0.5, 0.5]], depth: 8 }, text: 'check this' });
    window.__xrayMarkup.add({ kind: 'rect', fractions: { points: [[0.55, 0.3], [0.7, 0.45]], depth: 8 } });
    const doc = JSON.parse(new TextDecoder().decode(window.__xrayMarkup.exportJson({ ids: [s.id] }).bytes));
    doc.sets[0].markups[0].status = 'resolved';
    doc.sets[0].markups[0].comments = [{ id: 'c1', author: 'old reviewer', date: '2025-05-01T10:00:00.000Z', text: 'Moved the duct' }, { id: 'c2', author: 'old reviewer', date: '2025-05-02T10:00:00.000Z', text: 'Checked on site' }];
    doc.sets[0].markups[1].assignee = 'planner';
    for (const x of window.__xrayMarkup.list()) window.__xrayMarkup.deleteSet(x.id);
    return JSON.stringify(doc);
  });
  const rep = await page.evaluate((t) => window.__xrayMarkup.importJson(t), legacyJson);
  check('legacy markup JSON imports', rep.ok && rep.sets === 1 && rep.markups === 2, JSON.stringify(rep));
  await page.evaluate(() => window.__xrayIssues.open('sketches'));
  await page.waitForSelector('#issues-panel [data-banner=migrate]');
  const bannerText = await page.textContent('#issues-panel [data-banner-text]');
  check('the banner offers to raise the sketches', bannerText === '1 sketch has comments or a status. Raise it as an issue?', bannerText);
  await page.click('#issues-panel [data-sketch]');
  await page.waitForSelector('#issues-panel [data-legacy]');
  check('until converted, the legacy comments and status show read-only on the sketch', (await page.textContent('#issues-panel [data-legacy]')).includes('Moved the duct') && (await page.textContent('#issues-panel [data-legacy]')).includes('resolved'));
  await page.click('#issues-panel [data-act=back]');
  const before = await page.evaluate(() => window.__xrayBcf.topics.length);
  await page.click('#issues-panel [data-act=migrate]');
  await page.waitForFunction((n) => window.__xrayBcf.topics.length === n + 1, before);
  const mig = await page.evaluate(() => {
    const t = window.__xrayBcf.topics[window.__xrayBcf.topics.length - 1];
    const s = window.__xrayMarkup.list()[0];
    const set = window.__xrayMarkup.get(s.id);
    return { title: t.title, comments: t.comments.map((c) => c.text), authors: t.comments.map((c) => c.author), assignee: t.assignedTo, status: t.topicStatus, linked: t.viewpoints[0].sketchId === s.id, legacyLeft: set.markups.some((m) => m.comments.length || m.status === 'resolved' || m.assignee), banner: !!document.querySelector('[data-banner=migrate]') };
  });
  check('the sketch became an issue that links to it, with its comments, assignee and status moved', mig.title === 'Legacy review' && mig.comments.length === 2 && mig.comments[0] === '1. Moved the duct' && mig.authors[0] === 'old reviewer' && mig.assignee === 'planner' && mig.linked, JSON.stringify(mig));
  check('the issue is Open (the second drawing was still open); nothing is left on the sketch; the banner is gone', mig.status === 'Open' && !mig.legacyLeft && !mig.banner, JSON.stringify(mig));

  // ------------------------------------------------------------------ part 6: phone
  const phone = await browser.newContext({ viewport: { width: 390, height: 780 }, hasTouch: true, isMobile: true, deviceScaleFactor: 2 });
  const pp = await phone.newPage();
  pp.setDefaultTimeout(120000);
  pp.on('console', (m) => { if (m.type() === 'error') errors.push(`[phone] ${m.text()}`); });
  pp.on('pageerror', (e) => errors.push(`[phone pageerror] ${e.message}`));
  await boot(pp);
  await setCamera(pp);
  await pp.waitForTimeout(500);
  await pp.evaluate(() => { window.__xrayMarkup.create('Phone sketch'); window.__xrayBcf.createTopic({ title: 'Phone issue' }); });
  await pp.evaluate(() => window.__xrayIssues.open('issues'));
  await pp.waitForSelector('#issues-sheet.on');
  const sheet = await rect('#issues-sheet', pp);
  const vw = await pp.evaluate(() => window.innerWidth);
  check('phone: the list is a bottom sheet', !!sheet && sheet.r <= vw + 0.5 && sheet.b <= 780 && sheet.y > 100 && (await pp.evaluate(() => !!document.querySelector('#issues-sheet #issues-panel'))), JSON.stringify(sheet));
  await pp.screenshot({ path: resolve(here, 'issues-phone.png') });
  await pp.click('#issues-sheet [data-seg=sketches]');
  await pp.click('#issues-sheet [data-act=edit-drawing], #issues-sheet [data-sketch]');
  await pp.waitForTimeout(200);
  await pp.evaluate(() => { const s = window.__xrayMarkup.list()[0]; window.__xrayIssues.editSketch(s.id); });
  await pp.waitForSelector('#markup-float', { state: 'visible' });
  await pp.waitForTimeout(300);
  const pbar = await rect('#markup-float', pp);
  check('phone: the drawing toolbar fits 390 px and the sheet steps aside while drawing', !!pbar && pbar.x >= 0 && pbar.r <= 390.5 && !(await pp.evaluate(() => document.querySelector('#issues-sheet').classList.contains('on'))), JSON.stringify(pbar));
  await pp.click('#markup-float [data-act=done]');
  await pp.waitForSelector('#issues-sheet.on');
  check('phone: Done brings the sheet back', true);
  await phone.close();

  check('no console errors', errors.length === 0, errors.slice(0, 4).join(' | '));
} catch (e) {
  failed = true;
  console.log('ERROR', e instanceof Error ? e.stack ?? e.message : e);
} finally {
  await browser?.close();
  vite.kill();
}
process.exit(failed ? 1 : 0);
