// Shared SVG overlay above the canvas, for tools that draw labels and markers anchored to model points
// (penetration markers, measurements, the clearance legend).
//
//   const ov = getOverlay(app);
//   const g = ov.layer('mine');                 // an SVG <g>, created once per name, in creation order
//   const off = ov.onUpdate((ov) => { const p = ov.project([x, y, z]); ... });   // runs when the view changed
//   ov.invalidate();                            // ask for a redraw on the next frame (data changed)
//
// The svg fills #stage, ignores pointer events, and uses CSS pixels as user units. `project` is valid inside onUpdate
// callbacks and between frames: it uses the camera matrices of the last frame.
//
// Reserved rects: `ov.reserved` lists the parts of the view that chrome covers (status bar and drawer strips, the gizmo,
// legends, and anything registered with `ov.reserve(key, rect)`), refreshed every frame. `ov.place(x, y, w, h)` gives
// the nearest spot for a label box that is clear of them (see reserved.ts); labels that move draw a leader line back
// to their anchor. Measure labels, penetration markers, BCF pins and callouts all use it.

import { Matrix4 } from 'three';
import type { AppPlugin, ViewerApp } from '../app';
import { freeSpot, insetRects } from './reserved';
import type { Insets, Rect, Spot, SpotOptions } from './reserved';

export type { Insets, Rect, Spot, SpotOptions } from './reserved';
export { freeSpot, insetRects, underReserved } from './reserved';

export type Point3 = readonly [number, number, number] | { x: number; y: number; z: number };

export interface ScreenPoint {
  /** CSS pixels from the canvas top-left corner. */
  x: number;
  y: number;
  /** In front of the camera and inside the view frustum. */
  visible: boolean;
  /** In front of the camera (x, y are meaningful even when outside the frustum). */
  front: boolean;
  /** NDC depth, -1 near .. 1 far (meaningful when in front). */
  depth: number;
}

/**
 * Project a world point with a column-major view-projection matrix (three's Matrix4.elements) to CSS pixels.
 * `visible` needs w > 0 and the point inside the clip volume. Pure; tested without a DOM.
 */
export function projectToScreen(m: ArrayLike<number>, width: number, height: number, x: number, y: number, z: number, out?: ScreenPoint): ScreenPoint {
  const cx = m[0]! * x + m[4]! * y + m[8]! * z + m[12]!;
  const cy = m[1]! * x + m[5]! * y + m[9]! * z + m[13]!;
  const cz = m[2]! * x + m[6]! * y + m[10]! * z + m[14]!;
  const cw = m[3]! * x + m[7]! * y + m[11]! * z + m[15]!;
  const o = out ?? { x: 0, y: 0, visible: false, front: false, depth: 0 };
  if (cw <= 1e-9) {
    o.x = 0; o.y = 0; o.depth = 1; o.visible = false; o.front = false;
    return o;
  }
  const nx = cx / cw, ny = cy / cw, nz = cz / cw;
  o.x = (nx * 0.5 + 0.5) * width;
  o.y = (1 - (ny * 0.5 + 0.5)) * height;
  o.depth = nz;
  o.front = true;
  o.visible = Math.abs(nx) <= 1 && Math.abs(ny) <= 1 && nz >= -1 && nz <= 1;
  return o;
}

const SVG_NS = 'http://www.w3.org/2000/svg';

/** Chrome that can lie over the canvas edges: the tool strip and drawer, the tree and dock (rails on phones), the status bar. */
const EDGE_CHROME = ['#xray-toolbar', '#xray-toolbar-drawer', '#sidebar', '#dock', '#xray-overlay', '#xray-topbar'];

/** Legends drawn on the overlay itself: reserved by their drawn box (a legend may also register with ov.reserve). */
const LEGENDS = '.xray-svg-overlay [data-legend], .xray-svg-overlay g[data-layer$="legend"]';

function shown(e: Element | null): e is HTMLElement {
  if (!(e instanceof HTMLElement) || e.hidden || e.getClientRects().length === 0) return false;
  return getComputedStyle(e).visibility !== 'hidden';
}

/**
 * Where a legend of `w` x `h` px goes, in canvas pixels: the bottom right corner inside the insets, left of the gizmo
 * (or above it when there is no room beside it), `stack` px higher for a legend that sits above another one. Pure.
 */
export function legendSpot(width: number, height: number, ins: Insets, gizmo: Rect | null, w: number, h: number, stack = 0, colW = w): { x: number; y: number } {
  let right = width - ins.right - 12;
  let bottom = height - ins.bottom - 8;
  // `colW`: the widest legend of the column, so stacked legends make the same choice.
  if (gizmo && gizmo.w > 0 && gizmo.h > 0 && gizmo.y < bottom) {
    if (gizmo.x - 8 - colW >= ins.left + 8) right = Math.min(right, gizmo.x - 8);
    else bottom = Math.min(bottom, gizmo.y - 8);
  }
  // No room right of an open drawer: stay inside the stage (partly under the drawer) rather than past its right edge.
  const x = right - w >= ins.left + 8 ? right - w : Math.max(8, right - w);
  return { x, y: Math.max(ins.top + 8, bottom - stack - h) };
}

export class Overlay {
  readonly svg: SVGSVGElement;
  width = 1;
  height = 1;
  private readonly layers = new Map<string, SVGGElement>();
  private readonly listeners = new Set<(ov: Overlay) => void>();
  private readonly viewProj = new Matrix4();
  /** Chrome over the canvas edges and the gizmo box (canvas pixels), refreshed every frame. */
  insets: Insets = { top: 0, right: 0, bottom: 0, left: 0 };
  gizmo: Rect | null = null;
  /** Every reserved rect (canvas pixels): the edge chrome strips, the gizmo, the legends and the registered rects. */
  reserved: Rect[] = [];
  private readonly registry = new Map<string, Rect | (() => Rect | null)>();
  private signature = '';
  private dirty = true;

  constructor(private readonly app: ViewerApp) {
    const host = app.canvas.parentElement ?? document.body;
    if (getComputedStyle(host).position === 'static') host.style.position = 'relative';
    const svg = document.createElementNS(SVG_NS, 'svg');
    svg.setAttribute('class', 'xray-svg-overlay');
    svg.setAttribute('aria-hidden', 'true');
    svg.style.cssText = 'position:absolute;left:0;top:0;width:100%;height:100%;pointer-events:none;overflow:hidden;z-index:6';
    host.appendChild(svg);
    this.svg = svg;
    this.refreshMatrices();
  }

  /** A named group, created on first use. Layers draw in creation order (later on top). */
  layer(name: string): SVGGElement {
    let g = this.layers.get(name);
    if (!g) {
      g = document.createElementNS(SVG_NS, 'g');
      g.setAttribute('data-layer', name);
      this.svg.appendChild(g);
      this.layers.set(name, g);
    }
    return g;
  }

  project(p: Point3, out?: ScreenPoint): ScreenPoint {
    const [x, y, z] = Array.isArray(p) ? (p as readonly [number, number, number]) : [(p as { x: number }).x, (p as { y: number }).y, (p as { z: number }).z];
    return projectToScreen(this.viewProj.elements, this.width, this.height, x, y, z, out);
  }

  onUpdate(cb: (ov: Overlay) => void): () => void {
    this.listeners.add(cb);
    this.dirty = true;
    return () => this.listeners.delete(cb);
  }

  invalidate(): void {
    this.dirty = true;
  }

  private refreshMatrices(): void {
    const cam = this.app.renderer.camera;
    this.width = Math.max(1, this.app.canvas.clientWidth);
    this.height = Math.max(1, this.app.canvas.clientHeight);
    cam.updateMatrixWorld();
    this.viewProj.multiplyMatrices(cam.projectionMatrix, cam.matrixWorldInverse);
    this.refreshChrome();
  }

  private refreshChrome(): void {
    const c = this.app.canvas.getBoundingClientRect();
    const ins: Insets = { top: 0, right: 0, bottom: 0, left: 0 };
    for (const sel of EDGE_CHROME) {
      const e = document.querySelector(sel);
      if (!shown(e)) continue;
      const r = e.getBoundingClientRect();
      if (!r.width || !r.height || r.right <= c.left || r.left >= c.right || r.bottom <= c.top || r.top >= c.bottom) continue;
      if (r.height >= c.height * 0.6) {
        if (r.left - c.left < c.right - r.right) ins.left = Math.max(ins.left, r.right - c.left);
        else ins.right = Math.max(ins.right, c.right - r.left);
      } else if (r.bottom >= c.bottom - 1) ins.bottom = Math.max(ins.bottom, c.bottom - r.top);
      else if (r.top <= c.top + 1) ins.top = Math.max(ins.top, r.bottom - c.top);
    }
    this.insets = ins;
    const g = document.getElementById('xray-gizmo');
    const gr = shown(g) ? g.getBoundingClientRect() : null;
    this.gizmo = gr && gr.width ? { x: gr.left - c.left, y: gr.top - c.top, w: gr.width, h: gr.height } : null;
    const res = insetRects(this.width, this.height, ins);
    if (this.gizmo) res.push(this.gizmo);
    for (const e of Array.from(document.querySelectorAll(LEGENDS))) {
      const r = e.getBoundingClientRect();
      if (r.width > 0 && r.height > 0) res.push({ x: r.left - c.left, y: r.top - c.top, w: r.width, h: r.height });
    }
    for (const v of this.registry.values()) {
      const r = typeof v === 'function' ? v() : v;
      if (r && r.w > 0 && r.h > 0) res.push(r);
    }
    this.reserved = res;
  }

  /**
   * Reserve a rect of the view (canvas pixels) under `key`, or a function that returns it each frame; null removes it.
   * Labels and markers on the overlay keep out of it.
   */
  reserve(key: string, rect: Rect | (() => Rect | null) | null): void {
    if (rect) this.registry.set(key, rect);
    else this.registry.delete(key);
    this.dirty = true;
  }

  /** A spot for a label box of `w` x `h` centred on (x, y) that is clear of the reserved rects (see freeSpot). */
  place(x: number, y: number, w: number, h: number, opts?: SpotOptions): Spot | null {
    return freeSpot(x, y, w, h, this.reserved, { x: 0, y: 0, w: this.width, h: this.height }, opts);
  }

  /** Legend position (see legendSpot) for this overlay's size, chrome and gizmo. */
  legendSpot(w: number, h: number, stack = 0, colW = w): { x: number; y: number } {
    return legendSpot(this.width, this.height, this.insets, this.gizmo, w, h, stack, colW);
  }

  /** Per frame (after render): refresh the matrices and run the listeners when the view or the data changed. */
  update(): void {
    this.refreshMatrices();
    const e = this.viewProj.elements;
    const ins = this.insets;
    const gz = this.gizmo;
    let sig = `${this.width}x${this.height}|${ins.top},${ins.right},${ins.bottom},${ins.left}|${gz ? `${gz.x},${gz.y},${gz.w},${gz.h}` : '-'}`;
    for (const r of this.reserved) sig += `|${Math.round(r.x)},${Math.round(r.y)},${Math.round(r.w)},${Math.round(r.h)}`;
    // Element offsets (the exploded view) move anchored markup without a camera change.
    sig += `|o${(this.app.renderer as unknown as { offsetsVersion?: number }).offsetsVersion ?? 0}`;
    // A section changes what hides what (the dimming of attached outlines) without a camera change.
    sig += `|c${(this.app.renderer as unknown as { clipVersion?: number }).clipVersion ?? 0}`;
    for (let i = 0; i < 16; i++) sig += `,${e[i]!.toFixed(6)}`;
    if (!this.dirty && sig === this.signature) return;
    this.signature = sig;
    this.dirty = false;
    for (const l of this.listeners) l(this);
  }
}

const overlays = new WeakMap<ViewerApp, Overlay>();

/** The overlay of an app, created (and wired to the frame loop) on first use. */
export function getOverlay(app: ViewerApp): Overlay {
  let ov = overlays.get(app);
  if (!ov) {
    ov = new Overlay(app);
    overlays.set(app, ov);
    const plugin: AppPlugin = { name: 'overlay', afterFrame: () => ov!.update() };
    app.use(plugin);
  }
  return ov;
}

/** SVG element helper for tools drawing into a layer. */
export function svgEl<K extends keyof SVGElementTagNameMap>(tag: K, attrs: Record<string, string | number> = {}): SVGElementTagNameMap[K] {
  const e = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, String(v));
  return e;
}
