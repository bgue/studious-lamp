// USDZ export for AR Quick Look (src/export/usdz.ts): bucketing by colour and x-ray alpha, the zip layout Quick Look needs
// (model.usda first, 64-byte aligned, stored), the usda contents (metres, Y up, plane anchoring, opacity per material).
import { describe, expect, it } from 'vitest';
import { unzipSync, strFromU8 } from 'three/examples/jsm/libs/fflate.module.js';
import { bucketElements, buildUsdzScene, exportUsdz } from '../src/export/usdz';
import type { UsdzSource } from '../src/export/usdz';
import { FLAG_HIDDEN } from '../src/types';

/** A unit cube of 8 vertices and 12 triangles at an offset. */
function cube(ox: number, oy: number, oz: number): { pos: number[]; idx: number[] } {
  const pos: number[] = [];
  for (let i = 0; i < 8; i++) pos.push(ox + (i & 1), oy + ((i >> 1) & 1), oz + ((i >> 2) & 1));
  const idx = [0, 2, 1, 1, 2, 3, 4, 5, 6, 5, 7, 6, 0, 1, 4, 1, 5, 4, 2, 6, 3, 3, 6, 7, 0, 4, 2, 2, 4, 6, 1, 3, 5, 3, 7, 5];
  return { pos, idx };
}

/** 4 elements: a solid red pipe, two ghosted grey walls (same bucket), a hidden slab. */
function source(): UsdzSource {
  const parts = [cube(0, 2, 0), cube(3, 0, 0), cube(5, 0, 1), cube(0, -1, 0)];
  const positions: number[] = [];
  const index: number[] = [];
  const ranges: Array<{ start: number; count: number }> = [];
  const vertexRanges: Array<{ start: number; count: number }> = [];
  for (const p of parts) {
    const v0 = positions.length / 3;
    vertexRanges.push({ start: v0, count: 8 });
    ranges.push({ start: index.length, count: p.idx.length });
    positions.push(...p.pos);
    index.push(...p.idx.map((i) => i + v0));
  }
  return {
    positions: Float32Array.from(positions),
    normals: null,
    index: Uint32Array.from(index),
    ranges,
    vertexRanges,
    state: {
      alpha: Float32Array.from([1, 0.12, 0.14, 1]),
      color: Float32Array.from([0.9, 0.1, 0.1, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.2, 0.2, 0.2]),
      flags: Uint8Array.from([0, 0, 0, FLAG_HIDDEN]),
    },
  };
}

describe('USDZ export', () => {
  it('groups visible elements by quantised colour and alpha and leaves hidden ones out', () => {
    const b = bucketElements(source());
    expect(b.length).toBe(2);
    expect(b[0]!.alpha).toBe(1);
    expect(b[0]!.elements).toEqual([0]);
    expect(b[1]!.alpha).toBeCloseTo(0.1, 12);
    expect(b[1]!.elements).toEqual([1, 2]);
    expect(b[1]!.triangles).toBe(24);
  });

  it('centres the footprint at the origin with the lowest point at 0', () => {
    const s = buildUsdzScene(source());
    expect(s.elements).toBe(3);
    expect(s.triangles).toBe(36);
    // visible x 0..6, z 0..2, lowest y 0 (the hidden slab at -1 does not count)
    expect(s.offset).toEqual([-3, -0, -1]);
    const g = s.group.children[1] as unknown as { geometry: { getAttribute(n: string): { array: Float32Array }; index: { array: Uint32Array } }; material: { opacity: number; transparent: boolean } };
    expect(g.material.transparent).toBe(true);
    expect(g.material.opacity).toBeCloseTo(0.1, 12);
    expect(Math.max(...g.geometry.index.array)).toBe(15);
  });

  it('writes a USDZ zip: model.usda first, stored, 64-byte aligned, with metres, Y up, plane anchoring and the opacities', async () => {
    const s = buildUsdzScene(source());
    const bytes = await exportUsdz(s.group);
    expect(bytes[0]).toBe(0x50); // PK
    expect(bytes[1]).toBe(0x4b);
    // the first local file header names model.usda; method 0 (stored)
    const nameLen = bytes[26]! | (bytes[27]! << 8);
    expect(strFromU8(bytes.subarray(30, 30 + nameLen))).toBe('model.usda');
    expect(bytes[8]! | (bytes[9]! << 8)).toBe(0);
    const extraLen = bytes[28]! | (bytes[29]! << 8);
    expect((30 + nameLen + extraLen) % 64).toBe(0); // data of the first file starts on a 64-byte boundary
    const files = unzipSync(bytes);
    const names = Object.keys(files);
    expect(names[0]).toBe('model.usda');
    expect(names.filter((n) => n.startsWith('geometries/')).length).toBe(2);
    const usda = strFromU8(files['model.usda']!);
    expect(usda.startsWith('#usda 1.0')).toBe(true);
    expect(usda).toMatch(/metersPerUnit = 1/);
    expect(usda).toMatch(/upAxis = "Y"/);
    expect(usda).toMatch(/preliminary:anchoring:type = "plane"/);
    expect(usda).toMatch(/planeAnchoring:alignment = "horizontal"/);
    expect(usda).toMatch(/float inputs:opacity = 1\b/);
    expect(usda).toMatch(/float inputs:opacity = 0\.1\b/);
    expect(usda).toMatch(/color3f inputs:diffuseColor = \(0\.8666\d*, 0\.1333/); // 0.9 (float32) quantised to 13/15
    const geo = strFromU8(files[names.find((n) => n.startsWith('geometries/'))!]!);
    expect(geo).toMatch(/point3f\[\] points = \[/);
    expect(geo).toMatch(/int\[\] faceVertexCounts = \[3, 3/);
  });
});
