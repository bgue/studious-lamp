// Pure maths of the WebXR mode (no three.js, no DOM, no WebXR types), so the tests can check it without a headset.
//
// The viewer keeps the model where it is and moves the viewer. The XR camera sits in a "rig" (an Object3D in the scene):
//   world = rigPosition + Ry(yaw) * (scale * local)
// where `local` is a position in the XR reference space (metres as the headset measures them: the head pose, the controller
// poses, the AR hit-test result). `scale` is world metres per physical metre: 1 is real scale; 50 makes the model look 50
// times smaller, because the viewer is then 50 times larger than the model (tabletop 1:50). The yaw turns the viewer about
// the vertical axis. The rig never pitches or rolls: the floor stays level.

export type V3 = [number, number, number];
/** Quaternion x, y, z, w (the WebXR and three.js order). */
export type Q4 = [number, number, number, number];

export interface Rig {
  /** World position of the rig origin. */
  position: V3;
  /** Rotation about +Y, radians, counter-clockwise seen from above (three.js convention). */
  yaw: number;
  /** World metres per physical metre. */
  scale: number;
}

export const IDENTITY_RIG: Rig = { position: [0, 0, 0], yaw: 0, scale: 1 };

// ---------------------------------------------------------------- vectors and quaternions

export const add = (a: V3, b: V3): V3 => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
export const sub = (a: V3, b: V3): V3 => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
export const mul = (a: V3, k: number): V3 => [a[0] * k, a[1] * k, a[2] * k];
export const dot = (a: V3, b: V3): number => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
export const len = (a: V3): number => Math.hypot(a[0], a[1], a[2]);
export function norm(a: V3): V3 {
  const l = len(a);
  return l > 1e-12 ? [a[0] / l, a[1] / l, a[2] / l] : [0, 0, 0];
}

/** Rotate a vector by a unit quaternion. */
export function quatRotate(q: Q4, v: V3): V3 {
  const [x, y, z, w] = q;
  // t = 2 * cross(q.xyz, v); v' = v + w * t + cross(q.xyz, t)
  const tx = 2 * (y * v[2] - z * v[1]);
  const ty = 2 * (z * v[0] - x * v[2]);
  const tz = 2 * (x * v[1] - y * v[0]);
  return [v[0] + w * tx + (y * tz - z * ty), v[1] + w * ty + (z * tx - x * tz), v[2] + w * tz + (x * ty - y * tx)];
}

/** Rotation about +Y by `yaw`. */
export function yawQuat(yaw: number): Q4 {
  return [0, Math.sin(yaw / 2), 0, Math.cos(yaw / 2)];
}

/** Rotate about +Y (counter-clockwise from above). */
export function rotateY(v: V3, yaw: number): V3 {
  const c = Math.cos(yaw);
  const s = Math.sin(yaw);
  return [c * v[0] + s * v[2], v[1], -s * v[0] + c * v[2]];
}

/** The yaw that turns the forward direction -Z to the horizontal part of `dir`. 0 when `dir` is vertical. */
export function yawOfDirection(dir: V3): number {
  if (Math.hypot(dir[0], dir[2]) < 1e-9) return 0;
  return Math.atan2(-dir[0], -dir[2]);
}

/** Wrap an angle to (-pi, pi]. */
export function wrapAngle(a: number): number {
  const t = Math.PI * 2;
  let r = a % t;
  if (r > Math.PI) r -= t;
  else if (r <= -Math.PI) r += t;
  return r;
}

// ---------------------------------------------------------------- the rig

/** A point in the XR reference space as a world point. */
export function rigPoint(rig: Rig, local: V3): V3 {
  return add(rig.position, rotateY(mul(local, rig.scale), rig.yaw));
}

/** A direction in the XR reference space as a world direction (turned, not scaled). */
export function rigDirection(rig: Rig, local: V3): V3 {
  return rotateY(local, rig.yaw);
}

/** The world point as a point in the XR reference space (inverse of rigPoint). */
export function rigLocalPoint(rig: Rig, world: V3): V3 {
  return mul(rotateY(sub(world, rig.position), -rig.yaw), 1 / rig.scale);
}

/** Column-major 4 x 4 matrix of the rig (translate * rotateY * scale), for tests and for matrix consumers. */
export function rigMatrix(rig: Rig): number[] {
  const c = Math.cos(rig.yaw) * rig.scale;
  const s = Math.sin(rig.yaw) * rig.scale;
  return [c, 0, -s, 0, 0, rig.scale, 0, 0, s, 0, c, 0, rig.position[0], rig.position[1], rig.position[2], 1];
}

/**
 * Start of a VR session: the orbit camera becomes the head. With the 'local' reference space the head starts at `headLocal`
 * (about the origin), so the rig is placed such that the head lands exactly on `camPos` and looks along the horizontal part
 * of `camDir`. Real scale unless `scale` is given.
 */
export function rigFromOrbitCamera(camPos: V3, camDir: V3, headLocal: V3 = [0, 0, 0], scale = 1): Rig {
  const yaw = yawOfDirection(camDir);
  const r: Rig = { position: [0, 0, 0], yaw, scale };
  r.position = sub(camPos, rigPoint(r, headLocal));
  return r;
}

/** World position, world forward direction and world orientation of the head from its pose in the XR reference space. */
export function poseToCamera(rig: Rig, headPos: V3, headQuat: Q4): { position: V3; forward: V3; up: V3; quaternion: Q4 } {
  const position = rigPoint(rig, headPos);
  const forward = rigDirection(rig, quatRotate(headQuat, [0, 0, -1]));
  const up = rigDirection(rig, quatRotate(headQuat, [0, 1, 0]));
  const q = yawQuat(rig.yaw);
  const [x, y, z, w] = headQuat;
  // world orientation = yaw * head
  const quaternion: Q4 = [q[3] * x + q[0] * w + q[1] * z - q[2] * y, q[3] * y - q[0] * z + q[1] * w + q[2] * x, q[3] * z + q[0] * y - q[1] * x + q[2] * w, q[3] * w - q[0] * x - q[1] * y - q[2] * z];
  return { position, forward, up, quaternion };
}

/** A controller (or hand) target ray, given by its pose in the XR reference space, as a world ray. The ray runs along its local -Z. */
export function controllerRayToWorld(rig: Rig, pos: V3, quat: Q4): { origin: V3; direction: V3 } {
  return { origin: rigPoint(rig, pos), direction: norm(rigDirection(rig, quatRotate(quat, [0, 0, -1]))) };
}

// ---------------------------------------------------------------- locomotion

export const SNAP_TURN = (30 * Math.PI) / 180;
/** The stick must pass this to trigger a turn, and fall below the re-arm value before the next one. */
export const SNAP_ON = 0.7;
export const SNAP_REARM = 0.3;
export const STICK_DEADZONE = 0.15;
/** Walking speed in physical metres per second at full stick. */
export const MOVE_SPEED = 2.0;

/** Turn the rig by `angle` about the vertical axis through the head, so the head does not move in the world. */
export function turnAboutHead(rig: Rig, headLocal: V3, angle: number): Rig {
  const head = rigPoint(rig, headLocal);
  const next: Rig = { position: rig.position, yaw: wrapAngle(rig.yaw + angle), scale: rig.scale };
  next.position = sub(head, rigPoint({ ...next, position: [0, 0, 0] }, headLocal));
  return next;
}

export interface SnapState {
  armed: boolean;
}

/**
 * One step of the snap turn on a stick axis: returns the turn to make (-1, 0 or +1; +1 = stick right) and updates the
 * state. A turn needs |x| above SNAP_ON while armed; the stick re-arms below SNAP_REARM. Right turns the view clockwise
 * seen from above, which is a negative yaw.
 */
export function snapTurnStep(state: SnapState, x: number): -1 | 0 | 1 {
  if (Math.abs(x) < SNAP_REARM) {
    state.armed = true;
    return 0;
  }
  if (state.armed && Math.abs(x) > SNAP_ON) {
    state.armed = false;
    return x > 0 ? 1 : -1;
  }
  return 0;
}

/** Apply a snap turn step (+1 right, -1 left) to the rig. */
export function snapTurn(rig: Rig, headLocal: V3, step: -1 | 0 | 1): Rig {
  return step === 0 ? rig : turnAboutHead(rig, headLocal, -step * SNAP_TURN);
}

/**
 * Walk: the stick moves the rig in the horizontal plane along the head's forward (stick up) and right (stick right)
 * directions. `forward` is the head's world forward direction. The speed is in physical metres per second, so a tabletop
 * rig (scale 50) covers 50 world metres per physical metre like everything else.
 */
export function moveStep(rig: Rig, forward: V3, stickX: number, stickY: number, dtSeconds: number, speed = MOVE_SPEED): Rig {
  const dead = (v: number): number => (Math.abs(v) < STICK_DEADZONE ? 0 : v);
  const sx = dead(stickX);
  const sy = dead(stickY);
  if (sx === 0 && sy === 0) return rig;
  const f = norm([forward[0], 0, forward[2]]);
  if (len(f) === 0) return rig;
  const right: V3 = [-f[2], 0, f[0]];
  // stick up is negative y on a gamepad
  const d = add(mul(f, -sy), mul(right, sx));
  const step = mul(d, speed * rig.scale * Math.max(dtSeconds, 0));
  return { position: add(rig.position, step), yaw: rig.yaw, scale: rig.scale };
}

// ---------------------------------------------------------------- augmented reality

export const AR_SCALES = ['1:1', 'tabletop 1:50'] as const;
export type ArScale = (typeof AR_SCALES)[number];

/** World metres per physical metre of an AR preset. */
export function arScaleFactor(s: ArScale): number {
  return s === 'tabletop 1:50' ? 50 : 1;
}

/**
 * Place the model: the world point `anchor` (for example the centre of the model's footprint at floor height) appears at the
 * physical point `hit` (the hit-test result on the real floor or table, in the XR reference space), at the given scale
 * and turned by `yaw`. Returns the rig: for scale 50 the model is 50 times smaller than real life.
 */
export function arPlacement(hit: V3, anchor: V3, scale: number, yaw = 0): Rig {
  const r: Rig = { position: [0, 0, 0], yaw, scale };
  r.position = sub(anchor, rigPoint(r, hit));
  return r;
}

/** Apparent size of a model dimension (metres) in the room for an AR preset. */
export function apparentSize(modelMetres: number, scale: ArScale): number {
  return modelMetres / arScaleFactor(scale);
}

/** Where to look for the model before the first placement: `distance` physical metres ahead of the head, on the floor `eyeHeight` below. */
export function defaultArHit(headLocal: V3, headForward: V3, distance = 1.2, eyeHeight = 1.4): V3 {
  const f = norm([headForward[0], 0, headForward[2]]);
  const ahead: V3 = len(f) > 0 ? f : [0, 0, -1];
  return [headLocal[0] + ahead[0] * distance, headLocal[1] - eyeHeight, headLocal[2] + ahead[2] * distance];
}

/** Where the model stands before the first tap when the device reports no surface: a tabletop (about 0.8 m below the eyes) for a small model, the floor otherwise. */
export function defaultArSurface(scale: number): { distance: number; eyeHeight: number } {
  return scale > 1 ? { distance: 0.9, eyeHeight: 0.8 } : { distance: 1.2, eyeHeight: 1.4 };
}

/** Camera clip distances in physical metres for a model of the given world radius at the given rig scale. */
export function clipDistances(modelRadiusWorld: number, scale: number): { near: number; far: number } {
  const physRadius = modelRadiusWorld / Math.max(scale, 1e-6);
  return { near: 0.05, far: Math.max(50, physRadius * 6) };
}
