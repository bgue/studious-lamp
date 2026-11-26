// The concrete engine on a synthetic building (footing, slab on grade, columns, beam, suspended slab, walls): roles, marks, pour groups,
// supports, spec, reinforcement intent, one question per signature, queries and export columns.

import { describe, expect, it } from 'vitest';
import { classifyConcrete } from '../src/classify/concrete/engine';
import type { ConcreteItem } from '../src/classify/concrete/engine';
import { concreteCsvColumns, concreteCsvCells, concreteSetProperties, makeManualConcrete } from '../src/classify/concrete/write';
import { CONCRETE_FACET_IDS, CONCRETE_FIELDS, Q_CONCRETE } from '../src/classify/concrete/defs';
import { MemoryFacetCache } from '../src/classify/facets/engine';
import { runQuery } from '../src/query';
import { exportCsv } from '../src/classify/results';
import type { Answers, Questions } from '../src/classify/jevAdapter';
import type { ClassifyInput, DecisionModel } from '../src/classify/types';
import type { SceneModel } from '../src/types';
import { block, circle, prism } from './concrete-helpers';
import type { Mesh } from './concrete-helpers';

const input = (id: string, cls: string, name: string, o: Partial<ClassifyInput> = {}): ClassifyInput => ({ id, ifcClass: cls, name, psets: {}, material: 'Concrete C30/37', ...o });
const item = (i: ClassifyInput, mesh: Mesh, o: Partial<ConcreteItem> = {}): ConcreteItem => ({ input: i, mesh: () => mesh, storey: 0, ...o });

function building(): ConcreteItem[] {
  const out: ConcreteItem[] = [];
  out.push(item(input('F1', 'IfcFooting', 'Footing F1'), block(-5, -5, -1.0, 2, 2, 0.8), { belowGround: true }));
  out.push(item(input('SOG', 'IfcSlab', 'Ground slab', { psets: { Attr: { PredefinedType: 'BASESLAB' } } }), block(-6, -6, -0.2, 12, 12, 0.2)));
  for (const [i, [x, y]] of ([[-4.4, -4.4], [4.4, -4.4], [-4.4, 4.4], [4.4, 4.4]] as const).entries()) out.push(item(input(`C${i + 1}`, 'IfcColumn', `Column ${i + 1}`, { material: 'Concrete C30/37' }), block(x - 0.2, y - 0.2, 0, 0.4, 0.4, 2.6)));
  out.push(item(input('B1', 'IfcBeam', 'Beam B1'), block(-4.6, -4.6, 2.6, 9.2, 0.4, 0.4), { storey: 1 }));
  out.push(item(input('S1', 'IfcSlab', 'Floor slab', { psets: { Attr: { PredefinedType: 'FLOOR' } } }), block(-6, -6, 3.0, 12, 12, 0.2), { storey: 1 }));
  out.push(item(input('W1', 'IfcWall', 'Wall W1', { psets: { Pset_WallCommon: { LoadBearing: true } } }), block(-6, 6, 0, 12, 0.25, 3.0)));
  out.push(item(input('WALL-STEEL', 'IfcWall', 'Steel stud wall', { material: 'Steel' }), block(0, 0, 0, 4, 0.1, 3)));
  return out;
}

function provider(pick: (q: string, options: string[]) => string, conf = 0.9): DecisionModel & { calls: Array<{ questions: Questions; state: Record<string, unknown> }> } {
  const calls: Array<{ questions: Questions; state: Record<string, unknown> }> = [];
  return {
    provider: 'mock', calls,
    async decide(state, questions): Promise<Answers> {
      calls.push({ questions, state });
      const answers: Answers['answers'] = {};
      for (const [name, q] of Object.entries(questions)) {
        if (q.type !== 'choice') continue;
        const options = Object.keys(q.criteria);
        const want = pick(name, options);
        const rest = options.filter((x) => x !== want);
        const probabilities: Record<string, number> = { [want]: conf };
        rest.forEach((x) => { probabilities[x] = (1 - conf) / rest.length; });
        answers[name] = { type: 'choice', choice: want, confidence: conf, probabilities };
      }
      return { model: 'test-model', answers };
    },
  };
}

describe('the concrete family', () => {
  it('skips elements that are not concrete', async () => {
    const run = await classifyConcrete(building(), { groundLevel: 0 });
    expect(run.results.has('WALL-STEEL')).toBe(false);
    expect(run.results.size).toBe(building().length - 1);
    expect(run.stats.elements).toBe(building().length - 1);
  });
});

describe('roles, marks, groups and supports', () => {
  it('assigns roles by rule', async () => {
    const run = await classifyConcrete(building(), { groundLevel: 0 });
    const role = (id: string): string => run.results.get(id)!.ConcreteElement!.code;
    expect(role('F1')).toBe('PAD_FOOTING');
    expect(role('SOG')).toBe('SLAB_ON_GRADE');
    expect(role('C1')).toBe('COLUMN');
    expect(role('B1')).toBe('BEAM');
    expect(role('S1')).toBe('SUSPENDED_SLAB');
    expect(role('W1')).toBe('WALL');
  });
  it('generates stable marks in a fixed order, and uses a unique IFC Tag', async () => {
    const a = await classifyConcrete(building(), { groundLevel: 0 });
    const marks = (r: typeof a): string[] => ['C1', 'C2', 'C3', 'C4', 'S1', 'W1', 'SOG', 'B1', 'F1'].map((id) => r.results.get(id)!.ConcreteElement!.fields['Mark'] as string);
    expect(marks(a)).toEqual(['C0-01', 'C0-03', 'C0-02', 'C0-04', 'S1-01', 'W0-01', 'SG0-01', 'B1-01', 'FP0-01']);
    // shuffled input, same marks
    const b = await classifyConcrete([...building()].reverse(), { groundLevel: 0 });
    expect(marks(b)).toEqual(marks(a));
    const items = building();
    items[2]!.input.psets = { Attr: { Tag: 'COL-A' } };
    items[3]!.input.psets = { Attr: { Tag: 'COL-A' } };
    items[4]!.input.psets = { Attr: { Tag: 'COL-X' } };
    const c = await classifyConcrete(items, { groundLevel: 0 });
    expect(c.results.get('C3')!.ConcreteElement!.fields['Mark']).toBe('COL-X');
    expect(c.results.get('C3')!.ConcreteElement!.fields['MarkSource']).toBe('ifc');
    expect(c.results.get('C1')!.ConcreteElement!.fields['MarkSource']).toBe('generated'); // COL-A twice
  });
  it('supports are the contact graph refined by faces', async () => {
    const run = await classifyConcrete(building(), { groundLevel: 0 });
    const s1 = run.results.get('S1')!.ConcreteGeometry!.fields;
    expect(s1['Supports']).toBe('B1');
    const b1 = run.results.get('B1')!.ConcreteGeometry!.fields;
    expect(String(b1['Supports']).split(',').sort()).toEqual(['C1', 'C2', 'C3', 'C4'].filter((c) => c === 'C1' || c === 'C2'));
    expect(b1['Carries']).toBe('S1');
  });
  it('pour groups: a slab and its beam are one group on a storey', async () => {
    const run = await classifyConcrete(building(), { groundLevel: 0 });
    const g = (id: string): unknown => run.results.get(id)!.ConcreteElement!.fields['HostGroup'];
    expect(g('S1')).toBe('PG-1-1');
    expect(g('B1')).toBe('PG-1-1');
    expect(g('C1')).toMatch(/^PG-0-\d+$/);
    expect(g('C1')).not.toBe(g('S1'));
  });
  it('a precast element has no pour group', async () => {
    const items = building();
    items[7] = item(input('S1', 'IfcSlab', 'Hollow core plank', { psets: { Pset_PrecastConcreteElementGeneral: { PieceMark: 'HC-1' } } }), block(-6, -6, 3.0, 12, 12, 0.2), { storey: 1 });
    const run = await classifyConcrete(items, { groundLevel: 0 });
    expect(run.results.get('S1')!.ConcreteMethod!.code).toBe('PRECAST');
    expect(run.results.get('S1')!.ConcreteElement!.fields['HostGroup']).toBeUndefined();
    expect(run.results.get('S1')!.ConcreteElement!.fields['Mark']).toBe('HC-1');
  });
});

describe('marks from the IFC', () => {
  it('a GUID or UUID Tag is not a mark; a readable one is', async () => {
    const items = building();
    items[2]!.input.psets = { Attr: { Tag: 'E4D9CD4B-CA43-4735-94-BD-1FD4376BD455' } };
    items[3]!.input.psets = { Attr: { Tag: '2O2Fr$t4X7Zf8NhR4$yBo3' } };
    items[4]!.input.psets = { Attr: { Tag: 'K-12' } };
    const run = await classifyConcrete(items, { groundLevel: 0 });
    expect(run.results.get('C1')!.ConcreteElement!.fields['MarkSource']).toBe('generated');
    expect(run.results.get('C2')!.ConcreteElement!.fields['MarkSource']).toBe('generated');
    expect(run.results.get('C3')!.ConcreteElement!.fields['Mark']).toBe('K-12');
  });
});

describe('measured geometry in the sets', () => {
  it('volume, frame, dimensions, formwork', async () => {
    const run = await classifyConcrete(building(), { groundLevel: 0 });
    const s = run.results.get('S1')!.ConcreteGeometry!;
    expect(s.fields['Volume']).toBeCloseTo(28.8, 2);
    expect(s.fields['VolumeEstimated']).toBe(false);
    expect(s.fields['FrameZ']).toBe('0 0 1');
    expect(s.fields['Thickness']).toBeCloseTo(0.2, 2);
    expect(String(s.fields['Faces'])).toContain('TOP 144');
    const sog = run.results.get('SOG')!.ConcreteGeometry!;
    expect(sog.fields['SoffitArea']).toBeCloseTo(0, 1); // against the ground
    expect(String(sog.fields['Faces'])).toMatch(/BOTTOM 144 .*G/);
    // the slab on grade bears on nothing; the column rests on the slab on grade
    const c1 = run.results.get('C1')!.ConcreteGeometry!;
    expect(c1.fields['Supports']).toBe('SOG');
  });
});

describe('spec and reinforcement', () => {
  it('strength from the material, exposure suggested with review, cover from the table, ratio estimate', async () => {
    const items = building().map((it) => ({ ...it, placement: it.input.id === 'W1' ? 'BOUNDARY' : 'INT' }));
    const run = await classifyConcrete(items, { groundLevel: 0 });
    const spec = run.results.get('W1')!.ConcreteSpec!;
    expect(spec.code).toBe('C30/37');
    expect(spec.fields['Standard']).toBe('EN206');
    expect(spec.fields['ExposureClass']).toBe('XC4, XF1');
    expect(spec.fields['ExposureSource']).toBe('suggested');
    expect(spec.needsReview).toBe(true);
    expect(spec.fields['CoverNominal']).toBe(40);
    expect(spec.fields['Derived']).toContain('ExposureClass');
    const re = run.results.get('S1')!.ConcreteReinforcement!;
    expect(re.code).toBe('REINFORCED');
    expect(re.fields['Scheme']).toBe('TWO_WAY'); // square span ratio
    expect(re.fields['RatioEstimate']).toBe(105);
    expect(re.fields['MassEstimate']).toBeCloseTo(105 * 28.8, 0);
    expect(run.results.get('C1')!.ConcreteReinforcement!.fields['Scheme']).toBe('LINKS');
  });
  it('IFC values win and are not marked as derived', async () => {
    const items = building();
    items[7] = item(input('S1', 'IfcSlab', 'Floor slab', { psets: { Attr: { PredefinedType: 'FLOOR' }, Pset_ConcreteElementGeneral: { StrengthClass: 'C35/45', ExposureClass: 'XC3', ConcreteCover: 0.03, ReinforcementVolumeRatio: 120 }, Pset_SlabCommon: { FireRating: 'REI 90' } } }), block(-6, -6, 3.0, 12, 12, 0.2), { storey: 1 });
    const run = await classifyConcrete(items, { groundLevel: 0 });
    const spec = run.results.get('S1')!.ConcreteSpec!;
    expect(spec.code).toBe('C35/45');
    expect(spec.source).toBe('ifc');
    expect(spec.fields['ExposureClass']).toBe('XC3');
    expect(spec.fields['ExposureSource']).toBe('ifc');
    expect(spec.fields['CoverNominal']).toBe(30);
    expect(spec.fields['FireResistance']).toBe('REI90');
    expect(String(spec.fields['Derived'] ?? '')).not.toContain('StrengthClass');
    expect(run.results.get('S1')!.ConcreteReinforcement!.fields['RatioEstimate']).toBe(120);
    expect(run.results.get('S1')!.ConcreteReinforcement!.fields['RatioSource']).toBe('ifc');
  });
});

describe('the decision model', () => {
  it('asks once per signature, with only the roles allowed for the class', async () => {
    const items: ConcreteItem[] = [];
    // three identical odd slabs (a footing-sized plate with no support) and one odd column-like proxy
    for (let i = 0; i < 3; i++) items.push(item(input(`P${i}`, 'IfcBuildingElementProxy', 'Thing', { psets: { Pset_ConcreteElementGeneral: { StrengthClass: 'C25/30' } } }), block(10 * i, 0, 0, 2, 2, 0.4)));
    items.push(item(input('M1', 'IfcMember', 'Odd member', { psets: { Pset_ConcreteElementGeneral: { StrengthClass: 'C25/30' } } }), block(30, 0, 0, 0.3, 4, 0.3)));
    const p = provider((q, options) => (q === Q_CONCRETE.role ? (options.includes('PLINTH') ? 'PLINTH' : options[0]!) : options[0]!));
    const run = await classifyConcrete(items, { provider: p, groundLevel: 0 });
    const roleCalls = p.calls.filter((c) => Q_CONCRETE.role in c.questions);
    expect(roleCalls.length).toBe(2); // the three proxies share a signature, the member differs
    expect(run.results.get('P0')!.ConcreteElement!.source).toBe('model');
    expect(run.results.get('P0')!.ConcreteElement!.code).toBe('PLINTH');
    expect(run.stats.signatures).toBeGreaterThanOrEqual(2);
  });
  it('a slab is never asked COLUMN', async () => {
    const items = [item(input('X', 'IfcSlab', 'Mystery slab'), block(0, 0, 5, 3, 3, 0.2), { storey: 2 })];
    const p = provider((_q, options) => options[0]!);
    await classifyConcrete(items, { provider: p, groundLevel: 0 });
    for (const c of p.calls) { const q = c.questions[Q_CONCRETE.role]; if (q && q.type === 'choice') expect(Object.keys(q.criteria)).not.toContain('COLUMN'); }
    const q = p.calls.map((c) => c.questions[Q_CONCRETE.role]).find(Boolean);
    expect(q && q.type === 'choice' ? Object.keys(q.criteria) : []).toContain('SUSPENDED_SLAB');
  });
});

describe('cache, manual choices and switches', () => {
  it('the cache answers the second run without a request', async () => {
    const mk = (): ConcreteItem[] => [item(input('X', 'IfcSlab', 'Mystery slab'), block(0, 0, 5, 3, 3, 0.2), { storey: 2 })];
    const cache = new MemoryFacetCache();
    const p = provider((_q, options) => options[1]!);
    await classifyConcrete(mk(), { provider: p, cache, groundLevel: 0 });
    const n = p.calls.length;
    expect(n).toBeGreaterThan(0);
    const run = await classifyConcrete(mk(), { provider: p, cache, groundLevel: 0 });
    expect(p.calls.length).toBe(n);
    expect(run.results.get('X')!.ConcreteElement!.source).toBe('model');
    expect(run.stats.bySource['role']?.['cache']).toBe(1);
  });
  it('a manual role wins, changes the mark prefix and is never asked', async () => {
    const items = [item(input('X', 'IfcSlab', 'Mystery slab'), block(0, 0, 5, 3, 3, 0.2), { storey: 2 })];
    const p = provider((_q, options) => options[0]!);
    const manual = new Map([['X', { ConcreteElement: makeManualConcrete('ConcreteElement', 'TRANSFER_SLAB') }]]);
    const run = await classifyConcrete(items, { provider: p, manual, groundLevel: 0 });
    const e = run.results.get('X')!.ConcreteElement!;
    expect(e.code).toBe('TRANSFER_SLAB');
    expect(e.source).toBe('manual');
    expect(e.fields['Mark']).toBe('TS2-01');
    expect(p.calls.some((c) => Q_CONCRETE.role in c.questions)).toBe(false);
    expect(() => makeManualConcrete('ConcreteElement', 'NOPE')).toThrow(/not a Element code/);
  });
  it('no model: a weak rule is kept and flagged for review', async () => {
    const run = await classifyConcrete([item(input('X', 'IfcSlab', 'Mystery slab'), block(0, 0, 5, 3, 3, 0.2), { storey: 2 })], { groundLevel: 0 });
    expect(run.results.get('X')!.ConcreteElement!.needsReview).toBe(true);
    expect(run.results.get('X')!.ConcreteElement!.code).toBe('SUSPENDED_SLAB');
  });
  it('a failing model leaves the weak rule and reports the error', async () => {
    const bad: DecisionModel = { provider: 'bad', async decide() { throw new Error('boom'); } };
    const run = await classifyConcrete([item(input('X', 'IfcSlab', 'Mystery slab'), block(0, 0, 5, 3, 3, 0.2), { storey: 2 })], { provider: bad, groundLevel: 0, retry: { retries: 0 } });
    expect(run.results.get('X')!.ConcreteElement!.code).toBe('SUSPENDED_SLAB');
    expect(run.stats.errors.join(' ')).toContain('boom');
  });
  it('a set that is switched off is not returned', async () => {
    const run = await classifyConcrete(building(), { groundLevel: 0, enabled: { ConcreteSpec: false } });
    expect(run.results.get('S1')!.ConcreteSpec).toBeUndefined();
    expect(run.results.get('S1')!.ConcreteElement).toBeDefined();
  });
  it('a round column and a mesh with no triangles', async () => {
    const run = await classifyConcrete([item(input('R', 'IfcColumn', 'Round'), prism(circle(0, 0, 0.25, 32), 'Z', 0, 3)), { input: input('E', 'IfcColumn', 'No geometry') }], { groundLevel: 0 });
    expect(run.results.get('R')!.ConcreteGeometry!.fields['SectionShape']).toBe('CIRC');
    expect(run.results.get('E')!.ConcreteGeometry).toBeUndefined();
    expect(run.results.get('E')!.ConcreteElement!.code).toBe('COLUMN');
  });
});

describe('properties, queries and export', () => {
  async function modelFrom(items: ConcreteItem[]): Promise<{ model: SceneModel; run: Awaited<ReturnType<typeof classifyConcrete>> }> {
    const run = await classifyConcrete(items, { groundLevel: 0 });
    const elements = items.map((it, id) => ({ id, globalId: it.input.id, ifcClass: it.input.ifcClass, name: it.input.name, storey: 0, color: [1, 1, 1, 1] as [number, number, number, number], bounds: [0, 0, 0, 1, 1, 1] as [number, number, number, number, number, number], props: run.results.has(it.input.id) ? concreteSetProperties(run.results.get(it.input.id)!) : {} }));
    const model = { schema: 'xray-model/1', units: 'm', originShift: [0, 0, 0], storeys: [{ id: 0, name: 'EG', elevation: 0 }], elements, relations: { voids: [], fills: [], hosts: [], ports: [], systems: [] }, byGlobalId: new Map(elements.map((e) => [e.globalId, e.id])) } as unknown as SceneModel;
    return { model, run };
  }
  it('the namespace and the property types', async () => {
    const { run } = await classifyConcrete(building(), { groundLevel: 0 }).then((r) => ({ run: r }));
    const p = concreteSetProperties(run.results.get('S1')!);
    expect(p['XR_ConcreteElement.Code']).toBe('SUSPENDED_SLAB');
    expect(p['XR_ConcreteElement.SchemeVersion']).toBe('xr-concrete/1');
    expect(typeof p['XR_ConcreteGeometry.Volume']).toBe('number');
    expect(typeof p['XR_ConcreteGeometry.VolumeEstimated']).toBe('boolean');
    expect(p['XR_ConcreteSpec.StrengthClass']).toBe('C30/37');
    expect(p['XR_ConcreteMethod.Code']).toBe('CAST_IN_PLACE');
    expect(Object.keys(p).every((k) => /^XR_Concrete(Geometry|Element|Method|Spec|Reinforcement)\./.test(k))).toBe(true);
  });
  it('query examples work: sum Volume by StrengthClass, counts, contains', async () => {
    const items = building();
    items[7] = item(input('S1', 'IfcSlab', 'Floor slab', { material: 'Concrete C35/45', psets: { Attr: { PredefinedType: 'FLOOR' }, Pset_ConcreteElementGeneral: { ExposureClass: 'XD2, XC4' } } }), block(-6, -6, 3.0, 12, 12, 0.2), { storey: 1 });
    const { model } = await modelFrom(items);
    expect(runQuery(model, "ConcreteElement = 'SUSPENDED_SLAB'").ids).toEqual([7]);
    expect(runQuery(model, "XR_ConcreteSpec.ExposureClass contains 'XD'").ids).toEqual([7]);
    const { runAggregate, modelTable } = await import('../src/query/aggregate').then(async (a) => ({ runAggregate: a.runAggregate, modelTable: (await import('../src/query/table')).modelTable }));
    const s = runAggregate(modelTable(model), 'sum XR_ConcreteGeometry.Volume by XR_ConcreteSpec.StrengthClass');
    const rows = Object.fromEntries((s.groups ?? []).map((g) => [g.key, g.aggs[0]!.value as number]));
    expect(rows['C35/45']).toBeCloseTo(28.8, 1);
    expect(rows['C30/37']).toBeGreaterThan(30);
    const f = runAggregate(modelTable(model), 'sum FormworkArea by Storey');
    expect(f.groups!.length).toBeGreaterThan(0);
  });
  it('CSV gains the concrete columns; every field of every set is a column', async () => {
    const { run } = await modelFrom(building());
    const cols = concreteCsvColumns();
    for (const f of CONCRETE_FACET_IDS) for (const [k] of CONCRETE_FIELDS[f]) expect(cols).toContain(`XR_${f}.${k}`);
    const cells = concreteCsvCells(run.results.get('S1'), cols);
    expect(cells[cols.indexOf('XR_ConcreteElement.Code')]).toBe('SUSPENDED_SLAB');
    expect(concreteCsvCells(undefined, cols).every((c) => c === '')).toBe(true);
    const csv = exportCsv([], undefined, undefined, run.results);
    const header = csv.split('\r\n')[0]!.split(',');
    expect(header).toContain('XR_ConcreteGeometry.Volume');
    expect(csv.split('\r\n').filter(Boolean).length).toBe(1 + run.results.size);
  });
});
