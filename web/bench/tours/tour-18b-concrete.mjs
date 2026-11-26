// Tour of chapter 18B, "Concrete elements" (docs/manual/18b-concrete.md): the Concrete switch, the Bodenplatte's role and mark, the queries over the
// XR_Concrete* sets. Picture: `concrete-sets`.
// Run: node bench/run-smokes.mjs --only tour-18b-concrete
import { startTour, ui } from './lib.mjs';

const tour = await startTour('tour-18b-concrete');
const pane = (page) => page.locator('#dk-pane-classification');
const search = async (page, text) => {
  await page.keyboard.press('Escape');
  await page.mouse.move(900, 500);
  await page.keyboard.press('/');
  await page.keyboard.press('Control+a');
  await page.keyboard.type(text);
  await page.waitForTimeout(1000);
  return (await page.locator('.ab-pop').innerText().catch(() => '')).replace(/\n+/g, ' / ');
};

await tour.step('18B.1 Try it: Concrete switch, Classify all, the Bodenplatte, the queries', async () => {
  const page = await tour.open('model=fzk-haus');
  await ui.tab(page, 'Classification');
  await page.waitForTimeout(500);
  const f = pane(page).locator('details.xc-facets');
  if (!(await f.evaluate((d) => d.open))) await f.locator('summary').click();
  const conc = f.locator('label', { hasText: /^Concrete/ }).locator('input');
  tour.check('step 1: "open the Facets folder and check that Concrete is on"', (await conc.count()) === 1 && (await conc.isChecked()));
  await pane(page).getByRole('button', { name: 'Classify all' }).click();
  await page.waitForFunction(() => window.__xrayClassify.results().length >= 82, null, { timeout: 180000 });
  await page.waitForTimeout(15000);
  const q0 = await search(page, "count where ConcreteElement = 'SLAB_ON_GRADE'");
  tour.check('step 1: "Click Classify all. Concrete runs after the facets": the concrete sets are queryable', /\b[1-9]\d* (elements|slabs?)/.test(q0) || /SUMMARY \/ [1-9]/.test(q0), q0.slice(0, 120));
  // step 2: select the Bodenplatte
  const sr = await search(page, 'Bodenplatte');
  tour.check('the search finds the Bodenplatte', /Bodenplatte/.test(sr), sr.slice(0, 100));
  await page.keyboard.press('ArrowDown');
  await page.keyboard.press('Enter');
  await ui.waitStill(page, 15000);
  const sel = await ui.selection(page);
  tour.check('step 2: "Select the ground slab, named Bodenplatte"', sel.length === 1 && /Bodenplatte/.test(sel[0].name ?? ''), JSON.stringify(sel));
  await ui.tab(page, 'Classification');
  await page.waitForTimeout(1200);
  const rows = await f.locator('[data-facet^=Concrete] ').allInnerTexts();
  const txt = rows.map((r) => r.replace(/\s+/g, ' ')).join(' | ');
  tour.check('step 2: "read its concrete sets: role SLAB_ON_GRADE, mark SG0-01"', /SLAB_ON_GRADE/.test(txt) && /SG0-01/.test(txt), txt.slice(0, 400));
  tour.check('"Volume" and "FormworkArea" show for the geometry set', /Volume/.test(txt) && /FormworkArea/.test(txt), txt.slice(0, 400));
  await f.evaluate((e) => e.scrollIntoView({ block: 'start' }));
  await page.mouse.move(700, 120);
  await page.waitForTimeout(600);
  await tour.picture('concrete-sets', { page, element: '#dock' });
  const t3 = await search(page, "count where ConcreteElement = 'SLAB_ON_GRADE'");
  tour.check('step 3: "count where ConcreteElement = \'SLAB_ON_GRADE\'"', /\b\d+\b/.test(t3) && !/^QUERY \/ 0 /.test(t3), t3.slice(0, 140));
  const t4 = await search(page, 'sum XR_ConcreteGeometry.Volume by Storey');
  tour.check('step 4: "sum XR_ConcreteGeometry.Volume by Storey totals the measured concrete per storey"', /Σ Volume|Σ volume|m³/i.test(t4), t4.slice(0, 200));
  const t5 = await search(page, 'where XR_ConcreteSpec.NeedsReview = TRUE');
  tour.check('step 5: "where XR_ConcreteSpec.NeedsReview = TRUE" counts the suggested specs', /elements? match/.test(t5), t5.slice(0, 140));
  const t6 = await search(page, "where XR_ConcreteSpec.ExposureClass contains 'XD'");
  tour.check('"contains tests text: where XR_ConcreteSpec.ExposureClass contains \'XD\'" parses', /elements? match|0 elements/.test(t6) && !/Expected/.test(t6), t6.slice(0, 140));
  await page.keyboard.press('Escape');
  // method and reinforcement
  const t7 = await search(page, "count where ConcreteMethod = 'CAST_IN_PLACE'");
  tour.check('"ConcreteMethod stands for XR_ConcreteMethod.Code": foundations are cast in place', /\b\d+\b/.test(t7), t7.slice(0, 140));
  await page.keyboard.press('Escape');
});

await tour.finish();
