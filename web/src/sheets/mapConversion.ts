// IfcMapConversion and IfcProjectedCRS: how the model's project coordinates sit in a projected coordinate system, and the chain
// sheet -> ground (geoPdf.ts) -> model. Pure. Tested in tests/sheets-placement-geo.test.ts. Docs: docs-features/sheets.md.
//
// IFC: E + iN = (E0 + iN0) + Scale * (XAxisAbscissa + i XAxisOrdinate) * (x + iy), x, y the project coordinates. All numbers here are
// in metres: the reader (ifcRaw.ts) has already turned Eastings, Northings and OrthogonalHeight into metres through the map unit,
// and `scale` into the ratio of metres on the map to metres in the model (map unit scale over project length unit scale).

import type { MapConversion } from '../types';
import { mapConversionFrom } from '../model/ifcMap';
import type { GeoCrs, GeoPdfInfo } from './geoPdf';
import { groundFit } from './geoPdf';
import { composeSim } from './placement';
import type { Similarity } from './placement';

export type { MapConversion };
export { mapConversionFrom };

/** Ground (map) coordinates to the model's plan coordinates: the inverse of the conversion, as a similarity. */
export function groundToModel(m: MapConversion): Similarity {
  // w = m0 + S r z  =>  z = (w - m0) / (S r)
  const s = m.scale;
  const inv = 1 / s;
  const rot = -Math.atan2(m.xAxisOrdinate, m.xAxisAbscissa);
  const cr = inv * Math.cos(rot), ci = inv * Math.sin(rot);
  return { scale: inv, rotation: rot, tx: -(cr * m.eastings - ci * m.northings), ty: -(ci * m.eastings + cr * m.northings) };
}

/** The same CRS: both name an EPSG code and the codes are equal, or neither does and the names agree ignoring case and spaces. */
export function sameCrs(a: GeoCrs, b: { epsg?: number; name?: string }): boolean | null {
  if (a.epsg && b.epsg) return a.epsg === b.epsg;
  const na = (a.name ?? '').toLowerCase().replace(/[\s_]+/g, '');
  const nb = (b.name ?? '').toLowerCase().replace(/[\s_]+/g, '');
  if (na && nb) return na === nb;
  return null; // not enough to say
}

export interface GeoPlacementResult {
  ok: boolean;
  /** Sheet user space to model plan metres. */
  transform?: Similarity;
  /** "geo-PDF EPSG:25832" */
  source?: string;
  /** Largest misfit of the geo-referencing of the PDF, metres. */
  misfit?: number;
  /** When not ok: why the sheet is not placed by itself, and what was found (for the panel next to the manual placement). */
  reason?: string;
  detected?: string;
}

/**
 * sheet -> CRS -> model. Placed only when the PDF's CRS is projected, and the same as the model's IfcProjectedCRS. A different CRS,
 * a lat/long PDF without a projection we can apply, a model without a map conversion: not placed, with the reason.
 */
export function geoPlacement(info: GeoPdfInfo, map: MapConversion | null | undefined): GeoPlacementResult {
  const detected = info.summary;
  if (!map) return { ok: false, detected, reason: 'The PDF is geo-referenced but the model has no IfcMapConversion, so the ground coordinates have no place in it' };
  const g = groundFit(info);
  if (!g.ok || !g.transform) return { ok: false, detected, reason: g.reason ?? 'The geo-referencing of the PDF cannot be used' };
  const same = sameCrs(g.crs ?? info.crs, map.crs);
  if (same === false) {
    const a = g.crs?.epsg ? `EPSG:${g.crs.epsg}` : g.crs?.name ?? 'an unnamed CRS';
    const b = map.crs.epsg ? `EPSG:${map.crs.epsg}` : map.crs.name ?? 'an unnamed CRS';
    return { ok: false, detected, reason: `The PDF is in ${a} and the model in ${b}. Converting between them is not done here` };
  }
  if (same === null) return { ok: false, detected, reason: 'The PDF and the model do not name their coordinate system, so they cannot be matched' };
  const transform = composeSim(groundToModel(map), g.transform);
  const epsg = g.crs?.epsg ?? map.crs.epsg;
  return { ok: true, transform, source: `geo-PDF${epsg ? ` EPSG:${epsg}` : ''}`, detected, ...(g.misfit !== undefined ? { misfit: g.misfit } : {}) };
}
