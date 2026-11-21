// The 4D mapping tool's save into the IFC: the property set Xray_4D (IfcLabel Location, Trade, Zone) on each mapped element, written
// append-only in the same block as the other Xray sets, replaced on re-save, read back by web-ifc and by the viewer's importer.
import { readFileSync } from 'node:fs';
import { beforeAll, describe, expect, it, vi } from 'vitest';
import type { IfcAPI } from 'web-ifc';
import { createIfcApi } from '../src/model/ifcRaw';
import { planOf } from '../src/ifcsave/collect';
import { DEFAULT_SAVE_OPTIONS } from '../src/ifcsave/plan';
import type { SaveOptions } from '../src/ifcsave/plan';
import { runSave } from '../src/ifcsave/run';
import { readAdditions } from '../src/ifcsave/readBack';
import { locateInsert } from '../src/ifcsave/splice';
import { makeSource } from '../src/ifcsave/source';
import { acceptedValues, assign, decide } from '../src/map4d/assignments';
import { assignmentsFromProps, newFromProps, saveMap } from '../src/map4d/ifcio';
import { suggest } from '../src/map4d/suggest';
import { CASES, SCHEMA, blobOf, elementsOf, sourceInfo, bytesOf, modelIfc, sameBytes, syntheticResult, textOf, wasmPath, fileBytes } from './ifcsave-helpers';

vi.setConfig({ testTimeout: 180000 });
vi.mock('../src/model/ifcRuntime', () => ({
  IFC_READER_AVAILABLE: true,
  createIfcWorker: () => { throw new Error('no worker in node'); },
  getWasmSource: async () => ({ url: wasmPath }),
  loadRawReader: () => import('../src/model/ifcRaw'),
}));
const { importIfc } = await import('../src/model/ifcImport');

const FZK = modelIfc('AC20-FZK-Haus.ifc');
const OPTS: SaveOptions = { ...DEFAULT_SAVE_OPTIONS, includeFourD: true, toolVersion: 'test' };
const input = (): { name: string; data: ArrayBuffer }[] => [{ name: 'AC20-FZK-Haus.ifc', data: new Uint8Array(readFileSync(FZK)).buffer as ArrayBuffer }];

let api: IfcAPI;
beforeAll(async () => { api = await createIfcApi({ url: wasmPath }); }, 60000);

/** Properties of each element from the Xray_4D set, by express id, read through web-ifc. */
function readFourD(bytes: Uint8Array): Map<number, Record<string, string>> {
  const m = api.OpenModel(bytes);
  const out = new Map<number, Record<string, string>>();
  const rels = api.GetLineIDsWithType(m, api.GetTypeCodeFromName?.('IFCRELDEFINESBYPROPERTIES') ?? 0);
  for (let i = 0; i < rels.size(); i++) {
    const r = api.GetLine(m, rels.get(i), true);
    const set = r.RelatingPropertyDefinition;
    if (set?.Name?.value !== 'Xray_4D') continue;
    const props: Record<string, string> = {};
    for (const p of set.HasProperties) { expect(p.NominalValue?.type).toBe(1); props[p.Name.value] = p.NominalValue.value; }
    for (const o of r.RelatedObjects) out.set(o.value ?? o.expressID, props);
  }
  api.CloseModel(m);
  return out;
}

describe('Xray_4D in the IFC (FZK-Haus)', () => {
  let res: Awaited<ReturnType<typeof importIfc>>;
  let source: ReturnType<typeof makeSource>;
  let list = [] as ReturnType<typeof assign>['list'];
  beforeAll(async () => {
    res = await importIfc(input(), { forceMainThread: true, edges: 'none' });
    source = makeSource(res.raws[0]!.fileName, blobOf(FZK), res.raws[0]!.schema, res.raws[0]!.saveInfo);
    const model = res.loaded.model;
    // locations by storey, trades by suggestion + accept, one zone with a non-ASCII name
    for (const s of model.storeys) list = assign(list, model.elements.filter((e) => e.storey === s.id).map((e) => e.globalId), 'location', s.name).list;
    const storeyName = new Map(model.storeys.map((s) => [s.id, s.name] as const));
    const props = suggest(model.elements.map((e) => ({ globalId: e.globalId, ifcClass: e.ifcClass, material: e.material, storey: e.storey === null ? null : storeyName.get(e.storey) })), { attributes: ['trade'], existing: list });
    list = [...list, ...props];
    list = decide(list, props.map((p) => p.id), 'accepted').list;
    list = assign(list, model.elements.slice(0, 5).map((e) => e.globalId), 'zone', 'Zone Ébène 中').list;
  });

  const plan = (include: boolean, withResults = false) => planOf({
    model: res.loaded.model, sources: [source], results: withResults ? res.loaded.model.elements.map((e, i) => syntheticResult(e.globalId, i)) : [], schema: SCHEMA,
    options: { ...OPTS, includeFourD: include }, fourD: saveMap(list),
  });

  it('plans only mapped elements, with accepted values only', () => {
    const [p] = plan(true);
    const want = saveMap(list);
    expect(p!.elements.length).toBe(want.size);
    expect(p!.elements.length).toBeGreaterThan(20);
    for (const e of p!.elements) expect(e.fourD).toEqual(want.get(e.globalId));
    expect(plan(false)[0]!.elements).toHaveLength(0);
  });

  it('does not write a proposed or rejected value', () => {
    const model = res.loaded.model;
    const extra = suggest([{ globalId: model.elements[0]!.globalId, ifcClass: 'IfcRoof', storey: 'Nowhere' }], { attributes: ['location'], existing: [] });
    const withProposal = [...list.filter((a) => a.element !== model.elements[0]!.globalId), ...extra];
    expect(saveMap(withProposal).get(model.elements[0]!.globalId)).toBeUndefined();
  });

  it('writes one block with the Xray_4D set, reads back equal through web-ifc, and every original line is kept', async () => {
    const [p] = plan(true);
    const [out] = await runSave([{ plan: p!, blob: source.blob }], SCHEMA, OPTS);
    const bytes = await bytesOf(new Blob(out!.parts));
    const text = await textOf(new Blob(out!.parts));
    expect(text.match(/XRAY-BEGIN/g)).toHaveLength(1);
    expect(text).toContain("'Xray_4D'");
    const orig = fileBytes(FZK);
    const at = await locateInsert(source.blob);
    expect(sameBytes(bytes.subarray(0, at.cut), orig.subarray(0, at.cut))).toBe(true);
    // properties through web-ifc
    const got = readFourD(bytes);
    const want = saveMap(list);
    expect(got.size).toBe(want.size);
    for (const e of p!.elements) {
      const v = got.get(e.expressId)!;
      const w = want.get(e.globalId)!;
      expect(v.Location, e.globalId).toBe(w.location);
      expect(v.Trade).toBe(w.trade);
      expect(v.Zone).toBe(w.zone);
    }
    expect([...got.values()].some((v) => v.Zone === 'Zone Ébène 中')).toBe(true);
    // properties through the block reader
    const read = readAdditions(text.slice(at.cut, text.indexOf('ENDSEC;', at.cut)));
    const first = p!.elements[0]!;
    expect(read.byExpressId.get(first.expressId)!.review['Xray_4D.Location']).toBe(want.get(first.globalId)!.location);
  });

  it('reopens mapped: the viewer reads Xray_4D back into accepted assignments (source property)', async () => {
    const [p] = plan(true);
    const [out] = await runSave([{ plan: p!, blob: source.blob }], SCHEMA, OPTS);
    const saved = await bytesOf(new Blob(out!.parts));
    const again = await importIfc([{ name: 'AC20-FZK-Haus.xray.ifc', data: saved.buffer.slice(saved.byteOffset, saved.byteOffset + saved.byteLength) as ArrayBuffer }], { forceMainThread: true, edges: 'none' });
    const back = assignmentsFromProps(again.loaded.model.elements);
    expect(back.every((a) => a.status === 'accepted' && a.source === 'property' && a.confidence === 1 && !('reviewed_by' in a))).toBe(true);
    const have = acceptedValues(back);
    const want = saveMap(list);
    expect(have.size).toBe(want.size);
    for (const [g, v] of want) expect(have.get(g), g).toEqual(v);
    // a fresh model has nothing stored: all of them are new; with the same values stored, none is
    expect(newFromProps([], back)).toHaveLength(back.length);
    expect(newFromProps(list, back)).toHaveLength(0);
  });

  it('saves again with the same bytes (idempotent) and the count of lines does not double', async () => {
    const [p] = plan(true);
    const [first] = await runSave([{ plan: p!, blob: source.blob }], SCHEMA, OPTS);
    const firstBlob = new Blob(first!.parts);
    const src2 = makeSource('AC20-FZK-Haus.ifc', firstBlob, res.raws[0]!.schema, { ...res.raws[0]!.saveInfo!, blockBase: p!.base });
    const [p2] = planOf({ model: res.loaded.model, sources: [src2], results: [], schema: SCHEMA, options: OPTS, fourD: saveMap(list) });
    const [second] = await runSave([{ plan: p2!, blob: firstBlob }], SCHEMA, OPTS);
    expect(sameBytes(await bytesOf(new Blob(second!.parts)), await bytesOf(firstBlob))).toBe(true);
    expect(second!.replaced).toBe(true);
  });

  it('turning the option off removes Xray_4D and restores the original bytes; other sets stay', async () => {
    const [p] = plan(true, true);
    const [both] = await runSave([{ plan: p!, blob: source.blob }], SCHEMA, OPTS);
    const bothBlob = new Blob(both!.parts);
    const t = await textOf(bothBlob);
    expect(t).toContain("'Xray_4D'");
    expect(t).toContain("'Xray_Review'");
    const [noFour] = planOf({ model: res.loaded.model, sources: [source], results: res.loaded.model.elements.map((e, i) => syntheticResult(e.globalId, i)), schema: SCHEMA, options: { ...OPTS, includeFourD: false }, fourD: saveMap(list) });
    const [o2] = await runSave([{ plan: noFour!, blob: bothBlob }], SCHEMA, { ...OPTS, includeFourD: false });
    const t2 = await textOf(new Blob(o2!.parts));
    expect(t2).not.toContain("'Xray_4D'");
    expect(t2).toContain("'Xray_Review'");
    const [none] = planOf({ model: res.loaded.model, sources: [source], results: [], schema: SCHEMA, options: { ...OPTS, includeFourD: false, includeCleanupMarks: false }, fourD: saveMap(list) });
    const [o3] = await runSave([{ plan: none!, blob: bothBlob }], SCHEMA, { ...OPTS, includeFourD: false, includeCleanupMarks: false });
    expect(sameBytes(await bytesOf(new Blob(o3!.parts)), fileBytes(FZK))).toBe(true);
  });
});

describe.each(CASES)('Xray_4D in every schema: $name', ({ name, path }) => {
  it('writes and reads back Location, Trade and Zone', async () => {
    const blob = blobOf(path);
    const m = api.OpenModel(fileBytes(path));
    const elems = elementsOf(api, m).slice(0, 40);
    api.CloseModel(m);
    const fourD = new Map(elems.map((e, i) => [e.globalId, { location: `Level ${i % 3}`, ...(i % 2 ? { trade: 'CONC' } : {}), ...(i % 5 === 0 ? { zone: `Z ${i}` } : {}) }] as const));
    const info = await sourceInfo(name, blob);
    const [p] = planOf({ model: { elements: elems.map((e) => ({ ...e, file: name })) } as never, sources: [{ ...info, blob }], results: [], schema: SCHEMA, options: OPTS, fourD });
    expect(p!.elements).toHaveLength(elems.length);
    const [out] = await runSave([{ plan: p!, blob }], SCHEMA, OPTS);
    const got = readFourD(await bytesOf(new Blob(out!.parts)));
    for (const e of p!.elements) {
      const w = fourD.get(e.globalId)!;
      expect(got.get(e.expressId), e.globalId).toEqual({ Location: w.location, ...(w.trade ? { Trade: w.trade } : {}), ...(w.zone ? { Zone: w.zone } : {}) });
    }
  });
});
