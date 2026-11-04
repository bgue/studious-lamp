// Pure maths of the imaging styles (radiograph, MRI): material density, attenuation curve, palettes,
// MRI slab and scan timing. No three.js, no DOM. The GLSL in render/imagingGlsl.ts is generated from the
// constants here and mirrors these functions; tests/imaging-*.test.ts check the maths.

export type Vec3 = [number, number, number];
export type Box6 = readonly [number, number, number, number, number, number];

export const STYLES = ['standard', 'radiograph', 'mri'] as const;
export type ImagingStyle = (typeof STYLES)[number];
export const PALETTES = ['classic', 'negative', 'fluoro'] as const;
export type ImagingPalette = (typeof PALETTES)[number];
export const MRI_AXES = ['camera', 'x', 'y', 'z'] as const;
export type MriAxis = (typeof MRI_AXES)[number];

// ---------------------------------------------------------------- density

export const DEFAULT_DENSITY = 0.7;

/** Keyword table, first match wins (lower-case substrings; the German names of the fzk-haus model are included). */
const DENSITY_KEYWORDS: ReadonlyArray<readonly [readonly string[], number]> = [
  [['insulation', 'dämm', 'daemm', 'rockwool', 'foam'], 0.05],
  [['gypsum', 'plaster', 'gips', 'putz', 'drywall'], 0.3],
  [['glass', 'glas', 'glazing'], 0.6],
  [['concrete', 'beton', 'cement'], 1.0],
  [['steel', 'stahl', 'metal', 'galvan', 'iron', 'copper'], 3.0],
  [['timber', 'wood', 'holz', 'spruce', 'mdf'], 0.4],
  [['masonry', 'brick', 'ziegel', 'mauer', 'stone', 'sand-lime', 'kalksand'], 0.8],
];

/** Relative X-ray density of a material name (concrete 1.0, steel 3.0, wood 0.4, masonry 0.8, gypsum 0.3, glass 0.6, insulation 0.05, else 0.7). */
export function densityForMaterial(name: string | undefined | null): number {
  if (!name) return DEFAULT_DENSITY;
  const s = name.toLowerCase();
  for (const [keys, d] of DENSITY_KEYWORDS) for (const k of keys) if (s.includes(k)) return d;
  return DEFAULT_DENSITY;
}

// ---------------------------------------------------------------- attenuation, contrast

/** Soft tissue: opacity per unit (density * thickness). Bone: the same for the focus channel. */
export const K_TISSUE = 0.9;
export const K_BONE = 1.4;
/** The focus ("bone") thickness channel accumulates thickness * this, whatever the material: bone is dense. */
export const BONE_DENSITY = 8;
/** Contrast pivots around this intensity. */
export const CONTRAST_PIVOT = 0.35;
/** MRI: how bright the faint tissue outside the slab gets at most (scale of the attenuation). */
export const MRI_FAINT = 0.3;
export const MRI_FAINT_BONE = 0.45;
/** Weights of the two glow scales (small, wide). */
export const GLOW_A = 0.7;
export const GLOW_B = 0.6;

/** Beer-Lambert: intensity = 1 - exp(-exposure * k * T). Negative T (open meshes) is clamped to 0. */
export function attenuate(thickness: number, exposure: number, k: number = K_TISSUE): number {
  const t = thickness > 0 ? thickness : 0;
  return 1 - Math.exp(-Math.max(exposure, 0) * k * t);
}

/** Linear contrast about CONTRAST_PIVOT, clamped to 0..1. contrast 1 is the identity. */
export function contrastCurve(i: number, contrast: number): number {
  const v = (i - CONTRAST_PIVOT) * contrast + CONTRAST_PIVOT;
  return v < 0 ? 0 : v > 1 ? 1 : v;
}

// ---------------------------------------------------------------- automatic exposure

/** The 90th percentile of the non-zero context thickness is mapped to this tissue intensity. */
export const AUTO_TARGET = 0.8;
export const AUTO_PERCENTILE = 0.9;
/** Thickness samples (density * metres, already in the target's units) below this count as empty. */
export const AUTO_EMPTY = 1e-3;
/** Fewer non-empty samples than this: no measurement (the exposure stays where it was). */
export const AUTO_MIN_SAMPLES = 24;
/** Limits of the automatic factor. */
export const AUTO_LIMITS: readonly [number, number] = [0.002, 40];

/** The p-quantile (0..1) of the samples above `empty`, and how many there are. Null when none. */
export function nonZeroPercentile(samples: ArrayLike<number>, p: number, empty = AUTO_EMPTY): { value: number; count: number } | null {
  const v: number[] = [];
  for (let i = 0; i < samples.length; i++) {
    const x = samples[i]!;
    if (x > empty && Number.isFinite(x)) v.push(x);
  }
  if (v.length === 0) return null;
  v.sort((a, b) => a - b);
  const q = Math.min(1, Math.max(0, p)) * (v.length - 1);
  const lo = Math.floor(q);
  const hi = Math.min(v.length - 1, lo + 1);
  return { value: v[lo]! + (v[hi]! - v[lo]!) * (q - lo), count: v.length };
}

/**
 * The factor E for which `attenuate(T90, E, k)` equals `target`, with T90 the 90th percentile of the non-empty context
 * thickness samples: E = -ln(1 - target) / (k * T90). The exposure slider multiplies this factor. Null when there are
 * too few non-empty samples (an empty or nearly empty frame).
 */
export function autoExposureFor(samples: ArrayLike<number>, target = AUTO_TARGET, percentile = AUTO_PERCENTILE, k = K_TISSUE): number | null {
  const q = nonZeroPercentile(samples, percentile);
  if (!q || q.count < AUTO_MIN_SAMPLES) return null;
  const e = -Math.log(1 - Math.min(Math.max(target, 0.01), 0.99)) / (k * q.value);
  return Math.min(AUTO_LIMITS[1], Math.max(AUTO_LIMITS[0], e));
}

/**
 * One smoothing step in the log domain (a factor of 2 up or down feels the same): `rate` is the share of the gap closed
 * per measurement. The first measurement (prev null) is taken as it is. A gap under 2 % is ignored, so the picture does
 * not breathe while the camera is still.
 */
export function smoothExposure(prev: number | null, next: number, rate = 0.4): number {
  if (prev === null || !(prev > 0)) return next;
  const d = Math.log(next / prev);
  if (Math.abs(d) < 0.02) return prev;
  return prev * Math.exp(d * Math.min(1, Math.max(0, rate)));
}

// ---------------------------------------------------------------- palettes

export interface PaletteColours {
  /** The colour where nothing is: the background. */
  bg: Vec3;
  /** Tissue at full intensity. */
  tissue: Vec3;
  /** Bone (the focus) at full intensity. */
  bone: Vec3;
  /** Colour of the bone glow at full strength. */
  glow: Vec3;
  /** Faint tissue edges. */
  edge: Vec3;
}

export const PALETTE_TABLE: Record<ImagingPalette, PaletteColours> = {
  classic: { bg: [0, 0, 0], tissue: [0.6, 0.7, 0.8], bone: [1, 0.98, 0.92], glow: [0.55, 0.8, 1], edge: [0.7, 0.8, 0.9] },
  negative: { bg: [1, 1, 1], tissue: [0.22, 0.26, 0.32], bone: [0.02, 0.06, 0.2], glow: [0.1, 0.25, 0.7], edge: [0.2, 0.25, 0.35] },
  fluoro: { bg: [0.012, 0.055, 0.065], tissue: [0.22, 0.8, 0.66], bone: [0.82, 1, 0.88], glow: [0.3, 1, 0.8], edge: [0.3, 0.85, 0.75] },
};

const clamp01 = (x: number): number => (x < 0 ? 0 : x > 1 ? 1 : x);

/**
 * Colour of a pixel: tissue (0..1) between the background and the tissue colour, bone (0..1) mixed over it toward the
 * bone colour, glow (>= 0) added as the offset from the background toward the glow colour. Clamped to 0..1.
 */
export function paletteMap(p: ImagingPalette, tissue: number, bone: number, glow = 0): Vec3 {
  const c = PALETTE_TABLE[p];
  const t = clamp01(tissue);
  const b = clamp01(bone);
  const out: Vec3 = [0, 0, 0];
  for (let i = 0; i < 3; i++) {
    const base = c.bg[i]! + (c.tissue[i]! - c.bg[i]!) * t;
    const v = base + (c.bone[i]! - base) * b + (c.glow[i]! - c.bg[i]!) * Math.max(glow, 0);
    out[i] = clamp01(v);
  }
  return out;
}

// ---------------------------------------------------------------- MRI grey levels

export const MRI_G0 = 0.16;
export const MRI_G1 = 0.7;
export const MRI_GK = 0.9;

/** Grey level (0..1) of a cut element in the MRI slice, from its density: low density dark, steel bright. */
export function mriGrey(density: number): number {
  return MRI_G0 + MRI_G1 * (1 - Math.exp(-MRI_GK * Math.max(density, 0)));
}

/** Window / level on a grey value: contrast is the window, exposure the level (a gain). */
export function windowLevel(grey: number, exposure: number, contrast: number): number {
  const v = (grey - 0.5) * contrast + 0.5;
  return clamp01(v * Math.max(exposure, 0));
}

// ---------------------------------------------------------------- MRI slab and scan

export interface Slab {
  /** Unit normal of the slab planes. */
  normal: Vec3;
  /** Centre of the slab: dot(normal, p) = centre. */
  centre: number;
  /** Half thickness, metres. */
  half: number;
  /** Extent of the bounds along the normal (the sweep of `position`). */
  min: number;
  max: number;
}

const AXES: Record<'x' | 'y' | 'z', Vec3> = { x: [1, 0, 0], y: [0, 1, 0], z: [0, 0, 1] };

/** Extent [min, max] of boxes along a unit direction. */
export function extentAlong(n: Vec3, boxes: ReadonlyArray<Box6>): [number, number] {
  let lo = Infinity;
  let hi = -Infinity;
  for (const b of boxes) {
    for (let i = 0; i < 8; i++) {
      const d = n[0] * b[i & 1 ? 3 : 0] + n[1] * b[i & 2 ? 4 : 1] + n[2] * b[i & 4 ? 5 : 2];
      if (d < lo) lo = d;
      if (d > hi) hi = d;
    }
  }
  return [lo, hi];
}

/**
 * The slice slab: normal from the axis (camera: the view direction), `position` 0..1 across the extent of `boxes`
 * (the focus bounds) along that normal, `thickness` metres wide. Null without boxes.
 */
export function slabFor(axis: MriAxis, camForward: Vec3, boxes: ReadonlyArray<Box6>, position: number, thickness: number): Slab | null {
  if (boxes.length === 0) return null;
  let n: Vec3;
  if (axis === 'camera') {
    const l = Math.hypot(camForward[0], camForward[1], camForward[2]) || 1;
    n = [camForward[0] / l, camForward[1] / l, camForward[2] / l];
  } else n = AXES[axis];
  const [min, max] = extentAlong(n, boxes);
  const p = clamp01(position);
  return { normal: n, centre: min + p * (max - min), half: Math.max(thickness, 0.001) / 2, min, max };
}

/** Scan phase 0..2: 0..1 is the sweep up, 1..2 the sweep back. Advance by dt seconds at `speed` (fraction of the sweep per second). */
export function advanceScan(phase: number, dtSeconds: number, speed: number): number {
  let p = phase + dtSeconds * speed;
  p %= 2;
  if (p < 0) p += 2;
  return p;
}

/** Slice position (0..1) of a scan phase: up then back down. */
export function phaseToPosition(phase: number): number {
  const p = ((phase % 2) + 2) % 2;
  return p <= 1 ? p : 2 - p;
}

/** The phase on the way up for a given position (used when a scan starts from the slider value). */
export function positionToPhase(position: number): number {
  return clamp01(position);
}
