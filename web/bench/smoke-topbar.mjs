// Headless smoke test for the top bar (src/ui/topBar.ts, src/plugins/topBar.ts) and the radiograph controls in the X-ray panel.
// Starts vite (bench/vite.smoke.config.mjs) and loads /?model=fzk-haus with window 22 selected at 1600x900, then checks:
//   - the bar: 32 px high, on top of #stage, the five modes (Solid first), the empty-or-mounted search host #xray-topbar-search;
//   - each mode applies its preset and is the only highlighted one; Ghost is highlighted at start (factory look);
//   - a preset applied from the drawer or the API, a restored saved view, a key and a changed setting move the highlight;
//   - a click on a lit mode switches to Solid (X-ray off, imaging standard, all opaque, sections kept); Solid lit does nothing;
//   - the radiograph controls in the X-ray panel: Render style, the imaging folder open, dimmed controls, restore on leaving;
//   - keys Shift+0..4 and Shift+T; the topBar.visible setting; hidden in a kiosk page and while a XR session runs;
//   - layout: no overlap with the gizmo, the tool strip, the drawer, the status bar; reserved on the overlay; 390x844 and 360x740 phones;
//   - no console errors.
// Screenshots: bench/topbar-*.png. Usage: SMOKE_PORT=5661 node bench/smoke-topbar.mjs
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const port = Number(process.env.SMOKE_PORT ?? 5661);

function loadPlaywright() {
  const candidates = [process.env.PLAYWRIGHT_MODULE, resolve(root, 'node_modules/playwright'), '/opt/node-tools/node_modules/playwright', '/opt/node22/lib/node_modules/playwright'].filter(Boolean);
  for (const c of candidates) {
    try { return createRequire(import.meta.url)(c); } catch { /* try next */ }
  }
  throw new Error('playwright not found; set PLAYWRIGHT_MODULE');
}
const { chromium } = loadPlaywright();

const vite = spawn(resolve(root, 'node_modules/.bin/vite'), ['--config', resolve(here, 'vite.smoke.config.mjs'), '--host', '127.0.0.1', '--port', String(port), '--strictPort'], { cwd: root, stdio: ['ignore', 'pipe', 'pipe'] });
let viteLog = '';
vite.stdout.on('data', (d) => (viteLog += d));
vite.stderr.on('data', (d) => (viteLog += d));
async function waitForServer() {
  for (let i = 0; i < 100; i++) {
    try { const r = await fetch(`http://127.0.0.1:${port}/`); if (r.ok) return; } catch { /* retry */ }
    await new Promise((r) => setTimeout(r, 200));
  }
  throw new Error('vite did not start:\n' + viteLog);
}

const checks = [];
function check(name, ok, detail = '') {
  checks.push({ name, ok });
  console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${detail ? ` (${detail})` : ''}`);
}

const MODES = [
  { id: 'solid', preset: 'solid', digit: 0 },
  { id: 'ghost', preset: 'coordination', digit: 1 },
  { id: 'radiograph', preset: 'radiograph', digit: 2 },
  { id: 'glow', preset: 'focus-glow', digit: 3 },
  { id: 'cutaway', preset: 'peel-only', digit: 4 },
];
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const shot = (page, name) => page.screenshot({ path: resolve(here, `topbar-${name}.png`), timeout: 180000 });
const overlap = (a, b) => a && b && a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;

let browser;
let exitCode = 0;
try {
  await waitForServer();
  browser = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const errors = [];
  const watch = (page, tag) => {
    page.on('console', (m) => { if (m.type() === 'error') errors.push(`[${tag}][error] ${m.text()}`); });
    page.on('pageerror', (e) => errors.push(`[${tag}][pageerror] ${e.message}`));
  };

  async function open(context, tag, query = 'model=fzk-haus', init) {
    const page = await context.newPage();
    watch(page, tag);
    if (init) await page.addInitScript(init);
    await page.goto(`http://127.0.0.1:${port}/?${query}`, { timeout: 240000 });
    await page.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: 180000 });
    const err = await page.evaluate('window.__xrayError');
    if (err) throw new Error(err);
    await page.waitForFunction('!!window.__xrayPresets && !!window.__xrayTopBar', null, { timeout: 20000 });
    return page;
  }
  const rect = (page, sel) => page.evaluate((sel) => {
    const e = document.querySelector(sel);
    if (!e || e.hidden || e.getClientRects().length === 0) return null;
    const r = e.getBoundingClientRect();
    return { x: r.left, y: r.top, w: r.width, h: r.height };
  }, sel);
  const state = (page) => page.evaluate(() => ({
    active: window.__xrayPresets.active(),
    mode: window.__xrayTopBar.active(),
    pressed: [...document.querySelectorAll('#xray-topbar .tb-mode')].filter((b) => b.getAttribute('aria-pressed') === 'true').map((b) => b.dataset.mode),
    xray: window.__xray.app.settings.xray,
    imaging: window.__xrayImaging.config.style,
    peel: window.__xrayViewModes.config.peel.enabled,
    peelOutside: window.__xrayViewModes.config.peel.outside,
    glow: { edge: window.__cinematic.cfg.edgeGlow, bloom: window.__cinematic.cfg.bloom, scope: window.__cinematic.cfg.glowScope },
  }));
  const settle = (page, ms = 1200) => page.evaluate(async (ms) => {
    for (let i = 0; i < 3; i++) await new Promise((r) => requestAnimationFrame(r));
    const app = window.__xray.app;
    app.runSightlinesNow();
    for (let i = 0; i < 300 && !app.controller.converged; i++) await new Promise((r) => setTimeout(r, 25));
    await new Promise((r) => setTimeout(r, ms));
  }, ms);
  const select = (page) => page.evaluate(() => {
    const app = window.__xray.app;
    app.selectIds(app.loaded.model.elements.filter((e) => e.ifcClass === 'IfcWindow' && e.id === 22).map((e) => e.id));
  });
  const setView = (page) => page.evaluate(async () => {
    const r = window.__xray.app.renderer;
    r.camera.position.set(6, 5.5, 13);
    r.controls.target.set(-3.95, -1.8, -4.8);
    r.camera.near = 0.1;
    r.camera.updateProjectionMatrix();
    r.controls.update();
    window.__xray.app.runSightlinesNow();
  });
  const gui = (page) => page.evaluate(() => {
    const root = window.__xray.app.panel;
    const isNa = (f) => f.domElement.classList.contains('xr-na');
    const imaging = root.folders.find((f) => f._title === 'Imaging');
    const render = root.controllers.find((c) => c.property === 'style' || c._name === 'Render style');
    const visible = (e) => !!e && e.getClientRects().length > 0;
    const find = (f, name) => f.controllers.find((c) => c._name === name);
    return {
      renderStyle: render ? render.getValue() : null,
      renderVisible: visible(render?.domElement),
      imagingOpen: imaging ? !imaging._closed : null,
      imagingControlsVisible: imaging ? ['palette', 'auto exposure', 'exposure', 'bone glow'].map((n) => visible(find(imaging, n)?.domElement)) : [],
      na: root.folders.filter(isNa).map((f) => f._title),
      dim: root.folders.filter((f) => f.domElement.classList.contains('xr-dim')).map((f) => f._title),
      labels: Object.fromEntries(root.folders.filter(isNa).map((f) => [f._title, f.$title.getAttribute('data-na')])),
      displayDimmed: (root.folders.find((f) => f._title === 'Display')?.controllers ?? []).filter((c) => c.domElement.classList.contains('xr-na')).map((c) => c.property),
      tiersNa: root.controllers.find((c) => c.property === 'tiersMode')?.domElement.classList.contains('xr-na') ?? false,
      note: document.querySelector('.xr-style-note')?.textContent ?? '',
      noteVisible: visible(document.querySelector('.xr-style-note')),
      // order in the panel: Render style comes before the Imaging folder, before Classification
      order: [...root.$children.children].map((e) => e.querySelector?.('.lil-title')?.textContent?.trim() ?? e.querySelector?.('.lil-name')?.textContent?.trim() ?? '').filter(Boolean).slice(0, 12),
    };
  });

  // ============================================================== desktop
  const desktop = await browser.newContext({ viewport: { width: 1600, height: 900 } });
  let page = await open(desktop, 'desktop');
  console.log('\n== desktop 1600x900, fzk-haus');

  // --- the bar itself
  await sleep(2500); // the factory look is marked after 1.5 s
  const bar = await rect(page, '#xray-topbar');
  const stage = await rect(page, '#stage');
  check('bar is 32 px high and sits at the top of the stage', !!bar && Math.abs(bar.h - 32) < 1 && Math.abs(bar.y - stage.y) < 1 && Math.abs(bar.w - stage.w) < 2, JSON.stringify({ bar, stage }));
  const labels = await page.evaluate(() => [...document.querySelectorAll('#xray-topbar .tb-mode')].map((b) => [b.dataset.mode, b.textContent.trim(), b.getAttribute('aria-label')]));
  check('five modes in order Solid, Ghost, Radiograph, Glow, Cutaway with accessible names', JSON.stringify(labels.map((l) => l[1])) === JSON.stringify(['Solid', 'Ghost', 'Radiograph', 'Glow', 'Cutaway']) && labels.every((l) => /\(Shift\+\d\)$/.test(l[2])), JSON.stringify(labels));
  const host = await page.evaluate(() => { const h = document.getElementById('xray-topbar-search'); return h ? { w: h.getBoundingClientRect().width, h: h.getBoundingClientRect().height, parentIsBar: h.parentElement.id === 'xray-topbar' } : null; });
  check('search host #xray-topbar-search exists, in the bar, with the flexible width', !!host && host.parentIsBar && host.w > 300 && host.h > 20, JSON.stringify(host));
  const s0 = await state(page);
  check('Ghost is highlighted at start (the factory look)', s0.mode === 'ghost' && JSON.stringify(s0.pressed) === '["ghost"]' && s0.xray === true, JSON.stringify(s0));
  await shot(page, 'start');

  await select(page);
  await page.waitForTimeout(2500);
  await setView(page);
  await settle(page);

  // --- each mode applies and highlights
  let s;
  // Ghost is the highlighted mode at start, so a click on it switches to Solid: it goes last (and first as the "again" case below).
  await page.click('#xray-topbar .tb-mode[data-mode=ghost]');
  await settle(page, 1200);
  s = await state(page);
  check('clicking Ghost while it is highlighted (the factory look) switches to Solid: X-ray off', s.xray === false && s.mode === 'solid', JSON.stringify(s));
  for (const m of [MODES[2], MODES[3], MODES[4], MODES[1]]) {
    await page.click(`#xray-topbar .tb-mode[data-mode=${m.id}]`);
    await settle(page, 1800);
    s = await state(page);
    const ok = s.active === m.preset && s.mode === m.id && JSON.stringify(s.pressed) === JSON.stringify([m.id]);
    check(`click ${m.id}: preset ${m.preset} applied and the only highlighted mode`, ok, JSON.stringify(s));
    if (m.id === 'radiograph') check('radiograph: imaging style radiograph, x-ray on', s.imaging === 'radiograph' && s.xray);
    if (m.id === 'glow') check('glow: edge glow on, scope focus, bloom on, imaging standard', s.glow.edge && s.glow.bloom && s.glow.scope === 'focus' && s.imaging === 'standard', JSON.stringify(s.glow));
    if (m.id === 'cutaway') check('cutaway: peel window on, outside solid, imaging standard', s.peel && s.peelOutside === 'solid' && s.imaging === 'standard');
    if (m.id === 'solid') check('solid: x-ray off, no peel, imaging standard, glow off', !s.xray && !s.peel && s.imaging === 'standard' && !s.glow.edge && !s.glow.bloom, JSON.stringify(s));
    if (m.id === 'ghost') check('ghost: x-ray on, no peel, imaging standard, glow off', s.xray && !s.peel && s.imaging === 'standard' && !s.glow.edge && !s.glow.bloom);
    if (m.id !== 'glow') check(`${m.id}: the glow of the previous mode is switched off`, !s.glow.edge && !s.glow.bloom, JSON.stringify(s.glow));
    const aria = await page.evaluate((id) => document.querySelector(`#xray-topbar .tb-mode[data-mode=${id}]`).getAttribute('aria-pressed'), m.id);
    check(`${m.id}: aria-pressed is true`, aria === 'true');
    if (m.id === 'cutaway') { await setView(page); await settle(page, 1500); }
    await shot(page, m.id);
  }

  // --- the highlight follows presets, saved views, keys and changed settings
  await page.evaluate(() => window.__xrayPresets.apply('hide-blockers'));
  await sleep(500);
  s = await state(page);
  check('a preset without a mode (hide-blockers) clears the highlight', s.mode === null && s.pressed.length === 0, JSON.stringify(s));

  await page.evaluate(() => window.__xrayToolbar.open('presets'));
  await sleep(500);
  await page.evaluate(() => [...document.querySelectorAll('.xp-card[data-preset=radiograph] button')].find((b) => /apply/i.test(b.textContent))?.click());
  await sleep(500);
  s = await state(page);
  check('applying Radiograph from the presets drawer highlights Radiograph', s.mode === 'radiograph' && s.active === 'radiograph', JSON.stringify(s));
  await page.evaluate(() => [...document.querySelectorAll('.xp-card[data-preset=focus-glow] button')].find((b) => /apply/i.test(b.textContent))?.click());
  await sleep(500);
  s = await state(page);
  check('applying Focus glow from the drawer highlights Glow', s.mode === 'glow', JSON.stringify(s));
  await page.evaluate(() => window.__xrayToolbar.close());

  // key 1 (preset coordination) and key 7 (preset radiograph) are modes too
  await page.evaluate(() => document.activeElement?.blur?.());
  await page.keyboard.press('Digit7');
  await sleep(500);
  s = await state(page);
  check('key 7 (Radiograph preset) highlights Radiograph', s.mode === 'radiograph', JSON.stringify(s));

  // saved view: taken under Cutaway, restored later under another look
  await page.click('#xray-topbar .tb-mode[data-mode=cutaway]');
  await settle(page, 1500);
  const viewId = await page.evaluate(() => window.__xrayViews.save('topbar cutaway').id);
  await page.click('#xray-topbar .tb-mode[data-mode=ghost]');
  await settle(page, 1200);
  s = await state(page);
  check('before the restore Ghost is highlighted', s.mode === 'ghost');
  await page.evaluate((id) => window.__xrayViews.restore(id, { animate: false }), viewId);
  await settle(page, 600);
  s = await state(page);
  check('restoring a saved view taken under Cutaway highlights Cutaway', s.mode === 'cutaway' && s.peel, JSON.stringify(s));

  // drift: a changed setting clears the highlight
  await page.evaluate(() => { window.__xray.app.settings.sightlines.alphaMin = 0.31; });
  await sleep(1700);
  s = await state(page);
  check('a changed setting (alphaMin) clears the highlight', s.mode === null && s.pressed.length === 0, JSON.stringify(s));
  await page.evaluate(() => { window.__xray.app.settings.sightlines.alphaMin = 0.15; });

  // --- keys
  await page.evaluate(() => document.activeElement?.blur?.());
  for (const m of MODES) {
    await page.keyboard.press(`Shift+Digit${m.digit}`);
    await settle(page, 1200);
    s = await state(page);
    check(`key Shift+${m.digit} applies ${m.id}`, s.mode === m.id && s.active === m.preset, JSON.stringify(s));
  }
  check('Shift+4 did not also apply preset 4 (peelback)', (await state(page)).active === 'peel-only');

  // --- clicking the active mode turns X-ray off
  await page.click('#xray-topbar .tb-mode[data-mode=radiograph]');
  await settle(page, 1200);
  await page.click('#xray-topbar .tb-mode[data-mode=radiograph]');
  await settle(page, 1200);
  s = await state(page);
  check('clicking the lit mode again switches to Solid: X-ray off, imaging standard, Solid lit', s.xray === false && s.imaging === 'standard' && s.mode === 'solid' && JSON.stringify(s.pressed) === '["solid"]', JSON.stringify(s));
  const status = await page.evaluate(() => document.querySelector('#xray-overlay')?.textContent ?? '');
  check('status bar says x-ray off', /x-ray off/.test(status), status.slice(0, 80));
  await shot(page, 'off');
  for (const m of MODES.filter((x) => x.id !== 'radiograph' && x.id !== 'solid')) {
    await page.click(`#xray-topbar .tb-mode[data-mode=${m.id}]`);
    await settle(page, 1000);
    await page.click(`#xray-topbar .tb-mode[data-mode=${m.id}]`);
    await settle(page, 800);
    s = await state(page);
    check(`${m.id} twice: Solid`, s.xray === false && s.mode === 'solid' && !s.peel && !s.glow.edge && s.imaging === 'standard', JSON.stringify(s));
  }

  // --- Solid: opaque everything, sections kept, Shift+0, undo in one step, solid screenshot
  await page.evaluate(() => document.activeElement?.blur?.());
  await page.click('#xray-topbar .tb-mode[data-mode=glow]');
  await settle(page, 1200);
  await page.evaluate(() => { window.__xraySection.set({ box: { enabled: true, fit: 'model', margin: 3 } }); });
  await page.evaluate(() => window.__xrayUndo.clear());
  await page.keyboard.press('Shift+Digit0');
  await settle(page, 1500);
  s = await state(page);
  check('Shift+0 applies Solid and lights it', s.mode === 'solid' && s.active === 'solid' && s.xray === false && JSON.stringify(s.pressed) === '["solid"]', JSON.stringify(s));
  const SOL = await page.evaluate(() => {
    const app = window.__xray.app;
    const c = app.controller;
    const low = [];
    app.loaded.model.elements.forEach((e, i) => {
      const capped = (c.styleIndex?.[i]?.alphaMax ?? 1) < 1; // a class style (or alias) cap is the project's own look, like glass
      if ((c.state.alpha[i] ?? 1) < 0.999 && !capped && !/Window|Glass|Curtain/i.test(e.ifcClass)) low.push(`${e.ifcClass}#${i}`);
    });
    return { box: window.__xraySection.config.box.enabled, low: low.slice(0, 5), lowN: low.length, undo: window.__xrayUndo.list().undo.map((u) => u.label) };
  });
  check('Solid: no element below opacity 1 (apart from class-capped glass)', SOL.lowN === 0, JSON.stringify(SOL.low));
  check('Solid: the section box stays on', SOL.box === true);
  check('Solid applied in one undo entry', SOL.undo.length === 1, JSON.stringify(SOL.undo));
  await page.evaluate(() => window.__xrayUndo.undo());
  await sleep(600);
  s = await state(page);
  check('undo reverts Solid in one step (Glow state back, x-ray on)', s.xray === true, JSON.stringify(s));
  await page.click('#xray-topbar .tb-mode[data-mode=solid]');
  await settle(page, 1500);
  s = await state(page);
  check('clicking Solid lights it', s.mode === 'solid' && JSON.stringify(s.pressed) === '["solid"]');
  await page.click('#xray-topbar .tb-mode[data-mode=solid]');
  await settle(page, 600);
  s = await state(page);
  check('clicking lit Solid does nothing', s.mode === 'solid' && s.active === 'solid' && s.xray === false);
  await shot(page, 'solid');


  // --- radiograph in the X-ray panel
  await page.click('#xray-topbar .tb-mode[data-mode=ghost]');
  await settle(page, 1000);
  let g = await gui(page);
  check('standard: Render style = standard, imaging folder closed, nothing dimmed, no note', g.renderStyle === 'standard' && g.imagingOpen === false && g.na.length === 0 && !g.tiersNa && !g.noteVisible, JSON.stringify(g));
  await page.click('#xray-topbar .tb-mode[data-mode=radiograph]');
  await settle(page, 1500);
  g = await gui(page);
  check('radiograph: Render style shows radiograph at the top of the X-ray panel', g.renderStyle === 'radiograph' && g.renderVisible, JSON.stringify(g.order));
  check('radiograph: the Imaging folder opens with palette, auto exposure, exposure and bone glow visible', g.imagingOpen === true && g.imagingControlsVisible.length === 4 && g.imagingControlsVisible.every(Boolean), JSON.stringify(g.imagingControlsVisible));
  check('radiograph: Render style sits before the Imaging folder and before Classification', g.order.indexOf('Render style') >= 0 && g.order.indexOf('Render style') < g.order.indexOf('Imaging') && g.order.indexOf('Imaging') < g.order.indexOf('Classification (Alg 1)'), JSON.stringify(g.order));
  check('radiograph: Sightlines, Overrides and Tiers mode are dimmed and labelled as not used', ['Sightlines (Alg 2)', 'Overrides (Alg 7)'].every((t) => g.dim.includes(t) && /not used in radiograph/.test(g.labels[t])) && g.tiersNa, JSON.stringify({ dim: g.dim, labels: g.labels }));
  check('radiograph: Display and Class styles are labelled; in Display only far mode stays live', g.na.includes('Display') && g.na.includes('Class styles') && g.displayDimmed.length === 4 && !g.displayDimmed.includes('farMode'), JSON.stringify({ labels: g.labels, displayDimmed: g.displayDimmed }));
  check('radiograph: an explanation is shown', g.noteVisible && /Radiograph draws/.test(g.note) && /Hide, section and view modes still apply/.test(g.note), g.note);
  const paused0 = await page.evaluate(() => window.__xrayImaging.status().frames);
  await shot(page, 'radiograph-panel');
  // the control in the panel works both ways
  await page.evaluate(() => {
    const c = window.__xray.app.panel.controllers.find((x) => x._name === 'Render style');
    c.setValue('mri');
  });
  await sleep(300);
  check('Render style = mri sets the imaging style (and the note names the MRI slice)', (await page.evaluate(() => window.__xrayImaging.config.style)) === 'mri' && /MRI slice draws/.test((await gui(page)).note));
  await page.evaluate(() => window.__xrayImaging.set({ style: 'radiograph' }));
  await sleep(300);
  check('imaging.set from a script moves Render style back to radiograph', (await gui(page)).renderStyle === 'radiograph');
  // X-ray off pauses the imaging frame; the style stays; the note says so; X back brings it back
  await page.evaluate(() => window.__xray.app.setXray(false));
  await settle(page, 600);
  const f1 = await page.evaluate(() => window.__xrayImaging.status());
  await sleep(600);
  const f2 = await page.evaluate(() => window.__xrayImaging.status());
  g = await gui(page);
  check('x-ray off with radiograph: imaging paused (no imaging frames), style kept, panel says so', f2.frames === f1.frames && /paused/.test(f2.status) && g.renderStyle === 'radiograph' && /X-ray is off/.test(g.note) && g.na.length === 0, JSON.stringify({ f1: f1.frames, f2: f2.frames, status: f2.status, note: g.note }));
  await page.evaluate(() => window.__xray.app.setXray(true));
  await settle(page, 800);
  const f3 = await page.evaluate(() => window.__xrayImaging.status().frames);
  check('x-ray on again: the radiograph is drawn again', f3 > f2.frames, `${f2.frames} -> ${f3}`);
  // key M with x-ray off switches X-ray on with the look
  await page.evaluate(() => { window.__xrayImaging.set({ style: 'standard' }); window.__xray.app.setXray(false); });
  await page.evaluate(() => document.activeElement?.blur?.());
  await page.keyboard.press('m');
  await sleep(500);
  s = await state(page);
  check('key M with x-ray off: radiograph and x-ray on', s.imaging === 'radiograph' && s.xray === true, JSON.stringify(s));
  // leaving radiograph restores the panel
  await page.click('#xray-topbar .tb-mode[data-mode=glow]');
  await settle(page, 1200);
  g = await gui(page);
  s = await state(page);
  check('switching to Glow: Render style standard, imaging folder closed, dimmed marks gone, note hidden', s.imaging === 'standard' && g.renderStyle === 'standard' && g.imagingOpen === false && g.na.length === 0 && !g.tiersNa && !g.noteVisible, JSON.stringify(g));
  // a preset from the drawer shows in the panel too
  await page.evaluate(() => window.__xrayPresets.apply('radiograph'));
  await sleep(500);
  g = await gui(page);
  check('applying the radiograph preset shows in the X-ray panel (Render style, open folder, note)', g.renderStyle === 'radiograph' && g.imagingOpen === true && g.noteVisible);

  // --- setting topBar.visible, key Shift+T
  await page.evaluate(() => document.activeElement?.blur?.());
  await page.keyboard.press('Shift+t');
  await sleep(500);
  check('Shift+T hides the bar', (await rect(page, '#xray-topbar')) === null && (await page.evaluate(() => window.__xrayTopBar.visible() === false)));
  const strip0 = await rect(page, '.xt-strip');
  check('with the bar hidden the tool strip starts at the top', !!strip0 && strip0.y <= stage.y + 1, JSON.stringify(strip0));
  await page.keyboard.press('Shift+t');
  await sleep(500);
  check('Shift+T shows it again', (await rect(page, '#xray-topbar')) !== null);
  await page.evaluate(() => {
    const f = window.__xray.app.panel.folders.find((x) => x._title === 'Top bar');
    f.controllers[0].setValue(false);
  });
  await sleep(400);
  check('the Top bar folder switch hides the bar (params topBar.visible)', (await rect(page, '#xray-topbar')) === null);
  const doc = await page.evaluate(async () => { const m = await import('/src/ui/params.ts'); return m.collectParams(window.__xray.app).topBar; });
  check('collected params carry topBar.visible = false', doc && doc.visible === false, JSON.stringify(doc));
  await page.evaluate(() => window.__xrayTopBar.setVisible(true));
  await sleep(300);
  // XR session stand-in: the plugin reads window.__xrayXr.manager.active
  await page.evaluate(() => { window.__xrayXrBackup = window.__xrayXr; window.__xrayXr = { manager: { active: true } }; });
  await sleep(500);
  check('the bar is hidden while a XR session runs', (await rect(page, '#xray-topbar')) === null);
  await page.evaluate(() => { window.__xrayXr = window.__xrayXrBackup; });
  await sleep(500);
  check('the bar is back after the XR session', (await rect(page, '#xray-topbar')) !== null);

  // --- layout on desktop: nothing under the bar
  await page.evaluate(() => window.__xrayToolbar.open('presets'));
  await sleep(600);
  await setView(page);
  await settle(page, 600);
  const L = {
    bar: await rect(page, '#xray-topbar'),
    strip: await rect(page, '.xt-strip'),
    drawer: await rect(page, '.xt-drawer'),
    gizmo: await rect(page, '#xray-gizmo'),
    status: await rect(page, '#xray-overlay'),
    sidebar: await rect(page, '#sidebar'),
    dock: await rect(page, '#dock'),
  };
  const barBottom = L.bar.y + L.bar.h;
  check('tool strip and drawer start below the bar', L.strip.y >= barBottom - 0.5 && L.drawer.y >= barBottom - 0.5, JSON.stringify({ barBottom, strip: L.strip.y, drawer: L.drawer.y }));
  check('gizmo clear of the bar, the drawer and the status bar', !overlap(L.gizmo, L.bar) && !overlap(L.gizmo, L.drawer) && !overlap(L.gizmo, L.status), JSON.stringify(L.gizmo));
  check('bar clear of the status bar; sidebar and dock beside the stage (not under the bar)', !overlap(L.bar, L.status) && L.sidebar.x + L.sidebar.w <= L.bar.x + 1 && L.dock.x >= L.bar.x + L.bar.w - 1, JSON.stringify({ sb: L.sidebar.x + L.sidebar.w, bar: L.bar.x, dock: L.dock.x, barEnd: L.bar.x + L.bar.w }));
  const ov = await page.evaluate(async () => {
    const m = await import('/src/ui/overlay.ts');
    const o = m.getOverlay(window.__xray.app);
    o.update();
    const bar = document.getElementById('xray-topbar').getBoundingClientRect();
    const c = window.__xray.app.canvas.getBoundingClientRect();
    const hit = o.reserved.some((r) => Math.abs(r.y - (bar.top - c.top)) < 1 && r.h >= 31 && r.w >= bar.width - 2);
    const spot = o.place(200, 10, 80, 18);
    return { hit, top: o.insets.top, spot };
  });
  check('the bar is a reserved area on the overlay: top inset 32, labels placed below it', ov.hit && Math.abs(ov.top - 32) < 1.5 && ov.spot && ov.spot.y - 9 >= 32, JSON.stringify(ov));
  await shot(page, 'desktop-drawer');
  await page.evaluate(() => window.__xrayToolbar.close());
  await page.close();

  // ============================================================== kiosk page
  const kioskInit = 'window.__xrayBoot = { kiosk: true };';
  page = await open(desktop, 'kiosk', 'model=fzk-haus', kioskInit);
  await sleep(800);
  check('a kiosk page has no top bar, and the strip starts at the top', (await rect(page, '#xray-topbar')) === null && ((await rect(page, '.xt-strip'))?.y ?? 99) <= 1);
  await shot(page, 'kiosk');
  await page.close();
  page = await open(desktop, 'no-topbar', 'model=fzk-haus', 'window.__xrayBoot = { topBar: false };');
  await sleep(800);
  check('boot topBar:false (xray-pack --no-topbar) hides the bar', (await rect(page, '#xray-topbar')) === null);
  await page.close();

  await desktop.close();

  // ============================================================== phone 390x844
  const phone = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true });
  page = await open(phone, 'phone');
  console.log('\n== phone 390x844');
  await sleep(1500);
  await select(page);
  await page.waitForTimeout(2000);
  const P = await page.evaluate(() => {
    const r = (e) => { if (!e) return null; const b = e.getBoundingClientRect(); return { x: b.left, y: b.top, w: b.width, h: b.height }; };
    const btns = [...document.querySelectorAll('#xray-topbar .tb-mode')];
    return {
      bar: r(document.getElementById('xray-topbar')),
      host: r(document.getElementById('xray-topbar-search')),
      buttons: btns.map((b) => ({ ...r(b), label: b.getAttribute('aria-label'), mode: b.dataset.mode, text: r(b.querySelector('.tb-label')), pressed: b.getAttribute('aria-pressed') })),
      scrollW: document.documentElement.scrollWidth,
      sidebar: r(document.getElementById('sidebar')),
      dock: r(document.getElementById('dock')),
      strip: r(document.querySelector('.xt-strip')),
      gizmo: r(document.getElementById('xray-gizmo')),
      status: r(document.getElementById('xray-overlay')),
    };
  });
  check('phone: bar spans the width, 32 px high', !!P.bar && Math.abs(P.bar.w - 390) < 1 && Math.abs(P.bar.h - 32) < 1 && P.bar.y === 0, JSON.stringify(P.bar));
  check('phone 390: five icon-only buttons with accessible labels', P.buttons.length === 5 && P.buttons.every((b) => b.w <= 36 && b.text.w <= 2 && /\(Shift\+\d\)$/.test(b.label)), JSON.stringify(P.buttons.map((b) => [b.mode, Math.round(b.w), b.label])));
  check('phone: the search host shrinks but stays (at least 60 px) and the bar does not overflow', !!P.host && P.host.w >= 60 && P.host.w < 300 && P.host.x + P.host.w <= 390 + 0.5 && P.scrollW <= 390, JSON.stringify({ host: P.host, scrollW: P.scrollW }));
  check('phone: the rails of the sidebar and the dock start below the bar', P.sidebar.y >= 32 - 0.5 && P.dock.y >= 32 - 0.5 && P.strip.y >= 32 - 0.5, JSON.stringify({ sb: P.sidebar.y, dock: P.dock.y, strip: P.strip.y }));
  check('phone: gizmo clear of the bar and the status bar', !overlap(P.gizmo, P.bar) && !overlap(P.gizmo, P.status), JSON.stringify(P.gizmo));
  await page.tap('#xray-topbar .tb-mode[data-mode=radiograph]');
  await settle(page, 1500);
  s = await state(page);
  check('phone: tapping Radiograph applies it and highlights it', s.mode === 'radiograph' && s.imaging === 'radiograph', JSON.stringify(s));
  await shot(page, 'phone-radiograph');
  await page.evaluate(() => window.__xrayToolbar.open('presets'));
  await sleep(700);
  const PD = await page.evaluate(() => {
    const r = (e) => { if (!e) return null; const b = e.getBoundingClientRect(); return { x: b.left, y: b.top, w: b.width, h: b.height }; };
    return { drawer: r(document.querySelector('.xt-drawer')), bar: r(document.getElementById('xray-topbar')), gizmo: r(document.getElementById('xray-gizmo')) };
  });
  check('phone: the open drawer starts below the bar', !!PD.drawer && PD.drawer.y >= 32 - 0.5, JSON.stringify(PD.drawer));
  await shot(page, 'phone-drawer');
  await page.evaluate(() => window.__xrayToolbar.close());
  // the dock opened on the phone starts below the bar too
  await page.evaluate(() => document.querySelector('#dock .dk-toggle')?.click());
  // The dock opens with a width transition; it only advances on rendered frames, and a software-rendered frame of the model can
  // take longer than a fixed sleep (the check read 28 px or 58 px mid-way). Wait for the open width instead of a time.
  await page.waitForFunction(() => document.getElementById('dock').getBoundingClientRect().width > 100, null, { timeout: 15000 }).catch(() => undefined);
  const DK = await page.evaluate(() => { const b = document.getElementById('dock').getBoundingClientRect(); const t = document.getElementById('xray-topbar').getBoundingClientRect(); return { dockTop: b.top, dockW: b.width, barBottom: t.bottom }; });
  check('phone: the open dock starts below the bar', DK.dockTop >= DK.barBottom - 0.5 && DK.dockW > 100, JSON.stringify(DK));
  await shot(page, 'phone-dock');
  await page.close();
  await phone.close();

  // 360 px phone: five modes plus the search host still fit
  const small = await browser.newContext({ viewport: { width: 360, height: 740 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true });
  page = await open(small, 'phone360');
  console.log('\n== phone 360x740');
  await sleep(1500);
  const Q = await page.evaluate(() => {
    const r = (e) => { if (!e) return null; const b = e.getBoundingClientRect(); return { x: b.left, y: b.top, w: b.width, h: b.height }; };
    return { bar: r(document.getElementById('xray-topbar')), host: r(document.getElementById('xray-topbar-search')), buttons: [...document.querySelectorAll('#xray-topbar .tb-mode')].map((b) => ({ ...r(b), label: b.getAttribute('aria-label') })), scrollW: document.documentElement.scrollWidth };
  });
  check('phone 360: five 30 px buttons with names, search host >= 60 px, no overflow', Q.buttons.length === 5 && Q.buttons.every((b) => Math.abs(b.w - 30) < 1.5 && b.label) && Q.host.w >= 60 && Q.host.x + Q.host.w <= 360.5 && Q.scrollW <= 360, JSON.stringify({ host: Q.host, scrollW: Q.scrollW, w: Q.buttons.map((b) => b.w) }));
  await page.click('#xray-topbar .tb-mode[data-mode=solid]');
  await sleep(500);
  check('phone 360: tapping Solid lights it', (await state(page)).mode === 'solid');
  await shot(page, 'phone-360');
  await page.close();
  await small.close();

  // ============================================================== console
  check('no console errors or page errors', errors.length === 0, errors.slice(0, 4).join(' | '));
  for (const e of errors.slice(0, 10)) console.log('  ' + e.slice(0, 300));
} catch (e) {
  console.error(e);
  exitCode = 1;
} finally {
  await browser?.close();
  vite.kill();
}
const failed = checks.filter((c) => !c.ok);
console.log(`\n${checks.length - failed.length}/${checks.length} checks passed`);
if (failed.length) {
  console.log('FAILED:\n' + failed.map((c) => '  ' + c.name).join('\n'));
  exitCode = 1;
}
process.exit(exitCode);
