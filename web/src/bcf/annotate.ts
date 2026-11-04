// Layout of the viewer markup (topic pins and viewpoint annotations) as 2D draw operations. Pure: no DOM, no GPU.
// The same operations drive the live SVG overlay (pins.ts) and the snapshot burn-in (drawOps on a 2D canvas), so what
// the user sees on screen is what other BCF tools see in the snapshot.
//
// Points are IFC coordinates in the data and go through ifcToViewer before projection. Text box offsets are fractions of
// the view height, so they scale with the snapshot. Sizes are CSS pixels times `scale`.

import { dirIfcToViewer, ifcToViewer } from './model';
import type { BcfAnnotation, BcfAnnotationType, BcfCamera, BcfPin, BcfSnapshotView, Vec3 } from './model';

// ---------------------------------------------------------------- projection

export interface Projected {
  x: number;
  y: number;
  /** In front of the camera. */
  front: boolean;
  /** In front and inside the view. */
  visible: boolean;
  /** Screen direction from the view centre towards the point (also for points behind the camera). */
  dx: number;
  dy: number;
}

/** Project a viewer-frame point with a column-major view-projection matrix to pixels (y down). */
export function projectPoint(m: ArrayLike<number>, width: number, height: number, p: Vec3): Projected {
  const [x, y, z] = p;
  const cx = m[0]! * x + m[4]! * y + m[8]! * z + m[12]!;
  const cy = m[1]! * x + m[5]! * y + m[9]! * z + m[13]!;
  const cz = m[2]! * x + m[6]! * y + m[10]! * z + m[14]!;
  const cw = m[3]! * x + m[7]! * y + m[11]! * z + m[15]!;
  if (cw <= 1e-9) {
    // Behind the camera: only the direction means something (the clip x, y keep their sign before the divide).
    return { x: width / 2, y: height / 2, front: false, visible: false, dx: cx, dy: -cy };
  }
  const nx = cx / cw;
  const ny = cy / cw;
  const nz = cz / cw;
  const sx = (nx * 0.5 + 0.5) * width;
  const sy = (1 - (ny * 0.5 + 0.5)) * height;
  return { x: sx, y: sy, front: true, visible: Math.abs(nx) <= 1 && Math.abs(ny) <= 1 && nz >= -1 && nz <= 1, dx: sx - width / 2, dy: sy - height / 2 };
}

const sub = (a: Vec3, b: Vec3): Vec3 => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const cross = (a: Vec3, b: Vec3): Vec3 => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const dot = (a: Vec3, b: Vec3): number => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
function unit(a: Vec3): Vec3 | null {
  const l = Math.hypot(a[0], a[1], a[2]);
  return l > 1e-12 ? [a[0] / l, a[1] / l, a[2] / l] : null;
}

/** Column-major view-projection matrix of a perspective camera (OpenGL clip space, like three.js). */
export function viewProjection(eye: Vec3, dir: Vec3, up: Vec3, fovDeg: number, aspect: number, near = 0.05, far = 1e5): number[] {
  const f = unit(dir) ?? [0, 0, -1];
  let s = unit(cross(f, up));
  if (!s) s = unit(cross(f, Math.abs(f[1]) < 0.9 ? [0, 1, 0] : [1, 0, 0])) ?? [1, 0, 0];
  const u = cross(s, f);
  // View matrix rows: s, u, -f; translation -R * eye.
  const v = [s[0], u[0], -f[0], 0, s[1], u[1], -f[1], 0, s[2], u[2], -f[2], 0, -dot(s, eye), -dot(u, eye), dot(f, eye), 1];
  const t = 1 / Math.tan((fovDeg * Math.PI) / 360);
  const p = [t / aspect, 0, 0, 0, 0, t, 0, 0, 0, 0, -(far + near) / (far - near), -1, 0, 0, (-2 * far * near) / (far - near), 0];
  const out = new Array<number>(16).fill(0);
  for (let c = 0; c < 4; c++) for (let r = 0; r < 4; r++) {
    let sum = 0;
    for (let k = 0; k < 4; k++) sum += p[k * 4 + r]! * v[c * 4 + k]!;
    out[c * 4 + r] = sum;
  }
  return out;
}

/** The camera of a snapshot: the stored snapshot view, else the viewpoint camera with the image aspect. */
export function snapshotCamera(view: BcfSnapshotView | undefined, cam: BcfCamera | null): BcfSnapshotView | null {
  if (view) return view;
  if (!cam || cam.kind !== 'perspective') return null;
  return { position: cam.position, direction: cam.direction, up: cam.up, fov: cam.fov && cam.fov > 0 && cam.fov < 180 ? cam.fov : 60, aspect: cam.aspect ?? 1 };
}

/** A projector for an image of `width` x `height` taken by a snapshot camera (IFC frame), for viewer-frame points. */
export function snapshotProjector(view: BcfSnapshotView, shift: Vec3, width: number, height: number): (p: Vec3) => Projected {
  const eye = ifcToViewer(view.position, shift);
  const m = viewProjection(eye, dirIfcToViewer(view.direction), dirIfcToViewer(view.up), view.fov, width / height);
  return (p) => projectPoint(m, width, height, p);
}

// ---------------------------------------------------------------- draw operations

interface OpBase {
  /** Annotation guid or `pin:<topic guid>`, for hit testing. */
  key?: string;
  role?: 'pin' | 'box' | 'anchor' | 'edge' | 'line';
  alpha?: number;
}
export type DrawOp =
  | (OpBase & { op: 'line'; x1: number; y1: number; x2: number; y2: number; stroke: string; width: number; dash?: number[] })
  | (OpBase & { op: 'poly'; points: number[]; fill: string; stroke?: string; width?: number })
  | (OpBase & { op: 'circle'; x: number; y: number; r: number; fill: string; stroke?: string; width?: number; dash?: number[] })
  | (OpBase & { op: 'rect'; x: number; y: number; w: number; h: number; r: number; fill: string; stroke?: string; width?: number; dash?: number[] })
  | (OpBase & { op: 'text'; x: number; y: number; text: string; size: number; fill: string; align: 'start' | 'middle'; bold?: boolean });

export const MARKUP_FONT = 'ui-monospace, Menlo, Consolas, "DejaVu Sans Mono", monospace';
const CHAR_W = 0.6; // monospace advance, in em
const LINE_H = 1.3;
const WRAP = 34;

export const STYLE: Record<BcfAnnotationType, { stroke: string; fill: string; text: string }> = {
  callout: { stroke: '#ff7a2f', fill: 'rgba(14,18,24,0.92)', text: '#ffffff' },
  note: { stroke: '#b89400', fill: '#ffe97a', text: '#1d1a00' },
  arrow: { stroke: '#ff3d6e', fill: 'rgba(14,18,24,0.92)', text: '#ffffff' },
};
const PIN_FILL = '#e8483b';
const PIN_ACTIVE = '#3b9cff';
const MEASURE = '#ffd23f';
const HALO = 'rgba(10,14,20,0.8)';

/** Default text box offsets (fractions of the view height). */
export const DEFAULT_OFFSET: Record<BcfAnnotationType, [number, number]> = { callout: [0.1, -0.09], note: [0.05, -0.04], arrow: [-0.1, -0.08] };

/** Default offset of the n-th annotation of a viewpoint: the quadrant turns with n, so new boxes do not stack up. */
export function defaultOffset(type: BcfAnnotationType, n: number): [number, number] {
  const [x, y] = DEFAULT_OFFSET[type];
  const k = n % 4;
  const grow = 1 + 0.35 * Math.floor(n / 4);
  return [x * (k === 1 || k === 3 ? -1 : 1) * grow, y * (k >= 2 ? -1 : 1) * grow];
}

/** Word wrap at `width` characters; explicit line breaks stay. */
export function wrapText(text: string, width = WRAP): string[] {
  const out: string[] = [];
  for (const para of text.split(/\r?\n/)) {
    let line = '';
    for (const w of para.split(/\s+/).filter(Boolean)) {
      let word = w;
      while (word.length > width) {
        if (line) { out.push(line); line = ''; }
        out.push(word.slice(0, width));
        word = word.slice(width);
      }
      if (!line) line = word;
      else if (line.length + 1 + word.length <= width) line += ` ${word}`;
      else { out.push(line); line = word; }
    }
    out.push(line);
  }
  while (out.length > 1 && out[out.length - 1] === '') out.pop();
  return out;
}

export interface LayoutContext {
  width: number;
  height: number;
  /** Viewer-frame point to pixels. */
  project: (p: Vec3) => Projected;
  /** Viewer-frame point hidden behind geometry (optional). */
  occluded?: (p: Vec3) => boolean;
  /** IFC -> viewer shift (model originShift). */
  shift: Vec3;
  /** Size multiplier: 1 on screen (CSS px), larger for big snapshots. */
  scale?: number;
  /** Live view only: pixels along each edge covered by viewer chrome (status bar, tool drawer, rails). A pin there is
   *  drawn as an edge marker inside the free area. */
  insets?: { top: number; right: number; bottom: number; left: number };
}

/** Lines shown in an annotation box: the text, plus the measurement label when the text does not already hold it. */
export function annotationLines(a: BcfAnnotation): string[] {
  const lines = a.text.trim() ? wrapText(a.text) : [];
  const m = a.anchor.measurement;
  if (m && m.label && !a.text.includes(m.label)) lines.push(m.label);
  return lines;
}

/** Box geometry of an annotation around the box centre (cx, cy). */
export function boxSize(lines: string[], scale: number): { w: number; h: number; size: number; pad: number } {
  const size = 12 * scale;
  const pad = 6 * scale;
  const chars = Math.max(1, ...lines.map((l) => l.length));
  return { w: chars * size * CHAR_W + pad * 2, h: Math.max(1, lines.length) * size * LINE_H + pad * 2 - size * (LINE_H - 1), size, pad };
}

function clampToRect(x: number, y: number, r: { x: number; y: number; w: number; h: number }): [number, number] {
  return [Math.min(r.x + r.w, Math.max(r.x, x)), Math.min(r.y + r.h, Math.max(r.y, y))];
}

export function layoutAnnotation(a: BcfAnnotation, ctx: LayoutContext, opts: { selected?: boolean } = {}): DrawOp[] {
  const s = ctx.scale ?? 1;
  const ops: DrawOp[] = [];
  const st = STYLE[a.type];
  const key = a.guid;
  const m = a.anchor.measurement;
  if (m) {
    const pa = ctx.project(ifcToViewer(m.a, ctx.shift));
    const pb = ctx.project(ifcToViewer(m.b, ctx.shift));
    if (pa.front && pb.front) {
      ops.push({ op: 'line', x1: pa.x, y1: pa.y, x2: pb.x, y2: pb.y, stroke: HALO, width: 4 * s, key, role: 'line' });
      ops.push({ op: 'line', x1: pa.x, y1: pa.y, x2: pb.x, y2: pb.y, stroke: MEASURE, width: 2 * s, key, role: 'line' });
      for (const p of [pa, pb]) ops.push({ op: 'circle', x: p.x, y: p.y, r: 3.5 * s, fill: MEASURE, stroke: '#0b0f14', width: 1.5 * s, key, role: 'line' });
    }
  }
  const pv = ifcToViewer(a.anchor.point, ctx.shift);
  const A = ctx.project(pv);
  if (!A.front) return ops;
  const hidden = ctx.occluded?.(pv) ?? false;
  const lines = annotationLines(a);
  const box = boxSize(lines, s);
  const cx = A.x + a.offset[0] * ctx.height;
  const cy = A.y + a.offset[1] * ctx.height;
  const rect = { x: cx - box.w / 2, y: cy - box.h / 2, w: box.w, h: box.h };
  const hasBox = lines.length > 0 || a.type !== 'arrow';
  const [ex, ey] = hasBox ? clampToRect(A.x, A.y, rect) : [cx, cy];
  const strokeW = (opts.selected ? 3 : 2) * s;

  if (a.type === 'callout' || a.type === 'arrow') {
    ops.push({ op: 'line', x1: ex, y1: ey, x2: A.x, y2: A.y, stroke: HALO, width: strokeW + 2 * s, key, role: 'line' });
    ops.push({ op: 'line', x1: ex, y1: ey, x2: A.x, y2: A.y, stroke: st.stroke, width: strokeW, key, role: 'line' });
  }
  if (a.type === 'arrow') {
    const len = Math.hypot(A.x - ex, A.y - ey);
    if (len > 1) {
      const ux = (A.x - ex) / len;
      const uy = (A.y - ey) / len;
      const hl = 13 * s;
      const hw = 6 * s;
      const bx = A.x - ux * hl;
      const by = A.y - uy * hl;
      ops.push({ op: 'poly', points: [A.x, A.y, bx - uy * hw, by + ux * hw, bx + uy * hw, by - ux * hw], fill: st.stroke, stroke: HALO, width: 1 * s, key, role: 'line' });
    }
  } else {
    ops.push({ op: 'circle', x: A.x, y: A.y, r: 4.5 * s, fill: hidden ? 'rgba(14,18,24,0.6)' : st.stroke, stroke: hidden ? st.stroke : '#0b0f14', width: 1.5 * s, key, role: 'anchor', ...(hidden ? { dash: [2 * s, 2 * s] } : {}) });
  }
  if (hasBox) {
    ops.push({ op: 'rect', x: rect.x, y: rect.y, w: rect.w, h: rect.h, r: 4 * s, fill: st.fill, stroke: opts.selected ? '#ffffff' : st.stroke, width: opts.selected ? 2.5 * s : 1.5 * s, key, role: 'box' });
    lines.forEach((l, i) => {
      ops.push({ op: 'text', x: rect.x + box.pad, y: rect.y + box.pad + box.size * 0.8 + i * box.size * LINE_H, text: l, size: box.size, fill: st.text, align: 'start', key, role: 'box' });
    });
  }
  return ops;
}

/** A numbered pin. Behind geometry: faded with a dashed rim. Off screen: a marker at the view edge pointing towards it. */
export function layoutPin(pin: BcfPin, label: string, ctx: LayoutContext, opts: { active?: boolean; key?: string; edge?: boolean } = {}): DrawOp[] {
  const s = ctx.scale ?? 1;
  const key = opts.key;
  const fill = opts.active ? PIN_ACTIVE : PIN_FILL;
  const pv = ifcToViewer(pin.position, ctx.shift);
  const P = ctx.project(pv);
  const ops: DrawOp[] = [];
  const ins = ctx.insets ?? { top: 0, right: 0, bottom: 0, left: 0 };
  const inFree = P.visible && P.x >= ins.left && P.x <= ctx.width - ins.right && P.y >= ins.top && P.y <= ctx.height - ins.bottom;
  if (!inFree) {
    if (opts.edge === false && !P.visible) return ops;
    const margin = 16 * s;
    // The free area: the view minus the chrome along its edges.
    const cx0 = (ins.left + ctx.width - ins.right) / 2;
    const cy0 = (ins.top + ctx.height - ins.bottom) / 2;
    const hw = Math.max(1, (ctx.width - ins.left - ins.right) / 2 - margin);
    const hh = Math.max(1, (ctx.height - ins.top - ins.bottom) / 2 - margin);
    const dx = P.visible ? P.x - cx0 : P.dx;
    const dy = P.visible ? P.y - cy0 : P.dy;
    const l = Math.hypot(dx, dy);
    const ux = l > 1e-9 ? dx / l : 0;
    const uy = l > 1e-9 ? dy / l : 1;
    const t = Math.min(Math.abs(ux) > 1e-9 ? hw / Math.abs(ux) : Infinity, Math.abs(uy) > 1e-9 ? hh / Math.abs(uy) : Infinity);
    const x = cx0 + ux * t;
    const y = cy0 + uy * t;
    const r = 9 * s;
    ops.push({ op: 'poly', points: [x + ux * (r + 7 * s), y + uy * (r + 7 * s), x - uy * r * 0.7, y + ux * r * 0.7, x + uy * r * 0.7, y - ux * r * 0.7], fill, stroke: HALO, width: 1 * s, key, role: 'edge', alpha: 0.85 });
    ops.push({ op: 'circle', x, y, r, fill, stroke: '#ffffff', width: 1.5 * s, key, role: 'edge', alpha: 0.85 });
    ops.push({ op: 'text', x, y: y + 3.6 * s, text: label, size: 10 * s, fill: '#ffffff', align: 'middle', bold: true, key, role: 'edge', alpha: 0.85 });
    return ops;
  }
  const hidden = ctx.occluded?.(pv) ?? false;
  const alpha = hidden ? 0.45 : 1;
  const r = (opts.active ? 12.5 : 11) * s;
  const cy = P.y - r - 9 * s;
  ops.push({ op: 'poly', points: [P.x, P.y, P.x - r * 0.62, cy + r * 0.55, P.x + r * 0.62, cy + r * 0.55], fill, stroke: HALO, width: 1 * s, key, role: 'pin', alpha });
  ops.push({ op: 'circle', x: P.x, y: cy, r, fill, stroke: opts.active ? '#ffffff' : '#0b0f14', width: (opts.active ? 2.5 : 1.5) * s, key, role: 'pin', alpha, ...(hidden ? { dash: [3 * s, 2 * s] } : {}) });
  ops.push({ op: 'text', x: P.x, y: cy + 4.2 * s, text: label, size: (label.length > 2 ? 10 : 12) * s, fill: '#ffffff', align: 'middle', bold: true, key, role: 'pin', alpha });
  ops.push({ op: 'circle', x: P.x, y: P.y, r: 2.5 * s, fill: '#ffffff', stroke: '#0b0f14', width: 1 * s, key, role: 'pin', alpha });
  return ops;
}

/** Everything burned into a snapshot: the annotations of the viewpoint, then the topic pin (no edge marker). */
export function layoutSnapshot(pin: { pin: BcfPin; label: string } | null, annotations: readonly BcfAnnotation[], ctx: LayoutContext): DrawOp[] {
  const ops: DrawOp[] = [];
  for (const a of annotations) ops.push(...layoutAnnotation(a, ctx));
  if (pin) ops.push(...layoutPin(pin.pin, pin.label, ctx, { edge: false }));
  return ops;
}

/** Size multiplier for a snapshot of this height (CSS pixel sizes look right up to about 600 px high). */
export function snapshotScale(height: number): number {
  return Math.min(3, Math.max(1, height / 600));
}

// ---------------------------------------------------------------- canvas renderer

/** The part of CanvasRenderingContext2D that drawOps uses (a mock records the calls in the tests). */
export interface Ctx2D {
  globalAlpha: number;
  fillStyle: unknown;
  strokeStyle: unknown;
  lineWidth: number;
  lineCap: string;
  lineJoin: string;
  font: string;
  textAlign: string;
  textBaseline: string;
  save(): void;
  restore(): void;
  beginPath(): void;
  closePath(): void;
  moveTo(x: number, y: number): void;
  lineTo(x: number, y: number): void;
  arc(x: number, y: number, r: number, a0: number, a1: number): void;
  arcTo(x1: number, y1: number, x2: number, y2: number, r: number): void;
  fill(): void;
  stroke(): void;
  fillText(text: string, x: number, y: number): void;
  setLineDash(d: number[]): void;
}

function roundRectPath(g: Ctx2D, x: number, y: number, w: number, h: number, r: number): void {
  const rr = Math.max(0, Math.min(r, w / 2, h / 2));
  g.beginPath();
  g.moveTo(x + rr, y);
  g.arcTo(x + w, y, x + w, y + h, rr);
  g.arcTo(x + w, y + h, x, y + h, rr);
  g.arcTo(x, y + h, x, y, rr);
  g.arcTo(x, y, x + w, y, rr);
  g.closePath();
}

/** Paint draw operations on a 2D canvas context, in order. */
export function drawOps(g: Ctx2D, ops: readonly DrawOp[]): void {
  for (const o of ops) {
    g.save();
    g.globalAlpha = o.alpha ?? 1;
    g.lineCap = 'round';
    g.lineJoin = 'round';
    g.setLineDash([]);
    switch (o.op) {
      case 'line':
        g.beginPath();
        g.moveTo(o.x1, o.y1);
        g.lineTo(o.x2, o.y2);
        if (o.dash) g.setLineDash(o.dash);
        g.strokeStyle = o.stroke;
        g.lineWidth = o.width;
        g.stroke();
        break;
      case 'poly':
        g.beginPath();
        for (let i = 0; i < o.points.length; i += 2) (i ? g.lineTo : g.moveTo).call(g, o.points[i]!, o.points[i + 1]!);
        g.closePath();
        g.fillStyle = o.fill;
        g.fill();
        if (o.stroke && o.width) {
          g.strokeStyle = o.stroke;
          g.lineWidth = o.width;
          g.stroke();
        }
        break;
      case 'circle':
        g.beginPath();
        g.arc(o.x, o.y, o.r, 0, Math.PI * 2);
        g.fillStyle = o.fill;
        g.fill();
        if (o.stroke && o.width) {
          if (o.dash) g.setLineDash(o.dash);
          g.strokeStyle = o.stroke;
          g.lineWidth = o.width;
          g.stroke();
        }
        break;
      case 'rect':
        roundRectPath(g, o.x, o.y, o.w, o.h, o.r);
        g.fillStyle = o.fill;
        g.fill();
        if (o.stroke && o.width) {
          if (o.dash) g.setLineDash(o.dash);
          g.strokeStyle = o.stroke;
          g.lineWidth = o.width;
          g.stroke();
        }
        break;
      case 'text':
        g.font = `${o.bold ? '700 ' : ''}${o.size}px ${MARKUP_FONT}`;
        g.textAlign = o.align === 'middle' ? 'center' : 'left';
        g.textBaseline = 'alphabetic';
        g.fillStyle = o.fill;
        g.fillText(o.text, o.x, o.y);
        break;
    }
    g.restore();
  }
}
