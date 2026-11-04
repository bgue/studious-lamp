// Immediate camera fit to a box, with a hook so another plugin (cinematic) can animate instead.

import { Box3, Sphere, Vector3 } from 'three';
import type { PerspectiveCamera } from 'three';
import type { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';

/**
 * Move the camera along its current view direction so the box fills the view, and aim the orbit target at the
 * box centre. Immediate (no animation). `padding` > 1 leaves a margin.
 */
export function fitBox(camera: PerspectiveCamera, controls: OrbitControls, box: Box3, padding = 1.2): void {
  if (box.isEmpty()) return;
  const sphere = box.getBoundingSphere(new Sphere());
  const r = Math.max(sphere.radius, 0.05);
  const fov = (camera.fov * Math.PI) / 180;
  const fit = Math.min(fov, 2 * Math.atan(Math.tan(fov / 2) * camera.aspect));
  const dist = (r / Math.sin(fit / 2)) * padding;
  const dir = camera.position.clone().sub(controls.target);
  if (dir.lengthSq() < 1e-12) dir.set(0.7, 0.55, 0.85);
  dir.normalize();
  controls.target.copy(sphere.center);
  camera.position.copy(sphere.center).addScaledVector(dir, dist);
  // Keep the far plane beyond the fitted box; never shrink what frameAll() chose.
  if (camera.far < dist + r * 2) {
    camera.far = dist + r * 2;
    camera.updateProjectionMatrix();
  }
  if (controls.minDistance > dist) controls.minDistance = dist * 0.5;
  controls.update();
}

export type FrameEventDetail = { box: Box3 };

/**
 * Ask for the camera to frame `box`. Dispatches a cancelable `xray:frame` event on window first; when a listener
 * calls preventDefault() (the cinematic plugin does, and animates itself) nothing else happens. Otherwise the
 * camera is fitted immediately. Returns true when the immediate fit ran.
 */
export function requestFrame(camera: PerspectiveCamera, controls: OrbitControls, box: Box3): boolean {
  const ev = new CustomEvent<FrameEventDetail>('xray:frame', { detail: { box }, cancelable: true });
  const proceed = window.dispatchEvent(ev);
  if (!proceed) return false;
  fitBox(camera, controls, box);
  return true;
}

export function boxFromTuple(b: readonly [number, number, number, number, number, number]): Box3 {
  return new Box3(new Vector3(b[0], b[1], b[2]), new Vector3(b[3], b[4], b[5]));
}
