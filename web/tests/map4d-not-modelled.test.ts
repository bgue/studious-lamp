import { describe, expect, it } from 'vitest';
import { viewAt } from '../src/anim/fourd/live';
import { setNotModelled, notModelledCodes, parseConfig, serializeConfig } from '../src/map4d/scheduleConfig';
import { pickStart, stepStates, STEP_OF_SECTION } from '../src/map4d/stepBar';
import { buildReport } from '../src/schedule/report';
import { linkSchedule } from '../src/schedule/link';
import { buildPlan } from '../src/schedule/plan';
import { buildConfig, buildModel, buildSchedule } from './fourd-fixtures';

const model = buildModel();
const schedule = buildSchedule();

describe('activities marked not in the model', () => {
  const config = buildConfig();
  const links = linkSchedule(schedule, model, config, []);
  const plain = buildReport(schedule, links, model, { config });
  const gaps = plain.unlinkedActivities.map((a) => a.code);

  it('is a gap until marked, then it moves to "not in the model" and the numbers follow', () => {
    expect(gaps.length).toBeGreaterThan(1);
    const marked = setNotModelled(config, gaps, true);
    expect(notModelledCodes(marked).sort()).toEqual([...gaps].sort());
    const r = buildReport(schedule, links, model, { config: marked });
    expect(r.coverage.activities.notModelled).toBe(gaps.length);
    expect(r.coverage.activities.unlinked).toBe(0);
    expect(r.coverage.activities.total).toBe(plain.coverage.activities.total - gaps.length);
    expect(r.coverage.activities.linked).toBe(plain.coverage.activities.linked);
    expect(r.coverage.activities.ratio).toBe(1);
    expect(r.unlinkedActivities.every((a) => a.notModelled)).toBe(true);
    expect(plain.coverage.activities.notModelled).toBe(0);
  });

  it('keeps other overrides, drops empty entries, and travels in the .4d.json', () => {
    const c0 = { ...config, activities: { X1: { query: 'class = "IfcSlab"' } } };
    const on = setNotModelled(c0, ['X1', 'X2'], true);
    expect(on.activities).toEqual({ X1: { query: 'class = "IfcSlab"', notModelled: true }, X2: { notModelled: true } });
    const off = setNotModelled(on, ['X1', 'X2'], false);
    expect(off.activities).toEqual({ X1: { query: 'class = "IfcSlab"' } });
    const back = parseConfig(serializeConfig(on));
    expect(back.problems).toEqual([]);
    expect(notModelledCodes(back.config!).sort()).toEqual(['X1', 'X2']);
  });

  it('the plan flags them and the HUD view names at most two, then the rest as a count', () => {
    const marked = setNotModelled(config, gaps, true);
    const plan = buildPlan(schedule, links, model, config.style, { config: marked });
    const flagged = plan.tasks.filter((t) => t.notModelled);
    expect(flagged.length).toBeGreaterThan(0);
    expect(buildPlan(schedule, links, model, config.style, { config }).tasks.some((t) => t.notModelled)).toBe(false);
    let most = 0;
    for (let p = 0; p <= 1; p += 0.02) {
      const v = viewAt(plan, p, 20);
      if (v.notInModel) { expect(v.notInModel.names.length).toBeLessThanOrEqual(2); most = Math.max(most, v.notInModel.names.length + v.notInModel.more); }
    }
    expect(most).toBeGreaterThan(0);
    expect(viewAt(buildPlan(schedule, links, model, config.style, { config }), 0.5, 20).notInModel).toBeNull();
  });
});

describe('the three steps', () => {
  const base = { accepted: 0, proposed: 0, hasSchedule: false, hasLinks: false, acceptedLinks: 0, ties: 0, suggestions: 0 };
  it('starts on Link without a schedule or a link, on Film when linked', () => {
    expect(pickStart(base)).toBe('link');
    expect(pickStart({ hasSchedule: true, acceptedLinks: 0 })).toBe('link');
    expect(pickStart({ hasSchedule: true, acceptedLinks: 4 })).toBe('film');
  });
  it('shows done, a count that needs attention, or not started', () => {
    expect(stepStates(base).map((s) => s.kind)).toEqual(['idle', 'idle', 'idle']);
    const s = stepStates({ ...base, accepted: 5, hasSchedule: true, hasLinks: true, acceptedLinks: 3, ties: 3 });
    expect(s[0]).toMatchObject({ kind: 'done' });
    expect(s[1]).toEqual({ id: 'link', kind: 'attention', text: '3 ties' });
    expect(stepStates({ ...base, proposed: 2 })[0]).toEqual({ id: 'map', kind: 'attention', text: '2 to decide' });
    expect(stepStates({ ...base, hasSchedule: true, hasLinks: true, acceptedLinks: 3 })[1]!.kind).toBe('done');
  });
  it('puts every section in a step', () => {
    expect(Object.keys(STEP_OF_SECTION).sort()).toEqual(['assign', 'configure', 'coverage', 'io', 'link', 'play', 'schedule', 'style', 'suggest', 'values']);
    expect(STEP_OF_SECTION.play).toBe('film');
  });
});
