// The numeric shape descriptor (src/classify/geometryVector.ts): sides, volume, ratios, axis against up, plan direction, level, openings.
import { describe, expect, it } from 'vitest';
import { describeShape, meshVolumeArea, shapeLine, shapeText, shapeTokens } from '../src/classify/geometryVector';
import type { Box6, ShapeMesh } from '../src/classify/geometryVector';

/** A closed box mesh (12 triangles, outward winding) in the viewer frame (y up). */
function box(x0: number, y0: number, z0: number, x1: number, y1: number, z1: number): ShapeMesh {
  const p = [x0, y0, z0, x1, y0, z0, x1, y1, z0, x0, y1, z0, x0, y0, z1, x1, y0, z1, x1, y1, z1, x0, y1, z1];
  const index = [0, 2, 1, 0, 3, 2, 4, 5, 6, 4, 6, 7, 0, 1, 5, 0, 5, 4, 3, 7, 6, 3, 6, 2, 0, 4, 7, 0, 7, 3, 1, 2, 6, 1, 6, 5];
  return { position: p, index };
}
const bounds = (m: ShapeMesh): Box6 => {
  const p = m.position;
  const lo = [Infinity, Infinity, Infinity], hi = [-Infinity, -Infinity, -Infinity];
  for (let i = 0; i < p.length; i += 3) for (let k = 0; k < 3; k++) { lo[k] = Math.min(lo[k]!, p[i + k]!); hi[k] = Math.max(hi[k]!, p[i + k]!); }
  return [lo[0]!, lo[1]!, lo[2]!, hi[0]!, hi[1]!, hi[2]!];
};

describe('shape vector', () => {
  it('describes a wall: sorted sides, volume, surface, ratios, horizontal axis, level and openings', () => {
    const m = box(0, 3.1, 0, 4, 5.8, 0.2); // 4 m long along x, 2.7 m high, 0.2 m thick, bottom 0.1 above a storey at 3.0
    const v = describeShape({ bounds: bounds(m), mesh: m, storeyElevation: 3, openings: 2 })!;
    expect(v.dims.map((d) => Math.round(d * 100) / 100)).toEqual([4, 2.7, 0.2]);
    expect(v.volume).toBeCloseTo(4 * 2.7 * 0.2, 6);
    expect(v.area).toBeCloseTo(2 * (4 * 2.7 + 4 * 0.2 + 2.7 * 0.2), 6);
    expect(v.elongation).toBeCloseTo(4 / 2.7, 6);
    expect(v.flatness).toBeCloseTo(2.7 / 0.2, 6);
    expect(v.axisKind).toBe('horizontal');
    expect(v.axisFromUp).toBe(90);
    expect(v.planAngle).toBe(0); // along x = east
    expect(v.base).toBeCloseTo(0.1, 6);
    expect(v.top).toBeCloseTo(2.8, 6);
    expect(v.openings).toBe(2);
    const line = shapeLine(v);
    expect(line).toBe('4 x 2.7 x 0.2 m sorted; volume 2.16 m3; surface 24.3 m2; elongation 1.48; flatness 13.5; main axis horizontal (90 deg from up); plan angle 0 deg; base 0.1 m above storey, top 2.8 m; 2 openings');
    expect(line).not.toMatch(/\n/);
    expect(shapeTokens(line)).toBeLessThan(80);
  });

  it('finds a vertical column and a plan direction rotated in the IFC frame', () => {
    const col = box(1, 0, 1, 1.4, 3, 1.4);
    const v = describeShape({ bounds: bounds(col), mesh: col })!;
    expect(v.axisKind).toBe('vertical');
    expect(v.axisFromUp).toBeLessThan(5);
    expect(v.base).toBeNull();
    expect(shapeLine(v)).not.toMatch(/storey/);
    // a beam along the viewer's -z axis points north in IFC (Y = -z): 90 degrees in plan
    const beam = box(0, 3, 0, 0.3, 3.4, -5);
    const b = describeShape({ bounds: bounds(beam), mesh: beam })!;
    expect(b.axisKind).toBe('horizontal');
    expect(b.planAngle).toBe(90);
  });

  it('uses the box when there is no mesh, and measures an inclined element', () => {
    const v = describeShape({ bounds: [0, 0, 0, 1, 6, 0.2] })!;
    expect(v.axisKind).toBe('vertical');
    expect(v.volume).toBeNull();
    expect(v.area).toBeNull();
    expect(v.planAngle).toBe(0);
    // a ramp: points along x and y equally
    const ramp: ShapeMesh = { position: [0, 0, 0, 5, 5, 0, 0, 0, 0.3, 5, 5, 0.3, 0, 0.1, 0, 5, 5.1, 0.3] };
    expect(describeShape({ bounds: bounds(ramp), mesh: ramp })!.axisKind).toBe('inclined');
  });

  it('leaves out a volume that is not a closed solid, and nulls an empty box', () => {
    const open: ShapeMesh = { position: [0, 0, 0, 2, 0, 0, 0, 0, 2], index: [0, 1, 2] };
    expect(meshVolumeArea(open, 8)).toEqual({ volume: null, area: 2 });
    expect(describeShape({ bounds: [0, 0, 0, 0, 0, 0] })).toBeNull();
    expect(describeShape({ bounds: [0, 0, 0, NaN, 1, 1] })).toBeNull();
    expect(shapeLine(null)).toBe('');
    expect(shapeText({ bounds: [0, 0, 0, 1, 1, 1] })).toMatch(/^1 x 1 x 1 m sorted; elongation 1; flatness 1; main axis/);
  });

  it('gives equal text for equal shapes, rounded to the centimetre', () => {
    const a = shapeText({ bounds: [0, 0, 0, 2.001, 1, 0.5], storeyElevation: 0 });
    const b = shapeText({ bounds: [5, 0, 5, 7.001, 1, 5.5], storeyElevation: 0 });
    expect(a).toBe(b);
  });
});
