// Geometric estimates for quantity summaries, used when an element has no quantity property.
//   volume: the signed tetrahedron sum of the element's triangles, for closed solids only (the closed flags of
//           closedMesh.ts); an open mesh has no volume.
//   area:   the mesh surface divided by 2, for thin closed plates (a slab, a wall: both faces are in the mesh); otherwise none.
//   length: the longest axis of the bounds (in aggregate.ts, no mesh needed).
// Pure: typed arrays in, numbers out. Results are cached per element.

import type { GeoEstimator } from './aggregate';

export interface MeshRange {
  start: number;
  count: number;
}

/** Volume (absolute) and surface area of a triangle soup; `index` ranges are in indices (3 per triangle). */
export function meshMeasure(position: ArrayLike<number>, index: ArrayLike<number>, range: MeshRange): { volume: number; area: number } {
  const n = Math.floor(range.count / 3);
  if (n <= 0) return { volume: 0, area: 0 };
  const first = index[range.start]! * 3;
  const ox = position[first]!;
  const oy = position[first + 1]!;
  const oz = position[first + 2]!;
  let vol = 0;
  let area = 0;
  for (let t = 0; t < n; t++) {
    const a = index[range.start + t * 3]! * 3;
    const b = index[range.start + t * 3 + 1]! * 3;
    const c = index[range.start + t * 3 + 2]! * 3;
    const ax = position[a]! - ox, ay = position[a + 1]! - oy, az = position[a + 2]! - oz;
    const bx = position[b]! - ox, by = position[b + 1]! - oy, bz = position[b + 2]! - oz;
    const cx = position[c]! - ox, cy = position[c + 1]! - oy, cz = position[c + 2]! - oz;
    const cxp = by * cz - bz * cy;
    const cyp = bz * cx - bx * cz;
    const czp = bx * cy - by * cx;
    vol += (ax * cxp + ay * cyp + az * czp) / 6;
    // Triangle area from the cross product of two edges.
    const ux = bx - ax, uy = by - ay, uz = bz - az;
    const vx = cx - ax, vy = cy - ay, vz = cz - az;
    const nx = uy * vz - uz * vy;
    const ny = uz * vx - ux * vz;
    const nz = ux * vy - uy * vx;
    area += 0.5 * Math.sqrt(nx * nx + ny * ny + nz * nz);
  }
  return { volume: Math.abs(vol), area };
}

/** A plate: its smallest bounds extent is at most this fraction of the middle one, and at most `THIN_MAX_M`. */
export const THIN_RATIO = 0.3;
export const THIN_MAX_M = 0.6;

export interface GeoSource {
  position: ArrayLike<number>;
  index: ArrayLike<number>;
  /** Index range per element id. */
  ranges: ReadonlyArray<MeshRange>;
  /** 1 per closed element, by element id (renderer.closedFlags). */
  closed: ArrayLike<number>;
  /** Bounds per element id: minx, miny, minz, maxx, maxy, maxz. */
  bounds(id: number): readonly number[];
}

export function makeGeoEstimator(src: GeoSource): GeoEstimator {
  const cache = new Map<number, { volume: number | string; area: number | string }>();
  const compute = (id: number): { volume: number | string; area: number | string } => {
    const r = src.ranges[id];
    if (!r || r.count < 3) return { volume: 'the element has no mesh', area: 'the element has no mesh' };
    if (!src.closed[id]) return { volume: 'the mesh is not a closed solid', area: 'the mesh is not a closed solid, so a thin plate cannot be told' };
    const m = meshMeasure(src.position, src.index, r);
    const b = src.bounds(id);
    const ext = [b[3]! - b[0]!, b[4]! - b[1]!, b[5]! - b[2]!].sort((x, y) => x - y);
    const volume = m.volume > 0 ? m.volume : 'the mesh has no volume';
    const thin = ext[0]! <= THIN_RATIO * ext[1]! && ext[0]! <= THIN_MAX_M;
    const area = thin && m.area > 0 ? m.area / 2 : 'the element is not a thin plate';
    return { volume, area };
  };
  const get = (id: number): { volume: number | string; area: number | string } => {
    let v = cache.get(id);
    if (!v) {
      v = compute(id);
      cache.set(id, v);
    }
    return v;
  };
  return { volume: (id) => get(id).volume, area: (id) => get(id).area };
}
