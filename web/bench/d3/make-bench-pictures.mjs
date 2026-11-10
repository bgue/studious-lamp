// Draws the pictures (isolated and context, render, 384 px) of the representative element of every signature that a FINAL rule labels in the bundled
// models, the same signatures as bench/real-classify-decision.mjs, so that the real bench can run d3-edge with pictures (PICTURES_DIR=...).
// Node picks the elements (the rules and the sidecars or the IFC files, read with web-ifc); a headless browser (Playwright, WebGL by SwiftShader) loads every model
// in the viewer (sidecars with ?model=, IFC files through the open-file input) and draws the pictures through window.__xrayClassify.thumbnails.
// With GEOMETRY_ONLY=1 it draws no picture and writes the SVG geometry text of every element instead (geometry.json: the element alone, and with its bounding box), much faster.
// Usage: SMOKE_PORT=5697 PICTURES_DIR=/tmp/bench-pictures [N=51] [GEOMETRY_ONLY=1] node bench/d3/make-bench-pictures.mjs
import { spawn } from 'node:child_process';
import { existsSync, mkdirSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createServer } from 'vite';
import { IFC_FILES, SIDECARS, loadModels } from '../lib/real-models.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..', '..');
const port = Number(process.env.SMOKE_PORT ?? 5697);
const outDir = process.env.PICTURES_DIR;
if (!outDir) throw new Error('Set PICTURES_DIR.');
mkdirSync(outDir, { recursive: true });

// 1. which elements
const ssr = await createServer({ root, logLevel: 'error', server: { middlewareMode: true, hmr: false, watch: null }, appType: 'custom' });
const picks = [];
try {
  const C = await ssr.ssrLoadModule('/src/classify/index.ts');
  const R = await ssr.ssrLoadModule('/src/classify/calibrateRules.ts');
  const schema = C.defaultSchema();
  const models = await loadModels(ssr);
  const seen = new Map();
  for (const { name, model } of models) for (const t of R.ruleTruths(C.buildInputs(model, model.elements.map((e) => e.id)), schema)) if (!seen.has(t.signature)) seen.set(t.signature, { ...t, model: name });
  for (const t of R.pickTruths([...seen.values()], Number(process.env.N ?? 1000))) picks.push({ model: t.model, gid: t.input.id, signature: t.signature, ifcClass: t.input.ifcClass });
} finally {
  await ssr.close();
}
console.log(`${picks.length} elements in ${new Set(picks.map((p) => p.model)).size} models`);

// 2. draw them
function loadPlaywright() {
  for (const c of [process.env.PLAYWRIGHT_MODULE, resolve(root, 'node_modules/playwright'), '/opt/node-tools/node_modules/playwright', '/opt/node22/lib/node_modules/playwright'].filter(Boolean)) {
    try { return createRequire(import.meta.url)(c); } catch { /* next */ }
  }
  throw new Error('playwright not found; set PLAYWRIGHT_MODULE');
}
const { chromium } = loadPlaywright();
const vite = spawn(resolve(root, 'node_modules/.bin/vite'), ['--config', resolve(root, 'bench/vite.smoke.config.mjs'), '--host', '127.0.0.1', '--port', String(port), '--strictPort'], { cwd: root, stdio: ['ignore', 'pipe', 'pipe'] });
let code = 1;
try {
  for (let i = 0; i < 100; i++) { try { if ((await fetch(`http://127.0.0.1:${port}/`)).ok) break; } catch { /* retry */ } await new Promise((r) => setTimeout(r, 200)); }
  const browser = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const index = {};
  const geometry = {};
  const geoOnly = process.env.GEOMETRY_ONLY === '1';
  for (const model of [...new Set(picks.map((p) => p.model))]) {
    const group = picks.filter((p) => p.model === model);
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 } });
    await ctx.addInitScript(() => { try { localStorage.setItem('xray.help', 'off'); } catch { /* no storage */ } });
    const page = await ctx.newPage();
    const t0 = Date.now();
    if (SIDECARS.includes(model)) {
      await page.goto(`http://127.0.0.1:${port}/?model=${model}`);
    } else {
      await page.goto(`http://127.0.0.1:${port}/`);
      await page.waitForFunction(() => window.__xray?.app?.controller?.model && window.__xrayClassify, null, { timeout: 120000 });
      const file = resolve(root, '..', 'models', `${model}.ifc`);
      if (!existsSync(file)) throw new Error(`${file} is missing`);
      await page.setInputFiles('#xray-open-file-input', [file]);
    }
    await page.waitForFunction((gid) => window.__xray?.app?.controller?.model?.byGlobalId?.has(gid) && window.__xrayClassify, group[0].gid, { timeout: 300000 });
    await page.waitForTimeout(500);
    await page.evaluate(() => window.__xrayClassify.configure({ provider: 'd3', d3Backend: 'endpoint', images: 'both', imageStyle: 'render', imagePlan: false, imageSize: 384, imageMargin: 25 }));
    console.log(`${model}: loaded in ${Date.now() - t0} ms, ${group.length} elements`);
    mkdirSync(resolve(outDir, model), { recursive: true });
    for (const [k, p] of group.entries()) {
      if (geoOnly) {
        const g = await page.evaluate((gid) => {
          const out = {};
          for (const ctx of [false, true]) {
            window.__xrayClassify.configure({ provider: 'd3', d3Backend: 'endpoint', geometryText: 'svg', geometryContext: ctx, imageMargin: 25 });
            const s = window.__xrayClassify.geometry(gid);
            out[ctx ? 'context' : 'isolated'] = { legend: s.legend, svg: s.svg, tokens: s.tokens, neighbours: s.neighbours };
          }
          return out;
        }, p.gid).catch((e) => ({ error: String(e) }));
        if (g.error) console.log(`  ${p.ifcClass} ${p.gid}: ${g.error.slice(0, 120)}`); else geometry[`${model}|${p.gid}`] = g;
        continue;
      }
      const r = await page.evaluate(async (gid) => {
        const set = await window.__xrayClassify.thumbnails(gid);
        const out = [];
        for (const t of set.thumbs) {
          const bmp = await createImageBitmap(await (await fetch(t.dataUrl)).blob(), { colorSpaceConversion: 'none', premultiplyAlpha: 'none' });
          const cv = new OffscreenCanvas(bmp.width, bmp.height);
          const g = cv.getContext('2d', { willReadFrequently: true });
          g.drawImage(bmp, 0, 0);
          out.push({ view: t.view, dataUrl: t.dataUrl, w: bmp.width, h: bmp.height, rgba: Array.from(g.getImageData(0, 0, bmp.width, bmp.height).data) });
        }
        return { pictures: out, note: set.note, neighbours: set.neighbours.length };
      }, p.gid).catch((e) => ({ error: String(e) }));
      if (r.error) { console.log(`  ${p.ifcClass} ${p.gid}: ${r.error.slice(0, 120)}`); continue; }
      const files = r.pictures.map((pic) => {
        const base = `${model}/${k}-${pic.view}`;
        writeFileSync(resolve(outDir, `${base}.rgba`), Buffer.from(Uint8Array.from(pic.rgba)));
        writeFileSync(resolve(outDir, `${base}.${pic.dataUrl.startsWith('data:image/png') ? 'png' : 'webp'}`), Buffer.from(pic.dataUrl.split(',')[1], 'base64'));
        return { view: pic.view, rgba: resolve(outDir, `${base}.rgba`), width: pic.w, height: pic.h };
      });
      index[`${model}|${p.gid}`] = { pictures: files, note: r.note, neighbours: r.neighbours, ifcClass: p.ifcClass };
    }
    await ctx.close();
  }
  if (geoOnly) { writeFileSync(resolve(outDir, 'geometry.json'), JSON.stringify(geometry)); console.log(`wrote ${Object.keys(geometry).length} geometry sets to ${outDir}`); } else {
  writeFileSync(resolve(outDir, 'index.json'), JSON.stringify(index, null, 2));
  console.log(`wrote ${Object.keys(index).length} picture sets to ${outDir}`); }
  await browser.close();
  code = 0;
} catch (e) {
  console.error(e);
} finally {
  vite.kill();
  process.exit(code);
}
