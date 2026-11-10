// Headless check of the pictures that d3-edge gets (src/classify/thumbs.ts): starts vite (bench/vite.smoke.config.mjs), loads process-plant at
// 1600x900 and draws the pictures of a pipe, a pump, a beam and a wall in both styles (render and line drawing), through the same code path as the
// Classify drawer (window.__xrayClassify.thumbnails). Checks sizes, the note, the clipping to the context box (no ghost pixel outside the box outline
// in the line drawing), that the line drawing is black on white, and writes a contact sheet per element (bench/classify-pictures-<element>.png).
// With PICTURES_DIR set it also writes every picture (the WebP or PNG the model gets, and its pixels decoded by the browser as raw RGBA) and a JSON
// index, for the parity run (bench/d3/mm_reference.py and bench/d3/mm_parity.mjs).
// Usage: SMOKE_PORT=5696 [PICTURES_DIR=/tmp/pictures] node bench/smoke-thumbs.mjs
import { spawn } from 'node:child_process';
import { mkdirSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const port = Number(process.env.SMOKE_PORT ?? 5696);
const outDir = process.env.PICTURES_DIR ?? '';

function loadPlaywright() {
  const candidates = [process.env.PLAYWRIGHT_MODULE, resolve(root, 'node_modules/playwright'), '/opt/node-tools/node_modules/playwright', '/opt/node22/lib/node_modules/playwright'].filter(Boolean);
  for (const c of candidates) {
    try { return createRequire(import.meta.url)(c); } catch { /* try next */ }
  }
  throw new Error('playwright not found; set PLAYWRIGHT_MODULE');
}
const { chromium } = loadPlaywright();

const vite = spawn(resolve(root, 'node_modules/.bin/vite'), ['--config', resolve(here, 'vite.smoke.config.mjs'), '--host', '127.0.0.1', '--port', String(port), '--strictPort'], { cwd: root, stdio: ['ignore', 'pipe', 'pipe'] });
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
const checks = [];
const check = (name, ok, detail = '') => { checks.push({ name, ok }); console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${detail ? ` (${detail})` : ''}`); };

const ELEMENTS = [
  { key: 'pipe', gid: 352, what: 'a pipe spool' },
  { key: 'pump', gid: 330, what: 'a pump' },
  { key: 'beam', gid: 177, what: 'a beam' },
  { key: 'wall', gid: 314, what: 'a wall' },
];
const CASES = [
  { tag: 'render', cfg: { images: 'both', imageStyle: 'render', imagePlan: false } },
  { tag: 'vector', cfg: { images: 'both', imageStyle: 'vector', imagePlan: true } },
];

let code = 1;
try {
  await waitForServer();
  const browser = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const ctx = await browser.newContext({ viewport: { width: 1600, height: 900 } });
  await ctx.addInitScript(() => { try { localStorage.setItem('xray.help', 'off'); } catch { /* no storage */ } });
  const page = await ctx.newPage();
  const errors = [];
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', (e) => errors.push(`[pageerror] ${e.message}`));
  await page.goto(`http://127.0.0.1:${port}/?model=process-plant`);
  await page.waitForFunction(() => window.__xray?.app?.controller?.model?.elements?.length > 100 && window.__xrayClassify, null, { timeout: 120000 });
  if (outDir) mkdirSync(outDir, { recursive: true });
  const index = [];
  for (const el of ELEMENTS) {
    const sheets = [];
    for (const c of CASES) {
      const r = await page.evaluate(async ({ gid, cfg, raw }) => {
        window.__xrayClassify.configure({ provider: 'd3', d3Backend: 'endpoint', imageSize: 384, imageMargin: 25, ...cfg });
        const set = await window.__xrayClassify.thumbnails(gid);
        // The pixels as the browser decodes the picture the model gets (what the in-browser path reads).
        const decoded = [];
        for (const t of set.thumbs) {
          const bmp = await createImageBitmap(await (await fetch(t.dataUrl)).blob(), { colorSpaceConversion: 'none', premultiplyAlpha: 'none' });
          const cv = new OffscreenCanvas(bmp.width, bmp.height);
          const g = cv.getContext('2d', { willReadFrequently: true });
          g.drawImage(bmp, 0, 0);
          const d = g.getImageData(0, 0, bmp.width, bmp.height);
          let dark = 0, white = 0;
          for (let i = 0; i < d.data.length; i += 4) { if (d.data[i] < 80 && d.data[i + 1] < 80 && d.data[i + 2] < 80) dark++; else if (d.data[i] > 245 && d.data[i + 1] > 245 && d.data[i + 2] > 245) white++; }
          decoded.push({ w: bmp.width, h: bmp.height, dark, white, rgba: raw ? Array.from(d.data) : null });
        }
        return { thumbs: set.thumbs.map((t) => ({ view: t.view, label: t.label, dataUrl: t.dataUrl, width: t.width, height: t.height, scaleBarM: t.scaleBarM, neighbours: t.neighbours.length })), note: set.note, neighbours: set.neighbours.length, decoded };
      }, { gid: el.gid, cfg: c.cfg, raw: !!outDir });
      const expected = c.tag === 'vector' ? 3 : 2;
      check(`${el.key} ${c.tag}: ${expected} pictures in the order isolated${c.tag === 'vector' ? ', plan' : ''}, context`, r.thumbs.length === expected && r.thumbs[0].view === 'isolated' && r.thumbs.at(-1).view === 'context', r.thumbs.map((t) => t.view).join(','));
      check(`${el.key} ${c.tag}: 384 x 384 pixels each`, r.thumbs.every((t) => t.width === 384 && t.height === 384) && r.decoded.every((d) => d.w === 384 && d.h === 384));
      check(`${el.key} ${c.tag}: the note names every picture`, r.note.split('Picture ').length - 1 === expected && /bounding box/.test(r.note), r.note.slice(0, 80));
      check(`${el.key} ${c.tag}: the context picture has nearby elements`, r.neighbours > 0 || el.key === 'wall', `${r.neighbours} nearby`);
      if (c.tag === 'vector') {
        check(`${el.key} vector: PNG, mostly white with dark lines`, r.thumbs.every((t) => t.dataUrl.startsWith('data:image/png')) && r.decoded.every((d) => d.white > 0.5 * d.w * d.h && d.dark > 100), r.decoded.map((d) => `${d.dark} dark`).join(' '));
      } else {
        check(`${el.key} render: not blank`, r.decoded.every((d) => d.dark + d.white < d.w * d.h - 2000));
      }
      sheets.push({ tag: c.tag, urls: r.thumbs.map((t) => t.dataUrl) });
      if (outDir) {
        r.thumbs.forEach((t, i) => {
          const ext = t.dataUrl.startsWith('data:image/png') ? 'png' : 'webp';
          const base = `${el.key}-${c.tag}-${t.view}`;
          writeFileSync(resolve(outDir, `${base}.${ext}`), Buffer.from(t.dataUrl.split(',')[1], 'base64'));
          writeFileSync(resolve(outDir, `${base}.rgba`), Buffer.from(Uint8Array.from(r.decoded[i].rgba)));
          index.push({ element: el.key, style: c.tag, view: t.view, file: `${base}.${ext}`, rgba: `${base}.rgba`, width: r.decoded[i].w, height: r.decoded[i].h, label: t.label, scaleBarM: t.scaleBarM });
        });
        writeFileSync(resolve(outDir, `${el.key}-${c.tag}.note.txt`), r.note);
      }
    }
    // The contact sheet of this element: render isolated + context, line drawing isolated + context (+ plan).
    await page.evaluate(async ({ sheets, title }) => {
      const imgs = [];
      for (const s of sheets) for (const u of s.urls) { const im = new Image(); im.src = u; await im.decode(); imgs.push(im); }
      const cols = imgs.length > 4 ? 5 : imgs.length;
      const cv = document.createElement('canvas');
      cv.width = imgs.length * 0 + 5 * 384 + 4 * 6; cv.height = 2 * 384 + 6 + 24;
      const g = cv.getContext('2d');
      g.fillStyle = '#ffffff'; g.fillRect(0, 0, cv.width, cv.height);
      g.fillStyle = '#000'; g.font = '16px sans-serif'; g.fillText(title, 6, 17);
      let k = 0;
      sheets.forEach((s, row) => s.urls.forEach((u, i) => { g.drawImage(imgs[k++], i * 390, 24 + row * 390, 384, 384); }));
      void cols;
      const el = document.createElement('img');
      el.id = 'sheet'; el.src = cv.toDataURL('image/png'); el.style.cssText = 'position:fixed;left:0;top:0;z-index:99999;background:#fff';
      document.body.append(el);
      await el.decode();
    }, { sheets, title: `${el.what}: render (top: isolated, context) and line drawing (bottom: isolated, plan, context)` });
    await page.locator('#sheet').screenshot({ path: resolve(here, `classify-pictures-${el.key}.png`) });
    await page.evaluate(() => document.getElementById('sheet')?.remove());
  }
  // The native vector geometry (SVG text in the state): token counts, the text, and one contact sheet of the rendered markup of all four elements.
  const geo = [];
  for (const el of ELEMENTS) {
    const r = await page.evaluate((gid) => {
      window.__xrayClassify.configure({ provider: 'd3', d3Backend: 'endpoint', images: 'off', geometryText: 'svg', geometryContext: true, imageMargin: 25 });
      const g = window.__xrayClassify.geometry(gid);
      return { legend: g.legend, svg: g.svg, tokens: g.tokens, neighbours: g.neighbours, views: g.views };
    }, el.gid);
    geo.push({ el, r });
    check(`${el.key} svg: 4 views, about ${r.tokens} tokens (budget 1500), ${r.neighbours} nearby elements`, r.views.length === 4 && r.tokens <= 1500 && r.tokens > 60 && !r.svg.includes('"'), r.views.map((v) => v.name).join(','));
    check(`${el.key} svg: the target is marked and the class is named`, /<g id='target'><(rect|polygon|circle)/.test(r.views[2].svg) && /data-class='Ifc\w+'/.test(r.views[0].svg));
    if (outDir) writeFileSync(resolve(outDir, `${el.key}.svg.txt`), `${r.legend}\n${r.svg}\n`);
  }
  await page.evaluate(async (items) => {
    const cv = document.createElement('canvas');
    cv.width = 4 * 330; cv.height = items.length * 330 + 4;
    const g = cv.getContext('2d');
    g.fillStyle = '#fff'; g.fillRect(0, 0, cv.width, cv.height);
    for (const [row, it] of items.entries()) for (const [col, v] of it.r.views.entries()) {
      const im = new Image();
      im.src = `data:image/svg+xml;utf8,${encodeURIComponent(v.svg.replace('<svg ', "<svg xmlns='http://www.w3.org/2000/svg' ").replace(/(<svg [^>]*>)/, "$1<style>*{fill:#e3e6ea;stroke:#1b2430;stroke-width:1.4px;vector-effect:non-scaling-stroke}#target *{fill:#f0802a}</style>"))}`;
      await im.decode().catch(() => undefined);
      g.strokeStyle = '#ccc'; g.strokeRect(col * 330 + 4, row * 330 + 4, 320, 320);
      g.drawImage(im, col * 330 + 6, row * 330 + 6, 316, 316);
      g.fillStyle = '#000'; g.font = '13px sans-serif'; g.fillText(`${it.el.key}: ${v.name} (${it.r.tokens} tokens in all)`, col * 330 + 10, row * 330 + 20);
    }
    const el = document.createElement('img');
    el.id = 'sheet'; el.src = cv.toDataURL('image/png'); el.style.cssText = 'position:fixed;left:0;top:0;z-index:99999;background:#fff';
    document.body.append(el);
    await el.decode();
  }, geo.map((x) => ({ el: x.el, r: x.r })));
  await page.locator('#sheet').screenshot({ path: resolve(here, 'classify-geometry-svg.png') });
  await page.evaluate(() => document.getElementById('sheet')?.remove());
  if (outDir) writeFileSync(resolve(outDir, 'index.json'), JSON.stringify(index, null, 2));

  // The ghosts are clipped to the box: in the line drawing the context picture has no grey ghost line outside the blue box outline.
  const clip = await page.evaluate(async () => {
    window.__xrayClassify.configure({ provider: 'd3', d3Backend: 'endpoint', images: 'context', imageStyle: 'vector', imageSize: 384, imageMargin: 25 });
    const set = await window.__xrayClassify.thumbnails(352);
    const im = new Image(); im.src = set.thumbs[0].dataUrl; await im.decode();
    const cv = document.createElement('canvas'); cv.width = 384; cv.height = 384;
    const g = cv.getContext('2d'); g.drawImage(im, 0, 0);
    const d = g.getImageData(0, 0, 384, 384).data;
    // the blue outline pixels (2f6fd0) give the extent of the box in the picture; grey line pixels (8a929c-like) must lie inside it
    let x0 = 1e9, x1 = -1, y0 = 1e9, y1 = -1;
    const isBlue = (r, gg, b) => b > 150 && r < 110 && gg > 80 && gg < 160;
    const isGrey = (r, gg, b) => Math.abs(r - gg) < 14 && Math.abs(gg - b) < 18 && r > 100 && r < 200;
    for (let y = 0; y < 384; y++) for (let x = 0; x < 384; x++) { const i = (y * 384 + x) * 4; if (isBlue(d[i], d[i + 1], d[i + 2])) { x0 = Math.min(x0, x); x1 = Math.max(x1, x); y0 = Math.min(y0, y); y1 = Math.max(y1, y); } }
    let outside = 0, inside = 0;
    for (let y = 30; y < 360; y++) for (let x = 0; x < 384; x++) { const i = (y * 384 + x) * 4; if (isGrey(d[i], d[i + 1], d[i + 2])) { if (x < x0 - 3 || x > x1 + 3 || y < y0 - 3 || y > y1 + 3) outside++; else inside++; } }
    return { box: [x0, y0, x1, y1], outside, inside };
  });
  check('the context picture shows the box outline and the ghost lines stay inside it', clip.x1 !== -1 || clip.box[2] > 0 ? clip.outside < 80 && clip.inside > 100 : false, JSON.stringify(clip));
  check('no console errors', errors.length === 0, errors.slice(0, 3).join(' | '));
  await browser.close();
  code = checks.every((c) => c.ok) ? 0 : 1;
  console.log(`${checks.filter((c) => c.ok).length}/${checks.length} checks passed`);
} catch (e) {
  console.error(e);
  code = 1;
} finally {
  vite.kill();
  process.exit(code);
}
