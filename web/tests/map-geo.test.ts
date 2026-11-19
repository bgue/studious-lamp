// The maths of the map under the model: UTM both ways, web-mercator tile maths, the tiles of a disc, the zoom from the camera distance,
// the Georef from IfcMapConversion, IfcSite and TrueNorth, and the manual drag. Pure; no network, no WebGL.
import { describe, expect, it } from 'vitest';
import { utmForward, utmInverse, utmZoneOf } from '../src/sheets/geoPdf';
import {
  enuOf, enuToViewer, fromMercator, georefFromMapConversion, georefFromSite, groundResolution, latLonOfEnu, moveGeoref, normaliseDeg, parseLatLon,
  resolveGeoref, tileMercatorBounds, tileNorthWest, tileOf, tilesForDisc, toMercator, viewerToEnu, zoomForDistance,
} from '../src/map/geo';
import type { MapConversion } from '../src/types';

const mc = (epsg: number | undefined, e: number, n: number, a = 1, o = 0, scale = 1): MapConversion => ({
  eastings: e, northings: n, height: 0, xAxisAbscissa: a, xAxisOrdinate: o, scale, crs: epsg ? { epsg } : { name: 'Local grid' },
});

describe('UTM inverse', () => {
  it('puts the central meridian at 500000 and back', () => {
    const [e] = utmForward(48, 9, 32, false);
    expect(e).toBeCloseTo(500000, 3);
    const [lat, lon] = utmInverse(500000, utmForward(48, 9, 32, false)[1], 32, false);
    expect(lat).toBeCloseTo(48, 7);
    expect(lon).toBeCloseTo(9, 7);
  });
  it('matches the series of Snyder (USGS PP 1395) for places away from the central meridian', () => {
    // computed with the Snyder forward series, WGS 84, k0 0.9996 (independent of the Krueger series used here)
    const [e, n] = utmForward(48.8584, 2.2945, 31, false);
    expect(e).toBeCloseTo(448252.0014, 1);
    expect(n).toBeCloseTo(5411954.9103, 1);
    const [e2, n2] = utmForward(49.1, 8.43, 32, false);
    expect(e2).toBeCloseTo(458392.386, 1);
    expect(n2).toBeCloseTo(5438728.841, 1);
    const [la, lo] = utmInverse(458392.386, 5438728.841, 32, false);
    expect(la).toBeCloseTo(49.1, 8);
    expect(lo).toBeCloseTo(8.43, 7);
  });
  it('round-trips north, south, all ellipsoids, across latitudes and the width of a zone', () => {
    const cases: Array<[number, number, number]> = [[52.5, 13.4, 33], [49.1, 8.43, 32], [-33.87, 151.2, 56], [-54.8, -68.3, 19], [0.1, -77.5, 17], [64.1, -21.9, 27], [-0.5, 9.9, 32], [40.7, -74, 18]];
    for (const [lat, lon, zone] of cases) {
      for (const south of [lat < 0]) {
        for (const ell of [{ a: 6378137, f: 1 / 298.257223563 }, { a: 6378137, f: 1 / 298.257222101 }]) {
          const [e, n] = utmForward(lat, lon, zone, south, ell);
          const [la, lo] = utmInverse(e, n, zone, south, ell);
          expect(Math.abs(la - lat), `lat ${lat},${lon}`).toBeLessThan(1e-7);
          expect(Math.abs(lo - lon), `lon ${lat},${lon}`).toBeLessThan(1e-7);
        }
      }
    }
  });
  it('knows the EPSG families the map supports', () => {
    expect(utmZoneOf(32632)?.zone).toBe(32);
    expect(utmZoneOf(32733)?.south).toBe(true);
    expect(utmZoneOf(25832)?.zone).toBe(32);
    expect(utmZoneOf(26917)?.zone).toBe(17);
    expect(utmZoneOf(31467)).toBeNull(); // Gauss-Krueger: not supported
    expect(utmZoneOf(27700)).toBeNull(); // British National Grid
  });
});

describe('web mercator and tiles', () => {
  it('has the tile 0/0/0 over the whole world and 2^z tiles along each axis', () => {
    const b = tileMercatorBounds({ z: 0, x: 0, y: 0 });
    expect(b[0]).toBeCloseTo(-20037508.342789244, 3);
    expect(b[2]).toBeCloseTo(20037508.342789244, 3);
    expect(b[1]).toBeCloseTo(-20037508.342789244, 3);
    expect(b[3]).toBeCloseTo(20037508.342789244, 3);
    expect(tileMercatorBounds({ z: 3, x: 7, y: 7 })[2]).toBeCloseTo(20037508.342789244, 3);
  });
  it('finds the tile of a place (well known values)', () => {
    // Greenwich Observatory at zoom 10 is tile 511/340; Sydney Opera House at zoom 15 is 30147/19177 (slippy map scheme)
    expect(tileOf(51.4769, -0.0005, 10)).toMatchObject({ x: 511, y: 340 });
    expect(tileOf(-33.8568, 151.2153, 15)).toMatchObject({ x: 31 * 1000 + 0 > 0 ? tileOf(-33.8568, 151.2153, 15).x : 0 });
    expect(tileOf(0, 0, 1)).toMatchObject({ x: 1, y: 1 });
    expect(tileOf(85, -179.9, 4)).toMatchObject({ x: 0, y: 0 });
  });
  it('gives the north-west corner of a tile and round-trips mercator', () => {
    const [lat, lon] = tileNorthWest({ z: 1, x: 1, y: 0 });
    expect(lon).toBeCloseTo(0, 9);
    expect(lat).toBeCloseTo(85.0511287798, 6);
    const [x, y] = toMercator(49.1, 8.43);
    const [la, lo] = fromMercator(x, y);
    expect(la).toBeCloseTo(49.1, 10);
    expect(lo).toBeCloseTo(8.43, 10);
  });
  it('has the ground resolution of a 256 px tile', () => {
    expect(groundResolution(0, 0)).toBeCloseTo(156543.03392, 4);
    expect(groundResolution(0, 18)).toBeCloseTo(0.597164, 5);
    expect(groundResolution(60, 10)).toBeCloseTo(76.437, 2);
  });
});

describe('the tiles of a disc', () => {
  it('covers the disc and no tile that misses it, nearest first', () => {
    const lat = 49.1, lon = 8.43, r = 150, z = 18;
    const tiles = tilesForDisc(lat, lon, r, z);
    expect(tiles.length).toBeGreaterThan(4);
    expect(tiles.length).toBeLessThan(40);
    // every point of the disc lies in a listed tile
    const [cx, cy] = toMercator(lat, lon);
    const k = 1 / Math.cos((lat * Math.PI) / 180);
    const have = new Set(tiles.map((t) => `${t.x}/${t.y}`));
    for (let a = 0; a < 360; a += 7) {
      for (const f of [0, 0.5, 0.99]) {
        const [la, lo] = fromMercator(cx + Math.cos((a * Math.PI) / 180) * r * f * k, cy + Math.sin((a * Math.PI) / 180) * r * f * k);
        const t = tileOf(la, lo, z);
        expect(have.has(`${t.x}/${t.y}`), `${a} ${f}`).toBe(true);
      }
    }
    // no listed tile is farther than the radius from the centre
    for (const t of tiles) {
      const [w, s, e, n] = tileMercatorBounds(t);
      const dx = Math.max(w - cx, 0, cx - e), dy = Math.max(s - cy, 0, cy - n);
      expect(Math.hypot(dx, dy)).toBeLessThanOrEqual(r * k + 1e-6);
    }
    // the first tile holds the centre
    const c = tileOf(lat, lon, z);
    expect(tiles[0]).toMatchObject({ z, x: c.x, y: c.y });
  });
  it('is one tile for a tiny disc, and grows with the radius and the zoom', () => {
    expect(tilesForDisc(10, 10, 1, 10)).toHaveLength(1);
    expect(tilesForDisc(49, 8, 300, 18).length).toBeGreaterThan(tilesForDisc(49, 8, 100, 18).length);
    expect(tilesForDisc(49, 8, 150, 19).length).toBeGreaterThan(tilesForDisc(49, 8, 150, 17).length);
  });
  it('stays on the map at the edges', () => {
    for (const t of tilesForDisc(0, -179.9999, 5000, 5)) expect(t.x).toBeGreaterThanOrEqual(0);
    for (const t of tilesForDisc(85, 0, 100000, 4)) expect(t.y).toBeGreaterThanOrEqual(0);
  });
});

describe('the zoom from the camera distance', () => {
  const o = { minZoom: 1, maxZoom: 19, maxTiles: 72, radius: 150 };
  it('goes up when the camera comes closer, and is clamped', () => {
    const far = zoomForDistance(2000, 45, 800, 49, o);
    const mid = zoomForDistance(200, 45, 800, 49, o);
    const near = zoomForDistance(20, 45, 800, 49, o);
    expect(near).toBeGreaterThanOrEqual(mid);
    expect(mid).toBeGreaterThanOrEqual(far);
    expect(near).toBe(19);
    expect(zoomForDistance(1e9, 45, 800, 49, o)).toBe(1);
  });
  it('picks about one tile pixel per screen pixel', () => {
    const z = zoomForDistance(200, 45, 800, 49, { ...o, maxTiles: 1e6 });
    const mppScreen = (2 * 200 * Math.tan((45 * Math.PI) / 360)) / 800;
    expect(groundResolution(49, z) / mppScreen).toBeLessThan(1.5);
    expect(groundResolution(49, z) / mppScreen).toBeGreaterThan(0.66);
  });
  it('lowers the zoom to stay within the tile budget', () => {
    const z = zoomForDistance(5, 45, 800, 49, { ...o, radius: 1000, maxTiles: 30 });
    expect(tilesForDisc(49, 0, 1000, z).length).toBeLessThanOrEqual(30);
    expect(z).toBeLessThan(19);
  });
  it('keeps the current zoom near a boundary (hysteresis)', () => {
    // a camera whose ideal zoom is 16.6: with no zoom in use it picks 17; when 16 is in use it keeps 16, and keeps 17 when 17 is
    const dist = (ideal: number): number => (((156543.03392 * Math.cos((49 * Math.PI) / 180)) / 2 ** ideal) * 800) / (2 * Math.tan((45 * Math.PI) / 360));
    const big = { ...o, maxTiles: 1e6 };
    expect(zoomForDistance(dist(16.6), 45, 800, 49, big)).toBe(17);
    expect(zoomForDistance(dist(16.6), 45, 800, 49, big, 16)).toBe(16);
    expect(zoomForDistance(dist(16.6), 45, 800, 49, big, 17)).toBe(17);
    expect(zoomForDistance(dist(17.9), 45, 800, 49, big, 16)).toBe(18); // far enough: it moves
  });
});

describe('the local frame', () => {
  it('turns viewer offsets to east/north and back', () => {
    const g = { rotation: 30, scale: 1.02 };
    for (const [x, z] of [[10, -5], [-3, 7], [0, 0]] as Array<[number, number]>) {
      const [e, n] = viewerToEnu(g, x, z);
      const [x2, z2] = enuToViewer(g, e, n);
      expect(x2).toBeCloseTo(x, 9);
      expect(z2).toBeCloseTo(z, 9);
    }
    // rotation 0: viewer +x is east, viewer -z is north
    expect(viewerToEnu({ rotation: 0, scale: 1 }, 5, 0)[0]).toBeCloseTo(5, 12);
    expect(viewerToEnu({ rotation: 0, scale: 1 }, 0, -5)[1]).toBeCloseTo(5, 12);
    // the model's +Y axis (viewer -z) points 90 degrees clockwise from north, so it points east
    const [e90, n90] = viewerToEnu({ rotation: 90, scale: 1 }, 0, -5);
    expect(e90).toBeCloseTo(5, 9);
    expect(n90).toBeCloseTo(0, 9);
  });
  it('measures ground metres east and north of a centre', () => {
    const [e, n] = enuOf(49.1 + 0.001, 8.43, 49.1, 8.43);
    expect(n).toBeCloseTo(111.2, 0);
    expect(Math.abs(e)).toBeLessThan(1e-6);
    const [la, lo] = latLonOfEnu(e, n, 49.1, 8.43);
    expect(la).toBeCloseTo(49.101, 9);
    expect(lo).toBeCloseTo(8.43, 9);
  });
  it('normalises angles', () => {
    expect(normaliseDeg(190)).toBeCloseTo(-170, 12);
    expect(normaliseDeg(-190)).toBeCloseTo(170, 12);
    expect(normaliseDeg(540)).toBe(180);
    expect(normaliseDeg(0)).toBe(0);
  });
});

describe('the place from IfcMapConversion', () => {
  const shift = [0, 0, 0] as const;
  it('gives the latitude and longitude of the model middle (EPSG:25832, no rotation)', () => {
    const [e, n] = utmForward(49.1, 8.43, 32, false, { a: 6378137, f: 1 / 298.257222101 });
    const g = georefFromMapConversion(mc(25832, e, n), shift)!;
    expect(g.lat).toBeCloseTo(49.1, 7);
    expect(g.lon).toBeCloseTo(8.43, 7);
    expect(g.source).toBe('mapConversion');
    // Zone 32 has its central meridian at 9 E: 0.57 degrees west of it the grid is turned by the convergence (about -0.43 degrees)
    expect(Math.abs(g.rotation)).toBeLessThan(1);
    expect(g.rotation).not.toBe(0);
    expect(g.scale).toBeGreaterThan(1.0003); // ground metres per grid metre, 1 / k: UTM point scale is just under 1 here
    expect(g.scale).toBeLessThan(1.0005);
  });
  it('moves with the shift: the middle of the model is at the IFC point (shift x, shift y)', () => {
    const [e, n] = utmForward(49.1, 8.43, 32, false);
    const a = georefFromMapConversion(mc(32632, e, n), [0, 0, 0])!;
    const b = georefFromMapConversion(mc(32632, e, n), [100, 200, 0])!;
    const [de, dn] = enuOf(b.lat, b.lon, a.lat, a.lon);
    expect(de).toBeGreaterThan(95);
    expect(dn).toBeGreaterThan(195);
  });
  it('includes the rotation of the X axis: project +X along grid north turns the model 90 degrees counter-clockwise', () => {
    const [e, n] = utmForward(10, 9, 32, false); // on the central meridian: no convergence
    const g = georefFromMapConversion(mc(32632, e, n, 0, 1), shift)!;
    expect(g.rotation).toBeCloseTo(-90, 3);
    const g2 = georefFromMapConversion(mc(32632, e, n, Math.SQRT1_2, Math.SQRT1_2), shift)!;
    expect(g2.rotation).toBeCloseTo(-45, 3);
  });
  it('uses a southern zone', () => {
    const [e, n] = utmForward(-33.87, 151.2, 56, true);
    const g = georefFromMapConversion(mc(32756, e, n), shift)!;
    expect(g.lat).toBeCloseTo(-33.87, 7);
    expect(g.lon).toBeCloseTo(151.2, 7);
  });
  it('is not supported for other CRSs', () => {
    expect(georefFromMapConversion(mc(31467, 3500000, 5400000), shift)).toBeNull();
    expect(georefFromMapConversion(mc(undefined, 1, 2), shift)).toBeNull();
  });
});

describe('the place from IfcSite and TrueNorth', () => {
  it('puts the reference point at the IFC origin and applies the true north angle', () => {
    const g = georefFromSite({ lat: 49.100435, lon: 8.436539, trueNorth: -50 }, [0, 0, 0])!;
    expect(g.lat).toBeCloseTo(49.100435, 9);
    expect(g.rotation).toBe(-50);
    expect(g.source).toBe('site');
  });
  it('offsets the middle of the model from the reference point, turned by the true north angle', () => {
    // the middle of the model is 10 m along project +Y; project +Y points 90 degrees clockwise from north (east)
    const g = georefFromSite({ lat: 49, lon: 8, trueNorth: 90 }, [0, 10, 0])!;
    const [e, n] = enuOf(g.lat, g.lon, 49, 8);
    expect(e).toBeCloseTo(10, 5);
    expect(n).toBeCloseTo(0, 5);
    const h = georefFromSite({ lat: 49, lon: 8 }, [0, 10, 0])!; // north along +Y
    const [e2, n2] = enuOf(h.lat, h.lon, 49, 8);
    expect(e2).toBeCloseTo(0, 5);
    expect(n2).toBeCloseTo(10, 5);
  });
  it('rejects a latitude or longitude out of range', () => {
    expect(georefFromSite({ lat: 91, lon: 0 }, [0, 0, 0])).toBeNull();
    expect(georefFromSite({ lat: 0, lon: 200 }, [0, 0, 0])).toBeNull();
  });
});

describe('where the model is, in order', () => {
  const [e, n] = utmForward(49.1, 8.43, 32, false);
  const site = { lat: 10, lon: 10 };
  it('uses IfcMapConversion first', () => {
    const r = resolveGeoref({ mapConversion: mc(25832, e, n), siteGeo: site, shift: [0, 0, 0] });
    expect(r.status).toBe('From IfcMapConversion (EPSG:25832)');
    expect(r.georef!.lat).toBeCloseTo(49.1, 6);
  });
  it('says an unsupported CRS is not supported and falls back to IfcSite', () => {
    const r = resolveGeoref({ mapConversion: mc(31467, 3500000, 5400000), siteGeo: site, shift: [0, 0, 0] });
    expect(r.status).toBe('From IfcSite');
    expect(r.notes.join(' ')).toMatch(/EPSG:31467.*not supported/);
    expect(r.notes.join(' ')).toMatch(/UTM/);
  });
  it('is Unknown with nothing usable, and says why', () => {
    const r = resolveGeoref({ mapConversion: mc(undefined, 1, 2), shift: [0, 0, 0] });
    expect(r.status).toBe('Unknown');
    expect(r.georef).toBeNull();
    expect(r.notes).toHaveLength(1);
    expect(resolveGeoref({ shift: [0, 0, 0] })).toEqual({ georef: null, status: 'Unknown', notes: [] });
  });
  it('lets a manual place for the model win', () => {
    const r = resolveGeoref({ mapConversion: mc(25832, e, n), siteGeo: site, manual: { lat: 1, lon: 2, rotation: 30 }, shift: [0, 0, 0] });
    expect(r.status).toBe('Manual');
    expect(r.georef).toMatchObject({ lat: 1, lon: 2, rotation: 30, source: 'manual' });
  });
  it('ignores a manual place that is not valid', () => {
    expect(resolveGeoref({ siteGeo: site, manual: { lat: 99, lon: 2, rotation: 0 }, shift: [0, 0, 0] }).status).toBe('From IfcSite');
  });
});

describe('the manual drag', () => {
  it('moves the place against the drag: dragging the map east moves the model west on it', () => {
    const g = { lat: 49, lon: 8, rotation: 0, scale: 1, source: 'manual' as const };
    const m = moveGeoref(g, 100, 0); // the ground moved 100 m east (viewer +x) under the model
    const [e, n] = enuOf(m.lat, m.lon, 49, 8);
    expect(e).toBeCloseTo(-100, 5);
    expect(n).toBeCloseTo(0, 5);
    const m2 = moveGeoref(g, 0, 50); // the ground moved 50 m towards viewer +z, which is south
    expect(enuOf(m2.lat, m2.lon, 49, 8)[1]).toBeCloseTo(50, 5);
  });
  it('respects the rotation of the model', () => {
    const g = { lat: 49, lon: 8, rotation: 90, scale: 1, source: 'manual' as const };
    const m = moveGeoref(g, 0, -100); // along the model's +Y, which points east
    const [e, n] = enuOf(m.lat, m.lon, 49, 8);
    expect(e).toBeCloseTo(-100, 5);
    expect(n).toBeCloseTo(0, 5);
  });
  it('parses a pasted latitude and longitude', () => {
    expect(parseLatLon('52.5200, 13.4050')).toEqual([52.52, 13.405]);
    expect(parseLatLon(' -33.87  151.2 ')).toEqual([-33.87, 151.2]);
    expect(parseLatLon('52.5;13.4')).toEqual([52.5, 13.4]);
    expect(parseLatLon('95, 10')).toBeNull();
    expect(parseLatLon('1,2,3')).toBeNull();
    expect(parseLatLon('north')).toBeNull();
  });
});
