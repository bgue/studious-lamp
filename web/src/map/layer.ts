// The map under the model, drawn in the three.js scene. One group of textured tiles lying flat at the ground level of the model, in the
// ground frame (east, north) turned and scaled to the model by the Georef. The tiles are a plain part of the scene with these rules:
//   - no raycast (picks walk the per-element BVHs; the tiles are never a pick, a measurement or a classification target), and the
//     group is not in the model's bounds, which come from the geometry, so fit, section and explode do not see it;
//   - drawn first among the transparent objects (renderOrder far below everything), depth test on, no depth write, behind the model by a
//     small polygon offset: the opaque model and its section caps are drawn over it, the x-ray and ghost passes keep their own order;
//   - not clipped by the section planes: it is the ground the model stands on, a cut through the building does not cut the earth away;
//   - front side only: from below the ground is not drawn, so the x-ray view from underneath is not covered;
//   - its own private scenes: the radiograph and MRI views and the classification pictures never draw it.
// Docs: docs-features/map.md.

import { BufferGeometry, Float32BufferAttribute, Group, Mesh, Raycaster, ShaderMaterial, SRGBColorSpace, Texture } from 'three';
import type { PerspectiveCamera, Scene } from 'three';
import { enuOf, fromMercator, groundResolution, tileMercatorBounds, tilesForDisc, zoomForDistance } from './geo';
import type { Georef, TileId } from './geo';
import type { MapProvider } from './providers';
import { tileUrl } from './providers';
import { TileCache } from './tiles';
import type { TileFetcher } from './tiles';

const VERT = /* glsl */ `
varying vec2 vUv;
varying vec2 vLocal;
void main() {
  vUv = uv;
  vLocal = position.xz;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}`;

const FRAG = /* glsl */ `
uniform sampler2D map;
uniform float uAlpha;
uniform float uRadius;
varying vec2 vUv;
varying vec2 vLocal;
void main() {
  float d = length(vLocal);
  if (d > uRadius) discard;
  vec4 c = texture2D(map, vUv);
  float rim = 1.0 - smoothstep(0.92 * uRadius, uRadius, d);
  gl_FragColor = vec4(c.rgb, uAlpha * rim);
  #include <colorspace_fragment>
}`;

export const FADE_MS = 350;
export const MAX_TILES = 72;
export const RENDER_ORDER_BASE = -1000;
/** The map lies this far under the ground level (metres), and is pushed back in depth, so a floor slab at the same height wins. */
export const SINK = 0.02;

interface TileMesh {
  key: string;
  z: number;
  mesh: Mesh;
  material: ShaderMaterial;
  born: number;
}

export interface LayerConfig {
  georef: Georef | null;
  provider: MapProvider | null;
  apiKey: string | null;
  radius: number;
  opacity: number;
  /** Ground height in the viewer frame (y), metres. */
  y: number;
  enabled: boolean;
}

export interface LayerState {
  visible: boolean;
  zoom: number | null;
  tiles: number;
  tilesWanted: number;
  tilesReady: number;
  pending: number;
  requested: number;
  evicted: number;
  cached: number;
  /** Height of the group in the viewer frame. */
  y: number;
}

export class MapLayer {
  readonly group = new Group();
  private readonly tiles = new Map<string, TileMesh>();
  private readonly cache: TileCache<ImageBitmap>;
  private cfg: LayerConfig = { georef: null, provider: null, apiKey: null, radius: 150, opacity: 1, y: 0, enabled: false };
  private zoom: number | null = null;
  private wanted: TileId[] = [];
  private builtFor = '';
  private animating = false;
  private cacheFor = '';
  /** Until this time a rebuilt tile (the location was moved) shows at once instead of fading in again. */
  private instantUntil = 0;

  constructor(private readonly scene: Scene, fetcher: TileFetcher<ImageBitmap>, private readonly onChange: () => void, capacity = 256) {
    this.group.name = 'map-ground';
    this.group.visible = false;
    this.group.userData['mapGround'] = true;
    this.group.raycast = () => {};
    this.cache = new TileCache<ImageBitmap>({
      fetcher, capacity, onChange: () => this.onChange(),
      onEvict: (e) => { (e.extra as { dispose(): void } | null | undefined)?.dispose(); e.extra = null; },
    });
  }

  attach(): void {
    if (this.group.parent !== this.scene) this.scene.add(this.group);
  }

  dispose(): void {
    this.clearMeshes();
    this.cache.clear();
    this.scene.remove(this.group);
  }

  get tileCache(): TileCache<ImageBitmap> { return this.cache; }

  configure(c: LayerConfig): void {
    const prev = this.cfg;
    this.cfg = c;
    const source = c.provider ? `${c.provider.id}|${c.provider.template}` : '';
    if (source !== this.cacheFor) {
      // another provider (or template): the old tiles are of no use
      this.cacheFor = source;
      this.cache.clear();
      this.clearMeshes();
    }
    if (!c.enabled || !c.georef || !c.provider) {
      this.cache.cancelAll();
      this.group.visible = false;
      return;
    }
    const sig = this.sigOf(c);
    if (this.builtFor !== sig) this.clearMeshes();
    this.group.position.y = c.y - SINK;
    this.applyFrame();
    for (const t of this.tiles.values()) this.setUniforms(t, 0);
    if (prev.opacity !== c.opacity || prev.radius !== c.radius) this.onChange();
  }

  private sigOf(c: LayerConfig): string {
    const g = c.georef!;
    return `${g.lat.toFixed(7)},${g.lon.toFixed(7)},${g.rotation.toFixed(4)},${g.scale.toFixed(5)}`;
  }

  private clearMeshes(): void {
    for (const t of this.tiles.values()) {
      this.group.remove(t.mesh);
      t.mesh.geometry.dispose();
      t.material.dispose();
    }
    this.tiles.clear();
    this.builtFor = '';
    this.zoom = null;
  }

  private setUniforms(t: TileMesh, now: number): void {
    const u = t.material.uniforms;
    const fade = now === 0 ? 1 : Math.min(1, (now - t.born) / FADE_MS);
    u['uAlpha']!.value = this.cfg.opacity * fade;
    u['uRadius']!.value = this.cfg.radius; // ground metres: the tiles are built in ground metres, before the group's scale
  }

  /**
   * Per frame. Chooses the zoom from the camera, asks for the tiles of the disc, builds a mesh for each that has arrived and fades
   * it in, and drops the tiles of an older zoom once the new ones are all there. Returns true while a render is still needed
   * (a fade is running).
   */
  update(now: number, camera: PerspectiveCamera, viewportPx: number): boolean {
    const c = this.cfg;
    const visible = c.enabled && !!c.georef && !!c.provider;
    if (this.group.visible !== visible) this.group.visible = visible;
    if (!visible) { this.wanted = []; return false; }
    const g = c.georef!;
    const p = c.provider!;
    this.attach();
    const sig = this.sigOf(c);
    if (this.builtFor !== sig) {
      if (this.builtFor) this.instantUntil = now + 800;
      this.clearMeshes();
      this.builtFor = sig;
    }

    // Ground ENU radius to the disc; the camera distance is to the middle of the disc, at ground level.
    const dist = Math.hypot(camera.position.x, camera.position.y - c.y, camera.position.z);
    const z = zoomForDistance(dist, camera.fov, viewportPx, g.lat, { minZoom: p.minZoom, maxZoom: p.maxZoom, maxTiles: MAX_TILES, radius: c.radius }, this.zoom ?? undefined);
    this.zoom = z;
    this.wanted = tilesForDisc(g.lat, g.lon, c.radius, z);

    let missing = 0;
    const wantKeys = new Set<string>();
    this.wanted.forEach((t, i) => {
      const key = `${p.id}/${t.z}/${t.x}/${t.y}`;
      wantKeys.add(key);
      const e = this.cache.request(key, tileUrl(p.template, t.z, t.x, t.y, c.apiKey ?? undefined), i);
      if (e.state === 'ready' && e.image) {
        if (!this.tiles.has(key)) this.build(key, t, e, now);
      } else if (e.state === 'loading') missing++;
    });

    // Older zoom levels stay until the current one is complete (or what could not load has failed), then go.
    if (missing === 0) {
      for (const [k, t] of this.tiles) if (t.z !== z && !wantKeys.has(k)) this.remove(k, t);
    }
    // tiles of the current zoom that left the disc
    for (const [k, t] of this.tiles) if (t.z === z && !wantKeys.has(k)) this.remove(k, t);

    let anim = false;
    for (const t of this.tiles.values()) {
      const f = (now - t.born) / FADE_MS;
      this.setUniforms(t, now);
      if (f < 1) anim = true;
    }
    this.animating = anim;
    return anim;
  }

  private remove(k: string, t: TileMesh): void {
    this.group.remove(t.mesh);
    t.mesh.geometry.dispose();
    t.material.dispose();
    this.tiles.delete(k);
  }

  private build(key: string, t: TileId, e: { image?: ImageBitmap; extra?: { dispose(): void } | null }, now: number): void {
    const g = this.cfg.georef!;
    let tex = e.extra as Texture | null | undefined; // made once per tile and kept with the cache entry
    if (!tex) {
      tex = new Texture(e.image as ImageBitmap);
      tex.colorSpace = SRGBColorSpace;
      tex.flipY = false;
      tex.generateMipmaps = true;
      tex.anisotropy = 4;
      tex.needsUpdate = true;
      e.extra = tex;
    }
    const [w, s, ea, no] = tileMercatorBounds(t);
    // ground metres east, north of the model's middle: the corners are exact, the inside is linear (a tile is 80 m or less at the
    // zoom of a close view; the bend of latitude over it is under a millimetre)
    const [latN, lonW] = fromMercator(w, no);
    const [latS, lonE] = fromMercator(ea, s);
    const [e0, n1] = enuOf(latN, lonW, g.lat, g.lon);
    const [e1, n0] = enuOf(latS, lonE, g.lat, g.lon);
    const geo = new BufferGeometry();
    // north-west, north-east, south-east, south-west; x east, z south (z = -north)
    geo.setAttribute('position', new Float32BufferAttribute([e0, 0, -n1, e1, 0, -n1, e1, 0, -n0, e0, 0, -n0], 3));
    geo.setAttribute('uv', new Float32BufferAttribute([0, 0, 1, 0, 1, 1, 0, 1], 2));
    geo.setIndex([0, 3, 2, 0, 2, 1]);
    geo.computeBoundingSphere();
    const mat = new ShaderMaterial({
      vertexShader: VERT, fragmentShader: FRAG,
      uniforms: { map: { value: tex }, uAlpha: { value: 0 }, uRadius: { value: this.cfg.radius }, },
      transparent: true, depthWrite: false, depthTest: true, toneMapped: false, fog: false,
      polygonOffset: true, polygonOffsetFactor: 2, polygonOffsetUnits: 2,
    });
    const mesh = new Mesh(geo, mat);
    mesh.name = `map-tile:${t.z}/${t.x}/${t.y}`;
    mesh.renderOrder = RENDER_ORDER_BASE + t.z;
    mesh.frustumCulled = false;
    mesh.raycast = () => {};
    mesh.userData['mapTile'] = key;
    this.tiles.set(key, { key, z: t.z, mesh, material: mat, born: now < this.instantUntil ? now - FADE_MS : now });
    this.group.add(mesh);
    this.onChange();
  }

  /** The group is turned and scaled to the model: ground metres (east, north) to viewer metres. */
  private applyFrame(): void {
    const g = this.cfg.georef;
    if (!g) return;
    this.group.rotation.set(0, (g.rotation * Math.PI) / 180, 0);
    this.group.scale.setScalar(1 / g.scale);
  }

  state(): LayerState {
    let ready = 0;
    for (const t of this.wanted) if (this.cache.get(`${this.cfg.provider?.id}/${t.z}/${t.x}/${t.y}`)?.state === 'ready') ready++;
    return {
      visible: this.group.visible, zoom: this.zoom, tiles: this.tiles.size, tilesWanted: this.wanted.length, tilesReady: ready,
      pending: this.cache.pending, requested: this.cache.stats.requested, evicted: this.cache.stats.evicted, cached: this.cache.entries.size, y: this.group.position.y,
    };
  }

  /** Whether anything in the group answers a ray (it must not). */
  get pickable(): boolean {
    const rc = new Raycaster();
    rc.ray.origin.set(0, 100, 0);
    rc.ray.direction.set(0, -1, 0);
    return rc.intersectObject(this.group, true).length > 0;
  }

  get fading(): boolean { return this.animating; }
  /** Ground metres per tile pixel at the zoom now drawn (0 when none). */
  resolution(): number { const g = this.cfg.georef; return g && this.zoom !== null ? groundResolution(g.lat, this.zoom) : 0; }
}
