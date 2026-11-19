// Save IFC in the app (ticket T2): the importer's saveInfo, retained sources, the plan of a federation (one output per file), the
// pipeline over Blobs (worker fallback, progress, cancel), attach, cleanup marks and the reviewer leak rule.
import { readFileSync } from 'node:fs';
import { beforeAll, describe, expect, it, vi } from 'vitest';
import type { IfcAPI } from 'web-ifc';
import type { ClassifyResult } from '../src/classify/types';
import type { ReviewCommit } from '../src/classify/reviewLog';
import { createIfcApi } from '../src/model/ifcRaw';
import { SaveCancelled, startSave } from '../src/ifcsave/client';
import { cleanupMarks, planOf, reviewComments } from '../src/ifcsave/collect';
import { DEFAULT_SAVE_OPTIONS } from '../src/ifcsave/plan';
import type { SaveOptions } from '../src/ifcsave/plan';
import { outputName, runSave } from '../src/ifcsave/run';
import type { SaveProgress } from '../src/ifcsave/run';
import { checkAttach, makeSource, ownClassifications, tailBlockBase } from '../src/ifcsave/source';
import type { IfcSource } from '../src/ifcsave/source';
import { uniqueFileNames } from '../src/plugins/fileLoader';
import { CASES, SCHEMA, blobOf, fileBytes, latin1, modelIfc, fxIfc, sourceInfo, syntheticResult, textOf, wasmPath } from './ifcsave-helpers';
import { scanStep } from '../src/ifcsave/stepScan';

vi.setConfig({ testTimeout: 180000 });

// importIfc reaches web-ifc through ifcRuntime; in node the wasm is a file path and there is no worker.
vi.mock('../src/model/ifcRuntime', () => ({
  IFC_READER_AVAILABLE: true,
  createIfcWorker: () => { throw new Error('no worker in node'); },
  getWasmSource: async () => ({ url: wasmPath }),
  loadRawReader: () => import('../src/model/ifcRaw'),
}));
const { importIfc } = await import('../src/model/ifcImport');

const OPTS: SaveOptions = { ...DEFAULT_SAVE_OPTIONS, toolVersion: 'test' };
const FZK = modelIfc('AC20-FZK-Haus.ifc');
const PORTS = fxIfc('ports-ifc2x3.ifc');
const inputOf = (path: string, name: string) => ({ name, data: new Uint8Array(readFileSync(path)).buffer as ArrayBuffer });

let api: IfcAPI;
beforeAll(async () => { api = await createIfcApi({ url: wasmPath }); }, 60000);

describe('importer saveInfo equals stepScan, and a federation saves one output per file', () => {
  let res: Awaited<ReturnType<typeof importIfc>>;
  let sources: IfcSource[] = [];
  beforeAll(async () => {
    res = await importIfc([inputOf(FZK, 'AC20-FZK-Haus.ifc'), inputOf(PORTS, 'ports-ifc2x3.ifc')], { forceMainThread: true, edges: 'none' });
    sources = res.raws.map((r, i) => makeSource(r.fileName, blobOf([FZK, PORTS][i]!), r.schema, r.saveInfo));
  });

  it('captures maxExpressId, OwnerHistory and classifications as stepScan finds them', async () => {
    expect(res.raws.map((r) => r.fileName)).toEqual(['AC20-FZK-Haus.ifc', 'ports-ifc2x3.ifc']);
    for (const [i, r] of res.raws.entries()) {
      const s = await scanStep([blobOf(FZK), blobOf(PORTS)][i]!);
      expect(r.saveInfo, r.fileName).toBeTruthy();
      expect(r.saveInfo!.maxExpressId).toBe(s.maxExpressId);
      expect(r.saveInfo!.ownerHistoryId).toBe(s.ownerHistoryId);
      expect(r.saveInfo!.classifications).toEqual(s.classifications);
      expect(r.saveInfo!.blockBase).toBeNull();
      expect(r.schema).toBe(s.schema);
    }
    expect(sources[1]!.ownerHistoryId, 'IFC2X3 keeps the project OwnerHistory').not.toBeNull();
  });

  it('plans two files, each element in its own file, and writes two outputs that re-open', async () => {
    const model = res.loaded.model;
    const results = model.elements.map((e, i) => syntheticResult(e.globalId, i));
    const plans = planOf({ model, sources, results, schema: SCHEMA, options: OPTS });
    expect(plans.map((p) => p.fileName)).toEqual(['AC20-FZK-Haus.ifc', 'ports-ifc2x3.ifc']);
    for (const p of plans) {
      expect(p.elements.length).toBeGreaterThan(0);
      for (const e of p.elements) {
        const rec = model.elements.find((x) => x.globalId === e.globalId)!;
        expect(rec.file, e.globalId).toBe(p.fileName);
        expect(rec.expressId).toBe(e.expressId);
      }
    }
    expect(plans.reduce((a, p) => a + p.elements.length, 0)).toBe(model.elements.length);
    const progress: SaveProgress[] = [];
    const out = await runSave(plans.map((plan, i) => ({ plan, blob: sources[i]!.blob })), SCHEMA, OPTS, (p) => progress.push(p));
    expect(out.map((f) => f.outName)).toEqual(['AC20-FZK-Haus.xray.ifc', 'ports-ifc2x3.xray.ifc']);
    expect(new Set(progress.map((p) => p.phase))).toEqual(new Set(['locate', 'emit', 'splice']));
    for (const [i, f] of out.entries()) {
      const orig = fileBytes([FZK, PORTS][i]!);
      const blob = new Blob(f.parts);
      expect(blob.size).toBe(f.bytes);
      expect(new Uint8Array(await blob.slice(0, orig.length - 200).arrayBuffer())).toEqual(orig.subarray(0, orig.length - 200));
      const m = api.OpenModel(new Uint8Array(await blob.arrayBuffer()));
      const m0 = api.OpenModel(orig);
      expect(api.GetAllLines(m).size()).toBe(api.GetAllLines(m0).size() + f.lines);
      api.CloseModel(m);
      api.CloseModel(m0);
    }
  });

  it('writes nothing for an element whose twin was dropped as a duplicate', async () => {
    const twin = await importIfc([inputOf(PORTS, 'a.ifc'), inputOf(PORTS, 'a (2).ifc')], { forceMainThread: true, edges: 'none' });
    expect(twin.report.duplicatesSkipped).toBeGreaterThan(0);
    const srcs = twin.raws.map((r) => makeSource(r.fileName, blobOf(PORTS), r.schema, r.saveInfo));
    const results = twin.loaded.model.elements.map((e, i) => syntheticResult(e.globalId, i));
    const [a, b] = planOf({ model: twin.loaded.model, sources: srcs, results, schema: SCHEMA, options: OPTS });
    expect(a!.elements.length).toBe(twin.loaded.model.elements.length);
    expect(b!.elements.length).toBe(0);
  });
});

describe('file names of a federation', () => {
  it('makes names unique with " (n)" before the extension', () => {
    expect(uniqueFileNames(['a.ifc', 'b.ifc'])).toEqual(['a.ifc', 'b.ifc']);
    expect(uniqueFileNames(['a.ifc', 'a.ifc', 'A.IFC'])).toEqual(['a.ifc', 'a (2).ifc', 'A (3).IFC']);
  });
  it('names the output <stem>.xray.ifc and keeps that name on a re-save', () => {
    expect(outputName('Model.ifc')).toBe('Model.xray.ifc');
    expect(outputName('Model.xray.ifc')).toBe('Model.xray.ifc');
    expect(outputName('Model (2).IFC')).toBe('Model (2).xray.ifc');
    expect(outputName('weird')).toBe('weird.xray.ifc');
  });
});

describe('re-saving a file that holds our block', () => {
  it('replaces the block, takes the base from the marker and ignores our classifications', async () => {
    const c = CASES.find((x) => x.name === 'AC20-FZK-Haus.ifc')!;
    const blob = blobOf(c.path);
    const info = await sourceInfo(c.name, blob);
    const model = { elements: [] as Array<{ expressId: number; globalId: string; file: string }> };
    const m = api.OpenModel(fileBytes(c.path));
    const all = api.GetAllLines(m);
    for (let i = 0; i < all.size() && model.elements.length < 40; i++) {
      const id = all.get(i);
      if (!api.IsIfcElement(api.GetLineType(m, id))) continue;
      model.elements.push({ expressId: id, globalId: api.GetLine(m, id).GlobalId.value as string, file: c.name });
    }
    api.CloseModel(m);
    const results = model.elements.map((e, i) => syntheticResult(e.globalId, i));
    const source: IfcSource = { ...info, blob };
    const plans = planOf({ model: model as never, sources: [source], results, schema: SCHEMA, options: OPTS });
    const [first] = await runSave([{ plan: plans[0]!, blob }], SCHEMA, OPTS);
    const saved = new Blob(first!.parts);
    // what the importer would capture from the saved file: web-ifc counts our lines in maxExpressId, our classifications are dropped
    const bytes = new Uint8Array(await saved.arrayBuffer());
    const base = tailBlockBase(bytes);
    expect(base).toBe(info.maxExpressId);
    const s = await scanStep(saved);
    expect(s.maxExpressId).toBeGreaterThan(info.maxExpressId);
    expect(ownClassifications([...s.classifications, { id: info.maxExpressId + 1, name: 'x', edition: null }], base).some((x) => x.id > base!)).toBe(false);
    // a source made from the new file, with a stale blockBase: runSave still takes the marker's base
    const stale: IfcSource = { ...info, maxExpressId: s.maxExpressId, blockBase: null, blob: saved };
    const again = planOf({ model: model as never, sources: [stale], results, schema: SCHEMA, options: OPTS });
    const [second] = await runSave([{ plan: again[0]!, blob: saved }], SCHEMA, OPTS);
    expect(second!.replaced).toBe(true);
    expect(latin1(new Uint8Array(await new Blob(second!.parts).arrayBuffer()))).toBe(latin1(bytes));
  });
});

describe('reviewer names and comments (leak rule)', () => {
  const NAME = 'Rosalind Reviewer-Fanshawe';
  const COMMENT = 'checked on site by the structural engineer';
  const history = [{ id: 'c1', author: NAME, time: '2026-03-04T10:00:00Z', note: '', modelName: 'm', modelFingerprint: 'f', schemaEdition: 'e', changes: [{ globalId: 'g', action: 'confirm', comment: COMMENT }] }] as unknown as ReviewCommit[];
  const c = CASES[0]!;
  async function run(o: Partial<SaveOptions>): Promise<string> {
    const blob = blobOf(c.path);
    const info = await sourceInfo(c.name, blob);
    const m = api.OpenModel(fileBytes(c.path));
    const all = api.GetAllLines(m);
    const elements: Array<{ expressId: number; globalId: string; file: string }> = [];
    for (let i = 0; i < all.size() && elements.length < 30; i++) {
      const id = all.get(i);
      if (api.IsIfcElement(api.GetLineType(m, id))) elements.push({ expressId: id, globalId: api.GetLine(m, id).GlobalId.value as string, file: c.name });
    }
    api.CloseModel(m);
    const results: ClassifyResult[] = elements.map((e, i) => ({ ...syntheticResult(e.globalId, 0), source: 'confirmed' as const, confirmedBy: NAME, confirmedAt: '2026-03-04T10:11:12Z', commitId: `c${i}` }));
    const hist = [{ ...history[0]!, changes: [{ ...history[0]!.changes[0]!, globalId: elements[0]!.globalId }] }] as ReviewCommit[];
    const plans = planOf({ model: { elements } as never, sources: [{ ...info, blob }], results, schema: SCHEMA, options: { ...OPTS, ...o }, history: hist });
    const [f] = await runSave([{ plan: plans[0]!, blob }], SCHEMA, { ...OPTS, ...o });
    if (!o.includeReviewers) expect(JSON.stringify(plans)).not.toContain(COMMENT);
    return textOf(new Blob(f!.parts));
  }
  it('are absent from the bytes and the plan by default', async () => {
    const text = await run({});
    expect(text).not.toContain(NAME);
    expect(text).not.toContain(COMMENT);
    expect(text).not.toContain('Rosalind');
    expect(text).toContain('Xray_Review');
  });
  it('are written only when the box is ticked', async () => {
    const text = await run({ includeReviewers: true });
    expect(text).toContain(NAME);
    expect(text).toContain(COMMENT);
  });
  it('comments come from the newest change of each element', () => {
    const log = [
      { changes: [{ globalId: 'a', comment: 'old' }, { globalId: 'b', comment: 'b1' }] },
      { changes: [{ globalId: 'a', comment: 'new' }, { globalId: 'c' }] },
    ] as unknown as ReviewCommit[];
    expect([...reviewComments(log)]).toEqual([['a', 'new'], ['b', 'b1']]);
  });
});

describe('cleanup marks', () => {
  const model = { elements: [{ id: 0, globalId: 'G0' }, { id: 1, globalId: 'G1' }, { id: 2, globalId: 'G2' }] } as never;
  it('marks the ids cleanup hid, with the rules and reasons of its report', () => {
    const m = cleanupMarks([0, 2], model, [{ id: 0, globalId: 'G0', rules: ['tiny'], reasons: ['smaller than 5 cm'] }, { id: 1, globalId: 'G1', rules: ['strays'], reasons: ['far away'] }]);
    expect([...m.keys()]).toEqual(['G0', 'G2']);
    expect(m.get('G0')).toEqual({ rules: ['tiny'], reasons: ['smaller than 5 cm'] });
    expect(m.get('G2')!.rules).toEqual(['cleanup']); // the report no longer lists it
  });
  it('lands in Xray_Cleanup only with includeCleanupMarks', async () => {
    const c = CASES.find((x) => x.name === 'ports-ifc2x3.ifc')!;
    const blob = blobOf(c.path);
    const info = await sourceInfo(c.name, blob);
    const m = api.OpenModel(fileBytes(c.path));
    const all = api.GetAllLines(m);
    const elements: Array<{ id: number; expressId: number; globalId: string; file: string }> = [];
    for (let i = 0; i < all.size(); i++) {
      const id = all.get(i);
      if (api.IsIfcElement(api.GetLineType(m, id))) elements.push({ id: elements.length, expressId: id, globalId: api.GetLine(m, id).GlobalId.value as string, file: c.name });
    }
    api.CloseModel(m);
    const marks = cleanupMarks([0, 1], { elements } as never, [{ id: 0, globalId: elements[0]!.globalId, rules: ['tiny'], reasons: ['r'] }]);
    for (const on of [true, false]) {
      const o = { ...OPTS, includeCleanupMarks: on };
      const plans = planOf({ model: { elements } as never, sources: [{ ...info, blob }], results: [], schema: SCHEMA, options: o, cleanup: on ? marks : undefined });
      const [f] = await runSave(plans.map((plan) => ({ plan, blob })), SCHEMA, o);
      const text = await textOf(new Blob(f?.parts ?? []));
      expect(text.includes('FlaggedForRemoval'), `marks ${on}`).toBe(on);
      if (!on) expect(plans[0]!.elements.length).toBe(0);
    }
  });
});

describe('attach', () => {
  const c = CASES.find((x) => x.name === 'AC20-FZK-Haus.ifc')!;
  async function records(): Promise<Array<{ expressId: number; globalId: string; file: string }>> {
    const m = api.OpenModel(fileBytes(c.path));
    const all = api.GetAllLines(m);
    const out: Array<{ expressId: number; globalId: string; file: string }> = [];
    for (let i = 0; i < all.size(); i++) {
      const id = all.get(i);
      if (api.IsIfcElement(api.GetLineType(m, id))) out.push({ expressId: id, globalId: api.GetLine(m, id).GlobalId.value as string, file: c.name });
    }
    api.CloseModel(m);
    return out;
  }
  it('accepts the file the records came from and returns its saveInfo', async () => {
    const r = await checkAttach(blobOf(c.path), await records());
    expect(r.ok).toBe(true);
    expect(r.fraction).toBe(1);
    expect(r.info!.maxExpressId).toBe((await scanStep(blobOf(c.path))).maxExpressId);
  });
  it('accepts a saved copy of that file (our block in it)', async () => {
    const recs = await records();
    const blob = blobOf(c.path);
    const info = await sourceInfo(c.name, blob);
    const plans = planOf({ model: { elements: recs } as never, sources: [{ ...info, blob }], results: recs.map((e, i) => syntheticResult(e.globalId, i)), schema: SCHEMA, options: OPTS });
    const [f] = await runSave([{ plan: plans[0]!, blob }], SCHEMA, OPTS);
    const r = await checkAttach(new Blob(f!.parts), recs);
    expect(r.ok).toBe(true);
    expect(r.info!.blockBase).toBe(info.maxExpressId);
  });
  it('refuses another file', async () => {
    const r = await checkAttach(blobOf(PORTS), await records());
    expect(r.ok).toBe(false);
    expect(r.fraction).toBeLessThan(0.5);
  });
  it('refuses when no record has an express id', async () => {
    expect((await checkAttach(blobOf(c.path), [{ globalId: 'x' }])).ok).toBe(false);
  });
});

describe('the worker client', () => {
  const c = CASES.find((x) => x.name === 'mini-ifc4x3.ifc') ?? CASES[0]!;
  async function job() {
    const blob = blobOf(c.path);
    const info = await sourceInfo(c.name, blob);
    const m = api.OpenModel(fileBytes(c.path));
    const all = api.GetAllLines(m);
    const elements: Array<{ expressId: number; globalId: string; file: string }> = [];
    for (let i = 0; i < all.size(); i++) {
      const id = all.get(i);
      if (api.IsIfcElement(api.GetLineType(m, id))) elements.push({ expressId: id, globalId: api.GetLine(m, id).GlobalId.value as string, file: c.name });
    }
    api.CloseModel(m);
    const plans = planOf({ model: { elements } as never, sources: [{ ...info, blob }], results: elements.map((e, i) => syntheticResult(e.globalId, i)), schema: SCHEMA, options: OPTS });
    return [{ plan: plans[0]!, blob }];
  }
  it('falls back to the main thread when no worker can start, and reports progress', async () => {
    const seen: string[] = [];
    const r = await startSave(await job(), SCHEMA, OPTS, (p) => seen.push(p.phase)).promise;
    expect(r.mode).toBe('main');
    expect(r.files[0]!.outName).toBe(outputName(c.name));
    expect(seen).toContain('splice');
  });
  it('cancel rejects with SaveCancelled', async () => {
    const run = startSave(await job(), SCHEMA, OPTS, undefined, true);
    run.cancel();
    await expect(run.promise).rejects.toBeInstanceOf(SaveCancelled);
  });
  it('an unreadable source reports the browser error through the promise', async () => {
    const j = await job();
    const bad = { size: 100, slice: () => { throw Object.assign(new Error('gone'), { name: 'NotReadableError' }); } } as unknown as Blob;
    await expect(startSave([{ plan: j[0]!.plan, blob: bad }], SCHEMA, OPTS, undefined, true).promise).rejects.toMatchObject({ name: 'NotReadableError' });
  });
});
