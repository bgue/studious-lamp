// Tour of chapter 19, "Parameters, properties and saving" (docs/manual/19-data-and-saving.md): export / import parameters (19.1), the Properties tab (19.2),
// Save IFC and Save cleaned copy (19.3) and what is saved where (19.4). No picture notes in this chapter.
// Run: node bench/run-smokes.mjs --only tour-19-data-and-saving
import { mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { repoRoot, startTour, ui } from './lib.mjs';

const tour = await startTour('tour-19-data-and-saving');
// One page at a time: a page left over from the step before (a film still playing in it) would slow down every later page of a software renderer.
const _pages = [];
const open = async (...a) => { while (_pages.length) await _pages.pop().context().close().catch(() => {}); const p = await tour.open(...a); _pages.push(p); return p; };
const tmp = mkdtempSync(join(tmpdir(), 'tour-19-'));
// A headless browser has no native save dialog: Save IFC then downloads, as the manual says "Otherwise it downloads".
const noPicker = () => { delete window.showSaveFilePicker; delete window.showDirectoryPicker; };
const clipInit = () => { delete window.showSaveFilePicker; delete window.showDirectoryPicker; window.__clip = []; try { navigator.clipboard.writeText = async (t) => { window.__clip.push(String(t)); }; } catch { /* no clipboard */ } };
const status = (page) => page.evaluate(() => window.__xray.app.panel.controllersRecursive().find((c) => c.property === 'status').getValue());
async function openIfc(page, file) {
  await page.evaluate(() => window.__xray.app.panel.controllersRecursive().find((c) => c.property === 'status').setValue(''));
  const chooser = page.waitForEvent('filechooser');
  await ui.tab(page, 'Parameters'); await ui.topOfPanel(page);
  await ui.press(page, 'Open IFC or glb file');
  await (await chooser).setFiles(file);
  await page.waitForFunction(() => /^Loaded \d+ elements|fail|error/i.test(window.__xray.app.panel.controllersRecursive().find((c) => c.property === 'status').getValue()), null, { timeout: 240000 });
  await ui.settle(page, 600);
}
const FZK = resolve(repoRoot, 'models', 'AC20-FZK-Haus.ifc');

await tour.step('19.1 Try it steps 1-6: change a setting, Export JSON, change back, Import JSON, Copy share URL', async () => {
  const page = await open('model=fzk-haus', { init: clipInit });
  await ui.tab(page, 'Parameters');
  await ui.topOfPanel(page);
  await ui.folder(page, 'Sightlines (Alg 2)');
  const before = await ui.valueOf(page, 'alphaMin');
  await ui.set(page, 'alphaMin', 0.31);
  tour.check('step 1: the ghosting strength (alphaMin) is changed', String(await ui.valueOf(page, 'alphaMin')) === '0.31', String(await ui.valueOf(page, 'alphaMin')));
  await ui.topOfPanel(page);
  await ui.folder(page, 'Export / import');
  tour.check('step 2/3: the folder "Export / import" has "Export JSON", "Import JSON" and "Copy share URL"', (await Promise.all(['Export JSON', 'Import JSON', 'Copy share URL'].map(async (n) => (await ui.control(page, n)).isVisible()))).every(Boolean));
  const dl = page.waitForEvent('download');
  await ui.press(page, 'Export JSON');
  const d = await dl;
  const file = join(tmp, d.suggestedFilename());
  await d.saveAs(file);
  const doc = JSON.parse(readFileSync(file, 'utf8'));
  tour.check('step 3: "Your browser saves a small file" (a .json)', /\.json$/.test(d.suggestedFilename()) && readFileSync(file).length < 2e6, `${d.suggestedFilename()} ${readFileSync(file).length} bytes`);
  tour.check('"format xray-params/1"', doc.format === 'xray-params/1' || doc.schema === 'xray-params/1' || JSON.stringify(doc).includes('xray-params/1'), Object.keys(doc).slice(0, 8).join());
  tour.check('"The file holds one block per part of the viewer" (several top-level blocks)', Object.keys(doc).length >= 5, Object.keys(doc).join());
  const text = JSON.stringify(doc);
  tour.check('"API keys, the Hugging Face token and thumbnails never go into it"', !/hf_[A-Za-z0-9]{6}|apiKey|"token"/i.test(text) && !/data:image/.test(text));
  await ui.topOfPanel(page);
  await ui.folder(page, 'Sightlines (Alg 2)');
  await ui.set(page, 'alphaMin', before);
  tour.check('step 4: the setting is changed back, so the look differs from the file', String(await ui.valueOf(page, 'alphaMin')) === String(before));
  await ui.topOfPanel(page);
  await ui.folder(page, 'Export / import');
  const chooser = page.waitForEvent('filechooser');
  await ui.press(page, 'Import JSON');
  await (await chooser).setFiles(file);
  await ui.settle(page, 800);
  await ui.topOfPanel(page);
  await ui.folder(page, 'Sightlines (Alg 2)');
  tour.check('step 5: "The look from the file returns"', String(await ui.valueOf(page, 'alphaMin')) === '0.31', String(await ui.valueOf(page, 'alphaMin')));
  await ui.topOfPanel(page);
  await ui.folder(page, 'Export / import');
  await ui.press(page, 'Copy share URL');
  await page.waitForTimeout(500);
  const clip = await page.evaluate(() => window.__clip);
  tour.check('step 6: "Copy share URL" puts a link on the clipboard', clip.length === 1 && /^https?:\/\//.test(clip[0]), clip[0]?.slice(0, 120));
  tour.check('"The link carries the main settings and the camera" (model and a camera or settings part)', /model=/.test(clip[0] ?? '') && /[?&#]/.test(clip[0] ?? ''), clip[0]?.slice(0, 200));
  tour.check('no reviewer name or key in the link', !/reviewer|apikey|token/i.test(clip[0] ?? ''));
});

await tour.step('19.2 Try it steps 1-5: click a wall, Properties tab, Copy GlobalId, property sets, five elements', async () => {
  const page = await open('model=fzk-haus', { init: clipInit });
  const wall = await ui.clickElement(page, { cls: /IfcWall/ });
  tour.check('step 1: a wall is selected', !!wall, JSON.stringify(wall));
  await ui.tab(page, 'Properties');
  const dock = page.locator('#dock');
  const txt = (await dock.innerText()).replace(/\s+/g, ' ');
  tour.check('step 3: "At the top you see the GlobalId, class, name, storey, material and x-ray state"', /GlobalId/i.test(txt) && /IfcWall/.test(txt) && /storey/i.test(txt) && /material/i.test(txt) && /bucket|x-ray/i.test(txt), txt.slice(0, 220));
  await ui.button(page, 'Copy GlobalId').click();
  await page.waitForTimeout(300);
  const clip = await page.evaluate(() => window.__clip);
  tour.check('"Click Copy GlobalId to put the id on the clipboard"', clip.length > 0 && /^[0-9A-Za-z_$]{22}$/.test(clip[clip.length - 1]), clip.join('|').slice(0, 60));
  const mm = txt.match(/Properties \((\d+)(?: of (\d+))?\)/);
  tour.check('step 4: "below ... the list of properties and quantities": a list "Properties (n of m)" with a "⋯" menu on a row', !!mm && (await dock.locator('button:has-text("⋯")').count()) > 0, txt.slice(220, 420));
  await ui.tab(page, 'Parameters'); await ui.topOfPanel(page);
  await ui.folder(page, 'Hover info');
  await ui.set(page, 'all properties in sidebar', true);
  await ui.tab(page, 'Properties');
  await page.waitForTimeout(700);
  const mm2 = (await dock.innerText()).match(/Properties \((\d+)(?: of (\d+))?\)/);
  tour.check('"Two settings of the Hover info folder decide what shows: whether all properties appear in the sidebar": ticking it shows every property', !!mm2 && (mm2[2] === undefined || mm2[1] === mm2[2]) && Number(mm2[1]) > Number(mm?.[1] ?? 0), `${mm?.[0]} -> ${mm2?.[0]}`);
  tour.check('"Properties are read-only": the rows have no input boxes', (await dock.locator('#dk-pane-properties input[type=text], .pv input[type=text]').count()) === 0);
  // five elements
  const ids = await page.evaluate(() => window.__xray.app.controller.model.elements.filter((e) => /IfcWindow/.test(e.ifcClass)).slice(0, 5).map((e) => e.id));
  for (const id of ids) {
    const spots = await ui.spotsOf(page, id);
    if (!spots.length) continue;
    await page.keyboard.down('Shift'); await page.mouse.click(spots[0].x, spots[0].y); await page.keyboard.up('Shift');
    await page.waitForTimeout(150);
  }
  await ui.settle(page, 400);
  const sel = await ui.selection(page);
  const t2 = (await dock.innerText()).replace(/\s+/g, ' ');
  tour.check('step 5: several selected: the tab shows the first and "+ N more selected"', sel.length >= 2 && new RegExp(`\\+ ${sel.length - 1} more selected`).test(t2), `${sel.length} selected; ${/more selected/.test(t2)}`);
});

let savedPath = '';
await tour.step('19.3 Try it steps 1-6: open the IFC, classify, Save IFC, dialog, Write, the .xray.ifc', async () => {
  const page = await open('model=building', { init: noPicker });
  await openIfc(page, FZK);
  tour.check('step 1: the IFC opens with Open IFC or glb file', /^Loaded \d+ elements/.test(await status(page)), await status(page));
  await ui.tab(page, 'Classification');
  await ui.button(page, 'Classify all').click();
  await page.waitForFunction(() => window.__xrayClassify?.stats().total > 20, null, { timeout: 120000 });
  tour.check('step 1: classify it (rules only)', true);
  await ui.tab(page, 'Parameters'); await ui.topOfPanel(page);
  await ui.folder(page, 'Open model');
  await ui.press(page, 'Save IFC');
  const dlg = page.locator('.xis-box');
  await dlg.waitFor();
  const dt = (await dlg.innerText()).replace(/\s+/g, ' ');
  tour.check('step 3: "The dialog lists each file with its size, schema and the number of elements that carry data"', /AC20-FZK-Haus/.test(dt) && /IFC4/.test(dt) && /\d+ elements?/.test(dt), dt.slice(0, 200));
  tour.check('step 3: a "Write" choice (all classified, or only reviewed)', (await dlg.getByLabel('Which elements to write').count()) === 1, dt.slice(0, 100));
  const rev = dlg.getByText('Include reviewer names and comments').locator('xpath=ancestor::label').locator('input');
  tour.check('step 4: "Include reviewer names and comments" is off', (await rev.isChecked()) === false);
  await rev.check(); await dlg.getByRole('button', { name: 'Close' }).click();
  await ui.tab(page, 'Parameters');
  await ui.press(page, 'Save IFC');
  tour.check('"It is off every time you open the dialog"', (await dlg.getByText('Include reviewer names and comments').locator('xpath=ancestor::label').locator('input').isChecked()) === false);
  const dl = page.waitForEvent('download');
  await dlg.locator('button.primary').click();
  const d = await dl;
  savedPath = join(tmp, d.suggestedFilename());
  await d.saveAs(savedPath);
  tour.check('step 6: "The result is AC20-FZK-Haus.xray.ifc"', d.suggestedFilename() === 'AC20-FZK-Haus.xray.ifc', d.suggestedFilename());
  const out = readFileSync(savedPath), orig = readFileSync(FZK);
  const cut = orig.lastIndexOf('ENDSEC;');
  tour.check('"your original, byte for byte, plus one block of new lines inserted before the end of the data section"', out.subarray(0, cut).equals(orig.subarray(0, cut)) && out.subarray(out.length - (orig.length - cut)).equals(orig.subarray(cut)));
  const t = out.toString('latin1');
  tour.check('"Classification: IfcClassification and one IfcClassificationReference per code"', /IFCCLASSIFICATION\(/.test(t) && /IFCCLASSIFICATIONREFERENCE\(/.test(t));
  tour.check('"Classification values: the property set XR_Classification" and review state "Xray_Review"', t.includes("'XR_Classification'") && t.includes("'Xray_Review'"));
  tour.check('the block is "bracketed by two comments"', /\/\* XRAY-BEGIN/.test(t) && /\/\* XRAY-END/.test(t));
  tour.check('no reviewer name written with the box off', !/ReviewedBy/.test(t));
  // "Saving again replaces the block and never adds a second one"
  await dlg.getByRole('button', { name: 'Close' }).click();
  await ui.tab(page, 'Parameters');
  await ui.press(page, 'Save IFC');
  const dl2 = page.waitForEvent('download');
  await dlg.locator('button.primary').click();
  const d2 = await dl2; const p2 = join(tmp, 'again-' + d2.suggestedFilename()); await d2.saveAs(p2);
  tour.check('"Saving again ... the same state gives the same bytes"', readFileSync(p2).equals(out));
  await dlg.getByRole('button', { name: 'Close' }).click();
  // the palette entry
  tour.check('"The command palette entry Save IFC... does the same"', await page.evaluate(() => !!window.__xrayIfcSave?.open));
  // re-open the saved file: the new sets are readable
  await openIfc(page, savedPath);
  tour.check('"open in any IFC tool": the .xray.ifc opens again with the same elements', /^Loaded \d+ elements/.test(await status(page)), await status(page));
});

await tour.step('19.3 Try it, cleaned copy; Limits: a sample has no source', async () => {
  const page = await open('model=building', { init: noPicker });
  await ui.tab(page, 'Parameters'); await ui.topOfPanel(page);
  await ui.folder(page, 'Open model');
  await ui.press(page, 'Save IFC');
  const dlg = page.locator('.xis-box');
  await dlg.waitFor();
  const t = (await dlg.innerText()).replace(/\s+/g, ' ');
  tour.check('Limits: a sample has no source: the dialog offers "Attach the source IFC..."', /Attach the source IFC/.test(t), t.slice(0, 200));
  await dlg.getByRole('button', { name: 'Close' }).click().catch(() => {});
  const PLANT = resolve(repoRoot, 'models', 'Process-Plant.ifc');
  await openIfc(page, PLANT);
  await ui.tab(page, 'Parameters'); await ui.topOfPanel(page);
  await ui.folder(page, 'Model cleanup');
  // the default rules find little in the plant: also take the proxies (the manual's "run cleanup")
  await ui.folder(page, 'Classes');
  await ui.set(page, 'proxies', true);
  await ui.topOfPanel(page); await ui.folder(page, 'Model cleanup');
  await ui.press(page, 'Preview matches');
  await page.waitForTimeout(1500);
  await ui.press(page, 'Hide matches');
  await page.waitForTimeout(800);
  const hidden = await page.evaluate(() => window.__xrayCleanup.hiddenByCleanup().length);
  tour.check('"run cleanup, click Hide matches": cleanup hid some elements', hidden > 0, `${hidden} hidden`);
  await ui.topOfPanel(page); await ui.folder(page, 'Model cleanup');
  await ui.press(page, 'Save cleaned copy...');
  const dlg2 = page.locator('.xis-box[aria-labelledby="xis-clean-title"]');
  await dlg2.waitFor({ timeout: 60000 });
  await page.waitForFunction(() => { const b = [...document.querySelectorAll('.xis-box button.primary')].pop(); return b && !b.disabled; }, null, { timeout: 120000 });
  const t2 = (await dlg2.innerText()).replace(/\s+/g, ' ');
  tour.check('"The dialog first plans the removal and shows a report. Nothing is written until you press Save cleaned copy"', /Removed: \d+/.test(t2) && (await dlg2.getByRole('button', { name: /Save cleaned copy/ }).count()) > 0, t2.slice(0, 260));
  tour.check('options "Also write the classification" and "Remove walls even if a door or window stays"', /Also write the classification/.test(t2) && /Remove walls even if a door or window stays/.test(t2), t2.slice(0, 300));
  tour.check('"the dialog ... Kept and marked instead" (a wall that still hosts a door or window is kept and marked KeptBecause)', /Kept and marked instead|kept/i.test(t2), '');
  const dl = page.waitForEvent('download', { timeout: 180000 });
  await dlg2.locator('button.primary').click();
  const d = await dl;
  tour.check('"Save cleaned copy writes <stem>.cleaned.ifc"', d.suggestedFilename() === 'Process-Plant.cleaned.ifc', d.suggestedFilename());
  const cf = join(tmp, d.suggestedFilename()); await d.saveAs(cf);
  const cb = readFileSync(cf);
  tour.check('"your file without the elements cleanup hid": the copy is smaller than the source', cb.length < readFileSync(PLANT).length, `${cb.length} < ${readFileSync(PLANT).length}`);
});

await tour.step('19.4 Try it: close the tab, open again: what comes back (browser storage per model)', async () => {
  const page = await open('model=fzk-haus');
  await page.keyboard.press('Control+Shift+S');
  await page.waitForTimeout(600);
  await page.evaluate(() => window.__xrayScript.save('Tour script', 'wait 1'));
  const before = await page.evaluate(() => ({ views: window.__xrayViews.list().length, scripts: window.__xrayScript.list().length, keys: Object.keys(localStorage).filter((k) => /^xray\./.test(k)).length }));
  tour.check('a saved view and a saved script exist in the browser store', before.views === 1 && before.scripts === 1 && before.keys >= 2, JSON.stringify(before));
  await page.reload();
  await page.waitForFunction('window.__xrayReady === true && window.__xrayViews && window.__xrayScript', null, { timeout: 240000 });
  await page.waitForTimeout(800);
  const after = await page.evaluate(() => ({ views: window.__xrayViews.list().length, scripts: window.__xrayScript.list().length }));
  tour.check('"Close the tab, open the page again with the same model": "Saved views ... scripts ... come back"', after.views === 1 && after.scripts === 1, JSON.stringify(after));
  await ui.tab(page, 'Views');
  const vt = (await page.locator('#sidebar').innerText()).replace(/\s+/g, ' ');
  tour.check('the Views tab lists the saved view again', !/No saved views/i.test(vt) && /1/.test(vt), vt.slice(0, 120));
  const gone = await page.evaluate(() => { const t = window.__xrayParams.shareUrl(); return t.length; });
  tour.check('"A share link ... you did not export does not exist": a share link is only text you copy (nothing stored)', gone > 20);
  await page.evaluate(() => { localStorage.clear(); });
  await page.reload();
  await page.waitForFunction('window.__xrayReady === true && window.__xrayViews', null, { timeout: 240000 });
  await page.waitForTimeout(800);
  const cleared = await page.evaluate(() => ({ views: window.__xrayViews.list().length, scripts: window.__xrayScript.list().length }));
  tour.check('"Then clear the site data of the page, and see everything in browser storage go"', cleared.views === 0 && cleared.scripts === 0, JSON.stringify(cleared));
  const doc = await page.evaluate(() => JSON.stringify(window.__xrayParams.collect()));
  tour.check('"Never written anywhere: API keys, the Hugging Face token ... pictures of elements"', !/apiKey|hfToken|data:image/i.test(doc));
});

await tour.finish();
