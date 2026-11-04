// Headless check of the help tooltips: starts vite (bench/vite.smoke.config.mjs), opens /?model=building,
// hovers the bufferBase slider for 500 ms, screenshots bench/help-tooltip.png and asserts the popover: one title and
// four labelled lines in the order Intent, Impact, Use, Ref. A second hover on "layer falloff" is screenshotted to
// bench/help-tooltip-layer.png. Then it hovers the Peelback radius slider (bench/help-tooltip-peel.png) and a strip
// button of the action panel (bench/help-tooltip-toolbar.png). Finally, for each of the models building, fzk-haus and
// synth5k, it opens every tool drawer of the action panel once (window.__xrayToolbar.open), opens the keyboard dialogs
// and the BCF topic dialog, and fails on any "[help] no help text" console warning.
// Usage: node bench/help-smoke.mjs [--out bench/help-tooltip.png] [--out-layer bench/help-tooltip-layer.png]
//        [--out-peel bench/help-tooltip-peel.png] [--out-toolbar bench/help-tooltip-toolbar.png]
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const outIdx = process.argv.indexOf('--out');
const out = outIdx > 0 ? resolve(process.argv[outIdx + 1]) : resolve(here, 'help-tooltip.png');
const layerIdx = process.argv.indexOf('--out-layer');
const outLayer = layerIdx > 0 ? resolve(process.argv[layerIdx + 1]) : resolve(here, 'help-tooltip-layer.png');
const peelIdx = process.argv.indexOf('--out-peel');
const outPeel = peelIdx > 0 ? resolve(process.argv[peelIdx + 1]) : resolve(here, 'help-tooltip-peel.png');
const tbIdx = process.argv.indexOf('--out-toolbar');
const outToolbar = tbIdx > 0 ? resolve(process.argv[tbIdx + 1]) : resolve(here, 'help-tooltip-toolbar.png');
const port = Number(process.env.SMOKE_PORT ?? 5197);
const LABELS = ['Intent', 'Impact', 'Use', 'Ref'];

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

let failed = 0;
function check(name, ok, detail = '') {
  if (!ok) failed++;
  console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${detail ? ` (${detail})` : ''}`);
}

let browser;
try {
  await waitForServer();
  browser = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const page = await browser.newPage({ viewport: { width: 1600, height: 900 } });
  const warnings = [];
  const errors = [];
  page.on('console', (m) => {
    if (m.type() === 'warning' && m.text().startsWith('[help]')) warnings.push(m.text());
    else if (m.type() === 'error') errors.push(m.text());
  });
  page.on('pageerror', (e) => errors.push(`[pageerror] ${e.message}`));
  await page.goto(`http://127.0.0.1:${port}/?model=building`);
  await page.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: 120000 });
  check('app started', !(await page.evaluate('window.__xrayError')));
  await page.waitForTimeout(1500); // the late attach pass runs 1 s after onModel

  const popover = page.locator('#xray-help');
  const shownState = async () => page.evaluate(() => {
    const p = document.getElementById('xray-help');
    return {
    show: !!p && p.classList.contains('show'),
    titles: p ? p.querySelectorAll('.hp-title').length : 0,
    lines: p ? p.querySelectorAll('.hp-line').length : 0,
    labels: p ? [...p.querySelectorAll('.hp-line .hp-label')].map((e) => e.textContent) : [],
    texts: p ? [...p.querySelectorAll('.hp-line .hp-text')].map((e) => e.textContent) : [],
    text: p ? p.innerText : '',
    rect: p ? p.getBoundingClientRect().toJSON() : null,
  };
  });

  // 1. hover bufferBase for 500 ms
  const row = page.locator('[data-help-key="Classification (Alg 1)/bufferBase (m)"]');
  await row.waitFor({ timeout: 5000 });
  let box = await row.boundingBox();
  await page.mouse.move(box.x + 20, box.y + box.height / 2);
  await page.waitForTimeout(150);
  check('popover not shown before the 350 ms delay', !(await shownState()).show);
  await page.mouse.move(box.x + 24, box.y + box.height / 2);
  await page.waitForTimeout(500);
  const s = await shownState();
  await page.screenshot({ path: out });
  console.log('screenshot:', out);
  console.log('popover text:\n' + s.text.split('\n').map((l) => '  ' + l).join('\n'));
  check('popover visible after hover', s.show);
  check('popover has 1 title and 4 lines', s.titles === 1 && s.lines === 4, `titles=${s.titles} lines=${s.lines}`);
  check('the lines are labelled Intent, Impact, Use, Ref in this order', JSON.stringify(s.labels) === JSON.stringify(LABELS), s.labels.join(', '));
  check('the second line is the Impact text of the entry', s.labels[1] === 'Impact' && s.texts[1] === (await page.evaluate("window.__xrayHelp.lookup('Classification (Alg 1)/bufferBase (m)').impact")) && s.texts[1].length > 20, s.texts[1]);
  check('the Impact text differs from the Intent text', s.texts[0] !== s.texts[1]);
  check('popover is at most 360 px wide', s.rect && s.rect.width <= 360.5, `width=${s.rect?.width}`);
  check('popover lies inside the viewport', s.rect && s.rect.left >= 0 && s.rect.right <= 1600 && s.rect.top >= 0 && s.rect.bottom <= 900);
  check('popover does not cover the row (placed beside it)', s.rect && (s.rect.right <= box.x + 1 || s.rect.left >= box.x + box.width - 1));
  check('title line is the setting name', /bufferBase/.test(s.text.split('\n')[0] ?? ''));

  // 1b. second screenshot: the layer falloff slider (the effect of its setting is subtle, the Impact line explains it)
  await page.mouse.move(1000, 400);
  const lrow = page.locator('[data-help-key="Sightlines (Alg 2)/layer falloff"]');
  await lrow.waitFor({ timeout: 5000 });
  await lrow.evaluate((e) => e.scrollIntoView({ block: 'center' }));
  await page.waitForTimeout(150);
  const lbox = await lrow.boundingBox();
  await page.mouse.move(lbox.x + 20, lbox.y + lbox.height / 2);
  await page.waitForTimeout(500);
  const ls = await shownState();
  await page.screenshot({ path: outLayer });
  console.log('screenshot:', outLayer);
  console.log('layer falloff popover text:\n' + ls.text.split('\n').map((l) => '  ' + l).join('\n'));
  check('layer falloff popover has 4 labelled lines, Impact second', ls.show && JSON.stringify(ls.labels) === JSON.stringify(LABELS) && /layer falloff/.test(ls.text.split('\n')[0] ?? ''), ls.labels.join(', '));
  check('layer falloff popover lies inside the viewport', ls.rect && ls.rect.left >= 0 && ls.rect.right <= 1600 && ls.rect.top >= 0 && ls.rect.bottom <= 900);
  await page.mouse.move(1000, 400);
  await row.evaluate((e) => e.scrollIntoView({ block: 'center' }));
  await page.waitForTimeout(150);
  box = await row.boundingBox();
  await page.mouse.move(box.x + 22, box.y + box.height / 2);
  await page.waitForTimeout(150);

  // 2. hides on pointer down, stays hidden until the pointer leaves
  await page.mouse.down();
  check('popover hides on pointer down', !(await shownState()).show);
  await page.mouse.up();
  await page.waitForTimeout(500);
  check('popover stays hidden while the pointer stays on the row', !(await shownState()).show);

  // 3. wheel hides
  await page.mouse.move(1000, 400);
  await page.mouse.move(box.x + 30, box.y + box.height / 2);
  await page.waitForTimeout(500);
  check('popover shows again after leaving and re-entering', (await shownState()).show);
  await page.mouse.wheel(0, 40);
  // Chromium delivers wheel events on the next frame, which is slow under swiftshader: poll for the hidden state.
  const hid = await page.waitForFunction(() => !document.getElementById('xray-help').classList.contains('show'), null, { polling: 'raf', timeout: 3000 }).then(() => true, () => false);
  check('popover hides on wheel', hid);

  // 4. pointer leave hides
  await page.mouse.move(1000, 400);
  await page.mouse.move(box.x + 40, box.y + box.height / 2);
  await page.waitForTimeout(500);
  check('popover shows (third time)', (await shownState()).show);
  await page.mouse.move(1000, 400);
  await page.waitForTimeout(100);
  check('popover hides on pointer leave', !(await shownState()).show);

  // 5. keyboard path: focus a slider input after a key press shows the popover without a delay
  await page.mouse.move(1000, 450);
  await page.keyboard.press('Shift');
  await page.evaluate(() => document.querySelector('[data-help-key="Classification (Alg 1)/bufferScale"] input').focus());
  await page.waitForTimeout(100);
  const kb = await shownState();
  console.log('keyboard focus popover:', JSON.stringify(kb.text.split('\n')[0]));
  check('focus by keyboard shows the popover for the slider', kb.show && kb.lines === 4 && /bufferScale/.test(kb.text));
  await page.keyboard.press('Escape');
  check('Escape hides the popover', !(await shownState()).show);
  await page.evaluate(() => document.activeElement && document.activeElement.blur());

  // 6. sidebar and dock items, plus controls of the late plugins (open the closed folder first)
  await page.evaluate(() => window.__xray.app.panel.foldersRecursive().forEach((f) => { if (f._title === 'Export / import') f.open(); }));
  await page.waitForTimeout(300);
  for (const [sel, label] of [['.sb-filter .inp', 'Filter box'], ['.sb-toggle', 'Collapse toggle'], ['.tr .eye', 'Eye icon'], ['.tr .dot', 'Bucket dot'], ['.sb-tab >> nth=1', 'Sets tab'], ['.dk-toggle', 'Collapse toggle'], ['[data-help-key="Rendering/order-independent ghosts"]', 'order-independent ghosts'], ['[data-help-key="Export / import/Copy share URL"]', 'Copy share URL']]) {
    const loc = page.locator(sel).first();
    await loc.waitFor({ state: 'attached', timeout: 5000 });
    await loc.evaluate((e) => e.scrollIntoView({ block: 'center' }));
    await page.waitForTimeout(100);
    const b = await loc.boundingBox();
    await page.mouse.move(1000, 400);
    await page.mouse.move(b.x + b.width / 2, b.y + b.height / 2);
    await page.waitForTimeout(550);
    const t = await shownState();
    check(`sidebar: ${label}`, t.show && t.lines === 4 && t.labels[1] === 'Impact' && new RegExp(label, 'i').test(t.text.split('\n')[0] ?? ''), JSON.stringify(t.text.split('\n')[0]));
  }

  // 7. class style folder pattern: open Class styles > Classes and hover a class folder title
  await page.mouse.move(1000, 400);
  const clsTitle = page.locator('[data-help-key="Class styles/*"]').first();
  const nClass = await page.locator('[data-help-key="Class styles/*"]').count();
  check('class style folders are registered', nClass > 0, `${nClass} folders`);
  await page.evaluate(() => {
    const g = window.__xray.app.panel;
    for (const f of g.foldersRecursive()) { const t = f._title; if (t === 'Class styles' || t === 'Classes') f.open(); }
  });
  await page.waitForTimeout(400);
  const cb = await clsTitle.boundingBox();
  await page.mouse.move(cb.x + 20, cb.y + cb.height / 2);
  await page.waitForTimeout(550);
  const ct = await shownState();
  console.log('class folder popover:', JSON.stringify(ct.text));
  check('class folder popover names the class', ct.show && /Ifc[A-Za-z]+/.test(ct.text) && !/\{class\}/.test(ct.text));

  // 8. enable / disable / lookup API and the localStorage switch
  const api = await page.evaluate(() => {
    const h = window.__xrayHelp;
    return { has: !!h && typeof h.enable === 'function' && typeof h.disable === 'function' && typeof h.lookup === 'function', e: h.lookup('Display/edgeAlpha'), miss: h.lookup('No/Such') ?? null };
  });
  check('window.__xrayHelp has enable, disable, lookup', api.has && api.e && api.e.intent && api.miss === null);
  await page.evaluate("window.__xrayHelp.disable()");
  await page.mouse.move(1000, 400);
  await page.mouse.move(box.x + 24, box.y + box.height / 2);
  await page.waitForTimeout(550);
  check('disabled: no popover', !(await shownState()).show);
  check('disable() writes localStorage', (await page.evaluate("localStorage.getItem('xray.help')")) === 'off');
  await page.evaluate("window.__xrayHelp.enable()");
  await page.mouse.move(1000, 400);
  await page.mouse.move(box.x + 28, box.y + box.height / 2);
  await page.waitForTimeout(550);
  check('enabled again: popover shows', (await shownState()).show);


  // 10. the Peelback radius slider of the View modes folder, and a strip button of the action panel
  await page.mouse.move(1000, 400);
  await page.evaluate(() => {
    const g = window.__xray.app.panel;
    for (const f of g.foldersRecursive()) { const t = f._title; if (t === 'View modes' || t === 'Peelback') f.open(); }
  });
  await page.waitForTimeout(300);
  const prow = page.locator('[data-help-key="Peelback/radius (m)"]');
  await prow.waitFor({ timeout: 5000 });
  await prow.evaluate((e) => e.scrollIntoView({ block: 'center' }));
  await page.waitForTimeout(150);
  const pbox = await prow.boundingBox();
  await page.mouse.move(pbox.x + 20, pbox.y + pbox.height / 2);
  await page.waitForTimeout(550);
  const ps = await shownState();
  await page.screenshot({ path: outPeel });
  console.log('screenshot:', outPeel);
  console.log('peelback radius popover:', JSON.stringify(ps.text));
  check('Peelback radius popover has 4 labelled lines, Impact second', ps.show && JSON.stringify(ps.labels) === JSON.stringify(LABELS) && /radius/.test(ps.text.split('\n')[0] ?? ''), ps.labels.join(', '));
  check('Peelback radius popover lies inside the viewport', ps.rect && ps.rect.left >= 0 && ps.rect.right <= 1600 && ps.rect.top >= 0 && ps.rect.bottom <= 900);
  await page.mouse.move(1000, 400);
  await page.waitForTimeout(100);
  const sb = page.locator('.xt-btn-tool[data-tool="viewModes"]');
  await sb.waitFor({ timeout: 5000 });
  const sbb = await sb.boundingBox();
  await page.mouse.move(sbb.x + sbb.width / 2, sbb.y + sbb.height / 2);
  await page.waitForTimeout(550);
  const ts = await shownState();
  await page.screenshot({ path: outToolbar });
  console.log('screenshot:', outToolbar);
  console.log('strip button popover:', JSON.stringify(ts.text));
  check('strip button popover has 4 labelled lines, titled with the tool', ts.show && JSON.stringify(ts.labels) === JSON.stringify(LABELS) && /View modes/.test(ts.text.split('\n')[0] ?? ''), ts.labels.join(', '));
  check('strip button popover lies inside the viewport', ts.rect && ts.rect.left >= 0 && ts.rect.right <= 1600 && ts.rect.top >= 0 && ts.rect.bottom <= 900);
  check('the CSS tip of the strip button is hidden while help is on', await page.evaluate(() => getComputedStyle(document.querySelector('.xt-btn-tool'), '::after').display === 'none'));
  await page.mouse.move(1000, 400);

  // 9. coverage: every registered row has a text
  const cov = await page.evaluate(() => {
    const all = [...document.querySelectorAll('[data-help-key]')].map((e) => e.getAttribute('data-help-key'));
    const missing = [...new Set(all.filter((k) => !window.__xrayHelp.lookup(k)))];
    return { total: all.length, missing };
  });
  console.log(`registered rows: ${cov.total}; without a text: ${cov.missing.length}`);
  for (const m of cov.missing) console.log('  uncovered:', m);
  // Informational: texts that no row of the panel uses right now (sidebar items that need sets, a folder the other plugins add later).
  const unused = await page.evaluate(() => {
    const seen = new Set([...document.querySelectorAll('[data-help-key]')].map((e) => e.getAttribute('data-help-key')));
    const norm = (k) => k.toLowerCase().replace(/[^a-z0-9*/]+/g, '');
    const seenN = new Set([...seen].map(norm));
    return window.__xrayHelp.keys().filter((k) => !seenN.has(norm(k)));
  });
  console.log(`texts without a row in the page now: ${unused.length}`);
  for (const k of unused) console.log('  unused text:', k);

  // 11. every tool drawer, the dialogs and the models: no "[help]" warning
  await page.close();
  const MODELS = ['building', 'fzk-haus', 'synth5k'];
  for (const model of MODELS) {
    const pg = await browser.newPage({ viewport: { width: 1600, height: 900 } });
    const warn = [];
    const errs = [];
    pg.on('console', (m) => {
      if (m.type() === 'warning' && m.text().startsWith('[help]')) warn.push(m.text());
      else if (m.type() === 'error') errs.push(m.text());
    });
    pg.on('pageerror', (e) => errs.push(`[pageerror] ${e.message}`));
    await pg.goto(`http://127.0.0.1:${port}/?model=${model}`, { waitUntil: 'domcontentloaded', timeout: 180000 });
    await pg.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: 180000 });
    await pg.waitForTimeout(1500);
    const ids = await pg.evaluate('window.__xrayToolbar.tools()');
    const seen = [];
    for (const id of ids) {
      await pg.evaluate((t) => window.__xrayToolbar.open(t), id);
      await pg.waitForTimeout(450);
      const info = await pg.evaluate(() => {
        const d = document.getElementById('xray-toolbar-drawer');
        return { open: !!d && !d.classList.contains('hidden'), title: d?.querySelector('.xt-title')?.textContent ?? '' };
      });
      // Fill the dynamic parts of the drawer once: topics for BCF, a measurement, the analysis for penetrations.
      if (id === 'bcf') {
        await pg.evaluate(async () => { const b = window.__xrayBcf; if (b && b.topics.length === 0) { try { b.createTopic({ title: 'Help smoke topic', description: 'x', type: 'Issue', status: 'Open', priority: 'Normal', labels: ['a'], author: 'smoke', globalIds: [] }); await b.addComment(b.topics[0].guid, 'a comment', {}); } catch (e) { /* keep going */ } } });
        await pg.waitForTimeout(300);
        await pg.evaluate(() => { const t = document.querySelector('[data-topic]'); if (t) t.click(); });
        await pg.waitForTimeout(300);
        await pg.evaluate(() => document.querySelector('.bcf-btn[data-act="new"]')?.click());
        await pg.waitForTimeout(300);
        await pg.evaluate(() => [...document.querySelectorAll('.bcf-modal .bcf-btn')].find((b) => b.textContent === 'Cancel')?.click());
      }
      if (id === 'measure') {
        await pg.evaluate(() => { const m = window.__xrayMeasure; if (m) { m.click([0, 0, 0], 0); m.click([1, 0, 0], 0); } });
        await pg.waitForTimeout(300);
      }
      if (id === 'presets') {
        await pg.evaluate(() => [...document.querySelectorAll('#xray-toolbar-drawer .xt-btn')].find((b) => /Save current/.test(b.textContent))?.click());
        await pg.waitForTimeout(300);
        await pg.evaluate(() => [...document.querySelectorAll('#xray-toolbar-drawer .xt-btn')].find((b) => /^Duplicate$/.test(b.textContent))?.click());
        await pg.waitForTimeout(300);
        await pg.evaluate(() => [...document.querySelectorAll('#xray-toolbar-drawer .xt-btn')].find((b) => /^Edit$/.test(b.textContent))?.click());
        await pg.waitForTimeout(300);
      }
      await pg.waitForTimeout(200);
      seen.push(`${id}${info.open ? `(${info.title})` : '(no drawer)'}`);
    }
    // keyboard dialogs: palette (Ctrl+K), shortcut sheet (?), shortcut editor (button of the sheet)
    await pg.evaluate(() => document.activeElement && document.activeElement.blur());
    await pg.keyboard.press('Control+k');
    await pg.waitForTimeout(400);
    await pg.keyboard.press('Escape');
    await pg.keyboard.press('Shift+?');
    await pg.waitForTimeout(400);
    await pg.evaluate(() => [...document.querySelectorAll('.kx-sheet .kx-btn')].find((b) => b.textContent === 'Edit shortcuts')?.click());
    await pg.waitForTimeout(500);
    await pg.keyboard.press('Escape');
    await pg.waitForTimeout(300);
    const covg = await pg.evaluate(() => {
      const all = [...document.querySelectorAll('[data-help-key]')].map((e) => e.getAttribute('data-help-key'));
      return { total: all.length, missing: [...new Set(all.filter((k) => !window.__xrayHelp.lookup(k)))] };
    });
    console.log(`model ${model}: tools ${seen.join(', ')}`);
    console.log(`  rows with a key: ${covg.total}; without a text: ${covg.missing.length}; [help] warnings: ${warn.length}; console errors: ${errs.length}`);
    for (const w of [...new Set(warn)]) console.log('  ' + w);
    for (const m of covg.missing) console.log('  uncovered: ' + m);
    for (const e of errs.slice(0, 5)) console.log('  error: ' + e);
    check(`${model}: all ${ids.length} tools opened`, seen.length === ids.length && ids.length >= 10, ids.join(','));
    check(`${model}: no "[help] no help text" warning`, warn.length === 0, `${warn.length} warnings`);
    check(`${model}: every element with a help key has a text`, covg.missing.length === 0, `${covg.missing.length} missing`);
    await pg.close();
  }

  console.log(`console warnings from the attach step: ${warnings.length}`);
  for (const w of [...new Set(warnings)]) console.log('  ' + w);
  console.log(`console errors: ${errors.length}`);
  for (const e of errors.slice(0, 10)) console.log('  ' + e);
  check('no [help] warning on the first page', warnings.length === 0, `${warnings.length} warnings`);
  check('no console errors', errors.length === 0);
} catch (e) {
  console.error(e);
  failed++;
} finally {
  if (browser) await browser.close();
  vite.kill('SIGTERM');
}
console.log(failed ? `${failed} check(s) failed` : 'all checks passed');
process.exit(failed ? 1 : 0);
