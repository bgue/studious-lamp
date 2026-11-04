// Hand-written GLSL for the three mesh passes and the edge passes.
// three prepends `#version 300 es`, precision statements, and maps
// attribute -> in, varying -> out/in, gl_FragColor -> pc_fragColor, texture2D -> texture.

import { GHOST_GLSL } from './ghostMath';
import { OIT_GLSL } from './oitMath';
import { VIEWMODE_GLSL } from './viewModeGlsl';

const STATE_FETCH = /* glsl */ `
uniform sampler2D stateA; // rgb = colour (sRGB, 0..1), a = alpha
uniform sampler2D stateB; // r = flags (bit0 focus, bit1 hidden, bit2 pinned, bit3 selected), g = edge glow, b = sweep hold alpha (0 = not in the sweep), a = view-mode occluder mask (1 = occluder)
uniform sampler2D stateC; // rgb = world-space displacement (exploded context), a = X-ray density of the element (imaging)
uniform int texWidth;
attribute float elementId;

flat varying vec3 vColor;
flat varying float vAlpha;
flat varying float vFlags;
flat varying float vGlow;
flat varying float vHold;
flat varying float vElem;
flat varying float vVmOcc;
flat varying float vDensity;

vec3 gOffset; // displacement of the current element, set by fetchState()

// Fetch per-element state; returns flags as int.
int fetchState() {
  int id = int(elementId + 0.5);
  ivec2 tc = ivec2(id % texWidth, id / texWidth);
  vec4 a = texelFetch(stateA, tc, 0);
  vec4 b = texelFetch(stateB, tc, 0);
  vColor = a.rgb;
  vAlpha = a.a;
  vFlags = b.r;
  vGlow = b.g;
  vHold = b.b;
  vElem = float(id);
  vVmOcc = b.a;
  vec4 cc = texelFetch(stateC, tc, 0);
  gOffset = cc.rgb;
  vDensity = cc.a;
  return int(b.r + 0.5);
}
`;

const FLAG_HELPERS = /* glsl */ `
bool flagFocus(float f)    { return (int(f + 0.5) & 1) != 0; }
bool flagHidden(float f)   { return (int(f + 0.5) & 2) != 0; }
bool flagSelected(float f) { return (int(f + 0.5) & 8) != 0; }
bool flagClosed(float f)   { return (int(f + 0.5) & 16) != 0; } // closed solid: caps are painted for these only
`;

const FOG_HELPERS = /* glsl */ `
// Distance fog toward a horizon colour, disabled when fogRange.z (max mix) is 0.
uniform vec3 fogColor;
uniform vec3 fogRange; // x = near, y = far, z = max mix
vec3 applyFog(vec3 c, float dist) {
  if (fogRange.z <= 0.0) return c;
  return mix(c, fogColor, fogRange.z * smoothstep(fogRange.x, fogRange.y, dist));
}
`;

const SWEEP_HELPERS = /* glsl */ `
// Sweep reveal: a plane travelling from the camera through the occluders. Mirrors cinematic/sweep.ts.
uniform vec3 planeNormal;
uniform float planeOffset;
uniform float bandWidth;
uniform float sweepEnabled;   // 1 while a sweep runs
uniform vec3 sweepColor;
uniform float sweepAlphaMin;
// Signed distance to the plane: <= 0 on the camera side (already peeled), > 0 not reached yet.
float sweepDist(vec3 p) { return dot(planeNormal, p) - planeOffset; }
// Bright band at the plane: wide (bandWidth) on the unreached side, a thin rim on the peeled side.
float sweepBandAt(float s) {
  return s > 0.0 ? 1.0 - smoothstep(0.0, bandWidth, s) : 1.0 - smoothstep(0.0, 0.25 * bandWidth, -s);
}
// Extra transparency just behind the plane front, relaxing to nothing over 4 band widths.
float sweepPeelAt(float s) { return s <= 0.0 ? 1.0 - smoothstep(0.0, 4.0 * bandWidth, -s) : 0.0; }
`;

// ---------------------------------------------------------------- mesh passes

export const MESH_VERT = /* glsl */ `
${GHOST_GLSL}
${STATE_FETCH}
uniform float sweepEnabled;
uniform float vmAny;
varying vec3 vWorldNormal;
varying vec3 vWorldPos;

void main() {
  int f = fetchState();
  bool focus = (f & 1) != 0;
  bool hidden = (f & 2) != 0;

  vec4 wp = modelMatrix * vec4(position, 1.0);
  wp.xyz += gOffset;
  vWorldPos = wp.xyz;
  vWorldNormal = normalize(mat3(modelMatrix) * normal);
  gl_Position = projectionMatrix * viewMatrix * wp;

  // Reject whole triangles early (all three vertices carry the same element state).
  bool reject = hidden;
#if defined( PASS_OPAQUE )
  // During a sweep, ghost-bound members that were opaque before are also drawn here (the part the plane has not reached).
  reject = reject || focus || (vAlpha < OPAQUE_ALPHA && !(sweepEnabled > 0.5 && vHold >= OPAQUE_ALPHA) && vmAny < 0.5);
#elif defined( PASS_GHOST )
  reject = reject || focus || (vAlpha >= OPAQUE_ALPHA && vmAny < 0.5);
#elif defined( PASS_FOCUS )
  reject = reject || !focus;
#endif
  if (reject) gl_Position = vec4(2.0, 2.0, 2.0, 1.0);
}
`;

export const MESH_FRAG = /* glsl */ `
${GHOST_GLSL}
${FLAG_HELPERS}
${FOG_HELPERS}
${SWEEP_HELPERS}
${VIEWMODE_GLSL}
#if defined( OIT )
// Weighted blended OIT (render/oitMath.ts): the ghost pass writes accumulation and revealage (GLSL3 material).
layout(location = 0) out highp vec4 oitAccum;
layout(location = 1) out highp vec4 oitReveal;
${OIT_GLSL}
#endif
flat varying vec3 vColor;
flat varying float vAlpha;
flat varying float vFlags;
flat varying float vHold;
flat varying float vElem;
flat varying float vVmOcc;
varying vec3 vWorldNormal;
varying vec3 vWorldPos;

uniform vec3 lightDir;     // world space, towards the light, normalised
uniform vec3 skyColor;     // hemisphere sky colour * intensity
uniform vec3 groundColor;  // hemisphere ground colour * intensity
uniform vec3 dirColor;     // directional colour * intensity
uniform float ghostDesaturate;
uniform float focusBoost;  // emissive boost for the selective bloom mask render, 0 otherwise
uniform vec3 focusCenter;  // depth-graded ghosting: focus bounds centre
uniform float focusRadius; // normaliser for the along-view distance; 0 = no focus
uniform float gradeStrength; // 0 = off

vec3 shade(vec3 base, vec3 n) {
  vec3 hemi = mix(groundColor, skyColor, n.y * 0.5 + 0.5);
  float lambert = max(dot(n, lightDir), 0.0);
  return base * (hemi + dirColor * lambert);
}

// The one colour function of both mesh passes. t = 1 - alpha (0 for the opaque pass): every ghost-only
// effect (desaturation, ink tint, depth grade) is scaled by t, so at t = 0 this is exactly the opaque
// lighting and a ghost at alpha 0.99 differs from an opaque element by about 1% of each effect.
vec3 surfaceColour(vec3 base, vec3 n, float flags, vec3 worldPos, float t, float rim) {
  if (t > 0.0) {
    // Desaturate toward a cool grey that keeps the element's luminance.
    float lum = dot(base, vec3(0.299, 0.587, 0.114));
    vec3 coolGrey = vec3(lum) * vec3(0.92, 0.97, 1.06) + vec3(0.0, 0.01, 0.03);
    base = mix(base, coolGrey, ghostDesaturate * t);
  }
  vec3 col = shade(base, n);
  if (flagSelected(flags)) col = mix(col, vec3(1.0, 0.85, 0.2), 0.35);
  if (t > 0.0) {
    // Ink: a faint dark slate over the whole fill, more at grazing angles, so a nearly transparent
    // ghost still has a darker body than the light background behind it.
    col = mix(col, INK_COLOUR, t * (FILL_INK + RIM_INK * rim));
    if (gradeStrength > 0.0 && focusRadius > 0.0) {
      // Depth grading: cooler and darker the further the fragment sits in front of the focus (along the view axis).
      vec3 axis = normalize(focusCenter - cameraPosition);
      float d = max(dot(focusCenter - worldPos, axis), 0.0);
      float g = gradeStrength * t * (1.0 - exp(-d / focusRadius));
      vec3 deep = vec3(0.10, 0.16, 0.28) * (0.6 + 0.8 * dot(col, vec3(0.3333)));
      col = mix(col, deep, g);
    }
  }
  return col;
}

void main() {
  bool focus = flagFocus(vFlags);
  bool hidden = flagHidden(vFlags);
  if (hidden) discard;
  if (clipN > 0 && clipCut(vWorldPos)) discard; // section planes

  vec3 n = normalize(vWorldNormal);
  bool hovered = vmHovered(vElem);

#if defined( PASS_OPAQUE )
  if (focus) discard;
  // View modes (behind-only, peelback): per-fragment cut, solid-behind and cap decisions.
  VmOut vm = VmOut(vAlpha, 1.0, 0.0, false, false);
  // A back face counts as a cut face (cap) only on a closed solid; an open element (a pane, a sheet) just shows its back face shaded.
  bool capBack = !gl_FrontFacing && flagClosed(vFlags);
  if (vmAny > 0.5) vm = vmEval(vWorldPos, vAlpha, vVmOcc, capBack);
  if (vm.cover < VM_FULL) discard; // cut, or inside the feather (drawn by the ghost pass)
  bool member = sweepEnabled > 0.5 && vHold > 0.0;
  float s = 0.0;
  if (member) s = sweepDist(vWorldPos);
  if (vm.alpha != vAlpha) {
    // A view mode changed the alpha: below OPAQUE the fragment belongs to the ghost pass.
    if (vm.alpha < OPAQUE_ALPHA) discard;
  } else if (vAlpha < OPAQUE_ALPHA) {
    // Ghost-bound element: only the part the sweep has not reached yet is drawn here, opaque.
    if (!member || vHold < OPAQUE_ALPHA || s <= 0.0) discard;
  }
#if defined( DEPTH_ONLY )
  gl_FragColor = vec4(0.0); // depth pre-pass of the OIT target: same discards, no colour
#else
  if (!gl_FrontFacing) n = -n;
  vec3 col = surfaceColour(vColor, n, vFlags, vWorldPos, 0.0, 0.0);
  col = applyFog(col, distance(cameraPosition, vWorldPos));
  if (member) col = mix(col, sweepColor, 0.85 * sweepBandAt(s));
  if (vm.rim > 0.0) col = mix(col, peelRimCol, 0.85 * vm.rim);
  if (vm.cap) col = vmCapColour(bhOn > 0.5 && bhMode > 1.5 ? bhCap : peelCapCol);
  if (clipN > 0 && clipCapOn > 0.5 && capBack) col = vmCapColour(clipCapCol); // back face of a closed solid revealed by a section
  if (hovered) col = mix(col, hoverColor, 0.4) + 0.06;
  gl_FragColor = vec4(col, 1.0);
#endif

#elif defined( PASS_GHOST )
  if (focus) discard;
  VmOut vm = VmOut(vAlpha, 1.0, 0.0, false, false);
  if (vmAny > 0.5) vm = vmEval(vWorldPos, vAlpha, vVmOcc, false);
  if (vm.cover < 0.002) discard;
  bool feather = vm.cover < VM_FULL;
  // Solid fragments belong to the opaque pass, except in the peel feather where they fade out here.
  if (vm.alpha >= OPAQUE_ALPHA && !feather) discard;
  float aBase = vm.alpha;
  float band = 0.0;
  if (vm.alpha == vAlpha && sweepEnabled > 0.5 && vHold > 0.0) {
    float s = sweepDist(vWorldPos);
    band = sweepBandAt(s);
    if (s > 0.0) {
      // Not reached yet: look as before the selection (opaque ones are drawn by the opaque pass).
      if (vHold >= OPAQUE_ALPHA) discard;
      aBase = vHold;
    } else {
      aBase = min(vAlpha, mix(vAlpha, sweepAlphaMin, 0.6 * sweepPeelAt(s)));
    }
  }
  vec3 v = normalize(cameraPosition - vWorldPos);
  float rim = pow(1.0 - abs(dot(n, v)), RIM_POWER);
  float t = 1.0 - aBase;
  // Rim: opacity grows toward grazing angles (silhouettes read), never below a minimum fill.
  float fill = max(aBase, MIN_FILL_ALPHA);
  float a = aBase >= OPAQUE_ALPHA ? 1.0 : mix(fill, 1.0, RIM_OPACITY * rim);
  vec3 col = surfaceColour(vColor, n, vFlags, vWorldPos, t, rim);
  col = applyFog(col, distance(cameraPosition, vWorldPos));
  col = mix(col, sweepColor, 0.85 * band);
  a = mix(a, 1.0, band);
  if (vm.rim > 0.0) col = mix(col, peelRimCol, 0.85 * vm.rim);
  a *= vm.cover;
  if (hovered) {
    col = mix(col, hoverColor, 0.4) + 0.06;
    a = mix(a, 1.0, 0.35);
  }
#if defined( OIT )
  // Same premultiplied colour and alpha as the sorted path; only the output differs. The revealage
  // attachment holds -ln(1 - a), summed with the same ONE,ONE blend as the accumulation (see oitMath.ts).
  float w = oitWeight(1.0 / gl_FragCoord.w, a); // 1 / w_clip = view-space depth in metres
  oitAccum = vec4(col * a, a) * w;
  oitReveal = vec4(-log(1.0 - min(a, OIT_MAX_ALPHA)), 0.0, 0.0, 0.0);
#else
  gl_FragColor = vec4(col * a, a); // premultiplied
#endif

#else // PASS_FOCUS
  if (!focus) discard;
#if defined( DEPTH_ONLY )
  gl_FragColor = vec4(0.0);
#else
  if (!gl_FrontFacing) n = -n;
  vec3 col = shade(vColor, n) + 0.04;
  if (flagSelected(vFlags)) col = mix(col, vec3(1.0, 0.85, 0.2), 0.35);
  if (clipN > 0 && clipCapOn > 0.5 && !gl_FrontFacing && flagClosed(vFlags)) col = vmCapColour(clipCapCol);
  if (hovered) col = mix(col, hoverColor, 0.4) + 0.06;
  col *= 1.0 + focusBoost;
  gl_FragColor = vec4(col, 1.0);
#endif
#endif
}
`;

// ---------------------------------------------------------------- edge passes

export const EDGE_VERT = /* glsl */ `
${STATE_FETCH}
varying float vDist;
varying vec3 vWorldPos;
#if defined( EDGES_GLOW )
uniform vec2 glowOffset; // pixels
uniform vec2 glowRes;    // drawing buffer size in pixels
#endif

void main() {
  int f = fetchState();
  bool focus = (f & 1) != 0;
  bool hidden = (f & 2) != 0;
  vec4 wp = modelMatrix * vec4(position, 1.0);
  wp.xyz += gOffset;
  vWorldPos = wp.xyz;
  vec4 mv = viewMatrix * wp;
  vDist = length(mv.xyz);
  gl_Position = projectionMatrix * mv;
  bool reject = hidden;
#if defined( EDGES_GLOW )
  gl_Position.xy += glowOffset * (2.0 / glowRes) * gl_Position.w;
  reject = reject || vGlow < 0.5; // the focus may glow too (glow scope 'focus', plugins/cinematic.ts)
#elif defined( EDGES_FOCUS )
  reject = reject || !focus;
#else
  reject = reject || focus;
#endif
  if (reject) gl_Position = vec4(2.0, 2.0, 2.0, 1.0);
}
`;

export const EDGE_FRAG = /* glsl */ `
${GHOST_GLSL}
${FLAG_HELPERS}
${FOG_HELPERS}
${SWEEP_HELPERS}
${VIEWMODE_GLSL}
flat varying vec3 vColor;
flat varying float vAlpha;
flat varying float vFlags;
flat varying float vGlow;
flat varying float vHold;
flat varying float vElem;
flat varying float vVmOcc;
varying float vDist;
varying vec3 vWorldPos;
uniform float edgeAlpha;
uniform vec3 glowColor;
uniform float glowStrength;
uniform vec3 imgEdgeCol;   // imaging: faint tissue edges
uniform float imgEdgeAlpha;

void main() {
  if (flagHidden(vFlags)) discard;
  if (clipN > 0 && clipCut(vWorldPos)) discard; // section planes
  bool focus = flagFocus(vFlags);
#if defined( EDGES_IMG )
  if (focus) discard;
  float imgCover = 1.0;
  if (vmAny > 0.5) {
    VmOut vm = vmEval(vWorldPos, vAlpha, vVmOcc, false);
    imgCover = vm.cover;
    if (vm.cover < 0.01) discard;
  }
  float ia = imgEdgeAlpha * imgCover;
  gl_FragColor = vec4(imgEdgeCol * ia, ia);
#elif defined( EDGES_GLOW )
  if (vGlow < 0.5) discard;
  gl_FragColor = vec4(glowColor * glowStrength, glowStrength); // premultiplied; additive or over
#else
#if defined( EDGES_FOCUS )
  if (!focus) discard;
#else
  if (focus) discard;
#endif
  // View modes: edges follow the surfaces. No edges inside a cut; solid behind a plane; faint in a ghosted front.
  float aEl = vAlpha;
  float cover = 1.0;
  bool vmFront = false;
  float vmRim = 0.0;
#if defined( EDGES_CTX )
  if (vmAny > 0.5) {
    VmOut vm = vmEval(vWorldPos, vAlpha, vVmOcc, false);
    aEl = vm.alpha;
    cover = vm.cover;
    vmFront = vm.front;
    vmRim = vm.rim;
    if (cover < 0.01) discard;
  }
#endif
  float a = max(edgeAlpha, vAlpha);
  if (aEl != vAlpha) a = max(edgeAlpha, aEl);
  // Opaque elements: near-black tinted by the element colour. Ghosts: dark slate (the more transparent, the
  // more slate), which contrasts with the light background and with a dark graded fill alike.
  vec3 col = mix(vec3(0.07, 0.09, 0.12), vColor * 0.35, 0.5);
  col = mix(col, INK_COLOUR, clamp(1.0 - aEl, 0.0, 1.0));
  col = applyFog(col, vDist);
  if (sweepEnabled > 0.5 && vHold > 0.0 && aEl == vAlpha) {
    // Sweep reveal: the edges at the plane light up at full strength.
    float band = sweepBandAt(sweepDist(vWorldPos));
    col = mix(col, sweepColor, band);
    a = mix(a, 1.0, band);
  }
  if (vmFront) a *= 0.35;
  if (vmRim > 0.0) col = mix(col, peelRimCol, 0.85 * vmRim);
  a *= cover;
  if (vmHovered(vElem)) {
    col = mix(col, hoverColor, 0.75);
    a = 1.0;
  }
  gl_FragColor = vec4(col * a, a); // premultiplied
#endif
}
`;

// ---------------------------------------------------------------- OIT composite

/** Full-screen triangle (positions already in clip space). */
export const OIT_COMPOSITE_VERT = /* glsl */ `
void main() {
  gl_Position = vec4(position.xy, 0.0, 1.0);
}
`;

/**
 * Resolves the two OIT attachments over the frame (blend ONE, ONE_MINUS_SRC_ALPHA on premultiplied output):
 * final = avg * (1 - reveal) + frame * reveal, with reveal = exp(-sum of -ln(1 - a)).
 */
export const OIT_COMPOSITE_FRAG = /* glsl */ `
uniform sampler2D tAccum;
uniform sampler2D tReveal;
void main() {
  ivec2 p = ivec2(gl_FragCoord.xy);
  vec4 acc = texelFetch(tAccum, p, 0);
  float reveal = exp(-texelFetch(tReveal, p, 0).r);
  if (acc.a <= 0.0 && reveal >= 1.0) discard;
  // Half-float overflow of a very bright sum: fall back to a neutral average (the paper's guard).
  if (isinf(max(max(abs(acc.r), abs(acc.g)), abs(acc.b)))) acc.rgb = vec3(acc.a);
  vec3 avg = acc.rgb / max(acc.a, 1e-5);
  float cover = 1.0 - reveal;
  gl_FragColor = vec4(avg * cover, cover);
}
`;
