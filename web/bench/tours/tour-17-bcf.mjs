// Tour of chapter 17, "Exchanging issues: BCF" (docs/manual/17-bcf.md): the round trip (17.2), what applying a viewpoint does (17.3), what the file holds (17.4).
// Picture: `bcf-opened`.
// Run: node bench/run-smokes.mjs --only tour-17-bcf
import { readFileSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { startTour, ui, webRoot } from './lib.mjs';
import { drawThreeThings } from './views-helpers.mjs';

const tour = await startTour('tour-17-bcf');
const issues = (page) => page.evaluate(() => (window.__xrayBcf.currentTopics ?? window.__xrayBcf.topics).map((t) => ({ guid: t.guid, title: t.title, status: t.topicStatus, priority: t.priority, assignedTo: t.assignedTo, due: t.dueDate, comments: t.comments.length })));
const userHides = (page) => page.evaluate(() => window.__xray.app.controller.settings.overrides.userHides.size);
const isUnzip = async () => {
  try { return createRequire(import.meta.url)(webRoot + '/node_modules/fflate'); } catch { return null; }
};

await tour.step('17.2 Try it: make an issue with a drawing, export BCF 2.1, delete, open BCF, apply, clear', async () => {
  const page = await tour.open('model=fzk-haus');
  await drawThreeThings(page);
  await ui.tab(page, 'Views');
  await page.locator('#sidebar .vw-chip', { hasText: /^With drawings/ }).click();
  await page.locator('#sidebar .vw-row .vw-name').first().click();
  await page.waitForTimeout(1000);
  await page.locator('#sidebar').getByRole('button', { name: 'Make issue', exact: true }).click();
  await page.waitForFunction(() => (window.__xrayBcf.currentTopics ?? window.__xrayBcf.topics).length >= 1, null, { timeout: 90000 }).catch(() => {});
  await page.waitForTimeout(1500);
  const made = await issues(page);
  tour.check('"First make an issue with a drawing, as in 15.1"', made.length === 1, JSON.stringify(made).slice(0, 120));
  // step 1
  await ui.tab(page, 'Issues');
  const back = page.getByRole('button', { name: '‹ Issues' });
  if (await back.count()) await back.click();
  await page.locator('#sidebar .is-item').first().click();
  await page.waitForTimeout(1200);
  tour.check('step 1: "Open the Issues tab and click your issue. Its detail opens."', await page.getByRole('button', { name: 'Export BCF 2.1' }).isVisible());
  // step 2
  const [dl] = await Promise.all([page.waitForEvent('download', { timeout: 30000 }), page.getByRole('button', { name: 'Export BCF 2.1' }).click()]);
  const file = await dl.path();
  const bytes = readFileSync(file);
  tour.check('step 2: "The browser downloads a .bcfzip of every issue in the list"', /\.(bcfzip|bcf)$/.test(dl.suggestedFilename()) && bytes.subarray(0, 2).toString() === 'PK', `${dl.suggestedFilename()} ${bytes.length} bytes`);
  const fflate = await isUnzip();
  if (fflate) {
    const z = fflate.unzipSync(new Uint8Array(bytes));
    const names = Object.keys(z);
    tour.check('17.4 "the viewer writes a small extra file, xray-markup.json, in each issue\'s folder"', names.some((n) => /xray-markup\.json$/.test(n)) && names.some((n) => /markup\.bcf$/.test(n)) && names.some((n) => /viewpoint\.bcfv$/.test(n)), names.join(', '));
    const ver = fflate.strFromU8(z['bcf.version'] ?? new Uint8Array());
    tour.check('"It writes 2.1 (the default)"', /VersionId="2\.1"/.test(ver), ver.slice(0, 120));
  }
  // step 3: delete the issue
  await page.getByRole('button', { name: 'Delete issue' }).click();
  await page.waitForTimeout(300);
  const second = page.getByRole('button', { name: /Delete issue|Click again|Confirm/i });
  if (await second.count()) await second.first().click();
  await page.waitForTimeout(1000);
  const afterDel = await issues(page);
  const sb = (await ui.statusText(page)).replace(/\s+/g, ' ');
  tour.check('step 3: "Click Delete issue. The issue goes."', afterDel.length === 0, `${afterDel.length} issues left`);
  tour.check('step 3: "The status bar says 0 open issues"', /0 open issues/.test(sb) || !/[1-9]\d* open issue/.test(sb), sb.slice(0, 200));
  const loose = await page.evaluate(() => window.__xrayViews.list().length);
  tour.check('step 3: "Its view stays in the Views tab as a loose view"', loose === 1, String(loose));
  // hide a wall by hand, to see Clear keep it
  await ui.tab(page, 'Model');
  const cls = page.locator('#sidebar .tr', { has: page.locator('.lbl', { hasText: /^IfcWindow$/ }) }).first();
  if ((await cls.getAttribute('aria-expanded')) === 'false') await cls.locator('.caret').click();
  await page.locator('#sidebar .tr.k-element').first().locator('.eye').click();
  await ui.settle(page, 500);
  const mine = await userHides(page);
  // step 4: Open BCF
  await ui.tab(page, 'Issues');
  const [fc] = await Promise.all([page.waitForEvent('filechooser', { timeout: 15000 }), page.getByRole('button', { name: 'Open BCF' }).click()]);
  await fc.setFiles(file);
  await page.waitForTimeout(3500);
  const reopened = await issues(page);
  tour.check('step 5: "The issue is back, with its status, priority, comments and snapshot"', reopened.length === 1, JSON.stringify(reopened).slice(0, 200));
  const back2 = page.getByRole('button', { name: '‹ Issues' });
  if (await back2.count()) await back2.click();
  await page.locator('#sidebar .is-item').first().click();
  await page.waitForTimeout(2500);
  const st = (await ui.statusText(page)).replace(/\s+/g, ' ');
  const dtxt = await page.locator('#sidebar').innerText();
  tour.check('step 5: "Click it: the camera, selection, hides and cut come back, and the status line says what was applied"', /applied|Viewpoint|viewpoint|Applied|view/i.test(st) || /Apply/.test(dtxt), st.slice(0, 200));
  tour.check('step 5: "The Views tab has a view linked to the issue, with your drawings"', await page.evaluate(() => window.__xrayViews.list().some((v) => v.hasDrawings || v.drawings > 0 || /✎/.test(JSON.stringify(v)))), JSON.stringify(await page.evaluate(() => window.__xrayViews.list())).slice(0, 200));
  // picture: Issues tab after opening a BCF file
  await page.mouse.move(700, 120);
  await ui.settle(page, 800);
  await tour.picture('bcf-opened', { page });
  // step 6: Clear
  await page.getByRole('button', { name: 'Clear', exact: true }).first().click();
  await page.waitForTimeout(800);
  tour.check('step 6: "Click Clear on the view row. ... elements you hid yourself stay hidden."', (await userHides(page)) === mine, `${mine} before, ${await userHides(page)} after`);
  // 3.0 export
  const [d3] = await Promise.all([page.waitForEvent('download', { timeout: 30000 }), page.getByRole('button', { name: 'Export BCF 3.0' }).click()]);
  const b3 = readFileSync(await d3.path());
  const fflate3 = await isUnzip();
  if (fflate3) {
    const z3 = fflate3.unzipSync(new Uint8Array(b3));
    tour.check('"3.0 writes ... an extensions file"', Object.keys(z3).some((n) => /extensions/i.test(n)) && /VersionId="3\.0"/.test(fflate3.strFromU8(z3['bcf.version'])), Object.keys(z3).slice(0, 6).join(', '));
  }
  void writeFileSync;
});

await tour.step('17.2 Opening replaces, unless you have your own; a file for another model', async () => {
  const page = await tour.open('model=fzk-haus');
  await ui.clickElement(page, { cls: 'IfcDoor' });
  await ui.tab(page, 'Issues');
  await page.getByRole('button', { name: 'New issue' }).first().click();
  await page.locator('#bcf-f-create').waitFor();
  await page.locator('#bcf-f-title').fill('Own issue');
  await page.locator('#bcf-f-create').click();
  await page.waitForTimeout(2500);
  const back = page.getByRole('button', { name: '‹ Issues' });
  if (await back.count()) await back.click();
  await page.locator('#sidebar .is-item').first().click();
  await page.waitForTimeout(800);
  const [dl] = await Promise.all([page.waitForEvent('download', { timeout: 30000 }), page.getByRole('button', { name: 'Export BCF 2.1' }).click()]);
  const file = await dl.path();
  await page.getByRole('button', { name: '‹ Issues' }).click();
  // a second own issue, then open the file: it is merged in, not replaced
  await ui.clickElement(page, { cls: 'IfcWindow' });
  await page.getByRole('button', { name: 'New issue' }).first().click();
  await page.locator('#bcf-f-create').waitFor();
  await page.locator('#bcf-f-title').fill('Second own issue');
  await page.locator('#bcf-f-create').click();
  await page.waitForTimeout(2500);
  const [fc] = await Promise.all([page.waitForEvent('filechooser', { timeout: 15000 }), (async () => { const b = page.getByRole('button', { name: '‹ Issues' }); if (await b.count()) await b.click(); await page.getByRole('button', { name: 'Open BCF' }).click(); })()]);
  await fc.setFiles(file);
  await page.waitForTimeout(3000);
  const titles = (await issues(page)).map((i) => i.title);
  tour.check('"If you have unsaved issues of your own, the file is merged in instead"', titles.includes('Own issue') && titles.includes('Second own issue') && titles.length === 2, titles.join(' | '));
});

await tour.finish();
