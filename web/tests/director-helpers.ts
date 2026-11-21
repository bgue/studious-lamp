// Helpers of the 4D director tests: a hand-made plan for the docs and compiler tests, and a small synthetic building with plans.
import type { ElementState, FourDPlan, PlanTask } from '../src/schedule/types';
import { DEFAULT_STYLE } from '../src/schedule/types';
import type { DirectorModel } from '../src/schedule/director';
import type { BBox } from '../src/schedule/model';

export const DAY = 86400000;
export const BASE = Date.UTC(2027, 0, 4);

/** The plan the docs examples use ("Tower A"): 2026-09-01 to 2028-05-30 in 120 s, two milestones. */
export function fakePlan(over: Partial<FourDPlan> = {}): FourDPlan {
  const from = Date.UTC(2026, 8, 1);
  const to = Date.UTC(2028, 4, 30);
  return {
    schema: 'xray-4d-plan/1',
    model: { identityKey: 'fake', name: 'Tower A.ifc' },
    schedule: { project: 'TA', sourceHash: 'abc' },
    style: { ...DEFAULT_STYLE },
    window: { from, to },
    elements: [],
    tasks: [],
    milestones: [
      { code: 'M1', name: 'Frame complete', at: Date.UTC(2027, 5, 15) },
      { code: 'M2', name: 'Envelope closed', at: Date.UTC(2027, 10, 2) },
    ],
    timeMap: [[from, 0], [to, 120]],
    progress: [],
    ...over,
  };
}

export const DOCS_PLANS = (name: string): FourDPlan | null => (name === 'Tower A' ? fakePlan() : null);

export interface Work {
  /** Element index (0-based, by creation order). */
  el: number;
  /** Active from..to in video seconds (1 s = 1 day of the plan). */
  from: number;
  to: number;
  task: string;
}

export interface Synth {
  plan: FourDPlan;
  model: DirectorModel;
  gids: string[];
}

/**
 * A synthetic building: `storeys` storeys of 3 m, each with `perStorey` elements: the first four are walls on the footprint's edge
 * (12 x 12 m), the others small elements inside. `work` says when each element is active (video seconds); the film lasts `seconds`.
 * 1 video second = 1 day of the plan; no holds in the time map.
 */
export function synth(opts: { storeys: number; perStorey?: number; seconds: number; work: Work[]; milestones?: Array<{ name: string; at: number }>; style?: Partial<FourDPlan['style']> }): Synth {
  const per = opts.perStorey ?? 8;
  const gids: string[] = [];
  const elements: DirectorModel['elements'][number][] = [];
  for (let s = 0; s < opts.storeys; s++) {
    for (let k = 0; k < per; k++) {
      const gid = `S${s}E${k}`;
      gids.push(gid);
      let bbox: BBox;
      const z = s * 3;
      const walls: BBox[] = [[0, 0, z, 12, 0.3, z + 3], [11.7, 0, z, 12, 12, z + 3], [0, 11.7, z, 12, 12, z + 3], [0, 0, z, 0.3, 12, z + 3]];
      if (k < 4) bbox = walls[k]!;
      else bbox = [2 + (k - 4) * 1.5, 2 + s * 0.2, s * 3, 3 + (k - 4) * 1.5, 3 + s * 0.2, s * 3 + 3];
      elements.push({ globalId: gid, bbox, storey: `Level ${s + 1}` });
    }
  }
  const model: DirectorModel = { elements, storeys: Array.from({ length: opts.storeys }, (_, s) => ({ name: `Level ${s + 1}`, elevation: s * 3 })) };
  const ms = (sec: number): number => BASE + sec * DAY;
  const tl = new Map<number, Array<{ from: number; to: number; state: ElementState; task: string }>>();
  const tasks = new Map<string, PlanTask>();
  for (const w of [...opts.work].sort((a, b) => a.from - b.from)) {
    if (!tl.has(w.el)) tl.set(w.el, []);
    const list = tl.get(w.el)!;
    list.push({ from: ms(w.from), to: ms(w.to), state: 'active', task: w.task });
    list.push({ from: ms(w.to), to: Infinity, state: 'complete', task: w.task });
    const t = tasks.get(w.task);
    if (!t) tasks.set(w.task, { code: w.task, name: `Task ${w.task}`, start: ms(w.from), end: ms(w.to), critical: false, milestone: false, elements: 1 });
    else {
      t.start = Math.min(t.start, ms(w.from));
      t.end = Math.max(t.end, ms(w.to));
      t.elements++;
    }
  }
  const planElements = gids.map((gid, i) => ({ globalId: gid, intervals: (tl.get(i) ?? []).map((iv, j, a) => (j === a.length - 1 ? { ...iv, to: ms(opts.seconds) } : iv)) }));
  const plan: FourDPlan = {
    schema: 'xray-4d-plan/1',
    model: { identityKey: 'synth', name: 'synth.ifc' },
    schedule: { project: 'S', sourceHash: 'x' },
    style: { ...DEFAULT_STYLE, length: opts.seconds, ...opts.style },
    window: { from: ms(0), to: ms(opts.seconds) },
    elements: planElements,
    tasks: [...tasks.values()],
    milestones: (opts.milestones ?? []).map((m, i) => ({ code: `M${i}`, name: m.name, at: ms(m.at) })),
    timeMap: [[ms(0), 0], [ms(opts.seconds), opts.seconds]],
    progress: [],
  };
  return { plan, model, gids };
}

/** Element index of storey `s`, number `k`. */
export const el = (s: number, k: number, per = 8): number => s * per + k;
