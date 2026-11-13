// Layout of sheet sketches: where the text box of a text or callout markup sits on the page, and the draw operations of any markup
// on a displayed page. Shared by the sheet viewer (live), the snapshot of a raised issue and the PDF export (which needs the box
// rectangle of text and callouts), so all three agree. Pure: no DOM.
//
// Everything here is in displayed-page points (x right, y down, origin at the top left of the displayed page) unless the name
// says user space. The caller converts with model.ts. Shapes go through layoutMarkupFull (src/markup/layout.ts), the layout that
// draws the 3D view and the markup PDF; anchored kinds (text, callout) are laid out here because their anchor is a page point.

import { boxSize, wrapText } from '../bcf/annotate';
import type { DrawOp } from '../bcf/annotate';
import { layoutMarkupFull } from '../markup/layout';
import type { MarkupLayout } from '../markup/layout';
import { COLOURS, isAnchorKind } from '../markup/model';
import type { Markup } from '../markup/model';
import { rectCorners } from '../markup/geometry';
import type { Sheet } from './model';
import { pointsToDisplay, sheetUnit, userToDisplay } from './model';

const LINE_H = 1.3;
const INK = '#111111';
const PAPER = 'rgba(255,255,255,0.95)';

export interface BoxRect {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface AnchorGeometry {
  /** The anchor on the displayed page, points. */
  anchor: [number, number];
  /** The text box on the displayed page, points. */
  box: BoxRect;
  lines: string[];
  /** Text size and padding, points. */
  size: number;
  pad: number;
  /** Where the leader line leaves the box: the point of the box nearest the anchor. */
  edge: [number, number];
}

/** The text lines of a text or callout markup (never none: an empty box still shows). */
export function textLines(m: Markup): string[] {
  return m.text.trim() ? wrapText(m.text.trim()) : [''];
}

/** The box of a text or callout markup on the displayed page. Null for a markup without an anchor. */
export function anchorGeometry(m: Markup, sheet: Pick<Sheet, 'widthPt' | 'heightPt' | 'rotation' | 'box'>): AnchorGeometry | null {
  if (!isAnchorKind(m.kind) || !m.anchor) return null;
  const A = userToDisplay(sheet, m.anchor.point[0], m.anchor.point[1]);
  const lines = textLines(m);
  const bs = boxSize(lines, sheetUnit(sheet));
  const off = m.offset ?? [0.1, -0.09];
  const cx = A[0] + off[0] * sheet.heightPt;
  const cy = A[1] + off[1] * sheet.heightPt;
  const box = { x: cx - bs.w / 2, y: cy - bs.h / 2, w: bs.w, h: bs.h };
  const edge: [number, number] = [Math.min(box.x + box.w, Math.max(box.x, A[0])), Math.min(box.y + box.h, Math.max(box.y, A[1]))];
  return { anchor: A, box, lines, size: bs.size, pad: bs.pad, edge };
}

/** The offset (fractions of the page height) that puts the centre of a text box at `centre`, from an anchor (displayed page). */
export function offsetFor(sheet: Pick<Sheet, 'heightPt'>, anchor: readonly [number, number], centre: readonly [number, number]): [number, number] {
  const h = sheet.heightPt || 1;
  return [(centre[0] - anchor[0]) / h, (centre[1] - anchor[1]) / h];
}

/** The next box offset: the quadrant turns, so new boxes do not stack. */
export function nextOffset(count: number, kind: 'text' | 'callout'): [number, number] {
  const base: [number, number] = kind === 'text' ? [0.05, -0.04] : [0.1, -0.09];
  const k = count % 4;
  const grow = 1 + 0.35 * Math.floor(count / 4);
  return [base[0] * (k === 1 || k === 3 ? -1 : 1) * grow, base[1] * (k >= 2 ? -1 : 1) * grow];
}

export interface SheetLayoutOptions {
  /** Pixels per point of the displayed page. */
  scale: number;
  selected?: boolean;
  faded?: boolean;
  /** No number badge (a snapshot of an issue keeps them; the live view does too). */
  noBadge?: boolean;
}

/** A markup whose shape is in displayed-page fractions, so layoutMarkupFull draws it straight. */
function toFractions(m: Markup, sheet: Pick<Sheet, 'widthPt' | 'heightPt' | 'rotation' | 'box'>): Markup | null {
  const sh = m.shape;
  if (!sh) return null;
  const flat = sh.points.flatMap((p) => [p[0], p[1]]);
  const d = pointsToDisplay(sheet, flat);
  const pts: Array<[number, number]> = [];
  for (let i = 0; i < d.length; i += 2) pts.push([d[i]! / sheet.widthPt, d[i + 1]! / sheet.heightPt]);
  return { ...m, shape: { points: pts, depth: 1 }, attach: { kind: 'none' } };
}

/**
 * The draw operations of one markup on a displayed page, in pixels from the page's top left corner (`scale` pixels per point),
 * and its hit outline. Stroke widths, text and badges are in drawing units (sheetUnit) so they grow with the sheet.
 */
export function layoutSheetMarkup(m: Markup, sheet: Pick<Sheet, 'widthPt' | 'heightPt' | 'rotation' | 'box'>, o: SheetLayoutOptions): MarkupLayout {
  const s = o.scale * sheetUnit(sheet);
  const W = sheet.widthPt * o.scale;
  const H = sheet.heightPt * o.scale;
  const hex = m.hex ?? COLOURS[m.colour];
  const fade = o.faded ? 0.55 : 1;
  if (isAnchorKind(m.kind)) {
    const g = anchorGeometry(m, sheet);
    if (!g) return { ops: [] };
    const k = o.scale;
    const ops: DrawOp[] = [];
    const key = m.id;
    const [ax, ay] = [g.anchor[0] * k, g.anchor[1] * k];
    const box = { x: g.box.x * k, y: g.box.y * k, w: g.box.w * k, h: g.box.h * k };
    if (m.kind === 'callout') {
      const ex = g.edge[0] * k;
      const ey = g.edge[1] * k;
      ops.push({ op: 'line', x1: ex, y1: ey, x2: ax, y2: ay, stroke: hex, width: 2 * s, key, role: 'line' });
    }
    ops.push({ op: 'circle', x: ax, y: ay, r: 4.5 * s, fill: hex, stroke: '#ffffff', width: 1.5 * s, key, role: 'anchor' });
    ops.push({ op: 'rect', x: box.x, y: box.y, w: box.w, h: box.h, r: 4 * s, fill: PAPER, stroke: o.selected ? '#3b9cff' : hex, width: (o.selected ? 2.5 : 1.5) * s, key, role: 'box' });
    const size = g.size * k;
    const pad = g.pad * k;
    g.lines.forEach((l, i) => ops.push({ op: 'text', x: box.x + pad, y: box.y + pad + size * 0.8 + i * size * LINE_H, text: l, size, fill: INK, align: 'start', key, role: 'box' }));
    if (!o.noBadge) {
      const label = String(m.number);
      ops.push({ op: 'circle', x: box.x, y: box.y, r: 9 * s, fill: hex, stroke: '#ffffff', width: 1.5 * s, key, role: 'badge' });
      ops.push({ op: 'text', x: box.x, y: box.y + (label.length > 2 ? 3 : 4) * s, text: label, size: (label.length > 2 ? 9 : 11) * s, fill: m.colour === 'yellow' && !m.hex ? INK : '#ffffff', align: 'middle', bold: true, key, role: 'badge' });
    }
    const out = fade === 1 ? ops : ops.map((p) => ({ ...p, alpha: (p.alpha ?? 1) * fade }) as DrawOp);
    return { ops: out, hit: { pts: rectCorners([box.x, box.y], [box.x + box.w, box.y + box.h]), closed: true, filled: true } };
  }
  const t = toFractions(m, sheet);
  if (!t) return { ops: [] };
  const ctx = {
    width: W, height: H, shift: [0, 0, 0] as [number, number, number], scale: s, shapeDirect: true,
    project: () => ({ x: 0, y: 0, front: false, depth: 0 }),
  };
  const L = layoutMarkupFull(t, ctx as never, { selected: o.selected ?? false, faded: o.faded ?? false });
  if (o.noBadge) L.ops = L.ops.filter((p) => p.role !== 'badge');
  return L;
}
