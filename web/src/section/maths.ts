// Pure maths of sectioning: clip planes (normal points to the KEPT half-space), the section box and its
// handles, the section plane, and the projection of a pointer ray onto a handle's axis line.
// No three.js, no DOM. Coordinates are viewer coordinates (Y up), metres.

export type Vec3 = [number, number, number];
export type Box6 = readonly [number, number, number, number, number, number];

export interface ClipPlane {
  /** Points toward the kept half-space (not necessarily unit length when read back from BCF; the renderer normalises). */
  normal: Vec3;
  /** Any point on the plane. */
  point: Vec3;
}

/** The renderer evaluates this many planes per fragment (a box needs 6, a section plane 1, one spare). */
export const MAX_CLIP_PLANES = 8;

const dot = (a: Vec3, b: Vec3): number => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const len = (a: Vec3): number => Math.hypot(a[0], a[1], a[2]);

export function normalizePlane(p: ClipPlane): ClipPlane | null {
  const l = len(p.normal);
  if (!(l > 1e-9) || !p.point.every(Number.isFinite)) return null;
  return { normal: [p.normal[0] / l, p.normal[1] / l, p.normal[2] / l], point: [p.point[0], p.point[1], p.point[2]] };
}

/** Plane as (nx, ny, nz, w) with a point p kept when n . p + w >= 0. */
export function planeToVec4(p: ClipPlane): [number, number, number, number] {
  const n = normalizePlane(p);
  if (!n) return [0, 0, 0, 1];
  return [n.normal[0], n.normal[1], n.normal[2], -dot(n.normal, n.point)];
}

/** Signed distance of a point from the plane, positive on the kept side. */
export function signedDistance(p: ClipPlane, q: Vec3): number {
  const n = normalizePlane(p);
  if (!n) return 1;
  return n.normal[0] * (q[0] - n.point[0]) + n.normal[1] * (q[1] - n.point[1]) + n.normal[2] * (q[2] - n.point[2]);
}

/** Is the point on the kept side of every plane? */
export function pointKept(planes: ReadonlyArray<ClipPlane>, q: Vec3): boolean {
  for (const p of planes) if (signedDistance(p, q) < 0) return false;
  return true;
}

export function planesEqual(a: ReadonlyArray<ClipPlane> | null, b: ReadonlyArray<ClipPlane> | null, eps = 1e-6): boolean {
  const x = a ?? [];
  const y = b ?? [];
  if (x.length !== y.length) return false;
  for (let i = 0; i < x.length; i++) {
    for (let k = 0; k < 3; k++) {
      if (Math.abs(x[i]!.normal[k]! - y[i]!.normal[k]!) > eps || Math.abs(x[i]!.point[k]! - y[i]!.point[k]!) > eps) return false;
    }
  }
  return true;
}

// ---------------------------------------------------------------- box

export interface SectionBox {
  min: Vec3;
  max: Vec3;
}

/** Union of boxes, grown by `margin` metres on every side. Null for an empty list. */
export function fitBox(boxes: ReadonlyArray<Box6>, margin: number): SectionBox | null {
  if (boxes.length === 0) return null;
  const min: Vec3 = [Infinity, Infinity, Infinity];
  const max: Vec3 = [-Infinity, -Infinity, -Infinity];
  for (const b of boxes) {
    for (let a = 0; a < 3; a++) {
      if (b[a]! < min[a]!) min[a] = b[a]!;
      if (b[a + 3]! > max[a]!) max[a] = b[a + 3]!;
    }
  }
  const m = Math.max(margin, 0);
  return { min: [min[0] - m, min[1] - m, min[2] - m], max: [max[0] + m, max[1] + m, max[2] + m] };
}

export function boxCentre(b: SectionBox): Vec3 {
  return [(b.min[0] + b.max[0]) / 2, (b.min[1] + b.max[1]) / 2, (b.min[2] + b.max[2]) / 2];
}

/** The six planes of a box keeping its inside: order -x, +x, -y, +y, -z, +z (the plane of the min face first). */
export function boxPlanes(b: SectionBox): ClipPlane[] {
  const out: ClipPlane[] = [];
  for (let a = 0; a < 3; a++) {
    const nMin: Vec3 = [0, 0, 0];
    nMin[a] = 1;
    const pMin: Vec3 = boxCentre(b);
    pMin[a] = b.min[a]!;
    const nMax: Vec3 = [0, 0, 0];
    nMax[a] = -1;
    const pMax: Vec3 = boxCentre(b);
    pMax[a] = b.max[a]!;
    out.push({ normal: nMin, point: pMin }, { normal: nMax, point: pMax });
  }
  return out;
}

export function boxCorners(b: SectionBox): Vec3[] {
  const out: Vec3[] = [];
  for (let i = 0; i < 8; i++) out.push([i & 1 ? b.max[0] : b.min[0], i & 2 ? b.max[1] : b.min[1], i & 4 ? b.max[2] : b.min[2]]);
  return out;
}

/** The 12 edges of a box as corner index pairs into boxCorners. */
export const BOX_EDGES: ReadonlyArray<readonly [number, number]> = [
  [0, 1], [2, 3], [4, 5], [6, 7],
  [0, 2], [1, 3], [4, 6], [5, 7],
  [0, 4], [1, 5], [2, 6], [3, 7],
];

export interface Handle {
  /** 0..5, in the order of boxPlanes: -x +x -y +y -z +z. */
  index: number;
  axis: 0 | 1 | 2;
  side: 'min' | 'max';
  /** Face centre. */
  point: Vec3;
  /** Unit direction of the handle's axis line. */
  dir: Vec3;
}

export function boxHandles(b: SectionBox): Handle[] {
  const c = boxCentre(b);
  const out: Handle[] = [];
  for (let a = 0; a < 3; a++) {
    for (const side of ['min', 'max'] as const) {
      const p: Vec3 = [c[0], c[1], c[2]];
      p[a] = side === 'min' ? b.min[a]! : b.max[a]!;
      const d: Vec3 = [0, 0, 0];
      d[a] = 1;
      out.push({ index: a * 2 + (side === 'min' ? 0 : 1), axis: a as 0 | 1 | 2, side, point: p, dir: d });
    }
  }
  return out;
}

/**
 * Parameter t along the line `lineP + t * lineD` that is closest to the ray `rayO + s * rayD` (both directions need
 * not be unit length). Null when the ray is parallel to the line (or degenerate). Used to drag a face along its axis.
 */
export function closestParamOnLine(rayO: Vec3, rayD: Vec3, lineP: Vec3, lineD: Vec3): number | null {
  const w: Vec3 = [rayO[0] - lineP[0], rayO[1] - lineP[1], rayO[2] - lineP[2]];
  const a = dot(rayD, rayD);
  const b = dot(rayD, lineD);
  const c = dot(lineD, lineD);
  const d = dot(rayD, w);
  const e = dot(lineD, w);
  const den = a * c - b * b;
  if (!(Math.abs(den) > 1e-9 * a * c)) return null;
  return (a * e - b * d) / den;
}

/** Smallest box extent a drag may leave, metres. */
export const MIN_BOX_SIZE = 0.05;

/** Move one face of the box to coordinate `value` along its axis, keeping at least MIN_BOX_SIZE of extent. */
export function moveFace(b: SectionBox, h: Pick<Handle, 'axis' | 'side'>, value: number): SectionBox {
  const min: Vec3 = [b.min[0], b.min[1], b.min[2]];
  const max: Vec3 = [b.max[0], b.max[1], b.max[2]];
  if (h.side === 'min') min[h.axis] = Math.min(value, max[h.axis] - MIN_BOX_SIZE);
  else max[h.axis] = Math.max(value, min[h.axis] + MIN_BOX_SIZE);
  return { min, max };
}

/**
 * A drag step: the pointer ray moves the handle's face along its axis. `grabT` is the line parameter under the pointer
 * when the drag started (closestParamOnLine at pointer down), so the face does not jump to the pointer. Null when the
 * ray is parallel to the axis. `b` and `h` are the box and handle as they were at pointer down.
 */
export function dragHandle(b: SectionBox, h: Handle, rayO: Vec3, rayD: Vec3, grabT = 0): SectionBox | null {
  const t = closestParamOnLine(rayO, rayD, h.point, h.dir);
  if (t === null) return null;
  return moveFace(b, h, h.point[h.axis] + t - grabT);
}

// ---------------------------------------------------------------- plane

export type PlaneAxis = 'x' | 'y' | 'z' | 'camera';

/**
 * The section plane through `centre` shifted by `offset` metres along the axis (camera: along the view direction).
 * The kept side is the positive side of the axis (camera: away from the viewer); `flip` keeps the other side.
 */
export function sectionPlane(axis: PlaneAxis, centre: Vec3, offset: number, flip: boolean, camForward: Vec3): ClipPlane {
  let n: Vec3;
  if (axis === 'camera') {
    const l = len(camForward) || 1;
    n = [camForward[0] / l, camForward[1] / l, camForward[2] / l];
  } else {
    n = [axis === 'x' ? 1 : 0, axis === 'y' ? 1 : 0, axis === 'z' ? 1 : 0];
  }
  const point: Vec3 = [centre[0] + n[0] * offset, centre[1] + n[1] * offset, centre[2] + n[2] * offset];
  const k = flip ? -1 : 1;
  return { normal: [n[0] * k + 0, n[1] * k + 0, n[2] * k + 0], point }; // + 0 turns -0 into 0
}

/** Everything the section config asks for as one plane list (box first, then the plane). */
export function planesFor(box: SectionBox | null, boxOn: boolean, plane: ClipPlane | null): ClipPlane[] {
  const out: ClipPlane[] = [];
  if (boxOn && box) out.push(...boxPlanes(box));
  if (plane) out.push(plane);
  return out.slice(0, MAX_CLIP_PLANES);
}
