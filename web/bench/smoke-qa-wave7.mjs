// QA wave 7 cross-feature smoke (bench/RESULTS-qa-wave7.md). One dev server (SMOKE_PORT, default 5655), four parts:
//   1 saved views x BCF (viewpoint with plane, hide, callout, pin) x section box from the gizmo x explode x presets (fzk-haus)
//   2 field AR (iwer Quest 3 + the stub hit test of smoke-xr-field.mjs): views refused during the session; after exit
//     saved views, BCF and sections work and nothing of the session stays (fzk-haus)
//   3 reserved rects: measure labels, BCF pins and notes under the gizmo, status bar, tool strip and drawer, with the Views
//     tab open, at 1600x900 and on a 390x844 phone with the sidebar closed (the phone with the Views drawer open is
//     reported, not checked: 62 px of canvas are left, see RESULTS-qa-wave7.md)
//   4 point cloud "align within: section box" with the box set by the gizmo button (building + phone scan)
// Screenshots bench/qa7-*.png. Exit code 1 on any failure or console error.
//   SMOKE_PORT=5655 node bench/smoke-qa-wave7.mjs [1 2 3 4]
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const WEB = resolve(here, '..');
const SHOTS = here;
const port = Number(process.env.SMOKE_PORT ?? 5655);
const url = `http://127.0.0.1:${port}`;
const want = process.argv.slice(2).length ? new Set(process.argv.slice(2)) : new Set(['1', '2', '3', '4']);
const req = createRequire(import.meta.url);
let pw = null;
for (const c of [process.env.PLAYWRIGHT_MODULE, resolve(WEB, 'node_modules/playwright'), '/opt/node-tools/node_modules/playwright', '/opt/node22/lib/node_modules/playwright', 'playwright'].filter(Boolean)) {
  try { pw = req(c); break; } catch { /* next */ }
}
if (!pw) throw new Error('playwright not found; set PLAYWRIGHT_MODULE');
const { chromium } = pw;

let failed = 0;
const check = (name, ok, detail = '') => { if (!ok) failed++; console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${detail ? ` (${detail})` : ''}`); };
async function openApp(browser, base, q, vp = { width: 1600, height: 900 }, extra = {}) {
  const ctx = await browser.newContext({ viewport: vp, ...extra });
  const page = await ctx.newPage();
  page.setDefaultTimeout(180000);
  const errors = [];
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', (e) => errors.push(`[pageerror] ${e.message}`));
  await page.goto(`${base}/${q}`, { timeout: 240000 });
  await page.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: 240000 });
  const err = await page.evaluate('window.__xrayError');
  if (err) throw new Error('startup ' + err);
  return { ctx, page, errors };
}

const vite = spawn(resolve(WEB, 'node_modules/.bin/vite'), ['--config', resolve(here, 'vite.smoke.config.mjs'), '--host', '127.0.0.1', '--port', String(port), '--strictPort'], { cwd: WEB, stdio: ['ignore', 'pipe', 'pipe'] });
let viteLog = '';
vite.stdout.on('data', (d) => (viteLog += d));
vite.stderr.on('data', (d) => (viteLog += d));
async function waitForServer() {
  for (let i = 0; i < 150; i++) {
    try { const r = await fetch(`${url}/`); if (r.ok) return; } catch { /* retry */ }
    await new Promise((r) => setTimeout(r, 200));
  }
  throw new Error('vite did not start:\n' + viteLog);
}

async function part1() {
  const browser = await chromium.launch();
const settle = (page, ms = 600) => page.evaluate(() => window.__xray.app.controller.settle()).then(() => page.waitForTimeout(ms));
const state = (page) => page.evaluate(() => {
  const app = window.__xray.app, b = window.__xrayBcf;
  const planes = app.renderer.getClipPlanes();
  const sec = window.__xraySection.config;
  return {
    planes: planes ? planes.length : 0,
    box: sec.box.enabled, plane: sec.plane.enabled,
    pins: document.querySelectorAll('svg.xray-svg-overlay [data-bcf-pin]').length,
    // A viewpoint's drawing is its sketch (docs-features/issues.md): the markup view draws it (data-mk) and the BCF overlay draws none of it.
    anns: document.querySelectorAll('svg.xray-svg-overlay [data-bcf-ann], svg.xray-svg-overlay [data-mk]').length,
    hidden: app.controller.settings.overrides.userHides.size,
    sel: app.selection.length,
    bcfStatus: b.status,
    exploded: !!window.__cinematic?.exploded,
    handles: document.querySelectorAll('[data-plane-handle], .xg-handle, #xray-plane-handles *').length,
    preset: window.__xrayPresets.active(),
    color: (() => { const id = window.__qa?.win; if (id === undefined) return null; const c = app.renderer.state.color; return [c[id * 3], c[id * 3 + 1], c[id * 3 + 2]].map((v) => +v.toFixed(3)); })(),
  };
});  try {
  const { page, errors } = await openApp(browser, url, '?model=fzk-haus');
  await page.evaluate(() => { for (const k of Object.keys(localStorage)) if (k.startsWith('xray.views')) localStorage.removeItem(k); });
  // ---- setup: a BCF topic with a section plane, a hidden element, the window selected and a callout on it
  const setup = await page.evaluate(() => {
    const app = window.__xray.app;
    const els = app.controller.model.elements;
    const win = els.find((e) => e.ifcClass === 'IfcWindow');
    const slab = els.find((e) => e.ifcClass === 'IfcRoof' || e.ifcClass === 'IfcSlab');
    window.__qa = { win: win.id };
    return { win: win.id, winGid: win.globalId, roof: slab.id, color0: [...app.renderer.state.color.slice(win.id * 3, win.id * 3 + 3)].map((v) => +v.toFixed(3)) };
  });
  const s0 = await state(page);
  await page.evaluate(() => window.__xrayViews.save('plain'));
  await page.evaluate((s) => {
    const app = window.__xray.app;
    app.selectIds([s.win]);
    window.__cinematic?.cancelFlight?.();
    app.controller.settings.overrides.userHides.add(s.roof); app.controller.refreshOverrides();
    window.__xraySection.set({ plane: { enabled: true } });
  }, setup);
  await settle(page, 1500);
  const topic = await page.evaluate((s) => {
    const b = window.__xrayBcf;
    const t = b.createTopic({ title: 'QA window' });
    const e = window.__xray.app.controller.model.elements[s.win].bounds;
    b.addAnnotation(t.guid, { type: 'callout', text: 'QA callout', anchor: { kind: 'element', point: [(e[0] + e[3]) / 2, (e[1] + e[4]) / 2, (e[2] + e[5]) / 2], elementGuid: s.winGid } });
    return { guid: t.guid, vps: t.viewpoints.length, clip: t.viewpoints[0]?.data?.clippingPlanes?.length ?? null };
  }, setup);
  // back to a neutral state, no section, no hide, no selection
  await page.evaluate((s) => {
    const app = window.__xray.app;
    window.__xraySection.clear();
    app.controller.settings.overrides.userHides.delete(s.roof); app.controller.refreshOverrides();
    app.clearSelection();
  }, setup);
  await settle(page);
  console.log('topic', JSON.stringify(topic), 's0', JSON.stringify(s0));
  // ---- apply the BCF viewpoint, save a view while it is applied
  const rep = await page.evaluate((g) => window.__xrayBcf.applyViewpoint(g), topic.guid);
  await settle(page, 1200);
  const sA = await state(page);
  console.log('BCF applied:', rep.status, JSON.stringify(sA));
  check('BCF viewpoint applied: planes, pin, callout drawn', sA.planes > 0 && sA.pins === 1 && sA.anns >= 1, JSON.stringify(sA));
  await page.evaluate(() => window.__xrayViews.save('with bcf'));
  const vB = await page.evaluate(() => window.__xrayViews.get('with bcf'));
  check('view saved under BCF keeps its clip planes and the hide', (vB.clip?.length ?? 0) > 0 && (vB.hides?.ids?.length ?? 0) >= 1, `clip ${vB.clip?.length} hides ${JSON.stringify(vB.hides)}`);
  await page.screenshot({ path: `${SHOTS}/qa7-bcf-applied.png` });
  // ---- restore the plain view: nothing of the BCF viewpoint should stay
  await page.evaluate(() => window.__xrayViews.restore('plain', { animate: false }));
  await settle(page, 1200);
  const sP = await state(page);
  check('restore "plain" after BCF: no clip planes', sP.planes === 0, JSON.stringify(sP));
  check('restore "plain" after BCF: no stray BCF pin or callout', sP.pins === 0 && sP.anns === 0, `pins ${sP.pins} anns ${sP.anns}`);
  check('restore "plain" after BCF: no hides, no selection, window colour restored', sP.hidden === 0 && sP.sel === 0 && JSON.stringify(sP.color) === JSON.stringify(setup.color0), `hidden ${sP.hidden} sel ${sP.sel} colour ${sP.color} vs ${setup.color0}`);
  await page.screenshot({ path: `${SHOTS}/qa7-bcf-restore-plain.png` });
  // ---- restore the view saved under BCF, then plain again
  await page.evaluate(() => window.__xrayViews.restore('with bcf', { animate: false }));
  await settle(page, 1200);
  const sB = await state(page);
  check('restore "with bcf": its planes and hide come back', sB.planes === sA.planes && sB.hidden === sA.hidden, JSON.stringify(sB));
  // a later Clear viewpoint must not undo the view's hides
  await page.evaluate(() => window.__xrayBcf.clearViewpoint());
  await settle(page);
  const sBc = await state(page);
  check('BCF Clear viewpoint after restoring "with bcf" keeps the view hides and planes', sBc.hidden === sB.hidden && sBc.planes === sB.planes, `hidden ${sB.hidden}->${sBc.hidden} planes ${sB.planes}->${sBc.planes}`);
  await page.evaluate(() => window.__xrayViews.restore('plain', { animate: false }));
  await settle(page, 1200);
  const sP2 = await state(page);
  check('restore "plain" again: no planes, no hides', sP2.planes === 0 && sP2.hidden === 0, JSON.stringify(sP2));

  // ---- section box set with the gizmo button (real click), save, restore
  await page.evaluate((s) => { window.__xray.app.selectIds([s.win]); window.__cinematic?.cancelFlight?.(); }, setup);
  await settle(page, 800);
  const bx = page.locator('#xray-gizmo .xg-btn[title^="Section box"]');
  await bx.click();
  await settle(page, 800);
  const sG = await state(page);
  check('gizmo box button sets a section box around the selection', sG.box && sG.planes === 6, JSON.stringify(sG));
  await page.evaluate(() => window.__xrayViews.save('gizmo box'));
  await page.screenshot({ path: `${SHOTS}/qa7-gizmo-box.png` });
  // apply the BCF viewpoint over the box (the section tool owned the planes)
  await page.evaluate((g) => window.__xrayBcf.applyViewpoint(g), topic.guid);
  await settle(page, 1000);
  const sGB = await state(page);
  await page.evaluate(() => window.__xrayViews.restore('gizmo box', { animate: false }));
  await settle(page, 1200);
  const sG2 = await state(page);
  check('restore "gizmo box" over an applied BCF viewpoint: the box, no BCF pin or callout', sG2.box && sG2.planes === 6 && sG2.pins === 0 && sG2.anns === 0, `before ${JSON.stringify(sGB)} after ${JSON.stringify(sG2)}`);
  await page.evaluate(() => window.__xrayViews.restore('plain', { animate: false }));
  await settle(page, 1000);
  const sP3 = await state(page);
  check('restore "plain" after "gizmo box": box off, no planes', !sP3.box && sP3.planes === 0, JSON.stringify(sP3));
  const gzBtn = await page.evaluate(() => document.querySelector('#xray-gizmo .xg-btn[title^="Section box"]')?.getAttribute('aria-pressed'));
  check('gizmo box button not pressed after restoring "plain"', gzBtn !== 'true', `aria-pressed ${gzBtn}`);

  // ---- explode with callouts, restore during explode
  await page.evaluate((g) => window.__xrayBcf.applyViewpoint(g), topic.guid);
  await settle(page, 800);
  await page.evaluate(() => { window.__xray.app.selectIds([]); });
  await page.evaluate(() => window.__cinematic.explode());
  await page.waitForTimeout(300); // mid animation
  const sE = await state(page);
  await page.evaluate(() => window.__xrayViews.restore('with bcf', { animate: true }));
  await page.waitForTimeout(2500);
  await settle(page);
  const sE2 = await state(page);
  check('restore during explode: collapsed, view state, no console error', !sE2.exploded && sE2.planes === sA.planes, `exploding ${JSON.stringify(sE)} -> ${JSON.stringify(sE2)}`);
  const offs = await page.evaluate(() => { const r = window.__xray.app.renderer; let mx = 0; const n = window.__xray.app.controller.model.elements.length; for (let i = 0; i < n; i++) { const o = r.elementOffset?.(i); if (o) mx = Math.max(mx, Math.hypot(o[0] ?? o.x ?? 0, o[1] ?? o.y ?? 0, o[2] ?? o.z ?? 0)); } return mx; });
  check('restore during explode: no element left displaced', offs < 1e-4, `max offset ${offs}`);
  await page.screenshot({ path: `${SHOTS}/qa7-explode-restore.png` });
  // explode then save a view exploded with callouts on screen, restore plain and back
  await page.evaluate((g) => { window.__xrayBcf.applyViewpoint(g); }, topic.guid);
  await page.evaluate(() => window.__cinematic.explode());
  await page.waitForTimeout(2500);
  await page.evaluate(() => window.__xrayViews.save('exploded'));
  await page.screenshot({ path: `${SHOTS}/qa7-exploded-callouts.png` });
  const anEx = await page.evaluate(() => [...document.querySelectorAll('svg.xray-svg-overlay [data-bcf-ann]')].map((e) => e.getBoundingClientRect().toJSON()));
  await page.evaluate(() => window.__xrayViews.restore('plain', { animate: false }));
  await settle(page, 1500);
  const sX = await state(page);
  check('restore "plain" from exploded with callouts: collapsed, no callout left', !sX.exploded && sX.anns === 0 && sX.pins === 0, JSON.stringify(sX));
  await page.evaluate(() => window.__xrayViews.restore('exploded', { animate: false }));
  await page.waitForTimeout(2500);
  const sX2 = await state(page);
  check('restore "exploded": exploded again', sX2.exploded, JSON.stringify(sX2));
  await page.evaluate(() => window.__xrayViews.restore('plain', { animate: false }));
  await settle(page, 1500);

  // ---- presets: save a view with a preset, change preset, restore
  const presets = await page.evaluate(() => window.__xrayPresets.list().map((p) => p.id));
  console.log('presets', presets.join(','));
  const pid = presets.find((p) => /radiograph|section-focus|behind/.test(p)) ?? presets[1];
  const other = presets.find((p) => p !== pid && /standard|default|xray/.test(p)) ?? presets[0];
  await page.evaluate((s) => window.__xray.app.selectIds([s.win]), setup);
  await page.evaluate((id) => window.__xrayPresets.apply(id), pid);
  await page.waitForTimeout(2600); // baseline hash tick
  const act0 = await page.evaluate(() => window.__xrayPresets.active());
  await page.evaluate(() => window.__xrayViews.save('preset view'));
  const pv = await page.evaluate(() => window.__xrayViews.get('preset view').preset);
  check(`view saved with preset "${pid}" records it`, pv === pid && act0 === pid, `active ${act0}, view.preset ${pv}`);
  await page.evaluate((id) => window.__xrayPresets.apply(id), other);
  await page.waitForTimeout(1500);
  await page.evaluate(() => window.__xrayViews.restore('preset view', { animate: false }));
  await page.waitForTimeout(3500);
  const act1 = await page.evaluate(() => ({ a: window.__xrayPresets.active(), list: window.__xrayPresets.list().filter((p) => p.active).map((p) => p.id) }));
  check(`restoring the view marks preset "${pid}" active`, act1.a === pid, JSON.stringify(act1));
  // A view saved without any preset active. The "plain" view of the setup above is not one: since the top bar (docs-features/topbar.md,
  // "At start ... the bar marks coordination") the app starts with `coordination` marked active, so a view saved at the start records
  // that preset and restoring it marks it active again by design (views.ts restoreView -> markActive). A changed setting clears the mark.
  await page.evaluate(() => { window.__xray.app.settings.sightlines.gamma = 1.3; });
  await page.waitForTimeout(2600);
  check('a setting change cleared the mark before the view without a preset is saved', (await page.evaluate(() => window.__xrayPresets.active())) === null);
  await page.evaluate(() => window.__xrayViews.save('unmarked view'));
  const upv = await page.evaluate(() => window.__xrayViews.get('unmarked view').preset ?? null);
  check('a view saved with no preset active records none', upv === null, `view.preset ${upv}`);
  await page.evaluate((id) => window.__xrayPresets.apply(id), other);
  await page.waitForTimeout(2600);
  await page.evaluate(() => window.__xrayViews.restore('unmarked view', { animate: false }));
  await page.waitForTimeout(3500);
  const act2 = await page.evaluate(() => window.__xrayPresets.active());
  check('restoring a view without a preset (different settings) clears the mark', act2 === null, `active ${act2}`);
  await page.evaluate(() => window.__xrayViews.restore('plain', { animate: false }));
  await page.waitForTimeout(1500);
  const act3 = await page.evaluate(() => window.__xrayPresets.active());
  check('restoring the "plain" view saved at the start marks the boot preset (coordination) again', act3 === 'coordination', `active ${act3}`);
  check('no console errors', errors.length === 0, errors.slice(0, 5).join(' | '));
  } finally { await browser.close(); }
}

const iwerSrc = readFileSync(WEB + '/node_modules/iwer/build/iwer.js', 'utf8');
const smoke = readFileSync(WEB + '/bench/smoke-xr-field.mjs', 'utf8');
const stub = /content: `(\(\(\) => \{\s*const \{ XRDevice[\s\S]*?\}\)\(\);)`/.exec(smoke)[1];
const THETA = 0.6, SHIFT = [1.5, -3.0588, -0.8];
const rotY = (p, a) => [Math.cos(a) * p[0] + Math.sin(a) * p[2], p[1], -Math.sin(a) * p[0] + Math.cos(a) * p[2]];
const toGlobal = (m) => rotY([m[0] - SHIFT[0], m[1] - SHIFT[1], m[2] - SHIFT[2]], -THETA);
const MODEL_PTS = [[-4.2, -3.0588, -3.4], [4.1, -3.0588, -2.2], [0.9, -0.3588, 3.1]];
async function part2() {
  const browser = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const errors = [];
  try {
  const ctx = await browser.newContext({ viewport: { width: 1400, height: 760 } });
  const page = await ctx.newPage();
  page.setDefaultTimeout(180000);
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', (e) => errors.push(`[pageerror] ${e.message}`));
  await page.addInitScript({ content: iwerSrc });
  await page.addInitScript({ content: stub });
  await page.goto(`${url}/?model=fzk-haus&cinematic=off`, { timeout: 240000 });
  await page.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: 240000 });
  await page.evaluate(() => { for (const k of Object.keys(localStorage)) if (k.startsWith('xray.xr.') || k.includes('anchor') || k.startsWith('xray.views')) localStorage.removeItem(k); });
  const settle = (ms = 400) => page.evaluate(async (ms) => { for (let i = 0; i < 3; i++) await new Promise((r) => requestAnimationFrame(r)); await new Promise((r) => setTimeout(r, ms)); }, ms);
  const st = () => page.evaluate(() => window.__xrayXr.state());
  const act = (a, arg) => page.evaluate(([a, arg]) => document.querySelector(`#xray-xr-field button[data-act="${arg ? `${a}:${arg}` : a}"]`).click(), [a, arg]);
  const aim = (g) => page.evaluate((g) => {
    window.__semPlaneY = g[1];
    const ctl = window.__iwer.controllers.right; const p = ctl.position;
    const d = [g[0] - p.x, g[1] - p.y, g[2] - p.z]; const l = Math.hypot(...d); const u = d.map((v) => v / l);
    const ya = Math.atan2(-u[0], -u[2]); const pi = Math.asin(u[1]);
    const qy = [0, Math.sin(ya / 2), 0, Math.cos(ya / 2)]; const qx = [Math.sin(pi / 2), 0, 0, Math.cos(pi / 2)];
    ctl.quaternion.set(qy[3] * qx[0] + qy[0] * qx[3] + qy[1] * qx[2] - qy[2] * qx[1], qy[3] * qx[1] - qy[0] * qx[2] + qy[1] * qx[3] + qy[2] * qx[0], qy[3] * qx[2] + qy[0] * qx[1] - qy[1] * qx[0] + qy[2] * qx[3], qy[3] * qx[3] - qy[0] * qx[0] - qy[1] * qx[1] - qy[2] * qx[2]);
  }, g);
  const trigger = async () => { await page.evaluate(() => window.__iwer.controllers.right.updateButtonValue('trigger', 1)); await settle(250); await page.evaluate(() => window.__iwer.controllers.right.updateButtonValue('trigger', 0)); await settle(350); };
  const snap = () => page.evaluate(() => {
    const app = window.__xray.app;
    return {
      section: JSON.stringify(window.__xraySection.config), planes: app.renderer.getClipPlanes()?.length ?? 0,
      styles: JSON.stringify(app.controller.settings.classStyles), xray: app.controller.settings.xray ?? null,
      cam: [...app.renderer.camera.position.toArray(), ...app.renderer.controls.target.toArray()].map((v) => +v.toFixed(4)),
      near: app.renderer.camera.near, far: app.renderer.camera.far,
      sidebar: !!document.querySelector('.sb-tab'), hidden: app.controller.settings.overrides.userHides.size,
    };
  });

  // a saved view and a BCF topic before AR
  await page.evaluate(() => {
    const r = window.__xray.renderer; r.camera.position.set(6, 5.5, 13); r.controls.target.set(-3.95, -1.8, -4.8); r.controls.update();
    window.__xraySection.set({ plane: { enabled: true } });
  });
  await settle(800);
  await page.evaluate(() => { window.__xrayViews.save('before AR (plane)'); window.__xraySection.clear(); });
  await settle(500);
  const pre = await snap();
  await page.evaluate((pts) => { window.__xrayXr.field.clearDraft(); for (const p of pts) window.__xrayXr.field.addModelPoint(p); }, MODEL_PTS);

  // ---- enter field AR from the GUI, register, look ghosted, cut on
  await page.evaluate(() => { const t = [...document.querySelectorAll('.lil-gui .lil-name')].find((e) => e.textContent.trim() === 'Enter field AR'); t.closest('.lil-controller').querySelector('button').click(); });
  await page.waitForFunction('window.__xray.renderer.renderer.xr.isPresenting === true', null, { timeout: 60000 });
  await settle(900);
  for (const m of MODEL_PTS) { await aim(toGlobal(m)); await settle(350); await trigger(); }
  let s = await st();
  check('field AR: registered with 3 taps', s.field.registered, `step ${s.field.step}`);
  await act('view', 'ghosted');
  await settle(500);
  const inAr = await snap();
  check('field AR: cut box on while presenting', JSON.parse(inAr.section).box.enabled, inAr.section.slice(0, 80));
  // a saved view step in AR: Shift+PageDown (the keyboard is the only Views entry in a session), and Save view
  let stepErr = null;
  try { await page.evaluate(() => window.__xrayViews.next()); } catch (e) { stepErr = String(e); }
  await settle(500);
  const inAr2 = await snap();
  check('saved view restore during field AR does not throw', !stepErr, stepErr ?? '');
  check('saved view restore during field AR leaves the field cut box and the look alone', JSON.parse(inAr2.section).box.enabled && inAr2.styles === inAr.styles, inAr2.section.slice(0, 60));
  const saveErr = await page.evaluate(() => { try { window.__xrayViews.save('in AR'); return null; } catch (e) { return e.message; } });
  check('saving a view during field AR is refused with a message', !!saveErr && (await page.evaluate(() => window.__xrayViews.list().length)) === 1, saveErr ?? 'saved');
  await page.keyboard.press('Control+Shift+S');
  await settle(300);
  check('Ctrl+Shift+S during field AR saves nothing and logs no error', (await page.evaluate(() => window.__xrayViews.list().length)) === 1);
  console.log('during AR after view step:', JSON.stringify({ section: inAr2.section.slice(0, 60), planes: inAr2.planes }));
  // ---- exit
  await page.evaluate(() => window.__xrayXr.exit());
  await page.waitForFunction('window.__xray.renderer.renderer.xr.isPresenting === false', null, { timeout: 30000 });
  await settle(900);
  const post = await snap();
  check('after field AR: user class styles back', post.styles === pre.styles, '');
  check('after field AR: section back to the state before (no cut box)', post.section === pre.section || !JSON.parse(post.section).box.enabled, post.section.slice(0, 120));
  check('after field AR: no clip planes left', post.planes === pre.planes, `${pre.planes} -> ${post.planes}`);
  check('after field AR: camera near/far as before', post.near === pre.near && Math.abs(post.far - pre.far) < 1e-6, `near ${pre.near}->${post.near} far ${pre.far}->${post.far}`);
  await page.screenshot({ path: `${SHOTS}/qa7-after-ar.png` });

  // ---- saved views after AR
  await page.evaluate(() => window.__xrayViews.restore('before AR (plane)', { animate: false }));
  await settle(1000);
  const v1 = await snap();
  check('after AR: restoring a saved view gives its section plane', JSON.parse(v1.section).plane.enabled && v1.planes === 1, `planes ${v1.planes}`);
  await page.evaluate(() => window.__xrayViews.save('after AR'));
  const va = await page.evaluate(() => window.__xrayViews.get('after AR'));
  check('after AR: a new view saves without field AR leftovers (no field look styles, no cut box)', !JSON.stringify(va.params).includes('0.06') && va.params.section?.box?.enabled !== true, JSON.stringify(va.params.section ?? {}).slice(0, 120));
  // ---- BCF after AR
  const bcf = await page.evaluate(() => {
    const b = window.__xrayBcf; const t = b.createTopic({ title: 'after AR' });
    window.__xraySection.clear();
    const r = b.applyViewpoint(t.guid);
    return { status: r.status, planes: window.__xray.app.renderer.getClipPlanes()?.length ?? 0, pins: 0 };
  });
  await settle(600);
  const pins = await page.evaluate(() => document.querySelectorAll('svg.xray-svg-overlay [data-bcf-pin]').length);
  check('after AR: BCF topic captures and applies (section plane back from the viewpoint)', /clipping 1/.test(bcf.status) && bcf.planes === 1, bcf.status);
  // ---- sections after AR: box fit to the model, then clear
  await page.evaluate(() => { window.__xrayBcf.clearViewpoint(); window.__xraySection.fitToModel(); });
  await settle(600);
  const sb = await snap();
  check('after AR: section box fits and cuts (6 planes)', JSON.parse(sb.section).box.enabled && sb.planes === 6, `planes ${sb.planes}`);
  await page.evaluate(() => window.__xraySection.clear());
  await settle(400);
  check('after AR: section clear removes every plane', (await snap()).planes === 0);
  await page.screenshot({ path: `${SHOTS}/qa7-after-ar-done.png` });
  check('no console errors (field AR cross)', errors.length === 0, errors.slice(0, 5).join(' | '));
  } finally { await browser.close(); }
}

async function part3() {
  const browser = await chromium.launch();
const frames = (page, n = 6) => page.evaluate(async (n) => { for (let i = 0; i < n; i++) await new Promise((r) => requestAnimationFrame(r)); }, n);
async function scene(name, vp, opts) {
  const { page, errors, ctx } = await openApp(browser, url, '?model=fzk-haus&cinematic=off', vp, opts.ctx ?? {});
  await page.evaluate(() => { localStorage.removeItem('xray.views.fzk-haus'); window.__xrayViews.save('A'); window.__xrayViews.save('B'); });
  await page.evaluate((open) => {
    const sbc = document.body.classList.contains('sb-collapsed');
    if (open && sbc) document.querySelector('.sb-toggle')?.click();
    if (!open && !sbc) document.querySelector('.sb-toggle')?.click();
    if (open) [...document.querySelectorAll('.sb-tab')].find((t) => t.textContent === 'Views')?.click();
  }, opts.sidebar);
  // The BCF drawer moved into the sidebar tab Issues (docs-features/issues.md): the scene opens that tab instead.
  if (opts.drawer === 'bcf') await page.evaluate(() => window.__xrayIssues.open('issues'));
  else if (opts.drawer) await page.evaluate((d) => window.__xrayToolbar.open(d), opts.drawer);
  await page.waitForTimeout(800);
  // chrome rects over the canvas
  const chrome = await page.evaluate(() => {
    const c = window.__xray.app.canvas.getBoundingClientRect();
    const out = {};
    for (const [k, sel] of Object.entries({ gizmo: '#xray-gizmo', status: '#xray-overlay', sidebar: '#sidebar', dock: '#dock', strip: '#xray-toolbar', drawer: '#xray-toolbar-drawer' })) {
      const e = document.querySelector(sel);
      if (!e || e.hidden || !e.getClientRects().length || getComputedStyle(e).visibility === 'hidden') continue;
      const r = e.getBoundingClientRect();
      const ix = Math.max(0, Math.min(r.right, c.right) - Math.max(r.left, c.left)), iy = Math.max(0, Math.min(r.bottom, c.bottom) - Math.max(r.top, c.top));
      if (ix > 1 && iy > 1) out[k] = { x: r.left, y: r.top, w: r.width, h: r.height };
    }
    return { canvas: { x: c.left, y: c.top, w: c.width, h: c.height }, rects: out };
  });
  console.log(name, 'chrome over canvas:', Object.keys(chrome.rects).join(', '), JSON.stringify(chrome.canvas));
  // targets: centre of each chrome rect clipped to the canvas
  const targets = Object.entries(chrome.rects).map(([k, r]) => {
    const c = chrome.canvas;
    const x0 = Math.max(r.x, c.x), x1 = Math.min(r.x + r.w, c.x + c.w), y0 = Math.max(r.y, c.y), y1 = Math.min(r.y + r.h, c.y + c.h);
    return { k, x: (x0 + x1) / 2, y: (y0 + y1) / 2 };
  });
  const made = await page.evaluate((targets) => {
    const app = window.__xray.app;
    const cr = app.canvas.getBoundingClientRect();
    const cam = app.renderer.camera; cam.updateMatrixWorld();
    const world = (x, y, z = 0.6) => cam.position.clone().set(((x - cr.left) / cr.width) * 2 - 1, -(((y - cr.top) / cr.height) * 2 - 1), z).unproject(cam);
    const right = cam.position.clone().set(1, 0, 0).applyQuaternion(cam.quaternion).multiplyScalar(0.03);
    const b = window.__xrayBcf; const m = window.__xrayMeasure;
    const topics = [];
    for (const t of targets) {
      const P = world(t.x, t.y);
      m.click([P.x - right.x, P.y - right.y, P.z - right.z], -1);
      m.click([P.x + right.x, P.y + right.y, P.z + right.z], -1);
      const top = b.createTopic({ title: `under ${t.k}` });
      b.setPin(top.guid, [P.x, P.y, P.z]);
      b.addAnnotation(top.guid, { type: 'note', text: `note ${t.k}`, anchor: { kind: 'point', point: [P.x, P.y, P.z] } });
      topics.push(top.guid);
    }
    return topics;
  }, targets);
  // pins show with the BCF drawer open, or for the applied topic: open the BCF drawer on desktop; on the phone apply the last topic
  if (opts.applyLast) await page.evaluate((g) => window.__xrayBcf.applyViewpoint(g), made[made.length - 1]);
  await frames(page, 8);
  await page.waitForTimeout(400);
  const drawn = await page.evaluate(() => {
    const box = (e) => { const r = e.getBoundingClientRect(); return { x: r.left, y: r.top, w: r.width, h: r.height }; };
    const labels = [...document.querySelectorAll('[data-measure-label]')].map((l) => l.parentElement?.querySelector('rect') ?? l).map(box);
    // pin heads and edge markers; the 5 px dot at the end of a moved pin's leader marks the true point, under the chrome by design
    const pins = [...document.querySelectorAll('svg.xray-svg-overlay [data-bcf-pin] [data-role="pin"], svg.xray-svg-overlay [data-bcf-pin] [data-role="edge"]')].map(box).filter((r) => r.w >= 10 && r.h >= 10);
    const anns = [...document.querySelectorAll('svg.xray-svg-overlay [data-bcf-ann] rect, svg.xray-svg-overlay [data-mk] rect[data-role=box]')].map(box);
    return { labels, pins, anns };
  });
  const ov = (a, b) => a.x < b.x + b.w - 0.5 && a.x + a.w > b.x + 0.5 && a.y < b.y + b.h - 0.5 && a.y + a.h > b.y + 0.5;
  const bad = [];
  for (const [kind, list] of Object.entries(drawn)) for (const r of list) {
    if (r.w === 0 || r.h === 0) continue;
    for (const [k, c] of Object.entries(chrome.rects)) if (ov(r, c)) bad.push(`${kind} ${r.x.toFixed(0)},${r.y.toFixed(0)} ${r.w.toFixed(0)}x${r.h.toFixed(0)} under ${k}`);
  }
  (opts.report ? (n, ok, d) => console.log(`INFO ${n} (${ok ? 'clear' : 'not clear'}; ${d})`) : check)(`${name}: measure labels, BCF pins and notes clear of ${Object.keys(chrome.rects).join(', ')}`, bad.length === 0 && drawn.labels.length >= targets.length, `${drawn.labels.length} labels, ${drawn.pins.length} pins, ${drawn.anns.length} notes; ${bad.slice(0, 6).join('; ')}`);
  await page.screenshot({ path: `${SHOTS}/qa7-reserved-${name}.png` });
  check(`${name}: no console errors`, errors.length === 0, errors.slice(0, 3).join(' | '));
  await ctx.close();
}  try {
  await scene('desktop-views-bcf', { width: 1600, height: 900 }, { sidebar: true, drawer: 'bcf' });
  await scene('phone-views-open', { width: 390, height: 844 }, { sidebar: true, applyLast: true, report: true, ctx: { isMobile: true, hasTouch: true, deviceScaleFactor: 2 } });
  await scene('phone-closed', { width: 390, height: 844 }, { sidebar: false, applyLast: true, ctx: { isMobile: true, hasTouch: true, deviceScaleFactor: 2 } });
  } finally { await browser.close(); }
}

const PLY = WEB + '/public/samples/building-phone-scan.ply';
const head = readFileSync(PLY).subarray(0, 600).toString('latin1');
const tm = /comment truth: viewer = Ry\(([-\d.]+) deg\) \* p \+ \(([-\d.]+), ([-\d.]+), ([-\d.]+)\)/.exec(head);
const H = +tm[1], T = [+tm[2], +tm[3], +tm[4]]; const c = Math.cos(H * Math.PI / 180), s = Math.sin(H * Math.PI / 180);
const TRUE = [c, 0, -s, 0, 0, 1, 0, 0, s, 0, c, 0, T[0], T[1], T[2], 1];
async function part4() {
  const browser = await chromium.launch();
  try {
  const { page, errors } = await openApp(browser, url, '?model=building');
  await page.evaluate(() => window.__xrayToolbar.open('pointcloud'));
  await page.setInputFiles('input[data-pointcloud="open"]', PLY);
  await page.waitForFunction(() => window.__xrayPointCloud.stats.loaded && !window.__xrayPointCloud.controller.busy, null, { timeout: 120000 });
  await page.locator('#pointcloud-drawer .xt-select', { hasText: 'coordinates' }).locator('select').selectOption('viewer');
  await page.evaluate((M) => window.__xrayPointCloud.setMatrix(M.map((v, i) => (i === 12 ? v + 0.02 : i === 14 ? v - 0.015 : v)), 'truth + 2.5 cm'), TRUE);
  // no section box yet: the option says what it needs
  await page.locator('#pointcloud-drawer .xt-select', { hasText: 'align within' }).locator('select').selectOption('section box');
  const need = await page.evaluate(() => window.__xrayPointCloud.status);
  check('align within section box without a box: the status says what it needs', /needs an active section box/.test(need), need);
  // select the elements of the scanned room (bounds near the room centre), then the gizmo box button
  const n = await page.evaluate(() => {
    const app = window.__xray.app; const els = app.controller.model.elements; const k = [0, -1.5, -1];
    const ids = els.filter((e) => { const b = e.bounds; return b && b[0] < k[0] + 2.2 && b[3] > k[0] - 2.2 && b[2] < k[2] + 1.6 && b[5] > k[2] - 1.6 && b[1] < k[1] + 1 && b[4] > k[1] - 1; }).map((e) => e.id);
    app.selectIds(ids); window.__cinematic?.cancelFlight?.(); return ids.length;
  });
  await page.waitForTimeout(800);
  await page.locator('#xray-gizmo .xg-btn[title^="Section box"]').click();
  await page.waitForTimeout(800);
  const box = await page.evaluate(() => ({ ...window.__xraySection.config.box }));
  check('gizmo box button: section box around the selected room elements', box.enabled && !!box.min, `${n} elements, box ${box.min?.map((v) => v.toFixed(2))} .. ${box.max?.map((v) => v.toFixed(2))}`);
  await page.evaluate(() => window.__xrayPointCloud.controller.noteRegion?.());
  const t0 = Date.now();
  await page.locator('#pointcloud-drawer .xt-btn[data-mode="refine"]').click();
  await page.waitForFunction(() => /in the section box/.test(window.__xrayPointCloud.status) && !window.__xrayPointCloud.controller.busy, null, { timeout: 300000 });
  const reg = await page.evaluate(() => ({ icp: window.__xrayPointCloud.stats.icp, m: window.__xrayPointCloud.matrix, status: window.__xrayPointCloud.status, grid: document.querySelector('[data-pc-regions]')?.textContent ?? '' }));
  const err = (m, at) => { const ap = (M, p) => [M[0] * p[0] + M[4] * p[1] + M[8] * p[2] + M[12], M[1] * p[0] + M[5] * p[1] + M[9] * p[2] + M[13], M[2] * p[0] + M[6] * p[1] + M[10] * p[2] + M[14]]; const a = ap(TRUE, at), b = ap(m, at); return Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]); };
  const e = err(reg.m, [0, -1.5, -1]);
  check('align within the gizmo section box: ICP fits within it and lands within 6 mm', reg.icp.region?.label === 'section box' && !reg.icp.reverted && e < 0.006, `${(e * 1000).toFixed(2)} mm, ${reg.icp.samples} samples, ${(reg.icp.ms / 1000).toFixed(1)} s (wall ${((Date.now() - t0) / 1000).toFixed(1)} s); ${reg.status.slice(0, 140)}`);
  check('drift grid shows for the region', /section box/.test(reg.grid), reg.grid.slice(0, 120));
  await page.screenshot({ path: `${SHOTS}/qa7-pc-gizmo-box.png` });
  // gizmo box button again: box off; the option then refuses
  await page.locator('#xray-gizmo .xg-btn[title^="Section box"]').click();
  await page.waitForTimeout(500);
  await page.locator('#pointcloud-drawer .xt-btn[data-mode="refine"]').click();
  await page.waitForTimeout(800);
  const st2 = await page.evaluate(() => window.__xrayPointCloud.status);
  check('box switched off by the gizmo: Refine says the box is needed', /needs an active section box/.test(st2), st2);
  check('no console errors', errors.length === 0, errors.slice(0, 3).join(' | '));
  } finally { await browser.close(); }
}

try {
  await waitForServer();
  for (const [k, fn] of [['1', part1], ['2', part2], ['3', part3], ['4', part4]]) {
    if (!want.has(k)) continue;
    console.log(`---- part ${k}`);
    try { await fn(); } catch (e) { console.error(e); check(`part ${k} ran`, false, String(e).slice(0, 200)); }
  }
} finally {
  vite.kill();
}
console.log(failed ? `${failed} check(s) failed` : 'ALL OK');
process.exit(failed ? 1 : 0);
