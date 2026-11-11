// Selection sets: named groups of elements, persisted per model.
//
// Pure module (no DOM). Sets are stored by IFC globalId, not by numeric element id, so they survive a
// reconversion of the IFC file (ids are array indices and may change; globalIds do not).
//
// Storage layout: localStorage key `xray.sets.<modelName>` -> JSON { version: 1, sets: [{ name, globalIds }] }.
// A criteria set also has `kind: "criteria"` and `query` (src/query); its globalIds are the members found by the last
// evaluation, so readers that do not know criteria (older viewers, the cinematic tour) still see a static set.
// A missing key means "first load of this model": the default sets in DEFAULT_SETS are seeded. An existing key
// with an empty list means the user deleted everything, so nothing is seeded again.

import type { ElementId, ElementRecord, SceneModel } from './types';

export interface SelectionSet {
  name: string;
  globalIds: string[];
  /** Absent for a static set (explicit members). "criteria": members come from `query`. */
  kind?: 'criteria';
  /** Criteria query (SQL WHERE subset, src/query). Present only when kind is "criteria". */
  query?: string;
}

/** True for a criteria set (members re-evaluated from its query). */
export function isCriteria(s: SelectionSet): s is SelectionSet & { kind: 'criteria'; query: string } {
  return s.kind === 'criteria' && typeof s.query === 'string';
}

/** A clean copy: static sets keep only name and globalIds, criteria sets also kind and query. */
export function copySet(s: SelectionSet): SelectionSet {
  const globalIds = [...(s.globalIds ?? [])];
  return isCriteria(s) ? { name: s.name, globalIds, kind: 'criteria', query: s.query } : { name: s.name, globalIds };
}

/** The subset of the Web Storage API that this module uses. Lets tests pass an in-memory shim. */
export interface StorageLike {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem?(key: string): void;
}

/** In-memory StorageLike (tests, and the fallback when localStorage is unavailable). */
export class MemoryStorage implements StorageLike {
  readonly map = new Map<string, string>();
  getItem(key: string): string | null {
    return this.map.get(key) ?? null;
  }
  setItem(key: string, value: string): void {
    this.map.set(key, String(value));
  }
  removeItem(key: string): void {
    this.map.delete(key);
  }
}

/** Declarative rule for a default set. All given conditions must hold (AND). */
export interface DefaultSetDef {
  name: string;
  /** Element ifcClass is one of these. */
  classes?: string[];
  /** Element name contains this substring (case-insensitive). */
  nameContains?: string;
  /** Element is on the storey with this id. */
  storeyId?: number;
  /** Element's storey name matches this regular expression source (case-insensitive). */
  storeyName?: string;
}

/** Default sets per sample model, seeded the first time that model is loaded. */
export const DEFAULT_SETS: Readonly<Record<string, readonly DefaultSetDef[]>> = {
  building: [
    { name: 'Duct run', classes: ['IfcDuctSegment', 'IfcAirTerminal'] },
    { name: 'Roof beams', classes: ['IfcBeam'] },
  ],
  'fzk-haus': [
    { name: 'Rafters', classes: ['IfcMember'] },
    { name: 'Ground floor walls', classes: ['IfcWall', 'IfcWallStandardCase'], storeyName: 'erdgeschoss|ground' },
  ],
  synth5k: [
    { name: 'Level 0 ducts', classes: ['IfcDuctSegment'], storeyId: 0 },
    { name: 'Risers', nameContains: 'riser' },
  ],
  plumbing: [{ name: 'All pipes', classes: ['IfcPipeSegment'] }],
  // Synthetic process unit (tools/make_process_plant_ifc.py): piping, fittings and valves of every service (nozzles, tees and
  // the battery-limit spectacle blinds are fittings), the rack and support steel, instruments, foundations, the main equipment
  // (pumps, motors, exchangers, drums), the cable tray and the battery-limit blinds.
  'process-plant': [
    { name: 'Process piping', classes: ['IfcPipeSegment', 'IfcPipeFitting', 'IfcValve'] },
    { name: 'Pipe rack steel', classes: ['IfcColumn', 'IfcBeam', 'IfcMember'] },
    { name: 'Instruments', classes: ['IfcSensor'] },
    { name: 'Foundations', classes: ['IfcFooting'] },
    { name: 'Equipment', classes: ['IfcPump', 'IfcElectricMotor', 'IfcHeatExchanger', 'IfcTank'] },
    { name: 'Cable tray', classes: ['IfcCableCarrierSegment'] },
    { name: 'Battery-limit blinds', nameContains: 'spectacle blind' },
  ],
  // Every item the debris generator added is named "Debris ..." (bolts, offcuts, stray cluster, far stray, duplicate beams, zero-thickness wall).
  'debris-demo': [{ name: 'Debris', nameContains: 'debris' }],
};

export const STORAGE_PREFIX = 'xray.sets.';
export const EXPORT_SCHEMA = 'xray-sets/1';

export function storageKey(modelName: string): string {
  return STORAGE_PREFIX + modelName;
}

// ---------------------------------------------------------------- id mapping

/** Element ids -> globalIds (ids outside the model are dropped; duplicates removed; order kept). */
export function idsToGlobalIds(model: SceneModel, ids: Iterable<ElementId>): string[] {
  const out: string[] = [];
  const seen = new Set<string>();
  for (const id of ids) {
    const gid = model.elements[id]?.globalId;
    if (gid === undefined || seen.has(gid)) continue;
    seen.add(gid);
    out.push(gid);
  }
  return out;
}

/** GlobalIds -> element ids of this model. Unknown globalIds are skipped. */
export function globalIdsToIds(model: SceneModel, globalIds: Iterable<string>): ElementId[] {
  const out: ElementId[] = [];
  for (const g of globalIds) {
    const id = model.byGlobalId.get(g);
    if (id !== undefined) out.push(id);
  }
  return out;
}

/** Union of the element bounds as [minx, miny, minz, maxx, maxy, maxz], or null when `ids` is empty. */
export function unionBounds(model: SceneModel, ids: Iterable<ElementId>): [number, number, number, number, number, number] | null {
  let r: [number, number, number, number, number, number] | null = null;
  for (const id of ids) {
    const b = model.elements[id]?.bounds;
    if (!b) continue;
    if (!r) r = [b[0], b[1], b[2], b[3], b[4], b[5]];
    else {
      r[0] = Math.min(r[0], b[0]);
      r[1] = Math.min(r[1], b[1]);
      r[2] = Math.min(r[2], b[2]);
      r[3] = Math.max(r[3], b[3]);
      r[4] = Math.max(r[4], b[4]);
      r[5] = Math.max(r[5], b[5]);
    }
  }
  return r;
}

// ---------------------------------------------------------------- defaults

function matchesDef(model: SceneModel, e: ElementRecord, def: DefaultSetDef, storeyRe: RegExp | null): boolean {
  if (def.classes && !def.classes.includes(e.ifcClass)) return false;
  if (def.nameContains !== undefined && !(e.name ?? '').toLowerCase().includes(def.nameContains.toLowerCase())) return false;
  if (def.storeyId !== undefined && e.storey !== def.storeyId) return false;
  if (storeyRe) {
    const s = e.storey === null ? undefined : model.storeys.find((x) => x.id === e.storey);
    if (!s || !storeyRe.test(s.name)) return false;
  }
  return true;
}

/** Element ids matching a default-set rule. */
export function resolveDefault(model: SceneModel, def: DefaultSetDef): ElementId[] {
  const storeyRe = def.storeyName !== undefined ? new RegExp(def.storeyName, 'i') : null;
  const out: ElementId[] = [];
  for (const e of model.elements) if (matchesDef(model, e, def, storeyRe)) out.push(e.id);
  return out;
}

/** The default sets for a model name, resolved against the model. Rules that match nothing are dropped. */
export function defaultSetsFor(model: SceneModel, modelName: string): SelectionSet[] {
  const defs = DEFAULT_SETS[modelName] ?? [];
  const out: SelectionSet[] = [];
  for (const def of defs) {
    const ids = resolveDefault(model, def);
    if (ids.length > 0) out.push({ name: def.name, globalIds: idsToGlobalIds(model, ids) });
  }
  return out;
}

// ---------------------------------------------------------------- persistence

function isSet(x: unknown): x is SelectionSet {
  if (!x || typeof x !== 'object') return false;
  const o = x as Record<string, unknown>;
  if (typeof o['name'] !== 'string') return false;
  const gids = o['globalIds'];
  if (gids === undefined) return o['kind'] === 'criteria' && typeof o['query'] === 'string'; // hand-written criteria set
  return Array.isArray(gids) && gids.every((g) => typeof g === 'string');
}

/** Parse the stored JSON. Returns null for anything that is not a valid payload. */
export function parseStored(text: string | null): SelectionSet[] | null {
  if (text === null) return null;
  try {
    const v: unknown = JSON.parse(text);
    const list = Array.isArray(v) ? v : (v as { sets?: unknown } | null)?.sets;
    if (!Array.isArray(list)) return null;
    return list.filter(isSet).map(copySet);
  } catch {
    return null;
  }
}

/** Stored sets for a model, or null when nothing (valid) is stored. */
export function loadSets(storage: StorageLike, modelName: string): SelectionSet[] | null {
  try {
    return parseStored(storage.getItem(storageKey(modelName)));
  } catch {
    return null;
  }
}

/** Persist the sets. Returns false when the storage refused (quota, private mode). */
export function saveSets(storage: StorageLike, modelName: string, sets: readonly SelectionSet[]): boolean {
  try {
    storage.setItem(storageKey(modelName), JSON.stringify({ version: 1, sets }));
    return true;
  } catch {
    return false;
  }
}

/**
 * Stored sets for the model; if none are stored, the defaults for this model are seeded and saved.
 * (Models without defaults get an empty list, which is saved so the decision is made once.)
 */
export function loadOrSeed(storage: StorageLike, model: SceneModel, modelName: string): SelectionSet[] {
  const stored = loadSets(storage, modelName);
  if (stored) return stored;
  const seeded = defaultSetsFor(model, modelName);
  saveSets(storage, modelName, seeded);
  return seeded;
}

// ---------------------------------------------------------------- pure list operations

/** Unique name: "Foo" -> "Foo", then "Foo 2", "Foo 3" ... */
export function uniqueName(sets: readonly SelectionSet[], wanted: string, ignoreIndex = -1): string {
  const base = wanted.trim() || 'Set';
  const taken = new Set(sets.filter((_, i) => i !== ignoreIndex).map((s) => s.name));
  if (!taken.has(base)) return base;
  for (let n = 2; ; n++) if (!taken.has(`${base} ${n}`)) return `${base} ${n}`;
}

export function addSet(sets: readonly SelectionSet[], name: string, globalIds: string[]): SelectionSet[] {
  return [...sets, { name: uniqueName(sets, name), globalIds: [...globalIds] }];
}

/** Append a criteria set with its query and the members found now. */
export function addCriteriaSet(sets: readonly SelectionSet[], name: string, query: string, globalIds: string[]): SelectionSet[] {
  return [...sets, { name: uniqueName(sets, name), globalIds: [...globalIds], kind: 'criteria', query }];
}

/** Change the query (and members) of a set; a static set becomes a criteria set. */
export function setQuery(sets: readonly SelectionSet[], index: number, query: string, globalIds: string[]): SelectionSet[] {
  return sets.map((s, i) => (i === index ? { name: s.name, globalIds: [...globalIds], kind: 'criteria', query } : s));
}

/** Insert a copy of a set after it, named "<name> copy" (made unique). */
export function duplicateSet(sets: readonly SelectionSet[], index: number): SelectionSet[] {
  const src = sets[index];
  if (!src) return [...sets];
  const copy = { ...copySet(src), name: uniqueName(sets, `${src.name} copy`) };
  return [...sets.slice(0, index + 1), copy, ...sets.slice(index + 1)];
}

export function removeSet(sets: readonly SelectionSet[], index: number): SelectionSet[] {
  return sets.filter((_, i) => i !== index);
}

export function renameSet(sets: readonly SelectionSet[], index: number, name: string): SelectionSet[] {
  return sets.map((s, i) => (i === index ? { ...s, name: uniqueName(sets, name, index) } : s));
}

export function updateSet(sets: readonly SelectionSet[], index: number, globalIds: string[]): SelectionSet[] {
  return sets.map((s, i) => (i === index ? { ...s, globalIds: [...globalIds] } : s));
}

// ---------------------------------------------------------------- import / export

export function exportSets(modelName: string, sets: readonly SelectionSet[]): string {
  return JSON.stringify({ schema: EXPORT_SCHEMA, model: modelName, sets }, null, 2);
}

/**
 * Parse an export file. Accepts the export format or a bare array of sets. Returns null when invalid.
 * Merge into an existing list with mergeImported.
 */
export function parseImport(text: string): SelectionSet[] | null {
  return parseStored(text);
}

/** Imported sets replace same-named existing sets in place and are appended otherwise. */
export function mergeImported(existing: readonly SelectionSet[], imported: readonly SelectionSet[]): SelectionSet[] {
  const out = existing.map((s) => ({ ...s }));
  for (const s of imported) {
    const i = out.findIndex((x) => x.name === s.name);
    if (i >= 0) out[i] = copySet(s);
    else out.push(copySet(s));
  }
  return out;
}
