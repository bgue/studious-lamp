// Orientation facet: measured by area-weighted PCA on synthetic boxes, beams, walls, a rotated wall, a flat-lying wall, an upside-down door.

import { describe, expect, it } from 'vitest';
import { eigenSym3, measureOrientation, orientationPlausible } from '../src/classify/facets/orientation';
import { box, merge, rotate } from './facets-helpers';

// viewer frame: x east, y up, z south. IFC: X = x, Y = -z, Z = y.
const WALL_X = (): ReturnType<typeof box> => box(0, 1.5, 0, 5, 3, 0.2); // 5 m along x, 3 m high, 0.2 m thick

describe('eigenSym3', () => {
  it('finds the eigenvalues and vectors of a symmetric matrix', () => {
    const e = eigenSym3([[2, 0, 0], [0, 5, 1], [0, 1, 5]]);
    expect(e.values[0]).toBeCloseTo(6, 9);
    expect(e.values[1]).toBeCloseTo(4, 9);
    expect(e.values[2]).toBeCloseTo(2, 9);
    expect(Math.abs(e.vectors[0][1]!)).toBeCloseTo(Math.SQRT1_2, 6);
  });
});

describe('measureOrientation', () => {
  it('a wall along x is planar, vertical, tilt 90, azimuth of its normal 90', () => {
    const m = measureOrientation(WALL_X())!;
    expect(m.shape).toBe('planar');
    expect(m.class).toBe('VERTICAL');
    expect(m.tilt).toBe(90);
    expect(m.azimuth).toBe(90); // normal points along IFC Y
    expect(m.principalAxis).toBe('Y');
    expect(orientationPlausible({ ifcClass: 'IfcWall', measure: m })).toBe(true);
  });

  it('a wall rotated 30 degrees about the vertical axis keeps class VERTICAL and turns the azimuth', () => {
    const m = measureOrientation(rotate(WALL_X(), 'y', 30))!;
    expect(m.class).toBe('VERTICAL');
    expect(m.tilt).toBe(90);
    // the normal was IFC +Y (90 deg); a rotation about viewer y by 30 turns it by -30 or +30 in plan
    expect([60, 120]).toContain(Math.round(m.azimuth));
    expect(m.principalAxis).toBeNull();
  });

  it('a wall lying flat is HORIZONTAL and implausible for an IfcWall', () => {
    const m = measureOrientation(rotate(WALL_X(), 'x', 90))!;
    expect(m.shape).toBe('planar');
    expect(m.class).toBe('HORIZONTAL');
    expect(m.tilt).toBe(0);
    expect(orientationPlausible({ ifcClass: 'IfcWall', measure: m })).toBe(false);
    expect(orientationPlausible({ ifcClass: 'IfcSlab', measure: m })).toBe(true);
  });

  it('a slab is planar HORIZONTAL; an inclined slab is INCLINED with its tilt', () => {
    const slab = box(0, 0, 0, 8, 0.25, 6);
    const m = measureOrientation(slab)!;
    expect(m.class).toBe('HORIZONTAL');
    expect(m.tilt).toBe(0);
    expect(m.principalAxis).toBe('Z');
    const roof = measureOrientation(rotate(slab, 'z', 25))!;
    expect(roof.class).toBe('INCLINED');
    expect(roof.tilt).toBeCloseTo(25, 0);
    expect(orientationPlausible({ ifcClass: 'IfcSlab', measure: roof })).toBe(true);
  });

  it('a beam along x is linear ALONG_X; along y ALONG_Y; at 45 degrees DIAGONAL', () => {
    const beam = box(0, 3, 0, 6, 0.3, 0.2);
    const bx = measureOrientation(beam)!;
    expect(bx.shape).toBe('linear');
    expect(bx.class).toBe('ALONG_X');
    expect(bx.azimuth).toBe(0);
    expect(bx.tilt).toBe(0);
    expect(measureOrientation(rotate(beam, 'y', 90))!.class).toBe('ALONG_Y');
    expect(measureOrientation(rotate(beam, 'y', 45))!.class).toBe('DIAGONAL');
    expect(orientationPlausible({ ifcClass: 'IfcBeam', measure: bx })).toBe(true);
  });

  it('a column is linear VERTICAL with tilt 90; on its side it is implausible', () => {
    const col = box(0, 1.5, 0, 0.4, 3, 0.4);
    const m = measureOrientation(col)!;
    expect(m.shape).toBe('linear');
    expect(m.class).toBe('VERTICAL');
    expect(m.tilt).toBe(90);
    expect(m.principalAxis).toBe('Z');
    expect(orientationPlausible({ ifcClass: 'IfcColumn', measure: m })).toBe(true);
    const side = measureOrientation(rotate(col, 'z', 90))!;
    expect(side.class).toBe('ALONG_X');
    expect(orientationPlausible({ ifcClass: 'IfcColumn', measure: side })).toBe(false);
    expect(orientationPlausible({ ifcClass: 'IfcBeam', measure: m })).toBe(false);
  });

  it('a cube-like piece of equipment is compact, HORIZONTAL', () => {
    const m = measureOrientation(box(0, 0.5, 0, 1, 1, 1))!;
    expect(m.shape).toBe('compact');
    expect(m.class).toBe('HORIZONTAL');
    expect(orientationPlausible({ ifcClass: 'IfcPump', measure: m })).toBe(true);
  });

  it('is weighted by area: a dense end does not decide the axis', () => {
    // a bar with 200 extra tiny triangles clustered at one end
    const bar = box(0, 0, 0, 10, 0.2, 0.2);
    const pos = Array.from(bar.position);
    const idx = Array.from(bar.index);
    for (let i = 0; i < 200; i++) {
      const base = pos.length / 3;
      pos.push(5, 0.1, 0.1, 5.0001, 0.1, 0.1, 5, 0.1001, 0.1);
      idx.push(base, base + 1, base + 2);
    }
    const m = measureOrientation({ position: new Float32Array(pos), index: new Uint32Array(idx) })!;
    expect(m.class).toBe('ALONG_X');
  });

  it('an upside-down door is not upright (from the placement axis) and implausible', () => {
    const door = box(0, 1.05, 0, 0.9, 2.1, 0.05);
    const ok = measureOrientation(door, { hasTop: true, localUp: [0, 0, 1] })!;
    expect(ok.upright).toBe(true);
    expect(orientationPlausible({ ifcClass: 'IfcDoor', measure: ok })).toBe(true);
    const down = measureOrientation(rotate(door, 'x', 180), { hasTop: true, localUp: [0, 0, -1] })!;
    expect(down.upright).toBe(false);
    expect(orientationPlausible({ ifcClass: 'IfcDoor', measure: down })).toBe(false);
    // a door lying flat is implausible even when upright is unknown
    const flat = measureOrientation(rotate(door, 'x', 90), { hasTop: true })!;
    expect(flat.class).toBe('HORIZONTAL');
    expect(orientationPlausible({ ifcClass: 'IfcDoor', measure: flat })).toBe(false);
  });

  it('upright from the geometry: a wide base under a narrow top is upright, flipped it is not', () => {
    const pedestal = merge(box(0, 0.1, 0, 2, 0.2, 2), box(0, 0.6, 0, 0.4, 0.8, 0.4));
    const up = measureOrientation(pedestal, { hasTop: true })!;
    expect(up.upright).toBe(true);
    const down = measureOrientation(rotate(pedestal, 'x', 180), { hasTop: true })!;
    expect(down.upright).toBe(false);
    expect(measureOrientation(pedestal)!.upright).toBeNull(); // not asked: no top
  });

  it('returns null for an empty or flat-degenerate mesh', () => {
    expect(measureOrientation({ position: new Float32Array(0) })).toBeNull();
    expect(measureOrientation({ position: new Float32Array([0, 0, 0, 1, 0, 0, 2, 0, 0]) })).toBeNull();
  });

  it('the table has nothing to say for a class it does not know, and any orientation is fine for pipes and roofs', () => {
    const m = measureOrientation(WALL_X())!;
    expect(orientationPlausible({ ifcClass: 'IfcWindow', measure: m })).toBe(true);
    expect(orientationPlausible({ ifcClass: 'IfcRoof', measure: m })).toBe(true);
    expect(orientationPlausible({ ifcClass: 'IfcPipeSegment', measure: m })).toBe(true);
    expect(orientationPlausible({ ifcClass: 'IfcBuildingElementProxy', measure: m })).toBeNull();
  });
});
