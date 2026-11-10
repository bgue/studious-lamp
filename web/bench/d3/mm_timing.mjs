// Time per element (one signature: the main request with 3 questions, then the sub-discipline request) on Node CPU with onnxruntime-node, with no
// picture, one picture (the isolated one) and two pictures (isolated, context), 384 px. Uses the requests of make-mm-requests.mjs.
// With SVG_DIR (the *.svg.txt files of bench/smoke-thumbs.mjs with PICTURES_DIR) it times the SVG arms too: text only, SVG of the element alone, SVG with its bounding box.
// Usage: ORT_NODE=... TRANSFORMERS_NODE=... D3_DIR=/tmp/d3-mm REQUESTS=/tmp/requests-mm.json [REPEAT=2] [OUT=/tmp/mm-timing.json] node bench/d3/mm_timing.mjs
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
const SVG_DIR = process.env.SVG_DIR;
const REPEAT = Number(process.env.REPEAT ?? 2);
const server = await createServer({ root, logLevel: 'error', server: { middlewareMode: true, hmr: false, watch: null }, appType: 'custom' });
try {
  const D3 = await server.ssrLoadModule('/src/classify/providers/d3.ts');
  const source = { has: async () => true, read: async (f) => new Uint8Array(await readFile(join(DIR, f))) };
  const fetchImpl = async (url) => { const f = String(url).split('/d3/')[1]?.split('?')[0]; try { return new Response(await readFile(join(DIR, f)), { status: 200 }); } catch { return new Response('', { status: 404 }); } };
  const decodeImage = async (u) => { const [, file, w, h] = /^rgba:(.+):(\d+):(\d+)(?:#\d+)?$/.exec(u); const b = await readFile(file); return { data: new Uint8Array(b.buffer, b.byteOffset, b.byteLength), width: Number(w), height: Number(h) }; };
  const p = D3.createD3BrowserProvider({
    repo: 'http://bench.invalid/d3', revision: 'bench', endpoint: 'https://huggingface.co', device: 'wasm', source, fetchImpl, decodeImage,
    loadOrt: async () => ort, loadTokenizerLib: async () => ({ PreTrainedTokenizer: tjs.PreTrainedTokenizer }),
    sessionOptions: () => ({ executionProviders: ['cpu'], logSeverityLevel: 3 }),
  });
  await p.load();
  const sig = new AbortController().signal;
  const out = [];
  for (const el of ['pipe', 'pump']) {
    const main = requests.find((r) => r.name === `${el}-both`);
    const sub = requests.find((r) => r.name === `${el}-sub`);
    const text = requests.find((r) => r.name === `${el}-text`);
    for (const n of [0, 1, 2]) {
      const times = [];
      let tokens = 0, visionMs = 0;
      for (let rep = 0; rep < REPEAT + 1; rep++) { // the first pass is a warm-up
        // a new picture set each repetition would hide the vision cost: dispose clears the memo of pictures
        // a new "#n" on the address makes the provider run the vision graph again (it remembers the pictures of the last requests)
        const imgs = (main.rgba ?? []).slice(0, n).map((x) => `rgba:${x.file}:${x.width}:${x.height}#${rep}`);
        const s0 = p.stats();
        const t0 = Date.now();
        const extra = n ? { images: imgs } : undefined;
        const m = await p.decide(n ? main.state : text.state, main.questions, sig, extra);
        const s = await p.decide(n ? sub.state : text.state, sub.questions, sig, extra);
        const ms = Date.now() - t0;
        const st = p.stats();
        if (rep > 0) times.push(ms);
        tokens = (m.usage?.input_tokens ?? 0) + (s.usage?.input_tokens ?? 0);
        visionMs = st.pictureMs - s0.pictureMs;
      }
      const mean = times.reduce((a, b) => a + b, 0) / times.length;
      out.push({ element: el, pictures: n, msPerElement: Math.round(mean), tokens, visionMs });
      console.log(`${el} with ${n} picture(s): ${Math.round(mean)} ms per element (main + sub), ${tokens} tokens, of which the vision graph ${visionMs} ms`);
    }
  }
  if (SVG_DIR) {
    for (const el of ['pipe', 'pump']) {
      const main = requests.find((r) => r.name === `${el}-both`);
      const sub = requests.find((r) => r.name === `${el}-sub`);
      const text = requests.find((r) => r.name === `${el}-text`);
      const lines = (await readFile(join(SVG_DIR, `${el}.svg.txt`), 'utf8')).trim().split('\n');
      const arms = { 'svg isolated': `Geometry as SVG, metres, plan then elevation; the element alone (origin at its bounding box corner). ${lines.slice(1, 3).join(' ')}`, 'svg + box': `${lines[0]} ${lines.slice(1).join(' ')}` };
      for (const [arm, geometry] of Object.entries(arms)) {
        const times = [];
        let tokens = 0;
        for (let rep = 0; rep < REPEAT + 1; rep++) {
          const st = { geometry, ...text.state };
          const t0 = Date.now();
          const m = await p.decide(st, main.questions, sig);
          const sres = await p.decide(st, sub.questions, sig);
          if (rep > 0) times.push(Date.now() - t0);
          tokens = (m.usage?.input_tokens ?? 0) + (sres.usage?.input_tokens ?? 0);
        }
        const mean = times.reduce((a, b) => a + b, 0) / times.length;
        out.push({ element: el, arm, msPerElement: Math.round(mean), tokens });
        console.log(`${el} with ${arm}: ${Math.round(mean)} ms per element (main + sub), ${tokens} tokens`);
      }
    }
  }
  if (process.env.OUT) await writeFile(process.env.OUT, JSON.stringify(out, null, 2));
  await p.dispose();
} finally {
  await server.close();
}
