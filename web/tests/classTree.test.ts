import { describe, expect, it } from 'vitest';
import {
  NOT_CLASSIFIED, PRESETS, buildClassTree, legendRows, levelQuery, mapUniformat, needsReview, parseUniformat, ufAtLevel,
} from '../src/classify/classTree';
import type { ClassInfo } from '../src/classify/classTree';
import type { FacetId, FacetResult } from '../src/classify/facets/defs';
import uf from '../public/classification/uniformat2.json';

const fr = (facet: FacetId, code: string, review = false): FacetResult => ({ facet, code, label: code.toLowerCase(), confidence: review ? 0.4 : 0.95, source: 'rule', needsReview: review, fields: {} });
let n = 0;
const el = (ifcClass: string, f: Partial<Record<FacetId, [string, boolean?]>> = {}, extra: Partial<ClassInfo> = {}): ClassInfo => ({
  id: n, name: `${ifcClass} ${n++}`, globalId: `g${n}`, ifcClass, storey: 'Level 1',
  facets: Object.fromEntries(Object.entries(f).map(([k, v]) => [k, fr(k as FacetId, v![0], v![1])])),
  ...extra,
});

const infos = (): ClassInfo[] => {
  n = 0;
  return [
    el('IfcSlab', { Phase: ['FRAME'], Trade: ['CONC'] }),
    el('IfcSlab', { Phase: ['FRAME'], Trade: ['CONC', true] }),
    el('IfcWall', { Phase: ['ENVELOPE'], Trade: ['FACADE'], Placement: ['BOUNDARY'] }, { discipline: { code: 'ARC', label: 'Architecture' } }),
    el('IfcWall', { Phase: ['FRAME'], Trade: ['CONC'] }),
    el('IfcDoor', {}),
  ];
};

const table = parseUniformat(uf).table!;
const find = (nodes: ReturnType<typeof buildClassTree>, label: string) => nodes.find((x) => x.label.startsWith(label));

describe('buildClassTree', () => {
  it('groups Phase > Trade > class with counts, buckets and element leaves', () => {
    const roots = buildClassTree(infos(), { levels: PRESETS[0]!.levels, order: { Phase: ['SUBSTR', 'FRAME', 'ENVELOPE'] } });
    expect(roots.map((r) => r.label)).toEqual(['FRAME frame', 'ENVELOPE envelope', NOT_CLASSIFIED]);
    const frame = roots[0]!;
    expect(frame.count).toBe(3);
    expect(frame.children.map((c) => `${c.label}:${c.count}`)).toEqual(['CONC conc:3']);
    const conc = frame.children[0]!;
    expect(conc.children.map((c) => `${c.label}:${c.count}`)).toEqual(['IfcSlab:2', 'IfcWall:1']);
    expect(conc.children[0]!.children.every((e) => e.kind === 'element' && e.elementId !== null)).toBe(true);
    // the door has no Phase: Not classified at every level
    const nc = roots[2]!;
    expect(nc.count).toBe(1);
    expect(nc.children[0]!.label).toBe(NOT_CLASSIFIED);
    expect(nc.children[0]!.children[0]!.label).toBe('IfcDoor');
  });

  it('counts the elements that need review in every node', () => {
    const roots = buildClassTree(infos(), { levels: ['Phase', 'Trade'] });
    const frame = find(roots, 'FRAME')!;
    expect(frame.review).toBe(1);
    expect(frame.children[0]!.review).toBe(1);
    expect(find(roots, 'ENVELOPE')!.review).toBe(0);
    expect(needsReview(infos()[1]!)).toBe(true);
    expect(needsReview(infos()[0]!)).toBe(false);
  });

  it('gives each node the query of its path', () => {
    const roots = buildClassTree(infos(), { levels: ['Phase', 'Trade', 'IfcClass'] });
    const conc = find(roots, 'FRAME')!.children[0]!;
    expect(find(roots, 'FRAME')!.query).toBe("XR_Phase.Code = 'FRAME'");
    expect(conc.query).toBe("XR_Phase.Code = 'FRAME' and XR_Trade.Code = 'CONC'");
    expect(conc.children[0]!.query).toBe("XR_Phase.Code = 'FRAME' and XR_Trade.Code = 'CONC' and class = 'IfcSlab'");
    const nc = roots.find((r) => r.label === NOT_CLASSIFIED)!;
    expect(nc.query).toBe('XR_Phase.Code IS NULL');
    expect(nc.children[0]!.query).toBe('XR_Phase.Code IS NULL and XR_Trade.Code IS NULL');
  });

  it('uses the discipline columns, the storey and a facet that is not built in', () => {
    expect(levelQuery('Discipline', 'ARC', { discipline: 'XR_Class.Discipline', subDiscipline: 'x' })).toBe("XR_Class.Discipline = 'ARC'");
    expect(levelQuery('Storey', "Level 'A'")).toBe("storey = 'Level ''A'''");
    expect(levelQuery('Method', 'CIP')).toBe("XR_Method.Code = 'CIP'");
    const list = infos();
    list[0]!.facets = { ...list[0]!.facets, Method: fr('Trade', 'CIP') };
    const roots = buildClassTree(list, { levels: ['Method'] });
    expect(roots.map((r) => `${r.label}:${r.count}`)).toEqual(['CIP cip:1', `${NOT_CLASSIFIED}:4`]);
  });

  it('caps the levels at 4 and orders values by the given order, then alphabetically', () => {
    const roots = buildClassTree(infos(), { levels: ['Phase', 'Trade', 'Placement', 'IfcClass', 'Storey'] });
    let depth = 0;
    for (let c = roots[0]!; c.children.length && c.children[0]!.kind === 'group'; c = c.children[0]!) depth++;
    expect(depth).toBe(3);
    const byOrder = buildClassTree(infos(), { levels: ['Phase'], order: { Phase: ['ENVELOPE', 'FRAME'] } });
    expect(byOrder.map((r) => r.label.split(' ')[0])).toEqual(['ENVELOPE', 'FRAME', 'Not']);
  });

  it('builds the legend rows of a level', () => {
    const rows = legendRows(infos(), 'Trade', {});
    expect(rows.map((r) => [r.code, r.count, r.review, r.query])).toEqual([
      ['CONC', 3, 1, "XR_Trade.Code = 'CONC'"], ['FACADE', 1, 0, "XR_Trade.Code = 'FACADE'"], ['', 1, 0, 'XR_Trade.Code IS NULL'],
    ]);
    expect(rows[2]!.label).toBe(NOT_CLASSIFIED);
  });
});

describe('UniFormat II', () => {
  it('ships levels 1 to 3 with the standard titles', () => {
    expect(table.titles.get('A')).toBe('Substructure');
    expect(table.titles.get('B20')).toBe('Exterior Enclosure');
    expect(table.titles.get('B2010')).toBe('Exterior Walls');
    expect(table.levels.map((l) => l.code)).toEqual(['A', 'B', 'C', 'D', 'E', 'F', 'G']);
    expect(table.titles.get('G')).toBe('Building Sitework');
  });

  it('maps exterior walls to B2010, interior walls to C1010 and doors by placement', () => {
    expect(mapUniformat(table, el('IfcWallStandardCase', { Placement: ['BOUNDARY'] }))).toBe('B2010');
    expect(mapUniformat(table, el('IfcWall', { Placement: ['INT'] }))).toBe('C1010');
    expect(mapUniformat(table, el('IfcWall', { Phase: ['SUBSTR'] }))).toBe('A2020');
    expect(mapUniformat(table, el('IfcDoor', { Placement: ['EXT'] }))).toBe('B2030');
    expect(mapUniformat(table, el('IfcDoor', { Placement: ['INT'] }))).toBe('C1020');
    expect(mapUniformat(table, el('IfcSlab', { Phase: ['SUBSTR'] }))).toBe('A1030');
    expect(mapUniformat(table, el('IfcSlab', { Trade: ['ROOF'] }))).toBe('B3010');
    expect(mapUniformat(table, el('IfcDuctSegment', {}, { discipline: { code: 'MEC', label: 'Mechanical' } }))).toBe('D3040');
  });

  it('falls back to level 2 or 1 by phase, else to nothing', () => {
    expect(mapUniformat(table, el('IfcBuildingElementProxy', { Phase: ['ENVELOPE'] }))).toBe('B20');
    expect(mapUniformat(table, el('IfcBuildingElementProxy', {}, { discipline: { code: 'ELE', label: 'Electrical' } }))).toBe('D50');
    expect(mapUniformat(table, el('IfcBuildingElementProxy', {}))).toBeNull();
  });

  it('cuts a code at level 1, 2 and 3', () => {
    expect(ufAtLevel('B2010', 1)).toBe('B');
    expect(ufAtLevel('B2010', 2)).toBe('B20');
    expect(ufAtLevel('B2010', 3)).toBe('B2010');
    expect(ufAtLevel('B20', 3)).toBeNull();
    expect(ufAtLevel(null, 1)).toBeNull();
  });

  it('builds A > A10 > A1010 style paths with titles, and has no query', () => {
    const list = [el('IfcWall', { Placement: ['EXT'] }), el('IfcDoor', { Placement: ['INT'] }), el('IfcBuildingElementProxy', { Phase: ['ENVELOPE'] }), el('IfcBuildingElementProxy', {})];
    const roots = buildClassTree(list, { levels: PRESETS[3]!.levels, uniformat: table });
    expect(roots.map((r) => r.label)).toEqual(['B Shell', 'C Interiors', NOT_CLASSIFIED]);
    const b = roots[0]!;
    expect(b.count).toBe(2);
    expect(b.children.map((c) => c.label)).toEqual(['B20 Exterior Enclosure']);
    expect(b.children[0]!.children.map((c) => `${c.label}:${c.count}`)).toEqual(['B2010 Exterior Walls:1', NOT_CLASSIFIED + ':1']);
    expect(b.query).toBeNull();
    expect(b.children[0]!.children[0]!.query).toBeNull();
  });

  it('rejects a broken table in plain words', () => {
    expect(parseUniformat({}).table).toBeNull();
    const bad = parseUniformat({ schema: 'xray-uniformat2/1', levels: [{ code: 'A', title: 'x' }], rules: [{ when: {}, code: 'Z9' }] });
    expect(bad.table).toBeNull();
    expect(bad.errors[0]).toMatch(/Z9/);
  });

  it('only uses codes that are in the table', () => {
    for (const r of table.rules) expect(table.titles.has(r.code), r.code).toBe(true);
    for (const c of Object.values(table.fallbacks)) expect(table.titles.has(c), c).toBe(true);
  });
});
