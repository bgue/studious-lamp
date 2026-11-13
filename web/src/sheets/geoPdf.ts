// Geo-referencing of PDF pages: reads the geospatial dictionaries of a page and says which coordinate reference system and which
// ground points they give. Pure: the reader (pdfRead.ts) turns the page dictionary into plain data first, so there is no PDF
// library here. Tested in tests/sheets-placement-geo.test.ts. Docs: docs-features/sheets.md.
//
// Supported:
//   ISO 32000-2 (and Adobe's extension): page /VP array, a viewport with /Measure << /Subtype /GEO /GPTS /LPTS /GCS >>.
//     GPTS: pairs of ground points. LPTS: the same points on the sheet, 0..1 of the viewport /BBox (the page when it has none).
//     GCS: /PROJCS or /GEOGCS with /EPSG and/or /WKT. GPTS is latitude, longitude in degrees (ISO); a projected GCS whose GPTS are
//     not degrees (a producer that writes the projected coordinates, easting then northing) is read as projected.
//   OGC LGIDict (best effort): page /LGIDict with /CTM (a 6 number matrix, sheet to map) and /Projection (UTM with a WGS 84 datum
//     gives the EPSG code; other projections stay unnamed and are never matched).
// Degrees are projected to UTM for the EPSG families we know (WGS 84, ETRS89 and NAD83 UTM zones); any other projection of
// degrees is reported as "needs projection" and the sheet is placed by hand: nothing is guessed.

import { fitSimilarity } from './placement';
import type { PointPair, Similarity, Vec2 } from './placement';

/** A PDF value as plain data: names and strings are strings, numbers, arrays, dictionaries (depth and size capped by the reader). */
export type Plain = string | number | boolean | null | Plain[] | { [k: string]: Plain };
export type PlainDict = { [k: string]: Plain };

export interface GeoCrs {
  epsg?: number;
  name?: string;
  projected: boolean;
}

export interface GeoPdfInfo {
  kind: 'iso' | 'lgi';
  crs: GeoCrs;
  /** Sheet points (PDF user space) with their ground coordinates: easting, northing (projected) or longitude, latitude (degrees). */
  pairs: PointPair[];
  /** The ground coordinates are degrees, not metres. */
  degrees: boolean;
  /** Plain words for the panel: "ISO 32000 geospatial, EPSG:25832". */
  summary: string;
}

export interface GeoReadResult {
  info?: GeoPdfInfo;
  /** Why nothing usable was found, or what is missing (shown with the manual placement). */
  note?: string;
}

const isNum = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);
const isDict = (v: Plain | undefined): v is PlainDict => !!v && typeof v === 'object' && !Array.isArray(v);
const numArr = (v: Plain | undefined, even = false): number[] | null => {
  if (!Array.isArray(v) || !v.length || !v.every(isNum)) return null;
  return even && v.length % 2 ? null : (v as number[]);
};
const asList = (v: Plain | undefined): Plain[] => (Array.isArray(v) ? v : v === undefined || v === null ? [] : [v]);

/** An EPSG code from a number, "EPSG:25832", or the authority of a WKT (the last one is the CRS itself). */
export function epsgOf(v: Plain | undefined, wkt?: Plain): number | undefined {
  if (isNum(v) && v > 0 && v < 1_000_000) return Math.round(v);
  if (typeof v === 'string') {
    const m = /(?:EPSG[:\s]*|^)(\d{4,6})$/i.exec(v.trim());
    if (m) return Number(m[1]);
  }
  if (typeof wkt === 'string') {
    const all = [...wkt.matchAll(/(?:AUTHORITY|ID)\s*\[\s*"EPSG"\s*,\s*"?(\d{4,6})"?\s*\]/gi)];
    if (all.length) return Number(all[all.length - 1]![1]);
  }
  return undefined;
}

function nameOfWkt(wkt: Plain | undefined): string | undefined {
  if (typeof wkt !== 'string') return undefined;
  const m = /^\s*(?:PROJCS|PROJCRS|GEOGCS|GEOGCRS)\s*\[\s*"([^"]+)"/i.exec(wkt);
  return m?.[1];
}

// ---------------------------------------------------------------- UTM

const WGS84 = { a: 6378137, f: 1 / 298.257223563 };
const GRS80 = { a: 6378137, f: 1 / 298.257222101 };

/** The UTM zone of an EPSG code of a family we know, else null. */
export function utmZoneOf(epsg: number): { zone: number; south: boolean; ellipsoid: { a: number; f: number } } | null {
  if (epsg >= 32601 && epsg <= 32660) return { zone: epsg - 32600, south: false, ellipsoid: WGS84 };
  if (epsg >= 32701 && epsg <= 32760) return { zone: epsg - 32700, south: true, ellipsoid: WGS84 };
  if (epsg >= 25828 && epsg <= 25838) return { zone: epsg - 25800, south: false, ellipsoid: GRS80 }; // ETRS89 / UTM 28N-38N
  if (epsg >= 26901 && epsg <= 26923) return { zone: epsg - 26900, south: false, ellipsoid: GRS80 }; // NAD83 / UTM 1N-23N
  return null;
}

/** Transverse Mercator (UTM) forward projection, Krueger series: degrees to easting, northing in metres. */
export function utmForward(latDeg: number, lonDeg: number, zone: number, south: boolean, ell: { a: number; f: number } = WGS84): Vec2 {
  const k0 = 0.9996;
  const lon0 = ((zone - 1) * 6 - 180 + 3) * (Math.PI / 180);
  const lat = latDeg * (Math.PI / 180);
  const lon = lonDeg * (Math.PI / 180) - lon0;
  const n = ell.f / (2 - ell.f);
  const A = (ell.a / (1 + n)) * (1 + n * n / 4 + n ** 4 / 64);
  const a1 = n / 2 - (2 * n * n) / 3 + (5 * n ** 3) / 16;
  const a2 = (13 * n * n) / 48 - (3 * n ** 3) / 5;
  const a3 = (61 * n ** 3) / 240;
  const e = Math.sqrt(ell.f * (2 - ell.f));
  const t = Math.sinh(Math.atanh(Math.sin(lat)) - e * Math.atanh(e * Math.sin(lat)));
  const xi = Math.atan2(t, Math.cos(lon));
  const eta = Math.atanh(Math.sin(lon) / Math.sqrt(1 + t * t));
  const E = 500000 + k0 * A * (eta + a1 * Math.cos(2 * xi) * Math.sinh(2 * eta) + a2 * Math.cos(4 * xi) * Math.sinh(4 * eta) + a3 * Math.cos(6 * xi) * Math.sinh(6 * eta));
  const N = k0 * A * (xi + a1 * Math.sin(2 * xi) * Math.cosh(2 * eta) + a2 * Math.sin(4 * xi) * Math.cosh(4 * eta) + a3 * Math.sin(6 * xi) * Math.cosh(6 * eta));
  return [E, south ? N + 10_000_000 : N];
}

// ---------------------------------------------------------------- reading a page

/** The largest similarity misfit (metres, or degrees for lat/long) the geo transform may have before it is called skewed. */
export const GEO_FIT_TOLERANCE = 0.05;

function readIso(page: PlainDict, box: [number, number, number, number]): GeoReadResult | null {
  const vps = asList(page['VP']).filter(isDict);
  if (!vps.length) return null;
  let note: string | undefined;
  for (const vp of vps) {
    const m = vp['Measure'];
    if (!isDict(m) || m['Subtype'] !== 'GEO') continue;
    const gpts = numArr(m['GPTS'], true);
    const lpts = numArr(m['LPTS'], true);
    if (!gpts || !lpts || gpts.length !== lpts.length || gpts.length < 4) { note = 'The geospatial entry of the PDF has no usable GPTS and LPTS'; continue; }
    const gcs = isDict(m['GCS']) ? m['GCS'] : {};
    const wkt = gcs['WKT'];
    const epsg = epsgOf(gcs['EPSG'], wkt);
    const type = typeof gcs['Type'] === 'string' ? gcs['Type'] : '';
    const nm = nameOfWkt(wkt);
    const bb = numArr(vp['BBox']) && (vp['BBox'] as number[]).length === 4 ? (vp['BBox'] as number[]) : box;
    const bx0 = Math.min(bb[0]!, bb[2]!), bx1 = Math.max(bb[0]!, bb[2]!), by0 = Math.min(bb[1]!, bb[3]!), by1 = Math.max(bb[1]!, bb[3]!);
    const sheet: Vec2[] = [];
    const ground: Vec2[] = [];
    for (let i = 0; i < lpts.length; i += 2) {
      sheet.push([bx0 + lpts[i]! * (bx1 - bx0), by0 + lpts[i + 1]! * (by1 - by0)]);
      ground.push([gpts[i]!, gpts[i + 1]!]);
    }
    const degrees = ground.every((g) => Math.abs(g[0]) <= 90 && Math.abs(g[1]) <= 180);
    const projected = type === 'PROJCS' || (type !== 'GEOGCS' && !!epsg && (!degrees || utmZoneOf(epsg) !== null));
    const crs: GeoCrs = { projected, ...(epsg ? { epsg } : {}), ...(nm ? { name: nm } : {}) };
    // ISO order is latitude, longitude. A projected producer that wrote easting, northing is read as x, y.
    const pairs: PointPair[] = sheet.map((s, i) => ({ sheet: s, model: degrees ? [ground[i]![1], ground[i]![0]] : [ground[i]![0], ground[i]![1]] }));
    const label = epsg ? `EPSG:${epsg}` : nm ?? 'unnamed CRS';
    return { info: { kind: 'iso', crs, pairs, degrees, summary: `ISO 32000 geospatial, ${label}${degrees ? ', latitude and longitude' : ''}` } };
  }
  return note ? { note } : null;
}

const LGI_UT = /^UT$/i;

function readLgi(page: PlainDict): GeoReadResult | null {
  const l = asList(page['LGIDict']).filter(isDict);
  if (!l.length) return null;
  for (const d of l) {
    const ctm = numArr(d['CTM']);
    if (!ctm || ctm.length !== 6) continue;
    const proj = isDict(d['Projection']) ? d['Projection'] : {};
    const type = typeof proj['ProjectionType'] === 'string' ? proj['ProjectionType'] : '';
    const datum = typeof proj['Datum'] === 'string' ? proj['Datum'] : '';
    let epsg: number | undefined;
    if (LGI_UT.test(type) && /^(WGE|WGS|WGS84|WGS 84)$/i.test(datum) && isNum(proj['Zone'])) {
      const south = typeof proj['Hemisphere'] === 'string' && /^s/i.test(proj['Hemisphere']);
      epsg = (south ? 32700 : 32600) + Math.round(proj['Zone']);
    }
    // CTM: x' = a x + c y + e, y' = b x + d y + f (sheet user space to map). Three corner-ish points make the pairs.
    const [a, b, c, dd, e, f] = ctm as [number, number, number, number, number, number];
    const pts: Vec2[] = [[0, 0], [1000, 0], [0, 1000], [1000, 1000]];
    const pairs: PointPair[] = pts.map((p) => ({ sheet: p, model: [a * p[0] + c * p[1] + e, b * p[0] + dd * p[1] + f] as Vec2 }));
    const label = epsg ? `EPSG:${epsg}` : type ? `projection ${type}` : 'unnamed projection';
    return { info: { kind: 'lgi', crs: { projected: true, ...(epsg ? { epsg } : {}), ...(type && !epsg ? { name: `LGI ${type}` } : {}) }, pairs, degrees: false, summary: `OGC LGIDict, ${label}` } };
  }
  return { note: 'The LGIDict of the PDF has no usable CTM' };
}

/** The geo-referencing of a page from its plain dictionary. `box` is the visible box in user space. */
export function readGeoPage(page: PlainDict | null | undefined, box: [number, number, number, number]): GeoReadResult {
  if (!page) return {};
  const iso = readIso(page, box);
  if (iso?.info) return iso;
  const lgi = readLgi(page);
  if (lgi?.info) return lgi;
  return iso ?? lgi ?? {};
}

// ---------------------------------------------------------------- sheet to ground

export interface GroundFit {
  ok: boolean;
  /** Sheet user space to ground metres (easting, northing); set when ok. */
  transform?: Similarity;
  /** Largest misfit of the pairs, ground metres. */
  misfit?: number;
  /** When not ok: what is wrong, in words. */
  reason?: string;
  /** The CRS the transform is in (projected). */
  crs?: GeoCrs;
}

/** The similarity from the sheet to projected ground coordinates (degrees are projected first; unknown projections are refused). */
export function groundFit(info: GeoPdfInfo): GroundFit {
  let pairs = info.pairs;
  let crs = info.crs;
  if (info.degrees) {
    const utm = info.crs.epsg ? utmZoneOf(info.crs.epsg) : null;
    if (!utm) return { ok: false, reason: `The PDF is geo-referenced in latitude and longitude${info.crs.epsg ? ` (EPSG:${info.crs.epsg})` : ''} without a projection this viewer can apply`, crs: info.crs };
    pairs = pairs.map((p) => ({ sheet: p.sheet, model: utmForward(p.model[1], p.model[0], utm.zone, utm.south, utm.ellipsoid) }));
    crs = { ...info.crs, projected: true };
  } else if (!info.crs.projected) {
    return { ok: false, reason: 'The PDF gives ground coordinates without saying which projected coordinate system they are in', crs: info.crs };
  }
  const fit = fitSimilarity(pairs);
  if (!fit.ok) return { ok: false, reason: `The geo-referencing of the PDF cannot be used: ${fit.error}`, crs };
  const worst = Math.max(...fit.misfits);
  const tol = Math.max(GEO_FIT_TOLERANCE, fit.transform.scale * 1000 * 1e-4);
  if (worst > tol) return { ok: false, reason: `The geo-referencing of the PDF is skewed (misfit ${worst.toFixed(2)} m): it is not a plain scale and rotation`, misfit: worst, crs };
  return { ok: true, transform: fit.transform, misfit: worst, crs };
}
