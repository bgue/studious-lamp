// The post pipeline: one function, routed through renderer.setPostPipeline once, that applies whichever
// of these are enabled, in this fixed order:
//
//   scene  ->  ambient occlusion (GTAO, half resolution)  ->  depth of field  ->  bloom glow
//          ->  motion blur (temporal blend)  ->  vignette  ->  canvas
//
// With only the bloom on, the original direct path is kept (scene to the canvas, glow added over it).
// With any of the others on, the scene is drawn into a multisampled render target that has a depth
// texture; the AO and the depth of field read that depth texture (so the scene is drawn once), and
// the rest runs through EffectComposer. AO and DoF are skipped for ghosts (the ghost pass does not
// write depth), so they treat ghosts as see-through.
//
// Order-independent transparency (render/renderer.ts, render/oitMath.ts) sits inside the scene draw, so it
// works the same on the direct path and here, and always comes before AO, DoF, bloom and vignette:
//   renderScene() = [ghost accumulation into a private target (no MSAA by default, its own depth pre-pass)]
//                   then the scene into the current target (canvas, or this sceneRT) with the full-screen
//                   OIT composite drawn at the ghost pass's draw-order slot, so edges and the in-front focus
//                   pass draw over it. The OIT target is never the multisampled sceneRT (MRT plus a
//                   shared depth texture would force the ghost pass to depend on its resolve), so there is
//                   no MRT-in-multisampled-target problem: the composite is an ordinary draw into sceneRT.
//
// Colour: the x-ray shaders write display colours straight to the canvas. The composer's targets are
// linear and nothing converts at the end, so those values pass through unchanged. The one thing that
// would not is the built-in sky background (decoded on read, never re-encoded): the scene draw
// swaps in the dressing's raw sky texture, and the clear colour is set raw, so the composed frame
// matches the direct one.

import {
  Color,
  DataTexture,
  DepthTexture,
  HalfFloatType,
  LinearSRGBColorSpace,
  NearestFilter,
  RGBAFormat,
  SRGBColorSpace,
  UnsignedByteType,
  Vector2,
  WebGLRenderTarget,
} from 'three';
import type { Texture } from 'three';
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js';
import { GTAOPass } from 'three/examples/jsm/postprocessing/GTAOPass.js';
import { Pass } from 'three/examples/jsm/postprocessing/Pass.js';
import { ShaderPass } from 'three/examples/jsm/postprocessing/ShaderPass.js';
import { BokehShader } from 'three/examples/jsm/shaders/BokehShader.js';
import { CopyShader } from 'three/examples/jsm/shaders/CopyShader.js';
import { VignetteShader } from 'three/examples/jsm/shaders/VignetteShader.js';
import type { XrayRenderer } from '../render/renderer';
import type { SelectiveBloom } from './bloom';

export interface PostSettings {
  ao: boolean;
  /** World-space AO radius, metres. */
  aoRadius: number;
  /** Strength of the AO multiply (GTAOPass.blendIntensity). */
  aoIntensity: number;
  vignette: boolean;
  /** 0 = none, 1 = the corners fade to black. */
  vignetteDarkness: number;
  /** Depth of field on the focus; only applied while a fly-through plays. */
  dof: boolean;
  dofAperture: number;
  /** Weight of the previous frame (0 = off); only applied while a fly-through plays. */
  motionBlur: number;
}

export const DEFAULT_POST: PostSettings = {
  ao: false,
  aoRadius: 0.6,
  aoIntensity: 1,
  vignette: false,
  vignetteDarkness: 0.7,
  dof: false,
  dofAperture: 0.5,
  motionBlur: 0,
};

export interface PostHooks {
  /** The dressing's sky without the sRGB decode, or null. */
  rawBackground(): Texture | null;
  /** Distance along the view axis from the camera to the focus centre (metres), or null without a focus. */
  focusDistance(): number | null;
}

const GLOW_ADD_SHADER = {
  name: 'GlowAddShader',
  uniforms: { tDiffuse: { value: null as Texture | null }, tGlow: { value: null as Texture | null } },
  vertexShader: 'varying vec2 vUv; void main() { vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }',
  fragmentShader:
    'uniform sampler2D tDiffuse; uniform sampler2D tGlow; varying vec2 vUv;' +
    'void main() { gl_FragColor = vec4(texture2D(tDiffuse, vUv).rgb + texture2D(tGlow, vUv).rgb, 1.0); }',
};

const TEMPORAL_SHADER = {
  name: 'TemporalBlendShader',
  uniforms: { tDiffuse: { value: null as Texture | null }, tPrev: { value: null as Texture | null }, weight: { value: 0 } },
  vertexShader: 'varying vec2 vUv; void main() { vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }',
  fragmentShader:
    'uniform sampler2D tDiffuse; uniform sampler2D tPrev; uniform float weight; varying vec2 vUv;' +
    'void main() { gl_FragColor = vec4(mix(texture2D(tDiffuse, vUv).rgb, texture2D(tPrev, vUv).rgb, weight), 1.0); }',
};

/** Stand-in for a render target when a pass only reads `.texture`. */
function asBuffer(texture: Texture): WebGLRenderTarget {
  return { texture } as unknown as WebGLRenderTarget;
}

/** Draws the scene into the depth-carrying target, then copies it into the composer's chain. */
class ScenePass extends Pass {
  private readonly copy = new ShaderPass(CopyShader);
  constructor(private readonly fx: PostFx) {
    super();
    this.needsSwap = true;
  }
  render(renderer: unknown, writeBuffer: WebGLRenderTarget): void {
    const rt = this.fx.drawScene();
    this.copy.renderToScreen = this.renderToScreen;
    this.copy.render(renderer as never, writeBuffer, asBuffer(rt.texture), 0, false);
  }
  dispose(): void {
    this.copy.dispose();
  }
}

/** Adds the selective-bloom glow to the frame. */
class GlowAddPass extends Pass {
  private readonly add = new ShaderPass(GLOW_ADD_SHADER, 'tDiffuse');
  private readonly black: Texture;
  constructor(private readonly bloom: SelectiveBloom, black: Texture) {
    super();
    this.needsSwap = true;
    this.black = black;
  }
  render(renderer: unknown, writeBuffer: WebGLRenderTarget, readBuffer: WebGLRenderTarget): void {
    this.add.uniforms.tGlow!.value = this.bloom.glowTexture() ?? this.black;
    this.add.renderToScreen = this.renderToScreen;
    this.add.render(renderer as never, writeBuffer, readBuffer, 0, false);
  }
  dispose(): void {
    this.add.dispose();
  }
}

/** Mixes the frame with the previous output frame, kept in a persistent target. */
class TemporalPass extends Pass {
  weight = 0;
  private a: WebGLRenderTarget;
  private b: WebGLRenderTarget;
  private readonly blend = new ShaderPass(TEMPORAL_SHADER, 'tDiffuse');
  private readonly copy = new ShaderPass(CopyShader);
  private fresh = true;
  constructor(w: number, h: number) {
    super();
    this.needsSwap = true;
    this.a = new WebGLRenderTarget(w, h, { type: HalfFloatType, depthBuffer: false });
    this.b = new WebGLRenderTarget(w, h, { type: HalfFloatType, depthBuffer: false });
  }
  /** Forget the history (camera cut, playback start). */
  reset(): void {
    this.fresh = true;
  }
  setSize(w: number, h: number): void {
    this.a?.setSize(w, h);
    this.b?.setSize(w, h);
    this.fresh = true;
  }
  render(renderer: unknown, writeBuffer: WebGLRenderTarget, readBuffer: WebGLRenderTarget): void {
    // a: previous output (history), b: this frame's blend.
    this.blend.uniforms.weight!.value = this.fresh ? 0 : this.weight;
    this.blend.uniforms.tPrev!.value = this.a.texture;
    this.blend.renderToScreen = false;
    this.blend.render(renderer as never, this.b, readBuffer, 0, false);
    this.fresh = false;
    this.copy.renderToScreen = this.renderToScreen;
    this.copy.render(renderer as never, writeBuffer, this.b, 0, false);
    const t = this.a;
    this.a = this.b;
    this.b = t;
  }
  dispose(): void {
    this.a.dispose();
    this.b.dispose();
    this.blend.dispose();
    this.copy.dispose();
  }
}

export class PostFx {
  readonly settings: PostSettings = { ...DEFAULT_POST };
  /** True while a fly-through plays (enables depth of field and motion blur). */
  private playing = false;

  private sceneRT: WebGLRenderTarget | null = null;
  private composer: EffectComposer | null = null;
  private scenePass: ScenePass | null = null;
  private ao: GTAOPass | null = null;
  private dof: ShaderPass | null = null;
  private glow: GlowAddPass | null = null;
  private temporal: TemporalPass | null = null;
  private vignette: ShaderPass | null = null;
  private black: Texture | null = null;
  private lastW = 0;
  private lastH = 0;
  private readonly size = new Vector2();
  private routed = false;

  constructor(private readonly r: XrayRenderer, private readonly bloom: SelectiveBloom, private readonly hooks: PostHooks) {
    bloom.onChange = () => this.sync();
  }

  setPlaying(on: boolean): void {
    if (on === this.playing) return;
    this.playing = on;
    this.temporal?.reset();
    this.sync();
  }

  /** What the composer path has to do this frame. */
  get stages(): { ao: boolean; dof: boolean; glow: boolean; motion: boolean; vignette: boolean; composer: boolean } {
    const s = this.settings;
    const ao = s.ao;
    const dof = s.dof && this.playing;
    const motion = s.motionBlur > 0 && this.playing;
    const vignette = s.vignette;
    return { ao, dof, glow: this.bloom.enabled, motion, vignette, composer: ao || dof || motion || vignette };
  }

  /** Install or remove the pipeline according to the user-level switches. Call after any change of them. */
  sync(): void {
    const s = this.settings;
    const want = s.ao || s.vignette || s.dof || s.motionBlur > 0 || this.bloom.enabled;
    if (want && !this.routed) {
      this.r.setPostPipeline(() => this.run());
      this.routed = true;
    } else if (!want && this.routed) {
      this.r.setPostPipeline(null);
      this.routed = false;
    }
    if (!s.ao && !s.vignette && !s.dof && s.motionBlur <= 0) this.free();
  }

  private run(): void {
    const st = this.stages;
    if (!st.composer) {
      if (st.glow) this.bloom.renderDirect();
      else this.r.renderScene();
      return;
    }
    this.ensure();
    const composer = this.composer!;
    const renderer = this.r.renderer;
    renderer.getDrawingBufferSize(this.size);
    const w = Math.max(1, Math.floor(this.size.x));
    const h = Math.max(1, Math.floor(this.size.y));
    if (w !== this.lastW || h !== this.lastH) {
      this.lastW = w;
      this.lastH = h;
      composer.setSize(w, h);
      this.sceneRT!.setSize(w, h);
      this.ao!.setSize(Math.max(1, w >> 1), Math.max(1, h >> 1));
      this.ao!.setGBuffer(this.sceneRT!.depthTexture!, undefined);
    }
    const s = this.settings;
    const cam = this.r.camera;

    this.ao!.enabled = st.ao;
    this.ao!.blendIntensity = s.aoIntensity;
    this.ao!.updateGtaoMaterial({ radius: s.aoRadius });
    this.dof!.enabled = st.dof;
    if (st.dof) {
      const u = this.dof!.uniforms;
      const dist = this.hooks.focusDistance() ?? cam.position.distanceTo(this.r.controls.target);
      u.focus!.value = dist;
      // Blur grows with the depth difference relative to the focus distance; the slider scales it.
      u.aperture!.value = (s.dofAperture * 0.12) / Math.max(dist, 0.5);
      u.maxblur!.value = 0.015;
      u.aspect!.value = w / h;
      u.nearClip!.value = cam.near;
      u.farClip!.value = cam.far;
    }
    this.glow!.enabled = st.glow;
    this.temporal!.enabled = st.motion;
    this.temporal!.weight = Math.min(0.95, s.motionBlur);
    this.vignette!.enabled = st.vignette;
    // VignetteShader mixes toward (1 - darkness) by dot(uv, uv), uv = (vUv - 0.5) * offset. With darkness 1 the
    // target is black, and offset = sqrt(2 d) makes the corner factor exactly d (0 = no effect).
    this.vignette!.uniforms.darkness!.value = 1;
    this.vignette!.uniforms.offset!.value = Math.sqrt(2 * Math.min(Math.max(s.vignetteDarkness, 0), 1.5));

    // The scene pass writes into the composer's current write buffer; start every frame from the same pair.
    composer.readBuffer = composer.renderTarget1;
    composer.writeBuffer = composer.renderTarget2;
    composer.render(1 / 60);
  }

  /** Draw the scene into the depth target (raw sky and clear colour; see the header). Returns the target. */
  drawScene(): WebGLRenderTarget {
    const r = this.r;
    const renderer = r.renderer;
    const scene = r.scene;
    const prevBg = scene.background;
    const raw = this.hooks.rawBackground();
    let restoreClear: (() => void) | null = null;
    if (prevBg && raw) scene.background = raw;
    else if (!prevBg) {
      const keep = renderer.getClearColor(new Color());
      const alpha = renderer.getClearAlpha();
      const rgb = { r: 0, g: 0, b: 0 };
      keep.getRGB(rgb, SRGBColorSpace);
      renderer.setClearColor(new Color().setRGB(rgb.r, rgb.g, rgb.b, LinearSRGBColorSpace), alpha);
      restoreClear = () => renderer.setClearColor(keep, alpha);
    }
    renderer.setRenderTarget(this.sceneRT);
    r.renderScene();
    scene.background = prevBg;
    restoreClear?.();
    return this.sceneRT!;
  }

  private ensure(): void {
    if (this.composer) return;
    const r = this.r;
    const renderer = r.renderer;
    renderer.getDrawingBufferSize(this.size);
    const w = Math.max(1, Math.floor(this.size.x));
    const h = Math.max(1, Math.floor(this.size.y));

    const depth = new DepthTexture(w, h);
    depth.minFilter = NearestFilter;
    depth.magFilter = NearestFilter;
    const rt = new WebGLRenderTarget(w, h, { type: HalfFloatType, depthTexture: depth, samples: Math.min(4, renderer.capabilities.maxSamples) });
    this.sceneRT = rt;

    const composer = new EffectComposer(renderer, new WebGLRenderTarget(w, h, { type: HalfFloatType, depthBuffer: false }));
    composer.setPixelRatio(1);

    this.black = makeBlack();

    this.scenePass = new ScenePass(this);
    composer.addPass(this.scenePass);

    this.ao = new GTAOPass(r.scene, r.camera, Math.max(1, w >> 1), Math.max(1, h >> 1));
    this.ao.setGBuffer(depth, undefined);
    this.ao.updateGtaoMaterial({ radius: this.settings.aoRadius, distanceExponent: 1, thickness: 0.25, scale: 1, samples: 16, distanceFallOff: 1, screenSpaceRadius: false });
    this.ao.updatePdMaterial({ lumaPhi: 10, depthPhi: 1, normalPhi: 2, radius: 8, radiusExponent: 1, rings: 2, samples: 16 });
    composer.addPass(this.ao);

    this.dof = new ShaderPass({ ...BokehShader, defines: { ...BokehShader.defines, DEPTH_PACKING: 0 } }, 'tColor');
    this.dof.uniforms.tDepth!.value = depth;
    composer.addPass(this.dof);

    this.glow = new GlowAddPass(this.bloom, this.black);
    composer.addPass(this.glow);

    this.temporal = new TemporalPass(w, h);
    composer.addPass(this.temporal);

    this.vignette = new ShaderPass(VignetteShader);
    composer.addPass(this.vignette);

    this.composer = composer;
    this.lastW = this.lastH = 0;
  }

  /** Release the GPU resources (the pipeline stays routed when the bloom is still on). */
  free(): void {
    if (!this.composer) return;
    this.scenePass?.dispose();
    this.ao?.dispose();
    this.dof?.dispose();
    this.glow?.dispose();
    this.temporal?.dispose();
    this.vignette?.dispose();
    this.composer.dispose();
    this.sceneRT?.dispose();
    this.sceneRT?.depthTexture?.dispose();
    this.black?.dispose();
    this.composer = this.sceneRT = null;
    this.scenePass = null;
    this.ao = this.dof = this.glow = this.temporal = this.vignette = null;
    this.black = null;
  }

  dispose(): void {
    this.bloom.onChange = null;
    this.r.setPostPipeline(null);
    this.routed = false;
    this.free();
  }
}

function makeBlack(): Texture {
  const t = new DataTexture(new Uint8Array([0, 0, 0, 255]), 1, 1, RGBAFormat, UnsignedByteType);
  t.needsUpdate = true;
  return t;
}
