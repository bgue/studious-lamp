// The map: where the model is, what is drawn under it, and the settings. Holds no DOM and no lil-gui (src/map/ui.ts has those), so
// the pieces can move to another panel. Docs: docs-features/map.md.
//
// Privacy. `enabled` is false at start and is never stored. Nothing is requested while it is false (the tile cache is only asked from
// MapLayer.update, which returns at once while off), and turning it on for a host that has not been accepted first goes through the
// notice: the person must agree before the first request.

import type { PerspectiveCamera, Scene } from 'three';
import type { Georef, GeorefResult, ManualLocation } from './geo';
import { georefFromManual, resolveGeoref } from './geo';
import { MapLayer } from './layer';
import type { LayerState } from './layer';
import { activeProvider, privacyNotice } from './providers';
import type { MapProvider, ProviderId } from './providers';
import { MapSecrets, clampSettings, defaultMapSettings } from './settings';
import type { MapSettings } from './settings';
import { LocationStore } from './store';
import type { TileFetcher } from './tiles';
import type { MapConversion, SceneModel, SiteGeo } from '../types';

/** What the controller reads of the viewer. */
export interface MapHost {
  scene: Scene;
  camera: PerspectiveCamera;
  /** Pixels of the canvas height (device pixels). */
  viewportPx(): number;
  markDirty(): void;
  model(): Pick<SceneModel, 'originShift' | 'storeys' | 'elements' | 'mapConversion' | 'siteGeo'> | null;
  modelName(): string;
}

/** Ground height (viewer y) for a model: the lowest storey, else the bottom of the model. */
export function groundLevel(m: Pick<SceneModel, 'originShift' | 'storeys' | 'elements'>): { y: number; basis: string } {
  const shiftZ = m.originShift[2] ?? 0;
  let low = Infinity;
  for (const s of m.storeys) if (Number.isFinite(s.elevation)) low = Math.min(low, s.elevation);
  if (Number.isFinite(low)) return { y: low - shiftZ, basis: 'lowest storey' };
  let bottom = Infinity;
  for (const e of m.elements) if (Number.isFinite(e.bounds[1])) bottom = Math.min(bottom, e.bounds[1]);
  return Number.isFinite(bottom) ? { y: bottom, basis: 'bottom of the model' } : { y: 0, basis: 'origin' };
}

export interface MapControllerOptions {
  host: MapHost;
  fetcher: TileFetcher<ImageBitmap>;
  store: LocationStore;
  secrets?: MapSecrets;
  /** Asked before the first request to a host; resolve true to go on. Default: no (nothing is fetched without an answer). */
  confirm?: (text: string, host: string) => Promise<boolean>;
}

export class MapController {
  settings: MapSettings = defaultMapSettings();
  readonly secrets: MapSecrets;
  readonly layer: MapLayer;
  result: GeorefResult = { georef: null, status: 'Unknown', notes: [] };
  manual: ManualLocation | null = null;
  groundY = 0;
  groundBasis = 'origin';
  /** Why nothing is drawn although the map is on (a custom template that is not usable), or null. */
  problem: string | null = null;
  private provider: MapProvider | null = null;
  private key: string | null = null;
  private readonly listeners = new Set<() => void>();
  private modelKey = '';
  private loadToken = 0;

  constructor(private readonly o: MapControllerOptions) {
    this.secrets = o.secrets ?? new MapSecrets();
    this.layer = new MapLayer(o.host.scene, o.fetcher, () => o.host.markDirty());
  }

  onChange(cb: () => void): () => void {
    this.listeners.add(cb);
    return () => this.listeners.delete(cb);
  }

  private emit(): void {
    for (const l of this.listeners) l();
  }

  // ---------------------------------------------------------------- model

  /** A model was installed: read its stored manual location, then work out where it is. */
  async onModel(): Promise<void> {
    const token = ++this.loadToken;
    this.modelKey = this.o.host.modelName();
    this.manual = null;
    this.recompute();
    const stored = await this.o.store.get(this.modelKey);
    if (token !== this.loadToken) return;
    this.manual = stored;
    this.recompute();
  }

  /** Work out location, ground level and provider again and hand them to the layer. */
  recompute(): void {
    const m = this.o.host.model();
    if (m) {
      this.result = resolveGeoref({
        ...(m.mapConversion ? { mapConversion: m.mapConversion as MapConversion } : {}),
        ...(m.siteGeo ? { siteGeo: m.siteGeo as SiteGeo } : {}),
        manual: this.manual,
        shift: m.originShift,
      });
      const g = groundLevel(m);
      this.groundY = g.y;
      this.groundBasis = g.basis;
    } else {
      this.result = { georef: null, status: 'Unknown', notes: [] };
    }
    const a = activeProvider(this.settings.provider, this.secrets.custom(this.settings.customAttribution));
    this.provider = a.provider;
    this.key = a.key;
    this.problem = a.problem;
    this.apply();
    this.emit();
  }

  private apply(): void {
    const drawable = this.settings.enabled && !this.problem && !!this.result.georef;
    this.layer.configure({
      georef: this.result.georef, provider: this.provider, apiKey: this.key, radius: this.settings.radius,
      opacity: this.settings.opacity, y: this.groundY, enabled: drawable,
    });
    this.o.host.markDirty();
  }

  get georef(): Georef | null { return this.result.georef; }
  get activeProvider(): MapProvider | null { return this.provider; }

  /** The line under the controls. */
  get statusLine(): string {
    return this.result.status;
  }

  /** The attribution to show: only while tiles are drawn. */
  get attribution(): string | null {
    return this.layer.group.visible && this.provider ? this.provider.attribution : null;
  }

  // ---------------------------------------------------------------- settings

  patch(p: Partial<MapSettings>): void {
    const wasProvider = this.settings.provider;
    this.settings = clampSettings({ ...this.settings, ...p, enabled: this.settings.enabled });
    if (p.provider !== undefined && p.provider !== wasProvider) {
      // a provider is another party: it has to be agreed again before anything is asked from it
      if (this.settings.enabled && !this.acknowledged()) {
        this.settings.enabled = false;
      }
    }
    this.recompute();
  }

  /** Whether the notice for the provider in use was accepted. */
  acknowledged(): boolean {
    const a = activeProvider(this.settings.provider, this.secrets.custom(this.settings.customAttribution));
    return this.secrets.acknowledged(a.provider.host);
  }

  /**
   * Turn the map on or off. On: when the host has not been accepted before, the notice is asked first and the answer decides. Returns
   * whether the map is on afterwards.
   */
  async setEnabled(on: boolean): Promise<boolean> {
    if (!on) {
      this.settings.enabled = false;
      this.recompute();
      return false;
    }
    const a = activeProvider(this.settings.provider, this.secrets.custom(this.settings.customAttribution));
    if (a.problem) {
      this.settings.enabled = false;
      this.problem = a.problem;
      this.recompute();
      this.settings.enabled = false;
      return false;
    }
    if (!this.secrets.acknowledged(a.provider.host)) {
      const yes = (await this.o.confirm?.(privacyNotice(a.provider.host), a.provider.host)) ?? false;
      if (!yes) {
        this.settings.enabled = false;
        this.recompute();
        return false;
      }
      this.secrets.acknowledge(a.provider.host);
    }
    this.settings.enabled = true;
    this.recompute();
    return true;
  }

  // ---------------------------------------------------------------- location

  /** Set the manual location (kept per model in IndexedDB). */
  async setManual(loc: ManualLocation | null, persist = true): Promise<void> {
    this.manual = loc && georefFromManual(loc) ? { lat: loc.lat, lon: loc.lon, rotation: loc.rotation } : null;
    this.recompute();
    if (!persist) return;
    if (this.manual) await this.o.store.set(this.modelKey, this.manual);
    else await this.o.store.clear(this.modelKey);
  }

  /** The location the aligner starts from: the manual one, else what the model says, else nothing. */
  currentAsManual(): ManualLocation | null {
    const g = this.result.georef;
    return g ? { lat: g.lat, lon: g.lon, rotation: g.rotation } : null;
  }

  // ---------------------------------------------------------------- frame

  /** Per frame. True while a render is still needed. */
  tick(now: number): boolean {
    if (!this.settings.enabled) return false;
    return this.layer.update(now, this.o.host.camera, this.o.host.viewportPx());
  }

  state(): LayerState & { enabled: boolean; status: string; provider: ProviderId; problem: string | null; groundBasis: string; georef: Georef | null; notes: string[]; attribution: string | null } {
    return {
      ...this.layer.state(), enabled: this.settings.enabled, status: this.result.status, provider: this.settings.provider, problem: this.problem,
      groundBasis: this.groundBasis, georef: this.result.georef, notes: this.result.notes, attribution: this.attribution,
    };
  }

  dispose(): void {
    this.layer.dispose();
  }
}
