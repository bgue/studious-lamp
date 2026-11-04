// The direct path (merged arrays built in the worker, MergedGeometry.fromArrays) against the glb path (glb bytes + parseModel,
// what the CLI packager writes and what the viewer used to do): same SceneModel, same ranges, bounds, positions, indices and
// edges, on the sample IFC files and the generated fixtures. Also the pieces the large-model options rely on.
import { existsSync, readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { BufferAttribute, BufferGeometry, EdgesGeometry, Ray, Vector3, DoubleSide } from 'three';
import { MeshBVH } from 'three-mesh-bvh';
import { beforeAll, describe, expect, it } from 'vitest';
import type { IfcAPI } from 'web-ifc';
import { AUTO_EDGES_MAX_ELEMENTS, buildMergedData, buildModelData } from '../src/model/ifcImport';
import { buildBvh } from '../src/model/ifcBvh';
import { computeEdges, EDGE_THRESHOLD_DEG } from '../src/model/ifcEdges';
import { createIfcApi, extractIfc } from '../src/model/ifcRaw';
import type { RawModel } from '../src/model/ifcShared';
import { assembleLoaded, normaliseRecord, parseModel } from '../src/model/loader';
import type { LoadedModel } from '../src/model/loader';
import { MergedGeometry, EDGE_THRESHOLD_DEG as MERGED_THRESHOLD } from '../src/model/merged';
import { mergedTransferables } from '../src/model/mergedArrays';

const here = dirname(fileURLToPath(import.meta.url));
const web = resolve(here, '..');
const models = resolve(web, '..', 'models');
const fixtures = resolve(here, 'fixtures/ifc');
const wasm = resolve(web, 'node_modules/web-ifc/web-ifc-node.wasm');
const BIG = '/tmp/xray-big-ifc/big-1000.ifc'; // tools/make_big_ifc.py -n 1000, when the benchmark files exist

let api: IfcAPI;
beforeAll(async () => {
  api = await createIfcApi({ url: wasm });
}, 60000);

async function extractAll(paths: string[]): Promise<RawModel[]> {
  const out: RawModel[] = [];
  for (const p of paths) out.push(await extractIfc(api, new Uint8Array(readFileSync(p)), p.split('/').pop()!));
  return out;
}

/** SceneModel as JSON (the byGlobalId Map as entries). */
const modelJson = (m: LoadedModel['model']): string =>
  JSON.stringify(m, (_k, v) => (v instanceof Map ? [...v.entries()] : v));

/** A bound of -0 and +0 are the same number; Box3.expandByPoint and a plain comparison loop pick differently. */
const noNegZero = (v: number[]): number[] => v.map((x) => x + 0);

const sameArray = (a: ArrayLike<number>, b: ArrayLike<number>): boolean => {
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return false;
  return true;
};

async function bothPaths(raws: RawModel[]): Promise<{ glb: LoadedModel; direct: LoadedModel; arrays: ReturnType<typeof buildMergedData> }> {
  const data = buildModelData(raws);
  const glb = await parseModel(data.glb, data.sidecar);
  const built = buildMergedData(raws, { edges: 'all' });
  const geometry = MergedGeometry.fromArrays(built.arrays);
  const direct = assembleLoaded(built.head, built.records.map(normaliseRecord), geometry);
  return { glb, direct, arrays: built };
}

function expectIdentical(glb: LoadedModel, direct: LoadedModel): void {
  expect(modelJson(direct.model)).toBe(modelJson(glb.model));
  const a = glb.geometry;
  const b = direct.geometry;
  expect(b.elementCount).toBe(a.elementCount);
  expect(b.ranges).toEqual(a.ranges);
  expect(b.vertexRanges).toEqual(a.vertexRanges);
  expect(b.edgeRanges).toEqual(a.edgeRanges);
  for (let i = 0; i < a.elementCount; i++) {
    expect(noNegZero(b.bounds[i]!.min.toArray()), `bounds ${i}`).toEqual(noNegZero(a.bounds[i]!.min.toArray()));
    expect(noNegZero(b.bounds[i]!.max.toArray()), `bounds ${i}`).toEqual(noNegZero(a.bounds[i]!.max.toArray()));
    expect(b.bounds[i]!.isEmpty()).toBe(a.bounds[i]!.isEmpty());
  }
  const arr = (g: MergedGeometry, name: string): Float32Array => g.geometry.getAttribute(name).array as Float32Array;
  expect(sameArray(arr(b, 'position'), arr(a, 'position')), 'position').toBe(true);
  expect(sameArray(arr(b, 'elementId'), arr(a, 'elementId')), 'elementId').toBe(true);
  expect(sameArray(b.geometry.getIndex()!.array, a.geometry.getIndex()!.array), 'index').toBe(true);
  // the constructor re-normalises (identity matrix, 1 ulp at most)
  const na = arr(a, 'normal');
  const nb = arr(b, 'normal');
  expect(nb.length).toBe(na.length);
  let worst = 0;
  for (let i = 0; i < na.length; i++) worst = Math.max(worst, Math.abs(na[i]! - nb[i]!));
  expect(worst).toBeLessThan(1e-6);
  expect(sameArray(b.edges.getAttribute('position').array, a.edges.getAttribute('position').array), 'edge positions').toBe(true);
  expect(sameArray(b.edges.getAttribute('elementId').array, a.edges.getAttribute('elementId').array), 'edge ids').toBe(true);
  // the same lookups
  for (const tri of [0, 1, 7, (a.geometry.getIndex()!.count / 3) - 1]) expect(b.elementOfTriangle(tri)).toBe(a.elementOfTriangle(tri));
  expect(noNegZero(b.totalBounds().min.toArray())).toEqual(noNegZero(a.totalBounds().min.toArray()));
  expect(noNegZero(b.totalBounds().max.toArray())).toEqual(noNegZero(a.totalBounds().max.toArray()));
}

describe('direct path vs glb path', () => {
  const cases: Array<{ title: string; files: string[] }> = [
    { title: 'Building-Structural + Architecture + Hvac (federated)', files: [resolve(models, 'Building-Structural.ifc'), resolve(models, 'Building-Architecture.ifc'), resolve(models, 'Building-Hvac.ifc')] },
    { title: 'AC20-FZK-Haus (curved walls, windows, voids and fills)', files: [resolve(models, 'AC20-FZK-Haus.ifc')] },
    { title: 'Infra-Plumbing', files: [resolve(models, 'Infra-Plumbing.ifc')] },
    { title: 'fixture ports-ifc4', files: [resolve(fixtures, 'ports-ifc4.ifc')] },
    { title: 'fixture ports-ifc2x3', files: [resolve(fixtures, 'ports-ifc2x3.ifc')] },
    { title: 'fixture props-mm-ifc4', files: [resolve(fixtures, 'props-mm-ifc4.ifc')] },
  ];
  for (const c of cases) {
    it(c.title, async () => {
      const raws = await extractAll(c.files);
      const { glb, direct } = await bothPaths(raws);
      expect(glb.model.elements.length).toBeGreaterThan(0);
      expectIdentical(glb, direct);
    }, 180000);
  }

  it.skipIf(!existsSync(BIG))('generated 1,000-element building (make_big_ifc.py)', async () => {
    const raws = await extractAll([BIG]);
    const { glb, direct } = await bothPaths(raws);
    expect(glb.model.elements.length).toBe(1000);
    expectIdentical(glb, direct);
  }, 180000);

  it('consume mode frees the reader arrays but builds the same result', async () => {
    const raws = await extractAll([resolve(models, 'AC20-FZK-Haus.ifc')]);
    const keep = buildMergedData(raws, { edges: 'all' });
    const eaten = buildMergedData(raws, { edges: 'all', consume: true });
    expect(raws[0]!.elements.every((e) => e.positions.length === 0 && e.indices.length === 0)).toBe(true);
    expect(sameArray(eaten.arrays.position, keep.arrays.position)).toBe(true);
    expect(sameArray(eaten.arrays.index, keep.arrays.index)).toBe(true);
    expect(JSON.stringify(eaten.head)).toBe(JSON.stringify(keep.head));
    expect(JSON.stringify(eaten.records)).toBe(JSON.stringify(keep.records));
  }, 120000);
});

describe('worker BVH', () => {
  it('serialises to the same bytes the lazy getter builds, and installs without a rebuild', async () => {
    const raws = await extractAll([resolve(models, 'AC20-FZK-Haus.ifc')]);
    const data = buildModelData(raws);
    const glb = await parseModel(data.glb, data.sidecar);
    const lazy = glb.geometry.bvh; // MergedGeometry's own indirect build
    const built = buildMergedData(raws, { edges: 'none' });
    const ser = buildBvh(built.arrays);
    expect(ser.roots.length).toBe(lazy._roots.length);
    for (let i = 0; i < ser.roots.length; i++) expect(sameArray(new Uint8Array(ser.roots[i]!), new Uint8Array(lazy._roots[i]!))).toBe(true);
    expect(sameArray(ser.indirectBuffer, lazy._indirectBuffer!)).toBe(true);

    built.arrays.bvh = ser;
    const direct = MergedGeometry.fromArrays(built.arrays);
    // installed, not rebuilt: the getter returns the deserialised object whose buffers are the ones we gave it
    expect(direct.bvh._roots[0]).toBe(ser.roots[0]);
    expect(direct.bvh._indirectBuffer).toBe(ser.indirectBuffer);
    // and it answers like the lazy one
    const b = glb.geometry.totalBounds();
    const c = b.getCenter(new Vector3());
    const ray = new Ray(new Vector3(c.x, b.max.y + 5, c.z), new Vector3(0, -1, 0));
    const h1 = lazy.raycast(ray, DoubleSide, 0, 100).map((h) => [h.faceIndex, Math.round(h.distance * 1e4)]);
    const h2 = direct.bvh.raycast(ray, DoubleSide, 0, 100).map((h) => [h.faceIndex, Math.round(h.distance * 1e4)]);
    expect(h1.length).toBeGreaterThan(0);
    expect(h2).toEqual(h1);
    // the transfer list covers the BVH buffers and every array once
    const list = mergedTransferables(built.arrays);
    expect(new Set(list).size).toBe(list.length);
    expect(list).toContain(ser.indirectBuffer.buffer);
    expect(list).toContain(ser.roots[0]);
  }, 120000);
});

describe('edges', () => {
  it('uses the same crease angle as MergedGeometry', () => {
    expect(EDGE_THRESHOLD_DEG).toBe(30);
    expect(MERGED_THRESHOLD).toBe(EDGE_THRESHOLD_DEG);
  });

  it('computeEdges equals three EdgesGeometry on closed, open, degenerate and non-manifold meshes', () => {
    // a unit cube, an open cylinder (no caps), a fan with a repeated triangle and a degenerate one
    const pos: number[] = [];
    const idx: number[] = [];
    const v = (x: number, y: number, z: number): number => { pos.push(x, y, z); return pos.length / 3 - 1; };
    const quad = (a: number, b: number, c: number, d: number): void => { idx.push(a, b, c, a, c, d); };
    // cube with shared corner vertices
    const c = [v(0, 0, 0), v(1, 0, 0), v(1, 1, 0), v(0, 1, 0), v(0, 0, 1), v(1, 0, 1), v(1, 1, 1), v(0, 1, 1)];
    quad(c[0]!, c[3]!, c[2]!, c[1]!); quad(c[4]!, c[5]!, c[6]!, c[7]!); quad(c[0]!, c[1]!, c[5]!, c[4]!);
    quad(c[2]!, c[3]!, c[7]!, c[6]!); quad(c[1]!, c[2]!, c[6]!, c[5]!); quad(c[3]!, c[0]!, c[4]!, c[7]!);
    const vStart1 = pos.length / 3;
    const iStart1 = idx.length;
    // open cylinder, 24 sides, with duplicated seam vertices (same position, different index)
    const n = 24;
    for (let i = 0; i <= n; i++) {
      const t = (i / n) * Math.PI * 2;
      v(3 + Math.cos(t), Math.sin(t), 0);
      v(3 + Math.cos(t), Math.sin(t), 2);
    }
    for (let i = 0; i < n; i++) {
      const a = vStart1 + i * 2;
      idx.push(a, a + 2, a + 3, a, a + 3, a + 1);
    }
    const vStart2 = pos.length / 3;
    const iStart2 = idx.length;
    const p0 = v(10, 0, 0), p1 = v(11, 0, 0), p2 = v(10, 1, 0), p3 = v(10, 0, 1), p4 = v(10, 0, 0.00001);
    idx.push(p0, p1, p2, p0, p1, p2, p0, p2, p3, p0, p0, p1, p4, p1, p2, p0, p4, p3);
    const position = Float32Array.from(pos);
    const index = Uint32Array.from(idx);
    const vertexRanges = Uint32Array.from([0, vStart1, vStart1, vStart2 - vStart1, vStart2, pos.length / 3 - vStart2]);
    const ranges = Uint32Array.from([0, iStart1, iStart1, iStart2 - iStart1, iStart2, idx.length - iStart2]);
    const got = computeEdges({ position, index, vertexRanges, ranges, elementCount: 3 }, 30);
    for (let e = 0; e < 3; e++) {
      const vs = vertexRanges[e * 2]!, vn = vertexRanges[e * 2 + 1]!, is = ranges[e * 2]!, ic = ranges[e * 2 + 1]!;
      const g = new BufferGeometry();
      g.setAttribute('position', new BufferAttribute(position.slice(vs * 3, (vs + vn) * 3), 3));
      g.setIndex(new BufferAttribute(Uint32Array.from(index.subarray(is, is + ic), (x) => x - vs), 1));
      const ref = new EdgesGeometry(g, 30).getAttribute('position').array as Float32Array;
      const mine = got.position.subarray(got.ranges[e * 2]! * 3, (got.ranges[e * 2]! + got.ranges[e * 2 + 1]!) * 3);
      expect(mine.length, `element ${e} length`).toBe(ref.length);
      expect(sameArray(mine, ref), `element ${e} values`).toBe(true);
    }
    expect(got.ranges[1]).toBe(24); // cube: 12 edges, 2 vertices each
  });
});

describe('edges option', () => {
  /** n tiny boxes with normals, so the build does no smoothing. */
  function boxes(n: number): RawModel {
    const positions = Float32Array.from([0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1]);
    const normals = Float32Array.from([0, 0, 1, 0, 0, 1, 0, 0, 1, 0, 0, 1]);
    const indices = Uint32Array.from([0, 1, 2, 0, 2, 3, 0, 3, 1, 1, 3, 2]);
    return {
      fileName: 'many.ifc', schema: 'IFC4', storeys: [], voids: [], fills: [], ports: [], systems: [],
      elements: Array.from({ length: n }, (_, i) => ({
        expressId: i + 1, globalId: `g${i}`, ifcClass: 'IfcWall', name: `w${i}`, storeyExpressId: null, materialName: '', color: null,
        positions: positions.map((x, k) => (k % 3 === 0 ? x + i * 2 : x)), indices, normals,
      })),
    };
  }

  it('auto builds edges up to the limit and skips them above it; all and none override', () => {
    expect(AUTO_EDGES_MAX_ELEMENTS).toBe(50000);
    const small = buildMergedData([boxes(10)], { edges: 'auto' });
    expect(small.edgesSkipped).toBe(false);
    expect(small.arrays.edgePosition.length).toBeGreaterThan(0);
    expect(buildMergedData([boxes(10)], { edges: 'none' }).arrays.edgePosition.length).toBe(0);
    const big = buildMergedData([boxes(AUTO_EDGES_MAX_ELEMENTS + 1)], { edges: 'auto' });
    expect(big.edgesSkipped).toBe(true);
    expect(big.arrays.edgePosition.length).toBe(0);
    expect(big.arrays.edgeRanges.length).toBe((AUTO_EDGES_MAX_ELEMENTS + 1) * 2);
    // a skipped model still wraps into a valid geometry with an empty, cullable edge set
    const g = MergedGeometry.fromArrays(buildMergedData([boxes(10)], { edges: 'none' }).arrays);
    expect(g.edges.getAttribute('position').count).toBe(0);
    expect(g.edges.boundingSphere).not.toBeNull();
    expect(g.edgeRanges.every((r) => r.count === 0)).toBe(true);
  }, 60000);

  it('reports merge and edge progress', () => {
    const phases: string[] = [];
    buildMergedData([boxes(40)], { edges: 'all', onProgress: (p) => { if (!phases.includes(p.phase)) phases.push(p.phase); } });
    expect(phases).toEqual(['merge', 'edges']);
    const skipped: string[] = [];
    buildMergedData([boxes(40)], { edges: 'none', onProgress: (p) => { if (p.phase === 'edges') skipped.push(String(p.skipped)); } });
    expect(skipped).toEqual(['none']);
  });
});
