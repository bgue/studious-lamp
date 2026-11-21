// The on-screen HUD overlay: a canvas over the viewer canvas (no pointer events, sized to it, device-pixel aware) that the HUD
// layer draws into. Drawn each frame while a score plays, cleared otherwise.

import type { Camera } from 'three';
import type { HudLayer, HudFrame } from '../hud';
import { makeProjector } from './project';

export class HudOverlay {
  readonly canvas: HTMLCanvasElement;
  private ctx: CanvasRenderingContext2D | null = null;
  private drawn = false;
  private w = 0;
  private h = 0;
  private dpr = 1;
  /** Offset of the drawing area inside the viewer canvas (CSS px): the parts chrome covers are left out. */
  private ox = 0;
  private oy = 0;
  private fullW = 0;
  private fullH = 0;

  constructor(
    private readonly viewer: HTMLCanvasElement,
    private readonly layer: HudLayer,
    private readonly camera: () => Camera,
    /** How much of each edge of the viewer canvas chrome covers (tool strip, status bar, top bar), so the HUD stays clear of it. */
    private readonly insets: () => { top: number; right: number; bottom: number; left: number } | null = () => null,
  ) {
    const c = document.createElement('canvas');
    c.className = 'xray-hud';
    c.setAttribute('aria-hidden', 'true');
    // z-index 15: above the 3D view, below the sidebars and phone sheets (z-index 20), so an open panel is never drawn over
    c.style.cssText = 'position:fixed;left:0;top:0;width:0;height:0;pointer-events:none;z-index:15;display:none';
    document.body.appendChild(c);
    this.canvas = c;
    try {
      this.ctx = c.getContext('2d');
    } catch {
      this.ctx = null;
    }
  }

  /** True while something is drawn on it. */
  get visible(): boolean {
    return this.drawn;
  }

  /** CSS size and device pixel ratio of the last draw. */
  get size(): { width: number; height: number; pixelRatio: number } {
    return { width: this.w, height: this.h, pixelRatio: this.dpr };
  }

  private fit(): boolean {
    const r = this.viewer.getBoundingClientRect();
    const ins = this.insets() ?? { top: 0, right: 0, bottom: 0, left: 0 };
    this.fullW = Math.round(r.width);
    this.fullH = Math.round(r.height);
    this.ox = Math.round(Math.max(0, ins.left));
    this.oy = Math.round(Math.max(0, ins.top));
    const w = Math.round(r.width - this.ox - Math.max(0, ins.right));
    const h = Math.round(r.height - this.oy - Math.max(0, ins.bottom));
    if (w <= 0 || h <= 0) return false;
    const dpr = Math.min(3, Math.max(1, window.devicePixelRatio || 1));
    const s = this.canvas.style;
    s.left = `${r.left + this.ox}px`;
    s.top = `${r.top + this.oy}px`;
    s.width = `${w}px`;
    s.height = `${h}px`;
    if (w !== this.w || h !== this.h || dpr !== this.dpr || this.canvas.width !== Math.round(w * dpr)) {
      this.w = w;
      this.h = h;
      this.dpr = dpr;
      this.canvas.width = Math.round(w * dpr);
      this.canvas.height = Math.round(h * dpr);
    }
    return true;
  }

  /** Draw the layer at `t`. Clears the overlay when the layer has nothing to show. */
  draw(t: number, duration: number): void {
    const ctx = this.ctx;
    if (!ctx || !this.layer.active(t) || !this.fit()) {
      this.clear();
      return;
    }
    this.canvas.style.display = '';
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
    const cam = this.camera();
    cam.updateMatrixWorld();
    this.layer.draw(ctx, {
      t,
      duration,
      width: this.w,
      height: this.h,
      pixelRatio: this.dpr,
      project: this.projector(cam),
      recording: false,
    });
    this.drawn = true;
  }

  /** Project with the full canvas (the camera's aspect), then shift into the drawing area; points outside it give null. */
  private projector(cam: Camera): HudFrame['project'] {
    const full = makeProjector(cam, this.fullW, this.fullH);
    const ox = this.ox, oy = this.oy, w = this.w, h = this.h, slack = 40;
    return (p) => {
      const q = full(p);
      if (!q) return null;
      const x = q.x - ox, y = q.y - oy;
      return x < -slack || x > w + slack || y < -slack || y > h + slack ? null : { x, y };
    };
  }

  clear(): void {
    if (!this.drawn && this.canvas.style.display === 'none') return;
    const ctx = this.ctx;
    if (ctx) {
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
    }
    this.canvas.style.display = 'none';
    this.drawn = false;
  }
}
