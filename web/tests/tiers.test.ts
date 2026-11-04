import { describe, expect, it } from 'vitest';
import { Vector3 } from 'three';
import { DEFAULT_CLASSIFICATION } from '../src/types';
import { DEFAULT_TIER_SETTINGS, classifyTiers, createRenderState, applyRenderState, smoothAlpha, sightlinesTiered } from '../src/algo';
import { makeScene } from './boxProvider';

const TIERS = [['IfcDuctSegment'], ['IfcBeam'], ['IfcSlab']];
const DUCT = 0;
const BEAM = 1;
const SLAB = 2;
const FAR_SLAB = 3;

// Y up. Duct 0.3 x 0.3 (buffer 0.45). Slab sits between the duct and a beam above it, so from a
// camera above: duct samples are hidden by slab and beam, beam samples are hidden by nothing.
function scene() {
  return makeScene([
    { cls: 'IfcDuctSegment', box: [0, 0, -0.15, 4, 0.3, 0.15] },
    { cls: 'IfcBeam', box: [0, 0.5, -0.2, 4, 0.8, 0.2] },
    { cls: 'IfcSlab', box: [-1, 0.35, -1, 5, 0.45, 1] },
    { cls: 'IfcSlab', box: [-1, 30, -1, 5, 30.2, 1] },
  ]);
}

describe('classifyTiers', () => {
  const { model, geometry } = scene();
  const tc = classifyTiers(model, geometry, [DUCT], TIERS, DEFAULT_CLASSIFICATION);

  it('ranks by tier using Focus = everything above', () => {
    expect(tc.rank.get(DUCT)).toBe(0);
    expect(tc.rank.get(BEAM)).toBe(1);
    expect(tc.rank.get(SLAB)).toBe(2);
    expect(tc.rank.has(FAR_SLAB)).toBe(false);
    expect(tc.tiers[2]!.focus).toEqual(new Set([DUCT, BEAM])); // tier 3 sees beams as focus
    expect(tc.flat.far.has(FAR_SLAB)).toBe(true);
    expect(tc.flat.focus).toEqual(new Set([DUCT]));
  });

  it('a slab only near a beam, not the duct, is still found through the beam', () => {
    const s = makeScene([
      { cls: 'IfcDuctSegment', box: [0, 0, -0.15, 4, 0.3, 0.15] },
      { cls: 'IfcBeam', box: [0, 0.5, -0.2, 4, 0.8, 0.2] },
      { cls: 'IfcSlab', box: [-1, 1.0, -1, 5, 1.2, 1] }, // 0.7 from duct, 0.2 from beam
    ]);
    const c = classifyTiers(s.model, s.geometry, [0], TIERS);
    expect(c.rank.get(2)).toBe(2);
    expect(c.flat.proximityWeight.get(2)!).toBeGreaterThan(0.5);
  });
});

describe('sightlinesTiered', () => {
  const { model, geometry } = scene();
  const tc = classifyTiers(model, geometry, [DUCT], TIERS);
  const camera = new Vector3(2, 10, 0);

  it('defaults are weights [1.0, 0.6] and alphaMin [1.0, 0.35, 0.15]', () => {
    expect(DEFAULT_TIER_SETTINGS.tierWeight).toEqual([1.0, 0.6]);
    expect(DEFAULT_TIER_SETTINGS.tierAlphaMin).toEqual([1.0, 0.35, 0.15]);
  });

  // These two tests pin the tier weights, so they use 'uniform' hit credit. Under the default 'front'
  // weighting the slab sits behind the beam for a camera above and its credit is halved.
  const UNIFORM = { ...DEFAULT_TIER_SETTINGS, layerWeighting: 'uniform' as const };

  it("default 'front' layer weighting halves the credit of the slab hidden behind the beam", () => {
    const r = sightlinesTiered(tc, geometry, camera, DEFAULT_TIER_SETTINGS);
    expect(r.occlusion.get(BEAM)).toBeCloseTo(1, 9);
    expect(r.occlusion.get(SLAB)).toBeCloseTo(0.5 * (64 / 102.4), 6);
  });

  it('only samples of lower rank count, weighted by tierWeight[sample rank]', () => {
    const r = sightlinesTiered(tc, geometry, camera, UNIFORM);
    // Beam is hit by every duct sample (rank 0) and by no beam sample (rank not < 1)
    expect(r.occlusion.get(BEAM)).toBeCloseTo(1, 9);
    // Slab: eligible = duct (w 1.0 x 64) + beam (w 0.6 x 64) = 102.4; hits = duct samples only = 64
    expect(r.occlusion.get(SLAB)).toBeCloseTo(64 / 102.4, 6);
  });

  it('changing tierWeight moves the slab occlusion as the weights say', () => {
    const r0 = sightlinesTiered(tc, geometry, camera, { ...UNIFORM, tierWeight: [1, 0] });
    expect(r0.occlusion.get(SLAB)).toBeCloseTo(1, 9);
    const r1 = sightlinesTiered(tc, geometry, camera, { ...UNIFORM, tierWeight: [1, 1] });
    expect(r1.occlusion.get(SLAB)).toBeCloseTo(0.5, 9);
  });

  it('target alpha uses tierAlphaMin[rank]', () => {
    const s = DEFAULT_TIER_SETTINGS;
    const r = sightlinesTiered(tc, geometry, camera, s);
    for (const id of [BEAM, SLAB]) {
      const rank = tc.rank.get(id)!;
      const imp = Math.sqrt(r.occlusion.get(id)!) * tc.flat.proximityWeight.get(id)!;
      expect(r.importance.get(id)).toBeCloseTo(imp, 9);
      expect(r.targetAlpha.get(id)).toBeCloseTo(s.alphaMax + (s.tierAlphaMin[rank]! - s.alphaMax) * imp, 9);
    }
    // each tier never goes below its own alphaMin
    expect(r.targetAlpha.get(BEAM)!).toBeGreaterThanOrEqual(0.35 - 1e-9);
    expect(r.targetAlpha.get(SLAB)!).toBeGreaterThanOrEqual(0.15 - 1e-9);
  });

  it('flat view works with smoothAlpha and applyRenderState', () => {
    const r = sightlinesTiered(tc, geometry, camera, DEFAULT_TIER_SETTINGS);
    const state = createRenderState(model.elements.length);
    for (let i = 0; i < 40; i++) {
      const alphas = smoothAlpha(state.alpha, r.targetAlpha, new Map(), DEFAULT_TIER_SETTINGS, 'opaque', tc.flat);
      applyRenderState(state, tc.flat, alphas, { userHides: new Set(), userPins: new Set(), projectPins: {} }, 'opaque');
    }
    expect(state.alpha[DUCT]).toBe(1);
    expect(state.alpha[SLAB]).toBeCloseTo(r.targetAlpha.get(SLAB)!, 3);
    expect(state.alpha[FAR_SLAB]).toBe(1);
  });
});
