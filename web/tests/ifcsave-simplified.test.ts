// T5b (experimental): body write-back. Every element with geometry gets its bounding box as a new body (viewer frame, with an origin shift),
// the output is re-read with web-ifc and the bounds, colour and element count must match; ifcopenshell finds no new errors.
import { execFileSync } from 'node:child_process';
import { existsSync, mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { beforeAll, describe, expect, it, vi } from 'vitest';
import type { IfcAPI } from 'web-ifc';
import { createIfcApi, extractIfc } from '../src/model/ifcRaw';
import { runClean } from '../src/ifcsave/clean';
import { lengthScaleOf } from '../src/ifcsave/meshRep';
import type { SimplifiedMesh } from '../src/ifcsave/meshRep';
import { planSave } from '../src/ifcsave/plan';
import { indexStep } from '../src/ifcsave/stepIndex';
import { SCHEMA, blobOf, bytesOf, fileBytes, fxIfc, latin1, modelIfc, sourceInfo, wasmPath } from './ifcsave-helpers';

vi.setConfig({ testTimeout: 180000 });
const OPTS = { includeReviewers: false, includeCleanupMarks: true, scope: 'all' as const };
const SHIFT: [number, number, number] = [10.5, -5.25, 3];
let api: IfcAPI;
beforeAll(async () => { api = await createIfcApi({ url: wasmPath }); }, 60000);

type B = [number, number, number, number, number, number];
async function boundsOf(bytes: Uint8Array): Promise<{ bounds: Map<number, B>; color: Map<number, string>; n: number }> {
  const raw = await extractIfc(api, bytes, 'f.ifc');
  const o = raw.origin ?? [0, 0, 0];
  const bounds = new Map<number, B>();
  const color = new Map<number, string>();
  for (const e of raw.elements) {
    const b: B = [Infinity, Infinity, Infinity, -Infinity, -Infinity, -Infinity];
    for (let v = 0; v < e.positions.length; v += 3) for (let k = 0; k < 3; k++) {
      const w = e.positions[v + k]! + o[k]!;
      b[k] = Math.min(b[k]!, w);
      b[k + 3] = Math.max(b[k + 3]!, w);
    }
    bounds.set(e.expressId, b);
    color.set(e.expressId, JSON.stringify(e.color?.map((c) => +c.toFixed(3))));
  }
  return { bounds, color, n: raw.elements.length };
}

/** A box over IFC world bounds, in the viewer frame of a model with origin shift SHIFT. */
function boxMesh(globalId: string, expressId: number, b: B): SimplifiedMesh {
  const corners: number[][] = [];
  for (const z of [b[2], b[5]]) for (const y of [b[1], b[4]]) for (const x of [b[0], b[3]]) corners.push([x - SHIFT[0], z - SHIFT[2], -(y - SHIFT[1])]);
  const tri = [0, 2, 1, 1, 2, 3, 4, 5, 6, 5, 7, 6, 0, 1, 5, 0, 5, 4, 2, 6, 7, 2, 7, 3, 0, 4, 6, 0, 6, 2, 1, 3, 7, 1, 7, 5];
  return { globalId, expressId, positions: Float32Array.from(corners.flat()), indices: Uint32Array.from(tri) };
}

const PY = `
import sys, json
import ifcopenshell, ifcopenshell.validate
f = ifcopenshell.open(sys.argv[1])
lg = ifcopenshell.validate.json_logger()
ifcopenshell.validate.validate(f, lg)
print(json.dumps({"errors": sorted({str(s.get("level")) + "|" + str(s.get("message")) for s in lg.statements})}))
`;
const HAVE = (() => { try { execFileSync('python3', ['-I', '-c', 'import ifcopenshell, ifcopenshell.validate'], { stdio: 'ignore' }); return true; } catch { return false; } })();
const validate = (f: string): string[] => JSON.parse(new TextDecoder().decode(execFileSync('python3', ['-I', '-c', PY, f], { maxBuffer: 1 << 28, timeout: 170000 }))).errors;

const CASES = [
  { name: 'voids-ifc4', path: fxIfc('voids-ifc4.ifc') },
  { name: 'voids-ifc2x3', path: fxIfc('voids-ifc2x3.ifc') },
  { name: 'ports-ifc4', path: fxIfc('ports-ifc4.ifc') },
  { name: 'props-mm-ifc4 (millimetres)', path: fxIfc('props-mm-ifc4.ifc') },
  { name: 'AC20-FZK-Haus', path: modelIfc('AC20-FZK-Haus.ifc') },
].filter((c) => existsSync(c.path));

describe('length unit', () => {
  it('reads metres per file unit', () => {
    const f = (p: string): number => { const b = fileBytes(p); return lengthScaleOf(indexStep(b), b); };
    expect(f(fxIfc('voids-ifc4.ifc'))).toBe(1);
    expect(f(fxIfc('props-mm-ifc4.ifc'))).toBe(0.001);
  });
});

describe.each(CASES)('simplified write-back: $name', ({ path }) => {
  it('new bodies land where the viewer mesh is; colour, count and validity survive', async () => {
    const orig = fileBytes(path);
    const before = await boundsOf(orig);
    const text0 = latin1(orig);
    const guid = (id: number): string => new RegExp(`#${id}=IFC\\w+\\('([^']+)'`).exec(text0)?.[1] ?? '';
    const meshes = [...before.bounds].map(([id, b]) => boxMesh(guid(id), id, b));
    const blob = blobOf(path);
    const info = await sourceInfo('f.ifc', blob);
    const [plan] = planSave({ elements: [] } as never, new Map(), SCHEMA, [info], OPTS);
    const [file] = await runClean([{ plan: plan!, blob, candidates: [], removeHostsAnyway: false, simplified: { meshes, shift: SHIFT } }], SCHEMA, OPTS, 'write');
    const g = file!.report.geometry!;
    expect(g.applied.length + g.skipped.length).toBe(meshes.length);
    expect(g.applied.length).toBeGreaterThan(0);
    const out = await bytesOf(new Blob(file!.parts));
    const after = await boundsOf(out);
    expect(after.n).toBe(before.n);
    let colourDiff = 0;
    for (const a of g.applied) {
      const b = after.bounds.get(a.expressId)!;
      const want = before.bounds.get(a.expressId)!;
      for (let k = 0; k < 6; k++) expect(Math.abs(b[k]! - want[k]!), `${a.expressId} axis ${k}`).toBeLessThan(0.001);
      for (let k = 0; k < 6; k++) expect(Math.abs(a.bounds[k]! - want[k]!)).toBeLessThan(1e-4);
      if (after.color.get(a.expressId) !== before.color.get(a.expressId)) colourDiff++;
    }
    // one style is kept per element (the first body item's): an element whose items carried several styles may show another colour
    expect(colourDiff / g.applied.length).toBeLessThanOrEqual(path.includes('FZK') ? 0.15 : 0);
    // the block holds no geometry: the new lines come before it, so a later Save IFC cannot take them away
    const t = latin1(out);
    expect(t.indexOf(g.applied.length ? (path.includes('2x3') ? 'IFCFACETEDBREP' : 'IFCTRIANGULATEDFACESET') : '@')).toBeLessThan(t.indexOf('XRAY-BEGIN'));
    const base = Number(/XRAY-BEGIN \S+ base=(\d+)/.exec(t)![1]);
    expect(base).toBeGreaterThan(indexStep(orig).maxId);
    if (!HAVE) return;
    const dir = mkdtempSync(join(tmpdir(), 'simp-'));
    const p = join(dir, 'o.ifc');
    writeFileSync(p, out);
    const was = validate(path);
    expect(validate(p).filter((e) => !was.includes(e))).toEqual([]);
  });
});
