// occluderScope 'all': Far elements are ray candidates and ghost with weight farWeight.

import { describe, expect, it } from 'vitest';
import { Vector3 } from 'three';
import { DEFAULT_CLASSIFICATION, DEFAULT_SIGHTLINES, FLAG_HIDDEN } from '../src/types';
import {
  DEFAULT_TIER_SETTINGS,
  applyRenderState,
  classify,
  classifyTiers,
  createRenderState,
  occluderSet,
  sightlines,
  sightlinesTiered,
  smoothAlpha,
} from '../src/algo';
import { makeScene } from './boxProvider';

// Duct at x 0..4, a Near slab above it, an exterior wall 3 m to the side (Far) that sits between
// a camera at -x and the duct, and a Far wall on the other side.
const scene = () =>
  makeScene([
    { cls: 'IfcDuctSegment', box: [0, 0, -0.15, 4, 0.3, 0.15] }, // 0
    { cls: 'IfcSlab', box: [-1, 0.5, -2, 5, 0.75, 2] }, // 1 Near (0.2 m above)
    { cls: 'IfcWall', box: [-3.2, -2, -4, -3.0, 4, 4] }, // 2 Far, west of the duct (3 m)
    { cls: 'IfcWall', box: [7.0, -2, -4, 7.2, 4, 4] }, // 3 Far, east
  ]);

const WEST = new Vector3(-9, 0.15, 0);
const EAST = new Vector3(12, 0.15, 0);

describe('sightlines with occluderScope', () => {
  const { model, geometry } = scene();
  const cls = classify(model, geometry, [0], DEFAULT_CLASSIFICATION);
  const all = { ...DEFAULT_SIGHTLINES, occluderScope: 'all' as const };
  const near = { ...DEFAULT_SIGHTLINES, occluderScope: 'near' as const };

  it('classification: walls are Far, slab Near', () => {
    expect([...cls.far].sort()).toEqual([2, 3]);
    expect([...cls.near]).toEqual([1]);
  });

  it('defaults: scope all, farWeight 0.7', () => {
    expect(DEFAULT_SIGHTLINES.occluderScope).toBe('all');
    expect(DEFAULT_SIGHTLINES.farWeight).toBe(0.7);
  });

  it('scope all: the west wall blocks every sample, target = 1 + (alphaMin - 1) * (occ^gamma * farWeight)', () => {
    const r = sightlines(cls, geometry, WEST, all);
    expect(r.occlusion.get(2)).toBeCloseTo(1, 9);
    expect(r.importance.get(2)).toBeCloseTo(0.7, 9);
    expect(r.targetAlpha.get(2)).toBeCloseTo(1 + (0.15 - 1) * 0.7, 9);
    // a Far element that blocks nothing stays fully opaque (ceiling 1, not alphaMax)
    expect(r.occlusion.get(3)).toBe(0);
    expect(r.targetAlpha.get(3)).toBe(1);
    // Near keeps its own formula
    expect(r.targetAlpha.get(1)).toBeCloseTo(0.85, 9);
  });

  it('scope near: Far is not evaluated at all and no ray is tested against it', () => {
    const r = sightlines(cls, geometry, WEST, near);
    expect(r.targetAlpha.has(2)).toBe(false);
    expect(r.occlusion.has(3)).toBe(false);
    expect(occluderSet(cls).has(2)).toBe(false);
    expect(occluderSet(cls, undefined, 'all').has(2)).toBe(true);
  });

  it('farWeight scales the ghosting', () => {
    const r = sightlines(cls, geometry, WEST, { ...all, farWeight: 0.3 });
    expect(r.targetAlpha.get(2)).toBeCloseTo(1 + (0.15 - 1) * 0.3, 9);
    const r0 = sightlines(cls, geometry, WEST, { ...all, farWeight: 0 });
    expect(r0.targetAlpha.get(2)).toBe(1);
  });

  it('the east camera ghosts the east wall instead', () => {
    const r = sightlines(cls, geometry, EAST, all);
    expect(r.targetAlpha.get(3)!).toBeLessThan(0.5);
    expect(r.targetAlpha.get(2)).toBe(1);
  });

  it('flagged-hidden Far elements are not ray candidates', () => {
    const state = createRenderState(model.elements.length);
    state.flags[2] = FLAG_HIDDEN;
    const r = sightlines(cls, geometry, WEST, all, state);
    expect(r.occlusion.get(2)).toBe(0);
    expect(occluderSet(cls, state, 'all').has(2)).toBe(false);
  });
});

describe('smoothAlpha / applyRenderState with Far', () => {
  const { model, geometry } = scene();
  const cls = classify(model, geometry, [0], DEFAULT_CLASSIFICATION);
  const r = sightlines(cls, geometry, WEST, DEFAULT_SIGHTLINES);
  const ov = { userHides: new Set<number>(), userPins: new Set<number>(), projectPins: {} };

  it('steps Far alphas towards their targets under scope all', () => {
    const state = createRenderState(model.elements.length);
    for (let i = 0; i < 40; i++) {
      const a = smoothAlpha(state.alpha, r.targetAlpha, new Map(), DEFAULT_SIGHTLINES, 'opaque', cls);
      applyRenderState(state, cls, a, ov, 'opaque');
    }
    expect(state.alpha[2]).toBeCloseTo(r.targetAlpha.get(2)!, 3);
    expect(state.alpha[3]).toBe(1);
    expect(state.alpha[0]).toBe(1);
  });

  it('forces Far to 1 under scope near and in hidden far mode', () => {
    const state = createRenderState(model.elements.length);
    state.alpha.fill(0.4);
    let a = smoothAlpha(state.alpha, r.targetAlpha, new Map(), { ...DEFAULT_SIGHTLINES, occluderScope: 'near' }, 'opaque', cls);
    applyRenderState(state, cls, a, ov, 'opaque');
    expect(state.alpha[2]).toBe(1);
    state.alpha.fill(0.4);
    a = smoothAlpha(state.alpha, r.targetAlpha, new Map(), DEFAULT_SIGHTLINES, 'hidden', cls);
    applyRenderState(state, cls, a, ov, 'hidden');
    expect(state.alpha[2]).toBe(1);
    expect(state.flags[2]! & FLAG_HIDDEN).toBe(FLAG_HIDDEN);
  });
});

describe('tiers respect the scope with the tier own context', () => {
  const TIERS = [['IfcDuctSegment'], ['IfcBeam'], ['IfcSlab', 'IfcWall']];
  const { model, geometry } = scene();
  const tc = classifyTiers(model, geometry, [0], TIERS);

  it('Far walls get the farRank of tier 2 (the tier whose context holds them)', () => {
    expect(tc.rank.get(1)).toBe(2);
    expect(tc.farRank.get(2)).toBe(2);
    expect(tc.farRank.get(3)).toBe(2);
  });

  it('scope all ghosts the blocking Far wall with tierAlphaMin[2] and farWeight; scope near ignores it', () => {
    const s = { ...DEFAULT_TIER_SETTINGS, occluderScope: 'all' as const };
    const r = sightlinesTiered(tc, geometry, WEST, s);
    expect(r.occlusion.get(2)).toBeCloseTo(1, 9);
    expect(r.targetAlpha.get(2)).toBeCloseTo(1 + (0.15 - 1) * 0.7, 9);
    expect(r.targetAlpha.get(3)).toBe(1);
    const rn = sightlinesTiered(tc, geometry, WEST, { ...s, occluderScope: 'near' });
    expect(rn.targetAlpha.has(2)).toBe(false);
  });
});
