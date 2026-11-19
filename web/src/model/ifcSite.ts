// IfcSite RefLatitude / RefLongitude / RefElevation and the TrueNorth of the geometric representation context: the numbers, as
// decimal degrees and metres. Pure (no web-ifc, no three.js), so tests need no WASM. Used by ifcRaw.ts; the map code (src/map/)
// turns it into a place on Earth. Docs: docs-features/map.md.
//
// IFC: a compound plane angle is a list of 3 or 4 integers (degrees, minutes, seconds, millionths of a second); all parts carry
// the sign of the angle. TrueNorth is a 2D direction in the coordinate system of the context (0, 1 means project +Y is north).

import type { SiteGeo } from '../types';

const finite = (n: unknown): n is number => typeof n === 'number' && Number.isFinite(n);

/** One entry of a list: a plain number or a web-ifc wrapped value `{ type, value }`. */
function numberOf(x: unknown): number | null {
  if (finite(x)) return x;
  if (x && typeof x === 'object') {
    const v = (x as { value?: unknown }).value;
    if (finite(v)) return v;
  }
  return null;
}

/**
 * IfcCompoundPlaneAngleMeasure to decimal degrees. Null when it is not a list of 3 or 4 numbers, when the parts are out of range
 * (minutes and seconds 0..59, millionths 0..999999) or when the parts disagree in sign.
 */
export function compoundAngleToDegrees(parts: unknown): number | null {
  if (!Array.isArray(parts) || parts.length < 3 || parts.length > 4) return null;
  const v = parts.map(numberOf);
  if (v.some((n) => n === null)) return null;
  const [d, m, s, u] = v as number[];
  const millionths = u ?? 0;
  const all = [d!, m!, s!, millionths];
  if (all.some((n) => !Number.isFinite(n))) return null;
  const neg = all.some((n) => n < 0);
  if (neg && all.some((n) => n > 0)) return null;
  const a = all.map(Math.abs) as [number, number, number, number];
  if (a[1] > 59 || a[2] > 59 || a[3] > 999999) return null;
  const deg = a[0] + a[1] / 60 + (a[2] + a[3] / 1e6) / 3600;
  return neg ? -deg : deg;
}

/**
 * Bearing of project +Y from true north is not stored; IFC stores the direction of true north in the project frame. This gives the
 * angle, in degrees, by which true north is turned from project +Y, counter-clockwise seen from above (the IFC y-axis is 90 degrees
 * from the x-axis). (0, 1) gives 0; (-1, 0), north along project -X, gives 90.
 */
export function trueNorthAngle(ratios: unknown): number | null {
  if (!Array.isArray(ratios) || ratios.length < 2) return null;
  const x = numberOf(ratios[0]), y = numberOf(ratios[1]);
  if (x === null || y === null || Math.hypot(x, y) < 1e-12) return null;
  const a = (Math.atan2(0 - x, y) * 180) / Math.PI;
  return Math.abs(a) < 1e-9 ? 0 : a;
}

/**
 * The site's reference point from the attributes of an IfcSite line (already plain values) and the TrueNorth ratios of the
 * context, or null when latitude or longitude is missing or out of range. `lengthUnit`: metres per project length unit, for
 * RefElevation.
 */
export function siteGeoFrom(
  site: { RefLatitude?: unknown; RefLongitude?: unknown; RefElevation?: unknown },
  trueNorthRatios: unknown,
  lengthUnit = 1,
): SiteGeo | null {
  const lat = compoundAngleToDegrees(site.RefLatitude);
  const lon = compoundAngleToDegrees(site.RefLongitude);
  if (lat === null || lon === null || Math.abs(lat) > 90 || Math.abs(lon) > 180) return null;
  const elevRaw = numberOf(site.RefElevation);
  const tn = trueNorthAngle(trueNorthRatios);
  const lu = lengthUnit > 0 ? lengthUnit : 1;
  return { lat, lon, ...(elevRaw !== null ? { elevation: elevRaw * lu } : {}), ...(tn !== null ? { trueNorth: tn } : {}) };
}

/** A sidecar's site geo-reference, or undefined when it is not usable. */
export function cleanSiteGeo(s: unknown): SiteGeo | undefined {
  const r = s as Partial<SiteGeo> | undefined;
  if (!r || typeof r !== 'object') return undefined;
  if (!finite(r.lat) || !finite(r.lon) || Math.abs(r.lat) > 90 || Math.abs(r.lon) > 180) return undefined;
  return { lat: r.lat, lon: r.lon, ...(finite(r.elevation) ? { elevation: r.elevation } : {}), ...(finite(r.trueNorth) ? { trueNorth: r.trueNorth } : {}) };
}
