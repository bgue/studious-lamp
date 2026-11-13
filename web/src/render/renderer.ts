// WebGL renderer for the X-ray viewer: one merged geometry, three mesh passes and an edge pass,
// all driven by a per-element state texture.

import {
  AddEquation,
  AlwaysDepth,
  BufferAttribute,
  BufferGeometry,
  CustomBlending,
  GLSL3,
  HalfFloatType,
  LinearFilter,
  UnsignedByteType,
  OneFactor,
  OneMinusSrcAlphaFactor,
  Box3,
  Color,
  DataTexture,
  DoubleSide,
  FloatType,
  FrontSide,
  HemisphereLight,
  LessEqualDepth,
  LineSegments,
  Mesh,
  Object3D,
  NearestFilter,
  NormalBlending,
  NoBlending,
  PerspectiveCamera,
  RGBAFormat,
  RedFormat,
  Raycaster,
  Scene,
  ShaderMaterial,
  Sphere,
  Matrix4,
  Vector2,
  Vector3,
  Vector4,
  WebGLRenderer,
  WebGLRenderTarget,
  DirectionalLight,
  Ray,
} from 'three';
import type { IUniform, TextureDataType } from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import type { Classification, ElementId, RenderState } from '../types';
import { FLAG_FOCUS, FLAG_HIDDEN } from '../types';
import type { LoadedModel } from '../model/loader';
import { EDGE_FRAG, EDGE_VERT, MESH_FRAG, MESH_VERT, OIT_COMPOSITE_FRAG, OIT_COMPOSITE_VERT } from './shaders';
import { PEEL_FULLSCREEN_VERT, PEEL_INIT_FRAG, PEEL_MASK_FRAG, PEEL_STEP_FRAG } from './viewModeGlsl';
import { JFA_START, PEEL_EPS, PEEL_MAX_ELLIPSES, boxScreenEllipse, jfaSteps, peelCutsPoint } from '../viewModes/maths';
import type { FrontTreatment, Plane, ScreenEllipse } from '../viewModes/maths';
import { OPAQUE_ALPHA } from './ghostMath';
import type { OitWeightMode } from './oitMath';
import { IMG_BLUR_FRAG, IMG_COMPOSITE_FRAG, IMG_DECIMATE_FRAG, IMG_FULLSCREEN_VERT, IMG_SLAB_FRAG, IMG_THICK_FRAG } from './imagingGlsl';
import { PALETTE_TABLE, autoExposureFor, densityForMaterial, smoothExposure } from '../imaging/maths';
import { computeClosedFlags } from '../model/closedMesh';
import type { ImagingPalette, Slab } from '../imaging/maths';
import { MAX_CLIP_PLANES, normalizePlane, planeToVec4, pointKept } from '../section/maths';
import type { ClipPlane } from '../section/maths';

type Uniforms = Record<string, IUniform>;

/** Behind-only: what the shaders need (see viewModes/maths.ts for the plane convention). */
export interface BehindRender {
  plane: Plane;
  treatment: FrontTreatment;
  frontAlpha: number;
  keepXray: boolean;
  occludersOnly: boolean;
  capColour: readonly [number, number, number];
}

/** Partial peelback: radius is already scaled by the grow animation. */
export interface PeelRender {
  r0: number;
  slope: number;
  feather: number;
  /** Depth tolerance, metres. */
  eps?: number;
  rim: boolean;
  rimColour: readonly [number, number, number];
  capColour: readonly [number, number, number];
  solidOutside: boolean;
  occludersOnly: boolean;
  /** Focus element ids (for the CPU fallback and for picking). */
  focus: readonly number[];
}

export type PeelPath = 'off' | 'gpu-jfa' | 'cpu-ellipse';

/** Imaging style handed to the renderer (the plugin owns the settings; see imaging/config.ts). */
export interface ImagingRender {
  style: 'radiograph' | 'mri';
  palette: ImagingPalette;
  exposure: number;
  /** Measure the thickness distribution and scale the tissue exposure so its 90th percentile maps to about 0.8 (the exposure is then a multiplier). */
  autoExposure?: boolean;
  contrast: number;
  boneGlow: number;
  tissueEdges: boolean;
  /** MRI: the slab (imaging/maths.ts slabFor). Null: no slice (only the faint tissue shows). */
  slab: Slab | null;
  /** MRI: light the slab edges. */
  scan: boolean;
}

/** Resolution of the peel mask relative to the render target. */
const PEEL_SCALE = 0.5;

/**
 * Replaces the plain scene render (see setPostPipeline). The function is responsible for drawing the
 * frame to the canvas; it can call `r.renderScene()` for the normal draw and add to it.
 */
export type PostPipeline = (r: XrayRenderer) => void;

/** Screen-space offsets (pixels) of the four edge-glow copies. */
const GLOW_OFFSETS: Array<[number, number]> = [[-1.4, -1.4], [1.4, -1.4], [-1.4, 1.4], [1.4, 1.4]];

const MAX_TEX_WIDTH = 4096;

/** Bit 4 of the flags channel in the state texture: the element is a closed solid (set at upload, never in RenderState.flags). */
const CLOSED_BIT = 16;

const FOCUS_CATEGORY_COLORS: Array<[string, [number, number, number]]> = [
  ['Duct', [0.15, 0.6, 0.95]],
  ['Pipe', [0.2, 0.8, 0.4]],
  ['CableCarrier', [0.95, 0.85, 0.2]],
];

/** The field of view (radians) that the zoom limits of frameAll() are written for: the default perspective camera. */
const FRAME_REF_FOV = (45 * Math.PI) / 180;

export class XrayRenderer {
  readonly canvas: HTMLCanvasElement;
  readonly renderer: WebGLRenderer;
  readonly scene = new Scene();
  readonly camera: PerspectiveCamera;
  readonly controls: OrbitControls;

  /** Per-element state. Replaced (new arrays) by setModel: re-read `renderer.state` after calling it. */
  state: RenderState = { alpha: new Float32Array(0), color: new Float32Array(0), flags: new Uint8Array(0) };

  private loaded: LoadedModel | null = null;
  private baseColor = new Float32Array(0);
  private n = 0;
  private texWidth = 1;
  private dataA = new Float32Array(4);
  private dataB = new Float32Array(4);
  private dataC = new Float32Array(4);
  private texA: DataTexture;
  private texB: DataTexture;
  private texC: DataTexture;
  private offsetsDirty = false;
  /** Per element: 1 when the mesh is a closed solid (model/closedMesh.ts). Caps are painted for closed elements only. */
  private closed: Uint8Array = new Uint8Array(0);
  /** Time the closed-solid check took for the current model, ms. */
  closedMs = 0;
  private sweepHold: Float32Array | null = null;
  private dirty = true;
  private inFront = true;

  /** Lights are plain parameters for the shaders (hemisphere + one directional); plugins may adjust them. */
  readonly hemi = new HemisphereLight(0xdfe8f5, 0x6b6f78, 1.0);
  readonly sun = new DirectionalLight(0xffffff, 1.0);

  // Uniform objects shared by every material.
  private readonly shared: Uniforms;

  private opaqueMesh: Mesh | null = null;
  private ghostMesh: Mesh | null = null;
  private focusMesh: Mesh | null = null;
  private edgesCtx: LineSegments | null = null;
  private edgesFocus: LineSegments | null = null;
  private edgesGlow: LineSegments[] = [];
  private glowMask: Uint8Array | null = null;
  private post: PostPipeline | null = null;
  private focusOnlyStash: Array<[Object3D, boolean]> | null = null;
  private focusOnlyBackground: Scene['background'] = null;
  private readonly materials: ShaderMaterial[] = [];
  private focusMaterial: ShaderMaterial | null = null;

  // View modes (render/viewModeGlsl.ts, viewModes/maths.ts).
  private behind: BehindRender | null = null;
  private peel: PeelRender | null = null;
  private vmMask: Uint8Array | null = null;
  private vmGhost = false;
  private readonly peelScene = new Scene();
  private readonly peelPassScene = new Scene();
  private peelMaskMesh: Mesh | null = null;
  private peelQuad: Mesh | null = null;
  private peelInitMat: ShaderMaterial | null = null;
  private peelStepMat: ShaderMaterial | null = null;
  private peelMaskRT: WebGLRenderTarget | null = null;
  private peelA: WebGLRenderTarget | null = null;
  private peelB: WebGLRenderTarget | null = null;
  private peelFailure: string | null = null;
  private peelForceCpu = false;
  private peelStale = true;
  private peelSig = 0;
  private peelKey = new Float64Array(35);
  private peelPathNow: PeelPath = 'off';
  private peelDummy: DataTexture;
  private readonly peelFloatOk: boolean;
  private readonly viewProj = new Matrix4();
  private peelEllipses: ScreenEllipse[] = [];
  /** Counters for tests and benchmarks: how often the mask + flood ran. */
  peelRefreshes = 0;

  // Weighted blended OIT for the ghost pass (see render/oitMath.ts). The ghost pass of the main scene is
  // replaced by a full-screen composite (oitQuad, at the ghost's draw-order slot) of two attachments that
  // are rendered beforehand from a private scene: a colourless depth pre-pass of what is opaque, then the ghosts.
  /** Float colour buffers (EXT_color_buffer_float or half float) and two draw buffers are available. */
  readonly oitSupported: boolean;
  /** Which extension made OIT possible, for the status line. */
  readonly oitExtension: string;
  private oitOn = false;
  private oitFailure: string | null = null;
  private oitSamples: number;
  private oitMode: OitWeightMode = 'paper';
  private oitRT: WebGLRenderTarget | null = null;
  private oitRTSamples = 0;
  private readonly oitScene = new Scene();
  private oitDepthOpaque: Mesh | null = null;
  private oitDepthFocus: Mesh | null = null;
  private oitGhost: Mesh | null = null;
  private readonly oitQuad: Mesh;
  private readonly oitQuadMaterial: ShaderMaterial;
  private anyGhost = false;
  private readonly tmpColor = new Color();
  private readonly tmpSize = new Vector2();

  // Section clip planes (setClipPlanes) and imaging styles (setImaging; render/imagingGlsl.ts).
  private clipPlanes: ClipPlane[] | null = null;
  /** Incremented by every setClipPlanes call, so a plugin can tell that someone else changed the planes. */
  clipVersion = 0;
  private clipCapWanted = true;
  private imaging: ImagingRender | null = null;
  private imgFailure: string | null = null;
  private readonly imgBlend: boolean;
  private imgThickRT: WebGLRenderTarget | null = null;
  private imgSlabRT: WebGLRenderTarget | null = null;
  private imgGlow: WebGLRenderTarget[] = [];
  private imgSize = '';
  // Automatic exposure (imaging/maths.ts autoExposureFor): a 64 x 64 decimation of the thickness target is read back every
  // few frames; the smoothed factor multiplies the tissue exposure.
  private imgDecRT: WebGLRenderTarget | null = null;
  private imgDecMat: ShaderMaterial | null = null;
  private imgAutoE: number | null = null;
  private imgAutoFrame = 0;
  private imgAutoPending = false;
  private imgAutoGen = 0;
  private imgAutoFailure = '';
  private readonly imgAutoBuf = new Float32Array(64 * 64 * 4);
  private readonly imgAutoSamples = new Float32Array(64 * 64);
  /** Counters for tests: how many exposure measurements were taken. */
  imagingAutoMeasures = 0;
  private readonly imgThickScene = new Scene();
  private readonly imgSlabScene = new Scene();
  private readonly imgPassScene = new Scene();
  private readonly imgFinalScene = new Scene();
  private imgThickMesh: Mesh | null = null;
  private imgSlabMesh: Mesh | null = null;
  private imgEdges: LineSegments | null = null;
  private imgPassQuad: Mesh | null = null;
  private imgFinalQuad: Mesh | null = null;
  private imgBlurMat: ShaderMaterial | null = null;
  private imgCompositeMat: ShaderMaterial | null = null;
  private readonly imgSlabU: Uniforms = {
    imgSlab: { value: new Vector4(0, 1, 0, 0) },
    imgHalf: { value: 0.15 },
    imgScan: { value: 0 },
    imgCamSide: { value: new Vector3(1, 0, 0) },
  };
  /** Counters for tests and benchmarks: frames drawn through the imaging path. */
  imagingFrames = 0;

  // Focus drawn in front (depth Always) with section caps on: its own depth test, so only the nearest face of a focus solid
  // decides (see syncFocusDepth).
  private focusDepthReset: Mesh | null = null;
  private focusSelfDepth = false;
  private readonly tmpWorld = new Vector3();
  private readonly raycaster = new Raycaster();
  private readonly ndc = new Vector2();
  private readonly changeListeners = new Set<() => void>();
  private readonly onControlsChange = (): void => {
    for (const cb of this.changeListeners) cb();
  };

  constructor(canvas: HTMLCanvasElement) {
    this.canvas = canvas;
    this.renderer = new WebGLRenderer({ canvas, antialias: true, premultipliedAlpha: true });
    this.renderer.setPixelRatio(Math.min(typeof window !== 'undefined' ? window.devicePixelRatio : 1, 2));
    this.renderer.setClearColor(new Color(0xe9edf2), 1);

    this.camera = new PerspectiveCamera(45, 1, 0.1, 1000);
    this.camera.position.set(10, 8, 10);

    this.controls = new OrbitControls(this.camera, canvas);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.12;
    this.controls.addEventListener('change', this.onControlsChange);

    // OIT capability: float renderable (and blendable at half precision) colour buffers, and MRT.
    const ext = this.renderer.extensions;
    const gl = this.renderer.getContext();
    const maxDraw = Number(gl.getParameter((gl as WebGL2RenderingContext).MAX_DRAW_BUFFERS) ?? 1);
    this.oitExtension = ext.has('EXT_color_buffer_float') ? 'EXT_color_buffer_float' : ext.has('EXT_color_buffer_half_float') ? 'EXT_color_buffer_half_float' : '';
    this.oitSupported = this.oitExtension !== '' && maxDraw >= 2;
    // No MSAA on the OIT target by default: the context edges and the canvas's own MSAA already define the silhouettes
    // (compared on the procedural model: indistinguishable), and 4x float MRT roughly triples the OIT cost. setOitSamples(4) turns it on.
    this.oitSamples = 0;
    this.oitOn = this.oitSupported;
    this.oitQuadMaterial = new ShaderMaterial({
      vertexShader: OIT_COMPOSITE_VERT,
      fragmentShader: OIT_COMPOSITE_FRAG,
      uniforms: { tAccum: { value: null }, tReveal: { value: null } },
      transparent: true,
      blending: CustomBlending,
      blendSrc: OneFactor,
      blendDst: OneMinusSrcAlphaFactor,
      blendSrcAlpha: OneFactor,
      blendDstAlpha: OneMinusSrcAlphaFactor,
      depthTest: false,
      depthWrite: false,
      side: DoubleSide,
    });
    const tri = new BufferGeometry();
    tri.setAttribute('position', new BufferAttribute(new Float32Array([-1, -1, 0, 3, -1, 0, -1, 3, 0]), 3));
    this.oitQuad = new Mesh(tri, this.oitQuadMaterial);
    this.oitQuad.frustumCulled = false;
    this.oitQuad.visible = false;
    this.oitQuad.name = 'xray-oit-composite';
    this.scene.add(this.oitQuad);
    // Writes the far depth everywhere, no colour: drawn just before the focus when a section shows caps (syncFocusDepth).
    const resetMat = new ShaderMaterial({
      vertexShader: 'void main() { gl_Position = vec4(position.xy, 1.0, 1.0); }',
      fragmentShader: 'void main() { gl_FragColor = vec4(0.0); }',
      colorWrite: false,
      depthTest: true,
      depthFunc: AlwaysDepth,
      depthWrite: true,
      transparent: true,
      blending: NoBlending,
      side: DoubleSide,
    });
    this.focusDepthReset = new Mesh(tri, resetMat);
    this.focusDepthReset.frustumCulled = false;
    this.focusDepthReset.visible = false;
    this.focusDepthReset.name = 'xray-focus-depth-reset';
    this.scene.add(this.focusDepthReset);

    this.sun.position.set(-0.4, 0.8, 0.45).multiplyScalar(50);
    this.hemi.intensity = 0.62;
    this.sun.intensity = 0.55;
    this.scene.add(this.hemi, this.sun, this.sun.target);

    this.texA = this.makeTexture(this.dataA, 1, 1);
    this.texB = this.makeTexture(this.dataB, 1, 1);
    this.texC = this.makeTexture(this.dataC, 1, 1);
    this.shared = {
      stateA: { value: this.texA },
      stateB: { value: this.texB },
      stateC: { value: this.texC },
      planeNormal: { value: new Vector3(0, 0, -1) },
      planeOffset: { value: 0 },
      bandWidth: { value: 0.15 },
      sweepEnabled: { value: 0 },
      sweepColor: { value: new Vector3(0.55, 0.88, 1.0) },
      sweepAlphaMin: { value: 0.15 },
      focusCenter: { value: new Vector3() },
      focusRadius: { value: 0 },
      gradeStrength: { value: 0 },
      texWidth: { value: 1 },
      lightDir: { value: new Vector3(-0.4, 0.8, 0.45).normalize() },
      skyColor: { value: new Vector3() },
      groundColor: { value: new Vector3() },
      dirColor: { value: new Vector3() },
      ghostDesaturate: { value: 0.8 },
      edgeAlpha: { value: 0.8 },
      focusBoost: { value: 0 },
      fogColor: { value: new Vector3(0.9, 0.92, 0.95) },
      fogRange: { value: new Vector3(0, 1, 0) },
      glowColor: { value: new Vector3(1, 0.6, 0.15) },
      glowStrength: { value: 0.3 },
      glowRes: { value: new Vector2(1, 1) },
      oitFlat: { value: 0 },
      vmAny: { value: 0 },
      bhOn: { value: 0 },
      bhMode: { value: 0 },
      bhOccOnly: { value: 0 },
      bhKeep: { value: 0 },
      bhFrontAlpha: { value: 0.12 },
      bhPlane: { value: new Vector4(0, 0, -1, 0) },
      bhCap: { value: new Vector3(0.93, 0.78, 0.5) },
      peelOn: { value: 0 },
      peelOccOnly: { value: 0 },
      peelSolid: { value: 0 },
      peelRimOn: { value: 0 },
      peelCapOn: { value: 1 },
      peelP: { value: new Vector4(0.4, 0.6, 0.08, PEEL_EPS) },
      peelRimCol: { value: new Vector3(1, 0.55, 0.12) },
      peelCapCol: { value: new Vector3(0.93, 0.78, 0.5) },
      peelTex: { value: null },
      peelTexSize: { value: new Vector2(1, 1) },
      peelRes: { value: new Vector2(1, 1) },
      peelProjY: { value: 1 },
      peelEll: { value: Array.from({ length: PEEL_MAX_ELLIPSES }, () => new Vector4(0, 0, 1, 1)) },
      peelEllZ: { value: new Array<number>(PEEL_MAX_ELLIPSES).fill(0) },
      peelEllN: { value: 0 },
      hoverId: { value: -1 },
      hoverColor: { value: new Vector3(1, 0.85, 0.2) },
      clipN: { value: 0 },
      clipP: { value: Array.from({ length: MAX_CLIP_PLANES }, () => new Vector4(0, 0, 1, 0)) },
      clipCapOn: { value: 1 },
      clipCapCol: { value: new Vector3(0.93, 0.78, 0.5) },
      imgEdgeCol: { value: new Vector3(0.7, 0.8, 0.9) },
      imgEdgeAlpha: { value: 0.1 },
    };
    this.peelDummy = new DataTexture(new Float32Array(4), 1, 1, RGBAFormat, FloatType);
    this.peelDummy.needsUpdate = true;
    this.shared.peelTex!.value = this.peelDummy;
    this.peelFloatOk = ext.has('EXT_color_buffer_float');
    this.imgBlend = ext.has('EXT_color_buffer_float') && ext.has('EXT_float_blend');
    this.syncLights();
    this.resize();
  }

  // ------------------------------------------------------------------ model

  setModel(loaded: LoadedModel): void {
    this.disposeMeshes();
    this.loaded = loaded;
    const elements = loaded.model.elements;
    const n = elements.length;
    this.n = n;

    this.baseColor = new Float32Array(n * 3);
    const color = new Float32Array(n * 3);
    for (let i = 0; i < n; i++) {
      const c = elements[i]!.color;
      this.baseColor[i * 3] = color[i * 3] = c[0];
      this.baseColor[i * 3 + 1] = color[i * 3 + 1] = c[1];
      this.baseColor[i * 3 + 2] = color[i * 3 + 2] = c[2];
    }
    this.state = { alpha: new Float32Array(n).fill(1), color, flags: new Uint8Array(n) };

    this.texWidth = Math.max(1, Math.min(MAX_TEX_WIDTH, n));
    const height = Math.max(1, Math.ceil(n / this.texWidth));
    this.texA.dispose();
    this.texB.dispose();
    this.texC.dispose();
    this.dataA = new Float32Array(this.texWidth * height * 4);
    this.dataB = new Float32Array(this.texWidth * height * 4);
    this.dataC = new Float32Array(this.texWidth * height * 4);
    this.texA = this.makeTexture(this.dataA, this.texWidth, height);
    this.texB = this.makeTexture(this.dataB, this.texWidth, height);
    this.texC = this.makeTexture(this.dataC, this.texWidth, height);
    this.shared.stateA!.value = this.texA;
    this.shared.stateB!.value = this.texB;
    this.shared.stateC!.value = this.texC;
    // Imaging: the X-ray density of every element (from its material name) lives in stateC.a, uploaded once per model.
    for (let i = 0; i < n; i++) this.dataC[i * 4 + 3] = densityForMaterial(elements[i]!.material);
    this.texC.needsUpdate = true;
    // Caps (section, behind-only, peel, MRI slab) are painted for closed solids only: one edge-manifold check per model,
    // stored as bit 4 of the flags channel (stateB.r) at upload.
    const tc = performance.now();
    this.closed = computeClosedFlags(loaded.geometry.geometry.getAttribute('position').array, loaded.geometry.geometry.getIndex()!.array, loaded.geometry.ranges, loaded.geometry.vertexRanges);
    this.closedMs = performance.now() - tc;
    this.setClipPlanes(null); // the planes belong to the previous model
    this.shared.sweepEnabled!.value = 0;
    this.shared.gradeStrength!.value = 0;
    this.sweepHold = null;
    this.offsetsDirty = false;
    this.shared.texWidth!.value = this.texWidth;
    this.glowMask = null;

    this.buildMeshes(loaded);
    this.dirty = true;
    this.upload();
    this.frameAll();
  }

  private makeTexture(data: Float32Array, w: number, h: number): DataTexture {
    const t = new DataTexture(data, w, h, RGBAFormat, FloatType);
    t.minFilter = NearestFilter;
    t.magFilter = NearestFilter;
    t.generateMipmaps = false;
    t.flipY = false;
    t.needsUpdate = true;
    return t;
  }

  private meshMaterial(pass: 'PASS_OPAQUE' | 'PASS_GHOST' | 'PASS_FOCUS'): ShaderMaterial {
    const m = new ShaderMaterial({
      vertexShader: MESH_VERT,
      fragmentShader: MESH_FRAG,
      uniforms: this.shared,
      defines: { [pass]: '' },
    });
    if (pass === 'PASS_GHOST') {
      m.side = FrontSide; // backface culling on
      m.transparent = true;
      m.premultipliedAlpha = true;
      m.blending = NormalBlending;
      m.depthWrite = false;
      m.depthTest = true;
    } else {
      m.side = DoubleSide;
      m.transparent = false;
      m.blending = NoBlending;
      m.depthWrite = true;
      m.depthTest = true;
      // Keep coplanar edge lines from z-fighting with the faces.
      m.polygonOffset = true;
      m.polygonOffsetFactor = 1;
      m.polygonOffsetUnits = 1;
    }
    this.materials.push(m);
    return m;
  }

  /** Colourless copy of the opaque (or focus) pass for the OIT target's depth buffer: same vertex reject, same discards. */
  private depthMaterial(pass: 'PASS_OPAQUE' | 'PASS_FOCUS'): ShaderMaterial {
    const m = new ShaderMaterial({
      vertexShader: MESH_VERT,
      fragmentShader: MESH_FRAG,
      uniforms: this.shared,
      defines: { [pass]: '', DEPTH_ONLY: '' },
      side: DoubleSide,
      colorWrite: false,
      depthWrite: true,
      depthTest: true,
      polygonOffset: true,
      polygonOffsetFactor: 1,
      polygonOffsetUnits: 1,
    });
    this.materials.push(m);
    return m;
  }

  /** The ghost pass writing weighted accumulation (attachment 0) and revealage (1); both blend ONE, ONE. */
  private oitGhostMaterial(): ShaderMaterial {
    const m = new ShaderMaterial({
      vertexShader: MESH_VERT,
      fragmentShader: MESH_FRAG,
      uniforms: this.shared,
      defines: { PASS_GHOST: '', OIT: '' },
      glslVersion: GLSL3,
      side: FrontSide, // backface culling, as in the sorted path
      transparent: true,
      blending: CustomBlending,
      blendEquation: AddEquation,
      blendSrc: OneFactor,
      blendDst: OneFactor,
      blendEquationAlpha: AddEquation,
      blendSrcAlpha: OneFactor,
      blendDstAlpha: OneFactor,
      depthTest: true,
      depthWrite: false,
    });
    this.materials.push(m);
    return m;
  }

  private edgeMaterial(focus: boolean): ShaderMaterial {
    const m = new ShaderMaterial({
      vertexShader: EDGE_VERT,
      fragmentShader: EDGE_FRAG,
      uniforms: this.shared,
      defines: focus ? { EDGES_FOCUS: '' } : { EDGES_CTX: '' },
      transparent: true,
      premultipliedAlpha: true,
      blending: NormalBlending,
      depthTest: true,
      depthWrite: false,
    });
    this.materials.push(m);
    return m;
  }

  private glowMaterial(offset: [number, number]): ShaderMaterial {
    const m = new ShaderMaterial({
      vertexShader: EDGE_VERT,
      fragmentShader: EDGE_FRAG,
      uniforms: { ...this.shared, glowOffset: { value: new Vector2(offset[0], offset[1]) } },
      defines: { EDGES_GLOW: '' },
      transparent: true,
      premultipliedAlpha: true,
      blending: CustomBlending,
      blendSrc: OneFactor,
      blendDst: OneFactor,
      depthTest: true,
      depthWrite: false,
    });
    this.materials.push(m);
    return m;
  }

  private buildMeshes(loaded: LoadedModel): void {
    const g = loaded.geometry;
    const opaque = new Mesh(g.geometry, this.meshMaterial('PASS_OPAQUE'));
    const ghost = new Mesh(g.geometry, this.meshMaterial('PASS_GHOST'));
    this.focusMaterial = this.meshMaterial('PASS_FOCUS');
    const focus = new Mesh(g.geometry, this.focusMaterial);
    const edgesCtx = new LineSegments(g.edges, this.edgeMaterial(false));
    const edgesFocus = new LineSegments(g.edges, this.edgeMaterial(true));
    for (const o of [opaque, ghost, focus, edgesCtx, edgesFocus]) {
      o.frustumCulled = false;
      this.scene.add(o);
    }
    opaque.name = 'xray-opaque';
    ghost.name = 'xray-ghost';
    focus.name = 'xray-focus';
    edgesCtx.name = 'xray-edges';
    edgesFocus.name = 'xray-edges-focus';
    this.edgesGlow = GLOW_OFFSETS.map((o, i) => {
      const l = new LineSegments(g.edges, this.glowMaterial(o));
      l.frustumCulled = false;
      l.visible = false;
      l.renderOrder = 5;
      l.name = `xray-edges-glow-${i}`;
      this.scene.add(l);
      return l;
    });
    const dOpaque = new Mesh(g.geometry, this.depthMaterial('PASS_OPAQUE'));
    const dFocus = new Mesh(g.geometry, this.depthMaterial('PASS_FOCUS'));
    const oitGhost = new Mesh(g.geometry, this.oitGhostMaterial());
    dOpaque.renderOrder = 0;
    dFocus.renderOrder = 0;
    oitGhost.renderOrder = 1;
    for (const o of [dOpaque, dFocus, oitGhost]) {
      o.frustumCulled = false;
      this.oitScene.add(o);
    }
    dOpaque.name = 'xray-oit-depth-opaque';
    dFocus.name = 'xray-oit-depth-focus';
    oitGhost.name = 'xray-oit-ghost';
    this.oitDepthOpaque = dOpaque;
    this.oitDepthFocus = dFocus;
    this.oitGhost = oitGhost;
    // Peel mask: the focus set again, colour = view depth, in a private scene.
    const maskMat = new ShaderMaterial({
      vertexShader: MESH_VERT,
      fragmentShader: PEEL_MASK_FRAG,
      uniforms: this.shared,
      defines: { PASS_FOCUS: '' },
      side: DoubleSide,
      depthTest: true,
      depthWrite: true,
      blending: NoBlending,
    });
    this.materials.push(maskMat);
    const maskMesh = new Mesh(g.geometry, maskMat);
    maskMesh.frustumCulled = false;
    maskMesh.name = 'xray-peel-mask';
    this.peelScene.add(maskMesh);
    this.peelMaskMesh = maskMesh;
    this.opaqueMesh = opaque;
    this.ghostMesh = ghost;
    this.focusMesh = focus;
    this.edgesCtx = edgesCtx;
    this.edgesFocus = edgesFocus;
    this.buildImagingMeshes(g);
    this.applyPassOrder();
  }

  private disposeMeshes(): void {
    for (const o of [this.opaqueMesh, this.ghostMesh, this.focusMesh, this.edgesCtx, this.edgesFocus, ...this.edgesGlow]) {
      if (o) this.scene.remove(o);
    }
    this.edgesGlow = [];
    if (this.peelMaskMesh) this.peelScene.remove(this.peelMaskMesh);
    this.peelMaskMesh = null;
    this.peelStale = true;
    for (const o of [this.imgThickMesh, this.imgSlabMesh]) if (o) {
      this.imgThickScene.remove(o);
      this.imgSlabScene.remove(o);
    }
    if (this.imgEdges) this.imgFinalScene.remove(this.imgEdges);
    this.imgThickMesh = this.imgSlabMesh = null;
    this.imgEdges = null;
    for (const o of [this.oitDepthOpaque, this.oitDepthFocus, this.oitGhost]) if (o) this.oitScene.remove(o);
    this.oitDepthOpaque = this.oitDepthFocus = this.oitGhost = null;
    for (const m of this.materials) m.dispose();
    this.materials.length = 0;
    this.opaqueMesh = this.ghostMesh = this.focusMesh = this.edgesCtx = this.edgesFocus = null;
    this.focusMaterial = null;
  }

  /**
   * Draw order. inFront (default): opaque, ghost, context edges, focus (depth Always), focus edges.
   * Not inFront: the focus pass joins the opaque queue right after the opaque pass, so ghosts and
   * edges blend over it with correct depth.
   * (three draws all non-transparent materials before transparent ones, so the focus material is
   * flagged transparent in front mode, with blending off, to be sortable after the ghost pass.)
   */
  private applyPassOrder(): void {
    if (!this.opaqueMesh || !this.ghostMesh || !this.focusMesh || !this.edgesCtx || !this.edgesFocus || !this.focusMaterial) return;
    const fm = this.focusMaterial;
    fm.depthFunc = this.inFront && !this.focusSelfDepth ? AlwaysDepth : LessEqualDepth;
    fm.transparent = this.inFront;
    fm.needsUpdate = true;
    this.opaqueMesh.renderOrder = 0;
    if (this.inFront) {
      this.ghostMesh.renderOrder = 1;
      this.edgesCtx.renderOrder = 2;
      this.focusMesh.renderOrder = 3;
    } else {
      this.focusMesh.renderOrder = 1;
      this.ghostMesh.renderOrder = 2;
      this.edgesCtx.renderOrder = 3;
    }
    this.edgesFocus.renderOrder = 4;
    if (this.focusDepthReset) this.focusDepthReset.renderOrder = this.focusMesh.renderOrder - 0.5;
    // The OIT composite takes the ghost pass's slot, so edges and the (in front) focus draw over it.
    this.oitQuad.renderOrder = this.ghostMesh.renderOrder;
    if (this.oitDepthFocus) this.oitDepthFocus.visible = !this.inFront;
  }

  // ------------------------------------------------------------------ state

  markDirty(): void {
    this.dirty = true;
  }

  setInFront(b: boolean): void {
    this.inFront = b;
    this.applyPassOrder();
  }

  setEdgeAlpha(a: number): void {
    this.shared.edgeAlpha!.value = a;
  }

  setGhostDesaturate(d: number): void {
    this.shared.ghostDesaturate!.value = d;
  }

  /** Restore element colours from the model records (undo debugColorByBucket). */
  resetColors(): void {
    this.state.color.set(this.baseColor);
    this.dirty = true;
  }

  /**
   * Debug aid: focus = per-category colour, host = red, near = orange, far = grey, anything else = white.
   * Overwrites state.color; call resetColors() to undo.
   */
  debugColorByBucket(c: Classification): void {
    if (!this.loaded) return;
    const els = this.loaded.model.elements;
    const col = this.state.color;
    const set = (id: number, r: number, g: number, b: number): void => {
      col[id * 3] = r;
      col[id * 3 + 1] = g;
      col[id * 3 + 2] = b;
    };
    for (let i = 0; i < this.n; i++) set(i, 1, 1, 1);
    for (const id of c.far) set(id, 0.55, 0.55, 0.55);
    for (const id of c.near) set(id, 1.0, 0.6, 0.1);
    for (const id of c.host) set(id, 0.9, 0.15, 0.15);
    for (const id of c.focus) {
      const cls = els[id]?.ifcClass ?? '';
      const hit = FOCUS_CATEGORY_COLORS.find(([k]) => cls.includes(k));
      const rgb = hit ? hit[1] : [0.8, 0.3, 0.9];
      set(id, rgb[0]!, rgb[1]!, rgb[2]!);
    }
    this.dirty = true;
  }

  private upload(): void {
    if (!this.dirty) return;
    const { alpha, color, flags } = this.state;
    const A = this.dataA;
    const B = this.dataB;
    const glow = this.glowMask;
    const hold = this.sweepHold;
    const vmMask = this.vmMask && this.vmMask.length === this.n ? this.vmMask : null;
    const closed = this.closed.length === this.n ? this.closed : null;
    let ghost = false;
    let fsig = 0; // signature of what the peel mask depends on: the focus and hidden flags
    const peelBits = FLAG_FOCUS | FLAG_HIDDEN;
    for (let i = 0; i < this.n; i++) {
      const o = i * 4;
      A[o] = color[i * 3]!;
      A[o + 1] = color[i * 3 + 1]!;
      A[o + 2] = color[i * 3 + 2]!;
      const a = alpha[i]!;
      A[o + 3] = a;
      // alpha < 0 (types.HIDDEN) also means hidden
      B[o] = (a < 0 ? flags[i]! | FLAG_HIDDEN : flags[i]!) | (closed && closed[i] ? CLOSED_BIT : 0);
      fsig = (Math.imul(fsig, 31) + (B[o]! & peelBits)) | 0;
      B[o + 1] = glow ? glow[i]! : 0; // edge-glow membership
      B[o + 2] = hold ? hold[i]! : 0; // sweep hold alpha (0: not in the sweep)
      B[o + 3] = vmMask ? vmMask[i]! : 1; // view-mode occluder mask
      if (!ghost && a >= 0 && a < OPAQUE_ALPHA && (flags[i]! & (FLAG_FOCUS | FLAG_HIDDEN)) === 0) ghost = true;
    }
    this.anyGhost = ghost;
    if (fsig !== this.peelSig) {
      this.peelSig = fsig;
      this.peelStale = true;
    }
    this.texA.needsUpdate = true;
    this.texB.needsUpdate = true;
    this.dirty = false;
  }

  // ------------------------------------------------------------------ frame

  private syncLights(): void {
    const u = this.shared;
    const sky = new Color(this.hemi.color).multiplyScalar(this.hemi.intensity);
    const gnd = new Color(this.hemi.groundColor).multiplyScalar(this.hemi.intensity);
    const dir = new Color(this.sun.color).multiplyScalar(this.sun.intensity);
    (u.skyColor!.value as Vector3).set(sky.r, sky.g, sky.b);
    (u.groundColor!.value as Vector3).set(gnd.r, gnd.g, gnd.b);
    (u.dirColor!.value as Vector3).set(dir.r, dir.g, dir.b);
    (u.lightDir!.value as Vector3).copy(this.sun.position).sub(this.sun.target.position).normalize();
  }

  /**
   * Test hook: draw the order-independent ghosts also inside an XR session. Off by default and not meant for use: the OIT
   * target is one single-view texture, while an XR frame draws two views, which on a real headset may sit in different
   * textures or array layers (see docs-features/webxr.md, "Order-independent ghosts").
   */
  xrForceOit = false;

  /** True while a WebXR session presents (three then renders every pass into the XR framebuffer with the stereo camera). */
  get xrPresenting(): boolean {
    return this.renderer.xr.enabled && this.renderer.xr.isPresenting;
  }

  /**
   * What an XR frame leaves out of what is switched on, one phrase each (for the XR status line). The passes that draw through
   * private single-view targets cannot share the stereo framebuffer: imaging, order-independent ghosts, the peel window and
   * the post effects. Behind-only, sections, caps and the sorted ghost pass are drawn per eye as usual.
   */
  xrFallbacks(): string[] {
    const out: string[] = [];
    if (this.imaging) out.push(`imaging ${this.imaging.style} drawn as standard`);
    if (this.post) out.push('post effects off');
    if (this.oitOn) out.push('ghosts use the sorted pass, not order-independent blending');
    if (this.peel) out.push('peelback window off');
    return out;
  }

  /** World position of the head inside an XR session (set by the XR plugin each frame, null outside a session). */
  xrHeadWorld: Vector3 | null = null;

  /** World position of the camera: the camera's own position, or the head position when it sits in an XR rig. */
  cameraWorldPosition(out: Vector3 = new Vector3()): Vector3 {
    // In a session the head (between the eyes) is what looks: the XR plugin sets it every frame. The user camera itself sits at the left eye.
    if (this.xrHeadWorld && this.xrPresenting) return out.copy(this.xrHeadWorld);
    if (this.camera.parent) {
      this.camera.updateWorldMatrix(true, false);
      return out.setFromMatrixPosition(this.camera.matrixWorld);
    }
    return out.copy(this.camera.position);
  }

  /** Tell the camera listeners (the sightline scheduler) that the camera moved without the orbit controls (WebXR head motion). */
  notifyCameraChanged(): void {
    for (const cb of this.changeListeners) cb();
  }

  render(): void {
    const xr = this.xrPresenting;
    if (!xr) this.controls.update();
    this.upload();
    if (this.offsetsDirty) {
      this.texC.needsUpdate = true;
      this.offsetsDirty = false;
      this.peelStale = true;
    }
    this.syncLights();
    // Post effects are screen-space and single-view: not in an XR session (the plain stereo draw runs instead).
    if (this.post && !xr) this.post(this);
    else this.renderScene();
  }

  /**
   * The scene draw to the current render target (the canvas by default). With OIT on, the ghosts are first
   * accumulated into the OIT target, then composited over the opaque scene at the ghost pass's draw-order
   * slot, so context edges and the focus pass still draw over them. Works into the canvas and into any
   * render target (also multisampled): the composite is an ordinary draw into the current target.
   */
  renderScene(): void {
    // In an XR session every renderer.render call draws with the stereo camera into the XR framebuffer, so the passes that
    // go through private single-view targets (imaging, OIT, peel flood) are off: the sorted ghost path draws instead.
    const xr = this.xrPresenting;
    if (this.imaging && !xr && !this.focusOnlyStash && this.renderImaging(this.imaging)) return;
    if (!this.focusOnlyStash) {
      this.prepareViewModes();
      const oit = this.oitOn && (!xr || this.xrForceOit);
      const compose = oit && (this.anyGhost || this.vmGhost) && this.renderOitTarget();
      if (this.ghostMesh) this.ghostMesh.visible = !oit;
      this.oitQuad.visible = compose;
    }
    this.renderer.render(this.scene, this.camera);
  }

  // ------------------------------------------------------------------ order-independent transparency

  /** Whether the ghost pass is drawn order-independently (needs oitSupported). */
  get oitEnabled(): boolean {
    return this.oitOn;
  }

  /**
   * Switch weighted blended OIT on or off, and optionally set the depth weight. Accepts a boolean, or an
   * object `{ orderIndependent?, depthWeight? }` (depthWeight: 'paper' | 'flat', or a number where 0 = flat
   * and anything else = paper, as in getOit()). Returns the resulting on/off state (false when unsupported).
   */
  setOit(on: boolean | { orderIndependent?: boolean; depthWeight?: number | OitWeightMode }): boolean {
    let flag: boolean | undefined;
    if (typeof on === 'boolean') flag = on;
    else {
      flag = on.orderIndependent;
      const w = on.depthWeight;
      if (typeof w === 'number') this.setOitWeight(w > 0 ? 'paper' : 'flat');
      else if (w === 'paper' || w === 'flat') this.setOitWeight(w);
    }
    if (flag !== undefined) {
      const want = flag && this.oitSupported && this.oitFailure === null;
      if (want !== this.oitOn) {
        this.oitOn = want;
        if (!want) this.freeOitTarget();
      }
    }
    return this.oitOn;
  }

  /** Current OIT settings (depthWeight 1 = 'paper', 0 = 'flat'). */
  getOit(): { orderIndependent: boolean; depthWeight: number } {
    return { orderIndependent: this.oitOn, depthWeight: this.oitMode === 'flat' ? 0 : 1 };
  }

  /** 'paper': w = alpha * clamp(0.03 / (1e-5 + (z/200)^4), 1e-2, 3e3); 'flat': w = alpha. */
  setOitWeight(mode: OitWeightMode): void {
    this.oitMode = mode;
    this.shared.oitFlat!.value = mode === 'flat' ? 1 : 0;
  }

  get oitWeightMode(): OitWeightMode {
    return this.oitMode;
  }

  /** MSAA samples of the OIT target (0 = none). Capped by the context's maximum. */
  setOitSamples(n: number): void {
    const v = Math.max(0, Math.min(Math.floor(n), this.renderer.capabilities.maxSamples));
    if (v === this.oitSamples) return;
    this.oitSamples = v;
    this.freeOitTarget();
  }

  get oitSampleCount(): number {
    return this.oitRT ? this.oitRTSamples : this.oitSamples;
  }

  /** One line for the UI: float-buffer availability and the current state. */
  get oitStatus(): string {
    if (!this.oitSupported) return 'unavailable: no float colour buffers (OIT off)';
    if (this.oitFailure) return `${this.oitExtension}; failed: ${this.oitFailure}`;
    const n = this.oitRT ? this.oitRTSamples : this.oitSamples;
    return `${this.oitExtension}; MRT, ${n > 0 ? `${n}x MSAA` : 'no MSAA'}`;
  }

  private freeOitTarget(): void {
    this.oitRT?.dispose();
    this.oitRT = null;
    this.oitQuadMaterial.uniforms.tAccum!.value = null;
    this.oitQuadMaterial.uniforms.tReveal!.value = null;
  }

  /** Build an OIT target; null when the framebuffer is not complete in this context. */
  private tryOitTarget(w: number, h: number, samples: number, rgbaReveal: boolean): WebGLRenderTarget | null {
    const rt = new WebGLRenderTarget(w, h, { count: 2, type: HalfFloatType, format: RGBAFormat, depthBuffer: true, samples });
    rt.textures[0]!.minFilter = rt.textures[0]!.magFilter = NearestFilter;
    rt.textures[1]!.minFilter = rt.textures[1]!.magFilter = NearestFilter;
    if (!rgbaReveal) rt.textures[1]!.format = RedFormat;
    rt.textures[0]!.generateMipmaps = rt.textures[1]!.generateMipmaps = false;
    const r = this.renderer;
    const gl = r.getContext();
    const prev = r.getRenderTarget();
    while (gl.getError() !== gl.NO_ERROR) { /* drain */ }
    r.setRenderTarget(rt);
    const ok = gl.checkFramebufferStatus(gl.FRAMEBUFFER) === gl.FRAMEBUFFER_COMPLETE && gl.getError() === gl.NO_ERROR;
    r.setRenderTarget(prev);
    if (!ok) {
      rt.dispose();
      return null;
    }
    this.oitRTSamples = samples;
    return rt;
  }

  /**
   * Render the ghosts into the OIT target at the size of the current render target. Returns false when the
   * target cannot be created (OIT is then switched off for good, with the reason in oitStatus).
   */
  private renderOitTarget(): boolean {
    const r = this.renderer;
    const dst = r.getRenderTarget();
    let w: number;
    let h: number;
    if (dst) {
      w = dst.width;
      h = dst.height;
    } else {
      r.getDrawingBufferSize(this.tmpSize);
      w = Math.max(1, Math.floor(this.tmpSize.x));
      h = Math.max(1, Math.floor(this.tmpSize.y));
    }
    if (!this.oitRT) {
      const tries: Array<[number, boolean]> = [[this.oitSamples, false], [0, false], [0, true]];
      let rt: WebGLRenderTarget | null = null;
      for (const [samples, rgba] of tries) {
        rt = this.tryOitTarget(w, h, samples, rgba);
        if (rt) break;
      }
      if (!rt) {
        this.oitFailure = 'incomplete framebuffer for RGBA16F + R16F';
        this.oitOn = false;
        console.warn(`OIT disabled: ${this.oitFailure}`);
        return false;
      }
      this.oitRT = rt;
    } else if (this.oitRT.width !== w || this.oitRT.height !== h) {
      this.oitRT.setSize(w, h);
    }
    const rt = this.oitRT;
    this.oitQuadMaterial.uniforms.tAccum!.value = rt.textures[0];
    this.oitQuadMaterial.uniforms.tReveal!.value = rt.textures[1];

    const autoClear = r.autoClear;
    const clearAlpha = r.getClearAlpha();
    r.getClearColor(this.tmpColor);
    r.setRenderTarget(rt);
    r.setClearColor(0x000000, 0);
    r.autoClear = true;
    r.render(this.oitScene, this.camera);
    r.setClearColor(this.tmpColor, clearAlpha);
    r.autoClear = autoClear;
    r.setRenderTarget(dst);
    return true;
  }

  /**
   * Route render() through a custom pipeline (post-processing). Pass null to restore the plain draw.
   * The renderer knows nothing about what the pipeline does.
   */
  setPostPipeline(fn: PostPipeline | null): void {
    this.post = fn;
  }

  /** Emissive boost on the focus pass (0 = off). Used by the selective bloom mask render. */
  setFocusBoost(v: number): void {
    this.shared.focusBoost!.value = v;
  }

  /**
   * Show only the focus mesh (no background, no other scene objects), or restore the previous
   * visibility. For rendering a mask of the focus set alone.
   */
  setFocusOnly(on: boolean): void {
    if (on) {
      if (this.focusOnlyStash) return;
      this.focusOnlyStash = this.scene.children.map((c) => [c, c.visible] as [Object3D, boolean]);
      for (const c of this.scene.children) if (c !== this.focusMesh) c.visible = false;
      this.focusOnlyBackground = this.scene.background;
      this.scene.background = null;
    } else if (this.focusOnlyStash) {
      for (const [c, v] of this.focusOnlyStash) c.visible = v;
      this.focusOnlyStash = null;
      this.scene.background = this.focusOnlyBackground;
      this.focusOnlyBackground = null;
    }
  }

  /** Distance fog toward `color` (linear 0..1 rgb): none up to `near`, `maxMix` at `far`. maxMix 0 disables it. */
  setFog(color: [number, number, number], near: number, far: number, maxMix: number): void {
    (this.shared.fogColor!.value as Vector3).set(color[0], color[1], color[2]);
    (this.shared.fogRange!.value as Vector3).set(near, Math.max(far, near + 1e-3), maxMix);
  }

  /**
   * Draw the edges of `ids` a second time, four times, offset by about a pixel in screen space, as a
   * cheap halo. Additive by default. Pass null to turn it off (the glow meshes are then not drawn).
   */
  setEdgeGlow(ids: ReadonlySet<number> | null, color: [number, number, number] = [1, 0.6, 0.15], opts: { strength?: number; additive?: boolean } = {}): void {
    const on = ids !== null && ids.size > 0;
    if (on) {
      const mask = this.glowMask && this.glowMask.length === this.n ? this.glowMask : new Uint8Array(this.n);
      mask.fill(0);
      for (const id of ids!) if (id >= 0 && id < this.n) mask[id] = 1;
      this.glowMask = mask;
    } else {
      this.glowMask = null;
    }
    (this.shared.glowColor!.value as Vector3).set(color[0], color[1], color[2]);
    this.shared.glowStrength!.value = opts.strength ?? 0.3;
    const additive = opts.additive ?? true;
    for (const l of this.edgesGlow) {
      l.visible = on;
      const m = l.material as ShaderMaterial;
      const bd = additive ? OneFactor : OneMinusSrcAlphaFactor;
      if (m.blendDst !== bd) {
        m.blendDst = bd;
        m.needsUpdate = true;
      }
    }
    this.dirty = true;
  }

  // ------------------------------------------------------------------ view modes

  /**
   * Behind-only view: per fragment, context in front of `plane` (perpendicular to the view, through the focus's
   * nearest point) is cut, ghosted or cut with a cap; context behind it is drawn solid. null turns it off.
   * Elements split between passes: the opaque pass keeps the behind part, the ghost pass the front part (ghost treatment).
   */
  setBehind(p: BehindRender | null): void {
    this.behind = p;
    const u = this.shared;
    u.bhOn!.value = p ? 1 : 0;
    if (p) {
      (u.bhPlane!.value as Vector4).set(p.plane.nx, p.plane.ny, p.plane.nz, p.plane.d);
      u.bhMode!.value = p.treatment === 'cut' ? 0 : p.treatment === 'ghost' ? 1 : 2;
      u.bhFrontAlpha!.value = p.frontAlpha;
      u.bhKeep!.value = p.keepXray ? 1 : 0;
      u.bhOccOnly!.value = p.occludersOnly ? 1 : 0;
      (u.bhCap!.value as Vector3).set(p.capColour[0], p.capColour[1], p.capColour[2]);
    }
    this.vmGhost = (p !== null && p.treatment === 'ghost') || (this.peel !== null && this.peel.feather > 0);
    u.vmAny!.value = p || this.peel ? 1 : 0;
  }

  /**
   * Partial peelback: a window through the context in front of the focus, shaped like the focus silhouette
   * (low-resolution mask with depth, jump-flooded to the nearest focus pixel and its depth; see viewModeGlsl.ts).
   * null turns it off.
   */
  setPeel(p: PeelRender | null): void {
    this.peel = p;
    const u = this.shared;
    if (p) {
      (u.peelP!.value as Vector4).set(p.r0, p.slope, p.feather, p.eps ?? PEEL_EPS);
      u.peelSolid!.value = p.solidOutside ? 1 : 0;
      u.peelOccOnly!.value = p.occludersOnly ? 1 : 0;
      u.peelRimOn!.value = p.rim ? 1 : 0;
      (u.peelRimCol!.value as Vector3).set(p.rimColour[0], p.rimColour[1], p.rimColour[2]);
      (u.peelCapCol!.value as Vector3).set(p.capColour[0], p.capColour[1], p.capColour[2]);
    } else {
      u.peelOn!.value = 0;
      this.peelPathNow = 'off';
    }
    this.vmGhost = (this.behind !== null && this.behind.treatment === 'ghost') || (p !== null && p.feather > 0);
    u.vmAny!.value = this.behind || p ? 1 : 0;
  }

  /** 1 = occluder (host, near, far that blocks), per element; used by the 'occluders only' scope. null: every element counts. */
  setViewModeMask(mask: Uint8Array | null): void {
    this.vmMask = mask;
    this.dirty = true;
  }

  /** Which peel implementation ran on the last frame: 'gpu-jfa' (mask + jump flooding), 'cpu-ellipse' (fallback) or 'off'. */
  get peelPath(): PeelPath {
    return this.peelPathNow;
  }

  /** Why the GPU path is not used ('' when it is available). */
  get peelGpuStatus(): string {
    if (this.peelForceCpu) return 'CPU path forced';
    if (!this.peelFloatOk) return 'no EXT_color_buffer_float';
    return this.peelFailure ?? '';
  }

  /** Force the CPU ellipse fallback ('cpu') or let the renderer pick ('auto'). */
  setPeelPath(mode: 'auto' | 'cpu'): void {
    this.peelForceCpu = mode === 'cpu';
    this.peelStale = true;
  }

  /**
   * Tint one element (and brighten its edges) without touching the state flags. null clears. Cheap: a uniform
   * compared against the element id in the fragment shaders. Takes effect on the next frame.
   */
  setHoverHighlight(id: number | null, color?: [number, number, number]): void {
    this.shared.hoverId!.value = id === null || id < 0 ? -1 : id;
    if (color) (this.shared.hoverColor!.value as Vector3).set(color[0], color[1], color[2]);
  }

  private targetSize(): { w: number; h: number } {
    const dst = this.renderer.getRenderTarget();
    if (dst) return { w: dst.width, h: dst.height };
    this.renderer.getDrawingBufferSize(this.tmpSize);
    return { w: Math.max(1, Math.floor(this.tmpSize.x)), h: Math.max(1, Math.floor(this.tmpSize.y)) };
  }

  /** Per-frame setup of the view-mode uniforms; runs the peel mask and flood when the camera or the focus changed. */
  private prepareViewModes(): void {
    const u = this.shared;
    if (this.clipPlanes) {
      // Caps only show a cut when the viewer looks in from the removed side of some plane; from the kept side a visible
      // back face is an open or flipped mesh, not a revealed interior.
      const c = this.cameraWorldPosition(this.tmpWorld);
      u.clipCapOn!.value = this.clipCapWanted && !pointKept(this.clipPlanes, [c.x, c.y, c.z]) ? 1 : 0;
    }
    this.syncFocusDepth();
    const peel = this.peel;
    // The peel window is screen-space (a mask target and a flood in the camera's image): not drawn in an XR session.
    if (!peel || !this.peelMaskMesh || peel.focus.length === 0 || this.xrPresenting) {
      u.peelOn!.value = 0;
      this.peelPathNow = 'off';
      u.vmAny!.value = this.behind ? 1 : 0;
      return;
    }
    const { w, h } = this.targetSize();
    (u.peelRes!.value as Vector2).set(w, h);
    u.peelProjY!.value = this.camera.projectionMatrix.elements[5];
    this.camera.updateMatrixWorld();
    let gpu = this.peelFloatOk && !this.peelForceCpu && this.peelFailure === null;
    if (gpu) gpu = this.refreshPeelMask(w, h, peel);
    if (gpu) {
      u.peelOn!.value = 1;
      this.peelPathNow = 'gpu-jfa';
    } else {
      this.fillEllipses(w, h, peel);
      u.peelOn!.value = 2;
      this.peelPathNow = 'cpu-ellipse';
    }
    u.vmAny!.value = 1;
  }

  /**
   * With caps on, the focus (drawn in front with depth Always) needs a depth test of its own: otherwise the back faces of a
   * focus solid overpaint its front faces in draw order and show the cap colour over the whole element. A depth reset
   * just before the focus pass and LessEqual for it keep the focus in front of everything and let the nearest face decide.
   * Only while a section with caps is on and the camera looks in from the cut side; else the pass is the unchanged one.
   */
  private syncFocusDepth(): void {
    const want = this.inFront && this.clipPlanes !== null && this.shared.clipCapOn!.value > 0.5;
    if (want === this.focusSelfDepth) return;
    this.focusSelfDepth = want;
    if (this.focusMaterial) this.focusMaterial.depthFunc = this.inFront && !want ? AlwaysDepth : LessEqualDepth;
    if (this.focusDepthReset) this.focusDepthReset.visible = want;
  }

  private freePeelTargets(): void {
    this.peelMaskRT?.dispose();
    this.peelA?.dispose();
    this.peelB?.dispose();
    this.peelMaskRT = this.peelA = this.peelB = null;
    this.shared.peelTex!.value = this.peelDummy;
    this.peelStale = true;
  }

  private makeFloatTarget(w: number, h: number, depth: boolean): WebGLRenderTarget | null {
    const rt = new WebGLRenderTarget(w, h, { type: FloatType, format: RGBAFormat, depthBuffer: depth, samples: 0 });
    rt.texture.minFilter = rt.texture.magFilter = NearestFilter;
    rt.texture.generateMipmaps = false;
    const r = this.renderer;
    const gl = r.getContext();
    const prev = r.getRenderTarget();
    while (gl.getError() !== gl.NO_ERROR) { /* drain */ }
    r.setRenderTarget(rt);
    const ok = gl.checkFramebufferStatus(gl.FRAMEBUFFER) === gl.FRAMEBUFFER_COMPLETE && gl.getError() === gl.NO_ERROR;
    r.setRenderTarget(prev);
    if (!ok) {
      rt.dispose();
      return null;
    }
    return rt;
  }

  /** Mask + jump flood into this.peelTex. False when float targets cannot be built (the CPU path then runs). */
  private refreshPeelMask(w: number, h: number, peel: PeelRender): boolean {
    const mw = Math.max(1, Math.ceil(w * PEEL_SCALE));
    const mh = Math.max(1, Math.ceil(h * PEEL_SCALE));
    if (!this.peelMaskRT || this.peelMaskRT.width !== mw || this.peelMaskRT.height !== mh) {
      this.freePeelTargets();
      const m = this.makeFloatTarget(mw, mh, true);
      const a = m ? this.makeFloatTarget(mw, mh, false) : null;
      const b = a ? this.makeFloatTarget(mw, mh, false) : null;
      if (!m || !a || !b) {
        m?.dispose();
        a?.dispose();
        this.peelFailure = 'incomplete framebuffer for RGBA32F';
        console.warn(`Peelback GPU path disabled: ${this.peelFailure}`);
        return false;
      }
      this.peelMaskRT = m;
      this.peelA = a;
      this.peelB = b;
    }
    // Skip the work when nothing it depends on changed (camera, projection, target size, element state, focus set).
    const key = this.peelKey;
    const vi = this.camera.matrixWorldInverse.elements;
    const pr = this.camera.projectionMatrix.elements;
    let changed = this.peelStale;
    for (let i = 0; i < 16; i++) {
      if (key[i] !== vi[i]) changed = true;
      if (key[16 + i] !== pr[i]) changed = true;
    }
    let sig = peel.focus.length;
    for (const id of peel.focus) sig = (sig * 31 + id) % 1000003;
    if (key[32] !== w || key[33] !== h || key[34] !== sig) changed = true;
    if (!changed && this.shared.peelTex!.value !== this.peelDummy) return true;
    for (let i = 0; i < 16; i++) {
      key[i] = vi[i]!;
      key[16 + i] = pr[i]!;
    }
    key[32] = w;
    key[33] = h;
    key[34] = sig;
    this.peelStale = false;
    this.peelRefreshes++;

    const r = this.renderer;
    const dst = r.getRenderTarget();
    const autoClear = r.autoClear;
    const clearAlpha = r.getClearAlpha();
    r.getClearColor(this.tmpColor);
    r.autoClear = true;
    r.setClearColor(0x000000, 0);
    r.setRenderTarget(this.peelMaskRT);
    r.render(this.peelScene, this.camera);
    r.autoClear = false;

    if (!this.peelQuad) {
      this.peelInitMat = new ShaderMaterial({ vertexShader: PEEL_FULLSCREEN_VERT, fragmentShader: PEEL_INIT_FRAG, uniforms: { tMask: { value: null } }, depthTest: false, depthWrite: false, blending: NoBlending, side: DoubleSide });
      this.peelStepMat = new ShaderMaterial({ vertexShader: PEEL_FULLSCREEN_VERT, fragmentShader: PEEL_STEP_FRAG, uniforms: { tSeed: { value: null }, jump: { value: 1 } }, depthTest: false, depthWrite: false, blending: NoBlending, side: DoubleSide });
      this.peelQuad = new Mesh(this.oitQuad.geometry, this.peelInitMat);
      this.peelQuad.frustumCulled = false;
      this.peelPassScene.add(this.peelQuad);
    }
    this.peelInitMat!.uniforms.tMask!.value = this.peelMaskRT.texture;
    this.peelQuad.material = this.peelInitMat!;
    let src = this.peelA!;
    let other = this.peelB!;
    r.setRenderTarget(src);
    r.render(this.peelPassScene, this.camera);
    this.peelQuad.material = this.peelStepMat!;
    for (const jump of jfaSteps(JFA_START)) {
      this.peelStepMat!.uniforms.tSeed!.value = src.texture;
      this.peelStepMat!.uniforms.jump!.value = jump;
      r.setRenderTarget(other);
      r.render(this.peelPassScene, this.camera);
      const t = src;
      src = other;
      other = t;
    }
    r.setClearColor(this.tmpColor, clearAlpha);
    r.autoClear = autoClear;
    r.setRenderTarget(dst);
    this.shared.peelTex!.value = src.texture;
    (this.shared.peelTexSize!.value as Vector2).set(mw, mh);
    return true;
  }

  /** Screen ellipses (pixels, bottom-left origin) of the focus elements, at most PEEL_MAX_ELLIPSES, the largest first. */
  private computeEllipses(w: number, h: number, focus: readonly number[]): ScreenEllipse[] {
    const els = this.loaded?.model.elements;
    if (!els) return [];
    this.camera.updateMatrixWorld();
    this.viewProj.multiplyMatrices(this.camera.projectionMatrix, this.camera.matrixWorldInverse);
    const out: ScreenEllipse[] = [];
    for (const id of focus) {
      const b = els[id]?.bounds;
      if (!b) continue;
      const e = boxScreenEllipse(this.viewProj.elements, this.camera.matrixWorldInverse.elements, b, w, h);
      if (e) out.push(e);
    }
    out.sort((a, b) => b.ax * b.ay - a.ax * a.ay);
    return out.slice(0, PEEL_MAX_ELLIPSES);
  }

  private fillEllipses(w: number, h: number, peel: PeelRender): void {
    const list = this.computeEllipses(w, h, peel.focus);
    this.peelEllipses = list;
    const u = this.shared;
    const ell = u.peelEll!.value as Vector4[];
    const z = u.peelEllZ!.value as number[];
    list.forEach((e, i) => {
      ell[i]!.set(e.cx, e.cy, e.ax, e.ay);
      z[i] = e.z;
    });
    u.peelEllN!.value = list.length;
  }

  /** Is the surface point hit by the picker removed by a view mode (cut, or almost transparent)? Approximate for the peel. */
  private cutByViewMode(id: ElementId, point: Vector3): boolean {
    const b = this.behind;
    const p = this.xrPresenting ? null : this.peel; // the peel window is not drawn in an XR session, so it does not cut picks either
    if (!b && !p) return false;
    const flags = this.state.flags[id]!;
    if ((flags & FLAG_FOCUS) !== 0) return false;
    const occ = this.vmMask ? this.vmMask[id] === 1 : true;
    if (b && (!b.occludersOnly || occ)) {
      const front = b.plane.nx * point.x + b.plane.ny * point.y + b.plane.nz * point.z < b.plane.d;
      if (front && (b.treatment !== 'ghost' || b.frontAlpha < 0.3)) return true;
    }
    if (p && p.focus.length > 0 && (!p.occludersOnly || occ)) {
      const { w, h } = this.targetSize();
      if (!this.pickEllipseFresh) {
        this.peelEllipses = this.computeEllipses(w, h, p.focus);
        this.pickEllipseFresh = true;
      }
      const v = point.clone().applyMatrix4(this.camera.matrixWorldInverse);
      const c = point.clone().applyMatrix4(this.viewProj);
      const wClip = point.x * this.viewProj.elements[3]! + point.y * this.viewProj.elements[7]! + point.z * this.viewProj.elements[11]! + this.viewProj.elements[15]!;
      if (wClip > 1e-4) {
        const x = (c.x * 0.5 + 0.5) * w;
        const y = (c.y * 0.5 + 0.5) * h;
        const maths = { r0: p.r0, slope: p.slope, feather: p.feather, eps: p.eps ?? PEEL_EPS };
        if (peelCutsPoint(this.peelEllipses, x, y, -v.z, maths, (this.camera.fov * Math.PI) / 180, h)) return true;
      }
    }
    return false;
  }
  private pickEllipseFresh = false;


  // ------------------------------------------------------------------ section clip planes

  /**
   * Section planes (up to MAX_CLIP_PLANES = 8; extra ones are ignored). Each plane's normal points to the KEPT half-space
   * (viewer coordinates). Applied per fragment in every pass (opaque, ghost / OIT, focus, edges, glow, imaging), so elements
   * are split exactly. With `cap` (default true when the options are omitted) the back faces a cut reveals are painted flat
   * in `capColor` with a light hatch; the cap colour is kept when not given. null or [] removes the planes.
   */
  setClipPlanes(planes: ReadonlyArray<{ normal: ArrayLike<number>; point: ArrayLike<number> }> | null, opts?: { cap?: boolean; capColor?: ArrayLike<number> }): void {
    const list: ClipPlane[] = [];
    for (const p of planes ?? []) {
      const n = normalizePlane({ normal: [p.normal[0]!, p.normal[1]!, p.normal[2]!], point: [p.point[0]!, p.point[1]!, p.point[2]!] });
      if (n && list.length < MAX_CLIP_PLANES) list.push(n);
    }
    this.clipPlanes = list.length ? list : null;
    const u = this.shared;
    u.clipN!.value = list.length;
    const arr = u.clipP!.value as Vector4[];
    list.forEach((p, i) => {
      const v = planeToVec4(p);
      arr[i]!.set(v[0], v[1], v[2], v[3]);
    });
    this.clipCapWanted = opts?.cap !== false;
    u.clipCapOn!.value = this.clipCapWanted ? 1 : 0;
    if (opts?.capColor) (u.clipCapCol!.value as Vector3).set(opts.capColor[0]!, opts.capColor[1]!, opts.capColor[2]!);
    this.clipVersion++;
    this.peelStale = true;
    this.dirty = true;
  }

  /** The active section planes (unit normals, viewer coordinates), or null. */
  getClipPlanes(): Array<{ normal: [number, number, number]; point: [number, number, number] }> | null {
    return this.clipPlanes ? this.clipPlanes.map((p) => ({ normal: [...p.normal], point: [...p.point] })) : null;
  }

  /** True while section caps are painted (a section with caps is on and the camera looks in from the cut side). */
  get clipCapsDrawn(): boolean {
    return this.clipPlanes !== null && this.shared.clipCapOn!.value > 0.5;
  }

  /** True when a view mode (behind cut, peel) is on, so surface hits may be cut away (see viewModeCut). */
  get viewModeCuts(): boolean {
    return this.behind !== null || (this.peel !== null && !this.xrPresenting);
  }

  private cutCamKey = new Float64Array(17).fill(NaN);

  /**
   * Is the surface point of element `id` removed by a view mode (the same test a pick applies)? For rays other than a click (the
   * attachment projection and occlusion tests): the peel ellipses are kept while the camera and the focus stay the same.
   */
  viewModeCut(id: ElementId, point: Vector3): boolean {
    if (!this.viewModeCuts) return false;
    const e = this.camera.matrixWorldInverse.elements;
    const k = this.cutCamKey;
    let same = this.pickEllipseFresh;
    for (let i = 0; i < 16 && same; i++) if (k[i] !== e[i]) same = false;
    const focus = this.peel?.focus.length ?? -1;
    if (k[16] !== focus) same = false;
    if (!same) {
      this.pickEllipseFresh = false;
      for (let i = 0; i < 16; i++) k[i] = e[i]!;
      k[16] = focus;
    }
    return this.cutByViewMode(id, point);
  }

  /** Is the surface point removed by a section plane (picking skips such hits)? */
  private cutByClip(point: Vector3): boolean {
    return this.clipPlanes !== null && !pointKept(this.clipPlanes, [point.x, point.y, point.z]);
  }

  // ------------------------------------------------------------------ imaging styles

  /** Radiograph / MRI rendering needs float colour buffers; false otherwise (the standard renderer is used). */
  get imagingSupported(): boolean {
    return this.oitExtension !== '' && this.imgFailure === null;
  }

  /** One line for the UI. */
  get imagingStatus(): string {
    if (this.oitExtension === '') return 'unavailable: no float colour buffers';
    if (this.imgFailure) return `failed: ${this.imgFailure}`;
    const auto = this.imaging?.autoExposure && this.imaging.style === 'radiograph' ? (this.imgAutoFailure ? `, auto exposure off (${this.imgAutoFailure})` : this.imgAutoE !== null ? `, auto exposure x${this.imgAutoE.toFixed(2)}` : ', auto exposure measuring') : '';
    return `${this.imgBlend ? 'float32' : 'float16 (no EXT_float_blend: less precise)'} thickness target${this.imaging ? `, ${this.imaging.style} on` : ''}${auto}`;
  }

  /** The factor the automatic exposure currently applies to the tissue exposure (1 when it is off or has not measured yet). */
  get imagingAutoExposure(): number {
    return this.imaging?.autoExposure && this.imaging.style === 'radiograph' && !this.imgAutoFailure ? this.imgAutoE ?? 1 : 1;
  }

  /** Draw the frame as a radiograph or an MRI slice instead of the normal scene. null restores the normal renderer exactly. */
  setImaging(p: ImagingRender | null): void {
    this.imaging = p;
    if (!p) this.freeImaging();
  }

  private buildImagingMeshes(g: LoadedModel['geometry']): void {
    const thickMat = new ShaderMaterial({
      vertexShader: MESH_VERT,
      fragmentShader: IMG_THICK_FRAG,
      uniforms: this.shared,
      side: DoubleSide,
      transparent: true,
      blending: CustomBlending,
      blendEquation: AddEquation,
      blendSrc: OneFactor,
      blendDst: OneFactor,
      blendEquationAlpha: AddEquation,
      blendSrcAlpha: OneFactor,
      blendDstAlpha: OneFactor,
      depthTest: false,
      depthWrite: false,
    });
    const slabMat = new ShaderMaterial({
      vertexShader: MESH_VERT,
      fragmentShader: IMG_SLAB_FRAG,
      uniforms: { ...this.shared, ...this.imgSlabU },
      side: DoubleSide,
      blending: NoBlending,
      depthTest: true,
      depthWrite: true,
    });
    const edgeMat = new ShaderMaterial({
      vertexShader: EDGE_VERT,
      fragmentShader: EDGE_FRAG,
      uniforms: this.shared,
      defines: { EDGES_IMG: '' },
      transparent: true,
      premultipliedAlpha: true,
      blending: NormalBlending,
      depthTest: false,
      depthWrite: false,
    });
    this.materials.push(thickMat, slabMat, edgeMat);
    const thick = new Mesh(g.geometry, thickMat);
    const slab = new Mesh(g.geometry, slabMat);
    const edges = new LineSegments(g.edges, edgeMat);
    for (const o of [thick, slab, edges]) o.frustumCulled = false;
    thick.name = 'xray-img-thickness';
    slab.name = 'xray-img-slab';
    edges.name = 'xray-img-edges';
    edges.renderOrder = 1;
    this.imgThickScene.add(thick);
    this.imgSlabScene.add(slab);
    this.imgFinalScene.add(edges);
    this.imgThickMesh = thick;
    this.imgSlabMesh = slab;
    this.imgEdges = edges;
  }

  private makeImgTarget(w: number, h: number, type: TextureDataType, depth: boolean, samples: number, linear: boolean): WebGLRenderTarget | null {
    const rt = new WebGLRenderTarget(w, h, { type, format: RGBAFormat, depthBuffer: depth, samples });
    rt.texture.minFilter = rt.texture.magFilter = linear ? LinearFilter : NearestFilter;
    rt.texture.generateMipmaps = false;
    const r = this.renderer;
    const gl = r.getContext();
    const prev = r.getRenderTarget();
    while (gl.getError() !== gl.NO_ERROR) { /* drain */ }
    r.setRenderTarget(rt);
    const ok = gl.checkFramebufferStatus(gl.FRAMEBUFFER) === gl.FRAMEBUFFER_COMPLETE && gl.getError() === gl.NO_ERROR;
    r.setRenderTarget(prev);
    if (!ok) {
      rt.dispose();
      return null;
    }
    return rt;
  }

  private freeImaging(): void {
    this.imgThickRT?.dispose();
    this.imgSlabRT?.dispose();
    for (const t of this.imgGlow) t.dispose();
    this.imgDecRT?.dispose();
    this.imgDecRT = null;
    this.imgThickRT = this.imgSlabRT = null;
    this.imgGlow = [];
    this.imgSize = '';
    this.imgAutoE = null;
    this.imgAutoFrame = 0;
    this.imgAutoPending = false;
    this.imgAutoGen++;
  }

  /** (Re)create the imaging targets for a render target of w x h. False when they cannot be built. */
  private ensureImagingTargets(w: number, h: number): boolean {
    const key = `${w}x${h}`;
    if (this.imgThickRT && this.imgSize === key) return true;
    this.freeImaging();
    const thick = this.makeImgTarget(w, h, this.imgBlend ? FloatType : HalfFloatType, false, 0, false);
    const slab = thick ? this.makeImgTarget(w, h, UnsignedByteType, true, Math.min(4, this.renderer.capabilities.maxSamples), false) ?? this.makeImgTarget(w, h, UnsignedByteType, true, 0, false) : null;
    const hw = Math.max(1, Math.ceil(w / 2));
    const hh = Math.max(1, Math.ceil(h / 2));
    const qw = Math.max(1, Math.ceil(w / 4));
    const qh = Math.max(1, Math.ceil(h / 4));
    const sizes: Array<[number, number]> = [[hw, hh], [hw, hh], [qw, qh], [qw, qh]];
    const glow: WebGLRenderTarget[] = [];
    if (thick && slab) for (const [gw, gh] of sizes) {
      const t = this.makeImgTarget(gw, gh, HalfFloatType, false, 0, true);
      if (!t) break;
      glow.push(t);
    }
    if (!thick || !slab || glow.length < 4) {
      thick?.dispose();
      slab?.dispose();
      for (const t of glow) t.dispose();
      this.imgFailure = 'incomplete framebuffer for the imaging targets';
      console.warn(`Imaging disabled: ${this.imgFailure}`);
      return false;
    }
    this.imgThickRT = thick;
    this.imgSlabRT = slab;
    this.imgGlow = glow;
    this.imgSize = key;
    return true;
  }

  private ensureImagingMaterials(): void {
    if (this.imgPassQuad) return;
    const tri = this.oitQuad.geometry;
    this.imgBlurMat = new ShaderMaterial({
      vertexShader: IMG_FULLSCREEN_VERT,
      fragmentShader: IMG_BLUR_FRAG,
      uniforms: { tSrc: { value: null }, srcScale: { value: 1 }, stepPx: { value: new Vector2(1, 0) }, srcMode: { value: 0 }, imgExposure: { value: 1 } },
      depthTest: false,
      depthWrite: false,
      blending: NoBlending,
      side: DoubleSide,
    });
    this.imgCompositeMat = new ShaderMaterial({
      vertexShader: IMG_FULLSCREEN_VERT,
      fragmentShader: IMG_COMPOSITE_FRAG,
      uniforms: {
        tThick: { value: null },
        tSlab: { value: null },
        tGlowA: { value: null },
        tGlowB: { value: null },
        imgRes: { value: new Vector2(1, 1) },
        imgStyle: { value: 0 },
        imgExposure: { value: 1 },
        imgTissueExposure: { value: 1 },
        imgContrast: { value: 1 },
        imgBoneGlow: { value: 1 },
        imgGlowOn: { value: 0 },
        palBg: { value: new Vector3() },
        palTissue: { value: new Vector3() },
        palBone: { value: new Vector3() },
        palGlow: { value: new Vector3() },
      },
      depthTest: false,
      depthWrite: false,
      blending: NoBlending,
      side: DoubleSide,
    });
    this.imgDecMat = new ShaderMaterial({
      vertexShader: IMG_FULLSCREEN_VERT,
      fragmentShader: IMG_DECIMATE_FRAG,
      uniforms: { tSrc: { value: null } },
      depthTest: false,
      depthWrite: false,
      blending: NoBlending,
      side: DoubleSide,
    });
    this.imgPassQuad = new Mesh(tri, this.imgBlurMat);
    this.imgPassQuad.frustumCulled = false;
    this.imgPassScene.add(this.imgPassQuad);
    this.imgFinalQuad = new Mesh(tri, this.imgCompositeMat);
    this.imgFinalQuad.frustumCulled = false;
    this.imgFinalQuad.renderOrder = 0;
    this.imgFinalScene.add(this.imgFinalQuad);
  }

  /**
   * Automatic exposure: decimate the thickness target to a 64 x 64 grid (one sample per cell), read it back asynchronously (a
   * fenced pixel buffer, no pipeline stall; the first time at once, then every 4th frame) and smooth the factor that maps the 90th percentile of the non-empty
   * context thickness to 0.8. Needs EXT_color_buffer_float for the readback; without it the factor stays 1 (the status line says so).
   */
  private measureAutoExposure(): void {
    if (this.imgAutoFailure) return;
    if (!this.peelFloatOk) {
      this.imgAutoFailure = 'no EXT_color_buffer_float';
      return;
    }
    const first = this.imgAutoE === null;
    if (this.imgAutoPending || (!first && ++this.imgAutoFrame % 4 !== 0)) return;
    if (!this.imgDecRT) {
      this.imgDecRT = this.makeImgTarget(64, 64, FloatType, false, 0, false);
      if (!this.imgDecRT) {
        this.imgAutoFailure = 'incomplete 64 x 64 float target';
        return;
      }
    }
    const r = this.renderer;
    const dec = this.imgDecRT;
    const mat = this.imgDecMat!;
    mat.uniforms.tSrc!.value = this.imgThickRT!.texture;
    this.imgPassQuad!.material = mat;
    r.setRenderTarget(dec);
    r.render(this.imgPassScene, this.camera);
    const buf = this.imgAutoBuf;
    const apply = (): void => {
      const samples = this.imgAutoSamples;
      for (let i = 0; i < samples.length; i++) samples[i] = buf[i * 4]!;
      this.imagingAutoMeasures++;
      const e = autoExposureFor(samples);
      if (e !== null) this.imgAutoE = smoothExposure(this.imgAutoE, e);
      else if (this.imgAutoE === null) this.imgAutoE = 1; // an empty frame: no factor yet, but stop asking synchronously
    };
    this.imgAutoPending = true;
    const gen = this.imgAutoGen;
    r.readRenderTargetPixelsAsync(dec, 0, 0, 64, 64, buf).then(
      () => {
        if (gen !== this.imgAutoGen) return;
        this.imgAutoPending = false;
        apply();
      },
      () => {
        if (gen !== this.imgAutoGen) return;
        this.imgAutoPending = false;
        this.imgAutoFailure = 'readback failed';
      },
    );
  }

  /**
   * The imaging frame: thickness pass (all visible elements, additive), the MRI slab pass, the bone glow blur and
   * the full-screen composite into the current target. Returns false (standard renderer) when unsupported.
   */
  private renderImaging(im: ImagingRender): boolean {
    if (!this.imagingSupported || !this.imgThickMesh) return false;
    const { w, h } = this.targetSize();
    if (!this.ensureImagingTargets(w, h)) return false;
    this.ensureImagingMaterials();
    this.prepareViewModes();
    this.camera.updateMatrixWorld();

    const pal = PALETTE_TABLE[im.palette];
    const mri = im.style === 'mri';
    const slab = mri ? im.slab : null;
    const cm = this.imgCompositeMat!;
    const cu = cm.uniforms;
    (cu.palBg!.value as Vector3).set(...pal.bg);
    (cu.palTissue!.value as Vector3).set(...pal.tissue);
    (cu.palBone!.value as Vector3).set(...pal.bone);
    (cu.palGlow!.value as Vector3).set(...pal.glow);
    cu.imgStyle!.value = mri ? 1 : 0;
    cu.imgExposure!.value = im.exposure;
    cu.imgTissueExposure!.value = im.exposure;
    cu.imgContrast!.value = im.contrast;
    cu.imgBoneGlow!.value = im.boneGlow;
    (cu.imgRes!.value as Vector2).set(w, h);
    const glowOn = im.boneGlow > 0;
    cu.imgGlowOn!.value = glowOn ? 1 : 0;
    (this.shared.imgEdgeCol!.value as Vector3).set(...pal.edge);
    this.shared.imgEdgeAlpha!.value = 0.1;
    if (this.imgEdges) this.imgEdges.visible = im.tissueEdges && !mri;
    if (slab) {
      const su = this.imgSlabU;
      (su.imgSlab!.value as Vector4).set(slab.normal[0], slab.normal[1], slab.normal[2], slab.centre);
      su.imgHalf!.value = slab.half;
      su.imgScan!.value = im.scan ? 1 : 0;
      const cp = this.camera.position;
      (su.imgCamSide!.value as Vector3).x = slab.normal[0] * cp.x + slab.normal[1] * cp.y + slab.normal[2] * cp.z - slab.centre >= 0 ? 1 : -1;
    }
    if (this.imgSlabMesh) this.imgSlabMesh.visible = slab !== null;

    const r = this.renderer;
    const dst = r.getRenderTarget();
    const autoClear = r.autoClear;
    const clearAlpha = r.getClearAlpha();
    r.getClearColor(this.tmpColor);
    r.autoClear = true;
    r.setClearColor(0x000000, 0);

    r.setRenderTarget(this.imgThickRT);
    r.render(this.imgThickScene, this.camera);
    if (im.autoExposure && !mri) {
      this.measureAutoExposure();
      cu.imgTissueExposure!.value = im.exposure * (this.imgAutoFailure ? 1 : this.imgAutoE ?? 1);
    }
    if (mri) {
      r.setRenderTarget(this.imgSlabRT);
      r.render(this.imgSlabScene, this.camera);
    }
    if (glowOn) {
      const bm = this.imgBlurMat!;
      const bu = bm.uniforms;
      bu.imgExposure!.value = im.exposure;
      this.imgPassQuad!.material = bm;
      const [a1, a2, b1, b2] = this.imgGlow as [WebGLRenderTarget, WebGLRenderTarget, WebGLRenderTarget, WebGLRenderTarget];
      const blur = (src: WebGLRenderTarget, dstRT: WebGLRenderTarget, scale: number, sx: number, sy: number, mode: number): void => {
        bu.tSrc!.value = src.texture;
        bu.srcScale!.value = scale;
        (bu.stepPx!.value as Vector2).set(sx, sy);
        bu.srcMode!.value = mode;
        r.setRenderTarget(dstRT);
        r.render(this.imgPassScene, this.camera);
      };
      blur(this.imgThickRT!, a1, 2, 2, 0, 0);
      blur(a1, a2, 1, 0, 1, 1);
      blur(a2, b1, 2, 4, 0, 1);
      blur(b1, b2, 1, 0, 2, 1);
      cu.tGlowA!.value = a2.texture;
      cu.tGlowB!.value = b2.texture;
    }
    cu.tThick!.value = this.imgThickRT!.texture;
    cu.tSlab!.value = this.imgSlabRT!.texture;

    r.setClearColor(this.tmpColor, clearAlpha);
    r.setRenderTarget(dst);
    r.render(this.imgFinalScene, this.camera);
    r.autoClear = autoClear;
    this.imagingFrames++;
    return true;
  }

  // ------------------------------------------------------------------ sweep, depth grade, offsets

  /**
   * Sweep reveal. `hold[id]` is the alpha an element had before the selection (0 = not part of the
   * sweep); fragments on the far side of the plane (not reached yet) are drawn with that alpha (opaque
   * ones by the opaque pass), fragments on the camera side with their real alpha, pulled toward
   * `alphaMin` just behind the plane front, with a bright band of `band` metres at the plane.
   * Pass null to end the sweep (everything returns to the normal alphas).
   */
  setSweep(hold: Float32Array | null, alphaMin = 0.15, band = 0.15): void {
    this.sweepHold = hold;
    this.shared.sweepEnabled!.value = hold ? 1 : 0;
    this.shared.sweepAlphaMin!.value = alphaMin;
    this.shared.bandWidth!.value = Math.max(band, 1e-4);
    this.dirty = true;
  }

  /** Move the sweep plane: points p with dot(normal, p) - offset <= 0 have been reached. */
  setSweepPlane(normal: Vector3, offset: number): void {
    (this.shared.planeNormal!.value as Vector3).copy(normal);
    this.shared.planeOffset!.value = offset;
  }

  /** Depth-graded ghosting: tint ghosts the further they sit in front of `center` along the view. radius <= 0 or strength 0 disables it. */
  setDepthGrade(center: Vector3 | null, radius: number, strength: number): void {
    if (center) (this.shared.focusCenter!.value as Vector3).copy(center);
    this.shared.focusRadius!.value = center ? Math.max(radius, 0) : 0;
    this.shared.gradeStrength!.value = center ? strength : 0;
  }

  /** Bumped by every element offset change (setElementOffset, clearElementOffsets): overlays redraw anchors on it. */
  offsetsVersion = 0;

  /** World-space displacement of one element in every pass (exploded context). Picking and the BVH use the undisplaced geometry. */
  setElementOffset(id: number, x: number, y: number, z: number): void {
    if (id < 0 || id >= this.n) return;
    const o = id * 4;
    const C = this.dataC;
    if (C[o] === x && C[o + 1] === y && C[o + 2] === z) return;
    C[o] = x;
    C[o + 1] = y;
    C[o + 2] = z;
    this.offsetsDirty = true;
    this.offsetsVersion++;
  }

  /** The displacement set by setElementOffset (zeros when none). Overlays use it to follow exploded elements. */
  elementOffset(id: number): [number, number, number] {
    if (id < 0 || id >= this.n) return [0, 0, 0];
    const C = this.dataC;
    return [C[id * 4]!, C[id * 4 + 1]!, C[id * 4 + 2]!];
  }

  clearElementOffsets(): void {
    const C = this.dataC;
    for (let i = 0; i < C.length; i += 4) C[i] = C[i + 1] = C[i + 2] = 0; // keep the density in the alpha channel
    this.offsetsDirty = true;
    this.offsetsVersion++;
  }

  resize(): void {
    // three refuses (and warns) to resize while an XR session presents; the session owns the framebuffer size.
    if (this.xrPresenting) return;
    const w = this.canvas.clientWidth || this.canvas.width || 1;
    const h = this.canvas.clientHeight || this.canvas.height || 1;
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    const db = this.renderer.getDrawingBufferSize(new Vector2());
    (this.shared.glowRes!.value as Vector2).set(Math.max(1, db.x), Math.max(1, db.y));
  }

  /** Fit the camera to the union of element bounds. */
  frameAll(): void {
    const box = this.loaded ? this.loaded.geometry.totalBounds() : new Box3();
    if (box.isEmpty()) {
      box.set(new Vector3(-5, -5, -5), new Vector3(5, 5, 5));
    }
    const sphere = box.getBoundingSphere(new Sphere());
    const r = Math.max(sphere.radius, 1e-3);
    const fov = (this.camera.fov * Math.PI) / 180;
    const fit = Math.min(fov, 2 * Math.atan(Math.tan(fov / 2) * this.camera.aspect));
    const dist = (r / Math.sin(fit / 2)) * 1.05;
    // The zoom range is a multiple of the fit distance of the normal 45 degree view. In the orthographic approximation
    // (a 2 degree field of view) the camera sits about 24 times further away, so the range scales with it: a fixed r * 20
    // would pull Home in to a third of the model and stop the wheel from zooming out to the whole of it.
    const fitRef = Math.min(FRAME_REF_FOV, 2 * Math.atan(Math.tan(FRAME_REF_FOV / 2) * this.camera.aspect));
    const scale = Math.max(1, dist / ((r / Math.sin(fitRef / 2)) * 1.05));
    const dir = new Vector3(0.7, 0.55, 0.85).normalize();
    this.camera.position.copy(sphere.center).addScaledVector(dir, dist);
    this.camera.near = Math.max(r * 0.005, 1e-3);
    this.controls.target.copy(sphere.center);
    this.controls.minDistance = r * 0.02 * scale;
    this.controls.maxDistance = r * 20 * scale;
    this.camera.far = Math.max(dist + r * 50, this.controls.maxDistance + r * 2);
    this.camera.updateProjectionMatrix();
    this.controls.update();
  }

  onCameraChange(cb: () => void): () => void {
    this.changeListeners.add(cb);
    return () => {
      this.changeListeners.delete(cb);
    };
  }

  // ------------------------------------------------------------------ picking

  /**
   * Nearest eligible element under the NDC point. Walks hits front to back with `raycastFirst`
   * (firstHitOnly) and skips hidden elements and, unless focus, elements whose alpha < 0.3, so
   * the user can click through ghosts. Returns null on a miss.
   */
  pick(ndcX: number, ndcY: number): ElementId | null {
    if (!this.loaded) return null;
    this.ndc.set(ndcX, ndcY);
    this.camera.updateMatrixWorld();
    this.raycaster.setFromCamera(this.ndc, this.camera);
    return this.pickWithRay(this.raycaster.ray);
  }

  /** Same eligibility rules as pick(), for a world ray (a WebXR controller ray, or any other pointer). */
  pickRay(origin: Vector3, direction: Vector3): ElementId | null {
    if (!this.loaded) return null;
    this.camera.updateMatrixWorld();
    return this.pickWithRay(new Ray(origin.clone(), direction.clone().normalize()));
  }

  /** Distance from the ray origin to the surface of the last element a pick returned (world units). */
  lastPickDistance = 0;

  private pickWithRay(ray: Ray): ElementId | null {
    if (!this.loaded) return null;
    const g = this.loaded.geometry;
    const bvh = g.bvh;
    const { alpha, flags } = this.state;
    let near = 0;
    this.pickEllipseFresh = false;
    for (let iter = 0; iter < 512; iter++) {
      const hit = bvh.raycastFirst(ray, DoubleSide, near, Infinity);
      if (!hit || hit.faceIndex == null) return null;
      const id = g.elementOfTriangle(hit.faceIndex);
      if (id >= 0) {
        const f = flags[id]!;
        const a = alpha[id]!;
        const hidden = (f & FLAG_HIDDEN) !== 0 || a < 0;
        const clickThrough = (f & FLAG_FOCUS) === 0 && a < 0.3;
        if (!hidden && !clickThrough && !this.cutByViewMode(id, hit.point) && !this.cutByClip(hit.point)) {
          this.lastPickDistance = hit.distance;
          return id;
        }
      }
      near = hit.distance + 1e-4;
    }
    return null;
  }

  /** Per-element closed-solid flags of the current model (1 = closed). Caps are painted for these only. */
  get closedFlags(): Uint8Array {
    return this.closed;
  }

  dispose(): void {
    this.controls.removeEventListener('change', this.onControlsChange);
    this.controls.dispose();
    this.disposeMeshes();
    this.freeOitTarget();
    this.freePeelTargets();
    this.freeImaging();
    this.peelInitMat?.dispose();
    this.peelStepMat?.dispose();
    this.peelDummy.dispose();
    this.oitQuadMaterial.dispose();
    (this.focusDepthReset?.material as ShaderMaterial | undefined)?.dispose();
    this.oitQuad.geometry.dispose();
    this.texA.dispose();
    this.texB.dispose();
    this.texC.dispose();
    this.renderer.dispose();
  }
}
