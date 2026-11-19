// CleanupGeometry over the merged geometry and the BVH provider.

import type { MergedGeometry } from '../model/merged';
import type { BvhGeometryProvider } from '../render/geometry';
import { meshVolumeOf } from './analysis';
import type { CleanupGeometry } from './analysis';
import type { GeometrySource } from './simplify/types';
import type { RayCaster } from './simplify/interior';
import { DoubleSide, Ray } from 'three';

export function mergedCleanupGeometry(merged: MergedGeometry, provider?: BvhGeometryProvider | null): CleanupGeometry {
  const pos = merged.geometry.getAttribute('position').array;
  const idx = merged.geometry.getIndex()!.array;
  const volCache = new Map<number, number | null>();
  const g: CleanupGeometry = {
    triangleCount: (id) => Math.floor((merged.ranges[id]?.count ?? 0) / 3),
    meshVolume: (id) => {
      if (volCache.has(id)) return volCache.get(id)!;
      const r = merged.ranges[id];
      let v: number | null = null;
      if (r && r.count > 0) {
        const m = meshVolumeOf(pos, idx, r.start / 3, r.count / 3);
        v = m.closed ? m.volume : null;
      }
      volCache.set(id, v);
      return v;
    },
  };
  if (provider) g.surfaceDistance = (a, b, max) => provider.surfaceDistance(a, b, max);
  return g;
}

/** The merged buffers as a GeometrySource (no copies). */
export function mergedSource(merged: MergedGeometry): GeometrySource {
  return {
    position: merged.geometry.getAttribute('position').array as Float32Array,
    normal: merged.geometry.getAttribute('normal').array as Float32Array,
    index: merged.geometry.getIndex()!.array as Uint32Array,
    ranges: merged.ranges,
    vertexRanges: merged.vertexRanges,
  };
}

/** Nearest-hit ray caster over the merged BVH (both triangle sides count). */
export function mergedRayCaster(merged: MergedGeometry): RayCaster {
  const ray = new Ray();
  const bvh = merged.bvh;
  return {
    firstHit(ox, oy, oz, dx, dy, dz) {
      ray.origin.set(ox, oy, oz);
      ray.direction.set(dx, dy, dz);
      const h = bvh.raycastFirst(ray, DoubleSide);
      if (!h || h.faceIndex === undefined || h.faceIndex === null) return null;
      const id = merged.elementOfTriangle(h.faceIndex);
      return id < 0 ? null : { id, t: h.distance };
    },
  };
}
