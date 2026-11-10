// Markup controller: the markup sets of a session (one saved view and its markups each), drawing and editing with undo
// and redo, restoring a set's view, export (PDF, JSON), import, and conversion to BCF topics. DOM only where it renders
// pages (canvas) and downloads files; the data model, layout, PDF and report live in the other files of src/markup.
//
// The 3D machinery is the BCF one (src/bcf): shapes are fractions of the set camera's view on a depth plane
// (shapePointWorld / shapeFraction), anchors are IFC-frame points that follow elements (anchorPoint), picking and
// occlusion come from a BcfController used as a helper, and burn-in uses layout + drawOps.

import { Matrix4 } from 'three';
import type { ViewerApp } from '../app';
import { BcfController } from '../bcf/controller';
import { anchorPoint, drawOps, projectPoint, shapeFraction } from '../bcf/annotate';
import type { Ctx2D, LayoutContext } from '../bcf/annotate';
import { dirViewerToIfc, ifcToViewer, viewerToIfc } from '../bcf/model';
import type { BcfSnapshotView, Vec3 } from '../bcf/model';
import { cameraRay } from '../measure/geometry';
import { currentMeasurements } from '../measure/current';
import type { Measurement } from '../measure/maths';
import { formatLength } from '../measure/maths';
import { captureThumb } from '../views/thumb';
import type { RestoreResult } from '../plugins/views';
import { sharedAuthor } from '../plugins/bcf';
import { History } from './history';
import { bounds as ptsBounds, simplify } from './geometry';
import { boxCorners, ellipseInQuad, fractionsToPixels, layoutMarkups, markupName, rayToFraction, rebaseShape } from './layout';
import {
  KIND_LABEL, addComment, isBoxKind, addMarkup, buildMarkupDoc, compareModels, defaultColour, defaultSetTitle, markupDocJson, mergeSets,
  modelIdentity, newMarkup, newMarkupId, nowIso, parseMarkupDoc, referencedGuids, setCounts, uniqueSetTitle,
} from './model';
import type { ColourKey, Markup, MarkupKind, MarkupSet, ModelIdentity, ModelMatch, Weight } from './model';
import { extractAttachments } from './pdf';
import { buildReport, pictureWidthFor } from './report';
import type { PageSize, ReportImage } from './report';

export type ToolId =
  | 'select' | 'cloud' | 'cloudFree' | 'rect' | 'ellipse' | 'line' | 'arrow' | 'polyline' | 'polygon' | 'pen'
  | 'highlight' | 'highlightBox' | 'text' | 'callout' | 'pointer';

export type HowTo = 'none' | 'drag' | 'free' | 'poly' | 'click';

export interface ToolInfo {
  id: ToolId;
  label: string;
  kind: MarkupKind | null;
  how: HowTo;
  /** The group heading in the toolbar. */
  group: 'Select' | 'Cloud' | 'Annotate' | 'Highlight' | 'Shapes';
  hint: string;
}

export const TOOLS: readonly ToolInfo[] = [
  { id: 'select', label: 'Select', kind: null, how: 'none', group: 'Select', hint: 'Select and move markups. The orbit works as usual.' },
  { id: 'cloud', label: 'Cloud', kind: 'cloud', how: 'drag', group: 'Cloud', hint: 'Drag a rectangle. The cloud has scalloped edges.' },
  { id: 'cloudFree', label: 'Cloud draw', kind: 'cloud', how: 'free', group: 'Cloud', hint: 'Draw a closed outline. The cloud follows it.' },
  { id: 'callout', label: 'Callout', kind: 'callout', how: 'click', group: 'Annotate', hint: 'Click an element. A text box with a leader line follows it.' },
  { id: 'text', label: 'Text', kind: 'text', how: 'click', group: 'Annotate', hint: 'Click the model. A plain text box appears there.' },
  { id: 'pointer', label: 'Pointer', kind: 'pointer', how: 'click', group: 'Annotate', hint: 'Click an element. An arrow points at it.' },
  { id: 'highlight', label: 'Marker', kind: 'highlight', how: 'free', group: 'Highlight', hint: 'Draw with a wide translucent marker.' },
  { id: 'highlightBox', label: 'Highlight box', kind: 'highlightBox', how: 'drag', group: 'Highlight', hint: 'Drag a translucent box.' },
  { id: 'rect', label: 'Rectangle', kind: 'rect', how: 'drag', group: 'Shapes', hint: 'Drag a rectangle.' },
  { id: 'ellipse', label: 'Ellipse', kind: 'ellipse', how: 'drag', group: 'Shapes', hint: 'Drag an ellipse.' },
  { id: 'line', label: 'Line', kind: 'line', how: 'drag', group: 'Shapes', hint: 'Drag a straight line.' },
  { id: 'arrow', label: 'Arrow', kind: 'arrow', how: 'drag', group: 'Shapes', hint: 'Drag an arrow. The head is at the end.' },
  { id: 'polyline', label: 'Polyline', kind: 'polyline', how: 'poly', group: 'Shapes', hint: 'Click each corner. Double click or press Enter to finish.' },
  { id: 'polygon', label: 'Polygon', kind: 'polygon', how: 'poly', group: 'Shapes', hint: 'Click each corner. Double click or press Enter to close it.' },
  { id: 'pen', label: 'Pen', kind: 'pen', how: 'free', group: 'Shapes', hint: 'Draw a freehand line.' },
];

export function toolInfo(id: ToolId): ToolInfo {
  return TOOLS.find((t) => t.id === id)!;
}

const sleep = (ms: number): Promise<void> => new Promise((r) => setTimeout(r, ms));
const raf = (): Promise<void> => new Promise((r) => requestAnimationFrame(() => r()));

/** The camera drifted from the set's view: markups draw faded and the "Return to markup view" button shows. */
export function cameraAway(live: { position: Vec3; target: Vec3 }, set: { position: Vec3; target: Vec3 }): boolean {
  const d1 = [live.target[0] - live.position[0], live.target[1] - live.position[1], live.target[2] - live.position[2]];
  const d0 = [set.target[0] - set.position[0], set.target[1] - set.position[1], set.target[2] - set.position[2]];
  const l1 = Math.hypot(d1[0]!, d1[1]!, d1[2]!) || 1;
  const l0 = Math.hypot(d0[0]!, d0[1]!, d0[2]!) || 1;
  const cos = (d1[0]! * d0[0]! + d1[1]! * d0[1]! + d1[2]! * d0[2]!) / (l1 * l0);
  const angle = Math.acos(Math.max(-1, Math.min(1, cos)));
  const shift = Math.hypot(live.position[0] - set.position[0], live.position[1] - set.position[1], live.position[2] - set.position[2]) / l0;
  return angle > (4 * Math.PI) / 180 || shift > 0.05 || Math.abs(l1 / l0 - 1) > 0.08;
}

export interface ImportReport {
  ok: boolean;
  error?: string;
  sets: number;
  markups: number;
  added: number;
  replaced: number;
  /** GlobalIds the markup refers to that this model lacks. */
  unknownGuids: number;
  match: ModelMatch;
  warnings: string[];
  /** Markups and sets left out because they could not be read. */
  skipped: string[];
  /** The title of the set that was restored. */
  restored?: string;
}

export interface ExportedFile {
  name: string;
  bytes: Uint8Array;
  /** PDF only: what was rendered. */
  info?: PdfInfoReport;
}

export type PdfResolution = 'screen' | 150 | 200 | 300;
export const PDF_RESOLUTIONS: readonly PdfResolution[] = ['screen', 150, 200, 300];

export interface PdfInfoReport {
  resolution: PdfResolution;
  /** Pixel size of each picture (the first set's; all sets use the same size). */
  pictureWidth: number;
  pictureHeight: number;
  /** Set when the size was lowered to fit the GPU limits. */
  note: string;
  /** Rendering and writing, ms. */
  ms: number;
}

function stamp(): string {
  return new Date().toISOString().replace(/[-:]/g, '').slice(0, 13).replace('T', '-');
}
function slug(s: string): string {
  return s.normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^\w.-]+/g, '_').replace(/^_+|_+$/g, '').slice(0, 40) || 'markup';
}

function download(name: string, bytes: Uint8Array, type: string): void {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([bytes as Uint8Array<ArrayBuffer>], { type }));
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}

interface ViewsLike {
  capture(name?: string): import('../views/model').SavedView;
  restoreView(v: import('../views/model').SavedView, o?: { animate?: boolean }): RestoreResult;
  shareUrlFor(v: import('../views/model').SavedView): string;
}

/** Look of a markup that is not the toolbar's current one (scripts). */
export interface MarkupStyle {
  colour?: ColourKey;
  weight?: Weight;
  fill?: boolean;
  text?: string;
}

/** What undo and redo swap: the markups and the view of a set (Update view is undoable). */
interface SetState {
  markups: Markup[];
  view: MarkupSet['view'];
  camera: MarkupSet['camera'];
  thumb?: string;
}

export const SHARE_LINK_MAX = 1800;

export class MarkupController {
  sets: MarkupSet[] = [];
  activeId: string | null = null;
  /** The selected markup (id). */
  selected: string | null = null;
  tool: ToolId = 'select';
  private readonly colours: Partial<Record<ToolId, ColourKey>> = {};
  weight: Weight = 2;
  fill = false;
  /** Text for the next callout, text box or pointer. */
  text = '';
  page: PageSize = 'A4';
  /** Picture resolution of the PDF: the screen's pixels, or dots per inch of the picture on the page. */
  pdfResolution: PdfResolution = 200;
  /** Update view: shapes stay on the model (default) or on the screen. */
  updateKeep: 'model' | 'screen' = 'model';
  status = 'No markup sets yet';
  /** Show the markups of the active set on the model. */
  visible = true;
  /** Bumped on every change: views re-render on it. */
  rev = 0;
  /** The live view (view.ts) sets this: cancels a drawing in progress. */
  cancelDrawing: (() => void) | null = null;
  private readonly histories = new Map<string, History<SetState>>();
  private readonly listeners = new Set<(quiet: boolean) => void>();
  readonly geo: BcfController;
  private identity: { key: object; id: ModelIdentity } | null = null;

  constructor(readonly app: ViewerApp) {
    this.geo = new BcfController(app);
  }

  // ---------------------------------------------------------------- events, small state

  /** `quiet` changes (typing, dragging) only redraw the overlay: lists and forms keep what they show. */
  onChange(cb: (quiet: boolean) => void): () => void {
    this.listeners.add(cb);
    return () => this.listeners.delete(cb);
  }
  emit(quiet = false): void {
    this.rev++;
    for (const l of this.listeners) l(quiet);
  }
  setStatus(t: string): void {
    this.status = t;
    this.emit();
  }

  get author(): string {
    return sharedAuthor.get();
  }
  setAuthor(a: string): void {
    sharedAuthor.set(a);
    this.emit();
  }
  private get who(): string {
    return this.author.trim() || 'unknown';
  }

  get active(): MarkupSet | null {
    return this.sets.find((s) => s.id === this.activeId) ?? null;
  }
  get(id: string): MarkupSet | undefined {
    return this.sets.find((s) => s.id === id);
  }
  markup(id: string): { set: MarkupSet; m: Markup } | null {
    for (const set of this.sets) {
      const m = set.markups.find((x) => x.id === id);
      if (m) return { set, m };
    }
    return null;
  }
  private get views(): ViewsLike {
    const v = (window as unknown as { __xrayViews?: ViewsLike }).__xrayViews;
    if (!v) throw new Error('The saved views plugin is not available');
    return v;
  }

  colour(tool: ToolId = this.tool): ColourKey {
    const k = toolInfo(tool).kind;
    return this.colours[tool] ?? (k ? defaultColour(k) : 'red');
  }
  setColour(c: ColourKey): void {
    this.colours[this.tool] = c;
    // A selected markup takes the colour too.
    const sel = this.selected ? this.markup(this.selected) : null;
    if (sel) this.patch(sel.m.id, { colour: c });
    else this.emit();
  }
  setTool(t: ToolId): void {
    if (t !== this.tool) this.cancelDrawing?.();
    this.tool = t;
    if (t !== 'select') this.selected = null;
    this.emit();
  }
  setWeight(w: Weight): void {
    this.weight = w;
    const sel = this.selected ? this.markup(this.selected) : null;
    if (sel) this.patch(sel.m.id, { weight: w });
    else this.emit();
  }
  setFill(f: boolean): void {
    this.fill = f;
    const sel = this.selected ? this.markup(this.selected) : null;
    if (sel) this.patch(sel.m.id, { fill: f });
    else this.emit();
  }

  // ---------------------------------------------------------------- model identity

  get loaded(): boolean {
    return !!this.app.loaded;
  }
  get shift(): Vec3 {
    return this.geo.shift;
  }
  modelIdentity(): ModelIdentity {
    const loaded = this.app.loaded;
    if (!loaded) return modelIdentity(this.app.modelName, 0, []);
    if (this.identity?.key !== loaded) {
      const els = this.app.controller.model.elements;
      this.identity = { key: loaded, id: modelIdentity(this.app.modelName, els.length, els.map((e) => e.globalId).filter((g): g is string => !!g)) };
    }
    return this.identity.id;
  }
  hasGuid(g: string): boolean {
    return this.app.controller.model.byGlobalId.has(g);
  }

  onModel(): void {
    // The sets belong to the model that was open when they were made; they stay in the list (a different model shows a warning on restore).
    this.identity = null;
    this.cancelDrawing?.();
    this.emit();
  }

  // ---------------------------------------------------------------- sets

  /** The live camera as a BCF snapshot view (IFC frame), the base of the shapes of a set. */
  liveCamera(): BcfSnapshotView {
    const cam = this.app.renderer.camera;
    cam.updateMatrixWorld();
    const sh = this.shift;
    const f = cam.getWorldDirection(cam.position.clone());
    const up = cam.up.clone().applyQuaternion(cam.quaternion);
    return {
      position: viewerToIfc([cam.position.x, cam.position.y, cam.position.z], sh),
      direction: dirViewerToIfc([f.x, f.y, f.z]),
      up: dirViewerToIfc([up.x, up.y, up.z]),
      fov: cam.fov,
      aspect: cam.aspect,
    };
  }

  /** A new set from the current view; it becomes the active one. */
  newSet(title?: string): MarkupSet {
    if (!this.loaded) throw new Error('No model loaded');
    const t = title?.trim() ? uniqueSetTitle(title, this.sets) : defaultSetTitle(this.sets);
    const view = this.views.capture(t);
    delete view.thumb;
    const now = nowIso();
    const set: MarkupSet = {
      id: newMarkupId('s'), title: t, author: this.who, created: now, updated: now,
      view, camera: this.liveCamera(), markups: [], nextNumber: 1,
    };
    const thumb = captureThumb(this.app);
    if (thumb) set.thumb = thumb;
    this.sets.push(set);
    this.histories.set(set.id, new History());
    this.activeId = set.id;
    this.selected = null;
    this.setStatus(`Markup set "${t}" created from the current view`);
    return set;
  }

  /** Make a set active and (by default) bring back its view. */
  async select(id: string | null, o: { restore?: boolean; animate?: boolean } = {}): Promise<RestoreResult | null> {
    this.cancelDrawing?.();
    this.activeId = id;
    this.selected = null;
    const set = this.active;
    this.emit();
    if (!set || o.restore === false) return null;
    return this.restore(set.id, o.animate ?? true);
  }

  restore(id: string, animate = true): RestoreResult {
    const set = this.get(id);
    if (!set) throw new Error(`No markup set ${id}`);
    if (!this.loaded) throw new Error('No model loaded');
    const r = this.views.restoreView(set.view, { animate });
    this.activeId = set.id;
    const s = r.missing.length ? `; ${r.missing.length} element${r.missing.length === 1 ? '' : 's'} of the view not in this model` : '';
    this.setStatus(`View of "${set.title}" restored${s}`);
    return r;
  }

  renameSet(id: string, title: string): void {
    const s = this.get(id);
    if (!s) return;
    s.title = uniqueSetTitle(title, this.sets, id);
    s.view.name = s.title;
    s.updated = nowIso();
    this.emit();
  }

  deleteSet(id: string): void {
    const i = this.sets.findIndex((s) => s.id === id);
    if (i < 0) return;
    const [gone] = this.sets.splice(i, 1);
    this.histories.delete(id);
    if (this.activeId === id) {
      this.activeId = null;
      this.selected = null;
    }
    this.setStatus(`Markup set "${gone!.title}" deleted`);
  }

  // ---------------------------------------------------------------- markups

  private history(set: MarkupSet): History<SetState> {
    let h = this.histories.get(set.id);
    if (!h) { h = new History(); this.histories.set(set.id, h); }
    return h;
  }
  get canUndo(): boolean {
    const s = this.active;
    return !!s && this.history(s).canUndo;
  }
  get canRedo(): boolean {
    const s = this.active;
    return !!s && this.history(s).canRedo;
  }

  private stateOf(set: MarkupSet): SetState {
    const st: SetState = { markups: set.markups, view: set.view, camera: set.camera };
    if (set.thumb) st.thumb = set.thumb;
    return st;
  }
  private applyState(set: MarkupSet, st: SetState): void {
    set.markups = st.markups;
    set.view = st.view;
    set.camera = st.camera;
    if (st.thumb) set.thumb = st.thumb;
    else delete set.thumb;
  }

  /**
   * Update view: capture the set's view again from the current camera and state. Markups anchored in 3D keep their
   * anchors. Shapes are re-projected through their depth plane so they stay on the same model area (`keep` "model",
   * default), or keep their place on the screen (`keep` "screen"). Undoable.
   */
  updateView(id: string, keep: 'model' | 'screen' = this.updateKeep): { shapes: number; moved: number; kept: number } {
    const set = this.get(id);
    if (!set) throw new Error(`No markup set ${id}`);
    if (!this.loaded) throw new Error('No model loaded');
    this.cancelDrawing?.();
    const old = set.camera;
    const view = this.views.capture(set.title);
    delete view.thumb;
    view.id = set.view.id;
    view.created = set.view.created;
    const camera = this.liveCamera();
    this.record(set);
    let moved = 0;
    let kept = 0;
    let shapes = 0;
    for (const m of set.markups) {
      if (!m.shape) continue;
      shapes++;
      if (keep === 'screen') { kept++; continue; }
      const r = rebaseShape(m.shape, old, camera, this.shift, isBoxKind(m.kind) || (m.kind === 'cloud' && m.shape.points.length === 2));
      if (r) { m.shape = r; moved++; } else kept++;
    }
    set.view = view;
    set.camera = camera;
    const thumb = captureThumb(this.app);
    if (thumb) set.thumb = thumb;
    set.updated = nowIso();
    const msg = keep === 'screen' ? 'shapes stay on the screen' : `${moved} of ${shapes} shape${shapes === 1 ? '' : 's'} kept on the model${kept ? `, ${kept} left on the screen (behind the camera)` : ''}`;
    this.setStatus(`View of "${set.title}" updated: ${msg}`);
    return { shapes, moved, kept };
  }

  /** Record the state before a change of the set (undo goes back to it). */
  record(set: MarkupSet): void {
    this.history(set).record(this.stateOf(set));
  }

  undo(): boolean {
    const set = this.active;
    if (!set) return false;
    const prev = this.history(set).undo(this.stateOf(set));
    if (!prev) return false;
    this.applyState(set, prev);
    set.updated = nowIso();
    if (this.selected && !set.markups.some((m) => m.id === this.selected)) this.selected = null;
    this.setStatus('Undone');
    return true;
  }
  redo(): boolean {
    const set = this.active;
    if (!set) return false;
    const next = this.history(set).redo(this.stateOf(set));
    if (!next) return false;
    this.applyState(set, next);
    set.updated = nowIso();
    if (this.selected && !set.markups.some((m) => m.id === this.selected)) this.selected = null;
    this.setStatus('Redone');
    return true;
  }

  /** Add a finished markup to the active set (numbered, undoable, selected). */
  add(m: Markup, set: MarkupSet | null = this.active): Markup {
    if (!set) throw new Error('No markup set: create one from the view first');
    this.record(set);
    addMarkup(set, m);
    this.selected = m.id;
    this.setStatus(`${KIND_LABEL[m.kind]} ${m.number} added`);
    return m;
  }

  /** Change fields of a markup. `quiet`: no history entry for this keystroke, a redraw only. */
  patch(id: string, p: Partial<Pick<Markup, 'text' | 'colour' | 'weight' | 'fill' | 'status' | 'assignee' | 'due' | 'offset' | 'shape'>>, o: { quiet?: boolean; noHistory?: boolean } = {}): boolean {
    const f = this.markup(id);
    if (!f) return false;
    if (!o.quiet && !o.noHistory) this.record(f.set);
    const m = f.m;
    if (p.text !== undefined) m.text = p.text;
    if (p.colour) m.colour = p.colour;
    if (p.weight) m.weight = p.weight;
    if (p.fill !== undefined) m.fill = p.fill;
    if (p.status) m.status = p.status;
    if (p.assignee !== undefined) { if (p.assignee.trim()) m.assignee = p.assignee.trim(); else delete m.assignee; }
    if (p.due !== undefined) { if (p.due) m.due = p.due; else delete m.due; }
    if (p.offset) m.offset = [p.offset[0], p.offset[1]];
    if (p.shape) m.shape = p.shape;
    m.modified = nowIso();
    f.set.updated = m.modified;
    this.emit(o.quiet === true);
    return true;
  }

  remove(id: string): boolean {
    const f = this.markup(id);
    if (!f) return false;
    this.record(f.set);
    f.set.markups = f.set.markups.filter((m) => m.id !== id);
    f.set.updated = nowIso();
    if (this.selected === id) this.selected = null;
    this.setStatus(`${KIND_LABEL[f.m.kind]} ${f.m.number} deleted`);
    return true;
  }

  selectMarkup(id: string | null): void {
    this.selected = id;
    this.emit();
  }

  comment(id: string, text: string): boolean {
    const f = this.markup(id);
    if (!f || !text.trim()) return false;
    this.record(f.set);
    addComment(f.m, this.who, text);
    f.set.updated = f.m.modified!;
    this.setStatus(`Comment added to ${markupName(f.m)}`);
    return true;
  }

  // ---------------------------------------------------------------- drawing: screen to markup

  private canvasSize(): { W: number; H: number } {
    const cv = this.app.canvas;
    return { W: Math.max(1, cv.clientWidth), H: Math.max(1, cv.clientHeight) };
  }

  /** The depth (m along the set camera's view) of the plane a shape drawn around canvas point (cx, cy) lies on. */
  private depthAt(view: BcfSnapshotView, cx: number, cy: number): number {
    const { W, H } = this.canvasSize();
    const hit = this.geo.pick((cx / W) * 2 - 1, -((cy / H) * 2 - 1));
    const tg = this.app.renderer.controls.target;
    let depth = shapeFraction(view, this.shift, hit ? hit.point : [tg.x, tg.y, tg.z]).depth;
    if (!(depth > 0.05)) depth = Math.max(1, shapeFraction(view, this.shift, [tg.x, tg.y, tg.z]).depth);
    return depth;
  }

  /** Points drawn on the canvas (CSS px) as fractions of the set camera's view on the plane under the middle of the drawing. */
  screenToShape(set: MarkupSet, screen: ReadonlyArray<readonly [number, number]>): { points: Array<[number, number]>; depth: number } | null {
    const { W, H } = this.canvasSize();
    const b = ptsBounds(screen.flatMap((p) => [p[0], p[1]]));
    const depth = this.depthAt(set.camera, (b.x0 + b.x1) / 2, (b.y0 + b.y1) / 2);
    const cam = this.app.renderer.camera;
    cam.updateMatrixWorld();
    const out: Array<[number, number]> = [];
    for (const [x, y] of screen) {
      const ray = cameraRay(cam, (x / W) * 2 - 1, -((y / H) * 2 - 1));
      const f = rayToFraction(set.camera, this.shift, [ray.origin.x, ray.origin.y, ray.origin.z], [ray.direction.x, ray.direction.y, ray.direction.z], depth);
      if (!f) return null;
      const r = (v: number): number => Math.round(v * 1e5) / 1e5;
      out.push([r(f.u), r(f.v)]);
    }
    return { points: out, depth: Math.round(depth * 1e4) / 1e4 };
  }

  /** Move a shape by a screen delta (CSS px), on its own plane. */
  moveShape(id: string, from: ReadonlyArray<readonly [number, number]>, dx: number, dy: number): boolean {
    const f = this.markup(id);
    if (!f?.m.shape) return false;
    const { W, H } = this.canvasSize();
    const cam = this.app.renderer.camera;
    cam.updateMatrixWorld();
    const out: Array<[number, number]> = [];
    for (const [x, y] of from) {
      const ray = cameraRay(cam, ((x + dx) / W) * 2 - 1, -(((y + dy) / H) * 2 - 1));
      const q = rayToFraction(f.set.camera, this.shift, [ray.origin.x, ray.origin.y, ray.origin.z], [ray.direction.x, ray.direction.y, ray.direction.z], f.m.shape.depth);
      if (!q) return false;
      out.push([q.u, q.v]);
    }
    f.m.shape = { points: out, depth: f.m.shape.depth };
    f.m.modified = nowIso();
    this.emit(true);
    return true;
  }

  /** A drawn shape (points in canvas CSS px) becomes a markup of the active set. */
  addShape(tool: ToolId, screen: ReadonlyArray<readonly [number, number]>, style: MarkupStyle = {}): Markup | null {
    const set = this.active;
    const info = toolInfo(tool);
    if (!set || !info.kind) return null;
    let pts: ReadonlyArray<readonly [number, number]> = screen;
    if (info.how === 'drag') pts = [screen[0]!, screen[screen.length - 1]!];
    else if (info.how === 'free') {
      const flat = simplify(screen.flatMap((p) => [p[0], p[1]]), tool === 'cloudFree' ? 3 : 1.2);
      const p2: Array<[number, number]> = [];
      for (let i = 0; i < flat.length; i += 2) p2.push([flat[i]!, flat[i + 1]!]);
      pts = p2.length > 400 ? p2.filter((_p, i) => i % Math.ceil(p2.length / 400) === 0) : p2;
    }
    if (pts.length < 2) return null;
    const sh = this.screenToShape(set, pts);
    if (!sh) {
      this.setStatus('The drawing is not in front of the view camera');
      return null;
    }
    const kind = info.kind;
    const m = newMarkup(kind, {
      author: this.who, colour: style.colour ?? this.colour(tool), weight: style.weight ?? this.weight, fill: style.fill ?? this.fill, shape: sh,
      ...(style.text ? { text: style.text } : {}),
    });
    return this.add(m, set);
  }

  /** A click on the model (canvas CSS px) places a callout, text box or pointer. */
  addAnchored(tool: ToolId, cx: number, cy: number, text = this.text, style: MarkupStyle = {}): Markup | null {
    const set = this.active;
    const info = toolInfo(tool);
    if (!set || !info.kind) return null;
    const { W, H } = this.canvasSize();
    const hit = this.geo.pick((cx / W) * 2 - 1, -((cy / H) * 2 - 1));
    let point: Vec3;
    let guid: string | undefined;
    if (hit) {
      point = hit.point;
      guid = this.app.controller.model.elements[hit.element]?.globalId;
    } else if (tool === 'text') {
      // A text box on empty space: a point on the plane of the orbit target, along the ray.
      const tg = this.app.renderer.controls.target;
      const cam = this.app.renderer.camera;
      const ray = cameraRay(cam, (cx / W) * 2 - 1, -((cy / H) * 2 - 1));
      const dist = Math.max(0.5, Math.hypot(tg.x - cam.position.x, tg.y - cam.position.y, tg.z - cam.position.z));
      point = [ray.origin.x + ray.direction.x * dist, ray.origin.y + ray.direction.y * dist, ray.origin.z + ray.direction.z * dist];
    } else {
      this.setStatus('No surface under the cursor; click the model');
      return null;
    }
    const m = newMarkup(info.kind, {
      author: this.who, colour: style.colour ?? this.colour(tool), weight: style.weight ?? this.weight, text,
      anchor: this.makeAnchor(point, guid, tool === 'text' ? 'point' : 'element'),
      offset: this.defaultOffset(set, tool),
    });
    return this.add(m, set);
  }

  /** The next box offset: the quadrant turns, so new boxes do not stack (like BCF). */
  private defaultOffset(set: MarkupSet, tool: ToolId): [number, number] {
    const n = set.markups.filter((m) => m.anchor).length;
    const base: [number, number] = tool === 'pointer' ? [-0.1, -0.08] : tool === 'text' ? [0.05, -0.04] : [0.1, -0.09];
    const k = n % 4;
    const grow = 1 + 0.35 * Math.floor(n / 4);
    return [base[0] * (k === 1 || k === 3 ? -1 : 1) * grow, base[1] * (k >= 2 ? -1 : 1) * grow];
  }

  private makeAnchor(point: Vec3, guid: string | undefined, kind: 'element' | 'point'): NonNullable<Markup['anchor']> {
    const a: NonNullable<Markup['anchor']> = { kind: guid ? kind : 'point', point: viewerToIfc(point, this.shift) };
    if (guid) {
      a.elementGuid = guid;
      const id = this.app.controller.model.byGlobalId.get(guid);
      const b = id !== undefined ? this.app.controller.model.elements[id]?.bounds : undefined;
      if (b) {
        const d = dirViewerToIfc([point[0] - (b[0] + b[3]) / 2, point[1] - (b[1] + b[4]) / 2, point[2] - (b[2] + b[5]) / 2]);
        const r = (x: number): number => Math.round(x * 1e6) / 1e6;
        a.local = [r(d[0]), r(d[1]), r(d[2])];
      }
    }
    return a;
  }

  /** The measurements of the measure tool, to link as markups. */
  measurements(): readonly Measurement[] {
    return currentMeasurements();
  }

  /** A measurement of the measure tool becomes a measurement markup (its own dimension line and length). */
  linkMeasurement(measurementId: number, text = ''): Markup | null {
    const set = this.active;
    const meas = currentMeasurements().find((x) => x.id === measurementId);
    if (!set || !meas) return null;
    const link = this.geo.measureLink(meas);
    const mid: Vec3 = [(link.a[0] + link.b[0]) / 2, (link.a[1] + link.b[1]) / 2, (link.a[2] + link.b[2]) / 2];
    const m = newMarkup('measure', {
      author: this.who, colour: 'blue', weight: this.weight, text,
      anchor: { kind: 'measurement', point: mid, measurement: link }, offset: this.defaultOffset(set, 'callout'),
    });
    return this.add(m, set);
  }

  // ---------------------------------------------------------------- view of the camera against the set

  /** True when the live camera is away from the active set's view. */
  away(): boolean {
    const set = this.active;
    if (!set) return false;
    const cam = this.app.renderer.camera;
    const t = this.app.renderer.controls.target;
    const c = set.view.camera;
    return cameraAway({ position: [cam.position.x, cam.position.y, cam.position.z], target: [t.x, t.y, t.z] }, { position: c.position, target: c.target });
  }

  // ---------------------------------------------------------------- layout context for the live camera

  private readonly vp = new Matrix4();

  /** Layout context for the live camera over an image of w x h pixels (the overlay passes its CSS size). */
  layoutContext(set: MarkupSet, w: number, h: number, extra: Partial<LayoutContext> = {}): LayoutContext {
    const cam = this.app.renderer.camera;
    cam.updateMatrixWorld();
    this.vp.multiplyMatrices(cam.projectionMatrix, cam.matrixWorldInverse);
    const m = this.vp.elements;
    return {
      width: w, height: h, shift: this.shift, scale: 1,
      project: (p) => projectPoint(m, w, h, p),
      occluded: (p) => this.geo.occluded(p),
      units: this.geo.units,
      element: (g) => this.geo.elementFrame(g),
      shapeView: set.camera,
      ...extra,
    };
  }

  // ---------------------------------------------------------------- export

  /** Wait for the ghost animation and the classification to settle after a restore. */
  private async settleView(): Promise<void> {
    try {
      this.app.controller.settle();
    } catch {
      /* a test double without settle */
    }
    await sleep(450);
    await raf();
    await raf();
  }

  /** The pixel ratio the PDF pictures are rendered at, and why it was lowered (empty when it was not). */
  private pdfPixelRatio(res: PdfResolution, page: PageSize): { pr: number; note: string } {
    const three = this.app.renderer.renderer;
    const cur = three.getPixelRatio();
    if (res === 'screen') return { pr: cur, note: '' };
    const cssW = Math.max(1, this.app.canvas.clientWidth);
    const cssH = Math.max(1, this.app.canvas.clientHeight);
    const want = pictureWidthFor(page, cssW, cssH, res) / cssW;
    // GPU limits: texture and renderbuffer size, and a cap of 36 million pixels (the float targets of the passes).
    let side = three.capabilities.maxTextureSize || 4096;
    try {
      const gl = three.getContext();
      side = Math.min(side, Number(gl.getParameter(gl.MAX_RENDERBUFFER_SIZE)) || side);
    } catch {
      /* keep the texture limit */
    }
    side = Math.min(side, 8192);
    const max = Math.min(side / cssW, side / cssH, Math.sqrt(36e6 / (cssW * cssH)));
    const pr = Math.max(cur, Math.min(want, max));
    const note = want > max && max >= cur ? `The picture size was lowered to ${Math.floor(cssW * pr)} px wide to fit the graphics card (${res} dpi wanted).` : '';
    return { pr, note };
  }

  /**
   * Render the current view to two JPEGs: clean and with the markups of `set` burned in. At a PDF resolution the drawing
   * buffer of the renderer is enlarged for one frame (setPixelRatio and resize: the passes all follow the buffer size), read
   * into a 2D canvas in the same task, and put back, so the canvas shows no flicker. The markups scale with the picture.
   */
  private async renderPages(set: MarkupSet, res: PdfResolution, page: PageSize): Promise<{ clean: ReportImage; marked: ReportImage; note: string }> {
    const r = this.app.renderer;
    const three = r.renderer;
    const src = this.app.canvas;
    const oldPr = three.getPixelRatio();
    const { pr, note } = this.pdfPixelRatio(res, page);
    const big = Math.abs(pr - oldPr) > 1e-6;
    let cv: HTMLCanvasElement;
    let g: CanvasRenderingContext2D | null;
    let w: number;
    let h: number;
    try {
      if (big) {
        three.setPixelRatio(pr);
        r.resize();
      }
      r.markDirty();
      r.render();
      r.markDirty();
      r.render(); // a second frame lets the passes that depend on the previous frame settle at this size
      w = src.width;
      h = src.height;
      cv = document.createElement('canvas');
      cv.width = w;
      cv.height = h;
      g = cv.getContext('2d');
      if (!g) throw new Error('No 2D canvas to render the page');
      g.fillStyle = '#e9edf2'; // the clear colour of the renderer, under any transparent pixel
      g.fillRect(0, 0, w, h);
      g.drawImage(src, 0, 0);
    } finally {
      if (big) {
        three.setPixelRatio(oldPr);
        r.resize();
      }
      r.markDirty();
    }
    const toJpeg = async (): Promise<ReportImage> => {
      const blob = await new Promise<Blob | null>((res2) => cv.toBlob(res2, 'image/jpeg', 0.9));
      if (!blob) throw new Error('The canvas could not be read as JPEG');
      return { bytes: new Uint8Array(await blob.arrayBuffer()), width: w, height: h };
    };
    const clean = await toJpeg();
    // Sizes are CSS pixels times the factor between the picture and the screen, so the markup looks as it does on screen.
    const k = h / Math.max(1, src.clientHeight);
    const ctx = this.layoutContext(set, w, h, { scale: k });
    drawOps(g as unknown as Ctx2D, layoutMarkups(set.markups, ctx));
    const marked = await toJpeg();
    return { clean, marked, note };
  }

  /** JSON document of some sets (default all), as text. */
  exportJson(ids?: readonly string[]): ExportedFile {
    const sets = this.pick(ids);
    if (!sets.length) throw new Error('No markup set to export');
    const link = this.shareLinkOf(sets[0]!);
    const doc = buildMarkupDoc(this.modelIdentity(), sets, link ? { link } : {});
    const bytes = new TextEncoder().encode(markupDocJson(doc));
    this.setStatus(`JSON ready: ${sets.length} set${sets.length === 1 ? '' : 's'}, ${(bytes.length / 1024).toFixed(1)} KB`);
    return { name: `xray-markup-${slug(this.app.modelName)}-${sets.length === 1 ? slug(sets[0]!.title) : `${sets.length}-sets`}-${stamp()}.json`, bytes };
  }

  downloadJson(ids?: readonly string[]): ExportedFile {
    const f = this.exportJson(ids);
    download(f.name, f.bytes, 'application/json');
    return f;
  }

  /** The share link of a set's view when it is an http or https page and the link is short enough. */
  shareLinkOf(set: MarkupSet): string {
    if (!/^https?:$/.test(location.protocol)) return '';
    try {
      const url = this.views.shareUrlFor(set.view);
      return url.length <= SHARE_LINK_MAX ? url : '';
    } catch {
      return '';
    }
  }

  private pick(ids?: readonly string[]): MarkupSet[] {
    return ids ? ids.map((i) => this.get(i)).filter((s): s is MarkupSet => !!s) : [...this.sets];
  }

  /**
   * The PDF of some sets (default: all). Each set's view is restored and rendered twice (clean, with markups); the view
   * you were in comes back afterwards. The JSON of the sets is attached.
   */
  async exportPdf(o: { ids?: readonly string[]; page?: PageSize; resolution?: PdfResolution } = {}): Promise<ExportedFile> {
    if (!this.loaded) throw new Error('No model loaded');
    const t0 = performance.now();
    const page = o.page ?? this.page;
    const res = o.resolution ?? this.pdfResolution;
    let note = '';
    let size = { w: 0, h: 0 };
    const sets = this.pick(o.ids);
    if (!sets.length) throw new Error('No markup set to export');
    const keep = this.views.capture('before export');
    const keepActive = this.activeId;
    const keepTool = this.tool;
    this.cancelDrawing?.();
    this.setStatus('Rendering the PDF pages...');
    const items: Array<{ set: MarkupSet; clean: ReportImage; marked: ReportImage; link?: string }> = [];
    try {
      for (const set of sets) {
        this.views.restoreView(set.view, { animate: false });
        await this.settleView();
        const pages = await this.renderPages(set, res, page);
        if (pages.note) note = pages.note;
        size = { w: pages.clean.width, h: pages.clean.height };
        const link = this.shareLinkOf(set);
        items.push({ set, clean: pages.clean, marked: pages.marked, ...(link ? { link } : {}) });
      }
    } finally {
      this.views.restoreView(keep, { animate: false });
      this.activeId = keepActive;
      this.tool = keepTool;
    }
    const json = this.exportJson(sets.map((s) => s.id));
    const bytes = buildReport(items, {
      page, model: this.modelIdentity(), author: this.author, date: new Date(),
      json: json.bytes, jsonName: json.name,
    });
    const name = `xray-markup-${slug(this.app.modelName)}-${sets.length === 1 ? slug(sets[0]!.title) : `${sets.length}-sets`}-${stamp()}.pdf`;
    const ms = Math.round(performance.now() - t0);
    const info: PdfInfoReport = { resolution: res, pictureWidth: size.w, pictureHeight: size.h, note, ms };
    this.setStatus(`PDF ready: ${items.length} set${items.length === 1 ? '' : 's'}, pictures ${size.w} x ${size.h} px, ${(bytes.length / 1024).toFixed(0)} KB, ${(ms / 1000).toFixed(1)} s${note ? `. ${note}` : ''}`);
    return { name, bytes, info };
  }

  async downloadPdf(o: { ids?: readonly string[]; page?: PageSize; resolution?: PdfResolution } = {}): Promise<ExportedFile> {
    const f = await this.exportPdf(o);
    download(f.name, f.bytes, 'application/pdf');
    return f;
  }

  // ---------------------------------------------------------------- import

  /** Import a markup document (JSON text) and restore the first set's view. */
  async importJson(text: string, o: { restore?: boolean } = {}): Promise<ImportReport> {
    const empty = (error: string): ImportReport => ({ ok: false, error, sets: 0, markups: 0, added: 0, replaced: 0, unknownGuids: 0, match: 'unknown', warnings: [], skipped: [] });
    const p = parseMarkupDoc(text);
    if (p.error) {
      this.setStatus(p.error);
      return empty(p.error);
    }
    if (!this.loaded) {
      const e = 'Open the model first, then open the markup file.';
      this.setStatus(e);
      return empty(e);
    }
    const cmp = compareModels(p.model, this.modelIdentity());
    const warnings: string[] = [];
    if (cmp.message) warnings.push(cmp.message);
    const unknown = new Set<string>();
    for (const s of p.sets) for (const g of referencedGuids(s)) if (!this.hasGuid(g)) unknown.add(g);
    if (unknown.size) warnings.push(`${unknown.size} element${unknown.size === 1 ? '' : 's'} named in the markup ${unknown.size === 1 ? 'is' : 'are'} not in this model; their markups and view parts are left out or stay where they were drawn.`);
    if (p.bad.length) warnings.push(`${p.bad.length} item${p.bad.length === 1 ? '' : 's'} in the file could not be read.`);
    const merged = mergeSets(this.sets, p.sets);
    this.sets = merged.sets;
    for (const s of p.sets) if (!this.histories.has(s.id)) this.histories.set(s.id, new History());
    const first = p.sets[0]!;
    const rep: ImportReport = {
      ok: true, sets: p.sets.length, markups: p.sets.reduce((a, s) => a + s.markups.length, 0), added: merged.added, replaced: merged.replaced,
      unknownGuids: unknown.size, match: cmp.match, warnings, skipped: p.bad,
    };
    if (o.restore !== false) {
      this.activeId = first.id;
      this.selected = null;
      this.views.restoreView(first.view, { animate: false });
      rep.restored = first.title;
    }
    const n = rep.markups;
    this.setStatus(`Markup opened: ${p.sets.length} set${p.sets.length === 1 ? '' : 's'}, ${n} markup${n === 1 ? '' : 's'}${warnings.length ? `. Warning: ${warnings.join(' ')}` : ''}`);
    return rep;
  }

  /** Import a dropped or picked file: a markup JSON file, or a PDF that carries one. */
  async importFile(file: File | Blob): Promise<ImportReport> {
    const name = (file as File).name ?? '';
    const bytes = new Uint8Array(await file.arrayBuffer());
    const isPdf = /\.pdf$/i.test(name) || (bytes[0] === 0x25 && bytes[1] === 0x50 && bytes[2] === 0x44 && bytes[3] === 0x46);
    let text: string;
    if (isPdf) {
      const files = await extractAttachments(bytes);
      const hit = files.find((f) => /\.json$/i.test(f.name) || /json/.test(f.mime)) ?? files[0];
      if (!hit) {
        const e = 'This PDF does not carry markup data. Use a PDF exported from the Markup tool.';
        this.setStatus(e);
        return { ok: false, error: e, sets: 0, markups: 0, added: 0, replaced: 0, unknownGuids: 0, match: 'unknown', warnings: [], skipped: [] };
      }
      text = new TextDecoder().decode(hit.data);
    } else text = new TextDecoder().decode(bytes);
    return this.importJson(text);
  }

  // ---------------------------------------------------------------- BCF

  get bcfAvailable(): boolean {
    return !!window.__xrayBcf;
  }

  /**
   * A BCF topic for a set (or one markup of it): the set's view as the viewpoint with a snapshot, the markups as BCF
   * annotations and shapes, the comments as topic comments. Returns the topic guid. Needs the BCF tool.
   */
  async toBcf(setId: string, markupId?: string): Promise<string> {
    const bcf = window.__xrayBcf;
    if (!bcf) throw new Error('The BCF tool is not available in this build');
    const set = this.get(setId);
    if (!set) throw new Error(`No markup set ${setId}`);
    const list = markupId ? set.markups.filter((m) => m.id === markupId) : set.markups;
    if (markupId && !list.length) throw new Error(`No markup ${markupId} in "${set.title}"`);
    this.restore(set.id, false);
    await this.settleView();
    const open = list.some((m) => m.status === 'open');
    const one = markupId ? list[0]! : null;
    const topic = bcf.createTopic({
      title: one ? `${set.title}: ${markupName(one)}${one.text ? `, ${one.text.slice(0, 50)}` : ''}` : set.title,
      description: one?.text ?? `Markup set "${set.title}" with ${list.length} markup${list.length === 1 ? '' : 's'}.`,
      status: open ? 'Open' : 'Resolved',
      author: this.who,
      ...(one?.assignee ? { assignedTo: one.assignee } : {}),
      ...(one?.due ? { dueDate: one.due } : {}),
    }) as { guid: string };
    const { W, H } = this.canvasSize();
    const ctx = this.layoutContext(set, W, H);
    const sh = this.shift;
    for (const m of list) {
      const label = `${m.number}. ${m.text}`.trim();
      try {
        if (m.anchor && m.kind !== 'measure') {
          const p = anchorPoint(m.anchor, { shift: sh, element: (g) => this.geo.elementFrame(g) }).p;
          bcf.addAnnotation(topic.guid, {
            type: m.kind === 'text' ? 'note' : m.kind === 'pointer' ? 'arrow' : 'callout',
            text: label,
            anchor: m.anchor.kind === 'element' && m.anchor.elementGuid ? { kind: 'element', point: p, elementGuid: m.anchor.elementGuid } : { kind: 'point', point: p },
            ...(m.offset ? { offset: m.offset } : {}),
          });
        } else if (m.anchor?.measurement) {
          const ml = m.anchor.measurement;
          const mid = ifcToViewer(m.anchor.point, sh);
          bcf.addAnnotation(topic.guid, { type: 'callout', text: `${label} ${formatLength(ml.distance, this.geo.units)}`.trim(), anchor: { kind: 'point', point: mid } });
        } else if (m.shape) {
          const px = this.bcfPixels(m, ctx);
          if ((m.kind === 'rect' || m.kind === 'highlightBox') && m.shape.points.length === 2) bcf.addShape(topic.guid, 'rect', [[px[0]!, px[1]!], [px[4]!, px[5]!]], label);
          else {
            const pts: Array<[number, number]> = [];
            for (let i = 0; i < px.length; i += 2) pts.push([px[i]!, px[i + 1]!]);
            bcf.addShape(topic.guid, 'freehand', pts, label);
          }
        }
      } catch (e) {
        this.setStatus(`${markupName(m)} could not be copied to BCF: ${e instanceof Error ? e.message : String(e)}`);
      }
      for (const c of m.comments) bcf.addComment(topic.guid, `${m.number}. ${c.text}`, { author: c.author });
    }
    this.setStatus(`BCF topic created from "${set.title}". Open the BCF tool to review and export it.`);
    return topic.guid;
  }

  /** Pixels (canvas CSS px) of a shape markup for a BCF shape: closed shapes are closed again, arrows get their head. */
  private bcfPixels(m: Markup, ctx: LayoutContext): number[] {
    const sh = m.shape!;
    let pts: Array<readonly [number, number]> = sh.points;
    if (m.kind === 'rect' || m.kind === 'highlightBox') pts = boxCorners(sh.points);
    if (m.kind === 'cloud' && sh.points.length === 2) pts = boxCorners(sh.points);
    const px = fractionsToPixels(pts, sh.depth, ctx);
    if (!px) throw new Error('not in front of the camera');
    if (m.kind === 'ellipse') {
      const e = ellipseInQuad(boxCorners(sh.points), 40);
      e.push(e[0]!);
      return fractionsToPixels(e, sh.depth, ctx) ?? px;
    }
    if (m.kind === 'polygon' || m.kind === 'cloud' || m.kind === 'rect' || m.kind === 'highlightBox') {
      return [...px, px[0]!, px[1]!];
    }
    if (m.kind === 'arrow') {
      const n = px.length;
      const x1 = px[n - 4]!, y1 = px[n - 3]!, x2 = px[n - 2]!, y2 = px[n - 1]!;
      const l = Math.hypot(x2 - x1, y2 - y1) || 1;
      const ux = (x2 - x1) / l, uy = (y2 - y1) / l;
      const hl = Math.min(14, l * 0.5);
      return [x1, y1, x2, y2, x2 - ux * hl - uy * hl * 0.5, y2 - uy * hl + ux * hl * 0.5, x2, y2, x2 - ux * hl + uy * hl * 0.5, y2 - uy * hl - ux * hl * 0.5];
    }
    return px;
  }

  // ---------------------------------------------------------------- summary for scripts

  list(): Array<{ id: string; title: string; markups: number; open: number; resolved: number; active: boolean }> {
    return this.sets.map((s) => ({ id: s.id, title: s.title, ...setCounts(s), markups: s.markups.length, active: s.id === this.activeId }));
  }
}

