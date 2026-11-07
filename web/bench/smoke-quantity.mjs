// Headless smoke test for quantity summaries in the search bar (count, sum, avg, min, max, by) and the quantity HUD.
// Starts vite (bench/vite.smoke.config.mjs) on port 5681, loads fzk-haus and synth5k at 1600x900 and drives the bar with
// Playwright: `count where class like 'IfcWall%'`, a sum cross-checked against the properties of the model (computed in
// this script, not by the engine), a `by storey` query, Enter and Shift+Enter, the HUD (shown under the search box, clear
// of the gizmo and registered with the overlay, stays while hovered, fades, Escape, click copies), the console output
// (page.on('console')), kiosk mode and the phone layout (390x844). Screenshots: bench/quantity-*.png.
// Zero console errors is a check. Usage: SMOKE_PORT=5681 node bench/smoke-quantity.mjs
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const port = Number(process.env.SMOKE_PORT ?? 5681);

function loadPlaywright() {
  const candidates = [process.env.PLAYWRIGHT_MODULE, resolve(root, 'node_modules/playwright'), '/opt/node-tools/node_modules/playwright', '/opt/node22/lib/node_modules/playwright'].filter(Boolean);
  for (const c of candidates) {
    try { return createRequire(import.meta.url)(c); } catch { /* try next */ }
  }
  throw new Error('playwright not found; set PLAYWRIGHT_MODULE');
}
const { chromium } = loadPlaywright();

const vite = spawn(resolve(root, 'node_modules/.bin/vite'), ['--config', resolve(here, 'vite.smoke.config.mjs'), '--host', '127.0.0.1', '--port', String(port), '--strictPort'], {
  cwd: root, stdio: ['ignore', 'pipe', 'pipe'],
});
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

const GL = ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'];

async function open(browser, model, opts = {}) {
  const ctx = await browser.newContext({ viewport: opts.viewport ?? { width: 1600, height: 900 }, permissions: ['clipboard-read', 'clipboard-write'] });
  if (opts.init) await ctx.addInitScript(opts.init);
  const page = await ctx.newPage();
  const errors = [];
  const logs = [];
  page.on('console', (m) => {
    if (m.type() === 'error') errors.push(m.text());
    const e = { type: m.type(), text: m.text(), data: null };
    if (m.type() === 'table') e.data = m.args()[0].jsonValue().catch(() => null);
    logs.push(e);
  });
  page.on('pageerror', (e) => errors.push(`[pageerror] ${e.message}`));
  await page.goto(`http://127.0.0.1:${port}/?model=${model}`);
  await page.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: 120000 });
  const err = await page.evaluate('window.__xrayError');
  if (err) errors.push(`[app] ${err}`);
  await page.waitForFunction('window.__xraySearch && window.__xraySearch.indexReady()', null, { timeout: 60000 });
  await page.waitForTimeout(800);
  return { ctx, page, errors, logs };
}

const S = (page) => page.evaluate(() => window.__xraySearch.state());
const sel = (page) => page.evaluate(() => window.__xray.app.selection);
const hud = (page) => page.evaluate(() => {
  const h = window.__xraySearch.hud;
  const st = h.state();
  const r = h.root.getBoundingClientRect();
  return { ...st, opacity: Number(getComputedStyle(h.root).opacity), dom: { left: r.left, top: r.top, right: r.right, bottom: r.bottom, width: r.width, height: r.height } };
});
const typeInBar = async (page, text) => {
  await page.mouse.move(700, 600); // away from the chrome: no help tooltip over the picture
  await page.keyboard.press('/');
  await page.locator('.ab-input').fill('');
  await page.keyboard.type(text);
  await page.waitForTimeout(150);
};
const shot = (page, name) => page.screenshot({ path: resolve(here, name), timeout: 180000 });
const overlap = (a, b) => a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
const fmt = (n) => Number(n.toPrecision(10));

async function runFzk(browser) {
  const tag = '[fzk-haus]';
  const { ctx, page, errors, logs } = await open(browser, 'fzk-haus');
  try {
    // ---- facts, computed here from the model data (not by the engine)
    const facts = await page.evaluate(() => {
      const m = window.__xray.app.controller.model;
      const walls = m.elements.filter((e) => e.ifcClass.startsWith('IfcWall'));
      let sideArea = 0, sideN = 0;
      for (const e of walls) { const v = e.props && e.props['BaseQuantities.NetSideArea']; if (typeof v === 'number') { sideArea += v; sideN++; } }
      let len = 0, lenN = 0;
      for (const e of m.elements) { const v = e.props && e.props['BaseQuantities.Length']; if (typeof v === 'number') { len += v; lenN++; } }
      const storeyOf = new Map(m.storeys.map((s) => [s.id, s.name]));
      const perStorey = {};
      for (const e of walls) { const k = e.storey === null ? '(none)' : storeyOf.get(e.storey); perStorey[k] = (perStorey[k] ?? 0) + 1; }
      const classes = [...new Set(walls.map((e) => e.ifcClass))];
      return { total: m.elements.length, walls: walls.length, classes, sideArea, sideN, len, lenN, perStorey, storeys: m.storeys.map((s) => s.name) };
    });
    console.log(tag, 'facts', JSON.stringify(facts));

    // ---- the API, script side
    const api = await page.evaluate(() => {
      const r = window.__xraySearch.summarize("sum netsidearea, count where class like 'IfcWall%'");
      return { total: r.total, unit: r.unit, estimated: r.estimated, skipped: r.skippedCount, rows: r.rows.length, keys: Object.keys(r).sort(), aggs: r.aggs.map((a) => [a.fn, a.value, a.n]), lines: r.lines };
    });
    console.log(tag, 'api', JSON.stringify(api));
    check(`${tag} summarize() returns rows, total, groups, skipped, estimated and unit`, ['rows', 'total', 'groups', 'skipped', 'estimated', 'unit'].every((k) => api.keys.includes(k)));
    check(`${tag} the API sum of NetSideArea over the walls equals the total of the properties`, Math.abs(api.total - facts.sideArea) < 1e-6 && api.aggs[0][2] === facts.sideN, `engine ${fmt(api.total)} vs props ${fmt(facts.sideArea)} over ${facts.sideN} walls`);
    check(`${tag} the API counts the walls`, api.aggs[1][1] === facts.walls && api.rows === facts.walls, `${api.aggs[1][1]} vs ${facts.walls}`);

    // ---- live preview: count
    const q1 = "count where class like 'IfcWall%'";
    await typeInBar(page, q1);
    const st = await S(page);
    const row = st.rows.find((r) => r.section === 'query');
    check(`${tag} the query row shows the count while typing`, !!row && row.label.startsWith(`${facts.walls} `), JSON.stringify(row));
    check(`${tag} the footer reports the elements summarised`, /summarised/.test(st.footer), st.footer);
    await shot(page, 'quantity-fzk-haus-preview.png');
    const before = logs.length;
    await page.keyboard.press('Enter');
    await page.waitForTimeout(500);
    const s1 = await sel(page);
    check(`${tag} Enter selects the ${facts.walls} walls`, s1.length === facts.walls, `${s1.length}`);
    await page.waitForFunction(() => Number(getComputedStyle(window.__xraySearch.hud.root).opacity) > 0.9, null, { timeout: 5000 }).catch(() => {});
    const h1 = await hud(page);
    check(`${tag} the HUD shows the answer`, h1.visible && h1.opacity > 0.9 && h1.lines[0].startsWith(`${facts.walls} `), JSON.stringify(h1.lines));
    const mine = logs.slice(before);
    const open1 = mine.find((l) => l.type === 'startGroupCollapsed');
    check(`${tag} one console.groupCollapsed with the summary line`, !!open1 && open1.text.includes(q1) && open1.text.includes(`${facts.walls} `) && mine.filter((l) => l.type === 'startGroupCollapsed').length === 1, open1 && open1.text);
    check(`${tag} the group has a console.table and is closed again`, mine.some((l) => l.type === 'table') && mine.some((l) => l.type === 'endGroup'));
    // placement
    const geom = await page.evaluate(() => {
      const host = document.getElementById('xray-topbar-search').getBoundingClientRect();
      const bar = document.getElementById('xray-topbar').getBoundingClientRect();
      const g = document.getElementById('xray-gizmo').getBoundingClientRect();
      const h = window.__xraySearch.hud.root.getBoundingClientRect();
      return { host: { l: host.left, r: host.right, b: host.bottom }, bar: { b: bar.bottom }, giz: { left: g.left, top: g.top, right: g.right, bottom: g.bottom }, hud: { left: h.left, top: h.top, right: h.right, bottom: h.bottom } };
    });
    check(`${tag} the HUD sits just under the top-bar search`, geom.hud.top >= geom.bar.b && geom.hud.top - geom.bar.b < 16 && geom.hud.left < (geom.host.l + geom.host.r) / 2 && geom.hud.right > (geom.host.l + geom.host.r) / 2, JSON.stringify(geom));
    check(`${tag} the HUD stays clear of the gizmo`, !overlap(geom.hud, geom.giz));
    const reserved = await page.evaluate(async () => {
      const { getOverlay } = await import('/src/ui/overlay.ts');
      const ov = getOverlay(window.__xray.app);
      ov.update();
      const h = window.__xraySearch.hud.root.getBoundingClientRect();
      const c = window.__xray.app.canvas.getBoundingClientRect();
      return ov.reserved.some((r) => Math.abs(r.x - (h.left - c.left)) < 1.5 && Math.abs(r.y - (h.top - c.top)) < 1.5 && Math.abs(r.w - h.width) < 1.5);
    });
    check(`${tag} the HUD is a reserved rect of the overlay while shown`, reserved);
    const css = await page.evaluate(() => { const s = getComputedStyle(window.__xraySearch.hud.root); return { bf: s.backdropFilter || s.webkitBackdropFilter, bg: s.backgroundColor }; });
    check(`${tag} the HUD is translucent with a blur`, /blur/.test(css.bf) && /rgba\(.*,\s*0?\.\d+\)/.test(css.bg), JSON.stringify(css));
    await shot(page, 'quantity-fzk-haus-count.png');

    // ---- sum, cross-checked
    const q2 = "sum netsidearea where class like 'IfcWall%'";
    await typeInBar(page, q2);
    await page.keyboard.press('Enter');
    await page.waitForTimeout(500);
    const h2 = await hud(page);
    const shown = h2.lines[0];
    const m = /Σ netsidearea ([\d.\u202f]+) m²/i.exec(shown);
    const shownVal = m ? Number(m[1].replace(/ /g, '')) : NaN;
    check(`${tag} the HUD sum equals the property total (rounded for display)`, Math.abs(shownVal - facts.sideArea) < 0.06, `"${shown}" vs ${fmt(facts.sideArea)}`);
    check(`${tag} the sum is selected too`, (await sel(page)).length === facts.walls);
    const tableLog = logs.filter((l) => l.type === 'table').pop();
    const tdata = tableLog ? await tableLog.data : null;
    const first = tdata && Object.values(tdata)[0];
    check(`${tag} the console table lists the elements (GlobalId, name, class, storey, value, source)`, !!first && ['GlobalId', 'Name', 'Class', 'Storey', 'NetSideArea', 'NetSideArea source'].every((k) => k in first) && Object.keys(tdata).length === facts.walls, JSON.stringify(first));
    check(`${tag} the table row names the source property`, !!first && first['NetSideArea source'] === 'BaseQuantities.NetSideArea', first && first['NetSideArea source']);
    await shot(page, 'quantity-fzk-haus-sum.png');

    // ---- estimates: a sum of a quantity not every wall has
    const q3 = 'sum length, sum volume, sum area';
    await typeInBar(page, q3);
    await page.keyboard.press('Enter');
    await page.waitForTimeout(500);
    const h3 = await hud(page);
    console.log(tag, 'estimate HUD:', JSON.stringify(h3.lines));
    check(`${tag} totals with estimated values say how many`, /\(\d+ est\.\)/.test(h3.lines[0]), h3.lines[0]);
    check(`${tag} the console lists the skipped elements with their reasons`, logs.some((l) => l.type === 'log' && /^Skipped \d+ element/.test(l.text)) && /\d+ skipped/.test(h3.lines[0]), h3.lines[0]);
    const skipTable = logs.filter((l) => l.type === 'table').pop();
    const sk = skipTable ? await skipTable.data : null;
    check(`${tag} the skipped table has a reason for each element`, !!sk && Object.values(sk).every((r) => r.Reason && r.GlobalId), sk && JSON.stringify(Object.values(sk)[0]));
    await shot(page, 'quantity-fzk-haus-estimates.png');

    // ---- by storey
    const q4 = "sum netsidearea, count where class like 'IfcWall%' by storey";
    await typeInBar(page, q4);
    await page.keyboard.press('Enter');
    await page.waitForTimeout(500);
    const h4 = await hud(page);
    const grp = await page.evaluate(() => {
      const r = window.__xraySearch.summarize("sum netsidearea, count where class like 'IfcWall%' by storey");
      return r.groups.map((g) => [g.key, g.count, g.total]);
    });
    console.log(tag, 'groups', JSON.stringify(grp), '| HUD', JSON.stringify(h4.lines));
    check(`${tag} by storey: a second HUD line with the groups`, h4.lines.length === 2 && grp.every(([k]) => h4.lines[1].includes(k)) || (h4.lines.length === 2 && /\+\d+ more \(console\)/.test(h4.lines[1])), h4.lines[1]);
    check(`${tag} by storey: the group counts match the model`, grp.every(([k, n]) => facts.perStorey[k] === n) && grp.reduce((a, g) => a + g[1], 0) === facts.walls, JSON.stringify(facts.perStorey));
    check(`${tag} by storey: the subtotals add up to the total`, Math.abs(grp.reduce((a, g) => a + (g[2] ?? 0), 0) - facts.sideArea) < 1e-6);
    check(`${tag} by storey: the console has a subtotal table`, logs.some((l) => l.type === 'log' && /^Subtotals by storey/.test(l.text)));
    await shot(page, 'quantity-fzk-haus-by-storey.png');

    // ---- an error reads inline with a position
    await typeInBar(page, 'sum length where class =');
    const stE = await S(page);
    check(`${tag} an error in the condition is shown with its position`, stE.notes.some((n) => /Check the text around character 25/.test(n)), JSON.stringify(stE.notes));
    await page.keyboard.press('Escape');
    await typeInBar(page, 'sum banana');
    check(`${tag} a bare "sum banana" stays a plain text search`, !(await S(page)).rows.some((r) => r.section === 'query'));
    await page.keyboard.press('Escape');
    await typeInBar(page, 'sum banana by storey');
    check(`${tag} an unknown quantity in a summary is an error note`, (await S(page)).notes.some((n) => /No quantity or property matches "banana"/.test(n)));
    await page.keyboard.press('Escape');

    // ---- the HUD life: hover keeps it, it fades, Escape and click dismiss, click copies
    await page.evaluate(() => { window.__xraySearch.hud.holdMs = 1500; });
    await page.evaluate(() => window.__xray.app.selectIds([], false));
    await typeInBar(page, "count where class like 'IfcWall%'");
    await page.keyboard.press('Shift+Enter');
    await page.waitForTimeout(400);
    check(`${tag} Shift+Enter summarises without changing the selection`, (await sel(page)).length === 0 && (await hud(page)).visible);
    const c0 = await page.evaluate(() => window.__xraySearch.hud.root.getBoundingClientRect());
    await page.mouse.move(c0.left + c0.width / 2, c0.top + c0.height / 2);
    await page.waitForTimeout(2600);
    const hov = await hud(page);
    check(`${tag} the HUD stays while the pointer is on it`, hov.visible && hov.opacity > 0.9, `opacity ${hov.opacity}`);
    await page.mouse.move(800, 600);
    await page.waitForTimeout(900);
    const mid = await hud(page);
    await page.waitForTimeout(1700);
    const gone = await hud(page);
    check(`${tag} the HUD fades after the hold time`, mid.visible && !gone.visible && gone.opacity === 0 && (await page.evaluate(() => window.__xraySearch.hud.root.hidden)), `mid ${mid.opacity.toFixed(2)} visible ${mid.visible}, end opacity ${gone.opacity}`);
    check(`${tag} the reserved rect goes with it`, await page.evaluate(async () => {
      const { getOverlay } = await import('/src/ui/overlay.ts');
      const ov = getOverlay(window.__xray.app);
      ov.update();
      return !ov.reserved.some((r) => r.y > 20 && r.y < 80 && r.w > 100 && r.w < 700 && r.h < 80 && r.x > 100);
    }));
    await page.evaluate(() => { window.__xraySearch.hud.holdMs = 6000; });
    await typeInBar(page, "count where class like 'IfcWall%'");
    await page.keyboard.press('Shift+Enter');
    await page.waitForTimeout(300);
    await page.keyboard.press('Escape');
    await page.waitForTimeout(600);
    check(`${tag} Escape dismisses the HUD`, !(await hud(page)).visible);
    await typeInBar(page, "count where class like 'IfcWall%'");
    await page.keyboard.press('Shift+Enter');
    await page.waitForTimeout(300);
    const text = (await hud(page)).text;
    await page.locator('#xray-qhud').click();
    await page.waitForTimeout(500);
    const clip = await page.evaluate(() => navigator.clipboard.readText());
    check(`${tag} a click copies the summary text and dismisses the HUD`, clip === text && text.length > 0 && !(await hud(page)).visible, JSON.stringify(clip));
  } finally {
    const real = errors.filter((e) => !/favicon/i.test(e));
    check(`${tag} zero console errors`, real.length === 0, real.slice(0, 3).join(' | '));
    await ctx.close();
  }
}

async function runSynth(browser) {
  const tag = '[synth5k]';
  const { ctx, page, errors, logs } = await open(browser, 'synth5k');
  try {
    const facts = await page.evaluate(() => {
      const m = window.__xray.app.controller.model;
      const storeyOf = new Map(m.storeys.map((s) => [s.id, s.name]));
      let len = 0, n = 0;
      const per = {};
      for (const e of m.elements) {
        if (e.ifcClass !== 'IfcPipeSegment') continue;
        const v = e.props['Qto_PipeSegmentBaseQuantities.Length'];
        n++; len += v;
        const k = e.storey === null ? '(none)' : storeyOf.get(e.storey);
        per[k] = (per[k] ?? 0) + v;
      }
      return { n, len, per };
    });
    console.log(tag, 'facts', JSON.stringify({ n: facts.n, len: fmt(facts.len), per: Object.fromEntries(Object.entries(facts.per).map(([k, v]) => [k, fmt(v)])) }));
    const q = "sum length, count where class = 'IfcPipeSegment' by storey";
    await typeInBar(page, q);
    const t0 = Date.now();
    await page.keyboard.press('Enter');
    await page.waitForTimeout(500);
    const h = await hud(page);
    console.log(tag, 'HUD', JSON.stringify(h.lines), `(${Date.now() - t0} ms incl. wait)`);
    check(`${tag} the HUD gives the pipe count and the real total length`, h.lines[0].startsWith(`${facts.n} pipe segments · Σ length`) && h.lines.length === 2, JSON.stringify(h.lines));
    const r = await page.evaluate(() => { const x = window.__xraySearch.summarize("sum length, count where class = 'IfcPipeSegment' by storey"); return { total: x.total, groups: x.groups.map((g) => [g.key, g.total]), ms: x.ms }; });
    check(`${tag} the total length equals the sum of the properties`, Math.abs(r.total - facts.len) < 1e-6, `${fmt(r.total)} vs ${fmt(facts.len)}`);
    check(`${tag} every storey subtotal equals the sum of its pipes`, r.groups.every(([k, v]) => Math.abs(v - facts.per[k]) < 1e-6) && r.groups.length === Object.keys(facts.per).length);
    const sel1 = await sel(page);
    check(`${tag} the pipes are selected`, sel1.length === facts.n, `${sel1.length}`);
    const t1 = await page.evaluate(() => {
      const t = performance.now();
      for (let i = 0; i < 20; i++) window.__xraySearch.summarize('sum volume, sum area, sum length');
      return (performance.now() - t) / 20;
    });
    console.log(tag, `sum volume/area/length over all 5000 elements incl. rows: ${t1.toFixed(1)} ms per run`);
    const tv = await page.evaluate(() => { const x = window.__xraySearch.summarize("sum volume where class = 'IfcBeam'"); return { v: x.total, est: x.estimated, matched: x.matched }; });
    console.log(tag, 'beam volume', JSON.stringify(tv));
    await shot(page, 'quantity-synth5k-by-storey.png');
  } finally {
    const real = errors.filter((e) => !/favicon/i.test(e));
    check(`${tag} zero console errors`, real.length === 0, real.slice(0, 3).join(' | '));
    await ctx.close();
  }
}

async function runPhone(browser) {
  const tag = '[phone]';
  const { ctx, page, errors } = await open(browser, 'fzk-haus', { viewport: { width: 390, height: 844 } });
  try {
    await page.locator('.ab-icon').click();
    await page.mouse.move(200, 600);
    await page.keyboard.type("sum netsidearea, count where class like 'IfcWall%' by storey");
    await page.waitForTimeout(200);
    await shot(page, 'quantity-phone-preview.png');
    await page.keyboard.press('Enter');
    await page.waitForTimeout(500);
    const h = await hud(page);
    const bar = await page.evaluate(() => document.getElementById('xray-topbar').getBoundingClientRect().bottom);
    console.log(tag, 'HUD', JSON.stringify(h.lines), JSON.stringify(h.dom));
    check(`${tag} the HUD is full width under the bar`, h.visible && Math.abs(h.dom.left - 8) < 1 && Math.abs(h.dom.right - 382) < 1 && h.dom.top >= bar && h.dom.top - bar < 16, JSON.stringify(h.dom));
    check(`${tag} the page does not scroll sideways`, await page.evaluate(() => document.documentElement.scrollWidth <= 390));
    await shot(page, 'quantity-phone-hud.png');
  } finally {
    const real = errors.filter((e) => !/favicon/i.test(e));
    check(`${tag} zero console errors`, real.length === 0, real.slice(0, 3).join(' | '));
    await ctx.close();
  }
}

async function runKiosk(browser) {
  const tag = '[kiosk]';
  const { ctx, page, errors } = await open(browser, 'fzk-haus', { init: 'window.__xrayBoot = { kiosk: true };' });
  try {
    await page.evaluate(() => { window.__xraySearch.hud.showLines(['test']); });
    await page.waitForTimeout(200);
    check(`${tag} the HUD stays hidden in kiosk mode`, await page.evaluate(() => !window.__xraySearch.hud.visible && window.__xraySearch.hud.root.hidden));
  } finally {
    const real = errors.filter((e) => !/favicon/i.test(e));
    check(`${tag} zero console errors`, real.length === 0, real.slice(0, 3).join(' | '));
    await ctx.close();
  }
}

let browser;
let exitCode = 0;
try {
  await waitForServer();
  browser = await chromium.launch({ args: GL });
  await runFzk(browser);
  await runSynth(browser);
  await runPhone(browser);
  await runKiosk(browser);
  if (checks.some((c) => !c.ok)) exitCode = 1;
  console.log(`\n${checks.filter((c) => c.ok).length}/${checks.length} checks passed`);
} catch (e) {
  console.error(e);
  exitCode = 1;
} finally {
  if (browser) await browser.close();
  vite.kill('SIGTERM');
}
process.exit(exitCode);
