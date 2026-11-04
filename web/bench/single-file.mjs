// Opens web/dist-single/xray-viewer.html from file:// in headless Chromium, waits for window.__xrayReady, checks for
// console errors and network requests, and screenshots to bench/single-file.png.
//   node bench/single-file.mjs [--model plumbing] [--out bench/single-file.png]
import { createRequire } from 'node:module';
import { dirname, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const arg = (k, d) => { const i = process.argv.indexOf(k); return i > 0 ? process.argv[i + 1] : d; };
const out = resolve(arg('--out', resolve(here, 'single-file.png')));
const model = arg('--model', '');
const file = resolve(root, 'dist-single', 'xray-viewer.html');

const req = createRequire(import.meta.url);
let pw;
for (const c of [process.env.PLAYWRIGHT_MODULE, resolve(root, 'node_modules/playwright'), '/opt/node-tools/node_modules/playwright', '/opt/node22/lib/node_modules/playwright'].filter(Boolean)) {
  try { pw = req(c); break; } catch { /* next */ }
}
if (!pw) throw new Error('playwright not found; set PLAYWRIGHT_MODULE');

const browser = await pw.chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
let code = 0;
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  const errors = [];
  const requests = [];
  page.on('console', (m) => { if (m.type() === 'error' || m.type() === 'warning') errors.push(`[${m.type()}] ${m.text()}`); });
  page.on('pageerror', (e) => errors.push(`[pageerror] ${e.message}`));
  page.on('request', (r) => { if (!r.url().startsWith('file://') && !r.url().startsWith('data:') && !r.url().startsWith('blob:')) requests.push(r.url()); });
  page.on('requestfailed', (r) => errors.push(`[requestfailed] ${r.url()}`));
  await page.goto(pathToFileURL(file).href + (model ? `?model=${model}` : ''));
  await page.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: 120000 });
  const err = await page.evaluate('window.__xrayError');
  if (err) { errors.push(`[app] ${err}`); code = 1; }
  await page.waitForTimeout(800);
  await page.screenshot({ path: out });
  const info = await page.evaluate(`({
    url: location.href, title: document.title,
    model: window.__xray.app.modelName, elements: window.__xray.app.controller.model.elements.length,
    picker: window.__xray.app.gui.controllersRecursive().find((c) => c.property === 'model')?._values ?? null,
    sets: Object.keys(localStorage).filter((k) => k.startsWith('xray.sets.')),
    msg: document.getElementById('xray-message')?.textContent || '',
  })`);
  console.log(JSON.stringify(info));
  console.log('screenshot:', out);
  console.log('non-file requests:', requests.length ? requests.join(', ') : 'none');
  console.log('console errors/warnings:', errors.length ? '\n' + errors.join('\n') : 'none');
  if (errors.length || requests.length) code = 1;
} catch (e) { console.error(e); code = 1; } finally { await browser.close(); }
process.exit(code);
