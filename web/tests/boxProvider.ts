// Axis-aligned box mock of GeometryProvider, plus small model builders.

import { Box3, Vector3 } from 'three';
import type { ElementId, ElementRecord, GeometryProvider, SceneModel } from '../src/types';

export type BoxTuple = [number, number, number, number, number, number];

/** Van der Corput radical inverse, for deterministic low-discrepancy samples. */
function radical(i: number, base: number): number {
  let f = 1;
  let r = 0;
  while (i > 0) {
    f /= base;
    r += f * (i % base);
    i = Math.floor(i / base);
  }
  return r;
}

export class BoxGeometryProvider implements GeometryProvider {
  readonly boxes = new Map<ElementId, Box3>();
  /** Call counters, for coarse-to-fine tests. */
  readonly calls = { surfaceDistance: 0, intersects: 0, raycastAll: 0 };
  readonly callPairs: Array<['surfaceDistance' | 'intersects', ElementId, ElementId]> = [];

  constructor(boxes: Iterable<[ElementId, BoxTuple | Box3]>) {
    for (const [id, b] of boxes) {
      this.boxes.set(id, Array.isArray(b) ? new Box3(new Vector3(b[0], b[1], b[2]), new Vector3(b[3], b[4], b[5])) : b.clone());
    }
  }

  bounds(id: ElementId): Box3 {
    return this.get(id);
  }

  private get(id: ElementId): Box3 {
    const b = this.boxes.get(id);
    if (!b) throw new Error(`no box for element ${id}`);
    return b;
  }

  surfaceDistance(a: ElementId, b: ElementId): number {
    this.calls.surfaceDistance++;
    this.callPairs.push(['surfaceDistance', a, b]);
    const A = this.get(a);
    const B = this.get(b);
    const dx = Math.max(0, A.min.x - B.max.x, B.min.x - A.max.x);
    const dy = Math.max(0, A.min.y - B.max.y, B.min.y - A.max.y);
    const dz = Math.max(0, A.min.z - B.max.z, B.min.z - A.max.z);
    return Math.sqrt(dx * dx + dy * dy + dz * dz);
  }

  intersects(a: ElementId, b: ElementId): boolean {
    this.calls.intersects++;
    this.callPairs.push(['intersects', a, b]);
    return this.get(a).intersectsBox(this.get(b));
  }

  /**
   * Deterministic area-weighted samples: sample j picks a face by stratifying the cumulative
   * area at (j + 0.5) / count, and positions on the face with a (2, 3) Halton pair.
   */
  samplePoints(id: ElementId, count: number): Vector3[] {
    const b = this.get(id);
    const s = new Vector3().subVectors(b.max, b.min);
    // faces: [fixed axis, side(0=min,1=max), area]
    const faces: Array<[0 | 1 | 2, 0 | 1, number]> = [
      [0, 0, s.y * s.z], [0, 1, s.y * s.z],
      [1, 0, s.x * s.z], [1, 1, s.x * s.z],
      [2, 0, s.x * s.y], [2, 1, s.x * s.y],
    ];
    const total = faces.reduce((acc, f) => acc + f[2], 0);
    const out: Vector3[] = [];
    if (total <= 0) {
      for (let j = 0; j < count; j++) out.push(b.getCenter(new Vector3()));
      return out;
    }
    const cum: number[] = [];
    let acc = 0;
    for (const f of faces) cum.push((acc += f[2]) / total);
    const lo = b.min.toArray();
    const hi = b.max.toArray();
    for (let j = 0; j < count; j++) {
      const t = (j + 0.5) / count;
      let fi = cum.findIndex((c) => t <= c);
      if (fi < 0) fi = faces.length - 1;
      const [axis, side] = faces[fi]!;
      const u = radical(j + 1, 2);
      const v = radical(j + 1, 3);
      const p = [0, 0, 0];
      const free = [0, 1, 2].filter((a) => a !== axis);
      p[axis] = side === 0 ? lo[axis]! : hi[axis]!;
      p[free[0]!] = lo[free[0]!]! + u * (hi[free[0]!]! - lo[free[0]!]!);
      p[free[1]!] = lo[free[1]!]! + v * (hi[free[1]!]! - lo[free[1]!]!);
      out.push(new Vector3(p[0], p[1], p[2]));
    }
    return out;
  }

  /**
   * Slab-method segment/box test. A box is reported when the segment [0, maxDistance] meets it,
   * including when the origin is inside (the ray crosses the surface on the way out). Sorted by
   * entry distance (negative when the origin is inside).
   */
  raycastAll(origin: Vector3, dir: Vector3, maxDistance: number, candidates: ReadonlySet<ElementId>): ElementId[] {
    this.calls.raycastAll++;
    const hits: Array<[number, ElementId]> = [];
    // Allocation-free slab test (this runs candidates x rays times in the performance test).
    const ox = origin.x, oy = origin.y, oz = origin.z;
    const dx = dir.x, dy = dir.y, dz = dir.z;
    const EPS = 1e-12;
    for (const id of candidates) {
      const b = this.boxes.get(id);
      if (!b) continue;
      let tNear = -Infinity;
      let tFar = Infinity;
      let miss = false;
      for (let a = 0; a < 3 && !miss; a++) {
        const da = a === 0 ? dx : a === 1 ? dy : dz;
        const oa = a === 0 ? ox : a === 1 ? oy : oz;
        const lo = a === 0 ? b.min.x : a === 1 ? b.min.y : b.min.z;
        const hi = a === 0 ? b.max.x : a === 1 ? b.max.y : b.max.z;
        if (Math.abs(da) < EPS) {
          if (oa < lo || oa > hi) miss = true;
          continue;
        }
        let t0 = (lo - oa) / da;
        let t1 = (hi - oa) / da;
        if (t0 > t1) {
          const t = t0;
          t0 = t1;
          t1 = t;
        }
        if (t0 > tNear) tNear = t0;
        if (t1 < tFar) tFar = t1;
        if (tNear > tFar) miss = true;
      }
      if (miss || tFar < 0 || tNear > maxDistance) continue;
      hits.push([tNear, id]);
    }
    hits.sort((a, b) => a[0] - b[0]);
    return hits.map((h) => h[1]);
  }
}

export interface ElementSpec {
  cls: string;
  box: BoxTuple;
  storey?: number | null;
  name?: string;
}

export interface Scene {
  model: SceneModel;
  geometry: BoxGeometryProvider;
}

/** Build a SceneModel and matching BoxGeometryProvider. Element ids are the array indices. */
export function makeScene(
  specs: ElementSpec[],
  opts: {
    storeys?: Array<{ id: number; name: string; elevation: number }>;
    ports?: Array<[number, number]>;
    hosts?: Array<[number, number]>;
    systems?: Array<{ name: string; elements: number[] }>;
  } = {},
): Scene {
  const elements: ElementRecord[] = specs.map((s, id) => ({
    id,
    globalId: `g${id}`,
    ifcClass: s.cls,
    name: s.name,
    storey: s.storey === undefined ? 0 : s.storey,
    color: [0.7, 0.7, 0.7, 1],
    bounds: [...s.box] as BoxTuple,
  }));
  const model: SceneModel = {
    schema: 'xray-model/1',
    units: 'm',
    originShift: [0, 0, 0],
    storeys: opts.storeys ?? [{ id: 0, name: 'Level 0', elevation: 0 }],
    elements,
    relations: {
      voids: [],
      fills: [],
      hosts: opts.hosts ?? [],
      ports: opts.ports ?? [],
      systems: opts.systems ?? [],
    },
    byGlobalId: new Map(elements.map((e) => [e.globalId, e.id])),
  };
  const geometry = new BoxGeometryProvider(specs.map((s, id) => [id, s.box] as [number, BoxTuple]));
  return { model, geometry };
}
