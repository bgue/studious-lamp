// ActivityIds in the Xray_4D property set: the task codes of the accepted build links, written as IfcText in the same append-only block as
// Location, Trade and Zone, read back by web-ifc and by the viewer's importer, and restored by the linker (`idProperty`) as accepted links with source `property`.
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { beforeAll, describe, expect, it, vi } from 'vitest';
import type { IfcAPI } from 'web-ifc';
import { createIfcApi } from '../src/model/ifcRaw';
import { planOf } from '../src/ifcsave/collect';
import { elementProps } from '../src/ifcsave/additions';
import { DEFAULT_SAVE_OPTIONS } from '../src/ifcsave/plan';
import type { SaveOptions } from '../src/ifcsave/plan';
import { runSave } from '../src/ifcsave/run';
import { readAdditions } from '../src/ifcsave/readBack';
import { locateInsert } from '../src/ifcsave/splice';
import { makeSource } from '../src/ifcsave/source';
import { ACTIVITY_IDS_PROPERTY, activityIdsMap, saveMapWithLinks } from '../src/map4d/ifcio';
import { emptyConfig } from '../src/map4d/scheduleConfig';
import { fromSceneModel } from '../src/schedule/model';
import type { SceneLike } from '../src/schedule/model';
import { linkSchedule } from '../src/schedule/link';
import { parseXer } from '../src/schedule/xer';
import type { ActivityLink, FourDConfig } from '../src/schedule/types';
import { SCHEMA, blobOf, bytesOf, modelIfc, sameBytes, textOf, wasmPath } from './ifcsave-helpers';

vi.setConfig({ testTimeout: 180000 });
vi.mock('../src/model/ifcRuntime', () => ({
  IFC_READER_AVAILABLE: true,
  createIfcWorker: () => { throw new Error('no worker in node'); },
  getWasmSource: async () => ({ url: wasmPath }),
  loadRawReader: () => import('../src/model/ifcRaw'),
}));
const { importIfc } = await import('../src/model/ifcImport');

const file = (p: string): string => fileURLToPath(new URL(p, import.meta.url));
const FZK = modelIfc('AC20-FZK-Haus.ifc');
const OPTS: SaveOptions = { ...DEFAULT_SAVE_OPTIONS, includeFourD: true, toolVersion: 'test' };
const schedule = parseXer(readFileSync(file('../public/samples/fzk-haus.xer')));
const sample = JSON.parse(readFileSync(file('../public/samples/fzk-haus.4d.json'), 'utf8')) as FourDConfig;

let api: IfcAPI;
beforeAll(async () => { api = await createIfcApi({ url: wasmPath }); }, 60000);

/** ActivityIds (and its IFC type) of each element from the Xray_4D set, by express id, read through web-ifc. */
function readIds(bytes: Uint8Array): Map<number, string> {
  const m = api.OpenModel(bytes);
  const out = new Map<number, string>();
  const rels = api.GetLineIDsWithType(m, api.GetTypeCodeFromName?.('IFCRELDEFINESBYPROPERTIES') ?? 0);
  for (let i = 0; i < rels.size(); i++) {
    const r = api.GetLine(m, rels.get(i), true);
    const set = r.RelatingPropertyDefinition;
    if (set?.Name?.value !== 'Xray_4D') continue;
    const p = set.HasProperties.find((x: { Name: { value: string } }) => x.Name.value === 'ActivityIds');
    if (!p) continue;
    for (const o of r.RelatedObjects) out.set(o.value ?? o.expressID, p.NominalValue.value);
  }
  api.CloseModel(m);
  return out;
}

describe('the ActivityIds text (pure)', () => {
  const links: ActivityLink[] = [
    { id: 'a', activity: 'A20', role: 'build', elements: ['g1', 'g2'], status: 'accepted' },
    { id: 'b', activity: 'A10', role: 'build', elements: ['g1'], status: 'accepted' },
    { id: 'c', activity: 'A30', role: 'build', elements: ['g1', 'g3'], status: 'proposed' },
    { id: 'd', activity: 'A40', role: 'build', elements: ['g4'], status: 'rejected' },
    { id: 'e', activity: 'A50', role: 'remove', elements: ['g5'], status: 'accepted' },
    { id: 'f', activity: 'A,6', role: 'build', elements: ['g6'], status: 'accepted' },
  ];

  it('lists the accepted build links of each element, sorted, comma separated; nothing else', () => {
    expect([...activityIdsMap(links)]).toEqual([['g1', 'A10,A20'], ['g2', 'A20']]);
    expect(activityIdsMap(undefined).size).toBe(0);
  });

  it('joins with the accepted assignments in the save map', () => {
    const map = saveMapWithLinks([{ id: 'x', element: 'g2', attribute: 'trade', value: 'CONC', status: 'accepted' }], links);
    expect(map.get('g2')).toEqual({ trade: 'CONC', activityIds: 'A20' });
    expect(map.get('g1')).toEqual({ activityIds: 'A10,A20' });
    expect(map.has('g3')).toBe(false);
  });

  it('is an IfcText property after Location, Trade and Zone, and only with the 4D option on', () => {
    const e = { expressId: 1, globalId: 'g', fourD: { location: 'L', activityIds: 'A10,A20' } };
    const props = elementProps(e, SCHEMA, '4', OPTS).fourD;
    expect(props).toEqual([{ name: 'Location', type: 'IfcLabel', value: 'L' }, { name: 'ActivityIds', type: 'IfcText', value: 'A10,A20' }]);
    expect(elementProps(e, SCHEMA, '4', { ...OPTS, includeFourD: false }).fourD).toEqual([]);
  });
});

describe('ActivityIds in the IFC (FZK-Haus)', () => {
  let res: Awaited<ReturnType<typeof importIfc>>;
  let source: ReturnType<typeof makeSource>;
  let links: ActivityLink[] = [];
  beforeAll(async () => {
    const data = new Uint8Array(readFileSync(FZK)).buffer as ArrayBuffer;
    res = await importIfc([{ name: 'AC20-FZK-Haus.ifc', data }], { forceMainThread: true, edges: 'none' });
    source = makeSource(res.raws[0]!.fileName, blobOf(FZK), res.raws[0]!.schema, res.raws[0]!.saveInfo);
    const model = fromSceneModel(res.loaded.model as unknown as SceneLike, { identityKey: 'fzk' });
    links = linkSchedule(schedule, model, sample, []).links!.filter((l) => l.status === 'accepted');
  });

  const plan = () => planOf({ model: res.loaded.model, sources: [source], results: [], schema: SCHEMA, options: OPTS, fourD: saveMapWithLinks([], links) });

  it('plans every linked element with its task codes', () => {
    const [p] = plan();
    const want = activityIdsMap(links);
    expect(want.size).toBe(res.loaded.model.elements.length);
    expect(p!.elements.length).toBe(want.size);
    for (const e of p!.elements) expect(e.fourD).toEqual({ activityIds: want.get(e.globalId) });
  });

  it('writes the codes in the one block, reads them back through web-ifc and the block reader, and keeps every original line', async () => {
    const [p] = plan();
    const [out] = await runSave([{ plan: p!, blob: source.blob }], SCHEMA, OPTS);
    const bytes = await bytesOf(new Blob(out!.parts));
    const text = await textOf(new Blob(out!.parts));
    expect(text.match(/XRAY-BEGIN/g)).toHaveLength(1);
    expect(text).toContain("'ActivityIds'");
    expect(text).toMatch(/IFCTEXT\('[^']+'\)/);
    const at = await locateInsert(source.blob);
    const orig = new Uint8Array(readFileSync(FZK));
    expect(sameBytes(bytes.subarray(0, at.cut), orig.subarray(0, at.cut))).toBe(true);
    const got = readIds(bytes);
    const want = activityIdsMap(links);
    expect(got.size).toBe(want.size);
    for (const e of p!.elements) expect(got.get(e.expressId), e.globalId).toBe(want.get(e.globalId));
    const read = readAdditions(text.slice(at.cut, text.indexOf('ENDSEC;', at.cut)));
    const first = p!.elements[0]!;
    expect(read.byExpressId.get(first.expressId)!.review['Xray_4D.ActivityIds']).toBe(want.get(first.globalId));
  });

  it('reopens linked: the importer reads ActivityIds, and the linker restores accepted links with source property and the same elements', async () => {
    const [p] = plan();
    const [out] = await runSave([{ plan: p!, blob: source.blob }], SCHEMA, OPTS);
    const saved = await bytesOf(new Blob(out!.parts));
    const again = await importIfc([{ name: 'AC20-FZK-Haus.xray.ifc', data: saved.buffer.slice(saved.byteOffset, saved.byteOffset + saved.byteLength) as ArrayBuffer }], { forceMainThread: true, edges: 'none' });
    // the ids are in the hover properties of the elements; the linker reads them as links with source property, and an empty configuration links nothing else
    const model = fromSceneModel(again.loaded.model as unknown as SceneLike, { identityKey: 'fzk' });
    expect(Object.keys(again.loaded.model.elements[0]!.props ?? {})).toContain(ACTIVITY_IDS_PROPERTY);
    const back = linkSchedule(schedule, model, emptyConfig(), [], { idProperty: ACTIVITY_IDS_PROPERTY, suggest: false }).links!.filter((l) => l.status === 'accepted');
    expect(back.length).toBe(links.filter((l) => l.elements.length > 0).length);
    for (const l of back) {
      expect(l.source).toBe('property');
      expect(l.confidence).toBe(1);
      expect(l.role).toBe('build');
      const orig = links.find((x) => x.activity === l.activity)!;
      expect([...l.elements].sort()).toEqual([...orig.elements].sort());
    }
  });
});
