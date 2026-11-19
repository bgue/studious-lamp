// The order and the items of a revision walk (design 3.5). Pure, no randomness: the same diff always gives the same list, so a walk
// can be resumed and tests can pin it. Reuses WalkElement, WalkItem and sweepOrder of the review walk.

import { sweepOrder } from '../classify/reviewWalk';
import type { WalkElement, WalkItem } from '../classify/reviewWalk';
import type { ClassifyResult } from '../classify/types';
import { REVISION_ORDERS } from './types';
import type { Category, ChangeFlag, DiffEntry, ModelSnapshot, RevisionDecision, RevisionDiff, RevisionFilters, RevisionOrder, Vec3 } from './types';

export { REVISION_ORDERS };
export const REVISION_ORDER_LABEL: Record<RevisionOrder, string> = {
  category: 'By kind of change, then location',
  storey: 'By storey',
  class: 'By class',
};

export interface RevisionItem extends WalkItem {
  category: Category;
  flags: ChangeFlag[];
  entries: DiffEntry[];
}

/** Deleted, then rematched, then changed, then new. */
export const CATEGORY_RANK: Record<Category, number> = { deleted: 0, rematched: 1, changed: 2, new: 3, unchanged: 4 };

export interface RevisionWalkInput {
  base: ModelSnapshot;
  head: ModelSnapshot;
  diff: RevisionDiff;
  order?: RevisionOrder;
  filters?: RevisionFilters;
  /** One item per group of alike changes (default), or one item per element. */
  group?: boolean;
  decisions?: Readonly<Record<string, RevisionDecision>>;
  /** Skipped entry keys. */
  skipped?: { has(key: string): boolean };
  /** Issues and sketches attached to a GlobalId (base GlobalId for deleted and rematched, head otherwise). */
  attachments?: (globalId: string) => number;
  /** Placement moves closer than this (m) share one item when their vectors agree (default 1 mm). */
  moveGroupTol?: number;
}

const cmp = (a: string, b: string): number => (a < b ? -1 : a > b ? 1 : 0);

const codesOf = (r: ClassifyResult | null | undefined): string => (r ? `${r.discipline.code}/${r.subDiscipline?.code ?? ''}/${r.masterformat?.division ?? ''}` : '');

interface Located {
  entry: DiffEntry;
  el: WalkElement;
  /** Base decision codes (deleted, changed, rematched) or the head's (new). */
  codes: string;
  baseResult: ClassifyResult | null;
}

/** Index of GlobalIds (federation suffix kept: entries hold the stored ids). */
const indexOf = (s: ModelSnapshot): Map<string, number> => {
  const m = new Map<string, number>();
  s.globalId.forEach((g, i) => m.set(g, i));
  return m;
};

/** The element of a snapshot as a WalkElement; bounds in the head's viewer frame (Y up, relative to the head's origin shift). */
export function walkElementOf(s: ModelSnapshot, i: number, headShift: Vec3, storeyIds: Map<string, number>, system: string): WalkElement {
  const b = s.bounds;
  const o = i * 6;
  const dx = s.originShift[0] - headShift[0], dy = s.originShift[1] - headShift[1], dz = s.originShift[2] - headShift[2];
  const st = s.storey[i];
  let sid: number | null = null;
  if (st) sid = storeyIds.get(st.name) ?? storeyIds.set(st.name, storeyIds.size).get(st.name)!;
  return {
    id: i,
    globalId: s.globalId[i]!,
    ifcClass: s.ifcClass[i]!,
    name: s.name[i]!,
    tag: s.tag[i]!,
    storey: sid,
    storeyName: st?.name ?? '',
    elevation: st?.elevation ?? 0,
    system,
    signature: s.classifySignature[i]!,
    // IFC axes (x, y, z) -> viewer (x, z, -y)
    bounds: [b[o]! + dx, b[o + 2]! + dz, -(b[o + 4]! + dy), b[o + 3]! + dx, b[o + 5]! + dz, -(b[o + 1]! + dy)],
  };
}

/** Every listed (not unchanged) entry as a located element. */
function locate(inp: RevisionWalkInput): Located[] {
  const { base, head, diff } = inp;
  const bi = indexOf(base), hi = indexOf(head);
  const storeyIds = new Map<string, number>();
  const out: Located[] = [];
  for (const e of diff.entries) {
    const useHead = e.category !== 'deleted';
    const s = useHead ? head : base;
    const i = (useHead ? hi : bi).get((useHead ? e.head : e.base)!);
    if (i === undefined) continue;
    const bIdx = e.base ? bi.get(e.base) : undefined;
    const baseResult = bIdx === undefined ? null : base.results[bIdx] ?? null;
    out.push({ entry: e, el: walkElementOf(s, i, head.originShift, storeyIds, s.systems[i]![0] ?? ''), codes: codesOf(e.category === 'new' ? head.results[i] : baseResult), baseResult });
  }
  return out;
}

function passes(l: Located, f: RevisionFilters, inp: RevisionWalkInput): boolean {
  const e = l.entry;
  if (f.category && e.category !== f.category) return false;
  if (f.flag && !e.flags.includes(f.flag)) return false;
  if (f.storey !== undefined && l.el.storeyName !== f.storey) return false;
  if (f.ifcClass && l.el.ifcClass !== f.ifcClass) return false;
  const d = inp.decisions?.[e.key];
  if (f.undecided && d) return false;
  if (f.unsure && !(d?.unsure === true)) return false;
  if (f.onlySkipped && !(inp.skipped?.has(e.key) ?? false)) return false;
  if (f.hasAttachments && !((inp.attachments?.(e.base ?? e.head ?? '') ?? 0) > 0)) return false;
  if (f.minMove !== undefined && !((e.move ?? 0) >= f.minMove)) return false;
  return true;
}

/** The entries that pass a set of filters, in diff order (what "Everything in the current filter" and the walk's count use). */
export function filterEntries(inp: Omit<RevisionWalkInput, 'order' | 'group'>, filters: RevisionFilters = inp.filters ?? {}): DiffEntry[] {
  return locate(inp as RevisionWalkInput).filter((l) => passes(l, filters, inp as RevisionWalkInput)).map((l) => l.entry);
}

/** The grouping key: same category, flag set, class, storey, base codes and, for moves, the same vector to the millimetre. */
function groupKey(l: Located, tol: number): string {
  const e = l.entry;
  const mv = e.flags.includes('placement') && e.delta ? e.delta.map((v) => Math.round(v / tol)).join(',') : '';
  return [e.category, e.flags.join('+'), e.rotated ? 'r' : '', l.el.ifcClass, l.el.storeyName, l.codes, mv].join('|');
}

const titleOf = (els: readonly WalkElement[]): string => {
  const e = els[0]!;
  const one = `${e.ifcClass}: ${e.name || e.tag || e.globalId}`;
  return els.length > 1 ? `${els.length} x ${one}` : one;
};

/**
 * The items of a revision walk, in order. Default order `category`: deleted, rematched, changed, new; inside a category by storey
 * elevation (a storey-less element last), then class, then the serpentine sweep. `storey` and `class` change the primary grouping and
 * keep the other two as tie-breakers.
 */
export function buildRevisionWalk(inp: RevisionWalkInput): RevisionItem[] {
  const order = inp.order ?? 'category';
  const filters = inp.filters ?? {};
  const tol = inp.moveGroupTol ?? 0.001;
  const located = locate(inp).filter((l) => passes(l, filters, inp));
  // the sweep rank of every element: one global serpentine, so ties inside a storey follow the building
  const rank = new Map<string, number>();
  sweepOrder(located.map((l) => l.el)).forEach((e, i) => rank.set(e.globalId, i));
  const rankOf = (l: Located): number => rank.get(l.el.globalId) ?? 0;

  const groups = new Map<string, Located[]>();
  for (const l of located) {
    const k = inp.group === false ? `one|${l.entry.key}` : groupKey(l, tol);
    (groups.get(k) ?? groups.set(k, []).get(k)!).push(l);
  }
  const items: Array<{ item: RevisionItem; keys: [number | string, number | string, number | string, number] }> = [];
  for (const list of groups.values()) {
    list.sort((a, b) => rankOf(a) - rankOf(b) || cmp(a.entry.key, b.entry.key));
    const first = list[0]!;
    const els = list.map((l) => l.el);
    const e = first.entry;
    const item: RevisionItem = {
      key: `${e.category}:${e.key}`,
      title: titleOf(els),
      ifcClass: first.el.ifcClass,
      storeyName: first.el.storeyName,
      system: first.el.system,
      discipline: first.baseResult?.discipline.code ?? '',
      elements: els,
      category: e.category,
      flags: e.flags,
      entries: list.map((l) => l.entry),
    };
    const elev = first.el.storey === null ? Number.POSITIVE_INFINITY : first.el.elevation;
    const cat = CATEGORY_RANK[e.category];
    const cls = first.el.ifcClass;
    const keys: [number | string, number | string, number | string, number] =
      order === 'storey' ? [elev, cat, cls, rankOf(first)] : order === 'class' ? [cls, cat, elev, rankOf(first)] : [cat, elev, cls, rankOf(first)];
    items.push({ item, keys });
  }
  const c = (a: number | string, b: number | string): number => (typeof a === 'number' && typeof b === 'number' ? (a === b ? 0 : a < b ? -1 : 1) : cmp(String(a), String(b)));
  items.sort((x, y) => c(x.keys[0], y.keys[0]) || c(x.keys[1], y.keys[1]) || c(x.keys[2], y.keys[2]) || x.keys[3] - y.keys[3] || cmp(x.item.key, y.item.key));
  return items.map((x) => x.item);
}

