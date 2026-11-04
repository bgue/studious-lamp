import { describe, expect, it } from 'vitest';
import { decimate, mulberry32, sampleIndices } from '../src/pointcloud/decimate';
import { PointCloudLoader, WORKER_THRESHOLD } from '../src/pointcloud/client';
import { CloudSession } from '../src/pointcloud/session';
import { parsePointCloud } from '../src/pointcloud/readers';
import { grid, las } from './pointcloud-helpers';

describe('decimation', () => {
  it('returns exactly the budget, ascending, without repeats', () => {
    for (const [n, k] of [[1000, 1], [1000, 10], [1000, 999], [100_000, 3_000], [7, 3]] as const) {
      const idx = sampleIndices(n, k, 5);
      expect(idx.length).toBe(k);
      for (let i = 1; i < k; i++) expect(idx[i]!).toBeGreaterThan(idx[i - 1]!);
      expect(idx[k - 1]!).toBeLessThan(n);
    }
  });
  it('is deterministic for a seed and differs between seeds', () => {
    const a = sampleIndices(50_000, 2_000, 11);
    const b = sampleIndices(50_000, 2_000, 11);
    const c = sampleIndices(50_000, 2_000, 12);
    expect(Array.from(a)).toEqual(Array.from(b));
    expect(Array.from(a)).not.toEqual(Array.from(c));
    expect(mulberry32(3)()).toBe(mulberry32(3)());
  });
  it('is spread evenly: every tenth of the cloud gets about a tenth of the sample', () => {
    const idx = sampleIndices(100_000, 5_000, 1);
    const bins = new Array(10).fill(0);
    for (const i of idx) bins[Math.floor(i / 10_000)]++;
    for (const b of bins) expect(Math.abs(b - 500)).toBeLessThan(80);
  });
  it('keeps the whole cloud, without copying, when it fits the budget', () => {
    const d = parsePointCloud(las(grid(100)), 'a.las');
    const s = decimate(d, 1000);
    expect(s.count).toBe(100);
    expect(s.positions).toBe(d.positions);
  });
  it('keeps attributes aligned with the positions it keeps', () => {
    const pts = grid(500).map((p, k) => ({ ...p, i: k, c: k % 200 }));
    const d = parsePointCloud(las(pts, { format: 3 }), 'a.las');
    const s = decimate(d, 60, 9);
    expect(s.count).toBe(60);
    expect(s.positions.length).toBe(180);
    expect(s.colors!.length).toBe(180);
    for (let k = 0; k < 60; k++) {
      const orig = s.intensity![k]!; // intensity was set to the source index
      expect(s.positions[k * 3]!).toBe(d.positions[orig * 3]!);
      expect(s.classification![k]!).toBe((orig % 200) & 31); // LAS 1.2 classes are 5 bits
      expect(s.colors![k * 3]!).toBe(d.colors![orig * 3]!);
    }
  });
  it('reports original and shown counts through the session and the loader', async () => {
    const buf = las(grid(1000)).slice().buffer as ArrayBuffer;
    const s = new CloudSession();
    const info = s.load(buf, 'a.las');
    expect(info.originalCount).toBe(1000);
    expect(info.hasColor).toBe(true);
    expect(s.decimate(250).shown.count).toBe(250);
    const l = new PointCloudLoader();
    const r = await l.load(buf, 'a.las', { budget: 300 });
    expect(r.mode).toBe('inline');
    expect(r.info.originalCount).toBe(1000);
    expect(r.shown.count).toBe(300);
    const again = await l.decimate(50);
    expect(again.shown.count).toBe(50);
    l.dispose();
    expect(WORKER_THRESHOLD).toBe(5 * 1024 * 1024);
  });
  it('surfaces reader errors from the loader', async () => {
    const l = new PointCloudLoader();
    await expect(l.load(new TextEncoder().encode('nope').buffer as ArrayBuffer, 'a.laz', { budget: 10 })).rejects.toThrow(/PDAL/);
  });
});

describe('performance of the pure pipeline', () => {
  it('parses and decimates 300k points quickly (5x slack unless XRAY_PERF=1)', () => {
    const n = 300_000;
    const pts = new Array(n);
    for (let k = 0; k < n; k++) pts[k] = { x: (k % 1000) * 0.01, y: Math.floor(k / 1000) * 0.01, z: (k % 13) * 0.1, r: k & 255, g: 7, b: 9, i: k & 1023, c: 6 };
    const buf = las(pts, { format: 2 });
    const t0 = performance.now();
    const d = parsePointCloud(buf, 'big.las');
    const t1 = performance.now();
    const s = decimate(d, 100_000);
    const t2 = performance.now();
    expect(d.count).toBe(n);
    expect(s.count).toBe(100_000);
    const slack = process.env['XRAY_PERF'] === '1' ? 1 : 5;
    expect(t1 - t0).toBeLessThan(400 * slack);
    expect(t2 - t1).toBeLessThan(100 * slack);
  });
});
