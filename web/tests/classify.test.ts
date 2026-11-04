import { describe, expect, it } from 'vitest';
import { DEFAULT_CLASSIFICATION, type ClassificationSettings } from '../src/types';
import { bufferRadius, classify, connectedRun, crossSection, ease } from '../src/algo';
import { makeScene, type ElementSpec } from './boxProvider';
import { Box3, Vector3 } from 'three';

const duct = (x0: number, x1: number, storey = 0): ElementSpec =>
  ({ cls: 'IfcDuctSegment', box: [x0, 0, 0, x1, 0.3, 0.3], storey });
const slabAt = (y: number, storey: number | null, x = 0): ElementSpec =>
  ({ cls: 'IfcSlab', box: [x, y, -5, x + 1, y + 0.2, 5], storey });

describe('helpers', () => {
  it('crossSection is the second-largest extent', () => {
    expect(crossSection(new Box3(new Vector3(0, 0, 0), new Vector3(8, 0.3, 0.6)))).toBeCloseTo(0.6);
    expect(crossSection(new Box3(new Vector3(0, 0, 0), new Vector3(0.6, 8, 0.3)))).toBeCloseTo(0.6);
  });
  it('ease is smoothstep', () => {
    expect(ease(0)).toBe(0);
    expect(ease(1)).toBe(1);
    expect(ease(0.5)).toBeCloseTo(0.5);
  });
});

describe('storey band', () => {
  const storeys = [0, 1, 2, 3].map((id) => ({ id, name: `L${id}`, elevation: id * 3 }));
  // focus on storey 1; slabs far enough away that only the storey filter decides membership
  const { model, geometry } = makeScene(
    [
      duct(0, 4, 1),
      slabAt(20, 0), // adjacent below
      slabAt(21, 1),
      slabAt(22, 2), // adjacent above
      slabAt(23, 3), // two away
      slabAt(24, null), // no storey: always eligible
    ],
    { storeys },
  );
  const inContext = (c: ReturnType<typeof classify>, id: number) =>
    c.host.has(id) || c.near.has(id) || c.far.has(id);

  it('band 1 keeps adjacent storeys and storey-less elements', () => {
    const c = classify(model, geometry, [0], { ...DEFAULT_CLASSIFICATION, storeyBand: 1 });
    expect([1, 2, 3, 5].every((id) => inContext(c, id))).toBe(true);
    expect(inContext(c, 4)).toBe(false);
  });
  it('band 0 keeps only the focus storey (plus storey null)', () => {
    const c = classify(model, geometry, [0], { ...DEFAULT_CLASSIFICATION, storeyBand: 0 });
    expect([2, 5].every((id) => inContext(c, id))).toBe(true);
    expect([1, 3, 4].some((id) => inContext(c, id))).toBe(false);
  });
  it('band 2 reaches two storeys', () => {
    const c = classify(model, geometry, [0], { ...DEFAULT_CLASSIFICATION, storeyBand: 2 });
    expect(inContext(c, 4)).toBe(true);
  });
  it('storey filter is ignored when no focus element has a storey', () => {
    const s = makeScene([{ ...duct(0, 4), storey: null }, slabAt(20, 3)], { storeys });
    const c = classify(s.model, s.geometry, [0], { ...DEFAULT_CLASSIFICATION, storeyBand: 0 });
    expect(c.far.has(1)).toBe(true);
  });
  it('adjacency follows elevation order, not id arithmetic', () => {
    const s = makeScene([duct(0, 4, 10), slabAt(20, 30), slabAt(21, 50)], {
      storeys: [
        { id: 10, name: 'a', elevation: 0 },
        { id: 30, name: 'b', elevation: 3 },
        { id: 50, name: 'c', elevation: 6 },
      ],
    });
    const c = classify(s.model, s.geometry, [0], { ...DEFAULT_CLASSIFICATION, storeyBand: 1 });
    expect(c.far.has(1)).toBe(true);
    expect(c.far.has(2)).toBe(false);
  });
});

describe('ConnectedRun', () => {
  const pipe = (x0: number, x1: number): ElementSpec => ({ cls: 'IfcPipeSegment', box: [x0, 0, 0, x1, 0.1, 0.1] });
  const specs: ElementSpec[] = [
    duct(0, 2), // 0
    duct(2, 4), // 1  port 0-1
    duct(4, 6), // 2  port 1-2
    duct(20, 22), // 3  system with 0
    pipe(40, 42), // 4  unrelated
    { cls: 'IfcAirTerminalBox', box: [6, 0, 0, 7, 1, 1] }, // 5 not a focus class, joined to 2
    duct(7, 9), // 6 only reachable through 5
    { cls: 'IfcSlab', box: [100, 0, 0, 101, 1, 1] }, // 7
  ];
  const { model } = makeScene(specs, {
    ports: [
      [0, 1],
      [2, 1],
      [2, 5],
      [5, 6],
    ],
    systems: [{ name: 'S', elements: [0, 3, 7] }],
  });
  const fc = new Set(DEFAULT_CLASSIFICATION.focusClasses);

  it('follows ports in either direction, transitively', () => {
    expect([...connectedRun(model, [2], fc)].sort()).toEqual([0, 1, 2]);
  });
  it('adds every focus-class member of a system containing a selected element, then follows ports from them', () => {
    expect([...connectedRun(model, [3], fc)].sort()).toEqual([0, 1, 2, 3]);
    expect([...connectedRun(model, [0], fc)].sort()).toEqual([0, 1, 2, 3]);
  });
  it('does not walk through non-focus classes and ignores non-focus selections', () => {
    const run = connectedRun(model, [2], fc);
    expect(run.has(5)).toBe(false);
    expect(run.has(6)).toBe(false);
    expect(run.has(7)).toBe(false);
    expect(connectedRun(model, [7, 5], fc).size).toBe(0);
  });
  it('unrelated element stays out', () => {
    expect(connectedRun(model, [4], fc)).toEqual(new Set([4]));
  });
});

describe('Host: hosts relation vs geometric fallback', () => {
  const specs: ElementSpec[] = [
    { cls: 'IfcDuctSegment', box: [0, 0, 0, 4, 0.3, 0.3] }, // 0 focus
    { cls: 'IfcSlab', box: [10, 0, 0, 11, 1, 1] }, // 1 declared host but nowhere near
    { cls: 'IfcWall', box: [1, -1, -1, 1.2, 1, 1] }, // 2 crosses the duct, undeclared
    { cls: 'IfcWall', box: [1.5, 0.5, 0, 1.7, 1.5, 1] }, // 3 bounds-near but no overlap
  ];
  it('relations.hosts wins without any geometry call for that pair', () => {
    const s = makeScene([...specs], { hosts: [[0, 1]] });
    const c = classify(s.model, s.geometry, [0]);
    expect(c.host.has(1)).toBe(true);
    expect(c.proximityWeight.get(1)).toBe(1);
    expect(s.geometry.callPairs.some(([, , b]) => b === 1)).toBe(false);
  });
  it('fallback: overlapping bounds plus intersects', () => {
    const s = makeScene([...specs]);
    const c = classify(s.model, s.geometry, [0]);
    expect(c.host.has(2)).toBe(true);
    expect(c.host.has(1)).toBe(false);
    expect(c.near.has(3)).toBe(true);
    expect(c.host.has(3)).toBe(false);
  });
  it('overlapping bounds but meshes that do not intersect fall through to Near', () => {
    const s = makeScene([...specs]);
    s.geometry.intersects = () => false;
    s.geometry.surfaceDistance = () => 0.1;
    const c = classify(s.model, s.geometry, [0]);
    expect(c.host.has(2)).toBe(false);
    expect(c.near.has(2)).toBe(true);
    expect(c.proximityWeight.get(2)!).toBeGreaterThan(0.5);
  });
  it('a Host is never also Near, and the buckets are disjoint', () => {
    const s = makeScene([...specs], { hosts: [[0, 3]] });
    const c = classify(s.model, s.geometry, [0]);
    const all = [...c.host, ...c.near, ...c.far];
    expect(new Set(all).size).toBe(all.length);
    expect(c.host.has(3)).toBe(true);
    expect(c.near.has(3)).toBe(false);
  });
});

describe('buffer radius and Near weights', () => {
  const s = DEFAULT_CLASSIFICATION;
  const box = (x: number, y: number, z: number) => new Box3(new Vector3(0, 0, 0), new Vector3(x, y, z));
  it('clamps to [bufferLo, bufferHi]', () => {
    expect(bufferRadius(box(8, 0.0, 0.0), s)).toBeCloseTo(0.3);
    expect(bufferRadius(box(8, 0.6, 0.3), s)).toBeCloseTo(0.6);
    expect(bufferRadius(box(8, 5, 0.3), s)).toBeCloseTo(1.5); // 0.3 + 2.5 clamps to hi
    const custom: ClassificationSettings = { ...s, bufferLo: 0.5, bufferHi: 0.55 };
    expect(bufferRadius(box(8, 0.05, 0.05), custom)).toBeCloseTo(0.5);
    expect(bufferRadius(box(8, 0.6, 0.3), custom)).toBeCloseTo(0.55);
  });
  it('Near boundary: weight 1 at distance 0, 0 at the radius, none past it', () => {
    // radius for a 0.3 x 0.3 cross section = 0.45
    const sc = makeScene([
      { cls: 'IfcDuctSegment', box: [0, 0, 0, 8, 0.3, 0.3] },
      { cls: 'IfcWall', box: [0, 0.3, 5, 1, 1, 6] }, // 0: gap in z of 4.7, far
      { cls: 'IfcWall', box: [2, 0.3 + 0.45, 0, 2.2, 1.5, 0.3] }, // exactly at radius
      { cls: 'IfcWall', box: [4, 0.3 + 0.2, 0, 4.2, 1.5, 0.3] }, // d = 0.2/0.45
      { cls: 'IfcWall', box: [6, 0.3 + 0.46, 0, 6.2, 1.5, 0.3] }, // just outside
    ]);
    const c = classify(sc.model, sc.geometry, [0]);
    expect(c.bufferRadius.get(0)).toBeCloseTo(0.45);
    expect(c.near.has(2)).toBe(true);
    expect(c.proximityWeight.get(2)).toBeCloseTo(0, 6);
    const d = 0.2 / 0.45;
    expect(c.proximityWeight.get(3)).toBeCloseTo(1 - (3 * d * d - 2 * d * d * d), 9);
    expect(c.far.has(4)).toBe(true);
    expect(c.far.has(1)).toBe(true);
  });
  it('weight uses the minimum ratio over focus elements, each with its own radius', () => {
    const sc = makeScene(
      [
        { cls: 'IfcDuctSegment', box: [0, 0, 0, 8, 0.3, 0.3] }, // radius 0.45
        { cls: 'IfcDuctSegment', box: [0, 0, 2, 8, 1.2, 2.3] }, // cross 1.2 -> 0.9
        { cls: 'IfcWall', box: [0, 0, 1.0, 8, 1, 1.1] }, // 0.7 from the first, 0.9 from the second
      ],
      { ports: [[0, 1]] },
    );
    const c = classify(sc.model, sc.geometry, [0]);
    expect(c.bufferRadius.get(1)).toBeCloseTo(0.9);
    expect(c.near.has(2)).toBe(true); // outside radius 0.45 for duct 0, inside 0.9 for duct 1
    const d = 0.9 / 0.9;
    // distance to duct 1 = 2 - 1.1 = 0.9 -> ratio 1; distance to duct 0 = 0.7 > 0.45 -> ratio 1.56
    expect(c.proximityWeight.get(2)).toBeCloseTo(1 - ease1(d), 9);
  });
});

function ease1(d: number) {
  return 3 * d * d - 2 * d * d * d;
}

describe('coarse to fine (Algorithm 3)', () => {
  it('no mesh call is made for elements whose AABB is outside the buffer', () => {
    const specs: ElementSpec[] = [{ cls: 'IfcDuctSegment', box: [0, 0, 0, 8, 0.3, 0.3] }];
    for (let i = 0; i < 50; i++) specs.push({ cls: 'IfcSlab', box: [i, 10 + i, 0, i + 1, 11 + i, 1] });
    specs.push({ cls: 'IfcWall', box: [2, 0.4, 0, 2.2, 1, 0.3] }); // id 51, near
    const s = makeScene([...specs]);
    classify(s.model, s.geometry, [0]);
    const touched = new Set(s.geometry.callPairs.map(([, , b]) => b));
    expect([...touched]).toEqual([51]);
  });
});
