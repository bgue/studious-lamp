// GLSL of the imaging styles (radiograph, MRI). Constants come from imaging/maths.ts, which holds the reference
// implementation of every function here (attenuate, contrastCurve, paletteMap, mriGrey, windowLevel).
//
// Passes (render/renderer.ts, renderImaging):
//   thickness  every visible element, no depth test, additive blending into an RGBA float target:
//              r = context  sum of  (front face ? -z : +z) * density     (= density * thickness through closed solids)
//              g = focus ("bone") thickness times BONE_DENSITY, whatever the material
//   slab       (MRI) depth-tested section of the elements cut by the slab, with back-face caps
//   glow       separable blur of the bone intensity (two scales)
//   composite  full screen: attenuation + contrast + palette

import { BONE_DENSITY, CONTRAST_PIVOT, GLOW_A, GLOW_B, K_BONE, K_TISSUE, MRI_FAINT, MRI_FAINT_BONE, MRI_G0, MRI_G1, MRI_GK } from '../imaging/maths';
import { VIEWMODE_GLSL } from './viewModeGlsl';

const f = (x: number): string => (Number.isInteger(x) ? x.toFixed(1) : String(x));

const FLAGS = /* glsl */ `
bool flagFocus(float f)  { return (int(f + 0.5) & 1) != 0; }
bool flagHidden(float f) { return (int(f + 0.5) & 2) != 0; }
bool flagClosed(float f) { return (int(f + 0.5) & 16) != 0; }
`;

const VARYINGS = /* glsl */ `
flat varying float vAlpha;
flat varying float vFlags;
flat varying float vElem;
flat varying float vVmOcc;
flat varying float vDensity;
varying vec3 vWorldNormal;
varying vec3 vWorldPos;
`;

const MRI_GREY = /* glsl */ `
float mriGrey(float d) { return ${f(MRI_G0)} + ${f(MRI_G1)} * (1.0 - exp(-${f(MRI_GK)} * max(d, 0.0))); }
`;

/** Thickness accumulation (vertex shader: MESH_VERT without a pass define: only hidden elements are rejected). */
export const IMG_THICK_FRAG = /* glsl */ `
${FLAGS}
${VIEWMODE_GLSL}
${VARYINGS}
void main() {
  if (flagHidden(vFlags)) discard;
  if (clipN > 0 && clipCut(vWorldPos)) discard;
  bool focus = flagFocus(vFlags);
  float w = 1.0;
  if (!focus && vmAny > 0.5) {
    // Behind-only and peel cut the thickness pass like any other: the same per-fragment function.
    VmOut vm = vmEval(vWorldPos, vAlpha, vVmOcc, !gl_FrontFacing);
    if (vm.cover < 0.002) discard;
    w = vm.cover;
    if (vm.front) w *= vm.alpha;
  }
  float z = -(viewMatrix * vec4(vWorldPos, 1.0)).z; // view depth, metres
  float t = (gl_FrontFacing ? -1.0 : 1.0) * z * w;
  gl_FragColor = focus ? vec4(0.0, t * ${f(BONE_DENSITY)}, 0.0, 0.0) : vec4(t * vDensity, 0.0, 0.0, 0.0);
}
`;

/**
 * MRI slab: the ray enters the slab at its near plane. Everything on the camera side of that plane is cut. Of what
 * remains, the nearest surface decides: a back face means the ray starts inside a solid (cap: flat grey of that
 * element, whatever its depth), a front face inside the slab is drawn shaded, a front face beyond the slab shows nothing.
 * Output: r = grey level, g = bone (focus) flag, b = slab edge line, a = covered.
 */
export const IMG_SLAB_FRAG = /* glsl */ `
${FLAGS}
${VIEWMODE_GLSL}
${VARYINGS}
${MRI_GREY}
uniform vec4 imgSlab;     // xyz = unit normal, w = centre
uniform float imgHalf;    // half thickness, metres
uniform float imgScan;    // 1: light the slab edges
uniform vec3 imgCamSide;  // x = +1 / -1: the side of the slab the camera is on
void main() {
  if (flagHidden(vFlags)) discard;
  if (clipN > 0 && clipCut(vWorldPos)) discard;
  bool focus = flagFocus(vFlags);
  // A back face is a cap only on a closed solid. A back face of an open element (a pane, a sheet) is drawn like a front face.
  bool capBack = !gl_FrontFacing && flagClosed(vFlags);
  if (!focus && vmAny > 0.5) {
    VmOut vm = vmEval(vWorldPos, vAlpha, vVmOcc, capBack);
    if (vm.cover < VM_FULL) discard;
  }
  // u > 0 toward the camera.
  float u = imgCamSide.x * (dot(imgSlab.xyz, vWorldPos) - imgSlab.w);
  if (u > imgHalf) discard;
  float bone = focus ? 1.0 : 0.0;
  float lvl = mriGrey(vDensity);
  if (focus) lvl = 1.0;
  float edge = 0.0;
  if (!capBack) {
    if (u < -imgHalf) { gl_FragColor = vec4(0.0); return; } // beyond the slab: nothing, but it hides what is behind
    vec3 n = normalize(vWorldNormal);
    if (!gl_FrontFacing) n = -n;
    lvl *= 0.72 + 0.28 * clamp(dot(n, normalize(cameraPosition - vWorldPos)), 0.0, 1.0);
    if (imgScan > 0.5) edge = smoothstep(imgHalf - min(0.04, imgHalf * 0.6), imgHalf, abs(u));
  } else {
    lvl *= 0.92; // cap: flat
    if (imgScan > 0.5) edge = smoothstep(imgHalf - min(0.04, imgHalf * 0.6), imgHalf, abs(u));
  }
  gl_FragColor = vec4(lvl, bone, edge, 1.0);
}
`;

export const IMG_FULLSCREEN_VERT = /* glsl */ `
void main() {
  gl_Position = vec4(position.xy, 0.0, 1.0);
}
`;

/** One separable blur step. mode 0: input is the thickness target (bone channel -> intensity), mode 1: a previous blur. */
export const IMG_BLUR_FRAG = /* glsl */ `
uniform sampler2D tSrc;
uniform int srcScale;   // source texels per output texel
uniform ivec2 stepPx;   // tap spacing in source texels
uniform float srcMode;
uniform float imgExposure;
float boneIntensity(ivec2 q, ivec2 sz) {
  vec4 v = texelFetch(tSrc, clamp(q, ivec2(0), sz - 1), 0);
  return 1.0 - exp(-imgExposure * ${f(K_BONE)} * max(v.g, 0.0));
}
float boneAt(ivec2 q, ivec2 sz) {
  if (srcMode < 0.5) {
    // 2 x 2 box of the full-resolution target, so thin lines survive the reduction
    return 0.25 * (boneIntensity(q, sz) + boneIntensity(q + ivec2(1, 0), sz) + boneIntensity(q + ivec2(0, 1), sz) + boneIntensity(q + ivec2(1, 1), sz));
  }
  return texelFetch(tSrc, clamp(q, ivec2(0), sz - 1), 0).r;
}
void main() {
  ivec2 sz = textureSize(tSrc, 0);
  ivec2 c = ivec2(gl_FragCoord.xy) * srcScale;
  float acc = boneAt(c, sz) * 0.227027;
  float wgt[4] = float[4](0.1945946, 0.1216216, 0.054054, 0.016216);
  for (int k = 1; k <= 4; k++) {
    acc += (boneAt(c + stepPx * k, sz) + boneAt(c - stepPx * k, sz)) * wgt[k - 1];
  }
  gl_FragColor = vec4(acc, 0.0, 0.0, 1.0);
}
`;

/** Full-screen composite of the thickness (and slab, glow) targets through exposure, contrast and palette. */
export const IMG_COMPOSITE_FRAG = /* glsl */ `
uniform sampler2D tThick;
uniform sampler2D tSlab;
uniform sampler2D tGlowA;
uniform sampler2D tGlowB;
uniform vec2 imgRes;
uniform float imgStyle;     // 0 radiograph, 1 mri
uniform float imgExposure;       // the exposure slider: bone, and the MRI level
uniform float imgTissueExposure; // slider times the automatic exposure: the radiograph tissue attenuation (the MRI keeps the slider)
uniform float imgContrast;
uniform float imgBoneGlow;
uniform float imgGlowOn;
uniform vec3 palBg;
uniform vec3 palTissue;
uniform vec3 palBone;
uniform vec3 palGlow;

float imgAtt(float t, float k, float ex) { return 1.0 - exp(-ex * k * max(t, 0.0)); }
float imgContrastCurve(float i) { return clamp((i - ${f(CONTRAST_PIVOT)}) * imgContrast + ${f(CONTRAST_PIVOT)}, 0.0, 1.0); }

void main() {
  ivec2 p = ivec2(gl_FragCoord.xy);
  vec4 th = texelFetch(tThick, p, 0);
  vec2 uv = gl_FragCoord.xy / imgRes;
  float glow = 0.0;
  if (imgGlowOn > 0.5) glow = imgBoneGlow * (texture2D(tGlowA, uv).r * ${f(GLOW_A)} + texture2D(tGlowB, uv).r * ${f(GLOW_B)});
  float tissue;
  float bone;
  if (imgStyle < 0.5) {
    tissue = imgContrastCurve(imgAtt(th.r, ${f(K_TISSUE)}, imgTissueExposure));
    bone = imgContrastCurve(imgAtt(th.g, ${f(K_BONE)}, imgExposure));
  } else {
    float faint = ${f(MRI_FAINT)} * imgAtt(th.r, ${f(K_TISSUE)}, imgExposure);
    float faintBone = ${f(MRI_FAINT_BONE)} * imgAtt(th.g, ${f(K_BONE)}, imgExposure);
    vec4 s = texelFetch(tSlab, p, 0);
    float cov = s.a;
    vec3 sl = s.rgb / max(cov, 1e-4);
    // window / level on the grey level; the scan line lifts the slab edges
    float lvl = clamp(((sl.r - 0.5) * imgContrast + 0.5) * imgExposure, 0.0, 1.0);
    lvl = mix(lvl, 1.0, 0.85 * sl.b);
    tissue = mix(faint, lvl, cov);
    bone = mix(faintBone, sl.g, cov);
  }
  vec3 base = palBg + (palTissue - palBg) * clamp(tissue, 0.0, 1.0);
  vec3 col = base + (palBone - base) * clamp(bone, 0.0, 1.0) + (palGlow - palBg) * max(glow, 0.0);
  gl_FragColor = vec4(clamp(col, 0.0, 1.0), 1.0);
}
`;

/** Decimation for the automatic exposure: a 64 x 64 grid of single samples of the thickness target (r = context, g = bone). */
export const IMG_DECIMATE_FRAG = /* glsl */ `
uniform sampler2D tSrc;
void main() {
  ivec2 sz = textureSize(tSrc, 0);
  vec2 g = (floor(gl_FragCoord.xy) + 0.5) / 64.0;
  ivec2 p = clamp(ivec2(g * vec2(sz)), ivec2(0), sz - 1);
  vec4 v = texelFetch(tSrc, p, 0);
  gl_FragColor = vec4(v.r, v.g, 0.0, 1.0);
}
`;
