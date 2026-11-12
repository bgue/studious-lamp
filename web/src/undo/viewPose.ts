// Camera snapshots for the undo stack: pure maths, no three.js. A pose is what a person calls "the view": where the camera
// is, what it looks at, which way is up, the field of view (the orthographic approximation is a 2 degree field of view)
// and whether that approximation is on.

export type V3 = [number, number, number];

export interface ViewPose {
  position: V3;
  target: V3;
  up: V3;
  fov: number;
  ortho: boolean;
}

const sub = (a: V3, b: V3): V3 => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const len = (a: V3): number => Math.hypot(a[0], a[1], a[2]);

/** Same view, within a tolerance that scales with the distance to the target. */
export function viewPoseEqual(a: ViewPose, b: ViewPose, rel = 1e-4): boolean {
  if (a.ortho !== b.ortho) return false;
  const scale = Math.max(1e-6, len(sub(a.position, a.target)), len(sub(b.position, b.target)));
  const tol = scale * rel;
  for (let i = 0; i < 3; i++) {
    if (Math.abs(a.position[i]! - b.position[i]!) > tol) return false;
    if (Math.abs(a.target[i]! - b.target[i]!) > tol) return false;
    if (Math.abs(a.up[i]! - b.up[i]!) > 1e-4) return false;
  }
  return Math.abs(a.fov - b.fov) <= 1e-4;
}

/** What kind of move turned view `a` into view `b`: "zoom", "pan", "orbit", "projection" or "view" (a mix, or a jump). */
export function describeViewChange(a: ViewPose, b: ViewPose): string {
  if (a.ortho !== b.ortho) return 'projection';
  const oa = sub(a.position, a.target);
  const ob = sub(b.position, b.target);
  const da = len(oa);
  const db = len(ob);
  if (da < 1e-9 || db < 1e-9) return 'view';
  const cos = Math.max(-1, Math.min(1, (oa[0] * ob[0] + oa[1] * ob[1] + oa[2] * ob[2]) / (da * db)));
  const angle = (Math.acos(cos) * 180) / Math.PI;
  const shift = len(sub(a.target, b.target)) / Math.max(da, db);
  const ratio = Math.abs(Math.log(db / da));
  if (angle < 0.5 && shift < 0.005 && ratio < 0.02) {
    // Up or roll only.
    return 'view';
  }
  if (angle >= 0.5 && shift < 0.02 && ratio < 0.03) return 'orbit';
  if (angle < 0.5 && shift < 0.02 && ratio >= 0.02) return 'zoom';
  if (angle < 0.5 && shift >= 0.005 && ratio < 0.03) return 'pan';
  return 'view';
}

/** Linear mix of two poses (the up vector is mixed and normalised). t in 0..1. */
export function mixViewPose(a: ViewPose, b: ViewPose, t: number): ViewPose {
  const m = (p: V3, q: V3): V3 => [p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t, p[2] + (q[2] - p[2]) * t];
  const up = m(a.up, b.up);
  const l = len(up) || 1;
  return {
    position: m(a.position, b.position),
    target: m(a.target, b.target),
    up: [up[0] / l, up[1] / l, up[2] / l],
    fov: a.fov + (b.fov - a.fov) * t,
    ortho: t < 1 ? a.ortho : b.ortho,
  };
}

/** Ease in and out. */
export const easeInOut = (t: number): number => (t < 0.5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2);
