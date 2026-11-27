// Tour of chapter 6, "Imaging, map and cinematic effects" (docs/manual/06-imaging.md): the Try it of 6.1 (Radiograph, MRI, palettes), 6.2 (the map under the model,
// with the tile server answered offline) and 6.3 (bloom, edge glow, Glow mode, the presentation preset). Picture: `imaging-three-looks`.
// Run: node bench/run-smokes.mjs --only tour-06-imaging
import { resolve } from 'node:path';
import { repoRoot, startTour, ui } from './lib.mjs';

const tour = await startTour('tour-06-imaging');
const img = (page) => page.evaluate(() => ({ style: window.__xrayImaging.config.style, palette: window.__xrayImaging.config.palette }));
/** Colour of an empty canvas spot near the left edge of the stage, below the top bar. */
const ground = async (page) => { const c = await page.locator('#c').boundingBox(); return ui.pixel(page, c.x + 90, c.y + c.height - 70); };
const dark = (c) => c[0] < 60 && c[1] < 60 && c[2] < 60;
const TILE = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==', 'base64');

await tour.step('6.1 Try it steps 1-6: window, Radiograph, orbit, M, palette, M', async () => {
  const page = await tour.open('model=fzk-haus');
  const win = await ui.clickElement(page, { cls: 'IfcWindow' });
  tour.check('step 1: "Open FZK-Haus. Click a window."', !!win, JSON.stringify(win));
  await page.keyboard.press('f');
  await page.waitForTimeout(1500); await ui.settle(page, 800);
  await ui.park(page);
  const bgStd = await ground(page);
  await ui.mode(page, 'Radiograph');
  await ui.settle(page, 1500);
  const r = await img(page);
  const bgRad = await ground(page);
  tour.check('step 2: "Click Radiograph in the top bar ... turns the picture into a black-background x-ray"', r.style === 'radiograph' && dark(bgRad), `style ${r.style}, ground ${bgRad} (standard look ${bgStd})`);
  const cam0 = await ui.cam(page);
  const box = await page.locator('#c').boundingBox();
  await page.mouse.move(box.x + box.width * 0.5, box.y + box.height * 0.6); await page.mouse.down();
  await page.mouse.move(box.x + box.width * 0.5 + 120, box.y + box.height * 0.6, { steps: 6 }); await page.mouse.up();
  await ui.settle(page, 1200);
  tour.check('step 3: "Orbit." The Radiograph look follows the camera', Math.hypot(...(await ui.cam(page)).p.map((v, i) => v - cam0.p[i])) > 0.2 && (await img(page)).style === 'radiograph');
  await page.keyboard.press('m');
  await ui.settle(page, 1500);
  tour.check('step 4: "Press M. The look changes to MRI"', (await img(page)).style === 'mri', JSON.stringify(await img(page)));
  await ui.tab(page, 'Parameters'); await ui.topOfPanel(page);
  const styles = await (await ui.control(page, 'Render style')).locator('select option').allInnerTexts();
  tour.check('step 5: "At the top is a Render style list (Standard, Radiograph, MRI)"', ['Standard', 'Radiograph', 'MRI'].every((s) => styles.includes(s)), styles.join());
  tour.check('step 5: "below it an Imaging folder"', await page.locator('.lil-gui:not(.lil-root) > .lil-title', { hasText: 'Imaging' }).first().isVisible());
  await ui.folder(page, 'Imaging');
  const pal = await (await ui.control(page, 'palette')).locator('select option').allInnerTexts();
  tour.check('step 5: palette offers classic, negative and fluoro', ['classic', 'negative', 'fluoro'].every((s) => pal.includes(s)), pal.join());
  await ui.set(page, 'Render style', 'Radiograph').catch(() => {});
  await ui.topOfPanel(page); await ui.folder(page, 'Imaging');
  await ui.set(page, 'palette', 'negative');
  await page.locator('#c').hover(); await ui.settle(page, 1500);
  const neg = await ground(page);
  tour.check('step 5: "negative (white ground, dark ink, deep blue bone)"', neg[0] > 200 && neg[1] > 200 && neg[2] > 200, `ground ${neg}`);
  await ui.topOfPanel(page); await ui.folder(page, 'Imaging');
  await ui.set(page, 'palette', 'fluoro');
  await page.locator('#c').hover(); await ui.settle(page, 1500);
  const fl = await ground(page);
  tour.check('step 5: "fluoro (dark blue-green ground, green tissue)"', fl[0] < 60 && fl[1] >= fl[0] && fl[2] >= fl[0] && (fl[1] > 5 || fl[2] > 5), `ground ${fl}`);
  await ui.topOfPanel(page); await ui.folder(page, 'Imaging');
  await ui.set(page, 'palette', 'classic');
  await page.locator('#c').hover(); await ui.settle(page, 1200);
  tour.check('step 5: "classic (black ground, light blue-white tissue)"', dark(await ground(page)), `ground ${await ground(page)}`);
  await page.keyboard.press('m'); await ui.settle(page, 1500);
  const back = await img(page);
  tour.check('step 6: "Press M again to go back to Standard."', back.style === 'standard', JSON.stringify(back));
});

await tour.step('6.1 picture: the same view in Standard, Radiograph (classic) and MRI', async () => {
  const page = await tour.open('model=fzk-haus');
  const win = await ui.clickElement(page, { cls: 'IfcWindow' });
  await page.keyboard.press('f');
  await page.waitForTimeout(1500); await ui.settle(page, 800);
  await ui.park(page);
  await page.keyboard.press('Shift+0'); await ui.settle(page, 1500);
  const std = await tour.shot(page, { element: '#stage' });
  await ui.mode(page, 'Radiograph'); await ui.park(page); await ui.settle(page, 2000);
  const rad = await tour.shot(page, { element: '#stage' });
  await page.keyboard.press('m'); await ui.park(page); await ui.settle(page, 2000);
  const mri = await tour.shot(page, { element: '#stage' });
  tour.check('the three looks of the picture were taken on one selection', !!win && (await img(page)).style === 'mri');
  await tour.pictureRow('imaging-three-looks', [{ buf: std, label: 'Standard' }, { buf: rad, label: 'Radiograph (classic)' }, { buf: mri, label: 'MRI' }]);
});

await tour.step('6.2 Try it steps 1-5: Map folder, show map under model, accept, provider, opacity and radius', async () => {
  const tiles = [];
  const route = (r) => {
    const u = r.request().url();
    if (/^(http:\/\/127\.0\.0\.1|data:|blob:)/.test(u)) return r.continue();
    tiles.push(u);
    return r.fulfill({ status: 200, contentType: 'image/png', headers: { 'access-control-allow-origin': '*' }, body: TILE });
  };
  const page = await tour.open('model=fzk-haus', { route });
  // FZK-Haus as a sample has no place; the IFC file has an IfcSite position, so open that, as a person with the file would
  await ui.tab(page, 'Parameters'); await ui.topOfPanel(page);
  await ui.folder(page, 'Open model');
  const chooser = page.waitForEvent('filechooser');
  await ui.press(page, 'Open IFC or glb file');
  await (await chooser).setFiles(resolve(repoRoot, 'models', 'AC20-FZK-Haus.ifc'));
  await page.waitForFunction(() => window.__xray.app.modelName.startsWith('file:'), null, { timeout: 240000 });
  await ui.settle(page, 1500);
  await ui.topOfPanel(page);
  await ui.folder(page, 'Map');
  tour.check('step 1: the Map folder holds "show map under model"', !!(await ui.control(page, 'show map under model')));
  tour.check('"The map is off at every start. With the map off, the viewer makes no network request."', tiles.length === 0 && !(await ui.valueOf(page, 'show map under model')), `${tiles.length} outside requests`);
  await ui.set(page, 'show map under model', true);
  const dlg = page.getByRole('alertdialog');
  await dlg.waitFor({ timeout: 10000 }).catch(() => {});
  const text = await dlg.innerText().catch(() => '');
  tour.check('step 2: a notice reads "Map tiles are fetched from <provider>; this reveals the project\'s location to them."', /Map tiles are fetched from .+; this reveals the project.s location to them/.test(text), text.replace(/\s+/g, ' ').slice(0, 200));
  await page.waitForTimeout(800);
  tour.check('step 2: "Nothing is requested until you accept."', tiles.length === 0, `${tiles.length} requests`);
  await dlg.getByRole('button', { name: 'Show the map' }).click();
  await page.waitForTimeout(4000); await ui.settle(page, 1500);
  const st = await page.evaluate(() => window.__xrayMap.state());
  tour.check('step 3: "Accept. The ground under the model fills with tiles over a moment."', tiles.length > 0 && st.enabled, `${tiles.length} tile requests, state ${JSON.stringify(st).slice(0, 160)}`);
  const loc = String(await ui.valueOf(page, 'location'));
  tour.check('step 3: "The status line under location says where the place came from"', /^(From IfcMapConversion \(EPSG:\d+\)|From IfcSite|Manual|Unknown)/.test(loc), loc);
  const provs = await (await ui.control(page, 'provider')).locator('select option').allInnerTexts();
  tour.check('step 4: provider offers Esri World Imagery, OpenStreetMap and a custom XYZ template', /Esri World Imagery/.test(provs.join()) && /OpenStreetMap/.test(provs.join()) && /custom/i.test(provs.join()), provs.join(' | '));
  tour.check('step 5: "radius (m) (the disc around the model, 150 by default)"', Number(await ui.valueOf(page, 'radius (m)')) === 150, String(await ui.valueOf(page, 'radius (m)')));
  await ui.set(page, 'opacity', 0.5);
  tour.check('step 5: "Change opacity"', Number(await ui.valueOf(page, 'opacity')) === 0.5);
  await ui.set(page, 'radius (m)', 100);
  tour.check('step 5: "and radius (m)"', Number(await ui.valueOf(page, 'radius (m)')) === 100);
  tour.check('"you cannot pick it": a ray from above does not meet the map', (await page.evaluate(() => window.__xrayMap.pickable())) === false);
});

await tour.step('6.3 Try it: bloom and edge glow on a duct, Glow mode, another element, the presentation preset', async () => {
  const page = await tour.open('model=building');
  const duct = await ui.clickElement(page, { cls: 'IfcDuctSegment' });
  tour.check('"Select a duct in the Building model."', !!duct);
  await ui.tab(page, 'Parameters'); await ui.topOfPanel(page);
  await ui.folder(page, 'Cinematic');
  await ui.folder(page, 'Focus bloom'); await ui.set(page, 'Selective bloom', true);
  await ui.topOfPanel(page); await ui.folder(page, 'Cinematic'); await ui.folder(page, 'Edge glow'); await ui.set(page, 'Edge glow', true);
  await ui.settle(page, 1200);
  const c = await page.evaluate(() => ({ bloom: window.__cinematic.cfg.bloom, glow: window.__cinematic.cfg.edgeGlow }));
  tour.check('"Switch on Selective bloom and Edge glow. The duct gets a soft halo and a bright outline."', c.bloom && c.glow, JSON.stringify(c));
  await ui.mode(page, 'Solid');
  await ui.mode(page, 'Glow');
  const g = await page.evaluate(() => ({ bloom: window.__cinematic.cfg.bloom, glow: window.__cinematic.cfg.edgeGlow, scope: window.__cinematic.cfg.glowScope }));
  tour.check('"Or click Glow in the top bar, which does both"', g.bloom && g.glow && (await ui.litMode(page)) === 'Glow', JSON.stringify(g));
  const cam0 = await ui.cam(page);
  const other = await ui.clickElement(page, { cls: /Wall|Slab|Column/ });
  await ui.waitMoved(page, cam0, 12000);
  const cam1 = await ui.cam(page);
  tour.check('"Select another element: the camera glides"', !!other && Math.hypot(...cam1.p.map((v, i) => v - cam0.p[i])) > 0.05, `camera moved ${Math.hypot(...cam1.p.map((v, i) => v - cam0.p[i])).toFixed(2)} m`);
  await ui.tool(page, 'Presets').click();
  const card = page.locator('#xray-toolbar-drawer [data-preset=presentation]');
  await card.waitFor({ timeout: 10000 }).catch(() => {});
  await card.getByRole('button', { name: 'Apply' }).click();
  await ui.settle(page, 1200);
  const p = await page.evaluate(() => { const c = window.__cinematic.cfg; return { dressing: c.dressing, bloom: c.bloom, flyTo: c.flyTo, reveal: c.reveal, sweep: c.sweep.enabled, active: window.__xrayPresets.active() }; });
  tour.check('"apply the preset presentation ... It switches on scene dressing, bloom, fly-to, reveal and the sweep in one step."', p.active === 'presentation' && p.dressing && p.bloom && p.flyTo && p.reveal && p.sweep, JSON.stringify(p));
  await page.keyboard.press('Escape');
});

await tour.step('6.3 defaults of the Cinematic table', async () => {
  const page = await tour.open('model=building');
  const d = await page.evaluate(() => { const c = window.__cinematic.cfg; return { flyTo: c.flyTo, reveal: c.reveal, sweep: c.sweep.enabled, dressing: c.dressing, grade: c.grade.enabled, bloom: c.bloom, edgeGlow: c.edgeGlow, ao: window.__cinematic.post?.settings?.ao ?? null, margin: null }; });
  tour.check('the table: Camera fly-to, Staggered reveal, Sweep reveal, Scene dressing, Depth grading are on by default', d.flyTo && d.reveal && d.sweep && d.dressing && d.grade, JSON.stringify(d));
  tour.check('the table: Focus bloom and Edge glow are off by default', !d.bloom && !d.edgeGlow, JSON.stringify(d));
});

await tour.finish();
