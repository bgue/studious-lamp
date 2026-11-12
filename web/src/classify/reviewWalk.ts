// The order of a review walk: which work items a person visits, and in which order. No DOM, no randomness: the same model and the same
// results always give the same list, so a walk can be resumed and tests can pin it.
//
//   type      one item per kind of element (same signature and same codes), confirmed once for all N of them.
//             Ordered by storey, then system, then discipline, then position. The default.
//   systems   one item per element. Per distribution system: start at one end of the run and chain to the nearest element that is left.
//   location  one item per element. Storey by storey (lowest first), a serpentine sweep inside each storey.
//   review    like type, but the least confident kinds first.

import type { SceneModel } from '../types';
import { buildInput } from './build';
import { overallConfidence, topMargin } from './review';
import { signatureOf } from './state';
import type { ClassifyResult } from './types';

export const WALK_ORDERS = ['type', 'systems', 'location', 'review'] as const;
export type WalkOrder = (typeof WALK_ORDERS)[number];
export const WALK_ORDER_LABEL: Record<WalkOrder, string> = {
  type: 'By type, then location',
  systems: 'Along systems',
  location: 'By location',
  review: 'Needs review first',
};

export interface WalkElement {
  /** The element index in the model. */
  id: number;
  globalId: string;
  ifcClass: string;
  name: string;
  tag: string;
  storey: number | null;
  storeyName: string;
  /** Elevation of the storey, for ordering (a storey-less element goes last). */
  elevation: number;
  /** First system name, or '' when the element is in none. */
  system: string;
  /** The classification signature (state.ts). */
  signature: string;
  /** [minx, miny, minz, maxx, maxy, maxz] in viewer coordinates (Y up). */
  bounds: readonly [number, number, number, number, number, number];
}

export interface WalkFilters {
  /** Only elements whose result needs review. */
  needsReview?: boolean;
  /** Hide kinds that are all committed already. */
  unconfirmed?: boolean;
  /** Only this discipline code. */
  discipline?: string;
  /** Only elements whose result is committed and flagged unsure. */
  unsure?: boolean;
  /** Only the elements that were skipped in this session (needs `skipped` in the input). */
  onlySkipped?: boolean;
}

/**
 * The elements that a reviewer skipped in this session, by GlobalId. A skip leaves the element as it is: it is not a change, it is not
 * committed and it does not enter the review log. A decision on an element (confirm, runner-up, correct) takes it off the list.
 */
export class SkipList {
  private readonly set = new Set<string>();
  get size(): number {
    return this.set.size;
  }
  has(globalId: string): boolean {
    return this.set.has(globalId);
  }
  /** Add elements; returns how many were new. */
  add(globalIds: Iterable<string>): number {
    let n = 0;
    for (const g of globalIds) if (!this.set.has(g)) { this.set.add(g); n++; }
    return n;
  }
  /** Take elements off the list; returns how many were on it. */
  remove(globalIds: Iterable<string>): number {
    let n = 0;
    for (const g of globalIds) if (this.set.delete(g)) n++;
    return n;
  }
  clear(): void {
    this.set.clear();
  }
  ids(): string[] {
    return [...this.set];
  }
}

export interface WalkItem {
  /** Stable key: the item's first GlobalId and the order, e.g. "type:2Abc...". */
  key: string;
  /** Short title, e.g. "IfcPipeSegment: Pipe 150". */
  title: string;
  ifcClass: string;
  storeyName: string;
  system: string;
  discipline: string;
  /** The elements of the item, in walk order. */
  elements: WalkElement[];
}

export interface WalkInput {
  elements: readonly WalkElement[];
  resultOf(globalId: string): ClassifyResult | undefined;
  isCommitted(globalId: string): boolean;
  /** Discipline codes in the schema's order (the order of items within a storey and system). */
  disciplineOrder: readonly string[];
  order: WalkOrder;
  filters?: WalkFilters;
  /** The session's skipped elements, for the "Only skipped" filter. */
  skipped?: { has(globalId: string): boolean };
}

const cmp = (a: string, b: string): number => (a < b ? -1 : a > b ? 1 : 0);
const num = (a: number, b: number): number => a - b;
const centre = (b: WalkElement['bounds']): [number, number, number] => [(b[0] + b[3]) / 2, (b[1] + b[4]) / 2, (b[2] + b[5]) / 2];

/** Elements that pass the needs-review and discipline filters and have a result. */
export function walkScope(input: Pick<WalkInput, 'elements' | 'resultOf' | 'filters' | 'skipped'>): WalkElement[] {
  const f = input.filters ?? {};
  return input.elements.filter((e) => {
    const r = input.resultOf(e.globalId);
    if (!r) return false;
    if (f.needsReview && !r.needsReview) return false;
    if (f.discipline && r.discipline.code !== f.discipline) return false;
    if (f.unsure && r.unsure !== true) return false;
    if (f.onlySkipped && !(input.skipped?.has(e.globalId) ?? false)) return false;
    return true;
  });
}

/** Storey by storey from the lowest (no storey last), a serpentine sweep in each storey: rows along Z, X up on one row and down on the next. */
export function sweepOrder(els: readonly WalkElement[]): WalkElement[] {
  const byStorey = new Map<string, WalkElement[]>();
  for (const e of els) {
    const k = e.storey === null ? 'z' : 'a';
    const key = `${k}|${e.storey === null ? '' : e.elevation.toFixed(4).padStart(14, '0')}|${e.storey ?? ''}`;
    (byStorey.get(key) ?? byStorey.set(key, []).get(key)!).push(e);
  }
  const out: WalkElement[] = [];
  for (const key of [...byStorey.keys()].sort(cmp)) {
    const list = byStorey.get(key)!;
    const zs = list.map((e) => e.bounds[5] - e.bounds[2]).sort(num);
    const row = Math.max(1, (zs[Math.floor(zs.length / 2)] ?? 1) * 4);
    const minZ = Math.min(...list.map((e) => centre(e.bounds)[2]));
    const keyed = list.map((e) => {
      const c = centre(e.bounds);
      return { e, r: Math.floor((c[2] - minZ) / row), x: c[0], z: c[2] };
    });
    keyed.sort((a, b) => a.r - b.r || (a.r % 2 === 0 ? a.x - b.x : b.x - a.x) || a.z - b.z || cmp(a.e.globalId, b.e.globalId));
    for (const k of keyed) out.push(k.e);
  }
  return out;
}

/** The gap between two boxes (0 when they touch or overlap). */
function gap(a: WalkElement['bounds'], b: WalkElement['bounds']): number {
  const dx = Math.max(0, a[0] - b[3], b[0] - a[3]);
  const dy = Math.max(0, a[1] - b[4], b[1] - a[4]);
  const dz = Math.max(0, a[2] - b[5], b[2] - a[5]);
  return Math.hypot(dx, dy, dz);
}

const CHAIN_MAX = 6000;

/**
 * Walk a run from one end: the end is found by two sweeps (the element farthest from the centroid, then the element farthest from that
 * one), then each step goes to the nearest element that is left (gap between bounds, then distance between centres, then GlobalId).
 * A group above CHAIN_MAX elements falls back to the sweep order.
 */
export function chainOrder(els: readonly WalkElement[]): WalkElement[] {
  if (els.length <= 2) return [...els].sort((a, b) => cmp(a.globalId, b.globalId));
  if (els.length > CHAIN_MAX) return sweepOrder(els);
  const c = els.map((e) => centre(e.bounds));
  const dist = (i: number, j: number): number => Math.hypot(c[i]![0] - c[j]![0], c[i]![1] - c[j]![1], c[i]![2] - c[j]![2]);
  const mean: [number, number, number] = [0, 1, 2].map((k) => c.reduce((s, p) => s + p[k]!, 0) / c.length) as [number, number, number];
  const farthest = (d: (i: number) => number): number => {
    let best = 0;
    for (let i = 1; i < els.length; i++) {
      const di = d(i);
      const db = d(best);
      if (di > db + 1e-9 || (Math.abs(di - db) <= 1e-9 && cmp(els[i]!.globalId, els[best]!.globalId) < 0)) best = i;
    }
    return best;
  };
  const a = farthest((i) => Math.hypot(c[i]![0] - mean[0], c[i]![1] - mean[1], c[i]![2] - mean[2]));
  const start = farthest((i) => dist(i, a));
  const left = new Set(els.map((_, i) => i));
  const out: WalkElement[] = [];
  let cur = start;
  for (;;) {
    left.delete(cur);
    out.push(els[cur]!);
    if (left.size === 0) break;
    let best = -1;
    let bg = Infinity;
    let bd = Infinity;
    for (const j of left) {
      const g = gap(els[cur]!.bounds, els[j]!.bounds);
      const d = dist(cur, j);
      if (best < 0 || g < bg - 1e-9 || (Math.abs(g - bg) <= 1e-9 && (d < bd - 1e-9 || (Math.abs(d - bd) <= 1e-9 && cmp(els[j]!.globalId, els[best]!.globalId) < 0)))) { best = j; bg = g; bd = d; }
    }
    cur = best;
  }
  return out;
}

function titleOf(e: WalkElement, n: number): string {
  const base = `${e.ifcClass}: ${e.name || e.tag || e.globalId}`;
  return n > 1 ? `${base} (${n})` : base;
}

const single = (e: WalkElement, order: WalkOrder, disc: string): WalkItem => ({ key: `${order}:${e.globalId}`, title: titleOf(e, 1), ifcClass: e.ifcClass, storeyName: e.storeyName, system: e.system, discipline: disc, elements: [e] });

/** The work items of a walk, in order. */
export function buildWalk(input: WalkInput): WalkItem[] {
  const scope = walkScope(input);
  const disc = (e: WalkElement): string => input.resultOf(e.globalId)!.discipline.code;
  const discIdx = (code: string): number => {
    const i = input.disciplineOrder.indexOf(code);
    return i < 0 ? input.disciplineOrder.length : i;
  };
  const hideDone = input.filters?.unconfirmed === true;

  if (input.order === 'systems') {
    const groups = new Map<string, WalkElement[]>();
    for (const e of scope) (groups.get(e.system) ?? groups.set(e.system, []).get(e.system)!).push(e);
    const names = [...groups.keys()].sort((a, b) => (a === '' ? 1 : b === '' ? -1 : cmp(a, b)));
    const items: WalkItem[] = [];
    for (const n of names) for (const e of chainOrder(groups.get(n)!)) if (!(hideDone && input.isCommitted(e.globalId))) items.push(single(e, 'systems', disc(e)));
    return items;
  }

  const sweep = sweepOrder(scope);
  const rank = new Map(sweep.map((e, i) => [e.globalId, i]));

  if (input.order === 'location') return sweep.filter((e) => !(hideDone && input.isCommitted(e.globalId))).map((e) => single(e, 'location', disc(e)));

  // type and review: group by signature and codes
  const groups = new Map<string, WalkElement[]>();
  for (const e of sweep) {
    const r = input.resultOf(e.globalId)!;
    const key = `${e.signature}|${r.discipline.code}|${r.subDiscipline?.code ?? ''}|${r.masterformat?.division ?? ''}`;
    (groups.get(key) ?? groups.set(key, []).get(key)!).push(e); // sweep order inside the group
  }
  const items = [...groups.entries()].map(([gkey, els]) => {
    const first = els[0]!; // lowest rank
    const minConf = Math.min(...els.map((e) => overallConfidence(input.resultOf(e.globalId)!)));
    const margin = Math.min(...els.map((e) => topMargin(input.resultOf(e.globalId)!.discipline.probabilities)));
    return { gkey, els, first, minConf, margin, elev: Math.min(...els.map((e) => (e.storey === null ? Infinity : e.elevation))) };
  });
  const byLocation = (a: (typeof items)[number], b: (typeof items)[number]): number =>
    (a.elev === b.elev ? 0 : a.elev === Infinity ? 1 : b.elev === Infinity ? -1 : a.elev - b.elev) ||
    (a.first.system === b.first.system ? 0 : a.first.system === '' ? 1 : b.first.system === '' ? -1 : cmp(a.first.system, b.first.system)) ||
    discIdx(disc(a.first)) - discIdx(disc(b.first)) ||
    rank.get(a.first.globalId)! - rank.get(b.first.globalId)! ||
    cmp(a.gkey, b.gkey);
  if (input.order === 'review') items.sort((a, b) => a.minConf - b.minConf || a.margin - b.margin || byLocation(a, b));
  else items.sort(byLocation);
  return items
    .filter((g) => !(hideDone && g.els.every((e) => input.isCommitted(e.globalId))))
    .map((g): WalkItem => ({ key: `${input.order}:${g.first.globalId}`, title: titleOf(g.first, g.els.length), ifcClass: g.first.ifcClass, storeyName: g.first.storeyName, system: g.first.system, discipline: disc(g.first), elements: g.els }));
}

export interface WalkProgress {
  confirmed: number;
  corrected: number;
  remaining: number;
  total: number;
}

/** Element counts of the walk's scope: decided by a commit or by a pending change as confirmed or corrected, and the rest. */
export function walkProgress(scope: readonly WalkElement[], decision: (globalId: string) => 'confirmed' | 'corrected' | null): WalkProgress {
  let confirmed = 0;
  let corrected = 0;
  for (const e of scope) {
    const d = decision(e.globalId);
    if (d === 'confirmed') confirmed++;
    else if (d === 'corrected') corrected++;
  }
  return { confirmed, corrected, remaining: scope.length - confirmed - corrected, total: scope.length };
}

export interface RunnerUp {
  part: 'discipline' | 'subDiscipline' | 'division';
  /** The code that would replace the proposed one. */
  code: string;
  probability: number;
  /** The proposed code and its probability. */
  proposed: string;
  proposedProbability: number;
}

/**
 * The second choice of the model for the part of the result with the narrowest margin that has a second option. `valid` says whether a
 * code of that part is in the schema (for the sub-discipline it is asked with the discipline of the result).
 */
export function runnerUp(r: ClassifyResult, valid: (part: RunnerUp['part'], code: string) => boolean): RunnerUp | null {
  const parts: Array<{ part: RunnerUp['part']; c: { code: string; probabilities: Record<string, number> } | null }> = [
    { part: 'discipline', c: r.discipline },
    { part: 'subDiscipline', c: r.subDiscipline },
    { part: 'division', c: r.masterformat ? { code: r.masterformat.division, probabilities: r.masterformat.probabilities } : null },
  ];
  let best: { margin: number; up: RunnerUp } | null = null;
  for (const { part, c } of parts) {
    if (!c) continue;
    const ranked = Object.entries(c.probabilities).sort((a, b) => b[1] - a[1]);
    const proposed = c.probabilities[c.code] ?? ranked[0]?.[1] ?? 0;
    const alt = ranked.find(([code]) => code !== c.code && valid(part, code));
    if (!alt) continue;
    const margin = proposed - alt[1];
    if (!best || margin < best.margin) best = { margin, up: { part, code: alt[0], probability: alt[1], proposed: c.code, proposedProbability: proposed } };
  }
  return best?.up ?? null;
}

/** The walk elements of a loaded model: storey, first system, tag and the classification signature of each element. */
export function walkElementsOf(model: SceneModel): WalkElement[] {
  const system = new Map<number, string>();
  for (const s of model.relations.systems) for (const id of s.elements) if (!system.has(id)) system.set(id, s.name);
  const storeys = new Map(model.storeys.map((s) => [s.id, s]));
  const out: WalkElement[] = [];
  for (const e of model.elements) {
    const input = buildInput(model, e.id);
    if (!input) continue;
    const st = e.storey === null ? undefined : storeys.get(e.storey);
    const tag = e.props?.['Attr.Tag'];
    out.push({
      id: e.id,
      globalId: e.globalId,
      ifcClass: e.ifcClass,
      name: e.name ?? '',
      tag: typeof tag === 'string' ? tag : '',
      storey: e.storey,
      storeyName: st?.name ?? '',
      elevation: st?.elevation ?? 0,
      system: system.get(e.id) ?? '',
      signature: signatureOf(input),
      bounds: e.bounds,
    });
  }
  return out;
}
