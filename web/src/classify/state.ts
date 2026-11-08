// The `state` that the decision model reads, and the signature that decides which elements share one decision.
// No DOM.

import type { JsonObject, JsonValue } from './jevAdapter';
import type { ClassifyInput, PsetRecord, PsetValue, RelatedElement } from './types';
import { isBuildingContext } from './rules';

export const DEFAULT_MAX_STATE_BYTES = 4000;
/** Strings longer than this are dropped from the state (a long note or a hash says nothing about the discipline). */
const HUGE_STRING = 160;
/** A property whose name matches is kept longest when the state is cut down. */
const KEY_PROP = /^(ObjectType|PredefinedType|Description|Tag|LoadBearing|IsExternal|Reference|Status|System\w*|Function|Category|Type\w*|Application|NominalDiameter|FlowDirection|PipeSegmentType)$/i;

const bytes = (v: unknown): number => new TextEncoder().encode(JSON.stringify(v)).length;

function keep(v: PsetValue | undefined): v is string | number | boolean {
  if (v === null || v === undefined) return false;
  if (typeof v === 'string') return v.trim() !== '' && v.length <= HUGE_STRING;
  if (typeof v === 'number') return Number.isFinite(v);
  return true;
}

/** A pset record without empty and huge values and without empty sets. `onlyKey` keeps the key properties only. */
export function compactPsets(p: PsetRecord | undefined, onlyKey = false): JsonObject {
  const out: JsonObject = {};
  if (!p) return out;
  for (const [set, props] of Object.entries(p)) {
    const o: JsonObject = {};
    for (const [k, v] of Object.entries(props)) if (keep(v) && (!onlyKey || KEY_PROP.test(k))) o[k] = v as JsonValue;
    if (Object.keys(o).length) out[set] = o;
  }
  return out;
}

function relatedState(r: RelatedElement | undefined, onlyKey: boolean, withPsets: boolean): JsonObject | undefined {
  if (!r) return undefined;
  const o: JsonObject = { class: r.ifcClass, name: r.name };
  if (withPsets) {
    const ps = compactPsets(r.psets, onlyKey);
    if (Object.keys(ps).length) o['psets'] = ps;
  }
  return o;
}

const pathText = (p: { ifcClass: string; name: string }): string => `${p.ifcClass}: ${p.name}`;

/** Detail levels, richest first. The first one that fits in `maxBytes` is used. */
const LEVELS = 5;

function stateAt(i: ClassifyInput, level: number): JsonObject {
  const s: JsonObject = { class: i.ifcClass, name: i.name };
  const t = relatedState(i.type, level >= 2, level <= 3);
  if (t && level <= 4) s['type'] = t;
  if (level <= 3) {
    const ps = compactPsets(i.psets, level >= 2);
    if (Object.keys(ps).length) s['psets'] = ps;
  }
  if (level <= 1) {
    const q = compactPsets(i.quantities);
    if (Object.keys(q).length) s['quantities'] = q;
  }
  if (i.material && level <= 3) s['material'] = i.material;
  if (i.systems?.length && level <= 3) s['systems'] = i.systems;
  const h = i.hierarchy;
  if (h && h.path.length && level <= 4) s['hierarchy'] = (level >= 3 ? h.path.slice(-2) : h.path).map(pathText);
  if (h?.parents?.length && level <= 3) {
    s['parents'] = h.parents.slice(0, level === 0 ? 4 : 2).map((p) => relatedState(p, level >= 1, level <= 2)!);
  }
  const building = isBuildingContext(i);
  s['building_context'] = building;
  return s;
}

/** The compact, size-capped JSON state of an element. Detail is dropped in steps until it fits; class and name always stay. */
export function buildState(input: ClassifyInput, maxBytes = DEFAULT_MAX_STATE_BYTES): JsonObject {
  let s: JsonObject = {};
  for (let level = 0; level <= LEVELS; level++) {
    s = level === LEVELS ? { class: input.ifcClass, name: input.name.slice(0, 80) } : stateAt(input, level);
    if (bytes(s) <= maxBytes) return s;
  }
  return s;
}

// ---------------------------------------------------------------- signature

/** Properties whose values belong to the signature (they change the discipline or the division). */
export const SIGNATURE_PROPS = ['PredefinedType', 'LoadBearing', 'IsExternal'];

function propOf(i: ClassifyInput, name: string): PsetValue | undefined {
  for (const set of Object.values(i.psets)) if (name in set) return set[name];
  return undefined;
}

/** A name without digits and punctuation: "Pump P-101" and "Pump P-102" share a stem. */
export function nameStem(name: string): string {
  return name.toLowerCase().replace(/[\d_.,:;()\[\]#/\\-]+/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 40);
}

/**
 * The signature of an element: class, type name, the key property values, systems, material and the class of the first
 * parent. Elements with the same signature get the same decision, so a model with 5,000 elements needs tens of requests.
 * An element without a type name adds its name stem, so that generic classes (proxies) are told apart.
 */
export function signatureOf(i: ClassifyInput): string {
  const typeName = i.type?.name || String(propOf(i, 'ObjectType') ?? '');
  const parts = [i.ifcClass, typeName || `~${nameStem(i.name)}`];
  for (const k of SIGNATURE_PROPS) {
    const v = propOf(i, k);
    parts.push(v === undefined || v === null ? '' : String(v));
  }
  parts.push([...(i.systems ?? [])].sort().join('+'), i.material ?? '', i.hierarchy?.parents?.[0]?.ifcClass ?? '', isBuildingContext(i) ? 'B' : 'X');
  return parts.join('|');
}
