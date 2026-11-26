// Tour of chapter 16, "PDF sheets" (docs/manual/16-sheets.md): open a drawing set and draw on a page (16.1), the placement view and overlay (16.2),
// export a marked-up PDF and the imported annotations (16.3). Picture: `sheet-open`.
// Run: node bench/run-smokes.mjs --only tour-16-sheets
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { startTour, ui, webRoot } from './lib.mjs';
import { drawTool } from './views-helpers.mjs';

const tour = await startTour('tour-16-sheets');
const SAMPLE = resolve(webRoot, 'public', 'samples', 'sample-sheet.pdf');
const sheetView = (page) => page.locator('#sheet-view');
const openPdf = async (page) => {
  await ui.tab(page, 'Views');
  await page.locator('#sidebar .vw-chip', { hasText: /^On sheets/ }).click();
  await page.waitForTimeout(400);
  const [fc] = await Promise.all([page.waitForEvent('filechooser', { timeout: 15000 }), page.getByRole('button', { name: 'Open PDF' }).click()]);
  await fc.setFiles(SAMPLE);
};

await tour.step('16.1 Try it: open sample-sheet.pdf, open page 1, pan, zoom, imported annotations, draw, back to model', async () => {
  const page = await tour.open('model=fzk-haus');
  tour.check('step 1: "Open FZK-Haus so that a model is loaded"', (await ui.model(page)).n === 82);
  await ui.tab(page, 'Views');
  await page.locator('#sidebar .vw-chip', { hasText: /^On sheets/ }).click();
  await page.waitForTimeout(400);
  tour.check('step 2: "click the chip On sheets. The list is replaced by the sheets pane"', await page.getByRole('button', { name: 'Open PDF' }).isVisible());
  const [fc] = await Promise.all([page.waitForEvent('filechooser', { timeout: 15000 }), page.getByRole('button', { name: 'Open PDF' }).click()]);
  await fc.setFiles(SAMPLE);
  await page.waitForFunction(() => window.__xraySheets.sheets().length > 0, null, { timeout: 120000 });
  await page.locator('#sidebar .sh-page').first().waitFor({ timeout: 60000 });
  await page.waitForTimeout(1500);
  const sheets = await page.evaluate(() => window.__xraySheets.sheets().map((s) => s.page ?? s.pageNo ?? s.index));
  tour.check('step 3: "The PDF appears with its 2 pages as thumbnails"', sheets.length === 2 && (await page.locator('#sidebar .sh-page img').count()) === 2, `${sheets.length} sheets, ${await page.locator('#sidebar .sh-page img').count()} thumbnails`);
  // step 4: click page 1
  const sheetId = await page.evaluate(() => window.__xraySheets.sheets()[0].id);
  await page.locator('#sidebar .sh-page').first().click();
  await sheetView(page).waitFor({ state: 'visible', timeout: 60000 });
  await page.waitForTimeout(2500);
  tour.check('step 4: "Click page 1. A 2D view covers the model area"', await sheetView(page).isVisible() && (await page.evaluate(() => window.__xraySheets.openSheet)) === sheetId);
  const bar = await sheetView(page).innerText();
  tour.check('step 4: "At top left is Back to model. The bar also has page arrows, Fit, a list of views on this sheet, Draw and Make issue"', /Back to model/.test(bar) && /Fit/.test(bar) && /Draw/.test(bar) && /Make issue/.test(bar) && (await sheetView(page).locator('[data-act=prev]').count()) === 1, bar.replace(/\s+/g, ' ').slice(0, 160));
  const v0 = await page.evaluate(() => window.__xraySheets.view());
  // pan
  const sb = await sheetView(page).boundingBox();
  await page.mouse.move(sb.x + sb.width * 0.5, sb.y + sb.height * 0.6); await page.mouse.down(); await page.mouse.move(sb.x + sb.width * 0.5 + 60, sb.y + sb.height * 0.6 + 30, { steps: 5 }); await page.mouse.up();
  await page.waitForTimeout(500);
  const v1 = await page.evaluate(() => window.__xraySheets.view());
  tour.check('step 5: "Pan by dragging the empty page"', JSON.stringify(v0) !== JSON.stringify(v1), JSON.stringify(v0).slice(0, 80) + ' -> ' + JSON.stringify(v1).slice(0, 80));
  await page.mouse.move(sb.x + sb.width * 0.5, sb.y + sb.height * 0.5);
  await page.mouse.wheel(0, -240);
  await page.waitForTimeout(700);
  const v2 = await page.evaluate(() => window.__xraySheets.view());
  const zoomOf = (v) => v.zoom ?? v.scale ?? v.k ?? 0;
  tour.check('step 5: "Zoom with the wheel"', zoomOf(v2) > zoomOf(v1), `${zoomOf(v1)} -> ${zoomOf(v2)}`);
  await page.keyboard.press('+');
  await page.waitForTimeout(500);
  const v3 = await page.evaluate(() => window.__xraySheets.view());
  tour.check('step 5: "the + and - keys"', zoomOf(v3) > zoomOf(v2), `${zoomOf(v2)} -> ${zoomOf(v3)}`);
  await page.keyboard.press('0');
  await page.waitForTimeout(600);
  const v4 = await page.evaluate(() => window.__xraySheets.view());
  tour.check('step 5: "0 fits the page"', Math.abs(zoomOf(v4) - zoomOf(v0)) < zoomOf(v0) * 0.05 + 1e-6, `${zoomOf(v0)} vs ${zoomOf(v4)}`);
  // step 6: imported annotations
  await sheetView(page).locator('select[data-sv=sketch]').waitFor({ timeout: 5000 }).catch(() => {});
  const sel = await sheetView(page).locator('select[data-sv=sketch]').innerText().catch(() => '');
  tour.check('step 6: "The three annotations that were already in the PDF show as one read-only view called Imported annotations"', /Imported annotations/.test(sel) || /Imported annotations/.test(await page.locator('#sidebar').innerText()), sel.replace(/\s+/g, ' '));
  // step 7: copy to editable
  const back0 = page.getByRole('button', { name: 'Back to model' });
  await back0.click();
  await page.waitForTimeout(600);
  await ui.tab(page, 'Views');
  const copyBtn = page.getByRole('button', { name: 'Copy to editable drawings' });
  const hasCopy = (await copyBtn.count()) > 0;
  if (!hasCopy) {
    const imp = page.locator('#sidebar .vw-row, #sidebar [data-view-key]', { hasText: /Imported annotations/ }).first();
    await imp.click().catch(() => {});
    await page.waitForTimeout(500);
  }
  const copyBtn2 = page.getByRole('button', { name: 'Copy to editable drawings' });
  tour.check('step 7: "Click Copy to editable drawings on that view"', (await copyBtn2.count()) >= 1, await page.locator('#sidebar').innerText().then((t) => t.replace(/\s+/g, ' ').slice(0, 160)));
  if (await copyBtn2.count()) {
    const before = await page.evaluate(() => window.__xrayViews.list().length);
    await copyBtn2.first().click();
    await page.waitForTimeout(800);
    const after = await page.evaluate(() => window.__xrayViews.list().length);
    tour.check('step 7: "You get an editable copy, and the original stays read-only"', after === before + 1, `${before} -> ${after}`);
  }
  // step 4 again: open page 1 and step 8: draw
  await page.evaluate((id) => window.__xraySheets.open(id), sheetId);
  await sheetView(page).waitFor({ state: 'visible', timeout: 30000 });
  await page.waitForTimeout(1500);
  await page.keyboard.press('0');
  await sheetView(page).locator('[data-act=draw]').click();
  await page.locator('.markup-float:visible').first().waitFor({ state: 'visible', timeout: 30000 });
  const tools = await page.locator('.markup-float:visible .mf-tool').evaluateAll((b) => b.map((x) => x.getAttribute('aria-label')));
  tour.check('step 8: "The same floating toolbar as in 3D appears (without the 3D-only Pointer)"', tools.includes('Cloud') && !tools.includes('Pointer'), tools.join(' | '));
  await drawTool(page, 'Cloud').click();
  const sb2 = await sheetView(page).boundingBox();
  const x0 = sb2.x + sb2.width * 0.58, y0 = sb2.y + sb2.height * 0.5;
  await page.mouse.move(x0, y0); await page.mouse.down(); await page.mouse.move(x0 + 140, y0 + 90, { steps: 8 }); await page.mouse.up();
  await page.waitForTimeout(700);
  const n = await page.evaluate(() => window.__xraySheets.sketches(window.__xraySheets.openSheet).flatMap((s) => s.markups).filter((m) => /cloud/.test(m.kind)).length);
  tour.check('step 8: "Click Cloud and drag a rectangle on the plan"', n >= 1, String(n));
  await page.locator('.markup-float:visible button[data-act=done]').first().click();
  await page.waitForTimeout(600);
  // picture
  await page.addStyleTag({ content: '#xray-help{display:none!important}' });
  await page.mouse.move(sb2.x + 20, sb2.y + sb2.height - 20);
  await page.waitForTimeout(1500);
  await ui.settle(page, 800);
  await tour.picture('sheet-open', { page });
  // step 9
  await page.getByRole('button', { name: 'Back to model' }).click();
  await page.waitForTimeout(800);
  tour.check('step 9: "Click Back to model. The model returns as you left it"', !(await sheetView(page).isVisible().catch(() => false)) && (await page.evaluate(() => window.__xraySheets.openSheet)) == null, '');
});

await tour.step('16.2/16.3 Place in model, Model overlay, export a marked-up PDF', async () => {
  const page = await tour.open('model=fzk-haus');
  await openPdf(page);
  await page.waitForFunction(() => window.__xraySheets.sheets().length > 0, null, { timeout: 120000 });
  await page.locator('#sidebar .sh-page').first().waitFor({ timeout: 60000 });
  await page.waitForTimeout(1500);
  const txt = await page.locator('#sidebar').innerText();
  tour.check('"The sheets pane says it per sheet: Not placed"', /Not placed/.test(txt), txt.replace(/\s+/g, ' ').slice(0, 200));
  for (const b of ['Place in model…', 'Export marked-up PDF']) tour.check(`"Each sheet has the action ${b}"`, (await page.getByRole('button', { name: b }).count()) >= 1);
  await page.getByRole('button', { name: 'Place in model…' }).first().click();
  await page.waitForTimeout(2500);
  const pv = await page.evaluate(() => document.body.innerText);
  tour.check('16.2 step 1: "The placement view opens: the sheet on the left, the plan of one storey on the right. Choose the storey in the list"', /Use drawing scale/.test(pv) || /Add point|Accept|Undo point/.test(pv), pv.match(/(Use drawing scale|Add point|Accept|Undo point)/)?.[0] ?? '');
  await page.getByRole('button', { name: 'Cancel' }).first().click().catch(() => {});
  await page.waitForTimeout(500);
  const [dl] = await Promise.all([page.waitForEvent('download', { timeout: 60000 }).catch(() => null), page.getByRole('button', { name: 'Export marked-up PDF' }).first().click()]);
  const bytes = dl ? readFileSync(await dl.path()) : Buffer.alloc(0);
  tour.check('16.3 "Export marked-up PDF writes a copy of the original"', bytes.subarray(0, 5).toString() === '%PDF-', `${dl?.suggestedFilename()} ${bytes.length} bytes`);
});

await tour.finish();
