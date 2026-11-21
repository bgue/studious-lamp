// What the HUD shows while a `schedule4d` cue runs, computed from the plan and the clock only (so a video that steps frame by frame
// draws the same as the screen): the schedule date and ISO week, % complete (planned, actual), the current activities, the milestone
// caption, the S-curve and the data-date mark. Pure; the drawing is in src/anim/hud/fourd.ts.

import type { FourDPlan } from '../../schedule/types';
import type { Cue, Score } from '../score';
import { tradeColour } from './look';
import { resolvePlan } from './plans';
import { mapSpan, planTimeAt, secondsAtPlan } from './timeline';

export type ScheduleCue = Extract<Cue, { kind: 'schedule4d' }>;

/** The schedule4d cue that runs at `t` (the latest started when several), with its plan; null when none. */
export function scheduleCueAt(score: Score, t: number): { cue: ScheduleCue; plan: FourDPlan; index: number } | null {
  let best: { cue: ScheduleCue; plan: FourDPlan; index: number } | null = null;
  score.cues.forEach((c, index) => {
    if (c.kind !== 'schedule4d') return;
    if (t < c.at - 1e-9 || t > c.at + Math.max(0, c.dur) + 1e-9) return;
    const plan = resolvePlan(c.plan);
    if (!plan) return;
    if (!best || c.at >= best.cue.at) best = { cue: c, plan, index };
  });
  return best;
}

const pad = (n: number, w = 2): string => String(n).padStart(w, '0');

/** `2027-03-14` of a plan time (the wall time read as UTC). */
export function isoDate(ms: number): string {
  const d = new Date(ms);
  return `${pad(d.getUTCFullYear(), 4)}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}`;
}

/** ISO 8601 week number (1..53) and its week-year. */
export function isoWeek(ms: number): { week: number; year: number } {
  const d = new Date(Date.UTC(new Date(ms).getUTCFullYear(), new Date(ms).getUTCMonth(), new Date(ms).getUTCDate()));
  const day = d.getUTCDay() || 7;
  d.setUTCDate(d.getUTCDate() + 4 - day);
  const year = d.getUTCFullYear();
  const week = Math.ceil(((d.getTime() - Date.UTC(year, 0, 1)) / 86400000 + 1) / 7);
  return { week, year };
}

/** A plan time from an ISO local string ('2027-03-14' or '2027-03-14T08:00'), read as UTC; NaN when it is not a date. */
export function parsePlanDate(s: string | undefined): number {
  if (!s) return NaN;
  const m = /^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?/.exec(s);
  if (!m) return NaN;
  return Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3]), Number(m[4] ?? 0), Number(m[5] ?? 0));
}

/** Linear interpolation over samples sorted by time; clamped at both ends. */
function sample(pts: ReadonlyArray<readonly [number, number]>, at: number): number {
  if (pts.length === 0) return 0;
  if (at <= pts[0]![0]) return pts[0]![1];
  const last = pts[pts.length - 1]!;
  if (at >= last[0]) return last[1];
  let lo = 0;
  let hi = pts.length - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (pts[mid]![0] <= at) lo = mid;
    else hi = mid;
  }
  const a = pts[lo]!;
  const b = pts[hi]!;
  return b[0] > a[0] ? a[1] + ((at - a[0]) / (b[0] - a[0])) * (b[1] - a[1]) : b[1];
}

export interface ActivityRow {
  code: string;
  name: string;
  trade?: string;
  colour: string;
  elements: number;
  critical: boolean;
}

export interface ScurvePoint {
  at: number;
  planned: number;
  actual?: number;
}

export interface FourDView {
  /** Plan time now (ms) and the cue progress. */
  planMs: number;
  progress: number;
  date: string;
  week: number;
  weekYear: number;
  /** 0..100 */
  plannedPct: number;
  /** Absent when the plan has no actuals up to now. */
  actualPct?: number;
  activities: ActivityRow[];
  /** Activities running now beyond the five listed. */
  moreActivities: number;
  /** The milestone held on screen now (name), with 0..1 fade-in/out alpha. */
  milestone: { name: string; alpha: number } | null;
  /** Position of the data date on the cue, 0..1 of the cue (null: no data date or outside the window). */
  dataDate: number | null;
  /** Colours of the active trades now, for the legend. */
  trades: Array<{ trade: string; colour: string }>;
  hasCritical: boolean;
  curve: ScurvePoint[];
  window: { from: number; to: number };
  hasActual: boolean;
}

export const MAX_ACTIVITIES = 5;

/** The 4D view of the HUD at score time `t`; null when no schedule4d cue runs then. */
export function fourdViewAt(score: Score, t: number): { view: FourDView; cue: ScheduleCue; plan: FourDPlan } | null {
  const hit = scheduleCueAt(score, t);
  if (!hit) return null;
  const { cue, plan } = hit;
  const dur = Math.max(0, cue.dur);
  const p = dur > 1e-9 ? Math.min(1, Math.max(0, (t - cue.at) / dur)) : 1;
  return { view: viewAt(plan, p, dur), cue, plan };
}

/** The view at cue progress `p` (cue length `dur` seconds, for the milestone hold). */
export function viewAt(plan: FourDPlan, p: number, dur: number): FourDView {
  const ms = planTimeAt(plan, p);
  const wk = isoWeek(ms);
  const planned = plan.progress.map((q) => [q.at, q.planned] as const);
  const actualPts = plan.progress.filter((q) => q.actual !== undefined).map((q) => [q.at, q.actual!] as const);
  const lastActual = actualPts.length ? actualPts[actualPts.length - 1]![0] : -Infinity;
  const plannedPct = Math.round(sample(planned, ms) * 1000) / 10;
  const actualPct = actualPts.length && ms <= lastActual + 1e-9 ? Math.round(sample(actualPts, ms) * 1000) / 10 : undefined;

  // current activities: running now, the biggest first
  const running = plan.tasks.filter((k) => !k.milestone && k.start <= ms && ms < k.end && k.elements > 0);
  running.sort((a, b) => b.elements - a.elements || a.code.localeCompare(b.code));
  const rows: ActivityRow[] = running.slice(0, MAX_ACTIVITIES).map((k) => ({
    code: k.code,
    name: k.name,
    ...(k.trade !== undefined ? { trade: k.trade } : {}),
    colour: tradeColour(k.trade, plan.style.colours),
    elements: k.elements,
    critical: k.critical,
  }));
  const trades: Array<{ trade: string; colour: string }> = [];
  for (const k of running) {
    const key = k.trade ?? 'Work';
    if (!trades.some((x) => x.trade === key)) trades.push({ trade: key, colour: tradeColour(k.trade, plan.style.colours) });
  }

  // milestone caption: held for style.milestoneHold video seconds from the moment the film reaches it
  let milestone: FourDView['milestone'] = null;
  const hold = Math.max(0, plan.style.milestoneHold);
  const span = mapSpan(plan);
  const nowS = p * span;
  if (hold > 0 && span > 0) {
    const scale = dur > 0 ? span / dur : 1; // map seconds per cue second
    let best: { name: string; s: number } | null = null;
    for (const m of plan.milestones) {
      const s = secondsAtPlan(plan, m.at);
      const since = (nowS - s) / scale;
      if (since >= -1e-9 && since <= hold + 1e-9 && (!best || s >= best.s)) best = { name: m.name, s };
    }
    if (best) {
      const since = (nowS - best.s) / scale;
      const f = Math.min(0.3, hold / 2);
      const alpha = f > 0 ? Math.max(0, Math.min(1, since / f, (hold - since) / f)) : 1;
      if (alpha > 0) milestone = { name: best.name, alpha };
    }
  }

  const dd = parsePlanDate(plan.schedule.dataDate);
  let dataDate: number | null = null;
  if (Number.isFinite(dd) && dd >= plan.window.from && dd <= plan.window.to && span > 0) dataDate = secondsAtPlan(plan, dd) / span;

  return {
    planMs: ms,
    progress: p,
    date: isoDate(ms),
    week: wk.week,
    weekYear: wk.year,
    plannedPct,
    ...(actualPct !== undefined ? { actualPct } : {}),
    activities: rows,
    moreActivities: Math.max(0, running.length - rows.length),
    milestone,
    dataDate,
    trades,
    hasCritical: running.some((k) => k.critical),
    curve: plan.progress,
    window: plan.window,
    hasActual: actualPts.length > 0,
  };
}
