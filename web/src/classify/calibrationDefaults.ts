// Shipped temperatures per model, for the calibration mode `auto`. They were fitted by bench/real-classify-decision.mjs on the
// answers that the rules label with confidence (the rules as proxy truth) in the bundled IFC models, and measured on a held-out
// share of the distinct signatures. See docs-features/classify.md, "Logit scaling", for the table behind them. A model that is not
// listed here is not scaled in `auto` mode (the honest default): fit it with "Calibrate on rules".

import type { ClassifySettings } from './settings';
import type { Temperatures } from './calibrate';

export interface ShippedFit {
  temperatures: Temperatures;
  /** Signatures behind the fit and the held-out check. */
  n: number;
  /** Where the numbers come from. */
  source: string;
}

/** Keys are model ids as providerId() writes them for the decision provider (`decision:<repo>`), and `d3` for d3-edge. */
/**
 * A temperature is shipped for a question only when, out of fold, it lowered the NLL and did not raise the ECE; otherwise the question is left at 1.
 * (The default model's discipline question, the xtremedistil discipline question, the nli-deberta division, the base v1.1 sub-discipline and division, and the d3
 * division question therefore have no shipped number.)
 */
export const SHIPPED_TEMPERATURES: Record<string, ShippedFit> = {
  'decision:MoritzLaurer/deberta-v3-xsmall-zeroshot-v1.1-all-33': { temperatures: { sub_discipline: 0.43, masterformat: 0.26, building_element: 0.08 }, n: 51, source: 'bench/real-classify-decision.mjs, 51 signatures, 5-fold cross-validation' },
  'decision:MoritzLaurer/xtremedistil-l6-h256-zeroshot-v1.1-all-33': { temperatures: { sub_discipline: 0.21, masterformat: 0.41, building_element: 0.42 }, n: 51, source: 'bench/real-classify-decision.mjs, 51 signatures, 5-fold cross-validation' },
  'decision:Xenova/nli-deberta-v3-xsmall': { temperatures: { discipline: 0.63, sub_discipline: 0.54, building_element: 0.25 }, n: 51, source: 'bench/real-classify-decision.mjs, 51 signatures, 5-fold cross-validation' },
  'decision:MoritzLaurer/deberta-v3-base-zeroshot-v1.1-all-33': { temperatures: { discipline: 0.69, building_element: 0.05 }, n: 51, source: 'bench/real-classify-decision.mjs, 51 signatures, 5-fold cross-validation' },
  'decision:MoritzLaurer/deberta-v3-base-zeroshot-v2.0': { temperatures: { discipline: 0.53, sub_discipline: 0.58, masterformat: 0.76, building_element: 0.05 }, n: 51, source: 'bench/real-classify-decision.mjs, 51 signatures, 5-fold cross-validation' },
  'd3': { temperatures: { discipline: 1.53, sub_discipline: 1.36, building_element: 0.43 }, n: 51, source: 'bench/real-classify-decision.mjs, 51 signatures, 5-fold cross-validation' },
};

/** The shipped temperatures for the model in use, or null. d3-edge has one set for both backends (same weights). */
export function shippedFor(s: ClassifySettings): Temperatures | null {
  const id = s.provider === 'decision' ? `decision:${s.hfModel}` : s.provider === 'd3' ? 'd3' : null;
  const hit = id ? SHIPPED_TEMPERATURES[id] : undefined;
  return hit ? { ...hit.temperatures } : null;
}
