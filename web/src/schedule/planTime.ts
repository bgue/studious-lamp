// Time helpers shared by the linker, the plan builder and the report: local-time parsing, the date set each task contributes
// to each view, the critical test, the split rule resolution and a small working-time calendar.
//
// TODO: when src/schedule/calendar.ts exists (the XER parser's calendar module), switch WorkCalendar to it. WorkCalendar only
// needs `hoursOn(dayStartMs)`.

import type { FourDConfig, FourDStyle, Schedule, ScheduleCalendar, ScheduleTask, SplitRule } from './types';

export const HOUR = 3600000;
export const DAY = 86400000;

/** '2027-03-14T08:00' (or with seconds, or a plain date) -> ms of Date.UTC (local wall time read as UTC). */
export function parseLocal(s: string | undefined | null): number | undefined {
  if (!s) return undefined;
  const m = /^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2}))?)?/.exec(s.trim());
  if (!m) return undefined;
  const t = Date.UTC(+m[1]!, +m[2]! - 1, +m[3]!, +(m[4] ?? 0), +(m[5] ?? 0), +(m[6] ?? 0));
  return Number.isFinite(t) ? t : undefined;
}

/** ms -> '2027-03-14T08:00'. */
export function formatLocal(ms: number): string {
  return new Date(ms).toISOString().slice(0, 16);
}

export function formatDate(ms: number): string {
  return new Date(ms).toISOString().slice(0, 10);
}

// ---------------------------------------------------------------- spans per view

export interface Span { start: number; end: number }

const span = (a: number | undefined, b: number | undefined): Span | undefined => {
  if (a === undefined && b === undefined) return undefined;
  const start = a ?? b!;
  const end = b ?? a!;
  return { start, end: Math.max(start, end) };
};

/** Planned: early dates (target dates where early are missing); a baseline task's dates replace the task's own. */
export function plannedSpan(task: ScheduleTask, baseline?: ScheduleTask): Span | undefined {
  const d = (baseline ?? task).dates;
  return span(parseLocal(d.earlyStart) ?? parseLocal(d.targetStart), parseLocal(d.earlyEnd) ?? parseLocal(d.targetEnd));
}

/** The reference for the variance view: the baseline, else the target dates, else the early dates. */
export function referenceSpan(task: ScheduleTask, baseline?: ScheduleTask): Span | undefined {
  const d = (baseline ?? task).dates;
  return span(parseLocal(d.targetStart) ?? parseLocal(d.earlyStart), parseLocal(d.targetEnd) ?? parseLocal(d.earlyEnd))
    ?? plannedSpan(task, baseline);
}

/**
 * Actual view: actual start/finish where present; work in progress runs from its actual start to its remaining finish (the
 * forecast, never before the data date); work not started uses its remaining dates, else its early dates.
 */
export function actualSpan(task: ScheduleTask, dataDate: number | undefined): Span | undefined {
  const d = task.dates;
  const as = parseLocal(d.actualStart);
  const ae = parseLocal(d.actualEnd);
  if (as !== undefined && ae !== undefined) return { start: as, end: Math.max(as, ae) };
  if (as !== undefined) {
    let end = parseLocal(d.remainingEnd) ?? parseLocal(d.earlyEnd) ?? parseLocal(d.targetEnd) ?? as;
    if (task.status !== 'complete' && dataDate !== undefined) end = Math.max(end, dataDate);
    return { start: as, end: Math.max(as, end) };
  }
  if (ae !== undefined) {
    const start = parseLocal(d.earlyStart) ?? parseLocal(d.targetStart) ?? ae;
    return { start: Math.min(start, ae), end: ae };
  }
  return span(parseLocal(d.remainingStart) ?? parseLocal(d.earlyStart) ?? parseLocal(d.targetStart),
    parseLocal(d.remainingEnd) ?? parseLocal(d.earlyEnd) ?? parseLocal(d.targetEnd));
}

/** Tasks that become geometry: tasks and resource-dependent tasks. Milestones, LOE and WBS summaries never do. */
export const isBuildType = (t: ScheduleTask): boolean => t.type === 'task' || t.type === 'resource';
export const isMilestone = (t: ScheduleTask): boolean => t.type === 'milestone' || t.type === 'finishMilestone';

/** Critical: total float at or under the style's hours, or on the driving path. */
export function isCritical(task: ScheduleTask, style: FourDStyle): boolean {
  if (task.driving) return true;
  return style.criticalFloatHours !== null && task.totalFloatHours !== undefined && task.totalFloatHours <= style.criticalFloatHours + 1e-9;
}

/** The split rule for an activity: its override, else the config by trade ('*' = default), else 'none'. */
export function resolveSplit(code: string, trade: string | undefined, config: FourDConfig | undefined): SplitRule {
  const a = config?.activities?.[code]?.split;
  if (a) return a;
  const by = config?.split;
  if (by) {
    if (trade !== undefined) {
      if (by[trade]) return by[trade]!;
      const l = trade.toLowerCase();
      for (const k in by) if (k.toLowerCase() === l) return by[k]!;
    }
    if (by['*']) return by['*']!;
  }
  return 'none';
}

export function scheduleByCode(schedule: Schedule): Map<string, ScheduleTask> {
  return new Map(schedule.tasks.map((t) => [t.code, t]));
}

// ---------------------------------------------------------------- working time

const DEFAULT_WEEK: Array<Array<[number, number]>> = [[], [[8, 12], [13, 17]], [[8, 12], [13, 17]], [[8, 12], [13, 17]], [[8, 12], [13, 17]], [[8, 12], [13, 17]], []];

/** Working hours per day of a P6 calendar (weekday table plus dated exceptions). Default: Monday to Friday, 8 h. */
export class WorkCalendar {
  private readonly cache = new Map<number, number>();
  constructor(private readonly cal?: ScheduleCalendar) {}

  /** Working hours on the day that starts at `dayStartMs` (UTC midnight of the local date). */
  hoursOn(dayStartMs: number): number {
    const hit = this.cache.get(dayStartMs);
    if (hit !== undefined) return hit;
    const d = new Date(dayStartMs);
    const iso = d.toISOString().slice(0, 10);
    const ex = this.cal?.exceptions?.[iso];
    const ranges = ex ?? this.cal?.week?.[d.getUTCDay()] ?? DEFAULT_WEEK[d.getUTCDay()]!;
    const h = ranges.reduce((s, [a, b]) => s + Math.max(0, b - a), 0);
    this.cache.set(dayStartMs, h);
    return h;
  }

  /** Working hours between two instants (the partial days pro rata). */
  hoursBetween(a: number, b: number): number {
    if (b <= a) return 0;
    let total = 0;
    for (let d = Math.floor(a / DAY) * DAY; d < b; d += DAY) {
      const f = (Math.min(b, d + DAY) - Math.max(a, d)) / DAY;
      total += this.hoursOn(d) * f;
    }
    return total;
  }
}

/** The project's main calendar: the project's default calendar id, else the first calendar, else the default week. */
export function projectCalendar(schedule: Schedule): WorkCalendar {
  const id = schedule.project.calendarId;
  return new WorkCalendar(schedule.calendars.find((c) => c.id === id) ?? schedule.calendars[0]);
}
