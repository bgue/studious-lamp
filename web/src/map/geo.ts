// Where the model is on Earth, and the tile maths for a map under it. Pure (no three.js, no DOM), tested in tests/map-geo.test.ts.
// Docs: docs-features/map.md.
//
// Frames. The viewer frame has x = IFC X, y = IFC Z (up), z = -IFC Y, with the origin at the middle of the model (originShift).
// A Georef says which latitude and longitude the viewer origin has, and how the model is turned against the ground:
//   east, north (metres) = scale * R(psi) * (x, -z)        R: counter-clockwise rotation, psi = -rotation
// `rotation` is the bearing of the model's +Y axis from true north, degrees, clockwise (0: the model's +Y points north). It is the
// same number as the IFC TrueNorth angle of src/model/ifcSite.ts.

import { utmForward, utmInverse, utmZoneOf } from '../sheets/geoPdf';
import type { MapConversion, SiteGeo } from '../types';

export const EARTH_R = 6378137;
const D2R = Math.PI / 180;
const R2D = 180 / Math.PI;
/** Metres per pixel of a 256 px web-mercator tile at zoom 0 on the equator. */
export const MPP_Z0 = (2 * Math.PI * EARTH_R) / 256;
export const MAX_LAT = 85.0511287798;

export type GeoSource = 'mapConversion' | 'site' | 'manual';

export interface Georef {
  /** Latitude and longitude (WGS 84 degrees) of the viewer origin: the middle of the model in plan. */
  lat: number;
  lon: number;
  /** Bearing of the model's +Y axis from true north, degrees clockwise. */
  rotation: number;
  /** Ground metres per model metre (1 unless the IFC says otherwise). */
  scale: number;
  source: GeoSource;
}

/** What is stored per model for the manual location (IndexedDB). */
export interface ManualLocation {
  lat: number;
  lon: number;
  rotation: number;
}

export interface GeorefResult {
  georef: Georef | null;
  /** The line the UI shows: "From IfcMapConversion (EPSG:25832)", "From IfcSite", "Manual" or "Unknown". */
  status: string;
  /** Why a step was skipped, for the UI. */
  notes: string[];
}

const finite = (n: unknown): n is number => typeof n === 'number' && Number.isFinite(n);

export function normaliseDeg(d: number): number {
  let r = ((d + 180) % 360 + 360) % 360 - 180;
  if (r === -180) r = 180;
  return r;
}

export function validLatLon(lat: unknown, lon: unknown): boolean {
  return finite(lat) && finite(lon) && Math.abs(lat) <= MAX_LAT && Math.abs(lon) <= 180;
}

// ---------------------------------------------------------------- web mercator and tiles

/** EPSG:3857 metres of a latitude and longitude in degrees. */
export function toMercator(lat: number, lon: number): [number, number] {
  const la = Math.max(-MAX_LAT, Math.min(MAX_LAT, lat));
  return [EARTH_R * lon * D2R, EARTH_R * Math.log(Math.tan(Math.PI / 4 + (la * D2R) / 2))];
}

export function fromMercator(x: number, y: number): [number, number] {
  return [(2 * Math.atan(Math.exp(y / EARTH_R)) - Math.PI / 2) * R2D, (x / EARTH_R) * R2D];
}

export interface TileId { z: number; x: number; y: number }

const HALF = Math.PI * EARTH_R;

/** The tile that holds a point at a zoom (x east, y south, origin at the top left), with the fraction inside the tile. */
export function tileOf(lat: number, lon: number, z: number): { x: number; y: number; fx: number; fy: number } {
  const n = 2 ** z;
  const [mx, my] = toMercator(lat, lon);
  const tx = ((mx + HALF) / (2 * HALF)) * n;
  const ty = ((HALF - my) / (2 * HALF)) * n;
  const x = Math.min(n - 1, Math.max(0, Math.floor(tx)));
  const y = Math.min(n - 1, Math.max(0, Math.floor(ty)));
  return { x, y, fx: tx - x, fy: ty - y };
}

/** Mercator bounds of a tile: west, south, east, north (metres). */
export function tileMercatorBounds(t: TileId): [number, number, number, number] {
  const n = 2 ** t.z;
  const size = (2 * HALF) / n;
  return [-HALF + t.x * size, HALF - (t.y + 1) * size, -HALF + (t.x + 1) * size, HALF - t.y * size];
}

/** Latitude and longitude of the north-west corner of a tile. */
export function tileNorthWest(t: TileId): [number, number] {
  const b = tileMercatorBounds(t);
  return fromMercator(b[0], b[3]);
}

/** Ground metres per pixel of a 256 px tile at a latitude and zoom. */
export function groundResolution(lat: number, z: number): number {
  return (MPP_Z0 * Math.cos(lat * D2R)) / 2 ** z;
}

/**
 * The tiles that touch a disc of `radius` ground metres around a point, at a zoom, nearest to the centre first. The disc is
 * measured on the ground: web mercator stretches lengths by 1 / groundScale(latitude).
 */
export function tilesForDisc(lat: number, lon: number, radius: number, z: number): TileId[] {
  const n = 2 ** z;
  const k = 1 / Math.max(1e-6, groundScale(lat));
  const [cx, cy] = toMercator(lat, lon);
  const r = radius * k;
  const size = (2 * HALF) / n;
  const x0 = Math.max(0, Math.floor((cx - r + HALF) / size));
  const x1 = Math.min(n - 1, Math.floor((cx + r + HALF) / size));
  const y0 = Math.max(0, Math.floor((HALF - (cy + r)) / size));
  const y1 = Math.min(n - 1, Math.floor((HALF - (cy - r)) / size));
  const out: Array<TileId & { d: number }> = [];
  for (let y = y0; y <= y1; y++) {
    for (let x = x0; x <= x1; x++) {
      const [w, s, e, no] = tileMercatorBounds({ z, x, y });
      const dx = Math.max(w - cx, 0, cx - e);
      const dy = Math.max(s - cy, 0, cy - no);
      if (dx * dx + dy * dy <= r * r) out.push({ z, x, y, d: Math.hypot((w + e) / 2 - cx, (s + no) / 2 - cy) });
    }
  }
  out.sort((a, b) => a.d - b.d);
  return out.map(({ z: zz, x, y }) => ({ z: zz, x, y }));
}

export interface ZoomOptions { minZoom: number; maxZoom: number; maxTiles: number; radius: number }

/**
 * The tile zoom for a camera: the one whose tile pixels are about as big as the screen pixels on the ground below the model
 * (`distance` metres from the camera), lowered while the disc would need more than `maxTiles` tiles. `current`, when given, is kept
 * as long as the wanted zoom is within `hysteresis` of it, so a camera that hovers on a boundary does not flip tile levels.
 */
export function zoomForDistance(distance: number, fovDeg: number, viewportPx: number, lat: number, o: ZoomOptions, current?: number, hysteresis = 0.75): number {
  const mppScreen = (2 * Math.max(distance, 0.1) * Math.tan((fovDeg * D2R) / 2)) / Math.max(1, viewportPx);
  const ideal = Math.log2((MPP_Z0 * Math.max(0.05, Math.cos(lat * D2R))) / mppScreen);
  let z = Math.round(ideal);
  if (current !== undefined && Math.abs(ideal - current) < hysteresis) z = current;
  z = Math.max(o.minZoom, Math.min(o.maxZoom, z));
  while (z > o.minZoom && tilesForDisc(lat, 0, o.radius, z).length > o.maxTiles) z--;
  return z;
}

// ---------------------------------------------------------------- local frame

const E2 = 0.0066943799901413165; // WGS 84 first eccentricity squared
const A = EARTH_R;

/**
 * Ground metres per radian of longitude (east) and of latitude (north) at a latitude, on the WGS 84 ellipsoid: N cos(lat) and M. Web
 * mercator puts the latitudes and longitudes of the ellipsoid on a sphere, so the tiles are not conformal with the ground: a degree
 * of latitude is 0.65 percent shorter than the sphere says at 10 degrees. The local frame below uses these radii, so a 100 m model
 * and the imagery under it agree and a turned model stays at its angle.
 */
export function groundRadii(lat: number): { east: number; north: number } {
  const la = lat * D2R;
  const w = 1 - E2 * Math.sin(la) ** 2;
  return { east: (A * Math.cos(la)) / Math.sqrt(w), north: (A * (1 - E2)) / w ** 1.5 };
}

/** Ground metres per web-mercator metre, the smaller of east and north (so a disc cut from tiles is never short). */
export function groundScale(lat: number): number {
  const r = groundRadii(lat);
  return Math.min(r.east / A, (r.north * Math.cos(lat * D2R)) / A);
}

/** East and north (ground metres) of a point relative to a centre, linear about the centre. */
export function enuOf(lat: number, lon: number, lat0: number, lon0: number): [number, number] {
  const r = groundRadii(lat0);
  return [(lon - lon0) * D2R * r.east, (lat - lat0) * D2R * r.north];
}

/** The reverse: latitude and longitude of a point at east, north ground metres from a centre. */
export function latLonOfEnu(e: number, n: number, lat0: number, lon0: number): [number, number] {
  const r = groundRadii(lat0);
  return [lat0 + (n / Math.max(1, r.north)) * R2D, lon0 + (e / Math.max(1, r.east)) * R2D];
}

/** East, north in ground metres of a viewer-frame offset (x, z) from the viewer origin. */
export function viewerToEnu(g: Pick<Georef, 'rotation' | 'scale'>, x: number, z: number): [number, number] {
  const psi = -g.rotation * D2R;
  const px = x, py = -z;
  return [g.scale * (px * Math.cos(psi) - py * Math.sin(psi)), g.scale * (px * Math.sin(psi) + py * Math.cos(psi))];
}

/** The viewer-frame offset (x, z) of a point at east, north ground metres from the viewer origin. */
export function enuToViewer(g: Pick<Georef, 'rotation' | 'scale'>, e: number, n: number): [number, number] {
  const psi = g.rotation * D2R; // inverse rotation
  const px = (e * Math.cos(psi) - n * Math.sin(psi)) / g.scale;
  const py = (e * Math.sin(psi) + n * Math.cos(psi)) / g.scale;
  return [px, -py];
}

// ---------------------------------------------------------------- where the model is

export const UTM_FAMILIES = 'EPSG 326xx, 327xx (WGS 84), 258xx (ETRS89) and 269xx (NAD83)';

/** Latitude and longitude of the IFC project point (x, y) metres under an IfcMapConversion, or null when its CRS is not a UTM one. */
export function projectToLatLon(m: MapConversion, x: number, y: number): [number, number] | null {
  const utm = m.crs.epsg ? utmZoneOf(m.crs.epsg) : null;
  if (!utm) return null;
  const e = m.eastings + m.scale * (m.xAxisAbscissa * x - m.xAxisOrdinate * y);
  const n = m.northings + m.scale * (m.xAxisOrdinate * x + m.xAxisAbscissa * y);
  const [lat, lon] = utmInverse(e, n, utm.zone, utm.south, utm.ellipsoid);
  return validLatLon(lat, lon) ? [lat, lon] : null;
}

/**
 * The place of a model from its IfcMapConversion and IfcProjectedCRS: the viewer origin is the IFC point (shift x, shift y). Only UTM
 * families are supported (EPSG 326xx, 327xx, 258xx, 269xx). The turn against true north is measured on the ground, so the grid
 * convergence of the projection is included.
 */
export function georefFromMapConversion(m: MapConversion, shift: readonly [number, number, number]): Georef | null {
  const p0 = projectToLatLon(m, shift[0], shift[1]);
  const pe = projectToLatLon(m, shift[0] + 100, shift[1]); // 100 model metres along project +X
  if (!p0 || !pe) return null;
  const [de, dn] = enuOf(pe[0], pe[1], p0[0], p0[1]);
  const len = Math.hypot(de, dn);
  if (!(len > 1e-6)) return null;
  // ENU = R(psi) * project, so project +X lies at angle psi counter-clockwise from east on the ground: psi = dirX. rotation = -psi.
  const dirX = Math.atan2(dn, de) * R2D;
  return { lat: p0[0], lon: p0[1], rotation: normaliseDeg(-dirX), scale: len / 100, source: 'mapConversion' };
}

/**
 * The place of a model from IfcSite RefLatitude / RefLongitude and the TrueNorth of the context. The site's reference point is taken
 * as the IFC project origin (0, 0); the viewer origin lies (shift x, shift y) from it.
 */
export function georefFromSite(s: SiteGeo, shift: readonly [number, number, number]): Georef | null {
  if (!validLatLon(s.lat, s.lon)) return null;
  const rotation = finite(s.trueNorth) ? s.trueNorth : 0;
  const g = { rotation, scale: 1 };
  const [e, n] = viewerToEnu(g, shift[0], -shift[1]); // the project vector (shift x, shift y) from the reference point to the viewer origin
  const [lat, lon] = latLonOfEnu(e, n, s.lat, s.lon);
  return { lat, lon, rotation, scale: 1, source: 'site' };
}

export function georefFromManual(m: ManualLocation): Georef | null {
  if (!validLatLon(m.lat, m.lon)) return null;
  return { lat: m.lat, lon: m.lon, rotation: finite(m.rotation) ? normaliseDeg(m.rotation) : 0, scale: 1, source: 'manual' };
}

export interface LocationInput {
  mapConversion?: MapConversion;
  siteGeo?: SiteGeo;
  manual?: ManualLocation | null;
  shift: readonly [number, number, number];
}

/**
 * Where the model is, in this order: a location the person set by hand for this model; IfcMapConversion with a UTM CRS; IfcSite
 * RefLatitude and RefLongitude with TrueNorth; unknown. A CRS that is not supported is said so in `notes` and the next step is used.
 */
export function resolveGeoref(i: LocationInput): GeorefResult {
  const notes: string[] = [];
  const man = i.manual ? georefFromManual(i.manual) : null;
  if (man) return { georef: man, status: 'Manual', notes };
  const mc = i.mapConversion;
  if (mc) {
    const g = georefFromMapConversion(mc, i.shift);
    if (g) return { georef: g, status: `From IfcMapConversion (EPSG:${mc.crs.epsg})`, notes };
    const what = mc.crs.epsg ? `EPSG:${mc.crs.epsg}` : mc.crs.name ? `"${mc.crs.name}"` : 'an unnamed CRS';
    notes.push(`IfcMapConversion is in ${what}, which is not supported (only UTM: ${UTM_FAMILIES})`);
  }
  const sg = i.siteGeo ? georefFromSite(i.siteGeo, i.shift) : null;
  if (sg) return { georef: sg, status: 'From IfcSite', notes };
  return { georef: null, status: 'Unknown', notes };
}

/** A point that the person dragged: the location after the ground under the model moved by (dx, dz) in the viewer frame. */
export function moveGeoref(g: Georef, dx: number, dz: number): Georef {
  const [e, n] = viewerToEnu(g, dx, dz);
  const [lat, lon] = latLonOfEnu(-e, -n, g.lat, g.lon);
  return { ...g, lat, lon, source: 'manual' };
}

/** Parse "52.5200, 13.4050" (also with a semicolon, tab or spaces) into latitude and longitude, or null. */
export function parseLatLon(text: string): [number, number] | null {
  const parts = text.trim().split(/[\s,;]+/).filter(Boolean);
  if (parts.length !== 2) return null;
  const lat = Number(parts[0]), lon = Number(parts[1]);
  return validLatLon(lat, lon) ? [lat, lon] : null;
}

export { utmForward, utmInverse };
