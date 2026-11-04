// Headless check for the hover card (src/plugins/hoverInfo.ts, src/ui/hoverCard.ts) and the sidebar Properties list.
//   SMOKE_PORT=5314 node bench/smoke-hover.mjs
// Starts the dev server with bench/vite.smoke.config.mjs, opens /?model=fzk-haus at 1600x900, rests the mouse on a wall,
// checks the card (name, a property row), Alt freeze, the `i` toggle, the sidebar list, and a browser-read IFC
// (models/AC20-FZK-Haus.ifc through the file input). Writes bench/hover-card.png and bench/hover-card-ifc.png.
// Fails on any console error or page error.
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const repo = resolve(root, '..');
const port = Number(process.env.SMOKE_PORT ?? 5314);

const req = createRequire(import.meta.url);
let pw;
for (const c of [process.env.PLAYWRIGHT_MODULE, resolve(root, 'node_modules/playwright'), '/opt/node-tools/node_modules/playwright', '/opt/node22/lib/node_modules/playwright'].filter(Boolean)) {
  try { pw = req(c); break; } catch { /* next */ }
}
if (!pw) throw new Error('playwright not found; set PLAYWRIGHT_MODULE');

const vite = spawn(resolve(root, 'node_modules/.bin/vite'), ['--config', resolve(here, 'vite.smoke.config.mjs'), '--host', '127.0.0.1', '--port', String(port), '--strictPort'],
  { cwd: root, stdio: ['ignore', 'pipe', 'pipe'] });
let log = '';
vite.stdout.on('data', (d) => (log += d));
vite.stderr.on('data', (d) => (log += d));
let up = false;
for (let i = 0; i < 100 && !up; i++) {
  try { up = (await fetch(`http://127.0.0.1:${port}/`)).ok; } catch { await new Promise((r) => setTimeout(r, 200)); }
}
if (!up) { console.error('vite did not start:\n' + log); vite.kill('SIGTERM'); process.exit(1); }

const browser = await pw.chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
let failures = 0;
const check = (cond, what) => { console.log(`  ${cond ? 'ok  ' : 'FAIL'} ${what}`); if (!cond) failures++; return cond; };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

try {
  const page = await browser.newPage({ viewport: { width: 1600, height: 900 } });
  const errors = [];
  const warnings = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error') errors.push(`[error] ${msg.text()}`);
    else if (msg.type() === 'warning') warnings.push(msg.text());
  });
  page.on('pageerror', (e) => errors.push(`[pageerror] ${e.message}`));
  page.on('requestfailed', (r) => errors.push(`[requestfailed] ${r.url()}`));

  await page.goto(`http://127.0.0.1:${port}/?model=fzk-haus`);
  await page.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: 120000 });
  const startErr = await page.evaluate('window.__xrayError');
  if (startErr) throw new Error('app failed to start: ' + startErr);
  await sleep(800);

  /** Screen point (CSS px) where the pick returns an element of one of `classes` and that has props; coarse grid scan. */
  const findPoint = (classes) => page.evaluate((cls) => {
    const app = window.__xray.app;
    const r = app.canvas.getBoundingClientRect();
    const m = app.controller.model;
    const hits = [];
    for (let j = 0.15; j <= 0.9; j += 0.05) {
      for (let i = 0.1; i <= 0.9; i += 0.05) {
        const id = app.renderer.pick(i * 2 - 1, -(j * 2 - 1));
        if (id === null) continue;
        const e = m.elements[id];
        if (cls.includes(e.ifcClass) && e.props && Object.keys(e.props).length > 0) hits.push({ x: r.left + i * r.width, y: r.top + j * r.height, id, cls: e.ifcClass });
      }
    }
    // prefer a point whose neighbours (+-12 px) pick the same element, so a small move does not change the element
    for (const h of hits) {
      const ok = [[12, 0], [-12, 0], [0, 12], [0, -12]].every(([dx, dy]) => {
        const nid = app.renderer.pick(((h.x + dx - r.left) / r.width) * 2 - 1, -(((h.y + dy - r.top) / r.height) * 2 - 1));
        return nid === h.id;
      });
      if (ok) return h;
    }
    return hits[0] ?? null;
  }, classes);

  const card = () => page.evaluate(() => {
    const c = document.getElementById('xray-hover-card');
    if (!c) return { exists: false };
    const cs = getComputedStyle(c);
    const r = c.getBoundingClientRect();
    return {
      exists: true, visible: cs.display !== 'none', frozen: c.classList.contains('frozen'),
      title: c.querySelector('.hc-title')?.textContent ?? '', sub: c.querySelector('.hc-sub')?.textContent ?? '',
      rows: Array.from(c.querySelectorAll('.hc-rows dt')).map((dt, i) => [dt.textContent, c.querySelectorAll('.hc-rows dd')[i].textContent]),
      foot: c.querySelector('.hc-foot')?.textContent ?? '', rect: { x: r.x, y: r.y, w: r.width, h: r.height },
      copyVisible: getComputedStyle(c.querySelector('.hc-copy')).display !== 'none',
    };
  });
  /** The page renders slowly under swiftshader, and the card is driven from the frame loop: wait for it instead of a fixed sleep. */
  const waitCard = (visible, ms = 6000) => page.waitForFunction((v) => {
    const c = document.getElementById('xray-hover-card');
    return (!!c && getComputedStyle(c).display !== 'none') === v;
  }, visible, { timeout: ms }).then(() => true, () => false);
  /** Move to (x, y), let the throttled pick catch up (last pointermove inside 80 ms of the previous one is dropped), then rest. */
  const rest = async (x, y, ms = 600) => {
    await page.mouse.move(x - 40, y - 30);
    await sleep(100);
    await page.mouse.move(x - 10, y - 8, { steps: 3 });
    await sleep(100);
    await page.mouse.move(x, y);
    await sleep(ms);
  };

  // ---- panel folder and action
  const panel = await page.evaluate(() => {
    const f = window.__xray.app.panel.folders.find((x) => x._title === 'Hover info');
    return f ? f.controllers.map((c) => c._name) : null;
  });
  console.log('Hover info folder:', JSON.stringify(panel));
  check(JSON.stringify(panel) === JSON.stringify(['show on hover', 'delay (ms)', 'max rows', 'show x-ray state', 'highlight', 'property filter', 'all properties in sidebar']),
    "folder 'Hover info' with the seven controls");

  // ---- 1. hover a wall on the converter-made model
  const wall = await findPoint(['IfcWall', 'IfcWallStandardCase']);
  check(!!wall, `found a wall on screen ${wall ? `(#${wall.id} ${wall.cls} at ${Math.round(wall.x)},${Math.round(wall.y)})` : ''}`);
  await rest(wall.x, wall.y, 150);
  const early = await card();
  check(early.exists && !early.visible || !early.exists, 'card not shown before the delay (350 ms)');
  const fps = await page.evaluate(() => JSON.stringify(window.__xray.stats));
  console.log('stats:', fps.slice(0, 200));
  await waitCard(true);
  const c1 = await card();
  console.log('card:', JSON.stringify(c1));
  check(c1.visible, 'card visible after resting 700 ms');
  check(c1.title.length > 0 && c1.title !== 'undefined', `card title is the element name ("${c1.title}")`);
  check(c1.sub.includes('Ifc') && c1.sub.includes(' · '), `class · storey · material line ("${c1.sub}")`);
  check(c1.rows.length >= 1 && c1.rows.length <= 6, `${c1.rows.length} property rows`);
  check(c1.foot.startsWith('x-ray:'), `x-ray footer ("${c1.foot}")`);
  const pr = { x: wall.x, y: wall.y };
  check(!(pr.x >= c1.rect.x && pr.x <= c1.rect.x + c1.rect.w && pr.y >= c1.rect.y && pr.y <= c1.rect.y + c1.rect.h), 'card does not cover the pointer');
  check(c1.rect.x >= 0 && c1.rect.y >= 0 && c1.rect.x + c1.rect.w <= 1600 && c1.rect.y + c1.rect.h <= 900 && c1.rect.w <= 301, 'card on screen and at most 300 px wide');
  await page.screenshot({ path: resolve(here, 'hover-card.png'), timeout: 180000 });

  // ---- 2. Alt freezes
  await page.keyboard.down('Alt');
  await sleep(100);
  const f1 = await card();
  check(f1.visible && f1.frozen && f1.copyVisible, 'Alt freezes the card and shows the copy button');
  await page.mouse.move(wall.x + 4, wall.y + 3);
  await sleep(500);
  const f2 = await card();
  check(f2.visible && f2.frozen && f2.rect.x === f1.rect.x && f2.rect.y === f1.rect.y, 'frozen card stays in place when the mouse moves slightly');
  await page.screenshot({ path: resolve(here, 'hover-card-frozen.png'), timeout: 180000 });
  await page.keyboard.up('Alt');
  await sleep(150);
  const f3 = await card();
  check(!f3.frozen, 'releasing Alt unfreezes');

  // ---- 3. wheel / key hide, `i` toggles
  await page.mouse.move(wall.x + 6, wall.y + 4);
  await page.keyboard.press('i');
  await sleep(150);
  const toastOff = await page.evaluate(() => document.querySelector('.hc-toast')?.textContent);
  check(toastOff === 'Hover info off', `toast says "${toastOff}"`);
  await rest(wall.x, wall.y, 800);
  const c2 = await card();
  check(!c2.visible, 'with hover info off the card does not show');
  const on = await page.evaluate(() => window.__xray.app.panel.folders.find((x) => x._title === 'Hover info').controllers[0].getValue());
  check(on === false, "'show on hover' control follows the key");
  await page.keyboard.press('i');
  await rest(wall.x + 3, wall.y + 3, 100);
  await waitCard(true);
  const c3 = await card();
  check(c3.visible, 'pressing i again turns it back on');
  await page.keyboard.press('Shift+ArrowUp').catch(() => {});
  await sleep(100);
  check(!(await card()).visible, 'a key press hides the card');

  // ---- 4. select: sidebar Properties list
  await page.mouse.move(wall.x - 5, wall.y);
  await sleep(100);
  await page.mouse.click(wall.x, wall.y);
  await sleep(500);
  const side = await page.evaluate(() => {
    const d = document.querySelector('.props-list');
    return d ? {
      display: getComputedStyle(d).display, open: d.open, summary: d.querySelector('summary').textContent,
      rows: Array.from(d.querySelectorAll('dt')).map((x) => x.textContent), values: Array.from(d.querySelectorAll('dd')).map((x) => x.textContent),
    } : null;
  });
  console.log('sidebar list:', JSON.stringify(side));
  check(!!side && side.display !== 'none' && side.rows.length > 0 && side.values.length === side.rows.length, `sidebar Properties list shows ${side?.rows.length} rows (${side?.summary})`);
  await page.screenshot({ path: resolve(here, 'hover-sidebar.png'), timeout: 180000 });
  // property filter and `all properties in sidebar`
  const filt = await page.evaluate(() => {
    const f = window.__xray.app.panel.folders.find((x) => x._title === 'Hover info');
    const ctl = (n) => f.controllers.find((c) => c._name === n);
    ctl('property filter').setValue('*.Length, *.Width');
    const filtered = [document.querySelector('.props-list summary').textContent, document.querySelectorAll('.props-list dt').length];
    ctl('all properties in sidebar').setValue(true);
    const all = [document.querySelector('.props-list summary').textContent, document.querySelectorAll('.props-list dt').length];
    ctl('all properties in sidebar').setValue(false);
    ctl('property filter').setValue('Attr.ObjectType, *.IsExternal, *.LoadBearing, *.FireRating, *.Reference, Qto*.Length, Qto*.Width, Qto*.Height, Qto*.NetVolume, *Quantities.Length, *Quantities.Width, *Quantities.Height, *Quantities.NetVolume');
    return { filtered, all };
  });
  console.log('filter:', JSON.stringify(filt));
  check(filt.filtered[1] === 2 && filt.all[1] === 9 && filt.filtered[0] === 'Properties (2 of 9)', 'property filter narrows the sidebar list, `all properties in sidebar` lists everything');
  await page.evaluate(() => window.__xray.app.clearSelection());

  // ---- 5. browser-read IFC through the file input
  await page.setInputFiles('#xray-open-file-input', resolve(repo, 'models/AC20-FZK-Haus.ifc'));
  await page.waitForFunction(() => window.__xray.app.modelName === 'file:AC20-FZK-Haus.ifc', null, { timeout: 120000 });
  await sleep(1500);
  const elsWithProps = await page.evaluate(() => window.__xray.app.controller.model.elements.filter((e) => e.props && Object.keys(e.props).length).length);
  check(elsWithProps > 40, `browser-read model has props on ${elsWithProps} of 82 elements`);
  const wall2 = await findPoint(['IfcWall', 'IfcWallStandardCase']);
  check(!!wall2, 'found a wall in the browser-read model');
  await rest(wall2.x, wall2.y, 100);
  await waitCard(true);
  const c4 = await card();
  console.log('card (browser-read):', JSON.stringify(c4));
  check(c4.visible && c4.title.length > 0 && c4.rows.length >= 1, `hover shows name "${c4.title}" and ${c4.rows.length} property rows for a browser-read model`);
  await page.screenshot({ path: resolve(here, 'hover-card-ifc.png'), timeout: 180000 });

  console.log('console warnings:', warnings.length ? '\n  ' + [...new Set(warnings)].slice(0, 12).join('\n  ') : 'none');
  console.log('console errors:', errors.length ? '\n' + errors.join('\n') : 'none');
  failures += errors.length;
} catch (e) {
  console.error(e);
  failures++;
} finally {
  await browser.close();
  vite.kill('SIGTERM');
}
console.log(failures ? `\n${failures} problem(s)` : '\nall checks passed');
process.exit(failures ? 1 : 0);
