// @vitest-environment node
import { describe, expect, it } from 'vitest';
import { BoxGeometry, BufferGeometry, Matrix4, Quaternion, Vector3, Euler, Mesh, DoubleSide, Ray, SphereGeometry, CylinderGeometry, BufferAttribute } from 'three';
import { MeshBVH } from 'three-mesh-bvh';
import { cleanMesh, connectedPieces, creaseNormals, dropSmallPieces, meshBounds } from '../src/cleanup/simplify/mesh';
import { decimateMesh } from '../src/cleanup/simplify/decimate';
import { findRigidMatch, geometryHash, groupInstances, invertRigid, multiplyMatrices, pruneGroup } from '../src/cleanup/simplify/instances';
import { DETAIL_CLASSES, defaultDetailOptions, findSmallDetails } from '../src/cleanup/simplify/details';
import { findHiddenInterior } from '../src/cleanup/simplify/interior';
import type { RayCaster } from '../src/cleanup/simplify/interior';
import { runChunked, triangleCountOf } from '../src/cleanup/simplify/types';
import type { GeometrySource, MeshData } from '../src/cleanup/simplify/types';
import { buildCleanupPlan } from '../src/cleanup/plan';
import { SimplifyWork, previewClean, previewDecimation, previewInstances, previewSmallDetails } from '../src/cleanup/work';
import { MergedGeometry } from '../src/model/merged';
import { mergedSource } from '../src/cleanup/geometryAdapter';
import { exportCleanedGlb } from '../src/cleanup/glbExport';
import { parseModel } from '../src/model/loader';
import type { ElementRecord } from '../src/types';

function meshOfGeometry(g: BufferGeometry, m?: Matrix4): MeshData {
  const geo = g.index ? g : g;
  const c = geo.clone();
  if (m) c.applyMatrix4(m);
  const pos = c.getAttribute('position').array as Float32Array;
  const idx = c.index ? Uint32Array.from(c.index.array) : Uint32Array.from({ length: pos.length / 3 }, (_, i) => i);
  return { positions: Float32Array.from(pos), indices: idx };
}
const sphere = (m?: Matrix4): MeshData => meshOfGeometry(new SphereGeometry(1, 32, 24), m);
const box = (w = 1, h = 1, d = 1, m?: Matrix4): MeshData => meshOfGeometry(new BoxGeometry(w, h, d), m);
const move = (x: number, y: number, z: number, rx = 0, ry = 0, rz = 0): Matrix4 =>
  new Matrix4().compose(new Vector3(x, y, z), new Quaternion().setFromEuler(new Euler(rx, ry, rz)), new Vector3(1, 1, 1));

describe('weld and clean', () => {
  it('welds coincident vertices of a non-indexed mesh and keeps the shape', () => {
    const g = new BoxGeometry(1, 1, 1).toNonIndexed();
    const m: MeshData = { positions: Float32Array.from(g.getAttribute('position').array), indices: Uint32Array.from({ length: 36 }, (_, i) => i) };
    const r = cleanMesh(m);
    expect(r.stats.verticesBefore).toBe(36);
    expect(r.stats.verticesAfter).toBe(8);
    expect(r.stats.trianglesAfter).toBe(12);
    expect(meshBounds(r.mesh.positions)).toEqual(meshBounds(m.positions));
  });
  it('drops degenerate and zero-area triangles', () => {
    const m: MeshData = {
      positions: Float32Array.from([0, 0, 0, 1, 0, 0, 0, 1, 0, 2, 0, 0, 3, 0, 0]),
      indices: Uint32Array.from([0, 1, 2, 0, 0, 1, 1, 3, 4]), // good, repeated vertex, collinear
    };
    const r = cleanMesh(m);
    expect(r.stats.degenerate).toBe(2);
    expect(r.mesh.indices.length).toBe(3);
    expect(r.mesh.positions.length).toBe(9);
  });
  it('removes a duplicate coincident face but keeps one', () => {
    const m: MeshData = { positions: Float32Array.from([0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 1, 0]), indices: Uint32Array.from([0, 1, 2, 3, 4, 5]) };
    const r = cleanMesh(m);
    expect(r.stats.duplicateFaces).toBe(1);
    expect(triangleCountOf(r.mesh)).toBe(1);
    expect(cleanMesh(m, { dropDuplicateFaces: false }).stats.trianglesAfter).toBe(2);
  });
  it('splits connected pieces and drops the small ones, never the last', () => {
    const a = box(2, 2, 2);
    const b = box(0.02, 0.02, 0.02, new Matrix4().makeTranslation(5, 0, 0));
    const pos = Float32Array.from([...a.positions, ...b.positions]);
    const idx = Uint32Array.from([...a.indices, ...Array.from(b.indices, (v) => v + a.positions.length / 3)]);
    const m = { positions: pos, indices: idx };
    expect(connectedPieces(cleanMesh(m).mesh).length).toBe(2);
    const r = dropSmallPieces(cleanMesh(m).mesh, 0.1)!;
    expect(r.removedPieces).toBe(1);
    expect(triangleCountOf(r.mesh)).toBe(12);
    expect(dropSmallPieces(cleanMesh(a).mesh, 100)).toBeNull(); // one piece only: kept
  });
  it('crease normals keep a cube hard and a sphere smooth', () => {
    const c = creaseNormals(cleanMesh(box()).mesh);
    expect(c.positions.length / 3).toBe(24);
    const s = creaseNormals(cleanMesh(sphere()).mesh);
    expect(s.positions.length / 3).toBeLessThan(sphere().positions.length / 3 + 1);
  });
});

describe('decimation', () => {
  it('reduces a sphere by ratio and keeps the bounding box within tolerance', () => {
    const m = sphere();
    const before = meshBounds(m.positions);
    const r = decimateMesh(m, { ratio: 0.4 });
    expect(r.changed).toBe(true);
    expect(r.trianglesAfter).toBeLessThan(r.trianglesBefore * 0.6);
    const after = meshBounds(r.mesh.positions);
    for (let i = 0; i < 6; i++) expect(Math.abs(after[i]! - before[i]!)).toBeLessThan(0.08);
    expect(r.mesh.normals!.length).toBe(r.mesh.positions.length);
    for (const i of r.mesh.indices) expect(i).toBeLessThan(r.mesh.positions.length / 3);
  });
  it('a maximum error bounds how far it goes', () => {
    const m = sphere();
    const tight = decimateMesh(m, { maxError: 0.005 });
    const loose = decimateMesh(m, { maxError: 0.1 });
    expect(loose.trianglesAfter).toBeLessThan(tight.trianglesAfter);
    expect(loose.maxErrorReached).toBeLessThanOrEqual(0.1 + 1e-9);
    expect(tight.maxErrorReached).toBeLessThanOrEqual(0.005 + 1e-9);
  });
  it('keeps the corners and sharp edges of a flat plate while thinning its face', () => {
    const plate = meshOfGeometry(new BoxGeometry(4, 0.2, 2, 20, 1, 10));
    const before = meshBounds(plate.positions);
    const r = decimateMesh(plate, { ratio: 0.2 });
    expect(r.trianglesAfter).toBeLessThan(r.trianglesBefore * 0.7);
    expect(meshBounds(r.mesh.positions)).toEqual(before);
    // all eight corners survive
    const corners = new Set<string>();
    for (let i = 0; i < r.mesh.positions.length; i += 3) corners.add(`${r.mesh.positions[i]},${r.mesh.positions[i + 1]},${r.mesh.positions[i + 2]}`);
    for (const x of [-2, 2]) for (const y of [-0.1, 0.1]) for (const z of [-1, 1]) expect(corners.has(`${Math.fround(x)},${Math.fround(y)},${Math.fround(z)}`)).toBe(true);
  });
  it('leaves a plain box and small elements alone', () => {
    expect(decimateMesh(box(), { ratio: 0.1 }).changed).toBe(false);
    expect(decimateMesh(sphere(), { ratio: 0.1, minTriangles: 100000 }).changed).toBe(false);
  });
  it('thins a pipe along its length without losing its end caps', () => {
    const pipe = meshOfGeometry(new CylinderGeometry(0.1, 0.1, 3, 48, 12));
    const r = decimateMesh(pipe, { ratio: 0.3 });
    const b0 = meshBounds(pipe.positions), b1 = meshBounds(r.mesh.positions);
    for (let i = 0; i < 6; i++) expect(Math.abs(b1[i]! - b0[i]!)).toBeLessThan(0.02);
    expect(r.trianglesAfter).toBeLessThan(r.trianglesBefore * 0.5);
  });
});

describe('duplicate hash and instances', () => {
  const base = meshOfGeometry(new CylinderGeometry(0.2, 0.3, 1.5, 12));
  const moved = (m: Matrix4): MeshData => ({ positions: meshOfGeometry(new CylinderGeometry(0.2, 0.3, 1.5, 12), m).positions, indices: base.indices });

  it('hashes translated and rotated copies alike and different shapes apart', () => {
    const a = moved(move(10, 3, -2, 0.3, 1.1, 0.4));
    expect(geometryHash(a)).toBe(geometryHash(base));
    expect(geometryHash(meshOfGeometry(new CylinderGeometry(0.2, 0.31, 1.5, 12)))).not.toBe(geometryHash(base));
    expect(geometryHash(box())).not.toBe(geometryHash(base));
  });
  it('finds the rigid transform and rejects a mirror or a distorted copy', () => {
    const t = move(4, -1, 2, 0.5, -0.7, 1.9);
    const other = moved(t);
    const m = findRigidMatch(base, other)!;
    expect(m).not.toBeNull();
    const rebuilt = new Matrix4().fromArray(m);
    expect(rebuilt.elements.every((v, i) => Math.abs(v - t.elements[i]!) < 1e-4)).toBe(true);
    const mirrored: MeshData = { positions: other.positions.map((v, i) => (i % 3 === 0 ? -v : v)), indices: base.indices };
    expect(findRigidMatch(base, mirrored)).toBeNull();
    const bent = { positions: other.positions.slice(), indices: base.indices };
    bent.positions[3] = bent.positions[3]! + 0.05;
    expect(findRigidMatch(base, bent)).toBeNull();
  });
  it('groups repeats, with the lowest id as master, and rebases when the master goes', () => {
    const items = [0, 1, 2, 3].map((i) => ({ id: i, mesh: moved(move(i * 3, 0, i, 0, i * 0.4, 0)) }));
    items.push({ id: 4, mesh: box() });
    const groups = groupInstances(items);
    expect(groups).toHaveLength(1);
    expect(groups[0]!.master).toBe(0);
    expect(groups[0]!.members.map((m) => m.id)).toEqual([0, 1, 2, 3]);
    const p = pruneGroup(groups[0]!, (id) => id === 0)!;
    expect(p.master).toBe(1);
    // member 2 from the new master: M2 * M1^-1 maps master 1 mesh onto 2
    const m2 = p.members.find((m) => m.id === 2)!.matrix;
    const v = new Vector3(items[1]!.mesh.positions[0]!, items[1]!.mesh.positions[1]!, items[1]!.mesh.positions[2]!).applyMatrix4(new Matrix4().fromArray(m2));
    expect(v.distanceTo(new Vector3(items[2]!.mesh.positions[0]!, items[2]!.mesh.positions[1]!, items[2]!.mesh.positions[2]!))).toBeLessThan(1e-4);
    expect(multiplyMatrices(groups[0]!.members[1]!.matrix, invertRigid(groups[0]!.members[1]!.matrix)).every((x, i) => Math.abs(x - (i % 5 === 0 ? 1 : 0)) < 1e-9)).toBe(true);
    expect(pruneGroup(groups[0]!, (id) => id > 0)).toBeNull();
  });
  it('respects the group key (different colours do not share a mesh)', () => {
    const groups = groupInstances([{ id: 0, mesh: base, key: 'a' }, { id: 1, mesh: moved(move(1, 0, 0)), key: 'b' }]);
    expect(groups).toHaveLength(0);
  });
});

describe('small detail filter', () => {
  const items = [
    { id: 0, ifcClass: 'IfcWall', bounds: [0, 0, 0, 5, 0.2, 3] as const, triangles: 12 },
    { id: 1, ifcClass: 'IfcMechanicalFastener', bounds: [0, 0, 0, 0.03, 0.03, 0.04] as const, triangles: 40 },
    { id: 2, ifcClass: 'IfcFlowFitting', bounds: [0, 0, 0, 0.04, 0.04, 0.04] as const, triangles: 40 },
    { id: 3, ifcClass: 'IfcDiscreteAccessory', bounds: [0, 0, 0, 0.3, 0.3, 0.3] as const, triangles: 40 },
    { id: 4, ifcClass: 'IfcFastener', bounds: [0, 0, 0, 0.01, 0.01, 0.01] as const, triangles: 0 },
  ];
  it('filters by size, by volume and by class', () => {
    const o = defaultDetailOptions();
    expect(findSmallDetails(items, o)).toEqual([1, 2]); // < 50 mm, any class, no triangles skipped
    expect(findSmallDetails(items, { ...o, classes: DETAIL_CLASSES })).toEqual([1]);
    expect(findSmallDetails(items, { ...o, maxSize: 0, maxVolume: 0.03 })).toEqual([1, 2, 3]);
    expect(findSmallDetails(items, { ...o, maxSize: 0, maxVolume: 0 })).toEqual([]);
  });
});

describe('hidden interior', () => {
  function caster(parts: Array<{ id: number; mesh: MeshData }>): RayCaster {
    let total = 0;
    const pos: number[] = [], idx: number[] = [], owner: number[] = [];
    for (const p of parts) {
      for (const v of p.mesh.positions) pos.push(v);
      for (const i of p.mesh.indices) idx.push(i + total);
      for (let t = 0; t < p.mesh.indices.length / 3; t++) owner.push(p.id);
      total += p.mesh.positions.length / 3;
    }
    const g = new BufferGeometry();
    g.setAttribute('position', new BufferAttribute(Float32Array.from(pos), 3));
    g.setIndex(idx);
    const bvh = new MeshBVH(g, { indirect: true });
    const ray = new Ray();
    return {
      firstHit(ox, oy, oz, dx, dy, dz) {
        ray.origin.set(ox, oy, oz);
        ray.direction.set(dx, dy, dz);
        const h = bvh.raycastFirst(ray, DoubleSide);
        return h && h.faceIndex != null ? { id: owner[h.faceIndex]!, t: h.distance } : null;
      },
    };
  }
  it('reports an element sealed inside a closed shell and keeps an exposed one', () => {
    const shell = box(4, 4, 4);
    const inner = box(1, 1, 1);
    const outer = box(1, 1, 1, new Matrix4().makeTranslation(8, 0, 0));
    const parts = [{ id: 0, mesh: shell }, { id: 1, mesh: inner }, { id: 2, mesh: outer }];
    const items = parts.map((p) => ({ id: p.id, ifcClass: 'IfcBuildingElementProxy', mesh: () => p.mesh }));
    return findHiddenInterior(items, caster(parts)).then((r) => {
      expect(r).toEqual([1]); // the shell itself is exposed (its own hits are passed through), the loose box too
    });
  });
  it('an open shell does not hide what is inside', async () => {
    // two walls only: a ray can leave sideways
    const walls = [{ id: 0, mesh: box(4, 4, 0.1, new Matrix4().makeTranslation(0, 0, 2)) }, { id: 1, mesh: box(4, 4, 0.1, new Matrix4().makeTranslation(0, 0, -2)) }, { id: 2, mesh: box(1, 1, 1) }];
    const items = walls.map((p) => ({ id: p.id, ifcClass: 'IfcWall', mesh: () => p.mesh }));
    expect(await findHiddenInterior(items, caster(walls))).toEqual([]);
  });
  it('glazing does not block, so what lies behind a window stays', async () => {
    const shell = box(4, 4, 4);
    const inner = box(1, 1, 1);
    const parts = [{ id: 0, mesh: shell, cls: 'IfcWindow' }, { id: 1, mesh: inner, cls: 'IfcWall' }];
    const items = parts.map((p) => ({ id: p.id, ifcClass: p.cls, mesh: () => p.mesh }));
    expect(await findHiddenInterior(items, caster(parts))).toEqual([]);
  });
  it('stops at a chunk boundary when aborted', async () => {
    const signal = { aborted: false };
    const parts = [0, 1, 2, 3, 4, 5].map((i) => ({ id: i, mesh: box(1, 1, 1, new Matrix4().makeTranslation(i * 3, 0, 0)) }));
    const items = parts.map((p) => ({ id: p.id, ifcClass: 'IfcWall', mesh: () => { signal.aborted = true; return p.mesh; } }));
    expect(await findHiddenInterior(items, caster(parts), {}, { signal, budgetMs: 0, yieldFn: async () => {} })).toBeNull();
  });
});

describe('chunked runner', () => {
  it('yields between chunks and reports progress', async () => {
    let yields = 0;
    const seen: number[] = [];
    const ok = await runChunked(Array.from({ length: 5 }, (_, i) => i), () => {}, { budgetMs: 0, yieldFn: async () => { yields++; }, onProgress: (d) => seen.push(d) });
    expect(ok).toBe(true);
    expect(yields).toBe(5);
    expect(seen[seen.length - 1]).toBe(5);
  });
});

// ---------------------------------------------------------------- a small model with real merged geometry

function makeModel(): { merged: MergedGeometry; elements: ElementRecord[]; src: GeometrySource } {
  const specs: Array<{ gid: string; cls: string; name: string; mesh: MeshData; color: [number, number, number, number] }> = [
    { gid: 'slab-gid-0000000000001', cls: 'IfcSlab', name: 'Slab', mesh: box(10, 0.3, 10), color: [0.6, 0.6, 0.6, 1] },
    { gid: 'ball-gid-0000000000002$', cls: 'IfcBuildingElementProxy', name: 'Dome', mesh: sphere(move(0, 3, 0)), color: [0.2, 0.5, 0.8, 1] },
    { gid: 'rail-gid-0000000000003', cls: 'IfcRailing', name: 'Rail A', mesh: meshOfGeometry(new CylinderGeometry(0.1, 0.1, 2, 16), move(4, 1, 0, 0.1, 0.2, 0.3)), color: [0.5, 0.5, 0.5, 1] },
    { gid: 'rail-gid-0000000000004', cls: 'IfcRailing', name: 'Rail B', mesh: meshOfGeometry(new CylinderGeometry(0.1, 0.1, 2, 16), move(-4, 1, 3, 0.1, 1.2, 0.3)), color: [0.5, 0.5, 0.5, 1] },
    { gid: 'rail-gid-0000000000005', cls: 'IfcRailing', name: 'Rail C', mesh: meshOfGeometry(new CylinderGeometry(0.1, 0.1, 2, 16), move(0, 1, -4, 1, 0, 0)), color: [0.5, 0.5, 0.5, 1] },
    { gid: 'bolt-gid-0000000000006', cls: 'IfcMechanicalFastener', name: 'Bolt', mesh: box(0.02, 0.02, 0.04, move(2, 2, 2)), color: [0.3, 0.3, 0.3, 1] },
  ];
  const parts = specs.map((s) => {
    const g = new BufferGeometry();
    g.setAttribute('position', new BufferAttribute(s.mesh.positions, 3));
    const n = new BufferGeometry();
    n.setAttribute('position', g.getAttribute('position'));
    n.setIndex(new BufferAttribute(s.mesh.indices, 1));
    n.computeVertexNormals();
    return [{ geometry: n, matrix: new Matrix4() }];
  });
  const merged = new MergedGeometry(parts);
  const elements: ElementRecord[] = specs.map((s, i) => ({
    id: i, globalId: s.gid, ifcClass: s.cls, name: s.name, storey: null, color: s.color,
    bounds: merged.bounds[i]!.isEmpty() ? [0, 0, 0, 0, 0, 0] : [merged.bounds[i]!.min.x, merged.bounds[i]!.min.y, merged.bounds[i]!.min.z, merged.bounds[i]!.max.x, merged.bounds[i]!.max.y, merged.bounds[i]!.max.z],
    props: i === 0 ? { 'Pset.Fire': 'REI60' } : undefined,
  }));
  return { merged, elements, src: mergedSource(merged) };
}

describe('staged tools and the CleanupPlan', () => {
  it('previews decimation, details, clean and instances without touching the model, then commits', async () => {
    const { elements, src } = makeModel();
    const work = new SimplifyWork();
    const ctx = { src, elements, work, chunk: { budgetMs: 1000 } };
    const dec = (await previewDecimation(ctx, { mode: 'ratio', ratio: 0.4, minTriangles: 100, sharpAngle: 30, maxError: 0 }))!;
    expect(dec.ids).toContain(1);
    expect(dec.ids).not.toContain(0); // the box slab is below minTriangles and has nothing to lose
    expect(dec.trianglesAfter).toBeLessThan(dec.trianglesBefore);
    expect(dec.bytesAfter).toBeLessThan(dec.bytesBefore);
    expect(work.isEmpty).toBe(true);
    work.commit(dec);
    expect(work.replacements.has(1)).toBe(true);

    const det = (await previewSmallDetails(ctx, { ...defaultDetailOptions(), classes: DETAIL_CLASSES }))!;
    expect(det.ids).toEqual([5]);
    work.commit(det);
    expect(work.removals.get(5)).toBe('small detail');

    const inst = (await previewInstances(ctx))!;
    expect(inst.groups).toHaveLength(1);
    expect(inst.groups![0]!.members.map((m) => m.id)).toEqual([2, 3, 4]);
    work.commit(inst);
    // changing a member's mesh drops its group
    const cl = (await previewClean(ctx, { weldTolerance: 1e-4, dropDegenerate: true, dropDuplicateFaces: true }))!;
    expect(cl.ids.length).toBeGreaterThan(0);

    const plan = buildCleanupPlan({ elements, source: src, removed: new Map([[5, ['small detail']]]), replacements: work.replacements, groups: work.groups });
    expect(plan.schema).toBe('xray-cleanup-plan/1');
    expect(plan.removedGlobalIds).toEqual(['bolt-gid-0000000000006']);
    expect(plan.removalReasons['bolt-gid-0000000000006']).toEqual(['small detail']);
    expect(plan.replacements.map((r) => r.globalId)).toEqual(['ball-gid-0000000000002$']);
    const rep = plan.replacements[0]!;
    expect(rep.trianglesAfter).toBeLessThan(rep.trianglesBefore);
    expect(rep.ops).toEqual(['decimate']);
    expect(rep.mesh.normals.length).toBe(rep.mesh.positions.length);
    expect(plan.mergedGroups).toHaveLength(1);
    expect(plan.mergedGroups[0]!.masterGlobalId).toBe('rail-gid-0000000000003');
    expect(plan.mergedGroups[0]!.members.map((m) => m.globalId)).toEqual(['rail-gid-0000000000003', 'rail-gid-0000000000004', 'rail-gid-0000000000005']);
    const s = plan.stats;
    expect(s.elementsBefore).toBe(6);
    expect(s.elementsAfter).toBe(5);
    expect(s.removed).toBe(1);
    expect(s.removedByReason).toEqual({ 'small detail': 1 });
    expect(s.simplified).toBe(1);
    expect(s.instanceGroups).toBe(1);
    expect(s.instancedElements).toBe(2);
    expect(s.trianglesAfter).toBeLessThan(s.trianglesBefore);
    expect(s.trianglesStoredAfter).toBeLessThan(s.trianglesAfter);
    expect(s.bytesAfter).toBeLessThan(s.bytesBefore);
    // an empty plan changes nothing
    const none = buildCleanupPlan({ elements, source: src, removed: new Map(), replacements: new Map(), groups: [] }).stats;
    expect(none.trianglesAfter).toBe(none.trianglesBefore);
    expect(none.bytesAfter).toBe(none.bytesBefore);
  });
});

// ---------------------------------------------------------------- glb round trip

// GLTFExporter reads blobs with FileReader, which node lacks.
class NodeFileReader {
  result: ArrayBuffer | null = null;
  onloadend: (() => void) | null = null;
  readAsArrayBuffer(b: Blob): void {
    void b.arrayBuffer().then((r) => { this.result = r; this.onloadend?.(); });
  }
}
(globalThis as { FileReader?: unknown }).FileReader ??= NodeFileReader;

function glbJson(glb: ArrayBuffer): { nodes: Array<{ name?: string; mesh?: number; extras?: Record<string, unknown> }>; meshes: unknown[]; accessors: unknown[] } {
  const dv = new DataView(glb);
  expect(dv.getUint32(0, true)).toBe(0x46546c67);
  const len = dv.getUint32(12, true);
  return JSON.parse(new TextDecoder().decode(new Uint8Array(glb, 20, len)));
}

describe('glb export round trip', () => {
  it('writes nodes named by GlobalId with extras, shares instanced meshes and re-opens in the viewer loader', async () => {
    const { elements, src } = makeModel();
    const work = new SimplifyWork();
    const ctx = { src, elements, work, chunk: { budgetMs: 1000 } };
    work.commit((await previewDecimation(ctx, { mode: 'ratio', ratio: 0.4, minTriangles: 100, sharpAngle: 30, maxError: 0 }))!);
    work.commit((await previewSmallDetails(ctx, { ...defaultDetailOptions(), classes: DETAIL_CLASSES }))!);
    work.commit((await previewInstances(ctx))!);
    const plan = buildCleanupPlan({ elements, source: src, removed: new Map([[5, ['small detail']]]), replacements: work.replacements, groups: work.groups });
    const glb = await exportCleanedGlb(elements, src, plan, { stripProps: false });
    const json = glbJson(glb);
    const names = json.nodes.map((n) => n.name);
    expect(names.sort()).toEqual(elements.filter((e) => e.id !== 5).map((e) => e.globalId).sort());
    const slab = json.nodes.find((n) => n.name === 'slab-gid-0000000000001')!;
    expect(slab.extras).toMatchObject({ id: 0, ifcClass: 'IfcSlab', ifcName: 'Slab', props: { 'Pset.Fire': 'REI60' } });
    // three rails share one glTF mesh
    const railMeshes = new Set(json.nodes.filter((n) => n.name!.startsWith('rail-')).map((n) => n.mesh));
    expect(railMeshes.size).toBe(1);
    expect(json.meshes.length).toBe(3); // slab, dome, one rail mesh

    const loaded = await parseModel(glb);
    expect(loaded.model.elements).toHaveLength(5);
    const dome = loaded.model.elements.find((e) => e.globalId === 'ball-gid-0000000000002$')!;
    expect(dome.ifcClass).toBe('IfcBuildingElementProxy');
    expect(dome.name).toBe('Dome');
    expect(loaded.model.byGlobalId.get('slab-gid-0000000000001')).toBeDefined();
    expect(loaded.model.elements.find((e) => e.globalId === 'slab-gid-0000000000001')!.props).toEqual({ 'Pset.Fire': 'REI60' });
    // instanced rails come back at their original places
    for (const gid of ['rail-gid-0000000000003', 'rail-gid-0000000000004', 'rail-gid-0000000000005']) {
      const orig = elements.find((e) => e.globalId === gid)!;
      const back = loaded.model.elements.find((e) => e.globalId === gid)!;
      for (let i = 0; i < 6; i++) expect(Math.abs(back.bounds[i]! - orig.bounds[i]!)).toBeLessThan(2e-3);
    }
    // the dome has fewer triangles than the original
    const idx = loaded.geometry.ranges[dome.id]!.count / 3;
    expect(idx).toBeLessThan(plan.replacements[0]!.trianglesBefore);
    // the file is smaller than the unmodified export
    const plain = await exportCleanedGlb(elements, src, buildCleanupPlan({ elements, source: src, removed: new Map(), replacements: new Map(), groups: [] }), { stripProps: false });
    expect(glb.byteLength).toBeLessThan(plain.byteLength);
  });
  it('strips names and properties on request', async () => {
    const { elements, src } = makeModel();
    const plan = buildCleanupPlan({ elements, source: src, removed: new Map(), replacements: new Map(), groups: [], stripProps: true });
    const glb = await exportCleanedGlb(elements, src, plan, { stripProps: true });
    const slab = glbJson(glb).nodes.find((n) => n.name === 'slab-gid-0000000000001')!;
    expect(slab.extras).toEqual({ id: 0, ifcClass: 'IfcSlab' });
  });
});
void Mesh;
