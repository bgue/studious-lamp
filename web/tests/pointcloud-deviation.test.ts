import { describe, expect, it } from 'vitest';
import { Matrix4 } from 'three';
import { bandOf, buildColours, BAND_COLORS, UNMEASURED } from '../src/pointcloud/colour';
import { computeDeviation, sampleStride, summarise } from '../src/pointcloud/deviation';
import type { CloudFrame } from '../src/pointcloud/align';

const TOL = 0.02;

describe('bands', () => {
  it('green up to the tolerance, amber to twice, red to five times, then unrelated', () => {
    expect([0, 0.02, 0.0201, 0.04, 0.0401, 0.1, 0.1001, Infinity, NaN].map((d) => bandOf(d, TOL))).toEqual([0, 0, 1, 1, 2, 2, 3, 3, 3]);
  });
  it('colours bands as green, amber, red and grey, and unmeasured points apart', () => {
    const dev = Float32Array.from([0.001, 0.03, 0.08, 0.5, 0]);
    const measured = Uint8Array.from([1, 1, 1, 1, 0]);
    const c = buildColours('deviation', { count: 5, deviation: dev, measured, tolerance: TOL });
    const at = (i: number): number[] => Array.from(c.subarray(i * 3, i * 3 + 3));
    expect(at(0)).toEqual(BAND_COLORS[0]);
    expect(at(1)).toEqual(BAND_COLORS[1]);
    expect(at(2)).toEqual(BAND_COLORS[2]);
    expect(at(3)).toEqual(BAND_COLORS[3]);
    expect(at(4)).toEqual(UNMEASURED);
    expect(BAND_COLORS[0]![1]).toBeGreaterThan(BAND_COLORS[0]![0]); // green dominates
    expect(BAND_COLORS[2]![0]).toBeGreaterThan(BAND_COLORS[2]![1]); // red dominates
  });
  it('rgb falls back to a height ramp without colours, intensity and classes follow their data', () => {
    const heights = Float32Array.from([0, 1, 2]);
    const rgbFallback = buildColours('rgb', { count: 3, heights, tolerance: TOL });
    expect(rgbFallback[0]).not.toBe(rgbFallback[6]);
    const inten = buildColours('intensity', { count: 3, intensity: Float32Array.from([0, 50, 100]), intensityRange: [0, 100], tolerance: TOL });
    expect(Array.from(inten.subarray(0, 3))).toEqual([0, 0, 0]);
    expect(Array.from(inten.subarray(6, 9))).toEqual([255, 255, 255]);
    const cls = buildColours('classification', { count: 2, classification: Uint8Array.from([2, 6]), tolerance: TOL });
    expect(Array.from(cls.subarray(0, 3))).not.toEqual(Array.from(cls.subarray(3, 6)));
  });
});

describe('statistics on a synthetic plane', () => {
  // The model is the plane y = 0. The cloud is a grid of points at known heights above it.
  const plane = (_x: number, y: number, _z: number, max: number): number => (Math.abs(y) <= max ? Math.abs(y) : Infinity);
  const heights = [...Array(60).fill(0.005), ...Array(20).fill(0.03), ...Array(10).fill(0.07), ...Array(10).fill(0.4)]; // 100 points
  const pos = new Float32Array(heights.length * 3);
  heights.forEach((h, i) => pos.set([i * 0.01, h, 0], i * 3));
  const frame = { matrix: new Matrix4() } as CloudFrame;

  it('measures every point, bands them and summarises', async () => {
    const d = (await computeDeviation({ positions: pos, frame, indices: sampleStride(100, 500_000), distance: plane, tolerance: TOL }))!;
    expect(d.length).toBe(100);
    expect(d[0]).toBeCloseTo(0.005, 7);
    expect(d[99]).toBe(Infinity);
    const s = summarise(d, TOL);
    expect(s.bands).toEqual([60, 20, 10, 10]);
    expect(s.sampled).toBe(100);
    expect(s.related).toBe(90);
    expect(s.shareWithin).toBeCloseTo(60 / 90, 12);
    expect(s.shareWithinOfAll).toBeCloseTo(0.6, 12);
    expect(s.unrelatedShare).toBeCloseTo(0.1, 12);
    expect(s.mean).toBeCloseTo((60 * 0.005 + 20 * 0.03 + 10 * 0.07) / 90, 6);
    expect(s.median).toBeCloseTo(0.005, 7);
    // 95th percentile of the 90 related points: position 0.95 * 89 = 84.55 of the sorted list -> in the 0.07 group
    expect(s.p95).toBeCloseTo(0.07, 7);
    expect(s.maxDistance).toBeCloseTo(0.1, 12);
  });
  it('applies the frame (offset and rotation) before measuring', async () => {
    const lift = { matrix: new Matrix4().makeTranslation(0, 0.5, 0) } as CloudFrame;
    const d = (await computeDeviation({ positions: pos, frame: lift, indices: sampleStride(100, 100), distance: plane, tolerance: 1 }))!;
    expect(d[0]).toBeCloseTo(0.505, 6);
  });
  it('breaks the cloud into time slices that yield, reports progress and can be cancelled', async () => {
    let yields = 0;
    const progress: number[] = [];
    const slow = (x: number, y: number, z: number, m: number): number => { const t = performance.now(); while (performance.now() - t < 0.2); return plane(x, y, z, m); };
    const d = await computeDeviation({
      positions: pos, frame, indices: sampleStride(100, 100), distance: slow, tolerance: TOL, sliceMs: 5,
      onProgress: (f) => progress.push(f), yieldFn: async () => { yields++; },
    });
    expect(d!.length).toBe(100);
    expect(yields).toBeGreaterThan(1);
    expect(progress[progress.length - 1]).toBe(1);
    let calls = 0;
    const cancelled = await computeDeviation({
      positions: pos, frame, indices: sampleStride(100, 100), distance: slow, tolerance: TOL, sliceMs: 2,
      yieldFn: async () => { calls++; }, isCancelled: () => calls >= 2,
    });
    expect(cancelled).toBeNull();
  });
  it('samples at most the cap, evenly', () => {
    const idx = sampleStride(1_000_000, 500_000);
    expect(idx.length).toBe(500_000);
    expect(idx[0]).toBe(0);
    expect(idx[499_999]).toBeGreaterThan(998_000);
    expect(sampleStride(10, 500_000).length).toBe(10);
  });
  it('groups statistics by classification', () => {
    const dist = Float32Array.from([0.001, 0.002, 0.07, 0.08, 0.5]);
    const s = summarise(dist, TOL, Uint8Array.from([6, 6, 19, 19, 19]));
    expect(s.byClass![6]).toMatchObject({ n: 2, related: 2, shareWithin: 1, shareRed: 0 });
    expect(s.byClass![19]!.shareRed).toBeCloseTo(2 / 3, 12);
    expect(s.byClass![19]!.shareWithin).toBe(0);
  });
  it('handles an empty related set', () => {
    const s = summarise(Float32Array.from([1, 2]), TOL);
    expect(s.related).toBe(0);
    expect(Number.isNaN(s.mean)).toBe(true);
    expect(Number.isNaN(s.p95)).toBe(true);
  });
});
