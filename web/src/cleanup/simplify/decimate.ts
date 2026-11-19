// Mesh decimation by quadric edge collapse (Garland-Heckbert), hand written and small.
//
// Choices that keep the look of a BIM element:
//  - A collapse moves one vertex onto a neighbour, so no new vertex positions appear and the bounding box can only shrink
//    inside the original.
//  - Silhouette and sharp edges are protected. A boundary edge (one face) or a sharp edge (dihedral angle above
//    `sharpAngle`) is a feature edge. A vertex with two feature edges (a point on a rim) may only slide along one of them,
//    a vertex with one or three or more (a corner) never moves. Extra constraint planes through feature edges make the error
//    grow when a rim is cut short.
//  - A collapse that would flip a surrounding triangle is refused, and so is one that would make the mesh non-manifold.
//
// The error of a collapse is sqrt of the summed squared distances of the moved vertex to the planes around it, in model
// units (an estimate of the geometric error, not a strict Hausdorff bound).

import type { MeshData } from './types';
import { cleanMesh, creaseNormals, DEFAULT_WELD_TOLERANCE } from './mesh';

export interface DecimateOptions {
  /** Keep this fraction of the triangles (0..1). Omit with maxError to decimate by error only. */
  ratio?: number;
  /** Stop when the next collapse would exceed this error (model units, metres). Omit to decimate by ratio only. */
  maxError?: number;
  /** Dihedral angle (degrees) above which an edge is a sharp edge. Default 30. */
  sharpAngle?: number;
  /** Elements with fewer triangles are returned unchanged. Default 0. */
  minTriangles?: number;
  /** A collapse is refused when it turns a neighbouring triangle by more than this cosine threshold. Default 0.2. */
  flipCos?: number;
}

export interface DecimateResult {
  mesh: MeshData;
  trianglesBefore: number;
  trianglesAfter: number;
  /** Largest collapse error that was accepted (model units). */
  maxErrorReached: number;
  /** False when the mesh was returned unchanged (below minTriangles, or nothing could be collapsed). */
  changed: boolean;
}

interface Cand {
  cost: number;
  v: number; // vertex that moves
  u: number; // vertex it moves onto
  ver: number;
}

class MinHeap {
  private a: Cand[] = [];
  get size(): number {
    return this.a.length;
  }
  push(c: Cand): void {
    const a = this.a;
    a.push(c);
    let i = a.length - 1;
    while (i > 0) {
      const p = (i - 1) >> 1;
      if (a[p]!.cost <= a[i]!.cost) break;
      [a[p], a[i]] = [a[i]!, a[p]!];
      i = p;
    }
  }
  pop(): Cand | undefined {
    const a = this.a;
    if (a.length === 0) return undefined;
    const top = a[0]!;
    const last = a.pop()!;
    if (a.length > 0) {
      a[0] = last;
      let i = 0;
      for (;;) {
        const l = 2 * i + 1, r = l + 1;
        let m = i;
        if (l < a.length && a[l]!.cost < a[m]!.cost) m = l;
        if (r < a.length && a[r]!.cost < a[m]!.cost) m = r;
        if (m === i) break;
        [a[m], a[i]] = [a[i]!, a[m]!];
        i = m;
      }
    }
    return top;
  }
}

export function decimateMesh(input: MeshData, o: DecimateOptions): DecimateResult {
  const nt0 = Math.floor(input.indices.length / 3);
  const unchanged: DecimateResult = { mesh: input, trianglesBefore: nt0, trianglesAfter: nt0, maxErrorReached: 0, changed: false };
  if (nt0 < Math.max(4, o.minTriangles ?? 0)) return unchanged;
  const ratio = o.ratio !== undefined ? Math.min(1, Math.max(0, o.ratio)) : undefined;
  const maxErr = o.maxError !== undefined && o.maxError >= 0 ? o.maxError : undefined;
  if (ratio === undefined && maxErr === undefined) return unchanged;
  const target = ratio !== undefined ? Math.max(4, Math.ceil(nt0 * ratio)) : 4;
  if (target >= nt0 && maxErr === undefined) return unchanged;
  const maxCost = maxErr !== undefined ? maxErr * maxErr : Infinity;

  // Topology works on a welded copy (so the faces of a split-vertex mesh are connected).
  const welded = cleanMesh(input, { weldTolerance: DEFAULT_WELD_TOLERANCE, dropDuplicateFaces: false }).mesh;
  const P = welded.positions;
  const nv = P.length / 3;
  const faces = Int32Array.from(welded.indices);
  const nt = faces.length / 3;
  if (nt < 4) return unchanged;
  const alive = new Uint8Array(nt).fill(1);
  let liveTris = nt;

  const vFaces: Set<number>[] = Array.from({ length: nv }, () => new Set<number>());
  for (let t = 0; t < nt; t++) for (let c = 0; c < 3; c++) vFaces[faces[t * 3 + c]!]!.add(t);

  const faceNormal = (t: number, out: number[]): number => {
    const a = faces[t * 3]!, b = faces[t * 3 + 1]!, c = faces[t * 3 + 2]!;
    const ux = P[b * 3]! - P[a * 3]!, uy = P[b * 3 + 1]! - P[a * 3 + 1]!, uz = P[b * 3 + 2]! - P[a * 3 + 2]!;
    const vx = P[c * 3]! - P[a * 3]!, vy = P[c * 3 + 1]! - P[a * 3 + 1]!, vz = P[c * 3 + 2]! - P[a * 3 + 2]!;
    const x = uy * vz - uz * vy, y = uz * vx - ux * vz, z = ux * vy - uy * vx;
    const l = Math.hypot(x, y, z);
    out[0] = x; out[1] = y; out[2] = z;
    return l;
  };

  // Quadrics: 10 numbers per vertex (symmetric 4x4), unweighted planes so the error is a squared distance.
  const Q = new Float64Array(nv * 10);
  const addPlane = (v: number, nx: number, ny: number, nz: number, d: number, w: number): void => {
    const o2 = v * 10;
    const t = [nx * nx, nx * ny, nx * nz, nx * d, ny * ny, ny * nz, ny * d, nz * nz, nz * d, d * d];
    for (let i = 0; i < 10; i++) Q[o2 + i] = Q[o2 + i]! + w * t[i]!;
  };
  const tmp = [0, 0, 0];
  const edgeFaces = new Map<number, number[]>();
  const ek = (a: number, b: number): number => (a < b ? a * nv + b : b * nv + a);
  for (let t = 0; t < nt; t++) {
    for (let c = 0; c < 3; c++) {
      const a = faces[t * 3 + c]!, b = faces[t * 3 + ((c + 1) % 3)]!;
      const k = ek(a, b);
      const l = edgeFaces.get(k);
      if (l) l.push(t);
      else edgeFaces.set(k, [t]);
    }
    const l = faceNormal(t, tmp);
    if (l < 1e-20) continue;
    const nx = tmp[0]! / l, ny = tmp[1]! / l, nz = tmp[2]! / l;
    for (let c = 0; c < 3; c++) {
      const v = faces[t * 3 + c]!;
      addPlane(v, nx, ny, nz, -(nx * P[v * 3]! + ny * P[v * 3 + 1]! + nz * P[v * 3 + 2]!), 1);
    }
  }

  // Feature edges and their constraint planes.
  const feat = new Set<number>();
  const cosSharp = Math.cos(((o.sharpAngle ?? 30) * Math.PI) / 180);
  const n1 = [0, 0, 0], n2 = [0, 0, 0];
  for (const [k, fl] of edgeFaces) {
    const a = Math.floor(k / nv), b = k - a * nv;
    let isFeat = false;
    let sideNormal: number[] | null = null;
    if (fl.length !== 2) {
      isFeat = true; // boundary or non-manifold
      const l = faceNormal(fl[0]!, n1);
      sideNormal = l > 0 ? [n1[0]! / l, n1[1]! / l, n1[2]! / l] : null;
    } else {
      const l1 = faceNormal(fl[0]!, n1), l2 = faceNormal(fl[1]!, n2);
      if (l1 > 0 && l2 > 0 && (n1[0]! * n2[0]! + n1[1]! * n2[1]! + n1[2]! * n2[2]!) / (l1 * l2) < cosSharp) {
        isFeat = true;
        sideNormal = [n1[0]! / l1, n1[1]! / l1, n1[2]! / l1];
      }
    }
    if (!isFeat) continue;
    feat.add(k);
    if (sideNormal) {
      // plane through the edge, perpendicular to the face: the vertex pays for leaving the edge line
      const ex = P[b * 3]! - P[a * 3]!, ey = P[b * 3 + 1]! - P[a * 3 + 1]!, ez = P[b * 3 + 2]! - P[a * 3 + 2]!;
      let px = ey * sideNormal[2]! - ez * sideNormal[1]!, py = ez * sideNormal[0]! - ex * sideNormal[2]!, pz = ex * sideNormal[1]! - ey * sideNormal[0]!;
      const pl = Math.hypot(px, py, pz);
      if (pl > 1e-20) {
        px /= pl; py /= pl; pz /= pl;
        const d = -(px * P[a * 3]! + py * P[a * 3 + 1]! + pz * P[a * 3 + 2]!);
        addPlane(a, px, py, pz, d, 1);
        addPlane(b, px, py, pz, d, 1);
      }
    }
  }

  const neighbours = (v: number): Set<number> => {
    const s = new Set<number>();
    for (const t of vFaces[v]!) {
      for (let c = 0; c < 3; c++) {
        const w = faces[t * 3 + c]!;
        if (w !== v) s.add(w);
      }
    }
    return s;
  };
  const featureNeighbours = (v: number, nb: Set<number>): number[] => {
    const out: number[] = [];
    for (const w of nb) if (feat.has(ek(v, w))) out.push(w);
    return out;
  };

  const errorAt = (qa: number, qb: number, x: number, y: number, z: number): number => {
    const a = qa * 10, b = qb * 10;
    const m = (i: number): number => Q[a + i]! + Q[b + i]!;
    const v = m(0) * x * x + 2 * m(1) * x * y + 2 * m(2) * x * z + 2 * m(3) * x + m(4) * y * y + 2 * m(5) * y * z + 2 * m(6) * y + m(7) * z * z + 2 * m(8) * z + m(9);
    return v > 0 ? v : 0;
  };

  const version = new Uint32Array(nv);
  const removed = new Uint8Array(nv);
  const heap = new MinHeap();

  /** Cost of moving v onto u, or Infinity when not allowed (feature rules). */
  const moveCost = (v: number, u: number, nbV: Set<number>): number => {
    const fv = featureNeighbours(v, nbV);
    if (fv.length > 0) {
      if (fv.length !== 2 || !fv.includes(u)) return Infinity; // corner, or leaving the feature line
    }
    return errorAt(v, u, P[u * 3]!, P[u * 3 + 1]!, P[u * 3 + 2]!);
  };
  const pushVertex = (v: number): void => {
    const nbV = neighbours(v);
    for (const u of nbV) {
      const cost = moveCost(v, u, nbV);
      if (cost < Infinity) heap.push({ cost, v, u, ver: version[v]! });
    }
  };
  for (let v = 0; v < nv; v++) if (vFaces[v]!.size > 0) pushVertex(v);

  const flipCos = o.flipCos ?? 0.2;
  const na = [0, 0, 0], nb2 = [0, 0, 0];
  const wouldFlip = (v: number, u: number): boolean => {
    for (const t of vFaces[v]!) {
      const a = faces[t * 3]!, b = faces[t * 3 + 1]!, c = faces[t * 3 + 2]!;
      if (a === u || b === u || c === u) continue; // dies in the collapse
      const l0 = faceNormal(t, na);
      const px = P[v * 3]!, py = P[v * 3 + 1]!, pz = P[v * 3 + 2]!;
      P[v * 3] = P[u * 3]!; P[v * 3 + 1] = P[u * 3 + 1]!; P[v * 3 + 2] = P[u * 3 + 2]!;
      const l1 = faceNormal(t, nb2);
      P[v * 3] = px; P[v * 3 + 1] = py; P[v * 3 + 2] = pz;
      if (l0 <= 0) continue;
      if (l1 <= l0 * 1e-6) return true;
      if ((na[0]! * nb2[0]! + na[1]! * nb2[1]! + na[2]! * nb2[2]!) / (l0 * l1) < flipCos) return true;
    }
    return false;
  };

  let maxReached = 0;
  let collapsed = 0;
  while (liveTris > target && heap.size > 0) {
    const c = heap.pop()!;
    const { v, u } = c;
    if (removed[v] || removed[u]) continue;
    if (c.ver !== version[v]) continue;
    if (c.cost > maxCost) break;
    const nbV = neighbours(v);
    if (!nbV.has(u)) continue;
    // link condition: the shared neighbours of v and u are exactly the apexes of the faces on edge (v,u)
    const nbU = neighbours(u);
    let common = 0;
    for (const w of nbV) if (nbU.has(w)) common++;
    let shared = 0;
    for (const t of vFaces[v]!) if (vFaces[u]!.has(t)) shared++;
    if (common !== shared || shared === 0) continue;
    if (wouldFlip(v, u)) continue;

    // collapse v onto u
    for (const t of [...vFaces[v]!]) {
      if (!alive[t]) continue;
      const has = faces[t * 3] === u || faces[t * 3 + 1] === u || faces[t * 3 + 2] === u;
      if (has) {
        alive[t] = 0;
        liveTris--;
        for (let k = 0; k < 3; k++) vFaces[faces[t * 3 + k]!]!.delete(t);
      } else {
        for (let k = 0; k < 3; k++) if (faces[t * 3 + k] === v) faces[t * 3 + k] = u;
        vFaces[v]!.delete(t);
        vFaces[u]!.add(t);
      }
    }
    // feature edges follow the vertex
    for (const w of nbV) {
      const kv = ek(v, w);
      if (feat.has(kv)) {
        feat.delete(kv);
        if (w !== u) feat.add(ek(u, w));
      }
    }
    for (let i = 0; i < 10; i++) Q[u * 10 + i] = Q[u * 10 + i]! + Q[v * 10 + i]!;
    removed[v] = 1;
    version[u] = version[u]! + 1;
    collapsed++;
    if (c.cost > maxReached) maxReached = c.cost;
    // refresh u and its ring
    pushVertex(u);
    for (const w of neighbours(u)) {
      version[w] = version[w]! + 1;
      pushVertex(w);
    }
  }

  if (collapsed === 0) return unchanged;
  const kept: number[] = [];
  for (let t = 0; t < nt; t++) {
    if (!alive[t]) continue;
    const a = faces[t * 3]!, b = faces[t * 3 + 1]!, cc = faces[t * 3 + 2]!;
    if (a === b || b === cc || a === cc) continue;
    kept.push(a, b, cc);
  }
  const mapV = new Int32Array(nv).fill(-1);
  let used = 0;
  for (const v of kept) if (mapV[v] === -1) mapV[v] = used++;
  const positions = new Float32Array(used * 3);
  for (let i = 0; i < nv; i++) {
    const n = mapV[i]!;
    if (n >= 0) {
      positions[n * 3] = P[i * 3]!;
      positions[n * 3 + 1] = P[i * 3 + 1]!;
      positions[n * 3 + 2] = P[i * 3 + 2]!;
    }
  }
  const indices = new Uint32Array(kept.length);
  for (let i = 0; i < kept.length; i++) indices[i] = mapV[kept[i]!]!;
  const mesh = creaseNormals({ positions, indices });
  return { mesh, trianglesBefore: nt0, trianglesAfter: indices.length / 3, maxErrorReached: Math.sqrt(maxReached), changed: indices.length / 3 < nt0 };
}
