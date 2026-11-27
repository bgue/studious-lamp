// Tour of chapter 13, "Views" (docs/manual/13-views.md): save, name, reorder, restore (13.2), play, export and import, share link (13.4).
// Plan and Section (13.3) need a drawing and are toured in tour-14-drawing. Picture: `views-tab`.
// Run: node bench/run-smokes.mjs --only tour-13-views
import { readFileSync } from 'node:fs';
import { startTour, ui } from './lib.mjs';

const tour = await startTour('tour-13-views');
const rowsOf = (page) => page.locator('#sidebar .vw-row');
const names = (page) => rowsOf(page).locator('.vw-name').allInnerTexts();
const vrow = (page, name) => page.locator('#sidebar .vw-row', { has: page.locator('.vw-name', { hasText: new RegExp(`^${name}$`) }) });
const userHides = (page) => page.evaluate(() => window.__xray.app.controller.settings.overrides.userHides.size);

await tour.step('13.2 Try it: save, restore, rename, reorder', async () => {
  const page = await tour.open('model=fzk-haus');
  const win = await ui.clickElement(page, { cls: 'IfcWindow' });
  await ui.waitStill(page, 12000);
  tour.check('step 2: "Click a window to select it"', !!win && win.cls === 'IfcWindow', JSON.stringify(win));
  const c0 = await ui.cam(page);
  await ui.tab(page, 'Views');
  const nameBox = page.getByLabel('New view name');
  tour.check('step 3: "a box with the hint View name (optional) and a button Save view"', (await nameBox.isVisible()) && (await page.getByRole('button', { name: 'Save view' }).isVisible()));
  await nameBox.fill('Window from outside');
  await page.keyboard.press('Enter');
  await page.waitForTimeout(800);
  const r1 = vrow(page, 'Window from outside');
  const rowText = (await r1.innerText()).replace(/\s+/g, ' ');
  tour.check('step 4: "A row appears: a drag grip, the number 1, the name, and a one-line summary" (x-ray · 1 selected)', (await r1.count()) === 1 && (await r1.locator('.vw-grip').count()) === 1 && (await r1.locator('.vw-num').innerText()) === '1' && /x-ray · 1 selected/.test(rowText), rowText);
  // hover thumbnail
  await r1.locator('.vw-name').hover();
  await page.waitForTimeout(700);
  const peek = page.locator('.vw-peek');
  tour.check('step 4: "Hover over the row to see a thumbnail next to the sidebar"', (await peek.isVisible()) && (await peek.locator('img').count()) === 1, await peek.innerText().catch(() => ''));
  // step 5: orbit away, hide a wall with the tree, select something else
  const box = await page.locator('#c').boundingBox();
  await page.mouse.move(box.x + 700, box.y + 450); await page.mouse.down(); await page.mouse.move(box.x + 560, box.y + 420, { steps: 6 }); await page.mouse.up();
  await ui.waitStill(page, 8000);
  await ui.tab(page, 'Model');
  const cls = page.locator('#sidebar .tr', { has: page.locator('.lbl', { hasText: /^IfcWallStandardCase$/ }) }).first();
  if ((await cls.getAttribute('aria-expanded')) === 'false') await cls.locator('.caret').click();
  await page.locator('#sidebar .tr.k-element').first().locator('.eye').click();
  await ui.settle(page, 500);
  tour.check('step 5: "Hide a wall with the model tree"', (await userHides(page)) === 1, String(await userHides(page)));
  await ui.clickElement(page, { cls: 'IfcDoor' });
  const doorSel = await ui.selection(page);
  const c1 = await ui.cam(page);
  await ui.tab(page, 'Views');
  await page.locator('#sidebar .vw-row .vw-name', { hasText: 'Window from outside' }).click();
  await ui.waitMoved(page, c1, 12000).catch(() => {});
  const c2 = await ui.cam(page);
  const sel2 = await ui.selection(page);
  tour.check('step 6: "The camera turns back over about 0.4 s"', Math.hypot(...c2.p.map((v, i) => v - c0.p[i])) < 0.5, `distance from saved ${Math.hypot(...c2.p.map((v, i) => v - c0.p[i])).toFixed(2)} m, started ${Math.hypot(...c1.p.map((v, i) => v - c0.p[i])).toFixed(2)} m away`);
  tour.check('step 6: "the hidden wall returns"', (await userHides(page)) === 0, String(await userHides(page)));
  tour.check('step 6: "and the window is selected again"', sel2.length === 1 && sel2[0].cls === 'IfcWindow' && doorSel[0]?.cls === 'IfcDoor', JSON.stringify(sel2));
  tour.check('step 6: "The row is marked as the last view you restored"', await r1.evaluate((r) => r.classList.contains('active')));
  // step 7: empty name -> View 2, taken name gets a number
  await page.getByRole('button', { name: 'Save view' }).click();
  await page.waitForTimeout(600);
  tour.check('step 7: "Click Save view with the name box empty. You get View 2"', (await names(page)).includes('View 2'), (await names(page)).join(' | '));
  await nameBox.fill('Window from outside');
  await page.keyboard.press('Enter');
  await page.waitForTimeout(600);
  const ns = await names(page);
  tour.check('step 7: "A name that is already taken gets a number added"', ns.length === 3 && ns.filter((n) => /^Window from outside/.test(n)).length === 2 && new Set(ns).size === 3, ns.join(' | '));
  // step 8: rename via menu, then F2
  await page.locator('#sidebar .vw-row', { has: page.locator('.vw-name', { hasText: /^View 2$/ }) }).locator('[data-act=menu]').click();
  const items = await page.locator('.xm-menu [role=menuitem]').allInnerTexts();
  tour.check('"The row menu: Update from current, Draw on this view, Make issue, Rename, Duplicate, Copy link and Delete" (and Details for saved views with a set)', ['Update from current', 'Draw on this view', 'Make issue', 'Rename', 'Duplicate', 'Copy link', 'Delete'].every((l) => items.includes(l)), items.join(' | '));
  await page.locator('.xm-menu [role=menuitem]', { hasText: 'Rename' }).click();
  await page.locator('.vw-rename').fill('Overview');
  await page.keyboard.press('Enter');
  await page.waitForTimeout(400);
  tour.check('step 8: "Rename a view: the ⋯ at the end of its row and choose Rename"', (await names(page)).includes('Overview'), (await names(page)).join(' | '));
  await vrow(page, 'Overview').locator('.vw-name').focus();
  await page.keyboard.press('F2');
  await page.waitForTimeout(300);
  tour.check('step 8: "or focus the row and press F2"', (await page.locator('.vw-rename').count()) === 1);
  await page.locator('.vw-rename').fill('Overview 2');
  await page.keyboard.press('Enter');
  await page.waitForTimeout(400);
  // step 9: reorder
  await vrow(page, 'Overview 2').locator('.vw-name').focus();
  const before = await names(page);
  await page.keyboard.press('Alt+ArrowUp');
  await page.waitForTimeout(500);
  const after = await names(page);
  const nums = await rowsOf(page).locator('.vw-num').allInnerTexts();
  tour.check('step 9: "focus a row and press Alt+ArrowUp ... The numbers follow the list order"', after.indexOf('Overview 2') === before.indexOf('Overview 2') - 1 && nums.join() === '1,2,3', `${before.join(' | ')} -> ${after.join(' | ')} (${nums.join()})`);
  // drag the grip
  const g = await rowsOf(page).nth(2).locator('.vw-grip').boundingBox();
  const t = await rowsOf(page).nth(0).boundingBox();
  const last = (await names(page))[2];
  await page.mouse.move(g.x + g.width / 2, g.y + g.height / 2);
  await page.mouse.down();
  await page.mouse.move(g.x + g.width / 2, t.y + 3, { steps: 8 });
  await page.mouse.up();
  await page.waitForTimeout(600);
  tour.check('step 9: "drag the grip of a row up or down"', (await names(page))[0] === last, (await names(page)).join(' | '));
  // keys
  await page.locator('#c').hover();
  const nBefore = (await names(page)).length;
  await page.keyboard.press('Control+Shift+s');
  await page.waitForTimeout(700);
  tour.check('"The key Ctrl+Shift+S does the same as Save view from anywhere"', (await names(page)).length === nBefore + 1, (await names(page)).join(' | '));
  const cA = await ui.cam(page);
  await page.keyboard.press('Shift+PageUp');
  await ui.waitMoved(page, cA, 8000).catch(() => {});
  const lastKey = await page.locator('#sidebar .vw-row.active .vw-name').innerText().catch(() => '');
  tour.check('"Shift+PageUp and Shift+PageDown step to the previous and next view"', lastKey.length > 0, lastKey);
  // the filter chips
  const chips = await page.locator('#sidebar .vw-chip').allInnerTexts();
  tour.check('"Four chips sit above the list: All, With drawings, On sheets, In an issue"', chips.length === 4 && /^All 4/.test(chips[0]) && /^With drawings 0/.test(chips[1]) && /^On sheets/.test(chips[2]) && /^In an issue 0/.test(chips[3]), chips.join(' | '));
  await page.getByPlaceholder('Filter views').fill('Overview');
  await page.waitForTimeout(300);
  tour.check('"The box Filter views matches the name"', (await rowsOf(page).count()) === 1, String(await rowsOf(page).count()));
  await page.getByPlaceholder('Filter views').fill('');
});

await tour.step('13.2 The picture: three views, the chips and the thumbnail of the hovered row', async () => {
  const page = await tour.open('model=fzk-haus');
  const nameBox = () => page.getByLabel('New view name');
  const save = async (name) => { await ui.tab(page, 'Views'); await nameBox().fill(name); await page.keyboard.press('Enter'); await page.waitForTimeout(700); };
  await ui.clickElement(page, { cls: 'IfcWindow' });
  await ui.waitStill(page, 10000);
  await save('Window from outside');
  await ui.clearSelection(page);
  await page.locator('#c').hover();
  await page.keyboard.press('Home');
  await ui.waitStill(page, 10000);
  await save('Whole house');
  await ui.clickElement(page, { cls: 'IfcDoor' });
  await ui.waitStill(page, 10000);
  await save('Front door');
  await ui.tab(page, 'Views');
  tour.check('three views are listed', (await rowsOf(page).count()) === 3, (await names(page)).join(' | '));
  await page.evaluate(() => window.__xrayHelp?.disable?.());
  await ui.settle(page, 800);
  await rowsOf(page).nth(0).locator('.vw-name').hover();
  await page.waitForTimeout(800);
  await tour.picture('views-tab', { page, clip: { x: 0, y: 0, width: 640, height: 420 } });
});

await tour.step('13.2 Update, duplicate, play, export, import, share link', async () => {
  const page = await tour.open('model=fzk-haus');
  await ui.clickElement(page, { cls: 'IfcWindow' });
  await ui.tab(page, 'Views');
  await page.getByRole('button', { name: 'Save view' }).click();
  await page.waitForTimeout(600);
  const name1 = (await names(page))[0];
  await page.keyboard.press('Escape');
  await ui.clearSelection(page);
  await ui.tab(page, 'Views');
  const row = rowsOf(page).first();
  await row.locator('[data-act=menu]').click();
  await page.locator('.xm-menu [role=menuitem]', { hasText: 'Update from current' }).click();
  await page.waitForTimeout(600);
  tour.check('"Update from current keeps the name and replaces the camera and state with what you see now"', (await names(page))[0] === name1 && /1 selected/.test(await rowsOf(page).first().innerText()) === false, (await rowsOf(page).first().innerText()).replace(/\s+/g, ' '));
  await rowsOf(page).first().locator('[data-act=menu]').click();
  await page.locator('.xm-menu [role=menuitem]', { hasText: 'Duplicate' }).click();
  await page.waitForTimeout(500);
  tour.check('"Duplicate makes a plain copy"', (await rowsOf(page).count()) === 2, (await names(page)).join(' | '));
  // play
  const play = page.locator('.vw-play');
  await page.getByLabel('Time on each view').selectOption('2000');
  await play.click();
  await page.waitForTimeout(800);
  tour.check('"The Play button steps through the views": it changes to Stop', /Stop/.test(await page.locator('.vw-play').innerText()));
  await page.keyboard.press('Escape');
  await page.waitForTimeout(500);
  tour.check('"Escape stops it"', /Play/.test(await page.locator('.vw-play').innerText()));
  const dwell = await page.getByLabel('Time on each view').locator('option').allInnerTexts();
  tour.check('"The list beside it sets the time on each view: 2, 4, 6 or 10 s"', ['2 s', '4 s', '6 s', '10 s'].every((d) => dwell.includes(d)), dwell.join(','));
  // export / import
  const [dl] = await Promise.all([page.waitForEvent('download', { timeout: 15000 }), page.locator('#sidebar .vw-top').getByRole('button', { name: 'Export', exact: true }).click()]);
  tour.check('"Export downloads a file named xray-views-<model>-<date>.json"', /^xray-views-fzk-haus-\d{4}-\d{2}-\d{2}\.json$/.test(dl.suggestedFilename()), dl.suggestedFilename());
  const path = `/tmp/x/${Date.now()}-${dl.suggestedFilename()}`;
  await dl.saveAs(path);
  const data = JSON.parse(readFileSync(path, 'utf8'));
  tour.check('the file holds the saved views with thumbnails', JSON.stringify(data).includes('thumb') || JSON.stringify(data).includes('data:image'), JSON.stringify(data).slice(0, 100));
  await rowsOf(page).last().locator('[data-act=menu]').click();
  await page.locator('.xm-menu [role=menuitem]', { hasText: 'Delete' }).click();
  await page.locator('.xm-menu [role=menuitem]', { hasText: /click again|Delete/i }).click();
  await page.waitForTimeout(400);
  const nDel = await rowsOf(page).count();
  const [chooser] = await Promise.all([page.waitForEvent('filechooser'), page.locator('#sidebar .vw-top').getByRole('button', { name: 'Import', exact: true }).click()]);
  await chooser.setFiles(path);
  for (let i = 0; i < 12 && (await rowsOf(page).count()) < nDel + 1; i++) await page.waitForTimeout(700);
  tour.check('"Import adds the views of such a file": the deleted view is back', (await rowsOf(page).count()) === nDel + 1, `${nDel} -> ${await rowsOf(page).count()}; ${(await page.locator('#sidebar .vw-top').innerText()).replace(/\s+/g, ' ').slice(0, 80)}`);
  // copy link
  await page.context().grantPermissions(['clipboard-read', 'clipboard-write']).catch(() => {});
  await rowsOf(page).first().locator('[data-act=menu]').click();
  await page.locator('.xm-menu [role=menuitem]', { hasText: 'Copy link' }).click();
  await page.waitForTimeout(600);
  const link = await page.evaluate(() => navigator.clipboard.readText()).catch(() => '');
  tour.check('"Copy link puts a web address on the clipboard ... ?model=<name>#view=..."', /\?model=fzk-haus.*#view=/.test(link) && link.length > 100 && link.length < 1500, `${link.length} chars: ${link.slice(0, 90)}`);
  if (link) {
    const p2 = await tour.open('model=fzk-haus');
    const hash = link.slice(link.indexOf('#'));
    await p2.evaluate((h) => { location.hash = h.slice(1); }, hash);
    await p2.reload();
    await p2.waitForFunction(() => window.__xrayReady, null, { timeout: 120000 });
    await ui.settle(p2, 1500);
    const st = await ui.statusText(p2);
    const urlNow = await p2.evaluate(() => location.href);
    tour.check('"Whoever opens it ... gets the camera and look applied once, and the link is removed from the address bar"', !/#view=/.test(urlNow), urlNow);
    void st;
  }
});

await tour.finish();
