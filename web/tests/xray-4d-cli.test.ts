// The xray-4d pipeline commands on the FZK-Haus sample: link (coverage, report, native re-link), plan (shape), IFC 4D write-back
// (re-opened with web-ifc), idempotent re-write, IFC2X3 skip, and a guarded render (Playwright + the single-file template).
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest';
import type { IfcAPI } from 'web-ifc';
import { createIfcApi } from '../src/model/ifcRaw';
import { workScheduleSkipReason } from '../src/ifcsave/writeWorkSchedule';
import { readNativeTasks } from '../src/ifcsave/nativeTasks';
import { emitWorkSchedule } from '../src/ifcsave/workSchedule';
import type { FourDLinks, FourDPlan } from '../src/schedule/types';
import { modelIfc, sameBytes, wasmPath, web } from './ifcsave-helpers';
// @ts-expect-error plain .mjs without types
import { run } from '../tools/xray-4d.mjs';

vi.setConfig({ testTimeout: 240000 });
const FZK = modelIfc('AC20-FZK-Haus.ifc');
const XER = resolve(web, 'public/samples/fzk-haus.xer');
const CFG = resolve(web, 'public/samples/fzk-haus.4d.json');
const dir = mkdtempSync(join(tmpdir(), 'xray-4d-cli-'));
const p = (n: string): string => join(dir, n);
afterAll(() => rmSync(dir, { recursive: true, force: true }));

async function cli(argv: string[]): Promise<{ code: number; out: string; err: string }> {
  let out = '';
  let err = '';
  const code = (await run(argv, { out: (s: string) => (out += s + '\n'), err: (s: string) => (err += s + '\n') })) as number;
  return { code, out, err };
}
const json = <T>(f: string): T => JSON.parse(readFileSync(f, 'utf8')) as T;

describe('xray-4d link and plan on FZK-Haus', () => {
  it('help and usage errors', async () => {
    expect((await cli(['link', '--help'])).out).toContain('--min-coverage');
    expect((await cli(['link'])).code).toBe(2);
    expect((await cli(['link', FZK, XER])).code).toBe(2);
    expect((await cli(['link', FZK, XER, '--config', 'x.yaml', '-o', p('x.json')])).code).toBe(3);
    expect((await cli(['plan', FZK, XER, p('nolinks.json'), '--config', CFG])).code).toBe(3);
    expect((await cli(['script'])).code).toBe(2);
  });

  it('links every element (coverage 100 %) and writes links.json, report.html and the IFC copy', async () => {
    const r = await cli(['link', FZK, XER, '--config', CFG, '-o', p('links.json'), '--report', p('report.html'), '--write-ifc', p('w.ifc'), '--min-coverage', '1']);
    expect(r.err).toContain('elements 100.0 %');
    expect(r.code).toBe(0);
    const links = json<FourDLinks>(p('links.json'));
    const linked = new Set(links.links!.filter((l) => l.status === 'accepted' && l.role === 'build').flatMap((l) => l.elements));
    expect(linked.size).toBe(82);
    expect(readFileSync(p('report.html'), 'utf8')).toContain('<table');
  });

  it('exits 4 when the coverage is below --min-coverage (files still written)', async () => {
    const cfg = json<Record<string, any>>(CFG);
    cfg.schedule = { ...cfg.schedule, location: [{ code: 'Nope' }], trade: [{ code: 'Nope' }] };
    cfg.tradeQueries = {};
    writeFileSync(p('empty.4d.json'), JSON.stringify(cfg));
    const r = await cli(['link', FZK, XER, '--config', p('empty.4d.json'), '-o', p('low.json'), '--min-coverage', '0.9']);
    expect(r.code).toBe(4);
    expect(existsSync(p('low.json'))).toBe(true);
  });

  it('plans: a valid plan shape in the views and --length / --pace', async () => {
    const r = await cli(['plan', FZK, XER, p('links.json'), '--config', CFG, '--view', 'actual', '--length', '30s', '--window', 'all', '-o', p('build.4d.json')]);
    expect(r.code).toBe(0);
    const plan = json<FourDPlan>(p('build.4d.json'));
    expect(plan.schema).toBe('xray-4d-plan/1');
    expect(plan.style.view).toBe('actual');
    expect(plan.elements.length).toBe(82);
    for (const e of plan.elements) {
      expect(typeof e.globalId).toBe('string');
      for (const i of e.intervals) expect(i.to).toBeGreaterThanOrEqual(i.from);
    }
    for (const t of plan.tasks) expect(['code', 'name', 'start', 'end', 'critical', 'milestone', 'elements'].every((k) => k in t)).toBe(true);
    expect(plan.window.to).toBeGreaterThan(plan.window.from);
    expect(plan.timeMap[plan.timeMap.length - 1]![1]).toBeCloseTo(30, 0);
    for (let i = 1; i < plan.timeMap.length; i++) expect(plan.timeMap[i]![1]).toBeGreaterThanOrEqual(plan.timeMap[i - 1]![1]);
    expect((await cli(['plan', FZK, XER, p('links.json'), '--config', CFG, '--length', '9s', '--pace', '1w=2s'])).code).toBe(2);
    expect((await cli(['plan', FZK, XER, p('links.json'), '--config', CFG, '--window', 'bogus'])).code).toBe(2);
    const look = await cli(['plan', FZK, XER, p('links.json'), '--config', CFG, '--window', 'lookahead:6w', '--pace', '1w=2s', '-o', p('look.4d.json')]);
    expect(look.code).toBe(0);
    const lp = json<FourDPlan>(p('look.4d.json'));
    expect(lp.window.to - lp.window.from).toBe(6 * 7 * 86400000);
    expect(lp.timeMap[lp.timeMap.length - 1]![1]).toBeGreaterThanOrEqual(12); // 42 days at 3.5 days per second, plus milestone holds
  });
});

describe('IFC 4D write-back', () => {
  let api: IfcAPI;
  beforeAll(async () => { api = await createIfcApi({ url: wasmPath }); }, 60000);

  it('writes IfcWorkSchedule, IfcTask, IfcTaskTime and assignments that web-ifc reads back with the right GlobalIds', async () => {
    const links = json<FourDLinks>(p('links.json'));
    const bytes = new Uint8Array(readFileSync(p('w.ifc')));
    const orig = new Uint8Array(readFileSync(FZK));
    // append-only: everything before the insert point is the original
    expect(sameBytes(bytes.subarray(0, 200000), orig.subarray(0, 200000))).toBe(true);
    const text = new TextDecoder('latin1').decode(bytes.subarray(bytes.length - 60000));
    expect(text).toContain('XRAY-4D-BEGIN');
    const m = api.OpenModel(bytes);
    try {
      const type = (n: string): number => api.GetTypeCodeFromName(n);
      const tasks = api.GetLineIDsWithType(m, type('IFCTASK'));
      expect(tasks.size()).toBe(15);
      const byCode = new Map<string, any>();
      for (let i = 0; i < tasks.size(); i++) {
        const t = api.GetLine(m, tasks.get(i), true);
        byCode.set(t.Identification.value, t);
      }
      const ws = api.GetLineIDsWithType(m, type('IFCWORKSCHEDULE'));
      expect(ws.size()).toBe(1);
      expect(api.GetLine(m, ws.get(0)).Name.value).toBe('Xray 4D');
      const sample = links.links!.find((l) => l.status === 'accepted' && l.role === 'build')!;
      const task = byCode.get(sample.activity);
      expect(task.PredefinedType.value).toBe('CONSTRUCTION');
      expect(task.TaskTime.ScheduleStart.value).toMatch(/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d$/);
      expect(task.TaskTime.ScheduleFinish.value >= task.TaskTime.ScheduleStart.value).toBe(true);
      // build role: IfcRelAssignsToProduct, RelatingProduct = the element, RelatedObjects = [task]
      const rels = api.GetLineIDsWithType(m, type('IFCRELASSIGNSTOPRODUCT'));
      const seen = new Set<string>();
      for (let i = 0; i < rels.size(); i++) {
        const r = api.GetLine(m, rels.get(i), true);
        if (r.RelatedObjects.some((o: any) => o.Identification?.value === sample.activity)) seen.add(r.RelatingProduct.GlobalId.value);
      }
      expect([...seen].sort()).toEqual([...sample.elements].sort());
      expect(api.GetLineIDsWithType(m, type('IFCRELSEQUENCE')).size()).toBe(15);
    } finally {
      api.CloseModel(m);
    }
  });

  it('is idempotent: writing the written file again gives the same bytes; other Xray sets of an old block stay', async () => {
    const r = await cli(['link', p('w.ifc'), XER, '--config', CFG, '-o', p('links2.json'), '--write-ifc', p('w2.ifc')]);
    expect(r.code).toBe(0);
    expect(r.err).toContain('native IFC 4D: 15 tasks');
    expect(r.err).toContain('earlier XRAY block replaced');
    expect(sameBytes(new Uint8Array(readFileSync(p('w2.ifc'))), new Uint8Array(readFileSync(p('w.ifc'))))).toBe(true);
  });

  it('re-links natively with confidence 1', () => {
    const links = json<FourDLinks>(p('links2.json'));
    const build = links.links!.filter((l) => l.status === 'accepted' && l.role === 'build');
    expect(build.length).toBe(15);
    for (const l of build) {
      expect(l.source).toBe('native');
      expect(l.confidence).toBe(1);
    }
    const a = new Set(json<FourDLinks>(p('links.json')).links!.filter((l) => l.status === 'accepted').flatMap((l) => l.elements));
    expect(new Set(build.flatMap((l) => l.elements))).toEqual(a);
  });

  it('reads remove tasks and both assignment forms; IFC2X3 is skipped', () => {
    const text = [
      "#1=IFCTASK('g1',$,'Demo',$,$,'D100',$,$,$,.F.,$,$,.DEMOLITION.);",
      "#2=IFCTASK('g2',$,'Build',$,$,'B100',$,$,$,.F.,$,$,.CONSTRUCTION.);",
      "#3=IFCRELASSIGNSTOPROCESS('g3',$,$,$,(#10,#11),$,#1,$);",
      "#4=IFCRELASSIGNSTOPROCESS('g4',$,$,$,(#12),$,#2,$);",
      "#5=IFCRELASSIGNSTOPRODUCT('g5',$,$,$,(#2),$,#13);",
    ].join('\n');
    const n = readNativeTasks(text, new Map([[10, 'A'], [11, 'B'], [12, 'C'], [13, 'D']]));
    expect(n.remove.get('A')).toEqual(['D100']);
    expect(n.native.get('C')).toEqual(['B100']);
    expect(n.native.get('D')).toEqual(['B100']);
    expect(workScheduleSkipReason('IFC2X3')).toMatch(/IFC2X3/);
    expect(workScheduleSkipReason('IFC4X3_ADD2')).toBeNull();
    const { lines } = emitWorkSchedule({ name: 'Xray 4D', project: 'P', created: '2027-01-01T00:00:00', start: '2027-01-01T00:00:00', finish: '2027-01-02T00:00:00', kind: 'PLANNED', tasks: [{ key: 'A|remove', code: 'A', name: 'A', milestone: false, predefined: 'DEMOLITION', elements: [5] }], sequences: [] }, 100);
    expect(lines.some((l) => l.includes('IFCRELASSIGNSTOPROCESS'))).toBe(true);
    expect(lines.some((l) => l.includes('IFCRELASSIGNSTOPRODUCT'))).toBe(false);
  });
});

describe('xray-4d pack', () => {
  it('writes a kiosk page that registers the plan and autoplays it (loop)', async () => {
    const r = await cli(['pack', FZK, p('build.4d.json'), '--loop', '-o', p('film.html')]);
    expect(r.code).toBe(0);
    const html = readFileSync(p('film.html'), 'utf8');
    expect(html).toContain('"plans":{"build":{"schema":"xray-4d-plan/1"');
    expect(html).toContain('"autoplay":{"plan":"build","loop":true}');
    expect((await cli(['pack', FZK, p('build.4d.json')])).code).toBe(2);
    expect((await cli(['pack', FZK, p('links.json'), '-o', p('bad.html')])).code).toBe(3);
  });
});

// ---- render: Playwright and the single-file template are needed (skipped otherwise)
function playwright(): { chromium: { executablePath(): string } } | null {
  const req = createRequire(import.meta.url);
  for (const c of [process.env.PLAYWRIGHT_MODULE, resolve(web, 'node_modules/playwright'), '/opt/node-tools/node_modules/playwright', '/opt/node22/lib/node_modules/playwright'].filter(Boolean) as string[]) {
    try { return req(c); } catch { /* next */ }
  }
  return null;
}
const pw = playwright();
let chromiumOk = false;
try { chromiumOk = !!pw && existsSync(pw.chromium.executablePath()); } catch { /* no browser */ }
const haveTemplate = existsSync(resolve(web, 'dist-single/xray-template.html')) || existsSync(resolve(web, 'dist-single/xray-viewer.html'));

describe.skipIf(!chromiumOk || !haveTemplate)('xray-4d render (Playwright + single-file build)', () => {
  it('renders 2 s at 320x180 / 12 fps: an mp4 or webm with 24 frames', async () => {
    const plan = await cli(['plan', FZK, XER, p('links.json'), '--config', CFG, '--length', '2s', '-o', p('short.4d.json')]);
    expect(plan.code).toBe(0);
    const r = await cli(['render', FZK, p('short.4d.json'), '--size', '320x180', '--fps', '12', '-o', p('short.mp4')]);
    expect(r.code).toBe(0);
    const res = JSON.parse(r.out.trim().split('\n').pop()!);
    expect(res.frames).toBe(24);
    const head = readFileSync(p('short.mp4')).subarray(0, 12);
    const isMp4 = String.fromCharCode(...head.subarray(4, 8)) === 'ftyp';
    const isWebm = head[0] === 0x1a && head[1] === 0x45 && head[2] === 0xdf && head[3] === 0xa3;
    expect(isMp4 || isWebm).toBe(true);
    const mb = await import(/* @vite-ignore */ resolve(web, 'node_modules/mediabunny/dist/bundles/mediabunny.node.cjs')).then((m) => m.default ?? m);
    const input = new mb.Input({ source: new mb.FilePathSource(p('short.mp4')), formats: mb.ALL_FORMATS });
    const track = await input.getPrimaryVideoTrack();
    const stats = await track.computePacketStats();
    expect(stats.packetCount).toBe(24);
    expect(track.displayWidth).toBe(320);
  });
});
