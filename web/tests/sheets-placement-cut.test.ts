import { describe, expect, it } from 'vitest';
import { chainSegments, cutElement, distCut, insideCut, polygonTouchesCut, sliceMesh, snapToCut, straighten } from '../src/sheets/sectionCut';
import type { PlanCut } from '../src/sheets/sectionCut';

/** A box as 12 triangles; vertex frame: x, z as the plan, y up (viewer frame), so the slice axis is 1. */
function box(x0: number, z0: number, x1: number, z1: number, y0: number, y1: number): { pos: number[]; idx: number[] } {
  const v = [[x0, y0, z0], [x1, y0, z0], [x1, y0, z1], [x0, y0, z1], [x0, y1, z0], [x1, y1, z0], [x1, y1, z1], [x0, y1, z1]];
  const f = [[0, 1, 2, 3], [4, 7, 6, 5], [0, 4, 5, 1], [1, 5, 6, 2], [2, 6, 7, 3], [3, 7, 4, 0]];
  const idx: number[] = [];
  for (const q of f) idx.push(q[0]!, q[1]!, q[2]!, q[0]!, q[2]!, q[3]!);
  return { pos: v.flat(), idx };
}

describe('slicing triangles', () => {
  it('a box cut through the middle gives its footprint as one closed outline of four corners', () => {
    const b = box(0, 0, 4, 0.3, 0, 3);
    const segs = sliceMesh(b.pos, b.idx, 1.2);
    const polys = chainSegments(segs);
    expect(polys).toHaveLength(1);
    expect(polys[0]!.closed).toBe(true);
    expect(polys[0]!.pts.length).toBe(8); // four corners: the triangle diagonals are merged away
    const e = cutElement('w', segs)!;
    expect(e.box).toEqual([0, 0, 4, 0.3]);
  });

  it('misses a box that lies below the plane or only touches it', () => {
    const b = box(0, 0, 1, 1, 0, 1);
    expect(sliceMesh(b.pos, b.idx, 1.2)).toHaveLength(0);
    expect(sliceMesh(b.pos, b.idx, 1)).toHaveLength(0); // the top face lies in the plane: not a cut
    expect(cutElement('x', [])).toBeNull();
  });

  it('works on a triangle soup without an index and on the IFC axis', () => {
    const b = box(0, 0, 2, 2, 0, 3);
    const soup: number[] = [];
    for (const i of b.idx) soup.push(b.pos[i * 3]!, b.pos[i * 3 + 1]!, b.pos[i * 3 + 2]!);
    expect(sliceMesh(soup, null, 1).length).toBe(sliceMesh(b.pos, b.idx, 1).length);
    // IFC frame: z up (axis 2): swap y and z of the viewer box
    const ifc: number[] = [];
    for (let i = 0; i < b.pos.length; i += 3) ifc.push(b.pos[i]!, b.pos[i + 2]!, b.pos[i + 1]!);
    expect(sliceMesh(ifc, b.idx, 1, 2).length).toBe(sliceMesh(b.pos, b.idx, 1, 1).length);
  });

  it('straightens runs and keeps real corners', () => {
    expect(straighten([0, 0, 1, 0, 2, 0, 2, 1, 0, 1], true)).toEqual([0, 0, 2, 0, 2, 1, 0, 1]);
  });
});

describe('queries on a cut', () => {
  const wall = cutElement('wall', sliceMesh(box(0, 0, 4, 0.3, 0, 3).pos, box(0, 0, 4, 0.3, 0, 3).idx, 1.2))!;
  const col = cutElement('col', sliceMesh(box(5, 5, 5.4, 5.4, 0, 3).pos, box(5, 5, 5.4, 5.4, 0, 3).idx, 1.2))!;
  const cut: PlanCut = { z: 1.2, elements: [wall, col] };

  it('knows what a point is inside of, and how far from', () => {
    expect(insideCut(wall, 2, 0.15)).toBe(true);
    expect(insideCut(wall, 2, 0.5)).toBe(false);
    expect(distCut(wall, 2, 0.15)).toBe(0);
    expect(distCut(wall, 2, 0.5)).toBeCloseTo(0.2, 9);
  });

  it('knows when a polygon touches an outline: over it, around it, across it, and not', () => {
    const rect = (x0: number, y0: number, x1: number, y1: number): number[] => [x0, y0, x1, y0, x1, y1, x0, y1];
    expect(polygonTouchesCut(rect(1, -0.2, 2, 0.5), wall)).toBe(true); // over the wall
    expect(polygonTouchesCut(rect(-1, -1, 6, 1), wall)).toBe(true); // around it
    expect(polygonTouchesCut(rect(2, 0.1, 2.1, 0.2), wall)).toBe(true); // inside it
    expect(polygonTouchesCut(rect(1, 1, 2, 2), wall)).toBe(false);
    expect(polygonTouchesCut(rect(1, 1, 2, 2), col)).toBe(false);
  });

  it('snaps to the corner first, then to an edge', () => {
    const c = snapToCut(cut, 4.02, 0.28, 0.1)!;
    expect(c.kind).toBe('corner');
    expect(c.point).toEqual([4, 0.3]);
    expect(c.guid).toBe('wall');
    const e = snapToCut(cut, 2, 0.33, 0.1)!;
    expect(e.kind).toBe('edge');
    expect(e.point[0]).toBeCloseTo(2, 9);
    expect(e.point[1]).toBeCloseTo(0.3, 9);
    expect(snapToCut(cut, 9, 9, 0.1)).toBeNull();
    expect(snapToCut(null, 0, 0, 1)).toBeNull();
  });
});
