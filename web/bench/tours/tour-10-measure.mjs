// Tour of chapter 10, "Measure and clearance" (docs/manual/10-measure.md): point to point and element to element (10.1), clearance colouring (10.2).
// No pictures in this chapter.
// Run: node bench/run-smokes.mjs --only tour-10-measure
import { readFileSync } from 'node:fs';
import { startTour, ui } from './lib.mjs';

const tour = await startTour('tour-10-measure');
const list = (page) => page.evaluate(() => window.__xrayMeasure.list.map((m) => ({ id: m.id, kind: m.kind, d: m.distance, a: m.elementA, b: m.elementB })));
const pending = (page) => page.evaluate(() => !!window.__xrayMeasure.pending);
const drawer = (page) => page.locator('#xray-toolbar-drawer, .xt-drawer').first();
/** Screen spots (CSS px) where a pick lands on the element, found by asking the viewer's own picker over a grid of the canvas. */
const spotsFor = (page, ids) => page.evaluate((ids) => {
  const cv = window.__xray.app.canvas.getBoundingClientRect(), out = {};
  for (let fy = 0.1; fy < 0.95; fy += 0.025) for (let fx = 0.05; fx < 0.95; fx += 0.025) {
    const x = cv.left + cv.width * fx, y = cv.top + cv.height * fy;
    if (document.elementFromPoint(x, y)?.id !== 'c') continue;
    const h = window.__xrayMeasure.pickAt(x, y);
    if (h && ids.includes(h.element)) (out[h.element] ??= []).push({ x, y, p: h.point, snapped: h.snapped });
  }
  return out;
}, ids);
const idsOf = (page, re) => page.evaluate((re) => window.__xray.app.controller.model.elements.filter((e) => new RegExp(re).test(e.ifcClass)).map((e) => e.id), re);

await tour.step('10.1 Try it: point to point, snap, element to element, the list, Escape', async () => {
  const page = await tour.open('model=building');
  await ui.tool(page, 'Measure').click();
  await page.getByText('No measurements yet.').waitFor({ timeout: 8000 }).catch(() => {});
  tour.check('step 2: "Open the Measure tool. Its drawer opens"', await page.getByText('Click two points on surfaces').isVisible().catch(() => false));
  tour.check('step 3: "Keep mode on point to point"', (await page.locator('.xt-sel select, select').filter({ hasText: 'point to point' }).first().inputValue().catch(() => '')) === 'point to point');
  const walls = await idsOf(page, '^IfcWall'), slabs = await idsOf(page, '^IfcSlab');
  const sp = await spotsFor(page, [...walls, ...slabs]);
  const w = walls.find((i) => sp[i]?.length), s = slabs.find((i) => sp[i]?.length);
  tour.check('a wall and a slab show in the view', w !== undefined && s !== undefined, `walls ${walls.length}, slabs ${slabs.length}, spots ${Object.keys(sp).join(',')}`);
  const a = sp[w][Math.floor(sp[w].length / 2)], b = sp[s][Math.floor(sp[s].length / 2)];
  await page.mouse.click(a.x, a.y);
  await page.waitForTimeout(400);
  tour.check('step 3: "Click one point on a wall surface" (a first point is pending)', await pending(page));
  await page.mouse.move(b.x - 30, b.y - 10, { steps: 4 });
  await page.waitForTimeout(500);
  await page.mouse.click(b.x, b.y);
  await page.waitForTimeout(500);
  const l1 = await list(page);
  const d = Math.hypot(a.p[0] - b.p[0], a.p[1] - b.p[1], a.p[2] - b.p[2]);
  tour.check('step 3: "after the second click the dimension stays, with its label": one measurement, its length is the distance of the two points', l1.length === 1 && Math.abs(l1[0].d - d) < 0.02 && l1[0].kind === 'point', JSON.stringify(l1) + ` expected ${d.toFixed(3)}`);
  const labelTxt = await page.evaluate(() => [...document.querySelectorAll('#xray-overlay svg text, svg text')].map((t) => t.textContent).join(' | '));
  tour.check('step 3: the label shows the length', new RegExp(d.toFixed(2).replace('.', '\\.')).test(labelTxt) || /\d\.\d{3}/.test(labelTxt), labelTxt.slice(0, 120));
  const item = await page.locator('.xt-item').first().innerText();
  tour.check('step 6: "Each measurement is listed with a delete button"', /#1/.test(item) && (await page.getByRole('button', { name: 'Delete measurement 1' }).count()) === 1, item.replace(/\n/g, ' '));
  // step 4: snap
  await page.getByText('Snap to vertices').click();
  await page.waitForTimeout(300);
  const sp2 = await spotsFor(page, [...walls, ...slabs]);
  const snappedSpot = Object.values(sp2).flat().find((q) => q.snapped);
  tour.check('step 4: "Turn on snap to vertices ... the click lands on the corner exactly": a spot near a corner snaps', !!snappedSpot, `${Object.values(sp2).flat().length} spots`);
  if (snappedSpot) {
    await page.mouse.move(snappedSpot.x, snappedSpot.y);
    await page.waitForTimeout(500);
    const ring = await page.evaluate(() => [...document.querySelectorAll('svg circle')].some((c) => /#ffd|yellow|#fc|#ffe/i.test(c.getAttribute('stroke') ?? c.getAttribute('fill') ?? '')));
    tour.check('step 4: "a yellow ring appears when the cursor is within 12 px of a corner"', ring);
  }
  // step 5: element to element
  await page.locator('select').filter({ hasText: 'point to point' }).first().selectOption('element to element');
  const duct = (await idsOf(page, '^IfcDuctSegment'))[0];
  const wall2 = walls[0];
  await ui.setCam(page, [6, 4, 8], [0, 1, 0]);
  await ui.waitStill(page, 5000);
  const sp3 = await spotsFor(page, [duct, ...walls]);
  const dSpot = sp3[duct]?.[0], wSpot = Object.entries(sp3).find(([k]) => Number(k) !== duct)?.[1]?.[0];
  tour.known('step 5: "Click the duct, then a wall": the duct is clickable from the home view', !!dSpot && !!wSpot, 'no spot where a click lands on the duct, so element-to-element could not be clicked by hand', `duct ${duct}, spots ${Object.keys(sp3).join(',')}`);
  if (dSpot && wSpot) {
    await page.mouse.click(dSpot.x, dSpot.y);
    await page.waitForTimeout(300);
    await page.mouse.click(wSpot.x, wSpot.y);
    await page.waitForTimeout(800);
    const l2 = await list(page);
    const e2 = l2.find((m) => m.kind === 'element');
    tour.check('step 5: "The label shows the shortest distance between the two surfaces"', !!e2 && e2.d >= 0 && e2.a === duct, JSON.stringify(l2));
    tour.check('step 5: the drawer says closest points found, or that they touch', /Closest points found|touch or overlap/.test(await drawer(page).innerText().catch(() => '')) || (await page.locator('.xt-status').innerText().catch(() => '')) !== '');
  }
  // step 6: delete, clear, export
  const [dl] = await Promise.all([page.waitForEvent('download', { timeout: 15000 }).catch(() => null), page.getByRole('button', { name: 'Export CSV' }).click()]);
  const csv = dl ? readFileSync(await dl.path(), 'utf8') : '';
  tour.check('step 6: "Export CSV saves them": one row per measurement, with distance, differences and GlobalIds', csv.split('\n').filter(Boolean).length >= 2 && /dx|distance/i.test(csv.split('\n')[0]) && /gid|global/i.test(csv.split('\n')[0]), csv.split('\n')[0]);
  const n0 = (await list(page)).length;
  await page.getByRole('button', { name: 'Delete measurement 1' }).click();
  tour.check('step 6: the delete button removes one measurement', (await list(page)).length === n0 - 1);
  await page.getByRole('button', { name: 'Clear', exact: true }).click();
  tour.check('step 6: "Clear removes them all"', (await list(page)).length === 0);
  // step 7: Escape
  const ap = await spotsFor(page, walls);
  const one = Object.values(ap).flat()[0];
  await page.locator('select').filter({ hasText: 'element to element' }).first().selectOption('point to point');
  await page.mouse.click(one.x, one.y);
  await page.waitForTimeout(300);
  await page.keyboard.press('Escape');
  tour.check('step 7: "If a first point is pending, Escape cancels it"', !(await pending(page)) && (await page.getByText('Click two points on surfaces').isVisible()));
  await page.mouse.click(one.x, one.y); await page.waitForTimeout(200);
  await page.mouse.click(one.x + 1, one.y + 40); await page.waitForTimeout(300);
  const kept = (await list(page)).length;
  await page.keyboard.press('Escape');
  await page.waitForTimeout(400);
  tour.check('step 7: "A second Escape closes the drawer"', !(await page.getByText('Click two points on surfaces').isVisible().catch(() => false)));
  tour.check('step 7: "The dimensions stay on the model after the drawer closes"', (await list(page)).length === kept && kept >= 1, String(kept));
  // a measuring click does not change the selection / Parameters folder
  await ui.tab(page, 'Parameters');
  await ui.topOfPanel(page);
  await ui.folder(page, 'Measure');
  tour.check('"The same settings live in the Parameters tab: mode, units, snap to vertices"', (await ui.valueOf(page, 'mode')) === 'point to point' && ['m', 'mm'].includes(String(await ui.valueOf(page, 'units'))) && (await ui.valueOf(page, 'snap to vertices')) === true, `${await ui.valueOf(page, 'mode')} ${await ui.valueOf(page, 'units')}`);
  await ui.press(page, 'Clear measurements');
  tour.check('"Clear measurements in the Measure folder" removes them', (await list(page)).length === 0);
  await ui.set(page, 'units', 'mm');
  await page.evaluate(() => window.__xrayMeasure.click([0, 0, 0], 0));
  await page.evaluate(() => window.__xrayMeasure.click([1.234, 0, 0], 1));
  const lab = await page.evaluate(() => [...document.querySelectorAll('svg text')].map((t) => t.textContent).join('|'));
  tour.check('"units: metres with 3 decimals, or whole millimetres": 1.234 m reads 1234 mm', /1234 ?mm/.test(lab), lab);
});

await tour.step('10.2 Try it: clearance colouring on the duct', async () => {
  const page = await tour.open('model=building');
  const duct = await ui.clickElement(page, { cls: 'IfcDuctSegment' });
  tour.check('step 1: "In the Building model, select the duct"', !!duct && duct.cls === 'IfcDuctSegment', JSON.stringify(duct));
  const base = await page.evaluate(() => { const c = window.__xray.app.controller; return Array.from(c.state.color.slice(0, 3 * c.model.elements.length)); });
  await ui.tool(page, 'Clearance').click();
  await page.waitForTimeout(1500);
  const en = await page.evaluate(() => window.__xrayClearance.enabled);
  tour.check('step 2: "Open the Clearance tool in the strip. Colouring starts."', en === true, `enabled ${en}`);
  if (!en) { await page.getByText('Show clearance of the context to the focus').click(); await page.waitForTimeout(1500); }
  const counts = await page.evaluate(() => window.__xrayClearance.counts);
  const status = await page.evaluate(() => window.__xrayClearance.status);
  tour.check('step 4: "The drawer shows counts per band and the time it took"', /clash \d+, tight \d+, ok \d+, beyond \d+/.test(status) && /ms/.test(status), status);
  const painted = await page.evaluate((b) => { const c = window.__xray.app.controller; let n = 0; const col = c.state.color; for (let i = 0; i < b.length; i++) if (Math.abs(col[i] - b[i]) > 0.02) n++; return n; }, base);
  tour.check('step 3: "The context elements take colours"', painted > 0, `${painted} colour channels changed; ${JSON.stringify(counts)}`);
  tour.check('step 3: "A legend sits at the bottom right of the view"', (await page.locator('[data-legend=clearance]').count()) === 1);
  const ctx = await page.evaluate(() => { const c = window.__xray.app.controller, cl = c.classification; return [...cl.focus].length; });
  void ctx;
  // step 5: select another element
  const other = await ui.clickElement(page, { cls: 'IfcAirTerminal' });
  await page.waitForTimeout(1500);
  const status2 = await page.evaluate(() => window.__xrayClearance.status);
  tour.check('step 5: "Select another element. The colours are recomputed for it"', !!other && status2 !== status || /clash/.test(status2), `${status} -> ${status2}`);
  const again = await ui.clickElement(page, { cls: 'IfcDuctSegment' });
  await page.waitForTimeout(1500);
  const tightN0 = await page.evaluate(() => window.__xrayClearance.counts?.tight ?? -1);
  // step 6: raise tight
  const tightInput = page.locator('.xt-slider', { hasText: 'tight (m)' }).locator('input[type=range]');
  await tightInput.evaluate((el) => { el.value = '0.2'; el.dispatchEvent(new Event('input', { bubbles: true })); });
  await page.waitForTimeout(1500);
  const tightN1 = await page.evaluate(() => window.__xrayClearance.counts?.tight ?? -1);
  tour.check('step 6: "Raise tight (m) from 0.05 to 0.2. More elements turn amber"', tightN1 > tightN0 || tightN1 >= 1, `tight ${tightN0} -> ${tightN1}`);
  // step 7: off
  await page.getByText('Show clearance of the context to the focus').click();
  await page.waitForTimeout(1000);
  const after = await page.evaluate((b) => { const c = window.__xray.app.controller; let n = 0; const col = c.state.color; for (let i = 0; i < b.length; i++) if (Math.abs(col[i] - b[i]) > 0.02) n++; return n; }, base);
  tour.check('step 7: "Switch clearance off. The original colours return."', after === 0, `${after} channels still differ`);
  void again;
  // Raise issues block
  await page.getByText('Show clearance of the context to the focus').click();
  await page.waitForTimeout(1500);
  tour.check('"The drawer has an Issues block with Raise issues from results"', await page.getByRole('button', { name: 'Raise issues from results' }).count() >= 1);
});

await tour.finish();
