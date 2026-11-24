import { describe, expect, it } from 'vitest';
import type { ElementRecord, SceneModel } from '../src/types';
import { buildTree, flattenTree } from '../src/ui/treeModel';
import type { FlatRow } from '../src/ui/treeModel';
import { EMPTY_TYPE_AHEAD, TYPE_AHEAD_MS, isTypeAheadChar, leftMove, moveActive, parentIndex, rightMove, siblingKeysToOpen, typeAhead } from '../src/ui/treeKeys';
import { focusOwnerOf, ownMode, widgetOwnsKey } from '../src/input/focusOwner';
import { nextRegion } from '../src/input/regions';
import type { RegionId } from '../src/input/regions';

function el(id: number, name: string, cls: string, storey: number): ElementRecord {
  return { id, globalId: `g${id}`, name, ifcClass: cls, storey } as unknown as ElementRecord;
}
const model = {
  storeys: [
    { id: 1, name: 'Ground', elevation: 0 },
    { id: 2, name: 'First', elevation: 3 },
  ],
  elements: [el(0, 'Door A', 'IfcDoor', 1), el(1, 'Door B', 'IfcDoor', 1), el(2, 'Wall 1', 'IfcWall', 1), el(3, 'Door C', 'IfcDoor', 2)],
  relations: { systems: [] },
} as unknown as SceneModel;

function rowsWith(open: string[]): FlatRow[] {
  const set = new Set(open);
  return flattenTree(buildTree(model), (k) => set.has(k));
}
const labels = (rows: FlatRow[]): string[] => rows.map((r) => r.node.label);

describe('tree keys: movement', () => {
  const rows = rowsWith(['st:1', 'st:1|c:IfcDoor']);
  it('lists the expected rows', () => {
    expect(labels(rows)).toEqual(['Ground', 'IfcDoor', 'Door A', 'Door B', 'IfcWall', 'First']);
  });
  it('moves by one and clamps at both ends', () => {
    expect(moveActive(rows, 0, 'ArrowDown', 5)).toBe(1);
    expect(moveActive(rows, 0, 'ArrowUp', 5)).toBe(0);
    expect(moveActive(rows, 5, 'ArrowDown', 5)).toBe(5);
  });
  it('Home, End and pages', () => {
    expect(moveActive(rows, 3, 'Home', 5)).toBe(0);
    expect(moveActive(rows, 3, 'End', 5)).toBe(5);
    expect(moveActive(rows, 1, 'PageDown', 3)).toBe(4);
    expect(moveActive(rows, 4, 'PageUp', 3)).toBe(1);
    expect(moveActive(rows, 4, 'PageDown', 99)).toBe(5);
    expect(moveActive([], 0, 'ArrowDown', 5)).toBe(-1);
  });
  it('finds the parent row', () => {
    expect(parentIndex(rows, 3)).toBe(1);
    expect(parentIndex(rows, 1)).toBe(0);
    expect(parentIndex(rows, 0)).toBe(-1);
  });
});

describe('tree keys: open and close', () => {
  const rows = rowsWith(['st:1', 'st:1|c:IfcDoor']);
  it('Right opens a closed row, then goes to the first child', () => {
    expect(rightMove(rows, 5)).toEqual({ type: 'open', key: 'st:2' });
    expect(rightMove(rows, 0)).toEqual({ type: 'move', index: 1 });
    expect(rightMove(rows, 4)).toEqual({ type: 'open', key: 'st:1|c:IfcWall' });
  });
  it('Right on a leaf does nothing', () => {
    expect(rightMove(rows, 2)).toEqual({ type: 'none' });
  });
  it('Left closes an open row, else goes to the parent', () => {
    expect(leftMove(rows, 1)).toEqual({ type: 'close', key: 'st:1|c:IfcDoor' });
    expect(leftMove(rows, 2)).toEqual({ type: 'move', index: 1 });
    expect(leftMove(rows, 5)).toEqual({ type: 'none' });
  });
  it('star lists the closed siblings that have children', () => {
    expect(siblingKeysToOpen(rows, 5)).toEqual(['st:2']);
    expect(siblingKeysToOpen(rows, 1)).toEqual(['st:1|c:IfcWall']);
    expect(siblingKeysToOpen(rows, 2)).toEqual([]);
  });
});

describe('tree keys: type-ahead', () => {
  const rows = rowsWith(['st:1', 'st:1|c:IfcDoor']);
  it('jumps to the next row that starts with the letter', () => {
    const r = typeAhead(rows, 0, EMPTY_TYPE_AHEAD, 'd', 1000);
    expect(r.index).toBe(2);
  });
  it('a longer buffer includes the active row and narrows', () => {
    let st = EMPTY_TYPE_AHEAD;
    let r = typeAhead(rows, 0, st, 'd', 1000);
    st = r.state;
    r = typeAhead(rows, r.index, st, 'o', 1100);
    expect(r.index).toBe(2);
    st = r.state;
    r = typeAhead(rows, r.index, st, 'x', 1200);
    expect(st.buffer).toBe('do');
    expect(r.state.buffer).toBe('dox');
    expect(r.index).toBe(-1);
  });
  it('a repeated letter cycles', () => {
    let r = typeAhead(rows, 0, EMPTY_TYPE_AHEAD, 'd', 1000);
    expect(r.index).toBe(2);
    r = typeAhead(rows, r.index, r.state, 'd', 1100);
    expect(r.index).toBe(3);
    r = typeAhead(rows, r.index, r.state, 'd', 1200);
    expect(r.index).toBe(2);
  });
  it('the buffer resets after the timeout', () => {
    const a = typeAhead(rows, 0, EMPTY_TYPE_AHEAD, 'i', 1000);
    expect(a.index).toBe(1);
    const b = typeAhead(rows, a.index, a.state, 'f', 1000 + TYPE_AHEAD_MS + 1);
    expect(b.state.buffer).toBe('f');
    expect(b.index).toBe(5);
  });
  it('wraps around and ignores case', () => {
    expect(typeAhead(rows, 5, EMPTY_TYPE_AHEAD, 'G', 0).index).toBe(0);
    expect(typeAhead(rows, 0, EMPTY_TYPE_AHEAD, 'z', 0).index).toBe(-1);
  });
  it('knows which keys are characters', () => {
    expect(isTypeAheadChar('a')).toBe(true);
    expect(isTypeAheadChar(' ')).toBe(false);
    expect(isTypeAheadChar('*')).toBe(false);
    expect(isTypeAheadChar('Enter')).toBe(false);
  });
});

describe('focus ownership', () => {
  const k = (key: string, m: Partial<{ ctrlKey: boolean; altKey: boolean; metaKey: boolean; shiftKey: boolean }> = {}) => ({ key, ...m });
  it('a nav widget keeps arrows, Home/End, pages, Enter and Space but not letters', () => {
    for (const key of ['ArrowUp', 'ArrowLeft', 'Home', 'End', 'PageUp', 'PageDown', 'Enter', ' ']) expect(widgetOwnsKey('nav', k(key))).toBe(true);
    expect(widgetOwnsKey('nav', k('f'))).toBe(false);
    expect(widgetOwnsKey('nav', k('Escape'))).toBe(false);
    expect(widgetOwnsKey('nav', k('Tab'))).toBe(false);
  });
  it('an all widget also keeps plain characters', () => {
    expect(widgetOwnsKey('all', k('f'))).toBe(true);
    expect(widgetOwnsKey('all', k('H', { shiftKey: true }))).toBe(true);
  });
  it('Ctrl, Alt and Meta chords reach the global actions', () => {
    expect(widgetOwnsKey('all', k('ArrowLeft', { altKey: true }))).toBe(false);
    expect(widgetOwnsKey('all', k('a', { ctrlKey: true }))).toBe(false);
    expect(widgetOwnsKey('all', k('k', { metaKey: true }))).toBe(false);
  });
  it('Shift only counts with Up and Down in a nav widget', () => {
    expect(widgetOwnsKey('nav', k('ArrowDown', { shiftKey: true }))).toBe(true);
    expect(widgetOwnsKey('nav', k('ArrowLeft', { shiftKey: true }))).toBe(false);
    expect(widgetOwnsKey('nav', k('PageUp', { shiftKey: true }))).toBe(false);
  });
  it('reads the mode from role and attribute', () => {
    expect(ownMode('tree', null)).toBe('nav');
    expect(ownMode('listbox', null)).toBe('all');
    expect(ownMode('list', 'nav')).toBe('nav');
    expect(ownMode(null, '')).toBe('all');
  });
  it('finds the closest owner of a target', () => {
    const attrs = { role: 'tree' } as Record<string, string>;
    const widget = { getAttribute: (n: string) => attrs[n] ?? null };
    const target = { closest: (sel: string) => (sel.includes('role="tree"') ? widget : null) };
    expect(focusOwnerOf(target)?.mode).toBe('nav');
    expect(focusOwnerOf({ closest: () => null })).toBeNull();
    expect(focusOwnerOf(null)).toBeNull();
  });
});

describe('region cycling', () => {
  const all = (): boolean => true;
  it('goes canvas, left, right, top and wraps', () => {
    expect(nextRegion('canvas', 1, all)).toBe('left');
    expect(nextRegion('left', 1, all)).toBe('right');
    expect(nextRegion('right', 1, all)).toBe('top');
    expect(nextRegion('top', 1, all)).toBe('canvas');
  });
  it('goes backward', () => {
    expect(nextRegion('canvas', -1, all)).toBe('top');
    expect(nextRegion('left', -1, all)).toBe('canvas');
  });
  it('skips regions that are not available', () => {
    const av = (r: RegionId): boolean => r !== 'left' && r !== 'top';
    expect(nextRegion('canvas', 1, av)).toBe('right');
    expect(nextRegion('right', 1, av)).toBe('canvas');
    expect(nextRegion('canvas', 1, (r) => r === 'canvas')).toBe('canvas');
  });
});
