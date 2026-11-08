// The query view of a model: one flat row per element with the core columns and every property key.
// Rows are virtual: the accessors read the ElementRecord directly, so building the table costs one pass for the
// storey lookup and one for the property keys, and a query allocates nothing per element.

import type { ElementRecord, SceneModel } from '../types';
import type { Accessor, QueryTable } from './compile';
import type { Value } from './parser';

export type ColumnKind = 'string' | 'number' | 'boolean' | 'mixed' | 'empty';

export interface ColumnInfo {
  /** Canonical name, as the builder writes it. */
  name: string;
  /** Core column (not a property). */
  core: boolean;
  /** Rows with a non-NULL value. */
  count: number;
  kind: ColumnKind;
  /** Short description for the builder (core columns only). */
  doc?: string;
}

/** Core columns: canonical name, description. Matching ignores case; ALIASES adds other spellings. */
export const CORE_COLUMNS: ReadonlyArray<[string, string]> = [
  ['class', 'IFC class, such as IfcWall'],
  ['name', 'Element name'],
  ['storey', 'Storey name'],
  ['storeyElevation', 'Storey elevation, m'],
  ['material', 'Material name'],
  ['globalId', 'IFC GlobalId'],
  ['id', 'Viewer element index'],
  ['xMin', 'Bounds, viewer x, m'],
  ['xMax', 'Bounds, viewer x, m'],
  ['yMin', 'Bounds, viewer y (up), m'],
  ['yMax', 'Bounds, viewer y (up), m'],
  ['zMin', 'Bounds, viewer z, m'],
  ['zMax', 'Bounds, viewer z, m'],
  ['sizeX', 'Bounds size along x, m'],
  ['sizeY', 'Bounds size along y (height), m'],
  ['sizeZ', 'Bounds size along z, m'],
  ['volume', 'Bounding box volume, m3'],
];

const ALIASES: Record<string, string> = {
  ifcclass: 'class',
  type: 'class',
  minx: 'xMin',
  maxx: 'xMax',
  miny: 'yMin',
  maxy: 'yMax',
  minz: 'zMin',
  maxz: 'zMax',
  globalid: 'globalId',
  guid: 'globalId',
  elevation: 'storeyElevation',
};

const CORE_BY_LOWER = new Map<string, string>(CORE_COLUMNS.map(([n]) => [n.toLowerCase(), n]));

/** Canonical core column for a name (any case, aliases too), or null. */
export function coreColumn(name: string): string | null {
  const l = name.toLowerCase();
  return CORE_BY_LOWER.get(l) ?? ALIASES[l] ?? null;
}

const kindOf = (v: Value): ColumnKind => (v === null ? 'empty' : (typeof v as ColumnKind));
const merge = (a: ColumnKind, b: ColumnKind): ColumnKind => (a === 'empty' ? b : b === 'empty' || a === b ? a : 'mixed');

export class ModelTable implements QueryTable {
  readonly size: number;
  private readonly els: readonly ElementRecord[];
  private readonly storeyName: Array<string | null>;
  private readonly storeyElev: Array<number | null>;
  /** Property key -> rows with it. */
  private readonly propCount = new Map<string, number>();
  private readonly propKind = new Map<string, ColumnKind>();
  private readonly propLower = new Map<string, string>();
  /** Lower-case property name after the set name -> its key, or null when two sets have it (ambiguous). */
  private readonly propShort = new Map<string, string | null>();
  private readonly distinctCache = new Map<string, Array<{ value: Value; count: number }>>();
  private columnsCache: ColumnInfo[] | null = null;

  constructor(model: SceneModel) {
    this.els = model.elements;
    this.size = model.elements.length;
    const byId = new Map(model.storeys.map((s) => [s.id, s]));
    this.storeyName = new Array(this.size);
    this.storeyElev = new Array(this.size);
    for (let i = 0; i < this.size; i++) {
      const e = this.els[i]!;
      const s = e.storey === null ? undefined : byId.get(e.storey);
      this.storeyName[i] = s ? s.name : null;
      this.storeyElev[i] = s ? s.elevation : null;
      const p = e.props;
      if (p) {
        for (const k in p) {
          this.propCount.set(k, (this.propCount.get(k) ?? 0) + 1);
          this.propKind.set(k, merge(this.propKind.get(k) ?? 'empty', kindOf(p[k]!)));
        }
      }
    }
    for (const k of this.propCount.keys()) {
      const l = k.toLowerCase();
      if (!this.propLower.has(l)) this.propLower.set(l, k);
      const dot = k.indexOf('.');
      if (dot > 0) {
        const short = l.slice(dot + 1);
        this.propShort.set(short, this.propShort.has(short) ? null : k);
      }
    }
  }

  /** Element id of a row. */
  idOf(row: number): number {
    return this.els[row]!.id;
  }

  /** The element record behind a row. */
  elementAt(row: number): ElementRecord {
    return this.els[row]!;
  }

  /** Storey name of a row, or null. */
  storeyOf(row: number): string | null {
    return this.storeyName[row]!;
  }

  /** Every property key of the model (insertion order). */
  propKeys(): string[] {
    return [...this.propCount.keys()];
  }

  /** Canonical column name (core or property key), or null when the model has no such column. */
  resolve(name: string): string | null {
    const core = coreColumn(name);
    if (core) return core;
    if (this.propCount.has(name)) return name;
    const l = name.toLowerCase();
    // A bare property name finds the property when only one set has it: `discipline` for `XR_Classification.Discipline`.
    return this.propLower.get(l) ?? this.propShort.get(l) ?? null;
  }

  accessor(name: string): Accessor | null {
    const col = this.resolve(name);
    if (col === null) return null;
    const els = this.els;
    const b = (k: number): Accessor => (r) => els[r]!.bounds[k]!;
    switch (col) {
      case 'id':
        return (r) => els[r]!.id;
      case 'globalId':
        return (r) => els[r]!.globalId;
      case 'class':
        return (r) => els[r]!.ifcClass;
      case 'name':
        return (r) => els[r]!.name || null;
      case 'material':
        return (r) => els[r]!.material || null;
      case 'storey': {
        const s = this.storeyName;
        return (r) => s[r]!;
      }
      case 'storeyElevation': {
        const s = this.storeyElev;
        return (r) => s[r]!;
      }
      case 'xMin':
        return b(0);
      case 'yMin':
        return b(1);
      case 'zMin':
        return b(2);
      case 'xMax':
        return b(3);
      case 'yMax':
        return b(4);
      case 'zMax':
        return b(5);
      case 'sizeX':
        return (r) => els[r]!.bounds[3] - els[r]!.bounds[0];
      case 'sizeY':
        return (r) => els[r]!.bounds[4] - els[r]!.bounds[1];
      case 'sizeZ':
        return (r) => els[r]!.bounds[5] - els[r]!.bounds[2];
      case 'volume':
        return (r) => {
          const x = els[r]!.bounds;
          return (x[3] - x[0]) * (x[4] - x[1]) * (x[5] - x[2]);
        };
      default:
        return (r) => {
          const v = els[r]!.props?.[col];
          return v === undefined ? null : v;
        };
    }
  }

  /** The flat row of an element (for display and tests; queries use the accessors). */
  rowOf(row: number): Record<string, Value> {
    const out: Record<string, Value> = {};
    for (const [n] of CORE_COLUMNS) out[n] = this.accessor(n)!(row);
    const p = this.els[row]!.props;
    if (p) for (const k in p) out[k] = p[k]!;
    return out;
  }

  /** Columns present in the model: the core columns, then the property keys in alphabetical order. */
  columns(): ColumnInfo[] {
    if (this.columnsCache) return this.columnsCache;
    const out: ColumnInfo[] = [];
    for (const [n, doc] of CORE_COLUMNS) {
      const acc = this.accessor(n)!;
      let count = 0;
      let kind: ColumnKind = 'empty';
      for (let r = 0; r < this.size; r++) {
        const v = acc(r);
        if (v !== null) {
          count++;
          if (kind === 'empty') kind = kindOf(v);
        }
      }
      if (count > 0 || n === 'storey' || n === 'name' || n === 'material') out.push({ name: n, core: true, count, kind, doc });
    }
    const keys = [...this.propCount.keys()].sort((a, b) => a.localeCompare(b));
    for (const k of keys) out.push({ name: k, core: false, count: this.propCount.get(k)!, kind: this.propKind.get(k) ?? 'empty' });
    this.columnsCache = out;
    return out;
  }

  /** Kind of the values of a column ('empty' for an unknown column). */
  kind(name: string): ColumnKind {
    const col = this.resolve(name);
    if (col === null) return 'empty';
    return this.columns().find((c) => c.name === col)?.kind ?? 'empty';
  }

  /** Distinct non-NULL values of a column, most frequent first (ties in value order), at most `limit`. */
  distinct(name: string, limit = 200): Array<{ value: Value; count: number }> {
    const col = this.resolve(name);
    if (col === null) return [];
    let all = this.distinctCache.get(col);
    if (!all) {
      const acc = this.accessor(col)!;
      const m = new Map<string, { value: Value; count: number }>();
      for (let r = 0; r < this.size; r++) {
        const v = acc(r);
        if (v === null) continue;
        const key = `${typeof v}:${String(v)}`;
        const hit = m.get(key);
        if (hit) hit.count++;
        else m.set(key, { value: v, count: 1 });
      }
      all = [...m.values()].sort((a, b) => b.count - a.count || String(a.value).localeCompare(String(b.value), undefined, { numeric: true }));
      this.distinctCache.set(col, all);
    }
    return all.slice(0, limit);
  }
}

const tables = new WeakMap<SceneModel, ModelTable>();

/** Forget the cached table of a model. Call after properties were added or changed (the classifier writes some). */
export function resetModelTable(model: SceneModel): void {
  tables.delete(model);
}

/** The (cached) query table of a model. */
export function modelTable(model: SceneModel): ModelTable {
  let t = tables.get(model);
  if (!t) {
    t = new ModelTable(model);
    tables.set(model, t);
  }
  return t;
}
