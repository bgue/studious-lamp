// Closest model surface point for ICP (icp.ts ClosestFn) on three-mesh-bvh trees: the merged geometry's BVH, or the
// focus elements' own BVHs. With a normal filter, only triangles whose normal is compatible with the cloud point's
// normal count (a shapecast like three-mesh-bvh's closestPointToPoint, with the normal test in intersectsTriangle):
// a noise point beyond the middle of a thin wall then still finds the face it belongs to, not the far face.

import { Vector3 } from 'three';
import type { MeshBVH } from 'three-mesh-bvh';
import type { ClosestFn } from './icp';

export function bvhClosestFn(trees: MeshBVH[]): ClosestFn {
  const p = new Vector3();
  const tmp = new Vector3();
  const best = new Vector3();
  const nrm = new Vector3();
  const bestN = new Vector3();
  return (x, y, z, max, out, filter) => {
    p.set(x, y, z);
    let bestD2 = max * max;
    let found = false;
    const fx = filter ? filter.n[0]! : 0, fy = filter ? filter.n[1]! : 0, fz = filter ? filter.n[2]! : 0;
    for (const t of trees) {
      t.shapecast({
        boundsTraverseOrder: (box) => tmp.copy(p).clamp(box.min, box.max).distanceToSquared(p),
        intersectsBounds: (_box, _leaf, score) => (score ?? Infinity) <= bestD2,
        intersectsTriangle: (tri) => {
          tri.getNormal(nrm);
          if (filter) {
            const dot = nrm.x * fx + nrm.y * fy + nrm.z * fz;
            if (filter.oriented ? dot < filter.cos : Math.abs(dot) < filter.cos) return false;
          }
          tri.closestPointToPoint(p, tmp);
          const d2 = tmp.distanceToSquared(p);
          if (d2 <= bestD2) {
            bestD2 = d2;
            best.copy(tmp);
            bestN.copy(nrm);
            found = true;
          }
          return false;
        },
      });
    }
    if (!found) return Infinity;
    out.p[0] = best.x; out.p[1] = best.y; out.p[2] = best.z;
    out.n[0] = bestN.x; out.n[1] = bestN.y; out.n[2] = bestN.z;
    return Math.sqrt(bestD2);
  };
}
