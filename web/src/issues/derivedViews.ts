// Derived views of a sketch that is tied to a 3D construct: Plan (a top-down orthographic cut) and Section (a vertical cut with a
// limited depth). Pure: no three.js, no DOM. Tested in tests/issues-derived-views.test.ts. Docs: docs-features/issues.md.
//
// Coordinates are the viewer's (metres, Y up; IFC north is -Z) unless a name says IFC. A clip plane is {normal, point}: the
// normal points into the KEPT half-space, like renderer.setClipPlanes. In a BCF file the Direction points into the clipped half.
//
//   3D       the sketch's own authored camera, no clipping (not derived: the viewer restores it).
//   Plan     orthographic, looking down, north up. One horizontal cut at the storey level + 1.2 m. A target that sits above that
//            cut (ceiling MEP) is cut 0.3 m above its top; a short target that straddles it is cut just above its top.
//   Section  orthographic, looking along a horizontal axis. The cut is perpendicular to the target's longer horizontal side, or
//            to the horizontal part of the surface normal when that is clearly horizontal. A back plane keeps the depth short.
//
// The same views are written to BCF as extra viewpoints (withDerivedViewpoints) and marked in the side file (`derived`).

import { attachGuids } from '../bcf/attach';
import type { Attachment, SurfaceData } from '../bcf/attach';
import { dirIfcToViewer, dirViewerToIfc, ifcToViewer, newGuid, viewerToIfc } from '../bcf/model';
import type { BcfClippingPlane, BcfDerived, BcfProject, BcfTopic, BcfViewpoint, BcfViewpointRef, Vec3 } from '../bcf/model';
import { viewpointWithMarkup } from '../bcf/write';
import { unionBox } from '../bcf/plan';
import type { Box6 } from '../bcf/plan';

export type ViewMode = '3d' | 'plan' | 'section';
export const VIEW_MODES: readonly ViewMode[] = ['3d', 'plan', 'section'];
export const MODE_LABEL: Record<ViewMode, string> = { '3d': '3D', plan: 'Plan', section: 'Section' };

/** Metres above the storey level where the plan cut is made. */
export const PLAN_CUT_ABOVE_FLOOR = 1.2;
/** A target that lies wholly above the cut is cut this far above its top. */
export const PLAN_ABOVE_CLEARANCE = 0.3;
/** A short target that straddles the cut is cut this far above its top. */
export const PLAN_JUST_ABOVE = 0.05;
/** Targets up to this tall that straddle the cut are shown whole; taller ones (walls, columns) are cut like a plan. */
export const PLAN_SHORT_TARGET = 1.5;
/** The plan frames the target at this multiple of its larger side, and at least MIN_SPAN metres across. */
export const PLAN_MARGIN = 4;
export const PLAN_MIN_SPAN = 6;
export const SECTION_MARGIN = 3;
export const SECTION_MIN_SPAN = 5;
/** Section depth: the back plane is max(SECTION_DEPTH_MIN, SECTION_DEPTH_FACTOR x the target's depth) behind the cut. */
export const SECTION_DEPTH_MIN = 2;
export const SECTION_DEPTH_FACTOR = 2;
/** A surface normal is "clearly horizontal" when it is within this sine of the horizontal plane (|y| <= 0.5: 30 degrees). */
export const HORIZONTAL_NORMAL_Y = 0.5;

export interface ClipPlane {
  /** Unit normal into the kept half-space. */
  normal: Vec3;
  point: Vec3;
}

export interface DerivedInput {
  /** The target's world AABB. */
  target: Box6;
  /** Unit surface normal of the target (viewer frame), when it is a surface. */
  normal?: Vec3 | null;
  /** Viewer height of the target's storey level, when known. */
  storeyY?: number | null;
  /** Viewer heights of all storey levels, ascending: the fallback when `storeyY` is unknown. */
  floors?: readonly number[];
  /** The model AABB: the camera stands outside it. */
  model?: Box6 | null;
  /** Width over height of the view. */
  aspect?: number;
  /** The authored view direction (viewer frame): decides which side a section is looked from. */
  hint?: Vec3 | null;
}

export interface DerivedView {
  mode: 'plan' | 'section';
  /** Orthographic: the camera stands `standoff` metres from `target` against `direction`. */
  position: Vec3;
  target: Vec3;
  /** Unit view direction. */
  direction: Vec3;
  up: Vec3;
  standoff: number;
  /** Metres of visible height (BCF ViewToWorldScale). */
  orthoHeight: number;
  clip: ClipPlane[];
  /** Plan: the viewer height of the cut. */
  cutHeight?: number;
  /** Section: how the direction was chosen, and the depth of the box behind the cut. */
  basis?: 'long-axis' | 'normal';
  depth?: number;
}

const sub = (a: Vec3, b: Vec3): Vec3 => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const add = (a: Vec3, b: Vec3): Vec3 => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
const mul = (a: Vec3, s: number): Vec3 => [a[0] * s, a[1] * s, a[2] * s];
const finite = (n: unknown): n is number => typeof n === 'number' && Number.isFinite(n);
const centre = (b: Box6): Vec3 => [(b[0] + b[3]) / 2, (b[1] + b[4]) / 2, (b[2] + b[5]) / 2];
const clampAspect = (a: number | undefined): number => (finite(a) && a > 0 ? Math.min(5, Math.max(0.2, a)) : 1.6);

/** The storey level height under a target: the given one, else the highest floor at or below its centre, else its base. */
export function storeyLevel(i: Pick<DerivedInput, 'target' | 'storeyY' | 'floors'>): number {
  if (finite(i.storeyY)) return i.storeyY;
  const cy = (i.target[1] + i.target[4]) / 2;
  const fl = [...(i.floors ?? [])].filter(finite).sort((a, b) => a - b);
  if (!fl.length) return i.target[1];
  let pick = fl[0]!;
  for (const f of fl) if (f <= cy + 0.05) pick = f;
  return pick;
}

/** Where the plan cuts: storey + 1.2 m, above a target that lies over it, just above a short target that straddles it. */
export function planCutHeight(i: Pick<DerivedInput, 'target' | 'storeyY' | 'floors'>): number {
  const t = i.target;
  const cut = storeyLevel(i) + PLAN_CUT_ABOVE_FLOOR;
  if (t[1] >= cut) return t[4] + PLAN_ABOVE_CLEARANCE; // wholly above the cut: ceiling MEP, upper fittings
  if (t[4] > cut && t[4] - t[1] <= PLAN_SHORT_TARGET) return t[4] + PLAN_JUST_ABOVE;
  return cut;
}

/** Visible height that holds `span` metres across in both directions at this aspect. */
function heightFor(span: number, aspect: number): number {
  return span * Math.max(1, 1 / aspect);
}

function modelTop(i: DerivedInput): number {
  return Math.max(i.model ? i.model[4] : -Infinity, i.target[4]);
}

export function derivePlan(i: DerivedInput): DerivedView {
  const t = i.target;
  const cut = planCutHeight(i);
  const c = centre(t);
  const span = Math.max(PLAN_MIN_SPAN, PLAN_MARGIN * Math.max(t[3] - t[0], t[5] - t[2]));
  const look: Vec3 = [c[0], Math.min(c[1], cut), c[2]];
  const direction: Vec3 = [0, -1, 0];
  const standoff = Math.max(modelTop(i), cut) - look[1] + 1;
  return {
    mode: 'plan',
    position: sub(look, mul(direction, standoff)),
    target: look,
    direction,
    up: [0, 0, -1], // north up (IFC +Y is viewer -Z), east right
    standoff,
    orthoHeight: heightFor(span, clampAspect(i.aspect)),
    clip: [{ normal: [0, -1, 0], point: [c[0], cut, c[2]] }],
    cutHeight: cut,
  };
}

/** The horizontal unit part of a normal when it is clearly horizontal, else null. */
export function horizontalNormal(n: Vec3 | null | undefined): Vec3 | null {
  if (!n || !n.every(finite)) return null;
  const l = Math.hypot(n[0], n[1], n[2]);
  if (l < 1e-9) return null;
  const h = Math.hypot(n[0], n[2]);
  if (Math.abs(n[1]) / l > HORIZONTAL_NORMAL_Y || h / l < 0.1) return null;
  return [n[0] / h, 0, n[2] / h];
}

export function deriveSection(i: DerivedInput): DerivedView {
  const t = i.target;
  const c = centre(t);
  const sx = t[3] - t[0];
  const sy = t[4] - t[1];
  const sz = t[5] - t[2];
  const hint = i.hint && finite(i.hint[0]) && finite(i.hint[2]) && Math.hypot(i.hint[0], i.hint[2]) > 1e-6 ? i.hint : null;
  let ax: Vec3;
  let basis: 'long-axis' | 'normal';
  const hn = horizontalNormal(i.normal);
  if (hn) {
    // The normal faces the authoring camera: look into the surface, against it.
    ax = [-hn[0], 0, -hn[2]];
    basis = 'normal';
  } else {
    basis = 'long-axis';
    const nearSquare = Math.abs(sx - sz) <= 0.1 * Math.max(sx, sz, 1e-9);
    let alongX = sx >= sz;
    if (nearSquare && hint) alongX = Math.abs(hint[0]) >= Math.abs(hint[2]);
    ax = alongX ? [1, 0, 0] : [0, 0, 1];
    if (hint && hint[0] * ax[0] + hint[2] * ax[2] < 0) ax = mul(ax, -1);
  }
  const alongExtent = Math.abs(ax[0]) * sx + Math.abs(ax[2]) * sz;
  const acrossExtent = Math.abs(ax[2]) * sx + Math.abs(ax[0]) * sz;
  const depth = Math.max(SECTION_DEPTH_MIN, SECTION_DEPTH_FACTOR * alongExtent);
  const span = Math.max(SECTION_MIN_SPAN, SECTION_MARGIN * Math.max(acrossExtent, sy));
  const radius = i.model ? Math.hypot(i.model[3] - i.model[0], i.model[4] - i.model[1], i.model[5] - i.model[2]) / 2 : Math.hypot(sx, sy, sz) / 2;
  const standoff = radius + 1;
  return {
    mode: 'section',
    position: sub(c, mul(ax, standoff)),
    target: c,
    direction: ax,
    up: [0, 1, 0],
    standoff,
    orthoHeight: heightFor(span, clampAspect(i.aspect)),
    clip: [
      { normal: ax, point: c },
      { normal: mul(ax, -1), point: add(c, mul(ax, depth)) },
    ],
    basis,
    depth,
  };
}

export function deriveView(mode: 'plan' | 'section', i: DerivedInput): DerivedView {
  return mode === 'plan' ? derivePlan(i) : deriveSection(i);
}

// ---------------------------------------------------------------- what a sketch is tied to

/** Attachment kinds that tie a drawing to a 3D construct. View-locked (`none`) and foreign `lines` do not. */
export const TIED_KINDS = ['surface', 'elements', 'measurement', 'penetration', 'region', 'point'] as const;
export function isTied(a: Attachment | undefined): boolean {
  return !!a && (TIED_KINDS as readonly string[]).includes(a.kind);
}

/** What the markup layer lends: the attachment of each markup, and the anchor point (IFC frame) of an anchored one. */
export interface TiedMarkup {
  id: string;
  attach: Attachment;
  /** IFC frame; the position of a `point` attachment. */
  anchorPoint?: Vec3;
}

export interface TargetCtx {
  shift: Vec3;
  /** Bounds of the element with this GlobalId (viewer frame), or null when it is not in the model. */
  elementBox(guid: string): Box6 | null;
  /** Viewer height of the storey level of the element, or null. */
  storeyY(guid: string): number | null;
  /** The surface as it lies on the model now (src/markup/reprojectScene), else the stored one is used. */
  resolveSurface?(s: SurfaceData): SurfaceData | null;
}

export interface Target {
  box: Box6;
  normal: Vec3 | null;
  storeyY: number | null;
}

const pad = (b: Box6, d: number): Box6 => [b[0] - d, b[1] - d, b[2] - d, b[3] + d, b[4] + d, b[5] + d];
const pointBox = (p: Vec3, d: number): Box6 => pad([p[0], p[1], p[2], p[0], p[1], p[2]], d);
const intersect = (a: Box6, b: Box6): Box6 | null => {
  const o: Box6 = [Math.max(a[0], b[0]), Math.max(a[1], b[1]), Math.max(a[2], b[2]), Math.min(a[3], b[3]), Math.min(a[4], b[4]), Math.min(a[5], b[5])];
  return o[0] <= o[3] && o[1] <= o[4] && o[2] <= o[5] ? o : null;
};

/** The world box, surface normal and storey of one tied attachment. Null when nothing of it is in the model. */
export function attachmentTarget(a: Attachment, anchorPoint: Vec3 | null | undefined, ctx: TargetCtx): Target | null {
  if (!isTied(a)) return null;
  const guids = attachGuids(a);
  const storeyOf = (): number | null => {
    for (const g of guids) {
      const y = ctx.storeyY(g);
      if (y !== null && finite(y)) return y;
    }
    return null;
  };
  const boxesOf = (list: readonly string[]): Box6[] => list.map((g) => ctx.elementBox(g)).filter((b): b is Box6 => !!b);
  let box: Box6 | null = null;
  let normal: Vec3 | null = null;
  switch (a.kind) {
    case 'measurement': {
      const m = a.measurement;
      if (m) box = pad(unionBox([pointBox(ifcToViewer(m.a, ctx.shift), 0), pointBox(ifcToViewer(m.b, ctx.shift), 0)])!, 0.15);
      break;
    }
    case 'penetration': {
      const mep = a.penetration ? ctx.elementBox(a.penetration.mep) : null;
      const host = a.penetration ? ctx.elementBox(a.penetration.host) : null;
      box = mep && host ? intersect(mep, host) ?? unionBox([mep, host]) : mep ?? host;
      break;
    }
    case 'region':
      if (a.region) {
        const p = ifcToViewer(a.region.min, ctx.shift);
        const q = ifcToViewer(a.region.max, ctx.shift);
        box = [Math.min(p[0], q[0]), Math.min(p[1], q[1]), Math.min(p[2], q[2]), Math.max(p[0], q[0]), Math.max(p[1], q[1]), Math.max(p[2], q[2])];
      }
      break;
    case 'point':
      if (anchorPoint) box = pointBox(ifcToViewer(anchorPoint, ctx.shift), 0.25);
      break;
    default: {
      // surface and elements: the stroke on the model when there is one, else the elements themselves.
      const s = a.surface ? ctx.resolveSurface?.(a.surface) ?? a.surface : null;
      if (s && s.pts.length) {
        box = pad(unionBox(s.pts.map((p) => pointBox(ifcToViewer(p.p, ctx.shift), 0)))!, 0.15);
        const ns = s.pts.map((p) => p.n).filter((n): n is Vec3 => !!n);
        if (ns.length) {
          const sum = ns.reduce<Vec3>((acc, n) => add(acc, dirIfcToViewer(n)), [0, 0, 0]);
          const l = Math.hypot(sum[0], sum[1], sum[2]);
          if (l > 1e-6) normal = [sum[0] / l, sum[1] / l, sum[2] / l];
        }
      } else box = unionBox(boxesOf(a.guids ?? guids));
    }
  }
  if (!box) {
    const els = boxesOf(guids);
    box = els.length ? unionBox(els) : null;
  }
  return box ? { box, normal, storeyY: storeyOf() } : null;
}

/** The marker of a sketch's drawings that are tied, for the target. `selected` narrows it to one drawing when that one is tied. */
export function sketchTarget(markups: readonly TiedMarkup[], ctx: TargetCtx, selected?: string | null): Target | null {
  const tied = markups.filter((m) => isTied(m.attach));
  const one = selected ? tied.find((m) => m.id === selected) : undefined;
  const list = one ? [one] : tied;
  const targets = list.map((m) => attachmentTarget(m.attach, m.anchorPoint, ctx)).filter((x): x is Target => !!x);
  if (!targets.length) return null;
  const box = unionBox(targets.map((x) => x.box))!;
  const ys = targets.map((x) => x.storeyY).filter((y): y is number => y !== null);
  return { box, normal: targets.length === 1 ? targets[0]!.normal : null, storeyY: ys.length ? Math.min(...ys) : null };
}

/** True when any drawing of the sketch is tied to a 3D construct: the sketch gets the 3D, Plan, Section switch. */
export function sketchIsTied(markups: readonly TiedMarkup[]): boolean {
  return markups.some((m) => isTied(m.attach));
}

/** The authored view direction as a hint for the side a section is looked from: horizontal part, viewer frame. */
export function hintOf(direction: Vec3 | null | undefined): Vec3 | null {
  return direction && Math.hypot(direction[0], direction[2]) > 1e-6 ? [direction[0], 0, direction[2]] : null;
}

// ---------------------------------------------------------------- BCF export

export interface DerivedSource {
  /** The id of the sketch the views are of. */
  sketch: string;
  /** The views to write, by kind. */
  views: Partial<Record<'plan' | 'section', DerivedView>>;
  shift: Vec3;
  aspect: number;
}

/** The viewpoint file of a derived view: orthogonal camera with ViewToWorldScale, clipping planes, the source's components. */
export function derivedViewpoint(view: DerivedView, src: BcfViewpointRef, o: { shift: Vec3; aspect: number; guid?: string }): BcfViewpoint {
  const vp = src.data!;
  const clipping: BcfClippingPlane[] = view.clip.map((p) => ({
    location: viewerToIfc(p.point, o.shift),
    // BCF Direction points into the clipped half-space; the renderer's normal points into the kept one.
    direction: dirViewerToIfc(mul(p.normal, -1)),
  }));
  const withMarkup = viewpointWithMarkup(vp, src);
  return {
    guid: o.guid ?? newGuid(),
    camera: {
      kind: 'orthogonal',
      position: viewerToIfc(view.position, o.shift),
      direction: dirViewerToIfc(view.direction),
      up: dirViewerToIfc(view.up),
      viewToWorldScale: view.orthoHeight,
      aspect: o.aspect,
    },
    selection: withMarkup.selection.map((c) => ({ ...c })),
    visibility: vp.visibility ? { defaultVisibility: vp.visibility.defaultVisibility, exceptions: vp.visibility.exceptions.map((c) => ({ ...c })), ...(vp.visibility.hints ? { hints: { ...vp.visibility.hints } } : {}) } : null,
    coloring: vp.coloring.map((c) => ({ color: c.color, components: c.components.map((k) => ({ ...k })) })),
    clipping,
    lines: withMarkup.lines.map((l) => ({ start: [...l.start] as Vec3, end: [...l.end] as Vec3 })),
  };
}

/** The derived viewpoint refs of a source viewpoint (plan, then section). Guids are reused from `old` so re-exports are stable. */
export function derivedRefs(src: BcfViewpointRef, d: DerivedSource, old: readonly BcfViewpointRef[] = []): BcfViewpointRef[] {
  const out: BcfViewpointRef[] = [];
  if (!src.data) return out;
  for (const kind of ['plan', 'section'] as const) {
    const view = d.views[kind];
    if (!view) continue;
    const prev = old.find((r) => r.derived?.kind === kind && r.derived.of.toLowerCase() === src.guid.toLowerCase());
    const guid = prev?.guid ?? newGuid();
    const derived: BcfDerived = { kind, sketch: d.sketch, of: src.guid };
    out.push({ guid, data: derivedViewpoint(view, src, { shift: d.shift, aspect: d.aspect, guid }), derived });
  }
  return out;
}

/**
 * The project as it is exported: each viewpoint that has a derivable source gets its Plan and Section viewpoints right after
 * it. Derived viewpoints that came from an earlier export are replaced, not doubled (and keep their guids); those whose source
 * cannot derive now (a foreign copy of the issue) are kept as they are. The project itself is not changed.
 */
export function withDerivedViewpoints(project: BcfProject, provider: (topic: BcfTopic, ref: BcfViewpointRef) => DerivedSource | null): BcfProject {
  let changed = false;
  const topics = project.topics.map((t) => {
    const old = t.viewpoints.filter((r) => r.derived);
    const next: BcfViewpointRef[] = [];
    const used = new Set<BcfViewpointRef>();
    for (const r of t.viewpoints) {
      if (r.derived) continue;
      next.push(r);
      const d = r.data ? provider(t, r) : null;
      if (!d) continue;
      for (const x of derivedRefs(r, d, old)) {
        const prev = old.find((o) => o.guid === x.guid);
        if (prev) used.add(prev);
        next.push(x);
        changed = true;
      }
    }
    for (const o of old) if (!used.has(o)) next.push(o);
    return next.length === t.viewpoints.length && !next.some((r, i) => r !== t.viewpoints[i]) ? t : { ...t, viewpoints: next };
  });
  return changed ? { ...project, topics } : project;
}
