// Weighted blended order-independent transparency (McGuire and Bavoil 2013) for the ghost pass.
// The pure maths lives here so the shaders (render/shaders.ts interpolates OIT_GLSL) and the tests share it.
//
// Per ghost fragment i (premultiplied colour C_i * a_i, alpha a_i, view depth z_i in metres):
//   accum   += vec4(C_i * a_i, a_i) * w(z_i, a_i)
//   reveal  *= (1 - a_i)
// Composite over the opaque frame B:
//   avg   = accum.rgb / max(accum.a, 1e-5)
//   final = avg * (1 - reveal) + B * reveal
//
// Revealage as a product needs a different blend function from the accumulation target (ZERO,
// ONE_MINUS_SRC_COLOR against ONE,ONE). WebGL2 core has one blend function for all draw buffers and
// three's material has one blend state, so the ghost pass renders into both attachments with
// ONE,ONE and the revealage target stores the sum of -ln(1 - a_i). Then reveal = exp(-sum) =
// product of (1 - a_i) exactly. Sums are commutative, so the result is independent of draw order.

/** Weight of a fragment: the depth-weighted form of the paper, or a plain alpha weight. */
export type OitWeightMode = 'paper' | 'flat';

export const OIT_WEIGHT_MODES: readonly OitWeightMode[] = ['paper', 'flat'];

/** Fragment alpha is clamped here before -ln(1 - a), so a fully opaque rim fragment stays finite (about 6.2). */
export const OIT_MAX_ALPHA = 0.998;

/** Paper eq. (10) depth term: 0.03 / (1e-5 + (z / 200)^4), clamped to [1e-2, 3e3]. z in metres. */
export function oitDepthTerm(z: number): number {
  const t = z / 200;
  const v = 0.03 / (1e-5 + t * t * t * t);
  return Math.min(3e3, Math.max(1e-2, v));
}

/** w(z, a). 'flat' has no depth term (w = a). */
export function oitWeight(z: number, alpha: number, mode: OitWeightMode = 'paper'): number {
  return mode === 'flat' ? alpha : alpha * oitDepthTerm(z);
}

export interface OitLayer {
  /** Non-premultiplied colour, 0..1. */
  color: readonly [number, number, number];
  alpha: number;
  /** View-space depth in metres. */
  z: number;
}

export interface OitBuffers {
  accum: [number, number, number, number];
  /** Sum of -ln(1 - a_i) (what the revealage attachment holds). */
  logReveal: number;
}

/** What the two render targets hold after the ghost pass drew `layers` in any order. */
export function oitAccumulate(layers: readonly OitLayer[], mode: OitWeightMode = 'paper'): OitBuffers {
  const accum: [number, number, number, number] = [0, 0, 0, 0];
  let logReveal = 0;
  for (const l of layers) {
    const w = oitWeight(l.z, l.alpha, mode);
    accum[0] += l.color[0] * l.alpha * w;
    accum[1] += l.color[1] * l.alpha * w;
    accum[2] += l.color[2] * l.alpha * w;
    accum[3] += l.alpha * w;
    logReveal += -Math.log(1 - Math.min(l.alpha, OIT_MAX_ALPHA));
  }
  return { accum, logReveal };
}

/** The composite pass: final = avg * (1 - reveal) + background * reveal. */
export function oitComposite(buf: OitBuffers, background: readonly [number, number, number]): [number, number, number] {
  const reveal = Math.exp(-buf.logReveal);
  const d = Math.max(buf.accum[3], 1e-5);
  return [0, 1, 2].map((i) => (buf.accum[i]! / d) * (1 - reveal) + background[i]! * reveal) as [number, number, number];
}

/** Reference: the sorted over operator, far to near. */
export function overSorted(layers: readonly OitLayer[], background: readonly [number, number, number]): [number, number, number] {
  const sorted = [...layers].sort((a, b) => b.z - a.z);
  const out: [number, number, number] = [background[0], background[1], background[2]];
  for (const l of sorted) for (let i = 0; i < 3; i++) out[i] = l.color[i]! * l.alpha + out[i]! * (1 - l.alpha);
  return out;
}

const f = (x: number): string => (Number.isInteger(x) ? x.toFixed(1) : String(x));

/** GLSL for the ghost fragment shader in OIT mode; mirrors oitWeight above. */
export const OIT_GLSL = /* glsl */ `
const float OIT_MAX_ALPHA = ${f(OIT_MAX_ALPHA)};
uniform float oitFlat; // 1: w = alpha (no depth term)
float oitWeight(float z, float a) {
  if (oitFlat > 0.5) return a;
  return a * clamp(0.03 / (1e-5 + pow(z / 200.0, 4.0)), 1e-2, 3e3);
}
`;
