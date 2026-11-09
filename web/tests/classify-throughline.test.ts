// Throughline alignment: a Discipline code list (CodeValue entries) imported as our schema, the results exported in the shape of
// a code list, and the round trip. The shape of an entry is read from schema/modules/engineering/code_value.yaml of Throughline.

import { describe, expect, it } from 'vitest';
import { classifyInputs, buildInputs, defaultSchema, parseSchema, schemaHash } from '../src/classify';
import { ClassifyService } from '../src/classify/service';
import { exportThroughline, exportThroughlineJson, importDisciplineList, schemaToCodeValues, THROUGHLINE_EXPORT_SCHEMA } from '../src/classify/throughline';
import type { ThroughlineCodeValue } from '../src/classify/throughline';
import { MemoryStorage } from '../src/selectionSets';
import { sidecarModel } from './classify-helpers';

const EDITION = 'co.acme.standards@1.0.0';
const entry = (code: string, label: string, extra: Partial<ThroughlineCodeValue> = {}): ThroughlineCodeValue => ({
  code_list: 'Discipline', code, label, meaning: null, crosswalk: null, origin: 'company', sort_order: null, edition: EDITION, effective_from: null, effective_to: null, attributes: {}, ...extra,
});

// The sample company list of the Throughline fixture (co.acme.standards@1.0.0), with `M` and `E` as in a technical item.
const ACME: ThroughlineCodeValue[] = [
  entry('PIP', 'Piping', { sort_order: 10, attributes: { description: 'Piping systems: pipe, fittings, valves and supports.' } }),
  entry('MEC', 'Mechanical', { sort_order: 20, attributes: { description: 'Mechanical equipment and HVAC: ducts, fans, pumps.', sub_disciplines: [{ code: 'DUC', label: 'Ductwork', description: 'Ducts and fittings.' }, { code: 'EQP', label: 'Equipment', description: 'Fans and pumps.' }] } }),
  entry('ELE', 'Electrical', { sort_order: 30 }),
  entry('CIV', 'Civil', { sort_order: 60 }),
  entry('STR', 'Structural', { sort_order: 50 }),
  entry('HSE', 'Health safety and environment', { sort_order: 80, attributes: { fallback: true } }),
];

describe('import of a Throughline Discipline code list', () => {
  it('turns entries into a schema: codes, labels, descriptions, sub-disciplines, edition, order', () => {
    const r = importDisciplineList(ACME);
    expect(r.errors).toEqual([]);
    const s = r.schema!;
    expect(s.schema).toBe('xray-classification-schema/1');
    expect(s.codeList).toBe('Discipline');
    expect(s.edition).toBe(EDITION);
    expect(s.title).toBe(`Throughline Discipline list (${EDITION})`);
    expect(s.disciplines.map((d) => d.code)).toEqual(['PIP', 'MEC', 'ELE', 'STR', 'CIV', 'HSE']); // by sort_order
    const mec = s.disciplines.find((d) => d.code === 'MEC')!;
    expect(mec).toMatchObject({ label: 'Mechanical', description: 'Mechanical equipment and HVAC: ducts, fans, pumps.', sortOrder: 20, origin: 'company' });
    expect(mec.subDisciplines.map((x) => x.code)).toEqual(['DUC', 'EQP']);
    expect(s.disciplines.find((d) => d.code === 'ELE')!.description).toBe('Electrical'); // no description: the label
    expect(s.fallbackDiscipline).toBe('HSE'); // attributes.fallback
    expect(s.masterformat.divisions).toHaveLength(35); // from the shipped list
    expect(r.warnings.join(' ')).toMatch(/4 of 6 entries have no description/);
  });

  it('skips entries of other lists, retired and superseded entries, and says so', () => {
    const r = importDisciplineList([
      ...ACME,
      entry('10', 'Unit 10', { code_list: 'Area' }),
      entry('OLD', 'Old', { lifecycle: 'retired' }),
      entry('SUP', 'Superseded', { lifecycle: 'superseded' }),
      entry('PAST', 'Ended', { effective_to: '2020-01-01' }),
      entry('FUT', 'Not yet ended', { effective_to: '2999-01-01' }),
    ], {}, '2026-11-09');
    expect(r.schema!.disciplines.map((d) => d.code)).toContain('FUT');
    expect(r.schema!.disciplines.map((d) => d.code)).not.toEqual(expect.arrayContaining(['10']));
    for (const gone of ['10', 'OLD', 'SUP', 'PAST']) expect(r.schema!.disciplines.map((d) => d.code), gone).not.toContain(gone);
    expect(r.warnings.join(' ')).toMatch(/1 entry of another code list was skipped/);
    expect(r.warnings.join(' ')).toMatch(/3 retired or superseded entries were skipped/);
  });

  it('reads a JSON text, a list, and an object with values, code_values or entries', () => {
    expect(importDisciplineList(JSON.stringify(ACME)).schema).not.toBeNull();
    for (const key of ['values', 'code_values', 'entries']) expect(importDisciplineList({ [key]: ACME, edition: 'x@1' }).schema!.edition, key).toBe(EDITION);
    expect(importDisciplineList({ code: 'Discipline', edition: 'x@2', data: { values: ACME.map((e) => ({ ...e, code_list: undefined, edition: undefined })) } }).schema!.edition).toBe('x@2');
    expect(importDisciplineList({ code_list: 'Area', values: [{ code: '10', label: 'Unit' }] }).errors[0]).toMatch(/no active "Discipline" entries/);
  });

  it('explains plainly: not JSON, no entries, a missing label, a duplicate code', () => {
    expect(importDisciplineList('{nope').errors[0]).toMatch(/not valid JSON/);
    expect(importDisciplineList({ foo: 1 }).errors[0]).toMatch(/JSON list of Discipline entries/);
    expect(importDisciplineList([]).errors[0]).toMatch(/no active "Discipline" entries/);
    expect(importDisciplineList([{ code: 'X' }]).errors.join(' ')).toMatch(/Entry 1 needs a "code" and a "label"/);
    expect(importDisciplineList([42]).errors[0]).toMatch(/Entry 1 is not an object/);
    expect(importDisciplineList([entry('A', 'One'), entry('A', 'Two')]).errors.join(' ')).toMatch(/discipline code "A" appears twice/);
  });

  it('keeps the built-in rules working when the codes differ: rules_key, or a crosswalk to a rules code', async () => {
    const list = [
      entry('M', 'Mechanical', { sort_order: 10, attributes: { rules_key: 'MEC', description: 'Ducts, fans, HVAC.' } }),
      entry('S', 'Structure', { sort_order: 20, crosswalk: 'STR', origin: 'project' }),
      entry('A', 'Architecture', { sort_order: 30, attributes: { rules_key: 'ARC' } }),
      entry('X', 'Other', { sort_order: 99, attributes: { fallback: true } }),
    ];
    const r = importDisciplineList(list);
    expect(r.schema!.disciplines.map((d) => [d.code, d.rulesKey])).toEqual([['M', 'MEC'], ['S', 'STR'], ['A', 'ARC'], ['X', undefined]]);
    const m = sidecarModel('synth5k');
    const pick = (c: string): number[] => m.elements.filter((e) => e.ifcClass === c).slice(0, 30).map((e) => e.id);
    const inputs = buildInputs(m, [...pick('IfcDuctSegment'), ...pick('IfcPipeSegment')]);
    const run = await classifyInputs(inputs, { schema: r.schema!, provider: null });
    const ducts = run.results.filter((x) => m.elements[m.byGlobalId.get(x.id)!]!.ifcClass === 'IfcDuctSegment');
    expect(ducts.length).toBeGreaterThan(0);
    expect(ducts.every((x) => x.discipline.code === 'M' && x.source === 'rules')).toBe(true);
    // a code that the schema lacks (plumbing): no rule, no model: not classified
    expect(run.results.filter((x) => m.elements[m.byGlobalId.get(x.id)!]!.ifcClass === 'IfcPipeSegment')).toHaveLength(0);
    expect(run.stats.failed).toBe(30);
  });

  it('warns when no code matches a rule, and when there is no fallback entry', () => {
    const r = importDisciplineList([entry('Q', 'Quality', { attributes: { description: 'Quality.' } }), entry('R', 'Risk', { attributes: { description: 'Risk.' } })]);
    expect(r.warnings.join(' ')).toMatch(/None of the codes matches a built-in rule/);
    expect(r.warnings.join(' ')).toMatch(/no general or fallback entry\. "Q" is used/);
    expect(r.schema!.fallbackDiscipline).toBe('Q');
  });

  it('takes the first edition and warns about more than one', () => {
    const r = importDisciplineList([entry('A', 'A', { edition: 'a@1' }), entry('B', 'B', { edition: 'b@2' })]);
    expect(r.schema!.edition).toBe('a@1');
    expect(r.warnings.join(' ')).toMatch(/2 standards editions/);
  });
});

describe('export in the shape of a code list', () => {
  it('writes the whole Discipline list as CodeValue rows with the fields of Throughline', () => {
    const vals = schemaToCodeValues(defaultSchema());
    expect(vals).toHaveLength(11);
    const keys = ['attributes', 'code', 'code_list', 'crosswalk', 'edition', 'effective_from', 'effective_to', 'label', 'meaning', 'origin', 'sort_order'];
    for (const v of vals) expect(Object.keys(v).sort()).toEqual(keys);
    const mec = vals.find((v) => v.code === 'MEC')!;
    expect(mec).toMatchObject({ code_list: 'Discipline', label: 'Mechanical and HVAC', origin: 'company', crosswalk: null, sort_order: expect.any(Number), edition: 'local:xray-throughline-aligned-default@1.0.0' });
    expect((mec.attributes as { sub_disciplines: unknown[] }).sub_disciplines.length).toBeGreaterThan(1);
    expect(vals.find((v) => v.code === 'PLB')).toMatchObject({ origin: 'project', crosswalk: 'PIP' });
    expect(vals.find((v) => v.code === 'ARC')).toMatchObject({ origin: 'project', crosswalk: null });
    expect(vals.find((v) => v.code === 'GEN')!.attributes).toMatchObject({ fallback: true });
    expect(vals.map((v) => v.sort_order)).toEqual([...vals.map((v) => v.sort_order)].sort((a, b) => a! - b!)); // ordered
  });

  it('exports per element a discipline code, and sub-discipline and MasterFormat as attributes', async () => {
    const svc = new ClassifyService({ storage: new MemoryStorage() as never, keyStorages: { session: new MemoryStorage() as never, local: new MemoryStorage() as never } });
    svc.setModel(sidecarModel('fzk-haus'), 'fzk-haus');
    await svc.classify('all');
    const ex = JSON.parse(svc.export('throughline')) as ReturnType<typeof exportThroughline>;
    expect(ex.format).toBe(THROUGHLINE_EXPORT_SCHEMA);
    expect(ex.model).toBe('fzk-haus');
    expect(ex.count).toBe(svc.results().length);
    expect(ex.count).toBeGreaterThan(30);
    const codes = new Set(defaultSchema().disciplines.map((d) => d.code));
    const wall = ex.elements.find((e) => e.discipline === 'ARC')!;
    expect(wall).toMatchObject({ discipline_origin: 'project', crosswalk: null });
    expect(Object.keys(wall).sort()).toEqual(['attributes', 'crosswalk', 'discipline', 'discipline_origin', 'global_id']);
    expect(Object.keys(wall.attributes).sort()).toEqual(['confidence', 'masterformat_division', 'masterformat_edition', 'masterformat_section', 'masterformat_title', 'model', 'needs_review', 'source', 'sub_discipline', 'sub_discipline_label']);
    for (const e of ex.elements) {
      expect(codes.has(e.discipline)).toBe(true); // a code of the list, never free text
      if (e.attributes.masterformat_division) expect(e.attributes.masterformat_edition).toBe('MasterFormat 2018');
    }
    expect(ex.elements.find((e) => e.attributes.sub_discipline)!.attributes.sub_discipline_label).toBeTruthy();
    expect(ex.code_list).toMatchObject({ code_list: 'Discipline', schema_hash: svc.schemaHashValue });
    expect(ex.code_values).toHaveLength(11);
    // ARC has no company code to map to: the export says so; PLB maps to PIP, so it is not listed
    expect(ex.needs_crosswalk).toContain('ARC');
    expect(ex.needs_crosswalk).not.toContain('STR');
  });

  it('gives a project value its company crosswalk per element', () => {
    const s = defaultSchema();
    const r = (code: string): never => ({
      id: code, source: 'model', needsReview: false, buildingElement: 1, model: 'm',
      discipline: { code, label: code, confidence: 0.9, probabilities: { [code]: 0.9 } },
      subDiscipline: null, masterformat: { division: '22', title: 'Plumbing', confidence: 0.8, probabilities: {}, section: '22 11 16' },
    } as never);
    const ex = exportThroughline([r('PLB'), r('MEC')], s, 'x');
    expect(ex.elements[0]).toMatchObject({ discipline: 'PLB', discipline_origin: 'project', crosswalk: 'PIP' });
    expect(ex.elements[1]).toMatchObject({ discipline: 'MEC', discipline_origin: 'company', crosswalk: null });
    expect(ex.elements[0]!.attributes).toMatchObject({ masterformat_division: '22', masterformat_section: '22 11 16', sub_discipline: null, confidence: 0.8 });
    expect(ex.needs_crosswalk).toEqual([]);
    expect(JSON.parse(exportThroughlineJson([r('ARC')], s, 'x')).needs_crosswalk).toEqual(['ARC']);
  });
});

describe('round trip', () => {
  const strip = (s: ReturnType<typeof defaultSchema>) => s.disciplines.map((d) => ({
    code: d.code, label: d.label, description: d.description, crosswalk: d.crosswalk ?? null, rulesKey: d.rulesKey ?? null, sortOrder: d.sortOrder ?? null, company: d.origin === undefined || d.origin === 'company' || d.origin === 'throughline',
    subs: d.subDisciplines.map((x) => [x.code, x.label, x.description]),
  }));

  it('schema -> code values -> schema keeps codes, labels, descriptions, crosswalks and sub-disciplines', () => {
    const original = defaultSchema();
    const back = importDisciplineList(schemaToCodeValues(original));
    expect(back.errors).toEqual([]);
    expect(back.warnings).toEqual([]);
    const a = strip(original).map((d) => ({ ...d, sortOrder: null }));
    const b = strip(back.schema!).map((d) => ({ ...d, sortOrder: null }));
    // origin text changes ("throughline" and "added" become company and project); everything else is equal
    expect(b).toEqual(a);
    expect(back.schema!.fallbackDiscipline).toBe(original.fallbackDiscipline);
    expect(back.schema!.edition).toBe(original.edition);
    expect(back.schema!.disciplines.map((d) => d.origin)).toEqual(original.disciplines.map((d) => (d.origin === 'throughline' ? 'company' : 'project')));
    // the second round does not change anything any more
    const again = importDisciplineList(schemaToCodeValues(back.schema!));
    expect(schemaHash(again.schema!)).toBe(schemaHash(back.schema!));
    expect(schemaToCodeValues(again.schema!)).toEqual(schemaToCodeValues(back.schema!));
  });

  it('an export file imports again: results -> JSON -> schema', async () => {
    const svc = new ClassifyService({ storage: new MemoryStorage() as never, keyStorages: { session: new MemoryStorage() as never, local: new MemoryStorage() as never } });
    svc.setModel(sidecarModel('fzk-haus'), 'fzk-haus');
    await svc.classify('all');
    const text = svc.export('throughline');
    const r = importDisciplineList(text);
    expect(r.errors).toEqual([]);
    expect(r.schema!.disciplines.map((d) => d.code)).toEqual(defaultSchema().disciplines.map((d) => d.code));
    // and the service takes it as its schema (a new hash: caches of the old schema are not mixed in)
    const before = svc.schemaHashValue;
    expect(svc.importThroughline(text)).toEqual([]);
    expect(svc.customSchema).toBe(true);
    expect(svc.schema.codeList).toBe('Discipline');
    expect(svc.schemaHashValue).toBe(before); // the same list: the same decisions
  });

  it('a changed list changes the schema hash, and the service reports problems and notes', () => {
    const svc = new ClassifyService({ storage: new MemoryStorage() as never, keyStorages: { session: new MemoryStorage() as never, local: new MemoryStorage() as never } });
    const h0 = svc.schemaHashValue;
    expect(svc.importThroughline('{bad')[0]).toMatch(/not valid JSON/);
    expect(svc.customSchema).toBe(false);
    expect(svc.importThroughline(ACME)).toEqual([]);
    expect(svc.schemaHashValue).not.toBe(h0);
    expect(svc.importNotes.join(' ')).toMatch(/no description/);
    expect(svc.schema.disciplines).toHaveLength(6);
    svc.useDefaultSchema();
    expect(svc.importNotes).toEqual([]);
    expect(svc.schemaHashValue).toBe(h0);
  });

  it('survives parseSchema of the imported schema (it is a valid xray-classification-schema/1)', () => {
    const r = importDisciplineList(ACME);
    expect(parseSchema(JSON.stringify(r.schema)).errors).toEqual([]);
  });
});

describe('the shipped default schema', () => {
  it('is the Throughline-aligned default, with a note to load the real list', () => {
    const s = defaultSchema();
    expect(s.title).toBe('Throughline-aligned default');
    expect(s.placeholder).toBeUndefined();
    expect(s.codeList).toBe('Discipline');
    expect(s.notice).toMatch(/Throughline `Discipline` code list/);
    expect(s.notice).toMatch(/load the project's actual `Discipline` code list/);
    expect(JSON.stringify(s)).not.toMatch(/placeholder/i);
  });
});
