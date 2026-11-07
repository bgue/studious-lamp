// Quantity summaries: parsing and error positions, aggregation with NULL and non-numeric values, quantity aliases,
// geometric estimates (unit cube, box, thin plate), grouping, units and rounding, the HUD text, the real samples
// and a 100,000-row timing check.

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { computeClosedFlags } from '../src/model/closedMesh';
import {
  QueryError,
  classNoun,
  formatNumber,
  formatValue,
  freshTable,
  looksLikeAggregate,
  isExplicitAggregate,
  makeGeoEstimator,
  meshMeasure,
  modelTable,
  parseAggregate,
  resolveQuantity,
  runAggregate,
  summaryLines,
} from '../src/query';
import { reportToConsole, summaryRows, toApi } from '../src/search/quantityMode';
import type { ElementRecord, SceneModel } from '../src/types';

type P = Record<string, string | number | boolean>;
interface Spec {
  cls?: string;
  name?: string;
  storey?: number | null;
  props?: P;
  bounds?: [number, number, number, number, number, number];
}

function model(specs: Spec[]): SceneModel {
  const elements: ElementRecord[] = specs.map((s, id) => ({
    id,
    globalId: `G${id}`,
    ifcClass: s.cls ?? 'IfcWall',
    name: s.name,
    storey: s.storey === undefined ? 0 : s.storey,
    color: [0.7, 0.7, 0.7, 1],
    bounds: s.bounds ?? [id, 0, 0, id + 1, 1, 1],
    props: s.props,
  }));
  return {
    schema: 'xray-model/1',
    units: 'm',
    originShift: [0, 0, 0],
    storeys: [
      { id: 0, name: 'Level 1', elevation: 0 },
      { id: 1, name: 'Level 2', elevation: 3 },
    ],
    elements,
    relations: { voids: [], fills: [], hosts: [], ports: [], systems: [] },
    byGlobalId: new Map(elements.map((e) => [e.globalId, e.id])),
  };
}

const err = (text: string): QueryError => {
  try {
    parseAggregate(text);
  } catch (e) {
    return e as QueryError;
  }
  throw new Error(`no error for ${text}`);
};

describe('parsing', () => {
  it('reads count, sum, avg, min and max with an optional where', () => {
    const a = parseAggregate("count where class = 'IfcWall'");
    expect(a.aggs).toEqual([{ fn: 'count', qty: null, pos: 0 }]);
    expect(a.where).toBe("class = 'IfcWall'");
    expect(a.by).toBeNull();
    const b = parseAggregate('SUM Length');
    expect(b.aggs[0]).toMatchObject({ fn: 'sum', qty: 'Length' });
    expect(b.where).toBeNull();
    for (const fn of ['avg', 'min', 'max']) expect(parseAggregate(`${fn} width where height > 2`).aggs[0]!.fn).toBe(fn);
  });

  it('reads several aggregates, by, quoted keys, dotted keys and a leading ?', () => {
    const a = parseAggregate("sum length, count where class = 'IfcPipeSegment' by storey");
    expect(a.aggs.map((x) => x.fn)).toEqual(['sum', 'count']);
    expect(a.where).toBe("class = 'IfcPipeSegment'");
    expect(a.by).toEqual({ name: 'storey', pos: 52 });
    expect(parseAggregate('sum Qto_WallBaseQuantities.NetVolume').aggs[0]!.qty).toBe('Qto_WallBaseQuantities.NetVolume');
    expect(parseAggregate('sum "Net Volume"').aggs[0]!.qty).toBe('Net Volume');
    expect(parseAggregate('sum net volume').aggs[0]!.qty).toBe('net volume');
    expect(parseAggregate('sum of length').aggs[0]!.qty).toBe('length');
    expect(parseAggregate('sum(length) and count').aggs.map((x) => x.fn)).toEqual(['sum', 'count']);
    expect(parseAggregate('? count by class').by!.name).toBe('class');
    expect(parseAggregate('count by storey where class = 1').where).toBe('class = 1');
  });

  it('keeps by inside a string or a bracket out of the split', () => {
    const a = parseAggregate("count where name like '% by %' and (x = 1) by storey");
    expect(a.where).toBe("name like '% by %' and (x = 1)");
    expect(a.by!.name).toBe('storey');
  });

  it('reports the character position of the problem', () => {
    expect(err('')).toMatchObject({ pos: 0 });
    const e1 = err('total length');
    expect(e1.pos).toBe(0);
    expect(e1.bare).toContain('Expected count, sum, avg, min or max');
    const e2 = err('sum where x = 1');
    expect(e2.pos).toBe(4);
    expect(e2.bare).toContain('Expected a quantity after sum');
    const e3 = err('count where');
    expect(e3.pos).toBe(11);
    expect(e3.bare).toContain('Expected a condition after "where"');
    // an error inside the condition is placed in the whole text
    const e4 = err("sum length where class = ");
    expect(e4.pos).toBe(25);
    expect(e4.bare).toContain('Expected a value after "="');
    const e5 = err('count by');
    expect(e5.pos).toBe(8);
    expect(e5.bare).toContain('Expected a column name after "by"');
    const e6 = err('count where a = 1 where b = 2');
    expect(e6.pos).toBe(18);
    const e7 = err('count foo');
    expect(e7.pos).toBe(6);
    expect(e7.bare).toContain('Unexpected "foo"');
    expect(err("count where name = 'abc").pos).toBe(19);
    expect(e7.message).toMatch(/at character 7\)$/);
  });

  it('tells a summary from plain text', () => {
    expect(looksLikeAggregate('count')).toBe(true);
    expect(looksLikeAggregate('count where a = 1')).toBe(true);
    expect(looksLikeAggregate('sum length')).toBe(true);
    expect(looksLikeAggregate('counter')).toBe(false);
    expect(looksLikeAggregate('count wall')).toBe(false);
    expect(looksLikeAggregate("sum 'x")).toBe(false);
    expect(looksLikeAggregate('wall')).toBe(false);
    expect(isExplicitAggregate('sum length')).toBe(false);
    expect(isExplicitAggregate('sum length by storey')).toBe(true);
    expect(isExplicitAggregate('sum length, count')).toBe(true);
  });
});

describe('quantity names', () => {
  const m = model([
    { cls: 'IfcWall', props: { 'Qto_WallBaseQuantities.Length': 4, 'Qto_WallBaseQuantities.NetVolume': 2, 'Qto_WallBaseQuantities.NetSideArea': 10, 'Pset_X.Note': 'a' } },
    { cls: 'IfcBeam', props: { 'Qto_BeamBaseQuantities.Length': 5, 'Qto_BeamBaseQuantities.NetVolume': 1, 'Qto_BeamBaseQuantities.GrossVolume': 1.2 } },
    { cls: 'IfcSlab', props: { 'BaseQuantities.NetArea': 30, 'BaseQuantities.GrossArea': 31, 'BaseQuantities.GrossVolume': 6 } },
  ]);
  const t = freshTable(m);

  it('maps length, volume and area to the quantity keys of every class', () => {
    expect(resolveQuantity(t, 'length')!.keys).toEqual(['Qto_BeamBaseQuantities.Length', 'Qto_WallBaseQuantities.Length']);
    expect(resolveQuantity(t, 'LENGTH')!.dim).toBe('length');
    // net before gross
    expect(resolveQuantity(t, 'volume')!.keys).toEqual(['Qto_BeamBaseQuantities.NetVolume', 'Qto_WallBaseQuantities.NetVolume', 'BaseQuantities.GrossVolume', 'Qto_BeamBaseQuantities.GrossVolume']);
    expect(resolveQuantity(t, 'area')!.keys).toEqual(['BaseQuantities.NetArea', 'BaseQuantities.GrossArea', 'Qto_WallBaseQuantities.NetSideArea']);
    expect(resolveQuantity(t, 'area')!.dim).toBe('area');
  });

  it('matches the exact key, the last segment, a part of it, ignoring case and punctuation', () => {
    expect(resolveQuantity(t, 'qto_wallbasequantities.length')!.keys).toEqual(['Qto_WallBaseQuantities.Length']);
    expect(resolveQuantity(t, 'netsidearea')!.keys).toEqual(['Qto_WallBaseQuantities.NetSideArea']);
    expect(resolveQuantity(t, 'net side area')!.keys).toEqual(['Qto_WallBaseQuantities.NetSideArea']);
    expect(resolveQuantity(t, 'NetVolume')!.keys).toEqual(['Qto_BeamBaseQuantities.NetVolume', 'Qto_WallBaseQuantities.NetVolume']);
    expect(resolveQuantity(t, 'grossvol')!.dim).toBe('volume');
    expect(resolveQuantity(t, 'sizeY')!.core).toBe('sizeY');
  });

  it('gives null for a name nothing matches and keeps estimates for length and volume of a model without the keys', () => {
    expect(resolveQuantity(t, 'banana')).toBeNull();
    const bare = freshTable(model([{}]));
    expect(resolveQuantity(bare, 'length')).toMatchObject({ keys: [], est: 'length' });
    expect(resolveQuantity(bare, 'weight')).toBeNull();
  });

  it('reports an unknown quantity with the position of the word', () => {
    try {
      runAggregate(t, 'count, sum banana where class = 1');
      throw new Error('no error');
    } catch (e) {
      expect(e).toBeInstanceOf(QueryError);
      expect((e as QueryError).pos).toBe(11);
      expect((e as QueryError).bare).toContain('No quantity or property matches "banana"');
    }
  });

  it('joins words: net side area', () => {
    const s = runAggregate(t, 'sum net side area');
    expect(s.aggs[0]!.value).toBe(10);
  });
});

describe('aggregation', () => {
  const m = model([
    { cls: 'IfcWall', props: { 'Q.Length': 2 } },
    { cls: 'IfcWall', props: { 'Q.Length': '3.5' } }, // text that is a number
    { cls: 'IfcWall', props: { 'Q.Length': 'tall' } }, // not a number
    { cls: 'IfcWall', props: { 'Q.Length': true } }, // yes/no
    { cls: 'IfcWall', props: { 'Q.Length': Infinity } }, // not finite
    { cls: 'IfcWall', props: { 'Q.Area': 1 }, bounds: [0, 0, 0, 0, 0, 0] }, // no length and an empty box: no estimate
    { cls: 'IfcWall' }, // no props, boxed: estimate
    { cls: 'IfcDoor', props: { 'Q.Length': 10 } },
  ]);
  const t = freshTable(m);

  it('counts every matched element, sums the numbers and skips the rest with a reason', () => {
    const s = runAggregate(t, "count, sum length, avg length, min length, max length where class = 'IfcWall'");
    expect(s.matched).toBe(7);
    expect(s.aggs[0]).toMatchObject({ fn: 'count', value: 7 });
    // 2 + 3.5 + estimate of element 6 (bounds 6..7 x 1 x 1: longest axis 1)
    expect(s.aggs[1]).toMatchObject({ fn: 'sum', value: 6.5, n: 3, estimated: 1, skipped: 4 });
    expect(s.aggs[2]!.value).toBeCloseTo(6.5 / 3);
    expect(s.aggs[3]!.value).toBe(1);
    expect(s.aggs[4]!.value).toBe(3.5);
    expect(s.skippedCount).toBe(4);
    const reasons = s.skipped.map((k) => k.reason);
    expect(reasons[0]).toContain('Q.Length is not a number ("tall")');
    expect(reasons[1]).toContain('yes/no');
    expect(reasons[2]).toContain('not finite');
    expect(reasons[3]).toContain('the bounds are empty');
    expect(s.skipped[0]).toMatchObject({ id: 2, globalId: 'G2', qty: 'length' });
    expect(s.estimated).toBe(1);
  });

  it('gives null for avg, min and max of nothing, and 0 for sum', () => {
    const s = runAggregate(t, "sum length, avg length, max length where class = 'IfcWall' and name = 'none'");
    expect(s.matched).toBe(0);
    expect(s.aggs.map((a) => a.value)).toEqual([0, null, null]);
    expect(summaryLines(s)[0]).toContain('0 elements');
  });

  it('runs over the visible elements when there is no where, and over all matches when there is one', () => {
    const vis = (id: number): boolean => id !== 7;
    expect(runAggregate(t, 'count', { visible: vis }).matched).toBe(7);
    expect(runAggregate(t, 'count where id >= 0', { visible: vis }).matched).toBe(8);
    expect(runAggregate(t, 'count').matched).toBe(8);
  });

  it('names columns the condition does not know', () => {
    expect(runAggregate(t, "count where Banana = 'x'").unknown).toEqual(['Banana']);
  });

  it('answers the same through the script API shape', () => {
    const api = toApi(runAggregate(t, "sum length where class = 'IfcDoor'"));
    expect(api.total).toBe(10);
    expect(api.unit).toBe('m');
    expect(api.estimated).toBe(0);
    expect(api.rows).toHaveLength(1);
    expect(api.rows[0]).toMatchObject({ globalId: 'G7', class: 'IfcDoor', storey: 'Level 1', values: { length: 10 }, sources: { length: 'Q.Length' } });
    expect(api.groups).toBeNull();
    expect(api.lines[0]).toBe('1 door · Σ length 10 m');
  });
});

/** One merged soup: boxes as 12 triangles on 8 shared vertices. */
function boxMesh(boxes: Array<[number, number, number]>): { position: Float32Array; index: Uint32Array; ranges: Array<{ start: number; count: number }>; vranges: Array<{ start: number; count: number }>; bounds: number[][] } {
  const pos: number[] = [];
  const idx: number[] = [];
  const ranges: Array<{ start: number; count: number }> = [];
  const vranges: Array<{ start: number; count: number }> = [];
  const bounds: number[][] = [];
  const faces = [[0, 1, 3, 2], [4, 6, 7, 5], [0, 4, 5, 1], [2, 3, 7, 6], [0, 2, 6, 4], [1, 5, 7, 3]];
  for (const [sx, sy, sz] of boxes) {
    const v0 = pos.length / 3;
    vranges.push({ start: v0, count: 8 });
    ranges.push({ start: idx.length, count: 36 });
    for (let i = 0; i < 8; i++) pos.push((i & 1) * sx, ((i >> 1) & 1) * sy, ((i >> 2) & 1) * sz);
    for (const f of faces) idx.push(v0 + f[0]!, v0 + f[1]!, v0 + f[2]!, v0 + f[0]!, v0 + f[2]!, v0 + f[3]!);
    bounds.push([0, 0, 0, sx, sy, sz]);
  }
  return { position: new Float32Array(pos), index: new Uint32Array(idx), ranges, vranges, bounds };
}

describe('geometric estimates', () => {
  const mesh = boxMesh([[1, 1, 1], [2, 3, 4], [5, 4, 0.2]]);
  const closed = computeClosedFlags(mesh.position, mesh.index, mesh.ranges, mesh.vranges);
  const geo = makeGeoEstimator({ position: mesh.position, index: mesh.index, ranges: mesh.ranges, closed, bounds: (id) => mesh.bounds[id]! });

  it('measures volume and surface of a unit cube and a box', () => {
    const c = meshMeasure(mesh.position, mesh.index, mesh.ranges[0]!);
    expect(c.volume).toBeCloseTo(1, 9);
    expect(c.area).toBeCloseTo(6, 9);
    const b = meshMeasure(mesh.position, mesh.index, mesh.ranges[1]!);
    expect(b.volume).toBeCloseTo(24, 5);
    expect(b.area).toBeCloseTo(2 * (6 + 8 + 12), 5);
  });

  it('estimates the volume of closed solids and the area of thin plates only', () => {
    expect(geo.volume(0)).toBeCloseTo(1, 6);
    expect(geo.volume(1)).toBeCloseTo(24, 5);
    expect(typeof geo.area(0)).toBe('string'); // a cube is not a plate
    expect(geo.area(1)).toContain('not a thin plate');
    // 5 x 4 x 0.2 plate: surface / 2 = (2*(20 + 1 + 0.8)) / 2 = 21.8 (the plate face is 20: the edges add a few percent)
    expect(geo.area(2)).toBeCloseTo(21.8, 5);
  });

  it('gives a reason for an open mesh and does not estimate its volume', () => {
    const open = makeGeoEstimator({ position: mesh.position, index: mesh.index, ranges: mesh.ranges, closed: [0, 0, 0], bounds: (id) => mesh.bounds[id]! });
    expect(open.volume(0)).toBe('the mesh is not a closed solid');
  });

  it('uses the estimates in a summary and counts them', () => {
    const m = model([
      { cls: 'IfcSlab', props: { 'Q.NetVolume': 2 }, bounds: [0, 0, 0, 1, 1, 1] },
      { cls: 'IfcSlab', bounds: [0, 0, 0, 2, 3, 4] },
      { cls: 'IfcSlab', bounds: [0, 0, 0, 5, 4, 0.2] },
    ]);
    const s = runAggregate(freshTable(m), 'sum volume, sum area, sum length', { geo });
    expect(s.aggs[0]).toMatchObject({ n: 3, estimated: 2 });
    expect(s.aggs[0]!.value).toBeCloseTo(2 + 24 + 4, 4);
    // area: only the plate has an estimate (the cube and the box are not plates)
    expect(s.aggs[1]).toMatchObject({ n: 1, estimated: 1, skipped: 2 });
    expect(s.aggs[1]!.value).toBeCloseTo(21.8, 5);
    // length: the longest bounds axis of each (1, 4, 5)
    expect(s.aggs[2]).toMatchObject({ value: 10, estimated: 3 });
    expect(s.estimated).toBe(2 + 1 + 3);
    expect(summaryLines(s)[0]).toBe('3 slabs · Σ volume 30 m³ (2 est.) · Σ area 21.8 m² (1 est.) · Σ length 10 m (3 est.) · 2 skipped');
    const rows = summaryRows(s);
    expect(rows[0]!.sources.volume).toBe('Q.NetVolume');
    expect(rows[1]!.sources.volume).toBe('estimated');
    expect(rows[0]!.sources.area).toBe('none');
    expect(rows[2]!.sources.area).toBe('estimated');
  });

  it('skips a volume when no mesh is available', () => {
    const s = runAggregate(freshTable(model([{ bounds: [0, 0, 0, 1, 1, 1] }])), 'sum volume');
    expect(s.aggs[0]).toMatchObject({ value: 0, n: 0, skipped: 1 });
    expect(s.skipped[0]!.reason).toContain('no mesh is available');
  });
});

describe('grouping', () => {
  const m = model([
    { cls: 'IfcWall', storey: 0, props: { 'Q.Length': 1 } },
    { cls: 'IfcWall', storey: 0, props: { 'Q.Length': 2 } },
    { cls: 'IfcBeam', storey: 1, props: { 'Q.Length': 10 } },
    { cls: 'IfcBeam', storey: null, props: { 'Q.Length': 20 } },
    { cls: 'IfcBeam', storey: 1, props: { 'Q.Length': 'x' } },
  ]);
  const t = freshTable(m);

  it('adds subtotals per group, largest first, and keeps the grand total', () => {
    const s = runAggregate(t, 'sum length, count by storey');
    expect(s.aggs[0]!.value).toBe(33);
    expect(s.groups!.map((g) => [g.key, g.count, g.aggs[0]!.value, g.aggs[0]!.skipped])).toEqual([
      ['(none)', 1, 20, 0],
      ['Level 2', 2, 10, 1],
      ['Level 1', 2, 3, 0],
    ]);
    expect(s.groups!.reduce((a, g) => a + g.aggs[0]!.value!, 0)).toBe(s.aggs[0]!.value);
  });

  it('groups by class, by a property and by a level alias; counts only when there is no quantity', () => {
    expect(runAggregate(t, 'count by class').groups!.map((g) => [g.key, g.count])).toEqual([['IfcBeam', 3], ['IfcWall', 2]]);
    expect(runAggregate(t, 'count by level').groupBy).toBe('level');
    expect(runAggregate(t, 'count by Q.Length').groups).toHaveLength(5);
    expect(runAggregate(t, 'max length by class').groups!.map((g) => g.aggs[0]!.value)).toEqual([20, 2]);
  });

  it('rejects an unknown group column with its position', () => {
    try {
      runAggregate(t, 'count by banana');
      throw new Error('no error');
    } catch (e) {
      expect((e as QueryError).pos).toBe(9);
    }
  });

  it('shows the top 3 groups on the second line and says how many more', () => {
    const many = model(Array.from({ length: 6 }, (_, i) => ({ cls: `IfcThing${i}`, props: { 'Q.Length': i + 1 } })));
    const lines = summaryLines(runAggregate(freshTable(many), 'sum length by class'));
    expect(lines).toHaveLength(2);
    expect(lines[1]).toBe('IfcThing5: 6 m · IfcThing4: 5 m · IfcThing3: 4 m · +3 more (console)');
    const small = summaryLines(runAggregate(t, 'sum length by class'));
    expect(small[1]).toBe('IfcBeam: 30 m · IfcWall: 3 m');
  });
});

describe('units and rounding', () => {
  it('rounds by size and drops trailing zeros', () => {
    expect(formatNumber(318.43)).toBe('318.4');
    expect(formatNumber(12)).toBe('12');
    expect(formatNumber(12.04)).toBe('12');
    expect(formatNumber(3.14159)).toBe('3.14');
    expect(formatNumber(0.12345)).toBe('0.123');
    expect(formatNumber(0.5)).toBe('0.5');
    expect(formatNumber(12345.6)).toBe('12 346');
    expect(formatNumber(0)).toBe('0');
    expect(formatNumber(-0.0001)).toBe('-1.0e-4');
    expect(formatNumber(-1.234)).toBe('-1.23');
  });

  it('uses m, m2 and m3 by the kind of quantity, kg for weights and none for the rest', () => {
    const m = model([{ props: { 'Q.Length': 2.5, 'Q.NetArea': 3, 'Q.NetVolume': 4.25, 'Q.NetWeight': 100, 'Q.Count': 7 } }]);
    const s = runAggregate(freshTable(m), 'sum length, sum area, sum volume, sum weight, sum count');
    expect(s.aggs.map((a) => formatValue(a.value, a.unit))).toEqual(['2.5 m', '3 m²', '4.25 m³', '100 kg', '7']);
    expect(s.unit).toBe('m');
    expect(formatValue(null, 'm')).toBe('–');
  });

  it('labels with the unit of the model', () => {
    const s = runAggregate(freshTable(model([{ props: { 'Q.Length': 2500 } }])), 'sum length', { lengthUnit: 'mm' });
    expect(formatValue(s.aggs[0]!.value, s.aggs[0]!.unit)).toBe('2 500 mm');
  });

  it('writes class names as plain plurals', () => {
    expect(classNoun('IfcPipeSegment', 42)).toBe('pipe segments');
    expect(classNoun('IfcPipeSegment', 1)).toBe('pipe segment');
    expect(classNoun('IfcWallStandardCase', 2)).toBe('wall standard cases');
    expect(classNoun('IfcCovering', 2)).toBe('coverings');
    expect(classNoun('IfcBuildingStorey', 2)).toBe('building storeys');
    expect(classNoun('IfcSpaceBoundary', 2)).toBe('space boundaries');
    expect(classNoun('IfcBox', 2)).toBe('boxes');
  });

  it('writes the HUD line from the issue', () => {
    const specs: Spec[] = Array.from({ length: 42 }, (_, i) => ({ cls: 'IfcPipeSegment', props: i < 36 ? { 'Q.Length': 7.5 } : undefined, bounds: [0, 0, 0, 7.5, 0.1, 0.1] }));
    const s = runAggregate(freshTable(model(specs)), "sum length where class = 'IfcPipeSegment'");
    expect(summaryLines(s)).toEqual(['42 pipe segments · Σ length 315 m (6 est.)']);
  });
});

describe('console report', () => {
  it('writes one collapsed group with the table, the subtotals and the skipped elements', () => {
    const m = model([
      { cls: 'IfcWall', name: 'A', storey: 0, props: { 'Q.Length': 2 } },
      { cls: 'IfcWall', name: 'B', storey: 1, props: { 'Q.Length': 'x' } },
    ]);
    const s = runAggregate(freshTable(m), 'sum length by storey');
    const calls: string[] = [];
    const tables: unknown[][] = [];
    reportToConsole(s, {
      groupCollapsed: (...a: unknown[]) => void calls.push(`open ${String(a[0])}`),
      groupEnd: () => void calls.push('end'),
      table: (d: unknown) => void tables.push(d as unknown[]),
      log: (...a: unknown[]) => void calls.push(`log ${String(a[0])}`),
      info: (...a: unknown[]) => void calls.push(`info ${String(a[0])}`),
    } as unknown as Console);
    expect(calls[0]).toMatch(/^open \[X-ray\] sum length by storey → 2 walls · Σ length 2 m · 1 skipped/);
    expect(calls.at(-1)).toBe('end');
    expect(tables).toHaveLength(3); // elements, subtotals, skipped
    expect(Object.keys(tables[0]![0] as object)).toEqual(['GlobalId', 'Name', 'Class', 'Storey', 'storey', 'length', 'length source']);
    expect(tables[2]![0]).toMatchObject({ GlobalId: 'G1', Quantity: 'length' });
    expect((tables[2]![0] as { Reason: string }).Reason).toContain('not a number');
  });
});

// The samples: the expected totals are computed here from the sidecar properties, independent of the engine.
function sample(name: string): SceneModel {
  const j = JSON.parse(readFileSync(fileURLToPath(new URL(`../public/models/${name}.json`, import.meta.url)), 'utf8')) as SceneModel;
  return { ...j, byGlobalId: new Map() };
}

describe('the bundled samples', () => {
  it('fzk-haus: counts walls and sums a quantity to the total of the properties', () => {
    const m = sample('fzk-haus');
    const walls = m.elements.filter((e) => e.ifcClass.startsWith('IfcWall'));
    const s = runAggregate(modelTable(m), "count where class like 'IfcWall%'");
    expect(s.aggs[0]!.value).toBe(walls.length);
    expect(walls.length).toBeGreaterThan(5);
    let expected = 0;
    let n = 0;
    for (const e of walls) {
      const v = e.props?.['BaseQuantities.NetSideArea'];
      if (typeof v === 'number') {
        expected += v;
        n++;
      }
    }
    expect(n).toBeGreaterThan(5);
    const a = runAggregate(modelTable(m), "sum NetSideArea where class like 'IfcWall%'");
    expect(a.aggs[0]!.value).toBeCloseTo(expected, 6);
    expect(a.aggs[0]!.n).toBe(n);
    expect(a.aggs[0]!.estimated).toBe(0);
  });

  it('synth5k: sums the pipe length, per storey too', () => {
    const m = sample('synth5k');
    let expected = 0;
    let count = 0;
    const byStorey = new Map<number | null, number>();
    for (const e of m.elements) {
      if (e.ifcClass !== 'IfcPipeSegment') continue;
      count++;
      const v = e.props!['Qto_PipeSegmentBaseQuantities.Length'] as number;
      expected += v;
      byStorey.set(e.storey, (byStorey.get(e.storey) ?? 0) + v);
    }
    const t = modelTable(m);
    const s = runAggregate(t, "count, sum length where class = 'IfcPipeSegment' by storey");
    expect(s.aggs[0]!.value).toBe(count);
    expect(s.aggs[1]!.value).toBeCloseTo(expected, 6);
    expect(s.aggs[1]!.estimated).toBe(0);
    const names = new Map(m.storeys.map((x) => [x.id, x.name]));
    for (const g of s.groups!) {
      const id = [...byStorey.keys()].find((k) => (k === null ? '(none)' : names.get(k)) === g.key)!;
      expect(g.aggs[1]!.value).toBeCloseTo(byStorey.get(id)!, 6);
    }
  });

  it('building: resolves volume to NetVolume across classes', () => {
    const m = sample('building');
    let expected = 0;
    for (const e of m.elements) for (const k in e.props ?? {}) if (k.endsWith('.NetVolume')) expected += e.props![k] as number;
    expect(runAggregate(modelTable(m), 'sum volume').aggs[0]!.value).toBeCloseTo(expected, 6);
  });
});

describe('speed', () => {
  it('sums 100,000 rows in well under 30 ms', () => {
    const specs: Spec[] = Array.from({ length: 100000 }, (_, i) => ({ cls: i % 3 ? 'IfcPipeSegment' : 'IfcWall', storey: i % 2, props: { 'Qto_PipeSegmentBaseQuantities.Length': (i % 97) + 0.5, 'Qto_WallBaseQuantities.Length': 3, a: i, b: 'x', c: true } }));
    const m = model(specs);
    const t = modelTable(m);
    runAggregate(t, 'sum length'); // warm up
    const times: number[] = [];
    let s;
    for (let k = 0; k < 5; k++) {
      const t0 = performance.now();
      s = runAggregate(t, 'sum length');
      times.push(performance.now() - t0);
    }
    const best = Math.min(...times);
    const tg = performance.now();
    const g = runAggregate(t, "sum length, count where class = 'IfcPipeSegment' by storey");
    const groupMs = performance.now() - tg;
    console.log(`sum over 100000 rows: best ${best.toFixed(1)} ms of ${times.map((x) => x.toFixed(1)).join(', ')}; with where and by ${groupMs.toFixed(1)} ms`);
    expect(s!.matched).toBe(100000);
    expect(s!.aggs[0]!.n).toBe(100000);
    expect(best).toBeLessThan(30);
    expect(g.groups).toHaveLength(2);
  });
});
