// IfcSite RefLatitude / RefLongitude / RefElevation and TrueNorth: the pure parsing, and the reader on a real IFC (FZK-Haus) in node.
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { beforeAll, describe, expect, it } from 'vitest';
import type { IfcAPI } from 'web-ifc';
import { compoundAngleToDegrees, siteGeoFrom, trueNorthAngle, cleanSiteGeo } from '../src/model/ifcSite';
import { createIfcApi, extractIfc } from '../src/model/ifcRaw';
import { buildModelData } from '../src/model/ifcImport';

const here = dirname(fileURLToPath(import.meta.url));
const wasm = resolve(here, '../node_modules/web-ifc/web-ifc-node.wasm');

describe('compound plane angles', () => {
  it('converts degrees, minutes, seconds and millionths', () => {
    expect(compoundAngleToDegrees([49, 6, 1, 566000])).toBeCloseTo(49 + 6 / 60 + 1.566 / 3600, 10);
    expect(compoundAngleToDegrees([8, 26, 11, 540400])).toBeCloseTo(8 + 26 / 60 + 11.5404 / 3600, 10);
    expect(compoundAngleToDegrees([52, 30, 0])).toBeCloseTo(52.5, 12); // IFC2X3 allows 3 parts
    expect(compoundAngleToDegrees([0, 0, 0, 0])).toBe(0);
  });
  it('takes the sign from the parts (all parts carry it)', () => {
    expect(compoundAngleToDegrees([-33, -52, -4, -0])).toBeCloseTo(-(33 + 52 / 60 + 4 / 3600), 10);
    expect(compoundAngleToDegrees([0, -30, 0, 0])).toBeCloseTo(-0.5, 12);
    expect(compoundAngleToDegrees([-33, 52, 4, 0])).toBeNull(); // mixed signs
  });
  it('reads wrapped web-ifc values', () => {
    expect(compoundAngleToDegrees([{ type: 1, value: 10 }, { type: 1, value: 30 }, { type: 1, value: 0 }])).toBeCloseTo(10.5, 12);
  });
  it('refuses what is not an angle', () => {
    expect(compoundAngleToDegrees(null)).toBeNull();
    expect(compoundAngleToDegrees([1, 2])).toBeNull();
    expect(compoundAngleToDegrees([1, 2, 3, 4, 5])).toBeNull();
    expect(compoundAngleToDegrees([10, 60, 0, 0])).toBeNull();
    expect(compoundAngleToDegrees([10, 0, 60, 0])).toBeNull();
    expect(compoundAngleToDegrees([10, 0, 0, 1000000])).toBeNull();
    expect(compoundAngleToDegrees(['a', 1, 2])).toBeNull();
  });
});

describe('TrueNorth', () => {
  it('is 0 when project +Y is north', () => {
    expect(trueNorthAngle([0, 1])).toBe(0);
    expect(trueNorthAngle([0, 5])).toBe(0);
  });
  it('is the counter-clockwise angle from project +Y to true north', () => {
    expect(trueNorthAngle([-1, 0])).toBeCloseTo(90, 9); // north along project -X
    expect(trueNorthAngle([1, 0])).toBeCloseTo(-90, 9);
    expect(trueNorthAngle([0, -1])).toBeCloseTo(180, 9);
    expect(trueNorthAngle([-Math.sin(0.3), Math.cos(0.3)])).toBeCloseTo((0.3 * 180) / Math.PI, 9);
  });
  it('refuses a missing or zero direction', () => {
    expect(trueNorthAngle(null)).toBeNull();
    expect(trueNorthAngle([0, 0])).toBeNull();
    expect(trueNorthAngle([1])).toBeNull();
  });
});

describe('the site reference', () => {
  it('needs latitude and longitude, in range', () => {
    expect(siteGeoFrom({ RefLatitude: null, RefLongitude: [8, 0, 0] }, null)).toBeNull();
    expect(siteGeoFrom({ RefLatitude: [91, 0, 0], RefLongitude: [8, 0, 0] }, null)).toBeNull();
    expect(siteGeoFrom({ RefLatitude: [50, 0, 0], RefLongitude: [181, 0, 0] }, null)).toBeNull();
  });
  it('carries elevation in metres and the true north angle', () => {
    const g = siteGeoFrom({ RefLatitude: [49, 6, 1, 566000], RefLongitude: [8, 26, 11, 540400], RefElevation: 110000 }, [0, 1], 0.001)!;
    expect(g.lat).toBeCloseTo(49.100435, 5);
    expect(g.lon).toBeCloseTo(8.436539, 5);
    expect(g.elevation).toBeCloseTo(110, 9);
    expect(g.trueNorth).toBe(0);
    expect(siteGeoFrom({ RefLatitude: [1, 0, 0], RefLongitude: [2, 0, 0] }, null)).toEqual({ lat: 1, lon: 2 });
  });
  it('cleans a sidecar record', () => {
    expect(cleanSiteGeo({ lat: 10, lon: 20, elevation: 5, trueNorth: 3, extra: 1 })).toEqual({ lat: 10, lon: 20, elevation: 5, trueNorth: 3 });
    expect(cleanSiteGeo({ lat: 'x', lon: 20 })).toBeUndefined();
    expect(cleanSiteGeo(null)).toBeUndefined();
  });
});

describe('the IFC reader', () => {
  let api: IfcAPI;
  beforeAll(async () => { api = await createIfcApi({ url: wasm }); }, 60000);
  it('reads the IfcSite of FZK-Haus (RefLatitude 49 6 1.566, RefLongitude 8 26 11.5404, RefElevation 110)', async () => {
    const raw = await extractIfc(api, new Uint8Array(readFileSync(resolve(here, '../../models/AC20-FZK-Haus.ifc'))), 'fzk.ifc');
    expect(raw.siteGeo).toBeTruthy();
    expect(raw.siteGeo!.lat).toBeCloseTo(49.100435, 5);
    expect(raw.siteGeo!.lon).toBeCloseTo(8.436539, 5);
    expect(raw.siteGeo!.elevation).toBeCloseTo(110, 6);
    expect(raw.siteGeo!.trueNorth).toBeCloseTo(-50, 3); // TrueNorth (0.766, 0.643): the project is turned 50 degrees from north
    expect(raw.mapConversion).toBeUndefined();
    const built = buildModelData([raw]);
    expect(built.sidecar.siteGeo?.lat).toBeCloseTo(49.100435, 5);
  }, 60000);
});
