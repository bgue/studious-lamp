// Headless smoke test for the revision walk (docs/design/ifc-save-and-revision.md, section 6, steps 3 to 7). Steps 1 and 2 (Save IFC) and
// the `RevisionStatus` check of step 6 belong to ticket T2 (Save IFC), which lives on another branch: they are skipped here with a note
// and are added when that branch is merged. The `RevisionStatus` hand-off itself is unit tested (tests/revision-ui.test.ts).
//
// Desktop run: load AC20-FZK-Haus.ifc as v1, classify with the rules, commit a few confirmations, store a snapshot, load fzk-v2.ifc,
// expect the banner, "Review changes", expect the counts of the truth file, then a walk with the KEYBOARD only (accept a move and see the
// ghost, reject a deletion and raise an issue, a bulk rule, a skip, an unsure flag), reload the page mid-walk and resume, finish the walk,
// export the report. Phone run (390 x 844, touch): the bottom sheet, buttons and swipes only, to the end of the walk.
// Screenshots: bench/revision-walk.png, bench/revision-phone.png, bench/revision-ghost.png. Zero console errors.
// Usage: SMOKE_PORT=5780 node bench/smoke-ifc-save-revision.mjs
import { spawn } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const repo = resolve(root, '..');
const port = Number(process.env.SMOKE_PORT ?? 5780);
const V1 = resolve(repo, 'models/AC20-FZK-Haus.ifc');
const V2 = resolve(root, 'tests/fixtures/ifc/fzk-v2.ifc');
const truth = JSON.parse(readFileSync(resolve(root, 'tests/fixtures/ifc/fzk-v2.truth.json'), 'utf8'));
const NAME = 'Rosalind Fanshawe';

function loadPlaywright() {
  const candidates = [process.env.PLAYWRIGHT_MODULE, resolve(root, 'node_modules/playwright'), '/opt/node-tools/node_modules/playwright', '/opt/node22/lib/node_modules/playwright'].filter(Boolean);
  for (const c of candidates) {
    try { return createRequire(import.meta.url)(c); } catch { /* try next */ }
  }
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

const checks = [];
function check(name, ok, detail = '') {
  checks.push({ name, ok });
  console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${detail ? ` (${detail})` : ''}`);
}
const GL = ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'];
const shot = (page, name) => page.screenshot({ path: resolve(here, name), timeout: 240000 });
const T = 240000;

async function openPage(browser, o = {}) {
  const ctx = o.ctx ?? (await browser.newContext({ viewport: o.viewport ?? { width: 1500, height: 900 }, acceptDownloads: true, ...(o.touch ? { hasTouch: true, isMobile: true } : {}) }));
  const page = await ctx.newPage();
  const errors = [];
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', (e) => errors.push(`[pageerror] ${e.message}`));
  await page.route(/^https?:\/\/(?!127\.0\.0\.1)/, (route) => route.abort());
  await page.goto(`http://127.0.0.1:${port}/?model=building`);
  await page.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: T });
  const err = await page.evaluate('window.__xrayError');
  if (err) errors.push(`[app] ${err}`);
  await page.waitForFunction('window.__xrayClassify && window.__xrayRevision', null, { timeout: 60000 });
  return { ctx, page, errors };
}

/** Open an IFC through the hidden file input and wait until it is the model on screen. */
async function openIfc(page, file, name) {
  await page.setInputFiles('#xray-open-file-input', file);
  await page.waitForFunction((n) => window.__xray?.app.modelName === n && window.__xray.app.loaded, name, { timeout: 480000 });
  await page.evaluate(() => window.__xrayClassify.review.ready());
  await page.waitForTimeout(500);
}

/** Steps 1 and 3 of the outline: v1 classified by the rules, a few confirmations committed, snapshot stored; then v2 loaded. */
async function prepare(page) {
  await openIfc(page, V1, 'file:AC20-FZK-Haus.ifc');
  await page.evaluate(() => window.__xrayClassify.configure({ provider: 'off' }));
  await page.evaluate(() => window.__xrayClassify.classify('all'));
  const n = await page.evaluate(() => window.__xrayClassify.results().length);
  // commit confirmations for a handful of unchanged elements and for two elements that the revision changes (a moved one and a re-typed one)
  const ids = await page.evaluate(({ all, changed }) => {
    const have = window.__xrayClassify.results().map((r) => r.id);
    const pick = have.filter((g) => !all.includes(g)).slice(0, 6);
    return [...pick, ...changed.filter((g) => have.includes(g))];
  }, { all: truth.changes.flatMap((c) => [c.baseGuid, c.headGuid].filter(Boolean)), changed: truth.changes.filter((c) => c.flags.includes('type') || c.flags.includes('placement')).slice(0, 3).map((c) => c.baseGuid) });
  await page.evaluate((nm) => window.__xrayClassify.review.setReviewer(nm), NAME);
  await page.evaluate((g) => { window.__xrayClassify.review.propose(g, { action: 'confirm', item: 'smoke' }); return window.__xrayClassify.review.commit('v1 review'); }, ids);
  const committed = await page.evaluate(() => window.__xrayClassify.review.history().reduce((a, c) => a + c.changes.length, 0));
  await page.evaluate(() => window.__xrayRevision.snapshotNow(true));
  const snaps = await page.evaluate(() => window.__xrayRevision.snapshots());
  await openIfc(page, V2, 'file:fzk-v2.ifc');
  return { classified: n, committed, snaps, ids };
}

const rev = (page) => page.evaluate(() => window.__xrayRevision.state());
const walk = (page) => page.evaluate(() => window.__xrayRevision.walk.state());
const settle = (page, ms = 700) => page.waitForTimeout(ms);
async function waitBanner(page, re) {
  await page.waitForFunction((src) => { const b = document.querySelector('[data-testid=revision-banner]'); return b && !b.hidden && new RegExp(src).test(b.textContent ?? ''); }, re.source, { timeout: 60000 });
}
const bannerText = (page) => page.evaluate(() => document.querySelector('[data-testid=revision-banner]')?.textContent ?? '');
async function waitWalk(page) {
  await page.waitForFunction(() => window.__xrayRevision.walk.state().open && window.__xrayRevision.state().session, null, { timeout: 240000 });
  await settle(page, 600);
}

async function runDesktop(browser) {
  const tag = '[desktop]';
  const { ctx, page, errors } = await openPage(browser);
  const downloads = [];
  page.on('download', (d) => downloads.push(d.suggestedFilename()));
  try {
    const prep = await prepare(page);
    check(`${tag} v1 classified and ${prep.committed} decisions committed, a snapshot is stored`, prep.classified > 50 && prep.committed >= 6, `${prep.classified} results`);
    // ---- 3. banner
    await waitBanner(page, /revision of file:AC20-FZK-Haus\.ifc/);
    const bt = await bannerText(page);
    check(`${tag} the banner names the earlier model and offers Review changes`, /Review changes/.test(bt) && /Not a revision/.test(bt) && /reviewed/.test(bt), bt.slice(0, 120));
    check(`${tag} nothing is carried over before the click (no results on the new model)`, (await page.evaluate(() => window.__xrayClassify.results().length)) === 0);
    await page.click('[data-testid=revision-banner] [data-act=review-changes]');
    await waitWalk(page);
    const s = await rev(page);
    const exp = { new: 3, deleted: 4, changed: 14, rematched: 6 };
    check(`${tag} the counts equal the truth file`, ['new', 'deleted', 'changed', 'rematched'].every((k) => s.session.counts[k] === exp[k]), JSON.stringify(s.session.counts));
    check(`${tag} unchanged committed elements are committed in the new model`, (await page.evaluate(() => window.__xrayClassify.results().filter((r) => r.source === 'confirmed' || r.source === 'corrected').length)) === 6, `${s.session.carried?.commits.length} commits carried`);
    check(`${tag} the panel is open with the first item`, (await walk(page)).item !== null && (await walk(page)).items > 0);

    // ---- 4. walk by keyboard. Deleted first: reject one deletion, raise an issue for it.
    const w0 = await walk(page);
    check(`${tag} the walk starts with the deleted elements`, w0.item?.category === 'deleted', w0.item?.title);
    await page.keyboard.press('r');
    await settle(page);
    let st = await walk(page);
    check(`${tag} Reject records a rejection and does not raise an issue by itself`, st.progress.rejected >= 1 && (await page.evaluate(() => window.__xrayIssues.controller.topics.length)) === 0);
    await page.keyboard.press('ArrowLeft');
    await settle(page);
    await page.click('[data-act=raise-issue]', { timeout: 240000 }); // a snapshot of the view is taken: slow on a software GL
    await settle(page);
    const issue = await page.evaluate(() => { const t = window.__xrayIssues.controller.topics; return { n: t.length, sel: t[0]?.viewpoints[0]?.data?.selection?.length ?? 0, title: t[0]?.title ?? '' }; });
    check(`${tag} Raise issue creates one issue with the element GlobalIds as components`, issue.n === 1 && issue.sel >= 1, issue.title);
    await page.keyboard.press('ArrowRight'); // skip (already decided: the card moves on)
    await settle(page, 300);
    // accept the remaining deletions
    for (let i = 0; i < 20; i++) { const w = await walk(page); if (!w.item || w.item.category !== 'deleted') break; await page.keyboard.press('Enter'); await settle(page, 250); }
    // rematched, then changed: stop at the first changed item with a placement flag and look at the ghost
    for (let i = 0; i < 20; i++) { const w = await walk(page); if (!w.item || w.item.category === 'changed') break; await page.keyboard.press('Enter'); await settle(page, 250); }
    const items = await page.evaluate(() => window.__xrayRevision.items());
    const at = items.findIndex((it) => it.category === 'changed' && /moved|IfcMember|IfcBeam/.test(it.title));
    await page.evaluate((i) => window.__xrayRevision.walk.goto(i), Math.max(0, at));
    await settle(page, 1500);
    const g1 = await walk(page);
    check(`${tag} the ghost of the earlier shape is drawn for a changed element`, g1.ghostDrawn.meshes + g1.ghostDrawn.boxes > 0 && g1.ghostDrawn.frames > 0, JSON.stringify(g1.ghostDrawn));
    await shot(page, 'revision-ghost.png');
    await page.keyboard.press('g');
    await settle(page, 300);
    check(`${tag} G cycles the ghost: head only draws no ghost`, (await walk(page)).ghost === 'head' && (await walk(page)).ghostDrawn.meshes === 0);
    await page.keyboard.press('g'); await page.keyboard.press('g');
    check(`${tag} G comes back to both`, (await walk(page)).ghost === 'both');
    const text = await page.evaluate(() => document.querySelector('[data-role=what-changed]')?.textContent ?? '');
    check(`${tag} the what-changed table says how far it moved`, /moved .* mm/.test(text), text.slice(0, 100));
    await shot(page, 'revision-walk.png');

    // flag one unsure, accept it
    await page.keyboard.press('?');
    await page.keyboard.press('Enter');
    await settle(page, 300);
    const unsureN = (await walk(page)).progress.unsure;
    check(`${tag} Unsure marks the decision`, unsureN >= 1, `${unsureN}`);
    // skip one
    const before = (await walk(page)).progress.skipped;
    await page.keyboard.press('n');
    await settle(page, 300);
    check(`${tag} N skips and the skip is counted`, (await walk(page)).progress.skipped > before);

    // bulk: placement moves up to 10 mm (the 5 mm ones)
    await page.keyboard.press('b');
    await settle(page, 300);
    const rule = await page.evaluate(() => { const r = document.querySelector('[data-rule=placement-moves]'); return { n: Number(r?.querySelector('[data-role=rule-count]')?.textContent ?? -1) }; });
    check(`${tag} the bulk rule counts only the small moves`, rule.n >= 0 && rule.n <= 3, `${rule.n} left`);
    await page.click('[data-rule=placement-moves] [data-act=rule-apply]', { timeout: 120000 });
    await settle(page, 400);
    await page.keyboard.press('Escape');
    await settle(page, 300);
    const bulked = await page.evaluate(() => Object.values(window.__xrayRevision.controller.state.session.decisions).filter((d) => d.bulk === 'placement-moves').length);
    check(`${tag} a bulk accept took exactly the counted changes, as one step`, bulked === rule.n && rule.n > 0, `${bulked} of ${rule.n}`);
    const undoDepth = await page.evaluate(() => window.__xrayRevision.controller.undoStack.length);
    check(`${tag} the decisions so far are undoable`, undoDepth > 0);

    // ---- 5. reload mid-walk, open v2 again, resume
    const mid = await rev(page);
    const decidedBefore = mid.session.progress.decided;
    const keyBefore = mid.session.key;
    await page.evaluate(() => window.__xrayRevision.controller.saver.flush());
    await settle(page, 800);
    await page.reload({ waitUntil: 'domcontentloaded', timeout: 240000 });
    await page.waitForFunction('window.__xrayReady === true && window.__xrayClassify && window.__xrayRevision', null, { timeout: T });
    await openIfc(page, V2, 'file:fzk-v2.ifc');
    await waitBanner(page, /Resume revision review/);
    const rt = await bannerText(page);
    check(`${tag} after a reload the banner offers to resume with the count`, new RegExp(`${decidedBefore} of \\d+ decided`).test(rt), rt.slice(0, 90));
    await page.click('[data-testid=revision-banner] [data-act=resume]');
    await waitWalk(page);
    const back = await rev(page);
    check(`${tag} resume brings the decisions and the cursor back`, back.session.key === keyBefore && back.session.progress.decided === decidedBefore && back.session.progress.skipped === mid.session.progress.skipped, `${back.session.progress.decided} decided`);
    const at2 = await page.evaluate(() => {
      const c = window.__xrayRevision.controller;
      const keys = new Set(c.state.session.diff.entries.filter((e) => e.flags.includes('placement') && e.move > 0.1).map((e) => `changed:${e.key}`));
      return window.__xrayRevision.items().findIndex((i) => keys.has(i.key));
    });
    await page.evaluate((i) => window.__xrayRevision.walk.goto(i), Math.max(0, at2));
    await settle(page, 1200);
    const g2 = await walk(page);
    check(`${tag} the ghosts survive a reload (the meshes are stored in the browser)`, g2.ghostDrawn.meshes > 0 && g2.ghostDrawn.frames > 0, JSON.stringify(g2.ghostDrawn));

    // ---- finish by keyboard: accept everything that is left
    for (let i = 0; i < 80; i++) {
      const w = await walk(page);
      if (!w.item) break;
      await page.keyboard.press('Enter');
      await settle(page, 120);
    }
    // revisit the skipped ones through the Filters tab (Only skipped), as a user would
    if ((await rev(page)).session.progress.undecided > 0) {
      await page.click('[data-tab=filters]');
      await page.check('[data-role=filter-skipped]');
      await page.click('[data-act=to-walk]');
      await settle(page, 600);
      for (let i = 0; i < 40; i++) {
        const w = await walk(page);
        if (!w.item || (await rev(page)).session.progress.undecided === 0) break;
        await page.keyboard.press('Enter');
        await settle(page, 150);
      }
    }
    const fin = await rev(page);
    check(`${tag} the keyboard walk finishes: nothing is undecided and the session is finished`, fin.session.progress.undecided === 0 && fin.session.status === 'finished', JSON.stringify(fin.session.progress));

    // commit, then export the report
    await page.fill('[data-role=reviewer]', NAME).catch(() => undefined);
    const c = await page.evaluate(() => window.__xrayRevision.commit('smoke'));
    check(`${tag} Commit writes the accepted changes and carries the matched decisions`, c.changes >= 1, JSON.stringify(c));
    await page.click('[data-tab=report]');
    await settle(page, 300);
    await page.click('[data-act=export-report]');
    await settle(page, 1200);
    const rep = await page.evaluate(() => window.__xrayRevision.report());
    const rows = rep.csv.trim().split(/\r?\n/).length - 1;
    check(`${tag} the report has a row per changed element, rejected ones included`, rows === fin.session.progress.total && /rejected/.test(rep.csv), `${rows} rows`);
    check(`${tag} the report file names and two downloads`, downloads.some((d) => /^revision-.*\.csv$/.test(d)) && downloads.some((d) => /-summary\.md$/.test(d)), downloads.join(', '));
    const status = await page.evaluate(async () => { const m = await window.__xrayRevision.status(); const v = m ? [...m.values()] : []; return { n: v.length, changed: v.filter((x) => x.status === 'changed').length, base: v[0]?.baseline }; });
    check(`${tag} the RevisionStatus hand-off gives every element a status and the baseline name`, status.n === 81 && status.changed === 14 && status.base === 'file:AC20-FZK-Haus.ifc', JSON.stringify(status));
    await settle(page, 500);
  } catch (e) {
    check(`${tag} run completed`, false, e instanceof Error ? e.stack : String(e));
    await shot(page, 'revision-walk-failure.png').catch(() => undefined);
  }
  check(`${tag} zero console errors`, errors.length === 0, errors.slice(0, 3).join(' | '));
  await ctx.close();
}

async function runPhone(browser) {
  const tag = '[phone]';
  const { ctx, page, errors } = await openPage(browser, { viewport: { width: 390, height: 844 }, touch: true });
  try {
    await prepare(page);
    await waitBanner(page, /revision of file:AC20-FZK-Haus\.ifc/);
    await page.tap('[data-testid=revision-banner] [data-act=review-changes]');
    await waitWalk(page);
    const lay = await page.evaluate(() => {
      const r = document.querySelector('[data-testid=revision-walk]').getBoundingClientRect();
      const acts = [...document.querySelectorAll('[data-testid=revision-walk] .xrr-acts button')].filter((b) => b.offsetParent !== null);
      const inView = acts.every((b) => { const q = b.getBoundingClientRect(); return q.top >= 0 && q.bottom <= window.innerHeight && q.left >= 0 && q.right <= window.innerWidth; });
      return { top: r.top, h: r.height, w: r.width, vh: window.innerHeight, vw: window.innerWidth, labels: acts.map((b) => b.dataset.act), inView, handle: !!document.querySelector('.xrr-handle') && getComputedStyle(document.querySelector('.xrr-handle')).display !== 'none', scrollX: document.documentElement.scrollWidth <= window.innerWidth };
    });
    check(`${tag} the panel is a bottom sheet of about 45 % of the height`, lay.h / lay.vh > 0.3 && lay.h / lay.vh < 0.6 && lay.w <= lay.vw + 1, `${Math.round((lay.h / lay.vh) * 100)} %`);
    check(`${tag} Accept, Reject, Skip and More are on screen, with a drag handle`, ['accept', 'reject', 'skip', 'more'].every((a) => lay.labels.includes(a)) && lay.inView && lay.handle, lay.labels.join(','));
    check(`${tag} the page does not scroll sideways`, lay.scrollX);
    await shot(page, 'revision-phone.png');
    // swipe left = skip, swipe right = back
    const swipe = (dx) => page.evaluate((d) => {
      const body = document.querySelector('[data-testid=revision-walk] .xrw-body');
      const r = body.getBoundingClientRect();
      const mk = (x) => new Touch({ identifier: 1, target: body, clientX: x, clientY: r.top + 30 });
      const x0 = r.left + r.width / 2;
      body.dispatchEvent(new TouchEvent('touchstart', { touches: [mk(x0)], changedTouches: [mk(x0)], bubbles: true }));
      body.dispatchEvent(new TouchEvent('touchend', { touches: [], changedTouches: [mk(x0 + d)], bubbles: true }));
    }, dx);
    const s0 = (await rev(page)).session.progress.skipped;
    await swipe(-140);
    await settle(page, 400);
    const s1 = (await rev(page)).session.progress.skipped;
    const i1 = (await walk(page)).itemIndex;
    await swipe(140);
    await settle(page, 400);
    check(`${tag} swipe left skips and swipe right goes back`, s1 > s0 && (await walk(page)).itemIndex < i1, `skipped ${s0} to ${s1}`);
    // tap the chips open on a change, tap Accept to the end
    for (let i = 0; i < 80; i++) {
      const w = await walk(page);
      if (!w.item) break;
      await page.tap('[data-act=accept]');
      await settle(page, 150);
    }
    for (let i = 0; i < 20; i++) {
      const p = (await rev(page)).session.progress;
      if (p.undecided === 0) break;
      await page.evaluate(() => window.__xrayRevision.walk.goto(0));
      for (let k = 0; k < 40 && (await walk(page)).item; k++) { await page.tap('[data-act=accept]'); await settle(page, 120); }
    }
    const fin = await rev(page);
    check(`${tag} the touch-only walk finishes`, fin.session.progress.undecided === 0 && fin.session.status === 'finished', JSON.stringify(fin.session.progress));
    // More opens bulk and filters
    const more = await page.evaluate(() => { window.__xrayRevision.walk.goto(0); return !!document.querySelector('[data-act=more]'); });
    check(`${tag} More is reachable for bulk and filters`, more);
  } catch (e) {
    check(`${tag} run completed`, false, e instanceof Error ? e.stack : String(e));
    await shot(page, 'revision-phone-failure.png').catch(() => undefined);
  }
  check(`${tag} zero console errors`, errors.length === 0, errors.slice(0, 3).join(' | '));
  await ctx.close();
}

const only = process.env.SMOKE_ONLY ?? '';
let browser;
try {
  await waitForServer();
  browser = await chromium.launch({ args: GL });
  console.log('NOTE steps 1, 2 and the RevisionStatus-in-the-saved-file check of step 6 need ticket T2 (Save IFC, another branch): skipped here.');
  if (only !== 'phone') await runDesktop(browser);
  if (only !== 'desktop') await runPhone(browser);
} catch (e) {
  check('smoke completed', false, e instanceof Error ? e.stack : String(e));
} finally {
  await browser?.close().catch(() => undefined);
  vite.kill('SIGTERM');
}
const failed = checks.filter((c) => !c.ok);
console.log(`\n${checks.length - failed.length} of ${checks.length} checks passed`);
process.exit(failed.length ? 1 : 0);
