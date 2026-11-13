// Browser checks of the wave 7 fixes (bench/RESULTS-fixes-w7.md):
//   1  Reset to defaults shows a gizmo that was hidden before the page loaded (desktop expanded, phone collapsed)
//   2  a measure label under the gizmo moves out with a leader line
//   3  a BCF viewpoint applied after an import does not select annotated elements; they get the selection tint
//   4  a callout follows its element's displacement (renderer.setElementOffset, as the exploded view does)
//   5  rectangle (dragged with the mouse) and freehand shapes, stored in the side file, burned into the snapshot
//   6  stable pin numbers across export, import and new topics
//   7  linked measurement in millimetres when the measure tool is set to mm
//   9  a damaged IFC gives the friendly one-line message
//  10  section-focus frames the selection
// Usage: SMOKE_PORT=5714 node bench/smoke-fixes-w7.mjs   (writes bench/fixes-w7-bcf.png, bench/fixes-w7-snapshot.png)
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const port = Number(process.env.SMOKE_PORT ?? 5714);
const tmp = mkdtempSync(join(tmpdir(), 'smoke-fixes-w7-'));
const { chromium } = createRequire(import.meta.url)('playwright');

const vite = spawn(resolve(root, 'node_modules/.bin/vite'), ['--config', 'bench/vite.smoke.config.mjs', '--host', '127.0.0.1', '--port', String(port), '--strictPort'], { cwd: root, stdio: ['ignore', 'pipe', 'pipe'] });
let viteLog = '';
vite.stdout.on('data', (d) => (viteLog += d));
vite.stderr.on('data', (d) => (viteLog += d));
async function waitForServer() {
  for (let i = 0; i < 300; i++) {
    try { const r = await fetch(`http://127.0.0.1:${port}/`); if (r.ok) return; } catch { /* retry */ }
    await new Promise((r) => setTimeout(r, 200));
  }
  throw new Error('vite did not start:\n' + viteLog);
}

let failed = false;
function check(name, ok, detail = '') {
  if (!ok) failed = true;
  console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${detail ? ` (${detail})` : ''}`);
}
const overlaps = (a, b) => a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;

const errors = [];
let browser;
try {
  await waitForServer();
  browser = await chromium.launch();
  const watch = (page) => {
    page.setDefaultTimeout(240000);
    page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
    page.on('pageerror', (e) => errors.push(`[pageerror] ${e.message}`));
  };
  const boot = async (page, model) => {
    await page.goto(`http://127.0.0.1:${port}/?model=${model}`);
    await page.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: 300000 });
    const err = await page.evaluate('window.__xrayError');
    if (err) throw new Error(`startup failed: ${err}`);
  };
  const frames = (page, n = 3) => page.evaluate(async (n) => { for (let i = 0; i < n; i++) await new Promise((r) => requestAnimationFrame(r)); }, n);

  // ------------------------------------------------------------------ 1: gizmo reset
  for (const [label, viewport, collapsed] of [['desktop', { width: 1400, height: 860 }, false], ['phone', { width: 390, height: 844 }, true]]) {
    const ctx = await browser.newContext({ viewport });
    await ctx.addInitScript(() => { if (!sessionStorage.getItem('w7')) { localStorage.setItem('xray.gizmo', JSON.stringify({ visible: false, collapsed: false })); sessionStorage.setItem('w7', '1'); } });
    const page = await ctx.newPage();
    watch(page);
    await boot(page, 'building');
    const before = await page.evaluate(() => document.getElementById('xray-gizmo')?.hidden);
    await page.evaluate(() => window.__xrayParams.reset());
    await frames(page);
    const after = await page.evaluate(() => { const g = document.getElementById('xray-gizmo'); return { hidden: g.hidden, collapsed: g.classList.contains('collapsed') }; });
    check(`1 ${label}: a gizmo hidden before load comes back on Reset to defaults`, before === true && after.hidden === false && after.collapsed === collapsed, JSON.stringify({ before, after }));
    await ctx.close();
  }

  // ------------------------------------------------------------------ 9: damaged IFC
  {
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 } });
    const page = await ctx.newPage();
    watch(page);
    await boot(page, 'building');
    const bad = join(tmp, 'damaged.ifc');
    // A valid header, then entities whose references point nowhere and whose attributes are cut short.
    writeFileSync(bad, [
      'ISO-10303-21;', 'HEADER;', "FILE_DESCRIPTION(('ViewDefinition [CoordinationView]'),'2;1');", "FILE_NAME('d.ifc','2026-11-05T00:00:00',(''),(''),'','','');", "FILE_SCHEMA(('IFC4'));", 'ENDSEC;', 'DATA;',
      "#1=IFCPROJECT('0YvctVUKr0kugbFTf53O9L',#99,'P',$,$,$,$,(#77),#88);",
      "#2=IFCWALL('1YvctVUKr0kugbFTf53O9L',#99,'W',$,$,#55,#66,$,$);",
      "#3=IFCRELAGGREGATES('2YvctVUKr0kugbFTf53O9L',#99,$,$,#1,(#2,#123456));",
      '#4=IFCSHAPEREPRESENTATION(#5,\'Body\',\'SweptSolid\',(#6));', '#6=IFCEXTRUDEDAREASOLID(#7,$,#8,);', 'ENDSEC;', 'END-ISO-10303-21;',
    ].join('\n'));
    const model0 = await page.evaluate(() => window.__xray.app.modelName);
    await page.setInputFiles('#xray-open-file-input', [bad]);
    await page.waitForFunction(() => {
      const c = window.__xray.app.panel.controllersRecursive().find((x) => x.property === 'status');
      const v = String(c?.getValue() ?? '');
      return v && !/^(Reading|Opening|Meshing|Reading relations|Merging|Edges|BVH|Transferring|Uploading)/.test(v);
    }, null, { timeout: 180000 });
    const st = await page.evaluate(() => ({ status: String(window.__xray.app.panel.controllersRecursive().find((x) => x.property === 'status').getValue()), model: window.__xray.app.modelName }));
    console.log(`    damaged IFC status: ${st.status}`);
    check('9 damaged IFC: one friendly line, no web-ifc internals, the model stays',
      (/could not be read: it may be damaged or not an IFC file/.test(st.status) || /has no geometry|could not be parsed|not a valid IFC/.test(st.status)) && !/arguments|undefined|TypeError/.test(st.status) && st.model === model0, st.status);
    await ctx.close();
  }

  // ------------------------------------------------------------------ BCF on fzk-haus (2-7, 10)
  const ctx = await browser.newContext({ viewport: { width: 1400, height: 860 }, acceptDownloads: true });
  const page = await ctx.newPage();
  watch(page);
  await boot(page, 'fzk-haus');
  const setup = await page.evaluate(() => {
    const app = window.__xray.app;
    const els = app.controller.model.elements;
    const win = els.find((e) => e.ifcClass === 'IfcWindow');
    const wall = els.find((e) => /IfcWall/.test(e.ifcClass));
    const c = (e) => [(e.bounds[0] + e.bounds[3]) / 2, (e.bounds[1] + e.bounds[4]) / 2, (e.bounds[2] + e.bounds[5]) / 2];
    app.selectIds([win.id]);
    return { win: { id: win.id, gid: win.globalId, c: c(win) }, wall: { id: wall.id, gid: wall.globalId, c: c(wall) } };
  });
  await page.waitForTimeout(2500);
  // 10: section-focus frames the selection from the whole-model view
  const framing = await page.evaluate(async (winC) => {
    const app = window.__xray.app;
    window.__cinematic?.cancelFlight?.();
    if (window.__cinematic?.cfg) window.__cinematic.cfg.flyTo = false; // immediate fit, no animation to wait for
    app.frameAll();
    const d0 = app.renderer.camera.position.distanceTo(app.renderer.controls.target);
    const r = window.__xrayPresets.apply('section-focus');
    await new Promise((res) => setTimeout(res, 300));
    const t = app.renderer.controls.target;
    const d1 = app.renderer.camera.position.distanceTo(t);
    const r2 = window.__xrayPresets.apply('coordination');
    return { d0, d1, framed: r.framed, toWin: Math.hypot(t.x - winC[0], t.y - winC[1], t.z - winC[2]), coordFramed: r2.framed };
  }, setup.win.c);
  check('10 section-focus frames the selection (camera much closer, target on it); coordination does not move it',
    framing.framed === true && framing.d1 < framing.d0 * 0.6 && framing.toWin < 0.5 && framing.coordFramed === undefined, JSON.stringify(framing));

  await page.evaluate(() => {
    const app = window.__xray.app;
    const cam = app.renderer.camera;
    cam.position.set(9.5, 5.5, 11.5);
    app.renderer.controls.target.set(0.5, 1.2, -0.5);
    app.renderer.controls.update();
    app.controller.settle();
    window.__xrayIssues?.open('issues'); // the BCF drawer moved into the Issues tab
  });
  await page.waitForTimeout(800);

  // 2: a measure label whose dimension midpoint projects under the gizmo
  const label = await page.evaluate(async () => {
    const app = window.__xray.app;
    const g = document.getElementById('xray-gizmo').getBoundingClientRect();
    const cr = app.canvas.getBoundingClientRect();
    const cam = app.renderer.camera;
    cam.updateMatrixWorld();
    const ndc = (x, y) => [((x - cr.left) / cr.width) * 2 - 1, -(((y - cr.top) / cr.height) * 2 - 1)];
    const [nx, ny] = ndc(g.left + g.width / 2, g.top + g.height / 2);
    const P = cam.position.clone().set(nx, ny, 0.6).unproject(cam);
    const right = cam.position.clone().set(1, 0, 0).applyQuaternion(cam.quaternion).multiplyScalar(0.05);
    const m = window.__xrayMeasure;
    m.click([P.x - right.x, P.y - right.y, P.z - right.z], -1);
    m.click([P.x + right.x, P.y + right.y, P.z + right.z], -1);
    for (let i = 0; i < 4; i++) await new Promise((r) => requestAnimationFrame(r));
    const labels = [...document.querySelectorAll('[data-measure-label]')];
    const t = labels[labels.length - 1]?.parentElement?.querySelector('rect')?.getBoundingClientRect();
    const leader = labels[labels.length - 1]?.parentElement?.querySelector('[data-leader]');
    return { gizmo: { x: g.left, y: g.top, w: g.width, h: g.height }, label: t ? { x: t.left, y: t.top, w: t.width, h: t.height } : null, leader: !!leader, n: m.list.length };
  });
  check('2 a measure label under the gizmo moves out of it with a leader line', !!label.label && !overlaps(label.label, label.gizmo) && label.leader, JSON.stringify(label));

  // 6 + 7: two topics, linked measurement in mm, callout on a wall, shapes
  const made = await page.evaluate((s) => {
    const b = window.__xrayBcf;
    const app = window.__xray.app;
    app.selectIds([s.win.id]);
    window.__cinematic?.cancelFlight?.();
    const A = b.createTopic({ title: 'Window reveal', author: 'smoke' });
    const B = b.createTopic({ title: 'Second', author: 'smoke' });
    b.applyViewpoint(A.guid);
    window.__xrayParams.apply({ schema: 'xray-params/1', measure: { units: 'mm' } });
    const m = window.__xrayMeasure.list[window.__xrayMeasure.list.length - 1];
    const link = b.linkMeasurement(A.guid, m.id);
    const call = b.addAnnotation(A.guid, { type: 'callout', text: 'Wall note', anchor: { kind: 'element', point: s.wall.c, elementGuid: s.wall.gid } });
    const fh = b.addShape(A.guid, 'freehand', [[300, 300], [340, 320], [380, 300], [420, 330]], 'by hand');
    return { A: A.guid, B: B.guid, nA: b.pinNumber(A.guid), nB: b.pinNumber(B.guid), unit: window.__xrayMeasure.units, link: link?.guid, call: call.guid, fh: fh.guid, sel: A.viewpoints[0].data.selection.map((c) => c.ifcGuid) };
  }, setup);
  check('6 new topics get pin numbers 1 and 2', made.nA === 1 && made.nB === 2, `${made.nA}, ${made.nB}`);
  check('3 the annotated wall joins the viewpoint selection for other tools', made.sel.includes(setup.wall.gid) && made.sel.includes(setup.win.gid), made.sel.join(','));
  await frames(page, 4);
  // Assertions changed in 7, 5 and 4: the drawing of a viewpoint is its sketch, so the markup view draws it (data-mk, same guid) and
  // the BCF overlay draws none; the annotation text carries the markup number ("N. text").
  const mmText = await page.evaluate((g) => [...document.querySelectorAll(`svg.xray-svg-overlay [data-mk="${g}"] text`)].map((t) => t.textContent), made.link);
  check('7 the linked measurement shows in mm (the measure tool unit)', mmText.some((t) => /^\d+ mm$/.test(t)), JSON.stringify(mmText));

  // 5: a rectangle dragged with the mouse
  const cr = await page.evaluate(() => { const r = window.__xray.app.canvas.getBoundingClientRect(); return { x: r.left, y: r.top, w: r.width, h: r.height }; });
  await page.evaluate((t) => window.__xrayBcf.startPlacement('rect', t, 'Sill area'), made.A);
  const cam0 = await page.evaluate(() => window.__xray.app.renderer.camera.position.toArray());
  // A start where the canvas itself is under the pointer (not a pin, a text box or a drawer).
  const u0 = await page.evaluate(() => {
    const cv = window.__xray.app.canvas;
    const r = cv.getBoundingClientRect();
    for (const u of [0.42, 0.5, 0.58, 0.34, 0.62]) for (const v of [0.4, 0.3, 0.5, 0.25]) {
      const ok = [[u, v], [u + 0.07, v + 0.075], [u + 0.14, v + 0.15]].every(([a, b]) => document.elementFromPoint(r.left + a * r.width, r.top + b * r.height) === cv);
      if (ok) return [u, v];
    }
    return [0.42, 0.4];
  });
  await page.mouse.move(cr.x + cr.w * u0[0], cr.y + cr.h * u0[1]);
  await page.mouse.down();
  await page.mouse.move(cr.x + cr.w * (u0[0] + 0.07), cr.y + cr.h * (u0[1] + 0.075), { steps: 5 });
  await page.mouse.move(cr.x + cr.w * (u0[0] + 0.14), cr.y + cr.h * (u0[1] + 0.15), { steps: 5 });
  await page.mouse.up();
  await frames(page, 4);
  const rect = await page.evaluate(() => {
    const t = window.__xrayBcf.topics[0];
    const a = Object.values(window.__xrayBcf.annotations(t.guid)).flat().find((x) => x.type === 'rect');
    const el = a && document.querySelector(`svg.xray-svg-overlay [data-mk="${a.guid}"] polygon, svg.xray-svg-overlay [data-mk="${a.guid}"] [data-role=shape]`);
    return { a, drawn: !!el, cam: window.__xray.app.renderer.camera.position.toArray(), sel: window.__xray.app.selection, status: window.__xrayBcf.status };
  });
  const camMoved = Math.hypot(rect.cam[0] - cam0[0], rect.cam[1] - cam0[1], rect.cam[2] - cam0[2]);
  check('5 a mouse drag draws a rectangle in view fractions (the camera does not orbit)', !!rect.a && rect.drawn && rect.a.shape.points.length === 2 && Math.abs(rect.a.shape.points[0][0] - u0[0]) < 0.03 && Math.abs(rect.a.shape.points[1][1] - (u0[1] + 0.15)) < 0.03 && camMoved < 1e-6 && /Sill area$/.test(rect.a.text),
    JSON.stringify({ pts: rect.a?.shape?.points, u0, camMoved, status: rect.status }));

  // 4: the wall callout follows the wall's displacement (what the exploded view sets per element)
  const follow = await page.evaluate(async (s) => {
    const app = window.__xray.app;
    const pos = () => { const e = document.querySelector(`svg.xray-svg-overlay [data-mk="${s.call}"] circle[data-role=anchor]`); return e ? [Number(e.getAttribute('cx')), Number(e.getAttribute('cy'))] : null; };
    const f = () => new Promise((r) => requestAnimationFrame(r));
    for (let i = 0; i < 3; i++) await f();
    const p0 = pos();
    app.renderer.setElementOffset(s.wall.id, 0, 1.5, 0);
    app.renderer.markDirty();
    for (let i = 0; i < 4; i++) await f();
    const p1 = pos();
    const cam = app.renderer.camera;
    const a = cam.position.clone().set(...s.wall.c).project(cam);
    const b = cam.position.clone().set(s.wall.c[0], s.wall.c[1] + 1.5, s.wall.c[2]).project(cam);
    const r = app.canvas.getBoundingClientRect();
    const want = (b.y - a.y) * -0.5 * r.height;
    app.renderer.setElementOffset(s.wall.id, 0, 0, 0);
    app.renderer.markDirty();
    return { p0, p1, dy: p1 && p0 ? p1[1] - p0[1] : null, want };
  }, { ...setup, call: made.call });
  check('4 a callout on an element follows the element offset', follow.dy !== null && Math.abs(follow.dy - follow.want) < 2 && Math.abs(follow.want) > 10, JSON.stringify(follow));

  await page.waitForTimeout(300);
  await page.screenshot({ path: resolve(here, 'fixes-w7-bcf.png') });

  // export, check the side file, reload, import
  const exported = await page.evaluate(async (A) => {
    const b = window.__xrayBcf;
    const snap = await b.composeSnapshot(A);
    const bytes = await b.exportZip('3.0');
    let bin = '';
    for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
    let sbin = '';
    if (snap) for (let i = 0; i < snap.length; i += 0x8000) sbin += String.fromCharCode(...snap.subarray(i, i + 0x8000));
    return { zip: btoa(bin), snap: snap ? btoa(sbin) : null };
  }, made.A);
  const zipFile = join(tmp, 'w7.bcfzip');
  writeFileSync(zipFile, Buffer.from(exported.zip, 'base64'));
  if (exported.snap) writeFileSync(resolve(here, 'fixes-w7-snapshot.png'), Buffer.from(exported.snap, 'base64'));
  check('5 the burned snapshot exists (shapes, callout, measurement, pin)', !!exported.snap && exported.snap.length > 4000);

  await boot(page, 'fzk-haus');
  const back = await page.evaluate(async ({ zip, s }) => {
    const b = window.__xrayBcf;
    const bin = atob(zip);
    const u = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i);
    await b.load(u);
    const A = b.topics.find((t) => t.title === 'Window reveal');
    const B = b.topics.find((t) => t.title === 'Second');
    const app = window.__xray.app;
    const base = app.renderer.state.color.slice(s.wall.id * 3, s.wall.id * 3 + 3);
    const rep = b.applyViewpoint(A.guid);
    const tinted = app.renderer.state.color.slice(s.wall.id * 3, s.wall.id * 3 + 3);
    const sel = app.selection;
    const shapes = Object.values(b.annotations(A.guid)).flat().filter((a) => a.shape).map((a) => a.type).sort();
    b.clearViewpoint();
    const restored = app.renderer.state.color.slice(s.wall.id * 3, s.wall.id * 3 + 3);
    const C = b.createTopic({ title: 'Third', author: 'smoke' });
    return {
      nA: b.pinNumber(A.guid), nB: b.pinNumber(B.guid), nC: b.pinNumber(C.guid), status: rep.status,
      winSelected: sel.includes(s.win.id), wallSelected: sel.includes(s.wall.id), base: [...base], tinted: [...tinted], restored: [...restored], shapes,
      markupSel: A.viewpoints[0].markupSelection,
    };
  }, { zip: exported.zip, s: setup });
  console.log('    after import:', JSON.stringify(back));
  check('6 pin numbers survive the round trip; the next topic gets 3', back.nA === 1 && back.nB === 2 && back.nC === 3, `${back.nA}, ${back.nB}, ${back.nC}`);
  check('3 applied after the import: the window is selected, the annotated wall is not (no focus, keeps the x-ray look)', back.winSelected && !back.wallSelected && /annotated highlighted/.test(back.status), back.status);
  check('3 the annotated wall gets the selection tint until Clear viewpoint', back.tinted[2] < back.base[2] - 0.05 && back.restored.every((v, i) => Math.abs(v - back.base[i]) < 1e-6), JSON.stringify({ base: back.base, tinted: back.tinted, restored: back.restored }));
  check('5 rectangle and freehand come back from the side file', JSON.stringify(back.shapes) === JSON.stringify(['freehand', 'rect']), JSON.stringify(back.shapes));

  check('no console errors', errors.length === 0, errors.slice(0, 3).join(' | '));
} catch (e) {
  failed = true;
  console.log('ERROR', e instanceof Error ? e.stack ?? e.message : e);
} finally {
  await browser?.close();
  vite.kill();
}
process.exit(failed ? 1 : 0);
