// A cleaned FZK-Haus with 20 random non-host elements removed re-opens in web-ifc and in ifcopenshell, and its validation error set is a
// subset of the original's (design section 7, T5 acceptance).
import { execFileSync } from 'node:child_process';
import { existsSync, mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { beforeAll, describe, expect, it, vi } from 'vitest';
import type { IfcAPI } from 'web-ifc';
import { createIfcApi } from '../src/model/ifcRaw';
import { runClean } from '../src/ifcsave/clean';
import { planSave } from '../src/ifcsave/plan';
import { argTexts, latin1Decode, refIds } from '../src/ifcsave/removal';
import { indexStep } from '../src/ifcsave/stepIndex';
import { SCHEMA, blobOf, bytesOf, elementsOf, fileBytes, modelIfc, sourceInfo, wasmPath } from './ifcsave-helpers';

vi.setConfig({ testTimeout: 180000 });
const FZK = modelIfc('AC20-FZK-Haus.ifc');
let api: IfcAPI;
beforeAll(async () => {
  api = await createIfcApi({ url: wasmPath });
}, 60000);

const PY = `
import sys, json
import ifcopenshell, ifcopenshell.validate
f = ifcopenshell.open(sys.argv[1])
lg = ifcopenshell.validate.json_logger()
ifcopenshell.validate.validate(f, lg)
print(json.dumps({"schema": f.schema, "count": len(list(f)), "elements": len(f.by_type("IfcElement")), "errors": sorted({str(s.get("level")) + "|" + str(s.get("message")) for s in lg.statements})}))
`;
const HAVE = (() => {
  try { execFileSync('python3', ['-I', '-c', 'import ifcopenshell, ifcopenshell.validate'], { stdio: 'ignore' }); return true; } catch { return false; }
})();
if (!HAVE) console.warn('ifcsave-removal-fzk: python3 with ifcopenshell not found, validation skipped');
const validate = (file: string): { schema: string; count: number; elements: number; errors: string[] } =>
  JSON.parse(new TextDecoder().decode(execFileSync('python3', ['-I', '-c', PY, file], { maxBuffer: 1 << 28, timeout: 170000 })));

/** mulberry32 */
function rng(seed: number): () => number {
  return () => {
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

describe.skipIf(!existsSync(FZK))('cleaned FZK-Haus', () => {
  it('20 random non-host elements removed: re-opens in web-ifc and ifcopenshell, errors are a subset of the original', async () => {
    const bytes = fileBytes(FZK);
    const m0 = api.OpenModel(bytes);
    const els = elementsOf(api, m0);
    const guidsBefore = new Set(els.map((e) => e.globalId));
    api.CloseModel(m0);
    const ix = indexStep(bytes);
    const hosts = new Set<number>();
    for (let r = 0; r < ix.count; r++) {
      if (ix.typeOf(r) !== 'IFCRELVOIDSELEMENT') continue;
      hosts.add(refIds(argTexts(latin1Decode(bytes, ix.offset[r]!, ix.offset[r]! + ix.length[r]!))[4]!)[0]!);
    }
    const pool = els.filter((e) => !hosts.has(e.expressId));
    const rand = rng(7);
    const picked: typeof els = [];
    while (picked.length < 20 && pool.length) picked.push(pool.splice(Math.floor(rand() * pool.length), 1)[0]!);
    expect(picked.length).toBe(20);

    const blob = blobOf(FZK);
    const info = await sourceInfo('f.ifc', blob);
    const [plan] = planSave({ elements: [] } as never, new Map(), SCHEMA, [info], { includeReviewers: false, includeCleanupMarks: true, scope: 'all' });
    const candidates = picked.map((e) => ({ expressId: e.expressId, globalId: e.globalId, rules: ['tiny'], reasons: ['test'] }));
    const [file] = await runClean([{ plan: plan!, blob, candidates, removeHostsAnyway: false }], SCHEMA, { includeReviewers: false, includeCleanupMarks: true, scope: 'all' }, 'write');
    const out = await bytesOf(new Blob(file!.parts));
    // kept ones (a part of an assembly, say) are allowed; everything removed is really gone
    const m1 = api.OpenModel(out);
    const after = elementsOf(api, m1);
    api.CloseModel(m1);
    const guidsAfter = new Set(after.map((e) => e.globalId));
    const removedGuids = picked.filter((e) => !file!.report.kept.some((k) => k.expressId === e.expressId)).map((e) => e.globalId);
    for (const g of removedGuids) expect(guidsAfter.has(g)).toBe(false);
    for (const g of guidsBefore) if (!removedGuids.includes(g)) expect(guidsAfter.has(g), g).toBe(true);
    expect(after.length).toBe(els.length - file!.report.removed - file!.report.cascaded);
    expect(file!.report.removed + file!.report.kept.length).toBe(20);
    if (!HAVE) return;
    const dir = mkdtempSync(join(tmpdir(), 'fzkclean-'));
    const path = join(dir, 'fzk.cleaned.ifc');
    writeFileSync(path, out);
    const before = validate(FZK);
    const afterV = validate(path);
    expect(afterV.errors.filter((e) => !before.errors.includes(e))).toEqual([]);
    const dropped = before.elements - afterV.elements; // ifcopenshell's IfcElement does not cover everything web-ifc lists (spaces, grids)
    expect(dropped).toBeGreaterThan(0);
    expect(dropped).toBeLessThanOrEqual(file!.report.removed + file!.report.cascaded);
    expect(file!.bytes).toBeLessThan(bytes.length);
  });
});
