import { describe, expect, it } from 'vitest';
import { Vector3 } from 'three';
import {
  HISTORY_LIMIT,
  ViewHistory,
  dollyForFov,
  orbitOffset,
  stepCycle,
  stepStorey,
  storeyLevels,
  tabOrder,
  viewDirection,
  yawOf,
} from '../src/input/navigation';
import type { Pose } from '../src/input/navigation';
import { invertIds, sameClassIds } from '../src/input/commands';
import { modelOf } from './sidebar-model';

const pose = (x: number): Pose => ({ position: [x, 0, 0], target: [0, 0, 0] });

describe('view history', () => {
  it('goes back and forward through pushed poses', () => {
    const h = new ViewHistory();
    h.push(pose(1), 0);
    h.push(pose(2), 1000);
    h.push(pose(3), 2000);
    expect(h.goBack(pose(4))!.position[0]).toBe(3);
    expect(h.goBack(pose(3))!.position[0]).toBe(2);
    expect(h.goForward(pose(2))!.position[0]).toBe(3);
    expect(h.goForward(pose(3))!.position[0]).toBe(4);
    expect(h.goForward(pose(4))).toBeNull();
    expect(h.goBack(pose(4))!.position[0]).toBe(3);
  });
  it('a new push clears the forward stack', () => {
    const h = new ViewHistory();
    h.push(pose(1), 0);
    h.goBack(pose(2));
    expect(h.forwardCount).toBe(1);
    h.push(pose(5), 10);
    expect(h.forwardCount).toBe(0);
  });
  it('keeps at most 50 poses, dropping the oldest', () => {
    const h = new ViewHistory();
    for (let i = 0; i < 80; i++) h.push(pose(i + 1), i * 1000);
    expect(h.backCount).toBe(HISTORY_LIMIT);
    let last = 0;
    let n = 0;
    for (let p = h.goBack(pose(0)); p; p = h.goBack(p)) {
      last = p.position[0];
      n++;
    }
    expect(n).toBe(50);
    expect(last).toBe(31);
  });
  it('coalesces a run of same-tag pushes (zoom steps) into one entry', () => {
    const h = new ViewHistory();
    h.push(pose(1), 0, 'zoom');
    h.push(pose(2), 100, 'zoom');
    h.push(pose(3), 200, 'zoom');
    expect(h.backCount).toBe(1);
    expect(h.goBack(pose(4))!.position[0]).toBe(1);
    h.push(pose(1), 5000, 'zoom');
    h.push(pose(2), 9000, 'zoom');
    expect(h.backCount).toBe(2);
  });
  it('ignores a push equal to the top and returns null when empty', () => {
    const h = new ViewHistory();
    expect(h.goBack(pose(0))).toBeNull();
    h.push(pose(1), 0);
    h.push(pose(1), 5000);
    expect(h.backCount).toBe(1);
  });
});

describe('storey stepping', () => {
  // Elements at heights: storey 7 (elevation 6) low, storey 3 (elevation 0), storey 9 (elevation 3).
  const model = modelOf(
    [
      { cls: 'IfcWall', storey: 3 },
      { cls: 'IfcWall', storey: 3 },
      { cls: 'IfcSlab', storey: 9 },
      { cls: 'IfcSlab', storey: 7 },
      { cls: 'IfcWall', storey: null },
    ],
    [
      { id: 7, name: 'Roof', elevation: 6 },
      { id: 3, name: 'Ground', elevation: 0 },
      { id: 9, name: 'First', elevation: 3 },
      { id: 11, name: 'Empty', elevation: 9 },
    ],
  );
  model.elements[0]!.bounds = [0, 0, 0, 1, 2, 1];
  model.elements[1]!.bounds = [0, 0, 0, 1, 2, 1];
  model.elements[2]!.bounds = [0, 3, 0, 1, 3.4, 1];
  model.elements[3]!.bounds = [0, 6, 0, 1, 6.2, 1];
  const levels = storeyLevels(model);

  it('orders storeys by elevation and drops empty ones', () => {
    expect(levels.map((l) => l.name)).toEqual(['Ground', 'First', 'Roof']);
    expect(levels[0]!.y).toBeCloseTo(1);
  });
  it('steps up and down from any height', () => {
    expect(stepStorey(levels, 0.2, 1)!.name).toBe('Ground');
    expect(stepStorey(levels, 1, 1)!.name).toBe('First');
    expect(stepStorey(levels, 3.2, 1)!.name).toBe('Roof');
    expect(stepStorey(levels, 6.1, 1)).toBeNull();
    expect(stepStorey(levels, 6.1, -1)!.name).toBe('First');
    expect(stepStorey(levels, 3.2, -1)!.name).toBe('Ground');
    expect(stepStorey(levels, 1, -1)).toBeNull();
    expect(stepStorey([], 0, 1)).toBeNull();
  });
});

describe('Tab cycling', () => {
  it('visits the selection in id order and wraps both ways', () => {
    const order = tabOrder(new Set([9, 2, 5]));
    expect(order).toEqual([2, 5, 9]);
    let i = -1;
    const seen: number[] = [];
    for (let k = 0; k < 4; k++) {
      i = stepCycle(i, order.length, 1);
      seen.push(order[i]!);
    }
    expect(seen).toEqual([2, 5, 9, 2]);
    i = -1;
    expect(stepCycle(i, 3, -1)).toBe(2);
    expect(stepCycle(0, 3, -1)).toBe(2);
    expect(stepCycle(0, 0, 1)).toBe(-1);
    expect(stepCycle(0, 1, 1)).toBe(0);
  });
});

describe('camera maths', () => {
  it('orbits about the vertical axis keeping the distance, and clamps the pitch at the poles', () => {
    const off = new Vector3(0, 0, 10);
    const a = orbitOffset(off, Math.PI / 2, 0);
    expect(a.length()).toBeCloseTo(10);
    expect(a.x).toBeCloseTo(10);
    expect(yawOf(a)).toBeCloseTo(Math.PI / 2);
    const b = orbitOffset(new Vector3(0, 5, 5), 0, -3);
    expect(b.y).toBeGreaterThan(7.06);
    expect(b.length()).toBeCloseTo(Math.hypot(5, 5));
    expect(orbitOffset(new Vector3(5, 5, 0), 0, 3).y).toBeLessThan(-7.06);
  });
  it('standard view directions look the right way', () => {
    expect(viewDirection('top').y).toBe(1);
    expect(viewDirection('bottom').y).toBe(-1);
    expect(viewDirection('front').z).toBe(1);
    expect(viewDirection('back').z).toBe(-1);
    expect(viewDirection('right').x).toBe(1);
    expect(viewDirection('left').x).toBe(-1);
    expect(viewDirection('iso').length()).toBeCloseTo(1);
  });
  it('dollies out to keep the apparent size when the field of view narrows', () => {
    const d = dollyForFov(10, 45, 2);
    expect(d).toBeCloseTo((10 * Math.tan(Math.PI / 8)) / Math.tan(Math.PI / 180));
    expect(dollyForFov(d, 2, 45)).toBeCloseTo(10);
  });
});

describe('selection helpers', () => {
  it('inverts within the visible elements', () => {
    expect(invertIds([0, 1, 2, 4], new Set([1, 4]))).toEqual([0, 2]);
  });
  it('selects the visible elements of the same classes', () => {
    const els = [{ ifcClass: 'A' }, { ifcClass: 'B' }, { ifcClass: 'A' }, { ifcClass: 'A' }, { ifcClass: 'C' }];
    expect(sameClassIds(els, new Set([0]), new Set([3]))).toEqual([0, 2]);
    expect(sameClassIds(els, new Set([0, 4]), new Set())).toEqual([0, 2, 3, 4]);
    expect(sameClassIds(els, new Set(), new Set())).toEqual([]);
  });
});
