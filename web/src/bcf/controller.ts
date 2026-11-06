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
import type { BcfMarkupView } from './pins';
import { annotationGuids, cloneAnnotation, markupSelectionOf, needsBurn } from './sidecar';
import { cameraRay, firstSurfaceHit } from '../measure/geometry';
import { currentMeasureUnits } from '../measure/current';
import { formatLength } from '../measure/maths';
import type { Measurement } from '../measure/maths';
import { Ray, Vector3 } from 'three';

type PlaneLike = { normal: Vec3 | { x: number; y: number; z: number }; point: Vec3 | { x: number; y: number; z: number } };
interface ClipApi {
  setClipPlanes?(planes: Array<{ normal: Vec3; point: Vec3 }> | null, opts?: { cap?: boolean }): void;
  getClipPlanes?(): PlaneLike[] | null | undefined;
  /** Bumped by every setClipPlanes (renderer.ts); lets clear leave planes alone that someone set after us. */
  clipVersion?: number;
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
  /** The live markup view (pins.ts), set by it; the topic dialog starts pin placement through it. */
  markup: BcfMarkupView | null = null;

  constructor(readonly app: ViewerApp) {
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
  get topics(): BcfTopic[] {
    return this.project.topics;
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

  onModel(): void {
    // The renderer state, the hide set and the clip planes were replaced with the model.
    this.hides.clear();
    this.savedColors = null;
    this.clipOwned = false;
    this.applied = null;
    this.boundsFor = null;
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
      this.project = p;
      this.dirty = false;
      this.selectedTopic = null;
    }
    this.assignPinNumbers();
    const n = p.topics.length;
    const vps = p.topics.reduce((s, t) => s + t.viewpoints.length, 0);
    this.setStatus(`BCF ${p.versionId}: ${n} topic${n === 1 ? '' : 's'}, ${vps} viewpoint${vps === 1 ? '' : 's'}${p.warnings.length ? `, ${p.warnings.length} warning${p.warnings.length === 1 ? '' : 's'}` : ''}`);
    if (p.topics.length && !this.selectedTopic) this.selectedTopic = p.topics[0]!.guid;
    this.emit();
    return p;
  }

  // ---------------------------------------------------------------- viewpoints: apply and clear

  private setCamera(c: PlanCamera): void {
    const r = this.app.renderer;
    const cam = r.camera;
    const ctl = r.controls;
    cam.up.set(0, 1, 0);
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

  /** Apply a viewpoint of a loaded topic. With no viewpoint guid, the first viewpoint that has data. */
  applyViewpoint(topicGuid: string, viewpointGuid?: string): ApplyReport {
    const topic = this.topic(topicGuid);
    if (!topic) return this.fail(`No topic ${topicGuid}`);
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

  // ---------------------------------------------------------------- markup: pins and annotations

  /** The model origin shift (IFC frame), zeros without a model. */
  get shift(): Vec3 {
    const s = this.app.loaded?.model.originShift;
    return s ? [s[0], s[1], s[2]] : [0, 0, 0];
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
      return active ? this.project.topics.filter((t) => t.pin && t.guid === active) : [];
    }
    return this.project.topics.filter((t) => t.pin && (!this.pinFilter || this.pinFilter(t) || t.guid === this.selectedTopic));
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
    const ray = cameraRay(cam, ndcX, ndcY);
    const hides = this.app.controller.settings.overrides.userHides;
    const alpha = this.app.renderer.state.alpha;
    const hit = firstSurfaceHit(loaded.geometry, ray, (id) => hides.has(id) || (alpha[id] ?? 1) < GHOST_ALPHA)
      ?? firstSurfaceHit(loaded.geometry, ray, (id) => hides.has(id) || (alpha[id] ?? 1) < 0);
    return hit ? { point: [hit.point.x, hit.point.y, hit.point.z], element: hit.element } : null;
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
    this.ray.direction.copy(new Vector3(p[0] - e[0], p[1] - e[1], p[2] - e[2]).multiplyScalar(1 / d));
    const hides = this.app.controller.settings.overrides.userHides;
    const alpha = this.app.renderer.state.alpha;
    const skip = seeThrough ?? ((id: number) => hides.has(id) || (alpha[id] ?? 1) < GHOST_ALPHA);
    const hit = firstSurfaceHit(loaded.geometry, this.ray, skip, 64);
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
    const r = t?.viewpoints.find((v) => v.guid === this.applied!.viewpoint);
    return t && r ? { topic: t, ref: r, list: r.annotations ?? [] } : null;
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
  addShape(topicGuid: string, type: BcfShapeType, screen: ReadonlyArray<readonly [number, number]>, text = '', viewpointGuid?: string): BcfAnnotation {
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
    this.pushAnnotation(ref, a);
    this.status = `${type === 'rect' ? 'Rectangle' : 'Freehand line'} added to ${t.title}`;
    this.markupChanged(t);
    return a;
  }

  /** Change the text or box offset of an annotation. `quiet`: redraw only (no drawer refresh, used while typing or dragging). */
  updateAnnotation(guid: string, patch: { text?: string; offset?: [number, number] }, quiet = false): boolean {
    const f = this.findAnnotation(guid);
    if (!f) return false;
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
    const bytes = await writeBcf(this.project, version, { composeSnapshot: (t, r) => this.composeSnapshot(t, r) });
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
