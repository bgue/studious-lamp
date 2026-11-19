import { describe, expect, it } from 'vitest';
import { defaultSchema, parseSchema, schemaHash } from '../src/classify/schema';
import type { ClassificationSchema } from '../src/classify/types';
import { elementProps, emitAdditions, referencesOf } from '../src/ifcsave/additions';
import * as F from '../src/ifcsave/families';
import { planSave } from '../src/ifcsave/plan';
import type { FileSavePlan, IfcSourceInfo, SaveOptions } from '../src/ifcsave/plan';
import { readAdditions } from '../src/ifcsave/readBack';
import { SCHEMA, syntheticResult } from './ifcsave-helpers';

const O: SaveOptions = { includeReviewers: false, includeCleanupMarks: true, scope: 'all', toolVersion: '1.2.3' };
const src = (schema: string, extra: Partial<IfcSourceInfo> = {}): IfcSourceInfo => ({ fileName: 'a.ifc', schema, maxExpressId: 100, ownerHistoryId: 5, classifications: [], ...extra });
const els = (n: number): Array<{ expressId: number; globalId: string; file: string }> => Array.from({ length: n }, (_, i) => ({ expressId: 10 + i, globalId: `G${i}`, file: 'a.ifc' }));
function plan(schemaName: string, results: Map<string, ReturnType<typeof syntheticResult>>, n = 2, extra: Partial<IfcSourceInfo> = {}, o = O, schema = SCHEMA): FileSavePlan {
  return planSave({ elements: els(n) } as never, results, schema, [src(schemaName, extra)], o)[0]!;
}
const same = (n: number, idx = 1): Map<string, ReturnType<typeof syntheticResult>> => new Map(els(n).map((e) => [e.globalId, { ...syntheticResult(e.globalId, idx), source: 'rules' as const, needsReview: false }]));

describe('families', () => {
  it('maps schema names', () => {
    expect(F.familyOf('IFC2X3')).toBe('2x3');
    expect(F.familyOf('IFC2X3_TC1')).toBe('2x3');
    expect(F.familyOf('IFC4')).toBe('4');
    expect(F.familyOf('IFC4_ADD2_TC1')).toBe('4');
    expect(F.familyOf('IFC4X3_ADD2')).toBe('4x3');
    expect(F.familyOf('IFC4X3')).toBe('4x3');
    expect(F.familyOf('IFC2X2_FINAL')).toBeNull();
    expect(F.familyOf('')).toBeNull();
  });

  const cls = { source: 'CSI', edition: '2018', editionDate: '2018-01-01', name: 'MasterFormat', location: 'https://x.test' };
  it('writes exact text per family', () => {
    expect(F.classificationLine('2x3', 7, cls)).toBe("#7=IFCCLASSIFICATION('CSI','2018',$,'MasterFormat');");
    expect(F.classificationLine('4', 7, cls)).toBe("#7=IFCCLASSIFICATION('CSI','2018','2018-01-01','MasterFormat',$,'https://x.test',$);");
    expect(F.classificationLine('4x3', 7, { source: 's', edition: 'e', name: 'n' })).toBe("#7=IFCCLASSIFICATION('s','e',$,'n',$,$,$);");
    expect(F.classificationReferenceLine('2x3', 8, '23', 'HVAC', 7, null)).toBe("#8=IFCCLASSIFICATIONREFERENCE($,'23','HVAC',#7);");
    expect(F.classificationReferenceLine('2x3', 8, 'A.B', 'Sub', 7, 6)).toBe("#8=IFCCLASSIFICATIONREFERENCE($,'A.B','Sub',#7);");
    expect(F.classificationReferenceLine('4', 8, '23', 'HVAC', 7, null)).toBe("#8=IFCCLASSIFICATIONREFERENCE($,'23','HVAC',#7,$,$);");
    expect(F.classificationReferenceLine('4x3', 9, '23 31 13', 'Ducts', 7, 8)).toBe("#9=IFCCLASSIFICATIONREFERENCE($,'23 31 13','Ducts',#8,$,$);");
    expect(F.relAssociatesClassificationLine('2x3', 10, 'GUID', 5, 'R', [1, 2], 8)).toBe("#10=IFCRELASSOCIATESCLASSIFICATION('GUID',#5,'R',$,(#1,#2),#8);");
    expect(F.relAssociatesClassificationLine('4', 10, 'GUID', 5, 'R', [1], 8)).toBe("#10=IFCRELASSOCIATESCLASSIFICATION('GUID',$,'R',$,(#1),#8);");
    expect(F.propertySingleValueLine(11, { name: 'N', type: 'IfcLabel', value: "it's" })).toBe("#11=IFCPROPERTYSINGLEVALUE('N',$,IFCLABEL('it''s'),$);");
    expect(F.propertySingleValueLine(11, { name: 'N', type: 'IfcBoolean', value: true })).toBe("#11=IFCPROPERTYSINGLEVALUE('N',$,IFCBOOLEAN(.T.),$);");
    expect(F.propertySingleValueLine(11, { name: 'N', type: 'IfcNormalisedRatioMeasure', value: 1 })).toBe("#11=IFCPROPERTYSINGLEVALUE('N',$,IFCNORMALISEDRATIOMEASURE(1.),$);");
    expect(F.propertySetLine('4', 12, 'G', null, 'S', [11, 13])).toBe("#12=IFCPROPERTYSET('G',$,'S',$,(#11,#13));");
    expect(F.relDefinesByPropertiesLine('2x3', 14, 'G', 5, 'R', [1], 12)).toBe("#14=IFCRELDEFINESBYPROPERTIES('G',#5,'R',$,(#1),#12);");
  });
  it('cuts IfcLabel at 255 characters but not IfcText', () => {
    const long = 'x'.repeat(300);
    expect(F.typedValue({ name: 'n', type: 'IfcLabel', value: long })).toBe(`IFCLABEL('${'x'.repeat(255)}')`);
    expect(F.typedValue({ name: 'n', type: 'IfcText', value: long })).toBe(`IFCTEXT('${long}')`);
  });
  it('owner history chain is self contained', () => {
    const l = F.ownerHistoryChain(50, '1');
    expect(l).toHaveLength(5);
    expect(l[4]).toBe('#54=IFCOWNERHISTORY(#52,#53,$,.ADDED.,$,$,$,0);');
  });
});

describe('emitAdditions', () => {
  it('is deterministic: same state, same bytes, same GUIDs', () => {
    const a = emitAdditions(plan('IFC4', same(3), 3), SCHEMA, O);
    const b = emitAdditions(plan('IFC4', same(3), 3), SCHEMA, O);
    expect(a.text).toBe(b.text);
    const c = emitAdditions(plan('IFC4', same(4), 4), SCHEMA, O);
    const guids = (t: string): string[] => [...t.matchAll(/IFCPROPERTYSET\('([^']+)'/g)].map((m) => m[1]!);
    expect(guids(a.text)).not.toEqual(guids(c.text));
    expect(a.text.startsWith('/* XRAY-BEGIN xray-ifc-additions/1 base=100 lines=')).toBe(true);
    expect(a.text).toContain('tool=xray-viewer/1.2.3 */');
    expect(a.lastId).toBe(100 + a.lines);
  });

  it('allocates ids from base + 1 in emit order, and END reports the byte count before it', () => {
    const a = emitAdditions(plan('IFC4', same(2)), SCHEMA, O);
    const ids = [...a.text.matchAll(/^#(\d+)=/gm)].map((m) => Number(m[1]));
    expect(ids).toEqual(ids.map((_, i) => 101 + i));
    const m = /\/\* XRAY-END bytes=(\d+) \*\/\n$/.exec(a.text)!;
    expect(Number(m[1])).toBe(a.text.indexOf('/* XRAY-END'));
  });

  it('pools: identical results share one set and one relation, with all members', () => {
    const a = emitAdditions(plan('IFC4', same(6), 6), SCHEMA, O);
    const sets = [...a.text.matchAll(/^#\d+=IFCPROPERTYSET\('[^']*',\$,'([^']*)'/gm)].map((m) => m[1]);
    expect(sets.sort()).toEqual([SCHEMA.psetName, 'Xray_Review'].sort());
    const rels = [...a.text.matchAll(/^#\d+=IFCRELDEFINESBYPROPERTIES\([^\n]*\(([^)]*)\)/gm)].map((m) => m[1]);
    expect(rels).toEqual(['#10,#11,#12,#13,#14,#15', '#10,#11,#12,#13,#14,#15']);
    const assoc = [...a.text.matchAll(/^#\d+=IFCRELASSOCIATESCLASSIFICATION\([^\n]*\(([^)]*)\)/gm)].map((m) => m[1]);
    expect(assoc.every((s) => s === '#10,#11,#12,#13,#14,#15')).toBe(true);
    // a property value is written once however many sets use it
    const vals = [...a.text.matchAll(/^#\d+=IFCPROPERTYSINGLEVALUE\('Confidence'/gm)];
    expect(vals).toHaveLength(1);
  });

  it('differing results make separate sets', () => {
    const m = new Map([...same(2)]);
    m.set('G1', { ...syntheticResult('G1', 2), source: 'rules' as const });
    const a = emitAdditions(plan('IFC4', m), SCHEMA, O);
    expect([...a.text.matchAll(/IFCPROPERTYSET\('[^']*',\$,'XR_Classification'/g)]).toHaveLength(2);
  });

  it('associates the most specific reference per system and parents the sub-discipline under the discipline (IFC4)', () => {
    const r = { ...syntheticResult('G0', 4), masterformat: { division: '23', title: 'HVAC', confidence: 0.9, probabilities: {}, section: '23 31 13' } };
    const refs = referencesOf(r, '4').map((x) => [x.system, x.code, x.parent?.code]);
    expect(refs).toEqual([['discipline', r.subDiscipline!.code, r.discipline.code], ['masterformat', '23 31 13', '23']]);
    const a = emitAdditions(plan('IFC4', new Map([['G0', r]]), 1), SCHEMA, O);
    expect(a.text).toMatch(new RegExp(`IFCCLASSIFICATIONREFERENCE\\(\\$,'23 31 13','HVAC',#\\d+,\\$,\\$\\)`));
    const read = readAdditions(a.text);
    expect(read.byExpressId.get(10)!.codes.map((c) => [c.system, c.code])).toEqual([[SCHEMA.codeList ?? SCHEMA.title, r.subDiscipline!.code], ['MasterFormat', '23 31 13']]);
    // IFC2X3 has no reference hierarchy: the dotted code keeps the sub-discipline unique
    expect(referencesOf(r, '2x3')[0]!.code).toBe(`${r.discipline.code}.${r.subDiscipline!.code}`);
  });

  it('reuses an existing IfcClassification of the same name and edition, and never one inside an old block', () => {
    const meta = { name: SCHEMA.codeList ?? SCHEMA.title, edition: SCHEMA.edition ?? SCHEMA.version ?? 'unspecified' };
    const reuse = emitAdditions(plan('IFC4', same(2), 2, { classifications: [{ id: 42, name: meta.name.toUpperCase(), edition: meta.edition }] }), SCHEMA, O);
    expect(reuse.text.match(/IFCCLASSIFICATION\(/g)).toHaveLength(1); // MasterFormat only
    expect(reuse.text).toMatch(/IFCCLASSIFICATIONREFERENCE\(\$,'[^']+','[^']+',#42,/);
    const other = emitAdditions(plan('IFC4', same(2), 2, { classifications: [{ id: 42, name: meta.name, edition: 'other edition' }] }), SCHEMA, O);
    expect(other.text.match(/IFCCLASSIFICATION\(/g)).toHaveLength(2);
    const noEdition = emitAdditions(plan('IFC4', same(2), 2, { classifications: [{ id: 42, name: meta.name, edition: null }] }), SCHEMA, O);
    expect(noEdition.text.match(/IFCCLASSIFICATION\(/g)).toHaveLength(1);
    // id 150 > base 100: it sits in our old block, which the new block replaces
    const old = emitAdditions(plan('IFC4', same(2), 2, { classifications: [{ id: 150, name: meta.name, edition: meta.edition }] }), SCHEMA, O);
    expect(old.text.match(/IFCCLASSIFICATION\(/g)).toHaveLength(2);
    // the reuse is read back through the external map
    expect(readAdditions(reuse.text, new Map([[42, meta.name]])).byExpressId.get(10)!.codes[0]!.system).toBe(meta.name);
  });

  it('owner history: 2X3 uses the project one or builds a chain, IFC4 writes $', () => {
    expect(emitAdditions(plan('IFC2X3', same(2)), SCHEMA, O).text).toMatch(/IFCPROPERTYSET\('[^']+',#5,/);
    const none = emitAdditions(plan('IFC2X3', same(2), 2, { ownerHistoryId: null }), SCHEMA, O);
    expect(none.text).toContain("#101=IFCPERSON($,'Unknown'");
    expect(none.text).toContain('#105=IFCOWNERHISTORY(#103,#104,$,.ADDED.,$,$,$,0);');
    expect(none.text).toMatch(/IFCPROPERTYSET\('[^']+',#105,/);
    const four = emitAdditions(plan('IFC4X3_ADD2', same(2), 2, { ownerHistoryId: 5 }), SCHEMA, O);
    expect(four.text).toMatch(/IFCPROPERTYSET\('[^']+',\$,/);
    expect(four.text).not.toContain('IFCOWNERHISTORY');
  });

  it('dates: IfcDateTime from IFC4, an IfcLabel in 2X3', () => {
    const r = new Map([['G0', syntheticResult('G0', 5)]]);
    expect(emitAdditions(plan('IFC4', r, 1), SCHEMA, O).text).toContain("'ReviewedAt',$,IFCDATETIME('2026-03-04T10:11:12Z')");
    expect(emitAdditions(plan('IFC2X3', r, 1), SCHEMA, O).text).toContain("'ReviewedAt',$,IFCLABEL('2026-03-04T10:11:12Z')");
  });

  it('writes no reviewer name or comment with includeReviewers false (leak assertion)', () => {
    const r = new Map([['G0', syntheticResult('G0', 5)]]);
    const p = planSave({ elements: els(1) } as never, r, SCHEMA, [src('IFC4')], O, { comments: new Map([['G0', 'private remark']]) })[0]!;
    const off = emitAdditions(p, SCHEMA, O).text;
    expect(off).not.toContain('Alice Reviewer');
    expect(off).not.toContain('private remark');
    expect(off).not.toContain('ReviewedBy');
    expect(off).not.toContain("'Comment'");
    const on = emitAdditions(p, SCHEMA, { ...O, includeReviewers: true }).text;
    expect(on).toContain("'ReviewedBy',$,IFCLABEL('Alice Reviewer')");
    expect(on).toContain("'Comment',$,IFCTEXT('private remark')");
  });

  it('property order and omissions follow the design', () => {
    const e = { expressId: 1, globalId: 'G', result: { ...syntheticResult('G', 5), subDiscipline: null, masterformat: null } };
    const p = elementProps(e, SCHEMA, '4', O);
    expect(p.classification.map((x) => x.name)).toEqual(['Discipline', 'Confidence', 'Source', 'Model', 'NeedsReview']); // empty values are left out
    expect(p.review.map((x) => x.name)).toEqual(['Status', 'Unsure', 'NeedsReview', 'Confidence', 'DisciplineConfidence', 'BuildingElementProbability', 'ProposedBy', 'ReviewedAt', 'CommitId', 'SchemaHash']);
    const rev = elementProps({ ...e, revision: { status: 'changed', baseline: 'v1.ifc' }, cleanup: { rules: ['tiny', 'floating'], reasons: ['a', 'b'] } }, SCHEMA, '4', O);
    expect(rev.review.slice(-2).map((x) => [x.name, x.value])).toEqual([['RevisionStatus', 'changed'], ['RevisionBaseline', 'v1.ifc']]);
    expect(rev.cleanup.map((x) => [x.name, x.value])).toEqual([['FlaggedForRemoval', true], ['Rules', 'tiny;floating'], ['Reason', 'a; b']]);
    expect(elementProps({ ...e, cleanup: { rules: [], reasons: [] } }, SCHEMA, '4', { ...O, includeCleanupMarks: false }).cleanup).toEqual([]);
  });

  it('writes nothing for an empty plan', () => {
    const a = emitAdditions({ ...plan('IFC4', same(1)), elements: [] }, SCHEMA, O);
    expect(a).toEqual({ text: '', lines: 0, lastId: 100 });
  });

  it('scope reviewed keeps only reviewed results; plans are split per source by file name', () => {
    const results = new Map(els(3).map((e, i) => [e.globalId, syntheticResult(e.globalId, i * 5 === 0 ? 5 : i)])); // G0 is confirmed
    const elements = [...els(3).slice(0, 2), { expressId: 10, globalId: 'H0', file: 'b.ifc' }];
    results.set('H0', syntheticResult('H0', 10));
    const [a, b] = planSave({ elements } as never, results, SCHEMA, [src('IFC4'), src('IFC2X3', { fileName: 'b.ifc' })], { ...O, scope: 'reviewed' });
    expect(a!.elements.map((e) => e.globalId)).toEqual(['G0']);
    expect(b!.elements.map((e) => e.globalId)).toEqual(['H0']);
    expect(b!.family).toBe('2x3');
  });

  it('refuses an unsupported schema by name', () => {
    expect(() => planSave({ elements: [] } as never, new Map(), SCHEMA, [src('IFC2X2_FINAL')], O)).toThrow(/IFC2X2_FINAL/);
  });

  it('uses systems from the schema when given', () => {
    const s: ClassificationSchema = { ...SCHEMA, systems: { discipline: { name: 'Uniclass', source: 'NBS', edition: '2015', editionDate: '2024-05-01' }, masterformat: { name: 'OmniClass', edition: '2020' } } };
    const a = emitAdditions(plan('IFC4', same(1), 1, {}, O, s), s, O);
    expect(a.text).toContain("IFCCLASSIFICATION('NBS','2015','2024-05-01','Uniclass',$,$,$)");
    expect(a.text).toContain("IFCCLASSIFICATION('CSI','2020',$,'OmniClass',$,$,$)");
  });
});

describe('schema systems', () => {
  it('is parsed, validated and not hashed', () => {
    const base = JSON.parse(JSON.stringify(defaultSchema()));
    const h = schemaHash(defaultSchema());
    const withSys = parseSchema({ ...base, systems: { discipline: { name: 'Uniclass', edition: '2015', editionDate: '2024-05-01' } } });
    expect(withSys.errors).toEqual([]);
    expect(withSys.schema!.systems!.discipline).toEqual({ name: 'Uniclass', edition: '2015', editionDate: '2024-05-01' });
    expect(schemaHash(withSys.schema!)).toBe(h);
    expect(parseSchema({ ...base, systems: { masterformat: { edition: '1' } } }).errors[0]).toMatch(/systems\.masterformat/);
    expect(parseSchema({ ...base, systems: { discipline: { name: 'x', editionDate: 'May' } } }).errors[0]).toMatch(/editionDate/);
    expect(parseSchema(base).schema!.systems).toBeUndefined();
  });
});
