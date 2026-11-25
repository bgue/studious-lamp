// Walk mode and navigation style: the pure parts (maths, gating, storage). No DOM, no app: runs in vitest.
// The glue that moves the camera is in input/navigation.ts, the chip and the pointer handling in plugins/walk.ts.
//
//   Navigation style  'bim' (default): wheel zooms to the cursor, middle drag pans, Shift + middle drag orbits about the point
//                     under the cursor, w a s d q e do nothing until Walk mode is on.
//                     'game': the old mapping: w a s d q e fly the camera and its target at all times, middle drag zooms.
//   Walk mode         a per-viewer state (never in params, share links, saved views, presets or packed pages): the keys move
//                     the eye on the horizontal plane, the drag looks around from the eye.

import { Vector3 } from 'three';
import { FLAG_FOCUS, FLAG_HIDDEN } from '../types';

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

// ---------------------------------------------------------------------------- drop in, storey jump, collision (pure parts)

/** Default eye height above the floor, metres (the model units are metres, see SceneModel.units). */
export const DEFAULT_EYE_HEIGHT = 1.6;
export const EYE_HEIGHT_MIN = 0.5;
export const EYE_HEIGHT_MAX = 3;
/** A surface counts as a floor to stand on when its normal points up this much. */
export const FLOOR_NORMAL_Y = 0.7;
/** Collision: the eye stops this far (metres) from a wall. */
export const WALK_CLEARANCE = 0.3;

export function parseEyeHeight(v: unknown): number | null {
  return typeof v === 'number' && Number.isFinite(v) && v >= EYE_HEIGHT_MIN && v <= EYE_HEIGHT_MAX ? v : null;
}

export interface FloorLevel {
  id: number;
  name: string;
  /** Floor height in viewer coordinates. */
  floorY: number;
}

/** The highest floor at or below `y` (plus `tol`); null when `y` is below every floor. `floors` is sorted lowest first. */
export function floorAtOrBelow(floors: readonly FloorLevel[], y: number, tol = 0.05): FloorLevel | null {
  let best: FloorLevel | null = null;
  for (const f of floors) if (f.floorY <= y + tol) best = f;
  return best;
}

/**
 * Where the eye goes for a double click on a surface. A surface that faces up (normal.y > 0.7) is stood on; for a wall or a
 * ceiling the floor below the hit point is used: the storey elevation at or below it, else `groundY` (the result of a downward
 * ray from the hit; null when it found nothing), else the hit height itself. Same x and z as the hit.
 */
export function standingSpot(
  hit: { x: number; y: number; z: number },
  normal: { x: number; y: number; z: number },
  floors: readonly FloorLevel[],
  eyeHeight: number,
  groundY: number | null = null,
): { eye: Vector3; floorY: number; onSurface: boolean } {
  let floorY: number;
  let onSurface = false;
  if (normal.y > FLOOR_NORMAL_Y) {
    floorY = hit.y;
    onSurface = true;
  } else {
    const f = floorAtOrBelow(floors, hit.y);
    floorY = f ? f.floorY : groundY !== null ? groundY : hit.y;
  }
  return { eye: new Vector3(hit.x, floorY + eyeHeight, hit.z), floorY, onSurface };
}

/**
 * The storey a PageUp / PageDown in Walk mode goes to, and the eye height there. The current storey is the highest floor at or
 * below the feet-ish height (eye minus 0.3 m); the eye keeps its height above it. Null at the top or bottom of the stack, or
 * without storeys.
 */
export function stepWalkStorey(
  floors: readonly FloorLevel[],
  eyeY: number,
  dir: 1 | -1,
  eyeHeight = DEFAULT_EYE_HEIGHT,
): { level: FloorLevel; eyeY: number } | null {
  if (floors.length === 0) return null;
  const cur = floorAtOrBelow(floors, eyeY - 0.3, 0);
  const offset = cur ? eyeY - cur.floorY : eyeHeight;
  let next: FloorLevel | null = null;
  if (cur === null) next = dir > 0 ? floors[0]! : null;
  else {
    const i = floors.indexOf(cur);
    next = floors[i + dir] ?? null;
  }
  return next ? { level: next, eyeY: next.floorY + offset } : null;
}

/** The move with the part that goes into a wall removed. `normal` is the wall normal on the horizontal plane (any length, not zero). */
export function slideAlongWall(move: Vector3, normal: Vector3): Vector3 {
  const n = new Vector3(normal.x, 0, normal.z);
  if (n.lengthSq() < 1e-12) return move.clone();
  n.normalize();
  const into = move.dot(n);
  const out = move.clone();
  if (into < 0) out.addScaledVector(n, -into);
  return out;
}

/** An element blocks the walker unless it is a door, hidden, or ghosted (x-ray, alpha below 0.3 and not in focus). */
export function blocksWalk(ifcClass: string, flags: number, alpha: number): boolean {
  if (ifcClass.toLowerCase() === 'ifcdoor') return false;
  if ((flags & FLAG_HIDDEN) !== 0 || alpha < 0) return false;
  if ((flags & FLAG_FOCUS) === 0 && alpha < 0.3) return false;
  return true;
}

export interface WallHit {
  distance: number;
  /** Surface normal, any direction (it is flipped toward the walker here). */
  normal: { x: number; y: number; z: number };
}

/** Heights above the floor of the collision rays: knee, waist and eye. Offsets from the eye, given the eye height. */
export function collisionRayOffsets(eyeHeight: number): number[] {
  return [-(eyeHeight - 0.4), -eyeHeight * 0.45, 0];
}

/**
 * Limit a horizontal move by walls. `cast` shoots a ray (origin, horizontal unit direction, max distance) at what blocks and
 * returns the nearest hit. One ray per height (3), only when there is a move. The move stops `clearance` short of the nearest
 * wall and the rest slides along it. The slide is checked too (3 more rays at most): in a corner the slide along one wall
 * would otherwise run through the other, so a blocked slide stops at its own clearance and does not slide again.
 * Surfaces that face up or down (stairs, ramps, slabs) are not walls.
 */
export function collideMove(
  eye: Vector3,
  move: Vector3,
  cast: (origin: Vector3, dir: Vector3, maxDist: number) => WallHit | null,
  eyeHeight = DEFAULT_EYE_HEIGHT,
  clearance = WALK_CLEARANCE,
): Vector3 {
  const flat = new Vector3(move.x, 0, move.z);
  const first = limitByWall(eye, flat, cast, eyeHeight, clearance);
  let out = first.go;
  if (first.slide) {
    // The slide starts where the straight part ends; it may only stop, never slide a second time.
    const from = new Vector3(eye.x + first.go.x, eye.y, eye.z + first.go.z);
    const second = limitByWall(from, first.slide, cast, eyeHeight, clearance);
    out = first.go.clone().add(second.go);
  }
  const r = new Vector3(out.x, move.y, out.z);
  return r;
}

/** One pass: the part of a flat move that is free (`go`) and, when a wall stops it, the rest projected along that wall. */
function limitByWall(
  eye: Vector3,
  flat: Vector3,
  cast: (origin: Vector3, dir: Vector3, maxDist: number) => WallHit | null,
  eyeHeight: number,
  clearance: number,
): { go: Vector3; slide: Vector3 | null } {
  const len = flat.length();
  if (len < 1e-9) return { go: flat.clone(), slide: null };
  const dir = flat.clone().divideScalar(len);
  let best: { allowed: number; normal: Vector3 } | null = null;
  for (const off of collisionRayOffsets(eyeHeight)) {
    const hit = cast(new Vector3(eye.x, eye.y + off, eye.z), dir, len + clearance);
    if (!hit) continue;
    const n = new Vector3(hit.normal.x, hit.normal.y, hit.normal.z);
    if (Math.abs(n.y) > FLOOR_NORMAL_Y) continue;
    if (n.dot(dir) > 0) n.negate();
    // The clearance is kept square to the wall, so a slanting approach stops a little earlier along the ray.
    const allowed = hit.distance - clearance / Math.max(0.2, -n.dot(dir));
    if (allowed >= len) continue;
    if (!best || allowed < best.allowed) best = { allowed, normal: n };
  }
  if (!best) return { go: flat.clone(), slide: null };
  const a = Math.max(0, best.allowed);
  const rest = flat.clone().multiplyScalar(1 - a / len);
  const slide = slideAlongWall(rest, best.normal);
  return { go: flat.clone().multiplyScalar(a / len), slide: slide.lengthSq() > 1e-12 ? slide : null };
}
