// Facet results as properties (`XR_<Facet>.<Field>`), manual overrides and the export columns. Pure, no DOM.
// The namespace is the contract in docs/design/classification-facets.md section 3 and docs-features/classify.md, "Facets".

import { facetCode, facetPset, FACET_IDS, FACETS_VERSION } from './defs';
import type { FacetDefs, FacetFieldValue, FacetId, FacetResult, FacetSet } from './defs';

export type PropValue = string | number | boolean;

/** The core fields every facet set has, in order, with the type each is written as. */
export const CORE_FIELDS: ReadonlyArray<readonly [string, 'label' | 'real' | 'boolean']> = [
  ['Code', 'label'], ['Label', 'label'], ['Confidence', 'real'], ['Source', 'label'], ['Model', 'label'], ['NeedsReview', 'boolean'], ['SchemeVersion', 'label'],
];

/** The facet-specific fields of each facet, in order, with their types. */
export const FACET_FIELDS: Record<FacetId, ReadonlyArray<readonly [string, 'label' | 'real' | 'boolean']>> = {
  Trade: [['WorkPackage', 'label']],
  Placement: [['Exposure', 'label'], ['LoadBearing', 'boolean'], ['ExposureSource', 'label'], ['LoadBearingSource', 'label']],
  Material: [],
  Phase: [],
  Orientation: [['Tilt', 'real'], ['Azimuth', 'real'], ['Upright', 'boolean'], ['PrincipalAxis', 'label'], ['Plausible', 'boolean']],
  ClassRepair: [['OriginalClass', 'label'], ['SuggestedClass', 'label'], ['SuggestedPredefinedType', 'label'], ['Applied', 'boolean']],
};

/** Every property a facet can write, as `XR_<Facet>.<Field>`, in order. */
export function facetPropertyNames(facet: FacetId): string[] {
  return [...CORE_FIELDS, ...FACET_FIELDS[facet]].map(([f]) => `${facetPset(facet)}.${f}`);
}

/**
 * The properties of one facet result: core fields (Code, Label, Confidence, Source, Model, NeedsReview, SchemeVersion) and the
 * facet's own fields. An empty value is left out (so the property is absent, not an empty string). Types: labels are strings,
 * Confidence/Tilt/Azimuth numbers, NeedsReview/Upright/Plausible/LoadBearing/Applied booleans.
 */
export function facetProperties(r: FacetResult): Record<string, PropValue> {
  const pset = facetPset(r.facet);
  const out: Record<string, PropValue> = {};
  const put = (k: string, v: FacetFieldValue | undefined): void => {
    if (v === undefined || v === '') return;
    out[`${pset}.${k}`] = v;
  };
  put('Code', r.code);
  put('Label', r.label);
  put('Confidence', Math.round(r.confidence * 100) / 100);
  put('Source', r.source);
  put('Model', r.model);
  put('NeedsReview', r.needsReview);
  put('SchemeVersion', FACETS_VERSION);
  for (const [k] of FACET_FIELDS[r.facet]) {
    if (k === 'Exposure') put(k, r.facet === 'Placement' ? r.code : r.fields[k]);
    else put(k, r.fields[k]);
  }
  return out;
}

/** All properties of a set of facet results. */
export function facetSetProperties(set: FacetSet): Record<string, PropValue> {
  const out: Record<string, PropValue> = {};
  for (const f of FACET_IDS) {
    const r = set[f];
    if (r) Object.assign(out, facetProperties(r));
  }
  return out;
}

/** Is a property key one of the facet namespace (`XR_Trade.`, ...)? */
export const isFacetKey = (k: string): boolean => FACET_IDS.some((f) => k.startsWith(`${facetPset(f)}.`));

/** A change a person makes by hand: the code, and for Placement the load-bearing flag. */
export interface ManualFacetPartial {
  code?: string;
  loadBearing?: boolean | null;
  /** Trade: a free-text work package. */
  workPackage?: string;
  /** ClassRepair: the predefined type of the suggested class. */
  predefinedType?: string;
}

/** Build a manual facet result. `source` is `manual`, the confidence 1, no review. Throws an Error with a plain message for a code that is not in the facet's list. */
export function makeManualFacet(defs: FacetDefs, facet: FacetId, p: ManualFacetPartial, prior?: FacetResult, originalClass?: string): FacetResult {
  const def = defs[facet];
  const code = p.code ?? prior?.code;
  if (!code || !facetCode(def, code)) throw new Error(`"${code ?? ''}" is not a ${facet} code. Use one of: ${def.codes.map((c) => c.code).join(', ')}.`);
  const fields: Record<string, FacetFieldValue> = { ...(prior?.fields ?? {}) };
  if (facet === 'Placement') {
    fields['Exposure'] = code;
    fields['ExposureSource'] = 'manual';
    if (p.loadBearing === null) { delete fields['LoadBearing']; delete fields['LoadBearingSource']; }
    else if (typeof p.loadBearing === 'boolean') { fields['LoadBearing'] = p.loadBearing; fields['LoadBearingSource'] = 'manual'; }
  }
  if (facet === 'Trade' && p.workPackage !== undefined) { if (p.workPackage) fields['WorkPackage'] = p.workPackage; else delete fields['WorkPackage']; }
  if (facet === 'ClassRepair') {
    if (code === 'KEEP') { delete fields['SuggestedClass']; delete fields['SuggestedPredefinedType']; }
    else { fields['SuggestedClass'] = code; if (p.predefinedType !== undefined) { if (p.predefinedType) fields['SuggestedPredefinedType'] = p.predefinedType; else delete fields['SuggestedPredefinedType']; } }
    if (originalClass) fields['OriginalClass'] = originalClass;
    fields['Applied'] = false;
  }
  return { facet, code, label: facetCode(def, code)!.label, confidence: 1, source: 'manual', needsReview: false, fields, rationale: 'set by hand' };
}

// ---------------------------------------------------------------- export columns

/** CSV columns of the facets: every property of every facet, as `XR_<Facet>.<Field>`. */
export function facetCsvColumns(facets: readonly FacetId[] = FACET_IDS): string[] {
  return facets.flatMap(facetPropertyNames);
}

/** The cell values of a facet set for the given columns ('' for a missing value). */
export function facetCsvCells(set: FacetSet | undefined, columns: readonly string[]): PropValue[] {
  const props = set ? facetSetProperties(set) : {};
  return columns.map((c) => props[c] ?? '');
}
