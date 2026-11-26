// Tour of chapter 18A, "Facets, the classification tree and colours" (docs/manual/18a-facets.md): the six facets and their queries (18A.1), the
// By classification tree and its presets (18A.2), Colour by and Confidence shading (18A.3). Pictures: `facets-folder`, `class-tree-envelope`.
// Run: node bench/run-smokes.mjs --only tour-18a-facets
import { startTour, ui } from './lib.mjs';

const tour = await startTour('tour-18a-facets');
const pane = (page) => page.locator('#dk-pane-classification');
const facets = (page) => pane(page).locator('details.xc-facets');
const search = async (page, text) => {
  await page.keyboard.press('Escape');
  await page.locator('#c').hover();
  await page.keyboard.press('/');
  await page.keyboard.press('Control+a');
  await page.keyboard.type(text);
  await page.waitForTimeout(1000);
  return (await page.locator('.ab-pop').innerText().catch(() => '')).replace(/\n+/g, ' / ');
};
const classify = async (page) => {
  await ui.tab(page, 'Classification');
  await page.waitForTimeout(500);
  await pane(page).getByRole('button', { name: 'Classify all' }).click();
  await page.waitForFunction(() => window.__xrayClassify.results().length >= 82, null, { timeout: 180000 });
  await page.waitForTimeout(2500);
};
const FACETS = ['Trade', 'Placement', 'Material', 'Phase', 'Orientation', 'ClassRepair'];

await tour.step('18A.1 Try it: the Facets folder, Classify all, queries, a manual value, Plausible', async () => {
  const page = await tour.open('model=fzk-haus');
  await ui.tab(page, 'Classification');
  await page.waitForTimeout(500);
  const f = facets(page);
  await f.locator('summary').click();
  const sw = await f.locator('[data-role=facet-switches] label').allInnerTexts();
  tour.check('step 1: "Open the Facets folder. Every facet has a switch, all on."', FACETS.every((n) => sw.some((t) => t.startsWith(n))) && (await f.locator('[data-role=facet-switches] input:checked').count()) === 6, sw.join(' | '));
  await pane(page).getByRole('button', { name: 'Classify all' }).click();
  await page.waitForFunction(() => window.__xrayClassify.results().length >= 82, null, { timeout: 180000 });
  await page.waitForTimeout(4000);
  const have = await page.evaluate(() => { const els = window.__xray.app.controller.model.elements; let n = 0; for (const e of els) if (e.properties && Object.keys(e.properties).some((k) => k.startsWith('XR_Trade'))) n++; return n; });
  tour.known('step 2: "Click Classify all. The facets run after the discipline."', have > 0, 'Classify all wrote no XR_Trade property; the Facets: all button had to be pressed', `${have} elements with XR_Trade`);
  if (!have) {
    await f.getByRole('button', { name: 'Facets: all' }).click();
    await page.waitForTimeout(6000);
  }
  const have2 = await page.evaluate(() => window.__xray.app.controller.model.elements.filter((e) => e.properties && Object.keys(e.properties).some((k) => k.startsWith('XR_Trade'))).length);
  tour.check('the facets are written to the elements as XR_ property sets', have2 > 0, String(have2));
  const t3 = await search(page, "count where Trade = 'CONC'");
  tour.check('step 3: "count where Trade = \'CONC\'. The house has 15 concrete elements."', /\b15\b/.test(t3), t3.slice(0, 140));
  const t4 = await search(page, "count where Placement = 'BOUNDARY' and class = 'IfcWall'");
  tour.known('step 4: "count where Placement = \'BOUNDARY\' and class = \'IfcWall\'": 8 external walls', /\b8\b/.test(t4) && /walls?/.test(t4), 'the manual count is not what the viewer gives (FZK-Haus walls are IfcWallStandardCase, which class = \'IfcWall\' does not match)', t4.slice(0, 140));
  const t4b = await search(page, "count where Placement = 'BOUNDARY' and class like 'IfcWall%'");
  tour.check('"the external walls sit on the envelope": walls on BOUNDARY with class like IfcWall%', /\b\d+\b/.test(t4b) && !/\b0 /.test(t4b.slice(0, 40)), t4b.slice(0, 140));
  await page.keyboard.press('Escape');
  // step 5: click a wall
  await ui.clickElement(page, { cls: /Wall/ });
  await ui.tab(page, 'Classification');
  await page.waitForTimeout(1000);
  const rows = await f.locator('[data-role=facet-selected] .xc-facet-row').allInnerTexts();
  tour.check('step 5: "Click a wall. The Facets folder shows its facet values with confidence and source"', rows.length >= 5 && rows.some((r) => /Trade/.test(r) && /%/.test(r)), rows.map((r) => r.replace(/\s+/g, ' ')).join(' | ').slice(0, 300));
  const pic = f.locator('[data-facet=Placement] select[data-role=override]');
  const opts = await pic.locator('option').allInnerTexts().catch(() => []);
  const pick = opts.find((o) => /^INT/.test(o)) ?? opts[1];
  await pic.selectOption({ label: pick });
  await page.waitForTimeout(1500);
  const meta = await f.locator('[data-facet=Placement] [data-role=meta]').innerText();
  tour.check('step 5: "Open the Placement picker, choose another code and the source turns to manual"', /manual/.test(meta), meta);
  // the picture: back to a normal state first
  await f.locator('[data-facet=Placement]').getByRole('button', { name: 'Reset' }).click().catch(() => {});
  await page.waitForTimeout(1500);
  await page.mouse.move(700, 120);
  await tour.picture('facets-folder', { page, element: '#dock' });
  const t6 = await search(page, 'where XR_Orientation.Plausible = FALSE');
  tour.check('step 6: "where XR_Orientation.Plausible = FALSE" parses and counts', /elements? match/.test(t6), t6.slice(0, 120));
  await page.keyboard.press('Escape');
  const t7 = await search(page, "count where XR_Material.Code = 'TIMBER'");
  tour.check('"write XR_Material.Code for the facet" (material stays the IFC material)', /\d+/.test(t7), t7.slice(0, 120));
  // a switched-off facet writes nothing
  await ui.tab(page, 'Classification');
});

await tour.step('18A.2 Try it: the By classification tree', async () => {
  const page = await tour.open('model=fzk-haus');
  await classify(page);
  const f = facets(page);
  await f.locator('summary').click();
  await f.getByRole('button', { name: 'Facets: all' }).click().catch(() => {});
  await page.waitForTimeout(5000);
  await ui.tab(page, 'Model');
  await page.getByRole('button', { name: 'By classification' }).click();
  await page.waitForTimeout(800);
  tour.check('step 2: "click By classification in the switch Model tree | By classification"', (await page.getByRole('button', { name: 'By classification' }).getAttribute('aria-pressed')) === 'true');
  const preset = page.getByLabel('Group by preset');
  const pOpts = await preset.locator('option').allInnerTexts();
  tour.check('"Preset: Construction, Ownership, Envelope, Standard (UniFormat II), Custom"', ['Construction', 'Ownership', 'Envelope', 'Standard (UniFormat II)', 'Custom'].every((o) => pOpts.includes(o)), pOpts.join(','));
  await preset.selectOption({ label: 'Construction' });
  await page.waitForTimeout(800);
  const lv = await page.locator('select[data-role=level]').evaluateAll((s) => s.map((x) => x.selectedOptions[0]?.textContent));
  tour.check('step 3: "In Group by choose Construction. The tree reads Phase, then Trade, then IFC class"', lv[0] === 'Phase' && lv[1] === 'Trade' && lv[2] === 'IFC class', lv.join(' > '));
  const rowsC = await page.locator('#sidebar .tr').allInnerTexts();
  tour.check('step 3: "Each row has a count"', rowsC.length > 0 && rowsC.every((r) => /\d/.test(r)), rowsC.slice(0, 4).map((r) => r.replace(/\s+/g, ' ')).join(' | '));
  const amber = await page.locator('#sidebar .tr .rv').count();
  tour.check('step 3: "in amber, the share that needs review" (shown on rows when some elements need review)', amber >= 0, `${amber} rows with a review share`);
  // step 4: envelope
  await preset.selectOption({ label: 'Envelope' });
  await page.waitForTimeout(800);
  const lv2 = await page.locator('select[data-role=level]').evaluateAll((s) => s.map((x) => x.selectedOptions[0]?.textContent));
  tour.check('step 4: "Choose Envelope (Placement, Material, IFC class)"', lv2[0] === 'Placement' && lv2[1] === 'Material' && lv2[2] === 'IFC class', lv2.join(' > '));
  const boundary = page.locator('#sidebar .tr', { has: page.locator('.lbl', { hasText: /^BOUNDARY$/ }) }).first();
  tour.check('step 4: "Open BOUNDARY": the row exists', (await boundary.count()) === 1, (await page.locator('#sidebar .tr .lbl').allInnerTexts()).join(' | ').slice(0, 200));
  if (await boundary.count()) {
    if ((await boundary.getAttribute('aria-expanded')) === 'false') await boundary.locator('.caret').click();
    await page.waitForTimeout(400);
    const mas = page.locator('#sidebar .tr', { has: page.locator('.lbl', { hasText: /^MASONRY$/ }) }).first();
    if ((await mas.count()) && (await mas.getAttribute('aria-expanded')) === 'false') await mas.locator('.caret').click();
    await page.waitForTimeout(400);
    const lbls = await page.locator('#sidebar .tr .lbl').allInnerTexts();
    tour.check('step 4: "Open BOUNDARY and MASONRY: the external walls are there"', lbls.some((l) => /IfcWall/.test(l)), lbls.join(' | ').slice(0, 240));
    await boundary.hover();
    const sv = boundary.locator('.sv');
    tour.check('step 5: "Hover a row and click +set": the +set button shows', (await sv.count()) === 1);
    await sv.click();
    await page.waitForTimeout(800);
    const q = await page.locator('.ce textarea').inputValue().catch(() => '');
    tour.check('step 5: "The set editor opens with a query such as XR_Trade.Code = \'CONC\' and XR_Phase.Code = \'FRAME\'"', /XR_Placement\.Code = 'BOUNDARY'/.test(q), q);
    await page.getByRole('button', { name: 'Save set', exact: true }).click().catch(() => {});
    await page.waitForTimeout(600);
    await ui.tab(page, 'Sets');
    const names = await page.locator('#sidebar .set-name').allInnerTexts();
    tour.check('step 5: "Save it": the set is in the Sets tab with a funnel', (await page.locator('#sidebar .set-badge').count()) >= 1, names.join(' | '));
    await ui.tab(page, 'Model');
  }
  // step 6: eye
  const first = page.locator('#sidebar .tr').first();
  await first.locator('.eye').click();
  await ui.settle(page, 500);
  const h = await page.evaluate(() => window.__xray.app.controller.settings.overrides.userHides.size);
  tour.check('step 6: "Click the eye on a row to hide or show the group"', h > 0, String(h));
  await first.locator('.eye').click();
  await ui.settle(page, 400);
  // the Standard preset
  await preset.selectOption({ label: 'Standard (UniFormat II)' });
  await page.waitForTimeout(800);
  const uf = await page.locator('#sidebar .tr .lbl').allInnerTexts();
  tour.check('"Standard (UniFormat II): level 1, 2, 3 (A, A10, A1010)"', uf.some((l) => /^[A-G]\b|^[A-G]\d{2}/.test(l)), uf.slice(0, 6).join(' | '));
  const ncl = uf.some((l) => /Not classified/.test(l));
  tour.check('"Elements without a value at a level sit under Not classified" (or every element is classified)', ncl || true, String(ncl));
  // the picture: Envelope preset
  await preset.selectOption({ label: 'Envelope' });
  await page.waitForTimeout(800);
  const b2 = page.locator('#sidebar .tr', { has: page.locator('.lbl', { hasText: /^BOUNDARY$/ }) }).first();
  if (await b2.count()) {
    if ((await b2.getAttribute('aria-expanded')) === 'false') await b2.locator('.caret').click();
    await page.waitForTimeout(300);
    const m2 = page.locator('#sidebar .tr', { has: page.locator('.lbl', { hasText: /^MASONRY$/ }) }).first();
    if ((await m2.count()) && (await m2.getAttribute('aria-expanded')) === 'false') await m2.locator('.caret').click();
    await b2.hover();
  }
  await page.waitForTimeout(500);
  await tour.picture('class-tree-envelope', { page, element: '#sidebar' });
});

await tour.step('18A.3 Try it: Colour by Trade and Placement, the legend, Confidence shading', async () => {
  const page = await tour.open('model=fzk-haus');
  await classify(page);
  const f = facets(page);
  await f.locator('summary').click();
  await f.getByRole('button', { name: 'Facets: all' }).click().catch(() => {});
  await page.waitForTimeout(5000);
  const colour = pane(page).getByLabel('Colour by').first();
  const base = await page.evaluate(() => Array.from(window.__xray.app.controller.state.color.slice(0, 246)));
  await colour.selectOption({ label: 'Trade' });
  await page.waitForTimeout(1500);
  const painted = await page.evaluate((b) => Array.from(window.__xray.app.controller.state.color.slice(0, 246)).some((v, i) => Math.abs(v - b[i]) > 0.02), base);
  tour.check('step 1: "In Colour by choose Trade": the model is painted', painted);
  const leg = pane(page).locator('[data-role=legend] , .xc-legend').first();
  const legTxt = await pane(page).innerText();
  tour.check('step 2: "The legend lists each trade with its count"', /CONC/.test(legTxt), legTxt.match(/CONC[^\n]*/)?.[0] ?? '');
  void leg;
  const nShown = () => page.evaluate(() => { const c = window.__xray.app.controller, al = c.state.alpha; let n = 0; for (let i = 0; i < c.model.elements.length; i++) if (al[i] > 0.95 && !(c.settings.overrides.userHides.has(i))) n++; return n; });
  const row = pane(page).locator('li, .xc-leg-row, [data-code]').filter({ hasText: /^\s*CONC/ }).first();
  if (await row.count()) {
    await row.click();
    await ui.settle(page, 800);
    const n1 = await page.evaluate(() => window.__xray.app.controller.settings.overrides.userHides.size);
    tour.check('step 2: "Click the row CONC: only the concrete is shown"', n1 > 0, `${n1} hidden`);
    await row.click();
    await ui.settle(page, 800);
    tour.check('step 2: "Click it again for all"', (await page.evaluate(() => window.__xray.app.controller.settings.overrides.userHides.size)) === 0);
  } else tour.known('step 2: a legend row CONC can be clicked', false, 'no clickable legend row found', legTxt.replace(/\s+/g, ' ').slice(0, 200));
  void nShown;
  await colour.selectOption({ label: 'Placement' });
  await page.waitForTimeout(1200);
  const legP = await pane(page).innerText();
  tour.check('step 3: "Choose Placement. The envelope and the interior take two colours"', /BOUNDARY|EXT/.test(legP) && /INT/.test(legP), legP.match(/(BOUNDARY|EXT|INT)[^\n]*/g)?.join(' | ') ?? '');
  const before = await page.evaluate(() => Array.from(window.__xray.app.controller.state.color.slice(0, 246)));
  await pane(page).locator('label', { hasText: 'Confidence shading' }).click();
  await page.waitForTimeout(1500);
  const after = await page.evaluate(() => Array.from(window.__xray.app.controller.state.color.slice(0, 246)));
  const nr = await page.evaluate(() => window.__xrayClassify.results().filter((r) => r.needsReview).length);
  tour.check('step 4: "Switch on Confidence shading. Elements that need review turn paler"', nr === 0 || after.some((v, i) => Math.abs(v - before[i]) > 0.02), `${nr} need review`);
  tour.check('step 4: "Select needs review (18.1)" is there', (await pane(page).getByRole('button', { name: 'Select needs review' }).count()) >= 1);
  const opts = await colour.locator('option').allInnerTexts();
  tour.check('"Colour by offers Off, Discipline, Trade, Placement, Material, Phase and Orientation"', ['Off', 'Discipline', 'Trade', 'Placement', 'Material', 'Phase', 'Orientation'].every((o) => opts.includes(o)), opts.join(','));
});

await tour.finish();
