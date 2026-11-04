// Headless smoke test for the sidebar: starts vite, loads /?model=building, expands the storey and IfcDuctSegment
// nodes with DOM clicks, clicks the duct row, waits 1 s and screenshots to bench/smoke-sidebar.png (1600x900).
// Also checks the layout (canvas fills the stage, collapse to the 28 px rail and back, persisted state).
// Usage: node bench/smoke-sidebar.mjs [--out bench/smoke-sidebar.png]
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const outIdx = process.argv.indexOf('--out');
const out = outIdx > 0 ? resolve(process.argv[outIdx + 1]) : resolve(here, 'smoke-sidebar.png');
const port = Number(process.env.SMOKE_PORT ?? 5198);

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

let browser;
let exitCode = 0;
try {
  await waitForServer();
  browser = await chromium.launch({
    args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'],
  });
  const page = await browser.newPage({ viewport: { width: 1600, height: 900 } });
  const errors = [];
  page.on('console', (m) => { if (m.type() === 'error' || m.type() === 'warning') errors.push(`[${m.type()}] ${m.text()}`); });
  page.on('pageerror', (e) => errors.push(`[pageerror] ${e.message}`));
  await page.goto(`http://127.0.0.1:${port}/?model=building`);
  await page.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: 120000 });
  const err = await page.evaluate('window.__xrayError');
  if (err) { errors.push(`[app] ${err}`); exitCode = 1; }

  // Expand the storey (if not already) and the IfcDuctSegment class by clicking their carets.
  const storey = page.locator('.tr.k-storey').first();
  await storey.waitFor({ timeout: 10000 });
  if ((await storey.getAttribute('aria-expanded')) !== 'true') await storey.locator('.caret').click();
  const ductClass = page.locator('.tr.k-class', { hasText: 'IfcDuctSegment' });
  await ductClass.waitFor({ timeout: 10000 });
  await ductClass.locator('.caret').click();
  const duct = page.locator('.tr.k-element').first();
  await duct.waitFor({ timeout: 10000 });
  console.log('duct row:', JSON.stringify(await duct.getAttribute('title')));
  await duct.click();
  await page.waitForTimeout(1000);
  await page.screenshot({ path: out });
  console.log('screenshot:', out);

  const selected = await page.evaluate('window.__xray.app.selection.length');
  check('clicking the duct row selects one element', selected === 1, `selection=${selected}`);
  check('selected row is highlighted', (await page.locator('.tr.sel').count()) >= 1);
  const footer = await page.locator('.props-grid dd .pv-t').allTextContents(); // the value text; each row also has a ⋯ menu button
  console.log('properties:', JSON.stringify(footer));
  check('properties footer shows a globalId and class', footer[0]?.length > 5 && footer[1] === 'IfcDuctSegment');
  const buckets = await page.locator('.tr.k-element .dot').first().getAttribute('class');
  check('selected duct has the focus dot', /b-focus/.test(buckets ?? ''), buckets ?? '');

  // Layout: sidebar 300 px, canvas fills the rest, drawing buffer matches CSS size.
  const geo = async () => page.evaluate(() => {
    const r = (id) => document.querySelector(id).getBoundingClientRect();
    const c = document.getElementById('c');
    const dpr = window.devicePixelRatio;
    return { sb: r('#sidebar').width, stage: r('#stage').width, cw: c.clientWidth, ch: c.clientHeight, bw: c.width, bh: c.height, dpr, vw: window.innerWidth, vh: window.innerHeight };
  });
  let g = await geo();
  console.log('layout (expanded):', JSON.stringify(g));
  check('sidebar is 300 px', Math.round(g.sb) === 300);
  check('canvas fills the remaining width', g.cw === g.vw - 300 && g.ch === g.vh);
  check('canvas drawing buffer matches CSS size (not stretched)', Math.abs(g.bw - g.cw * g.dpr) <= 1 && Math.abs(g.bh - g.ch * g.dpr) <= 1);

  // Collapse with "[" and check the rail, then the state persists across a reload.
  await page.mouse.click(1000, 450); // focus the page body away from inputs
  await page.keyboard.press('[');
  await page.waitForTimeout(500);
  g = await geo();
  console.log('layout (collapsed):', JSON.stringify(g));
  check('collapsed sidebar is a 28 px rail', Math.round(g.sb) === 28);
  check('canvas grew to fill and the buffer was resized', g.cw === g.vw - 28 && Math.abs(g.bw - g.cw * g.dpr) <= 1);
  await page.reload();
  await page.waitForFunction('window.__xrayReady === true', null, { timeout: 120000 });
  check('collapsed state persisted in localStorage', await page.evaluate(() => document.body.classList.contains('sb-collapsed')));
  await page.keyboard.press('[');
  await page.waitForTimeout(500);
  g = await geo();
  check('"[" expands it again', Math.round(g.sb) === 300);

  // Sets tab: seeded defaults for the building model.
  await page.locator('.sb-tab', { hasText: 'Sets' }).click();
  const names = await page.locator('.set-row .set-name').allTextContents(); // one-line rows (wave 5): the name is the apply button
  console.log('sets:', JSON.stringify(names));
  check('default sets are seeded', names.includes('Duct run') && names.includes('Roof beams'));
  await page.locator('.set-row', { hasText: 'Duct run' }).locator('.set-name').click();
  await page.waitForTimeout(300);
  const n = await page.evaluate('window.__xray.app.selection.length');
  check('Apply selects the set', n === 3, `selection=${n}`);

  console.log('console errors/warnings:', errors.length ? '\n' + errors.join('\n') : 'none');
  if (errors.some((e) => !e.startsWith('[warning]'))) exitCode = 1;
  if (checks.some((c) => !c.ok)) exitCode = 1;
} catch (e) {
  console.error(e);
  exitCode = 1;
} finally {
  if (browser) await browser.close();
  vite.kill('SIGTERM');
}
process.exit(exitCode);
