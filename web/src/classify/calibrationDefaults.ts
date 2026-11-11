// Shipped temperatures per model, for the calibration mode `auto`. Two sources:
//  - the three models of the truth bench (deberta xsmall v1.1, deberta base v2.0, d3-edge) were re-checked and refitted against the design-intent
//    truth of the synthetic process plant (models/Process-Plant.truth.json) by bench/fit-truth-temperatures.mjs: 114 signatures, 1294 elements,
//    5-fold cross-validation BY SIGNATURE (seed 20240611), weighted by element count (the signature-weighted pass must not contradict). ONE SYNTHETIC
//    PLANT: the numbers are a measurement on one generated unit, not a general result;
//  - the other models still carry the numbers that bench/real-classify-decision.mjs fitted on the answers that the rules label (the rules as proxy
//    truth) in the bundled IFC models, 5-fold cross-validation on 51 signatures. See docs-features/classify.md, "Logit scaling".
// A model that is not listed here is not scaled in `auto` mode (the honest default): fit it with "Calibrate on rules".

import type { ClassifySettings } from './settings';
import type { Temperatures } from './calibrate';

export interface ShippedFit {
  temperatures: Temperatures;
  /** Signatures behind the fit and the held-out check. */
  n: number;
  /** Where the numbers come from. */
  source: string;
  /** Per question, where this number came from and the out-of-fold figures behind it (the truth-bench models only). */
  detail?: Partial<Record<keyof Temperatures, string>>;
}

/** Keys are model ids as providerId() writes them for the decision provider (`decision:<repo>`), and `d3` for d3-edge. */
/**
 * A temperature is shipped for a question only when, out of fold, it lowered the NLL and did not raise the ECE; otherwise the question is left at 1.
 * (The default model's sub-discipline and division, the xtremedistil discipline question, the nli-deberta division, the base v1.1 sub-discipline and division, the base v2.0
 * division and the d3 discipline and division questions therefore have no shipped number.) For the three models of the truth bench the test ran on the process-plant truth;
 * a value fitted on rule labels is kept only when it still beats T = 1 there.
 */
export const SHIPPED_TEMPERATURES: Record<string, ShippedFit> = {
  'decision:MoritzLaurer/deberta-v3-xsmall-zeroshot-v1.1-all-33': {
    temperatures: { discipline: 1.49, building_element: 0.08 },
    n: 114,
    source: 'discipline: truth fit on process-plant (bench/fit-truth-temperatures.mjs); building_element: rule labels (bench/real-classify-decision.mjs, 51 signatures); sub_discipline and masterformat have no shipped number',
    detail: {
      discipline: 'truth fit on process-plant, 114 signatures / 1294 elements, 5-fold by signature, out of fold NLL 2.315 -> 2.296, ECE 0.317 -> 0.221 (no shipped number before; the question is 2% right at the top option, so no answer clears 0.6 either way)',
      sub_discipline: 'dropped: the rule-label value 0.43 was worse than T = 1 on the truth (NLL 1.824 vs 1.703, ECE 0.352 vs 0.149), and the truth fit (T 0.79) raised the ECE out of fold (0.215 vs 0.149)',
      masterformat: 'dropped: the rule-label value 0.26 was worse than T = 1 on the truth (NLL 3.431 vs 3.220, ECE 0.223 vs 0.122), and the truth fit (T 0.51) raised the ECE out of fold (0.171 vs 0.122)',
      building_element: 'rule labels (51 signatures, 5-fold); not re-checked: the truth file has no building flag',
    },
  },
  'decision:MoritzLaurer/xtremedistil-l6-h256-zeroshot-v1.1-all-33': { temperatures: { sub_discipline: 0.21, masterformat: 0.41, building_element: 0.42 }, n: 51, source: 'bench/real-classify-decision.mjs, 51 signatures, 5-fold cross-validation' },
  'decision:Xenova/nli-deberta-v3-xsmall': { temperatures: { discipline: 0.63, sub_discipline: 0.54, building_element: 0.25 }, n: 51, source: 'bench/real-classify-decision.mjs, 51 signatures, 5-fold cross-validation' },
  'decision:MoritzLaurer/deberta-v3-base-zeroshot-v1.1-all-33': { temperatures: { discipline: 0.69, building_element: 0.05 }, n: 51, source: 'bench/real-classify-decision.mjs, 51 signatures, 5-fold cross-validation' },
  'decision:MoritzLaurer/deberta-v3-base-zeroshot-v2.0': {
    temperatures: { discipline: 0.53, sub_discipline: 0.58, building_element: 0.05 },
    n: 114,
    source: 'discipline and sub_discipline: rule-label values kept after a check on the process-plant truth (bench/fit-truth-temperatures.mjs); building_element: rule labels (51 signatures); masterformat has no shipped number',
    detail: {
      discipline: 'rule-label value 0.53 kept: on the truth it beats T = 1 (NLL 1.103 vs 1.153, ECE 0.229 vs 0.330) and the truth fit does not beat it out of fold (T 0.68; NLL 1.111, ECE 0.256)',
      sub_discipline: 'rule-label value 0.58 kept: on the truth it beats T = 1 (NLL 1.244 vs 1.372, ECE 0.147 vs 0.193) and the truth fit does not beat it out of fold (T 0.46; NLL 1.278, ECE 0.086, a lower ECE but a higher NLL)',
      masterformat: 'dropped: the rule-label value 0.76 was worse than T = 1 on the truth (NLL 2.723 vs 2.687, ECE 0.285 vs 0.272), and the truth fit (T 0.94) did not beat T = 1 out of fold',
      building_element: 'rule labels (51 signatures, 5-fold); not re-checked: the truth file has no building flag',
    },
  },
  'd3': {
    temperatures: { sub_discipline: 1.99, building_element: 0.43 },
    n: 114,
    source: 'sub_discipline: truth fit on process-plant (bench/fit-truth-temperatures.mjs); building_element: rule labels (51 signatures); discipline and masterformat have no shipped number',
    detail: {
      discipline: 'dropped: the rule-label value 1.53 made d3 under-confident on the truth (NLL 0.994 vs 0.869 at T = 1, ECE 0.245 vs 0.108; 25% of the elements clear 0.6 against 54%), and the truth fit (T 0.91) did not beat T = 1 out of fold (NLL 0.893, ECE 0.121)',
      sub_discipline: 'truth fit on process-plant, 113 signatures / 1293 elements, 5-fold by signature, T 1.99; out of fold NLL 1.239 -> 0.952 against T = 1 and 1.003 against the old 1.36, ECE 0.246 -> 0.151 (old 1.36: 0.200)',
      masterformat: 'no shipped number: the truth fit (T 0.92) did not beat T = 1 out of fold (NLL 2.177 vs 2.172, ECE 0.191 vs 0.168)',
      building_element: 'rule labels (51 signatures, 5-fold); not re-checked: the truth file has no building flag',
    },
  },
};

/** The shipped temperatures for the model in use, or null. d3-edge has one set for both backends (same weights). */
export function shippedFor(s: ClassifySettings): Temperatures | null {
  const id = s.provider === 'decision' ? `decision:${s.hfModel}` : s.provider === 'd3' ? 'd3' : null;
  const hit = id ? SHIPPED_TEMPERATURES[id] : undefined;
  return hit ? { ...hit.temperatures } : null;
}
