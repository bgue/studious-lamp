// A FAKE of onnxruntime-web for the unit tests and for bench/smoke-classify-local.mjs (which serves this file in place of the CDN module).
// It has the surface that the d3 browser backend uses: `env`, `InferenceSession.create(bytes, options)`, `Tensor`. No ONNX, no model: the
// torso reads the prompt back from the token ids (bench/fake-transformers.mjs makes the ids character codes), scores each option by the
// words that it shares with the state, and returns the scores in the first slots of the hidden vector; the readout returns them as logits.
// The answers are deterministic and plausible. Plain JavaScript with no imports.

export const env = { wasm: {} };
export const __log = { sessions: [], runs: [] };
globalThis.__fakeOrtLog = __log;
export function __reset() {
  __log.sessions.length = 0;
  __log.runs.length = 0;
}

export class Tensor {
  constructor(type, data, dims) {
    this.type = type;
    this.data = data;
    this.dims = dims;
  }
}

const STOP = new Set(['this', 'that', 'class', 'name', 'with', 'from', 'state', 'question', 'options', 'reply', 'only', 'code', 'best', 'option', 'element', 'choose', 'building', 'true', 'false', 'inside']);
const words = (s) => new Set(s.toLowerCase().split(/[^a-z]+/).filter((w) => w.length >= 4 && !STOP.has(w)).map((w) => w.replace(/(ing|es|s)$/, '')));

function scoreOptions(text) {
  const user = text.slice(text.indexOf('<|im_start|>user'));
  const state = user.slice(user.indexOf('State:'), user.indexOf('Question:'));
  const optionsAt = user.indexOf('Options:');
  const lines = user.slice(optionsAt + 8, user.indexOf('Reply with only')).split('\n').filter((l) => /^[A-Z]{1,2}: /.test(l));
  const sw = words(state);
  if (lines.length === 2 && /^A: No \/ false/.test(lines[0]) && /^B: Yes \/ true/.test(lines[1])) {
    // a yes/no statement about a building: yes when the state says it is inside one
    const yes = /"building_context": true/.test(state) || /inside a building/.test(state);
    return [yes ? -3 : 3, yes ? 3 : -3];
  }
  return lines.map((l) => {
    let hits = 0;
    for (const w of words(l.replace(/^[A-Z]{1,2}: /, ''))) if (sw.has(w)) hits++;
    return 2.5 * hits - 1;
  });
}

export const InferenceSession = {
  async create(model, options = {}) {
    const bytes = model instanceof Uint8Array ? model.byteLength : 0;
    __log.sessions.push({ bytes, options });
    if (options.executionProviders?.[0] === 'webgpu' && globalThis.__fakeOrtFailWebgpu) throw new Error('fake: no webgpu');
    // The fake files are text: the readout starts with READOUT, the torso with TORSO.
    const isReadout = model instanceof Uint8Array && new TextDecoder().decode(model.slice(0, 7)) === 'READOUT';
    if (isReadout) {
      return {
        inputNames: ['last', 'counts'],
        outputNames: ['logits'],
        async run(feeds) {
          const last = feeds.last.data;
          const n = Number(feeds.counts.data[0]);
          const logits = new Float32Array(255).fill(-Infinity);
          for (let i = 0; i < n; i++) logits[i] = last[i];
          return { logits: new Tensor('float32', logits, [1, 255]) };
        },
        async release() {},
      };
    }
    return {
      inputNames: ['input_ids', 'attention_mask'],
      outputNames: ['last'],
      async run(feeds) {
        const ids = Array.from(feeds.input_ids.data, Number);
        const text = String.fromCodePoint(...ids);
        const scores = scoreOptions(text);
        __log.runs.push({ tokens: ids.length, options: scores.length });
        const last = new Float32Array(1024);
        scores.forEach((s, i) => { last[i] = s; });
        return { last: new Tensor('float32', last, [1, 1024]) };
      },
      async release() {},
    };
  },
};
