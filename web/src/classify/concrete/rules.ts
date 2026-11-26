// Concrete family test and the rules of XR_ConcreteElement (role), XR_ConcreteMethod and XR_ConcreteReinforcement (type, scheme, ratio
// estimate). Pure. A rule returns a code and a confidence; at 0.85 and up it is final, below it the decision model is asked (when
// there is one) and the rule is the fallback, flagged for review. Design sections 1, 3.1 to 3.4 and 7.

import type { ClassifyInput } from '../types';
import { boolOf, materialRule, predefinedOf, propOf } from '../facets/facetRules';
import type { RuleOut } from '../facets/facetRules';
import type { FrameKind } from './geometry';
import { ROLE_CODES } from './defs';

export const CONCRETE_FINAL = 0.85;

const ci = (s: string): string => s.toLowerCase();

// ---------------------------------------------------------------- the family

const STRUCTURAL = new Set([
  'IfcSlab', 'IfcWall', 'IfcWallStandardCase', 'IfcWallElementedCase', 'IfcColumn', 'IfcColumnStandardCase', 'IfcBeam', 'IfcBeamStandardCase', 'IfcMember', 'IfcPlate', 'IfcStair', 'IfcStairFlight', 'IfcRamp', 'IfcRampFlight',
  'IfcRoof', 'IfcFooting', 'IfcPile', 'IfcBuildingElementProxy', 'IfcCivilElement', 'IfcChimney', 'IfcRailing', 'IfcSlabStandardCase', 'IfcSlabElementedCase',
]);
const NATURALLY_CONCRETE = new Set(['IfcFooting', 'IfcPile']);
const CONCRETE_PSET = /^Pset_(ConcreteElementGeneral|PrecastConcreteElement\w*)$/;

/** Could an element of this IFC class be concrete (the classes the family test looks at)? */
export const mayBeConcrete = (ifcClass: string): boolean => STRUCTURAL.has(ifcClass);

export const hasConcretePset = (i: ClassifyInput): boolean => Object.keys(i.psets).some((k) => CONCRETE_PSET.test(k));

/**
 * Is the element in the concrete family (design section 1)? Concrete material (the Material facet's code when given, else the keyword
 * rule), or a footing or pile whose material is not another one, or a structural element that carries a concrete or precast property set.
 * Masonry, steel and timber elements are out.
 */
export function isConcreteFamily(i: ClassifyInput, materialCode?: string): boolean {
  if (!STRUCTURAL.has(i.ifcClass)) return false;
  const mat = materialCode ?? materialRule(i)?.code;
  if (mat === 'CONCRETE') return true;
  if (hasConcretePset(i)) return true;
  if (NATURALLY_CONCRETE.has(i.ifcClass)) return !mat || mat === 'OTHER';
  return false;
}

/** The kind of local frame an IFC class asks for before the role is known. */
export function frameKindOfClass(ifcClass: string): FrameKind {
  if (/^IfcSlab|^IfcRoof/.test(ifcClass)) return 'slab';
  if (/^IfcWall/.test(ifcClass)) return 'wall';
  if (/^IfcColumn|^IfcPile$/.test(ifcClass)) return 'column';
  if (/^IfcBeam/.test(ifcClass)) return 'beam';
  if (ifcClass === 'IfcFooting') return 'footing';
  return 'other';
}

const GROUND_ROLES = new Set(['PAD_FOOTING', 'STRIP_FOOTING', 'RAFT', 'PILE_CAP', 'GRADE_BEAM', 'PLINTH', 'SLAB_ON_GRADE', 'PILE']);
export const isGroundRole = (role: string): boolean => GROUND_ROLES.has(role);
const FOUNDATION_SIDES = new Set(['PAD_FOOTING', 'STRIP_FOOTING', 'RAFT', 'PILE_CAP', 'GRADE_BEAM', 'PLINTH', 'PILE']);
export const groundSidesRole = (role: string): boolean => FOUNDATION_SIDES.has(role);

/** The frame of a role (design 3.5). */
export function frameKindOfRole(role: string): FrameKind {
  switch (role) {
    case 'PAD_FOOTING': case 'STRIP_FOOTING': case 'RAFT': case 'PILE_CAP': case 'PLINTH': case 'EQUIPMENT_PAD': return 'footing';
    case 'SLAB_ON_GRADE': case 'SUSPENDED_SLAB': case 'FLAT_SLAB': case 'RIBBED_SLAB': case 'WAFFLE_SLAB': case 'TRANSFER_SLAB': case 'TOPPING': case 'LANDING': case 'RAMP': return 'slab';
    case 'BEAM': case 'DOWNSTAND_BEAM': case 'UPSTAND_BEAM': case 'TRANSFER_BEAM': case 'GRADE_BEAM': case 'CORBEL': case 'CURB': return 'beam';
    case 'COLUMN': case 'PIER': case 'PILE': return 'column';
    case 'WALL': case 'SHEAR_WALL': case 'CORE_WALL': case 'RETAINING_WALL': case 'BASEMENT_WALL': case 'PARAPET': case 'PRECAST_PANEL': return 'wall';
    default: return 'other';
  }
}

// ---------------------------------------------------------------- allowed codes

const code = (...c: string[]): readonly string[] => c;
const ALL_ROLES = ROLE_CODES.map((r) => r.code);
const SLABS = code('SLAB_ON_GRADE', 'SUSPENDED_SLAB', 'FLAT_SLAB', 'RIBBED_SLAB', 'WAFFLE_SLAB', 'TRANSFER_SLAB', 'TOPPING', 'LANDING', 'RAFT', 'EQUIPMENT_PAD', 'PRECAST_PANEL', 'OTHER');
const WALLS = code('WALL', 'SHEAR_WALL', 'CORE_WALL', 'RETAINING_WALL', 'BASEMENT_WALL', 'PARAPET', 'CURB', 'PRECAST_PANEL', 'OTHER');
const BEAMS = code('BEAM', 'DOWNSTAND_BEAM', 'UPSTAND_BEAM', 'TRANSFER_BEAM', 'GRADE_BEAM', 'CORBEL', 'OTHER');
const COLUMNS = code('COLUMN', 'PIER', 'PLINTH', 'OTHER');

/** The role codes the decision model may choose from for an IFC class: a slab is never asked "COLUMN" (design section 7). */
export function allowedRoles(ifcClass: string): readonly string[] {
  if (/^IfcSlab/.test(ifcClass)) return SLABS;
  if (/^IfcWall/.test(ifcClass)) return WALLS;
  if (/^IfcBeam/.test(ifcClass)) return BEAMS;
  if (/^IfcColumn/.test(ifcClass)) return COLUMNS;
  if (ifcClass === 'IfcFooting') return code('PAD_FOOTING', 'STRIP_FOOTING', 'RAFT', 'PILE_CAP', 'GRADE_BEAM', 'PLINTH', 'OTHER');
  if (ifcClass === 'IfcPile') return code('PILE', 'OTHER');
  if (/^IfcStair/.test(ifcClass)) return code('STAIR', 'LANDING', 'OTHER');
  if (/^IfcRamp/.test(ifcClass)) return code('RAMP', 'OTHER');
  if (ifcClass === 'IfcRoof') return code('SUSPENDED_SLAB', 'FLAT_SLAB', 'OTHER');
  if (ifcClass === 'IfcRailing' || ifcClass === 'IfcChimney') return code('PARAPET', 'CURB', 'OTHER');
  return ALL_ROLES;
}

/** The role used when no rule and no model decides (flagged for review). */
export function defaultRole(ifcClass: string): string {
  if (/^IfcSlab|^IfcRoof/.test(ifcClass)) return 'SUSPENDED_SLAB';
  if (/^IfcWall/.test(ifcClass)) return 'WALL';
  if (/^IfcBeam/.test(ifcClass)) return 'BEAM';
  if (/^IfcColumn/.test(ifcClass)) return 'COLUMN';
  if (ifcClass === 'IfcFooting') return 'PAD_FOOTING';
  if (ifcClass === 'IfcPile') return 'PILE';
  if (/^IfcStair/.test(ifcClass)) return 'STAIR';
  if (/^IfcRamp/.test(ifcClass)) return 'RAMP';
  return 'OTHER';
}

// ---------------------------------------------------------------- the role rules

/** What the role rules know about an element besides its properties. */
export interface RoleContext {
  /** Frame extents by the class's frame: length, width, thickness (m), the footprint aspect and plan area. */
  length?: number;
  width?: number;
  thickness?: number;
  planAspect?: number;
  planArea?: number;
  /** Bottom of the element within 0.3 m of the ground level, and the element is on the lowest storey or below ground. */
  onGround?: boolean;
  belowGround?: boolean;
  /** Placement facet code, when known. */
  exposure?: string;
  /** IFC classes of the elements it bears on and of those that bear on it. */
  restsOn: readonly string[];
  carries: readonly string[];
  /** Orientation facet class (HORIZONTAL, VERTICAL, INCLINED, ...), when measured. */
  orientation?: string;
}

/** Text that names an element: name, type name, ObjectType, Description, Tag. */
export function nameText(i: ClassifyInput): string {
  const a = i.psets['Attr'] ?? {};
  return [i.name, i.type?.name ?? '', ...['ObjectType', 'Description'].map((k) => String(a[k] ?? ''))].join(' | ');
}

const NAME_ROLES: ReadonlyArray<readonly [string, RegExp]> = [
  ['PILE_CAP', /pile[ _-]?cap|pilecap|pfahlkopf|\bPC\d*\b/i],
  ['TRANSFER_SLAB', /transfer[ _-]?(slab|plate|deck)|lastverteil/i],
  ['TRANSFER_BEAM', /transfer[ _-]?(beam|girder)|abfang/i],
  ['GRADE_BEAM', /grade[ _-]?beam|ground[ _-]?beam|tie[ _-]?beam|foundation[ _-]?beam|strap[ _-]?beam|fundamentbalken|sockelbalken/i],
  ['RAFT', /\braft\b|mat[ _-]?foundation|plattenfundament|fundamentplatte/i],
  ['STRIP_FOOTING', /strip[ _-]?(footing|foundation)|wall[ _-]?footing|streifenfundament/i],
  ['PAD_FOOTING', /pad[ _-]?(footing|foundation)|isolated[ _-]?footing|spread[ _-]?footing|einzelfundament|\bpad\b/i],
  ['PLINTH', /plinth|sockel|stub[ _-]?column/i],
  ['EQUIPMENT_PAD', /equipment[ _-]?pad|machine[ _-]?base|housekeeping|maschinenfundament/i],
  ['SLAB_ON_GRADE', /slab[ _-]?on[ _-]?(grade|ground)|ground[ _-]?(floor[ _-]?)?slab|grade[ _-]?slab|\bSOG\b|bodenplatte|grundplatte|sauberkeitsschicht/i],
  ['FLAT_SLAB', /flat[ _-]?(slab|plate)|flachdecke|pilzdecke/i],
  ['RIBBED_SLAB', /ribbed|rippendecke|plattenbalken/i],
  ['WAFFLE_SLAB', /waffle|coffer|kassettendecke/i],
  ['TOPPING', /topping|screed|estrich|aufbeton/i],
  ['LANDING', /landing|podest/i],
  ['STAIR', /\bstair|treppe/i],
  ['RAMP', /\bramp|rampe/i],
  ['CORBEL', /corbel|konsole/i],
  ['CORE_WALL', /\bcore\b|lift[ _-]?core|stair[ _-]?core|elevator[ _-]?(shaft|core)|aufzugskern|treppenhauskern|\bkern\b/i],
  ['SHEAR_WALL', /shear[ _-]?wall|scheibe|aussteifung/i],
  ['RETAINING_WALL', /retaining|st(ü|ue|u)tzwand/i],
  ['BASEMENT_WALL', /basement[ _-]?wall|kellerwand|foundation[ _-]?wall|untergeschoss/i],
  ['PARAPET', /parapet|attika|br(ü|ue|u)stung/i],
  ['PRECAST_PANEL', /precast[ _-]?(wall|panel)|sandwich[ _-]?(wall|panel)|fertigteilwand|wall[ _-]?panel|tilt[ _-]?up/i],
  ['CURB', /\bcurb\b|\bkerb\b|aufkantung/i],
  ['UPSTAND_BEAM', /upstand[ _-]?beam|inverted[ _-]?beam|kerb[ _-]?beam/i],
  ['DOWNSTAND_BEAM', /downstand|drop[ _-]?beam|dropped[ _-]?beam|unterzug/i],
  ['PIER', /\bpier\b|pfeiler/i],
];

/** Roles that a name says, among the codes allowed for the class. Footing-only roles do not apply to other classes (allowed list). */
export function nameRole(i: ClassifyInput): { code: string; text: string } | null {
  const text = nameText(i);
  const ok = allowedRoles(i.ifcClass);
  for (const [role, re] of NAME_ROLES) {
    if (!ok.includes(role)) continue;
    // "PC" alone is a pile cap only on a footing
    if (role === 'PILE_CAP' && i.ifcClass !== 'IfcFooting' && !/pile[ _-]?cap|pilecap|pfahlkopf/i.test(text)) continue;
    const m = re.exec(text);
    if (m) return { code: role, text: m[0] };
  }
  return null;
}

const PREDEFINED: Record<string, Record<string, string>> = {
  IfcFooting: { PAD_FOOTING: 'PAD_FOOTING', STRIP_FOOTING: 'STRIP_FOOTING', PILE_CAP: 'PILE_CAP', FOOTING_BEAM: 'GRADE_BEAM', CAISSON_FOUNDATION: 'PIER' },
  IfcWall: { SHEAR: 'SHEAR_WALL', RETAININGWALL: 'RETAINING_WALL', PARAPET: 'PARAPET' },
  IfcSlab: { LANDING: 'LANDING', BASESLAB: 'SLAB_ON_GRADE' },
  IfcBeam: { LINTEL: 'BEAM', T_BEAM: 'BEAM', SPANDREL: 'BEAM', EDGEBEAM: 'BEAM', HOLLOWCORE: 'BEAM' },
  IfcColumn: { PILASTER: 'COLUMN', COLUMN: 'COLUMN' },
  IfcPile: { DRIVEN: 'PILE', JETGROUTING: 'PILE', BORED: 'PILE', COHESION: 'PILE', FRICTION: 'PILE', SUPPORT: 'PILE' },
  IfcStair: { STRAIGHT_RUN_STAIR: 'STAIR' },
};

/** The classes with `Standard` or `ElementedCase` suffixes read like the plain class. */
const baseClass = (c: string): string => c.replace(/(StandardCase|ElementedCase)$/, '');

/** XR_ConcreteElement.Code by rule: names, predefined type, class, then geometry. Null when nothing applies. */
export function roleRule(i: ClassifyInput, c: RoleContext): RuleOut | null {
  const cls = baseClass(i.ifcClass);
  const pre = predefinedOf(i);
  const named = nameRole(i);
  if (named) {
    // a name that agrees with the geometry or the class is final; "core" in a slab name etc. is filtered by the allowed codes
    return { code: named.code, confidence: 0.9, rationale: `name says "${named.text}"` };
  }
  if (/^IfcStair/.test(cls)) return { code: 'STAIR', confidence: 0.92, rationale: 'IFC class stair' };
  if (/^IfcRamp/.test(cls)) return { code: 'RAMP', confidence: 0.92, rationale: 'IFC class ramp' };
  if (cls === 'IfcPile') return { code: 'PILE', confidence: 0.95, rationale: 'IFC class pile' };
  const fromPre = PREDEFINED[cls]?.[pre];
  if (fromPre && !(cls === 'IfcSlab' && pre === 'BASESLAB')) return { code: fromPre, confidence: 0.9, rationale: `predefined type ${pre}` };
  const t = c.thickness ?? 0;
  switch (cls) {
    case 'IfcSlab': case 'IfcRoof': {
      if (pre === 'BASESLAB') {
        if (c.onGround) return { code: t >= 0.5 ? 'RAFT' : 'SLAB_ON_GRADE', confidence: t >= 0.5 ? 0.75 : 0.88, rationale: `base slab ${t >= 0.5 ? 'thicker than 0.5 m' : 'on the ground'}` };
        return { code: 'RAFT', confidence: 0.6, rationale: 'base slab not at the ground level' };
      }
      if (pre === 'ROOF' || cls === 'IfcRoof') return { code: 'SUSPENDED_SLAB', confidence: 0.86, rationale: 'roof slab' };
      if (c.onGround) return { code: t >= 0.6 ? 'RAFT' : 'SLAB_ON_GRADE', confidence: t >= 0.6 ? 0.7 : 0.86, rationale: 'bottom at the ground level on the lowest storey' };
      if (c.carries.some((x) => /^IfcColumn|^IfcWall/.test(x)) && t >= 0.5) return { code: 'TRANSFER_SLAB', confidence: 0.7, rationale: `${t.toFixed(2)} m thick and carries columns or walls` };
      if (c.restsOn.length) return { code: 'SUSPENDED_SLAB', confidence: 0.86, rationale: 'rests on other concrete elements above the ground' };
      if (!c.belowGround) return { code: 'SUSPENDED_SLAB', confidence: 0.7, rationale: 'above the ground, no support found' };
      return null;
    }
    case 'IfcWall': {
      const h = c.width ?? 0;
      if (c.belowGround && t >= 0.2) return { code: 'BASEMENT_WALL', confidence: 0.75, rationale: 'wall below the ground level' };
      if (h > 0 && h < 0.3) return { code: 'CURB', confidence: 0.7, rationale: `${h.toFixed(2)} m high` };
      if (boolOf(propOf(i, 'LoadBearing')) === true && c.orientation === 'VERTICAL') return { code: 'WALL', confidence: 0.88, rationale: 'load-bearing wall' };
      return { code: 'WALL', confidence: 0.86, rationale: 'wall, no specific role found' };
    }
    case 'IfcColumn': {
      if ((c.length ?? 9) < 0.5 && (c.length ?? 0) > 0) return { code: 'PLINTH', confidence: 0.7, rationale: `${(c.length ?? 0).toFixed(2)} m high` };
      return { code: 'COLUMN', confidence: 0.9, rationale: 'IFC class column' };
    }
    case 'IfcBeam': {
      if (c.carries.some((x) => /^IfcColumn|^IfcWall/.test(x))) return { code: 'TRANSFER_BEAM', confidence: 0.7, rationale: 'carries columns or walls' };
      if ((c.onGround || c.belowGround) && c.restsOn.some((x) => /^IfcFooting|^IfcPile/.test(x))) return { code: 'GRADE_BEAM', confidence: 0.75, rationale: 'beam at the ground between footings' };
      if (c.restsOn.length && c.restsOn.every((x) => /^IfcSlab/.test(x))) return { code: 'UPSTAND_BEAM', confidence: 0.7, rationale: 'rests on a slab, no column or wall under it' };
      return { code: 'BEAM', confidence: 0.86, rationale: 'IFC class beam' };
    }
    case 'IfcFooting': {
      const area = c.planArea ?? 0;
      if (area >= 60) return { code: 'RAFT', confidence: 0.75, rationale: `${area.toFixed(0)} m2 in plan` };
      if ((c.planAspect ?? 1) >= 3.5) return { code: 'STRIP_FOOTING', confidence: 0.75, rationale: `plan aspect ${(c.planAspect ?? 1).toFixed(1)}` };
      if (area > 0) return { code: 'PAD_FOOTING', confidence: 0.75, rationale: 'compact footing' };
      return null;
    }
    default: {
      // proxies, members, plates: from the shape
      const a = c.planAspect ?? 1;
      if (c.orientation === 'VERTICAL' && t > 0 && t < 0.6 && (c.length ?? 0) > 2 * t) return { code: 'WALL', confidence: 0.6, rationale: 'upright plate-like' };
      if (c.orientation === 'HORIZONTAL' && t > 0 && t < 0.6 && a < 6) return { code: 'SUSPENDED_SLAB', confidence: 0.55, rationale: 'flat plate-like' };
      return null;
    }
  }
}

// ---------------------------------------------------------------- method

export interface MethodContext { role: string; tendonNearby?: boolean }

const IN_SITE = new Set(['PAD_FOOTING', 'STRIP_FOOTING', 'RAFT', 'PILE_CAP', 'PILE', 'GRADE_BEAM', 'SLAB_ON_GRADE', 'PLINTH', 'RETAINING_WALL', 'BASEMENT_WALL', 'CORE_WALL']);

/** XR_ConcreteMethod.Code by rule: precast psets, IFC construction method, names, tendons nearby; else the in-place default (low confidence for roles that may be precast). */
export function methodRule(i: ClassifyInput, c: MethodContext): RuleOut {
  if (Object.keys(i.psets).some((k) => /^Pset_PrecastConcreteElement/.test(k))) return { code: 'PRECAST', confidence: 0.95, rationale: 'has a precast concrete property set' };
  const cm = propOf(i, 'ConstructionMethod') ?? propOf(i, 'ConstructionType');
  if (typeof cm === 'string') {
    if (/pre[- ]?cast|fertigteil|prefab/i.test(cm)) return { code: 'PRECAST', confidence: 0.95, rationale: `ConstructionMethod "${cm}"` };
    if (/in[- ]?situ|cast[- ]?in|on[- ]?site|ortbeton|cip/i.test(cm)) return { code: 'CAST_IN_PLACE', confidence: 0.95, rationale: `ConstructionMethod "${cm}"` };
  }
  const text = nameText(i);
  const footing = i.ifcClass === 'IfcFooting' || i.ifcClass === 'IfcPile';
  const tests: ReadonlyArray<readonly [string, RegExp, boolean]> = [
    ['COMPOSITE_DECK', /composite[ _-]?(deck|slab)|metal[ _-]?deck|profiled[ _-]?(steel|deck)|steel[ _-]?deck|trapez|verbunddecke|comflor|holorib/i, true],
    ['TILT_UP', /tilt[ _-]?up/i, true],
    ['POST_TENSIONED', /post[ _-]?tension|\bPT\b|nachspann/i, true],
    ['PRECAST', /pre[- ]?cast|hollow[ _-]?core|hohlplatte|fertigteil|filigran|half[ _-]?slab|double[ _-]?tee|prefab|\bTT\b|\bPC\b/i, !footing],
  ];
  for (const [code, re, on] of tests) {
    if (!on) continue;
    const m = re.exec(text);
    if (m) return { code, confidence: 0.88, rationale: `name says "${m[0]}"` };
  }
  if (c.role === 'PRECAST_PANEL') return { code: 'PRECAST', confidence: 0.88, rationale: 'role precast panel' };
  if (c.tendonNearby && /SLAB|BEAM/.test(c.role)) return { code: 'POST_TENSIONED', confidence: 0.7, rationale: 'tendons run through it' };
  if (IN_SITE.has(c.role)) return { code: 'CAST_IN_PLACE', confidence: 0.86, rationale: `${c.role.toLowerCase().replace(/_/g, ' ')} is cast on site unless stated otherwise` };
  return { code: 'CAST_IN_PLACE', confidence: 0.55, rationale: 'default, nothing says how it is made' };
}

// ---------------------------------------------------------------- reinforcement

const STRUCTURAL_ROLES = new Set(ROLE_CODES.map((r) => r.code).filter((r) => !['CURB', 'EQUIPMENT_PAD', 'PARAPET', 'TOPPING', 'OTHER', 'CORBEL'].includes(r)));

export interface ReinforcementContext { role: string; method: string }

/** XR_ConcreteReinforcement.Code by rule. */
export function reinforcementRule(i: ClassifyInput, c: ReinforcementContext): RuleOut {
  if (c.method === 'POST_TENSIONED') return { code: 'POST_TENSIONED', confidence: 0.9, rationale: 'post-tensioned element' };
  const text = `${nameText(i)} | ${i.material ?? ''}`;
  const plain = /unreinforced|plain concrete|blinding|lean concrete|mass concrete|unbewehrt|sauberkeitsschicht|magerbeton/i.exec(text);
  if (plain) return { code: 'PLAIN', confidence: 0.9, rationale: `name says "${plain[0]}"` };
  const fibre = /fib(re|er)[ _-]?reinforced|steel[ _-]?fib(re|er)|\bSFRC\b|faserbeton|stahlfaser/i.exec(text);
  if (fibre) return { code: 'FIBRE', confidence: 0.9, rationale: `name says "${fibre[0]}"` };
  if (propOf(i, 'ReinforcementVolumeRatio') !== undefined || propOf(i, 'ReinforcementAreaRatio') !== undefined || propOf(i, 'ReinforcementStrengthClass') !== undefined) return { code: 'REINFORCED', confidence: 0.95, rationale: 'IFC carries reinforcement properties' };
  if (/reinforced|stahlbeton|\bRC\b|armiert|bewehrt/i.test(text)) return { code: 'REINFORCED', confidence: 0.9, rationale: 'names reinforced concrete' };
  if (STRUCTURAL_ROLES.has(c.role)) return { code: 'REINFORCED', confidence: 0.86, rationale: 'structural concrete is reinforced unless stated otherwise' };
  return { code: 'REINFORCED', confidence: 0.6, rationale: 'non-structural element, reinforcement not stated' };
}

export interface SchemeContext { role: string; ifcClass: string; thickness?: number; spanRatio?: number; supportsTwoSided?: boolean; name: string }

/** The reinforcement scheme by rule: slabs ONE_WAY / TWO_WAY, walls SINGLE_LAYER / DOUBLE_LAYER, linear members LINKS. Null when nothing is known. */
export function schemeRule(c: SchemeContext): RuleOut | null {
  const r = c.role;
  if (/^(BEAM|DOWNSTAND_BEAM|UPSTAND_BEAM|TRANSFER_BEAM|GRADE_BEAM|COLUMN|PIER|PILE|PLINTH)$/.test(r)) return { code: 'LINKS', confidence: 0.9, rationale: 'linear member: bars with links' };
  if (/^(WALL|SHEAR_WALL|CORE_WALL|RETAINING_WALL|BASEMENT_WALL|PARAPET|PRECAST_PANEL)$/.test(r)) {
    const t = c.thickness ?? 0;
    if (t >= 0.2) return { code: 'DOUBLE_LAYER', confidence: 0.86, rationale: `${t.toFixed(2)} m thick` };
    if (t > 0 && t < 0.14) return { code: 'SINGLE_LAYER', confidence: 0.8, rationale: `${t.toFixed(2)} m thick` };
    return t > 0 ? { code: 'DOUBLE_LAYER', confidence: 0.6, rationale: `${t.toFixed(2)} m thick, between the usual limits` } : null;
  }
  if (/^(PAD_FOOTING|RAFT|PILE_CAP)$/.test(r)) return { code: 'TWO_WAY', confidence: 0.85, rationale: 'foundation block reinforced both ways' };
  if (r === 'STRIP_FOOTING' || r === 'TOPPING' || r === 'EQUIPMENT_PAD' || r === 'CURB' || r === 'CORBEL' || r === 'STAIR' || r === 'RAMP' || r === 'OTHER') return null;
  // slabs
  const nm = c.name;
  if (r === 'RIBBED_SLAB' || /hollow[ _-]?core|hohlplatte|one[ _-]?way|einachsig|plank/i.test(nm)) return { code: 'ONE_WAY', confidence: 0.9, rationale: r === 'RIBBED_SLAB' ? 'ribbed slab spans one way' : 'name says one-way' };
  if (r === 'WAFFLE_SLAB' || r === 'FLAT_SLAB' || /two[ _-]?way|zweiachsig|flat[ _-]?plate/i.test(nm)) return { code: 'TWO_WAY', confidence: 0.9, rationale: r === 'FLAT_SLAB' || r === 'WAFFLE_SLAB' ? `${r.toLowerCase().replace(/_/g, ' ')} spans both ways` : 'name says two-way' };
  if (r === 'SLAB_ON_GRADE') return { code: 'TWO_WAY', confidence: 0.86, rationale: 'ground slab, mesh both ways' };
  if (r === 'LANDING') return { code: 'ONE_WAY', confidence: 0.8, rationale: 'landing spans between its supports' };
  if (c.supportsTwoSided) return { code: 'ONE_WAY', confidence: 0.86, rationale: 'bears on two opposite sides only' };
  const q = c.spanRatio;
  if (q === undefined) return null;
  if (q >= 2) return { code: 'ONE_WAY', confidence: 0.88, rationale: `span ratio ${q.toFixed(2)}` };
  if (q <= 1.4) return { code: 'TWO_WAY', confidence: 0.86, rationale: `span ratio ${q.toFixed(2)}` };
  return { code: q >= 1.7 ? 'ONE_WAY' : 'TWO_WAY', confidence: 0.6, rationale: `span ratio ${q.toFixed(2)}, between the usual limits` };
}

/** Typical reinforcement ratio (kg of steel per m3 of concrete) by role, for take-off before rebar exists (design 3.4). */
export const RATIO_ESTIMATE: Record<string, number> = {
  PAD_FOOTING: 90, STRIP_FOOTING: 90, RAFT: 90, PILE_CAP: 100, PILE: 100, GRADE_BEAM: 150, PLINTH: 150,
  SLAB_ON_GRADE: 90, SUSPENDED_SLAB: 105, FLAT_SLAB: 120, RIBBED_SLAB: 110, WAFFLE_SLAB: 110, TRANSFER_SLAB: 250, TOPPING: 40, LANDING: 110,
  BEAM: 175, DOWNSTAND_BEAM: 175, UPSTAND_BEAM: 175, TRANSFER_BEAM: 275, COLUMN: 215, PIER: 215,
  WALL: 80, SHEAR_WALL: 100, CORE_WALL: 100, RETAINING_WALL: 90, BASEMENT_WALL: 90, PARAPET: 80, PRECAST_PANEL: 80,
  STAIR: 120, RAMP: 100, CORBEL: 200, CURB: 60, EQUIPMENT_PAD: 80, OTHER: 100,
};

/** Estimate of the ratio for a role and reinforcement type (kg/m3); 0 for plain and fibre concrete. */
export function ratioEstimate(role: string, reinforcement: string): number {
  if (reinforcement === 'PLAIN' || reinforcement === 'FIBRE') return 0;
  return RATIO_ESTIMATE[role] ?? RATIO_ESTIMATE['OTHER']!;
}
