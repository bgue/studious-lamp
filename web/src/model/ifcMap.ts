// IfcMapConversion and IfcProjectedCRS read from an IFC file: the numbers, in metres. Pure (no web-ifc, no three.js), so the worker
// bundle stays small and tests need no WASM. Used by ifcRaw.ts; the sheets code (src/sheets/mapConversion.ts) turns it into the
// transform from a geo-referenced PDF to the model.
//
// IFC: E + iN = (E0 + iN0) + Scale * (XAxisAbscissa + i XAxisOrdinate) * (x + iy), x and y the project coordinates.

import type { MapConversion } from '../types';

const finite = (n: unknown): n is number => typeof n === 'number' && Number.isFinite(n);

/**
 * The numbers of an IfcMapConversion line (already plain numbers) and its CRS name, with the unit factors that turn Eastings,
 * Northings and OrthogonalHeight into metres (`mapUnit`: metres per map unit) and `scale` into metres on the map per metre in
 * the model (`lengthUnit`: metres per project length unit). Null when the conversion is not usable.
 */
export function mapConversionFrom(
  conv: { Eastings?: number | null; Northings?: number | null; OrthogonalHeight?: number | null; XAxisAbscissa?: number | null; XAxisOrdinate?: number | null; Scale?: number | null },
  crs: { Name?: string | null } | null,
  scales: { mapUnit: number; lengthUnit: number },
): MapConversion | null {
  const e = conv.Eastings, n = conv.Northings;
  if (!finite(e) || !finite(n)) return null;
  const a = finite(conv.XAxisAbscissa) ? conv.XAxisAbscissa : 1;
  const o = finite(conv.XAxisOrdinate) ? conv.XAxisOrdinate : 0;
  const len = Math.hypot(a, o);
  if (!(len > 1e-9)) return null;
  const sc = finite(conv.Scale) && conv.Scale > 0 ? conv.Scale : 1;
  const mu = scales.mapUnit > 0 ? scales.mapUnit : 1;
  const lu = scales.lengthUnit > 0 ? scales.lengthUnit : 1;
  const name = crs?.Name ? String(crs.Name) : undefined;
  const epsgM = name ? /(?:EPSG[:\s]*|^)(\d{4,6})$/i.exec(name.trim()) : null;
  return {
    eastings: e * mu, northings: n * mu, height: (finite(conv.OrthogonalHeight) ? conv.OrthogonalHeight : 0) * mu,
    xAxisAbscissa: a / len, xAxisOrdinate: o / len, scale: (sc * mu) / lu,
    crs: { ...(epsgM ? { epsg: Number(epsgM[1]) } : {}), ...(name ? { name } : {}) },
  };
}
