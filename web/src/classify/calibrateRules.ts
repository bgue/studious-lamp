// "Calibrate on rules": fit one temperature per question on the elements that the rules labelled, with the rules as proxy truth, and
// report before and after on a held-out share. Pure TypeScript, no DOM. The raw scores come from the result cache (they are stored
// there with every model decision), so the model runs once per signature and a refit never runs it again.

import { fitQuestion } from './calibrate';
import type { QuestionReport, Sample, StoredFit, Temperatures, TemperatureKey } from './calibrate';
import type { CachedDecision } from './cache';
import { COMBINED_SEP, Q_BUILDING, Q_DISCIPLINE, Q_MASTERFORMAT, Q_SUB } from './questions';
import { classByRules, isBuildingContext, resolveRule, RULE_FINAL } from './rules';
import { signatureOf } from './state';
import { inHeldOut } from './calibrate';
import type { ClassificationSchema, ClassifyInput } from './types';

/** What a final rule says about a signature. */
export interface RuleTruth {
  signature: string;
  input: ClassifyInput;
  discipline: string;
  subDiscipline: string | null;
  division: string | null;
  building: boolean;
}

/** One truth per distinct signature, from the elements that a FINAL rule decides (the rules as proxy labels). Order: first seen. */
export function ruleTruths(inputs: readonly ClassifyInput[], schema: ClassificationSchema): RuleTruth[] {
  const seen = new Map<string, RuleTruth>();
  for (const i of inputs) {
    const h = classByRules(i);
    if (!h || h.confidence < RULE_FINAL) continue;
    const building = isBuildingContext(i);
    const d = resolveRule(h, schema, building);
    if (!d) continue;
    const sig = signatureOf(i);
    if (!seen.has(sig)) seen.set(sig, { signature: sig, input: i, discipline: d.discipline, subDiscipline: d.subDiscipline, division: d.division, building });
  }
  return [...seen.values()];
}

/** At most `n` truths, chosen by a hash of the signature (the same choice every time, spread over the classes). */
export function pickTruths(all: readonly RuleTruth[], n: number): RuleTruth[] {
  if (all.length <= n) return [...all];
  const h = (s: string): number => { let x = 2166136261; for (let i = 0; i < s.length; i++) x = Math.imul(x ^ s.charCodeAt(i), 16777619); return x >>> 0; };
  return [...all].sort((a, b) => h(a.signature) - h(b.signature)).slice(0, n);
}

export type SampleSets = Record<TemperatureKey, Array<{ key: string; sample: Sample }>>;

/** Labelled samples per question from the cached raw scores of the truths. A truth without raw scores gives none. */
export function collectSamples(truths: readonly RuleTruth[], decisionOf: (signature: string) => CachedDecision | undefined): SampleSets {
  const out: SampleSets = { [Q_DISCIPLINE]: [], [Q_SUB]: [], [Q_MASTERFORMAT]: [], [Q_BUILDING]: [] };
  for (const t of truths) {
    const raw = decisionOf(t.signature)?.raw;
    if (!raw) continue;
    const choice = (q: { logits: Record<string, number> } | { logit: number } | undefined, wanted: string | null): Sample | null => {
      if (!q || !('logits' in q) || wanted === null) return null;
      const keys = Object.keys(q.logits);
      const label = keys.indexOf(wanted);
      return label < 0 ? null : { logits: keys.map((k) => q.logits[k]!), label };
    };
    const d = choice(raw.main.questions[Q_DISCIPLINE], t.discipline);
    if (d) out[Q_DISCIPLINE].push({ key: t.signature, sample: d });
    const m = choice(raw.main.questions[Q_MASTERFORMAT], t.division);
    if (m) out[Q_MASTERFORMAT].push({ key: t.signature, sample: m });
    if (raw.sub && t.subDiscipline) {
      const combined = raw.subCodes.length > 1;
      const s = choice(raw.sub.questions[Q_SUB], combined ? `${t.discipline}${COMBINED_SEP}${t.subDiscipline}` : t.subDiscipline);
      if (s) out[Q_SUB].push({ key: t.signature, sample: s });
    }
    const b = raw.main.questions[Q_BUILDING];
    if (b && 'logit' in b) out[Q_BUILDING].push({ key: t.signature, sample: { logits: [0, b.logit], label: t.building ? 1 : 0 } });
  }
  return out;
}

export interface CalibrationReport {
  modelId: string;
  /** Source of the labels: the BIM model name. */
  source: string;
  at: string;
  minConfidence: number;
  /** Distinct signatures that the rules labelled in this model, and how many of them had raw scores. */
  signatures: number;
  scored: number;
  questions: QuestionReport[];
  temperatures: Temperatures;
}

/** Fit every question that has enough samples (at least 4) and report held-out numbers. */
export function fitFromSamples(sets: SampleSets, o: { modelId: string; source: string; minConfidence: number; signatures: number; scored: number; heldOut?: number; now?: Date }): CalibrationReport {
  const questions: QuestionReport[] = [];
  const temperatures: Temperatures = {};
  for (const q of Object.keys(sets) as TemperatureKey[]) {
    const items = sets[q];
    if (items.length < 4) continue;
    const r = fitQuestion(q, items, o.minConfidence, { heldOut: o.heldOut ?? 0.3, refitAll: true });
    questions.push(r);
    temperatures[q] = Math.round(r.Tfinal * 1000) / 1000;
  }
  return { modelId: o.modelId, source: o.source, at: (o.now ?? new Date()).toISOString(), minConfidence: o.minConfidence, signatures: o.signatures, scored: o.scored, questions, temperatures };
}

export function toStoredFit(r: CalibrationReport): StoredFit {
  const n: StoredFit['n'] = {};
  for (const q of r.questions) n[q.question as TemperatureKey] = q.nTrain + q.nTest;
  return { temperatures: r.temperatures, n, at: r.at, source: r.source, reports: r.questions };
}

/** Is the signature on the held-out side? (the same split that fitQuestion uses) */
export const isHeldOut = (signature: string, share = 0.3): boolean => inHeldOut(signature, share);
