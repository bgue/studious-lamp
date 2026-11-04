// Exploded view. A set of elements (the selection when it has several, else the occluders around a single
// selected element, see resolveExplodeSet) moves apart in one of three ways:
//   radial          offset_i = (c_i - C) * factor     C = bounds centre of the explode set (the classic exploded view)
//   storeys         offset_y = (storeyIndex_i - medianStoreyIndex) * storeyGap     (exploded floors)
//   radial+storeys  the sum of both
// c_i is the bounds centre of element i. Pure maths plus a small eased animation; the offsets are uploaded
// per element by the renderer (state texture C) and added in every vertex shader.
//
// Picking and the BVH use the undisplaced geometry, so clicking during an explode can select the
// element that sits behind the cursor in the unexploded model. Algorithm 2 also uses the
// unexploded geometry (the geometry provider is not touched).

import { Vector3 } from 'three';
import { easeInOutCubic } from './easing';

export const DEFAULT_EXPLODE_MS = 800;
export const DEFAULT_EXPLODE_FACTOR = 1;
export const DEFAULT_STOREY_GAP = 3;
/** Occluders around a single selected element move at least this far (m), so they clear it even when close to its centre. */
export const DEFAULT_MIN_PUSH = 0.5;
/** Storey height assumed when the explode set carries no storey information at all (m). */
export const FALLBACK_STOREY_HEIGHT = 3;

export type ExplodeSource = 'auto' | 'selection' | 'occluders' | 'both';
export type ExplodeMode = 'radial' | 'storeys' | 'radial+storeys';

export const EXPLODE_SOURCES: readonly ExplodeSource[] = ['auto', 'selection', 'occluders', 'both'];
export const EXPLODE_MODES: readonly ExplodeMode[] = ['radial', 'storeys', 'radial+storeys'];

export interface ExplodeParams {
  mode: ExplodeMode;
  /** Radial multiplier on (c_i - C). */
  factor: number;
  /** Vertical separation between neighbouring storeys (m). */
  storeyGap: number;
  /** Radial offsets shorter than this (m) are pushed out to this length (0 = off). */
  minPush: number;
}

export function usesRadial(mode: ExplodeMode): boolean {
  return mode === 'radial' || mode === 'radial+storeys';
}
export function usesStoreys(mode: ExplodeMode): boolean {
  return mode === 'storeys' || mode === 'radial+storeys';
}

/** Bounds as [minx, miny, minz, maxx, maxy, maxz]. */
export type BoundsTuple = readonly [number, number, number, number, number, number];

export function boundsCentre(b: BoundsTuple, out = new Vector3()): Vector3 {
  return out.set((b[0] + b[3]) / 2, (b[1] + b[4]) / 2, (b[2] + b[5]) / 2);
}

/** Centre of the union of the bounds of `ids` (ids without bounds are skipped). null when none has bounds. */
export function unionCentre(ids: Iterable<number>, bounds: (id: number) => BoundsTuple | undefined, out = new Vector3()): Vector3 | null {
  let n = 0;
  let x0 = Infinity, y0 = Infinity, z0 = Infinity, x1 = -Infinity, y1 = -Infinity, z1 = -Infinity;
  for (const id of ids) {
    const b = bounds(id);
    if (!b) continue;
    n++;
    x0 = Math.min(x0, b[0]); y0 = Math.min(y0, b[1]); z0 = Math.min(z0, b[2]);
    x1 = Math.max(x1, b[3]); y1 = Math.max(y1, b[4]); z1 = Math.max(z1, b[5]);
  }
  return n === 0 ? null : out.set((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2);
}

/**
 * The elements to explode. `auto`: the selection itself when it has more than one element (a storey or class
 * subtree picked in the sidebar), else the occluders (Host + Near) around the single selected element.
 */
export function resolveExplodeSource(source: ExplodeSource, selectionSize: number): Exclude<ExplodeSource, 'auto'> {
  if (source !== 'auto') return source;
  return selectionSize > 1 ? 'selection' : 'occluders';
}

export function resolveExplodeSet(source: ExplodeSource, selection: Iterable<number>, occluders: Iterable<number>): { ids: number[]; source: Exclude<ExplodeSource, 'auto'> } {
  const sel = [...selection];
  const used = resolveExplodeSource(source, sel.length);
  const set = new Set<number>();
  if (used !== 'occluders') for (const id of sel) set.add(id);
  if (used !== 'selection') for (const id of occluders) set.add(id);
  return { ids: [...set], source: used };
}

function median(values: number[]): number {
  if (values.length === 0) return 0;
  const v = [...values].sort((a, b) => a - b);
  const m = v.length >> 1;
  return v.length % 2 ? v[m]! : (v[m - 1]! + v[m]!) / 2;
}

/**
 * Index of each storey id in elevation order (0 = lowest). Storeys with the same elevation keep id order.
 */
export function storeyRanks(storeys: ReadonlyArray<{ id: number; elevation: number }>): Map<number, number> {
  const order = [...storeys].sort((a, b) => a.elevation - b.elevation || a.id - b.id);
  const rank = new Map<number, number>();
  order.forEach((s, i) => rank.set(s.id, i));
  return rank;
}

export interface ExplodeTable {
  ids: number[];
  /** c_i - C, 3 floats per entry of `ids` (metres). */
  rel: Float32Array;
  /** (storeyIndex_i - medianStoreyIndex), one float per entry: how many storeys above the median storey. */
  level: Float32Array;
  /** The explode centre C. */
  centre: Vector3;
}

export interface ExplodeInput {
  bounds: (id: number) => BoundsTuple | undefined;
  /** Storey id of an element, null/undefined when it has none. */
  storeyOf?: (id: number) => number | null | undefined;
  /** Storey id -> index in elevation order (see storeyRanks). Storey ids missing here count as "no storey". */
  ranks?: ReadonlyMap<number, number>;
  /** Explode centre C. Default: the bounds centre of the explode set. */
  centre?: Vector3;
}

/**
 * Build the per-element data for `ids`. The storey level of an element is its storey's elevation index minus
 * the median index of the storeys present in the set. Elements without a storey take a fractional index from their bounds centre y,
 * interpolated between the storeys that are present (reference y = median centre y of that storey's elements);
 * with fewer than two such storeys, one FALLBACK_STOREY_HEIGHT metres of height counts as one storey.
 */
export function buildExplodeTable(ids: Iterable<number>, input: ExplodeInput): ExplodeTable {
  const list: number[] = [];
  const centres: number[] = [];
  const bounds = input.bounds;
  const c = new Vector3();
  for (const id of ids) {
    const b = bounds(id);
    if (!b) continue;
    boundsCentre(b, c);
    list.push(id);
    centres.push(c.x, c.y, c.z);
  }
  const C = input.centre ? input.centre.clone() : unionCentre(list, bounds) ?? new Vector3();

  const n = list.length;
  const rel = new Float32Array(n * 3);
  for (let i = 0; i < n; i++) {
    rel[i * 3] = centres[i * 3]! - C.x;
    rel[i * 3 + 1] = centres[i * 3 + 1]! - C.y;
    rel[i * 3 + 2] = centres[i * 3 + 2]! - C.z;
  }

  // Storey index per entry (NaN: none).
  const idx = new Float64Array(n).fill(NaN);
  const yByRank = new Map<number, number[]>();
  for (let i = 0; i < n; i++) {
    const st = input.storeyOf?.(list[i]!);
    const r = st === null || st === undefined ? undefined : input.ranks?.get(st);
    if (r === undefined) continue;
    idx[i] = r;
    let arr = yByRank.get(r);
    if (!arr) yByRank.set(r, (arr = []));
    arr.push(centres[i * 3 + 1]!);
  }
  const refs = [...yByRank.entries()].map(([r, ys]) => ({ rank: r, y: median(ys) })).sort((a, b) => a.y - b.y);
  const indexFromY = (y: number): number => {
    if (refs.length < 2) {
      const y0 = refs.length === 1 ? refs[0]!.y : C.y;
      const r0 = refs.length === 1 ? refs[0]!.rank : 0;
      return r0 + (y - y0) / FALLBACK_STOREY_HEIGHT;
    }
    // Piecewise linear between neighbouring reference storeys, extrapolated with the end segments.
    let k = 0;
    while (k < refs.length - 2 && y > refs[k + 1]!.y) k++;
    const a = refs[k]!;
    const b = refs[k + 1]!;
    const dy = b.y - a.y;
    return dy > 1e-9 ? a.rank + ((y - a.y) / dy) * (b.rank - a.rank) : a.rank;
  };
  for (let i = 0; i < n; i++) if (Number.isNaN(idx[i]!)) idx[i] = indexFromY(centres[i * 3 + 1]!);

  // Median over the distinct storeys present (the middle storey stays put); without any, over the y-derived indices.
  const own = [...yByRank.keys()];
  const medianIndex = own.length > 0 ? median(own) : median([...idx]);
  const level = new Float32Array(n);
  for (let i = 0; i < n; i++) level[i] = idx[i]! - medianIndex;
  return { ids: list, rel, level, centre: C };
}

/**
 * Offset of table entry `i` at animation progress `k` (0..1, already eased).
 * radial: rel * factor (raised to `minPush` metres along the same direction when shorter; an entry at the
 * centre goes straight up); storeys: (0, level * storeyGap, 0).
 */
export function explodeOffset(table: ExplodeTable, i: number, p: ExplodeParams, k: number, out = new Vector3()): Vector3 {
  out.set(0, 0, 0);
  if (usesRadial(p.mode)) {
    const rx = table.rel[i * 3]!;
    const ry = table.rel[i * 3 + 1]!;
    const rz = table.rel[i * 3 + 2]!;
    out.set(rx * p.factor, ry * p.factor, rz * p.factor);
    if (p.minPush > 0) {
      const len = out.length();
      if (len < p.minPush) {
        const rl = Math.hypot(rx, ry, rz);
        if (rl < 1e-6) out.set(0, p.minPush, 0);
        else out.set(rx, ry, rz).multiplyScalar(p.minPush / rl);
      }
    }
  }
  if (usesStoreys(p.mode)) out.y += table.level[i]! * p.storeyGap;
  return out.multiplyScalar(k);
}

/** Eased progress toward 1 (exploded) or 0 (collapsed), driven by an external clock. */
export class ExplodeAnim {
  /** Eased progress 0..1 as of the last update. */
  value = 0;
  private from = 0;
  private to = 0;
  private t0 = 0;
  private dur = DEFAULT_EXPLODE_MS;

  get target(): number {
    return this.to;
  }

  /** True while moving. */
  get moving(): boolean {
    return this.value !== this.to;
  }

  /** Snap back to collapsed with no motion. */
  reset(): void {
    this.value = this.from = this.to = 0;
  }

  /** Start moving from the current value toward `to` (a fresh ease from wherever it is). */
  go(to: 0 | 1, now: number, durationMs: number): void {
    this.from = this.value;
    this.to = to;
    this.t0 = now;
    this.dur = Math.max(1, durationMs);
  }

  /** Advance to `now`; returns the eased value. */
  update(now: number): number {
    const raw = Math.min(1, Math.max(0, (now - this.t0) / this.dur));
    const k = easeInOutCubic(raw);
    this.value = this.from + (this.to - this.from) * k;
    if (raw >= 1) this.value = this.to;
    return this.value;
  }
}
