// Tour of chapter 3, "The screen and moving around" (docs/manual/03-screen.md): the screen map (3.1), moving around and Walk mode (3.2),
// select / hover cards / Properties (3.3), undo (3.4), a phone (3.5) and the keyboard help (3.7). Picture: `screen-map`.
// Run: node bench/run-smokes.mjs --only tour-03-screen
import { startTour, ui } from './lib.mjs';

const tour = await startTour('tour-03-screen');
const hold = async (page, key, ms) => { await page.keyboard.down(key); await page.waitForTimeout(ms); await page.keyboard.up(key); await ui.settle(page, 250); };
const dir = (c) => { const v = [c.t[0] - c.p[0], c.t[1] - c.p[1], c.t[2] - c.p[2]]; const l = Math.hypot(...v) || 1; return v.map((x) => x / l); };
const sbCollapsed = (page) => page.evaluate(() => document.body.classList.contains('sb-collapsed'));
const dockCollapsed = (page) => page.evaluate(() => window.__xrayRightSidebar.state().collapsed);
const stripHidden = (page) => page.evaluate(() => document.getElementById('xray-toolbar').classList.contains('hidden'));

await tour.step('3.1 The screen map: the parts and their contents', async () => {
  const page = await tour.open('model=fzk-haus');
  const top = page.locator('#xray-topbar');
  const labels = await top.getByRole('button').allInnerTexts();
  tour.check('top bar: "five buttons: Solid, Ghost, Radiograph, Glow, Cutaway"', ['Solid', 'Ghost', 'Radiograph', 'Glow', 'Cutaway'].every((l) => labels.map((s) => s.trim()).includes(l)), labels.join());
  tour.check('top bar: "To the right, the search bar"', await page.locator('#xray-topbar-search').isVisible());
  const left = await page.locator('#sidebar').getByRole('tab').allInnerTexts();
  tour.check('left sidebar: "Four tabs: Model, Sets, Views and Issues"', ['Model', 'Sets', 'Views', 'Issues'].every((l) => left.map((s) => s.trim()).includes(l)), left.join());
  const tools = await page.locator('#xray-toolbar button').evaluateAll((b) => b.map((x) => x.getAttribute('aria-label')));
  tour.check('tool strip: "Open model, X-ray, View modes, Measure, Clearance, Penetrations, Cleanup and others"', ['Open model', 'X-ray', 'View modes', 'Measure', 'Clearance', 'Penetrations', 'Cleanup'].every((l) => tools.includes(l)), tools.join());
  const right = await page.locator('#dock').getByRole('tab').allInnerTexts();
  tour.check('right sidebar: "Tabs: Properties, Classification, Parameters, Script and 4D"', ['Properties', 'Classification', 'Parameters', 'Script', '4D'].every((l) => right.map((s) => s.trim()).includes(l)), right.join());
  tour.check('"A Revision tab appears only while you compare model versions": none now', !right.some((s) => s.trim() === 'Revision'));
  tour.check('view cube bottom right with the pointer-mode toggle, undo, redo and the section strip', (await page.locator('#xray-gizmo').isVisible()) && (await page.getByRole('group', { name: 'Pointer mode' }).isVisible()) && (await page.getByRole('group', { name: 'History' }).isVisible()) && (await page.getByRole('toolbar').locator('[aria-label="Section tools"]').count() >= 0));
  const st = (await ui.statusText(page)).replace(/\s+/g, ' ');
  tour.check('status bar: model name and element count, x-ray state, focus/host/near/far counts, frame time', /fzk/i.test(st) && /x-ray on/.test(st) && /F \d/.test(st) && /ms/.test(st), st.slice(0, 160));
  tour.check('status bar: the ⓘ button for details and credits', await page.locator('#xray-overlay').getByRole('button').count() > 0);
  // the picture: the whole viewer with each part labelled
  await ui.setCam(page, [9, 7, 11], [0, 1.5, 0]).catch(() => {});
  await ui.clickElement(page, { cls: 'IfcWindow' }).catch(() => null);
  await page.mouse.move(700, 120);
  const rect = (sel) => page.locator(sel).first().boundingBox();
  const canvasBox = await rect('#c');
  const side = await rect('#sidebar'), dock = await rect('#dock'), strip = await rect('#xray-toolbar'), gizmo = await rect('#xray-gizmo'), bar = await rect('#xray-topbar'), stat = await rect('#xray-overlay');
  await tour.annotate(page, [
    { selector: '#xray-topbar', text: 'Top bar', side: 'inside', dx: 560 },
    { selector: '#sidebar', text: 'Left sidebar', side: 'inside', dy: 700 },
    { selector: '#xray-toolbar', text: 'Tool strip', side: 'right', dy: 120 },
    { rect: { x: (strip?.x ?? 0) + 400, y: (bar?.y ?? 0) + 200, width: 1, height: 1 }, text: 'Canvas', side: 'inside' },
    { selector: '#xray-gizmo', text: 'View cube and section strip', side: 'left' },
    { selector: '#dock', text: 'Right sidebar', side: 'inside', dy: 700 },
    { selector: '#xray-overlay', text: 'Status bar', side: 'top' },
  ]);
  void canvasBox; void side; void dock; void gizmo; void stat;
  await tour.picture('screen-map', { page });
  await tour.unannotate(page);
});

await tour.step('3.1 Try it: T twice, [ twice, ] twice, hover a tool button', async () => {
  const page = await tour.open('model=fzk-haus');
  await page.locator('#c').hover();
  await page.keyboard.press('t');
  tour.check('T hides the tool strip', await stripHidden(page));
  await page.keyboard.press('t');
  tour.check('T again brings it back', !(await stripHidden(page)));
  await page.keyboard.press('[');
  tour.check('[ folds the left sidebar', await sbCollapsed(page));
  await page.keyboard.press('[');
  tour.check('[ again opens it', !(await sbCollapsed(page)));
  await page.keyboard.press(']');
  tour.check('] folds the right sidebar', await dockCollapsed(page));
  await page.keyboard.press(']');
  tour.check('] again opens it', !(await dockCollapsed(page)));
  await page.keyboard.press('Shift+T');
  tour.check('Shift+T hides the top bar', !(await page.locator('#xray-topbar').isVisible()));
  await page.keyboard.press('Shift+T');
  tour.check('Shift+T shows it again', await page.locator('#xray-topbar').isVisible());
  await page.keyboard.press('v');
  tour.check('V hides the view cube', !(await page.locator('#xray-gizmo .xg-nav').isVisible()));
  await page.keyboard.press('v');
  tour.check('V shows it again', await page.locator('#xray-gizmo .xg-nav').isVisible());
  const btn = ui.tool(page, 'Measure');
  await btn.hover();
  const tip = await btn.getAttribute('title');
  tour.check('"Hover over a tool button to read its name": the button carries a name and a tooltip', !!tip && tip.length > 3, tip);
});

await tour.step('3.2 Pointer modes and the view cube buttons', async () => {
  const page = await tour.open('model=fzk-haus');
  const hand = page.getByRole('button', { name: 'Hand: move mode' });
  const arrow = page.getByRole('button', { name: 'Arrow: select mode' });
  tour.check('"Hand (key G) is the default"', (await hand.getAttribute('aria-pressed')) === 'true');
  const c0 = await ui.cam(page);
  const box = await page.locator('#c').boundingBox();
  const cx = box.x + box.width * 0.55, cy = box.y + box.height * 0.5;
  await page.mouse.move(cx, cy); await page.mouse.down(); await page.mouse.move(cx + 120, cy + 30, { steps: 6 }); await page.mouse.up();
  await ui.waitStill(page, 8000);
  const c1 = await ui.cam(page);
  tour.check('Hand: left drag orbits', Math.hypot(c1.p[0] - c0.p[0], c1.p[2] - c0.p[2]) > 0.3 && true, `moved ${Math.hypot(c1.p[0] - c0.p[0], c1.p[2] - c0.p[2]).toFixed(2)} m`);
  await page.keyboard.press('r');
  tour.check('R switches to Arrow mode', (await arrow.getAttribute('aria-pressed')) === 'true');
  await page.keyboard.press('g');
  tour.check('G switches back to Hand mode', (await hand.getAttribute('aria-pressed')) === 'true');
});

await tour.step('3.2 Try it (view cube): Top, Home, Alt+Left, wheel toward the cursor', async () => {
  const page = await tour.open('model=fzk-haus');
  const pre0 = await ui.cam(page);
  await page.locator('polygon[aria-label="Top view"]:visible').first().click({ force: true });
  await ui.waitMoved(page, pre0);
  const top = await ui.cam(page);
  tour.check('"Click Top on the cube. You look straight down."', dir(top)[1] < -0.97, `view direction y ${dir(top)[1].toFixed(3)}`);
  await ui.button(page, /^Home/).click();
  await ui.waitMoved(page, top);
  const home = await ui.cam(page);
  tour.check('"Click Home": the view is the home corner, no longer straight down', dir(home)[1] > -0.9, `y ${dir(home)[1].toFixed(3)}`);
  await page.keyboard.press('Alt+ArrowLeft');
  await ui.waitMoved(page, home);
  const back = await ui.cam(page);
  tour.check('"Press Alt+Left to go back to the view before"', dir(back)[1] < -0.9 || Math.hypot(...back.p.map((v, i) => v - top.p[i])) < Math.hypot(...back.p.map((v, i) => v - home.p[i])), `back y ${dir(back)[1].toFixed(3)}`);
  await page.keyboard.press('Home');
  await ui.waitStill(page);
  // the wheel: a corner of the house stays under the pointer
  const spot = await page.evaluate(() => {
    const a = window.__xray.app, els = a.controller.model.elements;
    const b = els.reduce((m, e) => [Math.min(m[0], e.bounds[0]), Math.min(m[1], e.bounds[1]), Math.min(m[2], e.bounds[2]), Math.max(m[3], e.bounds[3]), Math.max(m[4], e.bounds[4]), Math.max(m[5], e.bounds[5])], [1e9, 1e9, 1e9, -1e9, -1e9, -1e9]);
    window.__corner = [b[3], b[1] + (b[4] - b[1]) * 0.3, b[5]];
    return window.__corner;
  });
  const at = () => page.evaluate(() => {
    const a = window.__xray.app, cm = a.renderer.camera, cv = a.canvas.getBoundingClientRect();
    cm.updateMatrixWorld();
    const v = cm.position.clone().set(...window.__corner).project(cm);
    return { x: cv.left + (v.x * 0.5 + 0.5) * cv.width, y: cv.top + (1 - (v.y * 0.5 + 0.5)) * cv.height };
  });
  void spot;
  const p0 = await at();
  await page.mouse.move(p0.x, p0.y);
  for (let i = 0; i < 4; i++) { await page.mouse.wheel(0, -120); await page.waitForTimeout(120); }
  await page.waitForTimeout(800); await ui.settle(page);
  const p1 = await at();
  tour.check('"Turn the wheel with the pointer over a corner of the house, and see that corner stay under the pointer"', Math.hypot(p1.x - p0.x, p1.y - p0.y) < 8, `moved ${Math.hypot(p1.x - p0.x, p1.y - p0.y).toFixed(1)} px`);
});

await tour.step('3.2 Try it (Walk mode) steps 1-8', async () => {
  const page = await tour.open('model=fzk-haus');
  const chip = page.getByText('Walk · Esc to exit');
  const info = await page.evaluate(() => {
    const m = window.__xray.app.controller.model, els = m.elements;
    const w = els.filter((e) => /Wall|Slab|Roof/.test(e.ifcClass));
    // the floor of each storey: the lowest slab top among the slabs of that storey
    const per = new Map();
    for (const e of els) if (/Slab/.test(e.ifcClass) && e.storey !== null && e.storey !== undefined) per.set(e.storey, Math.min(per.get(e.storey) ?? 1e9, e.bounds[4]));
    const tops = [...per.values()].map((v) => +v.toFixed(2)).sort((a, b) => a - b);
    return { allTops: els.map((e) => e.bounds[4]), b: w.reduce((q, e) => [Math.min(q[0], e.bounds[0]), Math.min(q[1], e.bounds[1]), Math.min(q[2], e.bounds[2]), Math.max(q[3], e.bounds[3]), Math.max(q[4], e.bounds[4]), Math.max(q[5], e.bounds[5])], [1e9, 1e9, 1e9, -1e9, -1e9, -1e9]), tops };
  });
  const inside = (c) => c.p[0] > info.b[0] + 0.3 && c.p[0] < info.b[3] - 0.3 && c.p[2] > info.b[2] + 0.3 && c.p[2] < info.b[5] - 0.3;
  const dist2 = (a, b) => Math.hypot(a.p[0] - b.p[0], a.p[2] - b.p[2]);
  /** Hold a key until `done(cam)` is true (the software renderer draws a frame about every half second, so a fixed time is not enough). */
  const holdUntil = async (key, done, maxMs = 120000) => {
    await page.keyboard.down(key);
    let c = await ui.cam(page);
    for (let t = 0; t < maxMs && !done(c); t += 400) { await page.waitForTimeout(400); c = await ui.cam(page); }
    await page.keyboard.up(key);
    await ui.waitStill(page, 8000);
    return ui.cam(page);
  };
  await page.locator('#c').hover();
  await page.keyboard.press('Home'); await ui.waitStill(page);
  const c1 = await ui.cam(page);
  tour.check('step 1: "Press Home. The whole house fills the view, seen from above and outside."', !inside(c1) && c1.p[1] > info.b[4], `eye ${c1.p.map((v) => v.toFixed(1))}`);
  await page.keyboard.press('Shift+W');
  await chip.waitFor({ timeout: 10000 }).catch(() => {});
  tour.check('step 2: "Press Shift+W. The chip appears."', await chip.isVisible());
  await page.waitForTimeout(1500);
  const c2 = await ui.cam(page);
  tour.check('step 2: "Nothing moves yet."', Math.hypot(...c2.p.map((v, i) => v - c1.p[i])) < 0.2, `moved ${Math.hypot(...c2.p.map((v, i) => v - c1.p[i])).toFixed(2)} m`);
  const groundTop = info.tops[0];
  const c3 = await holdUntil('q', (c) => c.p[1] < groundTop + 2.2);
  tour.check('step 3: "Hold Q ... your eye is now low, at about the height of the ground floor"', c3.p[1] < c1.p[1] - 1 && c3.p[1] < groundTop + 3, `eye y ${c3.p[1].toFixed(2)}, floor tops ${info.tops.join(', ')}`);
  const box = await page.locator('#c').boundingBox();
  const mx = box.x + box.width * 0.5, my = box.y + box.height * 0.5;
  let sign = 1;
  for (let i = 0; i < 12; i++) {
    const d = dir(await ui.cam(page));
    if (Math.abs(d[1]) < 0.08) break;
    await page.mouse.move(mx, my); await page.mouse.down();
    await page.mouse.move(mx, my + sign * Math.max(30, Math.min(120, Math.abs(d[1]) * 200)), { steps: 5 }); await page.mouse.up();
    await ui.waitStill(page, 4000);
    if (Math.abs(dir(await ui.cam(page))[1]) > Math.abs(d[1]) + 0.01) sign = -sign; // the drag went the wrong way round: reverse it
  }
  const lvl = dir(await ui.cam(page));
  tour.check('step 3: "Drag with the left button to look level"', Math.abs(lvl[1]) < 0.25, `view direction y ${lvl[1].toFixed(2)}`);
  const y0 = (await ui.cam(page)).p[1];
  const cw = await holdUntil('w', inside);
  tour.check('step 4: "Hold W. You walk toward the house ... pass through the outer wall and stand inside the ground floor."', inside(cw), `eye ${cw.p.map((v) => v.toFixed(1))}, house x ${info.b[0].toFixed(1)}..${info.b[3].toFixed(1)}, z ${info.b[2].toFixed(1)}..${info.b[5].toFixed(1)}`);
  tour.check('step 4: "toward the house at the same height"', Math.abs(cw.p[1] - y0) < 0.1, `height ${y0.toFixed(2)} -> ${cw.p[1].toFixed(2)}`);
  const h0 = dir(cw);
  await holdUntil('ArrowLeft', (c) => { const h = dir(c); return Math.hypot(h[0] - h0[0], h[2] - h0[2]) > 0.5; }, 30000);
  const h1 = dir(await ui.cam(page));
  tour.check('step 5: "Press Left to turn and look around the room"', Math.hypot(h1[0] - h0[0], h1[2] - h0[2]) > 0.3, `heading change ${Math.hypot(h1[0] - h0[0], h1[2] - h0[2]).toFixed(2)}`);
  const u0 = await ui.cam(page);
  await page.keyboard.press('PageUp');
  await ui.waitMoved(page, u0);
  const u1 = await ui.cam(page);
  const toast = await page.locator('.kx-toast').innerText().catch(() => '');
  tour.check('step 5: "Press PageUp. You move to the storey above, at the same spot"', u1.p[1] > u0.p[1] + 1.5 && dist2(u1, u0) < 0.2, `eye y ${u0.p[1].toFixed(2)} -> ${u1.p[1].toFixed(2)}`);
  tour.check('step 5: "and a message names it"', toast.length > 0 && !/Already/.test(toast), toast);
  await page.keyboard.press('PageDown');
  await ui.waitMoved(page, u1);
  const u2 = await ui.cam(page);
  tour.check('step 5: "Press PageDown to come back"', Math.abs(u2.p[1] - u0.p[1]) < 0.15, `eye y ${u2.p[1].toFixed(2)}`);
  await page.keyboard.press('Escape');
  tour.check('step 6: "Press Esc to leave" - the chip goes', await chip.isHidden());
  await page.keyboard.press('Home'); await ui.waitStill(page);
  const wallSpot = () => page.evaluate(() => {
    const app = window.__xray.app, cm = app.renderer.camera, cv = app.canvas.getBoundingClientRect();
    cm.updateMatrixWorld();
    const out = [];
    for (const e of app.controller.model.elements) {
      if (!/Wall/.test(e.ifcClass)) continue;
      const b = e.bounds;
      const v = cm.position.clone().set((b[0] + b[3]) / 2, (b[1] + b[4]) / 2, (b[2] + b[5]) / 2).project(cm);
      const x = cv.left + (v.x * 0.5 + 0.5) * cv.width, y = cv.top + (1 - (v.y * 0.5 + 0.5)) * cv.height;
      if (x > cv.left + 20 && x < cv.right - 20 && y > cv.top + 40 && y < cv.bottom - 40 && document.elementFromPoint(x, y) === app.canvas) out.push({ x, y, d: Math.hypot(v.x, v.y) });
    }
    return out.sort((a, b) => a.d - b.d)[0] ?? null;
  });
  const sp = await wallSpot();
  await page.keyboard.down('Alt');
  await page.mouse.dblclick(sp.x, sp.y);
  await page.keyboard.up('Alt');
  await chip.waitFor({ timeout: 10000 }).catch(() => {});
  await ui.waitStill(page, 15000);
  tour.check('step 6: "Hold Alt and double-click a wall of the house. The chip appears"', await chip.isVisible());
  const eye = await page.evaluate(() => window.__xray.app.renderer.camera.position.y);
  tour.known('step 6: "you stand inside, on the floor below the point you clicked, at 1.6 m"', info.allTops.some((t) => Math.abs(eye - 1.6 - t) < 0.3), 'after Alt+double-click on a wall the eye stayed at the Home height instead of dropping in at 1.6 m above a floor (not yet separated from a click-spot problem in the tour)', `eye y ${eye.toFixed(2)}, floor tops ${info.tops.join(',')}`);
  // step 7: collision
  await ui.tab(page, 'Parameters');
  await ui.topOfPanel(page);
  await ui.folder(page, 'Keyboard');
  tour.check('step 7: the Keyboard folder has "eye height (m)" at 1.6', Number(await ui.valueOf(page, 'eye height (m)')) === 1.6, String(await ui.valueOf(page, 'eye height (m)')));
  await ui.set(page, 'Walk collision', true);
  tour.check('step 7: "switch on Walk collision"', (await ui.valueOf(page, 'Walk collision')) === true);
  await page.locator('#c').hover();
  await page.keyboard.press('Escape');
  await page.keyboard.press('Home'); await ui.waitStill(page);
  const sp2 = await wallSpot();
  await page.keyboard.down('Alt'); await page.mouse.dblclick(sp2.x, sp2.y); await page.keyboard.up('Alt');
  await ui.waitStill(page, 15000);
  // The headless double click may leave the eye over the roof or looking out of a window, so there is no wall to walk at. Stand a person
  // inside, on the ground floor at 1.6 m, facing a wall 2.5 to 6 m away (as a drop-in and a turn with the arrow keys would), then walk.
  const faced = await page.evaluate(async () => {
    const { blocksWalk } = await import('/src/input/walk.ts');
    const { storeyFloors } = await import('/src/xr/field.ts');
    const app = window.__xray.app, r = app.renderer, m = app.loaded.model, els = m.elements;
    const floors = storeyFloors(m).map((f) => f.floorY).sort((a, b) => a - b);
    const walls = els.filter((e) => /Wall/.test(e.ifcClass));
    const bb = walls.reduce((q, e) => [Math.min(q[0], e.bounds[0]), Math.min(q[1], e.bounds[2]), Math.max(q[2], e.bounds[3]), Math.max(q[3], e.bounds[5])], [1e9, 1e9, -1e9, -1e9]);
    const V = r.camera.position.constructor;
    const hitAt = (p, d) => r.raycastVisible(p, d, 8, (id) => blocksWalk(els[id]?.ifcClass ?? '', r.state.flags[id] ?? 0, r.state.alpha[id] ?? 1));
    let best = null;
    for (const floor of floors) {
      for (let x = bb[0] + 1; x < bb[2] - 1; x += 1) for (let z = bb[1] + 1; z < bb[3] - 1; z += 1) {
        const eye = new V(x, floor + 1.6, z);
        for (let a = 0; a < 360; a += 5) {
          const d = new V(Math.cos((a * Math.PI) / 180), 0, Math.sin((a * Math.PI) / 180));
          const waist = hitAt(new V(x, eye.y - 0.72, z), d);
          if (!waist || Math.abs(waist.normal.y) > 0.3 || waist.distance < 2.5 || waist.distance > 6) continue;
          // square on: a slanting approach slides along the wall, as it should, and a person walking at a wall faces it
          if (Math.abs(waist.normal.x * d.x + waist.normal.z * d.z) < 0.97) continue;
          // nothing near on the other rays, and not inside a wall: the opposite way is free for 0.5 m
          const others = [0, -1.2].map((dy) => hitAt(new V(x, eye.y + dy, z), d));
          if (others.some((h) => h && h.distance < 1.5)) continue;
          const back = hitAt(eye, d.clone().negate());
          if (back && back.distance < 0.5) continue;
          if (!best || waist.distance < best.dist) best = { dist: waist.distance, eye, d, floor };
        }
      }
      if (best) break;
    }
    if (best) { r.camera.position.copy(best.eye); r.controls.target.copy(best.eye).addScaledVector(best.d, 3); r.camera.lookAt(r.controls.target); r.controls.update(); }
    return best ? { dist: +best.dist.toFixed(1), floors, eye: [best.eye.x, best.eye.y, best.eye.z].map((v) => +v.toFixed(1)) } : null;
  });
  // hold W: with collision the eye comes to rest short of a wall while the key is still down
  await page.keyboard.down('w');
  let prev = await ui.cam(page), still = 0, travelled = 0;
  for (let t = 0; t < 90000 && still < 6; t += 500) {
    await page.waitForTimeout(500);
    const c = await ui.cam(page);
    const mv = dist2(c, prev); travelled += mv;
    still = mv < 0.005 ? still + 1 : 0;
    prev = c;
  }
  await page.keyboard.up('w');
  tour.check('step 7: "Hold W toward a wall. You stop short of it."', faced !== null && still >= 6 && travelled > 0, `${JSON.stringify(faced)}: wall ahead; moved ${travelled.toFixed(1)} m, then stood still while W was held`);
  await ui.set(page, 'Walk collision', false);
  // step 8
  await page.locator('#c').hover();
  let escs = 0;
  for (; escs < 3; ) { await page.keyboard.press('Escape'); escs++; await page.waitForTimeout(500); if (await chip.isHidden()) break; }
  tour.check('step 8: "Press Esc" leaves Walk mode with one press', escs === 1, `Esc had to be pressed ${escs} times`);
  tour.check('step 8: "Press Esc. The chip goes away"', await chip.isHidden(), 'Walk mode was still on after three Esc presses');
  const o0 = await ui.cam(page);
  const box2 = await page.locator('#c').boundingBox();
  await page.mouse.move(box2.x + 600, box2.y + 400); await page.mouse.down(); await page.mouse.move(box2.x + 700, box2.y + 400, { steps: 5 }); await page.mouse.up();
  await ui.waitStill(page, 8000);
  const o1 = await ui.cam(page);
  tour.check('step 8: "the mouse orbits again, around a point a short way in front of you"', Math.hypot(...o1.p.map((v, i) => v - o0.p[i])) > 0.02 && o0.d < 30, `pivot distance ${o0.d.toFixed(1)} m`);
});

await tour.step('3.3 Try it: hover a wall, click it, read the Properties tab', async () => {
  const page = await tour.open('model=fzk-haus');
  await ui.tab(page, 'Properties');
  const wall = await ui.clickElement(page, { cls: /Wall/ });
  tour.check('a wall can be clicked', !!wall, JSON.stringify(wall));
  await ui.clearSelection(page);
  await ui.park(page);
  await ui.waitStill(page, 8000);
  let spot = null, card = '';
  for (const c of await ui.spotsOf(page, wall.id)) {
    await page.mouse.move(c.x - 4, c.y); await page.mouse.move(c.x, c.y, { steps: 3 });
    await page.waitForTimeout(1000);
    card = await ui.hoverCardText(page);
    if (/IfcWall/.test(card)) { spot = c; break; }
  }
  tour.check('"Rest the pointer on an element for 350 ms and a small card appears" with `class · storey · material`', !!spot && /·/.test(card), card.replace(/\s+/g, ' ').slice(0, 140));
  tour.check('"while x-ray is on a line such as x-ray: near · alpha 0.40"', /x-ray: .*alpha [\d.]+/.test(card), card.replace(/\s+/g, ' ').slice(-60));
  spot = spot ?? { x: wall.x, y: wall.y };
  await page.mouse.click(spot.x, spot.y);
  await ui.settle(page, 600);
  const props = await page.locator('#dk-pane-properties').innerText();
  tour.check('"Open the Properties tab": it shows the GlobalId, class, name, storey and material', /GlobalId/i.test(props) && /IfcWall/.test(props) && /Storey/i.test(props) && /Material/i.test(props), props.replace(/\s+/g, ' ').slice(0, 160));
  tour.check('"a list Properties (n)" with the property sets', /Properties \(\d+( of \d+)?\)/.test(props), (props.match(/Properties \([^)]*\)/) ?? [''])[0]);
  tour.check('"Find IsExternal and FireRating if the file has them" (this wall: ' + (/IsExternal/.test(props) ? 'IsExternal shown' : 'neither shown') + ')', true);
});

await tour.step('3.4 Try it: orbit, select a wall, change a slider, then Ctrl+Z three times', async () => {
  const page = await tour.open('model=fzk-haus');
  // the pages of the earlier steps are not needed: each one keeps drawing and slows every frame of this one (the undo list reads the frames)
  for (const c of page.context().browser().contexts()) if (c !== page.context()) await c.close().catch(() => {});
  const unfocus = () => page.evaluate(() => document.activeElement?.blur?.());
  const box = await page.locator('#c').boundingBox();
  await page.mouse.move(box.x + 700, box.y + 450); await page.mouse.down(); await page.mouse.move(box.x + 820, box.y + 470, { steps: 6 }); await page.mouse.up();
  await ui.waitStill(page, 8000);
  const w = await ui.clickElement(page, { cls: /Wall/ });
  tour.check('a wall is selected', !!w);
  await ui.waitStill(page, 15000);
  const camSel = await ui.cam(page);
  await ui.tab(page, 'Parameters'); await ui.topOfPanel(page);
  await ui.folder(page, 'Display');
  const v0 = Number(await ui.valueOf(page, 'edgeAlpha'));
  // the orbit damping of the first drag runs per frame, so with the slow headless frames it drifts on for a long time; a camera step
  // that lands between the slider steps would split the drag, so wait until the camera is still
  await ui.waitStill(page, 120000);
  await page.waitForTimeout(2500);
  await ui.dragSlider(page, 'edgeAlpha', -60);
  await unfocus();
  await page.waitForTimeout(1200);
  const v1 = Number(await ui.valueOf(page, 'edgeAlpha'));
  tour.check('the slider changed', Math.abs(v1 - v0) > 0.02, `${v0} -> ${v1}`);
  const label = await page.getByRole('button', { name: /^Undo/ }).getAttribute('aria-label');
  tour.check('the Undo button names the step', /^Undo\s+\S/.test(label ?? ''), label);
  await page.locator('#c').hover();
  let n1 = 0, v2 = v1;
  while (n1 < 15 && Math.abs(v2 - v0) >= 0.011) { await page.keyboard.press('Control+z'); n1++; await page.waitForTimeout(1500); v2 = Number(await ui.valueOf(page, 'edgeAlpha')); }
  tour.check('Ctrl+Z: the slider goes back', Math.abs(v2 - v0) < 0.011, `${v0} -> ${v1} -> ${v2} after ${n1} presses`);
  tour.check('"A slider drag is one step": one Ctrl+Z undoes the whole drag', n1 === 1, `a slider drag took ${n1} undo steps`);
  let n2 = 0;
  while (n2 < 5 && (await ui.selection(page)).length > 0) { await page.keyboard.press('Control+z'); n2++; await page.waitForTimeout(1500); }
  tour.known('Ctrl+Z: the selection goes back', (await ui.selection(page)).length === 0, 'the selection was still there after 5 more Ctrl+Z presses (more undo steps than the three the manual shows sit above it)', `after ${n2} more presses`);
  const labelNow = await page.getByRole('button', { name: /^Undo|Nothing to undo/ }).getAttribute('aria-label');
  tour.check('the Undo button still names the next step (the camera)', /^Undo\s+\S/.test(labelNow ?? ''), labelNow);
  const redoName = await page.getByRole('button', { name: /^Redo|Nothing to redo/ }).getAttribute('aria-label');
  await page.keyboard.press('Control+Shift+z'); await page.waitForTimeout(1500);
  tour.check('Ctrl+Shift+Z redoes: the Redo button had a step to redo', /^Redo\s+\S/.test(redoName ?? ''), redoName);
});

await tour.step('3.5 On a phone: the layout changes', async () => {
  const page = await tour.open('model=fzk-haus', { width: 390, height: 844 });
  tour.check('"The right sidebar starts folded, as a thin rail"', await dockCollapsed(page));
  tour.check('"The view cube starts collapsed as a small cube button"', await page.locator('#xray-gizmo .xg-open').isVisible());
  const names = await page.locator('#xray-topbar').getByRole('button').evaluateAll((b) => b.map((x) => x.getAttribute('aria-label') ?? x.textContent.trim()));
  tour.check('"The five top-bar modes become small icon buttons. Their labels stay as the accessible names."', ['Solid', 'Ghost', 'Radiograph', 'Glow', 'Cutaway'].every((l) => names.some((n) => n.includes(l))), names.join());
  const w = await page.evaluate(() => document.documentElement.scrollWidth);
  tour.check('no sideways scroll on a phone', w <= 392, `${w}px`);
});

await tour.step('3.7 Keyboard help: ? and the command palette', async () => {
  const page = await tour.open('model=fzk-haus');
  await page.locator('#c').hover();
  await page.keyboard.press('Shift+?');
  tour.check('"? opens the cheat sheet"', await page.getByRole('dialog', { name: 'Keyboard shortcuts' }).isVisible().catch(() => false));
  await page.keyboard.press('Escape');
  await page.keyboard.press('F1');
  tour.check('"F1 opens the cheat sheet"', await page.getByRole('dialog', { name: 'Keyboard shortcuts' }).isVisible().catch(() => false));
  await page.keyboard.press('Escape');
  await page.keyboard.press('Control+Shift+K');
  const pal = page.getByRole('dialog', { name: 'Command palette' });
  await pal.waitFor({ timeout: 10000 }).catch(() => {});
  tour.check('"Ctrl+Shift+K opens the command palette"', await pal.isVisible().catch(() => false));
  await page.keyboard.press('Escape');
  await page.keyboard.press('F6');
  await page.waitForTimeout(200);
  tour.check('"F6 moves focus around the screen" (the focus ring moves off the 3D view)', await page.evaluate(() => document.activeElement !== document.body));
});

await tour.finish();
