// The facets engine: for a list of elements, the value of every facet, cheapest source first.
//   1. Orientation: measured from the geometry (no rule, no model).
//   2. In dependency order Material, Placement, Trade, Phase, ClassRepair: manual choice, then the rules (final at 0.85 and up), then
//      the facet cache, then ONE question per facet per signature to the decision model (the same providers, calibration and review
//      threshold as the discipline). A weak rule is the fallback when there is no model or the model fails.
// A facet that is switched off is still ruled (a later facet may need its value) but never asked of the model and not returned.
// Pure TypeScript, no DOM: runs in Node and in the browser. Docs: docs-features/classify.md, "Facets".

import { answersFromRaw, rawOfAnswers } from '../calibrate';
import type { RawAnswers, Temperatures } from '../calibrate';
import { choiceQuestion, noulQuestion, readChoice, readNoul } from '../jevAdapter';
import type { Answers, ChoiceAnswer, Questions } from '../jevAdapter';
import { DEFAULT_MIN_MARGIN, topMargin } from '../review';
import { isAbort, withBackoff } from '../retry';
import type { RetryOptions } from '../retry';
import { facetDefs } from '../schema';
import { buildState, DEFAULT_MAX_STATE_BYTES, signatureOf } from '../state';
import { ProviderError } from '../types';
import type { ClassificationSchema, ClassifyInput, DecisionModel } from '../types';
import { facetLabel, FACET_IDS, FACETS_VERSION, MODEL_FACETS } from './defs';
import type { FacetDef, FacetDefs, FacetFieldValue, FacetId, FacetResult, FacetSet, FacetSource } from './defs';
import {
  classRepairRule, FACET_RULE_FINAL, isGenericClass, loadBearingRule, materialRule, phaseRule, placementRule, predefinedOf, tradeRule,
} from './facetRules';
import type { FacetContext, RuleOut } from './facetRules';
import { orientationPlausible } from './orientation';
import type { OrientationMeasure } from './orientation';
import type { PlacementGeo } from './placementGeometry';

// ---------------------------------------------------------------- questions

export const Q_FACET: Record<Exclude<FacetId, 'Orientation'>, string> = {
  Trade: 'facet_trade',
  Placement: 'facet_placement',
  Material: 'facet_material',
  Phase: 'facet_phase',
  ClassRepair: 'facet_classrepair',
};
export const Q_LOAD_BEARING = 'facet_loadbearing';

const INSTRUCTIONS: Record<Exclude<FacetId, 'Orientation'>, string> = {
  Trade: 'Choose the trade (the work package) that builds this BIM element. Decide from its IFC class, name, type, material, discipline and the facets already known.',
  Placement: 'Choose where this BIM element sits: outside the building, inside it, or on the building envelope (weather on one side, the building on the other).',
  Material: 'Choose the material that this BIM element is mainly made of. Decide from its material, type name, name and properties.',
  Phase: 'Choose the phase of the construction job in which this BIM element is built. Decide from its trade, placement, class and level.',
  ClassRepair: 'This BIM element has a generic or doubtful IFC class. Choose the IFC class that describes it best, or KEEP when its class is right or no better class is known. Decide from its name, type name and shape.',
};

/** The options of a facet question: every code of the facet, with its label and description. */
export function facetOptions(def: FacetDef): Record<string, string> {
  const o: Record<string, string> = {};
  for (const c of def.codes) o[c.code] = `${c.label}. ${c.description}`;
  return o;
}

/** The questions of one facet: one choice question with the facet's codes as options (Placement may add the load-bearing yes/no). */
export function facetQuestions(defs: FacetDefs, facet: Exclude<FacetId, 'Orientation'>, o: { loadBearing?: boolean; exposure?: boolean } = {}): Questions {
  const q: Questions = {};
  if (facet !== 'Placement' || o.exposure !== false) q[Q_FACET[facet]] = choiceQuestion(INSTRUCTIONS[facet], facetOptions(defs[facet]));
  if (facet === 'Placement' && o.loadBearing) q[Q_LOAD_BEARING] = noulQuestion('This element carries structural load (it is load-bearing).');
  return q;
}

// ---------------------------------------------------------------- cache

/** A stored facet decision: the code, the raw scores (so calibration applies when it is read) and the model that answered. */
export interface CachedFacetDecision {
  raw: RawAnswers;
  model: string;
}

export interface FacetCache {
  get(key: string): CachedFacetDecision | undefined;
  set(key: string, d: CachedFacetDecision): void;
  readonly size: number;
  clear(): void;
  flush(): void;
}

export class MemoryFacetCache implements FacetCache {
  protected readonly map = new Map<string, CachedFacetDecision>();
  get(k: string): CachedFacetDecision | undefined { return this.map.get(k); }
  set(k: string, d: CachedFacetDecision): void { this.map.set(k, d); }
  get size(): number { return this.map.size; }
  clear(): void { this.map.clear(); }
  flush(): void { /* memory only */ }
}

export const FACET_CACHE_PREFIX = 'xray.classify.facets.cache.v1.';
const MAX_CACHE = 5000;

/** Key of the persisted facet cache: the model name, a hash of the facet code lists and the provider and model id. */
export const facetCacheKey = (modelName: string, facetsHash: string, modelId: string): string => `${FACET_CACHE_PREFIX}${modelName}|${facetsHash}|${modelId}`;

interface Store { getItem(k: string): string | null; setItem(k: string, v: string): void; removeItem(k: string): void }

export class StorageFacetCache extends MemoryFacetCache {
  private dirty = false;
  constructor(private readonly storage: Store | null, private readonly key: string) {
    super();
    try {
      const t = storage?.getItem(key);
      if (t) for (const [k, v] of Object.entries(JSON.parse(t) as Record<string, CachedFacetDecision>)) if (v && typeof v === 'object' && 'raw' in v) this.map.set(k, v);
    } catch { /* a broken entry is an empty cache */ }
  }
  override set(k: string, d: CachedFacetDecision): void { super.set(k, d); this.dirty = true; }
  override clear(): void {
    super.clear();
    try { this.storage?.removeItem(this.key); } catch { /* ignore */ }
    this.dirty = false;
  }
  override flush(): void {
    if (!this.dirty || !this.storage) return;
    this.dirty = false;
    while (this.map.size > MAX_CACHE) this.map.delete(this.map.keys().next().value as string);
    try { this.storage.setItem(this.key, JSON.stringify(Object.fromEntries(this.map))); } catch { /* quota or private mode */ }
  }
}

// ---------------------------------------------------------------- run types

/** What the viewer knows about an element's geometry and level, for the rules. All optional. */
export interface FacetElementInfo {
  measure?: OrientationMeasure | null;
  placementGeo?: PlacementGeo | null;
  belowGround?: boolean;
  /** Discipline code from the classifier, when it has run. */
  discipline?: string;
  /** The one-line numeric shape (geometryVector), for the model's state. A function: it is called only for the element that represents a signature. */
  shape?: () => string;
}

export interface FacetStats {
  /** Requests to the decision model. */
  calls: number;
  /** Distinct (facet, signature) pairs asked. */
  signatures: number;
  /** Per facet: how many elements each source decided. */
  bySource: Record<FacetId, Partial<Record<FacetSource | 'cache', number>>>;
  needsReview: number;
  errors: string[];
  aborted: boolean;
  models: Record<string, number>;
  usage: { input_tokens: number; output_tokens: number };
}

export interface FacetRunOptions {
  schema: ClassificationSchema;
  /** Which facets are on. Default: the schema's `enabled` flags. */
  enabled?: Partial<Record<FacetId, boolean>>;
  /** The decision model. Null: rules and cache only. */
  provider?: DecisionModel | null;
  info?: (input: ClassifyInput) => FacetElementInfo;
  cache?: FacetCache;
  /** Manual choices by element id; they win over everything and are never asked again. */
  manual?: ReadonlyMap<string, FacetSet>;
  /** Temperatures of the discipline question are applied to the facet questions (the same calibration). */
  temperatures?: Temperatures;
  minMargin?: number;
  ruleFinal?: number;
  concurrency?: number;
  maxStateBytes?: number;
  retry?: RetryOptions;
  signal?: AbortSignal;
  /** Count the requests that would be sent and send none. `stats.calls` then holds the number planned. */
  dry?: boolean;
  onProgress?: (p: { facet: FacetId; done: number; total: number; calls: number }) => void;
}

export interface FacetRun {
  /** The facet values by element id (only facets that are on). */
  results: Map<string, FacetSet>;
  stats: FacetStats;
}

const emptyStats = (): FacetStats => ({
  calls: 0, signatures: 0, bySource: Object.fromEntries(FACET_IDS.map((f) => [f, {}])) as FacetStats['bySource'], needsReview: 0, errors: [], aborted: false, models: {}, usage: { input_tokens: 0, output_tokens: 0 },
});

const r2 = (n: number): number => Math.round(n * 100) / 100;

// ---------------------------------------------------------------- building results

export function makeFacetResult(defs: FacetDefs, facet: FacetId, p: { code: string; confidence: number; source: FacetSource; model?: string; needsReview?: boolean; fields?: Record<string, FacetFieldValue>; probabilities?: Record<string, number>; rationale?: string }): FacetResult {
  const def = defs[facet];
  const needs = p.needsReview ?? (p.source !== 'manual' && p.source !== 'geometry' && p.confidence < def.minConfidence);
  return {
    facet,
    code: p.code,
    label: facetLabel(def, p.code),
    confidence: r2(p.confidence),
    source: p.source,
    ...(p.model && (p.source === 'model' || p.source === 'batch-learned') ? { model: p.model } : {}),
    needsReview: needs,
    fields: { ...(p.fields ?? {}) },
    ...(p.probabilities ? { probabilities: p.probabilities } : {}),
    ...(p.rationale ? { rationale: p.rationale } : {}),
  };
}

/** The Orientation result of a measure: code = Class, fields Tilt, Azimuth, Upright, PrincipalAxis, Plausible. Needs review when it is implausible for the class. */
export function orientationResult(defs: FacetDefs, input: ClassifyInput, m: OrientationMeasure): FacetResult {
  const plausible = orientationPlausible({ ifcClass: input.ifcClass, measure: m, predefinedType: predefinedOf(input) });
  const fields: Record<string, FacetFieldValue> = { Tilt: m.tilt, Azimuth: m.azimuth };
  if (m.upright !== null) fields['Upright'] = m.upright;
  if (m.principalAxis) fields['PrincipalAxis'] = m.principalAxis;
  if (plausible !== null) fields['Plausible'] = plausible;
  return makeFacetResult(defs, 'Orientation', {
    code: m.class, confidence: 1, source: 'geometry', needsReview: plausible === false, fields,
    rationale: `${m.shape} shape, ${m.class.toLowerCase()}${plausible === false ? `, not plausible for ${input.ifcClass}` : ''}`,
  });
}

// ---------------------------------------------------------------- the run

const ORDER = ['Material', 'Placement', 'Trade', 'Phase', 'ClassRepair'] as const;
type Ruled = (typeof ORDER)[number];

interface Item {
  input: ClassifyInput;
  info: FacetElementInfo;
  set: FacetSet;
  /** Values the rules of later facets read. */
  material?: string;
  exposure?: string;
  loadBearing?: boolean;
  trade?: string;
}

const ctxOf = (it: Item): FacetContext => ({
  input: it.input,
  ...(it.info.discipline ? { discipline: it.info.discipline } : {}),
  ...(it.info.measure !== undefined ? { measure: it.info.measure } : {}),
  ...(it.info.placementGeo !== undefined ? { placementGeo: it.info.placementGeo } : {}),
  ...(it.info.belowGround !== undefined ? { belowGround: it.info.belowGround } : {}),
  ...(it.material ? { material: it.material } : {}),
  ...(it.exposure ? { exposure: it.exposure } : {}),
  ...(it.loadBearing !== undefined ? { loadBearing: it.loadBearing } : {}),
  ...(it.trade ? { trade: it.trade } : {}),
});

/** A decision a rule or the model made, before it becomes a FacetResult. */
interface Decided {
  code: string;
  confidence: number;
  source: FacetSource;
  model?: string;
  needsReview?: boolean;
  fields?: Record<string, FacetFieldValue>;
  probabilities?: Record<string, number>;
  rationale?: string;
}

/** What the rules say about one facet of one element, and what stays open for the model. */
interface RuleView {
  /** Final decision, or null. */
  final: Decided | null;
  /** A weak decision: the fallback when the model cannot answer. */
  weak: Decided | null;
  /** The model should be asked (the facet is not final and is eligible). */
  ask: boolean;
  /** Placement: which questions are open. */
  askExposure?: boolean;
  askLoadBearing?: boolean;
  /** Placement: the load-bearing value known already (for combining). */
  lb?: { value: boolean; confidence: number; source: 'ifc' | 'rule' };
  /** Placement: the exposure known already. */
  exposure?: { code: string; confidence: number; source: 'ifc' | 'geometry'; needsReview: boolean; rationale: string };
}

function ruleView(facet: Ruled, it: Item, final: number): RuleView {
  const c = ctxOf(it);
  const fromRule = (r: RuleOut | null, extra: Partial<Decided> = {}): RuleView => {
    if (!r) return { final: null, weak: null, ask: true };
    const d: Decided = { code: r.code, confidence: r.confidence, source: 'rule', rationale: r.rationale, ...(r.fields ? { fields: r.fields } : {}), ...extra };
    return r.confidence >= final ? { final: d, weak: null, ask: false } : { final: null, weak: d, ask: true };
  };
  switch (facet) {
    case 'Material': return fromRule(materialRule(it.input));
    case 'Trade': return fromRule(tradeRule(c));
    case 'Phase': return fromRule(phaseRule(c));
    case 'ClassRepair': {
      if (!isGenericClass(it.input) && !c.measure) return { final: null, weak: null, ask: false };
      const r = classRepairRule(c);
      if (!r) return { final: null, weak: null, ask: isGenericClass(it.input) };
      return fromRule(r);
    }
    case 'Placement': {
      const pd = placementRule(it.input, it.info.placementGeo);
      const lb = loadBearingRule(c);
      const lbFinal = lb && lb.confidence >= final ? lb : null;
      const view: RuleView = { final: null, weak: null, ask: false };
      if (pd) view.exposure = pd;
      if (lb) view.lb = lb;
      const expoFinal = pd && pd.confidence >= final;
      view.askExposure = !expoFinal;
      view.askLoadBearing = !lbFinal;
      view.ask = view.askExposure || view.askLoadBearing;
      return view;
    }
  }
}

function placementFields(exposure: string, exposureSource: string, lb: { value: boolean; source: string } | undefined): Record<string, FacetFieldValue> {
  const f: Record<string, FacetFieldValue> = { Exposure: exposure, ExposureSource: exposureSource };
  if (lb) { f['LoadBearing'] = lb.value; f['LoadBearingSource'] = lb.source; }
  return f;
}

/** The compact `facets` object of the state: what is known about the element so far. */
function knownFacets(it: Item): Record<string, string | boolean | number> {
  const o: Record<string, string | boolean | number> = {};
  if (it.info.discipline) o['discipline'] = it.info.discipline;
  const m = it.info.measure;
  if (m) { o['orientation'] = `${m.shape} ${m.class} tilt ${m.tilt} deg`; }
  if (it.material) o['material'] = it.material;
  if (it.exposure) o['placement'] = it.exposure;
  if (it.loadBearing !== undefined) o['load_bearing'] = it.loadBearing;
  if (it.trade) o['trade'] = it.trade;
  if (it.info.belowGround !== undefined) o['below_ground'] = it.info.belowGround;
  return o;
}

/** The part of the signature that is specific to a facet: the facts the question depends on beyond the element's own signature. */
function facetSignature(facet: Ruled, it: Item, open: string): string {
  const m = it.info.measure;
  const orient = m ? `${m.shape}:${m.class}` : '';
  switch (facet) {
    case 'Material': return signatureOf(it.input);
    case 'Placement': return `${signatureOf(it.input)}#${open}#${it.info.placementGeo?.exposure ?? ''}#${it.material ?? ''}`;
    case 'Trade': return `${signatureOf(it.input)}#${it.material ?? ''}#${it.exposure ?? ''}#${it.info.discipline ?? ''}`;
    case 'Phase': return `${signatureOf(it.input)}#${it.trade ?? ''}#${it.exposure ?? ''}#${it.loadBearing ?? ''}#${it.info.belowGround ?? ''}`;
    case 'ClassRepair': return `${signatureOf(it.input)}#${orient}`;
  }
}

/**
 * The facets of the given elements. Orientation from `info.measure`; the other facets by manual choice, rule, cache and, last, the
 * decision model (one request per facet and signature). Never throws: a model failure leaves the weak rule (flagged for review) or nothing.
 */
export async function classifyFacets(inputs: readonly ClassifyInput[], o: FacetRunOptions): Promise<FacetRun> {
  const defs = facetDefs(o.schema);
  const on = (f: FacetId): boolean => o.enabled?.[f] ?? defs[f].enabled;
  const final = o.ruleFinal ?? FACET_RULE_FINAL;
  const minMargin = o.minMargin ?? DEFAULT_MIN_MARGIN;
  const cache = o.cache ?? new MemoryFacetCache();
  const stats = emptyStats();
  const ctl = new AbortController();
  const stop = (): void => ctl.abort();
  if (o.signal?.aborted) ctl.abort();
  else o.signal?.addEventListener('abort', stop, { once: true });
  const signal = ctl.signal;
  const addError = (m: string): void => { if (stats.errors.length < 20 && !stats.errors.includes(m)) stats.errors.push(m); };
  const count = (f: FacetId, s: FacetSource | 'cache'): void => { stats.bySource[f][s] = (stats.bySource[f][s] ?? 0) + 1; };

  const items: Item[] = inputs.map((input) => ({ input, info: o.info?.(input) ?? {}, set: {} }));

  // Orientation: measured
  for (const it of items) {
    const man = o.manual?.get(it.input.id)?.Orientation;
    if (man) { it.set.Orientation = man; count('Orientation', 'manual'); continue; }
    if (it.info.measure) { it.set.Orientation = orientationResult(defs, it.input, it.info.measure); count('Orientation', 'geometry'); }
  }

  const temps: Temperatures = {};
  if (o.temperatures) {
    for (const q of [...Object.values(Q_FACET), Q_LOAD_BEARING]) (temps as Record<string, number | undefined>)[q] = o.temperatures['discipline'] ?? undefined;
  }

  const readFacet = (a: Answers, facet: Exclude<FacetId, 'Orientation'>): ChoiceAnswer => {
    const x = readChoice(a, Q_FACET[facet]);
    if (!defs[facet].codes.some((c) => c.code === x.choice)) throw new ProviderError(`The model chose the ${facet} code "${x.choice}", which is not in the schema.`);
    return x;
  };

  for (const facet of ORDER) {
    if (signal.aborted) break;
    const def = defs[facet];
    const emit = on(facet);
    const askable = emit && !!o.provider && MODEL_FACETS.includes(facet);
    const need: Array<{ it: Item; view: RuleView }> = [];

    const apply = (it: Item, d: Decided, lb?: { value: boolean; source: string }): void => {
      const result = makeFacetResult(defs, facet, d);
      if (emit) it.set[facet] = result;
      if (facet === 'Material') it.material = d.code;
      if (facet === 'Trade') it.trade = d.code;
      if (facet === 'Placement') { it.exposure = d.code; if (lb) it.loadBearing = lb.value; }
    };

    // 1. manual and rules
    for (const it of items) {
      const man = o.manual?.get(it.input.id)?.[facet];
      if (man) {
        if (emit) { it.set[facet] = man; count(facet, 'manual'); }
        if (facet === 'Material') it.material = man.code;
        if (facet === 'Trade') it.trade = man.code;
        if (facet === 'Placement') { it.exposure = man.code; if (typeof man.fields['LoadBearing'] === 'boolean') it.loadBearing = man.fields['LoadBearing']; }
        continue;
      }
      const view = ruleView(facet, it, final);
      if (facet === 'Placement') {
        // Combine what the rules know; open parts go to the model.
        const ex = view.exposure;
        const lb = view.lb && view.lb.confidence >= final ? view.lb : undefined;
        if (!view.askExposure && !view.askLoadBearing) {
          apply(it, { code: ex!.code, confidence: ex!.confidence, source: ex!.source, needsReview: ex!.needsReview, rationale: ex!.rationale, fields: placementFields(ex!.code, ex!.source, lb ? { value: lb.value, source: lb.source } : undefined) }, lb ? { value: lb.value, source: lb.source } : undefined);
          count(facet, ex!.source);
          continue;
        }
        if (!askable) {
          // no model: keep what the rules know
          if (ex) {
            const lbAny = view.lb ? { value: view.lb.value, source: view.lb.source } : undefined;
            apply(it, { code: ex.code, confidence: ex.confidence, source: ex.source, needsReview: ex.needsReview || ex.confidence < def.minConfidence, rationale: ex.rationale, fields: placementFields(ex.code, ex.source, lbAny) }, lbAny);
            count(facet, ex.source);
          }
          continue;
        }
        need.push({ it, view });
        continue;
      }
      if (view.final) { apply(it, view.final); count(facet, 'rule'); continue; }
      if (!askable || !view.ask) {
        if (view.weak) { apply(it, { ...view.weak, needsReview: true }); count(facet, 'rule'); }
        continue;
      }
      need.push({ it, view });
    }

    // 2. cache and the model, grouped by signature
    if (need.length) {
      const groups = new Map<string, Array<{ it: Item; view: RuleView }>>();
      for (const n of need) {
        const open = facet === 'Placement' ? `${n.view.askExposure ? 'E' : ''}${n.view.askLoadBearing ? 'L' : ''}` : '';
        const key = `${facet}|${facetSignature(facet, n.it, open)}`;
        (groups.get(key) ?? groups.set(key, []).get(key)!).push(n);
      }
      const fallbackAll = (members: Array<{ it: Item; view: RuleView }>): void => {
        for (const m of members) {
          if (facet === 'Placement') {
            const ex = m.view.exposure;
            if (ex) {
              const lb = m.view.lb ? { value: m.view.lb.value, source: m.view.lb.source } : undefined;
              apply(m.it, { code: ex.code, confidence: ex.confidence, source: ex.source, needsReview: true, rationale: ex.rationale, fields: placementFields(ex.code, ex.source, lb) }, lb);
              count(facet, ex.source);
            }
          } else if (m.view.weak) { apply(m.it, { ...m.view.weak, needsReview: true }); count(facet, 'rule'); }
        }
      };

      const decide = (members: Array<{ it: Item; view: RuleView }>, a: Answers, fromCache: boolean): void => {
        const first = members[0]!;
        const askE = facet !== 'Placement' || !!first.view.askExposure;
        let choice: ChoiceAnswer | null = null;
        if (askE) choice = readFacet(a, facet as Exclude<FacetId, 'Orientation'>);
        const lbP = facet === 'Placement' && first.view.askLoadBearing ? readNoul(a, Q_LOAD_BEARING) : null;
        for (const m of members) {
          const modelId = a.model;
          if (facet === 'Placement') {
            const ex = m.view.exposure;
            const code = choice ? choice.choice : ex!.code;
            const conf = choice ? choice.confidence : ex!.confidence;
            const source: FacetSource = choice ? 'model' : ex!.source;
            const knownLb = m.view.lb && m.view.lb.confidence >= final ? { value: m.view.lb.value, source: m.view.lb.source as string } : undefined;
            const lb = knownLb ?? (lbP !== null ? { value: lbP >= 0.5, source: 'model' } : m.view.lb ? { value: m.view.lb.value, source: m.view.lb.source as string } : undefined);
            const weakLb = lbP !== null && Math.abs(lbP - 0.5) < 0.15;
            const needs = (choice ? choice.confidence < def.minConfidence || topMargin(choice.probabilities) < minMargin : ex!.needsReview) || weakLb;
            apply(m.it, { code, confidence: conf, source, ...(source === 'model' ? { model: modelId } : {}), needsReview: needs, ...(choice ? { probabilities: choice.probabilities } : {}), fields: placementFields(code, source, lb) }, lb);
            count(facet, fromCache ? 'cache' : source);
            continue;
          }
          const x = choice!;
          const needs = x.confidence < def.minConfidence || topMargin(x.probabilities) < minMargin;
          let code = x.choice;
          let fields: Record<string, FacetFieldValue> | undefined;
          if (facet === 'ClassRepair') {
            const orig = m.it.input.ifcClass;
            const keep = code === 'KEEP' || code === orig;
            code = keep ? 'KEEP' : code;
            fields = keep ? { OriginalClass: orig, Applied: false } : { OriginalClass: orig, SuggestedClass: code, SuggestedPredefinedType: m.view.weak?.fields?.['SuggestedPredefinedType'] ?? '', Applied: false };
            if (fields['SuggestedPredefinedType'] === '') delete fields['SuggestedPredefinedType'];
          }
          apply(m.it, { code, confidence: x.confidence, source: 'model', model: modelId, needsReview: needs, probabilities: x.probabilities, ...(fields ? { fields } : {}) });
          count(facet, fromCache ? 'cache' : 'model');
        }
      };

      const todo: Array<[string, Array<{ it: Item; view: RuleView }>]> = [];
      for (const [key, members] of groups) {
        const hit = cache.get(key);
        if (hit) {
          try { decide(members, answersFromRaw(hit.raw, temps), true); continue; } catch { /* a stale entry: ask again */ }
        }
        todo.push([key, members]);
      }
      stats.signatures += todo.length;
      if (o.dry) stats.calls += todo.length;
      else if (todo.length && !askable) fallbackAll(todo.flatMap(([, m]) => m));
      else if (todo.length) {
        const provider = o.provider!;
        let next = 0;
        let done = 0;
        const worker = async (): Promise<void> => {
          for (;;) {
            if (signal.aborted) return;
            const entry = todo[next++];
            if (!entry) return;
            const [key, members] = entry;
            const rep = members[0]!;
            try {
              let state = buildState(rep.it.input, o.maxStateBytes ?? DEFAULT_MAX_STATE_BYTES);
              const known = knownFacets(rep.it);
              if (Object.keys(known).length) state = { ...state, facets: known };
              const line = rep.it.info.shape?.();
              if (line) state = { ...state, shape: line };
              const questions = facetQuestions(defs, facet as Exclude<FacetId, 'Orientation'>, { exposure: facet !== 'Placement' || !!rep.view.askExposure, loadBearing: !!rep.view.askLoadBearing });
              stats.calls++;
              const answers = await withBackoff(() => provider.decide(state, questions, signal), signal, o.retry);
              stats.models[answers.model] = (stats.models[answers.model] ?? 0) + 1;
              stats.usage.input_tokens += answers.usage?.input_tokens ?? 0;
              stats.usage.output_tokens += answers.usage?.output_tokens ?? 0;
              const raw = rawOfAnswers(answers);
              decide(members, answersFromRaw(raw, temps), false);
              cache.set(key, { raw, model: answers.model });
              done++;
              o.onProgress?.({ facet, done, total: todo.length, calls: stats.calls });
            } catch (e) {
              if (isAbort(e) || signal.aborted) return;
              fallbackAll(members);
              addError(`${facet}: ${e instanceof Error ? e.message : String(e)}`);
            }
          }
        };
        const n = Math.max(1, Math.min(o.concurrency ?? 4, todo.length));
        await Promise.all(Array.from({ length: n }, () => worker()));
      }
    }
    o.onProgress?.({ facet, done: items.length, total: items.length, calls: stats.calls });
  }
  stats.aborted = signal.aborted;
  o.signal?.removeEventListener('abort', stop);
  cache.flush();

  const results = new Map<string, FacetSet>();
  for (const it of items) {
    const set: FacetSet = {};
    for (const f of FACET_IDS) {
      const r = it.set[f];
      if (r && on(f)) { set[f] = r; if (r.needsReview) stats.needsReview++; }
    }
    results.set(it.input.id, set);
  }
  return { results, stats };
}

/** The number of model requests a run would send now (rules and cache applied): one per facet and signature that is still open. */
export async function estimateFacetCalls(inputs: readonly ClassifyInput[], o: Omit<FacetRunOptions, 'dry' | 'signal'>): Promise<{ calls: number; signatures: number }> {
  const run = await classifyFacets(inputs, { ...o, dry: true });
  return { calls: run.stats.calls, signatures: run.stats.signatures };
}

export { FACETS_VERSION };
