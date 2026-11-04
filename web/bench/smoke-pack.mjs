// Headless check of tools/xray-pack.mjs: packs two models, opens each output from file:// in headless Chromium and asserts
// the title, element count, params, selection, panels, tool, network and console. Writes bench/pack-fzk.png.
//   node bench/smoke-pack.mjs [--keep]          (needs no dev server; SMOKE_PORT is not used)
import { spawnSync } from 'node:child_process';
import { createRequire } from 'node:module';
import { mkdirSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const repo = resolve(root, '..');
const tmp = process.env.XRAY_PACK_TMP || '/tmp/xray-pack-smoke';
rmSync(tmp, { recursive: true, force: true });
mkdirSync(tmp, { recursive: true });

const req = createRequire(import.meta.url);
let pw;
for (const c of [process.env.PLAYWRIGHT_MODULE, resolve(root, 'node_modules/playwright'), '/opt/node-tools/node_modules/playwright', '/opt/node22/lib/node_modules/playwright'].filter(Boolean)) {
  try { pw = req(c); break; } catch { /* next */ }
}
if (!pw) throw new Error('playwright not found; set PLAYWRIGHT_MODULE');

const pack = (args) => {
  const t0 = performance.now();
  const r = spawnSync(process.execPath, [resolve(root, 'tools/xray-pack.mjs'), ...args], { cwd: root, encoding: 'utf8' });
  const ms = Math.round(performance.now() - t0);
  if (r.status !== 0) throw new Error(`xray-pack ${args.join(' ')} failed (${r.status}): ${r.stderr || r.stdout}`);
  return ms;
};

const paramsFile = resolve(tmp, 'params.json');
writeFileSync(paramsFile, JSON.stringify({ schema: 'xray-params/1', sightlines: { alphaMin: 0.05, layerWeighting: 'budget' } }));

const cases = [
  {
    name: 'fzk', out: resolve(tmp, 'fzk.html'), title: 'FZK windows', elements: 82, alphaMin: 0.05, selectClass: 'IfcWindow', kiosk: true,
    args: [resolve(repo, 'models/AC20-FZK-Haus.ifc'), '--params', paramsFile, '--select', 'class:IfcWindow', '--title', 'FZK windows', '--kiosk'],
  },
  {
    name: 'building', out: resolve(tmp, 'building.html'), title: 'building', elements: 26, kiosk: false,
    args: [resolve(root, 'public/models/building.glb'), '--tools', 'xray,section,measure', '--open-tool', 'measure'], tools: ['xray', 'section', 'measure'], openTool: 'measure',
  },
];

const browser = await pw.chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
let failed = 0;
const check = (label, ok, detail = '') => {
  console.log(`  ${ok ? 'ok  ' : 'FAIL'} ${label}${detail ? ` (${detail})` : ''}`);
  if (!ok) failed++;
};

try {
  for (const c of cases) {
    const packMs = pack([...c.args, '-o', c.out, '--force', '--quiet']);
    const withReaderMs = pack([...c.args, '-o', c.out.replace('.html', '-ifc.html'), '--force', '--quiet', '--ifc-reader']);
    const size = statSync(c.out).size;
    const sizeIfc = statSync(c.out.replace('.html', '-ifc.html')).size;
    console.log(`${c.name}: pack ${packMs} ms; ${(size / 1048576).toFixed(2)} MB, with --ifc-reader ${(sizeIfc / 1048576).toFixed(2)} MB`);

    const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
    const errors = [];
    const requests = [];
    page.on('console', (m) => { if (m.type() === 'error') errors.push(`[console] ${m.text()}`); });
    page.on('pageerror', (e) => errors.push(`[pageerror] ${e.message}`));
    page.on('request', (r) => { const u = r.url(); if (!u.startsWith('file://') && !u.startsWith('data:') && !u.startsWith('blob:')) requests.push(u); });
    page.on('requestfailed', (r) => errors.push(`[requestfailed] ${r.url()}`));
    await page.goto(pathToFileURL(c.out).href);
    await page.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: 120000 });
    await page.waitForTimeout(1500); // boot's tool retry and the panel transitions
    const info = await page.evaluate(`(() => {
      const app = window.__xray.app;
      const els = app.controller.model.elements;
      const sel = app.selection;
      return {
        error: window.__xrayError || '', title: document.title, model: app.modelName, elements: els.length,
        alphaMin: app.settings.sightlines.alphaMin, layerWeighting: app.settings.sightlines.layerWeighting,
        selected: sel.length, selectedClasses: [...new Set(sel.map((i) => els[i].ifcClass))],
        windows: els.filter((e) => e.ifcClass === 'IfcWindow').length,
        sbCollapsed: document.body.classList.contains('sb-collapsed'), dkCollapsed: document.body.classList.contains('dk-collapsed'),
        picker: Object.keys(window.__xrayEmbeddedModels || {}),
        boot: Object.keys(window.__xrayBoot || {}),
        toolbarButtons: document.querySelectorAll('[data-tool-id]').length,
      };
    })()`);
    console.log('  ' + JSON.stringify(info));
    check('no startup error', !info.error, info.error);
    check('title', info.title === c.title, info.title);
    check('model name', info.model === (c.name === 'fzk' ? 'AC20-FZK-Haus' : 'building'), info.model);
    check(`element count ${c.elements}`, info.elements === c.elements, String(info.elements));
    check('only the packed model is embedded', info.picker.length === 1, info.picker.join(','));
    if (c.alphaMin !== undefined) {
      check('sightlines.alphaMin 0.05', info.alphaMin === c.alphaMin, String(info.alphaMin));
      check("layerWeighting 'budget'", info.layerWeighting === 'budget', info.layerWeighting);
      check('selection = all IfcWindow', info.selected === info.windows && info.selected > 0 && info.selectedClasses.join() === c.selectClass, `${info.selected} of ${info.windows}`);
    }
    check(c.kiosk ? 'both panels collapsed' : 'panels left as they were', c.kiosk ? info.sbCollapsed && info.dkCollapsed : true, `sb=${info.sbCollapsed} dk=${info.dkCollapsed}`);
    if (c.tools) check('boot carries tools and openTool', info.boot.includes('tools') && info.boot.includes('openTool'), info.boot.join(','));
    check('zero non-file network requests', requests.length === 0, requests.join(', '));
    check('zero console errors', errors.length === 0, errors.join(' | '));
    if (c.name === 'fzk') await page.screenshot({ path: resolve(here, 'pack-fzk.png') });
    await page.close();
  }
} finally {
  await browser.close();
}
console.log(failed ? `${failed} check(s) FAILED` : 'smoke-pack: all checks passed');
process.exit(failed ? 1 : 0);
