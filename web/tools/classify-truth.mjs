#!/usr/bin/env node
// Scores the classifiers against a ground truth, from the command line, for any IFC.
//
//   npm run classify:truth -- --ifc <path.ifc> --truth <truth.json> [--arms rules,majority,xsmall,base2,d3,hybrid-d3] [--out dir] [--limit N] [--props common|all]
//
// 1. checks the truth file against the shipped schema (unknown codes: exit 2),
// 2. converts the IFC to its element sidecar with tools/ifc2glb.py (into <out>/sidecar/),
// 3. checks the join (an element without a truth entry: exit 2; a truth entry without an element: a warning),
// 4. runs bench/real-classify-truth.mjs on the sidecar and prints its markdown table (also written to <out>/truth-bench.md).
// Exit codes: 0 done, 2 bad truth file or bad join, 3 the converter or the bench failed, 64 bad usage.
// The d3 and DeBERTa arms need the model files and onnxruntime-node that bench/real-classify-truth.mjs finds (env TRANSFORMERS_NODE, ORT_NODE, D3_DIR);
// the script sets NODE_USE_ENV_PROXY=1 for the downloads. `--arms rules,majority` needs none of them.

import { spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { basename, dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { joinTruth, validateTruth } from './classify-truth-lib.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const webRoot = resolve(here, '..');
const repoRoot = resolve(webRoot, '..');
const DEFAULT_ARMS = 'rules,majority,xsmall,base2,d3,hybrid-d3';

const USAGE = `Usage: npm run classify:truth -- --ifc <path.ifc> --truth <truth.json> [--arms ${DEFAULT_ARMS}] [--out dir] [--limit N] [--props common|all]`;

function parse(argv) {
  const o = { arms: DEFAULT_ARMS, props: 'common' };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '-h' || a === '--help') o.help = true;
    else if (a.startsWith('--')) o[a.slice(2).replace(/-(\w)/g, (_, c) => c.toUpperCase())] = argv[++i];
    else return { error: `unexpected argument ${a}` };
  }
  return o;
}

const fail = (code, msg) => { console.error(msg); process.exit(code); };

const o = parse(process.argv.slice(2));
if (o.help) { console.log(USAGE); process.exit(0); }
if (o.error || !o.ifc || !o.truth) fail(64, `${o.error ? `${o.error}\n` : ''}${USAGE}`);
if (!['common', 'all'].includes(o.props)) fail(64, `--props must be common or all\n${USAGE}`);
for (const f of [o.ifc, o.truth]) if (!existsSync(resolve(f))) fail(64, `no such file: ${f}`);
const ifc = resolve(o.ifc);
const truthPath = resolve(o.truth);
const name = basename(ifc).replace(/\.ifc$/i, '').toLowerCase().replace(/[^a-z0-9]+/g, '-');
const out = resolve(o.out ?? join(tmpdir(), `classify-truth-${name}`));
mkdirSync(join(out, 'sidecar'), { recursive: true });

// 1. the truth file against the schema
const schema = JSON.parse(readFileSync(join(webRoot, 'public/classification/default-schema.json'), 'utf8'));
let doc;
try { doc = JSON.parse(readFileSync(truthPath, 'utf8')); } catch (e) { fail(2, `truth file is not valid JSON: ${e.message}`); }
const v = validateTruth(doc, schema);
if (v.errors.length) {
  console.error(`bad truth file ${o.truth}: ${v.errors.length} problem(s)`);
  for (const e of v.errors.slice(0, 20)) console.error(`  ${e}`);
  process.exit(2);
}
console.error(`truth: ${v.entries} entries, codes valid (schema ${schema.edition})`);

// 2. IFC -> sidecar (the converter has no sidecar-only mode; the glb is a by-product)
const base = join(out, 'sidecar', name);
const conv = spawnSync('python3', [join(repoRoot, 'tools/ifc2glb.py'), ifc, '-o', base, '--props', o.props], { stdio: ['ignore', 'ignore', 'inherit'] });
if (conv.status !== 0) fail(3, `tools/ifc2glb.py failed (exit ${conv.status})`);
const sidecar = `${base}.json`;

// 3. the join
const side = JSON.parse(readFileSync(sidecar, 'utf8'));
const j = joinTruth(doc, side.elements.map((e) => e.globalId));
console.error(`sidecar: ${side.elements.length} elements; ${j.withoutTruth.length} without truth, ${j.withoutElement.length} truth entries without an element`);
if (j.withoutElement.length) console.error(`  warning: truth without element (first 5): ${j.withoutElement.slice(0, 5).join(', ')}`);
if (j.withoutTruth.length) {
  const byId = new Map(side.elements.map((e) => [e.globalId, e]));
  console.error('bad join: elements without a truth entry (first 10):');
  for (const g of j.withoutTruth.slice(0, 10)) console.error(`  ${g}  ${byId.get(g)?.ifcClass} ${byId.get(g)?.name ?? ''}`);
  process.exit(2);
}

// 4. the bench
const benchArgs = [join(webRoot, 'bench/real-classify-truth.mjs'), '--sidecar', sidecar, '--model', name, '--truth', truthPath, '--arms', o.arms, '--out', out];
if (o.limit) benchArgs.push('--limit', String(o.limit));
const r = spawnSync(process.execPath, benchArgs, { stdio: 'inherit', cwd: webRoot, env: { ...process.env, NODE_USE_ENV_PROXY: process.env.NODE_USE_ENV_PROXY ?? '1' } });
process.exit(r.status === 0 ? 0 : 3);
