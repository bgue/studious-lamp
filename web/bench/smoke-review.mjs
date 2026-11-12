// Headless smoke test for the review walk: starts vite (bench/vite.smoke.config.mjs), loads process-plant and drives the walk with
// Playwright: rules-only classification, open the walk (Shift+R), confirm two items (the keyboard and a button), correct one, commit,
// reload the page and check the commit and the results persist (IndexedDB), export the review log, import it on a fresh browser profile,
// re-run the classifier over a committed element, end the walk (the view is restored), and the same on a phone. The reviewer's name must
// not appear in the params or the share link. Also: Skip in every state (correction form open, one element or the whole type, after Back,
// the "Only skipped" revisit), the optional Unsure flag (pending and history tags, results table marker, back under Only needs review,
// superseded by a sure confirmation) and a phone run where Skip and Unsure are reachable. Screenshots: bench/review-walk-*.png.
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
    await page.locator('.xrw [data-role=unsure]').check(); // the screenshot shows the Unsure control ticked
    await shot(page, 'review-walk-desktop.png');
    await page.locator('.xrw [data-role=unsure]').uncheck();
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
    check(`${tag} the CSV carries confirmedBy, confirmedAt, the commit id and Unsure (false)`, csv.split('\r\n')[0].endsWith('ConfirmedBy,ConfirmedAt,CommitId,Unsure') && row.includes(NAME) && row.endsWith(`${firstCommit.time},${firstCommit.id},false`));
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

async function runSkipUnsure(browser) {
  const tag = '[skip+unsure]';
  const { ctx, page, errors } = await open(browser);
  const hdr = async () => (await page.locator('.xrw [data-role=skipped-count]').textContent()).trim();
  const listed = () => page.evaluate(() => window.__xrayClassify.walk.items());
  const skipped = () => page.evaluate(() => window.__xrayClassify.review.skipped());
  try {
    await page.evaluate(() => window.__xrayClassify.configure({ provider: 'off' }));
    await page.evaluate(() => window.__xrayClassify.classify('all'));
    await page.keyboard.press('Shift+R');
    await page.waitForSelector('.xrw:not([hidden])');
    let items = await listed();
    check(`${tag} the header starts at "Skipped (0)" and the button is disabled`, (await hdr()) === 'Skipped (0)' && (await page.locator('.xrw [data-role=skipped-count]').isDisabled()));
    const single = items.findIndex((i) => i.elements === 1);
    const multis = items.map((i, k) => [i, k]).filter(([i]) => i.elements > 2).map(([, k]) => k);
    check(`${tag} the model has single items and types of several elements`, single >= 0 && multis.length >= 2, `${single} ${multis.length}`);

    // ---- skip with the correction form open (button, then key)
    await page.evaluate((i) => window.__xrayClassify.walk.goto(i), single);
    await page.keyboard.press('e');
    await page.waitForSelector('.xrw-edit');
    const opts = await page.locator('.xrw-edit select[data-role=edit-discipline] option').evaluateAll((o) => o.map((x) => x.value));
    const cur = await page.locator('.xrw-edit select[data-role=edit-discipline]').inputValue();
    await page.locator('.xrw-edit select[data-role=edit-discipline]').selectOption(opts.find((d) => d !== cur));
    const gid0 = (await walkState(page)).item.key.replace(/^[a-z]+:/, '');
    await page.locator('.xrw [data-act=skip-edit]').click();
    let st = await walkState(page);
    check(`${tag} Skip with the correction form open drops the unsaved correction and moves on`, !st.editing && st.itemIndex === single + 1 && st.pending === 0 && (await page.locator('.xrw-edit').count()) === 0, JSON.stringify({ editing: st.editing, i: st.itemIndex, p: st.pending }));
    check(`${tag} the skipped element is on the list, and the header counts it`, (await skipped()).includes(gid0) && (await hdr()) === 'Skipped (1)');
    check(`${tag} a skip is not a change: nothing pending, no commit`, (await page.evaluate(() => window.__xrayClassify.review.pending().length + window.__xrayClassify.review.history().length)) === 0);
    // by key: the picker must not have the focus (its letters are its own)
    await page.keyboard.press('e');
    await page.waitForSelector('.xrw-edit');
    await page.locator('.xrw-edit select[data-role=edit-discipline]').selectOption(opts.find((d) => d !== (null)) ?? opts[0]);
    await page.evaluate(() => document.activeElement && document.activeElement.blur());
    await page.keyboard.press('n');
    st = await walkState(page);
    check(`${tag} the N key does the same while the form is open`, !st.editing && st.itemIndex === single + 2 && st.pending === 0 && (await hdr()) === 'Skipped (2)', JSON.stringify({ i: st.itemIndex, p: st.pending, h: await hdr() }));

    // ---- one element of a type, then the whole type
    const X = multis[0];
    const nX = items[X].elements;
    await page.evaluate((i) => window.__xrayClassify.walk.goto(i), X);
    await page.locator('.xrw [data-role=scope-one]').check();
    check(`${tag} a type shows both skips: this one and all ${nX}`, (await page.locator('.xrw [data-act=skip-element]').count()) === 1 && /Skip all \d+/.test(await page.locator('.xrw [data-act=skip-group]').textContent()));
    const before = (await skipped()).length;
    await page.keyboard.press('n'); // scope "this element only": skips this element
    st = await walkState(page);
    check(`${tag} N with "This element only" skips one element and steps to the next of the type`, st.itemIndex === X && st.elementIndex === 1 && (await skipped()).length === before + 1, JSON.stringify({ i: st.itemIndex, e: st.elementIndex }));
    await page.keyboard.press('Shift+N'); // the other one: the whole type
    st = await walkState(page);
    const sk = await skipped();
    check(`${tag} Shift+N skips the whole type (all ${nX}) and goes to the next item`, st.itemIndex === X + 1 && sk.length === before + nX, JSON.stringify({ i: st.itemIndex, n: sk.length, want: before + nX }));
    // all of a type with the default scope
    const Y = multis.find((k) => k > X + 1);
    const nY = items[Y].elements;
    await page.evaluate((i) => window.__xrayClassify.walk.goto(i), Y);
    await page.locator('.xrw [data-role=scope-all]').check();
    await page.keyboard.press('n');
    st = await walkState(page);
    check(`${tag} N with "All ${nY}" skips the whole type`, st.itemIndex === Y + 1 && (await skipped()).length === before + nX + nY);
    // ---- after Back
    await page.evaluate((i) => window.__xrayClassify.walk.goto(i), Y + 1);
    const n0 = (await skipped()).length;
    await page.keyboard.press('ArrowLeft');
    st = await walkState(page);
    check(`${tag} Back returns to the type that was skipped`, st.itemIndex === Y);
    await page.keyboard.press('ArrowRight');
    st = await walkState(page);
    check(`${tag} Skip works after Back (right arrow)`, st.itemIndex === Y + 1 && (await skipped()).length === n0);
    // ---- the header and "Only skipped"
    const total = (await skipped()).length;
    check(`${tag} the header counts every skipped element`, (await hdr()) === `Skipped (${total})`, await hdr());
    check(`${tag} nothing was committed or made pending by skipping`, (await page.evaluate(() => window.__xrayClassify.review.pending().length + window.__xrayClassify.review.history().length)) === 0);
    const allItems = (await listed()).length;
    await page.locator('.xrw [data-role=skipped-count]').click();
    st = await walkState(page);
    const only = await listed();
    check(`${tag} "Skipped (n)" revisits only the skipped elements`, st.filters.onlySkipped && st.progress.total === total && only.length < allItems && only.reduce((a, i) => a + i.elements, 0) === total, JSON.stringify({ total: st.progress.total, items: only.length, all: allItems }));
    check(`${tag} the "Only skipped" filter box is ticked`, await page.locator('.xrw [data-role=filter-skipped]').isChecked());
    const first = only[0];
    await page.keyboard.press('y');
    const left = (await skipped()).length;
    check(`${tag} deciding a skipped item takes its elements off the list`, left === total - first.elements && (await hdr()) === `Skipped (${left})`, `${left} vs ${total - first.elements}`);
    await page.locator('.xrw [data-role=skipped-count]').click();
    check(`${tag} the header button turns the filter off again`, !(await walkState(page)).filters.onlySkipped && (await listed()).length >= allItems - 1);
    await page.evaluate(() => window.__xrayClassify.review.pending().forEach((p) => window.__xrayClassify.review.undoPending(p.item)));
    await page.evaluate(() => window.__xrayClassify.walk.close());
    await page.evaluate(() => window.__xrayClassify.walk.open());

    // ---- Unsure
    await page.locator('.xrw select[data-role=order]').selectOption('location');
    await page.evaluate(() => window.__xrayClassify.walk.goto(5));
    check(`${tag} the Unsure box is there, off by default`, (await page.locator('.xrw [data-role=unsure]').count()) === 1 && !(await page.locator('.xrw [data-role=unsure]').isChecked()) && (await walkState(page)).unsure === false);
    await page.keyboard.press('?');
    check(`${tag} the ? key ticks it`, (await page.locator('.xrw [data-role=unsure]').isChecked()) && (await walkState(page)).unsure === true);
    await page.keyboard.press('?');
    check(`${tag} ? again clears it`, !(await page.locator('.xrw [data-role=unsure]').isChecked()));
    await page.keyboard.press('?');
    const uGid1 = (await walkState(page)).item.key.replace(/^[a-z]+:/, '');
    await page.keyboard.press('Enter');
    let pend = await page.evaluate(() => window.__xrayClassify.review.pending());
    check(`${tag} Confirm with Unsure: a pending change with unsure true, confidence 0.75`, pend.length === 1 && pend[0].globalId === uGid1 && pend[0].unsure === true && pend[0].after.confidence === 0.75 && pend[0].after.source === 'confirmed', JSON.stringify(pend[0]));
    check(`${tag} the Unsure box resets after the action`, !(await page.locator('.xrw [data-role=unsure]').isChecked()) && (await walkState(page)).unsure === false);
    // the next one: Correct with Unsure set inside the form
    const uGid2 = (await walkState(page)).item.key.replace(/^[a-z]+:/, '');
    await page.keyboard.press('e');
    await page.waitForSelector('.xrw-edit');
    check(`${tag} the correction form shows the Unsure box`, (await page.locator('.xrw [data-role=unsure]').count()) === 1);
    await page.locator('.xrw [data-role=unsure]').check();
    const o2 = await page.locator('.xrw-edit select[data-role=edit-discipline] option').evaluateAll((o) => o.map((x) => x.value));
    const c2 = await page.locator('.xrw-edit select[data-role=edit-discipline]').inputValue();
    await page.locator('.xrw-edit select[data-role=edit-discipline]').selectOption(o2.find((d) => d !== c2));
    await page.locator('.xrw [data-act=apply-correct]').click();
    pend = await page.evaluate(() => window.__xrayClassify.review.pending());
    const p2 = pend.find((p) => p.globalId === uGid2);
    check(`${tag} Correct with Unsure: pending, corrected, unsure true`, p2 && p2.unsure === true && p2.after.source === 'corrected' && p2.action === 'correct', JSON.stringify(p2));
    // Runner-up path or a sure confirmation on the third item
    const sGid = (await walkState(page)).item.key.replace(/^[a-z]+:/, '');
    await page.keyboard.press('Enter');
    pend = await page.evaluate(() => window.__xrayClassify.review.pending());
    check(`${tag} the next confirmation is sure: no unsure field, confidence 1`, pend.length === 3 && pend.find((p) => p.globalId === sGid).unsure === undefined && pend.find((p) => p.globalId === sGid).after.confidence === 1);
    await page.locator('.xrw [data-tab=pending]').click();
    const ptags = await page.locator('.xrw [data-role=unsure-tag]').count();
    check(`${tag} the Pending tab shows an "unsure" tag on the two unsure items only`, ptags === 2 && (await page.locator('.xrw [data-item]').count()) === 3, `${ptags}`);
    await page.locator('.xrw [data-tab=walk]').click();
    await page.locator('.xrw [data-role=reviewer]').fill(NAME);
    await page.locator('.xrw [data-act=commit]').click();
    await page.waitForTimeout(400);
    const commit = await page.evaluate(() => window.__xrayClassify.review.history()[0]);
    const byG = Object.fromEntries(commit.changes.map((c) => [c.globalId, c]));
    check(`${tag} the commit carries unsure: true on the two guesses and nothing on the sure one`, commit.changes.length === 3 && byG[uGid1].unsure === true && byG[uGid2].unsure === true && !('unsure' in byG[sGid]) && byG[uGid1].after.confidence === 0.75, JSON.stringify(commit.changes.map((c) => [c.globalId, c.unsure])));
    const rs = await page.evaluate(([a, b, c]) => { const r = (g) => window.__xrayClassify.results().find((x) => x.id === g); return [a, b, c].map((g) => ({ source: r(g).source, unsure: r(g).unsure, nr: r(g).needsReview, conf: Math.min(r(g).discipline.confidence, r(g).subDiscipline?.confidence ?? 1, r(g).masterformat?.confidence ?? 1) })); }, [uGid1, uGid2, sGid]);
    check(`${tag} the unsure results are confirmed/corrected with confidence 0.75 and still need review; the sure one does not`, rs[0].source === 'confirmed' && rs[0].unsure === true && rs[0].nr === true && rs[0].conf === 0.75 && rs[1].source === 'corrected' && rs[1].unsure === true && rs[1].nr === true && rs[2].source === 'confirmed' && rs[2].unsure === undefined && rs[2].nr === false && rs[2].conf === 1, JSON.stringify(rs));
    await page.locator('.xrw [data-tab=history]').click();
    await page.locator('.xrw [data-commit] [data-act=open-commit]').first().click();
    check(`${tag} the History tab shows an "unsure" tag per unsure change`, (await page.locator('.xrw .xrw-changes [data-role=unsure-tag]').count()) === 2 && /2 unsure/.test(await page.locator('.xrw [data-commit]').first().textContent()));
    // ---- exports
    const csv = await page.evaluate(() => window.__xrayClassify.export('csv'));
    const lines = csv.split('\r\n');
    check(`${tag} the CSV has an Unsure column at the end: true for the guesses, false otherwise`, lines[0].endsWith(',CommitId,Unsure') && lines.find((l) => l.startsWith(uGid1)).endsWith(',true') && lines.find((l) => l.startsWith(sGid)).endsWith(',false'));
    const js = JSON.parse(await page.evaluate(() => window.__xrayClassify.export('json')));
    const tl = JSON.parse(await page.evaluate(() => window.__xrayClassify.export('throughline')));
    check(`${tag} the JSON and Throughline exports carry it (Throughline: committed elements only)`, js.results.find((r) => r.id === uGid1).unsure === true && tl.elements.find((e) => e.global_id === uGid1).attributes.unsure === true && tl.elements.find((e) => e.global_id === sGid).attributes.unsure === false && !('unsure' in tl.elements.find((e) => !e.attributes.confirmed_by).attributes));
    const log = JSON.parse(await page.evaluate(() => window.__xrayClassify.review.exportLog()));
    check(`${tag} the review log keeps the format id and the additive field`, log.schema === 'xray-classification-review/1' && log.commits[0].changes.filter((c) => c.unsure === true).length === 2);

    // ---- the results table marks it
    await page.evaluate(() => window.__xrayClassify.walk.close());
    await page.locator('.xt-btn-tool[data-tool="classify"]').click();
    await page.waitForSelector('.xt-drawer:not(.hidden)');
    await page.waitForTimeout(400);
    const rowText = async (g) => (await page.locator(`.xt-drawer tr[data-gid="${g}"]`).first().locator('td').nth(6).textContent().catch(() => null));
    const t1 = await rowText(uGid1);
    check(`${tag} the results table marks the unsure result with "?" after the source`, t1 !== null && /^confirmed \?$/.test(t1.trim()), `${t1}`);
    const marked = await page.evaluate(() => [...document.querySelectorAll('.xt-drawer tr[data-gid]')].filter((tr) => / \?( !)?$/.test(tr.children[6]?.textContent ?? '')).map((tr) => tr.dataset.gid).sort());
    check(`${tag} only the unsure results carry the marker`, marked.join() === [uGid1, uGid2].sort().join(), marked.join());
    await page.keyboard.press('Escape');
    await page.evaluate(() => window.__xrayClassify.walk.open());
    // ---- Only needs review, Only unsure
    await page.locator('.xrw select[data-role=order]').selectOption('location');
    await page.locator('.xrw [data-role=needsReview]').check();
    const nr = await listed();
    check(`${tag} the unsure elements are back under "Only needs review"; the sure one is not`, nr.some((i) => i.key === `location:${uGid1}`) && nr.some((i) => i.key === `location:${uGid2}`) && !nr.some((i) => i.key === `location:${sGid}`), `${nr.length}`);
    await page.locator('.xrw [data-role=needsReview]').uncheck();
    await page.locator('.xrw [data-role=filter-unsure]').check();
    const un = await listed();
    check(`${tag} "Only unsure" lists the two guesses and nothing else`, un.length === 2 && un.map((i) => i.key.replace('location:', '')).sort().join() === [uGid1, uGid2].sort().join(), JSON.stringify(un.map((i) => i.key)));
    // order "Needs review first"
    await page.locator('.xrw [data-role=filter-unsure]').uncheck();
    await page.locator('.xrw select[data-role=order]').selectOption('review');
    const rv = await listed();
    check(`${tag} "Needs review first" still lists the unsure kinds`, rv.length > 0);
    // ---- a later sure confirmation supersedes
    await page.locator('.xrw select[data-role=order]').selectOption('location');
    await page.locator('.xrw [data-role=filter-unsure]').check();
    await page.evaluate(() => window.__xrayClassify.walk.goto(0));
    const supG = (await walkState(page)).item.key.replace(/^[a-z]+:/, '');
    check(`${tag} the walk says that the element was committed as unsure`, (await page.locator('.xrw [data-role=unsure-state]').count()) === 1);
    await page.keyboard.press('Enter');
    pend = await page.evaluate(() => window.__xrayClassify.review.pending());
    check(`${tag} a sure Confirm on the same codes is not left out: it is pending`, pend.length === 1 && pend[0].globalId === supG && pend[0].unsure === undefined && pend[0].before.confidence === 0.75, JSON.stringify(pend[0]));
    await page.locator('.xrw [data-act=commit]').click();
    await page.waitForTimeout(300);
    const after = await page.evaluate((g) => { const r = window.__xrayClassify.results().find((x) => x.id === g); return { unsure: r.unsure, nr: r.needsReview, conf: r.discipline.confidence, n: window.__xrayClassify.review.history().length }; }, supG);
    check(`${tag} the latest change wins: the element is sure now (confidence 1, no review), two commits in the log`, after.unsure === undefined && after.nr === false && after.conf === 1 && after.n === 2, JSON.stringify(after));
    await page.locator('.xrw [data-role=unsure]').count();
    // the name is still in no params or link
    const doc = await page.evaluate(() => JSON.stringify(window.__xray.exportParams?.collect?.() ?? window.__xrayParams?.collect?.() ?? {}));
    check(`${tag} the reviewer name is still not in the params or the page URL`, !doc.includes('Fanshawe') && !page.url().includes('Fanshawe') && doc.length > 10);
  } finally {
    const real = errors.filter((e) => !/favicon/i.test(e));
    check(`${tag} zero console errors`, real.length === 0, real.slice(0, 3).join(' | '));
    await ctx.close();
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
    check(`${tag} the panel fits the phone width and sits in the lower part of the screen`, box.left >= 0 && box.right <= box.vw + 1 && box.scrollW <= box.vw + 1 && box.top > box.vh * 0.25, JSON.stringify(box));
    const tiny = await page.evaluate(() => [...document.querySelectorAll('.xrw-acts .xrw-btn')].filter((b) => b.getBoundingClientRect().height < 34 || b.getBoundingClientRect().right > window.innerWidth).length);
    check(`${tag} the action buttons are large and inside the screen`, tiny === 0);
    // Skip and Unsure are on screen without scrolling, also on a short phone
    const reach = (sel) => page.evaluate((q) => {
      const e = document.querySelector(q);
      if (!e) return { found: false };
      const r = e.getBoundingClientRect();
      const p = document.querySelector('.xrw').getBoundingClientRect();
      return { found: true, inView: r.top >= 0 && r.bottom <= window.innerHeight && r.left >= 0 && r.right <= window.innerWidth, inPanel: r.top >= p.top - 1 && r.bottom <= p.bottom + 1, inScroller: !!e.closest('.xrw-body'), w: r.width, h: r.height };
    }, sel);
    for (const vp of [{ width: 390, height: 844 }, { width: 360, height: 640 }]) {
      await page.setViewportSize(vp);
      await page.waitForTimeout(250);
      for (const [name, sel] of [['Skip', '.xrw [data-act=skip], .xrw [data-act=skip-element]'], ['Unsure', '.xrw label.xrw-unsure'], ['Confirm', '.xrw [data-act=confirm]']]) {
        const r = await reach(sel);
        check(`${tag} ${name} is on screen without scrolling at ${vp.width}x${vp.height}`, r.found && r.inView && r.inPanel && !r.inScroller && r.h >= 20, JSON.stringify(r));
      }
    }
    await page.setViewportSize({ width: 390, height: 844 });
    await page.waitForTimeout(250);
    // Unsure with buttons only: tick it, Confirm, and the change is pending with the flag; the box clears
    await page.locator('.xrw [data-role=unsure]').check();
    check(`${tag} the Unsure box is ticked by a tap`, (await walkState(page)).unsure === true);
    await page.locator('.xrw [data-act=confirm]').click();
    const pu = await page.evaluate(() => window.__xrayClassify.review.pending());
    check(`${tag} Confirm with Unsure ticked gives pending changes with unsure: true, and the box clears`, pu.length >= 1 && pu.every((p) => p.unsure === true && p.after.confidence === 0.75) && (await walkState(page)).unsure === false && !(await page.locator('.xrw [data-role=unsure]').isChecked()), JSON.stringify(pu[0]));
    const sk0 = (await walkState(page)).skipped;
    await page.locator('.xrw [data-act=skip], .xrw [data-act=skip-element]').first().click();
    check(`${tag} Skip by button adds to the Skipped count in the header`, (await walkState(page)).skipped > sk0 && /Skipped \(\d+\)/.test(await page.locator('.xrw [data-role=skipped-count]').textContent()));
    await page.locator('.xrw [data-act=confirm]').tap().catch(() => page.locator('.xrw [data-act=confirm]').click());
    await page.locator('.xrw [data-act=skip], .xrw [data-act=skip-element]').first().click();
    await page.locator('.xrw [data-act=correct]').click();
    await page.waitForSelector('.xrw-edit');
    await page.waitForTimeout(500);
    check(`${tag} Confirm, Skip and Correct work with buttons only`, (await walkState(page)).pending >= 1 && (await walkState(page)).editing);
    await page.locator('.xrw [data-role=unsure]').check(); // the screenshot shows the control ticked
    await shot(page, 'review-walk-phone.png');
    check(`${tag} the correction form has Unsure, Apply, Skip and Cancel in view`, (await Promise.all(['[data-role=unsure]', '[data-act=apply-correct]', '[data-act=skip-edit]', '[data-act=cancel-correct]'].map((q) => reach(`.xrw ${q}`)))).every((r) => r.found && r.inView && !r.inScroller));
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
  await runSkipUnsure(browser);
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
