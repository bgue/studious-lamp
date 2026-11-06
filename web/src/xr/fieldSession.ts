// Field AR (experimental): the model at real scale over the real building, registered by point pairs. XrManager
// (xr/session.ts) runs an immersive-ar session and hands the field logic to this controller: the registration steps, the
// hit-test sources (the screen centre and each controller), the WebXR anchor that holds the registration while the user
// walks, the saved sites, the nudges, the field looks, the cut around the user, the tapped element's card and clearance, the
// snapshots, the phone panel (xr/fieldOverlay.ts) and the in-scene text for headsets (xr/hud.ts). The maths is xr/field.ts.

import { CanvasTexture, Group, Mesh, MeshBasicMaterial, PerspectiveCamera, Ray, SphereGeometry, Sprite, SpriteMaterial, Vector3, WebGLRenderTarget, DoubleSide } from 'three';
import type { Object3D } from 'three';
import type { MeshBVH } from 'three-mesh-bvh';
import type { ViewerApp } from '../app';
import { hoverInfoSettings } from '../plugins/hoverInfo';
import { FLAG_HIDDEN } from '../types';
import type { ClassStyles } from '../types';
import { cardRows, formatValue, parsePatterns, propLabel, subtitleOf } from '../ui/hoverCard';
import {
  DEFAULT_EYE_HEIGHT, FIELD_MIN_PAIRS, FIELD_VIEWS, SITE_SCHEMA, cm, fieldClassStyles, fieldCutBox, followAnchor, loadSites, modelKeyOf, nudgeRotate,
  nudgeTranslate, saveSiteTo, setFloorHeight, signedM, snapToVertexInPlan, solveFieldRegistration, storeyAt, storeyFloors, viewAxes,
} from './field';
import type { FieldLevel, FieldPair, FieldSolution, FieldView, Pose, SiteRegistration } from './field';
import { FieldOverlay } from './fieldOverlay';
import type { FieldAction, OverlayModel } from './fieldOverlay';
import { TextHud } from './hud';
import { add, controllerRayToWorld, mul, poseToCamera, quatRotate, rigPoint, snapTurnStep } from './maths';
import type { Q4, Rig, SnapState, V3 } from './maths';

export type FieldStep = 'model' | 'real' | 'done';
export type AnchorState = 'none' | 'pending' | 'tracked' | 'lost' | 'unsupported';

export interface FieldConfig {
  view: FieldView;
  /** Half size of the cut box around the user, metres; 0 switches the radius cut off. */
  cutRadius: number;
  /** Cut at the ceiling of the storey the user stands on. */
  storeyCut: boolean;
  /** Master switch of the cut. */
  cut: boolean;
  /** Snap a model point to a vertex of the element within this plan distance, metres (0 = off). */
  snapRadius: number;
  /** Restore the newest saved site of the model at the start of a session. */
  restore: boolean;
  /** Turn the snapshots into BCF topics when the session ends (when the BCF plugin is there). */
  notesToBcf: boolean;
}

export const defaultFieldConfig = (): FieldConfig => ({ view: 'ghosted', cutRadius: 6, storeyCut: true, cut: true, snapRadius: 0.1, restore: true, notesToBcf: true });

export const NUDGE_STEPS = [0.01, 0.1] as const;
const ROTATE_STEP_DEG = [0.5, 2] as const;
const CUT_RADII = [2, 3, 4, 6, 8, 12, 20];

export interface FieldNote {
  id: number;
  time: string;
  /** The rendered overlay (model only: WebXR gives the page no camera pixels), PNG data URL with a transparent background. */
  png: string | null;
  width: number;
  height: number;
  /** Head pose in world (viewer) coordinates. */
  head: Pose;
  forward: V3;
  element: { id: number; globalId: string; name: string } | null;
  point: V3 | null;
  clearance: number | null;
  storey: string | null;
  text: string;
}

export interface FieldHost {
  readonly app: ViewerApp;
  getRig(): Rig;
  setRig(r: Rig): void;
  head(): { position: V3; quaternion: Q4 };
  rigObject(): Object3D;
  /** Status changed: refresh the status line and listeners. */
  changed(): void;
  exit(): void;
}

/** A surface pick that ignores ghosting (model points may sit on nearly invisible walls); hidden and cut parts do not count. */
export function pickSurface(app: ViewerApp, origin: V3, dir: V3): { id: number; point: V3 } | null {
  const g = app.loaded?.geometry;
  if (!g) return null;
  const r = app.renderer;
  const ray = new Ray(new Vector3(...origin), new Vector3(...dir).normalize());
  const { alpha, flags } = r.state;
  let near = 0;
  for (let i = 0; i < 256; i++) {
    const hit = g.bvh.raycastFirst(ray, DoubleSide, near, Infinity);
    if (!hit || hit.faceIndex == null) return null;
    const id = g.elementOfTriangle(hit.faceIndex);
    const clipped = (r as unknown as { cutByClip?(p: Vector3): boolean }).cutByClip?.(hit.point) ?? false;
    if (id >= 0 && (flags[id]! & FLAG_HIDDEN) === 0 && alpha[id]! >= 0 && !clipped) return { id, point: [hit.point.x, hit.point.y, hit.point.z] };
    near = hit.distance + 1e-4;
  }
  return null;
}

/** Closest point of an element's surface to `p` (world). */
export function closestOnElement(app: ViewerApp, id: number, p: V3): { point: V3; distance: number } | null {
  const sub = app.loaded?.geometry.subGeometry(id);
  const bvh = sub?.boundsTree as MeshBVH | undefined;
  if (!bvh) return null;
  const hit = bvh.closestPointToPoint(new Vector3(...p));
  if (!hit) return null;
  return { point: [hit.point.x, hit.point.y, hit.point.z], distance: hit.distance };
}

/** Snap a model point to the nearest vertex of its element in plan. */
export function snapModelPoint(app: ViewerApp, id: number, p: V3, radius: number): V3 {
  const g = app.loaded?.geometry;
  if (!g || radius <= 0) return p;
  const vr = g.vertexRanges[id];
  if (!vr || vr.count === 0) return p;
  const pos = g.geometry.getAttribute('position').array as ArrayLike<number>;
  return snapToVertexInPlan(pos, vr.start, vr.count, p, radius).point;
}

function marker(color: number, label: string, radius: number): Group {
  const g = new Group();
  const ball = new Mesh(new SphereGeometry(radius, 16, 12), new MeshBasicMaterial({ color, depthTest: false, transparent: true, opacity: 0.9 }));
  ball.renderOrder = 25;
  g.add(ball);
  const c = document.createElement('canvas');
  c.width = c.height = 64;
  const x = c.getContext('2d');
  if (x) {
    x.fillStyle = '#000a';
    x.beginPath();
    x.arc(32, 32, 30, 0, Math.PI * 2);
    x.fill();
    x.fillStyle = '#fff';
    x.font = 'bold 40px system-ui, sans-serif';
    x.textAlign = 'center';
    x.textBaseline = 'middle';
    x.fillText(label, 32, 34);
  }
  const sp = new Sprite(new SpriteMaterial({ map: new CanvasTexture(c), depthTest: false, transparent: true }));
  sp.scale.setScalar(radius * 4);
  sp.position.set(0, radius * 3, 0);
  sp.renderOrder = 26;
  g.add(sp);
  g.traverse((o) => (o.frustumCulled = false));
  g.name = 'xray-xr-field-marker';
  return g;
}

function disposeTree(o: Object3D): void {
  o.removeFromParent();
  o.traverse((c) => {
    const m = c as Mesh;
    m.geometry?.dispose();
    const mat = m.material as MeshBasicMaterial | undefined;
    mat?.map?.dispose();
    mat?.dispose();
  });
}

interface HitInfo {
  point: V3;
  horizontal: boolean;
  source: 'centre' | 'pointer';
  time: number;
}

interface XrAnchorLike {
  anchorSpace: XRSpace;
  delete?(): void;
  requestPersistentHandle?(): Promise<string>;
}

type SessionWithAnchors = XRSession & {
  restorePersistentAnchor?(uuid: string): Promise<XrAnchorLike>;
  domOverlayState?: { type: string } | null;
  requestHitTestSource?(o: { space: XRSpace }): Promise<XRHitTestSource> | undefined;
};
type FrameWithAnchors = XRFrame & { createAnchor?(pose: XRRigidTransform, space: XRSpace): Promise<XrAnchorLike>; trackedAnchors?: Set<unknown> };

export interface FieldStateView {
  step: FieldStep;
  registered: boolean;
  pairs: Array<{ model: V3 | null; real: V3 | null }>;
  residuals: number[];
  rms: number | null;
  warnings: string[];
  anchor: AnchorState;
  anchorHandle: string | null;
  restoredFrom: string | null;
  view: FieldView;
  appliedView: FieldView;
  cut: { min: V3; max: V3 } | null;
  storey: string | null;
  feetY: number | null;
  eyeHeight: number;
  floorFromHit: boolean;
  selected: { id: number; name: string; globalId: string } | null;
  clearance: { device: number | null; point: number | null } | null;
  notes: number;
  domOverlay: string | null;
  hitTest: { centre: boolean; pointers: number };
  lastHit: V3 | null;
  nudgeStep: number;
  instruction: string;
  /** The last message of the panel (what happened, or what to do about a problem). */
  message: string;
}

export class FieldController {
  pairs: FieldPair[] = [];
  step: FieldStep = 'model';
  registered = false;
  solution: FieldSolution | null = null;
  anchorState: AnchorState = 'none';
  anchorHandle: string | null = null;
  restoredFrom: string | null = null;
  readonly notes: FieldNote[] = [];
  nudgeIndex = 0;
  domOverlay: string | null = null;
  message = '';

  private session: SessionWithAnchors | null = null;
  private viewerSource: XRHitTestSource | null = null;
  private readonly pointerSources = new Map<XRInputSource, XRHitTestSource | 'pending' | 'failed'>();
  private readonly hits = new Map<'centre' | XRInputSource, HitInfo>();
  private lastHit: HitInfo | null = null;
  private lastSelectSource: XRInputSource | null = null;
  private anchor: XrAnchorLike | null = null;
  private anchorThen: Pose | null = null;
  private rigAtAnchor: Rig | null = null;
  private pendingAnchorAt: V3 | null = null;
  private anchorTries = 0;
  private restoreHandle: string | null = null;
  private addingOne = false;
  private floorLocalY: number | null = null;
  private levels: FieldLevel[] = [];
  private storeyIdx = -1;
  private feetY: number | null = null;
  private ceilingY: number | null = null;
  private cutBox: { min: V3; max: V3 } | null = null;
  private lastCutAt = 0;
  private lastCutHead: V3 | null = null;
  private appliedView: FieldView | null = null;
  private savedStyles: { styles: ClassStyles; aliases: Record<string, string[]> } | null = null;
  private savedSection: unknown = null;
  private selected: number | null = null;
  private selectedPoint: V3 | null = null;
  private clearance: { device: number | null; point: number | null } | null = null;
  private lastClearanceAt = 0;
  private snapshotPending = false;
  private overlay: FieldOverlay | null = null;
  private hud: TextHud | null = null;
  private readonly modelMarkers: Group = new Group();
  private readonly realMarkers: Group = new Group();
  private markerKey = '';
  private reticle: Mesh | null = null;
  private readonly stickState = new Map<string, SnapState>();
  private readonly buttonsDown = new Map<string, boolean>();
  private lastUi = 0;
  private site: SiteRegistration | null = null;

  constructor(
    private readonly host: FieldHost,
    readonly config: FieldConfig,
    draft: V3[],
  ) {
    this.pairs = draft.map((p) => ({ model: [...p], real: null }));
    this.modelMarkers.name = 'xray-xr-field-model-points';
    this.realMarkers.name = 'xray-xr-field-room-points';
  }

  private get app(): ViewerApp {
    return this.host.app;
  }

  // ------------------------------------------------------------------ lifecycle

  /** Called once the session runs (the rig exists and the camera sits in it). */
  start(session: XRSession, ref: XRReferenceSpace | null): void {
    this.session = session as SessionWithAnchors;
    this.domOverlay = this.session.domOverlayState?.type ?? null;
    const m = this.app.loaded?.model;
    this.levels = m ? storeyFloors(m) : [];
    // look and section: remember what the user had
    const c = this.app.controller;
    this.savedStyles = { styles: c.settings.classStyles, aliases: c.settings.materialAliases };
    const sec = window.__xraySection;
    this.savedSection = sec ? JSON.parse(JSON.stringify(sec.config)) : null;
    this.app.renderer.scene.add(this.modelMarkers);
    this.host.rigObject().add(this.realMarkers);
    this.buildReticle();
    this.hud = new TextHud(this.host.rigObject());
    this.overlay?.show(true);
    void this.startHitTest(session);
    // restore a saved site, else start from the model points picked before the session
    const saved = this.config.restore && m ? loadSites(storage(), this.app.modelName, modelKeyOf(m))[0] : undefined;
    if (saved) this.restoreSite(saved);
    else this.step = this.modelPoints() >= FIELD_MIN_PAIRS ? 'real' : 'model';
    void ref;
    this.applyLook(true);
    this.changed();
  }

  /** The DOM overlay root to pass to requestSession (built before the session starts). */
  overlayRoot(): HTMLElement {
    if (!this.overlay) this.overlay = new FieldOverlay((a, arg) => this.act(a, arg));
    if (!this.overlay.root.isConnected) document.body.appendChild(this.overlay.root);
    return this.overlay.root;
  }

  /** Session ended: restore the look and the section, remove what was added, and hand back the notes. */
  end(): FieldNote[] {
    for (const s of this.pointerSources.values()) if (typeof s === 'object') try { s.cancel(); } catch { /* gone */ }
    this.pointerSources.clear();
    try { this.viewerSource?.cancel(); } catch { /* gone */ }
    this.viewerSource = null;
    this.hits.clear();
    try { this.anchor?.delete?.(); } catch { /* gone */ }
    this.anchor = null;
    disposeTree(this.modelMarkers);
    disposeTree(this.realMarkers);
    if (this.reticle) disposeTree(this.reticle);
    this.reticle = null;
    this.hud?.dispose();
    this.hud = null;
    this.overlay?.show(false);
    const c = this.app.controller;
    if (this.savedStyles && this.appliedView !== null && this.appliedView !== 'full') {
      c.setClassStyles(this.savedStyles.styles, this.savedStyles.aliases);
      this.app.reclassify();
    }
    this.appliedView = null;
    const sec = window.__xraySection;
    if (sec && this.savedSection && this.cutBox) sec.set(this.savedSection);
    this.cutBox = null;
    this.session = null;
    return [...this.notes];
  }

  // ------------------------------------------------------------------ hit test

  private async startHitTest(session: XRSession): Promise<void> {
    const s = session as SessionWithAnchors;
    try {
      const viewer = await session.requestReferenceSpace('viewer');
      const src = await s.requestHitTestSource?.({ space: viewer });
      if (src && this.session === s) this.viewerSource = src;
    } catch {
      this.viewerSource = null;
    }
    this.changed();
  }

  private pointerSource(src: XRInputSource): XRHitTestSource | null {
    const s = this.session;
    if (!s || src.targetRayMode !== 'tracked-pointer' || !src.targetRaySpace) return null;
    const cur = this.pointerSources.get(src);
    if (cur === undefined) {
      this.pointerSources.set(src, 'pending');
      const p = s.requestHitTestSource?.({ space: src.targetRaySpace });
      if (!p) this.pointerSources.set(src, 'failed');
      else
        p.then(
          (h) => (this.session === s ? this.pointerSources.set(src, h) : h.cancel()),
          () => this.pointerSources.set(src, 'failed'),
        );
      return null;
    }
    return typeof cur === 'object' ? cur : null;
  }

  private readHit(frame: XRFrame, ref: XRReferenceSpace, src: XRHitTestSource, key: 'centre' | XRInputSource, now: number): void {
    let results: readonly XRHitTestResult[] = [];
    try {
      results = frame.getHitTestResults(src);
    } catch {
      results = [];
    }
    const pose = results[0]?.getPose(ref);
    if (!pose) {
      this.hits.delete(key);
      return;
    }
    const t = pose.transform;
    const o = t.orientation;
    const up = quatRotate([o.x, o.y, o.z, o.w], [0, 1, 0]);
    const info: HitInfo = { point: [t.position.x, t.position.y, t.position.z], horizontal: up[1] > 0.9, source: key === 'centre' ? 'centre' : 'pointer', time: now };
    this.hits.set(key, info);
    // a horizontal surface 0.4 to 2.5 m below the eyes is the floor
    const head = this.host.head().position;
    const below = head[1] - info.point[1];
    if (info.horizontal && below > 0.4 && below < 2.5) this.floorLocalY = info.point[1];
  }

  /** The hit to use now: the pointer that selected (headsets), the screen centre for a screen tap (phones); with no source, a controller's hit when there is one, else the centre. */
  private currentHit(from?: XRInputSource | null): HitInfo | null {
    if (from?.targetRayMode === 'tracked-pointer') {
      const h = this.hits.get(from);
      if (h) return h;
    }
    if (from && from.targetRayMode !== 'tracked-pointer') return this.hits.get('centre') ?? null;
    for (const [k, v] of this.hits) if (k !== 'centre') return v;
    return this.hits.get('centre') ?? null;
  }

  // ------------------------------------------------------------------ frame

  frame(frame: XRFrame, ref: XRReferenceSpace, now: number): void {
    const s = this.session;
    if (!s) return;
    if (this.viewerSource) this.readHit(frame, ref, this.viewerSource, 'centre', now);
    const live = new Set<XRInputSource>();
    for (const src of s.inputSources) {
      live.add(src);
      const hs = this.pointerSource(src);
      if (hs) this.readHit(frame, ref, hs, src, now);
      this.readGamepad(src);
    }
    for (const k of [...this.hits.keys()]) if (k !== 'centre' && !live.has(k)) this.hits.delete(k);
    this.lastHit = this.currentHit(this.lastSelectSource);
    this.updateAnchor(frame as FrameWithAnchors, ref);
    this.updateReticle();
    this.updateMarkers();
    if (now - this.lastUi > 200) {
      this.lastUi = now;
      this.updateStorey();
      this.updateCut(now);
      this.updateClearance(now);
      this.renderUi();
    }
    const hd = this.host.head();
    this.hud?.follow(hd.position, hd.quaternion, this.domOverlay === null);
  }

  private updateAnchor(frame: FrameWithAnchors, ref: XRReferenceSpace): void {
    const s = this.session;
    if (!s) return;
    if (this.restoreHandle && s.restorePersistentAnchor) {
      const h = this.restoreHandle;
      this.restoreHandle = null;
      this.anchorState = 'pending';
      s.restorePersistentAnchor(h).then(
        (a) => {
          if (this.session !== s) return;
          this.anchor = a;
          this.anchorHandle = h;
        },
        () => this.restoreFallback('the saved anchor was not found here'),
      );
    }
    if (this.pendingAnchorAt) {
      const at = this.pendingAnchorAt;
      this.pendingAnchorAt = null;
      if (typeof frame.createAnchor !== 'function' || typeof XRRigidTransform === 'undefined' || !this.anchorsEnabled()) {
        this.anchorState = 'unsupported';
      } else {
        this.anchorState = 'pending';
        const rig = this.host.getRig();
        const asked = performance.now();
        this.anchorAskedAt = asked;
        // a request that never settles counts as no anchors after 4 s
        setTimeout(() => {
          if (this.anchorState === 'pending' && this.anchorAskedAt === asked && this.session === s) {
            this.anchorState = 'unsupported';
            this.changed();
          }
        }, 4000);
        try {
          frame.createAnchor(new XRRigidTransform({ x: at[0], y: at[1], z: at[2] }), ref).then(
            (a) => {
              if (this.session !== s) return void a.delete?.();
              try { this.anchor?.delete?.(); } catch { /* gone */ }
              this.anchor = a;
              this.anchorHandle = null;
              this.anchorThen = { position: [...at], quaternion: [0, 0, 0, 1] };
              this.rigAtAnchor = rig;
              this.anchorState = 'tracked';
              this.changed();
            },
            () => {
              this.anchorState = this.anchorTries++ < 2 ? 'none' : 'unsupported';
              if (this.anchorState === 'none') this.pendingAnchorAt = at;
              this.changed();
            },
          );
        } catch {
          this.anchorState = 'unsupported';
        }
      }
    }
    const a = this.anchor;
    if (!a) return;
    if (frame.trackedAnchors && !frame.trackedAnchors.has(a)) {
      if (this.anchorState === 'tracked') {
        this.anchorState = 'lost';
        this.changed();
      }
      return;
    }
    const p = frame.getPose(a.anchorSpace, ref);
    if (!p) return;
    const t = p.transform;
    const now: Pose = { position: [t.position.x, t.position.y, t.position.z], quaternion: [t.orientation.x, t.orientation.y, t.orientation.z, t.orientation.w] };
    if (!this.anchorThen && this.site?.anchor) {
      // a restored anchor: the saved rig belongs to the saved anchor pose
      this.anchorThen = this.site.anchor.pose;
      this.rigAtAnchor = { position: [...this.site.rig.position], yaw: this.site.rig.yaw, scale: 1 };
      this.registered = true;
      this.step = 'done';
      this.applyLook(false);
    }
    if (!this.anchorThen || !this.rigAtAnchor) return;
    if (this.anchorState !== 'tracked') {
      this.anchorState = 'tracked';
      this.changed();
    }
    this.host.setRig(followAnchor(this.rigAtAnchor, this.anchorThen, now));
    this.currentAnchorPose = now;
  }

  private currentAnchorPose: Pose | null = null;
  private anchorAskedAt = 0;

  /** False when the session says it runs without the anchors feature (enabledFeatures is newer than anchors; unknown counts as yes). */
  private anchorsEnabled(): boolean {
    const ef = (this.session as unknown as { enabledFeatures?: readonly string[] } | null)?.enabledFeatures;
    return !ef || ef.includes('anchors');
  }

  /** After a manual change of the rig: the anchor keeps the new rig from now on. */
  private rebaseAnchor(): void {
    if (this.anchor && this.currentAnchorPose && this.anchorState === 'tracked') {
      this.anchorThen = this.currentAnchorPose;
      this.rigAtAnchor = this.host.getRig();
    } else if (this.anchorThen) {
      // the anchor is not tracked now: keep the old base but move it with the change
      this.rigAtAnchor = this.host.getRig();
    }
  }

  // ------------------------------------------------------------------ input

  /** A select (tap, trigger, pinch). */
  onSelect(e: XRInputSourceEvent, ref: XRReferenceSpace | null): void {
    this.lastSelectSource = e.inputSource;
    if (this.step === 'model') {
      const ray = this.rayOf(e, ref);
      if (ray) this.pickModelPoint(ray.origin, ray.direction);
      return;
    }
    if (this.step === 'real') {
      this.markRealPoint(e.inputSource);
      return;
    }
    const ray = this.rayOf(e, ref);
    if (!ray) return;
    const id = this.app.renderer.pickRay(new Vector3(...ray.origin), new Vector3(...ray.direction));
    this.select(id, id === null ? null : add(ray.origin, mul(ray.direction, this.app.renderer.lastPickDistance)));
  }

  /** A squeeze: cycle the looks (headsets have no panel). */
  onSqueeze(): void {
    if (this.step === 'model' && this.modelPoints() >= FIELD_MIN_PAIRS) this.act('toReal');
    else this.act('view', FIELD_VIEWS[(FIELD_VIEWS.indexOf(this.config.view) + 1) % FIELD_VIEWS.length]);
  }

  private rayOf(e: XRInputSourceEvent, ref: XRReferenceSpace | null): { origin: V3; direction: V3 } | null {
    if (!ref) return null;
    const pose = e.frame.getPose(e.inputSource.targetRaySpace, ref);
    if (!pose) return null;
    const p = pose.transform.position;
    const o = pose.transform.orientation;
    return controllerRayToWorld(this.host.getRig(), [p.x, p.y, p.z], [o.x, o.y, o.z, o.w]);
  }

  /** Centre ray of the head in world coordinates (the "Mark point" button on a phone in the model step). */
  private headRay(): { origin: V3; direction: V3 } {
    const h = this.host.head();
    return controllerRayToWorld(this.host.getRig(), h.position, h.quaternion);
  }

  private readGamepad(src: XRInputSource): void {
    const gp = src.gamepad;
    if (!gp || src.targetRayMode !== 'tracked-pointer') return;
    const hand = src.handedness;
    const press = (i: number, run: () => void): void => {
      const k = `${hand}:${i}`;
      const down = !!gp.buttons[i]?.pressed;
      if (down && !this.buttonsDown.get(k)) run();
      this.buttonsDown.set(k, down);
    };
    if (hand === 'right') {
      press(4, () => this.act('snapshot'));
      press(5, () => this.act('reregister'));
    } else if (hand === 'left') {
      press(4, () => this.act('cut'));
      press(5, () => this.act('floor'));
    }
    if (!this.registered || gp.axes.length < 2) return;
    const ax = gp.axes.length >= 4 ? gp.axes[2]! : gp.axes[0]!;
    const ay = gp.axes.length >= 4 ? gp.axes[3]! : gp.axes[1]!;
    const flick = (axis: string, v: number): -1 | 0 | 1 => {
      const k = `${hand}:${axis}`;
      let st = this.stickState.get(k);
      if (!st) this.stickState.set(k, (st = { armed: true }));
      return snapTurnStep(st, v);
    };
    const sx = flick('x', ax);
    const sy = flick('y', ay);
    if (hand === 'left') {
      if (sx) this.nudge(sx > 0 ? 'right' : 'left');
      if (sy) this.nudge(sy < 0 ? 'fwd' : 'back');
    } else if (hand === 'right') {
      if (sx) this.nudge(sx > 0 ? 'cw' : 'ccw');
      if (sy) this.nudge(sy < 0 ? 'up' : 'down');
    }
  }

  // ------------------------------------------------------------------ registration

  private modelPoints(): number {
    return this.pairs.filter((p) => p.model).length;
  }

  private pickModelPoint(origin: V3, dir: V3): boolean {
    const hit = pickSurface(this.app, origin, dir);
    if (!hit) {
      this.message = 'No model surface under the ray: aim at a wall corner, a column or a floor mark.';
      this.changed();
      return false;
    }
    this.addModelPoint(snapModelPoint(this.app, hit.id, hit.point, this.config.snapRadius));
    return true;
  }

  /** Add a model point (world). In "+ Pair" mode the next room tap completes it. */
  addModelPoint(p: V3): void {
    this.pairs.push({ model: [...p], real: null });
    this.message = `Model point ${this.pairs.length} set.`;
    if (this.addingOne) {
      this.addingOne = false;
      this.step = 'real';
    }
    this.changed();
  }

  /** Record the hit of `from` (or the screen centre) as the room point of the next pair. */
  private markRealPoint(from?: XRInputSource | null): boolean {
    const hit = this.currentHit(from ?? null);
    if (!hit) {
      this.message = 'No surface found: move the device slowly so it can see the floor and the walls, then try again.';
      this.changed();
      return false;
    }
    return this.addRealPoint(hit.point);
  }

  /** Room point (XR reference space) of the first pair that has none; solves when every pair is complete. */
  addRealPoint(p: V3): boolean {
    const next = this.pairs.find((q) => q.model && !q.real);
    if (!next) {
      this.message = 'Every model point already has its room point. Add a pair first.';
      this.changed();
      return false;
    }
    next.real = [...p];
    this.message = `Room point ${this.pairs.indexOf(next) + 1} set.`;
    if (!this.pairs.some((q) => q.model && !q.real)) this.solve();
    this.changed();
    return true;
  }

  /** Solve from the complete pairs and apply. */
  solve(): FieldSolution | null {
    const complete = this.pairs.filter((p) => p.model && p.real).length;
    if (complete < FIELD_MIN_PAIRS) return null;
    const s = solveFieldRegistration(this.pairs);
    this.solution = s;
    if (!s.ok) {
      this.message = s.warnings.join(' ');
      this.changed();
      return s;
    }
    this.host.setRig(s.rig);
    this.registered = true;
    this.step = 'done';
    this.restoredFrom = null;
    this.site = null;
    // anchor at the centroid of the room points: the registration then follows the device's map corrections
    const reals = this.pairs.filter((p) => p.real).map((p) => p.real!);
    const c: V3 = reals.reduce((a, b) => add(a, b), [0, 0, 0] as V3).map((v) => v / reals.length) as V3;
    this.anchorThen = null;
    this.rigAtAnchor = null;
    this.anchorTries = 0;
    this.pendingAnchorAt = c;
    this.message = s.warnings.length ? s.warnings.join(' ') : `Registered with ${s.used} pairs.`;
    this.applyLook(false);
    this.app.runSightlinesNow();
    this.changed();
    return s;
  }

  private undo(): void {
    if (this.addingOne) {
      this.addingOne = false;
      this.step = this.registered ? 'done' : 'real';
    } else {
      const last = [...this.pairs].reverse().find((p) => p.model);
      if (!last) return;
      if (last.real && this.step !== 'model') last.real = null;
      else this.pairs.splice(this.pairs.lastIndexOf(last), 1);
      if (this.step === 'done') this.step = 'real';
    }
    this.message = 'Last point removed.';
    this.applyLook(false);
    this.changed();
  }

  private reregister(): void {
    for (const p of this.pairs) p.real = null;
    this.step = this.modelPoints() >= FIELD_MIN_PAIRS ? 'real' : 'model';
    this.message = this.step === 'real' ? 'Tap the room points again, in the same order.' : 'Pick at least 2 model points first.';
    this.applyLook(false);
    this.changed();
  }

  private floorHere(): void {
    const hit = this.currentHit(this.lastSelectSource);
    if (!hit || !this.registered) {
      this.message = 'Aim the ring at the floor first.';
      this.changed();
      return;
    }
    const rig = this.host.getRig();
    const world = rigPoint(rig, hit.point);
    const st = storeyAt(this.levels, world[1]);
    if (!st.level) {
      this.message = 'The model has no storeys.';
      this.changed();
      return;
    }
    this.host.setRig(setFloorHeight(rig, hit.point[1], st.level.floorY));
    this.floorLocalY = hit.point[1];
    this.rebaseAnchor();
    this.message = `Floor of ${st.level.name} set at the ring.`;
    this.changed();
  }

  // ------------------------------------------------------------------ saved sites

  private restoreSite(site: SiteRegistration): void {
    this.site = site;
    this.restoredFrom = site.name;
    this.pairs = site.pairs.map((p) => ({ model: [...p.model], real: null }));
    if (site.anchor?.handle && this.session?.restorePersistentAnchor && this.anchorsEnabled()) {
      this.restoreHandle = site.anchor.handle;
      this.step = 'real';
      this.message = `Looking for the saved anchor of "${site.name}". Or tap the ${this.pairs.length} saved points again.`;
    } else this.restoreFallback('this browser keeps no anchors between sessions');
  }

  private restoreFallback(why: string): void {
    this.anchorState = this.anchor ? this.anchorState : 'none';
    this.step = 'real';
    this.message = `Saved site "${this.site?.name ?? ''}": ${why}. Tap the ${this.pairs.length} saved points again, in order.`;
    this.changed();
  }

  /** Save the registration (localStorage) with a persistent anchor handle where the browser offers one. */
  async saveSite(name?: string): Promise<SiteRegistration | null> {
    const m = this.app.loaded?.model;
    if (!this.registered || !m) return null;
    const rig = this.rigAtAnchor ?? this.host.getRig();
    let handle: string | undefined;
    if (this.anchor?.requestPersistentHandle) {
      try {
        handle = await this.anchor.requestPersistentHandle();
      } catch {
        handle = undefined;
      }
    }
    const now = new Date().toISOString();
    const site: SiteRegistration = {
      schema: SITE_SCHEMA,
      id: `site-${Date.now().toString(36)}`,
      name: name ?? `${this.app.modelName} ${now.slice(0, 16).replace('T', ' ')}`,
      model: this.app.modelName,
      modelKey: modelKeyOf(m),
      created: now,
      pairs: this.pairs.filter((p) => p.model).map((p) => ({ model: [...p.model!], real: p.real ? [...p.real] : null })),
      rig: { position: [...rig.position], yaw: rig.yaw },
      residuals: this.solution?.residuals ?? [],
      rms: this.solution?.rms ?? NaN,
      ...(this.anchorThen ? { anchor: { pose: this.anchorThen, ...(handle ? { handle } : {}) } } : {}),
    };
    const ok = saveSiteTo(storage(), site);
    this.site = site;
    this.anchorHandle = handle ?? null;
    this.message = ok ? `Site saved${handle ? ' with a persistent anchor' : ': re-tap 2 points to restore it next time'}.` : 'The browser refused to save the site.';
    this.changed();
    return ok ? site : null;
  }

  get lastSite(): SiteRegistration | null {
    return this.site;
  }

  // ------------------------------------------------------------------ nudges

  nudge(kind: string): void {
    if (!this.registered) return;
    const step = NUDGE_STEPS[this.nudgeIndex]!;
    const rot = (ROTATE_STEP_DEG[this.nudgeIndex]! * Math.PI) / 180;
    const { forward, right } = viewAxes(this.host.head().quaternion);
    let rig = this.host.getRig();
    const pivot = this.pivot();
    switch (kind) {
      case 'left': rig = nudgeTranslate(rig, mul(right, -step)); break;
      case 'right': rig = nudgeTranslate(rig, mul(right, step)); break;
      case 'fwd': rig = nudgeTranslate(rig, mul(forward, step)); break;
      case 'back': rig = nudgeTranslate(rig, mul(forward, -step)); break;
      case 'up': rig = nudgeTranslate(rig, [0, step, 0]); break;
      case 'down': rig = nudgeTranslate(rig, [0, -step, 0]); break;
      case 'ccw': rig = nudgeRotate(rig, pivot, rot); break;
      case 'cw': rig = nudgeRotate(rig, pivot, -rot); break;
      default: return;
    }
    this.host.setRig(rig);
    this.rebaseAnchor();
    this.app.runSightlinesNow();
    this.message = `Nudged ${kind} by ${kind === 'cw' || kind === 'ccw' ? `${ROTATE_STEP_DEG[this.nudgeIndex]} degrees` : cm(step)}.`;
    this.changed();
  }

  /** Turn pivot: the centroid of the room points, else the ring, else the head. */
  private pivot(): V3 {
    const reals = this.pairs.filter((p) => p.real).map((p) => p.real!);
    if (reals.length) return reals.reduce((a, b) => add(a, b), [0, 0, 0] as V3).map((v) => v / reals.length) as V3;
    return this.lastHit?.point ?? this.host.head().position;
  }

  // ------------------------------------------------------------------ looks and cut

  /** The look in force: the full model while picking model points (the walls must be visible to pick them). */
  private wantedView(): FieldView {
    return this.step === 'model' ? 'full' : this.config.view;
  }

  applyLook(force: boolean): void {
    const v = this.wantedView();
    if (!force && v === this.appliedView) return;
    const c = this.app.controller;
    const base = this.savedStyles;
    if (!base) return;
    const present = [...new Set(c.model.elements.map((e) => e.ifcClass))];
    const st = fieldClassStyles(base.styles, present, c.settings.classification.focusClasses, c.settings.classification.ctxClasses, v);
    if (v !== this.appliedView) {
      c.setClassStyles(st, base.aliases);
      this.app.reclassify();
    }
    this.appliedView = v;
  }

  private headWorld(): V3 {
    return rigPoint(this.host.getRig(), this.host.head().position);
  }

  private eyeHeight(): number {
    if (this.floorLocalY === null) return DEFAULT_EYE_HEIGHT;
    const e = this.host.head().position[1] - this.floorLocalY;
    return e > 0.3 && e < 2.5 ? e : DEFAULT_EYE_HEIGHT;
  }

  private updateStorey(): void {
    const feet = this.headWorld()[1] - this.eyeHeight();
    this.feetY = feet;
    const st = storeyAt(this.levels, feet);
    this.storeyIdx = st.index;
    this.ceilingY = st.ceilingY;
  }

  private updateCut(now: number, force = false): void {
    const sec = window.__xraySection;
    if (!sec) return;
    const active = this.config.cut && this.registered && this.step !== 'model';
    const head = this.headWorld();
    if (!active) {
      if (this.cutBox && this.savedSection) {
        sec.set(this.savedSection);
        this.cutBox = null;
      }
      return;
    }
    const moved = !this.lastCutHead || Math.hypot(head[0] - this.lastCutHead[0], head[2] - this.lastCutHead[2]) > 0.25;
    const level = this.levels[this.storeyIdx];
    const box = this.app.loaded?.geometry.totalBounds();
    if (!box || box.isEmpty()) return;
    const want = fieldCutBox(head, { radius: this.config.cutRadius, storeyCut: this.config.storeyCut }, level ? { floorY: level.floorY, ceilingY: this.ceilingY } : null, [
      [box.min.x, box.min.y, box.min.z],
      [box.max.x, box.max.y, box.max.z],
    ]);
    const sameY = this.cutBox && want && Math.abs(this.cutBox.min[1] - want.min[1]) < 1e-6 && Math.abs(this.cutBox.max[1] - want.max[1]) < 1e-6;
    if (!force && !moved && sameY && now - this.lastCutAt < 5000) return;
    this.lastCutAt = now;
    this.lastCutHead = head;
    if (!want) {
      if (this.cutBox && this.savedSection) sec.set(this.savedSection);
      this.cutBox = null;
      return;
    }
    this.cutBox = want;
    sec.set({ box: { enabled: true, min: want.min, max: want.max }, caps: false, showHandles: false });
  }

  // ------------------------------------------------------------------ selection, clearance, snapshot

  /** Select an element (or clear with null) and measure its clearance. `point` is where the ray met it (world). */
  select(id: number | null, point: V3 | null = null): void {
    if (id === null) {
      this.selected = null;
      this.clearance = null;
      this.app.clearSelection();
    } else {
      this.selected = id;
      this.selectedPoint = point;
      this.app.selectIds([id], false);
      this.measure();
    }
    this.changed();
  }

  /** Clearance of the selected element from the device and from the ring (the last hit-test point). */
  measure(): { device: number | null; point: number | null } | null {
    const id = this.selected;
    if (id === null) {
      this.message = 'Tap an element first.';
      this.changed();
      return null;
    }
    const dev = closestOnElement(this.app, id, this.headWorld());
    const hit = this.lastHit ? rigPoint(this.host.getRig(), this.lastHit.point) : null;
    const pt = hit ? closestOnElement(this.app, id, hit) : null;
    this.clearance = { device: dev?.distance ?? null, point: pt?.distance ?? null };
    return this.clearance;
  }

  private updateClearance(now: number): void {
    if (this.selected === null || now - this.lastClearanceAt < 400) return;
    this.lastClearanceAt = now;
    this.measure();
  }

  /** Ask for a snapshot; it is rendered after the next XR frame (afterFrame). */
  snapshot(): void {
    this.snapshotPending = true;
  }

  afterFrame(): void {
    if (!this.snapshotPending || !this.session) return;
    this.snapshotPending = false;
    const shot = this.renderOverlay();
    const h = this.host.head();
    const rig = this.host.getRig();
    const cam = poseToCamera(rig, h.position, h.quaternion);
    const e = this.selected !== null ? this.app.loaded?.model.elements[this.selected] : undefined;
    const level = this.levels[this.storeyIdx];
    const note: FieldNote = {
      id: this.notes.length + 1,
      time: new Date().toISOString(),
      png: shot?.png ?? null,
      width: shot?.width ?? 0,
      height: shot?.height ?? 0,
      head: { position: cam.position, quaternion: cam.quaternion },
      forward: cam.forward,
      element: e ? { id: e.id, globalId: e.globalId, name: e.name || e.ifcClass } : null,
      point: this.selectedPoint ?? (this.lastHit ? rigPoint(rig, this.lastHit.point) : null),
      clearance: this.clearance?.device ?? null,
      storey: level?.name ?? null,
      text: this.solution ? `registration rms ${cm(this.solution.rms)}` : this.restoredFrom ? `registration restored from ${this.restoredFrom}` : 'not registered',
    };
    this.notes.push(note);
    this.message = `Snapshot ${note.id} kept${shot ? '' : ' (pose only, the picture could not be read)'}. Camera pixels are not available to the page.`;
    this.changed();
  }

  /** Render one mono view from the first XR view into a private target and read it back (the model layer only). */
  private renderOverlay(): { png: string; width: number; height: number } | null {
    const r = this.app.renderer;
    const three = r.renderer;
    const xrCam = three.xr.getCamera();
    const view = xrCam.cameras[0] ?? xrCam;
    const P = view.projectionMatrix;
    const aspect = Math.abs(P.elements[5]! / (P.elements[0]! || 1)) || 1;
    const maxSide = 1024;
    const w = aspect >= 1 ? maxSide : Math.max(16, Math.round(maxSide * aspect));
    const h = aspect >= 1 ? Math.max(16, Math.round(maxSide / aspect)) : maxSide;
    const cam = new PerspectiveCamera();
    view.updateMatrixWorld?.();
    view.matrixWorld.decompose(cam.position, cam.quaternion, cam.scale);
    cam.updateMatrixWorld(true);
    cam.projectionMatrix.copy(P);
    cam.projectionMatrixInverse.copy(P).invert();
    const rt = new WebGLRenderTarget(w, h);
    const prevRt = three.getRenderTarget();
    const prevXr = three.xr.enabled;
    const hidden: Object3D[] = [];
    for (const o of this.host.rigObject().children) if (o.visible && o !== r.camera) (hidden.push(o), (o.visible = false));
    try {
      three.xr.enabled = false;
      three.setRenderTarget(rt);
      three.clear();
      three.render(r.scene, cam);
      const buf = new Uint8Array(w * h * 4);
      three.readRenderTargetPixels(rt, 0, 0, w, h, buf);
      const canvas = document.createElement('canvas');
      canvas.width = w;
      canvas.height = h;
      const g = canvas.getContext('2d');
      if (!g) return null;
      const img = g.createImageData(w, h);
      const row = w * 4;
      for (let y = 0; y < h; y++) img.data.set(buf.subarray((h - 1 - y) * row, (h - y) * row), y * row);
      g.putImageData(img, 0, 0);
      return { png: canvas.toDataURL('image/png'), width: w, height: h };
    } catch {
      return null;
    } finally {
      three.setRenderTarget(prevRt);
      three.xr.enabled = prevXr;
      for (const o of hidden) o.visible = true;
      rt.dispose();
    }
  }

  // ------------------------------------------------------------------ actions (panel, buttons)

  act(a: FieldAction, arg?: string): void {
    switch (a) {
      case 'mark':
        if (this.step === 'model') {
          const ray = this.headRay();
          this.pickModelPoint(ray.origin, ray.direction);
        } else if (this.step === 'real') this.markRealPoint(null);
        break;
      case 'undo': this.undo(); break;
      case 'toReal':
        if (this.modelPoints() >= FIELD_MIN_PAIRS || (this.registered && this.pairs.some((p) => p.model && !p.real))) {
          this.step = 'real';
          this.addingOne = false;
          this.applyLook(false);
          this.message = 'Now tap the same points in the room, in the same order.';
        } else this.message = `Pick at least ${FIELD_MIN_PAIRS} model points.`;
        this.changed();
        break;
      case 'addPair':
        this.addingOne = true;
        this.step = 'model';
        this.message = 'Pick 1 more model point, then tap it in the room.';
        this.applyLook(false);
        this.changed();
        break;
      case 'reregister': this.reregister(); break;
      case 'floor': this.floorHere(); break;
      case 'save': void this.saveSite(); break;
      case 'view':
        if (arg && (FIELD_VIEWS as readonly string[]).includes(arg)) {
          this.config.view = arg as FieldView;
          this.applyLook(false);
          this.message = `Look: ${arg}.`;
          this.changed();
        }
        break;
      case 'cut':
        this.config.cut = !this.config.cut;
        this.updateCut(performance.now(), true);
        this.changed();
        break;
      case 'radius': {
        const i = CUT_RADII.findIndex((r) => r >= this.config.cutRadius);
        const j = Math.max(0, Math.min(CUT_RADII.length - 1, (i < 0 ? CUT_RADII.length - 1 : i) + (arg === '-1' ? -1 : 1)));
        this.config.cutRadius = CUT_RADII[j]!;
        this.updateCut(performance.now(), true);
        this.changed();
        break;
      }
      case 'nudge': if (arg) this.nudge(arg); break;
      case 'step':
        this.nudgeIndex = (this.nudgeIndex + 1) % NUDGE_STEPS.length;
        this.changed();
        break;
      case 'measure': this.measure(); this.changed(); break;
      case 'snapshot': this.snapshot(); break;
      case 'clear': this.select(null); break;
      case 'exit': this.host.exit(); break;
      default: break;
    }
  }

  // ------------------------------------------------------------------ visuals and text

  private buildReticle(): void {
    const geo = new SphereGeometry(0.012, 12, 8);
    const ring = new Mesh(geo, new MeshBasicMaterial({ color: 0xffd24a, depthTest: false, transparent: true }));
    ring.name = 'xray-xr-field-ring';
    ring.renderOrder = 27;
    ring.frustumCulled = false;
    ring.visible = false;
    this.reticle = ring;
    this.host.rigObject().add(ring);
  }

  private updateReticle(): void {
    const r = this.reticle;
    if (!r) return;
    const h = this.lastHit;
    r.visible = !!h;
    if (h) r.position.set(h.point[0], h.point[1], h.point[2]);
  }

  private updateMarkers(): void {
    const key = JSON.stringify(this.pairs) + this.step;
    if (key === this.markerKey) return;
    this.markerKey = key;
    for (const g of [this.modelMarkers, this.realMarkers]) for (const c of [...g.children]) disposeTree(c);
    const nextIdx = this.pairs.findIndex((p) => p.model && !p.real);
    this.pairs.forEach((p, i) => {
      if (p.model) {
        const m = marker(i === nextIdx && this.step === 'real' ? 0xff4fd8 : 0xd04fff, String(i + 1), 0.04);
        m.position.set(...p.model);
        this.modelMarkers.add(m);
      }
      if (p.real) {
        const m = marker(0x3fd0ff, String(i + 1), 0.03);
        m.position.set(...p.real);
        this.realMarkers.add(m);
      }
    });
    this.modelMarkers.visible = this.step !== 'done';
    this.realMarkers.visible = this.step !== 'done';
  }

  instruction(): string {
    const n = this.modelPoints();
    if (this.step === 'model') {
      if (this.addingOne) return 'Aim at the model feature for the new pair and tap.';
      return n < FIELD_MIN_PAIRS
        ? `Step 1: aim at a model corner, a column or a floor mark and tap (${n} of at least ${FIELD_MIN_PAIRS}).`
        : `Step 1: ${n} model points. Tap more, or tap Done picking.`;
    }
    if (this.step === 'real') {
      const i = this.pairs.findIndex((p) => p.model && !p.real);
      return `Step 2: aim the ring at real point ${i + 1} (the pink marker) and tap.`;
    }
    return 'Registered. Tap an element for its details. Nudge if the model is off.';
  }

  private anchorText(): string {
    switch (this.anchorState) {
      case 'tracked': return this.anchorHandle ? 'anchor held (persistent)' : 'anchor held';
      case 'pending': return 'anchor pending';
      case 'lost': return 'anchor lost: hold still or register again';
      case 'unsupported': return 'no anchors: may drift while you walk';
      default: return this.registered ? 'no anchor' : '';
    }
  }

  statusText(): string {
    const parts: string[] = [];
    if (this.registered) parts.push(this.restoredFrom && !this.solution ? `Field AR: restored "${this.restoredFrom}"` : `Field AR: registered${this.solution ? `, rms ${cm(this.solution.rms)}` : ''}`);
    else parts.push(`Field AR: ${this.step === 'model' ? 'pick model points' : 'tap room points'}`);
    const a = this.anchorText();
    if (a) parts.push(a);
    if (!this.viewerSource && !this.pointerSources.size) parts.push('no surface detection');
    return parts.join(', ');
  }

  private elevationText(): string {
    const level = this.levels[this.storeyIdx];
    if (!level || this.feetY === null) return this.registered ? 'No storeys in the model.' : '';
    const eyes = this.headWorld()[1] - level.floorY;
    const parts = [`${level.name}`, `eyes ${signedM(eyes)}`];
    if (this.ceilingY !== null) parts.push(`ceiling ${signedM(this.ceilingY - level.floorY)}`);
    if (this.lastHit) parts.push(`ring ${signedM(rigPoint(this.host.getRig(), this.lastHit.point)[1] - level.floorY)}`);
    return `${parts.join(' · ')} (above the storey floor${this.floorLocalY === null ? ', eye height assumed 1.5 m' : ''})`;
  }

  private card(): OverlayModel['card'] {
    const id = this.selected;
    const m = this.app.loaded?.model;
    const e = id !== null ? m?.elements[id] : undefined;
    if (!e || !m) return null;
    const storey = e.storey === null ? undefined : m.storeys.find((s) => s.id === e.storey)?.name;
    const rows = cardRows(e.props, parsePatterns(hoverInfoSettings.propertyFilter), Math.min(4, Math.max(0, hoverInfoSettings.maxRows))).map(([k, v]) => [propLabel(k), formatValue(v)] as [string, string]);
    const extra: string[] = [];
    const level = this.levels[this.storeyIdx];
    if (level) extra.push(`bottom ${signedM(e.bounds[1] - level.floorY)}, top ${signedM(e.bounds[4] - level.floorY)} above the storey floor`);
    if (this.clearance) {
      if (this.clearance.device !== null) extra.push(`clearance from the device ${cm(this.clearance.device)}`);
      if (this.clearance.point !== null) extra.push(`from the ring ${cm(this.clearance.point)}`);
    }
    return { title: e.name && e.name.trim() ? e.name : e.ifcClass, subtitle: subtitleOf(e.ifcClass, storey, e.material), rows, extra };
  }

  private renderUi(): void {
    const s = this.solution;
    const res = s && s.ok ? `residuals ${s.residuals.map(cm).join(', ')} (rms ${cm(s.rms)}; plan ${cm(Math.max(...s.horizontal))} max, height ${cm(Math.max(...s.vertical))} max)` : '';
    const model: OverlayModel = {
      status: this.statusText(),
      step: this.step,
      instruction: this.message ? `${this.instruction()} ${this.message}` : this.instruction(),
      pairs: this.pairs.map((p, i) => `${i + 1}: model ${p.model ? 'set' : '-'}, room ${p.real ? 'set' : '-'}${s?.ok && p.real && p.model ? ` ${cm(s.residuals[this.pairs.filter((q, j) => j < i && q.model && q.real).length] ?? NaN)}` : ''}`),
      residuals: res,
      elevation: this.elevationText(),
      view: this.config.view,
      cutOn: this.config.cut,
      cutText: this.cutBox ? `${this.config.cutRadius > 0 ? `${this.config.cutRadius} m around you` : 'no radius'}${this.config.storeyCut ? ', storey' : ''}` : 'cut off',
      nudgeStep: NUDGE_STEPS[this.nudgeIndex] === 0.01 ? '1 cm' : '10 cm',
      card: this.card(),
      notes: this.notes.length,
      canSave: this.registered,
      registered: this.registered,
    };
    this.overlay?.update(model);
    if (this.hud && this.domOverlay === null) {
      const lines = [model.status, this.instruction()];
      if (this.message) lines.push(this.message);
      if (res) lines.push(res);
      if (model.elevation) lines.push(model.elevation);
      if (model.card) lines.push(`${model.card.title}: ${model.card.subtitle}`, ...model.card.extra);
      lines.push(`look ${this.config.view} (squeeze), A snapshot, B register again, X cut, Y floor here`);
      this.hud.set(lines);
    }
  }

  private changed(): void {
    this.renderUi();
    this.host.changed();
  }

  state(): FieldStateView {
    return {
      step: this.step,
      registered: this.registered,
      pairs: this.pairs.map((p) => ({ model: p.model ? [...p.model] : null, real: p.real ? [...p.real] : null })),
      residuals: this.solution?.residuals ?? [],
      rms: this.solution && Number.isFinite(this.solution.rms) ? this.solution.rms : null,
      warnings: this.solution?.warnings ?? [],
      anchor: this.anchorState,
      anchorHandle: this.anchorHandle,
      restoredFrom: this.restoredFrom,
      view: this.config.view,
      appliedView: this.appliedView ?? 'full',
      cut: this.cutBox ? { min: [...this.cutBox.min], max: [...this.cutBox.max] } : null,
      storey: this.levels[this.storeyIdx]?.name ?? null,
      feetY: this.feetY,
      eyeHeight: this.eyeHeight(),
      floorFromHit: this.floorLocalY !== null,
      selected: this.selected !== null ? { id: this.selected, name: this.app.loaded?.model.elements[this.selected]?.name ?? '', globalId: this.app.loaded?.model.elements[this.selected]?.globalId ?? '' } : null,
      clearance: this.clearance ? { ...this.clearance } : null,
      notes: this.notes.length,
      domOverlay: this.domOverlay,
      hitTest: { centre: !!this.viewerSource, pointers: [...this.pointerSources.values()].filter((v) => typeof v === 'object').length },
      lastHit: this.lastHit ? [...this.lastHit.point] : null,
      nudgeStep: NUDGE_STEPS[this.nudgeIndex]!,
      instruction: this.instruction(),
      message: this.message,
    };
  }
}

function storage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

