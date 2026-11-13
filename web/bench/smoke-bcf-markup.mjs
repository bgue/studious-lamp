// Headless check for BCF markup (topic pins and annotations) on /?model=fzk-haus:
//   - select a window, create an issue through the New issue dialog of the Issues tab with "click the model to place the pin" ticked, click a
//     wall on the canvas: the pin lands there (Escape cancels a second placement without closing anything);
//   - measure two points with the measure tool API, then with the drawing toolbar on the issue's sketch (the BCF drawer and its annotation buttons are gone: a viewpoint's drawing is its sketch): a callout on an element (canvas click), a linked
//     measurement, a note; drag a callout text box with the mouse;
//   - export 2.1 and 3.0 with the Issues panel buttons, validate both against the official XSDs, extract the burned snapshot;
//   - reload, import the 3.0 file, compare pins and annotations with the state before export (exact), apply the viewpoint
//     and check the overlay draws them; click the pin to activate the topic. Fails on any console error.
// Screenshots: bench/bcf-markup-live.png (before export), bench/bcf-markup-snapshot.png (the exported snapshot),
// bench/bcf-markup-reimport.png (after reload and import).
// Usage: SMOKE_PORT=5623 node bench/smoke-bcf-markup.mjs   (BCF_CLIENT_PYTHON=<python with bcf-client> also reads the exports)
import { spawn, spawnSync } from 'node:child_process';
import { createRequire } from 'node:module';
import { mkdtempSync, mkdirSync, copyFileSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const port = Number(process.env.SMOKE_PORT ?? 5623);
const tmp = mkdtempSync(join(tmpdir(), 'smoke-bcf-markup-'));

function loadPlaywright() {
  const candidates = [process.env.PLAYWRIGHT_MODULE, resolve(root, 'node_modules/playwright'), '/opt/node-tools/node_modules/playwright', '/opt/node22/lib/node_modules/playwright', 'playwright'].filter(Boolean);
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
  for (let i = 0; i < 150; i++) {
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

function unzip(file, label) {
  const dir = join(tmp, `unz-${label}`);
  mkdirSync(dir, { recursive: true });
  const z = spawnSync('python3', ['-I', '-m', 'zipfile', '-e', file, dir], { encoding: 'utf8' });
  return z.status === 0 ? dir : null;
}
function validateXsd(dir, label) {
  if (spawnSync('python3', ['-I', '-c', 'import lxml.etree']).status !== 0) { console.log(`SKIP xsd validation (${label}): lxml missing`); return; }
  const r = spawnSync('python3', ['-I', resolve(root, 'tests/fixtures/bcf/validate_xsd.py'), dir], { encoding: 'utf8' });
  console.log(r.stdout.trim().split('\n').map((l) => `    ${l}`).join('\n'));
  check(`${label} validates against the official XSDs`, r.status === 0);
}
function bcfClient(file, version) {
  const py = process.env.BCF_CLIENT_PYTHON;
  if (!py) return;
  const mod = version === '3.0' ? 'bcf.v3.bcfxml' : 'bcf.v2.bcfxml';
  const code = `import sys, importlib\nm = importlib.import_module('${mod}')\nb = m.BcfXml.load(sys.argv[1])\nfor g, t in b.topics.items():\n  print(g, t.topic.title, len(t.viewpoints), sorted(t.viewpoints.keys())[:1])\n`;
  const r = spawnSync(py, ['-c', code, file], { encoding: 'utf8' });
  console.log(`${r.stdout}${r.stderr}`.trim().split('\n').map((l) => `    bcf-client: ${l}`).join('\n'));
  check(`IfcOpenShell bcf-client reads the ${version} export with the side file`, r.status === 0);
}

const errors = [];
let browser;
try {
  await waitForServer();
  browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1600, height: 900 }, acceptDownloads: true });
  const page = await ctx.newPage();
  page.setDefaultTimeout(180000);
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', (e) => errors.push(`[pageerror] ${e.message}`));

  async function boot() {
    await page.goto(`http://127.0.0.1:${port}/?model=fzk-haus`);
    await page.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: 240000 });
    const err = await page.evaluate('window.__xrayError');
    if (err) throw new Error(`startup failed: ${err}`);
    await page.evaluate(() => window.__xrayIssues.open('issues'));
  }
  /** Client position of a viewer-frame point under the current camera. */
  async function screenOf(p) {
    return page.evaluate((p) => {
      const app = window.__xray.app;
      const cam = app.renderer.camera;
      cam.updateMatrixWorld();
      const v = cam.position.clone().set(p[0], p[1], p[2]).project(cam);
      const r = app.canvas.getBoundingClientRect();
      return { x: r.left + (v.x * 0.5 + 0.5) * r.width, y: r.top + (1 - (v.y * 0.5 + 0.5)) * r.height };
    }, p);
  }
  const settle = () => page.evaluate(() => window.__xray.app.controller.settle());

  // ------------------------------------------------------------------ part 1: topic with pin
  await boot();
  const setup = await page.evaluate(() => {
    const app = window.__xray.app;
    const els = app.controller.model.elements;
    const win = els.find((e) => e.ifcClass === 'IfcWindow');
    app.selectIds([win.id]);
    const cam = app.renderer.camera;
    cam.position.set(9.5, 5.5, 11.5);
    app.renderer.controls.target.set(0.5, 1.2, -0.5);
    app.renderer.controls.update();
    app.controller.settle();
    const b = win.bounds;
    return { win: { id: win.id, gid: win.globalId, centre: [(b[0] + b[3]) / 2, (b[1] + b[4]) / 2, (b[2] + b[5]) / 2] } };
  });
  await page.waitForTimeout(2500); // the selection fly-to (cinematic) settles
  await page.evaluate(() => {
    const app = window.__xray.app;
    window.__cinematic?.cancelFlight?.();
    app.renderer.camera.position.set(9.5, 5.5, 11.5);
    app.renderer.controls.target.set(0.5, 1.2, -0.5);
    app.renderer.controls.update();
    app.controller.settle();
  });
  await page.click('#issues-panel [data-act=new]');
  await page.fill('#bcf-f-title', 'Window reveal too small');
  await page.fill('#bcf-f-author', 'smoke@example.org');
  await page.check('#bcf-f-pinpick');
  await page.click('#bcf-f-create');
  const placing = await page.evaluate(() => window.__xrayBcf.status);
  check('creating with "click the model" starts pin placement', /Click the model to place the pin/.test(placing), placing);
  // a wall surface point: pick at a screen point a bit off the model centre and click there
  const target = await screenOf([0.5, 1.2, -0.5]);
  await page.mouse.click(target.x, target.y);
  const pinned = await page.evaluate(() => {
    const t = window.__xrayBcf.topics[0];
    const app = window.__xray.app;
    const e = app.controller.model.byGlobalId.get(t.pin?.elementGuid);
    return { pin: t.pin, cls: e !== undefined ? app.controller.model.elements[e].ifcClass : null, sel: app.selection, status: window.__xrayBcf.status };
  });
  check('pin placed on a picked surface with its element', !!pinned.pin && !!pinned.cls, `${pinned.cls} ${JSON.stringify(pinned.pin?.position)}`);
  check('the placing click did not change the selection', pinned.sel.length === 1 && pinned.sel[0] === setup.win.id, `${pinned.sel}`);
  const pinDrawn = await page.evaluate(() => document.querySelectorAll('svg.xray-svg-overlay [data-bcf-pin]').length);
  check('the pin is drawn on the overlay', pinDrawn === 1, `${pinDrawn}`);

  // Escape cancels a placement without closing the panel
  await page.click('#issues-panel [data-act=place-pin]');
  await page.keyboard.press('Escape');
  const esc = await page.evaluate(() => ({ status: window.__xrayBcf.status, drawer: !!document.getElementById('issues-panel') }));
  check('Escape cancels the placement', /cancelled/.test(esc.status) && esc.drawer, esc.status);

  // ------------------------------------------------------------------ part 2: measurement, callout, linked measurement, note
  const meas = await page.evaluate((c) => {
    const m = window.__xrayMeasure;
    m.click([c[0] - 0.4, c[1], c[2]], 0);
    m.click([c[0] + 0.4, c[1], c[2]], 0);
    return m.list.map((x) => ({ id: x.id, d: x.distance }));
  }, setup.win.centre);
  check('a measurement exists', meas.length === 1, JSON.stringify(meas));

  // The drawing of the viewpoint is its sketch: Edit drawing makes it (linked to the issue) and shows the toolbar.
  await page.click('#issues-panel [data-viewpoint] [data-act=edit-drawing]');
  await page.waitForSelector('#markup-float', { state: 'visible' });
  await page.click('#markup-float [data-tool-id=callout]');
  await page.fill('#markup-float [aria-label="Text for the next markup"]', 'Reveal 3 cm too small');
  await settle();
  const win = await screenOf(setup.win.centre);
  await page.mouse.click(win.x, win.y);
  // The measurement joins the sketch through the scripting call (the Link a measurement list is covered in smoke-markup).
  await page.evaluate((id) => window.__xrayMarkup.add({ kind: 'measure', measurementId: id }), meas[0].id);
  await page.click('#markup-float [data-tool-id=text]');
  await page.fill('#markup-float [aria-label="Text for the next markup"]', 'Check sill on site');
  const notePt = await screenOf([setup.win.centre[0] - 1.2, setup.win.centre[1] - 0.6, setup.win.centre[2]]);
  await page.mouse.click(notePt.x, notePt.y);
  await settle();
  await page.click('#markup-float [data-tool-id=select]');
  await page.waitForTimeout(400);
  const anns = await page.evaluate(() => {
    const b = window.__xrayBcf;
    const t = b.topics[0];
    const byVp = b.annotations(t.guid);
    const list = Object.values(byVp).flat();
    const app = window.__xray.app;
    const cls = (g) => { const id = app.controller.model.byGlobalId.get(g); return id !== undefined ? app.controller.model.elements[id].ifcClass : null; };
    return {
      list: list.map((a) => ({ type: a.type, kind: a.anchor.kind, text: a.text, el: a.anchor.elementGuid ? cls(a.anchor.elementGuid) : null, m: a.anchor.measurement?.label })),
      sel: t.viewpoints[0].data.selection.map((s) => s.ifcGuid),
      drawn: document.querySelectorAll('svg.xray-svg-overlay [data-mk]').length,
      bcfDrawn: document.querySelectorAll('svg.xray-svg-overlay [data-bcf-ann]').length,
      linked: !!t.viewpoints[0].sketchId,
    };
  });
  console.log('    annotations:', JSON.stringify(anns.list));
  // Assertion changed: the annotations are now the projection of the sketch, whose labels carry the markup number ("1. text").
  check('callout anchored on an element', anns.list.some((a) => a.type === 'callout' && a.kind === 'element' && a.el && a.text === '1. Reveal 3 cm too small'));
  check('measurement linked with its label', anns.list.some((a) => a.kind === 'measurement' && /m$/.test(a.m ?? '')));
  check('note on a free point', anns.list.some((a) => a.type === 'note' && a.kind === 'point' && a.text === '3. Check sill on site'));
  // Assertion changed: the markup view draws the sketch (data-mk); the BCF overlay draws none of a linked viewpoint (no double drawing).
  check('the sketch draws the 3 annotations, the BCF overlay none, and the viewpoint links to the sketch', anns.drawn === 3 && anns.bcfDrawn === 0 && anns.linked, `drawn ${anns.drawn}, bcf ${anns.bcfDrawn}, linked ${anns.linked}`);
  check('annotated element joins the viewpoint selection', anns.sel.length >= 2, `${anns.sel.length} selected`);

  // drag a callout text box (the topmost box at the centre of the element callout's box)
  await page.click('#issues-panel [data-viewpoint] [data-act=edit-drawing]'); // the select tool of the toolbar moves boxes
  const callout = await page.evaluate(() => Object.values(window.__xrayBcf.annotations(window.__xrayBcf.topics[0].guid)).flat().find((a) => a.type === 'callout' && a.anchor.kind === 'element').guid);
  const grab = await page.evaluate((g) => {
    const r = document.querySelector(`svg.xray-svg-overlay [data-mk="${g}"] rect[data-role=box]`).getBoundingClientRect();
    const x = r.left + r.width / 2, y = r.top + r.height / 2;
    return { x, y, key: document.elementFromPoint(x, y)?.closest('[data-mk]')?.getAttribute('data-mk') };
  }, callout);
  const offOf = (g) => page.evaluate((g) => Object.values(window.__xrayBcf.annotations(window.__xrayBcf.topics[0].guid)).flat().find((a) => a.guid === g)?.offset, g);
  const before = await offOf(grab.key);
  await page.mouse.move(grab.x, grab.y);
  await page.mouse.down();
  await page.mouse.move(grab.x + 40, grab.y - 30, { steps: 4 });
  await page.mouse.up();
  const after = await offOf(grab.key);
  const moved = before && after ? [after[0] - before[0], after[1] - before[1]] : [0, 0];
  check('dragging a text box moves it', grab.key === callout && moved[0] > 0.02 && moved[1] < -0.02, `${grab.key === callout ? 'callout box on top' : 'another box on top'}; ${moved.map((v) => v.toFixed(3)).join(',')}`);

  await page.click('#markup-float [data-act=done]');
  await page.waitForTimeout(400);
  await page.screenshot({ path: resolve(here, 'bcf-markup-live.png') });
  console.log('screenshot bench/bcf-markup-live.png');

  // ------------------------------------------------------------------ part 3: export, snapshot, validation
  const state = await page.evaluate(() => window.__xrayBcf.topics.map((t) => ({ guid: t.guid.toLowerCase(), pin: t.pin, annotations: window.__xrayBcf.annotations(t.guid) })));
  const files = {};
  await page.evaluate(() => window.__xrayIssues.openIssue(window.__xrayBcf.topics[0].guid, { apply: false }));
  for (const v of ['2.1', '3.0']) {
    const [dl] = await Promise.all([page.waitForEvent('download'), page.click(`#issues-panel [data-act="export-${v}"]`)]);
    files[v] = join(tmp, `markup-${v}.bcfzip`);
    await dl.saveAs(files[v]);
    const dir = unzip(files[v], v);
    if (!dir) { check(`unzip ${v}`, false); continue; }
    validateXsd(dir, `BCF ${v} export with markup`);
    const t = state[0];
    const folder = v === '3.0' ? t.guid : (await page.evaluate(() => window.__xrayBcf.topics[0].guid));
    const side = JSON.parse(readFileSync(join(dir, folder, 'xray-markup.json'), 'utf8'));
    check(`${v}: side file holds the pin and 3 annotations`, !!side.pin && Object.values(side.viewpoints).flatMap((x) => x.annotations ?? []).length === 3);
    const vpg = Object.keys(side.viewpoints)[0];
    const snap = v === '2.1' ? 'snapshot.png' : `${vpg}.png`;
    const base = side.viewpoints[vpg].baseSnapshot;
    const a = readFileSync(join(dir, folder, snap));
    const b = readFileSync(join(dir, folder, base));
    check(`${v}: burned snapshot differs from the clean one`, !a.equals(b) && a.length > 2000, `${a.length} vs ${b.length} bytes`);
    if (v === '3.0') {
      copyFileSync(join(dir, folder, snap), resolve(here, 'bcf-markup-snapshot.png'));
      console.log('snapshot bench/bcf-markup-snapshot.png');
    }
    bcfClient(files[v], v);
  }

  // ------------------------------------------------------------------ part 4: reload, import, compare
  await boot();
  await page.setInputFiles('input[data-bcf=open]', files['3.0']);
  await page.waitForFunction(() => window.__xrayBcf.topics.length === 1, null, { timeout: 20000 });
  const back = await page.evaluate(() => window.__xrayBcf.topics.map((t) => ({ guid: t.guid.toLowerCase(), pin: t.pin, annotations: window.__xrayBcf.annotations(t.guid) })));
  const norm = (s) => JSON.stringify(s.map((t) => ({ ...t, annotations: Object.fromEntries(Object.entries(t.annotations).map(([k, v]) => [k.toLowerCase(), v])) })));
  check('import restores the pin and the annotations exactly', norm(back) === norm(state), norm(back) === norm(state) ? '' : `${norm(back).slice(0, 300)} vs ${norm(state).slice(0, 300)}`);
  const warn = await page.evaluate(() => window.__xrayBcf.status);
  check('import has no warnings', !/warning/.test(warn), warn);
  // the pin click activates the topic and applies its viewpoint
  await settle();
  await page.waitForTimeout(300);
  const pinEl = await page.evaluate(() => { const e = document.querySelector('svg.xray-svg-overlay [data-bcf-pin] [data-role=pin], svg.xray-svg-overlay [data-bcf-pin] [data-role=edge]'); if (!e) return null; const r = e.getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; });
  check('pin drawn after import', !!pinEl);
  if (pinEl) await page.mouse.click(pinEl.x, pinEl.y);
  await page.waitForTimeout(2500);
  await settle();
  const act = await page.evaluate(() => ({ status: window.__xrayBcf.status, drawn: document.querySelectorAll('svg.xray-svg-overlay [data-mk]').length, sel: document.querySelector('#issues-panel .is-item.sel') !== null }));
  // Assertion changed: the imported viewpoint became a sketch; once the viewpoint is applied the markup view draws it.
  check('clicking the pin applies the viewpoint and shows the annotations', /Viewpoint applied/.test(act.status) && act.drawn === 3 && act.sel, `${act.status}; drawn ${act.drawn}`);
  await page.waitForTimeout(400);
  await page.screenshot({ path: resolve(here, 'bcf-markup-reimport.png') });
  console.log('screenshot bench/bcf-markup-reimport.png');

  check('no console errors', errors.length === 0, errors.slice(0, 3).join(' | '));
} catch (e) {
  failed = true;
  console.log('ERROR', e instanceof Error ? e.stack ?? e.message : e);
} finally {
  await browser?.close();
  vite.kill();
}
process.exit(failed ? 1 : 0);
