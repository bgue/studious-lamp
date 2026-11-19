// Save cleaned copy on a large synthetic IFC (tools/make_big_ifc.py): opens the file through the file input, picks every 7th duct and
// pipe segment as the elements to remove, then runs the cleaned copy end to end (read, index, plan, write; target none) in the worker and
// on the main thread, recording the time, the JS heap before and after (after a forced GC) and the output size.
//   node bench/bench-ifc-clean.mjs --file /tmp/xray-big-ifc/big-100000.ifc [--label run]
// env: SMOKE_PORT (default 5796), XRAY_VITE_CACHE_DIR
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { statSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { loadavg, cpus } from 'node:os';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const args = process.argv.slice(2);
const arg = (k, d) => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : d; };
const file = resolve(arg('--file', '/tmp/xray-big-ifc/big-100000.ifc'));
const label = arg('--label', 'run');
const port = Number(process.env.SMOKE_PORT ?? 5796);
let pw;
for (const c of [process.env.PLAYWRIGHT_MODULE, resolve(root, 'node_modules/playwright'), '/opt/node-tools/node_modules/playwright', '/opt/node22/lib/node_modules/playwright'].filter(Boolean)) {
  try { pw = createRequire(import.meta.url)(c); break; } catch { /* next */ }
}
const vite = spawn(resolve(root, 'node_modules/.bin/vite'), ['--config', 'bench/vite.smoke.config.mjs', '--host', '127.0.0.1', '--port', String(port), '--strictPort'], { cwd: root, stdio: 'ignore' });
let browser;
const out = { file, sizeMb: Math.round(statSync(file).size / 1048576), cpus: cpus().length, loadavgStart: loadavg()[0] };
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
  const ids = await page.evaluate(() => window.__xray.app.controller.model.elements.filter((e) => /^Ifc(Duct|Pipe)Segment$/i.test(e.ifcClass)).filter((_, i) => i % 7 === 0).map((e) => e.id));
  out.toRemove = ids.length;
  await new Promise((r) => setTimeout(r, 1500));
  const h0 = await heap();
  await page.evaluate(() => { window.__peak = 0; window.__t = setInterval(() => { window.__peak = Math.max(window.__peak, performance.memory.usedJSHeapSize); }, 20); });
  out.runs = [];
  for (const mode of ['worker', 'main', 'worker']) {
    const t0 = Date.now();
    const l0 = loadavg()[0];
    const s = await page.evaluate(({ ids, forceMainThread }) => window.__xrayIfcSave.saveCleaned({ ids, target: 'none', withClassification: false, forceMainThread }), { ids, forceMainThread: mode === 'main' });
    const wall = Date.now() - t0;
    const hAfter = await heap();
    const peak = await page.evaluate('window.__peak');
    const f = s.files[0];
    out.runs.push({ requested: mode, mode: s.mode, wallMs: wall, apiMs: Math.round(s.ms), loadavg: [l0, loadavg()[0]], removed: f.removed, cascaded: f.cascaded, kept: f.kept, linesDeleted: f.linesDeleted, sourceMb: +(f.sourceBytes / 1048576).toFixed(1), outputMb: +(f.bytes / 1048576).toFixed(1), heapBeforeMb: +(h0 / 1048576).toFixed(1), heapAfterMb: +(hAfter / 1048576).toFixed(1), growthMb: +((hAfter - h0) / 1048576).toFixed(1), peakGrowthMb: +((peak - h0) / 1048576).toFixed(1) });
    await page.evaluate(() => { window.__peak = 0; });
  }
  out.output = await page.evaluate(async () => {
    const o = window.__xrayIfcSave.lastOutputs()[0];
    const tail = await o.blob.slice(Math.max(0, o.blob.size - 400)).text();
    return { name: o.name, size: o.blob.size, endsOk: /ENDSEC;\s*END-ISO-10303-21;\s*$/.test(tail), block: /XRAY-BEGIN[^\n]*removed=\d+ kept=\d+/.test(tail) };
  });
  out.loadavgEnd = loadavg()[0];
} catch (e) {
  out.error = String(e?.stack ?? e);
} finally {
  await browser?.close();
  vite.kill('SIGTERM');
}
console.log(JSON.stringify(out, null, 2));
writeFileSync(resolve(here, `ifc-clean-large-${label}.json`), JSON.stringify(out, null, 2));
process.exit(out.error ? 1 : 0);
