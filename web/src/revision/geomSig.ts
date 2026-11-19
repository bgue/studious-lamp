// The geometry signature of an element: 11 numbers that are surface integrals, so they do not depend on how the surface is
// triangulated (design 3.2). Pure: typed arrays in, typed arrays out. One pass over the triangles, Float64 accumulators, positions
// taken relative to the element's first vertex so large coordinates cost no precision.
//
//   area, |signed volume| (0 when the surface is open), area-weighted centroid, the three eigenvalues of the area-weighted
//   covariance (descending), and the axis-aligned extent.
//
// The arrays of a MergedGeometry are in viewer axes (Y up, origin shifted). `computeSignatures` returns IFC axes (x, -z, y) with the
// centroid still relative to the model's origin shift; the diff adds the shift in Float64 (see snapshot.ts).

import { SIG_STRIDE } from './types';
import type { GeomSig } from './types';

export interface IndexRange {
  start: number;
  count: number;
}

/** The triangles of a model: positions (xyz per vertex), a triangle index, and each element's index range. */
export interface TriangleSource {
  position: ArrayLike<number>;
  index: ArrayLike<number>;
  ranges: ReadonlyArray<IndexRange>;
}

/** [start, count] pairs in a Uint32Array (the layout of MergedArrays.ranges) as ranges. */
export function rangesOfPairs(u: ArrayLike<number>): IndexRange[] {
  const n = Math.floor(u.length / 2);
  const out: IndexRange[] = new Array(n);
  for (let i = 0; i < n; i++) out[i] = { start: u[i * 2]!, count: u[i * 2 + 1]! };
  return out;
}

/** Eigenvalues of the symmetric matrix [[xx,xy,xz],[xy,yy,yz],[xz,yz,zz]], descending. */
export function eigenvalues3(xx: number, yy: number, zz: number, xy: number, xz: number, yz: number): Vec3Tuple {
  const p1 = xy * xy + xz * xz + yz * yz;
  const q = (xx + yy + zz) / 3;
  const scale = Math.abs(xx) + Math.abs(yy) + Math.abs(zz);
  if (p1 <= 1e-30 * scale * scale) {
    const d = [xx, yy, zz].sort((a, b) => b - a);
    return [d[0]!, d[1]!, d[2]!];
  }
  const p2 = (xx - q) ** 2 + (yy - q) ** 2 + (zz - q) ** 2 + 2 * p1;
  const p = Math.sqrt(p2 / 6);
  const bxx = (xx - q) / p, byy = (yy - q) / p, bzz = (zz - q) / p, bxy = xy / p, bxz = xz / p, byz = yz / p;
  const det = bxx * (byy * bzz - byz * byz) - bxy * (bxy * bzz - byz * bxz) + bxz * (bxy * byz - byy * bxz);
  const r = Math.max(-1, Math.min(1, det / 2));
  const phi = Math.acos(r) / 3;
  const e1 = q + 2 * p * Math.cos(phi);
  const e3 = q + 2 * p * Math.cos(phi + (2 * Math.PI) / 3);
  const e2 = 3 * q - e1 - e3;
  return [e1, e2, e3];
}
type Vec3Tuple = [number, number, number];

/**
 * The signature of one index range, written into out[o .. o+11) in viewer axes (the caller converts, see computeSignatures).
 * An empty range gives zeros.
 */
export function signatureOfRange(position: ArrayLike<number>, index: ArrayLike<number>, start: number, count: number, out: Float32Array | number[], o: number): void {
  const end = start + count - (count % 3);
  if (end <= start) {
    for (let k = 0; k < SIG_STRIDE; k++) out[o + k] = 0;
    return;
  }
  const i0 = index[start]! * 3;
  const rx = position[i0]!, ry = position[i0 + 1]!, rz = position[i0 + 2]!;
  let area = 0, vol6 = 0;
  let gx = 0, gy = 0, gz = 0;
  let sxx = 0, syy = 0, szz = 0, sxy = 0, sxz = 0, syz = 0;
  let vax = 0, vay = 0, vaz = 0;
  let minx = Infinity, miny = Infinity, minz = Infinity, maxx = -Infinity, maxy = -Infinity, maxz = -Infinity;
  for (let t = start; t < end; t += 3) {
    const a = index[t]! * 3, b = index[t + 1]! * 3, c = index[t + 2]! * 3;
    const ax = position[a]! - rx, ay = position[a + 1]! - ry, az = position[a + 2]! - rz;
    const bx = position[b]! - rx, by = position[b + 1]! - ry, bz = position[b + 2]! - rz;
    const cx = position[c]! - rx, cy = position[c + 1]! - ry, cz = position[c + 2]! - rz;
    if (ax < minx) minx = ax; if (bx < minx) minx = bx; if (cx < minx) minx = cx;
    if (ax > maxx) maxx = ax; if (bx > maxx) maxx = bx; if (cx > maxx) maxx = cx;
    if (ay < miny) miny = ay; if (by < miny) miny = by; if (cy < miny) miny = cy;
    if (ay > maxy) maxy = ay; if (by > maxy) maxy = by; if (cy > maxy) maxy = cy;
    if (az < minz) minz = az; if (bz < minz) minz = bz; if (cz < minz) minz = cz;
    if (az > maxz) maxz = az; if (bz > maxz) maxz = bz; if (cz > maxz) maxz = cz;
    const ux = bx - ax, uy = by - ay, uz = bz - az, wx = cx - ax, wy = cy - ay, wz = cz - az;
    const nx = uy * wz - uz * wy, ny = uz * wx - ux * wz, nz = ux * wy - uy * wx;
    const A = 0.5 * Math.sqrt(nx * nx + ny * ny + nz * nz);
    if (A === 0) continue;
    area += A;
    vax += nx; vay += ny; vaz += nz;
    vol6 += ax * (by * cz - bz * cy) - ay * (bx * cz - bz * cx) + az * (bx * cy - by * cx);
    const sx = ax + bx + cx, sy = ay + by + cy, sz = az + bz + cz;
    gx += (A * sx) / 3; gy += (A * sy) / 3; gz += (A * sz) / 3;
    const k = A / 12;
    sxx += k * (ax * ax + bx * bx + cx * cx + sx * sx);
    syy += k * (ay * ay + by * by + cy * cy + sy * sy);
    szz += k * (az * az + bz * bz + cz * cz + sz * sz);
    sxy += k * (ax * ay + bx * by + cx * cy + sx * sy);
    sxz += k * (ax * az + bx * bz + cx * cz + sx * sz);
    syz += k * (ay * az + by * bz + cy * cz + sy * sz);
  }
  if (area === 0) {
    for (let k = 0; k < SIG_STRIDE; k++) out[o + k] = 0;
    return;
  }
  const mx = gx / area, my = gy / area, mz = gz / area;
  const [e1, e2, e3] = eigenvalues3(sxx / area - mx * mx, syy / area - my * my, szz / area - mz * mz, sxy / area - mx * my, sxz / area - mx * mz, syz / area - my * mz);
  // An open surface has a vector area sum that does not cancel; its signed volume then depends on the origin: report 0.
  const closed = Math.sqrt(vax * vax + vay * vay + vaz * vaz) * 0.5 <= 1e-3 * area;
  // viewer axes (x, y, z) -> IFC axes (x, -z, y): the centroid shifts to IFC axes, the extent swaps y and z.
  out[o] = area;
  out[o + 1] = closed ? Math.abs(vol6) / 6 : 0;
  out[o + 2] = rx + mx;
  out[o + 3] = -(rz + mz);
  out[o + 4] = ry + my;
  out[o + 5] = e1;
  out[o + 6] = e2;
  out[o + 7] = e3;
  out[o + 8] = maxx - minx;
  out[o + 9] = maxz - minz;
  out[o + 10] = maxy - miny;
}

/** All signatures at once (synchronous). 11 floats per range. */
export function computeSignatures(src: TriangleSource, out: Float32Array = new Float32Array(src.ranges.length * SIG_STRIDE), from = 0, to = src.ranges.length): Float32Array {
  for (let e = from; e < to; e++) {
    const r = src.ranges[e]!;
    signatureOfRange(src.position, src.index, r.start, r.count, out, e * SIG_STRIDE);
  }
  return out;
}

export interface SlicedOptions {
  /** Longest stretch of work between two yields (default 8 ms). */
  sliceMs?: number;
  now?: () => number;
  /** Give the event loop a turn (default: a macrotask). */
  yieldToUi?: () => Promise<void>;
  onProgress?: (done: number, total: number) => void;
  signal?: { aborted: boolean };
}

/**
 * The same result as computeSignatures, computed in `sliceMs` slices so the main thread stays responsive (the arrays are hundreds
 * of MB and cannot be copied to a worker). 10 M triangles take about 0.5 s of work, spread over about 60 frames. Resolves null when aborted.
 */
export async function computeSignaturesSliced(src: TriangleSource, o: SlicedOptions = {}): Promise<Float32Array | null> {
  const n = src.ranges.length;
  const out = new Float32Array(n * SIG_STRIDE);
  const now = o.now ?? (() => performance.now());
  const sliceMs = o.sliceMs ?? 8;
  const yieldToUi = o.yieldToUi ?? (() => new Promise<void>((r) => setTimeout(r, 0)));
  let e = 0;
  while (e < n) {
    if (o.signal?.aborted) return null;
    const t0 = now();
    // check the clock every 64 elements: a range is small, the clock call is not free
    do {
      const stop = Math.min(n, e + 64);
      computeSignatures(src, out, e, stop);
      e = stop;
    } while (e < n && now() - t0 < sliceMs);
    o.onProgress?.(e, n);
    if (e < n) await yieldToUi();
  }
  return out;
}

/** One element's signature as an object. */
export function sigAt(sig: ArrayLike<number>, i: number): GeomSig {
  const o = i * SIG_STRIDE;
  return {
    area: sig[o]!,
    volume: sig[o + 1]!,
    centroid: [sig[o + 2]!, sig[o + 3]!, sig[o + 4]!],
    moments: [sig[o + 5]!, sig[o + 6]!, sig[o + 7]!],
    extent: [sig[o + 8]!, sig[o + 9]!, sig[o + 10]!],
  };
}

/** Relative difference |a-b| / max(|a|,|b|,1e-9). */
export const rel = (a: number, b: number): number => Math.abs(a - b) / Math.max(Math.abs(a), Math.abs(b), 1e-9);
