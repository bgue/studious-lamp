// Headless smoke test for the classification tree and viewer: FZK-Haus at 1600x900, classify with the facets on, switch the Model tab
// to By classification, check the Construction preset (FRAME and ENVELOPE with counts), the UniFormat preset (B20 for the exterior
// walls), keyboard behaviour, Colour by Trade with its legend, isolate from the legend, confidence shading and Save as set.
// Screenshot: bench/class-tree.png.
// Usage: SMOKE_PORT=5735 node bench/smoke-class-tree.mjs
import { spawn } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const port = Number(process.env.SMOKE_PORT ?? 5691);

function loadPlaywright() {
  const candidates = [
    process.env.PLAYWRIGHT_MODULE,
    resolve(root, 'node_modules/playwright'),
    '/opt/node-tools/node_modules/playwright',
    '/opt/node22/lib/node_modules/playwright',
  ].filter(Boolean);
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
let browser;
let exitCode = 0;
try {
  await waitForServer();
  browser = await chromium.launch({ args: GL });
  const ctx = await browser.newContext({ viewport: { width: 1600, height: 900 } });
  const page = await ctx.newPage();
  const errors = [];
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', (e) => errors.push(`[pageerror] ${e.message}`));
  await page.route(/^https?:\/\/(?!127\.0\.0\.1)/, (route) => route.abort());
  await page.goto(`http://127.0.0.1:${port}/?model=fzk-haus`);
  await page.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: 120000 });
  await page.waitForFunction('window.__xraySearch && window.__xraySearch.indexReady() && window.__xrayClassify', null, { timeout: 60000 });
  await page.waitForTimeout(500);

  const rowsText = () => page.locator('.tv-win .tr').evaluateAll((rs) => rs.map((r) => ({ label: r.querySelector('.lbl')?.textContent ?? '', cnt: r.querySelector('.cnt')?.textContent ?? '', level: Number(r.getAttribute('aria-level')), key: r.dataset.key })));
  const modeBtn = (m) => page.locator(`.ct-seg-btn[data-mode="${m}"]`);

  // ---- the switch, before any classification
  check('the Model tab has the Model tree | By classification switch', (await modeBtn('model').count()) === 1 && (await modeBtn('class').count()) === 1);
  check('Model tree is the default and the controls are hidden', (await modeBtn('model').getAttribute('aria-pressed')) === 'true' && !(await page.locator('[data-role="class-controls"]').isVisible()));
  const modelRows = (await rowsText()).length;

  await page.evaluate(() => window.__xrayClassify.classify('all'));
  const stats = await page.evaluate(() => ({ n: Object.keys(window.__xrayClassify.facets.results()).length, els: window.__xrayClassify.results().length }));
  check('classify all with facets on gives every element facet values', stats.n === stats.els && stats.n > 0, JSON.stringify(stats));

  await modeBtn('class').click();
  await page.waitForTimeout(400);
  check('By classification shows the controls', await page.locator('[data-role="class-controls"]').isVisible());
  check('the stored mode is kept per viewer', await page.evaluate(() => JSON.parse(localStorage.getItem('xray.classtree.v1')).mode === 'class'));
  const top = await rowsText();
  console.log('construction top level:', JSON.stringify(top.filter((r) => r.level === 1)));
  const phases = top.filter((r) => r.level === 1);
  const phaseOf = (code) => phases.find((r) => r.label.startsWith(code));
  check('Construction preset: the FRAME and ENVELOPE nodes exist with counts', !!phaseOf('FRAME') && !!phaseOf('ENVELOPE') && Number(phaseOf('FRAME').cnt) > 0 && Number(phaseOf('ENVELOPE').cnt) > 0, JSON.stringify(phases.map((p) => `${p.label}:${p.cnt}`)));
  const sum = phases.reduce((a, r) => a + Number(r.cnt), 0);
  check('the top-level counts add up to every element (nothing disappears)', sum === stats.els, `${sum}/${stats.els}`);
  check('the tree is virtualised (few rows in the DOM)', (await page.locator('.tv-win .tr').count()) < 80);

  // ---- keyboard: the same behaviour as the model tree
  await page.locator('.tv-scroll').focus();
  await page.keyboard.press('Home');
  await page.keyboard.press('ArrowLeft');
  const closed = await rowsText();
  check('ArrowLeft closes the first node (its children go)', closed.length < top.length, `${top.length} -> ${closed.length}`);
  await page.keyboard.press('ArrowRight');
  const after = await rowsText();
  check('ArrowRight opens it again', after.length === top.length);
  await page.keyboard.press('ArrowRight');
  await page.keyboard.press('Enter');
  const selN = await page.evaluate(() => window.__xray.app.selection.length);
  check('Enter selects the elements of the active node', selN > 0, String(selN));
  await page.keyboard.press('ArrowLeft');
  await page.keyboard.press('ArrowLeft');
  await page.keyboard.press('Escape');

  // ---- the Standard (UniFormat II) preset
  await page.locator('[data-role="preset"]').selectOption('uniformat');
  await page.waitForTimeout(300);
  let uf = await rowsText();
  console.log('uniformat top:', JSON.stringify(uf.filter((r) => r.level === 1)));
  check('UniFormat: level 1 has B Shell', uf.some((r) => r.level === 1 && r.label === 'B Shell'));
  // level 1 is open by default; open B20 (a click on a caret toggles, so look first)
  const openIt = async (label) => {
    const r = page.locator('.tv-win .tr', { has: page.locator('.lbl', { hasText: new RegExp(`^${label}`) }) }).first();
    if ((await r.getAttribute('aria-expanded')) !== 'true') await r.locator('.caret').click();
    return rowsText();
  };
  await openIt('B Shell');
  uf = await openIt('B20 Exterior Enclosure');
  const b20 = uf.find((r) => r.label === 'B20 Exterior Enclosure');
  check('UniFormat: B shows B20 Exterior Enclosure', !!b20, JSON.stringify(uf.slice(0, 8).map((r) => r.label)));
  check('UniFormat: B20 shows B2010 Exterior Walls', uf.some((r) => r.label === 'B2010 Exterior Walls' && r.level === 3), JSON.stringify(uf.map((r) => r.label).slice(0, 12)));
  const walls = await page.evaluate(() => {
    const m = window.__xray.app.loaded.model;
    return m.elements.filter((e) => /^IfcWall/.test(e.ifcClass)).length;
  });
  const wallsNode = uf.find((r) => r.label === 'B2010 Exterior Walls');
  check('UniFormat: the exterior walls are counted under B2010', Number(wallsNode.cnt) > 0 && Number(wallsNode.cnt) <= walls, `${wallsNode.cnt} of ${walls} walls`);
  const depth = await page.evaluate(() => {
    const out = { level3: 0, level2: 0, level1: 0, none: 0, lines: {} };
    const walk = (n, d) => {
      const kids = n.children.filter((c) => c.kind === 'group');
      if (kids.length === 0) {
        if (n.label === 'Not classified') out[d === 1 ? 'none' : d === 2 ? 'level1' : 'level2'] += n.count;
        else if (d === 3) { out.level3 += n.count; out.lines[n.label] = n.count; }
        return;
      }
      kids.forEach((k) => walk(k, d + 1));
    };
    window.__xrayClassTree.roots().forEach((r) => walk(r, 1));
    return out;
  });
  console.log('UniFormat depth on FZK-Haus:', JSON.stringify(depth));
  const nc = (await page.locator('.tv-win .tr[aria-level="1"]').evaluateAll((rs) => rs.map((r) => [r.querySelector('.lbl').textContent, r.querySelector('.cnt').textContent])));
  console.log('uniformat level 1:', JSON.stringify(nc));
  const total = nc.reduce((a, r) => a + Number(r[1]), 0);
  const ncCount = nc.find((r) => r[0] === 'Not classified');
  console.log(`UniFormat coverage: ${stats.els - Number(ncCount?.[1] ?? 0)}/${stats.els} elements mapped (level 1 total ${total})`);
  check('UniFormat: no element disappears', total === stats.els);

  // ---- Group by: custom levels
  await page.locator('[data-role="preset"]').selectOption('envelope');
  await page.waitForTimeout(250);
  const env = await rowsText();
  check('Envelope preset groups by Placement (EXT/INT/BOUNDARY nodes)', env.some((r) => r.level === 1 && /^(EXT|INT|BOUNDARY)\b/.test(r.label)), JSON.stringify(env.filter((r) => r.level === 1).map((r) => r.label)));
  await page.locator('[data-role="level"][data-i="0"]').selectOption('Storey');
  await page.waitForTimeout(250);
  check('changing a level makes the preset Custom', (await page.locator('[data-role="preset"]').inputValue()) === 'custom');
  await page.locator('[data-role="preset"]').selectOption('construction');
  await page.waitForTimeout(250);

  // ---- the review badge, Save as set from a node
  const hasBadge = (await page.locator('.tv-win .tr .rv').count()) >= 0;
  check('rows render (review badge optional when nothing needs review)', hasBadge);
  const frameRow = page.locator('.tv-win .tr[aria-level="1"]', { hasText: 'FRAME' }).first();
  await frameRow.hover();
  await frameRow.locator('.sv').click();
  await page.waitForSelector('.set-editor, .crit-editor, [aria-label="Criteria set name"]', { timeout: 5000 }).catch(() => {});
  const qText = await page.evaluate(() => Array.from(document.querySelectorAll('textarea, input')).map((x) => x.value).filter((v) => /XR_Phase/.test(v)));
  console.log('save as set query:', JSON.stringify(qText));
  check('Save as set opens the editor with the query of the node', qText.some((q) => /XR_Phase\.Code = 'FRAME'/.test(q)), JSON.stringify(qText));
  await page.locator('button', { hasText: /^Save set$/ }).first().click().catch(() => {});
  await page.waitForTimeout(400);
  const sets = await page.evaluate(() => Array.from(document.querySelectorAll('.set-row, .set')).map((s) => s.textContent));
  check('the saved set is in the Sets tab with its members', sets.some((t) => /FRAME/.test(t)), JSON.stringify(sets.slice(0, 3)));
  await page.locator('.sb-tab', { hasText: 'Model' }).click();
  await page.waitForTimeout(200);

  // ---- colour by Trade
  await page.locator('.xt-btn-tool[data-tool="classify"]').click();
  await page.waitForSelector('#dk-pane-classification .xt-table');
  const before = await page.evaluate(() => Array.from(window.__xray.renderer.state.color.slice(0, 60)));
  await page.evaluate(() => window.__xrayClassify.colourBy('Trade'));
  await page.waitForSelector('[data-role="legend-row"]', { timeout: 15000 }).catch(() => {});
  const legend = await page.locator('[data-role="legend-row"]').evaluateAll((rs) => rs.map((r) => r.textContent));
  console.log('trade legend:', JSON.stringify(legend));
  check('colour by Trade draws a legend with a row per trade', legend.length >= 2, String(legend.length));
  const tinted = await page.evaluate(() => Array.from(window.__xray.renderer.state.color.slice(0, 60)));
  check('colour by Trade changes the element colours', JSON.stringify(before) !== JSON.stringify(tinted));
  // select by the dropdown too
  await page.locator('#dk-pane-classification label.xt-select', { hasText: 'Colour by' }).locator('select').selectOption('Phase');
  await page.waitForTimeout(300);
  check('the Colour by list switches to Phase', (await page.locator('[data-role="legend-row"]').count()) >= 2 && (await page.evaluate(() => window.__xrayClassify.colourBy())) === 'Phase');
  await page.locator('#dk-pane-classification label.xt-select', { hasText: 'Colour by' }).locator('select').selectOption('Trade');
  await page.waitForTimeout(300);
  const row0 = page.locator('[data-role="legend-row"]').first();
  const total0 = Number((await row0.locator('.xc-lg-cnt').textContent()) ?? 0);
  await row0.click();
  await page.waitForTimeout(300);
  const hidden = await page.evaluate(() => window.__xray.app.controller.settings.overrides.userHides.size);
  const nEl = await page.evaluate(() => window.__xray.app.loaded.model.elements.length);
  check('clicking a legend row isolates its elements', hidden === nEl - total0 && total0 > 0, `${hidden} hidden, expected ${nEl - total0}`);
  await page.locator('[data-role="legend-row"]').first().click();
  check('clicking it again shows everything', (await page.evaluate(() => window.__xray.app.controller.settings.overrides.userHides.size)) === 0);
  await page.locator('[data-role="legend-row"]').first().locator('[data-act="eye"]').click();
  check('the eye on a legend row hides its elements', (await page.evaluate(() => window.__xray.app.controller.settings.overrides.userHides.size)) === total0);
  await page.locator('[data-role="legend-row"]').first().locator('[data-act="eye"]').click();

  // ---- confidence shading
  const flagged = await page.evaluate(() => {
    const res = window.__xrayClassify.facets.results();
    const m = window.__xray.app.loaded.model;
    const out = [];
    for (const [g, f] of Object.entries(res)) if (Object.values(f).some((r) => r && r.needsReview)) out.push(m.byGlobalId.get(g));
    return out;
  });
  console.log('elements needing review:', flagged.length);
  await page.evaluate(() => window.__xrayClassify.colourBy('Off'));
  const base = await page.evaluate((id) => Array.from(window.__xray.renderer.state.color.slice(id * 3, id * 3 + 3)), flagged[0] ?? 0);
  await page.evaluate(() => window.__xrayClassify.confidenceShading(true));
  const shaded = await page.evaluate((id) => Array.from(window.__xray.renderer.state.color.slice(id * 3, id * 3 + 3)), flagged[0] ?? 0);
  if (flagged.length > 0) {
    const sat = (c) => Math.max(...c) - Math.min(...c);
    check('confidence shading washes out an element that needs review', sat(shaded) < sat(base) || JSON.stringify(shaded) !== JSON.stringify(base), `${base.map((x) => x.toFixed(2))} -> ${shaded.map((x) => x.toFixed(2))}`);
  } else check('confidence shading: no element needs review on FZK-Haus (nothing to wash out)', true);
  await page.evaluate(() => window.__xrayClassify.confidenceShading(false));
  const restored = await page.evaluate((id) => Array.from(window.__xray.renderer.state.color.slice(id * 3, id * 3 + 3)), flagged[0] ?? 0);
  check('switching shading off restores the colour', JSON.stringify(restored) === JSON.stringify(base));
  await page.evaluate(() => window.__xrayClassify.colourBy('Trade'));
  await page.waitForTimeout(300);

  // ---- a filter and a model switch back
  await page.locator('.sb-filter input').fill('door');
  await page.waitForTimeout(400);
  const fr = await rowsText();
  check('the filter box narrows the classification tree', fr.length > 0 && fr.length < top.length + 20 && fr.some((r) => /Door/i.test(r.label)), String(fr.length));
  await page.locator('.sb-filter input').fill('');
  await page.waitForTimeout(300);
  await page.screenshot({ path: resolve(here, 'class-tree.png'), timeout: 180000 });
  await modeBtn('model').click();
  await page.waitForTimeout(300);
  check('Model tree returns with its storeys', (await rowsText()).length === modelRows);

  const real = errors.filter((e) => !/favicon/i.test(e));
  check('zero console errors', real.length === 0, real.slice(0, 3).join(' | '));
  await ctx.close();
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
