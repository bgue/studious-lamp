// The concrete rules: family, roles (predefined types, class, names, geometry), method, reinforcement, scheme, strength and exposure
// parsing, the cover table, marks, contacts and pour groups.

import { describe, expect, it } from 'vitest';
import { allowedRoles, frameKindOfClass, frameKindOfRole, isConcreteFamily, methodRule, nameRole, ratioEstimate, reinforcementRule, roleRule, schemeRule } from '../src/classify/concrete/rules';
import type { RoleContext } from '../src/classify/concrete/rules';
import { coverFromTable, coverMm, defaultCoverTable, normaliseFire, parseCoverTable, parseExposure, parseStrength, specOf, suggestExposure } from '../src/classify/concrete/spec';
import { assignMarks } from '../src/classify/concrete/marks';
import { contactGraph, pourClassOf, pourGroups } from '../src/classify/concrete/contacts';
import { ROLE_CODES } from '../src/classify/concrete/defs';
import type { ClassifyInput } from '../src/classify/types';

const input = (cls: string, name: string, o: Partial<ClassifyInput> = {}): ClassifyInput => ({ id: name, ifcClass: cls, name, psets: {}, ...o });
const ctx = (o: Partial<RoleContext> = {}): RoleContext => ({ restsOn: [], carries: [], ...o });

describe('family', () => {
  it('concrete material, concrete psets, footings and piles are in; masonry, steel, timber are out', () => {
    expect(isConcreteFamily(input('IfcSlab', 's', { material: 'Reinforced concrete C25/30' }))).toBe(true);
    expect(isConcreteFamily(input('IfcWall', 'w', { material: 'Brick' }))).toBe(false);
    expect(isConcreteFamily(input('IfcColumn', 'c', { material: 'Steel S355' }))).toBe(false);
    expect(isConcreteFamily(input('IfcBeam', 'b', { material: 'Glulam' }))).toBe(false);
    expect(isConcreteFamily(input('IfcFooting', 'f'))).toBe(true);
    expect(isConcreteFamily(input('IfcPile', 'p', { material: 'Steel' }))).toBe(false);
    expect(isConcreteFamily(input('IfcPile', 'p'))).toBe(true);
    expect(isConcreteFamily(input('IfcSlab', 's'))).toBe(false); // no material, no pset
    expect(isConcreteFamily(input('IfcSlab', 's', { psets: { Pset_ConcreteElementGeneral: { StrengthClass: 'C30/37' } } }))).toBe(true);
    expect(isConcreteFamily(input('IfcWall', 'w', { psets: { Pset_PrecastConcreteElementGeneral: { PieceMark: 'W1' } } }))).toBe(true);
    expect(isConcreteFamily(input('IfcDoor', 'd', { material: 'Concrete' }))).toBe(false);
    expect(isConcreteFamily(input('IfcWall', 'w', { material: 'Brick' }), 'CONCRETE')).toBe(true); // the Material facet decides when given
  });
  it('frames by class and by role', () => {
    expect(frameKindOfClass('IfcSlab')).toBe('slab');
    expect(frameKindOfClass('IfcWallStandardCase')).toBe('wall');
    expect(frameKindOfRole('PILE')).toBe('column');
    expect(frameKindOfRole('GRADE_BEAM')).toBe('beam');
    expect(frameKindOfRole('RAFT')).toBe('footing');
  });
  it('the roles allowed for a class never cross the class', () => {
    expect(allowedRoles('IfcSlab')).not.toContain('COLUMN');
    expect(allowedRoles('IfcColumn')).not.toContain('SUSPENDED_SLAB');
    expect(allowedRoles('IfcWall')).toContain('CORE_WALL');
    expect(allowedRoles('IfcBuildingElementProxy').length).toBe(ROLE_CODES.length);
    expect(allowedRoles('IfcPile')).toContain('PILE');
  });
});

describe('role rules', () => {
  const role = (i: ClassifyInput, c: RoleContext = ctx()): [string, number] | null => { const r = roleRule(i, c); return r ? [r.code, r.confidence] : null; };
  it('predefined types', () => {
    expect(role(input('IfcFooting', 'F', { psets: { Attr: { PredefinedType: 'PILE_CAP' } } }))![0]).toBe('PILE_CAP');
    expect(role(input('IfcFooting', 'F', { psets: { Attr: { PredefinedType: 'STRIP_FOOTING' } } }))![0]).toBe('STRIP_FOOTING');
    expect(role(input('IfcFooting', 'F', { psets: { Attr: { PredefinedType: 'FOOTING_BEAM' } } }))![0]).toBe('GRADE_BEAM');
    expect(role(input('IfcWall', 'W', { psets: { Attr: { PredefinedType: 'SHEAR' } } }))![0]).toBe('SHEAR_WALL');
    expect(role(input('IfcWall', 'W', { psets: { Attr: { PredefinedType: 'RETAININGWALL' } } }))![0]).toBe('RETAINING_WALL');
    expect(role(input('IfcSlab', 'S', { psets: { Attr: { PredefinedType: 'LANDING' } } }))![0]).toBe('LANDING');
    expect(role(input('IfcSlab', 'S', { psets: { Attr: { PredefinedType: 'ROOF' } } }))![0]).toBe('SUSPENDED_SLAB');
    expect(role(input('IfcPile', 'P'))![0]).toBe('PILE');
    expect(role(input('IfcStairFlight', 'T'))![0]).toBe('STAIR');
  });
  it('FLOOR slabs: on the ground or suspended, from the geometry and the contacts', () => {
    const floor = input('IfcSlab', 'Floor', { psets: { Attr: { PredefinedType: 'FLOOR' } } });
    expect(role(floor, ctx({ onGround: true, thickness: 0.2 }))).toEqual(['SLAB_ON_GRADE', 0.86]);
    expect(role(floor, ctx({ restsOn: ['IfcWall', 'IfcColumn'], thickness: 0.2 }))).toEqual(['SUSPENDED_SLAB', 0.86]);
    expect(role(floor, ctx({ carries: ['IfcColumn'], restsOn: [], thickness: 0.7 }))![0]).toBe('TRANSFER_SLAB');
    expect(role(floor, ctx({ onGround: true, thickness: 0.8 }))![0]).toBe('RAFT');
    expect(role(input('IfcSlab', 'S', { psets: { Attr: { PredefinedType: 'BASESLAB' } } }), ctx({ onGround: true, thickness: 0.25 }))).toEqual(['SLAB_ON_GRADE', 0.88]);
  });
  it('names, in English and German', () => {
    expect(nameRole(input('IfcFooting', 'Pile cap PC4'))!.code).toBe('PILE_CAP');
    expect(nameRole(input('IfcFooting', 'PC4'))!.code).toBe('PILE_CAP');
    expect(nameRole(input('IfcSlab', 'PC panel'))).toBeNull(); // PC is a pile cap only on a footing
    expect(nameRole(input('IfcSlab', 'Transfer slab L2'))!.code).toBe('TRANSFER_SLAB');
    expect(nameRole(input('IfcSlab', 'Bodenplatte 25'))!.code).toBe('SLAB_ON_GRADE');
    expect(nameRole(input('IfcSlab', 'Flachdecke D=25'))!.code).toBe('FLAT_SLAB');
    expect(nameRole(input('IfcWall', 'Lift core wall'))!.code).toBe('CORE_WALL');
    expect(nameRole(input('IfcWall', 'Kellerwand'))!.code).toBe('BASEMENT_WALL');
    expect(nameRole(input('IfcWall', 'Attika'))!.code).toBe('PARAPET');
    expect(nameRole(input('IfcBeam', 'Unterzug 30/60'))!.code).toBe('DOWNSTAND_BEAM');
    expect(nameRole(input('IfcBeam', 'Transfer beam'))!.code).toBe('TRANSFER_BEAM');
    expect(nameRole(input('IfcColumn', 'Pier P1'))!.code).toBe('PIER');
    expect(nameRole(input('IfcSlab', 'Core slab'))).toBeNull(); // CORE_WALL is not allowed for a slab
    expect(nameRole(input('IfcSlab', 'Typical', { type: { name: 'Waffle slab 600' } as ClassifyInput['type'] }))!.code).toBe('WAFFLE_SLAB');
  });
  it('geometry: footings, walls, beams, columns, proxies', () => {
    const f = input('IfcFooting', 'F');
    expect(role(f, ctx({ planArea: 100, planAspect: 1.2 }))![0]).toBe('RAFT');
    expect(role(f, ctx({ planArea: 6, planAspect: 8 }))![0]).toBe('STRIP_FOOTING');
    expect(role(f, ctx({ planArea: 4, planAspect: 1 }))![0]).toBe('PAD_FOOTING');
    expect(role(input('IfcWall', 'W'), ctx({ belowGround: true, thickness: 0.3, width: 3 }))![0]).toBe('BASEMENT_WALL');
    expect(role(input('IfcWall', 'W'), ctx({ thickness: 0.2, width: 3 }))).toEqual(['WALL', 0.86]);
    expect(role(input('IfcWall', 'W'), ctx({ thickness: 0.2, width: 0.2 }))![0]).toBe('CURB');
    expect(role(input('IfcColumn', 'C'), ctx({ length: 3 }))![0]).toBe('COLUMN');
    expect(role(input('IfcColumn', 'C'), ctx({ length: 0.4 }))![0]).toBe('PLINTH');
    expect(role(input('IfcBeam', 'B'), ctx({ carries: ['IfcColumn'] }))![0]).toBe('TRANSFER_BEAM');
    expect(role(input('IfcBeam', 'B'), ctx({ carries: ['IfcSlab'], restsOn: ['IfcColumn'] }))).toEqual(['BEAM', 0.86]);
    expect(role(input('IfcBeam', 'B'), ctx({ restsOn: ['IfcSlab'] }))![0]).toBe('UPSTAND_BEAM');
    expect(role(input('IfcBeam', 'B'), ctx({ onGround: true, restsOn: ['IfcFooting', 'IfcFooting'] }))![0]).toBe('GRADE_BEAM');
    expect(role(input('IfcBuildingElementProxy', 'X'), ctx({ orientation: 'VERTICAL', thickness: 0.2, length: 3 }))![0]).toBe('WALL');
    expect(role(input('IfcBuildingElementProxy', 'X'), ctx())).toBeNull();
  });
});

describe('method rules', () => {
  it('precast pset, IFC construction method, names, tendons, default', () => {
    expect(methodRule(input('IfcSlab', 'S', { psets: { Pset_PrecastConcreteElementFabrication: { PieceMark: 'P1' } } }), { role: 'SUSPENDED_SLAB' })).toMatchObject({ code: 'PRECAST', confidence: 0.95 });
    expect(methodRule(input('IfcSlab', 'S', { psets: { Pset_ConcreteElementGeneral: { ConstructionMethod: 'In-Situ' } } }), { role: 'SUSPENDED_SLAB' })).toMatchObject({ code: 'CAST_IN_PLACE', confidence: 0.95 });
    expect(methodRule(input('IfcSlab', 'S', { psets: { Pset_ConcreteElementGeneral: { ConstructionMethod: 'Precast' } } }), { role: 'SUSPENDED_SLAB' }).code).toBe('PRECAST');
    expect(methodRule(input('IfcSlab', 'PT slab L3'), { role: 'SUSPENDED_SLAB' }).code).toBe('POST_TENSIONED');
    expect(methodRule(input('IfcSlab', 'Hollowcore 200'), { role: 'SUSPENDED_SLAB' }).code).toBe('PRECAST');
    expect(methodRule(input('IfcWall', 'Tilt-up panel'), { role: 'WALL' }).code).toBe('TILT_UP');
    expect(methodRule(input('IfcSlab', 'Composite deck slab'), { role: 'SUSPENDED_SLAB' }).code).toBe('COMPOSITE_DECK');
    expect(methodRule(input('IfcFooting', 'PC1'), { role: 'PILE_CAP' }).code).toBe('CAST_IN_PLACE'); // PC is a pile cap here
    expect(methodRule(input('IfcSlab', 'S'), { role: 'SUSPENDED_SLAB', tendonNearby: true })).toMatchObject({ code: 'POST_TENSIONED', confidence: 0.7 });
    expect(methodRule(input('IfcSlab', 'S'), { role: 'SUSPENDED_SLAB' })).toMatchObject({ code: 'CAST_IN_PLACE', confidence: 0.55 });
    expect(methodRule(input('IfcSlab', 'S'), { role: 'SLAB_ON_GRADE' }).confidence).toBeGreaterThanOrEqual(0.85);
    expect(methodRule(input('IfcWall', 'W'), { role: 'PRECAST_PANEL' }).code).toBe('PRECAST');
  });
});

describe('reinforcement rules', () => {
  it('type and scheme', () => {
    expect(reinforcementRule(input('IfcSlab', 'S'), { role: 'SUSPENDED_SLAB', method: 'POST_TENSIONED' }).code).toBe('POST_TENSIONED');
    expect(reinforcementRule(input('IfcSlab', 'Blinding'), { role: 'SLAB_ON_GRADE', method: 'CAST_IN_PLACE' }).code).toBe('PLAIN');
    expect(reinforcementRule(input('IfcSlab', 'Steel fibre slab'), { role: 'SLAB_ON_GRADE', method: 'CAST_IN_PLACE' }).code).toBe('FIBRE');
    expect(reinforcementRule(input('IfcSlab', 'S', { psets: { Pset_ConcreteElementGeneral: { ReinforcementVolumeRatio: 110 } } }), { role: 'SUSPENDED_SLAB', method: 'CAST_IN_PLACE' }).confidence).toBe(0.95);
    expect(reinforcementRule(input('IfcSlab', 'S'), { role: 'SUSPENDED_SLAB', method: 'CAST_IN_PLACE' })).toMatchObject({ code: 'REINFORCED', confidence: 0.86 });
    expect(reinforcementRule(input('IfcWall', 'Curb'), { role: 'CURB', method: 'CAST_IN_PLACE' }).confidence).toBeLessThan(0.85);
  });
  it('slab schemes from names, roles, supports and the span ratio', () => {
    const s = (role: string, o: Partial<Parameters<typeof schemeRule>[0]> = {}): ReturnType<typeof schemeRule> => schemeRule({ role, ifcClass: 'IfcSlab', name: 'S', ...o });
    expect(s('SUSPENDED_SLAB', { spanRatio: 2.4 })).toMatchObject({ code: 'ONE_WAY', confidence: 0.88 });
    expect(s('SUSPENDED_SLAB', { spanRatio: 1.1 })).toMatchObject({ code: 'TWO_WAY', confidence: 0.86 });
    expect(s('SUSPENDED_SLAB', { spanRatio: 1.6 })!.confidence).toBeLessThan(0.85);
    expect(s('SUSPENDED_SLAB', { spanRatio: 1.1, supportsTwoSided: true })!.code).toBe('ONE_WAY');
    expect(s('SUSPENDED_SLAB', { name: 'Hollow core', spanRatio: 1 })!.code).toBe('ONE_WAY');
    expect(s('FLAT_SLAB')!.code).toBe('TWO_WAY');
    expect(s('RIBBED_SLAB')!.code).toBe('ONE_WAY');
    expect(s('SUSPENDED_SLAB')).toBeNull();
  });
  it('walls by thickness, linear members LINKS, footings', () => {
    expect(schemeRule({ role: 'WALL', ifcClass: 'IfcWall', name: 'w', thickness: 0.25 })!.code).toBe('DOUBLE_LAYER');
    expect(schemeRule({ role: 'WALL', ifcClass: 'IfcWall', name: 'w', thickness: 0.1 })!.code).toBe('SINGLE_LAYER');
    expect(schemeRule({ role: 'COLUMN', ifcClass: 'IfcColumn', name: 'c' })!.code).toBe('LINKS');
    expect(schemeRule({ role: 'BEAM', ifcClass: 'IfcBeam', name: 'b' })!.code).toBe('LINKS');
    expect(schemeRule({ role: 'PAD_FOOTING', ifcClass: 'IfcFooting', name: 'f' })!.code).toBe('TWO_WAY');
    expect(schemeRule({ role: 'STAIR', ifcClass: 'IfcStair', name: 's' })).toBeNull();
  });
  it('ratio estimate by role', () => {
    expect(ratioEstimate('PAD_FOOTING', 'REINFORCED')).toBeGreaterThanOrEqual(80);
    expect(ratioEstimate('PAD_FOOTING', 'REINFORCED')).toBeLessThanOrEqual(100);
    expect(ratioEstimate('SUSPENDED_SLAB', 'REINFORCED')).toBeGreaterThanOrEqual(90);
    expect(ratioEstimate('SUSPENDED_SLAB', 'REINFORCED')).toBeLessThanOrEqual(120);
    expect(ratioEstimate('BEAM', 'REINFORCED')).toBeGreaterThanOrEqual(150);
    expect(ratioEstimate('COLUMN', 'REINFORCED')).toBeGreaterThanOrEqual(180);
    expect(ratioEstimate('WALL', 'REINFORCED')).toBeLessThanOrEqual(100);
    expect(ratioEstimate('TRANSFER_BEAM', 'REINFORCED')).toBeGreaterThanOrEqual(250);
    expect(ratioEstimate('WALL', 'PLAIN')).toBe(0);
  });
});

describe('strength classes', () => {
  it('EN 206, DIN B, ACI and SI forms', () => {
    expect(parseStrength('C30/37')).toMatchObject({ text: 'C30/37', unit: '', standard: 'EN206' });
    expect(parseStrength('Beton c25/30 XC2')!.text).toBe('C25/30');
    expect(parseStrength('LC25/28')!.text).toBe('LC25/28');
    expect(parseStrength('Concrete C30')!.text).toBe('C30');
    expect(parseStrength('B35')!.text).toBe('C25/30');
    expect(parseStrength('B25 Stahlbeton')!.text).toBe('C20/25');
    expect(parseStrength('4000 psi')).toMatchObject({ text: '4000 psi', unit: 'psi', standard: 'ACI318' });
    expect(parseStrength('4,000 PSI')!.text).toBe('4000 psi');
    expect(parseStrength("f'c=5 ksi")).toMatchObject({ text: '5 ksi', unit: 'ksi', standard: 'ACI318' });
    expect(parseStrength('f’c = 4000')!.text).toBe('4000 psi');
    expect(parseStrength('32MPa')).toMatchObject({ text: '32 MPa', unit: 'MPa', standard: 'EN206' });
    expect(parseStrength('32 MPa', 'ACI318')!.standard).toBe('ACI318');
    expect(parseStrength("f'c 32 MPa")!.standard).toBe('ACI318');
    expect(parseStrength('Generic concrete')).toBeNull();
    expect(parseStrength('C2')).toBeNull();
  });
});

describe('exposure classes', () => {
  it('EN classes normalised, ACI only from a property, suggestions', () => {
    expect(parseExposure('xc4/xf1')!.classes).toBe('XC4, XF1');
    expect(parseExposure('XD2, XC4')!.classes).toBe('XC4, XD2');
    expect(parseExposure('XS3 XF4 XA1')!.classes).toBe('XS3, XF4, XA1');
    expect(parseExposure('X0')!.classes).toBe('X0');
    expect(parseExposure('F2, S1')).toBeNull(); // not from a name
    expect(parseExposure('F2, S1', true)).toMatchObject({ classes: 'F2, S1', standard: 'ACI318' });
    expect(parseExposure('C1 W0', true)!.classes).toBe('C1, W0');
    expect(parseExposure('none')).toBeNull();
    expect(suggestExposure('EXT', false)!.classes).toBe('XC4, XF1');
    expect(suggestExposure('BOUNDARY', false)!.classes).toBe('XC4, XF1');
    expect(suggestExposure('INT', false)!.classes).toBe('XC1');
    expect(suggestExposure('INT', true)!.classes).toBe('XC2');
    expect(suggestExposure(undefined, undefined)).toBeNull();
  });
  it('a suggestion is never final: NeedsReview and ExposureSource suggested; an IFC value is not', () => {
    const slab = input('IfcSlab', 's', { material: 'Concrete C30/37' });
    const a = specOf(slab, { role: 'SUSPENDED_SLAB', placement: 'EXT' });
    expect(a.needsReview).toBe(true);
    expect(a.fields['ExposureSource']).toBe('suggested');
    const b = specOf(input('IfcSlab', 's', { psets: { Pset_ConcreteElementGeneral: { StrengthClass: 'C30/37', ExposureClass: 'XC1', ConcreteCover: 25, ConcreteCoverAtMainBars: 25, ConcreteCoverAtLinks: 25 } } }), { role: 'SUSPENDED_SLAB', placement: 'EXT' });
    expect(b.needsReview).toBe(false);
    expect(b.fields['ExposureClass']).toBe('XC1');
    expect(b.fields['CoverSource']).toBe('ifc');
    expect(b.fields['Derived']).toBeUndefined();
  });
  it('IFC2x3 names: EnvironmentalClass and FireRating', () => {
    const s = specOf(input('IfcWall', 'w', { material: 'Concrete', psets: { Pset_ConcreteElementGeneral: { EnvironmentalClass: 'XC3', ConcreteCoverAtMainBars: 0.035, ConcreteCoverAtLinks: 0.025 }, Pset_WallCommon: { FireRating: 'REI 120' } } }), { role: 'WALL' });
    expect(s.fields['ExposureClass']).toBe('XC3');
    expect(s.fields['CoverMainBars']).toBe(35);
    expect(s.fields['CoverLinks']).toBe(25);
    expect(s.fields['CoverNominal']).toBe(25);
    expect(s.fields['FireResistance']).toBe('REI120');
    expect(s.code).toBe('UNKNOWN');
    expect(s.needsReview).toBe(true);
  });
  it('fire rating and cover units', () => {
    expect(normaliseFire(60)).toBe('R60');
    expect(normaliseFire('90 min')).toBe('R90');
    expect(normaliseFire('r 60')).toBe('R60');
    expect(normaliseFire('')).toBeUndefined();
    expect(coverMm(0.04)).toBe(40);
    expect(coverMm(40)).toBe(40);
    expect(coverMm('35')).toBe(35);
    expect(coverMm(0)).toBeUndefined();
  });
});

describe('cover table', () => {
  const t = defaultCoverTable();
  it('EN: by exposure, by role minimum and main bar extra', () => {
    expect(coverFromTable(t, { role: 'SUSPENDED_SLAB', standard: 'EN206', exposure: 'XC1' })).toEqual({ nominal: 25, mainBars: 25, links: 25 });
    expect(coverFromTable(t, { role: 'BEAM', standard: 'EN206', exposure: 'XC4, XF1' })).toEqual({ nominal: 40, mainBars: 50, links: 40 });
    expect(coverFromTable(t, { role: 'PAD_FOOTING', standard: 'EN206', exposure: 'XC2' }).nominal).toBe(50);
    expect(coverFromTable(t, { role: 'WALL', standard: 'EN206', exposure: 'XD3, XC4' }).nominal).toBe(55);
    expect(coverFromTable(t, { role: 'WALL', standard: 'EN206' }).nominal).toBe(25);
  });
  it('ACI: ground, weather, interior', () => {
    expect(coverFromTable(t, { role: 'PAD_FOOTING', standard: 'ACI318', ground: true }).nominal).toBe(75);
    expect(coverFromTable(t, { role: 'WALL', standard: 'ACI318', placement: 'EXT' }).nominal).toBe(50);
    expect(coverFromTable(t, { role: 'SUSPENDED_SLAB', standard: 'ACI318', placement: 'INT' }).nominal).toBe(20);
    expect(coverFromTable(t, { role: 'COLUMN', standard: 'ACI318', placement: 'INT' }).nominal).toBe(40);
  });
  it('a project table overrides; a bad entry is reported and ignored', () => {
    const errors: string[] = [];
    const p = parseCoverTable({ en: { exposure: { XC1: 30, XC2: 'x' } }, aci: { ground: 80 } }, errors);
    expect(p.en.exposure['XC1']).toBe(30);
    expect(p.en.exposure['XC2']).toBe(35);
    expect(p.aci.ground).toBe(80);
    expect(errors.length).toBe(1);
    const e2: string[] = [];
    parseCoverTable('nope', e2);
    expect(e2.length).toBe(1);
  });
  it('the table is used and flagged when the IFC has no cover; the project table changes the value', () => {
    const slab = input('IfcSlab', 's', { material: 'Concrete C30/37', psets: { Pset_ConcreteElementGeneral: { ExposureClass: 'XC1' } } });
    expect(specOf(slab, { role: 'SUSPENDED_SLAB' }).fields).toMatchObject({ CoverNominal: 25, CoverSource: 'table' });
    const mine = parseCoverTable({ en: { exposure: { XC1: 30 } } }, []);
    expect(specOf(slab, { role: 'SUSPENDED_SLAB', cover: mine }).fields['CoverNominal']).toBe(30);
    expect(specOf(slab, { role: 'SUSPENDED_SLAB' }).needsReview).toBe(true);
  });
});

describe('marks', () => {
  it('numbers each series by storey, x and y; same input gives the same marks', () => {
    const items = [
      { id: 'a', role: 'SUSPENDED_SLAB', storey: 1, x: 10, y: 0 }, { id: 'b', role: 'SUSPENDED_SLAB', storey: 1, x: 0, y: 0 }, { id: 'c', role: 'SUSPENDED_SLAB', storey: 2, x: 5, y: 5 },
      { id: 'd', role: 'COLUMN', storey: 0, x: 0, y: 3 }, { id: 'e', role: 'COLUMN', storey: 0, x: 0, y: 1 }, { id: 'f', role: 'WALL', storey: null, x: 0, y: 0 },
    ];
    const m = assignMarks(items);
    expect(m.get('b')!.mark).toBe('S1-01');
    expect(m.get('a')!.mark).toBe('S1-02');
    expect(m.get('c')!.mark).toBe('S2-01');
    expect(m.get('e')!.mark).toBe('C0-01');
    expect(m.get('d')!.mark).toBe('C0-02');
    expect(m.get('f')!.mark).toBe('WX-01');
    expect([...assignMarks([...items].reverse())].sort()).toEqual([...m].sort());
  });
  it('IFC marks: used when unique, ignored when repeated, no clash with generated ones', () => {
    const m = assignMarks([
      { id: 'a', role: 'COLUMN', storey: 0, x: 0, y: 0, ifcMark: 'K1' }, { id: 'b', role: 'COLUMN', storey: 0, x: 1, y: 0, ifcMark: 'K1' }, { id: 'c', role: 'COLUMN', storey: 0, x: 2, y: 0, ifcMark: ' P7 ' },
      { id: 'd', role: 'COLUMN', storey: 0, x: 3, y: 0, ifcMark: 'C0-01' }, { id: 'e', role: 'COLUMN', storey: 0, x: 4, y: 0 },
    ]);
    expect(m.get('c')).toEqual({ mark: 'P7', source: 'ifc' });
    expect(m.get('a')!.source).toBe('generated');
    expect(m.get('d')).toEqual({ mark: 'C0-01', source: 'ifc' });
    const gen = ['a', 'b', 'e'].map((k) => m.get(k)!.mark);
    expect(new Set([...gen, 'P7', 'C0-01']).size).toBe(5);
  });
});

describe('contacts and pour groups', () => {
  const B = (id: string, b: [number, number, number, number, number, number], storey = 0) => ({ id, bounds: b, storey });
  it('bears-on, touching, and nothing for a gap', () => {
    const g = contactGraph([B('slab', [0, 0, 3, 8, 8, 3.2], 1), B('beam', [0, 3.8, 2.6, 8, 4.2, 3]), B('col', [0, 3.8, 0, 0.4, 4.2, 2.6]), B('far', [20, 20, 0, 21, 21, 1])]);
    expect(g.restsOn.get('slab')).toEqual(['beam']);
    expect(g.carries.get('beam')).toEqual(['slab']);
    expect(g.restsOn.get('beam')).toEqual(['col']);
    expect(g.touching.get('far')).toBeUndefined();
    expect(g.touching.get('col')).toEqual(['beam']);
  });
  it('pour classes', () => {
    expect(pourClassOf('SUSPENDED_SLAB')).toBe('DECK');
    expect(pourClassOf('BEAM')).toBe('DECK');
    expect(pourClassOf('COLUMN')).toBe('VERTICAL');
    expect(pourClassOf('PAD_FOOTING')).toBe('FOUNDATION');
    expect(pourClassOf('STAIR')).toBeNull();
  });
  it('groups touching elements of one class on one storey, numbered per storey; precast and other storeys stay out', () => {
    const items = [
      { id: 's', role: 'SUSPENDED_SLAB', method: 'CAST_IN_PLACE', storey: 1, x: 0, y: 0 }, { id: 'b', role: 'DOWNSTAND_BEAM', method: 'CAST_IN_PLACE', storey: 1, x: 0, y: 4 },
      { id: 'c', role: 'COLUMN', method: 'CAST_IN_PLACE', storey: 1, x: 0, y: 4 }, { id: 'p', role: 'SUSPENDED_SLAB', method: 'PRECAST', storey: 1, x: 9, y: 0 },
      { id: 's2', role: 'SUSPENDED_SLAB', method: 'CAST_IN_PLACE', storey: 2, x: 0, y: 0 }, { id: 'x', role: 'SUSPENDED_SLAB', method: 'CAST_IN_PLACE', storey: 1, x: 30, y: 0 },
    ];
    const touching = new Map<string, string[]>([['s', ['b', 'p', 's2']], ['b', ['s', 'c']], ['c', ['b']], ['p', ['s']], ['s2', ['s']]]);
    const g = pourGroups(items, touching);
    expect(g.get('s')).toBe('PG-1-1');
    expect(g.get('b')).toBe('PG-1-1');
    expect(g.get('c')).toBeDefined();
    expect(g.get('c')).not.toBe('PG-1-1');
    expect(g.has('p')).toBe(false);
    expect(g.get('s2')).toBe('PG-2-1');
    expect(g.get('x')).toMatch(/^PG-1-\d$/);
    expect(g.get('x')).not.toBe(g.get('s'));
  });
});
