import { describe, expect, it } from 'vitest';
import { Vector3 } from 'three';
import { UNBLOCKED_LENGTH_M, buildSightRays, rayLength, selectRays } from '../src/cinematic/sightlineViz';
import type { RayQueries } from '../src/cinematic/sightlineViz';

const mk = (n: number, every = 3): Array<{ i: number; blocked: boolean }> =>
  Array.from({ length: n }, (_, i) => ({ i, blocked: i % every === 0 }));

describe('selectRays', () => {
  const rays = mk(30); // blocked: 0,3,6,... = 10 blocked, 20 unblocked
  it('filters by blocked state', () => {
    expect(selectRays(rays, 'all', 100).length).toBe(30);
    expect(selectRays(rays, 'blocked', 100).every((r) => r.blocked)).toBe(true);
    expect(selectRays(rays, 'blocked', 100).length).toBe(10);
    expect(selectRays(rays, 'unblocked', 100).every((r) => !r.blocked)).toBe(true);
    expect(selectRays(rays, 'unblocked', 100).length).toBe(20);
  });
  it('caps at max with an even stride, not the first N', () => {
    const out = selectRays(rays, 'all', 5);
    expect(out.length).toBe(5);
    const idx = out.map((r) => r.i);
    expect(idx).toEqual([...idx].sort((a, b) => a - b));
    expect(idx[0]!).toBeLessThan(6);
    expect(idx[4]!).toBeGreaterThan(23); // reaches the far end of the list
  });
  it('cap applies after the filter', () => {
    const out = selectRays(rays, 'blocked', 4);
    expect(out.length).toBe(4);
    expect(out.every((r) => r.blocked)).toBe(true);
  });
  it('max 0 and empty input give nothing; max above the count keeps everything in order', () => {
    expect(selectRays(rays, 'all', 0)).toEqual([]);
    expect(selectRays([], 'all', 5)).toEqual([]);
    expect(selectRays(rays, 'all', 999).map((r) => r.i)).toEqual(rays.map((r) => r.i));
  });
  it('does not mutate the input', () => {
    const copy = rays.slice();
    selectRays(rays, 'unblocked', 3);
    expect(rays).toEqual(copy);
  });
});

describe('rayLength', () => {
  it('blocked: up to the first hit; unblocked: 3 m; never past the camera', () => {
    expect(rayLength({ blocked: true, hitDist: 1.25, toCamera: 10 })).toBe(1.25);
    expect(rayLength({ blocked: false, hitDist: null, toCamera: 10 })).toBe(UNBLOCKED_LENGTH_M);
    expect(rayLength({ blocked: true, hitDist: null, toCamera: 10 })).toBe(UNBLOCKED_LENGTH_M); // hit unknown -> 3 m
    expect(rayLength({ blocked: false, hitDist: null, toCamera: 1.5 })).toBe(1.5);
    expect(rayLength({ blocked: true, hitDist: 4, toCamera: 2 })).toBe(2);
  });
});

describe('buildSightRays', () => {
  // Occluder slab at y = 2: rays from points with x < 0 are blocked, first hit 2 m above the sample (sample y = 0).
  const q: RayQueries = {
    blocked: (o) => o.x < 0,
    firstHit: () => 2,
  };
  const samples = [new Vector3(-1, 0, 0), new Vector3(1, 0, 0), new Vector3(-2, 0, 1), new Vector3(2, 0, 1)];
  const cam = new Vector3(0, 10, 0);

  it('classifies every sample, unit directions toward the camera', () => {
    const rays = buildSightRays(samples, cam, q, 'all', 100);
    expect(rays.map((r) => r.blocked)).toEqual([true, false, true, false]);
    for (const r of rays) {
      expect(r.dir.length()).toBeCloseTo(1, 9);
      expect(r.toCamera).toBeCloseTo(r.from.distanceTo(cam), 9);
    }
  });
  it('fills the first-hit distance only for the blocked rays that were kept', () => {
    const rays = buildSightRays(samples, cam, q, 'all', 100);
    expect(rays.filter((r) => r.blocked).every((r) => r.hitDist === 2)).toBe(true);
    expect(rays.filter((r) => !r.blocked).every((r) => r.hitDist === null)).toBe(true);
  });
  it('applies the filter and the cap', () => {
    expect(buildSightRays(samples, cam, q, 'blocked', 100).length).toBe(2);
    expect(buildSightRays(samples, cam, q, 'unblocked', 100).length).toBe(2);
    expect(buildSightRays(samples, cam, q, 'all', 3).length).toBe(3);
  });
  it('skips a sample that sits on the camera', () => {
    expect(buildSightRays([cam.clone()], cam, q, 'all', 10)).toEqual([]);
  });
  it('only asks for first-hit distances of rays that survive the cap', () => {
    let calls = 0;
    const counting: RayQueries = { blocked: () => true, firstHit: () => { calls++; return 1; } };
    buildSightRays(samples, cam, counting, 'all', 2);
    expect(calls).toBe(2);
  });
});
