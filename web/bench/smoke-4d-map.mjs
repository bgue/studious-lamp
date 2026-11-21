// Headless smoke for the 4D mapping tool (src/map4d, src/plugins/map4d.ts): the 4D tab in the right sidebar, values, assign by storey / query /
// selection, suggestions and review, coverage and temporary colouring, Save IFC with the 4D option, re-opening the saved file mapped, the stored
// record coming back after a reload, export and import, help keys, the phone sheet.
// Screenshots: bench/4d-map.png (desktop), bench/4d-map-phone.png (phone bottom sheet).
// Usage: SMOKE_PORT=5850 XRAY_VITE_CACHE_DIR=/tmp/xray-vite-map4d node bench/smoke-4d-map.mjs
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { mkdtempSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const port = Number(process.env.SMOKE_PORT ?? 5850);
const tmp = mkdtempSync(join(tmpdir(), 'smoke-4d-map-'));
const FZK = resolve(root, '..', 'models', 'AC20-FZK-Haus.ifc');

let pw;
for (const c of [process.env.PLAYWRIGHT_MODULE, resolve(root, 'node_modules/playwright'), '/opt/node-tools/node_modules/playwright', '/opt/node22/lib/node_modules/playwright'].filter(Boolean)) {
  try { pw = createRequire(import.meta.url)(c); break; } catch { /* next */ }
}
if (!pw) throw new Error('playwright not found; set PLAYWRIGHT_MODULE');

const vite = spawn(resolve(root, 'node_modules/.bin/vite'), ['--config', 'bench/vite.smoke.config.mjs', '--host', '127.0.0.1', '--port', String(port), '--strictPort'], { cwd: root, stdio: ['ignore', 'pipe', 'pipe'] });
let viteLog = '';
vite.stdout.on('data', (d) => (viteLog += d));
vite.stderr.on('data', (d) => (viteLog += d));

let failed = false;
let passed = 0;
const check = (name, ok, detail = '') => { if (!ok) failed = true; else passed++; console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${detail ? ` (${detail})` : ''}`); };
const errors = [];
let browser;

const newPage = async (viewport, tag) => {
  const ctx = await browser.newContext({ viewport, acceptDownloads: true });
  const page = await ctx.newPage();
  page.setDefaultTimeout(180000);
  page.on('console', (m) => { if (m.type() === 'error') errors.push(`[${tag}] ${m.text()}`); });
  page.on('pageerror', (e) => errors.push(`[${tag} pageerror] ${e.message}`));
  await page.addInitScript(() => { delete window.showSaveFilePicker; delete window.showDirectoryPicker; });
  await page.goto(`http://127.0.0.1:${port}/?model=building`);
  await page.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: 180000 });
  const err = await page.evaluate('window.__xrayError');
  if (err) throw new Error(`startup failed: ${err}`);
  await page.waitForFunction('window.__xray4dMap && window.__xrayRightSidebar && window.__xrayIfcSave', null, { timeout: 60000 });
  return { ctx, page };
};

const openFile = async (page, file, label) => {
  await page.evaluate(() => window.__xray.app.panel.controllersRecursive().find((c) => c.property === 'status').setValue(''));
  await page.setInputFiles('#xray-open-file-input', file);
  await page.waitForFunction(() => {
    const s = window.__xray.app.panel.controllersRecursive().find((c) => c.property === 'status').getValue();
    return /^Loaded \d+ elements/.test(s) || /fail|error|cannot|not a valid/i.test(s);
  }, null, { timeout: 180000 });
  const st = await page.evaluate(() => ({ status: window.__xray.app.panel.controllersRecursive().find((c) => c.property === 'status').getValue(), model: window.__xray.app.modelName, n: window.__xray.app.controller.model.elements.length }));
  check(`${label} opens`, /^Loaded/.test(st.status), JSON.stringify(st));
  await page.evaluate(() => window.__xray4dMap.ready());
  return st;
};

try {
  let up = false;
  for (let i = 0; i < 100 && !up; i++) {
    try { up = (await fetch(`http://127.0.0.1:${port}/`)).ok; } catch { await new Promise((r) => setTimeout(r, 200)); }
  }
  if (!up) throw new Error('vite did not start:\n' + viteLog);
  browser = await pw.chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });

  // ---------------------------------------------------------------- desktop
  const { ctx, page } = await newPage({ width: 1600, height: 950 }, 'desktop');
  const tabs = await page.locator('#dock .dk-tab').allTextContents();
  check('the right sidebar has a 4D tab (order 50) after Script', JSON.stringify(tabs) === JSON.stringify(['Properties', 'Classification', 'Parameters', 'Script', '4D']), tabs.join());
  const opened = await openFile(page, FZK, 'AC20-FZK-Haus.ifc');
  await page.evaluate(() => window.__xray4dMap.open());
  await page.waitForSelector('#dk-pane-4d .x4');
  await page.waitForFunction(() => document.getElementById('dock').getBoundingClientRect().width >= 400, null, { timeout: 20000 }).catch(() => undefined);
  const st = await page.evaluate(() => ({ s: window.__xrayRightSidebar.state(), w: document.getElementById('dock').getBoundingClientRect().width, v: document.getElementById('dock').style.getPropertyValue('--dk-w'), act: document.querySelector('#dock .dk-tab.active')?.textContent }));
  check('the 4D tab opens at 420 px', st.s.tab === '4d' && !st.s.collapsed && st.v === '420px' && st.w >= 400 && st.w <= 440, JSON.stringify(st));

  // values: storeys, default trades
  const vals = await page.evaluate(() => window.__xray4dMap.values());
  const storeys = await page.evaluate(() => window.__xray.app.controller.model.storeys.map((s) => s.name));
  check('locations are seeded from the storey names', storeys.length > 0 && storeys.every((s) => vals.location.includes(s)), `${vals.location.join('|')}`);
  check('the default trade list is there', ['CONC', 'STEEL', 'MASONRY', 'FACADE', 'ROOF', 'MEP-MECH', 'MEP-ELEC', 'MEP-PLUMB', 'FINISHES', 'SITE'].every((t) => vals.trade.includes(t)), vals.trade.join());
  check('the Values list is drawn with a row per value', (await page.locator('#dk-pane-4d [data-x4=value-list] .x4-item').count()) === vals.location.length);

  // add / rename / delete a value through the UI
  await page.locator('#dk-pane-4d input[aria-label="New value"]').fill('Roof Terrace');
  await page.locator('#dk-pane-4d button', { hasText: /^Add$/ }).first().click();
  check('a typed value is added to the list', (await page.evaluate(() => window.__xray4dMap.values().location)).includes('Roof Terrace'));
  const row = page.locator('#dk-pane-4d [data-value="Roof Terrace"] input[aria-label="Value name"]');
  await row.fill('Terrace');
  await row.press('Enter');
  check('a value is renamed', (await page.evaluate(() => window.__xray4dMap.values().location)).includes('Terrace'));
  await page.locator('#dk-pane-4d [data-value="Terrace"] button[aria-label="Delete value"]').click();
  check('an unused value is deleted', !(await page.evaluate(() => window.__xray4dMap.values().location)).includes('Terrace'));

  // assign: location from every storey in one click
  const before = await page.evaluate(() => window.__xray4dMap.coverage());
  check('nothing is assigned at the start', before.attributes.location.assigned === 0 && before.total === opened.n, JSON.stringify(before.attributes.location));
  await page.locator('#dk-pane-4d button', { hasText: 'Every storey' }).click();
  const afterLoc = await page.evaluate(() => ({ c: window.__xray4dMap.coverage(), withStorey: window.__xray.app.controller.model.elements.filter((e) => e.storey !== null).length }));
  check('Every storey gives each element its storey as location', afterLoc.c.attributes.location.assigned === afterLoc.withStorey && afterLoc.withStorey > 0, JSON.stringify(afterLoc.c.attributes.location.values));

  // assign by selection
  await page.locator('#dk-pane-4d .x4-seg button[data-attr=zone]').click();
  await page.evaluate(() => { const a = window.__xray.app; a.selectIds([0, 1, 2]); });
  await page.waitForFunction(() => /3 selected/.test(document.querySelector('#dk-pane-4d .x4-sec .x4-dim')?.parentElement?.textContent ?? '') || document.body.textContent.includes('3 selected'));
  await page.locator('#dk-pane-4d input[aria-label="Value to assign"]').fill('Zone A');
  await page.locator('#dk-pane-4d button', { hasText: /^Selection$/ }).click();
  check('the selection gets the zone', (await page.evaluate(() => window.__xray4dMap.coverage().attributes.zone.assigned)) === 3);

  // assign by query: live count + preview highlight
  const colorBefore = await page.evaluate(() => Array.from(window.__xray.app.renderer.state.color.slice(0, 3000)));
  await page.locator('#dk-pane-4d input[aria-label="Criteria query"]').fill("class = 'IfcWindow'");
  const wantWindows = await page.evaluate(() => window.__xray.app.controller.model.elements.filter((e) => e.ifcClass === 'IfcWindow').length);
  await page.waitForFunction((n) => new RegExp(`${n} match`).test(document.querySelector('#dk-pane-4d [data-sec=assign]')?.textContent ?? ''), wantWindows, { timeout: 10000 });
  check('the query shows a live count', wantWindows > 0, `${wantWindows} windows`);
  const colorPreview = await page.evaluate(() => Array.from(window.__xray.app.renderer.state.color.slice(0, 3000)));
  check('the matching elements are highlighted while the query is typed', colorPreview.some((v, i) => v !== colorBefore[i]));
  await page.locator('#dk-pane-4d input[aria-label="Value to assign"]').fill('Zone W');
  await page.locator('#dk-pane-4d button', { hasText: /^Query$/ }).click();
  check('the query assignment sets the zone on every match', (await page.evaluate(() => window.__xray4dMap.coverage().attributes.zone.values.find((v) => v.value === 'Zone W')?.count)) === wantWindows);
  const colorAfter = await page.evaluate(() => Array.from(window.__xray.app.renderer.state.color.slice(0, 3000)));
  check('the preview highlight is gone after the assignment', colorAfter.every((v, i) => v === colorBefore[i]));

  // suggestions: trades, review list, accept above
  await page.locator('#dk-pane-4d [data-sec=suggest] > summary').click();
  await page.locator('#dk-pane-4d button', { hasText: /^Suggest$/ }).click();
  await page.waitForSelector('#dk-pane-4d [data-x4=proposals] .x4-prop');
  const props = await page.evaluate(() => window.__xray4dMap.proposals());
  check('proposals carry confidence, reasons and status proposed', props.length > 0 && props.every((p) => p.status === 'proposed' && p.confidence > 0 && p.reasons.length > 0), `${props.length} proposals`);
  check('suggestions cover locations (already assigned: none) and trades', props.some((p) => p.attribute === 'trade') && !props.some((p) => p.attribute === 'location'));
  const first = props.find((p) => p.attribute === 'trade');
  await page.locator(`#dk-pane-4d .x4-prop[data-id="${first.id}"] button[aria-label=Reject]`).click();
  check('Reject takes the proposal off the list', !(await page.evaluate((id) => window.__xray4dMap.proposals().some((p) => p.id === id), first.id)));
  await page.locator('#dk-pane-4d input[aria-label="Confidence limit"]').fill('0.65');
  await page.locator('#dk-pane-4d button', { hasText: 'Accept all above' }).click();
  const cov = await page.evaluate(() => window.__xray4dMap.coverage());
  check('Accept all above makes trades current', cov.attributes.trade.assigned > 0 && cov.attributes.trade.assigned + cov.attributes.trade.unassigned === cov.total, JSON.stringify(cov.attributes.trade.values.slice(0, 4)));
  const left = await page.evaluate(() => window.__xray4dMap.proposals());
  if (left.length) {
    await page.locator(`#dk-pane-4d .x4-prop[data-id="${left[0].id}"] button[aria-label=Accept]`).click();
    check('Accept makes one proposal current', !(await page.evaluate((id) => window.__xray4dMap.proposals().some((p) => p.id === id), left[0].id)));
  }

  // coverage and colouring
  await page.locator('#dk-pane-4d [data-sec=coverage] > summary').click();
  check('Coverage lists the three attributes with counts', (await page.locator('#dk-pane-4d [data-x4=coverage] tr[data-attr]').count()) === 3);
  const unsel = await page.evaluate(() => window.__xray4dMap.selectUnassigned('zone'));
  const selNow = await page.evaluate(() => window.__xray.app.selection.length);
  check('Select without selects the elements that have no zone', unsel > 0 && selNow === unsel, `${unsel}`);
  const base = await page.evaluate(() => Array.from(window.__xray.app.renderer.state.color));
  await page.locator('#dk-pane-4d select[aria-label="Colour the model by"]').selectOption('trade');
  const coloured = await page.evaluate(() => Array.from(window.__xray.app.renderer.state.color));
  check('Colour by trade recolours the model', coloured.some((v, i) => v !== base[i]));
  await page.screenshot({ path: resolve(here, '4d-map.png') });
  await page.locator('#dock .dk-tab', { hasText: 'Properties' }).click();
  const leaving = await page.evaluate(() => Array.from(window.__xray.app.renderer.state.color));
  check('the colouring is removed when the tab is left', leaving.every((v, i) => v === base[i]));
  await page.locator('#dock .dk-tab', { hasText: '4D' }).click();
  check('and comes back with the tab', (await page.evaluate(() => Array.from(window.__xray.app.renderer.state.color))).some((v, i) => v !== base[i]));
  await page.locator('#dk-pane-4d select[aria-label="Colour the model by"]').selectOption('');

  // help keys on every control
  const help = await page.evaluate(() => {
    const ctl = [...document.querySelectorAll('#dk-pane-4d button, #dk-pane-4d input, #dk-pane-4d select, #dk-pane-4d summary')];
    const missing = ctl.filter((c) => !c.getAttribute('data-help-key') || !window.__xrayHelp.lookup(c.getAttribute('data-help-key'))).map((c) => `${c.tagName} ${c.getAttribute('aria-label') ?? c.textContent} ${c.getAttribute('data-help-key')}`);
    return { n: ctl.length, missing };
  });
  check('every control of the 4D tab has help text', help.n > 20 && help.missing.length === 0, JSON.stringify(help.missing.slice(0, 5)));

  // save into the IFC
  const mapBefore = await page.evaluate(() => [...window.__xray4dMap.saveMap()].map(([g, v]) => [g, v]));
  await page.evaluate(() => window.__xrayIfcSave.open());
  const dlg = page.locator('.xis-box');
  await dlg.waitFor();
  const box = dlg.locator('label.xis-check', { hasText: 'Include 4D location, trade and zone' });
  check('the Save IFC dialog has the 4D box, on when there are assignments', (await box.count()) === 1 && (await box.locator('input').isChecked()));
  const planOn = await page.evaluate(() => window.__xrayIfcSave.plan());
  check('the plan counts the elements that get Xray_4D', planOn.fourDElements === mapBefore.length && planOn.fourDElements > 0, `${planOn.fourDElements}`);
  const dlp = page.waitForEvent('download');
  await dlg.locator('button.primary').click();
  const dl = await dlp;
  const outPath = join(tmp, dl.suggestedFilename());
  await dl.saveAs(outPath);
  const out = readFileSync(outPath).toString('latin1');
  check('the saved file holds the Xray_4D set with Location, Trade and Zone', out.includes("'Xray_4D'") && out.includes("'Location'") && out.includes("'Trade'") && out.includes("'Zone'") && out.includes("IFCLABEL('Zone A')"));
  await page.waitForFunction(() => /Saved AC20/.test(document.querySelector('.xis-box')?.textContent ?? ''));
  await box.locator('input').uncheck();
  const planOff = await page.evaluate(() => window.__xrayIfcSave.plan({ includeFourD: false }));
  check('with the box off nothing from 4D is planned', planOff.fourDElements === 0);
  await dlg.locator('button', { hasText: 'Close' }).click();

  // reopen the saved file: mapped again
  await page.evaluate(() => window.__xray4dMap.flush());
  const reopened = await openFile(page, outPath, 'the saved file');
  const back = await page.evaluate(() => ({ list: window.__xray4dMap.assignments(), map: [...window.__xray4dMap.saveMap()].map(([g, v]) => [g, v]) }));
  check('the saved model reopens mapped: assignments from the properties, source property', reopened.n === opened.n && back.list.length > 0 && back.list.every((a) => a.source === 'property' && a.status === 'accepted'), `${back.list.length}`);
  const canon = (v) => Object.fromEntries(Object.entries(v).sort());
  const norm = (m) => JSON.stringify([...m].map(([g, v]) => [g, canon(v)]).sort((a, b) => a[0].localeCompare(b[0])));
  const diff = (() => { const a = new Map(back.map), b = new Map(mapBefore); const out = []; for (const [g, v] of b) if (JSON.stringify(canon(a.get(g) ?? {})) !== JSON.stringify(canon(v))) out.push(`${g}: ${JSON.stringify(v)} vs ${JSON.stringify(a.get(g))}`); return out; })();
  check('the reopened values equal the saved ones', diff.length === 0 && back.map.length === mapBefore.length, `${diff.length} differ: ${diff.slice(0, 3).join(' | ')}; ${back.map.length} vs ${mapBefore.length}`);

  // reload: the stored record comes back for the same model
  await page.evaluate(() => window.__xray4dMap.flush());
  await page.reload();
  await page.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: 180000 });
  await page.waitForFunction('window.__xray4dMap', null, { timeout: 60000 });
  await openFile(page, FZK, 'AC20-FZK-Haus.ifc again');
  const stored = await page.evaluate(() => ({ n: window.__xray4dMap.assignments().length, manual: window.__xray4dMap.assignments().filter((a) => a.source === 'manual' && a.status === 'accepted').length, map: [...window.__xray4dMap.saveMap()].map(([g, v]) => [g, v]) }));
  check('after a reload the assignments of the model come back from IndexedDB', stored.manual > 0 && norm(stored.map) === norm(mapBefore), `${stored.n} records`);

  // export and import
  const exported = await page.evaluate(() => window.__xray4dMap.exportJson());
  const ds = JSON.parse(exported);
  check('the export is a LinkDataset with model, model_elements and assignments, and a marked placeholder schedule', ds.model.identity_key && ds.model_elements.length > 0 && ds.assignments.length > 0 && /no schedule/.test(ds.schedule.project) && !('activities' in ds) && !exported.includes('reviewed_by'));
  await page.evaluate(() => window.__xray4dMap.reset());
  check('Reset empties the assignments', (await page.evaluate(() => window.__xray4dMap.coverage().attributes.location.assigned)) === 0);
  const imp = await page.evaluate((t) => { const r = window.__xray4dMap.importJson(t); return { read: r.read, added: r.added, problems: r.problems.length }; }, exported);
  const afterImp = await page.evaluate(() => [...window.__xray4dMap.saveMap()].map(([g, v]) => [g, v]));
  check('import brings the same values back', imp.read === ds.assignments.length && imp.problems === 0 && norm(afterImp) === norm(mapBefore), JSON.stringify(imp));
  const again = await page.evaluate((t) => { const r = window.__xray4dMap.importJson(t); return { added: r.added, updated: r.updated }; }, exported);
  check('importing the same file again changes nothing', again.added === 0 && again.updated === 0);
  await page.evaluate(() => window.__xray4dMap.flush());
  await ctx.close();

  // ---------------------------------------------------------------- phone
  const phone = await newPage({ width: 390, height: 800 }, 'phone');
  const pp = phone.page;
  await openFile(pp, FZK, 'AC20-FZK-Haus.ifc (phone)');
  await pp.evaluate(() => window.__xray4dMap.open());
  await pp.waitForSelector('#dk-pane-4d .x4', { state: 'visible' });
  await pp.waitForTimeout(500);
  const lay = await pp.evaluate(() => {
    const d = document.getElementById('dock').getBoundingClientRect();
    const p = document.querySelector('#dk-pane-4d .x4');
    const s = document.getElementById('sidebar').getBoundingClientRect();
    return { dockW: d.width, dockTop: d.top, vh: innerHeight, vw: innerWidth, scrollW: p.scrollWidth, clientW: p.clientWidth, leftOpen: !document.body.classList.contains('sb-collapsed'), sideW: s.width, tab: window.__xrayRightSidebar.state() };
  });
  check('on a phone the 4D tab is the bottom sheet, full width, with no sideways scroll', lay.tab.tab === '4d' && lay.tab.phone && lay.dockW >= lay.vw - 40 && lay.dockTop > 0 && lay.scrollW <= lay.clientW + 1 && !lay.leftOpen, JSON.stringify(lay));
  await pp.locator('#dk-pane-4d button', { hasText: 'Every storey' }).click();
  check('the phone sheet assigns too', (await pp.evaluate(() => window.__xray4dMap.coverage().attributes.location.assigned)) > 0);
  await pp.screenshot({ path: resolve(here, '4d-map-phone.png') });
  await phone.ctx.close();

  const real = errors.filter((e) => !/favicon|Failed to load resource.*404/i.test(e));
  check('no console errors', real.length === 0, real.slice(0, 3).join(' | '));
} catch (e) {
  failed = true;
  console.log('FAIL', e && e.stack ? e.stack : e);
} finally {
  await browser?.close().catch(() => undefined);
  vite.kill();
}
console.log(`${passed} checks passed${failed ? ', FAILED' : ''}`);
process.exit(failed ? 1 : 0);
