import { describe, expect, it } from 'vitest';
import { History } from '../src/markup/history';

describe('markup undo / redo stack', () => {
  it('undoes and redoes in order', () => {
    const h = new History<string[]>();
    let state: string[] = [];
    const change = (v: string): void => { h.record(state); state = [...state, v]; };
    change('a'); change('b'); change('c');
    expect(h.undoDepth).toBe(3);
    state = h.undo(state)!; expect(state).toEqual(['a', 'b']);
    state = h.undo(state)!; expect(state).toEqual(['a']);
    expect(h.canRedo).toBe(true);
    state = h.redo(state)!; expect(state).toEqual(['a', 'b']);
    state = h.redo(state)!; expect(state).toEqual(['a', 'b', 'c']);
    expect(h.redo(state)).toBeNull();
    state = h.undo(state)!; state = h.undo(state)!; state = h.undo(state)!;
    expect(state).toEqual([]);
    expect(h.undo(state)).toBeNull();
    expect(h.canUndo).toBe(false);
  });

  it('a new change drops the redo stack', () => {
    const h = new History<number[]>();
    let s: number[] = [1];
    h.record(s); s = [1, 2];
    h.record(s); s = [1, 2, 3];
    s = h.undo(s)!;
    expect(h.canRedo).toBe(true);
    h.record(s); s = [1, 2, 9];
    expect(h.canRedo).toBe(false);
    expect(h.undo(s)).toEqual([1, 2]);
  });

  it('keeps copies, so later edits do not change the history', () => {
    const h = new History<{ n: number[] }>();
    const s = { n: [1] };
    h.record(s);
    s.n.push(2);
    expect(h.undo(s)).toEqual({ n: [1] });
  });

  it('caps the depth and clears', () => {
    const h = new History<number>(3);
    for (let i = 0; i < 10; i++) h.record(i);
    expect(h.undoDepth).toBe(3);
    expect(h.undo(99)).toBe(9);
    h.clear();
    expect(h.canUndo || h.canRedo).toBe(false);
  });
});
