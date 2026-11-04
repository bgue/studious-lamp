// GLSL of the view modes (behind-only and partial peelback) and of the peel mask / jump flooding passes.
// vmEval mirrors viewModes/maths.ts (behindFragment, peelFragment); the tests check the constants it shares.

import { JFA_START, PEEL_CAP_SLACK, PEEL_MAX_ELLIPSES, PEEL_TILT, VM_FULL } from '../viewModes/maths';

const f = (x: number): string => (Number.isInteger(x) ? x.toFixed(1) : String(x));

/** Uniform declarations and the per-fragment evaluation, included by the mesh and the edge fragment shaders. */
export const VIEWMODE_GLSL = /* glsl */ `
const float PEEL_CAP_SLACK = ${f(PEEL_CAP_SLACK)};
const float PEEL_TILT = ${f(PEEL_TILT)};
const float VM_FULL = ${f(VM_FULL)}; // coverage above this is untouched
const int PEEL_MAX_ELLIPSES = ${PEEL_MAX_ELLIPSES};

uniform float vmAny;          // 1 when behind-only or peelback is on (context fragments run vmEval)
// behind-only
uniform float bhOn;
uniform float bhMode;         // 0 cut, 1 ghost, 2 cut + cap
uniform float bhOccOnly;
uniform float bhKeep;         // keep x-ray behind the plane
uniform float bhFrontAlpha;
uniform vec4 bhPlane;         // xyz = unit normal, w = d; the camera side is dot(n, p) < d
uniform vec3 bhCap;
// peelback
uniform float peelOn;         // 0 off, 1 mask + jump flood, 2 CPU ellipses
uniform float peelOccOnly;
uniform float peelSolid;      // everything outside the window is solid
uniform float peelRimOn;
uniform float peelCapOn;
uniform vec4 peelP;           // r0 (m), slope, feather (m), eps (m)
uniform vec3 peelRimCol;
uniform vec3 peelCapCol;
uniform sampler2D peelTex;    // jump flood result: xy = nearest focus texel (centre), z = its view depth, w = 1 valid
uniform vec2 peelTexSize;
uniform vec2 peelRes;         // size in pixels of the render target being drawn
uniform float peelProjY;      // projectionMatrix[1][1]
uniform vec4 peelEll[PEEL_MAX_ELLIPSES];
uniform float peelEllZ[PEEL_MAX_ELLIPSES];
uniform int peelEllN;
// hover highlight
uniform float hoverId;
uniform vec3 hoverColor;

struct VmOut {
  float alpha;  // effective base alpha of the fragment (1: solid)
  float cover;  // 0 = cut, 1 = untouched, in between the feather
  float rim;    // peel rim band strength
  bool cap;     // back face revealed by a cut: paint the cap colour
  bool front;   // behind-only ghost treatment: drawn through the ghost pass at the front alpha
};

float vmSmooth(float a, float b, float x) {
  if (b <= a) return x >= b ? 1.0 : 0.0;
  float t = clamp((x - a) / (b - a), 0.0, 1.0);
  return t * t * (3.0 - 2.0 * t);
}

float vmViewDepth(vec3 wp) {
  return -(viewMatrix * vec4(wp, 1.0)).z;
}

// Nearest focus pixel to this fragment: distance in pixels and its view depth. False when there is none.
bool peelNearest(out float distPx, out float zf) {
  vec2 fc = gl_FragCoord.xy;
  distPx = 0.0;
  zf = 0.0;
  if (peelOn > 1.5) {
    bool found = false;
    float best = 1e20;
    for (int i = 0; i < PEEL_MAX_ELLIPSES; i++) {
      if (i >= peelEllN) break;
      vec4 e = peelEll[i];
      vec2 q = (fc - e.xy) / e.zw;
      float d = max(length(q) - 1.0, 0.0) * min(e.z, e.w);
      if (d < best) { best = d; zf = peelEllZ[i]; found = true; }
    }
    distPx = best;
    return found;
  }
  ivec2 sz = ivec2(peelTexSize);
  ivec2 t = clamp(ivec2(fc / peelRes * peelTexSize), ivec2(0), sz - 1);
  vec4 s = texelFetch(peelTex, t, 0);
  if (s.w < 0.5) return false;
  vec2 sp = (s.xy / peelTexSize) * peelRes;
  distPx = length(sp - fc);
  zf = s.z;
  return true;
}

VmOut vmEval(vec3 wp, float alpha0, float occ, bool back) {
  VmOut o;
  o.alpha = alpha0;
  o.cover = 1.0;
  o.rim = 0.0;
  o.cap = false;
  o.front = false;
  if (bhOn > 0.5 && (bhOccOnly < 0.5 || occ > 0.5)) {
    if (dot(bhPlane.xyz, wp) < bhPlane.w) {
      if (bhMode > 0.5 && bhMode < 1.5) { o.alpha = bhFrontAlpha; o.front = true; }
      else o.cover = 0.0;
    } else {
      if (bhKeep < 0.5) o.alpha = 1.0;
      if (bhMode > 1.5 && back) o.cap = true;
    }
  }
  if (peelOn > 0.5 && (peelOccOnly < 0.5 || occ > 0.5)) {
    float distPx;
    float zf;
    bool have = peelNearest(distPx, zf);
    if (have) {
      float z = vmViewDepth(wp);
      float distM = distPx * zf / (0.5 * peelRes.y * peelProjY); // screen distance in metres at the focus depth
      float R = peelP.x + peelP.y * max(zf - z, 0.0);
      float c = 1.0;
      if (z < zf - peelP.w - PEEL_TILT * distM) {
        c = vmSmooth(R, R + peelP.z, distM);
        if (peelRimOn > 0.5 && !back && distM >= R) o.rim = 1.0 - vmSmooth(R, R + peelP.z + 0.03, distM);
      }
      o.cover = min(o.cover, c);
      if (peelCapOn > 0.5 && back && c > VM_FULL) {
        float Rc = peelP.x + peelP.y * max(zf - (z - PEEL_CAP_SLACK), 0.0);
        if (distM < Rc) o.cap = true;
      }
    }
    if (peelSolid > 0.5 && !o.front) o.alpha = 1.0;
  }
  return o;
}

// Cap colour with a light screen-space hatch; used for back faces a cut revealed.
vec3 vmCapColour(vec3 base) {
  float h = mod(floor((gl_FragCoord.x + gl_FragCoord.y) / 5.0), 2.0);
  return base * (1.0 - 0.12 * h);
}

bool vmHovered(float id) { return abs(id - hoverId) < 0.5; }
`;

/** Fragment shader of the peel mask: view depth of the nearest focus fragment in r, 1 in g. */
export const PEEL_MASK_FRAG = /* glsl */ `
flat varying float vFlags;
varying vec3 vWorldPos;
void main() {
  if ((int(vFlags + 0.5) & 1) == 0 || (int(vFlags + 0.5) & 2) != 0) discard;
  float z = -(viewMatrix * vec4(vWorldPos, 1.0)).z;
  gl_FragColor = vec4(z, 1.0, 0.0, 1.0);
}
`;

/** Full-screen triangle (positions already in clip space). */
export const PEEL_FULLSCREEN_VERT = /* glsl */ `
void main() {
  gl_Position = vec4(position.xy, 0.0, 1.0);
}
`;

/** Turns the mask into seeds: xy = own texel centre, z = depth, w = 1. */
export const PEEL_INIT_FRAG = /* glsl */ `
uniform sampler2D tMask;
void main() {
  ivec2 p = ivec2(gl_FragCoord.xy);
  vec4 m = texelFetch(tMask, p, 0);
  gl_FragColor = m.g > 0.5 ? vec4(vec2(p) + 0.5, m.r, 1.0) : vec4(0.0);
}
`;

/** One jump of the flood: keep the nearest seed among the 3 x 3 neighbours `jump` texels away. */
export const PEEL_STEP_FRAG = /* glsl */ `
uniform sampler2D tSeed;
uniform float jump;
void main() {
  ivec2 p = ivec2(gl_FragCoord.xy);
  ivec2 sz = textureSize(tSeed, 0);
  int j = int(jump + 0.5);
  vec4 best = vec4(0.0);
  float bd = 1e20;
  for (int dy = -1; dy <= 1; dy++) {
    for (int dx = -1; dx <= 1; dx++) {
      ivec2 q = p + ivec2(dx, dy) * j;
      if (q.x < 0 || q.y < 0 || q.x >= sz.x || q.y >= sz.y) continue;
      vec4 s = texelFetch(tSeed, q, 0);
      if (s.w < 0.5) continue;
      vec2 d = s.xy - (vec2(p) + 0.5);
      float dd = dot(d, d);
      if (dd < bd) { bd = dd; best = s; }
    }
  }
  gl_FragColor = best;
}
`;

export const PEEL_JFA_START = JFA_START;
