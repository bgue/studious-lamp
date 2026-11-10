// Logit scaling (temperature calibration) for the decision providers. No DOM.
//
// A decision model gives a score per option (a logit). The probability is exp(score / T) normalised over the options.
// T = 1 is the model as it comes. The zero-shot NLI models are under-confident on this task: the ranking is decent, the
// probabilities are flat, so every answer sat under the minimum confidence. A temperature below 1 sharpens the
// distribution, above 1 flattens it. T is fitted per question (discipline, sub_discipline, masterformat, building_element)
// by minimising the negative log-likelihood on labelled answers. The ranking never changes (T is positive), only the
// confidence does, so calibration cannot fake accuracy: it makes the confidence track it.
//
// A provider that returns probabilities (Jev, d3, webllm) is scaled in the log domain: p_i ∝ exp(log p_i / T).
// The result cache keeps the raw scores, and calibration is applied when a result is read, so changing the mode or T
// re-scores without running the model again.

import { Q_BUILDING, Q_DISCIPLINE, Q_MASTERFORMAT, Q_SUB } from './questions';
import type { Answer, Answers, ChoiceAnswer, NoulAnswer } from './jevAdapter';

export const CALIBRATION_MODES = ['auto', 'fitted', 'manual', 'off'] as const;
export type CalibrationMode = (typeof CALIBRATION_MODES)[number];

/** The questions that have a temperature. */
export const TEMPERATURE_KEYS = [Q_DISCIPLINE, Q_SUB, Q_MASTERFORMAT, Q_BUILDING] as const;
export type TemperatureKey = (typeof TEMPERATURE_KEYS)[number];
export type Temperatures = Partial<Record<TemperatureKey, number>>;

export const T_MIN = 0.05;
export const T_MAX = 50;
export const isTemperatureKey = (k: string): k is TemperatureKey => (TEMPERATURE_KEYS as readonly string[]).includes(k);

/** Problem with one temperature, or null. */
export function temperatureProblem(v: unknown, name: string): string | null {
  if (typeof v !== 'number' || !Number.isFinite(v) || v < T_MIN || v > T_MAX) return `${name} must be a number from ${T_MIN} to ${T_MAX}.`;
  return null;
}

// ---------------------------------------------------------------- the maths

const FLOOR = 1e-12;

/** Natural log of a probability, with a floor so that a zero stays finite. */
export const logOf = (p: number): number => Math.log(Math.max(p, FLOOR));

/** log of the sum of exp(xs), stable. */
export function logSumExp(xs: readonly number[]): number {
  if (xs.length === 0) return -Infinity;
  const m = Math.max(...xs);
  if (!Number.isFinite(m)) return m;
  let s = 0;
  for (const x of xs) s += Math.exp(x - m);
  return m + Math.log(s);
}

/** p_i = exp(l_i / T) / sum. T must be positive; T = 1 is the plain softmax. */
export function softmaxT(logits: readonly number[], T = 1): number[] {
  if (logits.length === 0) return [];
  const t = T > 0 ? T : 1;
  const scaled = logits.map((x) => x / t);
  const lse = logSumExp(scaled);
  return scaled.map((x) => Math.exp(x - lse));
}

/** Probability of "yes" from a log-odds value, scaled by T. */
export function sigmoidT(logit: number, T = 1): number {
  const x = logit / (T > 0 ? T : 1);
  return x >= 0 ? 1 / (1 + Math.exp(-x)) : Math.exp(x) / (1 + Math.exp(x));
}

export const logit = (p: number): number => logOf(p) - logOf(1 - p);

/** Index of the largest value; the first one wins a tie. */
export function argmax(xs: readonly number[]): number {
  let b = 0;
  for (let i = 1; i < xs.length; i++) if (xs[i]! > xs[b]!) b = i;
  return b;
}

// ---------------------------------------------------------------- raw scores (what the cache keeps)

/** The raw scores of one answer: a score per option (choice) or the log-odds of yes (noul). */
export type RawQuestion = { logits: Record<string, number> } | { logit: number };
export interface RawAnswers {
  model: string;
  questions: Record<string, RawQuestion>;
}
/** The raw scores of both requests of a decision, and the sub-codes that the second request covered. */
export interface RawDecision {
  main: RawAnswers;
  sub: RawAnswers | null;
  subCodes: string[];
}

const r4 = (x: number): number => Math.round(x * 1e4) / 1e4;

/** Raw scores of an answer: its own logits when the provider gave them, else the log of its probabilities. Score answers are skipped. */
export function rawOfAnswer(a: Answer): RawQuestion | null {
  if (a.type === 'choice') {
    const src = a.logits ?? Object.fromEntries(Object.entries(a.probabilities).map(([k, p]) => [k, logOf(p)]));
    return { logits: Object.fromEntries(Object.entries(src).map(([k, v]) => [k, r4(v)])) };
  }
  if (a.type === 'noul') return { logit: r4(a.logit ?? logit(a.noul)) };
  return null;
}

export function rawOfAnswers(a: Answers): RawAnswers {
  const questions: Record<string, RawQuestion> = {};
  for (const [k, v] of Object.entries(a.answers)) {
    const r = rawOfAnswer(v);
    if (r) questions[k] = r;
  }
  return { model: a.model, questions };
}

/** Rebuild answers from raw scores at the given temperatures. */
export function answersFromRaw(raw: RawAnswers, temps: Temperatures = {}): Answers {
  const answers: Record<string, Answer> = {};
  for (const [name, q] of Object.entries(raw.questions)) {
    const T = temps[name as TemperatureKey] ?? 1;
    if ('logits' in q) {
      const keys = Object.keys(q.logits);
      const p = softmaxT(keys.map((k) => q.logits[k]!), T);
      const best = argmax(keys.map((k) => q.logits[k]!));
      answers[name] = { type: 'choice', choice: keys[best]!, confidence: p[best]!, probabilities: Object.fromEntries(keys.map((k, i) => [k, p[i]!])), logits: q.logits };
    } else {
      answers[name] = { type: 'noul', noul: sigmoidT(q.logit, T), logit: q.logit };
    }
  }
  return { model: raw.model, answers };
}

/** True when every temperature is 1 or missing: the scaling changes nothing. */
export const isIdentity = (t: Temperatures | undefined | null): boolean => !t || TEMPERATURE_KEYS.every((k) => t[k] === undefined || t[k] === 1);

/**
 * Scale the answers of a provider. Choice: p ∝ exp(logit / T), with the logits of the provider when it gave them and the
 * log of its probabilities otherwise. The chosen option does not change. A question without a temperature keeps its answer
 * untouched (the provider's own probabilities and confidence).
 */
export function calibrateAnswers(a: Answers, temps: Temperatures | undefined | null): Answers {
  if (isIdentity(temps)) return a;
  const answers: Record<string, Answer> = {};
  for (const [name, x] of Object.entries(a.answers)) {
    const T = isTemperatureKey(name) ? temps![name] : undefined;
    if (T === undefined || T === 1) {
      answers[name] = x;
      continue;
    }
    if (x.type === 'choice') {
      const keys = Object.keys(x.probabilities);
      const lg = x.logits ?? Object.fromEntries(keys.map((k) => [k, logOf(x.probabilities[k]!)]));
      const p = softmaxT(keys.map((k) => lg[k] ?? -Infinity), T);
      const probabilities = Object.fromEntries(keys.map((k, i) => [k, p[i]!]));
      const chosen = keys.indexOf(x.choice);
      const out: ChoiceAnswer = { type: 'choice', choice: x.choice, confidence: p[chosen >= 0 ? chosen : argmax(p)]!, probabilities };
      if (x.logits) out.logits = x.logits;
      answers[name] = out;
    } else if (x.type === 'noul') {
      const out: NoulAnswer = { type: 'noul', noul: sigmoidT(x.logit ?? logit(x.noul), T) };
      if (x.logit !== undefined) out.logit = x.logit;
      answers[name] = out;
    } else answers[name] = x;
  }
  return { ...a, answers };
}

// ---------------------------------------------------------------- fitting

/** One labelled answer: the raw scores of the options and the index of the right one. */
export interface Sample {
  logits: number[];
  label: number;
}

/** Negative log-likelihood per sample at temperature T. */
export function nll(samples: readonly Sample[], T: number): number {
  if (samples.length === 0) return 0;
  let s = 0;
  for (const x of samples) {
    const scaled = x.logits.map((v) => v / T);
    s += logSumExp(scaled) - scaled[x.label]!;
  }
  return s / samples.length;
}

export interface Fit {
  /** The fitted temperature, clamped to [T_MIN, T_MAX]. */
  T: number;
  /** NLL per sample at the fitted T and at T = 1. */
  nll: number;
  nllRaw: number;
  n: number;
}

/**
 * Fit T by minimising the NLL. In beta = 1/T the NLL is convex, so a golden-section search over log(beta) is exact enough
 * (it finds the minimum to 1e-6 in log space). With fewer than 2 samples, or no variation, T = 1.
 */
export function fitTemperature(samples: readonly Sample[]): Fit {
  const usable = samples.filter((x) => x.logits.length >= 2 && x.label >= 0 && x.label < x.logits.length && x.logits.every(Number.isFinite));
  const base: Fit = { T: 1, nll: nll(usable, 1), nllRaw: nll(usable, 1), n: usable.length };
  if (usable.length < 2) return base;
  let lo = Math.log(1 / T_MAX);
  let hi = Math.log(1 / T_MIN);
  const f = (lb: number): number => nll(usable, 1 / Math.exp(lb));
  const phi = (Math.sqrt(5) - 1) / 2;
  let a = hi - phi * (hi - lo);
  let b = lo + phi * (hi - lo);
  let fa = f(a);
  let fb = f(b);
  for (let i = 0; i < 80 && hi - lo > 1e-7; i++) {
    if (fa < fb) { hi = b; b = a; fb = fa; a = hi - phi * (hi - lo); fa = f(a); }
    else { lo = a; a = b; fa = fb; b = lo + phi * (hi - lo); fb = f(b); }
  }
  const T = Math.min(T_MAX, Math.max(T_MIN, 1 / Math.exp((lo + hi) / 2)));
  return { T, nll: nll(usable, T), nllRaw: base.nll, n: usable.length };
}

// ---------------------------------------------------------------- measuring

export interface CalibrationMetrics {
  n: number;
  /** Share of answers whose top option is the right one. */
  accuracy: number;
  /** Mean of the top probability. */
  meanConfidence: number;
  /** Expected calibration error with 10 equal-width bins. */
  ece: number;
  /** Share of answers whose confidence is at or above the minimum confidence. */
  clearShare: number;
  /** Accuracy of the answers that clear it (NaN when none do). */
  clearAccuracy: number;
  nll: number;
}

export const ECE_BINS = 10;

/** Accuracy, mean confidence, ECE and the clearing share of labelled answers at temperature T (one for all, or one per sample). */
export function measure(samples: readonly Sample[], T: number | readonly number[], minConfidence: number): CalibrationMetrics {
  const n = samples.length;
  if (n === 0) return { n: 0, accuracy: NaN, meanConfidence: NaN, ece: NaN, clearShare: NaN, clearAccuracy: NaN, nll: NaN };
  let correct = 0;
  let conf = 0;
  let clear = 0;
  let clearCorrect = 0;
  const bins = Array.from({ length: ECE_BINS }, () => ({ n: 0, conf: 0, ok: 0 }));
  let nllSum = 0;
  for (const [i, x] of samples.entries()) {
    const t = typeof T === 'number' ? T : T[i]!;
    const p = softmaxT(x.logits, t);
    const k = argmax(p);
    const ok = k === x.label ? 1 : 0;
    nllSum -= Math.log(Math.max(p[x.label]!, FLOOR));
    correct += ok;
    conf += p[k]!;
    if (p[k]! >= minConfidence) { clear++; clearCorrect += ok; }
    const b = bins[Math.min(ECE_BINS - 1, Math.floor(p[k]! * ECE_BINS))]!;
    b.n++; b.conf += p[k]!; b.ok += ok;
  }
  let ece = 0;
  for (const b of bins) if (b.n) ece += (b.n / n) * Math.abs(b.ok / b.n - b.conf / b.n);
  return { n, accuracy: correct / n, meanConfidence: conf / n, ece, clearShare: clear / n, clearAccuracy: clear ? clearCorrect / clear : NaN, nll: nllSum / n };
}

/** Deterministic split by a hash of a key: `heldOut` is the share (0 to 1) that goes to the test side. */
export function inHeldOut(key: string, heldOut: number): boolean {
  let h = 2166136261;
  for (let i = 0; i < key.length; i++) h = Math.imul(h ^ key.charCodeAt(i), 16777619);
  return ((h >>> 0) % 1000) / 1000 < heldOut;
}

export interface QuestionSamples {
  /** By signature, so that a split never puts one signature on both sides. */
  items: Array<{ key: string; sample: Sample }>;
}

export interface QuestionReport {
  question: string;
  /** Temperature that was fitted on the training side. */
  T: number;
  nTrain: number;
  nTest: number;
  /** On the held-out side: before is the raw model (T = 1), after is the fitted T. */
  before: CalibrationMetrics;
  after: CalibrationMetrics;
  /** The same two on the training side. */
  trainBefore: CalibrationMetrics;
  trainAfter: CalibrationMetrics;
}

/**
 * Fit T on the training side and report on the held-out side. With very few samples the held-out side may be empty; then the
 * training figures are the report and `nTest` is 0. The fit is repeated on all samples for the temperature that is stored
 * (more data, same method) only when `refitAll` is true.
 */
export function fitQuestion(question: string, items: QuestionSamples['items'], minConfidence: number, o: { heldOut?: number; refitAll?: boolean } = {}): QuestionReport & { Tfinal: number } {
  const share = o.heldOut ?? 0.3;
  const train = items.filter((x) => !inHeldOut(x.key, share));
  const test = items.filter((x) => inHeldOut(x.key, share));
  // Too small a side: use everything for both and say so through nTest = 0.
  const useTrain = train.length >= 3 ? train : items;
  const useTest = train.length >= 3 && test.length > 0 ? test : [];
  const fit = fitTemperature(useTrain.map((x) => x.sample));
  const evalSet = (useTest.length ? useTest : useTrain).map((x) => x.sample);
  const all = items.map((x) => x.sample);
  const Tfinal = o.refitAll ? fitTemperature(all).T : fit.T;
  return {
    question,
    T: fit.T,
    Tfinal,
    nTrain: useTrain.length,
    nTest: useTest.length,
    before: measure(evalSet, 1, minConfidence),
    after: measure(evalSet, fit.T, minConfidence),
    trainBefore: measure(useTrain.map((x) => x.sample), 1, minConfidence),
    trainAfter: measure(useTrain.map((x) => x.sample), fit.T, minConfidence),
  };
}

export interface CrossValidation {
  question: string;
  /** Number of samples, and the folds used. */
  n: number;
  folds: number;
  /** Temperature fitted on all samples (the one to ship) and the temperature of each fold (fitted on the other folds). */
  T: number;
  foldT: number[];
  /** Out-of-fold numbers: every sample is scored with a temperature that was fitted without it. */
  before: CalibrationMetrics;
  after: CalibrationMetrics;
}

/**
 * K-fold cross-validation by key (folds by a hash of the key, so a signature is on one side only). Every sample is scored with the
 * temperature fitted on the other folds, so the pooled numbers are all held out. For small label sets this is steadier than one split.
 */
export function crossValidate(question: string, items: QuestionSamples['items'], minConfidence: number, folds = 5): CrossValidation {
  const k = Math.max(2, Math.min(folds, items.length));
  const foldOf = (key: string): number => { let h = 2166136261; for (let i = 0; i < key.length; i++) h = Math.imul(h ^ key.charCodeAt(i), 16777619); return (h >>> 0) % k; };
  const fold = items.map((x) => foldOf(x.key));
  const foldT: number[] = [];
  for (let f = 0; f < k; f++) foldT.push(fitTemperature(items.filter((_, i) => fold[i] !== f).map((x) => x.sample)).T);
  const samples = items.map((x) => x.sample);
  const ts = fold.map((f) => foldT[f]!);
  return {
    question, n: items.length, folds: k, T: fitTemperature(samples).T, foldT,
    before: measure(samples, 1, minConfidence), after: measure(samples, ts, minConfidence),
  };
}

// ---------------------------------------------------------------- choosing the temperatures in use

/** A stored fit for one model id. */
export interface StoredFit {
  temperatures: Temperatures;
  /** Number of signatures behind the fit, per question. */
  n: Partial<Record<TemperatureKey, number>>;
  /** ISO date. */
  at: string;
  /** Names of the BIM model the rules labelled. */
  source: string;
  reports?: QuestionReport[];
}

export interface CalibrationChoice {
  /** The temperatures to apply, per question. Empty: the model as it comes. */
  temperatures: Temperatures;
  /** What is actually used, for the drawer: "shipped", "fitted on this model", "manual", "off", or a fallback. */
  label: string;
  /** Plain note when a requested mode could not be used. */
  note: string;
}

export interface CalibrationInputs {
  mode: CalibrationMode;
  manual: Temperatures;
  /** Shipped per-model temperatures, or none. */
  shipped: Temperatures | null;
  fitted: StoredFit | null;
  /** The temperature that the provider applies by itself (it is already in its raw scores): not used for scaling. */
}

/** Resolve the mode to the temperatures in use. `fitted` without a stored fit falls back to `auto` with a note. */
export function chooseTemperatures(c: CalibrationInputs): CalibrationChoice {
  const pickKnown = (t: Temperatures): Temperatures => {
    const o: Temperatures = {};
    for (const k of TEMPERATURE_KEYS) if (t[k] !== undefined && Number.isFinite(t[k])) o[k] = t[k]!;
    return o;
  };
  switch (c.mode) {
    case 'off':
      return { temperatures: {}, label: 'off (the model as it comes)', note: '' };
    case 'manual':
      return { temperatures: pickKnown(c.manual), label: 'manual', note: '' };
    case 'fitted':
      if (c.fitted) return { temperatures: pickKnown(c.fitted.temperatures), label: `fitted on ${c.fitted.source} (${c.fitted.at.slice(0, 10)})`, note: '' };
      return {
        temperatures: c.shipped ? pickKnown(c.shipped) : {},
        label: c.shipped ? 'shipped (no fit yet)' : 'off (no fit yet)',
        note: 'No temperatures were fitted for this model yet. Click Calibrate on rules.',
      };
    default:
      return c.shipped
        ? { temperatures: pickKnown(c.shipped), label: 'shipped', note: '' }
        : { temperatures: {}, label: 'off (no shipped numbers for this model)', note: 'This model has no shipped temperatures. Click Calibrate on rules to fit them.' };
  }
}
