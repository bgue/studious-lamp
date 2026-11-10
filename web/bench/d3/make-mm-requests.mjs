// Builds the requests of the multimodal parity run (bench/d3/mm_reference.py and bench/d3/mm_parity.mjs): the model card's receipt example and
// two BIM requests of process-plant (a pipe spool and a pump) with the pictures that bench/smoke-thumbs.mjs wrote (PICTURES_DIR), exactly as the
// viewer sends them: the state of the element with the note about the pictures first, then the main questions (discipline, building) and
// the sub-discipline question of the discipline.
// Usage: PICTURES_DIR=/tmp/pictures RECEIPT=/path/example-receipt.png OUT=/tmp/requests-mm.json node bench/d3/make-mm-requests.mjs
import { readFile, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createServer } from 'vite';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..', '..');
const need = (k) => process.env[k] ?? (() => { throw new Error(`Set ${k}.`); })();
const DIR = need('PICTURES_DIR');
const server = await createServer({ root, logLevel: 'error', server: { middlewareMode: true, hmr: false, watch: null }, appType: 'custom' });
try {
  const C = await server.ssrLoadModule('/src/classify/index.ts');
  const Q = await server.ssrLoadModule('/src/classify/questions.ts');
  const S = await server.ssrLoadModule('/src/classify/state.ts');
  const H = await server.ssrLoadModule('/tests/classify-helpers.ts');
  const T = await server.ssrLoadModule('/src/classify/thumbs.ts');
  const schema = C.defaultSchema();
  const model = H.sidecarModel('process-plant');
  const index = JSON.parse(await readFile(resolve(DIR, 'index.json'), 'utf8'));
  const out = [];
  // the model card example with the receipt (the same questions as the card)
  out.push({
    name: 'receipt',
    state: 'The customer says the blender arrived cracked and attached the receipt.',
    images: [need('RECEIPT')],
    questions: {
      route: { type: 'choice', instructions: 'Which team should handle this request?', criteria: { returns: 'Refunds, replacements and damaged deliveries', billing: 'Payments, invoices and charges', technical: 'Product setup and faults' } },
      on_receipt: { type: 'noul', instructions: 'Does the receipt list the blender?' },
      payment: { type: 'choice', instructions: 'How was the order paid?', criteria: { card: null, cash: null, 'gift card': null } },
    },
  });
  for (const [key, gid, style] of [['pipe', 352, 'render'], ['pump', 330, 'render'], ['pipe-vector', 352, 'vector']]) {
    const el = key.split('-')[0];
    const pics = index.filter((p) => p.element === el && p.style === style && (p.view === 'isolated' || p.view === 'context'));
    const input = C.buildInputs(model, [gid])[0];
    const note = T.pictureNote(pics.map((p) => p.view), style);
    const state = { pictures: note, ...S.buildState(input, 2000) };
    const main = Q.mainQuestions(schema);
    out.push({ name: `${key}-both`, element: input.name, state, questions: main, images: pics.map((p) => resolve(DIR, p.file)), rgba: pics.map((p) => ({ file: resolve(DIR, p.rgba), width: p.width, height: p.height })) });
    const sub = Q.subQuestions(schema, ['MEC', 'PLB', 'STR']);
    if (sub) out.push({ name: `${key}-sub`, element: input.name, state, questions: sub, images: pics.map((p) => resolve(DIR, p.file)), rgba: pics.map((p) => ({ file: resolve(DIR, p.rgba), width: p.width, height: p.height })) });
    // the same request as text only, for the difference the pictures make
    out.push({ name: `${key}-text`, element: input.name, state: S.buildState(input, 2000), questions: main, images: [] });
  }
  await writeFile(need('OUT'), JSON.stringify(out, null, 2));
  console.log(`wrote ${out.length} requests to ${process.env.OUT}`);
} finally {
  await server.close();
}
