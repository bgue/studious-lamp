#!/usr/bin/env node
// xray-pack: wrap a model in a self-contained X-ray viewer. See docs-features/xray-pack.md and `xray-pack --help`.
//   node tools/xray-pack.mjs <inputs...> -o out.html [options]
import { spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, readdirSync, statSync, writeFileSync } from 'node:fs';
import { basename, dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  EXIT_INPUT, EXIT_USAGE, HELP, PackError, buildBoot, checkViews, defaultModelName, injectTemplate, parseSelect, toBase64, unknownTools,
} from './pack/lib.mjs';
import { convertIfcFiles, newestMtime } from './pack/convert.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const webRoot = resolve(here, '..');
const distDir = join(webRoot, 'dist-single');
const SAMPLES = ['building', 'fzk-haus', 'plumbing'];

const fmtMB = (n) => (n / 1048576).toFixed(2) + ' MB';
const fmtMs = (n) => (n >= 1000 ? (n / 1000).toFixed(2) + ' s' : Math.round(n) + ' ms');

function readInput(path) {
  if (!existsSync(path) || !statSync(path).isFile()) throw new PackError(`cannot read input "${path}"`, EXIT_INPUT);
  return readFileSync(path);
}

/** Rebuild a template (via build-single-file.mjs --template) when it is missing or older than web/src and the build scripts. */
function ensureTemplate(withIfc, log) {
  // testing hook: a ready-made template file, used as is (tests/pack-integration.test.ts)
  if (process.env.XRAY_PACK_TEMPLATE) return resolve(process.env.XRAY_PACK_TEMPLATE);
  const file = join(distDir, withIfc ? 'xray-template-ifc.html' : 'xray-template.html');
  const sources = [join(webRoot, 'src'), join(here, 'build-single-file.mjs'), join(webRoot, 'vite.single.config.ts'), join(webRoot, 'public', 'xray.config.json')];
  const stale = !existsSync(file) || sources.some((p) => newestMtime(p) > statSync(file).mtimeMs);
  if (stale) {
    log(`building template ${basename(file)} ...`);
    const t0 = performance.now();
    const r = spawnSync(process.execPath, [join(here, 'build-single-file.mjs'), '--template', '--variant', withIfc ? 'ifc' : 'none'], {
      cwd: webRoot, encoding: 'utf8',
    });
    if (r.status !== 0 || !existsSync(file)) {
      throw new PackError(`template build failed: ${(r.stderr || r.stdout || '').trim().split('\n').pop()}`, EXIT_INPUT);
    }
    log(`  template built in ${fmtMs(performance.now() - t0)}`);
  }
  return file;
}

function loadParams(path) {
  const text = readInput(path).toString('utf8');
  let doc;
  try {
    doc = JSON.parse(text);
  } catch (e) {
    throw new PackError(`--params ${path} is not valid JSON (${e.message})`, EXIT_INPUT);
  }
  if (!doc || typeof doc !== 'object' || Array.isArray(doc)) throw new PackError(`--params ${path} must be a JSON object`, EXIT_INPUT);
  if (doc.schema !== undefined && doc.schema !== 'xray-params/1') throw new PackError(`--params ${path}: unsupported schema "${doc.schema}" (expected xray-params/1)`, EXIT_INPUT);
  return doc;
}

function loadJson(path, flag) {
  const text = readInput(path).toString('utf8');
  try {
    return JSON.parse(text);
  } catch (e) {
    throw new PackError(`${flag} ${path} is not valid JSON (${e.message})`, EXIT_INPUT);
  }
}

export async function run(argv, io = { out: (s) => process.stdout.write(s + '\n'), err: (s) => process.stderr.write(s + '\n') }) {
  const { help, inputs, options } = (await import('./pack/lib.mjs')).parseArgs(argv);
  if (help) {
    io.out(HELP.trimEnd());
    return 0;
  }
  const log = options.quiet ? () => {} : io.out;
  const warn = (m) => { if (!options.quiet) io.err(`xray-pack: warning: ${m}`); };
  const t0 = performance.now();

  const out = resolve(options.out);
  if (existsSync(out) && !options.force) throw new PackError(`${options.out} exists (use --force to overwrite)`, EXIT_USAGE);
  const params = options.params ? loadParams(options.params) : undefined;
  const viewsDoc = options.views ? loadJson(options.views, '--views') : undefined;

  // ---- model
  const name = options.name ?? defaultModelName(inputs[0]);
  let glb;
  let sidecar;
  let convertNote = '';
  const isGlb = /\.glb$/i.test(inputs[0]);
  if (isGlb) {
    glb = readInput(inputs[0]);
    if (glb.length < 12 || glb.readUInt32LE(0) !== 0x46546c67) throw new PackError(`${inputs[0]} is not a valid glb file`, EXIT_INPUT);
    const jsonPath = inputs[0].replace(/\.glb$/i, '.json');
    if (existsSync(jsonPath)) {
      try {
        sidecar = JSON.parse(readFileSync(jsonPath, 'utf8'));
      } catch (e) {
        throw new PackError(`sidecar ${jsonPath} is not valid JSON (${e.message})`, EXIT_INPUT);
      }
    } else warn(`no ${basename(jsonPath)} next to the glb: element classes are guessed from node names`);
  } else {
    const files = inputs.map((p) => ({ name: basename(p), bytes: new Uint8Array(readInput(p)) }));
    let res;
    try {
      res = await convertIfcFiles(files);
    } catch (e) {
      throw new PackError(`cannot convert ${inputs.map((p) => basename(p)).join(', ')}: ${String(e.message ?? e).split('\n')[0]}`, EXIT_INPUT);
    }
    glb = Buffer.from(res.glb.buffer, res.glb.byteOffset, res.glb.byteLength);
    sidecar = res.sidecar;
    convertNote = `converted ${inputs.length} IFC file${inputs.length > 1 ? 's' : ''} in ${fmtMs(performance.now() - t0)} (read ${fmtMs(res.extractMs)}, build ${fmtMs(res.buildMs)})`;
    if (res.report.duplicatesSkipped || res.report.renamed) convertNote += `; federation: ${res.report.duplicatesSkipped} duplicates skipped, ${res.report.renamed} GlobalIds renamed`;
  }
  const elements = Array.isArray(sidecar?.elements) ? sidecar.elements : null;
  if (convertNote) log(convertNote);

  // ---- select check against the sidecar (the viewer re-checks at run time)
  if (options.select && elements) {
    const sel = parseSelect(options.select.join(','));
    const gids = new Set(elements.map((e) => e.globalId));
    const classes = new Set(elements.map((e) => String(e.ifcClass).toLowerCase()));
    const missing = [...sel.gids.filter((g) => !gids.has(g)), ...sel.classes.filter((c) => !classes.has(c.toLowerCase())).map((c) => `class:${c}`)];
    if (missing.length) warn(`--select entries not found in the model: ${missing.slice(0, 8).join(', ')}${missing.length > 8 ? ', ...' : ''}`);
  }
  let views;
  if (viewsDoc !== undefined) {
    const checked = checkViews(viewsDoc, options.openView, name);
    views = checked.views;
    for (const m of checked.warnings) warn(`--views: ${m}`);
    if (elements) {
      const gids = new Set(elements.map((e) => e.globalId));
      const refs = new Set();
      for (const v of views) for (const g of [...(v.selection ?? []), ...(v.pins ?? []), ...(v.hides?.ids ?? [])]) refs.add(g);
      const missing = [...refs].filter((g) => !gids.has(g));
      if (missing.length) warn(`--views: ${missing.length} GlobalId${missing.length > 1 ? 's' : ''} of the views not in the model (${missing.slice(0, 4).join(', ')}${missing.length > 4 ? ', ...' : ''})`);
    }
  }
  const odd = unknownTools(options.tools);
  if (odd.length) warn(`--tools: unknown tool id${odd.length > 1 ? 's' : ''} ${odd.join(', ')} (known: see src/tools/registry.ts)`);

  // ---- assemble
  const models = { [name]: { glb: toBase64(glb), json: sidecar } };
  if (options.samples) {
    const dir = join(webRoot, 'public', 'models');
    for (const s of SAMPLES) {
      if (s === name) { warn(`sample "${s}" skipped: same name as your model (use --name)`); continue; }
      models[s] = { glb: toBase64(readInput(join(dir, `${s}.glb`))), json: JSON.parse(readInput(join(dir, `${s}.json`)).toString('utf8')) };
    }
  }
  const template = ensureTemplate(options.ifcReader, log);
  const html = injectTemplate(readFileSync(template, 'utf8'), {
    models,
    boot: buildBoot(name, options, params, views),
    title: options.title ?? name,
  });
  mkdirSync(dirname(out), { recursive: true });
  writeFileSync(out, html);
  const dt = performance.now() - t0;
  log(`wrote ${options.out}: ${fmtMB(Buffer.byteLength(html))}, model "${name}"${elements ? `, ${elements.length} elements` : ''}${views ? `, ${views.length} saved view${views.length > 1 ? 's' : ''}` : ''}${options.ifcReader ? ', with IFC reader' : ''}, ${fmtMs(dt)}`);
  return 0;
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  run(process.argv.slice(2)).then(
    (code) => process.exit(code),
    (e) => {
      if (e instanceof PackError) {
        console.error(`xray-pack: ${e.message}`);
        process.exit(e.code);
      }
      console.error(`xray-pack: unexpected error: ${e instanceof Error ? e.stack : e}`);
      process.exit(2);
    },
  );
}
