// Pure 4D plan evaluation: the plan time of a cue moment (time map), the state of an element at a plan time (binary search), and the
// PlanEvaluator that keeps every element's state while the plan time moves forward (O(changes) per frame through one sorted list of
// interval starts) and evaluates from scratch after a jump back (seek). No DOM, no three.js.

import type { ElementState, ElementTimeline, FourDPlan } from '../../schedule/types';

export type Interval = ElementTimeline['intervals'][number];

/** The states as small numbers (typed arrays); index = code. */
export const STATE_NAMES: readonly ElementState[] = ['future', 'existing', 'active', 'complete', 'removed', 'behind', 'ahead'];
export const S_FUTURE = 0;
export const S_EXISTING = 1;
export const S_ACTIVE = 2;
export const S_COMPLETE = 3;
export const S_REMOVED = 4;
export const S_BEHIND = 5;
export const S_AHEAD = 6;

const CODE = new Map<string, number>(STATE_NAMES.map((s, i) => [s, i]));
export const stateCode = (s: ElementState): number => CODE.get(s) ?? S_FUTURE;

// ---------------------------------------------------------------- time map

type TimeMap = FourDPlan['timeMap'];

/** The plan's time map; for a plan without one, a unit map of the window (plan window -> 0..1 s). */
function mapOf(plan: Pick<FourDPlan, 'timeMap' | 'window'>): TimeMap {
  if (plan.timeMap && plan.timeMap.length >= 2) return plan.timeMap;
  if (plan.timeMap && plan.timeMap.length === 1) return [plan.timeMap[0]!, [plan.timeMap[0]![0], plan.timeMap[0]![1] + 1]];
  return [
    [plan.window.from, 0],
    [plan.window.to, 1],
  ];
}

/** Total video seconds the time map spans (last second minus first). */
export function mapSpan(plan: Pick<FourDPlan, 'timeMap' | 'window'>): number {
  const m = mapOf(plan);
  return m[m.length - 1]![1] - m[0]![1];
}

/**
 * Plan time (ms) at progress `p` (0..1) of a schedule4d cue: the time map is scaled to the cue's duration, so the whole map plays
 * over the cue. Flat stretches of the map (a hold at a milestone) keep the plan time still while the cue goes on.
 */
export function planTimeAt(plan: Pick<FourDPlan, 'timeMap' | 'window'>, p: number): number {
  const m = mapOf(plan);
  const s0 = m[0]![1];
  const s = s0 + Math.min(1, Math.max(0, p)) * (m[m.length - 1]![1] - s0);
  // Last segment whose start second is <= s (binary search), so a jump in plan time at one second takes the later value.
  let lo = 0;
  let hi = m.length - 1;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (m[mid]![1] <= s) lo = mid;
    else hi = mid - 1;
  }
  if (lo >= m.length - 1) return m[m.length - 1]![0];
  const a = m[lo]!;
  const b = m[lo + 1]!;
  const ds = b[1] - a[1];
  return ds > 1e-12 ? a[0] + ((s - a[1]) / ds) * (b[0] - a[0]) : b[0];
}

/** Video seconds (from the start of the map) at plan time `ms`: the inverse of planTimeAt; the first second of a hold. */
export function secondsAtPlan(plan: Pick<FourDPlan, 'timeMap' | 'window'>, ms: number): number {
  const m = mapOf(plan);
  const s0 = m[0]![1];
  if (ms <= m[0]![0]) return 0;
  const last = m[m.length - 1]!;
  if (ms >= last[0]) {
    // The first point that reaches the end plan time (a hold at the end starts there).
    for (const pt of m) if (pt[0] >= last[0]) return pt[1] - s0;
    return last[1] - s0;
  }
  let lo = 0;
  let hi = m.length - 1;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (m[mid]![0] <= ms) lo = mid;
    else hi = mid - 1;
  }
  // Exactly at a hold: its first point.
  if (m[lo]![0] === ms) while (lo > 0 && m[lo - 1]![0] === m[lo]![0]) lo--;
  const a = m[lo]!;
  const b = m[Math.min(lo + 1, m.length - 1)]!;
  const dp = b[0] - a[0];
  return (dp > 0 ? a[1] + ((ms - a[0]) / dp) * (b[1] - a[1]) : a[1]) - s0;
}

/** Video seconds per plan ms around `ms` (the local speed of the film; 0 in a hold). */
export function secondsPerMs(plan: Pick<FourDPlan, 'timeMap' | 'window'>, ms: number): number {
  const m = mapOf(plan);
  let lo = 0;
  let hi = m.length - 2;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (m[mid]![0] <= ms) lo = mid;
    else hi = mid - 1;
  }
  const a = m[lo]!;
  const b = m[lo + 1] ?? a;
  const dp = b[0] - a[0];
  return dp > 0 ? (b[1] - a[1]) / dp : 0;
}

// ---------------------------------------------------------------- state lookup

/** Index of the last interval with `from <= t` (binary search); -1 before the first one. */
export function intervalAt(iv: readonly Interval[], t: number): number {
  let lo = 0;
  let hi = iv.length - 1;
  let ans = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (iv[mid]!.from <= t) {
      ans = mid;
      lo = mid + 1;
    } else hi = mid - 1;
  }
  return ans;
}

/** The state of one element at plan time `t`: its latest interval started by `t` (the last state holds); `future` before the first. */
export function stateAt(tl: ElementTimeline, t: number): { state: ElementState; index: number; interval: Interval | null } {
  const i = intervalAt(tl.intervals, t);
  if (i < 0) return { state: 'future', index: -1, interval: null };
  const interval = tl.intervals[i]!;
  return { state: interval.state, index: i, interval };
}

// ---------------------------------------------------------------- the evaluator

/**
 * Keeps the interval index of every element at the current plan time. Forward calls consume a global list of interval starts sorted by
 * time (each call costs the number of intervals that start in between); a call with an earlier time starts over from the beginning
 * (a seek), so the result never depends on how the time got there.
 */
export class PlanEvaluator {
  readonly n: number;
  /** Interval index per element (-1: before its first interval). */
  readonly idx: Int32Array;
  /** State code per element. */
  readonly code: Uint8Array;
  private readonly evTime: Float64Array;
  private readonly evEl: Int32Array;
  private readonly evIv: Int32Array;
  private ptr = 0;
  private lastT = -Infinity;
  private fresh = true;
  private readonly stamp: Uint32Array;
  private gen = 1;

  constructor(private readonly plan: Pick<FourDPlan, 'elements'>) {
    this.n = plan.elements.length;
    this.idx = new Int32Array(this.n).fill(-1);
    this.code = new Uint8Array(this.n);
    this.stamp = new Uint32Array(this.n);
    let m = 0;
    for (const e of plan.elements) m += e.intervals.length;
    const el = new Int32Array(m);
    const iv = new Int32Array(m);
    const tm = new Float64Array(m);
    let k = 0;
    for (let e = 0; e < this.n; e++) {
      const list = plan.elements[e]!.intervals;
      for (let j = 0; j < list.length; j++) {
        el[k] = e;
        iv[k] = j;
        tm[k] = list[j]!.from;
        k++;
      }
    }
    const order = new Uint32Array(m);
    for (let i = 0; i < m; i++) order[i] = i;
    order.sort((a, b) => tm[a]! - tm[b]! || el[a]! - el[b]! || iv[a]! - iv[b]!);
    this.evTime = new Float64Array(m);
    this.evEl = new Int32Array(m);
    this.evIv = new Int32Array(m);
    for (let i = 0; i < m; i++) {
      const o = order[i]!;
      this.evTime[i] = tm[o]!;
      this.evEl[i] = el[o]!;
      this.evIv[i] = iv[o]!;
    }
  }

  /** Forget everything: the next evaluate() reports every element. */
  reset(): void {
    this.idx.fill(-1);
    this.code.fill(S_FUTURE);
    this.ptr = 0;
    this.lastT = -Infinity;
    this.fresh = true;
  }

  /**
   * Move to plan time `t`. Returns the elements whose interval changed since the last call; the first call after construction, a
   * reset or a jump back returns every element (the picture is rebuilt from scratch).
   */
  evaluate(t: number): number[] {
    if (t < this.lastT) this.reset();
    this.lastT = t;
    const changed: number[] = [];
    const g = ++this.gen;
    const fresh = this.fresh;
    this.fresh = false;
    while (this.ptr < this.evTime.length && this.evTime[this.ptr]! <= t) {
      const e = this.evEl[this.ptr]!;
      const j = this.evIv[this.ptr]!;
      this.ptr++;
      if (j > this.idx[e]!) {
        this.idx[e] = j;
        this.code[e] = stateCode(this.plan.elements[e]!.intervals[j]!.state);
        if (!fresh && this.stamp[e] !== g) {
          this.stamp[e] = g;
          changed.push(e);
        }
      }
    }
    if (fresh) for (let e = 0; e < this.n; e++) changed.push(e);
    return changed;
  }

  /** The interval an element is in (null before its first one). */
  intervalOf(e: number): Interval | null {
    const j = this.idx[e]!;
    return j < 0 ? null : this.plan.elements[e]!.intervals[j]!;
  }
}
