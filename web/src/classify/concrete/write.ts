// Concrete facet results as properties (`XR_Concrete<Set>.<Field>`), manual overrides and the export columns. Pure, no DOM.
// Same shape as ../facets/write.ts: core fields first, then the set's own fields; an empty value is left out.

import { CONCRETE_FACET_IDS, CONCRETE_FIELDS, CONCRETE_SCHEME, CORE_FIELDS, ROLE_CODES, METHOD_CODES, REINFORCEMENT_CODES, concretePset, labelOf } from './defs';
import type { ConcreteCode, ConcreteFacetId, ConcreteFacetResult, ConcreteSet } from './defs';

export type PropValue = string | number | boolean;

/** Every property of one concrete set, as `XR_Concrete<Set>.<Field>`, in order. */
export function concretePropertyNames(facet: ConcreteFacetId): string[] {
  return [...CORE_FIELDS, ...CONCRETE_FIELDS[facet]].map(([f]) => `${concretePset(facet)}.${f}`);
}

/** The properties of one result: the core fields and the set's own fields. */
export function concreteProperties(r: ConcreteFacetResult): Record<string, PropValue> {
  const pset = concretePset(r.facet);
  const out: Record<string, PropValue> = {};
  const put = (k: string, v: PropValue | undefined): void => { if (v !== undefined && v !== '') out[`${pset}.${k}`] = v; };
  put('Code', r.code);
  put('Label', r.label);
  put('Confidence', Math.round(r.confidence * 100) / 100);
  put('Source', r.source);
  put('Model', r.model);
  put('NeedsReview', r.needsReview);
  put('SchemeVersion', CONCRETE_SCHEME);
  for (const [k] of CONCRETE_FIELDS[r.facet]) put(k, r.fields[k]);
  return out;
}

export function concreteSetProperties(set: ConcreteSet): Record<string, PropValue> {
  const out: Record<string, PropValue> = {};
  for (const f of CONCRETE_FACET_IDS) { const r = set[f]; if (r) Object.assign(out, concreteProperties(r)); }
  return out;
}

/** CSV columns of the concrete sets, as `XR_Concrete<Set>.<Field>`. */
export const concreteCsvColumns = (facets: readonly ConcreteFacetId[] = CONCRETE_FACET_IDS): string[] => facets.flatMap(concretePropertyNames);

export function concreteCsvCells(set: ConcreteSet | undefined, columns: readonly string[]): PropValue[] {
  const props = set ? concreteSetProperties(set) : {};
  return columns.map((c) => props[c] ?? '');
}

const LISTS: Partial<Record<ConcreteFacetId, readonly ConcreteCode[]>> = { ConcreteElement: ROLE_CODES, ConcreteMethod: METHOD_CODES, ConcreteReinforcement: REINFORCEMENT_CODES };

/** A manual choice of the role, the method or the reinforcement type. Throws an Error with a plain message for a code that is not in the list. */
export function makeManualConcrete(facet: 'ConcreteElement' | 'ConcreteMethod' | 'ConcreteReinforcement', code: string, prior?: ConcreteFacetResult): ConcreteFacetResult {
  const list = LISTS[facet]!;
  if (!list.some((c) => c.code === code)) throw new Error(`"${code}" is not a ${facet.replace('Concrete', '')} code. Use one of: ${list.map((c) => c.code).join(', ')}.`);
  return { facet, code, label: labelOf(list, code), confidence: 1, source: 'manual', needsReview: false, fields: { ...(prior?.fields ?? {}) }, rationale: 'set by hand' };
}
