// Colour modes for the cloud: rgb, intensity, height ramp, classification palette, deviation bands.

export type ColourMode = 'rgb' | 'intensity' | 'height' | 'classification' | 'deviation';
export const COLOUR_MODES: ColourMode[] = ['rgb', 'intensity', 'height', 'classification', 'deviation'];

export type RGB = [number, number, number];

/** Deviation band colours (0..255). */
export const BAND_COLORS: RGB[] = [
  [64, 200, 96], // within tolerance: green
  [244, 180, 40], // up to twice the tolerance: amber
  [232, 64, 56], // beyond: red
  [140, 146, 154], // further than the maximum: grey, unrelated
];
export const BAND_LABELS = ['within tolerance', 'up to 2 x tolerance', 'beyond 2 x tolerance', 'unrelated (> max)'];
/** Colour of points without a deviation value. */
export const UNMEASURED: RGB = [96, 100, 108];

/** Band index 0..3 for a distance (m): <= tol, <= 2 tol, <= 5 tol, beyond. Infinity and NaN are unrelated. */
export function bandOf(d: number, tol: number): number {
  if (!(d <= 5 * tol)) return 3;
  return d <= tol ? 0 : d <= 2 * tol ? 1 : 2;
}

// Viridis, 9 stops.
const RAMP: RGB[] = [
  [68, 1, 84], [70, 50, 127], [54, 92, 141], [39, 127, 142], [31, 161, 135], [74, 193, 109], [159, 218, 58], [223, 227, 24], [253, 231, 37],
];
export function rampColor(t: number, out: RGB = [0, 0, 0]): RGB {
  const x = (t < 0 ? 0 : t > 1 ? 1 : t) * (RAMP.length - 1);
  const i = Math.min(RAMP.length - 2, Math.floor(x));
  const f = x - i;
  const a = RAMP[i]!, b = RAMP[i + 1]!;
  out[0] = a[0] + (b[0] - a[0]) * f;
  out[1] = a[1] + (b[1] - a[1]) * f;
  out[2] = a[2] + (b[2] - a[2]) * f;
  return out;
}

/** ASPRS standard classes (LAS 1.2 to 1.4). */
export const CLASS_NAMES: Record<number, string> = {
  0: 'never classified', 1: 'unassigned', 2: 'ground', 3: 'low vegetation', 4: 'medium vegetation', 5: 'high vegetation', 6: 'building',
  7: 'low point (noise)', 8: 'model key', 9: 'water', 10: 'rail', 11: 'road surface', 12: 'overlap', 13: 'wire guard', 14: 'wire conductor',
  15: 'transmission tower', 16: 'wire connector', 17: 'bridge deck', 18: 'high noise', 19: 'overhead structure', 20: 'ignored ground',
  21: 'snow', 22: 'temporal exclusion',
};
const CLASS_COLORS: Record<number, RGB> = {
  0: [150, 150, 150], 1: [190, 190, 190], 2: [160, 120, 80], 3: [150, 210, 100], 4: [70, 180, 70], 5: [20, 130, 40], 6: [230, 120, 50],
  7: [255, 0, 255], 8: [255, 255, 255], 9: [60, 130, 230], 10: [110, 80, 60], 11: [90, 90, 100], 12: [200, 200, 120], 13: [255, 220, 0],
  14: [255, 170, 0], 15: [180, 60, 60], 16: [230, 100, 100], 17: [120, 160, 200], 18: [200, 0, 200], 19: [60, 190, 220], 20: [130, 100, 70],
  21: [240, 245, 255], 22: [100, 100, 160],
};
export function classColor(c: number): RGB {
  return CLASS_COLORS[c] ?? [(c * 53) % 200 + 40, (c * 97) % 200 + 40, (c * 29) % 200 + 40];
}

export interface ColourInputs {
  count: number;
  colors?: Uint8Array;
  intensity?: Float32Array;
  intensityRange?: [number, number] | null;
  classification?: Uint8Array;
  /** Height of each point (any constant offset), e.g. the mapped Y. */
  heights?: Float32Array;
  /** Distances (m) per point; Infinity or NaN for unrelated, undefined entries for points not measured: use `measured`. */
  deviation?: Float32Array | null;
  /** 1 for points that have a deviation value. Absent: all measured when `deviation` is given. */
  measured?: Uint8Array | null;
  tolerance: number;
}

/** RGB bytes (3 per point) for a colour mode. Modes whose data is missing fall back to height, then to grey. */
export function buildColours(mode: ColourMode, inp: ColourInputs): Uint8Array {
  const n = inp.count;
  const out = new Uint8Array(n * 3);
  const c: RGB = [0, 0, 0];
  const heightRamp = (): void => {
    const h = inp.heights;
    if (!h) { out.fill(180); return; }
    let lo = Infinity, hi = -Infinity;
    for (let i = 0; i < n; i++) { const v = h[i]!; if (v < lo) lo = v; if (v > hi) hi = v; }
    const span = hi - lo || 1;
    for (let i = 0; i < n; i++) {
      rampColor((h[i]! - lo) / span, c);
      out[i * 3] = c[0]; out[i * 3 + 1] = c[1]; out[i * 3 + 2] = c[2];
    }
  };
  if (mode === 'rgb') {
    if (inp.colors) out.set(inp.colors.subarray(0, n * 3));
    else heightRamp();
  } else if (mode === 'intensity') {
    const it = inp.intensity;
    if (!it) { heightRamp(); return out; }
    const [lo, hi] = inp.intensityRange ?? [0, 1];
    const span = hi - lo || 1;
    for (let i = 0; i < n; i++) {
      const g = Math.round(255 * Math.min(1, Math.max(0, (it[i]! - lo) / span)));
      out[i * 3] = g; out[i * 3 + 1] = g; out[i * 3 + 2] = g;
    }
  } else if (mode === 'height') heightRamp();
  else if (mode === 'classification') {
    const cl = inp.classification;
    if (!cl) { heightRamp(); return out; }
    for (let i = 0; i < n; i++) {
      const k = classColor(cl[i]!);
      out[i * 3] = k[0]; out[i * 3 + 1] = k[1]; out[i * 3 + 2] = k[2];
    }
  } else {
    const d = inp.deviation;
    for (let i = 0; i < n; i++) {
      const k = d && (!inp.measured || inp.measured[i]) ? BAND_COLORS[bandOf(d[i]!, inp.tolerance)]! : UNMEASURED;
      out[i * 3] = k[0]; out[i * 3 + 1] = k[1]; out[i * 3 + 2] = k[2];
    }
  }
  return out;
}
