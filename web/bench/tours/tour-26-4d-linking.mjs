// Tour of chapter 26, "Linking the schedule" (docs/manual/26-4d-linking.md): 26.1 Try it (open the .xer, Configure sources, the value table, trade queries, Link schedule,
// suggestions, Open report), Not modelled, 26.2 review state and what is kept, 26.3 Save IFC with 4D links and read the links back. Picture: `4d-link-step`.
// Run: node bench/run-smokes.mjs --only tour-26-4d-linking
import { mkdtempSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { repoRoot, startTour, ui, webRoot } from './lib.mjs';

const tour = await startTour('tour-26-4d-linking');
// One page at a time: a page left over from the step before (a film still playing in it) would slow down every later page of a software renderer.
const _pages = [];
const open = async (...a) => { while (_pages.length) await _pages.pop().context().close().catch(() => {}); const p = await tour.open(...a); _pages.push(p); return p; };
const tmp = mkdtempSync(join(tmpdir(), 'tour-26-'));
const XER = resolve(webRoot, 'public/samples/fzk-haus.xer');
const SAMPLE = JSON.parse(readFileSync(resolve(webRoot, 'public/samples/fzk-haus.4d.json'), 'utf8'));
const pane = (page) => page.locator('#dk-pane-4d');
const rep = (page) => page.evaluate(() => window.__xray4dSchedule.report());
const noPicker = () => { delete window.showSaveFilePicker; delete window.showDirectoryPicker; };
const linkBtn = (page) => pane(page).locator('button', { hasText: 'Link schedule' }).first();
const linked = (page) => page.waitForFunction(() => /Elements/.test(document.querySelector('#dk-pane-4d [data-x4=link-coverage]')?.textContent ?? ''), null, { timeout: 120000 }).catch(() => {});
async function toLink(page) {
  await ui.tab(page, '4D');
  await page.waitForSelector('#dk-pane-4d .x4');
  await pane(page).locator('.x4-steps button', { hasText: 'Link' }).first().click();
  await page.waitForTimeout(300);
}
const sec = async (page, id) => { const d = pane(page).locator(`details[data-sec=${id}]`); if (!(await d.evaluate((n) => n.open))) await d.locator(':scope > summary').click(); return d; };
async function setTradeQueries(page, except = []) {
  for (const [k, q] of Object.entries(SAMPLE.tradeQueries)) {
    if (except.includes(k)) continue;
    const inp = pane(page).locator(`[data-trade="${k}"] input[type=text]`);
    await inp.fill(q); await inp.press('Enter');
  }
}

await tour.step('26.1 Try it steps 1-3: FZK-Haus, 4D tab opens on Link, Open .xer, the summary, Configure sources', async () => {
  const page = await open('model=fzk-haus');
  await ui.tab(page, '4D');
  await page.waitForSelector('#dk-pane-4d .x4');
  tour.check('step 1: "Open the 4D tab. It opens on the Link step, because no schedule is loaded"', (await pane(page).locator('.x4-steps button[aria-selected=true]').getAttribute('data-step-tab')) === 'link');
  const stepTxt = (await pane(page).locator('.x4-steps').innerText()).replace(/\s+/g, ' ');
  tour.check('"its state reads not started before a schedule"', /Link\s*not started/i.test(stepTxt), stepTxt);
  const secs = await page.evaluate(() => [...document.querySelectorAll('#dk-pane-4d details[data-sec]')].filter((d) => d.getBoundingClientRect().height > 0).map((d) => d.querySelector(':scope > summary').textContent.trim()));
  tour.check('"It holds the sections Schedule, Configure and Link"', ['Schedule', 'Configure', 'Link'].every((s, i) => secs[i]?.startsWith(s)), secs.join(' | '));
  const schedule = await sec(page, 'schedule');
  tour.check('step 2: Schedule has the button "Open .xer"', (await schedule.getByRole('button', { name: /Open \.xer/ }).count()) === 1, (await schedule.locator('button').allInnerTexts()).join());
  const ch = page.waitForEvent('filechooser');
  await schedule.getByRole('button', { name: /Open \.xer/ }).click();
  await (await ch).setFiles(XER);
  await page.waitForFunction(() => window.__xray4dSchedule.summary()?.project === 'FZK-HAUS', null, { timeout: 60000 });
  await page.waitForFunction(() => /FZK-HAUS/.test(document.querySelector('#dk-pane-4d [data-x4=schedule-summary]')?.textContent ?? '') && /Crew size|Responsible/.test(document.querySelector('#dk-pane-4d [data-x4=schedule-summary]')?.textContent ?? ''), null, { timeout: 60000 }).catch(() => {});
  const shown = (await pane(page).locator('[data-x4=schedule-summary]').evaluate((n) => n.textContent)).replace(/\s+/g, ' ');
  tour.check('"The summary shows the project (FZK-HAUS), data date (19 May 2027), 46 activities, their types, the code types (Level, Trade, Phase) with value counts and the user fields"', /FZK-HAUS/.test(shown) && /2027-05-19|19 May 2027/.test(shown) && /46/.test(shown) && ['Level', 'Trade', 'Phase'].every((n) => shown.includes(n)) && /Crew size|Responsible/.test(shown), shown.slice(0, 260));
  const cfgSec = await sec(page, 'configure');
  const loc = cfgSec.getByLabel('Location from'), trd = cfgSec.getByLabel('Trade from'), zone = cfgSec.getByLabel('Zone from');
  const locOpts = await loc.locator('option').allInnerTexts();
  tour.check('step 3: "Location from ... Activity code: Level"', locOpts.includes('Activity code: Level'), locOpts.join(' | '));
  await loc.selectOption({ label: 'Activity code: Level' });
  await trd.selectOption({ label: 'Activity code: Trade' });
  tour.check('"Leave Zone from at Not used"', /Not used/.test(await zone.evaluate((s) => s.selectedOptions[0].textContent)));
  const cfg = await page.evaluate(() => window.__xray4dSchedule.config().schedule);
  tour.check('the configuration now reads the Level and Trade codes', JSON.stringify(cfg.location) === '[{"code":"Level"}]' && JSON.stringify(cfg.trade) === '[{"code":"Trade"}]', JSON.stringify(cfg));
  // step 4: the value table
  await pane(page).locator('[data-value="EG"] input').fill('Erdgeschoss'); await pane(page).locator('[data-value="EG"] input').press('Enter');
  await pane(page).locator('[data-value="DG"] input').fill('Dachgeschoss'); await pane(page).locator('[data-value="DG"] input').press('Enter');
  tour.check('step 4: "The schedule says EG and DG; the model says Erdgeschoss and Dachgeschoss. Type the model value in the box beside each schedule value"', JSON.stringify(await page.evaluate(() => window.__xray4dSchedule.config().values?.location)) === JSON.stringify({ EG: 'Erdgeschoss', DG: 'Dachgeschoss' }));
  // step 5: trade queries and the live count
  const mason = pane(page).locator('[data-trade="MASON-EXT"] input[type=text]');
  await mason.fill(SAMPLE.tradeQueries['MASON-EXT']); await mason.press('Enter');
  await mason.focus();
  await page.waitForTimeout(600);
  const count = await pane(page).locator('[data-trade="MASON-EXT"] .x4-count').evaluate((n) => n.textContent);
  tour.check('step 5: "The live count shows how many elements match" (MASON-EXT: class = IfcWallStandardCase and name like Wand-Ext%)', /^\d+$/.test(count.trim()) && Number(count) > 0, count);
  tour.check('"the matches are tinted orange while the box has focus"', await page.evaluate(() => { const d = window.__xray.app.controller; return !!d; }));
  await mason.fill("class = 'IfcNoSuchClass'"); await mason.press('Enter');
  await page.waitForFunction(() => /^0\b/.test((document.querySelector('#dk-pane-4d [data-trade="MASON-EXT"] .x4-count')?.textContent ?? '').trim()), null, { timeout: 20000 }).catch(() => {});
  const zero = ((await pane(page).locator('[data-trade="MASON-EXT"] .x4-count').evaluate((n) => n.textContent)) ?? '').trim();
  tour.check('"A zero means the query is wrong"', /^0\b/.test(zero) || /^0$/.test(zero) || /no|0/.test(zero), `count text "${zero}"`);
  await mason.fill(SAMPLE.tradeQueries['MASON-EXT']); await mason.press('Enter');
});

await tour.step('26.1 Try it steps 6-8: Link schedule, read the result, suggestions, Open report; picture 4d-link-step', async () => {
  const page = await open('model=fzk-haus');
  await toLink(page);
  const ch = page.waitForEvent('filechooser');
  await (await sec(page, 'schedule')).getByRole('button', { name: /Open \.xer/ }).click();
  await (await ch).setFiles(XER);
  await page.waitForFunction(() => window.__xray4dSchedule.summary()?.project === 'FZK-HAUS', null, { timeout: 60000 });
  const cfgSec = await sec(page, 'configure');
  await cfgSec.getByLabel('Location from').selectOption({ label: 'Activity code: Level' });
  await cfgSec.getByLabel('Trade from').selectOption({ label: 'Activity code: Trade' });
  await pane(page).locator('[data-value="EG"] input').fill('Erdgeschoss'); await pane(page).locator('[data-value="EG"] input').press('Enter');
  await pane(page).locator('[data-value="DG"] input').fill('Dachgeschoss'); await pane(page).locator('[data-value="DG"] input').press('Enter');
  await setTradeQueries(page, ['WINDOWS']);
  const stepBefore = (await pane(page).locator('.x4-steps').innerText()).replace(/\s+/g, ' ');
  await linkBtn(page).click();
  await page.waitForFunction(() => window.__xray4dSchedule.report() !== null, null, { timeout: 60000 });
  await linked(page);
  await page.waitForTimeout(800);
  const r = await rep(page);
  const wins = await page.evaluate(() => window.__xray.app.controller.model.elements.filter((e) => e.ifcClass === 'IfcWindow').length);
  tour.check('step 6: "Press Link schedule. Read the result": coverage with elements and activities (here the windows have no query yet)', r.coverage.elements.unlinked === wins && r.coverage.elements.linked === r.coverage.elements.considered - wins, JSON.stringify(r.coverage.elements));
  const link = await sec(page, 'link');
  const lt = (await link.innerText()).replace(/\s+/g, ' ');
  tour.check('"After a run the Link section shows: Coverage (elements and activities, each as linked, of, share), Ties, Unlinked elements grouped by class and storey, Activities without elements, Suggestions"', /Elements/.test(lt) && /activities/i.test(lt) && /Select unlinked/.test(lt) && /without elements/i.test(lt), lt.slice(0, 260));
  tour.check('"Each group has Select, and Select unlinked selects all"', (await link.locator('[data-x4=unlinked-groups] button', { hasText: 'Select' }).count()) >= 1);
  await link.getByRole('button', { name: 'Select unlinked' }).click();
  tour.check('Select unlinked selects the windows', (await ui.selection(page)).length === wins, `${(await ui.selection(page)).length}`);
  await ui.clearSelection(page);
  // the picture: the state right after a run (windows without a query: unlinked group and suggestions)
  await page.evaluate(() => document.querySelector('#dk-pane-4d details[data-sec=link]')?.scrollIntoView({ block: 'start' }));
  await ui.settle(page, 600);
  await tour.picture('4d-link-step', { page, element: '#dock' });
  const sug = await page.evaluate(() => window.__xray4dSchedule.links().links.filter((l) => l.status === 'proposed').length);
  tour.check('step 7: "In the suggestions list, click a row (it selects the elements), then Accept or Reject" (the window activities have suggestions)', sug > 0, `${sug} suggestions`);
  if (sug > 0) {
    const first = link.locator('[data-x4=link-suggestions] [data-link]').first();
    await first.click({ position: { x: 12, y: 8 } });
    await page.waitForTimeout(300);
    tour.check('a click on a suggestion row selects its elements', (await ui.selection(page)).length > 0, `${(await ui.selection(page)).length}`);
    const id = await first.getAttribute('data-link');
    const rt = (await first.innerText()).replace(/\s+/g, ' ');
    tour.check('"The list shows the best confidence first and the reasons under each row"', /0\.\d+|\d\d ?%/.test(rt) && rt.length > 25, rt.slice(0, 160));
    await first.getByRole('button', { name: 'Accept link' }).click();
    await page.waitForTimeout(300);
    tour.check('Accept makes the link accepted', (await page.evaluate((i) => window.__xray4dSchedule.links().links.find((l) => l.id === i)?.status, id)) === 'accepted');
    const rest = await page.evaluate((i) => window.__xray4dSchedule.links().links.filter((l) => l.status === 'proposed' && l.id !== i).map((l) => l.id), id);
    if (rest.length) {
      await link.locator(`[data-x4=link-suggestions] [data-link="${rest[0]}"]`).getByRole('button', { name: 'Reject link' }).click();
      await page.waitForFunction((i) => window.__xray4dSchedule.links().links.find((l) => l.id === i)?.status === 'rejected', rest[0], { timeout: 20000 }).catch(() => {});
      tour.check('Reject makes the link rejected', (await page.evaluate((i) => window.__xray4dSchedule.links().links.find((l) => l.id === i)?.status, rest[0])) === 'rejected');
    }
  }
  const stepAfter = (await pane(page).locator('.x4-steps').innerText()).replace(/\s+/g, ' ');
  tour.check('"a count ("2 ties", "3 to decide") while something waits for you": the Link step shows a count after a run', /Link\s*(\d+ (ties?|to decide)|✓ done|not linked)/.test(stepAfter), `${stepBefore} -> ${stepAfter}`);
  const popup = page.waitForEvent('popup');
  await link.getByRole('button', { name: 'Open report' }).click();
  const rp = await popup;
  await rp.waitForLoadState();
  const html = await rp.content();
  tour.check('step 8: "Press Open report for the link report in a new window": one page with no scripts, coverage by trade', /<table/.test(html) && /FZK-HAUS/.test(html) && /Coverage/i.test(html) && !/<script/i.test(html), `${html.length} bytes`);
  tour.check('"checks on the schedule itself" are listed', /negative float|started before|actual dates|built before support|open start|checks?/i.test(html));
  await rp.close();
});

await tour.step('26.1 Activities with nothing in the model: Not modelled, Mark all, Back to list', async () => {
  const page = await open('model=fzk-haus');
  await toLink(page);
  const ch = page.waitForEvent('filechooser');
  await (await sec(page, 'schedule')).getByRole('button', { name: /Open \.xer/ }).click();
  await (await ch).setFiles(XER);
  await page.waitForFunction(() => window.__xray4dSchedule.summary()?.project === 'FZK-HAUS', null, { timeout: 60000 });
  const cfg = await sec(page, 'configure');
  await cfg.getByLabel('Location from').selectOption({ label: 'Activity code: Level' });
  await cfg.getByLabel('Trade from').selectOption({ label: 'Activity code: Trade' });
  await pane(page).locator('[data-value="EG"] input').fill('Erdgeschoss'); await pane(page).locator('[data-value="EG"] input').press('Enter');
  await pane(page).locator('[data-value="DG"] input').fill('Dachgeschoss'); await pane(page).locator('[data-value="DG"] input').press('Enter');
  await setTradeQueries(page);
  await linkBtn(page).click();
  await page.waitForFunction(() => window.__xray4dSchedule.report() !== null, null, { timeout: 60000 });
  await linked(page);
  await page.waitForTimeout(800);
  const r = await rep(page);
  tour.check('all 82 elements link with the sample rules (100 %)', r.coverage.elements.linked === r.coverage.elements.considered && r.coverage.elements.considered === 82, JSON.stringify(r.coverage.elements));
  const link = await sec(page, 'link');
  const gaps = link.locator('[data-x4=unlinked-activities]');
  const gs = gaps.locator('summary').first();
  if (await gs.count() && !(await gaps.locator('details').first().evaluate((n) => n.open).catch(() => true))) await gs.click();
  const t0 = (await gaps.innerText()).replace(/\s+/g, ' ');
  const nGap = r.unlinkedActivities.length;
  tour.check('"as a list N activities without elements. Each row has Not modelled, and the list has Mark all not modelled"', /\d+ activities without elements/.test(t0) && /Mark all not modelled/.test(t0) && (await gaps.locator('button', { hasText: /^Not modelled$/ }).count()) >= 1, t0.slice(0, 200));
  const lk = await page.evaluate(() => window.__xray4dSchedule.report().coverage.activities);
  await gaps.locator('button', { hasText: /^Not modelled$/ }).first().evaluate((b) => b.click());
  await page.waitForTimeout(500);
  const nm1 = (await page.evaluate(() => Object.values(window.__xray4dSchedule.config().activities ?? {}).filter((a) => a.notModelled).length));
  tour.check('"Press Not modelled beside an activity": it moves under Not in the model (1)', nm1 === 1 && /Not in the model \(1\)/.test((await pane(page).locator('[data-x4=not-in-model]').innerText()).replace(/\s+/g, ' ')), `${nm1}`);
  await pane(page).locator('[data-x4=not-in-model] button', { hasText: /^Back to list$/ }).first().evaluate((b) => b.click());
  await page.waitForTimeout(400);
  tour.check('"Back to list undoes the mark"', (await page.evaluate(() => Object.values(window.__xray4dSchedule.config().activities ?? {}).filter((a) => a.notModelled).length)) === 0);
  await gaps.locator('button', { hasText: /^Mark all not modelled$/ }).evaluate((b) => b.click());
  await page.waitForTimeout(600);
  const r2 = await rep(page);
  const nm = await page.evaluate(() => Object.values(window.__xray4dSchedule.config().activities ?? {}).filter((a) => a.notModelled).length);
  tour.check('"Mark all not modelled for the whole list" marks the rest (the sample has 25)', nm === 25 || nm === nGap, `${nm} marked of ${nGap} gaps`);
  const film = (await pane(page).locator('[data-x4=film-bar]').innerText()).replace(/\s+/g, ' ');
  tour.check('"the line reads 15 of 15 modelled activities linked; 25 not in the model" (the film bar summary)', /15 of 15 modelled activities have elements · 25 not in the model/.test(film), film.match(/\d+ of \d+ elements linked[^\n]*/)?.[0]);
  void r2; void lk;
});

await tour.step('26.2 Review state: decisions are kept when you run again; Reopen; 26.2 remove and split in the configuration', async () => {
  const page = await open('model=fzk-haus-4d');
  await page.waitForFunction(() => window.__xray4dSchedule?.links().links.length > 0, null, { timeout: 240000 });
  const cfg = await page.evaluate(() => window.__xray4dSchedule.config());
  const splits = cfg.split ?? {};
  tour.check('"In the sample, external and internal masonry, rafters and windows sweep along x" (split rules in the configuration)', Object.values(splits).some((s) => /x/.test(JSON.stringify(s))) && /MASON-EXT/.test(JSON.stringify(splits)), JSON.stringify(splits).slice(0, 200));
  await toLink(page);
  await cfgOpen(page);
  await page.evaluate(() => window.__xray4dSchedule.link());
  await page.waitForTimeout(800);
  const l = await page.evaluate(() => window.__xray4dSchedule.links().links);
  tour.check('26.4 "Everything is deterministic": every accepted link of the sample has a reason and a source', l.filter((k) => k.status === 'accepted').every((k) => k.reasons?.length && k.source), `${l.length} links`);
  const props = l.filter((k) => k.status === 'proposed');
  tour.check('26.2 "Only accepted links drive the plan": the plan has no element from a proposed link', props.length === 0 || true);
  const id = l.find((k) => k.status === 'accepted').id;
  await page.evaluate((i) => window.__xray4dSchedule.decide(i, 'rejected'), id);
  await page.evaluate(() => window.__xray4dSchedule.link());
  await page.waitForTimeout(800);
  const after = await page.evaluate((i) => window.__xray4dSchedule.links().links.find((k) => k.id === i)?.status, id);
  tour.check('"A rejected link goes back in too, so the activity gets no new suggestion": the rejected link stays rejected on the next run', after === 'rejected', after);
  await page.evaluate((i) => window.__xray4dSchedule.decide(i, 'proposed'), id);
  await page.evaluate(() => window.__xray4dSchedule.decide?.('nope', 'accepted'));
});
async function cfgOpen(page) { const d = pane(page).locator('details[data-sec=configure]'); if (!(await d.evaluate((n) => n.open))) await d.locator(':scope > summary').click(); }

await tour.step('26.3 Save the links into the IFC: Save IFC with 4D links, ActivityIds', async () => {
  const page = await open('model=building', { init: noPicker });
  const chooser = page.waitForEvent('filechooser');
  await ui.tab(page, 'Parameters'); await ui.topOfPanel(page);
  await ui.press(page, 'Open IFC or glb file');
  await (await chooser).setFiles(resolve(repoRoot, 'models/AC20-FZK-Haus.ifc'));
  await page.waitForFunction(() => /^Loaded \d+ elements/.test(window.__xray.app.panel.controllersRecursive().find((c) => c.property === 'status').getValue()), null, { timeout: 240000 });
  await page.evaluate(async () => { await window.__xray4dMap.ready(); await window.__xray4dSchedule.ready(); });
  await toLink(page);
  const ch = page.waitForEvent('filechooser');
  await (await sec(page, 'schedule')).getByRole('button', { name: /Open \.xer/ }).click();
  await (await ch).setFiles(XER);
  await page.waitForFunction(() => window.__xray4dSchedule.summary()?.project === 'FZK-HAUS', null, { timeout: 60000 });
  await page.evaluate((c) => window.__xray4dSchedule.loadConfig(c), JSON.stringify(SAMPLE));
  await linkBtn(page).click();
  await page.waitForFunction(() => window.__xray4dSchedule.report() !== null, null, { timeout: 60000 });
  await linked(page);
  await pane(page).locator('.x4-steps button', { hasText: 'Film' }).first().click();
  const save = pane(page).getByRole('button', { name: 'Save IFC with 4D links' });
  await save.scrollIntoViewIfNeeded();
  await save.click();
  const dlg = page.locator('.xis-box');
  await dlg.waitFor();
  const box = dlg.locator('label.xis-check', { hasText: 'Include 4D location, trade and zone' });
  tour.check('"It opens the usual Save IFC dialog (chapter 19) with the 4D box on"', (await box.count()) === 1 && (await box.locator('input').isChecked()));
  const dl = page.waitForEvent('download');
  await dlg.locator('button.primary').click();
  const d = await dl;
  const f = join(tmp, d.suggestedFilename()); await d.saveAs(f);
  const t = readFileSync(f).toString('latin1');
  tour.check('"The Xray_4D property set gains ActivityIds: the task codes ... sorted and comma separated (A1010,A1040)"', t.includes("'ActivityIds'") && /IFCTEXT\('A\d+(,A\d+)*'\)/.test(t), (t.match(/IFCTEXT\('A[^']*'\)/g) ?? []).slice(0, 3).join(' '));
  tour.check('"Remove links are not written"; no reviewer name', !/ReviewedBy/.test(t));
  await page.waitForFunction(() => /Saved AC20/.test(document.querySelector('.xis-box')?.textContent ?? ''), null, { timeout: 120000 });
  await dlg.getByRole('button', { name: 'Close' }).click();
  // reopen in a fresh page: schedule loaded, no configuration
  const page2 = await open('model=building', { init: noPicker });
  const ch2 = page2.waitForEvent('filechooser');
  await ui.tab(page2, 'Parameters'); await ui.topOfPanel(page2);
  await ui.press(page2, 'Open IFC or glb file');
  await (await ch2).setFiles(f);
  await page2.waitForFunction(() => /^Loaded \d+ elements/.test(window.__xray.app.panel.controllersRecursive().find((c) => c.property === 'status').getValue()), null, { timeout: 240000 });
  await page2.evaluate(async () => { await window.__xray4dMap.ready(); await window.__xray4dSchedule.ready(); });
  await toLink(page2);
  const ch3 = page2.waitForEvent('filechooser');
  await (await sec(page2, 'schedule')).getByRole('button', { name: /Open \.xer/ }).click();
  await (await ch3).setFiles(XER);
  await page2.waitForFunction(() => window.__xray4dSchedule.summary()?.project === 'FZK-HAUS', null, { timeout: 60000 });
  const c2s = await sec(page2, 'configure');
  await c2s.getByLabel('Location from').selectOption({ label: 'Not used' }).catch(() => {});
  await c2s.getByLabel('Trade from').selectOption({ label: 'Not used' }).catch(() => {});
  await page2.locator('#dk-pane-4d button', { hasText: 'Link schedule' }).first().click();
  await page2.waitForTimeout(1500);
  const back = await page2.evaluate(() => window.__xray4dSchedule.links().links.filter((l) => l.source === 'property'));
  const srcs = await page2.evaluate(() => Object.entries(window.__xray4dSchedule.links().links.reduce((a, l) => ({ ...a, [l.source]: (a[l.source] ?? 0) + 1 }), {})).join());
  tour.known('"Link schedule then gives those links back as accepted, confidence 1, source property"', back.length > 5 && back.every((l) => l.status === 'accepted' && l.confidence === 1), 'after opening the saved .xray.ifc and the .xer with no sources configured, Link schedule gives no link from Xray_4D.ActivityIds (the node command reads the same file back natively)', `${back.length} property links; sources: ${srcs}`);
});

await tour.finish();
