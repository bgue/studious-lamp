// Headless smoke test for the presets feature. Starts vite (bench/vite.smoke.config.mjs), loads
//   /?model=building  with the largest duct selected, and
//   /?model=fzk-haus  with window 22 selected (camera south-east, outside),
// at 1600x900 and applies every built-in preset: keys 1 to 9 are pressed, the rest go through window.__xrayPresets.apply.
// Records the skipped-keys list per preset (expected non-empty only for imaging and section while those plugins are not
// built), checks the Presets folder of the parameter panel, the drawer, the active mark, and that a saved user preset
// and a share link survive a reload. Screenshots: bench/preset-<id>.png (fzk-haus: coordination, hide-blockers,
// behind-only, peelback, presentation) and bench/preset-drawer.png.
// Usage: SMOKE_PORT=5342 node bench/smoke-presets.mjs
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const port = Number(process.env.SMOKE_PORT ?? 5342);

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

const SCENES = [
  {
    key: 'building',
    model: 'building',
    select: `(els) => { const ducts = els.filter((e) => e.ifcClass === 'IfcDuctSegment'); const ext = (e) => (e.bounds[3] - e.bounds[0]) + (e.bounds[5] - e.bounds[2]); return [ducts.reduce((a, b) => (ext(b) > ext(a) ? b : a)).id]; }`,
    view: null,
    shots: [],
  },
  {
    key: 'fzk-haus',
    model: 'fzk-haus',
    select: `(els) => els.filter((e) => e.ifcClass === 'IfcWindow' && e.id === 22).map((e) => e.id)`,
    view: { pos: [6, 5.5, 13], tgt: [-3.95, -1.8, -4.8] },
    shots: ['coordination', 'hide-blockers', 'behind-only', 'peelback', 'presentation'],
  },
];

const KEYED = ['coordination', 'hide-blockers', 'behind-only', 'peelback', 'peel-only', 'stacked-floors', 'radiograph', 'mri-scan', 'section-focus'];
const REST = ['presentation', 'clearance-review', 'plain'];

let browser;
let exitCode = 0;
const report = [];
try {
  await waitForServer();
  browser = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const context = await browser.newContext({ viewport: { width: 1600, height: 900 } });
  const errors = [];
  const warnings = [];
  const watch = (page, tag) => {
    page.on('console', (m) => {
      if (m.type() === 'error') errors.push(`[${tag}][error] ${m.text()}`);
      else if (m.type() === 'warning') warnings.push(`[${tag}] ${m.text()}`);
    });
    page.on('pageerror', (e) => errors.push(`[${tag}][pageerror] ${e.message}`));
  };

  for (const sc of SCENES) {
    const page = await context.newPage();
    watch(page, sc.key);
    console.log(`\n== ${sc.model}`);
    await page.goto(`http://127.0.0.1:${port}/?model=${sc.model}`);
    await page.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: 180000 });
    const startErr = await page.evaluate('window.__xrayError');
    if (startErr) throw new Error(startErr);
    await page.waitForFunction('!!window.__xrayPresets', null, { timeout: 10000 });

    const sel = await page.evaluate(([src]) => {
      const app = window.__xray.app;
      const els = app.loaded.model.elements;
      const ids = (0, eval)(src)(els);
      app.selectIds(ids);
      return ids;
    }, [sc.select]);
    check(`${sc.key}: an element is selected`, sel.length > 0, JSON.stringify(sel));

    const setView = async (v) => {
      await page.evaluate(async ([v]) => {
        const app = window.__xray.app;
        const r = app.renderer;
        const sleep = (ms) => new Promise((x) => setTimeout(x, ms));
        r.camera.position.set(...v.pos);
        r.controls.target.set(...v.tgt);
        r.camera.near = 0.1;
        r.camera.updateProjectionMatrix();
        r.controls.update();
        app.runSightlinesNow();
        for (let i = 0; i < 400 && !app.controller.converged; i++) await sleep(25);
        await sleep(200);
      }, [v]);
    };
    // Let the fly-to started by the selection finish, then fix the camera.
    await page.waitForTimeout(2500);
    if (sc.view) await setView(sc.view);
    const settle = (ms = 900) => page.evaluate(async (ms) => {
      const app = window.__xray.app;
      for (let i = 0; i < 3; i++) await new Promise((r) => requestAnimationFrame(r));
      app.runSightlinesNow();
      for (let i = 0; i < 300 && !app.controller.converged; i++) await new Promise((r) => setTimeout(r, 25));
      await new Promise((r) => setTimeout(r, ms));
      for (let i = 0; i < 2; i++) await new Promise((r) => requestAnimationFrame(r));
    }, ms);

    // The parameter panel folder and its controls.
    const gui = await page.evaluate(() => {
      const root = window.__xray.app.panel;
      const f = root.folders.find((x) => x._title === 'Presets');
      if (!f) return null;
      return { names: f.controllers.map((c) => c._name), statusDisabled: f.controllers.find((c) => c._name === 'Preset status')?._disabled === true };
    });
    check(`${sc.key}: Presets folder has the five named controls`, !!gui && JSON.stringify(gui.names) === JSON.stringify(['preset', 'Apply preset', 'Save current as preset', 'Export presets', 'Import presets', 'Preset status']), JSON.stringify(gui));
    check(`${sc.key}: Preset status is read-only`, !!gui?.statusDisabled);

    const list = await page.evaluate(() => window.__xrayPresets.list());
    check(`${sc.key}: 12 built-in presets, keys 1-9 on the first nine`, list.filter((p) => p.builtIn).length === 12 && list.slice(0, 9).every((p, i) => p.key === String(i + 1)), list.map((p) => `${p.key ?? '-'}:${p.id}`).join(' '));

    const apply = async (id, byKey) => {
      if (byKey !== undefined) {
        await page.evaluate(() => { document.activeElement?.blur?.(); });
        await page.keyboard.press(`Digit${byKey}`);
      } else {
        await page.evaluate((id) => window.__xrayPresets.apply(id), id);
      }
      await settle();
      return page.evaluate(() => ({ active: window.__xrayPresets.active(), result: window.__xrayPresets.lastResult() }));
    };

    for (const id of [...KEYED, ...REST]) {
      const i = KEYED.indexOf(id);
      const r = await apply(id, i >= 0 ? i + 1 : undefined);
      const skipped = r.result?.skipped ?? ['<no result>'];
      check(`${sc.key}: ${i >= 0 ? `key ${i + 1}` : 'API'} applies ${id}`, r.active === id && r.result?.id === id, `active=${r.active}`);
      const unexpected = skipped.filter((s) => !/^(imaging|section|action:section\.)/.test(s));
      check(`${sc.key}: ${id} skips nothing but imaging/section`, unexpected.length === 0, `skipped: ${JSON.stringify(skipped)}`);
      report.push(`${sc.key}\t${id}\t${skipped.length ? skipped.join(' ') : '-'}`);
      if (sc.shots.includes(id)) {
        await page.addStyleTag({ content: '.lil-gui, #xray-overlay, #xray-message { visibility: hidden !important }' });
        await page.screenshot({ path: resolve(here, `preset-${id}.png`), timeout: 180000 });
      }
    }

    // State checks after a few presets.
    await apply('hide-blockers', 2);
    const s2 = await page.evaluate(() => window.__xray.app.settings.sightlines);
    check(`${sc.key}: hide-blockers sets alphaMin 0, alphaMax 1, budget, farWeight 1`, s2.alphaMin === 0 && s2.alphaMax === 1 && s2.layerWeighting === 'budget' && s2.farWeight === 1);
    await apply('behind-only', 3);
    const vm3 = await page.evaluate(() => JSON.parse(JSON.stringify(window.__xrayViewModes?.config ?? null)));
    check(`${sc.key}: behind-only enables behind (cut + cap), peel off`, !!vm3 && vm3.behind.enabled && vm3.behind.frontTreatment === 'cut + cap' && !vm3.peel.enabled, JSON.stringify(vm3?.behind));
    await apply('peelback', 4);
    const vm4 = await page.evaluate(() => JSON.parse(JSON.stringify(window.__xrayViewModes?.config ?? null)));
    check(`${sc.key}: peelback switches behind off and peel on (x-ray outside)`, !!vm4 && !vm4.behind.enabled && vm4.peel.enabled && vm4.peel.outside === 'x-ray');
    await apply('plain', undefined);
    check(`${sc.key}: plain turns x-ray off and the modes off`, await page.evaluate(() => !window.__xray.app.settings.xray && !window.__xrayViewModes.config.peel.enabled));
    await apply('clearance-review', undefined);
    check(`${sc.key}: clearance-review enables the clearance colouring`, await page.evaluate(() => window.__xrayClearance.enabled === true));
    await apply('coordination', 1);
    check(`${sc.key}: coordination restores x-ray, default sightlines and switches clearance off`, await page.evaluate(() => {
      const s = window.__xray.app.settings;
      return s.xray && s.sightlines.alphaMin === 0.15 && s.sightlines.layerWeighting === 'front' && window.__xrayClearance.enabled === false;
    }));

    // The active mark clears when a setting changes.
    await page.evaluate(() => { window.__xray.app.settings.sightlines.gamma = 1.3; });
    await page.waitForTimeout(2600);
    check(`${sc.key}: the active mark clears after a setting change`, (await page.evaluate(() => window.__xrayPresets.active())) === null);
    const st = await page.evaluate(() => window.__xray.app.panel.folders.find((x) => x._title === 'Presets').controllers.find((c) => c._name === 'Preset status').getValue());
    check(`${sc.key}: Preset status reads "No preset applied" after that`, st === 'No preset applied', st);

    // The drawer.
    await page.evaluate(() => window.__xrayToolbar.open('presets'));
    await page.waitForTimeout(400);
    const drawer = await page.evaluate(() => ({
      cards: document.querySelectorAll('.xp-card').length,
      headings: [...document.querySelectorAll('.xt-drawer .xt-sec')].map((e) => e.textContent),
      applyButtons: [...document.querySelectorAll('.xp-card .xt-btn')].filter((b) => b.textContent === 'Apply').length,
      keys: [...document.querySelectorAll('.xp-key')].map((e) => e.textContent).sort().join(''),
    }));
    check(`${sc.key}: drawer shows 12 cards with keys 1-9 and Apply buttons`, drawer.cards === 12 && drawer.applyButtons === 12 && drawer.keys === '123456789', JSON.stringify(drawer));
    await page.evaluate(() => window.__xrayPresets.apply('peelback'));
    await page.waitForTimeout(300);
    check(`${sc.key}: the applied card is marked active`, (await page.evaluate(() => document.querySelector('.xp-card.on')?.getAttribute('data-preset'))) === 'peelback');
    if (sc.key === 'fzk-haus') {
      await page.addStyleTag({ content: '#xray-overlay, #xray-message { visibility: hidden !important }' });
      await page.screenshot({ path: resolve(here, 'preset-drawer.png'), timeout: 180000 });
    }
    await page.evaluate(() => window.__xrayToolbar.close());

    if (sc.key === 'building') {
      // User preset: save, reload, it persists; apply restores it. Then a share link.
      await page.evaluate(() => { window.__xrayPresets.apply('coordination'); window.__xray.app.settings.sightlines.alphaMin = 0.05; });
      const saved = await page.evaluate(() => window.__xrayPresets.save('Smoke look', ['sightlines', 'display', 'farMode', 'viewModes', 'imaging', 'section', 'cinematic'], 'Saved by the smoke test.'));
      check('user preset saved with the sections of this build', saved.preset.id === 'smoke-look' && saved.preset.params.sightlines.alphaMin === 0.05 && 'imaging' in saved.preset.params && saved.missing.length === 0, `missing: ${JSON.stringify(saved.missing)}`);
      const share = await page.evaluate(() => window.__xrayPresets.shareUrl('smoke-look'));
      await page.reload();
      await page.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: 180000 });
      await page.waitForFunction('!!window.__xrayPresets', null, { timeout: 10000 });
      const after = await page.evaluate(() => window.__xrayPresets.list().find((p) => p.id === 'smoke-look') ?? null);
      check('user preset persists across a reload', !!after && !after.builtIn && after.group === 'My presets' && after.key === null, JSON.stringify(after));
      await page.evaluate(() => window.__xrayPresets.apply('Smoke look'));
      check('applying the stored user preset restores alphaMin', await page.evaluate(() => window.__xray.app.settings.sightlines.alphaMin) === 0.05);
      // delete + export/import via the API
      const json = await page.evaluate(() => window.__xrayPresets.exportJson(false));
      check('export contains the user preset in xray-presets/1', JSON.parse(json).schema === 'xray-presets/1' && JSON.parse(json).presets.length === 1);
      await page.evaluate(() => window.__xrayPresets.remove('smoke-look'));
      const imp = await page.evaluate((j) => window.__xrayPresets.importJson(j), json);
      check('import restores it', imp.added.length === 1 && imp.errors.length === 0, JSON.stringify(imp));
      // Share link applied on load, after the model.
      await page.evaluate(() => { window.__xray.app.settings.sightlines.alphaMin = 0.15; });
      await page.goto(share);
      await page.reload();
      await page.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: 180000 });
      await page.waitForTimeout(800);
      const sh = await page.evaluate(() => ({ active: window.__xrayPresets.active(), alphaMin: window.__xray.app.settings.sightlines.alphaMin, hash: location.hash }));
      check('share link #preset= applies after the model loaded and clears the hash', sh.active === 'shared-preset' && sh.alphaMin === 0.05 && sh.hash === '', JSON.stringify(sh));
      await page.evaluate(() => { try { localStorage.removeItem('xray.presets'); } catch { /* ignore */ } });
    }
    await page.close();
  }

  console.log('\nSkipped keys per preset (model, id, skipped):');
  for (const l of report) console.log('  ' + l);
  console.log('\nConsole warnings (distinct):');
  for (const w of [...new Set(warnings)].slice(0, 12)) console.log('  ' + w.slice(0, 200));
  check('zero console errors', errors.length === 0, errors.slice(0, 5).join(' | '));
  if (checks.some((c) => !c.ok)) exitCode = 1;
} catch (e) {
  console.error('smoke-presets failed:', e);
  exitCode = 1;
} finally {
  await browser?.close();
  vite.kill();
}
console.log(exitCode === 0 ? '\nALL OK' : '\nFAILED');
process.exit(exitCode);
