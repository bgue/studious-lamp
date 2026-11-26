// Facets engine: schema with and without the facets section, the questions, one request per signature, calibration and review,
// the property names and types, manual overrides, the query alias and the CSV and JSON export columns.

import { describe, expect, it } from 'vitest';
import { defaultSchema, parseSchema, schemaHash } from '../src/classify';
import { classifyFacets, facetQuestions, MemoryFacetCache, orientationResult, Q_FACET, Q_LOAD_BEARING } from '../src/classify/facets/engine';
import { defaultFacetDefs, FACET_IDS, FACETS_VERSION, facetsSection, parseFacets } from '../src/classify/facets/defs';
import { measureOrientation } from '../src/classify/facets/orientation';
import { facetCsvColumns, facetProperties, facetPropertyNames, facetSetProperties, makeManualFacet } from '../src/classify/facets/write';
import { exportCsv, exportJson } from '../src/classify/results';
import { facetDefs, facetsHash } from '../src/classify/schema';
import { freshTable, filterRows, runQuery } from '../src/query';
import type { Answers, Questions } from '../src/classify/jevAdapter';
import type { ClassifyInput, DecisionModel } from '../src/classify/types';
import type { SceneModel } from '../src/types';
import { box } from './facets-helpers';

const schema = defaultSchema();
const defs = facetDefs(schema);
const input = (id: string, cls: string, o: Partial<ClassifyInput> = {}): ClassifyInput => ({ id, ifcClass: cls, name: id, psets: {}, ...o });

/** A provider that answers every choice with its first-listed preferred option and counts the requests. */
function provider(pick: (q: string, options: string[], state: Record<string, unknown>) => string, conf = 0.9): DecisionModel & { calls: Array<{ state: Record<string, unknown>; questions: Questions }> } {
  const calls: Array<{ state: Record<string, unknown>; questions: Questions }> = [];
  return {
    provider: 'mock',
    calls,
    async decide(state, questions): Promise<Answers> {
      calls.push({ state, questions });
      const answers: Answers['answers'] = {};
      for (const [name, q] of Object.entries(questions)) {
        if (q.type === 'noul') { answers[name] = { type: 'noul', noul: 0.97 }; continue; }
        if (q.type !== 'choice') continue;
        const options = Object.keys(q.criteria);
        const want = pick(name, options, state);
        const rest = options.filter((o) => o !== want);
        const probabilities: Record<string, number> = { [want]: conf };
        rest.forEach((o) => { probabilities[o] = (1 - conf) / rest.length; });
        answers[name] = { type: 'choice', choice: want, confidence: conf, probabilities };
      }
      return { model: 'test-model', answers };
    },
  };
}

describe('schema facets section', () => {
  it('the shipped schema has the facets with the codes of the design', () => {
    expect(schema.facets?.version).toBe(FACETS_VERSION);
    expect(defs.Trade.codes.map((c) => c.code)).toEqual(['EARTH', 'CONC', 'STEEL', 'TIMBER', 'MASON', 'ROOF', 'FACADE', 'GLAZ', 'DRYLN', 'FINISH', 'DOORS', 'MECH', 'PLUMB', 'ELEC', 'FIRE', 'LIFT', 'SITE', 'OTHER']);
    expect(defs.Placement.codes.map((c) => c.code)).toEqual(['EXT', 'INT', 'BOUNDARY']);
    expect(defs.Material.codes.map((c) => c.code)).toEqual(['CONCRETE', 'STEEL', 'TIMBER', 'MASONRY', 'GYPSUM', 'GLASS', 'ALUMINIUM', 'INSULATION', 'PLASTIC', 'STONE', 'EARTH', 'OTHER']);
    expect(defs.Phase.codes.map((c) => c.code)).toEqual(['SUBSTR', 'FRAME', 'ENVELOPE', 'SERVICES', 'FITOUT', 'EXTERNAL']);
    expect(defs.Orientation.codes.map((c) => c.code)).toEqual(['HORIZONTAL', 'VERTICAL', 'INCLINED', 'ALONG_X', 'ALONG_Y', 'DIAGONAL']);
    expect(defs.ClassRepair.codes[0]!.code).toBe('KEEP');
    for (const id of FACET_IDS) expect(defs[id].enabled).toBe(true);
  });

  it('the shipped JSON file and the built-in defaults agree', async () => {
    const { readFileSync } = await import('node:fs');
    const { fileURLToPath } = await import('node:url');
    const file = JSON.parse(readFileSync(fileURLToPath(new URL('../public/classification/default-schema.json', import.meta.url)), 'utf8')) as { facets: unknown };
    expect(file.facets).toEqual(facetsSection(defaultFacetDefs(0.6)));
    const parsed = parseSchema(file);
    expect(parsed.errors).toEqual([]);
    expect(parsed.schema!.facets!.facets.Trade.codes.length).toBe(18);
  });

  it('an older schema file without facets still loads and gets the defaults', () => {
    const { facets: _f, ...old } = JSON.parse(JSON.stringify({ ...schema, facets: undefined })) as Record<string, unknown>;
    const p = parseSchema({ ...old, schema: 'xray-classification-schema/1' });
    expect(p.errors).toEqual([]);
    expect(p.schema!.facets).toBeUndefined();
    expect(facetDefs(p.schema!).Phase.codes.length).toBe(6);
    expect(facetDefs(p.schema!).Trade.enabled).toBe(true);
  });

  it('a schema file can switch a facet off, change a threshold and a code list; bad entries are reported', () => {
    const base = JSON.parse(JSON.stringify(schema)) as Record<string, unknown>;
    base['facets'] = { version: 'xr-facets/1', Trade: { enabled: false, minConfidence: 0.8, codes: [{ code: 'A', label: 'A work' }, { code: 'B', label: 'B work' }] } };
    const p = parseSchema(base);
    expect(p.errors).toEqual([]);
    const d = facetDefs(p.schema!);
    expect(d.Trade.enabled).toBe(false);
    expect(d.Trade.minConfidence).toBe(0.8);
    expect(d.Trade.codes.map((c) => c.code)).toEqual(['A', 'B']);
    expect(d.Phase.codes.length).toBe(6); // untouched
    const errs: string[] = [];
    parseFacets({ Trade: { codes: [{ code: 'A', label: 'x' }, { code: 'A', label: 'y' }] }, Phase: { minConfidence: 3 }, Material: { codes: [] } }, errs);
    expect(errs.length).toBe(3);
  });

  it('the facet code lists do not change the discipline hash; they have their own', () => {
    const other = JSON.parse(JSON.stringify(schema)) as typeof schema;
    other.facets!.facets.Trade.codes.pop();
    expect(schemaHash(other)).toBe(schemaHash(schema));
    expect(facetsHash(other)).not.toBe(facetsHash(schema));
  });
});

describe('the questions', () => {
  it('one choice question per facet with the facet\'s codes as options', () => {
    const q = facetQuestions(defs, 'Trade');
    expect(Object.keys(q)).toEqual([Q_FACET.Trade]);
    const t = q[Q_FACET.Trade]!;
    expect(t.type).toBe('choice');
    if (t.type === 'choice') {
      expect(Object.keys(t.criteria)).toEqual(defs.Trade.codes.map((c) => c.code));
      expect(t.criteria['CONC']).toContain('Concrete works');
    }
    for (const f of ['Material', 'Phase', 'ClassRepair'] as const) expect(Object.keys(facetQuestions(defs, f))).toEqual([Q_FACET[f]]);
  });
  it('Placement adds the load-bearing yes/no only when it is open, and may leave out the exposure', () => {
    expect(Object.keys(facetQuestions(defs, 'Placement'))).toEqual([Q_FACET.Placement]);
    expect(Object.keys(facetQuestions(defs, 'Placement', { loadBearing: true }))).toEqual([Q_FACET.Placement, Q_LOAD_BEARING]);
    expect(Object.keys(facetQuestions(defs, 'Placement', { exposure: false, loadBearing: true }))).toEqual([Q_LOAD_BEARING]);
  });
});

describe('classifyFacets', () => {
  it('rules decide what they can without a provider; open facets are left out (or a weak rule, flagged)', async () => {
    const slab = input('s1', 'IfcSlab', { material: 'Concrete C30/37', psets: { Pset_SlabCommon: { IsExternal: false } } });
    const run = await classifyFacets([slab], { schema });
    const s = run.results.get('s1')!;
    expect(s.Material).toMatchObject({ code: 'CONCRETE', source: 'rule' });
    expect(s.Trade).toMatchObject({ code: 'CONC', source: 'rule' });
    expect(s.Placement).toMatchObject({ code: 'INT', source: 'ifc' });
    expect(s.Placement!.fields).toMatchObject({ Exposure: 'INT', ExposureSource: 'ifc', LoadBearing: true, LoadBearingSource: 'rule' });
    expect(s.Phase).toMatchObject({ code: 'FRAME', source: 'rule' });
    expect(s.Orientation).toBeUndefined();
    expect(run.stats.calls).toBe(0);
  });

  it('Orientation is measured, with plausibility flagged for review', async () => {
    const flatWall = input('w1', 'IfcWall');
    const m = measureOrientation(box(0, 0, 0, 5, 0.2, 3))!; // 5 x 3 plane lying flat
    const run = await classifyFacets([flatWall], { schema, info: () => ({ measure: m }) });
    const o = run.results.get('w1')!.Orientation!;
    expect(o).toMatchObject({ code: 'HORIZONTAL', source: 'geometry', confidence: 1, needsReview: true });
    expect(o.fields).toMatchObject({ Tilt: 0, Plausible: false });
    expect(orientationResult(defs, flatWall, measureOrientation(box(0, 1.5, 0, 5, 3, 0.2))!).needsReview).toBe(false);
  });

  it('asks the model once per facet and signature, with the facet codes as options', async () => {
    const p = provider((q, options) => (q === Q_FACET.Trade ? 'CONC' : q === Q_FACET.Material ? 'CONCRETE' : q === Q_FACET.Phase ? 'FRAME' : options[0]!));
    const inputs = Array.from({ length: 6 }, (_, i) => input(`b${i}`, 'IfcBuildingElementProxy', { name: `Block ${i}`, type: { ifcClass: 'T', name: 'Generic block', psets: {} } }));
    const run = await classifyFacets(inputs, { schema, provider: p });
    const asked = p.calls.flatMap((c) => Object.keys(c.questions));
    expect(asked.filter((q) => q === Q_FACET.Trade).length).toBe(1);
    expect(asked.filter((q) => q === Q_FACET.Material).length).toBe(1);
    expect(run.stats.calls).toBe(p.calls.length);
    for (const r of run.results.values()) {
      expect(r.Material).toMatchObject({ code: 'CONCRETE', source: 'model', model: 'test-model' });
      expect(r.Trade).toMatchObject({ code: 'CONC', source: 'model' });
      expect(r.Trade!.confidence).toBeCloseTo(0.9, 2);
    }
    // the answer is cached: a second run asks nothing
    const cache = new MemoryFacetCache();
    const p2 = provider((q, o) => (q === Q_FACET.Material ? 'CONCRETE' : o[0]!));
    await classifyFacets(inputs, { schema, provider: p2, cache });
    const n = p2.calls.length;
    const again = await classifyFacets(inputs, { schema, provider: p2, cache });
    expect(p2.calls.length).toBe(n);
    expect(again.stats.bySource.Material['cache']).toBe(6);
  });

  it('a confident model answer needs no review; a low or close one does', async () => {
    const mk = async (conf: number): Promise<boolean> => {
      const run = await classifyFacets([input('x', 'IfcBuildingElementProxy', { name: 'Thing' })], { schema, provider: provider((q, o) => (q === Q_FACET.Material ? 'GLASS' : o[0]!), conf), enabled: { Trade: false, Phase: false, Placement: false, ClassRepair: false } });
      return run.results.get('x')!.Material!.needsReview;
    };
    expect(await mk(0.95)).toBe(false);
    expect(await mk(0.5)).toBe(true);
  });

  it('the temperature of the discipline question calibrates the facet answers', async () => {
    const mk = async (T: number): Promise<number> => {
      const run = await classifyFacets([input('x', 'IfcBuildingElementProxy', { name: 'Thing' })], { schema, provider: provider((q, o) => (q === Q_FACET.Material ? 'GLASS' : o[0]!), 0.9), temperatures: { discipline: T }, enabled: { Trade: false, Phase: false, Placement: false, ClassRepair: false } });
      return run.results.get('x')!.Material!.confidence;
    };
    expect(await mk(3)).toBeLessThan(await mk(1));
  });

  it('a model failure falls back to the weak rule and flags it; a switched-off facet is not asked and not returned', async () => {
    const failing: DecisionModel = { provider: 'mock', async decide() { throw new Error('boom'); } };
    const w = input('w', 'IfcSlab', { psets: { Pset_SlabCommon: { IsExternal: false } } });
    const run = await classifyFacets([w], { schema, provider: failing, retry: { retries: 0 } as never, enabled: { Material: false } });
    expect(run.stats.errors.join(' ')).toMatch(/boom/);
    expect(run.results.get('w')!.Material).toBeUndefined();
    expect(run.results.get('w')!.Placement).toMatchObject({ code: 'INT' });
  });

  it('a manual choice wins and is used by the rules of later facets', async () => {
    const e = input('m', 'IfcWall');
    const manual = new Map([['m', { Trade: makeManualFacet(defs, 'Trade', { code: 'MASON' }) }]]);
    const run = await classifyFacets([e], { schema, manual, info: () => ({ placementGeo: { exposure: 'BOUNDARY', confidence: 0.85, rationale: 'x' } }) });
    const r = run.results.get('m')!;
    expect(r.Trade).toMatchObject({ code: 'MASON', source: 'manual', confidence: 1, needsReview: false });
    expect(r.Phase).toMatchObject({ code: 'ENVELOPE' }); // a boundary masonry wall
  });

  it('ClassRepair is offered only for generic classes (or contradicted ones)', async () => {
    const col = measureOrientation(box(0, 1.5, 0, 0.3, 3, 0.3))!;
    const run = await classifyFacets([input('p', 'IfcBuildingElementProxy', { name: 'Col 1' }), input('d', 'IfcDoor', { name: 'Door 1' })], { schema, info: (i) => (i.id === 'p' ? { measure: col } : {}) });
    expect(run.results.get('p')!.ClassRepair).toMatchObject({ code: 'IfcColumn', source: 'rule' });
    expect(run.results.get('d')!.ClassRepair).toBeUndefined();
  });

  it('dry run counts the requests without sending any', async () => {
    const p = provider(() => 'CONCRETE');
    const run = await classifyFacets([input('a', 'IfcBuildingElementProxy', { name: 'A' })], { schema, provider: p, dry: true });
    expect(p.calls.length).toBe(0);
    expect(run.stats.calls).toBeGreaterThan(0);
  });
});

describe('writing: names and types', () => {
  it('the core fields and the facet fields, as XR_<Facet>.<Field>, typed', async () => {
    const run = await classifyFacets([input('s1', 'IfcSlab', { material: 'Concrete', psets: { Pset_SlabCommon: { IsExternal: false } } })], { schema, info: () => ({ measure: measureOrientation(box(0, 0, 0, 8, 0.25, 6)) }) });
    const props = facetSetProperties(run.results.get('s1')!);
    expect(props['XR_Trade.Code']).toBe('CONC');
    expect(props['XR_Trade.Label']).toBe('Concrete works');
    expect(props['XR_Trade.Confidence']).toBe(0.88);
    expect(props['XR_Trade.Source']).toBe('rule');
    expect(props['XR_Trade.NeedsReview']).toBe(false);
    expect(props['XR_Trade.SchemeVersion']).toBe('xr-facets/1');
    expect('XR_Trade.Model' in props).toBe(false); // empty values are not written
    expect(props['XR_Placement.Code']).toBe('INT');
    expect(props['XR_Placement.Exposure']).toBe('INT');
    expect(props['XR_Placement.LoadBearing']).toBe(true);
    expect(props['XR_Placement.ExposureSource']).toBe('ifc');
    expect(props['XR_Placement.LoadBearingSource']).toBe('rule');
    expect(props['XR_Orientation.Code']).toBe('HORIZONTAL');
    expect(props['XR_Orientation.Tilt']).toBe(0);
    expect(typeof props['XR_Orientation.Azimuth']).toBe('number');
    expect(props['XR_Orientation.Plausible']).toBe(true);
    expect(props['XR_Orientation.PrincipalAxis']).toBe('Z');
    expect(props['XR_Orientation.Source']).toBe('geometry');
    expect(props['XR_Material.Code']).toBe('CONCRETE');
    expect(props['XR_Phase.Code']).toBe('FRAME');
    // every written key belongs to the namespace of its facet
    for (const k of Object.keys(props)) expect(/^XR_(Trade|Placement|Material|Phase|Orientation|ClassRepair)\.[A-Za-z]+$/.test(k)).toBe(true);
    for (const f of FACET_IDS) for (const k of Object.keys(facetProperties(run.results.get('s1')![f] ?? ({ facet: f, code: '', label: '', confidence: 1, source: 'rule', needsReview: false, fields: {} })))) expect(facetPropertyNames(f)).toContain(k);
  });

  it('a model result writes Model; a ClassRepair suggestion writes its fields', () => {
    const r = makeManualFacet(defs, 'ClassRepair', { code: 'IfcColumn', predefinedType: 'COLUMN' }, undefined, 'IfcBuildingElementProxy');
    const p = facetProperties(r);
    expect(p['XR_ClassRepair.OriginalClass']).toBe('IfcBuildingElementProxy');
    expect(p['XR_ClassRepair.SuggestedClass']).toBe('IfcColumn');
    expect(p['XR_ClassRepair.SuggestedPredefinedType']).toBe('COLUMN');
    expect(p['XR_ClassRepair.Applied']).toBe(false);
    expect(p['XR_ClassRepair.Source']).toBe('manual');
    expect(p['XR_ClassRepair.Confidence']).toBe(1);
  });

  it('a manual override checks the code against the facet list', () => {
    expect(() => makeManualFacet(defs, 'Trade', { code: 'NOPE' })).toThrow(/not a Trade code/);
    const t = makeManualFacet(defs, 'Trade', { code: 'CONC', workPackage: 'WP-3' });
    expect(facetProperties(t)['XR_Trade.WorkPackage']).toBe('WP-3');
    const pl = makeManualFacet(defs, 'Placement', { code: 'BOUNDARY', loadBearing: true });
    expect(facetProperties(pl)).toMatchObject({ 'XR_Placement.Code': 'BOUNDARY', 'XR_Placement.LoadBearing': true, 'XR_Placement.LoadBearingSource': 'manual', 'XR_Placement.Source': 'manual' });
  });
});

describe('the query alias', () => {
  const model = (): SceneModel => {
    const els = [
      { cls: 'IfcSlab', props: { 'XR_Trade.Code': 'CONC', 'XR_Phase.Code': 'FRAME', 'XR_Orientation.Plausible': true, 'XR_Material.Code': 'CONCRETE' }, material: 'Beton' },
      { cls: 'IfcWall', props: { 'XR_Trade.Code': 'MASON', 'XR_Phase.Code': 'ENVELOPE', 'XR_Orientation.Plausible': false, 'XR_Material.Code': 'MASONRY' }, material: 'Brick' },
      { cls: 'IfcDoor', props: { 'XR_Trade.Code': 'DOORS', 'XR_Phase.Code': 'FITOUT', 'XR_Orientation.Plausible': true }, material: 'Wood' },
    ].map((s, id) => ({ id, globalId: `G${id}`, ifcClass: s.cls, storey: 0, material: s.material, color: [1, 1, 1, 1] as [number, number, number, number], bounds: [id, 0, 0, id + 1, 1, 1] as [number, number, number, number, number, number], props: s.props as Record<string, string | number | boolean> }));
    return { schema: 'xray-model/1', units: 'm', originShift: [0, 0, 0], storeys: [{ id: 0, name: 'EG', elevation: 0 }], elements: els, relations: { voids: [], fills: [], hosts: [], ports: [], systems: [] }, byGlobalId: new Map(els.map((e) => [e.globalId, e.id])) };
  };
  it('a bare facet name is XR_<Facet>.Code; the full name works; material stays the IFC material', () => {
    const t = freshTable(model());
    expect(filterRows("Trade = 'CONC'", t)).toEqual([0]);
    expect(filterRows("trade = 'MASON'", t)).toEqual([1]);
    expect(filterRows("XR_Trade.Code = 'CONC'", t)).toEqual([0]);
    expect(filterRows("Phase = 'ENVELOPE'", t)).toEqual([1]);
    expect(filterRows('XR_Orientation.Plausible = FALSE', t)).toEqual([1]);
    expect(filterRows("XR_Material.Code = 'MASONRY'", t)).toEqual([1]);
    expect(filterRows("Material = 'Brick'", t)).toEqual([1]); // the core material column
    const r = runQuery(model(), "Trade = 'CONC'");
    expect(r.ids).toEqual([0]);
    expect(r.unknown).toEqual([]);
  });
  it('NeedsReview, Confidence and Source stay the discipline\'s bare names although every facet set has them', () => {
    const m = model();
    m.elements[0]!.props = { ...m.elements[0]!.props, 'XR_Classification.NeedsReview': true, 'XR_Trade.NeedsReview': false, 'XR_Phase.NeedsReview': false };
    expect(runQuery(m, 'NeedsReview = TRUE').ids).toEqual([0]);
  });
  it('without the facet written the bare name is not a column', () => {
    const m = model();
    for (const e of m.elements) delete e.props;
    const r = runQuery(m, "Trade = 'CONC'");
    expect(r.ids).toEqual([]);
    expect(r.unknown).toEqual(['Trade']);
  });
});

describe('export columns', () => {
  it('CSV gains the facet columns and rows for elements that have only facets; JSON gains the facets', async () => {
    const run = await classifyFacets([input('s1', 'IfcSlab', { material: 'Concrete' })], { schema });
    const csv = exportCsv([], run.results);
    const header = csv.split('\r\n')[0]!.split(',');
    for (const c of facetCsvColumns()) expect(header).toContain(c);
    expect(header).toContain('XR_Trade.Code');
    expect(header).toContain('GlobalId');
    const row = csv.split('\r\n')[1]!.split(',');
    expect(row[0]).toBe('s1');
    expect(row[header.indexOf('XR_Trade.Code')]).toBe('CONC');
    expect(row[header.indexOf('XR_Material.Code')]).toBe('CONCRETE');
    const plain = exportCsv([]);
    expect(plain).not.toContain('XR_Trade');
    const json = JSON.parse(exportJson([], schema, null, 'm', run.results)) as { facetScheme: string; facets: Record<string, { Trade: { code: string } }> };
    expect(json.facetScheme).toBe('xr-facets/1');
    expect(json.facets['s1']!.Trade.code).toBe('CONC');
    expect('facets' in JSON.parse(exportJson([], schema, null, 'm'))).toBe(false);
  });
});
