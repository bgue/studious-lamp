// Walk mode and navigation style: the pure parts (maths, gating, storage). No DOM, no app: runs in vitest.
// The glue that moves the camera is in input/navigation.ts, the chip and the pointer handling in plugins/walk.ts.
//
//   Navigation style  'bim' (default): wheel zooms to the cursor, middle drag pans, Shift + middle drag orbits about the point
//                     under the cursor, w a s d q e do nothing until Walk mode is on.
//                     'game': the old mapping: w a s d q e fly the camera and its target at all times, middle drag zooms.
//   Walk mode         a per-viewer state (never in params, share links, saved views, presets or packed pages): the keys move
//                     the eye on the horizontal plane, the drag looks around from the eye.

import { Vector3 } from 'three';

export type NavStyle = 'bim' | 'game';
export const DEFAULT_NAV_STYLE: NavStyle = 'bim';

export function parseNavStyle(v: unknown): NavStyle | null {
  return v === 'bim' || v === 'game' ? v : null;
}

/** Walk speed factors: Shift is 3 times faster, Ctrl is 0.25 times (both held: 0.75). */
export const WALK_FAST = 3;
export const WALK_SLOW = 0.25;
/** The eye never looks further than this above or below the horizon, radians (85 degrees). */
export const WALK_PITCH_LIMIT = (85 * Math.PI) / 180;

/** The w a s d q e fly keys act in Game style at all times, in BIM style only while Walk mode is on. */
export function flyKeysEnabled(style: NavStyle, walking: boolean): boolean {
  return style === 'game' || walking;
}

export function walkSpeedFactor(m: { ctrl?: boolean; shift?: boolean }): number {
  return (m.shift ? WALK_FAST : 1) * (m.ctrl ? WALK_SLOW : 1);
}

const UP = new Vector3(0, 1, 0);

/**
 * The view direction projected on the horizontal plane (Y up), as a unit vector. When the view is (nearly) vertical the
 * projection is degenerate: `fallback` (a direction such as the screen up vector of the camera) is projected instead; with no
 * usable fallback the result is -Z.
 */
export function horizontalForward(look: Vector3, fallback?: Vector3): Vector3 {
  const out = new Vector3(look.x, 0, look.z);
  if (out.lengthSq() < 1e-8 && fallback) out.set(fallback.x, 0, fallback.z);
  if (out.lengthSq() < 1e-12) return new Vector3(0, 0, -1);
  return out.normalize();
}

/** The horizontal unit vector to the right of a horizontal forward vector (Y up). */
export function walkRight(forward: Vector3): Vector3 {
  return new Vector3().crossVectors(forward, UP).normalize();
}

/**
 * The eye after a step: `fwd` along the horizontal forward, `right` along its right-hand side, `up` along world Y (metres, any
 * sign). The height only changes by `up`, whatever the pitch of the view.
 */
export function walkMove(eye: Vector3, look: Vector3, fwd: number, right: number, up: number, fallback?: Vector3): Vector3 {
  const f = horizontalForward(look, fallback);
  const r = walkRight(f);
  return eye.clone().addScaledVector(f, fwd).addScaledVector(r, right).addScaledVector(UP, up);
}

export function clampPitch(pitch: number, limit = WALK_PITCH_LIMIT): number {
  return Math.max(-limit, Math.min(limit, pitch));
}

/** Yaw (0 looks along -Z, positive turns left, seen from above) and pitch (positive looks up) of a view direction. */
export function yawPitchOf(look: Vector3): { yaw: number; pitch: number } {
  const l = look.clone().normalize();
  return { yaw: Math.atan2(-l.x, -l.z), pitch: Math.asin(Math.max(-1, Math.min(1, l.y))) };
}

export function lookFromYawPitch(yaw: number, pitch: number): Vector3 {
  const c = Math.cos(pitch);
  return new Vector3(-Math.sin(yaw) * c, Math.sin(pitch), -Math.cos(yaw) * c);
}

/**
 * Turn a view direction about the eye: `dyaw` radians left (positive) or right about world Y, `dpitch` radians up (positive);
 * the pitch is clamped to +-`limit`. A vertical view (no yaw of its own) takes its yaw from `fallback`.
 */
export function turnLook(look: Vector3, dyaw: number, dpitch: number, limit = WALK_PITCH_LIMIT, fallback?: Vector3): Vector3 {
  const { pitch } = yawPitchOf(look);
  const h = horizontalForward(look, fallback);
  const yaw = Math.atan2(-h.x, -h.z) + dyaw;
  return lookFromYawPitch(yaw, clampPitch(pitch + dpitch, limit));
}

/** The orbit target for an eye that looks along `look`: a point `dist` in front of it. */
export function eyeTarget(eye: Vector3, look: Vector3, dist: number): Vector3 {
  return eye.clone().addScaledVector(look.clone().normalize(), dist);
}

/** Radians per pixel of a look drag, so the point under the pointer follows it (the vertical field of view over the height). */
export function lookRadiansPerPixel(fovDeg: number, heightPx: number): number {
  return ((fovDeg * Math.PI) / 180) / Math.max(1, heightPx);
}

/** The distance of the orbit target kept in front of the eye in Walk mode: the orbit distance, within the zoom limits. */
export function walkTargetDistance(current: number, minDistance: number, maxDistance: number, modelDiagonal: number): number {
  const lo = Math.max(minDistance * 1.01, 0.05);
  const hi = Math.max(lo, Math.min(maxDistance > 0 && Number.isFinite(maxDistance) ? maxDistance * 0.99 : Infinity, modelDiagonal * 0.25));
  return Math.max(lo, Math.min(hi, current));
}

/** How far along the view axis a hit point lies (the depth the orbit pivot moves to). */
export function pivotDepth(camera: Vector3, viewDir: Vector3, hit: Vector3): number {
  return new Vector3().subVectors(hit, camera).dot(viewDir.clone().normalize());
}

/**
 * The new orbit target for "orbit about what you grab": the point on the current view axis at the depth of the hit, so the view
 * does not jump (the camera keeps its pose, only the pivot moves). Clamped into the orbit distance limits (a pivot nearer than the
 * minimum distance would pull the camera back). Null when the hit is behind the camera.
 */
export function retargetAtDepth(camera: Vector3, viewDir: Vector3, depth: number, minDistance = 0, maxDistance = Infinity): Vector3 | null {
  if (!(depth > 1e-9)) return null;
  let d = depth;
  if (minDistance > 0) d = Math.max(d, minDistance * 1.001);
  if (maxDistance > 0 && Number.isFinite(maxDistance)) d = Math.min(d, maxDistance * 0.999);
  return camera.clone().addScaledVector(viewDir.clone().normalize(), d);
}

/** Two clicks that count as a double click: close in time and in place. */
export function isDoubleClick(prev: { t: number; x: number; y: number } | null, now: { t: number; x: number; y: number }, ms = 400, px = 6): boolean {
  return !!prev && now.t - prev.t <= ms && Math.hypot(now.x - prev.x, now.y - prev.y) <= px;
}
