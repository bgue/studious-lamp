// CleanupGeometry over the merged geometry and the BVH provider.

import type { MergedGeometry } from '../model/merged';
import type { BvhGeometryProvider } from '../render/geometry';
import { meshVolumeOf } from './analysis';
import type { CleanupGeometry } from './analysis';

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
