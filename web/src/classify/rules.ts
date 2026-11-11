// Deterministic rules, the cheapest step of the pipeline: an IFC class map with pset, system-name and name hints, and a
// default MasterFormat division per class. A rule names the discipline, sub-discipline and division by the codes of the
// DEFAULT schema ("rules keys"). resolveRule maps them onto the schema in use: a discipline matches by its code or by its
// `rulesKey`; a key that the schema does not have gives no rule (the element goes on to the cache and the model).
// A rule with confidence at or above RULE_FINAL is final.

import { divisionTitle, findDiscipline, findSub, masterformatBuildingOnly } from './schema';
import type { ClassificationSchema, ClassifyInput, PsetValue } from './types';

export const RULE_FINAL = 0.85;

/** A rule hit resolved onto the schema in use. */
export interface Decision {
  discipline: string;
  subDiscipline: string | null;
  division: string | null;
  section: string | null;
  confidence: number;
  rationale: string;
}

export interface RuleHit {
  discipline: string;
  subDiscipline: string | null;
  division: string | null;
  section?: string | null;
  confidence: number;
  rationale: string;
}

const INFRA_CLASSES = new Set([
  'IfcRoad', 'IfcRoadPart', 'IfcPavement', 'IfcKerb', 'IfcCourse', 'IfcRailway', 'IfcRailwayPart', 'IfcTrackElement', 'IfcBridge', 'IfcBridgePart',
  'IfcEarthworksElement', 'IfcEarthworksFill', 'IfcEarthworksCut', 'IfcGeotechnicalElement', 'IfcGeotechnicalStratum', 'IfcSite', 'IfcAlignment',
]);

/** Text of an element that the hints search: names, types, systems, material, parents and pset names, lower case. */
export function hayOf(i: ClassifyInput): string {
  const parts: string[] = [i.name, i.type?.name ?? '', ...(i.systems ?? []), i.material ?? '', ...Object.keys(i.psets)];
  for (const k of ['ObjectType', 'Description', 'Tag', 'PredefinedType']) {
    const v = i.psets['Attr']?.[k];
    if (typeof v === 'string') parts.push(v);
  }
  for (const p of i.hierarchy?.parents ?? []) parts.push(p.name);
  return parts.join(' | ').toLowerCase();
}

/**
 * Is the element part of a building (so MasterFormat applies)? Uses the hierarchy when it has one: a building or storey
 * in the path says yes. Without that, the explicit flag, then the class and the words road, sewer and the like.
 */
export function isBuildingContext(i: ClassifyInput): boolean {
  const h = i.hierarchy;
  if (h) {
    if (h.path.some((n) => n.ifcClass === 'IfcBuilding' || n.ifcClass === 'IfcBuildingStorey')) return true;
    if (h.buildingContext !== undefined) return h.buildingContext;
    if (h.path.some((n) => INFRA_CLASSES.has(n.ifcClass))) return false;
  }
  if (INFRA_CLASSES.has(i.ifcClass)) return false;
  return !/\b(road|highway|street|kerb|curb|railway|culvert|sewer|manhole)\b/.test(hayOf(i));
}

// ---- process context
// A process facility (refinery, chemical plant, power block) reads differently from a building: its steam, condensate and cooling
// water piping is utility piping (PIP/UTL, schema: "air, steam, water and nitrogen"), its pumps, vessels and exchangers are process
// equipment (PIP, schema: "process pumps and compressors, heat exchangers, vessels"), and its instruments belong to division 40
// ("instrumentation and control of process systems"). In a building the same words mean HVAC and plumbing (MEC/HYD, PLB). The context
// is decided for the whole model, conservatively: it needs two different kinds of evidence, on at least three elements.

/** Services that only a process facility has (a building has no flare or crude line). Utility words are NOT in here: a hospital has steam too. */
const PROCESS_SERVICE = /\bprocess\b|\bflare\b|crude|hydrocarbon|slurry|solvent|chemical|blowdown|\binstrument air\b|\bplant air\b|\bfuel gas\b|\bnitrogen\b/;
/** Utility services of a plant, read as utility piping once the context is process. */
const UTILITY_SERVICE = /steam|condensate|cooling water|boiler feed|utility (air|water)|service water|\bn2\b/;
/** ISA-style line number: size, service code, sequence (150-CW-1203-A1A). */
const LINE_NUMBER = /\b\d{1,4}-[A-Z]{1,4}-\d{3,5}(-[A-Z0-9]{1,6})?\b/;

const propText = (i: ClassifyInput, names: string[]): string => {
  for (const n of names) {
    const v = prop(i, n);
    if (typeof v === 'string' && v.trim()) return v;
  }
  return '';
};

/** The line number of a pipe, valve or instrument: a LineNumber property, or an ISA-style number in its tag or name. */
export function lineNumberOf(i: ClassifyInput): string {
  const p = propText(i, ['LineNumber', 'Line Number', 'LineNo', 'Line No']);
  if (p) return p;
  const m = LINE_NUMBER.exec(`${i.psets['Attr']?.['Tag'] ?? ''} ${i.name}`);
  return m ? m[0] : '';
}

/** The service text of an element: its systems and a Service or Medium property. */
const serviceOf = (i: ClassifyInput): string => [...(i.systems ?? []), propText(i, ['Service']), propText(i, ['Medium'])].join(' | ').toLowerCase();

export type ProcessEvidence = 'line' | 'service' | 'equipment';

/** What one element says about a process context: a line number, a process service, or process equipment (a pressure vessel, a shell and tube exchanger). */
export function processEvidenceOf(i: ClassifyInput): ProcessEvidence[] {
  const out: ProcessEvidence[] = [];
  if (propText(i, ['LineNumber', 'Line Number', 'LineNo', 'Line No']) || LINE_NUMBER.test(`${i.psets['Attr']?.['Tag'] ?? ''}`)) out.push('line');
  if (PROCESS_SERVICE.test([...(i.systems ?? []), propText(i, ['Service'])].join(' | ').toLowerCase())) out.push('service');
  const pt = String(i.psets['Attr']?.['PredefinedType'] ?? '').toUpperCase();
  if ((i.ifcClass === 'IfcTank' && (pt === 'VESSEL' || pt === 'PRESSUREVESSEL')) || (i.ifcClass === 'IfcHeatExchanger' && pt === 'SHELLANDTUBE')) out.push('equipment');
  return out;
}

/** Does the model show a process context? From the evidence of all its elements: two kinds, three elements. */
export function isProcessModel(evidence: Iterable<readonly ProcessEvidence[]>): boolean {
  const kinds = new Set<ProcessEvidence>();
  let elements = 0;
  for (const e of evidence) {
    if (!e.length) continue;
    elements++;
    for (const k of e) kinds.add(k);
  }
  return kinds.size >= 2 && elements >= 3;
}

/**
 * Is this element in a process context? The model-level flag when buildInput set it; otherwise the element's own evidence: a line number
 * together with a process or utility service (a lone line number is not enough).
 */
export function isProcessContext(i: ClassifyInput): boolean {
  if (i.processContext !== undefined) return i.processContext;
  if (!lineNumberOf(i)) return false;
  const svc = serviceOf(i);
  return PROCESS_SERVICE.test(svc) || UTILITY_SERVICE.test(svc);
}

function prop(i: ClassifyInput, name: string): PsetValue | undefined {
  const want = name.toLowerCase();
  for (const set of Object.values(i.psets)) for (const [k, v] of Object.entries(set)) if (k.toLowerCase() === want) return v;
  return undefined;
}
const asBool = (v: PsetValue | undefined): boolean | undefined => (typeof v === 'boolean' ? v : typeof v === 'string' ? (/^(true|yes|1)$/i.test(v) ? true : /^(false|no|0)$/i.test(v) ? false : undefined) : undefined);

const hit = (discipline: string, subDiscipline: string | null, division: string | null, confidence: number, rationale: string, section: string | null = null): RuleHit => ({
  discipline, subDiscipline, division, section, confidence, rationale,
});

interface SystemHint {
  discipline: string;
  sub: string;
  division: string;
  section: string | null;
  why: string;
}

/** Discipline hint from system names and other text, for the classes that several disciplines share (pipes, pumps, valves, tanks). */
export function systemHint(hay: string, building: boolean, process = false): SystemHint | null {
  if (!building) {
    if (/sewer|storm|wastewater|waste water|drain|culvert|gully|rain/.test(hay)) return { discipline: 'CIV', sub: 'DRN', division: '33', section: null, why: 'site drainage name' };
    if (/water main|potable|water supply|hydrant|gas main|utility/.test(hay)) return { discipline: 'CIV', sub: 'UTL', division: '33', section: null, why: 'site utility name' };
  }
  if (/fire|sprinkler|standpipe|hose reel/.test(hay)) return { discipline: 'FPR', sub: 'SPR', division: '21', section: '21 13 13', why: 'fire or sprinkler system name' };
  if (process) {
    // In a process facility the process and utility services are piping (PIP), not HVAC or plumbing.
    if (PROCESS_SERVICE.test(hay) || /\bcompressed air\b/.test(hay)) return { discipline: 'PIP', sub: 'PRC', division: '40', section: null, why: 'process service name' };
    if (UTILITY_SERVICE.test(hay)) return { discipline: 'PIP', sub: 'UTL', division: '40', section: null, why: 'utility service name in a process facility' };
  }
  if (/chilled|\bchw|hydronic|heating|cooling|condenser|hvac|boiler|refrigerant|glycol|steam|\bhw[sr]\b/.test(hay)) return { discipline: 'MEC', sub: 'HYD', division: '23', section: '23 21 13', why: 'heating or cooling system name' };
  if (/process|chemical|crude|hydrocarbon|flare|slurry|solvent|compressed air/.test(hay)) return { discipline: 'PIP', sub: 'PRC', division: '40', section: null, why: 'process system name' };
  if (/storm|rain/.test(hay)) return { discipline: 'PLB', sub: 'STM', division: '22', section: '22 14 00', why: 'storm drainage name' };
  if (/sanitary|waste|drain|vent|sewage|soil/.test(hay)) return { discipline: 'PLB', sub: 'DRN', division: '22', section: '22 13 16', why: 'drainage system name' };
  if (/domestic|potable|cold water|hot water|\bdhw\b|plumbing|water/.test(hay)) return { discipline: 'PLB', sub: 'SUP', division: '22', section: '22 11 16', why: 'water system name' };
  return null;
}

const MATERIAL_DIVISION: Array<[RegExp, string, string]> = [
  [/concrete|beton|cast.in/, '03', 'concrete'],
  [/masonry|brick|block|cmu|stone|mauerwerk/, '04', 'masonry'],
  [/steel|metal|aluminium|aluminum|stahl/, '05', 'metal'],
  [/wood|timber|holz|lumber/, '06', 'wood'],
  [/glass|glas/, '08', 'glass'],
  [/insulation|d.mm/, '07', 'insulation'],
  [/gypsum|drywall|plaster|putz|stud/, '09', 'gypsum or plaster'],
];

function materialDivision(hay: string): { division: string; why: string } | null {
  for (const [re, division, why] of MATERIAL_DIVISION) if (re.test(hay)) return { division, why };
  return null;
}

type Ctx = { i: ClassifyInput; hay: string; building: boolean; process: boolean };
type ClassRule = (c: Ctx) => RuleHit | null;
const fixed = (d: string, s: string | null, div: string | null, conf: number, why: string, section: string | null = null): ClassRule => () => hit(d, s, div, conf, why, section);

// ---- civil and site works
// A site item (paving, kerbs, fences, trench drains, ...) is recognised by its names, not by its class alone: the IFC has
// no class for most of them (paving is an IfcSlab, a kerb an IfcBuildingElementProxy). Only the classes in CIVIL_CLASSES are
// tested, so a pipe, valve or duct never takes a civil name (a pipe named "drain" stays PIP or PLB).

/** Text that names an item: the name, the type name, ObjectType, Description, Tag and PredefinedType. Pset names and systems are left out. */
export function civilTextOf(i: ClassifyInput): string {
  const parts: string[] = [i.name, i.type?.name ?? ''];
  for (const k of ['ObjectType', 'Description', 'Tag', 'PredefinedType']) {
    const v = i.psets['Attr']?.[k];
    if (typeof v === 'string') parts.push(v);
  }
  return parts.join(' | ').toLowerCase();
}

interface CivilName {
  re: RegExp;
  sub: string;
  division: string;
  section: string;
  why: string;
}

/** Site items by name. The first match wins, so the more specific words come first. */
const CIVIL_NAMES: CivilName[] = [
  { re: /drain(age)? trench|trench drain|drain(age)? channel|channel drain|\bgully|catch ?basin/, sub: 'DRN', division: '33', section: '33 44 00', why: 'site drain trench, channel, gully or catch basin' },
  { re: /\bculvert/, sub: 'DRN', division: '33', section: '33 41 00', why: 'culvert' },
  { re: /\bmanholes?\b|inspection chamber/, sub: 'DRN', division: '33', section: '33 39 00', why: 'manhole or inspection chamber' },
  { re: /\bkerbs?\b|\bcurbs?\b/, sub: 'PAV', division: '32', section: '32 16 13', why: 'kerb or curb' },
  { re: /paving|pavement|hardstanding|\bapron\b|\broads?\b|highway|\bstreet\b|car park/, sub: 'PAV', division: '32', section: '32 13 00', why: 'paving, pavement, hardstanding or road' },
  { re: /retaining wall/, sub: 'ERT', division: '32', section: '32 32 00', why: 'retaining wall' },
  { re: /\bbund\b|earthworks?|excavat|\bgrading\b/, sub: 'ERT', division: '31', section: '31 23 00', why: 'earthwork, excavation, grading or bund' },
  { re: /\bfenc(e|es|ing)\b|\b(site|vehicle|entrance|security|perimeter|pedestrian) gate\b/, sub: 'LND', division: '32', section: '32 31 00', why: 'fence or site gate' },
];

/** The classes that can carry a site item in the IFC. Flow, pipe, duct, cable and valve classes are never tested. */
const CIVIL_CLASSES = new Set([
  'IfcBuildingElementProxy', 'IfcElementAssembly', 'IfcDiscreteAccessory', 'IfcRailing', 'IfcWall', 'IfcWallStandardCase', 'IfcSlab',
  'IfcPlate', 'IfcMember', 'IfcGeographicElement', 'IfcCivilElement',
]);

/** The civil rule that a name gives, or null. */
export function civilByName(i: ClassifyInput): RuleHit | null {
  const t = civilTextOf(i);
  for (const n of CIVIL_NAMES) if (n.re.test(t)) return hit('CIV', n.sub, n.division, 0.88, `${n.why}, by name`, n.section);
  return null;
}

/** For a class that can also be a site item: a civil name decides first, the class rule is the fallback. */
const civilFirst = (rule: ClassRule): ClassRule => (c) => (CIVIL_CLASSES.has(c.i.ifcClass) ? civilByName(c.i) : null) ?? rule(c);

/** Equipment foundations and plinths, by name or ObjectType. A building footing does not match these words. */
const EQUIPMENT_FOUNDATION = /equipment (foundation|base|pad|plinth)|(pump|skid|machine|vessel|tank|exchanger|compressor) (base|foundation|plinth|pad)|\bplinth\b|\bpad under\b|\bpad for (equipment|pump|vessel|tank|compressor)\b/;

/**
 * A footing is structural (a building footing), unless its name or ObjectType says equipment foundation, or it is in the
 * site and not in a building storey: then it is a civil foundation (CIV FND).
 */
const footing: ClassRule = (c) => {
  if (EQUIPMENT_FOUNDATION.test(civilTextOf(c.i))) return hit('CIV', 'FND', '03', 0.9, 'equipment foundation, by name', '03 30 00');
  const path = c.i.hierarchy?.path ?? [];
  if (path.some((n) => n.ifcClass === 'IfcSite') && !path.some((n) => n.ifcClass === 'IfcBuildingStorey')) {
    return hit('CIV', 'FND', '03', 0.88, 'footing in the site, not in a building storey', '03 30 00');
  }
  return hit('STR', 'FND', '03', 0.95, 'IfcFooting is a foundation', '03 30 00');
};

/** For classes that several disciplines share: the system hint decides; without one the rule is weak and the model decides. */
const shared = (kind: 'pipe' | 'pump' | 'valve' | 'tank', weak: RuleHit): ClassRule => (c) => {
  // In a process context the Service and Medium properties count as system names, and a pump or tank is process equipment unless a fire or plumbing name says otherwise.
  const text = c.process ? `${c.hay} | ${serviceOf(c.i)}` : c.hay;
  let h = systemHint(text, c.building, c.process);
  if (c.process && (kind === 'pump' || kind === 'tank') && (!h || h.discipline === 'MEC' || h.discipline === 'CIV')) {
    return hit('PIP', kind === 'pump' ? 'PMP' : 'VES', '43', 0.88, `${kind === 'pump' ? 'pump' : 'tank or vessel'} in a process facility`);
  }
  if (c.process && !h && lineNumberOf(c.i)) h = { discipline: 'PIP', sub: 'PRC', division: '40', section: null, why: 'line number in a process facility' };
  if (!h) return weak;
  const named = (c.i.systems ?? []).some((s) => systemHint(s.toLowerCase(), c.building, c.process));
  const conf = named ? 0.92 : 0.86;
  const why = `${kind}, ${h.why}`;
  if (h.discipline === 'CIV') return hit('CIV', h.sub, null, conf, why);
  if (h.discipline === 'PIP') {
    if (kind === 'pump') return hit('PIP', 'PMP', '43', conf, why);
    if (kind === 'tank') return hit('PIP', 'VES', '43', conf, why);
    // A regulating valve is a control valve (schema: INS/CTL "controllers, actuators and control valves").
    if (kind === 'valve' && c.process && String(c.i.psets['Attr']?.['PredefinedType'] ?? '').toUpperCase() === 'REGULATING') return hit('INS', 'CTL', '40', conf, 'regulating valve, a control valve in a process facility');
    return hit('PIP', kind === 'valve' ? 'VLV' : h.sub, '40', conf, why);
  }
  return hit(h.discipline, kind === 'pipe' ? h.sub : 'EQP', h.division, conf, why, kind === 'pipe' ? h.section : null);
};

// ---- supports and equipment parts
// A member that says it is a pipe support (post, guide, sleeper, shoe, hanger) is PIP/SUP (schema: "pipe supports, hangers and guides"), and
// a member that says it supports a cable tray goes with the tray (ELE/CND). The class is no evidence: IfcMember is also a brace.

const TRAY_SUPPORT = /\b(cable )?(tray|ladder|trunking|basket)[- ](t[- ])?(support|hanger|bracket|stanchion|riser|trapeze|cantilever|post)|\bcable tray support/;
const PIPE_SUPPORT = /\bpipe[- ](t[- ])?(support|sleeper|hanger|shoe|guide|anchor|rack support|clamp)|\bpipe hangers?\b|\bsleepers?\b|\briser guide|\bline guide|\bpipe supports?\b/;
const SUPPORT_CLASSES = new Set(['IfcMember', 'IfcBuildingElementProxy', 'IfcDiscreteAccessory', 'IfcPlate', 'IfcElementAssembly', 'IfcMechanicalFastener', 'IfcBeam', 'IfcColumn']);

/** The support rule of an element that names itself a pipe or cable tray support, or null. */
export function supportByName(c: Ctx): RuleHit | null {
  if (!SUPPORT_CLASSES.has(c.i.ifcClass)) return null;
  const t = civilTextOf(c.i);
  if (TRAY_SUPPORT.test(t)) return hit('ELE', 'CND', '26', 0.9, 'support of a cable tray, by name', '26 05 29');
  if (PIPE_SUPPORT.test(t)) {
    const div = c.process ? '40' : /water|plumbing|sanitary|drain/.test(c.hay) ? '22' : /hvac|chilled|heating|hydronic/.test(c.hay) ? '23' : '05';
    return hit('PIP', 'SUP', div, 0.9, 'pipe support, guide or sleeper, by name');
  }
  return null;
}
const supportFirst = (rule: ClassRule): ClassRule => (c) => supportByName(c) ?? rule(c);

/** Parts of process equipment (baseplate, skirt, saddle, channel, bundle) in a process facility, by name or type. They follow the equipment they belong to. */
const EQUIPMENT_PART = /\b(pump|compressor|motor)[ -]*(baseplate|bedplate|skid|casing|coupling)|\b(exchanger|cooler|condenser|reboiler)[ -]*(channel|saddle|shell|bundle|head|support)|\b(vessel|drum|column|tower|tank)[ -]*(skirt|saddle|leg|support ring|manway)/;
const equipmentPart: ClassRule = (c) => {
  if (!c.process) return null;
  const t = civilTextOf(c.i);
  const m = EQUIPMENT_PART.exec(t);
  if (!m) return null;
  if (/pump|compressor|motor/.test(m[0])) return hit('PIP', 'PMP', '43', 0.86, 'part of a pump or compressor, in a process facility');
  if (/exchanger|cooler|condenser|reboiler/.test(m[0])) return hit('PIP', 'HTX', '42', 0.86, 'part of a heat exchanger, in a process facility');
  if (/vessel|drum|column|tower|tank/.test(m[0])) return hit('PIP', 'VES', '43', 0.86, 'part of a vessel, in a process facility');
  return null;
};

const wall: ClassRule = (c) => {
  const lb = asBool(prop(c.i, 'LoadBearing'));
  const m = materialDivision(c.hay);
  // A load-bearing masonry wall is structural but its work belongs to masonry (division 04), not concrete.
  if (lb === true && m?.division === '04') return hit('STR', 'WLS', '04', 0.88, 'wall with LoadBearing=true, masonry material');
  if (lb === true) return hit('STR', 'WLS', '03', 0.88, 'wall with LoadBearing=true', '03 30 00');
  const base = m ? 0.9 : 0.86;
  return hit('ARC', 'WAL', m?.division ?? '09', base, `wall${lb === false ? ' with LoadBearing=false' : ''}${m ? `, ${m.why} material` : ''}`);
};

const slab: ClassRule = (c) => {
  const lb = asBool(prop(c.i, 'LoadBearing'));
  const steel = /steel deck|metal deck|grating|checker(ed)? plate/.test(c.hay);
  if (lb === false) return hit('ARC', 'FIN', '09', 0.7, 'slab with LoadBearing=false');
  // a base slab outside a building is site paving; a building ground slab stays structural
  if (String(c.i.psets['Attr']?.['PredefinedType'] ?? '').toUpperCase() === 'BASESLAB' && !c.building) {
    return hit('CIV', 'PAV', '32', 0.88, 'base slab outside a building (site paving)', '32 13 00');
  }
  return hit('STR', 'SLB', steel ? '05' : '03', lb === true ? 0.92 : 0.88, `slab${lb === true ? ' with LoadBearing=true' : ''}`, steel ? '05 31 00' : '03 30 00');
};

/** Words of bracing and connection parts (schema STR/BRC: "bracing, plates, connections and other structural members"). */
const BRACING_WORDS = /\b(brace|braces|bracing|strut|gusset|diagonal|splice plate|connection plate|base ?plate|cleat|stiffener)\b/;

const member: ClassRule = (c) => {
  if (/mullion|curtain|glazing|window|transom/.test(c.hay)) return hit('ARC', 'WIN', '08', 0.86, 'member named as a glazing part', '08 44 00');
  const m = materialDivision(c.hay);
  if (BRACING_WORDS.test(civilTextOf(c.i))) return hit('STR', 'BRC', m?.division === '06' ? '06' : m?.division === '03' ? '03' : '05', 0.9, 'member named as bracing or a connection part', '05 12 00');
  return hit('STR', 'BRC', m?.division === '06' ? '06' : m?.division === '03' ? '03' : '05', m ? 0.86 : 0.8, `structural member${m ? `, ${m.why}` : ''}`);
};

const covering: ClassRule = (c) => {
  const pt = String(c.i.psets['Attr']?.['PredefinedType'] ?? '').toUpperCase();
  if (pt === 'CEILING') return hit('ARC', 'FIN', '09', 0.9, 'covering, ceiling', '09 51 00');
  if (pt === 'FLOORING') return hit('ARC', 'FIN', '09', 0.9, 'covering, flooring', '09 60 00');
  if (pt === 'CLADDING' || pt === 'ROOFING' || pt === 'INSULATION' || pt === 'MEMBRANE') return hit('ARC', 'ROF', '07', 0.88, `covering, ${pt.toLowerCase()}`);
  return hit('ARC', 'FIN', '09', 0.86, 'covering');
};

const NAME_KEYWORDS: Array<[RegExp, RuleHit]> = [
  [/beam|column|footing|pile|foundation|girder/, hit('STR', null, null, 0.7, 'name suggests a structural part')],
  [/duct|diffuser|\bahu\b|\bvav\b|fan coil|damper|grille/, hit('MEC', null, '23', 0.7, 'name suggests an HVAC part')],
  [/sprinkler|standpipe/, hit('FPR', 'SPR', '21', 0.7, 'name suggests a fire protection part')],
  [/cable|conduit|luminaire|lighting|switchboard|panelboard|transformer|socket|outlet/, hit('ELE', null, '26', 0.7, 'name suggests an electrical part')],
  [/door|window|partition|ceiling|stair|railing|curtain/, hit('ARC', null, null, 0.7, 'name suggests an architectural part')],
  [/pipe|drain|toilet|sink|basin|faucet|tap|urinal/, hit('PLB', null, '22', 0.7, 'name suggests a plumbing part')],
];

const nameRule: ClassRule = (c) => {
  for (const [re, h] of NAME_KEYWORDS) if (re.test(c.hay)) return { ...h };
  return null;
};

const weakPlumbing = hit('PLB', 'SUP', '22', 0.55, 'pipe without a system hint', '22 11 16');

/** The IFC class map. */
export const CLASS_RULES: Record<string, ClassRule> = {
  // structure
  IfcBeam: supportFirst(fixed('STR', 'BEM', '05', 0.93, 'IfcBeam is a structural member', '05 12 00')),
  IfcColumn: supportFirst(fixed('STR', 'COL', '05', 0.93, 'IfcColumn is a structural member', '05 12 00')),
  IfcFooting: footing,
  IfcPile: fixed('STR', 'FND', '31', 0.95, 'IfcPile is a foundation', '31 60 00'),
  IfcReinforcingBar: fixed('STR', 'REB', '03', 0.95, 'reinforcement', '03 20 00'),
  IfcReinforcingMesh: fixed('STR', 'REB', '03', 0.95, 'reinforcement', '03 20 00'),
  IfcTendon: fixed('STR', 'REB', '03', 0.9, 'tendon', '03 38 00'),
  IfcMember: supportFirst(civilFirst(member)),
  IfcSlab: civilFirst(slab),
  IfcWall: civilFirst(wall),
  IfcWallStandardCase: civilFirst(wall),
  IfcPlate: supportFirst(civilFirst((c) => (BRACING_WORDS.test(civilTextOf(c.i)) ? hit('STR', 'BRC', '05', 0.9, 'plate named as a connection part') : hit('STR', 'BRC', '05', 0.6, 'plate, structural or architectural')))),
  // architecture
  IfcDoor: fixed('ARC', 'DOR', '08', 0.95, 'IfcDoor', '08 10 00'),
  IfcWindow: fixed('ARC', 'WIN', '08', 0.95, 'IfcWindow', '08 50 00'),
  IfcCurtainWall: fixed('ARC', 'WIN', '08', 0.93, 'IfcCurtainWall', '08 44 00'),
  IfcStair: fixed('ARC', 'STA', '05', 0.9, 'IfcStair', '05 51 00'),
  IfcStairFlight: fixed('ARC', 'STA', '05', 0.9, 'IfcStairFlight', '05 51 00'),
  IfcRamp: fixed('ARC', 'STA', '03', 0.86, 'IfcRamp'),
  IfcRampFlight: fixed('ARC', 'STA', '03', 0.86, 'IfcRampFlight'),
  IfcRailing: civilFirst(fixed('ARC', 'STA', '05', 0.9, 'IfcRailing', '05 52 00')),
  IfcRoof: fixed('ARC', 'ROF', '07', 0.9, 'IfcRoof'),
  IfcCovering: covering,
  IfcChimney: fixed('ARC', 'WAL', '04', 0.86, 'IfcChimney'),
  IfcFurniture: fixed('ARC', 'FUR', '12', 0.93, 'IfcFurniture', '12 50 00'),
  IfcFurnishingElement: fixed('ARC', 'FUR', '12', 0.9, 'IfcFurnishingElement'),
  IfcSystemFurnitureElement: fixed('ARC', 'FUR', '12', 0.9, 'IfcSystemFurnitureElement'),
  IfcTransportElement: fixed('ARC', null, '14', 0.86, 'IfcTransportElement is conveying equipment', '14 20 00'),
  IfcShadingDevice: fixed('ARC', 'WIN', '08', 0.8, 'IfcShadingDevice'),
  // HVAC
  IfcDuctSegment: fixed('MEC', 'DUC', '23', 0.95, 'IfcDuctSegment is ductwork', '23 31 13'),
  IfcDuctFitting: fixed('MEC', 'DUC', '23', 0.95, 'IfcDuctFitting is ductwork', '23 31 13'),
  IfcDuctSilencer: fixed('MEC', 'ACC', '23', 0.92, 'IfcDuctSilencer', '23 33 00'),
  IfcDamper: fixed('MEC', 'ACC', '23', 0.92, 'IfcDamper', '23 33 00'),
  IfcAirTerminal: fixed('MEC', 'TRM', '23', 0.95, 'IfcAirTerminal', '23 37 13'),
  IfcAirTerminalBox: fixed('MEC', 'TRM', '23', 0.93, 'IfcAirTerminalBox', '23 36 00'),
  IfcFan: fixed('MEC', 'EQP', '23', 0.93, 'IfcFan', '23 34 00'),
  IfcAirToAirHeatRecovery: fixed('MEC', 'EQP', '23', 0.93, 'heat recovery unit', '23 72 00'),
  IfcUnitaryEquipment: fixed('MEC', 'EQP', '23', 0.9, 'IfcUnitaryEquipment'),
  IfcBoiler: fixed('MEC', 'EQP', '23', 0.93, 'IfcBoiler', '23 52 00'),
  IfcChiller: fixed('MEC', 'EQP', '23', 0.93, 'IfcChiller', '23 64 00'),
  IfcCoolingTower: fixed('MEC', 'EQP', '23', 0.93, 'IfcCoolingTower', '23 65 00'),
  IfcCoil: fixed('MEC', 'EQP', '23', 0.9, 'IfcCoil', '23 82 16'),
  IfcSpaceHeater: fixed('MEC', 'EQP', '23', 0.92, 'IfcSpaceHeater', '23 82 00'),
  IfcHumidifier: fixed('MEC', 'EQP', '23', 0.9, 'IfcHumidifier', '23 84 00'),
  IfcEvaporator: fixed('MEC', 'EQP', '23', 0.9, 'IfcEvaporator'),
  IfcCondenser: fixed('MEC', 'EQP', '23', 0.9, 'IfcCondenser'),
  IfcCompressor: (c) => (c.process || systemHint(c.hay, c.building)?.discipline === 'PIP' ? hit('PIP', 'PMP', '43', 0.86, 'compressor, process system') : hit('MEC', 'EQP', '23', 0.7, 'compressor')),
  IfcHeatExchanger: (c) => (c.process || systemHint(c.hay, c.building)?.discipline === 'PIP' ? hit('PIP', 'HTX', '42', 0.88, 'heat exchanger, process system') : hit('MEC', 'EQP', '23', 0.75, 'heat exchanger')),
  // pipes and plumbing
  IfcPipeSegment: shared('pipe', weakPlumbing),
  IfcPipeFitting: shared('pipe', weakPlumbing),
  IfcPump: shared('pump', hit('MEC', 'EQP', '23', 0.45, 'pump without a system hint')),
  IfcValve: shared('valve', hit('PLB', 'EQP', '22', 0.4, 'valve without a system hint')),
  IfcTank: shared('tank', hit('PLB', 'EQP', '22', 0.4, 'tank without a system hint')),
  IfcSanitaryTerminal: fixed('PLB', 'FIX', '22', 0.95, 'IfcSanitaryTerminal', '22 40 00'),
  IfcWasteTerminal: fixed('PLB', 'DRN', '22', 0.92, 'IfcWasteTerminal', '22 13 00'),
  IfcStackTerminal: fixed('PLB', 'DRN', '22', 0.92, 'IfcStackTerminal', '22 13 00'),
  IfcInterceptor: fixed('PLB', 'DRN', '22', 0.88, 'IfcInterceptor'),
  IfcFireSuppressionTerminal: fixed('FPR', 'SPR', '21', 0.95, 'IfcFireSuppressionTerminal', '21 13 13'),
  IfcDistributionChamberElement: (c) => (c.building ? hit('PLB', 'DRN', '22', 0.7, 'chamber in a building') : hit('CIV', 'DRN', null, 0.88, 'chamber on a site')),
  // electrical
  IfcCableCarrierSegment: fixed('ELE', 'CND', '26', 0.95, 'IfcCableCarrierSegment', '26 05 36'),
  IfcCableCarrierFitting: fixed('ELE', 'CND', '26', 0.95, 'IfcCableCarrierFitting', '26 05 36'),
  IfcCableSegment: fixed('ELE', 'WIR', '26', 0.93, 'IfcCableSegment', '26 05 19'),
  IfcCableFitting: fixed('ELE', 'WIR', '26', 0.9, 'IfcCableFitting'),
  IfcJunctionBox: fixed('ELE', 'WIR', '26', 0.9, 'IfcJunctionBox', '26 05 33'),
  IfcElectricDistributionBoard: fixed('ELE', 'PWR', '26', 0.95, 'IfcElectricDistributionBoard', '26 24 16'),
  IfcTransformer: fixed('ELE', 'PWR', '26', 0.95, 'IfcTransformer', '26 22 00'),
  IfcProtectiveDevice: fixed('ELE', 'PWR', '26', 0.9, 'IfcProtectiveDevice', '26 28 00'),
  IfcSwitchingDevice: fixed('ELE', 'DEV', '26', 0.9, 'IfcSwitchingDevice', '26 27 26'),
  IfcOutlet: fixed('ELE', 'DEV', '26', 0.88, 'IfcOutlet', '26 27 26'),
  IfcLamp: fixed('ELE', 'LTG', '26', 0.95, 'IfcLamp', '26 51 00'),
  IfcLightFixture: fixed('ELE', 'LTG', '26', 0.95, 'IfcLightFixture', '26 51 00'),
  IfcElectricGenerator: fixed('ELE', 'GEN', '26', 0.93, 'IfcElectricGenerator', '26 32 13'),
  IfcElectricFlowStorageDevice: fixed('ELE', 'GEN', '26', 0.9, 'IfcElectricFlowStorageDevice', '26 33 00'),
  IfcMotorConnection: fixed('ELE', 'PWR', '26', 0.85, 'IfcMotorConnection'),
  // A motor that names the equipment it drives, in a process facility, is part of that pump or compressor.
  IfcElectricMotor: (c) => (c.process && propText(c.i, ['Driver', 'DrivenEquipment', 'Driven Equipment', 'Driven']) ? hit('PIP', 'PMP', '43', 0.86, 'motor of a driven process machine') : hit('ELE', 'PWR', '26', 0.7, 'IfcElectricMotor')),
  IfcElectricAppliance: fixed('ELE', 'DEV', '26', 0.7, 'IfcElectricAppliance'),
  IfcSolarDevice: fixed('ELE', 'GEN', '48', 0.88, 'IfcSolarDevice'),
  // low voltage, controls
  IfcCommunicationsAppliance: fixed('TEL', 'DAT', '27', 0.92, 'IfcCommunicationsAppliance', '27 10 00'),
  IfcAudioVisualAppliance: fixed('TEL', 'AVS', '27', 0.92, 'IfcAudioVisualAppliance', '27 41 00'),
  IfcAlarm: fixed('TEL', 'ALM', '28', 0.9, 'IfcAlarm', '28 31 00'),
  IfcSensor: (c) => (/smoke|fire|heat detector/.test(c.hay) ? hit('TEL', 'ALM', '28', 0.9, 'detector', '28 31 00') : c.process ? hit('INS', 'SNS', '40', 0.86, 'sensor on a process line') : hit('INS', 'SNS', '25', 0.65, 'sensor')),
  IfcActuator: (c) => hit('INS', 'CTL', c.process ? '40' : '25', 0.88, 'IfcActuator'),
  IfcController: fixed('INS', 'CTL', '25', 0.9, 'IfcController'),
  IfcUnitaryControlElement: fixed('INS', 'CTL', '25', 0.88, 'IfcUnitaryControlElement'),
  IfcFlowMeter: (c) => (c.process ? hit('INS', 'SNS', '40', 0.86, 'flow meter on a process line') : hit('INS', 'SNS', '25', 0.65, 'IfcFlowMeter')),
  // site
  IfcCivilElement: civilFirst(fixed('CIV', null, null, 0.88, 'IfcCivilElement')),
  IfcAlignment: fixed('CIV', 'PAV', null, 0.9, 'IfcAlignment, a road or rail line'),
  IfcRoad: fixed('CIV', 'PAV', '32', 0.95, 'IfcRoad', '32 13 00'),
  IfcRoadPart: fixed('CIV', 'PAV', '32', 0.95, 'IfcRoadPart', '32 13 00'),
  IfcPavement: fixed('CIV', 'PAV', '32', 0.95, 'IfcPavement', '32 13 00'),
  IfcKerb: fixed('CIV', 'PAV', '32', 0.95, 'IfcKerb', '32 16 13'),
  IfcCourse: fixed('CIV', 'PAV', '32', 0.93, 'IfcCourse, a pavement layer', '32 11 00'),
  IfcEarthworksElement: fixed('CIV', 'ERT', '31', 0.95, 'earthworks', '31 23 00'),
  IfcEarthworksFill: fixed('CIV', 'ERT', '31', 0.95, 'earthworks', '31 23 00'),
  IfcEarthworksCut: fixed('CIV', 'ERT', '31', 0.95, 'earthworks', '31 23 00'),
  IfcGeotechnicalElement: fixed('CIV', 'ERT', null, 0.9, 'geotechnical element'),
  IfcGeographicElement: civilFirst(fixed('CIV', 'LND', null, 0.9, 'IfcGeographicElement')),
  IfcRailway: fixed('CIV', 'PAV', null, 0.9, 'IfcRailway'),
  IfcTrackElement: fixed('CIV', 'PAV', null, 0.9, 'IfcTrackElement'),
  IfcBridge: fixed('STR', null, null, 0.86, 'IfcBridge'),
  // generic classes: only the name can say
  IfcBuildingElementProxy: supportFirst((c) => equipmentPart(c) ?? civilFirst(nameRule)(c)),
  IfcDistributionElement: nameRule,
  IfcFlowSegment: nameRule,
  IfcFlowFitting: nameRule,
  IfcFlowTerminal: nameRule,
  IfcFlowController: nameRule,
  IfcFlowMovingDevice: nameRule,
  IfcFlowStorageDevice: nameRule,
  IfcFlowTreatmentDevice: nameRule,
  IfcEnergyConversionDevice: nameRule,
  IfcDiscreteAccessory: supportFirst(civilFirst(nameRule)),
  IfcMechanicalFastener: supportFirst(nameRule),
  IfcElementAssembly: supportFirst(civilFirst(nameRule)),
};

/** The rule result for an element, in rules keys (the codes of the default schema), or null when no rule applies. */
export function classByRules(i: ClassifyInput): RuleHit | null {
  const rule = CLASS_RULES[i.ifcClass];
  if (!rule) return null;
  return rule({ i, hay: hayOf(i), building: isBuildingContext(i), process: isProcessContext(i) });
}

/**
 * Map a rule onto the schema in use. Null when the schema has no matching discipline. A division that the schema lacks
 * is dropped (the discipline stays). Outside a building context the division is null, when the schema says so.
 */
export function resolveRule(hit: RuleHit, schema: ClassificationSchema, buildingContext: boolean): Decision | null {
  const d = findDiscipline(schema, hit.discipline);
  if (!d) return null;
  const sub = hit.subDiscipline ? findSub(d, hit.subDiscipline) : undefined;
  let division = hit.division && divisionTitle(schema, hit.division) ? hit.division : null;
  if (masterformatBuildingOnly(schema) && !buildingContext) division = null;
  const section = division && hit.section && hit.section.startsWith(division) ? hit.section : null;
  return { discipline: d.code, subDiscipline: sub?.code ?? null, division, section, confidence: hit.confidence, rationale: hit.rationale };
}
