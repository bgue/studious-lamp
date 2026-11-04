// Camera fly-to: where to put the camera to frame a box, and the eased flight between two views.
// Pure (three math only): no renderer, no DOM.

import { Box3, Sphere, Vector3 } from 'three';
import { easeInOutCubic } from './easing';

export const DEFAULT_FLY_MS = 900;
/** Distance multiplier on top of the exact sphere fit. */
export const DEFAULT_FLY_MARGIN = 1.35;
const DEFAULT_DIRECTION = new Vector3(0.7, 0.55, 0.85).normalize();

export interface FlyView {
  position: Vector3;
  target: Vector3;
}

export interface FlyCamera extends FlyView {
  fovDeg: number;
  aspect: number;
  /** OrbitControls distance limits; the result is clamped into them. */
  minDistance?: number;
  maxDistance?: number;
}

export interface FlyOptions {
  durationMs?: number;
  margin?: number;
  /** Unit direction from the focus to the camera. Overrides the keep-direction rule. */
  direction?: Vector3;
  ease?: (t: number) => number;
}

/** Distance at which a sphere of `radius` fits the (smaller) field of view, times `margin`. */
export function fitDistance(radius: number, fovDeg: number, aspect: number, margin = DEFAULT_FLY_MARGIN): number {
  const fov = (fovDeg * Math.PI) / 180;
  const fit = Math.min(fov, 2 * Math.atan(Math.tan(fov / 2) * aspect));
  return (Math.max(radius, 1e-4) / Math.sin(fit / 2)) * margin;
}

/** True when `point` lies behind the camera plane (the camera looks from `position` towards `target`). */
export function isBehindCamera(position: Vector3, target: Vector3, point: Vector3): boolean {
  const fwd = new Vector3().subVectors(target, position);
  const to = new Vector3().subVectors(point, position);
  return fwd.dot(to) < 0;
}

/**
 * The view that frames `box`. Target = box centre. Distance = sphere fit with margin, clamped to the
 * control limits. Direction: keep the current view direction (camera sits on the opposite side of the
 * target, looking the same way) unless the focus is behind the camera; then approach from the side the
 * camera is already on, so it never has to swing through 180 degrees.
 */
export function computeFlyView(box: Box3, cam: FlyCamera, opts: FlyOptions = {}): FlyView {
  const sphere = box.getBoundingSphere(new Sphere());
  const centre = sphere.center.clone();
  let dist = fitDistance(sphere.radius, cam.fovDeg, cam.aspect, opts.margin ?? DEFAULT_FLY_MARGIN);
  if (cam.minDistance !== undefined) dist = Math.max(dist, cam.minDistance * 1.01);
  if (cam.maxDistance !== undefined && cam.maxDistance > 0) dist = Math.min(dist, cam.maxDistance * 0.99);

  const dir = new Vector3();
  if (opts.direction && opts.direction.lengthSq() > 1e-12) {
    dir.copy(opts.direction).normalize();
  } else {
    const look = new Vector3().subVectors(cam.target, cam.position);
    if (look.lengthSq() > 1e-12 && !isBehindCamera(cam.position, cam.target, centre)) {
      dir.copy(look).normalize().negate(); // focus -> camera
    } else {
      dir.subVectors(cam.position, centre);
      if (dir.lengthSq() > 1e-12) dir.normalize();
      else dir.copy(DEFAULT_DIRECTION);
    }
  }
  return { position: centre.clone().addScaledVector(dir, dist), target: centre };
}

/** An eased interpolation between two views, driven by an external clock. */
export class Flight {
  readonly from: FlyView;
  readonly to: FlyView;
  readonly durationMs: number;
  private readonly ease: (t: number) => number;
  private t0 = Number.NaN;

  constructor(from: FlyView, to: FlyView, durationMs = DEFAULT_FLY_MS, ease: (t: number) => number = easeInOutCubic) {
    this.from = { position: from.position.clone(), target: from.target.clone() };
    this.to = { position: to.position.clone(), target: to.target.clone() };
    this.durationMs = Math.max(0, durationMs);
    this.ease = ease;
  }

  /** Write the view at clock time `now` (ms) into `out`. Returns true when the flight is complete. The first call starts the clock. */
  sample(now: number, out: FlyView): boolean {
    if (Number.isNaN(this.t0)) this.t0 = now;
    const raw = this.durationMs <= 0 ? 1 : (now - this.t0) / this.durationMs;
    if (raw >= 1) {
      out.position.copy(this.to.position);
      out.target.copy(this.to.target);
      return true;
    }
    const k = this.ease(Math.max(0, raw));
    out.position.lerpVectors(this.from.position, this.to.position, k);
    out.target.lerpVectors(this.from.target, this.to.target, k);
    return false;
  }
}
