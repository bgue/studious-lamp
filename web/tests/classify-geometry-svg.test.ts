// The SVG geometry that goes into the state as text (src/classify/geometrySvg.ts): outlines, circles and rectangles, the clipping to the context box, the
// neighbour cap, the token budget, determinism and the rounding of the numbers. Pure: synthetic meshes, no browser.

import { describe, expect, it } from 'vitest';
import { GEOMETRY_BUDGET_TOKENS, MAX_GEOMETRY_NEIGHBOURS, buildGeometry, clipPolygon, convexHull, estimateTokens, simplifyPolygon } from '../src/classify/geometrySvg';
import type { GeoInfo, GeoMesh, GeoSource } from '../src/classify/geometrySvg';
import type { Bounds6 } from '../src/classify/thumbs';

/** A closed box mesh (viewer axes, y up). */
function boxMesh(b: Bounds6): GeoMesh {
  const [x0, y0, z0, x1, y1, z1] = b;
  const p = [x0, y0, z0, x1, y0, z0, x1, y1, z0, x0, y1, z0, x0, y0, z1, x1, y0, z1, x1, y1, z1, x0, y1, z1];
  return { position: p, index: [0, 2, 1, 0, 3, 2, 4, 5, 6, 4, 6, 7, 0, 1, 5, 0, 5, 4, 3, 7, 6, 3, 6, 2, 0, 4, 7, 0, 7, 3, 1, 2, 6, 1, 6, 5] };
}
/** A cylinder along the viewer's y axis (IFC Z), n sides. */
function cylinder(cx: number, cz: number, r: number, y0: number, y1: number, n = 24): { mesh: GeoMesh; bounds: Bounds6 } {
  const p: number[] = [];
  for (let k = 0; k < n; k++) { const a = (k / n) * Math.PI * 2; p.push(cx + Math.cos(a) * r, y0, cz + Math.sin(a) * r, cx + Math.cos(a) * r, y1, cz + Math.sin(a) * r); }
  return { mesh: { position: p, index: [] }, bounds: [cx - r, y0, cz - r, cx + r, y1, cz + r] };
}

function source(items: Array<{ bounds: Bounds6; mesh: GeoMesh; info: GeoInfo }>): GeoSource {
  return { bounds: (i) => items[i]?.bounds ?? null, mesh: (i) => items[i]?.mesh ?? null, ids: () => items.map((_, i) => i), info: (i) => items[i]!.info };
}
const item = (b: Bounds6, info: GeoInfo) => ({ bounds: b, mesh: boxMesh(b), info });

describe('the building blocks', () => {
  it('makes the convex hull of points, and simplifies a polygon', () => {
    const hull = convexHull([[0, 0], [1, 0], [1, 1], [0, 1], [0.5, 0.5], [0.5, 0]]);
    expect(hull).toHaveLength(4);
    const round: Array<[number, number]> = Array.from({ length: 40 }, (_, k) => [Math.cos((k / 40) * 6.283), Math.sin((k / 40) * 6.283)]);
    const s = simplifyPolygon(round, 0.05);
    expect(s.length).toBeLessThan(25);
    expect(s.length).toBeGreaterThan(5);
  });
  it('clips a polygon to a rectangle', () => {
    const c = clipPolygon([[-1, -1], [3, -1], [3, 3], [-1, 3]], [0, 0, 2, 2]);
    expect(c.every((p) => p[0] >= 0 && p[0] <= 2 && p[1] >= 0 && p[1] <= 2)).toBe(true);
    expect(c).toHaveLength(4);
    expect(clipPolygon([[5, 5], [6, 5], [6, 6]], [0, 0, 2, 2])).toEqual([]);
  });
});

describe('the isolated element', () => {
  const pipe = cylinder(10, -20, 0.135, 0, 2);
  const src = source([{ bounds: pipe.bounds, mesh: pipe.mesh, info: { ifcClass: 'IfcPipeSegment', predefined: 'RIGIDSEGMENT', tag: 'P-1' } }]);
  const g = buildGeometry(src, 0, { context: false, margin: 25 });
  it('puts the class, type and size in attributes and starts from the minimum corner', () => {
    expect(g.svg).toContain("data-class='IfcPipeSegment'");
    expect(g.svg).toContain("data-type='RIGIDSEGMENT'");
    expect(g.svg).toContain("data-size='0.27x0.27x2'");
    expect(g.svg).toContain("viewBox='0 0 0.27 0.27'"); // plan
    expect(g.svg).toContain("viewBox='0 0 0.27 2'"); // the elevation: along the longer horizontal axis, then the height
    expect(g.views.map((v) => v.name)).toEqual(['plan', 'elevation']);
    expect(g.legend).toMatch(/^Geometry as SVG, metres, plan then elevation/);
  });
  it('draws a round pipe seen from above as a circle and its side as a rectangle', () => {
    expect(g.svg).toMatch(/<circle cx='0\.14' cy='0\.14' r='0\.14'\/>|<circle cx='0\.13' cy='0\.13' r='0\.13'\/>/);
    expect(g.views[1]!.svg).toMatch(/<rect x='0' y='0' width='0\.27' height='2'\/>/);
  });
  it('is the same text every time, with at most 2 decimals and no wild numbers', () => {
    expect(buildGeometry(src, 0, { context: false, margin: 25 }).svg).toBe(g.svg);
    for (const m of g.svg.matchAll(/-?\d+\.\d+/g)) expect(m[0]!.split('.')[1]!.length).toBeLessThanOrEqual(2);
    expect(g.tokens).toBe(estimateTokens(g.legend) + estimateTokens(g.svg));
    expect(g.tokens).toBeLessThan(GEOMETRY_BUDGET_TOKENS);
  });
  it('uses single quotes only, so the JSON state needs no escape', () => {
    expect(g.svg).not.toContain('"');
    expect(JSON.stringify(g.svg).length).toBe(g.svg.length + 2 + (g.svg.split('\n').length - 1)); // only the newlines are escaped
  });
  it('refuses an element without geometry', () => {
    expect(() => buildGeometry(source([]), 0, { context: false, margin: 25 })).toThrow(/no geometry/);
  });
});

describe('the element in its bounding box', () => {
  const target: Bounds6 = [0, 0, 0, 2, 1, 1]; // viewer x 2 long, y 1 high, z 1 deep -> IFC 2 x 1 x 1
  const near = (k: number): Bounds6 => [1.5 + k * 0.01, 0, 0.2, 3.5 + k * 0.01, 0.8, 0.8]; // sticks out of the box on the +x side
  it('draws the neighbours clipped to the box, marks the target and leaves out far and tiny elements', () => {
    const items = [
      item(target, { ifcClass: 'IfcPump', tag: 'P-101A' }),
      item(near(0), { ifcClass: 'IfcPipeSegment', tag: 'L-1' }),
      item([40, 0, 0, 41, 1, 1], { ifcClass: 'IfcWall' }), // far
      item([1, 0, 0.5, 1.01, 0.01, 0.51], { ifcClass: 'IfcSensor' }), // tiny
    ];
    const g = buildGeometry(source(items), 0, { context: true, margin: 25 });
    expect(g.neighbours).toBe(1);
    expect(g.views.map((v) => v.name)).toEqual(['plan', 'elevation', 'context plan', 'context elevation']);
    const ctx = g.views[2]!.svg;
    expect(ctx).toContain("<g id='target'>");
    expect(ctx).toContain("<g data-class='IfcPipeSegment' data-tag='L-1'>");
    expect(ctx).not.toContain('IfcWall');
    expect(ctx).not.toContain('IfcSensor');
    // viewBox is the box: 2 + 2 * 0.5 by 1 + 2 * 0.5 (the margin is 25 % of 2 m = 0.5 m)
    expect(ctx).toContain("viewBox='0 0 3 2'");
    // every coordinate lies inside the box
    for (const m of ctx.matchAll(/points='([^']+)'/g)) for (const pt of m[1]!.split(' ')) { const [x, y] = pt.split(',').map(Number); expect(x!).toBeGreaterThanOrEqual(0); expect(x!).toBeLessThanOrEqual(3); expect(y!).toBeGreaterThanOrEqual(0); expect(y!).toBeLessThanOrEqual(2); }
    for (const m of ctx.matchAll(/<rect [^>]*x='([\d.]+)' y='([\d.]+)' width='([\d.]+)' height='([\d.]+)'/g)) { expect(+m[1]! + +m[3]!).toBeLessThanOrEqual(3.0001); expect(+m[2]! + +m[4]!).toBeLessThanOrEqual(2.0001); }
  });
  it('gives the class and tag of a neighbour, never a classification result', () => {
    const g = buildGeometry(source([item(target, { ifcClass: 'IfcPump', tag: 'P-1' }), item(near(0), { ifcClass: 'IfcPipeSegment', tag: 'L-1' })]), 0, { context: true, margin: 25 });
    expect(g.svg).not.toMatch(/discipline|MEC|PLB|classif/i);
  });
  it('keeps at most 25 neighbours, the nearest first', () => {
    const items = [item(target, { ifcClass: 'IfcPump' })];
    for (let k = 0; k < 60; k++) items.push(item([0.1 + k * 0.02, 0.1, 0.1, 0.6 + k * 0.02, 0.6, 0.6], { ifcClass: 'IfcPipeSegment', tag: `T${k}` }));
    const g = buildGeometry(source(items), 0, { context: true, margin: 25, budget: 100000 });
    expect(g.neighbours).toBe(MAX_GEOMETRY_NEIGHBOURS);
    expect(g.views[2]!.svg.match(/data-tag=/g)).toHaveLength(MAX_GEOMETRY_NEIGHBOURS);
    // all overlap the element, so the nearest are the ones whose centres are nearest to its centre (T32 is the nearest); the far ends are left out
    expect(g.views[2]!.svg).toContain("data-tag='T32'");
    expect(g.views[2]!.svg).not.toContain("data-tag='T0'");
    expect(g.views[2]!.svg).not.toContain("data-tag='T59'");
  });
  it('keeps the token budget by dropping neighbours and simplifying harder', () => {
    const items = [item(target, { ifcClass: 'IfcPump' })];
    for (let k = 0; k < 40; k++) { const c = cylinder(0.3 + k * 0.03, 0.5, 0.2 + (k % 3) * 0.02, 0, 1, 40); items.push({ bounds: c.bounds, mesh: c.mesh, info: { ifcClass: 'IfcPipeSegment', tag: `Tag-${k}` } }); }
    const loose = buildGeometry(source(items), 0, { context: true, margin: 25, budget: 100000 });
    const tight = buildGeometry(source(items), 0, { context: true, margin: 25, budget: 600 });
    expect(loose.tokens).toBeGreaterThan(600);
    expect(tight.tokens).toBeLessThanOrEqual(600);
    expect(tight.neighbours).toBeLessThan(loose.neighbours);
    expect(buildGeometry(source(items), 0, { context: true, margin: 25, budget: 600 }).svg).toBe(tight.svg); // deterministic
    expect(buildGeometry(source(items), 0, { context: true, margin: 25 }).tokens).toBeLessThanOrEqual(GEOMETRY_BUDGET_TOKENS);
  });
});
