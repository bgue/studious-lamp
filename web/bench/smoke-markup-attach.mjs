// Headless check for markup attachments on /?model=fzk-haus (see docs-features/markup.md, "Attachments"):
//   - a cloud drawn around an element is attached (the chip says so); after a 60 degree orbit its projected outline still
//     overlaps the element on the screen (the old depth plane slid away from it);
//   - a cloud in empty space is view-locked: faded at 15 degrees, a pin at 60 degrees, the pin flies back to the authored view;
//   - the chip's Change menu re-attaches (view-locked), and Undo brings the old attachment back;
//   - the same shapes still draw in both pointer modes (Arrow and Hand);
//   - the BCF export carries the target in the viewpoint selection and the outline as 3D <Lines>;
//   - phone layout; zero console errors.
// Screenshots: bench/markup-attach-authored.png, markup-attach-orbited.png, markup-viewlocked-pin.png.
// Usage: SMOKE_PORT=5703 node bench/smoke-markup-attach.mjs
import { spawn, spawnSync } from 'node:child_process';
import { createRequire } from 'node:module';
import { mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const port = Number(process.env.SMOKE_PORT ?? 5703);
const tmp = mkdtempSync(join(tmpdir(), 'smoke-attach-'));

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

const errors = [];
const keep = [];
let browser;
try {
  await waitForServer();
  browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1500, height: 780 }, acceptDownloads: true });
  const page = await ctx.newPage();
  page.setDefaultTimeout(Number(process.env.SMOKE_TIMEOUT ?? 180000));
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', (e) => errors.push(`[pageerror] ${e.message}`));

  async function boot(pg = page, model = 'fzk-haus') {
    await pg.goto(`http://127.0.0.1:${port}/?model=${model}`);
    await pg.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: 240000 });
    const err = await pg.evaluate('window.__xrayError');
    if (err) throw new Error(`startup failed: ${err}`);
  }
  const settle = (pg = page) => pg.evaluate(() => window.__xray.app.controller.settle());
  const cam = (pg = page) => pg.evaluate(() => {
    const c = window.__xray.app.renderer.camera;
    const t = window.__xray.app.renderer.controls.target;
    return { p: [c.position.x, c.position.y, c.position.z], t: [t.x, t.y, t.z] };
  });
  const dist3 = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
  async function setCamera(pos, target, pg = page) {
    await pg.evaluate(([pos, target]) => {
      const app = window.__xray.app;
      window.__cinematic?.cancelFlight?.();
      app.renderer.camera.position.set(...pos);
      app.renderer.controls.target.set(...target);
      app.renderer.controls.update();
      app.controller.settle();
    }, [pos, target]);
    await pg.waitForTimeout(300);
  }
  /** Orbit the camera about its target by `deg` degrees of azimuth. */
  async function orbit(deg, pg = page) {
    await pg.evaluate((deg) => {
      const app = window.__xray.app;
      const c = app.renderer.camera;
      const t = app.renderer.controls.target;
      const a = (deg * Math.PI) / 180;
      const dx = c.position.x - t.x, dz = c.position.z - t.z;
      c.position.x = t.x + dx * Math.cos(a) + dz * Math.sin(a);
      c.position.z = t.z - dx * Math.sin(a) + dz * Math.cos(a);
      app.renderer.controls.update();
      app.renderer.markDirty();
      app.controller.settle();
    }, deg);
    await pg.waitForTimeout(500);
  }
  async function drag(x0, y0, x1, y1, pg = page) {
    await pg.mouse.move(x0, y0);
    await pg.mouse.down();
    for (let i = 1; i <= 4; i++) await pg.mouse.move(x0 + ((x1 - x0) * i) / 4, y0 + ((y1 - y0) * i) / 4);
    await pg.mouse.up();
  }
  const last = (pg = page) => pg.evaluate(() => { const s = window.__xrayMarkup.get(window.__xrayMarkup.list().find((x) => x.active).id); return s.markups[s.markups.length - 1]; });
  const attachOf = (id, pg = page) => pg.evaluate((id) => window.__xrayMarkup.attachment(id), id);
  const chipText = (pg = page) => pg.evaluate(() => document.querySelector('#markup-attach-chip [data-attach-text]')?.textContent ?? null);
  /** Screen bbox of the outline of a markup, from its SVG shape. */
  const outlineBox = (id, pg = page) => pg.evaluate((id) => {
    const els = Array.from(document.querySelectorAll(`[data-mk="${id}"] [data-role="shape"]`));
    if (!els.length) return null;
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (const e of els) { const r = e.getBoundingClientRect(); x0 = Math.min(x0, r.left); y0 = Math.min(y0, r.top); x1 = Math.max(x1, r.right); y1 = Math.max(y1, r.bottom); }
    return { x0, y0, x1, y1 };
  }, id);
  const elementBox = (guid, pg = page) => pg.evaluate((guid) => {
    const app = window.__xray.app;
    const id = app.controller.model.byGlobalId.get(guid);
    const b = app.controller.model.elements[id].bounds;
    const cm = app.renderer.camera;
    cm.updateMatrixWorld();
    const r = app.canvas.getBoundingClientRect();
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (let i = 0; i < 8; i++) {
      const v = cm.position.clone().set(i & 1 ? b[3] : b[0], i & 2 ? b[4] : b[1], i & 4 ? b[5] : b[2]).project(cm);
      const x = r.left + (v.x * 0.5 + 0.5) * r.width, y = r.top + (1 - (v.y * 0.5 + 0.5)) * r.height;
      x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y);
    }
    return { x0, y0, x1, y1 };
  }, guid);
  const overlap = (a, b) => {
    const w = Math.min(a.x1, b.x1) - Math.max(a.x0, b.x0), h = Math.min(a.y1, b.y1) - Math.max(a.y0, b.y0);
    return w > 0 && h > 0 ? (w * h) / Math.max(1, (a.x1 - a.x0) * (a.y1 - a.y0)) : 0;
  };

  // ------------------------------------------------------------------ part 1: attached cloud
  await boot();
  await page.keyboard.press('k');
  await page.waitForSelector('#markup-drawer');
  await page.fill('#markup-drawer [data-keep=author]', 'smoke@example.org');
  await page.dispatchEvent('#markup-drawer [data-keep=author]', 'change');
  // Close the drawer's cover: the free part of the canvas.
  const free = await page.evaluate(() => {
    const cv = window.__xray.app.canvas.getBoundingClientRect();
    const dr = document.querySelector('#xray-toolbar-drawer')?.getBoundingClientRect();
    const gui = document.querySelector('.lil-gui.root')?.getBoundingClientRect();
    return { x0: Math.max(cv.left, dr ? dr.right : 0) + 12, x1: Math.min(cv.right, gui && gui.width ? gui.left : cv.right) - 12, y0: cv.top + 60, y1: cv.bottom - 60 };
  });
  // A wall element whose centre is looked at from the front-right, with the orbit pivot behind it, so the old plane would slide away.
  const wallGuid = await page.evaluate(() => {
    const els = window.__xray.app.controller.model.elements;
    const walls = els.filter((e) => e.ifcClass === 'IfcWallStandardCase' && e.globalId).sort((a, b) => ((b.bounds[3] - b.bounds[0]) * (b.bounds[4] - b.bounds[1])) - ((a.bounds[3] - a.bounds[0]) * (a.bounds[4] - a.bounds[1])));
    return walls[0].globalId;
  });
  const wallInfo = await page.evaluate((g) => {
    const app = window.__xray.app;
    const e = app.controller.model.elements[app.controller.model.byGlobalId.get(g)];
    const b = e.bounds;
    return { c: [(b[0] + b[3]) / 2, (b[1] + b[4]) / 2, (b[2] + b[5]) / 2], size: [b[3] - b[0], b[4] - b[1], b[5] - b[2]] };
  }, wallGuid);
  // The pivot is 6 m behind the wall (towards the model centre), the camera in front of it.
  const c0 = wallInfo.c;
  const along = wallInfo.size[0] > wallInfo.size[2] ? [0, 0, 1] : [1, 0, 0];
  const camPos = [c0[0] + along[0] * 14 + 4, c0[1] + 3, c0[2] + along[2] * 14 + 4];
  const pivot = [c0[0] - along[0] * 6, c0[1], c0[2] - along[2] * 6];
  await setCamera(camPos, pivot);
  await page.click('#markup-drawer >> text=New set from view');
  await page.waitForFunction(() => window.__xrayMarkup.list().length === 1);
  await page.waitForTimeout(300);
  const wbox = await elementBox(wallGuid);
  console.log('wall box', JSON.stringify(wbox), 'free', JSON.stringify(free));
  // Draw a cloud on the middle of the wall's screen box, clear of the drawer.
  const cx0 = Math.max(wbox.x0, free.x0), cx1 = Math.min(wbox.x1, free.x1);
  const cy0 = wbox.y0, cy1 = wbox.y1;
  const rx0 = cx0 + (cx1 - cx0) * 0.3, rx1 = cx0 + (cx1 - cx0) * 0.7, ry0 = cy0 + (cy1 - cy0) * 0.3, ry1 = cy0 + (cy1 - cy0) * 0.7;
  await page.click('#markup-drawer [data-tool-id=cloud]');
  await drag(rx0, ry0, rx1, ry1);
  await page.waitForTimeout(400);
  const m1 = await last();
  const a1 = await attachOf(m1.id);
  check('a cloud drawn on an element is attached (surface)', a1?.attach.kind === 'surface' && a1.attach.surface.pts.length > 10, JSON.stringify(a1?.description));
  const ct = await chipText();
  check('the chip on the canvas says attached', /^Attached to:/.test(ct ?? ''), String(ct));
  await page.click('#markup-drawer [data-tool-id=select]');
  const ob0 = await outlineBox(m1.id);
  const ov0 = ob0 ? overlap(ob0, await elementBox(wallGuid)) : 0;
  check('authored view: the outline lies on the element', ov0 > 0.7, ov0.toFixed(2));
  await page.screenshot({ path: resolve(here, 'markup-attach-authored.png') });
  keep.push('markup-attach-authored.png');
  await orbit(60);
  const ob1 = await outlineBox(m1.id);
  const eb1 = await elementBox(wallGuid);
  const ov1 = ob1 ? overlap(ob1, eb1) : 0;
  check('after a 60 degree orbit the projected cloud still overlaps its element', ov1 > 0.6, ov1.toFixed(2));
  // The drawer covers the left of the view: close it for the picture, then bring it back.
  await page.evaluate(() => window.__xrayToolbar.close());
  await page.waitForTimeout(500);
  await page.screenshot({ path: resolve(here, 'markup-attach-orbited.png') });
  keep.push('markup-attach-orbited.png');
  await page.evaluate(() => window.__xrayToolbar.open('markup'));
  await page.waitForSelector('#markup-drawer');

  // Behind the building the wall hides the outline: dashed and faint instead of showing through.
  check('visible from the front side: not dimmed', (await page.$(`[data-mk="${m1.id}"][data-behind]`)) === null);
  await orbit(120);
  await page.waitForTimeout(700);
  const dim = await page.evaluate((id) => {
    const g = document.querySelector(`[data-mk="${id}"]`);
    const sh = g?.querySelector('[data-role="shape"]');
    return { behind: g?.getAttribute('data-behind'), dash: sh?.getAttribute('stroke-dasharray') ?? null, opacity: sh?.getAttribute('opacity') ?? null, title: g?.querySelector('title')?.textContent ?? '' };
  }, m1.id);
  check('far side of the wall: the outline is dashed and dimmed, tooltip says behind', dim.behind === '1' && !!dim.dash && Number(dim.opacity) < 0.5 && /behind/.test(dim.title), JSON.stringify(dim));

  // ------------------------------------------------------------------ part 2: change the attachment, undo
  await setCamera(camPos, pivot);
  await page.click(`#markup-drawer [data-mk-item="${m1.id}"]`);
  await page.waitForSelector('#markup-drawer [data-attach-chip]');
  check('panel chip shows the attachment', /^Attached to:/.test(await page.textContent('#markup-drawer [data-attach-chip] [data-attach-text]')));
  await page.click('#markup-drawer [data-attach-chip] [data-act=attach-change]');
  await page.click('#markup-drawer [data-attach-choice=none]');
  await page.waitForTimeout(200);
  check('Change > View-locked re-attaches', (await attachOf(m1.id)).attach.kind === 'none' && /View-locked/.test(await page.textContent('#markup-drawer [data-attach-chip] [data-attach-text]')));
  await page.evaluate(() => window.__xrayMarkup.undo());
  await page.waitForTimeout(200);
  check('Undo brings the attachment back', (await attachOf(m1.id)).attach.kind === 'surface');
  await page.click('#markup-drawer [data-attach-chip] [data-act=attach-change]');
  await page.click('#markup-drawer [data-attach-choice=region]');
  await page.waitForTimeout(200);
  check('Change > Region fits a 3D box', (await attachOf(m1.id)).attach.kind === 'region');
  await page.evaluate(() => window.__xrayMarkup.undo());

  // ------------------------------------------------------------------ part 3: BCF export
  const setId = await page.evaluate(() => window.__xrayMarkup.list()[0].id);
  const topic = await page.evaluate(async (s) => window.__xrayMarkup.toBcf(s), setId);
  check('markup set converts to a BCF topic', typeof topic === 'string');
  const b64 = await page.evaluate(async () => {
    const bytes = await window.__xrayBcf.exportZip('2.1');
    let s = '';
    for (let i = 0; i < bytes.length; i += 8192) s += String.fromCharCode(...bytes.subarray(i, i + 8192));
    return btoa(s);
  });
  const zipPath = join(tmp, 'attach.bcf');
  writeFileSync(zipPath, Buffer.from(b64, 'base64'));
  const py = spawnSync('python3', ['-I', '-c', 'import sys,zipfile\nz=zipfile.ZipFile(sys.argv[1])\nfor n in z.namelist():\n    if n.endswith(".bcfv"): print(z.read(n).decode())', zipPath], { encoding: 'utf8' });
  const xml = py.stdout;
  const lines = (xml.match(/<Line>/g) ?? []).length;
  check('BCF export: the outline is written as 3D <Lines>', lines > 8, `${lines} lines`);
  check('BCF export: the target is in the viewpoint selection', new RegExp(`<Component IfcGuid="${wallGuid}"`).test(xml) || xml.includes(wallGuid));

  // ------------------------------------------------------------------ part 4: view-locked cloud, fade, pin, fly back
  await page.click('#markup-drawer >> text=Close').catch(() => undefined);
  await setCamera([c0[0] + along[0] * 60 + 20, c0[1] + 25, c0[2] + along[2] * 60 + 20], c0);
  await page.evaluate(() => window.__xrayMarkup.setTool('select'));
  await page.click('#markup-drawer >> text=New set from view');
  await page.waitForFunction(() => window.__xrayMarkup.list().length === 2);
  const sky = await page.evaluate(() => { const cv = window.__xray.app.canvas.getBoundingClientRect(); return { x: cv.left + cv.width * 0.62, y: cv.top + 80 }; });
  await page.click('#markup-drawer [data-tool-id=cloud]');
  await drag(sky.x, sky.y, sky.x + 150, sky.y + 70);
  await page.waitForTimeout(300);
  const m2 = await last();
  const a2 = await attachOf(m2.id);
  check('a cloud in empty space is view-locked', a2?.attach.kind === 'none' && /View-locked/.test(a2.description.text), a2?.description.text);
  await page.click('#markup-drawer [data-tool-id=select]');
  check('near the authored view the view-locked cloud is at full strength', (await page.evaluate(() => window.__xrayMarkup.lock?.mode)) === 'full');
  const set2cam = await cam();
  await orbit(15);
  const l15 = await page.evaluate(() => window.__xrayMarkup.lock);
  check('15 degrees: the view-locked cloud is faded', l15.mode === 'fade' && l15.alpha > 0.05 && l15.alpha < 0.95, `${l15.angle.toFixed(1)} deg, alpha ${l15.alpha.toFixed(2)}`);
  await orbit(45);
  const l60 = await page.evaluate(() => window.__xrayMarkup.lock);
  check('60 degrees: only a pin is left', l60.mode === 'pin' && (await page.$$(`[data-mk-pin="${m2.id}"] [data-role="pin"]`)).length > 0, `${l60.angle.toFixed(1)} deg`);
  const pinTitle = await page.textContent(`[data-mk-pin="${m2.id}"] title`);
  check('the pin tooltip names the markup', /Cloud \d+/.test(pinTitle ?? ''), String(pinTitle));
  await page.evaluate(() => window.__xrayToolbar.close());
  await page.waitForTimeout(500);
  await page.screenshot({ path: resolve(here, 'markup-viewlocked-pin.png') });
  await page.evaluate(() => window.__xrayToolbar.open('markup'));
  await page.waitForSelector('#markup-drawer');
  keep.push('markup-viewlocked-pin.png');
  await page.click(`[data-mk-pin="${m2.id}"] text[data-role=pin]`);
  await page.waitForTimeout(2500);
  const back = await cam();
  check('clicking the pin flies back to the authored view', dist3(back.p, set2cam.p) < 0.5, `${dist3(back.p, set2cam.p).toFixed(2)} m`);
  // settings
  await page.evaluate(() => { window.__xrayMarkup.viewLocked3d = 'hidden'; });
  await orbit(60);
  check('setting "hidden": nothing in 3D', (await page.$$(`[data-mk="${m2.id}"]`)).length === 0);
  await page.evaluate(() => { window.__xrayMarkup.viewLocked3d = 'pin only'; });
  await setCamera(set2cam.p, set2cam.t);
  check('setting "pin only": a pin even at the authored view', (await page.$$(`[data-mk-pin="${m2.id}"]`)).length > 0);
  await page.evaluate(() => { window.__xrayMarkup.viewLocked3d = 'near view + pin'; });

  // ------------------------------------------------------------------ part 5: both pointer modes
  for (const mode of ['arrow', 'hand']) {
    await page.evaluate((m) => window.__xrayPointer.setMode(m), mode);
    await setCamera(camPos, pivot);
    const before = (await page.evaluate(() => window.__xrayMarkup.get(window.__xrayMarkup.list().find((x) => x.active).id).markups.length));
    await page.click('#markup-drawer [data-tool-id=rect]');
    const camA = await cam();
    await drag(rx0, ry0 + 20, rx0 + 120, ry0 + 90);
    await page.waitForTimeout(250);
    const after = (await page.evaluate(() => window.__xrayMarkup.get(window.__xrayMarkup.list().find((x) => x.active).id).markups.length));
    const camB = await cam();
    check(`${mode} pointer mode: a rectangle draws and the orbit stays`, after === before + 1 && dist3(camA.p, camB.p) < 1e-6, `${before} -> ${after}`);
    await page.click('#markup-drawer [data-tool-id=select]');
  }

  // ------------------------------------------------------------------ part 6: phone
  const phone = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true, deviceScaleFactor: 2 });
  const pp = await phone.newPage();
  pp.on('console', (m) => { if (m.type() === 'error') errors.push(`[phone] ${m.text()}`); });
  pp.on('pageerror', (e) => errors.push(`[phone pageerror] ${e.message}`));
  await boot(pp);
  await pp.evaluate(() => window.__xrayToolbar.open('markup'));
  await pp.waitForSelector('#markup-drawer');
  await pp.click('#markup-drawer >> text=New set from view');
  await pp.waitForFunction(() => window.__xrayMarkup.list().length === 1);
  await pp.evaluate(() => window.__xrayToolbar.close());
  const mm = await pp.evaluate(() => {
    const app = window.__xray.app;
    const sz = { w: app.canvas.clientWidth, h: app.canvas.clientHeight };
    return window.__xrayMarkup.add({ kind: 'cloud', points: [[sz.w * 0.25, sz.h * 0.35], [sz.w * 0.75, sz.h * 0.6]] }).id;
  });
  await pp.waitForTimeout(400);
  await pp.evaluate((id) => window.__xrayMarkup.update(id, {}), mm);
  const pa = await pp.evaluate((id) => window.__xrayMarkup.attachment(id), mm);
  check('phone: a shape gets an attachment decision', !!pa && typeof pa.attach.kind === 'string', pa?.description.text);
  const over = await pp.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1);
  check('phone: no horizontal page scroll', over);
  await pp.screenshot({ path: join(tmp, 'markup-attach-phone.png') });
  await phone.close();

  check('no console errors', errors.length === 0, errors.slice(0, 4).join(' | '));
  console.log('new screenshots:', keep.map((k) => `bench/${k}`).join(' '));
} catch (e) {
  failed = true;
  console.log('ERROR', e instanceof Error ? e.stack ?? e.message : e);
} finally {
  await browser?.close();
  vite.kill();
}
process.exit(failed ? 1 : 0);
