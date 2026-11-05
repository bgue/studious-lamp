// Rigid (and similarity) registration maths for point cloud alignment. Pure, double precision, no DOM, no three.js.
//
// Matrices are 4x4, column-major (the layout of three's Matrix4.elements), as plain number arrays of 16, so they go
// into the params document as they are. The viewer frame is Y up: "keep vertical" means a rotation about Y only
// (a yaw) plus a translation, which is what a gravity-aligned phone or tripod scan needs.
//
//   solvePairs   point pairs (cloud -> model), least squares:
//                full 3D     Horn's closed-form quaternion method (Kabsch without the reflection case), with the
//                            Umeyama scale when allowScale
//                keep vertical  2D Kabsch on the horizontal plane (x, z) plus the mean vertical offset
//   jacobiEigen  symmetric eigen decomposition (Horn's 4x4 and the 3x3 spread used for the collinearity check)

import type { Vec3 } from './types';

export type Mat4 = number[];

export const identity = (): Mat4 => [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];

export function isIdentity(m: ArrayLike<number>, eps = 1e-12): boolean {
  const id = identity();
  for (let i = 0; i < 16; i++) if (Math.abs(m[i]! - id[i]!) > eps) return false;
  return true;
}

/** a * b (apply b first). */
export function mul(a: ArrayLike<number>, b: ArrayLike<number>): Mat4 {
  const o = new Array<number>(16).fill(0);
  for (let c = 0; c < 4; c++) {
    for (let r = 0; r < 4; r++) {
      let s = 0;
      for (let k = 0; k < 4; k++) s += a[k * 4 + r]! * b[c * 4 + k]!;
      o[c * 4 + r] = s;
    }
  }
  return o;
}

export function translation(x: number, y: number, z: number): Mat4 {
  return [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, x, y, z, 1];
}

/** Rotation about the viewer's vertical axis Y (three's makeRotationY: x' = c x + s z, z' = -s x + c z). */
export function rotationY(rad: number): Mat4 {
  const c = Math.cos(rad), s = Math.sin(rad);
  return [c, 0, -s, 0, 0, 1, 0, 0, s, 0, c, 0, 0, 0, 0, 1];
}

/** 4x4 from a row-major 3x3 rotation R, a uniform scale and a translation: p' = s R p + t. */
export function compose(R: number[], s: number, t: Vec3): Mat4 {
  return [s * R[0]!, s * R[3]!, s * R[6]!, 0, s * R[1]!, s * R[4]!, s * R[7]!, 0, s * R[2]!, s * R[5]!, s * R[8]!, 0, t[0], t[1], t[2], 1];
}

export function apply(m: ArrayLike<number>, p: ArrayLike<number>): Vec3 {
  const x = p[0]!, y = p[1]!, z = p[2]!;
  return [m[0]! * x + m[4]! * y + m[8]! * z + m[12]!, m[1]! * x + m[5]! * y + m[9]! * z + m[13]!, m[2]! * x + m[6]! * y + m[10]! * z + m[14]!];
}

/** Uniform scale of a similarity matrix (cube root of the determinant of the 3x3 part). */
export function scaleOf(m: ArrayLike<number>): number {
  const d =
    m[0]! * (m[5]! * m[10]! - m[9]! * m[6]!) - m[4]! * (m[1]! * m[10]! - m[9]! * m[2]!) + m[8]! * (m[1]! * m[6]! - m[5]! * m[2]!);
  return Math.cbrt(d);
}

/** Inverse of a similarity transform p' = s R p + t. */
export function invertSimilarity(m: ArrayLike<number>): Mat4 {
  const s = scaleOf(m);
  const k = 1 / (s * s);
  // inverse 3x3 = R^T / s = M3^T / s^2; transposing a column-major 3x3 reads it row by row
  const t = [m[12]!, m[13]!, m[14]!];
  const o: Mat4 = [m[0]! * k, m[4]! * k, m[8]! * k, 0, m[1]! * k, m[5]! * k, m[9]! * k, 0, m[2]! * k, m[6]! * k, m[10]! * k, 0, 0, 0, 0, 1];
  const ti = apply(o, t);
  o[12] = -ti[0];
  o[13] = -ti[1];
  o[14] = -ti[2];
  return o;
}

/**
 * True when m is a rotation about Y (any angle) plus a translation, with scale 1: the alignment then has an exact
 * offset + rotation (deg) form.
 */
export function isYawOnly(m: ArrayLike<number>, eps = 1e-9): boolean {
  return (
    Math.abs(m[1]!) < eps && Math.abs(m[4]!) < eps && Math.abs(m[6]!) < eps && Math.abs(m[9]!) < eps && Math.abs(m[5]! - 1) < eps &&
    Math.abs(m[0]! - m[10]!) < eps && Math.abs(m[2]! + m[8]!) < eps && Math.abs(m[0]! * m[0]! + m[8]! * m[8]! - 1) < eps &&
    Math.abs(m[3]!) < eps && Math.abs(m[7]!) < eps && Math.abs(m[11]!) < eps && Math.abs(m[15]! - 1) < eps
  );
}

/** Yaw of a matrix in degrees (-180..180]: the heading of its x axis about Y. */
export function yawDeg(m: ArrayLike<number>): number {
  return (Math.atan2(m[8]!, m[0]!) * 180) / Math.PI;
}

/** Angle of the rotation between two similarity matrices, degrees, and the distance between where they put `at`. */
export function transformError(a: ArrayLike<number>, b: ArrayLike<number>, at: Vec3 = [0, 0, 0]): { rotationDeg: number; translation: number; scale: number } {
  const sa = scaleOf(a), sb = scaleOf(b);
  // R = Ra^T Rb, trace -> angle
  let tr = 0;
  for (let i = 0; i < 3; i++) for (let k = 0; k < 3; k++) tr += (a[i * 4 + k]! / sa) * (b[i * 4 + k]! / sb);
  const cos = Math.min(1, Math.max(-1, (tr - 1) / 2));
  const pa = apply(a, at), pb = apply(b, at);
  return { rotationDeg: (Math.acos(cos) * 180) / Math.PI, translation: Math.hypot(pa[0] - pb[0], pa[1] - pb[1], pa[2] - pb[2]), scale: sb / sa };
}

// ---------------------------------------------------------------- eigen

/** Eigenvalues (descending) and eigenvectors (columns of a row-major n x n matrix) of a symmetric matrix. */
export function jacobiEigen(a: number[], n: number): { values: number[]; vectors: number[] } {
  const A = a.slice();
  const V = new Array<number>(n * n).fill(0);
  for (let i = 0; i < n; i++) V[i * n + i] = 1;
  for (let sweep = 0; sweep < 60; sweep++) {
    let off = 0;
    for (let p = 0; p < n; p++) for (let q = p + 1; q < n; q++) off += A[p * n + q]! * A[p * n + q]!;
    if (off < 1e-30) break;
    for (let p = 0; p < n; p++) {
      for (let q = p + 1; q < n; q++) {
        const apq = A[p * n + q]!;
        if (Math.abs(apq) < 1e-300) continue;
        const theta = (A[q * n + q]! - A[p * n + p]!) / (2 * apq);
        const t = Math.sign(theta || 1) / (Math.abs(theta) + Math.sqrt(theta * theta + 1));
        const c = 1 / Math.sqrt(t * t + 1);
        const s = t * c;
        for (let k = 0; k < n; k++) {
          const akp = A[k * n + p]!, akq = A[k * n + q]!;
          A[k * n + p] = c * akp - s * akq;
          A[k * n + q] = s * akp + c * akq;
        }
        for (let k = 0; k < n; k++) {
          const apk = A[p * n + k]!, aqk = A[q * n + k]!;
          A[p * n + k] = c * apk - s * aqk;
          A[q * n + k] = s * apk + c * aqk;
        }
        for (let k = 0; k < n; k++) {
          const vkp = V[k * n + p]!, vkq = V[k * n + q]!;
          V[k * n + p] = c * vkp - s * vkq;
          V[k * n + q] = s * vkp + c * vkq;
        }
      }
    }
  }
  const order = Array.from({ length: n }, (_, i) => i).sort((i, j) => A[j * n + j]! - A[i * n + i]!);
  const values = order.map((i) => A[i * n + i]!);
  const vectors = new Array<number>(n * n);
  order.forEach((src, dst) => {
    for (let k = 0; k < n; k++) vectors[k * n + dst] = V[k * n + src]!;
  });
  return { values, vectors };
}

// ---------------------------------------------------------------- spread / collinearity

export interface Spread {
  /** Standard deviations along the principal axes, metres, descending. */
  sigma: [number, number, number];
  /** sigma[1] / sigma[0]: 0 for points on a line, about 0.5 or more for a well spread triangle. */
  planarity: number;
  /** Standard deviation on the horizontal plane (x, z), metres (largest axis). */
  horizontal: number;
}

export function spreadOf(pts: readonly Vec3[]): Spread {
  const n = pts.length;
  if (!n) return { sigma: [0, 0, 0], planarity: 0, horizontal: 0 };
  const c = [0, 0, 0];
  for (const p of pts) for (let k = 0; k < 3; k++) c[k]! += p[k]! / n;
  const C = new Array<number>(9).fill(0);
  for (const p of pts) {
    const d = [p[0] - c[0]!, p[1] - c[1]!, p[2] - c[2]!];
    for (let i = 0; i < 3; i++) for (let j = 0; j < 3; j++) C[i * 3 + j]! += (d[i]! * d[j]!) / n;
  }
  const { values } = jacobiEigen(C, 3);
  const sigma = values.map((v) => Math.sqrt(Math.max(0, v))) as [number, number, number];
  // horizontal 2x2 (x, z)
  const a = C[0]!, b = C[2]!, d = C[8]!;
  const l1 = (a + d) / 2 + Math.sqrt(((a - d) / 2) ** 2 + b * b);
  return { sigma, planarity: sigma[0] > 0 ? sigma[1] / sigma[0] : 0, horizontal: Math.sqrt(Math.max(0, l1)) };
}

// ---------------------------------------------------------------- pair solve

export interface SolveOptions {
  /** Yaw (about Y) and translation only. */
  keepVertical: boolean;
  /** Also estimate a uniform scale (Umeyama). */
  allowScale: boolean;
}

export interface PairSolution {
  /** cloud -> model, column-major. Identity when the solve failed. */
  matrix: Mat4;
  ok: boolean;
  scale: number;
  /** |model - matrix * cloud| per pair, metres. */
  residuals: number[];
  rms: number;
  /** Plain-language problems: too few pairs, nearly collinear, large residual, odd scale. */
  warnings: string[];
  /** Pairs needed for this mode (2 with keep vertical, 3 otherwise). */
  needed: number;
}

/** Thresholds of the warnings, metres or ratios. */
export const PAIR_LIMITS = { collinear: 0.08, degenerate: 0.01, minSpread: 0.05, rms: 0.05, residual: 0.1 };

/**
 * Least squares rigid (or similarity) transform that maps `src` (cloud) onto `dst` (model). With keepVertical the
 * rotation is about Y only: the yaw comes from the 2D Kabsch problem on (x, z), the vertical offset is the mean.
 */
export function solvePairs(src: readonly Vec3[], dst: readonly Vec3[], opt: SolveOptions): PairSolution {
  const n = Math.min(src.length, dst.length);
  const needed = opt.keepVertical ? 2 : 3;
  const fail = (w: string): PairSolution => ({ matrix: identity(), ok: false, scale: 1, residuals: [], rms: NaN, warnings: [w], needed });
  if (n < needed) return fail(`Pick at least ${needed} pairs${opt.keepVertical ? '' : ' (3 for a full 3D rotation)'}.`);
  const warnings: string[] = [];
  const ss = spreadOf(src.slice(0, n)), sd = spreadOf(dst.slice(0, n));
  if (opt.keepVertical) {
    if (Math.min(ss.horizontal, sd.horizontal) < PAIR_LIMITS.minSpread) return fail('The points lie above each other: pick points further apart on plan.');
  } else {
    const pl = Math.min(ss.planarity, sd.planarity);
    if (pl < PAIR_LIMITS.degenerate || Math.min(ss.sigma[1], sd.sigma[1]) < 0.005) return fail('The points lie on a line: the rotation about that line is unknown. Pick a point off the line.');
    if (pl < PAIR_LIMITS.collinear) warnings.push('The points are nearly on a line: the result is sensitive to small picking errors. Pick a point further off the line.');
  }
  const cs = [0, 0, 0], cd = [0, 0, 0];
  for (let i = 0; i < n; i++) for (let k = 0; k < 3; k++) {
    cs[k]! += src[i]![k]! / n;
    cd[k]! += dst[i]![k]! / n;
  }
  const a = src.slice(0, n).map((p) => [p[0] - cs[0]!, p[1] - cs[1]!, p[2] - cs[2]!]);
  const b = dst.slice(0, n).map((p) => [p[0] - cd[0]!, p[1] - cd[1]!, p[2] - cd[2]!]);
  let R: number[]; // row-major 3x3
  if (opt.keepVertical) {
    let A = 0, B = 0;
    for (let i = 0; i < n; i++) {
      A += b[i]![0]! * a[i]![0]! + b[i]![2]! * a[i]![2]!;
      B += b[i]![0]! * a[i]![2]! - b[i]![2]! * a[i]![0]!;
    }
    const th = Math.atan2(B, A);
    const c = Math.cos(th), s = Math.sin(th);
    R = [c, 0, s, 0, 1, 0, -s, 0, c];
  } else {
    const S = new Array<number>(9).fill(0); // S[i][j] = sum a_i b_j
    for (let k = 0; k < n; k++) for (let i = 0; i < 3; i++) for (let j = 0; j < 3; j++) S[i * 3 + j]! += a[k]![i]! * b[k]![j]!;
    const [xx, xy, xz, yx, yy, yz, zx, zy, zz] = S as [number, number, number, number, number, number, number, number, number];
    const N = [
      xx + yy + zz, yz - zy, zx - xz, xy - yx,
      yz - zy, xx - yy - zz, xy + yx, zx + xz,
      zx - xz, xy + yx, -xx + yy - zz, yz + zy,
      xy - yx, zx + xz, yz + zy, -xx - yy + zz,
    ];
    const { vectors } = jacobiEigen(N, 4);
    let w = vectors[0]!, x = vectors[4]!, y = vectors[8]!, z = vectors[12]!;
    const qn = Math.hypot(w, x, y, z) || 1;
    w /= qn; x /= qn; y /= qn; z /= qn;
    R = [
      1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w),
      2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w),
      2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y),
    ];
  }
  let scale = 1;
  if (opt.allowScale) {
    let num = 0, den = 0;
    for (let i = 0; i < n; i++) {
      const ra = [
        R[0]! * a[i]![0]! + R[1]! * a[i]![1]! + R[2]! * a[i]![2]!,
        R[3]! * a[i]![0]! + R[4]! * a[i]![1]! + R[5]! * a[i]![2]!,
        R[6]! * a[i]![0]! + R[7]! * a[i]![1]! + R[8]! * a[i]![2]!,
      ];
      num += ra[0]! * b[i]![0]! + ra[1]! * b[i]![1]! + ra[2]! * b[i]![2]!;
      den += a[i]![0]! ** 2 + a[i]![1]! ** 2 + a[i]![2]! ** 2;
    }
    scale = den > 0 && num > 0 ? num / den : 1;
    if (Math.abs(scale - 1) > 0.05) warnings.push(`The scale is ${scale.toFixed(3)}: phone and laser scans are in metres, so check the pairs or turn allow scale off.`);
  }
  const rcs = [R[0]! * cs[0]! + R[1]! * cs[1]! + R[2]! * cs[2]!, R[3]! * cs[0]! + R[4]! * cs[1]! + R[5]! * cs[2]!, R[6]! * cs[0]! + R[7]! * cs[1]! + R[8]! * cs[2]!];
  const t: Vec3 = [cd[0]! - scale * rcs[0]!, cd[1]! - scale * rcs[1]!, cd[2]! - scale * rcs[2]!];
  const matrix = compose(R, scale, t);
  const residuals = src.slice(0, n).map((p, i) => {
    const q = apply(matrix, p);
    return Math.hypot(q[0] - dst[i]![0], q[1] - dst[i]![1], q[2] - dst[i]![2]);
  });
  const rms = Math.sqrt(residuals.reduce((s, r) => s + r * r, 0) / n);
  if (n > needed) {
    let worst = 0;
    residuals.forEach((r, i) => { if (r > residuals[worst]!) worst = i; });
    if (rms > PAIR_LIMITS.rms || residuals[worst]! > PAIR_LIMITS.residual) warnings.push(`Large residual: pair ${worst + 1} is ${(residuals[worst]! * 100).toFixed(1)} cm off. Check that its 2 points are the same feature.`);
  }
  return { matrix, ok: true, scale, residuals, rms, warnings, needed };
}

/** "1.2 cm" below a metre, "1.234 m" above; "3 mm" below a centimetre. */
export function formatDistance(m: number): string {
  if (!Number.isFinite(m)) return '-';
  const a = Math.abs(m);
  if (a < 0.01) return `${(m * 1000).toFixed(1)} mm`;
  if (a < 1) return `${(m * 100).toFixed(1)} cm`;
  return `${m.toFixed(3)} m`;
}
