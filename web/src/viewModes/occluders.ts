// Which elements the 'occluders only' scope of the view modes applies to. Pure.

import type { Classification, ElementId } from '../types';

export const SCOPE_OCCLUDERS_ONLY = 'occluders only';

/**
 * 1 for every element that is an occluder: Host and Near, plus a Far element that blocks the focus (occlusion > 0
 * in the last sightline result). Everything else, the focus included, is 0.
 */
export function occluderMask(n: number, c: Classification, occlusion: ReadonlyMap<ElementId, number>): Uint8Array {
  const m = new Uint8Array(n);
  for (const id of c.host) if (id >= 0 && id < n) m[id] = 1;
  for (const id of c.near) if (id >= 0 && id < n) m[id] = 1;
  for (const id of c.far) if (id >= 0 && id < n && (occlusion.get(id) ?? 0) > 0) m[id] = 1;
  return m;
}
