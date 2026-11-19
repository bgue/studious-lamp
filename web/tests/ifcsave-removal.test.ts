// Cleaned copy (design 2.3, 2.4): each row of the removal table on the small fixtures, in IFC4 and IFC2X3. The output opens in web-ifc,
// the removed elements are gone, every other line is unchanged unless it was rewritten, no reference dangles, vetoes carry
// Xray_Cleanup.KeptBecause, ifcopenshell finds no new errors.
import { execFileSync } from 'node:child_process';
import { existsSync, mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { beforeAll, describe, expect, it, vi } from 'vitest';
import type { IfcAPI } from 'web-ifc';
import { createIfcApi } from '../src/model/ifcRaw';
import { emitAdditions } from '../src/ifcsave/additions';
import { cleanedName, runClean } from '../src/ifcsave/clean';
import type { CleanedFile } from '../src/ifcsave/clean';
import { planSave } from '../src/ifcsave/plan';
import { runSave } from '../src/ifcsave/run';
import { splice, locateInsert } from '../src/ifcsave/splice';
import { indexStep } from '../src/ifcsave/stepIndex';
import { scanStep } from '../src/ifcsave/stepScan';
import { argTexts, latin1Decode, planRemoval, refIds, trimRefs } from '../src/ifcsave/removal';
import { SCHEMA, blobOf, bytesOf, fileBytes, fxIfc, latin1, sourceInfo, syntheticResult, wasmPath } from './ifcsave-helpers';

vi.setConfig({ testTimeout: 120000 });

const OPTS = { includeReviewers: false, includeCleanupMarks: true, scope: 'all' as const, toolVersion: 'test' };
let api: IfcAPI;
beforeAll(async () => {
  api = await createIfcApi({ url: wasmPath });
}, 60000);

const STMT = /#(\d+)\s*=\s*([A-Z0-9_]+)\s*\(/g;
/** express id of the first line whose class is `cls` and whose Name argument is `name`. */
function idByName(text: string, name: string): number {
  const re = new RegExp(`#(\\d+)=IFC[A-Z0-9]+\\([^;]*?,'${name}'`, 'g');
  const m = re.exec(text);
  if (!m) throw new Error(`no line named ${name}`);
  return Number(m[1]);
}
/** All `#n` references of a text that point at no line (strings skipped). */
function dangling(text: string): string[] {
  const ids = new Set<number>();
  for (const m of text.matchAll(STMT)) ids.add(Number(m[1]));
  const bad: string[] = [];
  for (const m of text.replace(/'(?:[^']|'')*'/g, "''").matchAll(/#(\d+)(?!\d|\s*=)/g)) if (!ids.has(Number(m[1]))) bad.push(m[0]);
  return bad;
}
const linesOf = (text: string): Map<number, string> => {
  const out = new Map<number, string>();
  for (const m of text.matchAll(/#(\d+)\s*=[^;]*?(?:'(?:[^']|'')*'[^;]*?)*;/g)) out.set(Number(m[1]), m[0]);
  return out;
};

interface Run {
  file: CleanedFile;
  text: string;
  bytes: Uint8Array;
  orig: string;
  ids: Map<string, number>;
}

async function clean(path: string, names: string[], o: { hostsAnyway?: boolean; withClassification?: boolean; source?: Blob } = {}): Promise<Run> {
  const blob = o.source ?? blobOf(path);
  const text0 = latin1Decode(new Uint8Array(await blob.arrayBuffer()), 0, blob.size);
  const info = await sourceInfo('f.ifc', blob);
  const ids = new Map<string, number>();
  for (const n of names) ids.set(n, idByName(text0, n));
  const candidates = [...ids.entries()].map(([n, id]) => ({ expressId: id, globalId: `g-${n}`, rules: ['tiny'], reasons: ['test'] }));
  const [plan] = planSave({ elements: [] } as never, new Map(), SCHEMA, [info], OPTS);
  const [file] = await runClean([{ plan: plan!, blob, candidates, removeHostsAnyway: !!o.hostsAnyway }], SCHEMA, OPTS, 'write');
  const bytes = await bytesOf(new Blob(file!.parts));
  return { file: file!, text: latin1(bytes), bytes, orig: text0, ids };
}

function check(r: Run, label: string): void {
  // opens in web-ifc, line count = original - deleted + added
  const m = api.OpenModel(r.bytes);
  const count = api.GetAllLines(m).size();
  api.CloseModel(m);
  const origCount = (r.orig.match(/^#\d+\s*=/gm) ?? []).length;
  const outCount = (r.text.match(/^#\d+\s*=/gm) ?? []).length;
  expect(outCount, label).toBe(origCount - r.file.report.stats.linesDeleted - r.file.report.stats.blockLinesDropped + r.file.lines);
  expect(count, label).toBe(outCount);
  expect(dangling(r.text), label).toEqual([]);
  // every retained original line is unchanged unless rewritten
  const before = linesOf(r.orig);
  const after = linesOf(r.text);
  let changed = 0;
  for (const [id, t] of after) {
    const o = before.get(id);
    if (o === undefined) continue; // the new block
    if (o !== t) changed++;
  }
  expect(changed, label).toBe(r.file.report.stats.relationsTrimmed);
}

const FIXTURES = [
  { schema: 'IFC4', path: fxIfc('voids-ifc4.ifc') },
  { schema: 'IFC2X3', path: fxIfc('voids-ifc2x3.ifc') },
];
const PORTS = [
  { schema: 'IFC4', path: fxIfc('ports-ifc4.ifc') },
  { schema: 'IFC2X3', path: fxIfc('ports-ifc2x3.ifc') },
];

describe('text helpers', () => {
  it('trimRefs drops list members and leaves every other byte alone', () => {
    const s = "#5=IFCRELCONTAINEDINSPATIALSTRUCTURE('2lS;x',#2,'a, (b)',$,(#65, #19,#86),#16);";
    const t = trimRefs(s, (id) => id === 19);
    expect(t.text).toBe("#5=IFCRELCONTAINEDINSPATIALSTRUCTURE('2lS;x',#2,'a, (b)',$,(#65,#86),#16);");
    expect(t.changed).toBe(true);
    expect(t.single).toBe(false);
    expect(trimRefs(s, (id) => id === 16).single).toBe(true);
    expect(trimRefs("#5=IFCRELX('g',$,$,$,(#1),#2);", (id) => id === 1).emptied).toBe(true);
    expect(trimRefs(s, () => false).text).toBe(s);
  });
  it('argTexts and refIds ignore strings', () => {
    expect(argTexts("#1=IFCFOO('a,#9',#2,(#3,#4),$);")).toEqual(["'a,#9'", '#2', '(#3,#4)', '$']);
    expect(refIds("('#7',#8,#9)")).toEqual([8, 9]);
  });
});

describe('stepIndex', () => {
  it.each(FIXTURES)('$schema: rows, references and inverse references agree with the text', ({ path }) => {
    const bytes = fileBytes(path);
    const ix = indexStep(bytes);
    const text = latin1(bytes);
    expect(ix.count).toBe((text.match(/^#\d+\s*=/gm) ?? []).length);
    expect(ix.maxId).toBe(Math.max(...[...text.matchAll(/^#(\d+)\s*=/gm)].map((m) => Number(m[1]))));
    expect(ix.dataEnd).toBe(text.lastIndexOf('ENDSEC;'));
    for (let r = 0; r < ix.count; r += 7) {
      const s = latin1Decode(bytes, ix.offset[r]!, ix.offset[r]! + ix.length[r]!);
      expect(s.startsWith(`#${ix.id[r]}=`)).toBe(true);
      expect(s.endsWith(';')).toBe(true);
      const want = refIds(s.slice(s.indexOf('=') + 1)).filter((id) => ix.rowOf(id) >= 0).map((id) => ix.rowOf(id));
      expect([...ix.fwd.subarray(ix.fwdStart[r], ix.fwdStart[r + 1])]).toEqual(want);
      for (const t of want) expect([...ix.inv.subarray(ix.invStart[t], ix.invStart[t + 1])]).toContain(r);
    }
  });
});

describe.each(FIXTURES)('cleaned copy: voids ($schema)', ({ path, schema }) => {
  it('free-standing debris with its own property set: the element, its geometry and its property set go; neighbours are untouched', async () => {
    const r = await clean(path, ['Debris 1']);
    check(r, 'debris 1');
    const id = r.ids.get('Debris 1')!;
    expect(r.file.report.removed).toBe(1);
    expect(r.file.report.kept).toEqual([]);
    expect(r.orig).toContain(`#${id}=`);
    expect(r.text).not.toContain(`#${id}=`);
    expect(r.text).not.toContain("'Debris 1'");
    expect(r.text).not.toContain("'Acme_Debris'"); // the property set went in the orphan sweep
    expect(r.text).not.toContain("'stray'");
    expect(r.text).toContain("'Debris 2'");
    expect(r.file.report.stats.swept).toBeGreaterThan(5);
    expect(r.text).toMatch(/IFCRELCONTAINEDINSPATIALSTRUCTURE/);
  });

  it('a material shared with a remaining element stays', async () => {
    const r = await clean(path, ['Debris 2']);
    check(r, 'debris 2');
    expect(r.text).toContain("'Concrete C30'");
    expect(r.text).not.toContain("'Debris 2'");
    const rel = /IFCRELASSOCIATESMATERIAL\([^;]*;/.exec(r.text)![0];
    expect(rel).not.toContain(`#${r.ids.get('Debris 2')}`);
  });

  it('a door: its fill is cut and counted, its opening stays as a hole in the wall', async () => {
    const r = await clean(path, ['Door 1']);
    check(r, 'door');
    expect(r.file.report.stats.fillsCut).toBe(1);
    expect(r.file.report.kept).toEqual([]);
    expect(r.text).toContain("'Opening 1'");
    expect(r.text).not.toContain("'Door 1'");
    expect((r.text.match(/IFCRELFILLSELEMENT/g) ?? []).length).toBe(1);
  });

  it('a wall that still hosts a window is kept and marked (guard on)', async () => {
    const r = await clean(path, ['Wall A', 'Door 1']);
    check(r, 'host guard');
    expect(r.file.report.kept.map((k) => k.because)).toEqual(['hosts a door or window']);
    expect(r.file.report.removed).toBe(1); // the door
    expect(r.text).toContain("'Wall A'");
    expect(r.text).toContain("'Xray_Cleanup'");
    expect(r.text).toMatch(/'KeptBecause'/);
    expect(r.text).toContain("IFCLABEL('hosts a door or window')");
    expect(r.text).toContain('removed=1 kept=1');
    // the voids of the kept wall are intact
    expect((r.text.match(/IFCRELVOIDSELEMENT/g) ?? []).length).toBe(3);
  });

  it('a wall with all its fillers removed goes with its openings and their fills', async () => {
    const r = await clean(path, ['Wall A', 'Door 1', 'Window 1']);
    check(r, 'wall and fillers');
    expect(r.file.report.kept).toEqual([]);
    expect(r.file.report.removed).toBe(3);
    expect(r.file.report.cascaded).toBe(2);
    for (const n of ['Wall A', 'Door 1', 'Window 1', 'Opening 1', 'Opening 2']) expect(r.text).not.toContain(`'${n}'`);
    expect(r.text).toContain("'Wall B'");
    expect(r.text).toContain("'Opening 3'");
    expect((r.text.match(/IFCRELFILLSELEMENT/g) ?? []).length).toBe(0);
    expect((r.text.match(/IFCRELVOIDSELEMENT/g) ?? []).length).toBe(1);
    // the material the wall had stays for debris 2
    expect(r.text).toContain("'Concrete C30'");
  });

  it('"remove hosts anyway" lifts the guard: the window stands in no wall', async () => {
    const r = await clean(path, ['Wall A'], { hostsAnyway: true });
    check(r, 'hosts anyway');
    expect(r.file.report.kept).toEqual([]);
    expect(r.text).not.toContain("'Wall A'");
    expect(r.text).toContain("'Window 1'");
    expect(r.text).toContain("'Door 1'");
  });

  it('a wall whose opening has no filler goes with the opening', async () => {
    const r = await clean(path, ['Wall B']);
    check(r, 'wall b');
    expect(r.file.report.kept).toEqual([]);
    expect(r.file.report.cascaded).toBe(1);
    expect(r.text).not.toContain("'Opening 3'");
    expect(r.text).not.toContain("'Wall B'");
    expect((r.text.match(/IFCRELVOIDSELEMENT/g) ?? []).length).toBe(2);
  });

  it('an assembly with parts that stay is kept and marked; with all parts it goes; one part is trimmed out of the aggregate', async () => {
    const a = await clean(path, ['Assembly 1']);
    check(a, 'assembly only');
    expect(a.file.report.kept.map((k) => k.because)).toEqual(['has parts']);
    expect(a.text).toContain("'Assembly 1'");
    const b = await clean(path, ['Assembly 1', 'Part 1', 'Part 2']);
    check(b, 'assembly and parts');
    expect(b.file.report.kept).toEqual([]);
    for (const n of ['Assembly 1', 'Part 1', 'Part 2']) expect(b.text).not.toContain(`'${n}'`);
    const c = await clean(path, ['Part 1']);
    check(c, 'one part');
    expect(c.file.report.stats.relationsTrimmed).toBeGreaterThanOrEqual(1);
    const agg = [...c.text.matchAll(/IFCRELAGGREGATES\([^;]*;/g)].map((m) => m[0]).find((s) => s.includes(`#${c.ids.get('Part 1')}`) === false && s.includes(`#${indexIdOf(c.orig, 'Part 2')}`));
    expect(agg).toBeTruthy();
  });

  it('a bulk of unrelated elements in one pass, and the result is deterministic', async () => {
    const names = ['Debris 1', 'Debris 2', 'Free beam', 'Wall B', 'Door 1'];
    const a = await clean(path, names);
    const b = await clean(path, names);
    check(a, 'bulk');
    expect(a.bytes).toEqual(b.bytes);
    expect(a.file.report.removed).toBe(5);
  });

  it('ifcopenshell finds no new errors', async () => {
    if (!pythonOk()) return;
    const r = await clean(path, ['Debris 1', 'Door 1', 'Wall B', 'Assembly 1', 'Part 1', 'Part 2']);
    const dir = mkdtempSync(join(tmpdir(), 'ifcclean-'));
    const out = join(dir, `${schema}.cleaned.ifc`);
    writeFileSync(out, r.bytes);
    const before = validate(path);
    const after = validate(out);
    expect(after.errors.filter((e) => !before.errors.includes(e))).toEqual([]);
    expect(after.schema).toBe(before.schema);
  });
});

function indexIdOf(text: string, name: string): number {
  return idByName(text, name);
}

describe.each(PORTS)('cleaned copy: ports ($schema)', ({ path }) => {
  it('removing a duct element deletes its ports and their connections; the neighbour keeps its port', async () => {
    const text0 = latin1(fileBytes(path));
    const r = await clean(path, ['Duct 2']);
    check(r, 'ports');
    expect(r.file.report.kept).toEqual([]);
    expect(r.file.report.cascaded).toBeGreaterThanOrEqual(2);
    expect(r.text).not.toContain("'Duct 2'");
    const portsBefore = (text0.match(/IFCDISTRIBUTIONPORT/g) ?? []).length;
    const portsAfter = (r.text.match(/IFCDISTRIBUTIONPORT\(/g) ?? []).length;
    expect(portsAfter).toBeLessThan(portsBefore);
    expect(portsAfter).toBeGreaterThan(0);
    expect(r.text).toContain("'Duct 1'");
    expect(r.text).toContain("'Elbow'");
    const keptPorts = (r.text.match(/IFCRELCONNECTSPORTS\(/g) ?? []).length;
    expect(keptPorts).toBeLessThan((text0.match(/IFCRELCONNECTSPORTS\(/g) ?? []).length);
  });
});

describe('old Xray blocks', () => {
  const path = fxIfc('voids-ifc4.ifc');
  async function withBlock(): Promise<Blob> {
    const blob = blobOf(path);
    const info = await sourceInfo('f.ifc', blob);
    const text0 = latin1(fileBytes(path));
    const guids = new Map<number, string>();
    for (const m of text0.matchAll(/#(\d+)=IFC(?:WALL|DOOR|WINDOW|BUILDINGELEMENTPROXY|BEAM)\('([^']+)'/g)) guids.set(Number(m[1]), m[2]!);
    const els = [...guids].map(([expressId, globalId]) => ({ expressId, globalId, file: 'f.ifc' }));
    const results = new Map(els.map((e, i) => [e.globalId, syntheticResult(e.globalId, i)]));
    const cleanup = new Map([[els[0]!.globalId, { rules: ['tiny'], reasons: ['x'] }]]);
    const [plan] = planSave({ elements: els } as never, results, SCHEMA, [info], OPTS, { cleanup });
    const add = emitAdditions(plan!, SCHEMA, OPTS);
    return splice(blob, await locateInsert(blob), add.text);
  }

  it('an earlier block is dropped and written again, ids start at its base, nothing doubles', async () => {
    const saved = await withBlock();
    const base = (await scanStep(saved)).block!.base;
    const r = await clean(path, ['Debris 1'], { source: saved });
    expect(r.file.report.blockReplaced).toBe(true);
    expect(r.file.report.stats.blockLinesDropped).toBeGreaterThan(10);
    expect((r.text.match(/XRAY-BEGIN/g) ?? []).length).toBe(1);
    expect(r.text).toContain(`base=${base} `);
    expect(dangling(r.text)).toEqual([]);
    expect((r.text.match(/IFCPROPERTYSET\('[^']*',[^,]*,'Xray_Cleanup'/g) ?? []).length).toBe(0); // no marks: the plan holds none
    const m = api.OpenModel(r.bytes);
    api.CloseModel(m);
  });

  it('markers lost (another tool dropped the comments): the old lines are found by name and deleted, then the block is appended', async () => {
    const saved = await withBlock();
    const stripped = latin1(await bytesOf(saved)).replace(/\/\* XRAY-[^\n]*\*\/\n/g, '');
    const r = await clean(path, ['Debris 1'], { source: new Blob([stripped]) });
    expect(r.file.report.foreignXrayLines).toBeGreaterThan(0);
    expect(r.file.report.blockReplaced).toBe(false);
    expect(dangling(r.text)).toEqual([]);
    const ix = indexStep(r.bytes);
    expect(ix.ourNamedRows).toEqual([]);
    expect(ix.block).toBeTruthy();
    const orig = latin1(fileBytes(path));
    const lines = (t: string): number => (t.match(/^#\d+\s*=/gm) ?? []).length;
    // nothing of the old save is left: the cleaned copy holds the original minus debris 1 plus a block with no classification
    expect(lines(r.text)).toBeLessThan(lines(orig));
  });
});

describe('plain Save IFC of a file whose markers were lost', () => {
  it('the old Xray lines are taken out first: the saved file holds each property set once', async () => {
    const path = fxIfc('voids-ifc4.ifc');
    const blob0 = blobOf(path);
    const text0 = latin1(fileBytes(path));
    const guids = new Map<number, string>();
    for (const m of text0.matchAll(/#(\d+)=IFC(?:WALL|DOOR|WINDOW|BUILDINGELEMENTPROXY|BEAM)\('([^']+)'/g)) guids.set(Number(m[1]), m[2]!);
    const els = [...guids].map(([expressId, globalId]) => ({ expressId, globalId, file: 'f.ifc' }));
    const results = new Map(els.map((e, i) => [e.globalId, syntheticResult(e.globalId, i)]));
    const info = await sourceInfo('f.ifc', blob0);
    const [plan] = planSave({ elements: els } as never, results, SCHEMA, [info], OPTS);
    const [first] = await runSave([{ plan: plan!, blob: blob0 }], SCHEMA, OPTS);
    const saved = new Blob(first!.parts);
    const stripped = new Blob([latin1(await bytesOf(saved)).replace(/\/\* XRAY-[^\n]*\*\/\n/g, '')]);
    const info2 = await sourceInfo('f.ifc', stripped);
    const [plan2] = planSave({ elements: els } as never, results, SCHEMA, [info2], OPTS);
    const [second] = await runSave([{ plan: plan2!, blob: stripped }], SCHEMA, OPTS);
    const out = latin1(await bytesOf(new Blob(second!.parts)));
    const count = (t: string, re: RegExp): number => (t.match(re) ?? []).length;
    expect(count(out, /IFCPROPERTYSET\('[^']*',[^,]*,'XR_Classification'/g)).toBe(count(latin1(await bytesOf(saved)), /IFCPROPERTYSET\('[^']*',[^,]*,'XR_Classification'/g));
    expect(count(out, /IFCPROPERTYSET\('[^']*',[^,]*,'XR_Classification'/g)).toBeGreaterThan(0);
    expect(count(out, /XRAY-BEGIN/g)).toBe(1);
    expect(dangling(out)).toEqual([]);
    const m = api.OpenModel(new Uint8Array(await new Blob(second!.parts).arrayBuffer()));
    api.CloseModel(m);
  });
});

describe('guards on bad input', () => {
  it('ids the file does not have are counted; spatial elements are never removed', () => {
    const bytes = fileBytes(fxIfc('voids-ifc4.ifc'));
    const ix = indexStep(bytes);
    const storey = [...Array(ix.count).keys()].find((r) => ix.typeOf(r) === 'IFCBUILDINGSTOREY')!;
    const p = planRemoval(ix, bytes, [999999, ix.id[storey]!], { removeHostsAnyway: false });
    expect(p.stats.missing).toBe(1);
    expect(p.kept[0]!.because).toMatch(/spatial/);
    expect(p.delete.size).toBe(0);
  });
  it('cleanedName', () => {
    expect(cleanedName('A.ifc')).toBe('A.cleaned.ifc');
    expect(cleanedName('A.xray.ifc')).toBe('A.cleaned.ifc');
    expect(cleanedName('A.cleaned.ifc')).toBe('A.cleaned.ifc');
  });
});

// ---------------------------------------------------------------- ifcopenshell

const PY = `
import sys, json
import ifcopenshell, ifcopenshell.validate
f = ifcopenshell.open(sys.argv[1])
lg = ifcopenshell.validate.json_logger()
ifcopenshell.validate.validate(f, lg)
print(json.dumps({"schema": f.schema, "count": len(list(f)), "errors": sorted({str(s.get("level")) + "|" + str(s.get("message")) for s in lg.statements})}))
`;
let py: boolean | null = null;
function pythonOk(): boolean {
  if (py === null) {
    try {
      execFileSync('python3', ['-I', '-c', 'import ifcopenshell, ifcopenshell.validate'], { stdio: 'ignore' });
      py = true;
    } catch {
      py = false;
      console.warn('ifcsave-removal: python3 with ifcopenshell not found, validation skipped');
    }
  }
  return py;
}
function validate(file: string): { schema: string; count: number; errors: string[] } {
  return JSON.parse(new TextDecoder().decode(execFileSync('python3', ['-I', '-c', PY, file], { maxBuffer: 1 << 28, timeout: 120000 })));
}
void existsSync;
