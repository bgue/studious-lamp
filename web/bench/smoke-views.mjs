// Headless smoke test for saved views (docs-features/saved-views.md). Per model (fzk-haus, synth5k), at 1600x900:
//   - saves 3 views with different cameras, section box / plane, view modes, imaging, hides / isolate, ortho, roll,
//     explode, and records the expected state of each;
//   - reloads, restores every view (animated) and compares camera and section planes numerically, plus modes, imaging,
//     x-ray, selection and hides;
//   - plays the views (dwell 1.5 s) and stops with Escape;
//   - opens the share link of one view in a fresh browser context (empty storage) and compares again;
//   - fzk-haus only: the phone layout (390x844, list and grid) and a packed page (xray-pack --views --open-view) from
//     file://.
// Screenshots: bench/views-<model>-<n>.png, views-phone.png, views-phone-grid.png, views-pack.png. No console errors.
// Usage: SMOKE_PORT=5651 node bench/smoke-views.mjs        (SMOKE_REUSE=1 uses a server already on that port)
import { spawn, spawnSync } from 'node:child_process';
import { createRequire } from 'node:module';
import { mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const port = Number(process.env.SMOKE_PORT ?? 5651);
const base = `http://127.0.0.1:${port}`;

function loadPlaywright() {
  const candidates = [process.env.PLAYWRIGHT_MODULE, resolve(root, 'node_modules/playwright'), '/opt/node-tools/node_modules/playwright', '/opt/node22/lib/node_modules/playwright', 'playwright'].filter(Boolean);
  for (const c of candidates) {
    try { return createRequire(import.meta.url)(c); } catch { /* try next */ }
  }
  throw new Error('playwright not found; set PLAYWRIGHT_MODULE');
}
const { chromium } = loadPlaywright();

let vite = null;
let viteLog = '';
if (!process.env.SMOKE_REUSE) {
  vite = spawn(resolve(root, 'node_modules/.bin/vite'), ['--config', resolve(here, 'vite.smoke.config.mjs'), '--host', '127.0.0.1', '--port', String(port), '--strictPort'], { cwd: root, stdio: ['ignore', 'pipe', 'pipe'] });
  vite.stdout.on('data', (d) => (viteLog += d));
  vite.stderr.on('data', (d) => (viteLog += d));
}
async function waitForServer() {
  for (let i = 0; i < 100; i++) {
    try { const r = await fetch(`${base}/`); if (r.ok) return; } catch { /* retry */ }
    await new Promise((r) => setTimeout(r, 200));
  }
  throw new Error('vite did not start:\n' + viteLog);
}

const checks = [];
function check(name, ok, detail = '') {
  checks.push({ name, ok: !!ok });
  console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${detail ? ` (${detail})` : ''}`);
}

const errors = [];
function watch(page, label) {
  page.setDefaultTimeout(240000); // software rendering: one frame can take seconds
  page.on('console', (m) => { if (m.type() === 'error') errors.push(`${label}: ${m.text()}`); });
  page.on('pageerror', (e) => errors.push(`${label}: pageerror ${e.message}`));
}

async function ready(page) {
  await page.waitForFunction('window.__xrayReady === true || window.__xrayError', null, { timeout: 240000, polling: 500 });
  const err = await page.evaluate('window.__xrayError');
  if (err) throw new Error(`startup failed: ${err}`);
  await page.waitForFunction('!!window.__xrayViews', null, { timeout: 60000, polling: 500 });
}

/** Wait until the camera holds still (two samples 300 ms apart within 1e-5). */
async function settle(page, maxMs = 12000) {
  const t0 = Date.now();
  let last = null;
  while (Date.now() - t0 < maxMs) {
    const c = await page.evaluate(() => window.__xrayViews.camera());
    if (last && dist(c.position, last.position) < 1e-5 && dist(c.target, last.target) < 1e-5) return c;
    last = c;
    await page.waitForTimeout(300);
  }
  return last;
}

/** A screenshot that waits long for a software-rendered frame and never aborts the run. */
async function shot(page, file, opts = {}) {
  try {
    await page.screenshot({ path: resolve(here, file), timeout: 240000, ...opts });
  } catch (e) {
    console.log(`(screenshot ${file} skipped: ${String(e.message ?? e).split('\n')[0]})`);
  }
}

const dist = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);

/** The state the comparison uses. */
function snapshot(page) {
  return page.evaluate(() => {
    const app = window.__xray.app;
    const p = window.__xrayParams.collect();
    const els = app.controller.model.elements;
    const sec = window.__xraySection;
    return {
      camera: window.__xrayViews.camera(),
      planes: sec.planes().map((q) => ({ normal: [...q.normal], point: [...q.point] })),
      box: !!sec.config.box.enabled,
      plane: !!sec.config.plane.enabled,
      behind: !!p.viewModes?.behind?.enabled,
      peel: !!p.viewModes?.peel?.enabled,
      imaging: p.imaging?.style ?? null,
      xray: app.settings.xray,
      selection: app.selection.map((id) => els[id].globalId).sort(),
      hidden: app.controller.settings.overrides.userHides.size,
      exploded: window.__cinematic?.exploded === true,
    };
  });
}

function planesClose(a, b, tol = 1e-4) {
  if (a.length !== b.length) return false;
  return a.every((p, i) => dist(p.normal, b[i].normal) < tol && dist(p.point, b[i].point) < tol);
}

function compare(label, got, want) {
  const dp = dist(got.camera.position, want.camera.position);
  const dt = dist(got.camera.target, want.camera.target);
  const du = dist(got.camera.up, want.camera.up);
  check(`${label}: camera position, target, up within 1e-3`, dp < 1e-3 && dt < 1e-3 && du < 1e-3, `dp ${dp.toExponential(1)} dt ${dt.toExponential(1)} du ${du.toExponential(1)}`);
  check(`${label}: fov and projection`, Math.abs(got.camera.fov - want.camera.fov) < 1e-6 && got.camera.ortho === want.camera.ortho, `fov ${got.camera.fov} ortho ${got.camera.ortho}`);
  check(`${label}: section planes within 1e-4`, planesClose(got.planes, want.planes) && got.box === want.box && got.plane === want.plane, `${got.planes.length} planes, box ${got.box}, plane ${got.plane}`);
  check(`${label}: modes, imaging, x-ray`, got.behind === want.behind && got.peel === want.peel && got.imaging === want.imaging && got.xray === want.xray, `behind ${got.behind} peel ${got.peel} imaging ${got.imaging} xray ${got.xray}`);
  check(`${label}: selection, hides, explode`, JSON.stringify(got.selection) === JSON.stringify(want.selection) && got.hidden === want.hidden && got.exploded === want.exploded, `sel ${got.selection.length} hidden ${got.hidden} exploded ${got.exploded}`);
}

async function waitCamera(page, want, maxMs = 15000) {
  const t0 = Date.now();
  while (Date.now() - t0 < maxMs) {
    const c = await page.evaluate(() => window.__xrayViews.camera());
    if (dist(c.position, want.position) < 1e-3 && dist(c.target, want.target) < 1e-3) return Date.now() - t0;
    await page.waitForTimeout(200);
  }
  return -1;
}

const setCam = (page, pos, tgt) => page.evaluate(([p, t]) => {
  const r = window.__xray.app.renderer;
  r.camera.position.set(...p);
  r.controls.target.set(...t);
  r.controls.update();
}, [pos, tgt]);

const SCENES = {
  'fzk-haus': [
    {
      name: 'Window box behind',
      async setup(page) {
        await page.evaluate(() => {
          window.__xray.app.selectIds([22]);
          window.__xraySection.fitToSelection();
          window.__xrayParams.apply({ schema: 'xray-params/1', viewModes: { behind: { enabled: true } } });
        });
        await page.waitForTimeout(1500);
        await setCam(page, [6, 5.5, 13], [-3.95, -1.8, -4.8]);
      },
    },
    {
      name: 'Plane radiograph',
      async setup(page) {
        await page.evaluate(() => {
          const app = window.__xray.app;
          app.clearSelection();
          window.__xraySection.clear();
          window.__xraySection.set({ plane: { enabled: true, axis: 'y', offset: 1.2 } });
          window.__xrayParams.apply({ schema: 'xray-params/1', viewModes: { behind: { enabled: false } }, imaging: { style: 'radiograph' } });
          const h = app.controller.settings.overrides.userHides;
          h.add(0);
          h.add(1);
          app.controller.refreshOverrides();
          app.runSightlinesNow();
        });
        await setCam(page, [2, 22, 9], [0, 0, 0]);
      },
    },
    {
      name: 'Isolate ortho rolled',
      async setup(page) {
        await page.evaluate(() => {
          const app = window.__xray.app;
          window.__xraySection.clear();
          window.__xrayParams.apply({ schema: 'xray-params/1', imaging: { style: 'standard' } });
          app.setXray(false);
          const ids = [20, 21, 22];
          app.selectIds(ids);
          const h = app.controller.settings.overrides.userHides;
          h.clear();
          for (let i = 0; i < app.controller.model.elements.length; i++) if (!ids.includes(i)) h.add(i);
          app.controller.refreshOverrides();
          app.runSightlinesNow();
        });
        await page.waitForTimeout(1500);
        await setCam(page, [-12, 6, 9], [0, 1.5, 0]);
        await page.evaluate(() => document.activeElement?.blur?.());
        await page.keyboard.press('Alt+Digit5'); // pseudo-orthographic
        await page.waitForTimeout(300);
        await page.evaluate(() => window.__xrayGizmo.roll(1));
      },
    },
  ],
  synth5k: [
    {
      name: 'Duct box peel',
      async setup(page) {
        await page.evaluate(() => {
          const app = window.__xray.app;
          const els = app.controller.model.elements;
          const duct = els.find((e) => e.ifcClass === 'IfcDuctSegment') ?? els[0];
          app.selectIds([duct.id]);
          window.__xraySection.fitToSelection();
          window.__xrayParams.apply({ schema: 'xray-params/1', viewModes: { peel: { enabled: true } } });
        });
        await page.waitForTimeout(1500);
        const c = await page.evaluate(() => window.__xrayViews.camera());
        await setCam(page, c.position.map((x, i) => x + [3, 2, -2][i]), c.target);
      },
    },
    {
      name: 'Plane x radiograph',
      async setup(page) {
        await page.evaluate(() => {
          window.__xray.app.clearSelection();
          window.__xraySection.clear();
          window.__xraySection.set({ plane: { enabled: true, axis: 'x', offset: 2, flip: true } });
          window.__xrayParams.apply({ schema: 'xray-params/1', viewModes: { peel: { enabled: false } }, imaging: { style: 'radiograph' } });
        });
        await page.evaluate(() => window.__xrayGizmo.lookFrom?.('top'));
        await page.waitForTimeout(1200);
      },
    },
    {
      name: 'Exploded isolate',
      async setup(page) {
        await page.evaluate(() => {
          const app = window.__xray.app;
          window.__xraySection.clear();
          window.__xrayParams.apply({ schema: 'xray-params/1', imaging: { style: 'standard' } });
          const els = app.controller.model.elements;
          const ids = els.filter((e) => e.ifcClass === 'IfcDuctSegment').slice(0, 20).map((e) => e.id);
          app.selectIds(ids.length ? ids : [0, 1, 2]);
        });
        await page.waitForTimeout(1500);
        await page.evaluate(() => {
          const app = window.__xray.app;
          const sel = new Set(app.selection);
          const h = app.controller.settings.overrides.userHides;
          for (let i = 0; i < app.controller.model.elements.length; i++) if (!sel.has(i) && i % 3 !== 0) h.add(i);
          app.controller.refreshOverrides();
          app.runSightlinesNow();
          window.__cinematic?.explode();
        });
        await page.evaluate(() => window.__xrayGizmo.lookFrom?.('iso') ?? window.__xrayGizmo.home());
        await page.waitForTimeout(1500);
      },
    },
  ],
};

async function runScene(browser, model) {
  const ctx = await browser.newContext({ viewport: { width: 1600, height: 900 } });
  const page = await ctx.newPage();
  watch(page, model);
  await page.goto(`${base}/?model=${model}`);
  await ready(page);
  await page.evaluate((m) => {
    for (const k of Object.keys(localStorage)) if (k.startsWith('xray.views.')) localStorage.removeItem(k);
    localStorage.setItem('xray.sidebar', JSON.stringify({ collapsed: false, tab: 'views' }));
  }, model);
  await page.reload();
  await ready(page);
  check(`${model}: Views tab is open after the reload`, await page.evaluate(() => document.querySelector('.sb-tab.active')?.textContent === 'Views'));

  const expected = [];
  for (const spec of SCENES[model]) {
    await spec.setup(page);
    await settle(page);
    const want = await snapshot(page);
    const saved = await page.evaluate((n) => window.__xrayViews.save(n), spec.name);
    expected.push({ name: spec.name, want, id: saved.id });
    check(`${model}: saved "${spec.name}" with a thumbnail`, saved.thumb && saved.thumb.startsWith('data:image/jpeg') && saved.thumb.length > 800, `${saved.thumb?.length ?? 0} chars`);
  }
  const rows = await page.evaluate(() => [...document.querySelectorAll('.vw-row .vw-name')].map((e) => e.textContent));
  check(`${model}: 3 rows in the Views tab`, rows.length === 3, rows.join(' | '));

  await page.reload();
  await ready(page);
  const list = await page.evaluate(() => window.__xrayViews.list());
  check(`${model}: 3 views survive the reload, with thumbnails`, list.length === 3 && list.every((v) => v.hasThumb), list.map((v) => `${v.name} [${v.summary}]`).join('; '));

  const order = [0, 1, 2, 0];
  for (let k = 0; k < order.length; k++) {
    const e = expected[order[k]];
    // Through the UI: a click on the row name.
    await page.evaluate((i) => document.querySelectorAll('.vw-row .vw-name')[i].click(), order[k]);
    const ms = await waitCamera(page, e.want.camera);
    await settle(page, 4000);
    const got = await snapshot(page);
    compare(`${model}: restore "${e.name}"${k === 3 ? ' again' : ''} (${ms} ms)`, got, e.want);
    if (k < 3) await shot(page, `views-${model}-${order[k] + 1}.png`);
  }
  check(`${model}: active row marked`, await page.evaluate(() => document.querySelectorAll('.vw-row.active').length === 1));

  // Hover thumbnail.
  // A synthetic pointerover: page.hover can time out while a software-rendered frame blocks the page.
  await page.evaluate(() => document.querySelector('.vw-row:nth-child(2) .vw-name').dispatchEvent(new PointerEvent('pointerover', { bubbles: true, pointerType: 'mouse' })));
  await page.waitForTimeout(200);
  check(`${model}: hover shows the thumbnail next to the row`, await page.evaluate(() => {
    const p = document.querySelector('.vw-peek');
    return p && p.style.display !== 'none' && !!p.querySelector('img');
  }));
  if (model === 'fzk-haus') await shot(page, 'views-hover.png', { clip: { x: 0, y: 0, width: 700, height: 300 } });
  await page.evaluate(() => document.querySelector('.vw-list').dispatchEvent(new PointerEvent('pointerleave', { pointerType: 'mouse' })));

  // Play.
  await page.evaluate(() => window.__xrayViews.play(1500));
  const seen = new Set();
  for (let i = 0; i < 40 && seen.size < 3; i++) {
    seen.add(await page.evaluate(() => window.__xrayViews.active));
    await page.waitForTimeout(250);
  }
  check(`${model}: play steps through all 3 views`, seen.size >= 3, `${seen.size} seen`);
  check(`${model}: Play button shows Stop while playing`, await page.evaluate(() => document.querySelector('.vw-play')?.textContent?.includes('Stop')));
  await page.evaluate(() => document.activeElement?.blur?.());
  await page.keyboard.press('Escape');
  await page.waitForTimeout(200);
  // The play timer may step once more before the key arrives (slow frames), so compare with the active view.
  const after = await page.evaluate(() => {
    const v = window.__xrayViews.get(window.__xrayViews.active);
    return { playing: window.__xrayViews.playing, sel: window.__xray.app.selection.length, want: v ? v.selection.length : -1 };
  });
  check(`${model}: Escape stops playing and keeps the selection`, !after.playing && after.sel === after.want, `sel ${after.sel}, view has ${after.want}`);

  // Keys: Shift+PageDown steps to the next view.
  const before = await page.evaluate(() => window.__xrayViews.active);
  await page.keyboard.press('Shift+PageDown');
  await page.waitForTimeout(300);
  const nextId = await page.evaluate(() => window.__xrayViews.active);
  check(`${model}: Shift+PageDown steps to the next view`, nextId && nextId !== before);

  // Share link in a fresh context.
  const shareIdx = 1;
  const url = await page.evaluate((id) => window.__xrayViews.shareUrl(id), expected[shareIdx].id);
  check(`${model}: share link is short`, url.length < 1500, `${url.length} characters`);
  const ctx2 = await browser.newContext({ viewport: { width: 1600, height: 900 } });
  const p2 = await ctx2.newPage();
  watch(p2, `${model} share`);
  await p2.goto(url);
  await ready(p2);
  const ms2 = await waitCamera(p2, expected[shareIdx].want.camera);
  compare(`${model}: share link "${expected[shareIdx].name}" (${ms2} ms)`, await snapshot(p2), expected[shareIdx].want);
  check(`${model}: share link applied, not saved, hash removed`, await p2.evaluate(() => window.__xrayViews.list().length === 0 && !location.hash.includes('view=')));
  await ctx2.close();

  let packInfo = null;
  if (model === 'fzk-haus') {
    // Phone layout.
    await page.setViewportSize({ width: 390, height: 844 });
    await page.waitForTimeout(600);
    await page.evaluate(() => {
      // A phone starts with the parameter dock collapsed; this page was resized from a desktop width.
      if (!document.body.classList.contains('dk-collapsed')) document.querySelector('.dk-toggle')?.click();
      if (document.body.classList.contains('sb-collapsed')) document.querySelector('.sb-toggle').click();
      [...document.querySelectorAll('.sb-tab')].find((t) => t.textContent === 'Views').click();
    });
    await page.waitForTimeout(500);
    const phone = await page.evaluate(() => {
      const sb = document.getElementById('sidebar').getBoundingClientRect();
      const over = [...document.querySelectorAll('.vw-top button, .vw-top select, .vw-row')].filter((e) => e.getBoundingClientRect().right > sb.right + 1).length;
      return { width: sb.width, over, scroll: document.documentElement.scrollWidth <= window.innerWidth };
    });
    check('phone: Views tab fits the sidebar without overflow', phone.over === 0 && phone.scroll, JSON.stringify(phone));
    await shot(page, 'views-phone.png');
    await page.evaluate(() => document.querySelector('.vw-grid-btn').click());
    await page.waitForTimeout(400);
    check('phone: grid shows 3 cards with pictures', await page.evaluate(() => document.querySelectorAll('.vw-card img').length === 3));
    await shot(page, 'views-phone-grid.png');
    await page.evaluate(() => document.querySelector('.vw-grid-btn').click());
    await page.setViewportSize({ width: 1600, height: 900 });

    // Packed page from file:// with --views and --open-view.
    const json = await page.evaluate(() => window.__xrayViews.exportJson());
    const dir = mkdtempSync(join(tmpdir(), 'xray-views-'));
    const vf = join(dir, 'views.json');
    const out = join(dir, 'fzk-views.html');
    writeFileSync(vf, json);
    const r = spawnSync(process.execPath, [resolve(root, 'tools/xray-pack.mjs'), resolve(root, 'public/models/fzk-haus.glb'), '-o', out, '--name', 'fzk-haus', '--views', vf, '--open-view', expected[1].name, '--force'], { cwd: root, encoding: 'utf8' });
    check('pack: xray-pack --views --open-view exits 0', r.status === 0, (r.stdout + r.stderr).trim().split('\n').pop());
    if (r.status === 0) {
      const ctx3 = await browser.newContext({ viewport: { width: 1600, height: 900 } });
      const p3 = await ctx3.newPage();
      watch(p3, 'pack');
      await p3.goto(pathToFileURL(out).href);
      await ready(p3);
      await p3.waitForTimeout(500);
      const info = await p3.evaluate(() => ({ list: window.__xrayViews.list().map((v) => v.name), active: window.__xrayViews.active, proto: location.protocol }));
      check('pack: page from file:// lists the 3 packed views', info.proto === 'file:' && info.list.length === 3, info.list.join(' | '));
      check('pack: --open-view opened at boot', info.active === expected[1].id);
      compare(`pack: open view "${expected[1].name}"`, await snapshot(p3), expected[1].want);
      await shot(p3, 'views-pack.png');
      packInfo = info;
      await ctx3.close();
    }
  }
  await ctx.close();
  return packInfo;
}

let failed = false;
try {
  await waitForServer();
  const browser = await chromium.launch();
  for (const model of (process.env.SMOKE_MODELS ?? 'fzk-haus,synth5k').split(',')) await runScene(browser, model);
  await browser.close();
} catch (e) {
  failed = true;
  console.error(e);
} finally {
  if (vite) vite.kill();
}
check('no console errors', errors.length === 0, errors.slice(0, 5).join(' || '));
const bad = checks.filter((c) => !c.ok);
console.log(`\n${checks.length - bad.length}/${checks.length} checks passed`);
process.exit(failed || bad.length ? 1 : 0);
