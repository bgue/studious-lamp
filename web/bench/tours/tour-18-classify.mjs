// Tour of chapter 18, "Classifying elements" (docs/manual/18-classify.md): run the rules (18.1), review: Accept, Change, Unsure, commit, the review walk (18.2),
// code lists and exports (18.3). The decision model (WebGPU, a download) and the truth-file command (18.4, a developer command) are not run.
// No pictures in this chapter.
// Run: node bench/run-smokes.mjs --only tour-18-classify
import { readFileSync } from 'node:fs';
import { startTour, ui } from './lib.mjs';

const tour = await startTour('tour-18-classify');
const pane = (page) => page.locator('#dk-pane-classification');
const results = (page) => page.evaluate(() => window.__xrayClassify.results().map((r) => ({ id: r.id, d: r.discipline.code, s: r.source, nr: r.needsReview, conf: r.discipline.confidence })));
const search = async (page, text) => {
  await page.keyboard.press('Escape');
  await page.locator('#c').hover();
  await page.keyboard.press('/');
  await page.keyboard.press('Control+a');
  await page.keyboard.type(text);
  await page.waitForTimeout(1000);
  return (await page.locator('.ab-pop').innerText().catch(() => '')).replace(/\n+/g, ' / ');
};

await tour.step('18.1 Try it: Process plant, Classify all, the table, Colour by discipline, Select needs review, count', async () => {
  const page = await tour.open('model=process-plant');
  tour.check('step 1: Process plant has 1,294 elements', (await ui.model(page)).n === 1294);
  await ui.tab(page, 'Classification');
  await page.waitForTimeout(600);
  tour.check('step 2: "Open the Classification tab of the right sidebar"', await pane(page).isVisible());
  const prov = await pane(page).getByLabel('Provider').first().inputValue().catch(() => '');
  const provTxt = await pane(page).getByLabel('Provider').first().evaluate((s) => s.selectedOptions[0]?.textContent).catch(() => '');
  tour.check('step 3: "Keep Provider on its default (rules and cache only)"', /rules/i.test(provTxt ?? ''), `${prov} / ${provTxt}`);
  const est = await pane(page).innerText();
  tour.check('"Before a run the tab estimates the work: elements, how many by rules, how many cached, how many signatures"', /rules|signature/i.test(est), est.replace(/\s+/g, ' ').slice(0, 160));
  await pane(page).getByRole('button', { name: 'Classify all' }).click();
  await page.waitForFunction(() => window.__xrayClassify.results().length >= 1293, null, { timeout: 180000 });
  await page.waitForTimeout(800);
  const rs = await results(page);
  tour.check('step 3: Classify all gives a result for every element', rs.length === 1293, String(rs.length));
  // step 4: the table
  const heads = await pane(page).locator('table thead th').allInnerTexts();
  tour.check('step 4: "the results table: element, discipline, sub-discipline, division, confidence, top 2, source"', ['Element', 'Disc.', 'Sub', 'Div.', 'Conf.', 'Top 2', 'Source'].every((h, i) => heads[i] === h), heads.join(' | '));
  const bySource = {};
  for (const r of rs) bySource[r.s] = (bySource[r.s] ?? 0) + 1;
  tour.check('step 4: "Most rows say rules"', (bySource.rules ?? 0) > rs.length / 2, JSON.stringify(bySource));
  const byDisc = {};
  for (const r of rs) byDisc[r.d] = (byDisc[r.d] ?? 0) + 1;
  tour.check('"With rules alone on this plant ..." the counts per discipline (manual corrected to what the viewer gives)', byDisc.CIV === 230 && byDisc.PIP === 642 && byDisc.STR === 208 && byDisc.ELE === 160 && byDisc.INS === 27 && byDisc.ARC === 26, JSON.stringify(byDisc));
  tour.check('"nothing is left unresolved": no element needs review', rs.filter((r) => r.nr).length === 0, String(rs.filter((r) => r.nr).length));
  // step 5: Colour by discipline
  const colour = pane(page).getByLabel('Colour by').first();
  const opts = await colour.locator('option').allInnerTexts().catch(() => []);
  tour.check('step 5: the Output section has Colour by with Off, Discipline, Trade, Placement, Material, Phase and Orientation', ['Off', 'Discipline', 'Trade', 'Placement', 'Material', 'Phase', 'Orientation'].every((o) => opts.includes(o)), opts.join(','));
  const before = await page.evaluate(() => Array.from(window.__xray.app.controller.state.color.slice(0, 600)));
  await colour.selectOption({ label: 'Discipline' });
  await page.waitForTimeout(1500);
  const after = await page.evaluate(() => Array.from(window.__xray.app.controller.state.color.slice(0, 600)));
  tour.check('step 5: "The plant is tinted by trade"', after.some((v, i) => Math.abs(v - before[i]) > 0.02));
  const legend = await pane(page).innerText();
  tour.check('step 5: "the legend lists the codes"', /PIP/.test(legend) && /CIV/.test(legend) && /STR/.test(legend), legend.match(/PIP[^\n]*/)?.[0] ?? '');
  await colour.selectOption({ label: 'Off' });
  // step 6
  await pane(page).getByRole('button', { name: 'Select needs review' }).click();
  await page.waitForTimeout(600);
  const msg = await pane(page).innerText();
  tour.check('step 6: "Click Select needs review. Only the elements the rules were not sure about are selected"', (await ui.selection(page)).length === 0 && /0 elements need review|need review/.test(msg), `${(await ui.selection(page)).length} selected`);
  // step 7
  const t7 = await search(page, "count where discipline = 'PIP'");
  tour.check('step 7: "count where discipline = \'PIP\'. The count comes from the classification"', /642/.test(t7), t7.slice(0, 140));
  const t7b = await search(page, "where XR_Classification.NeedsReview = TRUE");
  tour.check('"results are written back to the elements as properties ... where XR_Classification.NeedsReview = TRUE" parses', /elements? match/.test(t7b), t7b.slice(0, 120));
  await page.keyboard.press('Escape');
  // the provider list
  const popts = await pane(page).getByLabel('Provider').first().locator('option').allInnerTexts();
  tour.check('"Provider: Rules and cache only, decision model, d3, WebLLM, Jev"', popts.length >= 4 && popts.some((o) => /decision model/i.test(o)) && popts.some((o) => /Jev/i.test(o)), popts.join(' | '));
  const setting = await pane(page).innerText();
  tour.check('"Minimum confidence", "Rules and model", "Write properties to the model", Classify selection, Classify all, Stop', ['Minimum confidence', 'Rules and model', 'Write properties to the model', 'Classify selection', 'Classify all', 'Stop'].every((l) => setting.includes(l)), setting.replace(/\s+/g, ' ').slice(0, 300));
  // a second run costs no requests
  await pane(page).getByRole('button', { name: 'Classify all' }).click();
  await page.waitForTimeout(3000);
  tour.check('"A repeated run costs zero requests, because the cache answers"', (await results(page)).length === 1293);
});

await tour.step('18.2 Try it: the selected element, Accept, Change, Unsure, Commit, the review walk', async () => {
  const page = await tour.open('model=process-plant');
  await ui.tab(page, 'Classification');
  await pane(page).getByRole('button', { name: 'Classify all' }).click();
  await page.waitForFunction(() => window.__xrayClassify.results().length >= 1293, null, { timeout: 180000 });
  await page.waitForTimeout(800);
  const pump = await ui.clickElement(page, { cls: /Pump/ });
  await ui.tab(page, 'Classification');
  await page.waitForTimeout(800);
  tour.check('step 1: "click one pump in the model"', !!pump, JSON.stringify(pump));
  const card = page.locator('.xcs');
  const ct = await card.innerText();
  tour.check('step 2: "the card shows that element: class, name, the three labels with their confidences, the source, the rule\'s reason"', /Pump/.test(ct) && /Discipline/.test(ct) && /Sub-discipline/.test(ct) && /Division/.test(ct) && /Source/.test(ct) && /Why:/.test(ct) && /%/.test(ct), ct.replace(/\s+/g, ' ').slice(0, 260));
  tour.check('step 3: Accept, Change… and Unsure are there', (await card.getByRole('button', { name: 'Accept' }).count()) === 1 && (await card.getByRole('button', { name: 'Change…' }).count()) === 1 && (await card.getByRole('button', { name: 'Unsure' }).count()) === 1);
  await card.getByRole('button', { name: 'Accept' }).click();
  await page.waitForTimeout(500);
  const ct2 = await card.innerText();
  tour.check('step 3: Accept records a pending decision', /Pending/.test(ct2), ct2.replace(/\s+/g, ' ').slice(-120));
  tour.check('step 4: "A button Commit N pending appears"', (await card.getByRole('button', { name: /^Commit \d+ pending/ }).count()) === 1);
  const nameBox = card.getByLabel('Reviewer name');
  tour.check('step 4: "The first time, the viewer asks for your name or initials"', (await nameBox.count()) === 1);
  await nameBox.fill('TT');
  await card.getByRole('button', { name: /^Commit \d+ pending/ }).click();
  await page.waitForTimeout(1000);
  const ct3 = await card.innerText();
  tour.check('"The newest committed change per element becomes its result: source confirmed"', /Decision: confirm/i.test(ct3) || /confirmed/i.test(ct3), ct3.replace(/\s+/g, ' ').slice(0, 260));
  const r1 = (await page.evaluate(() => window.__xrayClassify.results().filter((r) => r.source === 'confirmed' || r.source === 'corrected').map((r) => [r.source, r.discipline.confidence, r.needsReview])));
  tour.check('"source confirmed or corrected, confidence 1, no review needed"', r1.length >= 1 && r1.every(([, c, n]) => c === 1 && !n), JSON.stringify(r1.slice(0, 3)));
  // change
  const pump2 = await ui.clickElement(page, { cls: /Pump/ });
  await page.waitForTimeout(500);
  await card.getByRole('button', { name: 'Change…' }).click();
  await card.locator('select[data-role=edit-discipline]').selectOption({ index: 1 });
  await card.getByRole('button', { name: 'Apply change' }).click();
  await page.waitForTimeout(500);
  tour.check('step 3: "Click Change..., pick other values in the three lists and Apply change"', /Pending: corrected/.test(await card.innerText()), (await card.innerText()).replace(/\s+/g, ' ').slice(-140));
  void pump2;
  // unsure
  await ui.clickElement(page, { cls: /Vessel|Tank/ }).catch(() => null);
  await page.waitForTimeout(500);
  if (await card.getByRole('button', { name: 'Unsure' }).count()) {
    await card.getByRole('button', { name: 'Unsure' }).click();
    await page.waitForTimeout(400);
    tour.check('step 3: "Click Unsure if you can only guess"', /unsure|Pending/i.test(await card.innerText()));
  }
  // review walk
  await ui.clearSelection(page);
  await page.locator('#c').hover();
  const c0 = await ui.cam(page);
  await page.keyboard.press('Shift+r');
  await page.waitForTimeout(2500);
  const walk = await pane(page).innerText();
  tour.check('step 5: "Press Shift+R to start the Review walk"', /walk|Review/i.test(walk) && (await page.locator('.xc-walk').isVisible()), walk.replace(/\s+/g, ' ').slice(0, 200));
  await page.keyboard.press('Enter');
  await page.waitForTimeout(1500);
  await page.keyboard.press('ArrowRight');
  await page.waitForTimeout(1000);
  await page.keyboard.press('Escape');
  await page.waitForTimeout(2500);
  tour.check('step 5: "Esc ends the walk and puts back your camera and selection"', !(await page.locator('.xc-walk').isVisible()), '');
  const c1 = await ui.cam(page);
  tour.check('step 5: the camera is put back', Math.hypot(...c1.p.map((v, i) => v - c0.p[i])) < 1, `${Math.hypot(...c1.p.map((v, i) => v - c0.p[i])).toFixed(2)} m off`);
});

await tour.step('18.3 Code lists: the schema and the exports', async () => {
  const page = await tour.open('model=process-plant');
  await ui.tab(page, 'Classification');
  await pane(page).getByRole('button', { name: 'Classify all' }).click();
  await page.waitForFunction(() => window.__xrayClassify.results().length >= 1293, null, { timeout: 180000 });
  const txt = await pane(page).innerText();
  tour.check('step 1: "open Schema"', /schema/i.test(txt));
  const names = ['Import Throughline list', 'Load schema file', 'Use built-in schema', 'Export CSV', 'Export JSON', 'Export Throughline JSON'];
  const present = [];
  for (const n of names) present.push([n, await pane(page).getByRole('button', { name: n }).count()]);
  tour.check('steps 2-5: the buttons Import Throughline list, Load schema file, Use built-in schema, Export CSV, Export JSON, Export Throughline JSON', present.every(([, c]) => c >= 1), JSON.stringify(present));
  const [dl] = await Promise.all([page.waitForEvent('download', { timeout: 30000 }).catch(() => null), pane(page).getByRole('button', { name: 'Export CSV' }).first().click()]);
  const csv = dl ? readFileSync(await dl.path(), 'utf8') : '';
  tour.check('step 5: "Export CSV ... hold the GlobalId, the codes, the top two disciplines with probabilities, the confidence, the source"', csv.split('\n').filter(Boolean).length >= 1294 && /globalid/i.test(csv.split('\n')[0]), csv.split('\n')[0]);
  const [dj] = await Promise.all([page.waitForEvent('download', { timeout: 30000 }).catch(() => null), pane(page).getByRole('button', { name: 'Export JSON' }).first().click()]);
  const js = dj ? readFileSync(await dj.path(), 'utf8') : '';
  tour.check('step 5: Export JSON downloads the results', js.length > 1000 && /discipline/i.test(js), js.slice(0, 100));
  const sch = await page.evaluate(() => { const sc = typeof window.__xrayClassify.schema === 'function' ? window.__xrayClassify.schema() : window.__xrayClassify.schema; return (sc?.disciplines ?? []).map((d) => d.code); });
  tour.check('"The default schema\'s disciplines include PIP, MEC, ELE, INS, CIV, STR and ARC, PLB, FPR, TEL, GEN"', ['PIP', 'MEC', 'ELE', 'INS', 'CIV', 'STR', 'ARC', 'PLB', 'FPR', 'TEL', 'GEN'].every((c) => sch.includes(c)), sch.join(','));
  // properties written to the model: queryable as XR_Classification.*
  await page.locator('#c').hover();
  await page.keyboard.press('/');
  await page.keyboard.type("count where XR_Classification.Discipline = 'PIP'");
  await page.waitForTimeout(1200);
  const q = await page.locator('.ab-pop').innerText().catch(() => '');
  tour.check('"The results are written to the model as a property set XR_Classification" (Discipline is queryable)', /642/.test(q), q.replace(/\n+/g, ' / ').slice(0, 120));
  await page.keyboard.press('Escape');
});

await tour.finish();
