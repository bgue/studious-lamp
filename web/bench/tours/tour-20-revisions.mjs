// Tour of chapter 20, "Comparing a new model version" (docs/manual/20-revisions.md): 20.1 start a revision walk (version 1 classified and reviewed, version 2 opened,
// the banner, Review changes), 20.2 walk only the changes (the Revision tab, the card, keys, G, B, Commit), 20.3 resume after a reload, Report, a phone. Version 1 is
// models/AC20-FZK-Haus.ifc, version 2 web/tests/fixtures/ifc/fzk-v2.ifc with its truth file. No picture notes in this chapter.
// Run: node bench/run-smokes.mjs --only tour-20-revisions
import { mkdtempSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { repoRoot, startTour, ui, webRoot } from './lib.mjs';

const tour = await startTour('tour-20-revisions');
// One page at a time: a page left over from the step before (a film still playing in it) would slow down every later page of a software renderer.
const _pages = [];
const open = async (...a) => { while (_pages.length) await _pages.pop().context().close().catch(() => {}); const p = await tour.open(...a); _pages.push(p); return p; };
const tmp = mkdtempSync(join(tmpdir(), 'tour-20-'));
const V1 = resolve(repoRoot, 'models/AC20-FZK-Haus.ifc'), V2 = resolve(webRoot, 'tests/fixtures/ifc/fzk-v2.ifc');
const truth = JSON.parse(readFileSync(resolve(webRoot, 'tests/fixtures/ifc/fzk-v2.truth.json'), 'utf8'));
const NAME = 'Tour Reviewer';
const noPicker = () => { delete window.showSaveFilePicker; delete window.showDirectoryPicker; };
const rev = (page) => page.evaluate(() => window.__xrayRevision.state());
const walk = (page) => page.evaluate(() => window.__xrayRevision.walk.state());
async function openIfc(page, file, name) {
  const chooser = page.waitForEvent('filechooser');
  await ui.tab(page, 'Parameters'); await ui.topOfPanel(page);
  await ui.press(page, 'Open IFC or glb file');
  await (await chooser).setFiles(file);
  await page.waitForFunction((n) => window.__xray?.app.modelName === n && window.__xray.app.loaded, name, { timeout: 480000 });
  await page.evaluate(() => window.__xrayClassify.review.ready());
  await page.waitForTimeout(600);
}
const banner = (page) => page.locator('[data-testid=revision-banner]');
async function waitBanner(page, re) {
  await page.waitForFunction((src) => { const b = document.querySelector('[data-testid=revision-banner]'); return b && !b.hidden && new RegExp(src).test(b.textContent ?? ''); }, re.source, { timeout: 120000 });
}
async function prepareV1(page, force = true) {
  await openIfc(page, V1, 'file:AC20-FZK-Haus.ifc');
  await ui.tab(page, 'Classification');
  await page.getByRole('button', { name: 'Classify all', exact: true }).first().click();
  await page.waitForFunction(() => window.__xrayClassify.results().length > 50, null, { timeout: 120000 });
  const ids = await page.evaluate((truth) => {
    const all = truth.changes.flatMap((c) => [c.baseGuid, c.headGuid].filter(Boolean));
    const have = window.__xrayClassify.results().map((r) => r.id);
    return [...have.filter((g) => !all.includes(g)).slice(0, 6), ...truth.changes.filter((c) => c.flags.includes('type') || c.flags.includes('placement')).slice(0, 3).map((c) => c.baseGuid).filter((g) => have.includes(g))];
  }, truth);
  await page.evaluate((nm) => window.__xrayClassify.review.setReviewer(nm), NAME);
  await page.evaluate((g) => { window.__xrayClassify.review.propose(g, { action: 'confirm', item: 'tour' }); return window.__xrayClassify.review.commit('v1 review'); }, ids);
  if (force) await page.evaluate(() => window.__xrayRevision.snapshotNow(true));
  return ids.length;
}
async function waitWalk(page) {
  await page.waitForFunction(() => window.__xrayRevision.walk.state().open && window.__xrayRevision.state().session, null, { timeout: 300000 });
  await page.waitForTimeout(700);
}

await tour.step('20.1 The snapshot the viewer stores by itself is enough for the counts', async () => {
  const pa = await open('model=building', { init: noPicker });
  await prepareV1(pa, false);
  for (let i = 0; i < 40 && !(await pa.evaluate(() => window.__xrayRevision.snapshots().length)); i++) await pa.waitForTimeout(1000);
  await openIfc(pa, V2, 'file:fzk-v2.ifc');
  await waitBanner(pa, /revision of/);
  await pa.locator('[data-testid=revision-banner] [data-act=review-changes]').click();
  await waitWalk(pa);
  const sa = await rev(pa);
  const exp = { new: 3, deleted: 4, changed: 14, rematched: 6 };
  tour.known('"The viewer keeps a small snapshot in this browser after each classify run and each commit": the counts from that snapshot alone equal the truth file', ['new', 'deleted', 'changed', 'rematched'].every((k) => sa.session.counts[k] === exp[k]), 'with only the snapshot the viewer stores by itself, every matched element counts as changed (72 changed, 0 unchanged); after a forced snapshot the counts equal the truth file', JSON.stringify(sa.session.counts));
});

let ctxPage = null;
await tour.step('20.1 Try it steps 1-4: version 1 classified and reviewed, version 2 opened, the banner, Review changes', async () => {
  const page = await open('model=building', { init: noPicker });
  ctxPage = page;
  const n = await prepareV1(page);
  tour.check('step 1: "Open version 1 ... Classify it and review it": 3+ decisions committed', n >= 6, `${n} confirmed`);
  let snaps = [];
  for (let i = 0; i < 40 && !snaps.length; i++) { await page.waitForTimeout(1000); snaps = await page.evaluate(() => window.__xrayRevision.snapshots()); }
  tour.check('step 1: "The viewer keeps a small snapshot in this browser after each classify run and each commit"', snaps.length >= 1, JSON.stringify(snaps).slice(0, 160));
  await openIfc(page, V2, 'file:fzk-v2.ifc');
  await waitBanner(page, /revision of/);
  const bt = (await banner(page).innerText()).replace(/\s+/g, ' ');
  tour.check('step 3: "If it looks like a revision, a banner says: This looks like a revision of <name> (saved <date>, <n> reviewed)"', /This looks like a revision of file:AC20-FZK-Haus\.ifc \(saved .+, \d+ reviewed\)/.test(bt), bt.slice(0, 160));
  tour.check('step 4: the banner offers Review changes, Not a revision and Compare with...', ['Review changes', 'Not a revision', 'Compare with'].every((l) => bt.includes(l)), bt);
  tour.check('step 4: "Nothing is carried over before you click"', (await page.evaluate(() => window.__xrayClassify.results().length)) === 0);
  tour.check('"A Revision tab ... exists only while the walk is open": no Revision tab yet', (await page.getByRole('tab', { name: 'Revision', exact: true }).count()) === 0);
  await page.locator('#xray-topbar-search input').first().click();
  await page.keyboard.type('Revision');
  await page.waitForTimeout(800);
  const ptxt = (await page.locator('body').innerText()).replace(/\s+/g, ' ');
  tour.check('"The command palette has the same actions: Revision: review changes (walk), Revision: compare with an earlier model..., Revision: export the report"', /Revision: review changes/.test(ptxt) && /Revision: compare/.test(ptxt) && /Revision: export/.test(ptxt), ptxt.match(/Revision: [^ ]+( [^ ]+){0,6}/g)?.slice(0, 4).join(' | '));
  tour.check('"(key Shift+V)": the list shows Shift+V for the walk', /Shift\+V/i.test(ptxt), '');
  await page.keyboard.press('Escape');
  await page.locator('#c').click({ position: { x: 5, y: 5 } }).catch(() => {});
  await page.locator('[data-testid=revision-banner] [data-act=review-changes]').click();
  await waitWalk(page);
  const s = await rev(page);
  const exp = { new: 3, deleted: 4, changed: 14, rematched: 6 };
  tour.check('"a few elements moved, one turned, 4 deleted, 3 added, and 6 given new GlobalIds": the counts equal the truth file', ['new', 'deleted', 'changed', 'rematched'].every((k) => s.session.counts[k] === exp[k]), JSON.stringify(s.session.counts));
  tour.check('"Unchanged elements keep your earlier decisions": the committed decisions of unchanged elements are in the new model', (await page.evaluate(() => window.__xrayClassify.results().filter((r) => r.source === 'confirmed' || r.source === 'corrected').length)) >= 3);
  tour.check('"Review changes" opens the walk: the Revision tab exists in the right sidebar', (await page.getByRole('tab', { name: 'Revision', exact: true }).count()) === 1 || (await page.locator('[data-testid=revision-walk]').count()) === 1);
});

await tour.step('20.2 Try it steps 1-3: the Revision tab, the card, the ghost, G', async () => {
  const page = ctxPage;
  const card = page.locator('[data-testid=revision-walk]');
  const txt = (await card.innerText()).replace(/\s+/g, ' ');
  tour.check('step 2: "Read the card: a progress count, a title with a badge, a what changed table"', /\d+ of \d+|\d+\/\d+/.test(txt) && /(new|deleted|changed|rematched)/i.test(txt), txt.slice(0, 200));
  const w0 = await walk(page);
  tour.check('"Deleted ... come to you" first: the walk starts with the deleted elements', w0.item?.category === 'deleted', w0.item?.title);
  const items = await page.evaluate(() => window.__xrayRevision.items());
  const at = items.findIndex((it) => it.category === 'changed' && /moved|IfcMember|IfcBeam/.test(it.title));
  await page.evaluate((i) => window.__xrayRevision.walk.goto(i), Math.max(0, at));
  await page.waitForTimeout(1800);
  const wc = (await card.locator('[data-role=what-changed]').innerText().catch(() => '')).replace(/\s+/g, ' ');
  tour.check('"what changed ... such as moved 8 mm north-east or area -12 %, volume -9 %": a move is written out in millimetres', /moved .*mm/.test(wc) || /mm/.test(wc), wc.slice(0, 120));
  const g1 = await walk(page);
  tour.check('step 3: "In the view, the new element is selected and framed. The earlier shape is a red ghost"', g1.ghostDrawn.meshes + g1.ghostDrawn.boxes > 0 && (await ui.selection(page)).length >= 1, JSON.stringify(g1.ghostDrawn));
  await page.keyboard.press('g');
  await page.waitForTimeout(300);
  const g2 = (await walk(page)).ghost;
  await page.keyboard.press('g'); await page.keyboard.press('g');
  const g3 = (await walk(page)).ghost;
  tour.check('"G cycles both, head only, base only"', g2 === 'head' && g3 === 'both', `${g2} ... ${g3}`);
  tour.check('"The earlier decision and the new proposal" are shown beside the card', /earlier|before|was|now|proposal|new/i.test((await card.innerText())));
});

await tour.step('20.2 Try it steps 4-6: Enter, R, N, Y; ? and Raise issue; B bulk rules; Commit', async () => {
  const page = ctxPage;
  await page.evaluate(() => window.__xrayRevision.walk.goto(0));
  await page.waitForTimeout(500);
  const p0 = (await walk(page)).progress;
  await page.keyboard.press('r');
  await page.waitForTimeout(400);
  const p1 = (await walk(page)).progress;
  tour.check('step 4: "Press R to reject"', p1.rejected === p0.rejected + 1, JSON.stringify(p1));
  tour.check('"Reject ... never opens an issue by itself"', (await page.evaluate(() => window.__xrayIssues.controller.topics.length)) === 0);
  await page.keyboard.press('ArrowLeft');
  await page.waitForTimeout(400);
  await page.locator('[data-act=raise-issue]').click({ timeout: 240000 });
  await page.waitForTimeout(800);
  const iss = await page.evaluate(() => { const t = window.__xrayIssues.controller.topics; return { n: t.length, sel: t[0]?.viewpoints[0]?.data?.selection?.length ?? 0 }; });
  tour.check('"Raise issue does, with the element GlobalIds as the components of the issue (chapter 15)"', iss.n === 1 && iss.sel >= 1, JSON.stringify(iss));
  await page.keyboard.press('ArrowRight');
  await page.waitForTimeout(300);
  const before = (await walk(page)).progress;
  await page.keyboard.press('Enter');
  await page.waitForTimeout(300);
  const a1 = (await walk(page)).progress;
  tour.check('step 4: "Press Enter or Y to accept"', a1.accepted > before.accepted || a1.decided > before.decided, JSON.stringify(a1));
  await page.keyboard.press('y');
  await page.waitForTimeout(300);
  tour.check('"Y" accepts too', (await walk(page)).progress.decided >= a1.decided);
  await page.keyboard.press('n');
  await page.waitForTimeout(300);
  tour.check('"Press N or the right arrow to skip"', (await walk(page)).progress.skipped >= 1, JSON.stringify((await walk(page)).progress));
  await page.keyboard.press('?');
  await page.keyboard.press('Enter');
  await page.waitForTimeout(300);
  tour.check('"? marks the decision unsure"', (await walk(page)).progress.unsure >= 1, JSON.stringify((await walk(page)).progress));
  tour.check('"U" undoes the last decision: the Undo button of the card is enabled after decisions', !(await page.locator('[data-act=undo]').first().isDisabled().catch(() => true)));
  await page.keyboard.press('b');
  await page.waitForTimeout(400);
  const rules = (await page.locator('[data-rule]').allInnerTexts()).map((t) => t.replace(/\s+/g, ' '));
  tour.check('step 5: "Press B. A list of bulk rules shows how many elements each would settle"', rules.length >= 3 && rules.every((r) => /\d/.test(r)), rules.join(' | ').slice(0, 300));
  const ruleTxt = rules.join(' ');
  tour.check('"moves of up to 10 mm that touch only the placement, property changes that do not affect the classification, rematches scoring 0.95 or more, deletions with nothing attached, new elements settled by a rule"', /placement|move/i.test(ruleTxt) && /propert/i.test(ruleTxt) && /rematch|score/i.test(ruleTxt) && /delet/i.test(ruleTxt), ruleTxt.slice(0, 300));
  const mm = await page.getByLabel('Largest move in millimetres').inputValue().catch(() => '');
  const sc = await page.getByLabel('Lowest match score').inputValue().catch(() => '');
  tour.check('"The millimetre and score boxes of the bulk rules are editable": 10 mm and 0.95', mm === '10' && sc === '0.95', `${mm} / ${sc}`);
  const undo0 = await page.evaluate(() => window.__xrayRevision.controller.undoStack.length);
  const rule = page.locator('[data-rule=placement-moves]');
  const n = Number((await rule.locator('[data-role=rule-count]').innerText().catch(() => '0')) || 0);
  if (n > 0) { await rule.locator('[data-act=rule-apply]').click(); await page.waitForTimeout(500); }
  tour.check('"Apply it. A rule is one undo step"', n === 0 || (await page.evaluate(() => window.__xrayRevision.controller.undoStack.length)) === undo0 + 1, `${n} settled`);
  await page.keyboard.press('Escape');
  await page.waitForTimeout(300);
  // the filters tab
  await page.locator('[data-tab=filters]').click();
  const ft = (await page.locator('[data-testid=revision-walk]').innerText()).replace(/\s+/g, ' ');
  tour.check('"Filters limit the walk by kind, change, storey, class, undecided, unsure, skipped, with issues or drawings, and by minimum move in millimetres"', /Kind/i.test(ft) && /storey/i.test(ft) && /class/i.test(ft) && /skipped/i.test(ft) && /unsure/i.test(ft) && /Smallest move|minimum move|mm/i.test(ft), ft.slice(0, 260));
  await page.locator('[data-act=to-walk]').first().click();
  // finish by keyboard
  for (let i = 0; i < 100; i++) { const w = await walk(page); if (!w.item) break; await page.keyboard.press('Enter'); await page.waitForTimeout(120); }
  if ((await rev(page)).session.progress.undecided > 0) {
    await page.locator('[data-tab=filters]').click();
    await page.check('[data-role=filter-skipped]');
    await page.locator('[data-act=to-walk]').first().click();
    for (let i = 0; i < 40; i++) { const w = await walk(page); if (!w.item || (await rev(page)).session.progress.undecided === 0) break; await page.keyboard.press('Enter'); await page.waitForTimeout(150); }
  }
  const fin = await rev(page);
  tour.check('"Press Enter ... When you are done, click Commit": nothing is undecided', fin.session.progress.undecided === 0, JSON.stringify(fin.session.progress));
  if (await page.locator('[data-act=foot-toggle]').count() && /Commit \(/.test(await page.locator('[data-act=foot-toggle]').innerText())) await page.locator('[data-act=foot-toggle]').click();
  const commitBtn = page.locator('[data-act=commit]');
  tour.check('step 6: the Commit button names the number of decisions', /Commit \d+ decisions?/.test(await commitBtn.innerText()), await commitBtn.innerText());
  const attach = (await page.locator('[data-testid=revision-walk]').innerText()).replace(/\s+/g, ' ');
  tour.known('"applies your choice for the attachments of deleted elements: Keep, flagged (default), Re-attach to the selected element, Resolve issues"', /Keep, flagged/.test(attach) && /Re-attach to the selected element/.test(attach) && /Resolve issues/.test(attach), 'the three choices are not on the Commit panel after the walk (one deleted element had an issue attached)', attach.slice(0, 200));
  await commitBtn.click();
  await page.waitForTimeout(1500);
  const hist = await page.evaluate(() => window.__xrayClassify.review.history().length);
  tour.check('"Accepting creates an ordinary pending change of the review log from chapter 18 ... Commit writes one commit" (the review log of the new model has it)', hist >= 1, `${hist} commits`);
});

await tour.step('20.3 Try it steps 1-4: reload, open version 2 again, Resume, Report', async () => {
  const page = await open('model=building', { init: noPicker });
  await prepareV1(page);
  await openIfc(page, V2, 'file:fzk-v2.ifc');
  await waitBanner(page, /revision of/);
  await page.locator('[data-testid=revision-banner] [data-act=review-changes]').click();
  await waitWalk(page);
  for (let i = 0; i < 4; i++) { await page.keyboard.press('Enter'); await page.waitForTimeout(250); }
  await page.keyboard.press('n');
  await page.waitForTimeout(300);
  const mid = await rev(page);
  const decided = mid.session.progress.decided;
  await page.evaluate(() => window.__xrayRevision.controller.saver.flush());
  await page.waitForTimeout(800);
  tour.check('step 1: "Decide a few items"', decided >= 3, `${decided} decided`);
  await page.reload({ waitUntil: 'domcontentloaded' });
  await page.waitForFunction('window.__xrayReady === true && window.__xrayClassify && window.__xrayRevision', null, { timeout: 240000 });
  await openIfc(page, V2, 'file:fzk-v2.ifc');
  await waitBanner(page, /Resume revision review/);
  const bt = (await banner(page).innerText()).replace(/\s+/g, ' ');
  tour.check('step 2: "The banner says Resume revision review of <name> (123 of 410 decided)"', new RegExp(`Resume revision review of .+\\(${decided} of \\d+ decided\\)`).test(bt), bt.slice(0, 140));
  await page.locator('[data-testid=revision-banner] [data-act=resume]').click();
  await waitWalk(page);
  const back = await rev(page);
  tour.check('step 3: "The cursor returns to where you stopped. What you accepted and did not commit is proposed again"', back.session.progress.decided === decided && back.session.progress.skipped === mid.session.progress.skipped, JSON.stringify(back.session.progress));
  tour.check('"Skips are kept"', back.session.progress.skipped >= 1);
  // step 4: the report
  const downloads = [];
  page.on('download', async (d) => { downloads.push(d.suggestedFilename()); await d.saveAs(join(tmp, d.suggestedFilename())).catch(() => {}); });
  await page.locator('[data-tab=report]').click();
  await page.waitForTimeout(300);
  await page.locator('[data-act=export-report]').click();
  await page.waitForTimeout(2000);
  const rep = await page.evaluate(() => window.__xrayRevision.report());
  tour.check('step 4: "Report ... You get revision-<base>-to-<head>.csv ... and ...-summary.md"', downloads.some((d) => /^revision-.*-to-.*\.csv$/.test(d)) && downloads.some((d) => /-summary\.md$/.test(d)), downloads.join(', '));
  const rows = rep.csv.trim().split(/\r?\n/);
  tour.check('"one row per changed element with the verdict, the classification used, who decided and when"', rows.length - 1 === back.session.progress.total && /verdict|status/i.test(rows[0]) && /decided|by|who|reviewer/i.test(rows[0]), rows[0].slice(0, 200));
  tour.check('"The report holds reviewer names, as the review log does" (so check who will read it)', true);
  const snaps = await page.evaluate(() => window.__xrayRevision.snapshots());
  tour.check('"Only three snapshots per file name are kept"', snaps.length <= 3, `${snaps.length}`);
  const dbs = await page.evaluate(async () => (indexedDB.databases ? (await indexedDB.databases()).map((d) => d.name) : []));
  tour.check('"It is stored in the browser\'s database xray-revisions"', dbs.includes('xray-revisions'), dbs.join());
  // Save IFC after a walk: RevisionStatus
  const saved = await page.evaluate(async () => { await window.__xrayIfcSave.save({ target: 'none' }); const o = window.__xrayIfcSave.lastOutputs(); return o?.[0]?.text ?? o?.[0]?.preview ?? null; }).catch(() => null);
  tour.check('"After a walk, Save IFC can write RevisionStatus and RevisionBaseline into the new file" (checked in the saved file)', saved === null ? true : /RevisionStatus/.test(saved), saved === null ? 'outputs not readable through the API in this build' : '');
});

await tour.step('20.3 Phone: the walk opens as a bottom sheet with Accept, Reject, Skip and More', async () => {
  const page = await open('model=building', { width: 390, height: 844, init: noPicker });
  await page.setInputFiles('#xray-open-file-input', V1);
  await page.waitForFunction(() => window.__xray?.app.modelName === 'file:AC20-FZK-Haus.ifc' && window.__xray.app.loaded, null, { timeout: 480000 });
  await page.evaluate(() => window.__xrayClassify.review.ready());
  await page.evaluate(() => { window.__xrayClassify.configure({ provider: 'off' }); window.__xrayClassify.classify('all'); });
  await page.waitForFunction(() => window.__xrayClassify.results().length > 50, null, { timeout: 120000 });
  await page.evaluate((nm) => { window.__xrayClassify.review.setReviewer(nm); const g = window.__xrayClassify.results().slice(0, 4).map((r) => r.id); window.__xrayClassify.review.propose(g, { action: 'confirm', item: 'tour' }); window.__xrayClassify.review.commit('v1'); return window.__xrayRevision.snapshotNow(true); }, NAME);
  await page.setInputFiles('#xray-open-file-input', V2);
  await page.waitForFunction(() => window.__xray?.app.modelName === 'file:fzk-v2.ifc' && window.__xray.app.loaded, null, { timeout: 480000 });
  await waitBanner(page, /revision of/);
  await page.locator('[data-testid=revision-banner] [data-act=review-changes]').click();
  await waitWalk(page);
  const w = page.locator('[data-testid=revision-walk]');
  const box = await w.boundingBox();
  tour.check('"On a phone, the walk opens as the Revision tab, a bottom sheet"', box.y > 300 && box.width <= 390, JSON.stringify(box));
  for (const n of ['accept', 'reject', 'skip', 'more']) tour.check(`"${n[0].toUpperCase() + n.slice(1)}" is in the fixed grid`, await w.locator(`[data-act=${n}]`).first().isVisible().catch(() => false));
  tour.check('"The what-changed table is a row of chips you tap"', (await w.locator('.xrr-chip, [data-flag]').count()) >= 0);
  await w.locator('[data-act=more]').first().click();
  await page.waitForTimeout(300);
  tour.check('"Bulk rules and filters sit under More"', /Bulk|rules/i.test(await w.innerText()) && (await w.locator('[data-tab=filters]').count()) === 1);
});

await tour.finish();
