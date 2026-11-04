// Parity of the browser reader (web-ifc, run here in node) against the Python converter (ifcopenshell) on the checked-in
// models. The reference output is public/models/*.json, produced by tools/ifc2glb.py.
import { execFileSync } from 'node:child_process';
import { readFileSync, existsSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { beforeAll, describe, expect, it } from 'vitest';
import type { IfcAPI } from 'web-ifc';
import { createIfcApi, extractIfc } from '../src/model/ifcRaw';
import { buildModelData } from '../src/model/ifcImport';
import { classColor } from '../src/model/ifcShared';
import type { RawModel } from '../src/model/ifcShared';

const here = dirname(fileURLToPath(import.meta.url));
const web = resolve(here, '..');
const models = resolve(web, '..', 'models');
const wasm = resolve(web, 'node_modules/web-ifc/web-ifc-node.wasm');

interface RefElement {
  id: number; globalId: string; expressId: number; ifcClass: string; name: string; storey: number | null;
  material: string; color: number[]; bounds: number[]; file: string;
}
interface RefSidecar {
  originShift: number[];
  storeys: Array<{ id: number; name: string; elevation: number }>;
  elements: RefElement[];
  relations: { voids: unknown[]; fills: unknown[]; hosts: unknown[]; ports: unknown[]; systems: Array<{ name: string; elements: number[] }> };
}

let api: IfcAPI;
beforeAll(async () => {
  api = await createIfcApi({ url: wasm });
}, 60000);

async function extractAll(files: string[]): Promise<RawModel[]> {
  const out: RawModel[] = [];
  for (const f of files) out.push(await extractIfc(api, new Uint8Array(readFileSync(resolve(models, f))), f));
  return out;
}

/** glb frame bounds + origin shift -> IFC-frame world bounds [x0,y0,z0,x1,y1,z1]. glb (x,y,z) = ifc (x, z, -y) - shift. */
function worldBounds(b: number[], shift: number[]): number[] {
  return [b[0]! + shift[0]!, -b[5]! + shift[1]!, b[1]! + shift[2]!, b[3]! + shift[0]!, -b[2]! + shift[1]!, b[4]! + shift[2]!];
}

function classCounts(els: Array<{ ifcClass: string }>): Record<string, number> {
  const c: Record<string, number> = {};
  for (const e of els) c[e.ifcClass] = (c[e.ifcClass] ?? 0) + 1;
  return Object.fromEntries(Object.entries(c).sort());
}

interface Compare {
  maxBoundsDiff: number;
  missing: string[];
  extra: string[];
  storeyMismatch: string[];
  materialMismatch: string[];
  shiftDiff: number;
}

function compare(raws: RawModel[], ref: RefSidecar) {
  const built = buildModelData(raws);
  const mine = built.sidecar;
  const key = (e: { file?: string; expressId?: number }): string => `${e.file}#${e.expressId}`;
  const refBy = new Map(ref.elements.map((e) => [key(e), e]));
  const myBy = new Map(mine.elements.map((e) => [key(e), e]));
  const cmp: Compare = { maxBoundsDiff: 0, missing: [], extra: [], storeyMismatch: [], materialMismatch: [], shiftDiff: 0 };
  for (const [k, r] of refBy) {
    const m = myBy.get(k);
    if (!m) { cmp.missing.push(`${k} ${r.ifcClass} ${r.name}`); continue; }
    const rb = worldBounds(r.bounds, ref.originShift);
    const mb = worldBounds(m.bounds, mine.originShift);
    for (let i = 0; i < 6; i++) cmp.maxBoundsDiff = Math.max(cmp.maxBoundsDiff, Math.abs(rb[i]! - mb[i]!));
    const rs = r.storey === null ? null : ref.storeys[r.storey]!.name;
    const ms = m.storey === null ? null : mine.storeys[m.storey]!.name;
    if (rs !== ms) cmp.storeyMismatch.push(`${k} ref=${rs} mine=${ms}`);
    if ((r.material ?? '') !== (m.material ?? '')) cmp.materialMismatch.push(`${k} ref="${r.material}" mine="${m.material}"`);
  }
  for (const [k, m] of myBy) if (!refBy.has(k)) cmp.extra.push(`${k} ${m.ifcClass} ${m.name}`);
  cmp.shiftDiff = Math.max(...mine.originShift.map((v, i) => Math.abs(v - ref.originShift[i]!)));
  return { built, mine, cmp };
}

function relationCounts(r: { voids: unknown[]; fills: unknown[]; hosts: unknown[]; ports: unknown[]; systems: Array<{ name: string; elements: number[] }> }) {
  return { voids: r.voids.length, fills: r.fills.length, hosts: r.hosts.length, ports: r.ports.length,
    systems: r.systems.map((s) => [s.name, s.elements.length]) };
}

const refOf = (name: string): RefSidecar => JSON.parse(readFileSync(resolve(web, 'public/models', `${name}.json`), 'utf8')) as RefSidecar;
const fixtures = resolve(here, 'fixtures/ifc');

// IFC2X3 and IFC4X3 versions of the same buildingSMART Simple-Scene files. They are not part of this repository; when the
// buildingSMART clone from the session is present they are read straight from git. The expectations below are the output
// of tools/ifc2glb.py on those files (element count, class counts, systems, storeys), and bounds are not compared here.
const STF = '/home/user/models-probe/stf';
const STF_DIRS: Record<string, string> = { '2x3': 'IFC 2.3.0.1 (IFC 2x3 TC1)', '4x3': 'IFC 4.3.2.0 (IFC 4.3 ADD2)' };
const STF_EXPECT: Record<string, { files: string[]; n: number; classes: Record<string, number>; systems: Array<[string, number]>; storeys: string[] }> = {
  '2x3/building': { files: ['Building-Structural', 'Building-Architecture', 'Building-Hvac'], n: 27, classes: { IfcBeam: 6, IfcBuildingElementProxy: 5, IfcFlowSegment: 1, IfcFlowTerminal: 2, IfcFooting: 1, IfcFurnishingElement: 1, IfcSlab: 3, IfcWall: 8 }, systems: [['house - chimney flue', 3]], storeys: ['00 groundfloor'] },
  '2x3/Infra-Plumbing': { files: ['Infra-Plumbing'], n: 26, classes: { IfcDistributionChamberElement: 2, IfcFlowSegment: 24 }, systems: [['road wastewater system', 26]], storeys: [] },
  '2x3/Infra-Bridge': { files: ['Infra-Bridge'], n: 47, classes: { IfcBeam: 8, IfcBuildingElementProxy: 8, IfcColumn: 7, IfcFooting: 7, IfcMember: 8, IfcRailing: 2, IfcSlab: 3, IfcWall: 4 }, systems: [], storeys: [] },
  '2x3/Infra-Rail': { files: ['Infra-Rail'], n: 72, classes: { IfcBuildingElementProxy: 72 }, systems: [], storeys: [] },
  '2x3/Infra-Road': { files: ['Infra-Road'], n: 44, classes: { IfcElementAssembly: 12, IfcSlab: 32 }, systems: [], storeys: [] },
  '4x3/building': { files: ['Building-Structural', 'Building-Architecture', 'Building-Hvac'], n: 26, classes: { IfcAirTerminal: 2, IfcBeam: 6, IfcChimney: 1, IfcDiscreteAccessory: 2, IfcDuctSegment: 1, IfcEarthworksFill: 1, IfcFooting: 1, IfcFurniture: 1, IfcSlab: 3, IfcWall: 8 }, systems: [['house - chimney flue', 3]], storeys: ['00 groundfloor'] },
  '4x3/Infra-Plumbing': { files: ['Infra-Plumbing'], n: 26, classes: { IfcDistributionChamberElement: 2, IfcPipeSegment: 24 }, systems: [['road wastewater system', 26]], storeys: [] },
  '4x3/Infra-Bridge': { files: ['Infra-Bridge'], n: 47, classes: { IfcBeam: 8, IfcColumn: 7, IfcEarthworksFill: 4, IfcFooting: 7, IfcMember: 8, IfcRailing: 2, IfcSign: 4, IfcSlab: 3, IfcWall: 4 }, systems: [], storeys: [] },
  '4x3/Infra-Rail': { files: ['Infra-Rail'], n: 72, classes: { IfcCourse: 2, IfcRail: 4, IfcTrackElement: 66 }, systems: [], storeys: [] },
  '4x3/Infra-Road': { files: ['Infra-Road'], n: 64, classes: { IfcCourse: 16, IfcEarthworksFill: 16, IfcRoadPart: 12, IfcSurfaceFeature: 20 }, systems: [], storeys: [] },
};

describe.skipIf(!existsSync(STF))('IFC2X3 and IFC4X3 Simple-Scene files (buildingSMART clone) vs ifc2glb.py', () => {
  for (const [key, exp] of Object.entries(STF_EXPECT)) {
    it(key, async () => {
      const dir = STF_DIRS[key.split('/')[0]!]!;
      const raws: RawModel[] = [];
      for (const f of exp.files) {
        const bytes = execFileSync('git', ['-C', STF, 'show', `HEAD:${dir}/Simple-Scene/${f}.ifc`], { maxBuffer: 64 * 1024 * 1024 });
        raws.push(await extractIfc(api, new Uint8Array(bytes), `${f}.ifc`));
      }
      expect(raws[0]!.schema).toBe(key.startsWith('2x3') ? 'IFC2X3' : 'IFC4X3_ADD2');
      const { sidecar } = buildModelData(raws);
      expect(sidecar.elements.length).toBe(exp.n);
      expect(classCounts(sidecar.elements)).toEqual(Object.fromEntries(Object.entries(exp.classes).sort()));
      expect(sidecar.relations.systems.map((s) => [s.name, s.elements.length])).toEqual(exp.systems);
      expect(sidecar.storeys.map((s) => s.name)).toEqual(exp.storeys);
      expect(sidecar.relations.voids.length + sidecar.relations.fills.length + sidecar.relations.ports.length).toBe(0);
    }, 120000);
  }
});

describe('web-ifc reader vs ifc2glb.py', () => {
  const cases: Array<{ title: string; files: string[]; ref: string; voids?: number; fills?: number }> = [
    { title: 'Building-Structural + Architecture + Hvac (IFC4) vs building.json', files: ['Building-Structural.ifc', 'Building-Architecture.ifc', 'Building-Hvac.ifc'], ref: 'building' },
    { title: 'AC20-FZK-Haus (IFC4, 17 voids, 16 fills) vs fzk-haus.json', files: ['AC20-FZK-Haus.ifc'], ref: 'fzk-haus', voids: 17, fills: 16 },
    { title: 'Infra-Plumbing (IFC4) vs plumbing.json', files: ['Infra-Plumbing.ifc'], ref: 'plumbing' },
  ];
  for (const c of cases) {
    it(c.title, async () => {
      const ref = refOf(c.ref);
      const raws = await extractAll(c.files);
      const { mine, cmp } = compare(raws, ref);
      expect(classCounts(mine.elements)).toEqual(classCounts(ref.elements));
      expect(cmp.missing).toEqual([]);
      expect(cmp.extra).toEqual([]);
      expect(cmp.maxBoundsDiff).toBeLessThan(0.01);
      expect(relationCounts(mine.relations)).toEqual(relationCounts(ref.relations));
      if (c.voids !== undefined) expect(mine.relations.voids.length).toBe(c.voids);
      if (c.fills !== undefined) expect(mine.relations.fills.length).toBe(c.fills);
      expect(cmp.storeyMismatch).toEqual([]);
    }, 180000);
  }
  // Generated by tests/fixtures/make_ifc_fixtures.py; the .ref.json files are what tools/ifc2glb.py makes of them.
  // They cover what the sample files do not: ports (IFC4 IfcRelNests + IfcRelConnectsPorts, IFC2X3
  // IfcRelConnectsPortToElement), a system, a material, the storey fallback and an unstyled element.
  for (const [name, schema] of [['ports-ifc4', 'IFC4'], ['ports-ifc2x3', 'IFC2X3']] as const) {
    it(`${name} (${schema}): ports, systems, voids/fills, materials, storey fallback`, async () => {
      const ref = JSON.parse(readFileSync(resolve(fixtures, `${name}.ref.json`), 'utf8')) as RefSidecar;
      const raw = await extractIfc(api, new Uint8Array(readFileSync(resolve(fixtures, `${name}.ifc`))), `${name}.ifc`);
      expect(raw.schema).toBe(schema);
      const built = buildModelData([raw]);
      const mine = built.sidecar;
      expect(classCounts(mine.elements)).toEqual(classCounts(ref.elements));
      expect(relationCounts(mine.relations)).toEqual(relationCounts(ref.relations));
      expect(relationCounts(mine.relations)).toEqual({ voids: 1, fills: 1, hosts: 1, ports: 2, systems: [['Supply Air', 3]] });
      expect(mine.relations.ports).toEqual(ref.relations.ports);
      expect(mine.relations.systems).toEqual(ref.relations.systems);
      expect(mine.relations.hosts).toEqual(ref.relations.hosts);
      expect(mine.storeys.map((s) => [s.name, s.elevation])).toEqual(ref.storeys.map((s) => [s.name, s.elevation]));
      expect(mine.elements.map((e) => e.storey)).toEqual(ref.elements.map((e) => e.storey));
      expect(built.report.storeyFallback).toBe(1); // the beam, contained in the building only
      expect(mine.elements.map((e) => e.material)).toEqual(ref.elements.map((e) => e.material));
      expect(mine.elements.find((e) => e.ifcClass === 'IfcSlab')!.material).toBe('Concrete C30');
      // Colours: the styled wall keeps its style. Unstyled elements: the converter's output there is ifcopenshell's built-in
      // per-class default (door brown, slab 0.4 grey, other 0.7 grey), not the CLASS_COLORS table it also contains (that
      // table only applies when ifcopenshell reports no material at all). The reader has no such built-ins, so unstyled
      // elements get the converter's CLASS_COLORS entry. Documented difference.
      const wall = mine.elements.find((e) => e.ifcClass === 'IfcWall')!;
      expect(wall.color).toEqual(ref.elements.find((e) => e.ifcClass === 'IfcWall')!.color);
      expect(wall.color).toEqual([0.8, 0.3, 0.2, 1]);
      for (const e of mine.elements) if (e.ifcClass !== 'IfcWall') expect(e.color).toEqual(classColor(e.ifcClass));
      let maxDiff = 0;
      mine.elements.forEach((e, i) => {
        const a = worldBounds(e.bounds, mine.originShift);
        const b = worldBounds(ref.elements[i]!.bounds, ref.originShift);
        for (let k = 0; k < 6; k++) maxDiff = Math.max(maxDiff, Math.abs(a[k]! - b[k]!));
      });
      expect(maxDiff).toBeLessThan(0.01);
    }, 60000);
  }

  it('the models directory is where the converter left it', () => {
    expect(existsSync(resolve(models, 'AC20-FZK-Haus.ifc'))).toBe(true);
    expect(existsSync(resolve(web, 'public/models/fzk-haus.json'))).toBe(true);
  });
});
