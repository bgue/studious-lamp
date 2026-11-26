// The 4D plan builder: schedule + links + model + style -> FourDPlan (what every element is doing at every moment, the time map
// from plan time to film seconds, the progress curve). Design: docs/design/4d-xer-animation.md section 4. Pure.
//
// Decisions (where the design is open):
// - Only ACCEPTED links drive the plan (schema/linkml/README).
// - planned = early dates (target where early are missing; a baseline Schedule replaces them). actual = actual start/finish,
//   remaining finish for work in progress, early dates for work not started. variance = the planned timeline, with `behind`
//   (planned complete by the data date, not done: from the planned finish until it is done) and `ahead` (done at the data date
//   before its planned finish: from the actual finish until the planned finish) elements. Variance compares against the baseline,
//   else the TARGET dates (P6's early dates are the forecast, so they cannot show a variance), else the early dates.
// - `behind` / `ahead` appear in the variance view only.
// - Intervals are clipped to the window; an element complete before the window starts is `complete` from the window start.
//   `future` is never written (before the first interval the element is future); `existing` elements have one interval.
// - Time map: strictly increasing seconds; plan time is flat across a milestone hold. Non-working days get a tiny weight
//   (NON_WORKING_HOURS per day) so the map stays invertible. When both `daysPerSecond` and `length` are set, daysPerSecond wins.

import type { ElementState, ElementTimeline, FourDConfig, FourDLinks, FourDPlan, FourDStyle, PlanTask, Schedule, ScheduleTask, SplitRule } from './types';
import { bboxCentre, storeyOrder } from './model';
import type { FourDElement, FourDModel } from './model';
import { FourDTable } from './model';
import { DAY, actualSpan, isBuildType, isCritical, isMilestone, parseLocal, plannedSpan, projectCalendar, referenceSpan, resolveSplit } from './planTime';
import type { Span, WorkCalendar } from './planTime';
import { compile, parseQuery, QueryError } from '../query';
import { buildTempWorksGroups } from './tempworks';

export { parseLocal, formatLocal, isCritical } from './planTime';

export interface PlanOptions {
  /** A baseline schedule: its dates replace the planned dates (matched by task code). */
  baseline?: Schedule;
  /** For the `existing` query and the split fallbacks of links without a split. */
  config?: FourDConfig;
  /** More GlobalIds that exist before the job starts. */
  existing?: Iterable<string>;
  /** Overlap of consecutive element slots inside an activity, fraction of a slot (default 0.25). */
  overlap?: number;
  /** false: leave the temporary works of the configuration out of the plan (xray-4d plan --no-temporary-works). */
  temporaryWorks?: boolean;
}

/** Weight of a non-working day in the time map, in working hours (a working day weighs its hours). */
export const NON_WORKING_HOURS = 0.02;
export const WARP_MIN = 0.3;
export const WARP_MAX = 3;

interface Raw { from: number; to: number; state: ElementState; task: string }
interface Slot { start: number; end: number }

// ---------------------------------------------------------------- split

const natural = (a: string, b: string): number => a.localeCompare(b, undefined, { numeric: true, sensitivity: 'base' });

/** The elements of an activity in order, as groups: each group is one slice of the activity's duration. */
export function orderElements(els: FourDElement[], rule: SplitRule, model: FourDModel): FourDElement[][] {
  if (rule === 'none') return [els];
  const tie = (a: FourDElement, b: FourDElement): number => natural(a.name, b.name) || natural(a.globalId, b.globalId);
  if (rule === 'by_name') return [...els].sort(tie).map((e) => [e]);
  if (rule === 'by_storey') {
    const order = storeyOrder(model);
    const rank = new Map(order.map((s, i) => [s, i]));
    const groups = new Map<number, FourDElement[]>();
    for (const e of els) {
      const r = e.storey !== undefined ? rank.get(e.storey) ?? order.length : order.length;
      if (!groups.has(r)) groups.set(r, []);
      groups.get(r)!.push(e);
    }
    return [...groups].sort((a, b) => a[0] - b[0]).map(([, g]) => g.sort(tie));
  }
  const axis = rule.endsWith('x') ? 0 : rule.endsWith('y') ? 1 : 2;
  const sign = rule.includes('minus') ? -1 : 1;
  const key = (e: FourDElement): number | null => (e.bbox ? sign * bboxCentre(e.bbox)[axis]! : null);
  return [...els].sort((a, b) => {
    const ka = key(a);
    const kb = key(b);
    if (ka === null || kb === null) return ka === kb ? tie(a, b) : ka === null ? 1 : -1;
    return ka - kb || tie(a, b);
  }).map((e) => [e]);
}

/** Slots of the groups inside [start, end]: equal slices overlapping by `overlap` of a slice, the last one ending at `end`. */
export function slotsFor(groups: number, span: Span, overlap = 0.25): Slot[] {
  const D = span.end - span.start;
  if (groups <= 1 || D <= 0) return Array.from({ length: Math.max(groups, 1) }, () => ({ start: span.start, end: span.end }));
  const step = 1 - overlap;
  const L = D / (1 + (groups - 1) * step);
  return Array.from({ length: groups }, (_v, i) => ({ start: span.start + i * L * step, end: i === groups - 1 ? span.end : span.start + i * L * step + L }));
}

// ---------------------------------------------------------------- intervals

function clipMerge(raws: Raw[], wf: number, wt: number): Array<{ from: number; to: number; state: ElementState; task: string }> {
  const out: Raw[] = [];
  for (const r of raws.sort((a, b) => a.from - b.from || a.to - b.to)) {
    const from = Math.max(r.from, wf);
    const to = Math.min(r.to, wt);
    if (!(to > from)) continue;
    const last = out[out.length - 1];
    if (last && last.state === r.state && last.task === r.task && last.to >= from) last.to = Math.max(last.to, to);
    else out.push({ from, to, state: r.state, task: r.task });
  }
  // sorted, non-overlapping
  for (let i = 1; i < out.length; i++) if (out[i]!.from < out[i - 1]!.to) out[i - 1]!.to = out[i]!.from;
  return out.filter((r) => r.to > r.from);
}

const INF = Number.POSITIVE_INFINITY;

function buildRaws(build: { slot: Slot; task: string } | undefined, remove: { slot: Slot; task: string } | undefined, existing: boolean): Raw[] {
  const raws: Raw[] = [];
  if (!build && !remove) return existing ? [{ from: -INF, to: INF, state: 'existing', task: '' }] : [];
  if (build) {
    raws.push({ from: build.slot.start, to: build.slot.end, state: 'active', task: build.task });
    raws.push({ from: build.slot.end, to: remove ? remove.slot.start : INF, state: 'complete', task: build.task });
  } else if (remove) raws.push({ from: -INF, to: remove.slot.start, state: 'existing', task: remove.task });
  if (remove) {
    raws.push({ from: remove.slot.start, to: remove.slot.end, state: 'active', task: remove.task });
    raws.push({ from: remove.slot.end, to: INF, state: 'removed', task: remove.task });
  }
  return raws;
}

/** Variance: the planned slot with `behind` and `ahead` against the actual slot at the data date. */
function varianceRaws(plan: Slot, act: Slot | undefined, dd: number | undefined, task: string): Raw[] {
  const base: Raw[] = [{ from: plan.start, to: plan.end, state: 'active', task }, { from: plan.end, to: INF, state: 'complete', task }];
  if (!act || dd === undefined) return base;
  const done = act.end <= dd;
  if (plan.end <= dd && !done) {
    return [{ from: plan.start, to: plan.end, state: 'active', task }, { from: plan.end, to: Math.max(act.end, plan.end), state: 'behind', task }, { from: Math.max(act.end, plan.end), to: INF, state: 'complete', task }];
  }
  if (done && act.end < plan.end) {
    return [{ from: plan.start, to: act.end, state: 'active', task }, { from: act.end, to: plan.end, state: 'ahead', task }, { from: plan.end, to: INF, state: 'complete', task }];
  }
  return base;
}

// ---------------------------------------------------------------- the plan

export function buildPlan(schedule: Schedule, links: FourDLinks, model: FourDModel, style: FourDStyle, opts: PlanOptions = {}): FourDPlan {
  const dd = parseLocal(schedule.project.dataDate);
  const baseByCode = new Map((opts.baseline?.tasks ?? []).map((t) => [t.code, t]));
  const taskByCode = new Map(schedule.tasks.map((t) => [t.code, t]));
  const overlap = opts.overlap ?? 0.25;
  const actAttr = new Map((links.activities ?? []).map((a) => [a.task_code, a]));

  const primary = (t: ScheduleTask): Span | undefined =>
    style.view === 'actual' ? actualSpan(t, dd) : style.view === 'variance' ? referenceSpan(t, baseByCode.get(t.code)) : plannedSpan(t, baseByCode.get(t.code));
  const spans = new Map<string, Span>();
  for (const t of schedule.tasks) { const s = primary(t); if (s) spans.set(t.code, s); }

  // existing elements
  const existing = new Set<string>(opts.existing ?? []);
  for (const e of links.model_elements ?? []) if (e.existing) existing.add(e.global_id);
  if (opts.config?.model.existing) {
    try {
      const table = new FourDTable(model);
      const c = compile(parseQuery(opts.config.model.existing), table);
      for (let r = 0; r < table.size; r++) if (c.test(r)) existing.add(model.elements[r]!.globalId);
    } catch (e) { if (!(e instanceof QueryError)) throw e; }
  }

  // window
  const considered = schedule.tasks.filter((t) => spans.has(t.code) && t.type !== 'loe' && t.type !== 'wbsSummary');
  let lo = Math.min(...considered.map((t) => spans.get(t.code)!.start));
  let hi = Math.max(...considered.map((t) => spans.get(t.code)!.end));
  if (!Number.isFinite(lo)) { lo = dd ?? 0; hi = lo + DAY; }
  let wf = lo;
  let wt = hi;
  const w = style.window;
  if (w.kind === 'lookahead') {
    const from = w.from === 'dataDate' ? dd ?? lo : parseLocal(w.from) ?? dd ?? lo;
    wf = from;
    wt = from + w.weeks * 7 * DAY;
  } else if (w.kind === 'range') {
    wf = parseLocal(w.from) ?? lo;
    wt = parseLocal(w.to) ?? hi;
  }
  if (wt <= wf) wt = wf + DAY;

  // accepted links: one build per element (highest confidence, then first), removes by element
  type Entry = { link: FourDLinks['links'] extends infer L ? (L extends Array<infer X> ? X : never) : never; task: ScheduleTask };
  const buildOf = new Map<string, Entry & { conf: number }>();
  const removeOf = new Map<string, Entry>();
  const elCount = new Map<string, number>();
  for (const l of links.links ?? []) {
    if (l.status !== 'accepted') continue;
    const task = taskByCode.get(l.activity);
    if (!task || !spans.has(task.code)) continue;
    if (l.role === 'build') {
      if (!isBuildType(task)) continue;
      for (const g of l.elements) {
        const prev = buildOf.get(g);
        if (!prev || (l.confidence ?? 1) > prev.conf) buildOf.set(g, { link: l, task, conf: l.confidence ?? 1 });
      }
      elCount.set(task.code, (elCount.get(task.code) ?? 0) + l.elements.length);
    } else for (const g of l.elements) if (!removeOf.has(g)) removeOf.set(g, { link: l, task });
  }

  // slots per (view span) for each link
  const elByGid = new Map(model.elements.map((e) => [e.globalId, e]));
  const slotCache = new Map<string, Map<string, Slot>>();
  const slotsOfLink = (l: Entry['link'], task: ScheduleTask, which: 'primary' | 'planned' | 'actual'): Map<string, Slot> => {
    const key = `${l.id}|${which}`;
    const hit = slotCache.get(key);
    if (hit) return hit;
    const sp = which === 'primary' ? spans.get(task.code)!
      : which === 'planned' ? plannedSpan(task, baseByCode.get(task.code)) ?? spans.get(task.code)!
      : actualSpan(task, dd) ?? spans.get(task.code)!;
    const rule = l.split ?? resolveSplit(task.code, actAttr.get(task.code)?.trade, opts.config);
    const present = l.elements.map((g) => elByGid.get(g)).filter((e): e is FourDElement => !!e);
    const groups = orderElements(present, rule, model);
    const slots = slotsFor(groups.length, sp, overlap);
    const out = new Map<string, Slot>();
    groups.forEach((grp, i) => grp.forEach((e) => out.set(e.globalId, slots[i]!)));
    for (const g of l.elements) if (!out.has(g)) out.set(g, { start: sp.start, end: sp.end });
    slotCache.set(key, out);
    return out;
  };

  const elements: ElementTimeline[] = [];
  const events: number[] = [];
  const planItems: Array<{ s: Slot; a?: Slot }> = [];
  const gids = new Set<string>([...buildOf.keys(), ...removeOf.keys(), ...existing]);
  // iterate in model order, then any link-only GlobalIds
  const order: string[] = [];
  const seen = new Set<string>();
  for (const e of model.elements) if (buildOf.has(e.globalId) || removeOf.has(e.globalId) || existing.has(e.globalId)) { order.push(e.globalId); seen.add(e.globalId); }
  for (const g of gids) if (!seen.has(g) && (buildOf.has(g) || removeOf.has(g) || existing.has(g))) { order.push(g); seen.add(g); }

  for (const g of order) {
    const b = buildOf.get(g);
    const r = removeOf.get(g);
    const bSlot = b ? slotsOfLink(b.link, b.task, 'primary').get(g)! : undefined;
    const rSlot = r ? slotsOfLink(r.link, r.task, 'primary').get(g)! : undefined;
    let raws: Raw[];
    if (b && style.view === 'variance' && !r) {
      const aSlot = slotsOfLink(b.link, b.task, 'actual').get(g);
      raws = varianceRaws(bSlot!, aSlot, dd, b.task.code);
    } else raws = buildRaws(b && bSlot ? { slot: bSlot, task: b.task.code } : undefined, r && rSlot ? { slot: rSlot, task: r.task.code } : undefined, existing.has(g));
    const intervals = clipMerge(raws, wf, wt);
    if (!intervals.length) continue;
    elements.push({ globalId: g, intervals });
    for (const iv of intervals) if (iv.from > wf && iv.state !== 'existing') events.push(iv.from);
    if (b && bSlot) {
      const pk = style.view === 'variance' ? 'primary' : 'planned';
      planItems.push({ s: slotsOfLink(b.link, b.task, pk).get(g)!, a: style.view === 'planned' ? undefined : slotsOfLink(b.link, b.task, 'actual').get(g) });
    }
  }

  // temporary works: rules of the configuration -> groups with their own erect and strike times
  const spanOf = new Map<string, { start: number; end: number }>();
  for (const [code, sp] of spans) spanOf.set(code, sp);
  const tw = opts.temporaryWorks === false ? { groups: [] } : buildTempWorksGroups(opts.config?.temporaryWorks, { model, elements, spans: spanOf });
  for (const g of tw.groups) for (const t of [g.erect.from, g.erect.to, g.strike.from, g.strike.to]) if (t > wf && t < wt) events.push(t);

  // tasks and milestones
  const tasks: PlanTask[] = [];
  const milestones: FourDPlan['milestones'] = [];
  for (const t of schedule.tasks) {
    if (t.type === 'loe' || t.type === 'wbsSummary' || t.type === 'other') continue;
    const sp = spans.get(t.code);
    if (!sp) continue;
    const ms = isMilestone(t);
    const at = t.type === 'finishMilestone' ? sp.end : sp.start;
    const start = ms ? at : sp.start;
    const end = ms ? at : sp.end;
    if (end < wf || start > wt) continue;
    const a = actAttr.get(t.code);
    tasks.push({ code: t.code, name: t.name, start, end, critical: isCritical(t, style), milestone: ms, ...(a?.location !== undefined ? { location: a.location } : {}), ...(a?.trade !== undefined ? { trade: a.trade } : {}), elements: elCount.get(t.code) ?? 0, ...(opts.config?.activities?.[t.code]?.notModelled && !elCount.get(t.code) ? { notModelled: true } : {}) });
    if (ms) milestones.push({ code: t.code, name: t.name, at });
    else if (!elCount.get(t.code)) { events.push(Math.max(start, wf + 1), Math.min(end, wt)); }
  }
  tasks.sort((a, b) => a.start - b.start || a.end - b.end || natural(a.code, b.code));
  milestones.sort((a, b) => a.at - b.at || natural(a.code, b.code));

  const cal = projectCalendar(schedule);
  const timeMap = buildTimeMap(wf, wt, cal, style, events, milestones.map((m) => m.at));

  // progress, weekly: by element (fraction of its slot), else by activity
  let items = planItems;
  if (!items.length) {
    items = [];
    for (const t of schedule.tasks.filter(isBuildType)) {
      const p = style.view === 'variance' ? spans.get(t.code) : plannedSpan(t, baseByCode.get(t.code));
      if (p) items.push({ s: p, a: style.view === 'planned' ? undefined : actualSpan(t, dd) });
    }
  }
  const planned = items.map((i) => i.s);
  const actual = items.map((i) => i.a).filter((a): a is Slot => !!a);
  const progress: FourDPlan['progress'] = [];
  const times: number[] = [];
  for (let t = wf; t < wt; t += 7 * DAY) times.push(t);
  times.push(wt);
  const frac = (s: Slot, t: number): number => (t >= s.end ? 1 : t <= s.start ? 0 : (t - s.start) / (s.end - s.start));
  for (const at of times) {
    const row: { at: number; planned: number; actual?: number } = { at, planned: planned.length ? planned.reduce((a, s) => a + frac(s, at), 0) / planned.length : 0 };
    if (style.view !== 'planned' && dd !== undefined && at <= dd && actual.length === items.length) row.actual = actual.reduce((a, s) => a + frac(s, at), 0) / actual.length;
    progress.push(row);
  }

  return {
    schema: 'xray-4d-plan/1',
    model: { identityKey: model.identityKey, name: model.name },
    schedule: { project: schedule.project.shortName, ...(schedule.project.dataDate ? { dataDate: schedule.project.dataDate } : {}), sourceHash: schedule.sourceHash },
    style,
    window: { from: wf, to: wt },
    elements,
    tasks,
    milestones,
    timeMap,
    progress,
    ...(tw.groups.length ? { temporaryWorks: { version: 1 as const, groups: tw.groups } } : {}),
  };
}

// ---------------------------------------------------------------- the time map

/**
 * Plan time -> film seconds: [[planMs, seconds], ...], seconds strictly increasing, plan time non-decreasing (flat across a
 * milestone hold). Knots at every local midnight. A day weighs its working hours on the project calendar (non-working days
 * NON_WORKING_HOURS), times a pace factor: 1 for fixed; for warp the smoothed density of state changes of the day relative to
 * the mean, kept within WARP_MIN..WARP_MAX of the mean. Scaled to style.length (holds included) or to style.daysPerSecond.
 */
export function buildTimeMap(wf: number, wt: number, cal: WorkCalendar, style: FourDStyle, events: number[], milestoneAt: number[]): Array<[number, number]> {
  const d0 = Math.floor(wf / DAY);
  const n = Math.max(1, Math.ceil(wt / DAY) - d0);
  const hours = new Array<number>(n);
  for (let i = 0; i < n; i++) hours[i] = cal.hoursOn((d0 + i) * DAY);
  const rate = new Array<number>(n).fill(1);
  if (style.pace === 'warp') {
    const dens = new Array<number>(n).fill(0);
    for (const t of events) { const i = Math.floor(t / DAY) - d0; if (i >= 0 && i < n) dens[i]! += 1; }
    const wd: number[] = [];
    for (let i = 0; i < n; i++) if (hours[i]! > 0) wd.push(i);
    if (wd.length) {
      const R = 9;
      const sigma = 3;
      const kernel = Array.from({ length: 2 * R + 1 }, (_v, k) => Math.exp(-((k - R) ** 2) / (2 * sigma * sigma)));
      const sm = wd.map((_d, j) => {
        let s = 0;
        let ws = 0;
        for (let k = -R; k <= R; k++) { const jj = j + k; if (jj < 0 || jj >= wd.length) continue; s += dens[wd[jj]!]! * kernel[k + R]!; ws += kernel[k + R]!; }
        return s / ws;
      });
      const mean = sm.reduce((a, b) => a + b, 0) / sm.length;
      if (mean > 0) {
        let r = sm.map((v) => v / mean);
        for (let it = 0; it < 60; it++) {
          const c = r.map((v) => Math.min(WARP_MAX, Math.max(WARP_MIN, v)));
          const m = c.reduce((a, b) => a + b, 0) / c.length;
          const next = c.map((v) => v / m);
          const delta = Math.max(...next.map((v, i) => Math.abs(v - r[i]!)));
          r = next;
          if (delta < 1e-12) break;
        }
        wd.forEach((d, j) => { rate[d] = r[j]!; });
      }
    }
  }
  // base knots (unscaled weight units)
  const knots: Array<[number, number]> = [[wf, 0]];
  let acc = 0;
  for (let i = 0; i < n; i++) {
    const a = Math.max(wf, (d0 + i) * DAY);
    const b = Math.min(wt, (d0 + i + 1) * DAY);
    if (b <= a) continue;
    const f = (b - a) / DAY;
    acc += (hours[i]! > 0 ? hours[i]! * rate[i]! : NON_WORKING_HOURS) * f;
    knots.push([b, acc]);
  }
  const holdTimes = style.milestoneHold > 0 ? [...new Set(milestoneAt.filter((t) => t >= wf && t <= wt))].sort((a, b) => a - b) : [];
  let hold = style.milestoneHold;
  let motion: number;
  if (style.daysPerSecond !== undefined && style.daysPerSecond > 0) motion = Math.max(0.5, (wt - wf) / DAY / style.daysPerSecond);
  else {
    const length = style.length ?? 120;
    if (holdTimes.length * hold > 0.4 * length) hold = (0.4 * length) / holdTimes.length;
    motion = Math.max(0.1, length - holdTimes.length * hold);
  }
  const scale = motion / acc;
  const base = knots.map(([t, s]) => [t, s * scale] as [number, number]);
  const sAt = (t: number): number => {
    let lo = 0;
    let hi = base.length - 1;
    while (hi - lo > 1) { const mid = (lo + hi) >> 1; if (base[mid]![0] <= t) lo = mid; else hi = mid; }
    const [t0, s0] = base[lo]!;
    const [t1, s1] = base[hi]!;
    return t1 === t0 ? s0 : s0 + ((t - t0) / (t1 - t0)) * (s1 - s0);
  };
  if (!holdTimes.length) return base;
  const out: Array<[number, number]> = [];
  let shift = 0;
  let h = 0;
  for (const [t, s] of base) {
    while (h < holdTimes.length && holdTimes[h]! <= t) {
      const ht = holdTimes[h]!;
      const sb = sAt(ht);
      out.push([ht, sb + shift]);
      shift += hold;
      out.push([ht, sb + shift]);
      h++;
    }
    if (!holdTimes.includes(t)) out.push([t, s + shift]);
  }
  return out;
}
