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
import { dirIfcToViewer, dirViewerToIfc, ifcToViewer, viewerToIfc } from '../bcf/model';
import type { BcfSnapshotView, Vec3 } from '../bcf/model';
import { attachGuids, describeAttachment, isSpatial, viewLockState } from '../bcf/attach';
import type { AttachDescription, Attachment, LockState, ViewLockMode } from '../bcf/attach';
import { OcclusionCache, VIEWLOCK_MODES, viewLockSetting } from '../bcf/attach';
import { loadedIdentity, modelLabel, scopeOf, splitByScope } from './scope';
import type { OtherGroup, ScopeInfo } from './scope';
import { cameraRay } from '../measure/geometry';
import type { ResolveOptions } from './reprojectScene';
import type { SurfaceData } from '../bcf/attach';
import { findHint, fractionInput, inferAttachment, projectRegion, projectSurface, projectSurfaceData, screenInput } from './attachScene';
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
  KIND_LABEL, attachmentOf, isBoxKind, isSheetSet, needsAttach, addMarkup, buildMarkupDoc, compareModels, defaultColour, defaultSetTitle, markupDocJson, mergeSets,
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
  /** The markup whose Change menu of the attachment chip is open. */
  attachMenuOpen: string | null = null;
  /** The next click in the view picks a measurement or a penetration for this markup (the chip's pick choices). */
  pickLink: { id: string; kind: 'measurement' | 'penetration' } | null = null;
  /** View-locked markups in 3D: "near view + pin" (default), "pin only" or "hidden". A per-viewer display setting. */
  get viewLocked3d(): ViewLockMode {
    return viewLockSetting.mode;
  }
  set viewLocked3d(v: ViewLockMode) {
    viewLockSetting.mode = v;
  }
  /** The live view (view.ts) sets this: cancels a drawing in progress. */
  cancelDrawing: (() => void) | null = null;
  /**
   * A sketch is being edited: the drawing toolbar is up and the view takes pointer and key input (select, move, delete,
   * undo). Set by the Issues panel (Edit drawing, New sketch) and by choosing a drawing tool; Done clears it.
   */
  editing = false;
  /** src/issues sets this: "Raise as issue" (a new issue from a sketch). Without it toBcf makes the old copy. */
  raise: ((setId: string, o?: { topic?: string }) => Promise<string>) | null = null;
  /** src/issues sets this: another sketch the live view draws next to the active one (the sketch of the applied issue viewpoint). */
  companion: (() => MarkupSet | null) | null = null;
  /**
   * src/issues sets this: the 3D · Plan · Section switch of a sketch that is tied to a 3D construct (src/issues/derivedSwitch.ts).
   * The drawing toolbar shows it for the active sketch when `tied` is true; `key` changes when it must be drawn again.
   */
  viewSwitch: {
    tied(set: MarkupSet | null | undefined): boolean;
    mode(set: MarkupSet | null | undefined): 'plan' | 'section' | '3d';
    key(set: MarkupSet | null | undefined): string;
    apply(setId: string, mode: 'plan' | 'section' | '3d'): boolean;
  } | null = null;
  /** src/sheets sets this: a PDF that carries no markup data of ours is a drawing sheet; this opens it as sheets. */
  openPdfSheets: ((file: File | Blob, bytes: Uint8Array) => Promise<ImportReport>) | null = null;
  /** src/sheets sets this: a sketch drawn on a PDF sheet has no 3D view to restore; this opens the sheet instead. True when it did. */
  sheetRestore: ((set: MarkupSet) => boolean) | null = null;
  /** src/issues sets this: restoring a sketch made from an imported viewpoint applies that viewpoint. True when it did. */
  viewpointRestore: ((set: MarkupSet) => boolean) | null = null;
  private readonly removedListeners = new Set<(set: MarkupSet) => void>();
  private readonly viewListeners = new Set<(set: MarkupSet) => void>();
  /** A sketch was removed from the session (its issue link, if any, is cut by src/issues). */
  onRemoved(cb: (set: MarkupSet) => void): () => void {
    this.removedListeners.add(cb);
    return () => this.removedListeners.delete(cb);
  }
  /** The view of a sketch was captured again (Update view): its issue viewpoint is captured again with it. */
  onViewUpdated(cb: (set: MarkupSet) => void): () => void {
    this.viewListeners.add(cb);
    return () => this.viewListeners.delete(cb);
  }
  private readonly histories = new Map<string, History<SetState>>();
  private readonly listeners = new Set<(quiet: boolean) => void>();
  readonly geo: BcfController;
  /** Sets of another model that the user opened on purpose: shown until the model changes. */
  private readonly peeked = new Set<string>();
  /** Throttled "behind other geometry" test for the live view (the PDF and snapshots test directly). */
  readonly behindCache = new OcclusionCache(
    (p) => this.geo.occluded(p),
    () => {
      const e = this.app.renderer.camera.matrixWorld.elements;
      return `${e[12]!.toFixed(3)},${e[13]!.toFixed(3)},${e[14]!.toFixed(3)},${e[0]!.toFixed(4)},${e[2]!.toFixed(4)},${e[6]!.toFixed(4)}|${this.app.controller.settings.overrides.userHides.size}`;
    },
    () => this.emit(true),
  );

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

  /** The active set. A set of another model is never active (nothing of it is drawn) unless it was opened on purpose. */
  get active(): MarkupSet | null {
    const s = this.sets.find((x) => x.id === this.activeId) ?? null;
    return s && this.inScope(s) ? s : null;
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
    if (t !== 'select') {
      this.selected = null;
      if (this.active) this.editing = true; // choosing a drawing tool starts editing the active sketch
    }
    this.emit();
  }
  /** Start or stop editing the active sketch (the drawing toolbar). Stopping also puts the pointer back to select. */
  setEditing(on: boolean): void {
    if (on && !this.active) return;
    if (!on && this.tool !== 'select') {
      this.cancelDrawing?.();
      this.tool = 'select';
    }
    this.editing = on;
    if (!on) this.pickLink = null;
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
    return loadedIdentity(this.app as never) ?? modelIdentity(this.app.modelName, 0, []);
  }

  // ---------------------------------------------------------------- which model a set belongs to (scope.ts)

  /** The scope of a set against the loaded model: same, revised (flagged), unknown (tagged) or another model (hidden). */
  scopeOf(set: MarkupSet): ScopeInfo {
    return scopeOf(set.model, this.loaded ? this.modelIdentity() : null);
  }
  /** True when the set is listed and drawn now: its model matches, is a revision, is unknown, or it was opened on purpose. */
  inScope(set: MarkupSet): boolean {
    return this.scopeOf(set).visible || this.peeked.has(set.id);
  }
  /** The sets of the loaded model (same, revised, unknown) and those opened on purpose, with their scope. */
  visibleSets(): Array<{ set: MarkupSet; scope: ScopeInfo }> {
    return splitByScope(this.sets, (s) => s.model, this.loaded ? this.modelIdentity() : null, (s) => this.peeked.has(s.id)).here.map((h) => ({ set: h.item, scope: h.scope }));
  }
  /** The sets of other models, grouped per model: hidden, nothing of them is drawn. */
  otherModels(): Array<OtherGroup<MarkupSet>> {
    return splitByScope(this.sets, (s) => s.model, this.loaded ? this.modelIdentity() : null, (s) => this.peeked.has(s.id)).other;
  }
  /** Number of sets of other models. */
  get otherCount(): number {
    return this.otherModels().reduce((n, g) => n + g.items.length, 0);
  }
  /** Open a set of another model on purpose: it becomes the active set (until the model changes). Its view is not restored. */
  openOther(id: string): boolean {
    const set = this.get(id);
    if (!set) return false;
    this.cancelDrawing?.();
    this.peeked.add(id);
    this.activeId = id;
    this.selected = null;
    this.setStatus(`"${set.title}" was made on ${set.model ? `"${set.model.name}"` : 'another model'}; its markups may not fit this model. Move to this model to re-attach them`);
    return true;
  }
  /**
   * Re-bind a set to the loaded model and run the attachment migration again: shapes without an attachment (older files) are
   * projected onto this model; targets this model lacks show detached (view-locked). Returns the counts.
   */
  moveToModel(id: string): { migrated: number; attached: number; detached: number } | null {
    const set = this.get(id);
    if (!set || !this.loaded) return null;
    set.model = { ...this.modelIdentity() };
    this.peeked.delete(id);
    this.geo.resolver.reset();
    const r = this.migrateSet(set);
    set.updated = nowIso();
    const detached = set.markups.filter((m) => this.describe(m, set).detached).length;
    this.setStatus(`"${set.title}" now belongs to ${modelLabel(set.model)}${detached ? `; ${detached} markup${detached === 1 ? '' : 's'} could not attach and show${detached === 1 ? 's' : ''} view-locked` : ''}`);
    return { ...r, detached };
  }
  hasGuid(g: string): boolean {
    return this.app.controller.model.byGlobalId.has(g);
  }

  onModel(): void {
    // Sets belong to the model they were made on. The ones of another model stay in the session but are hidden: not active, not
    // drawn, listed under "Other models". Nothing opened on purpose carries over.
    this.peeked.clear();
    this.tinted = null;
    this.geo.resolver.reset();
    this.behindCache.clear();
    this.cancelDrawing?.();
    this.pickLink = null;
    this.attachMenuOpen = null;
    const cur = this.sets.find((s) => s.id === this.activeId);
    if (!cur || !this.inScope(cur)) {
      this.activeId = null;
      this.selected = null;
    } else if (this.selected && !cur.markups.some((m) => m.id === this.selected)) this.selected = null;
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

  /** Add a finished set made elsewhere (a sheet sketch, src/sheets) to the session, with its own undo history. */
  adoptSet(set: MarkupSet, o: { activate?: boolean } = {}): MarkupSet {
    this.sets.push(set);
    if (!this.histories.has(set.id)) this.histories.set(set.id, new History());
    if (o.activate) { this.activeId = set.id; this.selected = null; }
    this.emit();
    return set;
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
      view, camera: this.liveCamera(), markups: [], nextNumber: 1, model: { ...this.modelIdentity() },
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
    if (isSheetSet(set)) {
      this.activeId = set.id;
      this.selected = null;
      const ok = this.sheetRestore?.(set) ?? false;
      this.setStatus(ok ? `Sheet of "${set.title}" opened` : `"${set.title}" is drawn on a PDF sheet, which is not open`);
      return { name: set.title, missing: [], skipped: [], applied: ok ? ['sheet'] : [] };
    }
    if (!this.loaded) throw new Error('No model loaded');
    this.untint();
    if (set.fromViewpoint && this.viewpointRestore?.(set)) {
      this.activeId = set.id;
      this.syncTint();
      this.setStatus(`View of "${set.title}" restored`);
      return { name: set.title, missing: [], skipped: [], applied: ['viewpoint'] };
    }
    const r = this.views.restoreView(set.view, { animate });
    this.activeId = set.id;
    this.syncTint();
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
      this.editing = false;
      this.tool = 'select';
    }
    for (const l of this.removedListeners) l(gone!);
    this.setStatus(`Sketch "${gone!.title}" deleted`);
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
    if (isSheetSet(set)) throw new Error('A sketch on a PDF sheet has no 3D view to update');
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
      if (keep === 'screen') { kept++; m.attach = { kind: 'none' }; continue; }
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
    for (const l of this.viewListeners) l(set);
    return { shapes, moved, kept };
  }

  /** Record the state before a change of the set (undo goes back to it). */
  record(set: MarkupSet): void {
    this.history(set).record(this.stateOf(set));
  }

  undo(): boolean {
    const set = this.active;
    if (!set || set.readonly) return false;
    const prev = this.history(set).undo(this.stateOf(set));
    if (!prev) return false;
    this.applyState(set, prev);
    set.updated = nowIso();
    if (this.selected && !set.markups.some((m) => m.id === this.selected)) this.selected = null;
    this.syncTint();
    this.setStatus('Undone');
    return true;
  }
  redo(): boolean {
    const set = this.active;
    if (!set || set.readonly) return false;
    const next = this.history(set).redo(this.stateOf(set));
    if (!next) return false;
    this.applyState(set, next);
    set.updated = nowIso();
    if (this.selected && !set.markups.some((m) => m.id === this.selected)) this.selected = null;
    this.syncTint();
    this.setStatus('Redone');
    return true;
  }

  /** Add a finished markup to the active set (numbered, undoable, selected). */
  add(m: Markup, set: MarkupSet | null = this.active): Markup {
    if (!set) throw new Error('No markup set: create one from the view first');
    if (set.readonly) throw new Error(`"${set.title}" is read-only (annotations that were already in the PDF). Copy it to an editable sketch first.`);
    if (needsAttach(m)) this.migrateMarkup(m, set);
    this.record(set);
    addMarkup(set, m);
    this.selected = m.id;
    this.syncTint();
    this.setStatus(`${KIND_LABEL[m.kind]} ${m.number} added`);
    return m;
  }

  /** Change fields of a markup. `quiet`: no history entry for this keystroke, a redraw only. */
  patch(id: string, p: Partial<Pick<Markup, 'text' | 'colour' | 'weight' | 'fill' | 'status' | 'assignee' | 'due' | 'offset' | 'shape'>>, o: { quiet?: boolean; noHistory?: boolean } = {}): boolean {
    const f = this.markup(id);
    if (!f || f.set.readonly) return false;
    if (!o.quiet && !o.noHistory) this.record(f.set);
    const m = f.m;
    if (p.text !== undefined) m.text = p.text;
    if (p.colour) m.colour = p.colour;
    if (p.weight) m.weight = p.weight;
    if (p.fill !== undefined) m.fill = p.fill;
    // status, assignee and due are review data: sketches no longer take them (they belong to an issue). Old values stay as read.
    if (p.offset) m.offset = [p.offset[0], p.offset[1]];
    if (p.shape) m.shape = p.shape;
    m.modified = nowIso();
    f.set.updated = m.modified;
    this.emit(o.quiet === true);
    return true;
  }

  remove(id: string): boolean {
    const f = this.markup(id);
    if (!f || f.set.readonly) return false;
    this.record(f.set);
    f.set.markups = f.set.markups.filter((m) => m.id !== id);
    f.set.updated = nowIso();
    if (this.selected === id) { this.selected = null; this.syncTint(); }
    this.setStatus(`${KIND_LABEL[f.m.kind]} ${f.m.number} deleted`);
    return true;
  }

  selectMarkup(id: string | null): void {
    this.selected = id;
    this.syncTint();
    this.emit();
  }

  /** Sketches have no comment threads: comments belong to an issue (raise the sketch as an issue). Always false. */
  comment(_id: string, _text: string): boolean {
    this.setStatus('Sketches have no comments. Raise the sketch as an issue to discuss it.');
    return false;
  }

  /** The one-line note of a sketch. */
  setNote(id: string, note: string, o: { quiet?: boolean } = {}): boolean {
    const set = this.get(id);
    if (!set) return false;
    const t = note.replace(/\s+/g, ' ').trim().slice(0, 400);
    if (t) set.note = t;
    else delete set.note;
    set.updated = nowIso();
    this.emit(o.quiet === true);
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
    const attach = this.inferScreen(kind, pts);
    const m = newMarkup(kind, {
      author: this.who, colour: style.colour ?? this.colour(tool), weight: style.weight ?? this.weight, fill: style.fill ?? this.fill, shape: sh,
      attach, ...(style.text ? { text: style.text } : {}),
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

  // ---------------------------------------------------------------- attachments (src/bcf/attach.ts)

  /** A measurement or penetration under the shape, from the screen (live camera). */
  private hintFor(path: ReadonlyArray<number>, closed: boolean, W: number, H: number) {
    const ctx = this.layoutContext(this.active!, W, H);
    const pen = window.__xrayPenetrations?.rows ?? [];
    return findHint(path, closed, {
      project: ctx.project, measurements: this.measurements(), measureLink: (m) => this.geo.measureLink(m),
      penetrations: pen.map((r) => ({ location: r.location, mep: r.mep, host: r.host })), guidOfId: (id) => this.geo.guidOfId(id),
    });
  }

  /** What a shape just drawn on the screen is attached to: the inference of src/bcf/surface.ts from the live camera. */
  private inferScreen(kind: MarkupKind, screen: ReadonlyArray<readonly [number, number]>): Attachment {
    try {
      const { W, H } = this.canvasSize();
      const inp = screenInput(this.geo, kind, screen, W, H, this.app.renderer.camera);
      const hint = this.hintFor(inp.path, inp.closed, W, H);
      const r = inferAttachment(hint ? { ...inp, hint } : inp);
      return r.attach;
    } catch {
      return { kind: 'none' };
    }
  }

  /** The same inference for a stored shape, from the rays of its set camera through its fractions. */
  private inferStored(m: Markup, set: MarkupSet): Attachment {
    if (!m.shape || !this.loaded) return { kind: 'none' };
    try {
      const { W, H } = this.canvasSize();
      const inp = fractionInput(this.geo, m.kind, m.shape.points, set.camera, W, H);
      const hint = this.hintFor(inp.path, inp.closed, W, H);
      return inferAttachment(hint ? { ...inp, hint } : inp).attach;
    } catch {
      return { kind: 'none' };
    }
  }

  /** Migration of a shape from a document made before attachments: attached when it projects cleanly, else view-locked. */
  migrateMarkup(m: Markup, set: MarkupSet): void {
    if (!m.shape) return;
    m.attach = this.inferStored(m, set);
  }

  /** Migrate every old shape of a set (no `attach`); returns how many ended up attached. */
  migrateSet(set: MarkupSet, o: { keepLocked?: boolean } = {}): { migrated: number; attached: number } {
    let migrated = 0;
    let attached = 0;
    for (const m of set.markups) {
      if (!needsAttach(m)) continue;
      migrated++;
      if (o.keepLocked) m.attach = { kind: 'none' };
      else this.migrateMarkup(m, set);
      if (m.attach && m.attach.kind !== 'none') attached++;
    }
    return { migrated, attached };
  }

  /** The surface data to draw for a set's outline: re-projected onto reshaped elements, null when it cannot land (detached). Cached per model load. */
  resolveSurface(s: SurfaceData, set?: MarkupSet): SurfaceData | null {
    const o: ResolveOptions = { revised: !!set && this.scopeOf(set).match === 'revised' };
    if (set) o.fallbackDir = set.camera.direction;
    return this.geo.resolver.resolve(s, o);
  }

  /** The words of the chip of a markup. `set`: the set it is in (found when absent). */
  describe(m: Markup, set?: MarkupSet): AttachDescription {
    const att = attachmentOf(m);
    const missing = this.loaded ? attachGuids(att).filter((g) => !this.hasGuid(g)) : [];
    const owner = set ?? this.sets.find((s) => s.markups.includes(m));
    const lost = this.loaded && missing.length === 0 && !!att.surface && isSpatial(att) && this.resolveSurface(att.surface, owner) === null;
    return describeAttachment(att, { classOf: (g) => this.geo.classOf(g), missing, surfaceLost: lost, revised: !!owner && this.scopeOf(owner).match === 'revised' });
  }

  /** True when an attached markup lost an element or its surface: it shows view-locked and the panel says "detached". */
  detached(m: Markup, set?: MarkupSet): boolean {
    return this.describe(m, set).detached;
  }

  /**
   * Change what a shape is attached to (undoable). `how`: `none` view-locked; `elements` the current selection;
   * `surface` and `region` project the stored shape again from its set camera; `measurement` and `penetration` take their link.
   * Returns false, with a status line, when it cannot be done.
   */
  setAttachment(id: string, how: 'none' | 'elements' | 'surface' | 'region' | 'measurement' | 'penetration', link?: { measurement?: NonNullable<Attachment['measurement']>; penetration?: NonNullable<Attachment['penetration']> }): boolean {
    const f = this.markup(id);
    if (!f?.m.shape) { this.setStatus('Only shapes can change their attachment'); return false; }
    const { set, m } = f;
    const fail = (t: string): false => { this.setStatus(t); return false; };
    let att: Attachment | null = null;
    if (how === 'none') att = { kind: 'none' };
    else {
      if (!this.loaded) return fail('No model loaded');
      const { W, H } = this.canvasSize();
      const inp = fractionInput(this.geo, m.kind, f.m.shape.points, set.camera, W, H);
      if (how === 'surface') att = projectSurface(inp);
      else if (how === 'region') att = projectRegion(inp);
      else if (how === 'elements') {
        const guids = this.app.selection.map((i) => this.geo.guidOfId(i)).filter((g): g is string => !!g);
        if (!guids.length) return fail('Select the elements in the model first, then choose Elements');
        att = { kind: 'elements', guids };
        const sd = projectSurfaceData(inp);
        if (sd) att.surface = sd;
      } else if (how === 'measurement' || how === 'penetration') {
        const l = link?.[how];
        if (!l) return fail(`No ${how} to attach to`);
        att = how === 'measurement' ? { kind: 'measurement', measurement: l as NonNullable<Attachment['measurement']> } : { kind: 'penetration', penetration: l as NonNullable<Attachment['penetration']> };
        const sd = projectSurfaceData(inp);
        if (sd) att.surface = sd;
      }
      if (!att) return fail(how === 'region' ? 'Nothing under the outline to fit a region to' : 'The outline does not project cleanly onto the model surfaces');
    }
    this.record(set);
    m.attach = att;
    m.modified = nowIso();
    set.updated = m.modified;
    this.syncTint();
    this.setStatus(`${markupName(m)}: ${describeAttachment(att, { classOf: (g) => this.geo.classOf(g) }).text}`);
    return true;
  }

  toggleAttachMenu(id: string): void {
    this.attachMenuOpen = this.attachMenuOpen === id ? null : id;
    this.emit();
  }

  /** A choice of the Change menu. Measurement and Penetration wait for a click on the link in the view. */
  chooseAttachment(id: string, how: 'none' | 'elements' | 'surface' | 'region' | 'measurement' | 'penetration'): void {
    this.attachMenuOpen = null;
    this.pickLink = null;
    if (how === 'measurement' || how === 'penetration') {
      this.pickLink = { id, kind: how };
      this.setStatus(how === 'measurement' ? 'Click a dimension line of the measure tool in the view (Esc cancels)' : 'Click a penetration marker in the view (Esc cancels)');
      return;
    }
    this.setAttachment(id, how);
    this.emit();
  }

  /** The measurement or penetration nearest to a canvas point (20 px at most), as a link. */
  linkAt(kind: 'measurement' | 'penetration', x: number, y: number): { measurement?: NonNullable<Attachment['measurement']>; penetration?: NonNullable<Attachment['penetration']> } | null {
    const { W, H } = this.canvasSize();
    const ctx = this.layoutContext(this.active!, W, H);
    let best = 20;
    let out: ReturnType<MarkupController['linkAt']> = null;
    if (kind === 'measurement') {
      for (const m of this.measurements()) {
        const a = ctx.project(m.a as unknown as Vec3);
        const b = ctx.project(m.b as unknown as Vec3);
        if (!a.front || !b.front) continue;
        const d = ptsDist(x, y, a.x, a.y, b.x, b.y);
        if (d < best) { best = d; out = { measurement: this.geo.measureLink(m) }; }
      }
    } else {
      for (const r of window.__xrayPenetrations?.rows ?? []) {
        const p = ctx.project(r.location);
        const mep = this.geo.guidOfId(r.mep);
        const host = this.geo.guidOfId(r.host);
        if (!p.front || !mep || !host) continue;
        const d = Math.hypot(p.x - x, p.y - y);
        if (d < best) { best = d; out = { penetration: { mep, host } }; }
      }
    }
    return out;
  }

  /** After a shape was moved: attached shapes are projected again at their new place (no history entry of their own). */
  reattach(id: string): void {
    const f = this.markup(id);
    if (!f?.m.shape || !isSpatial(f.m.attach)) return;
    f.m.attach = this.inferStored(f.m, f.set);
    this.syncTint();
    this.emit(true);
  }

  // ---------------------------------------------------------------- display: view lock, target highlight

  /** The view-lock state of the live camera against the active set's camera (src/bcf/attach.ts viewLockState). */
  lockState(set: MarkupSet | null = this.active): LockState | undefined {
    if (!set || !this.loaded) return undefined;
    const cam = this.app.renderer.camera;
    cam.updateMatrixWorld();
    const f = cam.getWorldDirection(cam.position.clone());
    const sh = this.shift;
    return viewLockState(
      { position: [cam.position.x, cam.position.y, cam.position.z], direction: [f.x, f.y, f.z] },
      { position: ifcToViewer(set.camera.position, sh), direction: dirIfcToViewer(set.camera.direction) },
      this.geo.sceneScale(ifcToViewer(set.camera.position, sh)), this.viewLocked3d,
    );
  }

  setViewLocked3d(v: string): void {
    if ((VIEWLOCK_MODES as readonly string[]).includes(v)) this.viewLocked3d = v as ViewLockMode;
    this.emit(true);
  }

  private tinted: Map<number, [number, number, number]> | null = null;

  /** Put the colours back (before a view is restored: it sets its own). */
  untint(): void {
    const r = this.app.loaded ? this.app.renderer : null;
    if (this.tinted && r) {
      const color = r.state.color;
      for (const [id, c] of this.tinted) { color[id * 3] = c[0]; color[id * 3 + 1] = c[1]; color[id * 3 + 2] = c[2]; }
    }
    this.tinted = null;
  }

  /** Give the elements an attached selected markup points at the selection tint of the viewer; restore the others. */
  syncTint(): void {
    const r = this.app.loaded ? this.app.renderer : null;
    this.untint();
    const sel = this.selected ? this.markup(this.selected) : null;
    if (!r || !sel || !sel.m.shape || !isSpatial(sel.m.attach)) { r?.markDirty(); return; }
    const color = r.state.color;
    const saved = new Map<number, [number, number, number]>();
    for (const g of attachGuids(sel.m.attach)) {
      const id = this.app.controller.model.byGlobalId.get(g);
      if (id === undefined || id * 3 + 2 >= color.length) continue;
      saved.set(id, [color[id * 3]!, color[id * 3 + 1]!, color[id * 3 + 2]!]);
      const T = [1, 0.85, 0.2];
      for (let k = 0; k < 3; k++) color[id * 3 + k] = color[id * 3 + k]! + (T[k]! - color[id * 3 + k]!) * 0.5;
    }
    this.tinted = saved;
    r.markDirty();
  }

  // ---------------------------------------------------------------- view of the camera against the set

  /** True when the live camera is away from the active set's view. */
  away(of: MarkupSet | null = this.active): boolean {
    const set = of;
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
      hidden: (g) => this.geo.elementHidden(g),
      shapeView: set.camera,
      resolveSurface: (s) => this.resolveSurface(s, set),
      ...extra,
    };
  }

  // ---------------------------------------------------------------- export

  /** Wait for the ghost animation and the classification to settle after a restore. */
  async settleView(): Promise<void> {
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
    // Default: the sets of the loaded model; the ones of other models are listed apart and are not exported unless asked for by id.
    return ids ? ids.map((i) => this.get(i)).filter((s): s is MarkupSet => !!s) : this.sets.filter((s) => this.inScope(s));
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
    // Each set says which model it was made on. Sets of this model, a revision or no model are shown; sets of another model are
    // kept, hidden, under "Other models" (open them there, or Move to this model).
    const now = this.modelIdentity();
    const matches = p.sets.map((s) => compareModels(s.model ?? undefined, now));
    const rank: Record<ModelMatch, number> = { same: 0, unknown: 1, revised: 2, different: 3 };
    const match = matches.reduce<ModelMatch>((w, m) => (rank[m.match] > rank[w] ? m.match : w), 'same');
    const warnings: string[] = [];
    for (const msg of new Set(matches.map((m) => m.message).filter(Boolean))) warnings.push(msg);
    const hidden = p.sets.filter((_s, i) => matches[i]!.match === 'different');
    if (hidden.length) warnings.push(`${hidden.length === 1 ? 'This set is' : `These ${hidden.length} sets are`} listed under Other models and not drawn on this model. Open ${hidden.length === 1 ? 'it' : 'them'} there, or Move to this model.`);
    if (matches.some((m) => m.match === 'unknown')) warnings.push('The file does not name its model; the markup is shown on this one, tagged model unknown.');
    const shown = p.sets.filter((_s, i) => matches[i]!.match !== 'different');
    const unknown = new Set<string>();
    for (const s of p.sets) for (const g of referencedGuids(s)) if (!this.hasGuid(g)) unknown.add(g);
    if (unknown.size && shown.length) warnings.push(`${unknown.size} element${unknown.size === 1 ? '' : 's'} named in the markup ${unknown.size === 1 ? 'is' : 'are'} not in this model; their markups and view parts are left out or stay where they were drawn.`);
    if (p.bad.length) warnings.push(`${p.bad.length} item${p.bad.length === 1 ? '' : 's'} in the file could not be read.`);
    // Shapes from a document made before attachments: attached when they project cleanly on this model, else view-locked.
    // (Sets of another model are migrated when they are moved to this model.)
    let migrated = 0;
    let nowAttached = 0;
    for (const set of shown) {
      if (isSheetSet(set)) continue;
      const r = this.migrateSet(set);
      migrated += r.migrated;
      nowAttached += r.attached;
    }
    if (migrated) warnings.push(`${nowAttached} of ${migrated} older shape${migrated === 1 ? '' : 's'} could be attached to the model; the others stay view-locked.`);
    const merged = mergeSets(this.sets, p.sets);
    this.sets = merged.sets;
    this.geo.resolver.reset();
    for (const s of p.sets) if (!this.histories.has(s.id)) this.histories.set(s.id, new History());
    const rep: ImportReport = {
      ok: true, sets: p.sets.length, markups: p.sets.reduce((a, s) => a + s.markups.length, 0), added: merged.added, replaced: merged.replaced,
      unknownGuids: unknown.size, match, warnings, skipped: p.bad,
    };
    const first = shown.find((x) => !isSheetSet(x));
    if (o.restore !== false && first) {
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
      if (!hit && this.openPdfSheets) return this.openPdfSheets(file, bytes);
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
    if (this.raise) return this.raise(setId);
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
          if ((m.kind === 'rect' || m.kind === 'highlightBox') && m.shape.points.length === 2) bcf.addShape(topic.guid, 'rect', [[px[0]!, px[1]!], [px[4]!, px[5]!]], label, m.attach);
          else {
            const pts: Array<[number, number]> = [];
            for (let i = 0; i < px.length; i += 2) pts.push([px[i]!, px[i + 1]!]);
            bcf.addShape(topic.guid, 'freehand', pts, label, m.attach);
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

  /** The sets of the loaded model (same, revised, unknown), with their scope. `all`: also the sets of other models. */
  list(o: { all?: boolean } = {}): Array<{ id: string; title: string; markups: number; open: number; resolved: number; active: boolean; scope: ModelMatch; model: string }> {
    const sets = o.all ? this.sets : this.sets.filter((s) => this.inScope(s));
    return sets.map((s) => ({ id: s.id, title: s.title, ...setCounts(s), markups: s.markups.length, active: s.id === this.activeId && this.inScope(s), scope: this.scopeOf(s).match, model: s.model?.name ?? '' }));
  }
}


function ptsDist(x: number, y: number, ax: number, ay: number, bx: number, by: number): number {
  const dx = bx - ax, dy = by - ay;
  const l2 = dx * dx + dy * dy;
  const t = l2 > 0 ? Math.max(0, Math.min(1, ((x - ax) * dx + (y - ay) * dy) / l2)) : 0;
  return Math.hypot(x - (ax + t * dx), y - (ay + t * dy));
}
