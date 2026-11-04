// Staggered reveal: occluders start fading in order of distance from the focus, so transparency
// ripples outward. Pure: works on plain arrays.

import { Box3, Vector3 } from 'three';
import { clamp01 } from './easing';

export const MAX_REVEAL_DELAY_MS = 600;

/** Distance from a point to a box (0 inside). */
export function pointBoxDistance(p: Vector3, box: Box3): number {
  const dx = Math.max(box.min.x - p.x, 0, p.x - box.max.x);
  const dy = Math.max(box.min.y - p.y, 0, p.y - box.max.y);
  const dz = Math.max(box.min.z - p.z, 0, p.z - box.max.z);
  return Math.sqrt(dx * dx + dy * dy + dz * dz);
}

export interface RevealItem {
  id: number;
  box: Box3;
}

/**
 * Delay in ms before each item may start fading: linear in the distance from `centre` to the item's
 * box, 0 at distance 0 and `maxDelayMs` at `reach` or beyond. `reach` is the focus bounds radius plus
 * the buffer radius.
 */
export function revealDelays(items: readonly RevealItem[], centre: Vector3, reach: number, maxDelayMs = MAX_REVEAL_DELAY_MS): Map<number, number> {
  const out = new Map<number, number>();
  for (const it of items) {
    const d = pointBoxDistance(centre, it.box);
    out.set(it.id, reach > 1e-9 ? maxDelayMs * clamp01(d / reach) : 0);
  }
  return out;
}

/**
 * Holds elements at their previous alpha until their start time. Used after the controller's tick
 * and before the render: `apply` writes the held alpha back into the render state, so the controller
 * (which smooths from `state.alpha`) sees no progress for that element until the delay is over.
 */
export class StaggerReveal {
  private readonly startAt = new Map<number, number>();
  private readonly held = new Map<number, number>();

  get size(): number {
    return this.startAt.size;
  }

  has(id: number): boolean {
    return this.startAt.has(id);
  }

  startTime(id: number): number | undefined {
    return this.startAt.get(id);
  }

  clear(): void {
    this.startAt.clear();
    this.held.clear();
  }

  /** Start a reveal at `now` (ms). Hidden elements (alpha < 0) and zero delays are not held. */
  begin(now: number, delays: ReadonlyMap<number, number>, alpha: ArrayLike<number>): void {
    this.clear();
    for (const [id, d] of delays) {
      const a = alpha[id];
      if (d <= 0 || a === undefined || a < 0) continue;
      this.startAt.set(id, now + d);
      this.held.set(id, a);
    }
  }

  /** Write held alphas for elements still inside their delay window; forget the others. Returns true if any was written. */
  apply(now: number, alpha: Float32Array): boolean {
    let wrote = false;
    for (const [id, t] of this.startAt) {
      if (now >= t) {
        this.startAt.delete(id);
        this.held.delete(id);
      } else {
        alpha[id] = this.held.get(id)!;
        wrote = true;
      }
    }
    return wrote;
  }
}
