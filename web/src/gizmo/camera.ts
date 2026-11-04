// Camera moves of the gizmo: an eased turn from the current view to a target view (direction, up, target, distance).
// The orientation is interpolated as a quaternion (slerp), so a move into or out of a top view never swings through the
// pole, and a roll about the view axis is possible. Settings, duration, easing, view history and cancelling come from
// src/input/navigation.ts; the fit distance from src/cinematic/flyto.ts.

import { Box3, Matrix4, Quaternion, Sphere, Vector3 } from 'three';
import type { ViewerApp } from '../app';
import { computeFlyView } from '../cinematic/flyto';
import { easeInOutCubic } from '../cinematic/easing';
import { VIEW_MOVE_MS, cancelNavigationMoves, navSettings, orbitOffset, pushHistory } from '../input/navigation';
import { isUnrolled, turntableOffset } from './maths';
import type { V3, View } from './maths';

interface Move {
  q0: Quaternion;
  q1: Quaternion;
  t0: Vector3;
  t1: Vector3;
  d0: number;
  d1: number;
  view: View;
  start: number;
  ms: number;
  lastPos: Vector3;
  lastTarget: Vector3;
}

let move: Move | null = null;
const WORLD_UP = new Vector3(0, 1, 0);
const tmpM = new Matrix4();
const ORIGIN = new Vector3();

/** Camera orientation for a view: looks along -direction with screen up `up`. */
export function quatOf(v: View, out = new Quaternion()): Quaternion {
  tmpM.lookAt(new Vector3(...v.direction), ORIGIN, new Vector3(...v.up));
  return out.setFromRotationMatrix(tmpM);
}

/** The current view of the camera: direction from target to camera and the screen up. */
export function currentView(app: ViewerApp): View {
  const { camera, controls } = app.renderer;
  const d = camera.position.clone().sub(controls.target);
  if (d.lengthSq() < 1e-18) camera.getWorldDirection(d).negate();
  d.normalize();
  const up = new Vector3(0, 1, 0).applyQuaternion(camera.quaternion);
  return { direction: [d.x, d.y, d.z], up: [up.x, up.y, up.z] };
}

function cinematicCancel(): void {
  const w = window as unknown as { __cinematic?: { cancelFlight?(): void } };
  w.__cinematic?.cancelFlight?.();
}

/** Stop a running gizmo move (the camera stays where it is). */
export function cancelGizmoMove(): void {
  move = null;
}

export function isGizmoMoving(): boolean {
  return move !== null;
}

/** Bring the camera up vector back to world up when the view allows it (unrolled), keeping the picture. */
function settle(app: ViewerApp, v: View, target: Vector3, dist: number): void {
  const { camera, controls } = app.renderer;
  if (isUnrolled(v)) {
    camera.up.copy(WORLD_UP);
    const off = turntableOffset(v);
    camera.position.copy(target).addScaledVector(new Vector3(...off), dist);
  } else {
    camera.up.set(...v.up);
    camera.position.copy(target).addScaledVector(new Vector3(...v.direction), dist);
  }
  controls.target.copy(target);
  controls.update();
}

/**
 * Turn the camera to `view`. `target` and `distance` default to the current ones. Records the view history and
 * eases over the navigation move time when smooth moves are on (else jumps).
 */
export function turnTo(app: ViewerApp, view: View, target?: Vector3, distance?: number): void {
  const { camera, controls } = app.renderer;
  cancelNavigationMoves();
  cinematicCancel();
  pushHistory(app, 'gizmo');
  const t1 = (target ?? controls.target).clone();
  const d0 = Math.max(camera.position.distanceTo(controls.target), 1e-6);
  const d1 = distance ?? d0;
  if (!navSettings.smoothMoves) {
    move = null;
    settle(app, view, t1, d1);
    return;
  }
  camera.updateMatrixWorld();
  move = {
    q0: camera.quaternion.clone(),
    q1: quatOf(view),
    t0: controls.target.clone(),
    t1,
    d0,
    d1,
    view,
    start: Number.NaN,
    ms: VIEW_MOVE_MS,
    lastPos: camera.position.clone(),
    lastTarget: controls.target.clone(),
  };
}

/** The target and distance that frame `box` from `dir` (as the keyboard views do: margin 1.2). */
export function frameFrom(app: ViewerApp, box: Box3, dir: V3, margin = 1.2): { target: Vector3; distance: number } | null {
  if (box.isEmpty()) return null;
  const { camera, controls } = app.renderer;
  const fv = computeFlyView(
    box,
    { position: camera.position, target: controls.target, fovDeg: camera.fov, aspect: camera.aspect, minDistance: controls.minDistance, maxDistance: controls.maxDistance },
    { direction: new Vector3(...dir), margin },
  );
  const distance = fv.position.distanceTo(fv.target);
  const r = box.getBoundingSphere(new Sphere()).radius;
  if (camera.far < distance + r * 2) {
    camera.far = distance + r * 2;
    camera.updateProjectionMatrix();
  }
  return { target: fv.target, distance };
}

/** Per frame, before the render: advance the move. Returns true while it runs. */
export function gizmoCameraFrame(app: ViewerApp, now: number): boolean {
  const m = move;
  if (!m) return false;
  const { camera, controls } = app.renderer;
  // Lenient: the orbit damping may still add a little of the last drag. A pointer on the canvas cancels at once (plugin).
  const tol = 1e-2 * Math.max(1e-3, m.lastPos.distanceTo(m.lastTarget));
  if (camera.position.distanceTo(m.lastPos) > tol || controls.target.distanceTo(m.lastTarget) > tol) {
    move = null; // the user or another tool moved the camera: let go
    return false;
  }
  if (Number.isNaN(m.start)) m.start = now;
  const raw = m.ms <= 0 ? 1 : (now - m.start) / m.ms;
  if (raw >= 1) {
    move = null;
    settle(app, m.view, m.t1, m.d1);
    return true;
  }
  const k = easeInOutCubic(Math.max(0, raw));
  const q = m.q0.clone().slerp(m.q1, k);
  const back = new Vector3(0, 0, 1).applyQuaternion(q);
  const up = new Vector3(0, 1, 0).applyQuaternion(q);
  const target = m.t0.clone().lerp(m.t1, k);
  const dist = m.d0 * Math.pow(m.d1 / m.d0, k);
  camera.up.copy(up);
  camera.position.copy(target).addScaledVector(back, dist);
  controls.target.copy(target);
  controls.update();
  m.lastPos.copy(camera.position);
  m.lastTarget.copy(controls.target);
  return true;
}

/** Orbit by yaw (about world up) and pitch, as a drag on the cube does. Cancels a running move. */
export function orbitCamera(app: ViewerApp, yaw: number, pitch: number): void {
  const { camera, controls } = app.renderer;
  move = null;
  cancelNavigationMoves();
  const off = camera.position.clone().sub(controls.target);
  if (off.lengthSq() < 1e-12) return;
  if (Math.abs(camera.up.y - 1) > 1e-9) camera.up.copy(WORLD_UP); // a drag returns to the turntable
  camera.position.copy(controls.target).add(orbitOffset(off, yaw, pitch));
  controls.update();
}
