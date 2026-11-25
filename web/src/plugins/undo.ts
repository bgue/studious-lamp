// Undo plugin: one session-only stack for the view, the selection and the settings. Docs: docs-features/undo.md.
//
//   Ctrl/Cmd+Z undo, Ctrl/Cmd+Shift+Z or Ctrl+Y redo (actions undo.undo and undo.redo), and the Undo and Redo buttons of the gizmo.
//   window.__xrayUndo = { undo(), redo(), canUndo, canRedo, undoLabel, redoLabel, list(), clear(), settling }
//
// What it records (by watching, not by hooks, so a key, a button, a preset or a script is seen the same way):
//   - camera: when the camera has not moved for SETTLE_MS, one entry for the whole move (a wheel gesture, an orbit drag, a
//     cube click, home, fit, a saved view). Undo eases the camera back (a snap with "smooth moves" off).
//   - section: when the clip planes of the renderer change (a handle drag, the 3D · Plan · Section switch, a BCF viewpoint applied or
//     cleared) and have been still for SETTLE_MS, one entry. If the camera moved in the same step, it is the same entry: undo
//     puts back camera and planes together. The section controls of the panel that make planes belong here, not to the settings watch.
//   - selection: every change of the selection set, the box select included.
//   - settings: every change of a control of the parameter panel (lil-gui), before to after. A slider drag is one entry.
// What it ignores: what its own undo and redo apply, and everything for QUIET_MS after a model is installed (a model load,
// a share link, a boot preset). The stack is cleared when a model is installed. The markup tool has its own history
// (src/markup/history.ts) and the review walk its own keys: while either has the keyboard, Ctrl+Z is theirs.

import type { Controller } from 'lil-gui';
import type { AppPlugin, ViewerApp } from '../app';
import { registerAction, runAction } from '../input/actions';
import { cancelNavigationMoves, isPseudoOrtho, navSettings } from '../input/navigation';
import { cancelGizmoMove } from '../gizmo/camera';
import { showToast } from '../ui/keymapView';
import { UndoStack } from '../undo/stack';
import type { UndoEntry } from '../undo/stack';
import { describeViewChange, easeInOut, mixViewPose, viewPoseEqual } from '../undo/viewPose';
import type { ViewPose } from '../undo/viewPose';
import { ClipWatch, applyClip, composeStep, readClipState } from '../undo/clipWatch';
import type { ClipChange, ClipState } from '../undo/clipWatch';
import { cloneSection } from '../section/config';
import { bcfController } from './bcf';

export interface ViewEntry extends UndoEntry {
  kind: 'view';
  before: ViewPose;
  after: ViewPose;
  /** The clip planes changed in the same step (the 3D · Plan · Section switch, a BCF viewpoint). */
  clip?: ClipChange;
}
export interface SectionEntry extends UndoEntry {
  kind: 'section';
  before: ClipState;
  after: ClipState;
}
export interface SelectionEntry extends UndoEntry {
  kind: 'selection';
  before: number[];
  after: number[];
}
export interface SettingChange {
  ctrl: Controller;
  before: unknown;
  after: unknown;
}
export interface SettingEntry extends UndoEntry {
  kind: 'setting';
  changes: SettingChange[];
  /** The clip planes the settings made (a preset or view mode that turns the section on): one step with them. */
  clip?: ClipChange;
}

/** Planes that start changing this soon after a settings entry are that entry's doing (the section tool pushes them a frame later). */
const CLIP_FOLLOWS_SETTINGS_MS = 600;
export type Entry = ViewEntry | SectionEntry | SelectionEntry | SettingEntry;

export interface UndoApi {
  undo(): boolean;
  redo(): boolean;
  readonly canUndo: boolean;
  readonly canRedo: boolean;
  readonly undoLabel: string | null;
  readonly redoLabel: string | null;
  /** The entries, oldest first: kind and label. `redo` lists the undone ones, the next redo last. */
  list(): { undo: Array<{ kind: string; label: string }>; redo: Array<{ kind: string; label: string }> };
  clear(): void;
  /** True while a camera or clip plane move is still waiting to be recorded (smokes wait for false before they act). */
  readonly settling: boolean;
}

declare global {
  interface Window {
    __xrayUndo?: UndoApi;
  }
}

/** The camera counts as settled after this long without a move: a wheel gesture or a drag is one entry. */
export const SETTLE_MS = 400;
/** Slow frames (a phone, a big model) stretch the wait: the camera is seen once per frame. At most this long. */
const SETTLE_MAX_MS = 1000;
/** After a model is installed, changes are baseline, not history. */
export const QUIET_MS = 1500;
/** A camera change below this fraction of the distance to the target is not recorded. */
const NEGLIGIBLE = 3e-3;
/** The panel is read this often, in ms. */
const POLL_MS = 100;
/** Easing time of a camera undo, ms. */
const EASE_MS = 240;

const stack = new UndoStack<Entry>({
  cap: 100,
  coalesceMs: 600,
  merge(prev, next) {
    if (prev.kind !== 'setting' || next.kind !== 'setting') return next;
    const a = prev.changes[0]!;
    const b = next.changes[0]!;
    if (Object.is(a.before, b.after)) return null; // the slider came back to where it started
    return { ...prev, at: next.at, changes: [{ ctrl: a.ctrl, before: a.before, after: b.after }] };
  },
});

let appRef: ViewerApp | null = null;
let quietUntil = 0;
// Camera watch.
let committed: ViewPose | null = null; // the last settled view
let lastSeen: ViewPose | null = null;
let lastMoveAt = 0;
let moving = false;
/** Frames left in which the clip planes are only re-read (after an undo the section tool pushes its planes on the next frame). */
let clipHold = 0;
let ease: { from: ViewPose; to: ViewPose; start: number; lastPos: [number, number, number] } | null = null;
// Selection watch.
let selRef: Set<number> | null = null;
let selCommitted: number[] = [];
// Section watch.
const clipWatch = new ClipWatch();
// Settings watch.
const seen = new Map<Controller, unknown>();
let lastPoll = 0;
const ctrlIds = new WeakMap<Controller, number>();
let nextCtrlId = 1;

// ---------------------------------------------------------------- state readers

function readPose(app: ViewerApp): ViewPose {
  const { camera, controls } = app.renderer;
  return {
    position: [camera.position.x, camera.position.y, camera.position.z],
    target: [controls.target.x, controls.target.y, controls.target.z],
    up: [camera.up.x, camera.up.y, camera.up.z],
    fov: camera.fov,
    ortho: isPseudoOrtho(),
  };
}

function writePose(app: ViewerApp, p: ViewPose): void {
  const { camera, controls } = app.renderer;
  const dist = Math.hypot(p.position[0] - p.target[0], p.position[1] - p.target[1], p.position[2] - p.target[2]);
  // A view from before a limit changed (home resets them) must stay reachable.
  if (controls.maxDistance > 0 && Number.isFinite(controls.maxDistance) && dist > controls.maxDistance) controls.maxDistance = dist * 1.05;
  if (controls.minDistance > dist) controls.minDistance = dist * 0.5;
  if (camera.far < dist * 1.5) {
    camera.far = dist * 2;
    camera.updateProjectionMatrix();
  }
  camera.up.set(p.up[0], p.up[1], p.up[2]);
  camera.position.set(p.position[0], p.position[1], p.position[2]);
  controls.target.set(p.target[0], p.target[1], p.target[2]);
  controls.update();
}

const sameIds = (a: readonly number[], b: ReadonlySet<number>): boolean => {
  if (a.length !== b.size) return false;
  for (const id of a) if (!b.has(id)) return false;
  return true;
};

function controllers(app: ViewerApp): Controller[] {
  return (app.panel?.controllersRecursive() ?? []) as Controller[];
}

/** The controls of the Section folder that make clip planes: the section watch records those (with the box corners), as one step. */
const SECTION_PLANE_CONTROLS = ['enabled', 'margin', 'axis', 'offset', 'flip', 'caps', 'capColor'];
function isSectionPlaneControl(c: Controller): boolean {
  return (c.parent as unknown as { _title?: string } | undefined)?._title === 'Section' && SECTION_PLANE_CONTROLS.includes(c.property);
}

/** Controls whose value is a setting: not buttons, not read-only status lines, not the model picker. */
function watched(c: Controller): boolean {
  const v = c.getValue();
  if (typeof v === 'function') return false;
  if (c.property === 'model') return false;
  if (isSectionPlaneControl(c)) return false;
  return !(c as unknown as { _disabled?: boolean })._disabled;
}

function nameOf(c: Controller): string {
  const n = (c as unknown as { _name?: string })._name;
  return (n && n.trim() !== '' ? n : c.property).replace(/\s*\([A-Za-z0-9+]{1,3}\)\s*$/, '');
}

function baselineSettings(app: ViewerApp): void {
  seen.clear();
  for (const c of controllers(app)) if (watched(c)) seen.set(c, c.getValue());
}

function readClip(app: ViewerApp): ClipState {
  const sec = window.__xraySection;
  return readClipState(app.renderer.getClipPlanes(), sec?.config ?? null, (sec?.foreignPlanes() ?? 0) > 0);
}

function baseline(app: ViewerApp): void {
  committed = lastSeen = readPose(app);
  clipWatch.baseline(readClip(app), app.renderer.clipVersion);
  moving = false;
  selRef = app.controller.selection;
  selCommitted = [...selRef];
  baselineSettings(app);
}

// ---------------------------------------------------------------- recording

function now(): number {
  return performance.now();
}

/** Camera and clip planes have been still: record what changed as one entry. */
function commitChanges(app: ViewerApp, t: number): void {
  const pose = readPose(app);
  moving = false;
  lastSeen = pose;
  // A drift under 0.3 % of the distance (the tail of an orbit's damping) is not a step to undo; `committed` stays put, so
  // drift that adds up still becomes an entry once it is big enough.
  const cam = committed && !viewPoseEqual(committed, pose, NEGLIGIBLE) ? committed : null;
  const since = clipWatch.since;
  const clip = clipWatch.settle(() => readClip(app));
  if (!cam && clip && since !== null) {
    const undo = stack.list().undo;
    const top = undo[undo.length - 1];
    if (top && top.kind === 'setting' && !top.clip && since >= top.at && since - top.at <= CLIP_FOLLOWS_SETTINGS_MS) {
      top.clip = clip;
      top.label = `${top.label} and section`;
      return;
    }
  }
  const step = composeStep(cam ? { before: cam, after: pose, label: describeViewChange(cam, pose) } : null, clip);
  if (step) stack.push({ ...step, at: t });
  if (cam) committed = pose;
}

function settleFor(app: ViewerApp): number {
  return Math.min(SETTLE_MAX_MS, Math.max(SETTLE_MS, app.stats.frameMs * 2.5));
}

/** See what moved since the last look: the camera, and the clip planes of the renderer. */
function detect(app: ViewerApp, t: number): void {
  const pose = readPose(app);
  if (lastSeen && !viewPoseEqual(lastSeen, pose)) {
    lastSeen = pose;
    lastMoveAt = t;
    moving = true;
  }
  clipWatch.observe(() => readClip(app), app.renderer.clipVersion, t);
}

function watchView(app: ViewerApp, t: number): void {
  if (ease) return;
  const pose = readPose(app);
  if (!committed || !lastSeen) {
    committed = lastSeen = pose;
    return;
  }
  detect(app, t);
  const last = Math.max(moving ? lastMoveAt : -Infinity, clipWatch.lastChangeAt ?? -Infinity);
  if ((moving || clipWatch.changing) && t - last >= settleFor(app)) commitChanges(app, t);
}

/**
 * A camera move that is still settling (the tail of an orbit's damping, a wheel gesture) happened BEFORE the selection or setting
 * change that is about to be recorded: write it first, so the list keeps the order of events and the newest entry is the click.
 * Without this the move was recorded up to a second later, on top of the click ("Undo orbit" where "Undo selection" belongs).
 */
function commitPendingMove(app: ViewerApp, t: number): void {
  if (moving) commitChanges(app, t);
}

function watchSelection(app: ViewerApp, t: number): void {
  const sel = app.controller.selection;
  if (sel === selRef) return;
  selRef = sel;
  if (sameIds(selCommitted, sel)) return;
  commitPendingMove(app, t);
  const after = [...sel];
  stack.push({ kind: 'selection', label: 'selection', at: t, before: selCommitted, after });
  selCommitted = after;
}

function watchSettings(app: ViewerApp, t: number): void {
  const changes: SettingChange[] = [];
  const all = controllers(app);
  const present = new Set(all);
  for (const c of all) {
    if (!watched(c)) continue;
    const v = c.getValue();
    if (!seen.has(c)) {
      seen.set(c, v); // a control built after the start: baseline
      continue;
    }
    const was = seen.get(c);
    if (Object.is(was, v)) continue;
    seen.set(c, v);
    changes.push({ ctrl: c, before: was, after: v });
  }
  for (const c of seen.keys()) if (!present.has(c)) seen.delete(c);
  if (changes.length === 0) return;
  commitPendingMove(app, t);
  if (changes.length === 1) {
    const c = changes[0]!.ctrl;
    let id = ctrlIds.get(c);
    if (id === undefined) ctrlIds.set(c, (id = nextCtrlId++));
    stack.push({ kind: 'setting', label: nameOf(c), key: `set:${id}`, at: t, changes });
  } else {
    stack.push({ kind: 'setting', label: `${changes.length} settings`, at: t, changes });
  }
}

/** Record what has happened since the last frame, without waiting for the camera to settle. */
function flush(app: ViewerApp): void {
  const t = now();
  if (ease) endEase(app);
  const wasMoving = moving;
  detect(app, t);
  if (wasMoving || clipWatch.changing) commitChanges(app, t);
  watchSelection(app, t);
  watchSettings(app, t);
}

// ---------------------------------------------------------------- applying

function endEase(app: ViewerApp): void {
  if (!ease) return;
  const to = ease.to;
  ease = null;
  writePose(app, to);
  committed = lastSeen = readPose(app);
}

function startEase(app: ViewerApp, to: ViewPose): void {
  cancelGizmoMove();
  cancelNavigationMoves();
  (window as unknown as { __cinematic?: { cancelFlight?(): void } }).__cinematic?.cancelFlight?.();
  endEase(app);
  const from = readPose(app);
  // The projection toggle keeps the framing; the pose is eased from there.
  if (from.ortho !== to.ortho) {
    runAction(app, 'view.projection');
    cancelNavigationMoves();
  }
  const start = readPose(app);
  if (!navSettings.smoothMoves || viewPoseEqual(start, to)) {
    writePose(app, to);
    committed = lastSeen = readPose(app);
    return;
  }
  ease = { from: start, to, start: Number.NaN, lastPos: [...start.position] };
}

function easeFrame(app: ViewerApp, t: number): boolean {
  const e = ease;
  if (!e) return false;
  const cam = app.renderer.camera.position;
  const tol = 1e-2 * Math.max(1e-3, Math.hypot(e.to.position[0] - e.to.target[0], e.to.position[1] - e.to.target[1], e.to.position[2] - e.to.target[2]));
  if (Math.hypot(cam.x - e.lastPos[0], cam.y - e.lastPos[1], cam.z - e.lastPos[2]) > tol) {
    // Something else moved the camera (a pointer, another tool): let go; what follows is a new move.
    ease = null;
    committed = lastSeen = readPose(app);
    return false;
  }
  if (Number.isNaN(e.start)) e.start = t;
  const k = (t - e.start) / EASE_MS;
  if (k >= 1) {
    endEase(app);
    return true;
  }
  const p = mixViewPose(e.from, e.to, easeInOut(Math.max(0, k)));
  writePose(app, p);
  e.lastPos = [app.renderer.camera.position.x, app.renderer.camera.position.y, app.renderer.camera.position.z];
  return true;
}

function setSelection(app: ViewerApp, ids: number[]): void {
  app.selectIds(ids);
  selRef = app.controller.selection;
  selCommitted = [...selRef];
}

function applySetting(app: ViewerApp, e: SettingEntry, dir: 'before' | 'after'): void {
  for (const ch of e.changes) {
    if (!ch.ctrl.domElement.isConnected) continue;
    try {
      ch.ctrl.setValue(dir === 'before' ? ch.before : ch.after);
    } catch (err) {
      console.error('[undo] could not apply', err);
    }
  }
  if (e.clip) putClip(app, dir === 'before' ? e.clip.before : e.clip.after);
  baselineSettings(app);
  quietUntil = Math.max(quietUntil, now() + 250); // a control that moves another one is not a new change
}

/** Put the clip planes (and the section tool's settings) back to a state. */
function putClip(app: ViewerApp, state: ClipState): void {
  const sec = window.__xraySection;
  const r = app.renderer;
  applyClip(
    {
      ...(sec ? { setConfig: (cfg) => { sec.set(cloneSection(cfg)); } } : {}),
      wantsPlanes: (cfg) => cfg.box.enabled || cfg.plane.enabled,
      setPlanes: (planes, cap) => r.setClipPlanes(planes, { cap, ...(sec ? { capColor: sec.config.capColor } : {}) }),
    },
    state,
  );
  // Planes that are not the section tool's came from a viewpoint or the Plan and Section switch: a viewpoint that is applied keeps
  // them as its own (so that Clear viewpoint still removes them).
  if (state.foreign) bcfController()?.reclaimClip();
  clipWatch.baseline(readClip(app), r.clipVersion);
  clipHold = 3;
  baselineSettings(app);
  quietUntil = Math.max(quietUntil, now() + 250); // the section tool pushes its planes on the next frame: not a new change
}

function apply(app: ViewerApp, e: Entry, dir: 'before' | 'after'): void {
  if (e.kind === 'view') {
    startEase(app, dir === 'before' ? e.before : e.after);
    if (e.clip) putClip(app, dir === 'before' ? e.clip.before : e.clip.after);
  } else if (e.kind === 'section') putClip(app, dir === 'before' ? e.before : e.after);
  else if (e.kind === 'selection') setSelection(app, dir === 'before' ? e.before : e.after);
  else applySetting(app, e, dir);
}

function describe(verb: string, e: Entry): string {
  return `${verb} ${e.label}`;
}

export function undoNow(): boolean {
  const app = appRef;
  if (!app?.controller) return false;
  flush(app);
  const e = stack.undo((x) => apply(app, x, 'before'));
  if (e) showToast(describe('Undid', e));
  else showToast('Nothing to undo');
  return !!e;
}

export function redoNow(): boolean {
  const app = appRef;
  if (!app?.controller) return false;
  flush(app);
  const e = stack.redo((x) => apply(app, x, 'after'));
  if (e) showToast(describe('Redid', e));
  else showToast('Nothing to redo');
  return !!e;
}

/** What the gizmo buttons show. */
export function undoState(): { canUndo: boolean; canRedo: boolean; undoLabel: string | null; redoLabel: string | null } {
  return { canUndo: stack.canUndo, canRedo: stack.canRedo, undoLabel: stack.undoLabel, redoLabel: stack.redoLabel };
}

export function onUndoChange(cb: () => void): () => void {
  return stack.onChange(cb);
}

/** A sketch is being edited (the drawing toolbar is up, or a drawing tool is on): the markup history owns Ctrl+Z. */
function markupHasKeys(): boolean {
  const m = window.__xrayMarkup;
  if (m && (m.editing || m.tool !== 'select')) return true;
  const bar = document.getElementById('markup-float');
  return !!bar && bar.style.display !== 'none' && bar.style.display !== '';
}

/** The keyboard focus is inside the classification review walk panel. */
function reviewHasFocus(): boolean {
  const a = document.activeElement;
  return !!a && typeof a.closest === 'function' && !!a.closest('.xrw');
}

const keysFree = (): boolean => !markupHasKeys() && !reviewHasFocus();

export const undoPlugin: AppPlugin = {
  name: 'undo',

  install(app) {
    appRef = app;
    const api: UndoApi = {
      undo: undoNow,
      redo: redoNow,
      get canUndo() {
        return stack.canUndo;
      },
      get canRedo() {
        return stack.canRedo;
      },
      get undoLabel() {
        return stack.undoLabel;
      },
      get redoLabel() {
        return stack.redoLabel;
      },
      list() {
        const l = stack.list();
        const m = (e: Entry): { kind: string; label: string } => ({ kind: e.kind, label: e.label });
        return { undo: l.undo.map(m), redo: l.redo.map(m) };
      },
      clear: () => stack.clear(),
      get settling() {
        return moving || clipWatch.changing || ease !== null;
      },
    };
    window.__xrayUndo = api;
    registerAction({
      id: 'undo.undo',
      label: 'Undo: view, selection or setting',
      group: 'Edit',
      keys: ['Ctrl+z', 'Meta+z'],
      description: 'Step back one camera move, selection or setting change. The markup tool has its own undo.',
      enabled: keysFree,
      run: () => void undoNow(),
    });
    registerAction({
      id: 'undo.redo',
      label: 'Redo: view, selection or setting',
      group: 'Edit',
      keys: ['Ctrl+Shift+z', 'Meta+Shift+z', 'Ctrl+y'],
      description: 'Step forward again after an undo.',
      enabled: keysFree,
      run: () => void redoNow(),
    });
    // A pointer or the wheel on the canvas takes the camera back from a running undo move.
    app.canvas.addEventListener('pointerdown', () => {
      if (ease) {
        ease = null;
        committed = lastSeen = readPose(app);
      }
    });
    app.canvas.addEventListener('wheel', () => {
      if (ease) {
        ease = null;
        committed = lastSeen = readPose(app);
      }
    }, { passive: true });
    quietUntil = now() + QUIET_MS;
  },

  onModel(app) {
    stack.clear();
    ease = null;
    clipHold = 0;
    quietUntil = now() + QUIET_MS;
    baseline(app);
  },

  onFrame(app, t) {
    if (!app.controller) return;
    const moved = easeFrame(app, t);
    const clock = now();
    if (clock < quietUntil) {
      baseline(app); // loading: what changes now is the starting state
      return moved;
    }
    if (clipHold > 0) {
      clipHold--;
      clipWatch.baseline(readClip(app), app.renderer.clipVersion);
    }
    watchView(app, clock);
    watchSelection(app, clock);
    if (clock - lastPoll >= POLL_MS) {
      lastPoll = clock;
      watchSettings(app, clock);
    }
    return moved;
  },
};
