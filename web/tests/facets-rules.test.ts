// Rule facets: Material keywords, Placement from Pset_*Common, Trade, Phase, ClassRepair, load-bearing.

import { describe, expect, it } from 'vitest';
import { classRepairRule, ifcPlacement, loadBearingRule, materialHits, materialRule, phaseRule, placementRule, tradeRule } from '../src/classify/facets/facetRules';
import type { FacetContext } from '../src/classify/facets/facetRules';
import { measureOrientation } from '../src/classify/facets/orientation';
import type { ClassifyInput } from '../src/classify/types';
import { box } from './facets-helpers';

const input = (cls: string, o: Partial<ClassifyInput> = {}): ClassifyInput => ({ id: 'G', ifcClass: cls, name: '', psets: {}, ...o });
type CtxArg = Omit<Partial<FacetContext>, 'input'> & { input?: Partial<ClassifyInput> };
const ctx = (cls: string, o: CtxArg = {}): FacetContext => {
  const { input: i, ...rest } = o;
  return { input: input(cls, i), ...rest };
};

describe('Material keyword table', () => {
  const m = (material: string): string | undefined => materialRule(input('IfcWall', { material }))?.code;
  it('maps IFC material names to the codes', () => {
    expect(m('Concrete C30/37')).toBe('CONCRETE');
    expect(m('C30/37')).toBe('CONCRETE');
    expect(m('Reinforced concrete')).toBe('CONCRETE');
    expect(m('Steel S355')).toBe('STEEL');
    expect(m('S355JR')).toBe('STEEL');
    expect(m('S355')).toBe('STEEL');
    expect(m('Glulam GL24h')).toBe('TIMBER');
    expect(m('CLT')).toBe('TIMBER');
    expect(m('Spruce timber')).toBe('TIMBER');
    expect(m('Brick')).toBe('MASONRY');
    expect(m('Concrete block')).toBe('CONCRETE'); // structural tie-break order: concrete first
    expect(m('Kalksandstein')).toBe('MASONRY');
    expect(m('Leichtbeton 102890359 0.24')).toBe('CONCRETE');
    expect(m('Gypsum plasterboard 12.5')).toBe('GYPSUM');
    expect(m('Float glass')).toBe('GLASS');
    expect(m('Aluminium')).toBe('ALUMINIUM');
    expect(m('Mineral wool 100')).toBe('INSULATION');
    expect(m('EPS 035')).toBe('INSULATION');
    expect(m('XPS')).toBe('INSULATION');
    expect(m('PVC-U')).toBe('PLASTIC');
    expect(m('Granite')).toBe('STONE');
    expect(m('Gravel backfill')).toBe('EARTH');
  });
  it('picks the most frequent material of a layer set; structural wins a tie', () => {
    expect(m('Gypsum board, Mineral wool, Steel stud, Gypsum board')).toBe('GYPSUM');
    expect(m('Brick, Insulation')).toBe('MASONRY');
    expect(materialHits('Brick, Insulation').size).toBe(2);
  });
  it('reads the type name, then the name, with lower confidence, and a class prior last', () => {
    const t = materialRule(input('IfcSlab', { type: { ifcClass: 'IfcSlabType', name: 'Concrete slab 200', psets: {} } }))!;
    expect(t.code).toBe('CONCRETE');
    const n = materialRule(input('IfcBeam', { name: 'Timber beam 12/24' }))!;
    expect(n.code).toBe('TIMBER');
    const mat = materialRule(input('IfcWall', { material: 'Brick', name: 'Timber wall' }))!;
    expect(mat.confidence).toBeGreaterThan(n.confidence);
    expect(materialRule(input('IfcWindow'))!.confidence).toBeLessThan(0.85);
    expect(materialRule(input('IfcFlowTerminal', { name: 'x' }))).toBeNull();
  });
});

describe('Placement from Pset_*Common', () => {
  const wall = (v: unknown, extra: Record<string, unknown> = {}): ClassifyInput => input('IfcWall', { psets: { Pset_WallCommon: { IsExternal: v, ...extra } as never } });
  it('IsExternal on a wall is the envelope, on a column it is exterior; false is interior', () => {
    expect(ifcPlacement(wall(true)).exposure).toBe('BOUNDARY');
    expect(ifcPlacement(wall(false)).exposure).toBe('INT');
    expect(ifcPlacement(wall('TRUE')).exposure).toBe('BOUNDARY');
    expect(ifcPlacement(input('IfcColumn', { psets: { Pset_ColumnCommon: { IsExternal: true } } })).exposure).toBe('EXT');
    expect(ifcPlacement(input('IfcWall')).exposure).toBeUndefined();
    expect(ifcPlacement(wall(true, { LoadBearing: true })).loadBearing).toBe(true);
  });
  it('the element\'s own value wins (source ifc); a confident contradicting geometry wins and asks for review', () => {
    expect(placementRule(wall(true), null)).toMatchObject({ code: 'BOUNDARY', source: 'ifc', needsReview: false });
    expect(placementRule(wall(true), { exposure: 'BOUNDARY', confidence: 0.85, rationale: '' })).toMatchObject({ code: 'BOUNDARY', source: 'ifc' });
    const bad = placementRule(wall(true), { exposure: 'INT', confidence: 0.8, rationale: 'both faces blocked' })!;
    expect(bad).toMatchObject({ code: 'INT', source: 'geometry', needsReview: true });
    // a weak geometric hunch does not override the model's own data
    expect(placementRule(wall(true), { exposure: 'INT', confidence: 0.5, rationale: '' })).toMatchObject({ code: 'BOUNDARY', source: 'ifc' });
    // an "internal" wall with a clear outside face
    expect(placementRule(wall(false), { exposure: 'BOUNDARY', confidence: 0.85, rationale: '' })).toMatchObject({ code: 'BOUNDARY', source: 'geometry', needsReview: true });
  });
  it('without its own value the geometry decides; with neither there is no rule', () => {
    expect(placementRule(input('IfcWall'), { exposure: 'INT', confidence: 0.8, rationale: 'x' })).toMatchObject({ code: 'INT', source: 'geometry' });
    expect(placementRule(input('IfcWall'), null)).toBeNull();
  });
});

describe('load-bearing', () => {
  it('own property first, then structural classes, then thick concrete or masonry walls', () => {
    expect(loadBearingRule(ctx('IfcWall', { input: { psets: { Pset_WallCommon: { LoadBearing: false } } } }))).toMatchObject({ value: false, source: 'ifc' });
    expect(loadBearingRule(ctx('IfcColumn'))).toMatchObject({ value: true, source: 'rule' });
    expect(loadBearingRule(ctx('IfcDoor'))).toMatchObject({ value: false });
    const m = measureOrientation(box(0, 1.5, 0, 5, 3, 0.3))!;
    expect(loadBearingRule(ctx('IfcWall', { material: 'CONCRETE', measure: m }))).toMatchObject({ value: true });
    const thin = measureOrientation(box(0, 1.5, 0, 5, 3, 0.1))!;
    expect(loadBearingRule(ctx('IfcWall', { material: 'GYPSUM', measure: thin }))).toMatchObject({ value: false });
    expect(loadBearingRule(ctx('IfcWall'))).toBeNull();
  });
});

describe('Trade', () => {
  const t = (cls: string, o: CtxArg = {}): string | undefined => tradeRule(ctx(cls, o))?.code;
  it('class, discipline and material give the trade', () => {
    expect(t('IfcSlab', { material: 'CONCRETE' })).toBe('CONC');
    expect(t('IfcWall', { material: 'MASONRY' })).toBe('MASON');
    expect(t('IfcWall', { material: 'GYPSUM' })).toBe('DRYLN');
    expect(t('IfcColumn', { material: 'STEEL' })).toBe('STEEL');
    expect(t('IfcBeam', { material: 'TIMBER' })).toBe('TIMBER');
    expect(t('IfcCovering', { input: { psets: { Attr: { PredefinedType: 'CEILING' } } }, material: 'GYPSUM' })).toBe('DRYLN');
    expect(t('IfcCovering', { input: { psets: { Attr: { PredefinedType: 'FLOORING' } } } })).toBe('FINISH');
    expect(t('IfcDoor')).toBe('DOORS');
    expect(t('IfcWindow')).toBe('GLAZ');
    expect(t('IfcCurtainWall')).toBe('FACADE');
    expect(t('IfcRoof')).toBe('ROOF');
    expect(t('IfcPipeSegment', { discipline: 'PLB' })).toBe('PLUMB');
    expect(t('IfcPipeSegment', { discipline: 'MEC' })).toBe('MECH');
    expect(t('IfcPipeSegment', { discipline: 'FPR' })).toBe('FIRE');
    expect(t('IfcDuctSegment')).toBe('MECH');
    expect(t('IfcCableCarrierSegment')).toBe('ELEC');
    expect(t('IfcTransportElement')).toBe('LIFT');
    expect(t('IfcSite')).toBe('SITE');
  });
  it('a slab with no material is a weak guess, a proxy with no hint is open', () => {
    expect(tradeRule(ctx('IfcSlab', { discipline: 'STR' }))!.confidence).toBeLessThan(0.85);
    expect(tradeRule(ctx('IfcSlab'))).toBeNull();
    expect(tradeRule(ctx('IfcBuildingElementProxy'))).toBeNull();
    expect(tradeRule(ctx('IfcBuildingElementProxy', { material: 'CONCRETE' }))!.confidence).toBeLessThan(0.85);
  });
});

describe('Phase', () => {
  const p = (cls: string, o: CtxArg = {}): string | undefined => phaseRule(ctx(cls, o))?.code;
  it('from trade, placement, class and level', () => {
    expect(p('IfcFooting', { trade: 'CONC' })).toBe('SUBSTR');
    expect(p('IfcSlab', { trade: 'CONC', belowGround: true })).toBe('SUBSTR');
    expect(p('IfcColumn', { trade: 'CONC' })).toBe('FRAME');
    expect(p('IfcBeam', { trade: 'STEEL' })).toBe('FRAME');
    expect(p('IfcSlab', { trade: 'CONC', exposure: 'INT' })).toBe('FRAME');
    expect(p('IfcWall', { trade: 'MASON', exposure: 'BOUNDARY' })).toBe('ENVELOPE');
    expect(p('IfcWall', { trade: 'CONC', exposure: 'BOUNDARY', loadBearing: true })).toBe('FRAME');
    expect(p('IfcWall', { trade: 'DRYLN', exposure: 'INT' })).toBe('FITOUT');
    expect(p('IfcWall', { trade: 'CONC', exposure: 'INT', loadBearing: true })).toBe('FRAME');
    expect(p('IfcWindow', { trade: 'GLAZ', exposure: 'BOUNDARY' })).toBe('ENVELOPE');
    expect(p('IfcRoof', { trade: 'ROOF' })).toBe('ENVELOPE');
    expect(p('IfcDoor', { trade: 'DOORS', exposure: 'BOUNDARY' })).toBe('ENVELOPE');
    expect(p('IfcDoor', { trade: 'DOORS', exposure: 'INT' })).toBe('FITOUT');
    expect(p('IfcPipeSegment', { trade: 'PLUMB' })).toBe('SERVICES');
    expect(p('IfcDuctSegment', { trade: 'MECH' })).toBe('SERVICES');
    expect(p('IfcCovering', { trade: 'FINISH' })).toBe('FITOUT');
    expect(p('IfcSite', { trade: 'SITE' })).toBe('EXTERNAL');
  });
  it('is open without a trade', () => {
    expect(p('IfcBuildingElementProxy')).toBeUndefined();
  });
});

describe('ClassRepair', () => {
  const thinVertical = measureOrientation(box(0, 1.5, 0, 0.3, 3, 0.3))!;
  it('a long thin vertical proxy named Col... is an IfcColumn, with the shape agreeing', () => {
    const r = classRepairRule(ctx('IfcBuildingElementProxy', { input: { name: 'Col-12' }, measure: thinVertical }))!;
    expect(r.code).toBe('IfcColumn');
    expect(r.confidence).toBeGreaterThanOrEqual(0.85);
    expect(r.fields).toMatchObject({ OriginalClass: 'IfcBuildingElementProxy', SuggestedClass: 'IfcColumn', SuggestedPredefinedType: 'COLUMN', Applied: false });
  });
  it('a name that disagrees with the shape is a weak suggestion', () => {
    const r = classRepairRule(ctx('IfcBuildingElementProxy', { input: { name: 'Column 5' }, measure: measureOrientation(box(0, 0, 0, 6, 0.3, 0.2))! }))!;
    expect(r.code).toBe('IfcColumn');
    expect(r.confidence).toBeLessThan(0.85);
  });
  it('shape alone gives a low-confidence suggestion; a proxy with no hint gets none', () => {
    expect(classRepairRule(ctx('IfcBuildingElementProxy', { input: { name: 'Generic 1' }, measure: thinVertical }))).toMatchObject({ code: 'IfcColumn' });
    expect(classRepairRule(ctx('IfcBuildingElementProxy', { input: { name: 'Generic 1' } }))).toBeNull();
  });
  it('an untyped IfcBuiltElement is generic, a typed one is not; a class the geometry contradicts is repaired', () => {
    expect(classRepairRule(ctx('IfcBuiltElement', { input: { name: 'Door 1' } }))).toMatchObject({ code: 'IfcDoor' });
    expect(classRepairRule(ctx('IfcBuiltElement', { input: { name: 'Door 1', type: { ifcClass: 'T', name: 'x', psets: {} } } }))).toBeNull();
    expect(classRepairRule(ctx('IfcWall', { input: { name: 'Wall 1' }, measure: thinVertical }))).toMatchObject({ code: 'IfcColumn' });
    expect(classRepairRule(ctx('IfcWall', { input: { name: 'Wall 1' }, measure: measureOrientation(box(0, 1.5, 0, 5, 3, 0.2))! }))).toBeNull();
    expect(classRepairRule(ctx('IfcColumn', { input: { name: 'C1' }, measure: measureOrientation(box(0, 3, 0, 6, 0.3, 0.3))! }))).toMatchObject({ code: 'IfcBeam' });
    expect(classRepairRule(ctx('IfcColumn', { input: { name: 'C1' }, measure: thinVertical }))).toBeNull();
  });
  it('names in other words: beam, door, ceiling, pipe, furniture', () => {
    const c = (name: string): string | undefined => classRepairRule(ctx('IfcBuildingElementProxy', { input: { name } }))?.code;
    expect(c('Steel girder G4')).toBe('IfcBeam');
    expect(c('Tür 1')).toBe('IfcDoor');
    expect(c('Suspended ceiling')).toBe('IfcCovering');
    expect(c('Pipe DN50')).toBe('IfcPipeSegment');
    expect(c('Office chair')).toBe('IfcFurniture');
    expect(c('Thing')).toBeUndefined();
  });
});
