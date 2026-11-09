// The target schema: parse and check a schema file, look codes up, validate decisions against it, and build the JSON
// Schema that the providers send as structured output.

import { DEFAULT_SCHEMA } from './defaultSchema';
import type { ClassificationSchema, SchemaDiscipline, SchemaPropertyNames } from './types';

export const SCHEMA_ID = 'xray-classification-schema/1';
export const DEFAULT_MIN_CONFIDENCE = 0.6;

export const DEFAULT_PROPERTY_NAMES: SchemaPropertyNames = {
  discipline: 'Discipline',
  subDiscipline: 'SubDiscipline',
  masterformatDivision: 'MasterFormatDivision',
  masterformatTitle: 'MasterFormatTitle',
  masterformatSection: 'MasterFormatSection',
  confidence: 'Confidence',
  source: 'Source',
  model: 'Model',
  needsReview: 'NeedsReview',
};

export function defaultSchema(): ClassificationSchema {
  return DEFAULT_SCHEMA;
}

/** Property names of the schema with the defaults filled in. */
export function propertyNames(schema: ClassificationSchema): SchemaPropertyNames {
  const p = schema.properties ?? {};
  const out = { ...DEFAULT_PROPERTY_NAMES };
  for (const k of Object.keys(out) as Array<keyof SchemaPropertyNames>) if (typeof p[k] === 'string' && p[k]!.trim()) out[k] = p[k]!.trim();
  return out;
}

const isObj = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
const str = (v: unknown): v is string => typeof v === 'string' && v.trim() !== '';
const PROP_NAME = /^[A-Za-z_][A-Za-z0-9_]*$/;

export interface SchemaParse {
  schema: ClassificationSchema | null;
  /** Plain-language problems. Empty when the schema is usable. */
  errors: string[];
}

/** Check untrusted JSON (text or value) and return a clean schema, or the reasons it is not one. Never throws. */
export function parseSchema(input: unknown): SchemaParse {
  let v: unknown = input;
  if (typeof input === 'string') {
    try {
      v = JSON.parse(input);
    } catch (e) {
      return { schema: null, errors: [`The schema file is not valid JSON: ${e instanceof Error ? e.message : String(e)}`] };
    }
  }
  const errors: string[] = [];
  if (!isObj(v)) return { schema: null, errors: ['The schema must be a JSON object.'] };
  if (v['schema'] !== SCHEMA_ID) errors.push(`"schema" must be "${SCHEMA_ID}".`);
  if (!str(v['psetName']) || !PROP_NAME.test(v['psetName'] as string)) errors.push('"psetName" must be a name of letters, digits and underscores, such as XR_Classification.');
  const props: Record<string, string> = {};
  if (v['properties'] !== undefined) {
    if (!isObj(v['properties'])) errors.push('"properties" must be an object that maps each output property to its name.');
    else {
      for (const [k, n] of Object.entries(v['properties'])) {
        if (!(k in DEFAULT_PROPERTY_NAMES)) errors.push(`"properties.${k}" is not a known output property.`);
        else if (!str(n) || !PROP_NAME.test(n)) errors.push(`"properties.${k}" must be a name of letters, digits and underscores.`);
        else props[k] = n;
      }
    }
  }
  const disciplines: SchemaDiscipline[] = [];
  if (!Array.isArray(v['disciplines']) || v['disciplines'].length === 0) errors.push('"disciplines" must be a list with at least one discipline.');
  else {
    const seen = new Set<string>();
    v['disciplines'].forEach((d: unknown, i: number) => {
      if (!isObj(d) || !str(d['code']) || !str(d['label'])) {
        errors.push(`disciplines[${i}] needs a "code" and a "label".`);
        return;
      }
      const code = (d['code'] as string).trim();
      if (seen.has(code)) errors.push(`The discipline code "${code}" appears twice.`);
      seen.add(code);
      const subs: SchemaDiscipline['subDisciplines'] = [];
      const sseen = new Set<string>();
      const rawSubs = d['subDisciplines'] === undefined ? [] : d['subDisciplines'];
      if (!Array.isArray(rawSubs)) errors.push(`disciplines[${i}].subDisciplines must be a list.`);
      else {
        rawSubs.forEach((s: unknown, j: number) => {
          if (!isObj(s) || !str(s['code']) || !str(s['label'])) {
            errors.push(`disciplines[${i}].subDisciplines[${j}] needs a "code" and a "label".`);
            return;
          }
          const sc = (s['code'] as string).trim();
          if (sseen.has(sc)) errors.push(`The sub-discipline code "${sc}" appears twice under "${code}".`);
          sseen.add(sc);
          subs.push({ code: sc, label: (s['label'] as string).trim(), description: str(s['description']) ? (s['description'] as string).trim() : (s['label'] as string).trim(), ...(str(s['rulesKey']) ? { rulesKey: (s['rulesKey'] as string).trim() } : {}) });
        });
      }
      disciplines.push({
        code,
        label: (d['label'] as string).trim(),
        description: str(d['description']) ? (d['description'] as string).trim() : (d['label'] as string).trim(),
        subDisciplines: subs,
        ...(str(d['rulesKey']) ? { rulesKey: (d['rulesKey'] as string).trim() } : {}),
        ...(str(d['origin']) ? { origin: d['origin'] as string } : {}),
        ...(str(d['crosswalk']) ? { crosswalk: (d['crosswalk'] as string).trim() } : {}),
        ...(str(d['meaning']) ? { meaning: (d['meaning'] as string).trim() } : {}),
        ...(typeof d['sortOrder'] === 'number' && Number.isFinite(d['sortOrder']) ? { sortOrder: d['sortOrder'] } : {}),
      });
    });
  }
  const mf = v['masterformat'];
  const divisions: ClassificationSchema['masterformat']['divisions'] = [];
  let appliesTo: 'building' | 'all' = 'building';
  let mfRest: { edition?: string; note?: string } = {};
  if (!isObj(mf) || !Array.isArray(mf['divisions']) || mf['divisions'].length === 0) errors.push('"masterformat.divisions" must be a list with at least one division.');
  else {
    const seen = new Set<string>();
    mf['divisions'].forEach((d: unknown, i: number) => {
      if (!isObj(d) || !str(d['division']) || !str(d['title']) || !/^\d{2}$/.test((d['division'] as string).trim())) {
        errors.push(`masterformat.divisions[${i}] needs a two-digit "division" such as "23" and a "title".`);
        return;
      }
      const n = (d['division'] as string).trim();
      if (seen.has(n)) errors.push(`The division "${n}" appears twice.`);
      seen.add(n);
      divisions.push({ division: n, title: (d['title'] as string).trim(), description: str(d['description']) ? (d['description'] as string).trim() : (d['title'] as string).trim() });
    });
    if (mf['appliesTo'] !== undefined) {
      if (mf['appliesTo'] === 'building' || mf['appliesTo'] === 'all') appliesTo = mf['appliesTo'];
      else errors.push('"masterformat.appliesTo" must be "building" or "all".');
    }
    mfRest = { ...(str(mf['edition']) ? { edition: mf['edition'] as string } : {}), ...(str(mf['note']) ? { note: mf['note'] as string } : {}) };
  }
  let minConfidence = DEFAULT_MIN_CONFIDENCE;
  if (v['minConfidence'] !== undefined) {
    if (typeof v['minConfidence'] === 'number' && v['minConfidence'] >= 0 && v['minConfidence'] <= 1) minConfidence = v['minConfidence'];
    else errors.push('"minConfidence" must be a number from 0 to 1.');
  }
  const fb = v['fallbackDiscipline'];
  if (fb !== undefined && (!str(fb) || !disciplines.some((d) => d.code === fb))) errors.push('"fallbackDiscipline" must be one of the discipline codes.');
  if (errors.length) return { schema: null, errors };
  const fbCode = str(fb) ? (fb as string) : disciplines[0]!.code;
  const fbDisc = disciplines.find((d) => d.code === fbCode)!;
  const fsub = v['fallbackSubDiscipline'];
  const schema: ClassificationSchema = {
    schema: SCHEMA_ID,
    title: str(v['title']) ? (v['title'] as string) : 'Classification schema',
    ...(str(v['version']) ? { version: v['version'] as string } : {}),
    ...(v['placeholder'] === true ? { placeholder: true } : {}),
    ...(str(v['codeList']) ? { codeList: (v['codeList'] as string).trim() } : {}),
    ...(str(v['edition']) ? { edition: (v['edition'] as string).trim() } : {}),
    ...(str(v['notice']) ? { notice: v['notice'] as string } : {}),
    psetName: (v['psetName'] as string).trim(),
    minConfidence,
    properties: props,
    fallbackDiscipline: fbCode,
    ...(str(fsub) && fbDisc.subDisciplines.some((s) => s.code === fsub) ? { fallbackSubDiscipline: fsub as string } : {}),
    disciplines,
    masterformat: { ...mfRest, appliesTo, divisions },
  };
  return { schema, errors: [] };
}

// ---------------------------------------------------------------- lookups

export function findDiscipline(schema: ClassificationSchema, key: string): SchemaDiscipline | undefined {
  return schema.disciplines.find((d) => d.code === key) ?? schema.disciplines.find((d) => d.rulesKey === key);
}

export function findSub(d: SchemaDiscipline, key: string): SchemaDiscipline['subDisciplines'][number] | undefined {
  return d.subDisciplines.find((s) => s.code === key) ?? d.subDisciplines.find((s) => s.rulesKey === key);
}

export function divisionTitle(schema: ClassificationSchema, division: string): string | undefined {
  return schema.masterformat.divisions.find((d) => d.division === division)?.title;
}

/** True when the schema wants a MasterFormat division only for building elements (the default). */
export function masterformatBuildingOnly(schema: ClassificationSchema): boolean {
  return schema.masterformat.appliesTo !== 'all';
}

// ---------------------------------------------------------------- hash

/** A short, stable hash of the parts of the schema that change a decision (code lists and descriptions). 53-bit, hex. */
export function schemaHash(schema: ClassificationSchema): string {
  const text = JSON.stringify([
    schema.disciplines.map((d) => [d.code, d.label, d.description, d.subDisciplines.map((s) => [s.code, s.label, s.description])]),
    schema.masterformat.divisions.map((d) => [d.division, d.title, d.description]),
    schema.masterformat.appliesTo ?? 'building',
    schema.fallbackDiscipline ?? '',
  ]);
  let h1 = 0xdeadbeef;
  let h2 = 0x41c6ce57;
  for (let i = 0; i < text.length; i++) {
    const c = text.charCodeAt(i);
    h1 = Math.imul(h1 ^ c, 2654435761);
    h2 = Math.imul(h2 ^ c, 1597334677);
  }
  h1 = Math.imul(h1 ^ (h1 >>> 16), 2246822507) ^ Math.imul(h2 ^ (h2 >>> 13), 3266489909);
  h2 = Math.imul(h2 ^ (h2 >>> 16), 2246822507) ^ Math.imul(h1 ^ (h1 >>> 13), 3266489909);
  return (4294967296 * (2097151 & h2) + (h1 >>> 0)).toString(16).padStart(14, '0');
}
