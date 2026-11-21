import { describe, expect, it } from 'vitest';
import { buildDemoPlan, tradeOfClass } from '../src/anim/fourd/demoPlan';
import type { DemoModel } from '../src/anim/fourd/demoPlan';
import { clearPlans, getPlan, registerPlan, resolvePlan } from '../src/anim/fourd/plans';
import { PlanEvaluator, STATE_NAMES, intervalAt, mapSpan, planTimeAt, secondsAtPlan, secondsPerMs, stateAt } from '../src/anim/fourd/timeline';
import type { ElementTimeline, FourDPlan } from '../src/schedule/types';
import { DEFAULT_STYLE } from '../src/schedule/types';

/** A deterministic pseudo random generator. */
function rng(seed: number): () => number {
  let s = seed >>> 0;
  return () => {
    s = (Math.imul(s, 1664525) + 1013904223) >>> 0;
    return s / 4294967296;
  };
}

const STATES = ['existing', 'active', 'complete', 'removed', 'behind', 'ahead'] as const;

function randomElements(n: number, seed: number): ElementTimeline[] {
  const r = rng(seed);
  const out: ElementTimeline[] = [];
  for (let i = 0; i < n; i++) {
    const k = Math.floor(r() * 4);
    let t = Math.floor(r() * 50);
    const intervals: ElementTimeline['intervals'] = [];
    for (let j = 0; j < k; j++) {
      const len = 1 + Math.floor(r() * 20);
      intervals.push({ from: t, to: t + len, state: STATES[Math.floor(r() * STATES.length)]!, task: `T${j}` });
      t += len + Math.floor(r() * 3);
    }
    out.push({ globalId: `g${i}`, intervals });
  }
  return out;
}

const planOf = (elements: ElementTimeline[], extra: Partial<FourDPlan> = {}): FourDPlan => ({
  schema: 'xray-4d-plan/1',
  model: { identityKey: 'k', name: 'm' },
  schedule: { project: 'P', sourceHash: 'h' },
  style: { ...DEFAULT_STYLE },
  window: { from: 0, to: 100 },
  elements,
  tasks: [],
  milestones: [],
  timeMap: [[0, 0], [100, 10]],
  progress: [],
  ...extra,
});

describe('stateAt (binary search)', () => {
  const tl: ElementTimeline = {
    globalId: 'a',
    intervals: [
      { from: 10, to: 20, state: 'active', task: 'A' },
      { from: 20, to: 30, state: 'complete', task: 'A' },
      { from: 50, to: 60, state: 'removed', task: 'B' },
    ],
  };
  it('is future before the first interval and holds the last state after the last', () => {
    expect(stateAt(tl, 0).state).toBe('future');
    expect(stateAt(tl, 9.99).index).toBe(-1);
    expect(stateAt(tl, 10).state).toBe('active');
    expect(stateAt(tl, 19.9).state).toBe('active');
    expect(stateAt(tl, 20).state).toBe('complete');
    expect(stateAt(tl, 40).state).toBe('complete'); // a gap holds the previous state
    expect(stateAt(tl, 55).state).toBe('removed');
    expect(stateAt(tl, 1e9).state).toBe('removed');
    expect(intervalAt([], 5)).toBe(-1);
  });
});

describe('PlanEvaluator', () => {
  it('agrees with the binary search at every time, going forward', () => {
    const plan = planOf(randomElements(300, 7));
    const ev = new PlanEvaluator(plan);
    for (let t = -2; t <= 90; t += 0.5) {
      ev.evaluate(t);
      for (let e = 0; e < plan.elements.length; e++) {
        const want = stateAt(plan.elements[e]!, t);
        expect(STATE_NAMES[ev.code[e]!], `e${e} t${t}`).toBe(want.state);
        expect(ev.idx[e]).toBe(want.index);
      }
    }
  });

  it('reports only what changed on a forward step, and everything on the first call', () => {
    const plan = planOf(randomElements(200, 3));
    const ev = new PlanEvaluator(plan);
    expect(ev.evaluate(5).length).toBe(200);
    const before = Array.from(ev.idx);
    const changed = new Set(ev.evaluate(30));
    for (let e = 0; e < 200; e++) expect(changed.has(e), `e${e}`).toBe(before[e] !== ev.idx[e]);
    expect(ev.evaluate(30)).toEqual([]);
  });

  it('seeks: a jump back and a jump to the same time give the same picture as a fresh start', () => {
    const plan = planOf(randomElements(250, 11));
    const a = new PlanEvaluator(plan);
    for (const t of [10, 40, 80, 20, 60, 5, 95]) {
      a.evaluate(t);
      const fresh = new PlanEvaluator(plan);
      fresh.evaluate(t);
      expect(Array.from(a.idx), `t${t}`).toEqual(Array.from(fresh.idx));
      expect(Array.from(a.code)).toEqual(Array.from(fresh.code));
    }
    // a jump back reports every element (the picture is rebuilt)
    a.evaluate(90);
    expect(a.evaluate(10).length).toBe(250);
  });

  it('handles intervals that start at the same time and an element without intervals', () => {
    const plan = planOf([
      { globalId: 'x', intervals: [{ from: 5, to: 5, state: 'active', task: 'A' }, { from: 5, to: 9, state: 'complete', task: 'A' }] },
      { globalId: 'y', intervals: [] },
    ]);
    const ev = new PlanEvaluator(plan);
    ev.evaluate(5);
    expect(STATE_NAMES[ev.code[0]!]).toBe('complete');
    expect(STATE_NAMES[ev.code[1]!]).toBe('future');
    expect(ev.intervalOf(1)).toBeNull();
  });
});

describe('time map', () => {
  const plan = planOf([], { window: { from: 1000, to: 5000 }, timeMap: [[1000, 0], [2000, 1], [2000, 3], [5000, 6]] });

  it('scales the whole map to the cue: progress 0..1 covers plan time from the first to the last point', () => {
    expect(planTimeAt(plan, 0)).toBe(1000);
    expect(planTimeAt(plan, 1)).toBe(5000);
    expect(planTimeAt(plan, 1 / 6)).toBeCloseTo(2000, 6); // second 1 of 6
    expect(planTimeAt(plan, 0.5)).toBeCloseTo(2000, 6); // second 3: the end of the hold
    expect(planTimeAt(plan, 0.75)).toBeCloseTo(3500, 6); // second 4.5, half way up the last segment
    expect(planTimeAt(plan, -1)).toBe(1000);
    expect(planTimeAt(plan, 2)).toBe(5000);
  });

  it('holds the plan time still in a flat stretch (a milestone dwell)', () => {
    const a = planTimeAt(plan, 0.2);
    const b = planTimeAt(plan, 0.4);
    expect(a).toBeCloseTo(2000, 6);
    expect(b).toBeCloseTo(2000, 6);
  });

  it('does not depend on the length of the cue, only on progress', () => {
    const scaled = planOf([], { timeMap: [[1000, 0], [2000, 10], [2000, 30], [5000, 60]], window: { from: 1000, to: 5000 } });
    for (const p of [0, 0.1, 0.3, 0.5, 0.8, 1]) expect(planTimeAt(scaled, p)).toBeCloseTo(planTimeAt(plan, p), 6);
    expect(mapSpan(scaled)).toBe(60);
  });

  it('inverts: seconds at a plan time, and the local speed', () => {
    expect(secondsAtPlan(plan, 1000)).toBe(0);
    expect(secondsAtPlan(plan, 1500)).toBeCloseTo(0.5, 6);
    expect(secondsAtPlan(plan, 2000)).toBeCloseTo(1, 6); // the first second of the hold
    expect(secondsAtPlan(plan, 3500)).toBeCloseTo(4.5, 6);
    expect(secondsAtPlan(plan, 9999)).toBeCloseTo(6, 6);
    expect(secondsPerMs(plan, 1500)).toBeCloseTo(0.001, 9);
    expect(secondsPerMs(plan, 4000)).toBeCloseTo(0.001, 9);
  });

  it('falls back to a linear map over the window when the plan has none', () => {
    const bare = planOf([], { timeMap: [], window: { from: 0, to: 200 } });
    expect(planTimeAt(bare, 0.5)).toBe(100);
  });
});

describe('plan registry', () => {
  it('resolves an inline plan and a name', () => {
    clearPlans();
    const p = planOf([]);
    expect(resolvePlan(p)).toBe(p);
    expect(resolvePlan({ name: 'x' })).toBeNull();
    registerPlan('x', p);
    expect(getPlan('x')).toBe(p);
    expect(resolvePlan({ name: 'x' })).toBe(p);
    clearPlans();
  });
});

describe('demo plan', () => {
  const classes = ['IfcSlab', 'IfcWall', 'IfcColumn', 'IfcDuctSegment', 'IfcCovering', 'IfcWindow'];
  const model: DemoModel = {
    name: 'T',
    storeys: [{ id: 5, name: 'L2', elevation: 3 }, { id: 4, name: 'L1', elevation: 0 }, { id: 6, name: 'L3', elevation: 6 }],
    elements: Array.from({ length: 120 }, (_, i) => ({ globalId: `e${i}`, ifcClass: classes[i % classes.length]!, storey: i % 10 === 0 ? null : 4 + (i % 3), bounds: [i, 0, 0, i + 1, 1, 1] })),
  };
  const plan = buildDemoPlan(model);

  it('groups by storey bottom-up with one milestone per storey and a handover', () => {
    expect(plan.milestones.length).toBe(4);
    expect(plan.milestones[0]!.name).toContain('L1');
    expect(plan.milestones[0]!.at).toBeLessThan(plan.milestones[1]!.at);
    expect(plan.tasks.every((t) => t.elements > 0)).toBe(true);
    expect(new Set(plan.tasks.map((t) => t.trade)).size).toBeGreaterThanOrEqual(3);
    expect(plan.tasks.filter((t) => t.critical).every((t) => t.trade === 'Structure')).toBe(true);
    expect(tradeOfClass('IfcSlab')).toBe('Structure');
    expect(tradeOfClass('IfcDuctSegment')).toBe('Services');
  });

  it('builds every element: future at the start, complete at the end, active in between', () => {
    const ev = new PlanEvaluator(plan);
    ev.evaluate(plan.window.from - 1);
    expect(Array.from(ev.code).every((c) => STATE_NAMES[c] === 'future')).toBe(true);
    ev.evaluate(plan.window.to);
    expect(Array.from(ev.code).every((c) => STATE_NAMES[c] === 'complete')).toBe(true);
    ev.evaluate((plan.window.from + plan.window.to) / 2);
    const states = new Set(Array.from(ev.code).map((c) => STATE_NAMES[c]));
    expect(states.has('active') && states.has('complete') && states.has('future')).toBe(true);
  });

  it('has a time map that increases, a progress curve that ends at 1 and actuals up to the data date', () => {
    for (let i = 1; i < plan.timeMap.length; i++) {
      expect(plan.timeMap[i]![0]).toBeGreaterThanOrEqual(plan.timeMap[i - 1]![0]);
      expect(plan.timeMap[i]![1]).toBeGreaterThanOrEqual(plan.timeMap[i - 1]![1]);
    }
    expect(plan.progress[plan.progress.length - 1]!.planned).toBeCloseTo(1, 6);
    expect(plan.progress.some((q) => q.actual !== undefined)).toBe(true);
    expect(plan.progress[plan.progress.length - 1]!.actual).toBeUndefined();
    expect(plan.schedule.dataDate).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });

  it('is deterministic', () => {
    expect(JSON.stringify(buildDemoPlan(model))).toBe(JSON.stringify(plan));
  });
});
