// Drawing the plan cut (sectionCut.ts) as thin lines on a 2D canvas: shared by the model overlay on the sheet (viewer.ts) and the
// model side of the placement view (placeView.ts). One affine map takes plan metres to canvas pixels. Pure of the DOM except for the
// context it is given.

import { invertSim } from './placement';
import type { SheetPlacement, Vec2 } from './placement';
import type { PlanCut } from './sectionCut';

/** x' = a x + c y + e, y' = b x + d y + f. */
export interface Affine {
  a: number;
  b: number;
  c: number;
  d: number;
  e: number;
  f: number;
}

export const applyAffine = (m: Affine, x: number, y: number): Vec2 => [m.a * x + m.c * y + m.e, m.b * x + m.d * y + m.f];

/** The affine map through three images: of (0, 0), (1, 0) and (0, 1). */
export function affineFrom(o: Vec2, ex: Vec2, ey: Vec2): Affine {
  return { a: ex[0] - o[0], b: ex[1] - o[1], c: ey[0] - o[0], d: ey[1] - o[1], e: o[0], f: o[1] };
}

/** Plan metres to canvas pixels for a placed sheet, through the sheet's user space: `userToPx` is the viewer's own map. */
export function modelToPixels(p: SheetPlacement, userToPx: (ux: number, uy: number) => Vec2): Affine {
  const inv = invertSim(p.transform);
  const c = Math.cos(inv.rotation) * inv.scale;
  const s = Math.sin(inv.rotation) * inv.scale;
  const user = (x: number, y: number): Vec2 => [c * x - s * y + inv.tx, s * x + c * y + inv.ty];
  const o = userToPx(...user(0, 0));
  const ex = userToPx(...user(1, 0));
  const ey = userToPx(...user(0, 1));
  return affineFrom(o, ex, ey);
}

export interface CutStyle {
  color: string;
  alpha: number;
  /** Line width in pixels. */
  width: number;
  /** Visible rectangle of the canvas (x0, y0, x1, y1): elements outside are skipped. */
  view?: [number, number, number, number];
  /** Elements to draw in the highlight colour (GlobalIds). */
  highlight?: ReadonlySet<string>;
  highlightColor?: string;
}

/** Stroke the outlines of a cut. Returns how many elements were drawn. */
export function drawCut(g: CanvasRenderingContext2D, cut: PlanCut | null | undefined, m: Affine, st: CutStyle): number {
  if (!cut) return 0;
  g.save();
  g.globalAlpha = st.alpha;
  g.lineWidth = st.width;
  g.lineJoin = 'round';
  g.lineCap = 'round';
  let n = 0;
  const visible = (b: [number, number, number, number]): boolean => {
    if (!st.view) return true;
    const p = [applyAffine(m, b[0], b[1]), applyAffine(m, b[2], b[1]), applyAffine(m, b[2], b[3]), applyAffine(m, b[0], b[3])];
    const x0 = Math.min(...p.map((q) => q[0])), x1 = Math.max(...p.map((q) => q[0])), y0 = Math.min(...p.map((q) => q[1])), y1 = Math.max(...p.map((q) => q[1]));
    return !(x1 < st.view[0] || x0 > st.view[2] || y1 < st.view[1] || y0 > st.view[3]);
  };
  const stroke = (hl: boolean): void => {
    g.beginPath();
    let any = false;
    for (const e of cut.elements) {
      if ((st.highlight?.has(e.guid) ?? false) !== hl || !visible(e.box)) continue;
      any = true;
      n++;
      for (const q of e.polys) {
        const k = q.pts.length / 2;
        if (k < 2) continue;
        const p0 = applyAffine(m, q.pts[0]!, q.pts[1]!);
        g.moveTo(p0[0], p0[1]);
        for (let i = 1; i < k; i++) { const p = applyAffine(m, q.pts[i * 2]!, q.pts[i * 2 + 1]!); g.lineTo(p[0], p[1]); }
        if (q.closed) g.closePath();
      }
    }
    if (!any) return;
    g.strokeStyle = hl ? st.highlightColor ?? st.color : st.color;
    g.stroke();
  };
  stroke(false);
  if (st.highlight?.size) stroke(true);
  g.restore();
  return n;
}
