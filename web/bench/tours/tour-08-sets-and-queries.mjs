// Tour of chapter 8, "Selection sets and the query language" (docs/manual/08-sets-and-queries.md): static sets (8.1), a criteria set and the
// query language (8.2), export and import (8.3). No pictures in this chapter.
// Run: node bench/run-smokes.mjs --only tour-08-sets-and-queries
import { readFileSync } from 'node:fs';
import { startTour, ui } from './lib.mjs';

const tour = await startTour('tour-08-sets-and-queries');
const pop = (page) => page.locator('.ab-pop');
/** Type into the search bar and return the text of its list, one line per row. */
const search = async (page, text) => {
  await page.keyboard.press('Escape');
  await page.locator('#c').hover();
  await page.keyboard.press('/');
  await page.keyboard.press('Control+a');
  await page.keyboard.type(text);
  await page.waitForTimeout(900);
  return (await pop(page).innerText().catch(() => '')).replace(/\n+/g, ' / ');
};
const setCount = (page) => page.locator('#sidebar .set-row').count();
const countOf = (t) => { const m = t.match(/([\d,]+) elements? match/); return m ? Number(m[1].replace(/,/g, '')) : null; };
const setRow = (page, name) => page.locator('#sidebar .set-row', { has: page.locator('.set-name', { hasText: new RegExp(`^${name}$`) }) });
const menuItems = (page) => page.locator('.xm-menu [role=menuitem]').allInnerTexts();
const openMenu = async (page, name) => { await setRow(page, name).locator('[data-act=menu]').click(); await page.locator('.xm-menu').waitFor(); };
const pickMenu = async (page, label) => { await page.locator('.xm-menu [role=menuitem]', { hasText: label }).first().click(); await page.waitForTimeout(400); };

await tour.step('8.1 Try it: save the selection as a static set', async () => {
  const page = await tour.open('model=fzk-haus');
  const base = await (async () => { await ui.tab(page, 'Sets'); return setCount(page); })();
  tour.check('"A new model starts with the sample sets of FZK-Haus": Rafters and Ground floor walls', base === 2 && (await setRow(page, 'Rafters').count()) === 1 && (await setRow(page, 'Ground floor walls').count()) === 1, String(base));
  const w = await ui.clickElement(page, { cls: /Wall/ });
  await ui.waitStill(page, 8000);
  const d = await ui.clickElement(page, { cls: 'IfcWindow' }, { tree: false });
  tour.check('step 2: "Select a few elements: click one, then Shift+click others"', !!w && !!d);
  // select by tree: a robust way to get several elements
  await ui.tab(page, 'Model');
  await page.locator('#sidebar .tr', { has: page.locator('.lbl', { hasText: /^IfcWallStandardCase$/ }) }).first().click();
  await ui.settle(page, 400);
  const nSel = (await ui.selection(page)).length;
  await ui.tab(page, 'Sets');
  await page.getByLabel('New set name').fill('Test walls');
  await page.getByRole('button', { name: 'Save selection as…' }).click();
  await page.waitForTimeout(400);
  const row = setRow(page, 'Test walls');
  await page.waitForFunction(() => [...document.querySelectorAll('#sidebar .set-row')].some((r) => /Test walls/.test(r.textContent) && /\d/.test(r.querySelector('.cnt')?.textContent ?? '')), null, { timeout: 8000 }).catch(() => {});
  tour.check('step 3-4: "A new line appears: the name, a count and two small buttons, + and ⋯"', (await row.count()) === 1 && new RegExp(`Test walls\\s+${nSel}\\b`).test((await row.innerText()).replace(/\n/g, ' ')) && nSel === 9 && (await row.locator('[data-act=add]').count()) === 1 && (await row.locator('[data-act=menu]').count()) === 1, `nSel ${nSel}, text ${(await row.innerText().catch(() => '-')).replace(/\n/g, ' ')}, rows ${await row.count()}, add ${await row.locator('[data-act=add]').count()}, menu ${await row.locator('[data-act=menu]').count()}`);
  await page.locator('#c').hover();
  await ui.clearSelection(page);
  tour.check('step 5: Escape clears the selection', (await ui.selection(page)).length === 0);
  await ui.tab(page, 'Sets');
  const c0 = await ui.cam(page);
  await row.locator('.set-name').click();
  await ui.waitMoved(page, c0, 25000).catch(() => {});
  tour.check('step 5: "Click the name of the set. The elements are selected again"', (await ui.selection(page)).length === nSel, String((await ui.selection(page)).length));
  const c1 = await ui.cam(page);
  tour.known('step 5: "and the camera frames them"', Math.hypot(...c1.p.map((v, i) => v - c0.p[i])) > 0.05, 'clicking a set name selected the elements but the camera did not move within 25 s (the Home view was the start; 9 ground floor walls)', `moved ${Math.hypot(...c1.p.map((v, i) => v - c0.p[i])).toFixed(2)} m`);
  await ui.clearSelection(page);
  await ui.tab(page, 'Sets');
  await row.locator('[data-act=add]').click();
  await ui.settle(page, 300);
  tour.check('step 5: "The + button does the same" (adds the set to the selection)', (await ui.selection(page)).length === nSel);
  await openMenu(page, 'Test walls');
  const items = await menuItems(page);
  tour.check('step 6: "For a static set you see Update from selection, Rename, Duplicate and Delete"', ['Update from selection', 'Rename', 'Duplicate', 'Delete'].every((l) => items.includes(l)) && items.length === 4, items.join(' | '));
  await pickMenu(page, 'Duplicate');
  tour.check('Duplicate makes a copy', (await setCount(page)) === base + 2, await page.locator('#sidebar .sets-list').innerText());
  await openMenu(page, 'Test walls');
  await page.locator('.xm-menu [role=menuitem]', { hasText: 'Delete' }).first().click();
  tour.check('step 6: "Delete asks you to click twice" (the first click does not delete)', (await setCount(page)) === base + 2 && (await page.locator('.xm-menu').count()) >= 1);
  await page.locator('.xm-menu [role=menuitem]', { hasText: /click again|Delete/i }).first().click();
  await page.waitForTimeout(400);
  tour.check('step 6: the second click deletes', (await setCount(page)) === base + 1);
  // filter
  await page.getByPlaceholder('Filter sets').fill('Test walls');
  await page.waitForTimeout(300);
  const fi = await page.locator('.sets-filter-info').innerText();
  tour.check('"The Filter sets box shows the sets whose name or query contains your text"', /^\d+ of \d+$/.test(fi) && fi.startsWith('1 of'), fi);
});

await tour.step('8.2 Try it: a criteria set (External walls)', async () => {
  const page = await tour.open('model=fzk-haus');
  await ui.tab(page, 'Sets');
  await page.getByRole('button', { name: 'New criteria set' }).click();
  const form = page.getByRole('form', { name: 'Criteria set editor' });
  tour.check('step 1: "A small editor opens"', await form.isVisible());
  await page.getByLabel('Criteria set name').fill('External walls');
  await page.getByLabel('Condition 1 field').fill('class');
  await page.getByLabel('Condition 1 operator').selectOption('=');
  await page.getByLabel('Condition 1 value').fill('IfcWallStandardCase');
  await page.waitForTimeout(500);
  const q = await form.locator('textarea').inputValue();
  tour.check('step 4: "the Query box shows the text the rows write" (class = \'IfcWallStandardCase\')', /^class = 'IfcWallStandardCase'$/.test(q), q);
  const st = await form.locator('.ce-status').innerText();
  tour.check('step 5: "the live line says n matches of N elements"', /^13 matches of 82 elements/.test(st), st);
  const opts = await page.locator('datalist option').evaluateAll((o) => o.map((x) => x.getAttribute('value')));
  tour.check('step 3: "The value box suggests the values the model really has"', opts.includes('IfcWallStandardCase') && opts.includes('IfcWindow'), opts.slice(0, 8).join(','));
  await page.getByRole('button', { name: '+ Condition' }).click();
  tour.check('step 4: with two conditions the "Match all / any" list shows', await page.getByLabel('Combine the conditions with').isVisible());
  await page.getByRole('button', { name: 'Remove condition 2' }).click();
  // an error
  await form.locator('textarea').fill("class = 'IfcWall' AND (storey = 'x'");
  await page.waitForTimeout(400);
  const err = await form.locator('.ce-status').innerText();
  tour.check('step 5: "If you made a mistake it shows the error and puts a caret under the place"', /Expected "\)" to close the "\(" at character \d+/.test(err) && /\^/.test(err), err.replace(/\n/g, ' / '));
  await form.locator('textarea').fill("class = 'IfcWallStandardCase'");
  await page.waitForTimeout(400);
  const c0 = await ui.cam(page);
  await page.getByRole('button', { name: 'Preview' }).click();
  await ui.waitMoved(page, c0).catch(() => {});
  tour.check('step 6: "Press Preview. The matches are selected and framed, nothing is saved yet"', (await ui.selection(page)).length === 13 && (await page.locator('#sidebar .set-row').count()) === 2, `${(await ui.selection(page)).length} selected`);
  await page.getByRole('button', { name: 'Save set', exact: true }).click();
  await page.waitForTimeout(500);
  const row = setRow(page, 'External walls');
  tour.check('step 7: "The set appears in the list with a funnel icon"', (await row.count()) === 1 && (await row.locator('.set-badge').count()) === 1, await page.locator('#sidebar .sets-list').innerText());
  await openMenu(page, 'External walls');
  const items = await menuItems(page);
  tour.check('step 8: "A criteria set has Re-evaluate now and Edit criteria… instead of Update from selection"', items.includes('Re-evaluate now') && items.includes('Edit criteria…') && !items.includes('Update from selection'), items.join(' | '));
  await page.keyboard.press('Escape');
  // Ctrl+Enter saves
  await page.getByRole('button', { name: 'New criteria set' }).click();
  await page.getByLabel('Criteria set name').fill('Doors');
  await form.locator('textarea').fill("class = 'IfcDoor'");
  await page.waitForTimeout(400);
  await form.locator('textarea').press('Control+Enter');
  await page.waitForTimeout(500);
  tour.check('step 8: "Ctrl+Enter in the Query box also saves"', (await setRow(page, 'Doors').count()) === 1);
  // the criteria set follows the model: its count stays 13 after a reload of the model is covered by 8.3
});

await tour.step('8.2 The query language: shapes, comparisons, columns, NULL, errors', async () => {
  const page = await tour.open('model=fzk-haus');
  const q = async (text) => countOf(await search(page, `where ${text}`));
  const all = (await ui.model(page)).n;
  const walls = await q("class = 'IfcWallStandardCase'");
  tour.check('"class = \'IfcWall\'" style: a plain equality finds the 13 walls', walls === 13, String(walls));
  tour.check('"Keywords ignore case: and, AND and And are the same"', (await q("class = 'IfcWallStandardCase' and storey = 'Erdgeschoss'")) === (await q("class = 'IfcWallStandardCase' AND storey = 'Erdgeschoss'")) && (await q("class = 'IfcWallStandardCase' And storey = 'Erdgeschoss'")) === 9);
  tour.check('"Text comparison ignores case: class = \'ifcwallstandardcase\'"', (await q("class = 'ifcwallstandardcase'")) === 13);
  const or = await q("class = 'IfcWindow' OR class = 'IfcDoor'");
  tour.check('OR: windows or doors', or === 11 + 5, String(or));
  tour.check('NOT: NOT class = \'IfcWindow\'', (await q("NOT class = 'IfcWindow'")) === all - 11);
  const noBr = await q("class = 'IfcWindow' OR class = 'IfcDoor' AND storey = 'Dachgeschoss'");
  const br = await q("(class = 'IfcWindow' OR class = 'IfcDoor') AND storey = 'Dachgeschoss'");
  tour.check('"AND binds tighter than OR; use brackets": without brackets every window plus the doors upstairs', noBr === 11 && br === 2, `${noBr} vs ${br}`);
  tour.check('"!= or <>": not equal', (await q("class != 'IfcWindow'")) === all - 11 && (await q("class <> 'IfcWindow'")) === all - 11);
  tour.check('"IN (\'a\', \'b\')" is a short way to write several ORs', (await q("class IN ('IfcWindow', 'IfcDoor')")) === 16 && (await q("class NOT IN ('IfcWindow', 'IfcDoor')")) === all - 16);
  tour.check('"LIKE must match the whole text": name LIKE \'Haustuer\' finds one, \'Haus\' none, \'%tuer%\' the doors', (await q("name LIKE 'Haustuer'")) === 1 && (await q("name LIKE 'Haus'")) === 0 && (await q("name LIKE '%tuer%'")) >= 5);
  tour.check('"_ stands for exactly one character"', (await q("name LIKE 'Haustue_'")) === 1);
  tour.check('"NOT LIKE"', (await q("class NOT LIKE 'IfcW%'")) === all - 24);
  const between = await q('sizeY BETWEEN 2.4 AND 3.2');
  const manual = await page.evaluate(() => window.__xray.app.controller.model.elements.filter((e) => { const h = e.bounds[4] - e.bounds[1]; return h >= 2.4 && h <= 3.2; }).length);
  tour.check('"BETWEEN a AND b: both ends included" (sizeY is the height of the box)', between === manual && between > 0, `${between} vs ${manual}`);
  const lt = await q('sizeY < 0.5');
  tour.check('"< <= > >=" compare numbers', lt !== null && lt < all, String(lt));
  tour.check('"A column on its own is a test for TRUE"', (await q('"Pset_WallCommon.IsExternal"')) === (await q('"Pset_WallCommon.IsExternal" = TRUE')));
  const ext = await q('"Pset_WallCommon.IsExternal" = TRUE');
  const notExt = await q('"Pset_WallCommon.IsExternal" != TRUE');
  const notExtN = await q('"Pset_WallCommon.IsExternal" != TRUE OR "Pset_WallCommon.IsExternal" IS NULL');
  tour.check('"!= TRUE does not find walls that have no such property; add OR ... IS NULL to include them"', notExt !== null && notExtN !== null && notExtN === all - ext && notExt < notExtN, `ext ${ext}, != TRUE ${notExt}, with IS NULL ${notExtN}, all ${all}`);
  tour.check('"x = NULL never matches. Use IS NULL"', (await q('storey = NULL')) === 0 && (await q('storey IS NULL')) >= 0 && (await q('storey IS NOT NULL')) + (await q('storey IS NULL')) === all);
  tour.check('"A number and a text that looks like a number compare as numbers"', (await q("'0.24' = 0.24")) === all);
  tour.check('core columns ignore case: CLASS and ifcClass', (await q("CLASS = 'IfcDoor'")) === 5 && (await q("ifcClass = 'IfcDoor'")) === 5);
  tour.check('"globalId, id" and "storeyElevation (also elevation)" are columns', (await q('storeyElevation >= 0')) > 0 && (await q('elevation >= 0')) > 0 && (await q('id = 0')) === 1);
  tour.check('"volume" is the volume of the bounding box: columns can be compared (sizeX > sizeZ)', (await q('sizeX > sizeZ')) > 0);
  // worked examples
  const ex1 = await q("class IN ('IfcWall', 'IfcWallStandardCase') AND \"Pset_WallCommon.IsExternal\"");
  const ex2 = await q('"BaseQuantities.NetVolume" > 2 AND storey = \'Erdgeschoss\'');
  const ex3 = await q('name LIKE \'Riser%\' OR "Attr.ObjectType" LIKE \'%duct%\'');
  const ex4 = await q("sizeY BETWEEN 2.4 AND 3.2 AND NOT class = 'IfcColumn'");
  const ex5 = await q("\"Pset_WallCommon.FireRating\" IS NULL AND class LIKE 'IfcWall%'");
  tour.check('"Worked examples": all five parse and give a count', [ex1, ex2, ex3, ex4, ex5].every((n) => n !== null), [ex1, ex2, ex3, ex4, ex5].join(', '));
  tour.check('"The last one is a quality check: every wall that has no fire rating"', ex5 > 0 && ex5 <= 13, String(ex5));
  // errors
  const e1 = await search(page, "where (class = 'IfcWall'");
  tour.check('"Errors: Expected \\")\\" to close the \\"(\\" at character N, found the end of the query"', /Expected "\)" to close the "\(" at character \d+, found the end of the query/.test(e1), e1.slice(0, 160));
  const e2 = await search(page, 'where and = 1');
  tour.check('"If you use a keyword as a column name the message says to put it in double quotes"', /double quotes/i.test(e2), e2.slice(0, 200));
  const e3 = await search(page, 'where flavour = 1');
  tour.check('"A column that no element has is not an error: it reads as NULL, and the editor warns you in a note"', /flavour/.test(e3) && /empty|NULL/i.test(e3), e3.slice(0, 200));
  await page.keyboard.press('Escape');
});

await tour.step('8.2 Counting and adding up', async () => {
  const page = await tour.open('model=synth5k');
  const t1 = await search(page, "count where class like 'IfcWall%'");
  tour.check('"count where class like \'IfcWall%\'": 240 walls', /240 walls?/.test(t1), t1.slice(0, 120));
  const t2 = await search(page, "sum length, count where class = 'IfcPipeSegment' by storey");
  tour.check('"sum length, count where ... by storey": the answer has a sum of length and subtotals', /Σ length/.test(t2) && /924/.test(t2), t2.slice(0, 220));
  const t3 = await search(page, "avg length, max length where class = 'IfcBeam'");
  tour.check('"avg length, max length where class = \'IfcBeam\'"', /avg|mean|average/i.test(t3) && /max/i.test(t3), t3.slice(0, 220));
  const t4 = await search(page, 'sum volume by class');
  tour.check('"sum volume by class"', /Σ volume/.test(t4) && /m³/.test(t4), t4.slice(0, 220));
  const t5 = await search(page, "sum of length where class = 'IfcBeam'");
  const t5b = await search(page, "sum(length) where class = 'IfcBeam'");
  tour.check('"sum of length and sum(length) also work"', /Σ length/.test(t5) && /Σ length/.test(t5b), t5.slice(0, 100));
  const t6 = await search(page, 'count and sum volume by level');
  tour.check('"level means storey" (by level)', /Level 0|Level 1/.test(t6), t6.slice(0, 220));
  // Enter selects, Shift+Enter leaves the selection alone
  await search(page, "count where class = 'IfcColumn'");
  await page.keyboard.press('Shift+Enter');
  await ui.settle(page, 300);
  tour.check('"Shift+Enter leaves the selection alone"', (await ui.selection(page)).length === 0);
  await search(page, "count where class = 'IfcColumn'");
  await page.keyboard.press('Enter');
  await ui.settle(page, 500);
  tour.check('"Enter selects the elements and frames them"', (await ui.selection(page)).length === 726, String((await ui.selection(page)).length));
  const t7 = await search(page, "sum netsidearea where class like 'IfcWall%'");
  tour.check('"sum netsidearea where class like \'IfcWall%\'" gives an area or says what is missing', /m²|netsidearea|skipp|no value/i.test(t7), t7.slice(0, 200));
  await page.keyboard.press('Escape');
});

await tour.step('8.2 Right-click to write a query (Properties tab)', async () => {
  const page = await tour.open('model=fzk-haus');
  await ui.clickElement(page, { cls: 'IfcWindow' });
  await ui.tab(page, 'Properties');
  await ui.settle(page, 500);
  const dd = page.locator('#dk-pane-properties dd[data-field=ifcClass]').first();
  await dd.click({ button: 'right' });
  await page.locator('.xm-menu').waitFor({ timeout: 5000 });
  const items = await menuItems(page);
  tour.check('"The menu: Select all with this value, Add to selection all with this value, Copy value, Save as criteria set…"', ['Select all with this value', 'Add to selection all with this value', 'Copy value', 'Save as criteria set…'].every((l) => items.includes(l)), items.join(' | '));
  await pickMenu(page, 'Select all with this value');
  await ui.settle(page, 400);
  tour.check('"Select all with this value" selects every IfcWindow (11)', (await ui.selection(page)).length === 11, String((await ui.selection(page)).length));
  await dd.click({ button: 'right' });
  await pickMenu(page, 'Save as criteria set…');
  await page.waitForTimeout(500);
  const form = page.getByRole('form', { name: 'Criteria set editor' });
  const text = await form.locator('textarea').inputValue().catch(() => '');
  const name = await page.getByLabel('Criteria set name').inputValue().catch(() => '');
  tour.check('"Save as criteria set… opens the criteria editor with the query and a suggested name"', /class = 'IfcWindow'/.test(text) && name.length > 0, `${text} / ${name}`);
  await page.getByRole('button', { name: 'Save set', exact: true }).click();
  await page.waitForTimeout(400);
  const sets = await page.evaluate(() => document.querySelectorAll('#sidebar .set-row').length);
  tour.check('the set is saved', sets === 3, String(sets));
});

await tour.step('8.3 Try it: export and import the sets', async () => {
  const page = await tour.open('model=fzk-haus');
  await ui.tab(page, 'Sets');
  await page.getByRole('button', { name: 'New criteria set' }).click();
  await page.getByLabel('Criteria set name').fill('Windows');
  await page.locator('.ce textarea').fill("class = 'IfcWindow'");
  await page.waitForTimeout(300);
  await page.getByRole('button', { name: 'Save set', exact: true }).click();
  await page.waitForTimeout(400);
  const [dl] = await Promise.all([page.waitForEvent('download', { timeout: 15000 }), page.getByRole('button', { name: 'Export', exact: true }).click()]);
  const path = await dl.path();
  const data = JSON.parse(readFileSync(path, 'utf8'));
  tour.check('step 1: "A JSON file (xray-sets/1) downloads"', /xray-sets\/1/.test(JSON.stringify(data).slice(0, 400)) && JSON.stringify(data).includes('Windows'), JSON.stringify(data).slice(0, 200));
  // delete, then import
  await openMenu(page, 'Windows');
  await page.locator('.xm-menu [role=menuitem]', { hasText: 'Delete' }).click();
  await page.locator('.xm-menu [role=menuitem]', { hasText: /click again|Delete/i }).click();
  await page.waitForTimeout(300);
  tour.check('the set is gone before the import', (await setRow(page, 'Windows').count()) === 0);
  await page.locator('#sidebar .sets input[type=file]').setInputFiles(path);
  await page.waitForTimeout(600);
  tour.check('step 3: "Press Import and choose the file. The sets appear"', (await setRow(page, 'Windows').count()) === 1 && (await setRow(page, 'Windows').locator('.set-badge').count()) === 1, await page.locator('#sidebar .sets-list').innerText());
  await page.locator('#sidebar .sets input[type=file]').setInputFiles(path);
  await page.waitForTimeout(600);
  tour.check('"A set with the same name as one already there replaces it"', (await setRow(page, 'Windows').count()) === 1);
  // a criteria set follows the model: reload the page, the set is there with its count
  await page.reload({ waitUntil: 'commit' });
  await page.waitForFunction(() => window.__xrayReady, null, { timeout: 120000 }).catch(() => {});
  await ui.tab(page, 'Sets');
  await page.waitForTimeout(800);
  tour.check('"Sets are kept per model, in the browser\'s own storage": the set is back after a reload with its count 11', (await setRow(page, 'Windows').count()) === 1 && /Windows\s+11\b/.test((await setRow(page, 'Windows').innerText()).replace(/\n/g, ' ')), await page.locator('#sidebar .sets-list').innerText());
});

await tour.finish();
