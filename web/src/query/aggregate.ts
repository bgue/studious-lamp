// Aggregate summaries over the elements of a model: `count where ...`, `sum length where ...`, `avg|min|max <qty>`,
// several aggregates at once and `by <column>` groups. The condition after `where` is the criteria language of
// parser.ts (parsed by it, so the error positions and the semantics are the same). Pure module, no DOM.
//
// Grammar (keywords case-insensitive, `of` and parentheses around the quantity are accepted and ignored):
//   summary   := agg ( ( ',' | AND ) agg )* [ where cond ] [ by column ]      (where and by may come in either order)
//   agg       := COUNT | ( SUM | AVG | MIN | MAX ) [ OF ] qty
//   qty       := one or more words: `length`, `net volume`, `Qto_WallBaseQuantities.Length`, "quoted key"
//
// A quantity name resolves per element: `length` means the Length of whatever Qto or Pset the element carries
// (Qto_BeamBaseQuantities.Length, BaseQuantities.Length ...), `volume` NetVolume, else GrossVolume, `area` NetArea, GrossArea,
// NetSideArea ... An element that has none gets a geometric estimate when one is possible (see geoEstimate.ts) and that value
// is counted as estimated. A value that does not parse as a number is skipped and reported.

import { QueryError, tokenize } from './lexer';
import type { Token } from './lexer';
import { compile } from './compile';
import { parseQuery } from './parser';
import type { ModelTable } from './table';

export type AggFn = 'count' | 'sum' | 'avg' | 'min' | 'max';
export type Dim = 'length' | 'area' | 'volume' | 'mass' | 'other';
export type EstKind = 'length' | 'height' | 'volume' | 'area';

const FNS = new Set<string>(['count', 'sum', 'avg', 'min', 'max']);
export const SYMBOL: Record<AggFn, string> = { count: '#', sum: 'Σ', avg: 'avg', min: 'min', max: 'max' };

export interface AggSpec {
  fn: AggFn;
  /** The quantity as typed (null for count). */
  qty: string | null;
  /** Character offset of the quantity (or of the function word for count). */
  pos: number;
}

export interface AggQuery {
  aggs: AggSpec[];
  /** Condition text (no `where`), or null. */
  where: string | null;
  /** Character offset of the condition in the input. */
  wherePos: number;
  by: { name: string; pos: number } | null;
}

// ---------------------------------------------------------------------------------------------------- parsing

const isWord = (t: Token | undefined, w: string): boolean => !!t && t.type === 'ident' && t.value.toLowerCase() === w;
const isPunct = (t: Token | undefined, p: string): boolean => !!t && t.type === 'punct' && t.value === p;

function describeTok(t: Token): string {
  if (t.type === 'eof') return 'the end of the text';
  if (t.type === 'string') return `'${t.value}'`;
  return `"${t.value}"`;
}

/** `?` in front of the text is allowed and ignored (the offsets stay the same). */
function blankQuestion(src: string): string {
  const m = /^(\s*)\?/.exec(src);
  return m ? `${m[1]} ${src.slice(m[0].length)}` : src;
}

/** Cheap check: does the text start like an aggregate summary? (No model needed; `parseAggregate` gives the errors.) */
export function looksLikeAggregate(src: string): boolean {
  try {
    const toks = tokenize(blankQuestion(src));
    const t0 = toks[0]!;
    if (t0.type !== 'ident' || !FNS.has(t0.value.toLowerCase())) return false;
    const t1 = toks[1]!;
    if (t0.value.toLowerCase() === 'count') return t1.type === 'eof' || isWord(t1, 'where') || isWord(t1, 'by') || isPunct(t1, ',') || (t1.type === 'keyword' && t1.value === 'AND');
    return t1.type === 'ident' || t1.type === 'qident' || isPunct(t1, '(');
  } catch {
    return false;
  }
}

/** True when the text names a clause (where, by) or several aggregates: it can only be a summary, never plain text. */
export function isExplicitAggregate(src: string): boolean {
  try {
    const toks = tokenize(blankQuestion(src));
    return toks.some((t, i) => i > 0 && (isWord(t, 'where') || isWord(t, 'by') || isPunct(t, ',')));
  } catch {
    return false;
  }
}

/** Parse a summary. Throws QueryError with the character position of the problem. */
export function parseAggregate(input: string): AggQuery {
  const src = blankQuestion(input);
  const toks = tokenize(src);
  let i = 0;
  const t = (): Token => toks[i]!;
  const aggs: AggSpec[] = [];

  if (t().type === 'eof') throw new QueryError('The summary is empty. Write for example "count where class = \'IfcWall\'" or "sum length"', 0);
  for (;;) {
    const f = t();
    if (f.type !== 'ident' || !FNS.has(f.value.toLowerCase())) {
      throw new QueryError(`Expected count, sum, avg, min or max, found ${describeTok(f)}`, f.pos);
    }
    i++;
    const fn = f.value.toLowerCase() as AggFn;
    if (fn === 'count') {
      aggs.push({ fn, qty: null, pos: f.pos });
    } else {
      if (isWord(t(), 'of')) i++;
      const paren = isPunct(t(), '(');
      if (paren) i++;
      const words: Token[] = [];
      while ((t().type === 'ident' || t().type === 'qident') && !isWord(t(), 'where') && !isWord(t(), 'by')) words.push(toks[i++]!);
      if (words.length === 0) {
        throw new QueryError(`Expected a quantity after ${fn}, for example "${fn} length", found ${describeTok(t())}`, t().pos);
      }
      if (paren) {
        if (!isPunct(t(), ')')) throw new QueryError(`Expected ")" after the quantity, found ${describeTok(t())}`, t().pos);
        i++;
      }
      aggs.push({ fn, qty: words.map((w) => w.value).join(' '), pos: words[0]!.pos });
    }
    if (isPunct(t(), ',') || (t().type === 'keyword' && t().value === 'AND')) {
      i++;
      continue;
    }
    break;
  }

  let where: string | null = null;
  let wherePos = -1;
  let by: AggQuery['by'] = null;
  while (t().type !== 'eof') {
    const c = t();
    if (isWord(c, 'where')) {
      if (where !== null) throw new QueryError('The text has two "where" parts: join the conditions with AND', c.pos);
      i++;
      const start = c.end;
      // The condition runs to the next top-level `by` word or the end.
      let depth = 0;
      let j = i;
      for (; toks[j]!.type !== 'eof'; j++) {
        const x = toks[j]!;
        if (isPunct(x, '(')) depth++;
        else if (isPunct(x, ')')) depth--;
        else if (depth <= 0 && isWord(x, 'by')) break;
      }
      if (j === i) throw new QueryError(`Expected a condition after "where", found ${describeTok(toks[j]!)}`, toks[j]!.pos);
      const end = toks[j]!.type === 'eof' ? src.length : toks[j]!.pos;
      // Blank prefix: the parser reports positions in the whole input.
      const padded = ' '.repeat(start) + src.slice(start, end);
      parseQuery(padded);
      where = padded.slice(start).trim();
      wherePos = start + (padded.slice(start).length - padded.slice(start).trimStart().length);
      i = j;
      continue;
    }
    if (isWord(c, 'by')) {
      if (by) throw new QueryError('The text has two "by" parts: group by one column', c.pos);
      i++;
      const n = t();
      if (n.type !== 'ident' && n.type !== 'qident') throw new QueryError(`Expected a column name after "by", found ${describeTok(n)}`, n.pos);
      by = { name: n.value, pos: n.pos };
      i++;
      continue;
    }
    throw new QueryError(`Unexpected ${describeTok(c)}: expected "where", "by" or the end of the text`, c.pos);
  }
  return { aggs, where, wherePos, by };
}

// ---------------------------------------------------------------------------------------------------- numbers

const NUM_TEXT = /^[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?$/;

/** A number from a property value: a finite number, or text that is only a number. Otherwise null. */
export function toNumber(v: unknown): number | null {
  if (typeof v === 'number') return Number.isFinite(v) ? v : null;
  if (typeof v === 'string') {
    const s = v.trim();
    return NUM_TEXT.test(s) ? Number(s) : null;
  }
  return null;
}

function notNumberReason(key: string, v: unknown): string {
  if (typeof v === 'number') return `${key} is not finite (${String(v)})`;
  if (typeof v === 'boolean') return `${key} is a yes/no value (${String(v)})`;
  const s = String(v);
  return `${key} is not a number ("${s.length > 24 ? `${s.slice(0, 24)}...` : s}")`;
}

// ---------------------------------------------------------------------------------------------------- quantity names

interface Family {
  segs: string[];
  dim: Dim;
  est: EstKind | null;
}

/** Fuzzy names: the last segment of the property key, lower case without punctuation, in order of preference. */
const FAMILIES: Record<string, Family> = {
  length: { segs: ['length', 'netlength', 'grosslength'], dim: 'length', est: 'length' },
  width: { segs: ['width', 'nominalwidth'], dim: 'length', est: null },
  height: { segs: ['height', 'nominalheight'], dim: 'length', est: 'height' },
  depth: { segs: ['depth'], dim: 'length', est: null },
  thickness: { segs: ['width', 'depth', 'thickness'], dim: 'length', est: null },
  perimeter: { segs: ['perimeter'], dim: 'length', est: null },
  area: { segs: ['netarea', 'grossarea', 'netsidearea', 'grosssidearea', 'netfootprintarea', 'grossfootprintarea', 'outersurfacearea', 'area'], dim: 'area', est: 'area' },
  sidearea: { segs: ['netsidearea', 'grosssidearea'], dim: 'area', est: null },
  footprint: { segs: ['netfootprintarea', 'grossfootprintarea'], dim: 'area', est: null },
  section: { segs: ['crosssectionarea'], dim: 'area', est: null },
  crosssection: { segs: ['crosssectionarea'], dim: 'area', est: null },
  volume: { segs: ['netvolume', 'grossvolume', 'volume'], dim: 'volume', est: 'volume' },
  weight: { segs: ['netweight', 'grossweight', 'weight'], dim: 'mass', est: null },
  mass: { segs: ['netweight', 'grossweight', 'weight', 'mass'], dim: 'mass', est: null },
};

const norm = (s: string): string => s.toLowerCase().replace(/[^a-z0-9]/g, '');
const lastSeg = (key: string): string => norm(key.slice(key.lastIndexOf('.') + 1));

function dimOf(seg: string): Dim {
  if (seg.includes('volume')) return 'volume';
  if (seg.includes('area')) return 'area';
  if (/weight|mass/.test(seg)) return 'mass';
  if (/length|width|height|depth|perimeter|thickness|offset|elevation|^size[xyz]$|^[xyz](min|max)$/.test(seg)) return 'length';
  return 'other';
}

function estOf(seg: string): EstKind | null {
  if (seg.endsWith('volume')) return 'volume';
  if (seg === 'length') return 'length';
  if (seg === 'height') return 'height';
  if (seg === 'area' || seg === 'netarea' || seg === 'grossarea') return 'area';
  return null;
}

export interface QtyPlan {
  /** As typed. */
  name: string;
  /** Short name for display: the typed word, or the last segment of the key. */
  label: string;
  dim: Dim;
  /** Property keys to read, in order of preference; the first number wins. */
  keys: string[];
  /** Core column (sizeY, storeyElevation ...) when the name is one and no family applies. */
  core: string | null;
  est: EstKind | null;
}

/**
 * Resolve a quantity name against the properties of a model. Null when nothing matches. Order: a fuzzy family name
 * (`length`, `area`, `volume` ...), the exact key, the key's last segment, a numeric core column, a part of a last segment.
 */
export function resolveQuantity(table: ModelTable, name: string): QtyPlan | null {
  const n = norm(name);
  if (n === '') return null;
  const keys = table.propKeys();
  const segOf = new Map<string, string>();
  for (const k of keys) segOf.set(k, lastSeg(k));
  const order = (list: string[], segs: string[]): string[] =>
    list.sort((a, b) => segs.indexOf(segOf.get(a)!) - segs.indexOf(segOf.get(b)!) || a.localeCompare(b));

  const fam = FAMILIES[n];
  if (fam) {
    const hit = order(keys.filter((k) => fam.segs.includes(segOf.get(k)!)), fam.segs);
    if (hit.length > 0 || fam.est) return { name, label: name.trim().toLowerCase(), dim: fam.dim, keys: hit, core: null, est: fam.est };
  }
  const exact = keys.filter((k) => norm(k) === n);
  if (exact.length > 0) return { name, label: segOf.get(exact[0]!)! === n ? exact[0]!.slice(exact[0]!.lastIndexOf('.') + 1) : exact[0]!, dim: dimOf(segOf.get(exact[0]!)!), keys: exact, core: null, est: estOf(segOf.get(exact[0]!)!) };
  const bySeg = keys.filter((k) => segOf.get(k) === n);
  if (bySeg.length > 0) {
    const label = bySeg[0]!.slice(bySeg[0]!.lastIndexOf('.') + 1);
    return { name, label, dim: dimOf(n), keys: bySeg.sort(), core: null, est: estOf(n) };
  }
  const core = table.resolve(name);
  if (core && table.kind(core) === 'number') return { name, label: core, dim: dimOf(norm(core)), keys: [], core, est: null };
  if (n.length >= 3) {
    const part = keys.filter((k) => segOf.get(k)!.includes(n)).sort((a, b) => segOf.get(a)!.length - segOf.get(b)!.length || a.localeCompare(b));
    if (part.length > 0) {
      const segs = [...new Set(part.map((k) => segOf.get(k)!))];
      const label = part[0]!.slice(part[0]!.lastIndexOf('.') + 1);
      return { name, label, dim: dimOf(segs[0]!), keys: part, core: null, est: estOf(segs[0]!) };
    }
  }
  return null;
}

// ---------------------------------------------------------------------------------------------------- geometry hook

/** Geometric estimates for an element. A number is the estimate, a string the reason there is none. Implemented in geoEstimate.ts. */
export interface GeoEstimator {
  volume(id: number): number | string;
  area(id: number): number | string;
}

// ---------------------------------------------------------------------------------------------------- aggregation

export interface AggOptions {
  /** Unit of length of the property values. The model's own (always 'm' for now). */
  lengthUnit?: string;
  geo?: GeoEstimator | null;
  /** Elements that count when there is no `where` (not hidden). Default: all. */
  visible?: ((id: number) => boolean) | null;
  /** Cap of the stored skipped list (the count is always exact). */
  skippedCap?: number;
}

export interface AggResult {
  fn: AggFn;
  /** Quantity label ('' for count). */
  label: string;
  dim: Dim;
  unit: string;
  /** Null when there is no value (avg, min, max of nothing). Count and sum give 0. */
  value: number | null;
  /** Values used. */
  n: number;
  /** Of those, geometric estimates. */
  estimated: number;
  /** Elements matched whose quantity was missing or not a number. */
  skipped: number;
}

export interface GroupResult {
  key: string;
  count: number;
  aggs: AggResult[];
}

export interface SkippedRow {
  id: number;
  globalId: string;
  name: string;
  qty: string;
  reason: string;
}

export interface QtyColumn {
  plan: QtyPlan;
  /** Value per summarised element (NaN: none). */
  vals: Float64Array;
  /** Where each value came from: index into `keys`, -1 estimated, -2 none. */
  src: Int16Array;
  keys: string[];
}

export interface QuantitySummary {
  text: string;
  query: AggQuery;
  /** Table rows and element ids that were summarised (matched, or visible when there is no where). */
  rows: Int32Array;
  ids: number[];
  matched: number;
  qtys: QtyColumn[];
  aggs: AggResult[];
  groups: GroupResult[] | null;
  groupBy: string | null;
  /** Group index per summarised element (empty without `by`). */
  groupOf: Int32Array;
  groupKeys: string[];
  skipped: SkippedRow[];
  skippedCount: number;
  /** Estimated values over all quantities. */
  estimated: number;
  /** Names the condition used that no element has. */
  unknown: string[];
  /** Unit of the first quantity aggregate ('' when there is none). */
  unit: string;
  /** Class of every matched element when they share one, else null. */
  commonClass: string | null;
  ms: number;
  table: ModelTable;
}

export function unitFor(dim: Dim, lengthUnit = 'm'): string {
  switch (dim) {
    case 'length':
      return lengthUnit;
    case 'area':
      return `${lengthUnit}²`;
    case 'volume':
      return `${lengthUnit}³`;
    case 'mass':
      return 'kg';
    default:
      return '';
  }
}

class Reader {
  src = -2;
  reason = '';
  private readonly acc: ((r: number) => unknown) | null;
  constructor(
    private readonly table: ModelTable,
    readonly plan: QtyPlan,
    private readonly geo: GeoEstimator | null,
  ) {
    this.acc = plan.core ? table.accessor(plan.core) : null;
  }

  /** Value of the quantity for a row (NaN when there is none; `src` and `reason` say what happened). */
  read(row: number): number {
    const el = this.table.elementAt(row);
    const p = this.plan;
    const props = el.props;
    let bad = '';
    if (props) {
      for (let k = 0; k < p.keys.length; k++) {
        const raw = props[p.keys[k]!];
        if (raw === undefined) continue;
        const x = typeof raw === 'number' ? raw : toNumber(raw);
        if (x !== null && Number.isFinite(x)) {
          this.src = k;
          return x;
        }
        if (!bad) bad = notNumberReason(p.keys[k]!, raw);
      }
    }
    if (this.acc) {
      const v = this.acc(row);
      const x = toNumber(v);
      if (x !== null) {
        this.src = 0;
        return x;
      }
      this.src = -2;
      this.reason = v === null ? `${p.core} is empty` : notNumberReason(p.core!, v);
      return NaN;
    }
    if (bad) {
      this.src = -2;
      this.reason = bad;
      return NaN;
    }
    // No property at all: a geometric estimate, when the quantity has one.
    if (p.est) {
      const e = this.estimate(p.est, row);
      if (typeof e === 'number') {
        this.src = -1;
        return e;
      }
      this.src = -2;
      this.reason = `no ${p.label} property, and no estimate: ${e}`;
      return NaN;
    }
    this.src = -2;
    this.reason = `no ${p.label} property`;
    return NaN;
  }

  private estimate(kind: EstKind, row: number): number | string {
    const el = this.table.elementAt(row);
    const b = el.bounds;
    const ok = b.every((x) => Number.isFinite(x)) && b[3] >= b[0] && b[4] >= b[1] && b[5] >= b[2];
    if (kind === 'length' || kind === 'height') {
      if (!ok) return 'the element has no geometry';
      const v = kind === 'height' ? b[4] - b[1] : Math.max(b[3] - b[0], b[4] - b[1], b[5] - b[2]);
      return v > 0 ? v : 'the bounds are empty';
    }
    if (!this.geo) return 'no mesh is available';
    if (!ok) return 'the element has no geometry';
    return kind === 'volume' ? this.geo.volume(el.id) : this.geo.area(el.id);
  }
}

interface Acc {
  n: Int32Array;
  sum: Float64Array;
  min: Float64Array;
  max: Float64Array;
  est: Int32Array;
  skp: Int32Array;
}
const newAcc = (slots: number): Acc => ({
  n: new Int32Array(slots),
  sum: new Float64Array(slots),
  min: new Float64Array(slots).fill(Infinity),
  max: new Float64Array(slots).fill(-Infinity),
  est: new Int32Array(slots),
  skp: new Int32Array(slots),
});

function result(spec: AggSpec, plan: QtyPlan | null, a: Acc | null, slot: number, matched: number, lengthUnit: string): AggResult {
  if (spec.fn === 'count' || !plan || !a) {
    return { fn: 'count', label: '', dim: 'other', unit: '', value: matched, n: matched, estimated: 0, skipped: 0 };
  }
  const n = a.n[slot]!;
  let value: number | null;
  switch (spec.fn) {
    case 'sum':
      value = a.sum[slot]!;
      break;
    case 'avg':
      value = n > 0 ? a.sum[slot]! / n : null;
      break;
    case 'min':
      value = n > 0 ? a.min[slot]! : null;
      break;
    default:
      value = n > 0 ? a.max[slot]! : null;
  }
  return { fn: spec.fn, label: plan.label, dim: plan.dim, unit: unitFor(plan.dim, lengthUnit), value, n, estimated: a.est[slot]!, skipped: a.skp[slot]! };
}

/** Core group columns with friendly names. */
const GROUP_ALIASES: Record<string, string> = { level: 'storey', floor: 'storey', classes: 'class', ifcclass: 'class', type: 'class' };

/** Run a parsed summary over the matched rows. Throws QueryError for a quantity or group column the model does not have. */
export function aggregate(table: ModelTable, text: string, q: AggQuery, rows: ArrayLike<number>, opts: AggOptions = {}, unknown: string[] = []): QuantitySummary {
  const t0 = performance.now();
  const lengthUnit = opts.lengthUnit ?? 'm';
  const geo = opts.geo ?? null;
  const m = rows.length;

  // Distinct quantities.
  const plans: QtyPlan[] = [];
  const planOf: number[] = []; // per agg
  for (const s of q.aggs) {
    if (s.qty === null) {
      planOf.push(-1);
      continue;
    }
    let idx = plans.findIndex((p) => norm(p.name) === norm(s.qty!));
    if (idx < 0) {
      const p = resolveQuantity(table, s.qty);
      if (!p) {
        throw new QueryError(`No quantity or property matches "${s.qty}". Try length, area or volume, or a property key such as Qto_WallBaseQuantities.Length`, s.pos);
      }
      idx = plans.push(p) - 1;
    }
    planOf.push(idx);
  }

  // Groups.
  let groupOf = new Int32Array(0);
  let groupKeys: string[] = [];
  if (q.by) {
    const alias = GROUP_ALIASES[q.by.name.toLowerCase()];
    const col = table.resolve(alias ?? q.by.name);
    if (!col) throw new QueryError(`No element has a column or property "${q.by.name}" to group by. Try storey, class or material`, q.by.pos);
    const acc = table.accessor(col)!;
    groupOf = new Int32Array(m);
    const index = new Map<string, number>();
    for (let i = 0; i < m; i++) {
      const v = acc(rows[i]!);
      const key = v === null || v === '' ? '(none)' : String(v);
      let g = index.get(key);
      if (g === undefined) {
        g = groupKeys.length;
        groupKeys.push(key);
        index.set(key, g);
      }
      groupOf[i] = g;
    }
  } else groupKeys = [];
  const G = q.by ? groupKeys.length : 0;
  const slots = G + 1; // the last slot is the total
  const total = G;

  const readers = plans.map((p) => new Reader(table, p, geo));
  const cols: QtyColumn[] = plans.map((p) => ({ plan: p, vals: new Float64Array(m), src: new Int16Array(m), keys: p.keys.length > 0 ? p.keys : p.core ? [p.core] : [] }));
  const accs = plans.map(() => newAcc(slots));
  const groupCount = new Int32Array(slots);
  const skipped: SkippedRow[] = [];
  const cap = opts.skippedCap ?? 5000;
  const skipCount = new Int32Array(plans.length);

  const classes = new Set<string>();
  for (let i = 0; i < m; i++) {
    const row = rows[i]!;
    const g = q.by ? groupOf[i]! : total;
    groupCount[g]!++;
    if (g !== total) groupCount[total]!++;
    if (classes.size < 2) classes.add(table.elementAt(row).ifcClass);
    for (let qi = 0; qi < readers.length; qi++) {
      const r = readers[qi]!;
      const a = accs[qi]!;
      const v = r.read(row);
      cols[qi]!.vals[i] = v;
      cols[qi]!.src[i] = r.src;
      if (v !== v) {
        a.skp[g]!++;
        if (g !== total) a.skp[total]!++;
        skipCount[qi]!++;
        if (skipped.length < cap) {
          const el = table.elementAt(row);
          skipped.push({ id: el.id, globalId: el.globalId, name: el.name ?? '', qty: r.plan.label, reason: r.reason });
        }
        continue;
      }
      const est = r.src === -1 ? 1 : 0;
      for (let pass = 0; pass < 2; pass++) {
        const s = pass === 0 ? g : total;
        if (pass === 1 && g === total) break;
        a.n[s]!++;
        a.sum[s]! += v;
        if (v < a.min[s]!) a.min[s] = v;
        if (v > a.max[s]!) a.max[s] = v;
        a.est[s]! += est;
      }
    }
  }

  const aggResults = (slot: number, matched: number): AggResult[] =>
    q.aggs.map((s, k) => result(s, planOf[k]! >= 0 ? plans[planOf[k]!]! : null, planOf[k]! >= 0 ? accs[planOf[k]!]! : null, slot, matched, lengthUnit));
  const aggs = aggResults(total, m);
  let groups: GroupResult[] | null = null;
  if (q.by) {
    groups = groupKeys.map((key, g) => ({ key, count: groupCount[g]!, aggs: aggResults(g, groupCount[g]!) }));
    // Largest first by the first aggregate that has a value (count: the count), ties in natural order.
    const lead = q.aggs.findIndex((s) => s.fn !== 'count');
    const k = lead >= 0 ? lead : 0;
    groups.sort((a, b) => (b.aggs[k]!.value ?? -Infinity) - (a.aggs[k]!.value ?? -Infinity) || a.key.localeCompare(b.key, undefined, { numeric: true }));
  }
  const firstQ = aggs.find((a) => a.fn !== 'count');
  const ids = new Array<number>(m);
  for (let i = 0; i < m; i++) ids[i] = table.elementAt(rows[i]!).id;
  let estimated = 0;
  for (const a of accs) estimated += a.est[total]!;
  let skippedCount = 0;
  for (const c of skipCount) skippedCount += c;
  return {
    text,
    query: q,
    rows: Int32Array.from(rows as ArrayLike<number>),
    ids,
    matched: m,
    qtys: cols,
    aggs,
    groups,
    groupBy: q.by ? q.by.name : null,
    groupOf,
    groupKeys,
    skipped,
    skippedCount,
    estimated,
    unknown,
    unit: firstQ ? firstQ.unit : '',
    commonClass: m > 0 && classes.size === 1 ? [...classes][0]! : null,
    ms: performance.now() - t0,
    table,
  };
}

/**
 * Parse and run a summary on a model table. Without `where` it covers the visible elements (`opts.visible`), with it the
 * matching ones, hidden or not, like the selection a plain query makes. Throws QueryError.
 */
export function runAggregate(table: ModelTable, text: string, opts: AggOptions = {}): QuantitySummary {
  const q = parseAggregate(text);
  let unknown: string[] = [];
  const rows: number[] = [];
  if (q.where !== null) {
    const c = compile(parseQuery(' '.repeat(q.wherePos) + q.where), table);
    unknown = c.unknown;
    for (let r = 0; r < table.size; r++) if (c.test(r)) rows.push(r);
  } else {
    const vis = opts.visible;
    for (let r = 0; r < table.size; r++) if (!vis || vis(table.idOf(r))) rows.push(r);
  }
  return aggregate(table, text, q, rows, opts, unknown);
}

// ---------------------------------------------------------------------------------------------------- display

/** A quantity with sensible rounding: 3 decimals below 1, 2 below 10, 1 below 1000, none from 1000; trailing zeros dropped. */
export function formatNumber(v: number): string {
  if (!Number.isFinite(v)) return String(v);
  const a = Math.abs(v);
  const d = a >= 1000 ? 0 : a >= 10 ? 1 : a >= 1 ? 2 : a >= 0.001 ? 3 : 0;
  let s = a < 0.001 && a > 0 ? v.toExponential(1) : v.toFixed(d);
  if (s.includes('.') && !s.includes('e')) s = s.replace(/\.?0+$/, '');
  if (a >= 1000) s = s.replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
  return s === '-0' ? '0' : s;
}

export function formatValue(v: number | null, unit: string): string {
  if (v === null) return '–';
  return unit ? `${formatNumber(v)} ${unit}` : formatNumber(v);
}

/** `IfcPipeSegment` -> `pipe segments`. */
export function classNoun(cls: string, n: number): string {
  const words = cls.replace(/^Ifc/, '').replace(/([a-z0-9])([A-Z])/g, '$1 $2').toLowerCase();
  if (n === 1) return words;
  const i = words.lastIndexOf(' ') + 1;
  const last = words.slice(i);
  const plural = /(s|x|ch|sh)$/.test(last) ? `${last}es` : /[^aeiou]y$/.test(last) ? `${last.slice(0, -1)}ies` : `${last}s`;
  return words.slice(0, i) + plural;
}

function aggLabel(a: AggResult): string {
  return a.fn === 'count' ? `${formatNumber(a.value ?? 0)} ${a.value === 1 ? 'element' : 'elements'}` : `${SYMBOL[a.fn]} ${a.label} ${formatValue(a.value, a.unit)}${a.estimated > 0 ? ` (${a.estimated} est.)` : ''}`;
}

/** The short answer, one or two lines: `42 pipe segments · Σ length 318.4 m (6 est.)`, then the top 3 groups. */
export function summaryLines(s: QuantitySummary): string[] {
  const n = s.matched;
  const noun = s.commonClass ? classNoun(s.commonClass, n) : n === 1 ? 'element' : 'elements';
  const parts = [`${formatNumber(n)} ${noun}`];
  for (const a of s.aggs) if (a.fn !== 'count') parts.push(aggLabel(a));
  if (s.skippedCount > 0) parts.push(`${s.skippedCount} skipped`);
  const lines = [parts.join(' · ')];
  if (s.groups && s.groups.length > 0) {
    const k = s.aggs.findIndex((a) => a.fn !== 'count');
    const shown = s.groups.slice(0, 3).map((g) => {
      const a = g.aggs[k >= 0 ? k : 0]!;
      return `${g.key}: ${a.fn === 'count' ? formatNumber(a.value ?? 0) : formatValue(a.value, a.unit)}`;
    });
    const more = s.groups.length - 3;
    lines.push(shown.join(' · ') + (more > 0 ? ` · +${more} more (console)` : ''));
  }
  return lines;
}
