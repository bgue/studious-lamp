// Views plugin: named viewpoints people come back to. A view stores the camera (with up, field of view and the
// pseudo-orthographic flag), the section box and plane (and foreign clip planes), selection, hides, pins and isolate,
// the exploded state, a params snapshot (x-ray, view modes, imaging, sightlines, display, cinematic, ...), the active
// preset id and a thumbnail. A view may carry drawings (src/markup, the drawing engine): the Views tab lists the saved views and the
// views that only have a drawing layer as one list (src/views/unified.ts). See docs-features/saved-views.md and
// docs/design/views-and-issues.md.
//
//   - Sidebar tab "Views" (src/views/panel.ts), actions views.save (Ctrl+Shift+S), views.prev / views.next
//     (Shift+PageUp / Shift+PageDown), views.play, views.open.
//   - Persistence: localStorage `xray.views.<model>` (src/views/model.ts), export / import JSON, params section
//     `views` (not in the share URL), a share link `#view=<base64url>` for one view.
//   - Packed pages: window.__xrayBoot.views is merged in on the first model; boot.openView is opened by plugins/boot.ts.
//   - window.__xrayViews for scripts and smoke tests.

import { Vector3 } from 'three';
import type { AppPlugin, ViewerApp } from '../app';
import { getAction, registerAction } from '../input/actions';
import { VIEW_MOVE_MS, isPseudoOrtho, navSettings } from '../input/navigation';
import { turnTo } from '../gizmo/camera';
import { bootConfig } from '../tools/registry';
import { copyText } from '../ui/dom';
import { registerParamSection } from '../ui/params';
import type { ParamsApp } from '../ui/params';
import { addSidebarTab } from './sidebar';
import { bcfController } from './bcf';
import { markupController } from './markup';
import type { MarkupController } from '../markup/controller';
import type { MarkupSet } from '../markup/model';
import type { IssuesController } from '../issues/controller';
import { buildEntries, filterEntries, findEntry, isViewFilter } from '../views/unified';
import type { ViewEntry, ViewFilter } from '../views/unified';
import { buildIssuesPanel } from '../issues/ui';
import type { SidebarTabHandle } from './sidebar';
import { applyPlan, captureView, currentViewParams, planRestore } from '../views/capture';
import type { ViewsApp } from '../views/capture';
import {
  decodeViewShare,
  defaultName,
  duplicateView,
  encodeViewShare,
  findView,
  hashWithoutView,
  loadPackedSeen,
  loadViews,
  mergePackedViews,
  mergeViews,
  moveView,
  parseViewsDocument,
  savePackedSeen,
  saveViews,
  stepIndex,
  stripView,
  uniqueName,
  viewShareFromHash,
  viewShareUrl,
  viewSummary,
  viewsDocument,
} from '../views/model';
import type { SavedView, StorageLike, Vec3, ViewCamera } from '../views/model';
import { ViewsPanel } from '../views/panel';
import { captureThumb } from '../views/thumb';

export interface RestoreResult {
  name: string;
  /** GlobalIds of the view that the model lacks. */
  missing: string[];
  /** Params keys that could not be applied. */
  skipped: string[];
  /** Sections that differed and were applied. */
  applied: string[];
}

/** One row of the Views list, as scripts see it (the saved views and the views that only have a drawing layer). */
export interface ViewRow {
  /** A saved view id, or the id of a markup set that has no saved view. `restore` takes it. */
  id: string;
  name: string;
  summary: string;
  hasThumb: boolean;
  note: string;
  /** Number of drawings. */
  drawings: number;
  hasDrawings: boolean;
  /** A page of a PDF sheet. */
  sheet: boolean;
  /** The markup set that holds the drawings, when the view has one. */
  set: string | null;
  /** The issue the view is in. */
  issue: { topic: string; title: string } | null;
}

export interface ViewsApi {
  list(): ViewRow[];
  /** The list, filtered: all, with drawings, on sheets, in an issue. */
  entries(filter?: ViewFilter): ViewEntry[];
  /** The views that have drawings. */
  withDrawings(): ViewRow[];
  /** The filter of the Views tab, and setting it. */
  readonly filter: ViewFilter;
  setFilter(f: ViewFilter): void;
  /** Show the Views tab (on a filter). */
  open(filter?: ViewFilter): void;
  /** Draw on a view (saved view id, set id or name): it gets a drawing layer if it has none, the drawing toolbar comes up. Returns the set id. */
  drawOn(key: string): Promise<string>;
  /** Save the current state as a view and draw on it. Returns the set. */
  drawOnCurrent(name?: string): MarkupSet;
  /** Make an issue of a view (a new one, or one more viewpoint of `topic`). Returns the issue guid. */
  makeIssue(key: string, opts?: { topic?: string }): Promise<string>;
  get(key: string): SavedView | null;
  /** Save the current state as a view (name optional). */
  save(name?: string): SavedView;
  /** Restore a view by id, name or 1-based position (or the id of a view that only has drawings). animate defaults to true (false: jump). */
  restore(key: string, opts?: { animate?: boolean }): RestoreResult;
  update(key: string): SavedView;
  rename(key: string, name: string): void;
  duplicate(key: string): SavedView;
  remove(key: string): void;
  move(from: number, to: number): void;
  next(): RestoreResult | null;
  prev(): RestoreResult | null;
  play(dwellMs?: number): void;
  stop(): void;
  readonly playing: boolean;
  readonly active: string | null;
  shareUrl(key: string): string;
  exportJson(withThumbs?: boolean): string;
  importJson(text: string): { added: number; replaced: number; bad: string[]; error?: string };
  /** The current camera, as a view stores it. */
  camera(): ViewCamera;
  /** Capture the current state as a view without adding it to the list (the markup tool keeps its own views). */
  capture(name?: string): SavedView;
  /** Restore a view object that is not in the list (a markup set). Same effect as restore(). */
  restoreView(view: SavedView, opts?: { animate?: boolean }): RestoreResult;
  /** The share link of a view object, or '' when there is no model. */
  shareUrlFor(view: SavedView): string;
  /** Views from a shared link or a packed page, applied but maybe not in the list. */
  readonly lastRestore: RestoreResult | null;
}

declare global {
  interface Window {
    __xrayViews?: ViewsApi;
  }
}

interface CinematicLike {
  readonly exploded?: boolean;
  explode?(): number;
  collapse?(): void;
}
interface SectionLike {
  config: { box: { enabled: boolean }; plane: { enabled: boolean } };
  set(p: unknown): string[];
  foreignPlanes?(): number;
}
interface BcfLike {
  createTopic(o: { title: string; description?: string }): { guid?: string; title?: string };
  readonly applied?: { topic: string; viewpoint: string } | null;
  clearViewpoint?(quiet?: boolean): number;
}
interface PresetsLike {
  active(): string | null;
  markActive?(id: string): boolean;
}

const w = (): {
  __cinematic?: CinematicLike;
  __xraySection?: SectionLike;
  __xrayBcf?: BcfLike;
  __xrayPresets?: PresetsLike;
} => window as never;

const MSG_MS = 5000;
const MAX_MISSING_LISTED = 4;

function storage(): StorageLike | null {
  try {
    const s = window.localStorage;
    s.getItem('xray.probe');
    return s;
  } catch {
    return null;
  }
}

function reducedMotion(): boolean {
  try {
    return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;
  } catch {
    return false;
  }
}

function download(name: string, text: string): void {
  const url = URL.createObjectURL(new Blob([text], { type: 'application/json' }));
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

class ViewsController {
  views: SavedView[] = [];
  activeId: string | null = null;
  modelName = '';
  /** Filtered params after the first model: the base a partial view (share link, packed file) is merged over. */
  factory: Record<string, unknown> | null = null;
  /** Ids deleted in this session: an import (or "Reset to defaults" of the params) does not bring them back. */
  readonly deleted = new Set<string>();
  playTimer: ReturnType<typeof setTimeout> | null = null;
  playIndex = -1;
  dwell = 4000;
  lastRestore: RestoreResult | null = null;
  panel: ViewsPanel | null = null;
  tab: SidebarTabHandle | null = null;
  /** The Issues side (src/plugins/issues.ts links it): the detail of a view with drawings, making issues. */
  issues: IssuesController | null = null;
  filterKind: ViewFilter = 'all';
  private renderTimer: ReturnType<typeof setTimeout> | null = null;
  private msgTimer: ReturnType<typeof setTimeout> | null = null;
  readonly store = storage();

  constructor(readonly app: ViewerApp) {}

  get vapp(): ViewsApp {
    return this.app as unknown as ViewsApp;
  }

  get playing(): boolean {
    return this.playTimer !== null;
  }

  /**
   * An AR or VR session runs: it sets its own look, cut box and camera (field AR), and puts them back on exit. A view
   * saved now would store the session's look; a view restored now would replace the session's cut and look.
   */
  get inXr(): boolean {
    return (this.app.renderer as unknown as { xrPresenting?: boolean }).xrPresenting === true;
  }

  // ---------------------------------------------------------------- messages

  /** A line in the tab and a status bar message that clears itself. */
  note(text: string, statusBar = true, ms = MSG_MS): void {
    this.panel?.say(text);
    if (!statusBar) return;
    this.app.showMessage(text);
    if (this.msgTimer) clearTimeout(this.msgTimer);
    this.msgTimer = setTimeout(() => {
      this.msgTimer = null;
      this.app.showMessage(null);
    }, ms);
  }

  render(): void {
    this.panel?.render();
  }

  /** Draw the list again soon (the markup or the issues changed); only while the tab is on screen. */
  scheduleRender(): void {
    if (this.renderTimer || !this.panel) return;
    this.renderTimer = setTimeout(() => {
      this.renderTimer = null;
      if (this.tab?.visible()) this.panel?.render();
    }, 80);
  }

  get mk(): MarkupController | null {
    return markupController();
  }

  // ---------------------------------------------------------------- the unified list

  entries(): ViewEntry[] {
    const mk = this.mk;
    return buildEntries({ views: this.views, sets: mk ? mk.visibleSets().map((x) => x.set) : [], topics: bcfController()?.topics ?? [] });
  }

  entry(key: string): ViewEntry {
    const e = findEntry(this.entries(), key);
    if (!e) throw new Error(`No view "${key}"`);
    return e;
  }

  activeKey(): string | null {
    const all = this.entries();
    if (this.activeId && all.some((e) => e.viewId === this.activeId)) return `v:${this.activeId}`;
    const mid = this.mk?.activeId;
    return mid ? all.find((e) => e.setId === mid)?.key ?? null : null;
  }

  setFilter(f: ViewFilter): void {
    if (this.filterKind === f && this.issues?.viewFilter === f) return;
    this.filterKind = f;
    if (this.issues) {
      this.issues.viewFilter = f;
      this.issues.detail = null;
    }
    this.render();
    this.issues?.emit();
  }

  private setOf(e: ViewEntry): MarkupSet | undefined {
    return e.setId ? this.mk?.get(e.setId) : undefined;
  }

  /** Restore an entry: a saved view the usual way; a view with a drawing layer through the layer, so its drawings show. */
  restoreEntry(e: ViewEntry, animate = true): RestoreResult {
    const mk = this.mk;
    if (e.viewId) {
      mk?.untint();
      const r = this.restore(this.index(e.viewId), animate);
      if (e.setId && mk && mk.get(e.setId) && !r.skipped.includes('xr session')) {
        mk.activeId = e.setId;
        mk.selected = null;
        mk.syncTint();
        mk.emit();
      }
      return r;
    }
    if (!mk) throw new Error('Drawings are not in this build');
    this.stop(false);
    return mk.restore(e.id, animate);
  }

  /** The drawing layer of a view, made when it has none (a saved view that is restored first, so the layer holds its camera). */
  async ensureSet(e: ViewEntry): Promise<MarkupSet> {
    const mk = this.mk;
    if (!mk) throw new Error('Drawings are not in this build');
    const have = this.setOf(e);
    if (have) return have;
    const i = this.index(e.viewId ?? e.id);
    const v = this.views[i]!;
    this.stop(false);
    this.restoreView(v, false);
    this.activeId = v.id;
    await mk.settleView();
    const set = mk.newSet(v.name, { view: v, ...(v.thumb ? { thumb: v.thumb } : {}) });
    this.commit(this.views.map((x, k) => (k === i ? { ...x, drawings: set.id } : x)));
    return set;
  }

  /** Save the current state as a view that has a drawing layer. Nothing is restored: it is what is on screen. */
  saveWithDrawings(name?: string): MarkupSet {
    const mk = this.mk;
    if (!mk) throw new Error('Drawings are not in this build');
    const v = this.save(name);
    const set = mk.newSet(v.name, { view: v, ...(v.thumb ? { thumb: v.thumb } : {}) });
    this.commit(this.views.map((x) => (x.id === v.id ? { ...x, drawings: set.id } : x)));
    return set;
  }

  /** Show the drawing toolbar on a view's drawing layer (the layer is made first when there is none). */
  async drawOnEntry(e: ViewEntry): Promise<string> {
    const set = await this.ensureSet(e);
    const ic = this.issues;
    if (ic) {
      ic.openSketch(set.id);
      ic.editSketch(set.id);
    } else {
      this.mk?.restore(set.id, true);
      this.mk?.setEditing(true);
    }
    this.render();
    return set.id;
  }

  async makeIssueOf(e: ViewEntry, o: { topic?: string } = {}): Promise<string> {
    const ic = this.issues;
    if (!ic) throw new Error('Issues are not in this build');
    const set = await this.ensureSet(e);
    return ic.raise(set.id, o);
  }

  savedOfSet(setId: string): SavedView | undefined {
    return this.views.find((v) => v.drawings === setId);
  }

  persist(): void {
    if (!this.store) return;
    if (!saveViews(this.store, this.modelName, this.views)) this.note('Could not store the views (browser storage is full or blocked). They last for this session.');
  }

  commit(next: SavedView[]): void {
    this.views = next;
    this.persist();
    this.render();
  }

  index(key: string): number {
    const i = findView(this.views, key);
    if (i < 0) throw new Error(`No saved view "${key}"`);
    return i;
  }

  // ---------------------------------------------------------------- capture

  capture(name: string, keep?: SavedView): SavedView {
    const app = this.app;
    const sec = w().__xraySection;
    const sectionOn = !!sec && (sec.config.box.enabled || sec.config.plane.enabled);
    const planes = app.renderer.getClipPlanes() as Array<{ normal: Vec3; point: Vec3 }> | null;
    const foreign = !sectionOn && planes && planes.length ? planes : null;
    let preset: string | null = null;
    try {
      preset = w().__xrayPresets?.active() ?? null;
    } catch {
      preset = null;
    }
    const v = captureView(this.vapp, name, {
      ortho: isPseudoOrtho(),
      exploded: w().__cinematic?.exploded === true,
      preset,
      clip: foreign,
      thumb: captureThumb(app) ?? null,
      takenIds: new Set(this.views.map((x) => x.id)),
    });
    if (keep) {
      v.id = keep.id;
      v.name = keep.name;
      v.created = keep.created;
    }
    return v;
  }

  save(name?: string): SavedView {
    if (!this.app.loaded) throw new Error('No model loaded');
    if (this.inXr) throw new Error('Leave the AR or VR session to save a view: the session changes the look and the cuts.');
    const n = name?.trim() ? uniqueName(name, this.views) : defaultName(this.views);
    const v = this.capture(n);
    this.activeId = v.id;
    this.commit([...this.views, v]);
    this.note(`Saved view "${v.name}" (${this.views.length}).`, false);
    this.panel?.focusView(this.views.length - 1);
    return v;
  }

  update(i: number): SavedView {
    if (this.inXr) throw new Error('Leave the AR or VR session to update a view: the session changes the look and the cuts.');
    const old = this.views[i]!;
    const v = this.capture(old.name, old);
    this.activeId = v.id;
    this.commit(this.views.map((x, k) => (k === i ? v : x)));
    this.note(`Updated "${v.name}".`, false);
    return v;
  }

  // ---------------------------------------------------------------- restore

  restoreView(view: SavedView, animate: boolean): RestoreResult {
    const app = this.app;
    if (!app.loaded) throw new Error('No model loaded');
    if (this.inXr) {
      this.note(`Saved view "${view.name}" not restored: leave the AR or VR session first.`, true, 4000);
      return { name: view.name, missing: [], skipped: ['xr session'], applied: [] };
    }
    const model = app.controller.model;
    // A saved view replaces the whole state: an applied BCF viewpoint ends first (its hides, colours and clip planes
    // go, and its pin and callouts stop drawing). Its hides and planes are in the view when it was saved under it.
    const bcf = w().__xrayBcf;
    if (bcf?.applied) bcf.clearViewpoint?.();
    const plan = planRestore(view, model, currentViewParams(app as unknown as ParamsApp), this.factory);
    const skipped = applyPlan(this.vapp, plan);
    // The preset the view was taken with is the active one again (its settings are back); a later change clears it.
    if (view.preset) {
      try {
        w().__xrayPresets?.markActive?.(view.preset);
      } catch {
        /* a presets plugin without the mark */
      }
    }

    // Clip planes: the section tool owns them when the view has a box or a plane; else the view's own planes (a BCF
    // viewpoint that was active when it was saved), else none.
    const sec = w().__xraySection;
    const sectionOn = !!sec && (sec.config.box.enabled || sec.config.plane.enabled);
    const foreignNow = sec?.foreignPlanes?.() ?? 0;
    if (sectionOn) {
      if (foreignNow > 0) sec!.set({});
    } else if (view.clip?.length) app.renderer.setClipPlanes(view.clip);
    else if (foreignNow > 0 || (!sec && app.renderer.getClipPlanes())) app.renderer.setClipPlanes(null);

    // Exploded context: after the selection (a selection change collapses it).
    const cin = w().__cinematic;
    if (cin) {
      if (view.exploded && !cin.exploded) cin.explode?.();
      else if (!view.exploded && cin.exploded) cin.collapse?.();
    }

    this.moveCamera(view.camera, animate && !reducedMotion());
    app.renderer.markDirty();

    const res: RestoreResult = { name: view.name, missing: plan.missing, skipped, applied: Object.keys(plan.params) };
    this.lastRestore = res;
    if (plan.missing.length > 0) {
      const shown = plan.missing.slice(0, MAX_MISSING_LISTED).join(', ');
      const more = plan.missing.length > MAX_MISSING_LISTED ? ` and ${plan.missing.length - MAX_MISSING_LISTED} more` : '';
      this.note(`View "${view.name}": ${plan.missing.length} element${plan.missing.length === 1 ? '' : 's'} not in this model (${shown}${more}).`, true, 8000);
    } else if (skipped.length > 0) {
      this.note(`View "${view.name}" restored; not applied: ${skipped.slice(0, 5).join(', ')}${skipped.length > 5 ? ', ...' : ''}.`, true, 6000);
    } else this.panel?.say(`Restored "${view.name}".`);
    return res;
  }

  restore(i: number, animate = true): RestoreResult {
    const v = this.views[i]!;
    const r = this.restoreView(v, animate);
    if (r.skipped.includes('xr session')) {
      this.stop(false);
      return r;
    }
    this.activeId = v.id;
    this.render();
    return r;
  }

  moveCamera(cam: ViewCamera, animate: boolean): void {
    const app = this.app;
    const { camera, controls } = app.renderer;
    const ortho = isPseudoOrtho();
    const toggle = (): void => getAction('view.projection')?.run(app);
    const setFov = (fov: number): void => {
      if (Math.abs(camera.fov - fov) > 1e-6) {
        camera.fov = fov;
        camera.updateProjectionMatrix();
      }
    };
    if (!ortho && !cam.ortho) setFov(cam.fov);
    else if (!ortho && cam.ortho) {
      setFov(cam.fov);
      toggle();
    } else if (ortho && !cam.ortho) {
      toggle();
      setFov(cam.fov);
    }
    const pos = new Vector3(...cam.position);
    const target = new Vector3(...cam.target);
    const off = pos.clone().sub(target);
    const dist = Math.max(off.length(), 1e-6);
    const dir = off.divideScalar(dist);
    // Reach: the far plane and the orbit limits must allow the stored distance.
    const b = app.loaded?.geometry.totalBounds();
    const diag = b && !b.isEmpty() ? b.min.distanceTo(b.max) : 10;
    if (camera.far < dist + diag * 2) {
      camera.far = dist + diag * 2;
      camera.updateProjectionMatrix();
    }
    if (controls.minDistance > dist) controls.minDistance = dist * 0.5;
    if (controls.maxDistance > 0 && controls.maxDistance < dist * 1.05) controls.maxDistance = dist * 1.05;
    const view = { direction: [dir.x, dir.y, dir.z] as Vec3, up: [...cam.up] as Vec3 };
    if (animate) turnTo(app, view, target, dist);
    else {
      const smooth = navSettings.smoothMoves;
      navSettings.smoothMoves = false;
      try {
        turnTo(app, view, target, dist);
      } finally {
        navSettings.smoothMoves = smooth;
      }
    }
  }

  step(dir: 1 | -1): RestoreResult | null {
    if (this.views.length === 0) {
      this.note('No saved views yet. Press Ctrl+Shift+S to save one.', true, 3000);
      return null;
    }
    const cur = this.views.findIndex((v) => v.id === this.activeId);
    const i = stepIndex(cur, this.views.length, dir);
    const r = this.restore(i);
    if (!r.skipped.includes('xr session')) this.note(`View ${i + 1} of ${this.views.length}: ${this.views[i]!.name}`, true, 2500);
    return r;
  }

  // ---------------------------------------------------------------- play

  play(dwell?: number): void {
    if (this.views.length === 0) {
      this.note('No saved views to play.', true, 3000);
      return;
    }
    if (dwell !== undefined) this.dwell = Math.max(500, dwell);
    this.stop(false);
    const cur = this.views.findIndex((v) => v.id === this.activeId);
    this.playIndex = cur >= 0 ? cur - 1 : -1;
    const tick = (): void => {
      if (this.views.length === 0) return this.stop();
      this.playIndex = stepIndex(this.playIndex, this.views.length, 1);
      const i = this.playIndex;
      if (this.restore(i, true).skipped.includes('xr session')) return; // restore stopped the play
      this.app.showMessage(`Playing views: ${i + 1} of ${this.views.length}, ${this.views[i]!.name}. Press Escape to stop.`);
      this.playTimer = setTimeout(tick, (reducedMotion() ? 0 : VIEW_MOVE_MS) + this.dwell);
    };
    this.playTimer = setTimeout(tick, 0);
    this.render();
  }

  stop(say = true): void {
    if (!this.playTimer) return;
    clearTimeout(this.playTimer);
    this.playTimer = null;
    if (say) {
      this.app.showMessage(null);
      this.panel?.say('Stopped playing.');
    }
    this.render();
  }

  // ---------------------------------------------------------------- share, export, import

  shareUrl(i: number): string {
    const v = this.views[i]!;
    const enc = encodeViewShare(this.modelName, v, this.factory);
    return viewShareUrl({ origin: location.origin, pathname: location.pathname, search: location.search }, this.modelName, enc);
  }

  exportJson(withThumbs = true): string {
    return JSON.stringify(viewsDocument(this.modelName, this.views, withThumbs), null, 2) + '\n';
  }

  importViews(incoming: SavedView[], bad: string[] = []): { added: number; replaced: number; bad: string[] } {
    const r = mergeViews(this.views, incoming, this.deleted);
    if (r.added || r.replaced) this.commit(r.views);
    return { added: r.added, replaced: r.replaced, bad };
  }

  importJson(text: string): { added: number; replaced: number; bad: string[]; error?: string } {
    const p = parseViewsDocument(text);
    if (p.error) return { added: 0, replaced: 0, bad: p.bad, error: p.error };
    // An explicit import may bring back a view deleted earlier in the session.
    for (const v of p.views) this.deleted.delete(v.id);
    return this.importViews(p.views, p.bad);
  }
}

let ctl: ViewsController | null = null;
let pendingShare: { model?: string; view: SavedView } | null = null;
let firstModel = true;

function buildApi(c: ViewsController): ViewsApi {
  return {
    list: () => c.entries().map(rowOf),
    entries: (f) => filterEntries(c.entries(), { filter: f ?? 'all' }),
    withDrawings: () => filterEntries(c.entries(), { filter: 'drawings' }).map(rowOf),
    get filter() {
      return c.filterKind;
    },
    setFilter: (f) => {
      if (isViewFilter(f)) c.setFilter(f);
    },
    open: (f) => {
      if (f && isViewFilter(f)) c.setFilter(f);
      c.tab?.show();
    },
    drawOn: (key) => c.drawOnEntry(c.entry(key)),
    drawOnCurrent: (name) => {
      const set = c.saveWithDrawings(name);
      const ic = c.issues;
      if (ic) {
        ic.openSketch(set.id, { restore: false });
        ic.editSketch(set.id);
      } else c.mk?.setEditing(true);
      return set;
    },
    makeIssue: (key, o) => c.makeIssueOf(c.entry(key), o),
    get: (key) => {
      const i = findView(c.views, key);
      return i < 0 ? null : stripView(c.views[i]!);
    },
    save: (name) => c.save(name),
    restore: (key, opts) => {
      const i = findView(c.views, key);
      if (i >= 0) {
        const e = c.entries().find((x) => x.viewId === c.views[i]!.id);
        return e ? c.restoreEntry(e, opts?.animate ?? true) : c.restore(i, opts?.animate ?? true);
      }
      return c.restoreEntry(c.entry(key), opts?.animate ?? true);
    },
    update: (key) => c.update(c.index(key)),
    rename: (key, name) => {
      const i = c.index(key);
      c.commit(c.views.map((v, k) => (k === i ? { ...v, name: uniqueName(name, c.views, v.id), updated: new Date().toISOString() } : v)));
    },
    duplicate: (key) => {
      const i = c.index(key);
      c.commit(duplicateView(c.views, i));
      return c.views[i + 1]!;
    },
    remove: (key) => {
      const i = c.index(key);
      const v = c.views[i]!;
      c.deleted.add(v.id);
      if (c.activeId === v.id) c.activeId = null;
      c.commit(c.views.filter((_, k) => k !== i));
    },
    move: (from, to) => c.commit(moveView(c.views, from, to)),
    next: () => c.step(1),
    prev: () => c.step(-1),
    play: (ms) => c.play(ms),
    stop: () => c.stop(),
    get playing() {
      return c.playing;
    },
    get active() {
      return c.activeId;
    },
    shareUrl: (key) => c.shareUrl(c.index(key)),
    exportJson: (t) => c.exportJson(t),
    importJson: (text) => c.importJson(text),
    camera: () => {
      const v = captureView(c.vapp, 'x', { ortho: isPseudoOrtho() });
      return v.camera;
    },
    capture: (name) => {
      if (!c.app.loaded) throw new Error('No model loaded');
      return c.capture(name?.trim() || 'View');
    },
    restoreView: (view, opts) => c.restoreView(view, opts?.animate ?? true),
    shareUrlFor: (view) => {
      if (!c.app.loaded) return '';
      const enc = encodeViewShare(c.modelName, view, c.factory);
      return viewShareUrl({ origin: location.origin, pathname: location.pathname, search: location.search }, c.modelName, enc);
    },
    get lastRestore() {
      return c.lastRestore;
    },
  };
}

function rowOf(e: ViewEntry): ViewRow {
  return { id: e.id, name: e.name, summary: e.summary, hasThumb: !!e.thumb, note: e.note, drawings: e.drawings, hasDrawings: e.hasDrawings, sheet: e.sheet, set: e.setId ?? null, issue: e.issue ? { topic: e.issue.topic, title: e.issue.title } : null };
}

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

function buildPanel(c: ViewsController, api: ViewsApi): void {
  const note = (e: unknown): void => c.note(e instanceof Error ? e.message : String(e), false);
  const at = (i: number): ViewEntry => {
    const e = c.entries()[i];
    if (!e) throw new Error('No such view');
    return e;
  };
  const panel = new ViewsPanel({
    entries: () => c.entries(),
    activeKey: () => c.activeKey(),
    filter: () => c.filterKind,
    setFilter: (f) => c.setFilter(f),
    detailOpen: () => c.issues?.detail?.kind === 'view' && c.filterKind !== 'sheets',
    playing: () => c.playing,
    canIssue: () => !!c.issues,
    save: (name) => {
      try {
        api.save(name);
      } catch (e) {
        note(e);
      }
    },
    restore: (i) => {
      const e = at(i);
      c.stop(false);
      try {
        c.restoreEntry(e);
        // A view with a drawing layer opens its detail; a plain view just comes back.
        if (e.setId && !e.sheet && c.issues) c.issues.openSketch(e.setId, { restore: false });
      } catch (err) {
        note(err);
      }
    },
    update: (i) => {
      const e = at(i);
      try {
        if (e.viewId) c.update(c.index(e.viewId));
        if (e.setId && !e.sheet) c.mk?.updateView(e.setId);
      } catch (err) {
        note(err);
      }
    },
    rename: (i, name) => {
      const e = at(i);
      if (e.viewId) api.rename(e.viewId, name);
      if (e.setId) {
        c.mk?.renameSet(e.setId, name);
        c.render();
      }
    },
    duplicate: (i) => {
      const e = at(i);
      if (!e.viewId) return;
      api.duplicate(e.viewId);
      c.note(`Duplicated "${e.name}".`, false);
    },
    copyLink: (i) => {
      const e = at(i);
      let url = '';
      if (e.viewId) url = c.shareUrl(c.index(e.viewId));
      else {
        const set = c.mk?.get(e.id);
        url = set ? api.shareUrlFor(set.view) : '';
      }
      void copyText(url).then((ok) => c.note(ok ? `Link to "${e.name}" copied (${url.length} characters).` : 'Could not copy to the clipboard.', false));
    },
    drawOn: (i) => {
      void c.drawOnEntry(at(i)).catch(note);
    },
    drawCurrent: () => {
      const key = c.activeKey();
      const e = key ? c.entries().find((x) => x.key === key) : undefined;
      if (e) void c.drawOnEntry(e).catch(note);
      else {
        try {
          api.drawOnCurrent();
        } catch (err) {
          note(err);
        }
      }
    },
    makeIssue: (i) => {
      void (async () => {
        try {
          const set = await c.ensureSet(at(i));
          c.issues?.openSketch(set.id);
        } catch (e) {
          note(e);
        }
      })();
    },
    openIssue: (i) => {
      const e = at(i);
      if (e.issue) c.issues?.openIssue(e.issue.topic, { apply: false });
    },
    details: (i) => {
      const e = at(i);
      if (e.setId) c.issues?.openSketch(e.setId);
    },
    remove: (i) => {
      const e = at(i);
      if (e.setId && c.issues) {
        const r = c.issues.removeSketch(e.setId);
        if (r === 'confirm') c.issues.openSketch(e.setId, { restore: false }); // the detail asks first: the view is in an issue
        else c.note(`Deleted "${e.name}".`, false);
        return;
      }
      if (e.viewId) {
        api.remove(e.viewId);
        c.note(`Deleted "${e.name}".`, false);
      }
    },
    move: (from, to) => {
      const e = c.entries()[from];
      if (!e?.viewId) return;
      api.move(from, Math.min(to, c.views.length - 1));
    },
    togglePlay: () => (c.playing ? c.stop() : c.play()),
    exportFile: () => {
      if (c.views.length === 0) return c.note('No views to export.', false);
      download(`xray-views-${c.modelName}-${today()}.json`, c.exportJson());
    },
    importFile: (file) => {
      void file.text().then((text) => {
        const r = c.importJson(text);
        if (r.error) c.note(`Import failed: ${r.error}.`, false);
        else c.note(`Imported ${r.added} view${r.added === 1 ? '' : 's'}${r.replaced ? `, ${r.replaced} updated` : ''}${r.bad.length ? `; ${r.bad.length} skipped (${r.bad[0]})` : ''}.`, false);
      });
    },
    dwellMs: () => c.dwell,
    setDwellMs: (ms) => {
      c.dwell = ms;
    },
  });
  c.panel = panel;
  c.tab = addSidebarTab({ id: 'views', label: 'Views', pane: panel.root, helpKey: 'Sidebar/Views tab', onShow: () => panel.render() });
  if (!c.tab) {
    // A page without the sidebar: the actions and window.__xrayViews still work.
    c.panel = null;
    panel.hidePeek();
  }
}

export const viewsPlugin: AppPlugin = {
  name: 'views',

  install(app) {
    const c = new ViewsController(app);
    ctl = c;
    const api = buildApi(c);
    window.__xrayViews = api;
    buildPanel(c, api);

    registerAction({
      id: 'views.save',
      label: 'Save view',
      group: 'Views',
      keys: ['Ctrl+Shift+s'],
      description: 'Save the camera, cuts, modes, selection and hides as a named view (sidebar tab Views).',
      run: () => {
        try {
          const v = api.save();
          c.note(`Saved view "${v.name}". Shift+PageUp and Shift+PageDown step through the views.`, true, 3000);
        } catch (e) {
          c.note(e instanceof Error ? e.message : String(e), true, 4000);
        }
      },
    });
    registerAction({ id: 'views.next', label: 'Next saved view', group: 'Views', keys: ['Shift+PageDown'], run: () => void c.step(1) });
    registerAction({ id: 'views.prev', label: 'Previous saved view', group: 'Views', keys: ['Shift+PageUp'], run: () => void c.step(-1) });
    registerAction({ id: 'views.play', label: 'Play saved views', group: 'Views', keys: [], run: () => (c.playing ? c.stop() : c.play()) });
    registerAction({ id: 'views.open', label: 'Open the saved views', group: 'Views', keys: [], run: () => c.tab?.show() });

    registerParamSection('views', {
      share: false,
      // Without thumbnails (they are in the views export); absent when there are none.
      collect: () => (c.views.length ? c.views.map((v) => stripView(v, false, false)) : undefined),
      apply(value, bad, path) {
        const p = parseViewsDocument(value);
        if (p.error) {
          bad.push(path);
          return;
        }
        c.importViews(p.views);
        for (const b of p.bad) bad.push(`${path}${b}`);
      },
    });

    const enc = viewShareFromHash(location.hash);
    if (enc) {
      pendingShare = decodeViewShare(enc);
      if (!pendingShare) console.warn('views: could not decode the #view= fragment');
    }

    // Playing stops on Escape (the key is taken, so it does not also clear the selection) or a press on the canvas.
    window.addEventListener(
      'keydown',
      (e) => {
        if (e.key === 'Escape' && c.playing) {
          c.stop();
          e.preventDefault();
          e.stopPropagation();
        }
      },
      true,
    );
    app.canvas.addEventListener('pointerdown', () => c.stop());
  },

  onModel(app) {
    const c = ctl;
    if (!c) return;
    c.stop(false);
    c.modelName = app.modelName;
    if (!c.factory) c.factory = currentViewParams(app as unknown as ParamsApp);
    const stored = loadViews(c.store, app.modelName);
    if (stored.error) console.warn(`views: stored views of "${app.modelName}" not read: ${stored.error}`);
    c.views = stored.views;
    c.activeId = null;
    c.deleted.clear();
    if (firstModel) {
      firstModel = false;
      // A packed page: the views of the boot document join the stored ones (by id, newer wins), once: the ids
      // offered before are remembered per model, so a packed view the user deleted does not come back.
      const boot = bootConfig() as { views?: unknown };
      if (boot.views !== undefined) {
        const p = parseViewsDocument(boot.views);
        if (p.error) console.warn(`[xray-boot] views ignored: ${p.error}`);
        else {
          const r = mergePackedViews(c.views, p.views, loadPackedSeen(c.store, app.modelName));
          c.views = r.views;
          if (r.added || r.replaced) c.persist();
          savePackedSeen(c.store, app.modelName, r.seen);
          if (p.bad.length) console.warn(`[xray-boot] views skipped: ${p.bad.join('; ')}`);
        }
      }
    }
    c.render();

    const share = pendingShare;
    if (share) {
      pendingShare = null;
      try {
        const u = new URL(location.href);
        u.hash = hashWithoutView(u.hash);
        history.replaceState(null, '', u);
      } catch {
        /* ignore */
      }
      if (share.model && share.model !== app.modelName) {
        c.note(`Shared view "${share.view.name}" belongs to model "${share.model}"; "${app.modelName}" is loaded. Camera and elements may not match.`, true, 8000);
      }
      const r = c.restoreView(share.view, false);
      if (r.missing.length === 0) c.note(`Shared view "${share.view.name}" applied. Press Save view to keep it.`, true, 6000);
    }
  },
};

/** Open a view at boot (plugins/boot.ts, `window.__xrayBoot.openView`). Returns false when there is no such view. */
export function openBootView(key: string): boolean {
  const c = ctl;
  if (!c) return false;
  const i = findView(c.views, key);
  if (i < 0) return false;
  c.restore(i, false);
  return true;
}

/** The panel of the Views tab, for plugins that add a section to it (the fly-through). Null on a page without the sidebar. */
export function viewsPanel(): ViewsPanel | null {
  return ctl?.panel ?? null;
}

/**
 * The Issues plugin joins the Views tab: the drawings part of the tab (the detail of a view with drawings, the sheets, Open file,
 * Other models) is built from the issues controller, and the saved views learn which sets are theirs. Returns false without a Views tab.
 */
export function linkViews(ic: IssuesController): boolean {
  const c = ctl;
  if (!c) return false;
  c.issues = ic;
  ic.viewFilter = c.filterKind;
  const mk = ic.markup;
  ic.viewsHost = {
    savedOf: (setId) => {
      const v = c.savedOfSet(setId);
      return v ? { id: v.id, name: v.name } : null;
    },
    removeSaved: (id) => {
      if (c.views.some((v) => v.id === id)) window.__xrayViews?.remove(id);
    },
    saveCurrent: (name) => c.saveWithDrawings(name),
    renamed: (setId, title) => {
      const v = c.savedOfSet(setId);
      if (v && v.name !== title) c.commit(c.views.map((x) => (x.id === v.id ? { ...x, name: uniqueName(title, c.views, v.id), updated: new Date().toISOString() } : x)));
      else c.render();
    },
    updated: (setId) => {
      const v = c.savedOfSet(setId);
      const set = mk.get(setId);
      if (!v || !set) return;
      const now = new Date().toISOString();
      const fresh: SavedView = { ...JSON.parse(JSON.stringify(set.view)), id: v.id, name: v.name, created: v.created, updated: now, drawings: set.id };
      const thumb = set.thumb ?? v.thumb;
      if (thumb) fresh.thumb = thumb;
      c.commit(c.views.map((x) => (x.id === v.id ? fresh : x)));
    },
  };
  if (c.panel) {
    buildIssuesPanel(c.panel.drawings, ic, 'views');
    ic.onChange(() => {
      c.panel?.render();
    });
  }
  // A set that goes away leaves its saved view as a plain view.
  mk.onRemoved((set) => {
    if (c.views.some((v) => v.drawings === set.id)) c.commit(c.views.map((v) => { if (v.drawings !== set.id) return v; const { drawings: _gone, ...rest } = v; return rest; }));
  });
  mk.onChange(() => c.scheduleRender());
  return true;
}
