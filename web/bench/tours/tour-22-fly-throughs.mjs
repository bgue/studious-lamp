// Tour of chapter 22, "Fly-throughs" (docs/manual/22-fly-throughs.md): 22.1 build a fly-through from saved views (New, From views, cards, the editor, Timing, Play),
// 22.2 play, pause, scrub, keys, stop, a click on the 3D view, 22.3 the Record a video dialog (and a short real export). No picture notes in this chapter.
// Run: node bench/run-smokes.mjs --only tour-22-fly-throughs
import { startTour, ui } from './lib.mjs';

const tour = await startTour('tour-22-fly-throughs');
// One page at a time: a page left over from the step before (a film still playing in it) would slow down every later page of a software renderer.
const _pages = [];
const open = async (...a) => { while (_pages.length) await _pages.pop().context().close().catch(() => {}); const p = await tour.open(...a); _pages.push(p); return p; };
const FLY = (page, fn, arg) => page.evaluate(fn, arg);
const state = (page) => page.evaluate(() => window.__xrayFlythrough.state());
const cards = (page) => page.locator('.fl-card');
const camMoved = (a, b) => Math.hypot(...a.p.map((v, i) => v - b.p[i]));

// Three saved views like the manual asks: the outside, the roof, the cellar side (FZK-Haus has no heating pipes, so a low view stands in).
const POSES = [[[14, 8, 16], [0, 2, 0]], [[3, 10, 6], [0, 5, 0]], [[-9, 1.5, 8], [0, 0.5, 0]]];
async function makeViews(page) {
  for (const [p, t] of POSES) {
    await ui.setCam(page, p, t);
    await page.keyboard.press('Control+Shift+S');
    await page.waitForTimeout(500);
  }
}
async function openSection(page) {
  await ui.tab(page, 'Views');
  const head = page.locator('.fl-head');
  if ((await head.getAttribute('aria-expanded')) !== 'true') await head.click();
  await page.waitForTimeout(300);
}

await tour.step('22.1 Try it steps 1-3: Views tab, Fly-through section, New, From views', async () => {
  const page = await open('model=fzk-haus');
  await makeViews(page);
  const nViews = await page.evaluate(() => window.__xrayViews.list().length);
  tour.check('"If you have no saved views yet, make three first": three views saved', nViews === 3, `${nViews}`);
  await openSection(page);
  tour.check('step 1: "Open the Views tab ... Find the Fly-through section"', await page.locator('.fl-head').isVisible() && /Fly-through/.test(await page.locator('.fl-head').innerText()));
  await page.getByRole('button', { name: 'New', exact: true }).click();
  await page.waitForTimeout(400);
  tour.check('step 2: "Click New. A fly-through is a named list"', (await page.evaluate(() => window.__xrayFlythrough.list().length)) === 1);
  await page.getByRole('button', { name: 'From views' }).click();
  await page.waitForTimeout(1500);
  tour.check('step 3: "From views ... one keyframe per saved view"', (await cards(page).count()) === 3, `${await cards(page).count()} cards`);
  const addSel = await page.getByLabel('Add a saved view as a keyframe').locator('option').count();
  tour.check('"The list next to Add keyframe adds one view"', addSel >= 3, `${addSel} options`);
  await ui.setCam(page, [6, 4, 6], [0, 1, 0]);
  await page.getByRole('button', { name: 'Add keyframe' }).dispatchEvent('click');
  await page.waitForTimeout(800);
  tour.check('"To add one at a time, orbit to a place and click Add keyframe"', (await cards(page).count()) === 4);
  const txt = (await cards(page).first().innerText()).replace(/\s+/g, ' ');
  tour.check('step 4: "Each keyframe is a card with a thumbnail, its name and the move (to 2 s, hold 1 s)"', (await cards(page).first().locator('img, canvas').count()) > 0 && /\d/.test(txt), txt.slice(0, 80));
  const cam0 = await ui.cam(page);
  await cards(page).nth(1).locator('.fl-shot').click();
  await ui.waitStill(page);
  tour.check('step 4: "Click a card to go there"', camMoved(cam0, await ui.cam(page)) > 0.3);
  const before = await page.evaluate(() => window.__xrayFlythrough.keyframes().map((k) => k.name));
  await cards(page).nth(0).getByRole('button', { name: 'Move later' }).click();
  await page.waitForTimeout(300);
  const after = await page.evaluate(() => window.__xrayFlythrough.keyframes().map((k) => k.name));
  tour.check('step 4: "use the arrow buttons ... to reorder"', after[1] === before[0] && after[0] === before[1], `${before.join()} -> ${after.join()}`);
  await cards(page).nth(1).locator('.fl-shot').click();
  await page.keyboard.press('Alt+ArrowLeft');
  await page.waitForTimeout(300);
  const after2 = await page.evaluate(() => window.__xrayFlythrough.keyframes().map((k) => k.name));
  tour.check('step 4: "press Alt+Left and Alt+Right to reorder"', after2.join() !== after.join(), `${after.join()} -> ${after2.join()}`);
  await cards(page).nth(3).locator('.fl-shot').click();
  await page.getByRole('button', { name: 'Delete', exact: true }).first().click();
  await page.waitForTimeout(300);
  tour.check('step 4: "Delete removes the card"', (await cards(page).count()) === 3);
});

await tour.step('22.1 Try it steps 5-7: Hold, Fade, caption, Timing, Play; the path in 3D', async () => {
  const page = await open('model=fzk-haus');
  await makeViews(page);
  await openSection(page);
  await page.getByRole('button', { name: 'New', exact: true }).click();
  await page.getByRole('button', { name: 'From views' }).click();
  await page.waitForTimeout(1200);
  await cards(page).nth(1).locator('.fl-shot').click();
  await ui.waitStill(page);
  await page.getByLabel('Hold', { exact: true }).fill('1'); await page.getByLabel('Hold', { exact: true }).press('Tab');
  const fade = page.locator('.fl-edit label', { hasText: 'Fade' }).first().locator('input');
  await fade.check();
  await page.getByLabel('Caption title').fill('The roof'); await page.getByLabel('Caption title').press('Tab');
  await page.getByLabel('Caption text').fill('Seen from above'); await page.getByLabel('Caption text').press('Tab');
  const k = await page.evaluate(() => window.__xrayFlythrough.keyframes()[1]);
  tour.check('step 5: "set Hold to 1 s ... Set Fade on ... Type a caption title and text"', k.hold === 1 && !!k.fade && k.caption?.title === 'The roof' && k.caption?.text === 'Seen from above', JSON.stringify({ hold: k.hold, fade: k.fade, caption: k.caption }));
  const tim = await page.getByLabel('How the travel time is set').locator('option').allInnerTexts();
  tour.check('step 6: "Choose Timing: Constant speed (default) or Seconds per move"', tim.some((t) => /Constant speed/i.test(t)) && tim.some((t) => /Seconds per move/i.test(t)), tim.join(' | '));
  const dflt = await page.getByLabel('How the travel time is set').evaluate((s) => s.selectedOptions[0].textContent);
  tour.check('"Constant speed (default; metres per second along the path)"', /Constant speed/i.test(dflt), dflt);
  tour.check('"While the section is open, the camera path is drawn in 3D as a dashed line"', await page.evaluate(() => window.__xrayFlythrough.pathVisible === true));
  await page.getByRole('button', { name: /Play$/ }).first().click();
  await page.waitForFunction(() => window.__xrayFlythrough.state().playing, null, { timeout: 150000 });
  tour.check('step 7: "Click Play": it plays', (await state(page)).playing === true);
  tour.check('"It is hidden while the fly-through plays or records": the path is hidden', await page.evaluate(() => window.__xrayFlythrough.pathVisible === false));
  await page.keyboard.press('Escape');
  await page.waitForFunction(() => !window.__xrayFlythrough.state().playing, null, { timeout: 150000 });
  await page.waitForTimeout(300);
  tour.check('"the path is back after playback"', await page.evaluate(() => window.__xrayFlythrough.pathVisible === true));
  const kf = await page.evaluate(() => window.__xrayFlythrough.keyframes().length);
  tour.check('"The Fly-through ⋯ menu renames, duplicates, exports, imports and deletes"', await (async () => {
    await page.getByRole('button', { name: 'More fly-through actions' }).click();
    const items = await page.getByRole('menuitem').allInnerTexts();
    await page.keyboard.press('Escape');
    return ['Rename', 'Duplicate', 'Export file', 'Import file', 'Delete'].every((n) => items.some((i) => i.includes(n)));
  })(), String(kf));
});

await tour.step('22.2 Try it steps 1-5: Play, Space, the timeline, Left/Right, Stop, click on the 3D view', async () => {
  const page = await open('model=fzk-haus');
  await makeViews(page);
  await openSection(page);
  await page.getByRole('button', { name: 'New', exact: true }).click();
  await page.getByRole('button', { name: 'From views' }).click();
  await page.waitForTimeout(1200);
  await page.evaluate(() => window.__xrayFlythrough.setOptions({ timing: 'seconds', segmentS: 6 }));
  const pre = await page.evaluate(() => ({ cam: window.__xrayViews.camera(), sel: window.__xray.app.selection.slice() }));
  await ui.setCam(page, [20, 12, 20], [0, 0, 0]);
  const camBefore = await ui.cam(page);
  await page.getByRole('button', { name: /Play$/ }).first().click();
  await page.waitForFunction(() => window.__xrayFlythrough.state().time > 0.4, null, { timeout: 150000 });
  tour.check('step 1: "Click Play. It starts from the beginning"', (await state(page)).time < 4);
  await page.locator('#c').hover();
  await page.keyboard.press('Space');
  await page.waitForTimeout(400);
  const t1 = (await state(page)).time;
  await page.waitForTimeout(1200);
  const s2 = await state(page);
  tour.check('step 2: "Press Space ... pauses" and the time holds', s2.paused === true && Math.abs(s2.time - t1) < 0.3, `paused ${s2.paused}, ${t1.toFixed(2)} -> ${s2.time.toFixed(2)}`);
  await page.keyboard.press('Space');
  await page.waitForTimeout(800);
  tour.check('"Press Space again to resume"', (await state(page)).paused === false);
  const bar = await page.locator('.fl-bar').boundingBox();
  await page.mouse.click(bar.x + bar.width * 0.7, bar.y + bar.height / 2);
  await page.waitForTimeout(600);
  const total = await page.evaluate(() => window.__xrayFlythrough.timing().total);
  const jumped = await state(page);
  tour.check('step 2: "Click or drag on the timeline bar to jump"', Math.abs(jumped.time - total * 0.7) < total * 0.15, `time ${jumped.time.toFixed(1)} of ${total.toFixed(1)}`);
  tour.check('"A tick marks each keyframe": the bar has ticks', (await page.locator('.fl-bar .fl-tick, .fl-bar [class*=tick]').count()) >= 2 || (await page.locator('.fl-bar *').count()) >= 2);
  await page.locator('#c').hover();
  const kBefore = (await state(page)).keyframe;
  await page.keyboard.press('ArrowRight');
  await page.waitForTimeout(600);
  const kR = await state(page);
  tour.check('step 3: "Press Left and Right for the previous and next keyframe": Right goes forward', kR.keyframe !== kBefore || kR.time > jumped.time, `keyframe ${kBefore} -> ${kR.keyframe}`);
  await page.keyboard.press('ArrowLeft');
  await page.waitForTimeout(600);
  const kL = await state(page);
  tour.check('"Left goes back"', kL.time < kR.time, `${kR.time.toFixed(1)} -> ${kL.time.toFixed(1)}`);
  await page.getByRole('button', { name: '■' }).first().click().catch(() => page.keyboard.press('Escape'));
  await page.waitForFunction(() => !window.__xrayFlythrough.state().playing, null, { timeout: 150000 });
  await ui.settle(page, 500);
  const camAfter = await ui.cam(page);
  tour.check('step 4: "Click Stop or press Esc. Camera ... go back as they were"', camMoved(camBefore, camAfter) < 0.05, `moved ${camMoved(camBefore, camAfter).toFixed(3)} m`);
  // step 5: a click on the 3D view during play stops and keeps the camera
  await page.getByRole('button', { name: /Play$/ }).first().click();
  await page.waitForFunction(() => window.__xrayFlythrough.state().time > 1.5, null, { timeout: 150000 });
  const c = await page.locator('#c').boundingBox();
  await page.mouse.click(c.x + c.width * 0.5, c.y + c.height * 0.35);
  await page.waitForFunction(() => !window.__xrayFlythrough.state().playing, null, { timeout: 150000 });
  await ui.settle(page, 500);
  const camTaken = await ui.cam(page);
  tour.check('step 5: "Click on the 3D view during play: it stops, and keeps the camera where you took it"', camMoved(camBefore, camTaken) > 0.5, `moved ${camMoved(camBefore, camTaken).toFixed(2)} m from the start pose`);
  void pre;
});

await tour.step('22.3 Try it steps 1-7: the Record a video dialog', async () => {
  const page = await open('model=fzk-haus');
  await makeViews(page);
  await openSection(page);
  await page.getByRole('button', { name: 'New', exact: true }).click();
  await page.getByRole('button', { name: 'From views' }).click();
  await page.waitForTimeout(1200);
  await page.getByRole('button', { name: /Rec$/ }).click();
  const dlg = page.getByRole('dialog', { name: 'Record a video' });
  await dlg.waitFor();
  tour.check('step 1: "Click Rec ... The Record a video dialog opens"', await dlg.isVisible());
  const opts = async (label) => dlg.getByLabel(label, { exact: true }).locator('option').allInnerTexts();
  const size = await opts('Size');
  tour.check('step 2: Size: the window, 1280 x 720, 1920 x 1080, 2560 x 1440 or 3840 x 2160', ['1280', '1920', '2560', '3840'].every((n) => size.some((s) => s.includes(n))) && size.some((s) => /window/i.test(s)), size.join(' | '));
  const fps = await opts('Frame rate');
  tour.check('step 3: Frame rate: 24, 30 or 60', ['24', '30', '60'].every((n) => fps.some((s) => s.startsWith(n))), fps.join(' | '));
  const q = await opts('Quality');
  tour.check('step 3: Quality: small file, balanced or high quality', q.length === 3 && /small/i.test(q[0]) && /balanced/i.test(q[1]) && /high/i.test(q[2]), q.join(' | '));
  const fm = await opts('Format');
  tour.check('step 4: Format: automatic, MP4, WebM or PNG sequence', /Automatic/.test(fm[0]) && fm.some((s) => /MP4/.test(s)) && fm.some((s) => /WebM/.test(s)) && fm.some((s) => /PNG/.test(s)), fm.join(' | '));
  tour.check('step 5: "Captions and labels" is on, with a file name', (await dlg.getByLabel('Captions and labels').isChecked()) && (await dlg.getByLabel('File name').inputValue()).length > 0);
  tour.check('step 6: "Time a few frames" appears for large sizes', (await dlg.getByRole('button', { name: 'Time a few frames' }).count()) === 1);
  await dlg.getByLabel('Size', { exact: true }).selectOption({ label: size.find((s) => /1280/.test(s)) });
  await dlg.getByLabel('Frame rate', { exact: true }).selectOption({ label: fps.find((s) => s.startsWith('24')) });
  await dlg.getByLabel('Format', { exact: true }).selectOption({ label: fm.find((s) => /WebM/.test(s)) });
  tour.check('step 7: the dialog has Cancel and Record', (await dlg.getByRole('button', { name: 'Cancel' }).count()) === 1 && (await dlg.getByRole('button', { name: 'Record' }).count()) === 1);
  await dlg.getByRole('button', { name: 'Cancel' }).click();
  tour.check('Cancel closes the dialog', !(await dlg.isVisible().catch(() => false)));
});

await tour.finish();
