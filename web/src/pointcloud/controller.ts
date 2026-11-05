// Point cloud controller: owns the THREE.Points in the main scene, the display and alignment settings, the loader
// and the deviation check. UI (drawer, lil-gui) and the window API only talk to this class.

import { BufferAttribute, BufferGeometry, Matrix4, Plane, Points, PointsMaterial, Vector3 } from 'three';
import type { BufferGeometry as Geom } from 'three';
import { CLEARANCE_LEGEND_H, CLEARANCE_LEGEND_W } from '../measure/clearanceTool';
import { cameraRay, firstSurfaceHit } from '../measure/geometry';
import { snapToVertex } from '../measure/maths';
import type { MeshBVH } from 'three-mesh-bvh';
import type { ViewerApp } from '../app';
import { applyFrame, autoAlign, cloudFrame, decomposeTotal, mapPositions } from './align';
import type { AutoAlignResult, CloudFrame, CoordMode } from './align';
import { icp, voxelSample } from './icp';
import type { ClosestFn, IcpResult } from './icp';
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
  icp: { iterations: number; converged: boolean; reverted: boolean; rmsBefore: number; rmsAfter: number; inlierFraction: number; samples: number; ms: number; reason: string } | null;
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

  // ---------------------------------------------------------------- picking

  /** Shown cloud point under a client position (nearest on screen within `radiusPx`, frontmost surface first). */
  pickCloudAt(clientX: number, clientY: number, radiusPx = 8): { index: number; cloud: Vec3; world: Vec3 } | null {
    if (!this.points || !this.mapped || !this.frame || !this.settings.visible) return null;
    const r = this.app.canvas.getBoundingClientRect();
    const idx = this.screenIndex(r.width, r.height);
    const i = pickNearest(idx, clientX - r.left, clientY - r.top, { radiusPx, innerPx: this.settings.pointSize / 2 + 1 });
    if (i < 0) return null;
    return { index: i, cloud: this.cloudPoint(i)!, world: this.pointPosition(i)! };
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
    const done = this.completePairs;
    const s = this.settings;
    this.pairSolution = done.length ? solvePairs(done.map((p) => p.cloud), done.map((p) => p.model), { keepVertical: s.keepVertical, allowScale: s.allowScale }) : null;
    this.setStatus(this.pairPrompt());
  }

  pairPrompt(): string {
    const ps = this.pairs;
    if (!ps) return this.status;
    const n = this.completePairs.length;
    const k = ps.length + (this.pairStep === 'cloud' ? 1 : 0);
    const next = this.pairStep === 'cloud' ? `Click point ${k} on the cloud` : `Click the matching point ${k} on the model`;
    const sol = this.pairSolution;
    const tail = n >= 3 && sol?.ok ? `, or Apply (RMS ${formatDistance(sol.rms)})` : n > 0 && n < 3 ? ` (${n} of 3 pairs)` : '';
    return `${next}${tail}. Esc undoes a pending point, then cancels.`;
  }

  /** Apply the pair solution as the new alignment. Returns false when there is none. */
  applyPairs(): boolean {
    const sol = this.pairSolution;
    const n = this.completePairs.length;
    if (!this.pairs || !sol || !sol.ok || n < 3) {
      this.setStatus(sol && !sol.ok ? sol.warnings.join(' ') : 'Pick 3 pairs first.');
      return false;
    }
    const before = this.totalMatrix;
    const desc = `3-point alignment from ${n} pairs (${this.settings.keepVertical ? 'keep vertical' : 'full 3D'}${this.settings.allowScale ? `, scale ${sol.scale.toFixed(4)}` : ''}): RMS ${formatDistance(sol.rms)}.`;
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
    const p = new Vector3();
    const tgt = { point: new Vector3(), distance: 0, faceIndex: 0 };
    const normalOf = (g: Geom, f: number, out: number[]): void => {
      const pos = g.getAttribute('position');
      const idx = g.getIndex();
      const i0 = idx ? idx.getX(f * 3) : f * 3, i1 = idx ? idx.getX(f * 3 + 1) : f * 3 + 1, i2 = idx ? idx.getX(f * 3 + 2) : f * 3 + 2;
      const ax = pos.getX(i1) - pos.getX(i0), ay = pos.getY(i1) - pos.getY(i0), az = pos.getZ(i1) - pos.getZ(i0);
      const bx = pos.getX(i2) - pos.getX(i0), by = pos.getY(i2) - pos.getY(i0), bz = pos.getZ(i2) - pos.getZ(i0);
      const nx = ay * bz - az * by, ny = az * bx - ax * bz, nz = ax * by - ay * bx;
      const l = Math.hypot(nx, ny, nz) || 1;
      out[0] = nx / l; out[1] = ny / l; out[2] = nz / l;
    };
    return (x, y, z, max, out) => {
      p.set(x, y, z);
      let best = Infinity;
      let lim = max;
      for (const t of trees) {
        const r = t.closestPointToPoint(p, tgt, 0, lim);
        if (r && r.distance < best) {
          best = r.distance;
          lim = Math.min(lim, best);
          out.p[0] = r.point.x; out.p[1] = r.point.y; out.p[2] = r.point.z;
          normalOf(t.geometry, r.faceIndex, out.n);
        }
      }
      return best;
    };
  }

  /**
   * Fine registration: trimmed point-to-plane ICP of a spatially uniform sample of the shown points against the model
   * surface (the deviation scope decides which surfaces). Applies the result when it improved the fit; reverts and
   * says so otherwise. Resolves with the result, or null when cancelled or not possible.
   */
  async refine(opts: { samples?: number; maxIterations?: number; startDistance?: number; trim?: number; minDistance?: number } = {}): Promise<IcpResult | null> {
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
    this.cancel = false;
    const token = ++this.token;
    this.busy = true;
    this.icpToken = token;
    const t0 = performance.now();
    this.setStatus('Refine (ICP): choosing sample points...');
    try {
      const pick = voxelSample(this.mapped, opts.samples ?? ICP_SAMPLES);
      const b = this.frame.base;
      const pts = new Float64Array(pick.length * 3);
      for (let k = 0; k < pick.length; k++) {
        const j = pick[k]! * 3;
        pts[k * 3] = this.mapped[j]! + b[0];
        pts[k * 3 + 1] = this.mapped[j + 1]! + b[1];
        pts[k * 3 + 2] = this.mapped[j + 2]! + b[2];
      }
      const keepVertical = this.settings.keepVertical;
      const r = await icp({
        points: pts, initial: this.totalMatrix, closest, keepVertical, maxIterations: opts.maxIterations, startDistance: opts.startDistance, trim: opts.trim, minDistance: opts.minDistance,
        onProgress: (it, rms) => { if (token === this.token) this.setStatus(`Refine (ICP): iteration ${it}, RMS ${formatDistance(rms)}`); },
        onSearch: (k, n) => { if (token === this.token) this.setStatus(`Refine (ICP): trying start heading ${k} of ${n}`); },
        isCancelled: () => this.cancel || token !== this.token,
      });
      if (!r || token !== this.token) {
        if (token === this.token) this.setStatus('Refine (ICP) stopped: the alignment did not change.');
        return null;
      }
      const ms = performance.now() - t0;
      this.stats.icp = {
        iterations: r.iterations, converged: r.converged, reverted: r.reverted, rmsBefore: r.before.rms, rmsAfter: r.after.rms,
        inlierFraction: r.after.inlierFraction, samples: pick.length, ms, reason: r.reason,
      };
      const head = `ICP (${keepVertical ? 'keep vertical' : 'full 3D'}, ${pick.length.toLocaleString('en-US')} points, ${scope})`;
      const nums = `RMS ${formatDistance(r.before.rms)} -> ${formatDistance(r.after.rms)} within ${formatDistance(r.scoreDistance)}, inliers ${(r.before.inlierFraction * 100).toFixed(0)}% -> ${(r.after.inlierFraction * 100).toFixed(0)}%`;
      if (r.ok) {
        const ch = transformError(this.totalMatrix, r.matrix, this.frame.pivot);
        const desc = `${head}: ${r.iterations} iterations${r.searchYawDeg ? ` from a start turned ${r.searchYawDeg} deg` : ''}, ${r.converged ? 'converged' : r.reason}; ${nums}.`;
        this.applyTotal(r.matrix, desc);
        this.setStatus(`${desc} Moved ${formatDistance(ch.translation)}, turned ${ch.rotationDeg.toFixed(3)} deg in ${(ms / 1000).toFixed(1)} s.`);
      } else {
        this.setStatus(`${head}: ${r.reason}. ${nums}.`);
      }
      return r;
    } finally {
      if (token === this.token) this.busy = false;
      this.emit();
    }
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

function emptyStats(): PointCloudStats {
  return {
    loaded: false, name: '', format: '', originalCount: 0, shownCount: 0, parseMs: 0, decimateMs: 0, mode: '', warnings: [], deviation: null,
    deviationMs: 0, deviationScope: null, alignment: '', icp: null,
  };
}

export { PointCloudError };
