// Merged geometry: every element's triangles in one BufferGeometry, plus the
// tables needed to go from element id to buffer ranges and back.

import {
  Box3,
  BufferAttribute,
  BufferGeometry,
  EdgesGeometry,
  Matrix3,
  Matrix4,
  Vector3,
} from 'three';
import { MeshBVH } from 'three-mesh-bvh';
import type { ElementId } from '../types';

export interface IndexRange {
  start: number;
  count: number;
}

/** One source mesh (already a plain BufferGeometry) with its element-to-world matrix. */
export interface MeshPart {
  geometry: BufferGeometry;
  matrix: Matrix4;
}

export const EDGE_THRESHOLD_DEG = 30;

/**
 * Layout guarantees:
 *  - Vertices are laid out element by element in id order, so each element owns a contiguous
 *    vertex range (`vertexRanges`) and a contiguous index range (`ranges`, in indices, 3 per triangle).
 *  - `geometry` has `position`, `normal`, `elementId` (float, one per vertex) and a Uint32 index.
 *    All positions are in world (viewer) space; the Mesh using it has an identity matrix.
 *  - `edges` is a non-indexed line-segment geometry (2 vertices per segment) with `position` and
 *    `elementId`; `edgeRanges` are vertex ranges into it.
 *  - Elements without geometry have `count: 0` ranges and an empty Box3.
 */
export class MergedGeometry {
  readonly geometry: BufferGeometry;
  readonly ranges: IndexRange[];
  readonly vertexRanges: IndexRange[];
  readonly bounds: Box3[];
  readonly edges: BufferGeometry;
  readonly edgeRanges: IndexRange[];
  readonly elementCount: number;

  private readonly rangeStarts: Uint32Array;
  private readonly rangeIds: Uint32Array;
  private bvhCache: MeshBVH | null = null;
  private readonly subCache = new Map<ElementId, BufferGeometry>();

  constructor(parts: MeshPart[][]) {
    const n = parts.length;
    this.elementCount = n;

    // Pass 1: counts.
    let vTotal = 0;
    let iTotal = 0;
    const vCounts = new Uint32Array(n);
    const iCounts = new Uint32Array(n);
    for (let e = 0; e < n; e++) {
      for (const p of parts[e]!) {
        const pos = p.geometry.getAttribute('position');
        if (!pos) continue;
        const idx = p.geometry.getIndex();
        const triIdx = idx ? idx.count : pos.count;
        vCounts[e]! += pos.count;
        iCounts[e]! += triIdx - (triIdx % 3);
      }
      vTotal += vCounts[e]!;
      iTotal += iCounts[e]!;
    }

    const position = new Float32Array(vTotal * 3);
    const normal = new Float32Array(vTotal * 3);
    const elementId = new Float32Array(vTotal);
    const index = new Uint32Array(iTotal);

    this.ranges = [];
    this.vertexRanges = [];
    this.bounds = [];

    const v = new Vector3();
    const nrm = new Matrix3();
    let vOff = 0;
    let iOff = 0;

    // Pass 2: fill.
    for (let e = 0; e < n; e++) {
      const vStart = vOff;
      const iStart = iOff;
      const box = new Box3();
      for (const p of parts[e]!) {
        const g = p.geometry;
        const pos = g.getAttribute('position');
        if (!pos) continue;
        let nor = g.getAttribute('normal');
        if (!nor) {
          const tmp = g.clone();
          tmp.computeVertexNormals();
          nor = tmp.getAttribute('normal');
        }
        nrm.getNormalMatrix(p.matrix);
        const flip = p.matrix.determinant() < 0;

        for (let k = 0; k < pos.count; k++) {
          v.fromBufferAttribute(pos, k).applyMatrix4(p.matrix);
          const o = (vOff + k) * 3;
          position[o] = v.x;
          position[o + 1] = v.y;
          position[o + 2] = v.z;
          box.expandByPoint(v);
          v.fromBufferAttribute(nor as BufferAttribute, k).applyMatrix3(nrm).normalize();
          if (flip) v.negate();
          normal[o] = v.x;
          normal[o + 1] = v.y;
          normal[o + 2] = v.z;
          elementId[vOff + k] = e;
        }

        const idx = g.getIndex();
        const count = idx ? idx.count : pos.count;
        const tris = Math.floor(count / 3);
        for (let t = 0; t < tris; t++) {
          const a = idx ? idx.getX(t * 3) : t * 3;
          const b = idx ? idx.getX(t * 3 + 1) : t * 3 + 1;
          const c = idx ? idx.getX(t * 3 + 2) : t * 3 + 2;
          const o = iOff + t * 3;
          index[o] = vOff + a;
          index[o + 1] = vOff + (flip ? c : b);
          index[o + 2] = vOff + (flip ? b : c);
        }
        vOff += pos.count;
        iOff += tris * 3;
      }
      this.vertexRanges.push({ start: vStart, count: vOff - vStart });
      this.ranges.push({ start: iStart, count: iOff - iStart });
      this.bounds.push(box);
    }

    const geometry = new BufferGeometry();
    geometry.setAttribute('position', new BufferAttribute(position, 3));
    geometry.setAttribute('normal', new BufferAttribute(normal, 3));
    geometry.setAttribute('elementId', new BufferAttribute(elementId, 1));
    geometry.setIndex(new BufferAttribute(index, 1));
    geometry.computeBoundingBox();
    geometry.computeBoundingSphere();
    this.geometry = geometry;

    // Sorted table of non-empty ranges for binary search.
    const ids: number[] = [];
    for (let e = 0; e < n; e++) if (this.ranges[e]!.count > 0) ids.push(e);
    ids.sort((x, y) => this.ranges[x]!.start - this.ranges[y]!.start);
    this.rangeIds = Uint32Array.from(ids);
    this.rangeStarts = Uint32Array.from(ids.map((e) => this.ranges[e]!.start));

    // Edges.
    const edgeRanges: IndexRange[] = [];
    const chunks: Float32Array[] = [];
    let eTotal = 0;
    for (let e = 0; e < n; e++) {
      if (this.ranges[e]!.count === 0) {
        edgeRanges.push({ start: eTotal, count: 0 });
        continue;
      }
      const sub = this.makeSub(e);
      const eg = new EdgesGeometry(sub, EDGE_THRESHOLD_DEG);
      const arr = eg.getAttribute('position').array as Float32Array;
      chunks.push(arr);
      edgeRanges.push({ start: eTotal, count: arr.length / 3 });
      eTotal += arr.length / 3;
      eg.dispose();
      sub.dispose();
    }
    const ePos = new Float32Array(eTotal * 3);
    const eId = new Float32Array(eTotal);
    let off = 0;
    let ci = 0;
    for (let e = 0; e < n; e++) {
      if (this.ranges[e]!.count === 0) continue;
      const arr = chunks[ci++]!;
      ePos.set(arr, off * 3);
      eId.fill(e, off, off + arr.length / 3);
      off += arr.length / 3;
    }
    const edges = new BufferGeometry();
    edges.setAttribute('position', new BufferAttribute(ePos, 3));
    edges.setAttribute('elementId', new BufferAttribute(eId, 1));
    edges.computeBoundingBox();
    edges.computeBoundingSphere();
    this.edges = edges;
    this.edgeRanges = edgeRanges;
  }

  /** Element owning triangle `tri` (index into the merged index buffer / 3), or -1. */
  elementOfTriangle(tri: number): ElementId {
    const target = tri * 3;
    const starts = this.rangeStarts;
    let lo = 0;
    let hi = starts.length - 1;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      if (starts[mid]! <= target) lo = mid + 1;
      else hi = mid - 1;
    }
    if (hi < 0) return -1;
    const id = this.rangeIds[hi]!;
    const r = this.ranges[id]!;
    return target < r.start + r.count ? id : -1;
  }

  /**
   * BVH over the whole merged geometry. Built with `indirect: true` so the index buffer is NOT
   * reordered (the range table and the draw call keep working). `faceIndex` of hits is therefore
   * the true triangle index into the merged index buffer.
   */
  get bvh(): MeshBVH {
    if (!this.bvhCache) {
      this.bvhCache = new MeshBVH(this.geometry, { indirect: true });
    }
    return this.bvhCache;
  }

  hasGeometry(id: ElementId): boolean {
    return (this.ranges[id]?.count ?? 0) > 0;
  }

  private makeSub(id: ElementId): BufferGeometry {
    const vr = this.vertexRanges[id]!;
    const r = this.ranges[id]!;
    const srcPos = this.geometry.getAttribute('position').array as Float32Array;
    const srcNor = this.geometry.getAttribute('normal').array as Float32Array;
    const srcIdx = this.geometry.getIndex()!.array as Uint32Array;
    const g = new BufferGeometry();
    g.setAttribute('position', new BufferAttribute(srcPos.slice(vr.start * 3, (vr.start + vr.count) * 3), 3));
    g.setAttribute('normal', new BufferAttribute(srcNor.slice(vr.start * 3, (vr.start + vr.count) * 3), 3));
    const idx = new Uint32Array(r.count);
    for (let k = 0; k < r.count; k++) idx[k] = srcIdx[r.start + k]! - vr.start;
    g.setIndex(new BufferAttribute(idx, 1));
    return g;
  }

  /**
   * Compact, world-space sub-geometry of one element with its own BVH
   * (`geometry.boundsTree` is set, which three-mesh-bvh uses for geometry-vs-geometry queries).
   * Built lazily and cached. Returns null for elements without triangles. Note the BVH build
   * reorders this geometry's own (copied) index buffer; the merged buffers are untouched.
   */
  subGeometry(id: ElementId): BufferGeometry | null {
    if (!this.hasGeometry(id)) return null;
    let g = this.subCache.get(id);
    if (!g) {
      g = this.makeSub(id);
      const bvh = new MeshBVH(g);
      g.boundsTree = bvh;
      g.computeBoundingBox();
      this.subCache.set(id, g);
    }
    return g;
  }

  /** Union of all element bounds; empty Box3 for an empty model. */
  totalBounds(): Box3 {
    const b = new Box3();
    for (const e of this.bounds) if (!e.isEmpty()) b.union(e);
    return b;
  }

  dispose(): void {
    this.geometry.dispose();
    this.edges.dispose();
    for (const g of this.subCache.values()) g.dispose();
    this.subCache.clear();
    this.bvhCache = null;
  }
}
