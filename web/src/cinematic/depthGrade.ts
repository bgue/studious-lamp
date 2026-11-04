// Depth-graded ghosting: tint ghosts cooler and darker the further they sit in front of the focus.
// The shader (render/shaders.ts, PASS_GHOST) evaluates the same mapping per fragment.

import { Vector3 } from 'three';

export interface DepthGradeSettings {
  strength: number;
}

/**
 * Distance of `point` in front of `focusCentre`, measured along the view axis (camera -> focus centre).
 * Positive: the point is nearer the camera than the focus centre. Behind it: negative.
 */
export function alongViewDistance(camera: Vector3, focusCentre: Vector3, point: Vector3): number {
  const axis = new Vector3().subVectors(focusCentre, camera);
  if (axis.lengthSq() < 1e-12) return 0;
  axis.normalize();
  return new Vector3().subVectors(focusCentre, point).dot(axis);
}

/**
 * Mix factor toward the cool dark tone: `strength * (1 - exp(-d / radius))` for d > 0, else 0.
 * No effect when radius <= 0 (no focus) or strength <= 0. Saturates at `strength`.
 */
export function depthGradeMix(d: number, radius: number, strength: number): number {
  if (!(radius > 0) || !(strength > 0) || !(d > 0)) return 0;
  return strength * (1 - Math.exp(-d / radius));
}
