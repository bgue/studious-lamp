// Performance sanity with the O(n)-per-ray box mock. Budgets are generous upper bounds, not benchmarks.

import { describe, expect, it } from 'vitest';
import { Vector3 } from 'three';
import { DEFAULT_CLASSIFICATION, DEFAULT_SIGHTLINES } from '../src/types';
import { classify, sightlines } from '../src/algo';
import { makeScene, type ElementSpec } from './boxProvider';

// Timing budgets are strict only when XRAY_PERF=1; otherwise they get 5x slack so parallel
// work on a shared machine does not fail the suite. Run `XRAY_PERF=1 npx vitest run tests/performance.test.ts` to check budgets.
const SLACK = (globalThis as { process?: { env?: Record<string, string | undefined> } }).process?.env?.['XRAY_PERF'] === '1' ? 1 : 5;

function build() {
  const specs: ElementSpec[] = [];
  // 20 focus boxes: a duct run along x at y = 3, z = 0
  for (let i = 0; i < 20; i++) specs.push({ cls: 'IfcDuctSegment', box: [i * 2, 3, -0.15, i * 2 + 2, 3.3, 0.15], storey: 0 });
  // 2,000 context boxes on a 50 x 40 plan grid, a slab layer above the run and members around it
  const classes = ['IfcSlab', 'IfcWall', 'IfcBeam', 'IfcColumn'];
  for (let i = 0; i < 2000; i++) {
    const gx = i % 50;
    const gz = Math.floor(i / 50) - 20;
    const cls = classes[i % 4]!;
    const y = cls === 'IfcSlab' ? 3.6 : cls === 'IfcBeam' ? 2.6 : 0;
    const h = cls === 'IfcSlab' ? 0.25 : cls === 'IfcBeam' ? 0.4 : 3;
    specs.push({ cls, box: [gx * 1.0, y, gz * 1.0, gx * 1.0 + 0.9, y + h, gz * 1.0 + 0.9], storey: i % 7 === 0 ? 1 : 0 });
  }
  const ports: Array<[number, number]> = [];
  for (let i = 0; i < 19; i++) ports.push([i, i + 1]);
  return makeScene(specs, {
    ports,
    storeys: [
      { id: 0, name: 'L0', elevation: 0 },
      { id: 1, name: 'L1', elevation: 4 },
    ],
  });
}

describe('performance sanity (2,000 context boxes, 20 focus boxes)', () => {
  const { model, geometry } = build();

  it('classify < 200 ms', () => {
    classify(model, geometry, [0], DEFAULT_CLASSIFICATION); // warm up
    const t0 = performance.now();
    const c = classify(model, geometry, [0], DEFAULT_CLASSIFICATION);
    const dt = performance.now() - t0;
    console.info(`classify: ${dt.toFixed(2)} ms (host ${c.host.size}, near ${c.near.size}, far ${c.far.size})`);
    expect(c.focus.size).toBe(20);
    expect(c.host.size + c.near.size).toBeGreaterThan(50);
    expect(dt).toBeLessThan(200 * SLACK);
  });

  it('sightlines with 300 samples < 100 ms', () => {
    const c = classify(model, geometry, [0], DEFAULT_CLASSIFICATION);
    const settings = { ...DEFAULT_SIGHTLINES, samplesPerObject: 15, maxSamples: 300 };
    const camera = new Vector3(20, 15, 0.5);
    const t0 = performance.now();
    const r = sightlines(c, geometry, camera, settings); // includes sample generation (cache miss)
    const dt = performance.now() - t0;
    const t1 = performance.now();
    sightlines(c, geometry, camera, settings); // cache hit
    const dt2 = performance.now() - t1;
    console.info(`sightlines(300): ${dt.toFixed(2)} ms cold, ${dt2.toFixed(2)} ms warm; occluders ${r.occlusion.size}`);
    expect(geometry.calls.raycastAll).toBeGreaterThanOrEqual(600);
    expect([...r.occlusion.values()].some((o) => o > 0)).toBe(true);
    expect(dt).toBeLessThan(100 * SLACK);
    expect(dt2).toBeLessThan(100 * SLACK);
  });

  it('scope all (default): all 2,000 Context boxes are ray candidates and 300 samples stay under 100 ms', () => {
    const c = classify(model, geometry, [0], DEFAULT_CLASSIFICATION);
    const base = { ...DEFAULT_SIGHTLINES, samplesPerObject: 15, maxSamples: 300 };
    const camera = new Vector3(20, 15, 0.5);
    const time = (occluderScope: 'all' | 'near'): { ms: number; evaluated: number } => {
      const s = { ...base, occluderScope };
      sightlines(c, geometry, camera, s); // warm up (samples cached)
      const t0 = performance.now();
      const r = sightlines(c, geometry, camera, s);
      return { ms: performance.now() - t0, evaluated: r.occlusion.size };
    };
    const near = time('near');
    const all = time('all');
    console.info(`sightlines(300) scope near: ${near.ms.toFixed(2)} ms (${near.evaluated} candidates); scope all: ${all.ms.toFixed(2)} ms (${all.evaluated} candidates)`);
    expect(all.evaluated).toBe(c.host.size + c.near.size + c.far.size);
    expect(all.evaluated).toBeGreaterThan(near.evaluated);
    expect(all.ms).toBeLessThan(100 * SLACK);
  });

  it('sample cache: same focus set and settings does not resample', () => {
    const c = classify(model, geometry, [0], DEFAULT_CLASSIFICATION);
    let calls = 0;
    const orig = geometry.samplePoints.bind(geometry);
    geometry.samplePoints = (id, n) => (calls++, orig(id, n));
    const s = { ...DEFAULT_SIGHTLINES, samplesPerObject: 8, maxSamples: 100 };
    sightlines(c, geometry, new Vector3(1, 9, 0), s);
    const first = calls;
    sightlines(c, geometry, new Vector3(5, 9, 1), s);
    expect(calls).toBe(first);
    sightlines(c, geometry, new Vector3(5, 9, 1), { ...s, maxSamples: 60 });
    expect(calls).toBeGreaterThan(first);
    geometry.samplePoints = orig;
  });

  it('maxSamples caps the total, spread evenly over focus elements', () => {
    const c = classify(model, geometry, [0], DEFAULT_CLASSIFICATION);
    let total = 0;
    const per = new Map<number, number>();
    const orig = geometry.samplePoints.bind(geometry);
    geometry.samplePoints = (id, n) => {
      total += n;
      per.set(id, n);
      return orig(id, n);
    };
    sightlines(c, geometry, new Vector3(0, 9, 0), { ...DEFAULT_SIGHTLINES, samplesPerObject: 64, maxSamples: 130 });
    geometry.samplePoints = orig;
    expect(total).toBe(130);
    expect(Math.max(...per.values()) - Math.min(...per.values())).toBeLessThanOrEqual(1);
  });
});
