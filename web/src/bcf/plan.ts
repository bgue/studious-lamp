// Pure planning for BCF viewpoints: from a parsed viewpoint to a "plan" of what to do in the viewer (ids, hide set, colours,
// camera and clip planes in viewer coordinates), and from viewer state to a viewpoint. No three.js and no DOM, so the
// semantics (visibility, coordinates, unknown GlobalIds) are unit tested in node. The plugin (plugins/bcf.ts) executes plans.

import { dirIfcToViewer, dirViewerToIfc, ifcToViewer, newGuid, toIfcGuid, viewerToIfc } from './model';
import type { BcfClippingPlane, BcfComponent, BcfViewpoint, Vec3 } from './model';

// ---------------------------------------------------------------- vector helpers

const sub = (a: Vec3, b: Vec3): Vec3 => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const add = (a: Vec3, b: Vec3): Vec3 => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
const mul = (a: Vec3, s: number): Vec3 => [a[0] * s, a[1] * s, a[2] * s];
const dot = (a: Vec3, b: Vec3): number => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const len = (a: Vec3): number => Math.hypot(a[0], a[1], a[2]);
export function normalize(a: Vec3): Vec3 | null {
  const l = len(a);
  return l > 1e-12 && Number.isFinite(l) ? [a[0] / l, a[1] / l, a[2] / l] : null;
}

/** [minx, miny, minz, maxx, maxy, maxz] in viewer coordinates. */
export type Box6 = readonly [number, number, number, number, number, number];

const boxCentre = (b: Box6): Vec3 => [(b[0] + b[3]) / 2, (b[1] + b[4]) / 2, (b[2] + b[5]) / 2];
const boxRadius = (b: Box6): number => Math.hypot(b[3] - b[0], b[4] - b[1], b[5] - b[2]) / 2;

export function unionBox(boxes: Iterable<Box6>): Box6 | null {
  let out: [number, number, number, number, number, number] | null = null;
  for (const b of boxes) {
    if (!out) out = [b[0], b[1], b[2], b[3], b[4], b[5]];
    else {
      out[0] = Math.min(out[0], b[0]); out[1] = Math.min(out[1], b[1]); out[2] = Math.min(out[2], b[2]);
      out[3] = Math.max(out[3], b[3]); out[4] = Math.max(out[4], b[4]); out[5] = Math.max(out[5], b[5]);
    }
  }
  return out;
}

/** Distance along the ray from `p` in unit direction `d` to the middle of the chord through the box; falls back to the centre depth. */
export function distanceAlongView(p: Vec3, d: Vec3, box: Box6 | null): number {
  if (!box) return 10;
  let t0 = -Infinity;
  let t1 = Infinity;
  for (let a = 0; a < 3; a++) {
    const lo = box[a]!;
    const hi = box[a + 3]!;
    if (Math.abs(d[a]!) < 1e-12) {
      if (p[a]! < lo || p[a]! > hi) {
        t0 = Infinity;
        t1 = -Infinity;
      }
    } else {
      const ta = (lo - p[a]!) / d[a]!;
      const tb = (hi - p[a]!) / d[a]!;
      t0 = Math.max(t0, Math.min(ta, tb));
      t1 = Math.min(t1, Math.max(ta, tb));
    }
  }
  if (t1 >= Math.max(t0, 0) && t1 > 0) return Math.max((Math.max(t0, 0) + t1) / 2, 0.05);
  const c = boxCentre(box);
  const along = dot(sub(c, p), d);
  return along > 0.05 ? along : Math.max(len(sub(c, p)), 0.5);
}

// ---------------------------------------------------------------- applying: viewpoint -> plan

export interface PlanContext {
  /** sidecar originShift (IFC frame). */
  shift: Vec3;
  /** GlobalId -> element id. */
  resolve(globalId: string): number | undefined;
  /** Number of elements; ids are 0..count-1. */
  count: number;
  classOf(id: number): string;
  /** Union of all element bounds, viewer coordinates. */
  modelBounds: Box6 | null;
  /** Current camera: vertical field of view (degrees) and width / height. */
  fov: number;
  aspect: number;
  /** Whether renderer.setClipPlanes exists. */
  canClip: boolean;
}

export interface PlanCamera {
  position: Vec3;
  target: Vec3;
  up: Vec3;
  fov: number;
  /** True when an orthographic camera was approximated by a perspective one. */
  approximatedOrthogonal: boolean;
}

export interface ViewpointPlan {
  camera: PlanCamera | null;
  selection: number[];
  /** Elements the viewpoint selects whose GlobalId is not in this model. */
  selectionUnknown: number;
  /** Elements to hide, or null when the viewpoint has no usable visibility information. */
  hide: number[] | null;
  visibilityUnknown: number;
  colors: Array<{ rgb: [number, number, number]; ids: number[] }>;
  colorUnknown: number;
  clip: Array<{ normal: Vec3; point: Vec3 }>;
  /** What was applied and what was skipped, one phrase each. */
  applied: string[];
  skipped: string[];
}

function resolveAll(comps: BcfComponent[], ctx: PlanContext): { ids: number[]; unknown: number } {
  const ids: number[] = [];
  const seen = new Set<number>();
  let unknown = 0;
  for (const c of comps) {
    const id = c.ifcGuid ? ctx.resolve(c.ifcGuid) : undefined;
    if (id === undefined) unknown++;
    else if (!seen.has(id)) {
      seen.add(id);
      ids.push(id);
    }
  }
  return { ids, unknown };
}

/** Elements to hide for a Visibility block: default, then ViewSetupHints (spaces, openings), then exceptions. */
export function visibilityHides(
  vis: NonNullable<BcfViewpoint['visibility']>,
  ctx: Pick<PlanContext, 'resolve' | 'count' | 'classOf'>,
): { hide: number[]; unknown: number; exceptionsResolved: number } {
  const ex = resolveAll(vis.exceptions, ctx as PlanContext);
  const visible = new Uint8Array(ctx.count).fill(vis.defaultVisibility ? 1 : 0);
  const h = vis.hints;
  if (h) {
    for (let i = 0; i < ctx.count; i++) {
      const cls = ctx.classOf(i);
      if (cls === 'IfcSpace' && h.spacesVisible !== undefined) visible[i] = h.spacesVisible ? 1 : 0;
      else if (cls === 'IfcOpeningElement' && h.openingsVisible !== undefined) visible[i] = h.openingsVisible ? 1 : 0;
    }
  }
  for (const id of ex.ids) visible[id] = vis.defaultVisibility ? 0 : 1;
  const hide: number[] = [];
  for (let i = 0; i < ctx.count; i++) if (!visible[i]) hide.push(i);
  return { hide, unknown: ex.unknown, exceptionsResolved: ex.ids.length };
}

export function parseColor(hex: string): { rgb: [number, number, number]; alpha: number } | null {
  const m = /^([0-9A-Fa-f]{6})([0-9A-Fa-f]{2})?$/.exec(hex);
  if (!m) return null;
  const v = parseInt(m[1]!, 16);
  return { rgb: [((v >> 16) & 255) / 255, ((v >> 8) & 255) / 255, (v & 255) / 255], alpha: m[2] ? parseInt(m[2], 16) / 255 : 1 };
}

export function planViewpoint(vp: BcfViewpoint, ctx: PlanContext): ViewpointPlan {
  const plan: ViewpointPlan = {
    camera: null, selection: [], selectionUnknown: 0, hide: null, visibilityUnknown: 0, colors: [], colorUnknown: 0, clip: [], applied: [], skipped: [],
  };

  // ---- camera
  const cam = vp.camera;
  if (cam) {
    const pos = ifcToViewer(cam.position, ctx.shift);
    const dir = normalize(dirIfcToViewer(cam.direction));
    const up = normalize(dirIfcToViewer(cam.up));
    if (!dir || !up) {
      plan.skipped.push('camera (zero direction or up vector)');
    } else {
      const vpAspect = cam.aspect && cam.aspect > 0 ? cam.aspect : 1;
      const widen = ctx.aspect > 0 && ctx.aspect < vpAspect ? vpAspect / ctx.aspect : 1;
      if (cam.kind === 'perspective') {
        let fov = cam.fov && cam.fov > 0 && cam.fov < 180 ? cam.fov : ctx.fov;
        if (widen > 1) fov = (2 * Math.atan(Math.tan((fov * Math.PI) / 360) * widen) * 180) / Math.PI;
        fov = Math.min(120, Math.max(5, fov));
        const dist = distanceAlongView(pos, dir, ctx.modelBounds);
        plan.camera = { position: pos, target: add(pos, mul(dir, dist)), up, fov, approximatedOrthogonal: false };
        plan.applied.push('camera');
      } else {
        // Orthographic: a perspective camera at the distance where the viewer's vertical extent equals ViewToWorldScale,
        // aimed at the model depth the orthographic camera looked at.
        const scale = (cam.viewToWorldScale && cam.viewToWorldScale > 0 ? cam.viewToWorldScale : 10) * widen;
        const fov = ctx.fov;
        const back = scale / 2 / Math.tan((fov * Math.PI) / 360);
        const focusDepth = distanceAlongView(pos, dir, ctx.modelBounds);
        const focus = add(pos, mul(dir, focusDepth));
        plan.camera = { position: sub(focus, mul(dir, back)), target: focus, up, fov, approximatedOrthogonal: true };
        plan.applied.push('camera (orthographic approximated by a perspective camera)');
      }
    }
  } else {
    plan.skipped.push('camera (none in the viewpoint)');
  }

  // ---- selection
  if (vp.selection.length) {
    const r = resolveAll(vp.selection, ctx);
    plan.selection = r.ids;
    plan.selectionUnknown = r.unknown;
    plan.applied.push(`selection ${r.ids.length}`);
    if (r.unknown) plan.skipped.push(`${r.unknown} selected GlobalIds not in this model`);
  }

  // ---- visibility
  if (vp.visibility) {
    const v = visibilityHides(vp.visibility, ctx);
    plan.visibilityUnknown = v.unknown;
    if (!vp.visibility.defaultVisibility && v.exceptionsResolved === 0) {
      plan.skipped.push(`visibility (DefaultVisibility false but none of the ${vp.visibility.exceptions.length} visible components exist in this model)`);
    } else {
      plan.hide = v.hide;
      plan.applied.push(`visibility (${v.hide.length} hidden)`);
      if (v.unknown) plan.skipped.push(`${v.unknown} visibility GlobalIds not in this model`);
    }
  }

  // ---- coloring
  let alphaSeen = false;
  for (const c of vp.coloring) {
    const col = parseColor(c.color);
    if (!col) continue;
    if (col.alpha < 1) alphaSeen = true;
    const r = resolveAll(c.components, ctx);
    plan.colorUnknown += r.unknown;
    if (r.ids.length) plan.colors.push({ rgb: col.rgb, ids: r.ids });
  }
  if (vp.coloring.length) {
    const n = plan.colors.reduce((s, c) => s + c.ids.length, 0);
    plan.applied.push(`coloring ${n}`);
    if (plan.colorUnknown) plan.skipped.push(`${plan.colorUnknown} coloured GlobalIds not in this model`);
    if (alphaSeen) plan.skipped.push('colour alpha (colour only)');
  }

  // ---- clipping: BCF Direction points into the clipped half-space, the renderer's normal points into the kept one.
  for (const c of vp.clipping) {
    const d = normalize(dirIfcToViewer(c.direction));
    if (!d) continue;
    plan.clip.push({ normal: mul(d, -1), point: ifcToViewer(c.location, ctx.shift) });
  }
  if (vp.clipping.length) {
    if (!ctx.canClip) plan.skipped.push(`${vp.clipping.length} clipping planes (renderer.setClipPlanes is not available)`);
    else if (plan.clip.length) plan.applied.push(`clipping ${plan.clip.length}`);
  }
  if (vp.lines.length) plan.skipped.push(`${vp.lines.length} lines`);
  if (vp.bitmapsIgnored) plan.skipped.push(`${vp.bitmapsIgnored} bitmaps`);
  return plan;
}

// ---------------------------------------------------------------- authoring: viewer state -> viewpoint

export interface CaptureState {
  shift: Vec3;
  /** Camera in viewer coordinates. */
  position: Vec3;
  target: Vec3;
  up: Vec3;
  fov: number;
  aspect: number;
  selection: number[];
  hidden: ReadonlySet<number>;
  count: number;
  globalId(id: number): string;
  clip: Array<{ normal: Vec3; point: Vec3 }>;
}

export interface CaptureResult {
  viewpoint: BcfViewpoint;
  /** Elements left out because their GlobalId is not a valid 22 character IfcGuid. */
  skippedIds: number;
  /** Size of the Exceptions list. */
  exceptions: number;
}

export function captureViewpoint(s: CaptureState, guid: string = newGuid()): CaptureResult {
  let skipped = 0;
  const comp = (id: number): BcfComponent | null => {
    const g = toIfcGuid(s.globalId(id));
    if (!g) {
      skipped++;
      return null;
    }
    return { ifcGuid: g };
  };
  const dir = normalize(sub(s.target, s.position)) ?? [0, 0, -1];
  const up = normalize(s.up) ?? [0, 1, 0];
  const vp: BcfViewpoint = {
    guid,
    camera: {
      kind: 'perspective',
      position: viewerToIfc(s.position, s.shift),
      direction: dirViewerToIfc(dir),
      up: dirViewerToIfc(up),
      fov: s.fov,
      aspect: s.aspect,
    },
    selection: [],
    visibility: null,
    coloring: [],
    clipping: [],
    lines: [],
  };
  for (const id of s.selection) {
    const c = comp(id);
    if (c) vp.selection.push(c);
  }
  // Visibility: put whichever list is shorter in Exceptions (BCF 3.0 optimisation rule).
  const hiddenCount = s.hidden.size;
  const visibleCount = s.count - hiddenCount;
  const exceptions: BcfComponent[] = [];
  let defaultVisibility = true;
  if (hiddenCount <= visibleCount) {
    for (const id of s.hidden) {
      const c = comp(id);
      if (c) exceptions.push(c);
    }
  } else {
    defaultVisibility = false;
    for (let id = 0; id < s.count; id++) {
      if (s.hidden.has(id)) continue;
      const c = comp(id);
      if (c) exceptions.push(c);
    }
  }
  vp.visibility = { defaultVisibility, exceptions };
  for (const c of s.clip) {
    const d = normalize(c.normal);
    if (!d) continue;
    const p: BcfClippingPlane = { location: viewerToIfc(c.point, s.shift), direction: dirViewerToIfc(mul(d, -1)) };
    vp.clipping.push(p);
  }
  return { viewpoint: vp, skippedIds: skipped, exceptions: exceptions.length };
}

/**
 * A camera that frames a box from a given view direction (from the box centre towards the eye), viewer coordinates.
 * `padding` > 1 leaves a margin.
 */
export function frameCamera(box: Box6, fovDeg: number, aspect: number, eyeDir: Vec3 = [0.62, 0.5, 0.78], padding = 1.25): { position: Vec3; target: Vec3 } {
  const c = boxCentre(box);
  const r = Math.max(boxRadius(box), 0.25);
  const fov = (fovDeg * Math.PI) / 180;
  const fit = Math.min(fov, 2 * Math.atan(Math.tan(fov / 2) * Math.max(aspect, 0.1)));
  const dist = (r / Math.sin(fit / 2)) * padding;
  const d = normalize(eyeDir) ?? [0, 0, 1];
  return { position: add(c, mul(d, dist)), target: c };
}


/** The ways a caller may name the elements of a topic: `globalIds`, its alias `elements`, or viewer `elementIds`. */
export interface TopicElementRefs {
  globalIds?: string[];
  elements?: string[];
  elementIds?: number[];
}

/** GlobalIds of a topic spec: globalIds, else elements, else elementIds mapped through the model's elements. */
export function topicGlobalIds(spec: TopicElementRefs, elements: ReadonlyArray<{ globalId: string }>): string[] {
  if (spec.globalIds && spec.globalIds.length) return spec.globalIds;
  if (spec.elements && spec.elements.length) return spec.elements;
  const out: string[] = [];
  for (const i of spec.elementIds ?? []) {
    const e = elements[i];
    if (e) out.push(e.globalId);
  }
  return out;
}

/** A box around a point (viewer frame) merged with optional element bounds, for framing a located finding. */
export function boxAround(point: Vec3, base: Box6 | null, pad = 0.4): Box6 {
  const b: Box6 = [point[0] - pad, point[1] - pad, point[2] - pad, point[0] + pad, point[1] + pad, point[2] + pad];
  return base ? unionBox([base, b])! : b;
}
