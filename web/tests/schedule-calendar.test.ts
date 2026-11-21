// Working-time helpers (src/schedule/calendar.ts) on a ScheduleCalendar: weekends, holidays, split days, half days.
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { addWorkingMinutes, calendarDate, isWorking, workingIntervals, workingMinutesBetween } from '../src/schedule/calendar';
import { parseXer } from '../src/schedule/xer';
import type { ScheduleCalendar } from '../src/schedule/types';

/** Plan time of a P6-style local date-time: ms of Date.UTC of the wall time. */
const at = (s: string): number => {
  const [d, t = '00:00'] = s.split(' ');
  const [y, m, dd] = d!.split('-').map(Number);
  const [hh, mm] = t.split(':').map(Number);
  return Date.UTC(y!, m! - 1, dd!, hh, mm);
};

// Monday to Friday 08:00-12:00 and 13:00-17:00 (a lunch gap), Saturday and Sunday off, a holiday on Tuesday 2027-03-16
// and a half day on Thursday 2027-03-18 (08:00-12:00 only).
const cal: ScheduleCalendar = {
  id: 'std',
  name: 'Standard',
  week: [[], [[8, 12], [13, 17]], [[8, 12], [13, 17]], [[8, 12], [13, 17]], [[8, 12], [13, 17]], [[8, 12], [13, 17]], []],
  exceptions: { '2027-03-16': [], '2027-03-18': [[8, 12]] },
  hoursPerDay: 8,
};

describe('isWorking', () => {
  it('is true in the working hours, false in the lunch gap, at the exact end, and on weekends', () => {
    expect(isWorking(cal, at('2027-03-15 09:00'))).toBe(true);
    expect(isWorking(cal, at('2027-03-15 08:00'))).toBe(true);
    expect(isWorking(cal, at('2027-03-15 12:30'))).toBe(false);
    expect(isWorking(cal, at('2027-03-15 17:00'))).toBe(false);
    expect(isWorking(cal, at('2027-03-13 10:00'))).toBe(false);
    expect(isWorking(cal, at('2027-03-14 10:00'))).toBe(false);
  });
  it('honours holidays and part days from the exceptions', () => {
    expect(isWorking(cal, at('2027-03-16 10:00'))).toBe(false);
    expect(isWorking(cal, at('2027-03-18 10:00'))).toBe(true);
    expect(isWorking(cal, at('2027-03-18 14:00'))).toBe(false);
    expect(calendarDate(at('2027-03-18 14:00'))).toBe('2027-03-18');
  });
  it('lists the intervals of a day, exceptions first', () => {
    expect(workingIntervals(cal, at('2027-03-18 00:00'))).toEqual([[at('2027-03-18 08:00'), at('2027-03-18 12:00')]]);
    expect(workingIntervals(cal, at('2027-03-16 00:00'))).toEqual([]);
  });
});

describe('workingMinutesBetween', () => {
  it('counts a full working day as 480 minutes and skips weekends and holidays', () => {
    expect(workingMinutesBetween(cal, at('2027-03-15 08:00'), at('2027-03-15 17:00'))).toBe(480);
    // Fri 12 (480) + Mon 15 (480); the weekend in between takes nothing
    expect(workingMinutesBetween(cal, at('2027-03-12 08:00'), at('2027-03-15 17:00'))).toBe(960);
    // Mon 15 (480), Tue 16 holiday (0), Wed 17 (480), Thu 18 half day (240), Fri 19 (480)
    expect(workingMinutesBetween(cal, at('2027-03-15 08:00'), at('2027-03-19 17:00'))).toBe(1680);
  });
  it('does not count the lunch gap of a split day', () => {
    expect(workingMinutesBetween(cal, at('2027-03-15 11:00'), at('2027-03-15 14:00'))).toBe(120);
  });
  it('counts a part-day exception and returns a negative number when the order is reversed', () => {
    expect(workingMinutesBetween(cal, at('2027-03-18 08:00'), at('2027-03-18 17:00'))).toBe(240);
    expect(workingMinutesBetween(cal, at('2027-03-15 17:00'), at('2027-03-15 08:00'))).toBe(-480);
    expect(workingMinutesBetween(cal, at('2027-03-15 09:00'), at('2027-03-15 09:00'))).toBe(0);
  });
});

describe('addWorkingMinutes', () => {
  it('adds within a day, across the lunch gap and into the next working day', () => {
    expect(addWorkingMinutes(cal, at('2027-03-15 08:00'), 60)).toBe(at('2027-03-15 09:00'));
    expect(addWorkingMinutes(cal, at('2027-03-15 11:30'), 60)).toBe(at('2027-03-15 13:30'));
    expect(addWorkingMinutes(cal, at('2027-03-15 08:00'), 480)).toBe(at('2027-03-15 17:00'));
    // Mon 17:00 is the end of the day; Tuesday is a holiday, so the next minute is Wednesday 08:01
    expect(addWorkingMinutes(cal, at('2027-03-15 08:00'), 481)).toBe(at('2027-03-17 08:01'));
  });
  it('skips the holiday and the weekend', () => {
    expect(addWorkingMinutes(cal, at('2027-03-15 16:30'), 60)).toBe(at('2027-03-17 08:30'));
    expect(addWorkingMinutes(cal, at('2027-03-19 16:00'), 120)).toBe(at('2027-03-22 09:00'));
  });
  it('starts from the next working moment when the start is not working', () => {
    expect(addWorkingMinutes(cal, at('2027-03-13 10:00'), 30)).toBe(at('2027-03-15 08:30'));
    expect(addWorkingMinutes(cal, at('2027-03-15 12:30'), 30)).toBe(at('2027-03-15 13:30'));
  });
  it('goes backwards for negative minutes, skipping the gaps', () => {
    expect(addWorkingMinutes(cal, at('2027-03-15 13:30'), -30)).toBe(at('2027-03-15 13:00'));
    expect(addWorkingMinutes(cal, at('2027-03-17 08:00'), -1)).toBe(at('2027-03-15 16:59'));
    expect(addWorkingMinutes(cal, at('2027-03-15 09:00'), 0)).toBe(at('2027-03-15 09:00'));
  });
  it('is the inverse of workingMinutesBetween', () => {
    const start = at('2027-03-15 10:20');
    for (const m of [1, 45, 300, 900, 2000]) {
      const end = addWorkingMinutes(cal, start, m);
      expect(workingMinutesBetween(cal, start, end)).toBe(m);
      expect(isWorking(cal, end - 1)).toBe(true);
    }
  });
  it('throws for a calendar with no working time at all', () => {
    const none: ScheduleCalendar = { id: 'x', name: 'Off', week: [[], [], [], [], [], [], []], exceptions: {} };
    expect(() => addWorkingMinutes(none, at('2027-03-15 08:00'), 10)).toThrow(/no working time/);
  });
});

describe('the building calendars from the fixture', () => {
  const s = parseXer(new Uint8Array(readFileSync(resolve(__dirname, 'fixtures/xer/building.xer'))));
  const std = s.calendars.find((c) => c.id === '1')!;
  const site = s.calendars.find((c) => c.id === '2')!;

  it('skips Christmas Day and New Year on the standard calendar', () => {
    expect(isWorking(std, at('2026-12-25 10:00'))).toBe(false);
    expect(isWorking(std, at('2026-12-24 10:00'))).toBe(true);
    expect(isWorking(std, at('2026-12-24 14:00'))).toBe(false);
    // Thu 24 Dec 08:00-12:00 is 4 h, then Mon 28 Dec 08:00 onwards
    expect(addWorkingMinutes(std, at('2026-12-24 08:00'), 240 + 60)).toBe(at('2026-12-28 09:00'));
  });
  it('works Saturdays on the site calendar, and keeps its own holidays', () => {
    expect(isWorking(site, at('2026-12-26 09:00'))).toBe(true);
    expect(isWorking(site, at('2026-12-26 13:00'))).toBe(true);
    expect(isWorking(site, at('2026-12-25 09:00'))).toBe(false);
    expect(workingMinutesBetween(site, at('2027-03-13 07:00'), at('2027-03-14 07:00'))).toBe(480);
  });
});
