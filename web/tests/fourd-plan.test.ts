import { describe, expect, it } from 'vitest';
import { buildPlan, buildTimeMap, orderElements, slotsFor, NON_WORKING_HOURS, WARP_MAX, WARP_MIN } from '../src/schedule/plan';
import { DAY, WorkCalendar, parseLocal, projectCalendar, formatLocal } from '../src/schedule/planTime';
import { linkSchedule } from '../src/schedule/link';
import type { ActivityLink, ElementState, FourDLinks, FourDPlan, FourDStyle } from '../src/schedule/types';
import { DEFAULT_STYLE } from '../src/schedule/types';
import type { FourDElement } from '../src/schedule/model';
import { DATA_DATE, buildConfig, buildModel, buildSchedule, task } from './fourd-fixtures';

const L = (s: string): number => parseLocal(s)!;
const model = buildModel();
const schedule = buildSchedule();
const links = linkSchedule(schedule, model, buildConfig(), []);
const style = (o: Partial<FourDStyle> = {}): FourDStyle => ({ ...DEFAULT_STYLE, ...o });
const plan = (o: Partial<FourDStyle> = {}, opts?: Parameters<typeof buildPlan>[4], l: FourDLinks = links, sch = schedule): FourDPlan => buildPlan(sch, l, model, style(o), { config: buildConfig(), ...opts });
const tl = (p: FourDPlan, g: string) => p.elements.find((e) => e.globalId === g);
const stateAt = (p: FourDPlan, g: string, t: number): ElementState | 'future' | 'none' => {
  const e = tl(p, g);
  if (!e) return 'none';
  return e.intervals.find((i) => t >= i.from && t < i.to)?.state ?? 'future';
};
const states = (p: FourDPlan, g: string): string[] => tl(p, g)?.intervals.map((i) => i.state) ?? [];

describe('plan: planned view (early dates), whole job', () => {
  const p = plan();
  it('windows the whole job and records the schedule and model', () => {
    expect(p.schema).toBe('xray-4d-plan/1');
    expect(p.window).toEqual({ from: L('2027-01-04T08:00'), to: L('2027-02-22T17:00') });
    expect(p.model).toEqual({ identityKey: 'fixture|31|abcd', name: 'fixture.ifc' });
    expect(p.schedule).toEqual({ project: 'TOWER', dataDate: DATA_DATE, sourceHash: 'deadbeefcafe0123' });
    expect(p.style.view).toBe('planned');
  });
  it('an element is future until its slot, active during it, complete after', () => {
    const e = tl(p, 'WALLA3')!; // A410: Feb 8 - Feb 12
    expect(e.intervals.map((i) => [i.state, i.task])).toEqual([['active', 'A410'], ['complete', 'A410']]);
    expect(e.intervals[0]!.from).toBe(L('2027-02-08T08:00'));
    expect(e.intervals[1]!.to).toBe(p.window.to);
    expect(stateAt(p, 'WALLA3', L('2027-02-01T08:00'))).toBe('future');
    expect(stateAt(p, 'WALLA3', L('2027-02-10T08:00'))).toBe('active');
    expect(stateAt(p, 'WALLA3', L('2027-02-20T08:00'))).toBe('complete');
  });
  it('every timeline is sorted, non-overlapping, inside the window and only for linked or existing elements', () => {
    for (const e of p.elements) {
      expect(e.intervals.length).toBeGreaterThan(0);
      e.intervals.forEach((i, k) => {
        expect(i.to).toBeGreaterThan(i.from);
        expect(i.from).toBeGreaterThanOrEqual(p.window.from);
        expect(i.to).toBeLessThanOrEqual(p.window.to);
        if (k) expect(i.from).toBeGreaterThanOrEqual(e.intervals[k - 1]!.to);
      });
    }
    expect(tl(p, 'FURN1')).toBeUndefined();   // unplanned
    expect(tl(p, 'DOOR2')).toBeUndefined();   // only a proposed suggestion: not accepted, does not drive the plan
  });
  it('removal: existing, active (fading out), removed; and elements named by the existing query are existing throughout', () => {
    expect(tl(p, 'OLD1')!.intervals.map((i) => [i.state, i.task])).toEqual([['existing', 'A600'], ['active', 'A600'], ['removed', 'A600']]);
    expect(stateAt(p, 'OLD1', L('2027-01-04T12:00'))).toBe('existing');
    expect(stateAt(p, 'OLD1', L('2027-01-05T12:00'))).toBe('active');
    expect(stateAt(p, 'OLD1', L('2027-02-01T12:00'))).toBe('removed');
  });
  it('an existing element without a remove link is existing throughout', () => {
    const noRemove = linkSchedule(schedule, model, { ...buildConfig(), activities: { A500: { query: "class = 'IfcWindow'" } } }, []);
    const p2 = plan({}, undefined, noRemove);
    expect(tl(p2, 'OLD2')!.intervals).toEqual([{ from: p2.window.from, to: p2.window.to, state: 'existing', task: '' }]);
    // the links' own existing flag works without the config query
    const p3 = buildPlan(schedule, noRemove, model, style());
    expect(states(p3, 'OLD2')).toEqual(['existing']);
    expect(states(buildPlan(schedule, { ...noRemove, model_elements: [] }, model, style(), { existing: ['OLD2'] }), 'OLD2')).toEqual(['existing']);
  });
  it('tasks: milestones flagged, LOE left out, element counts, location and trade', () => {
    expect(p.tasks.map((t) => t.code)).not.toContain('A800');
    const m = p.tasks.find((t) => t.code === 'A100')!;
    expect(m).toMatchObject({ milestone: true, start: L('2027-01-04T08:00'), end: L('2027-01-04T08:00') });
    expect(p.tasks.find((t) => t.code === 'A300')).toMatchObject({ elements: 3, location: 'Level 2', trade: 'CONC', milestone: false, start: L('2027-01-18T08:00'), end: L('2027-01-22T17:00') });
    expect(p.tasks.find((t) => t.code === 'A500')!.elements).toBe(3);
    expect(p.tasks.map((t) => t.start)).toEqual([...p.tasks.map((t) => t.start)].sort((a, b) => a - b));
    expect(p.milestones).toEqual([{ code: 'A100', name: 'Start of works', at: L('2027-01-04T08:00') }, { code: 'A900', name: 'Practical completion', at: L('2027-02-22T17:00') }]);
  });
  it('is deterministic', () => {
    expect(JSON.stringify(plan())).toBe(JSON.stringify(plan()));
  });
});

describe('plan: critical', () => {
  const crit = (o: Partial<FourDStyle>): string[] => plan(o).tasks.filter((t) => t.critical).map((t) => t.code).sort();
  it('total float at or under the limit, or the driving flag', () => {
    expect(crit({ criticalFloatHours: 0 })).toEqual(['A200', 'A210', 'A300', 'A400']);
    expect(crit({ criticalFloatHours: 16 })).toEqual(['A200', 'A210', 'A300', 'A310', 'A400', 'A410']);
  });
  it('null uses only the driving path flag', () => {
    expect(crit({ criticalFloatHours: null })).toEqual(['A300']);
  });
});

describe('plan: actual view', () => {
  const p = plan({ view: 'actual' });
  it('uses actual dates, then remaining dates for active work, early dates after the data date', () => {
    const a210 = p.tasks.find((t) => t.code === 'A210')!;
    expect([a210.start, a210.end]).toEqual([L('2027-01-11T08:00'), L('2027-01-13T17:00')]);      // actual, earlier than early (Jan 15)
    const a300 = p.tasks.find((t) => t.code === 'A300')!;
    expect([a300.start, a300.end]).toEqual([L('2027-01-18T08:00'), L('2027-01-25T17:00')]);      // actual start, remaining finish
    const a310 = p.tasks.find((t) => t.code === 'A310')!;
    expect([a310.start, a310.end]).toEqual([L('2027-01-25T08:00'), L('2027-01-29T17:00')]);      // early
  });
  it('elements: complete at the data date when done, active when in progress, future after', () => {
    const dd = L(DATA_DATE);
    expect(stateAt(p, 'COLA1', dd)).toBe('complete');
    expect(stateAt(p, 'COLA2', dd)).toBe('active');       // sweep_x: A300 runs Jan 18 .. Jan 25; its first slot (COLA2) is running,
    expect(stateAt(p, 'SLAB2', dd)).toBe('future');       // the second (SLAB2) starts on Jan 20 13:00
    expect(stateAt(p, 'SLAB2', L('2027-01-21T12:00'))).toBe('active');
    expect(stateAt(p, 'COLB2', dd)).toBe('future');
    expect(stateAt(p, 'COLB2', L('2027-01-25T12:00'))).toBe('active');
    expect(stateAt(p, 'COLB2', L('2027-01-26T08:00'))).toBe('complete');
    expect(stateAt(p, 'WALLA2', dd)).toBe('future');
  });
  it('never writes behind or ahead (variance view only)', () => {
    for (const e of p.elements) for (const i of e.intervals) expect(['behind', 'ahead']).not.toContain(i.state);
  });
  it('the progress curve has an actual line up to the data date only', () => {
    const dd = L(DATA_DATE);
    for (const row of p.progress) expect(row.actual === undefined).toBe(row.at > dd);
    expect(p.progress.some((r) => r.actual !== undefined)).toBe(true);
  });
});

describe('plan: variance view', () => {
  const p = plan({ view: 'variance' });
  it('uses the target dates as the planned reference', () => {
    const a300 = p.tasks.find((t) => t.code === 'A300')!;
    expect([a300.start, a300.end]).toEqual([L('2027-01-18T08:00'), L('2027-01-19T17:00')]);
  });
  it('behind: planned complete by the data date, not done: from the planned finish until done', () => {
    const e = tl(p, 'COLB2')!;       // last slot of A300: planned end Jan 19 17:00, actual forecast Jan 25 17:00
    expect(e.intervals.map((i) => i.state)).toEqual(['active', 'behind', 'complete']);
    expect(e.intervals[1]!.from).toBe(L('2027-01-19T17:00'));
    expect(e.intervals[1]!.to).toBe(L('2027-01-25T17:00'));
    expect(stateAt(p, 'COLB2', L(DATA_DATE))).toBe('behind');
  });
  it('ahead: done at the data date before the planned finish: from the actual finish until the planned finish', () => {
    const e = tl(p, 'COLA1')!;       // A210: target Jan 11-15, actual Jan 11-13 17:00
    expect(e.intervals.map((i) => i.state)).toEqual(['active', 'ahead', 'complete']);
    expect(e.intervals[1]!.from).toBe(L('2027-01-13T17:00'));
    expect(e.intervals[1]!.to).toBe(L('2027-01-15T17:00'));
  });
  it('on-time and future work stay plain planned', () => {
    expect(states(p, 'SLAB1')).toEqual(['active', 'complete']);
    expect(states(p, 'WALLA3')).toEqual(['active', 'complete']);
  });
  it('without a data date there is nothing to compare', () => {
    const s2 = { ...schedule, project: { ...schedule.project, dataDate: undefined } };
    const p2 = buildPlan(s2, links, model, style({ view: 'variance' }), { config: buildConfig() });
    for (const e of p2.elements) for (const i of e.intervals) expect(['behind', 'ahead']).not.toContain(i.state);
  });
  it('the progress curve has planned and actual', () => {
    expect(p.progress.at(-1)!.planned).toBeCloseTo(1);
    expect(p.progress.find((r) => r.actual !== undefined)).toBeDefined();
  });
});

describe('plan: baseline', () => {
  const base = buildSchedule();
  base.tasks.find((t) => t.code === 'A400')!.dates = { earlyStart: '2027-03-01T08:00', earlyEnd: '2027-03-05T17:00' };
  it('a baseline replaces the planned dates (matched by task code)', () => {
    const p = plan({}, { baseline: base });
    const t = p.tasks.find((x) => x.code === 'A400')!;
    expect([t.start, t.end]).toEqual([L('2027-03-01T08:00'), L('2027-03-05T17:00')]);
    expect(p.window.to).toBe(L('2027-03-05T17:00'));
    expect(p.tasks.find((x) => x.code === 'A300')!.start).toBe(L('2027-01-18T08:00'));
  });
  it('the variance view compares with the baseline', () => {
    const b2 = buildSchedule();
    b2.tasks.find((t) => t.code === 'A210')!.dates = { earlyStart: '2027-01-11T08:00', earlyEnd: '2027-01-12T17:00' };
    const p = plan({ view: 'variance' }, { baseline: b2 });
    expect(p.tasks.find((t) => t.code === 'A210')!.end).toBe(L('2027-01-12T17:00'));
    expect(states(p, 'COLA1')).toEqual(['active', 'complete']); // actual finish Jan 13 is later than baseline, but done: no behind (data date after it)
  });
});

describe('plan: windows', () => {
  it('lookahead from the data date: elements finished before the window are complete from the start', () => {
    const p = plan({ window: { kind: 'lookahead', from: 'dataDate', weeks: 2 } });
    expect(p.window).toEqual({ from: L(DATA_DATE), to: L(DATA_DATE) + 14 * DAY });
    expect(tl(p, 'SLAB1')!.intervals).toEqual([{ from: p.window.from, to: p.window.to, state: 'complete', task: 'A200' }]);
    expect(tl(p, 'COLA1')!.intervals[0]).toMatchObject({ from: p.window.from, state: 'complete' });
    expect(tl(p, 'OLD1')!.intervals).toEqual([{ from: p.window.from, to: p.window.to, state: 'removed', task: 'A600' }]);
  });
  it('work in progress at the window start is active from the start; work inside starts later; work after the window is absent', () => {
    const p = plan({ window: { kind: 'lookahead', from: 'dataDate', weeks: 2 } });
    expect(tl(p, 'SLAB2')!.intervals[0]).toMatchObject({ from: p.window.from, state: 'active', task: 'A300' });
    expect(tl(p, 'WALLA2')!.intervals[0]).toMatchObject({ state: 'active', from: L('2027-01-25T08:00') });
    expect(tl(p, 'COLA3')!.intervals[0]).toMatchObject({ state: 'active', from: L('2027-02-01T08:00') });
    expect(tl(p, 'WALLA3')).toBeUndefined();   // Feb 8 is after Feb 3
    expect(tl(p, 'WIN1')).toBeUndefined();
  });
  it('tasks and milestones are the ones touching the window', () => {
    const p = plan({ window: { kind: 'lookahead', from: 'dataDate', weeks: 2 } });
    expect(p.tasks.map((t) => t.code)).toEqual(['A200', 'A210', 'A300', 'A310', 'A320', 'A400'].filter((c) => c !== 'A200' && c !== 'A210'));
    expect(p.milestones).toEqual([]);
  });
  it('lookahead from a date, in the actual view (actual dates before the window)', () => {
    const p = plan({ view: 'actual', window: { kind: 'lookahead', from: '2027-01-25T08:00', weeks: 1 } });
    expect(p.window).toEqual({ from: L('2027-01-25T08:00'), to: L('2027-02-01T08:00') });
    expect(stateAt(p, 'COLB2', p.window.from)).toBe('active');
    expect(stateAt(p, 'SLAB1', p.window.from)).toBe('complete');
  });
  it('lookahead without a data date starts at the first task', () => {
    const s2 = { ...schedule, project: { ...schedule.project, dataDate: undefined } };
    const p = buildPlan(s2, links, model, style({ window: { kind: 'lookahead', from: 'dataDate', weeks: 1 } }), { config: buildConfig() });
    expect(p.window.from).toBe(L('2027-01-04T08:00'));
  });
  it('a range window clips the intervals', () => {
    const p = plan({ window: { kind: 'range', from: '2027-02-01T00:00', to: '2027-02-10T00:00' } });
    expect(p.window).toEqual({ from: L('2027-02-01T00:00'), to: L('2027-02-10T00:00') });
    expect(tl(p, 'WALLA3')!.intervals.map((i) => [i.state, i.to])).toEqual([['active', L('2027-02-10T00:00')]]);
    expect(stateAt(p, 'SLAB1', L('2027-02-01T00:00'))).toBe('complete');
  });
});

describe('split rules', () => {
  const mk = (id: string, name: string, x: number, y: number, z: number, storey?: string): FourDElement =>
    ({ globalId: id, ifcClass: 'IfcSlab', name, props: {}, ...(storey ? { storey } : {}), bbox: [x - 1, y - 1, z - 1, x + 1, y + 1, z + 1] });
  const els = [mk('a', 'Pour 10', 5, 9, 3, 'Level 2'), mk('b', 'Pour 2', 1, 4, 9, 'Level 3'), mk('c', 'Pour 1', 9, 1, 0, 'Level 1'), mk('d', 'Pour 3', 3, 7, 6, 'Level 2')];
  const order = (rule: Parameters<typeof orderElements>[1]): string[][] => orderElements(els, rule, model).map((g) => g.map((e) => e.globalId));
  it('none: one group, all at once', () => expect(order('none')).toEqual([['a', 'b', 'c', 'd']]));
  it('sweeps order by bbox centre along the axis', () => {
    expect(order('sweep_x')).toEqual([['b'], ['d'], ['a'], ['c']]);
    expect(order('sweep_minus_x')).toEqual([['c'], ['a'], ['d'], ['b']]);
    expect(order('sweep_y')).toEqual([['c'], ['b'], ['d'], ['a']]);
    expect(order('sweep_minus_y')).toEqual([['a'], ['d'], ['b'], ['c']]);
    expect(order('sweep_z')).toEqual([['c'], ['a'], ['d'], ['b']]);
    expect(order('sweep_minus_z')).toEqual([['b'], ['d'], ['a'], ['c']]);
  });
  it('sweeps put elements without a bbox last', () => {
    const n = { globalId: 'n', ifcClass: 'IfcSlab', name: 'x', props: {} } as FourDElement;
    expect(orderElements([n, ...els], 'sweep_x', model).map((g) => g[0]!.globalId)).toEqual(['b', 'd', 'a', 'c', 'n']);
  });
  it('by_storey: one group per storey, bottom up', () => expect(order('by_storey')).toEqual([['c'], ['d', 'a'], ['b']]));
  it('by_name: natural sort (Pour 2 before Pour 10)', () => expect(order('by_name')).toEqual([['c'], ['b'], ['d'], ['a']]));
  it('slots: equal slices overlapping slightly, first starts at the start, last ends at the end', () => {
    const s = slotsFor(4, { start: 0, end: 1000 });
    expect(s[0]!.start).toBe(0);
    expect(s[3]!.end).toBe(1000);
    for (let i = 1; i < 4; i++) { expect(s[i]!.start).toBeGreaterThan(s[i - 1]!.start); expect(s[i]!.start).toBeLessThan(s[i - 1]!.end); }
    const len = s[0]!.end - s[0]!.start;
    s.slice(0, 3).forEach((x) => expect(x.end - x.start).toBeCloseTo(len));
    expect(slotsFor(1, { start: 5, end: 9 })).toEqual([{ start: 5, end: 9 }]);
    expect(slotsFor(3, { start: 5, end: 5 })).toHaveLength(3);
    expect(slotsFor(3, { start: 0, end: 90 }, 0).map((x) => [x.start, x.end])).toEqual([[0, 30], [30, 60], [60, 90]]);
  });
  const custom = (split: ActivityLink['split']): FourDLinks => ({
    ...links, links: [{ id: 'ln-A300-build', activity: 'A300', role: 'build', elements: ['SLAB2', 'COLA2', 'COLB2'], status: 'accepted', split }],
  });
  it('the plan applies the rule: sweep_x staggers the elements, none starts them together', () => {
    const p = plan({}, undefined, custom('sweep_x'));
    const start = (g: string): number => tl(p, g)!.intervals[0]!.from;
    expect(start('COLA2')).toBe(L('2027-01-18T08:00'));        // x centre 0.2
    expect(start('SLAB2')).toBeGreaterThan(start('COLA2'));    // 10
    expect(start('COLB2')).toBeGreaterThan(start('SLAB2'));    // 18.2
    expect(tl(p, 'COLB2')!.intervals[0]!.to).toBe(L('2027-01-22T17:00'));
    expect(stateAt(p, 'COLA2', L('2027-01-18T10:00'))).toBe('active');
    expect(stateAt(p, 'COLB2', L('2027-01-18T10:00'))).toBe('future');
    const q = plan({}, undefined, custom('none'));
    expect(['SLAB2', 'COLA2', 'COLB2'].map((g) => tl(q, g)!.intervals[0]!.from)).toEqual([L('2027-01-18T08:00'), L('2027-01-18T08:00'), L('2027-01-18T08:00')]);
    const r = plan({}, undefined, custom('sweep_minus_x'));
    expect(r.elements.find((e) => e.globalId === 'COLB2')!.intervals[0]!.from).toBe(L('2027-01-18T08:00'));
  });
  it('by_storey and by_name through the plan', () => {
    const wall = (split: ActivityLink['split']): FourDLinks => ({ ...links, links: [{ id: 'x', activity: 'A310', role: 'build', elements: ['WALLA3', 'WALLA1', 'WALLA2'], status: 'accepted', split }] });
    const p = plan({}, undefined, wall('by_storey'));
    const s = (g: string): number => tl(p, g)!.intervals[0]!.from;
    expect(s('WALLA1')).toBeLessThan(s('WALLA2'));
    expect(s('WALLA2')).toBeLessThan(s('WALLA3'));
    const q = plan({}, undefined, wall('by_name'));
    const t = (g: string): number => tl(q, g)!.intervals[0]!.from;
    expect(t('WALLA1')).toBeLessThan(t('WALLA2'));
  });
  it('a link without a split falls back to the config rule', () => {
    const p = plan({}, undefined, { ...links, links: [{ id: 'x', activity: 'A300', role: 'build', elements: ['SLAB2', 'COLA2'], status: 'accepted' }] });
    expect(tl(p, 'COLA2')!.intervals[0]!.from).toBeLessThan(tl(p, 'SLAB2')!.intervals[0]!.from);  // CONC -> sweep_x
  });
});

describe('plan: only accepted links drive it', () => {
  it('proposed, rejected and superseded links are ignored', () => {
    const mk = (status: ActivityLink['status']): FourDLinks => ({ ...links, links: [{ id: 'x', activity: 'A300', role: 'build', elements: ['SLAB2'], status }] });
    for (const s of ['proposed', 'rejected', 'superseded', undefined] as const) expect(plan({}, undefined, mk(s)).elements.find((e) => e.globalId === 'SLAB2')).toBeUndefined();
    expect(plan({}, undefined, mk('accepted')).elements.find((e) => e.globalId === 'SLAB2')).toBeDefined();
  });
  it('milestones and LOE cannot build even when linked', () => {
    const p = plan({}, undefined, { ...links, links: [{ id: 'x', activity: 'A100', role: 'build', elements: ['SLAB2'], status: 'accepted' }, { id: 'y', activity: 'A800', role: 'build', elements: ['SLAB1'], status: 'accepted' }] });
    expect(p.elements).toHaveLength(2); // only OLD1 and OLD2 (existing)
  });
});

describe('working calendar', () => {
  const cal = projectCalendar(schedule);
  it('hours per day from the week table and the exceptions', () => {
    expect(cal.hoursOn(L('2027-01-04T00:00'))).toBe(8);   // Monday
    expect(cal.hoursOn(L('2027-01-09T00:00'))).toBe(0);   // Saturday
    expect(cal.hoursOn(L('2027-02-15T00:00'))).toBe(0);   // exception: holiday
    expect(cal.hoursBetween(L('2027-01-04T00:00'), L('2027-01-06T00:00'))).toBe(16);
    expect(cal.hoursBetween(L('2027-01-04T12:00'), L('2027-01-05T12:00'))).toBe(8);
  });
  it('falls back to Monday to Friday, 8 h', () => {
    expect(new WorkCalendar().hoursOn(L('2027-01-04T00:00'))).toBe(8);
    expect(new WorkCalendar().hoursOn(L('2027-01-10T00:00'))).toBe(0);
  });
  it('round-trips local time', () => expect(formatLocal(L('2027-03-14T08:30'))).toBe('2027-03-14T08:30'));
});

describe('time map', () => {
  const cal = projectCalendar(schedule);
  const sec = (m: Array<[number, number]>, t: number): number => {
    for (let i = m.length - 1; i > 0; i--) {
      if (m[i - 1]![0] <= t && t <= m[i]![0] && m[i]![0] > m[i - 1]![0]) return m[i - 1]![1] + ((t - m[i - 1]![0]) / (m[i]![0] - m[i - 1]![0])) * (m[i]![1] - m[i - 1]![1]);
    }
    return NaN;
  };
  const check = (m: Array<[number, number]>): void => {
    for (let i = 1; i < m.length; i++) { expect(m[i]![1]).toBeGreaterThan(m[i - 1]![1]); expect(m[i]![0]).toBeGreaterThanOrEqual(m[i - 1]![0]); }
  };

  it('is monotonic, starts at 0 and ends at the film length', () => {
    for (const pace of ['fixed', 'warp'] as const) for (const length of [30, 120]) {
      const p = plan({ pace, length });
      check(p.timeMap);
      expect(p.timeMap[0]).toEqual([p.window.from, 0]);
      expect(p.timeMap.at(-1)![0]).toBe(p.window.to);
      expect(p.timeMap.at(-1)![1]).toBeCloseTo(length, 6);
    }
  });
  it('milestone holds: flat plan time for milestoneHold seconds at each milestone', () => {
    const p = plan({ pace: 'fixed', length: 60, milestoneHold: 1.5 });
    for (const m of p.milestones) {
      const idx = p.timeMap.map((k, i) => (k[0] === m.at ? i : -1)).filter((i) => i >= 0);
      expect(idx).toHaveLength(2);
      expect(p.timeMap[idx[1]!]![1] - p.timeMap[idx[0]!]![1]).toBeCloseTo(1.5, 9);
    }
    const none = plan({ pace: 'fixed', length: 60, milestoneHold: 0 });
    expect(new Set(none.timeMap.map((k) => k[0])).size).toBe(none.timeMap.length);
  });
  it('holds are cut back when they would eat the film', () => {
    const p = plan({ pace: 'fixed', length: 2, milestoneHold: 5 });
    check(p.timeMap);
    expect(p.timeMap.at(-1)![1]).toBeCloseTo(2, 6);
  });
  it('fixed pace: working time only (weekends and the holiday take almost none)', () => {
    const wf = L('2027-01-04T00:00');
    const m = buildTimeMap(wf, L('2027-02-22T00:00'), cal, style({ pace: 'fixed', length: 100, milestoneHold: 0 }), [], []);
    const day = (d: string): number => sec(m, L(`${d}T00:00`) + DAY) - sec(m, L(`${d}T00:00`));
    const monday = day('2027-01-04');
    expect(day('2027-01-05')).toBeCloseTo(monday, 9);
    expect(day('2027-01-09') / monday).toBeCloseTo(NON_WORKING_HOURS / 8, 6);    // Saturday
    expect(day('2027-02-15') / monday).toBeCloseTo(NON_WORKING_HOURS / 8, 6);    // holiday
    expect(day('2027-01-09')).toBeLessThan(monday / 100);
  });
  it('days per second sets the pace (and wins over length)', () => {
    const p = plan({ pace: 'fixed', daysPerSecond: 7, length: 999, milestoneHold: 1.5 });
    const days = (p.window.to - p.window.from) / DAY;
    expect(p.timeMap.at(-1)![1]).toBeCloseTo(days / 7 + 2 * 1.5, 6);
  });
  it('warp: busy days get more screen time than quiet ones, within 0.3x..3x of the mean', () => {
    const wf = L('2027-01-04T00:00');
    const wt = wf + 100 * DAY;
    const events: number[] = [];
    for (let i = 0; i < 40; i++) events.push(wf + 50 * DAY + (i % 3) * 3600000);   // a burst in the middle
    for (let i = 0; i < 10; i++) events.push(wf + (5 + i * 9) * DAY);              // a trickle elsewhere
    const m = buildTimeMap(wf, wt, cal, style({ pace: 'warp', length: 100, milestoneHold: 0 }), events, []);
    check(m);
    const rates: number[] = [];
    for (let d = 0; d < 100; d++) {
      const a = wf + d * DAY;
      if (cal.hoursOn(a) === 0) continue;
      rates.push((sec(m, a + DAY) - sec(m, a)) / cal.hoursOn(a));
    }
    const mean = rates.reduce((x, y) => x + y, 0) / rates.length;
    for (const r of rates) { expect(r / mean).toBeGreaterThanOrEqual(WARP_MIN - 0.02); expect(r / mean).toBeLessThanOrEqual(WARP_MAX + 0.02); }
    expect(Math.max(...rates) / mean).toBeGreaterThan(2);
    expect(Math.min(...rates) / mean).toBeLessThan(0.6);
    const busy = rates[Math.floor(rates.length / 2)]!;
    expect(busy).toBeGreaterThan(mean * 2);
    // smoothed: a raw 0 -> burst step would jump by the whole 2.7x clamp range; the smoothing keeps neighbours close
    for (let i = 1; i < rates.length; i++) expect(Math.abs(rates[i]! - rates[i - 1]!) / mean).toBeLessThan(1.2);
  });
  it('warp with no events is the fixed pace', () => {
    const wf = L('2027-01-04T00:00');
    const a = buildTimeMap(wf, wf + 30 * DAY, cal, style({ pace: 'warp', length: 50, milestoneHold: 0 }), [], []);
    const b = buildTimeMap(wf, wf + 30 * DAY, cal, style({ pace: 'fixed', length: 50, milestoneHold: 0 }), [], []);
    expect(a).toEqual(b);
  });
  it('a plan in warp pace gives the busy weeks more room than fixed does', () => {
    const w = plan({ pace: 'warp', milestoneHold: 0 });
    const f = plan({ pace: 'fixed', milestoneHold: 0 });
    const span = (p: FourDPlan, a: string, b: string): number => sec(p.timeMap, L(b)) - sec(p.timeMap, L(a));
    // Feb 8-12 has the most state changes of the schedule; Jan 11-15 (one task) the fewest in comparison
    expect(span(w, '2027-02-01T08:00', '2027-02-12T17:00') / span(f, '2027-02-01T08:00', '2027-02-12T17:00')).not.toBeCloseTo(1, 2);
  });
});

describe('progress curve', () => {
  it('weekly samples from the window start to its end, planned from 0 to 1 and non-decreasing', () => {
    const p = plan();
    expect(p.progress[0]!.at).toBe(p.window.from);
    expect(p.progress.at(-1)!.at).toBe(p.window.to);
    for (let i = 1; i < p.progress.length - 1; i++) expect(p.progress[i]!.at - p.progress[i - 1]!.at).toBe(7 * DAY);
    expect(p.progress[0]!.planned).toBe(0);
    expect(p.progress.at(-1)!.planned).toBe(1);
    for (let i = 1; i < p.progress.length; i++) expect(p.progress[i]!.planned).toBeGreaterThanOrEqual(p.progress[i - 1]!.planned);
    expect(p.progress.every((r) => r.actual === undefined)).toBe(true);   // planned view: no actual line
  });
  it('falls back to activities when nothing is linked', () => {
    const empty: FourDLinks = { ...links, links: [] };
    const p = plan({}, undefined, empty);
    expect(p.progress.at(-1)!.planned).toBe(1);
    expect(p.progress[1]!.planned).toBeGreaterThan(0);
    expect(p.elements.map((e) => e.globalId).sort()).toEqual(['OLD1', 'OLD2']);
  });
  it('an empty schedule still gives a plan', () => {
    const p = buildPlan({ ...schedule, tasks: [] }, { ...links, links: [] }, model, style(), {});
    expect(p.tasks).toEqual([]);
    expect(p.timeMap.length).toBeGreaterThanOrEqual(2);
    const t = task('Z', 'No dates');
    expect(buildPlan({ ...schedule, tasks: [t] }, { ...links, links: [] }, model, style(), {}).tasks).toEqual([]);
  });
});
