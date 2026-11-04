// Criteria query engine: tokenizer, parser, precedence, NULL semantics, LIKE, typed comparison, model columns,
// builder round trip and a 100k-element timing check.

import { describe, expect, it } from 'vitest';
import {
  QueryError,
  columnsOf,
  compareValues,
  conditionsText,
  equalsQuery,
  filterRows,
  freshTable,
  literal,
  modelTable,
  parseQuery,
  quoteIdent,
  runQuery,
  toConditions,
  tokenize,
  typedLiteral,
} from '../src/query';
import type { ElementRecord, SceneModel } from '../src/types';

type P = Record<string, string | number | boolean>;
interface Spec {
  cls: string;
  name?: string;
  storey?: number | null;
  material?: string;
  props?: P;
  bounds?: [number, number, number, number, number, number];
}

function model(specs: Spec[]): SceneModel {
  const elements: ElementRecord[] = specs.map((s, id) => ({
    id,
    globalId: `G${id}`,
    ifcClass: s.cls,
    name: s.name,
    storey: s.storey === undefined ? 0 : s.storey,
    material: s.material,
    color: [0.7, 0.7, 0.7, 1],
    bounds: s.bounds ?? [id, 0, 0, id + 1, 1, 1],
    props: s.props,
  }));
  return {
    schema: 'xray-model/1',
    units: 'm',
    originShift: [0, 0, 0],
    storeys: [
      { id: 0, name: 'Erdgeschoss', elevation: 0 },
      { id: 1, name: 'Dachgeschoss', elevation: 2.7 },
    ],
    elements,
    relations: { voids: [], fills: [], hosts: [], ports: [], systems: [] },
    byGlobalId: new Map(elements.map((e) => [e.globalId, e.id])),
  };
}

const M = model([
  { cls: 'IfcWall', name: 'Wall ext 1', material: 'Concrete', props: { 'Pset_WallCommon.IsExternal': true, 'Pset_WallCommon.FireRating': 'EI60', 'BaseQuantities.NetVolume': 3.412 } }, // 0
  { cls: 'IfcWall', name: 'Wall int 2', material: 'Leichtbeton', props: { 'Pset_WallCommon.IsExternal': false, 'BaseQuantities.NetVolume': 1.5 } }, // 1
  { cls: 'IfcWallStandardCase', name: 'Wall_3', storey: 1, props: { 'Pset_WallCommon.IsExternal': true, 'Attr.ObjectType': 'Basic Wall:200' } }, // 2
  { cls: 'IfcDuctSegment', name: 'Duct 100%', storey: 1, props: { 'Qto.Length': '12', 'Attr.ObjectType': 'Round' } }, // 3
  { cls: 'IfcSlab', name: undefined, storey: null, material: '', bounds: [0, -0.25, 0, 10, 0, 5] }, // 4
  { cls: 'IfcBeam', name: 'Beam', props: { 'Pset_BeamCommon.LoadBearing': 'yes', 'Qto.Length': 4.5 } }, // 5
]);
const T = freshTable(M);
const q = (text: string): number[] => filterRows(text, T);

describe('tokenizer', () => {
  it('splits keywords, dotted names, quoted names, strings and numbers', () => {
    const t = tokenize(`Pset_WallCommon.IsExternal = true and "Fire Rating" <> 'it''s' OR x>=-1.5e2`);
    expect(t.map((x) => `${x.type}:${x.value}`)).toEqual([
      'ident:Pset_WallCommon.IsExternal', 'op:=', 'keyword:TRUE', 'keyword:AND', 'qident:Fire Rating', 'op:!=', "string:it's",
      'keyword:OR', 'ident:x', 'op:>=', 'punct:-', 'number:1.5e2', 'eof:',
    ]);
  });

  it('reports an unterminated string with its start position', () => {
    try {
      tokenize("name = 'abc");
      expect.unreachable();
    } catch (e) {
      expect(e).toBeInstanceOf(QueryError);
      expect((e as QueryError).pos).toBe(7);
      expect((e as QueryError).message).toMatch(/Unterminated string.*character 8/);
    }
  });

  it('rejects unknown characters', () => {
    expect(() => tokenize('a = 1 ; b')).toThrow(/Unexpected character ";" \(at character 7\)/);
  });
});

describe('parser', () => {
  it('gives AND a higher precedence than OR', () => {
    const e = parseQuery('a = 1 OR b = 2 AND c = 3');
    expect(e.kind).toBe('or');
    if (e.kind === 'or') expect(e.items[1]!.kind).toBe('and');
  });

  it('binds NOT tighter than AND', () => {
    const e = parseQuery('NOT a = 1 AND b = 2');
    expect(e.kind).toBe('and');
    if (e.kind === 'and') expect(e.items[0]!.kind).toBe('not');
  });

  it('honours parentheses', () => {
    const e = parseQuery('(a = 1 OR b = 2) AND c = 3');
    expect(e.kind).toBe('and');
    if (e.kind === 'and') expect(e.items[0]!.kind).toBe('or');
  });

  it('parses IN, NOT IN, BETWEEN, NOT BETWEEN, IS [NOT] NULL, NOT LIKE', () => {
    expect(parseQuery("class IN ('IfcWall', 'IfcSlab')").kind).toBe('in');
    const e = parseQuery('x NOT IN (1, 2)');
    expect(e.kind === 'in' && e.neg).toBe(true);
    const b = parseQuery('x NOT BETWEEN 1 AND 2');
    expect(b.kind === 'between' && b.neg).toBe(true);
    const n = parseQuery('x IS NOT NULL');
    expect(n.kind === 'isnull' && n.neg).toBe(true);
    const l = parseQuery("name NOT LIKE 'a%'");
    expect(l.kind === 'like' && l.neg).toBe(true);
  });

  it('BETWEEN takes its AND before the boolean AND', () => {
    const e = parseQuery('x BETWEEN 1 AND 2 AND y = 3');
    expect(e.kind).toBe('and');
    if (e.kind === 'and') expect(e.items.map((i) => i.kind)).toEqual(['between', 'cmp']);
  });

  it('lists the referenced columns', () => {
    expect(columnsOf(parseQuery('"A.b" = 1 AND (c LIKE \'x\' OR "A.b" IS NULL)')).map((c) => c.name)).toEqual(['A.b', 'c']);
  });

  it.each([
    ['', /empty/],
    ['name =', /Expected a value after "=", found the end of the query \(at character 7\)/],
    ['(a = 1', /Expected "\)" to close the "\(" at character 1/],
    ['a = 1)', /no matching "\("/],
    ['a = 1 b = 2', /Unexpected "b": expected AND, OR or the end of the query \(at character 7\)/],
    ['x IN ()', /IN list is empty/],
    ['x IN (1 2)', /Expected "," or "\)"/],
    ['x BETWEEN 1 OR 2', /Expected AND in BETWEEN/],
    ['x IS 3', /Expected NULL after IS/],
    ['x NOT 3', /Expected LIKE, IN or BETWEEN after NOT/],
    ['and = 1', /AND is a keyword/],
    ['= 3', /Expected a column name or a value/],
  ])('reports %j clearly', (text, re) => {
    expect(() => parseQuery(text)).toThrow(re);
  });
});

describe('evaluation', () => {
  it('matches the class and ignores case in string equality', () => {
    expect(q("class = 'IfcWall'")).toEqual([0, 1]);
    expect(q("class = 'ifcwall'")).toEqual([0, 1]);
    expect(q("ifcClass != 'IfcWall'")).toEqual([2, 3, 4, 5]);
  });

  it('reads boolean properties, quoted and bare', () => {
    expect(q('"Pset_WallCommon.IsExternal" = TRUE')).toEqual([0, 2]);
    expect(q('Pset_WallCommon.IsExternal = false')).toEqual([1]);
    expect(q('"Pset_WallCommon.IsExternal"')).toEqual([0, 2]);
    expect(q('NOT "Pset_WallCommon.IsExternal"')).toEqual([1]);
  });

  it('compares booleans with yes/no strings', () => {
    expect(q('"Pset_BeamCommon.LoadBearing" = TRUE')).toEqual([5]);
    expect(q("\"Pset_WallCommon.IsExternal\" = 'true'")).toEqual([0, 2]);
  });

  it('resolves property keys without regard to case', () => {
    expect(q('pset_wallcommon.isexternal = TRUE')).toEqual([0, 2]);
  });

  it('applies SQL NULL semantics: a missing property never matches = or !=', () => {
    expect(q('"Pset_WallCommon.IsExternal" != TRUE')).toEqual([1]);
    expect(q('NOT ("Pset_WallCommon.IsExternal" = TRUE)')).toEqual([1]);
    expect(q('"Pset_WallCommon.IsExternal" IS NULL')).toEqual([3, 4, 5]);
    expect(q('"Pset_WallCommon.IsExternal" IS NOT NULL')).toEqual([0, 1, 2]);
    expect(q('x = NULL')).toEqual([]);
  });

  it('treats UNKNOWN OR TRUE as TRUE and UNKNOWN AND FALSE as FALSE', () => {
    expect(q('"Pset_WallCommon.IsExternal" = TRUE OR class = \'IfcBeam\'')).toEqual([0, 2, 5]);
    // row 5 has no IsExternal: UNKNOWN AND TRUE is UNKNOWN, and NOT UNKNOWN stays UNKNOWN
    expect(q('NOT ("Pset_WallCommon.IsExternal" = TRUE AND class = \'IfcBeam\')')).toEqual([0, 1, 2, 3, 4]);
  });

  it('treats an empty name or material and no storey as NULL', () => {
    expect(q('name IS NULL')).toEqual([4]);
    expect(q('material IS NULL')).toEqual([2, 3, 4, 5]);
    expect(q('storey IS NULL')).toEqual([4]);
    expect(q("storey = 'Dachgeschoss'")).toEqual([2, 3]);
    expect(q('storeyElevation > 1')).toEqual([2, 3]);
  });

  it('compares numbers numerically, also against numeric strings', () => {
    expect(q('"BaseQuantities.NetVolume" > 2')).toEqual([0]);
    expect(q('"BaseQuantities.NetVolume" >= 1.5')).toEqual([0, 1]);
    expect(q('"Qto.Length" > 10')).toEqual([3]); // '12' (string) > 10
    expect(q("\"Qto.Length\" = '4.5'")).toEqual([5]);
    expect(q('"Qto.Length" < 9')).toEqual([5]); // numeric, not '12' < '9' as text
  });

  it('LIKE uses % and _, ignores case and anchors the pattern', () => {
    expect(q("name LIKE 'wall%'")).toEqual([0, 1, 2]);
    expect(q("name LIKE 'Wall_3'")).toEqual([2]);
    expect(q("name LIKE 'wall'")).toEqual([]);
    expect(q("name NOT LIKE 'wall%'")).toEqual([3, 5]); // the NULL name does not match NOT LIKE either
    expect(q("name LIKE '%\\%'")).toEqual([3]); // escaped %
    expect(q("\"Attr.ObjectType\" LIKE '%wall%'")).toEqual([2]);
  });

  it('IN and NOT IN with NULL members follow SQL', () => {
    expect(q("class IN ('IfcSlab', 'IfcBeam')")).toEqual([4, 5]);
    expect(q("class NOT IN ('IfcWall', 'IfcWallStandardCase', 'IfcSlab')")).toEqual([3, 5]);
    expect(q("class NOT IN ('IfcWall', NULL)")).toEqual([]);
    expect(q("class IN ('IfcWall', NULL)")).toEqual([0, 1]);
    expect(q("class in ('ifcwall', 'IFCSLAB')")).toEqual([0, 1, 4]);
    expect(q("\"Qto.Length\" IN ('12', '4.5')")).toEqual([3, 5]); // number 4.5 = numeric string '4.5'
    expect(q('"Qto.Length" IN (12, 4.5)')).toEqual([3, 5]);
  });

  it('BETWEEN is inclusive and works on bounds columns', () => {
    expect(q('xMin BETWEEN 1 AND 3')).toEqual([1, 2, 3]);
    expect(q('xmin NOT BETWEEN 1 AND 3')).toEqual([0, 4, 5]);
    expect(q('sizeX > 5 AND volume = 12.5 AND yMax = 0')).toEqual([4]);
    expect(q('id >= -1 AND id < 2')).toEqual([0, 1]);
  });

  it('matches every column of the flat row', () => {
    const row = T.rowOf(0);
    expect(row).toMatchObject({ class: 'IfcWall', globalId: 'G0', storey: 'Erdgeschoss', storeyElevation: 0, sizeX: 1, volume: 1, 'Pset_WallCommon.FireRating': 'EI60' });
    expect(q("globalId = 'G3'")).toEqual([3]);
  });

  it('reports unknown columns but keeps running', () => {
    const r = runQuery(M, '"Pset_Nope.X" = 1 OR class = \'IfcBeam\'');
    expect(r.error).toBeNull();
    expect(r.unknown).toEqual(['Pset_Nope.X']);
    expect(r.ids).toEqual([5]);
  });

  it('returns the error instead of throwing from runQuery', () => {
    const r = runQuery(M, "class = 'IfcWall' AND");
    expect(r.ids).toEqual([]);
    expect(r.error).toBeInstanceOf(QueryError);
    expect(r.error!.pos).toBe(21);
  });

  it('rejects a bare string as a condition', () => {
    expect(() => q("'IfcWall'")).toThrow(/text value alone/);
  });
});

describe('compareValues', () => {
  it('orders mixed types', () => {
    expect(compareValues(2, '10')).toBeLessThan(0);
    expect(compareValues('2', '10')).toBeGreaterThan(0); // two strings: text order
    expect(compareValues(true, 1)).toBe(0);
    expect(compareValues(false, 'no')).toBe(0);
    expect(compareValues(null, 1)).toBeNull();
    expect(compareValues('abc', 5)).not.toBe(0);
  });
});

describe('columns and values', () => {
  it('lists the core columns, then the property keys', () => {
    const cols = T.columns().map((c) => c.name);
    expect(cols.slice(0, 3)).toEqual(['class', 'name', 'storey']);
    expect(cols).toContain('Pset_WallCommon.IsExternal');
    expect(T.columns().find((c) => c.name === 'Pset_WallCommon.IsExternal')).toMatchObject({ count: 3, kind: 'boolean', core: false });
    expect(T.kind('Qto.Length')).toBe('mixed');
  });

  it('lists distinct values, most frequent first', () => {
    expect(T.distinct('class', 2)).toEqual([
      { value: 'IfcWall', count: 2 },
      { value: 'IfcBeam', count: 1 },
    ]);
    expect(T.distinct('Pset_WallCommon.IsExternal').map((d) => d.value)).toEqual([true, false]);
  });

  it('caches one table per model', () => {
    expect(modelTable(M)).toBe(modelTable(M));
  });
});

describe('writing queries and the row builder', () => {
  it('quotes names and literals', () => {
    expect(quoteIdent('class')).toBe('class');
    expect(quoteIdent('Pset_WallCommon.IsExternal')).toBe('"Pset_WallCommon.IsExternal"');
    expect(quoteIdent('Fire "x" Rating')).toBe('"Fire ""x"" Rating"');
    expect(quoteIdent('not')).toBe('"not"');
    expect(literal("it's")).toBe("'it''s'");
    expect(literal(true)).toBe('TRUE');
    expect(equalsQuery('Pset_WallCommon.IsExternal', true)).toBe('"Pset_WallCommon.IsExternal" = TRUE');
    expect(equalsQuery('material', null)).toBe('material IS NULL');
  });

  it('types builder values by column kind', () => {
    expect(typedLiteral('true', 'boolean')).toBe('TRUE');
    expect(typedLiteral('3.50', 'number')).toBe('3.5');
    expect(typedLiteral('3.50', 'string')).toBe("'3.50'");
    expect(typedLiteral('EI60', 'mixed')).toBe("'EI60'");
  });

  it('round trips builder rows through query text', () => {
    const text = conditionsText(
      {
        join: 'AND',
        conditions: [
          { column: 'class', op: 'IN', value: 'IfcWall, IfcWallStandardCase' },
          { column: 'Pset_WallCommon.IsExternal', op: '=', value: 'true' },
          { column: 'name', op: 'IS NOT NULL', value: '' },
        ],
      },
      (c) => T.kind(c),
    );
    expect(text).toBe('class IN (\'IfcWall\', \'IfcWallStandardCase\') AND "Pset_WallCommon.IsExternal" = TRUE AND name IS NOT NULL');
    expect(q(text)).toEqual([0, 2]);
    expect(toConditions(text)).toEqual({
      join: 'AND',
      conditions: [
        { column: 'class', op: 'IN', value: 'IfcWall, IfcWallStandardCase' },
        { column: 'Pset_WallCommon.IsExternal', op: '=', value: 'TRUE' },
        { column: 'name', op: 'IS NOT NULL', value: '' },
      ],
    });
  });

  it('gives up on queries the builder cannot show', () => {
    expect(toConditions('(a = 1 OR b = 2) AND c = 3')).toBeNull();
    expect(toConditions('x BETWEEN 1 AND 2')).toBeNull();
    expect(toConditions('a = b')).toBeNull();
    expect(toConditions('a =')).toBeNull();
    expect(toConditions("a = 1 OR name LIKE 'x%'")).toMatchObject({ join: 'OR' });
  });
});

const SLACK = (globalThis as { process?: { env?: Record<string, string | undefined> } }).process?.env?.['XRAY_PERF'] === '1' ? 1 : 5;

describe('performance', () => {
  it('filters 100,000 elements well under 100 ms', () => {
    const specs: Spec[] = [];
    const classes = ['IfcWall', 'IfcSlab', 'IfcBeam', 'IfcColumn', 'IfcDuctSegment'];
    for (let i = 0; i < 100_000; i++) {
      specs.push({
        cls: classes[i % 5]!,
        name: `El ${i}`,
        storey: i % 2,
        material: i % 3 ? 'Concrete' : 'Steel',
        props: { 'Pset_X.IsExternal': i % 4 === 0, 'Qto.NetVolume': (i % 100) / 10, 'Attr.ObjectType': `T${i % 50}` },
      });
    }
    const big = model(specs);
    const table = freshTable(big);
    const text = "class IN ('IfcWall', 'IfcBeam') AND \"Pset_X.IsExternal\" = TRUE AND \"Qto.NetVolume\" BETWEEN 1 AND 8 AND name LIKE 'el 1%' OR storey = 'Dachgeschoss' AND material != 'steel'";
    let n = 0;
    let ms = Infinity;
    for (let k = 0; k < 4; k++) {
      // best of 4 (the first run warms up the JIT)
      const t0 = performance.now();
      n = filterRows(text, table).length;
      ms = Math.min(ms, performance.now() - t0);
    }
    expect(n).toBe(filterRows(text, table).length);
    expect(n).toBeGreaterThan(0);
    // Strict budget with XRAY_PERF=1; otherwise 5x slack for a busy shared machine (as tests/performance.test.ts).
    expect(ms).toBeLessThan(100 * SLACK);
  });
});
