// Classification facets in the saved IFC: each XR_<Facet> set (XR_Trade, XR_Orientation, ...) on the elements that have facet
// results, typed values (IfcLabel, IfcBoolean, IfcReal, IfcNormalisedRatioMeasure), written only with includeFacets, read back by
// web-ifc, original bytes kept.
import { readFileSync } from 'node:fs';
import { beforeAll, describe, expect, it, vi } from 'vitest';
import type { IfcAPI } from 'web-ifc';
import { createIfcApi } from '../src/model/ifcRaw';
import { planOf } from '../src/ifcsave/collect';
import { facetPropSpec, facetSets } from '../src/ifcsave/additions';
import { DEFAULT_SAVE_OPTIONS } from '../src/ifcsave/plan';
import type { SaveOptions } from '../src/ifcsave/plan';
import { runSave } from '../src/ifcsave/run';
import { locateInsert } from '../src/ifcsave/splice';
import { makeSource } from '../src/ifcsave/source';
import { SCHEMA, blobOf, bytesOf, fileBytes, modelIfc, sameBytes, textOf, wasmPath } from './ifcsave-helpers';

vi.setConfig({ testTimeout: 180000 });
vi.mock('../src/model/ifcRuntime', () => ({
  IFC_READER_AVAILABLE: true,
  createIfcWorker: () => { throw new Error('no worker in node'); },
  getWasmSource: async () => ({ url: wasmPath }),
  loadRawReader: () => import('../src/model/ifcRaw'),
}));
const { importIfc } = await import('../src/model/ifcImport');

const FZK = modelIfc('AC20-FZK-Haus.ifc');
const OPTS: SaveOptions = { ...DEFAULT_SAVE_OPTIONS, includeFacets: true, toolVersion: 'test' };

describe('facet value types', () => {
  it('booleans, numbers, confidence, short and long text', () => {
    expect(facetPropSpec('NeedsReview', true).type).toBe('IfcBoolean');
    expect(facetPropSpec('Tilt', 35.2).type).toBe('IfcReal');
    expect(facetPropSpec('Confidence', 0.82).type).toBe('IfcNormalisedRatioMeasure');
    expect(facetPropSpec('Code', 'CONC').type).toBe('IfcLabel');
    expect(facetPropSpec('Code', 'x'.repeat(300)).type).toBe('IfcText');
  });
  it('groups flat names into XR_ sets and skips anything else', () => {
    const m = facetSets({ 'XR_Trade.Code': 'CONC', 'XR_Trade.Confidence': 0.9, 'XR_Orientation.Tilt': 0, 'Pset_WallCommon.IsExternal': true, Loose: 'x' });
    expect([...m.keys()].sort()).toEqual(['XR_Orientation', 'XR_Trade']);
    expect(m.get('XR_Trade')!.map((p) => p.name)).toEqual(['Code', 'Confidence']);
  });
});

describe('save with facets (FZK-Haus)', () => {
  let api: IfcAPI;
  let res: Awaited<ReturnType<typeof importIfc>>;
  let source: ReturnType<typeof makeSource>;
  let facets: Map<string, Record<string, string | number | boolean>>;
  beforeAll(async () => {
    api = await createIfcApi({ url: wasmPath });
    res = await importIfc([{ name: 'AC20-FZK-Haus.ifc', data: new Uint8Array(readFileSync(FZK)).buffer as ArrayBuffer }], { forceMainThread: true, edges: 'none' });
    source = makeSource(res.raws[0]!.fileName, blobOf(FZK), res.raws[0]!.schema, res.raws[0]!.saveInfo);
    facets = new Map();
    res.loaded.model.elements.slice(0, 10).forEach((e, i) => facets.set(e.globalId, {
      'XR_Trade.Code': i % 2 ? 'CONC' : 'GLAZ', 'XR_Trade.Confidence': 0.75, 'XR_Trade.Source': 'rule', 'XR_Trade.NeedsReview': false, 'XR_Trade.SchemeVersion': 'xr-facets/1',
      'XR_Orientation.Code': 'VERTICAL', 'XR_Orientation.Tilt': 90, 'XR_Orientation.Plausible': true,
    }));
  });
  const plan = (include: boolean) => planOf({ model: res.loaded.model, sources: [source], results: [], schema: SCHEMA, options: { ...OPTS, includeFacets: include }, facets });

  it('plans only the elements with facet results, and none when the box is off', () => {
    expect(plan(true)[0]!.elements).toHaveLength(10);
    expect(plan(false)[0]!.elements).toHaveLength(0);
  });

  it('writes the XR_ sets with typed values, readable by web-ifc, original bytes kept', async () => {
    const [p] = plan(true);
    const [out] = await runSave([{ plan: p!, blob: source.blob }], SCHEMA, OPTS);
    const bytes = await bytesOf(new Blob(out!.parts));
    const text = await textOf(new Blob(out!.parts));
    expect(text).toContain("'XR_Trade'");
    expect(text).toContain("'XR_Orientation'");
    expect(text).toMatch(/IFCREAL\(90\.?\)/);
    expect(text).toMatch(/IFCNORMALISEDRATIOMEASURE\(0\.75\)/);
    const at = await locateInsert(source.blob);
    expect(sameBytes(bytes.subarray(0, at.cut), fileBytes(FZK).subarray(0, at.cut))).toBe(true);
    // web-ifc opens the result and finds the sets
    const m = api.OpenModel(bytes);
    const psets = api.GetLineIDsWithType(m, api.GetTypeCodeFromName?.('IFCPROPERTYSET') ?? 0);
    const names = new Set<string>();
    for (let i = 0; i < psets.size(); i++) names.add(String((api.GetLine(m, psets.get(i)) as { Name?: { value?: string } }).Name?.value));
    expect(names.has('XR_Trade')).toBe(true);
    expect(names.has('XR_Orientation')).toBe(true);
    api.CloseModel(m);
  });
});
