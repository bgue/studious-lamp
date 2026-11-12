// Undo plugin: one session-only stack for the view, the selection and the settings. Docs: docs-features/undo.md.
//
//   Ctrl/Cmd+Z undo, Ctrl/Cmd+Shift+Z or Ctrl+Y redo (actions undo.undo and undo.redo), and the Undo and Redo buttons of the gizmo.
//   window.__xrayUndo = { undo(), redo(), canUndo, canRedo, undoLabel, redoLabel, list(), clear() }
//
// What it records (by watching, not by hooks, so a key, a button, a preset or a script is seen the same way):
//   - camera: when the camera has not moved for SETTLE_MS, one entry for the whole move (a wheel gesture, an orbit drag, a
//     cube click, home, fit, a saved view). Undo eases the camera back (a snap with "smooth moves" off).
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

export interface ViewEntry extends UndoEntry {
  kind: 'view';
  before: ViewPose;
  after: ViewPose;
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
}
export type Entry = ViewEntry | SelectionEntry | SettingEntry;

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
let ease: { from: ViewPose; to: ViewPose; start: number; lastPos: [number, number, number] } | null = null;
// Selection watch.
let selRef: Set<number> | null = null;
let selCommitted: number[] = [];
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

/** Controls whose value is a setting: not buttons, not read-only status lines, not the model picker. */
function watched(c: Controller): boolean {
  const v = c.getValue();
  if (typeof v === 'function') return false;
  if (c.property === 'model') return false;
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

function baseline(app: ViewerApp): void {
  committed = lastSeen = readPose(app);
  moving = false;
  selRef = app.controller.selection;
  selCommitted = [...selRef];
  baselineSettings(app);
}

// ---------------------------------------------------------------- recording

function now(): number {
  return performance.now();
}

function commitView(app: ViewerApp, t: number): void {
  const pose = readPose(app);
  moving = false;
  lastSeen = pose;
  // A drift under 0.3 % of the distance (the tail of an orbit's damping) is not a step to undo; `committed` stays put, so
  // drift that adds up still becomes an entry once it is big enough.
  if (!committed || viewPoseEqual(committed, pose, NEGLIGIBLE)) return;
  stack.push({ kind: 'view', label: describeViewChange(committed, pose), at: t, before: committed, after: pose });
  committed = pose;
}

function watchView(app: ViewerApp, t: number): void {
  if (ease) return;
  const pose = readPose(app);
  if (!committed || !lastSeen) {
    committed = lastSeen = pose;
    return;
  }
  if (!viewPoseEqual(lastSeen, pose)) {
    lastSeen = pose;
    lastMoveAt = t;
    moving = true;
  } else if (moving && t - lastMoveAt >= Math.min(SETTLE_MAX_MS, Math.max(SETTLE_MS, app.stats.frameMs * 2.5))) commitView(app, t);
}

function watchSelection(app: ViewerApp, t: number): void {
  const sel = app.controller.selection;
  if (sel === selRef) return;
  selRef = sel;
  if (sameIds(selCommitted, sel)) return;
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
  if (moving) commitView(app, t);
  else watchView(app, t);
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
  baselineSettings(app);
  quietUntil = Math.max(quietUntil, now() + 250); // a control that moves another one is not a new change
}

function apply(app: ViewerApp, e: Entry, dir: 'before' | 'after'): void {
  if (e.kind === 'view') startEase(app, dir === 'before' ? e.before : e.after);
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

/** The markup tool is drawing or its drawer is open: its own undo owns Ctrl+Z. */
function markupHasKeys(): boolean {
  const m = window.__xrayMarkup;
  if (m && m.tool !== 'select') return true;
  return !!document.querySelector('[data-tool="markup"].open');
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
    watchView(app, clock);
    watchSelection(app, clock);
    if (clock - lastPoll >= POLL_MS) {
      lastPoll = clock;
      watchSettings(app, clock);
    }
    return moved;
  },
};
