// Save IFC on a large synthetic IFC (tools/make_big_ifc.py): opens the file through the file input, classifies with the rules,
// then saves with the dialog's pipeline (target none: nothing is written to disk) and records the JS heap before and after (after a
// forced GC), the peak heap during the save, the save time and the output size.
//   node bench/bench-ifc-save.mjs --file /tmp/xray-big-ifc/big-100000.ifc [--out bench/ifc-save-large-<label>.json] [--label run]
// env: SMOKE_PORT (default 5772)
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { statSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { loadavg } from 'node:os';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const args = process.argv.slice(2);
const arg = (k, d) => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : d; };
const file = resolve(arg('--file', '/tmp/xray-big-ifc/big-100000.ifc'));
const label = arg('--label', 'run');
const port = Number(process.env.SMOKE_PORT ?? 5772);
let pw;
for (const c of [process.env.PLAYWRIGHT_MODULE, resolve(root, 'node_modules/playwright'), '/opt/node-tools/node_modules/playwright', '/opt/node22/lib/node_modules/playwright'].filter(Boolean)) {
  try { pw = createRequire(import.meta.url)(c); break; } catch { /* next */ }
}
const vite = spawn(resolve(root, 'node_modules/.bin/vite'), ['--config', 'bench/vite.smoke.config.mjs', '--host', '127.0.0.1', '--port', String(port), '--strictPort'], { cwd: root, stdio: 'ignore' });
let browser;
const out = { file, sizeMb: Math.round(statSync(file).size / 1048576), loadavgStart: loadavg()[0] };
try {
  for (let i = 0; i < 100; i++) { try { if ((await fetch(`http://127.0.0.1:${port}/`)).ok) break; } catch { await new Promise((r) => setTimeout(r, 200)); } }
  browser = await pw.chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist', '--enable-precise-memory-info', '--js-flags=--expose-gc'] });
  const page = await (await browser.newContext({ viewport: { width: 1000, height: 700 } })).newPage();
  page.setDefaultTimeout(900000);
  const cdp = await page.context().newCDPSession(page);
  await page.goto(`http://127.0.0.1:${port}/?model=building`);
  await page.waitForFunction('window.__xrayReady === true', null, { timeout: 180000 });
  const heap = async () => { await cdp.send('HeapProfiler.collectGarbage'); await cdp.send('HeapProfiler.collectGarbage'); return page.evaluate('performance.memory.usedJSHeapSize'); };
  await page.setInputFiles('#xray-open-file-input', [file]);
  await page.waitForFunction(() => /^Loaded \d+ elements/.test(window.__xray.app.panel.controllersRecursive().find((c) => c.property === 'status').getValue()), null, { timeout: 900000 });
  out.elements = await page.evaluate('window.__xray.app.controller.model.elements.length');
  await page.evaluate(() => window.__xrayClassify.configure({ provider: 'off' }));
  await page.evaluate(() => window.__xrayClassify.classify('all'));
  out.classified = (await page.evaluate(() => window.__xrayClassify.stats())).total;
  await new Promise((r) => setTimeout(r, 1500));
  const h0 = await heap();
  await page.evaluate(() => { window.__peak = 0; window.__t = setInterval(() => { window.__peak = Math.max(window.__peak, performance.memory.usedJSHeapSize); }, 20); });
  out.saves = [];
  for (const mode of ['worker', 'main']) {
    const t0 = Date.now();
    const s = await page.evaluate((forceMainThread) => window.__xrayIfcSave.save({ target: 'none', forceMainThread }), mode === 'main');
    const hAfter = await heap();
    const peak = await page.evaluate('window.__peak');
    out.saves.push({ requested: mode, mode: s.mode, ms: Date.now() - t0, lines: s.files[0].lines, outputMb: Math.round(s.files[0].bytes / 1048576), heapBeforeMb: +(h0 / 1048576).toFixed(1), heapAfterMb: +(hAfter / 1048576).toFixed(1), growthMb: +((hAfter - h0) / 1048576).toFixed(1), peakGrowthMb: +((peak - h0) / 1048576).toFixed(1) });
    await page.evaluate(() => { window.__peak = 0; });
  }
  // the output really holds the block and ends with the original tail
  const check = await page.evaluate(async () => {
    const o = window.__xrayIfcSave.lastOutputs()[0];
    const tail = await o.blob.slice(Math.max(0, o.blob.size - 400)).text();
    return { name: o.name, size: o.blob.size, endsOk: /ENDSEC;\s*END-ISO-10303-21;\s*$/.test(tail) };
  });
  out.output = check;
  out.loadavgEnd = loadavg()[0];
} catch (e) {
  out.error = String(e?.stack ?? e);
} finally {
  await browser?.close();
  vite.kill('SIGTERM');
}
console.log(JSON.stringify(out, null, 2));
writeFileSync(resolve(here, `ifc-save-large-${label}.json`), JSON.stringify(out, null, 2));
process.exit(out.error ? 1 : 0);
