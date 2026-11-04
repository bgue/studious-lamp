// GeometryProvider over the merged geometry, using three-mesh-bvh.

import { Box3, DoubleSide, Matrix4, Ray, Vector3 } from 'three';
import type { BufferGeometry } from 'three';
import type { MeshBVH, HitPointInfo } from 'three-mesh-bvh';
import type { ElementId, GeometryProvider } from '../types';
import type { MergedGeometry } from '../model/merged';

const IDENTITY = new Matrix4();

function pairKey(a: ElementId, b: ElementId): string {
  return a < b ? `${a}:${b}` : `${b}:${a}`;
}

/** mulberry32 PRNG: tiny, fast, deterministic. */
function mulberry32(seed: number): () => number {
  let s = seed >>> 0;
  return () => {
    s = (s + 0x6d2b79f5) >>> 0;
    let t = s;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

interface AreaTable {
  /** cumulative triangle areas, length = triangle count */
  cumulative: Float64Array;
  total: number;
}

export class BvhGeometryProvider implements GeometryProvider {
  private readonly merged: MergedGeometry;
  private readonly distCache = new Map<string, number>();
  private readonly intersectCache = new Map<string, boolean>();
  private readonly areaCache = new Map<ElementId, AreaTable>();
  private readonly sampleCache = new Map<ElementId, Vector3[]>();

  // scratch
  private readonly ray = new Ray();
  private readonly t1: HitPointInfo = { point: new Vector3(), distance: 0, faceIndex: 0 };
  private readonly t2: HitPointInfo = { point: new Vector3(), distance: 0, faceIndex: 0 };
  private readonly va = new Vector3();
  private readonly vb = new Vector3();
  private readonly vc = new Vector3();
  private readonly vd = new Vector3();

  constructor(merged: MergedGeometry) {
    this.merged = merged;
  }

  /** Stored Box3 (world space). Treat as read-only. Empty box for elements without geometry. */
  bounds(id: ElementId): Box3 {
    return this.merged.bounds[id]!;
  }

  /**
   * All-hits raycast (`firstHitOnly = false` semantics: `MeshBVH.raycast`, not `raycastFirst`) over
   * the merged geometry with both sides counted, so a ray entering and leaving a solid hits it twice.
   * Hits beyond maxDistance are dropped by the BVH (far = maxDistance); the triangle index is mapped
   * to an element id with a binary search on the range table; hits are filtered to `candidates`,
   * deduplicated per element keeping the nearest, and returned nearest first.
   */
  raycastAll(origin: Vector3, dir: Vector3, maxDistance: number, candidates: ReadonlySet<ElementId>): ElementId[] {
    this.ray.origin.copy(origin);
    this.ray.direction.copy(dir);
    const hits = this.merged.bvh.raycast(this.ray, DoubleSide, 0, maxDistance);
    const nearest = new Map<ElementId, number>();
    for (const h of hits) {
      if (h.distance > maxDistance || h.faceIndex === undefined || h.faceIndex === null) continue;
      const id = this.merged.elementOfTriangle(h.faceIndex);
      if (id < 0 || !candidates.has(id)) continue;
      const prev = nearest.get(id);
      if (prev === undefined || h.distance < prev) nearest.set(id, h.distance);
    }
    return [...nearest.entries()].sort((x, y) => x[1] - y[1]).map((e) => e[0]);
  }

  /**
   * Surface-intersection OR containment.
   *  1. Bounds overlap test (cheap reject).
   *  2. `bvhA.intersectsGeometry(subB, identity)`: triangle-triangle test using both per-element BVHs.
   *  3. If no surfaces cross, one mesh is either fully inside the other or fully apart. Containment is
   *     decided by a closest-point sign check: take one vertex of A; if it lies inside B's bounds, find
   *     the closest point on B and test the sign of (p - closest) . faceNormal (negative = inside, assuming
   *     outward-facing winding). Then the same with the roles swapped. (This is the "closest-point sign
   *     check" variant, not the 8-corner variant: corners of a bounds box are not on the mesh, so they
   *     would give false positives for L-shaped or hollow elements.)
   */
  intersects(a: ElementId, b: ElementId): boolean {
    if (a === b) return this.merged.hasGeometry(a);
    const key = pairKey(a, b);
    const cached = this.intersectCache.get(key);
    if (cached !== undefined) return cached;
    const result = this.computeIntersects(a, b);
    this.intersectCache.set(key, result);
    return result;
  }

  private computeIntersects(a: ElementId, b: ElementId): boolean {
    const ba = this.merged.bounds[a];
    const bb = this.merged.bounds[b];
    if (!ba || !bb || ba.isEmpty() || bb.isEmpty() || !ba.intersectsBox(bb)) return false;
    const ga = this.merged.subGeometry(a);
    const gb = this.merged.subGeometry(b);
    if (!ga || !gb) return false;
    const bvhA = ga.boundsTree as MeshBVH;
    if (bvhA.intersectsGeometry(gb, IDENTITY)) return true;
    return this.insideOf(ga, gb, bb) || this.insideOf(gb, ga, ba);
  }

  /** True when the first vertex of `inner` lies inside the closed mesh `outer`. */
  private insideOf(inner: BufferGeometry, outer: BufferGeometry, outerBounds: Box3): boolean {
    const p = this.va.fromBufferAttribute(inner.getAttribute('position'), 0);
    if (!outerBounds.containsPoint(p)) return false;
    const bvh = outer.boundsTree as MeshBVH;
    const hit = bvh.closestPointToPoint(p, this.t1);
    if (!hit) return false;
    const idx = outer.getIndex()!;
    const pos = outer.getAttribute('position');
    const f = hit.faceIndex * 3;
    this.vb.fromBufferAttribute(pos, idx.getX(f));
    this.vc.fromBufferAttribute(pos, idx.getX(f + 1));
    this.vd.fromBufferAttribute(pos, idx.getX(f + 2));
    this.vc.sub(this.vb);
    this.vd.sub(this.vb);
    const n = this.vc.cross(this.vd); // face normal (unnormalised, CCW outward)
    this.vb.copy(p).sub(hit.point);
    return n.dot(this.vb) < 0;
  }

  /** Lower bound on the surface distance: the Euclidean distance between the two Box3s (0 if they overlap). */
  boundsDistance(a: ElementId, b: ElementId): number {
    const ba = this.merged.bounds[a];
    const bb = this.merged.bounds[b];
    if (!ba || !bb || ba.isEmpty() || bb.isEmpty()) return Infinity;
    const dx = Math.max(0, ba.min.x - bb.max.x, bb.min.x - ba.max.x);
    const dy = Math.max(0, ba.min.y - bb.max.y, bb.min.y - ba.max.y);
    const dz = Math.max(0, ba.min.z - bb.max.z, bb.min.z - ba.max.z);
    return Math.hypot(dx, dy, dz);
  }

  /**
   * Exact shortest surface-to-surface distance, 0 when the meshes intersect or one contains the other.
   * Exact values are cached per unordered pair (`${min}:${max}`).
   *
   * Optional `maxDistance`: callers that only care about distances below a threshold (the buffer
   * radius) pass it. If the Box3 lower bound already exceeds it, or the exact search finds nothing
   * within it, a value strictly greater than `maxDistance` is returned (the Box3 lower bound, at
   * least maxDistance + 1e-6) and NOT cached, since it is not the exact distance.
   */
  surfaceDistance(a: ElementId, b: ElementId, maxDistance = Infinity): number {
    if (a === b) return 0;
    const key = pairKey(a, b);
    const cached = this.distCache.get(key);
    if (cached !== undefined) return cached;

    const lower = this.boundsDistance(a, b);
    if (lower === Infinity) return Infinity;
    if (lower > maxDistance) return lower;

    if (this.intersects(a, b)) {
      this.distCache.set(key, 0);
      return 0;
    }
    const ga = this.merged.subGeometry(a);
    const gb = this.merged.subGeometry(b);
    if (!ga || !gb) return Infinity;
    const bvhA = ga.boundsTree as MeshBVH;
    const hit = bvhA.closestPointToGeometry(gb, IDENTITY, this.t1, this.t2, 0, maxDistance);
    if (!hit) return Math.max(lower, maxDistance + 1e-6);
    const d = hit.distance;
    if (d > maxDistance) return d;
    this.distCache.set(key, d);
    return d;
  }

  /** Drop cached distances / intersections (call if geometry changes; not needed for static models). */
  clearCaches(): void {
    this.distCache.clear();
    this.intersectCache.clear();
  }

  /**
   * Area-weighted points on the element surface (world space). Deterministic: the PRNG is seeded
   * from the element id only, so the result for `count` is a prefix of the result for any larger
   * count, and identical between calls. The returned array and its Vector3s are cached and shared:
   * treat them as read-only (use .clone() before mutating). Elements without triangles return [].
   */
  samplePoints(id: ElementId, count: number): Vector3[] {
    const cached = this.sampleCache.get(id);
    if (cached && cached.length >= count) return cached.length === count ? cached : cached.slice(0, count);
    const sub = this.merged.subGeometry(id);
    if (!sub || count <= 0) return [];
    const table = this.areaTable(id, sub);
    if (table.total <= 0) return [];

    const pos = sub.getAttribute('position');
    const idx = sub.getIndex()!;
    const rand = mulberry32((Math.imul(id + 1, 0x9e3779b1) ^ 0x85ebca6b) >>> 0);
    const cum = table.cumulative;
    const out: Vector3[] = [];
    const a = new Vector3();
    const b = new Vector3();
    const c = new Vector3();
    for (let k = 0; k < count; k++) {
      const target = rand() * table.total;
      let lo = 0;
      let hi = cum.length - 1;
      while (lo < hi) {
        const mid = (lo + hi) >> 1;
        if (cum[mid]! < target) lo = mid + 1;
        else hi = mid;
      }
      a.fromBufferAttribute(pos, idx.getX(lo * 3));
      b.fromBufferAttribute(pos, idx.getX(lo * 3 + 1));
      c.fromBufferAttribute(pos, idx.getX(lo * 3 + 2));
      let u = rand();
      let v = rand();
      if (u + v > 1) {
        u = 1 - u;
        v = 1 - v;
      }
      out.push(new Vector3().copy(a).addScaledVector(b.clone().sub(a), u).addScaledVector(c.clone().sub(a), v));
    }
    this.sampleCache.set(id, out);
    return out;
  }

  private areaTable(id: ElementId, sub: BufferGeometry): AreaTable {
    let t = this.areaCache.get(id);
    if (t) return t;
    const pos = sub.getAttribute('position');
    const idx = sub.getIndex()!;
    const tris = idx.count / 3;
    const cumulative = new Float64Array(tris);
    let total = 0;
    const a = this.va;
    const b = this.vb;
    const c = this.vc;
    for (let i = 0; i < tris; i++) {
      a.fromBufferAttribute(pos, idx.getX(i * 3));
      b.fromBufferAttribute(pos, idx.getX(i * 3 + 1));
      c.fromBufferAttribute(pos, idx.getX(i * 3 + 2));
      b.sub(a);
      c.sub(a);
      total += 0.5 * b.cross(c).length();
      cumulative[i] = total;
    }
    t = { cumulative, total };
    this.areaCache.set(id, t);
    return t;
  }
}
