// Parity check of the d3 browser backend in Node: the REAL onnxruntime-node and the REAL torso and readout graphs of
// warsang/d3-edge-web (a local copy), the Qwen tokenizer from transformers.js, and OUR TypeScript prompt builder and readout.
// It runs the requests of bench/d3/requests.json (the model card examples and one BIM state) and writes the prompts and the
// probabilities, so that they can be compared with the official PyTorch model (bench/d3/reference.py).
//
// Needs a Node install of onnxruntime-node and @huggingface/transformers OUTSIDE the project (never a dependency of the viewer):
//   mkdir /tmp/ortnode && cd /tmp/ortnode && npm i onnxruntime-node@1.30.0 @huggingface/transformers@4.3.2
// and the files of the export in D3_DIR (MANIFEST.json decision_config.json tokenizer.json tokenizer_config.json onnx/*.onnx).
// Usage: ORT_NODE=/tmp/ortnode/node_modules/onnxruntime-node/dist/index.js TRANSFORMERS_NODE=/tmp/ortnode/node_modules/@huggingface/transformers/dist/transformers.node.mjs \
//        D3_DIR=/tmp/d3web OUT=/tmp/d3-ts.json node bench/real-d3-parity.mjs
import { readFile, writeFile } from 'node:fs/promises';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createServer } from 'vite';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const need = (k) => process.env[k] ?? (() => { throw new Error(`Set ${k}.`); })();
const DIR = need('D3_DIR');
const ort = await import(pathToFileURL(need('ORT_NODE')).href);
const tjs = await import(pathToFileURL(need('TRANSFORMERS_NODE')).href);
const requests = JSON.parse(await readFile(process.env.REQUESTS ?? join(here, 'd3', 'requests.json'), 'utf8'));

const server = await createServer({ root, logLevel: 'error', server: { middlewareMode: true, hmr: false, watch: null }, appType: 'custom' });
try {
  const D3 = await server.ssrLoadModule('/src/classify/providers/d3.ts');
  const F = await server.ssrLoadModule('/src/classify/providers/d3Format.ts');
  const source = {
    has: async () => true,
    read: async (f) => new Uint8Array(await readFile(join(DIR, f))),
  };
  // inspectD3Repo reads MANIFEST.json and decision_config.json through fetch: serve them from the folder.
  const fetchImpl = async (url) => {
    const f = String(url).split('/resolve/')[1]?.split('/').slice(1).join('/');
    try { return new Response(await readFile(join(DIR, f)), { status: 200 }); } catch { return new Response('', { status: 404 }); }
  };
  const provider = D3.createD3BrowserProvider({
    repo: 'warsang/d3-edge-web', revision: '117fb255e630667ae1736666497e8a1c69c7a066', endpoint: 'https://huggingface.co', device: 'wasm', source, fetchImpl,
    loadOrt: async () => ort,
    loadTokenizerLib: async () => ({ PreTrainedTokenizer: tjs.PreTrainedTokenizer }),
    sessionOptions: () => ({ executionProviders: ['cpu'], logSeverityLevel: 3 }),
  });
  const t0 = Date.now();
  const rep = await provider.load();
  console.log(`loaded in ${Date.now() - t0} ms (${rep.device})`);
  const out = [];
  for (const r of requests) {
    const t1 = Date.now();
    const a = await provider.decide(r.state, r.questions, new AbortController().signal);
    const ms = Date.now() - t1;
    const prompts = Object.fromEntries(Object.entries(r.questions).map(([k, q]) => [k, F.d3Render(r.state, q)]));
    out.push({ name: r.name, ms, tokens: a.usage?.input_tokens, prompts, answers: a.answers });
    console.log(`${r.name}: ${ms} ms, ${a.usage?.input_tokens} tokens`);
    for (const [k, v] of Object.entries(a.answers)) {
      console.log(`  ${k}: ${v.type === 'choice' ? Object.entries(v.probabilities).map(([o, p]) => `${o} ${p.toFixed(4)}`).join('  ') : v.type === 'noul' ? `yes ${v.noul.toFixed(4)}` : `score ${v.score.toFixed(3)} ${Object.values(v.probabilities).map((p) => p.toFixed(4)).join(' ')}`}`);
    }
  }
  if (process.env.OUT) await writeFile(process.env.OUT, JSON.stringify(out, null, 2));
  await provider.dispose();
} finally {
  await server.close();
}
