// The IFC reader gives IfcMapConversion (with its IfcProjectedCRS) in metres, and the storeys' GlobalIds. web-ifc runs here in node
// on a checked-in fixture with the IFC4 map entities added to its text (a real, small IFC; nothing synthetic about the reader).
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { beforeAll, describe, expect, it } from 'vitest';
import type { IfcAPI } from 'web-ifc';
import { createIfcApi, extractIfc } from '../src/model/ifcRaw';
import { buildModelData } from '../src/model/ifcImport';

const here = dirname(fileURLToPath(import.meta.url));
const wasm = resolve(here, '../node_modules/web-ifc/web-ifc-node.wasm');
let api: IfcAPI;
beforeAll(async () => { api = await createIfcApi({ url: wasm }); }, 60000);

function withMap(file: string, lines: string[]): Uint8Array {
  const text = readFileSync(resolve(here, 'fixtures/ifc', file), 'utf8');
  const i = text.lastIndexOf('ENDSEC;');
  return new TextEncoder().encode(text.slice(0, i) + lines.join('\n') + '\n' + text.slice(i));
}

describe('IfcMapConversion in the IFC reader', () => {
  it('reads a metre model: eastings, northings, rotation, scale and the EPSG code', async () => {
    const bytes = withMap('ports-ifc4.ifc', [
      '#9001=IFCSIUNIT(*,.LENGTHUNIT.,$,.METRE.);',
      "#9002=IFCPROJECTEDCRS('EPSG:25832',$,$,$,$,$,#9001);",
      '#9003=IFCMAPCONVERSION(#10,#9002,500000.,5400000.,12.5,0.8,0.6,1.);',
    ]);
    const raw = await extractIfc(api, bytes, 'a.ifc');
    expect(raw.mapConversion).toBeTruthy();
    const m = raw.mapConversion!;
    expect(m.eastings).toBe(500000);
    expect(m.northings).toBe(5400000);
    expect(m.height).toBe(12.5);
    expect(m.xAxisAbscissa).toBeCloseTo(0.8, 9);
    expect(m.xAxisOrdinate).toBeCloseTo(0.6, 9);
    expect(m.scale).toBe(1);
    expect(m.crs.epsg).toBe(25832);
    // The storeys carry their GlobalIds, and the model that is built from the file carries both.
    expect(raw.storeys.map((s) => s.globalId)).toEqual(expect.arrayContaining(['3Scp8nJDr5Hwp7hmL8Dm5y', '1gspy37PX27vQfr11xh2N1']));
    const built = buildModelData([raw]);
    expect(built.sidecar.mapConversion?.crs.epsg).toBe(25832);
    expect(built.sidecar.storeys.find((s) => s.name === 'Level 2')?.guid).toBe('1gspy37PX27vQfr11xh2N1');
  });

  it('puts a millimetre model and a metre CRS in metres', async () => {
    const bytes = withMap('props-mm-ifc4.ifc', [
      '#9001=IFCSIUNIT(*,.LENGTHUNIT.,$,.METRE.);',
      "#9002=IFCPROJECTEDCRS('EPSG:31467',$,$,$,$,$,#9001);",
      '#9003=IFCMAPCONVERSION(#10,#9002,3500000.,5400000.,0.,1.,0.,0.001);',
    ]);
    const text = new TextDecoder().decode(bytes);
    // The context entity of that fixture is not #10: point the conversion at whichever context there is.
    const ctx = /#(\d+)=IFCGEOMETRICREPRESENTATIONCONTEXT/.exec(text)?.[1];
    const fixed = new TextEncoder().encode(text.replace('IFCMAPCONVERSION(#10,', `IFCMAPCONVERSION(#${ctx},`));
    const raw = await extractIfc(api, fixed, 'b.ifc');
    expect(/LENGTHUNIT.,.MILLI.,.METRE/.test(text)).toBe(true);
    expect(raw.mapConversion!.scale).toBeCloseTo(1, 9); // 0.001 map metres per millimetre of model = 1 m per m
    expect(raw.mapConversion!.eastings).toBe(3500000);
    expect(raw.mapConversion!.crs.epsg).toBe(31467);
  });

  it('a file without the entities has none', async () => {
    const raw = await extractIfc(api, new Uint8Array(readFileSync(resolve(here, 'fixtures/ifc/ports-ifc4.ifc'))), 'c.ifc');
    expect(raw.mapConversion).toBeUndefined();
  });
});
