// Clearance colouring: the minimum surface distance from each context element to the focus set, in three bands.
//   clash  distance <= 0 (touching or overlapping)         red
//   tight  0 < distance < tight                            amber
//   ok     tight <= distance <= max                        cool ramp (teal near, blue far)
//   far    distance > max                                  unchanged
// Pure over a small geometry interface (bounds distance + exact surface distance), so it is tested with boxes.

export interface ClearanceSettings {
  /** metres */
  tight: number;
  /** metres */
  max: number;
}

export const DEFAULT_CLEARANCE: ClearanceSettings = { tight: 0.05, max: 0.5 };

export type Band = 'clash' | 'tight' | 'ok' | 'far';
export type Rgb = readonly [number, number, number];

export const CLASH_COLOUR: Rgb = [0.93, 0.2, 0.2];
export const TIGHT_COLOUR: Rgb = [0.98, 0.7, 0.1];
const OK_NEAR: Rgb = [0.2, 0.82, 0.78];
const OK_FAR: Rgb = [0.3, 0.45, 0.92];
/** Distances at or below this count as touching. */
export const TOUCH_EPS = 1e-6;

export function bandOf(d: number, s: ClearanceSettings): Band {
  if (!(d > TOUCH_EPS)) return 'clash'; // also negative and NaN-free zero
  if (d < s.tight) return 'tight';
  if (d <= s.max) return 'ok';
  return 'far';
}

/** Colour of a distance, or null when it is beyond the range (left unchanged). */
export function clearanceColour(d: number, s: ClearanceSettings): Rgb | null {
  switch (bandOf(d, s)) {
    case 'clash': return CLASH_COLOUR;
    case 'tight': return TIGHT_COLOUR;
    case 'far': return null;
    case 'ok': {
      const span = Math.max(1e-9, s.max - s.tight);
      const t = Math.min(1, Math.max(0, (d - s.tight) / span));
      return [OK_NEAR[0] + (OK_FAR[0] - OK_NEAR[0]) * t, OK_NEAR[1] + (OK_FAR[1] - OK_NEAR[1]) * t, OK_NEAR[2] + (OK_FAR[2] - OK_NEAR[2]) * t];
    }
  }
}

/** Gradient stops for the legend: [offset 0..1, css colour]. */
export function legendStops(): Array<[number, string]> {
  const css = (c: Rgb): string => `rgb(${Math.round(c[0] * 255)},${Math.round(c[1] * 255)},${Math.round(c[2] * 255)})`;
  return [[0, css(OK_NEAR)], [1, css(OK_FAR)]];
}

export interface ClearanceGeometry {
  /** Lower bound: distance between the two bounds boxes (0 when they overlap). */
  boundsDistance(a: number, b: number): number;
  /** Exact distance; any value > maxDistance when farther than that (GeometryProvider semantics). */
  surfaceDistance(a: number, b: number, maxDistance: number): number;
}

export interface ClearanceResult {
  /** Context elements within the range, with their minimum distance to the focus set. */
  distances: Map<number, number>;
  counts: Record<Band, number>;
  /** Elements that needed a mesh distance query (passed the bounds prefilter). */
  queried: number;
}

/**
 * Minimum distance from each context element to the focus set. Only context elements whose bounds are within `max` of
 * some focus element get mesh queries; focus elements are tried nearest-bounds first and the search stops as soon as the
 * bounds distance cannot beat the best exact distance.
 */
export function computeClearance(focus: readonly number[], context: readonly number[], geo: ClearanceGeometry, s: ClearanceSettings): ClearanceResult {
  const distances = new Map<number, number>();
  const counts: Record<Band, number> = { clash: 0, tight: 0, ok: 0, far: 0 };
  let queried = 0;
  const near: Array<[number, number]> = [];
  for (const c of context) {
    near.length = 0;
    for (const f of focus) {
      if (f === c) continue;
      const bd = geo.boundsDistance(f, c);
      if (bd <= s.max) near.push([bd, f]);
    }
    if (near.length === 0) {
      counts.far++;
      continue;
    }
    queried++;
    near.sort((a, b) => a[0] - b[0]);
    let best = Infinity;
    for (const [bd, f] of near) {
      if (bd >= best) break;
      const d = geo.surfaceDistance(f, c, Math.min(s.max, best));
      if (d < best) best = d;
      if (best <= TOUCH_EPS) break;
    }
    const band = bandOf(best, s);
    counts[band]++;
    if (band !== 'far') distances.set(c, best);
  }
  return { distances, counts, queried };
}
