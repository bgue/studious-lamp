// Point cloud controller: owns the THREE.Points in the main scene, the display and alignment settings, the loader
// and the deviation check. UI (drawer, lil-gui) and the window API only talk to this class.

import { BufferAttribute, BufferGeometry, Matrix4, Plane, Points, PointsMaterial, Vector3 } from 'three';
import { CLEARANCE_LEGEND_H, CLEARANCE_LEGEND_W } from '../measure/clearanceTool';
import { cameraRay, firstSurfaceHit } from '../measure/geometry';
import { snapToVertex } from '../measure/maths';
import type { MeshBVH } from 'three-mesh-bvh';
import type { ViewerApp } from '../app';
import { applyFrame, autoAlign, cloudFrame, decomposeTotal, mapPositions, projectToViewer } from './align';
import type { AutoAlignResult, CloudFrame, CoordMode } from './align';
import { icp, voxelSample } from './icp';
import type { ClosestFn, IcpResult, RegionResidual } from './icp';
import { estimateNormalsAsync } from './normals';
import type { CloudNormals } from './normals';
import { bvhClosestFn } from './surface';
import { buildScreenIndex, pickNearest } from './pick';
import type { ScreenIndex } from './pick';
import { apply as applyMat, formatDistance, identity, scaleOf, solvePairs, transformError, yawDeg } from './register';
import type { Mat4, PairSolution } from './register';
import { PointCloudLoader } from './client';
import { BAND_COLORS, BAND_LABELS, bandOf, buildColours } from './colour';
import type { ColourMode } from './colour';
import { DEFAULT_SAMPLE_CAP, MAX_FACTOR, computeDeviation, sampleStride, summarise } from './deviation';
import type { DeviationStats, DistanceFn } from './deviation';
import { PointCloudError } from './types';
import type { LoadInfo, Shown, Vec3 } from './types';
import { getOverlay, svgEl } from '../ui/overlay';

export type DeviationScope = 'all elements' | 'focus only';
export const DEFAULT_BUDGET = 3_000_000;
/**
 * Where 3-point alignment and ICP look: the whole cloud, the active section box, or the bounds of the selected
 * elements plus REGION_MARGIN. A part of a long scan aligned on its own (room by room) does not suffer from the drift
 * of the rest.
 */
export type AlignRegion = 'whole cloud' | 'section box' | 'selection';
export const ALIGN_REGIONS: AlignRegion[] = ['whole cloud', 'section box', 'selection'];
export const REGION_MARGIN = 0.5;
/** Ghosted elements below this alpha do not hide cloud points from picking (the measure tool's rule for ghosts). */
export const OCCLUDE_ALPHA = 0.5;

/** An axis aligned box in the viewer frame. */
export interface RegionBox {
  min: Vec3;
  max: Vec3;
  /** What it is, for the status line: 'section box' or 'selection (+0.5 m)'. */
  label: string;
}

export interface PointCloudSettings {
  visible: boolean;
  /** Pixels (CSS). */
  pointSize: number;
  /** Shrink points with distance (pointSize is then the size at the orbit target). */
  sizeAttenuation: boolean;
  colourBy: ColourMode;
  budget: number;
  coordinates: CoordMode;
  offsetX: number;
  offsetY: number;
  offsetZ: number;
  rotationDeg: number;
  /** Registration (column-major 4x4, cloud frame -> viewer) under the offset / rotation nudge. Identity by default. */
  matrix: number[];
  /** 3-point alignment and ICP keep the cloud upright: yaw and translation only. */
  keepVertical: boolean;
  /** 3-point alignment may also scale the cloud (uniform). */
  allowScale: boolean;
  tolerance: number;
  scope: DeviationScope;
  /** Where 3-point alignment and ICP look (not part of the params document: a step of the workflow). */
  alignRegion: AlignRegion;
}

/** Default number of cloud points that ICP matches against the model. */
export const ICP_SAMPLES = 20_000;

export interface PointPair {
  /** Cloud frame (before any alignment), so the pair survives alignment changes. */
  cloud: Vec3 | null;
  /** Viewer frame, on the model surface. */
  model: Vec3 | null;
}

interface AlignSnapshot {
  offset: Vec3;
  rotationDeg: number;
  matrix: number[];
  alignment: string;
}

export function defaultPointCloudSettings(): PointCloudSettings {
  return {
    visible: true, pointSize: 2, sizeAttenuation: false, colourBy: 'rgb', budget: DEFAULT_BUDGET, coordinates: 'project',
    offsetX: 0, offsetY: 0, offsetZ: 0, rotationDeg: 0, matrix: identity(), keepVertical: true, allowScale: false, tolerance: 0.02, scope: 'all elements',
    alignRegion: 'whole cloud',
  };
}

export interface PointCloudStats {
  loaded: boolean;
  name: string;
  format: string;
  originalCount: number;
  shownCount: number;
  parseMs: number;
  decimateMs: number;
  /** 'worker' or 'inline'. */
  mode: string;
  warnings: string[];
  deviation: DeviationStats | null;
  deviationMs: number;
  deviationScope: DeviationScope | null;
  alignment: string;
  /** Last ICP run (null until one ran on this cloud). */
  icp: {
    iterations: number; converged: boolean; reverted: boolean; rmsBefore: number; rmsAfter: number; inlierFraction: number; samples: number; ms: number; reason: string;
    /** How normals took part ('none', 'axis', 'oriented'; see icp.ts) and how many sample points had one / an orientation. */
    normalMode: string; withNormal: number; oriented: number;
    /** The region the run was limited to (null: the whole cloud). */
    region: RegionBox | null;
    /** Residual per cell of a 3 x 3 plan grid at the end (drift diagnostic). */
    regions: RegionResidual[];
    /** One line on where the fit degrades, or '' when it is even. */
    drift: string;
  } | null;
}

interface DeviationState {
  indices: Uint32Array;
  dist: Float32Array;
  stats: DeviationStats;
  /** Per shown point: 1 when measured. */
  measured: Uint8Array;
  full: Float32Array;
}

type Plane6 = { normal: Vec3 | { x: number; y: number; z: number }; point: Vec3 | { x: number; y: number; z: number } };
const v3 = (v: Vec3 | { x: number; y: number; z: number }): Vec3 => (Array.isArray(v) ? [v[0], v[1], v[2]] : [(v as { x: number }).x, (v as { y: number }).y, (v as { z: number }).z]);

export class PointCloudController {
  readonly settings: PointCloudSettings = defaultPointCloudSettings();
  status = 'No point cloud loaded. Open a .las, .e57, .ply, .pcd, .xyz, .pts or .txt file.';
  busy = false;
  info: LoadInfo | null = null;
  readonly stats: PointCloudStats = emptyStats();

  private readonly loader = new PointCloudLoader();
  private shown: Shown | null = null;
  private mapped: Float32Array | null = null;
  private frame: CloudFrame | null = null;
  private points: Points | null = null;
  private geom: BufferGeometry | null = null;
  private readonly material: PointsMaterial;
  /** Deviation findings (amber and red points) drawn through the model: see updateOverlay(). */
  private readonly overlayMaterial: PointsMaterial;
  private overlay: Points | null = null;
  private dev: DeviationState | null = null;
  private token = 0;
  private cancel = false;
  private listeners = new Set<() => void>();
  private clipSig = '';
  private legendOff: (() => void) | null = null;
  private legendLayer: SVGGElement | null = null;
  private legendShown = false;
  private heights: Float32Array | null = null;
  private undoStack: AlignSnapshot[] = [];
  /** Bumped whenever the drawn positions, the transform or the drawn subset change (screen index cache key). */
  private version = 0;
  private screen: { sig: string; idx: ScreenIndex } | null = null;
  /** 3-point alignment: picked pairs, or null when the mode is off. */
  pairs: PointPair[] | null = null;
  pairSolution: PairSolution | null = null;
  private icpToken = -1;

  constructor(private readonly app: ViewerApp) {
    // Opaque queue: drawn before the ghost pass, so the ghost (which writes depth) blends over the points instead of
    // hiding them; the focus pass (drawn last, in front) still covers points inside the focus silhouette.
    this.material = new PointsMaterial({ size: this.settings.pointSize, sizeAttenuation: false, vertexColors: true, depthTest: true, depthWrite: true });
    this.material.toneMapped = false;
    this.overlayMaterial = new PointsMaterial({ size: this.settings.pointSize, sizeAttenuation: false, vertexColors: true, depthTest: false, depthWrite: false, transparent: true });
    this.overlayMaterial.toneMapped = false;
    app.renderer.renderer.localClippingEnabled = true;
  }

  onChange(cb: () => void): () => void {
    this.listeners.add(cb);
    return () => this.listeners.delete(cb);
  }
  private emit(): void {
    for (const l of this.listeners) l();
  }
  private setStatus(s: string): void {
    this.status = s;
    this.emit();
  }

  get loaded(): boolean {
    return !!this.shown;
  }
  get hasDeviation(): boolean {
    return !!this.dev;
  }
  get hasClassification(): boolean {
    return !!this.shown?.classification;
  }
  get hasIntensity(): boolean {
    return !!this.shown?.intensity;
  }
  get hasColor(): boolean {
    return !!this.shown?.colors;
  }

  // ---------------------------------------------------------------- load / remove

  async load(src: File | Blob | ArrayBuffer | Uint8Array, name?: string): Promise<PointCloudStats> {
    const fname = name ?? (src instanceof File ? src.name : 'pointcloud');
    const token = ++this.token;
    this.busy = true;
    this.setStatus(`Reading ${fname}...`);
    try {
      let buf: ArrayBuffer;
      if (src instanceof ArrayBuffer) buf = src;
      else if (src instanceof Uint8Array) buf = src.byteOffset === 0 && src.byteLength === src.buffer.byteLength ? (src.buffer as ArrayBuffer) : (src.slice().buffer as ArrayBuffer);
      else buf = await src.arrayBuffer();
      const res = await this.loader.load(buf, fname, {
        budget: this.settings.budget,
        onProgress: (f, stage) => {
          if (token === this.token) this.setStatus(`${stage === 'decimate' ? 'Decimating' : 'Parsing'} ${fname}: ${Math.round(f * 100)}%`);
        },
      });
      if (token !== this.token) return this.stats;
      this.removeObjects();
      this.info = res.info;
      this.shown = res.shown;
      this.stats.name = fname;
      this.stats.format = res.info.format;
      this.stats.originalCount = res.info.originalCount;
      this.stats.parseMs = res.info.parseMs;
      this.stats.decimateMs = res.decimateMs;
      this.stats.mode = res.mode;
      this.stats.warnings = res.info.warnings;
      this.stats.loaded = true;
      this.dev = null;
      this.stats.deviation = null;
      this.stats.deviationScope = null;
      this.stats.alignment = '';
      this.stats.icp = null;
      this.undoStack = [];
      this.pairs = null;
      this.pairSolution = null;
      if (this.settings.colourBy === 'deviation') this.settings.colourBy = 'rgb';
      this.buildObjects();
      this.syncStats();
      this.setStatus(this.summaryLine());
      this.app.renderer.markDirty();
      return this.stats;
    } catch (e) {
      if (token === this.token) this.setStatus(`Could not open ${fname}: ${e instanceof Error ? e.message : String(e)}`);
      throw e;
    } finally {
      if (token === this.token) this.busy = false;
      this.emit();
    }
  }

  remove(): void {
    this.token++;
    this.cancel = true;
    this.loader.dispose();
    this.removeObjects();
    this.shown = null;
    this.info = null;
    this.dev = null;
    this.undoStack = [];
    this.pairs = null;
    this.pairSolution = null;
    this.screen = null;
    Object.assign(this.stats, emptyStats());
    this.busy = false;
    this.hideLegend();
    this.setStatus('No point cloud loaded. Open a .las, .e57, .ply, .pcd, .xyz, .pts or .txt file.');
    this.app.renderer.markDirty();
  }

  private removeObjects(): void {
    this.updateOverlay(null);
    if (this.points) this.app.renderer.scene.remove(this.points);
    this.geom?.dispose();
    this.points = null;
    this.geom = null;
    this.mapped = null;
    this.frame = null;
    this.heights = null;
    this.screen = null;
    this.version++;
  }

  // ---------------------------------------------------------------- build / update

  private shift(): Vec3 {
    const s = this.app.controller?.model?.originShift as Vec3 | undefined;
    return s ? [s[0], s[1], s[2]] : [0, 0, 0];
  }

  private buildObjects(): void {
    const sh = this.shown!;
    this.mapped = mapPositions(sh.positions, this.settings.coordinates);
    const g = new BufferGeometry();
    g.setAttribute('position', new BufferAttribute(this.mapped, 3));
    g.setAttribute('color', new BufferAttribute(new Uint8Array(sh.count * 3), 3, true));
    g.computeBoundingSphere();
    this.geom = g;
    const pts = new Points(g, this.material);
    pts.name = 'pointcloud';
    pts.frustumCulled = true;
    pts.matrixAutoUpdate = false;
    pts.renderOrder = 4; // after the ghost (1 to 2), context edges (2) and focus (3) passes, so the points are never hidden by them; depth tested
    pts.raycast = () => {}; // picking uses the model's BVH, never the cloud
    this.points = pts;
    this.app.renderer.scene.add(pts);
    this.computeHeights();
    this.updateFrame();
    this.recolour();
    this.applyDisplay();
  }

  private computeHeights(): void {
    const m = this.mapped;
    if (!m) return;
    const n = m.length / 3;
    const h = new Float32Array(n);
    for (let i = 0; i < n; i++) h[i] = m[i * 3 + 1]!;
    this.heights = h;
  }

  /** Recompute the transform from the settings. Invalidates a deviation result. */
  private updateFrame(): void {
    if (!this.info || !this.points) return;
    const s = this.settings;
    this.frame = cloudFrame(this.info, { mode: s.coordinates, shift: this.shift(), offset: [s.offsetX, s.offsetY, s.offsetZ], rotationDeg: s.rotationDeg, registration: s.matrix });
    this.version++;
    this.points.matrix.copy(this.frame.matrix);
    this.points.matrixWorldNeedsUpdate = true;
    this.points.updateMatrixWorld(true);
    if (this.overlay) {
      this.overlay.matrix.copy(this.frame.matrix);
      this.overlay.matrixWorldNeedsUpdate = true;
    }
    this.app.renderer.markDirty();
  }

  private invalidateDeviation(): void {
    if (!this.dev) return;
    this.cancel = true;
    this.dev = null;
    this.stats.deviation = null;
    this.stats.deviationScope = null;
    this.hideLegend();
    this.recolour();
  }

  /** Display settings changed (point size, visibility, colour mode, attenuation). */
  applyDisplay(): void {
    const s = this.settings;
    if (this.points) this.points.visible = s.visible;
    for (const m of [this.material, this.overlayMaterial]) {
      m.sizeAttenuation = s.sizeAttenuation;
      m.size = s.pointSize;
      m.needsUpdate = true;
    }
    if (this.overlay) this.overlay.visible = s.visible;
    this.updateLegend();
    this.app.renderer.markDirty();
    this.emit();
  }

  recolour(): void {
    const g = this.geom;
    const sh = this.shown;
    if (!g || !sh) return;
    const s = this.settings;
    const dev = s.colourBy === 'deviation' ? this.dev : null;
    const cols = buildColours(s.colourBy, {
      count: sh.count, colors: sh.colors, intensity: sh.intensity, intensityRange: this.info?.intensityRange, classification: sh.classification,
      heights: this.heights ?? undefined, deviation: dev?.full ?? null, measured: dev?.measured ?? null, tolerance: s.tolerance,
    });
    const attr = g.getAttribute('color') as BufferAttribute;
    (attr.array as Uint8Array).set(cols);
    attr.needsUpdate = true;
    // a sampled deviation draws only the measured points (the rest has no value to show)
    if (dev && dev.indices.length < sh.count) g.setIndex(new BufferAttribute(dev.indices, 1));
    else if (g.getIndex()) g.setIndex(null);
    this.version++;
    this.updateOverlay(dev);
    this.updateLegend();
    this.app.renderer.markDirty();
  }

  /**
   * With the deviation colouring, the amber and red points (the findings) are drawn a second time without depth test,
   * after every other pass: a displaced duct inside a ghosted host, or behind the focus element, stays visible.
   * Healthy (green) and unrelated (grey) points keep the normal depth behaviour. Shares the attribute buffers.
   */
  private updateOverlay(dev: DeviationState | null): void {
    if (this.overlay) {
      this.app.renderer.scene.remove(this.overlay);
      this.overlay.geometry.dispose();
      this.overlay = null;
    }
    if (!dev || !this.geom) return;
    const tol = this.settings.tolerance;
    const keep: number[] = [];
    for (let k = 0; k < dev.indices.length; k++) {
      const b = bandOf(dev.dist[k]!, tol);
      if (b === 1 || b === 2) keep.push(dev.indices[k]!);
    }
    if (!keep.length) return;
    const g = new BufferGeometry();
    g.setAttribute('position', this.geom.getAttribute('position'));
    g.setAttribute('color', this.geom.getAttribute('color'));
    g.setIndex(new BufferAttribute(Uint32Array.from(keep), 1));
    g.boundingSphere = this.geom.boundingSphere;
    const o = new Points(g, this.overlayMaterial);
    o.name = 'pointcloud-findings';
    o.matrixAutoUpdate = false;
    o.matrix.copy(this.points!.matrix);
    o.matrixWorldNeedsUpdate = true;
    o.renderOrder = 6; // after the focus edges (4) and glow (5)
    o.raycast = () => {};
    o.visible = this.settings.visible;
    this.overlay = o;
    this.app.renderer.scene.add(o);
  }

  setColourBy(m: ColourMode): void {
    this.settings.colourBy = m;
    this.recolour();
    this.emit();
  }

  /** Alignment settings changed: refresh the transform. */
  setAlignment(): void {
    this.updateFrame();
    this.invalidateDeviation();
    this.stats.alignment = '';
    this.emit();
  }

  /** `coordinates` changed: remap axes. */
  setCoordinates(mode: CoordMode): void {
    const changed = mode !== this.settings.coordinates;
    this.settings.coordinates = mode;
    if (!this.shown || !this.info) return;
    if (changed && this.pairs) this.cancelPairs(); // picked cloud points are in the old axis mapping
    this.mapped = mapPositions(this.shown.positions, mode);
    const g = this.geom!;
    g.setAttribute('position', new BufferAttribute(this.mapped, 3));
    g.computeBoundingSphere();
    this.computeHeights();
    this.updateFrame();
    this.invalidateDeviation();
    this.recolour();
    this.emit();
  }

  /** Budget changed: decimate the loaded cloud again. */
  async setBudget(budget: number): Promise<void> {
    this.settings.budget = budget;
    if (!this.shown) return;
    const token = ++this.token;
    this.busy = true;
    try {
      const r = await this.loader.decimate(budget);
      if (token !== this.token) return;
      this.shown = r.shown;
      this.stats.decimateMs = r.decimateMs;
      this.dev = null;
      this.stats.deviation = null;
      this.geom?.dispose();
      if (this.points) this.app.renderer.scene.remove(this.points);
      this.buildObjects();
      this.syncStats();
      this.setStatus(this.summaryLine());
    } finally {
      if (token === this.token) this.busy = false;
      this.emit();
    }
  }

  /** Append a one-line note to the status (after an action finished). */
  noteExtra(text: string): void {
    this.setStatus(`${this.status} ${text}`);
  }

  setTolerance(t: number): void {
    this.settings.tolerance = t;
    if (this.dev) {
      this.invalidateDeviation();
      this.setStatus('Tolerance changed: compute the deviation again.');
    }
    this.emit();
  }

  setModelChanged(): void {
    if (!this.shown) return;
    this.updateFrame();
    this.invalidateDeviation();
    this.emit();
  }

  private syncStats(): void {
    this.stats.shownCount = this.shown?.count ?? 0;
  }

  private summaryLine(): string {
    const i = this.info;
    if (!i) return this.status;
    const f = (n: number): string => n.toLocaleString('en-US');
    const extras = [i.hasColor ? 'colour' : null, i.hasIntensity ? 'intensity' : null, i.hasClassification ? 'classes' : null].filter(Boolean).join(', ');
    return `${i.name}: ${f(i.originalCount)} points, ${f(this.shown!.count)} shown (${i.format.toUpperCase()}${extras ? `, ${extras}` : ''}). ${this.stats.mode === 'worker' ? 'Parsed in a worker' : 'Parsed inline'} in ${i.parseMs.toFixed(0)} ms.` + (i.warnings.length ? ` Warning: ${i.warnings.join('; ')}.` : '');
  }

  // ---------------------------------------------------------------- per frame

  onFrame(): void {
    if (!this.points) return;
    // section planes: renderer.getClipPlanes() when it exists; normals point to the kept side, like three's clipping planes
    const api = this.app.renderer as unknown as { getClipPlanes?: () => Plane6[] | null | undefined };
    const planes = api.getClipPlanes?.() ?? null;
    const sig = planes && planes.length ? JSON.stringify(planes.map((p) => [v3(p.normal), v3(p.point)])) : '';
    if (sig !== this.clipSig) {
      this.clipSig = sig;
      const cp = planes && planes.length
        ? planes.map((p) => new Plane().setFromNormalAndCoplanarPoint(new Vector3(...v3(p.normal)).normalize(), new Vector3(...v3(p.point))))
        : null;
      for (const m of [this.material, this.overlayMaterial]) {
        m.clippingPlanes = cp;
        m.needsUpdate = true;
      }
      this.app.renderer.markDirty();
    }
    if (this.settings.sizeAttenuation) {
      // pointSize pixels at the orbit target: three scales size by (drawing height / 2) / distance
      const r = this.app.renderer;
      const dist = r.camera.position.distanceTo(r.controls.target);
      const hh = r.renderer.domElement.clientHeight || 900;
      const size = (this.settings.pointSize * dist) / (hh / 2);
      if (Math.abs(size - this.material.size) > 1e-4 * size) {
        this.material.size = size;
        this.overlayMaterial.size = size;
        this.app.renderer.markDirty();
      }
    }
  }

  // ---------------------------------------------------------------- auto align

  /** Move (and optionally rotate in 90 degree steps) the cloud onto the model. Returns the description. */
  autoAlign(rotate = true): AutoAlignResult | null {
    if (!this.info || !this.mapped || !this.shown) return null;
    const geo = this.app.loaded?.geometry;
    if (!geo) {
      this.setStatus('Auto-align needs a model.');
      return null;
    }
    const b = geo.totalBounds();
    // sample relative to the pivot, with the current base and no offset / rotation
    const s = this.settings;
    const f0 = cloudFrame(this.info, { mode: s.coordinates, shift: this.shift(), offset: [0, 0, 0], rotationDeg: 0 });
    const n = this.shown.count;
    const k = Math.min(n, 2000);
    const sample = new Float32Array(k * 3);
    for (let i = 0; i < k; i++) {
      const j = Math.floor((i * n) / k) * 3;
      sample[i * 3] = this.mapped[j]! + f0.base[0] - f0.pivot[0];
      sample[i * 3 + 1] = this.mapped[j + 1]! + f0.base[1] - f0.pivot[1];
      sample[i * 3 + 2] = this.mapped[j + 2]! + f0.base[2] - f0.pivot[2];
    }
    const dist = this.distanceFn('all elements');
    const r = autoAlign({
      pivot: f0.pivot, samplesRelPivot: sample, modelMin: [b.min.x, b.min.y, b.min.z], modelMax: [b.max.x, b.max.y, b.max.z],
      distance: dist ? (x, y, z) => dist(x, y, z, 1e9) : undefined, rotate,
    });
    this.pushUndo();
    s.offsetX = r.offset[0];
    s.offsetY = r.offset[1];
    s.offsetZ = r.offset[2];
    s.rotationDeg = r.rotationDeg;
    s.matrix = identity();
    this.setAlignment();
    this.stats.alignment = r.description;
    this.setStatus(`Auto-align: ${r.description}`);
    return r;
  }

  // ---------------------------------------------------------------- deviation

  /** Distance function for the scope, or null when there is nothing to measure against. */
  distanceFn(scope: DeviationScope): DistanceFn | null {
    const geo = this.app.loaded?.geometry;
    if (!geo) return null;
    const p = new Vector3();
    const tgt = { point: new Vector3(), distance: 0, faceIndex: 0 };
    if (scope === 'all elements') {
      const bvh = geo.bvh;
      return (x, y, z, max) => {
        p.set(x, y, z);
        const r = bvh.closestPointToPoint(p, tgt, 0, max);
        return r ? r.distance : Infinity;
      };
    }
    const focus = this.app.controller.classification.focus;
    const trees = [...focus].map((id) => geo.subGeometry(id)?.boundsTree as MeshBVH | undefined).filter((t): t is MeshBVH => !!t);
    if (!trees.length) return null;
    return (x, y, z, max) => {
      p.set(x, y, z);
      let best = Infinity;
      let lim = max;
      for (const t of trees) {
        const r = t.closestPointToPoint(p, tgt, 0, lim);
        if (r && r.distance < best) {
          best = r.distance;
          lim = Math.min(lim, best);
        }
      }
      return best;
    };
  }

  /** Measure the distance of (a sample of) the shown points to the model and colour them by band. */
  async computeDeviation(): Promise<DeviationStats | null> {
    if (!this.shown || !this.mapped || !this.frame) {
      this.setStatus('Deviation needs a point cloud. Open one first.');
      return null;
    }
    if (!this.app.loaded) {
      this.setStatus('Deviation needs a model.');
      return null;
    }
    const scope = this.settings.scope;
    const dist = this.distanceFn(scope);
    if (!dist) {
      this.setStatus(scope === 'focus only' ? 'Deviation scope "focus only" needs a selection: select the elements to check against.' : 'Deviation needs a model with geometry.');
      return null;
    }
    this.cancel = false;
    const token = ++this.token;
    const sh = this.shown;
    const tol = this.settings.tolerance;
    const indices = sampleStride(sh.count, DEFAULT_SAMPLE_CAP);
    this.busy = true;
    const t0 = performance.now();
    this.setStatus('Computing deviation: 0%');
    try {
      const d = await computeDeviation({
        positions: this.mapped, frame: this.frame, indices, distance: dist, tolerance: tol,
        onProgress: (f) => this.setStatus(`Computing deviation: ${Math.round(f * 100)}%`),
        isCancelled: () => this.cancel || token !== this.token,
      });
      if (!d) return null;
      const cls = sh.classification ? Uint8Array.from(indices, (i) => sh.classification![i]!) : null;
      const stats = summarise(d, tol, cls);
      const full = new Float32Array(sh.count);
      const measured = new Uint8Array(sh.count);
      for (let k = 0; k < indices.length; k++) {
        full[indices[k]!] = d[k]!;
        measured[indices[k]!] = 1;
      }
      this.dev = { indices, dist: d, stats, measured, full };
      this.stats.deviation = stats;
      this.stats.deviationMs = performance.now() - t0;
      this.stats.deviationScope = scope;
      this.settings.colourBy = 'deviation';
      this.recolour();
      const cm = (v: number): string => (isFinite(v) ? `${(v * 100).toFixed(1)} cm` : '-');
      this.setStatus(
        `Deviation (${scope}, tolerance ${(tol * 100).toFixed(1)} cm, ${stats.sampled.toLocaleString('en-US')} points): ${(stats.shareWithin * 100).toFixed(1)}% of related points within tolerance, mean ${cm(stats.mean)}, 95th percentile ${cm(stats.p95)}; ${(stats.unrelatedShare * 100).toFixed(1)}% unrelated (> ${cm(stats.maxDistance)}).`,
      );
      return stats;
    } finally {
      if (token === this.token) this.busy = false;
      this.emit();
    }
  }

  // ---------------------------------------------------------------- legend (shared SVG overlay)

  private updateLegend(): void {
    const show = !!this.dev && this.settings.colourBy === 'deviation' && this.settings.visible && !!this.points;
    if (!show) {
      this.hideLegend();
      return;
    }
    const ov = getOverlay(this.app);
    if (!this.legendLayer) this.legendLayer = ov.layer('pointcloud-legend');
    const g = this.legendLayer;
    g.replaceChildren();
    const tol = this.settings.tolerance;
    const cm = (v: number): string => `${+(v * 100).toFixed(1)} cm`;
    const labels = [`within ${cm(tol)}`, `up to ${cm(2 * tol)}`, `up to ${cm(MAX_FACTOR * tol)}`, `beyond ${cm(MAX_FACTOR * tol)} (unrelated)`];
    const w = 190;
    const h = 22 + labels.length * 18;
    g.appendChild(svgEl('rect', { x: 0, y: 0, width: w, height: h, rx: 4, fill: 'rgba(20,24,30,0.82)' }));
    const title = svgEl('text', { x: 8, y: 15, fill: '#dfe6ee', 'font-size': 11, 'font-family': 'system-ui,sans-serif', 'font-weight': 600 });
    title.textContent = 'Deviation from model';
    g.appendChild(title);
    labels.forEach((l, i) => {
      const c = BAND_COLORS[i]!;
      g.appendChild(svgEl('rect', { x: 8, y: 24 + i * 18, width: 12, height: 12, fill: `rgb(${c[0]},${c[1]},${c[2]})` }));
      const t = svgEl('text', { x: 26, y: 34 + i * 18, fill: '#dfe6ee', 'font-size': 11, 'font-family': 'system-ui,sans-serif' });
      t.textContent = l;
      g.appendChild(t);
    });
    void BAND_LABELS;
    if (!this.legendOff) {
      this.legendOff = ov.onUpdate((o) => {
        // Bottom right of the stage, above the status bar and beside (or above) the gizmo; above the clearance legend
        // when that one shows (src/measure/clearanceTool.ts).
        const clearance = (window as unknown as { __xrayClearance?: { enabled?: boolean } }).__xrayClearance?.enabled === true;
        const p = o.legendSpot(190, 22 + 4 * 18, clearance ? CLEARANCE_LEGEND_H + 8 : 0, clearance ? CLEARANCE_LEGEND_W : 190);
        this.legendLayer?.setAttribute('transform', `translate(${p.x},${p.y})`);
      });
    }
    this.legendLayer.style.display = '';
    this.legendShown = true;
    ov.invalidate();
  }

  private hideLegend(): void {
    if (this.legendLayer && this.legendShown) this.legendLayer.style.display = 'none';
    this.legendShown = false;
  }

  // ---------------------------------------------------------------- general transform, undo

  /** Total transform from the cloud frame (axis-mapped, before alignment) to the viewer, column-major. */
  get totalMatrix(): Mat4 {
    return this.frame ? this.frame.total.slice() : identity();
  }

  /** Cloud-frame position (axis-mapped, before alignment, double) of shown point i. */
  cloudPoint(i: number): Vec3 | null {
    if (!this.mapped || !this.frame) return null;
    const b = this.frame.base;
    return [this.mapped[i * 3]! + b[0], this.mapped[i * 3 + 1]! + b[1], this.mapped[i * 3 + 2]! + b[2]];
  }

  /** Viewer position of a cloud-frame point under the current alignment. */
  toViewer(c: Vec3): Vec3 {
    return applyMat(this.totalMatrix, c);
  }

  get canUndoAlignment(): boolean {
    return this.undoStack.length > 0;
  }

  private snapshot(): AlignSnapshot {
    const s = this.settings;
    return { offset: [s.offsetX, s.offsetY, s.offsetZ], rotationDeg: s.rotationDeg, matrix: s.matrix.slice(), alignment: this.stats.alignment };
  }

  private restore(a: AlignSnapshot): void {
    const s = this.settings;
    [s.offsetX, s.offsetY, s.offsetZ] = a.offset;
    s.rotationDeg = a.rotationDeg;
    s.matrix = a.matrix.slice();
    this.setAlignment();
    this.stats.alignment = a.alignment;
  }

  private pushUndo(): void {
    this.undoStack.push(this.snapshot());
    if (this.undoStack.length > 20) this.undoStack.shift();
  }

  /**
   * Set the total transform (cloud frame -> viewer). A yaw plus a translation is stored as offset + rotation; anything
   * else as the registration matrix with a zero nudge. Pushes the previous alignment on the undo stack.
   */
  applyTotal(total: Mat4, description: string): void {
    if (!this.frame) return;
    this.pushUndo();
    const parts = decomposeTotal(total, this.frame.pivot);
    const s = this.settings;
    [s.offsetX, s.offsetY, s.offsetZ] = parts.offset;
    s.rotationDeg = parts.rotationDeg;
    s.matrix = parts.registration;
    this.setAlignment();
    this.stats.alignment = description;
    this.emit();
  }

  /** Back to the alignment before the last Auto-align, 3-point alignment, ICP or reset. */
  undoAlignment(): boolean {
    const a = this.undoStack.pop();
    if (!a) {
      this.setStatus('Nothing to undo.');
      return false;
    }
    this.restore(a);
    this.setStatus('Alignment undone: back to the previous transform.');
    return true;
  }

  /** Offset, rotation and registration back to zero / identity. */
  resetAlignment(): void {
    this.pushUndo();
    const s = this.settings;
    s.offsetX = s.offsetY = s.offsetZ = 0;
    s.rotationDeg = 0;
    s.matrix = identity();
    this.setAlignment();
    this.setStatus('Alignment reset: no offset, no rotation, no registration.');
  }

  /** One line describing the current transform: heading, tilt, scale, translation of the bounds centre. */
  describeTransform(): string {
    const m = this.totalMatrix;
    const s = scaleOf(m);
    // tilt: angle between the transformed vertical and the vertical
    const tilt = (Math.acos(Math.min(1, Math.max(-1, m[5]! / s))) * 180) / Math.PI;
    return `heading ${yawDeg(m).toFixed(2)} deg${tilt > 0.005 ? `, tilt ${tilt.toFixed(2)} deg` : ''}${Math.abs(s - 1) > 1e-6 ? `, scale ${s.toFixed(4)}` : ''}`;
  }

  // ---------------------------------------------------------------- region

  /**
   * The box that `align within` names, in the viewer frame; null for the whole cloud; a string when the region is not
   * available (no active section box, nothing selected).
   */
  regionBox(region: AlignRegion = this.settings.alignRegion): RegionBox | null | string {
    if (region === 'whole cloud') return null;
    if (region === 'section box') {
      const sec = (window as unknown as { __xraySection?: { config?: { box?: { enabled?: boolean; min?: number[] | null; max?: number[] | null } } } }).__xraySection;
      const b = sec?.config?.box;
      if (!b?.enabled || !b.min || !b.max) return 'Align within section box needs an active section box (Section tool, box on).';
      return { min: [b.min[0]!, b.min[1]!, b.min[2]!], max: [b.max[0]!, b.max[1]!, b.max[2]!], label: 'section box' };
    }
    const els = this.app.loaded?.model.elements as Array<{ bounds?: number[] } | undefined> | undefined;
    const ids = this.app.controller?.selection ?? new Set<number>();
    const min: Vec3 = [Infinity, Infinity, Infinity], max: Vec3 = [-Infinity, -Infinity, -Infinity];
    for (const id of ids) {
      const b = els?.[id]?.bounds;
      if (!b || b.length < 6) continue;
      for (let k = 0; k < 3; k++) {
        min[k] = Math.min(min[k]!, b[k]!);
        max[k] = Math.max(max[k]!, b[k + 3]!);
      }
    }
    if (!Number.isFinite(min[0])) return 'Align within selection needs selected elements: select the room\'s walls and slab first.';
    const m = REGION_MARGIN;
    return { min: [min[0] - m, min[1] - m, min[2] - m], max: [max[0] + m, max[1] + m, max[2] + m], label: `selection (+${m} m)` };
  }

  /** Say in the status line what `align within` now covers. */
  noteRegion(): void {
    const b = this.regionBox();
    if (b === null) this.setStatus('Align within the whole cloud: 3-point alignment and ICP use every point.');
    else if (typeof b === 'string') this.setStatus(b);
    else {
      const f = (v: Vec3): string => v.map((x) => x.toFixed(2)).join(', ');
      this.setStatus(`Align within the ${b.label}: 3-point alignment uses the pairs whose model point lies in the box (${f(b.min)}) to (${f(b.max)}); ICP fits the cloud points inside it.`);
    }
  }

  // ---------------------------------------------------------------- picking

  /** Shown cloud point under a client position (nearest on screen within `radiusPx`, frontmost surface first). */
  pickCloudAt(clientX: number, clientY: number, radiusPx = 8): { index: number; cloud: Vec3; world: Vec3 } | null {
    if (!this.points || !this.mapped || !this.frame || !this.settings.visible) return null;
    const r = this.app.canvas.getBoundingClientRect();
    const idx = this.screenIndex(r.width, r.height);
    const maxDepth = this.occluderDepth(clientX, clientY);
    const i = pickNearest(idx, clientX - r.left, clientY - r.top, { radiusPx, innerPx: this.settings.pointSize / 2 + 1, maxDepth });
    if (i < 0) return null;
    return { index: i, cloud: this.cloudPoint(i)!, world: this.pointPosition(i)! };
  }

  /**
   * View depth of the first model surface under a client position that hides cloud points: not hidden, not ghosted
   * below OCCLUDE_ALPHA (a ghost is drawn see-through, so the points behind it are visible and pickable). Infinity
   * when there is none.
   */
  occluderDepth(clientX: number, clientY: number): number {
    const app = this.app;
    const loaded = app.loaded;
    if (!loaded) return Infinity;
    const r = app.canvas.getBoundingClientRect();
    const cam = app.renderer.camera;
    cam.updateMatrixWorld();
    const ray = cameraRay(cam, ((clientX - r.left) / r.width) * 2 - 1, -(((clientY - r.top) / r.height) * 2 - 1));
    const hides = app.controller.settings.overrides.userHides;
    const alpha = app.renderer.state.alpha;
    const hit = firstSurfaceHit(loaded.geometry, ray, (id) => hides.has(id) || (alpha[id] ?? 1) < OCCLUDE_ALPHA);
    if (!hit) return Infinity;
    // section planes cut the surface away too: a hit on the removed side does not hide anything
    for (const p of this.material.clippingPlanes ?? []) if (p.distanceToPoint(hit.point) < 0) return Infinity;
    return -hit.point.clone().applyMatrix4(cam.matrixWorldInverse).z;
  }

  private screenIndex(width: number, height: number): ScreenIndex {
    const cam = this.app.renderer.camera;
    cam.updateMatrixWorld();
    const view = new Matrix4().multiplyMatrices(cam.matrixWorldInverse, this.frame!.matrix);
    const clip = new Matrix4().multiplyMatrices(cam.projectionMatrix, view);
    const planes = this.material.clippingPlanes;
    const sig = `${this.version}|${width}x${height}|${clip.elements.map((v) => v.toPrecision(10)).join(',')}|${this.clipSig}`;
    if (this.screen && this.screen.sig === sig) return this.screen.idx;
    const index = this.geom?.getIndex();
    const M = this.frame!.matrix.elements;
    const keep = planes && planes.length
      ? (x: number, y: number, z: number): boolean => {
        const wx = M[0]! * x + M[4]! * y + M[8]! * z + M[12]!, wy = M[1]! * x + M[5]! * y + M[9]! * z + M[13]!, wz = M[2]! * x + M[6]! * y + M[10]! * z + M[14]!;
        for (const p of planes) if (p.normal.x * wx + p.normal.y * wy + p.normal.z * wz + p.constant < 0) return false;
        return true;
      }
      : undefined;
    const idx = buildScreenIndex({
      positions: this.mapped!, clip: clip.elements, view: view.elements, width, height, cell: 8,
      indices: index ? (index.array as Uint32Array) : null, keep,
    });
    this.screen = { sig, idx };
    return idx;
  }

  /**
   * Model surface point under a client position, as the measure tool picks it: first surface along the camera ray,
   * skipping hidden elements (ghosted ones count), snapped to a vertex of the hit triangle within 12 px.
   */
  pickModelAt(clientX: number, clientY: number, snapPx = 12): { point: Vec3; element: number; snapped: boolean } | null {
    const app = this.app;
    const loaded = app.loaded;
    if (!loaded) return null;
    const r = app.canvas.getBoundingClientRect();
    const px = clientX - r.left, py = clientY - r.top;
    const cam = app.renderer.camera;
    cam.updateMatrixWorld();
    const ray = cameraRay(cam, (px / r.width) * 2 - 1, -((py / r.height) * 2 - 1));
    const hides = app.controller.settings.overrides.userHides;
    const alpha = app.renderer.state.alpha;
    const hit = firstSurfaceHit(loaded.geometry, ray, (id) => hides.has(id) || (alpha[id] ?? 1) < 0);
    if (!hit) return null;
    const p: Vec3 = [hit.point.x, hit.point.y, hit.point.z];
    if (snapPx <= 0) return { point: p, element: hit.element, snapped: false };
    const ov = getOverlay(app);
    const s = snapToVertex(p, hit.triangle, { x: px, y: py }, (v) => ov.project(v), snapPx);
    return { point: [s.point[0], s.point[1], s.point[2]], element: hit.element, snapped: s.snapped };
  }

  // ---------------------------------------------------------------- 3-point alignment

  get pairMode(): boolean {
    return !!this.pairs;
  }

  /** What the next click picks. */
  get pairStep(): 'cloud' | 'model' {
    const last = this.pairs?.[this.pairs.length - 1];
    return last && last.cloud && !last.model ? 'model' : 'cloud';
  }

  get completePairs(): Array<{ cloud: Vec3; model: Vec3 }> {
    return (this.pairs ?? []).filter((p): p is { cloud: Vec3; model: Vec3 } => !!p.cloud && !!p.model);
  }

  /** The complete pairs the solve uses: those whose model point lies in the `align within` region (all without one). */
  get solvedPairs(): Array<{ cloud: Vec3; model: Vec3 }> {
    const box = this.regionBox();
    const all = this.completePairs;
    if (!box || typeof box === 'string') return all;
    return all.filter((p) => p.model.every((v, k) => v >= box.min[k]! && v <= box.max[k]!));
  }

  startPairs(): boolean {
    if (!this.loaded) {
      this.setStatus('Align by 3 points needs a point cloud. Open one first.');
      return false;
    }
    if (!this.app.loaded) {
      this.setStatus('Align by 3 points needs a model.');
      return false;
    }
    this.pairs = [];
    this.pairSolution = null;
    this.setStatus(this.pairPrompt());
    return true;
  }

  cancelPairs(): void {
    if (!this.pairs) return;
    this.pairs = null;
    this.pairSolution = null;
    this.setStatus('Align by 3 points cancelled: the alignment did not change.');
  }

  /** Remove the last pick (half a pair, or the model point of the last pair). */
  undoPair(): void {
    const ps = this.pairs;
    if (!ps || !ps.length) return;
    const last = ps[ps.length - 1]!;
    if (last.model) last.model = null;
    else ps.pop();
    this.resolvePairs();
  }

  addCloudPoint(c: Vec3): void {
    if (!this.pairs) return;
    if (this.pairStep === 'model') this.pairs[this.pairs.length - 1]!.cloud = c; // re-pick the pending cloud point
    else this.pairs.push({ cloud: c, model: null });
    this.resolvePairs();
  }

  addModelPoint(v: Vec3): void {
    if (!this.pairs || this.pairStep !== 'model') return;
    this.pairs[this.pairs.length - 1]!.model = v;
    this.resolvePairs();
  }

  /** Solve again with the complete pairs and the current keep vertical / allow scale. */
  resolvePairs(): void {
    if (!this.pairs) return;
    const done = this.solvedPairs;
    const s = this.settings;
    this.pairSolution = done.length ? solvePairs(done.map((p) => p.cloud), done.map((p) => p.model), { keepVertical: s.keepVertical, allowScale: s.allowScale }) : null;
    const left = this.completePairs.length - done.length;
    if (left > 0) {
      const box = this.regionBox() as RegionBox;
      const w = `${left} pair${left > 1 ? 's' : ''} outside the ${box.label} ${left > 1 ? 'are' : 'is'} not used.`;
      if (this.pairSolution) this.pairSolution.warnings.push(w);
    }
    this.setStatus(this.pairPrompt());
  }

  pairPrompt(): string {
    const ps = this.pairs;
    if (!ps) return this.status;
    const n = this.solvedPairs.length;
    const k = ps.length + (this.pairStep === 'cloud' ? 1 : 0);
    const next = this.pairStep === 'cloud' ? `Click point ${k} on the cloud` : `Click the matching point ${k} on the model`;
    const sol = this.pairSolution;
    const tail = n >= 3 && sol?.ok ? `, or Apply (RMS ${formatDistance(sol.rms)})` : n > 0 && n < 3 ? ` (${n} of 3 pairs)` : '';
    return `${next}${tail}. Esc undoes a pending point, then cancels.`;
  }

  /** Apply the pair solution as the new alignment. Returns false when there is none. */
  applyPairs(): boolean {
    const sol = this.pairSolution;
    const n = this.solvedPairs.length;
    if (!this.pairs || !sol || !sol.ok || n < 3) {
      this.setStatus(sol && !sol.ok ? sol.warnings.join(' ') : 'Pick 3 pairs first.');
      return false;
    }
    const before = this.totalMatrix;
    const reg = this.regionBox();
    const within = reg && typeof reg !== 'string' ? `, within the ${reg.label}` : '';
    const desc = `3-point alignment from ${n} pairs (${this.settings.keepVertical ? 'keep vertical' : 'full 3D'}${this.settings.allowScale ? `, scale ${sol.scale.toFixed(4)}` : ''}${within}): RMS ${formatDistance(sol.rms)}.`;
    this.pairs = null;
    this.pairSolution = null;
    this.applyTotal(sol.matrix, desc);
    const ch = transformError(before, sol.matrix, this.frame?.pivot ?? [0, 0, 0]);
    this.setStatus(`${desc} Moved ${formatDistance(ch.translation)}, turned ${ch.rotationDeg.toFixed(2)} deg; ${this.describeTransform()}. Refine (ICP) fits it to the surfaces.`);
    return true;
  }

  // ---------------------------------------------------------------- ICP

  /** Closest surface point and unit normal for the scope (normals from the hit triangle), or null without geometry. */
  closestFn(scope: DeviationScope): ClosestFn | null {
    const geo = this.app.loaded?.geometry;
    if (!geo) return null;
    let trees: MeshBVH[];
    if (scope === 'all elements') trees = [geo.bvh];
    else {
      const focus = this.app.controller.classification.focus;
      trees = [...focus].map((id) => geo.subGeometry(id)?.boundsTree as MeshBVH | undefined).filter((t): t is MeshBVH => !!t);
    }
    if (!trees.length) return null;
    return bvhClosestFn(trees);
  }

  /**
   * Fine registration: trimmed point-to-plane ICP of a spatially uniform sample of the shown points against the model
   * surface (the deviation scope decides which surfaces). Applies the result when it improved the fit; reverts and
   * says so otherwise. Resolves with the result, or null when cancelled or not possible.
   */
  async refine(opts: { samples?: number; maxIterations?: number; startDistance?: number; trim?: number; minDistance?: number; normals?: boolean } = {}): Promise<IcpResult | null> {
    if (!this.shown || !this.mapped || !this.frame) {
      this.setStatus('Refine (ICP) needs a point cloud. Open one first.');
      return null;
    }
    const scope = this.settings.scope;
    const closest = this.closestFn(scope);
    if (!closest) {
      this.setStatus(scope === 'focus only' ? 'Refine (ICP) with scope "focus only" needs a selection.' : 'Refine (ICP) needs a model with geometry.');
      return null;
    }
    const region = this.regionBox();
    if (typeof region === 'string') {
      this.setStatus(region);
      return null;
    }
    this.cancel = false;
    const token = ++this.token;
    this.busy = true;
    this.icpToken = token;
    const t0 = performance.now();
    this.setStatus('Refine (ICP): choosing sample points...');
    try {
      // the shown points in the region (all of them without one): their mapped positions, for the sample and normals
      const b = this.frame.base;
      const total = this.totalMatrix;
      let pool = this.mapped;
      if (region) {
        const keep: number[] = [];
        const n = this.mapped.length / 3;
        const g: Vec3 = [0, 0, 0];
        for (let i = 0; i < n; i++) {
          g[0] = this.mapped[i * 3]! + b[0]; g[1] = this.mapped[i * 3 + 1]! + b[1]; g[2] = this.mapped[i * 3 + 2]! + b[2];
          const v = applyMat(total, g);
          if (v[0] >= region.min[0] && v[0] <= region.max[0] && v[1] >= region.min[1] && v[1] <= region.max[1] && v[2] >= region.min[2] && v[2] <= region.max[2]) keep.push(i);
        }
        pool = new Float32Array(keep.length * 3);
        keep.forEach((i, k) => pool.set(this.mapped!.subarray(i * 3, i * 3 + 3), k * 3));
        if (keep.length < 200) {
          this.setStatus(`Refine (ICP): only ${keep.length} cloud points lie in the ${region.label}: align roughly first, or choose a larger region.`);
          return null;
        }
      }
      const pick = voxelSample(pool, opts.samples ?? ICP_SAMPLES);
      const pts = new Float64Array(pick.length * 3);
      for (let k = 0; k < pick.length; k++) {
        const j = pick[k]! * 3;
        pts[k * 3] = pool[j]! + b[0];
        pts[k * 3 + 1] = pool[j + 1]! + b[1];
        pts[k * 3 + 2] = pool[j + 2]! + b[2];
      }
      // normals: PCA on the sample, oriented by occlusion in a denser copy and towards the scanner when the file's own
      // origin lies inside the cloud (a scanner frame: a phone scan starts there)
      let nrm: CloudNormals | null = null;
      if (opts.normals !== false) {
        this.setStatus('Refine (ICP): estimating point normals...');
        // the dense copy: every shown point in the pool, thinned by a stride to at most 100 000
        const step = Math.max(1, Math.ceil(pool.length / 3 / 100_000));
        const dense = step === 1 ? pool : Float32Array.from({ length: Math.floor(pool.length / 3 / step) * 3 }, (_, k) => pool[(Math.floor(k / 3) * step) * 3 + (k % 3)]!);
        nrm = await estimateNormalsAsync(pts, { dense: { positions: dense, base: b }, viewpoint: this.scannerOrigin(), isCancelled: () => this.cancel || token !== this.token });
        if (!nrm) {
          if (token === this.token) this.setStatus('Refine (ICP) stopped: the alignment did not change.');
          return null;
        }
      }
      const keepVertical = this.settings.keepVertical;
      const r = await icp({
        points: pts, normals: nrm?.normals, oriented: nrm?.oriented, initial: total, closest, keepVertical, maxIterations: opts.maxIterations, startDistance: opts.startDistance, trim: opts.trim, minDistance: opts.minDistance,
        onProgress: (it, rms) => { if (token === this.token) this.setStatus(`Refine (ICP): iteration ${it}, RMS ${formatDistance(rms)}`); },
        onSearch: (k, n) => { if (token === this.token) this.setStatus(`Refine (ICP): trying start heading ${k} of ${n}`); },
        isCancelled: () => this.cancel || token !== this.token,
      });
      if (!r || token !== this.token) {
        if (token === this.token) this.setStatus('Refine (ICP) stopped: the alignment did not change.');
        return null;
      }
      const ms = performance.now() - t0;
      const drift = driftNote(r.regions);
      this.stats.icp = {
        iterations: r.iterations, converged: r.converged, reverted: r.reverted, rmsBefore: r.before.rms, rmsAfter: r.after.rms,
        inlierFraction: r.after.inlierFraction, samples: pick.length, ms, reason: r.reason,
        normalMode: r.normalMode, withNormal: nrm?.valid ?? 0, oriented: nrm?.orientedCount ?? 0, region, regions: r.regions, drift,
      };
      const head = `ICP (${keepVertical ? 'keep vertical' : 'full 3D'}, ${pick.length.toLocaleString('en-US')} points${region ? ` in the ${region.label}` : ''}, ${scope}${r.normalMode === 'oriented' ? ', oriented normals' : r.normalMode === 'axis' ? ', normals' : ''})`;
      const nums = `RMS ${formatDistance(r.before.rms)} -> ${formatDistance(r.after.rms)} within ${formatDistance(r.scoreDistance)}, inliers ${(r.before.inlierFraction * 100).toFixed(0)}% -> ${(r.after.inlierFraction * 100).toFixed(0)}%`;
      if (r.ok) {
        const ch = transformError(this.totalMatrix, r.matrix, this.frame.pivot);
        const desc = `${head}: ${r.iterations} iterations${r.searchYawDeg ? ` from a start turned ${r.searchYawDeg} deg` : ''}, ${r.converged ? 'converged' : r.reason}; ${nums}.`;
        this.applyTotal(r.matrix, desc);
        this.setStatus(`${desc} Moved ${formatDistance(ch.translation)}, turned ${ch.rotationDeg.toFixed(3)} deg in ${(ms / 1000).toFixed(1)} s.${drift ? ` ${drift}` : ''}`);
      } else {
        this.setStatus(`${head}: ${r.reason}. ${nums}.`);
      }
      return r;
    } finally {
      if (token === this.token) this.busy = false;
      this.emit();
    }
  }

  /**
   * The source file's origin in the cloud frame when it lies inside the cloud's bounds (plus 1 m): then the file is in
   * a scanner's own frame (a phone scan starts at its origin, a single terrestrial scan sits at it), and normals can
   * turn towards it. Null for survey coordinates (the origin is far away) and when nothing is loaded.
   */
  scannerOrigin(): Vec3 | null {
    const i = this.info;
    if (!i) return null;
    const pad = 1;
    for (let k = 0; k < 3; k++) if (!(0 >= i.boundsMin[k]! - pad && 0 <= i.boundsMax[k]! + pad)) return null;
    // the cloud frame is the axis mapped source frame, shifted like the model in project coordinates
    return this.settings.coordinates === 'project' ? projectToViewer([0, 0, 0], this.shift()) : [0, 0, 0];
  }

  /** An ICP run is in progress. */
  get icpRunning(): boolean {
    return this.busy && this.icpToken === this.token;
  }

  /** Stop a running deviation or ICP. */
  cancelWork(): void {
    this.cancel = true;
  }

  // ---------------------------------------------------------------- queries for tests

  /** World (viewer) position of shown point i. */
  pointPosition(i: number): Vec3 | null {
    if (!this.mapped || !this.frame) return null;
    return applyFrame(this.frame, [this.mapped[i * 3]!, this.mapped[i * 3 + 1]!, this.mapped[i * 3 + 2]!]);
  }
}

const PLAN = [['north-west', 'north', 'north-east'], ['west', 'middle', 'east'], ['south-west', 'south', 'south-east']];

/** Name of a plan grid cell (viewer x east, z south). */
export function regionName(r: { ix: number; iz: number }): string {
  return PLAN[r.iz]![r.ix]!;
}

/**
 * One line on where the fit degrades, from the local misfit of the 3 x 3 plan grid (the translation that would fit
 * each cell alone; noise averages out of it): the worst cell with enough points against the typical one. '' when
 * the fit is even (worst under 4 mm, or under 2.5 x the median cell). A rigid fit of a scan that bends (the heading
 * drift of a long phone walk) is good in the middle and pulls the ends the opposite ways.
 */
export function driftNote(regions: readonly RegionResidual[], minCount = 40): string {
  const ok = regions.filter((r) => r.count >= minCount && Number.isFinite(r.misfit));
  if (ok.length < 3) return '';
  const sorted = ok.map((r) => r.misfit).sort((a, b) => a - b);
  const typical = sorted[sorted.length >> 1]!;
  const worst = ok.reduce((a, b) => (b.misfit > a.misfit ? b : a));
  if (worst.misfit < 0.004 || worst.misfit < 2.5 * typical) return '';
  return `The fit degrades towards the ${regionName(worst)}: that part sits ${formatDistance(worst.misfit)} off (typical ${formatDistance(typical)}), so the scan may bend (drift). Align that part on its own with align within.`;
}

function emptyStats(): PointCloudStats {
  return {
    loaded: false, name: '', format: '', originalCount: 0, shownCount: 0, parseMs: 0, decimateMs: 0, mode: '', warnings: [], deviation: null,
    deviationMs: 0, deviationScope: null, alignment: '', icp: null,
  };
}

export { PointCloudError };
