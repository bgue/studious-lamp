import { describe, expect, it } from 'vitest';
import { Vector3 } from 'three';
import { FLAG_FOCUS, FLAG_HIDDEN } from '../src/types';
import { blocksWalk, collideMove, floorAtOrBelow, slideAlongWall, standingSpot, stepWalkStorey } from '../src/input/walk';

const floors = [
  { id: 0, name: 'Ground', floorY: 0 },
  { id: 1, name: 'Upper', floorY: 3 },
  { id: 2, name: 'Roof', floorY: 6 },
];

describe('standing spot', () => {
  it('stands on a surface that faces up', () => {
    const s = standingSpot({ x: 2, y: 3.05, z: 4 }, { x: 0, y: 1, z: 0 }, floors, 1.6);
    expect(s.onSurface).toBe(true);
    expect(s.eye.toArray()).toEqual([2, 3.05 + 1.6, 4]);
  });
  it('uses the storey floor below a wall hit', () => {
    const s = standingSpot({ x: 1, y: 4.2, z: 1 }, { x: 1, y: 0, z: 0 }, floors, 1.6);
    expect(s.onSurface).toBe(false);
    expect(s.floorY).toBe(3);
    expect(s.eye.y).toBeCloseTo(4.6);
  });
  it('falls back to the downward ray, then to the hit height', () => {
    const wall = { x: 0, y: 0, z: 1 };
    expect(standingSpot({ x: 0, y: -1, z: 0 }, wall, floors, 1.6, -2).floorY).toBe(-2);
    expect(standingSpot({ x: 0, y: -1, z: 0 }, wall, floors, 1.6, null).floorY).toBe(-1);
    expect(standingSpot({ x: 0, y: 1, z: 0 }, wall, [], 1.6, 0.2).floorY).toBe(0.2);
  });
  it('a slightly sloped surface is not a floor', () => {
    expect(standingSpot({ x: 0, y: 4, z: 0 }, { x: 0.8, y: 0.6, z: 0 }, floors, 1.6).onSurface).toBe(false);
  });
  it('floorAtOrBelow tolerates a slab a few cm below the level', () => {
    expect(floorAtOrBelow(floors, 2.97)?.id).toBe(1);
    expect(floorAtOrBelow(floors, -1)).toBeNull();
  });
});

describe('storey stepping in Walk mode', () => {
  it('goes up and keeps the eye height above the floor', () => {
    const r = stepWalkStorey(floors, 1.6, 1)!;
    expect(r.level.name).toBe('Upper');
    expect(r.eyeY).toBeCloseTo(4.6);
  });
  it('keeps a raised eye (q/e) offset', () => {
    expect(stepWalkStorey(floors, 3 + 2.1, -1)!.eyeY).toBeCloseTo(2.1);
  });
  it('stops at the ends', () => {
    expect(stepWalkStorey(floors, 7.6, 1)).toBeNull();
    expect(stepWalkStorey(floors, 1.6, -1)).toBeNull();
    expect(stepWalkStorey([], 1.6, 1)).toBeNull();
  });
  it('from below every floor, up goes to the lowest', () => {
    expect(stepWalkStorey(floors, -0.5, 1)!.level.id).toBe(0);
  });
});

describe('collision maths', () => {
  it('slide removes the component into the wall only', () => {
    const out = slideAlongWall(new Vector3(1, 0, -1), new Vector3(0, 0, 1));
    expect(out.toArray()).toEqual([1, 0, 0]);
    // moving away from the wall is untouched
    expect(slideAlongWall(new Vector3(1, 0, 1), new Vector3(0, 0, 1)).toArray()).toEqual([1, 0, 1]);
  });
  const wallAt = (x: number) => (o: Vector3, d: Vector3, max: number) => {
    if (d.x <= 1e-9) return null;
    const dist = (x - o.x) / d.x;
    return dist >= 0 && dist <= max ? { distance: dist, normal: { x: -1, y: 0, z: 0 } } : null;
  };
  it('does not touch a free move and casts nothing for no move', () => {
    let rays = 0;
    const cast = (...a: Parameters<ReturnType<typeof wallAt>>) => (rays++, wallAt(10)(...a));
    expect(collideMove(new Vector3(), new Vector3(0.1, 0, 0), cast).x).toBeCloseTo(0.1);
    expect(rays).toBe(3);
    rays = 0;
    collideMove(new Vector3(), new Vector3(0, 0.2, 0), cast);
    expect(rays).toBe(0);
  });
  it('stops 0.3 m short of the wall', () => {
    const out = collideMove(new Vector3(0, 1.6, 0), new Vector3(0.5, 0, 0), wallAt(0.6));
    expect(out.x).toBeCloseTo(0.3);
  });
  it('slides along a wall on a diagonal move', () => {
    const out = collideMove(new Vector3(0.3, 1.6, 0), new Vector3(0.2, 0, 0.2), wallAt(0.6));
    expect(out.x).toBeCloseTo(0, 5);
    expect(out.z).toBeGreaterThan(0.05);
  });
  it('ignores floors and ceilings, and a move that keeps clear', () => {
    const slab = () => ({ distance: 0.35, normal: { x: 0, y: 1, z: 0 } });
    expect(collideMove(new Vector3(), new Vector3(0.1, 0, 0), slab).x).toBeCloseTo(0.1);
    expect(collideMove(new Vector3(), new Vector3(0.1, 0, 0), wallAt(0.45)).x).toBeCloseTo(0.1);
  });
  it('keeps the vertical part of the move', () => {
    expect(collideMove(new Vector3(), new Vector3(0.5, 0.2, 0), wallAt(0.6)).y).toBe(0.2);
  });
});

describe('what blocks', () => {
  it('doors, hidden and ghosted elements do not', () => {
    expect(blocksWalk('IfcWall', 0, 1)).toBe(true);
    expect(blocksWalk('IfcDoor', 0, 1)).toBe(false);
    expect(blocksWalk('IFCDOOR', 0, 1)).toBe(false);
    expect(blocksWalk('IfcWall', FLAG_HIDDEN, 1)).toBe(false);
    expect(blocksWalk('IfcWall', 0, -1)).toBe(false);
    expect(blocksWalk('IfcWall', 0, 0.1)).toBe(false);
    expect(blocksWalk('IfcWall', FLAG_FOCUS, 0.1)).toBe(true);
    expect(blocksWalk('IfcWindow', 0, 0.5)).toBe(true);
  });
});
