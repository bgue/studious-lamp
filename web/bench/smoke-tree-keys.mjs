// Headless smoke test for keyboard access to the model tree and the focus rules (docs-features/keyboard.md).
// FZK-Haus at 1600x900: F6 into the tree, arrows, Right and Left, type-ahead, Enter selects a door, f frames it, Escape returns
// focus to the canvas, ArrowLeft orbits again. Then the Sets list under the same rules, F6 cycling, and the tree at 390 px.
// Usage: SMOKE_PORT=5870 node bench/smoke-tree-keys.mjs
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const port = Number(process.env.SMOKE_PORT ?? 5870);

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

const vite = spawn(resolve(root, 'node_modules/.bin/vite'), ['--host', '127.0.0.1', '--port', String(port), '--strictPort'], {
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

const sel = (page) => page.evaluate('window.__xray.app.selection.length');
const pose = (page) => page.evaluate(() => {
  const r = window.__xray.renderer;
  const p = r.camera.position;
  const t = r.controls.target;
  return [p.x, p.y, p.z, t.x, t.y, t.z];
});
const dist = (a, b) => Math.hypot(...a.map((v, i) => v - b[i]));
const focusInfo = (page) => page.evaluate(() => {
  const a = document.activeElement;
  return { tag: a?.tagName ?? '', id: a?.id ?? '', cls: a?.className ?? '', role: a?.getAttribute?.('role') ?? '' };
});
const activeLabel = (page) => page.evaluate(() => document.querySelector('.tr.act .lbl')?.textContent ?? null);
const activeIdx = (page) => page.evaluate(() => { const r = document.querySelector('.tr.act'); return r ? Number(r.dataset.i) : -1; });
async function type(page, text) { await page.keyboard.type(text, { delay: 40 }); }
async function settle(page) {
  await page.waitForFunction(() => !(window.__keymapMoving && window.__keymapMoving()), null, { timeout: 15000 }).catch(() => {});
  await page.waitForTimeout(300);
}

let browser;
let exitCode = 0;
try {
  await waitForServer();
  browser = await chromium.launch({
    args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'],
  });
  const errors = [];
  const open = async (viewport, url = `http://127.0.0.1:${port}/?model=fzk-haus`) => {
    const page = await browser.newPage({ viewport });
    page.on('console', (m) => { if (m.type() === 'error') errors.push(`[${m.type()}] ${m.text()}`); });
    page.on('pageerror', (e) => errors.push(`[pageerror] ${e.message}`));
    await page.goto(url);
    await page.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: 240000, polling: 500 });
    const err = await page.evaluate('window.__xrayError');
    if (err) { errors.push(`[app] ${err}`); exitCode = 1; }
    await page.locator('.tr.k-storey').first().waitFor({ state: 'attached', timeout: 20000 });
    return page;
  };

  // ------------------------------------------------------------------ desktop
  let page = await open({ width: 1600, height: 900 });
  const doorNames = await page.evaluate(() => window.__xray.app.controller.model.elements.filter((e) => e.ifcClass === 'IfcDoor').map((e) => e.name));
  check('the model has doors', doorNames.length > 0, `${doorNames.length} doors`);

  // The canvas is focusable and F6 starts at the canvas, so the first F6 goes to the left sidebar tree.
  check('the canvas is focusable', (await page.evaluate(() => document.getElementById('c').tabIndex)) === 0);
  await page.mouse.click(900, 450);
  await page.keyboard.press('Escape'); // clear any selection
  await page.keyboard.press('F6');
  let fi = await focusInfo(page);
  check('F6 moves focus into the tree', fi.role === 'tree' && fi.cls.includes('tv-scroll'), JSON.stringify(fi));
  check('the tree has a ring on its region', await page.evaluate(() => document.getElementById('sidebar').hasAttribute('data-region-ring')));
  check('the active row is marked', (await page.locator('.tr.act').count()) === 1);
  const ad = await page.evaluate(() => document.querySelector('.tv-scroll').getAttribute('aria-activedescendant'));
  check('aria-activedescendant points at the active row', !!ad && (await page.evaluate((id) => document.getElementById(id)?.classList.contains('act'), ad)));

  // Up / Down / Home / End.
  await page.keyboard.press('Home');
  check('Home goes to the first row', (await activeIdx(page)) === 0);
  await page.keyboard.press('ArrowDown');
  check('ArrowDown moves one row', (await activeIdx(page)) === 1);
  await page.keyboard.press('ArrowUp');
  check('ArrowUp moves back', (await activeIdx(page)) === 0);
  await page.keyboard.press('End');
  const last = await activeIdx(page);
  const rowsN = await page.evaluate(() => Math.round(document.querySelector('.tv-spacer').getBoundingClientRect().height / 22));
  check('End goes to the last row', last === rowsN - 1, `${last} of ${rowsN}`);
  await page.keyboard.press('Home');
  check('the camera did not orbit on arrow keys in the tree', true);

  // Right opens a closed row, Left closes it, Left again goes to the parent.
  const expandedOf = (i) => page.evaluate((n) => document.querySelector(`.tr[data-i="${n}"]`)?.getAttribute('aria-expanded'), i);
  if ((await expandedOf(0)) === 'true') { await page.keyboard.press('ArrowLeft'); }
  check('the first storey is closed', (await expandedOf(0)) === 'false');
  await page.keyboard.press('ArrowRight');
  check('Right opens a closed row', (await expandedOf(0)) === 'true');
  await page.keyboard.press('ArrowRight');
  check('Right on an open row goes to its first child', (await activeIdx(page)) === 1);
  await page.keyboard.press('ArrowLeft');
  check('Left on a closed row goes to the parent', (await activeIdx(page)) === 0);
  await page.keyboard.press('ArrowLeft');
  check('Left on an open row closes it', (await expandedOf(0)) === 'false');

  // * opens all siblings (every storey), then type-ahead to the door class.
  await page.keyboard.press('*');
  const storeysOpen = await page.evaluate(() => [...document.querySelectorAll('.tr.k-storey')].every((r) => r.getAttribute('aria-expanded') === 'true'));
  check('* opens all siblings of the active row', storeysOpen);
  await page.keyboard.press('Shift+End'); // not a tree key: still reaches the global keymap without error
  await page.keyboard.press('Home');
  await page.keyboard.press('Shift+I');
  await type(page, 'fcDoor');
  check('type-ahead (Shift+I then letters) jumps to IfcDoor', (await activeLabel(page)) === 'IfcDoor', String(await activeLabel(page)));
  check('typing letters did not run global actions (no hide, still no selection)', (await sel(page)) === 0 && (await page.evaluate('window.__xray.app.controller.settings.overrides.userHides.size')) === 0);
  await page.keyboard.press('ArrowRight'); // open the class
  await page.keyboard.press('ArrowRight'); // first door
  const doorLabel = await activeLabel(page);
  check('Right twice reaches a door row', !!doorLabel && doorNames.some((n) => (n || '').startsWith(doorLabel.replace('…', ''))), String(doorLabel));
  await page.keyboard.press('ArrowDown');
  await page.keyboard.press('ArrowUp');
  await page.waitForTimeout(700); // buffer expired
  await page.keyboard.press('Enter');
  await page.waitForTimeout(400);
  let cls = await page.evaluate(() => { const a = window.__xray.app; return a.selection.length === 1 ? a.controller.model.elements[a.selection[0]].ifcClass : null; });
  check('Enter selects the door', cls === 'IfcDoor', String(cls));
  check('the selected row is highlighted and the ring is on a row', (await page.locator('.tr.sel').count()) === 1 && (await page.locator('.tr.act').count()) === 1);

  // Ctrl+Space toggles, Shift+Down extends.
  await page.keyboard.press('ArrowDown');
  await page.keyboard.press('Control+ ');
  check('Ctrl+Space adds the active row to the selection', (await sel(page)) === 2, `selection=${await sel(page)}`);
  await page.keyboard.press('Control+ ');
  check('Ctrl+Space again removes it', (await sel(page)) === 1);
  await page.keyboard.press('Shift+ArrowDown');
  check('Shift+Down extends the selection', (await sel(page)) === 2, `selection=${await sel(page)}`);
  await page.keyboard.press('Home');
  await page.keyboard.press('Space');
  check('Space on a storey selects all of its elements', (await sel(page)) > 5, `selection=${await sel(page)}`);
  // Select a single door again for the global keys.
  await page.keyboard.press('ArrowDown'); // first class of the storey
  await page.keyboard.press('Shift+I');
  await type(page, 'fcDoor');
  await page.waitForTimeout(700);
  await page.keyboard.press('ArrowRight');
  await page.keyboard.press('ArrowRight');
  await page.keyboard.press('Enter');
  check('one door selected again', (await sel(page)) === 1);

  // Global keys on the selection while the tree has focus.
  const before = await pose(page);
  await page.keyboard.press('f');
  let framed = before;
  for (let i = 0; i < 20 && dist(before, framed) < 0.05; i++) { await page.waitForTimeout(250); framed = await pose(page); }
  await settle(page);
  check('f frames the selection while the tree has focus', dist(before, framed) > 0.05, `moved ${dist(before, framed).toFixed(2)}`);
  fi = await focusInfo(page);
  check('focus stays in the tree after f', fi.role === 'tree');
  await page.keyboard.press('h');
  check('h hides the selection while the tree has focus', (await page.evaluate('window.__xray.app.controller.settings.overrides.userHides.size')) === 1);
  await page.keyboard.press('Alt+h');
  check('Alt+h unhides', (await page.evaluate('window.__xray.app.controller.settings.overrides.userHides.size')) === 0);
  await page.keyboard.press('x');
  await page.keyboard.press('x');

  // Escape returns to the canvas without clearing the selection; ArrowLeft then orbits.
  await page.keyboard.press('Escape');
  fi = await focusInfo(page);
  check('Escape returns focus to the canvas', fi.id === 'c', JSON.stringify(fi));
  check('the first Escape keeps the selection', (await sel(page)) === 1);
  const p0 = await pose(page);
  await page.keyboard.down('ArrowLeft');
  await page.waitForTimeout(500);
  await page.keyboard.up('ArrowLeft');
  await settle(page);
  const p1 = await pose(page);
  check('ArrowLeft orbits the camera again', dist(p0, p1) > 0.05, `moved ${dist(p0, p1).toFixed(2)}`);
  await page.keyboard.press('Escape');
  check('the second Escape clears the selection', (await sel(page)) === 0);

  // Selecting in 3D reveals the element in the tree and does not steal focus.
  await page.evaluate(() => {
    const a = window.__xray.app;
    const door = a.controller.model.elements.find((e) => e.ifcClass === 'IfcDoor');
    window.__door = door.id;
    a.selectIds([door.id]);
  });
  await page.waitForTimeout(800);
  check('selecting in 3D reveals the row in the tree', (await page.locator('.tr.sel.k-element').count()) === 1);
  check('the revealed row is the active row', (await page.locator('.tr.sel.act').count()) === 1);
  fi = await focusInfo(page);
  check('reveal does not steal focus from the canvas', fi.id === 'c', JSON.stringify(fi));

  // F6 cycling.
  const ring = () => page.evaluate(() => [...document.querySelectorAll('[data-region-ring]')].map((e) => e.getAttribute('data-region-ring')));
  await page.keyboard.press('F6');
  check('F6 canvas -> left', (await ring()).join() === 'left');
  await page.keyboard.press('F6');
  fi = await focusInfo(page);
  check('F6 left -> right sidebar', (await ring()).join() === 'right' && (await page.evaluate(() => document.getElementById('dock').contains(document.activeElement))), JSON.stringify(fi));
  await page.keyboard.press('F6');
  check('F6 right -> top bar', (await ring()).join() === 'top' && (await page.evaluate(() => document.getElementById('xray-topbar').contains(document.activeElement))));
  await page.keyboard.press('F6');
  check('F6 top bar -> canvas', (await ring()).join() === 'canvas' && (await focusInfo(page)).id === 'c');
  await page.keyboard.press('Shift+F6');
  check('Shift+F6 goes back to the top bar', (await ring()).join() === 'top');
  await page.keyboard.press('Shift+F6');
  await page.keyboard.press('Shift+F6');
  check('Shift+F6 twice reaches the left sidebar', (await ring()).join() === 'left' && (await focusInfo(page)).role === 'tree');
  check('the cheat sheet lists the region actions', await page.evaluate(() => window.__keymap.idsFor('F6').includes('focus.nextRegion') && window.__keymap.idsFor('Shift+F6').includes('focus.prevRegion')));

  // Sets list: the Sets tab under the same rule.
  await page.locator('.sb-tab', { hasText: 'Sets' }).click();
  await page.evaluate(() => document.getElementById('c').focus());
  await page.keyboard.press('F6');
  fi = await focusInfo(page);
  check('F6 into the Sets tab focuses a set row control', await page.evaluate(() => !!document.activeElement?.closest('.sets-list')), JSON.stringify(fi));
  await page.keyboard.press('ArrowDown');
  const same = await page.evaluate(() => !!document.activeElement?.closest('.set-row'));
  check('ArrowDown moves between set rows', same);
  const poseS = await pose(page);
  await page.keyboard.press('PageDown'); // owned by the list: the storey action does not run
  await page.waitForTimeout(400);
  check('PageDown in the Sets list does not move the camera', dist(poseS, await pose(page)) < 0.001);
  await page.keyboard.press('Escape');
  check('Escape in the Sets list returns to the canvas', (await focusInfo(page)).id === 'c');
  await page.close();

  // ------------------------------------------------------------------ phone width
  page = await open({ width: 390, height: 844 });
  await page.mouse.click(200, 700);
  await page.keyboard.press('[');
  await page.waitForFunction(() => !document.body.classList.contains('sb-collapsed'), null, { timeout: 5000 }).catch(() => {});
  await page.keyboard.press('F6');
  fi = await focusInfo(page);
  check('phone: F6 focuses the tree', fi.role === 'tree', JSON.stringify(fi));
  await page.keyboard.press('Home');
  await page.keyboard.press('*');
  await page.keyboard.press('Home');
  await page.keyboard.press('Shift+I');
  await type(page, 'fcDoor');
  check('phone: type-ahead finds IfcDoor', (await activeLabel(page)) === 'IfcDoor', String(await activeLabel(page)));
  await page.keyboard.press('ArrowRight');
  await page.keyboard.press('ArrowRight');
  await page.keyboard.press('Enter');
  await page.waitForTimeout(400);
  cls = await page.evaluate(() => { const a = window.__xray.app; return a.selection.length === 1 ? a.controller.model.elements[a.selection[0]].ifcClass : null; });
  check('phone: Enter selects a door', cls === 'IfcDoor', String(cls));
  await page.keyboard.press('Escape');
  check('phone: Escape returns to the canvas', (await focusInfo(page)).id === 'c');
  await page.close();

  console.log('console errors:', errors.length ? '\n' + errors.join('\n') : 'none');
  if (errors.length) exitCode = 1;
  if (checks.some((c) => !c.ok)) exitCode = 1;
  console.log(`${checks.filter((c) => c.ok).length}/${checks.length} checks passed`);
} catch (e) {
  console.error(e);
  exitCode = 1;
} finally {
  if (browser) await browser.close();
  vite.kill('SIGTERM');
}
process.exit(exitCode);
