// When does a result need a person to look at it?

import type { ChoiceResult, ClassifyResult } from './types';

/** Two choices closer than this need review, even when the top one is above the confidence limit. */
export const DEFAULT_MIN_MARGIN = 0.15;
/** A yes/no probability inside 0.5 plus or minus this is undecided. */
export const BUILDING_UNDECIDED = 0.15;

/** Probability of the top option minus that of the second option (the top one alone: its own probability). */
export function topMargin(probabilities: Record<string, number>): number {
  const v = Object.values(probabilities).sort((a, b) => b - a);
  if (v.length === 0) return 0;
  return v[0]! - (v[1] ?? 0);
}

/** The two most probable options, best first. */
export function topTwo(probabilities: Record<string, number>): Array<[string, number]> {
  return Object.entries(probabilities).sort((a, b) => b[1] - a[1]).slice(0, 2);
}

const weak = (c: { confidence: number; probabilities: Record<string, number> }, minConfidence: number, minMargin: number): boolean =>
  c.confidence < minConfidence || topMargin(c.probabilities) < minMargin;

/** The part of a result that the review depends on. */
export type Reviewable = Pick<ClassifyResult, 'discipline' | 'subDiscipline' | 'masterformat' | 'buildingElement'>;

/** True when any confidence is below `minConfidence`, any top-2 margin is below `minMargin`, or the building answer is undecided. */
export function computeNeedsReview(r: Reviewable, minConfidence: number, minMargin = DEFAULT_MIN_MARGIN): boolean {
  if (weak(r.discipline, minConfidence, minMargin)) return true;
  if (r.subDiscipline && weak(r.subDiscipline as ChoiceResult, minConfidence, minMargin)) return true;
  if (r.masterformat && weak(r.masterformat, minConfidence, minMargin)) return true;
  return Math.abs(r.buildingElement - 0.5) < BUILDING_UNDECIDED;
}

/** The lowest confidence among the parts that are present: the figure written to the Confidence property. */
export function overallConfidence(r: Reviewable): number {
  const v = [r.discipline.confidence];
  if (r.subDiscipline) v.push(r.subDiscipline.confidence);
  if (r.masterformat) v.push(r.masterformat.confidence);
  return Math.round(Math.min(...v) * 100) / 100;
}
