// Scene dressing: gradient sky, soft ground shadow, distance fog and a warm key / cool fill light rig.
// No shadow maps; the ground shadow is one textured plane.

import {
  Box3,
  CanvasTexture,
  Color,
  NoColorSpace,
  DoubleSide,
  Mesh,
  MeshBasicMaterial,
  PlaneGeometry,
  SRGBColorSpace,
  Sphere,
  Vector3,
} from 'three';
import type { Texture } from 'three';
import type { XrayRenderer } from '../render/renderer';

export interface DressingSettings {
  skyTop: string;
  skyBottom: string;
  /** Draw the ground shadow plane. It is the costliest part (one extra transparent draw), so it is off by default. */
  ground: boolean;
  shadowStrength: number;
  fogStrength: number;
}

export const DEFAULT_DRESSING: DressingSettings = {
  skyTop: '#b7c6da',
  skyBottom: '#eef1f4',
  ground: false,
  shadowStrength: 0.5,
  fogStrength: 0.4,
};

/** '#rrggbb' -> sRGB 0..1 triple. The shaders write colours straight to the canvas, so no colour-space conversion. */
export function hexToRgb(hex: string): [number, number, number] {
  const n = parseInt(hex.replace('#', ''), 16);
  return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255];
}

function canvas2d(w: number, h: number): { c: HTMLCanvasElement; g: CanvasRenderingContext2D } {
  const c = document.createElement('canvas');
  c.width = w;
  c.height = h;
  return { c, g: c.getContext('2d')! };
}

export function makeSkyTexture(top: string, bottom: string, raw = false): CanvasTexture {
  const { c, g } = canvas2d(4, 256);
  const grad = g.createLinearGradient(0, 0, 0, 256);
  grad.addColorStop(0, top);
  grad.addColorStop(1, bottom);
  g.fillStyle = grad;
  g.fillRect(0, 0, 4, 256);
  const t = new CanvasTexture(c);
  // raw: sampled without a colour-space decode, for the post pipeline (see rawBackground).
  t.colorSpace = raw ? NoColorSpace : SRGBColorSpace;
  return t;
}

export function makeShadowTexture(): CanvasTexture {
  const { c, g } = canvas2d(256, 256);
  const grad = g.createRadialGradient(128, 128, 0, 128, 128, 128);
  grad.addColorStop(0, 'rgba(18,24,34,1)');
  grad.addColorStop(0.45, 'rgba(18,24,34,0.55)');
  grad.addColorStop(1, 'rgba(18,24,34,0)');
  g.fillStyle = grad;
  g.fillRect(0, 0, 256, 256);
  return new CanvasTexture(c);
}

export class SceneDressing {
  private sky: Texture | null = null;
  private skyRaw: Texture | null = null;
  private ground: Mesh | null = null;
  private shadowMap: CanvasTexture | null = null;
  private bounds = new Box3();
  private sphere = new Sphere();
  private active = false;
  private saved: { sky: Color; ground: Color; hemiI: number; sun: Color; sunI: number; sunPos: Vector3 } | null = null;
  readonly settings: DressingSettings = { ...DEFAULT_DRESSING };

  constructor(private readonly r: XrayRenderer) {}

  get enabled(): boolean {
    return this.active;
  }

  /** Apply (or re-apply, after a model change or a setting change). `bounds` is the model's total bounds. */
  enable(bounds: Box3): void {
    if (!bounds.isEmpty()) {
      this.bounds.copy(bounds);
      this.bounds.getBoundingSphere(this.sphere);
    }
    this.active = true;
    this.applySky();
    this.applyGround();
    this.applyLights();
  }

  disable(): void {
    if (!this.active) return;
    this.active = false;
    this.r.scene.background = null;
    this.sky?.dispose();
    this.sky = null;
    this.skyRaw?.dispose();
    this.skyRaw = null;
    if (this.ground) this.ground.visible = false;
    this.r.setFog([0, 0, 0], 0, 1, 0);
    const s = this.saved;
    if (s) {
      this.r.hemi.color.copy(s.sky);
      this.r.hemi.groundColor.copy(s.ground);
      this.r.hemi.intensity = s.hemiI;
      this.r.sun.color.copy(s.sun);
      this.r.sun.intensity = s.sunI;
      this.r.sun.position.copy(s.sunPos);
      this.saved = null;
    }
  }

  /**
   * The same sky without the sRGB decode. The normal draw writes colours straight to the canvas, so the
   * built-in background is decoded then re-encoded; when the scene is drawn into a linear render target
   * (post pipeline) nothing re-encodes it, so the pipeline swaps this texture in for that draw.
   */
  rawBackground(): Texture | null {
    if (!this.active || !this.sky) return null;
    if (!this.skyRaw) this.skyRaw = makeSkyTexture(this.settings.skyTop, this.settings.skyBottom, true);
    return this.skyRaw;
  }

  private applySky(): void {
    this.skyRaw?.dispose();
    this.skyRaw = null;
    this.sky?.dispose();
    this.sky = makeSkyTexture(this.settings.skyTop, this.settings.skyBottom);
    this.r.scene.background = this.sky;
  }

  private applyGround(): void {
    if (!this.settings.ground) {
      if (this.ground) this.ground.visible = false;
      return;
    }
    if (!this.ground) {
      this.shadowMap = makeShadowTexture();
      const mat = new MeshBasicMaterial({
        map: this.shadowMap,
        transparent: true,
        depthWrite: false,
        side: DoubleSide,
        polygonOffset: true,
        polygonOffsetFactor: 2,
        polygonOffsetUnits: 2,
      });
      this.ground = new Mesh(new PlaneGeometry(1, 1), mat);
      this.ground.rotation.x = -Math.PI / 2;
      this.ground.renderOrder = -1;
      this.ground.frustumCulled = false;
      this.ground.name = 'cinematic-ground-shadow';
      this.r.scene.add(this.ground);
    }
    const size = this.bounds.getSize(new Vector3());
    const centre = this.bounds.getCenter(new Vector3());
    const span = Math.max(size.x, size.z, 1e-3) * 1.7;
    this.ground.scale.set(span, span, 1);
    this.ground.position.set(centre.x, this.bounds.min.y - Math.max(0.01, size.y * 0.002), centre.z);
    (this.ground.material as MeshBasicMaterial).opacity = this.settings.shadowStrength;
    this.ground.visible = this.bounds.isEmpty() ? false : true;
  }

  /** Warm key (the directional light) plus cool fill (the hemisphere light). */
  private applyLights(): void {
    const { hemi, sun } = this.r;
    if (!this.saved) {
      this.saved = {
        sky: hemi.color.clone(),
        ground: hemi.groundColor.clone(),
        hemiI: hemi.intensity,
        sun: sun.color.clone(),
        sunI: sun.intensity,
        sunPos: sun.position.clone(),
      };
    }
    hemi.color.set(0xd3e2fb); // cool fill from above
    hemi.groundColor.set(0x7d7a78); // neutral-warm bounce
    hemi.intensity = 0.6;
    sun.color.set(0xfff3e2); // warm key
    sun.intensity = 0.6;
  }

  setSettings(patch: Partial<DressingSettings>): void {
    Object.assign(this.settings, patch);
    if (!this.active) return;
    this.applySky();
    this.applyGround();
  }

  /** Per-frame fog: nothing up to just beyond the orbit target, rising to `fogStrength` behind the model. */
  updateFog(): void {
    if (!this.active) return;
    const r = Math.max(this.sphere.radius, 1e-3);
    const cam = this.r.camera.position;
    const dTarget = cam.distanceTo(this.r.controls.target);
    this.r.setFog(hexToRgb(this.settings.skyBottom), dTarget + 0.15 * r, dTarget + 2.2 * r, this.settings.fogStrength);
  }

  dispose(): void {
    this.disable();
    if (this.ground) {
      this.r.scene.remove(this.ground);
      this.ground.geometry.dispose();
      (this.ground.material as MeshBasicMaterial).dispose();
      this.ground = null;
    }
    this.shadowMap?.dispose();
    this.shadowMap = null;
  }
}
