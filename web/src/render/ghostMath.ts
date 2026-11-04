// Ghost appearance maths shared by the shaders (render/shaders.ts interpolates these constants into the
// GLSL) and the tests. Everything that makes a ghost look different from an opaque element scales with
// the transparency t = 1 - alpha, so an element at alpha 0.99 is nearly identical to one at 1.0 and the
// pass switch at OPAQUE_ALPHA is invisible.

/** Elements with alpha >= this are drawn by the opaque pass, the others by the ghost pass. */
export const OPAQUE_ALPHA = 0.999;
/** Fresnel-style rim: opacity gain = rimOpacity * (1 - |n.v|)^rimPower, at grazing angles. */
export const RIM_POWER = 2;
export const RIM_OPACITY = 0.75;
/** At full transparency the rim also darkens the fill toward the ink colour by this much. */
export const RIM_INK = 0.4;
/** At full transparency the whole fill is pulled toward the ink colour by this much (planar faces seen head-on). */
export const FILL_INK = 0.55;
/** Dark slate (not black) used for ghost fill tint and for ghost edges. Linear-ish sRGB values 0..1. */
export const INK_COLOUR: readonly [number, number, number] = [0.16, 0.21, 0.3];
/** No ghost fragment is more transparent than this before the rim is added. */
export const MIN_FILL_ALPHA = 0.08;

const clamp01 = (x: number): number => Math.min(1, Math.max(0, x));

/** Transparency of a ghost: 0 opaque .. 1 invisible. */
export function transparency(alpha: number): number {
  return clamp01(1 - alpha);
}

/** Desaturation toward the cool grey: ghostDesaturate * t. */
export function desaturation(ghostDesaturate: number, alpha: number): number {
  return ghostDesaturate * transparency(alpha);
}

/** Depth-grade strength actually applied: strength * t. */
export function gradeStrengthFor(strength: number, alpha: number): number {
  return strength * transparency(alpha);
}

/** Rim factor 0 (head-on) .. 1 (grazing) from |n.v|. */
export function rimFactor(absNdotV: number): number {
  return Math.pow(1 - clamp01(absNdotV), RIM_POWER);
}

/** Fragment alpha of a ghost with base alpha `alpha` at facing ratio |n.v|. Equals alpha at alpha = 1. */
export function ghostFragmentAlpha(alpha: number, absNdotV: number): number {
  const base = Math.max(alpha, MIN_FILL_ALPHA);
  const a = base + (1 - base) * RIM_OPACITY * rimFactor(absNdotV);
  return alpha >= 1 ? 1 : a;
}

const f = (x: number): string => (Number.isInteger(x) ? x.toFixed(1) : String(x));

/** GLSL constant block for the shaders. */
export const GHOST_GLSL = /* glsl */ `
#define OPAQUE_ALPHA ${f(OPAQUE_ALPHA)}
const float RIM_POWER = ${f(RIM_POWER)};
const float RIM_OPACITY = ${f(RIM_OPACITY)};
const float RIM_INK = ${f(RIM_INK)};
const float FILL_INK = ${f(FILL_INK)};
const float MIN_FILL_ALPHA = ${f(MIN_FILL_ALPHA)};
const vec3 INK_COLOUR = vec3(${INK_COLOUR.map(f).join(', ')});
`;
