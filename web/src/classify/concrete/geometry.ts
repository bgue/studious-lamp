// XR_ConcreteGeometry, measured: volume, local frame, dimensions, section shape, planar faces and formwork of one concrete element.
// Pure functions over world-space triangles (no DOM, no three.js). Design: docs/design/concrete-classification.md section 3.5.
//
// Input mesh: the viewer frame (y up), like `measureOrientation`. All output vectors and boxes are in IFC axes (X east, Y north, Z up):
// (X, Y, Z) = (x, -z, y). Lengths in metres, areas in m2, volumes in m3.

import { eigenSym3, surfaceMoments } from '../facets/orientation';
import type { OrientationMesh } from '../facets/orientation';

export type V3 = [number, number, number];
/** minX, minY, minZ, maxX, maxY, maxZ in IFC axes. */
export type Box6 = [number, number, number, number, number, number];
export type FrameKind = 'slab' | 'wall' | 'beam' | 'column' | 'footing' | 'other';
export type SectionShape = 'RECT' | 'CIRC' | 'T' | 'L' | 'I' | 'IRREGULAR';

export interface Frame { origin: V3; x: V3; y: V3; z: V3 }

/** Another element a face may lie against. `bounds` in IFC axes. */
export interface Neighbour { id: string; bounds: Box6 }

export interface GeometryOptions {
  /** Concrete neighbours (bounds): faces against them are construction joints and are not formed. */
  others?: readonly Neighbour[];
  /** Ground: faces below `level` (soffit and/or sides, per role) lie against the ground. `level` is the IFC Z of the ground in the viewer's frame. */
  ground?: { level: number; soffit: boolean; sides: boolean };
  /** Walls: the plan direction pointing out of the wall's exterior face (x, y). Decides the sign of local Y. */
  outward?: readonly [number, number] | null;
  /** Slabs: plan directions (unit, x y) of the linear elements that carry it. All parallel: the span runs across them. */
  supportDirs?: ReadonlyArray<readonly [number, number]>;
}

export interface FaceInfo {
  /** TOP, BOTTOM, SIDE_X+, SIDE_X-, SIDE_Y+, SIDE_Y-, END_+, END_-, INCL (a second face of the same name gets #2, #3). */
  name: string;
  area: number;
  /** Local-frame unit normal. */
  normal: V3;
  /** Area against other concrete elements / against the ground. */
  againstConcrete: number;
  againstGround: number;
  /** Ids of the neighbours that touch it. */
  touches: string[];
}

export interface ConcreteGeometry {
  kind: FrameKind;
  volume: number;
  /** The mesh is not a closed surface: `volume` is the bounds volume (in the local frame), flagged. */
  volumeEstimated: boolean;
  /** Total surface area. */
  area: number;
  bounds: Box6;
  frame: Frame;
  /** Extents along the local X, Y, Z. */
  size: V3;
  /** Role dependent, see `dimensions`. */
  length: number;
  width: number;
  thickness: number;
  sectionShape: SectionShape;
  faces: FaceInfo[];
  formworkArea: number;
  topArea: number;
  soffitArea: number;
  groundArea: number;
  /** Plan long side over short side of the footprint rectangle (1 for a square or a round shape). */
  planAspect: number;
  /** The axis of the principal direction (unit, IFC), Z >= 0. */
  axis: V3;
  /** Second spread over the first (small: a linear element). */
  linearity: number;
  triangles: number;
}

const r3 = (n: number): number => Math.round(n * 1000) / 1000;
const dot = (a: readonly number[], b: readonly number[]): number => a[0]! * b[0]! + a[1]! * b[1]! + a[2]! * b[2]!;
const cross = (a: readonly number[], b: readonly number[]): V3 => [a[1]! * b[2]! - a[2]! * b[1]!, a[2]! * b[0]! - a[0]! * b[2]!, a[0]! * b[1]! - a[1]! * b[0]!];
const norm = (a: readonly number[]): V3 => { const n = Math.hypot(a[0]!, a[1]!, a[2]!) || 1; return [a[0]! / n, a[1]! / n, a[2]! / n]; };
const UP: V3 = [0, 0, 1];

/** Triangles in IFC axes, 9 numbers each. */
export function ifcTriangles(mesh: OrientationMesh): Float64Array {
  const pos = mesh.position;
  const idx = mesh.index ?? null;
  const tris = idx ? Math.floor(idx.length / 3) : Math.floor(pos.length / 9);
  const out = new Float64Array(tris * 9);
  let k = 0;
  for (let t = 0; t < tris * 3; t++) {
    const i = idx ? idx[t]! : t;
    out[k++] = pos[3 * i]!;
    out[k++] = -pos[3 * i + 2]!;
    out[k++] = pos[3 * i + 1]!;
  }
  return out;
}

/** Volume by the divergence theorem, and whether the surface is closed (every edge shared by exactly two triangles, vertices welded at 0.1 mm). */
export function meshVolume(p: Float64Array): { volume: number; closed: boolean } {
  const n = p.length / 9;
  let v = 0;
  const ids = new Map<string, number>();
  const idOf = (x: number, y: number, z: number): number => {
    const key = `${Math.round(x * 1e4)},${Math.round(y * 1e4)},${Math.round(z * 1e4)}`;
    let i = ids.get(key);
    if (i === undefined) { i = ids.size; ids.set(key, i); }
    return i;
  };
  const edges = new Map<number, number>();
  const SH = 67108864;
  for (let t = 0; t < n; t++) {
    const o = 9 * t;
    const ax = p[o]!, ay = p[o + 1]!, az = p[o + 2]!, bx = p[o + 3]!, by = p[o + 4]!, bz = p[o + 5]!, cx = p[o + 6]!, cy = p[o + 7]!, cz = p[o + 8]!;
    v += (ax * (by * cz - bz * cy) - ay * (bx * cz - bz * cx) + az * (bx * cy - by * cx)) / 6;
    const a = idOf(ax, ay, az), b = idOf(bx, by, bz), c = idOf(cx, cy, cz);
    if (a === b || b === c || a === c) continue;
    for (const [i, j] of [[a, b], [b, c], [c, a]] as const) {
      const key = i < j ? i * SH + j : j * SH + i;
      edges.set(key, (edges.get(key) ?? 0) + 1);
    }
  }
  let closed = n >= 4;
  if (closed) for (const c of edges.values()) if (c !== 2) { closed = false; break; }
  return { volume: Math.abs(v), closed };
}

// ---------------------------------------------------------------- planar faces

interface Cluster { nx: number; ny: number; nz: number; d: number; area: number; tris: number[] }
const COS_PLANE = Math.cos((2 * Math.PI) / 180);
const PLANE_TOL = 0.005;
const MAX_CLUSTERS = 300;

interface TriInfo { area: Float64Array; n: Float64Array }

function triInfo(p: Float64Array): TriInfo {
  const t = p.length / 9;
  const area = new Float64Array(t), n = new Float64Array(t * 3);
  for (let i = 0; i < t; i++) {
    const o = 9 * i;
    const ux = p[o + 3]! - p[o]!, uy = p[o + 4]! - p[o + 1]!, uz = p[o + 5]! - p[o + 2]!, vx = p[o + 6]! - p[o]!, vy = p[o + 7]! - p[o + 1]!, vz = p[o + 8]! - p[o + 2]!;
    const nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
    const l = Math.hypot(nx, ny, nz);
    if (!(l > 1e-12)) continue;
    area[i] = l / 2;
    n[3 * i] = nx / l; n[3 * i + 1] = ny / l; n[3 * i + 2] = nz / l;
  }
  return { area, n };
}

/** Group triangles into planar faces (normals within 2 degrees, planes within 5 mm). Curved surfaces split into many small clusters, past 300 the rest is left out. */
function clusterFaces(p: Float64Array, ti: TriInfo): Cluster[] {
  const out: Cluster[] = [];
  const t = p.length / 9;
  for (let i = 0; i < t; i++) {
    const a = ti.area[i]!;
    if (!(a > 0)) continue;
    const nx = ti.n[3 * i]!, ny = ti.n[3 * i + 1]!, nz = ti.n[3 * i + 2]!;
    const d = nx * p[9 * i]! + ny * p[9 * i + 1]! + nz * p[9 * i + 2]!;
    let hit: Cluster | undefined;
    for (const c of out) if (c.nx * nx + c.ny * ny + c.nz * nz >= COS_PLANE && Math.abs(c.d - d) <= PLANE_TOL) { hit = c; break; }
    if (!hit) {
      if (out.length >= MAX_CLUSTERS) continue;
      hit = { nx, ny, nz, d, area: 0, tris: [] };
      out.push(hit);
    }
    const w = hit.area + a;
    hit.nx = (hit.nx * hit.area + nx * a) / w; hit.ny = (hit.ny * hit.area + ny * a) / w; hit.nz = (hit.nz * hit.area + nz * a) / w;
    const l = Math.hypot(hit.nx, hit.ny, hit.nz) || 1;
    hit.nx /= l; hit.ny /= l; hit.nz /= l;
    hit.d = (hit.d * hit.area + d * a) / w;
    hit.area = w;
    hit.tris.push(i);
  }
  return out;
}

// ---------------------------------------------------------------- 2D helpers

/** The minimum-area bounding rectangle of 2D points: the unit direction of its longer side and the two side lengths (long, short). */
export function minAreaRect(pts: ArrayLike<number>): { u: [number, number]; long: number; short: number } {
  const n = Math.floor(pts.length / 2);
  const P: Array<[number, number]> = [];
  for (let i = 0; i < n; i++) P.push([pts[2 * i]!, pts[2 * i + 1]!]);
  P.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  const U = P.filter((q, i) => i === 0 || q[0] !== P[i - 1]![0] || q[1] !== P[i - 1]![1]);
  if (U.length < 3) return { u: [1, 0], long: U.length ? Math.hypot(U[U.length - 1]![0] - U[0]![0], U[U.length - 1]![1] - U[0]![1]) : 0, short: 0 };
  const cr = (o: [number, number], a: [number, number], b: [number, number]): number => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
  const lo: Array<[number, number]> = [];
  for (const q of U) { while (lo.length >= 2 && cr(lo[lo.length - 2]!, lo[lo.length - 1]!, q) <= 0) lo.pop(); lo.push(q); }
  const up: Array<[number, number]> = [];
  for (let i = U.length - 1; i >= 0; i--) { const q = U[i]!; while (up.length >= 2 && cr(up[up.length - 2]!, up[up.length - 1]!, q) <= 0) up.pop(); up.push(q); }
  const H = lo.slice(0, -1).concat(up.slice(0, -1));
  let best = { area: Infinity, u: [1, 0] as [number, number], a: 0, b: 0 };
  for (let i = 0; i < H.length; i++) {
    const A = H[i]!, B = H[(i + 1) % H.length]!;
    const l = Math.hypot(B[0] - A[0], B[1] - A[1]);
    if (!(l > 1e-9)) continue;
    const ex = (B[0] - A[0]) / l, ey = (B[1] - A[1]) / l;
    let a0 = Infinity, a1 = -Infinity, b0 = Infinity, b1 = -Infinity;
    for (const q of H) {
      const s = q[0] * ex + q[1] * ey, t = -q[0] * ey + q[1] * ex;
      if (s < a0) a0 = s; if (s > a1) a1 = s; if (t < b0) b0 = t; if (t > b1) b1 = t;
    }
    const area = (a1 - a0) * (b1 - b0);
    if (area < best.area - 1e-12) best = { area, u: [ex, ey], a: a1 - a0, b: b1 - b0 };
  }
  if (!Number.isFinite(best.area)) return { u: [1, 0], long: 0, short: 0 };
  // u along the longer side
  if (best.a >= best.b) return { u: best.u, long: best.a, short: best.b };
  return { u: [-best.u[1], best.u[0]], long: best.b, short: best.a };
}

/** Two unit vectors perpendicular to `z` and to each other, with e1 as close to the world X as possible (so that for z = up they are X and Y). */
function planeBasis(z: V3): [V3, V3] {
  const h: V3 = Math.abs(z[0]) > 0.9 ? [0, 1, 0] : [1, 0, 0];
  const k = dot(h, z);
  const e1 = norm([h[0] - k * z[0], h[1] - k * z[1], h[2] - k * z[2]]);
  return [e1, cross(z, e1)];
}

/** The longer side direction (3D, unit) of the footprint of the points seen along `z`. */
function rectAlong(p: Float64Array, z: V3): { u: V3; long: number; short: number } {
  const [e1, e2] = planeBasis(z);
  const n = p.length / 3;
  const pts = new Float64Array(n * 2);
  for (let i = 0; i < n; i++) { const v = [p[3 * i]!, p[3 * i + 1]!, p[3 * i + 2]!]; pts[2 * i] = dot(v, e1); pts[2 * i + 1] = dot(v, e2); }
  const r = minAreaRect(pts);
  return { u: norm([e1[0] * r.u[0] + e2[0] * r.u[1], e1[1] * r.u[0] + e2[1] * r.u[1], e1[2] * r.u[0] + e2[2] * r.u[1]]), long: r.long, short: r.short };
}

/** Make a frame right handed (X x Y = Z) with a canonical sign of X (towards +X, else +Y). */
function frameOf(x: V3, z: V3, flip = false): { x: V3; y: V3; z: V3 } {
  let xx = norm(x);
  if (!flip && (xx[0] < -1e-9 || (Math.abs(xx[0]) <= 1e-9 && xx[1] < 0))) xx = [-xx[0], -xx[1], -xx[2]];
  const y = norm(cross(z, xx));
  return { x: norm(cross(y, z)), y, z };
}

/** The kind of frame a measured shape asks for when the role is not known (`other`). */
function resolveKind(kind: FrameKind, linear: boolean, axis: V3, planarHoriz: boolean): FrameKind {
  if (kind !== 'other') return kind;
  if (linear) return Math.abs(axis[2]) > 0.85 ? 'column' : 'beam';
  return planarHoriz ? 'slab' : 'footing';
}

// ---------------------------------------------------------------- the main function

const faceNameOf = (c: V3, kind: FrameKind): string => {
  const ax = Math.abs(c[0]), ay = Math.abs(c[1]), az = Math.abs(c[2]);
  const m = Math.max(ax, ay, az);
  if (m < 0.9) return 'INCL';
  const sgn = (v: number): string => (v >= 0 ? '+' : '-');
  if (m === az) {
    if (kind === 'column') return `END_${sgn(c[2])}`;
    return c[2] >= 0 ? 'TOP' : 'BOTTOM';
  }
  if (m === ax) return kind === 'beam' || kind === 'wall' ? `END_${sgn(c[0])}` : `SIDE_X${sgn(c[0])}`;
  return `SIDE_Y${sgn(c[1])}`;
};

const SAMPLE_SIDE = 0.15;

/** The sub-triangle sample points of one triangle (centroids of a k x k subdivision), each with the same weight area / k^2. */
const sampleK = (area: number): number => Math.max(1, Math.min(40, Math.ceil(Math.sqrt(area) / SAMPLE_SIDE)));

function* samplesOf(p: Float64Array, t: number, k: number): Generator<[number, number, number]> {
  const o = 9 * t;
  const ax = p[o]!, ay = p[o + 1]!, az = p[o + 2]!;
  const ux = (p[o + 3]! - ax) / k, uy = (p[o + 4]! - ay) / k, uz = (p[o + 5]! - az) / k;
  const vx = (p[o + 6]! - ax) / k, vy = (p[o + 7]! - ay) / k, vz = (p[o + 8]! - az) / k;
  for (let i = 0; i < k; i++) {
    for (let j = 0; j < k - i; j++) {
      yield [ax + (i + 1 / 3) * ux + (j + 1 / 3) * vx, ay + (i + 1 / 3) * uy + (j + 1 / 3) * vy, az + (i + 1 / 3) * uz + (j + 1 / 3) * vz];
      if (i + j < k - 1) yield [ax + (i + 2 / 3) * ux + (j + 2 / 3) * vx, ay + (i + 2 / 3) * uy + (j + 2 / 3) * vy, az + (i + 2 / 3) * uz + (j + 2 / 3) * vz];
    }
  }
}

const GRID = 16;

/** Section shape from the end cap: the cells of a 16 x 16 grid over the element's extents that the cap covers. */
function sectionShapeOf(p: Float64Array, ti: TriInfo, faces: Cluster[], f: Frame, axisIdx: 0 | 2, ext: V3, mins: V3): SectionShape {
  const ax = axisIdx === 0 ? f.x : f.z;
  const ai = axisIdx === 0 ? [1, 2] : [0, 1];
  let pos = 0, neg = 0;
  const pc: Cluster[] = [], nc: Cluster[] = [];
  for (const c of faces) {
    const s = dot([c.nx, c.ny, c.nz], ax);
    if (s >= 0.98) { pos += c.area; pc.push(c); } else if (s <= -0.98) { neg += c.area; nc.push(c); }
  }
  const cap = pos >= neg ? pc : nc;
  if (!cap.length) return 'IRREGULAR';
  const [a, b] = [ai[0]!, ai[1]!];
  const A = [f.x, f.y, f.z][a]!, B = [f.x, f.y, f.z][b]!;
  const ea = ext[a]!, eb = ext[b]!;
  if (!(ea > 1e-6) || !(eb > 1e-6)) return 'IRREGULAR';
  const cells = new Uint8Array(GRID * GRID);
  const loc = (o: number): [number, number] => [(dot([p[o]!, p[o + 1]!, p[o + 2]!], A) - mins[a]!) / ea, (dot([p[o]!, p[o + 1]!, p[o + 2]!], B) - mins[b]!) / eb];
  let used = 0;
  for (const c of cap) {
    const step = Math.max(1, Math.ceil(c.tris.length / 2000));
    for (let q = 0; q < c.tris.length; q += step) {
      const t = c.tris[q]!;
      const P0 = loc(9 * t), P1 = loc(9 * t + 3), P2 = loc(9 * t + 6);
      used++;
      const i0 = Math.max(0, Math.floor(Math.min(P0[0], P1[0], P2[0]) * GRID)), i1 = Math.min(GRID - 1, Math.floor(Math.max(P0[0], P1[0], P2[0]) * GRID));
      const j0 = Math.max(0, Math.floor(Math.min(P0[1], P1[1], P2[1]) * GRID)), j1 = Math.min(GRID - 1, Math.floor(Math.max(P0[1], P1[1], P2[1]) * GRID));
      const den = (P1[1] - P2[1]) * (P0[0] - P2[0]) + (P2[0] - P1[0]) * (P0[1] - P2[1]);
      if (Math.abs(den) < 1e-15) continue;
      for (let i = i0; i <= i1; i++) for (let j = j0; j <= j1; j++) {
        const x = (i + 0.5) / GRID, y = (j + 0.5) / GRID;
        const w0 = ((P1[1] - P2[1]) * (x - P2[0]) + (P2[0] - P1[0]) * (y - P2[1])) / den;
        const w1 = ((P2[1] - P0[1]) * (x - P2[0]) + (P0[0] - P2[0]) * (y - P2[1])) / den;
        if (w0 >= -1e-9 && w1 >= -1e-9 && 1 - w0 - w1 >= -1e-9) cells[i * GRID + j] = 1;
      }
    }
  }
  if (!used) return 'IRREGULAR';
  let n = 0;
  for (const c of cells) n += c;
  const fill = n / (GRID * GRID);
  const at = (i: number, j: number): number => cells[i * GRID + j]!;
  const corners = at(0, 0) + at(GRID - 1, 0) + at(0, GRID - 1) + at(GRID - 1, GRID - 1);
  const mid = [at(GRID / 2, 0), at(GRID / 2, GRID - 1), at(0, GRID / 2), at(GRID - 1, GRID / 2)];
  if (corners === 4 && fill >= 0.9) return 'RECT';
  if (corners === 0 && fill >= 0.68 && fill <= 0.88) return 'CIRC';
  if (corners === 3 && fill >= 0.35) return 'L';
  if (corners === 2 && fill >= 0.35) {
    const adjacent = at(0, 0) + at(GRID - 1, 0) === 2 || at(0, GRID - 1) + at(GRID - 1, GRID - 1) === 2 || at(0, 0) + at(0, GRID - 1) === 2 || at(GRID - 1, 0) + at(GRID - 1, GRID - 1) === 2;
    if (adjacent) return 'T';
  }
  if (corners === 4 && fill >= 0.3 && ((mid[0] === 0 && mid[1] === 0 && mid[2] === 1 && mid[3] === 1) || (mid[2] === 0 && mid[3] === 0 && mid[0] === 1 && mid[1] === 1))) return 'I';
  return 'IRREGULAR';
}

const inBox = (x: number, y: number, z: number, b: Box6, e: number): boolean => x >= b[0] - e && x <= b[3] + e && y >= b[1] - e && y <= b[4] + e && z >= b[2] - e && z <= b[5] + e;

/** Length, Width and Thickness (m) from the extents along the local X, Y, Z. Slab, footing, beam, other: X, Y, Z (a beam's Z is its depth). Wall: X, height (Z), Y. Column: Z (height), X, Y. */
export function dimensions(kind: FrameKind, size: V3): { length: number; width: number; thickness: number } {
  switch (kind) {
    case 'wall': return { length: size[0], width: size[2], thickness: size[1] };
    case 'column': return { length: size[2], width: size[0], thickness: size[1] };
    default: return { length: size[0], width: size[1], thickness: size[2] };
  }
}

/**
 * Everything measured about one concrete element. `kind` is the frame the role asks for (slab, wall, beam, column, footing; `other`
 * lets the shape decide). Null for a mesh with no triangles or no area. Without `others` no face lies against another element.
 */
export function concreteGeometry(mesh: OrientationMesh, kind: FrameKind, o: GeometryOptions = {}): ConcreteGeometry | null {
  const p = ifcTriangles(mesh);
  const ti = triInfo(p);
  const nt = p.length / 9;
  const mom = surfaceMoments(mesh);
  if (!mom || nt === 0) return null;
  const eg = eigenSym3(mom.cov);
  const s = eg.values.map((x) => Math.sqrt(Math.max(0, x)));
  const linearity = s[0]! > 1e-9 ? s[1]! / s[0]! : 1;
  let axis = norm(eg.vectors[0]);
  if (axis[2] < -1e-9 || (Math.abs(axis[2]) <= 1e-9 && axis[0] < 0)) axis = [-axis[0], -axis[1], -axis[2]];
  const faces = clusterFaces(p, ti);
  let area = 0;
  for (let i = 0; i < nt; i++) area += ti.area[i]!;
  const vol = meshVolume(p);
  const verts = p;

  const largestUp = [...faces].filter((c) => c.nz > 0.3).sort((a, b) => b.area - a.area)[0];
  const planarHoriz = !!largestUp && largestUp.nz > 0.9 && linearity >= 0.3;
  const k = resolveKind(kind, linearity < 0.3, axis, planarHoriz);

  let z: V3 = UP;
  let xdir: V3;
  let flip = false;
  if (k === 'beam' && Math.abs(axis[2]) <= 0.85) {
    xdir = axis;
    z = norm([UP[0] - dot(UP, xdir) * xdir[0], UP[1] - dot(UP, xdir) * xdir[1], UP[2] - dot(UP, xdir) * xdir[2]]);
  } else if (k === 'column' || k === 'beam') {
    z = Math.abs(axis[2]) > 0.9995 ? UP : axis;
    xdir = rectAlong(verts, z).u;
  } else if (k === 'slab' && largestUp && largestUp.nz < 0.9995 && largestUp.nz > 0.3 && largestUp.area > 0.5 * area / 2) {
    z = norm([largestUp.nx, largestUp.ny, largestUp.nz]);
    xdir = rectAlong(verts, z).u;
  } else {
    xdir = rectAlong(verts, UP).u;
  }
  if (k === 'slab' && o.supportDirs && o.supportDirs.length) {
    const d0 = o.supportDirs[0]!;
    if (o.supportDirs.every((d) => Math.abs(d[0] * d0[0] + d[1] * d0[1]) >= 0.97)) {
      const perp: V3 = [-d0[1], d0[0], 0];
      xdir = norm(perp);
    }
  }
  if (k === 'wall' && o.outward && Math.hypot(o.outward[0], o.outward[1]) > 1e-9) {
    const y0 = norm(cross(z, norm(xdir)));
    if (y0[0] * o.outward[0] + y0[1] * o.outward[1] < 0) {
      // make Y point out: reverse X (Y = Z x X flips)
      xdir = [-xdir[0], -xdir[1], -xdir[2]];
      flip = true;
    }
  }
  const fr = frameOf(xdir, z, flip);

  // extents in the frame
  const mn: V3 = [Infinity, Infinity, Infinity], mx: V3 = [-Infinity, -Infinity, -Infinity];
  const bounds: Box6 = [Infinity, Infinity, Infinity, -Infinity, -Infinity, -Infinity];
  for (let i = 0; i < nt * 3; i++) {
    const v = [p[3 * i]!, p[3 * i + 1]!, p[3 * i + 2]!];
    const loc = [dot(v, fr.x), dot(v, fr.y), dot(v, fr.z)];
    for (let a = 0; a < 3; a++) {
      if (loc[a]! < mn[a]!) mn[a] = loc[a]!;
      if (loc[a]! > mx[a]!) mx[a] = loc[a]!;
      if (v[a]! < bounds[a]!) bounds[a] = v[a]!;
      if (v[a]! > bounds[a + 3]!) bounds[a + 3] = v[a]!;
    }
  }
  const size: V3 = [mx[0] - mn[0], mx[1] - mn[1], mx[2] - mn[2]];
  const origin: V3 = [fr.x[0] * mn[0] + fr.y[0] * mn[1] + fr.z[0] * mn[2], fr.x[1] * mn[0] + fr.y[1] * mn[1] + fr.z[1] * mn[2], fr.x[2] * mn[0] + fr.y[2] * mn[1] + fr.z[2] * mn[2]];
  const frame: Frame = { origin, x: fr.x, y: fr.y, z: fr.z };
  const volumeEstimated = !vol.closed;
  const volume = vol.closed ? vol.volume : size[0] * size[1] * size[2];

  const minFace = Math.max(1e-3, 0.003 * area);
  const sectionAxis: 0 | 2 = k === 'wall' || k === 'beam' ? 0 : 2;
  const sectionShape = sectionShapeOf(p, ti, faces, frame, sectionAxis, size, mn);

  // contacts and formwork, per sample
  const others = (o.others ?? []).filter((b) => b.bounds[0] <= bounds[3] + 0.05 && b.bounds[3] >= bounds[0] - 0.05 && b.bounds[1] <= bounds[4] + 0.05 && b.bounds[4] >= bounds[1] - 0.05 && b.bounds[2] <= bounds[5] + 0.05 && b.bounds[5] >= bounds[2] - 0.05);
  const g = o.ground;
  const covered = new Float64Array(nt), grounded = new Float64Array(nt);
  const touch: Array<Set<string>> = faces.map(() => new Set<string>());
  const faceOf = new Int32Array(nt).fill(-1);
  faces.forEach((c, ci) => { for (const t of c.tris) faceOf[t] = ci; });
  let formwork = 0, top = 0, soffit = 0, groundArea = 0;
  for (let t = 0; t < nt; t++) {
    const a = ti.area[t]!;
    if (!(a > 0)) continue;
    const nx = ti.n[3 * t]!, ny = ti.n[3 * t + 1]!, nz = ti.n[3 * t + 2]!;
    if (nz >= 0.7) top += a;
    let cov = 0, gr = 0, form = 0;
    const kk = sampleK(a);
    const w = a / (kk * kk);
    for (const [x, y, zz] of samplesOf(p, t, kk)) {
      let hit: string | null = null;
      if (others.length) for (const ot of others) if (inBox(x + nx * 0.02, y + ny * 0.02, zz + nz * 0.02, ot.bounds, 0.005)) { hit = ot.id; break; }
      if (hit) { cov += w; const ci = faceOf[t]!; if (ci >= 0) touch[ci]!.add(hit); continue; }
      if (g && ((g.soffit && nz <= -0.7 && zz <= g.level + 0.02) || (g.sides && nz < 0.5 && zz <= g.level - 0.02))) { gr += w; continue; }
      if (nz < 0.5) form += w;
    }
    covered[t] = cov; grounded[t] = gr;
    formwork += form;
    groundArea += gr;
    if (nz <= -0.7) soffit += form;
  }

  const named: FaceInfo[] = [];
  const count = new Map<string, number>();
  const ordered = faces.map((c, ci) => ({ c, ci })).filter(({ c }) => c.area >= minFace).sort((a, b) => b.c.area - a.c.area);
  for (const { c, ci } of ordered) {
    const local: V3 = [r3(dot([c.nx, c.ny, c.nz], fr.x)), r3(dot([c.nx, c.ny, c.nz], fr.y)), r3(dot([c.nx, c.ny, c.nz], fr.z))];
    let name = faceNameOf(local, k);
    const n = (count.get(name) ?? 0) + 1;
    count.set(name, n);
    if (n > 1) name = `${name}#${n}`;
    let cc = 0, gg = 0;
    for (const t of c.tris) { cc += covered[t]!; gg += grounded[t]!; }
    named.push({ name, area: r3(c.area), normal: local, againstConcrete: r3(cc), againstGround: r3(gg), touches: [...touch[ci]!].sort() });
  }
  const dims = dimensions(k, size);
  const rect = rectAlong(verts, UP);
  return {
    kind: k, volume: r3(volume), volumeEstimated, area: r3(area), bounds, frame, size: [r3(size[0]), r3(size[1]), r3(size[2])],
    length: r3(dims.length), width: r3(dims.width), thickness: r3(dims.thickness), sectionShape, faces: named,
    formworkArea: r3(formwork), topArea: r3(top), soffitArea: r3(soffit), groundArea: r3(groundArea),
    planAspect: rect.short > 1e-6 ? r3(rect.long / rect.short) : 1, axis, linearity: r3(linearity), triangles: nt,
  };
}

/** The faces as a compact text: `TOP 12.3; BOTTOM 12.3 G12.3; SIDE_X+ 2 C0.5` (area m2; C = area against concrete, G = against ground). */
export function facesText(faces: readonly FaceInfo[]): string {
  return faces.map((f) => `${f.name} ${f.area}${f.againstConcrete > 0 ? ` C${f.againstConcrete}` : ''}${f.againstGround > 0 ? ` G${f.againstGround}` : ''}`).join('; ');
}

/** A vector as text "x y z" (3 decimals). */
export const vecText = (v: readonly number[]): string => v.map((n) => { const r = Math.round(n * 1000) / 1000; return String(Object.is(r, -0) ? 0 : r); }).join(' ');
