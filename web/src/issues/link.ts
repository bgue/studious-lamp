// Sketches and issues, the pure part: how a sketch (a markup set: a view, drawings and a note) and an issue (a BCF topic)
// link, and how drawings convert to BCF annotations and back. No DOM, no three.js. Tested in tests/issues-link.test.ts.
//
// The model: an issue's viewpoints ARE sketches. A viewpoint holds `sketchId`, the sketch holds `issue` (topic and viewpoint
// guid); one sketch belongs to at most one issue. The viewpoint's `annotations` are then a projection of the sketch, rebuilt
// by `syncViewpoint` on every edit and before export, so the export burns and serialises the current drawing. The points of a
// shape are fractions of the sketch camera, and the viewpoint camera for annotations is that same camera, so shapes copy over
// without projecting.

import { annotationGuids } from '../bcf/sidecar';
import { cloneAnnotation } from '../bcf/sidecar';
import { cloneAttachment } from '../bcf/attach';
import { shapePointWorld } from '../bcf/annotate';
import { dirIfcToViewer, ifcToViewer, nowIso, viewerToIfc } from '../bcf/model';
import type { BcfAnnotation, BcfAnnotationType, BcfSnapshotView, BcfTopic, BcfViewpointRef, Vec3 } from '../bcf/model';
import { boxCorners, ellipseInQuad } from '../markup/layout';
import { newMarkup, newMarkupId } from '../markup/model';
import type { Markup, MarkupKind, MarkupSet } from '../markup/model';
import type { SavedView } from '../views/model';

// ---------------------------------------------------------------- links

export interface IssueRef {
  topic: BcfTopic;
  viewpoint: BcfViewpointRef;
}

/** The issue a sketch belongs to: the topic whose viewpoint holds the sketch id. Null for a loose sketch. */
export function issueOfSketch(topics: readonly BcfTopic[], sketchId: string): IssueRef | null {
  for (const topic of topics) {
    const viewpoint = topic.viewpoints.find((v) => v.sketchId === sketchId);
    if (viewpoint) return { topic, viewpoint };
  }
  return null;
}

/** The sketches that are viewpoints of an issue, in viewpoint order. */
export function sketchesOfIssue(topic: BcfTopic, sets: readonly MarkupSet[]): MarkupSet[] {
  const out: MarkupSet[] = [];
  for (const v of topic.viewpoints) {
    const s = v.sketchId ? sets.find((x) => x.id === v.sketchId) : undefined;
    if (s) out.push(s);
  }
  return out;
}

export type LinkResult = { ok: true } | { ok: false; error: string };

/**
 * Make a sketch the drawing of a viewpoint. A sketch belongs to at most one issue: linking one that belongs to another issue
 * is refused (the same issue and viewpoint again is fine).
 */
export function linkSketch(topics: readonly BcfTopic[], sets: readonly MarkupSet[], sketchId: string, topicGuid: string, viewpointGuid: string): LinkResult {
  const set = sets.find((s) => s.id === sketchId);
  if (!set) return { ok: false, error: `No sketch ${sketchId}` };
  const topic = topics.find((t) => t.guid === topicGuid);
  const vp = topic?.viewpoints.find((v) => v.guid === viewpointGuid);
  if (!topic || !vp) return { ok: false, error: 'No such issue viewpoint' };
  const have = issueOfSketch(topics, sketchId);
  if (have && (have.topic.guid !== topicGuid || have.viewpoint.guid !== viewpointGuid)) {
    return { ok: false, error: `"${set.title}" already belongs to the issue "${have.topic.title}". A sketch belongs to at most one issue.` };
  }
  if (vp.sketchId && vp.sketchId !== sketchId) return { ok: false, error: 'That viewpoint already has another sketch' };
  vp.sketchId = sketchId;
  set.issue = { topic: topicGuid, viewpoint: viewpointGuid };
  return { ok: true };
}

/** Cut the link of a sketch (both sides). The viewpoint keeps its camera and snapshot, and loses the drawing. */
export function unlinkSketch(topics: readonly BcfTopic[], sets: readonly MarkupSet[], sketchId: string, o: { keepAnnotations?: boolean } = {}): void {
  for (const t of topics) {
    for (const v of t.viewpoints) {
      if (v.sketchId !== sketchId) continue;
      delete v.sketchId;
      if (!o.keepAnnotations) {
        delete v.annotations;
        delete v.markupSelection;
      }
    }
  }
  const s = sets.find((x) => x.id === sketchId);
  if (s) delete s.issue;
}

/** Bring the two sides of every link in step with the viewpoints (their `sketchId` is the truth); returns how many changed. */
export function reconcileLinks(topics: readonly BcfTopic[], sets: readonly MarkupSet[]): number {
  let n = 0;
  const seen = new Set<string>();
  for (const t of topics) {
    for (const v of t.viewpoints) {
      if (!v.sketchId) continue;
      const s = sets.find((x) => x.id === v.sketchId);
      if (!s || seen.has(v.sketchId)) {
        delete v.sketchId; // a sketch that is gone, or claimed twice: the first claim stands
        n++;
        continue;
      }
      seen.add(v.sketchId);
      if (s.issue?.topic !== t.guid || s.issue.viewpoint !== v.guid) {
        s.issue = { topic: t.guid, viewpoint: v.guid };
        n++;
      }
    }
  }
  for (const s of sets) {
    if (s.issue && !seen.has(s.id)) {
      delete s.issue;
      n++;
    }
  }
  return n;
}

// ---------------------------------------------------------------- markup <-> annotation

const ARROW_HEAD = 0.02; // arrow head length, fractions of the view height
const ANCHOR_TYPE: Record<string, BcfAnnotationType | undefined> = { text: 'note', callout: 'callout', pointer: 'arrow', measure: 'callout' };

function closed(p: Array<[number, number]>): Array<[number, number]> {
  return [...p, [p[0]![0], p[0]![1]]];
}

/** The outline of a shape markup as fractions: closed shapes are closed again, an ellipse is a polygon, an arrow gets its head. */
export function shapeOutline(m: Markup, aspect: number): { type: 'rect' | 'freehand'; points: Array<[number, number]> } | null {
  const sh = m.shape;
  if (!sh || sh.points.length < 2) return null;
  const P = sh.points;
  switch (m.kind) {
    case 'rect':
    case 'highlightBox':
      return P.length === 2 ? { type: 'rect', points: [[P[0]![0], P[0]![1]], [P[1]![0], P[1]![1]]] } : { type: 'freehand', points: closed(boxCorners(P)) };
    case 'cloud':
      return { type: 'freehand', points: closed(P.length === 2 ? boxCorners(P) : P.map((p) => [p[0], p[1]] as [number, number])) };
    case 'ellipse':
      return { type: 'freehand', points: closed(ellipseInQuad(boxCorners(P), 40)) };
    case 'polygon':
      return { type: 'freehand', points: closed(P.map((p) => [p[0], p[1]] as [number, number])) };
    case 'arrow': {
      const a = P[P.length - 2]!;
      const b = P[P.length - 1]!;
      // Head in units of the view height (x scaled by the aspect), so it is square on the picture.
      const dx = (b[0] - a[0]) * aspect;
      const dy = b[1] - a[1];
      const l = Math.hypot(dx, dy) || 1;
      const ux = dx / l, uy = dy / l;
      const hl = Math.min(ARROW_HEAD, l * 0.5);
      const w = (x: number, y: number): [number, number] => [b[0] + x / aspect, b[1] + y];
      const h1 = w(-ux * hl - uy * hl * 0.5, -uy * hl + ux * hl * 0.5);
      const h2 = w(-ux * hl + uy * hl * 0.5, -uy * hl - ux * hl * 0.5);
      return { type: 'freehand', points: [[a[0], a[1]], [b[0], b[1]], h1, [b[0], b[1]], h2] };
    }
    default:
      return { type: 'freehand', points: P.map((p) => [p[0], p[1]] as [number, number]) };
  }
}

/** The BCF annotation that serialises a markup. Null when it has nothing to draw. Positions in IFC coordinates. */
export function markupToAnnotation(m: Markup, camera: BcfSnapshotView, shift: Vec3): BcfAnnotation | null {
  const label = `${m.number}. ${m.text}`.trim();
  const base = { guid: m.id, text: label, author: m.author, date: m.created };
  if (m.anchor) {
    const type = ANCHOR_TYPE[m.kind];
    if (!type) return null;
    const a: BcfAnnotation = { ...base, type, anchor: cloneAnnotation({ guid: '', type: 'callout', text: '', anchor: m.anchor, offset: [0, 0] }).anchor, offset: m.offset ? [m.offset[0], m.offset[1]] : [0.1, -0.09] };
    if (m.kind === 'measure' && m.anchor.measurement) a.text = m.text ? label : '';
    return a;
  }
  const o = shapeOutline(m, camera.aspect);
  if (!o || !m.shape) return null;
  const mu = o.points.reduce((s, p) => s + p[0], 0) / o.points.length;
  const mv = o.points.reduce((s, p) => s + p[1], 0) / o.points.length;
  const depth = m.shape.depth > 0 ? m.shape.depth : 1;
  const a: BcfAnnotation = {
    ...base, type: o.type, offset: [0.12, -0.1],
    anchor: { kind: 'point', point: viewerToIfc(shapePointWorld(camera, shift, mu, mv, depth), shift) },
    shape: { points: o.points, depth },
  };
  a.attach = m.attach ? cloneAttachment(m.attach) : { kind: 'none' };
  return a;
}

/** The annotations of a sketch, in markup order. */
export function sketchAnnotations(set: MarkupSet, shift: Vec3): BcfAnnotation[] {
  const out: BcfAnnotation[] = [];
  for (const m of set.markups) {
    const a = markupToAnnotation(m, set.camera, shift);
    if (a) out.push(a);
  }
  return out;
}

/**
 * Rebuild the viewpoint's drawing from its sketch: the annotations, the camera they are drawn in, and the elements they point
 * at in the viewpoint selection (other BCF tools highlight them). Returns true when the annotations changed.
 */
export function syncViewpoint(set: MarkupSet, ref: BcfViewpointRef, shift: Vec3): boolean {
  const next = sketchAnnotations(set, shift);
  const before = JSON.stringify([ref.annotations ?? [], ref.snapshotView ?? null]);
  const sig = JSON.stringify([next, set.camera]);
  if (before === sig) return false;
  ref.annotations = next;
  ref.snapshotView = { position: [...set.camera.position], direction: [...set.camera.direction], up: [...set.camera.up], fov: set.camera.fov, aspect: set.camera.aspect };
  if (!next.length) delete ref.annotations;
  if (ref.data) {
    const want = new Set(annotationGuids(next));
    const prev = new Set(ref.markupSelection ?? []);
    ref.data.selection = ref.data.selection.filter((c) => !c.ifcGuid || !prev.has(c.ifcGuid) || want.has(c.ifcGuid));
    const have = new Set(ref.data.selection.map((c) => c.ifcGuid));
    const added = new Set<string>([...prev].filter((g) => want.has(g)));
    for (const g of want) {
      if (have.has(g)) continue;
      ref.data.selection.push({ ifcGuid: g });
      added.add(g);
    }
    if (added.size) ref.markupSelection = [...added];
    else delete ref.markupSelection;
  }
  return true;
}

/** One BCF annotation as a markup. Null when it cannot be (a line set of a foreign viewpoint has no shape to draw). */
export function annotationToMarkup(a: BcfAnnotation, number: number, author: string): Markup | null {
  const strip = (t: string): string => (t.startsWith(`${number}. `) ? t.slice(String(number).length + 2) : t === `${number}.` ? '' : t);
  const o = { author: a.author || author, text: strip(a.text), number, id: a.guid && a.guid.length <= 64 ? a.guid : newMarkupId(), ...(a.date ? { created: a.date } : {}) };
  if (a.type === 'rect' || a.type === 'freehand') {
    if (!a.shape || a.shape.points.length < 2) return null;
    const shape = { points: a.shape.points.map((p) => [p[0], p[1]] as [number, number]), depth: a.shape.depth };
    const m = newMarkup(a.type === 'rect' ? 'rect' : 'pen', { ...o, shape, text: o.text });
    if (a.attach) m.attach = cloneAttachment(a.attach);
    return m;
  }
  const kind: MarkupKind = a.type === 'note' ? 'text' : a.type === 'arrow' ? 'pointer' : a.anchor.measurement ? 'measure' : 'callout';
  const anchor = cloneAnnotation(a).anchor;
  if (kind === 'measure' && !anchor.measurement) return null;
  return newMarkup(kind, { ...o, anchor, offset: [a.offset[0], a.offset[1]] });
}

/** A saved view that holds only a camera: what a sketch made from an imported viewpoint keeps (restoring applies the viewpoint). */
export function viewFromCamera(name: string, cam: BcfSnapshotView, shift: Vec3, distance = 10): SavedView {
  const now = nowIso();
  const eye = ifcToViewer(cam.position, shift);
  const f = dirIfcToViewer(cam.direction);
  const l = Math.hypot(f[0], f[1], f[2]) || 1;
  return {
    id: newMarkupId('v'), name, created: now, updated: now,
    camera: { position: eye, target: [eye[0] + (f[0] / l) * distance, eye[1] + (f[1] / l) * distance, eye[2] + (f[2] / l) * distance], up: dirIfcToViewer(cam.up), fov: cam.fov, ortho: false },
    selection: [], params: {},
  };
}

export interface FromViewpointOptions {
  author: string;
  shift: Vec3;
  /** The camera of the viewpoint when it has no snapshot camera. */
  camera: BcfSnapshotView;
  model?: MarkupSet['model'];
  /** Make the sketch even when the viewpoint has no annotations yet (Edit drawing on a viewpoint that has none). */
  empty?: boolean;
}

/**
 * A sketch from an imported viewpoint with annotations, linked to it. Null when the viewpoint has no annotations, or one of
 * them cannot become a markup (then the viewpoint keeps its own drawing and no sketch is made).
 */
export function sketchFromViewpoint(topic: BcfTopic, ref: BcfViewpointRef, o: FromViewpointOptions): MarkupSet | null {
  const list = ref.annotations ?? [];
  // A derived Plan or Section viewpoint is a view of another viewpoint's sketch: it never gets a sketch of its own.
  if (ref.derived || ref.sketchId || (!list.length && !o.empty)) return null;
  const markups: Markup[] = [];
  const ids = new Set<string>();
  for (let i = 0; i < list.length; i++) {
    const m = annotationToMarkup(list[i]!, i + 1, o.author);
    if (!m) return null;
    if (ids.has(m.id)) m.id = newMarkupId();
    ids.add(m.id);
    markups.push(m);
  }
  const camera = ref.snapshotView ?? o.camera;
  const now = nowIso();
  const title = topic.viewpoints.length > 1 ? `${topic.title} (view ${topic.viewpoints.indexOf(ref) + 1})` : topic.title;
  const set: MarkupSet = {
    id: newMarkupId('s'), title: title || 'Sketch', author: o.author, created: now, updated: now,
    view: viewFromCamera(title, camera, o.shift), camera: { position: [...camera.position], direction: [...camera.direction], up: [...camera.up], fov: camera.fov, aspect: camera.aspect },
    markups, nextNumber: list.length + 1, fromViewpoint: true, issue: { topic: topic.guid, viewpoint: ref.guid },
  };
  if (topic.model) set.model = { ...topic.model };
  ref.sketchId = set.id;
  return set;
}

// ---------------------------------------------------------------- legacy review data

/** What an old set's comments and status become as an issue. */
export interface LegacyIssue {
  title: string;
  description: string;
  status: 'Open' | 'Resolved';
  assignedTo?: string;
  dueDate?: string;
  comments: Array<{ author: string; date: string; text: string }>;
}

export function legacyIssueOf(set: MarkupSet): LegacyIssue {
  const open = set.markups.length === 0 || set.markups.some((m) => m.status === 'open');
  const out: LegacyIssue = {
    title: set.title,
    description: set.note ?? `Sketch "${set.title}" with ${set.markups.length} markup${set.markups.length === 1 ? '' : 's'}.`,
    status: open ? 'Open' : 'Resolved',
    comments: [],
  };
  const dues: string[] = [];
  for (const m of set.markups) {
    if (m.assignee && !out.assignedTo) out.assignedTo = m.assignee;
    if (m.due) dues.push(m.due);
    for (const c of m.comments) out.comments.push({ author: c.author, date: c.date, text: `${m.number}. ${c.text}` });
  }
  if (dues.length) out.dueDate = dues.sort()[0]!;
  out.comments.sort((a, b) => a.date.localeCompare(b.date));
  return out;
}

/** Remove the legacy review data from a set (after it moved to an issue). */
export function clearLegacyReview(set: MarkupSet): void {
  for (const m of set.markups) {
    m.comments = [];
    m.status = 'open';
    delete m.assignee;
    delete m.due;
  }
}

/** The sketches that still carry legacy review data and are not part of an issue yet: what the banner offers to raise. */
export function legacySketches(sets: readonly MarkupSet[], hasLegacy: (s: MarkupSet) => boolean): MarkupSet[] {
  return sets.filter((s) => !s.issue && hasLegacy(s));
}
