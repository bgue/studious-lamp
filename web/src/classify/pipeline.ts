// The decision pipeline, cheapest step first: deterministic rules, the signature cache, then the decision model with one
// request per signature (plus one for the sub-discipline). Pure TypeScript, no DOM: runs in Node and in the browser.

import { Q_BUILDING, Q_DISCIPLINE, Q_MASTERFORMAT, Q_SUB, COMBINED_SEP, mainQuestions, subQuestions } from './questions';
import { readChoice, readNoul } from './jevAdapter';
import type { Answers, ChoiceAnswer } from './jevAdapter';
import { MemoryCache } from './cache';
import { answersFromRaw, calibrateAnswers, isIdentity, rawOfAnswers } from './calibrate';
import type { Temperatures } from './calibrate';
import type { CachedDecision, SignatureCache } from './cache';
import { classByRules, isBuildingContext, resolveRule, RULE_FINAL } from './rules';
import type { Decision } from './rules';
import { isAbort, withBackoff } from './retry';
import type { RetryOptions } from './retry';
import { computeNeedsReview, DEFAULT_MIN_MARGIN } from './review';
import { divisionTitle, masterformatBuildingOnly } from './schema';
import { buildState, DEFAULT_MAX_STATE_BYTES, signatureOf } from './state';
import { ProviderError } from './types';
import type { ChoiceResult, ClassificationSchema, ClassifyInput, ClassifyResult, ClassifyStats, DecideExtra, DecisionModel, ProgressInfo, ResultSource } from './types';

// ---------------------------------------------------------------- sub-discipline strategy

/** Which disciplines' sub-codes the sub-discipline question covers. Pluggable. */
export type SubDisciplineStrategy = (schema: ClassificationSchema, discipline: ChoiceResult, minConfidence: number) => string[];

/** The chosen discipline only. */
export const subOfTop: SubDisciplineStrategy = (_s, d) => [d.code];

/** The chosen discipline; when its confidence is below the limit, the top 2 disciplines together. The default. */
export const subOfTop2WhenUnsure: SubDisciplineStrategy = (_s, d, minConfidence) => {
  if (d.confidence >= minConfidence) return [d.code];
  const second = Object.entries(d.probabilities).filter(([c]) => c !== d.code).sort((a, b) => b[1] - a[1])[0];
  return second && second[1] > 0 ? [d.code, second[0]] : [d.code];
};

export const SUB_STRATEGIES = { top: subOfTop, 'top2-when-unsure': subOfTop2WhenUnsure } as const;

// ---------------------------------------------------------------- options

export interface ClassifyRunOptions {
  schema: ClassificationSchema;
  /** The decision model. Null: rules and cache only. */
  provider?: DecisionModel | null;
  /** Default: the schema's. */
  minConfidence?: number;
  minMargin?: number;
  /** false: skip the rules (every element goes to the cache and the model). Default true. */
  rules?: boolean;
  /** A rule at or above this confidence is final. Default RULE_FINAL. */
  ruleFinal?: number;
  cache?: SignatureCache;
  /** Results that win over everything else, by element id. */
  manual?: ReadonlyMap<string, ClassifyResult>;
  concurrency?: number;
  maxStateBytes?: number;
  subDiscipline?: SubDisciplineStrategy;
  /**
   * Temperatures of the logit scaling, per question (see calibrate.ts). Applied when a decision is read, from the raw scores
   * in the cache; the ranking never changes, only the probabilities. Empty or all 1: the model as it comes.
   */
  temperatures?: Temperatures;
  /**
   * Pictures of the representative element of a signature (base64 data URLs), sent with both requests to a provider that reads
   * images. A failure is not fatal: the request goes out with the text alone and the message is added to `stats.errors`.
   */
  images?: (input: ClassifyInput, signal: AbortSignal) => Promise<PictureSet | readonly string[]> | PictureSet | readonly string[];
  /**
   * Native vector geometry of the representative element as SVG text (geometrySvg.ts): it goes into the state as `geometry`, with the one-line legend first.
   * A failure is not fatal: the request goes out without it and the message is added to `stats.errors`.
   */
  geometry?: (input: ClassifyInput, signal: AbortSignal) => Promise<{ legend: string; svg: string } | null> | { legend: string; svg: string } | null;
  retry?: RetryOptions;
  signal?: AbortSignal;
  onProgress?: (p: ProgressInfo) => void;
}

/** The pictures of an element, and the note that tells the model what they are (it goes into the state as `pictures`). */
export interface PictureSet {
  images: readonly string[];
  note?: string;
}

export interface ClassifyRun {
  results: ClassifyResult[];
  stats: ClassifyStats;
}

const emptyBySource = (): Record<ResultSource, number> => ({ rules: 0, cache: 0, model: 0, manual: 0 });

// ---------------------------------------------------------------- building results

const choice = (schema: ClassificationSchema, code: string, confidence: number, probabilities: Record<string, number>): ChoiceResult => ({
  code, label: schema.disciplines.find((d) => d.code === code)?.label ?? code, confidence, probabilities,
});

/** The decision that a (final or weak) rule gives, as a cacheable decision. */
function fromRule(schema: ClassificationSchema, d: Decision, building: boolean): CachedDecision {
  const disc = schema.disciplines.find((x) => x.code === d.discipline)!;
  const sub = d.subDiscipline ? disc.subDisciplines.find((s) => s.code === d.subDiscipline) : undefined;
  const title = d.division ? divisionTitle(schema, d.division) : undefined;
  return {
    discipline: { code: disc.code, label: disc.label, confidence: d.confidence, probabilities: { [disc.code]: d.confidence } },
    subDiscipline: sub ? { code: sub.code, label: sub.label, confidence: d.confidence, probabilities: { [sub.code]: d.confidence } } : null,
    masterformat: d.division && title ? { division: d.division, title, confidence: d.confidence, probabilities: { [d.division]: d.confidence }, ...(d.section ? { section: d.section } : {}) } : null,
    buildingElement: building ? 1 : 0,
    rationale: d.rationale,
  };
}

function finish(id: string, d: CachedDecision, source: ResultSource, minConfidence: number, minMargin: number, signature?: string, forceReview = false): ClassifyResult {
  const { raw: _raw, ...plain } = d;
  const r: ClassifyResult = { id, ...plain, source, needsReview: false, ...(signature ? { signature } : {}) };
  if (source !== 'model' && source !== 'cache') delete r.model;
  r.needsReview = forceReview || computeNeedsReview(r, minConfidence, minMargin);
  return r;
}

// ---------------------------------------------------------------- decoding the answers of the model

/** Turn the answers of the two requests into a decision, checking every code against the schema. Throws ProviderError. */
export function decodeAnswers(schema: ClassificationSchema, main: Answers, sub: Answers | null, subCodes: readonly string[]): CachedDecision {
  const dAns = readChoice(main, Q_DISCIPLINE);
  if (!schema.disciplines.some((d) => d.code === dAns.choice)) throw new ProviderError(`The model chose the discipline "${dAns.choice}", which is not in the schema.`);
  let discipline = choice(schema, dAns.choice, dAns.confidence, dAns.probabilities);
  const building = readNoul(main, Q_BUILDING);

  let masterformat: CachedDecision['masterformat'] = null;
  if (!masterformatBuildingOnly(schema) || building >= 0.5) {
    const m = readChoice(main, Q_MASTERFORMAT);
    const title = divisionTitle(schema, m.choice);
    if (!title) throw new ProviderError(`The model chose the division "${m.choice}", which is not in the schema.`);
    masterformat = { division: m.choice, title, confidence: m.confidence, probabilities: m.probabilities };
  }

  let subDiscipline: ChoiceResult | null = null;
  if (sub) {
    const s: ChoiceAnswer = readChoice(sub, Q_SUB);
    const combined = subCodes.length > 1;
    const [dCode, sCode] = combined ? s.choice.split(COMBINED_SEP) : [discipline.code, s.choice];
    const d = schema.disciplines.find((x) => x.code === dCode);
    const sd = d?.subDisciplines.find((x) => x.code === sCode);
    if (!d || !sd) throw new ProviderError(`The model chose the sub-discipline "${s.choice}", which is not in the schema.`);
    if (d.code !== discipline.code) {
      // The sub-discipline question saw the top 2 disciplines together and picked one of the runner-up: it breaks the tie.
      discipline = choice(schema, d.code, dAns.probabilities[d.code] ?? 0, dAns.probabilities);
    }
    // Probabilities of the sub-codes of the final discipline only, by plain sub code.
    const probabilities: Record<string, number> = {};
    for (const [k, p] of Object.entries(s.probabilities)) {
      const [kd, ks] = combined ? k.split(COMBINED_SEP) : [d.code, k];
      if (kd === d.code && ks) probabilities[ks] = p;
    }
    subDiscipline = { code: sd.code, label: sd.label, confidence: s.confidence, probabilities };
  } else {
    const d = schema.disciplines.find((x) => x.code === discipline.code)!;
    if (d.subDisciplines.length === 1) subDiscipline = { code: d.subDisciplines[0]!.code, label: d.subDisciplines[0]!.label, confidence: 1, probabilities: { [d.subDisciplines[0]!.code]: 1 } };
  }
  const models = [main.model, ...(sub && sub.model !== main.model ? [sub.model] : [])];
  return { discipline, subDiscipline, masterformat, buildingElement: building, model: models.join('+') };
}

/**
 * A cached decision at the given temperatures. A decision with raw scores is decoded again from them (the same code path as a
 * fresh answer, so tie-breaks and the building check follow the scaled probabilities); one without (a rule, or an entry from
 * before calibration) is returned as it is. With no scaling the stored decision is returned untouched.
 */
export function rescoreDecision(schema: ClassificationSchema, d: CachedDecision, temps: Temperatures | undefined): CachedDecision {
  if (!d.raw || isIdentity(temps)) return d;
  try {
    const main = answersFromRaw(d.raw.main, temps);
    const sub = d.raw.sub ? answersFromRaw(d.raw.sub, temps) : null;
    return { ...decodeAnswers(schema, main, sub, d.raw.subCodes), raw: d.raw };
  } catch {
    return d;
  }
}

/**
 * A stored result at the given temperatures, for a result that came from the model or the cache. Returns the result itself when
 * nothing changes (no raw scores, or no scaling that differs). The review flag follows the new confidences.
 */
export function rescoreResult(schema: ClassificationSchema, r: ClassifyResult, cached: CachedDecision | undefined, temps: Temperatures | undefined, minConfidence: number, minMargin = DEFAULT_MIN_MARGIN): ClassifyResult {
  if (!cached?.raw || (r.source !== 'model' && r.source !== 'cache')) return r;
  const d = rescoreDecision(schema, cached, temps);
  const { raw: _raw, ...plain } = d;
  const next: ClassifyResult = { ...r, ...plain, id: r.id, source: r.source, needsReview: false };
  next.needsReview = computeNeedsReview(next, minConfidence, minMargin);
  return next;
}

// ---------------------------------------------------------------- estimate

export interface CallEstimate {
  elements: number;
  manual: number;
  byRules: number;
  /** Elements whose signature is already cached. */
  cached: number;
  /** Distinct signatures that need the model. */
  signatures: number;
  /** Requests: up to 2 per signature (discipline and the rest, then the sub-discipline). */
  calls: number;
  callsMin: number;
}

export function estimateCalls(inputs: readonly ClassifyInput[], o: Pick<ClassifyRunOptions, 'schema' | 'cache' | 'rules' | 'ruleFinal' | 'manual'>): CallEstimate {
  const e: CallEstimate = { elements: inputs.length, manual: 0, byRules: 0, cached: 0, signatures: 0, calls: 0, callsMin: 0 };
  const seen = new Set<string>();
  for (const i of inputs) {
    if (o.manual?.has(i.id)) { e.manual++; continue; }
    if (o.rules !== false) {
      const h = classByRules(i);
      if (h && h.confidence >= (o.ruleFinal ?? RULE_FINAL) && resolveRule(h, o.schema, isBuildingContext(i))) { e.byRules++; continue; }
    }
    const sig = signatureOf(i);
    if (o.cache?.get(sig)) { e.cached++; continue; }
    seen.add(sig);
  }
  e.signatures = seen.size;
  e.callsMin = seen.size;
  e.calls = seen.size * 2;
  return e;
}

// ---------------------------------------------------------------- run

export async function classifyInputs(inputs: readonly ClassifyInput[], o: ClassifyRunOptions): Promise<ClassifyRun> {
  const schema = o.schema;
  const minConfidence = o.minConfidence ?? schema.minConfidence;
  const minMargin = o.minMargin ?? DEFAULT_MIN_MARGIN;
  const cache = o.cache ?? new MemoryCache();
  const strategy = o.subDiscipline ?? subOfTop2WhenUnsure;
  const ctl = new AbortController();
  const stop = (): void => ctl.abort();
  if (o.signal?.aborted) ctl.abort();
  else o.signal?.addEventListener('abort', stop, { once: true });
  const signal = ctl.signal;

  const stats: ClassifyStats = { total: inputs.length, bySource: emptyBySource(), calls: 0, signatures: 0, needsReview: 0, failed: 0, aborted: false, errors: [], models: {}, usage: { input_tokens: 0, output_tokens: 0 } };
  const out = new Map<string, ClassifyResult>();
  const addError = (m: string): void => { if (stats.errors.length < 20 && !stats.errors.includes(m)) stats.errors.push(m); };
  let planned = 0;
  const progress = (phase: ProgressInfo['phase']): void =>
    o.onProgress?.({ phase, total: inputs.length, done: out.size, bySource: { ...stats.bySource }, calls: stats.calls, callsPlanned: planned });
  const put = (r: ClassifyResult): void => {
    out.set(r.id, r);
    stats.bySource[r.source]++;
    if (r.needsReview) stats.needsReview++;
  };

  // 1. manual and rules
  const rest: Array<{ input: ClassifyInput; sig: string; weak: CachedDecision | null; building: boolean }> = [];
  for (const i of inputs) {
    const m = o.manual?.get(i.id);
    if (m) { put(m); continue; }
    const building = isBuildingContext(i);
    let weak: CachedDecision | null = null;
    if (o.rules !== false) {
      const h = classByRules(i);
      const d = h ? resolveRule(h, schema, building) : null;
      if (d) {
        const cd = fromRule(schema, d, building);
        if (d.confidence >= (o.ruleFinal ?? RULE_FINAL)) { put(finish(i.id, cd, 'rules', minConfidence, minMargin)); continue; }
        weak = cd;
      }
    }
    rest.push({ input: i, sig: signatureOf(i), weak, building });
  }
  progress('rules');

  // 2. cache
  const todo = new Map<string, typeof rest>();
  for (const r of rest) {
    const hit = cache.get(r.sig);
    if (hit) { put(finish(r.input.id, rescoreDecision(schema, hit, o.temperatures), 'cache', minConfidence, minMargin, r.sig)); continue; }
    const l = todo.get(r.sig);
    if (l) l.push(r);
    else todo.set(r.sig, [r]);
  }
  progress('cache');

  // 3. the model, one signature at a time (concurrently)
  stats.signatures = todo.size;
  planned = o.provider ? todo.size : 0;
  const fallback = (members: typeof rest, why: string): void => {
    for (const m of members) {
      if (m.weak) put(finish(m.input.id, m.weak, 'rules', minConfidence, minMargin, undefined, true));
      else stats.failed++;
    }
    addError(why);
  };
  if (!o.provider) {
    for (const members of todo.values()) fallback(members, 'No decision model is set, so elements without a final rule were not classified.');
  } else {
    const provider = o.provider;
    const queue = [...todo.entries()];
    let next = 0;
    const call = async (state: ReturnType<typeof buildState>, questions: ReturnType<typeof mainQuestions>, extra?: DecideExtra): Promise<Answers> => {
      stats.calls++;
      progress('model');
      const a = await withBackoff(() => provider.decide(state, questions, signal, extra), signal, o.retry);
      stats.models[a.model] = (stats.models[a.model] ?? 0) + 1;
      stats.usage.input_tokens += a.usage?.input_tokens ?? 0;
      stats.usage.output_tokens += a.usage?.output_tokens ?? 0;
      return a;
    };
    const worker = async (): Promise<void> => {
      for (;;) {
        if (signal.aborted) return;
        const entry = queue[next++];
        if (!entry) return;
        const [sig, members] = entry;
        const rep = members[0]!.input;
        try {
          let state = buildState(rep, o.maxStateBytes ?? DEFAULT_MAX_STATE_BYTES);
          let extra: DecideExtra | undefined;
          if (o.geometry) {
            try {
              const g = await o.geometry(rep, signal);
              // One line (a newline would be escaped in the JSON state, which costs tokens); the legend comes first.
              if (g) state = { geometry: `${g.legend} ${g.svg.replace(/\n/g, ' ')}`, ...state };
            } catch (e) {
              if (isAbort(e) || signal.aborted) return;
              addError(`The geometry of an element could not be made, so it went out without it: ${e instanceof Error ? e.message : String(e)}`);
            }
          }
          if (o.images) {
            try {
              const got = await o.images(rep, signal);
              const set: PictureSet = Array.isArray(got) ? { images: got as readonly string[] } : (got as PictureSet);
              if (set.images.length) {
                extra = { images: set.images };
                // The pictures come before the text in the prompt, so the note goes first in the state. It is short and not part of the byte cap.
                if (set.note) state = { pictures: set.note, ...state };
              }
            } catch (e) {
              if (isAbort(e) || signal.aborted) return;
              addError(`Pictures of an element could not be made, so it went out as text only: ${e instanceof Error ? e.message : String(e)}`);
            }
          }
          const main = await call(state, mainQuestions(schema), extra);
          // Check the discipline now: the sub-discipline question depends on it.
          // The sub-discipline strategy sees the scaled confidence: a sharper discipline needs fewer options in the second request.
          const dAns = readChoice(calibrateAnswers(main, o.temperatures), Q_DISCIPLINE);
          const dChoice = schema.disciplines.some((d) => d.code === dAns.choice) ? choice(schema, dAns.choice, dAns.confidence, dAns.probabilities) : null;
          if (!dChoice) throw new ProviderError(`The model chose the discipline "${dAns.choice}", which is not in the schema.`);
          const codes = strategy(schema, dChoice, minConfidence).filter((c) => schema.disciplines.some((d) => d.code === c));
          const sq = subQuestions(schema, codes.length ? codes : [dChoice.code]);
          const subAns = sq ? await call(state, sq, extra) : null;
          const subCodes = codes.length ? codes : [dChoice.code];
          // Stored as the model gave it, with the raw scores; the temperatures apply when the decision is read.
          const decision: CachedDecision = { ...decodeAnswers(schema, main, subAns, subCodes), raw: { main: rawOfAnswers(main), sub: subAns ? rawOfAnswers(subAns) : null, subCodes } };
          cache.set(sig, decision);
          const shown = rescoreDecision(schema, decision, o.temperatures);
          members.forEach((m, k) => put(finish(m.input.id, shown, k === 0 ? 'model' : 'cache', minConfidence, minMargin, sig)));
          progress('model');
        } catch (e) {
          if (isAbort(e) || signal.aborted) return;
          fallback(members, e instanceof Error ? e.message : String(e));
        }
      }
    };
    const n = Math.max(1, Math.min(o.concurrency ?? 4, queue.length || 1));
    await Promise.all(Array.from({ length: n }, () => worker()));
  }
  stats.aborted = signal.aborted;
  o.signal?.removeEventListener('abort', stop);
  cache.flush();
  progress('done');
  const results = inputs.map((i) => out.get(i.id)).filter((r): r is ClassifyResult => !!r);
  return { results, stats };
}
