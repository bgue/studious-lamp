// BVH over the merged geometry, built where the main thread is not (the import worker) and serialised for transfer.
// Same options as MergedGeometry's lazy getter (`indirect: true`: the index buffer is not reordered, so ranges and the draw
// call keep working and `faceIndex` of a hit is the triangle index into the merged index buffer).
import { BufferAttribute, BufferGeometry } from 'three';
import { MeshBVH } from 'three-mesh-bvh';
import type { MergedArrays, SerializedBvh } from './mergedArrays';

/**
 * Builds the indirect BVH of `position` + `index` and returns its buffers without copying them. `index` is not part of the
 * result (indirect BVHs leave it untouched; the main thread already owns it). `onProgress` receives 0..1.
 */
export function buildBvh(a: Pick<MergedArrays, 'position' | 'index'>, onProgress?: (fraction: number) => void): SerializedBvh {
  const g = new BufferGeometry();
  g.setAttribute('position', new BufferAttribute(a.position, 3));
  g.setIndex(new BufferAttribute(a.index, 1));
  const bvh = new MeshBVH(g, { indirect: true, ...(onProgress ? { onProgress } : {}) });
  const s = MeshBVH.serialize(bvh, { cloneBuffers: false });
  return { roots: s.roots, indirectBuffer: s.indirectBuffer as Uint32Array };
}
