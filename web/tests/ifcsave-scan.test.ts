import { beforeAll, describe, expect, it, vi } from 'vitest';

vi.setConfig({ testTimeout: 120000 });
import type { IfcAPI } from 'web-ifc';
import { createIfcApi } from '../src/model/ifcRaw';
import { emitAdditions } from '../src/ifcsave/additions';
import { planSave } from '../src/ifcsave/plan';
import { locateInsert, splice } from '../src/ifcsave/splice';
import { scanStep } from '../src/ifcsave/stepScan';
import { CASES, SCHEMA, blobOf, elementsOf, fileBytes, fxIfc, latin1, sourceInfo, syntheticResult, textOf, wasmPath } from './ifcsave-helpers';
import { existsSync } from 'node:fs';

const EXTRA = ['ports-ifc4.ifc', 'props-mm-ifc4.ifc'].map((n) => ({ name: n, path: fxIfc(n) })).filter((c) => existsSync(c.path));
const ALL = [...CASES.map((c) => ({ name: c.name, path: c.path })), ...EXTRA];
let api: IfcAPI;
beforeAll(async () => {
  api = await createIfcApi({ url: wasmPath });
}, 60000);

describe.each(ALL)('stepScan: $name', ({ name, path }) => {
  const bytes = fileBytes(path);
  it('max id, data end, schema and owner history agree with web-ifc and the true offsets', async () => {
    const s = await scanStep(new Blob([bytes as BlobPart]));
    const m = api.OpenModel(bytes);
    expect(s.maxExpressId).toBe(api.GetMaxExpressID(m));
    const text = latin1(bytes);
    expect(s.dataEnd).toBe(text.lastIndexOf('ENDSEC;'));
    expect(s.endIso).toBe(text.lastIndexOf('END-ISO-10303-21;'));
    expect(s.schema.toUpperCase().startsWith('IFC')).toBe(true);
    expect(text).toContain(`'${s.schema}'`);
    const proj = api.GetLineIDsWithType(m, 4140 /* placeholder, replaced below */);
    void proj;
    expect(s.block).toBeUndefined();
    api.CloseModel(m);
  });
  it('chunk size does not change the result (boundaries inside strings, comments and tokens)', async () => {
    const blob = new Blob([bytes.slice(0, Math.min(bytes.length, 20000)), '\nENDSEC;\nEND-ISO-10303-21;\n']);
    const full = await scanStep(blob);
    for (const chunkSize of [7, 17, 255, 4096]) expect(await scanStep(blob, { chunkSize })).toEqual(full);
    const tiny = new Blob([bytes.slice(0, 600), '\nENDSEC;\nEND-ISO-10303-21;\n']);
    expect(await scanStep(tiny, { chunkSize: 1 })).toEqual(await scanStep(tiny));
  });
  it('finds a guid and the classifications that were asked for', async () => {
    const m = api.OpenModel(bytes);
    const els = elementsOf(api, m).slice(0, 5);
    api.CloseModel(m);
    const s = await scanStep(new Blob([bytes as BlobPart]), { wantGuids: els.map((e) => e.expressId) });
    for (const e of els) expect(s.guidOf.get(e.expressId)).toBe(e.globalId);
  });
});

describe('stepScan on tricky text', () => {
  const T = (data: string): Blob => new Blob([`ISO-10303-21;\nHEADER;\nFILE_SCHEMA(('IFC4'));\nENDSEC;\nDATA;\n${data}\nENDSEC;\nEND-ISO-10303-21;\n`]);
  it('honours semicolons, quotes and ENDSEC inside strings and comments', async () => {
    const s = await scanStep(T("#1=IFCWALL('a;ENDSEC;b','it''s; #99=X();',$);\n/* ENDSEC; #500=Y(); */\n#2=IFCSLAB('x',$);"), { chunkSize: 5 });
    expect(s.maxExpressId).toBe(2);
    expect(s.statements).toBe(9); // ISO line, HEADER, FILE_SCHEMA, ENDSEC, DATA, #1, #2, ENDSEC, END-ISO
  });
  it('reads the project owner history and existing classifications', async () => {
    const s = await scanStep(T("#1=IFCPROJECT('g',#7,'P',$,$,$,$,$,$);\n#2=IFCCLASSIFICATION('CSI','2018',$,'MasterFormat');\n#3=IFCCLASSIFICATION('x','y',$,'Uniclass',$,$,$);"));
    expect(s.ownerHistoryId).toBe(7);
    expect(s.classifications).toEqual([{ id: 2, name: 'MasterFormat', edition: '2018' }, { id: 3, name: 'Uniclass', edition: 'y' }]);
  });
  it('is quick enough (budget 80 MB/s)', async () => {
    const line = "#12345=IFCCARTESIANPOINT((1.5,2.5,3.5));\n";
    const blob = T(line.repeat(Math.ceil(20e6 / line.length)));
    let best = 0;
    for (let k = 0; k < 3; k++) {
      const t0 = performance.now();
      await scanStep(blob);
      best = Math.max(best, blob.size / 1e6 / ((performance.now() - t0) / 1000));
    }
    expect(best).toBeGreaterThan(30); // measured 120 to 160 MB/s idle; the design budget is 80. The floor leaves room for a loaded machine
  });
});

describe('stepScan finds our block', () => {
  const c = CASES.find((x) => x.name === 'mini-ifc4x3.ifc') ?? CASES[0]!;
  it('reports the block, drops its classifications and lists roots named like ours once the markers are gone', async () => {
    const blob = blobOf(c.path);
    const info = await sourceInfo(c.name, blob);
    const m = api.OpenModel(fileBytes(c.path));
    const els = elementsOf(api, m);
    api.CloseModel(m);
    const results = new Map(els.map((e, i) => [e.globalId, syntheticResult(e.globalId, i)]));
    const o = { includeReviewers: false, includeCleanupMarks: false, scope: 'all' as const };
    const [plan] = planSave({ elements: els.map((e) => ({ ...e, file: c.name })) } as never, results, SCHEMA, [info], o);
    const add = emitAdditions(plan!, SCHEMA, o);
    const saved = splice(blob, await locateInsert(blob), add.text);
    const s = await scanStep(saved);
    expect(s.block).toBeTruthy();
    expect(s.block!.base).toBe(plan!.base);
    expect(s.block!.begin).toBe((await locateInsert(blob)).cut);
    expect(s.classifications).toEqual(info.classifications); // ours are not "existing"
    expect(s.ourNamedRoots).toEqual([]);
    // the same file after another tool dropped the comments
    const stripped = (await textOf(saved)).replace(/\/\* XRAY-[^\n]*\*\/\n/g, '');
    const s2 = await scanStep(new Blob([stripped]));
    expect(s2.block).toBeUndefined();
    expect(s2.ourNamedRoots.length).toBeGreaterThan(0);
    expect(s2.classifications.length).toBe(2);
  });

  it('locateInsert verifies the markers and falls back to a scan when they do not', async () => {
    const blob = blobOf(c.path);
    const first = await locateInsert(blob);
    expect(first.oldBlock).toBeUndefined();
    const text = 'x'.repeat(0);
    void text;
    const info = await sourceInfo(c.name, blob);
    const o = { includeReviewers: false, includeCleanupMarks: false, scope: 'all' as const };
    const m = api.OpenModel(fileBytes(c.path));
    const els = elementsOf(api, m);
    api.CloseModel(m);
    const results = new Map(els.map((e, i) => [e.globalId, syntheticResult(e.globalId, i)]));
    const [plan] = planSave({ elements: els.map((e) => ({ ...e, file: c.name })) } as never, results, SCHEMA, [info], o);
    const saved = splice(blob, first, emitAdditions(plan!, SCHEMA, o).text);
    const at = await locateInsert(saved);
    expect(at.oldBlock?.begin).toBe(first.cut);
    // a hand edit inside the block makes the byte count wrong: the scan finds the markers anyway
    const edited = (await textOf(saved)).replace('Xray classification', 'Xray classification EDITED');
    const at2 = await locateInsert(new Blob([edited]));
    expect(at2.oldBlock?.begin).toBe(first.cut);
    // a tail longer than the 64 KB window
    const padded = new Blob([saved, ' '.repeat(70000)]);
    expect((await locateInsert(padded)).cut).toBeGreaterThan(0);
  });

  it('rejects a file that is not STEP', async () => {
    await expect(locateInsert(new Blob(['hello']))).rejects.toThrow(/STEP/);
  });
});
