import { describe, expect, it } from 'vitest';
import type { ClassifyResult } from '../src/classify/types';
import { assign, mergeAssignments } from '../src/map4d/assignments';
import { suggest, tradeOfClass } from '../src/map4d/suggest';
import type { SuggestElement } from '../src/map4d/suggest';
import { resolveTarget } from '../src/map4d/targets';
import { DEFAULT_CLASS_TRADE, DEFAULT_TRADES, absorb, addValue, cleanValue, defaultLists, knownValues, removeFromList, renameInList, setColour } from '../src/map4d/values';
import type { SceneModel } from '../src/types';

const g = (n: number): string => String(n).padStart(22, 'A');
const el = (n: number, ifcClass: string, o: Partial<SuggestElement> = {}): SuggestElement => ({ globalId: g(n), ifcClass, storey: 'Level 1', ...o });
const result = (id: string, code: string, label: string, conf: number, division?: string): ClassifyResult => ({
  id, discipline: { code, label, confidence: conf, probabilities: {} }, subDiscipline: null,
  masterformat: division ? { division, title: 'Title', confidence: conf, probabilities: {} } : null, buildingElement: 1, source: 'rules', needsReview: false,
});
const NOW = '2027-01-01T00:00:00Z';
let k = 0;
const idGen = (): string => `s${++k}`;

describe('suggestions', () => {
  it('proposes the storey as location and the group as zone, with reasons and confidence', () => {
    const out = suggest([el(1, 'IfcSlab', { zones: ['Zone A'] })], { now: NOW, idGen, attributes: ['location', 'zone'] });
    expect(out.map((a) => [a.attribute, a.value, a.status, a.confidence])).toEqual([['location', 'Level 1', 'proposed', 0.9], ['zone', 'Zone A', 'proposed', 0.9]]);
    expect(out[0]!.reasons![0]).toContain('Level 1');
    expect(out.every((a) => a.source === 'suggested' && !('reviewed_by' in a))).toBe(true);
  });

  it('takes the trade from the class table, and a material rule beats the bare class', () => {
    expect(tradeOfClass(DEFAULT_CLASS_TRADE, 'IfcWall')!.trade).toBe('MASONRY');
    expect(tradeOfClass(DEFAULT_CLASS_TRADE, 'IfcWall', 'Concrete C30')).toMatchObject({ trade: 'CONC', byMaterial: true });
    expect(tradeOfClass(DEFAULT_CLASS_TRADE, 'IfcBeam', 'Steel S355')!.trade).toBe('STEEL');
    expect(tradeOfClass(DEFAULT_CLASS_TRADE, 'IfcBeam')!.trade).toBe('CONC');
    expect(tradeOfClass(DEFAULT_CLASS_TRADE, 'IfcNothing')).toBeNull();
    const out = suggest([el(1, 'IfcDuctSegment'), el(2, 'IfcSpace'), el(3, 'IfcBuildingElementProxy')], { now: NOW, idGen, attributes: ['trade'] });
    expect(out.map((a) => [a.element, a.value, a.confidence])).toEqual([[g(1), 'MEP-MECH', 0.7]]);
  });

  it('adds the classifier discipline and division, raises confidence when they agree and names the disagreement', () => {
    const results = new Map([[g(1), result(g(1), 'MEC', 'Mechanical', 0.9, '23')], [g(2), result(g(2), 'ELE', 'Electrical', 0.95)]]);
    const out = suggest([el(1, 'IfcDuctSegment'), el(2, 'IfcDuctSegment')], { now: NOW, idGen, attributes: ['trade'], results });
    const a = out.find((x) => x.element === g(1))!;
    expect(a.value).toBe('MEP-MECH');
    expect(a.confidence).toBeCloseTo(0.91, 2); // 0.81 from the discipline, plus 0.05 each for the division and the class
    expect(a.reasons!.length).toBe(3);
    expect(a.source).toBe('classifier');
    const b = out.find((x) => x.element === g(2))!;
    expect(b.value).toBe('MEP-ELEC'); // 0.855 beats the class table's 0.7
    expect(b.reasons!.some((r) => r.startsWith('Not MEP-MECH'))).toBe(true);
  });

  it('skips elements that already have an accepted value or the same open proposal', () => {
    const have = assign([], [g(1)], 'location', 'Level 1', { idGen }).list;
    const first = suggest([el(1, 'IfcSlab'), el(2, 'IfcSlab')], { now: NOW, idGen, existing: have, attributes: ['location']});
    expect(first.map((a) => a.element)).toEqual([g(2)]);
    const again = suggest([el(2, 'IfcSlab')], { now: NOW, idGen, existing: mergeAssignments(have, first).list, attributes: ['location'] });
    expect(again).toEqual([]);
  });
});

describe('value lists', () => {
  it('seeds the default trades, adds, renames, colours and removes', () => {
    let l = defaultLists();
    expect(l.trade.map((v) => v.name)).toEqual([...DEFAULT_TRADES]);
    expect(DEFAULT_TRADES).toEqual(['CONC', 'STEEL', 'MASONRY', 'FACADE', 'ROOF', 'MEP-MECH', 'MEP-ELEC', 'MEP-PLUMB', 'FINISHES', 'SITE']);
    const a = addValue(l, 'location', '  Level   3 ');
    expect(a.name).toBe('Level 3');
    l = a.lists;
    expect(addValue(l, 'location', 'Level 3').added).toBe(false);
    expect(renameInList(l, 'location', 'Level 3', 'L3').ok).toBe(true);
    expect(renameInList(l, 'trade', 'CONC', 'STEEL').ok).toBe(false);
    l = setColour(l, 'trade', 'CONC', '#AABBCC');
    expect(l.trade[0]!.colour).toBe('#aabbcc');
    l = setColour(l, 'trade', 'CONC', 'red');
    expect(l.trade[0]!.colour).toBe('#aabbcc');
    expect(removeFromList(l, 'trade', 'ROOF').trade.some((v) => v.name === 'ROOF')).toBe(false);
    expect(cleanValue('x'.repeat(300))).toHaveLength(255);
  });

  it('lists values that assignments use but the list lacks (an import)', () => {
    const list = assign([], [g(1)], 'zone', 'Zone Q', { idGen }).list;
    expect(knownValues(defaultLists(), list, 'zone').map((v) => v.name)).toEqual(['Zone Q']);
    expect(absorb(defaultLists(), list).zone.map((v) => v.name)).toEqual(['Zone Q']);
  });
});

describe('targets', () => {
  const elements = [
    { id: 0, globalId: g(1), ifcClass: 'IfcSlab', storey: 0, name: 'S1' }, { id: 1, globalId: g(2), ifcClass: 'IfcWall', storey: 0, name: 'W1' }, { id: 2, globalId: g(3), ifcClass: 'IfcWall', storey: 1, name: 'W2' },
  ];
  const model = { elements, storeys: [{ id: 0, name: 'Ground', elevation: 0 }, { id: 1, name: 'Level 1', elevation: 3 }], byGlobalId: new Map(elements.map((e, i) => [e.globalId, i])), relations: { systems: [] } } as unknown as SceneModel;
  const ctx = { model, selection: [2], sets: [{ name: 'Walls', globalIds: [g(2)] }, { name: 'Slabs', globalIds: [], kind: 'criteria' as const, query: "class = 'IfcSlab'" }] };
  it('resolves selection, storey, query, set and ids', () => {
    expect(resolveTarget({ selection: true }, ctx).ids).toEqual([2]);
    expect(resolveTarget({ storey: 'Ground' }, ctx).ids).toEqual([0, 1]);
    expect(resolveTarget({ storey: 1 }, ctx).ids).toEqual([2]);
    expect(resolveTarget({ query: "class = 'IfcWall'" }, ctx).ids).toEqual([1, 2]);
    expect(resolveTarget({ set: 'Walls' }, ctx).ids).toEqual([1]);
    expect(resolveTarget({ set: 'Slabs' }, ctx).ids).toEqual([0]);
    expect(resolveTarget({ ids: [0, 7] }, ctx).ids).toEqual([0]);
    expect(resolveTarget({ globalIds: [g(3), 'nope'] }, ctx).ids).toEqual([2]);
  });
  it('reports a bad query, storey or set instead of throwing', () => {
    expect(resolveTarget({ query: 'class = ' }, ctx).error).toBeTruthy();
    expect(resolveTarget({ storey: 'Roof' }, ctx).error).toContain('Roof');
    expect(resolveTarget({ set: 'Nope' }, ctx).error).toContain('Nope');
  });
});
