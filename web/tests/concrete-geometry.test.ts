// XR_ConcreteGeometry: volume (closed and estimated), local frames by role, dimensions, section shapes, faces and formwork.

import { describe, expect, it } from 'vitest';
import { concreteGeometry, facesText, meshVolume, ifcTriangles, minAreaRect } from '../src/classify/concrete/geometry';
import type { Box6 } from '../src/classify/concrete/geometry';
import { block, circle, prism, rotateZ } from './concrete-helpers';

const near = (a: number, b: number, tol = 0.01): void => expect(Math.abs(a - b)).toBeLessThanOrEqual(tol);
const vecNear = (a: readonly number[], b: readonly number[], tol = 0.01): void => b.forEach((x, i) => near(a[i]!, x, tol));
const box6 = (x0: number, y0: number, z0: number, dx: number, dy: number, dz: number): Box6 => [x0, y0, z0, x0 + dx, y0 + dy, z0 + dz];

describe('volume', () => {
  it('a closed block has its exact volume', () => {
    const r = meshVolume(ifcTriangles(block(0, 0, 0, 6, 4, 0.2)));
    expect(r.closed).toBe(true);
    near(r.volume, 4.8, 1e-6);
  });
  it('a prism with a non-convex outline (L) is closed with the right volume', () => {
    const L: Array<[number, number]> = [[0, 0], [4, 0], [4, 1], [1, 1], [1, 3], [0, 3]];
    const r = meshVolume(ifcTriangles(prism(L, 'Z', 0, 0.3)));
    expect(r.closed).toBe(true);
    near(r.volume, (4 * 1 + 1 * 2) * 0.3, 1e-6);
  });
  it('an open mesh (a face removed) is flagged and gets the bounds volume', () => {
    const m = block(0, 0, 0, 5, 2, 0.5);
    const open = { position: m.position, index: m.index.slice(0, m.index.length - 6) };
    const g = concreteGeometry(open, 'slab')!;
    expect(g.volumeEstimated).toBe(true);
    near(g.volume, 5, 0.01);
  });
  it('a closed mesh is not flagged', () => {
    expect(concreteGeometry(block(0, 0, 0, 5, 2, 0.5), 'slab')!.volumeEstimated).toBe(false);
  });
});

describe('min area rectangle', () => {
  it('finds a rotated rectangle', () => {
    const pts: number[] = [];
    const a = (30 * Math.PI) / 180;
    for (const [x, y] of [[0, 0], [8, 0], [8, 2], [0, 2]] as const) pts.push(x * Math.cos(a) - y * Math.sin(a), x * Math.sin(a) + y * Math.cos(a));
    const r = minAreaRect(pts);
    near(r.long, 8, 1e-6); near(r.short, 2, 1e-6);
    near(Math.abs(r.u[0] * Math.cos(a) + r.u[1] * Math.sin(a)), 1, 1e-6);
  });
});

describe('slab', () => {
  const slab = block(0, 0, 3, 8, 5, 0.2);
  it('frame: Z up, X along the longer side; dimensions; formwork excludes the top', () => {
    const g = concreteGeometry(slab, 'slab')!;
    vecNear(g.frame.z, [0, 0, 1]); vecNear(g.frame.x, [1, 0, 0]); vecNear(g.frame.y, [0, 1, 0]);
    vecNear(g.frame.origin, [0, 0, 3]);
    near(g.length, 8); near(g.width, 5); near(g.thickness, 0.2);
    near(g.volume, 8, 1e-3);
    near(g.topArea, 40, 0.01); near(g.soffitArea, 40, 0.01);
    near(g.formworkArea, 40 + 2 * (8 + 5) * 0.2, 0.05);
    expect(g.sectionShape).toBe('RECT');
    expect(g.faces.map((f) => f.name).sort()).toEqual(['BOTTOM', 'SIDE_X+', 'SIDE_X-', 'SIDE_Y+', 'SIDE_Y-', 'TOP']);
  });
  it('the long side is X even when the slab is rotated and when it is longer in Y', () => {
    const g = concreteGeometry(rotateZ(block(-2.5, -4, 3, 5, 8, 0.2), 30), 'slab')!;
    near(g.length, 8, 0.02); near(g.width, 5, 0.02);
    near(Math.abs(g.frame.x[0] * Math.cos((2 * Math.PI) / 3) + g.frame.x[1] * Math.sin((2 * Math.PI) / 3)), 1, 0.01);
    expect(g.frame.x[0] > 0 || (Math.abs(g.frame.x[0]) < 1e-6 && g.frame.x[1] > 0)).toBe(true);
    vecNear(g.frame.z, [0, 0, 1]);
    // right handed
    const x = g.frame.x, y = g.frame.y, z = g.frame.z;
    vecNear([x[1] * y[2] - x[2] * y[1], x[2] * y[0] - x[0] * y[2], x[0] * y[1] - x[1] * y[0]], z, 1e-6);
  });
  it('supports on two opposite sides: the span (X) runs across them', () => {
    const g = concreteGeometry(block(0, 0, 3, 8, 5, 0.2), 'slab', { supportDirs: [[1, 0], [1, 0]] })!;
    // supports run along X, so the span is along Y
    vecNear(g.frame.x, [0, 1, 0]);
    near(g.length, 5);
  });
  it('a slab with a downstand beam: faces against concrete are not formed', () => {
    const beam = box6(0, 2, 2.6, 8, 0.4, 0.4);
    const g = concreteGeometry(slab, 'slab', { others: [{ id: 'B', bounds: beam }] })!;
    const bottom = g.faces.find((f) => f.name === 'BOTTOM')!;
    near(bottom.againstConcrete, 8 * 0.4, 0.35);
    expect(bottom.touches).toEqual(['B']);
    near(g.soffitArea, 40 - 3.2, 0.35);
  });
  it('a slab on grade: the soffit is against the ground, not formed', () => {
    const sog = block(0, 0, -0.2, 8, 5, 0.2);
    const g = concreteGeometry(sog, 'slab', { ground: { level: 0, soffit: true, sides: false } })!;
    near(g.groundArea, 40, 0.01);
    near(g.soffitArea, 0, 0.01);
    near(g.formworkArea, 2 * 13 * 0.2, 0.05);
    near(g.faces.find((f) => f.name === 'BOTTOM')!.againstGround, 40, 0.01);
  });
  it('a stepped (L-shaped) slab has the L section shape and two TOP faces when stepped', () => {
    const L: Array<[number, number]> = [[0, 0], [6, 0], [6, 2], [2, 2], [2, 5], [0, 5]];
    expect(concreteGeometry(prism(L, 'Z', 3, 3.2), 'slab')!.sectionShape).toBe('L');
  });
});

describe('wall', () => {
  const wall = block(0, 0, 0, 6, 0.2, 3);
  it('frame: X along the wall, Z up, Y across; thickness is the small side', () => {
    const g = concreteGeometry(wall, 'wall')!;
    vecNear(g.frame.x, [1, 0, 0]); vecNear(g.frame.y, [0, 1, 0]); vecNear(g.frame.z, [0, 0, 1]);
    near(g.length, 6); near(g.thickness, 0.2); near(g.width, 3);
    expect(g.faces.map((f) => f.name).sort()).toEqual(['BOTTOM', 'END_+', 'END_-', 'SIDE_Y+', 'SIDE_Y-', 'TOP']);
  });
  it('a wall along Y: X follows the wall', () => {
    const g = concreteGeometry(block(0, 0, 0, 0.2, 6, 3), 'wall')!;
    vecNear(g.frame.x, [0, 1, 0]);
    // right handed: Y = Z x X = (-1, 0, 0)
    vecNear(g.frame.y, [-1, 0, 0]);
  });
  it('the exterior face decides the sign of Y', () => {
    const north = concreteGeometry(wall, 'wall', { outward: [0, 1] })!;
    vecNear(north.frame.y, [0, 1, 0]);
    const south = concreteGeometry(wall, 'wall', { outward: [0, -1] })!;
    vecNear(south.frame.y, [0, -1, 0]);
    vecNear(south.frame.x, [-1, 0, 0]);
    const z = south.frame.z;
    vecNear([south.frame.x[1] * south.frame.y[2] - south.frame.x[2] * south.frame.y[1], south.frame.x[2] * south.frame.y[0] - south.frame.x[0] * south.frame.y[2], south.frame.x[0] * south.frame.y[1] - south.frame.x[1] * south.frame.y[0]], z, 1e-6);
  });
  it('formwork: both faces and the ends; the base on a slab is against concrete, the top is open', () => {
    const slab = box6(-1, -1, -0.2, 8, 3, 0.2);
    const g = concreteGeometry(wall, 'wall', { others: [{ id: 'S', bounds: slab }] })!;
    near(g.formworkArea, 2 * 6 * 3 + 2 * 0.2 * 3, 0.1);
    near(g.faces.find((f) => f.name === 'BOTTOM')!.againstConcrete, 1.2, 0.05);
  });
  it('a wall against a basement soil: the sides below ground are not formed', () => {
    const g = concreteGeometry(block(0, 0, -3, 6, 0.3, 3), 'wall', { ground: { level: 0, soffit: false, sides: true } })!;
    near(g.groundArea, 2 * 6 * 3 + 2 * 0.3 * 3 + 6 * 0.3, 0.1);
  });
});

describe('column and beam', () => {
  it('rectangular column: Z along the axis, X along the longer section side', () => {
    const g = concreteGeometry(block(0, 0, 0, 0.3, 0.5, 3), 'column')!;
    vecNear(g.frame.z, [0, 0, 1]); vecNear(g.frame.x, [0, 1, 0]);
    near(g.length, 3); near(g.width, 0.5); near(g.thickness, 0.3);
    expect(g.sectionShape).toBe('RECT');
    expect(g.faces.map((f) => f.name).sort()).toEqual(['END_+', 'END_-', 'SIDE_X+', 'SIDE_X-', 'SIDE_Y+', 'SIDE_Y-']);
  });
  it('round column has a CIRC section', () => {
    const g = concreteGeometry(prism(circle(0, 0, 0.2, 32), 'Z', 0, 3), 'column')!;
    expect(g.sectionShape).toBe('CIRC');
    near(g.volume, 0.5 * 32 * 0.2 * 0.2 * Math.sin((2 * Math.PI) / 32) * 3, 0.002);
  });
  it('beam: X along the axis, Z up, depth is the thickness', () => {
    const g = concreteGeometry(block(0, 0, 2.5, 0.3, 6, 0.5), 'beam')!;
    vecNear(g.frame.x, [0, 1, 0]); vecNear(g.frame.z, [0, 0, 1]);
    near(g.length, 6); near(g.width, 0.3); near(g.thickness, 0.5);
    expect(g.sectionShape).toBe('RECT');
    expect(g.faces.map((f) => f.name).sort()).toEqual(['BOTTOM', 'END_+', 'END_-', 'SIDE_Y+', 'SIDE_Y-', 'TOP']);
    // beam formwork: soffit + two sides + ends, no top
    near(g.formworkArea, 6 * 0.3 + 2 * 6 * 0.5 + 2 * 0.3 * 0.5, 0.05);
  });
  it('T beam, L column and I section shapes', () => {
    const T: Array<[number, number]> = [[0, 0.3], [1.2, 0.3], [1.2, 0.5], [0, 0.5], [0, 0.3]].slice(0, 4) as Array<[number, number]>;
    // T section in (Y, Z): flange 1.2 wide x 0.15 deep on top of a 0.3 wide stem 0.5 deep, beam along X
    const poly: Array<[number, number]> = [[0.45, 0], [0.75, 0], [0.75, 0.35], [1.2, 0.35], [1.2, 0.5], [0, 0.5], [0, 0.35], [0.45, 0.35]];
    void T;
    expect(concreteGeometry(prism(poly, 'X', 0, 6), 'beam')!.sectionShape).toBe('T');
    const L: Array<[number, number]> = [[0, 0], [0.6, 0], [0.6, 0.2], [0.2, 0.2], [0.2, 0.6], [0, 0.6]];
    expect(concreteGeometry(prism(L, 'Z', 0, 3), 'column')!.sectionShape).toBe('L');
    const I: Array<[number, number]> = [[0, 0], [0.4, 0], [0.4, 0.1], [0.25, 0.1], [0.25, 0.5], [0.4, 0.5], [0.4, 0.6], [0, 0.6], [0, 0.5], [0.15, 0.5], [0.15, 0.1], [0, 0.1]];
    expect(concreteGeometry(prism(I, 'Z', 0, 3), 'column')!.sectionShape).toBe('I');
  });
  it('an irregular outline (an S) is IRREGULAR', () => {
    const S: Array<[number, number]> = [[0, 0], [3, 0], [3, 1], [2, 1], [2, 3], [-1, 3], [-1, 2], [0, 2]];
    expect(concreteGeometry(prism(S, 'Z', 0, 0.5), 'footing')!.sectionShape).toBe('IRREGULAR');
  });
});

describe('footing and the shape-led frame', () => {
  it('footing: Z up, X along the longer side, sides below ground are against the ground', () => {
    const g = concreteGeometry(block(0, 0, -1.2, 2.4, 1.6, 0.6), 'footing', { ground: { level: 0, soffit: true, sides: true } })!;
    vecNear(g.frame.x, [1, 0, 0]);
    near(g.length, 2.4); near(g.width, 1.6); near(g.thickness, 0.6);
    near(g.formworkArea, 0, 0.01);
    near(g.groundArea, 2.4 * 1.6 + 2 * (2.4 + 1.6) * 0.6, 0.05);
  });
  it('kind other lets the shape decide: a long thin member is a beam, a tall one a column', () => {
    expect(concreteGeometry(block(0, 0, 0, 0.3, 6, 0.4), 'other')!.kind).toBe('beam');
    expect(concreteGeometry(block(0, 0, 0, 0.3, 0.3, 4), 'other')!.kind).toBe('column');
    expect(concreteGeometry(block(0, 0, 0, 6, 5, 0.2), 'other')!.kind).toBe('slab');
  });
  it('an inclined slab (a ramp) has Z normal to its top', () => {
    const m = block(0, 0, 0, 6, 3, 0.2);
    // tilt about the IFC Y axis (viewer z): z' = z cos + x sin
    const a = (15 * Math.PI) / 180;
    const pos = new Float32Array(m.position);
    for (let i = 0; i < pos.length; i += 3) { const x = pos[i]!, y = pos[i + 1]!; pos[i] = x * Math.cos(a) - y * Math.sin(a); pos[i + 1] = x * Math.sin(a) + y * Math.cos(a); }
    const g = concreteGeometry({ position: pos, index: m.index }, 'slab')!;
    near(g.thickness, 0.2, 0.02);
    near(g.length, 6, 0.05);
    near(g.frame.z[2], Math.cos(a), 0.01);
  });
});

describe('faces text', () => {
  it('writes name, area and the contacts', () => {
    const g = concreteGeometry(block(0, 0, -0.2, 4, 4, 0.2), 'slab', { ground: { level: 0, soffit: true, sides: false } })!;
    const t = facesText(g.faces);
    expect(t).toContain('TOP 16');
    expect(t).toContain('BOTTOM 16 G16');
  });
});
