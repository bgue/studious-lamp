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
  Vector2,
  Vector3,
  WebGLRenderer,
  WebGLRenderTarget,
  DirectionalLight,
} from 'three';
import type { IUniform } from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import type { Classification, ElementId, RenderState } from '../types';
import { FLAG_FOCUS, FLAG_HIDDEN } from '../types';
import type { LoadedModel } from '../model/loader';
import { EDGE_FRAG, EDGE_VERT, MESH_FRAG, MESH_VERT, OIT_COMPOSITE_FRAG, OIT_COMPOSITE_VERT } from './shaders';
import { OPAQUE_ALPHA } from './ghostMath';
import type { OitWeightMode } from './oitMath';

type Uniforms = Record<string, IUniform>;

/**
 * Replaces the plain scene render (see setPostPipeline). The function is responsible for drawing the
 * frame to the canvas; it can call `r.renderScene()` for the normal draw and add to it.
 */
export type PostPipeline = (r: XrayRenderer) => void;

/** Screen-space offsets (pixels) of the four edge-glow copies. */
const GLOW_OFFSETS: Array<[number, number]> = [[-1.4, -1.4], [1.4, -1.4], [-1.4, 1.4], [1.4, 1.4]];

const MAX_TEX_WIDTH = 4096;

const FOCUS_CATEGORY_COLORS: Array<[string, [number, number, number]]> = [
  ['Duct', [0.15, 0.6, 0.95]],
  ['Pipe', [0.2, 0.8, 0.4]],
  ['CableCarrier', [0.95, 0.85, 0.2]],
];

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
    };
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
    this.opaqueMesh = opaque;
    this.ghostMesh = ghost;
    this.focusMesh = focus;
    this.edgesCtx = edgesCtx;
    this.edgesFocus = edgesFocus;
    this.applyPassOrder();
  }

  private disposeMeshes(): void {
    for (const o of [this.opaqueMesh, this.ghostMesh, this.focusMesh, this.edgesCtx, this.edgesFocus, ...this.edgesGlow]) {
      if (o) this.scene.remove(o);
    }
    this.edgesGlow = [];
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
    fm.depthFunc = this.inFront ? AlwaysDepth : LessEqualDepth;
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
    let ghost = false;
    for (let i = 0; i < this.n; i++) {
      const o = i * 4;
      A[o] = color[i * 3]!;
      A[o + 1] = color[i * 3 + 1]!;
      A[o + 2] = color[i * 3 + 2]!;
      const a = alpha[i]!;
      A[o + 3] = a;
      // alpha < 0 (types.HIDDEN) also means hidden
      B[o] = a < 0 ? flags[i]! | FLAG_HIDDEN : flags[i]!;
      B[o + 1] = glow ? glow[i]! : 0; // edge-glow membership
      B[o + 2] = hold ? hold[i]! : 0; // sweep hold alpha (0: not in the sweep)
      if (!ghost && a >= 0 && a < OPAQUE_ALPHA && (flags[i]! & (FLAG_FOCUS | FLAG_HIDDEN)) === 0) ghost = true;
    }
    this.anyGhost = ghost;
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

  render(): void {
    this.controls.update();
    this.upload();
    if (this.offsetsDirty) {
      this.texC.needsUpdate = true;
      this.offsetsDirty = false;
    }
    this.syncLights();
    if (this.post) this.post(this);
    else this.renderScene();
  }

  /**
   * The scene draw to the current render target (the canvas by default). With OIT on, the ghosts are first
   * accumulated into the OIT target, then composited over the opaque scene at the ghost pass's draw-order
   * slot, so context edges and the focus pass still draw over them. Works into the canvas and into any
   * render target (also multisampled): the composite is an ordinary draw into the current target.
   */
  renderScene(): void {
    if (!this.focusOnlyStash) {
      const compose = this.oitOn && this.anyGhost && this.renderOitTarget();
      if (this.ghostMesh) this.ghostMesh.visible = !this.oitOn;
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

  /** World-space displacement of one element in every pass (exploded context). Picking and the BVH use the undisplaced geometry. */
  setElementOffset(id: number, x: number, y: number, z: number): void {
    if (id < 0 || id >= this.n) return;
    const o = id * 4;
    const C = this.dataC;
    C[o] = x;
    C[o + 1] = y;
    C[o + 2] = z;
    this.offsetsDirty = true;
  }

  clearElementOffsets(): void {
    this.dataC.fill(0);
    this.offsetsDirty = true;
  }

  resize(): void {
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
    const dir = new Vector3(0.7, 0.55, 0.85).normalize();
    this.camera.position.copy(sphere.center).addScaledVector(dir, dist);
    this.camera.near = Math.max(r * 0.005, 1e-3);
    this.camera.far = dist + r * 50;
    this.camera.updateProjectionMatrix();
    this.controls.target.copy(sphere.center);
    this.controls.minDistance = r * 0.02;
    this.controls.maxDistance = r * 20;
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
    const ray = this.raycaster.ray;
    const g = this.loaded.geometry;
    const bvh = g.bvh;
    const { alpha, flags } = this.state;
    let near = 0;
    for (let iter = 0; iter < 512; iter++) {
      const hit = bvh.raycastFirst(ray, DoubleSide, near, Infinity);
      if (!hit || hit.faceIndex == null) return null;
      const id = g.elementOfTriangle(hit.faceIndex);
      if (id >= 0) {
        const f = flags[id]!;
        const a = alpha[id]!;
        const hidden = (f & FLAG_HIDDEN) !== 0 || a < 0;
        const clickThrough = (f & FLAG_FOCUS) === 0 && a < 0.3;
        if (!hidden && !clickThrough) return id;
      }
      near = hit.distance + 1e-4;
    }
    return null;
  }

  dispose(): void {
    this.controls.removeEventListener('change', this.onControlsChange);
    this.controls.dispose();
    this.disposeMeshes();
    this.freeOitTarget();
    this.oitQuadMaterial.dispose();
    this.oitQuad.geometry.dispose();
    this.texA.dispose();
    this.texB.dispose();
    this.texC.dispose();
    this.renderer.dispose();
  }
}
