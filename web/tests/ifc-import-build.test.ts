// The pure `build` stage of the IFC reader on synthetic RawModels: no web-ifc, no WASM.
// Conventions under test are those of tools/ifc2glb.py (see src/model/ifcImport.ts).
import { describe, expect, it } from 'vitest';
import { build, buildModelData, unzipIfc, writeGlb } from '../src/model/ifcImport';
import { classColor, isMarker, isSkippedClass, smoothMesh } from '../src/model/ifcShared';
import type { RawElement, RawModel, RawStorey } from '../src/model/ifcShared';
import { deflateRawSync } from 'node:zlib';

/** Axis-aligned box as an unindexed triangle soup (36 vertices), IFC frame. */
function boxSoup(lo: [number, number, number], hi: [number, number, number]): { positions: Float32Array; indices: Uint32Array } {
  const [x0, y0, z0] = lo;
  const [x1, y1, z1] = hi;
  const quads: Array<[number, number, number][]> = [
    [[x1, y0, z0], [x1, y1, z0], [x1, y1, z1], [x1, y0, z1]],
    [[x0, y1, z0], [x0, y0, z0], [x0, y0, z1], [x0, y1, z1]],
    [[x1, y1, z0], [x0, y1, z0], [x0, y1, z1], [x1, y1, z1]],
    [[x0, y0, z0], [x1, y0, z0], [x1, y0, z1], [x0, y0, z1]],
    [[x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]],
    [[x0, y1, z0], [x1, y1, z0], [x1, y0, z0], [x0, y0, z0]],
  ];
  const pos: number[] = [];
  for (const q of quads) for (const i of [0, 1, 2, 0, 2, 3]) pos.push(...q[i]!);
  return { positions: Float32Array.from(pos), indices: Uint32Array.from({ length: 36 }, (_, i) => i) };
}

let nextExpress = 100;
function el(over: Partial<RawElement> & { lo?: [number, number, number]; hi?: [number, number, number] } = {}): RawElement {
  const { lo = [0, 0, 0], hi = [1, 1, 1], ...rest } = over;
  const { positions, indices } = boxSoup(lo, hi);
  const id = nextExpress++;
  return {
    expressId: id, globalId: `gid-${id}`, ifcClass: 'IfcWall', name: `wall ${id}`, storeyExpressId: null, materialName: '',
    color: null, positions, indices, ...rest,
  };
}
const raw = (elements: RawElement[], extra: Partial<RawModel> = {}): RawModel => ({
  fileName: 'a.ifc', schema: 'IFC4', elements, storeys: [], voids: [], fills: [], ports: [], systems: [], ...extra,
});
const storey = (expressId: number, name: string, elevation: number): RawStorey => ({ expressId, name, elevation });

describe('classes and markers', () => {
  it('knows the converter skip list', () => {
    for (const c of ['IfcOpeningElement', 'IfcSpace', 'IfcSite', 'IfcBuilding', 'IfcBuildingStorey', 'IfcAnnotation', 'IfcSpatialZone',
      'IfcExternalSpatialElement', 'IfcGrid', 'IfcVirtualElement']) expect(isSkippedClass(c)).toBe(true);
    expect(isSkippedClass('IfcWall')).toBe(false);
    expect(isMarker('IfcBuildingElementProxy', ' Origin ')).toBe(true);
    expect(isMarker('IfcBuildingElementProxy', 'geo-reference')).toBe(true);
    expect(isMarker('IfcBuildingElementProxy', 'Proxy 1')).toBe(false);
    expect(isMarker('IfcWall', 'origin')).toBe(false);
  });

  it('drops skipped classes, marker proxies and empty meshes', () => {
    const keep = el({ ifcClass: 'IfcSlab' });
    const proxy = el({ ifcClass: 'IfcBuildingElementProxy', name: 'Box' });
    const data = buildModelData([raw([
      keep, proxy,
      el({ ifcClass: 'IfcOpeningElement' }), el({ ifcClass: 'IfcOpeningStandardCase' }), el({ ifcClass: 'IfcSpace' }),
      el({ ifcClass: 'IfcSite' }), el({ ifcClass: 'IfcBuilding' }), el({ ifcClass: 'IfcBuildingStorey' }),
      el({ ifcClass: 'IfcAnnotation' }), el({ ifcClass: 'IfcSpatialZone' }), el({ ifcClass: 'IfcExternalSpatialElement' }),
      el({ ifcClass: 'IfcGrid' }), el({ ifcClass: 'IfcVirtualElement' }),
      el({ ifcClass: 'IfcBuildingElementProxy', name: 'origin' }), el({ ifcClass: 'IfcBuildingElementProxy', name: 'geo-reference' }),
      el({ positions: new Float32Array(0), indices: new Uint32Array(0) }),
    ])]);
    expect(data.sidecar.elements.map((e) => e.ifcClass)).toEqual(['IfcSlab', 'IfcBuildingElementProxy']);
    expect(data.report.dropped).toBe(14);
  });

  it('throws when nothing is left', () => {
    expect(() => buildModelData([raw([el({ ifcClass: 'IfcSpace' })])])).toThrow(/no exportable geometry/);
  });
});

describe('Y-up conversion and origin shift', () => {
  it('shifts the bounds centre to the origin and rotates Z-up to Y-up', async () => {
    const a = el({ lo: [10, 20, 30], hi: [12, 24, 36] });
    const b = el({ lo: [14, 20, 30], hi: [16, 24, 36] });
    const data = buildModelData([raw([a, b])]);
    // IFC bounds x 10..16, y 20..24, z 30..36 -> centre (13, 22, 33)
    expect(data.sidecar.originShift).toEqual([13, 22, 33]);
    const e0 = data.sidecar.elements[0]!;
    // glb (x, y, z) = (x - cx, z - cz, -(y - cy)); element a: x -3..-1, y(up) -3..3, z(-y) -2..2
    expect(e0.bounds).toEqual([-3, -3, -2, -1, 3, 2]);
    const loaded = await build([raw([a, b])]);
    const gb = loaded.geometry.bounds[0]!;
    expect([gb.min.x, gb.min.y, gb.min.z, gb.max.x, gb.max.y, gb.max.z]).toEqual([-3, -3, -2, -1, 3, 2]);
    expect(loaded.model.originShift).toEqual([13, 22, 33]);
  });

  it('keeps a model with a far-away origin precise (RawModel.origin)', () => {
    const origin: [number, number, number] = [500000, 6000000, 100];
    const near = (lo: number[], hi: number[]) => boxSoup(lo as [number, number, number], hi as [number, number, number]);
    const p = near([0, 0, 0], [2, 2, 2]);
    const q = near([2, 0, 0], [4, 2, 2]);
    const data = buildModelData([raw([
      { ...el(), positions: p.positions, indices: p.indices },
      { ...el(), positions: q.positions, indices: q.indices },
    ], { origin })]);
    expect(data.sidecar.originShift).toEqual([500002, 6000001, 101]);
    expect(data.sidecar.elements[0]!.bounds).toEqual([-2, -1, -1, 0, 1, 1]);
  });

  it('produces unit normals that follow the rotation', async () => {
    const loaded = await build([raw([el({ lo: [0, 0, 0], hi: [1, 1, 1] })])]);
    const n = loaded.geometry.geometry.getAttribute('normal');
    const pos = loaded.geometry.geometry.getAttribute('position');
    // the top face of the box (IFC +Z) must now face +Y: vertices whose normal is +Y sit at the top (y = +0.5)
    let top = 0;
    for (let i = 0; i < pos.count; i++) {
      if (n.getY(i) > 0.99) {
        top++;
        expect(pos.getY(i)).toBeCloseTo(0.5, 6);
      }
      if (n.getY(i) < -0.99) expect(pos.getY(i)).toBeCloseTo(-0.5, 6);
      expect(Math.hypot(n.getX(i), n.getY(i), n.getZ(i))).toBeCloseTo(1, 5);
    }
    expect(top).toBeGreaterThanOrEqual(4);
  });
});

describe('smoothMesh (30 degree crease)', () => {
  it('keeps box edges hard: 24 vertices, 12 triangles, axis normals', () => {
    const { positions, indices } = boxSoup([0, 0, 0], [1, 1, 1]);
    const s = smoothMesh(positions, indices);
    expect(s.positions.length / 3).toBe(24);
    expect(s.indices.length / 3).toBe(12);
    for (let i = 0; i < s.normals.length; i += 3) {
      const abs = [Math.abs(s.normals[i]!), Math.abs(s.normals[i + 1]!), Math.abs(s.normals[i + 2]!)].sort();
      expect(abs[0]).toBeCloseTo(0, 5);
      expect(abs[1]).toBeCloseTo(0, 5);
      expect(abs[2]).toBeCloseTo(1, 5);
    }
  });

  it('smooths a curved surface and drops degenerate triangles', () => {
    // a 24-sided prism side: neighbouring faces differ by 15 degrees, so the side normals blend
    const n = 24;
    const pos: number[] = [];
    const idx: number[] = [];
    for (let i = 0; i < n; i++) {
      const a0 = (i / n) * Math.PI * 2;
      const a1 = ((i + 1) / n) * Math.PI * 2;
      const b = pos.length / 3;
      pos.push(Math.cos(a0), Math.sin(a0), 0, Math.cos(a1), Math.sin(a1), 0, Math.cos(a1), Math.sin(a1), 1, Math.cos(a0), Math.sin(a0), 1);
      idx.push(b, b + 1, b + 2, b, b + 2, b + 3);
    }
    idx.push(0, 0, 1); // degenerate
    const s = smoothMesh(pos, idx);
    expect(s.indices.length / 3).toBe(n * 2);
    expect(s.positions.length / 3).toBe(n * 2); // welded to a ring of 2 * 24 vertices, none split
    for (let i = 0; i < s.positions.length; i += 3) {
      // smoothed normal points radially outward
      const r = Math.hypot(s.positions[i]!, s.positions[i + 1]!);
      expect(s.normals[i]! * s.positions[i]! / r + s.normals[i + 1]! * s.positions[i + 1]! / r).toBeGreaterThan(0.99);
    }
    expect(smoothMesh([0, 0, 0, 1, 0, 0, 2, 0, 0], [0, 1, 2]).indices.length).toBe(0);
  });
});

describe('storeys', () => {
  const levels = [storey(1, 'Level 1', 0), storey(2, 'Level 2', 3)];

  it('uses containment when given, whatever the elevation says', () => {
    const a = el({ storeyExpressId: 2, lo: [0, 0, 0], hi: [1, 1, 1] });
    const data = buildModelData([raw([a], { storeys: levels })]);
    expect(data.sidecar.elements[0]!.storey).toBe(1);
    expect(data.report.storeyFallback).toBe(0);
  });

  it('falls back to the nearest storey at or below the lowest point, else the lowest storey', () => {
    const data = buildModelData([raw([
      el({ lo: [0, 0, 3.4], hi: [1, 1, 4] }), // above Level 2
      el({ lo: [0, 0, 1], hi: [1, 1, 2] }), // between: Level 1
      el({ lo: [0, 0, -2], hi: [1, 1, -1] }), // below all: lowest
      el({ lo: [0, 0, 3], hi: [1, 1, 4] }), // exactly at Level 2
    ], { storeys: levels })]);
    expect(data.sidecar.elements.map((e) => e.storey)).toEqual([1, 0, 0, 1]);
    expect(data.report.storeyFallback).toBe(4);
  });

  it('leaves storey null when the file has no storeys', () => {
    const data = buildModelData([raw([el()])]);
    expect(data.sidecar.elements[0]!.storey).toBeNull();
    expect(data.sidecar.storeys).toEqual([]);
  });

  it('sorts storeys by elevation and keeps ones without elements', () => {
    const data = buildModelData([raw([el({ storeyExpressId: 9 })], { storeys: [storey(9, 'Roof', 6), storey(1, 'Ground', 0), storey(2, 'Upper', 3)] })]);
    expect(data.sidecar.storeys.map((s) => [s.id, s.name, s.elevation])).toEqual([[0, 'Ground', 0], [1, 'Upper', 3], [2, 'Roof', 6]]);
    expect(data.sidecar.elements[0]!.storey).toBe(2);
  });
});

describe('federation', () => {
  it('numbers elements consecutively across files and keeps the file name', () => {
    const a = raw([el(), el()], { fileName: 'a.ifc' });
    const b = raw([el(), el({ ifcClass: 'IfcSlab' })], { fileName: 'b.ifc' });
    const d = buildModelData([a, b]);
    expect(d.sidecar.elements.map((e) => e.id)).toEqual([0, 1, 2, 3]);
    expect(d.sidecar.elements.map((e) => e.file)).toEqual(['a.ifc', 'a.ifc', 'b.ifc', 'b.ifc']);
    expect(d.sidecar.source.files).toEqual(['a.ifc', 'b.ifc']);
  });

  it('merges storeys by name and elevation within 1 cm', () => {
    const a = raw([el({ storeyExpressId: 1 })], { storeys: [storey(1, 'Level 2', 3.0), storey(2, 'Level 1', 0)] });
    const b = raw([el({ storeyExpressId: 5 }), el({ storeyExpressId: 6 }), el({ storeyExpressId: 7 })], {
      storeys: [storey(5, 'Level 2', 3.004), storey(6, 'Level 2', 3.5), storey(7, 'Other', 3.0)],
    });
    const d = buildModelData([a, b]);
    expect(d.sidecar.storeys.map((s) => [s.name, s.elevation])).toEqual([['Level 1', 0], ['Level 2', 3], ['Other', 3], ['Level 2', 3.5]]);
    expect(d.sidecar.elements.map((e) => e.storey)).toEqual([1, 1, 3, 2]);
  });

  it('skips same-GlobalId same-geometry duplicates and renames clashes with different geometry', () => {
    const shared = el({ globalId: 'G1', ifcClass: 'IfcWall', lo: [0, 0, 0], hi: [2, 2, 2] });
    const dup = el({ globalId: 'G1', ifcClass: 'IfcWall', lo: [0, 0, 0], hi: [2, 2, 2] });
    const clash = el({ globalId: 'G1', ifcClass: 'IfcWall', lo: [5, 5, 5], hi: [7, 7, 7] });
    const other = el({ globalId: 'G2' });
    const d = buildModelData([raw([shared], { fileName: 'a.ifc' }), raw([dup, clash, other], { fileName: 'b.ifc' })]);
    expect(d.report.duplicatesSkipped).toBe(1);
    expect(d.report.renamed).toBe(1);
    expect(d.sidecar.elements.map((e) => e.globalId)).toEqual(['G1', 'G1~1', 'G2']);
  });

  it('a duplicate of another class is a clash, not a duplicate', () => {
    const a = el({ globalId: 'G1', ifcClass: 'IfcWall' });
    const b = el({ globalId: 'G1', ifcClass: 'IfcSlab' });
    const d = buildModelData([raw([a]), raw([b])]);
    expect(d.report.duplicatesSkipped).toBe(0);
    expect(d.sidecar.elements.map((e) => e.globalId)).toEqual(['G1', 'G1~1']);
  });

  it('remaps relations per file and merges systems by name', () => {
    const w1 = el({ expressId: 10 }), d1 = el({ expressId: 20 }), s1 = el({ expressId: 30 });
    const w2 = el({ expressId: 10 }), s2 = el({ expressId: 31 });
    const a = raw([w1, d1, s1], { voids: [[10, 99]], fills: [[99, 20]], systems: [{ name: 'Air', elements: [30] }] });
    const b = raw([w2, s2], { fileName: 'b.ifc', systems: [{ name: 'Air', elements: [31, 10] }, { name: 'Water', elements: [31] }] });
    const d = buildModelData([a, b]);
    // eids: a: 10->0, 20->1, 30->2; b: 10->3, 31->4
    expect(d.sidecar.relations.voids).toEqual([[0, 99]]);
    expect(d.sidecar.relations.fills).toEqual([[99, 1]]);
    expect(d.sidecar.relations.hosts).toEqual([[1, 0]]);
    expect(d.sidecar.relations.systems).toEqual([{ name: 'Air', elements: [2, 4, 3] }, { name: 'Water', elements: [4] }]);
  });
});

describe('relations', () => {
  it('derives hosts from voids and fills (filler -> opening -> host)', () => {
    const wall = el({ expressId: 10 }), door = el({ expressId: 20, ifcClass: 'IfcDoor' }), win = el({ expressId: 21, ifcClass: 'IfcWindow' });
    const opening = el({ expressId: 90, ifcClass: 'IfcOpeningElement' });
    const d = buildModelData([raw([wall, door, win, opening], {
      voids: [[10, 90], [10, 91]], fills: [[90, 20], [91, 21], [92, 20]],
    })]);
    expect(d.sidecar.relations.voids).toEqual([[0, 90], [0, 91]]);
    expect(d.sidecar.relations.fills).toEqual([[90, 1], [91, 2], [92, 1]]);
    expect(d.sidecar.relations.hosts).toEqual([[1, 0], [2, 0]]); // door twice, host listed once; opening 92 has no host
    // the opening element itself is not exported
    expect(d.sidecar.elements.map((e) => e.ifcClass)).toEqual(['IfcWall', 'IfcDoor', 'IfcWindow']);
  });

  it('drops relations that point at elements that are not exported', () => {
    const wall = el({ expressId: 10 });
    const d = buildModelData([raw([wall], { voids: [[77, 90]], fills: [[90, 78]], ports: [[10, 77]] })]);
    expect(d.sidecar.relations).toEqual({ voids: [], fills: [], hosts: [], ports: [], systems: [] });
  });

  it('resolves ports to unordered, de-duplicated element pairs without self links', () => {
    const e1 = el({ expressId: 1 }), e2 = el({ expressId: 2 }), e3 = el({ expressId: 3 });
    const d = buildModelData([raw([e1, e2, e3], { ports: [[2, 1], [1, 2], [2, 3], [3, 3]] })]);
    expect(d.sidecar.relations.ports).toEqual([[0, 1], [1, 2]]);
  });
});

describe('colours, names and material', () => {
  it('uses the IFC style when present and the converter class colour otherwise', () => {
    const d = buildModelData([raw([
      el({ color: [0.1234567, 0.2, 0.3, 0.5], materialName: 'Concrete' }),
      el({ ifcClass: 'IfcDuctSegment' }), el({ ifcClass: 'IfcSlab' }), el({ ifcClass: 'IfcFurniture' }),
    ])]);
    expect(d.sidecar.elements[0]!.color).toEqual([0.1235, 0.2, 0.3, 0.5]);
    expect(d.sidecar.elements[0]!.material).toBe('Concrete');
    expect(d.sidecar.elements[1]!.color).toEqual([0.3, 0.6, 0.9, 1]);
    expect(d.sidecar.elements[2]!.color).toEqual([0.62, 0.62, 0.62, 1]);
    expect(d.sidecar.elements[3]!.color).toEqual(classColor('IfcFurniture'));
    expect(d.sidecar.elements[3]!.color).toEqual([0.7, 0.7, 0.7, 1]);
  });

  it('is sorted by express id inside each file, like the converter', () => {
    const d = buildModelData([raw([el({ expressId: 30 }), el({ expressId: 10 }), el({ expressId: 20 })])]);
    expect(d.sidecar.elements.map((e) => e.expressId)).toEqual([10, 20, 30]);
  });
});

describe('glb and loader round trip', () => {
  it('parseModel reads back what build wrote', async () => {
    const a = el({ ifcClass: 'IfcSlab', globalId: 'abc$1', name: 'Slab 1', storeyExpressId: 1, lo: [0, 0, 0], hi: [4, 3, 0.2] });
    const b = el({ ifcClass: 'IfcDuctSegment', globalId: 'def_2', lo: [1, 1, 0.5], hi: [3, 1.4, 0.9] });
    const loaded = await build([raw([a, b], { storeys: [storey(1, 'L1', 0)], systems: [{ name: 'S', elements: [a.expressId, b.expressId] }] })]);
    expect(loaded.model.elements.map((e) => e.ifcClass)).toEqual(['IfcSlab', 'IfcDuctSegment']);
    expect(loaded.model.byGlobalId.get('abc$1')).toBe(0);
    expect(loaded.model.byGlobalId.get('def_2')).toBe(1);
    expect(loaded.model.storeys.map((s) => s.name)).toEqual(['L1']);
    expect(loaded.model.relations.systems[0]).toEqual({ name: 'S', elements: [0, 1] });
    expect(loaded.geometry.ranges.map((r) => r.count)).toEqual([36, 36]);
    for (const e of loaded.model.elements) {
      const gb = loaded.geometry.bounds[e.id]!;
      expect(gb.min.x).toBeCloseTo(e.bounds[0], 4);
      expect(gb.max.z).toBeCloseTo(e.bounds[5], 4);
    }
  });

  it('writes a well-formed glb header and chunks', () => {
    const glb = writeGlb([{ name: 'n', id: 0, ifcClass: 'IfcWall', positions: new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0]), normals: new Float32Array([0, 0, 1, 0, 0, 1, 0, 0, 1]), indices: new Uint32Array([0, 1, 2]) }]);
    const dv = new DataView(glb);
    expect(dv.getUint32(0, true)).toBe(0x46546c67);
    expect(dv.getUint32(4, true)).toBe(2);
    expect(dv.getUint32(8, true)).toBe(glb.byteLength);
    const jsonLen = dv.getUint32(12, true);
    expect(jsonLen % 4).toBe(0);
    expect(dv.getUint32(16, true)).toBe(0x4e4f534a);
    const doc = JSON.parse(new TextDecoder().decode(new Uint8Array(glb, 20, jsonLen)));
    expect(doc.nodes[0].extras).toEqual({ id: 0, ifcClass: 'IfcWall' });
    expect(doc.accessors[0].min).toEqual([0, 0, 0]);
    expect(doc.accessors[0].max).toEqual([1, 1, 0]);
    expect(dv.getUint32(20 + jsonLen + 4, true)).toBe(0x004e4942);
  });
});

describe('.ifczip', () => {
  /** Smallest possible zip with one entry. */
  function zip(name: string, data: Uint8Array, method: 0 | 8): Uint8Array {
    const comp = method === 8 ? deflateRawSync(data) : data;
    const nm = new TextEncoder().encode(name);
    const local = new Uint8Array(30 + nm.length);
    const lv = new DataView(local.buffer);
    lv.setUint32(0, 0x04034b50, true); lv.setUint16(4, 20, true); lv.setUint16(8, method, true);
    lv.setUint32(18, comp.length, true); lv.setUint32(22, data.length, true); lv.setUint16(26, nm.length, true);
    local.set(nm, 30);
    const cen = new Uint8Array(46 + nm.length);
    const cv = new DataView(cen.buffer);
    cv.setUint32(0, 0x02014b50, true); cv.setUint16(4, 20, true); cv.setUint16(6, 20, true); cv.setUint16(10, method, true);
    cv.setUint32(20, comp.length, true); cv.setUint32(24, data.length, true); cv.setUint16(28, nm.length, true);
    cv.setUint32(42, 0, true);
    cen.set(nm, 46);
    const eocd = new Uint8Array(22);
    const ev = new DataView(eocd.buffer);
    ev.setUint32(0, 0x06054b50, true); ev.setUint16(8, 1, true); ev.setUint16(10, 1, true);
    ev.setUint32(12, cen.length, true); ev.setUint32(16, local.length + comp.length, true);
    const out = new Uint8Array(local.length + comp.length + cen.length + eocd.length);
    out.set(local, 0); out.set(comp, local.length); out.set(cen, local.length + comp.length); out.set(eocd, local.length + comp.length + cen.length);
    return out;
  }
  const payload = new TextEncoder().encode('ISO-10303-21;\nHEADER;\nENDSEC;\n'.repeat(20));

  it('reads a deflated entry', async () => {
    const r = await unzipIfc(zip('models/house.ifc', payload, 8));
    expect(r.name).toBe('models/house.ifc');
    expect(Array.from(r.bytes)).toEqual(Array.from(payload));
  });

  it('reads a stored entry', async () => {
    const r = await unzipIfc(zip('a.ifc', payload, 0));
    expect(Array.from(r.bytes)).toEqual(Array.from(payload));
  });

  it('rejects a zip without an .ifc and non-zip data', async () => {
    await expect(unzipIfc(zip('readme.txt', payload, 0))).rejects.toThrow(/no .ifc/);
    await expect(unzipIfc(new Uint8Array(100))).rejects.toThrow(/not a valid zip/);
  });
});
