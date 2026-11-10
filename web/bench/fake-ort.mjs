// A FAKE of onnxruntime-web for the unit tests and for bench/smoke-classify-local.mjs (which serves this file in place of the CDN module).
// It has the surface that the d3 browser backend uses: `env`, `InferenceSession.create(bytes, options)`, `Tensor`. No ONNX, no model: the
// torso reads the prompt back from the token ids (bench/fake-transformers.mjs makes the ids character codes), scores each option by the
// words that it shares with the state, and returns the scores in the first slots of the hidden vector; the readout returns them as logits.
// The answers are deterministic and plausible. Plain JavaScript with no imports.

export const env = { wasm: {} };
export const __log = { sessions: [], runs: [], vision: [] };
globalThis.__fakeOrtLog = __log;
export function __reset() {
  __log.sessions.length = 0;
  __log.runs.length = 0;
  __log.vision.length = 0;
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

const IMAGE_TOKEN = 248056;
const dec = (model, n) => (model instanceof Uint8Array ? new TextDecoder().decode(model.slice(0, n)) : '');

export const InferenceSession = {
  async create(model, options = {}) {
    const bytes = model instanceof Uint8Array ? model.byteLength : 0;
    __log.sessions.push({ bytes, options });
    if (options.executionProviders?.[0] === 'webgpu' && globalThis.__fakeOrtFailWebgpu) throw new Error('fake: no webgpu');
    // The fake files are text: the readout starts with READOUT, the vision encoder with VISION, the multimodal torso with TORSOMM, the text torso with TORSO.
    const isReadout = dec(model, 7) === 'READOUT';
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
    if (dec(model, 6) === 'VISION') {
      // pixel_values [N, 768], pos_hw [N, 2], pos_idx [N, 4], pos_w [N, 4] -> embeds [N / 4, 1024]. It checks what the viewer sends, then puts the
      // mean of the pixel values in slot 0 of every row, so that a test sees which picture came through.
      return {
        inputNames: ['pixel_values', 'pos_hw', 'pos_idx', 'pos_w'],
        outputNames: ['embeds'],
        async run(feeds) {
          const pv = feeds.pixel_values;
          const n = pv.dims[0];
          const ok = pv.dims[1] === 768 && feeds.pos_hw.dims[0] === n && feeds.pos_hw.dims[1] === 2 && feeds.pos_idx.dims[0] === n && feeds.pos_idx.dims[1] === 4 && feeds.pos_w.dims[1] === 4 && pv.data.length === n * 768;
          if (!ok) throw new Error(`fake vision: bad input shapes ${JSON.stringify([pv.dims, feeds.pos_hw.dims, feeds.pos_idx.dims, feeds.pos_w.dims])}`);
          let sum = 0;
          for (let i = 0; i < pv.data.length; i++) sum += pv.data[i];
          let wsum = 0;
          for (let i = 0; i < n; i++) { let w = 0; for (let k = 0; k < 4; k++) w += feeds.pos_w.data[i * 4 + k]; wsum += w; }
          for (const x of feeds.pos_idx.data) if (!(Number(x) >= 0 && Number(x) < 2304)) throw new Error('fake vision: a position tap is outside the 48 x 48 table');
          const mean = sum / pv.data.length;
          __log.vision.push({ patches: n, mean, weightMean: wsum / n, maxRow: Math.max(...Array.from(feeds.pos_hw.data, Number).filter((_, i) => i % 2 === 0)) });
          const out = new Float32Array((n / 4) * 1024);
          for (let r = 0; r < n / 4; r++) out[r * 1024] = mean;
          return { embeds: new Tensor('float32', out, [n / 4, 1024]) };
        },
        async release() {},
      };
    }
    const multimodal = dec(model, 7) === 'TORSOMM';
    return {
      inputNames: multimodal ? ['input_ids', 'image_embeds', 'position_ids'] : ['input_ids', 'attention_mask'],
      outputNames: ['last'],
      async run(feeds) {
        const ids = Array.from(feeds.input_ids.data, Number);
        const imageTokens = ids.filter((x) => x === IMAGE_TOKEN).length;
        if (multimodal) {
          const rows = feeds.image_embeds.dims[0];
          const L = ids.length;
          if (feeds.position_ids.dims.join() !== `3,1,${L}`) throw new Error(`fake torso: position_ids has dims ${feeds.position_ids.dims}`);
          if (imageTokens > 0 && rows !== imageTokens) throw new Error(`fake torso: ${imageTokens} picture tokens but ${rows} embedding rows`);
          __log.runs.push({ tokens: L, imageTokens, rows, pos: Array.from(feeds.position_ids.data, Number), embedSlot0: Array.from({ length: Math.min(rows, imageTokens || 1) }, (_, i) => feeds.image_embeds.data[i * 1024]) });
        }
        const text = String.fromCodePoint(...ids.map((x) => (x === IMAGE_TOKEN ? 0x2588 : x)));
        const scores = scoreOptions(text);
        if (!multimodal) __log.runs.push({ tokens: ids.length, options: scores.length });
        else __log.runs.at(-1).options = scores.length;
        const last = new Float32Array(1024);
        scores.forEach((sc, i) => { last[i] = sc; });
        return { last: new Tensor('float32', last, [1, 1024]) };
      },
      async release() {},
    };
  },
};
