// Headless smoke test for the search bar (awesome bar): starts vite (bench/vite.smoke.config.mjs) on port 5662, loads
// fzk-haus and synth5k at 1600x900 and drives the bar with Playwright: element search and selection, Shift+Enter,
// a command, a preset, a WHERE query (live count, Enter selects N, error text), a settings jump, the keyboard flow
// (/, Ctrl+K, arrows, Escape, Ctrl+Shift+K palette), recent items, hover preview, the top bar host mount, kiosk, and the
// phone layout (390x844). Screenshots: bench/search-<model>-*.png. Zero console errors is a check.
// Usage: SMOKE_PORT=5662 node bench/smoke-search.mjs
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const port = Number(process.env.SMOKE_PORT ?? 5662);

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

async function open(browser, model, opts = {}) {
  const ctx = await browser.newContext({ viewport: opts.viewport ?? { width: 1600, height: 900 } });
  if (opts.init) await ctx.addInitScript(opts.init);
  const page = await ctx.newPage();
  const errors = [];
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', (e) => errors.push(`[pageerror] ${e.message}`));
  await page.goto(`http://127.0.0.1:${port}/?model=${model}`);
  await page.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: 120000 });
  const err = await page.evaluate('window.__xrayError');
  if (err) errors.push(`[app] ${err}`);
  await page.waitForFunction('window.__xraySearch && window.__xraySearch.indexReady()', null, { timeout: 60000 });
  await page.waitForTimeout(800);
  return { ctx, page, errors };
}

const S = (page) => page.evaluate(() => window.__xraySearch.state());
const sel = (page) => page.evaluate(() => window.__xray.app.selection);
const typeInBar = async (page, text) => {
  await page.locator('.ab-input').fill('');
  await page.keyboard.type(text);
  await page.waitForTimeout(120);
};
const shot = (page, name) => page.screenshot({ path: resolve(here, name), timeout: 180000 });

async function runModel(browser, model) {
  const tag = `[${model}]`;
  const { ctx, page, errors } = await open(browser, model);
  try {
    // ---- facts about the model
    const facts = await page.evaluate(() => {
      const m = window.__xray.app.controller.model;
      const byClass = new Map();
      for (const e of m.elements) byClass.set(e.ifcClass, (byClass.get(e.ifcClass) ?? 0) + 1);
      const [cls, n] = [...byClass.entries()].sort((a, b) => b[1] - a[1])[0];
      const named = m.elements.filter((e) => e.name && e.name.length >= 6);
      // an element whose name no other element shares, so the top hit is unambiguous
      const counts = new Map();
      for (const e of named) counts.set(e.name, (counts.get(e.name) ?? 0) + 1);
      const uniq = named.filter((e) => counts.get(e.name) === 1);
      const withStorey = m.elements.find((e) => e.storey !== null && m.storeys.find((x) => x.id === e.storey));
      const pair = withStorey ? { cls: withStorey.ifcClass, storey: m.storeys.find((x) => x.id === withStorey.storey).name } : null;
      return { total: m.elements.length, cls, n, pair, uniq: uniq.slice(0, 3).map((e) => ({ id: e.id, gid: e.globalId, name: e.name, cls: e.ifcClass })), storeys: m.storeys.map((s) => s.name) };
    });
    console.log(tag, 'facts', JSON.stringify({ total: facts.total, cls: facts.cls, n: facts.n, uniq: facts.uniq.map((u) => u.name) }));
    check(`${tag} the bar exists with combobox and listbox roles`, await page.evaluate(() => {
      const i = document.querySelector('.ab-input');
      const l = document.getElementById(i.getAttribute('aria-controls'));
      return i.getAttribute('role') === 'combobox' && i.getAttribute('aria-expanded') === 'false' && l && l.getAttribute('role') === 'listbox';
    }));
    const hostAtLoad = await page.evaluate(() => !!document.getElementById('xray-topbar-search'));
    check(`${tag} the bar is mounted in #xray-topbar-search when the top bar made it, else in the fallback box on #stage`, await page.evaluate((hostAtLoad) => {
      const r = document.querySelector('.ab-root');
      return hostAtLoad ? r.parentElement.id === 'xray-topbar-search' && !r.classList.contains('ab-fallback') : r.classList.contains('ab-fallback') && r.parentElement.id === 'stage';
    }, hostAtLoad), `host at load: ${hostAtLoad}`);

    // ---- element search and selection
    await page.evaluate(() => document.activeElement && document.activeElement.blur());
    await page.keyboard.press('/');
    check(`${tag} / focuses the bar`, await page.evaluate(() => document.activeElement && document.activeElement.classList.contains('ab-input')));
    check(`${tag} the combobox reports expanded when focused`, await page.evaluate(() => document.querySelector('.ab-input').getAttribute('aria-expanded') === 'true'));
    const u = facts.uniq[0];
    if (u) {
      await page.keyboard.type(u.name);
      await page.waitForTimeout(150);
      let st = await S(page);
      const top = st.rows.find((r) => r.section === 'elements');
      check(`${tag} typing a name finds the element first`, !!top && top.key === `e:${u.gid}`, JSON.stringify(top));
      check(`${tag} the list has an Elements header and a highlight`, await page.evaluate(() => !!document.querySelector('.ab-head') && !!document.querySelector('.ab-opt mark')));
      check(`${tag} active option is wired with aria-activedescendant`, await page.evaluate(() => {
        const i = document.querySelector('.ab-input');
        const id = i.getAttribute('aria-activedescendant');
        const o = id && document.getElementById(id);
        return !!o && o.getAttribute('role') === 'option' && o.getAttribute('aria-selected') === 'true';
      }));
      const hov = await page.evaluate(() => window.__xray.renderer.shared.hoverId.value);
      check(`${tag} the active element result is highlighted in 3D (hover preview)`, hov === u.id, `hoverId=${hov}`);
      await shot(page, `search-${model}-element.png`);
      await page.keyboard.press('Enter');
      await page.waitForTimeout(300);
      const s1 = await sel(page);
      check(`${tag} Enter selects the element`, s1.length === 1 && s1[0] === u.id, JSON.stringify(s1));
      check(`${tag} the box clears and blurs after acting`, await page.evaluate(() => document.querySelector('.ab-input').value === '' && document.activeElement === document.body));
      check(`${tag} the hover highlight is cleared`, (await page.evaluate(() => window.__xray.renderer.shared.hoverId.value)) === -1);
      const u2 = facts.uniq[1];
      if (u2) {
        await page.keyboard.press('/');
        await page.keyboard.type(u2.name);
        await page.waitForTimeout(150);
        await page.keyboard.press('Shift+Enter');
        await page.waitForTimeout(300);
        const s2 = await sel(page);
        check(`${tag} Shift+Enter adds to the selection`, s2.includes(u.id) && s2.includes(u2.id) && s2.length >= 2, JSON.stringify(s2));
      }
    }
    // other fields: class, storey, GlobalId
    await page.keyboard.press('/');
    await page.keyboard.type(facts.cls.toLowerCase());
    await page.waitForTimeout(150);
    let st = await S(page);
    const clsRows = st.rows.filter((r) => r.section === 'elements' && !r.key.startsWith('more:'));
    check(`${tag} a class name finds elements of that class`, clsRows.length > 0 && clsRows.every((r) => r.sub.toLowerCase().includes(facts.cls.toLowerCase()) || r.label.toLowerCase().includes(facts.cls.toLowerCase())), `${clsRows.length} rows`);
    const capped = await page.evaluate(() => [...document.querySelectorAll('.ab-opt')].filter((o) => !o.classList.contains('ab-more')).length);
    const more = st.rows.find((r) => r.key === 'more:elements');
    check(`${tag} the element list is capped at about 50 with "N more…"`, facts.n <= 50 ? true : capped <= 50 + 30 && !!more && /\d+ more…/.test(more.label), more ? more.label : `no more row (${capped} shown)`);
    await shot(page, `search-${model}-class.png`);
    await page.keyboard.press('Escape');
    if (u) {
      await page.keyboard.press('/');
      await page.keyboard.type(u.gid.slice(0, 8));
      await page.waitForTimeout(150);
      st = await S(page);
      check(`${tag} a GlobalId prefix finds the element`, st.rows.some((r) => r.key === `e:${u.gid}`));
      await page.keyboard.press('Escape');
    }
    if (facts.pair) {
      await page.keyboard.press('/');
      await page.keyboard.type(`${facts.pair.cls.toLowerCase()} ${facts.pair.storey.toLowerCase()}`);
      await page.waitForTimeout(150);
      st = await S(page);
      check(`${tag} several terms narrow the list (class and storey)`, st.rows.some((r) => r.section === 'elements') && st.rows.filter((r) => r.section === 'elements' && !r.key.startsWith('more:')).every((r) => r.sub.toLowerCase().includes(facts.pair.cls.toLowerCase())), JSON.stringify(facts.pair));
      await page.keyboard.press('Escape');
    }
    await page.keyboard.press('Escape');

    // ---- a command
    await page.evaluate(() => window.__xray.app.selectIds([0]));
    await page.keyboard.press('/');
    await page.keyboard.type('hide selected');
    await page.waitForTimeout(150);
    st = await S(page);
    const cmd = st.rows.find((r) => r.section === 'commands');
    check(`${tag} a command row appears with its key shown`, !!cmd && cmd.key === 'a:visibility.hide' && (await page.evaluate(() => !!document.querySelector('.ab-opt kbd.kx-key'))), JSON.stringify(cmd));
    await shot(page, `search-${model}-command.png`);
    // the Commands section should be on top for this query
    check(`${tag} the best section comes first`, st.rows[0].section === 'commands', st.rows[0].section);
    await page.keyboard.press('Enter');
    await page.waitForTimeout(300);
    check(`${tag} Enter runs the command (the element is hidden)`, (await page.evaluate(() => window.__xray.app.settings.overrides.userHides.has(0))) === true);
    await page.keyboard.press('/');
    await page.keyboard.type('unhide all');
    await page.waitForTimeout(150);
    await page.keyboard.press('Enter');
    await page.waitForTimeout(300);
    check(`${tag} Unhide all through the bar`, (await page.evaluate(() => window.__xray.app.settings.overrides.userHides.size)) === 0);

    // ---- a preset
    const presets = await page.evaluate(() => window.__xrayPresets.list().map((p) => ({ id: p.id, name: p.name })));
    const pr = presets.find((p) => p.name.length > 6) ?? presets[0];
    await page.keyboard.press('/');
    await page.keyboard.type(pr.name);
    await page.waitForTimeout(150);
    st = await S(page);
    const prow = st.rows.find((r) => r.key === `p:${pr.id}`);
    check(`${tag} a preset is listed under Presets`, !!prow, JSON.stringify(st.rows.slice(0, 4)));
    // move to the preset row with the arrow keys
    for (let i = 0; i < 30; i++) {
      const cur = await S(page);
      const flat = cur.rows;
      if (flat[cur.active]?.key === `p:${pr.id}`) break;
      await page.keyboard.press('ArrowDown');
    }
    await shot(page, `search-${model}-preset.png`);
    await page.keyboard.press('Enter');
    await page.waitForTimeout(500);
    check(`${tag} Enter applies the preset`, (await page.evaluate(() => window.__xrayPresets.active())) === pr.id, await page.evaluate(() => String(window.__xrayPresets.active())));

    // ---- a saved view
    const vname = await page.evaluate(() => { const v = window.__xrayViews.save('Smoke view'); return v.name; });
    await page.keyboard.press('/');
    await page.keyboard.type('smoke view');
    await page.waitForTimeout(150);
    st = await S(page);
    check(`${tag} a saved view is listed`, st.rows.some((r) => r.section === 'views' && r.label === vname));
    await page.keyboard.press('Escape');

    // ---- selection sets
    const setName = await page.evaluate(() => {
      const raw = JSON.parse(localStorage.getItem('xray.sets.' + window.__xray.app.modelName) ?? 'null');
      const sets = raw?.sets ?? [];
      return sets[0]?.name ?? null;
    });
    if (setName) {
      await page.keyboard.press('/');
      await page.keyboard.type(setName);
      await page.waitForTimeout(150);
      st = await S(page);
      const srow = st.rows.find((r) => r.section === 'sets');
      check(`${tag} a selection set is listed`, !!srow, JSON.stringify(srow));
      for (let i = 0; i < 40; i++) {
        const cur = await S(page);
        if (cur.rows[cur.active]?.section === 'sets') break;
        await page.keyboard.press('ArrowDown');
      }
      await page.keyboard.press('Enter');
      await page.waitForTimeout(400);
      check(`${tag} Enter selects the set`, (await sel(page)).length > 0);
    } else {
      console.log(tag, 'no stored selection sets for this model: set check skipped');
    }

    // ---- WHERE query
    await page.evaluate(() => window.__xray.app.clearSelection());
    await page.keyboard.press('/');
    await page.keyboard.type(`where class = '${facts.cls}'`);
    await page.waitForTimeout(150);
    st = await S(page);
    check(`${tag} where-query shows the live count`, st.rows[0]?.section === 'query' && st.rows[0].label === `${facts.n} elements match`, st.rows[0]?.label);
    check(`${tag} the footer repeats the count`, st.footer.includes(`${facts.n} elements match the query`), st.footer);
    await shot(page, `search-${model}-query.png`);
    await page.keyboard.press('Enter');
    await page.waitForTimeout(500);
    check(`${tag} Enter selects all ${facts.n} matches`, (await sel(page)).length === facts.n, `${(await sel(page)).length}`);
    await page.evaluate(() => window.__xray.app.clearSelection());
    // auto-detected WHERE expression, ? prefix
    await page.keyboard.press('/');
    await page.keyboard.type(`class = '${facts.cls}' and storey like '%'`);
    await page.waitForTimeout(150);
    st = await S(page);
    check(`${tag} a bare WHERE expression is detected`, st.rows[0]?.section === 'query' && /elements? match/.test(st.rows[0].label), st.rows[0]?.label);
    await page.keyboard.press('Escape');
    await page.keyboard.press('/');
    await page.keyboard.type(`?class = '${facts.cls}'`);
    await page.waitForTimeout(150);
    st = await S(page);
    check(`${tag} the ? prefix runs a query`, st.rows[0]?.section === 'query');
    await page.keyboard.press('Escape');
    // errors in plain language
    await page.keyboard.press('/');
    await page.keyboard.type(`where class = `);
    await page.waitForTimeout(150);
    st = await S(page);
    check(`${tag} a query error is shown inline in plain words`, st.notes.some((n) => /Expected/i.test(n) && /character/.test(n)) && !st.rows.some((r) => r.section === 'query'), JSON.stringify(st.notes));
    check(`${tag} the error note is styled as an error`, await page.evaluate(() => !!document.querySelector('.ab-note.ab-err')));
    await shot(page, `search-${model}-query-error.png`);
    await page.keyboard.press('Control+a');
    await page.keyboard.type(`where nosuchcolumn = 1`);
    await page.waitForTimeout(150);
    st = await S(page);
    check(`${tag} an unknown column is explained`, st.notes.some((n) => /nosuchcolumn/.test(n)) && st.rows[0]?.label === '0 elements match', JSON.stringify(st.notes));
    await page.keyboard.press('Escape');

    // ---- a settings jump
    const setting = await page.evaluate(() => {
      const app = window.__xray.app;
      const ctls = app.panel.controllersRecursive();
      const pick = ctls.find((c) => c._name && c._name.length > 9 && c.parent && c.parent._closed && c.parent.parent && c.parent.parent.parent === undefined && c.$input);
      if (!pick) return null;
      return { label: pick._name.trim(), folder: pick.parent._title };
    });
    check(`${tag} found a control in a closed folder to jump to`, !!setting);
    if (setting) {
      await page.keyboard.press('/');
      await page.keyboard.type(setting.label);
      await page.waitForTimeout(150);
      st = await S(page);
      const grow = st.rows.find((r) => r.section === 'settings' && r.label === setting.label);
      check(`${tag} the setting is listed under Settings`, !!grow, JSON.stringify(st.rows.filter((r) => r.section === 'settings').slice(0, 3)));
      for (let i = 0; i < 60; i++) {
        const cur = await S(page);
        if (cur.rows[cur.active]?.key === grow?.key) break;
        await page.keyboard.press('ArrowDown');
      }
      await page.keyboard.press('Enter');
      await page.waitForTimeout(500);
      const j = await page.evaluate((label) => {
        const c = window.__xray.app.panel.controllersRecursive().find((x) => x._name && x._name.trim() === label);
        return { open: !c.parent._closed, flash: c.domElement.classList.contains('ab-flash'), dock: document.body.classList.contains('dk-collapsed') };
      }, setting.label);
      check(`${tag} Enter opens the folder and flashes the control`, j.open && j.flash && !j.dock, JSON.stringify(j));
      await shot(page, `search-${model}-setting.png`);
    }
    // help-text title match
    await page.keyboard.press('/');
    await page.keyboard.type('buffer');
    await page.waitForTimeout(150);
    st = await S(page);
    check(`${tag} a word of a setting name lists settings`, st.rows.some((r) => r.section === 'settings'));
    await page.keyboard.press('Escape');

    // ---- keyboard flow
    await page.evaluate(() => document.activeElement && document.activeElement.blur());
    await page.keyboard.press('Control+k');
    check(`${tag} Ctrl+K focuses the bar (not the palette)`, (await page.evaluate(() => document.activeElement.classList.contains('ab-input'))) && (await page.locator('.kx-palette').count()) === 0);
    await page.keyboard.type('x');
    await page.waitForTimeout(120);
    const a0 = (await S(page)).active;
    await page.keyboard.press('ArrowDown');
    await page.keyboard.press('ArrowDown');
    const a2 = (await S(page)).active;
    await page.keyboard.press('ArrowUp');
    const a1 = (await S(page)).active;
    check(`${tag} arrow keys move through the results`, a0 === 0 && a2 === 2 && a1 === 1, `${a0},${a2},${a1}`);
    await page.keyboard.press('Escape');
    check(`${tag} Escape clears and blurs`, await page.evaluate(() => document.querySelector('.ab-input').value === '' && document.activeElement === document.body && document.querySelector('.ab-input').getAttribute('aria-expanded') === 'false'));
    await page.keyboard.press('Control+Shift+k');
    await page.waitForTimeout(250);
    check(`${tag} the command palette is still there on Ctrl+Shift+K`, (await page.locator('.kx-palette').count()) === 1);
    await page.keyboard.press('Escape');
    await page.waitForTimeout(100);
    check(`${tag} typing a letter key in the bar triggers no action (x-ray unchanged)`, await (async () => {
      const x0 = await page.evaluate(() => window.__xray.app.settings.xray);
      await page.keyboard.press('/');
      await page.keyboard.type('xhb');
      await page.keyboard.press('Escape');
      return (await page.evaluate(() => window.__xray.app.settings.xray)) === x0;
    })());
    const conflicts = await page.evaluate(() => window.__keymap.conflicts().map((c) => `${c.chord}=${c.ids.join(',')}`));
    check(`${tag} no key conflicts in the keymap`, conflicts.length === 0, conflicts.join('; '));

    // ---- recent items
    await page.keyboard.press('/');
    await page.waitForTimeout(150);
    st = await S(page);
    check(`${tag} focusing the empty box lists recent items`, st.rows.length > 0 && (await page.evaluate(() => document.querySelector('.ab-head').textContent === 'Recent')), JSON.stringify(st.rows.slice(0, 3).map((r) => r.label)));
    const stored = await page.evaluate(() => JSON.parse(localStorage.getItem('xray.search.recent') ?? '[]'));
    check(`${tag} recent items are kept in localStorage, newest first`, stored.length > 1 && stored.length <= 8, JSON.stringify(stored.slice(0, 3)));
    await shot(page, `search-${model}-recent.png`);
    await page.keyboard.press('Escape');

    // ---- the host: the bar leaves for the fallback when the host goes away and moves in when it comes back
    const hostBox = await page.evaluate(() => {
      let h = document.getElementById('xray-topbar-search');
      const made = !h;
      if (!h) {
        h = document.createElement('div');
        h.id = 'xray-topbar-search';
        h.style.cssText = 'position:fixed;top:0;left:300px;width:520px;height:30px;z-index:20';
        document.body.appendChild(h);
      }
      return made;
    });
    await page.waitForTimeout(200);
    check(`${tag} the bar moves into #xray-topbar-search when it appears`, await page.evaluate(() => {
      const r = document.querySelector('.ab-root');
      return r.parentElement.id === 'xray-topbar-search' && !r.classList.contains('ab-fallback');
    }), hostBox ? 'host made by the test' : 'host from the top bar');
    await page.keyboard.press('/');
    await page.keyboard.type('wall');
    await page.waitForTimeout(150);
    const geo = await page.evaluate(() => {
      const i = document.querySelector('.ab-input').getBoundingClientRect();
      const p = document.querySelector('.ab-pop').getBoundingClientRect();
      return { iTop: i.top, iBottom: i.bottom, pTop: p.top, pLeft: p.left, pRight: p.right, vw: innerWidth };
    });
    check(`${tag} the list opens below the box in the host`, geo.pTop >= geo.iBottom && geo.pLeft >= 0 && geo.pRight <= geo.vw, JSON.stringify(geo));
    await shot(page, `search-${model}-host.png`);
    await page.keyboard.press('Escape');
    await page.evaluate(() => { window.__hostKeep = document.getElementById('xray-topbar-search'); window.__hostKeep.remove(); });
    await page.waitForTimeout(200);
    check(`${tag} when the host goes away the fallback box returns`, await page.evaluate(() => document.querySelector('.ab-root').classList.contains('ab-fallback') && document.querySelector('.ab-root').isConnected));
    await page.evaluate(() => { document.body.appendChild(window.__hostKeep); });
    await page.waitForTimeout(200);
    check(`${tag} the bar moves back into the host`, await page.evaluate(() => document.querySelector('.ab-root').parentElement.id === 'xray-topbar-search'));

    // ---- the box does not steal selection clicks: clicking the canvas blurs it
    await page.keyboard.press('/');
    await page.keyboard.type('abc');
    await page.mouse.click(800, 600);
    await page.waitForTimeout(150);
    check(`${tag} clicking the canvas closes the list`, (await page.evaluate(() => document.querySelector('.ab-input').getAttribute('aria-expanded'))) === 'false');
    await page.evaluate(() => { const i = document.querySelector('.ab-input'); i.value = ''; });
  } finally {
    const real = errors.filter((e) => !/favicon/i.test(e));
    check(`${tag} zero console errors`, real.length === 0, real.slice(0, 3).join(' | '));
    await ctx.close();
  }
}

async function runPhone(browser) {
  const tag = '[phone 390x844]';
  const { ctx, page, errors } = await open(browser, 'fzk-haus', { viewport: { width: 390, height: 844 } });
  try {
    const st0 = await page.evaluate(() => {
      const r = document.querySelector('.ab-root');
      const ic = document.querySelector('.ab-icon').getBoundingClientRect();
      const f = document.querySelector('.ab-field');
      return { phone: r.classList.contains('ab-phone'), icon: ic.width > 0 && ic.height > 0, fieldHidden: getComputedStyle(f).display === 'none', sw: document.documentElement.scrollWidth };
    });
    check(`${tag} the bar collapses to a search icon`, st0.phone && st0.icon && st0.fieldHidden, JSON.stringify(st0));
    await shot(page, 'search-phone-collapsed.png');
    await page.locator('.ab-icon').click();
    await page.waitForTimeout(200);
    const st1 = await page.evaluate(() => {
      const i = document.querySelector('.ab-input').getBoundingClientRect();
      return { w: i.width, left: i.left, focused: document.activeElement.classList.contains('ab-input'), sw: document.documentElement.scrollWidth };
    });
    check(`${tag} the icon expands the box to the full width and focuses it`, st1.focused && st1.w >= 390 - 24 && st1.left >= 0, JSON.stringify(st1));
    await page.keyboard.type('wand');
    await page.waitForTimeout(200);
    const st2 = await page.evaluate(() => {
      const p = document.querySelector('.ab-pop').getBoundingClientRect();
      return { left: p.left, right: p.right, bottom: p.bottom, sw: document.documentElement.scrollWidth, rows: document.querySelectorAll('.ab-opt').length };
    });
    check(`${tag} the list fits the screen and the page does not scroll sideways`, st2.left >= 0 && st2.right <= 390 && st2.bottom <= 844 && st2.sw <= 390 && st2.rows > 0, JSON.stringify(st2));
    await shot(page, 'search-phone-open.png');
    await page.keyboard.press('Enter');
    await page.waitForTimeout(300);
    check(`${tag} Enter selects and the bar collapses again`, await page.evaluate(() => window.__xray.app.selection.length > 0 && document.querySelector('.ab-field') && getComputedStyle(document.querySelector('.ab-field')).display === 'none'));
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
    check(`${tag} the bar is hidden in kiosk mode`, await page.evaluate(() => window.__xraySearch.bar.hidden && document.querySelector('.ab-root').hidden));
    await page.keyboard.press('Control+k');
    await page.waitForTimeout(200);
    check(`${tag} Ctrl+K still opens the command palette`, (await page.locator('.kx-palette').count()) === 1);
    await page.keyboard.press('Escape');
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
  for (const m of ['fzk-haus', 'synth5k']) await runModel(browser, m);
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
