// Working-time helpers on a ScheduleCalendar (src/schedule/types.ts). Times are plan times: ms of Date.UTC of the local
// wall time, so there are no time zones and no DST jumps. Week index 0 = Sunday .. 6 = Saturday, as in ScheduleCalendar.
// An exception for a date (ISO 'YYYY-MM-DD') replaces that weekday's hours; an empty exception is a holiday.

import type { ScheduleCalendar } from './types';

const MIN_MS = 60000;
const HOUR_MS = 3600000;
const DAY_MS = 86400000;
/** How far addWorkingMinutes looks for working time before it gives up (about 30 years). */
const SEARCH_DAYS = 366 * 30;

type Interval = [number, number];

const dayStart = (ms: number): number => Math.floor(ms / DAY_MS) * DAY_MS;

/** The ISO date ('2027-03-14') of a plan time. */
export function calendarDate(ms: number): string {
  return new Date(ms).toISOString().slice(0, 10);
}

/** Working intervals [from, to) of the day that starts at `dayMs` (a midnight), in order. */
export function workingIntervals(cal: ScheduleCalendar, dayMs: number): Interval[] {
  const start = dayStart(dayMs);
  const hours = cal.exceptions[calendarDate(start)] ?? cal.week[new Date(start).getUTCDay()] ?? [];
  const out: Interval[] = [];
  for (const [h0, h1] of hours) {
    if (h1 > h0) out.push([start + h0 * HOUR_MS, start + h1 * HOUR_MS]);
  }
  return out.sort((a, b) => a[0] - b[0]);
}

/** True when the plan time falls inside a working interval of the calendar. */
export function isWorking(cal: ScheduleCalendar, ms: number): boolean {
  return workingIntervals(cal, ms).some(([from, to]) => ms >= from && ms < to);
}

/**
 * Working minutes between two plan times (fractional). Negative when `bMs` is before `aMs`.
 * Weekends, holidays and the gaps of split days take no time.
 */
export function workingMinutesBetween(cal: ScheduleCalendar, aMs: number, bMs: number): number {
  if (bMs < aMs) return -workingMinutesBetween(cal, bMs, aMs);
  let total = 0;
  for (let day = dayStart(aMs); day < bMs; day += DAY_MS) {
    for (const [from, to] of workingIntervals(cal, day)) {
      const lo = Math.max(from, aMs);
      const hi = Math.min(to, bMs);
      if (hi > lo) total += hi - lo;
    }
  }
  return total / MIN_MS;
}

/**
 * The plan time that lies `minutes` working minutes after `ms` (before it when negative). Starting at a non-working
 * moment counts from the next working moment. Throws when the calendar has no working time within about 30 years.
 */
export function addWorkingMinutes(cal: ScheduleCalendar, ms: number, minutes: number): number {
  if (minutes === 0) return ms;
  let remaining = Math.abs(minutes) * MIN_MS;
  let cursor = ms;
  if (minutes > 0) {
    let day = dayStart(ms);
    for (let i = 0; i < SEARCH_DAYS; i++, day += DAY_MS) {
      for (const [from, to] of workingIntervals(cal, day)) {
        if (to <= cursor) continue;
        const start = Math.max(from, cursor);
        const available = to - start;
        if (available >= remaining) return start + remaining;
        remaining -= available;
        cursor = to;
      }
    }
  } else {
    let day = dayStart(ms);
    for (let i = 0; i < SEARCH_DAYS; i++, day -= DAY_MS) {
      const intervals = workingIntervals(cal, day).reverse();
      for (const [from, to] of intervals) {
        if (from >= cursor) continue;
        const end = Math.min(to, cursor);
        const available = end - from;
        if (available >= remaining) return end - remaining;
        remaining -= available;
        cursor = from;
      }
    }
  }
  throw new Error(`calendar ${cal.name || cal.id} has no working time within ${SEARCH_DAYS} days of ${calendarDate(ms)}`);
}
