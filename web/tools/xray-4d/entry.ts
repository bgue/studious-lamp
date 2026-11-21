// Bundle entry for the xray-4d CLI: tools/xray-4d.mjs builds this (vite ssr, one ES module, no dependencies) into
// tools/xray-4d/schedule.bundle.mjs when it is missing or older than src/schedule. Only pure modules are re-exported.
export { parseXer, decodeXer, parseCalendarData } from '../../src/schedule/xer';
export { calendarDate, isWorking, workingIntervals, workingMinutesBetween, addWorkingMinutes } from '../../src/schedule/calendar';
export type { Schedule, ScheduleTask, ScheduleCalendar, ScheduleWbs } from '../../src/schedule/types';
