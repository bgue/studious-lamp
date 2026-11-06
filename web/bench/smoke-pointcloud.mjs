// Headless check for point clouds on /?model=building (1600x900):
//   - lil-gui folder "Point cloud" with the agreed entry names, tool and palette actions registered
//   - public/samples/building-scan.las through the folder's file input: point count, aligned (walls' median deviation < 2 cm)
//   - Compute deviation: the displaced duct is red, the walls green; focus-only scope greys out the rest
//   - screenshots bench/pointcloud-rgb.png and bench/pointcloud-deviation.png (X-ray on, duct selected)
//   - the PLY sample, budget change, auto-align, drop handler, LAZ message, a 300k point timing run
//   - zero console errors
// Usage: SMOKE_PORT=5381 node bench/smoke-pointcloud.mjs
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const port = Number(process.env.SMOKE_PORT ?? 5381);
const LAS = resolve(root, 'public/samples/building-scan.las');
const PLY = resolve(root, 'public/samples/building-scan.ply');

function loadPlaywright() {
  const candidates = [process.env.PLAYWRIGHT_MODULE, resolve(root, 'node_modules/playwright'), '/opt/node-tools/node_modules/playwright', '/opt/node22/lib/node_modules/playwright'].filter(Boolean);
  for (const c of candidates) {
    try { return createRequire(import.meta.url)(c); } catch { /* next */ }
  }
  throw new Error('playwright not found; set PLAYWRIGHT_MODULE');
}
const { chromium } = loadPlaywright();

const vite = spawn(resolve(root, 'node_modules/.bin/vite'), ['--config', 'bench/vite.smoke.config.mjs', '--host', '127.0.0.1', '--port', String(port), '--strictPort'], { cwd: root, stdio: ['ignore', 'pipe', 'pipe'] });
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

/** A 300k point LAS: the sample plus jittered copies of its first points (same header, longer body). */
function bigLas(n) {
  const src = readFileSync(LAS);
  const rec = 26, head = 227;
  const have = (src.length - head) / rec;
  const out = Buffer.alloc(head + n * rec);
  src.copy(out, 0, 0, head + have * rec);
  for (let i = have; i < n; i++) {
    const from = head + (i % have) * rec;
    src.copy(out, head + i * rec, from, from + rec);
    out.writeInt32LE(out.readInt32LE(head + i * rec) + ((i * 7) % 5) - 2, head + i * rec);
  }
  out.writeUInt32LE(n, 107);
  return out;
}

const errors = [];
let browser;
try {
  await waitForServer();
  browser = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const ctx = await browser.newContext({ viewport: { width: 1600, height: 900 } });
  const page = await ctx.newPage();
  page.setDefaultTimeout(120000);
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', (e) => errors.push(`[pageerror] ${e.message}`));

  await page.goto(`http://127.0.0.1:${port}/?model=building`);
  await page.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: 180000 });
  const err = await page.evaluate('window.__xrayError');
  if (err) throw new Error(`startup failed: ${err}`);

  // ---------------------------------------------------------------- registration
  const guiNames = await page.evaluate(() => [...document.querySelectorAll('.lil-gui .lil-name, .lil-gui .name, .lil-gui .lil-title, .lil-gui .title')].map((e) => e.textContent.trim()));
  for (const n of ['Point cloud', 'Open point cloud', 'visible', 'point size', 'colour by', 'point budget', 'coordinates', 'Auto-align to model', 'align within', 'Align by 3 points', 'Refine (ICP)', 'offset x', 'offset y', 'offset z', 'rotation (deg)', 'Compute deviation', 'tolerance (m)', 'deviation scope', 'Remove point cloud', 'Point cloud status']) {
    check(`lil-gui entry "${n}"`, guiNames.includes(n));
  }
  check('tool "pointcloud", palette actions without keys, params section, window API', await page.evaluate(async () => {
    const { getTool } = await import('/src/tools/registry.ts');
    const { getAction } = await import('/src/input/actions.ts');
    const { paramSectionNames } = await import('/src/ui/params.ts');
    return !!getTool('pointcloud') && ['pointcloud.open', 'pointcloud.toggle', 'pointcloud.deviation'].every((id) => { const a = getAction(id); return a && a.keys.length === 0; })
      && paramSectionNames().includes('pointcloud') && typeof window.__xrayPointCloud?.load === 'function' && typeof window.__xrayPointCloud.stats === 'object';
  }));

  // ---------------------------------------------------------------- view: duct selected, X-ray on, oblique camera
  const duct = await page.evaluate(() => {
    const app = window.__xray.app;
    const d = app.controller.model.elements.find((e) => e.ifcClass === 'IfcDuctSegment');
    app.selectIds([d.id]);
    window.__xrayPointCloud.settings.pointSize = 3;
    const cam = app.renderer.camera;
    cam.position.set(4.6, 1.6, 1.2);
    app.renderer.controls.target.set(2.1, 0.5, -1.95);
    app.renderer.controls.update();
    app.controller.settle();
    return { id: d.id, xray: app.settings.xray };
  });
  check('X-ray on and the duct selected', duct.xray === true);

  // ---------------------------------------------------------------- LAS through the folder's file input
  await page.setInputFiles('input[data-pointcloud=open]', LAS);
  await page.waitForFunction(() => window.__xrayPointCloud.stats.loaded, null, { timeout: 120000 });
  const lasHeaderCount = readFileSync(LAS).readUInt32LE(107);
  const s1 = await page.evaluate(() => JSON.parse(JSON.stringify(window.__xrayPointCloud.stats)));
  check('LAS point count matches the header', s1.originalCount === lasHeaderCount && s1.shownCount === Math.min(lasHeaderCount, 3_000_000), `${s1.originalCount} original, ${s1.shownCount} shown`);
  check('file over 5 MB was parsed in a worker', s1.mode === 'worker', s1.mode);
  console.log(`    parse ${s1.parseMs.toFixed(0)} ms, decimate ${s1.decimateMs.toFixed(1)} ms, format ${s1.format}`);
  check('status line names the file and counts', (await page.evaluate(() => window.__xrayPointCloud.status)).includes('building-scan.las'));
  const pcCount = await page.evaluate(() => window.__xray.app.renderer.scene.children.filter((o) => o.isPoints).length);
  check('one THREE.Points in the main scene', pcCount === 1);

  await page.evaluate(() => window.__xray.app.controller.settle());
  await page.waitForTimeout(800);
  await page.screenshot({ path: resolve(here, 'pointcloud-rgb.png') });
  console.log('screenshot bench/pointcloud-rgb.png');

  // ---------------------------------------------------------------- deviation, scope all elements
  const d1 = await page.evaluate(async () => { const s = await window.__xrayPointCloud.computeDeviation(); return JSON.parse(JSON.stringify(s)); });
  const walls = d1.byClass['6'], ductC = d1.byClass['19'];
  check('aligned: median deviation of the walls under 2 cm', walls.median < 0.02, `${(walls.median * 1000).toFixed(1)} mm`);
  check('walls are green', walls.shareWithin > 0.95, `${(walls.shareWithin * 100).toFixed(1)}% within tolerance`);
  check('the displaced duct is red', ductC.shareRed > 0.5 && ductC.shareWithin < 0.3, `${(ductC.shareRed * 100).toFixed(1)}% red, ${(ductC.shareWithin * 100).toFixed(1)}% within, ${ductC.n} points`);
  check('stats: share within tolerance, mean, 95th percentile', d1.shareWithin > 0.8 && d1.mean > 0 && d1.p95 > d1.median, `within ${(d1.shareWithin * 100).toFixed(1)}%, mean ${(d1.mean * 1000).toFixed(1)} mm, p95 ${(d1.p95 * 1000).toFixed(1)} mm`);
  const mode = await page.evaluate(() => window.__xrayPointCloud.settings.colourBy);
  check('findings (amber and red points) are drawn through the model', await page.evaluate(() => { const o = window.__xray.app.renderer.scene.children.find((c) => c.name === 'pointcloud-findings'); return !!o && o.visible && o.geometry.index.count > 1000; }));
  check('colour by switched to deviation', mode === 'deviation');
  check('legend on the shared overlay', await page.evaluate(() => { const g = document.querySelector('[data-layer=pointcloud-legend]'); return !!g && g.style.display !== 'none' && g.textContent.includes('within'); }));
  await page.waitForTimeout(600);
  await page.screenshot({ path: resolve(here, 'pointcloud-deviation.png') });
  console.log('screenshot bench/pointcloud-deviation.png');
  const devMs = await page.evaluate(() => window.__xrayPointCloud.stats.deviationMs);
  console.log(`    deviation (${d1.sampled} points) ${devMs.toFixed(0)} ms`);

  // ---------------------------------------------------------------- focus-only scope
  const d2 = await page.evaluate(async () => {
    const pc = window.__xrayPointCloud;
    pc.settings.scope = 'focus only';
    const s = await pc.computeDeviation();
    pc.settings.scope = 'all elements';
    return JSON.parse(JSON.stringify(s));
  });
  check('focus only: duct points still red, the rest unrelated (grey)', d2.byClass['19'].shareRed > 0.5 && d2.unrelatedShare > 0.5 && d2.byClass['6'].related < d2.byClass['6'].n * 0.3, `unrelated ${(d2.unrelatedShare * 100).toFixed(1)}%`);

  // ---------------------------------------------------------------- panel and colour modes
  const modes = await page.evaluate(() => {
    const pc = window.__xrayPointCloud.controller;
    const out = {};
    for (const m of ['rgb', 'intensity', 'height', 'classification', 'deviation']) { pc.setColourBy(m); out[m] = window.__xrayPointCloud.settings.colourBy === m; }
    return out;
  });
  check('all colour modes selectable', Object.values(modes).every(Boolean));

  // ---------------------------------------------------------------- budget
  const b = await page.evaluate(async () => {
    const pc = window.__xrayPointCloud;
    await pc.controller.setBudget(50_000);
    return { ...JSON.parse(JSON.stringify(pc.stats)), dev: pc.stats.deviation };
  });
  check('budget decimates again: shown 50000 of the original', b.shownCount === 50_000 && b.originalCount === lasHeaderCount, `${b.shownCount}/${b.originalCount}`);
  check('a new budget invalidates the deviation result', b.dev === null);
  await page.evaluate(async () => { await window.__xrayPointCloud.controller.setBudget(3_000_000); });

  // ---------------------------------------------------------------- section planes
  const clip = await page.evaluate(async () => {
    const app = window.__xray.app;
    const pc = window.__xrayPointCloud.controller;
    app.renderer.setClipPlanes([{ normal: [0, 1, 0], point: [0, 0.5, 0] }]); // keeps y >= 0.5
    await new Promise((r) => setTimeout(r, 2500));
    const withPlane = pc.material.clippingPlanes?.length ?? 0;
    const c = pc.material.clippingPlanes?.[0];
    app.renderer.setClipPlanes(null);
    await new Promise((r) => setTimeout(r, 2500));
    return { withPlane, keepsAbove: !!c && c.distanceToPoint({ x: 0, y: 1, z: 0 }) > 0 && c.distanceToPoint({ x: 0, y: 0, z: 0 }) < 0, after: pc.material.clippingPlanes?.length ?? 0 };
  });
  check('section plane reaches the points material (kept side positive) and is released', clip.withPlane === 1 && clip.keepsAbove && clip.after === 0, JSON.stringify(clip));

  // ---------------------------------------------------------------- auto align
  const aa = await page.evaluate(async () => {
    const pc = window.__xrayPointCloud;
    const s = pc.settings;
    s.offsetX = 2.5; s.offsetY = 0.6; s.offsetZ = -1.8; s.rotationDeg = 33;
    pc.controller.setAlignment();
    const r = pc.autoAlign(true);
    const resid = Math.hypot(s.offsetX, s.offsetY, s.offsetZ);
    const out = { rot: r.rotationDeg, resid, desc: r.description };
    const dv = await pc.computeDeviation();
    out.wallMedian = dv.byClass['6'].median;
    s.offsetX = 0; s.offsetY = 0; s.offsetZ = 0; s.rotationDeg = 0;
    pc.controller.setAlignment();
    return out;
  });
  check('auto-align recovers the placement coarsely', [0, 180].includes(aa.rot) && aa.resid < 0.2, `rotation ${aa.rot}, residual offset ${aa.resid.toFixed(3)} m, walls median ${(aa.wallMedian * 100).toFixed(1)} cm`);
  console.log(`    ${aa.desc}`);

  // ---------------------------------------------------------------- PLY
  await page.setInputFiles('input[data-pointcloud=open]', PLY);
  await page.waitForFunction(() => window.__xrayPointCloud.stats.format === 'ply' && window.__xrayPointCloud.stats.loaded, null, { timeout: 60000 });
  const plyHeader = readFileSync(PLY, 'latin1').match(/element vertex (\d+)/)[1];
  const p1 = await page.evaluate(async () => {
    const pc = window.__xrayPointCloud;
    const st = JSON.parse(JSON.stringify(pc.stats));
    const dv = await pc.computeDeviation();
    return { st, wall: dv.byClass['6'].median, red: dv.byClass['19'].shareRed };
  });
  check('PLY loads with the header count', p1.st.originalCount === Number(plyHeader), `${p1.st.originalCount}`);
  check('PLY aligns too (walls median < 2 cm) and flags the duct', p1.wall < 0.02 && p1.red > 0.5, `${(p1.wall * 1000).toFixed(1)} mm, ${(p1.red * 100).toFixed(1)}% red`);

  // ---------------------------------------------------------------- drop handler (capture phase, before the model loader)
  const dropped = await page.evaluate(async () => {
    window.__xrayPointCloud.remove();
    const bytes = new Uint8Array(await (await fetch('/samples/building-scan.ply')).arrayBuffer());
    const dt = new DataTransfer();
    dt.items.add(new File([bytes], 'dropped.ply'));
    const ev = new DragEvent('drop', { dataTransfer: dt, bubbles: true, cancelable: true });
    document.body.dispatchEvent(ev);
    await new Promise((r) => setTimeout(r, 1500));
    const ov = document.getElementById('xray-drop-overlay');
    return { name: window.__xrayPointCloud.stats.name, loaded: window.__xrayPointCloud.stats.loaded, prevented: ev.defaultPrevented, overlayHidden: !ov || ov.style.display === 'none', model: window.__xray.app.modelName };
  });
  check('drop of a .ply opens it and leaves the model alone', dropped.loaded && dropped.name === 'dropped.ply' && dropped.model === 'building' && dropped.prevented, JSON.stringify(dropped));
  check('drop overlay is hidden afterwards', dropped.overlayHidden);

  // ---------------------------------------------------------------- LAZ message
  await page.setInputFiles('input[data-pointcloud=open]', { name: 'scan.laz', mimeType: 'application/octet-stream', buffer: Buffer.from('LASF-not-really') });
  await page.waitForFunction(() => /PDAL/.test(window.__xrayPointCloud.status), null, { timeout: 10000 });
  check('LAZ gives a conversion hint', true, (await page.evaluate(() => window.__xrayPointCloud.status)).slice(0, 90));
  await page.evaluate(() => window.__xrayPointCloud.remove());

  // ---------------------------------------------------------------- 300k points timing (worker path)
  const big = bigLas(300_000);
  const t0 = Date.now();
  await page.setInputFiles('input[data-pointcloud=open]', { name: 'big.las', mimeType: 'application/octet-stream', buffer: big });
  await page.waitForFunction(() => window.__xrayPointCloud.stats.name === 'big.las' && window.__xrayPointCloud.stats.loaded, null, { timeout: 120000 });
  const loadWall = Date.now() - t0;
  const t = await page.evaluate(async () => {
    const pc = window.__xrayPointCloud;
    const st = JSON.parse(JSON.stringify(pc.stats));
    const dv = await pc.computeDeviation();
    return { st, devMs: pc.stats.deviationMs, sampled: dv.sampled };
  });
  t.loadWall = loadWall;
  check('300k points load and measure', t.st.originalCount === 300_000 && t.sampled === 300_000, `mode ${t.st.mode}`);
  const pure = await page.evaluate(() => {
    const pc = window.__xrayPointCloud.controller;
    const f = pc.distanceFn('all elements');
    const n = 300_000;
    const t0 = performance.now();
    let hit = 0;
    for (let i = 0; i < n; i++) { const p = pc.pointPosition(i); if (f(p[0], p[1], p[2], 0.1) < Infinity) hit++; }
    return { ms: performance.now() - t0, hit };
  });
  console.log(`    pure distance queries for 300k points, no frames in between: ${pure.ms.toFixed(0)} ms (${(pure.ms * 1000 / 300000).toFixed(1)} us per point)`);
  console.log(`    300k points: parse ${t.st.parseMs.toFixed(0)} ms (in the worker), decimate ${t.st.decimateMs.toFixed(1)} ms, file input to loaded ${t.loadWall} ms, deviation ${t.devMs.toFixed(0)} ms (swiftshader build, includes the model BVH being warm)`);

  check('no console errors', errors.length === 0, errors.slice(0, 3).join(' | '));
} catch (e) {
  failed = true;
  console.log('ERROR', e instanceof Error ? e.stack ?? e.message : e);
} finally {
  await browser?.close();
  vite.kill();
}
process.exit(failed ? 1 : 0);
