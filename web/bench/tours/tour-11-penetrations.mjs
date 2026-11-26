// Tour of chapter 11, "Penetrations" (docs/manual/11-penetrations.md): the penetration schedule (11.1) and raising findings as issues (11.2).
// No pictures in this chapter.
// Run: node bench/run-smokes.mjs --only tour-11-penetrations
import { readFileSync } from 'node:fs';
import { startTour, ui } from './lib.mjs';

const tour = await startTour('tour-11-penetrations');
const rowsOf = (page) => page.locator('.xt-table tbody tr');
const heads = (page) => page.locator('.xt-table thead th').allInnerTexts();

await tour.step('11.1 Try it: the schedule on Synthetic 5k', async () => {
  const page = await tour.open('model=synth5k');
  page.setDefaultTimeout(60000);
  await ui.tool(page, 'Penetrations').click();
  await page.locator('.xt-status').first().waitFor({ timeout: 15000 });
  await page.waitForFunction(() => window.__xrayPenetrations.rows.length > 0, null, { timeout: 120000 });
  const sum = await page.evaluate(() => window.__xrayPenetrations.summary);
  const status = await page.locator('.xt-status').first().innerText();
  tour.check('step 2: "A wide drawer opens and analyses once"', sum.total > 0, JSON.stringify(sum));
  tour.check('step 3: "Read the summary counts at the top"', /\d+ penetrations: \d+ with opening, \d+ no opening, \d+ unknown/.test(status), status);
  const chipTexts = await page.locator('.xt-chip').allInnerTexts();
  tour.check('step 3: "filter chips for status, storey and host class"', chipTexts.some((t) => /^opening/.test(t)) && chipTexts.some((t) => /^Level/.test(t)), chipTexts.join(' | '));
  const hostClasses = await page.evaluate(() => [...new Set(window.__xrayPenetrations.rows.map((r) => window.__xray.app.controller.model.elements[r.host].ifcClass))]);
  tour.check('step 3: the host class chips show when the hosts have more than one class', hostClasses.length > 1 ? chipTexts.some((t) => /^(Slab|Wall|Beam|Column)/.test(t)) : !chipTexts.some((t) => /^(Slab|Wall|Beam|Column)/.test(t)), `hosts: ${hostClasses.join(',')}`);
  tour.check('"On Synthetic 5k every crossing shows as opening": none without an opening', sum.none === 0 && sum.unknown === 0 && sum.opening === sum.total, JSON.stringify(sum));
  const gaps = await page.evaluate(() => [...new Set(window.__xrayPenetrations.rows.map((r) => Math.round(r.gapMm)))]);
  tour.check('"with a gap of 10 mm"', gaps.length === 1 && gaps[0] === 10, gaps.join(','));
  const hs = await heads(page);
  tour.check('"What the columns say": #, Element, Host, Storey, Size, Thk, Status, Gap', ['#', 'Element', 'Host', 'Storey', 'Size', 'Thk', 'Status', 'Gap'].every((h, i) => hs[i]?.replace(/[▲▼↑↓\s]/g, '') === h), hs.join(' | '));
  // step 4: sort
  const firstId = async () => (await rowsOf(page).first().locator('td').first().innerText()).trim();
  const id0 = await firstId();
  await page.locator('.xt-table thead th', { hasText: 'Host' }).click();
  await page.waitForTimeout(300);
  const hostsSorted = await rowsOf(page).evaluateAll((r) => r.slice(0, 20).map((x) => x.children[2].textContent.trim()));
  tour.check('step 4: "Click a column header to sort"', hostsSorted.join() === [...hostsSorted].sort((a, b) => a.localeCompare(b, undefined, { numeric: true })).join() || hostsSorted.join() === [...hostsSorted].sort().join(), hostsSorted.slice(0, 5).join(' | '));
  await page.locator('.xt-table thead th', { hasText: '#' }).first().click();
  // filters
  const nAll = await rowsOf(page).count();
  const storeyChip = page.locator('.xt-chip', { hasText: /^Level 1$/ });
  await storeyChip.click();
  await page.waitForTimeout(400);
  const nL1 = await rowsOf(page).count();
  tour.check('step 4: "Use the filter chips to narrow the list by storey"', nL1 > 0 && nL1 < nAll, `${nAll} -> ${nL1}`);
  await storeyChip.click();
  const hostChip = page.locator('.xt-chip', { hasText: /^(Slab|Wall|Beam|Column)$/ }).first();
  if (await hostChip.count()) {
    await hostChip.click();
    await page.waitForTimeout(400);
    const nHost = await rowsOf(page).count();
    tour.check('step 4: "or host class"', nHost > 0 && nHost < nAll, `${nAll} -> ${nHost}`);
    await hostChip.click();
    await page.waitForTimeout(300);
  }
  tour.check('the filters can be cleared again', (await rowsOf(page).count()) === nAll);
  // step 5: click a row
  const row = rowsOf(page).nth(2);
  const c0 = await ui.cam(page);
  await row.click();
  await ui.waitMoved(page, c0, 12000).catch(() => {});
  const sel = await ui.selection(page);
  const rowData = await page.evaluate(() => window.__xrayPenetrations.rows[2]);
  tour.check('step 5: "Click a row. The MEP element is selected"', sel.length === 1 && sel[0].id === rowData.mep, JSON.stringify(sel) + ' mep ' + rowData.mep);
  const c1 = await ui.cam(page);
  tour.check('step 5: "the camera flies to the crossing"', Math.hypot(...c1.p.map((v, i) => v - c0.p[i])) > 0.3, `moved ${Math.hypot(...c1.p.map((v, i) => v - c0.p[i])).toFixed(1)} m`);
  const other = await page.evaluate((mep0) => window.__xrayPenetrations.rows.findIndex((r, i) => r.mep !== mep0 && i < 500), rowData.mep);
  await rowsOf(page).nth(other).click({ modifiers: ['Control'] });
  for (let i = 0; i < 10 && (await ui.selection(page)).length < 2; i++) await page.waitForTimeout(700);
  tour.known('step 5: "Ctrl or Shift click selects several rows"', (await ui.selection(page)).length >= 2, 'a Ctrl+click on a second row (a different MEP element) left only one element selected', String((await ui.selection(page)).length));
  // step 6: markers
  const markersOn = await page.evaluate(() => document.querySelectorAll('svg [data-pen], svg g[data-marker], svg circle').length);
  tour.check('step 6: "Look at the markers in the model"', markersOn > 0, String(markersOn));
  const cb = page.getByText('Markers on the model');
  await cb.click();
  await page.waitForTimeout(400);
  const markersOff = await page.evaluate(() => document.querySelectorAll('svg [data-pen], svg g[data-marker]').length);
  tour.check('step 6: "The markers option turns them on and off"', markersOff === 0 || markersOff < markersOn, `${markersOn} -> ${markersOff}`);
  await cb.click();
  // step 7: export
  const [dl] = await Promise.all([page.waitForEvent('download', { timeout: 20000 }), page.getByRole('button', { name: /^Export CSV/ }).click()]);
  const csv = readFileSync(await dl.path(), 'utf8').split('\n').filter(Boolean);
  tour.check('step 7: "Export CSV to save the filtered rows": the file has the location and orientation columns', csv.length === (await page.evaluate(() => window.__xrayPenetrations.rows.length)) + 1 && /orientation/i.test(csv[0]) && /x_m,y_m,z_m/.test(csv[0]), csv[0]);
  // scope
  const orient = await page.evaluate(() => [...new Set(window.__xrayPenetrations.rows.map((r) => r.orientation))]);
  tour.check('"orientation: vertical, horizontal or inclined"', orient.every((o) => ['vertical', 'horizontal', 'inclined'].includes(o)), orient.join());
  tour.check('"A host ... slab, wall, beam, column, footing or roof"', await page.evaluate(() => window.__xrayPenetrations.rows.every((r) => /Slab|Wall|Beam|Column|Footing|Roof/.test(window.__xray.app.controller.model.elements[r.host].ifcClass))));
  tour.check('"The drawer lists at most 500 rows"', (await rowsOf(page).count()) <= 500);
  // scope focus only
  const scopeSel = page.locator('select').filter({ has: page.locator('option', { hasText: 'focus only' }) }).first();
  const okScope = await scopeSel.selectOption({ label: 'focus only' }, { timeout: 8000 }).then(() => true).catch(() => false);
  await ui.clearSelection(page);
  const okAn = await page.getByRole('button', { name: 'Analyse', exact: true }).click({ timeout: 20000, force: true }).then(() => true).catch(() => false);
  tour.known('"Analyse runs it again, for example after you changed the scope"', okScope && okAn, 'the scope list or the Analyse button of the drawer could not be used', `scope ${okScope}, analyse ${okAn}`);
  await page.waitForTimeout(3000);
  const sumFocus = await page.evaluate(() => window.__xrayPenetrations.summary.total);
  tour.check('"scope: focus only (the current focus)" re-analyses with fewer or no rows', sumFocus <= nAll, `${nAll} -> ${sumFocus}`);
});

await tour.step('11.1 Models without opening data read unknown (Building)', async () => {
  const page = await tour.open('model=building');
  const r = await page.evaluate(() => window.__xrayPenetrations.analyse && 0);
  void r;
  await ui.tool(page, 'Penetrations').click();
  await page.waitForTimeout(3000);
  const sum = await page.evaluate(() => window.__xrayPenetrations.summary);
  tour.check('"Sample models building and plumbing have no opening relations": no crossing reads opening', sum.opening === 0, JSON.stringify(sum));
  tour.check('"unknown: the model has no opening data at all"', sum.total === 0 || sum.unknown === sum.total, JSON.stringify(sum));
});

await tour.step('11.2 Raise findings as issues', async () => {
  const page = await tour.open('model=synth5k');
  await ui.tool(page, 'Penetrations').click();
  await page.waitForFunction(() => window.__xrayPenetrations.rows.length > 0, null, { timeout: 120000 });
  const btn = page.getByRole('button', { name: 'Raise issues from results' });
  tour.check('"The drawer has an Issues block with Raise issues from results"', (await btn.count()) >= 1);
  const rows = await page.evaluate(() => window.__xrayPenetrations.rows.length);
  await page.locator('.xt-table tbody tr').nth(0).click();
  await page.locator('.xt-table tbody tr').nth(1).click({ modifiers: ['Control'] });
  await btn.first().click();
  await page.waitForTimeout(2500);
  const issueTitles = () => page.evaluate(() => (window.__xrayBcf.currentTopics ?? window.__xrayBcf.topics).map((t) => t.title));
  const info = await issueTitles();
  tour.check('"It makes one issue per row, titled like Penetration: Duct-12 through Wall-3": two selected rows make two issues', info.length === 2 && info.every((t) => /^Penetration: .+ through .+/.test(t)), `${rows} rows; ${JSON.stringify(info).slice(0, 200)}`);
  await btn.first().click();
  await page.waitForTimeout(2000);
  const info2 = (await issueTitles()).length;
  tour.check('"Raising again only adds new pairs"', info2 === info.length, `${info.length} -> ${info2}`);
});

await tour.finish();
