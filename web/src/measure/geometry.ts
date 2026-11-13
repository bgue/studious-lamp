// Mesh queries for the measure tool, over the merged geometry. Kept here (not in render/geometry.ts).

import { Matrix4, Ray, Vector3, DoubleSide } from 'three';
import type { Camera } from 'three';
import type { HitPointInfo, MeshBVH } from 'three-mesh-bvh';
import type { MergedGeometry } from '../model/merged';
import type { V3 } from './maths';

const IDENTITY = new Matrix4();

export interface SurfaceHit {
  point: Vector3;
  element: number;
  faceIndex: number;
  distance: number;
  /** The three vertices of the hit triangle (world space). */
  triangle: [V3, V3, V3];
}

/** Triangle vertices of a merged-geometry face index (positions are world space already). */
export function triangleVertices(g: MergedGeometry, faceIndex: number): [V3, V3, V3] {
  const pos = g.geometry.getAttribute('position');
  const idx = g.geometry.getIndex()!;
  const v = (k: number): V3 => {
    const i = idx.getX(faceIndex * 3 + k);
    return [pos.getX(i), pos.getY(i), pos.getZ(i)];
  };
  return [v(0), v(1), v(2)];
}

/**
 * First surface under a ray, skipping hidden elements (the ray continues behind them). Both sides of triangles count.
 * `skip(id, point)` returns true for elements to ignore (user-hidden, fully transparent) or a hit point that is cut away (a view
 * mode). `range` limits the ray to distances in [near, far] (the part of it inside a section: src/bcf/clipRay.ts).
 */
export function firstSurfaceHit(g: MergedGeometry, ray: Ray, skip: (id: number, point: Vector3) => boolean, maxSkips = 256, range?: { near: number; far: number }): SurfaceHit | null {
  const bvh = g.bvh;
  let near = range?.near ?? 0;
  const far = range?.far ?? Infinity;
  for (let i = 0; i < maxSkips; i++) {
    const hit = bvh.raycastFirst(ray, DoubleSide, near, far);
    if (!hit || hit.faceIndex == null) return null;
    const id = g.elementOfTriangle(hit.faceIndex);
    if (id >= 0 && !skip(id, hit.point)) {
      return { point: hit.point.clone(), element: id, faceIndex: hit.faceIndex, distance: hit.distance, triangle: triangleVertices(g, hit.faceIndex) };
    }
    near = hit.distance + 1e-4;
  }
  return null;
}

/** Ray through an NDC point of a camera (call camera.updateMatrixWorld first). */
export function cameraRay(camera: Camera, ndcX: number, ndcY: number, out = new Ray()): Ray {
  const p = new Vector3(ndcX, ndcY, 0.5).unproject(camera as never);
  out.origin.setFromMatrixPosition(camera.matrixWorld);
  out.direction.copy(p).sub(out.origin).normalize();
  return out;
}

export interface ElementPair {
  distance: number;
  a: [number, number, number];
  b: [number, number, number];
  /** True when the meshes cross or one contains the other (distance 0). */
  touching: boolean;
}

/**
 * Minimum surface distance between two elements and the two closest points, from the per-element BVHs
 * (closestPointToGeometry). When the meshes intersect (or one contains the other) the distance is 0 and both points are
 * the centre of the overlap of the two bounds. `intersects` is geometry.intersects.
 */
export function elementDistance(g: MergedGeometry, a: number, b: number, intersects: (a: number, b: number) => boolean): ElementPair | null {
  const ga = g.subGeometry(a);
  const gb = g.subGeometry(b);
  if (!ga || !gb) return null;
  if (a === b) return null;
  if (intersects(a, b)) {
    const ba = g.bounds[a]!;
    const bb = g.bounds[b]!;
    const lo = new Vector3().copy(ba.min).max(bb.min);
    const hi = new Vector3().copy(ba.max).min(bb.max);
    const c = lo.add(hi).multiplyScalar(0.5);
    return { distance: 0, a: [c.x, c.y, c.z], b: [c.x, c.y, c.z], touching: true };
  }
  const t1: HitPointInfo = { point: new Vector3(), distance: 0, faceIndex: 0 };
  const t2: HitPointInfo = { point: new Vector3(), distance: 0, faceIndex: 0 };
  const hit = (ga.boundsTree as MeshBVH).closestPointToGeometry(gb, IDENTITY, t1, t2);
  if (!hit) return null;
  return { distance: hit.distance, a: [t1.point.x, t1.point.y, t1.point.z], b: [t2.point.x, t2.point.y, t2.point.z], touching: false };
}
