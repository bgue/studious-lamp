// Fly-through plugin: keyframes that are full saved-view states plus timing, played by the score player.
//
//   - Section "Fly-through" in the Views tab (src/views/flythroughPanel.ts): fly-through list, transport, timeline, keyframe cards
//     and the keyframe editor. While the tab is open with the section expanded the camera path is drawn in 3D (src/anim/overlay.ts).
//   - The player (src/anim/player.ts, viewerHost.ts) is registered with setScorePlayer for every other source of scores.
//   - Keys while it plays: Space pauses and resumes, Left and Right go to the previous and next keyframe, Escape stops. A press
//     or a wheel turn on the canvas stops it too (the camera stays where the person took it).
//   - Persistence: localStorage `xray.flythroughs.<identity key of the model>`; the old `xray.flythrough.<modelName>` keyframes are
//     imported once as the fly-through "Imported". See docs-features/flythrough.md.
//   - window.__xrayFlythrough for scripts and smoke tests; window.__cinematic.play / record / keys keep working.

import { Box3, Vector3 } from 'three';
import type { AppPlugin, ViewerApp } from '../app';
import { registerAction, getAction } from '../input/actions';
import { computeFlyView } from '../cinematic/flyto';
import type { Keyframe } from '../cinematic/flythrough';
import { loadedIdentity, identityKey } from '../markup/scope';
import { defaultSetsFor, isCriteria, loadSets, unionBounds } from '../selectionSets';
import { runQuery } from '../query';
import { FlyStore } from '../anim/store';
import type { KeyframePatch } from '../anim/store';
import { compileFlyThrough, defaultSpeed, keyframePose, keyframeTimes, newKeyframe } from '../anim/flythrough';
import type { FlyKeyframe, FlyThrough, Timing } from '../anim/flythrough';
import { ScorePlayer } from '../anim/player';
import { ViewerScoreHost } from '../anim/viewerHost';
import { PathOverlay } from '../anim/overlay';
import { setScorePlayer } from '../anim/score';
import type { PlayOptions, Score } from '../anim/score';
import { FlythroughPanel } from '../views/flythroughPanel';
import type { FlyHost, FlyState } from '../views/flythroughPanel';
import { viewsPanel } from './views';
import type { SavedView } from '../views/model';

export interface FlyPlayArgs {
  /** Start at this keyframe (0-based). */
  fromKeyframe?: number;
  /** Start at this time (seconds). */
  from?: number;
  restore?: boolean;
  onEnd?: () => void;
}

export interface FlythroughApi {
  list(): Array<{ id: string; name: string; keyframes: number; duration: number }>;
  active(): string | null;
  setActive(key: string): void;
  create(name?: string): string;
  rename(key: string, name: string): void;
  duplicate(key: string): string | null;
  removeFlythrough(key: string): void;
  setOptions(o: Partial<Pick<FlyThrough, 'timing' | 'speed' | 'segmentS' | 'lookAtSelection' | 'loop'>>): void;
  /** Keyframes of the active fly-through (without the thumbnails and the params snapshots). */
  keyframes(): Array<{ id: string; name: string; travel: number; hold: number; ease: boolean; fade: boolean; fadeFraction: number; switchAt: string; caption?: { title?: string; text?: string }; selection: number; hasThumb: boolean; camera: SavedView['camera'] }>;
  /** Add the current view (or a saved view by id or name) as a keyframe at the end or at `at`. */
  add(opts?: { view?: string; at?: number; name?: string } & KeyframePatch): number;
  update(index: number, patch: KeyframePatch & { fromCurrent?: boolean }): boolean;
  remove(index: number): boolean;
  move(from: number, to: number): boolean;
  clear(): void;
  buildFromViews(): number;
  buildFromSets(): number;
  /** Start a keyframe fly-through (active, or by key). False without keyframes. */
  play(args?: FlyPlayArgs & { key?: string }): boolean;
  pause(): void;
  resume(): void;
  stop(): void;
  /** Stop because a person took over the camera: it stays. */
  userStop(): void;
  seek(t: number): void;
  /** Go to the previous or next keyframe while playing. */
  step(dir: 1 | -1): void;
  record(): boolean;
  state(): FlyState & { keyframe: number };
  /** The score of the fly-through (active, or by key). */
  compile(key?: string): Score;
  timing(key?: string): Timing;
  exportJson(all?: boolean): string;
  importJson(text: string): { ok: boolean; added: number };
  /** The keyframes in the old shape of window.__cinematic.keys. */
  legacyKeys(): Keyframe[];
  openTab(): void;
  /** The camera-path overlay is drawn now. */
  readonly pathVisible: boolean;
  readonly store: FlyStore;
}

declare global {
  interface Window {
    __xrayFlythrough?: FlythroughApi;
  }
}

interface ViewsLike {
  list(): Array<{ id: string; name: string }>;
  get(key: string): SavedView | null;
  capture(name?: string): SavedView;
}
const viewsApi = (): ViewsLike | undefined => (window as unknown as { __xrayViews?: ViewsLike }).__xrayViews;

function storage(): Storage | null {
  try {
    const s = window.localStorage;
    s.getItem('xray.probe');
    return s;
  } catch {
    return null;
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

function isTyping(t: EventTarget | null): boolean {
  const e = t as HTMLElement | null;
  if (!e || !e.tagName) return false;
  return e.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(e.tagName);
}

class FlythroughController {
  readonly store: FlyStore;
  readonly host: ViewerScoreHost;
  readonly player: ScorePlayer;
  panel: FlythroughPanel | null = null;
  overlay: PathOverlay | null = null;
  private lastVisCheck = 0;
  private msgTimer: ReturnType<typeof setTimeout> | null = null;
  private suppressedForPlay = false;

  constructor(readonly app: ViewerApp) {
    this.store = new FlyStore(storage());
    this.host = new ViewerScoreHost(app);
    this.player = new ScorePlayer(this.host);
  }

  get model() {
    return this.app.controller.model;
  }

  note(text: string, ms = 4000): void {
    this.panel?.say(text);
    this.app.showMessage(text);
    if (this.msgTimer) clearTimeout(this.msgTimer);
    this.msgTimer = setTimeout(() => this.app.showMessage(null), ms);
  }

  ctx() {
    return {
      selectionCenter: (gids: readonly string[]): [number, number, number] | null => {
        const ids: number[] = [];
        for (const g of gids) {
          const id = this.model.byGlobalId.get(g);
          if (id !== undefined) ids.push(id);
        }
        const b = unionBounds(this.model, ids);
        return b ? [(b[0] + b[3]) / 2, (b[1] + b[4]) / 2, (b[2] + b[5]) / 2] : null;
      },
    };
  }

  flyBy(key?: string): FlyThrough | null {
    return key === undefined ? this.store.active : this.store.find(key);
  }

  timing(f: FlyThrough | null = this.store.active): Timing {
    if (!f || f.keyframes.length === 0) return { arrive: [], depart: [], travel: [], total: 0 };
    return keyframeTimes(f, this.ctx());
  }

  compile(f: FlyThrough | null = this.store.active): Score {
    if (!f) throw new Error('No fly-through');
    return compileFlyThrough(f, this.ctx());
  }

  // ---------------------------------------------------------------- capture

  /** The current view as a saved-view state, with a thumbnail that shows no overlay. */
  captureCurrent(name: string): SavedView {
    const views = viewsApi();
    if (!views) throw new Error('The saved views are not available');
    this.overlay?.suppress();
    try {
      return views.capture(name);
    } finally {
      this.overlay?.release();
    }
  }

  addCurrent(at?: number, patch: KeyframePatch = {}): number {
    const f = this.store.ensureActive();
    const name = `Keyframe ${f.keyframes.length + 1}`;
    const v = this.captureCurrent(name);
    const k = this.store.add(f, v, at, { name });
    if (!k) throw new Error('Too many keyframes');
    const i = f.keyframes.indexOf(k);
    if (Object.keys(patch).length) this.store.update(f, i, patch);
    this.panel?.select(i);
    return i;
  }

  addSaved(key: string, at?: number): number {
    const v = viewsApi()?.get(key);
    if (!v) throw new Error(`No saved view "${key}"`);
    const f = this.store.ensureActive();
    const k = this.store.add(f, v, at, { name: v.name, viewId: v.id });
    if (!k) throw new Error('Too many keyframes');
    const i = f.keyframes.indexOf(k);
    this.panel?.select(i);
    return i;
  }

  buildFromViews(): number {
    const views = viewsApi();
    if (!views) return 0;
    const list = views.list();
    if (list.length === 0) {
      this.note('No saved views to build keyframes from.');
      return 0;
    }
    const f = this.store.ensureActive();
    const keys: FlyKeyframe[] = [];
    for (const it of list) {
      const v = views.get(it.id);
      if (v) keys.push(newKeyframe(v, { name: v.name, viewId: v.id }));
    }
    this.store.replaceAll(f, keys);
    this.panel?.select(0);
    return keys.length;
  }

  /** One keyframe per stored selection set, the camera framed on the set with the fly-to fit maths. */
  buildFromSets(): number {
    const app = this.app;
    const model = app.loaded?.model;
    const views = viewsApi();
    if (!model || !views) return 0;
    let stored = null;
    try {
      const st = storage();
      stored = st ? loadSets(st, app.modelName) : null;
    } catch {
      stored = null;
    }
    const sets = stored && stored.length > 0 ? stored : defaultSetsFor(model, app.modelName);
    const base = views.capture('Base');
    const { camera, controls } = app.renderer;
    const keys: FlyKeyframe[] = [];
    for (const set of sets) {
      const gids = isCriteria(set) ? runQuery(model, set.query).ids.map((i) => model.elements[i]!.globalId) : [...set.globalIds];
      const ids: number[] = [];
      for (const g of gids) {
        const id = model.byGlobalId.get(g);
        if (id !== undefined) ids.push(id);
      }
      const ub = unionBounds(model, ids);
      if (!ub) continue;
      const fv = computeFlyView(new Box3(new Vector3(ub[0], ub[1], ub[2]), new Vector3(ub[3], ub[4], ub[5])), {
        position: camera.position,
        target: controls.target,
        fovDeg: camera.fov,
        aspect: camera.aspect,
        minDistance: controls.minDistance,
        maxDistance: controls.maxDistance,
      });
      const view: SavedView = {
        id: `set-${keys.length}`,
        name: set.name,
        created: base.created,
        updated: base.updated,
        camera: { position: fv.position.toArray() as [number, number, number], target: fv.target.toArray() as [number, number, number], up: base.camera.up, fov: base.camera.fov, ortho: base.camera.ortho },
        selection: gids,
        params: {},
      };
      keys.push(newKeyframe(view, { name: set.name }));
    }
    if (keys.length === 0) {
      this.note('No selection sets to build keyframes from.');
      return 0;
    }
    this.store.replaceAll(this.store.ensureActive(), keys);
    this.panel?.select(0);
    return keys.length;
  }

  updateFromCurrent(index: number): boolean {
    const f = this.store.active;
    const k = f?.keyframes[index];
    if (!f || !k) return false;
    const v = this.captureCurrent(k.name);
    this.store.setView(f, index, v);
    this.note(`Updated "${k.name}" from the current view.`);
    return true;
  }

  goTo(index: number): void {
    const f = this.store.active;
    const k = f?.keyframes[index];
    if (!f || !k) return;
    if (this.player.playing) {
      this.seekKeyframe(index);
      return;
    }
    const pose = keyframePose(k, f.lookAtSelection, this.ctx());
    this.host.writePose(pose, true);
    // The look of the keyframe (its settings, hides, selection) comes back with a restore of the saved-view state.
    const views = (window as unknown as { __xrayViews?: { restoreView(v: SavedView, o?: { animate?: boolean }): unknown } }).__xrayViews;
    views?.restoreView(k.view, { animate: false });
    this.app.renderer.markDirty();
  }

  // ---------------------------------------------------------------- play

  play(args: FlyPlayArgs & { key?: string } = {}): boolean {
    const f = this.flyBy(args.key);
    if (!f || f.keyframes.length === 0) {
      this.note('Fly-through: add keyframes first.');
      return false;
    }
    if (!this.app.loaded) return false;
    const score = this.compile(f);
    const tm = this.timing(f);
    const opts: PlayOptions = {
      restore: args.restore !== false,
      onEnd: () => {
        this.afterPlay();
        args.onEnd?.();
      },
    };
    const from = args.from ?? (args.fromKeyframe !== undefined ? tm.arrive[args.fromKeyframe] : undefined);
    if (from !== undefined && from > 0) opts.from = from;
    if (this.player.playing) this.player.stop();
    this.overlay?.suppress();
    this.suppressedForPlay = true;
    const ok = this.player.play(score, opts);
    if (!ok) this.afterPlay();
    this.panel?.render();
    return ok;
  }

  private afterPlay(): void {
    if (this.suppressedForPlay) {
      this.suppressedForPlay = false;
      this.overlay?.release();
    }
    this.panel?.render();
  }

  stop(): void {
    this.player.stop();
  }

  userStop(): void {
    if (this.player.playing) this.player.stopKeepingCamera();
  }

  seekKeyframe(i: number): void {
    const tm = this.timing();
    const t = tm.arrive[i];
    if (t !== undefined) this.player.seek(t);
  }

  step(dir: 1 | -1): void {
    const tm = this.timing();
    if (tm.arrive.length === 0) return;
    const t = this.player.time;
    let cur = 0;
    for (let i = 0; i < tm.arrive.length; i++) if (tm.arrive[i]! <= t + 1e-6) cur = i;
    let target = cur + dir;
    // Left inside a keyframe's move goes back to the keyframe that began it.
    if (dir < 0 && t > tm.arrive[cur]! + 0.6) target = cur;
    target = Math.min(Math.max(target, 0), tm.arrive.length - 1);
    this.seekKeyframe(target);
  }

  record(): boolean {
    const f = this.store.active;
    if (!f || f.keyframes.length === 0) {
      this.note('Fly-through: add keyframes first.');
      return false;
    }
    const cin = (window as unknown as { __cinematic?: { record(): boolean } }).__cinematic;
    return cin ? cin.record() : false;
  }

  frame(now: number): boolean {
    if (this.player.playing) {
      this.player.tick(now);
      if (this.player.paused) this.host.applyFades();
      this.panel?.tick();
      return true;
    }
    if (now - this.lastVisCheck > 250) {
      this.lastVisCheck = now;
      this.updateOverlayVisible();
    }
    return false;
  }

  /** The path shows while the Views tab is open and the section is expanded. */
  updateOverlayVisible(): void {
    const p = this.panel;
    if (!p || !this.overlay) return;
    const visible = p.expanded && p.root.offsetParent !== null && !this.player.playing;
    this.overlay.setWanted(visible);
  }

  refreshOverlay(): void {
    const f = this.store.active;
    const o = this.overlay;
    if (!o) return;
    if (!f || f.keyframes.length === 0) return o.set([], 1, -1);
    const b = this.app.loaded?.geometry.totalBounds();
    const diag = b && !b.isEmpty() ? b.min.distanceTo(b.max) : 10;
    o.set(f.keyframes.map((k) => keyframePose(k, f.lookAtSelection, this.ctx())), Math.max(diag * 0.012, 0.05), this.panel?.selectedIndex ?? -1);
  }
}

let ctl: FlythroughController | null = null;

function buildApi(c: FlythroughController): FlythroughApi {
  const st = c.store;
  const need = (): FlyThrough => {
    const f = st.active;
    if (!f) throw new Error('No fly-through');
    return f;
  };
  return {
    list: () => st.list.map((f) => ({ id: f.id, name: f.name, keyframes: f.keyframes.length, duration: c.timing(f).total })),
    active: () => st.active?.id ?? null,
    setActive: (key) => {
      const f = st.find(key);
      if (f) st.setActive(f.id);
    },
    create: (name) => st.create(name).id,
    rename: (key, name) => {
      const f = st.find(key);
      if (f) st.rename(f.id, name);
    },
    duplicate: (key) => {
      const f = st.find(key);
      return f ? (st.duplicate(f.id)?.id ?? null) : null;
    },
    removeFlythrough: (key) => {
      const f = st.find(key);
      if (f) st.remove(f.id);
    },
    setOptions: (o) => st.setOptions(st.ensureActive().id, o),
    keyframes: () =>
      (st.active?.keyframes ?? []).map((k) => ({
        id: k.id,
        name: k.name,
        travel: 0,
        hold: k.hold,
        ease: k.ease,
        fade: k.fade,
        fadeFraction: k.fadeFraction,
        switchAt: k.switchAt,
        ...(k.caption ? { caption: { ...k.caption } } : {}),
        selection: k.view.selection.length,
        hasThumb: !!k.view.thumb,
        camera: JSON.parse(JSON.stringify(k.view.camera)) as SavedView['camera'],
      })).map((k, i) => ({ ...k, travel: c.timing().travel[i] ?? 0 })),
    add: (opts = {}) => {
      const { view, at, name, ...patch } = opts;
      const i = view ? c.addSaved(view, at) : c.addCurrent(at, patch);
      if (name) st.update(need(), i, { name });
      if (view && Object.keys(patch).length) st.update(need(), i, patch);
      return i;
    },
    update: (index, patch) => {
      const f = st.active;
      if (!f) return false;
      const { fromCurrent, ...rest } = patch;
      if (fromCurrent) c.updateFromCurrent(index);
      return Object.keys(rest).length ? st.update(f, index, rest) : !!f.keyframes[index];
    },
    remove: (i) => {
      const f = st.active;
      return f ? st.removeKeyframe(f, i) : false;
    },
    move: (from, to) => {
      const f = st.active;
      return f ? st.move(f, from, to) : false;
    },
    clear: () => {
      const f = st.active;
      if (f) st.clear(f);
    },
    buildFromViews: () => c.buildFromViews(),
    buildFromSets: () => c.buildFromSets(),
    play: (args) => c.play(args),
    pause: () => c.player.pause(),
    resume: () => c.player.resume(),
    stop: () => c.stop(),
    userStop: () => c.userStop(),
    seek: (t) => c.player.seek(t),
    step: (d) => c.step(d),
    record: () => c.record(),
    state: () => {
      const tm = c.timing();
      let kf = -1;
      if (c.player.playing) for (let i = 0; i < tm.arrive.length; i++) if (tm.arrive[i]! <= c.player.time + 1e-6) kf = i;
      return { playing: c.player.playing, paused: c.player.paused, recording: (window as unknown as { __cinematic?: { recording?: boolean } }).__cinematic?.recording === true, time: c.player.time, duration: c.player.playing ? c.player.duration : tm.total, keyframe: kf };
    },
    compile: (key) => {
      const f = key === undefined ? st.active : st.find(key);
      if (!f) throw new Error('No fly-through');
      return c.compile(f);
    },
    timing: (key) => c.timing(key === undefined ? st.active : st.find(key)),
    exportJson: (all) => st.exportDoc(all === true),
    importJson: (text) => {
      const n = st.importDoc(text);
      return { ok: n > 0, added: n };
    },
    legacyKeys: () =>
      (st.active?.keyframes ?? []).map((k) => ({
        position: [...k.view.camera.position] as [number, number, number],
        target: [...k.view.camera.target] as [number, number, number],
        selection: [...k.view.selection],
        toggles: {},
        name: k.name,
      })),
    openTab: () => void getAction('views.open')?.run(c.app),
    get pathVisible() {
      return c.overlay?.visible === true;
    },
    store: st,
  };
}

export const flythroughPlugin: AppPlugin = {
  name: 'flythrough',

  install(app) {
    const c = new FlythroughController(app);
    ctl = c;
    setScorePlayer(c.player);
    const api = buildApi(c);
    window.__xrayFlythrough = api;
    c.overlay = new PathOverlay(app.renderer.scene, () => app.renderer.markDirty());

    const host: FlyHost = {
      list: () => c.store.list,
      active: () => c.store.active,
      setActive: (id) => c.store.setActive(id),
      create: () => {
        const f = c.store.create();
        c.note(`New fly-through "${f.name}". Add keyframes below.`);
      },
      rename: (name) => {
        const f = c.store.active;
        if (f) c.store.rename(f.id, name);
      },
      duplicate: () => {
        const f = c.store.active;
        if (f) c.store.duplicate(f.id);
      },
      remove: () => {
        const f = c.store.active;
        if (f) {
          c.note(`Deleted "${f.name}".`);
          c.store.remove(f.id);
        }
      },
      exportFile: () => {
        const f = c.store.active;
        if (!f) return c.note('No fly-through to export.');
        download(`xray-flythrough-${app.modelName}-${new Date().toISOString().slice(0, 10)}.json`, c.store.exportDoc(false) + '\n');
      },
      importFile: (file) => {
        void file.text().then((t) => {
          const r = api.importJson(t);
          c.note(r.ok ? `Imported ${r.added} fly-through${r.added === 1 ? '' : 's'}.` : 'Import failed: not a fly-through file.');
        });
      },
      timing: () => c.timing(),
      state: () => api.state(),
      savedViews: () => viewsApi()?.list() ?? [],
      addCurrent: () => {
        try {
          const i = c.addCurrent();
          c.note(`Added keyframe ${i + 1}.`);
        } catch (e) {
          c.note(e instanceof Error ? e.message : String(e));
        }
      },
      addSaved: (id) => {
        try {
          c.addSaved(id);
        } catch (e) {
          c.note(e instanceof Error ? e.message : String(e));
        }
      },
      buildFromViews: () => {
        const n = c.buildFromViews();
        if (n) c.note(`Built ${n} keyframe${n === 1 ? '' : 's'} from the saved views.`);
      },
      buildFromSets: () => {
        const n = c.buildFromSets();
        if (n) c.note(`Built ${n} keyframe${n === 1 ? '' : 's'} from the selection sets.`);
      },
      update: (i, patch) => void api.update(i, patch),
      updateFromCurrent: (i) => void c.updateFromCurrent(i),
      insertAfter: (i) => {
        try {
          c.addCurrent(i + 1);
        } catch (e) {
          c.note(e instanceof Error ? e.message : String(e));
        }
      },
      goTo: (i) => c.goTo(i),
      removeKeyframe: (i) => void api.remove(i),
      move: (from, to) => void api.move(from, to),
      setOptions: (o) => c.store.setOptions(c.store.ensureActive().id, o),
      play: (from) => void c.play(from !== undefined ? { fromKeyframe: from } : {}),
      pause: () => {
        c.player.pause();
        c.panel?.render();
      },
      resume: () => {
        c.player.resume();
        c.panel?.render();
      },
      stop: () => c.stop(),
      record: () => void c.record(),
      seekTime: (t) => {
        if (c.player.playing) c.player.seek(t);
        else c.play({ from: t });
      },
      onExpanded: () => c.updateOverlayVisible(),
    };

    const vp = viewsPanel();
    if (vp) {
      c.panel = new FlythroughPanel(host);
      vp.addSection(c.panel.root);
      c.store.onChange(() => {
        c.panel?.render();
        c.refreshOverlay();
      });
      c.panel.render();
    }

    registerAction({
      id: 'flythrough.play',
      label: 'Play fly-through',
      group: 'Views',
      keys: [],
      description: 'Play the active fly-through of the Views tab, or stop it when it plays.',
      run: () => (c.player.playing ? c.stop() : void c.play()),
    });
    registerAction({
      id: 'flythrough.add',
      label: 'Add fly-through keyframe',
      group: 'Views',
      keys: [],
      description: 'Add the current view as a keyframe at the end of the active fly-through.',
      run: () => {
        try {
          c.addCurrent();
        } catch (e) {
          c.note(e instanceof Error ? e.message : String(e));
        }
      },
    });

    // Space, Left, Right and Escape while it plays. Capture phase: they do not reach the viewer's own keys.
    window.addEventListener(
      'keydown',
      (e) => {
        if (!c.player.playing || isTyping(e.target) || e.ctrlKey || e.metaKey || e.altKey) return;
        let handled = true;
        if (e.key === 'Escape') c.stop();
        else if (e.key === ' ' || e.code === 'Space') {
          if (c.player.paused) c.player.resume();
          else c.player.pause();
          c.panel?.render();
        } else if (e.key === 'ArrowRight') c.step(1);
        else if (e.key === 'ArrowLeft') c.step(-1);
        else handled = false;
        if (handled) {
          e.preventDefault();
          e.stopPropagation();
        }
      },
      true,
    );
    app.canvas.addEventListener('pointerdown', () => c.userStop());
    app.canvas.addEventListener('wheel', () => c.userStop(), { passive: true });
  },

  onModel(app) {
    const c = ctl;
    if (!c) return;
    if (c.player.playing) c.player.abort();
    const ident = loadedIdentity(app as never);
    const b = app.loaded?.geometry.totalBounds();
    c.store.defaultSpeed = defaultSpeed(b && !b.isEmpty() ? b.min.distanceTo(b.max) : 0);
    const r = c.store.load(identityKey(ident), app.modelName, app.renderer.camera.fov);
    if (r.migrated) c.note('Imported the earlier keyframes of this model as the fly-through "Imported".');
    c.panel?.render();
    c.refreshOverlay();
  },

  onFrame(_app, now) {
    return ctl ? ctl.frame(now) : false;
  },
};

export function getFlythrough(): FlythroughController | null {
  return ctl;
}
