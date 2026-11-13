// BCF controller: holds the loaded / authored BCF project and applies viewpoints to the viewer.
//
// Provenance: a viewpoint hides elements through settings.overrides.userHides, remembering which ids it added itself
// (CleanupHides). `clearViewpoint` removes only those, so elements the user hid by hand stay hidden. Colours are temporary
// renderer.state.color overrides restored on clear; clipping goes through renderer.setClipPlanes when the renderer has it.

import type { ViewerApp } from '../app';
import { CleanupHides } from '../cleanup/hides';
import { parseBcf } from './parse';
import { writeBcf } from './write';
import { boxAround, captureViewpoint, frameCamera, planViewpoint, topicGlobalIds, unionBox, visibilityHides } from './plan';
import type { Box6, PlanCamera, ViewpointPlan } from './plan';
import { dirViewerToIfc, emptyProject, ifcToViewer, newGuid, nowIso, toIfcGuid, viewerToIfc } from './model';
import type { BcfAnnotation, BcfAnnotationType, BcfComment, BcfMeasureLink, BcfProject, BcfShapeType, BcfSnapshotView, BcfTopic, BcfVersion, BcfViewpointRef, Vec3 } from './model';
import { defaultOffset, drawOps, layoutSnapshot, shapeFraction, shapePointWorld, snapshotCamera, snapshotProjector, snapshotScale } from './annotate';
import type { Ctx2D, LayoutContext } from './annotate';
import type { ProbeHit, Ray3 } from './surface';
import { cloneAttachment as cloneAttach, occlusionWorld, viewLockSetting, viewLockState } from './attach';
import type { Attachment, LockState } from './attach';
import { dirIfcToViewer } from './model';
import { fractionInput, inferAttachment, screenInput } from '../markup/attachScene';
import type { BcfMarkupView } from './pins';
import { loadedIdentity, scopeOf, splitByScope } from '../markup/scope';
import type { ModelIdentity, OtherGroup, ScopeInfo } from '../markup/scope';
import { SurfaceResolver } from '../markup/reprojectScene';
import type { ResolveOptions } from '../markup/reprojectScene';
import type { SurfaceData } from './attach';
import { annotationGuids, cloneAnnotation, markupSelectionOf, needsBurn } from './sidecar';
import { cameraRay, firstSurfaceHit } from '../measure/geometry';
import { currentMeasureUnits } from '../measure/current';
import { formatLength } from '../measure/maths';
import type { Measurement } from '../measure/maths';
import { Ray, Vector3 } from 'three';
import { castClipped, clipInterval, keptPoint, unitPlanes } from './clipRay';
import type { ClipCast, Plane, RangeProbe } from './clipRay';

type PlaneLike = { normal: Vec3 | { x: number; y: number; z: number }; point: Vec3 | { x: number; y: number; z: number } };
interface ClipApi {
  setClipPlanes?(planes: Array<{ normal: Vec3; point: Vec3 }> | null, opts?: { cap?: boolean }): void;
  getClipPlanes?(): PlaneLike[] | null | undefined;
  /** Bumped by every setClipPlanes (renderer.ts); lets clear leave planes alone that someone set after us. */
  clipVersion?: number;
  /** Section caps are painted now (renderer.ts). */
  clipCapsDrawn?: boolean;
  /** A view mode (behind cut, peel) may cut surface hits away; viewModeCut says whether it does for a hit. */
  viewModeCuts?: boolean;
  viewModeCut?(id: number, point: Vector3): boolean;
  /** Per-element closed-solid flags (1 = closed): section caps are painted for these only. */
  closedFlags?: Uint8Array;
}

const v3 = (v: Vec3 | { x: number; y: number; z: number }): Vec3 => (Array.isArray(v) ? [v[0], v[1], v[2]] : [(v as { x: number }).x, (v as { y: number }).y, (v as { z: number }).z]);

export interface ApplyReport {
  ok: boolean;
  applied: string[];
  skipped: string[];
  /** Unknown GlobalIds, summed over selection, visibility and coloring. */
  unknownGuids: number;
  status: string;
}

export interface CreateTopicOptions {
  title: string;
  description?: string;
  type?: string;
  status?: string;
  priority?: string;
  labels?: string[];
  assignedTo?: string;
  author?: string;
  dueDate?: string;
  /** Capture a PNG snapshot (default true). */
  snapshot?: boolean;
  /** Attach the viewpoint (default true). */
  viewpoint?: boolean;
  /** Build the viewpoint around these GlobalIds (selected and framed) instead of the current view. */
  globalIds?: string[];
  /** Camera in viewer coordinates for the viewpoint. */
  camera?: { position: Vec3; target: Vec3 };
  /**
   * Pin point in viewer coordinates. Default: the centre of the bounds of `globalIds` (or of the selection), else the
   * surface point in the middle of the view. null: no pin.
   */
  pin?: Vec3 | null;
  /** GlobalId of the element under the pin. */
  pinElement?: string;
}

/** An annotation to add; points in viewer coordinates. */
export interface AnnotationSpec {
  type: Exclude<BcfAnnotationType, BcfShapeType>;
  text?: string;
  anchor: { kind: 'element' | 'point'; point: Vec3; elementGuid?: string } | { kind: 'measurement'; measurement: Measurement };
  /** Text box offset, fractions of the view height (default per type). */
  offset?: [number, number];
}

export interface TopicSpec {
  title: string;
  description?: string;
  /** Elements by GlobalId; `elements` is an alias, and `elementIds` (viewer ids) is the fallback. */
  globalIds?: string[];
  elements?: string[];
  elementIds?: number[];
  /** Viewer-frame point to frame together with the elements. */
  location?: Vec3;
  /** IFC project coordinates of the same point (informational). */
  ifcLocation?: Vec3;
  camera?: { position: Vec3; target: Vec3 };
  labels?: string[];
  type?: string;
  status?: string;
  priority?: string;
  assignedTo?: string;
}

/** Elements drawn below this alpha are see-through: picking passes them first and they hide no pin. */
const GHOST_ALPHA = 0.5;
/** The selection tint of the shaders (shaders.ts surfaceColour): annotated elements that are not selected get it as a colour. */
const SELECT_TINT: [number, number, number] = [1, 0.85, 0.2];
const SELECT_MIX = 0.35;

export const DEFAULT_TYPES = ['Issue', 'Clash', 'Request', 'Remark', 'Fault', 'Inquiry'];
export const DEFAULT_STATUSES = ['Open', 'In Progress', 'Resolved', 'Closed'];
export const DEFAULT_PRIORITIES = ['Low', 'Normal', 'High', 'Critical'];

function storage(): Storage | null {
  try {
    const s = window.localStorage;
    s.getItem('xray.probe');
    return s;
  } catch {
    return null;
  }
}

function dataUrlToBytes(url: string): Uint8Array | null {
  const i = url.indexOf(',');
  if (i < 0 || !url.startsWith('data:image/png')) return null;
  const bin = atob(url.slice(i + 1));
  const out = new Uint8Array(bin.length);
  for (let k = 0; k < bin.length; k++) out[k] = bin.charCodeAt(k);
  return out;
}

/** Selecting can start the cinematic plugin's fly-to; a BCF camera (or a restored camera) must win, so cancel it (if present). */
function cancelFly(): void {
  const c = (window as unknown as { __cinematic?: { cancelFlight?: () => void } }).__cinematic;
  if (typeof c?.cancelFlight === 'function') c.cancelFlight();
}

export class BcfController {
  project: BcfProject = emptyProject('2.1');
  selectedTopic: string | null = null;
  status = 'No BCF loaded';
  author = '';
  exportVersion: BcfVersion = '2.1';
  /** Unsaved authored changes (Open BCF then merges instead of replacing). */
  dirty = false;
  /** The viewpoint currently applied, if any. */
  applied: { topic: string; viewpoint: string } | null = null;
  private readonly listeners = new Set<() => void>();
  private readonly hides = new CleanupHides();
  private savedColors: Map<number, [number, number, number]> | null = null;
  private clipOwned = false;
  private clipVersion: number | undefined = undefined;
  private boundsFor: object | null = null;
  private bounds: Box6 | null = null;
  private lastPrune = 0;
  /** Show topic pins on the model. */
  pinsVisible = true;
  /** Which topics show a pin (the drawer sets its filter); null: all. */
  pinFilter: ((t: BcfTopic) => boolean) | null = null;
  /** Open BCF drawers. Pins show while a drawer is open; with none, only the pin of the topic whose viewpoint is applied. */
  private drawers = 0;
  /** Bumped on every markup change (pins, annotations): views re-render on it. */
  markupRev = 0;
  /**
   * src/issues sets this. A viewpoint whose drawing is a sketch (`sketchId`) takes annotation changes through the sketch:
   * `add` gets the new annotation, `update` a text or offset change, `remove` a deleted one (by annotation guid, which is the
   * markup id). Each returns true when the sketch took the change.
   */
  linked: {
    add(ref: BcfViewpointRef, a: BcfAnnotation): boolean;
    update(ref: BcfViewpointRef, guid: string, patch: { text?: string; offset?: [number, number] }): boolean;
    remove(ref: BcfViewpointRef, guid: string): boolean;
  } | null = null;
  /** Runs before export and before a snapshot is composed: src/issues refreshes the drawings of linked sketches. */
  beforeExport: (() => void) | null = null;
  /** src/issues sets this: the project as exported, with the Plan and Section viewpoints of attached sketches added (not stored). */
  deriveForExport: ((project: BcfProject) => BcfProject) | null = null;
  /** The live markup view (pins.ts), set by it; the topic dialog starts pin placement through it. */
  markup: BcfMarkupView | null = null;
  /** Re-projection of surface outlines onto reshaped elements, cached per model load. */
  readonly resolver: SurfaceResolver;
  /** Topics of another model that the user opened on purpose: shown until the model changes. */
  private readonly peeked = new Set<string>();
  /** What the last file import found about the model of its topics (the drawer warns with it). */
  lastImport: { different: number; revised: number; unknown: number; message: string } | null = null;

  constructor(readonly app: ViewerApp) {
    this.resolver = new SurfaceResolver(app);
    // The occlusion cache of the live view is keyed on the camera: a section or a view mode changes what hides what as well.
    occlusionWorld.stamp = () => { const a = this.clipApi(); return `${a.clipVersion ?? 0}|${a.viewModeCuts ? 1 : 0}`; };
    const s = storage();
    try {
      this.author = s?.getItem('xray.bcf.author') ?? '';
      const v = s?.getItem('xray.bcf.version');
      if (v === '2.1' || v === '3.0') this.exportVersion = v;
    } catch {
      /* ignore */
    }
  }

  // ---------------------------------------------------------------- events and settings

  onChange(cb: () => void): () => void {
    this.listeners.add(cb);
    return () => this.listeners.delete(cb);
  }
  private emit(): void {
    for (const l of this.listeners) l();
  }
  setStatus(t: string): void {
    this.status = t;
    this.emit();
  }
  setAuthor(a: string): void {
    this.author = a.trim();
    try {
      storage()?.setItem('xray.bcf.author', this.author);
    } catch {
      /* ignore */
    }
  }
  setExportVersion(v: BcfVersion): void {
    this.exportVersion = v;
    try {
      storage()?.setItem('xray.bcf.version', v);
    } catch {
      /* ignore */
    }
  }
  /** Every topic of the session, whatever model it belongs to (the live array). The panels use `currentTopics`. */
  get topics(): BcfTopic[] {
    return this.project.topics;
  }
  /** The topics of the loaded model (same, revised or unknown), and those opened on purpose from another model. */
  get currentTopics(): BcfTopic[] {
    return this.project.topics.filter((t) => this.inScope(t));
  }

  // ---------------------------------------------------------------- which model a topic belongs to (markup/scope.ts)

  /** The identity of the loaded model, null while none is loaded. */
  modelIdentity(): ModelIdentity | null {
    return loadedIdentity(this.app as never);
  }
  scopeOf(t: BcfTopic): ScopeInfo {
    return scopeOf(t.model, this.modelIdentity());
  }
  /** True when the topic is listed and drawn now: its model matches, is a revision, is unknown, or it was opened on purpose. */
  inScope(t: BcfTopic): boolean {
    return this.scopeOf(t).visible || this.peeked.has(t.guid);
  }
  /** The topics of other models, grouped per model (hidden: no pin, no annotation, no viewpoint is drawn). */
  otherModels(): Array<OtherGroup<BcfTopic>> {
    return splitByScope(this.project.topics, (t) => t.model, this.modelIdentity(), (t) => this.peeked.has(t.guid)).other;
  }
  /** Open a topic of another model on purpose: it is listed with the current ones and can apply its viewpoint (until the model changes). */
  openOther(guid: string): boolean {
    const t = this.topic(guid);
    if (!t) return false;
    this.peeked.add(guid);
    this.selectedTopic = guid;
    this.markupRev++;
    this.setStatus(`"${t.title}" was made on ${t.model ? `"${t.model.name}"` : 'another model'}; its viewpoint and markup may not fit this model`);
    return true;
  }
  /** Re-bind a topic to the loaded model. Its annotations whose targets are missing show detached (view-locked). */
  moveToModel(guid: string): boolean {
    const t = this.topic(guid);
    const id = this.modelIdentity();
    if (!t || !id) return false;
    t.model = { ...id };
    this.peeked.delete(guid);
    this.resolver.reset();
    this.markupChanged(t);
    let detached = 0;
    for (const r of t.viewpoints) for (const a of r.annotations ?? []) if (this.annotationDetached(a, r, t)) detached++;
    this.setStatus(`"${t.title}" now belongs to this model${detached ? `; ${detached} annotation${detached === 1 ? '' : 's'} could not attach and show view-locked` : ''}`);
    return true;
  }
  /** Delete a topic (any model's). */
  deleteTopic(guid: string): boolean {
    const i = this.project.topics.findIndex((t) => t.guid === guid);
    if (i < 0) return false;
    const [gone] = this.project.topics.splice(i, 1);
    this.peeked.delete(guid);
    if (this.applied?.topic === guid) this.clearViewpoint(true);
    if (this.selectedTopic === guid) this.selectedTopic = null;
    this.dirty = true;
    this.markupRev++;
    this.setStatus(`Topic "${gone!.title}" deleted`);
    return true;
  }

  /** The model a surface outline of `topic` is drawn on: re-projected onto reshaped elements, null when detached. */
  resolveSurface(s: SurfaceData, topic?: BcfTopic, view?: BcfSnapshotView | null): SurfaceData | null {
    const o: ResolveOptions = { revised: !!topic && this.scopeOf(topic).match === 'revised' };
    if (view) o.fallbackDir = view.direction;
    return this.resolver.resolve(s, o);
  }

  /** True when an annotation's surface outline cannot follow the current model: a target is missing or the surface no longer fits. */
  annotationDetached(a: BcfAnnotation, ref?: BcfViewpointRef, topic?: BcfTopic): boolean {
    const att = a.attach;
    if (!att?.surface || !this.app.loaded) return false;
    if (att.surface.guids.some((g) => this.model.byGlobalId.get(g) === undefined)) return true;
    const t = topic ?? this.project.topics.find((x) => x.viewpoints.some((v) => v.annotations?.includes(a)));
    return this.resolveSurface(att.surface, t, ref ? this.shapeView(ref) : null) === null;
  }

  topic(guid: string): BcfTopic | undefined {
    return this.project.topics.find((t) => t.guid === guid);
  }
  select(guid: string | null): void {
    this.selectedTopic = guid;
    this.emit();
  }

  // ---------------------------------------------------------------- model helpers

  private get model() {
    return this.app.controller.model;
  }
  private modelBounds(): Box6 | null {
    const loaded = this.app.loaded;
    if (!loaded) return null;
    if (this.boundsFor !== loaded) {
      this.boundsFor = loaded;
      this.bounds = unionBox(this.model.elements.map((e) => e.bounds as Box6));
    }
    return this.bounds;
  }
  private clipApi(): ClipApi {
    return this.app.renderer as unknown as ClipApi;
  }
  get canClip(): boolean {
    return typeof this.clipApi().setClipPlanes === 'function';
  }
  private elementBounds(ids: number[]): Box6 | null {
    return unionBox(ids.map((i) => this.model.elements[i]!.bounds as Box6));
  }

  boundsOfId(id: number): readonly number[] | null {
    return this.model?.elements[id]?.bounds ?? null;
  }

  onModel(): void {
    // The renderer state, the hide set and the clip planes were replaced with the model.
    this.hides.clear();
    this.savedColors = null;
    this.clipOwned = false;
    this.applied = null;
    this.boundsFor = null;
    // Topics belong to the model they were made on: the ones of another model stay in the session but are hidden (no pin, no
    // annotation, not listed with the current topics). Nothing opened on purpose carries over.
    this.peeked.clear();
    this.resolver.reset();
    const sel = this.selectedTopic ? this.topic(this.selectedTopic) : undefined;
    if (!sel || !this.inScope(sel)) this.selectedTopic = null;
    this.markupRev++;
    this.emit();
  }

  /** Throttled: forget owned hides the user has since undone by hand. */
  tick(now: number): void {
    if (now - this.lastPrune < 250 || this.hides.owned.size === 0) return;
    this.lastPrune = now;
    this.hides.prune(this.app.controller.settings.overrides.userHides);
  }

  // ---------------------------------------------------------------- loading

  async load(src: File | Blob | ArrayBuffer | Uint8Array, opts: { merge?: boolean } = {}): Promise<BcfProject> {
    const bytes = src instanceof Uint8Array ? src : src instanceof ArrayBuffer ? new Uint8Array(src) : new Uint8Array(await src.arrayBuffer());
    let p: BcfProject;
    try {
      p = await parseBcf(bytes);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      this.setStatus(`Could not read BCF: ${msg}`);
      throw e;
    }
    const merge = opts.merge === true;
    this.lastImport = this.importScope(p.topics);
    if (merge) {
      const have = new Set(this.project.topics.map((t) => t.guid));
      for (const t of p.topics) {
        if (have.has(t.guid)) this.project.topics = this.project.topics.filter((x) => x.guid !== t.guid);
        this.project.topics.push(t);
      }
      this.project.warnings.push(...p.warnings);
      for (const k of Object.keys(p.extensions) as Array<keyof typeof p.extensions>) {
        this.project.extensions[k] = [...new Set([...this.project.extensions[k], ...p.extensions[k]])];
      }
    } else {
      this.clearViewpoint(true);
      // Topics of other models are not "the loaded topics": opening a file leaves them in the session (hidden).
      const incoming = new Set(p.topics.map((t) => t.guid));
      const hidden = this.project.topics.filter((t) => !this.inScope(t) && !incoming.has(t.guid));
      this.project = p;
      this.project.topics = [...p.topics, ...hidden];
      this.dirty = false;
      this.selectedTopic = null;
    }
    this.assignPinNumbers();
    const n = p.topics.length;
    const vps = p.topics.reduce((s, t) => s + t.viewpoints.length, 0);
    const warn = this.lastImport?.message ? `. Warning: ${this.lastImport.message}` : '';
    this.setStatus(`BCF ${p.versionId}: ${n} topic${n === 1 ? '' : 's'}, ${vps} viewpoint${vps === 1 ? '' : 's'}${p.warnings.length ? `, ${p.warnings.length} warning${p.warnings.length === 1 ? '' : 's'}` : ''}${warn}`);
    const first = p.topics.find((t) => this.inScope(t));
    if (first && !this.selectedTopic) this.selectedTopic = first.guid;
    this.emit();
    return p;
  }

  /**
   * What a file's topics say about their model, against the loaded one: a warning when some were made on another model (they
   * are listed under "Other models" and not drawn), a revision, or name none (shown, tagged "model unknown").
   */
  private importScope(topics: readonly BcfTopic[]): NonNullable<BcfController['lastImport']> {
    const r = { different: 0, revised: 0, unknown: 0, message: '' };
    if (!this.app.loaded) return r;
    const names = new Set<string>();
    for (const t of topics) {
      const m = this.scopeOf(t).match;
      if (m === 'different') { r.different++; names.add(t.model?.name ?? '?'); }
      else if (m === 'revised') r.revised++;
      else if (m === 'unknown') r.unknown++;
    }
    const words: string[] = [];
    const nt = (n: number): string => `${n} topic${n === 1 ? '' : 's'}`;
    if (r.different) words.push(`${nt(r.different)} ${r.different === 1 ? 'was' : 'were'} made on another model (${[...names].join(', ')}); ${r.different === 1 ? 'it is' : 'they are'} listed under Other models and not drawn here. Open ${r.different === 1 ? 'it' : 'them'} there, or Move to this model.`);
    if (r.revised) words.push(`${nt(r.revised)} ${r.revised === 1 ? 'was' : 'were'} made on an earlier revision of this model; targets that no longer fit are detached.`);
    if (r.unknown) words.push(`${nt(r.unknown)} name${r.unknown === 1 ? 's' : ''} no model and ${r.unknown === 1 ? 'is' : 'are'} shown here, tagged model unknown.`);
    r.message = words.join(' ');
    return r;
  }

  // ---------------------------------------------------------------- viewpoints: apply and clear

  private setCamera(c: PlanCamera): void {
    const r = this.app.renderer;
    const cam = r.camera;
    const ctl = r.controls;
    // A view straight down or up needs its own up vector (a plan keeps north up); every other view keeps Y up.
    const look = [c.target[0] - c.position[0], c.target[1] - c.position[1], c.target[2] - c.position[2]];
    const ll = Math.hypot(look[0]!, look[1]!, look[2]!);
    if (ll > 1e-9 && Math.abs(look[1]!) / ll > 0.999 && Math.hypot(c.up[0], c.up[1], c.up[2]) > 1e-9 && Math.abs(c.up[1]) < 0.01) cam.up.set(c.up[0], c.up[1], c.up[2]);
    else cam.up.set(0, 1, 0);
    cam.position.set(...c.position);
    ctl.target.set(...c.target);
    cam.fov = c.fov;
    const dist = Math.hypot(c.target[0] - c.position[0], c.target[1] - c.position[1], c.target[2] - c.position[2]);
    if (ctl.minDistance > dist) ctl.minDistance = dist * 0.5;
    if (ctl.maxDistance < dist) ctl.maxDistance = dist * 1.5;
    const b = this.modelBounds();
    if (b) {
      const rad = Math.hypot(b[3] - b[0], b[4] - b[1], b[5] - b[2]) / 2;
      if (cam.far < dist + rad * 2) cam.far = dist + rad * 2;
    }
    cam.updateProjectionMatrix();
    ctl.update();
    r.markDirty();
  }

  /**
   * Older and foreign viewpoints: a shape annotation without an attachment is projected onto the model from its viewpoint camera
   * (attached when that is clean, else view-locked, its fractions untouched); a viewpoint with <Lines> and no annotations of
   * ours gets one `lines` annotation, so a foreign tool's 3D redlines show here as world lines. Quiet: no change flag.
   */
  private prepareAttachments(ref: BcfViewpointRef): void {
    if (!this.app.loaded || !ref.data) return;
    const view = this.shapeView(ref);
    const W = Math.max(1, this.app.canvas.clientWidth);
    const H = Math.max(1, this.app.canvas.clientHeight);
    for (const a of ref.annotations ?? []) {
      if (!a.shape || a.attach !== undefined) continue;
      try {
        a.attach = view ? inferAttachment(fractionInput(this, a.type === 'rect' ? 'rect' : 'pen', a.shape.points, view, W, H)).attach : { kind: 'none' };
      } catch {
        a.attach = { kind: 'none' };
      }
    }
    if (!ref.annotations?.length && ref.data.lines.length && !this.linesSeen.has(ref)) {
      this.linesSeen.add(ref);
      const lines = ref.data.lines.slice(0, 4000).map((l) => [l.start, l.end] as [Vec3, Vec3]);
      ref.annotations = [{
        guid: newGuid(), type: 'freehand', text: '', offset: [0, 0], anchor: { kind: 'point', point: lines[0]![0] },
        attach: { kind: 'lines', lines },
      }];
    }
  }
  private readonly linesSeen = new WeakSet<BcfViewpointRef>();

  /** Apply a viewpoint of a loaded topic. With no viewpoint guid, the first viewpoint that has data. */
  applyViewpoint(topicGuid: string, viewpointGuid?: string): ApplyReport {
    const topic = this.topic(topicGuid);
    if (!topic) return this.fail(`No topic ${topicGuid}`);
    if (!this.inScope(topic)) return this.fail(`"${topic.title}" was made on another model. Open it from Other models, or Move to this model.`);
    const ref = viewpointGuid ? topic.viewpoints.find((v) => v.guid === viewpointGuid) : topic.viewpoints.find((v) => v.data);
    if (!ref) return this.fail(viewpointGuid ? `No viewpoint ${viewpointGuid} in this topic` : 'This topic has no viewpoint');
    if (!ref.data) return this.fail(ref.problem ?? 'The viewpoint file could not be read');
    const app = this.app;
    if (!app.loaded) return this.fail('No model loaded');
    const vp = ref.data;

    this.clearViewpoint(true);
    const els = this.model.elements;
    const cam = app.renderer.camera;
    const plan = planViewpoint(vp, {
      shift: app.loaded.model.originShift,
      resolve: (g) => this.model.byGlobalId.get(g),
      count: els.length,
      classOf: (i) => els[i]!.ifcClass,
      modelBounds: this.modelBounds(),
      fov: cam.fov,
      aspect: cam.aspect,
      canClip: this.canClip,
    });
    // Elements in the selection only because annotations point at them keep the x-ray look: not selected (they would
    // become focus and draw solid over what the viewpoint is about), but tinted like a selection until Clear viewpoint.
    const markup = new Set(markupSelectionOf(ref).map((g) => this.model.byGlobalId.get(g)).filter((x): x is number => x !== undefined));
    let tint: number[] = [];
    if (markup.size) {
      tint = plan.selection.filter((id) => markup.has(id));
      plan.selection = plan.selection.filter((id) => !markup.has(id));
      const i = plan.applied.findIndex((a) => a.startsWith('selection '));
      if (i >= 0) plan.applied[i] = `selection ${plan.selection.length}`;
      if (tint.length) plan.applied.push(`${tint.length} annotated highlighted`);
    }
    this.execute(plan, vp.selection.length > 0, vp.coloring.length > 0, tint);
    this.applied = { topic: topic.guid, viewpoint: ref.guid };
    this.prepareAttachments(ref);
    const unknown = plan.selectionUnknown + plan.visibilityUnknown + plan.colorUnknown;
    const status = `Viewpoint applied: ${plan.applied.join(', ') || 'nothing'}${plan.skipped.length ? `; skipped: ${plan.skipped.join(', ')}` : ''}`;
    this.setStatus(status);
    return { ok: true, applied: plan.applied, skipped: plan.skipped, unknownGuids: unknown, status };
  }

  private fail(msg: string): ApplyReport {
    this.setStatus(msg);
    return { ok: false, applied: [], skipped: [msg], unknownGuids: 0, status: msg };
  }

  private execute(plan: ViewpointPlan, hasSelection: boolean, hasColoring: boolean, tint: number[] = []): void {
    const app = this.app;
    const ov = app.controller.settings.overrides;
    if (plan.hide) {
      this.hides.hide(ov.userHides, plan.hide);
      for (const id of plan.hide) ov.userPins.delete(id);
      app.controller.refreshOverrides();
    }
    // Selection first: it may start the cinematic fly-to, which the viewpoint camera then overrides.
    if (hasSelection) app.selectIds(plan.selection);
    else app.clearSelection();
    cancelFly();
    if (plan.camera) this.setCamera(plan.camera);
    const color = app.renderer.state.color;
    const saved = new Map<number, [number, number, number]>();
    for (const id of tint) {
      const o = id * 3;
      if (o + 2 >= color.length) continue;
      saved.set(id, [color[o]!, color[o + 1]!, color[o + 2]!]);
      for (let k = 0; k < 3; k++) color[o + k] = color[o + k]! + (SELECT_TINT[k]! - color[o + k]!) * SELECT_MIX;
    }
    if (tint.length) this.savedColors = saved;
    if (hasColoring && plan.colors.length) {
      for (const c of plan.colors) {
        for (const id of c.ids) {
          const o = id * 3;
          if (!saved.has(id)) saved.set(id, [color[o]!, color[o + 1]!, color[o + 2]!]);
          color[o] = c.rgb[0];
          color[o + 1] = c.rgb[1];
          color[o + 2] = c.rgb[2];
        }
      }
      this.savedColors = saved;
    }
    if (plan.clip.length && this.canClip) {
      this.clipApi().setClipPlanes!(plan.clip);
      this.clipOwned = true;
      this.clipVersion = this.clipApi().clipVersion;
    }
    app.runSightlinesNow();
    app.renderer.markDirty();
  }

  /** The clip planes of the applied viewpoint were put back by someone else (the Plan and Section switch): they are ours again. */
  reclaimClip(): void {
    if (this.clipOwned) this.clipVersion = this.clipApi().clipVersion;
  }

  /** Undo what the last viewpoint did: its hides, colours and clip planes. Camera and selection stay. */
  clearViewpoint(quiet = false): number {
    const app = this.app;
    let shown = 0;
    if (app.controller) {
      const ov = app.controller.settings.overrides;
      shown = this.hides.restore(ov.userHides).length;
      if (shown) app.controller.refreshOverrides();
    }
    if (this.savedColors) {
      const color = app.renderer.state.color;
      for (const [id, c] of this.savedColors) {
        color[id * 3] = c[0];
        color[id * 3 + 1] = c[1];
        color[id * 3 + 2] = c[2];
      }
      this.savedColors = null;
    }
    if (this.clipOwned) {
      // Only our planes: if the section tool took the planes over since (a plane, box or Clear), leave its planes alone.
      const api = this.clipApi();
      if (this.clipVersion === undefined || api.clipVersion === undefined || api.clipVersion === this.clipVersion) api.setClipPlanes?.(null);
      this.clipOwned = false;
    }
    const was = this.applied !== null || shown > 0;
    this.applied = null;
    if (app.controller && was) app.runSightlinesNow();
    app.renderer.markDirty();
    if (!quiet) this.setStatus(was ? `Viewpoint cleared (${shown} hidden element${shown === 1 ? '' : 's'} restored)` : 'No viewpoint applied');
    return shown;
  }

  // ---------------------------------------------------------------- authoring

  /** PNG snapshot of the canvas. Rendered and read in the same task, so no preserveDrawingBuffer is needed. */
  snapshot(maxSide = 1280): Uint8Array | null {
    const r = this.app.renderer;
    r.markDirty();
    r.render();
    const src = this.app.canvas;
    const w = src.width;
    const h = src.height;
    if (!w || !h) return null;
    const s = Math.min(1, maxSide / Math.max(w, h));
    let url: string;
    if (s < 1) {
      const oc = document.createElement('canvas');
      oc.width = Math.max(1, Math.round(w * s));
      oc.height = Math.max(1, Math.round(h * s));
      const g = oc.getContext('2d');
      if (!g) return null;
      g.drawImage(src, 0, 0, oc.width, oc.height);
      url = oc.toDataURL('image/png');
    } else {
      url = src.toDataURL('image/png');
    }
    return dataUrlToBytes(url);
  }

  private currentCapture(): { ref: BcfViewpointRef; skippedIds: number; exceptions: number } {
    const app = this.app;
    const cam = app.renderer.camera;
    cam.updateMatrixWorld();
    const up = cam.up.clone().applyQuaternion(cam.quaternion);
    const t = app.renderer.controls.target;
    const els = this.model.elements;
    const clip: Array<{ normal: Vec3; point: Vec3 }> = [];
    for (const p of this.clipApi().getClipPlanes?.() ?? []) clip.push({ normal: v3(p.normal), point: v3(p.point) });
    const res = captureViewpoint({
      shift: app.loaded!.model.originShift,
      position: [cam.position.x, cam.position.y, cam.position.z],
      target: [t.x, t.y, t.z],
      up: [up.x, up.y, up.z],
      fov: cam.fov,
      aspect: cam.aspect,
      selection: app.selection,
      hidden: app.controller.settings.overrides.userHides,
      count: els.length,
      globalId: (id) => els[id]!.globalId,
      clip,
    });
    const ref: BcfViewpointRef = { guid: res.viewpoint.guid, data: res.viewpoint };
    // What is hidden or see-through now, for the occlusion fade when the markup is burned into this snapshot later.
    const hides = app.controller.settings.overrides.userHides;
    const alpha = app.renderer.state.alpha;
    const see = new Set<number>(hides);
    for (let i = 0; i < alpha.length; i++) if (alpha[i]! < GHOST_ALPHA) see.add(i);
    ref.captureSeeThrough = see;
    const c = res.viewpoint.camera;
    // The camera that takes the snapshot, unclamped (the 2.1 writer clamps the field of view), for the markup burn-in.
    if (c) ref.snapshotView = { position: [...c.position], direction: [...c.direction], up: [...c.up], fov: cam.fov, aspect: cam.aspect };
    return { ref, skippedIds: res.skippedIds, exceptions: res.exceptions };
  }

  private newTopic(o: CreateTopicOptions, author: string): BcfTopic {
    const now = nowIso();
    const t: BcfTopic = {
      guid: newGuid(),
      topicType: o.type?.trim() || 'Issue',
      topicStatus: o.status?.trim() || 'Open',
      title: o.title.trim() || 'Untitled',
      labels: (o.labels ?? []).map((l) => l.trim()).filter(Boolean),
      referenceLinks: [],
      creationDate: now,
      creationAuthor: author,
      headerFiles: [],
      documentReferences: [],
      relatedTopics: [],
      comments: [],
      viewpoints: [],
    };
    if (o.priority?.trim()) t.priority = o.priority.trim();
    if (o.description?.trim()) t.description = o.description.trim();
    if (o.assignedTo?.trim()) t.assignedTo = o.assignedTo.trim();
    if (o.dueDate) t.dueDate = o.dueDate;
    const file = this.app.modelName;
    if (file) t.headerFiles.push({ filename: file, date: now, isExternal: true });
    const id = this.modelIdentity();
    if (id) t.model = { ...id };
    return t;
  }

  private authorOf(o?: { author?: string }): string {
    return (o?.author ?? this.author).trim() || 'unknown';
  }

  /** Create a topic from the current view (or around `globalIds`). */
  createTopic(o: CreateTopicOptions): BcfTopic {
    if (!this.app.loaded) throw new Error('No model loaded');
    const author = this.authorOf(o);
    if (o.author?.trim()) this.setAuthor(o.author);
    const topic = this.newTopic(o, author);
    if (o.viewpoint !== false) {
      let restore: (() => void) | null = null;
      if (o.globalIds && o.globalIds.length) restore = this.stageAround(o.globalIds, o.camera);
      else if (o.camera) restore = this.stageCamera(o.camera);
      try {
        const cap = this.currentCapture();
        if (o.globalIds && o.globalIds.length) this.forceSelection(cap.ref, o.globalIds);
        if (o.snapshot !== false) {
          const png = this.snapshot();
          if (png) {
            cap.ref.snapshot = png;
            cap.ref.snapshotMime = 'image/png';
          }
        }
        topic.viewpoints.push(cap.ref);
      } finally {
        restore?.();
      }
    }
    const pin = o.pin === undefined ? this.defaultPin(o.globalIds) : o.pin;
    if (pin) {
      const pe = o.pin !== undefined ? o.pinElement : this.lastDefaultPinElement;
      topic.pin = this.makePin(pin, pe);
      this.markupRev++;
    }
    topic.pinNumber = this.nextPinNumber();
    this.project.topics.push(topic);
    this.dirty = true;
    this.selectedTopic = topic.guid;
    this.setStatus(`Topic created: ${topic.title}`);
    return topic;
  }

  /** Several topics at once, each selecting and framing its elements. Snapshots default to on for up to 20 topics. */
  createTopics(list: TopicSpec[], opts: { snapshot?: boolean } = {}): BcfTopic[] {
    if (!this.app.loaded) throw new Error('No model loaded');
    const snapshot = opts.snapshot ?? list.length <= 20;
    const app = this.app;
    const cam = app.renderer.camera;
    const savedCam = { p: cam.position.clone(), t: app.renderer.controls.target.clone() };
    const savedSel = app.selection;
    const out: BcfTopic[] = [];
    try {
      const els = this.model.elements;
      for (const s of list) {
        const gids = topicGlobalIds(s, els);
        let camera = s.camera;
        if (!camera && s.location) {
          const ids = gids.map((g) => this.model.byGlobalId.get(g)).filter((x): x is number => x !== undefined);
          camera = frameCamera(boxAround(s.location, this.elementBounds(ids)), cam.fov, cam.aspect);
        }
        out.push(this.createTopic({
          title: s.title, description: s.description, labels: s.labels, type: s.type, status: s.status, priority: s.priority, assignedTo: s.assignedTo,
          globalIds: gids.length ? gids : undefined, camera, snapshot, ...(s.location ? { pin: s.location } : {}),
        }));
      }
    } finally {
      cam.position.copy(savedCam.p);
      app.renderer.controls.target.copy(savedCam.t);
      app.renderer.controls.update();
      app.selectIds(savedSel);
      cancelFly();
      app.renderer.markDirty();
    }
    this.setStatus(`${out.length} topic${out.length === 1 ? '' : 's'} created`);
    return out;
  }

  /** Select and frame `globalIds` (or use `camera`) so the capture and snapshot show them; returns an undo of the camera + selection. */
  private stageAround(globalIds: string[], camera?: { position: Vec3; target: Vec3 }): () => void {
    const app = this.app;
    const ids: number[] = [];
    for (const g of globalIds) {
      const id = this.model.byGlobalId.get(g);
      if (id !== undefined) ids.push(id);
    }
    const savedSel = app.selection;
    const undoCam = this.stageCamera(camera ?? this.framing(ids));
    app.selectIds(ids);
    cancelFly();
    app.controller.settle();
    return () => {
      undoCam();
      app.selectIds(savedSel);
      cancelFly();
    };
  }

  private framing(ids: number[]): { position: Vec3; target: Vec3 } {
    const cam = this.app.renderer.camera;
    const box = this.elementBounds(ids);
    if (!box) {
      const t = this.app.renderer.controls.target;
      return { position: [cam.position.x, cam.position.y, cam.position.z], target: [t.x, t.y, t.z] };
    }
    return frameCamera(box, cam.fov, cam.aspect);
  }

  private stageCamera(c: { position: Vec3; target: Vec3 }): () => void {
    const r = this.app.renderer;
    const p0 = r.camera.position.clone();
    const t0 = r.controls.target.clone();
    this.setCamera({ position: c.position, target: c.target, up: [0, 1, 0], fov: r.camera.fov, approximatedOrthogonal: false });
    return () => {
      r.camera.position.copy(p0);
      r.controls.target.copy(t0);
      r.controls.update();
    };
  }

  /** Replace the viewpoint selection with the requested GlobalIds (valid IfcGuids only), whatever the viewer holds. */
  private forceSelection(ref: BcfViewpointRef, globalIds: string[]): void {
    if (!ref.data) return;
    const seen = new Set<string>();
    ref.data.selection = [];
    for (const g of globalIds) {
      const ig = toIfcGuid(g);
      if (ig && !seen.has(ig)) {
        seen.add(ig);
        ref.data.selection.push({ ifcGuid: ig });
      }
    }
  }

  addComment(topicGuid: string, text: string, o: { author?: string; viewpoint?: boolean } = {}): BcfComment {
    const topic = this.topic(topicGuid);
    if (!topic) throw new Error(`No topic ${topicGuid}`);
    const author = this.authorOf(o);
    const c: BcfComment = { guid: newGuid(), date: nowIso(), author, text: text.trim() };
    if (o.viewpoint && this.app.loaded) {
      const cap = this.currentCapture();
      const png = this.snapshot();
      if (png) {
        cap.ref.snapshot = png;
        cap.ref.snapshotMime = 'image/png';
      }
      topic.viewpoints.push(cap.ref);
      c.viewpointGuid = cap.ref.guid;
    }
    topic.comments.push(c);
    topic.modifiedDate = c.date;
    topic.modifiedAuthor = author;
    this.dirty = true;
    this.setStatus(`Comment added to ${topic.title}`);
    return c;
  }

  setTopicStatus(topicGuid: string, status: string): void {
    const t = this.topic(topicGuid);
    if (!t || !status.trim() || t.topicStatus === status) return;
    t.topicStatus = status;
    t.modifiedDate = nowIso();
    t.modifiedAuthor = this.authorOf();
    this.dirty = true;
    this.emit();
  }

  /** Change the priority, assignee or due date of a topic (an empty string clears it). */
  setTopicFields(topicGuid: string, f: { priority?: string; assignedTo?: string; dueDate?: string }): boolean {
    const t = this.topic(topicGuid);
    if (!t) return false;
    const set = (k: 'priority' | 'assignedTo' | 'dueDate', v: string | undefined): void => {
      if (v === undefined) return;
      const x = v.trim();
      if (x) t[k] = x;
      else delete t[k];
    };
    set('priority', f.priority);
    set('assignedTo', f.assignedTo);
    set('dueDate', f.dueDate);
    t.modifiedDate = nowIso();
    t.modifiedAuthor = this.authorOf();
    this.dirty = true;
    this.emit();
    return true;
  }

  // ---------------------------------------------------------------- markup: pins and annotations

  /** The model origin shift (IFC frame), zeros without a model. */
  get shift(): Vec3 {
    const s = this.app.loaded?.model.originShift;
    return s ? [s[0], s[1], s[2]] : [0, 0, 0];
  }

  /** Mark a topic as changed from outside (its comments or fields were edited by src/issues): stamps it and redraws. */
  touch(t?: BcfTopic): void {
    this.markupChanged(t);
  }

  /** Capture the current view as one more viewpoint of a topic (with a snapshot). */
  addViewpoint(topicGuid: string): BcfViewpointRef {
    const topic = this.topic(topicGuid);
    if (!topic) throw new Error(`No topic ${topicGuid}`);
    if (!this.app.loaded) throw new Error('No model loaded');
    const cap = this.currentCapture();
    const png = this.snapshot();
    if (png) {
      cap.ref.snapshot = png;
      cap.ref.snapshotMime = 'image/png';
    }
    topic.viewpoints.push(cap.ref);
    this.markupChanged(topic);
    return cap.ref;
  }

  /** Replace the camera, selection, visibility and snapshot of a viewpoint with the current view (its guid, link and drawing stay). */
  recaptureViewpoint(topicGuid: string, viewpointGuid: string): boolean {
    const topic = this.topic(topicGuid);
    const ref = topic?.viewpoints.find((v) => v.guid === viewpointGuid);
    if (!topic || !ref || !this.app.loaded) return false;
    const cap = this.currentCapture();
    ref.data = { ...cap.ref.data!, guid: ref.guid };
    delete ref.problem;
    if (cap.ref.captureSeeThrough) ref.captureSeeThrough = cap.ref.captureSeeThrough;
    if (cap.ref.snapshotView) ref.snapshotView = cap.ref.snapshotView;
    const png = this.snapshot();
    if (png) {
      ref.snapshot = png;
      ref.snapshotMime = 'image/png';
    }
    this.markupChanged(topic);
    return true;
  }

  private markupChanged(t?: BcfTopic): void {
    this.markupRev++;
    this.dirty = true;
    if (t) {
      t.modifiedDate = nowIso();
      t.modifiedAuthor = this.authorOf();
    }
    this.emit();
  }

  setPinsVisible(on: boolean): void {
    this.pinsVisible = on;
    this.markupRev++;
    this.emit();
  }

  /** Pin number shown on the marker: stable per topic (side file `pinNumber`), the next free number when it was made. */
  pinNumber(t: BcfTopic): number {
    if (t.pinNumber === undefined) this.assignPinNumbers();
    return t.pinNumber ?? this.project.topics.indexOf(t) + 1;
  }

  /** One more than the highest pin number in use. */
  nextPinNumber(): number {
    let max = 0;
    for (const t of this.project.topics) if (t.pinNumber !== undefined && t.pinNumber > max) max = t.pinNumber;
    return max + 1;
  }

  /**
   * Give every topic without a pin number (topics from other tools, older files), or with one that an earlier topic in the
   * list already uses (a merged file), the next free number, in list order. Topics that have their own keep it.
   */
  assignPinNumbers(): void {
    const used = new Set<number>();
    const todo: BcfTopic[] = [];
    for (const t of this.project.topics) {
      if (t.pinNumber !== undefined && Number.isInteger(t.pinNumber) && t.pinNumber >= 1 && !used.has(t.pinNumber)) used.add(t.pinNumber);
      else todo.push(t);
    }
    let next = used.size ? Math.max(...used) + 1 : 1;
    for (const t of todo) t.pinNumber = next++;
  }

  /** The BCF drawer mounts (true) or unmounts (false); pins follow it. */
  setDrawerOpen(open: boolean): void {
    this.drawers = Math.max(0, this.drawers + (open ? 1 : -1));
    this.markupRev++;
    this.emit();
  }

  get drawerOpen(): boolean {
    return this.drawers > 0;
  }

  /**
   * Topics whose pin is drawn: pins on and a pin; while the drawer is open, those passing its filter (and the selected one);
   * with the drawer closed, only the topic whose viewpoint is applied (pins are review markup, not part of the model view).
   */
  pinnedTopics(): BcfTopic[] {
    if (!this.pinsVisible) return [];
    if (!this.drawers) {
      const active = this.applied?.topic;
      return active ? this.project.topics.filter((t) => t.pin && t.guid === active && this.inScope(t)) : [];
    }
    return this.project.topics.filter((t) => t.pin && this.inScope(t) && (!this.pinFilter || this.pinFilter(t) || t.guid === this.selectedTopic));
  }

  private lastDefaultPinElement: string | undefined;

  /** Default pin: centre of the bounds of the GlobalIds (or the selection), else the surface in the middle of the view. */
  defaultPin(globalIds?: string[]): Vec3 | null {
    this.lastDefaultPinElement = undefined;
    if (!this.app.loaded) return null;
    let ids = (globalIds ?? []).map((g) => this.model.byGlobalId.get(g)).filter((x): x is number => x !== undefined);
    if (!ids.length && !globalIds?.length) ids = this.app.selection;
    const box = ids.length ? this.elementBounds(ids) : null;
    if (box) {
      if (ids.length === 1) this.lastDefaultPinElement = this.model.elements[ids[0]!]!.globalId;
      return [(box[0] + box[3]) / 2, (box[1] + box[4]) / 2, (box[2] + box[5]) / 2];
    }
    const hit = this.pick(0, 0);
    if (!hit) return null;
    this.lastDefaultPinElement = this.model.elements[hit.element]?.globalId;
    return hit.point;
  }

  /**
   * First surface under a view point (NDC, -1..1, y up), the ray test of the measure tool. Ghosted elements (drawn
   * see-through) are passed first, so the click lands on what the user sees; when only ghosts are under the cursor, they count.
   */
  pick(ndcX: number, ndcY: number): { point: Vec3; element: number } | null {
    const loaded = this.app.loaded;
    if (!loaded) return null;
    const cam = this.app.renderer.camera;
    cam.updateMatrixWorld();
    const hit = this.castRay(cameraRay(cam, ndcX, ndcY));
    return hit ? { point: hit.point, element: hit.element } : null;
  }

  /**
   * The ray test behind pick, for any ray (viewer frame): the same hidden, isolated and click-through ghost rules as a pick in
   * the current view. Also gives the surface normal (facing the ray origin) and the distance. Used by the attachment inference.
   */
  castRay(ray: Ray | Ray3): ProbeHit | null {
    const loaded = this.app.loaded;
    if (!loaded) return null;
    const r = ray instanceof Ray ? ray : new Ray(new Vector3(...ray.o), new Vector3(...ray.d));
    const hides = this.app.controller.settings.overrides.userHides;
    const alpha = this.app.renderer.state.alpha;
    const api = this.clipApi();
    const vm = api.viewModeCuts === true && !!api.viewModeCut;
    const cut = (id: number, p: Vector3): boolean => vm && api.viewModeCut!(id, p);
    const range: RangeProbe = (_ray, near, far) => {
      const hit = firstSurfaceHit(loaded.geometry, r, (id, p) => hides.has(id) || (alpha[id] ?? 1) < GHOST_ALPHA || cut(id, p), 256, { near, far })
        ?? firstSurfaceHit(loaded.geometry, r, (id, p) => hides.has(id) || (alpha[id] ?? 1) < 0 || cut(id, p), 256, { near, far });
      if (!hit) return null;
      const [a, b, c] = hit.triangle;
      const u: Vec3 = [b[0] - a[0], b[1] - a[1], b[2] - a[2]];
      const w: Vec3 = [c[0] - a[0], c[1] - a[1], c[2] - a[2]];
      const n: Vec3 = [u[1] * w[2] - u[2] * w[1], u[2] * w[0] - u[0] * w[2], u[0] * w[1] - u[1] * w[0]];
      const l = Math.hypot(n[0], n[1], n[2]) || 1;
      return { point: [hit.point.x, hit.point.y, hit.point.z], normal: [n[0] / l, n[1] / l, n[2] / l], element: hit.element, distance: hit.distance };
    };
    const planes = this.clipPlanesNow();
    const clip: ClipCast | null = planes.length ? { planes, caps: api.clipCapsDrawn === true, closed: (id) => api.closedFlags?.[id] === 1 } : null;
    return castClipped({ o: [r.origin.x, r.origin.y, r.origin.z], d: [r.direction.x, r.direction.y, r.direction.z] }, range, clip);
  }

  private clipCache: { version: number | undefined; planes: Plane[] } | null = null;
  /** The active section planes (unit normals, viewer frame): section planes, the section box, BCF clipping. Cached by the renderer's clipVersion. */
  private clipPlanesNow(): Plane[] {
    const api = this.clipApi();
    if (typeof api.getClipPlanes !== 'function') return [];
    const v = api.clipVersion;
    if (v !== undefined && this.clipCache && this.clipCache.version === v) return this.clipCache.planes;
    const planes = unitPlanes((api.getClipPlanes() ?? []).map((p) => ({ normal: v3(p.normal), point: v3(p.point) })));
    this.clipCache = { version: v, planes };
    return planes;
  }

  /** True when the element is hidden by the user, isolated away, or fully transparent: markup attached to it shows dimmed. */
  elementHidden(guid: string): boolean {
    const id = this.model?.byGlobalId.get(guid);
    if (id === undefined || !this.app.loaded) return false;
    return this.app.controller.settings.overrides.userHides.has(id) || (this.app.renderer.state.alpha[id] ?? 1) < 0.05;
  }

  /** The diagonal of the model bounds (m): the scale of the view-lock rule. */
  sceneSize(): number {
    const b = this.modelBounds();
    return b ? Math.max(1, Math.hypot(b[3] - b[0], b[4] - b[1], b[5] - b[2])) : 10;
  }

  /** The view-lock state of the live camera against a viewpoint camera (IFC frame): fade and pin of view-locked shapes. */
  lockState(view: BcfSnapshotView): LockState | undefined {
    if (!this.app.loaded) return undefined;
    const cam = this.app.renderer.camera;
    cam.updateMatrixWorld();
    const f = cam.getWorldDirection(cam.position.clone());
    return viewLockState(
      { position: [cam.position.x, cam.position.y, cam.position.z], direction: [f.x, f.y, f.z] },
      { position: ifcToViewer(view.position, this.shift), direction: dirIfcToViewer(view.direction) },
      this.sceneScale(ifcToViewer(view.position, this.shift)), viewLockSetting.mode,
    );
  }

  /** GlobalId of an element id. */
  guidOfId(id: number): string | undefined {
    return this.model?.elements[id]?.globalId || undefined;
  }

  /** Bounds centre of an element id (viewer frame). */
  centreOfId(id: number): Vec3 | null {
    const b = this.model?.elements[id]?.bounds;
    return b ? [(b[0] + b[3]) / 2, (b[1] + b[4]) / 2, (b[2] + b[5]) / 2] : null;
  }

  /** The scale of the view-lock shift for an authored eye (viewer frame): the model diagonal, or the eye's distance from the model centre if larger. */
  sceneScale(eye: Vec3): number {
    const b = this.modelBounds();
    if (!b) return 10;
    const d = Math.hypot(eye[0] - (b[0] + b[3]) / 2, eye[1] - (b[1] + b[4]) / 2, eye[2] - (b[2] + b[5]) / 2);
    return Math.max(this.sceneSize(), d);
  }

  /** The IFC class of an element by GlobalId (the chip says "2 pipes"). */
  classOf(guid: string): string | undefined {
    const id = this.model?.byGlobalId.get(guid);
    return id === undefined ? undefined : this.model.elements[id]?.ifcClass;
  }

  private readonly ray = new Ray();
  /** True when geometry hides the viewer-frame point `p` from `eye` (default: the camera). Hidden and ghosted elements do not count. */
  occluded(p: Vec3, eye?: Vec3, seeThrough?: (id: number) => boolean): boolean {
    const loaded = this.app.loaded;
    if (!loaded) return false;
    const e = eye ?? (() => { const c = this.app.renderer.camera.position; return [c.x, c.y, c.z] as Vec3; })();
    const d = Math.hypot(p[0] - e[0], p[1] - e[1], p[2] - e[2]);
    if (d < 1e-6) return false;
    this.ray.origin.set(e[0], e[1], e[2]);
    this.ray.direction.set((p[0] - e[0]) / d, (p[1] - e[1]) / d, (p[2] - e[2]) / d);
    const hides = this.app.controller.settings.overrides.userHides;
    const alpha = this.app.renderer.state.alpha;
    const api = this.clipApi();
    // Geometry that a section or a view mode cuts away does not hide anything; a point that is itself cut away is not tested.
    const planes = this.clipPlanesNow();
    let near = 0;
    let far = Infinity;
    if (planes.length) {
      if (!keptPoint(planes, p)) return false;
      const iv = clipInterval(planes, [e[0], e[1], e[2]], [this.ray.direction.x, this.ray.direction.y, this.ray.direction.z], d);
      if (!iv) return false;
      near = iv.near;
      far = iv.far;
    }
    const vm = api.viewModeCuts === true && !!api.viewModeCut;
    const base = seeThrough ?? ((id: number) => hides.has(id) || (alpha[id] ?? 1) < GHOST_ALPHA);
    const skip = vm ? (id: number, pt: Vector3): boolean => base(id) || api.viewModeCut!(id, pt) : (id: number): boolean => base(id);
    const hit = firstSurfaceHit(loaded.geometry, this.ray, skip, 64, { near, far });
    return !!hit && hit.distance < d - Math.max(0.03, d * 0.003);
  }

  /** Pin a topic to a viewer-frame point (null removes the pin). */
  setPin(topicGuid: string, point: Vec3 | null, elementGuid?: string): void {
    const t = this.topic(topicGuid);
    if (!t) throw new Error(`No topic ${topicGuid}`);
    if (point) t.pin = this.makePin(point, elementGuid);
    else delete t.pin;
    this.status = point ? `Pin placed for ${t.title}` : `Pin removed from ${t.title}`;
    this.markupChanged(t);
  }

  /** A pin at a viewer-frame point; on an element it also stores the offset from the element's bounds centre. */
  private makePin(point: Vec3, elementGuid?: string): { position: Vec3; elementGuid?: string; local?: Vec3 } {
    const pin: { position: Vec3; elementGuid?: string; local?: Vec3 } = { position: viewerToIfc(point, this.shift) };
    if (elementGuid) {
      pin.elementGuid = elementGuid;
      const local = this.localOffset(point, elementGuid);
      if (local) pin.local = local;
    }
    return pin;
  }

  /** `point` (viewer frame) minus the bounds centre of the element, as an IFC-frame offset; null for an unknown element. */
  private localOffset(point: Vec3, elementGuid: string): Vec3 | null {
    const id = this.model?.byGlobalId.get(elementGuid);
    const b = id !== undefined ? this.model.elements[id]?.bounds : undefined;
    if (!b) return null;
    const r = (x: number): number => Math.round(x * 1e6) / 1e6;
    const d = dirViewerToIfc([point[0] - (b[0] + b[3]) / 2, point[1] - (b[1] + b[4]) / 2, point[2] - (b[2] + b[5]) / 2]);
    return [r(d[0]), r(d[1]), r(d[2])];
  }

  /**
   * The current frame of an element (viewer frame): its bounds centre and its displacement (the exploded view sets one
   * per element through renderer.setElementOffset). Markup anchored to the element follows it.
   */
  elementFrame(guid: string, withOffset = true): { centre: Vec3; offset: Vec3 } | null {
    if (!this.app.loaded) return null;
    const id = this.model.byGlobalId.get(guid);
    const b = id !== undefined ? this.model.elements[id]?.bounds : undefined;
    if (id === undefined || !b) return null;
    const r = this.app.renderer as unknown as { elementOffset?: (id: number) => [number, number, number] };
    const offset: Vec3 = withOffset && typeof r.elementOffset === 'function' ? r.elementOffset(id) : [0, 0, 0];
    return { centre: [(b[0] + b[3]) / 2, (b[1] + b[4]) / 2, (b[2] + b[5]) / 2], offset };
  }

  /** The length unit of linked measurements: the measure tool's setting. */
  get units(): 'm' | 'mm' {
    return currentMeasureUnits();
  }

  /**
   * The camera that rectangle and freehand shapes of a viewpoint are drawn in: the snapshot camera, else the viewpoint's
   * perspective camera with the aspect of the viewer. Null for an orthogonal camera without a snapshot camera.
   */
  shapeView(ref: BcfViewpointRef): BcfSnapshotView | null {
    if (ref.snapshotView) return ref.snapshotView;
    const cam = ref.data?.camera;
    if (!cam || cam.kind !== 'perspective') return null;
    return snapshotCamera(undefined, { ...cam, aspect: cam.aspect ?? this.app.renderer.camera.aspect });
  }

  /** Viewer-frame position of a topic pin. */
  pinPoint(t: BcfTopic): Vec3 | null {
    return t.pin ? ifcToViewer(t.pin.position, this.shift) : null;
  }

  /** The viewpoint that annotations go to: the applied one when it belongs to the topic, else the first with data. */
  annotationViewpoint(topicGuid: string): BcfViewpointRef | undefined {
    const t = this.topic(topicGuid);
    if (!t) return undefined;
    if (this.applied?.topic === topicGuid) {
      const r = t.viewpoints.find((v) => v.guid === this.applied!.viewpoint);
      if (r?.data) return r;
    }
    return t.viewpoints.find((v) => v.data);
  }

  /** Annotations drawn now: those of the applied viewpoint. */
  visibleAnnotations(): { topic: BcfTopic; ref: BcfViewpointRef; list: BcfAnnotation[] } | null {
    if (!this.applied) return null;
    const t = this.topic(this.applied.topic);
    if (t && !this.inScope(t)) return null; // another model: nothing of it is drawn
    const r = t?.viewpoints.find((v) => v.guid === this.applied!.viewpoint);
    // A viewpoint whose drawing is a sketch: the markup view draws the sketch, so this one draws none (no double drawing).
    return t && r ? { topic: t, ref: r, list: r.sketchId ? [] : (r.annotations ?? []) } : null;
  }

  findAnnotation(guid: string): { topic: BcfTopic; ref: BcfViewpointRef; ann: BcfAnnotation } | null {
    for (const t of this.project.topics) for (const r of t.viewpoints) {
      const a = r.annotations?.find((x) => x.guid === guid);
      if (a) return { topic: t, ref: r, ann: a };
    }
    return null;
  }

  /** Capture a measurement of the measure tool (viewer frame) as a link in IFC coordinates. */
  measureLink(m: Measurement): BcfMeasureLink {
    const sh = this.shift;
    const link: BcfMeasureLink = { kind: m.kind, a: viewerToIfc([...m.a], sh), b: viewerToIfc([...m.b], sh), distance: m.distance, label: formatLength(m.distance, this.units), sourceId: m.id };
    const els = this.model?.elements ?? [];
    const gids = [m.elementA, m.elementB].filter((x): x is number => x !== undefined).map((id) => els[id]?.globalId).filter((g): g is string => !!g);
    if (gids.length) link.elementGuids = gids;
    return link;
  }

  /** Add an annotation to a viewpoint of a topic (default: annotationViewpoint). The annotated elements join its selection. */
  addAnnotation(topicGuid: string, spec: AnnotationSpec, viewpointGuid?: string): BcfAnnotation {
    const t = this.topic(topicGuid);
    if (!t) throw new Error(`No topic ${topicGuid}`);
    const ref = viewpointGuid ? t.viewpoints.find((v) => v.guid === viewpointGuid) : this.annotationViewpoint(topicGuid);
    if (!ref?.data) throw new Error('The topic has no viewpoint to annotate');
    const sh = this.shift;
    let a: BcfAnnotation;
    const base = { guid: newGuid(), type: spec.type, offset: spec.offset ?? defaultOffset(spec.type, ref.annotations?.length ?? 0), author: this.authorOf(), date: nowIso() };
    if (spec.anchor.kind === 'measurement') {
      const m = this.measureLink(spec.anchor.measurement);
      const mid: Vec3 = [(m.a[0] + m.b[0]) / 2, (m.a[1] + m.b[1]) / 2, (m.a[2] + m.b[2]) / 2];
      // No text by default: the box shows the length in the measure tool's current unit (annotationLines).
      a = { ...base, text: spec.text ?? '', anchor: { kind: 'measurement', point: mid, measurement: m } };
    } else {
      a = { ...base, text: spec.text ?? '', anchor: { kind: spec.anchor.kind, point: viewerToIfc(spec.anchor.point, sh) } };
      if (spec.anchor.elementGuid) {
        a.anchor.elementGuid = spec.anchor.elementGuid;
        const local = this.localOffset(spec.anchor.point, spec.anchor.elementGuid);
        if (local) a.anchor.local = local;
      }
    }
    this.pushAnnotation(ref, a);
    this.status = `${spec.type[0]!.toUpperCase()}${spec.type.slice(1)} added to ${t.title}`;
    this.markupChanged(t);
    return a;
  }

  /** Add the annotation; the elements it points at join the viewpoint selection (other BCF tools highlight them). */
  private pushAnnotation(ref: BcfViewpointRef, a: BcfAnnotation): void {
    if (ref.sketchId && this.linked?.add(ref, a)) return; // the sketch took it; its drawing is projected back onto the viewpoint
    (ref.annotations ??= []).push(a);
    if (!ref.data) return;
    const markup = new Set(markupSelectionOf(ref));
    const have = new Set(ref.data.selection.map((c) => c.ifcGuid));
    for (const g of annotationGuids([a])) {
      if (have.has(g)) continue;
      ref.data.selection.push({ ifcGuid: g });
      markup.add(g);
    }
    ref.markupSelection = [...markup];
  }

  /**
   * Add a rectangle (2 corners) or a freehand line drawn on the screen, in canvas CSS pixels, to the viewpoint of a topic.
   * The points are stored in the view of the viewpoint camera, on a plane through the surface under the middle of the shape.
   */
  addShape(topicGuid: string, type: BcfShapeType, screen: ReadonlyArray<readonly [number, number]>, text = '', viewpointGuid?: string, attachment?: Attachment): BcfAnnotation {
    const t = this.topic(topicGuid);
    if (!t) throw new Error(`No topic ${topicGuid}`);
    const ref = viewpointGuid ? t.viewpoints.find((v) => v.guid === viewpointGuid) : this.annotationViewpoint(topicGuid);
    if (!ref?.data) throw new Error('The topic has no viewpoint to annotate');
    const view = this.shapeView(ref);
    if (!view) throw new Error('Shapes need a perspective viewpoint camera');
    if (screen.length < 2) throw new Error('A shape needs at least 2 points');
    const sh = this.shift;
    const cv = this.app.canvas;
    const W = Math.max(1, cv.clientWidth);
    const H = Math.max(1, cv.clientHeight);
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (const [x, y] of screen) { x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y); }
    const ndc = (x: number, y: number): [number, number] => [(x / W) * 2 - 1, -((y / H) * 2 - 1)];
    // The plane of the shape: through the surface under its middle (else the orbit target), facing the viewpoint camera.
    const [cx, cy] = ndc((x0 + x1) / 2, (y0 + y1) / 2);
    const hit = this.pick(cx, cy);
    const tg = this.app.renderer.controls.target;
    let depth = shapeFraction(view, sh, hit ? hit.point : [tg.x, tg.y, tg.z]).depth;
    if (!(depth > 0.05)) depth = Math.max(1, shapeFraction(view, sh, [tg.x, tg.y, tg.z]).depth);
    const eye = ifcToViewer(view.position, sh);
    const centre = shapePointWorld(view, sh, 0.5, 0.5, depth);
    const nrm: Vec3 = [centre[0] - eye[0], centre[1] - eye[1], centre[2] - eye[2]];
    const cam = this.app.renderer.camera;
    cam.updateMatrixWorld();
    const toFrac = (x: number, y: number): [number, number] | null => {
      const [nx, ny] = ndc(x, y);
      const ray = cameraRay(cam, nx, ny);
      const o: Vec3 = [ray.origin.x, ray.origin.y, ray.origin.z];
      const d: Vec3 = [ray.direction.x, ray.direction.y, ray.direction.z];
      const den = d[0] * nrm[0] + d[1] * nrm[1] + d[2] * nrm[2];
      if (Math.abs(den) < 1e-9) return null;
      const k = ((centre[0] - o[0]) * nrm[0] + (centre[1] - o[1]) * nrm[1] + (centre[2] - o[2]) * nrm[2]) / den;
      if (k <= 0) return null;
      const f = shapeFraction(view, sh, [o[0] + d[0] * k, o[1] + d[1] * k, o[2] + d[2] * k]);
      const r = (v: number): number => Math.round(v * 1e5) / 1e5;
      return [r(f.u), r(f.v)];
    };
    let src: Array<readonly [number, number]>;
    if (type === 'rect') src = [[x0, y0], [x1, y1]];
    else {
      // Thin the line: points closer than 2 px to the last kept one go, and at most 512 points stay.
      const kept: Array<readonly [number, number]> = [];
      for (const p of screen) {
        const l = kept[kept.length - 1];
        if (!l || Math.hypot(p[0] - l[0], p[1] - l[1]) >= 2) kept.push(p);
      }
      const step = Math.max(1, Math.ceil(kept.length / 512));
      src = kept.filter((_, i) => i % step === 0 || i === kept.length - 1);
    }
    const points = src.map(([x, y]) => toFrac(x, y)).filter((p): p is [number, number] => p !== null);
    if (points.length < 2) throw new Error('The shape is not in front of the viewpoint camera');
    const mu = points.reduce((s2, p) => s2 + p[0], 0) / points.length;
    const mv = points.reduce((s2, p) => s2 + p[1], 0) / points.length;
    const a: BcfAnnotation = {
      guid: newGuid(), type, text, offset: defaultOffset(type, 0), author: this.authorOf(), date: nowIso(),
      anchor: { kind: 'point', point: viewerToIfc(shapePointWorld(view, sh, mu, mv, depth), sh) },
      shape: { points, depth: Math.round(depth * 1e4) / 1e4 },
    };
    // What the shape is attached to in 3D (the inference of src/bcf/surface.ts from the live camera), unless the caller says.
    if (attachment) a.attach = cloneAttach(attachment);
    else {
      try {
        a.attach = inferAttachment(screenInput(this, type === 'rect' ? 'rect' : 'pen', src, W, H, cam)).attach;
      } catch {
        a.attach = { kind: 'none' };
      }
    }
    this.pushAnnotation(ref, a);
    this.status = `${type === 'rect' ? 'Rectangle' : 'Freehand line'} added to ${t.title}`;
    this.markupChanged(t);
    return a;
  }

  /** Change the text or box offset of an annotation. `quiet`: redraw only (no drawer refresh, used while typing or dragging). */
  updateAnnotation(guid: string, patch: { text?: string; offset?: [number, number] }, quiet = false): boolean {
    const f = this.findAnnotation(guid);
    if (!f) return false;
    if (f.ref.sketchId && this.linked?.update(f.ref, guid, patch)) return true;
    if (patch.text !== undefined) f.ann.text = patch.text;
    if (patch.offset) f.ann.offset = [patch.offset[0], patch.offset[1]];
    if (quiet) {
      this.markupRev++;
      this.dirty = true;
      this.emit();
    } else this.markupChanged(f.topic);
    return true;
  }

  removeAnnotation(guid: string): boolean {
    const f = this.findAnnotation(guid);
    if (!f) return false;
    if (f.ref.sketchId && this.linked?.remove(f.ref, guid)) return true;
    const before = markupSelectionOf(f.ref);
    f.ref.annotations = f.ref.annotations!.filter((a) => a.guid !== guid);
    if (!f.ref.annotations.length) delete f.ref.annotations;
    // Elements that were selected only for annotations leave the selection with their last annotation.
    const still = new Set(annotationGuids(f.ref.annotations));
    const gone = new Set(before.filter((g) => !still.has(g)));
    if (gone.size && f.ref.data) f.ref.data.selection = f.ref.data.selection.filter((c) => !c.ifcGuid || !gone.has(c.ifcGuid));
    f.ref.markupSelection = before.filter((g) => still.has(g));
    this.status = 'Annotation deleted';
    this.markupChanged(f.topic);
    return true;
  }

  /** Copies of a topic's annotations per viewpoint (scripting and tests). */
  annotations(topicGuid: string): Record<string, BcfAnnotation[]> {
    const out: Record<string, BcfAnnotation[]> = {};
    for (const r of this.topic(topicGuid)?.viewpoints ?? []) if (r.annotations?.length) out[r.guid] = r.annotations.map(cloneAnnotation);
    return out;
  }

  /**
   * The snapshot of a viewpoint with the markup burned in (its annotations and the topic pin), as PNG (JPEG for a JPEG
   * snapshot). Null when the viewpoint has no annotations, or without a canvas. The projection uses the camera that took
   * the snapshot.
   */
  async composeSnapshot(t: BcfTopic, ref: BcfViewpointRef): Promise<Uint8Array | null> {
    if (!needsBurn(t, ref) || typeof document === 'undefined') return null;
    const view = snapshotCamera(ref.snapshotView, ref.data?.camera ?? null);
    if (!view) return null;
    const mime = ref.snapshotMime ?? 'image/png';
    let bmp: ImageBitmap;
    try {
      bmp = await createImageBitmap(new Blob([ref.snapshot as Uint8Array<ArrayBuffer>], { type: mime }));
    } catch {
      return null;
    }
    const w = bmp.width;
    const h = bmp.height;
    const cv = document.createElement('canvas');
    cv.width = w;
    cv.height = h;
    const g = cv.getContext('2d');
    if (!g) return null;
    g.drawImage(bmp, 0, 0);
    bmp.close?.();
    const sh = this.shift;
    const eye = ifcToViewer(view.position, sh);
    // The occlusion fade uses what was hidden or see-through when the snapshot was taken, not the hides of now.
    const see = this.app.loaded ? this.seeThroughAtCapture(ref) : null;
    const ctx: LayoutContext = {
      width: w, height: h, shift: sh, scale: snapshotScale(h),
      project: snapshotProjector(view, sh, w, h),
      occluded: see ? (p) => this.occluded(p, eye, (id) => see.has(id)) : undefined,
      units: this.units,
      // Anchors follow their element's bounds centre (a revised model), not the explode offsets of the live view.
      element: (g) => this.elementFrame(g, false),
      ...(ref.snapshotView ? { shapeDirect: true } : { shapeView: this.shapeView(ref) }),
      resolveSurface: (s) => this.resolveSurface(s, t, view),
    };
    const ops = layoutSnapshot(t.pin ? { pin: t.pin, label: String(this.pinNumber(t)) } : null, ref.annotations ?? [], ctx);
    if (!ops.length) return null;
    drawOps(g as unknown as Ctx2D, ops);
    const blob = await new Promise<Blob | null>((res) => cv.toBlob(res, mime, 0.92));
    return blob ? new Uint8Array(await blob.arrayBuffer()) : null;
  }

  /**
   * Elements hidden or see-through when the viewpoint was captured: kept in memory for viewpoints made in this session,
   * else the hidden elements of its Visibility (what the snapshot shows).
   */
  seeThroughAtCapture(ref: BcfViewpointRef): ReadonlySet<number> {
    if (ref.captureSeeThrough) return ref.captureSeeThrough;
    const vis = ref.data?.visibility;
    if (!vis || !this.app.loaded) return new Set();
    const els = this.model.elements;
    const v = visibilityHides(vis, { resolve: (g) => this.model.byGlobalId.get(g), count: els.length, classOf: (i) => els[i]!.ifcClass });
    // Same guard as applying: a DefaultVisibility false whose visible components are all unknown would hide everything.
    if (!vis.defaultVisibility && v.exceptionsResolved === 0) return new Set();
    return new Set(v.hide);
  }

  // ---------------------------------------------------------------- export

  async exportZip(version: BcfVersion = this.exportVersion): Promise<Uint8Array> {
    this.beforeExport?.();
    const project = this.deriveForExport ? this.deriveForExport(this.project) : this.project;
    const bytes = await writeBcf(project, version, { composeSnapshot: (t, r) => this.composeSnapshot(t, r) });
    this.dirty = false;
    const n = this.project.topics.length;
    this.setStatus(`Exported BCF ${version}: ${n} topic${n === 1 ? '' : 's'}, ${(bytes.length / 1024).toFixed(0)} KB`);
    return bytes;
  }

  async download(version: BcfVersion = this.exportVersion): Promise<Uint8Array> {
    const bytes = await this.exportZip(version);
    const stamp = new Date().toISOString().replace(/[-:]/g, '').slice(0, 13).replace('T', '-');
    const blob = new Blob([bytes as Uint8Array<ArrayBuffer>], { type: 'application/octet-stream' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `${this.app.modelName.replace(/[^\w.-]+/g, '_')}-${stamp}.bcfzip`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
    return bytes;
  }
}
