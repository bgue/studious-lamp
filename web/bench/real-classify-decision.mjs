// Real check of the local decision providers in Node: a REAL model, the distinct signatures that a FINAL rule labels in every bundled
// model (the sidecars of public/models and the IFC files of ../models, read with web-ifc), the rules' answers as proxy truth.
// It reports agreement (discipline, sub-discipline, MasterFormat division), the passes and the time per element, then the logit scaling:
// one temperature per question fitted with 5-fold cross-validation (every number is out-of-fold), before and after, with the ECE and the
// share of answers that clear the minimum confidence and their accuracy. Writes everything to OUT (JSON) when set.
//
// PROVIDER=decision (default)  the DeBERTa NLI models with transformers.js. Needs a Node install OUTSIDE the project:
//     mkdir /tmp/tjs && cd /tmp/tjs && npm i @huggingface/transformers@4.3.2
//     TRANSFORMERS_NODE=/tmp/tjs/node_modules/@huggingface/transformers/dist/transformers.node.mjs \
//     HF_MODEL=MoritzLaurer/deberta-v3-xsmall-zeroshot-v1.1-all-33 DTYPE=q8 DEVICE=cpu node bench/real-classify-decision.mjs
// PROVIDER=d3                  d3-edge in Node (onnxruntime-node, CPU) from a local copy of warsang/d3-edge-web:
//     ORT_NODE=/tmp/ortnode/node_modules/onnxruntime-node/dist/index.js TRANSFORMERS_NODE=... D3_DIR=/tmp/d3web PROVIDER=d3 node bench/real-classify-decision.mjs
// PROVIDER=d3 with D3_MM=1     our own multimodal export (tools/export_d3_web.py) in D3_DIR, read as a plain base URL; with PICTURES_DIR (bench/d3/make-bench-pictures.mjs)
//     and PICTURES=both|isolated|context the pictures of every representative element go with both requests of its signature, as the viewer sends them
//     (the state starts with the note about the pictures). Without PICTURES_DIR the same export runs text only.
// Other knobs: N (cap of elements, default all), MIN_CONF (0.6), FOLDS (5), OUT (json file), HYP_DISCIPLINE / HYP_SUB / HYP_MF.
import { readFile, writeFile } from 'node:fs/promises';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createServer } from 'vite';
import { loadModels } from './lib/real-models.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const PROVIDER = process.env.PROVIDER ?? 'decision';
const MIN = Number(process.env.MIN_CONF ?? 0.6);
const FOLDS = Number(process.env.FOLDS ?? 5);
const N = Number(process.env.N ?? 1000);
const need = (k) => process.env[k] ?? (() => { throw new Error(`Set ${k}.`); })();

const server = await createServer({ root, logLevel: 'error', server: { middlewareMode: true, hmr: false, watch: null }, appType: 'custom' });
try {
  const C = await server.ssrLoadModule('/src/classify/index.ts');
  const K = await server.ssrLoadModule('/src/classify/calibrate.ts');
  const R = await server.ssrLoadModule('/src/classify/calibrateRules.ts');
  const P = await server.ssrLoadModule('/src/classify/pipeline.ts');
  const schema = C.defaultSchema();

  // All the distinct signatures (across models: a model that is also a sidecar counts once) with a final rule.
  const models = await loadModels(server);
  const seen = new Map();
  for (const { name, model } of models) {
    for (const t of R.ruleTruths(C.buildInputs(model, model.elements.map((e) => e.id)), schema)) if (!seen.has(t.signature)) seen.set(t.signature, { ...t, model: name });
  }
  const truths = R.pickTruths([...seen.values()], N);
  const byModel = {};
  for (const t of truths) byModel[t.model] = (byModel[t.model] ?? 0) + 1;
  console.log(`${truths.length} distinct signatures with a final rule (${Object.entries(byModel).map(([k, v]) => `${k} ${v}`).join(', ')})`);

  let provider, modelId, label, stats;
  if (PROVIDER === 'd3') {
    const D3 = await server.ssrLoadModule('/src/classify/providers/d3.ts');
    const ort = await import(pathToFileURL(need('ORT_NODE')).href);
    const tjs = await import(pathToFileURL(need('TRANSFORMERS_NODE')).href);
    const DIR = need('D3_DIR');
    const source = { has: async () => true, read: async (f) => new Uint8Array(await readFile(join(DIR, f))) };
    const MM = process.env.D3_MM === '1';
    const fetchImpl = async (url) => {
      const f = MM ? String(url).split('/d3/')[1]?.split('?')[0] : String(url).split('/resolve/')[1]?.split('/').slice(1).join('/');
      try { return new Response(await readFile(join(DIR, f)), { status: 200 }); } catch { return new Response('', { status: 404 }); }
    };
    // The pictures arrive as "rgba:<file>:<width>:<height>": the Node bench has no image decoder, the files hold the pixels (make-bench-pictures.mjs).
    const decodeImage = async (u) => { const [, file, w, h] = /^rgba:(.+):(\d+):(\d+)$/.exec(u); const b = await readFile(file); return { data: new Uint8Array(b.buffer, b.byteOffset, b.byteLength), width: Number(w), height: Number(h) }; };
    const p = D3.createD3BrowserProvider({
      ...(MM ? { repo: 'http://bench.invalid/d3', revision: 'bench' } : { repo: 'warsang/d3-edge-web', revision: '117fb255e630667ae1736666497e8a1c69c7a066' }),
      endpoint: 'https://huggingface.co', device: 'wasm', source, fetchImpl, decodeImage,
      loadOrt: async () => ort, loadTokenizerLib: async () => ({ PreTrainedTokenizer: tjs.PreTrainedTokenizer }),
      sessionOptions: () => ({ executionProviders: ['cpu'], logSeverityLevel: 3 }),
    });
    const t0 = Date.now();
    await p.load();
    console.log(`loaded d3-edge (onnxruntime-node, cpu) in ${Date.now() - t0} ms`);
    provider = p; modelId = 'd3'; label = MM ? `d3-edge (our export, fp16, CPU${process.env.PICTURES_DIR ? `, pictures: ${process.env.PICTURES ?? 'both'}` : ''}${process.env.GEOMETRY && process.env.GEOMETRY !== 'none' ? `, svg: ${process.env.GEOMETRY}` : ''}${!process.env.PICTURES_DIR && !(process.env.GEOMETRY && process.env.GEOMETRY !== 'none') ? ', text only' : ''})` : 'd3-edge (fp16 torso, CPU)'; stats = () => { const s = p.stats(); return { requests: s.requests, passes: s.passes, tokens: s.tokens, pictures: s.pictures, pictureMs: s.pictureMs }; };
  } else {
    const D = await server.ssrLoadModule('/src/classify/providers/decision.ts');
    const lib = need('TRANSFORMERS_NODE');
    const MODEL = process.env.HF_MODEL ?? 'MoritzLaurer/deberta-v3-xsmall-zeroshot-v1.1-all-33';
    const DTYPE = process.env.DTYPE ?? 'q8';
    const DEVICE = process.env.DEVICE ?? 'cpu'; // Node: 'cpu' (onnxruntime-node)
    const p = D.createDecisionProvider({
      model: MODEL, device: 'wasm', dtype: DTYPE, hfEndpoint: 'https://huggingface.co',
      hypothesis: { ...D.DEFAULT_HYPOTHESES, ...(process.env.HYP_DISCIPLINE ? { discipline: process.env.HYP_DISCIPLINE } : {}), ...(process.env.HYP_SUB ? { sub_discipline: process.env.HYP_SUB } : {}), ...(process.env.HYP_MF ? { masterformat: process.env.HYP_MF } : {}) },
      onProgress: (pr) => { if (pr.totalMB && Math.round(pr.progress * 100) % 25 === 0) process.stdout.write(`\r  ${pr.text}      `); },
      loadLib: async () => {
        const mod = await import(pathToFileURL(lib).href);
        return { env: mod.env, pipeline: (task, id, o) => mod.pipeline(task, id, { ...o, device: DEVICE }) };
      },
      gpu: async () => ({ present: false, adapter: false, f16: false }),
    });
    const t0 = Date.now();
    const rep = await p.load();
    console.log(`\nloaded ${MODEL} (${rep.dtype}) in ${Date.now() - t0} ms, labels ${rep.labels.join('/')}`);
    provider = p; modelId = `decision:${MODEL}`; label = `${MODEL} ${rep.dtype}`; stats = () => { const s = p.stats(); return { requests: s.requests, pairs: s.pairs, passes: s.passes }; };
  }

  // The model runs once per signature; the raw scores stay in the cache. rules:false: every element goes to the model.
  const cache = new C.MemoryCache();
  const t1 = Date.now();
  // With pictures: the representative element's pictures (drawn by make-bench-pictures.mjs) and the note, as the viewer passes them to the pipeline.
  let images;
  if (PROVIDER === 'd3' && process.env.PICTURES_DIR) {
    const T = await server.ssrLoadModule('/src/classify/thumbs.ts');
    const index = JSON.parse(await readFile(join(process.env.PICTURES_DIR, 'index.json'), 'utf8'));
    const mode = process.env.PICTURES ?? 'both';
    const modelOf = new Map(truths.map((t) => [t.input.id, t.model]));
    let missing = 0;
    images = (input) => {
      const e = index[`${modelOf.get(input.id)}|${input.id}`];
      const pics = (e?.pictures ?? []).filter((x) => mode === 'both' || x.view === mode);
      if (!pics.length) { missing++; return []; }
      return { images: pics.map((x) => `rgba:${x.rgba}:${x.width}:${x.height}`), note: T.pictureNote(pics.map((x) => x.view), 'render') };
    };
    process.on('exit', () => { if (missing) console.log(`${missing} elements had no pictures`); });
  }
  // With SVG: GEOMETRY=isolated|context and GEOMETRY_FILE=<geometry.json of make-bench-pictures.mjs with GEOMETRY_ONLY=1>.
  let geometry;
  if (process.env.GEOMETRY && process.env.GEOMETRY !== 'none') {
    const gj = JSON.parse(await readFile(need('GEOMETRY_FILE'), 'utf8'));
    const modelOf = new Map(truths.map((t) => [t.input.id, t.model]));
    geometry = (input) => gj[`${modelOf.get(input.id)}|${input.id}`]?.[process.env.GEOMETRY] ?? null;
  }
  const run = await C.classifyInputs(truths.map((t) => t.input), { schema, provider, rules: false, concurrency: 1, cache, maxStateBytes: PROVIDER === 'd3' ? 2000 : 4000, ...(images ? { images } : {}), ...(geometry ? { geometry } : {}) });
  const ms = Date.now() - t1;
  const st = stats();
  const row = new Map(run.results.map((r) => [r.id, r]));

  // Agreement as the model comes (T = 1).
  let dOk = 0, sOk = 0, mOk = 0, sN = 0, mN = 0;
  const rows = [];
  for (const t of truths) {
    const r = row.get(t.input.id);
    if (!r) { rows.push(`${t.model} ${t.input.ifcClass}: no result`); continue; }
    const d = r.discipline.code === t.discipline;
    dOk += d ? 1 : 0;
    if (t.subDiscipline) { sN++; sOk += r.subDiscipline?.code === t.subDiscipline ? 1 : 0; }
    if (t.division) { mN++; mOk += r.masterformat?.division === t.division ? 1 : 0; }
    rows.push(`${d ? 'ok  ' : 'MISS'} ${t.model.padEnd(10)} ${t.input.ifcClass.padEnd(24)} rule ${t.discipline}/${t.subDiscipline ?? '-'}/${t.division ?? '-'}  model ${r.discipline.code}(${r.discipline.confidence.toFixed(2)})/${r.subDiscipline?.code ?? '-'}/${r.masterformat?.division ?? '-'}`);
  }
  console.log(rows.join('\n'));

  // Logit scaling: out-of-fold temperatures per question.
  const sets = R.collectSamples(truths, (sig) => cache.get(sig));
  const cv = {};
  for (const q of Object.keys(sets)) if (sets[q].length >= 4) cv[q] = K.crossValidate(q, sets[q], MIN, FOLDS);
  const f = (x, d = 3) => (Number.isFinite(x) ? x.toFixed(d) : '-');
  const pct = (x) => (Number.isFinite(x) ? `${Math.round(x * 100)}%` : '-');
  const lines = [];
  lines.push('question            n    T      acc    meanConf  ECE    clear>=min  acc(clear)   [before -> after, out-of-fold]');
  for (const [q, c] of Object.entries(cv)) {
    lines.push(`${q.padEnd(18)} ${String(c.n).padStart(3)}  ${f(c.T, 2).padStart(5)}  before ${pct(c.before.accuracy).padStart(4)}  ${f(c.before.meanConfidence, 2)}   ${f(c.before.ece, 2)}   ${pct(c.before.clearShare).padStart(4)}   ${pct(c.before.clearAccuracy).padStart(4)}`);
    lines.push(`${''.padEnd(18)} ${''.padStart(3)}  ${''.padStart(5)}  after  ${pct(c.after.accuracy).padStart(4)}  ${f(c.after.meanConfidence, 2)}   ${f(c.after.ece, 2)}   ${pct(c.after.clearShare).padStart(4)}   ${pct(c.after.clearAccuracy).padStart(4)}`);
  }
  console.log(lines.join('\n'));

  // Joint view: elements whose discipline, sub-discipline and division all clear the minimum confidence, with out-of-fold temperatures.
  const foldOf = (key, k) => { let h = 2166136261; for (let i = 0; i < key.length; i++) h = Math.imul(h ^ key.charCodeAt(i), 16777619); return (h >>> 0) % k; };
  const joint = { before: { n: 0, clear: 0, right: 0 }, after: { n: 0, clear: 0, right: 0 } };
  for (const t of truths) {
    const d = cache.get(t.signature);
    if (!d?.raw) continue;
    for (const [which, temps] of [['before', {}], ['after', Object.fromEntries(Object.entries(cv).map(([q, c]) => [q, c.foldT[foldOf(t.signature, c.folds)]]))]]) {
      const r = P.rescoreDecision(schema, d, temps);
      const conf = [r.discipline.confidence, ...(r.subDiscipline && t.subDiscipline ? [r.subDiscipline.confidence] : []), ...(r.masterformat && t.division ? [r.masterformat.confidence] : [])];
      const right = r.discipline.code === t.discipline && (!t.subDiscipline || r.subDiscipline?.code === t.subDiscipline) && (!t.division || r.masterformat?.division === t.division);
      joint[which].n++;
      if (Math.min(...conf) >= MIN) { joint[which].clear++; joint[which].right += right ? 1 : 0; }
    }
  }
  console.log(`all parts at or above ${MIN}: before ${joint.before.clear}/${joint.before.n} (${joint.before.clear ? pct(joint.before.right / joint.before.clear) : '-'} all right), after ${joint.after.clear}/${joint.after.n} (${joint.after.clear ? pct(joint.after.right / joint.after.clear) : '-'} all right)`);

  const summary = {
    provider: PROVIDER, model: label, modelId, elements: truths.length, models: byModel,
    discipline: `${dOk}/${truths.length}`, subDiscipline: `${sOk}/${sN}`, masterformat: `${mOk}/${mN}`,
    totalMs: ms, msPerElement: Math.round(ms / truths.length), ...st,
    errors: run.stats.errors, minConfidence: MIN, folds: FOLDS,
    perElement: truths.map((t) => { const r = row.get(t.input.id); return r ? { model: t.model, ifcClass: t.input.ifcClass, rule: [t.discipline, t.subDiscipline ?? null, t.division ?? null], d3: [r.discipline.code, r.subDiscipline?.code ?? null, r.masterformat?.division ?? null], confidence: +r.discipline.confidence.toFixed(3) } : null; }),
    temperatures: Object.fromEntries(Object.entries(cv).map(([q, c]) => [q, +c.T.toFixed(3)])),
    crossValidation: cv, joint,
  };
  console.log(JSON.stringify({ ...summary, crossValidation: undefined }, null, 2));
  if (process.env.OUT) await writeFile(process.env.OUT, JSON.stringify(summary, null, 2));
} finally {
  await server.close();
}
