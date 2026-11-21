// World point to CSS pixels of a frame for a three.js camera. Null behind the camera and well outside the frame.

import { Matrix4, Vector3 } from 'three';
import type { Camera } from 'three';
import type { V3 } from '../score';

const tmp = new Vector3();
const view = new Matrix4();

/** The projection of `camera` onto a `width` x `height` frame. The camera's matrices must be current (updateMatrixWorld). */
export function makeProjector(camera: Camera, width: number, height: number, slack = 40): (p: V3) => { x: number; y: number } | null {
  view.copy(camera.matrixWorldInverse);
  const proj = camera.projectionMatrix.clone();
  const m = view.clone();
  return (p) => {
    tmp.set(p[0], p[1], p[2]).applyMatrix4(m);
    if (tmp.z >= -1e-6) return null; // behind the camera (it looks down -z)
    tmp.applyMatrix4(proj);
    const x = (tmp.x * 0.5 + 0.5) * width;
    const y = (-tmp.y * 0.5 + 0.5) * height;
    if (!Number.isFinite(x) || !Number.isFinite(y) || x < -slack || x > width + slack || y < -slack || y > height + slack) return null;
    return { x, y };
  };
}
