import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { parseModel } from '../src/model/loader';
import { computeClosedFlags } from '../src/model/closedMesh';
import type { Range } from '../src/model/closedMesh';

/** Build one merged soup from per-element (positions, indices) pairs. */
function merge(parts: Array<{ pos: number[]; idx: number[] }>): { position: Float32Array; index: Uint32Array; ranges: Range[]; vranges: Range[] } {
  const pos: number[] = [];
  const idx: number[] = [];
  const ranges: Range[] = [];
  const vranges: Range[] = [];
  for (const p of parts) {
    const v0 = pos.length / 3;
    vranges.push({ start: v0, count: p.pos.length / 3 });
    ranges.push({ start: idx.length, count: p.idx.length });
    pos.push(...p.pos);
    for (const i of p.idx) idx.push(i + v0);
  }
  return { position: new Float32Array(pos), index: new Uint32Array(idx), ranges, vranges };
}

/** Axis-aligned box at (x0,y0,z0) of size (sx,sy,sz) with 8 shared vertices. */
function box8(x0 = 0, y0 = 0, z0 = 0, s = 1): { pos: number[]; idx: number[] } {
  const pos: number[] = [];
  for (let i = 0; i < 8; i++) pos.push(x0 + (i & 1) * s, y0 + ((i >> 1) & 1) * s, z0 + ((i >> 2) & 1) * s);
  const q = [[0, 1, 3, 2], [4, 6, 7, 5], [0, 4, 5, 1], [2, 3, 7, 6], [0, 2, 6, 4], [1, 5, 7, 3]];
  const idx: number[] = [];
  for (const f of q) idx.push(f[0]!, f[1]!, f[2]!, f[0]!, f[2]!, f[3]!);
  return { pos, idx };
}

/** The same box with 24 vertices (4 per face, as the crease-welded geometry has at sharp edges). */
function box24(x0 = 0, y0 = 0, z0 = 0, s = 1): { pos: number[]; idx: number[] } {
  const b = box8(x0, y0, z0, s);
  const pos: number[] = [];
  const idx: number[] = [];
  for (let t = 0; t < b.idx.length; t++) {
    const v = b.idx[t]!;
    pos.push(b.pos[v * 3]!, b.pos[v * 3 + 1]!, b.pos[v * 3 + 2]!);
    idx.push(t);
  }
  return { pos, idx };
}

describe('computeClosedFlags', () => {
  it('flags a box with shared vertices and a box whose faces do not share vertices as closed', () => {
    const m = merge([box8(), box24(3, 0, 0)]);
    expect([...computeClosedFlags(m.position, m.index, m.ranges, m.vranges)]).toEqual([1, 1]);
  });

  it('flags a single-sided pane (2 triangles) and a box missing a face as open', () => {
    const pane = { pos: [0, 0, 0, 1, 0, 0, 1, 1, 0, 0, 1, 0], idx: [0, 1, 2, 0, 2, 3] };
    const b = box8();
    const open = { pos: b.pos, idx: b.idx.slice(0, b.idx.length - 6) };
    const m = merge([pane, open, box8()]);
    expect([...computeClosedFlags(m.position, m.index, m.ranges, m.vranges)]).toEqual([0, 0, 1]);
  });

  it('flags a finely tessellated open sheet as open and an element without triangles as open', () => {
    const pos: number[] = [];
    const idx: number[] = [];
    const N = 20;
    for (let j = 0; j <= N; j++) for (let i = 0; i <= N; i++) pos.push(i, j, Math.sin(i / 3));
    for (let j = 0; j < N; j++) for (let i = 0; i < N; i++) {
      const a = j * (N + 1) + i;
      idx.push(a, a + 1, a + N + 2, a, a + N + 2, a + N + 1);
    }
    const m = merge([{ pos, idx }, { pos: [], idx: [] }]);
    expect([...computeClosedFlags(m.position, m.index, m.ranges, m.vranges)]).toEqual([0, 0]);
  });

  it('treats an element made of a closed box plus a loose pane as open', () => {
    const b = box8();
    const pos = [...b.pos, 5, 5, 5, 6, 5, 5, 6, 6, 5];
    const idx = [...b.idx, 8, 9, 10];
    const m = merge([{ pos, idx }]);
    expect(computeClosedFlags(m.position, m.index, m.ranges, m.vranges)[0]).toBe(0);
  });

  it('is fast on 100,000 elements', () => {
    const parts: Array<{ pos: number[]; idx: number[] }> = [];
    for (let i = 0; i < 100_000; i++) parts.push(i % 5 === 0 ? box24(i, 0, 0) : i % 7 === 0 ? { pos: [0, 0, 0, 1, 0, 0, 1, 1, 0], idx: [0, 1, 2] } : box8(i, 0, 0));
    const m = merge(parts);
    const t0 = performance.now();
    const f = computeClosedFlags(m.position, m.index, m.ranges, m.vranges);
    const ms = performance.now() - t0;
    console.log(`closed flags, 100000 elements (${m.index.length / 3} triangles): ${ms.toFixed(1)} ms`);
    let open = 0;
    for (let i = 0; i < f.length; i++) if (f[i] === 0) open++;
    expect(open).toBe(parts.filter((_, i) => i % 5 !== 0 && i % 7 === 0).length);
    expect(ms).toBeLessThan(5 * 300); // measured well below 300 ms; 5x slack as in performance.test.ts unless XRAY_PERF=1
    if (process.env.XRAY_PERF === '1') expect(ms).toBeLessThan(300);
  });

  it('classifies the real models: every solid is closed, T-junctions tolerated (census printed)', async () => {
    for (const name of ['fzk-haus', 'building', 'synth5k']) {
      const glb = readFileSync(fileURLToPath(new URL(`../public/models/${name}.glb`, import.meta.url)));
      const side = JSON.parse(readFileSync(fileURLToPath(new URL(`../public/models/${name}.json`, import.meta.url)), 'utf8'));
      const { model, geometry } = await parseModel(glb.buffer.slice(glb.byteOffset, glb.byteOffset + glb.byteLength) as ArrayBuffer, side);
      const t0 = performance.now();
      const f = computeClosedFlags(geometry.geometry.getAttribute('position').array, geometry.geometry.getIndex()!.array, geometry.ranges, geometry.vertexRanges);
      const ms = performance.now() - t0;
      const byClass = new Map<string, [number, number]>();
      model.elements.forEach((e, i) => {
        const c = byClass.get(e.ifcClass) ?? [0, 0];
        c[f[i] ? 0 : 1]++;
        byClass.set(e.ifcClass, c);
      });
      console.log(`${name}: ${model.elements.length} elements, ${ms.toFixed(1)} ms; closed/open by class: ${[...byClass].map(([k, v]) => `${k} ${v[0]}/${v[1]}`).join(', ')}`);
      expect(f.length).toBe(model.elements.length);
      expect([...f].filter((v) => v === 0).length, `${name}: open elements (T-junctions must not count)`).toBe(0);
    }
  });
});
