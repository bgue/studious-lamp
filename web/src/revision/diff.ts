// diffModels: compare two snapshots (design 3.2, 3.3). Pure. GlobalIds first, then the signature match for what is left.
// The result lists every element that is not unchanged; unchanged ones are only counted.

import { frameOf, compareShape, estimateOffset, matchLeftovers } from './match';
import { stripFederation } from './snapshot';
import { CATEGORIES, CHANGE_FLAGS, withOptions } from './types';
import type { Category, ChangeFlag, DiffEntry, ModelSnapshot, PropValue, RevisionDiff, RevisionOptions, Vec3 } from './types';

const sameStorey = (a: ModelSnapshot['storey'][number], b: ModelSnapshot['storey'][number], tol: number): boolean => {
  if (!a || !b) return !a && !b;
  return a.name === b.name && Math.abs(a.elevation - b.elevation) <= tol;
};

const sameList = (a: readonly string[], b: readonly string[]): boolean => a.length === b.length && a.every((x, i) => x === b[i]);

const propEqual = (a: PropValue | undefined, b: PropValue | undefined, tol: number): boolean => {
  if (a === b) return true;
  if (typeof a === 'number' && typeof b === 'number') return Math.abs(a - b) / Math.max(Math.abs(a), Math.abs(b), 1e-12) <= tol;
  return false;
};

/** The loaded properties that differ (added, removed, changed). Attr.* keys and the ignored prefixes are not compared. */
export function diffProps(a: Record<string, PropValue> | null, b: Record<string, PropValue> | null, o: Pick<RevisionOptions, 'propRelTol' | 'ignoreProps'>): NonNullable<DiffEntry['props']> {
  const out: NonNullable<DiffEntry['props']> = [];
  if (!a && !b) return out;
  const skip = (k: string): boolean => k.startsWith('Attr.') || o.ignoreProps.some((p) => k.startsWith(p));
  const seen = new Set<string>();
  if (a) for (const k of Object.keys(a)) {
    if (skip(k)) continue;
    seen.add(k);
    const bv = b?.[k];
    if (bv === undefined) out.push({ key: k, before: a[k]! });
    else if (!propEqual(a[k], bv, o.propRelTol)) out.push({ key: k, before: a[k]!, after: bv });
  }
  if (b) for (const k of Object.keys(b)) if (!skip(k) && !seen.has(k) && !(a && k in a)) out.push({ key: k, after: b[k]! });
  return out.sort((x, y) => (x.key < y.key ? -1 : x.key > y.key ? 1 : 0));
}

/** The attribute, property and structure flags of a matched pair (everything but geometry and placement). */
const NO_ATTRIBUTE_CHANGE: { flags: ChangeFlag[]; props?: DiffEntry['props'] } = Object.freeze({ flags: Object.freeze([]) as unknown as ChangeFlag[] });

function attributeFlags(base: ModelSnapshot, i: number, head: ModelSnapshot, j: number, o: RevisionOptions): { flags: ChangeFlag[]; props?: DiffEntry['props'] } {
  let flags: ChangeFlag[] | null = null; // allocated only for a pair that changed: most pairs of a revision are untouched
  const add = (f: ChangeFlag): void => { (flags ??= []).push(f); };
  if (base.ifcClass[i] !== head.ifcClass[j]) add('class');
  const pa = base.props[i], pb = head.props[j];
  if (base.typeName[i] !== head.typeName[j] || (pa?.['Attr.PredefinedType'] ?? '') !== (pb?.['Attr.PredefinedType'] ?? '')) add('type');
  if (base.name[i] !== head.name[j] || base.tag[i] !== head.tag[j] || (pa?.['Attr.Description'] ?? '') !== (pb?.['Attr.Description'] ?? '')) add('attributes');
  if (!sameStorey(base.storey[i]!, head.storey[j]!, o.elevationTol)) add('storey');
  if (base.material[i] !== head.material[j]) add('material');
  let props: DiffEntry['props'];
  if (pa || pb) {
    const d = diffProps(pa ?? null, pb ?? null, o);
    if (d.length) { add('properties'); props = d; }
  }
  if (!sameList(base.systems[i]!, head.systems[j]!)) add('systems');
  return flags === null ? NO_ATTRIBUTE_CHANGE : { flags, ...(props ? { props } : {}) };
}

const order = (f: ChangeFlag[]): ChangeFlag[] => CHANGE_FLAGS.filter((x) => f.includes(x));

/** Compare two models. Pure; the same inputs give the same entries in the same order. */
export function diffModels(base: ModelSnapshot, head: ModelSnapshot, opts?: Partial<RevisionOptions>): RevisionDiff {
  const o = withOptions(opts);
  const nb = base.globalId.length, nh = head.globalId.length;
  const ref: Vec3 = [head.originShift[0], head.originShift[1], head.originShift[2]];
  const a = frameOf(base, ref), b = frameOf(head, ref);
  const counts = Object.fromEntries(CATEGORIES.map((c) => [c, 0])) as Record<Category, number>;
  const flagCounts = Object.fromEntries(CHANGE_FLAGS.map((f) => [f, 0])) as Record<ChangeFlag, number>;
  const headEntries: Array<DiffEntry | undefined> = new Array<DiffEntry | undefined>(nh);

  // 1. by GlobalId (federation suffix stripped; on a clash the first element keeps the id)
  const byGid = new Map<string, number>();
  for (let i = 0; i < nb; i++) { const g = stripFederation(base.globalId[i]!); if (g && !byGid.has(g)) byGid.set(g, i); }
  const baseUsed = new Uint8Array(nb);
  const headMatched = new Uint8Array(nh);
  let pairs = 0;
  const finish = (i: number, j: number, category: Category, score: number | undefined, offset: Vec3): void => {
    const shape = compareShape(a, i, b, j, o, offset);
    const at = attributeFlags(base, i, head, j, o);
    const flags = shape.flags.length === 0 && at.flags.length === 0 ? [] : order([...shape.flags, ...at.flags]);
    const affected = base.classifySignature[i] !== head.classifySignature[j];
    if (category === 'changed' && flags.length === 0) { counts.unchanged++; return; }
    counts[category]++;
    for (const f of flags) flagCounts[f]++;
    headEntries[j] = {
      key: head.globalId[j]!, category, base: base.globalId[i]!, head: head.globalId[j]!, flags,
      ...(shape.move !== undefined ? { move: shape.move, delta: shape.delta! } : {}),
      ...(shape.rotated ? { rotated: true } : {}),
      ...(score !== undefined ? { score } : {}),
      ...(at.props ? { props: at.props } : {}),
      classifyAffected: affected,
    };
  };
  for (let j = 0; j < nh; j++) {
    const g = stripFederation(head.globalId[j]!);
    const i = g ? byGid.get(g) : undefined;
    if (i === undefined || baseUsed[i]) continue;
    baseUsed[i] = 1; headMatched[j] = 1; pairs++;
    finish(i, j, 'changed', undefined, [0, 0, 0]);
  }

  // 2.-5. what is left: global offset when the GUIDs hardly met, then the scored one-to-one match
  const D: number[] = [], N: number[] = [];
  for (let i = 0; i < nb; i++) if (!baseUsed[i]) D.push(i);
  for (let j = 0; j < nh; j++) if (!headMatched[j]) N.push(j);
  let offset: Vec3 = [0, 0, 0];
  const rematchedBase = new Uint8Array(nb);
  if (D.length && N.length) {
    if (pairs < o.guidPairFloor * Math.min(nb, nh)) offset = estimateOffset(base, head, a, b, D, N);
    const matched = matchLeftovers({ base, head, a, b, options: o, offset }, D, N);
    for (const m of matched) { rematchedBase[m.d] = 1; headMatched[m.n] = 1; finish(m.d, m.n, 'rematched', m.score, offset); }
  }

  const entries: DiffEntry[] = [];
  for (let j = 0; j < nh; j++) {
    const e = headEntries[j];
    if (e) entries.push(e);
    else if (!headMatched[j]) {
      counts.new++;
      entries.push({ key: head.globalId[j]!, category: 'new', head: head.globalId[j]!, flags: [], classifyAffected: true });
    }
  }
  for (let i = 0; i < nb; i++) {
    if (baseUsed[i] || rematchedBase[i]) continue;
    counts.deleted++;
    entries.push({ key: `del:${base.globalId[i]}`, category: 'deleted', base: base.globalId[i]!, flags: [], classifyAffected: false });
  }
  return { base: base.identity, head: head.identity, options: o, counts, flagCounts, entries, offset };
}
