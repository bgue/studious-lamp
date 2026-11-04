// Layer weighting of Algorithm 2: stacked occluders on one ray no longer share one hit credit.

import { describe, expect, it } from 'vitest';
import { DEFAULT_CLASSIFICATION, DEFAULT_SIGHTLINES, type SightlineSettings } from '../src/types';
import {
  DEFAULT_TIER_SETTINGS,
  classify,
  classifyTiers,
  layerCredit,
  sightlines,
  sightlinesTiered,
} from '../src/algo';
import { buildStackedScene } from './fixtures/stacked-scene';

const { duct, bottom, middle, top } = buildStackedScene().ids;
const cfg = (over: Partial<SightlineSettings>): SightlineSettings => ({ ...DEFAULT_SIGHTLINES, ...over });

function run(over: Partial<SightlineSettings>, hosts?: Array<'bottom' | 'middle' | 'top'>) {
  const sc = buildStackedScene({ hosts });
  const cls = classify(sc.model, sc.geometry, [duct], DEFAULT_CLASSIFICATION);
  return { sc, cls, res: sightlines(cls, sc.geometry, sc.camera, cfg(over)) };
}

describe('defaults and credit function', () => {
  it('defaults: front, falloff 0.5, budget 2', () => {
    expect(DEFAULT_SIGHTLINES.layerWeighting).toBe('front');
    expect(DEFAULT_SIGHTLINES.layerFalloff).toBe(0.5);
    expect(DEFAULT_SIGHTLINES.layerBudget).toBe(2);
  });

  it('layerCredit', () => {
    expect([0, 1, 2, 3].map((k) => layerCredit({ layerWeighting: 'uniform' }, k))).toEqual([1, 1, 1, 1]);
    expect([0, 1, 2, 3].map((k) => layerCredit({ layerWeighting: 'front', layerFalloff: 0.5 }, k))).toEqual([1, 0.5, 0.25, 0.125]);
    expect([0, 1, 2, 3].map((k) => layerCredit({ layerWeighting: 'budget', layerBudget: 2 }, k))).toEqual([1, 1, 0, 0]);
    // undefined fields fall back to the defaults ('front', 0.5)
    expect(layerCredit({}, 2)).toBe(0.25);
  });
});

describe('stacked slabs, camera straight above', () => {
  it('fixture: all three slabs are Host', () => {
    const { cls } = run({});
    expect([...cls.host].sort()).toEqual([bottom, middle, top]);
  });

  it("'uniform': all three slabs get the same occlusion and target alpha", () => {
    const { res } = run({ layerWeighting: 'uniform' });
    for (const id of [bottom, middle, top]) expect(res.occlusion.get(id)).toBeCloseTo(1, 9);
    expect(res.targetAlpha.get(bottom)).toBeCloseTo(res.targetAlpha.get(top)!, 12);
    expect(res.targetAlpha.get(middle)).toBeCloseTo(res.targetAlpha.get(top)!, 12);
    expect(res.targetAlpha.get(top)).toBeCloseTo(0.15, 9); // alphaMin
  });

  it("'front': top 1.0, middle 0.5, bottom 0.25, target alphas ascend from top to bottom", () => {
    const { res } = run({ layerWeighting: 'front' });
    expect(res.occlusion.get(top)).toBeCloseTo(1.0, 9);
    expect(res.occlusion.get(middle)).toBeCloseTo(0.5, 9);
    expect(res.occlusion.get(bottom)).toBeCloseTo(0.25, 9);
    const a = [top, middle, bottom].map((id) => res.targetAlpha.get(id)!);
    expect(a[0]!).toBeLessThan(a[1]!);
    expect(a[1]!).toBeLessThan(a[2]!);
    expect(a[0]).toBeCloseTo(0.15, 9);
    expect(a[1]).toBeCloseTo(0.85 - 0.7 * Math.sqrt(0.5), 9);
    expect(a[2]).toBeCloseTo(0.85 - 0.7 * Math.sqrt(0.25), 9);
  });

  it('is the default mode', () => {
    const { res } = run({});
    expect(res.occlusion.get(bottom)).toBeCloseTo(0.25, 9);
  });

  it('layerFalloff changes the ratio; falloff 1 equals uniform', () => {
    const r = run({ layerFalloff: 0.8 }).res;
    expect(r.occlusion.get(middle)).toBeCloseTo(0.8, 9);
    expect(r.occlusion.get(bottom)).toBeCloseTo(0.64, 9);
    const one = run({ layerFalloff: 1 }).res;
    expect(one.occlusion.get(bottom)).toBeCloseTo(1, 9);
  });

  it("'budget' 2: bottom slab stays opaque at alphaMax; top and middle ghost fully", () => {
    const { res } = run({ layerWeighting: 'budget', layerBudget: 2 });
    expect(res.occlusion.get(top)).toBeCloseTo(1, 9);
    expect(res.occlusion.get(middle)).toBeCloseTo(1, 9);
    expect(res.occlusion.get(bottom)).toBe(0);
    expect(res.targetAlpha.get(bottom)).toBeCloseTo(DEFAULT_SIGHTLINES.alphaMax, 9);
    expect(res.targetAlpha.get(top)).toBeCloseTo(0.15, 9);
  });

  it("'budget' 1 only ghosts the front slab; 3 ghosts all", () => {
    const one = run({ layerWeighting: 'budget', layerBudget: 1 }).res;
    expect([top, middle, bottom].map((id) => one.occlusion.get(id))).toEqual([1, 0, 0]);
    const three = run({ layerWeighting: 'budget', layerBudget: 3 }).res;
    expect([top, middle, bottom].map((id) => three.occlusion.get(id))).toEqual([1, 1, 1]);
  });

  it('a camera below the stack reverses the order (nearest the camera is k = 0)', () => {
    const { sc, cls } = run({});
    const below = sc.camera.clone().set(2, -6, 0);
    // From below the duct only sees nothing in the way: the slabs are all above the duct.
    const r = sightlines(cls, sc.geometry, below, cfg({}));
    for (const id of [bottom, middle, top]) expect(r.occlusion.get(id)).toBe(0);
  });
});

describe("scope 'all' with a Far slab in the stack", () => {
  // Top slab is not hosted: 1.3 m above the duct, beyond the 0.6 m buffer, so Far.
  const hosts: Array<'bottom' | 'middle'> = ['bottom', 'middle'];

  it('the top slab is Far', () => {
    const { cls } = run({}, hosts);
    expect([...cls.far]).toEqual([top]);
  });

  it("scope 'all', front: the Far slab is the front layer (1.0), the others follow (0.5, 0.25)", () => {
    const { res } = run({ occluderScope: 'all', layerWeighting: 'front' }, hosts);
    expect(res.occlusion.get(top)).toBeCloseTo(1, 9);
    expect(res.occlusion.get(middle)).toBeCloseTo(0.5, 9);
    expect(res.occlusion.get(bottom)).toBeCloseTo(0.25, 9);
    // Far keeps its own formula: ceiling 1, farWeight
    expect(res.targetAlpha.get(top)).toBeCloseTo(1 + (0.15 - 1) * 0.7, 9);
  });

  it("scope 'all', farWeight still scales the Far importance", () => {
    const { res } = run({ occluderScope: 'all', farWeight: 0.3 }, hosts);
    expect(res.targetAlpha.get(top)).toBeCloseTo(1 + (0.15 - 1) * 0.3, 9);
  });

  it("scope 'all', budget 2: the Far slab uses a slot, so the bottom slab stays opaque", () => {
    const { res } = run({ occluderScope: 'all', layerWeighting: 'budget', layerBudget: 2 }, hosts);
    expect(res.occlusion.get(top)).toBeCloseTo(1, 9);
    expect(res.occlusion.get(middle)).toBeCloseTo(1, 9);
    expect(res.occlusion.get(bottom)).toBe(0);
    expect(res.targetAlpha.get(bottom)).toBeCloseTo(0.85, 9);
  });

  it("scope 'near': the Far slab is not a candidate and takes no layer slot", () => {
    const { res } = run({ occluderScope: 'near', layerWeighting: 'front' }, hosts);
    expect(res.occlusion.has(top)).toBe(false);
    expect(res.occlusion.get(middle)).toBeCloseTo(1, 9);
    expect(res.occlusion.get(bottom)).toBeCloseTo(0.5, 9);
  });

  it('uniform reproduces the old behaviour for the whole stack', () => {
    const { res } = run({ occluderScope: 'all', layerWeighting: 'uniform' }, hosts);
    for (const id of [bottom, middle, top]) expect(res.occlusion.get(id)).toBeCloseTo(1, 9);
  });
});

describe('tiered variant mirrors the layer credit', () => {
  const TIERS = [['IfcDuctSegment'], ['IfcSlab']];
  const sc = buildStackedScene();
  const tc = classifyTiers(sc.model, sc.geometry, [duct], TIERS);

  it('front: 1.0 / 0.5 / 0.25; uniform: all 1; budget 2: bottom 0', () => {
    const t = (over: Partial<SightlineSettings>) =>
      sightlinesTiered(tc, sc.geometry, sc.camera, { ...DEFAULT_TIER_SETTINGS, ...over });
    const f = t({ layerWeighting: 'front' });
    expect([top, middle, bottom].map((id) => f.occlusion.get(id)!.toFixed(6))).toEqual(['1.000000', '0.500000', '0.250000']);
    const u = t({ layerWeighting: 'uniform' });
    for (const id of [bottom, middle, top]) expect(u.occlusion.get(id)).toBeCloseTo(1, 9);
    const b = t({ layerWeighting: 'budget', layerBudget: 2 });
    expect(b.occlusion.get(bottom)).toBe(0);
    expect(b.targetAlpha.get(bottom)).toBeCloseTo(DEFAULT_TIER_SETTINGS.alphaMax, 9);
  });
});
