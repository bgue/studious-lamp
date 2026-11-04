import { describe, expect, it } from 'vitest';
import { analysePenetrations, boxCentre, filterRows, intersectBox, orientationOf, overlapPairs, penetrationCsvRows, principalAxis, summarise } from '../src/penetrations/analysis';
import type { Box6, PenElement, PenInput, OpeningRec } from '../src/penetrations/analysis';
import { PEN_CSV_HEADER } from '../src/penetrations/analysis';
import { csvCell, toCsv } from '../src/tools/csv';

const el = (id: number, ifcClass: string, bounds: Box6, storey: number | null = 0): PenElement => ({ id, ifcClass, bounds, storey });
const overlapsVolume = (a: Box6, b: Box6): boolean => {
  const o = intersectBox(a, b);
  return !!o && o[3] - o[0] > 1e-6 && o[4] - o[1] > 1e-6 && o[5] - o[2] > 1e-6;
};
function input(mep: PenElement[], hosts: PenElement[], extra: Partial<PenInput> = {}, deny: Array<[number, number]> = []): PenInput {
  const by = new Map([...mep, ...hosts].map((e) => [e.id, e]));
  return {
    mep, hosts,
    intersects: (a, b) => !deny.some(([x, y]) => x === a && y === b) && overlapsVolume(by.get(a)!.bounds, by.get(b)!.bounds),
    ...extra,
  };
}

const slab1 = el(1, 'IfcSlab', [-5, 0, -5, 5, 0.25, 5], 0);
const slab2 = el(2, 'IfcSlab', [-5, 3, -5, 5, 3.25, 5], 1);
const duct = el(10, 'IfcDuctSegment', [-0.3, -1, -0.15, 0.3, 4, 0.15], 0);

describe('penetration analysis: vertical duct through two slabs', () => {
  const opening: OpeningRec = { expressId: 501, host: 1, bounds: [-0.4, -0.01, -0.25, 0.4, 0.26, 0.25] };
  const rows = analysePenetrations(input([duct], [slab1, slab2], { openings: [opening] }));

  it('finds one penetration per slab, ordered, 1-based', () => {
    expect(rows.map((r) => [r.id, r.mep, r.host])).toEqual([[1, 10, 1], [2, 10, 2]]);
  });
  it('slab with an opening: status opening, gap is half the smaller extent difference', () => {
    expect(rows[0]!.status).toBe('opening');
    expect(rows[0]!.openingExpressId).toBe(501);
    expect(rows[0]!.gapMm).toBe(100); // (0.8-0.6)/2 and (0.5-0.3)/2
  });
  it('slab without an opening, in a model with opening data: none', () => {
    expect(rows[1]!.status).toBe('none');
    expect(rows[1]!.gapMm).toBeNull();
  });
  it('location, orientation, size and thickness', () => {
    expect(rows[0]!.location[0]).toBeCloseTo(0, 9);
    expect(rows[0]!.location[1]).toBeCloseTo(0.125, 9);
    expect(rows[0]!.orientation).toBe('vertical');
    expect(rows[0]!.sizeMm).toEqual([300, 600]);
    expect(rows[0]!.hostThicknessMm).toBe(250);
    expect(rows[0]!.storey).toBe(0);
    expect(rows[1]!.storey).toBe(1);
  });
  it('summary counts', () => {
    expect(summarise(rows)).toEqual({ total: 2, opening: 1, none: 1, unknown: 0 });
  });
});

describe('penetration analysis: other cases', () => {
  it('horizontal pipe through a wall', () => {
    const wall = el(3, 'IfcWall', [-0.1, 0, -5, 0.1, 3, 5]);
    const pipe = el(11, 'IfcPipeSegment', [-2, 1, 0, 2, 1.1, 0.1]);
    const rows = analysePenetrations(input([pipe], [wall], { openings: [{ expressId: 7, host: 99, bounds: [0, 0, 0, 1, 1, 1] }] }));
    expect(rows).toHaveLength(1);
    expect(rows[0]!.orientation).toBe('horizontal');
    expect(rows[0]!.sizeMm).toEqual([100, 100]);
    expect(rows[0]!.hostThicknessMm).toBe(200);
    expect(rows[0]!.status).toBe('none');
  });
  it('inclined pipe uses the axis estimate', () => {
    const wall = el(3, 'IfcWall', [-0.1, 0, -5, 0.1, 3, 5]);
    const pipe = el(12, 'IfcPipeSegment', [-1, 0.5, 0, 1, 2.5, 0.1]);
    const rows = analysePenetrations(input([pipe], [wall], { axisOf: () => [Math.SQRT1_2, Math.SQRT1_2, 0] }));
    expect(rows[0]!.orientation).toBe('inclined');
    expect(orientationOf([0, 1, 0])).toBe('vertical');
    expect(orientationOf([1, 0.1, 0])).toBe('horizontal');
    expect(orientationOf([1, 1, 0])).toBe('inclined');
  });
  it('a duct alongside a wall (bounds overlap, geometry does not) is not a penetration', () => {
    const wall = el(3, 'IfcWall', [-0.1, 0, -5, 0.1, 3, 5]);
    const alongside = el(13, 'IfcDuctSegment', [0.05, 1, -2, 0.5, 1.3, 2]);
    expect(analysePenetrations(input([alongside], [wall], {}, [[13, 3]]))).toHaveLength(0);
    expect(analysePenetrations(input([alongside], [wall]))).toHaveLength(1);
  });
  it('a duct that only touches bounds edge-on, or is clear of the wall, gives nothing', () => {
    const wall = el(3, 'IfcWall', [-0.1, 0, -5, 0.1, 3, 5]);
    expect(analysePenetrations(input([el(14, 'IfcDuctSegment', [0.5, 1, 0, 1.5, 1.3, 1])], [wall]))).toHaveLength(0);
  });
  it('a model without opening data: unknown, unless the MEP element is hosted by relation', () => {
    const rows = analysePenetrations(input([duct], [slab1, slab2], { hostedBy: [[10, 2]] }));
    expect(rows.map((r) => r.status)).toEqual(['unknown', 'opening']);
    expect(rows[1]!.gapMm).toBeNull();
    expect(rows[1]!.openingExpressId).toBeNull();
  });
  it('opening containment tolerance is 5 mm', () => {
    const slab = el(1, 'IfcSlab', [-5, 0, -5, 5, 0.25, 5]);
    const d = el(10, 'IfcDuctSegment', [-0.3, -1, -0.15, 0.3, 4, 0.15]);
    // location is (0, 0.125, 0); an opening ending 4 mm short of it in y still contains it
    const near: OpeningRec = { expressId: 1, host: 1, bounds: [-1, 0.129, -1, 1, 1, 1] };
    const far: OpeningRec = { expressId: 2, host: 1, bounds: [-1, 0.131, -1, 1, 1, 1] };
    expect(analysePenetrations(input([d], [slab], { openings: [near] }))[0]!.status).toBe('opening');
    expect(analysePenetrations(input([d], [slab], { openings: [far] }))[0]!.status).toBe('none');
  });
  it('the smallest containing opening gives the gap; a negative gap means the opening is too small', () => {
    const big: OpeningRec = { expressId: 1, host: 1, bounds: [-1, -1, -1, 1, 1, 1] };
    const small: OpeningRec = { expressId: 2, host: 1, bounds: [-0.25, -0.1, -0.1, 0.25, 0.4, 0.1] };
    const r = analysePenetrations(input([duct], [slab1], { openings: [big, small] }))[0]!;
    expect(r.openingExpressId).toBe(2);
    expect(r.gapMm).toBe(-50); // x: (0.5-0.6)/2
  });
});

describe('sweep and helpers', () => {
  it('overlapPairs finds exactly the bounds-overlapping pairs, once each', () => {
    const mep = [el(1, 'a', [0, 0, 0, 2, 1, 1]), el(2, 'a', [10, 0, 0, 12, 1, 1]), el(3, 'a', [1, 5, 0, 3, 6, 1])];
    const hosts = [el(4, 'h', [1.5, 0, 0, 2.5, 1, 1]), el(5, 'h', [11, 0.5, 0.5, 20, 2, 2]), el(6, 'h', [-5, -5, -5, 30, 30, 30])];
    const got = overlapPairs(mep, hosts).map(([m, h]) => `${m.id}-${h.id}`).sort();
    const brute: string[] = [];
    for (const m of mep) for (const h of hosts) if (intersectBox(m.bounds, h.bounds)) brute.push(`${m.id}-${h.id}`);
    expect(got).toEqual(brute.sort());
    expect(got).toContain('1-4');
    expect(got).not.toContain('3-4');
  });
  it('overlapPairs agrees with brute force on random boxes', () => {
    let s = 7;
    const rnd = (): number => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296);
    const mk = (id: number): PenElement => {
      const x = rnd() * 20, y = rnd() * 20, z = rnd() * 20;
      return el(id, 'x', [x, y, z, x + rnd() * 4, y + rnd() * 4, z + rnd() * 4]);
    };
    const mep = Array.from({ length: 150 }, (_, i) => mk(i));
    const hosts = Array.from({ length: 150 }, (_, i) => mk(1000 + i));
    const got = overlapPairs(mep, hosts).map(([m, h]) => `${m.id}-${h.id}`).sort();
    const brute: string[] = [];
    for (const m of mep) for (const h of hosts) if (intersectBox(m.bounds, h.bounds)) brute.push(`${m.id}-${h.id}`);
    expect(got).toEqual(brute.sort());
  });
  it('principalAxis finds the long direction of a point cloud', () => {
    const pts = Array.from({ length: 50 }, (_, i) => [i * 0.1, i * 0.1 + (i % 2) * 0.01, (i % 3) * 0.01] as [number, number, number]);
    const a = principalAxis(pts)!;
    expect(Math.abs(a[0])).toBeCloseTo(Math.SQRT1_2, 1);
    expect(Math.abs(a[1])).toBeCloseTo(Math.SQRT1_2, 1);
    expect(principalAxis([[0, 0, 0]])).toBeNull();
  });
  it('boxCentre', () => expect(boxCentre([0, 0, 0, 2, 4, 6])).toEqual([1, 2, 3]));
  it('filterRows by status, storey and host class', () => {
    const rows = analysePenetrations(input([duct], [slab1, slab2], { openings: [{ expressId: 1, host: 1, bounds: [-1, -1, -1, 1, 1, 1] }] }));
    const cls = (id: number): string => (id === 1 ? 'IfcSlab' : 'IfcWall');
    expect(filterRows(rows, { status: new Set(['none']) }, cls).map((r) => r.host)).toEqual([2]);
    expect(filterRows(rows, { storeys: new Set([0]) }, cls).map((r) => r.host)).toEqual([1]);
    expect(filterRows(rows, { hostClasses: new Set(['IfcWall']) }, cls).map((r) => r.host)).toEqual([2]);
    expect(filterRows(rows, {}, cls)).toHaveLength(2);
  });
});

describe('CSV', () => {
  it('quotes commas, quotes and newlines; doubles quotes', () => {
    expect(csvCell('a,b')).toBe('"a,b"');
    expect(csvCell('say "hi"')).toBe('"say ""hi"""');
    expect(csvCell('l1\nl2')).toBe('"l1\nl2"');
    expect(csvCell('plain')).toBe('plain');
  });
  it('numbers, nulls and booleans', () => {
    expect(csvCell(1.5)).toBe('1.5');
    expect(csvCell(null)).toBe('');
    expect(csvCell(undefined)).toBe('');
    expect(csvCell(NaN)).toBe('');
    expect(csvCell(true)).toBe('true');
  });
  it('neutralises spreadsheet formulas in text but leaves numbers alone', () => {
    expect(csvCell('=SUM(A1)')).toBe("'=SUM(A1)");
    expect(csvCell('-5 duct')).toBe("'-5 duct");
    expect(csvCell(-5)).toBe('-5');
  });
  it('penetration rows round trip to a well-formed CSV', () => {
    const rows = analysePenetrations(input([duct], [slab1]));
    const ctx = {
      mepName: () => 'Duct, "main"', mepGlobalId: () => 'G1', mepClass: () => 'IfcDuctSegment',
      hostName: () => 'Slab', hostGlobalId: () => 'G2', hostClass: () => 'IfcSlab', storeyName: () => 'Level 1',
    };
    const csv = toCsv(PEN_CSV_HEADER, penetrationCsvRows(rows, ctx));
    const lines = csv.trim().split('\r\n');
    expect(lines).toHaveLength(2);
    expect(lines[0]!.split(',')).toHaveLength(PEN_CSV_HEADER.length);
    expect(lines[1]).toContain('"Duct, ""main"""');
    expect(lines[1]).toContain(',unknown,');
  });
});
