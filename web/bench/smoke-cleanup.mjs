// Headless check for model cleanup: for building, fzk-haus and synth5k run analyse with defaults, print per-rule
// counts and the floating matches, preview (screenshot bench/cleanup-preview-<model>.png for building and fzk-haus),
// hide, assert the elements are hidden in the controller and the sidebar, restore, assert visible, and assert no
// console errors. Usage: SMOKE_PORT=5313 node bench/smoke-cleanup.mjs [model ...]
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const port = Number(process.env.SMOKE_PORT ?? 5313);
const models = process.argv.slice(2).length ? process.argv.slice(2) : ['building', 'fzk-haus', 'synth5k'];

function loadPlaywright() {
  const candidates = [process.env.PLAYWRIGHT_MODULE, resolve(root, 'node_modules/playwright'), '/opt/node-tools/node_modules/playwright', '/opt/node22/lib/node_modules/playwright'].filter(Boolean);
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
  for (let i = 0; i < 100; i++) {
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

let browser;
try {
  await waitForServer();
  browser = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const PROFILES = {
    defaults: null,
    // Aggressive: bigger floating threshold with clusters, tiny up to 0.3 m, and every class group.
    aggressive: { floating: { threshold: 1, mode: 'small clusters', contactTolerance: 0.02 }, tiny: { maxSize: 0.3 }, classes: { proxies: true, furniture: true, accessories: true } },
    // Stress: forces matches on every model so hide, sidebar and restore are exercised with real ids.
    stress: { tiny: { maxSize: 1.2 }, strays: { factor: 1.5 } },
  };
  for (const [model, profile] of models.flatMap((m) => Object.keys(PROFILES).map((p) => [m, p]))) {
    console.log(`\n=== ${model} / ${profile} ===`);
    const page = await browser.newPage({ viewport: { width: 1600, height: 900 } });
    const errors = [];
    page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
    page.on('pageerror', (e) => errors.push(`[pageerror] ${e.message}`));
    await page.goto(`http://127.0.0.1:${port}/?model=${model}`);
    await page.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: 180000 });
    const err = await page.evaluate('window.__xrayError');
    if (err) errors.push(err);
    await page.evaluate(() => localStorage.clear());
    if (PROFILES[profile]) await page.evaluate((p) => window.__xrayCleanup.setRules(p), PROFILES[profile]);

    const rep = await page.evaluate(() => {
      const r = window.__xrayCleanup.analyse();
      return { counts: r.counts, total: r.total, ms: r.analysisMs, summary: r.summary, n: window.__xray.app.loaded.model.elements.length,
        matches: r.matches.map((m) => ({ id: m.id, cls: m.ifcClass, name: m.name, rules: m.rules, reason: m.reasons.join(' | ') })) };
    });
    console.log(`elements ${rep.n}, analysis ${rep.ms.toFixed(0)} ms: ${rep.summary}; ${rep.total} ids`);
    const byRule = {};
    for (const m of rep.matches) for (const r of m.rules) (byRule[r] ??= []).push(m);
    for (const [rule, list] of Object.entries(byRule)) {
      console.log(`  ${rule}: ${list.length}`);
      for (const m of list.slice(0, 40)) console.log(`    #${m.id} ${m.cls} "${m.name ?? ''}"  ${m.reason}`);
      if (list.length > 40) console.log(`    ... ${list.length - 40} more`);
    }
    const countsByClass = {};
    for (const m of rep.matches) countsByClass[m.cls] = (countsByClass[m.cls] ?? 0) + 1;
    console.log('  by class:', JSON.stringify(countsByClass));

    // Preview.
    await page.evaluate(() => window.__xrayCleanup.preview());
    await page.waitForTimeout(800);
    if (model !== 'synth5k' && profile === 'aggressive') {
      const out = resolve(here, `cleanup-preview-${model}.png`);
      // Matches inside walls are hidden behind opaque neighbours: select them (focus draws them in front) for the picture.
      await page.evaluate((ids) => window.__xray.app.selectIds(ids), rep.matches.map((m) => m.id));
      await page.waitForTimeout(1500);
      await page.screenshot({ path: out });
      await page.evaluate(() => window.__xray.app.clearSelection());
      console.log('  screenshot', out);
    }
    const tinted = await page.evaluate((ids) => {
      const c = window.__xray.renderer.state.color;
      return ids.filter((id) => Math.abs(c[id * 3] - 1) < 1e-6 && Math.abs(c[id * 3 + 1] - 0.1) < 1e-6).length;
    }, rep.matches.map((m) => m.id));
    check('preview tints every match', tinted === rep.total, `${tinted}/${rep.total}`);

    // Hide.
    const hid = await page.evaluate(() => {
      window.__xrayCleanup.hide();
      const app = window.__xray.app;
      return { hides: app.controller.settings.overrides.userHides.size, flagged: [...app.controller.settings.overrides.userHides].filter((id) => (app.renderer.state.flags[id] & 2) !== 0).length };
    });
    check('hide fills userHides and flags every id hidden', hid.hides === rep.total && hid.flagged === rep.total, JSON.stringify(hid));
    const tintGone = await page.evaluate((ids) => {
      const c = window.__xray.renderer.state.color;
      return ids.filter((id) => Math.abs(c[id * 3 + 1] - 0.1) < 1e-6 && Math.abs(c[id * 3] - 1) < 1e-6).length;
    }, rep.matches.map((m) => m.id));
    check('preview tint cleared by hide', tintGone === 0, `${tintGone} still tinted`);

    if (rep.total > 0) {
      const first = rep.matches[0];
      const gid = await page.evaluate((id) => window.__xray.app.loaded.model.elements[id].globalId, first.id);
      await page.waitForTimeout(500);
      const filter = page.locator('input[type=search]').first();
      await filter.fill(gid);
      await page.waitForTimeout(700);
      const hiddenRows = await page.locator('.tr.k-element.hid').count();
      check('sidebar shows the first match as hidden', hiddenRows >= 1, `${hiddenRows} hidden rows for ${gid}`);
      await filter.fill('');
      await page.waitForTimeout(400);
      const partial = await page.locator('.tr .eye.part, .tr .eye.off').count();
      check('sidebar group rows show partial or off eyes', partial >= 1, `${partial}`);
    }
    // User hides one extra element that is also a match, then restore must keep it.
    const keep = await page.evaluate((m) => {
      const app = window.__xray.app;
      return m ? m.id : -1;
    }, rep.matches[0] ?? null);
    const rest = await page.evaluate(() => {
      window.__xrayCleanup.restore();
      const app = window.__xray.app;
      const st = app.renderer.state;
      let flagged = 0;
      for (let i = 0; i < st.flags.length; i++) if (st.flags[i] & 2) flagged++;
      return { hides: app.controller.settings.overrides.userHides.size };
    });
    void keep;
    await page.waitForTimeout(500);
    const after = await page.evaluate((ids) => {
      const app = window.__xray.app;
      // flags are reapplied on the next tick
      return ids.filter((id) => (app.renderer.state.flags[id] & 2) !== 0).length;
    }, rep.matches.map((m) => m.id));
    check('restore empties userHides and clears hidden flags', rest.hides === 0 && after === 0, `userHides ${rest.hides}, flagged ${after}`);
    let hiddenRowsAfter = await page.locator('.tr.hid').count();
    for (let i = 0; i < 10 && hiddenRowsAfter > 0; i++) {
      await page.waitForTimeout(300);
      hiddenRowsAfter = await page.locator('.tr.hid').count();
    }
    check('sidebar shows nothing hidden after restore', hiddenRowsAfter === 0, `${hiddenRowsAfter}`);

    // Provenance: a user hide that cleanup also matched survives restore.
    if (rep.total > 0) {
      const prov = await page.evaluate((id) => {
        const app = window.__xray.app;
        app.controller.settings.overrides.userHides.add(id);
        window.__xrayCleanup.hide();
        window.__xrayCleanup.restore();
        const stays = app.controller.settings.overrides.userHides.has(id);
        app.controller.settings.overrides.userHides.clear();
        return stays;
      }, rep.matches[0].id);
      check('an element hidden by the user and by cleanup stays hidden after restore', prov === true);
    }
    check('no console errors', errors.length === 0, errors.join(' | '));
    await page.close();
  }
} catch (e) {
  console.error(e);
  failed = true;
} finally {
  if (browser) await browser.close();
  vite.kill('SIGTERM');
}
process.exit(failed ? 1 : 0);
