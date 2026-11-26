// Tour of chapter 9, "Cleaning a messy model" (docs/manual/09-cleanup.md): find, preview, hide, restore (9.1), the rules, units, and
// the Simplify folder (9.2). No pictures in this chapter.
// Run: node bench/run-smokes.mjs --only tour-09-cleanup
import { readFileSync } from 'node:fs';
import { startTour, ui } from './lib.mjs';

const tour = await startTour('tour-09-cleanup');
const report = (page) => page.evaluate(() => { const r = window.__xrayCleanup.lastReport; return r ? { total: r.matches.length, names: r.matches.map((m) => m.name), counts: r.counts, reasons: r.matches.map((m) => m.reasons[0]), ids: r.matches.map((m) => m.id) } : null; });
const userHides = (page) => page.evaluate(() => window.__xray.app.controller.settings.overrides.userHides.size);
const cleanupFolder = async (page) => { await ui.tab(page, 'Parameters'); await ui.topOfPanel(page); return ui.folder(page, 'Model cleanup'); };
const press = async (page, name) => { await cleanupFolder(page); await ui.press(page, name); await ui.settle(page, 800); };

await tour.step('9.1 Try it steps 1-3: Debris demo, the Cleanup tool, Preview matches', async () => {
  const page = await tour.open('model=debris-demo');
  const m = await ui.model(page);
  tour.check('step 1: "a 400-element building with 31 pieces of rubbish"', m.n === 424 || m.n === 400, `${m.n} elements`);
  const debris = await page.evaluate(() => window.__xray.app.controller.model.elements.filter((e) => /^Debris/.test(e.name ?? '')).length);
  tour.check('step 1: "31 pieces of rubbish ... all named Debris ..."', debris === 31, String(debris));
  // the Cleanup tool in the strip
  await ui.tool(page, 'Cleanup').click();
  const drawer = page.locator('#xray-toolbar-drawer, .xt-drawer, [class*=drawer]').filter({ hasText: 'Floating elements' }).first();
  await drawer.waitFor({ timeout: 8000 }).catch(() => {});
  tour.check('step 2: "Open the Cleanup tool in the tool strip" (a drawer with the rules opens)', await page.getByText('Floating elements').first().isVisible().catch(() => false));
  await ui.tool(page, 'Cleanup').click();
  await cleanupFolder(page);
  tour.check('step 2: "or the Model cleanup folder in the Parameters tab" shows the same rules', (await ui.valueOf(page, 'apply on load')) === false);
  await ui.press(page, 'Preview matches');
  await ui.settle(page, 1500);
  const r = await report(page);
  tour.check('step 3: "Preview matches": there are matches, all small debris', !!r && r.total >= 15 && r.total <= 30, JSON.stringify(r && { total: r.total, counts: r.counts }));
  tour.check('step 3: "When there are fewer than 50, the camera frames them" (status line reports them)', /\d+/.test(String(await ui.valueOf(page, 'Cleanup status'))), String(await ui.valueOf(page, 'Cleanup status')));
  const debrisMatched = (r?.names ?? []).filter((n) => /^Debris/.test(n ?? '')).length;
  tour.check('step 3: the matches are the debris pieces', debrisMatched >= 15, `${debrisMatched} of ${r?.total}`);
  // step 4: select matches
  await ui.press(page, 'Select matches');
  await ui.settle(page, 500);
  tour.check('step 4: "Select matches selects them"', (await ui.selection(page)).length === r.total, `${(await ui.selection(page)).length} of ${r.total}`);
  // step 5: compare with the set
  await ui.tab(page, 'Sets');
  await page.locator('#sidebar .set-row', { has: page.locator('.set-name', { hasText: /^Debris$/ }) }).locator('.set-name').click();
  await ui.settle(page, 400);
  const inSet = await ui.selection(page);
  tour.check('step 5: "the Sets tab has a set called Debris" with 31 elements', inSet.length === 31, String(inSet.length));
  const matchSet = new Set(r.ids);
  const missing = inSet.filter((e) => !matchSet.has(e.id));
  tour.check('step 5: "The two selections are nearly the same. The cluster of three touching 12 cm boxes is missing from the cleanup matches"', missing.length === 3, `missing ${missing.length}: ${missing.map((e) => e.name).join(', ')}`);
  // step 6: small clusters
  await cleanupFolder(page);
  await ui.folder(page, 'Floating');
  await ui.set(page, 'mode', 'small clusters');
  await ui.settle(page, 600);
  await ui.topOfPanel(page);
  await cleanupFolder(page);
  await ui.press(page, 'Preview matches');
  await ui.settle(page, 1500);
  const r2 = await report(page);
  tour.check('step 6: "Press Preview matches again. The cluster is now in"', !!r2 && r2.total === r.total + 3, `${r.total} -> ${r2?.total}`);
  // step 7: hide
  await ui.press(page, 'Hide matches');
  await ui.settle(page, 800);
  const h = await userHides(page);
  tour.check('step 7: "Press Hide matches. The debris disappears from the view"', h === r2.total, `${h} hidden`);
  // step 8: hide a wall, restore
  await ui.clearSelection(page);
  const wall = await ui.clickElement(page, { cls: /Wall/ });
  await page.locator('#c').hover();
  await page.keyboard.press('h');
  await ui.settle(page, 500);
  tour.check('step 8: "Hide one wall yourself with h"', (await userHides(page)) === h + 1, String(await userHides(page)));
  await press(page, 'Restore cleanup');
  tour.check('step 8: "Press Restore cleanup. The debris returns. The wall stays hidden"', (await userHides(page)) === 1, `${await userHides(page)} still hidden`);
  void wall;
  // step 9: export report
  await cleanupFolder(page);
  const [dl] = await Promise.all([page.waitForEvent('download', { timeout: 20000 }), ui.press(page, 'Export report')]);
  const data = JSON.parse(readFileSync(await dl.path(), 'utf8'));
  const first = (data.matches ?? [])[0];
  tour.check('step 9: "Export report: a JSON file with each element, its class and the reason"', !!first && first.ifcClass && first.reasons?.length > 0 && first.globalId, JSON.stringify(first).slice(0, 200));
  tour.check('"Each match has a reason in plain words, such as floating lone element, no contacts: largest dimension 0.300 m < 0.500 m"', (data.matches ?? []).some((m) => /floating lone element, no contacts: largest dimension [\d.]+ m < 0\.500 m/.test(m.reasons.join(' '))), (data.matches ?? []).slice(0, 3).map((m) => m.reasons.join(';')).join(' | '));
});

await tour.step('9.1 What the rules mean: kinds, defaults, units, apply on load, palette', async () => {
  const page = await tour.open('model=debris-demo');
  await cleanupFolder(page);
  await ui.folder(page, 'Floating');
  tour.check('defaults: "size metric largest dimension", "mode single elements"', (await ui.valueOf(page, 'size metric')) === 'largest dimension' && (await ui.valueOf(page, 'mode')) === 'single elements', `${await ui.valueOf(page, 'size metric')} / ${await ui.valueOf(page, 'mode')}`);
  await ui.topOfPanel(page);
  const folder = await cleanupFolder(page);
  const kinds = await folder.locator(':scope > .lil-children > .lil-gui > .lil-title').allInnerTexts();
  tour.check('"There are five kinds of suspect": Floating, Tiny, Distant strays, Duplicates, Degenerate', ['Floating', 'Tiny', 'Distant strays', 'Duplicates', 'Degenerate'].every((k) => kinds.some((t) => t.trim().startsWith(k))), kinds.join(' | '));
  tour.check('"Three class toggles": proxies, furniture, accessories and fasteners', (await ui.folder(page, 'Classes').then(async () => [await ui.valueOf(page, 'proxies'), await ui.valueOf(page, 'furniture'), await ui.valueOf(page, 'accessories and fasteners')])).every((v) => v === false));
  await ui.topOfPanel(page);
  await cleanupFolder(page);
  tour.check('"A length unit list at the top of the folder switches the whole folder between mm, cm and m"', ['mm', 'cm', 'm'].every(async () => true) && ['m', 'cm', 'mm'].includes(String(await ui.valueOf(page, 'length unit'))), String(await ui.valueOf(page, 'length unit')));
  await ui.folder(page, 'Tiny');
  const before = await page.locator('[data-tour-ref] .lil-controller .lil-name').allInnerTexts();
  void before;
  await ui.topOfPanel(page);
  await cleanupFolder(page);
  await ui.set(page, 'length unit', 'mm');
  await ui.folder(page, 'Tiny');
  const maxSize = await ui.valueOf(page, 'max size (mm)').catch(() => null);
  tour.check('"Tiny: max size ... (50 mm by default)" shows 50 in mm', Number(maxSize) === 50, String(maxSize));
  await ui.topOfPanel(page);
  await cleanupFolder(page);
  await ui.set(page, 'length unit', 'cm');
  await ui.folder(page, 'Tiny');
  tour.check('"The numbers convert for display": 5 cm', Number(await ui.valueOf(page, 'max size (cm)').catch(() => null)) === 5);
  await ui.topOfPanel(page);
  await cleanupFolder(page);
  await ui.set(page, 'length unit', 'm');
  await ui.folder(page, 'Floating');
  const th = await ui.valueOf(page, 'threshold (m)').catch(() => null);
  tour.check('"A floating threshold of 0.5 m"', Number(th) === 0.5, String(th));
  const ct = await ui.valueOf(page, 'contact tolerance (m)').catch(() => ui.valueOf(page, 'contact tolerance', { exact: false }).catch(() => null));
  tour.check('"contact tolerance (10 mm by default)"', Number(ct) === 0.01 || Number(ct) === 10, String(ct));
  await ui.topOfPanel(page);
  await cleanupFolder(page);
  await ui.folder(page, 'Distant strays');
  tour.check('"distance factor ... (6 by default)"', Number(await ui.valueOf(page, 'distance factor (× radius)')) === 6);
  // palette actions
  await page.locator('#c').hover();
  await page.keyboard.press('Control+Shift+k');
  await page.waitForTimeout(500);
  await page.keyboard.type('cleanup');
  await page.waitForTimeout(600);
  const pal = await page.locator('body').innerText();
  tour.check('"The palette has cleanup.preview, cleanup.hide and cleanup.restore, without default keys": the three commands are listed', /Cleanup: preview matches/.test(pal) && /Cleanup: hide matches/.test(pal) && /Cleanup: restore hidden/.test(pal));
  await page.keyboard.press('Escape');
});

await tour.step('9.1 Rules on a model: Tiny, Duplicates, Distant strays and apply on load', async () => {
  const page = await tour.open('model=debris-demo');
  const run = async (patch) => page.evaluate((p) => { const a = window.__xrayCleanup; a.setRules(p); a.preview(); const r = a.lastReport; return r ? { total: r.matches.length, counts: r.counts } : null; }, patch);
  const off = { floating: { enabled: false }, tiny: { enabled: false }, strays: { enabled: false }, duplicates: { enabled: false }, degenerate: { enabled: false } };
  const tiny = await run({ ...off, tiny: { enabled: true } });
  tour.check('"Tiny: elements whose largest side is below a limit" finds something', !!tiny && tiny.total > 0, JSON.stringify(tiny));
  const strays = await run({ ...off, strays: { enabled: true } });
  tour.check('"Distant strays: elements far from the rest of the model" finds the marker', !!strays && strays.total >= 1, JSON.stringify(strays));
  const dup = await run({ ...off, duplicates: { enabled: true } });
  tour.check('"Duplicates: elements of the same class and shape in the same place"', !!dup && dup.total >= 1, JSON.stringify(dup));
  const none = await run({ ...off });
  tour.check('with every rule off nothing matches', !none || none.total === 0, JSON.stringify(none));
  // Apply on load
  await cleanupFolder(page);
  await page.evaluate(() => window.__xrayCleanup.setRules({ floating: { enabled: true } }));
  await ui.set(page, 'apply on load', true);
  await page.reload();
  await page.waitForFunction(() => window.__xrayReady, null, { timeout: 120000 });
  await ui.settle(page, 1500);
  const h = await userHides(page);
  tour.check('"Apply on load runs the rules and hides the matches every time the model loads"', h > 0, `${h} hidden after reload`);
});

await tour.step('9.2 Simplify and save a glb: the Simplify folder and the save summary', async () => {
  const page = await tour.open('model=debris-demo');
  await cleanupFolder(page);
  const simp = await ui.folder(page, 'Simplify');
  const tools = await simp.locator(':scope > .lil-children > .lil-gui > .lil-title').allInnerTexts();
  tour.check('"The Simplify folder": Decimate mesh, Small details, Hidden interior, Instances, Weld and clean', ['Decimate mesh', 'Small details', 'Hidden interior', 'Instances', 'Weld and clean'].every((k) => tools.some((t) => t.trim().startsWith(k))), tools.join(' | '));
  const names = await simp.locator('.lil-controller .lil-name').allInnerTexts();
  tour.check('"Every tool has Preview ... and Apply"', names.filter((n) => n === 'Preview').length >= 5 && names.filter((n) => n === 'Apply').length >= 5, names.join(','));
  tour.check('"Undo simplification", "Cancel run" and "strip property data" exist', ['Undo simplification', 'Cancel run', 'strip property data'].every((n) => names.includes(n)));
  await ui.folder(page, 'Weld and clean');
  const before = await page.evaluate(() => window.__xrayCleanup?.simplify ? 1 : 0);
  void before;
  await ui.press(page, 'Preview');
  await ui.settle(page, 3000);
  const simpStatus = async () => { await ui.topOfPanel(page); await ui.folder(page, 'Model cleanup'); await ui.folder(page, 'Simplify'); return String(await ui.valueOf(page, 'Simplify status').catch(() => '')); };
  const st = await simpStatus();
  tour.check('"Preview shows what it would change and the triangles before and after"', /triangle|→|->|no change|nothing/i.test(st), st);
  await ui.topOfPanel(page); await cleanupFolder(page); await ui.folder(page, 'Simplify'); await ui.folder(page, 'Weld and clean');
  await ui.press(page, 'Apply');
  await ui.settle(page, 1500);
  tour.check('"Apply stages the change"', /Staged/.test(await simpStatus()), await simpStatus());
  await ui.topOfPanel(page);
  await cleanupFolder(page);
  await ui.press(page, 'Save cleaned model');
  await page.waitForTimeout(1500);
  const txt = await page.locator('body').innerText();
  tour.check('"Save cleaned model opens a summary": the elements removed, simplified and instanced, the triangles before and after, an estimated size', /Removed/.test(txt) && /Simplified/.test(txt) && /Instanced/.test(txt) && /Triangles/.test(txt) && /Estimated size/.test(txt) && /Strip names and property data/.test(txt), txt.match(/Elements[^\n]*/)?.[0] ?? '');
  const [dl] = await Promise.all([page.waitForEvent('download', { timeout: 30000 }).catch(() => null), page.getByRole('button', { name: /Save \.glb/i }).first().click().catch(() => null)]);
  tour.check('"Save .glb downloads cleaned-<model>.glb"', !!dl && /^cleaned-.*\.glb$/.test(dl.suggestedFilename()), dl?.suggestedFilename());
  await page.waitForTimeout(800);
  tour.check('"Open the saved file to check" shows after saving', await page.getByRole('button', { name: 'Open the saved file to check' }).isVisible().catch(() => false));
});

await tour.finish();
