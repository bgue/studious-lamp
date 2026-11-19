// Duplicate geometry: the same mesh placed several times. For a glb, repeats become instances (one shared mesh, one
// transform per element). The detector works on world-space meshes (the viewer's merged geometry has no instance
// information), so it finds a rigid transform that maps one element's vertices onto another's.
//
//   geometryHash(mesh)         a string that is equal for two meshes that differ only by a rigid motion (same vertex order)
//   findRigidMatch(ref, other) a 4x4 column-major matrix M with M * ref = other (within tolerance), or null
//   groupInstances(items)      groups of elements that repeat one master mesh, with the matrix of each member
//
// Conservative on purpose: vertex order and triangle indices must be identical, mirrored copies are not instanced, and
// every vertex is verified against the transform.

import type { MeshData } from './types';

export const INSTANCE_TOLERANCE = 0.002;

function fnv(h: number, v: number): number {
  h ^= v & 0xff;
  h = Math.imul(h, 16777619);
  h ^= (v >>> 8) & 0xff;
  h = Math.imul(h, 16777619);
  h ^= (v >>> 16) & 0xff;
  h = Math.imul(h, 16777619);
  h ^= (v >>> 24) & 0xff;
  return Math.imul(h, 16777619) >>> 0;
}

function centroid(p: ArrayLike<number>): [number, number, number] {
  const n = Math.floor(p.length / 3);
  let x = 0, y = 0, z = 0;
  for (let i = 0; i < n; i++) {
    x += p[i * 3]!;
    y += p[i * 3 + 1]!;
    z += p[i * 3 + 2]!;
  }
  return n > 0 ? [x / n, y / n, z / n] : [0, 0, 0];
}

/**
 * Hash that does not change when the mesh is moved or rotated: counts, a hash of the index list, and three distances that
 * rigid motion keeps (radius of gyration, distance of the first and the last vertex from the centroid, each to 1 mm).
 */
export function geometryHash(mesh: MeshData): string {
  const p = mesh.positions;
  const nv = Math.floor(p.length / 3);
  const c = centroid(p);
  let h = 2166136261;
  for (let i = 0; i < mesh.indices.length; i++) h = fnv(h, mesh.indices[i]!);
  let rg = 0;
  for (let i = 0; i < nv; i++) rg += (p[i * 3]! - c[0]) ** 2 + (p[i * 3 + 1]! - c[1]) ** 2 + (p[i * 3 + 2]! - c[2]) ** 2;
  rg = Math.sqrt(rg / Math.max(1, nv));
  const dist = (i: number): number => Math.hypot(p[i * 3]! - c[0], p[i * 3 + 1]! - c[1], p[i * 3 + 2]! - c[2]);
  const q = (x: number): number => Math.round(x * 1000);
  return `${nv}:${mesh.indices.length / 3}:${h.toString(16)}:${q(rg)}:${q(dist(0))}:${q(dist(nv - 1))}`;
}

type V3 = [number, number, number];
const sub = (a: V3, b: V3): V3 => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const dot = (a: V3, b: V3): number => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const cross = (a: V3, b: V3): V3 => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const len = (a: V3): number => Math.hypot(a[0], a[1], a[2]);
const scale = (a: V3, s: number): V3 => [a[0] * s, a[1] * s, a[2] * s];

/** Frame (three orthonormal axes) from the vertices at the given indices relative to the centroid, or null when degenerate. */
function frame(p: ArrayLike<number>, c: V3, i0: number, i1: number): V3[] | null {
  const at = (i: number): V3 => [p[i * 3]! - c[0], p[i * 3 + 1]! - c[1], p[i * 3 + 2]! - c[2]];
  const a = at(i0);
  const la = len(a);
  if (la < 1e-9) return null;
  const e1 = scale(a, 1 / la);
  const b = at(i1);
  const bp = sub(b, scale(e1, dot(b, e1)));
  const lb = len(bp);
  if (lb < 1e-9) return null;
  const e2 = scale(bp, 1 / lb);
  return [e1, e2, cross(e1, e2)];
}

/** Row-major 3x3 times column: R = Fb * Fa^T where F has the axes as columns. */
function rotationBetween(fa: V3[], fb: V3[]): number[] {
  const R: number[] = new Array(9).fill(0);
  for (let r = 0; r < 3; r++) for (let c = 0; c < 3; c++) {
    let s = 0;
    for (let k = 0; k < 3; k++) s += fb[k]![r]! * fa[k]![c]!;
    R[r * 3 + c] = s;
  }
  return R;
}

/**
 * Rigid transform M (4x4, column-major, rotation and translation only) with M * ref = other for every vertex, or null.
 * Meshes need the same vertex count and the same index list.
 */
export function findRigidMatch(ref: MeshData, other: MeshData, tol = INSTANCE_TOLERANCE): number[] | null {
  const pa = ref.positions, pb = other.positions;
  const nv = Math.floor(pa.length / 3);
  if (nv === 0 || pb.length !== pa.length || ref.indices.length !== other.indices.length) return null;
  for (let i = 0; i < ref.indices.length; i++) if (ref.indices[i] !== other.indices[i]) return null;
  const ca = centroid(pa), cb = centroid(pb);
  // reference vertices: the one farthest from the centroid, then the one farthest from that axis
  let i0 = 0, best = -1;
  for (let i = 0; i < nv; i++) {
    const d = (pa[i * 3]! - ca[0]) ** 2 + (pa[i * 3 + 1]! - ca[1]) ** 2 + (pa[i * 3 + 2]! - ca[2]) ** 2;
    if (d > best) { best = d; i0 = i; }
  }
  const a0: V3 = [pa[i0 * 3]! - ca[0], pa[i0 * 3 + 1]! - ca[1], pa[i0 * 3 + 2]! - ca[2]];
  const l0 = len(a0);
  if (l0 < 1e-9) return identityIfSame(pa, pb, ca, cb, tol);
  const e1 = scale(a0, 1 / l0);
  let i1 = -1;
  best = -1;
  for (let i = 0; i < nv; i++) {
    const v: V3 = [pa[i * 3]! - ca[0], pa[i * 3 + 1]! - ca[1], pa[i * 3 + 2]! - ca[2]];
    const perp = sub(v, scale(e1, dot(v, e1)));
    const d = dot(perp, perp);
    if (d > best) { best = d; i1 = i; }
  }
  const fa = frame(pa, ca, i0, i1);
  const fb = frame(pb, cb, i0, i1);
  if (!fa || !fb) return null;
  // a mirrored copy has frames of opposite handedness only through the third axis; the verification below rejects it
  const R = rotationBetween(fa, fb);
  const t: V3 = [
    cb[0] - (R[0]! * ca[0] + R[1]! * ca[1] + R[2]! * ca[2]),
    cb[1] - (R[3]! * ca[0] + R[4]! * ca[1] + R[5]! * ca[2]),
    cb[2] - (R[6]! * ca[0] + R[7]! * ca[1] + R[8]! * ca[2]),
  ];
  const tol2 = tol * tol;
  for (let i = 0; i < nv; i++) {
    const x = pa[i * 3]!, y = pa[i * 3 + 1]!, z = pa[i * 3 + 2]!;
    const ex = R[0]! * x + R[1]! * y + R[2]! * z + t[0] - pb[i * 3]!;
    const ey = R[3]! * x + R[4]! * y + R[5]! * z + t[1] - pb[i * 3 + 1]!;
    const ez = R[6]! * x + R[7]! * y + R[8]! * z + t[2] - pb[i * 3 + 2]!;
    if (ex * ex + ey * ey + ez * ez > tol2) return null;
  }
  return [R[0]!, R[3]!, R[6]!, 0, R[1]!, R[4]!, R[7]!, 0, R[2]!, R[5]!, R[8]!, 0, t[0], t[1], t[2], 1];
}

function identityIfSame(pa: ArrayLike<number>, pb: ArrayLike<number>, ca: V3, cb: V3, tol: number): number[] | null {
  // all vertices at the centroid: a point cloud; only translation can be told
  const t = sub(cb, ca);
  for (let i = 0; i < pa.length / 3; i++) {
    if (Math.hypot(pa[i * 3]! + t[0] - pb[i * 3]!, pa[i * 3 + 1]! + t[1] - pb[i * 3 + 1]!, pa[i * 3 + 2]! + t[2] - pb[i * 3 + 2]!) > tol) return null;
  }
  return [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, t[0], t[1], t[2], 1];
}

export interface InstanceItem {
  id: number;
  mesh: MeshData;
  /** Only elements with the same key can share a mesh (e.g. the colour). Default: all alike. */
  key?: string;
}

export interface InstanceMember {
  id: number;
  /** Column-major 4x4 that takes the master's vertices to this member's. */
  matrix: number[];
}

export interface InstanceGroup {
  master: number;
  /** Includes the master (identity matrix) first. */
  members: InstanceMember[];
  hash: string;
}

export const IDENTITY = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];

/** Group elements that repeat one mesh. Groups have at least two members; the lowest id of a group is its master. */
export function groupInstances(items: readonly InstanceItem[], tol = INSTANCE_TOLERANCE): InstanceGroup[] {
  const buckets = new Map<string, InstanceItem[]>();
  const sorted = [...items].sort((a, b) => a.id - b.id);
  for (const it of sorted) {
    if (it.mesh.indices.length < 3) continue;
    const key = `${it.key ?? ''}|${geometryHash(it.mesh)}`;
    let b = buckets.get(key);
    if (!b) buckets.set(key, (b = []));
    b.push(it);
  }
  const groups: InstanceGroup[] = [];
  for (const [key, list] of buckets) {
    if (list.length < 2) continue;
    // several masters can live in one bucket (same hash, different shape); match each item to the first master it fits
    const masters: InstanceGroup[] = [];
    const masterItems: InstanceItem[] = [];
    for (const it of list) {
      let placed = false;
      for (let m = 0; m < masters.length && !placed; m++) {
        const mat = findRigidMatch(masterItems[m]!.mesh, it.mesh, tol);
        if (mat) {
          masters[m]!.members.push({ id: it.id, matrix: mat });
          placed = true;
        }
      }
      if (!placed) {
        masters.push({ master: it.id, members: [{ id: it.id, matrix: IDENTITY.slice() }], hash: key });
        masterItems.push(it);
      }
    }
    for (const g of masters) if (g.members.length >= 2) groups.push(g);
  }
  return groups.sort((a, b) => a.master - b.master);
}

// ---------------------------------------------------------------- rigid matrix helpers (column-major 4x4)

/** Inverse of a rotation + translation matrix. */
export function invertRigid(m: readonly number[]): number[] {
  const tx = m[12]!, ty = m[13]!, tz = m[14]!;
  return [
    m[0]!, m[4]!, m[8]!, 0,
    m[1]!, m[5]!, m[9]!, 0,
    m[2]!, m[6]!, m[10]!, 0,
    -(m[0]! * tx + m[1]! * ty + m[2]! * tz), -(m[4]! * tx + m[5]! * ty + m[6]! * tz), -(m[8]! * tx + m[9]! * ty + m[10]! * tz), 1,
  ];
}

/** a * b (apply b first). */
export function multiplyMatrices(a: readonly number[], b: readonly number[]): number[] {
  const o = new Array<number>(16).fill(0);
  for (let c = 0; c < 4; c++) for (let r = 0; r < 4; r++) {
    let s = 0;
    for (let k = 0; k < 4; k++) s += a[k * 4 + r]! * b[c * 4 + k]!;
    o[c * 4 + r] = s;
  }
  return o;
}

/** The group without the members that `drop` names; the lowest remaining id becomes the master and the matrices are rebased. Null when fewer than two remain. */
export function pruneGroup(g: InstanceGroup, drop: (id: number) => boolean): InstanceGroup | null {
  const rest = g.members.filter((m) => !drop(m.id));
  if (rest.length < 2) return null;
  if (!drop(g.master)) return { ...g, members: rest };
  const first = rest[0]!;
  const inv = invertRigid(first.matrix);
  return { master: first.id, hash: g.hash, members: rest.map((m) => ({ id: m.id, matrix: m.id === first.id ? IDENTITY.slice() : multiplyMatrices(m.matrix, inv) })) };
}
