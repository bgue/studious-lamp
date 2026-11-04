// Selective bloom on the focus set. The renderer's render() is routed through a post pipeline:
//   1. the normal frame is drawn to the canvas;
//   2. the focus mesh alone is drawn (emissive-boosted via the focus material's uniform) into the
//      composer's target;
//   3. UnrealBloomPass blurs it;
//   4. only the blurred glow (not the mask itself) is added over the canvas.
// So context geometry never blooms and the focus colours are not doubled.

import { AdditiveBlending, Color, ShaderMaterial, Vector2 } from 'three';
import type { Texture } from 'three';
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/examples/jsm/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass.js';
import { FullScreenQuad } from 'three/examples/jsm/postprocessing/Pass.js';
import type { XrayRenderer } from '../render/renderer';

export interface BloomSettings {
  strength: number;
  radius: number;
  /** Emissive multiplier on the focus colours in the mask render. */
  boost: number;
  /** Fraction of the canvas resolution used for the mask and blur. */
  scale: number;
}

export const DEFAULT_BLOOM: BloomSettings = { strength: 0.7, radius: 0.45, boost: 1.0, scale: 0.5 };

export class SelectiveBloom {
  readonly settings: BloomSettings = { ...DEFAULT_BLOOM };
  private composer: EffectComposer | null = null;
  private bloom: UnrealBloomPass | null = null;
  private quad: FullScreenQuad | null = null;
  private addMaterial: ShaderMaterial | null = null;
  private size = new Vector2();
  private lastW = 0;
  private lastH = 0;
  private on = false;
  /**
   * Called when the bloom is switched on or off. The post pipeline (post.ts) sets this to route the
   * frame; without it the bloom installs its own pipeline.
   */
  onChange: (() => void) | null = null;

  /** Focus element count; the bloom is skipped when there is nothing to bloom. */
  constructor(private readonly r: XrayRenderer, private readonly focusCount: () => number) {}

  get enabled(): boolean {
    return this.on;
  }

  enable(): void {
    if (this.on) return;
    this.on = true;
    if (this.onChange) this.onChange();
    else this.r.setPostPipeline(() => this.renderDirect());
  }

  disable(): void {
    if (!this.on) return;
    this.on = false;
    if (this.onChange) this.onChange();
    else this.r.setPostPipeline(null);
    this.r.setFocusBoost(0);
    this.r.setFocusOnly(false);
    this.free();
  }

  private ensure(): void {
    if (this.composer) return;
    const renderer = this.r.renderer;
    const composer = new EffectComposer(renderer);
    composer.renderToScreen = false;
    const mask = new RenderPass(this.r.scene, this.r.camera, null, new Color(0, 0, 0), 0);
    const bloom = new UnrealBloomPass(new Vector2(256, 256), this.settings.strength, this.settings.radius, 0);
    composer.addPass(mask);
    composer.addPass(bloom);
    this.composer = composer;
    this.bloom = bloom;
    this.addMaterial = new ShaderMaterial({
      uniforms: { tDiffuse: { value: null } },
      vertexShader: 'varying vec2 vUv; void main() { vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }',
      fragmentShader: 'uniform sampler2D tDiffuse; varying vec2 vUv; void main() { gl_FragColor = vec4(texture2D(tDiffuse, vUv).rgb, 1.0); }',
      blending: AdditiveBlending,
      transparent: true,
      depthTest: false,
      depthWrite: false,
    });
    this.quad = new FullScreenQuad(this.addMaterial);
    this.lastW = this.lastH = 0;
  }

  private free(): void {
    this.composer?.dispose();
    this.bloom?.dispose();
    this.quad?.dispose();
    this.addMaterial?.dispose();
    this.composer = null;
    this.bloom = null;
    this.quad = null;
    this.addMaterial = null;
  }

  /** The bloom alone: draw the frame to the canvas, then add the blurred glow over it. */
  renderDirect(): void {
    this.r.renderScene();
    const glow = this.glowTexture();
    if (!glow) return;
    const renderer = this.r.renderer;
    this.addMaterial!.uniforms.tDiffuse!.value = glow;
    const autoClear = renderer.autoClear;
    renderer.autoClear = false;
    renderer.setRenderTarget(null);
    this.quad!.render(renderer);
    renderer.autoClear = autoClear;
  }

  /**
   * Render the focus-only mask, blur it and return the blurred glow texture (null when there is no
   * focus). The caller adds it to the frame. Leaves the renderer's render target unspecified.
   */
  glowTexture(): Texture | null {
    const r = this.r;
    if (this.focusCount() === 0) return null;
    this.ensure();
    const composer = this.composer!;
    const bloom = this.bloom!;
    const renderer = r.renderer;

    renderer.getDrawingBufferSize(this.size);
    if (this.size.x !== this.lastW || this.size.y !== this.lastH) {
      this.lastW = this.size.x;
      this.lastH = this.size.y;
      composer.setPixelRatio(this.settings.scale);
      composer.setSize(this.size.x, this.size.y);
    }
    bloom.strength = this.settings.strength;
    bloom.radius = this.settings.radius;

    r.setFocusOnly(true);
    r.setFocusBoost(this.settings.boost);
    composer.render(1 / 60);
    r.setFocusBoost(0);
    r.setFocusOnly(false);

    // The pass leaves the composite of its mips in the first horizontal target.
    return bloom.renderTargetsHorizontal[0]!.texture;
  }

  dispose(): void {
    this.disable();
  }
}
