// Build the single self-contained viewer: runs `vite build --config vite.single.config.ts`, then inlines the output.
//   node tools/build-single-file.mjs [--all] [--no-ifc] [--keep] [--skip-vite]
// Reads  web/.single-build/  (index.html, one JS chunk, one CSS file)
// Writes web/dist-single/xray-viewer.html  (web/dist-single/xray-viewer-no-ifc.html with --no-ifc)
// Embedded models: building, fzk-haus, plumbing, debris-demo (+ synth5k with --all) as glb with their sidecar, and process-plant as
// gzip-compressed IFC (window.__xrayEmbeddedIfc, read by the built-in IFC reader; not with --no-ifc). The scratch directory is removed unless --keep.
// IFC reader: the web-ifc wasm is embedded as base64 (window.__xrayIfcWasm) and the worker is already inside the JS chunk
// (see src/model/ifcRuntime.single.ts). --no-ifc builds without the reader: no wasm, no worker, no web-ifc code.
// PDF sheets (src/sheets): pdf.js, pdf-lib and the pdf.js worker are embedded as gzip + base64 (window.__xrayPdfLibsGz and
// window.__xrayPdfWorkerGz) and unpacked on first use, like the IFC worker; the libraries are built into one ES module by
// vite.pdflibs.config.ts, not into the app chunk. Every variant has them (templates too).
// --template [--variant ifc|none] builds the templates used by tools/xray-pack.mjs instead: web/dist-single/xray-template-ifc.html
// (with the IFC reader) and xray-template.html (without), no sample models, no footer note, and one clearly marked injection
// block (XRAY-PACK:INJECT-BEGIN ... XRAY-PACK:INJECT-END) that holds window.__xrayEmbeddedModels = {}. Both variants are built
// unless --variant picks one. Templates build in their own scratch directory.
// --skip-vite reuses an existing .single-build (only valid when it was built with the same --no-ifc setting).
import { spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { gzipSync } from 'node:zlib';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const template = process.argv.includes('--template');
const variantArg = (() => { const i = process.argv.indexOf('--variant'); return i > 0 ? process.argv[i + 1] : ''; })();
if (template && !variantArg) {
  // run each variant in a child process: the vite config reads XRAY_NO_IFC once
  for (const v of ['none', 'ifc']) {
    const r = spawnSync(process.execPath, [fileURLToPath(import.meta.url), '--template', '--variant', v], { stdio: 'inherit' });
    if (r.status !== 0) process.exit(r.status ?? 1);
  }
  process.exit(0);
}
if (template && variantArg !== 'ifc' && variantArg !== 'none') { console.error('build-single-file: --variant must be ifc or none'); process.exit(1); }
const buildDir = join(root, template ? `.single-build-template-${variantArg}` : '.single-build');
const modelsDir = join(root, 'public', 'models');
const all = process.argv.includes('--all');
const keep = process.argv.includes('--keep');
const noIfc = template ? variantArg === 'none' : process.argv.includes('--no-ifc');
const skipVite = process.argv.includes('--skip-vite');
const outFile = join(root, 'dist-single', template ? (noIfc ? 'xray-template.html' : 'xray-template-ifc.html') : noIfc ? 'xray-viewer-no-ifc.html' : 'xray-viewer.html');

const MODELS = template ? [] : [
  { name: 'building', src: 'buildingSMART Simple-Scene: Building-Structural + Building-Architecture + Building-Hvac (IFC4)' },
  { name: 'fzk-haus', src: 'KIT FZK-Haus (AC20-FZK-Haus.ifc, from the IfcOpenShell repository)' },
  { name: 'plumbing', src: 'buildingSMART Simple-Scene: Infra-Plumbing (IFC4)' },
  { name: 'debris-demo', src: 'synthetic 400-element building with scattered debris for the cleanup tool (tools/synth_model.py --debris 24)' },
  ...(all ? [{ name: 'synth5k', src: 'synthetic 5,000-element benchmark model (tools/synth_model.py)' }] : []),
];
// IFC samples: the IFC file itself, gzip-compressed and base64-encoded, read by the built-in IFC reader. No glb, no sidecar.
const IFC_MODELS = template || noIfc ? [] : [
  { name: 'process-plant', file: 'Process-Plant.ifc', src: 'Synthetic process unit: civil, structural, architecture, MEPI (generated)' },
];

const fmtMB = (n) => (n / 1048576).toFixed(2) + ' MB';
const die = (m) => { console.error('build-single-file: ' + m); process.exit(1); };

if (!skipVite) {
  const viteBin = join(root, 'node_modules', 'vite', 'bin', 'vite.js');
  const r = spawnSync(process.execPath, [viteBin, 'build', '--config', 'vite.single.config.ts'], {
    cwd: root, stdio: 'inherit', env: { ...process.env, XRAY_NO_IFC: noIfc ? '1' : '', XRAY_SINGLE_OUT: template ? buildDir : '' },
  });
  if (r.status !== 0) die('vite build failed');
}

if (!existsSync(join(buildDir, 'index.html'))) die(`${buildDir}/index.html missing; run "vite build --config vite.single.config.ts" first (npm run bundle does)`);

let html = readFileSync(join(buildDir, 'index.html'), 'utf8');

/** Make text safe inside an inline <script>: no closing tag or comment opener can end the element early. */
const scriptSafe = (s) => s.replace(/<\/(script)/gi, '<\\/$1').replace(/<!--/g, '<\\!--');

// ---- JS: inline every emitted module script; refuse relative imports left behind.
const assetsDir = join(buildDir, 'assets');
const allJs = existsSync(assetsDir) ? readdirSync(assetsDir).filter((f) => f.endsWith('.js')) : [];
// the IFC worker is emitted next to the app chunk (ifcRuntime.single.ts imports its URL); it is embedded separately below
const workerFiles = allJs.filter((f) => /^ifcWorker/.test(f));
const jsFiles = allJs.filter((f) => !workerFiles.includes(f));
if (noIfc ? workerFiles.length !== 0 : workerFiles.length !== 1) die(`expected ${noIfc ? 'no' : 'one'} IFC worker file, found ${workerFiles.length} (${workerFiles.join(', ')})`);
let inlinedJs = 0;
let jsBytes = 0;
html = html.replace(/<script\b[^>]*\btype="module"[^>]*\bsrc="([^"]+)"[^>]*><\/script>\s*/g, (_m, src) => {
  const file = join(buildDir, src);
  if (!existsSync(file)) die(`script ${src} not found in build output`);
  const js = readFileSync(file, 'utf8');
  if (/(^|[;}\s])(import|export)\s*(\{[^}]*\}\s*from\s*|\*\s*as\s+\w+\s+from\s*)["']\.{0,2}\//.test(js) || /\bimport\(\s*["']\.\.?\//.test(js)) {
    die(`${src} still imports a relative chunk (dynamic imports not inlined)`);
  }
  inlinedJs++;
  jsBytes += js.length;
  return `\u0000APP_SCRIPT_${inlinedJs - 1}\u0000`; // placeholder; replaced after the embed script is built
});
if (inlinedJs !== 1 || jsFiles.length !== 1) die(`expected exactly one JS chunk, found ${jsFiles.length} files / ${inlinedJs} script tags`);
const appJs = readFileSync(join(buildDir, 'assets', jsFiles[0]), 'utf8');

// ---- CSS: inline stylesheets.
html = html.replace(/<link\b[^>]*\brel="stylesheet"[^>]*\bhref="([^"]+)"[^>]*>\s*/g, (_m, href) => {
  const file = join(buildDir, href);
  if (!existsSync(file)) die(`stylesheet ${href} not found`);
  return `<style>\n${readFileSync(file, 'utf8').replace(/<\/style/gi, '<\\/style')}\n</style>\n`;
});

// ---- Strip modulepreload links and crossorigin attributes.
html = html.replace(/<link\b[^>]*\brel="modulepreload"[^>]*>\s*/g, '');
html = html.replace(/\s+crossorigin(="[^"]*")?/g, '');

// ---- Title.
html = html.replace(/<title>[^<]*<\/title>/, `<title>${template ? 'BIM X-ray viewer' : `BIM X-ray viewer (single file${noIfc ? ', no IFC reader' : ''})`}</title>`);

// ---- Embedded data.
const embedded = {};
const sizes = [];
for (const m of MODELS) {
  const glbPath = join(modelsDir, `${m.name}.glb`);
  const jsonPath = join(modelsDir, `${m.name}.json`);
  if (!existsSync(glbPath) || !existsSync(jsonPath)) die(`model ${m.name} missing in ${modelsDir}`);
  const glb = readFileSync(glbPath);
  embedded[m.name] = { glb: glb.toString('base64'), json: JSON.parse(readFileSync(jsonPath, 'utf8')) };
  sizes.push(`${m.name}: glb ${fmtMB(glb.length)}, json ${fmtMB(statSync(jsonPath).size)}`);
}
// The IFC samples: models/<file> (the source IFC, not the converted glb), gzip level 9, base64. The page inflates them.
const embeddedIfc = {};
let ifcSourceBytes = 0;
let ifcGzipBytes = 0;
for (const m of IFC_MODELS) {
  const ifcPath = join(root, '..', 'models', m.file);
  if (!existsSync(ifcPath)) die(`${m.file} missing (expected in models/ at the repository root)`);
  const raw = readFileSync(ifcPath);
  const gz = gzipSync(raw, { level: 9 });
  embeddedIfc[m.name] = { file: m.file, gz: gz.toString('base64') };
  ifcSourceBytes += raw.length;
  ifcGzipBytes += gz.length;
  sizes.push(`${m.name}: ifc ${fmtMB(raw.length)} -> gzip ${fmtMB(gz.length)} (base64 ${fmtMB(gz.toString('base64').length)})`);
}
const configPath = join(root, 'public', 'xray.config.json');
const config = existsSync(configPath) ? JSON.parse(readFileSync(configPath, 'utf8')) : null;
// Presets override (public/xray.presets.json, schema xray-presets/1): entries with a built-in id replace it, new ids are added.
// Embedded in every variant (also the templates) as window.__xrayEmbeddedPresets, so the page never has to fetch it.
const presetsPath = join(root, 'public', 'xray.presets.json');
const presetsDoc = existsSync(presetsPath) ? JSON.parse(readFileSync(presetsPath, 'utf8')) : null;
// web-ifc.wasm (browser build, single thread), gzipped and base64-encoded; at run time the page inflates it with
// DecompressionStream, and the inlined worker serves the bytes to web-ifc through a Blob URL. Left out with --no-ifc.
let wasmBytes = 0;
let wasmEmbedded = 0;
let workerBytes = 0;
let workerEmbedded = 0;
let wasmScript = '';
if (!noIfc) {
  const workerJs = readFileSync(join(assetsDir, workerFiles[0]));
  if (/(^|[;}\s])import\s*[{*"']/.test(workerJs.toString('utf8').slice(0, 2000))) die('the IFC worker is an ES module with imports; expected one self-contained script');
  workerBytes = workerJs.length;
  const workerB64 = gzipSync(workerJs, { level: 9 }).toString('base64');
  workerEmbedded = workerB64.length;
  const wasmPath = join(root, 'node_modules', 'web-ifc', 'web-ifc.wasm');
  if (!existsSync(wasmPath)) die(`${wasmPath} missing (npm install)`);
  const wasm = readFileSync(wasmPath);
  wasmBytes = wasm.length;
  const b64 = gzipSync(wasm, { level: 9 }).toString('base64');
  wasmEmbedded = b64.length;
  // web-ifc is MPL-2.0 (file-level copyleft): it is included unmodified; this is the notice and the source location.
  wasmScript =
    '<!-- web-ifc 0.0.78 (https://github.com/ThatOpen/engine_web-ifc), Mozilla Public License 2.0, included unmodified: its JavaScript\n' +
    '     is part of the IFC worker script and web-ifc.wasm is the wasm below (both gzip + base64). Source and licence: https://www.mozilla.org/MPL/2.0/ -->\n' +
    `<script>\nwindow.__xrayIfcWorkerGz = "${workerB64}";\nwindow.__xrayIfcWasm = "${b64}";\nwindow.__xrayIfcWasmEnc = "gzip";\n</script>\n`;
}
// The PDF libraries (sheets): one ES module with pdf.js and pdf-lib, and the pdf.js worker; both gzipped + base64 into the HTML.
const pdfOut = join(root, template ? `.single-build-pdf-${variantArg}` : '.single-build-pdf');
{
  const viteBin = join(root, 'node_modules', 'vite', 'bin', 'vite.js');
  const r = spawnSync(process.execPath, [viteBin, 'build', '--config', 'vite.pdflibs.config.ts'], { cwd: root, stdio: 'inherit', env: { ...process.env, XRAY_PDFLIBS_OUT: pdfOut } });
  if (r.status !== 0) die('the PDF libraries build failed');
}
const pdfLibsJs = readFileSync(join(pdfOut, 'pdf-libs.mjs'));
// The pdf.js worker is an ES module file; a module worker cannot start from a Blob URL on a file:// page, a classic one can (as the IFC
// worker does). So the file is turned into a classic script: the one `import.meta.url` (a wasm glue path that is never used here) becomes
// the worker's own address and the closing `export` goes. The script starts itself when it runs as a worker.
const pdfWorkerSrc = readFileSync(join(root, 'node_modules', 'pdfjs-dist', 'build', 'pdf.worker.min.mjs'), 'utf8')
  .replace(/import\.meta\.url/g, 'self.location.href')
  .replace(/export\s*\{\s*WorkerMessageHandler\s*\};?\s*$/, '');
if (/\bimport\.meta\b/.test(pdfWorkerSrc) || /(^|[;}\s])export\s*[{*d]/.test(pdfWorkerSrc.slice(-300))) die('the pdf.js worker could not be turned into a classic script (its format changed)');
const pdfWorkerJs = Buffer.from(pdfWorkerSrc, 'utf8');
if (/\bimport\s*\(\s*["']\.\.?\//.test(pdfLibsJs.toString('utf8'))) die('the PDF libraries bundle still imports a relative chunk');
const pdfLibsB64 = gzipSync(pdfLibsJs, { level: 9 }).toString('base64');
const pdfWorkerB64 = gzipSync(pdfWorkerJs, { level: 9 }).toString('base64');
rmSync(pdfOut, { recursive: true, force: true });
const pdfScript =
  '<!-- pdf.js (https://github.com/mozilla/pdf.js, Apache License 2.0) and pdf-lib (https://github.com/Hopding/pdf-lib, MIT) are included unmodified,\n' +
  '     bundled into one ES module, and the pdf.js worker; both gzip + base64, unpacked when the first PDF is opened. -->\n' +
  `<script>\nwindow.__xrayPdfLibsGz = "${pdfLibsB64}";\nwindow.__xrayPdfWorkerGz = "${pdfWorkerB64}";\n</script>\n`;
// Model credits and a note about the build: the status bar shows them (model segment tooltip and its "About models"
// popover, src/ui/statusBar.ts) instead of a banner over the canvas.
const credits = Object.fromEntries([...MODELS, ...IFC_MODELS].map((m) => [m.name, m.src]));
const buildNote = 'Self-contained file: no server or network needed.' +
  (noIfc ? ' Built without the IFC reader: only glb files can be opened.' : ' Open your own .ifc or .glb files from the panel (Open model) or drop them on the viewer.');
const creditScript = scriptSafe((Object.keys(credits).length ? `window.__xrayModelCredits = ${JSON.stringify(credits)};\n` : '') + `window.__xrayBuildNote = ${JSON.stringify(buildNote)};`) + '\n';
const embedScript = template
  // tools/xray-pack.mjs replaces everything between the two marker comments (models and window.__xrayBoot) and the <title>
  ? '<script>\n/* XRAY-PACK:INJECT-BEGIN */\nwindow.__xrayEmbeddedModels = {};\n/* XRAY-PACK:INJECT-END */\n</script>\n<script>\n' +
    scriptSafe(`window.__xrayEmbeddedConfig = ${JSON.stringify(config)};\nwindow.__xrayEmbeddedPresets = ${JSON.stringify(presetsDoc)};`) + '\n' + creditScript + '</script>\n' + wasmScript + pdfScript
  : '<script>\n' +
    scriptSafe(`window.__xrayEmbeddedModels = ${JSON.stringify(embedded)};\nwindow.__xrayEmbeddedIfc = ${JSON.stringify(embeddedIfc)};\nwindow.__xrayEmbeddedConfig = ${JSON.stringify(config)};\nwindow.__xrayEmbeddedPresets = ${JSON.stringify(presetsDoc)};`) +
    '\n' + creditScript + '</script>\n' + wasmScript + pdfScript;

// ---- Assemble: embed data first, then the app module.
const moduleScript = `<script type="module">\n${scriptSafe(appJs)}\n</script>\n`;
html = html.replace(/\u0000APP_SCRIPT_0\u0000/, () => embedScript + moduleScript);

if (/\bsrc="\.?\.?\/(assets|src)\//.test(html) || /<link[^>]+href="\.?\.?\/assets/.test(html)) die('a relative asset reference remains in the output');

mkdirSync(dirname(outFile), { recursive: true });
writeFileSync(outFile, html);
if (!keep) rmSync(buildDir, { recursive: true, force: true });

const size = statSync(outFile).size;
console.log(`wrote ${outFile}`);
if (template) console.log('  template: injection block XRAY-PACK:INJECT-BEGIN/END, no sample models');
console.log(`  app JS ${fmtMB(jsBytes)} (1 chunk${noIfc ? ', no IFC reader' : ''}), embedded: ${sizes.join('; ')}`);
console.log(`  PDF sheets: libraries ${fmtMB(pdfLibsJs.length)} -> ${fmtMB(pdfLibsB64.length)} and worker ${fmtMB(pdfWorkerJs.length)} -> ${fmtMB(pdfWorkerB64.length)} embedded as gzip + base64`);
console.log(noIfc ? '  IFC reader: not included (--no-ifc)' : `  IFC reader: worker script ${fmtMB(workerBytes)} -> ${fmtMB(workerEmbedded)} and web-ifc.wasm ${fmtMB(wasmBytes)} -> ${fmtMB(wasmEmbedded)} embedded as gzip + base64`);
console.log(`  total ${size} bytes (${fmtMB(size)})${all ? ' [--all]' : ''}${noIfc ? ' [--no-ifc]' : ''}`);
