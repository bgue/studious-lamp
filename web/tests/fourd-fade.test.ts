// How long a newly built element takes to fade in (and a removed one to fade out): the default rule, style.fadeIn, the cue's fadeIn and a fadeDefault cue.
import { describe, expect, it } from 'vitest';
import { FADE_VIDEO_S, fadeMs, lookFor } from '../src/anim/fourd/look';
import { Schedule4dRunner } from '../src/anim/fourd/runner';
import type { LookSink } from '../src/anim/fourd/runner';
import { DEFAULT_STYLE } from '../src/schedule/types';
import type { FourDPlan } from '../src/schedule/types';
import { BASE, DAY } from './director-helpers';

/** Film of 40 s, 1 s = 1 day. Element 0: built from second 10 to 30 (active), complete after. Element 1: demolished from second 20 to 30. */
function plan(style: Partial<FourDPlan['style']> = {}): FourDPlan {
  const ms = (s: number): number => BASE + s * DAY;
  return {
    schema: 'xray-4d-plan/1',
    model: { identityKey: 'f', name: 'f.ifc' },
    schedule: { project: 'F', sourceHash: 'x' },
    style: { ...DEFAULT_STYLE, length: 40, ...style },
    window: { from: ms(0), to: ms(40) },
    elements: [
      { globalId: 'a', intervals: [{ from: ms(10), to: ms(30), state: 'active', task: 'T1' }, { from: ms(30), to: ms(40), state: 'complete', task: 'T1' }] },
      { globalId: 'b', intervals: [{ from: ms(0), to: ms(20), state: 'existing', task: 'T2' }, { from: ms(20), to: ms(30), state: 'removed', task: 'T2' }] },
    ],
    tasks: [
      { code: 'T1', name: 'Build', start: ms(10), end: ms(30), critical: false, milestone: false, elements: 1 },
      { code: 'T2', name: 'Demolish', start: ms(20), end: ms(30), critical: false, milestone: false, elements: 1 },
    ],
    milestones: [],
    timeMap: [[ms(0), 0], [ms(40), 40]],
    progress: [],
  };
}

class Sink implements LookSink {
  alpha = new Map<number, number>();
  hidden = new Set<number>();
  setHidden(id: number, h: boolean): void {
    if (h) this.hidden.add(id);
    else this.hidden.delete(id);
  }
  setAlpha(id: number, a: number): void {
    this.alpha.set(id, a);
  }
  setTint(): void {}
  setGlow(): void {}
  setFocus(): void {}
  commit(): void {}
  reset(): void {}
}

/** A runner over the plan; `at` seconds of film later the alpha of element `e` (1 when none was set). */
function run(p: FourDPlan, opts: { fadeIn?: number } = {}) {
  const sink = new Sink();
  const r = new Schedule4dRunner({ plan: p, ids: [0, 1], sink, cueDur: 40, ...opts });
  const at = (s: number): void => r.update(s / 40);
  return { sink, r, at };
}

describe('fadeMs', () => {
  it('default: 10 % of the interval, at most 0.6 s of film', () => {
    const spm = 1 / DAY; // 1 s per day
    expect(fadeMs(0, 20 * DAY, spm)).toBeCloseTo(0.6 * DAY, 3); // 10 % would be 2 s: capped
    expect(fadeMs(0, 2 * DAY, spm)).toBeCloseTo(0.2 * DAY, 3); // 10 % of 2 days
  });
  it('explicit seconds of film, never longer than the interval, 0 = at once', () => {
    const spm = 1 / DAY;
    expect(fadeMs(0, 20 * DAY, spm, 3)).toBeCloseTo(3 * DAY, 3);
    expect(fadeMs(0, 2 * DAY, spm, 3)).toBeCloseTo(2 * DAY, 3);
    expect(fadeMs(0, 20 * DAY, spm, 0)).toBe(1);
    expect(FADE_VIDEO_S).toBe(0.6);
  });
});

describe('lookFor with fadeS', () => {
  const base = { state: 'active' as const, from: 0, to: 20 * DAY, t: 1 * DAY, secPerMs: 1 / DAY, style: { unbuilt: 'hidden' as const, colours: {} } };
  it('a build fades over the given seconds', () => {
    expect(lookFor({ ...base, fadeS: 4 }).alpha).toBeCloseTo(0.25, 3);
    expect(lookFor({ ...base }).alpha).toBe(1); // default 0.6 s: already in after 1 s
  });
  it('0 shows the part at once, and a removal hides at once', () => {
    expect(lookFor({ ...base, t: 0, fadeS: 0 }).alpha).toBe(1);
    expect(lookFor({ ...base, state: 'removed', t: 0, fadeS: 0 }).hidden).toBe(true);
  });
});

describe('the runner', () => {
  it('default rule: in within 0.6 s', () => {
    const { sink, at } = run(plan());
    at(10.3);
    expect(sink.alpha.get(0)!).toBeCloseTo(0.5, 1);
    at(10.7);
    expect(sink.alpha.get(0)).toBe(1);
  });

  it('style.fadeIn sets the time of a build and of a removal', () => {
    const { sink, at } = run(plan({ fadeIn: 4 }));
    at(11);
    expect(sink.alpha.get(0)!).toBeCloseTo(0.25, 1);
    at(13);
    expect(sink.alpha.get(0)!).toBeCloseTo(0.75, 1);
    at(14.5);
    expect(sink.alpha.get(0)).toBe(1);
    // element 1 goes after 4 s too: 22 s is half way
    at(22);
    expect(sink.alpha.get(1)!).toBeCloseTo(0.5, 1);
    expect(sink.hidden.has(1)).toBe(false);
    at(24.5);
    expect(sink.hidden.has(1)).toBe(true);
  });

  it('fadeIn 0: at once', () => {
    const { sink, at } = run(plan({ fadeIn: 0 }));
    at(10.05);
    expect(sink.alpha.get(0)).toBe(1);
    expect(sink.hidden.has(0)).toBe(false);
    at(20.05);
    expect(sink.hidden.has(1)).toBe(true);
  });

  it('the cue option wins over the style', () => {
    const { sink, at } = run(plan({ fadeIn: 4 }), { fadeIn: 2 });
    at(11);
    expect(sink.alpha.get(0)!).toBeCloseTo(0.5, 1);
  });

  it('a fadeDefault cue changes what starts after it and leaves what is fading', () => {
    const { sink, r, at } = run(plan({ fadeIn: 2 }));
    at(5);
    r.setFadeSeconds(8); // before element 0 starts at 10 and element 1 at 20
    at(12);
    expect(sink.alpha.get(0)!).toBeCloseTo(0.25, 1);
    r.setFadeSeconds(0.5); // element 0 keeps its 8 s; element 1 (removal at 20) takes 0.5 s
    at(14);
    expect(sink.alpha.get(0)!).toBeCloseTo(0.5, 1);
    at(20.25);
    expect(sink.alpha.get(1)!).toBeCloseTo(0.5, 1);
    at(20.6);
    expect(sink.hidden.has(1)).toBe(true);
  });
});
