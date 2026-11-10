// Parity of OUR multimodal ONNX export (tools/export_d3_web.py) and its TypeScript side (providers/d3.ts, d3Vision.ts: picture preprocessing, positions)
// against the official vllm-sr/d3-edge (bench/d3/mm_reference.py). Real onnxruntime-node (CPU), the real graphs, the Qwen tokenizer of transformers.js.
// Reads the requests (make-mm-requests.mjs, after mm_reference.py added the pixels of the receipt) and the official answers, runs every request through
// the provider (pictures from the raw RGBA files), prints the largest probability difference and the argmax agreement, and the time per request.
//
// Needs a Node install of onnxruntime-node and @huggingface/transformers OUTSIDE the project (never a dependency of the viewer):
//   mkdir /tmp/ortnode && cd /tmp/ortnode && npm i onnxruntime-node@1.30.0 @huggingface/transformers@4.3.2
// Usage: ORT_NODE=/tmp/ortnode/node_modules/onnxruntime-node/dist/index.js TRANSFORMERS_NODE=/tmp/ortnode/node_modules/@huggingface/transformers/dist/transformers.node.mjs \
//        D3_DIR=/tmp/d3-mm REQUESTS=/tmp/requests-mm.json REFERENCE=/tmp/ref-mm.json [OUT=/tmp/mm-parity.json] [ONLY=name,name] node bench/d3/mm_parity.mjs
import { readFile, writeFile } from 'node:fs/promises';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createServer } from 'vite';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..', '..');
const need = (k) => process.env[k] ?? (() => { throw new Error(`Set ${k}.`); })();
const DIR = need('D3_DIR');
const ort = await import(pathToFileURL(need('ORT_NODE')).href);
const tjs = await import(pathToFileURL(need('TRANSFORMERS_NODE')).href);
const requests = JSON.parse(await readFile(need('REQUESTS'), 'utf8'));
const reference = JSON.parse(await readFile(need('REFERENCE'), 'utf8'));
const only = process.env.ONLY ? new Set(process.env.ONLY.split(',')) : null;

const server = await createServer({ root, logLevel: 'error', server: { middlewareMode: true, hmr: false, watch: null }, appType: 'custom' });
try {
  const D3 = await server.ssrLoadModule('/src/classify/providers/d3.ts');
  const source = { has: async () => true, read: async (f) => new Uint8Array(await readFile(join(DIR, f))) };
  const fetchImpl = async (url) => {
    const f = String(url).split('/d3/')[1]?.split('?')[0];
    try { return new Response(await readFile(join(DIR, f)), { status: 200 }); } catch { return new Response('', { status: 404 }); }
  };
  // The pictures arrive as "rgba:<file>:<width>:<height>" instead of data URLs: the Node bench has no image decoder, the files hold the pixels.
  const decodeImage = async (u) => {
    const [, file, w, h] = /^rgba:(.+):(\d+):(\d+)$/.exec(u);
    const b = await readFile(file);
    return { data: new Uint8Array(b.buffer, b.byteOffset, b.byteLength), width: Number(w), height: Number(h) };
  };
  const provider = D3.createD3BrowserProvider({
    repo: 'http://bench.invalid/d3', revision: 'bench', endpoint: 'https://huggingface.co', device: 'wasm', source, fetchImpl, decodeImage,
    loadOrt: async () => ort, loadTokenizerLib: async () => ({ PreTrainedTokenizer: tjs.PreTrainedTokenizer }),
    sessionOptions: () => ({ executionProviders: ['cpu'], logSeverityLevel: 3 }),
  });
  // inspectD3Repo reads the manifest and the config through fetch: serve them from the folder (a base URL ending in /d3).
  const t0 = Date.now();
  const rep = await provider.load();
  console.log(`loaded in ${Date.now() - t0} ms (${rep.device}), pictures ${rep.vision ? 'on' : 'off'}`);
  const rows = [];
  let worst = 0;
  let agree = 0;
  let total = 0;
  for (const r of requests) {
    if (only && !only.has(r.name)) continue;
    const ref = reference.find((x) => x.name === r.name);
    if (!ref) continue;
    const images = (r.rgba ?? []).map((x) => `rgba:${x.file}:${x.width}:${x.height}`);
    const stats0 = provider.stats();
    const t1 = Date.now();
    const a = await provider.decide(r.state, r.questions, new AbortController().signal, images.length ? { images } : undefined);
    const ms = Date.now() - t1;
    const st = provider.stats();
    const row = { name: r.name, ms, pictureMs: st.pictureMs - stats0.pictureMs, tokens: a.usage?.input_tokens, refTokens: ref.usage?.input_tokens, questions: {} };
    for (const [k, v] of Object.entries(a.answers)) {
      const o = ref.answers[k];
      let diff = 0, ok = false;
      if (v.type === 'choice') {
        for (const key of Object.keys(v.probabilities)) diff = Math.max(diff, Math.abs(v.probabilities[key] - o.probabilities[key]));
        ok = v.choice === o.choice;
        row.questions[k] = { ours: v.choice, official: o.choice, diff, top: v.probabilities[v.choice], topOfficial: o.probabilities[o.choice] };
      } else if (v.type === 'score') {
        for (const key of Object.keys(v.probabilities)) diff = Math.max(diff, Math.abs(v.probabilities[key] - o.probabilities[key]));
        ok = Math.abs(v.score - o.score) < 0.1;
        row.questions[k] = { ours: v.score, official: o.score, diff };
      } else if (v.type === 'noul') {
        diff = Math.abs(v.noul - o.noul);
        ok = (v.noul >= 0.5) === (o.noul >= 0.5);
        row.questions[k] = { ours: v.noul, official: o.noul, diff };
      }
      worst = Math.max(worst, diff);
      total++;
      if (ok) agree++;
    }
    rows.push(row);
    console.log(`${r.name}: ${ms} ms (pictures ${row.pictureMs} ms), tokens ${row.tokens} (official ${row.refTokens})`);
    for (const [k, q] of Object.entries(row.questions)) console.log(`  ${k}: ${q.ours} vs ${q.official}  max diff ${q.diff.toFixed(4)}${q.top !== undefined ? `  top ${q.top.toFixed(4)} / ${q.topOfficial.toFixed(4)}` : ''}`);
  }
  console.log(`WORST probability difference ${worst.toFixed(4)}; argmax agrees ${agree}/${total}`);
  if (process.env.OUT) await writeFile(process.env.OUT, JSON.stringify({ worst, agree, total, rows }, null, 2));
  await provider.dispose();
} finally {
  await server.close();
}
