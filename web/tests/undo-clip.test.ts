// Clip planes on the undo stack: the state machine that settles plane changes, joining a camera move and a plane change into one
// entry, putting a state back through the section tool or the renderer, and one undo / redo round on the real stack.
import { describe, expect, it } from 'vitest';
import { UndoStack } from '../src/undo/stack';
import type { UndoEntry } from '../src/undo/stack';
import { defaultSection } from '../src/section/config';
import type { SectionConfig } from '../src/section/config';
import { ClipWatch, applyClip, clipSame, composeStep, describeClipChange, planesSame, readClipState } from '../src/undo/clipWatch';
import type { ClipState, ClipTarget, PlaneState } from '../src/undo/clipWatch';

const P = (y: number): PlaneState => ({ normal: [0, -1, 0], point: [0, y, 0] });
const state = (planes: PlaneState[] | null, cfg: SectionConfig | null = null, foreign = false): ClipState => ({ planes, cfg, foreign });

describe('comparing clip states', () => {
  it('planes are the same when the point only moves along the plane', () => {
    expect(planesSame([P(2)], [{ normal: [0, -1, 0], point: [5, 2, 9] }])).toBe(true);
    expect(planesSame([P(2)], [P(2.5)])).toBe(false);
    expect(planesSame(null, [])).toBe(true);
    expect(planesSame([P(1)], null)).toBe(false);
  });

  it('copies what it reads, and ignores an empty list', () => {
    const live = [{ normal: [0, 1, 0], point: [0, 3, 0] }];
    const s = readClipState(live, defaultSection());
    live[0]!.point[1] = 99;
    expect(s.planes![0]!.point[1]).toBe(3);
    expect(readClipState([], null).planes).toBeNull();
    expect(readClipState(live, null, true).foreign).toBe(true);
    expect(readClipState(null, null, true).foreign).toBe(false);
  });

  it('names a change', () => {
    expect(describeClipChange(state(null), state([P(1)]))).toBe('section on');
    expect(describeClipChange(state([P(1)]), state(null))).toBe('section off');
    expect(describeClipChange(state([P(1)]), state([P(2)]))).toBe('section move');
  });
});

describe('the clip watch', () => {
  const read = (s: ClipState) => () => s;

  it('does nothing while the planes do not change, and a change comes out once', () => {
    const w = new ClipWatch();
    const a = state(null);
    w.baseline(a, 1);
    w.observe(read(a), 1, 100);
    expect(w.changing).toBe(false);
    const b = state([P(2)]);
    w.observe(read(b), 2, 200);
    expect(w.changing).toBe(true);
    expect(w.lastChangeAt).toBe(200);
    const ch = w.settle(read(b))!;
    expect(ch.before).toBe(a);
    expect(ch.after).toBe(b);
    expect(w.changing).toBe(false);
    expect(w.settle(read(b))).toBeNull();
  });

  it('a drag is one change: before is the state at its start, and each frame extends it', () => {
    const w = new ClipWatch();
    const a = state([P(1)]);
    w.baseline(a, 1);
    let v = 1;
    for (let t = 100; t < 600; t += 16) w.observe(read(state([P(1 + (t - 100) / 100)])), ++v, t);
    expect(w.since).toBe(100);
    expect(w.lastChangeAt).toBeGreaterThan(500);
    const end = state([P(6)]);
    const ch = w.settle(read(end))!;
    expect(ch.before).toBe(a);
    expect(ch.after).toBe(end);
  });

  it('a change that comes back to where it started is no change', () => {
    const w = new ClipWatch();
    const a = state([P(1)]);
    w.baseline(a, 1);
    w.observe(read(state([P(3)])), 2, 100);
    expect(w.settle(read(state([P(1)])))).toBeNull();
  });

  it('keeps the committed state fresh while idle, so the settings in "before" are those from just before the change', () => {
    const w = new ClipWatch();
    const cfg = defaultSection();
    w.baseline(state(null, cfg), 1);
    const later = defaultSection();
    later.caps = false;
    w.observe(read(state(null, later)), 1, 1000);
    w.observe(read(state([P(1)], later)), 2, 1010);
    expect(w.settle(read(state([P(1)], later)))!.before.cfg!.caps).toBe(false);
  });

  it('a version bump with the same planes (a push of the same section) is no change', () => {
    const w = new ClipWatch();
    const a = state([P(1)]);
    w.baseline(a, 1);
    w.observe(read(state([P(1)])), 2, 100);
    expect(w.settle(read(state([P(1)])))).toBeNull();
  });
});

describe('one step', () => {
  const cam = { before: 'A', after: 'B', label: 'orbit' };
  const clip = { before: state(null), after: state([P(2)]) };

  it('camera and planes together are one entry; either alone is its own', () => {
    expect(composeStep(cam, clip)).toMatchObject({ kind: 'view', label: 'orbit and section', clip });
    expect(composeStep(cam, null)).toMatchObject({ kind: 'view', label: 'orbit' });
    expect(composeStep(null, clip)).toMatchObject({ kind: 'section', label: 'section on' });
    expect(composeStep(null, null)).toBeNull();
  });

  it('undo and redo of the joined entry bring back camera and planes in one step', () => {
    interface E extends UndoEntry { kind: string; before: string; after: string; clip?: typeof clip }
    const stack = new UndoStack<E>();
    const live = { cam: 'A', planes: null as PlaneState[] | null };
    const step = composeStep(cam, clip)!;
    live.cam = 'B';
    live.planes = clip.after.planes;
    stack.push({ ...(step as E), at: 1 });
    const apply = (e: E, dir: 'before' | 'after'): void => {
      live.cam = e[dir];
      if (e.clip) live.planes = e.clip[dir].planes;
    };
    stack.undo((e) => apply(e, 'before'));
    expect(live).toEqual({ cam: 'A', planes: null });
    expect(stack.canUndo).toBe(false);
    stack.redo((e) => apply(e, 'after'));
    expect(live.cam).toBe('B');
    expect(live.planes).toEqual([P(2)]);
  });
});

describe('putting a state back', () => {
  function target(over: Partial<ClipTarget> = {}) {
    const calls: string[] = [];
    const t: ClipTarget = {
      setConfig: (cfg) => { calls.push(`config:${cfg.box.enabled ? 'box' : cfg.plane.enabled ? 'plane' : 'off'}`); },
      wantsPlanes: (cfg) => cfg.box.enabled || cfg.plane.enabled,
      setPlanes: (planes, cap) => { calls.push(`planes:${planes ? planes.length : 'none'}:${cap}`); },
      ...over,
    };
    return { t, calls };
  }
  const boxOn = (): SectionConfig => { const c = defaultSection(); c.box.enabled = true; return c; };

  it('planes the section tool makes go back to the tool, which pushes them itself', () => {
    const { t, calls } = target();
    applyClip(t, state([P(1)], boxOn()));
    expect(calls).toEqual(['config:box']);
  });

  it('planes of a viewpoint or a switch go on the renderer as they were, and the tool is left alone', () => {
    const { t, calls } = target();
    applyClip(t, state([P(1)], boxOn(), true));
    expect(calls).toEqual(['planes:1:true']);
  });

  it('no planes with the tool off: its settings come back, then the renderer is cleared', () => {
    const { t, calls } = target();
    applyClip(t, state(null, defaultSection()));
    expect(calls).toEqual(['config:off', 'planes:none:true']);
  });

  it('works without a section tool', () => {
    const { t, calls } = target({ setConfig: undefined as never });
    applyClip(t, state([P(1)], null));
    expect(calls).toEqual(['planes:1:true']);
  });

  it('states differ in their settings or their owner, not only in their planes', () => {
    expect(clipSame(state([P(1)], defaultSection()), state([P(1)], boxOn()))).toBe(false);
    expect(clipSame(state([P(1)], null, true), state([P(1)], null, false))).toBe(false);
    expect(clipSame(state([P(1)], defaultSection()), state([P(1)], defaultSection()))).toBe(true);
  });
});
