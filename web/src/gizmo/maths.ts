// Pure maths of the gizmo (navigation cube and section handles): cube regions to view direction and up vector, roll
// and quarter turns, the projection of the cube for drawing, screen drags along an axis, ring angles and snapping.
// No three.js, no DOM. Viewer coordinates: Y up, IFC front (looking north) is the camera on +Z, right is +X.

export type V3 = [number, number, number];
export type V2 = [number, number];

export const dot = (a: readonly number[], b: readonly number[]): number => a[0]! * b[0]! + a[1]! * b[1]! + a[2]! * b[2]!;
export const cross = (a: readonly number[], b: readonly number[]): V3 => [a[1]! * b[2]! - a[2]! * b[1]!, a[2]! * b[0]! - a[0]! * b[2]!, a[0]! * b[1]! - a[1]! * b[0]!];
export const scale = (a: readonly number[], k: number): V3 => [a[0]! * k, a[1]! * k, a[2]! * k];
export const add = (a: readonly number[], b: readonly number[]): V3 => [a[0]! + b[0]!, a[1]! + b[1]!, a[2]! + b[2]!];
export const sub = (a: readonly number[], b: readonly number[]): V3 => [a[0]! - b[0]!, a[1]! - b[1]!, a[2]! - b[2]!];
export const length = (a: readonly number[]): number => Math.hypot(a[0]!, a[1]!, a[2]!);
export function normalize(a: readonly number[]): V3 {
  const l = length(a);
  return l > 1e-12 ? [a[0]! / l, a[1]! / l, a[2]! / l] : [0, 0, 0];
}
/** Remove -0 so that results compare cleanly. */
const clean = (a: V3): V3 => [Math.abs(a[0]) < 1e-12 ? 0 : a[0], Math.abs(a[1]) < 1e-12 ? 0 : a[1], Math.abs(a[2]) < 1e-12 ? 0 : a[2]];

// ---------------------------------------------------------------- cube regions

/**
 * A clickable part of the cube as the sign of each axis: a face has one non-zero component, an edge two, a corner
 * three. The camera looks at the model from the region's side.
 */
export type Region = readonly [-1 | 0 | 1, -1 | 0 | 1, -1 | 0 | 1];

export const FACE_NAMES: Readonly<Record<string, string>> = {
  '1,0,0': 'Right', '-1,0,0': 'Left', '0,1,0': 'Top', '0,-1,0': 'Bottom', '0,0,1': 'Front', '0,0,-1': 'Back',
};

/** All 26 regions: 6 faces, 12 edges, 8 corners. */
export function allRegions(): Region[] {
  const out: Region[] = [];
  for (const x of [-1, 0, 1] as const) for (const y of [-1, 0, 1] as const) for (const z of [-1, 0, 1] as const) if (x || y || z) out.push([x, y, z]);
  return out;
}

export function regionKind(r: Region): 'face' | 'edge' | 'corner' {
  const n = (r[0] ? 1 : 0) + (r[1] ? 1 : 0) + (r[2] ? 1 : 0);
  return n === 1 ? 'face' : n === 2 ? 'edge' : 'corner';
}

/** "Top", "Top Front", "Top Front Right": vertical first, then front/back, then left/right. */
export function regionName(r: Region): string {
  const parts: string[] = [];
  if (r[1]) parts.push(r[1] > 0 ? 'Top' : 'Bottom');
  if (r[2]) parts.push(r[2] > 0 ? 'Front' : 'Back');
  if (r[0]) parts.push(r[0] > 0 ? 'Right' : 'Left');
  return parts.join(' ');
}

/** Unit vector from the target to the camera for a region. */
export function regionDirection(r: Region): V3 {
  return normalize([r[0], r[1], r[2]]);
}

/** True when the direction is vertical (top or bottom view), where world up cannot be the screen up. */
export function isVertical(dir: readonly number[], eps = 1e-6): boolean {
  return Math.abs(dir[1]!) > 1 - eps;
}

/**
 * The up vector of an unrolled view from direction `dir` (target to camera): world up projected on the view plane.
 * Straight down (top) the screen up is -Z, so the back (north) is at the top of the screen as on a plan; straight up
 * (bottom) it is +Z.
 */
export function naturalUp(dir: readonly number[]): V3 {
  const d = normalize(dir);
  if (isVertical(d)) return d[1] > 0 ? [0, 0, -1] : [0, 0, 1];
  return clean(normalize(sub([0, 1, 0], scale(d, d[1]))));
}

export interface View {
  /** Unit vector from the target to the camera. */
  direction: V3;
  /** Unit screen up, perpendicular to `direction`. */
  up: V3;
}

/** The view a click on a region asks for. */
export function regionView(r: Region): View {
  const direction = regionDirection(r);
  return { direction, up: naturalUp(direction) };
}

/** Rodrigues rotation of `v` about the unit axis `axis` by `angle` radians (right hand rule). */
export function rotateAbout(v: readonly number[], axis: readonly number[], angle: number): V3 {
  const k = normalize(axis);
  const c = Math.cos(angle);
  const s = Math.sin(angle);
  const kv = cross(k, v);
  const kd = dot(k, v) * (1 - c);
  return clean([v[0]! * c + kv[0] * s + k[0] * kd, v[1]! * c + kv[1] * s + k[1] * kd, v[2]! * c + kv[2] * s + k[2] * kd]);
}

/**
 * Roll the view a quarter turn about the view axis. `sign` +1 turns the picture clockwise on screen (the camera up
 * turns counter-clockwise, towards the screen left), -1 counter-clockwise. The direction does not change.
 */
export function rollView(v: View, sign: 1 | -1): View {
  return { direction: [...v.direction], up: rotateAbout(v.up, v.direction, (sign * Math.PI) / 2) };
}

/** Turn the view a quarter turn about the vertical axis through the target. `sign` +1 moves the camera to its right. */
export function turnView(v: View, sign: 1 | -1): View {
  const a = (sign * Math.PI) / 2;
  return { direction: rotateAbout(v.direction, [0, 1, 0], a), up: rotateAbout(v.up, [0, 1, 0], a) };
}

/**
 * Can the turntable camera (orbit controls with world up = +Y) show this view without a roll? Any view that is not
 * vertical needs up = naturalUp(direction); a vertical view works with any horizontal up (the azimuth sets it).
 */
export function isUnrolled(v: View, eps = 1e-4): boolean {
  if (isVertical(v.direction)) return Math.abs(v.up[1]) < eps;
  return length(sub(v.up, naturalUp(v.direction))) < eps;
}

/**
 * Offset direction (target to camera) that makes a turntable camera show `v` without a roll. A vertical view is
 * tipped by `tilt` radians away from the screen up, so the azimuth of the camera sets the screen up.
 */
export function turntableOffset(v: View, tilt = 1e-4): V3 {
  if (!isVertical(v.direction)) return [...v.direction];
  return normalize(sub(v.direction, scale(v.up, tilt)));
}

/** Camera basis (right, up, back = towards the viewer) of a view. */
export function viewBasis(v: View): { right: V3; up: V3; back: V3 } {
  const back = normalize(v.direction);
  const up = normalize(sub(v.up, scale(back, dot(v.up, back))));
  return { right: clean(cross(up, back)), up: clean(up), back: clean(back) };
}

/** The region whose view is closest to `dir` when it is within `maxDeg` degrees, else null. Highlights the current face. */
export function regionNear(dir: readonly number[], maxDeg = 1): Region | null {
  const d = normalize(dir);
  let best: Region | null = null;
  let bestDot = Math.cos((maxDeg * Math.PI) / 180);
  for (const r of allRegions()) {
    const k = dot(regionDirection(r), d);
    if (k >= bestDot) {
      bestDot = k;
      best = r;
    }
  }
  return best;
}

// ---------------------------------------------------------------- drawing the cube

export interface CubeCell {
  region: Region;
  /** The face the cell lies on (a face region). */
  face: Region;
  /** Polygon in screen units, y down, centred on the cube centre, for a cube of half size 1. */
  points: V2[];
  /** Mean depth towards the viewer (larger is nearer). */
  depth: number;
}

/** Fraction of a face's half width taken by the edge and corner cells. */
export const EDGE_BAND = 0.32;

/**
 * The visible cells of a unit cube (half size 1) seen with camera basis (right, up, back), projected orthographically.
 * Each visible face gives 9 cells: the face centre, 4 edge strips and 4 corner squares. Sorted far to near.
 */
export function cubeCells(right: readonly number[], up: readonly number[], back: readonly number[]): CubeCell[] {
  const out: CubeCell[] = [];
  const t = 1 - 2 * EDGE_BAND; // inner square half size
  const ticks = [-1, -t, t, 1];
  for (let axis = 0; axis < 3; axis++) {
    for (const s of [1, -1] as const) {
      const n: V3 = [0, 0, 0];
      n[axis] = s;
      if (dot(n, back) <= 0.02) continue; // edge on: a sliver nobody can click
      const ua = (axis + 1) % 3;
      const va = (axis + 2) % 3;
      const face = [0, 0, 0] as unknown as [-1 | 0 | 1, -1 | 0 | 1, -1 | 0 | 1];
      face[axis] = s;
      for (let i = 0; i < 3; i++) {
        for (let j = 0; j < 3; j++) {
          const reg = [0, 0, 0] as unknown as [-1 | 0 | 1, -1 | 0 | 1, -1 | 0 | 1];
          reg[axis] = s;
          reg[ua] = (i - 1) as -1 | 0 | 1;
          reg[va] = (j - 1) as -1 | 0 | 1;
          const corners: V3[] = [];
          for (const [a, b] of [[i, j], [i + 1, j], [i + 1, j + 1], [i, j + 1]] as const) {
            const p: V3 = [0, 0, 0];
            p[axis] = s;
            p[ua] = ticks[a]!;
            p[va] = ticks[b]!;
            corners.push(p);
          }
          let depth = 0;
          const points = corners.map((p): V2 => {
            depth += dot(p, back) / 4;
            return [dot(p, right), -dot(p, up)];
          });
          out.push({ region: reg, face, points, depth });
        }
      }
    }
  }
  return out.sort((a, b) => a.depth - b.depth);
}

/**
 * In-face axes of a face for its label, chosen so the text reads upright from the face's own standard view:
 * Top reads with the back at the top of the screen, Bottom with the front at the top.
 */
export function faceLabelAxes(face: Region): { u: V3; v: V3 } {
  const n = regionDirection(face);
  const up = naturalUp(n);
  return { u: clean(cross(up, n)), v: up };
}

// ---------------------------------------------------------------- dragging handles

/**
 * Metres along an axis for a pointer move of `delta` CSS pixels, when 1 m along the axis spans `axisScreen` pixels on
 * screen. The move is projected on the axis's screen direction. Null when the axis is (almost) square to the screen.
 */
export function axisDragMetres(delta: V2, axisScreen: V2, minPxPerMetre = 1e-3): number | null {
  const l2 = axisScreen[0] * axisScreen[0] + axisScreen[1] * axisScreen[1];
  if (!(l2 > minPxPerMetre * minPxPerMetre)) return null;
  return (delta[0] * axisScreen[0] + delta[1] * axisScreen[1]) / l2;
}

/**
 * Angle in radians of the point where the ray `o + s d` meets the plane through `centre` square to `axis`, measured
 * about `axis` from `ref` (right hand rule). Null when the ray is parallel to that plane.
 */
export function ringAngle(o: V3, d: V3, centre: V3, axis: V3, ref: V3): number | null {
  const k = normalize(axis);
  const den = dot(d, k);
  if (Math.abs(den) < 1e-9 * (length(d) || 1)) return null;
  const s = dot(sub(centre, o), k) / den;
  const p = sub(add(o, scale(d, s)), centre);
  const r = normalize(sub(ref, scale(k, dot(ref, k))));
  const q = cross(k, r);
  return Math.atan2(dot(p, q), dot(p, r));
}

/** Wrap an angle to (-pi, pi]. */
export function wrapAngle(a: number): number {
  let x = a % (2 * Math.PI);
  if (x <= -Math.PI) x += 2 * Math.PI;
  if (x > Math.PI) x -= 2 * Math.PI;
  return x;
}

/** Snap an angle (radians) to steps of `stepDeg` degrees; `free` (Shift held) returns it unchanged. */
export function snapAngle(a: number, stepDeg = 15, free = false): number {
  if (free || !(stepDeg > 0)) return a;
  const step = (stepDeg * Math.PI) / 180;
  return Math.round(a / step) * step + 0;
}

/** Two unit axes in the plane square to `n`; the first is horizontal whenever the plane is not horizontal. */
export function planeAxes(n: readonly number[]): { u: V3; v: V3 } {
  const k = normalize(n);
  const ref: V3 = Math.abs(k[1]) > 0.99 ? [1, 0, 0] : [0, 1, 0];
  const u = normalize(cross(ref, k));
  return { u, v: cross(k, u) };
}

/** The axis direction a ring drag gives: `n0` turned about `axis` by `angle`, snapped back onto a world axis when within 1e-6. */
export function rotatePlaneAxis(n0: readonly number[], axis: readonly number[], angle: number): V3 {
  const n = normalize(rotateAbout(n0, axis, angle));
  for (let a = 0; a < 3; a++) {
    if (Math.abs(Math.abs(n[a]!) - 1) < 1e-6) {
      const e: V3 = [0, 0, 0];
      e[a] = Math.sign(n[a]!);
      return e;
    }
  }
  return n;
}

/**
 * Offset of a plane with axis `n` through `pivot`, measured from `centre` along `n` (the section plane's offset). A
 * ring drag keeps the plane through the point under the handle, so the plane pivots there.
 */
export function offsetThrough(centre: readonly number[], pivot: readonly number[], n: readonly number[]): number {
  return dot(sub(pivot, centre), normalize(n));
}

/**
 * The section plane settings for a world axis direction: a direction along +/- a world axis becomes that axis (with
 * offset and flip adjusted so the cut is the same); anything else is axis 'custom'.
 */
export function planeSettingsFor(n: readonly number[], offset: number, flip: boolean): { axis: 'x' | 'y' | 'z' | 'custom'; normal: V3; offset: number; flip: boolean } {
  const k = normalize(n);
  for (let a = 0; a < 3; a++) {
    if (Math.abs(Math.abs(k[a]!) - 1) < 1e-6) {
      const e: V3 = [0, 0, 0];
      e[a] = 1;
      const neg = k[a]! < 0;
      return { axis: (['x', 'y', 'z'] as const)[a]!, normal: e, offset: neg ? -offset + 0 : offset, flip: neg ? !flip : flip };
    }
  }
  return { axis: 'custom', normal: k, offset, flip };
}
