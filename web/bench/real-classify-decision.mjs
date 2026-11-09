// Real check of the `decision` provider in Node: the real transformers.js (WASM, onnxruntime-web or node), a real model from
// Hugging Face, N elements with distinct signatures from fzk-haus and synth5k. The rules' answers are the ground truth.
// It reports agreement (discipline, sub-discipline, MasterFormat division), the passes and the time per element.
//
// Needs the network (huggingface.co) and a Node install of @huggingface/transformers OUTSIDE the project (it is never a
// dependency of the viewer):  mkdir /tmp/tjs && cd /tmp/tjs && npm i @huggingface/transformers@4.3.2
// Usage:  TRANSFORMERS_NODE=/tmp/tjs/node_modules/@huggingface/transformers/dist/transformers.node.mjs \
//         HF_MODEL=MoritzLaurer/deberta-v3-xsmall-zeroshot-v1.1-all-33 DTYPE=q8 DEVICE=cpu N=20 node bench/real-classify-decision.mjs
import { dirname, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createServer } from 'vite';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const lib = process.env.TRANSFORMERS_NODE;
if (!lib) throw new Error('Set TRANSFORMERS_NODE to the transformers.node.mjs of a Node install of @huggingface/transformers.');
const MODEL = process.env.HF_MODEL ?? 'MoritzLaurer/deberta-v3-xsmall-zeroshot-v1.1-all-33';
const DTYPE = process.env.DTYPE ?? 'q8';
const DEVICE = process.env.DEVICE ?? 'cpu'; // Node: 'cpu' (onnxruntime-node) or 'wasm'
const N = Number(process.env.N ?? 20);

const server = await createServer({ root, logLevel: 'error', server: { middlewareMode: true, hmr: false, watch: null }, appType: 'custom' });
try {
  const C = await server.ssrLoadModule('/src/classify/index.ts');
  const D = await server.ssrLoadModule('/src/classify/providers/decision.ts');
  const H = await server.ssrLoadModule('/tests/classify-helpers.ts');
  const schema = C.defaultSchema();

  // N elements with distinct signatures, spread over both models (round-robin over the signatures of each).
  const pools = ['fzk-haus', 'synth5k'].map((name) => {
    const m = H.sidecarModel(name);
    const bySig = new Map();
    for (const i of C.buildInputs(m, m.elements.map((e) => e.id))) {
      const h = C.classByRules(i);
      const d = h ? C.resolveRule(h, schema, C.isBuildingContext(i)) : null;
      if (!d || d.confidence < C.RULE_FINAL) continue; // ground truth only where a rule is final
      const sig = C.signatureOf(i);
      if (!bySig.has(sig)) bySig.set(sig, { input: i, truth: d, model: name });
    }
    return [...bySig.values()];
  });
  const picked = [];
  for (let k = 0; picked.length < N && pools.some((p) => k < p.length); k++) for (const p of pools) if (k < p.length && picked.length < N) picked.push(p[k]);
  console.log(`${picked.length} elements with distinct signatures (${pools.map((p, i) => `${['fzk-haus', 'synth5k'][i]}: ${p.length} available`).join(', ')})`);

  const provider = D.createDecisionProvider({
    model: MODEL, device: 'wasm', dtype: DTYPE, hfEndpoint: 'https://huggingface.co', hypothesis: { ...D.DEFAULT_HYPOTHESES, ...(process.env.HYP_DISCIPLINE ? { discipline: process.env.HYP_DISCIPLINE } : {}), ...(process.env.HYP_SUB ? { sub_discipline: process.env.HYP_SUB } : {}), ...(process.env.HYP_MF ? { masterformat: process.env.HYP_MF } : {}) },
    onProgress: (p) => { if (p.totalMB && Math.round(p.progress * 100) % 25 === 0) process.stdout.write(`\r  ${p.text}      `); },
    // Node: the real library; the device name of onnxruntime-node is 'cpu', of onnxruntime-web 'wasm'.
    loadLib: async () => {
      const mod = await import(pathToFileURL(lib).href);
      const pipeline = mod.pipeline;
      return { env: mod.env, pipeline: (task, id, o) => pipeline(task, id, { ...o, device: DEVICE }) };
    },
    gpu: async () => ({ present: false, adapter: false, f16: false }),
  });
  const t0 = Date.now();
  const rep = await provider.load();
  console.log(`\nloaded ${MODEL} (${rep.dtype}) in ${Date.now() - t0} ms, labels ${rep.labels.join('/')}`);

  const inputs = picked.map((p) => p.input);
  const t1 = Date.now();
  const run = await C.classifyInputs(inputs, { schema, provider, rules: false, concurrency: 1, cache: new C.MemoryCache() });
  const ms = Date.now() - t1;
  const st = provider.stats();
  let dOk = 0, sOk = 0, mOk = 0, sN = 0, mN = 0;
  const rows = [];
  for (const [k, p] of picked.entries()) {
    const r = run.results.find((x) => x.id === p.input.id);
    if (!r) { rows.push(`${p.model} ${p.input.ifcClass}: no result`); continue; }
    const d = r.discipline.code === p.truth.discipline || schema.disciplines.find((x) => x.code === r.discipline.code)?.rulesKey === p.truth.discipline;
    dOk += d ? 1 : 0;
    if (p.truth.subDiscipline) { sN++; sOk += r.subDiscipline?.code === p.truth.subDiscipline ? 1 : 0; }
    if (p.truth.division) { mN++; mOk += r.masterformat?.division === p.truth.division ? 1 : 0; }
    rows.push(`${d ? 'ok  ' : 'MISS'} ${p.model.padEnd(8)} ${p.input.ifcClass.padEnd(22)} rule ${p.truth.discipline}/${p.truth.subDiscipline ?? '-'}/${p.truth.division ?? '-'}  model ${r.discipline.code}(${r.discipline.confidence.toFixed(2)})/${r.subDiscipline?.code ?? '-'}/${r.masterformat?.division ?? '-'}${r.needsReview ? ' review' : ''}`);
  }
  console.log(rows.join('\n'));
  console.log(JSON.stringify({
    model: MODEL, dtype: rep.dtype, device: DEVICE, elements: picked.length,
    discipline: `${dOk}/${picked.length}`, subDiscipline: `${sOk}/${sN}`, masterformat: `${mOk}/${mN}`,
    totalMs: ms, msPerElement: Math.round(ms / picked.length), requests: st.requests, pairs: st.pairs, passes: st.passes,
    pairsPerElement: +(st.pairs / picked.length).toFixed(1), passesPerElement: +(st.passes / picked.length).toFixed(1), cachedPairs: st.cachedPairs,
    needsReview: run.stats.needsReview, errors: run.stats.errors,
  }, null, 2));
} finally {
  await server.close();
}
