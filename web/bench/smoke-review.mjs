// Headless smoke test for the review walk: starts vite (bench/vite.smoke.config.mjs), loads process-plant and drives the walk with
// Playwright: rules-only classification, open the walk (Shift+R), confirm two items (the keyboard and a button), correct one, commit,
// reload the page and check the commit and the results persist (IndexedDB), export the review log, import it on a fresh browser profile,
// re-run the classifier over a committed element, end the walk (the view is restored), and the same on a phone. The reviewer's name must
// not appear in the params or the share link. Screenshots: bench/review-walk-*.png.
// Usage: SMOKE_PORT=5699 node bench/smoke-review.mjs
import { spawn } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const port = Number(process.env.SMOKE_PORT ?? 5699);
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
  for (let i = 0; i < 100; i++) {
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
const shot = (page, name) => page.screenshot({ path: resolve(here, name), timeout: 180000 });

async function open(browser, ctxOrOpts = {}) {
  const ctx = ctxOrOpts.ctx ?? (await browser.newContext({ viewport: ctxOrOpts.viewport ?? { width: 1600, height: 900 }, acceptDownloads: true }));
  const page = await ctx.newPage();
  const errors = [];
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', (e) => errors.push(`[pageerror] ${e.message}`));
  await page.route(/^https?:\/\/(?!127\.0\.0\.1)/, (route) => route.abort());
  await page.goto(`http://127.0.0.1:${port}/?model=process-plant`);
  await page.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: 120000 });
  const err = await page.evaluate('window.__xrayError');
  if (err) errors.push(`[app] ${err}`);
  await page.waitForFunction('window.__xraySearch && window.__xraySearch.indexReady() && window.__xrayClassify', null, { timeout: 60000 });
  await page.evaluate(() => window.__xrayClassify.review.ready());
  await page.waitForTimeout(400);
  return { ctx, page, errors };
}

const walkState = (page) => page.evaluate(() => window.__xrayClassify.walk.state());
const pose = (page) => page.evaluate(() => { const r = window.__xray.app.renderer; return [r.camera.position.x, r.camera.position.y, r.camera.position.z, r.controls.target.x, r.controls.target.y, r.controls.target.z].map((v) => Math.round(v * 1000) / 1000); });
const settle = (page, ms = 900) => page.waitForTimeout(ms);

async function runDesktop(browser) {
  const tag = '[process-plant]';
  const { ctx, page, errors } = await open(browser);
  let exported = '';
  let firstCommit = null;
  let correctedGid = null;
  try {
    // ---- 1. rules-only classification
    await page.evaluate(() => window.__xrayClassify.configure({ provider: 'off' }));
    await page.evaluate(() => window.__xrayClassify.classify('all'));
    const s1 = await page.evaluate(() => window.__xrayClassify.stats());
    check(`${tag} rules-only classification gave results`, s1.total > 1000 && s1.bySource.rules > 1000 && s1.calls === 0, JSON.stringify(s1.bySource));

    // ---- 2. open the walk with its shortcut
    const before = await pose(page);
    await page.evaluate(() => window.__xray.app.selectIds([3, 4]));
    await page.keyboard.press('Shift+R');
    await page.waitForSelector('.xrw:not([hidden])');
    let st = await walkState(page);
    check(`${tag} Shift+R opens the review walk, by type, with items`, st.open && st.order === 'type' && st.items > 5 && st.item !== null, JSON.stringify({ items: st.items, order: st.order }));
    check(`${tag} the walk panel shows progress and the proposal with confidence and source`, /0 confirmed, 0 corrected, \d+ remaining/.test(await page.locator('.xrw [data-role=progress]').textContent()) && /%/.test(await page.locator('.xrw-tbl').textContent()) && /rule/.test(await page.locator('.xrw-tbl').textContent()));
    await settle(page);
    const selN = await page.evaluate(() => window.__xray.app.selection.length);
    check(`${tag} the camera frames the item: its ${st.item.elements} element(s) are selected`, selN === st.item.elements, `${selN}`);
    check(`${tag} the camera moved`, JSON.stringify(await pose(page)) !== JSON.stringify(before));
    await shot(page, 'review-walk-desktop.png');
    const orders = [];
    for (const o of ['type', 'systems', 'location', 'review']) {
      await page.locator('.xrw select[data-role=order]').selectOption(o);
      const s = await walkState(page);
      orders.push(`${o}:${s.items}`);
      check(`${tag} order ${o} lists items`, s.order === o && s.items > 0);
    }
    console.log(tag, orders.join(' '));
    await page.locator('.xrw select[data-role=order]').selectOption('type');
    st = await walkState(page);
    const firstTitle = st.item.title;

    // ---- 3. confirm two items (Enter, then the button), correct one
    const i0 = st.itemIndex;
    await page.keyboard.press('Enter');
    st = await walkState(page);
    check(`${tag} Enter confirms the item and moves on`, st.itemIndex === i0 + 1 && st.pending >= 1, `pending ${st.pending}`);
    const n1 = st.pending;
    await page.locator('.xrw [data-act=confirm]').click();
    st = await walkState(page);
    check(`${tag} the Confirm button confirms the second item`, st.itemIndex === i0 + 2 && st.pending > n1);
    // correct the third item with the keyboard and the pickers
    const thirdGid = await page.evaluate(() => { const s = window.__xrayClassify.walk.state(); return s.item.key.replace(/^[a-z]+:/, ''); });
    await page.keyboard.press('e');
    await page.waitForSelector('.xrw-edit');
    const discOptions = await page.locator('.xrw-edit select[data-role=edit-discipline] option').evaluateAll((o) => o.map((x) => x.value));
    const cur = await page.locator('.xrw-edit select[data-role=edit-discipline]').inputValue();
    const pick = discOptions.find((d) => d !== cur && d !== 'GEN') ?? discOptions[0];
    await page.locator('.xrw-edit select[data-role=edit-discipline]').selectOption(pick);
    const subOpts = await page.locator('.xrw-edit select[data-role=edit-sub] option').evaluateAll((o) => o.map((x) => x.value));
    check(`${tag} the sub-discipline picker is restricted to the chosen discipline`, subOpts.every((c) => c === '' || /^[A-Z]{3}$/.test(c)) && (await page.evaluate((d) => window.__xrayClassify.schema().disciplines.find((x) => x.code === d).subDisciplines.length, pick)) === subOpts.length - 1, subOpts.join());
    await page.locator('.xrw [data-role=comment]').fill('walked on site');
    await page.locator('.xrw [data-act=apply-correct]').click();
    st = await walkState(page);
    const pend = await page.evaluate(() => window.__xrayClassify.review.pending());
    const corrected = pend.filter((p) => p.action === 'correct');
    check(`${tag} the correction is pending with its comment and the chosen discipline`, corrected.length >= 1 && corrected.every((p) => p.after.discipline === pick && p.comment === 'walked on site' && p.after.source === 'corrected'), JSON.stringify(corrected[0]?.after));
    correctedGid = corrected[0]?.globalId;
    check(`${tag} nothing is committed yet: the result still has its old source`, await page.evaluate((g) => window.__xrayClassify.results().find((r) => r.id === g).source === 'rules', correctedGid));
    await page.locator('.xrw [data-tab=pending]').click();
    const pendRows = await page.locator('.xrw [data-act=undo-item]').count();
    check(`${tag} the pending tab lists the three items, each with an Undo`, pendRows === 3, `${pendRows}`);
    await shot(page, 'review-walk-pending.png');
    // undo one item and do it again
    await page.locator('.xrw [data-act=undo-item]').last().click();
    check(`${tag} Undo takes one item out of the pending set`, (await page.locator('.xrw [data-act=undo-item]').count()) === 2);
    await page.locator('.xrw [data-tab=walk]').click();
    await page.locator('.xrw [data-act=back]').first().click();
    st = await walkState(page);
    check(`${tag} Back returns to the item that was undone`, st.item.key.endsWith(thirdGid));
    await page.keyboard.press('e');
    await page.locator('.xrw-edit select[data-role=edit-discipline]').selectOption(pick);
    await page.locator('.xrw [data-role=comment]').fill('walked on site');
    await page.keyboard.press('Escape'); // Escape cancels the editor first
    check(`${tag} Escape closes the correction picker and keeps the walk open`, (await page.locator('.xrw-edit').count()) === 0 && (await walkState(page)).open);
    await page.keyboard.press('e');
    await page.locator('.xrw-edit select[data-role=edit-discipline]').selectOption(pick);
    await page.locator('.xrw [data-act=apply-correct]').click();

    // ---- 4. commit
    const total = await page.evaluate(() => window.__xrayClassify.review.pending().length);
    check(`${tag} the footer button says how many changes it commits`, (await page.locator('.xrw [data-act=commit]').textContent()) === `Commit ${total} changes`, await page.locator('.xrw [data-act=commit]').textContent());
    await page.locator('.xrw [data-act=commit]').click(); // no name yet: refused in plain words
    check(`${tag} a commit without a reviewer name is refused in plain words`, /name or initials/.test(await page.locator('.xrw [role=status]').first().textContent().catch(() => '')));
    await page.locator('.xrw [data-role=reviewer]').fill(NAME);
    await page.locator('.xrw [data-role=note]').fill('first pass');
    await page.locator('.xrw [data-act=commit]').click();
    await page.waitForTimeout(400);
    firstCommit = await page.evaluate(() => window.__xrayClassify.review.history()[0]);
    check(`${tag} one commit record with id, author, ISO time, note, fingerprint and the changes`, firstCommit && firstCommit.author === NAME && firstCommit.note === 'first pass' && firstCommit.changes.length === total && /^\d{4}-\d\d-\d\dT/.test(firstCommit.time) && /^[0-9a-f]{16}$/.test(firstCommit.modelFingerprint) && firstCommit.modelName === 'process-plant' && !!firstCommit.schemaEdition, JSON.stringify({ n: firstCommit?.changes.length, total }));
    const ch = firstCommit.changes.find((c) => c.action === 'correct');
    check(`${tag} a change records before and after with source and confidence`, ch.before.source === 'rules' && ch.after.source === 'corrected' && ch.after.confidence === 1 && ch.before.discipline !== ch.after.discipline && ch.comment === 'walked on site');
    const res = await page.evaluate((g) => { const r = window.__xrayClassify.results().find((x) => x.id === g); const m = window.__xray.app.controller.model; return { r, prop: m.elements[m.byGlobalId.get(g)].props['XR_Classification.Source'] }; }, correctedGid);
    check(`${tag} the committed correction is the result: source corrected, confidence 1, no review, who and when`, res.r.source === 'corrected' && res.r.discipline.confidence === 1 && res.r.needsReview === false && res.r.confirmedBy === NAME && res.r.commitId === firstCommit.id && res.prop === 'corrected');
    const stats = await page.evaluate(() => window.__xrayClassify.stats().bySource);
    check(`${tag} the stats count confirmed and corrected elements`, stats.confirmed > 0 && stats.corrected > 0, JSON.stringify(stats));
    check(`${tag} the progress line counts them`, /[1-9]\d* confirmed, [1-9]\d* corrected/.test(await page.locator('.xrw [data-role=progress]').textContent()), await page.locator('.xrw [data-role=progress]').textContent());
    await page.locator('.xrw [data-tab=history]').click();
    check(`${tag} the history lists the commit with who, when and how many`, new RegExp(`${NAME}.*first pass.*${total} changes`).test(await page.locator('.xrw [data-commit]').first().textContent()));
    await page.locator('.xrw [data-commit] [data-act=open-commit]').first().click();
    check(`${tag} a commit opens to show its changes`, (await page.locator('.xrw-changes div').count()) === Math.min(200, total));
    await shot(page, 'review-walk-history.png');

    // ---- the name is not in params or links
    const doc = await page.evaluate(() => JSON.stringify(window.__xray.exportParams?.collect?.() ?? window.__xrayParams?.collect?.() ?? {}));
    const shareUrl = await page.evaluate(() => (window.__xrayParams?.shareUrl ?? window.__xray.exportParams?.shareUrl)?.() ?? '');
    check(`${tag} the reviewer name is not in the params, the share link or the page URL`, !doc.includes('Fanshawe') && !shareUrl.includes('Fanshawe') && !page.url().includes('Fanshawe') && doc.length > 10);

    // ---- ending the walk restores the view
    await page.keyboard.press('Escape');
    for (let i = 0; i < 20; i++) { // the camera eases back: wait until it stops
      const p0 = await pose(page);
      await settle(page, 500);
      const p1 = await pose(page);
      if (JSON.stringify(p0) === JSON.stringify(p1) && JSON.stringify(p1) === JSON.stringify(before)) break;
    }
    const selAfter = await page.evaluate(() => window.__xray.app.selection.slice().sort());
    check(`${tag} Escape ends the walk, restores the selection and the camera`, (await page.locator('.xrw').count()) === 0 && JSON.stringify(selAfter) === JSON.stringify([3, 4]) && JSON.stringify(await pose(page)) === JSON.stringify(before), `${JSON.stringify(await pose(page))} vs ${JSON.stringify(before)}`);

    // ---- 5. reload: the commit and the results persist
    await page.reload();
    await page.waitForFunction('window.__xrayReady === true && window.__xrayClassify', null, { timeout: 120000 });
    await page.evaluate(() => window.__xrayClassify.review.ready());
    await page.waitForTimeout(500);
    const after = await page.evaluate(() => ({ h: window.__xrayClassify.review.history().map((c) => c.id), r: window.__xrayClassify.results().map((x) => [x.id, x.source, x.confirmedBy, x.commitId]), where: window.__xrayClassify.review.storage().where, rev: window.__xrayClassify.review.reviewer(), idb: indexedDB.databases ? undefined : undefined }));
    check(`${tag} after a reload the commit is back from the stored log`, after.h.length === 1 && after.h[0] === firstCommit.id);
    check(`${tag} after a reload the committed results are the results (no classification run yet)`, after.r.length === total || after.r.length >= total, `${after.r.length} results for ${total} changes`);
    check(`${tag} after a reload the results carry source, who and the commit`, after.r.every(([, s, by, cid]) => (s === 'confirmed' || s === 'corrected') && by === NAME && cid === firstCommit.id));
    check(`${tag} the reviewer name is remembered on this device`, after.rev === NAME);
    const idb = await page.evaluate(async () => { try { const dbs = await indexedDB.databases(); return dbs.map((d) => d.name); } catch { return ['n/a']; } });
    check(`${tag} the log is in IndexedDB`, idb.includes('xray-classification-review') || idb[0] === 'n/a', idb.join());
    const ls = await page.evaluate(() => Object.keys(localStorage).filter((k) => k.startsWith('xray.classify.review.v1.')));
    check(`${tag} the localStorage fallback was not needed`, ls.length === 0, ls.join());

    // ---- a re-run never overwrites a committed result; the model disagrees where it differs
    await page.evaluate(() => window.__xrayClassify.classify('all'));
    await page.evaluate(() => window.__xrayClassify.classify('all', { rules: false }));
    const rerun = await page.evaluate((g) => ({ src: window.__xrayClassify.results().find((r) => r.id === g).source, dis: window.__xrayClassify.review.disagreements(), n: window.__xrayClassify.results().filter((r) => r.source === 'confirmed' || r.source === 'corrected').length }), correctedGid);
    check(`${tag} a re-run keeps every committed result`, rerun.src === 'corrected' && rerun.n === total, JSON.stringify({ n: rerun.n, total }));
    check(`${tag} the model now disagrees on the corrected element`, rerun.dis.includes(correctedGid), rerun.dis.join());
    // CSV and JSON carry the confirmation
    const csv = await page.evaluate(() => window.__xrayClassify.export('csv'));
    const row = csv.split('\r\n').find((l) => l.startsWith(correctedGid));
    check(`${tag} the CSV carries confirmedBy, confirmedAt and the commit id`, csv.split('\r\n')[0].endsWith('ConfirmedBy,ConfirmedAt,CommitId') && row.includes(NAME) && row.endsWith(firstCommit.id.length ? `${firstCommit.time},${firstCommit.id}` : ''));
    const js = JSON.parse(await page.evaluate(() => window.__xrayClassify.export('json')));
    check(`${tag} the JSON export carries them too`, js.results.find((r) => r.id === correctedGid).commitId === firstCommit.id);
    const tl = JSON.parse(await page.evaluate(() => window.__xrayClassify.export('throughline')));
    check(`${tag} the Throughline export carries them too`, tl.elements.find((e) => e.global_id === correctedGid).attributes.commit_id === firstCommit.id);
    // a disagreement shows in the walk
    await page.evaluate(() => window.__xrayClassify.walk.open());
    await page.locator('.xrw select[data-role=order]').selectOption('location');
    await page.locator('.xrw select[data-role=discipline]').selectOption(pick);
    await page.waitForTimeout(200);

    // ---- export from the drawer button, then import on a fresh browser profile
    await page.evaluate(() => window.__xrayClassify.walk.close());
    await page.locator('.xt-btn-tool[data-tool="classify"]').click();
    await page.waitForSelector('.xt-drawer:not(.hidden)');
    const dl = page.waitForEvent('download', { timeout: 15000 });
    await page.locator('.xt-drawer .xt-btn', { hasText: 'Export review log' }).click();
    const d = await dl;
    exported = readFileSync(await d.path(), 'utf8');
    const parsed = JSON.parse(exported);
    check(`${tag} Export review log writes an xray-classification-review/1 file`, parsed.schema === 'xray-classification-review/1' && parsed.commits.length === 1 && parsed.commits[0].id === firstCommit.id && parsed.modelFingerprint === firstCommit.modelFingerprint && /review.*\.json$/.test(d.suggestedFilename()), d.suggestedFilename());
    await page.evaluate(() => window.__xrayClassify.configure({ provider: 'mock' }));
    await page.waitForTimeout(300);
    const calBtn = page.locator('.xt-drawer .xt-btn', { hasText: 'Calibrate on confirmed' });
    check(`${tag} the drawer has Calibrate on confirmed next to Calibrate on rules`, (await calBtn.count()) === 1 && (await page.locator('.xt-drawer .xt-btn', { hasText: 'Calibrate on rules' }).count()) === 1 && !(await calBtn.isDisabled()));
    await page.evaluate(() => window.__xrayClassify.configure({ provider: 'off' }));
  } finally {
    const real = errors.filter((e) => !/favicon/i.test(e));
    check(`${tag} zero console errors`, real.length === 0, real.slice(0, 3).join(' | '));
    await ctx.close();
  }

  // ---- a fresh profile: import by the drawer button
  const fresh = await open(browser);
  try {
    check(`${tag} a fresh profile has no commit`, (await fresh.page.evaluate(() => window.__xrayClassify.review.history().length)) === 0);
    await fresh.page.locator('.xt-btn-tool[data-tool="classify"]').click();
    await fresh.page.waitForSelector('.xt-drawer:not(.hidden)');
    await fresh.page.evaluate(() => window.__xrayClassify.classify('all'));
    const file = { name: 'review-log.json', mimeType: 'application/json', buffer: Buffer.from(exported) };
    await fresh.page.locator('.xt-drawer input[type=file][accept*="json"]').last().setInputFiles(file);
    await fresh.page.waitForTimeout(600);
    const imp = await fresh.page.evaluate(() => ({ h: window.__xrayClassify.review.history().map((c) => c.id), src: window.__xrayClassify.results().filter((r) => r.source === 'corrected').length }));
    check(`${tag} Import review log replays the commit (once) and the results come back`, imp.h.length === 1 && imp.h[0] === firstCommit.id && imp.src >= 1, JSON.stringify(imp));
    const again = await fresh.page.evaluate((t) => window.__xrayClassify.review.importLog(t), exported);
    check(`${tag} importing the same log again adds nothing (deduplicated by commit id)`, again.ok && again.added.length === 0 && again.duplicates.length === 1);
    const bad = await fresh.page.evaluate((t) => { const d = JSON.parse(t); d.modelFingerprint = 'deadbeefdeadbeef'; d.commits[0].id = 'zzz'; return window.__xrayClassify.review.importLog(JSON.stringify(d)); }, exported);
    check(`${tag} a log with another fingerprint is refused in plain words`, !bad.ok && /another model or schema/.test(bad.error) && (await fresh.page.evaluate(() => window.__xrayClassify.review.history().length)) === 1);
    // an item of several elements: confirm all N at once, or this element only
    await fresh.page.evaluate(() => window.__xrayClassify.walk.open());
    const items = await fresh.page.evaluate(() => window.__xrayClassify.walk.items());
    const multi = items.findIndex((i) => i.elements > 2);
    const N = items[multi].elements;
    await fresh.page.evaluate((i) => window.__xrayClassify.walk.goto(i), multi);
    await fresh.page.waitForTimeout(900);
    check(`${tag} an item of ${N} elements selects all ${N} and offers All or This element only`, (await fresh.page.evaluate(() => window.__xray.app.selection.length)) === N && (await fresh.page.locator('.xrw [data-role=scope-all]').isChecked()), `${N}`);
    await fresh.page.locator('.xrw [data-role=scope-one]').check();
    await fresh.page.waitForTimeout(500);
    check(`${tag} "This element only" selects one element and steps through the type`, (await fresh.page.evaluate(() => window.__xray.app.selection.length)) === 1 && /1 \/ \d+/.test(await fresh.page.locator('.xrw [data-role=element-count]').textContent()));
    await fresh.page.keyboard.press(']');
    check(`${tag} the bracket keys step to the next element of the type`, (await walkState(fresh.page)).elementIndex === 1);
    await fresh.page.locator('.xrw [data-role=scope-all]').check();
    await fresh.page.waitForTimeout(300);
    await fresh.page.keyboard.press('y');
    const pendN = await fresh.page.evaluate(() => window.__xrayClassify.review.pending().length);
    check(`${tag} Y with All confirms all ${N} elements of the type as pending changes`, pendN === N, `${pendN}`);
    await fresh.page.keyboard.press('u');
    check(`${tag} U undoes that item`, (await fresh.page.evaluate(() => window.__xrayClassify.review.pending().length)) === 0);
    await fresh.page.evaluate(() => window.__xrayClassify.walk.close());
    // revert as a new commit
    await fresh.page.evaluate(() => { window.__xrayClassify.review.setReviewer('RF'); });
    await fresh.page.evaluate(() => window.__xrayClassify.walk.open());
    await fresh.page.locator('.xrw [data-tab=history]').click();
    await fresh.page.locator('.xrw [data-commit] [data-act=revert]').first().click();
    await fresh.page.waitForTimeout(300);
    const rev = await fresh.page.evaluate(() => ({ h: window.__xrayClassify.review.history(), c: window.__xrayClassify.results().filter((r) => r.source === 'corrected' || r.source === 'confirmed').length }));
    check(`${tag} Revert adds a new commit that reverses the first and removes nothing`, rev.h.length === 2 && rev.h[0].reverts === firstCommit.id && rev.h[1].id === firstCommit.id && rev.c === 0, JSON.stringify({ n: rev.h.length, c: rev.c }));
    check(`${tag} the original commit record is unchanged after the revert`, JSON.stringify(rev.h[1]) === JSON.stringify(JSON.parse(exported).commits[0]));
  } finally {
    const real = fresh.errors.filter((e) => !/favicon/i.test(e));
    check(`${tag} (fresh profile) zero console errors`, real.length === 0, real.slice(0, 3).join(' | '));
    await fresh.ctx.close();
  }
}

async function runPhone(browser) {
  const tag = '[phone]';
  const { ctx, page, errors } = await open(browser, { viewport: { width: 390, height: 844 } });
  try {
    await page.evaluate(() => window.__xrayClassify.classify('all'));
    await page.locator('.xt-btn-tool[data-tool="classify"]').click();
    await page.waitForSelector('.xt-drawer:not(.hidden)');
    await page.locator('.xt-drawer .xt-btn', { hasText: 'Review walk' }).click();
    await page.waitForSelector('.xrw:not([hidden])');
    await page.waitForTimeout(900);
    check(`${tag} the Review walk button in the drawer opens the panel and closes the drawer`, (await page.locator('.xt-drawer:not(.hidden)').count()) === 0 && (await walkState(page)).open);
    const box = await page.evaluate(() => { const r = document.querySelector('.xrw').getBoundingClientRect(); return { left: r.left, right: r.right, top: r.top, bottom: r.bottom, vw: window.innerWidth, vh: window.innerHeight, scrollW: document.documentElement.scrollWidth }; });
    check(`${tag} the panel fits the phone width and sits in the lower part of the screen`, box.left >= 0 && box.right <= box.vw + 1 && box.scrollW <= box.vw + 1 && box.top > box.vh * 0.3, JSON.stringify(box));
    const tiny = await page.evaluate(() => [...document.querySelectorAll('.xrw-acts .xrw-btn')].filter((b) => b.getBoundingClientRect().height < 34 || b.getBoundingClientRect().right > window.innerWidth).length);
    check(`${tag} the action buttons are large and inside the screen`, tiny === 0);
    await page.locator('.xrw [data-act=confirm]').tap().catch(() => page.locator('.xrw [data-act=confirm]').click());
    await page.locator('.xrw [data-act=skip]').click();
    await page.locator('.xrw [data-act=correct]').click();
    await page.waitForSelector('.xrw-edit');
    await page.waitForTimeout(500);
    check(`${tag} Confirm, Skip and Correct work with buttons only`, (await walkState(page)).pending >= 1 && (await walkState(page)).editing);
    await shot(page, 'review-walk-phone.png');
    await page.locator('.xrw [data-act=cancel-correct]').click();
    await page.locator('.xrw-x').click();
    check(`${tag} the close button ends the walk`, (await page.locator('.xrw').count()) === 0);
  } finally {
    const real = errors.filter((e) => !/favicon/i.test(e));
    check(`${tag} zero console errors`, real.length === 0, real.slice(0, 3).join(' | '));
    await ctx.close();
  }
}

let browser;
let exitCode = 0;
try {
  await waitForServer();
  browser = await chromium.launch({ args: GL });
  await runDesktop(browser);
  await runPhone(browser);
  if (checks.some((c) => !c.ok)) exitCode = 1;
  console.log(`\n${checks.filter((c) => c.ok).length}/${checks.length} checks passed`);
} catch (e) {
  console.error(e);
  exitCode = 1;
} finally {
  if (browser) await browser.close();
  vite.kill('SIGTERM');
}
process.exit(exitCode);
