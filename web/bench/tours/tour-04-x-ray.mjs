// Tour of chapter 4, "X-ray: let the structure get out of the way" (docs/manual/04-x-ray.md): the Try it of 4.1 (select a duct, orbit, X, Esc),
// 4.3 (pin and clear), 4.4 (the five top-bar modes) and 4.5 (keys 1 to 4). Picture: `xray-on-off`.
// Run: node bench/run-smokes.mjs --only tour-04-x-ray
import { startTour, ui } from './lib.mjs';

const tour = await startTour('tour-04-x-ray');

await tour.step('4.1 Try it steps 1-6: select a duct, orbit, X, X, Esc', async () => {
  const page = await tour.open('model=building');
  const st = (await ui.statusText(page)).replace(/\s+/g, ' ');
  tour.check('step 1: "X-ray is on by default. The status bar says so."', /x-ray on/.test(st) && (await ui.xray(page)).on, st.slice(0, 120));
  const duct = await ui.clickElement(page, { cls: 'IfcDuctSegment' });
  tour.check('step 2: "Click a duct. If you do not see one, orbit until you find one."', !!duct, JSON.stringify(duct));
  await ui.park(page);
  await ui.settle(page, 1200);
  const x1 = await ui.xray(page);
  const focusAlpha = await ui.xray(page, x1.focusIds);
  tour.check('step 3: "The duct and the run connected to it stay solid."', x1.focus >= 1 && Object.values(focusAlpha.alpha).every((a) => a > 0.99), `focus ${x1.focus}`);
  tour.check('step 3: "A slab or a wall in front of it turns faint."', Object.keys(x1.faintByClass).some((c) => /Slab|Wall/.test(c)), JSON.stringify(x1.faintByClass));
  // step 4: orbit
  const box = await page.locator('#c').boundingBox();
  let changed = false, x2 = x1;
  for (let i = 0; i < 6 && !changed; i++) {
    await page.mouse.move(box.x + box.width * 0.6, box.y + box.height * 0.6);
    await page.mouse.down(); await page.mouse.move(box.x + box.width * 0.6 + (i % 2 ? -150 : 150), box.y + box.height * 0.6 + 20, { steps: 8 }); await page.mouse.up();
    await ui.settle(page, 1200);
    x2 = await ui.xray(page);
    changed = x2.faintIds.join() !== x1.faintIds.join();
  }
  tour.check('step 4: "Orbit. The faint parts change as your point of view changes."', changed, `${x1.faint} faint before, ${x2.faint} after`);
  // step 5
  await page.keyboard.press('x');
  await ui.settle(page, 1200);
  const off = await ui.xray(page);
  tour.check('step 5: "Press X. All ghosts go solid at once: x-ray is off."', !off.on && off.faint === 0, `on=${off.on}, faint ${off.faint}`);
  await tour.expectText(page.locator('#xray-overlay'), /x-ray off/, 'the status bar says x-ray is off', 8000);
  await page.keyboard.press('x');
  await ui.settle(page, 1200);
  tour.check('step 5: "Press X again."', (await ui.xray(page)).on && (await ui.xray(page)).faint > 0);
  // step 6
  await page.keyboard.press('Escape');
  await ui.settle(page, 1200);
  const x6 = await ui.xray(page);
  tour.check('step 6: "Press Esc to clear the selection. With nothing selected there is no focus, so nothing ghosts."', (await ui.selection(page)).length === 0 && x6.focus === 0 && x6.faint === 0, `focus ${x6.focus}, faint ${x6.faint}`);
});

await tour.step('4.1 picture: the same view with x-ray on and off', async () => {
  const page = await tour.open('model=building');
  const duct = await ui.clickElement(page, { cls: 'IfcDuctSegment' });
  await ui.park(page);
  await ui.settle(page, 1500);
  const on = await tour.shot(page, { element: '#stage' });
  await page.keyboard.press('x');
  await ui.settle(page, 1500);
  const off = await tour.shot(page, { element: '#stage' });
  tour.check('both states of the picture were taken on the same selection', !!duct && !!on && !!off);
  await tour.pictureRow('xray-on-off', [{ buf: on, label: 'X-ray on: the slab and wall in front of the duct run are faint' }, { buf: off, label: 'X-ray off (press X): everything solid' }]);
});

await tour.step('4.3 Try it: select a beam, Pin selected, orbit, Clear pins/hides', async () => {
  const page = await tour.open('model=building');
  const col = await ui.clickElement(page, { cls: "IfcBeam" });
  tour.check('step 1: "In the Building model, select a beam."', !!col, JSON.stringify(col));
  await ui.tab(page, 'Parameters'); await ui.topOfPanel(page);
  await ui.press(page, 'Pin selected');
  const pins = await page.evaluate(() => window.__xray.app.settings.overrides.userPins.size);
  tour.check('"Click Pin selected": the beam is pinned', pins >= 1, `${pins} pinned`);
  // orbit so a wall is in front of it
  const box = await page.locator('#c').boundingBox();
  for (const dx of [160, -320, 160]) {
    await page.mouse.move(box.x + box.width * 0.6, box.y + box.height * 0.6); await page.mouse.down();
    await page.mouse.move(box.x + box.width * 0.6 + dx, box.y + box.height * 0.6, { steps: 8 }); await page.mouse.up();
    await ui.settle(page, 1000);
    const a = (await ui.xray(page, [col.id])).alpha[col.id];
    tour.check('"The beam stays clearly visible" (not below the pin floor 0.60)', a >= 0.59, `alpha ${a.toFixed(2)}`);
  }
  await ui.press(page, 'Clear pins/hides');
  tour.check('"Click Clear pins/hides": no pins left', (await page.evaluate(() => window.__xray.app.settings.overrides.userPins.size)) === 0);
  await ui.clickElement(page, { cls: 'IfcBeam' });
  await page.locator('#c').hover();
  await page.keyboard.press('h');
  await ui.settle(page, 600);
  const hid = await page.evaluate(() => window.__xray.app.settings.overrides.userHides.size);
  tour.check('"Hide selected (key H)": the selection is hidden', hid >= 1, `${hid} hidden`);
  await page.keyboard.press('Alt+h');
  await ui.settle(page, 600);
  tour.check('"Alt+H brings back everything you hid"', (await page.evaluate(() => window.__xray.app.settings.overrides.userHides.size)) === 0);
});

await tour.step('4.4 Try it: select a duct, click each mode in turn, click a lit mode again', async () => {
  const page = await tour.open('model=building');
  await ui.clickElement(page, { cls: 'IfcDuctSegment' });
  tour.check('"At start the bar lights Ghost"', (await ui.litMode(page)) === 'Ghost', await ui.litMode(page));
  const probe = () => page.evaluate(() => ({ xray: window.__xray.app.settings.xray, style: window.__xrayImaging.config.style, peel: window.__xrayViewModes.config.peel.enabled, bloom: window.__cinematic.cfg.bloom, glow: window.__cinematic.cfg.edgeGlow, preset: window.__xrayPresets.active() }));
  for (const [mode, ok] of [
    ['Solid', (p) => !p.xray && p.style === 'standard' && !p.peel],
    ['Ghost', (p) => p.xray && p.style === 'standard' && p.preset === 'coordination'],
    ['Radiograph', (p) => p.style === 'radiograph'],
    ['Glow', (p) => p.bloom && p.glow],
    ['Cutaway', (p) => p.peel],
  ]) {
    await ui.mode(page, mode);
    const p = await probe();
    tour.check(`clicking ${mode} lights it and applies its look`, (await ui.litMode(page)) === mode && ok(p), JSON.stringify(p));
  }
  await ui.mode(page, 'Cutaway');
  tour.check('"Click a lit mode again: you go to Solid"', (await ui.litMode(page)) === 'Solid' && !(await probe()).xray, await ui.litMode(page));
  await page.keyboard.press('Shift+1');
  await ui.settle(page, 500);
  tour.check('Shift+1 is the Ghost mode', (await ui.litMode(page)) === 'Ghost');
});

await tour.step('4.5 Try it: keys 2, 1, 3, 4, 1', async () => {
  const page = await tour.open('model=building');
  await ui.clickElement(page, { cls: 'IfcDuctSegment' });
  await ui.park(page);
  const active = () => page.evaluate(() => window.__xrayPresets.active());
  await page.keyboard.press('2');
  await ui.settle(page, 1500);
  const hb = await ui.xray(page);
  tour.check('step 2: "Press 2. This is hide-blockers: what blocks the focus disappears, and everything else stays solid."', (await active()) === 'hide-blockers' && hb.min <= 0.5, `preset ${await active()}, faintest alpha ${hb.min.toFixed(2)}`);
  await page.keyboard.press('1');
  await ui.settle(page, 1200);
  tour.check('step 3: "Press 1 to return to the factory x-ray (coordination)."', (await active()) === 'coordination', await active());
  await page.keyboard.press('3');
  await ui.settle(page, 1200);
  tour.check('step 4: "Press 3 (behind-only)"', (await active()) === 'behind-only' && (await page.evaluate(() => window.__xrayViewModes.config.behind.enabled)), await active());
  await page.keyboard.press('4');
  await ui.settle(page, 1200);
  tour.check('step 4: "and 4 (peelback)"', (await active()) === 'peelback' && (await page.evaluate(() => window.__xrayViewModes.config.peel.enabled)), await active());
  await page.keyboard.press('1');
  await ui.settle(page, 1200);
  tour.check('step 5: "Press 1 again."', (await active()) === 'coordination' && !(await page.evaluate(() => window.__xrayViewModes.config.peel.enabled)), await active());
});

await tour.finish();
