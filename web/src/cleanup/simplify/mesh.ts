// Mesh clean-up: weld coincident vertices, drop degenerate triangles and duplicate faces, split into connected pieces,
// and recompute normals with a crease angle. All functions are pure and take and return typed arrays.

import type { MeshData } from './types';

export interface CleanOptions {
  /** Vertices closer than this (metres, per axis grid) are merged. 0 merges only bit-identical positions. */
  weldTolerance?: number;
  /** Triangles with area below this (m²) count as zero-area. */
  minArea?: number;
  dropDegenerate?: boolean;
  dropDuplicateFaces?: boolean;
}

export interface CleanStats {
  verticesBefore: number;
  verticesAfter: number;
  trianglesBefore: number;
  trianglesAfter: number;
  welded: number;
  degenerate: number;
  duplicateFaces: number;
}

export const DEFAULT_WELD_TOLERANCE = 1e-4;
export const DEFAULT_MIN_AREA = 1e-10;

/**
 * Weld, then drop triangles that have a repeated vertex or no area, then drop faces that repeat another face (same three
 * vertices in any order; the first one stays, so a closed mesh stays closed). Unused vertices are removed.
 * Normals are not carried over; call `creaseNormals` on the result.
 */
export function cleanMesh(mesh: MeshData, o: CleanOptions = {}): { mesh: MeshData; stats: CleanStats } {
  const tol = o.weldTolerance ?? DEFAULT_WELD_TOLERANCE;
  const minArea = o.minArea ?? DEFAULT_MIN_AREA;
  const pos = mesh.positions;
  const nv = Math.floor(pos.length / 3);
  const nt = Math.floor(mesh.indices.length / 3);

  // Weld by grid cell (first vertex of a cell is the representative, so original coordinates survive).
  const remap = new Uint32Array(nv);
  const cells = new Map<string, number>();
  let welded = 0;
  const inv = tol > 0 ? 1 / tol : 0;
  for (let i = 0; i < nv; i++) {
    const x = pos[i * 3]!, y = pos[i * 3 + 1]!, z = pos[i * 3 + 2]!;
    const key = tol > 0 ? `${Math.round(x * inv)},${Math.round(y * inv)},${Math.round(z * inv)}` : `${x},${y},${z}`;
    const hit = cells.get(key);
    if (hit === undefined) {
      cells.set(key, i);
      remap[i] = i;
    } else {
      remap[i] = hit;
      welded++;
    }
  }

  const keep: number[] = [];
  const seen = new Set<string>();
  let degenerate = 0;
  let dup = 0;
  for (let t = 0; t < nt; t++) {
    const a = remap[mesh.indices[t * 3]!]!, b = remap[mesh.indices[t * 3 + 1]!]!, c = remap[mesh.indices[t * 3 + 2]!]!;
    if (o.dropDegenerate !== false) {
      if (a === b || b === c || a === c || triArea(pos, a, b, c) < minArea) {
        degenerate++;
        continue;
      }
    }
    if (o.dropDuplicateFaces !== false) {
      const s = [a, b, c].sort((p, q) => p - q);
      const key = `${s[0]},${s[1]},${s[2]}`;
      if (seen.has(key)) {
        dup++;
        continue;
      }
      seen.add(key);
    }
    keep.push(a, b, c);
  }

  // Compact the vertex list to the used ones.
  const newIndex = new Int32Array(nv).fill(-1);
  let used = 0;
  for (const v of keep) if (newIndex[v] === -1) newIndex[v] = used++;
  const positions = new Float32Array(used * 3);
  for (let i = 0; i < nv; i++) {
    const n = newIndex[i]!;
    if (n < 0) continue;
    positions[n * 3] = pos[i * 3]!;
    positions[n * 3 + 1] = pos[i * 3 + 1]!;
    positions[n * 3 + 2] = pos[i * 3 + 2]!;
  }
  const indices = new Uint32Array(keep.length);
  for (let k = 0; k < keep.length; k++) indices[k] = newIndex[keep[k]!]!;
  return {
    mesh: { positions, indices },
    stats: { verticesBefore: nv, verticesAfter: used, trianglesBefore: nt, trianglesAfter: keep.length / 3, welded, degenerate, duplicateFaces: dup },
  };
}

export function triArea(pos: ArrayLike<number>, a: number, b: number, c: number): number {
  const ax = pos[a * 3]!, ay = pos[a * 3 + 1]!, az = pos[a * 3 + 2]!;
  const ux = pos[b * 3]! - ax, uy = pos[b * 3 + 1]! - ay, uz = pos[b * 3 + 2]! - az;
  const vx = pos[c * 3]! - ax, vy = pos[c * 3 + 1]! - ay, vz = pos[c * 3 + 2]! - az;
  const x = uy * vz - uz * vy, y = uz * vx - ux * vz, z = ux * vy - uy * vx;
  return 0.5 * Math.sqrt(x * x + y * y + z * z);
}

export function meshBounds(positions: ArrayLike<number>): [number, number, number, number, number, number] {
  const b: [number, number, number, number, number, number] = [Infinity, Infinity, Infinity, -Infinity, -Infinity, -Infinity];
  for (let i = 0; i + 2 < positions.length; i += 3) {
    for (let a = 0; a < 3; a++) {
      const v = positions[i + a]!;
      if (v < b[a]!) b[a] = v;
      if (v > b[3 + a]!) b[3 + a] = v;
    }
  }
  return b;
}

/** Vertex count that a mesh uses (indices reference it). */
export function usedVertexCount(mesh: MeshData): number {
  const seen = new Uint8Array(Math.floor(mesh.positions.length / 3));
  let n = 0;
  for (const i of mesh.indices) if (!seen[i]) { seen[i] = 1; n++; }
  return n;
}

// ---------------------------------------------------------------- connected pieces

/** Triangle index lists of the connected pieces (triangles that share a vertex), largest first. Vertices are shared by index. */
export function connectedPieces(mesh: MeshData): number[][] {
  const nv = Math.floor(mesh.positions.length / 3);
  const nt = Math.floor(mesh.indices.length / 3);
  const parent = new Int32Array(nv);
  for (let i = 0; i < nv; i++) parent[i] = i;
  const find = (x: number): number => {
    while (parent[x] !== x) {
      parent[x] = parent[parent[x]!]!;
      x = parent[x]!;
    }
    return x;
  };
  for (let t = 0; t < nt; t++) {
    const a = find(mesh.indices[t * 3]!), b = find(mesh.indices[t * 3 + 1]!), c = find(mesh.indices[t * 3 + 2]!);
    if (a !== b) parent[b] = a;
    const ra = find(a);
    const rc = find(c);
    if (ra !== rc) parent[rc] = ra;
  }
  const groups = new Map<number, number[]>();
  for (let t = 0; t < nt; t++) {
    const r = find(mesh.indices[t * 3]!);
    let g = groups.get(r);
    if (!g) groups.set(r, (g = []));
    g.push(t);
  }
  return [...groups.values()].sort((x, y) => y.length - x.length);
}

/** A new mesh with only the given triangles (unused vertices dropped, normals carried over when present). */
export function subMesh(mesh: MeshData, triangles: readonly number[]): MeshData {
  const map = new Map<number, number>();
  const pos: number[] = [];
  const nor: number[] = [];
  const idx = new Uint32Array(triangles.length * 3);
  let k = 0;
  for (const t of triangles) {
    for (let c = 0; c < 3; c++) {
      const v = mesh.indices[t * 3 + c]!;
      let n = map.get(v);
      if (n === undefined) {
        n = map.size;
        map.set(v, n);
        pos.push(mesh.positions[v * 3]!, mesh.positions[v * 3 + 1]!, mesh.positions[v * 3 + 2]!);
        if (mesh.normals) nor.push(mesh.normals[v * 3]!, mesh.normals[v * 3 + 1]!, mesh.normals[v * 3 + 2]!);
      }
      idx[k++] = n;
    }
  }
  const out: MeshData = { positions: Float32Array.from(pos), indices: idx };
  if (mesh.normals) out.normals = Float32Array.from(nor);
  return out;
}

/**
 * Remove the connected pieces whose largest bounds dimension is below `maxSize` (m), keeping the largest piece whatever
 * its size. Returns null when nothing is removed.
 */
export function dropSmallPieces(mesh: MeshData, maxSize: number): { mesh: MeshData; removedPieces: number; removedTriangles: number } | null {
  const pieces = connectedPieces(mesh);
  if (pieces.length < 2) return null;
  const keepTris: number[] = [];
  let removedPieces = 0;
  let removedTriangles = 0;
  pieces.forEach((tris, i) => {
    let small = false;
    if (i > 0) {
      const lo = [Infinity, Infinity, Infinity];
      const hi = [-Infinity, -Infinity, -Infinity];
      for (const t of tris) {
        for (let c = 0; c < 3; c++) {
          const v = mesh.indices[t * 3 + c]!;
          for (let a = 0; a < 3; a++) {
            const x = mesh.positions[v * 3 + a]!;
            if (x < lo[a]!) lo[a] = x;
            if (x > hi[a]!) hi[a] = x;
          }
        }
      }
      small = Math.max(hi[0]! - lo[0]!, hi[1]! - lo[1]!, hi[2]! - lo[2]!) < maxSize;
    }
    if (small) {
      removedPieces++;
      removedTriangles += tris.length;
    } else keepTris.push(...tris);
  });
  if (removedPieces === 0) return null;
  keepTris.sort((a, b) => a - b);
  return { mesh: subMesh(mesh, keepTris), removedPieces, removedTriangles };
}

// ---------------------------------------------------------------- normals

/**
 * Per-vertex normals with a crease angle: faces whose normals differ by more than `creaseDeg` from a vertex's smooth group
 * do not share a normal there, so hard edges stay hard and curved surfaces stay smooth. Vertices are duplicated where a
 * crease runs through them. Returns a new mesh with normals.
 */
export function creaseNormals(mesh: MeshData, creaseDeg = 35): MeshData {
  const nv = Math.floor(mesh.positions.length / 3);
  const nt = Math.floor(mesh.indices.length / 3);
  const fn = new Float32Array(nt * 3);
  for (let t = 0; t < nt; t++) {
    const a = mesh.indices[t * 3]!, b = mesh.indices[t * 3 + 1]!, c = mesh.indices[t * 3 + 2]!;
    const ux = mesh.positions[b * 3]! - mesh.positions[a * 3]!, uy = mesh.positions[b * 3 + 1]! - mesh.positions[a * 3 + 1]!, uz = mesh.positions[b * 3 + 2]! - mesh.positions[a * 3 + 2]!;
    const vx = mesh.positions[c * 3]! - mesh.positions[a * 3]!, vy = mesh.positions[c * 3 + 1]! - mesh.positions[a * 3 + 1]!, vz = mesh.positions[c * 3 + 2]! - mesh.positions[a * 3 + 2]!;
    // area-weighted normal (the cross product is not normalised)
    fn[t * 3] = uy * vz - uz * vy;
    fn[t * 3 + 1] = uz * vx - ux * vz;
    fn[t * 3 + 2] = ux * vy - uy * vx;
  }
  const unit = (t: number): [number, number, number] => {
    const x = fn[t * 3]!, y = fn[t * 3 + 1]!, z = fn[t * 3 + 2]!;
    const l = Math.hypot(x, y, z) || 1;
    return [x / l, y / l, z / l];
  };
  const cosCrease = Math.cos((creaseDeg * Math.PI) / 180);
  // faces per vertex
  const counts = new Uint32Array(nv + 1);
  for (let k = 0; k < mesh.indices.length; k++) counts[mesh.indices[k]! + 1]!++;
  for (let i = 0; i < nv; i++) counts[i + 1]! += counts[i]!;
  const fill = counts.slice(0, nv);
  const vf = new Uint32Array(mesh.indices.length);
  for (let t = 0; t < nt; t++) for (let c = 0; c < 3; c++) vf[fill[mesh.indices[t * 3 + c]!]!++] = t;

  const outPos: number[] = [];
  const outNor: number[] = [];
  const outIdx = new Uint32Array(mesh.indices.length);
  for (let v = 0; v < nv; v++) {
    const faces = Array.from(vf.subarray(counts[v]!, counts[v + 1]!));
    // greedy smooth groups: a face joins the first group whose seed normal is within the crease angle
    const groups: { seed: [number, number, number]; sum: [number, number, number]; faces: number[] }[] = [];
    for (const t of faces) {
      const n = unit(t);
      let g = groups.find((q) => q.seed[0] * n[0] + q.seed[1] * n[1] + q.seed[2] * n[2] >= cosCrease);
      if (!g) groups.push((g = { seed: n, sum: [0, 0, 0], faces: [] }));
      g.faces.push(t);
      g.sum[0] += fn[t * 3]!;
      g.sum[1] += fn[t * 3 + 1]!;
      g.sum[2] += fn[t * 3 + 2]!;
    }
    for (const g of groups) {
      const l = Math.hypot(g.sum[0], g.sum[1], g.sum[2]) || 1;
      const n = outPos.length / 3;
      outPos.push(mesh.positions[v * 3]!, mesh.positions[v * 3 + 1]!, mesh.positions[v * 3 + 2]!);
      outNor.push(g.sum[0] / l, g.sum[1] / l, g.sum[2] / l);
      for (const t of g.faces) {
        for (let c = 0; c < 3; c++) if (mesh.indices[t * 3 + c] === v) outIdx[t * 3 + c] = n;
      }
    }
  }
  return { positions: Float32Array.from(outPos), normals: Float32Array.from(outNor), indices: outIdx };
}
