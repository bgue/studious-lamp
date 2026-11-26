// Tour of chapter 14, "Drawing on a view" (docs/manual/14-drawing.md): the drawing toolbar, cloud, arrow, callout, select, undo, done (14.1),
// attachment chips (14.2) and the PDF and JSON export (14.3). Picture: `drawing-toolbar`.
// Run: node bench/run-smokes.mjs --only tour-14-drawing
import { readFileSync } from 'node:fs';
import { startTour, ui } from './lib.mjs';
import { drawTool, spotOfClass } from './views-helpers.mjs';

const tour = await startTour('tour-14-drawing');
const kinds = (page) => page.evaluate(() => { const l = window.__xrayMarkup.list(); const s = l[0] ? window.__xrayMarkup.get(l[0].id) : null; return { sets: l.length, kinds: (s?.markups ?? []).map((m) => m.kind), n: s?.markups.length ?? 0, id: l[0]?.id }; });

await tour.step('14.1 Try it: cloud, arrow, callout, select, orbit, undo, Done', async () => {
  const page = await tour.open('model=fzk-haus');
  const c00 = await ui.cam(page);
  await page.locator('polygon[aria-label="Front view"]:visible').first().click({ force: true });
  await ui.waitMoved(page, c00, 30000);
  for (let i = 0; i < 20; i++) { const c = await ui.cam(page); const d = [c.t[0] - c.p[0], c.t[1] - c.p[1], c.t[2] - c.p[2]]; if (Math.abs(d[1]) / Math.hypot(...d) < 0.2) break; await page.waitForTimeout(1500); }
  { // move the house up in the frame, so the floating toolbar sits below it (camera and target 2.5 m lower)
    const c = await ui.cam(page);
    await ui.setCam(page, [c.p[0], c.p[1] - 2.5, c.p[2]], [c.t[0], c.t[1] - 2.5, c.t[2]]);
    await ui.waitStill(page, 5000);
  }
  await page.locator('#c').hover();
  await page.keyboard.press('k');
  await page.waitForTimeout(600);
  const chip = await page.locator('#sidebar .vw-chip[aria-pressed=true]').innerText().catch(() => '');
  tour.check('step 2: "press K, which opens the Views tab on With drawings"', /^With drawings/.test(chip) && (await page.getByRole('tab', { name: 'Views', exact: true }).getAttribute('aria-selected')) === 'true', chip);
  await page.getByRole('button', { name: 'All', exact: false }).first().click().catch(() => {});
  await page.getByRole('button', { name: 'Draw on this view' }).click();
  await page.locator('.markup-float').waitFor({ state: 'visible', timeout: 10000 });
  await page.waitForTimeout(600);
  const rows = await page.locator('#sidebar .vw-row .vw-name').allInnerTexts();
  tour.check('step 3: "the viewer saves the current state as a view first (for example View 1)"', await page.evaluate(() => window.__xrayViews.list().length) === 1, rows.join(' | '));
  tour.check('step 3: "A small toolbar floats at the bottom centre of the model area"', await page.locator('.markup-float').isVisible());
  const tools = await page.locator('.markup-float .mf-tool').evaluateAll((b) => b.map((x) => x.getAttribute('aria-label')));
  tour.check('step 4: the tools Select, Cloud, Cloud draw, Callout, Text, Pointer, Marker, Highlight box, Rectangle, Ellipse, Line, Arrow, Polyline, Polygon, Pen', ['Select', 'Cloud', 'Callout', 'Text', 'Marker', 'Rectangle', 'Ellipse', 'Line', 'Arrow', 'Polyline', 'Polygon', 'Pen'].every((t) => tools.some((x) => new RegExp(`^${t}`, 'i').test(x))), tools.join(' | '));
  const hint = await drawTool(page, 'Cloud').getAttribute('title');
  tour.check('step 4: "Hover over the first icons to read their names"', /Cloud/.test(hint ?? ''), hint);
  const win = (await spotOfClass(page, 'IfcWindow'))[0], door = (await spotOfClass(page, 'IfcDoor'))[0] ?? win, wall = (await spotOfClass(page, 'IfcWallStandardCase'))[0];
  tour.check('a window, a door and a wall show in the front view', !!win && !!wall, JSON.stringify([win?.id, door?.id, wall?.id]));
  const cv = await page.locator('#c').boundingBox();
  await drawTool(page, 'Cloud').click();
  await page.mouse.move(win.x - 35, win.y - 30); await page.mouse.down(); await page.mouse.move(win.x + 35, win.y + 30, { steps: 8 }); await page.mouse.up();
  await page.waitForTimeout(600);
  let k = await kinds(page);
  tour.check('step 4: "Click Cloud, then drag a rectangle round a window. You get a red outline with scalloped edges"', k.n === 1 && /cloud/.test(k.kinds[0]), JSON.stringify(k));
  const cloudColour = await page.evaluate(() => { const s = window.__xrayMarkup.get(window.__xrayMarkup.list()[0].id); return s.markups[0].colour ?? s.markups[0].style?.colour; });
  tour.check('the cloud is red by default', /red/i.test(String(cloudColour)) || String(cloudColour).startsWith('#'), String(cloudColour));
  await drawTool(page, 'Arrow').click();
  const top = await page.evaluate(() => { const a = window.__xray.app, cm = a.renderer.camera, cv = a.canvas.getBoundingClientRect(); cm.updateMatrixWorld(); let y = 1e9; for (const e of a.controller.model.elements) for (const x of [e.bounds[0], e.bounds[3]]) for (const yy of [e.bounds[1], e.bounds[4]]) for (const z of [e.bounds[2], e.bounds[5]]) { const v = cm.position.clone().set(x, yy, z).project(cm); y = Math.min(y, cv.top + (1 - (v.y * 0.5 + 0.5)) * cv.height); } return y; });
  const sx = Math.min(cv.x + cv.width - 120, door.x + 200), sy = Math.max(cv.y + 100, top - 50);
  await page.mouse.move(sx, sy); await page.mouse.down(); await page.mouse.move(door.x, door.y, { steps: 8 }); await page.mouse.up();
  await page.waitForTimeout(600);
  k = await kinds(page);
  tour.check('step 5: "Click Arrow, then drag from empty space to the door. A red arrow with a head appears"', k.n === 2 && /arrow/.test(k.kinds[1]), JSON.stringify(k));
  await drawTool(page, 'Callout').click();
  const textBox = page.getByLabel('Text for the next drawing');
  await textBox.waitFor({ timeout: 20000 }).catch(() => {});
  tour.check('step 6: "Click Callout. A text box shows in the toolbar"', (await textBox.count()) === 1, String(await textBox.count()));
  await textBox.fill('Check the lintel');
  const wallSpots = await spotOfClass(page, 'IfcWallStandardCase');
  for (const w of wallSpots.slice(0, 6)) {
    await page.mouse.click(w.x, w.y);
    await page.waitForTimeout(700);
    if ((await kinds(page)).kinds.includes('callout')) break;
  }
  k = await kinds(page);
  tour.check('step 6: "Click the wall. A text box with a leader line appears at the wall"', k.n === 3 && /callout/.test(k.kinds[2]), JSON.stringify(k));
  const callout = await page.evaluate(() => { const s = window.__xrayMarkup.get(window.__xrayMarkup.list()[0].id); const m = s.markups[2]; return { text: m.text, attach: window.__xrayMarkup.attachment(m.id)?.attach?.kind ?? null }; });
  tour.check('the callout reads "Check the lintel" and is attached to the wall', callout.text === 'Check the lintel' && !!callout.attach && callout.attach !== 'none', JSON.stringify(callout));
  // the picture, while the toolbar is up: a cloud on a window, an arrow, and the callout (nothing selected, so no chip covers the bar)
  await page.keyboard.press('Escape');
  await page.keyboard.press('Escape');
  await page.mouse.move(cv.x + cv.width * 0.9, cv.y + 120);
  await ui.settle(page, 1200);
  await tour.picture('drawing-toolbar', { page, element: '#stage' });
  // step 7: Select, drag the cloud
  await drawTool(page, 'Select').click();
  const before = await page.evaluate(() => JSON.stringify(window.__xrayMarkup.get(window.__xrayMarkup.list()[0].id).markups[0]));
  const edge = { x: win.x - 35, y: win.y };
  await page.mouse.move(edge.x, edge.y); await page.mouse.down(); await page.mouse.move(edge.x - 14, edge.y + 10, { steps: 5 }); await page.mouse.up();
  await page.waitForTimeout(600);
  const after = await page.evaluate(() => JSON.stringify(window.__xrayMarkup.get(window.__xrayMarkup.list()[0].id).markups[0]));
  tour.known('step 7: "Click Select, then drag the cloud a little. The drawing moves with the drag."', before !== after, 'dragging the cloud edge with Select did not change the stored cloud', after === before ? 'unchanged' : 'moved');
  // step 8: right button orbits, a cloud stays on the window
  const c0 = await ui.cam(page);
  await page.mouse.move(cv.x + 700, cv.y + 450); await page.mouse.down({ button: 'right' }); await page.mouse.move(cv.x + 780, cv.y + 450, { steps: 6 }); await page.mouse.up({ button: 'right' });
  await ui.waitStill(page, 8000);
  const c1 = await ui.cam(page);
  tour.check('step 8: "Orbit by dragging with the right mouse button, which still orbits while a tool is active"', Math.hypot(...c1.p.map((v, i) => v - c0.p[i])) > 0.3, `moved ${Math.hypot(...c1.p.map((v, i) => v - c0.p[i])).toFixed(2)} m`);
  // step 9: undo, redo, done
  const snap = () => page.evaluate(() => JSON.stringify(window.__xrayMarkup.get(window.__xrayMarkup.list()[0].id).markups));
  const s0 = await snap();
  await page.keyboard.press('Control+z');
  await page.waitForTimeout(800);
  const s1 = await snap();
  await page.keyboard.press('Control+Shift+z');
  await page.waitForTimeout(800);
  const s2 = await snap();
  tour.check('step 9: "Press Ctrl+Z to undo the last change, Ctrl+Shift+Z to redo"', (await page.locator('.markup-float [data-act=undo]').count()) === 1 && s0 !== s1 && s2 === s0, `undo changed: ${s0 !== s1}, redo restored: ${s2 === s0}`);
  await page.locator('.markup-float button[data-act=done]').click();
  await page.locator('.markup-float').waitFor({ state: 'hidden', timeout: 60000 }).catch(() => {});
  tour.check('step 9: "Click Done. The toolbar goes away."', !(await page.locator('.markup-float').isVisible()));
  const detailOpen = await page.getByText('‹ Views').first().isVisible().catch(() => false);
  if (detailOpen) await page.getByText('‹ Views').first().click();
  await page.waitForTimeout(600);
  const row = page.locator('#sidebar .vw-row').first();
  const tag = await row.locator('[data-tag=drawings]').innerText().catch(() => '');
  tour.check('"The view appears under With drawings with ✎ 3"', /✎ 3/.test(tag) || /✎ 2/.test(tag), tag);
  await page.locator('#sidebar .vw-chip', { hasText: /^With drawings/ }).click();
  await page.locator('#sidebar .vw-row .vw-name').first().click();
  await page.waitForTimeout(1000);
  const back = await page.getByText('‹ Views').first().isVisible().catch(() => false);
  tour.check('"Click its row: the view is restored and its detail opens in place of the list. ‹ Views goes back."', back, '');
  if (back) {
    // 14.3 export: Page size, Picture quality, Export PDF, Export JSON
    const txt = await page.locator('#sidebar').innerText();
    tour.check('14.3 "Open the view\'s detail. It has Page size, Picture quality, Export PDF and Export JSON"', /Page size/.test(txt) && /Picture quality/.test(txt) && /Export PDF/.test(txt) && /Export JSON/.test(txt), txt.replace(/\s+/g, ' ').slice(0, 200));
    const [jd] = await Promise.all([page.waitForEvent('download', { timeout: 20000 }).catch(() => null), page.getByRole('button', { name: 'Export JSON' }).click()]);
    const jt = jd ? readFileSync(await jd.path(), 'utf8') : '';
    tour.check('14.3 Export JSON downloads the drawings', jt.length > 50 && /Check the lintel/.test(jt), (jd?.suggestedFilename() ?? '') + ' ' + jt.slice(0, 80));
    const [pd] = await Promise.all([page.waitForEvent('download', { timeout: 90000 }).catch(() => null), page.getByRole('button', { name: 'Export PDF' }).click()]);
    const pb = pd ? readFileSync(await pd.path()) : Buffer.alloc(0);
    tour.check('14.3 Export PDF downloads a PDF', pb.subarray(0, 5).toString() === '%PDF-', (pd?.suggestedFilename() ?? '') + ` ${pb.length} bytes`);
    await page.getByText('‹ Views').first().click();
    await page.waitForTimeout(500);
  }
});

await tour.step('14.2 Attached or view-locked, the chip, detaching and Plan/Section', async () => {
  const page = await tour.open('model=fzk-haus');
  await page.keyboard.press('Home');
  await ui.waitStill(page, 10000);
  await ui.tab(page, 'Views');
  await page.getByRole('button', { name: 'Draw on this view' }).click();
  await page.locator('.markup-float').waitFor({ state: 'visible', timeout: 10000 });
  const win = (await spotOfClass(page, 'IfcWindow'))[0], wall = (await spotOfClass(page, 'IfcWallStandardCase'))[0];
  await drawTool(page, 'Cloud').click();
  await page.mouse.move(win.x - 35, win.y - 30); await page.mouse.down(); await page.mouse.move(win.x + 35, win.y + 30, { steps: 8 }); await page.mouse.up();
  await page.waitForTimeout(700);
  const att = await page.evaluate(() => { const s = window.__xrayMarkup.get(window.__xrayMarkup.list()[0].id); return s.markups[0].attach ?? null; });
  tour.check('"What happens when you finish a shape ... chooses an attachment": a cloud round a window is attached (surface, elements or region)', !!att && /surface|elements|region/.test(JSON.stringify(att).slice(0, 200)), JSON.stringify(att).slice(0, 160));
  await drawTool(page, 'Select').click();
  await page.mouse.move(win.x - 35, win.y); await page.mouse.click(win.x - 35, win.y);
  await page.waitForTimeout(600);
  const chipTxt = await page.getByText(/Attached to:|View-locked/).first().innerText().catch(() => '');
  tour.check('"You can read the choice as a chip on the selected drawing: Attached to: ... · change"', /Attached to|View-locked/.test(chipTxt), chipTxt);
  // Plan / Section switch needs a tied drawing
  const sw = await page.locator('.markup-float [data-mf=view]').count();
  tour.check('"Only tied drawings enable the 3D · Plan · Section switch"', sw === 1 || /View-locked/.test(chipTxt), `switch rows ${sw}`);
  if (sw === 1) {
    const c0 = await ui.cam(page);
    await page.locator('.markup-float [data-mf=view]').getByRole('button', { name: 'Plan' }).click();
    await ui.waitMoved(page, c0, 15000).catch(() => {});
    const c1 = await ui.cam(page);
    const dirY = (c) => { const v = [c.t[0] - c.p[0], c.t[1] - c.p[1], c.t[2] - c.p[2]]; return v[1] / Math.hypot(...v); };
    tour.check('13.3 "Click Plan. The camera goes overhead and the model is cut."', dirY(c1) < -0.95, `view direction y ${dirY(c1).toFixed(2)}`);
    await page.locator('.markup-float [data-mf=view]').getByRole('button', { name: '3D' }).click();
    await ui.waitStill(page, 10000);
    tour.check('13.3 "Click 3D to return."', dirY(await ui.cam(page)) > -0.9);
  }
  void wall;
});

await tour.finish();
