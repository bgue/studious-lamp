// Headless check for the cleanup simplification tools and "Save cleaned model" on process-plant (or the model named on the
// command line): preview and apply decimation (triangle count drops), remove small details, instance duplicates, weld, read the
// CleanupPlan, open the summary dialog from the panel, save the glb (the download is captured), re-open it in the viewer and
// check the element count and that a selected element shows its GlobalId, check the phone layout, and zero console errors.
// Screenshots: bench/cleanup-simplify.png, bench/cleanup-save.png, bench/cleanup-simplify-phone.png.
// Usage: SMOKE_PORT=5760 node bench/smoke-cleanup-simplify.mjs [model]
import { spawn } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const port = Number(process.env.SMOKE_PORT ?? 5760);
const model = process.argv[2] ?? 'process-plant';

function loadPlaywright() {
  const candidates = [process.env.PLAYWRIGHT_MODULE, resolve(root, 'node_modules/playwright'), '/opt/node-tools/node_modules/playwright', '/opt/node22/lib/node_modules/playwright'].filter(Boolean);
  for (const c of candidates) {
    try { return createRequire(import.meta.url)(c); } catch { /* next */ }
  }
  throw new Error('playwright not found; set PLAYWRIGHT_MODULE');
}
const { chromium } = loadPlaywright();

const vite = spawn(resolve(root, 'node_modules/.bin/vite'), ['--config', 'bench/vite.smoke.config.mjs', '--host', '127.0.0.1', '--port', String(port), '--strictPort'], { cwd: root, stdio: ['ignore', 'pipe', 'pipe'], env: { ...process.env, XRAY_VITE_CACHE_DIR: process.env.XRAY_VITE_CACHE_DIR ?? `/tmp/xray-vite-cache-cleanup-${port}` } });
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

let failed = false;
function check(name, ok, detail = '') {
  if (!ok) failed = true;
  console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${detail ? ` (${detail})` : ''}`);
}

async function openPage(browser, viewport) {
  const ctx = await browser.newContext({ viewport, acceptDownloads: true });
  const page = await ctx.newPage();
  const errors = [];
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', (e) => errors.push(`[pageerror] ${e.message}`));
  if (process.env.DEBUG_SMOKE) { page.on('console', (m) => console.log(`    [console ${m.type()}] ${m.text()}`)); page.on('framenavigated', (f) => console.log(`    [navigated] ${f.url()}`)); }
  await page.goto(`http://127.0.0.1:${port}/?model=${model}`);
  await page.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: 180000 });
  const err = await page.evaluate('window.__xrayError');
  if (err) errors.push(err);
  await page.evaluate(() => localStorage.clear());
  return { ctx, page, errors };
}

/** Open a lil-gui folder by its title (and its parents) so its controls are on screen. */
async function openFolder(page, titles) {
  // At each level open the folder and close its siblings, so the cleanup folders sit near the top of the dock.
  for (const t of titles) {
    await page.evaluate((title) => {
      const el = [...document.querySelectorAll('.lil-gui .lil-title')].find((e) => e.textContent.trim() === title);
      if (!el) return;
      const folder = el.parentElement;
      for (const sib of folder.parentElement.children) {
        if (sib !== folder && sib.classList.contains('lil-gui') && !sib.classList.contains('lil-closed')) sib.querySelector(':scope > .lil-title').click();
      }
      if (folder.classList.contains('lil-closed')) el.click();
    }, t);
    await page.waitForTimeout(1200);
  }
  await page.evaluate((title) => {
    const el = [...document.querySelectorAll('.lil-gui .lil-title')].find((e) => e.textContent.trim() === title);
    el?.scrollIntoView({ block: 'start' });
  }, titles[0]);
}

let browser;
try {
  await waitForServer();
  browser = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });

  // Warm-up: the dev server pre-bundles three's GLTFExporter the first time the lazy chunk asks for it and answers that first
  // request with 504 "Outdated Optimize Dep". Trigger it once in a throwaway page so the real pages see a settled cache.
  {
    const w = await openPage(browser, { width: 800, height: 600 });
    for (let i = 0; i < 3; i++) {
      const ok = await w.page.evaluate(() => import('/src/cleanup/glbExport.ts').then((m) => m.exportCleanedGlb([], { position: new Float32Array(0), normal: new Float32Array(0), index: new Uint32Array(0), ranges: [], vertexRanges: [] }, { removedGlobalIds: [], replacements: [], mergedGroups: [] }, { stripProps: false })).then(() => true, () => false));
      if (ok) break;
      await w.page.waitForTimeout(3000);
    }
    await w.ctx.close();
  }

  // ------------------------------------------------------------ desktop
  const { ctx, page, errors } = await openPage(browser, { width: 1600, height: 900 });
  console.log(`\n=== ${model} ===`);
  const n = await page.evaluate(() => window.__xray.app.loaded.model.elements.filter((e, i) => window.__xray.app.loaded.geometry.ranges[i].count > 0).length);
  console.log(`elements with geometry: ${n}`);

  // Decimation: preview first (nothing changes), then apply.
  await page.evaluate(() => {
    const o = window.__xrayCleanup.simplify.options;
    o.decimate.mode = 'target ratio';
    o.decimate.ratio = 0.4;
    o.decimate.minTriangles = 60;
  });
  const dec = await page.evaluate(() => window.__xrayCleanup.simplify.preview('decimate'));
  console.log('  decimate preview:', JSON.stringify(dec));
  check('decimation preview lists elements and a triangle drop', dec && dec.elements > 0 && dec.trianglesAfter < dec.trianglesBefore, dec ? `${dec.elements} elements, ${dec.trianglesBefore} to ${dec.trianglesAfter}` : 'null');
  check('decimation preview estimates a smaller size', dec && dec.bytesAfter < dec.bytesBefore, dec ? `${dec.bytesBefore} to ${dec.bytesAfter}` : '');
  const tinted = await page.evaluate(() => {
    const c = window.__xray.renderer.state.color;
    let k = 0;
    for (let i = 0; i < c.length / 3; i++) if (Math.abs(c[i * 3] - 1) < 1e-6 && Math.abs(c[i * 3 + 1] - 0.1) < 1e-6) k++;
    return k;
  });
  check('preview tints the affected elements', dec && tinted === dec.elements, `${tinted}`);
  const before = await page.evaluate(() => window.__xrayCleanup.simplify.plan().stats);
  check('preview alone stages nothing', before.simplified === 0 && before.trianglesAfter === before.trianglesBefore);
  await openFolder(page, ['Model cleanup', 'Simplify', 'Decimate mesh']);
  await page.waitForTimeout(1500);
  await page.screenshot({ path: resolve(here, 'cleanup-simplify.png'), timeout: 120000 });
  const dApplied = await page.evaluate(() => window.__xrayCleanup.simplify.apply());
  const afterDec = await page.evaluate(() => window.__xrayCleanup.simplify.plan().stats);
  check('apply stages the simplified elements', afterDec.simplified === dec.elements && afterDec.trianglesAfter < afterDec.trianglesBefore, `${afterDec.simplified} simplified, ${afterDec.trianglesBefore} to ${afterDec.trianglesAfter}`);
  check('apply returned the summary', dApplied && dApplied.elements === dec.elements);

  // Small details: widen the size until something matches.
  let det = null;
  for (const size of [0.05, 0.1, 0.2, 0.4]) {
    det = await page.evaluate((s) => { window.__xrayCleanup.simplify.options.details.maxSize = s; return window.__xrayCleanup.simplify.preview('details'); }, size);
    if (det && det.elements > 0) { console.log(`  small details at ${size} m: ${det.elements}`); break; }
  }
  check('small details preview finds elements', det && det.elements > 0, det ? det.text : 'null');
  const hid0 = await page.evaluate(() => window.__xray.app.controller.settings.overrides.userHides.size);
  await page.evaluate(() => window.__xrayCleanup.simplify.apply());
  const hid1 = await page.evaluate(() => window.__xray.app.controller.settings.overrides.userHides.size);
  check('removing small details hides them in the viewer', hid1 === hid0 + det.elements, `${hid0} to ${hid1}`);

  // Instances and weld.
  const inst = await page.evaluate(() => window.__xrayCleanup.simplify.preview('instances'));
  console.log('  instances preview:', inst && inst.text);
  await page.evaluate(() => window.__xrayCleanup.simplify.apply());
  const weld = await page.evaluate(() => window.__xrayCleanup.simplify.preview('weld'));
  console.log('  weld preview:', weld && weld.text);
  await page.evaluate(() => window.__xrayCleanup.simplify.apply());

  const plan = await page.evaluate(() => {
    const p = window.__xrayCleanup.simplify.plan();
    return { stats: p.stats, removed: p.removedGlobalIds.length, repl: p.replacements.length, groups: p.mergedGroups.length, keys: Object.keys(p), reasons: Object.values(p.removalReasons).flat().filter((v, i, a) => a.indexOf(v) === i) };
  });
  console.log('  plan:', JSON.stringify(plan));
  check('CleanupPlan has the four parts', ['removedGlobalIds', 'replacements', 'mergedGroups', 'stats'].every((k) => plan.keys.includes(k)));
  check('plan counts add up', plan.removed === plan.stats.removed && plan.repl === plan.stats.simplified && plan.stats.elementsAfter === plan.stats.elementsBefore - plan.stats.removed);
  check('plan: fewer triangles and a smaller estimated file', plan.stats.trianglesAfter < plan.stats.trianglesBefore && plan.stats.bytesAfter < plan.stats.bytesBefore, `${plan.stats.trianglesBefore} to ${plan.stats.trianglesAfter}, ${plan.stats.bytesBefore} to ${plan.stats.bytesAfter} bytes`);

  // Save through the panel button and the dialog; capture the download.
  await openFolder(page, ['Model cleanup']);
  await page.evaluate(() => {
    const b = [...document.querySelectorAll('.lil-gui .lil-controller.lil-function .lil-name')].find((e) => e.textContent.trim() === 'Save cleaned model');
    b.click();
  });
  await page.waitForSelector('#xray-save-dialog');
  const rows = await page.evaluate(() => Object.fromEntries([...document.querySelectorAll('#xray-save-dialog td[data-row]')].map((e) => [e.dataset.row, e.textContent])));
  console.log('  dialog:', JSON.stringify(rows));
  check('dialog shows removed, simplified, instanced, triangles and size', ['Removed', 'Simplified', 'Instanced', 'Triangles drawn', 'Estimated size'].every((k) => rows[k]));
  await page.screenshot({ path: resolve(here, 'cleanup-save.png'), timeout: 120000 });
  const [download] = await Promise.all([page.waitForEvent('download', { timeout: 120000 }), page.click('#xray-save-dialog [data-act=save]')]);
  const path = await download.path();
  const glb = readFileSync(path);
  console.log(`  downloaded ${download.suggestedFilename()} ${glb.length} bytes`);
  check('the download is a glb', glb.readUInt32LE(0) === 0x46546c67 && download.suggestedFilename().endsWith('.glb'));
  const jsonLen = glb.readUInt32LE(12);
  const json = JSON.parse(glb.subarray(20, 20 + jsonLen).toString('utf8'));
  const gids = await page.evaluate(() => window.__xray.app.loaded.model.elements.map((e) => e.globalId));
  check('glb nodes are named by GlobalId of the original model', json.nodes.length === plan.stats.elementsAfter && json.nodes.every((nd) => gids.includes(nd.name)), `${json.nodes.length} nodes`);
  check('glb nodes carry class in extras', json.nodes.every((nd) => typeof nd.extras?.ifcClass === 'string'));
  check('instancing shares meshes', plan.stats.instancedElements === 0 || json.meshes.length < json.nodes.length, `${json.meshes.length} meshes for ${json.nodes.length} nodes`);
  await page.waitForSelector('#xray-save-dialog [data-act=open]:not([hidden])');

  // Re-open the saved file.
  await page.click('#xray-save-dialog [data-act=open]');
  await page.waitForFunction((nn) => window.__xray.app.loaded.model.elements.length === nn, plan.stats.elementsAfter, { timeout: 60000 });
  await page.waitForTimeout(800);
  const re = await page.evaluate(() => {
    const app = window.__xray.app;
    const els = app.loaded.model.elements;
    app.selectIds([els[0].id]);
    return { n: els.length, name: app.modelName, gid: els[0].globalId, cls: els[0].ifcClass, sel: app.selection.map((id) => els[id].globalId) };
  });
  check('the re-opened file has the expected element count', re.n === plan.stats.elementsAfter, `${re.n}, model ${re.name}`);
  check('a selected element is the one with that GlobalId', re.sel[0] === re.gid && gids.includes(re.gid), re.gid);
  await page.waitForTimeout(600);
  const shown = await page.evaluate((g) => document.body.innerText.includes(g), re.gid);
  check('the GlobalId is shown in the viewer after selecting', shown, re.gid);
  const trisBack = await page.evaluate(() => { const g = window.__xray.app.loaded.geometry; return g.ranges.reduce((a, r) => a + r.count / 3, 0); });
  console.log(`  re-opened triangles ${trisBack}`);
  check('the re-opened triangle count matches the plan', trisBack === plan.stats.trianglesAfter, `${trisBack} vs ${plan.stats.trianglesAfter}`);
  const real = errors.filter((e) => !/favicon/i.test(e));
  check('no console errors (desktop)', real.length === 0, real.slice(0, 3).join(' | '));
  await ctx.close();

  // ------------------------------------------------------------ phone
  const ph = await openPage(browser, { width: 390, height: 844 });
  await ph.page.evaluate(() => { const o = window.__xrayCleanup.simplify.options; o.decimate.ratio = 0.4; o.decimate.minTriangles = 60; });
  await ph.page.evaluate(() => window.__xrayCleanup.simplify.preview('decimate'));
  await ph.page.evaluate(() => window.__xrayCleanup.simplify.apply());
  await ph.page.evaluate(() => document.querySelector('.dk-toggle')?.click());
  await ph.page.waitForTimeout(500);
  await openFolder(ph.page, ['Model cleanup', 'Simplify', 'Decimate mesh']);
  await ph.page.waitForTimeout(1500);
  const panel = await ph.page.evaluate(() => {
    const d = document.querySelector('#dock').getBoundingClientRect();
    return { right: d.right, vw: window.innerWidth, scrollW: document.documentElement.scrollWidth, dockScroll: document.querySelector('#dk-body').scrollWidth, dockClient: document.querySelector('#dk-body').clientWidth };
  });
  check('[phone] the panel fits the screen with the Simplify folder open', panel.right <= panel.vw + 1 && panel.scrollW <= panel.vw + 1 && panel.dockScroll <= panel.dockClient + 1, JSON.stringify(panel));
  await ph.page.screenshot({ path: resolve(here, 'cleanup-simplify-phone.png'), timeout: 120000 });
  await ph.page.evaluate(() => window.__xrayCleanup.simplify.openDialog());
  await ph.page.waitForSelector('#xray-save-dialog');
  const dlg = await ph.page.evaluate(() => {
    const b = document.querySelector('#xray-save-dialog .box').getBoundingClientRect();
    const btns = [...document.querySelectorAll('#xray-save-dialog button')].filter((e) => !e.hidden).map((e) => e.getBoundingClientRect());
    return { left: b.left, right: b.right, top: b.top, bottom: b.bottom, vw: window.innerWidth, vh: window.innerHeight, btnsOk: btns.every((r) => r.left >= 0 && r.right <= window.innerWidth && r.height >= 30) };
  });
  check('[phone] the dialog and its buttons fit the screen', dlg.left >= 0 && dlg.right <= dlg.vw && dlg.top >= 0 && dlg.bottom <= dlg.vh && dlg.btnsOk, JSON.stringify(dlg));
  await ph.page.screenshot({ path: resolve(here, 'cleanup-save-phone.png'), timeout: 120000 });
  const pe = ph.errors.filter((e) => !/favicon/i.test(e));
  check('no console errors (phone)', pe.length === 0, pe.slice(0, 3).join(' | '));
  await ph.ctx.close();
} catch (e) {
  console.error(e);
  failed = true;
} finally {
  if (browser) await browser.close();
  vite.kill('SIGTERM');
}
process.exit(failed ? 1 : 0);
