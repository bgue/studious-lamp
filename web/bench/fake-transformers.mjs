// A FAKE of the transformers.js module, for the unit tests and for bench/smoke-classify-local.mjs (which serves this file
// in place of the CDN module). It has the same surface that the decision provider uses: `env`, `pipeline(task, model, opts)`
// and a pipeline with `.tokenizer` and `.model` (raw logits). No download, no ONNX: the logits come from word overlap between
// the premise and the hypothesis, so the answers are deterministic and plausible.
//
// Plain JavaScript with no imports, because the smoke test serves the text as a module.

export const env = { remoteHost: 'https://huggingface.co/', allowLocalModels: true, useBrowserCache: false, fetch: (u, i) => globalThis.fetch(u, i) };

/** What happened, for the assertions. Reset with __reset(). */
export const __log = { pipelines: [], batches: [], loads: 0 };
// The smoke test reads the log from the page.
globalThis.__fakeTransformersLog = __log;
export function __reset() {
  __log.pipelines.length = 0;
  __log.batches.length = 0;
  __log.loads = 0;
}

const STOP = new Set(['this', 'that', 'building', 'element', 'belongs', 'discipline', 'part', 'work', 'falls', 'under', 'class', 'name', 'type', 'with', 'from', 'inside', 'storey', 'hosted', 'there']);
const stems = (s) => new Set(s.toLowerCase().split(/[^a-z]+/).filter((w) => w.length >= 4 && !STOP.has(w)).map((w) => w.replace(/(ing|es|s)$/, '')));

/** Entailment logit of a (premise, hypothesis) pair. */
export function entailLogit(premise, hypothesis) {
  if (/^This element is part of a building/.test(hypothesis)) return /It is inside a building/.test(premise) ? 4 : -4;
  const p = stems(premise);
  let hits = 0;
  for (const w of stems(hypothesis)) if (p.has(w)) hits++;
  return 2.5 * hits - 1;
}

export async function pipeline(task, model, opts = {}) {
  if (task !== 'zero-shot-classification') throw new Error(`fake: unsupported task ${task}`);
  __log.pipelines.push({ task, model, device: opts.device, dtype: opts.dtype });
  __log.loads++;
  const cb = opts.progress_callback;
  if (cb) {
    const file = `onnx/model_${opts.dtype ?? 'fp32'}.onnx`;
    const total = 87_000_000;
    cb({ status: 'initiate', file });
    for (const f of [0.25, 0.5, 0.75, 1]) cb({ status: 'progress', file, loaded: Math.round(total * f), total });
    cb({ status: 'done', file });
    cb({ status: 'ready' });
  }
  const binary = /zeroshot|xtremedistil/i.test(model);
  const label2id = binary ? { entailment: 0, not_entailment: 1 } : { contradiction: 0, entailment: 1, neutral: 2 };
  const L = Object.keys(label2id).length;
  const entId = label2id.entailment;
  const againstId = label2id.contradiction ?? label2id.not_entailment;
  const tokenizer = (premises, o) => ({ premises, hyps: o.text_pair, padding: o.padding, truncation: o.truncation });
  const m = async (inputs) => {
    __log.batches.push({ size: inputs.hyps.length, premise: inputs.premises[0], hyps: [...inputs.hyps] });
    const data = new Float32Array(inputs.hyps.length * L);
    inputs.hyps.forEach((h, i) => {
      const e = entailLogit(inputs.premises[i], h);
      data[i * L + entId] = e;
      data[i * L + againstId] = -e;
    });
    return { logits: { data, dims: [inputs.hyps.length, L] } };
  };
  m.config = { label2id, id2label: Object.fromEntries(Object.entries(label2id).map(([k, v]) => [String(v), k])) };
  const pipe = async () => { throw new Error('fake: use tokenizer and model'); };
  pipe.tokenizer = tokenizer;
  pipe.model = m;
  pipe.dispose = async () => {};
  return pipe;
}
