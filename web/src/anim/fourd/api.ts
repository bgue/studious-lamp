// window.__xray4d for smoke tests and scripts: build the demo plan of the loaded model, play it, read the state of a plan at a time.
//   demoPlan(opts?)            the demo plan of the loaded model (also registered as "demo")
//   score(plan, seconds, extra?)  a score: one schedule4d cue of `seconds` (plus extra cues)
//   play(plan, seconds, extra?, opts?)  play that score with the score player; false when it cannot start
//   state(at, plan?)           counts of the plan's element states at plan time `at` (ms, or a fraction 0..1 of the window) and the sizes of the groups
//   live()                     what the running schedule has done to the viewer: plan time, progress, hidden / tinted / glowing / active counts
//   bench(plan?, frames?)      ms per frame of the state update alone (evaluator and looks, no viewer), over `frames` frames
//   registerPlan(name, plan), plans()

import type { FourDPlan } from '../../schedule/types';
import { getScorePlayer, SCORE_SCHEMA } from '../score';
import type { Cue, PlayOptions, Score } from '../score';
import { buildDemoPlan } from './demoPlan';
import type { DemoModel, DemoPlanOptions } from './demoPlan';
import { planNames, registerPlan } from './plans';
import { Schedule4dRunner } from './runner';
import type { LookSink } from './runner';
import { PlanEvaluator, STATE_NAMES } from './timeline';

export interface FourDLive {
  planMs: number | null;
  progress: number | null;
  hidden: number;
  alphaOverrides: number;
  tinted: number;
  glow: number;
  active: number;
  completed: number;
}

export interface FourDApi {
  demoPlan(opts?: DemoPlanOptions): FourDPlan;
  score(plan: FourDPlan | { name: string }, seconds: number, extra?: Cue[]): Score;
  play(plan: FourDPlan | { name: string }, seconds: number, extra?: Cue[], opts?: PlayOptions): boolean;
  state(at: number, plan?: FourDPlan): { planMs: number; counts: Record<string, number>; total: number };
  live(): FourDLive;
  bench(plan?: FourDPlan, frames?: number): { frames: number; elements: number; msPerFrame: number; maxMs: number; buildMs: number };
  registerPlan(name: string, plan: FourDPlan): void;
  plans(): string[];
}

declare global {
  interface Window {
    __xray4d?: FourDApi;
  }
}

export interface FourDApiHost {
  model(): DemoModel | null;
  live(): FourDLive;
}

const nullSink: LookSink = {
  setHidden: () => undefined,
  setAlpha: () => undefined,
  setTint: () => undefined,
  setGlow: () => undefined,
  setFocus: () => undefined,
  commit: () => undefined,
  reset: () => undefined,
};

export function makeFourDScore(plan: FourDPlan | { name: string }, seconds: number, extra: Cue[] = []): Score {
  const cues: Cue[] = [{ at: 0, dur: seconds, kind: 'schedule4d', plan }, ...extra];
  const end = cues.reduce((m, c) => Math.max(m, c.at + Math.max(0, c.dur)), 0);
  return { schema: SCORE_SCHEMA, duration: end, cues };
}

export function install4dApi(host: FourDApiHost): FourDApi {
  let last: FourDPlan | null = null;
  const api: FourDApi = {
    demoPlan: (opts) => {
      const m = host.model();
      if (!m) throw new Error('No model loaded');
      const plan = buildDemoPlan(m, opts);
      registerPlan('demo', plan);
      last = plan;
      return plan;
    },
    score: (plan, seconds, extra) => makeFourDScore(plan, seconds, extra),
    play: (plan, seconds, extra, opts) => {
      const p = getScorePlayer();
      if (!p) return false;
      if ('schema' in plan) last = plan;
      return p.play(makeFourDScore(plan, seconds, extra), opts);
    },
    state: (at, plan) => {
      const p = plan ?? last;
      if (!p) throw new Error('No plan: call demoPlan() first');
      const ms = at >= 0 && at <= 1 ? p.window.from + at * (p.window.to - p.window.from) : at;
      const ev = new PlanEvaluator(p);
      ev.evaluate(ms);
      const counts: Record<string, number> = {};
      for (const s of STATE_NAMES) counts[s] = 0;
      for (let e = 0; e < ev.n; e++) counts[STATE_NAMES[ev.code[e]!]!]!++;
      return { planMs: ms, counts, total: ev.n };
    },
    live: () => host.live(),
    bench: (plan, frames = 120) => {
      const p = plan ?? last;
      if (!p) throw new Error('No plan: call demoPlan() first');
      const ids = new Int32Array(p.elements.length).map((_, i) => i);
      const t0 = performance.now();
      const r = new Schedule4dRunner({ plan: p, ids, sink: nullSink, cueDur: frames / 30 });
      const buildMs = performance.now() - t0;
      let total = 0;
      let max = 0;
      for (let f = 0; f <= frames; f++) {
        const a = performance.now();
        r.update(f / frames);
        const d = performance.now() - a;
        if (f > 0) {
          total += d;
          max = Math.max(max, d);
        }
      }
      return { frames, elements: p.elements.length, msPerFrame: total / frames, maxMs: max, buildMs };
    },
    registerPlan,
    plans: planNames,
  };
  window.__xray4d = api;
  return api;
}
