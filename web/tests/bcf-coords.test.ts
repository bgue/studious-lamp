import { describe, expect, it } from 'vitest';
import { dirIfcToViewer, dirViewerToIfc, ifcToViewer, toIfcGuid, viewerToIfc } from '../src/bcf/model';
import type { Vec3 } from '../src/bcf/model';

const SHIFT: Vec3 = [6.0, 5.0, 3.058846]; // fzk-haus originShift

describe('BCF <-> viewer coordinates', () => {
  it('follows the converter mapping: subtract the shift in the IFC frame, then (x, y, z) -> (x, z, -y)', () => {
    // the shift itself is the viewer origin
    expect(ifcToViewer(SHIFT, SHIFT)).toEqual([0, 0, -0]);
    // +Z (up) in IFC is +Y in the viewer, +Y (north) is -Z, +X stays
    const o = ifcToViewer(SHIFT, SHIFT);
    const up = ifcToViewer([SHIFT[0], SHIFT[1], SHIFT[2] + 1], SHIFT);
    const north = ifcToViewer([SHIFT[0], SHIFT[1] + 1, SHIFT[2]], SHIFT);
    const east = ifcToViewer([SHIFT[0] + 1, SHIFT[1], SHIFT[2]], SHIFT);
    expect(up[1] - o[1]).toBeCloseTo(1, 12);
    expect(north[2] - o[2]).toBeCloseTo(-1, 12);
    expect(east[0] - o[0]).toBeCloseTo(1, 12);
    expect(dirIfcToViewer([0, 0, 1])).toEqual([0, 1, -0]);
    expect(dirIfcToViewer([0, 1, 0])).toEqual([0, 0, -1]);
  });

  it('matches a real fzk-haus element: IFC bounds -> sidecar viewer bounds', () => {
    // Wand-Int-ERDG-4 viewer bounds [1.41,-3.05885,0.75, 5.7,-0.55885,0.99] (from public/models/fzk-haus.json) back to IFC
    const lo = viewerToIfc([1.41, -3.05885, 0.75], SHIFT);
    const hi = viewerToIfc([5.7, -0.55885, 0.99], SHIFT);
    // z extent 2.5 m (BaseQuantities.Height), walls 0.24 m thick in IFC y
    expect(Math.abs(hi[2] - lo[2])).toBeCloseTo(2.5, 5);
    expect(lo[2]).toBeCloseTo(0, 5);
    expect(Math.abs(hi[0] - lo[0])).toBeCloseTo(4.29, 5);
    expect(Math.abs(hi[1] - lo[1])).toBeCloseTo(0.24, 5);
  });

  it('round trips points and directions', () => {
    let seed = 7;
    const rnd = (): number => ((seed = (seed * 16807) % 2147483647) / 2147483647 - 0.5) * 1000;
    for (let i = 0; i < 200; i++) {
      const p: Vec3 = [rnd(), rnd(), rnd()];
      const s: Vec3 = [rnd(), rnd(), rnd()];
      const back = viewerToIfc(ifcToViewer(p, s), s);
      for (let k = 0; k < 3; k++) expect(back[k]!).toBeCloseTo(p[k]!, 9);
      const v = ifcToViewer(viewerToIfc(p, s), s);
      for (let k = 0; k < 3; k++) expect(v[k]!).toBeCloseTo(p[k]!, 9);
      const d = dirViewerToIfc(dirIfcToViewer(p));
      for (let k = 0; k < 3; k++) expect(d[k]!).toBeCloseTo(p[k]!, 12);
    }
  });

  it('the mapping is a proper rotation (keeps handedness and lengths)', () => {
    const a = dirIfcToViewer([1, 0, 0]);
    const b = dirIfcToViewer([0, 1, 0]);
    const c = dirIfcToViewer([0, 0, 1]);
    const cross: Vec3 = [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
    for (let k = 0; k < 3; k++) expect(cross[k]! + 0).toBeCloseTo(c[k]!, 12);
  });

  it('toIfcGuid strips federation suffixes and rejects invalid ids', () => {
    expect(toIfcGuid('2XPyKWY018sA1ygZKgQPtU')).toBe('2XPyKWY018sA1ygZKgQPtU');
    expect(toIfcGuid('2XPyKWY018sA1ygZKgQPtU~2')).toBe('2XPyKWY018sA1ygZKgQPtU');
    expect(toIfcGuid('synthetic-12')).toBeNull();
    expect(toIfcGuid('')).toBeNull();
  });
});
