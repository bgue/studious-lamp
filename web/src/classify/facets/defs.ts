// Classification facets: the facet ids, their code lists (defaults) and the types of a facet result. No DOM.
// The design is docs/design/classification-facets.md; the user documentation is docs-features/classify.md, "Facets".
//
// A facet answers one question about an element (who builds it, where it sits, what it is made of, when it is built, which way it
// points, what it really is). Every facet has a code list, a review threshold and an on/off switch, kept in the schema's
// optional `facets` section (additive: a schema without it gets these defaults).

export const FACET_IDS = ['Trade', 'Placement', 'Material', 'Phase', 'Orientation', 'ClassRepair'] as const;
export type FacetId = (typeof FACET_IDS)[number];
export const isFacetId = (s: string): s is FacetId => (FACET_IDS as readonly string[]).includes(s);

/** Version written to `XR_<Facet>.SchemeVersion` and to the `facets.version` field of the schema. */
export const FACETS_VERSION = 'xr-facets/1';

/** Name of the property set of a facet: `XR_Trade`, `XR_Placement`, ... */
export const facetPset = (f: FacetId): string => `XR_${f}`;

export interface FacetCode {
  code: string;
  label: string;
  description: string;
}

export interface FacetDef {
  id: FacetId;
  /** The facet is computed and written. */
  enabled: boolean;
  /** A result below this confidence needs review. 0 to 1. */
  minConfidence: number;
  /** The question the facet answers (shown in the interface and in the model question). */
  description: string;
  codes: FacetCode[];
}

export type FacetDefs = Record<FacetId, FacetDef>;

/** The `facets` section of a schema file as parsed (all six facets present, defaults filled in). */
export interface FacetsSchema {
  version: string;
  facets: FacetDefs;
}

/** Who decided a facet value. */
export type FacetSource = 'rule' | 'model' | 'geometry' | 'ifc' | 'manual' | 'batch-learned';

export type FacetFieldValue = string | number | boolean;

/** One facet value of one element. `fields` are the facet-specific properties (see the namespace table in the docs). */
export interface FacetResult {
  facet: FacetId;
  code: string;
  label: string;
  /** Calibrated probability of `code`; 1 for a measured value or a manual choice. */
  confidence: number;
  source: FacetSource;
  /** Provider and model id, for source `model` and `batch-learned`. */
  model?: string;
  needsReview: boolean;
  /** Facet-specific properties: Placement (Exposure, LoadBearing, ExposureSource, LoadBearingSource), Orientation (Tilt, Azimuth, Upright, PrincipalAxis, Plausible), ClassRepair (OriginalClass, SuggestedClass, SuggestedPredefinedType, Applied), Trade (WorkPackage). */
  fields: Record<string, FacetFieldValue>;
  /** The probabilities of the options, for a model decision. */
  probabilities?: Record<string, number>;
  /** Why, for a rule or a measurement. */
  rationale?: string;
}

export type FacetSet = Partial<Record<FacetId, FacetResult>>;

const c = (code: string, label: string, description = label): FacetCode => ({ code, label, description });

const DEFAULT_CODES: Record<FacetId, FacetCode[]> = {
  Trade: [
    c('EARTH', 'Earthworks', 'Excavation, fill, grading and shoring'),
    c('CONC', 'Concrete works', 'Cast-in-place and precast concrete: foundations, slabs, walls, columns, beams, stairs'),
    c('STEEL', 'Steel works', 'Structural and miscellaneous steel: columns, beams, braces, stairs, railings'),
    c('TIMBER', 'Timber works', 'Structural and finish carpentry: timber and glulam frames, joists, rafters, CLT panels'),
    c('MASON', 'Masonry', 'Brick, block and stone walls'),
    c('ROOF', 'Roofing', 'Roof coverings, membranes, insulation above the deck, flashings'),
    c('FACADE', 'Facade and cladding', 'Exterior wall systems, cladding, curtain walling, rainscreens'),
    c('GLAZ', 'Glazing', 'Windows, glazed screens, skylights'),
    c('DRYLN', 'Drylining and partitions', 'Plasterboard walls and ceilings, metal stud partitions, suspended ceilings'),
    c('FINISH', 'Finishes', 'Floor, wall and ceiling finishes, paint, tiling, joinery, furniture'),
    c('DOORS', 'Doors and ironmongery', 'Doors, frames, hardware, shutters'),
    c('MECH', 'Mechanical (HVAC)', 'Ducts, air handling, chillers, boilers, heating and cooling pipework'),
    c('PLUMB', 'Plumbing', 'Water supply, drainage, sanitary fixtures'),
    c('ELEC', 'Electrical', 'Power, lighting, cable routes, switchgear, data and communications'),
    c('FIRE', 'Fire protection', 'Sprinklers, standpipes, fire alarm and detection'),
    c('LIFT', 'Vertical transport', 'Elevators, escalators, hoists'),
    c('SITE', 'Site works', 'Paving, landscaping, site utilities, fences, roads'),
    c('OTHER', 'Other', 'Work that fits none of the other trades'),
  ],
  Placement: [
    c('EXT', 'Exterior', 'Outside the building, exposed to weather'),
    c('INT', 'Interior', 'Inside the building envelope, not exposed to weather'),
    c('BOUNDARY', 'Envelope boundary', 'On the building envelope: weather on one side, building on the other'),
  ],
  Material: [
    c('CONCRETE', 'Concrete', 'Concrete, reinforced concrete, precast, grout, screed'),
    c('STEEL', 'Steel', 'Structural steel, reinforcing steel, stainless steel, cast iron'),
    c('TIMBER', 'Timber', 'Wood, glulam, CLT, plywood, OSB, timber boards'),
    c('MASONRY', 'Masonry', 'Brick, concrete block, calcium silicate, aerated block'),
    c('GYPSUM', 'Gypsum', 'Plasterboard, drywall, gypsum plaster'),
    c('GLASS', 'Glass', 'Glass and glazing units'),
    c('ALUMINIUM', 'Aluminium', 'Aluminium frames and sheet'),
    c('INSULATION', 'Insulation', 'Mineral wool, EPS, XPS, PIR, glass wool'),
    c('PLASTIC', 'Plastic', 'PVC, polyethylene, polypropylene and other polymers'),
    c('STONE', 'Stone', 'Natural stone, granite, marble, slate'),
    c('EARTH', 'Earth', 'Soil, gravel, sand, clay, fill'),
    c('OTHER', 'Other', 'Another material, or a mix with no main material'),
  ],
  Phase: [
    c('SUBSTR', 'Substructure', 'Below ground: excavation, footings, foundation walls, piles, ground slab'),
    c('FRAME', 'Frame', 'The load-bearing structure above ground: columns, beams, floor slabs, structural walls, stairs'),
    c('ENVELOPE', 'Envelope', 'The weather barrier: external walls, windows, external doors, roof'),
    c('SERVICES', 'Services', 'Mechanical, plumbing, electrical, fire and vertical transport installations'),
    c('FITOUT', 'Fit-out', 'Interior partitions, doors, ceilings, finishes, fixed furniture'),
    c('EXTERNAL', 'External works', 'Site works outside the building'),
  ],
  Orientation: [
    c('HORIZONTAL', 'Horizontal', 'A slab-like or compact element lying flat (its plane or footprint is horizontal)'),
    c('VERTICAL', 'Vertical', 'A wall-like element standing upright, or a linear element along the vertical axis'),
    c('INCLINED', 'Inclined', 'Tilted between horizontal and vertical (roofs, ramps, braces)'),
    c('ALONG_X', 'Along X', 'A horizontal linear element parallel to the model X axis (within 5 degrees)'),
    c('ALONG_Y', 'Along Y', 'A horizontal linear element parallel to the model Y axis (within 5 degrees)'),
    c('DIAGONAL', 'Diagonal', 'A horizontal linear element at an angle to both model axes'),
  ],
  ClassRepair: [
    c('KEEP', 'Keep the class', 'The IFC class is right, or no better class is known'),
    ...[
      ['IfcColumn', 'Column'], ['IfcBeam', 'Beam'], ['IfcMember', 'Member (brace, truss member)'], ['IfcWall', 'Wall'], ['IfcSlab', 'Slab'], ['IfcRoof', 'Roof'],
      ['IfcFooting', 'Footing'], ['IfcPile', 'Pile'], ['IfcStair', 'Stair'], ['IfcStairFlight', 'Stair flight'], ['IfcRamp', 'Ramp'], ['IfcRailing', 'Railing'],
      ['IfcDoor', 'Door'], ['IfcWindow', 'Window'], ['IfcCurtainWall', 'Curtain wall'], ['IfcPlate', 'Plate'], ['IfcCovering', 'Covering (ceiling, flooring, cladding)'],
      ['IfcPipeSegment', 'Pipe segment'], ['IfcDuctSegment', 'Duct segment'], ['IfcFurniture', 'Furniture'], ['IfcLightFixture', 'Light fixture'],
      ['IfcSanitaryTerminal', 'Sanitary terminal'], ['IfcPump', 'Pump'], ['IfcTank', 'Tank'], ['IfcFan', 'Fan'],
    ].map(([code, label]) => c(code!, label!, `Suggested IFC4 class ${code}`)),
  ],
};

const DEFAULT_DESCRIPTION: Record<FacetId, string> = {
  Trade: 'Who builds it (the work package)?',
  Placement: 'Where does it sit (exterior, interior, on the envelope) and does it carry load?',
  Material: 'What is it mainly made of?',
  Phase: 'When in the job is it built?',
  Orientation: 'Which way does it point? (measured from the geometry)',
  ClassRepair: 'What is it, when its IFC class is generic or the geometry contradicts it? (suggestions only)',
};

/** Facets that the decision model may be asked about. Orientation is measured only. */
export const MODEL_FACETS: readonly FacetId[] = ['Trade', 'Placement', 'Material', 'Phase', 'ClassRepair'];

/** The default definition of a facet. A new object each call. */
export function defaultFacetDef(id: FacetId, minConfidence = 0.6): FacetDef {
  return { id, enabled: true, minConfidence, description: DEFAULT_DESCRIPTION[id], codes: DEFAULT_CODES[id].map((x) => ({ ...x })) };
}

export function defaultFacetDefs(minConfidence = 0.6): FacetDefs {
  const out = {} as FacetDefs;
  for (const id of FACET_IDS) out[id] = defaultFacetDef(id, minConfidence);
  return out;
}

/** The facets section as it is written in the shipped schema file (keys are the facet ids). */
export function facetsSection(defs: FacetDefs = defaultFacetDefs()): Record<string, unknown> {
  const out: Record<string, unknown> = { version: FACETS_VERSION };
  for (const id of FACET_IDS) {
    const d = defs[id];
    out[id] = { enabled: d.enabled, minConfidence: d.minConfidence, description: d.description, codes: d.codes.map((x) => ({ code: x.code, label: x.label, description: x.description })) };
  }
  return out;
}

const isObj = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
const str = (v: unknown): v is string => typeof v === 'string' && v.trim() !== '';

/**
 * Check the `facets` section of a schema file. Never throws. A missing section, a missing facet or a facet without codes gets the
 * defaults; a malformed code list is an error (a plain-language message is pushed to `errors`).
 */
export function parseFacets(v: unknown, errors: string[], schemaMinConfidence = 0.6): FacetsSchema {
  const defs = defaultFacetDefs(schemaMinConfidence);
  if (v === undefined) return { version: FACETS_VERSION, facets: defs };
  if (!isObj(v)) {
    errors.push('"facets" must be an object with one entry per facet.');
    return { version: FACETS_VERSION, facets: defs };
  }
  if (v['version'] !== undefined && !str(v['version'])) errors.push('"facets.version" must be text such as xr-facets/1.');
  for (const id of FACET_IDS) {
    const raw = v[id];
    if (raw === undefined) continue;
    const path = `facets.${id}`;
    if (!isObj(raw)) { errors.push(`"${path}" must be an object.`); continue; }
    const d = defs[id];
    if (raw['enabled'] !== undefined) {
      if (typeof raw['enabled'] === 'boolean') d.enabled = raw['enabled'];
      else errors.push(`"${path}.enabled" must be true or false.`);
    }
    if (raw['minConfidence'] !== undefined) {
      if (typeof raw['minConfidence'] === 'number' && raw['minConfidence'] >= 0 && raw['minConfidence'] <= 1) d.minConfidence = raw['minConfidence'];
      else errors.push(`"${path}.minConfidence" must be a number from 0 to 1.`);
    }
    if (str(raw['description'])) d.description = raw['description'].trim();
    if (raw['codes'] !== undefined) {
      if (!Array.isArray(raw['codes']) || raw['codes'].length === 0) { errors.push(`"${path}.codes" must be a list with at least one code.`); continue; }
      const seen = new Set<string>();
      const codes: FacetCode[] = [];
      raw['codes'].forEach((x: unknown, i: number) => {
        if (!isObj(x) || !str(x['code']) || !str(x['label'])) { errors.push(`${path}.codes[${i}] needs a "code" and a "label".`); return; }
        const code = (x['code'] as string).trim();
        if (seen.has(code)) { errors.push(`The ${id} code "${code}" appears twice.`); return; }
        seen.add(code);
        codes.push({ code, label: (x['label'] as string).trim(), description: str(x['description']) ? (x['description'] as string).trim() : (x['label'] as string).trim() });
      });
      if (codes.length) d.codes = codes;
    }
  }
  return { version: str(v['version']) ? (v['version'] as string).trim() : FACETS_VERSION, facets: defs };
}

export const facetCode = (def: FacetDef, code: string): FacetCode | undefined => def.codes.find((x) => x.code === code);
export const facetLabel = (def: FacetDef, code: string): string => facetCode(def, code)?.label ?? code;
