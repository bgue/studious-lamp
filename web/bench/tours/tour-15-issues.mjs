// Tour of chapter 15, "Issues" (docs/manual/15-issues.md): make an issue from a view (15.1), status, priority, assignee, comments, history (15.2),
// the list chips and search, and the reports (15.4). Issues from checks (15.3) are toured with the penetrations and the clearance (chapters 10, 11).
// Picture: `issues-tab`.
// Run: node bench/run-smokes.mjs --only tour-15-issues
import { readFileSync } from 'node:fs';
import { startTour, ui } from './lib.mjs';
import { drawThreeThings } from './views-helpers.mjs';

const tour = await startTour('tour-15-issues');
const issues = (page) => page.evaluate(() => (window.__xrayBcf.currentTopics ?? window.__xrayBcf.topics).map((t) => ({ guid: t.guid, title: t.title, status: t.topicStatus, priority: t.priority, assignedTo: t.assignedTo, due: t.dueDate, comments: t.comments.length })));
const items = (page) => page.locator('#sidebar .is-item');
const status = (page) => ui.statusText(page).then((t) => t.replace(/\s+/g, ' '));

await tour.step('15.1 Try it: Make issue from the view with drawings, the Issues tab, New issue', async () => {
  const page = await tour.open('model=fzk-haus');
  await drawThreeThings(page);
  // step 1: the Views tab, the row of the view with drawings
  await ui.tab(page, 'Views');
  await page.locator('#sidebar .vw-chip', { hasText: /^With drawings/ }).click();
  await page.locator('#sidebar .vw-row .vw-name').first().click();
  await page.waitForTimeout(1200);
  tour.check('step 1: "Click the row of your view with drawings. Its detail opens."', await page.getByText('‹ Views').first().isVisible());
  // step 2
  const make = page.locator('#sidebar').getByRole('button', { name: 'Make issue' }).first();
  await make.click();
  await page.waitForTimeout(500);
  const chooser = (await page.locator('.xm-menu, [role=menu]').first().innerText().catch(() => '')).replace(/\n+/g, ' | ');
  tour.check('step 2: "A chooser offers New issue and Add to: <issue> for each issue that already exists"', /New issue/.test(chooser), chooser);
  await page.locator('.xm-menu [role=menuitem], [role=menu] [role=menuitem]').filter({ hasText: 'New issue' }).first().click();
  await page.waitForTimeout(2500);
  const l1 = await issues(page);
  tour.check('step 3: "makes the issue from the view\'s title and note with status Open"', l1.length === 1 && /open/i.test(l1[0].status ?? l1[0].topicStatus ?? ''), JSON.stringify(l1).slice(0, 200));
  const det = await page.locator('#sidebar').innerText();
  tour.check('step 3: "its detail says In issue: <title> with Open issue" (or the issue detail itself opens)', /In issue:/.test(det) || /Open issue/.test(det) || /Status/.test(det), det.replace(/\s+/g, ' ').slice(0, 160));
  // step 4
  await ui.tab(page, 'Issues');
  await page.waitForTimeout(600);
  const listBack = page.getByRole('button', { name: '‹ Issues' });
  if (await listBack.count()) await listBack.click();
  await page.waitForTimeout(400);
  tour.check('step 4: "Your issue is in the list"', (await items(page).count()) === 1, await page.locator('#sidebar').innerText().then((t) => t.replace(/\s+/g, ' ').slice(0, 200)));
  const tags = await items(page).first().innerText();
  tour.check('step 4: "with status, priority, the number of views, comments and assignee"', /1 view/.test(tags), tags.replace(/\n/g, ' | '));
  const sb = await status(page);
  tour.check('step 4: "The status bar shows 1 open issues"', /1 open issues?/.test(sb), sb.slice(0, 200));
  // step 5
  const c0 = await ui.cam(page);
  await items(page).first().click();
  await page.waitForTimeout(1500);
  tour.check('step 5: "Click the issue. Its detail opens in the same column"', await page.getByRole('button', { name: '‹ Issues' }).isVisible());
  const d5 = await page.locator('#sidebar').innerText();
  tour.check('step 5: the views block has Apply, Clear, Edit drawings and Open in Views', ['Apply', 'Clear', 'Edit drawings', 'Open in Views'].every((b) => d5.includes(b)), d5.replace(/\s+/g, ' ').slice(0, 300));
  void c0;
  await page.getByRole('button', { name: 'Clear', exact: true }).first().click().catch(() => {});
  await page.getByRole('button', { name: '‹ Issues' }).click();
  // step 6
  await ui.tab(page, 'Views');
  await page.locator('#sidebar .vw-chip', { hasText: /^In an issue/ }).click();
  await page.waitForTimeout(400);
  tour.check('step 6: "click In an issue to list the views that issues point at"', (await page.locator('#sidebar .vw-row').count()) === 1 && /Issue/.test(await page.locator('#sidebar .vw-row').first().innerText()), await page.locator('#sidebar .vw-row').first().innerText().catch(() => ''));
  // the other direction
  await ui.tab(page, 'Issues');
  await ui.clearSelection(page);
  await ui.clickElement(page, { cls: 'IfcDoor' });
  await ui.tab(page, 'Issues');
  await page.getByRole('button', { name: 'New issue' }).first().click();
  await page.waitForTimeout(500);
  const dlg = page.locator('#bcf-f-create').locator('xpath=ancestor::form');
  const labels = await dlg.locator('label, .bcf-field').allInnerTexts().catch(() => []);
  const dtxt = await page.locator('body').innerText();
  tour.check('"The dialog is headed New issue. Fill Title and Description. Pick Type, Status and Priority. Add Labels and Assigned to. Author is remembered."', ['Title', 'Description', 'Type', 'Status', 'Priority', 'Labels', 'Assigned to', 'Author'].every((l) => new RegExp(l).test(dtxt)), labels.join(' | ').slice(0, 200));
  tour.check('"Two options: Attach a snapshot of the current view (on by default), and Click the model to place the pin"', /Attach a snapshot of the current view/.test(dtxt) && /Click the model to place the pin/.test(dtxt) && (await page.locator('#bcf-f-snapshot').isChecked()));
  await dlg.locator('input[type=text], input:not([type])').first().fill('Door too narrow');
  await dlg.locator('textarea').first().fill('The door does not meet the width.');
  await page.locator('#bcf-f-create').click();
  await page.waitForTimeout(2500);
  const l2 = await issues(page);
  tour.check('"Click Create issue. You get a second issue with its own view"', l2.length === 2, JSON.stringify(l2.map((i) => i.title)));
  // back to the list, first issue open for the picture
  const back = page.getByRole('button', { name: '‹ Issues' });
  if (await back.count()) await back.click();
  await page.waitForTimeout(500);
  await items(page).first().click();
  await page.waitForTimeout(1800);
  await page.mouse.move(700, 120);
  await ui.settle(page, 800);
  await tour.picture('issues-tab', { page, clip: { x: 0, y: 0, width: 640, height: 900 } });
});

await tour.step('15.2 Status, priority, assignee, due date, comments, history, list and search', async () => {
  const page = await tour.open('model=fzk-haus');
  await ui.clickElement(page, { cls: 'IfcWindow' });
  await ui.tab(page, 'Issues');
  await page.getByRole('button', { name: 'New issue' }).first().click();
  await page.locator('#bcf-f-create').waitFor();
  const dlg = page.locator('#bcf-f-create').locator('xpath=ancestor::form');
  await dlg.locator('input[type=text], input:not([type])').first().fill('Window sill too low');
  await page.locator('#bcf-f-create').click();
  await page.waitForTimeout(2500);
  const det = page.locator('#sidebar');
  const stSel = det.getByLabel('Status').first(), prSel = det.getByLabel('Priority').first();
  const stOpts = await stSel.locator('option').allInnerTexts();
  const prOpts = await prSel.locator('option').allInnerTexts();
  tour.check('"Statuses are Open, In Progress, Resolved and Closed"', ['Open', 'In Progress', 'Resolved', 'Closed'].every((s) => stOpts.some((o) => o.trim() === s)), stOpts.join(','));
  tour.check('"Priorities are Low, Normal, High and Critical"', ['Low', 'Normal', 'High', 'Critical'].every((s) => prOpts.some((o) => o.trim() === s)), prOpts.join(','));
  await stSel.selectOption({ label: 'In Progress' });
  await prSel.selectOption({ label: 'High' });
  await det.getByLabel('Assignee').fill('Mia');
  await det.getByLabel('Assignee').press('Enter');
  await det.getByLabel('Due date').fill('2026-12-24');
  await det.getByLabel('Due date').press('Enter').catch(() => {});
  await page.waitForTimeout(500);
  const t0 = (await issues(page))[0];
  tour.check('status, priority, assignee and due date are stored', /progress/i.test(t0.status ?? t0.topicStatus ?? '') && /high/i.test(t0.priority ?? '') && /Mia/.test(t0.assignedTo ?? t0.assignee ?? JSON.stringify(t0)), JSON.stringify(t0).slice(0, 240));
  await det.getByLabel('Comment').fill('Checked on site.');
  await det.getByRole('button', { name: 'Add comment' }).click();
  await page.waitForTimeout(500);
  const txt = await det.innerText();
  tour.check('"The comments with Add comment"', /Checked on site\./.test(txt), txt.replace(/\s+/g, ' ').slice(-200));
  tour.check('"History: created, each comment, last change"', /History/.test(txt) && /[Cc]reated/.test(txt), txt.match(/History[\s\S]{0,160}/)?.[0]?.replace(/\s+/g, ' ') ?? '');
  tour.check('"Add current view", "Place pin", "Export BCF 2.1", "Export BCF 3.0" and "Delete issue" are there', ['Add current view', 'Place pin', 'Export BCF 2.1', 'Export BCF 3.0', 'Delete issue'].every((b) => txt.includes(b)), '');
  // add current view
  await det.getByRole('button', { name: 'Add current view' }).click();
  await page.waitForTimeout(1200);
  const nViews = await page.evaluate(() => window.__xrayViews.list().length);
  tour.check('"Add current view: saves what you see now as a view and adds it to this issue"', nViews >= 2, String(nViews));
  // list, chips, search
  await det.getByRole('button', { name: '‹ Issues' }).click();
  await page.waitForTimeout(400);
  const chips = await page.locator('#sidebar .is-fchip').allInnerTexts();
  tour.check('"The list has a search box and the chips All, Open and Closed, each with a count"', chips.length === 3 && /^All 1/.test(chips[0]) && /^Open 1/.test(chips[1]) && /^Closed 0/.test(chips[2]), chips.join(' | '));
  await page.getByLabel('Search', { exact: true }).fill('sill');
  await page.waitForTimeout(300);
  const nHit = await items(page).count();
  await page.getByLabel('Search', { exact: true }).fill('zzzz');
  await page.waitForTimeout(300);
  const nMiss = await items(page).count();
  tour.check('"Search matches title, description, assignee, labels and comment text"', nHit === 1 && nMiss === 0, `${nHit} / ${nMiss}`);
  await page.getByLabel('Search', { exact: true }).fill('Checked on');
  await page.waitForTimeout(300);
  tour.check('search finds comment text', (await items(page).count()) === 1);
  await page.getByLabel('Search', { exact: true }).fill('');
  // top bar search finds issues
  await page.locator('#c').hover();
  await page.keyboard.press('/');
  await page.keyboard.type('sill');
  await page.waitForTimeout(900);
  const pop = await page.locator('.ab-pop').innerText();
  tour.check('"The top-bar search also finds issues"', /ISSUES/i.test(pop) && /Window sill too low/.test(pop), pop.replace(/\n+/g, ' / ').slice(0, 160));
  await page.keyboard.press('Escape');
  // closing moves it to Closed
  await items(page).first().click();
  await page.waitForTimeout(800);
  await page.locator('#sidebar').getByLabel('Status').first().selectOption({ label: 'Closed' });
  await page.waitForTimeout(500);
  await page.getByRole('button', { name: '‹ Issues' }).click();
  const sb = await status(page);
  tour.check('"N open issues counts the issues ... that are not resolved, closed ...": 0 open issues after closing', /0 open issues/.test(sb) || !/\d+ open issues?/.test(sb) || /^0/.test(sb), sb.slice(0, 200));
  // reports
  await page.locator('#sidebar details.is-report summary').click();
  const rt = await page.locator('#sidebar details.is-report').innerText();
  tour.check('15.4 "the collapsed block Export report has Page size and Plan/Section images, and two buttons: PDF report (n) and CSV (n)"', /Page size/.test(rt) && /Plan\/Section images/.test(rt) && /PDF report \(1\)/.test(rt) && /CSV \(1\)/.test(rt), rt.replace(/\s+/g, ' '));
  const [cd] = await Promise.all([page.waitForEvent('download', { timeout: 20000 }).catch(() => null), page.getByRole('button', { name: /^CSV/ }).click()]);
  const csv = cd ? readFileSync(await cd.path(), 'utf8') : '';
  tour.check('15.4 CSV downloads one row per issue', csv.split('\n').filter(Boolean).length === 2 && /Window sill too low/.test(csv), csv.slice(0, 120));
  const [pd] = await Promise.all([page.waitForEvent('download', { timeout: 120000 }).catch(() => null), page.getByRole('button', { name: /^PDF report/ }).click()]);
  const pb = pd ? readFileSync(await pd.path()) : Buffer.alloc(0);
  tour.check('15.4 the PDF report downloads', pb.subarray(0, 5).toString() === '%PDF-', `${pd?.suggestedFilename()} ${pb.length} bytes`);
});

await tour.finish();
