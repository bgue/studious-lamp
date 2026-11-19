// ifcopenshell.validate on the original and the saved file: the saved error set must be a subset of the original's.
// Skipped with a notice when python3 or ifcopenshell is missing (same pattern as ifc-import-parity.test.ts).
import { execFileSync } from 'node:child_process';
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { beforeAll, describe, expect, it } from 'vitest';
import type { IfcAPI } from 'web-ifc';
import { createIfcApi } from '../src/model/ifcRaw';
import { emitAdditions } from '../src/ifcsave/additions';
import { planSave } from '../src/ifcsave/plan';
import { locateInsert, splice } from '../src/ifcsave/splice';
import { CASES, SCHEMA, blobOf, bytesOf, elementsOf, fileBytes, sameBytes, sourceInfo, syntheticResult, wasmPath } from './ifcsave-helpers';

const PY = `
import sys, json
import ifcopenshell, ifcopenshell.validate
f = ifcopenshell.open(sys.argv[1])
lg = ifcopenshell.validate.json_logger()
ifcopenshell.validate.validate(f, lg)
print(json.dumps({"schema": f.schema, "count": len(list(f)), "errors": sorted({str(s.get("level")) + "|" + str(s.get("message")) for s in lg.statements})}))
`;

function python(): boolean {
  try {
    execFileSync('python3', ['-I', '-c', 'import ifcopenshell, ifcopenshell.validate'], { stdio: 'ignore' });
    return true;
  } catch {
    return false;
  }
}
const HAVE = python();
if (!HAVE) console.warn('ifcsave-validate: python3 with ifcopenshell not found, validation skipped');

let api: IfcAPI;
beforeAll(async () => {
  api = await createIfcApi({ url: wasmPath });
}, 60000);

const run = (file: string): { schema: string; count: number; errors: string[] } => JSON.parse(new TextDecoder().decode(execFileSync('python3', ['-I', '-c', PY, file], { maxBuffer: 1 << 28, timeout: 120000 })));

describe.skipIf(!HAVE)('ifcopenshell.validate on saved files', () => {
  const dir = HAVE ? mkdtempSync(join(tmpdir(), 'ifcsave-')) : '';
  it.each(CASES)('$name: no new validation errors; entity count = original + added', async ({ name, path }) => {
    const blob = blobOf(path);
    const info = await sourceInfo(name, blob);
    const m = api.OpenModel(fileBytes(path));
    const els = elementsOf(api, m);
    api.CloseModel(m);
    const results = new Map(els.map((e, i) => [e.globalId, syntheticResult(e.globalId, i)]));
    const cleanup = new Map(els.filter((_, i) => i % 9 === 0).map((e) => [e.globalId, { rules: ['tiny'], reasons: ['too small'] }]));
    const o = { includeReviewers: true, includeCleanupMarks: true, scope: 'all' as const };
    const [plan] = planSave({ elements: els.map((e) => ({ ...e, file: name })) } as never, results, SCHEMA, [info], o, { cleanup, comments: new Map(els.map((e) => [e.globalId, 'check "this"; it’s odd'])) });
    const add = emitAdditions(plan!, SCHEMA, o);
    const saved = splice(blob, await locateInsert(blob), add.text);
    const out = join(dir, name);
    writeFileSync(out, await bytesOf(saved));
    const before = run(path);
    const after = run(out);
    expect(after.schema).toBe(before.schema);
    expect(after.count).toBe(before.count + add.lines);
    const known = new Set(before.errors);
    const fresh = after.errors.filter((e) => !known.has(e));
    expect(fresh).toEqual([]);
    // and a second save from the saved file stays clean
    const again = splice(saved, await locateInsert(saved), add.text);
    expect(sameBytes(await bytesOf(again), await bytesOf(saved))).toBe(true);
  }, 240000);
  it('cleans up', () => {
    rmSync(dir, { recursive: true, force: true });
  });
});
