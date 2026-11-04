// Pure easing helpers for the cinematic plugin.

export function clamp01(t: number): number {
  return t < 0 ? 0 : t > 1 ? 1 : t;
}

export function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

/** Hermite smooth-step: 3t^2 - 2t^3, zero slope at both ends. */
export function smoothStep(t: number): number {
  const c = clamp01(t);
  return c * c * (3 - 2 * c);
}

/** Cubic ease in-out: 4t^3 for the first half, mirrored for the second. */
export function easeInOutCubic(t: number): number {
  const c = clamp01(t);
  return c < 0.5 ? 4 * c * c * c : 1 - Math.pow(-2 * c + 2, 3) / 2;
}
