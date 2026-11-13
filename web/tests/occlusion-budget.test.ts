// Occlusion test cost (src/bcf/attach.ts): early exit once decided, and a per-pass ray budget for refreshing stale outlines.

import { describe, expect, it, vi } from 'vitest';
import { OcclusionCache, mostlyHidden, occlusionWorld } from '../src/bcf/attach';
import type { Vec3 } from '../src/bcf/model';

const pts = (n: number): Vec3[] => Array.from({ length: n }, (_, i) => [i, 0, 0] as Vec3);

describe('mostlyHidden early exit', () => {
  it('gives the same answer as counting all of them, with fewer rays', () => {
    for (let n = 1; n <= 12; n++) {
      for (let mask = 0; mask < 1 << n; mask += n > 8 ? 37 : 1) {
        const s = pts(n);
        let calls = 0;
        const occ = (p: Vec3): boolean => { calls++; return ((mask >> p[0]) & 1) === 1; };
        let hidden = 0;
        for (let i = 0; i < n; i++) if ((mask >> i) & 1) hidden++;
        expect(mostlyHidden(s, occ)).toBe(hidden / n > 0.6);
        expect(calls).toBeLessThanOrEqual(n);
      }
    }
  });
  it('a clearly visible outline costs 5 of 12 rays, a clearly hidden one 8', () => {
    let calls = 0;
    expect(mostlyHidden(pts(12), () => { calls++; return false; })).toBe(false);
    expect(calls).toBe(5);
    calls = 0;
    expect(mostlyHidden(pts(12), () => { calls++; return true; })).toBe(true);
    expect(calls).toBe(8);
  });
});

describe('OcclusionCache budget', () => {
  it('refreshes at most `budget` samples per pass and finishes the rest on the next pass', async () => {
    occlusionWorld.stamp = () => '';
    let t = 0;
    let cam = 'a';
    let rays = 0;
    const redraw = vi.fn();
    const cache = new OcclusionCache(() => { rays++; return false; }, () => cam, redraw, 150, () => t, 20);
    const keys = Array.from({ length: 10 }, (_, i) => `k${i}`);
    const s = pts(12);
    for (const k of keys) cache.behind(k, s); // first sight: tested at once (5 rays each, nothing hidden)
    expect(rays).toBe(50);
    await Promise.resolve();
    rays = 0;
    cam = 'b';
    t = 1000;
    for (const k of keys) cache.behind(k, s);
    expect(rays).toBe(20); // 4 outlines at 5 rays, the rest keep the old answer for now
    expect(rays).toBeLessThan(50);
    await new Promise((r) => setTimeout(r, 40));
    expect(redraw).toHaveBeenCalled();
    rays = 0;
    for (const k of keys) cache.behind(k, s);
    expect(rays).toBe(20); // 6 were left: 4 more now
    await Promise.resolve();
    rays = 0;
    for (const k of keys) cache.behind(k, s);
    expect(rays).toBe(10); // the last 2
  });
  it('a stale answer is kept while it is refreshed, a new key is never skipped', async () => {
    occlusionWorld.stamp = () => '';
    let cam = 'a';
    const cache = new OcclusionCache(() => true, () => cam, () => undefined, 0, () => 0, 0);
    expect(cache.behind('x', pts(12))).toBe(true); // new key: tested although the budget is 0
    cam = 'b';
    expect(cache.behind('x', pts(12))).toBe(true); // budget used up: the old answer stands
  });
  it('a change of the world stamp (a section) invalidates the answers', () => {
    let stamp = '1';
    occlusionWorld.stamp = () => stamp;
    let hidden = true;
    const cache = new OcclusionCache(() => hidden, () => 'cam', () => undefined, 0, () => 0);
    expect(cache.behind('x', pts(12))).toBe(true);
    hidden = false;
    expect(cache.behind('x', pts(12))).toBe(true); // same camera, same stamp: cached
    stamp = '2';
    expect(cache.behind('x', pts(12))).toBe(false);
    occlusionWorld.stamp = () => '';
  });
});
