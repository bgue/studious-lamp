// The runner of a `schedule4d` cue: every frame it maps the cue progress to plan time (the plan's time map scaled to the cue), moves
// a PlanEvaluator there and applies the look of each element whose state changed (or whose look still fades) to a LookSink. The sink
// is the viewer (src/anim/fourd/viewerSink.ts) or a fake in the tests. Nothing here touches the DOM.

import type { FourDPlan, PlanTask } from '../../schedule/types';
import type { CueRunner } from '../player';
import type { Look } from './look';
import { lookFor } from './look';
import { PlanEvaluator, S_ACTIVE, S_AHEAD, S_BEHIND, S_COMPLETE, S_FUTURE, planTimeAt, secondsPerMs } from './timeline';

/** What the runner changes in the viewer. Calls are batched: nothing is drawn until commit(). */
export interface LookSink {
  setHidden(id: number, hidden: boolean): void;
  /** 1 clears the alpha override. */
  setAlpha(id: number, alpha: number): void;
  /** null clears the tint. */
  setTint(id: number, rgb: readonly [number, number, number] | null, amount: number): void;
  /** 0 none, 1 active glow, 2 critical (red) glow. */
  setGlow(id: number, kind: 0 | 1 | 2): void;
  /** The x-ray focus: these elements (an empty list: none). */
  setFocus(ids: readonly number[]): void;
  /** The frame's changes are all in. */
  commit(): void;
  /** Put everything back as it was before the first call. */
  reset(): void;
}

export interface Schedule4dRunnerOptions {
  plan: FourDPlan;
  /** Model element id per plan element (same order as plan.elements), -1 where the model has no such GlobalId. */
  ids: ArrayLike<number>;
  sink: LookSink;
  /** The cue's length in video seconds (for the pace of the focus updates). */
  cueDur: number;
  /** The x-ray focus changes at most this often, in video seconds (default 0.25). */
  focusEveryS?: number;
  /** Fade time of what appears or disappears, seconds of film; absent: the plan's style, else the rule (10 % of the interval or 0.6 s). 0: at once. */
  fadeIn?: number;
}

export type ScheduleSet = 'active' | 'completed' | 'critical' | 'future';

export class Schedule4dRunner implements CueRunner {
  readonly plan: FourDPlan;
  readonly evaluator: PlanEvaluator;
  /** Plan time (ms) and cue progress of the last update; NaN before the first. */
  planTime = NaN;
  progress = NaN;
  private readonly ids: ArrayLike<number>;
  private readonly sink: LookSink;
  private readonly tasks = new Map<string, PlanTask>();
  private readonly transient = new Set<number>();
  private readonly hid: Uint8Array;
  private readonly activeFlag: Uint8Array;
  private activeVersion = 0;
  private appliedVersion = -1;
  private lastFocusS = -Infinity;
  private readonly focusEvery: number;
  private readonly cueDur: number;
  private disposed = false;
  private fadeS: number | undefined;
  /** The fade setting each element started its current state with (NaN: not seen yet), so a `fadeDefault` changes only what starts later. */
  private readonly fadeOf: Float64Array;
  private readonly lastCode: Int8Array;

  constructor(opts: Schedule4dRunnerOptions) {
    this.plan = opts.plan;
    this.ids = opts.ids;
    this.sink = opts.sink;
    this.cueDur = opts.cueDur;
    this.focusEvery = opts.focusEveryS ?? 0.25;
    this.fadeS = opts.fadeIn ?? opts.plan.style.fadeIn;
    this.evaluator = new PlanEvaluator(opts.plan);
    for (const t of opts.plan.tasks) this.tasks.set(t.code, t);
    this.hid = new Uint8Array(this.evaluator.n);
    this.activeFlag = new Uint8Array(this.evaluator.n);
    this.fadeOf = new Float64Array(this.evaluator.n).fill(NaN);
    this.lastCode = new Int8Array(this.evaluator.n).fill(-1);
  }

  /** A `fadeDefault` cue: activities that start from now on fade over this many seconds (0: at once). */
  setFadeSeconds(s: number): void {
    this.fadeS = s;
  }

  update(progress: number): void {
    if (this.disposed) return;
    const p = Math.min(1, Math.max(0, progress));
    const t = planTimeAt(this.plan, p);
    const jumpedBack = Number.isFinite(this.planTime) && t < this.planTime;
    this.progress = p;
    this.planTime = t;
    if (jumpedBack) this.transient.clear();
    const changed = this.evaluator.evaluate(t);
    const spm = secondsPerMs(this.plan, t);
    const seen = new Set<number>();
    for (const e of changed) {
      seen.add(e);
      this.apply(e, t, spm);
    }
    if (this.transient.size) for (const e of [...this.transient]) if (!seen.has(e)) this.apply(e, t, spm);
    this.updateFocus(p);
    this.sink.commit();
  }

  private apply(e: number, t: number, spm: number): void {
    const code = this.evaluator.code[e]!;
    const isActive = code === S_ACTIVE || code === S_BEHIND ? 1 : 0;
    if (isActive !== this.activeFlag[e]) {
      this.activeFlag[e] = isActive;
      this.activeVersion++;
    }
    if (code !== this.lastCode[e]) {
      this.lastCode[e] = code;
      this.fadeOf[e] = this.fadeS ?? NaN;
    }
    const id = this.ids[e]!;
    if (id < 0) return;
    const iv = this.evaluator.intervalOf(e);
    const look: Look = lookFor({
      state: code,
      from: iv ? iv.from : -Infinity,
      to: iv ? iv.to : Infinity,
      t,
      task: iv ? this.tasks.get(iv.task) : undefined,
      style: this.plan.style,
      secPerMs: spm,
      fadeS: Number.isNaN(this.fadeOf[e]!) ? undefined : this.fadeOf[e]!,
    });
    if (look.until > t) this.transient.add(e);
    else this.transient.delete(e);
    const h = look.hidden ? 1 : 0;
    if (h !== this.hid[e]) {
      this.hid[e] = h;
      this.sink.setHidden(id, look.hidden);
    }
    if (look.hidden) {
      this.sink.setAlpha(id, 1);
      this.sink.setTint(id, null, 0);
      this.sink.setGlow(id, 0);
      return;
    }
    this.sink.setAlpha(id, look.alpha);
    this.sink.setTint(id, look.tint, look.tintAmount);
    this.sink.setGlow(id, look.glow);
  }

  private updateFocus(p: number): void {
    if (!this.plan.style.xrayFocus) return;
    if (this.activeVersion === this.appliedVersion) return;
    const s = p * this.cueDur;
    const last = p >= 1;
    if (!last && this.appliedVersion >= 0 && s - this.lastFocusS < this.focusEvery && s >= this.lastFocusS) return;
    this.appliedVersion = this.activeVersion;
    this.lastFocusS = s;
    this.sink.setFocus(this.idsIn('active'));
  }

  private byModelId: Map<number, number> | null = null;

  /** The activity an element is in at the current plan time (for HUD label fields activity / percent / finish), or null. */
  taskInfo(modelId: number): { code: string; name: string; percent: number; finish: number } | null {
    if (!this.byModelId) {
      this.byModelId = new Map();
      for (let e = 0; e < this.evaluator.n; e++) if (this.ids[e]! >= 0) this.byModelId.set(this.ids[e]!, e);
    }
    const e = this.byModelId.get(modelId);
    if (e === undefined) return null;
    const iv = this.evaluator.idx[e]!;
    const list = this.plan.elements[e]!.intervals;
    const it = iv >= 0 ? list[iv] : list[0];
    const task = it ? this.tasks.get(it.task) : undefined;
    if (!task) return null;
    const span = Math.max(1, task.end - task.start);
    const pct = Math.round(Math.min(1, Math.max(0, ((Number.isFinite(this.planTime) ? this.planTime : task.start) - task.start) / span)) * 100);
    return { code: task.code, name: task.name, percent: pct, finish: task.end };
  }

  /** Model element ids by state group (the dynamic element references of the score). */
  idsIn(set: ScheduleSet): number[] {
    const out: number[] = [];
    const n = this.evaluator.n;
    for (let e = 0; e < n; e++) {
      const id = this.ids[e]!;
      if (id < 0) continue;
      const code = this.evaluator.code[e]!;
      if (set === 'active') {
        if (code === S_ACTIVE || code === S_BEHIND) out.push(id);
      } else if (set === 'completed') {
        if (code === S_COMPLETE || code === S_AHEAD) out.push(id);
      } else if (set === 'future') {
        if (code === S_FUTURE) out.push(id);
      } else if (code === S_ACTIVE || code === S_BEHIND) {
        const iv = this.evaluator.intervalOf(e);
        if (iv && this.tasks.get(iv.task)?.critical) out.push(id);
      }
    }
    return out;
  }

  /** Put everything back (the host calls it at the end of the play). */
  restore(): void {
    this.disposed = true;
    this.transient.clear();
    this.sink.reset();
  }

  /** Forget the run without touching the viewer. */
  abandon(): void {
    this.disposed = true;
    this.transient.clear();
  }
}
