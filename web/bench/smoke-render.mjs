// Headless smoke test for the renderer: starts vite, opens /demo.html, screenshots to bench/smoke.png.
// Usage: node bench/smoke-render.mjs [procedural|building] [--out bench/smoke.png]
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const model = process.argv[2] && !process.argv[2].startsWith('--') ? process.argv[2] : 'procedural';
const qIdx = process.argv.indexOf('--query');
const extraQuery = qIdx > 0 ? '&' + process.argv[qIdx + 1] : '';
const outIdx = process.argv.indexOf('--out');
const out = outIdx > 0 ? resolve(process.argv[outIdx + 1]) : resolve(here, model === 'procedural' ? 'smoke.png' : `smoke-${model}.png`);
const port = Number(process.env.SMOKE_PORT ?? 5199);

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
    try { const r = await fetch(`http://127.0.0.1:${port}/demo.html`); if (r.ok) return; } catch { /* retry */ }
    await new Promise((r) => setTimeout(r, 200));
  }
  throw new Error('vite did not start:\n' + viteLog);
}

let browser;
let exitCode = 0;
try {
  await waitForServer();
  browser = await chromium.launch({
    args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'],
  });
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  const errors = [];
  page.on('console', (m) => { if (m.type() === 'error' || m.type() === 'warning') errors.push(`[${m.type()}] ${m.text()}`); });
  page.on('pageerror', (e) => errors.push(`[pageerror] ${e.message}`));
  await page.goto(`http://127.0.0.1:${port}/demo.html?model=${model}${extraQuery}`);
  await page.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: 120000 });
  const err = await page.evaluate('window.__xrayError');
  if (err) { errors.push(`[app] ${err}`); exitCode = 1; }
  await page.waitForTimeout(500);
  await page.screenshot({ path: out });
  const info = await page.evaluate('window.__xrayInfo');
  const slim = info ? { ...info, classes: undefined, classCount: [...new Set(info.classes)].length } : null;
  console.log('info:', JSON.stringify(slim));
  console.log('element count:', info?.elements);
  console.log('screenshot:', out);
  console.log('console errors/warnings:', errors.length ? '\n' + errors.join('\n') : 'none');
  if (errors.some((e) => !e.startsWith('[warning]'))) exitCode = 1;
} catch (e) {
  console.error(e);
  exitCode = 1;
} finally {
  if (browser) await browser.close();
  vite.kill('SIGTERM');
}
process.exit(exitCode);
