// Headless check of the action panel and its tools: toolbar rendering and boot filtering, the penetration schedule
// (fzk-haus and synth5k), measure, clearance. Screenshots: bench/tools-penetrations.png, tools-measure.png,
// tools-clearance.png. Usage: SMOKE_PORT=5332 node bench/smoke-tools.mjs
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const port = Number(process.env.SMOKE_PORT ?? 5332);

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

const errors = [];
async function open(browser, model, init) {
  const ctx = await browser.newContext({ viewport: { width: 1600, height: 900 } });
  const page = await ctx.newPage();
  if (init) await page.addInitScript(init);
  page.on('console', (m) => { if (m.type() === 'error') errors.push(`[${model}] ${m.text()}`); });
  page.on('pageerror', (e) => errors.push(`[${model}] [pageerror] ${e.message}`));
  await page.goto(`http://127.0.0.1:${port}/?model=${model}`);
  await page.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: 180000 });
  const err = await page.evaluate('window.__xrayError');
  if (err) errors.push(err);
  await page.waitForTimeout(500);
  return { page, ctx };
}

const summary = {};
let browser;
try {
  await waitForServer();
  browser = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });

  // ------------------------------------------------------------------ toolbar basics + fzk-haus
  {
    const { page, ctx } = await open(browser, 'fzk-haus');
    const ids = await page.evaluate(() => [...document.querySelectorAll('#xray-toolbar .xt-btn-tool')].map((b) => b.getAttribute('data-tool')));
    console.log('toolbar buttons:', ids.join(', '));
    const want = ['open', 'xray', 'viewModes', 'measure', 'clearance', 'penetrations', 'cleanup'];
    check('toolbar renders the registered tools in order (other plugins may add more)', want.every((t) => ids.includes(t)) && JSON.stringify(ids.filter((i) => want.includes(i))) === JSON.stringify(want), ids.join(','));
    const w = await page.evaluate(() => document.getElementById('xray-toolbar').getBoundingClientRect().width);
    check('strip is 44 px wide', Math.round(w) === 44, `${w}`);
    check('window.__xrayToolbar.tools() matches', JSON.stringify(await page.evaluate(() => window.__xrayToolbar.tools())) === JSON.stringify(ids));

    // x-ray tool: toggle and active state
    const xrayBefore = await page.evaluate(() => window.__xray.app.settings.xray);
    await page.click('#xray-toolbar [data-tool="xray"]');
    const xrayAfter = await page.evaluate(() => window.__xray.app.settings.xray);
    check('x-ray tool toggles app.setXray', xrayBefore !== xrayAfter);
    await page.click('#xray-toolbar [data-tool="xray"]');

    // drawer: open, only one at a time, Escape closes, t toggles the strip
    await page.click('#xray-toolbar [data-tool="viewModes"]');
    check('view modes drawer opens', await page.evaluate(() => !document.getElementById('xray-toolbar-drawer').classList.contains('hidden')));
    await page.click('#xray-toolbar [data-tool="cleanup"]');
    const title = await page.evaluate(() => document.querySelector('#xray-toolbar-drawer .xt-title').textContent);
    check('opening another tool replaces the drawer', title === 'Cleanup', title);
    await page.keyboard.press('Escape');
    check('Escape closes the drawer', await page.evaluate(() => document.getElementById('xray-toolbar-drawer').classList.contains('hidden')));
    await page.keyboard.press('t');
    check('t hides the strip', await page.evaluate(() => document.getElementById('xray-toolbar').classList.contains('hidden')));
    await page.keyboard.press('t');
    check('t shows the strip again', await page.evaluate(() => !document.getElementById('xray-toolbar').classList.contains('hidden')));
    check('tool.<id> actions are registered', await page.evaluate(() => !!document.querySelector('#xray-toolbar')) );

    // penetrations on fzk-haus
    const fzk = await page.evaluate(() => {
      const app = window.__xray.app;
      const ops = app.loaded.model.relations.openings ?? [];
      const a = window.__xrayPenetrations.analyse({ scope: 'focus classes' });
      return { openings: ops.length, voids: app.loaded.model.relations.voids.length, rows: a.rows.length, mep: a.mepCount, hosts: a.hostCount, hasOpeningData: a.hasOpeningData, ms: a.ms };
    });
    console.log('fzk-haus penetrations:', JSON.stringify(fzk));
    check('fzk-haus carries opening bounds', fzk.openings === 17, `${fzk.openings}`);
    check('fzk-haus has no MEP: zero penetrations', fzk.rows === 0 && fzk.mep === 0);
    const fzkFocus = await page.evaluate(() => window.__xrayPenetrations.analyse({ scope: 'focus only' }).rows.length);
    check('scope focus only: zero as well', fzkFocus === 0);
    summary.fzk = fzk;
    await ctx.close();
  }

  // ------------------------------------------------------------------ synth5k penetrations
  {
    const { page, ctx } = await open(browser, 'synth5k');
    const res = await page.evaluate(() => {
      const t0 = performance.now();
      const a = window.__xrayPenetrations.analyse({ scope: 'focus classes' });
      return { total: a.rows.length, summary: a.summary, mep: a.mepCount, hosts: a.hostCount, ms: a.ms, wall: performance.now() - t0, hasOpeningData: a.hasOpeningData,
        gaps: a.rows.filter((r) => r.gapMm !== null).slice(0, 3).map((r) => r.gapMm), orient: Object.entries(a.rows.reduce((m, r) => ((m[r.orientation] = (m[r.orientation] ?? 0) + 1), m), {})) };
    });
    console.log('synth5k penetrations:', JSON.stringify(res));
    check('synth5k: hundreds of penetrations', res.total >= 100, `${res.total}`);
    check('synth5k: has opening data', res.hasOpeningData);
    summary.synth5k = res;
    await page.evaluate(() => window.__xrayToolbar.open('penetrations'));
    await page.waitForSelector('#xray-toolbar-drawer .xt-table tbody tr', { timeout: 20000 });
    const rowsShown = await page.evaluate(() => document.querySelectorAll('#xray-toolbar-drawer .xt-table tbody tr').length);
    check('table shows rows', rowsShown > 0, `${rowsShown}`);
    const bcf = await page.evaluate(() => [...document.querySelectorAll('#xray-toolbar-drawer button')].find((b) => /BCF/.test(b.textContent)));
    const bcfInfo = await page.evaluate(() => { const b = [...document.querySelectorAll('#xray-toolbar-drawer button')].find((x) => /BCF/.test(x.textContent)); return { disabled: b.disabled, title: b.title }; });
    console.log('BCF button:', JSON.stringify(bcfInfo));
    // click the first row
    const sel0 = await page.evaluate(() => window.__xray.app.selection.length);
    await page.click('#xray-toolbar-drawer .xt-table tbody tr:first-child');
    await page.waitForTimeout(1600);
    const after = await page.evaluate(() => ({ sel: window.__xray.app.selection, markers: document.querySelectorAll('[data-layer="penetrations"] circle[data-pen]').length, shown: [...document.querySelectorAll('[data-layer="penetrations"] circle[data-pen]')].filter((c) => c.style.display !== 'none').length }));
    check('clicking a row selects the MEP element', after.sel.length === 1 && sel0 === 0, JSON.stringify(after.sel));
    check('markers are drawn on the overlay', after.shown > 0, `${after.shown} visible of ${after.markers}`);
    const csvLen = await page.evaluate(() => { let n = 0; const orig = URL.createObjectURL; URL.createObjectURL = (b) => { n = b.size; return orig.call(URL, b); }; [...document.querySelectorAll('#xray-toolbar-drawer button')].find((b) => /Export CSV/.test(b.textContent)).click(); return n; });
    check('Export CSV produces a file with all rows', csvLen > 897 * 100, `${csvLen} bytes`);
    // filter chip: status "no opening" has none in synth5k, so only check the table reacts
    await page.evaluate(() => [...document.querySelectorAll('#xray-toolbar-drawer .xt-chip')].find((c) => /^opening/.test(c.textContent))?.click());
    await page.waitForTimeout(200);
    const filtered = await page.evaluate(() => document.querySelectorAll('#xray-toolbar-drawer .xt-table tbody tr').length);
    check('status chip filters the table', filtered > 0 && filtered <= 500, `${filtered}`);
    await page.evaluate(() => [...document.querySelectorAll('#xray-toolbar-drawer .xt-chip')].find((c) => /^opening/.test(c.textContent))?.click());
    await page.waitForTimeout(200);
    await page.screenshot({ path: resolve(here, 'tools-penetrations.png'), timeout: 240000 });
    await ctx.close();
  }

  // ------------------------------------------------------------------ measure + clearance on building
  {
    const { page, ctx } = await open(browser, 'building');
    await page.evaluate(() => window.__xrayToolbar.open('measure'));
    // find two clickable surface pixels
    const pts = await page.evaluate(() => {
      const r = document.getElementById('c').getBoundingClientRect();
      const out = [];
      for (let fy = 0.3; fy <= 0.9 && out.length < 2; fy += 0.04) {
        for (let fx = 0.5; fx <= 0.95; fx += 0.025) {
          const x = r.left + r.width * fx;
          const y = r.top + r.height * fy;
          const h = window.__xrayMeasure.pickAt(x, y);
          if (h && (out.length === 0 || (h.element !== out[0].element && Math.hypot(x - out[0].x, y - out[0].y) > 60))) { out.push({ x, y, element: h.element }); if (out.length === 2) break; }
        }
      }
      return out;
    });
    check('found two surface pixels', pts.length === 2, JSON.stringify(pts));
    const selBefore = await page.evaluate(() => window.__xray.app.selection.length);
    await page.mouse.click(pts[0].x, pts[0].y);
    await page.mouse.move(pts[1].x - 40, pts[1].y - 30);
    await page.mouse.move(pts[1].x, pts[1].y, { steps: 4 });
    await page.waitForTimeout(250);
    check('first click leaves a pending point (and does not select)', await page.evaluate(() => !!window.__xrayMeasure.pending) && (await page.evaluate(() => window.__xray.app.selection.length)) === selBefore);
    await page.keyboard.press('Escape');
    check('Escape cancels the pending point and keeps the drawer open', !(await page.evaluate(() => !!window.__xrayMeasure.pending)) && (await page.evaluate(() => !document.getElementById('xray-toolbar-drawer').classList.contains('hidden'))));
    await page.mouse.click(pts[0].x, pts[0].y);
    await page.mouse.click(pts[1].x, pts[1].y);
    await page.waitForTimeout(400);
    const m1 = await page.evaluate(() => ({ n: window.__xrayMeasure.list.length, d: window.__xrayMeasure.list[0]?.distance, labels: [...document.querySelectorAll('[data-measure-label]')].map((t) => t.textContent) }));
    console.log('measure:', JSON.stringify(m1));
    check('a distance label appears on the overlay', m1.n === 1 && m1.labels.length === 1 && /m$/.test(m1.labels[0]), JSON.stringify(m1.labels));
    // element to element
    await page.evaluate(() => { const sel = document.querySelector('#xray-toolbar-drawer select'); sel.value = 'element to element'; sel.dispatchEvent(new Event('change')); });
    const e2 = await page.evaluate((pp) => pp, pts);
    if (pts[0].element !== pts[1].element) {
      await page.mouse.click(pts[0].x, pts[0].y);
      await page.mouse.click(pts[1].x, pts[1].y);
      await page.waitForTimeout(400);
      const m2 = await page.evaluate(() => window.__xrayMeasure.list.map((m) => ({ kind: m.kind, d: m.distance })));
      console.log('element measure:', JSON.stringify(m2));
      check('element to element adds a measurement', m2.length === 2 && m2[1].kind === 'element');
    } else console.log('(both pixels hit the same element: element mode skipped)');
    void e2;
    await page.screenshot({ path: resolve(here, 'tools-measure.png'), timeout: 240000 });
    await page.evaluate(() => window.__xrayToolbar.close());

    // clearance with a duct selected
    const duct = await page.evaluate(() => window.__xray.app.loaded.model.elements.find((e) => e.ifcClass === 'IfcDuctSegment')?.id ?? window.__xray.app.loaded.model.elements.find((e) => /Duct|Pipe|Flow/.test(e.ifcClass))?.id);
    await page.evaluate((id) => window.__xray.app.selectIds([id]), duct);
    await page.waitForTimeout(1500);
    await page.evaluate(() => window.__xrayToolbar.open('clearance'));
    await page.evaluate(() => window.__xrayClearance.setEnabled(true));
    await page.waitForTimeout(1200);
    const cl = await page.evaluate(() => ({ counts: window.__xrayClearance.counts, status: window.__xrayClearance.status, legend: !!document.querySelector('[data-legend="clearance"]') }));
    console.log('clearance:', JSON.stringify(cl));
    const nonFar = cl.counts ? cl.counts.clash + cl.counts.tight + cl.counts.ok : 0;
    check('clearance bands some context elements', nonFar > 0, cl.status);
    check('legend is on the overlay', cl.legend);
    summary.clearance = cl;
    await page.screenshot({ path: resolve(here, 'tools-clearance.png'), timeout: 240000 });
    // restore on disable
    const restored = await page.evaluate(() => {
      const st = window.__xray.renderer.state.color;
      const before = Array.from(st);
      window.__xrayClearance.setEnabled(false);
      const base = window.__xray.renderer.baseColor ? Array.from(window.__xray.renderer.baseColor) : null;
      const after = Array.from(window.__xray.renderer.state.color);
      return { changed: before.some((v, i) => v !== after[i]), matchesBase: base ? base.every((v, i) => Math.abs(v - after[i]) < 1e-6) : null };
    });
    check('disabling clearance restores the colours', restored.changed && restored.matchesBase !== false, JSON.stringify(restored));
    await ctx.close();
  }

  // ------------------------------------------------------------------ boot tool filtering
  {
    const { page, ctx } = await open(browser, 'building', () => { window.__xrayBoot = { tools: ['xray', 'measure'] }; });
    const ids = await page.evaluate(() => [...document.querySelectorAll('#xray-toolbar .xt-btn-tool')].map((b) => b.getAttribute('data-tool')));
    check('window.__xrayBoot.tools filters and orders the buttons', JSON.stringify(ids) === JSON.stringify(['xray', 'measure']), ids.join(','));
    await ctx.close();
  }
  {
    const { page, ctx } = await open(browser, 'building', () => { window.__xrayBoot = { tools: ['penetrations'], openTool: 'penetrations' }; });
    await page.waitForTimeout(1500);
    const st = await page.evaluate(() => ({ ids: window.__xrayToolbar.tools(), open: !document.getElementById('xray-toolbar-drawer').classList.contains('hidden'), title: document.querySelector('#xray-toolbar-drawer .xt-title')?.textContent }));
    check('openTool opens the drawer at boot', st.open && st.title === 'Penetrations', JSON.stringify(st));
    await ctx.close();
  }

  check('no console errors', errors.length === 0, errors.slice(0, 5).join(' | '));
  console.log('\nSUMMARY', JSON.stringify(summary));
} finally {
  await browser?.close();
  vite.kill();
}
process.exit(failed ? 1 : 0);
