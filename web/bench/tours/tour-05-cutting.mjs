// Tour of chapter 5, "Cutting and peeling" (docs/manual/05-cutting.md): the Try it of 5.1 (peel and behind-only on a window of FZK-Haus), 5.2 (section box and
// plane) and 5.3 (exploded view on Synthetic 5k). Picture: `peel-behind-states`.
// Run: node bench/run-smokes.mjs --only tour-05-cutting
import { startTour, ui } from './lib.mjs';

const tour = await startTour('tour-05-cutting');
const vm = (page) => page.evaluate(() => { const c = window.__xrayViewModes.config; return { peel: c.peel.enabled, outside: c.peel.outside, radius: c.peel.radius, behind: c.behind.enabled, front: c.behind.frontTreatment, xray: window.__xray.app.settings.xray }; });
const sec = (page) => page.evaluate(() => { const c = window.__xraySection.config; return JSON.parse(JSON.stringify({ box: c.box, plane: c.plane, caps: c.caps })); });

await tour.step('5.1 Try it steps 1-4: window, P, Alt+=, Cutaway, Shift+1, B, Shift+B, B', async () => {
  const page = await tour.open('model=fzk-haus');
  const win = await ui.clickElement(page, { cls: 'IfcWindow' });
  tour.check('step 1: "Click a window in an outside wall."', !!win, JSON.stringify(win));
  await ui.waitStill(page, 15000);
  await page.keyboard.press('p');
  await ui.settle(page, 1500);
  const a = await vm(page);
  const xr = await ui.xray(page);
  tour.check('step 2: "Press P. A window opens in what hides the selected window"', a.peel, JSON.stringify(a));
  tour.check('step 2: "The rest of the model is ghosted."', a.outside === 'x-ray' && xr.faint > 0, `${xr.faint} faint, outside=${a.outside}`);
  await page.keyboard.press('Alt+='); await page.waitForTimeout(200); await page.keyboard.press('Alt+=');
  await ui.settle(page, 800);
  const b = await vm(page);
  tour.check('step 2: "Press Alt+= once or twice to widen the opening."', b.radius > a.radius * 1.4, `radius ${a.radius} -> ${b.radius}`);
  const camBefore = await ui.cam(page);
  await ui.mode(page, 'Cutaway');
  await page.waitForTimeout(1500); await ui.settle(page, 800);
  const c = await vm(page);
  const camAfter = await ui.cam(page);
  tour.check('step 3: "Click Cutaway. The wall is solid around the opening: peeling with outside set to solid"', c.peel && c.outside === 'solid', JSON.stringify(c));
  const spot = await ui.spotOf(page, win.id);
  const cv = await page.locator('#c').boundingBox();
  tour.check('step 3: "and it frames the selection for you": the window is in the middle of the view', !!spot && Math.abs(spot.x - (cv.x + cv.width / 2)) < cv.width * 0.3 && Math.abs(spot.y - (cv.y + cv.height / 2)) < cv.height * 0.3, spot ? `at ${Math.round(spot.x)},${Math.round(spot.y)} in ${cv.width}x${cv.height}` : 'not in view');
  await page.keyboard.press('Shift+1');
  await ui.settle(page, 1200);
  const d = await vm(page);
  tour.check('step 4: "Press Shift+1 to go back to the plain x-ray"', !d.peel && d.xray && (await ui.litMode(page)) === 'Ghost', JSON.stringify(d));
  await page.keyboard.press('b');
  await ui.settle(page, 1500);
  const e = await vm(page);
  tour.check('step 4: "then press B. A plane cuts everything in front of the window"', e.behind, JSON.stringify(e));
  const seen = [e.front];
  for (let i = 0; i < 3; i++) { await page.keyboard.press('Shift+B'); await page.waitForTimeout(500); seen.push((await vm(page)).front); }
  tour.check('step 4: "Press Shift+B to try the other treatments": cut, ghost, cut + cap', new Set(seen.slice(0, 3)).size === 3 && ['cut', 'ghost', 'cut + cap'].every((t) => seen.includes(t)), seen.join(' > '));
  await page.keyboard.press('b');
  await ui.settle(page, 800);
  tour.check('step 4: "Press B again to switch it off."', !(await vm(page)).behind);
});

await tour.step('5.1 picture: ghosted, peeled with solid surroundings, behind-only with cap', async () => {
  const page = await tour.open('model=fzk-haus');
  const win = await ui.clickElement(page, { cls: 'IfcWindow' });
  await page.keyboard.press('f');
  await page.waitForTimeout(1500); await ui.settle(page, 800);
  await ui.park(page);
  await ui.settle(page, 1500); // Ghost is already lit at start; Shift+1 on a lit mode would switch to Solid
  const ghost = await tour.shot(page, { element: '#stage' });
  await page.keyboard.press('Shift+4'); await page.waitForTimeout(1500); await ui.settle(page, 1500);
  const peel = await tour.shot(page, { element: '#stage' });
  await page.keyboard.press('Shift+1'); await ui.settle(page, 1000);
  await page.keyboard.press('b'); await ui.settle(page, 800);
  for (let i = 0; i < 3 && (await vm(page)).front !== 'cut + cap'; i++) { await page.keyboard.press('Shift+B'); await page.waitForTimeout(400); }
  await ui.settle(page, 1500);
  const cap = await tour.shot(page, { element: '#stage' });
  tour.check('behind-only reached the "cut + cap" treatment for the picture', !!win && (await vm(page)).front === 'cut + cap', (await vm(page)).front);
  await tour.pictureRow('peel-behind-states', [{ buf: ghost, label: 'Ghosted (Shift+1)' }, { buf: peel, label: 'Peeled, surroundings solid (Shift+4)' }, { buf: cap, label: 'Behind-only with cap (B, Shift+B)' }]);
});

await tour.step('5.2 Try it steps 1-6: Shift+C, handles, Y, Flip, Caps, arrow and ring, Clear', async () => {
  const page = await tour.open('model=fzk-haus');
  const el = await ui.clickElement(page, { cls: /Wall/ });
  await ui.park(page);
  const bounds = await page.evaluate((id) => window.__xray.app.controller.model.elements.find((e) => e.id === id).bounds, el.id);
  await page.keyboard.press('Shift+c');
  await ui.settle(page, 1500);
  const s1 = await sec(page);
  const size = s1.box.max.map((v, i) => v - s1.box.min[i]);
  const want = [bounds[3] - bounds[0] + 1, bounds[4] - bounds[1] + 1, bounds[5] - bounds[2] + 1];
  tour.check('step 1: "A section box fits around the selection with a margin of 0.5 m and switches on."', s1.box.enabled && size.every((v, i) => Math.abs(v - want[i]) < 0.05), `box ${size.map((v) => v.toFixed(2))} vs selection+1 m ${want.map((v) => v.toFixed(2))}`);
  const dots = page.locator('svg circle[r="7"][visibility="visible"]');
  await dots.first().waitFor({ timeout: 10000 }).catch(() => {});
  const n = await dots.count();
  tour.check('step 2: "Six round handles appear on the box faces" (those on the near side are drawn)', n >= 3, `${n} visible of 6`);
  const bx = await dots.first().boundingBox();
  const before = JSON.stringify((await sec(page)).box);
  await page.mouse.move(bx.x + bx.width / 2, bx.y + bx.height / 2);
  await page.mouse.down();
  await page.mouse.move(bx.x + bx.width / 2 + 25, bx.y + bx.height / 2 + 25, { steps: 6 });
  const readout = await page.locator('text.xs-readout').first().evaluate((t) => t.getAttribute('visibility') === 'visible' ? t.textContent : null).catch(() => null);
  await page.mouse.up();
  await ui.settle(page, 800);
  tour.check('step 2: "Drag one: that face moves along its axis."', JSON.stringify((await sec(page)).box) !== before);
  tour.check('step 2: "A readout shows the face position and the size of the box."', !!readout, String(readout));
  // a face stops 5 cm before the opposite one
  const bx2 = await dots.first().boundingBox();
  await page.mouse.move(bx2.x + bx2.width / 2, bx2.y + bx2.height / 2); await page.mouse.down();
  await page.mouse.move(bx2.x + bx2.width / 2 - 900, bx2.y + bx2.height / 2 - 900, { steps: 10 }); await page.mouse.up();
  await ui.settle(page, 600);
  const s2 = await sec(page);
  const gaps = s2.box.max.map((v, i) => v - s2.box.min[i]);
  tour.check('step 2: "A face stops 5 cm before the opposite one."', Math.min(...gaps) >= 0.049, `smallest side ${Math.min(...gaps).toFixed(3)} m`);
  // step 3: Y
  const strip = page.locator('#xray-gizmo');
  await strip.getByRole('button', { name: /^Section plane Y/ }).click();
  await ui.settle(page, 800);
  const p1 = await sec(page);
  tour.check('step 3: "click Y. A plane square to the vertical axis cuts the model through the centre of the selection"', p1.plane.enabled && p1.plane.axis === 'y', JSON.stringify(p1.plane));
  await strip.getByRole('button', { name: /^Section plane Y/ }).click();
  tour.check('step 3: "Click Y again to remove it."', !(await sec(page)).plane.enabled);
  for (const ax of ['X', 'Z']) {
    await strip.getByRole('button', { name: new RegExp(`^Section plane ${ax}`) }).click();
    const q = await sec(page);
    tour.check(`step 3: "${ax} cuts the other two ways"`, q.plane.enabled && q.plane.axis === ax.toLowerCase(), JSON.stringify(q.plane));
  }
  await strip.getByRole('button', { name: /^Section plane Y/ }).click();
  // step 4
  const f0 = (await sec(page)).plane.flip;
  await strip.getByRole('button', { name: 'Flip the section plane' }).click();
  tour.check('step 4: "Click Flip to keep the other side."', (await sec(page)).plane.flip !== f0);
  const c0 = (await sec(page)).caps;
  await strip.getByRole('button', { name: 'Caps on cut solids' }).click();
  tour.check('step 4: "Click Caps to turn the hatched caps on or off."', (await sec(page)).caps !== c0);
  // step 5: arrow
  await ui.settle(page, 800);
  const head = page.locator('.xg-arrow-head').first();
  const hb = await head.boundingBox();
  if (hb) {
    const o0 = (await sec(page)).plane.offset;
    await page.mouse.move(hb.x + hb.width / 2, hb.y + hb.height / 2); await page.mouse.down();
    await page.mouse.move(hb.x + hb.width / 2 + 10, hb.y + hb.height / 2 - 40, { steps: 6 });
    const ro = await page.locator('text.xg-readout').first().evaluate((t) => t.getAttribute('visibility') === 'visible' ? t.textContent : null).catch(() => null);
    await page.mouse.up();
    await ui.settle(page, 600);
    const o1 = (await sec(page)).plane.offset;
    tour.check('step 5: "Drag the arrow on the plane to push or pull it."', Math.abs(o1 - o0) > 0.02, `offset ${o0.toFixed(2)} -> ${o1.toFixed(2)}`);
    tour.check('step 5: "A readout shows the offset in metres."', !!ro && /m/.test(ro), String(ro));
  } else tour.check('step 5: the arrow on the plane is drawn', false, 'no .xg-arrow-head box');
  const ring = page.locator('.xg-ring-0').first();
  const rb = await ring.boundingBox().catch(() => null);
  if (rb) {
    const ax0 = JSON.stringify((await sec(page)).plane);
    // grab the ring at the middle of its stroke: use the polyline's first point
    const pt = await ring.evaluate((p) => { const pts = p.getAttribute('points').trim().split(/\s+/).map((s) => s.split(',').map(Number)); const m = pts[Math.floor(pts.length / 4)]; const r = p.ownerSVGElement.getBoundingClientRect(); return { x: r.left + m[0], y: r.top + m[1] }; });
    await page.mouse.move(pt.x, pt.y); await page.mouse.down(); await page.mouse.move(pt.x + 20, pt.y + 45, { steps: 8 }); await page.mouse.up();
    await ui.settle(page, 600);
    const pl = (await sec(page)).plane;
    tour.check('step 5: "Drag a ring to tilt the plane in steps of 15 degrees."', JSON.stringify(pl) !== ax0 && pl.axis === 'custom', JSON.stringify(pl));
  } else tour.check('step 5: a ring is drawn on the plane', false, 'no .xg-ring-0');
  // step 6
  await strip.getByRole('button', { name: 'Clear the section' }).click();
  await ui.settle(page, 500);
  const z = await sec(page);
  tour.check('step 6: "Click Clear to remove everything."', !z.box.enabled && !z.plane.enabled, JSON.stringify({ box: z.box.enabled, plane: z.plane.enabled }));
});

await tour.step('5.3 Try it steps 1-3: Synthetic 5k, select everything, Cinematic, Exploded view, Mode storeys, Explode', async () => {
  const page = await tour.open('model=synth5k');
  const m = await ui.model(page);
  tour.check('"Open Synthetic 5k (needs the served app)": it opens with several storeys', m.name === 'synth5k' && m.n > 4000, `${m.n} elements`);
  await page.locator('#c').hover();
  await page.keyboard.press('Control+a');
  await ui.settle(page, 1000);
  const sel = await ui.selection(page);
  tour.check('step 1: "press Ctrl+A to select everything visible"', sel.length > 1000, `${sel.length} selected`);
  await ui.tab(page, 'Parameters'); await ui.topOfPanel(page);
  await ui.folder(page, 'Cinematic');
  await ui.folder(page, 'Exploded view');
  await ui.set(page, 'Mode', 'storeys');
  tour.check('step 2: "Set Mode to storeys"', (await ui.valueOf(page, 'Mode')) === 'storeys');
  tour.check('step 3: "Storey gap (m) (default 3 m)"', Number(await ui.valueOf(page, 'Storey gap (m)')) === 3, String(await ui.valueOf(page, 'Storey gap (m)')));
  await ui.press(page, 'Explode');
  await page.waitForTimeout(2000); await ui.settle(page, 800);
  tour.check('step 3: "Click Explode. The floors slide apart vertically."', await page.evaluate(() => window.__cinematic.exploded), '');
  const label = await page.evaluate(() => [...document.querySelectorAll('.lil-controller')].map((c) => c.querySelector('.lil-name')?.textContent.trim()).filter((t) => t === 'Explode' || t === 'Collapse'));
  tour.check('the button is renamed Collapse after the first click (the manual says so)', label.includes('Collapse') && !label.includes('Explode'), label.join());
  await ui.press(page, 'Collapse').catch(() => ui.press(page, 'Explode'));
  await page.waitForTimeout(2000); await ui.settle(page, 500);
  tour.check('step 3: pressing it again slides the floors back', !(await page.evaluate(() => window.__cinematic.exploded)));
});

await tour.finish();
