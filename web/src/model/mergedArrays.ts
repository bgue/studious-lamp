// The flat typed arrays of a merged geometry, as the import worker produces them and `MergedGeometry.fromArrays` wraps them.
// Pure data (no three.js), so it can cross postMessage as transferables.

export interface MergedArrays {
  elementCount: number;
  /** xyz per vertex in viewer space (Y up, origin shifted), elements laid out one after the other in id order. */
  position: Float32Array;
  normal: Float32Array;
  /** One float per vertex: the element id. */
  elementId: Float32Array;
  /** Triangle list, global vertex indices. */
  index: Uint32Array;
  /** [start, count] per element in indices (2 Uint32 per element). */
  ranges: Uint32Array;
  /** [start, count] per element in vertices (2 Uint32 per element). */
  vertexRanges: Uint32Array;
  /** [minx, miny, minz, maxx, maxy, maxz] per element; +-Infinity for an element without triangles. */
  bounds: Float32Array;
  /** Line segment end points (2 vertices per segment), empty when edges were skipped. */
  edgePosition: Float32Array;
  edgeElementId: Float32Array;
  /** [start, count] per element in edge vertices (2 Uint32 per element). */
  edgeRanges: Uint32Array;
  /** three-mesh-bvh serialisation of the indirect BVH over position/index, when the worker built it. */
  bvh?: SerializedBvh | null;
}

export interface SerializedBvh {
  roots: ArrayBuffer[];
  indirectBuffer: Uint32Array | Uint16Array;
}

/** Every ArrayBuffer inside `a`, for a postMessage transfer list. */
export function mergedTransferables(a: MergedArrays): ArrayBuffer[] {
  const out: ArrayBuffer[] = [
    a.position.buffer, a.normal.buffer, a.elementId.buffer, a.index.buffer, a.ranges.buffer, a.vertexRanges.buffer,
    a.bounds.buffer, a.edgePosition.buffer, a.edgeElementId.buffer, a.edgeRanges.buffer,
  ] as ArrayBuffer[];
  if (a.bvh) {
    for (const r of a.bvh.roots) out.push(r);
    out.push(a.bvh.indirectBuffer.buffer as ArrayBuffer);
  }
  return out;
}
