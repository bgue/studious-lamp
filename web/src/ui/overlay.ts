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

import { Matrix4 } from 'three';
import type { AppPlugin, ViewerApp } from '../app';

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

export class Overlay {
  readonly svg: SVGSVGElement;
  width = 1;
  height = 1;
  private readonly layers = new Map<string, SVGGElement>();
  private readonly listeners = new Set<(ov: Overlay) => void>();
  private readonly viewProj = new Matrix4();
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
  }

  /** Per frame (after render): refresh the matrices and run the listeners when the view or the data changed. */
  update(): void {
    this.refreshMatrices();
    const e = this.viewProj.elements;
    let sig = `${this.width}x${this.height}`;
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
