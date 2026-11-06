// 3-point alignment on screen: canvas clicks pick cloud and model points in turn (the state lives in the controller),
// the overlay draws the pairs as numbered markers in two colours with a line between the 2 points of each pair, and
// Escape undoes a pending point, then cancels the mode.
//
//   cloud point: cyan circle with its number      model point: orange square with its number
//   dashed line from the cloud point to its model point, the residual (after the solve) on the line

import type { ViewerApp } from '../app';
import { getOverlay, svgEl } from '../ui/overlay';
import type { Overlay, ScreenPoint } from '../ui/overlay';
import type { PointCloudController } from './controller';
import { apply, formatDistance } from './register';
import type { Vec3 } from './types';

export const CLOUD_COLOUR = '#38d0ff';
export const MODEL_COLOUR = '#ff9a2e';
const CLICK_SLOP = 5;

export class PairTool {
  private overlay: Overlay | null = null;
  private layer: SVGGElement | null = null;
  private down: { x: number; y: number } | null = null;
  private hover: { p: Vec3; kind: 'cloud' | 'model' } | null = null;
  private hoverPending: { x: number; y: number } | null = null;
  private raf = 0;
  private escOn = false;
  message = '';

  constructor(private readonly app: ViewerApp, private readonly c: PointCloudController) {
    const cv = app.canvas;
    cv.addEventListener('pointerdown', (e) => {
      if (this.c.pairMode) this.down = { x: e.clientX, y: e.clientY };
    }, true);
    cv.addEventListener('pointerup', (e) => this.onUp(e), true);
    cv.addEventListener('pointermove', (e) => this.onMove(e), true);
    cv.addEventListener('pointerleave', () => {
      this.hover = null;
      this.overlay?.invalidate();
    });
    c.onChange(() => this.sync());
  }

  private ensureOverlay(): Overlay {
    if (!this.overlay) {
      this.overlay = getOverlay(this.app);
      this.layer = this.overlay.layer('pointcloud-pairs');
      this.overlay.onUpdate((ov) => this.draw(ov));
    }
    return this.overlay;
  }

  /** Follow the controller: cursor, Escape handler, redraw. */
  private sync(): void {
    const on = this.c.pairMode;
    this.app.canvas.style.cursor = on ? 'crosshair' : this.app.canvas.style.cursor === 'crosshair' ? '' : this.app.canvas.style.cursor;
    if (on && !this.escOn) {
      window.addEventListener('keydown', this.onKey, true);
      this.escOn = true;
    } else if (!on && this.escOn) {
      window.removeEventListener('keydown', this.onKey, true);
      this.escOn = false;
      this.hover = null;
    }
    if (on || this.layer?.childNodes.length) this.ensureOverlay().invalidate();
  }

  // window capture runs before the toolbar's document handler: the first Escape acts here, not on the drawer
  private readonly onKey = (e: KeyboardEvent): void => {
    if (e.key !== 'Escape' || !this.c.pairMode) return;
    e.stopImmediatePropagation();
    e.preventDefault();
    const ps = this.c.pairs!;
    if (ps.length && this.c.pairStep === 'model') this.c.undoPair();
    else this.c.cancelPairs();
  };

  private onMove(e: PointerEvent): void {
    if (!this.c.pairMode || e.buttons !== 0) return;
    this.hoverPending = { x: e.clientX, y: e.clientY };
    if (this.raf) return;
    this.raf = requestAnimationFrame(() => {
      this.raf = 0;
      const h = this.hoverPending;
      if (!h || !this.c.pairMode) return;
      if (this.c.pairStep === 'cloud') {
        const p = this.c.pickCloudAt(h.x, h.y);
        this.hover = p ? { p: p.world, kind: 'cloud' } : null;
      } else {
        const p = this.c.pickModelAt(h.x, h.y);
        this.hover = p ? { p: p.point, kind: 'model' } : null;
      }
      this.ensureOverlay().invalidate();
    });
  }

  private onUp(e: PointerEvent): void {
    if (!this.c.pairMode || e.button !== 0 || !this.down) return;
    const moved = Math.hypot(e.clientX - this.down.x, e.clientY - this.down.y);
    this.down = null;
    if (moved > CLICK_SLOP) return; // an orbit drag
    // present the click to later listeners as a secondary button (no select), like the measure tool does
    try {
      Object.defineProperty(e, 'button', { value: 2 });
    } catch {
      /* the event stays as is */
    }
    this.clickAt(e.clientX, e.clientY);
  }

  /** One pick at a client position (also used by scripts and tests). Returns what was picked. */
  clickAt(clientX: number, clientY: number): 'cloud' | 'model' | null {
    if (!this.c.pairMode) return null;
    if (this.c.pairStep === 'cloud') {
      const p = this.c.pickCloudAt(clientX, clientY);
      if (!p) {
        this.c.noteExtra('No cloud point under the cursor.');
        return null;
      }
      this.c.addCloudPoint(p.cloud);
      return 'cloud';
    }
    const p = this.c.pickModelAt(clientX, clientY);
    if (!p) {
      this.c.noteExtra('No model surface under the cursor.');
      return null;
    }
    this.c.addModelPoint(p.point);
    return 'model';
  }

  private draw(ov: Overlay): void {
    const g = this.layer;
    if (!g) return;
    g.replaceChildren();
    const ps = this.c.pairs;
    if (!ps) return;
    const M = this.c.totalMatrix;
    const sol = this.c.pairSolution;
    const a: ScreenPoint = { x: 0, y: 0, visible: false, front: false, depth: 0 };
    const b: ScreenPoint = { x: 0, y: 0, visible: false, front: false, depth: 0 };
    const label = (x: number, y: number, text: string, colour: string): void => {
      const t = svgEl('text', { x: x + 9, y: y - 8, fill: colour, stroke: '#0b0f14', 'stroke-width': 3, 'paint-order': 'stroke', 'font-size': 13, 'font-weight': 700, 'font-family': 'system-ui,sans-serif' });
      t.textContent = text;
      g.appendChild(t);
    };
    const complete = this.c.solvedPairs;
    ps.forEach((pr, i) => {
      const n = String(i + 1);
      const cw = pr.cloud ? apply(M, pr.cloud) : null;
      if (cw) ov.project(cw, a);
      if (pr.model) ov.project(pr.model, b);
      if (cw && pr.model && a.front && b.front) {
        g.appendChild(svgEl('line', { x1: a.x, y1: a.y, x2: b.x, y2: b.y, stroke: 'rgba(10,14,20,0.7)', 'stroke-width': 4 }));
        g.appendChild(svgEl('line', { x1: a.x, y1: a.y, x2: b.x, y2: b.y, stroke: '#f2f6fb', 'stroke-width': 1.5, 'stroke-dasharray': '6 4', 'data-pair-line': n }));
        const k = complete.findIndex((q) => q.cloud === pr.cloud);
        const r = sol?.ok && k >= 0 ? sol.residuals[k] : undefined;
        if (r !== undefined) {
          const t = svgEl('text', { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 - 6, 'text-anchor': 'middle', fill: '#f2f6fb', stroke: '#0b0f14', 'stroke-width': 3, 'paint-order': 'stroke', 'font-size': 11, 'font-family': 'ui-monospace,Menlo,Consolas,monospace' });
          t.textContent = formatDistance(r);
          g.appendChild(t);
        }
      }
      if (cw && a.front) {
        g.appendChild(svgEl('circle', { cx: a.x, cy: a.y, r: 6, fill: CLOUD_COLOUR, stroke: '#0b0f14', 'stroke-width': 2, 'data-pair-cloud': n }));
        label(a.x, a.y, n, CLOUD_COLOUR);
      }
      if (pr.model && b.front) {
        g.appendChild(svgEl('rect', { x: b.x - 6, y: b.y - 6, width: 12, height: 12, fill: MODEL_COLOUR, stroke: '#0b0f14', 'stroke-width': 2, 'data-pair-model': n }));
        label(b.x, b.y, n, MODEL_COLOUR);
      }
    });
    if (this.hover) {
      ov.project(this.hover.p, a);
      if (a.front) {
        const col = this.hover.kind === 'cloud' ? CLOUD_COLOUR : MODEL_COLOUR;
        g.appendChild(svgEl('circle', { cx: a.x, cy: a.y, r: 9, fill: 'none', stroke: col, 'stroke-width': 2, 'data-pair-hover': this.hover.kind }));
      }
    }
  }
}
