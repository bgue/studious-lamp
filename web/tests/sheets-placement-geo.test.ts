// @vitest-environment node
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import * as PdfLib from 'pdf-lib';
import { epsgOf, groundFit, readGeoPage, utmForward, utmZoneOf } from '../src/sheets/geoPdf';
import type { PlainDict } from '../src/sheets/geoPdf';
import { geoPlacement, groundToModel, mapConversionFrom, sameCrs } from '../src/sheets/mapConversion';
import { applySim } from '../src/sheets/placement';
import { readGeoPages } from '../src/sheets/pdfRead';

const geoPdf = new Uint8Array(readFileSync(fileURLToPath(new URL('../bench/fixtures/geo-sheet.pdf', import.meta.url))));
const samplePdf = new Uint8Array(readFileSync(fileURLToPath(new URL('../bench/fixtures/sample-sheet.pdf', import.meta.url))));
const MPP = (25.4 / 72 / 1000) * 100;
const BOX: [number, number, number, number] = [0, 0, 842, 595];

// The model that goes with bench/fixtures/geo-sheet.pdf: project origin at E 500000, N 5400000 in EPSG:25832, north up. No IFC
// file is built here (web-ifc and a hand-made IFC are heavy): the numbers of an IfcMapConversion and IfcProjectedCRS are given as
// the reader hands them over. tests/ifc-map-conversion.test.ts reads them from an IFC text through web-ifc.
const MAP = mapConversionFrom({ Eastings: 500000, Northings: 5400000, OrthogonalHeight: 12, XAxisAbscissa: 1, XAxisOrdinate: 0, Scale: 1 }, { Name: 'EPSG:25832' }, { mapUnit: 1, lengthUnit: 1 })!;

describe('reading the geo-PDF', () => {
  it('finds the ISO 32000 viewport of the fixture page with pdf-lib', async () => {
    const pages = await readGeoPages(PdfLib, geoPdf);
    expect(pages).toHaveLength(1);
    const r = readGeoPage(pages[0]!, BOX);
    expect(r.info).toBeTruthy();
    expect(r.info!.kind).toBe('iso');
    expect(r.info!.crs).toMatchObject({ epsg: 25832, projected: true });
    expect(r.info!.degrees).toBe(false);
    expect(r.info!.pairs).toHaveLength(4);
    expect(r.info!.pairs[0]!.sheet).toEqual([0, 0]);
    expect(r.info!.pairs[0]!.model).toEqual([500100, 5400010]);
    expect(r.info!.summary).toContain('EPSG:25832');
  });

  it('a PDF without geo entries has none', async () => {
    const pages = await readGeoPages(PdfLib, samplePdf);
    expect(pages.every((p) => p === null)).toBe(true);
    expect(readGeoPage(pages[0], BOX)).toEqual({});
  });

  it('reads EPSG from a number, a name and a WKT', () => {
    expect(epsgOf(25832)).toBe(25832);
    expect(epsgOf('EPSG:25832')).toBe(25832);
    expect(epsgOf(undefined, 'PROJCS["x",GEOGCS["y",AUTHORITY["EPSG","4258"]],AUTHORITY["EPSG","25832"]]')).toBe(25832);
    expect(epsgOf('nonsense')).toBeUndefined();
  });

  it('reads a viewport with its own BBox, and ignores viewports that are not GEO', () => {
    const page: PlainDict = {
      VP: [
        { Type: 'Viewport', BBox: [0, 0, 10, 10], Measure: { Subtype: 'RL' } },
        { Type: 'Viewport', BBox: [100, 50, 500, 450], Measure: { Subtype: 'GEO', GPTS: [10, 20, 10, 60, 50, 60, 50, 20].map((v) => v * 1000), LPTS: [0, 0, 1, 0, 1, 1, 0, 1], GCS: { Type: 'PROJCS', EPSG: 25832 } } },
      ],
    };
    const r = readGeoPage(page, BOX);
    expect(r.info!.pairs.map((p) => p.sheet)).toEqual([[100, 50], [500, 50], [500, 450], [100, 450]]);
  });

  it('reads the OGC LGIDict best effort (UTM on WGS 84 names its EPSG code)', () => {
    const page: PlainDict = { LGIDict: { Type: 'LGIDict', Version: '2.1', CTM: [MPP, 0, 0, MPP, 500100, 5400010], Projection: { ProjectionType: 'UT', Zone: 32, Hemisphere: 'N', Datum: 'WGE' } } };
    const r = readGeoPage(page, BOX);
    expect(r.info!.kind).toBe('lgi');
    expect(r.info!.crs.epsg).toBe(32632);
    const g = groundFit(r.info!);
    expect(g.ok).toBe(true);
    expect(g.transform!.scale).toBeCloseTo(MPP, 9);
  });
});

describe('the sheet to ground fit', () => {
  it('is a similarity with the scale of 1:100 and no rotation', async () => {
    const info = readGeoPage((await readGeoPages(PdfLib, geoPdf))[0]!, BOX).info!;
    const g = groundFit(info);
    expect(g.ok).toBe(true);
    expect(g.transform!.scale).toBeCloseTo(MPP, 6); // the fixture's GPTS are rounded to a millimetre
    expect(g.transform!.rotation).toBeCloseTo(0, 5);
    const q = applySim(g.transform!, [842, 595]);
    expect(q[0]).toBeCloseTo(500100 + 842 * MPP, 2);
    expect(q[1]).toBeCloseTo(5400010 + 595 * MPP, 2);
  });

  it('refuses a skewed geo-referencing instead of guessing', () => {
    const page: PlainDict = { VP: [{ BBox: BOX, Measure: { Subtype: 'GEO', GPTS: [0, 0, 1000, 0, 1000, 100, 0, 700], LPTS: [0, 0, 1, 0, 1, 1, 0, 1], GCS: { Type: 'PROJCS', EPSG: 25832 } } }] };
    const g = groundFit(readGeoPage(page, BOX).info!);
    expect(g.ok).toBe(false);
    expect(g.reason).toMatch(/skewed/);
  });
});

describe('UTM', () => {
  it('knows the EPSG families', () => {
    expect(utmZoneOf(25832)).toMatchObject({ zone: 32, south: false });
    expect(utmZoneOf(32732)).toMatchObject({ zone: 32, south: true });
    expect(utmZoneOf(31467)).toBeNull();
    expect(utmZoneOf(4326)).toBeNull();
  });
  it('projects the central meridian to the false easting and 50 degrees to its meridian arc', () => {
    const [e, n] = utmForward(50, 9, 32, false);
    expect(e).toBeCloseTo(500000, 3);
    expect(n).toBeCloseTo(5538630.7, 0);
    const [e2, n2] = utmForward(0, 9, 32, false);
    expect([e2, n2].map((v) => Math.round(v))).toEqual([500000, 0]);
    expect(utmForward(-10, 9, 32, true)[1]).toBeGreaterThan(8_800_000);
  });
  it('a lat/long PDF in a UTM CRS is projected, then placed', () => {
    // The four corners of a 100 m square, as latitude and longitude, from the projection itself (inverse is not needed: use the forward map's own points).
    const probe = (e: number, n: number): [number, number] => {
      // invert by Newton steps from the central meridian (test helper only)
      let lat = 48.8, lon = 9.1;
      for (let i = 0; i < 40; i++) {
        const p = utmForward(lat, lon, 32, false);
        const q = utmForward(lat + 1e-5, lon, 32, false);
        const r = utmForward(lat, lon + 1e-5, 32, false);
        const a = (q[0] - p[0]) / 1e-5, b = (r[0] - p[0]) / 1e-5, c = (q[1] - p[1]) / 1e-5, d = (r[1] - p[1]) / 1e-5;
        const de = e - p[0], dn = n - p[1];
        const det = a * d - b * c;
        lat += (de * d - b * dn) / det;
        lon += (a * dn - c * de) / det;
      }
      return [lat, lon];
    };
    const c = [[500000, 5400000], [500000 + 842 * MPP, 5400000], [500000 + 842 * MPP, 5400000 + 595 * MPP], [500000, 5400000 + 595 * MPP]].map(([e, n]) => probe(e!, n!));
    const page: PlainDict = { VP: [{ BBox: BOX, Measure: { Subtype: 'GEO', GPTS: c.flat(), LPTS: [0, 0, 1, 0, 1, 1, 0, 1], GCS: { Type: 'PROJCS', EPSG: 25832 } } }] };
    const info = readGeoPage(page, BOX).info!;
    expect(info.degrees).toBe(true);
    const r = geoPlacement(info, MAP);
    expect(r.ok).toBe(true);
    const o = applySim(r.transform!, [0, 0]);
    expect(o[0]).toBeCloseTo(0, 1);
    expect(o[1]).toBeCloseTo(0, 1);
  });
  it('lat/long in a geographic CRS is not guessed: it needs a projection', () => {
    const page: PlainDict = { VP: [{ BBox: BOX, Measure: { Subtype: 'GEO', GPTS: [48, 9, 48, 9.01, 48.01, 9.01, 48.01, 9], LPTS: [0, 0, 1, 0, 1, 1, 0, 1], GCS: { Type: 'GEOGCS', EPSG: 4326 } } }] };
    const r = geoPlacement(readGeoPage(page, BOX).info!, MAP);
    expect(r.ok).toBe(false);
    expect(r.reason).toMatch(/latitude and longitude/);
    expect(r.detected).toContain('EPSG:4326');
  });
});

describe('IfcMapConversion', () => {
  it('keeps the numbers in metres, unit scales applied', () => {
    const m = mapConversionFrom({ Eastings: 500000000, Northings: 5400000000, OrthogonalHeight: 12000, XAxisAbscissa: 0, XAxisOrdinate: 2, Scale: 1 }, { Name: 'EPSG:25832' }, { mapUnit: 0.001, lengthUnit: 0.001 })!;
    expect(m.eastings).toBe(500000);
    expect(m.northings).toBe(5400000);
    expect(m.height).toBe(12);
    expect(m.xAxisAbscissa).toBe(0);
    expect(m.xAxisOrdinate).toBe(1); // normalised
    expect(m.scale).toBe(1); // mm map and mm model
    expect(m.crs.epsg).toBe(25832);
  });
  it('is not usable without eastings and northings', () => {
    expect(mapConversionFrom({ Northings: 1 }, null, { mapUnit: 1, lengthUnit: 1 })).toBeNull();
    expect(mapConversionFrom({ Eastings: 1, Northings: 1, XAxisAbscissa: 0, XAxisOrdinate: 0 }, null, { mapUnit: 1, lengthUnit: 1 })).toBeNull();
  });
  it('ground to model is the inverse of the conversion', () => {
    const m = mapConversionFrom({ Eastings: 1000, Northings: 2000, XAxisAbscissa: Math.cos(0.5), XAxisOrdinate: Math.sin(0.5), Scale: 0.999 }, { Name: 'EPSG:25832' }, { mapUnit: 1, lengthUnit: 1 })!;
    const local: [number, number] = [37.5, -12.25];
    // forward: E + iN = (E0 + iN0) + S r (x + iy)
    const c = Math.cos(0.5), s = Math.sin(0.5);
    const e = 1000 + 0.999 * (c * local[0] - s * local[1]);
    const n = 2000 + 0.999 * (s * local[0] + c * local[1]);
    const back = applySim(groundToModel(m), [e, n]);
    expect(back[0]).toBeCloseTo(local[0], 9);
    expect(back[1]).toBeCloseTo(local[1], 9);
  });
});

describe('the chain: PDF to CRS to model', () => {
  it('places the fixture page where the model says', async () => {
    const info = readGeoPage((await readGeoPages(PdfLib, geoPdf))[0]!, BOX).info!;
    const r = geoPlacement(info, MAP);
    expect(r.ok).toBe(true);
    expect(r.source).toBe('geo-PDF EPSG:25832');
    // Sheet (0, 0) is E 500100, N 5400010: model (100, 10). 1 point is 35.28 mm on the ground.
    const o = applySim(r.transform!, [0, 0]);
    expect(o[0]).toBeCloseTo(100, 2);
    expect(o[1]).toBeCloseTo(10, 2);
    expect(r.transform!.scale).toBeCloseTo(MPP, 6);
    const q = applySim(r.transform!, [100, 0]);
    expect(q[0]).toBeCloseTo(100 + 100 * MPP, 2);
  });

  it('follows a rotated and scaled model conversion', async () => {
    const rot = mapConversionFrom({ Eastings: 500050, Northings: 5400000, XAxisAbscissa: Math.cos(0.3), XAxisOrdinate: Math.sin(0.3), Scale: 1 }, { Name: 'EPSG:25832' }, { mapUnit: 1, lengthUnit: 1 })!;
    const info = readGeoPage((await readGeoPages(PdfLib, geoPdf))[0]!, BOX).info!;
    const r = geoPlacement(info, rot);
    expect(r.ok).toBe(true);
    // The sheet runs north up; the model's x axis points 0.3 rad east of north... of east: the sheet is turned by -0.3 in the model.
    expect(r.transform!.rotation).toBeCloseTo(-0.3, 5);
    // And a point maps back to the same ground point through the conversion.
    const sheetPt: [number, number] = [400, 300];
    const loc = applySim(r.transform!, sheetPt);
    const c = Math.cos(0.3), s = Math.sin(0.3);
    expect(500050 + (c * loc[0] - s * loc[1])).toBeCloseTo(500100 + sheetPt[0] * MPP, 2);
    expect(5400000 + (s * loc[0] + c * loc[1])).toBeCloseTo(5400010 + sheetPt[1] * MPP, 2);
  });

  it('refuses when the CRS differ, and says what it found', async () => {
    const other = mapConversionFrom({ Eastings: 3500000, Northings: 5400000 }, { Name: 'EPSG:31467' }, { mapUnit: 1, lengthUnit: 1 })!;
    const info = readGeoPage((await readGeoPages(PdfLib, geoPdf))[0]!, BOX).info!;
    const r = geoPlacement(info, other);
    expect(r.ok).toBe(false);
    expect(r.transform).toBeUndefined();
    expect(r.reason).toContain('EPSG:25832');
    expect(r.reason).toContain('EPSG:31467');
    expect(r.detected).toContain('ISO 32000');
  });

  it('refuses when the model has no map conversion, or no CRS name on one side', async () => {
    const info = readGeoPage((await readGeoPages(PdfLib, geoPdf))[0]!, BOX).info!;
    expect(geoPlacement(info, null).ok).toBe(false);
    const unnamed = mapConversionFrom({ Eastings: 1, Northings: 1 }, null, { mapUnit: 1, lengthUnit: 1 })!;
    const r = geoPlacement({ ...info, crs: { projected: true } }, unnamed);
    expect(r.ok).toBe(false);
    expect(sameCrs({ projected: true, name: 'A b' }, { name: 'a_b' })).toBe(true);
    expect(sameCrs({ projected: true }, {})).toBeNull();
  });
});
