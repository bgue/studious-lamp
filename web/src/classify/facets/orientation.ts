// Orientation facet, measured: which way does an element point? Pure functions over world-space triangles. No DOM, no three.js.
// Design: docs/design/classification-facets.md section 4. User docs: docs-features/classify.md, "Facets".
//
// Input frame: the viewer's, y up (x east, z south). Output frame: IFC (X east, Y north, Z up): (X, Y, Z) = (x, -z, y).
// Tilt is the angle from horizontal (0 flat, 90 upright). Azimuth is a direction in plan, degrees from +X towards +Y, folded into
// [0, 180) because a line has no sense.
//
// Method: principal axes of the surface by area-weighted PCA (the exact second moment of every triangle, so a dense end does not
// dominate). The standard deviations along the axes give the shape: linear (one long axis), planar (two), compact (three alike).

export interface OrientationMesh {
  /** Vertex positions, x y z, viewer frame. */
  position: ArrayLike<number>;
  /** Triangle indices; absent: every 3 vertices are a triangle. */
  index?: ArrayLike<number> | null;
}

export type OrientationClass = 'HORIZONTAL' | 'VERTICAL' | 'INCLINED' | 'ALONG_X' | 'ALONG_Y' | 'DIAGONAL';
export type OrientationShape = 'linear' | 'planar' | 'compact';

export interface OrientationMeasure {
  shape: OrientationShape;
  class: OrientationClass;
  /** Degrees from horizontal, 0 to 90, 0.1 precision. Linear: of the main axis. Planar: of the plane (the angle of its normal from vertical). */
  tilt: number;
  /** Degrees in plan, 0 to 180 (0.1 precision). Linear: the main axis. Planar and not flat: the plane normal. Flat or compact: the longest horizontal side. */
  azimuth: number;
  /** true / false when the element has a "top" and it can be told; null otherwise. */
  upright: boolean | null;
  /** 'X', 'Y' or 'Z' when the main direction (axis of a linear element, normal of a planar one) is within 5 degrees of that axis; else null. */
  principalAxis: 'X' | 'Y' | 'Z' | null;
  /** The main direction (linear axis or planar normal) in IFC axes, unit length, with a non-negative Z (X when Z is 0). */
  axis: [number, number, number];
  /** Standard deviations along the principal axes, longest first, metres. */
  spread: [number, number, number];
  /** The box of the triangles, IFC axes: sizes along X, Y, Z. */
  size: [number, number, number];
  /** Triangles used, and their total area (m2). */
  triangles: number;
  area: number;
}

/** Within this angle (degrees) of an axis counts as along it. */
export const AXIS_TOLERANCE = 5;
/** Linear: second spread over first below this. */
const LINEAR_RATIO = 0.3;
/** Planar: third spread over second below this. */
const PLANAR_RATIO = 0.35;

const DEG = 180 / Math.PI;
const r1 = (n: number): number => {
  const r = Math.round(n * 10) / 10;
  return Object.is(r, -0) ? 0 : r;
};

/** Eigen decomposition of a symmetric 3x3 matrix by Jacobi rotations. Eigenvalues descending, vectors as columns' rows (v[i] is the vector of value i). */
export function eigenSym3(m: number[][]): { values: [number, number, number]; vectors: [number[], number[], number[]] } {
  const a = m.map((r) => r.slice());
  const v = [[1, 0, 0], [0, 1, 0], [0, 0, 1]];
  for (let sweep = 0; sweep < 32; sweep++) {
    const off = Math.abs(a[0]![1]!) + Math.abs(a[0]![2]!) + Math.abs(a[1]![2]!);
    if (off < 1e-300) break;
    for (const [p, q] of [[0, 1], [0, 2], [1, 2]] as const) {
      const apq = a[p]![q]!;
      if (Math.abs(apq) < 1e-300) continue;
      const theta = (a[q]![q]! - a[p]![p]!) / (2 * apq);
      const t = Math.sign(theta || 1) / (Math.abs(theta) + Math.sqrt(theta * theta + 1));
      const c = 1 / Math.sqrt(t * t + 1);
      const s = t * c;
      for (let k = 0; k < 3; k++) {
        const akp = a[k]![p]!, akq = a[k]![q]!;
        a[k]![p] = c * akp - s * akq;
        a[k]![q] = s * akp + c * akq;
      }
      for (let k = 0; k < 3; k++) {
        const apk = a[p]![k]!, aqk = a[q]![k]!;
        a[p]![k] = c * apk - s * aqk;
        a[q]![k] = s * apk + c * aqk;
      }
      for (let k = 0; k < 3; k++) {
        const vkp = v[k]![p]!, vkq = v[k]![q]!;
        v[k]![p] = c * vkp - s * vkq;
        v[k]![q] = s * vkp + c * vkq;
      }
    }
  }
  const order = [0, 1, 2].sort((i, j) => a[j]![j]! - a[i]![i]!);
  const vec = (i: number): number[] => [v[0]![i]!, v[1]![i]!, v[2]![i]!];
  return { values: [a[order[0]!]![order[0]!]!, a[order[1]!]![order[1]!]!, a[order[2]!]![order[2]!]!], vectors: [vec(order[0]!), vec(order[1]!), vec(order[2]!)] };
}

interface Moments {
  cov: number[][];
  centroid: [number, number, number];
  area: number;
  triangles: number;
  min: [number, number, number];
  max: [number, number, number];
  /** Horizontal-facing area in the lowest and the highest tenth of the height. */
  baseArea: number;
  topArea: number;
}

/** Area-weighted second moments of the surface, in IFC axes. Null for no triangles or no area. */
export function surfaceMoments(mesh: OrientationMesh): Moments | null {
  const pos = mesh.position;
  const idx = mesh.index ?? null;
  const tris = idx ? Math.floor(idx.length / 3) : Math.floor(pos.length / 9);
  if (tris === 0) return null;
  const cov = [[0, 0, 0], [0, 0, 0], [0, 0, 0]];
  let area = 0;
  const first = [0, 0, 0];
  const min: [number, number, number] = [Infinity, Infinity, Infinity];
  const max: [number, number, number] = [-Infinity, -Infinity, -Infinity];
  const vtx = (i: number): [number, number, number] => [pos[3 * i]!, -pos[3 * i + 2]!, pos[3 * i + 1]!];
  const faceNz: number[] = [];
  const faceZ: number[] = [];
  const faceA: number[] = [];
  let used = 0;
  for (let t = 0; t < tris; t++) {
    const ia = idx ? idx[3 * t]! : 3 * t, ib = idx ? idx[3 * t + 1]! : 3 * t + 1, ic = idx ? idx[3 * t + 2]! : 3 * t + 2;
    const A = vtx(ia), B = vtx(ib), C = vtx(ic);
    for (const P of [A, B, C]) for (let k = 0; k < 3; k++) { if (P[k]! < min[k]!) min[k] = P[k]!; if (P[k]! > max[k]!) max[k] = P[k]!; }
    const ux = B[0] - A[0], uy = B[1] - A[1], uz = B[2] - A[2], vx = C[0] - A[0], vy = C[1] - A[1], vz = C[2] - A[2];
    const nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
    const len = Math.hypot(nx, ny, nz);
    const a = len / 2;
    if (!(a > 0) || !Number.isFinite(a)) continue;
    used++;
    area += a;
    const S = [A[0] + B[0] + C[0], A[1] + B[1] + C[1], A[2] + B[2] + C[2]];
    for (let i = 0; i < 3; i++) {
      first[i]! += (a * S[i]!) / 3;
      for (let j = i; j < 3; j++) cov[i]![j]! += (a / 12) * (A[i]! * A[j]! + B[i]! * B[j]! + C[i]! * C[j]! + S[i]! * S[j]!);
    }
    faceNz.push(Math.abs(nz) / len);
    faceZ.push((A[2] + B[2] + C[2]) / 3);
    faceA.push(a);
  }
  if (used === 0 || !(area > 0)) return null;
  const cx = first[0]! / area, cy = first[1]! / area, cz = first[2]! / area;
  const c = [cx, cy, cz];
  for (let i = 0; i < 3; i++) for (let j = i; j < 3; j++) cov[i]![j] = cov[i]![j]! / area - c[i]! * c[j]!;
  cov[1]![0] = cov[0]![1]!; cov[2]![0] = cov[0]![2]!; cov[2]![1] = cov[1]![2]!;
  // Horizontal-facing area near the base and near the top.
  const h = max[2] - min[2];
  let baseArea = 0, topArea = 0;
  if (h > 1e-9) {
    for (let k = 0; k < faceZ.length; k++) {
      if (faceNz[k]! < 0.7) continue;
      const rel = (faceZ[k]! - min[2]) / h;
      if (rel <= 0.1) baseArea += faceA[k]!;
      else if (rel >= 0.9) topArea += faceA[k]!;
    }
  }
  return { cov, centroid: [cx, cy, cz], area, triangles: used, min, max, baseArea, topArea };
}

const clampUnit = (x: number): number => Math.max(-1, Math.min(1, x));

/** Fold a direction so Z >= 0 (and X > 0 when Z is 0), and make it unit length. */
function foldAxis(v: number[]): [number, number, number] {
  const n = Math.hypot(v[0]!, v[1]!, v[2]!) || 1;
  let x = v[0]! / n, y = v[1]! / n, z = v[2]! / n;
  if (z < -1e-9 || (Math.abs(z) <= 1e-9 && (x < -1e-9 || (Math.abs(x) <= 1e-9 && y < 0)))) { x = -x; y = -y; z = -z; }
  return [x, y, z];
}

const planAzimuth = (x: number, y: number): number => {
  let a = Math.atan2(y, x) * DEG;
  a = ((a % 180) + 180) % 180;
  return r1(a) === 180 ? 0 : r1(a);
};

export interface MeasureOptions {
  /** The local +Z of the element's placement in IFC axes (a unit vector), when the model carries it: decides `upright` before the geometry does. */
  localUp?: readonly [number, number, number] | null;
  /** Compute `upright` (the element has a top: doors, windows, stairs, furniture, equipment). Default false. */
  hasTop?: boolean;
}

/** Orientation of one element from its world-space triangles. Null for an element with no triangles or no area. */
export function measureOrientation(mesh: OrientationMesh, o: MeasureOptions = {}): OrientationMeasure | null {
  const m = surfaceMoments(mesh);
  if (!m) return null;
  const e = eigenSym3(m.cov);
  const s = e.values.map((x) => Math.sqrt(Math.max(0, x))) as [number, number, number];
  if (!(s[0] > 1e-9)) return null;
  const size: [number, number, number] = [m.max[0] - m.min[0], m.max[1] - m.min[1], m.max[2] - m.min[2]];
  let shape: OrientationShape;
  if (s[1] / s[0] < LINEAR_RATIO) shape = 'linear';
  else if (s[2] / Math.max(s[1], 1e-12) < PLANAR_RATIO) shape = 'planar';
  else shape = 'compact';

  let axis: [number, number, number];
  let tilt: number;
  let azimuth: number;
  let cls: OrientationClass;
  if (shape === 'linear') {
    axis = foldAxis(e.vectors[0]);
    tilt = Math.asin(clampUnit(Math.abs(axis[2]))) * DEG;
    azimuth = planAzimuth(axis[0], axis[1]);
    if (tilt >= 90 - AXIS_TOLERANCE) cls = 'VERTICAL';
    else if (tilt <= AXIS_TOLERANCE) {
      const a = azimuth % 90;
      cls = a <= AXIS_TOLERANCE || a >= 90 - AXIS_TOLERANCE ? (azimuth < 45 || azimuth >= 135 ? 'ALONG_X' : 'ALONG_Y') : 'DIAGONAL';
    } else cls = 'INCLINED';
  } else if (shape === 'planar') {
    axis = foldAxis(e.vectors[2]);
    tilt = Math.acos(clampUnit(Math.abs(axis[2]))) * DEG;
    if (tilt <= AXIS_TOLERANCE) {
      cls = 'HORIZONTAL';
      const a = foldAxis(e.vectors[0]);
      azimuth = planAzimuth(a[0], a[1]);
    } else {
      cls = tilt >= 90 - AXIS_TOLERANCE ? 'VERTICAL' : 'INCLINED';
      azimuth = planAzimuth(axis[0], axis[1]);
    }
  } else {
    // compact: lying on its footprint; the azimuth is its longest horizontal side
    axis = [0, 0, 1];
    tilt = 0;
    cls = 'HORIZONTAL';
    azimuth = size[0] >= size[1] ? 0 : 90;
  }
  const principalAxis: OrientationMeasure['principalAxis'] =
    Math.abs(axis[2]) >= Math.cos((AXIS_TOLERANCE * Math.PI) / 180) ? 'Z'
      : Math.abs(axis[0]) >= Math.cos((AXIS_TOLERANCE * Math.PI) / 180) ? 'X'
        : Math.abs(axis[1]) >= Math.cos((AXIS_TOLERANCE * Math.PI) / 180) ? 'Y' : null;

  let upright: boolean | null = null;
  if (o.hasTop) {
    if (o.localUp) {
      const uz = o.localUp[2];
      if (uz > 0.7) upright = true;
      else if (uz < -0.7) upright = false;
    }
    if (upright === null) {
      const { baseArea, topArea } = m;
      if (baseArea + topArea > 1e-9) {
        if (baseArea >= topArea * 1.5 && baseArea > 1e-9) upright = true;
        else if (topArea >= baseArea * 1.5 && topArea > 1e-9) upright = false;
      }
    }
  }
  return { shape, class: cls, tilt: r1(tilt), azimuth, upright, principalAxis, axis, spread: s, size, triangles: m.triangles, area: m.area };
}

// ---------------------------------------------------------------- plausibility

const WALLS = new Set(['IfcWall', 'IfcWallStandardCase', 'IfcWallElementedCase', 'IfcCurtainWall']);
const SLABS = new Set(['IfcSlab', 'IfcSlabStandardCase', 'IfcSlabElementedCase']);
const COLUMNS = new Set(['IfcColumn', 'IfcColumnStandardCase', 'IfcPile']);
const BEAMS = new Set(['IfcBeam', 'IfcBeamStandardCase']);
/** Classes that have a top: the facet then tells upright from upside down. */
export const HAS_TOP = new Set([
  'IfcDoor', 'IfcWindow', 'IfcStair', 'IfcStairFlight', 'IfcFurniture', 'IfcFurnishingElement', 'IfcSanitaryTerminal', 'IfcElectricAppliance',
  'IfcPump', 'IfcTank', 'IfcBoiler', 'IfcChiller', 'IfcFan', 'IfcTransportElement', 'IfcUnitaryEquipment', 'IfcAirToAirHeatRecovery',
]);
/** Classes that may take any orientation. */
const ANY = new Set(['IfcRoof', 'IfcPipeSegment', 'IfcPipeFitting', 'IfcDuctSegment', 'IfcDuctFitting', 'IfcCableCarrierSegment', 'IfcCableSegment', 'IfcCovering', 'IfcPlate', 'IfcRamp', 'IfcRampFlight', 'IfcRailing', 'IfcMember', 'IfcFlowSegment']);

/** Does this class have a top (so upright is measured)? */
export const hasTop = (ifcClass: string): boolean => HAS_TOP.has(ifcClass);

export interface PlausibleInput {
  ifcClass: string;
  measure: OrientationMeasure;
  /** The PredefinedType of the element (a skylight is a window that lies flat). */
  predefinedType?: string;
}

/**
 * Does the orientation suit the class? True, false, or null when the class is not in the table (nothing to say).
 * IfcWall: vertical (or a standing short wall). IfcSlab: horizontal or inclined. IfcColumn: vertical or inclined. IfcBeam: along X, along Y,
 * diagonal or inclined. IfcDoor and IfcWindow: vertical and not upside down. IfcRoof, pipes, ducts and the like: any.
 */
export function orientationPlausible(i: PlausibleInput): boolean | null {
  const { ifcClass: c, measure: m } = i;
  // vertical extent against the smaller horizontal extent: a wall that stands up is taller than it is thick
  const standing = m.size[2] >= Math.min(m.size[0], m.size[1]) * 0.99;
  if (ANY.has(c)) return true;
  if (WALLS.has(c)) {
    if (m.class === 'VERTICAL') return true;
    if (m.class === 'INCLINED') return m.tilt >= 60;
    return m.shape !== 'planar' && standing; // a short stub of wall, measured as a bar
  }
  if (SLABS.has(c)) {
    if (m.class === 'HORIZONTAL' || m.class === 'INCLINED') return true;
    if (m.class === 'VERTICAL') return false;
    return !standing; // a narrow strip of slab along an axis
  }
  if (COLUMNS.has(c)) {
    if (m.class === 'VERTICAL' || m.class === 'INCLINED') return true;
    return m.shape === 'compact' && m.size[2] >= 0.7 * Math.max(m.size[0], m.size[1]); // a squat column measured as compact
  }
  if (BEAMS.has(c)) {
    return m.class !== 'VERTICAL';
  }
  if (c === 'IfcDoor') return m.class === 'VERTICAL' && m.upright !== false;
  if (c === 'IfcWindow') {
    const sky = /SKYLIGHT|LIGHTDOME/i.test(i.predefinedType ?? '');
    return (m.class === 'VERTICAL' || m.class === 'INCLINED' || sky) && m.upright !== false;
  }
  if (HAS_TOP.has(c)) return m.upright !== false;
  return null;
}
