import { describe, expect, it } from 'vitest';
import { Vector3 } from 'three';
import {
  ExplodeAnim,
  boundsCentre,
  buildExplodeTable,
  explodeOffset,
  resolveExplodeSet,
  resolveExplodeSource,
  storeyRanks,
  unionCentre,
} from '../src/cinematic/explode';
import type { BoundsTuple, ExplodeParams } from '../src/cinematic/explode';

const radial = (factor = 1, minPush = 0): ExplodeParams => ({ mode: 'radial', factor, storeyGap: 3, minPush });
const box = (cx: number, cy: number, cz: number, h = 0.5): BoundsTuple => [cx - h, cy - h, cz - h, cx + h, cy + h, cz + h];

describe('explode set', () => {
  const sel = [10, 11, 12];
  const occ = [20, 21];
  it('auto picks the selection when more than one element is selected', () => {
    expect(resolveExplodeSource('auto', 2)).toBe('selection');
    expect(resolveExplodeSource('auto', 300)).toBe('selection');
    const r = resolveExplodeSet('auto', sel, occ);
    expect(r.source).toBe('selection');
    expect(r.ids).toEqual([10, 11, 12]);
  });
  it('auto picks the occluders when exactly one element is selected', () => {
    expect(resolveExplodeSource('auto', 1)).toBe('occluders');
    const r = resolveExplodeSet('auto', [10], occ);
    expect(r.source).toBe('occluders');
    expect(r.ids).toEqual([20, 21]);
  });
  it('explicit sources override the rule; both is the union without duplicates', () => {
    expect(resolveExplodeSet('occluders', sel, occ).ids).toEqual([20, 21]);
    expect(resolveExplodeSet('selection', [10], occ).ids).toEqual([10]);
    expect(resolveExplodeSet('both', sel, [11, 20]).ids.sort((a, b) => a - b)).toEqual([10, 11, 12, 20]);
  });
});

describe('radial offsets', () => {
  // Centre of the set: x from -1 to 9 -> C.x = 4, y/z around 0.
  const b: Record<number, BoundsTuple> = {
    1: box(-0.5, 0, 0), // union x from -1 ...
    2: box(2, 0, 0),
    3: box(8.5, 0, 0), // ... to 9
    4: box(4, 0, 0), // exactly at C
  };
  const table = buildExplodeTable([1, 2, 3, 4], { bounds: (id) => b[id] });
  const o = new Vector3();

  it('C is the bounds centre of the explode set', () => {
    expect(table.centre.toArray()).toEqual([4, 0, 0]);
    expect(unionCentre([1, 3], (id) => b[id])!.toArray()).toEqual([4, 0, 0]);
    expect(boundsCentre([0, 0, 0, 2, 4, 6]).toArray()).toEqual([1, 2, 3]);
  });
  it('offset_i = (c_i - C) * factor: an element twice as far moves twice as far, away from C', () => {
    explodeOffset(table, 0, radial(1), 1, o); // c = -0.5: 4.5 m from C on the -x side
    expect(o.x).toBeCloseTo(-4.5, 6);
    expect(explodeOffset(table, 1, radial(1), 1).x).toBeCloseTo(-2, 6); // c = 2: 2 m from C
    // Exactly twice as far: elements at 2 m and 4 m from C
    const t2 = buildExplodeTable([5, 6, 7], { bounds: (id) => ({ 5: box(-4, 0, 0), 6: box(2, 0, 0), 7: box(4, 0, 0) } as Record<number, BoundsTuple>)[id], centre: new Vector3(0, 0, 0) });
    const a = explodeOffset(t2, 1, radial(1), 1).clone();
    const c = explodeOffset(t2, 2, radial(1), 1).clone();
    expect(c.length()).toBeCloseTo(2 * a.length(), 9);
    expect(a.x).toBeCloseTo(2, 9);
  });
  it('scales with factor and progress, and is zero at progress 0 or factor 0', () => {
    expect(explodeOffset(table, 2, radial(0.5), 1).x).toBeCloseTo(2.25, 6);
    expect(explodeOffset(table, 2, radial(2), 0.5).x).toBeCloseTo(4.5, 6);
    expect(explodeOffset(table, 2, radial(1), 0).length()).toBe(0);
    expect(explodeOffset(table, 2, radial(0), 1).length()).toBe(0);
  });
  it('is radial, not planar: elements on one storey plane move different distances in different directions', () => {
    const planar = buildExplodeTable([1, 2, 3, 4], {
      bounds: (id) => ({ 1: box(-3, 3, 0), 2: box(3, 3, 0), 3: box(0, 3, 6), 4: box(0, 3, -6) } as Record<number, BoundsTuple>)[id],
    });
    const offs = [0, 1, 2, 3].map((i) => explodeOffset(planar, i, radial(1), 1).clone());
    expect(offs[0]!.x).toBeLessThan(0);
    expect(offs[1]!.x).toBeGreaterThan(0);
    expect(offs[2]!.z).toBeGreaterThan(0);
    expect(offs[3]!.z).toBeLessThan(0);
    expect(offs[2]!.length()).toBeCloseTo(2 * offs[0]!.length(), 9); // 6 m vs 3 m from the centre
  });
  it('minPush lifts short offsets to a minimum along the same direction; an element at C goes straight up', () => {
    const p = radial(1, 0.5);
    explodeOffset(table, 3, p, 1, o);
    expect(o.toArray()).toEqual([0, 0.5, 0]);
    const close = buildExplodeTable([1, 2], { bounds: (id) => (id === 1 ? box(1, 0, 0) : box(-1, 0, 0)) });
    explodeOffset(close, 0, radial(1, 0.5), 1, o); // 1 m from C already: unchanged
    expect(o.x).toBeCloseTo(1, 6);
    explodeOffset(close, 0, radial(0.2, 0.5), 1, o); // 0.2 m raised to 0.5 m, direction +x
    expect(o.x).toBeCloseTo(0.5, 6);
    expect(o.y).toBeCloseTo(0, 9);
  });
});

describe('storeys mode', () => {
  const storeys = [
    { id: 0, elevation: 0 },
    { id: 1, elevation: 3 },
    { id: 2, elevation: 6 },
    { id: 3, elevation: 9 },
  ];
  const ranks = storeyRanks(storeys);
  // Elements: two per storey, ids 10.. ; storey s centre y = 3 s + 1.
  const storeyOfId = (id: number): number | null => (id >= 100 ? null : Math.floor((id - 10) / 2));
  const cy = (id: number): number => (id >= 100 ? 4 : 3 * storeyOfId(id)! + 1);
  const ids = [10, 11, 12, 13, 14, 15];
  const bounds = (id: number): BoundsTuple => box(id % 2 ? 1 : -1, cy(id), 0);
  const p: ExplodeParams = { mode: 'storeys', factor: 1, storeyGap: 3, minPush: 0 };

  it('separates storeys vertically by (index - median) * gap, ordered bottom to top', () => {
    const t = buildExplodeTable(ids, { bounds, storeyOf: storeyOfId, ranks });
    const dy = ids.map((_, i) => explodeOffset(t, i, p, 1).y);
    // storeys 0,1,2 -> levels -1,0,+1 -> -3, 0, +3
    expect(dy).toEqual([-3, -3, 0, 0, 3, 3]);
    for (let i = 0; i < ids.length; i++) {
      const o = explodeOffset(t, i, p, 1);
      expect(o.x).toBe(0);
      expect(o.z).toBe(0);
    }
  });
  it('gap scales the separation, progress eases it', () => {
    const t = buildExplodeTable(ids, { bounds, storeyOf: storeyOfId, ranks });
    expect(explodeOffset(t, 5, { ...p, storeyGap: 5 }, 1).y).toBe(5);
    expect(explodeOffset(t, 5, { ...p, storeyGap: 5 }, 0.5).y).toBe(2.5);
  });
  it('median is over the storeys present, with storey ids ranked by elevation', () => {
    const t = buildExplodeTable([10, 14], { bounds, storeyOf: storeyOfId, ranks }); // storeys 0 and 2: median 1
    expect(explodeOffset(t, 0, p, 1).y).toBe(-3);
    expect(explodeOffset(t, 1, p, 1).y).toBe(3);
    // Storey ids need not be in elevation order
    const shuffled = storeyRanks([{ id: 0, elevation: 6 }, { id: 1, elevation: 0 }, { id: 2, elevation: 3 }]);
    expect([...shuffled.entries()]).toEqual([[1, 0], [2, 1], [0, 2]]);
  });
  it('elements without a storey take a fractional level from their bounds centre y', () => {
    const t = buildExplodeTable([10, 12, 14, 100], { bounds, storeyOf: storeyOfId, ranks });
    // Reference centre y per storey: 1, 4, 7. Element 100 sits at y 4: exactly storey 1, the median -> level 0.
    const o = explodeOffset(t, 3, p, 1);
    expect(o.y).toBeCloseTo(0, 6);
    const t2 = buildExplodeTable([10, 12, 14, 101], { bounds: (id) => (id === 101 ? box(0, 5.5, 0) : bounds(id)), storeyOf: (id) => (id === 101 ? null : storeyOfId(id)), ranks });
    expect(explodeOffset(t2, 3, p, 1).y).toBeCloseTo(1.5, 6); // y 5.5: half a storey above storey 1 -> +0.5 storey -> 1.5 m
  });
  it('without any storey, centre y over a nominal storey height gives the level', () => {
    const t = buildExplodeTable([1, 2, 3], { bounds: (id) => box(0, id * 3, 0) }); // y 3, 6, 9: median 6
    expect(explodeOffset(t, 0, p, 1).y).toBeCloseTo(-3, 6);
    expect(explodeOffset(t, 1, p, 1).y).toBeCloseTo(0, 6);
    expect(explodeOffset(t, 2, p, 1).y).toBeCloseTo(3, 6);
  });
  it('radial+storeys is the sum of both', () => {
    const t = buildExplodeTable(ids, { bounds, storeyOf: storeyOfId, ranks });
    const both = explodeOffset(t, 5, { ...p, mode: 'radial+storeys' }, 1).clone();
    const r = explodeOffset(t, 5, { ...p, mode: 'radial' }, 1).clone();
    const s = explodeOffset(t, 5, p, 1).clone();
    expect(both.toArray()).toEqual(r.add(s).toArray());
  });
});

describe('ExplodeAnim', () => {
  it('eases from 0 to 1 over the duration and stops', () => {
    const a = new ExplodeAnim();
    expect(a.moving).toBe(false);
    a.go(1, 1000, 800);
    expect(a.moving).toBe(true);
    expect(a.update(1000)).toBe(0);
    const mid = a.update(1400);
    expect(mid).toBeCloseTo(0.5, 6); // ease-in-out is symmetric
    expect(a.update(1800)).toBe(1);
    expect(a.moving).toBe(false);
    expect(a.update(5000)).toBe(1);
  });
  it('collapse goes back to exactly 0, and reversing mid-way starts from where it is', () => {
    const a = new ExplodeAnim();
    a.go(1, 0, 1000);
    const v = a.update(300);
    expect(v).toBeGreaterThan(0);
    expect(v).toBeLessThan(0.5);
    a.go(0, 300, 1000);
    expect(a.update(300)).toBeCloseTo(v, 9);
    expect(a.update(1300)).toBe(0);
    expect(a.target).toBe(0);
    expect(a.moving).toBe(false);
  });
  it('reset snaps to collapsed', () => {
    const a = new ExplodeAnim();
    a.go(1, 0, 100);
    a.update(100);
    a.reset();
    expect(a.value).toBe(0);
    expect(a.target).toBe(0);
    expect(a.moving).toBe(false);
  });
});
