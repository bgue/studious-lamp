// Throughline alignment of the classification schema. No DOM.
//
// Throughline (the project at /home/user/studious-lamp, schema/modules/engineering) keeps coded lists as `engineering.CodeList`
// registry entries; each value of a list is an `engineering.CodeValue` row with these fields:
//
//   code_list   the list the value belongs to ("Discipline")           code        the value's code ("PIP")
//   label       display text                                            meaning     IRI that says what the value means
//   sort_order  position in the list                                    origin      "company" or "project"
//   crosswalk   the COMPANY code that a project-added value maps to     edition     the standards edition, "co.acme.standards@1.0.0"
//   attributes  list-specific content (any JSON object)                 effective_from / effective_to, lifecycle (active, superseded, retired)
//
// A document (`documents.Document.discipline`) and a technical item (`correspondence.TechnicalItem.discipline`) carry a `discipline`
// that is a code of the `Discipline` list. This file does two things:
//   importDisciplineList(entries)   a JSON export of the `Discipline` CodeValue entries -> our `xray-classification-schema/1`
//   exportThroughline(...)          the results -> per element a `discipline` code; sub-discipline and MasterFormat as `attributes`;
//                                   the code values that were used, as CodeValue rows (so the export imports again)

import { DEFAULT_SCHEMA } from './defaultSchema';
import { parseSchema, schemaHash } from './schema';
import { overallConfidence } from './review';
import type { ClassificationSchema, ClassifyResult, SchemaDiscipline } from './types';

export const THROUGHLINE_EXPORT_SCHEMA = 'xray-throughline-classification/1';
export const DISCIPLINE_LIST = 'Discipline';
/** The values that the `origin` field takes in a Throughline CodeValue. */
export type ThroughlineOrigin = 'company' | 'project';

/** One `engineering.CodeValue` row, as a JSON export has it. Every field but `code` and `label` may be missing. */
export interface ThroughlineCodeValue {
  code_list?: string;
  code: string;
  label: string;
  meaning?: string | null;
  crosswalk?: string | null;
  origin?: string | null;
  sort_order?: number | null;
  edition?: string | null;
  effective_from?: string | null;
  effective_to?: string | null;
  lifecycle?: string | null;
  attributes?: Record<string, unknown> | null;
}

const isObj = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
const str = (v: unknown): v is string => typeof v === 'string' && v.trim() !== '';

// ---------------------------------------------------------------- import

export interface ImportResult {
  schema: ClassificationSchema | null;
  /** Plain-language problems. Empty when the schema is usable. */
  errors: string[];
  /** Things that work but deserve a second look (entries skipped, descriptions missing). */
  warnings: string[];
}

export interface ImportOptions {
  /** Codes that the built-in rules speak (default: the codes of the shipped schema). An entry with one of them, or a crosswalk to one, gets rules. */
  rulesCodes?: readonly string[];
  /** MasterFormat divisions and edition for the new schema (default: the shipped list; Throughline has no MasterFormat code list). */
  masterformat?: ClassificationSchema['masterformat'];
  /** psetName, properties and minConfidence come from here (default: the shipped schema). */
  base?: ClassificationSchema;
}

/** The entries of an export: a list, or an object with `values`, `code_values`, `entries` or `items`. */
function entriesOf(input: unknown): { list: unknown[]; edition?: string; codeList?: string } | string {
  let v = input;
  if (typeof v === 'string') {
    try {
      v = JSON.parse(v);
    } catch (e) {
      return `The file is not valid JSON: ${e instanceof Error ? e.message : String(e)}`;
    }
  }
  if (Array.isArray(v)) return { list: v };
  if (isObj(v)) {
    for (const k of ['values', 'code_values', 'codeValues', 'entries', 'items']) {
      if (Array.isArray(v[k])) {
        return { list: v[k] as unknown[], ...(str(v['edition']) ? { edition: v['edition'] } : {}), ...(str(v['code_list']) ? { codeList: v['code_list'] as string } : {}) };
      }
    }
    // The export of this viewer: { code_list: { ... }, code_values: [...] } is handled above; a CodeList record with `data.values` too.
    const data = v['data'];
    if (isObj(data) && Array.isArray(data['values'])) return { list: data['values'] as unknown[], ...(str(v['edition']) ? { edition: v['edition'] } : {}), ...(str(v['code']) ? { codeList: v['code'] as string } : {}) };
  }
  return 'The file must be a JSON list of Discipline entries, or an object with a "values" (or "code_values", "entries") list.';
}

const closed = (e: Record<string, unknown>, today: string): boolean => {
  const life = str(e['lifecycle']) ? (e['lifecycle'] as string).toLowerCase() : '';
  if (life === 'retired' || life === 'superseded') return true;
  return str(e['effective_to']) && (e['effective_to'] as string) < today;
};

/**
 * A Throughline `Discipline` code list (JSON of CodeValue entries) as an `xray-classification-schema/1`.
 *  - entries of another list (a `code_list` other than Discipline) are skipped; retired and superseded entries too
 *  - `label` and `code` carry over; the choice text is `attributes.description` (else the label); the sub-disciplines are
 *    `attributes.sub_disciplines` (a list of { code, label, description })
 *  - `origin`, `crosswalk`, `meaning`, `sort_order` and `edition` carry over; `attributes.rules_key` (or the crosswalk, or the code)
 *    names the built-in rules key, so the rules still work when the project's codes differ from ours (`M` for `MEC`)
 */
export function importDisciplineList(input: unknown, o: ImportOptions = {}, today = new Date().toISOString().slice(0, 10)): ImportResult {
  const warnings: string[] = [];
  const found = entriesOf(input);
  if (typeof found === 'string') return { schema: null, errors: [found], warnings };
  const base = o.base ?? DEFAULT_SCHEMA;
  const rulesCodes = new Set(o.rulesCodes ?? DEFAULT_SCHEMA.disciplines.map((d) => d.code));
  const errors: string[] = [];
  const picked: Array<{ e: Record<string, unknown>; index: number }> = [];
  let otherList = 0;
  let skippedClosed = 0;
  found.list.forEach((raw, index) => {
    if (!isObj(raw)) { errors.push(`Entry ${index + 1} is not an object.`); return; }
    if (str(raw['code_list']) && (raw['code_list'] as string) !== DISCIPLINE_LIST) { otherList++; return; }
    if (!str(raw['code_list']) && found.codeList && found.codeList !== DISCIPLINE_LIST) { otherList++; return; }
    if (closed(raw, today)) { skippedClosed++; return; }
    picked.push({ e: raw, index });
  });
  if (otherList) warnings.push(`${otherList} entr${otherList === 1 ? 'y' : 'ies'} of another code list ${otherList === 1 ? 'was' : 'were'} skipped. Only the "${DISCIPLINE_LIST}" list is used.`);
  if (skippedClosed) warnings.push(`${skippedClosed} retired or superseded entr${skippedClosed === 1 ? 'y' : 'ies'} ${skippedClosed === 1 ? 'was' : 'were'} skipped.`);
  if (picked.length === 0) return { schema: null, errors: [...errors, `The file has no active "${DISCIPLINE_LIST}" entries.`], warnings };

  let noDescription = 0;
  const editions = new Set<string>();
  const disciplines: SchemaDiscipline[] = [];
  let fallback: string | undefined;
  picked
    .map((p, i) => ({ ...p, order: typeof p.e['sort_order'] === 'number' ? (p.e['sort_order'] as number) : Number.MAX_SAFE_INTEGER, i }))
    .sort((a, b) => a.order - b.order || String(a.e['code']).localeCompare(String(b.e['code'])) || a.i - b.i)
    .forEach(({ e, index }) => {
      if (!str(e['code']) || !str(e['label'])) { errors.push(`Entry ${index + 1} needs a "code" and a "label".`); return; }
      const code = (e['code'] as string).trim();
      const attrs = isObj(e['attributes']) ? (e['attributes'] as Record<string, unknown>) : {};
      const description = str(attrs['description']) ? (attrs['description'] as string).trim() : str(e['definition']) ? (e['definition'] as string).trim() : '';
      if (!description) noDescription++;
      const subsRaw = Array.isArray(attrs['sub_disciplines']) ? (attrs['sub_disciplines'] as unknown[]) : Array.isArray(attrs['subDisciplines']) ? (attrs['subDisciplines'] as unknown[]) : [];
      const subDisciplines = subsRaw.filter(isObj).filter((s) => str(s['code']) && str(s['label'])).map((s) => ({
        code: (s['code'] as string).trim(),
        label: (s['label'] as string).trim(),
        description: str(s['description']) ? (s['description'] as string).trim() : (s['label'] as string).trim(),
        ...(str(s['rules_key']) ? { rulesKey: (s['rules_key'] as string).trim() } : str(s['rulesKey']) ? { rulesKey: (s['rulesKey'] as string).trim() } : {}),
      }));
      const crosswalk = str(e['crosswalk']) ? (e['crosswalk'] as string).trim() : undefined;
      const explicit = str(attrs['rules_key']) ? (attrs['rules_key'] as string).trim() : str(attrs['rulesKey']) ? (attrs['rulesKey'] as string).trim() : undefined;
      const rulesKey = explicit ?? (rulesCodes.has(code) ? undefined : crosswalk && rulesCodes.has(crosswalk) ? crosswalk : undefined);
      if (str(e['edition'])) editions.add((e['edition'] as string).trim());
      if (attrs['fallback'] === true && !fallback) fallback = code;
      disciplines.push({
        code,
        label: (e['label'] as string).trim(),
        description: description || (e['label'] as string).trim(),
        origin: str(e['origin']) ? (e['origin'] as string).trim() : 'company',
        ...(crosswalk ? { crosswalk } : {}),
        ...(str(e['meaning']) ? { meaning: (e['meaning'] as string).trim() } : {}),
        ...(typeof e['sort_order'] === 'number' && Number.isFinite(e['sort_order']) ? { sortOrder: e['sort_order'] as number } : {}),
        ...(rulesKey ? { rulesKey } : {}),
        subDisciplines,
      });
    });
  if (errors.length) return { schema: null, errors, warnings };
  if (noDescription) warnings.push(`${noDescription} of ${disciplines.length} entries have no description (attributes.description), so the decision model chooses them by their label only. Add a description to each for better results.`);
  if (editions.size > 1) warnings.push(`The entries come from ${editions.size} standards editions (${[...editions].join(', ')}). The first is recorded.`);
  const edition = [...editions][0] ?? found.edition;
  const gen = disciplines.find((d) => d.code === 'GEN') ?? disciplines.find((d) => /^(OTH|GENERAL|MISC)$/i.test(d.code));
  const fb = fallback ?? gen?.code ?? disciplines[0]!.code;
  if (!fallback && !gen) warnings.push(`The list has no general or fallback entry. "${fb}" is used for elements that nothing could place; mark one entry with attributes.fallback = true to choose another.`);

  const ruled = disciplines.filter((d) => d.rulesKey || rulesCodes.has(d.code)).length;
  if (ruled === 0) warnings.push('None of the codes matches a built-in rule (MEC, STR, ARC, ...), so no element is classified by rules and every element goes to the decision model. Add attributes.rules_key to an entry to enable a rule.');

  const out = parseSchema({
    schema: 'xray-classification-schema/1',
    title: `Throughline ${DISCIPLINE_LIST} list${edition ? ` (${edition})` : ''}`,
    version: edition ?? '1.0.0',
    codeList: DISCIPLINE_LIST,
    ...(edition ? { edition } : {}),
    notice: 'Imported from a Throughline Discipline code list. MasterFormat comes from the shipped list.',
    psetName: base.psetName,
    minConfidence: base.minConfidence,
    properties: base.properties,
    fallbackDiscipline: fb,
    disciplines,
    masterformat: o.masterformat ?? base.masterformat,
  });
  if (!out.schema) return { schema: null, errors: out.errors, warnings };
  return { schema: out.schema, errors: [], warnings };
}

// ---------------------------------------------------------------- export

const toOrigin = (o: string | undefined): ThroughlineOrigin => (o === undefined || o === 'company' || o === 'throughline' ? 'company' : 'project');

/** The `Discipline` code values of a schema, as Throughline CodeValue rows (they import again with importDisciplineList). */
export function schemaToCodeValues(schema: ClassificationSchema): ThroughlineCodeValue[] {
  const edition = schema.edition ?? null;
  return schema.disciplines.map((d, i) => ({
    code_list: schema.codeList ?? DISCIPLINE_LIST,
    code: d.code,
    label: d.label,
    meaning: d.meaning ?? null,
    crosswalk: d.crosswalk ?? null,
    origin: toOrigin(d.origin),
    sort_order: d.sortOrder ?? (i + 1) * 10,
    edition,
    effective_from: null,
    effective_to: null,
    attributes: {
      description: d.description,
      ...(d.rulesKey ? { rules_key: d.rulesKey } : {}),
      ...(d.code === schema.fallbackDiscipline ? { fallback: true } : {}),
      ...(d.subDisciplines.length ? { sub_disciplines: d.subDisciplines.map((s) => ({ code: s.code, label: s.label, description: s.description, ...(s.rulesKey ? { rules_key: s.rulesKey } : {}) })) } : {}),
    },
  }));
}

export interface ThroughlineElement {
  global_id: string;
  /** A code of the `Discipline` list: what `Document.discipline` and `TechnicalItem.discipline` hold. */
  discipline: string;
  /** `company` for a company value; `project` for a value that a project added (it needs a crosswalk to a company code). */
  discipline_origin: ThroughlineOrigin;
  /** The company code that a project value maps to; null for a company value, or a project value without a crosswalk. */
  crosswalk: string | null;
  /** Sub-discipline and MasterFormat are not code lists of Throughline: they are attributes, as a code list's `attributes` are. */
  attributes: {
    sub_discipline: string | null;
    sub_discipline_label: string | null;
    masterformat_division: string | null;
    masterformat_title: string | null;
    masterformat_section: string | null;
    masterformat_edition: string | null;
    confidence: number;
    source: string;
    model: string | null;
    needs_review: boolean;
    /** Set only on a result that a person committed in the review walk (source confirmed or corrected). */
    confirmed_by?: string;
    confirmed_at?: string;
    commit_id?: string;
    /** On the same committed elements: true when the reviewer flagged the change as a guess ("Unsure"). */
    unsure?: boolean;
  };
}

export interface ThroughlineExport {
  format: typeof THROUGHLINE_EXPORT_SCHEMA;
  model: string;
  count: number;
  code_list: { code_list: string; edition: string | null; schema_title: string; schema_version: string | null; schema_hash: string };
  /** The whole `Discipline` list of the schema as CodeValue rows: this file imports again with importDisciplineList. */
  code_values: ThroughlineCodeValue[];
  /** Codes that the elements use which are project values without a crosswalk: the company must add them, or map them. */
  needs_crosswalk: string[];
  elements: ThroughlineElement[];
}

const round = (n: number): number => Math.round(n * 1000) / 1000;

/** The results in a shape that Throughline can take in. Pure. */
export function exportThroughline(results: readonly ClassifyResult[], schema: ClassificationSchema, modelName: string): ThroughlineExport {
  const byCode = new Map(schema.disciplines.map((d) => [d.code, d]));
  const used = new Set<string>();
  const edition = schema.masterformat.edition ?? null;
  const elements = results.map((r): ThroughlineElement => {
    const d = byCode.get(r.discipline.code);
    used.add(r.discipline.code);
    const origin = toOrigin(d?.origin);
    return {
      global_id: r.id,
      discipline: r.discipline.code,
      discipline_origin: origin,
      crosswalk: origin === 'project' ? d?.crosswalk ?? null : null,
      attributes: {
        sub_discipline: r.subDiscipline?.code ?? null,
        sub_discipline_label: r.subDiscipline?.label ?? null,
        masterformat_division: r.masterformat?.division ?? null,
        masterformat_title: r.masterformat?.title ?? null,
        masterformat_section: r.masterformat?.section ?? null,
        masterformat_edition: r.masterformat ? edition : null,
        confidence: round(overallConfidence(r)),
        source: r.source,
        model: r.model ?? null,
        needs_review: r.needsReview,
        ...(r.confirmedBy !== undefined ? { confirmed_by: r.confirmedBy } : {}),
        ...(r.confirmedAt !== undefined ? { confirmed_at: r.confirmedAt } : {}),
        ...(r.commitId !== undefined ? { commit_id: r.commitId } : {}),
        ...(r.confirmedBy !== undefined ? { unsure: r.unsure === true } : {}),
      },
    };
  });
  const values = schemaToCodeValues(schema);
  return {
    format: THROUGHLINE_EXPORT_SCHEMA,
    model: modelName,
    count: elements.length,
    code_list: { code_list: schema.codeList ?? DISCIPLINE_LIST, edition: schema.edition ?? null, schema_title: schema.title, schema_version: schema.version ?? null, schema_hash: schemaHash(schema) },
    code_values: values,
    needs_crosswalk: values.filter((v) => used.has(v.code) && v.origin === 'project' && !v.crosswalk).map((v) => v.code),
    elements,
  };
}

export const exportThroughlineJson = (results: readonly ClassifyResult[], schema: ClassificationSchema, modelName: string): string => JSON.stringify(exportThroughline(results, schema, modelName), null, 2);
