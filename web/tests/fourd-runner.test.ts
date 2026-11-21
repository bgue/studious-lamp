import { describe, expect, it } from 'vitest';
import { ScorePlayer } from '../src/anim/player';
import type { CueRunner, PlayerHost } from '../src/anim/player';
import type { Cue, Score } from '../src/anim/score';
import { SCORE_SCHEMA } from '../src/anim/score';
import { collapseRunner, explodeRunner, focusRunner, sectionRunner, tintRunner } from '../src/anim/fourd/cues';
import type { Box, ExplodeTarget, FocusTarget, SectionTarget, TintTarget } from '../src/anim/fourd/cues';
import { buildDemoPlan } from '../src/anim/fourd/demoPlan';
import type { DemoModel } from '../src/anim/fourd/demoPlan';
import { Schedule4dRunner } from '../src/anim/fourd/runner';
import type { LookSink } from '../src/anim/fourd/runner';
import { resolvePlan } from '../src/anim/fourd/plans';
import { GHOST_ALPHA } from '../src/anim/fourd/look';
import type { FourDPlan } from '../src/schedule/types';

// ---------------------------------------------------------------- fakes

class FakeSink implements LookSink, TintTarget {
  hidden = new Set<number>();
  alpha = new Map<number, number>();
  tint = new Map<number, { rgb: readonly number[]; amount: number }>();
  glow = new Map<number, number>();
  focus: number[] | null = null;
  focusCalls = 0;
  commits = 0;
  resets = 0;
  setHidden(id: number, h: boolean): void {
    if (h) this.hidden.add(id);
    else this.hidden.delete(id);
  }
  setAlpha(id: number, a: number): void {
    if (a >= 0.999) this.alpha.delete(id);
    else this.alpha.set(id, a);
  }
  setTint(id: number, rgb: readonly [number, number, number] | null, amount: number): void {
    if (rgb === null || amount <= 0) this.tint.delete(id);
    else this.tint.set(id, { rgb, amount });
  }
  getTint(id: number): { rgb: readonly [number, number, number]; amount: number } | null {
    const t = this.tint.get(id);
    return t ? { rgb: t.rgb as [number, number, number], amount: t.amount } : null;
  }
  setGlow(id: number, k: 0 | 1 | 2): void {
    if (k === 0) this.glow.delete(id);
    else this.glow.set(id, k);
  }
  setFocus(ids: readonly number[]): void {
    this.focus = [...ids];
    this.focusCalls++;
  }
  commit(): void {
    this.commits++;
  }
  reset(): void {
    this.resets++;
    this.hidden.clear();
    this.alpha.clear();
    this.tint.clear();
    this.glow.clear();
    this.focus = null;
  }
}

const classes = ['IfcSlab', 'IfcWall', 'IfcColumn', 'IfcDuctSegment', 'IfcCovering', 'IfcWindow'];
const model: DemoModel = {
  name: 'T',
  storeys: [{ id: 0, name: 'L1', elevation: 0 }, { id: 1, name: 'L2', elevation: 3 }, { id: 2, name: 'L3', elevation: 6 }],
  elements: Array.from({ length: 90 }, (_, i) => ({ globalId: `e${i}`, ifcClass: classes[i % classes.length]!, storey: i % 3, bounds: [i, 0, 0, i + 1, 1, 1] })),
};
const plan = buildDemoPlan(model);
const ids = (): number[] => plan.elements.map((_, i) => i);

function runner(sink: FakeSink, p: FourDPlan = plan, extra: Partial<ConstructorParameters<typeof Schedule4dRunner>[0]> = {}): Schedule4dRunner {
  return new Schedule4dRunner({ plan: p, ids: ids(), sink, cueDur: 10, ...extra });
}

// ---------------------------------------------------------------- schedule4d

describe('schedule4d runner', () => {
  it('hides everything not yet built at the start, shows it all built at the end', () => {
    const sink = new FakeSink();
    const r = runner(sink);
    r.update(0);
    expect(sink.hidden.size).toBe(90);
    expect(sink.commits).toBe(1);
    r.update(1);
    expect(sink.hidden.size).toBe(0);
    expect(sink.tint.size).toBe(0);
    expect(sink.glow.size).toBe(0);
    expect(sink.alpha.size).toBe(0);
  });

  it('shows active elements tinted with glow, fading in; built ones plain', () => {
    const sink = new FakeSink();
    const r = runner(sink);
    for (const p of [0.1, 0.25, 0.4, 0.55, 0.7]) r.update(p);
    const active = r.idsIn('active');
    const done = r.idsIn('completed');
    expect(active.length).toBeGreaterThan(0);
    for (const id of active) {
      expect(sink.hidden.has(id)).toBe(false);
      expect(sink.tint.has(id)).toBe(true);
      expect(sink.glow.has(id)).toBe(true);
    }
    for (const id of done) {
      expect(sink.hidden.has(id)).toBe(false);
      expect(sink.tint.has(id)).toBe(false);
      expect(sink.glow.has(id)).toBe(false);
    }
    // every element is exactly one of hidden / active / completed
    expect(sink.hidden.size + active.length + done.length).toBe(90);
  });

  it('gives critical active elements the red glow (2) and the others 1', () => {
    const sink = new FakeSink();
    const r = runner(sink);
    let sawCritical = false;
    let sawNormal = false;
    for (let p = 0; p <= 1; p += 0.01) {
      r.update(p);
      const crit = new Set(r.idsIn('critical'));
      for (const [id, k] of sink.glow) {
        if (crit.has(id)) {
          expect(k).toBe(2);
          sawCritical = true;
        } else {
          expect(k).toBe(1);
          sawNormal = true;
        }
      }
    }
    expect(sawCritical && sawNormal).toBe(true);
  });

  it('a ghost view fades unbuilt elements to a faint alpha instead of hiding them', () => {
    const sink = new FakeSink();
    const ghost = { ...plan, style: { ...plan.style, unbuilt: 'ghost' as const } };
    runner(sink, ghost).update(0);
    expect(sink.hidden.size).toBe(0);
    expect(sink.alpha.size).toBe(90);
    expect([...sink.alpha.values()].every((a) => a === GHOST_ALPHA)).toBe(true);
  });

  it('seeking gives the picture of a fresh run at that time', () => {
    const a = new FakeSink();
    const ra = runner(a);
    for (const p of [0.2, 0.6, 0.9, 0.35, 0.05, 0.5]) ra.update(p);
    const b = new FakeSink();
    runner(b).update(0.5);
    expect([...a.hidden].sort()).toEqual([...b.hidden].sort());
    expect([...a.tint.keys()].sort()).toEqual([...b.tint.keys()].sort());
    expect([...a.glow.entries()].sort()).toEqual([...b.glow.entries()].sort());
    for (const [id, v] of b.alpha) expect(a.alpha.get(id)).toBeCloseTo(v, 9);
  });

  it('only touches elements that change (a quiet frame makes no per-element calls)', () => {
    const calls = { n: 0 };
    class Counting extends FakeSink {
      override setHidden(id: number, h: boolean): void {
        calls.n++;
        super.setHidden(id, h);
      }
      override setAlpha(id: number, a: number): void {
        calls.n++;
        super.setAlpha(id, a);
      }
    }
    const sink = new Counting();
    const r = runner(sink);
    r.update(0.5);
    const first = calls.n;
    expect(first).toBeGreaterThan(90);
    // the same time again: only the elements that are still fading in are looked at again
    calls.n = 0;
    r.update(0.5);
    expect(calls.n).toBeGreaterThan(0);
    expect(calls.n).toBeLessThan(first / 3);
    // the finished picture is static: nothing to do
    r.update(1);
    calls.n = 0;
    r.update(1);
    expect(calls.n).toBe(0);
  });

  it('with xrayFocus, the active elements become the focus when the set changes, at most every 0.25 s of video', () => {
    const sink = new FakeSink();
    const r = runner(sink);
    r.update(0);
    expect(sink.focus).toEqual([]); // nothing active yet: the focus is empty
    let last = -1;
    for (let p = 0.3; p <= 0.31; p += 0.0005) r.update(p);
    expect(sink.focus).not.toBeNull();
    expect(sink.focus!.length).toBe(r.idsIn('active').length);
    last = sink.focusCalls;
    r.update(0.3105);
    expect(sink.focusCalls).toBe(last); // the same set (or inside the pause): unchanged
    const off = new FakeSink();
    const r2 = runner(off, { ...plan, style: { ...plan.style, xrayFocus: false } });
    for (let p = 0; p <= 1; p += 0.05) r2.update(p);
    expect(off.focusCalls).toBe(0);
  });

  it('the dynamic element groups follow the state (active, completed, critical, future)', () => {
    const sink = new FakeSink();
    const r = runner(sink);
    r.update(0);
    expect(r.idsIn('active')).toEqual([]);
    expect(r.idsIn('future').length).toBe(90);
    r.update(0.5);
    const total = r.idsIn('active').length + r.idsIn('completed').length + r.idsIn('future').length;
    expect(total).toBe(90);
    expect(r.idsIn('critical').every((id) => r.idsIn('active').includes(id))).toBe(true);
    r.update(1);
    expect(r.idsIn('completed').length).toBe(90);
    expect(r.idsIn('active')).toEqual([]);
  });

  it('skips plan elements the model does not have (id -1) but still counts their state', () => {
    const sink = new FakeSink();
    const some = ids().map((i) => (i % 2 ? -1 : i));
    const r = new Schedule4dRunner({ plan, ids: some, sink, cueDur: 10 });
    r.update(0);
    expect(sink.hidden.size).toBe(45);
    expect(r.idsIn('future').length).toBe(45);
  });

  it('restore puts everything back and stops further updates', () => {
    const sink = new FakeSink();
    const r = runner(sink);
    r.update(0.5);
    r.restore();
    expect(sink.resets).toBe(1);
    expect(sink.hidden.size).toBe(0);
    const c = sink.commits;
    r.update(0.6);
    expect(sink.commits).toBe(c);
  });
});

// ---------------------------------------------------------------- a fake host for the whole path: player, cues, dynamic refs

class FakeHost implements PlayerHost {
  readonly sink = new FakeSink();
  schedule: Schedule4dRunner | null = null;
  focus = new FakeFocus();
  tintLog: string[] = [];
  begun = 0;
  restored = 0;
  resolve = (ref: import('../src/anim/score').ElementRef): number[] => {
    if ('schedule' in ref) return this.schedule?.idsIn(ref.schedule) ?? [];
    if ('globalIds' in ref) return ref.globalIds.map((g) => Number(g.slice(1)));
    return [];
  };
  begin(): void {
    this.begun++;
    this.schedule = null;
  }
  start(cue: Cue, index: number): CueRunner | null {
    const env = { resolve: (ref: import('../src/anim/score').ElementRef) => this.resolve(ref) };
    switch (cue.kind) {
      case 'schedule4d': {
        const p = resolvePlan(cue.plan)!;
        this.schedule = new Schedule4dRunner({ plan: p, ids: ids(), sink: this.sink, cueDur: cue.dur });
        return this.schedule;
      }
      case 'tint':
        return tintRunner(cue, index, env, this.sink);
      case 'focus':
        return focusRunner(cue, index, env, this.focus);
      default:
        return null;
    }
  }
  finish(): void {}
  restore(): void {
    this.restored++;
    this.schedule?.restore();
    this.schedule = null;
  }
}
class FakeFocus implements FocusTarget {
  last: readonly number[] | null | undefined = undefined;
  set(ids: readonly number[] | null): void {
    this.last = ids;
  }
}

const score = (cues: Cue[], duration = 10): Score => ({ schema: SCORE_SCHEMA, duration, cues });

describe('the score path with a fake host', () => {
  it('plays a schedule4d cue through the player and restores at the end', () => {
    const host = new FakeHost();
    const pl = new ScorePlayer(host);
    pl.play(score([{ at: 0, dur: 10, kind: 'schedule4d', plan }]));
    expect(host.sink.hidden.size).toBe(90);
    pl.advance(5);
    const mid = host.sink.hidden.size;
    expect(mid).toBeGreaterThan(0);
    expect(mid).toBeLessThan(90);
    pl.advance(5.1);
    expect(host.restored).toBe(1);
    expect(host.sink.resets).toBe(1);
  });

  it('seek replays to the same picture', () => {
    const host = new FakeHost();
    const pl = new ScorePlayer(host);
    pl.play(score([{ at: 0, dur: 10, kind: 'schedule4d', plan }]));
    pl.advance(7);
    const hidden = [...host.sink.hidden].sort();
    pl.advance(2);
    pl.seek(7);
    expect([...host.sink.hidden].sort()).toEqual(hidden);
  });

  it('resolves { schedule } references when the cue runs: active elements from the running schedule, empty without one', () => {
    const host = new FakeHost();
    const pl = new ScorePlayer(host);
    // the focus cue starts at 4 s, while the schedule runs; a second focus at 0 s runs before any schedule state exists
    pl.play(score([
      { at: 0, dur: 10, kind: 'schedule4d', plan },
      { at: 4, dur: 0, kind: 'focus', elements: { schedule: 'active' } },
      { at: 4, dur: 1, kind: 'tint', elements: { schedule: 'completed' }, colour: '#ff0000' },
    ]));
    pl.advance(4);
    expect(host.focus.last).not.toBeNull();
    expect((host.focus.last as number[]).length).toBe(host.schedule!.idsIn('active').length);
    expect((host.focus.last as number[]).length).toBeGreaterThan(0);
    pl.advance(1);
    const done = host.schedule!.idsIn('completed');
    expect(done.length).toBeGreaterThan(0);

    const none = new FakeHost();
    const p2 = new ScorePlayer(none);
    p2.play(score([{ at: 0, dur: 0, kind: 'focus', elements: { schedule: 'active' } }]));
    expect(none.focus.last).toEqual([]);
  });
});

// ---------------------------------------------------------------- tint, explode, collapse, focus, sectionBox

describe('tint cue', () => {
  const env = { resolve: (): number[] => [1, 2, 3] };
  it('fades the colour in over the cue and keeps it', () => {
    const t = new FakeSink();
    const r = tintRunner({ at: 0, dur: 2, kind: 'tint', elements: { all: true }, colour: '#ff0000' }, 0, env, t);
    r.update(0);
    expect(t.tint.has(1)).toBe(false); // amount 0
    r.update(0.5);
    expect(t.tint.get(1)!.amount).toBeCloseTo(0.4, 6);
    expect(t.tint.get(1)!.rgb).toEqual([1, 0, 0]);
    r.update(1);
    expect(t.tint.get(3)!.amount).toBeCloseTo(0.8, 6);
    expect(t.commits).toBe(3);
  });
  it('null fades the tint out from what the elements show and removes it', () => {
    const t = new FakeSink();
    t.setTint(1, [0, 1, 0], 0.8);
    const r = tintRunner({ at: 0, dur: 2, kind: 'tint', elements: { all: true }, colour: null }, 0, env, t);
    r.update(0.5);
    expect(t.tint.get(1)!.amount).toBeCloseTo(0.4, 6);
    expect(t.tint.has(2)).toBe(false); // had none
    r.update(1);
    expect(t.tint.has(1)).toBe(false);
  });
  it('honours the ease', () => {
    const t = new FakeSink();
    const r = tintRunner({ at: 0, dur: 1, kind: 'tint', elements: { all: true }, colour: '#00ff00', ease: 'in' }, 0, env, t);
    r.update(0.5);
    expect(t.tint.get(1)!.amount).toBeCloseTo(0.8 * 0.125, 6);
  });
});

class FakeExplode implements ExplodeTarget {
  k = 0;
  began: Array<[string, number]> = [];
  cleared = 0;
  value(): number {
    return this.k;
  }
  begin(mode: 'storeys' | 'radial', factor: number): void {
    this.began.push([mode, factor]);
  }
  set(k: number): void {
    this.k = k;
  }
  clear(): void {
    this.k = 0;
    this.cleared++;
  }
}

describe('explode and collapse cues', () => {
  it('explode: begins with the mode and factor (default 1), eases the progress to 1', () => {
    const t = new FakeExplode();
    const r = explodeRunner({ at: 0, dur: 2, kind: 'explode', mode: 'storeys' }, t);
    expect(t.began).toEqual([['storeys', 1]]);
    r.update(0.5);
    expect(t.k).toBeCloseTo(0.5, 6);
    r.update(1);
    expect(t.k).toBe(1);
    const t2 = new FakeExplode();
    explodeRunner({ at: 0, dur: 2, kind: 'explode', mode: 'radial', factor: 1.5, ease: 'inOut' }, t2).update(0.25);
    expect(t2.began).toEqual([['radial', 1.5]]);
    expect(t2.k).toBeCloseTo(0.0625, 6);
  });
  it('a second explode continues from where the building is', () => {
    const t = new FakeExplode();
    t.k = 0.5;
    const r = explodeRunner({ at: 0, dur: 1, kind: 'explode', mode: 'storeys' }, t);
    r.update(0);
    expect(t.k).toBeCloseTo(0.5, 6);
    r.update(0.5);
    expect(t.k).toBeCloseTo(0.75, 6);
  });
  it('collapse: eases back to 0 and clears at the end', () => {
    const t = new FakeExplode();
    t.k = 1;
    const r = collapseRunner({ at: 0, dur: 2, kind: 'collapse' }, t);
    r.update(0.25);
    expect(t.k).toBeCloseTo(0.75, 6);
    expect(t.cleared).toBe(0);
    r.update(1);
    expect(t.cleared).toBe(1);
    expect(t.k).toBe(0);
  });
});

describe('focus cue', () => {
  it('sets the focus to the elements once, null gives it back', () => {
    const f = new FakeFocus();
    const env = { resolve: (): number[] => [4, 5] };
    const r = focusRunner({ at: 0, dur: 0, kind: 'focus', elements: { all: true } }, 0, env, f);
    r.update(1);
    expect(f.last).toEqual([4, 5]);
    const g = new FakeFocus();
    focusRunner({ at: 0, dur: 0, kind: 'focus', elements: null }, 0, env, g).update(1);
    expect(g.last).toBeNull();
  });
});

class FakeSection implements SectionTarget {
  box: Box | null = null;
  modelBox: Box | null = { min: [0, 0, 0], max: [10, 10, 10] };
  sets: Array<Box | null> = [];
  current(): Box | null {
    return this.box;
  }
  model(): Box | null {
    return this.modelBox;
  }
  around(ids: readonly number[]): Box | null {
    return ids.length ? { min: [2, 2, 2], max: [4, 4, 4] } : null;
  }
  aroundStorey(name: string): Box | null {
    return name === 'L2' ? { min: [0, 3, 0], max: [10, 6, 10] } : null;
  }
  set(b: Box | null): void {
    this.sets.push(b);
    this.box = b;
  }
  margin(): number {
    return 0.5;
  }
}

describe('sectionBox cue', () => {
  const env = { resolve: (): number[] => [1] };
  it('closes in from the whole model to the box around the elements (with the margin), eased', () => {
    const s = new FakeSection();
    const r = sectionRunner({ at: 0, dur: 2, kind: 'sectionBox', around: { all: true }, margin: 1 }, 0, env, s)!;
    r.update(0);
    expect(s.box).toEqual({ min: [-1, -1, -1], max: [11, 11, 11] }); // the model plus the margin
    r.update(0.5);
    expect(s.box!.min[0]).toBeCloseTo(0, 6); // half way between -1 and 1
    r.update(1);
    expect(s.box).toEqual({ min: [1, 1, 1], max: [5, 5, 5] });
  });
  it('around a storey by name, with the margin of the section tool by default', () => {
    const s = new FakeSection();
    const r = sectionRunner({ at: 0, dur: 1, kind: 'sectionBox', around: { storey: 'L2' } }, 0, env, s)!;
    r.update(1);
    expect(s.box).toEqual({ min: [-0.5, 2.5, -0.5], max: [10.5, 6.5, 10.5] });
  });
  it('starts from the box that is on now', () => {
    const s = new FakeSection();
    s.box = { min: [0, 0, 0], max: [2, 2, 2] };
    const r = sectionRunner({ at: 0, dur: 1, kind: 'sectionBox', around: { all: true }, margin: 0 }, 0, env, s)!;
    r.update(0);
    expect(s.box).toEqual({ min: [0, 0, 0], max: [2, 2, 2] });
  });
  it('null opens out to the model and then switches the box off', () => {
    const s = new FakeSection();
    s.box = { min: [4, 4, 4], max: [6, 6, 6] };
    const r = sectionRunner({ at: 0, dur: 1, kind: 'sectionBox', around: null }, 0, env, s)!;
    r.update(0.5);
    expect(s.box).not.toBeNull();
    r.update(1);
    expect(s.box).toBeNull();
  });
  it('does nothing for a storey or elements that do not exist', () => {
    const s = new FakeSection();
    expect(sectionRunner({ at: 0, dur: 1, kind: 'sectionBox', around: { storey: 'Nope' } }, 0, env, s)).toBeNull();
    expect(s.sets).toEqual([]);
  });
  it('off with nothing on is a no-op that still ends off', () => {
    const s = new FakeSection();
    s.modelBox = null;
    expect(sectionRunner({ at: 0, dur: 1, kind: 'sectionBox', around: null }, 0, env, s)).toBeNull();
    expect(s.box).toBeNull();
  });
});

describe('cost of the state update', () => {
  it('a frame of a 50 000 element plan costs a few milliseconds, not O(elements) per frame', () => {
    const n = 50000;
    const classes2 = ['IfcSlab', 'IfcWall', 'IfcColumn', 'IfcDuctSegment', 'IfcCovering', 'IfcWindow'];
    const big: DemoModel = {
      storeys: Array.from({ length: 10 }, (_, i) => ({ id: i, name: `L${i}`, elevation: i * 3 })),
      elements: Array.from({ length: n }, (_, i) => ({ globalId: `g${i}`, ifcClass: classes2[i % 6]!, storey: i % 10, bounds: [i % 977, 0, 0, (i % 977) + 1, 1, 1] })),
    };
    const p = buildDemoPlan(big);
    const sink = new FakeSink();
    const r = new Schedule4dRunner({ plan: p, ids: p.elements.map((_, i) => i), sink, cueDur: 120 });
    r.update(0); // the first frame builds the whole picture
    const frames = 240;
    const t0 = performance.now();
    for (let f = 1; f <= frames; f++) r.update(f / frames);
    const per = (performance.now() - t0) / frames;
    console.log(`4D state update, ${n} elements: ${per.toFixed(3)} ms per frame (${frames} frames over the whole plan)`);
    expect(per).toBeLessThan(25);
  });
});
