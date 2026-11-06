// WebXR session manager (experimental): enter and leave an immersive VR or AR session, move the XR rig, read the controllers
// and hands, draw the pointer rays and the AR reticle. The maths is in xr/maths.ts; the GUI, the tool and the actions are in
// plugins/xr.ts. three.js does the session plumbing (renderer.xr); this file owns what the viewer does inside a session.
//
// Design: the model never moves. The XR camera sits in a rig (an Object3D that holds the camera, the pointer rays and the
// reticle); moving, turning and scaling the rig moves, turns and scales the viewer. See xr/maths.ts for the transform.
// Inside a session the renderer draws with the stereo camera straight into the XR framebuffer and leaves out the passes that go
// through private single-view targets (renderer.xrFallbacks lists them).

import { BoxGeometry, Group, Mesh, MeshBasicMaterial, RingGeometry, Sphere, Vector3 } from 'three';
import type { Object3D } from 'three';
import type { ViewerApp } from '../app';
import {
  AR_SCALES, arPlacement, arScaleFactor, clipDistances, controllerRayToWorld, defaultArHit, defaultArSurface, moveStep, poseToCamera, rigFromOrbitCamera,
  quatRotate, snapTurn, snapTurnStep, yawOfDirection,
} from './maths';
import type { ArScale, Q4, Rig, SnapState, V3 } from './maths';
import { FieldController, defaultFieldConfig } from './fieldSession';
import type { FieldConfig, FieldHost, FieldNote, FieldStateView } from './fieldSession';

/** 'field': augmented reality at real scale, registered on the real building by point pairs (xr/fieldSession.ts). */
export type XrMode = 'vr' | 'ar' | 'field';

export interface XrSupport {
  vr: boolean;
  ar: boolean;
}

export interface XrConfig {
  arScale: ArScale;
  pointerRays: boolean;
}

export interface XrState {
  supported: XrSupport;
  mode: XrMode | null;
  presenting: boolean;
  status: string;
  rig: { position: V3; yaw: number; scale: number };
  placed: boolean;
  arScale: ArScale;
  fallbacks: string[];
  selects: number;
  squeezes: number;
  turns: number;
  inputSources: number;
  hitTest: boolean;
  /** Field AR state (null outside a field session). */
  field: FieldStateView | null;
}

interface NavigatorXr {
  isSessionSupported(mode: string): Promise<boolean>;
  requestSession(mode: string, init?: Record<string, unknown>): Promise<XRSession>;
}

/** Feature detection: navigator.xr and isSessionSupported for immersive-vr and immersive-ar. Never throws. */
export async function detectXr(nav: { xr?: unknown } | undefined = typeof navigator === 'undefined' ? undefined : navigator): Promise<XrSupport> {
  const xr = nav?.xr as NavigatorXr | undefined;
  if (!xr || typeof xr.isSessionSupported !== 'function') return { vr: false, ar: false };
  const ask = async (m: string): Promise<boolean> => {
    try {
      return (await xr.isSessionSupported(m)) === true;
    } catch {
      return false;
    }
  };
  const [vr, ar] = await Promise.all([ask('immersive-vr'), ask('immersive-ar')]);
  return { vr, ar };
}

/** The forward direction (-Z) of a head orientation, in the XR reference space. */
const quatForward = (q: Q4): V3 => quatRotate(q, [0, 0, -1]);

/** Time between two picks of a pointer ray for the hover highlight, ms. */
const RAY_PICK_MS = 100;
/** Physical length of a pointer ray that hits nothing, metres. */
const RAY_FREE_LENGTH = 3;
const RAY_WIDTH = 0.004;

interface RayVisual {
  mesh: Mesh;
  lastPick: number;
  hitLength: number | null;
  id: number | null;
}

export class XrManager {
  readonly config: XrConfig = { arScale: '1:1', pointerRays: true };
  /** Settings of the field AR mode (look, cut, snapping, restore, BCF notes). */
  readonly fieldConfig: FieldConfig = defaultFieldConfig();
  /** Model points picked in the normal view before a field session (world coordinates). */
  fieldDraft: V3[] = [];
  /** The field controller while a field session runs. */
  field: FieldController | null = null;
  /** Snapshots of the last field session. */
  lastNotes: FieldNote[] = [];
  /** Called after a field session ended and the normal view is back, with its snapshots. */
  onFieldEnd: ((notes: FieldNote[]) => void) | null = null;
  support: XrSupport = { vr: false, ar: false };
  mode: XrMode | null = null;
  status = 'WebXR: checking the device';
  selects = 0;
  squeezes = 0;
  turns = 0;
  placed = false;
  hitTestActive = false;

  private readonly rigObj = new Group();
  private rig: Rig = { position: [0, 0, 0], yaw: 0, scale: 1 };
  private session: XRSession | null = null;
  private entering = false;
  private head: V3 = [0, 0, 0];
  private headQ: Q4 = [0, 0, 0, 1];
  private orbitYaw = 0;
  private orbitPos: V3 = [0, 0, 0];
  private orbitDirV: V3 = [0, 0, -1];
  /** The rig is placed again from the real head pose at the first frame (the head is near, not exactly at, the origin of 'local'). */
  private rigPending = false;
  private anchor: V3 = [0, 0, 0];
  private radius = 10;
  private lastHit: V3 = [0, -1.4, -1.2];
  private hitSource: XRHitTestSource | null = null;
  private reticle: Mesh | null = null;
  private reticleOk = false;
  private readonly rays = new Map<XRInputSource, RayVisual>();
  private readonly snap = new Map<XRInputSource, SnapState>();
  private lastSlPos: V3 | null = null;
  private lastStatusNotify = 0;
  private readonly listeners = new Set<() => void>();
  private saved: {
    pos: Vector3;
    quat: import('three').Quaternion;
    scale: Vector3;
    near: number;
    far: number;
    fov: number;
    target: Vector3;
    controls: boolean;
    background: import('three').Scene['background'];
    clearAlpha: number;
  } | null = null;

  constructor(private readonly app: ViewerApp) {
    this.rigObj.name = 'xray-xr-rig';
    app.renderer.renderer.xr.addEventListener('sessionend', this.onSessionEnd);
  }

  /** Subscribe to state changes (status text, mode). Returns an unsubscribe function. */
  onChange(cb: () => void): () => void {
    this.listeners.add(cb);
    return () => this.listeners.delete(cb);
  }

  private notify(): void {
    for (const l of this.listeners) l();
  }

  get active(): boolean {
    return this.mode !== null;
  }

  /** Check what the device supports (navigator.xr, immersive-vr, immersive-ar) and set the idle status. */
  async detect(nav?: { xr?: unknown }): Promise<XrSupport> {
    this.support = await detectXr(nav);
    this.setIdleStatus();
    this.notify();
    return this.support;
  }

  private setIdleStatus(): void {
    const { vr, ar } = this.support;
    this.status = vr || ar ? `ready: ${[vr ? 'VR' : '', ar ? 'AR' : ''].filter(Boolean).join(' and ')} (experimental)` : 'WebXR is not supported on this device';
  }

  // ------------------------------------------------------------------ enter and leave

  /** Start a session. Call it from a click or a key press (a browser rule for XR sessions). */
  async enter(mode: XrMode): Promise<void> {
    if (this.session || this.entering) return;
    if (!(mode === 'field' ? this.support.ar : this.support[mode])) {
      this.status = `${mode.toUpperCase()} is not supported on this device`;
      this.notify();
      return;
    }
    const xrNav = (navigator as unknown as { xr?: NavigatorXr }).xr;
    if (!xrNav) return;
    this.entering = true;
    const r = this.app.renderer;
    const three = r.renderer;
    let session: XRSession;
    const field = mode === 'field' ? new FieldController(this.fieldHost, this.fieldConfig, this.fieldDraft) : null;
    try {
      const init: Record<string, unknown> =
        mode === 'vr'
          ? { optionalFeatures: ['local-floor', 'hand-tracking'] }
          : mode === 'ar'
            ? { optionalFeatures: ['hit-test', 'local-floor', 'hand-tracking'] }
            : // Field AR: anchors hold the registration while walking; the DOM overlay is the phone panel.
              { optionalFeatures: ['hit-test', 'anchors', 'dom-overlay', 'local-floor', 'hand-tracking'], domOverlay: { root: field!.overlayRoot() } };
      session = await xrNav.requestSession(mode === 'vr' ? 'immersive-vr' : 'immersive-ar', init);
    } catch (e) {
      field?.end();
      this.entering = false;
      this.status = `could not start ${mode.toUpperCase()}: ${e instanceof Error ? e.message : String(e)}`;
      this.notify();
      return;
    }
    const cam = r.camera;
    // What to restore on exit.
    this.saved = {
      pos: cam.position.clone(),
      quat: cam.quaternion.clone(),
      scale: cam.scale.clone(),
      near: cam.near,
      far: cam.far,
      fov: cam.fov,
      target: r.controls.target.clone(),
      controls: r.controls.enabled,
      background: r.scene.background,
      clearAlpha: three.getClearAlpha(),
    };
    const orbitPos = cam.position.clone();
    const orbitDir = cam.getWorldDirection(new Vector3());
    try {
      three.xr.enabled = true;
      // 'local': the head starts at the origin of the reference space, so the rig can put it exactly on the orbit camera.
      three.xr.setReferenceSpaceType('local');
      await three.xr.setSession(session);
    } catch (e) {
      three.xr.enabled = false;
      field?.end();
      this.entering = false;
      this.saved = null;
      this.status = `could not start ${mode.toUpperCase()}: ${e instanceof Error ? e.message : String(e)}`;
      void session.end().catch(() => undefined);
      this.notify();
      return;
    }
    this.session = session;
    this.mode = mode;
    this.selects = this.squeezes = this.turns = 0;
    this.placed = mode === 'vr';
    this.field = field;
    this.entering = false;

    const box = this.app.loaded?.geometry.totalBounds();
    if (box && !box.isEmpty()) {
      const c = box.getCenter(new Vector3());
      this.radius = Math.max(box.getBoundingSphere(new Sphere()).radius, 1);
      this.anchor = [c.x, box.min.y, c.z];
    }
    this.orbitYaw = yawOfDirection([orbitDir.x, orbitDir.y, orbitDir.z]);
    this.orbitPos = [orbitPos.x, orbitPos.y, orbitPos.z];
    this.orbitDirV = [orbitDir.x, orbitDir.y, orbitDir.z];
    this.rigPending = true;
    if (mode === 'vr') {
      this.rig = rigFromOrbitCamera([orbitPos.x, orbitPos.y, orbitPos.z], [orbitDir.x, orbitDir.y, orbitDir.z]);
    } else {
      // Until the first tap the model stands 1.2 m ahead on the floor, turned as in the orbit view.
      const surf = defaultArSurface(this.arScale());
      this.lastHit = defaultArHit([0, 0, 0], [0, 0, -1], surf.distance, surf.eyeHeight);
      this.rig = arPlacement(this.lastHit, this.anchor, this.arScale(), this.orbitYaw);
    }
    r.scene.add(this.rigObj);
    this.rigObj.add(cam);
    r.controls.enabled = false;
    if (mode !== 'vr') {
      r.scene.background = null;
      three.setClearAlpha(0);
    }
    if (mode === 'ar') {
      this.buildReticle();
      void this.startHitTest(session);
    }
    this.applyRig();
    field?.start(session, three.xr.getReferenceSpace());
    session.addEventListener('select', this.onSelect);
    session.addEventListener('squeeze', this.onSqueeze);
    this.lastSlPos = null;
    this.app.runSightlinesNow();
    this.refreshStatus(true);
  }

  /** End the session; the state is restored by the 'sessionend' handler (also when the headset or the browser ends it). */
  exit(): void {
    const s = this.session;
    if (s) void s.end().catch(() => undefined);
  }

  private readonly onSessionEnd = (): void => {
    const r = this.app.renderer;
    const three = r.renderer;
    const session = this.session;
    session?.removeEventListener('select', this.onSelect);
    session?.removeEventListener('squeeze', this.onSqueeze);
    try {
      this.hitSource?.cancel();
    } catch {
      /* the session is gone */
    }
    this.hitSource = null;
    this.hitTestActive = false;
    for (const v of this.rays.values()) {
      v.mesh.removeFromParent();
      v.mesh.geometry.dispose();
      (v.mesh.material as MeshBasicMaterial).dispose();
    }
    this.rays.clear();
    this.snap.clear();
    if (this.reticle) {
      this.reticle.removeFromParent();
      this.reticle.geometry.dispose();
      (this.reticle.material as MeshBasicMaterial).dispose();
      this.reticle = null;
    }
    const field = this.field;
    this.field = null;
    const notes = field ? field.end() : null;
    const cam = r.camera;
    cam.removeFromParent();
    this.rigObj.removeFromParent();
    this.rigObj.position.set(0, 0, 0);
    this.rigObj.rotation.set(0, 0, 0);
    this.rigObj.scale.set(1, 1, 1);
    const s = this.saved;
    r.xrHeadWorld = null;
    three.xr.enabled = false;
    if (s) {
      cam.position.copy(s.pos);
      cam.quaternion.copy(s.quat);
      cam.scale.copy(s.scale);
      cam.near = s.near;
      cam.far = s.far;
      cam.fov = s.fov;
      cam.zoom = 1;
      r.controls.target.copy(s.target);
      r.controls.enabled = s.controls;
      r.scene.background = s.background;
      three.setClearAlpha(s.clearAlpha);
    }
    this.saved = null;
    this.session = null;
    this.mode = null;
    this.placed = false;
    this.app.hoverId = null;
    r.resize(); // the framebuffer size of the session is gone: size to the page again, which also restores the projection
    cam.updateMatrixWorld(true);
    r.controls.update();
    r.markDirty();
    this.app.runSightlinesNow();
    this.setIdleStatus();
    if (notes) {
      this.lastNotes = notes;
      this.onFieldEnd?.(notes);
    }
    this.notify();
  };

  /** World metres per physical metre of the AR modes: field AR is always real scale. */
  private arScale(): number {
    return this.mode === 'field' || (this.entering && this.field) ? 1 : arScaleFactor(this.config.arScale);
  }

  /** What the field controller may use of this manager. */
  private readonly fieldHost: FieldHost = ((m: XrManager) => ({
    get app(): ViewerApp {
      return m.app;
    },
    getRig: (): Rig => m.getRig(),
    setRig: (r: Rig): void => {
      m.rig = { position: [...r.position], yaw: r.yaw, scale: r.scale };
      m.applyRig();
    },
    head: (): { position: V3; quaternion: Q4 } => ({ position: [...m.head], quaternion: [...m.headQ] }),
    rigObject: (): Object3D => m.rigObj,
    changed: (): void => m.refreshStatus(true),
    exit: (): void => m.exit(),
  }))(this);

  // ------------------------------------------------------------------ rig

  private applyRig(): void {
    const o = this.rigObj;
    o.position.set(this.rig.position[0], this.rig.position[1], this.rig.position[2]);
    o.rotation.set(0, this.rig.yaw, 0);
    o.scale.setScalar(this.rig.scale);
    o.updateMatrixWorld(true);
    const { near, far } = clipDistances(this.radius, this.rig.scale);
    const cam = this.app.renderer.camera;
    cam.near = near;
    cam.far = far;
    // Bring the camera up to date with the head pose and the new rig, for every hook of this frame (view-mode planes, sections).
    this.app.renderer.renderer.xr.updateCamera(cam);
  }

  /** Current rig (copy), for tests and the status line. */
  getRig(): Rig {
    return { position: [...this.rig.position], yaw: this.rig.yaw, scale: this.rig.scale };
  }

  setArScale(s: ArScale): void {
    if (!AR_SCALES.includes(s)) return;
    this.config.arScale = s;
    if (this.mode === 'ar') {
      if (!this.placed && !this.reticleOk) {
        const surf = defaultArSurface(arScaleFactor(s));
        this.lastHit = defaultArHit(this.head, [0, 0, -1], surf.distance, surf.eyeHeight);
      }
      this.rig = arPlacement(this.lastHit, this.anchor, arScaleFactor(s), this.rig.yaw);
      this.applyRig();
      this.refreshStatus(true);
    }
    this.notify();
  }

  // ------------------------------------------------------------------ frame

  /** First hook of every frame: moves the rig, brings the camera up to date, runs the sightlines from the head. */
  beforeFrame(now: number, dt: number): void {
    const session = this.session;
    if (!session) return;
    const x = this.app.renderer.renderer.xr;
    const frame = x.getFrame();
    const ref = x.getReferenceSpace();
    if (!frame || !ref) return;
    const pose = frame.getViewerPose(ref);
    if (!pose) return;
    const p = pose.transform.position;
    const q = pose.transform.orientation;
    this.head = [p.x, p.y, p.z];
    this.headQ = [q.x, q.y, q.z, q.w];
    if (this.rigPending) {
      // First frame: put the real head exactly on the orbit camera (VR), or the default model spot ahead of the head (AR).
      this.rigPending = false;
      if (this.mode === 'vr') this.rig = rigFromOrbitCamera(this.orbitPos, this.orbitDirV, this.head);
      else if (!this.field?.registered) {
        const surf = defaultArSurface(this.arScale());
        this.lastHit = defaultArHit(this.head, quatForward(this.headQ), surf.distance, surf.eyeHeight);
        this.rig = arPlacement(this.lastHit, this.anchor, this.arScale(), this.orbitYaw);
      }
      this.applyRig();
      this.app.runSightlinesNow();
    }

    const dts = Math.min(Math.max(dt, 0), 100) / 1000;
    const sources = new Set<XRInputSource>();
    for (const src of session.inputSources) {
      sources.add(src);
      if (this.mode === 'vr') {
        const gp = src.gamepad;
        if (gp && gp.axes.length >= 2) {
          const ax = gp.axes.length >= 4 ? gp.axes[2]! : gp.axes[0]!;
          const ay = gp.axes.length >= 4 ? gp.axes[3]! : gp.axes[1]!;
          if (src.handedness === 'left') {
            const fwd = poseToCamera(this.rig, this.head, this.headQ).forward;
            const next = moveStep(this.rig, fwd, ax, ay, dts);
            this.rig = next;
          } else {
            let st = this.snap.get(src);
            if (!st) this.snap.set(src, (st = { armed: true }));
            const step = snapTurnStep(st, ax);
            if (step !== 0) {
              this.rig = snapTurn(this.rig, this.head, step);
              this.turns++;
            }
          }
        }
      }
      this.updateRay(src, frame, ref, now);
    }
    for (const [src, v] of this.rays) {
      if (!sources.has(src)) {
        v.mesh.removeFromParent();
        v.mesh.geometry.dispose();
        (v.mesh.material as MeshBasicMaterial).dispose();
        this.rays.delete(src);
      }
    }
    if (this.mode === 'ar' && this.hitSource && !this.placed) this.updateReticle(frame, ref);
    if (this.field) {
      this.field.frame(frame, ref, now);
      this.placed = this.field.registered && this.field.step === 'done';
    }
    this.applyRig();

    // Algorithm 2 runs from the head position, throttled by the app (SIGHTLINE_INTERVAL_MS) and by this distance test.
    const w = poseToCamera(this.rig, this.head, this.headQ).position;
    const hw = this.app.renderer.xrHeadWorld ?? (this.app.renderer.xrHeadWorld = new Vector3());
    hw.set(w[0], w[1], w[2]);
    const moved = this.lastSlPos === null || Math.hypot(w[0] - this.lastSlPos[0], w[1] - this.lastSlPos[1], w[2] - this.lastSlPos[2]) > 0.01 * this.rig.scale;
    if (moved) {
      this.lastSlPos = w;
      this.app.renderer.notifyCameraChanged();
    }
    this.refreshStatus(false, now);
  }

  // ------------------------------------------------------------------ input

  private readonly onSelect = (ev: Event): void => {
    const e = ev as XRInputSourceEvent;
    this.selects++;
    const x = this.app.renderer.renderer.xr;
    const ref = x.getReferenceSpace();
    if (!ref) return;
    if (this.field) {
      this.field.onSelect(e, ref);
      return;
    }
    if (this.mode === 'ar' && !this.placed) {
      this.placeModel();
      return;
    }
    const pose = e.frame.getPose(e.inputSource.targetRaySpace, ref);
    if (!pose) return;
    const pp = pose.transform.position;
    const po = pose.transform.orientation;
    const ray = controllerRayToWorld(this.rig, [pp.x, pp.y, pp.z], [po.x, po.y, po.z, po.w]);
    const id = this.app.renderer.pickRay(new Vector3(...ray.origin), new Vector3(...ray.direction));
    if (id === null) this.app.clearSelection();
    else this.app.selectIds([id], false);
  };

  private readonly onSqueeze = (): void => {
    this.squeezes++;
    if (this.field) {
      this.field.onSqueeze();
      return;
    }
    if (this.mode === 'ar') {
      // AR: a squeeze picks the model up again (the next select places it).
      this.placed = false;
      this.refreshStatus(true);
      return;
    }
    this.app.setXray(!this.app.settings.xray);
  };

  /** AR: put the model at the reticle (or ahead of the head when the device found no surface) at the chosen scale. */
  private placeModel(): void {
    const hit = this.reticleOk && this.reticle ? ([this.reticle.position.x, this.reticle.position.y, this.reticle.position.z] as V3) : this.lastHit;
    this.lastHit = hit;
    this.rig = arPlacement(hit, this.anchor, arScaleFactor(this.config.arScale), this.rig.yaw);
    this.placed = true;
    if (this.reticle) this.reticle.visible = false;
    this.applyRig();
    this.app.runSightlinesNow();
    this.refreshStatus(true);
  }

  private updateRay(src: XRInputSource, frame: XRFrame, ref: XRReferenceSpace, now: number): void {
    const space = src.targetRaySpace;
    if (!space) return;
    const pose = frame.getPose(space, ref);
    let v = this.rays.get(src);
    if (!pose) {
      if (v) v.mesh.visible = false;
      return;
    }
    if (!v) {
      const geo = new BoxGeometry(1, 1, 1);
      geo.translate(0, 0, -0.5);
      const mesh = new Mesh(geo, new MeshBasicMaterial({ color: 0x4aa8ff, depthTest: false, transparent: true, opacity: 0.85 }));
      mesh.frustumCulled = false;
      mesh.renderOrder = 20;
      mesh.name = 'xray-xr-ray';
      this.rigObj.add(mesh);
      v = { mesh, lastPick: 0, hitLength: null, id: null };
      this.rays.set(src, v);
    }
    const pp = pose.transform.position;
    const po = pose.transform.orientation;
    v.mesh.position.set(pp.x, pp.y, pp.z);
    v.mesh.quaternion.set(po.x, po.y, po.z, po.w);
    v.mesh.visible = this.config.pointerRays;
    if (now - v.lastPick >= RAY_PICK_MS && (this.mode === 'vr' || this.placed)) {
      v.lastPick = now;
      const ray = controllerRayToWorld(this.rig, [pp.x, pp.y, pp.z], [po.x, po.y, po.z, po.w]);
      const id = this.app.renderer.pickRay(new Vector3(...ray.origin), new Vector3(...ray.direction));
      v.id = id;
      v.hitLength = id === null ? null : this.app.renderer.lastPickDistance / this.rig.scale;
      // Hover highlight from the first pointer (the same path the mouse takes).
      if (this.rays.keys().next().value === src) this.app.hoverId = id;
    }
    const len = v.hitLength ?? RAY_FREE_LENGTH;
    v.mesh.scale.set(RAY_WIDTH, RAY_WIDTH, Math.max(0.05, len));
    (v.mesh.material as MeshBasicMaterial).color.setHex(v.hitLength === null ? 0x4aa8ff : 0xffd24a);
  }

  // ------------------------------------------------------------------ AR hit test and reticle

  private buildReticle(): void {
    const geo = new RingGeometry(0.05, 0.07, 32).rotateX(-Math.PI / 2);
    const m = new Mesh(geo, new MeshBasicMaterial({ color: 0xffffff, depthTest: false, transparent: true, opacity: 0.9 }));
    m.visible = false;
    m.frustumCulled = false;
    m.renderOrder = 21;
    m.name = 'xray-xr-reticle';
    this.reticle = m;
    this.rigObj.add(m);
  }

  private async startHitTest(session: XRSession): Promise<void> {
    try {
      const viewer = await session.requestReferenceSpace('viewer');
      const src = await session.requestHitTestSource?.({ space: viewer });
      if (src && this.session === session) {
        this.hitSource = src;
        this.hitTestActive = true;
      }
    } catch {
      this.hitTestActive = false;
    }
    this.refreshStatus(true);
  }

  private updateReticle(frame: XRFrame, ref: XRReferenceSpace): void {
    if (!this.hitSource || !this.reticle) return;
    const results = frame.getHitTestResults(this.hitSource);
    const hit = results[0]?.getPose(ref);
    this.reticleOk = !!hit;
    if (hit) {
      const t = hit.transform;
      this.reticle.position.set(t.position.x, t.position.y, t.position.z);
      this.reticle.quaternion.set(t.orientation.x, t.orientation.y, t.orientation.z, t.orientation.w);
    }
    this.reticle.visible = !!hit && !this.placed;
  }

  // ------------------------------------------------------------------ status

  /** Text of the passes that the XR frame leaves out (the status line says so). */
  fallbacks(): string[] {
    return this.app.renderer.xrFallbacks();
  }

  private refreshStatus(force: boolean, now = performance.now()): void {
    if (!this.mode) return;
    if (!force && now - this.lastStatusNotify < 400) return;
    this.lastStatusNotify = now;
    const inputs = this.session ? this.session.inputSources.length : 0;
    const fb = this.fallbacks();
    const parts: string[] = [];
    if (this.mode === 'vr') {
      parts.push(`VR on, ${inputs} input source${inputs === 1 ? '' : 's'}`);
    } else if (this.field) {
      parts.push(this.field.statusText());
    } else {
      parts.push(
        this.placed
          ? `AR on, model placed at ${this.config.arScale}`
          : this.hitTestActive
            ? `AR on, ${this.reticleOk ? 'select to place the model at the ring' : 'point at a surface, then select to place the model'}`
            : 'AR on, no surface detection: select to place the model ahead of you',
      );
    }
    if (fb.length) parts.push(`left out: ${fb.join('; ')}`);
    this.status = parts.join('. ');
    this.notify();
  }

  state(): XrState {
    return {
      supported: { ...this.support },
      mode: this.mode,
      presenting: this.app.renderer.xrPresenting,
      status: this.status,
      rig: this.getRig(),
      placed: this.placed,
      arScale: this.config.arScale,
      fallbacks: this.mode ? this.fallbacks() : [],
      selects: this.selects,
      squeezes: this.squeezes,
      turns: this.turns,
      inputSources: this.session ? this.session.inputSources.length : 0,
      hitTest: this.mode === 'field' ? !!this.field?.state().hitTest.centre : this.hitTestActive,
      field: this.field ? this.field.state() : null,
    };
  }

  /** After the frame rendered (field snapshots render here, between two XR frames). */
  afterFrame(): void {
    this.field?.afterFrame();
  }

  /** The Object3D that holds the camera while a session runs (tests). */
  get rigObject(): Object3D {
    return this.rigObj;
  }
}
