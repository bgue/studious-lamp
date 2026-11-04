// Coordinates and alignment. Pure maths, no DOM.
//
// IFC project coordinates are Z up and metres. The viewer is Y up, shifted by the model's `originShift` (IFC frame):
//   v = (x - sx, z - sz, -(y - sy))        (tools/glb_common.py write_model: rotate -90 degrees about X after the shift)
// so a rotation about the viewer's vertical axis (Y) by an angle is a rotation about IFC Z by the same angle.
//
// A cloud is drawn with the transform
//   p' = Ry(theta) * (g + base - pivot) + pivot + offset
// where g is the Float32 position relative to the cloud's double precision origin, already axis-mapped; base is the
// mapped origin (double, minus the shift: small when cloud and model share a frame); pivot is the mapped bounds centre.
// Everything large is combined in double inside the 4x4 matrix, so the Float32 vertex data stays small.

import { Matrix4 } from 'three';
import type { Vec3 } from './types';

export type CoordMode = 'project' | 'viewer';

export function projectToViewer(p: Vec3, shift: Vec3): Vec3 {
  return [p[0] - shift[0], p[2] - shift[2], -(p[1] - shift[1])];
}

export function viewerToProject(v: Vec3, shift: Vec3): Vec3 {
  return [v[0] + shift[0], -v[2] + shift[1], v[1] + shift[2]];
}

/** Direction (no shift): IFC (x, y, z) -> viewer (x, z, -y). */
export function mapAxes(p: Vec3, mode: CoordMode): Vec3 {
  return mode === 'project' ? [p[0], p[2], -p[1]] : [p[0], p[1], p[2]];
}

/** Copy of relative positions with the axis mapping applied (the input when mode is 'viewer'). */
export function mapPositions(rel: Float32Array, mode: CoordMode): Float32Array {
  if (mode === 'viewer') return rel;
  const out = new Float32Array(rel.length);
  for (let i = 0; i < rel.length; i += 3) {
    out[i] = rel[i]!;
    out[i + 1] = rel[i + 2]!;
    out[i + 2] = -rel[i + 1]!;
  }
  return out;
}

export interface FrameParams {
  mode: CoordMode;
  /** Model originShift (IFC frame). Ignored in viewer mode. */
  shift: Vec3;
  offset: Vec3;
  rotationDeg: number;
}

export interface CloudGeometryInfo {
  origin: Vec3;
  boundsMin: Vec3;
  boundsMax: Vec3;
}

export interface CloudFrame {
  /** Mapped origin in the viewer frame (before offset and rotation). */
  base: Vec3;
  /** Mapped bounds centre in the viewer frame (before offset and rotation). */
  pivot: Vec3;
  matrix: Matrix4;
}

const toViewer = (p: Vec3, f: FrameParams): Vec3 => (f.mode === 'project' ? projectToViewer(p, f.shift) : [p[0], p[1], p[2]]);

export function cloudFrame(info: CloudGeometryInfo, f: FrameParams): CloudFrame {
  const base = toViewer(info.origin, f);
  const centre: Vec3 = [
    (info.boundsMin[0] + info.boundsMax[0]) / 2,
    (info.boundsMin[1] + info.boundsMax[1]) / 2,
    (info.boundsMin[2] + info.boundsMax[2]) / 2,
  ];
  const pivot = toViewer(centre, f);
  const m = new Matrix4().makeTranslation(pivot[0] + f.offset[0], pivot[1] + f.offset[1], pivot[2] + f.offset[2]);
  m.multiply(new Matrix4().makeRotationY((f.rotationDeg * Math.PI) / 180));
  m.multiply(new Matrix4().makeTranslation(base[0] - pivot[0], base[1] - pivot[1], base[2] - pivot[2]));
  return { base, pivot, matrix: m };
}

/** Viewer position of a mapped relative position g. */
export function applyFrame(frame: CloudFrame, g: Vec3): Vec3 {
  const e = frame.matrix.elements;
  return [
    e[0]! * g[0] + e[4]! * g[1] + e[8]! * g[2] + e[12]!,
    e[1]! * g[0] + e[5]! * g[1] + e[9]! * g[2] + e[13]!,
    e[2]! * g[0] + e[6]! * g[1] + e[10]! * g[2] + e[14]!,
  ];
}

// ---------------------------------------------------------------- auto align

export interface AutoAlignInput {
  /** Cloud pivot (mapped bounds centre) in the viewer frame. */
  pivot: Vec3;
  /** Sample of the cloud, viewer frame, with the current base (no offset, no rotation), 3 floats per point, relative to `pivot`. */
  samplesRelPivot: Float32Array;
  modelMin: Vec3;
  modelMax: Vec3;
  /** Distance from a viewer point to the model surface (Infinity when none within `max`). Needed for the rotation search. */
  distance?: (x: number, y: number, z: number) => number;
  /** Also search 0, 90, 180, 270 degrees about the vertical axis. */
  rotate: boolean;
}

export interface AutoAlignResult {
  offset: Vec3;
  rotationDeg: number;
  /** Median distance of the sample to the model for each tried angle (empty when no rotation search ran). */
  scores: Array<{ deg: number; median: number }>;
  description: string;
}

/**
 * Step 1: translate so the cloud's bounds centre lands on the model's bounds centre.
 * Step 2 (optional): try 0, 90, 180 and 270 degrees about the vertical axis through that centre and keep the one whose
 * sample has the smallest median distance to the model. No fine registration (no ICP); the result is a coarse start
 * that the manual offset and rotation can refine.
 */
export function autoAlign(inp: AutoAlignInput): AutoAlignResult {
  const mc: Vec3 = [(inp.modelMin[0] + inp.modelMax[0]) / 2, (inp.modelMin[1] + inp.modelMax[1]) / 2, (inp.modelMin[2] + inp.modelMax[2]) / 2];
  const offset: Vec3 = [mc[0] - inp.pivot[0], mc[1] - inp.pivot[1], mc[2] - inp.pivot[2]];
  const scores: Array<{ deg: number; median: number }> = [];
  let best = 0;
  if (inp.rotate && inp.distance) {
    const s = inp.samplesRelPivot;
    const n = Math.floor(s.length / 3);
    const dist = new Float64Array(n);
    let bestMed = Infinity;
    for (const deg of [0, 90, 180, 270]) {
      const c = Math.cos((deg * Math.PI) / 180);
      const sn = Math.sin((deg * Math.PI) / 180);
      for (let i = 0; i < n; i++) {
        const x = s[i * 3]!, y = s[i * 3 + 1]!, z = s[i * 3 + 2]!;
        // makeRotationY: x' = c x + s z, z' = -s x + c z
        dist[i] = inp.distance(mc[0] + c * x + sn * z, mc[1] + y, mc[2] - sn * x + c * z);
      }
      const med = median(dist);
      scores.push({ deg, median: med });
      if (med < bestMed - 1e-9) {
        bestMed = med;
        best = deg;
      }
    }
  }
  const d = (v: number): string => v.toFixed(3);
  const description =
    `Moved the cloud bounds centre onto the model bounds centre (offset ${d(offset[0])}, ${d(offset[1])}, ${d(offset[2])} m)` +
    (scores.length ? `; tried 0/90/180/270 degrees by median distance of ${Math.floor(inp.samplesRelPivot.length / 3)} sample points (${scores.map((x) => `${x.deg}: ${isFinite(x.median) ? (x.median * 100).toFixed(1) + ' cm' : 'none near'}`).join(', ')}), kept ${best}.` : '; no rotation search.');
  return { offset, rotationDeg: best, scores, description };
}

export function median(a: ArrayLike<number>): number {
  const n = a.length;
  if (n === 0) return NaN;
  const c = Float64Array.from(Array.from(a)).sort();
  return n % 2 ? c[(n - 1) / 2]! : (c[n / 2 - 1]! + c[n / 2]!) / 2;
}
