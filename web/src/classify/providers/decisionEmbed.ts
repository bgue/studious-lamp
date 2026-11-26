// The `embed` mode of the decision provider: label prototypes. Each option's label and description is embedded once, the element
// text is embedded per element, and the probabilities are a softmax over the cosine similarities divided by a temperature (the same idea
// as the embed mode of WebLLM). Everything here is pure; the provider in decision.ts runs the model.
//
// It is standalone on purpose: webllm.ts imports decision.ts, so decision.ts must not import webllm.ts.

export type DecisionMode = 'nli' | 'embed';
export const DECISION_MODES: readonly DecisionMode[] = ['nli', 'embed'];

export interface EmbedModelInfo {
  id: string;
  label: string;
  /** Download in MB per data type (ONNX files incl. external data, from the Hugging Face model API). */
  sizesMB: Partial<Record<'fp32' | 'fp16' | 'q8' | 'q4', number>>;
  /** How the token vectors become one vector (the model's own sentence-transformers setting). */
  pooling: 'mean' | 'cls';
  /** Text put before the ELEMENT (the query side). */
  queryPrefix: string;
  /** Text put before every OPTION (the document side). */
  docPrefix: string;
  note: string;
}

export const EMBED_MODELS: readonly EmbedModelInfo[] = [
  { id: 'onnx-community/embeddinggemma-300m-ONNX', label: 'EmbeddingGemma 300M (default)', sizesMB: { fp32: 1235, fp16: 617, q8: 309, q4: 197 }, pooling: 'mean', queryPrefix: 'task: search result | query: ', docPrefix: 'title: none | text: ', note: 'Gemma terms of use. The most exact of the three here, the largest download, 768 dimensions.' },
  { id: 'hotchpotch/bekko-embedding-v1-a25m', label: 'Bekko embedding v1 a25m', sizesMB: { fp32: 199 }, pooling: 'mean', queryPrefix: '', docPrefix: '', note: 'MIT. Multilingual, 384 dimensions, no prefixes. Only the model.onnx file is used (fp32 name, 199 MB).' },
  { id: 'onnx-community/granite-embedding-97m-multilingual-r2-ONNX', label: 'Granite embedding 97M multilingual r2', sizesMB: { fp32: 390, fp16: 195, q8: 98 }, pooling: 'cls', queryPrefix: '', docPrefix: '', note: 'Apache-2.0. Small and very fast, multilingual, 384 dimensions. Less exact on the discipline.' },
];
export const EMBED_DEFAULT_MODEL = EMBED_MODELS[0]!.id;
export const embedModelInfo = (id: string): EmbedModelInfo | undefined => EMBED_MODELS.find((m) => m.id === id);

/** Unit vector (a zero vector stays zero). */
export function normaliseVec(v: ArrayLike<number>): number[] {
  let s = 0;
  for (let i = 0; i < v.length; i++) s += v[i]! * v[i]!;
  const n = Math.sqrt(s) || 1;
  return Array.from({ length: v.length }, (_, i) => v[i]! / n);
}

export function cosineSim(a: ArrayLike<number>, b: ArrayLike<number>): number {
  const x = normaliseVec(a);
  const y = normaliseVec(b);
  let s = 0;
  for (let i = 0; i < x.length; i++) s += x[i]! * (y[i] ?? 0);
  return s;
}

/** Softmax of xs / temperature. Sums to 1. A temperature at or below 0 is 0.001 (nearly argmax). */
export function softmaxTemperature(xs: readonly number[], temperature: number): number[] {
  if (xs.length === 0) return [];
  const t = temperature > 0 ? temperature : 0.001;
  const m = Math.max(...xs);
  const e = xs.map((x) => Math.exp((x - m) / t));
  const s = e.reduce((a, b) => a + b, 0);
  return e.map((x) => x / s);
}

export interface EmbedScores {
  /** Probability per option (sums to 1). */
  probs: number[];
  /** cosine / temperature: the raw scores that calibration scales further. */
  logits: number[];
  cosines: number[];
}

/** Probabilities of the options from the element vector and the option (prototype) vectors. */
export function embedScores(element: ArrayLike<number>, options: ReadonlyArray<ArrayLike<number>>, temperature: number): EmbedScores {
  const cosines = options.map((o) => cosineSim(element, o));
  const t = temperature > 0 ? temperature : 0.001;
  return { probs: softmaxTemperature(cosines, temperature), logits: cosines.map((c) => c / t), cosines };
}

/** The statement and its negation as the two prototypes of a yes/no question. */
export function negation(statement: string): string {
  const s = statement.trim();
  return `It is not true that ${s.charAt(0).toLowerCase()}${s.slice(1)}`;
}

/** p(yes) of a statement: softmax over the cosines of the element to the statement and to its negation; logit = cosine difference / T. */
export function embedYes(element: ArrayLike<number>, pos: ArrayLike<number>, neg: ArrayLike<number>, temperature: number): { p: number; logit: number } {
  const { probs, logits } = embedScores(element, [pos, neg], temperature);
  return { p: probs[0]!, logit: logits[0]! - logits[1]! };
}

/** Rows of a [n, d] tensor (flat data and dims) as arrays. */
export function tensorRows(data: ArrayLike<number>, dims: readonly number[]): number[][] {
  const n = dims[0] ?? 0;
  const d = dims[1] ?? (n ? Math.round(data.length / n) : 0);
  return Array.from({ length: n }, (_, i) => Array.from({ length: d }, (_, j) => Number(data[i * d + j])));
}

export function describeEmbedModel(id: string, dtype: string = 'auto'): string {
  const m = embedModelInfo(id);
  if (!m) return `${id}: an embedding model from Hugging Face with ONNX weights. Mean pooling, no prefixes.`;
  const sizes = Object.entries(m.sizesMB).map(([k, v]) => `${k} ${v} MB`).join(', ');
  const one = dtype !== 'auto' ? (m.sizesMB as Record<string, number | undefined>)[dtype] : undefined;
  return `${m.label}: download ${one !== undefined ? `${one} MB (${dtype})` : sizes}. ${m.note}`;
}
