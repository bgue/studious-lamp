// The deterministic rules of the facets: Material (keyword table), Placement from the element's own Pset_*Common properties,
// Trade (class + discipline + material), Phase (trade + placement + level) and ClassRepair (names and shape). Pure, no DOM.
// A rule gives a code and a confidence; at or above RULE_FINAL it is final, below it the decision model is asked (when there is one)
// and the rule is the fallback. Design: docs/design/classification-facets.md. Docs: docs-features/classify.md, "Facets".

import type { ClassifyInput, PsetValue } from '../types';
import type { OrientationMeasure } from './orientation';
import type { PlacementGeo } from './placementGeometry';
import type { FacetId } from './defs';

export const FACET_RULE_FINAL = 0.85;

export interface RuleOut {
  code: string;
  confidence: number;
  rationale: string;
  /** Facet-specific properties the rule fills in. */
  fields?: Record<string, string | number | boolean>;
}

/** What the rules know about one element besides its properties. All optional: a missing value just narrows what a rule can say. */
export interface FacetContext {
  input: ClassifyInput;
  /** The discipline code (of the schema in use, or the default code list). */
  discipline?: string;
  measure?: OrientationMeasure | null;
  placementGeo?: PlacementGeo | null;
  /** The element lies below the ground level of the model (its top is at or below the lowest storey's floor, or in a basement). */
  belowGround?: boolean;
  /** Values of the facets decided before this one. */
  material?: string;
  exposure?: string;
  loadBearing?: boolean;
  trade?: string;
}

const ci = (s: string): string => s.toLowerCase();

export function propOf(i: ClassifyInput, name: string): PsetValue | undefined {
  for (const set of Object.values(i.psets)) if (name in set) return set[name];
  return undefined;
}

/** A property from a `Pset_*Common` set first, then from any set. */
function commonProp(i: ClassifyInput, name: string): PsetValue | undefined {
  for (const [set, props] of Object.entries(i.psets)) if (/^Pset_.*Common$/.test(set) && name in props) return props[name];
  return propOf(i, name);
}

export function boolOf(v: PsetValue | undefined): boolean | undefined {
  if (typeof v === 'boolean') return v;
  if (typeof v === 'number') return v !== 0;
  if (typeof v === 'string') {
    const s = v.trim().toLowerCase();
    if (['true', 'yes', 'ja', '.t.', '1'].includes(s)) return true;
    if (['false', 'no', 'nein', '.f.', '0'].includes(s)) return false;
  }
  return undefined;
}

export const predefinedOf = (i: ClassifyInput): string => {
  const v = i.psets['Attr']?.['PredefinedType'] ?? propOf(i, 'PredefinedType');
  return typeof v === 'string' ? v.toUpperCase() : '';
};

// ---------------------------------------------------------------- Material

/** Keyword table: the code, then the pattern (lower case text). Order is the tie-break: structural materials first. */
export const MATERIAL_KEYWORDS: ReadonlyArray<readonly [string, RegExp]> = [
  ['CONCRETE', /concrete|\bc\d{2}\/\d{2}\b|reinforced|\brc\b|beton|precast|screed|grout|\bcement\b|stahlbeton/],
  ['STEEL', /\bsteel\b|\bs(235|275|355|420|460)[a-z0-9]{0,3}\b|stahl|stainless|galvani[sz]ed|\bfe ?\d{3}\b|cast iron|\biron\b|rebar/],
  ['TIMBER', /timber|\bwood|glulam|\bclt\b|\blvl\b|plywood|\bosb\b|holz|lumber|\bspruce\b|\bpine\b|\boak\b|larch|hardwood|softwood|brettsperrholz|\bbsh\b/],
  ['MASONRY', /\bbrick|\bblock|masonry|\bcmu\b|mortar|ziegel|mauerwerk|calcium silicate|kalksandstein|\baac\b|aerated|\bporenbeton\b/],
  ['STONE', /\bstone\b|granite|marble|slate|limestone|sandstone|travertine|\bnaturstein\b/],
  ['GYPSUM', /gypsum|plasterboard|plaster board|drywall|gyproc|\bgkb\b|\bgips\b|gipskarton|fermacell/],
  ['GLASS', /\bglass\b|glazing|\bglas|\bigu\b|\bfloat\b|verglasung/],
  ['ALUMINIUM', /alumin|\balu\b/],
  ['PLASTIC', /plastic|\bpvc\b|\bupvc\b|\bpe\b|\bhdpe\b|\bpp\b|polyethylene|polypropylene|\babs\b|vinyl|\bpex\b|polycarbonate|acrylic|kunststoff/],
  ['INSULATION', /insulat|mineral wool|rockwool|\beps\b|\bxps\b|glass wool|\bpir\b|\bpur\b|\bfoam\b|d(ä|a)mm|isolier|fibreglass|stone wool/],
  ['EARTH', /\bearth\b|\bsoil\b|gravel|\bsand\b|\bclay\b|backfill|hardcore|\bfill\b|\bdirt\b|erdreich|\bkies\b/],
];

/** The material codes named in a text, with the number of hits of each. */
export function materialHits(text: string): Map<string, number> {
  const t = ci(text);
  const out = new Map<string, number>();
  for (const [code, re] of MATERIAL_KEYWORDS) {
    const g = new RegExp(re.source, re.flags.includes('g') ? re.flags : `${re.flags}g`);
    const n = (t.match(g) ?? []).length;
    if (n > 0) out.set(code, n);
  }
  return out;
}

const bestOf = (hits: Map<string, number>): { code: string; n: number; total: number } | null => {
  let best: { code: string; n: number; total: number } | null = null;
  let total = 0;
  for (const n of hits.values()) total += n;
  for (const [code] of MATERIAL_KEYWORDS) {
    const n = hits.get(code);
    if (n !== undefined && (!best || n > best.n)) best = { code, n, total };
  }
  return best;
};

/** Material from IFC material names and layer sets (strongest), then the type name, the name and the material properties. */
export function materialRule(i: ClassifyInput): RuleOut | null {
  const fromMaterial = i.material ? materialHits(i.material) : new Map<string, number>();
  const m = bestOf(fromMaterial);
  if (m) {
    const multi = fromMaterial.size > 1;
    return { code: m.code, confidence: multi ? 0.8 : 0.92, rationale: `IFC material "${i.material}"` };
  }
  const props: string[] = [];
  for (const [set, p] of Object.entries(i.psets)) {
    if (/material/i.test(set)) for (const v of Object.values(p)) if (typeof v === 'string') props.push(v);
    for (const [k, v] of Object.entries(p)) if (/^(Material|Finish|Surface)\w*$/i.test(k) && typeof v === 'string') props.push(v);
  }
  const text = [i.type?.name ?? '', String(i.psets['Attr']?.['ObjectType'] ?? ''), ...props].join(' | ');
  const t = bestOf(materialHits(text));
  if (t) return { code: t.code, confidence: 0.78, rationale: 'a material word in the type name or a property' };
  const n = bestOf(materialHits(i.name));
  if (n) return { code: n.code, confidence: 0.7, rationale: `a material word in the name "${i.name}"` };
  // class priors (weak: the model is asked, when there is one)
  if (i.ifcClass === 'IfcWindow' || i.ifcClass === 'IfcCurtainWall') return { code: 'GLASS', confidence: 0.55, rationale: `${i.ifcClass} is mostly glass` };
  if (i.ifcClass === 'IfcFooting' || i.ifcClass === 'IfcPile') return { code: 'CONCRETE', confidence: 0.6, rationale: `${i.ifcClass} is usually concrete` };
  return null;
}

// ---------------------------------------------------------------- Placement

const STRUCTURAL_CLASSES = /^Ifc(Column|Beam|Footing|Pile|Member)(StandardCase)?$/;
const ENVELOPE_LIKE = /^IfcWall|^IfcCurtainWall$|^IfcWindow$|^IfcDoor$|^IfcRoof$/;

export interface IfcPlacement {
  exposure?: 'EXT' | 'INT' | 'BOUNDARY';
  loadBearing?: boolean;
}

/** The element's own `Pset_*Common.IsExternal` and `LoadBearing`. IsExternal true on a wall, window, door or roof is the envelope (BOUNDARY), on anything else EXT. */
export function ifcPlacement(i: ClassifyInput): IfcPlacement {
  const out: IfcPlacement = {};
  const ext = boolOf(commonProp(i, 'IsExternal'));
  if (ext === true) out.exposure = ENVELOPE_LIKE.test(i.ifcClass) ? 'BOUNDARY' : 'EXT';
  else if (ext === false) out.exposure = 'INT';
  const lb = boolOf(commonProp(i, 'LoadBearing'));
  if (lb !== undefined) out.loadBearing = lb;
  return out;
}

export interface PlacementDecision {
  code: 'EXT' | 'INT' | 'BOUNDARY';
  confidence: number;
  source: 'ifc' | 'geometry';
  needsReview: boolean;
  rationale: string;
}

/**
 * Placement from the element's own properties and the geometry. The element's own value wins (source `ifc`), unless the geometry
 * contradicts it with confidence: an "external" wall inside the plan, an "internal" wall with a clear outside face. Then the
 * geometry wins and the element needs review. With no own value the geometry decides. Null when neither says anything.
 */
export function placementRule(i: ClassifyInput, geo: PlacementGeo | null | undefined): PlacementDecision | null {
  const own = ifcPlacement(i).exposure;
  if (own) {
    if (geo && geo.confidence >= 0.75) {
      const ownInside = own === 'INT';
      const geoInside = geo.exposure === 'INT';
      if (ownInside !== geoInside) return { code: geo.exposure, confidence: Math.min(0.6, geo.confidence), source: 'geometry', needsReview: true, rationale: `IsExternal says ${own}, but the geometry says ${geo.exposure} (${geo.rationale})` };
    }
    return { code: own, confidence: 0.9, source: 'ifc', needsReview: false, rationale: 'Pset_*Common.IsExternal of the element' };
  }
  if (geo) return { code: geo.exposure, confidence: geo.confidence, source: 'geometry', needsReview: geo.confidence < 0.6, rationale: geo.rationale };
  return null;
}

/** Is the element load-bearing? From its own property, then by rule. Null when open. `source` tells which. */
export function loadBearingRule(c: FacetContext): { value: boolean; confidence: number; source: 'ifc' | 'rule'; rationale: string } | null {
  const i = c.input;
  const own = ifcPlacement(i).loadBearing;
  if (own !== undefined) return { value: own, confidence: 0.9, source: 'ifc', rationale: 'Pset_*Common.LoadBearing of the element' };
  const cls = i.ifcClass;
  if (STRUCTURAL_CLASSES.test(cls)) return { value: true, confidence: 0.9, source: 'rule', rationale: `${cls} is a structural class` };
  if (/^IfcStair|^IfcRamp/.test(cls)) return { value: c.discipline === 'STR', confidence: 0.6, source: 'rule', rationale: 'stairs bear load only when structural' };
  const structural = c.discipline === 'STR';
  const heavy = c.material === 'CONCRETE' || c.material === 'MASONRY' || c.material === 'STEEL';
  if (/^IfcSlab/.test(cls)) {
    if (structural) return { value: true, confidence: 0.85, source: 'rule', rationale: 'a slab of a structural discipline' };
    if (c.material === 'CONCRETE') return { value: true, confidence: 0.75, source: 'rule', rationale: 'a concrete slab' };
    return null;
  }
  if (/^IfcWall/.test(cls)) {
    if (structural) return { value: true, confidence: 0.85, source: 'rule', rationale: 'a wall of a structural discipline' };
    const thick = c.measure ? Math.min(c.measure.size[0], c.measure.size[1]) : undefined;
    if (heavy && thick !== undefined && thick >= 0.2) return { value: true, confidence: 0.7, source: 'rule', rationale: `a ${Math.round(thick * 100)} cm ${ci(c.material ?? '')} wall` };
    if (c.material === 'GYPSUM' || c.material === 'GLASS' || c.material === 'INSULATION') return { value: false, confidence: 0.85, source: 'rule', rationale: `a ${ci(c.material)} wall carries no load` };
    if (thick !== undefined && thick < 0.12) return { value: false, confidence: 0.75, source: 'rule', rationale: 'a thin wall' };
    return null;
  }
  if (/^Ifc(Door|Window|Covering|Furniture|FurnishingElement|CurtainWall|Railing|Plate)$|^IfcFlow|^IfcDistribution|^IfcPipe|^IfcDuct|^IfcCable|^IfcLight|^IfcSanitary|^IfcElectric/.test(cls)) return { value: false, confidence: 0.85, source: 'rule', rationale: `${cls} carries no building load` };
  if (cls === 'IfcRoof') return { value: false, confidence: 0.6, source: 'rule', rationale: 'a roof covering; its structure is separate' };
  return null;
}

// ---------------------------------------------------------------- Trade

const MATERIAL_TRADE: Record<string, string> = { CONCRETE: 'CONC', STEEL: 'STEEL', TIMBER: 'TIMBER', MASONRY: 'MASON', STONE: 'MASON', GLASS: 'GLAZ', GYPSUM: 'DRYLN', EARTH: 'EARTH' };

const ELECTRICAL = /^Ifc(CableCarrier|CableSegment|CableFitting|Electric|Lamp|LightFixture|Outlet|SwitchingDevice|DistributionBoard|JunctionBox|Protective|Transformer|Motor|Generator|Communications|Audio|Sensor|Alarm|Actuator|Controller|UnitaryControl)/;
const MECHANICAL = /^Ifc(Duct|Fan|AirTerminal|AirToAir|Boiler|Chiller|Coil|Compressor|CoolingTower|Damper|Filter|Heat|Humidifier|Evaporat|Condenser|Burner|Unitary|Valve)/;
const PLUMBING = /^Ifc(Sanitary|WasteTerminal|Tank|Pump|StackTerminal|Interceptor|Valve)/;
const PIPES = /^Ifc(PipeSegment|PipeFitting)$/;
const FIRE = /^IfcFireSuppression|^IfcFireAlarm/;
const SITE = /^Ifc(Site|GeographicElement|Pavement|Road|Kerb|Course|Railway|Bridge|Alignment)/;
const EARTHWORKS = /^IfcEarthworks|^IfcGeotechnical/;

/** The trade of an element: by class, with the discipline and the material deciding where the class alone does not. */
export function tradeRule(c: FacetContext): RuleOut | null {
  const i = c.input;
  const cls = i.ifcClass;
  const pre = predefinedOf(i);
  const mat = c.material;
  const byMat = mat ? MATERIAL_TRADE[mat] : undefined;
  const d = c.discipline;
  const out = (code: string, confidence: number, rationale: string): RuleOut => ({ code, confidence, rationale });

  if (cls === 'IfcDoor') return out('DOORS', 0.95, 'IfcDoor');
  if (cls === 'IfcWindow') return out('GLAZ', 0.9, 'IfcWindow');
  if (cls === 'IfcCurtainWall') return out('FACADE', 0.9, 'IfcCurtainWall');
  if (cls === 'IfcRoof') return out('ROOF', 0.9, 'IfcRoof');
  if (/^IfcTransportElement|^IfcLift|^IfcElevator|^IfcEscalator/.test(cls)) return out('LIFT', 0.9, cls);
  if (FIRE.test(cls)) return out('FIRE', 0.9, cls);
  if (SITE.test(cls)) return out('SITE', 0.9, cls);
  if (EARTHWORKS.test(cls)) return out('EARTH', 0.9, cls);
  if (cls === 'IfcCovering') {
    if (/CEILING/.test(pre)) return out(mat === 'GYPSUM' || !mat ? 'DRYLN' : 'FINISH', mat === 'GYPSUM' ? 0.9 : 0.8, 'a ceiling covering');
    if (/CLADDING/.test(pre)) return out('FACADE', 0.85, 'a cladding covering');
    if (/ROOFING/.test(pre)) return out('ROOF', 0.85, 'a roofing covering');
    if (/FLOORING|WRAPPING|MEMBRANE|SKIRTING|MOLDING|INSULATION/.test(pre)) return out('FINISH', 0.8, `a ${ci(pre)} covering`);
    return out(mat === 'GYPSUM' ? 'DRYLN' : 'FINISH', 0.75, 'a covering');
  }
  if (/^IfcWall/.test(cls)) {
    if (byMat && mat !== 'EARTH') return out(byMat, 0.85, `a wall of ${ci(mat!)}`);
    if (c.exposure === 'BOUNDARY') return out('FACADE', 0.55, 'a wall on the envelope with no material');
    if (d === 'STR') return out('CONC', 0.55, 'a wall of a structural discipline');
    return out('DRYLN', 0.5, 'a wall with no material');
  }
  if (/^IfcSlab/.test(cls)) {
    if (/ROOF/.test(pre) && mat !== 'CONCRETE') return out('ROOF', 0.85, 'a roof slab');
    if (byMat) return out(byMat, 0.88, `a slab of ${ci(mat!)}`);
    if (d === 'STR') return out('CONC', 0.6, 'a slab of a structural discipline');
    return null;
  }
  if (/^Ifc(Column|Beam|Member|Plate|Footing|Pile)/.test(cls)) {
    if (byMat) return out(byMat, 0.88, `${cls} of ${ci(mat!)}`);
    if (/^Ifc(Footing|Pile)/.test(cls)) return out('CONC', 0.7, `${cls} is usually concrete`);
    // A sloping member or beam with no material is roof framing (rafters, purlins at a pitch): the roofer or carpenter builds it.
    const m = c.measure;
    if (/^Ifc(Member|Beam)/.test(cls) && m && m.shape === 'linear' && m.tilt >= 10 && m.tilt <= 75) return out('ROOF', 0.6, `a sloping ${cls === 'IfcMember' ? 'member' : 'beam'} with no material (${m.tilt} degrees): roof framing`);
    return null;
  }
  if (/^IfcStair|^IfcRamp/.test(cls)) {
    if (mat === 'CONCRETE' || mat === 'STEEL' || mat === 'TIMBER') return out(byMat!, 0.8, `${cls} of ${ci(mat)}`);
    return null;
  }
  if (cls === 'IfcRailing') return out(mat === 'TIMBER' ? 'TIMBER' : 'STEEL', 0.6, 'a railing');
  if (/^Ifc(Furniture|FurnishingElement|SystemFurniture)/.test(cls)) return out('FINISH', 0.65, 'furniture and fixtures');
  if (PIPES.test(cls)) {
    if (d === 'PLB') return out('PLUMB', 0.9, 'a pipe of the plumbing discipline');
    if (d === 'MEC') return out('MECH', 0.85, 'a pipe of the mechanical discipline');
    if (d === 'FPR') return out('FIRE', 0.9, 'a pipe of fire protection');
    if (d === 'ELE') return out('ELEC', 0.7, 'a conduit of the electrical discipline');
    return out('PLUMB', 0.6, 'a pipe with no discipline');
  }
  if (ELECTRICAL.test(cls)) return out('ELEC', 0.9, cls);
  if (PLUMBING.test(cls) && !MECHANICAL.test(cls)) return out(d === 'MEC' ? 'MECH' : 'PLUMB', d === 'MEC' || d === 'PLB' ? 0.85 : 0.75, cls);
  if (MECHANICAL.test(cls)) return out(d === 'PLB' ? 'PLUMB' : 'MECH', 0.88, cls);
  if (/^IfcFlow|^IfcDistribution/.test(cls)) {
    if (d === 'PLB') return out('PLUMB', 0.8, 'a distribution element of plumbing');
    if (d === 'MEC') return out('MECH', 0.8, 'a distribution element of the mechanical discipline');
    if (d === 'ELE') return out('ELEC', 0.8, 'a distribution element of the electrical discipline');
    if (d === 'FPR') return out('FIRE', 0.8, 'a distribution element of fire protection');
  }
  // a generic element with a known material or discipline
  if (byMat && cls === 'IfcBuildingElementProxy') return out(byMat, 0.55, `a generic element of ${ci(mat!)}`);
  return null;
}

// ---------------------------------------------------------------- Phase

const FRAME_CLASSES = /^Ifc(Column|Beam|Member|Slab|Stair|StairFlight|Ramp|RampFlight|Footing|Pile)/;

/** The phase of an element, from its trade, placement, class and level. Null when the trade is unknown. */
export function phaseRule(c: FacetContext): RuleOut | null {
  const cls = c.input.ifcClass;
  const t = c.trade;
  const out = (code: string, confidence: number, rationale: string): RuleOut => ({ code, confidence, rationale });
  if (/^Ifc(Footing|Pile)/.test(cls)) return out('SUBSTR', 0.95, `${cls} is substructure`);
  if (t === 'SITE') return out('EXTERNAL', 0.9, 'site works');
  if (t === 'EARTH') return out(c.belowGround ? 'SUBSTR' : 'EXTERNAL', 0.8, 'earthworks');
  if (c.belowGround && (FRAME_CLASSES.test(cls) || /^IfcWall/.test(cls)) && t !== 'DOORS') return out('SUBSTR', 0.85, 'a structural element below ground');
  if (t === 'MECH' || t === 'PLUMB' || t === 'ELEC' || t === 'FIRE' || t === 'LIFT') return out('SERVICES', 0.88, `${t} installations`);
  if (cls === 'IfcRoof' || t === 'ROOF') return out('ENVELOPE', 0.88, 'the roof');
  if (cls === 'IfcWindow' || cls === 'IfcCurtainWall' || t === 'GLAZ' || t === 'FACADE') return out('ENVELOPE', 0.88, 'windows and facade');
  if (cls === 'IfcDoor') return out(c.exposure === 'BOUNDARY' || c.exposure === 'EXT' ? 'ENVELOPE' : 'FITOUT', c.exposure ? 0.85 : 0.6, c.exposure === 'BOUNDARY' || c.exposure === 'EXT' ? 'an external door' : 'an interior door');
  if (/^IfcWall/.test(cls)) {
    if (c.exposure === 'BOUNDARY') {
      if ((t === 'CONC' || t === 'STEEL' || t === 'TIMBER') && c.loadBearing) return out('FRAME', 0.75, 'a load-bearing wall of structural material');
      return out('ENVELOPE', 0.85, 'a wall on the envelope');
    }
    if (c.exposure === 'INT') {
      if (c.loadBearing && (t === 'CONC' || t === 'STEEL' || t === 'TIMBER' || t === 'MASON')) return out('FRAME', 0.8, 'a load-bearing interior wall');
      if (t === 'DRYLN' || t === 'FINISH') return out('FITOUT', 0.85, 'a partition');
      return out('FITOUT', 0.65, 'an interior wall');
    }
    if (c.exposure === 'EXT') return out('EXTERNAL', 0.6, 'a wall outside the building');
    return null;
  }
  if (FRAME_CLASSES.test(cls) && (t === 'CONC' || t === 'STEEL' || t === 'TIMBER' || t === 'MASON')) return out('FRAME', 0.88, `structure (${t})`);
  if (t === 'DRYLN' || t === 'FINISH' || t === 'DOORS') return out('FITOUT', 0.85, `${t} work`);
  if (c.exposure === 'EXT' && !t) return out('EXTERNAL', 0.5, 'outside the building');
  return null;
}

// ---------------------------------------------------------------- ClassRepair

export interface Suggestion {
  ifcClass: string;
  predefinedType: string;
}

/** Name words that point to a class, in priority order. */
const NAME_CLASSES: ReadonlyArray<readonly [RegExp, string, string]> = [
  [/\bcurtain ?wall|\bfacade\b|fassade/, 'IfcCurtainWall', ''],
  [/(^|[\s_\-:.])(col|column|columns|pillar|pier|post|stütze|stuetze|stutze|support)(?![a-z])|^col/, 'IfcColumn', 'COLUMN'],
  [/\b(beam|girder|joist|lintel|rafter|purlin|träger|traeger|binder|bearer)s?\b/, 'IfcBeam', 'BEAM'],
  [/\b(brace|bracing|truss|strut|stringer|chord|member)s?\b/, 'IfcMember', 'BRACE'],
  [/\b(footing|foundation|fundament|strip foundation|pad foundation)s?\b/, 'IfcFooting', 'PAD_FOOTING'],
  [/\bpiles?\b/, 'IfcPile', ''],
  [/\b(door|doors|tür|tuer|gate)\b/, 'IfcDoor', 'DOOR'],
  [/\b(window|windows|fenster|skylight)\b/, 'IfcWindow', 'WINDOW'],
  [/\b(stairs?|staircase|treppe)\b/, 'IfcStair', ''],
  [/\b(ramp|rampe)\b/, 'IfcRamp', ''],
  [/\b(railing|balustrade|handrail|guardrail|geländer)\b/, 'IfcRailing', ''],
  [/\b(roof|roofing|dach)\b/, 'IfcRoof', ''],
  [/\b(ceiling|decke abgehängt|soffit)\b/, 'IfcCovering', 'CEILING'],
  [/\b(slab|floor|deck|decke|bodenplatte|plinth)s?\b/, 'IfcSlab', 'FLOOR'],
  [/\b(wall|walls|partition|wand|parapet)\b/, 'IfcWall', 'STANDARD'],
  [/\b(pipe|pipes|tube|rohr|conduit)\b/, 'IfcPipeSegment', ''],
  [/\b(duct|ducts|kanal)\b/, 'IfcDuctSegment', ''],
  [/\b(chair|table|desk|bench|sofa|bed|cabinet|shelf|furniture|stuhl|tisch|möbel)s?\b/, 'IfcFurniture', ''],
  [/\b(lamp|luminaire|light fitting|light fixture|leuchte)s?\b/, 'IfcLightFixture', ''],
  [/\b(sink|toilet|wc|basin|bath|shower|urinal|waschbecken)s?\b/, 'IfcSanitaryTerminal', ''],
  [/\bpumps?\b/, 'IfcPump', ''],
  [/\btanks?\b/, 'IfcTank', ''],
  [/\bfans?\b/, 'IfcFan', ''],
];

const GENERIC = /^Ifc(BuildingElementProxy|BuiltElement|ElementProxy|Element|BuildingElement|ProxyElement)$/;

/** Is the class generic (a proxy, or an untyped built element), so that a better class is worth looking for? */
export function isGenericClass(i: ClassifyInput): boolean {
  if (i.ifcClass === 'IfcBuildingElementProxy' || i.ifcClass === 'IfcElementProxy' || i.ifcClass === 'IfcProxy') return true;
  return GENERIC.test(i.ifcClass) && !i.type;
}

/** Does the shape say that the class is wrong? Returns the class the shape points to, or null. */
export function shapeContradiction(i: ClassifyInput, m: OrientationMeasure | null | undefined): { ifcClass: string; rationale: string } | null {
  if (!m) return null;
  const cls = i.ifcClass;
  const slender = m.spread[0] >= 3 * m.spread[1];
  if (/^IfcWall/.test(cls) && m.shape === 'linear' && m.class === 'VERTICAL' && Math.max(m.size[0], m.size[1]) <= 0.6) return { ifcClass: 'IfcColumn', rationale: 'a wall that is a thin vertical bar' };
  if (/^IfcBeam/.test(cls) && m.class === 'VERTICAL' && m.shape === 'linear') return { ifcClass: 'IfcColumn', rationale: 'a beam standing upright' };
  if (/^IfcColumn/.test(cls) && m.shape === 'linear' && slender && (m.class === 'ALONG_X' || m.class === 'ALONG_Y' || m.class === 'DIAGONAL')) return { ifcClass: 'IfcBeam', rationale: 'a column lying along a horizontal axis' };
  if (/^IfcSlab/.test(cls) && m.shape === 'planar' && m.class === 'VERTICAL') return { ifcClass: 'IfcWall', rationale: 'a slab standing upright' };
  return null;
}

function predefinedFor(cls: string, m: OrientationMeasure | null | undefined, text: string): string {
  const row = NAME_CLASSES.find((r) => r[1] === cls);
  let p = row?.[2] ?? '';
  if (cls === 'IfcSlab' && m) p = m.class === 'INCLINED' ? 'ROOF' : /\b(roof|dach)\b/.test(text) ? 'ROOF' : /foundation|base|bodenplatte|ground/.test(text) ? 'BASESLAB' : 'FLOOR';
  if (cls === 'IfcWall' && m && m.class !== 'VERTICAL') p = '';
  return p;
}

/** A class suggestion for a generic element (from its name, type name and shape) or for a class the geometry contradicts. Null: keep. */
export function classRepairRule(c: FacetContext): (RuleOut & { suggestion: Suggestion }) | null {
  const i = c.input;
  const m = c.measure;
  const generic = isGenericClass(i);
  const contra = generic ? null : shapeContradiction(i, m);
  if (!generic && !contra) return null;
  const mk = (cls: string, confidence: number, why: string): RuleOut & { suggestion: Suggestion } => {
    const text = ci(`${i.name} ${i.type?.name ?? ''}`);
    const pre = predefinedFor(cls, m, text);
    return { code: cls, confidence, rationale: why, suggestion: { ifcClass: cls, predefinedType: pre }, fields: { OriginalClass: i.ifcClass, SuggestedClass: cls, SuggestedPredefinedType: pre, Applied: false } };
  };
  if (contra) return mk(contra.ifcClass, 0.6, `${contra.rationale} (the class ${i.ifcClass} contradicts the geometry)`);
  const text = ci([i.name, i.type?.name ?? '', String(i.psets['Attr']?.['ObjectType'] ?? '')].join(' '));
  for (const [re, cls] of NAME_CLASSES) {
    if (!re.test(text)) continue;
    const agrees = shapeAgrees(cls, m);
    if (agrees === true) return mk(cls, 0.9, `the name says ${cls} and the shape agrees`);
    if (agrees === false) return mk(cls, 0.5, `the name says ${cls}, but the shape does not fit`);
    return mk(cls, 0.8, `the name or type name says ${cls}`);
  }
  // no name hint: a clear shape alone, with a low confidence
  if (m && m.shape === 'linear' && m.spread[0] >= 4 * m.spread[1]) {
    if (m.class === 'VERTICAL') return mk('IfcColumn', 0.55, 'a long thin vertical bar');
    if (m.class === 'ALONG_X' || m.class === 'ALONG_Y' || m.class === 'DIAGONAL') return mk('IfcBeam', 0.5, 'a long thin horizontal bar');
  }
  return null;
}

/** Does the measured shape fit a class? true/false, or null when the class has no shape expectation or there is no measure. */
export function shapeAgrees(cls: string, m: OrientationMeasure | null | undefined): boolean | null {
  if (!m) return null;
  switch (cls) {
    case 'IfcColumn': return m.shape === 'linear' && m.class === 'VERTICAL';
    case 'IfcBeam': return m.shape === 'linear' && m.class !== 'VERTICAL';
    case 'IfcWall': case 'IfcDoor': case 'IfcWindow': case 'IfcCurtainWall': return m.class === 'VERTICAL' || (m.shape !== 'planar' && m.size[2] >= Math.min(m.size[0], m.size[1]));
    case 'IfcSlab': case 'IfcRoof': case 'IfcCovering': return m.shape === 'planar' && (m.class === 'HORIZONTAL' || m.class === 'INCLINED');
    default: return null;
  }
}

/** Which facets a rule function exists for (Orientation is measured, not ruled). */
export const RULE_FACETS: readonly FacetId[] = ['Material', 'Placement', 'Trade', 'Phase', 'ClassRepair'];
