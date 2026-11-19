// Clash to issue, the pure part: the key an issue is found again by, the plan of a raise (what is new, what was raised before,
// what no longer occurs), the choice of "top N by severity" and the camera region of a pair. No DOM, no three.js.
// Tested in tests/issues-clash.test.ts. The browser part is clashRaise.ts; docs: docs-features/issues.md.

import type { Box6 } from '../bcf/plan';
import type { Vec3 } from '../bcf/model';

/** The checks that can raise issues. */
export type ClashCheck = 'penetration' | 'clearance';
export const CLASH_CHECKS: readonly ClashCheck[] = ['penetration', 'clearance'];
export const CLASH_LABEL: Record<ClashCheck, string> = { penetration: 'penetration', clearance: 'clearance' };

/** Above this many results to raise, the user is asked first and "top N by severity" is offered. */
export const MAX_BATCH = 200;

/** What a topic remembers of the result it was raised from (side file `clash`). */
export interface ClashRef {
  check: ClashCheck;
  /** `clashKey(check, a, b)`. */
  key: string;
  /** The two GlobalIds, sorted. */
  a: string;
  b: string;
  /** ISO time the latest run did not report the pair any more; absent while it occurs. */
  missing?: string;
}

/** The identity of a result: the check type and the sorted GlobalId pair. The same pair in either order is one result. */
export function clashKey(check: ClashCheck, a: string, b: string): string {
  const [x, y] = a <= b ? [a, b] : [b, a];
  return `${check}|${x}|${y}`;
}

export function clashRef(check: ClashCheck, a: string, b: string): ClashRef {
  const [x, y] = a <= b ? [a, b] : [b, a];
  return { check, key: clashKey(check, a, b), a: x, b: y };
}

export function isClashCheck(v: unknown): v is ClashCheck {
  return v === 'penetration' || v === 'clearance';
}

/** A result of a check, ready to become an issue. */
export interface ClashResult {
  check: ClashCheck;
  /** GlobalIds of the two elements (the MEP element or focus element first). */
  a: string;
  b: string;
  /** Larger is worse: the order of "top N by severity". */
  severity: number;
  title: string;
  description: string;
  /** BCF priority. */
  priority: string;
  /** Where the two meet, viewer frame; the pin and the centre of the sketch's rectangle. */
  location: Vec3;
  /** The region the camera frames, viewer frame. */
  region: Box6;
  /** What the sketch is tied to. */
  attach: { kind: 'penetration' } | { kind: 'measurement'; distanceM: number; label: string; pointA: Vec3; pointB: Vec3 };
}

export const resultKey = (r: Pick<ClashResult, 'check' | 'a' | 'b'>): string => clashKey(r.check, r.a, r.b);

/** The topic fields that matter to a merge. */
export interface ExistingClash {
  topic: string;
  ref: ClashRef;
  /** The topic's status counts as open. */
  open: boolean;
}

export interface ClashPlan {
  /** Chosen results that no issue exists for yet: these get raised. */
  fresh: ClashResult[];
  /** Chosen results an issue exists for: left as they are. */
  already: Array<{ result: ClashResult; topic: string }>;
  /** Issues of this check, inside the scope of the run, that the run does not report any more. */
  resolved: ExistingClash[];
  /** Of `resolved`, those not yet marked "Not found in latest run". */
  toFlag: ExistingClash[];
  /** Of `resolved`, those still open: offered for closing. */
  toClose: ExistingClash[];
  /** Issues marked not found that the run reports again. */
  backAgain: ExistingClash[];
}

/**
 * Compare the latest run with the issues raised before.
 *   all     every result of the run (the table without filters): decides what "no longer occurs" means
 *   chosen  the results to raise (the filtered or selected rows), a subset of `all`
 *   inScope whether an existing pair could have been found by this run (a run with another focus or scope says nothing about it)
 * Several existing issues with one key count once (the first stands).
 */
export function planClashRaise(check: ClashCheck, existing: readonly ExistingClash[], all: readonly ClashResult[], chosen: readonly ClashResult[], inScope: (a: string, b: string) => boolean = () => true): ClashPlan {
  const byKey = new Map<string, ExistingClash>();
  for (const e of existing) if (e.ref.check === check && !byKey.has(e.ref.key)) byKey.set(e.ref.key, e);
  const seen = new Set(all.map(resultKey));
  const plan: ClashPlan = { fresh: [], already: [], resolved: [], toFlag: [], toClose: [], backAgain: [] };
  const taken = new Set<string>();
  for (const r of chosen) {
    const k = resultKey(r);
    if (taken.has(k)) continue;
    taken.add(k);
    const have = byKey.get(k);
    if (have) plan.already.push({ result: r, topic: have.topic });
    else plan.fresh.push(r);
  }
  for (const [k, e] of byKey) {
    if (seen.has(k)) {
      if (e.ref.missing) plan.backAgain.push(e);
      continue;
    }
    if (!inScope(e.ref.a, e.ref.b)) continue;
    plan.resolved.push(e);
    if (!e.ref.missing) plan.toFlag.push(e);
    if (e.open) plan.toClose.push(e);
  }
  return plan;
}

/** The `n` worst results (stable: equal severities keep their order), worst first. */
export function topBySeverity<T extends { severity: number }>(results: readonly T[], n: number): T[] {
  return results.map((r, i) => ({ r, i })).sort((x, y) => y.r.severity - x.r.severity || x.i - y.i).slice(0, Math.max(0, n)).map((x) => x.r);
}

/** The counts the panels show: new / already raised / not found in the latest run. */
export interface ClashCounts {
  fresh: number;
  already: number;
  resolved: number;
}
export const countsOf = (p: ClashPlan): ClashCounts => ({ fresh: p.fresh.length, already: p.already.length, resolved: p.resolved.length });

export function countsText(c: ClashCounts): string {
  return `${c.fresh} new, ${c.already} already raised, ${c.resolved} not found in the latest run`;
}

/** The note an issue gets when the latest run does not report its pair any more. */
export const NOT_FOUND_NOTE = 'Not found in latest run. The check no longer reports this pair, so it may be resolved. Close the issue if it is.';
export const FOUND_AGAIN_NOTE = 'Found again in the latest run.';

// ---------------------------------------------------------------- the camera region of a pair

const inflate = (b: Box6, d: number): Box6 => [b[0] - d, b[1] - d, b[2] - d, b[3] + d, b[4] + d, b[5] + d];
const union = (a: Box6, b: Box6): Box6 => [Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.min(a[2], b[2]), Math.max(a[3], b[3]), Math.max(a[4], b[4]), Math.max(a[5], b[5])];
const meet = (a: Box6, b: Box6): Box6 | null => {
  const lo = [Math.max(a[0], b[0]), Math.max(a[1], b[1]), Math.max(a[2], b[2])];
  const hi = [Math.min(a[3], b[3]), Math.min(a[4], b[4]), Math.min(a[5], b[5])];
  return lo[0]! <= hi[0]! && lo[1]! <= hi[1]! && lo[2]! <= hi[2]! ? [lo[0]!, lo[1]!, lo[2]!, hi[0]!, hi[1]!, hi[2]!] : null;
};

/**
 * The region of two elements the camera should frame: where they are within `gap` metres of each other (a long pipe beside a long
 * beam is framed where they meet, not end to end). The union of both boxes when they have no such region.
 */
export function pairRegion(a: Box6, b: Box6, gap: number, minHalf = 0.4): Box6 {
  const near = meet(inflate(a, gap + 0.2), inflate(b, gap + 0.2));
  const r = near ?? union(a, b);
  const c: Vec3 = [(r[0] + r[3]) / 2, (r[1] + r[4]) / 2, (r[2] + r[5]) / 2];
  const half = [Math.max(minHalf, (r[3] - r[0]) / 2), Math.max(minHalf, (r[4] - r[1]) / 2), Math.max(minHalf, (r[5] - r[2]) / 2)];
  return [c[0] - half[0]!, c[1] - half[1]!, c[2] - half[2]!, c[0] + half[0]!, c[1] + half[1]!, c[2] + half[2]!];
}

/** The closest points of two boxes (one on each), viewer frame: the ends of the clearance between them. */
export function closestPoints(a: Box6, b: Box6): [Vec3, Vec3] {
  const pa: Vec3 = [0, 0, 0];
  const pb: Vec3 = [0, 0, 0];
  for (let i = 0; i < 3; i++) {
    const lo = Math.max(a[i]!, b[i]!);
    const hi = Math.min(a[i + 3]!, b[i + 3]!);
    if (lo <= hi) { pa[i] = pb[i] = (lo + hi) / 2; } // overlapping on this axis
    else if (a[i + 3]! < b[i]!) { pa[i] = a[i + 3]!; pb[i] = b[i]!; }
    else { pa[i] = a[i]!; pb[i] = b[i + 3]!; }
  }
  return [pa, pb];
}

export const mmText = (m: number): string => `${Math.round(m * 1000)} mm`;
