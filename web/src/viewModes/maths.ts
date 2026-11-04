// Pure maths of the two view modes (behind-only and partial peelback). The shaders
// (render/viewModeGlsl.ts) mirror these functions; the tests exercise them directly.
//
// Conventions: the viewer is Y up. A "plane" is { n, d } with n unit length; a point p is on the FRONT
// (camera) side when dot(n, p) < d and BEHIND it when dot(n, p) >= d.

export type Vec3 = readonly [number, number, number];
/** [minx, miny, minz, maxx, maxy, maxz] */
export type Box6 = readonly [number, number, number, number, number, number];

export interface Plane {
  nx: number;
  ny: number;
  nz: number;
  d: number;
}

// ---------------------------------------------------------------- behind-only

/** Smallest dot(n, p) over the box (the corner nearest to a viewer looking along n). Exact for an AABB. */
export function minDotBox(n: Vec3, b: Box6): number {
  return Math.min(n[0] * b[0], n[0] * b[3]) + Math.min(n[1] * b[1], n[1] * b[4]) + Math.min(n[2] * b[2], n[2] * b[5]);
}

/**
 * Plane perpendicular to the view direction `forward` (camera to scene) through the focus's nearest point,
 * pushed `offset` metres toward the camera (negative: into the focus). Context in front of it is the part
 * that obstructs the view. Null without focus boxes.
 */
export function planeFromCamera(forward: Vec3, boxes: Iterable<Box6>, offset: number): Plane | null {
  const len = Math.hypot(forward[0], forward[1], forward[2]);
  if (!(len > 0)) return null;
  const n: Vec3 = [forward[0] / len, forward[1] / len, forward[2] / len];
  let t0 = Infinity;
  for (const b of boxes) t0 = Math.min(t0, minDotBox(n, b));
  if (!Number.isFinite(t0)) return null;
  return { nx: n[0], ny: n[1], nz: n[2], d: t0 - offset };
}

/** Plan cut: horizontal plane at the top of the focus plus `offset`; everything above it is the front side. */
export function planeHorizontal(boxes: Iterable<Box6>, offset: number): Plane | null {
  let top = -Infinity;
  for (const b of boxes) top = Math.max(top, b[4]);
  if (!Number.isFinite(top)) return null;
  // n = (0, -1, 0): dot(n, p) < d  <=>  -y < -(top + offset)  <=>  y > top + offset
  return { nx: 0, ny: -1, nz: 0, d: -(top + offset) };
}

/** > 0 on the front (camera) side, < 0 behind. Metres. */
export function planeSide(pl: Plane, p: Vec3): number {
  return pl.d - (pl.nx * p[0] + pl.ny * p[1] + pl.nz * p[2]);
}

export type FrontTreatment = 'cut' | 'ghost' | 'cut + cap';
export const FRONT_TREATMENTS: readonly FrontTreatment[] = ['cut', 'ghost', 'cut + cap'];
export type PlaneOrientation = 'camera' | 'locked' | 'horizontal';
export const PLANE_ORIENTATIONS: readonly PlaneOrientation[] = ['camera', 'locked', 'horizontal'];
export type ApplyTo = 'all context' | 'occluders only';
export const APPLY_TO: readonly ApplyTo[] = ['all context', 'occluders only'];

/** What happens to a context fragment, given its side of the plane (mirrors vmEval in the shader). */
export interface BehindFragment {
  /** 0: removed; 1: drawn as normal geometry. */
  cover: number;
  /** Effective base alpha. */
  alpha: number;
  /** Back face revealed by a cut, painted with the cap colour. */
  cap: boolean;
}

export function behindFragment(
  side: number,
  alpha: number,
  back: boolean,
  o: { treatment: FrontTreatment; frontAlpha: number; keepXray: boolean },
): BehindFragment {
  if (side > 0) {
    if (o.treatment === 'ghost') return { cover: 1, alpha: o.frontAlpha, cap: false };
    return { cover: 0, alpha, cap: false };
  }
  return { cover: 1, alpha: o.keepXray ? alpha : 1, cap: o.treatment === 'cut + cap' && back };
}

// ---------------------------------------------------------------- peelback

export interface PeelMaths {
  /** Window radius at the focus depth, metres. */
  r0: number;
  /** Extra radius per metre between the fragment and the focus (towards the viewer). */
  slope: number;
  /** Soft edge width, metres. */
  feather: number;
  /** A fragment is "in front" when its view depth is smaller than the focus depth by more than this (m). */
  eps: number;
}

/** Coverage above this counts as untouched (not cut, not in the feather). */
export const VM_FULL = 0.995;
/** Default depth tolerance (m): context less than this in front of the focus (a host wall around a window) is not cut. */
export const PEEL_EPS = 0.2;
/**
 * The depth tolerance grows with the screen distance (metres at the focus depth) from the nearest focus pixel: a wall
 * seen obliquely is nearer by up to about tan(tilt) times that distance on the side of the focus nearer the camera,
 * and must not be mistaken for an obstruction. 1.0 covers a surface tilted up to 45 degrees away from the screen plane.
 */
export const PEEL_TILT = 1.0;
/** Back faces up to this much deeper than the cut front face are assumed to belong to the same solid (m). */
export const PEEL_CAP_SLACK = 0.5;
export const PEEL_MAX_ELLIPSES = 16;
/** First jump of the flood, in texels of the half resolution mask (covers radii up to 2 * this - 1). */
export const JFA_START = 256;

/** r(z) = r0 + slope * (zFocus - z): the window widens toward the viewer. Zero slope term behind the focus. */
export function peelRadius(r0: number, slope: number, zFocus: number, z: number): number {
  return r0 + slope * Math.max(zFocus - z, 0);
}

/** Pixels per metre at view depth `depth` for a camera with vertical field of view `fovY` (radians) and `resY` pixel rows. */
export function pixelsPerMetre(depth: number, fovY: number, resY: number): number {
  return resY / (2 * Math.tan(fovY / 2) * Math.max(depth, 1e-6));
}

export function metresToPixels(m: number, depth: number, fovY: number, resY: number): number {
  return m * pixelsPerMetre(depth, fovY, resY);
}

export function pixelsToMetres(px: number, depth: number, fovY: number, resY: number): number {
  return px / pixelsPerMetre(depth, fovY, resY);
}

const smooth = (a: number, b: number, x: number): number => {
  if (b <= a) return x >= b ? 1 : 0;
  const t = Math.min(1, Math.max(0, (x - a) / (b - a)));
  return t * t * (3 - 2 * t);
};

/** 0 inside the window (lateral distance `distM` < R), rising to 1 over `feather` metres outside it. */
export function peelCoverage(distM: number, R: number, feather: number): number {
  return smooth(R, R + Math.max(feather, 0), distM);
}

/** Width of the rim colour band beyond the radius, metres. */
export function peelRimWidth(feather: number): number {
  return Math.max(feather, 0) + 0.03;
}

/** 1 right at the window edge, fading to 0 over peelRimWidth. 0 inside the window. */
export function peelRim(distM: number, R: number, feather: number): number {
  if (distM < R) return 0;
  return 1 - smooth(R, R + peelRimWidth(feather), distM);
}

export interface PeelFragment {
  /** 0 = cut, 1 = untouched. */
  cover: number;
  rim: number;
  /** Back face in the neighbourhood of the window that the cut revealed. */
  cap: boolean;
  /** The fragment lies in front of the nearest focus pixel (the cut applies to it). */
  inFront: boolean;
}

/**
 * The per-fragment test. `distPx`: screen distance (pixels) to the nearest focus pixel, `zFocus` its view depth (the metres
 * of r0, slope and feather are converted to pixels with the projection at that depth),
 * `z` the fragment's view depth, `fovY` and `resY` those of the render target.
 */
export function peelFragment(distPx: number, zFocus: number, z: number, back: boolean, p: PeelMaths, fovY: number, resY: number): PeelFragment {
  const distM = pixelsToMetres(distPx, zFocus, fovY, resY); // screen distance in metres at the focus depth (r0 is defined there)
  const R = peelRadius(p.r0, p.slope, zFocus, z);
  const inFront = z < zFocus - p.eps - PEEL_TILT * distM;
  const cover = inFront ? peelCoverage(distM, R, p.feather) : 1;
  const rim = inFront ? peelRim(distM, R, p.feather) : 0;
  let cap = false;
  if (back && cover > VM_FULL) cap = distM < peelRadius(p.r0, p.slope, zFocus, z - PEEL_CAP_SLACK);
  return { cover, rim, cap, inFront };
}

/** Ease-out (cubic) growth of the radius from 0 to 1 over `durationMs`. */
export function peelAnimScale(elapsedMs: number, durationMs = 500): number {
  if (durationMs <= 0) return 1;
  const t = Math.min(1, Math.max(0, elapsedMs / durationMs));
  return 1 - Math.pow(1 - t, 3);
}

// ---------------------------------------------------------------- jump flooding

/** Jump sizes of one flood: start, start/2, ..., 1, then 1 again (JFA+1 cuts the error of the plain flood). */
export function jfaSteps(start: number = JFA_START): number[] {
  const out: number[] = [];
  let s = Math.max(1, Math.floor(start));
  for (; s >= 1; s = Math.floor(s / 2)) out.push(s);
  out.push(1);
  return out;
}

/** Smallest power of two >= n, at least 1. */
export function nextPow2(n: number): number {
  let p = 1;
  while (p < n) p *= 2;
  return p;
}

/**
 * CPU reference of the shader flood. `mask[y*w+x] != 0` marks seeds. Returns, per pixel, the index of the nearest
 * seed found (y*w+x) or -1.
 */
export function jfaNearest(mask: ArrayLike<number>, w: number, h: number, steps: readonly number[] = jfaSteps(nextPow2(Math.max(w, h)) / 2)): Int32Array {
  let cur = new Int32Array(w * h).fill(-1);
  for (let i = 0; i < w * h; i++) if (mask[i]) cur[i] = i;
  let next = new Int32Array(w * h);
  for (const s of steps) {
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) {
        let best = -1;
        let bd = Infinity;
        for (let dy = -1; dy <= 1; dy++) {
          for (let dx = -1; dx <= 1; dx++) {
            const qx = x + dx * s;
            const qy = y + dy * s;
            if (qx < 0 || qy < 0 || qx >= w || qy >= h) continue;
            const c = cur[qy * w + qx]!;
            if (c < 0) continue;
            const cx = c % w;
            const cy = (c - cx) / w;
            const d = (cx - x) * (cx - x) + (cy - y) * (cy - y);
            if (d < bd) {
              bd = d;
              best = c;
            }
          }
        }
        next[y * w + x] = best;
      }
    }
    const t = cur;
    cur = next;
    next = t;
  }
  return cur;
}

/** Brute force nearest seed, for tests. */
export function bruteNearest(mask: ArrayLike<number>, w: number, h: number): Int32Array {
  const seeds: number[] = [];
  for (let i = 0; i < w * h; i++) if (mask[i]) seeds.push(i);
  const out = new Int32Array(w * h).fill(-1);
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      let bd = Infinity;
      for (const s of seeds) {
        const sx = s % w;
        const sy = (s - sx) / w;
        const d = (sx - x) * (sx - x) + (sy - y) * (sy - y);
        if (d < bd) {
          bd = d;
          out[y * w + x] = s;
        }
      }
    }
  }
  return out;
}

// ---------------------------------------------------------------- CPU fallback and picking

/** A focus element's screen footprint: ellipse centre and semi-axes in pixels (bottom-left origin), and the depth. */
export interface ScreenEllipse {
  cx: number;
  cy: number;
  ax: number;
  ay: number;
  z: number;
}

/**
 * Project a box with the column-major `viewProj` and `view` matrices (three's `elements`) to a screen ellipse that
 * circumscribes its bounding rectangle. A box crossing the camera plane covers the whole screen. Null when it is
 * wholly behind the camera.
 */
export function boxScreenEllipse(viewProj: ArrayLike<number>, view: ArrayLike<number>, b: Box6, w: number, h: number): ScreenEllipse | null {
  let minx = Infinity;
  let miny = Infinity;
  let maxx = -Infinity;
  let maxy = -Infinity;
  let zmin = Infinity;
  let zmax = -Infinity;
  let behind = 0;
  for (let i = 0; i < 8; i++) {
    const x = i & 1 ? b[3] : b[0];
    const y = i & 2 ? b[4] : b[1];
    const z = i & 4 ? b[5] : b[2];
    const cw = viewProj[3]! * x + viewProj[7]! * y + viewProj[11]! * z + viewProj[15]!;
    const vz = -(view[2]! * x + view[6]! * y + view[10]! * z + view[14]!);
    zmin = Math.min(zmin, vz);
    zmax = Math.max(zmax, vz);
    if (cw <= 1e-4) {
      behind++;
      continue;
    }
    const cx = viewProj[0]! * x + viewProj[4]! * y + viewProj[8]! * z + viewProj[12]!;
    const cy = viewProj[1]! * x + viewProj[5]! * y + viewProj[9]! * z + viewProj[13]!;
    const px = (cx / cw * 0.5 + 0.5) * w;
    const py = (cy / cw * 0.5 + 0.5) * h;
    minx = Math.min(minx, px);
    maxx = Math.max(maxx, px);
    miny = Math.min(miny, py);
    maxy = Math.max(maxy, py);
  }
  if (behind === 8) return null;
  const zc = Math.min(zmax, Math.max(zmin, 0.0001, (zmin + zmax) / 2));
  if (behind > 0) return { cx: w / 2, cy: h / 2, ax: w, ay: h, z: Math.max(zc, 1e-3) };
  return {
    cx: (minx + maxx) / 2,
    cy: (miny + maxy) / 2,
    ax: Math.max((maxx - minx) / 2 * Math.SQRT2, 1),
    ay: Math.max((maxy - miny) / 2 * Math.SQRT2, 1),
    z: Math.max(zc, 1e-3),
  };
}

/** Approximate distance in pixels from (x, y) to the ellipse (0 inside). Same formula as the shader. */
export function ellipseDistancePx(e: ScreenEllipse, x: number, y: number): number {
  const k = Math.hypot((x - e.cx) / e.ax, (y - e.cy) / e.ay);
  return Math.max(k - 1, 0) * Math.min(e.ax, e.ay);
}

/** Nearest ellipse to a pixel: its distance (pixels) and depth, or null for an empty list. */
export function nearestEllipse(list: readonly ScreenEllipse[], x: number, y: number): { distPx: number; z: number } | null {
  let best: { distPx: number; z: number } | null = null;
  for (const e of list) {
    const d = ellipseDistancePx(e, x, y);
    if (!best || d < best.distPx) best = { distPx: d, z: e.z };
  }
  return best;
}

/**
 * CPU version of the cut test for the picker: does the window remove a surface point at pixel (x, y), view depth `z`?
 * Approximates the focus by its projected bounds, so it can differ from the rendered window by a few pixels.
 */
export function peelCutsPoint(list: readonly ScreenEllipse[], x: number, y: number, z: number, p: PeelMaths, fovY: number, resY: number): boolean {
  const n = nearestEllipse(list, x, y);
  if (!n) return false;
  return peelFragment(n.distPx, n.z, z, false, p, fovY, resY).cover < 0.5;
}
