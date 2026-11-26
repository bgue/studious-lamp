// XR_ConcreteSpec: strength class, exposure class, standard, cover and fire resistance. Read from IFC first, parsed from names and
// material text second, looked up in the project's cover table last. Exposure is only ever suggested (never final). Pure.
// Property names verified against the IFC4 (ADD2) property set templates in ifcopenshell and the IFC2x3 ones:
//   Pset_ConcreteElementGeneral (IFC4): ConstructionMethod, StructuralClass, StrengthClass, ExposureClass, ReinforcementVolumeRatio,
//     ReinforcementAreaRatio, DimensionalAccuracyClass, ConstructionToleranceClass, ConcreteCover, ConcreteCoverAtMainBars,
//     ConcreteCoverAtLinks, ReinforcementStrengthClass.
//   Pset_ConcreteElementGeneral (IFC2x3): StructuralClass, EnvironmentalClass, FireRating, ServiceLife, ..., ConstructionType,
//     ConcreteCoverAtMainBars, ConcreteCoverAtLinks.
//   Pset_PrecastConcreteElementGeneral / Fabrication (IFC4): TypeDesignator, ProductionLotId, SerialNumber, PieceMark, ...
// The design document lists CastingMethod and AssemblyPlace; neither exists in IFC4 (ConstructionMethod is the one), so they are not read.

import type { ClassifyInput } from '../types';
import { propOf } from '../facets/facetRules';
import { nameText } from './rules';
import coverJson from '../../../public/classification/concrete-cover.json';

export type Standard = 'EN206' | 'ACI318';

export interface ParsedStrength {
  /** `C30/37`, `4000 psi`, `32 MPa`. */
  text: string;
  unit: '' | 'psi' | 'ksi' | 'MPa';
  standard: Standard | null;
  /** The text as found. */
  raw: string;
}

/** DIN 1045 (1988) classes B and their EN 206 equivalents. */
const B_TO_C: Record<number, string> = { 5: 'C4/5', 10: 'C8/10', 15: 'C12/15', 25: 'C20/25', 35: 'C25/30', 45: 'C35/45', 55: 'C45/55' };

/** Parse a strength class from text: C30/37, LC25/28, C30, B35, 4000 psi, f'c = 5 ksi, 32 MPa. Null when none is found. */
export function parseStrength(text: string, defaultStandard: Standard = 'EN206'): ParsedStrength | null {
  const s = text.replace(/[’`´]/g, "'");
  let m = /\b(LC|C)\s?(\d{1,3})\s?[/-]\s?(\d{2,3})\b/i.exec(s);
  if (m) return { text: `${m[1]!.toUpperCase()}${m[2]}/${m[3]}`, unit: '', standard: 'EN206', raw: m[0] };
  m = /f'?\s?c'?\s*[=:]?\s*(\d[\d,]*(?:\.\d+)?)\s*(psi|ksi|mpa)?/i.exec(s);
  if (m) {
    const n = Number(m[1]!.replace(/,/g, ''));
    let unit = (m[2] ?? '').toLowerCase();
    if (!unit) unit = n >= 1000 ? 'psi' : n <= 20 ? 'ksi' : 'mpa';
    if (Number.isFinite(n) && n > 0) return norm(n, unit, 'ACI318', m[0]);
  }
  m = /(\d[\d,]*(?:\.\d+)?)\s*(psi|ksi)\b/i.exec(s);
  if (m) { const n = Number(m[1]!.replace(/,/g, '')); if (n > 0) return norm(n, m[2]!.toLowerCase(), 'ACI318', m[0]); }
  m = /\b(\d{2}(?:\.\d+)?)\s?mpa\b/i.exec(s);
  if (m) return norm(Number(m[1]), 'mpa', defaultStandard, m[0]);
  m = /\bC\s?(\d{2,3})\b(?!\s?[/-]\s?\d)/.exec(s);
  if (m && Number(m[1]) >= 8 && Number(m[1]) <= 120) return { text: `C${m[1]}`, unit: '', standard: 'EN206', raw: m[0] };
  m = /\bB\s?(\d{1,2})\b/.exec(s);
  if (m && B_TO_C[Number(m[1])]) return { text: B_TO_C[Number(m[1])]!, unit: '', standard: 'EN206', raw: m[0] };
  return null;
}

function norm(n: number, unit: string, standard: Standard, raw: string): ParsedStrength {
  const u = unit === 'mpa' ? 'MPa' : unit === 'ksi' ? 'ksi' : 'psi';
  const num = Number.isInteger(n) ? String(n) : String(Math.round(n * 100) / 100);
  return { text: `${num} ${u}`, unit: u, standard, raw };
}

const EN_ORDER = ['X0', 'XC', 'XD', 'XS', 'XF', 'XA'];
const EN_TOKEN = /\b(X0|XC[1-4]|XD[1-3]|XS[1-3]|XF[1-4]|XA[1-3])\b/gi;
const ACI_TOKEN = /^(F[0-3]|S[0-3]|W[0-2]|C[0-2])$/;

/** Exposure classes from text. `property` is the text of an IFC exposure property (ACI categories F/S/W/C are accepted there only). Normalised, comma separated. */
export function parseExposure(text: string, property = false): { classes: string; standard: Standard } | null {
  const en = [...new Set([...text.toUpperCase().matchAll(EN_TOKEN)].map((m) => m[1]!))];
  if (en.length) {
    en.sort((a, b) => EN_ORDER.indexOf(a.slice(0, 2)) - EN_ORDER.indexOf(b.slice(0, 2)) || a.localeCompare(b));
    return { classes: en.join(', '), standard: 'EN206' };
  }
  if (property) {
    const aci = [...new Set(text.toUpperCase().split(/[\s,;/+&]+/).filter((t) => ACI_TOKEN.test(t)))];
    if (aci.length) { aci.sort(); return { classes: aci.join(', '), standard: 'ACI318' }; }
  }
  return null;
}

/** An exposure suggestion from the placement and the level (never final): below ground XC2, outside or on the envelope XC4 and XF1, inside XC1. */
export function suggestExposure(placement: string | undefined, belowGround: boolean | undefined): { classes: string; why: string } | null {
  if (belowGround) return { classes: 'XC2', why: 'below the ground level' };
  if (placement === 'EXT' || placement === 'BOUNDARY') return { classes: 'XC4, XF1', why: `placement ${placement}` };
  if (placement === 'INT') return { classes: 'XC1', why: 'inside the building' };
  return null;
}

// ---------------------------------------------------------------- cover

export interface CoverTable {
  version: string;
  en: { exposure: Record<string, number>; roleMinimum: Record<string, number>; mainBarExtra: Record<string, number>; defaultExposure: string };
  aci: { ground: number; weather: number; interior: number; interiorSlabWall: number };
}

const isObj = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
const numMap = (v: unknown, into: Record<string, number>, errors: string[], path: string): void => {
  if (v === undefined) return;
  if (!isObj(v)) { errors.push(`"${path}" must be an object of numbers (mm).`); return; }
  for (const [k, x] of Object.entries(v)) {
    if (typeof x === 'number' && x >= 0 && x <= 300) into[k] = x;
    else errors.push(`"${path}.${k}" must be a cover in mm from 0 to 300.`);
  }
};

/** The default table: public/classification/concrete-cover.json. */
export const defaultCoverTable = (): CoverTable => parseCoverTable(coverJson, []);

/** Check a cover table (the shipped file or a project's own). Never throws; a bad entry is reported and the shipped value kept. */
export function parseCoverTable(v: unknown, errors: string[]): CoverTable {
  const base = isObj(coverJson) ? (coverJson as unknown as { en: CoverTable['en']; aci: CoverTable['aci'] }) : null;
  const t: CoverTable = {
    version: 'xr-concrete-cover/1',
    en: { exposure: { ...(base?.en.exposure ?? {}) }, roleMinimum: { ...(base?.en.roleMinimum ?? {}) }, mainBarExtra: { ...(base?.en.mainBarExtra ?? {}) }, defaultExposure: base?.en.defaultExposure ?? 'XC1' },
    aci: { ...(base?.aci ?? { ground: 75, weather: 50, interior: 40, interiorSlabWall: 20 }) },
  };
  if (v === coverJson) return t;
  if (!isObj(v)) { errors.push('The cover table must be an object.'); return t; }
  if (typeof v['version'] === 'string') t.version = v['version'];
  if (isObj(v['en'])) {
    numMap(v['en']['exposure'], t.en.exposure, errors, 'en.exposure');
    numMap(v['en']['roleMinimum'], t.en.roleMinimum, errors, 'en.roleMinimum');
    numMap(v['en']['mainBarExtra'], t.en.mainBarExtra, errors, 'en.mainBarExtra');
    if (typeof v['en']['defaultExposure'] === 'string') t.en.defaultExposure = v['en']['defaultExposure'];
  }
  if (isObj(v['aci'])) {
    const a: Record<string, number> = {};
    numMap(v['aci'], a, errors, 'aci');
    for (const k of ['ground', 'weather', 'interior', 'interiorSlabWall'] as const) if (a[k] !== undefined) t.aci[k] = a[k]!;
  }
  return t;
}

/** Cover from the table for a role, exposure and standard: nominal (outermost reinforcement), to main bars and to links. */
export function coverFromTable(t: CoverTable, o: { role: string; standard: Standard; exposure?: string; belowGround?: boolean; placement?: string; ground?: boolean }): { nominal: number; mainBars: number; links: number } {
  if (o.standard === 'ACI318') {
    const slabWall = /SLAB|WALL|TOPPING|LANDING|PARAPET|PRECAST_PANEL/.test(o.role) && !/^(PILE|PILE_CAP|RAFT)$/.test(o.role);
    const v = o.ground || o.belowGround ? t.aci.ground : o.placement === 'EXT' || o.placement === 'BOUNDARY' ? t.aci.weather : slabWall ? t.aci.interiorSlabWall : t.aci.interior;
    return { nominal: v, mainBars: v, links: v };
  }
  const classes = (o.exposure ?? t.en.defaultExposure).split(/[,\s]+/).filter(Boolean);
  let nominal = 0;
  for (const c of classes) nominal = Math.max(nominal, t.en.exposure[c] ?? 0);
  if (!nominal) nominal = t.en.exposure[t.en.defaultExposure] ?? 25;
  nominal = Math.max(nominal, t.en.roleMinimum[o.role] ?? 0);
  const extra = t.en.mainBarExtra[o.role] ?? 0;
  return { nominal, mainBars: nominal + extra, links: nominal };
}

/** A cover from an IFC property in mm: a value below 1 is metres. */
export function coverMm(v: unknown): number | undefined {
  const n = typeof v === 'number' ? v : typeof v === 'string' ? Number(v.replace(',', '.')) : NaN;
  if (!Number.isFinite(n) || n <= 0) return undefined;
  return Math.round((n < 1 ? n * 1000 : n) * 10) / 10;
}

/** Fire resistance from a `FireRating`: `REI 90` becomes REI90, a bare number R<n>. */
export function normaliseFire(v: unknown): string | undefined {
  if (typeof v === 'number' && v > 0) return `R${v}`;
  if (typeof v !== 'string') return undefined;
  const t = v.trim().toUpperCase().replace(/\s+/g, '');
  if (!t) return undefined;
  if (/^\d+(MIN)?$/.test(t)) return `R${t.replace('MIN', '')}`;
  return t;
}

// ---------------------------------------------------------------- the whole set

export interface SpecContext {
  role: string;
  placement?: string;
  belowGround?: boolean;
  /** The role's element is cast against the ground. */
  ground?: boolean;
  cover?: CoverTable;
  defaultStandard?: Standard;
}

export interface SpecOut {
  code: string;
  confidence: number;
  source: 'ifc' | 'rule';
  needsReview: boolean;
  fields: Record<string, string | number | boolean>;
  rationale: string;
  /** The IFC reinforcement ratio (kg/m3), when it carries one. */
  ifcRatio?: number;
}

/** XR_ConcreteSpec of one element. */
export function specOf(i: ClassifyInput, c: SpecContext): SpecOut {
  const f: Record<string, string | number | boolean> = {};
  const derived: string[] = [];
  const why: string[] = [];
  let source: 'ifc' | 'rule' = 'rule';
  let review = false;
  const std0 = c.defaultStandard ?? 'EN206';

  // strength
  let strength: ParsedStrength | null = null;
  let strengthIfc = false;
  const sc = propOf(i, 'StrengthClass');
  if (typeof sc === 'string' && sc.trim()) { strength = parseStrength(sc, std0); strengthIfc = !!strength; if (!strength) f['StrengthClass'] = sc.trim(); }
  if (!strength && f['StrengthClass'] === undefined) {
    const text = [i.material ?? '', i.type?.name ?? '', nameText(i)].join(' | ');
    strength = parseStrength(text, std0);
    if (strength) derived.push('StrengthClass');
  }
  if (strength) {
    f['StrengthClass'] = strength.text;
    if (strength.unit) f['StrengthUnit'] = strength.unit;
    if (strength.standard) f['Standard'] = strength.standard;
    why.push(strengthIfc ? 'strength from IFC' : 'strength from the name or material text');
  }
  if (strengthIfc) source = 'ifc';

  // exposure
  const ep = propOf(i, 'ExposureClass') ?? propOf(i, 'EnvironmentalClass');
  let exposure: { classes: string; standard: Standard } | null = null;
  let exposureSource = '';
  if (typeof ep === 'string' && ep.trim()) {
    exposure = parseExposure(ep, true);
    if (exposure) exposureSource = 'ifc'; else { f['ExposureClass'] = ep.trim(); exposureSource = 'ifc'; }
  }
  if (!exposure && f['ExposureClass'] === undefined) {
    const t = parseExposure(`${i.material ?? ''} | ${nameText(i)}`);
    if (t) { exposure = t; exposureSource = 'rule'; derived.push('ExposureClass'); }
  }
  if (!exposure && f['ExposureClass'] === undefined) {
    const sg = suggestExposure(c.placement, c.belowGround);
    if (sg) { exposure = { classes: sg.classes, standard: 'EN206' }; exposureSource = 'suggested'; review = true; derived.push('ExposureClass'); why.push(`exposure suggested: ${sg.why}`); }
  }
  if (exposure) { f['ExposureClass'] = exposure.classes; f['ExposureSource'] = exposureSource; }

  // standard
  if (f['Standard'] === undefined) {
    const std = exposure && exposureSource !== 'suggested' ? exposure.standard : undefined;
    if (std) f['Standard'] = std;
  }

  // cover
  const main = coverMm(propOf(i, 'ConcreteCoverAtMainBars')), links = coverMm(propOf(i, 'ConcreteCoverAtLinks')), nominal = coverMm(propOf(i, 'ConcreteCover'));
  if (nominal !== undefined) f['CoverNominal'] = nominal;
  if (main !== undefined) f['CoverMainBars'] = main;
  if (links !== undefined) f['CoverLinks'] = links;
  const ifcCover = nominal !== undefined || main !== undefined || links !== undefined;
  if (nominal === undefined && (main !== undefined || links !== undefined)) f['CoverNominal'] = Math.min(...[main, links].filter((x): x is number => x !== undefined));
  if (nominal !== undefined) for (const k of ['CoverMainBars', 'CoverLinks']) if (f[k] === undefined) { f[k] = nominal; derived.push(k); }
  if (f['CoverNominal'] === undefined || f['CoverMainBars'] === undefined || f['CoverLinks'] === undefined) {
    const std = (f['Standard'] as Standard | undefined) ?? std0;
    const tab = coverFromTable(c.cover ?? defaultCoverTable(), { role: c.role, standard: std, ...(exposure ? { exposure: exposure.classes } : {}), ...(c.belowGround !== undefined ? { belowGround: c.belowGround } : {}), ...(c.placement ? { placement: c.placement } : {}), ...(c.ground !== undefined ? { ground: c.ground } : {}) });
    let used = false;
    for (const [k, v] of [['CoverNominal', tab.nominal], ['CoverMainBars', tab.mainBars], ['CoverLinks', tab.links]] as const) {
      if (f[k] === undefined) { f[k] = v; derived.push(k); used = true; }
    }
    if (used) { f['CoverSource'] = ifcCover ? 'ifc+table' : 'table'; review = true; why.push('cover from the project table'); }
    else f['CoverSource'] = 'ifc';
  } else f['CoverSource'] = 'ifc';

  const fire = normaliseFire(propOf(i, 'FireRating') ?? propOf(i, 'FireResistance'));
  if (fire) f['FireResistance'] = fire;
  const rg = propOf(i, 'ReinforcementStrengthClass');
  if (typeof rg === 'string' && rg.trim()) f['ReinforcementGrade'] = rg.trim();
  if (derived.length) f['Derived'] = derived.join(',');

  const ratio = propOf(i, 'ReinforcementVolumeRatio');
  const code = typeof f['StrengthClass'] === 'string' ? (f['StrengthClass'] as string) : 'UNKNOWN';
  return {
    code, confidence: code === 'UNKNOWN' ? 0.5 : strengthIfc ? 0.95 : 0.85, source, needsReview: review || code === 'UNKNOWN', fields: f,
    rationale: why.join('; ') || 'no strength class found',
    ...(typeof ratio === 'number' && ratio > 0 ? { ifcRatio: ratio } : {}),
  };
}
