// BCF controller: holds the loaded / authored BCF project and applies viewpoints to the viewer.
//
// Provenance: a viewpoint hides elements through settings.overrides.userHides, remembering which ids it added itself
// (CleanupHides). `clearViewpoint` removes only those, so elements the user hid by hand stay hidden. Colours are temporary
// renderer.state.color overrides restored on clear; clipping goes through renderer.setClipPlanes when the renderer has it.

import type { ViewerApp } from '../app';
import { CleanupHides } from '../cleanup/hides';
import { parseBcf } from './parse';
import { writeBcf } from './write';
import { boxAround, captureViewpoint, frameCamera, planViewpoint, topicGlobalIds, unionBox } from './plan';
import type { Box6, PlanCamera, ViewpointPlan } from './plan';
import { emptyProject, newGuid, nowIso, toIfcGuid } from './model';
import type { BcfComment, BcfProject, BcfTopic, BcfVersion, BcfViewpointRef, Vec3 } from './model';

type PlaneLike = { normal: Vec3 | { x: number; y: number; z: number }; point: Vec3 | { x: number; y: number; z: number } };
interface ClipApi {
  setClipPlanes?(planes: Array<{ normal: Vec3; point: Vec3 }> | null, opts?: { cap?: boolean }): void;
  getClipPlanes?(): PlaneLike[] | null | undefined;
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
  private boundsFor: object | null = null;
  private bounds: Box6 | null = null;
  private lastPrune = 0;

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
    this.execute(plan, vp.selection.length > 0, vp.coloring.length > 0);
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

  private execute(plan: ViewpointPlan, hasSelection: boolean, hasColoring: boolean): void {
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
    if (hasColoring && plan.colors.length) {
      const color = app.renderer.state.color;
      const saved = new Map<number, [number, number, number]>();
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
      this.clipApi().setClipPlanes?.(null);
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
          globalIds: gids.length ? gids : undefined, camera, snapshot,
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

  // ---------------------------------------------------------------- export

  async exportZip(version: BcfVersion = this.exportVersion): Promise<Uint8Array> {
    const bytes = await writeBcf(this.project, version);
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
