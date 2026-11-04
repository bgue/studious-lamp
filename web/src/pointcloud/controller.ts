// Point cloud controller: owns the THREE.Points in the main scene, the display and alignment settings, the loader
// and the deviation check. UI (drawer, lil-gui) and the window API only talk to this class.

import { BufferAttribute, BufferGeometry, Plane, Points, PointsMaterial, Vector3 } from 'three';
import type { MeshBVH } from 'three-mesh-bvh';
import type { ViewerApp } from '../app';
import { applyFrame, autoAlign, cloudFrame, mapPositions } from './align';
import type { AutoAlignResult, CloudFrame, CoordMode } from './align';
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
  tolerance: number;
  scope: DeviationScope;
}

export function defaultPointCloudSettings(): PointCloudSettings {
  return {
    visible: true, pointSize: 2, sizeAttenuation: false, colourBy: 'rgb', budget: DEFAULT_BUDGET, coordinates: 'project',
    offsetX: 0, offsetY: 0, offsetZ: 0, rotationDeg: 0, tolerance: 0.02, scope: 'all elements',
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
  status = 'No point cloud loaded. Open a .las, .ply, .pcd, .xyz, .pts or .txt file.';
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
    Object.assign(this.stats, emptyStats());
    this.busy = false;
    this.hideLegend();
    this.setStatus('No point cloud loaded. Open a .las, .ply, .pcd, .xyz, .pts or .txt file.');
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
    this.frame = cloudFrame(this.info, { mode: s.coordinates, shift: this.shift(), offset: [s.offsetX, s.offsetY, s.offsetZ], rotationDeg: s.rotationDeg });
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
    this.settings.coordinates = mode;
    if (!this.shown || !this.info) return;
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
    s.offsetX = r.offset[0];
    s.offsetY = r.offset[1];
    s.offsetZ = r.offset[2];
    s.rotationDeg = r.rotationDeg;
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
        // bottom right of the stage, clear of the debug text bottom left
        this.legendLayer?.setAttribute('transform', `translate(${Math.max(8, o.width - 190 - 12)},${Math.max(8, o.height - 22 - 4 * 18 - 12)})`);
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
    deviationMs: 0, deviationScope: null, alignment: '',
  };
}

export { PointCloudError };
