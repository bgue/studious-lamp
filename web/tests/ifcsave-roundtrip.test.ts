import { beforeAll, describe, expect, it, vi } from 'vitest';

vi.setConfig({ testTimeout: 120000 });
import type { IfcAPI } from 'web-ifc';
import { propertyNames } from '../src/classify/schema';
import { overallConfidence } from '../src/classify/review';
import type { ClassifyResult } from '../src/classify/types';
import { createIfcApi } from '../src/model/ifcRaw';
import { elementProps, emitAdditions, referencesOf } from '../src/ifcsave/additions';
import { planSave } from '../src/ifcsave/plan';
import type { FileSavePlan, SaveOptions } from '../src/ifcsave/plan';
import { readAdditions } from '../src/ifcsave/readBack';
import { locateInsert, splice } from '../src/ifcsave/splice';
import { CASES, SCHEMA, blobOf, bytesOf, elementsOf, fileBytes, latin1, sameBytes, sourceInfo, syntheticResult, textOf, wasmPath } from './ifcsave-helpers';

const OPTS: SaveOptions = { includeReviewers: false, includeCleanupMarks: true, scope: 'all', toolVersion: 'test' };
let api: IfcAPI;
beforeAll(async () => {
  api = await createIfcApi({ url: wasmPath });
}, 60000);

async function save(blob: Blob, name: string, results: ReadonlyMap<string, ClassifyResult>, elems: Array<{ expressId: number; globalId: string }>, o: SaveOptions = OPTS) {
  const info = await sourceInfo(name, blob);
  const model = { elements: elems.map((e) => ({ ...e, file: name })) } as never;
  const cleanup = new Map(elems.filter((_, i) => i % 11 === 0).map((e) => [e.globalId, { rules: ['tiny', 'floating'], reasons: ['smaller than 5 cm'] }]));
  const [plan] = planSave(model, results, SCHEMA, [info], o, { cleanup }) as [FileSavePlan];
  const add = emitAdditions(plan, SCHEMA, o);
  const at = await locateInsert(blob);
  const out = splice(blob, at, add.text);
  return { info, plan, add, at, out };
}

describe.each(CASES)('save round trip: $name', ({ name, path }) => {
  const orig = fileBytes(path);
  const blob = blobOf(path);
  let origCount = 0;
  let elems: Array<{ expressId: number; globalId: string }> = [];
  let results = new Map<string, ClassifyResult>();
  let guidOfId = new Map<number, string>();
  beforeAll(() => {
    const m = api.OpenModel(orig);
    origCount = api.GetAllLines(m).size();
    elems = elementsOf(api, m);
    const all = api.GetAllLines(m);
    for (let i = 0; i < all.size(); i++) {
      const g = api.GetLine(m, all.get(i))?.GlobalId?.value;
      if (typeof g === 'string') guidOfId.set(all.get(i), g);
    }
    api.CloseModel(m);
    elems.forEach((e, i) => results.set(e.globalId, syntheticResult(e.globalId, i)));
  });

  it('keeps the original bytes and writes one marked block before the final ENDSEC', async () => {
    const { out, at, add } = await save(blob, name, results, elems);
    const bytes = new Uint8Array(await out.arrayBuffer());
    expect(add.lines).toBeGreaterThan(0);
    expect(sameBytes(bytes.subarray(0, at.cut), orig.subarray(0, at.cut))).toBe(true);
    expect(sameBytes(bytes.subarray(bytes.length - (orig.length - at.cut)), orig.subarray(at.cut))).toBe(true);
    const text = latin1(bytes.subarray(at.cut));
    expect(text.startsWith('/* XRAY-BEGIN xray-ifc-additions/1 base=')).toBe(true);
    expect(text.match(/XRAY-BEGIN/g)).toHaveLength(1);
    expect(text.match(/XRAY-END/g)).toHaveLength(1);
    expect(text.indexOf('ENDSEC;')).toBeGreaterThan(text.indexOf('XRAY-END'));
  });

  it('opens in web-ifc with original + added entities; every original id keeps its GlobalId', async () => {
    const { out, add } = await save(blob, name, results, elems);
    const m = api.OpenModel(new Uint8Array(await out.arrayBuffer()));
    expect(api.GetAllLines(m).size()).toBe(origCount + add.lines);
    for (const [id, g] of guidOfId) expect(api.GetLine(m, id)?.GlobalId?.value).toBe(g);
    api.CloseModel(m);
  });

  it('reads back: classification references and Xray_Review values, equal to the plan (readAdditions and web-ifc)', async () => {
    const { out, plan, add } = await save(blob, name, results, elems);
    const read = readAdditions(add.text);
    expect(read.header?.lines).toBe(add.lines);
    expect(read.header?.base).toBe(plan.base);
    const names = propertyNames(SCHEMA);
    for (const e of plan.elements) {
      const got = read.byExpressId.get(e.expressId)!;
      expect(got, `element #${e.expressId}`).toBeTruthy();
      const want = referencesOf(e.result!, plan.family).map((r) => r.code).sort();
      expect(got.codes.map((c) => c.code).sort()).toEqual(want);
      const p = elementProps(e, SCHEMA, plan.family, OPTS);
      for (const [set, list] of [[SCHEMA.psetName, p.classification], ['Xray_Review', p.review], ['Xray_Cleanup', p.cleanup]] as const)
        for (const prop of list) expect(got.review[`${set}.${prop.name}`], `${set}.${prop.name}`).toEqual(prop.type === 'IfcNormalisedRatioMeasure' ? Number(prop.value) : prop.value);
      expect(got.review[`${SCHEMA.psetName}.${names.discipline}`]).toBe(e.result!.discipline.code);
      expect(got.review[`${SCHEMA.psetName}.${names.confidence}`]).toBe(overallConfidence(e.result!));
    }
    // the same through web-ifc
    const m = api.OpenModel(new Uint8Array(await out.arrayBuffer()));
    const assoc = api.GetLineIDsWithType(m, api.GetTypeCodeFromName?.('IFCRELASSOCIATESCLASSIFICATION') ?? 0);
    const seen = new Map<number, string[]>();
    for (let i = 0; i < assoc.size(); i++) {
      const l = api.GetLine(m, assoc.get(i), true);
      if (l.Name?.value !== 'Xray classification') continue;
      const code = (l.RelatingClassification?.Identification ?? l.RelatingClassification?.ItemReference)?.value as string;
      for (const o of l.RelatedObjects) (seen.get(o.value ?? o.expressID) ?? seen.set(o.value ?? o.expressID, []).get(o.value ?? o.expressID)!).push(code);
    }
    for (const e of plan.elements) expect((seen.get(e.expressId) ?? []).sort()).toEqual(referencesOf(e.result!, plan.family).map((r) => r.code).sort());
    api.CloseModel(m);
  });

  it('saving again with the same state gives the same bytes; with changed state the count does not double', async () => {
    const first = await save(blob, name, results, elems);
    const firstBytes = await bytesOf(first.out);
    // second save from the saved file: the old block is found and replaced, base comes from its marker
    const second = await save(first.out, name, results, elems);
    expect(second.at.oldBlock?.base).toBe(first.plan.base);
    expect(second.plan.base).toBe(first.plan.base);
    expect(sameBytes(await bytesOf(second.out), firstBytes)).toBe(true);

    const changed = new Map(results);
    for (const [i, e] of elems.entries()) if (i % 3 === 0) changed.set(e.globalId, syntheticResult(e.globalId, i + 1));
    const third = await save(first.out, name, changed, elems);
    const m = api.OpenModel(new Uint8Array(await third.out.arrayBuffer()));
    expect(api.GetAllLines(m).size()).toBe(origCount + third.add.lines);
    api.CloseModel(m);
    expect((await textOf(third.out)).match(/XRAY-BEGIN/g)).toHaveLength(1);
  });

  it('removing all state removes the block and restores the original bytes', async () => {
    const first = await save(blob, name, results, elems);
    const empty = await save(first.out, name, new Map(), elems, { ...OPTS, includeCleanupMarks: false });
    expect(empty.add.text).toBe('');
    expect(sameBytes(await bytesOf(empty.out), orig)).toBe(true);
  });

  it('writes no reviewer name or comment unless asked', async () => {
    const comments = new Map(elems.map((e) => [e.globalId, 'SECRET-COMMENT-Zed'] as const));
    const info = await sourceInfo(name, blob);
    const model = { elements: elems.map((e) => ({ ...e, file: name })) } as never;
    for (const includeReviewers of [false, true]) {
      const o = { ...OPTS, includeReviewers };
      const [plan] = planSave(model, results, SCHEMA, [info], o, { comments });
      const text = emitAdditions(plan!, SCHEMA, o).text;
      expect(text.includes('Alice Reviewer')).toBe(includeReviewers);
      expect(text.includes('SECRET-COMMENT-Zed')).toBe(includeReviewers);
    }
  });
});
