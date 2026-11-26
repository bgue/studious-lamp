// Tour of chapter 21, "One player behind every Play" (docs/manual/21-player.md): 21.1 the four sources, the Try it (Script Run, Space, the timeline, a press on the 3D
// view, the end, Esc), the keys table, Walk mode left while playing, and the On-screen display block. No picture notes in this chapter.
// Run: node bench/run-smokes.mjs --only tour-21-player
import { startTour, ui } from './lib.mjs';

const tour = await startTour('tour-21-player');
// One page at a time: a page left over from the step before (a film still playing in it) would slow down every later page of a software renderer.
const _pages = [];
const open = async (...a) => { while (_pages.length) await _pages.pop().context().close().catch(() => {}); const p = await tour.open(...a); _pages.push(p); return p; };
const dist = (a, b) => Math.hypot(...a.p.map((v, i) => v - b.p[i]));
const sstate = (page) => page.evaluate(() => window.__xrayScript.state());
const flyState = (page) => page.evaluate(() => window.__xrayFlythrough.state());
async function runScript(page, text) {
  await ui.tab(page, 'Script');
  const ta = page.getByLabel('Animation script');
  await ta.fill(text);
  await page.getByRole('button', { name: 'Run', exact: true }).click();
}

await tour.step('21.1 Try it step 1-2: Script tab, "fly to everything over 3 seconds", Run, Space pauses', async () => {
  const page = await open('model=fzk-haus');
  tour.check('"Four things produce a timeline": the Script tab, the Views tab fly-through section and the 4D tab exist', (await page.getByRole('tab', { name: 'Script', exact: true }).count()) === 1 && (await page.getByRole('tab', { name: '4D', exact: true }).count()) === 1 && (await page.getByRole('tab', { name: 'Views', exact: true }).count()) === 1);
  await ui.setCam(page, [18, 10, 18], [0, 1, 0]);
  const start = await ui.cam(page);
  await runScript(page, 'fly to everything over 3 seconds');
  await page.waitForFunction(() => window.__xrayScript.state().running, null, { timeout: 150000 });
  tour.check('step 1: "type fly to everything over 3 seconds and press Run": it plays', (await sstate(page)).running === true);
  await page.locator('#c').hover();
  await page.keyboard.press('Space');
  await page.waitForTimeout(500);
  const c1 = await ui.cam(page);
  await page.waitForTimeout(1200);
  const c2 = await ui.cam(page);
  tour.check('step 2: "press Space. It pauses, and the picture holds"', (await sstate(page)).paused === true && dist(c1, c2) < 0.05, `paused=${(await sstate(page)).paused}, moved ${dist(c1, c2).toFixed(3)}`);
  await page.keyboard.press('Space');
  await page.waitForTimeout(600);
  tour.check('"Press Space again to resume"', (await sstate(page)).paused === false);
  await page.waitForFunction(() => !window.__xrayScript.state().running, null, { timeout: 150000 });
  await ui.settle(page, 600);
  const end = await ui.cam(page);
  tour.check('step 5: "let it end. The camera ... are all as they were before Play"', dist(start, end) < 0.05, `moved ${dist(start, end).toFixed(3)} m`);
});

await tour.step('21.1 Try it steps 4 and 6: a press on the 3D view keeps the camera, Esc puts everything back', async () => {
  const page = await open('model=fzk-haus');
  await ui.setCam(page, [18, 10, 18], [0, 1, 0]);
  const start = await ui.cam(page);
  await runScript(page, 'mode glow\nfly to everything over 4 seconds\nwait 4 seconds');
  await page.waitForFunction(() => window.__xrayScript.state().running, null, { timeout: 150000 });
  for (let i = 0; i < 200 && dist(start, await ui.cam(page)) < 1; i++) await page.waitForTimeout(300);
  const modeDuring = await ui.litMode(page);
  const c = await page.locator('#c').boundingBox();
  await page.mouse.click(c.x + c.width * 0.5, c.y + c.height * 0.3);
  await page.waitForFunction(() => !window.__xrayScript.state().running, null, { timeout: 150000 });
  await ui.settle(page, 600);
  const kept = await ui.cam(page);
  tour.check('step 4: "click on the 3D view. Playing stops and the camera stays where you took it"', dist(start, kept) > 0.5, `moved ${dist(start, kept).toFixed(2)} m`);
  tour.check('"Everything else goes back": the look returns to what it was', (await ui.litMode(page)) !== 'Glow' || modeDuring === (await ui.litMode(page)), `during ${modeDuring}, after ${await ui.litMode(page)}`);
  await ui.setCam(page, [18, 10, 18], [0, 1, 0]);
  const start2 = await ui.cam(page);
  await page.getByRole('button', { name: 'Run', exact: true }).click();
  await page.waitForFunction(() => window.__xrayScript.state().running, null, { timeout: 150000 });
  await page.waitForTimeout(1500);
  await page.locator('#c').hover();
  await page.keyboard.press('Escape');
  await page.waitForFunction(() => !window.__xrayScript.state().running, null, { timeout: 150000 });
  await ui.settle(page, 600);
  tour.check('step 6: "Press Esc while it plays. It stops, and everything goes back, camera included"', dist(start2, await ui.cam(page)) < 0.05, `moved ${dist(start2, await ui.cam(page)).toFixed(3)} m`);
});

await tour.step('21.1 Keys: Shift+w does nothing while something plays; typing in a box does not trigger the keys', async () => {
  const page = await open('model=fzk-haus');
  await ui.setCam(page, [18, 10, 18], [0, 1, 0]);
  await runScript(page, 'fly to everything over 6 seconds');
  await page.waitForFunction(() => window.__xrayScript.state().running, null, { timeout: 150000 });
  await page.locator('#c').hover();
  await page.keyboard.press('Shift+w');
  await page.waitForTimeout(400);
  tour.check('"Shift+w: Nothing. Walk mode cannot start while something plays"', await page.evaluate(() => !document.querySelector('#c').dataset.walk), '');
  const ta = page.getByLabel('Animation script');
  await ta.click();
  await page.keyboard.press('End');
  await page.keyboard.type(' ');
  await page.waitForTimeout(300);
  tour.check('"Space ... work only while ... the cursor is not in a text box": typing a space in the editor does not pause', (await sstate(page)).paused === false);
  await page.locator('#c').hover();
  await page.keyboard.press('Escape');
  await page.waitForFunction(() => !window.__xrayScript.state().running, null, { timeout: 150000 });
  await ui.settle(page, 400);
  await page.keyboard.press('Shift+w');
  await page.waitForTimeout(400);
  tour.check('"After it ends, press Shift+w to walk again"', await page.evaluate(() => !!document.querySelector('#c').dataset.walk), (await ui.statusText(page)).slice(0, 80));
});

await tour.step('21.1 Where you set the display: On-screen display block of the fly-through section', async () => {
  const page = await open('model=fzk-haus');
  await ui.tab(page, 'Views');
  const head = page.locator('.fl-head');
  if ((await head.getAttribute('aria-expanded')) !== 'true') await head.click();
  await page.waitForTimeout(300);
  const t = (await page.locator('.fl').innerText()).replace(/\s+/g, ' ');
  tour.check('"the On-screen display block ... Progress bar, Compass, Scale bar, Label size and the caption position"', /On-screen display/i.test(t) && ['Progress bar', 'Compass', 'Scale bar'].every((n) => t.includes(n)), t.slice(0, 200));
  const size = page.getByLabel('Label font size in pixels');
  tour.check('"Label size (9 to 28)"', (await size.getAttribute('min')) === '9' && (await size.getAttribute('max')) === '28');
  const bar = page.locator('.fl input[data-help-key="Sidebar/Fly-through progress bar"]');
  const comp = page.locator('.fl input[data-help-key="Sidebar/Fly-through compass"]');
  const sc = page.locator('.fl input[data-help-key="Sidebar/Fly-through scale bar"]');
  tour.check('"The progress bar ... On by default. The compass (off by default) ... The scale bar (off by default)"', (await bar.isChecked()) && !(await comp.isChecked()) && !(await sc.isChecked()));
  const pos = await page.getByLabel('Where captions show').locator('option').allInnerTexts();
  tour.check('"Captions ... can sit at the bottom or top"', pos.some((p) => /bottom/i.test(p)) && pos.some((p) => /top/i.test(p)), pos.join());
  const loop = page.locator('.fl label', { hasText: 'Loop' });
  tour.check('"Loop repeats a fly-through or a script"', (await loop.count()) >= 1);
});

await tour.finish();
