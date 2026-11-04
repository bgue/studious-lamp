// relations.openings in the browser reader's build stage: bounds go through the same shift and Y-up rotation as elements.
import { describe, expect, it } from 'vitest';
import { buildModelData } from '../src/model/ifcImport';
import type { RawElement, RawModel } from '../src/model/ifcShared';
import { parseModel } from '../src/model/loader';

function box(lo: [number, number, number], hi: [number, number, number]): { positions: Float32Array; indices: Uint32Array } {
  const [x0, y0, z0] = lo, [x1, y1, z1] = hi;
  const v = [[x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0], [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]];
  const idx = [0, 2, 1, 0, 3, 2, 4, 5, 6, 4, 6, 7, 0, 1, 5, 0, 5, 4, 1, 2, 6, 1, 6, 5, 2, 3, 7, 2, 7, 6, 3, 0, 4, 3, 4, 7];
  return { positions: Float32Array.from(v.flat()), indices: Uint32Array.from(idx) };
}
const el = (expressId: number, cls: string, lo: [number, number, number], hi: [number, number, number]): RawElement => ({
  expressId, globalId: `g${expressId}`, ifcClass: cls, name: `e${expressId}`, storeyExpressId: null, materialName: '', color: null, ...box(lo, hi),
});
const raw = (extra: Partial<RawModel>): RawModel => ({
  fileName: 'a.ifc', schema: 'IFC4', elements: [], storeys: [], voids: [], fills: [], ports: [], systems: [], ...extra,
});

describe('opening bounds in the IFC build stage', () => {
  // slab 0..10 x 0..10 x 0..1 (IFC, Z up); overall centre (5, 5, 0.5) becomes the origin
  const slab = el(1, 'IfcSlab', [0, 0, 0], [10, 10, 1]);
  const model = raw({ elements: [slab], voids: [[1, 50]], openings: [{ expressId: 50, host: 1, bounds: [2, 3, -0.01, 3, 4, 1.01] }] });

  it('converts IFC world bounds to the glb frame (shift, then x, z, -y)', () => {
    const { sidecar } = buildModelData([model]);
    const o = sidecar.relations.openings!;
    expect(o).toHaveLength(1);
    expect(o[0]!.expressId).toBe(50);
    expect(o[0]!.host).toBe(0);
    // shifted: x 2-5..3-5 = -3..-2; y 3-5..4-5 = -2..-1; z -0.01-0.5..1.01-0.5 = -0.51..0.51
    // glb: [x0, z0, -y1, x1, z1, -y0] = [-3, -0.51, 1, -2, 0.51, 2]
    expect(o[0]!.bounds).toEqual([-3, -0.51, 1, -2, 0.51, 2]);
  });
  it('openings of an element that was not exported are dropped; the key is omitted when there are none', () => {
    const orphan = buildModelData([raw({ elements: [slab], openings: [{ expressId: 51, host: 999, bounds: [0, 0, 0, 1, 1, 1] }] })]);
    expect(orphan.sidecar.relations.openings).toBeUndefined();
    expect(buildModelData([raw({ elements: [slab] })]).sidecar.relations).not.toHaveProperty('openings');
  });
  it('survives the loader into model.relations.openings', async () => {
    const { glb, sidecar } = buildModelData([model]);
    const loaded = await parseModel(glb, sidecar);
    expect(loaded.model.relations.openings).toEqual(sidecar.relations.openings);
    const e = loaded.model.elements[0]!;
    // the opening lies inside the slab bounds
    const b = loaded.model.relations.openings![0]!.bounds;
    expect(b[0]).toBeGreaterThanOrEqual(e.bounds[0]);
    expect(b[3]).toBeLessThanOrEqual(e.bounds[3]);
  });
  it('the sidecar json of the checked-in models carries openings in the glb frame', async () => {
    const { readFileSync } = await import('node:fs');
    const { fileURLToPath } = await import('node:url');
    const side = JSON.parse(readFileSync(fileURLToPath(new URL('../public/models/fzk-haus.json', import.meta.url)), 'utf8')) as {
      elements: Array<{ id: number; bounds: number[] }>; relations: { openings: Array<{ host: number; bounds: number[] }> };
    };
    expect(side.relations.openings.length).toBe(17);
    for (const o of side.relations.openings) {
      const h = side.elements[o.host]!.bounds;
      // each opening overlaps its host
      for (let k = 0; k < 3; k++) {
        expect(o.bounds[k]!).toBeLessThanOrEqual(h[k + 3]! + 1e-3);
        expect(o.bounds[k + 3]!).toBeGreaterThanOrEqual(h[k]! - 1e-3);
      }
    }
  });
});
