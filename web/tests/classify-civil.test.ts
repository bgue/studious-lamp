// The civil rules: site paving, kerbs, fences, drains, earthworks and equipment foundations, and the cases they must not take.

import { describe, expect, it } from 'vitest';
import { buildInputs, classByRules, defaultSchema, resolveRule, isBuildingContext, RULE_FINAL } from '../src/classify';
import type { ClassifyInput } from '../src/classify';
import { sidecarModel } from './classify-helpers';

const schema = defaultSchema();
const storey = { ifcClass: 'IfcBuildingStorey', name: 'Grade +0.0', globalId: 'storey:0' };
const site = { ifcClass: 'IfcSite', name: 'Site', globalId: 'site' };

const input = (over: Partial<ClassifyInput> = {}): ClassifyInput => ({
  id: 'G1', ifcClass: 'IfcBuildingElementProxy', name: 'Unit 7', psets: { Attr: { ObjectType: 'Box:Generic' } }, ...over,
});
const attr = (o: Record<string, string>): ClassifyInput['psets'] => ({ Attr: o });
const inBuilding = { path: [storey] };
const inSite = { path: [site] };

/** The rule and the schema decision of an input. */
function decide(i: ClassifyInput) {
  const h = classByRules(i)!;
  return { h, d: resolveRule(h, schema, isBuildingContext(i)) };
}

describe('civil rules: site paving and slabs', () => {
  it('a paving slab (BASESLAB) is CIV paving with a MasterFormat division in a building', () => {
    const { h, d } = decide(input({ ifcClass: 'IfcSlab', name: 'Paving slab PAV-01-01', psets: attr({ PredefinedType: 'BASESLAB', ObjectType: 'Paving (concrete)' }), hierarchy: inBuilding }));
    expect(h.discipline).toBe('CIV');
    expect(d).toMatchObject({ discipline: 'CIV', subDiscipline: 'PAV', division: '32', section: '32 13 00' });
  });

  it('a road or apron base slab is CIV paving, even in a building storey', () => {
    expect(classByRules(input({ ifcClass: 'IfcSlab', name: 'Perimeter road south', psets: attr({ PredefinedType: 'BASESLAB' }), hierarchy: inBuilding }))!.discipline).toBe('CIV');
    expect(classByRules(input({ ifcClass: 'IfcSlab', name: 'Apron slab', psets: attr({ PredefinedType: 'BASESLAB' }), hierarchy: inBuilding }))!.discipline).toBe('CIV');
  });

  it('a base slab outside a building is site paving', () => {
    const h = classByRules(input({ ifcClass: 'IfcSlab', name: 'Yard slab', psets: attr({ PredefinedType: 'BASESLAB' }), hierarchy: { path: [], buildingContext: false } }))!;
    expect(h).toMatchObject({ discipline: 'CIV', subDiscipline: 'PAV' });
  });

  it('a building ground slab (BASESLAB in a building) stays STR', () => {
    const h = classByRules(input({ ifcClass: 'IfcSlab', name: 'Ground floor slab', psets: attr({ PredefinedType: 'BASESLAB' }), hierarchy: inBuilding }))!;
    expect(h).toMatchObject({ discipline: 'STR', subDiscipline: 'SLB' });
  });

  it('a slab named hardstanding is CIV paving, and a floor slab stays STR', () => {
    expect(classByRules(input({ ifcClass: 'IfcSlab', name: 'Hardstanding HS-2', psets: attr({ PredefinedType: 'FLOOR' }), hierarchy: inBuilding }))!.discipline).toBe('CIV');
    expect(classByRules(input({ ifcClass: 'IfcSlab', name: 'Control building floor', psets: attr({ PredefinedType: 'FLOOR' }), hierarchy: inBuilding }))!.discipline).toBe('STR');
  });
});

describe('civil rules: kerbs, fences, drains, earthworks, walls', () => {
  it('a kerb is CIV paving with the MasterFormat section 32 16 13 (a proxy has no class for it)', () => {
    const { d } = decide(input({ name: 'Kerb KB1S1', psets: attr({ ObjectType: 'Kerb (concrete, 3 m)' }), hierarchy: inBuilding }));
    expect(d).toMatchObject({ discipline: 'CIV', subDiscipline: 'PAV', division: '32', section: '32 16 13' });
  });

  it('a fence post is CIV landscape and site improvements, with division 32', () => {
    const { d } = decide(input({ name: 'Fence post FP1', psets: attr({ ObjectType: 'Fence post 2.4 m' }), hierarchy: inBuilding }));
    expect(d).toMatchObject({ discipline: 'CIV', subDiscipline: 'LND', division: '32', section: '32 31 00' });
  });

  it('a site gate is a fence item, but a gate valve stays a valve', () => {
    expect(classByRules(input({ name: 'Vehicle gate VG-1' }))).toMatchObject({ discipline: 'CIV', subDiscipline: 'LND' });
    expect(classByRules(input({ ifcClass: 'IfcValve', name: 'Gate valve DN150', systems: ['Process crude'] }))!.discipline).toBe('PIP');
  });

  it('a drain trench is CIV site drainage, with division 33', () => {
    const { d } = decide(input({ name: 'Drain trench DT1', psets: attr({ ObjectType: 'Drain trench (concrete channel)' }), hierarchy: inBuilding }));
    expect(d).toMatchObject({ discipline: 'CIV', subDiscipline: 'DRN', division: '33', section: '33 44 00' });
  });

  it('a culvert and a manhole are site drainage', () => {
    expect(classByRules(input({ name: 'Culvert C-3' }))).toMatchObject({ discipline: 'CIV', subDiscipline: 'DRN' });
    expect(classByRules(input({ name: 'Manhole MH-4' }))).toMatchObject({ discipline: 'CIV', subDiscipline: 'DRN', section: '33 39 00' });
  });

  it('an earthwork or a bund is CIV earthwork (division 31), a retaining wall is CIV earthwork too', () => {
    expect(classByRules(input({ ifcClass: 'IfcEarthworksCut', name: 'Cut' }))).toMatchObject({ discipline: 'CIV', subDiscipline: 'ERT', division: '31' });
    expect(classByRules(input({ name: 'Bund wall BW-1', psets: attr({ ObjectType: 'Bund' }) }))).toMatchObject({ discipline: 'CIV', subDiscipline: 'ERT', section: '31 23 00' });
    const rw = classByRules(input({ ifcClass: 'IfcWall', name: 'Retaining wall RW-2', psets: { Pset_WallCommon: { LoadBearing: true } } }))!;
    expect(rw).toMatchObject({ discipline: 'CIV', subDiscipline: 'ERT', section: '32 32 00' });
  });

  it('a generic IFC civil element and an alignment are CIV', () => {
    expect(classByRules(input({ ifcClass: 'IfcCivilElement', name: 'Site item' }))!.discipline).toBe('CIV');
    expect(classByRules(input({ ifcClass: 'IfcAlignment', name: 'Road centre line' }))).toMatchObject({ discipline: 'CIV', subDiscipline: 'PAV' });
  });

  it('a road or pavement keeps division 32 when it is in a building, and loses it outside (appliesTo building)', () => {
    const h = classByRules(input({ ifcClass: 'IfcPavement', name: 'Car park' }))!;
    expect(resolveRule(h, schema, true)!.division).toBe('32');
    expect(resolveRule(h, schema, false)!.division).toBeNull();
  });
});

describe('civil rules: footings', () => {
  it('a building footing stays STR', () => {
    expect(classByRules(input({ ifcClass: 'IfcFooting', name: 'Footing RCA1', psets: attr({ ObjectType: 'Pad footing 0.8 x 0.8 m' }), hierarchy: inBuilding })))
      .toMatchObject({ discipline: 'STR', subDiscipline: 'FND' });
  });

  it('a footing named or typed as an equipment foundation is CIV foundations', () => {
    expect(classByRules(input({ ifcClass: 'IfcFooting', name: 'Equipment foundation P-101A', hierarchy: inBuilding })))
      .toMatchObject({ discipline: 'CIV', subDiscipline: 'FND', division: '03' });
    expect(classByRules(input({ ifcClass: 'IfcFooting', name: 'Footing P-101B', psets: attr({ ObjectType: 'Pump base 1.6 x 1.2 m' }), hierarchy: inBuilding }))!.discipline).toBe('CIV');
    expect(classByRules(input({ ifcClass: 'IfcFooting', name: 'Skid foundation S-1', hierarchy: inBuilding }))!.discipline).toBe('CIV');
  });

  it('a footing contained in the site, and not in a storey, is CIV foundations', () => {
    expect(classByRules(input({ ifcClass: 'IfcFooting', name: 'Footing F-9', hierarchy: inSite }))).toMatchObject({ discipline: 'CIV', subDiscipline: 'FND' });
  });

  it('the decision is the schema code, so the CIV foundations sub-discipline exists in the default schema', () => {
    const { d } = decide(input({ ifcClass: 'IfcFooting', name: 'Equipment foundation E-1', hierarchy: inBuilding }));
    expect(d!.subDiscipline).toBe('FND');
    expect(schema.disciplines.find((x) => x.code === 'CIV')!.subDisciplines.map((s) => s.code)).toContain('FND');
  });
});

describe('civil rules: what they must not take', () => {
  it('a pipe named drain stays PIP or PLB', () => {
    expect(classByRules(input({ ifcClass: 'IfcPipeSegment', name: 'Drain pipe DN100', systems: ['Process unit'] }))!.discipline).toBe('PIP');
    const weak = classByRules(input({ ifcClass: 'IfcPipeSegment', name: 'Drain pipe DN100' }))!;
    expect(weak.discipline).toBe('PLB');
    expect(weak.discipline).not.toBe('CIV');
    expect(classByRules(input({ ifcClass: 'IfcPipeSegment', name: 'Trench drain line', systems: ['Sewer'], hierarchy: inBuilding }))!.discipline).toBe('PLB');
  });

  it('a wall with no civil name keeps its structural or architectural rule', () => {
    expect(classByRules(input({ ifcClass: 'IfcWall', name: 'Control building wall N', psets: { Pset_WallCommon: { LoadBearing: true } } }))!.discipline).toBe('STR');
    expect(classByRules(input({ ifcClass: 'IfcWall', name: 'Control building wall N', psets: { Pset_WallCommon: { LoadBearing: false } } }))!.discipline).toBe('ARC');
  });

  it('a pipe support or a cable tray bracket is not civil', () => {
    expect(classByRules(input({ ifcClass: 'IfcMember', name: 'Pipe support post PS1A', hierarchy: inBuilding }))!.discipline).toBe('STR');
    expect(classByRules(input({ ifcClass: 'IfcMember', name: 'Cable tray bracket TB1A', hierarchy: inBuilding }))!.discipline).toBe('STR');
  });
});

describe('civil rules on the process-plant sample', () => {
  // The counts are what the rules say about the generated unit (tools/make_process_plant_ifc.py), not what is right: the
  // ground truth is models/Process-Plant.truth.json. Known gaps: pumps, drums and exchangers come out as MEC/PLB equipment,
  // steam, cooling water and condensate lines as MEC/HYD or PLB/SUP, pipe and tray supports as STR/BRC, and the 13 equipment
  // parts and markers modelled as IfcBuildingElementProxy (pump baseplates, exchanger channels and saddles, vessel skirts,
  // the battery-limit board) match no rule.
  it('moves paving, roads, kerbs, fences and drain trenches to CIV; only 13 equipment-part proxies stay unresolved', () => {
    const counts: Record<string, number> = {};
    let unresolved = 0;
    for (const i of buildInputs(sidecarModel('process-plant'))) {
      const h = classByRules(i);
      const d = h ? resolveRule(h, schema, isBuildingContext(i)) : null;
      if (!h || !d) { unresolved++; continue; }
      counts[d.discipline] = (counts[d.discipline] ?? 0) + 1;
      expect(h.confidence).toBeGreaterThanOrEqual(0);
      if (h.confidence < RULE_FINAL && h.discipline === 'CIV') throw new Error(`weak civil rule on ${i.name}`);
    }
    expect(counts).toEqual({ CIV: 230, STR: 336, ARC: 26, ELE: 115, MEC: 206, PLB: 59, INS: 24, PIP: 285 });
    expect(unresolved).toBe(13);
  });
});
