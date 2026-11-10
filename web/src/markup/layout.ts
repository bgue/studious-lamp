// Layout of markups as draw operations (src/bcf/annotate.ts DrawOp), so the live overlay and the burned page of the PDF
// draw the same thing. Shapes are points as fractions of the view of the set's camera on a plane `depth` metres along its
// view direction (shapePointWorld), then projected with whatever camera the layout context has: with the set's camera
// they sit exactly where they were drawn, from another camera they stay on the model area they mark. Anchored kinds
// (text, callout, pointer, measurement) reuse layoutAnnotation, the BCF callout layout. Pure: no DOM.

import { boxSize, layoutAnnotation, shapeFraction, shapePointWorld, wrapText } from '../bcf/annotate';
import type { DrawOp, LayoutContext } from '../bcf/annotate';
import { dirIfcToViewer, ifcToViewer } from '../bcf/model';
import type { BcfAnnotation, BcfSnapshotView, Vec3 } from '../bcf/model';
import { freeSpot } from '../ui/reserved';
import { arrowHead, bounds, cloudOutline, rectCorners } from './geometry';
import { COLOURS, KIND_LABEL, isAnchorKind, strokePx } from './model';
import type { Markup } from './model';

const LINE_H = 1.3;
const INK = '#111111';
const PAPER = 'rgba(255,255,255,0.95)';
export const SELECT_COLOUR = '#3b9cff';

export function rgba(hex: string, a: number): string {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
}

/** The BCF annotation of an anchored markup, so layoutAnnotation draws it. */
export function markupToAnnotation(m: Markup): BcfAnnotation {
  return {
    guid: m.id,
    type: m.kind === 'text' ? 'note' : m.kind === 'pointer' ? 'arrow' : 'callout',
    text: m.text,
    anchor: m.anchor!,
    offset: m.offset ?? [0.1, -0.09],
  };
}

/** Pixels (flat) of fraction points under the layout context, or null when one is behind the camera. */
export function fractionsToPixels(points: ReadonlyArray<readonly [number, number]>, depth: number, ctx: LayoutContext): number[] | null {
  const out: number[] = [];
  if (ctx.shapeDirect) {
    for (const [u, v] of points) out.push(u * ctx.width, v * ctx.height);
    return out;
  }
  const view = ctx.shapeView;
  if (!view) return null;
  for (const [u, v] of points) {
    const q = ctx.project(shapePointWorld(view, ctx.shift, u, v, depth));
    if (!q.front) return null;
    out.push(q.x, q.y);
  }
  return out;
}

/**
 * The 4 corners (top left, top right, bottom right, bottom left, in the first corner's sense) of a box shape: 2 opposite
 * points give the axis-aligned box; 4 points are the corners themselves (a box seen from another camera is a quad).
 */
export function boxCorners(P: ReadonlyArray<readonly [number, number]>): Array<[number, number]> {
  if (P.length >= 4) return P.slice(0, 4).map((p) => [p[0], p[1]] as [number, number]);
  return [[P[0]![0], P[0]![1]], [P[1]![0], P[0]![1]], [P[1]![0], P[1]![1]], [P[0]![0], P[1]![1]]];
}

/** Points of an ellipse inscribed in the quad of 4 corners (bilinear map of the unit circle), as fractions. */
export function ellipseInQuad(c: ReadonlyArray<readonly [number, number]>, n = 56): Array<[number, number]> {
  const out: Array<[number, number]> = [];
  for (let i = 0; i < n; i++) {
    const t = (i / n) * Math.PI * 2;
    const a = 0.5 + 0.5 * Math.cos(t);
    const b = 0.5 + 0.5 * Math.sin(t);
    const w = [(1 - a) * (1 - b), a * (1 - b), a * b, (1 - a) * b];
    out.push([w[0]! * c[0]![0] + w[1]! * c[1]![0] + w[2]! * c[2]![0] + w[3]! * c[3]![0], w[0]! * c[0]![1] + w[1]! * c[1]![1] + w[2]! * c[2]![1] + w[3]! * c[3]![1]]);
  }
  return out;
}

export interface MarkupLayout {
  ops: DrawOp[];
  /** Pixel outline for hit testing (shapes), and whether it is closed and filled (a click inside counts). */
  hit?: { pts: number[]; closed: boolean; filled: boolean };
}

export interface MarkupLayoutOptions {
  selected?: boolean;
  /** Draw faded (the camera is away from the view the markup was made in). */
  faded?: boolean;
}

/** The 2D box a label of a shape goes in: right of the number badge, above the top-left corner of the shape. */
function labelOps(m: Markup, minX: number, minY: number, ctx: LayoutContext, s: number, r: number): DrawOp[] {
  const lines = m.text.trim() ? wrapText(m.text) : [];
  if (!lines.length) return [];
  const box = boxSize(lines, s);
  const hex = COLOURS[m.colour];
  let cx = minX + r + 3 * s + box.w / 2 + (m.offset?.[0] ?? 0) * ctx.height;
  let cy = minY - box.h / 2 - 4 * s + (m.offset?.[1] ?? 0) * ctx.height;
  let moved = false;
  if (ctx.reserved?.length) {
    const sp = freeSpot(cx, cy, box.w, box.h, ctx.reserved, { x: 0, y: 0, w: ctx.width, h: ctx.height });
    if (sp) { cx = sp.x; cy = sp.y; moved = sp.moved; }
  }
  const rect = { x: cx - box.w / 2, y: cy - box.h / 2, w: box.w, h: box.h };
  const ops: DrawOp[] = [];
  if (moved) ops.push({ op: 'line', x1: rect.x, y1: rect.y + rect.h, x2: minX, y2: minY, stroke: hex, width: 1.5 * s, dash: [4 * s, 3 * s], key: m.id, role: 'line' });
  ops.push({ op: 'rect', x: rect.x, y: rect.y, w: rect.w, h: rect.h, r: 4 * s, fill: PAPER, stroke: hex, width: 1.5 * s, key: m.id, role: 'box' });
  lines.forEach((l, i) => ops.push({ op: 'text', x: rect.x + box.pad, y: rect.y + box.pad + box.size * 0.8 + i * box.size * LINE_H, text: l, size: box.size, fill: INK, align: 'start', key: m.id, role: 'box' }));
  return ops;
}

function badge(m: Markup, x: number, y: number, s: number): DrawOp[] {
  const hex = COLOURS[m.colour];
  const label = String(m.number);
  const dark = m.colour === 'yellow';
  return [
    { op: 'circle', x, y, r: 9 * s, fill: hex, stroke: '#ffffff', width: 1.5 * s, key: m.id, role: 'badge' },
    { op: 'text', x, y: y + (label.length > 2 ? 3 : 4) * s, text: label, size: (label.length > 2 ? 9 : 11) * s, fill: dark ? INK : '#ffffff', align: 'middle', bold: true, key: m.id, role: 'badge' },
  ];
}

function selectBox(minX: number, minY: number, maxX: number, maxY: number, s: number, key: string): DrawOp {
  const pad = 7 * s;
  return { op: 'rect', x: minX - pad, y: minY - pad, w: maxX - minX + 2 * pad, h: maxY - minY + 2 * pad, r: 3 * s, fill: 'rgba(0,0,0,0)', stroke: SELECT_COLOUR, width: 1.5 * s, dash: [5 * s, 4 * s], key, role: 'select' };
}

/** All draw operations of one markup (shape, label, number badge), and its hit outline. */
export function layoutMarkupFull(m: Markup, ctx: LayoutContext, opts: MarkupLayoutOptions = {}): MarkupLayout {
  const s = ctx.scale ?? 1;
  const hex = COLOURS[m.colour];
  const fade = (ops: DrawOp[]): DrawOp[] => {
    const f = (m.status === 'resolved' ? 0.5 : 1) * (opts.faded ? 0.55 : 1);
    return f === 1 ? ops : ops.map((o) => ({ ...o, alpha: (o.alpha ?? 1) * f }));
  };

  if (isAnchorKind(m.kind)) {
    if (!m.anchor) return { ops: [] };
    const ann = markupToAnnotation(m);
    const c2: LayoutContext = { ...ctx, style: () => ({ stroke: hex, fill: PAPER, text: INK }) };
    const ops = layoutAnnotation(ann, c2, { selected: opts.selected });
    if (!ops.length) return { ops };
    const box = ops.find((o) => o.op === 'rect' && o.role === 'box') as Extract<DrawOp, { op: 'rect' }> | undefined;
    const tip = ops.find((o) => o.op === 'poly') as Extract<DrawOp, { op: 'poly' }> | undefined;
    const at = box ? [box.x, box.y] : tip ? [tip.points[0]! + 11 * s, tip.points[1]! - 11 * s] : null;
    if (at) ops.push(...badge(m, at[0]!, at[1]!, s));
    // Hit outline: the box, else the anchor.
    const hit = box ? { pts: rectCorners([box.x, box.y], [box.x + box.w, box.y + box.h]), closed: true, filled: true } : undefined;
    return { ops: fade(ops), ...(hit ? { hit } : {}) };
  }

  const shape = m.shape;
  if (!shape) return { ops: [] };
  const P = shape.points;
  let px: number[] | null;
  let closed = false;
  let fillable = false;
  let outline: number[] | null = null; // what is stroked (cloud outline replaces the base polygon)
  switch (m.kind) {
    case 'rect':
    case 'highlightBox': {
      px = fractionsToPixels(boxCorners(P), shape.depth, ctx);
      closed = true; fillable = true;
      break;
    }
    case 'ellipse': {
      px = fractionsToPixels(ellipseInQuad(boxCorners(P), 56), shape.depth, ctx);
      closed = true; fillable = true;
      break;
    }
    case 'cloud': {
      const base = fractionsToPixels(P.length === 2 ? boxCorners(P) : P, shape.depth, ctx);
      px = base;
      closed = true; fillable = true;
      if (base) outline = cloudOutline(base, { arc: (11 + m.weight * 3) * s });
      break;
    }
    case 'polygon':
      px = fractionsToPixels(P, shape.depth, ctx);
      closed = true; fillable = true;
      break;
    default:
      px = fractionsToPixels(P, shape.depth, ctx);
  }
  if (!px || px.length < 4) return { ops: [] };
  const stroke = strokePx(m.kind, m.weight) * s;
  const ops: DrawOp[] = [];
  const key = m.id;
  const fillCol = m.fill && fillable ? rgba(hex, 0.16) : undefined;
  switch (m.kind) {
    case 'highlight':
      ops.push({ op: 'path', points: px, stroke: hex, width: stroke, alpha: 0.5, blend: 'multiply', key, role: 'shape' });
      break;
    case 'highlightBox':
      ops.push({ op: 'poly', points: px, fill: hex, alpha: 0.55, blend: 'multiply', key, role: 'shape' });
      break;
    case 'arrow': {
      ops.push({ op: 'path', points: px, stroke: hex, width: stroke, key, role: 'shape' });
      const n = px.length;
      const head = arrowHead(px[n - 4]!, px[n - 3]!, px[n - 2]!, px[n - 1]!, (10 + m.weight * 3) * s, (4 + m.weight * 1.6) * s);
      if (head) ops.push({ op: 'poly', points: head, fill: hex, key, role: 'shape' });
      break;
    }
    case 'cloud':
      ops.push({ op: 'path', points: outline ?? px, stroke: hex, width: stroke, closed: true, ...(fillCol ? { fill: fillCol } : {}), key, role: 'shape' });
      break;
    default:
      ops.push({ op: 'path', points: px, stroke: hex, width: stroke, closed, ...(fillCol ? { fill: fillCol } : {}), key, role: 'shape' });
  }
  const bb = bounds(px);
  const r = 9 * s;
  ops.push(...labelOps(m, bb.x0, bb.y0, ctx, s, r));
  ops.push(...badge(m, bb.x0, bb.y0, s));
  if (opts.selected) ops.push(selectBox(bb.x0, bb.y0, bb.x1, bb.y1, s, key));
  return { ops: fade(ops), hit: { pts: px, closed, filled: m.kind === 'highlightBox' || (m.fill && fillable) } };
}

export function layoutMarkup(m: Markup, ctx: LayoutContext, opts: MarkupLayoutOptions = {}): DrawOp[] {
  return layoutMarkupFull(m, ctx, opts).ops;
}

/** Everything of a set, in markup order. */
export function layoutMarkups(list: readonly Markup[], ctx: LayoutContext, opts: { selected?: string | null; faded?: boolean } = {}): DrawOp[] {
  const ops: DrawOp[] = [];
  for (const m of list) ops.push(...layoutMarkup(m, ctx, { selected: m.id === opts.selected, faded: opts.faded }));
  return ops;
}

/** A short plain description: "Cloud 3" etc. */
export function markupName(m: Markup): string {
  return `${KIND_LABEL[m.kind]} ${m.number}`;
}

// ---------------------------------------------------------------- conversions between screen pixels and the shape plane

/**
 * The fractions (u right, v down) of the view of `view` where a ray (viewer frame) meets the plane `depth` metres along
 * that view's direction, or null when the ray is parallel to the plane or points away from it.
 */
export function rayToFraction(view: BcfSnapshotView, shift: Vec3, origin: Vec3, dir: Vec3, depth: number): { u: number; v: number } | null {
  const eye = ifcToViewer(view.position, shift);
  const f0 = dirIfcToViewer(view.direction);
  const fl = Math.hypot(f0[0], f0[1], f0[2]) || 1;
  const f: Vec3 = [f0[0] / fl, f0[1] / fl, f0[2] / fl];
  const den = dir[0] * f[0] + dir[1] * f[1] + dir[2] * f[2];
  if (Math.abs(den) < 1e-9) return null;
  const k = (depth - ((origin[0] - eye[0]) * f[0] + (origin[1] - eye[1]) * f[1] + (origin[2] - eye[2]) * f[2])) / den;
  if (k <= 0) return null;
  const p: Vec3 = [origin[0] + dir[0] * k, origin[1] + dir[1] * k, origin[2] + dir[2] * k];
  const q = shapeFraction(view, shift, p);
  return { u: q.u, v: q.v };
}

/**
 * Express a shape drawn in the view of `from` in the view of `to`, so it stays on the same model area: each point goes to
 * 3D on its plane (shapePointWorld) and back to screen fractions of the new camera (shapeFraction). The new plane is
 * perpendicular to the new view at the mean depth of the points (a shape cannot be tilted), which puts the shape exactly
 * where it was on the model as seen from the new camera. Null when a point is behind the new camera.
 */
export function rebaseShape(shape: { points: Array<[number, number]>; depth: number }, from: BcfSnapshotView, to: BcfSnapshotView, shift: Vec3, box = false): { points: Array<[number, number]>; depth: number } | null {
  const pts: Array<[number, number]> = [];
  let depthSum = 0;
  // A box seen from another camera is a quad: its 4 corners are re-projected (a box shape then holds 4 points).
  const src = box ? boxCorners(shape.points) : shape.points;
  for (const [u, v] of src) {
    const w = shapePointWorld(from, shift, u, v, shape.depth);
    const f = shapeFraction(to, shift, w);
    if (!(f.depth > 0.05) || !Number.isFinite(f.u) || !Number.isFinite(f.v)) return null;
    const r = (x: number): number => Math.round(x * 1e5) / 1e5;
    pts.push([r(f.u), r(f.v)]);
    depthSum += f.depth;
  }
  return { points: pts, depth: Math.round((depthSum / pts.length) * 1e4) / 1e4 };
}
