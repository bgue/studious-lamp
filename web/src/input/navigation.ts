// Keyboard camera navigation: orbit, pan, fly, zoom steps, standard views, framing, storey stepping,
// selection cycling and the view history. The maths (pure, tested in tests/keymap-*.test.ts) is separate from the
// actions, which read and write app.renderer.camera / app.renderer.controls.

import { Box3, Sphere, Spherical, Vector3 } from 'three';
import type { ViewerApp } from '../app';
import type { SceneModel, ElementId } from '../types';
import { Flight, computeFlyView } from '../cinematic/flyto';
import type { FlyOptions, FlyView } from '../cinematic/flyto';
import { easeInOutCubic } from '../cinematic/easing';
import { registerAction } from './actions';
import type { HoldMods } from './actions';
import { showToast } from '../ui/keymapView';
import {
  eyeTarget,
  flyKeysEnabled,
  parseNavStyle,
  turnLook,
  walkMove,
  walkSpeedFactor,
  DEFAULT_EYE_HEIGHT,
  blocksWalk,
  collideMove,
  parseEyeHeight,
  standingSpot,
  stepWalkStorey,
  walkTargetDistance,
} from './walk';
import type { FloorLevel, NavStyle } from './walk';
import { storeyFloors } from '../xr/field';

// ---------------------------------------------------------------------------- settings

export interface NavSettings {
  /** Master switch for the Navigation and Views keys. */
  enabled: boolean;
  /** Orbit rate in degrees per second. */
  orbitSpeed: number;
  /** Pan rate as a multiple of 0.5 screen heights per second. */
  panSpeed: number;
  /** Fly rate as a multiple of 0.2 model diagonals per second. */
  moveSpeed: number;
  invertVertical: boolean;
  smoothMoves: boolean;
  /** 'bim' (default): BIM-app mouse and keys, w a s d q e only in Walk mode. 'game': w a s d q e always fly, middle drag zooms. */
  style: NavStyle;
  /** Walk mode: eye height above the floor, metres (the model units). Per viewer, not in params. */
  eyeHeight: number;
  /** Walk mode: stop short of walls (off by default). */
  walkCollision: boolean;
}

export const NAV_STORAGE_KEY = 'xray.keynav';
export const navSettings: NavSettings = { enabled: true, orbitSpeed: 90, panSpeed: 1, moveSpeed: 1, invertVertical: false, smoothMoves: true, style: 'bim', eyeHeight: DEFAULT_EYE_HEIGHT, walkCollision: false };
const styleListeners = new Set<() => void>();

/** Change the navigation style and tell the listeners (the pointer mapping, the cheat sheet). Not stored: see saveNavSettings. */
export function setNavStyle(style: NavStyle): void {
  if (navSettings.style === style) return;
  navSettings.style = style;
  for (const l of styleListeners) l();
}

export function onNavStyleChange(cb: () => void): () => void {
  styleListeners.add(cb);
  return () => styleListeners.delete(cb);
}

export function loadNavSettings(storage: { getItem(k: string): string | null } | null): void {
  try {
    const v = JSON.parse(storage?.getItem(NAV_STORAGE_KEY) ?? 'null') as Partial<NavSettings> | null;
    if (!v || typeof v !== 'object') return;
    if (typeof v.enabled === 'boolean') navSettings.enabled = v.enabled;
    if (typeof v.invertVertical === 'boolean') navSettings.invertVertical = v.invertVertical;
    if (typeof v.smoothMoves === 'boolean') navSettings.smoothMoves = v.smoothMoves;
    if (typeof v.walkCollision === 'boolean') navSettings.walkCollision = v.walkCollision;
    const eh = parseEyeHeight(v.eyeHeight);
    if (eh !== null) navSettings.eyeHeight = eh;
    const style = parseNavStyle(v.style);
    if (style && style !== navSettings.style) {
      navSettings.style = style;
      for (const l of styleListeners) l();
    }
    for (const k of ['orbitSpeed', 'panSpeed', 'moveSpeed'] as const) {
      const n = v[k];
      if (typeof n === 'number' && Number.isFinite(n) && n > 0) navSettings[k] = n;
    }
  } catch {
    /* corrupt or unavailable: keep the defaults */
  }
}

export function saveNavSettings(storage: { setItem(k: string, v: string): void } | null): void {
  try {
    storage?.setItem(NAV_STORAGE_KEY, JSON.stringify(navSettings));
  } catch {
    /* ignore */
  }
}

/** Ctrl held = slow. */
export const SLOW_FACTOR = 0.25;
/** A zoom step moves the camera 15 % of the way to the target (or away from it by the inverse). */
export const ZOOM_STEP = 0.85;
export const VIEW_MOVE_MS = 400;
export const HISTORY_LIMIT = 50;
/** Field of view of the pseudo-orthographic projection, degrees. */
export const ORTHO_FOV = 2;

// ---------------------------------------------------------------------------- pure maths

export type ViewKind = 'front' | 'back' | 'right' | 'left' | 'top' | 'bottom' | 'iso';

/** Unit vector from the framed object to the camera. Viewer space is Y up; IFC "front" (looking north) is +Z. */
export function viewDirection(kind: ViewKind): Vector3 {
  switch (kind) {
    case 'front': return new Vector3(0, 0, 1);
    case 'back': return new Vector3(0, 0, -1);
    case 'right': return new Vector3(1, 0, 0);
    case 'left': return new Vector3(-1, 0, 0);
    case 'top': return new Vector3(0, 1, 0);
    case 'bottom': return new Vector3(0, -1, 0);
    case 'iso': return new Vector3(1, 1, 1).normalize();
  }
}

/** Rotate a camera offset (camera minus target) by yaw about the up axis and pitch towards the pole. Y up. */
export function orbitOffset(offset: Vector3, yaw: number, pitch: number): Vector3 {
  const s = new Spherical().setFromVector3(offset);
  s.theta += yaw;
  s.phi = Math.min(Math.PI - 0.01, Math.max(0.01, s.phi + pitch));
  return new Vector3().setFromSpherical(s);
}

/** Azimuth of the camera about the target, radians (what ArrowLeft/Right change). */
export function yawOf(offset: Vector3): number {
  return Math.atan2(offset.x, offset.z);
}

/** Distance that keeps the apparent size of the target when the field of view changes. */
export function dollyForFov(distance: number, fromFovDeg: number, toFovDeg: number): number {
  const a = Math.tan((fromFovDeg * Math.PI) / 360);
  const b = Math.tan((toFovDeg * Math.PI) / 360);
  return (distance * a) / b;
}

export interface Level {
  id: number;
  name: string;
  /** Viewer-space height the camera target moves to. */
  y: number;
}

function median(v: number[]): number {
  const s = [...v].sort((a, b) => a - b);
  const n = s.length;
  return n === 0 ? 0 : n % 2 ? s[(n - 1) >> 1]! : (s[n / 2 - 1]! + s[n / 2]!) / 2;
}

/** Storeys in elevation order with the height of each: the median centre height of its elements. Storeys without elements are left out. */
export function storeyLevels(model: Pick<SceneModel, 'storeys' | 'elements'>): Level[] {
  const ys = new Map<number, number[]>();
  for (const e of model.elements) {
    if (e.storey === null || e.storey === undefined) continue;
    const list = ys.get(e.storey) ?? [];
    list.push((e.bounds[1] + e.bounds[4]) / 2);
    ys.set(e.storey, list);
  }
  const out: Level[] = [];
  for (const s of [...model.storeys].sort((a, b) => a.elevation - b.elevation || a.id - b.id)) {
    const list = ys.get(s.id);
    if (list && list.length) out.push({ id: s.id, name: s.name, y: median(list) });
  }
  return out.sort((a, b) => a.y - b.y);
}

/** The next level above (dir 1) or below (dir -1) height `y`; null at the end of the stack. */
export function stepStorey(levels: readonly Level[], y: number, dir: 1 | -1, eps = 1e-3): Level | null {
  if (dir > 0) return levels.find((l) => l.y > y + eps) ?? null;
  for (let i = levels.length - 1; i >= 0; i--) if (levels[i]!.y < y - eps) return levels[i]!;
  return null;
}

/** The order in which Tab visits the selected elements. */
export function tabOrder(ids: Iterable<ElementId>): ElementId[] {
  return [...ids].sort((a, b) => a - b);
}

/** Next index when cycling `n` items, starting before the first (-1). Wraps. */
export function stepCycle(index: number, n: number, dir: 1 | -1): number {
  if (n <= 0) return -1;
  if (index < 0) return dir > 0 ? 0 : n - 1;
  return (index + dir + n) % n;
}

export interface Pose {
  position: [number, number, number];
  target: [number, number, number];
}

export function poseDistance(a: Pose, b: Pose): number {
  let s = 0;
  for (let i = 0; i < 3; i++) s += (a.position[i]! - b.position[i]!) ** 2 + (a.target[i]! - b.target[i]!) ** 2;
  return Math.sqrt(s);
}

/**
 * Back/forward stacks of camera poses. push() is called before a discrete camera move with the pose it leaves.
 * Pushes with the same `tag` within `coalesceMs` of each other keep only the first (a run of zoom steps is one entry).
 */
export class ViewHistory {
  private back: Pose[] = [];
  private fwd: Pose[] = [];
  private lastTag = '';
  private lastAt = -Infinity;

  constructor(private readonly limit = HISTORY_LIMIT, private readonly coalesceMs = 700) {}

  get backCount(): number {
    return this.back.length;
  }
  get forwardCount(): number {
    return this.fwd.length;
  }

  push(pose: Pose, now = 0, tag = ''): void {
    if (tag && tag === this.lastTag && now - this.lastAt < this.coalesceMs) {
      this.lastAt = now;
      return;
    }
    this.lastTag = tag;
    this.lastAt = now;
    const top = this.back[this.back.length - 1];
    if (!top || poseDistance(top, pose) > 1e-6) this.back.push(clonePose(pose));
    if (this.back.length > this.limit) this.back.shift();
    this.fwd = [];
  }

  /** Go back one pose. `current` is kept for forward(). Null when there is nothing to go back to. */
  goBack(current: Pose): Pose | null {
    const p = this.back.pop();
    if (!p) return null;
    this.fwd.push(clonePose(current));
    this.lastTag = '';
    return p;
  }

  goForward(current: Pose): Pose | null {
    const p = this.fwd.pop();
    if (!p) return null;
    this.back.push(clonePose(current));
    this.lastTag = '';
    return p;
  }

  clear(): void {
    this.back = [];
    this.fwd = [];
    this.lastTag = '';
  }
}

function clonePose(p: Pose): Pose {
  return { position: [...p.position], target: [...p.target] };
}

// ---------------------------------------------------------------------------- app glue

export const history = new ViewHistory();

interface Ortho {
  fov: number;
  far: number;
  minDistance: number;
  maxDistance: number;
}
let ortho: Ortho | null = null;

const boundsCache = new WeakMap<object, Box3>();
let tabCursor = { key: '', index: -1 };
let tween: { flight: Flight; last: FlyView } | null = null;
let storeyCache: { model: SceneModel; levels: Level[] } | null = null;

function modelBox(app: ViewerApp): Box3 {
  const l = app.loaded;
  if (!l) return new Box3();
  let b = boundsCache.get(l);
  if (!b) {
    b = l.geometry.totalBounds();
    boundsCache.set(l, b);
  }
  return b;
}

function modelDiagonal(app: ViewerApp): number {
  const b = modelBox(app);
  return b.isEmpty() ? 10 : Math.max(b.min.distanceTo(b.max), 0.5);
}

function boxOfIds(app: ViewerApp, ids: Iterable<ElementId>): Box3 {
  const box = new Box3();
  const els = app.loaded?.model.elements;
  if (!els) return box;
  for (const id of ids) {
    const b = els[id]?.bounds;
    if (b) box.union(new Box3(new Vector3(b[0], b[1], b[2]), new Vector3(b[3], b[4], b[5])));
  }
  return box;
}

/** The box a view or frame command works on: the selection, else the whole model. */
function workBox(app: ViewerApp): Box3 {
  const sel = app.controller?.selection;
  if (sel && sel.size > 0) {
    const b = boxOfIds(app, sel);
    if (!b.isEmpty()) return b;
  }
  return modelBox(app);
}

export function currentPose(app: ViewerApp): Pose {
  const { camera, controls } = app.renderer;
  return {
    position: [camera.position.x, camera.position.y, camera.position.z],
    target: [controls.target.x, controls.target.y, controls.target.z],
  };
}

function nowMs(): number {
  return typeof performance !== 'undefined' ? performance.now() : Date.now();
}

/** Remember the current pose before a discrete move. */
export function pushHistory(app: ViewerApp, tag = ''): void {
  history.push(currentPose(app), nowMs(), tag);
}

function cinematic(): { flyTo(box: Box3, opts?: FlyOptions): void; cancelFlight?(): void } | null {
  const w = typeof window !== 'undefined' ? (window as unknown as { __cinematic?: { flyTo(box: Box3, opts?: FlyOptions): void; cancelFlight?(): void } }) : null;
  return w?.__cinematic ?? null;
}

function cancelMoves(): void {
  tween = null;
  cinematic()?.cancelFlight?.();
}

function writeView(app: ViewerApp, v: FlyView): void {
  const { camera, controls } = app.renderer;
  camera.position.copy(v.position);
  controls.target.copy(v.target);
  controls.update();
}

function ensureReach(app: ViewerApp, v: FlyView, radius: number): void {
  const { camera, controls } = app.renderer;
  const dist = v.position.distanceTo(v.target);
  if (camera.far < dist + radius * 2) {
    camera.far = dist + radius * 2;
    camera.updateProjectionMatrix();
  }
  if (controls.minDistance > dist) controls.minDistance = dist * 0.5;
  if (controls.maxDistance > 0 && controls.maxDistance < dist * 1.05) controls.maxDistance = dist * 1.05;
}

function startTween(app: ViewerApp, to: FlyView, ms: number): void {
  const { camera, controls } = app.renderer;
  const from: FlyView = { position: camera.position.clone(), target: controls.target.clone() };
  cinematic()?.cancelFlight?.();
  tween = { flight: new Flight(from, to, ms, easeInOutCubic), last: { position: from.position.clone(), target: from.target.clone() } };
}

/** Per-frame driver of the fallback tween. Called from the keymap plugin's onFrame. */
export function navigationFrame(app: ViewerApp, now: number): void {
  const t = tween;
  if (!t) return;
  const { camera, controls } = app.renderer;
  const tol = 1e-4 * Math.max(1, camera.position.distanceTo(controls.target));
  if (camera.position.distanceTo(t.last.position) > tol || controls.target.distanceTo(t.last.target) > tol) {
    tween = null; // something else moved the camera: let go
    return;
  }
  const out: FlyView = { position: new Vector3(), target: new Vector3() };
  const done = t.flight.sample(now, out);
  writeView(app, out);
  t.last = { position: camera.position.clone(), target: controls.target.clone() };
  if (done) tween = null;
}

/** Move the camera to a pose, eased when `smooth moves` is on. */
export function moveToPose(app: ViewerApp, pose: Pose): void {
  const to: FlyView = { position: new Vector3(...pose.position), target: new Vector3(...pose.target) };
  cancelMoves();
  if (navSettings.smoothMoves) startTween(app, to, VIEW_MOVE_MS);
  else writeView(app, to);
}

/** Frame a box: through the cinematic fly-to when present, else an eased tween, else at once. Records the history. */
export function moveToBox(app: ViewerApp, box: Box3, opts: FlyOptions & { tag?: string } = {}): void {
  if (box.isEmpty()) return;
  pushHistory(app, opts.tag ?? '');
  const { camera, controls } = app.renderer;
  const fly: FlyOptions = { margin: opts.margin, direction: opts.direction, durationMs: VIEW_MOVE_MS, ...(opts.minDistance !== undefined ? { minDistance: opts.minDistance } : {}) };
  const cin = cinematic();
  if (navSettings.smoothMoves && cin) {
    tween = null;
    cin.flyTo(box, fly);
    return;
  }
  const view = computeFlyView(
    box,
    { position: camera.position, target: controls.target, fovDeg: camera.fov, aspect: camera.aspect, minDistance: controls.minDistance, maxDistance: controls.maxDistance },
    fly,
  );
  cancelMoves();
  ensureReach(app, view, box.getBoundingSphere(new Sphere()).radius);
  if (navSettings.smoothMoves) startTween(app, view, VIEW_MOVE_MS);
  else writeView(app, view);
}

/** Select-and-fly helper for a double click: frame one element with the fly-to framing (records the view history). */
export function flyToElement(app: ViewerApp, id: ElementId): void {
  const box = boxOfIds(app, [id]);
  if (!box.isEmpty()) moveToBox(app, box, { tag: 'dblclick' });
}

/** Frame the whole model (the Home key). */
export function frameAllNow(app: ViewerApp): void {
  pushHistory(app);
  cancelMoves();
  app.frameAll();
}

// ---------------------------------------------------------------------------- actions

const navEnabled = (): boolean => navSettings.enabled;

function viewAction(id: string, label: string, kind: ViewKind, keys: string[]): void {
  registerAction({
    id,
    label,
    group: 'Views',
    keys,
    description: `Look at the selection, or the whole model, from the ${kind === 'iso' ? 'isometric corner' : kind}.`,
    enabled: navEnabled,
    run(app) {
      moveToBox(app, workBox(app), { direction: viewDirection(kind), margin: 1.2 });
      showToast(label);
    },
  });
}

function holdAction(
  id: string,
  label: string,
  group: string,
  keys: string[],
  hold: (app: ViewerApp, dt: number, mods: HoldMods) => void,
  description?: string,
  opts: { enabled?: (app: ViewerApp) => boolean; modifiers?: Array<'ctrl' | 'shift' | 'alt' | 'meta'> } = {},
): void {
  registerAction({
    id,
    label,
    group,
    keys,
    description,
    modifiers: opts.modifiers ?? ['ctrl'],
    enabled: opts.enabled ?? navEnabled,
    run() {
      /* held action: see hold() */
    },
    hold(app, dt, mods) {
      cancelMoves();
      hold(app, dt, mods ?? { ctrl: false, shift: false, alt: false, meta: false });
    },
  });
}

const slow = (m: HoldMods): number => (m.ctrl ? SLOW_FACTOR : 1);

function orbitBy(app: ViewerApp, yaw: number, pitch: number): void {
  const { camera, controls } = app.renderer;
  const off = camera.position.clone().sub(controls.target);
  if (off.lengthSq() < 1e-12) return;
  camera.position.copy(controls.target).add(orbitOffset(off, yaw, pitch));
  controls.update();
}

function panBy(app: ViewerApp, right: number, up: number): void {
  const { camera, controls } = app.renderer;
  const dist = camera.position.distanceTo(controls.target);
  const height = 2 * dist * Math.tan((camera.fov * Math.PI) / 360);
  const r = new Vector3(1, 0, 0).applyQuaternion(camera.quaternion);
  const u = new Vector3(0, 1, 0).applyQuaternion(camera.quaternion);
  const d = r.multiplyScalar(right * height).addScaledVector(u, up * height);
  camera.position.add(d);
  controls.target.add(d);
  controls.update();
}

function flyBy(app: ViewerApp, fwd: number, right: number, up: number): void {
  const { camera, controls } = app.renderer;
  const f = controls.target.clone().sub(camera.position);
  if (f.lengthSq() < 1e-12) return;
  f.normalize();
  const r = new Vector3(1, 0, 0).applyQuaternion(camera.quaternion);
  const d = f.multiplyScalar(fwd).addScaledVector(r, right).addScaledVector(new Vector3(0, 1, 0), up);
  camera.position.add(d);
  controls.target.add(d);
  controls.update();
}

// ---------------------------------------------------------------------------- Walk mode

/** Walk mode: a per-viewer state (never in params, a share link, a saved view, a preset or a packed page). */
const walkState = { active: false, dist: 1 };
const walkListeners = new Set<() => void>();

export function isWalking(): boolean {
  return walkState.active;
}

export function onWalkChange(cb: () => void): () => void {
  walkListeners.add(cb);
  return () => walkListeners.delete(cb);
}

/** True while a fly-through, a script or a 4D film plays (they own the camera). */
export function playerPlaying(): boolean {
  try {
    const w = typeof window !== 'undefined' ? (window as unknown as { __xrayFlythrough?: { state?(): { playing?: boolean } } }) : null;
    return w?.__xrayFlythrough?.state?.().playing === true;
  } catch {
    return false;
  }
}

/** The screen-up direction of the camera: the horizontal forward of a view that looks straight down or up. */
function screenUp(app: ViewerApp): Vector3 {
  return new Vector3(0, 1, 0).applyQuaternion(app.renderer.camera.quaternion);
}

function lookOf(app: ViewerApp): Vector3 {
  return app.renderer.camera.getWorldDirection(new Vector3());
}

/** Put the orbit target a fixed distance in front of the eye, so leaving Walk mode leaves a sane orbit. */
function syncWalkTarget(app: ViewerApp, look: Vector3): void {
  const { camera, controls } = app.renderer;
  controls.target.copy(eyeTarget(camera.position, look, walkState.dist));
  controls.update();
}

/** Enter or leave Walk mode. False when it cannot be entered (no model, keys off, a film plays). */
export function setWalking(app: ViewerApp, on: boolean): boolean {
  if (on === walkState.active) return true;
  const { camera, controls } = app.renderer;
  if (on) {
    if (!navSettings.enabled || !app.loaded || playerPlaying()) return false;
    cancelMoves();
    if (ortho) setPseudoOrtho(app, false);
    const dist = camera.position.distanceTo(controls.target);
    walkState.dist = walkTargetDistance(dist, controls.minDistance, controls.maxDistance, modelDiagonal(app));
    camera.up.set(0, 1, 0); // a rolled view (cube roll buttons) is levelled: the eye turns about world Y
    // From a top or bottom view the yaw comes from the screen up vector, and the pitch is clamped to 85 degrees.
    const look = turnLook(lookOf(app), 0, 0, undefined, screenUp(app));
    walkState.active = true;
    controls.enabled = false;
    syncWalkTarget(app, look);
    showToast('Walk mode: Esc to exit');
  } else {
    walkState.active = false;
    controls.enabled = true;
    controls.update();
  }
  app.renderer.markDirty();
  for (const l of walkListeners) l();
  return true;
}

export function toggleWalking(app: ViewerApp): void {
  if (walkState.active) setWalking(app, false);
  else if (!setWalking(app, true)) showToast(playerPlaying() ? 'Walk mode is off while a film plays' : 'Walk mode is not available now');
}

/** Move the eye on the horizontal plane (fwd, right) and along world Y (up), metres. The orbit target moves with it. */
export function walkBy(app: ViewerApp, fwd: number, right: number, up: number): void {
  const { camera } = app.renderer;
  cancelMoves();
  const look = lookOf(app);
  let next = walkMove(camera.position, look, fwd, right, up, screenUp(app));
  if (navSettings.walkCollision && (fwd !== 0 || right !== 0)) {
    // Only the horizontal part is limited; q and e (up) ignore collision. At most 3 rays, none when standing still.
    const horiz = new Vector3(next.x - camera.position.x, 0, next.z - camera.position.z);
    const ok = collideMove(camera.position, horiz, (o, d, max) => castWall(app, o, d, max), navSettings.eyeHeight);
    next = new Vector3(camera.position.x + ok.x, next.y, camera.position.z + ok.z);
  }
  camera.position.copy(next);
  syncWalkTarget(app, look);
}

/** The nearest wall for the collision rays: visible, not ghosted, not a door. */
function castWall(app: ViewerApp, origin: Vector3, dir: Vector3, maxDist: number): { distance: number; normal: Vector3 } | null {
  const els = app.loaded?.model.elements;
  if (!els) return null;
  const { alpha, flags } = app.renderer.state;
  const hit = app.renderer.raycastVisible(origin, dir, maxDist, (id) => blocksWalk(els[id]?.ifcClass ?? '', flags[id] ?? 0, alpha[id] ?? 1));
  return hit ? { distance: hit.distance, normal: hit.normal } : null;
}

let floorCache: { model: SceneModel; floors: FloorLevel[] } | null = null;
function floorsOf(app: ViewerApp): FloorLevel[] {
  const model = app.loaded?.model;
  if (!model) return [];
  if (!floorCache || floorCache.model !== model) floorCache = { model, floors: storeyFloors(model).map((f) => ({ id: f.id, name: f.name, floorY: f.floorY })) };
  return floorCache.floors;
}

function reducedMotion(): boolean {
  try {
    return typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  } catch {
    return false;
  }
}

/** Move the eye (and the target in front of it) to `eye`, keeping the view direction: a short glide, or at once. */
function glideEye(app: ViewerApp, eye: Vector3, look: Vector3): void {
  const to: FlyView = { position: eye.clone(), target: eyeTarget(eye, look, walkState.dist) };
  cancelMoves();
  if (navSettings.smoothMoves && !reducedMotion()) startTween(app, to, VIEW_MOVE_MS);
  else writeView(app, to);
  app.renderer.markDirty();
}

/** The surface under a pointer (client pixels): element, point and a normal facing the camera. Null on empty space. */
export function pickSurface(app: ViewerApp, clientX: number, clientY: number): { id: ElementId; point: Vector3; normal: Vector3 } | null {
  const { camera, canvas } = app.renderer;
  const r = canvas.getBoundingClientRect();
  const nx = ((clientX - r.left) / r.width) * 2 - 1;
  const ny = -((clientY - r.top) / r.height) * 2 + 1;
  const id = app.renderer.pick(nx, ny);
  if (id === null) return null;
  camera.updateMatrixWorld();
  const origin = camera.position.clone();
  const dir = new Vector3(nx, ny, 0.5).unproject(camera).sub(origin).normalize();
  return { id, point: origin.addScaledVector(dir, app.renderer.lastPickDistance), normal: app.renderer.lastPickNormal.clone() };
}

/**
 * Drop in here: stand on the picked spot at eye height, facing the same way. Enters Walk mode first when it is off. A surface that
 * faces up is stood on; for a wall the floor below is used (storey elevation, else a ray down). False when nothing was done.
 */
export function walkDropIn(app: ViewerApp, clientX: number, clientY: number): boolean {
  if (!app.loaded) return false;
  const surf = pickSurface(app, clientX, clientY);
  if (!surf) return false;
  if (!walkState.active && !setWalking(app, true)) return false;
  let ground: number | null = null;
  if (surf.normal.y <= 0.7 && floorsOf(app).every((f) => f.floorY > surf.point.y + 0.05)) {
    const hit = app.renderer.raycastVisible(surf.point.clone().add(new Vector3(0, 0.05, 0)), new Vector3(0, -1, 0), 1e4);
    ground = hit ? hit.point.y : null;
  }
  const spot = standingSpot(surf.point, surf.normal, floorsOf(app), navSettings.eyeHeight, ground);
  pushHistory(app, 'walk-drop');
  glideEye(app, spot.eye, lookOf(app));
  return true;
}

/** PageUp / PageDown in Walk mode: the eye moves to the next storey, keeping x, z and its height above the floor. */
function walkStoreyStep(app: ViewerApp, dir: 1 | -1): void {
  const floors = floorsOf(app);
  if (floors.length === 0) {
    showToast('The model has no storeys');
    return;
  }
  const { camera } = app.renderer;
  const step = stepWalkStorey(floors, camera.position.y, dir, navSettings.eyeHeight);
  if (!step) {
    showToast(dir > 0 ? 'Already at the top storey' : 'Already at the bottom storey');
    return;
  }
  pushHistory(app, 'storey');
  glideEye(app, new Vector3(camera.position.x, step.eyeY, camera.position.z), lookOf(app));
  showToast(step.level.name || `Storey ${step.level.id}`);
}

/** Turn the view about the eye: radians left and up (negative: right and down). The pitch stays within 85 degrees. */
export function walkTurn(app: ViewerApp, yaw: number, pitch: number): void {
  cancelMoves();
  syncWalkTarget(app, turnLook(lookOf(app), yaw, pitch, undefined, screenUp(app)));
}

/** A wheel gesture of `notches` (one notch = 100 px of delta, positive = scroll down) moves the eye back; negative moves it forward. */
export function walkWheel(app: ViewerApp, notches: number): void {
  walkBy(app, -notches * 0.03 * modelDiagonal(app) * navSettings.moveSpeed, 0, 0);
}

function zoomStep(app: ViewerApp, dir: 1 | -1): void {
  const { camera, controls } = app.renderer;
  cancelMoves();
  pushHistory(app, 'zoom');
  const off = camera.position.clone().sub(controls.target);
  let d = off.length();
  if (d < 1e-9) return;
  d = dir > 0 ? d * ZOOM_STEP : d / ZOOM_STEP;
  if (controls.minDistance > 0) d = Math.max(d, controls.minDistance);
  if (controls.maxDistance > 0 && Number.isFinite(controls.maxDistance)) d = Math.min(d, controls.maxDistance);
  camera.position.copy(controls.target).addScaledVector(off.normalize(), d);
  controls.update();
}

function frameBox(app: ViewerApp, box: Box3): void {
  moveToBox(app, box); // the framing controls (Cinematic > Camera fly-to) decide how close
}

function toggleProjection(app: ViewerApp): void {
  const { camera, controls } = app.renderer;
  cancelMoves();
  pushHistory(app, 'projection');
  const off = camera.position.clone().sub(controls.target);
  const dist = off.length();
  if (dist < 1e-9) return;
  const dir = off.normalize();
  if (!ortho) {
    ortho = { fov: camera.fov, far: camera.far, minDistance: controls.minDistance, maxDistance: controls.maxDistance };
    const nd = dollyForFov(dist, camera.fov, ORTHO_FOV);
    camera.fov = ORTHO_FOV;
    // The camera moves back by `ratio` to keep the framing, so the zoom range moves back with it. Limits left in
    // perspective units stopped the wheel from zooming out to the whole model, and the far plane cut it when it did.
    const ratio = nd / dist;
    controls.minDistance = controls.minDistance * ratio;
    controls.maxDistance = Math.max(controls.maxDistance * ratio, nd * 2);
    camera.far = Math.max(camera.far, controls.maxDistance + modelDiagonal(app) * 3);
    camera.position.copy(controls.target).addScaledVector(dir, nd);
    camera.updateProjectionMatrix();
    showToast('Orthographic (approximation: 2 degree field of view)');
  } else {
    const o = ortho;
    ortho = null;
    const nd = dollyForFov(dist, camera.fov, o.fov);
    camera.fov = o.fov;
    camera.far = o.far;
    controls.minDistance = o.minDistance;
    controls.maxDistance = o.maxDistance;
    camera.position.copy(controls.target).addScaledVector(dir, nd);
    camera.updateProjectionMatrix();
    showToast('Perspective');
  }
  controls.update();
}

export function isPseudoOrtho(): boolean {
  return ortho !== null;
}

/** Switch the pseudo-orthographic projection on or off (the camera keeps its framing). False when it was already so. */
export function setPseudoOrtho(app: ViewerApp, on: boolean): boolean {
  if (on === (ortho !== null)) return false;
  toggleProjection(app);
  return true;
}

/** Distance at which the pseudo-orthographic camera sees `height` metres top to bottom. */
export function orthoDistance(height: number): number {
  return height / 2 / Math.tan((ORTHO_FOV * Math.PI) / 360);
}

/**
 * Put the camera at a pose at once (no tween), stopping other camera moves, and make the orbit limits and the far plane reach
 * it. `up` is the screen up; `fov` (perspective only) is left alone when absent. Records the history for the back key.
 */
export function placeCamera(app: ViewerApp, pose: { position: readonly [number, number, number]; target: readonly [number, number, number]; up: readonly [number, number, number]; fov?: number }): void {
  const { camera, controls } = app.renderer;
  cancelMoves();
  pushHistory(app, 'view');
  const dist = Math.hypot(pose.position[0] - pose.target[0], pose.position[1] - pose.target[1], pose.position[2] - pose.target[2]);
  if (controls.minDistance > dist) controls.minDistance = dist * 0.5;
  if (controls.maxDistance > 0 && Number.isFinite(controls.maxDistance) && controls.maxDistance < dist * 1.05) controls.maxDistance = dist * 1.05;
  const need = dist + modelDiagonal(app) * 2;
  if (camera.far < need) camera.far = need;
  if (pose.fov !== undefined && ortho === null) camera.fov = pose.fov;
  camera.up.set(pose.up[0], pose.up[1], pose.up[2]);
  camera.position.set(pose.position[0], pose.position[1], pose.position[2]);
  controls.target.set(pose.target[0], pose.target[1], pose.target[2]);
  camera.updateProjectionMatrix();
  controls.update();
  app.renderer.markDirty();
}

function levelsOf(app: ViewerApp): Level[] {
  const model = app.loaded?.model;
  if (!model) return [];
  if (!storeyCache || storeyCache.model !== model) storeyCache = { model, levels: storeyLevels(model) };
  return storeyCache.levels;
}

function stepStoreyAction(app: ViewerApp, dir: 1 | -1): void {
  if (walkState.active) {
    walkStoreyStep(app, dir);
    return;
  }
  const { camera, controls } = app.renderer;
  const levels = levelsOf(app);
  if (levels.length === 0) {
    showToast('The model has no storeys');
    return;
  }
  const next = stepStorey(levels, controls.target.y, dir);
  if (!next) {
    showToast(dir > 0 ? 'Already at the top storey' : 'Already at the bottom storey');
    return;
  }
  cancelMoves();
  pushHistory(app, 'storey');
  const dy = next.y - controls.target.y;
  const to: FlyView = {
    position: camera.position.clone().add(new Vector3(0, dy, 0)),
    target: controls.target.clone().add(new Vector3(0, dy, 0)),
  };
  if (navSettings.smoothMoves) startTween(app, to, VIEW_MOVE_MS);
  else writeView(app, to);
  showToast(next.name || `Storey ${next.id}`);
}

function cycleSelection(app: ViewerApp, dir: 1 | -1): void {
  const order = tabOrder(app.controller.selection);
  if (order.length === 0) return;
  const key = order.join(',');
  if (tabCursor.key !== key) tabCursor = { key, index: -1 };
  tabCursor.index = stepCycle(tabCursor.index, order.length, dir);
  const id = order[tabCursor.index]!;
  const box = boxOfIds(app, [id]);
  const e = app.loaded?.model.elements[id];
  moveToBox(app, box, { margin: 2.2, tag: 'tab' });
  showToast(`${tabCursor.index + 1} / ${order.length}  ${e?.name || e?.ifcClass || `#${id}`}`);
}

function applyPose(app: ViewerApp, p: Pose | null, what: string): void {
  if (!p) {
    showToast(`No ${what} view`);
    return;
  }
  moveToPose(app, p);
}

/** Register every navigation action. Safe to call again (registerAction replaces by id). */
export function registerNavigationActions(): void {
  const dpr = (): number => Math.PI / 180;
  const vSign = (): number => (navSettings.invertVertical ? -1 : 1);
  const orbitRate = (dt: number, m: HoldMods): number => navSettings.orbitSpeed * dpr() * (dt / 1000) * slow(m);

  // In Walk mode the arrow keys walk and turn (Shift: 3 times faster, Ctrl: 0.25 times); the pan chords do the same, so Shift+Arrow is fast.
  const walkRate = (app: ViewerApp, dt: number, m: HoldMods): number => navSettings.moveSpeed * 0.2 * modelDiagonal(app) * (dt / 1000) * walkSpeedFactor(m);
  const turnRate = (dt: number, m: HoldMods): number => navSettings.orbitSpeed * dpr() * (dt / 1000) * walkSpeedFactor(m);
  const walkingNow = (): boolean => walkState.active;

  holdAction('nav.orbitLeft', 'Orbit left', 'Navigation', ['ArrowLeft'], (app, dt, m) => (walkingNow() ? walkTurn(app, turnRate(dt, m), 0) : orbitBy(app, orbitRate(dt, m), 0)), 'Orbit around the camera target. Hold the key. Ctrl is slow. In Walk mode: turn left.');
  holdAction('nav.orbitRight', 'Orbit right', 'Navigation', ['ArrowRight'], (app, dt, m) => (walkingNow() ? walkTurn(app, -turnRate(dt, m), 0) : orbitBy(app, -orbitRate(dt, m), 0)), undefined, { modifiers: ['ctrl'] });
  holdAction('nav.orbitUp', 'Orbit up', 'Navigation', ['ArrowUp'], (app, dt, m) => (walkingNow() ? walkBy(app, walkRate(app, dt, m), 0, 0) : orbitBy(app, 0, -orbitRate(dt, m) * vSign())), undefined, { modifiers: ['ctrl'] });
  holdAction('nav.orbitDown', 'Orbit down', 'Navigation', ['ArrowDown'], (app, dt, m) => (walkingNow() ? walkBy(app, -walkRate(app, dt, m), 0, 0) : orbitBy(app, 0, orbitRate(dt, m) * vSign())), undefined, { modifiers: ['ctrl'] });

  const panRate = (dt: number, m: HoldMods): number => navSettings.panSpeed * 0.5 * (dt / 1000) * slow(m);
  holdAction('nav.panLeft', 'Pan left', 'Navigation', ['Shift+ArrowLeft'], (app, dt, m) => (walkingNow() ? walkTurn(app, turnRate(dt, m), 0) : panBy(app, -panRate(dt, m), 0)), 'Slide the view sideways. Hold the key. In Walk mode: turn left, fast.');
  holdAction('nav.panRight', 'Pan right', 'Navigation', ['Shift+ArrowRight'], (app, dt, m) => (walkingNow() ? walkTurn(app, -turnRate(dt, m), 0) : panBy(app, panRate(dt, m), 0)));
  holdAction('nav.panUp', 'Pan up', 'Navigation', ['Shift+ArrowUp'], (app, dt, m) => (walkingNow() ? walkBy(app, walkRate(app, dt, m), 0, 0) : panBy(app, 0, panRate(dt, m) * vSign())));
  holdAction('nav.panDown', 'Pan down', 'Navigation', ['Shift+ArrowDown'], (app, dt, m) => (walkingNow() ? walkBy(app, -walkRate(app, dt, m), 0, 0) : panBy(app, 0, -panRate(dt, m) * vSign())));

  // w a s d q e: Game style flies the camera and its target at all times; BIM style (the default) only in Walk mode, where they
  // move the eye on the horizontal plane (q and e change its height). Ids and chords stay, so custom keymaps keep working.
  const moveRate = (app: ViewerApp, dt: number, m: HoldMods): number => navSettings.moveSpeed * 0.2 * modelDiagonal(app) * (dt / 1000) * slow(m);
  const flyEnabled = (): boolean => navSettings.enabled && flyKeysEnabled(navSettings.style, walkState.active);
  const fly = { enabled: flyEnabled, modifiers: ['ctrl', 'shift'] as Array<'ctrl' | 'shift'> };
  const flyHold = (f: (app: ViewerApp, r: number) => void, w: (app: ViewerApp, r: number) => void) => (app: ViewerApp, dt: number, m: HoldMods): void =>
    walkingNow() ? w(app, walkRate(app, dt, m)) : f(app, moveRate(app, dt, m));
  holdAction('nav.forward', 'Fly forward (Walk mode)', 'Navigation', ['w'], flyHold((a, r) => flyBy(a, r, 0, 0), (a, r) => walkBy(a, r, 0, 0)), 'Game style, or Walk mode (Shift+W): move the camera and its target together. Hold the key. Ctrl is slow.', fly);
  holdAction('nav.back', 'Fly back (Walk mode)', 'Navigation', ['s'], flyHold((a, r) => flyBy(a, -r, 0, 0), (a, r) => walkBy(a, -r, 0, 0)), 'Game style, or Walk mode.', fly);
  holdAction('nav.left', 'Fly left (Walk mode)', 'Navigation', ['a'], flyHold((a, r) => flyBy(a, 0, -r, 0), (a, r) => walkBy(a, 0, -r, 0)), 'Game style, or Walk mode.', fly);
  holdAction('nav.right', 'Fly right (Walk mode)', 'Navigation', ['d'], flyHold((a, r) => flyBy(a, 0, r, 0), (a, r) => walkBy(a, 0, r, 0)), 'Game style, or Walk mode.', fly);
  holdAction('nav.down', 'Fly down (Walk mode)', 'Navigation', ['q'], flyHold((a, r) => flyBy(a, 0, 0, -r), (a, r) => walkBy(a, 0, 0, -r)), 'Game style, or Walk mode.', fly);
  holdAction('nav.up', 'Fly up (Walk mode)', 'Navigation', ['e'], flyHold((a, r) => flyBy(a, 0, 0, r), (a, r) => walkBy(a, 0, 0, r)), 'Game style, or Walk mode.', fly);

  registerAction({
    id: 'nav.walk',
    label: 'Walk mode',
    group: 'Navigation',
    keys: ['Shift+w'],
    // Only enters: while walking, Shift+w is "run forward" (Shift with a move key), so the chord must fall through to nav.forward.
    enabled: (app) => navSettings.enabled && !!app.loaded && !isWalking(),
    description: 'Walk through the model: w s and Up Down move on the floor, a d strafe, Left Right turn, q e change the eye height, Shift runs, drag looks around. Esc, the chip or the gizmo button leaves.',
    run: toggleWalking,
  });

  registerAction({ id: 'nav.zoomIn', label: 'Zoom in', group: 'Navigation', keys: ['=', '+', 'code:NumpadAdd'], repeat: true, enabled: navEnabled, description: 'Move 15 % closer to the camera target.', run: (app) => zoomStep(app, 1) });
  registerAction({ id: 'nav.zoomOut', label: 'Zoom out', group: 'Navigation', keys: ['-', 'code:NumpadSubtract'], repeat: true, enabled: navEnabled, description: 'Move 15 % further from the camera target.', run: (app) => zoomStep(app, -1) });

  viewAction('view.front', 'Front view', 'front', ['code:Numpad1', 'Alt+code:Digit1']);
  viewAction('view.back', 'Back view', 'back', ['Ctrl+code:Numpad1', 'Alt+Shift+code:Digit1']);
  viewAction('view.right', 'Right view', 'right', ['code:Numpad3', 'Alt+code:Digit3']);
  viewAction('view.left', 'Left view', 'left', ['Ctrl+code:Numpad3', 'Alt+Shift+code:Digit3']);
  viewAction('view.top', 'Top view', 'top', ['code:Numpad7', 'Alt+code:Digit7']);
  viewAction('view.bottom', 'Bottom view', 'bottom', ['Ctrl+code:Numpad7', 'Alt+Shift+code:Digit7']);
  viewAction('view.iso', 'Isometric view', 'iso', ['code:Numpad0', 'Alt+code:Digit0']);
  registerAction({
    id: 'view.projection',
    label: 'Toggle perspective / orthographic',
    group: 'Views',
    keys: ['code:Numpad5', 'Alt+code:Digit5'],
    enabled: navEnabled,
    description: 'Orthographic is an approximation: a 2 degree field of view with the camera moved back.',
    run: toggleProjection,
  });

  registerAction({
    id: 'view.frame',
    label: 'Frame selection (or all)',
    group: 'Views',
    keys: ['f'],
    description: 'Fly to the selection. With nothing selected, frame the whole model.',
    enabled: navEnabled,
    run(app) {
      if (app.controller.selection.size > 0) {
        const b = boxOfIds(app, app.controller.selection);
        if (!b.isEmpty()) {
          frameBox(app, b);
          return;
        }
      }
      pushHistory(app);
      cancelMoves();
      app.frameAll();
    },
  });
  registerAction({
    id: 'view.frameSelection',
    label: 'Frame selection',
    group: 'Views',
    keys: ['.', 'code:NumpadDecimal'],
    enabled: navEnabled,
    run(app) {
      const b = boxOfIds(app, app.controller.selection);
      if (b.isEmpty()) {
        showToast('Nothing selected');
        return;
      }
      frameBox(app, b);
    },
  });
  registerAction({
    id: 'view.frameAll',
    label: 'Frame all',
    group: 'Views',
    keys: ['Home'],
    enabled: navEnabled,
    run(app) {
      pushHistory(app);
      cancelMoves();
      app.frameAll();
    },
  });

  registerAction({ id: 'nav.storeyUp', label: 'Storey up', group: 'Navigation', keys: ['PageUp'], enabled: navEnabled, repeat: false, description: 'Move the camera target to the next storey above. In Walk mode: move the eye to the next storey, same spot and eye height.', run: (app) => stepStoreyAction(app, 1) });
  registerAction({ id: 'nav.storeyDown', label: 'Storey down', group: 'Navigation', keys: ['PageDown'], enabled: navEnabled, description: 'Move the camera target to the next storey below. In Walk mode: move the eye to the next storey down.', run: (app) => stepStoreyAction(app, -1) });
  registerAction({
    id: 'nav.nextSelected',
    label: 'Next selected element',
    group: 'Navigation',
    keys: ['Tab'],
    enabled: (app) => navSettings.enabled && !!app.controller && app.controller.selection.size > 0,
    description: 'Fly the camera to each selected element in turn, without changing the selection.',
    run: (app) => cycleSelection(app, 1),
  });
  registerAction({
    id: 'nav.prevSelected',
    label: 'Previous selected element',
    group: 'Navigation',
    keys: ['Shift+Tab'],
    enabled: (app) => navSettings.enabled && !!app.controller && app.controller.selection.size > 0,
    run: (app) => cycleSelection(app, -1),
  });
  registerAction({
    id: 'nav.historyBack',
    label: 'Previous view',
    group: 'Navigation',
    keys: ['Alt+ArrowLeft'],
    enabled: navEnabled,
    description: 'Return to the camera pose before the last view change. Up to 50 poses.',
    run: (app) => applyPose(app, history.goBack(currentPose(app)), 'previous'),
  });
  registerAction({
    id: 'nav.historyForward',
    label: 'Next view',
    group: 'Navigation',
    keys: ['Alt+ArrowRight'],
    enabled: navEnabled,
    run: (app) => applyPose(app, history.goForward(currentPose(app)), 'next'),
  });
}

/** A new model is installed: forget poses and projection state of the old one. */
export function navigationOnModel(app: ViewerApp): void {
  history.clear();
  tabCursor = { key: '', index: -1 };
  tween = null;
  storeyCache = null;
  floorCache = null;
  if (ortho) {
    const o = ortho;
    ortho = null;
    app.renderer.camera.fov = o.fov;
    app.renderer.camera.updateProjectionMatrix();
    app.renderer.frameAll();
  }
}

/** Mouse buttons 4 and 5 (back, forward) walk the view history. */
export function bindMouseHistory(app: ViewerApp): void {
  const onUp = (e: MouseEvent): void => {
    if (!navSettings.enabled || (e.button !== 3 && e.button !== 4)) return;
    e.preventDefault();
    if (e.button === 3) applyPose(app, history.goBack(currentPose(app)), 'previous');
    else applyPose(app, history.goForward(currentPose(app)), 'next');
  };
  window.addEventListener('mouseup', onUp);
  // Stop the browser's own history navigation for those buttons.
  window.addEventListener('mousedown', (e) => {
    if (e.button === 3 || e.button === 4) e.preventDefault();
  });
}

/** True while the fallback tween (history, storey steps, views without the cinematic plugin) is running. */
export function isNavigationMoving(): boolean {
  return tween !== null;
}

/** Stop any running tween (camera moved by a pointer). */
export function cancelNavigationMoves(): void {
  tween = null;
}
