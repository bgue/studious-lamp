// The geometry signature (design 3.2): independent of the triangulation, rotation and translation free where it should be,
// 1 % scale flagged, and the performance budget (1 M triangles < 400 ms in node).
import { describe, expect, it } from 'vitest';
import { computeSignatures, computeSignaturesSliced, eigenvalues3, rel, sigAt } from '../src/revision/geomSig';
import type { TriangleSource } from '../src/revision/geomSig';
import { frameOf, compareShape } from '../src/revision/match';
import { DEFAULT_REVISION_OPTIONS, SIG_STRIDE } from '../src/revision/types';
import type { ModelSnapshot, Vec3 } from '../src/revision/types';
import { cloneSnapshot, measure, synthSnapshot } from './revision-helpers';

type Mat = (p: Vec3) => Vec3;
const id: Mat = (p) => p;

/** A box [0,a]x[0,b]x[0,c] as triangles: `sub` x `sub` quads per face, optionally the other diagonal. Outward winding. */
function box(a: number, b: number, c: number, sub = 1, flipDiagonal = false, f: Mat = id): { position: Float32Array; index: Uint32Array } {
  const pos: number[] = [];
  const idx: number[] = [];
  const face = (o: Vec3, u: Vec3, v: Vec3): void => {
    // origin o, edge vectors u and v (counter-clockwise seen from outside)
    const base = pos.length / 3;
    for (let j = 0; j <= sub; j++) for (let i = 0; i <= sub; i++) {
      const p = f([o[0] + (u[0] * i) / sub + (v[0] * j) / sub, o[1] + (u[1] * i) / sub + (v[1] * j) / sub, o[2] + (u[2] * i) / sub + (v[2] * j) / sub]);
      pos.push(p[0], p[1], p[2]);
    }
    const w = sub + 1;
    for (let j = 0; j < sub; j++) for (let i = 0; i < sub; i++) {
      const p00 = base + j * w + i, p10 = p00 + 1, p01 = p00 + w, p11 = p01 + 1;
      if (flipDiagonal) idx.push(p00, p10, p01, p10, p11, p01); else idx.push(p00, p10, p11, p00, p11, p01);
    }
  };
  face([0, 0, 0], [0, b, 0], [a, 0, 0]); // bottom (normal -z)
  face([0, 0, c], [a, 0, 0], [0, b, 0]); // top
  face([0, 0, 0], [a, 0, 0], [0, 0, c]); // front (-y)
  face([0, b, 0], [0, 0, c], [a, 0, 0]); // back (+y)
  face([0, 0, 0], [0, 0, c], [0, b, 0]); // left (-x)
  face([a, 0, 0], [0, b, 0], [0, 0, c]); // right (+x)
  return { position: Float32Array.from(pos), index: Uint32Array.from(idx) };
}

const sigOf = (g: { position: Float32Array; index: Uint32Array }): number[] => {
  const out = computeSignatures({ position: g.position, index: g.index, ranges: [{ start: 0, count: g.index.length }] });
  return [...out];
};

describe('geometry signature', () => {
  it('has the area, volume, centroid, moments and extent of a box (viewer axes in, IFC axes out)', () => {
    const [area, vol, cx, cy, cz, m1, m2, m3, ex, ey, ez] = sigOf(box(2, 3, 0.5));
    expect(area).toBeCloseTo(2 * (6 + 1 + 1.5), 4);
    expect(vol).toBeCloseTo(3, 4);
    // viewer (x, y, z) = (1, 1.5, 0.25) -> IFC (x, -z, y) = (1, -0.25, 1.5); extent (2, 3, 0.5) -> (2, 0.5, 3)
    expect([cx, cy, cz].map((v) => Math.round(v! * 1e4) / 1e4)).toEqual([1, -0.25, 1.5]);
    expect([ex, ey, ez]).toEqual([2, 0.5, 3]);
    expect(m1! >= m2! && m2! >= m3!).toBe(true);
    expect(m3!).toBeGreaterThan(0);
  });

  it('gives the same signature for one box triangulated three ways, within 1e-5', () => {
    const ref = sigOf(box(2, 3, 0.5, 1));
    for (const g of [box(2, 3, 0.5, 2), box(2, 3, 0.5, 1, true), box(2, 3, 0.5, 4, true)]) {
      const s = sigOf(g);
      for (let k = 0; k < SIG_STRIDE; k++) expect(Math.abs(s[k]! - ref[k]!) / Math.max(1, Math.abs(ref[k]!)), `component ${k}`).toBeLessThan(1e-5);
    }
  });

  it('reports 0 volume for an open surface, and zeros for no triangles', () => {
    const b = box(1, 1, 1);
    const open = sigOf({ position: b.position, index: b.index.slice(0, b.index.length - 6) }); // top face missing
    expect(open[0]).toBeGreaterThan(0);
    expect(open[1]).toBe(0);
    expect(computeSignatures({ position: b.position, index: b.index, ranges: [{ start: 0, count: 0 }] })[0]).toBe(0);
  });

  it('translation changes only the centroid; a 90 degree turn only the centroid and the extent', () => {
    const a = sigOf(box(2, 3, 0.5));
    const moved = sigOf(box(2, 3, 0.5, 1, false, (p) => [p[0] + 10, p[1] - 4, p[2] + 2.5]));
    for (const k of [0, 1, 5, 6, 7, 8, 9, 10]) expect(moved[k]!).toBeCloseTo(a[k]!, 4);
    expect(moved[2]! - a[2]!).toBeCloseTo(10, 4);
    const turned = sigOf(box(2, 3, 0.5, 1, false, (p) => [-p[1], p[0], p[2]])); // 90 degrees about the viewer's y... (x,y) plane turn
    for (const k of [0, 1, 5, 6, 7]) expect(turned[k]!).toBeCloseTo(a[k]!, 4);
    expect(turned.slice(8, 11)).not.toEqual(a.slice(8, 11));
    const slanted = sigOf(box(2, 3, 0.5, 1, false, (p) => { const c = Math.cos(0.5), s = Math.sin(0.5); return [p[0] * c - p[1] * s, p[0] * s + p[1] * c, p[2]]; }));
    for (const k of [0, 1, 5, 6, 7]) expect(rel(slanted[k]!, a[k]!), `moment ${k}`).toBeLessThan(1e-5);
  });

  it('flags a 1 % scale as geometry, a 0.05 % one not, and a move as placement', () => {
    const snapOf = (g: { position: Float32Array; index: Uint32Array }): ModelSnapshot => {
      const s = cloneSnapshot(synthSnapshot({ n: 1 }));
      s.sig.set(computeSignatures({ position: g.position, index: g.index, ranges: [{ start: 0, count: g.index.length }] }));
      return s;
    };
    const o = DEFAULT_REVISION_OPTIONS;
    const base = frameOf(snapOf(box(2, 3, 0.5)), [0, 0, 0]);
    const cmp = (g: { position: Float32Array; index: Uint32Array }) => compareShape(base, 0, frameOf(snapOf(g), [0, 0, 0]), 0, o);
    const scaled = (k: number) => box(2, 3, 0.5, 1, false, (p) => [1 + (p[0] - 1) * k, 1.5 + (p[1] - 1.5) * k, 0.25 + (p[2] - 0.25) * k]); // about the centre
    expect(cmp(scaled(1.01)).flags).toEqual(['geometry']);
    expect(cmp(scaled(1.0005)).flags).toEqual([]);
    const m = cmp(box(2, 3, 0.5, 1, false, (p) => [p[0] + 0.005, p[1], p[2]]));
    expect(m.flags).toEqual(['placement']);
    expect(m.move).toBeCloseTo(0.005, 5);
  });

  it('computes eigenvalues of a symmetric matrix', () => {
    expect(eigenvalues3(3, 2, 1, 0, 0, 0)).toEqual([3, 2, 1]);
    const [a, b, c] = eigenvalues3(2, 2, 3, 1, 0, 0); // [[2,1],[1,2]] block: 3 and 1, plus 3
    expect(a!).toBeCloseTo(3, 6);
    expect(b!).toBeCloseTo(3, 6);
    expect(c!).toBeCloseTo(1, 6);
  });

  it('runs sliced to the same result and yields between slices', async () => {
    const g = box(2, 3, 0.5, 3);
    const n = 1000;
    const ranges = Array.from({ length: n }, () => ({ start: 0, count: g.index.length }));
    const src: TriangleSource = { position: g.position, index: g.index, ranges };
    let yields = 0, clock = 0;
    const sliced = await computeSignaturesSliced(src, { sliceMs: 3, now: () => (clock += 1), yieldToUi: async () => { yields++; } });
    expect(yields).toBeGreaterThan(1);
    expect([...sliced!]).toEqual([...computeSignatures(src)]);
    const aborted = await computeSignaturesSliced(src, { signal: { aborted: true } });
    expect(aborted).toBeNull();
    expect(sigAt(sliced!, 0).area).toBeGreaterThan(0);
  });

  it('budget: 1 M triangles in under 400 ms', () => {
    // 4000 elements of 250 triangles each (1 M in all), on a shared vertex pool laid out like a merged geometry
    const per = box(1, 1, 1, 6);
    const nt = per.index.length / 3;
    const elements = Math.ceil(1_000_000 / nt);
    const pv = per.position.length / 3;
    const position = new Float32Array(elements * per.position.length);
    const index = new Uint32Array(elements * per.index.length);
    const ranges: Array<{ start: number; count: number }> = [];
    for (let e = 0; e < elements; e++) {
      for (let i = 0; i < per.position.length; i += 3) { position[e * per.position.length + i] = per.position[i]! + (e % 100); position[e * per.position.length + i + 1] = per.position[i + 1]! + Math.floor(e / 100); position[e * per.position.length + i + 2] = per.position[i + 2]!; }
      for (let i = 0; i < per.index.length; i++) index[e * per.index.length + i] = per.index[i]! + e * pv;
      ranges.push({ start: e * per.index.length, count: per.index.length });
    }
    computeSignatures({ position, index, ranges: ranges.slice(0, 50) }); // warm up the JIT
    const m = measure(() => computeSignatures({ position, index, ranges }));
    const out = m.value, ms = m.ms;
    console.log(`geomSig: ${(elements * nt).toLocaleString()} triangles in ${ms.toFixed(0)} ms (wall ${m.wallMs.toFixed(0)})`);
    expect(out[0]).toBeGreaterThan(0);
    expect(ms).toBeLessThan(400);
  });
});
