import { describe, expect, it } from 'vitest';
import { UndoStack } from '../src/undo/stack';
import type { UndoEntry } from '../src/undo/stack';
import { describeViewChange, easeInOut, mixViewPose, viewPoseEqual } from '../src/undo/viewPose';
import type { ViewPose } from '../src/undo/viewPose';

interface E extends UndoEntry {
  before?: number;
  after?: number;
}
const e = (label: string, at: number, extra: Partial<E> = {}): E => ({ label, at, ...extra });
const merge = (a: E, b: E): E | null => (a.before === b.after ? null : { ...a, at: b.at, after: b.after });

describe('UndoStack', () => {
  it('undoes and redoes in order and names the next step', () => {
    const s = new UndoStack<E>();
    s.push(e('zoom', 0));
    s.push(e('selection', 1));
    expect(s.canUndo).toBe(true);
    expect(s.undoLabel).toBe('selection');
    expect(s.canRedo).toBe(false);
    const seen: string[] = [];
    s.undo((x) => seen.push(`undo ${x.label}`));
    expect(s.undoLabel).toBe('zoom');
    expect(s.redoLabel).toBe('selection');
    s.undo((x) => seen.push(`undo ${x.label}`));
    expect(s.canUndo).toBe(false);
    expect(s.undo(() => seen.push('never'))).toBeNull();
    s.redo((x) => seen.push(`redo ${x.label}`));
    s.redo((x) => seen.push(`redo ${x.label}`));
    expect(seen).toEqual(['undo selection', 'undo zoom', 'redo zoom', 'redo selection']);
    expect(s.redo(() => seen.push('never'))).toBeNull();
  });

  it('clears the redo list on a new action', () => {
    const s = new UndoStack<E>();
    s.push(e('a', 0));
    s.push(e('b', 1));
    s.undo(() => {});
    expect(s.canRedo).toBe(true);
    s.push(e('c', 2));
    expect(s.canRedo).toBe(false);
    expect(s.list().undo.map((x) => x.label)).toEqual(['a', 'c']);
  });

  it('caps the stack and drops the oldest entries', () => {
    const s = new UndoStack<E>({ cap: 5 });
    for (let i = 0; i < 12; i++) s.push(e(`n${i}`, i));
    expect(s.size).toBe(5);
    expect(s.list().undo.map((x) => x.label)).toEqual(['n7', 'n8', 'n9', 'n10', 'n11']);
    expect(new UndoStack<E>().cap).toBe(100);
  });

  it('merges entries with the same key inside the window (a slider drag)', () => {
    const s = new UndoStack<E>({ coalesceMs: 500, merge });
    s.push(e('opacity', 0, { key: 'k', before: 1, after: 0.9 }));
    s.push(e('opacity', 200, { key: 'k', before: 0.9, after: 0.7 }));
    s.push(e('opacity', 600, { key: 'k', before: 0.7, after: 0.4 })); // 400 ms after the previous change: still one drag
    expect(s.size).toBe(1);
    const only = s.list().undo[0]!;
    expect([only.before, only.after]).toEqual([1, 0.4]);
  });

  it('keeps entries apart when the key differs or the pause is long', () => {
    const s = new UndoStack<E>({ coalesceMs: 500, merge });
    s.push(e('a', 0, { key: 'a', before: 1, after: 2 }));
    s.push(e('b', 100, { key: 'b', before: 1, after: 2 }));
    s.push(e('b', 900, { key: 'b', before: 2, after: 3 }));
    expect(s.size).toBe(3);
  });

  it('drops a merged entry that came back to where it started', () => {
    const s = new UndoStack<E>({ coalesceMs: 500, merge });
    s.push(e('x', 0, { key: 'k', before: 1, after: 2 }));
    s.push(e('x', 100, { key: 'k', before: 2, after: 1 }));
    expect(s.size).toBe(0);
    expect(s.canUndo).toBe(false);
  });

  it('a merge clears the redo list too', () => {
    const s = new UndoStack<E>({ coalesceMs: 500, merge });
    s.push(e('a', 0));
    s.push(e('x', 10, { key: 'k', before: 1, after: 2 }));
    s.undo(() => {});
    expect(s.canRedo).toBe(true);
    s.push(e('x', 20, { key: 'k', before: 1, after: 3 }));
    expect(s.canRedo).toBe(false);
  });

  it('ignores changes that the undo and the redo apply themselves', () => {
    const s = new UndoStack<E>();
    s.push(e('a', 0));
    let pushedDuringUndo = true;
    s.undo(() => {
      pushedDuringUndo = s.push(e('echo', 5));
      expect(s.isApplying).toBe(true);
    });
    expect(pushedDuringUndo).toBe(false);
    expect(s.isApplying).toBe(false);
    expect(s.size).toBe(0);
    expect(s.redoLabel).toBe('a'); // the echo did not clear the redo list
    s.redo(() => {
      s.push(e('echo2', 6));
    });
    expect(s.list().undo.map((x) => x.label)).toEqual(['a']);
  });

  it('stays usable after an apply that throws', () => {
    const s = new UndoStack<E>();
    s.push(e('a', 0));
    expect(() => s.undo(() => { throw new Error('boom'); })).toThrow('boom');
    expect(s.isApplying).toBe(false);
    expect(s.push(e('b', 1))).toBe(true);
  });

  it('ignores pushes while muted (a model loads, a link applies)', () => {
    const s = new UndoStack<E>();
    expect(s.mute(() => s.push(e('load', 0)))).toBe(false);
    expect(s.size).toBe(0);
    expect(s.push(e('after', 1))).toBe(true);
    s.setMuted(true);
    expect(s.push(e('muted', 2))).toBe(false);
    s.setMuted(false);
    expect(s.push(e('free', 3))).toBe(true);
  });

  it('clears everything and tells the listeners', () => {
    const s = new UndoStack<E>();
    let calls = 0;
    const off = s.onChange(() => calls++);
    s.push(e('a', 0));
    s.undo(() => {});
    s.clear();
    expect(s.canUndo || s.canRedo).toBe(false);
    expect(calls).toBe(3);
    off();
    s.push(e('b', 1));
    expect(calls).toBe(3);
  });
});

const pose = (p: Partial<ViewPose> = {}): ViewPose => ({ position: [10, 8, 10], target: [0, 0, 0], up: [0, 1, 0], fov: 45, ortho: false, ...p });

describe('view poses', () => {
  it('compares within a tolerance that scales with the distance', () => {
    expect(viewPoseEqual(pose(), pose())).toBe(true);
    expect(viewPoseEqual(pose(), pose({ position: [10.0001, 8, 10] }))).toBe(true);
    expect(viewPoseEqual(pose(), pose({ position: [10.5, 8, 10] }))).toBe(false);
    expect(viewPoseEqual(pose(), pose({ ortho: true }))).toBe(false);
    expect(viewPoseEqual(pose(), pose({ up: [0, 0, 1] }))).toBe(false);
    // The undo plugin uses a looser tolerance (0.3 %) to skip the tail of a damped orbit.
    expect(viewPoseEqual(pose(), pose({ position: [10.03, 8, 10] }), 3e-3)).toBe(true);
    expect(viewPoseEqual(pose(), pose({ position: [10.2, 8, 10] }), 3e-3)).toBe(false);
  });

  it('names the move', () => {
    expect(describeViewChange(pose(), pose({ position: [5, 4, 5] }))).toBe('zoom'); // same direction, half the distance
    expect(describeViewChange(pose(), pose({ position: [10, 8, -10] }))).toBe('orbit'); // about the target
    expect(describeViewChange(pose(), pose({ position: [11.5, 8, 10], target: [1.5, 0, 0] }))).toBe('pan'); // both slid
    expect(describeViewChange(pose(), pose({ ortho: true }))).toBe('projection');
    expect(describeViewChange(pose(), pose({ position: [0, 30, 0.1], target: [3, 0, 3] }))).toBe('view'); // a jump: home, fit, a saved view
  });

  it('mixes two poses and eases', () => {
    const a = pose();
    const b = pose({ position: [0, 0, 20], up: [0, 0, 1] });
    expect(mixViewPose(a, b, 0)).toEqual({ ...a, ortho: false });
    expect(mixViewPose(a, b, 1).position).toEqual([0, 0, 20]);
    const m = mixViewPose(a, b, 0.5);
    expect(m.position).toEqual([5, 4, 15]);
    expect(Math.hypot(...m.up)).toBeCloseTo(1, 9);
    expect(easeInOut(0)).toBe(0);
    expect(easeInOut(1)).toBe(1);
    expect(easeInOut(0.5)).toBeCloseTo(0.5, 9);
    expect(easeInOut(0.25)).toBeLessThan(0.25);
  });
});
