import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { FourDTable, bboxVolume, fromSceneModel, fromSidecar, guidHash, storeyOrder, viewerBoundsToIfc } from '../src/schedule/model';
import type { FourDModel } from '../src/schedule/model';
import { compile, parseQuery } from '../src/query';
import { linkSchedule } from '../src/schedule/link';
import { WEB } from './revision-helpers';
import { buildConfig, buildModel, buildSchedule } from './fourd-fixtures';

const scene = {
  storeys: [{ id: 1, name: 'Level 1', elevation: 0 }, { id: 2, name: 'Level 2', elevation: 4 }],
  elements: [
    { id: 0, globalId: 'G0', ifcClass: 'IfcSlab', name: 'Slab', storey: 1, material: 'Concrete', bounds: [1, 2, 3, 4, 6, 9] as [number, number, number, number, number, number], props: { 'Pset_X.Fire': 'REI60', 'Attr.Tag': 7, 'XR_Classification.Discipline': 'Structure', 'Xray_4D.Zone': 'Z1' } },
    { id: 1, globalId: 'G1', ifcClass: 'IfcWall', storey: null, bounds: [0, 0, 0, 1, 1, 1] as [number, number, number, number, number, number] },
  ],
};

describe('adapters', () => {
  it('converts the viewer (Y up) bounds to the IFC frame (Z up)', () => {
    expect(viewerBoundsToIfc([1, 2, 3, 4, 6, 9])).toEqual([1, -9, 2, 4, -3, 6]);
  });
  const m = fromSceneModel(scene, { name: 'a.ifc' });
  it('maps elements, storeys, props, zone and discipline', () => {
    expect(m.name).toBe('a.ifc');
    expect(m.elements[0]).toEqual({ globalId: 'G0', ifcClass: 'IfcSlab', name: 'Slab', storey: 'Level 1', zone: 'Z1', discipline: 'Structure', material: 'Concrete', bbox: [1, -9, 2, 4, -3, 6], props: { 'Pset_X.Fire': 'REI60', 'Attr.Tag': '7', 'XR_Classification.Discipline': 'Structure', 'Xray_4D.Zone': 'Z1' } });
    expect(m.elements[1]).toEqual({ globalId: 'G1', ifcClass: 'IfcWall', name: '', props: {}, bbox: [0, -1, 0, 1, 0, 1] });
    expect(m.storeys).toEqual([{ name: 'Level 1', elevation: 0 }, { name: 'Level 2', elevation: 4 }]);
  });
  it('an identity key is stable and changes with the GlobalIds; an explicit one wins', () => {
    expect(fromSceneModel(scene, { name: 'A.ifc' }).identityKey).toBe(m.identityKey.replace(/^a\.ifc/, 'a.ifc'));
    expect(m.identityKey).toMatch(/^a\.ifc\|2\|[0-9a-f]{8}$/);
    expect(fromSceneModel({ ...scene, elements: scene.elements.slice(0, 1) }).identityKey).not.toBe(fromSceneModel(scene).identityKey);
    expect(fromSceneModel(scene, { identityKey: 'k' }).identityKey).toBe('k');
    expect(guidHash(['b', 'a'])).toBe(guidHash(['a', 'b']));
  });
  it('custom property keys for zone and discipline', () => {
    const c = fromSceneModel(scene, { zoneProperty: 'Attr.Tag', disciplineProperty: 'Pset_X.Fire' });
    expect(c.elements[0]).toMatchObject({ zone: '7', discipline: 'REI60' });
  });
  it('reads the node reader sidecar the same way', () => {
    const sm = fromSidecar({ ...scene, source: { files: ['model.ifc'] } });
    expect(sm.name).toBe('model.ifc');
    expect(sm.elements).toHaveLength(2);
  });
  it('the linker does not depend on the viewer: the module graph holds no DOM, three or app imports', () => {
    for (const f of ['model', 'attrs', 'link', 'plan', 'planTime', 'report']) {
      const src = readFileSync(resolve(WEB, `src/schedule/${f}.ts`), 'utf8');
      for (const m of src.matchAll(/^(?:import|export)\b[^;]*?from '([^']+)'/gm)) expect(m[1]).toMatch(/^(\.\/|\.\.\/query)/);
    }
  });
});

describe('FourDTable (the criteria language over a FourDModel)', () => {
  const model = buildModel();
  const table = new FourDTable(model);
  const ids = (q: string): string[] => { const c = compile(parseQuery(q), table); return model.elements.filter((_e, i) => c.test(i)).map((e) => e.globalId); };
  it('core columns', () => {
    expect(ids("class = 'IfcSlab'")).toEqual(['SLAB1', 'SLAB2', 'SLAB3']);
    expect(ids("storey = 'Level 3' AND class = 'IfcDoor'")).toEqual(['DOOR3']);
    expect(ids("name LIKE 'Old wall%'")).toEqual(['OLD1', 'OLD2']);
    expect(ids("globalId = 'ROOF1'")).toEqual(['ROOF1']);
    expect(ids('storey IS NULL')).toEqual(['STAIR1']);
    expect(ids('storeyElevation >= 8 AND class = \'IfcSlab\'')).toEqual(['SLAB3']);
  });
  it('properties: exact, any case, or the short name; zone and discipline', () => {
    expect(ids("\"Xray_4D.Trade\" = 'MAS' AND storey = 'Level 1'")).toEqual(['WALLA1', 'WALLB1']);
    expect(ids("trade = 'ROOF'")).toEqual(['ROOF1']);
    expect(ids("zone = 'Zone B' AND storey = 'Level 2'")).toEqual(['COLB2', 'WALLB2']);
  });
  it('bounds follow the viewer convention: y is up', () => {
    expect(ids("class = 'IfcSlab' AND yMin > 7")).toEqual(['SLAB3']);
    expect(ids("class = 'IfcSlab' AND sizeY < 0.5 AND sizeX = 20")).toEqual(['SLAB1', 'SLAB2', 'SLAB3']);
    expect(ids("globalId = 'STAIR1' AND volume > 40")).toEqual(['STAIR1']);
  });
  it('an unknown column is NULL, not an error', () => {
    expect(ids("nothing = 'x'")).toEqual([]);
  });
});

describe('storey order and volume', () => {
  it('uses the model storeys, else the median bbox z', () => {
    const m = buildModel();
    expect(storeyOrder(m)).toEqual(['Level 1', 'Level 2', 'Level 3']);
    const derived: FourDModel = { ...m, storeys: undefined, elements: [...m.elements].reverse() };
    expect(storeyOrder(derived)).toEqual(['Level 1', 'Level 2', 'Level 3']);
    expect(bboxVolume([0, 0, 0, 2, 3, 4])).toBe(24);
    expect(bboxVolume(undefined)).toBe(0);
  });
});

describe('links output validates against the LinkML JSON schema', () => {
  const schema = JSON.parse(readFileSync(resolve(WEB, '../schema/linkml/xray_4d.schema.json'), 'utf8')) as { $defs: Record<string, { properties?: Record<string, { enum?: string[]; $ref?: string }>; enum?: string[] }> };
  const out = linkSchedule(buildSchedule(), buildModel(), buildConfig(), [{ id: 'a1', element: 'SLAB1', attribute: 'zone', value: 'Z', status: 'accepted', source: 'manual' }], { createdAt: '2027-01-20T00:00:00Z' });
  const only = (obj: object, def: string): void => {
    const allowed = Object.keys(schema.$defs[def]!.properties!);
    for (const k of Object.keys(obj)) expect(allowed, `${def}.${k}`).toContain(k);
  };
  it('every object uses only schema fields, snake_case, with schema enum values', () => {
    only(out, 'LinkDataset');
    only(out.model, 'ModelRef');
    only(out.schedule!, 'ScheduleRef'); // the linker always writes the schedule (optional only for mapping-only datasets)
    out.activities!.forEach((a) => only(a, 'Activity'));
    out.model_elements!.forEach((e) => only(e, 'Element'));
    out.assignments!.forEach((a) => only(a, 'Assignment'));
    out.links!.forEach((l) => only(l, 'ActivityLink'));
    out.ties!.forEach((t) => only(t, 'Tie'));
    const src = schema.$defs['LinkSource']!.enum!;
    const st = schema.$defs['ReviewStatus']!.enum!;
    const sp = schema.$defs['SplitRule']!.enum!;
    for (const l of out.links!) { expect(src).toContain(l.source); expect(st).toContain(l.status); if (l.split) expect(sp).toContain(l.split); expect(['build', 'remove']).toContain(l.role); expect(l.confidence).toBeGreaterThanOrEqual(0); expect(l.confidence).toBeLessThanOrEqual(1); }
    expect(JSON.stringify(out)).not.toMatch(/[a-z][A-Z]\w*":/); // no camelCase keys
  });
  it('references resolve: link activities are task codes, link elements are GlobalIds', () => {
    const codes = new Set(buildSchedule().tasks.map((t) => t.code));
    const gids = new Set(buildModel().elements.map((e) => e.globalId));
    for (const l of out.links!) { expect(codes.has(l.activity)).toBe(true); l.elements.forEach((g) => expect(gids.has(g)).toBe(true)); }
    out.unlinked_activities!.forEach((c) => expect(codes.has(c)).toBe(true));
  });
});

describe('docs: the example FourDConfig', () => {
  it('is valid JSON and runs through the linker and the plan', async () => {
    const md = readFileSync(resolve(WEB, 'docs-features/4d-linking.md'), 'utf8');
    const block = /```json\n([\s\S]*?)```/.exec(md)![1]!;
    const cfg = JSON.parse(block) as ReturnType<typeof buildConfig>;
    expect(cfg.schema).toBe('xray-4d-config/1');
    const { buildPlan } = await import('../src/schedule/plan');
    const links = linkSchedule(buildSchedule(), buildModel(), cfg, []);
    expect(links.links!.length).toBeGreaterThan(5);
    const plan = buildPlan(buildSchedule(), links, buildModel(), cfg.style, { config: cfg });
    expect(plan.window.to - plan.window.from).toBe(42 * 86400000);
  });
});
