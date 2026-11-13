// Layout of the viewer markup (topic pins and viewpoint annotations) as 2D draw operations. Pure: no DOM, no GPU.
// The same operations drive the live SVG overlay (pins.ts) and the snapshot burn-in (drawOps on a 2D canvas), so what
// the user sees on screen is what other BCF tools see in the snapshot.
//
// Points are IFC coordinates in the data and go through ifcToViewer before projection. Text box offsets are fractions of
// the view height, so they scale with the snapshot. Sizes are CSS pixels times `scale`.

import { dirIfcToViewer, ifcToViewer } from './model';
import { attachGuids, isSpatial, mostlyHidden, pickSamples, regionCorners, regionEdges } from './attach';
import type { LockState, SurfaceData } from './attach';
import type { BcfAnchor, BcfAnnotation, BcfAnnotationType, BcfCamera, BcfPin, BcfShape, BcfSnapshotView, Vec3 } from './model';
import { formatLength } from '../measure/maths';
import type { Units } from '../measure/maths';
import { freeSpot, rectsOverlap, underReserved } from '../ui/reserved';
import type { Rect } from '../ui/reserved';

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

/**
 * The viewer-frame point of a shape point given as fractions (u right, v down) of the view of `view`, on the plane at
 * `depth` metres along its view direction.
 */
export function shapePointWorld(view: BcfSnapshotView, shift: Vec3, u: number, v: number, depth: number): Vec3 {
  const eye = ifcToViewer(view.position, shift);
  const f = unit(dirIfcToViewer(view.direction)) ?? [0, 0, -1];
  const up = dirIfcToViewer(view.up);
  let s = unit(cross(f, up));
  if (!s) s = unit(cross(f, Math.abs(f[1]) < 0.9 ? [0, 1, 0] : [1, 0, 0])) ?? [1, 0, 0];
  const uu = cross(s, f);
  const ty = Math.tan((view.fov * Math.PI) / 360);
  const tx = ty * view.aspect;
  const x = (2 * u - 1) * tx * depth;
  const y = (1 - 2 * v) * ty * depth;
  return [eye[0] + f[0] * depth + s[0] * x + uu[0] * y, eye[1] + f[1] * depth + s[1] * x + uu[1] * y, eye[2] + f[2] * depth + s[2] * x + uu[2] * y];
}

/** Inverse of shapePointWorld: fractions of the view of `view` for a viewer-frame point, and its depth along the view. */
export function shapeFraction(view: BcfSnapshotView, shift: Vec3, p: Vec3): { u: number; v: number; depth: number } {
  const eye = ifcToViewer(view.position, shift);
  const f = unit(dirIfcToViewer(view.direction)) ?? [0, 0, -1];
  const m = viewProjection(eye, f, dirIfcToViewer(view.up), view.fov, view.aspect);
  const q = projectPoint(m, 1, 1, p);
  return { u: q.x, v: q.y, depth: dot(sub(p, eye), f) };
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
  role?: 'pin' | 'box' | 'anchor' | 'edge' | 'line' | 'shape' | 'badge' | 'select';
  alpha?: number;
  /** Compositing: `multiply` darkens what is under it (highlighter markers). */
  blend?: 'multiply';
}
export type DrawOp =
  | (OpBase & { op: 'line'; x1: number; y1: number; x2: number; y2: number; stroke: string; width: number; dash?: number[] })
  | (OpBase & { op: 'path'; points: number[]; stroke: string; width: number; closed?: boolean; fill?: string; dash?: number[] })
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
  rect: { stroke: '#ff3d6e', fill: 'rgba(14,18,24,0.92)', text: '#ffffff' },
  freehand: { stroke: '#ffb000', fill: 'rgba(14,18,24,0.92)', text: '#ffffff' },
};
/** Fill inside a rectangle highlight (the picture stays readable under it). */
const SHAPE_FILL: Record<string, string> = { rect: 'rgba(255,61,110,0.10)', freehand: 'rgba(255,176,0,0.08)' };
const PIN_FILL = '#e8483b';
const PIN_ACTIVE = '#3b9cff';
const MEASURE = '#ffd23f';
const HALO = 'rgba(10,14,20,0.8)';

/** Default text box offsets (fractions of the view height). */
export const DEFAULT_OFFSET: Record<BcfAnnotationType, [number, number]> = {
  callout: [0.1, -0.09], note: [0.05, -0.04], arrow: [-0.1, -0.08],
  // Shapes: the text box sits above the top-left corner of the shape.
  rect: [0, 0], freehand: [0, 0],
};

/** Default offset of the n-th annotation of a viewpoint: the quadrant turns with n, so new boxes do not stack up. */
export function defaultOffset(type: BcfAnnotationType, n: number): [number, number] {
  const [x, y] = DEFAULT_OFFSET[type];
  if (type === 'rect' || type === 'freehand') return [x, y];
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
  /**
   * Live view only: reserved rects (the edge chrome, the gizmo, legends; see ui/reserved.ts). Text boxes move out of them,
   * a pin whose point is under one is drawn beside it with a leader line, and edge markers keep out of them.
   */
  reserved?: readonly Rect[];
  /** Length unit of measurement labels (the measure tool's setting). Default metres. */
  units?: Units;
  /**
   * The current frame of an element by GlobalId (viewer frame): its bounds centre and its displacement (explode offset).
   * Element anchors with a `local` offset follow the element; without this, anchors stay at their stored point.
   */
  element?: (guid: string) => { centre: Vec3; offset: Vec3 } | null;
  /** View-lock state of the live camera against the viewpoint camera (live view only): fades or collapses view-locked shapes. */
  lock?: LockState;
  /** Live view: throttled test whether an attached outline (sample points, viewer frame) is behind other geometry. Absent: tested directly with `occluded`. */
  behind?: (key: string, samples: Vec3[]) => boolean;
  /** True when the element (GlobalId) is hidden or isolated away: shapes attached to it are drawn dimmed with a hint. */
  hidden?: (guid: string) => boolean;
  /** The camera of the viewpoint whose shapes are drawn (IFC frame): shapes go through it to 3D, then `project`. */
  shapeView?: BcfSnapshotView | null;
  /** The image is the view of that camera (a snapshot burn-in): shape fractions map straight to pixels. */
  shapeDirect?: boolean;
  /** Colours of an annotation's box and leader, replacing the BCF defaults (the markup tool colours by its palette). */
  style?: (a: BcfAnnotation) => { stroke: string; fill: string; text: string } | undefined;
  /**
   * The surface data to draw for a stored surface outline: the points projected onto the current surfaces when a revised model
   * reshaped the elements (src/bcf/reproject.ts), or null when the outline cannot land any more (detached: shown view-locked).
   * Absent: the stored data.
   */
  resolveSurface?: (s: SurfaceData) => SurfaceData | null;
}

const add3 = (a: Vec3, b: Vec3): Vec3 => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
const nonZero = (v: Vec3): boolean => Math.abs(v[0]) + Math.abs(v[1]) + Math.abs(v[2]) > 1e-9;

/**
 * Viewer-frame point of an anchor (or a pin, `position` as the point): an element anchor with a `local` offset is placed
 * relative to the element's current bounds centre, and every element anchor moves with the element's displacement.
 * `displaced`: the element is offset from its geometry (exploded), so the BVH occlusion test does not apply.
 */
export function anchorPoint(a: Pick<BcfAnchor, 'point' | 'elementGuid' | 'local'>, ctx: Pick<LayoutContext, 'shift' | 'element'>): { p: Vec3; displaced: boolean } {
  const base = ifcToViewer(a.point, ctx.shift);
  const f = a.elementGuid && ctx.element ? ctx.element(a.elementGuid) : null;
  if (!f) return { p: base, displaced: false };
  const p = a.local ? add3(f.centre, dirIfcToViewer(a.local)) : base;
  return { p: add3(p, f.offset), displaced: nonZero(f.offset) };
}

/** End points of a linked measurement (viewer frame), moved with their elements (element-to-element measurements). */
function measurePoints(m: NonNullable<BcfAnchor['measurement']>, ctx: LayoutContext): { a: Vec3; b: Vec3; displaced: boolean } {
  let a = ifcToViewer(m.a, ctx.shift);
  let b = ifcToViewer(m.b, ctx.shift);
  let displaced = false;
  const g = m.elementGuids;
  if (m.kind === 'element' && g && g.length === 2 && ctx.element) {
    const fa = ctx.element(g[0]!);
    const fb = ctx.element(g[1]!);
    if (fa) a = add3(a, fa.offset);
    if (fb) b = add3(b, fb.offset);
    displaced = (!!fa && nonZero(fa.offset)) || (!!fb && nonZero(fb.offset));
  }
  return { a, b, displaced };
}

/**
 * Lines shown in an annotation box: the text, plus the measurement length in the measure tool's unit when the text does
 * not already hold it. A text that is only the stored label (older links used it as the default text) counts as empty,
 * so the length follows the unit setting.
 */
export function annotationLines(a: BcfAnnotation, units: Units = 'm'): string[] {
  const m = a.anchor.measurement;
  let text = a.text;
  if (m) {
    const t = text.trim();
    if (t && (t === m.label.trim() || t === formatLength(m.distance, 'm') || t === formatLength(m.distance, 'mm'))) text = '';
  }
  const lines = text.trim() ? wrapText(text) : [];
  const label = m ? formatLength(m.distance, units) : '';
  if (label && !text.includes(label)) lines.push(label);
  return lines;
}

/** Keep a text box (centre cx, cy) out of the reserved rects. */
function boxSpot(cx: number, cy: number, w: number, h: number, ctx: LayoutContext): { x: number; y: number; moved: boolean } {
  if (!ctx.reserved?.length) return { x: cx, y: cy, moved: false };
  return freeSpot(cx, cy, w, h, ctx.reserved, { x: 0, y: 0, w: ctx.width, h: ctx.height }) ?? { x: cx, y: cy, moved: false };
}

/** Pixels of the points of a shape, or null when it cannot be drawn in this view. */
function shapePixels(shape: BcfShape, type: BcfAnnotationType, ctx: LayoutContext): number[] | null {
  const pts: Array<[number, number]> = type === 'rect' && shape.points.length === 2
    ? (() => {
      const [[u0, v0], [u1, v1]] = shape.points as [[number, number], [number, number]];
      return [[u0, v0], [u1, v0], [u1, v1], [u0, v1]] as Array<[number, number]>;
    })()
    : shape.points;
  const out: number[] = [];
  if (ctx.shapeDirect) {
    for (const [u, v] of pts) out.push(u * ctx.width, v * ctx.height);
    return out;
  }
  const view = ctx.shapeView;
  if (!view) return null;
  for (const [u, v] of pts) {
    const q = ctx.project(shapePointWorld(view, ctx.shift, u, v, shape.depth));
    if (!q.front) return null;
    out.push(q.x, q.y);
  }
  return out;
}

/** Pixel segments (flat x0 y0 x1 y1 ...) of an attached shape in 3D through the live camera, or null when it is not attached. */
function attachedSegments(a: BcfAnnotation, ctx: LayoutContext): { segs: number[][]; path: number[] | null; closed: boolean; samples: Vec3[] } | null {
  const att = a.attach;
  if (ctx.shapeDirect || !isSpatial(att)) return null;
  if (attachGuids(att).some((g) => ctx.element && !ctx.element(g))) return null; // detached: shown view-locked
  const proj = (p: Vec3): Projected => ctx.project(p);
  if (att.kind === 'region' && att.region) {
    const segs: number[][] = [];
    for (const [p, q] of regionEdges(att.region)) {
      const A = proj(ifcToViewer(p, ctx.shift));
      const B = proj(ifcToViewer(q, ctx.shift));
      if (A.front && B.front) segs.push([A.x, A.y, B.x, B.y]);
    }
    const cs = regionCorners(att.region).map((p) => ifcToViewer(p, ctx.shift));
    const mids = regionEdges(att.region).map(([p, q]) => ifcToViewer([(p[0] + q[0]) / 2, (p[1] + q[1]) / 2, (p[2] + q[2]) / 2], ctx.shift));
    return segs.length ? { segs, path: null, closed: false, samples: pickSamples([...cs, ...mids]) } : null;
  }
  if (att.kind === 'lines' && att.lines) {
    const segs: number[][] = [];
    for (const [p, q] of att.lines) {
      const A = proj(ifcToViewer(p, ctx.shift));
      const B = proj(ifcToViewer(q, ctx.shift));
      if (A.front && B.front) segs.push([A.x, A.y, B.x, B.y]);
    }
    return segs.length ? { segs, path: null, closed: false, samples: [] } : null;
  }
  if (att.surface) {
    const sd = ctx.resolveSurface ? ctx.resolveSurface(att.surface) : att.surface;
    if (!sd) return null; // detached: its surface no longer fits the model, shown view-locked
    const path: number[] = [];
    const world: Vec3[] = [];
    for (const sp of sd.pts) {
      const w = anchorPoint({ point: sp.p, elementGuid: sd.guids[sp.e], local: sp.l }, ctx).p;
      const q = proj(w);
      if (!q.front) return null;
      path.push(q.x, q.y);
      world.push(w);
    }
    return { segs: [], path, closed: sd.closed, samples: pickSamples(world) };
  }
  return null;
}

/** A rectangle or freehand highlight with its optional text box above the top-left corner. */
function layoutShape(a: BcfAnnotation, ctx: LayoutContext, opts: { selected?: boolean }): DrawOp[] {
  const s = ctx.scale ?? 1;
  const st = STYLE[a.type];
  const key = a.guid;
  const att3d = attachedSegments(a, ctx);
  const lock = att3d ? undefined : ctx.lock;
  const hiddenTarget = !!att3d && attachGuids(a.attach).some((g) => ctx.hidden?.(g));
  const alphaOf = (o: DrawOp, f: number): DrawOp => (f === 1 ? o : { ...o, alpha: (o.alpha ?? 1) * f });
  const px = att3d ? att3d.path : a.shape ? shapePixels(a.shape, a.type, ctx) : null;
  const w = (opts.selected ? 3.5 : 2.5) * s;
  const closed = att3d ? att3d.closed : a.type === 'rect';
  const ops: DrawOp[] = [];
  if (lock && (lock.mode === 'pin' || lock.mode === 'hidden')) return lock.mode === 'hidden' ? [] : shapePin(a, ctx, s, lock.pinAlpha, st.stroke);
  if (att3d && att3d.segs.length) {
    for (const g of att3d.segs) ops.push({ op: 'line', x1: g[0]!, y1: g[1]!, x2: g[2]!, y2: g[3]!, stroke: HALO, width: w + 2 * s, key, role: 'shape' }, { op: 'line', x1: g[0]!, y1: g[1]!, x2: g[2]!, y2: g[3]!, stroke: opts.selected ? '#ffffff' : st.stroke, width: w, key, role: 'shape' });
  } else {
    if (!px || px.length < 4) return [];
    ops.push(
      { op: 'path', points: px, stroke: HALO, width: w + 2 * s, closed, key, role: 'shape' },
      { op: 'path', points: px, stroke: opts.selected ? '#ffffff' : st.stroke, width: w, closed, ...(closed ? { fill: SHAPE_FILL[a.type] } : {}), key, role: 'shape' },
    );
  }
  const lines = a.text.trim() ? wrapText(a.text) : [];
  const flat = att3d?.segs.length ? att3d.segs.flat() : px!;
  if (lines.length) {
    let minX = Infinity;
    let minY = Infinity;
    for (let i = 0; i < flat.length; i += 2) {
      minX = Math.min(minX, flat[i]!);
      minY = Math.min(minY, flat[i + 1]!);
    }
    const box = boxSize(lines, s);
    const spot = boxSpot(minX + box.w / 2 + a.offset[0] * ctx.height, minY - box.h / 2 - 4 * s + a.offset[1] * ctx.height, box.w, box.h, ctx);
    const rect = { x: spot.x - box.w / 2, y: spot.y - box.h / 2, w: box.w, h: box.h };
    if (spot.moved) ops.push({ op: 'line', x1: rect.x, y1: rect.y + rect.h, x2: minX, y2: minY, stroke: st.stroke, width: 1.5 * s, dash: [4 * s, 3 * s], key, role: 'line' });
    ops.push({ op: 'rect', x: rect.x, y: rect.y, w: rect.w, h: rect.h, r: 4 * s, fill: st.fill, stroke: opts.selected ? '#ffffff' : st.stroke, width: opts.selected ? 2.5 * s : 1.5 * s, key, role: 'box' });
    lines.forEach((l, i) => {
      ops.push({ op: 'text', x: rect.x + box.pad, y: rect.y + box.pad + box.size * 0.8 + i * box.size * LINE_H, text: l, size: box.size, fill: st.text, align: 'start', key, role: 'box' });
    });
  }
  // Behind other geometry: dashed and faint instead of showing through.
  const behind = !!att3d && att3d.samples.length > 0 && (ctx.behind ? ctx.behind(key, att3d.samples) : mostlyHidden(att3d.samples, ctx.occluded));
  const f = (hiddenTarget || behind ? 0.35 : 1) * (lock && lock.mode === 'fade' ? lock.alpha : 1);
  const out = ops.map((o) => {
    const d = alphaOf(o, f);
    return behind && o.role === 'shape' ? ({ ...d, dash: [6 * s, 4 * s] } as DrawOp) : d;
  });
  if (lock && lock.mode === 'fade') out.push(...shapePin(a, ctx, s, lock.pinAlpha, st.stroke));
  return out;
}

/** The pin a view-locked shape collapses to: at its centroid on its old depth plane. Click: back to the viewpoint. */
function shapePin(a: BcfAnnotation, ctx: LayoutContext, s: number, alpha: number, fill: string): DrawOp[] {
  const view = ctx.shapeView;
  if (!a.shape || !view || alpha <= 0.01) return [];
  let u0 = Infinity, v0 = Infinity, u1 = -Infinity, v1 = -Infinity;
  for (const [u, v] of a.shape.points) { u0 = Math.min(u0, u); u1 = Math.max(u1, u); v0 = Math.min(v0, v); v1 = Math.max(v1, v); }
  const q = ctx.project(shapePointWorld(view, ctx.shift, (u0 + u1) / 2, (v0 + v1) / 2, a.shape.depth));
  if (!q.front) return [];
  const r = 8 * s;
  const key = `annpin:${a.guid}`;
  return [
    { op: 'poly', points: [q.x, q.y, q.x - r * 0.6, q.y - r * 1.4, q.x + r * 0.6, q.y - r * 1.4], fill, stroke: HALO, width: 1 * s, alpha, key, role: 'pin' },
    { op: 'circle', x: q.x, y: q.y - r * 1.8, r, fill, stroke: '#ffffff', width: 1.5 * s, alpha, key, role: 'pin' },
  ];
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
  if (a.type === 'rect' || a.type === 'freehand') return layoutShape(a, ctx, opts);
  const s = ctx.scale ?? 1;
  const ops: DrawOp[] = [];
  const st = ctx.style?.(a) ?? STYLE[a.type];
  const key = a.guid;
  const m = a.anchor.measurement;
  let mid: { p: Vec3; displaced: boolean } | null = null;
  if (m) {
    const { a: va, b: vb, displaced } = measurePoints(m, ctx);
    if (displaced) mid = { p: [(va[0] + vb[0]) / 2, (va[1] + vb[1]) / 2, (va[2] + vb[2]) / 2], displaced };
    const pa = ctx.project(va);
    const pb = ctx.project(vb);
    if (pa.front && pb.front) {
      ops.push({ op: 'line', x1: pa.x, y1: pa.y, x2: pb.x, y2: pb.y, stroke: HALO, width: 4 * s, key, role: 'line' });
      ops.push({ op: 'line', x1: pa.x, y1: pa.y, x2: pb.x, y2: pb.y, stroke: MEASURE, width: 2 * s, key, role: 'line' });
      for (const p of [pa, pb]) ops.push({ op: 'circle', x: p.x, y: p.y, r: 3.5 * s, fill: MEASURE, stroke: '#0b0f14', width: 1.5 * s, key, role: 'line' });
    }
  }
  // A measurement anchor is the middle of its (possibly displaced) dimension line; others resolve through their element.
  const anc = mid ?? anchorPoint(a.anchor, ctx);
  const pv = anc.p;
  const A = ctx.project(pv);
  if (!A.front) return ops;
  const hidden = !anc.displaced && (ctx.occluded?.(pv) ?? false);
  const lines = annotationLines(a, ctx.units);
  const box = boxSize(lines, s);
  const hasBox = lines.length > 0 || a.type !== 'arrow';
  const spot = hasBox ? boxSpot(A.x + a.offset[0] * ctx.height, A.y + a.offset[1] * ctx.height, box.w, box.h, ctx) : { x: A.x + a.offset[0] * ctx.height, y: A.y + a.offset[1] * ctx.height, moved: false };
  const cx = spot.x;
  const cy = spot.y;
  const rect = { x: cx - box.w / 2, y: cy - box.h / 2, w: box.w, h: box.h };
  const [ex, ey] = hasBox ? clampToRect(A.x, A.y, rect) : [cx, cy];
  const strokeW = (opts.selected ? 3 : 2) * s;

  // A note has no leader; one pushed out of a reserved rect gets a thin one back to its point.
  if (a.type === 'note' && spot.moved) ops.push({ op: 'line', x1: ex, y1: ey, x2: A.x, y2: A.y, stroke: st.stroke, width: 1.5 * s, dash: [4 * s, 3 * s], key, role: 'line' });
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

/** A numbered pin. Behind geometry: faded with a dashed rim. Off screen: a marker at the view edge pointing towards it.
 *  Live view: a pin whose point is under a reserved rect (the gizmo, a legend) is drawn beside it with a dashed leader
 *  line to the point, or as an edge marker when there is no free spot near; edge markers keep out of reserved rects. */
export function layoutPin(pin: BcfPin, label: string, ctx: LayoutContext, opts: { active?: boolean; key?: string; edge?: boolean } = {}): DrawOp[] {
  const s = ctx.scale ?? 1;
  const key = opts.key;
  const fill = opts.active ? PIN_ACTIVE : PIN_FILL;
  const anc = anchorPoint({ point: pin.position, elementGuid: pin.elementGuid, local: pin.local }, ctx);
  const pv = anc.p;
  const P = ctx.project(pv);
  const ops: DrawOp[] = [];
  const ins = ctx.insets ?? { top: 0, right: 0, bottom: 0, left: 0 };
  const res = ctx.reserved ?? [];
  const area = { x: 0, y: 0, w: ctx.width, h: ctx.height };
  const inFree = P.visible && P.x >= ins.left && P.x <= ctx.width - ins.right && P.y >= ins.top && P.y <= ctx.height - ins.bottom;
  const r = (opts.active ? 12.5 : 11) * s;
  const headY = P.y - r - 9 * s;
  // Under a reserved rect (or the head is): the head moves to the nearest free spot close by, with a leader line.
  let head: { x: number; y: number } | null = null;
  if (inFree && res.length) {
    const covered = underReserved(P.x, P.y, res);
    const headBox = { x: P.x - r, y: headY - r, w: 2 * r, h: 2 * r + 9 * s };
    if (covered || res.some((q) => rectsOverlap(headBox, q))) {
      const spot = freeSpot(P.x, headY, 2 * r + 4 * s, 2 * r + 4 * s, res, area, { maxShift: 160 * s });
      if (spot) head = spot;
      else if (covered) return layoutEdgeMarker(P, label, ctx, fill, key, s);
    }
  }
  if (!inFree) {
    if (opts.edge === false && !P.visible) return ops;
    return layoutEdgeMarker(P, label, ctx, fill, key, s);
  }
  const hidden = !anc.displaced && (ctx.occluded?.(pv) ?? false);
  const alpha = hidden ? 0.45 : 1;
  const hx = head ? head.x : P.x;
  const cy = head ? head.y : headY;
  if (head) {
    ops.push({ op: 'line', x1: P.x, y1: P.y, x2: hx, y2: cy, stroke: HALO, width: 3 * s, key, role: 'pin', alpha });
    ops.push({ op: 'line', x1: P.x, y1: P.y, x2: hx, y2: cy, stroke: fill, width: 1.5 * s, dash: [4 * s, 3 * s], key, role: 'pin', alpha });
  } else {
    ops.push({ op: 'poly', points: [P.x, P.y, P.x - r * 0.62, cy + r * 0.55, P.x + r * 0.62, cy + r * 0.55], fill, stroke: HALO, width: 1 * s, key, role: 'pin', alpha });
  }
  ops.push({ op: 'circle', x: hx, y: cy, r, fill, stroke: opts.active ? '#ffffff' : '#0b0f14', width: (opts.active ? 2.5 : 1.5) * s, key, role: 'pin', alpha, ...(hidden ? { dash: [3 * s, 2 * s] } : {}) });
  ops.push({ op: 'text', x: hx, y: cy + 4.2 * s, text: label, size: (label.length > 2 ? 10 : 12) * s, fill: '#ffffff', align: 'middle', bold: true, key, role: 'pin', alpha });
  ops.push({ op: 'circle', x: P.x, y: P.y, r: 2.5 * s, fill: '#ffffff', stroke: '#0b0f14', width: 1 * s, key, role: 'pin', alpha });
  return ops;
}

/** The marker at the edge of the free view (the view minus the edge chrome) in the direction of the pin. */
function layoutEdgeMarker(P: Projected, label: string, ctx: LayoutContext, fill: string, key: string | undefined, s: number): DrawOp[] {
  const ins = ctx.insets ?? { top: 0, right: 0, bottom: 0, left: 0 };
  const margin = 16 * s;
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
  let x = cx0 + ux * t;
  let y = cy0 + uy * t;
  const r = 9 * s;
  if (ctx.reserved?.length) {
    const spot = freeSpot(x, y, 2 * r + 16 * s, 2 * r + 16 * s, ctx.reserved, { x: 0, y: 0, w: ctx.width, h: ctx.height });
    if (spot) {
      x = spot.x;
      y = spot.y;
    }
  }
  return [
    { op: 'poly', points: [x + ux * (r + 7 * s), y + uy * (r + 7 * s), x - uy * r * 0.7, y + ux * r * 0.7, x + uy * r * 0.7, y - ux * r * 0.7], fill, stroke: HALO, width: 1 * s, key, role: 'edge', alpha: 0.85 },
    { op: 'circle', x, y, r, fill, stroke: '#ffffff', width: 1.5 * s, key, role: 'edge', alpha: 0.85 },
    { op: 'text', x, y: y + 3.6 * s, text: label, size: 10 * s, fill: '#ffffff', align: 'middle', bold: true, key, role: 'edge', alpha: 0.85 },
  ];
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
  globalCompositeOperation?: string;
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
    if (o.blend) g.globalCompositeOperation = o.blend;
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
      case 'path':
        g.beginPath();
        for (let i = 0; i < o.points.length; i += 2) (i ? g.lineTo : g.moveTo).call(g, o.points[i]!, o.points[i + 1]!);
        if (o.closed) g.closePath();
        if (o.fill) {
          g.fillStyle = o.fill;
          g.fill();
        }
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
