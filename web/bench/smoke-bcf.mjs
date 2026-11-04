// Headless check for BCF: on /?model=fzk-haus select two windows, create a topic with a snapshot through the drawer's
// New topic dialog, export 2.1 with the drawer button, reload the page, import the downloaded file through the file input,
// apply its viewpoint from the drawer and assert the camera matches within 1 cm and the selection is restored; check hide
// provenance on Clear viewpoint; then createTopics for three wall GlobalIds through the API, export 3.0, reload, import
// and count three topics. Both exports are also validated against the official XSDs (python3 + lxml, when available).
// Screenshot bench/bcf-drawer.png with the drawer open and a topic selected. Fails on any console error.
// Usage: SMOKE_PORT=5333 node bench/smoke-bcf.mjs
import { spawn, spawnSync } from 'node:child_process';
import { createRequire } from 'node:module';
import { mkdtempSync, mkdirSync, writeFileSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const port = Number(process.env.SMOKE_PORT ?? 5333);
const tmp = mkdtempSync(join(tmpdir(), 'smoke-bcf-'));

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

function validateXsd(file, label) {
  const dir = join(tmp, `unz-${label}`);
  mkdirSync(dir, { recursive: true });
  const z = spawnSync('python3', ['-I', '-m', 'zipfile', '-e', file, dir], { encoding: 'utf8' });
  if (z.status !== 0) { console.log(`SKIP xsd validation (${label}): python3 zipfile failed`); return; }
  if (spawnSync('python3', ['-I', '-c', 'import lxml.etree']).status !== 0) { console.log(`SKIP xsd validation (${label}): lxml missing`); return; }
  const r = spawnSync('python3', ['-I', resolve(root, 'tests/fixtures/bcf/validate_xsd.py'), dir], { encoding: 'utf8' });
  console.log(r.stdout.trim().split('\n').map((l) => `    ${l}`).join('\n'));
  check(`${label} validates against the official XSDs`, r.status === 0);
}

const errors = [];
let browser;
try {
  await waitForServer();
  browser = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const ctx = await browser.newContext({ viewport: { width: 1600, height: 900 }, acceptDownloads: true });
  const page = await ctx.newPage();
  page.setDefaultTimeout(120000); // swiftshader readbacks are slow on a loaded machine
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', (e) => errors.push(`[pageerror] ${e.message}`));

  async function boot() {
    await page.goto(`http://127.0.0.1:${port}/?model=fzk-haus`);
    await page.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: 180000 });
    const err = await page.evaluate('window.__xrayError');
    if (err) throw new Error(`startup failed: ${err}`);
    // Mount the registered `bcf` tool panel in a drawer-like container (works with or without the toolbar plugin).
    await page.evaluate(async () => {
      const { getTool } = await import('/src/tools/registry.ts');
      document.getElementById('bcf-test-drawer')?.remove();
      const d = document.createElement('div');
      d.id = 'bcf-test-drawer';
      d.style.cssText = 'position:fixed;left:312px;top:8px;bottom:8px;width:400px;z-index:20;background:#141820;border:1px solid #262d3a;border-radius:6px;overflow:auto;box-shadow:0 4px 24px rgba(0,0,0,.4)';
      document.body.appendChild(d);
      getTool('bcf').panel(d, window.__xray.app);
    });
  }

  // ------------------------------------------------------------------ part 1: topic from view, export 2.1, reload, import, apply
  await boot();
  check('bcf tool registered and API present', await page.evaluate(async () => { const { getTool } = await import('/src/tools/registry.ts'); return !!getTool('bcf') && typeof window.__xrayBcf?.createTopics === 'function'; }));
  const guiNames = await page.evaluate(() => [...document.querySelectorAll('.lil-gui .lil-name, .lil-gui .name, .lil-gui .lil-title, .lil-gui .title')].map((e) => e.textContent.trim()));
  for (const n of ['BCF', 'Open BCF', 'Create topic from view', 'Export BCF 2.1', 'Export BCF 3.0', 'Clear viewpoint', 'BCF status']) check(`lil-gui entry "${n}"`, guiNames.includes(n));
  const actionsOk = await page.evaluate(async () => {
    const { getAction } = await import('/src/input/actions.ts');
    return ['bcf.open', 'bcf.create', 'bcf.export', 'bcf.clear'].every((id) => { const a = getAction(id); return a && a.keys.length === 0; });
  });
  check('palette actions bcf.open/create/export/clear without keys', actionsOk);

  const setup = await page.evaluate(() => {
    const app = window.__xray.app;
    const els = app.controller.model.elements;
    const windows = els.filter((e) => e.ifcClass === 'IfcWindow').slice(0, 2);
    const walls = els.filter((e) => e.ifcClass.startsWith('IfcWall'));
    const hideId = walls[0].id;
    app.settings.overrides.userHides.add(hideId); // a user hide that must be part of the viewpoint
    app.controller.refreshOverrides();
    app.selectIds(windows.map((w) => w.id));
    const cam = app.renderer.camera;
    cam.position.set(9.5, 5.5, 11.5);
    app.renderer.controls.target.set(0.5, 1.2, -0.5);
    app.renderer.controls.update();
    app.controller.settle();
    const p = cam.position;
    return { winIds: windows.map((w) => w.id), hideId, pos: [p.x, p.y, p.z], target: app.renderer.controls.target.toArray(), shift: app.loaded.model.originShift };
  });
  check('two windows selected', setup.winIds.length === 2, `ids ${setup.winIds}`);

  await page.click('#bcf-drawer [data-act=new]');
  await page.fill('#bcf-f-title', 'Window reveal too small');
  await page.fill('#bcf-f-description', 'Check both windows & the reveal.');
  await page.fill('#bcf-f-type', 'Issue');
  await page.fill('#bcf-f-status', 'Open');
  await page.fill('#bcf-f-priority', 'High');
  await page.fill('#bcf-f-labels', 'Architecture, Windows');
  await page.fill('#bcf-f-assigned', 'bob@example.org');
  await page.fill('#bcf-f-author', 'smoke@example.org');
  await page.click('#bcf-f-create');
  const created = await page.evaluate(() => {
    const t = window.__xrayBcf.topics;
    const v = t[0]?.viewpoints[0];
    return { n: t.length, snap: v?.snapshot?.length ?? 0, mime: v?.snapshotMime, sel: v?.data?.selection.length, vis: v?.data?.visibility, author: t[0]?.creationAuthor, stored: localStorage.getItem('xray.bcf.author') };
  });
  check('topic created from view with snapshot', created.n === 1 && created.snap > 2000 && created.mime === 'image/png', `snapshot ${created.snap} bytes`);
  check('viewpoint selects the two windows and keeps the user hide as exception', created.sel === 2 && created.vis?.defaultVisibility === true && created.vis.exceptions.length === 1);
  check('author remembered', created.author === 'smoke@example.org' && created.stored === 'smoke@example.org');

  // screenshot with the drawer open and the topic selected (thumbnail needs a moment to decode)
  await page.waitForFunction(() => { const i = document.querySelector('#bcf-drawer .bcf-snap'); return i && i.complete && i.naturalWidth > 0; }, null, { timeout: 10000 });
  await page.evaluate(() => window.__xray.app.controller.settle());
  await page.waitForTimeout(500);
  await page.screenshot({ path: resolve(here, 'bcf-drawer.png') });
  console.log('screenshot bench/bcf-drawer.png');

  const [dl21] = await Promise.all([page.waitForEvent('download'), page.click('#bcf-drawer [data-act="export-2.1"]')]);
  const file21 = join(tmp, 'export-2.1.bcfzip');
  await dl21.saveAs(file21);
  check('Export 2.1 downloaded a .bcfzip', /\.bcfzip$/.test(dl21.suggestedFilename()), dl21.suggestedFilename());
  validateXsd(file21, 'BCF 2.1 export');

  await boot(); // fresh page: nothing selected, nothing hidden
  const fresh = await page.evaluate(() => ({ sel: window.__xray.app.selection.length, hides: window.__xray.app.settings.overrides.userHides.size, n: window.__xrayBcf.topics.length }));
  check('reloaded page starts clean', fresh.sel === 0 && fresh.hides === 0 && fresh.n === 0);
  await page.setInputFiles('input[data-bcf=open]', file21);
  await page.waitForFunction(() => window.__xrayBcf.topics.length === 1, null, { timeout: 15000 });
  const listed = await page.evaluate(() => ({ items: document.querySelectorAll('#bcf-drawer [data-topic]').length, title: document.querySelector('#bcf-drawer [data-topic] .bcf-title')?.textContent, chips: [...document.querySelectorAll('#bcf-drawer [data-topic] .bcf-chip')].map((c) => c.textContent) }));
  check('imported topic is listed with chips', listed.items === 1 && listed.title === 'Window reveal too small' && listed.chips.includes('Open') && listed.chips.includes('High'), JSON.stringify(listed.chips));

  // user hides another element first: it must survive Clear viewpoint
  const userHid = await page.evaluate((hideId) => {
    const app = window.__xray.app;
    const other = app.controller.model.elements.find((e) => e.ifcClass.startsWith('IfcWall') && e.id !== hideId).id;
    app.settings.overrides.userHides.add(other);
    app.controller.refreshOverrides();
    return other;
  }, setup.hideId);
  await page.click('#bcf-drawer [data-act=apply]');
  await page.waitForTimeout(2500); // a selection fly-to (cinematic plugin) must not move the applied camera
  const applied = await page.evaluate(() => {
    const app = window.__xray.app;
    const p = app.renderer.camera.position;
    return { pos: [p.x, p.y, p.z], sel: app.selection.slice().sort((a, b) => a - b), hides: [...app.settings.overrides.userHides], status: window.__xrayBcf.status };
  });
  const dpos = Math.hypot(applied.pos[0] - setup.pos[0], applied.pos[1] - setup.pos[1], applied.pos[2] - setup.pos[2]);
  check('camera position matches within 1 cm', dpos < 0.01, `${(dpos * 1000).toFixed(3)} mm`);
  check('selection restored', JSON.stringify(applied.sel) === JSON.stringify([...setup.winIds].sort((a, b) => a - b)), `${applied.sel}`);
  check('viewpoint hides the exception element (DefaultVisibility true)', applied.hides.includes(setup.hideId) && applied.hides.includes(userHid) && applied.hides.length === 2, `hides ${applied.hides}`);
  console.log(`    status: ${applied.status}`);
  await page.click('#bcf-drawer [data-bcf-detail] [data-act=clear]');
  const cleared = await page.evaluate(() => [...window.__xray.app.settings.overrides.userHides]);
  check('Clear viewpoint restores only what BCF hid', JSON.stringify(cleared) === JSON.stringify([userHid]), `hides ${cleared}`);

  // ------------------------------------------------------------------ part 2: createTopics via API, export 3.0, reimport
  const walls = await page.evaluate(() => window.__xray.app.controller.model.elements.filter((e) => e.ifcClass.startsWith('IfcWall')).slice(0, 3).map((e) => ({ id: e.id, gid: e.globalId })));
  const camBefore = await page.evaluate(() => window.__xray.app.renderer.camera.position.toArray());
  const made = await page.evaluate(async (w) => {
    const topics = window.__xrayBcf.createTopics(w.map((x, i) => ({ title: `Wall ${i + 1}`, description: `Penetration check ${i + 1}`, globalIds: [x.gid], labels: ['Penetration'] })));
    return topics.map((t) => ({ title: t.title, snap: t.viewpoints[0]?.snapshot?.length ?? 0, sel: t.viewpoints[0]?.data?.selection.map((s) => s.ifcGuid) }));
  }, walls);
  check('createTopics built 3 topics with snapshots', made.length === 3 && made.every((m) => m.snap > 1000), made.map((m) => m.snap).join(','));
  check('each topic selects its wall', made.every((m, i) => m.sel.length === 1 && m.sel[0] === walls[i].gid));
  await page.waitForTimeout(2500);
  const camAfter = await page.evaluate(() => window.__xray.app.renderer.camera.position.toArray());
  check('createTopics restored the camera', Math.hypot(...camAfter.map((v, i) => v - camBefore[i])) < 1e-6);
  const noSnap = await page.evaluate((gid) => { const t = window.__xrayBcf.createTopics([{ title: 'no snapshot', globalIds: [gid] }], { snapshot: false })[0]; return t.viewpoints[0].snapshot === undefined; }, walls[0].gid);
  check('snapshot flag off skips the PNG', noSnap);
  await page.evaluate(() => { window.__xrayBcf.topics.pop(); }); // drop the extra topic: three remain besides the imported one
  await page.evaluate(() => { window.__xrayBcf.topics.splice(0, 1); }); // and the imported one
  const arr = await page.evaluate(async () => Array.from(await window.__xrayBcf.exportZip('3.0')));
  const file30 = join(tmp, 'export-3.0.bcfzip');
  writeFileSync(file30, Buffer.from(arr));
  check('exportZip(3.0) returned bytes', arr.length > 3000, `${arr.length} bytes`);
  validateXsd(file30, 'BCF 3.0 export');

  await boot();
  await page.setInputFiles('input[data-bcf=open]', file30);
  await page.waitForFunction(() => window.__xrayBcf.topics.length >= 1, null, { timeout: 15000 });
  const re = await page.evaluate(async (walls) => {
    const b = window.__xrayBcf;
    const out = { count: b.topics.length, titles: b.topics.map((t) => t.title).sort(), picks: [] };
    for (const t of b.topics) {
      const r = b.applyViewpoint(t.guid);
      out.picks.push({ title: t.title, ok: r.ok, sel: window.__xray.app.selection });
    }
    out.walls = walls;
    return out;
  }, walls);
  check('reimported 3.0 file has three topics', re.count === 3, re.titles.join(' | '));
  check('each reimported viewpoint selects its wall', re.picks.every((p) => p.ok && p.sel.length === 1 && p.sel[0] === walls[Number(p.title.slice(5)) - 1].id));

  check('no console errors', errors.length === 0, errors.slice(0, 3).join(' | '));
} catch (e) {
  failed = true;
  console.log('ERROR', e instanceof Error ? e.stack ?? e.message : e);
} finally {
  await browser?.close();
  vite.kill();
}
process.exit(failed ? 1 : 0);
