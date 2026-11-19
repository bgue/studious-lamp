// Headless smoke test for the right sidebar (src/ui/rightSidebar.ts, src/plugins/rightSidebar.ts): tabs, properties that follow the
// selection, the Classification tab opened by the action tool.classify with the selected element's result, the Parameters tab (lil-gui),
// the persisted fold, the phone bottom sheet (never together with the left sidebar), the addTab API and the console.
// Screenshots: bench/right-sidebar.png (desktop, Classification tab), bench/right-sidebar-phone.png (the sheet on a phone).
// Usage: SMOKE_PORT=5745 node bench/smoke-right-sidebar.mjs
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const port = Number(process.env.SMOKE_PORT ?? 5745);

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

let browser;
let exitCode = 0;
const errors = [];

async function openPage(viewport, tag) {
  const context = await browser.newContext({ viewport });
  const page = await context.newPage();
  page.on('console', (m) => { if (m.type() === 'error' || m.type() === 'warning') errors.push(`[${tag} ${m.type()}] ${m.text()}`); });
  page.on('pageerror', (e) => errors.push(`[${tag} pageerror] ${e.message}`));
  await page.goto(`http://127.0.0.1:${port}/?model=building`);
  await page.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: 120000 });
  const err = await page.evaluate('window.__xrayError');
  if (err) { errors.push(`[${tag} app] ${err}`); exitCode = 1; }
  await page.waitForFunction('window.__xrayRightSidebar && window.__xrayClassify && window.__xraySearch && window.__xraySearch.indexReady()', null, { timeout: 60000 });
  return { context, page };
}

/** Select the first element of a class through the app (the same path as a click). */
const selectClass = (page, re) => page.evaluate((src) => {
  const a = window.__xray.app;
  const id = a.controller.model.elements.findIndex((e) => new RegExp(src).test(e.ifcClass));
  a.selectIds(id < 0 ? [] : [id]);
  return id < 0 ? null : a.controller.model.elements[id].ifcClass;
}, re.source);
const propText = (page, field) => page.evaluate((f) => document.querySelector(`#dk-pane-properties .props-grid dd[data-field="${f}"] .pv-t`)?.textContent ?? null, field);
const runPalette = async (page, text) => {
  await page.keyboard.press('Control+Shift+k');
  await page.waitForSelector('.kx-palette');
  await page.keyboard.type(text);
  await page.waitForTimeout(300);
  await page.keyboard.press('Enter');
  await page.waitForTimeout(500);
};

try {
  await waitForServer();
  browser = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });

  // ---------------------------------------------------------------- desktop
  const { context, page } = await openPage({ width: 1600, height: 900 }, 'desktop');

  // tabs
  const tabs = await page.locator('#dock .dk-tab').allTextContents();
  check('the right sidebar has the tabs Properties, Classification and Parameters, in that order', JSON.stringify(tabs) === JSON.stringify(['Properties', 'Classification', 'Parameters']), JSON.stringify(tabs));
  const st0 = await page.evaluate(() => window.__xrayRightSidebar.state());
  check('it is open on Properties by default', !st0.collapsed && st0.tab === 'properties' && (await page.locator('#dock .dk-tab.active').textContent()) === 'Properties', JSON.stringify(st0));
  check('the left sidebar has lost its properties block and keeps Model, Sets, Views, Issues', (await page.locator('#sidebar .props').count()) === 0 && (await page.locator('#sidebar .sb-tab').allTextContents()).join() === 'Model,Sets,Views,Issues');

  // properties follow the selection
  check('no selection: "No selection" is shown', /No selection/.test(await page.locator('#dk-pane-properties .props-empty').textContent()));
  const duct = await selectClass(page, /Duct/);
  await page.waitForFunction(() => /Duct/.test(document.querySelector('#dk-pane-properties .props-grid dd[data-field="ifcClass"] .pv-t')?.textContent ?? ''), null, { timeout: 8000 });
  check('selecting a duct shows its class, storey and a GlobalId', (await propText(page, 'ifcClass')) === duct && !!(await propText(page, 'storey')) && (await propText(page, 'globalId')).length > 10, `${duct} ${await propText(page, 'globalId')}`);
  const wall = await selectClass(page, /^IfcWall/);
  await page.waitForFunction((w) => document.querySelector('#dk-pane-properties .props-grid dd[data-field="ifcClass"] .pv-t')?.textContent === w, wall, { timeout: 8000 });
  check('selecting a wall changes the properties with it', (await propText(page, 'ifcClass')) === wall, wall);
  check('Copy GlobalId is enabled and the property list is there', !(await page.locator('#dk-pane-properties .props-head .btn').isDisabled()) && (await page.locator('#dk-pane-properties .props-list').count()) === 1);
  await page.evaluate(() => {
    const a = window.__xray.app;
    a.selectIds([a.controller.model.elements.findIndex((e) => /^IfcWall/.test(e.ifcClass)), a.controller.model.elements.findIndex((e) => /Duct/.test(e.ifcClass))]);
  });
  await page.waitForFunction(() => /\+ 1 more selected/.test(document.querySelector('#dk-pane-properties .props-more')?.textContent ?? ''), null, { timeout: 8000 }).catch(() => undefined);
  check('a multi-selection says how many more are selected', /\+ 1 more selected/.test(await page.locator('#dk-pane-properties .props-more').textContent()));

  // Classification: open with the action tool.classify (through the command palette), then the selected element's result
  await selectClass(page, /Duct/);
  await page.evaluate(() => window.__xrayClassify.classify('all'));
  await runPalette(page, 'Tool: Classify');
  const st1 = await page.evaluate(() => window.__xrayRightSidebar.state());
  check('the action tool.classify opens the Classification tab', !st1.collapsed && st1.tab === 'classification' && (await page.locator('#dk-pane-classification').isVisible()), JSON.stringify(st1));
  check('the strip button of the Classify tool shows it open and no drawer opened', (await page.locator('.xt-btn-tool[data-tool="classify"].open').count()) === 1 && (await page.locator('.xt-drawer:not(.hidden)').count()) === 0);
  await page.waitForSelector('#dk-pane-classification .xcs [data-role=discipline]', { timeout: 10000 });
  const card = await page.evaluate(() => ({
    title: document.querySelector('.xcs-title')?.textContent,
    disc: document.querySelector('.xcs [data-role=discipline]')?.textContent,
    sub: document.querySelector('.xcs [data-role=sub]')?.textContent,
    src: document.querySelector('.xcs [data-role=source]')?.textContent,
    decision: document.querySelector('.xcs [data-role=decision]')?.textContent,
    acts: [...document.querySelectorAll('.xcs-acts [data-act]')].map((b) => b.dataset.act),
    expected: window.__xrayClassify.results().find((r) => r.id === window.__xray.app.controller.model.elements[window.__xray.app.selection[0]].globalId)?.discipline.code,
  }));
  check('the selected element\'s result is shown at the top: class, discipline, source and "No decision yet"', /Duct/.test(card.title) && card.disc.startsWith(card.expected) && /rule/.test(card.src) && /No decision yet/.test(card.decision), JSON.stringify(card));
  check('with Accept, Change and Unsure controls', ['accept', 'change', 'unsure'].every((a) => card.acts.includes(a)), card.acts.join());
  await page.locator('.xcs-acts [data-act=accept]').click();
  await page.waitForSelector('.xcs [data-role=decision].xcs-ok');
  const pend = await page.evaluate(() => ({ text: document.querySelector('.xcs [data-role=decision]').textContent, n: window.__xrayClassify.review.pending().length, commit: !!document.querySelector('.xcs-acts [data-act=commit]') }));
  check('Accept records a pending confirmation through the review service, and Commit appears', /Pending: confirmed/.test(pend.text) && pend.n === 1 && pend.commit, JSON.stringify(pend));
  await page.evaluate(() => window.__xrayClassify.review.setReviewer('Smoke'));
  await page.evaluate(() => window.__xrayClassify.review.commit('smoke'));
  await page.waitForFunction(() => /Decision: confirmed/.test(document.querySelector('.xcs [data-role=decision]')?.textContent ?? ''), null, { timeout: 8000 });
  check('after the commit the card says "Decision: confirmed by Smoke"', /Decision: confirmed.*Smoke/.test(await page.locator('.xcs [data-role=decision]').textContent()));
  // a change of selection updates the card
  await selectClass(page, /^IfcWall/);
  await page.waitForFunction(() => /Wall/.test(document.querySelector('.xcs-title')?.textContent ?? ''), null, { timeout: 8000 });
  check('selecting another element updates the card', /Wall/.test(await page.locator('.xcs-title').textContent()));
  // the review walk opens in the tab
  await page.evaluate(() => window.__xrayClassify.walk.open());
  await page.waitForSelector('#dk-pane-classification .xrw.xrw-in', { timeout: 8000 });
  check('the review walk lives in the Classification tab (not over the view) and replaces its content', (await page.locator('#stage .xrw').count()) === 0 && !(await page.locator('#dk-pane-classification .xcs').isVisible()));
  await page.evaluate(() => window.__xrayClassify.walk.close());
  await page.waitForFunction(() => document.querySelector('.xcs')?.hidden === false, null, { timeout: 5000 });
  check('closing the walk brings the panel back', await page.locator('#dk-pane-classification .xcs').isVisible());
  // the Shape section: the vector option, its explanation, a token estimate and a preview
  await page.evaluate(() => window.__xrayClassify.configure({ provider: 'jev' }));
  await selectClass(page, /Duct/);
  await page.waitForFunction(() => [...document.querySelectorAll('#dk-pane-classification .xt-check')].find((l) => /vector/.test(l.textContent))?.querySelector('input')?.disabled === false && document.querySelector('#dk-pane-classification .xc-geo img') !== null, null, { timeout: 15000 });
  const shape = await page.evaluate(() => ({
    label: [...document.querySelectorAll('#dk-pane-classification .xt-check')].map((l) => l.textContent),
    tokens: /about \d+ tokens/.test(document.querySelector('#dk-pane-classification [data-role=geo-explain]')?.parentElement?.textContent ?? ''),
    svgDisabled: [...document.querySelectorAll('#dk-pane-classification .xt-check')].find((l) => /vector/.test(l.textContent))?.querySelector('input')?.disabled,
    img: document.querySelectorAll('#dk-pane-classification .xc-geo img').length,
  }));
  check('Shape section: "Send shape as vector (SVG)" and "Send shape as numbers" with a preview and a token estimate (jev)', shape.label.some((t) => /Send shape as vector \(SVG\)/.test(t)) && shape.label.some((t) => /Send shape as numbers/.test(t)) && shape.tokens && shape.img >= 2 && shape.svgDisabled === false, JSON.stringify(shape));
  await page.evaluate(() => window.__xrayClassify.configure({ provider: 'decision', geometryVector: true }));
  await page.waitForFunction(() => document.querySelector('#dk-pane-classification [data-role=vec-line]')?.hidden === false && [...document.querySelectorAll('#dk-pane-classification .xt-check')].find((l) => /vector/.test(l.textContent))?.querySelector('input')?.disabled === true, null, { timeout: 15000 });
  const vec = await page.evaluate(() => ({ line: document.querySelector('#dk-pane-classification [data-role=vec-line]').textContent, svgDisabled: [...document.querySelectorAll('#dk-pane-classification .xt-check')].find((l) => /vector/.test(l.textContent)).querySelector('input').disabled }));
  check('the numbers line is previewed for the decision provider, where the SVG switch is disabled', /sorted; /.test(vec.line) && /elongation/.test(vec.line) && vec.svgDisabled === true, vec.line);
  await page.evaluate(() => window.__xrayClassify.configure({ provider: 'off', geometryVector: false }));
  await page.waitForTimeout(300);
  await page.screenshot({ path: resolve(here, 'right-sidebar.png'), timeout: 120000 });

  // Parameters tab: the lil-gui panel
  await page.locator('#dock .dk-tab', { hasText: 'Parameters' }).click();
  await page.waitForTimeout(300);
  const par = await page.evaluate(() => {
    const gui = document.querySelector('.lil-gui.lil-root');
    const r = gui.getBoundingClientRect();
    const d = document.getElementById('dock').getBoundingClientRect();
    return { parent: gui.parentElement.id, visible: r.width > 100 && r.height > 100, inside: r.left >= d.left - 1 && r.right <= d.right + 1, fixed: getComputedStyle(gui).position === 'fixed' };
  });
  check('the Parameters tab holds the lil-gui panel, in the column and not floating', par.parent === 'dk-pane-parameters' && par.visible && par.inside && !par.fixed, JSON.stringify(par));
  await page.evaluate(() => { document.querySelector('.lil-gui.lil-root > .lil-title')?.click(); document.querySelector('.lil-gui.lil-root > .lil-title')?.click(); });
  const folders = await page.evaluate(() => window.__xray.app.panel.folders.length);
  check('the panel has its folders and a control can be driven', folders > 5 && (await page.evaluate(() => { const c = window.__xray.app.panel.controllersRecursive().find((x) => x.property === 'xray'); return !!c; })) );
  await page.keyboard.press('Control+Shift+k'); // the palette is not the search bar: close it again
  await page.keyboard.press('Escape');

  // search jumps to a setting: the Parameters tab opens even when another tab is shown
  await page.locator('#dock .dk-tab', { hasText: 'Properties' }).click();
  await page.evaluate(() => { const bar = window.__xraySearch; void bar; });
  await page.keyboard.press('/');
  await page.locator('.ab-input').fill('');
  await page.keyboard.type('bufferBase');
  await page.waitForTimeout(500);
  await page.keyboard.press('Enter');
  await page.waitForTimeout(500);
  check('jumping to a setting from the search bar shows the Parameters tab', (await page.evaluate(() => window.__xrayRightSidebar.state().tab)) === 'parameters');

  // collapse persists
  await page.mouse.click(700, 450);
  await page.keyboard.press(']');
  await page.waitForFunction(() => document.body.classList.contains('dk-collapsed'));
  const saved = await page.evaluate(() => JSON.parse(localStorage.getItem('xray.dock')));
  check('"]" folds the sidebar and the state (collapsed and tab) is stored in localStorage', saved.collapsed === true && saved.tab === 'parameters', JSON.stringify(saved));
  await page.reload();
  await page.waitForFunction('window.__xrayReady === true && window.__xrayRightSidebar', null, { timeout: 120000 });
  const after = await page.evaluate(() => ({ collapsed: document.body.classList.contains('dk-collapsed'), w: document.getElementById('dock').getBoundingClientRect().width, st: window.__xrayRightSidebar.state() }));
  check('after a reload it is still folded (a 28 px rail) on the same tab', after.collapsed && Math.round(after.w) === 28 && after.st.tab === 'parameters', JSON.stringify(after));
  await page.click('#dock .dk-toggle');
  await page.waitForFunction(() => !document.body.classList.contains('dk-collapsed'));
  check('the chevron opens it again', !(await page.evaluate(() => window.__xrayRightSidebar.state().collapsed)));

  // the addTab API
  const api = await page.evaluate(async () => {
    const calls = { mount: 0, vis: [] };
    const tab = window.__xrayRightSidebar.addTab({
      id: 'revision-test', label: 'Revision', order: 40, width: 360,
      mount(pane, ctx) {
        calls.mount++;
        pane.append(Object.assign(document.createElement('div'), { id: 'rev-content', textContent: 'Revision walkthrough' }));
        ctx.onVisible((v) => calls.vis.push(v));
        ctx.setBadge('2');
        return () => { calls.cleaned = true; };
      },
    });
    const before = { mounted: calls.mount, ids: window.__xrayRightSidebar.tabs() };
    tab.show();
    await new Promise((r) => setTimeout(r, 400));
    const shown = { mounted: calls.mount, visible: tab.visible(), content: document.getElementById('rev-content')?.textContent, badge: document.querySelector('#dock .dk-tab[data-tab="revision-test"] .dk-badge')?.textContent, w: document.getElementById('dock').style.getPropertyValue('--dk-w'), active: window.__xrayRightSidebar.state().tab };
    window.__xrayRightSidebar.open('properties');
    await new Promise((r) => setTimeout(r, 200));
    const dup = window.__xrayRightSidebar.addTab({ id: 'revision-test', label: 'X', mount() {} });
    const hidden = calls.vis.slice();
    tab.remove();
    return { before, shown, hidden, ids: window.__xrayRightSidebar.tabs(), cleaned: calls.cleaned === true, dupSame: dup.id === 'revision-test' };
  });
  check('addTab: the tab is listed after the built-in ones and mounts lazily on the first show', JSON.stringify(api.before.ids) === JSON.stringify(['properties', 'classification', 'parameters', 'revision-test']) && api.before.mounted === 0 && api.shown.mounted === 1, JSON.stringify(api.before));
  check('addTab: show() opens it with its content, badge and width; the visibility callback runs', api.shown.visible && api.shown.content === 'Revision walkthrough' && api.shown.badge === '2' && api.shown.w === '360px' && api.shown.active === 'revision-test' && api.hidden[0] === true && api.hidden.at(-1) === false, JSON.stringify(api));
  check('addTab: a known id returns the same tab, and remove() runs the cleanup and takes the tab away', api.dupSame && api.cleaned && !api.ids.includes('revision-test'), JSON.stringify(api.ids));

  // the overlay reserve: the column beside the canvas covers nothing, and the edge chrome counts it
  const ov = await page.evaluate(() => {
    const c = document.getElementById('c').getBoundingClientRect();
    const d = document.getElementById('dock').getBoundingClientRect();
    return { besideCanvas: d.left >= c.right - 1, w: Math.round(d.width) };
  });
  check('on a wide screen the column sits beside the canvas (nothing of the view is covered)', ov.besideCanvas && (await page.evaluate(() => window.__xrayRightSidebar.reserved().every((r) => r.x + r.w <= document.getElementById('c').clientWidth + 1))), JSON.stringify(ov));
  await context.close();

  // ---------------------------------------------------------------- phone
  const ph = await openPage({ width: 360, height: 740 }, 'phone');
  const p = ph.page;
  const rects = () => p.evaluate(() => {
    const r = (q) => { const e = document.querySelector(q); const b = e.getBoundingClientRect(); return { x: b.left, y: b.top, w: b.width, h: b.height, r: b.right, b: b.bottom }; };
    return { dock: r('#dock'), sb: r('#sidebar'), vw: innerWidth, vh: innerHeight, dkCollapsed: document.body.classList.contains('dk-collapsed'), sbCollapsed: document.body.classList.contains('sb-collapsed'), scrollW: document.documentElement.scrollWidth };
  });
  let R = await rects();
  check('phone: both sidebars start folded (rails)', R.dkCollapsed && R.sbCollapsed && Math.round(R.dock.w) === 28 && Math.round(R.sb.w) === 28, JSON.stringify([R.dock.w, R.sb.w]));
  await p.evaluate(() => document.querySelector('#dock .dk-toggle').click());
  await p.waitForFunction(() => document.getElementById('dock').getBoundingClientRect().height < 600 && document.getElementById('dock').getBoundingClientRect().width > 200, null, { timeout: 15000 });
  R = await rects();
  check('phone: the right sidebar opens as a bottom sheet with the same tabs', R.dock.w > 300 && R.dock.h > 150 && R.dock.h < R.vh * 0.62 && R.dock.b <= R.vh && R.dock.b > R.vh - 40 && (await p.locator('#dock .dk-tab').count()) === 3, JSON.stringify(R.dock));
  check('phone: no horizontal page scroll with the sheet open', R.scrollW <= R.vw + 1, `${R.scrollW} vs ${R.vw}`);
  // the overlay reserve counts the sheet: one reserved rect covers it (canvas pixels), so labels, the gizmo and the drawing toolbar keep clear of it
  await p.waitForTimeout(600);
  const res = await p.evaluate(() => {
    const d = document.getElementById('dock').getBoundingClientRect();
    const c = document.getElementById('c').getBoundingClientRect();
    const want = { x: d.left - c.left, y: d.top - c.top, w: d.width, h: d.height };
    const hit = window.__xrayRightSidebar.reserved().find((r) => Math.abs(r.x - want.x) < 2 && Math.abs(r.y - want.y) < 2 && Math.abs(r.w - want.w) < 2 && Math.abs(r.h - want.h) < 2);
    const g = document.getElementById('xray-gizmo')?.getBoundingClientRect();
    const clear = !g || g.right <= d.left + 1 || g.left >= d.right - 1 || g.bottom <= d.top + 1 || g.top >= d.bottom - 1;
    return { hit: !!hit, gizmoClear: clear };
  });
  check('phone: the overlay reserve (ov.reserve) holds the sheet and the gizmo is clear of it', res.hit && res.gizmoClear, JSON.stringify(res));
  await p.evaluate(() => document.querySelector('#sidebar .sb-toggle').click());
  await p.waitForFunction(() => !document.body.classList.contains('sb-collapsed'), null, { timeout: 8000 });
  await p.waitForFunction(() => document.body.classList.contains('dk-collapsed'), null, { timeout: 8000 });
  R = await rects();
  check('phone: opening the left sidebar closes the sheet (never both over the view)', !R.sbCollapsed && R.dkCollapsed && Math.round(R.dock.w) === 28, JSON.stringify({ sb: R.sbCollapsed, dk: R.dkCollapsed }));
  await p.evaluate(() => window.__xrayRightSidebar.open('classification'));
  await p.waitForFunction(() => document.body.classList.contains('sb-collapsed') && !document.body.classList.contains('dk-collapsed'), null, { timeout: 8000 });
  R = await rects();
  check('phone: opening the sheet closes the left sidebar', R.sbCollapsed && !R.dkCollapsed, JSON.stringify({ sb: R.sbCollapsed, dk: R.dkCollapsed }));
  // the classification tab opened by tool.classify on the phone
  await p.evaluate(() => window.__xrayRightSidebar.close());
  await p.waitForFunction(() => document.body.classList.contains('dk-collapsed'));
  await p.evaluate(() => window.__xrayToolbar.open('classify'));
  await p.waitForFunction(() => window.__xrayRightSidebar.state().tab === 'classification' && !window.__xrayRightSidebar.state().collapsed, null, { timeout: 8000 });
  await selectClass(p, /Duct/);
  await p.waitForSelector('#dk-pane-classification .xcs', { timeout: 10000 });
  await p.waitForTimeout(500);
  const sheet = await p.evaluate(() => {
    const d = document.getElementById('dock').getBoundingClientRect();
    const card = document.querySelector('.xcs').getBoundingClientRect();
    const tb = document.getElementById('xray-topbar')?.getBoundingClientRect();
    const st = document.getElementById('xray-overlay')?.getBoundingClientRect();
    return { dockTop: d.top, cardInside: card.left >= d.left - 1 && card.right <= d.right + 1 && card.top >= d.top, belowBar: tb ? d.top >= tb.bottom : true, aboveStatus: st ? d.bottom <= st.top + 1 : true, scrollW: document.documentElement.scrollWidth, vw: innerWidth };
  });
  check('phone: the Classification tab in the sheet shows the card inside the sheet, below the top bar and above the status bar', sheet.cardInside && sheet.belowBar && sheet.aboveStatus && sheet.scrollW <= sheet.vw + 1, JSON.stringify(sheet));
  await p.screenshot({ path: resolve(here, 'right-sidebar-phone.png'), timeout: 120000 });
  await ph.context.close();

  // Chromium without a GPU warns when the decision provider probes WebGPU (the Shape check selects it): not an app error.
  const real = errors.filter((e) => !/favicon|No available adapters/i.test(e));
  console.log('console errors/warnings:', real.length ? '\n' + real.join('\n') : 'none');
  check('no console errors', real.length === 0, real.slice(0, 2).join(' | '));
  if (checks.some((c) => !c.ok)) exitCode = 1;
} catch (e) {
  console.error(e);
  exitCode = 1;
} finally {
  if (browser) await browser.close();
  vite.kill('SIGTERM');
}
process.exit(exitCode);
