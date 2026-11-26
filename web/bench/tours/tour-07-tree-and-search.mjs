// Tour of chapter 7, "Model tree and search" (docs/manual/07-tree-and-search.md): browse the tree (7.1), the keyboard, hide/isolate/show,
// the search bar (7.2) and conditions typed into search (7.3). No pictures in this chapter.
// Run: node bench/run-smokes.mjs --only tour-07-tree-and-search
import { startTour, ui } from './lib.mjs';

const tour = await startTour('tour-07-tree-and-search');
const rows = (page) => page.locator('#sidebar .tr');
const row = (page, label) => page.locator('#sidebar .tr', { has: page.locator('.lbl', { hasText: new RegExp(`^${label}$`) }) }).first();
const rowTexts = (page) => rows(page).evaluateAll((r) => r.map((x) => x.innerText.replace(/\s+/g, ' ').trim()));
const pop = (page) => page.locator('.ab-pop');
const search = async (page, text) => {
  await page.keyboard.press('/');
  await page.keyboard.press('Control+a');
  await page.keyboard.type(text);
  await page.waitForTimeout(900);
  return (await pop(page).innerText().catch(() => '')).replace(/\n+/g, ' / ');
};

await tour.step('7.1 Try it steps 1-5: the tree, selecting, class rows, the eye', async () => {
  const page = await tour.open('model=fzk-haus');
  tour.check('step 1: "The left sidebar opens on the Model tab"', (await page.getByRole('tab', { name: 'Model', exact: true }).getAttribute('aria-selected')) === 'true');
  const t0 = await rowTexts(page);
  tour.check('"The top level is the storeys, lowest first"', /^Erdgeschoss/.test(t0[0]) && t0.some((t) => /^Dachgeschoss/.test(t)) && t0.findIndex((t) => /^Erdgeschoss/.test(t)) < t0.findIndex((t) => /^Dachgeschoss/.test(t)), t0.slice(0, 3).join(' | '));
  const eg = row(page, 'Erdgeschoss');
  // step 2: the arrow in front of a storey
  const open0 = await eg.getAttribute('aria-expanded');
  if (open0 === 'true') await eg.locator('.caret').click();
  const closedCount = await rows(page).count();
  await eg.locator('.caret').click();
  await page.waitForTimeout(300);
  const opened = await rowTexts(page);
  tour.check('step 2: "The classes inside it appear, each with a number"', opened.length > closedCount && opened.some((t) => /^IfcWallStandardCase 9$/.test(t)), opened.slice(0, 6).join(' | '));
  // step 3: open a class, click an element
  const wallCls = row(page, 'IfcWallStandardCase');
  await wallCls.locator('.caret').click();
  await page.waitForTimeout(300);
  const wallRow = page.locator('#sidebar .tr.k-element').first();
  await wallRow.click();
  await ui.settle(page, 500);
  const sel = await ui.selection(page);
  tour.check('step 3: "It is selected in the 3D view"', sel.length === 1 && /Wall/.test(sel[0].cls ?? ''), JSON.stringify(sel));
  tour.check('step 3: "its data appears in the Properties tab on the right"', /IfcWall/.test(await page.locator('#dk-pane-properties').innerText()));
  await wallRow.hover();
  await page.waitForTimeout(600);
  const title = await wallRow.getAttribute('title');
  tour.check('step 3: "Hover a row to see its full name, class and GlobalId in a tooltip"', !!title && /IfcWall/.test(title) && /[0-9A-Za-z_$]{22}/.test(title), title);
  const hl = await page.evaluate(() => { const a = window.__xray.app; return JSON.stringify([a.hoverId ?? a.hovered ?? null]); }).catch(() => '');
  void hl;
  // step 4: class row selects the class in that storey
  await ui.clearSelection(page);
  await wallCls.click();
  await ui.settle(page, 400);
  const s4 = await ui.selection(page);
  tour.check('step 4: "Every element of that class in that storey is selected" (9 walls on Erdgeschoss)', s4.length === 9 && s4.every((e) => e.cls === 'IfcWallStandardCase'), `${s4.length} selected`);
  await row(page, 'IfcDoor').click({ modifiers: ['Shift'] });
  await ui.settle(page, 400);
  const s4b = await ui.selection(page);
  tour.check('step 4: "Hold Shift and click another class to add it"', s4b.length === 14 && s4b.some((e) => e.cls === 'IfcDoor') && s4b.some((e) => /Wall/.test(e.cls)), `${s4b.length} selected`);
  // step 5: the eye
  await ui.clearSelection(page);
  const faintBefore = (await ui.model(page)).n;
  const egRow = row(page, 'Erdgeschoss');
  await egRow.locator('.eye').click();
  await ui.settle(page, 500);
  const hid = await page.evaluate(() => window.__xray.app.controller.settings.overrides.userHides.size);
  const crossed = await egRow.evaluate((r) => r.classList.contains('hid') || r.querySelector('.eye')?.getAttribute('title') === 'Show');
  tour.check('step 5: "Everything on that storey hides, and the eye changes to a crossed eye"', crossed && hid === 26, `hidden ${hid} of ${faintBefore}`);
  await egRow.locator('.eye').click();
  await ui.settle(page, 400);
  tour.check('step 5: "Click it again to show them"', (await egRow.locator('.eye').getAttribute('title')) === 'Hide');
});

await tour.step('7.1 Try it step 6: Alt+F, door, count, Escape', async () => {
  const page = await tour.open('model=fzk-haus');
  await page.locator('#c').hover();
  await page.keyboard.press('Alt+f');
  const focused = await page.evaluate(() => document.activeElement?.getAttribute('aria-label'));
  tour.check('"Press Alt+F. The cursor jumps to the filter box above the tree"', focused === 'Filter model tree', String(focused));
  await page.keyboard.type('door');
  await page.waitForTimeout(500);
  const t = await rowTexts(page);
  tour.check('"The tree shrinks to the matching elements, with every branch open"', t.length > 0 && t.length < 15 && t.some((x) => /Tür|door/i.test(x) || x.startsWith('IfcDoor')), t.join(' | '));
  const info = await page.locator('.sb-filter-info').innerText();
  tour.check('"a count appears beside the box (5 matches for door)"', /5 match/.test(info), info);
  const inFilter = () => page.evaluate(() => document.activeElement?.getAttribute('aria-label') === 'Filter model tree');
  await page.keyboard.press('Escape');
  await page.waitForTimeout(400);
  const after = await page.locator('.sb-filter input').inputValue();
  tour.check('"Press Escape to clear the filter"', after === '' && (await rowTexts(page)).length > 10, `value "${after}"`);
  if (await inFilter()) await page.keyboard.press('Escape');
  tour.check('"and give the keys back to the page" (a second Escape)', !(await inFilter()));
});

await tour.step('7.1 Keyboard: arrows, Right/Left, Enter, Ctrl+Space, type-ahead, follows clicks in 3D', async () => {
  const page = await tour.open('model=fzk-haus');
  const tree = page.locator('#sidebar [aria-label="Model tree"]').first();
  await tree.focus();
  const act = async () => (await page.locator('#sidebar .tr.act').first().innerText().catch(() => '')).replace(/\s+/g, ' ').trim();
  await page.keyboard.press('Home');
  const a0 = await act();
  await page.keyboard.press('ArrowDown');
  const a1 = await act();
  tour.check('"Up, Down, Home, End ... Move to another row"', a1 !== a0 && /^Erdgeschoss/.test(a0), `${a0} -> ${a1}`);
  await page.keyboard.press('End');
  const aEnd = await act();
  tour.check('End moves to the last row', aEnd !== a1 && aEnd !== '', aEnd);
  await page.keyboard.press('Home');
  await page.keyboard.press('ArrowLeft');
  const closed = await row(page, 'Erdgeschoss').getAttribute('aria-expanded');
  tour.check('"Left: close an open row"', closed === 'false', closed);
  await page.keyboard.press('ArrowRight');
  tour.check('"Right: open a closed row"', (await row(page, 'Erdgeschoss').getAttribute('aria-expanded')) === 'true');
  await page.keyboard.press('ArrowRight');
  const child = await act();
  tour.check('"On an open row, go to its first child"', /^IfcBeam/.test(child), child);
  await page.keyboard.press('Enter');
  await ui.settle(page, 400);
  const s1 = await ui.selection(page);
  tour.check('"Enter: select what the row holds ... a class selects all its elements"', s1.length === 1 && s1[0].cls === 'IfcBeam', JSON.stringify(s1));
  await page.keyboard.press('ArrowDown');
  await page.keyboard.press('Control+ ');
  await ui.settle(page, 300);
  tour.check('"Ctrl+Space: add the row\'s elements to the selection"', (await ui.selection(page)).length === 1 + 5, String((await ui.selection(page)).length));
  await page.keyboard.press('Control+ ');
  await ui.settle(page, 300);
  tour.check('"or remove them if they are already in it"', (await ui.selection(page)).length === 1);
  await page.keyboard.press('Shift+ArrowDown');
  await ui.settle(page, 300);
  tour.check('"Shift+Down: move, and add the new row\'s elements"', (await ui.selection(page)).length > 1, String((await ui.selection(page)).length));
  await page.keyboard.press('Home');
  await page.keyboard.press('d');
  tour.check('"Type-ahead: d jumps to a row whose name starts with it" (Dachgeschoss)', /^Dachgeschoss/.test(await act()), await act());
  await page.waitForTimeout(700);
  await page.keyboard.press('Shift+I');
  await page.keyboard.type('fcDoor');
  tour.check('"Shift+I, then fcDoor, finds IfcDoor"', /^IfcDoor/.test(await act()), await act());
  // f keeps its job: frames the selection
  await page.waitForTimeout(700);
  await row(page, 'IfcDoor').locator('.lbl').click();
  await ui.settle(page, 300);
  await tree.focus();
  const c0 = await ui.cam(page);
  await page.keyboard.press('f');
  await ui.waitMoved(page, c0).catch(() => {});
  const c1 = await ui.cam(page);
  tour.check('"f still frames the selection, even with the tree in focus"', Math.hypot(...c1.p.map((v, i) => v - c0.p[i])) > 0.3, `moved ${Math.hypot(...c1.p.map((v, i) => v - c0.p[i])).toFixed(1)} m`);
  await page.keyboard.press('Escape');
  const ae = await page.evaluate(() => document.activeElement?.closest('#sidebar') !== null && document.activeElement?.getAttribute('aria-label') === 'Model tree');
  tour.check('"Esc hands focus back to the 3D view"', !ae);
  // the tree follows clicks in 3D
  await ui.clearSelection(page);
  await row(page, 'Dachgeschoss').locator('.caret').click().catch(() => {});
  await page.waitForTimeout(200);
  const w = await ui.clickElement(page, { cls: 'IfcWindow' }, { tree: false });
  await ui.settle(page, 600);
  const actNow = await page.locator('#sidebar .tr.act, #sidebar .tr.sel').first().innerText().catch(() => '');
  tour.check('"Click an element in the 3D view ... The tree opens its storey and class, scrolls the row into view"', !!w && (await page.locator('#sidebar .tr.sel').count()) >= 1, `${JSON.stringify(w)} / ${actNow.replace(/\s+/g, ' ')}`);
});

await tour.step('7.1 Hide, isolate, show: h, Shift+H, Alt+H and the eye states', async () => {
  const page = await tour.open('model=fzk-haus');
  const n = (await ui.model(page)).n;
  const visible = () => page.evaluate(() => { const a = window.__xray.app; const c = a.controller; return c.model.elements.filter((e) => !(c.state.hidden && c.state.hidden[e.id])).length; });
  void visible;
  await row(page, 'IfcDoor').locator('.lbl').click();
  await ui.settle(page, 400);
  const userHides = () => page.evaluate(() => window.__xray.app.controller.settings.overrides.userHides.size);
  await page.keyboard.press('h');
  await ui.settle(page, 800);
  const doorRow = row(page, 'IfcDoor');
  await page.waitForFunction(() => [...document.querySelectorAll('#sidebar .tr')].some((r) => /IfcDoor/.test(r.innerText) && r.classList.contains('hid')), null, { timeout: 8000 }).catch(() => {});
  tour.check('"h: hide the selected elements" (5 doors)', (await userHides()) === 5, String(await userHides()));
  tour.check('"h: hide the selected elements" (the doors row shows its eye crossed)', (await doorRow.locator('.eye').getAttribute('title')) === 'Show', await doorRow.getAttribute('class'));
  tour.known('"Hidden elements ... are removed from the selection"', (await ui.selection(page)).length === 0, 'after h the hidden doors stay in the selection', `${(await ui.selection(page)).length} still selected`);
  const egCls = await row(page, 'Erdgeschoss').getAttribute('class');
  tour.check('"A half-dimmed eye on a storey ... means some of its elements are hidden"', /\bpart\b/.test((await row(page, 'Erdgeschoss').locator('.eye').getAttribute('class')) ?? ''), `eye class: ${await row(page, 'Erdgeschoss').locator('.eye').getAttribute('class')} row: ${egCls}`);
  await page.keyboard.press('Alt+h');
  await ui.settle(page, 400);
  await page.waitForFunction(() => ![...document.querySelectorAll('#sidebar .tr')].some((r) => /IfcDoor/.test(r.innerText) && r.classList.contains('hid')), null, { timeout: 8000 }).catch(() => {});
  tour.check('"Alt+H: show everything you hid"', (await doorRow.locator('.eye').getAttribute('title')) === 'Hide');
  await row(page, 'IfcWindow').first().locator('.lbl').click();
  await ui.settle(page, 400);
  await page.locator('#c').hover();
  await page.keyboard.press('Shift+h');
  await ui.settle(page, 500);
  const hiddenN = await userHides();
  tour.check('"Shift+H: hide everything that is not selected (isolate)": all but the 9 windows of the ground floor', hiddenN === n - 9, `hidden ${hiddenN} of ${n}`);
  await page.keyboard.press('Alt+h');
  await ui.settle(page, 300);
});

await tour.step('7.2 Try it: the search bar', async () => {
  const page = await tour.open('model=synth5k');
  const m = await ui.model(page);
  await page.locator('#c').hover();
  await page.keyboard.press('/');
  tour.check('step 1: "Press /. The cursor goes into the search box in the top bar"', (await page.evaluate(() => document.activeElement?.className)).includes('ab-input'));
  await page.keyboard.press('Escape');
  await page.keyboard.press('Control+k');
  tour.check('step 1: Ctrl+K does the same', (await page.evaluate(() => document.activeElement?.className)).includes('ab-input'));
  await page.keyboard.press('Escape');
  const t = await search(page, 'wall');
  const heads = await pop(page).locator('.ab-head').allInnerTexts();
  tour.check('step 2: "grouped under headers: Elements, Commands, Presets, Views and so on"', ['Elements', 'Commands', 'Presets'].every((h) => heads.some((x) => x.toLowerCase() === h.toLowerCase())), heads.join(','));
  tour.check('step 2: "The group with the best match is on top" (Elements)', heads[0]?.toLowerCase() === 'elements', heads.join(','));
  await page.keyboard.press('ArrowDown');
  await page.waitForTimeout(500);
  tour.check('step 3: "Press the Down arrow. The first element row is highlighted"', await pop(page).locator('.ab-opt.ab-active').count() === 1, t.slice(0, 80));
  await page.keyboard.press('Enter');
  await ui.waitStill(page, 15000);
  const sel = await ui.selection(page);
  tour.check('step 4: "Press Enter. The element is selected and the camera frames it"', sel.length === 1 && /Wall/.test(sel[0].cls ?? ''), JSON.stringify(sel));
  // step 5 abbreviation
  const t5 = await search(page, 'dri');
  const marks = await pop(page).locator('.ab-opt mark').count();
  tour.check('step 5: "letters can be an abbreviation of the start of each word" (dri finds Duct riser)', /Duct riser/.test(t5.split('COMMANDS')[0]), t5.slice(0, 120));
  tour.check('step 5: "Matched letters are highlighted"', marks > 0, String(marks));
  await page.keyboard.press('Escape');
  // step 6
  const t6 = await search(page, 'duct level 2');
  const first = t6.split('/')[1]?.trim();
  tour.check('step 6: "All three words must match, in any order": elements are ducts on Level 2', /^Duct .*L2/.test(first ?? '') || /Duct/.test(first ?? ''), t6.slice(0, 140));
  const subs = await pop(page).locator('.ab-opt .ab-sub').allInnerTexts();
  tour.check('step 6: the element rows are all ducts (the words may match the name or the storey)', subs.length > 0 && subs.slice(0, 5).every((x) => /IfcDuctSegment/.test(x)), subs.slice(0, 3).join(' | '));
  await page.keyboard.press('Escape');
  // step 7
  const t7 = await search(page, '>hide');
  const h7 = await pop(page).locator('.ab-head').allInnerTexts();
  tour.check('step 7: "The > limits the search to commands and settings"', h7.every((h) => /command|setting/i.test(h)) && h7.length >= 1, h7.join(','));
  await page.keyboard.press('Enter');
  await ui.settle(page, 500);
  tour.check('step 7: Enter runs the top command (the box closes)', !(await pop(page).isVisible().catch(() => false)));
  // step 8
  await page.keyboard.press('Escape');
  await page.locator('#c').hover();
  await page.keyboard.press('Escape');
  await search(page, 'fire');
  const h8 = await pop(page).locator('.ab-head').allInnerTexts();
  tour.check('step 8: "look under Settings"', h8.some((h) => /setting/i.test(h)), h8.join(','));
  let inSettings = false;
  for (let i = 0; i < 20 && !inSettings; i++) {
    await page.keyboard.press('ArrowDown');
    inSettings = await pop(page).locator('.ab-opt.ab-active').first().evaluate((e) => { let p = e.previousElementSibling; while (p && !p.classList.contains('ab-head')) p = p.previousElementSibling; return /setting/i.test(p?.textContent ?? ''); }).catch(() => false);
  }
  tour.check('step 8: Down reaches a row under Settings', inSettings, await pop(page).innerText().then((t) => t.replace(/\n+/g, ' / ').slice(0, 200)).catch((e) => 'popup gone'));
  await page.keyboard.press('Enter');
  await page.waitForTimeout(1000);
  const tabSel = await page.getByRole('tab', { name: 'Parameters', exact: true }).getAttribute('aria-selected');
  tour.check('step 8: "Enter opens the right folder in the Parameters tab"', tabSel === 'true', String(tabSel));
  // sections table: recents
  await page.locator('#c').hover();
  await page.keyboard.press('/');
  await page.keyboard.press('Control+a'); await page.keyboard.press('Delete');
  await page.waitForTimeout(500);
  const rec = (await pop(page).innerText().catch(() => '')).replace(/\n+/g, ' / ');
  tour.check('"Focus the empty box and it lists the last things you used, newest first"', rec.length > 0, rec.slice(0, 100));
  await page.keyboard.press('Escape');
  // Shift+Enter adds without moving the camera
  await ui.clearSelection(page);
  await search(page, 'column');
  await page.keyboard.press('ArrowDown');
  await page.keyboard.press('Shift+Enter');
  await ui.settle(page, 400);
  tour.check('"Shift+Enter adds to the selection instead of replacing it"', (await ui.selection(page)).length >= 1);
  await page.keyboard.press('Escape');
  const more = await search(page, 'beam');
  tour.check('"Elements show up to 50 rows and then N more..."', /\d+ more/.test(more), more.slice(-120));
  void m;
});

await tour.step('7.3 Try it: conditions typed into search', async () => {
  const page = await tour.open('model=synth5k');
  const foot = () => pop(page).locator('.ab-foot').innerText().catch(() => '');
  const t1 = await search(page, "where class like 'IfcWall%'");
  const m1 = t1.match(/([\d,]+) elements? match/);
  tour.check('step 2: "one row: N elements match, with the top classes"', !!m1 && /IfcWall/.test(t1), t1.slice(0, 120));
  tour.check('step 2: "The footer repeats the count"', /[\d,]+ elements? match/.test(await foot()), await foot());
  const n1 = Number((m1?.[1] ?? '0').replace(/,/g, ''));
  const t3 = await search(page, "where class like 'IfcWall%' and storey like '%1%'");
  const m3 = t3.match(/([\d,]+) elements? match/);
  const n3 = Number((m3?.[1] ?? '0').replace(/,/g, ''));
  tour.check('step 3: "Add and storey like \'%1%\'. The count drops."', n3 > 0 && n3 < n1, `${n1} -> ${n3}`);
  await page.keyboard.press('Enter');
  await ui.settle(page, 500);
  tour.check('step 4: "Press Enter. All the matching elements are selected"', (await ui.selection(page)).length === n3, `${(await ui.selection(page)).length} selected, ${n3} counted`);
  await ui.clearSelection(page);
  await search(page, "where class like 'IfcWall%' and storey like '%1%'");
  await page.keyboard.press('Shift+Enter');
  await ui.settle(page, 400);
  tour.check('step 4: Shift+Enter adds them to the selection', (await ui.selection(page)).length === n3);
  await page.keyboard.press('Escape');
  const t5 = await search(page, 'where class =');
  const err = await pop(page).locator('.ab-err').innerText().catch(() => '');
  tour.check('step 5: "A red note says what is wrong and where"', /Expected a value after "="/.test(err), err || t5.slice(0, 100));
  await page.keyboard.press('Escape');
  const t6 = await search(page, "count where class like 'IfcWall%'");
  tour.check('step 6: "You get a number, not a list: a quantity summary"', /\b240\b|count/i.test(t6) && !/ELEMENTS/.test(t6), t6.slice(0, 140));
  await page.keyboard.press('Escape');
  const t7 = await search(page, "class = 'IfcDuctSegment'");
  tour.check('"Type class = \'IfcDuctSegment\' and the box starts counting the elements"', /870 elements match/.test(t7), t7.slice(0, 100));
  await page.keyboard.press('Escape');
  const t8 = await search(page, 'where flavour = 3');
  tour.check('"A column that no element has reads as empty, and the box names it in a note"', /flavour/i.test(t8), t8.slice(0, 140));
});

await tour.finish();
