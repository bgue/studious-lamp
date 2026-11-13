// Headless check for the 3D · Plan · Section switch of a sketch that is tied to a 3D construct, on /?model=fzk-haus
// (docs-features/issues.md, "Plan and Section views"):
//   - a cloud drawn on a wall is attached; the sketch detail and the drawing toolbar show the switch, a view-locked sketch does not;
//   - Plan: an orthographic camera looking straight down, one horizontal clip plane at the storey + 1.2 m, and the cloud still on
//     screen over the wall; Section: two vertical clip planes (cut and back) and a horizontal camera; 3D: the authored camera
//     is back and the clips the switch added are gone;
//   - a section the user had (a section plane) comes back after Plan and 3D; a section the user sets while in Plan stays;
//   - raising the sketch and exporting BCF 2.1 and 3.0 writes the Plan and Section as orthogonal viewpoints with clip planes,
//     marked as derived; opening the file again makes one sketch, not three, and a second export does not double them;
//   - phone width (360 px): the switch fits in the sheet and in the toolbar;
//   - fails on any console error.
// Screenshots: bench/derived-plan.png, derived-section.png, derived-phone.png.
// Usage: SMOKE_PORT=5713 node bench/smoke-derived-views.mjs
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const port = Number(process.env.SMOKE_PORT ?? 5713);

function loadPlaywright() {
  const candidates = [process.env.PLAYWRIGHT_MODULE, resolve(root, 'node_modules/playwright'), '/opt/node-tools/node_modules/playwright', '/opt/node22/lib/node_modules/playwright', 'playwright'].filter(Boolean);
  for (const c of candidates) {
    try { return createRequire(import.meta.url)(c); } catch { /* next */ }
  }
  throw new Error('playwright not found; set PLAYWRIGHT_MODULE');
}
const { chromium } = loadPlaywright();

const vite = spawn(resolve(root, 'node_modules/.bin/vite'), ['--config', 'bench/vite.smoke.config.mjs', '--host', '127.0.0.1', '--port', String(port), '--strictPort'], { cwd: root, stdio: ['ignore', 'pipe', 'pipe'] });
let viteLog = '';
vite.stdout.on('data', (d) => (viteLog += d));
vite.stderr.on('data', (d) => (viteLog += d));
async function waitForServer() {
  for (let i = 0; i < 150; i++) {
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
const near = (a, b, d = 1e-3) => Math.abs(a - b) <= d;

const errors = [];
let browser;
try {
  await waitForServer();
  browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1500, height: 780 } });
  const page = await ctx.newPage();
  page.setDefaultTimeout(Number(process.env.SMOKE_TIMEOUT ?? 180000));
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', (e) => errors.push(`[pageerror] ${e.message}`));

  async function boot(pg = page) {
    await pg.goto(`http://127.0.0.1:${port}/?model=fzk-haus`);
    await pg.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: 240000 });
    const err = await pg.evaluate('window.__xrayError');
    if (err) throw new Error(`startup failed: ${err}`);
  }
  async function setCamera(pos, target, pg = page) {
    await pg.evaluate(([pos, target]) => {
      const app = window.__xray.app;
      window.__cinematic?.cancelFlight?.();
      app.renderer.camera.position.set(...pos);
      app.renderer.controls.target.set(...target);
      app.renderer.controls.update();
      app.controller.settle();
    }, [pos, target]);
    await pg.waitForTimeout(300);
  }
  /** The camera, the projection and the clip planes of the live view. */
  const live = (pg = page) => pg.evaluate(() => {
    const r = window.__xray.app.renderer;
    const c = r.camera;
    const d = c.getWorldDirection(c.position.clone());
    return { fov: c.fov, pos: [c.position.x, c.position.y, c.position.z], dir: [d.x, d.y, d.z], clips: r.getClipPlanes() ?? [] };
  });
  const frames = (n = 3, pg = page) => pg.evaluate((n) => new Promise((res) => { let i = 0; const f = () => (++i >= n ? res(0) : requestAnimationFrame(f)); requestAnimationFrame(f); }), n);
  const elementBox = (guid, pg = page) => pg.evaluate((guid) => {
    const app = window.__xray.app;
    const id = app.controller.model.byGlobalId.get(guid);
    const b = app.controller.model.elements[id].bounds;
    const cm = app.renderer.camera;
    cm.updateMatrixWorld();
    const r = app.canvas.getBoundingClientRect();
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (let i = 0; i < 8; i++) {
      const v = cm.position.clone().set(i & 1 ? b[3] : b[0], i & 2 ? b[4] : b[1], i & 4 ? b[5] : b[2]).project(cm);
      const x = r.left + (v.x * 0.5 + 0.5) * r.width, y = r.top + (1 - (v.y * 0.5 + 0.5)) * r.height;
      x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y);
    }
    return { x0, y0, x1, y1 };
  }, guid);
  const outlineBox = (id, pg = page) => pg.evaluate((id) => {
    const els = Array.from(document.querySelectorAll(`[data-mk="${id}"] [data-role="shape"]`));
    if (!els.length) return null;
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (const e of els) { const r = e.getBoundingClientRect(); x0 = Math.min(x0, r.left); y0 = Math.min(y0, r.top); x1 = Math.max(x1, r.right); y1 = Math.max(y1, r.bottom); }
    return { x0, y0, x1, y1 };
  }, id);
  const onElement = (o, e, slack = 14) => !!o && !!e && (o.x0 + o.x1) / 2 >= e.x0 - slack && (o.x0 + o.x1) / 2 <= e.x1 + slack && (o.y0 + o.y1) / 2 >= e.y0 - slack && (o.y0 + o.y1) / 2 <= e.y1 + slack;
  const rect = (sel, pg = page) => pg.evaluate((s) => { const e = document.querySelector(s); if (!e) return null; const r = e.getBoundingClientRect(); return { x: r.left, y: r.top, w: r.width, h: r.height, r: r.right, b: r.bottom }; }, sel);

  /** Find the biggest wall, put the camera in front of it and add a cloud on it. Returns the ids. */
  async function sketchOnWall(pg = page, author = 'smoke@example.org') {
    void author;
    const wallGuid = await pg.evaluate(() => {
      const els = window.__xray.app.controller.model.elements;
      const walls = els.filter((e) => e.ifcClass === 'IfcWallStandardCase' && e.globalId).sort((a, b) => ((b.bounds[3] - b.bounds[0]) * (b.bounds[4] - b.bounds[1])) - ((a.bounds[3] - a.bounds[0]) * (a.bounds[4] - a.bounds[1])));
      return walls[0].globalId;
    });
    const info = await pg.evaluate((g) => {
      const app = window.__xray.app;
      const e = app.controller.model.elements[app.controller.model.byGlobalId.get(g)];
      const b = e.bounds;
      return { b: [...b], c: [(b[0] + b[3]) / 2, (b[1] + b[4]) / 2, (b[2] + b[5]) / 2], size: [b[3] - b[0], b[4] - b[1], b[5] - b[2]], storey: e.storey };
    }, wallGuid);
    const along = info.size[0] > info.size[2] ? [0, 0, 1] : [1, 0, 0];
    await setCamera([info.c[0] + along[0] * 14 + 4, info.c[1] + 3, info.c[2] + along[2] * 14 + 4], [info.c[0] - along[0] * 6, info.c[1], info.c[2] - along[2] * 6], pg);
    const set = await pg.evaluate(() => window.__xrayIssues.newSketch('Wall clash').id);
    await pg.waitForTimeout(300);
    const wb = await elementBox(wallGuid, pg);
    const cv = await pg.evaluate(() => { const r = window.__xray.app.canvas.getBoundingClientRect(); return { l: r.left, t: r.top, w: r.width, h: r.height }; });
    // inside the wall's screen box and inside the canvas, away from the edge chrome
    const x0 = Math.max(wb.x0, cv.l + 60), x1 = Math.min(wb.x1, cv.l + cv.w - 12), y0 = Math.max(wb.y0, cv.t + 60), y1 = Math.min(wb.y1, cv.t + cv.h - 200);
    const px = [x0 + (x1 - x0) * 0.3 - cv.l, y0 + (y1 - y0) * 0.3 - cv.t], qx = [x0 + (x1 - x0) * 0.7 - cv.l, y0 + (y1 - y0) * 0.7 - cv.t];
    const mk = await pg.evaluate(([p, q]) => { const m = window.__xrayMarkup.add({ kind: 'cloud', points: [p, q] }); return { id: m.id, attach: window.__xrayMarkup.attachment(m.id)?.attach.kind }; }, [px, qx]);
    return { set, wallGuid, info, markup: mk };
  }

  // ------------------------------------------------------------------ part 1: tied sketch, the switch, Plan, Section, 3D
  await boot();
  await page.keyboard.press('k');
  await page.waitForSelector('#issues-panel');
  const A = await sketchOnWall();
  check('the cloud drawn on the wall is attached (surface)', A.markup.attach === 'surface', A.markup.attach);
  await page.waitForTimeout(400);
  const authored = await page.evaluate((id) => { const s = window.__xrayMarkup.get(id); return { cam: s.view.camera, aspect: s.camera.aspect }; }, A.set);
  const cam3d = await live();
  check('3D is the starting mode and the sketch has the switch', await page.evaluate((id) => window.__xrayIssues.viewMode(id) === '3d' && window.__xrayIssues.viewSwitchAvailable(id), A.set));

  // the switch in the drawing toolbar (the sketch is being edited) and a view-locked sketch has none
  await page.waitForSelector('#markup-float [data-view-switch]');
  const tbModes = await page.evaluate(() => [...document.querySelectorAll('#markup-float [data-view-switch] [data-view-mode]')].map((b) => `${b.dataset.viewMode}:${b.getAttribute('aria-pressed')}`));
  check('the drawing toolbar shows 3D · Plan · Section with 3D pressed', JSON.stringify(tbModes) === JSON.stringify(['3d:true', 'plan:false', 'section:false']), tbModes.join(','));
  const lockedId = await page.evaluate(() => {
    const s = window.__xrayMarkup.create('Locked');
    window.__xrayMarkup.add({ kind: 'cloud', fractions: { points: [[0.3, 0.3], [0.5, 0.5]], depth: 8 } });
    window.__xrayMarkup.setAttachment(window.__xrayMarkup.get(s.id).markups[0].id, 'none');
    return s.id;
  });
  await page.waitForTimeout(200);
  check('a view-locked sketch has no switch', await page.evaluate((id) => !window.__xrayIssues.viewSwitchAvailable(id) && !document.querySelector('#markup-float [data-view-switch]'), lockedId));
  await page.evaluate((id) => window.__xrayMarkup.deleteSet(id), lockedId);
  await page.evaluate((id) => { window.__xrayMarkup.restore(id, { animate: false }); }, A.set);
  await page.evaluate(() => window.__xrayIssues.stopEditing());
  await setCamera(cam3d.pos, await page.evaluate(() => { const t = window.__xray.app.renderer.controls.target; return [t.x, t.y, t.z]; }));
  await page.evaluate((id) => window.__xrayIssues.openSketch(id), A.set);
  await page.waitForSelector('#issues-panel [data-view-switch-row]');
  check('the sketch detail shows the switch', (await page.textContent('#issues-panel [data-view-switch-row]')).replace(/\s+/g, '') === 'View3DPlanSection');
  await page.evaluate(() => window.__xrayIssues.editSketch(window.__xrayIssues.detail.id));
  await page.waitForSelector('#markup-float [data-view-switch]');
  await page.evaluate(() => window.__xrayIssues.close());

  // Plan, from the toolbar
  await page.click('#markup-float [data-view-mode=plan]');
  await frames(4);
  const plan = await live();
  const dv = await page.evaluate((id) => window.__xrayIssues.derivedView(id, 'plan'), A.set);
  check('Plan: an orthographic camera (2 degree field of view) looking straight down', near(plan.fov, 2, 1e-6) && near(plan.dir[1], -1, 1e-4), JSON.stringify({ fov: plan.fov, dir: plan.dir }));
  const wallBottom = A.info.b[1];
  const cutExpected = wallBottom + 1.2;
  check('Plan: one horizontal clip plane at the storey level + 1.2 m', plan.clips.length === 1 && near(plan.clips[0].normal[1], -1, 1e-6) && near(plan.clips[0].point[1], dv.cutHeight, 1e-3) && near(dv.cutHeight, cutExpected, 0.4),
    `cut ${plan.clips[0]?.point[1]?.toFixed(3)} planned ${dv.cutHeight?.toFixed(3)} wall bottom + 1.2 = ${cutExpected.toFixed(3)}`);
  check('Plan: the toolbar says Plan', await page.evaluate(() => document.querySelector('#markup-float [data-view-mode=plan]').getAttribute('aria-pressed') === 'true' && window.__xrayIssues.viewMode(window.__xrayMarkup.list().find((s) => s.active).id) === 'plan'));
  await page.waitForTimeout(500);
  const planOutline = await outlineBox(A.markup.id);
  const planWall = await elementBox(A.wallGuid);
  check('Plan: the sketch shape is still on screen, over the wall', onElement(planOutline, planWall), JSON.stringify({ planOutline, planWall }));
  await page.mouse.move(2, 2);
  await page.waitForTimeout(400);
  await page.screenshot({ path: resolve(here, 'derived-plan.png') });

  // Section
  await page.click('#markup-float [data-view-mode=section]');
  await frames(4);
  const sec = await live();
  const sv = await page.evaluate((id) => window.__xrayIssues.derivedView(id, 'section'), A.set);
  const horizontal = (v) => Math.abs(v[1]) < 1e-6;
  check('Section: a horizontal camera and two vertical clip planes, cut and back, facing each other', sec.clips.length === 2 && horizontal(sec.dir) && sec.clips.every((c) => horizontal(c.normal)) && near(sec.clips[0].normal[0] + sec.clips[1].normal[0], 0, 1e-6) && near(sec.clips[0].normal[2] + sec.clips[1].normal[2], 0, 1e-6),
    JSON.stringify({ dir: sec.dir, clips: sec.clips }));
  const along = Math.abs(sec.dir[0]) > Math.abs(sec.dir[2]) ? 0 : 2;
  const wallThin = A.info.size[0] > A.info.size[2] ? 2 : 0;
  // The cloud lies on the wall face, so its normal is clearly horizontal: the cut is parallel to the face and looks into it.
  check('Section: the cut follows the surface normal of the wall face (looking into it), through the target, with a back plane', sv.basis === 'normal' && along === wallThin && near(sec.clips[0].normal[0] * sec.dir[0] + sec.clips[0].normal[2] * sec.dir[2], 1, 1e-6) && near(sec.clips[0].point[along], sv.target[along], 1e-3) && sv.depth >= 2 && near(sec.clips[1].point[along] - sec.clips[0].point[along], sec.dir[along] * sv.depth, 1e-3),
    `view axis ${along} wall thin axis ${wallThin} depth ${sv.depth?.toFixed(2)} basis ${sv.basis}`);
  await page.waitForTimeout(500);
  const secOutline = await outlineBox(A.markup.id);
  check('Section: the sketch is still drawn', !!secOutline, JSON.stringify(secOutline));
  await page.mouse.move(2, 2);
  await page.waitForTimeout(400);
  await page.screenshot({ path: resolve(here, 'derived-section.png') });

  // back to 3D
  await page.click('#markup-float [data-view-mode="3d"]');
  await frames(4);
  const back = await live();
  check('3D: the authored camera is back (position, field of view, perspective)', near(back.fov, authored.cam.fov, 1e-6) && Math.hypot(back.pos[0] - authored.cam.position[0], back.pos[1] - authored.cam.position[1], back.pos[2] - authored.cam.position[2]) < 1e-2, JSON.stringify({ fov: back.fov, pos: back.pos, want: authored.cam.position }));
  check('3D: the clip planes the switch added are gone', back.clips.length === 0);
  check('3D: the switch says 3D', await page.evaluate((id) => window.__xrayIssues.viewMode(id) === '3d', A.set));

  // ------------------------------------------------------------------ part 2: a section the user set survives
  await page.evaluate(() => window.__xraySection.set({ plane: { enabled: true, axis: 'y', offset: 1.5 } }));
  await frames(4);
  const user0 = await live();
  check('a user section plane is in force', user0.clips.length === 1 && near(user0.clips[0].normal[1], -1, 1e-6) || user0.clips.length === 1, JSON.stringify(user0.clips));
  await page.click('#markup-float [data-view-mode=plan]');
  await frames(4);
  const inPlan = await live();
  check('Plan replaces the user section with its own cut', inPlan.clips.length === 1 && Math.abs(inPlan.clips[0].point[1] - user0.clips[0].point[1]) > 1e-3, JSON.stringify(inPlan.clips));
  await page.click('#markup-float [data-view-mode=section]');
  await frames(3);
  await page.click('#markup-float [data-view-mode="3d"]');
  await frames(5);
  const user1 = await live();
  const same = user1.clips.length === user0.clips.length && user1.clips.every((c, i) => c.normal.every((v, k) => near(v, user0.clips[i].normal[k], 1e-6)) && c.point.every((v, k) => near(v, user0.clips[i].point[k], 1e-6)));
  check('3D puts the user section back, and the section tool owns it again', same && (await page.evaluate(() => window.__xraySection.foreignPlanes() === 0 && window.__xraySection.config.plane.enabled === true)), JSON.stringify({ before: user0.clips, after: user1.clips }));
  // a section the user changes while in Plan stands when 3D is pressed
  await page.click('#markup-float [data-view-mode=plan]');
  await frames(3);
  await page.evaluate(() => window.__xraySection.set({ plane: { enabled: true, axis: 'y', offset: 2.5 } }));
  await frames(4);
  const mid = await live();
  await page.click('#markup-float [data-view-mode="3d"]');
  await frames(4);
  const user2 = await live();
  check('a section changed in Plan stays after 3D', user2.clips.length === 1 && near(user2.clips[0].point[1], mid.clips[0].point[1], 1e-6), JSON.stringify({ mid: mid.clips, after: user2.clips }));
  await page.evaluate(() => window.__xraySection.clear());
  await frames(3);
  check('without a section of the user, 3D leaves none', (await live()).clips.length === 0);
  await page.click('#markup-float [data-view-mode=plan]');
  await frames(3);
  await page.click('#markup-float [data-view-mode="3d"]');
  await frames(3);
  check('Plan then 3D with no user section leaves no clip plane', (await live()).clips.length === 0);

  // ------------------------------------------------------------------ part 3: raise, export, open again
  await page.evaluate(() => window.__xrayIssues.stopEditing());
  const issueGuid = await page.evaluate((id) => window.__xrayIssues.raise(id), A.set);
  await page.evaluate((g) => window.__xrayIssues.openIssue(g, { apply: false }), issueGuid);
  await page.waitForSelector('#issues-panel [data-view-switch-row]');
  check('the issue detail shows the switch on the sketch row', true);
  await page.click('#issues-panel [data-view-switch-row] [data-view-mode=section]');
  await frames(3);
  check('the issue detail switch drives the live view', (await live()).clips.length === 2);
  await page.click('#issues-panel [data-view-switch-row] [data-view-mode="3d"]');
  await frames(3);
  const nSketches = await page.evaluate(() => window.__xrayMarkup.list().length);
  const out = {};
  for (const v of ['2.1', '3.0']) {
    out[v] = await page.evaluate(async (v) => {
      const bytes = await window.__xrayBcf.exportZip(v);
      const { parseBcf } = await import('/src/bcf/parse.ts');
      const proj = await parseBcf(bytes);
      const t = proj.topics[0];
      return { n: t.viewpoints.length, derived: t.viewpoints.filter((x) => x.derived).map((x) => ({ kind: x.derived.kind, cam: x.data?.camera?.kind, scale: x.data?.camera?.viewToWorldScale, planes: x.data?.clipping.length, sel: x.data?.selection.length })), srcSel: t.viewpoints[0].data.selection.length, bytes: Array.from(bytes) };
    }, v);
  }
  for (const v of ['2.1', '3.0']) {
    const o = out[v];
    check(`BCF ${v}: Plan and Section are written as orthogonal viewpoints with clip planes, marked derived`, o.n === 3 && o.derived.length === 2 && o.derived[0].kind === 'plan' && o.derived[1].kind === 'section' && o.derived.every((d) => d.cam === 'orthogonal' && d.scale > 0 && d.planes >= 1 && d.sel === o.srcSel) && o.derived[0].planes === 1 && o.derived[1].planes === 2, JSON.stringify({ ...o, bytes: undefined }));
  }
  check('the session project is not changed by the export (no derived viewpoint is stored)', await page.evaluate(() => window.__xrayBcf.topics[0].viewpoints.length === 1));
  // a fresh session: no sketches, open the file
  const reopened = await page.evaluate(async (bytes) => {
    for (const s of window.__xrayMarkup.list({ all: true })) window.__xrayMarkup.deleteSet(s.id);
    await window.__xrayBcf.load(new Uint8Array(bytes));
    const t = window.__xrayBcf.topics[0];
    return { topics: window.__xrayBcf.topics.length, vps: t.viewpoints.length, derived: t.viewpoints.filter((v) => v.derived).length, sketches: window.__xrayMarkup.list().length, derivedSketch: t.viewpoints.filter((v) => v.derived && v.sketchId).length, linked: !!t.viewpoints[0].sketchId };
  }, out['3.0'].bytes);
  check('opening the file again: 1 sketch, linked to the source viewpoint; the 2 derived viewpoints are views of it, not sketches', reopened.topics === 1 && reopened.vps === 3 && reopened.derived === 2 && reopened.sketches === nSketches && reopened.derivedSketch === 0 && reopened.linked, JSON.stringify(reopened));
  const again = await page.evaluate(async () => {
    const bytes = await window.__xrayBcf.exportZip('3.0');
    const { parseBcf } = await import('/src/bcf/parse.ts');
      const proj = await parseBcf(bytes);
    return { vps: proj.topics[0].viewpoints.length, derived: proj.topics[0].viewpoints.filter((v) => v.derived).length };
  });
  check('exporting again does not double the derived viewpoints', again.vps === 3 && again.derived === 2, JSON.stringify(again));
  // a derived viewpoint applies like any viewpoint: the orthographic camera and its cut
  await page.evaluate(() => window.__xrayIssues.openIssue(window.__xrayBcf.topics[0].guid, { apply: false }));
  await page.waitForSelector('#issues-panel [data-derived=plan]');
  await page.click('#issues-panel [data-derived=plan] [data-act=apply]');
  await frames(4);
  const applied = await live();
  check('a derived Plan viewpoint applies with its clip plane (as a foreign viewer would use it)', applied.clips.length === 1 && near(applied.clips[0].normal[1], -1, 1e-6), JSON.stringify(applied.clips));
  await page.click('#issues-panel [data-derived=plan] [data-act=clear]');

  // ------------------------------------------------------------------ part 4: phone width
  const phone = await browser.newContext({ viewport: { width: 360, height: 740 }, hasTouch: true, isMobile: true, deviceScaleFactor: 2 });
  const pp = await phone.newPage();
  pp.setDefaultTimeout(180000);
  pp.on('console', (m) => { if (m.type() === 'error') errors.push(`[phone] ${m.text()}`); });
  pp.on('pageerror', (e) => errors.push(`[phone pageerror] ${e.message}`));
  await boot(pp);
  const P = await sketchOnWall(pp);
  check('phone: the cloud is attached', P.markup.attach === 'surface', P.markup.attach);
  await pp.waitForSelector('#markup-float [data-view-switch]');
  const tb = await rect('#markup-float [data-view-switch]', pp);
  const tbar = await rect('#markup-float', pp);
  check('phone: the switch fits the drawing toolbar at 360 px', !!tb && tb.x >= 0 && tb.r <= 360.5 && !!tbar && tbar.r <= 360.5 && tb.h >= 28, JSON.stringify({ tb, tbar }));
  await pp.click('#markup-float [data-view-mode=plan]');
  await frames(4, pp);
  check('phone: Plan from the toolbar', (await live(pp)).clips.length === 1);
  await pp.click('#markup-float [data-view-mode="3d"]');
  await frames(3, pp);
  await pp.evaluate(() => { window.__xrayIssues.stopEditing(); window.__xrayIssues.openSketch(window.__xrayIssues.detail?.id ?? window.__xrayMarkup.list()[0].id); });
  await pp.waitForSelector('#issues-sheet.on [data-view-switch]');
  const sw = await rect('#issues-sheet [data-view-switch]', pp);
  const sheet = await rect('#issues-sheet', pp);
  check('phone: the switch fits the bottom sheet at 360 px', !!sw && sw.x >= 0 && sw.r <= 360.5 && !!sheet && sheet.r <= 360.5 && sw.h >= 28, JSON.stringify({ sw, sheet }));
  await pp.click('#issues-sheet [data-view-mode=plan]');
  await frames(4, pp);
  check('phone: Plan from the sheet', (await live(pp)).clips.length === 1 && (await pp.evaluate(() => document.querySelector('#issues-sheet [data-view-mode=plan]').getAttribute('aria-pressed') === 'true')));
  check('phone: no horizontal page scroll', await pp.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1));
  await pp.evaluate(() => document.activeElement?.blur?.());
  await pp.mouse.move(2, 2);
  await pp.waitForTimeout(500);
  await pp.screenshot({ path: resolve(here, 'derived-phone.png') });
  await phone.close();

  check('no console errors', errors.length === 0, errors.slice(0, 4).join(' | '));
} catch (e) {
  failed = true;
  console.log('ERROR', e instanceof Error ? e.stack ?? e.message : e);
} finally {
  await browser?.close();
  vite.kill();
}
process.exit(failed ? 1 : 0);
