// SPEC acceptance 4: the report's worked example on synthetic boxes (Y up).

import { describe, expect, it } from 'vitest';
import { Vector3 } from 'three';
import {
  DEFAULT_CLASSIFICATION,
  DEFAULT_OVERRIDES,
  DEFAULT_SIGHTLINES,
} from '../src/types';
import { classify, computeFloors, createRenderState, occluderSet, sightlines, smoothAlpha } from '../src/algo';
import { makeScene } from './boxProvider';

// The report's Algorithm 2: Host + Near are the only ray candidates.
const NEAR_ONLY = { ...DEFAULT_SIGHTLINES, occluderScope: 'near' as const };

const D1 = 0; // duct run, 8 m long, 0.6 x 0.3 section
const D1_RISER = 1; // the end of D1 that rises through S1
const S1 = 2;
const B1 = 3;
const W1 = 4;
const C1 = 5;
const S0 = 6;

function build() {
  return makeScene(
    [
      { cls: 'IfcDuctSegment', box: [0, 0, -0.3, 8, 0.3, 0.3], storey: 1, name: 'D1' },
      { cls: 'IfcDuctSegment', box: [7.4, 0.3, -0.15, 8.0, 1.5, 0.15], storey: 1, name: 'D1 riser' },
      { cls: 'IfcSlab', box: [-1, 0.6, -3, 9, 0.85, 3], storey: 1, name: 'S1' }, // 250 mm
      { cls: 'IfcBeam', box: [3.0, -0.8, -3, 3.4, -0.2, 3], storey: 1, name: 'B1' }, // 0.4 x 0.6, 200 mm below
      { cls: 'IfcWall', box: [-1, -2.5, 0.85, 9, 0.6, 1.05], storey: 1, name: 'W1' }, // 200 mm, 550 mm to the side
      { cls: 'IfcColumn', box: [3.8, -2.5, 3.3, 4.2, 0.6, 3.7], storey: 1, name: 'C1' }, // 3.0 m away
      { cls: 'IfcSlab', box: [-1, -3.45, -3, 9, -3.2, 3], storey: 0, name: 'S0' }, // 3.2 m below
    ],
    {
      storeys: [
        { id: 0, name: 'Level 0', elevation: -3.5 },
        { id: 1, name: 'Level 1', elevation: 0 },
      ],
      ports: [[D1, D1_RISER]],
      hosts: [[D1_RISER, S1]],
    },
  );
}

describe('worked example (SPEC acceptance 4)', () => {
  const { model, geometry } = build();
  const cls = classify(model, geometry, [D1], DEFAULT_CLASSIFICATION);

  it('Focus is the whole L-shaped run, reached through the port', () => {
    expect([...cls.focus].sort()).toEqual([D1, D1_RISER]);
  });

  it('buffer radius is 0.60 m for the 0.6 x 0.3 section', () => {
    expect(cls.bufferRadius.get(D1)).toBeCloseTo(0.6, 9);
    expect(cls.bufferRadius.get(D1_RISER)).toBeCloseTo(0.6, 9);
  });

  it('buckets', () => {
    expect([...cls.host]).toEqual([S1]);
    expect([...cls.near].sort()).toEqual([B1, W1]);
    expect([...cls.far].sort()).toEqual([C1, S0]);
  });

  it('proximity weights: S1 1.0, B1 0.741, W1 0.02', () => {
    expect(cls.proximityWeight.get(S1)).toBe(1);
    expect(cls.proximityWeight.get(B1)).toBeCloseTo(0.741, 2);
    expect(Math.abs(cls.proximityWeight.get(B1)! - 0.741)).toBeLessThan(0.01);
    expect(Math.abs(cls.proximityWeight.get(W1)! - 0.02)).toBeLessThan(0.01);
    expect(cls.proximityWeight.has(C1)).toBe(false);
    expect(cls.proximityWeight.has(S0)).toBe(false);
  });

  it('S0 is dropped from Context entirely when storeyBand is 0', () => {
    const c0 = classify(model, geometry, [D1], { ...DEFAULT_CLASSIFICATION, storeyBand: 0 });
    expect(c0.far.has(S0)).toBe(false);
    expect(c0.far.has(C1)).toBe(true);
  });

  it('Host also found by the geometric fallback when hosts is empty', () => {
    const noRel = build();
    noRel.model.relations.hosts = [];
    const c = classify(noRel.model, noRel.geometry, [D1], DEFAULT_CLASSIFICATION);
    expect([...c.host]).toEqual([S1]);
  });

  describe('sightlines from 6 m above the slab', () => {
    const camera = new Vector3(4, 0.85 + 6, 0);
    const res = sightlines(cls, geometry, camera, NEAR_ONLY);

    it('S1 occlusion is about 0.75 and target alpha about 0.24', () => {
      const occ = res.occlusion.get(S1)!;
      const target = res.targetAlpha.get(S1)!;
      expect(occ).toBeGreaterThanOrEqual(0.6);
      expect(occ).toBeLessThanOrEqual(0.9);
      expect(target).toBeGreaterThanOrEqual(0.15);
      expect(target).toBeLessThanOrEqual(0.35);
      // formula check
      const importance = Math.pow(occ, 0.5) * 1;
      expect(target).toBeCloseTo(0.85 + (0.15 - 0.85) * importance, 9);
    });

    it('W1 and B1 are not between the duct and the camera', () => {
      expect(res.occlusion.get(W1)).toBe(0);
      expect(res.occlusion.get(B1)).toBe(0);
      expect(res.targetAlpha.get(W1)).toBeCloseTo(0.85, 9);
    });

    it('scope all gives the same Host/Near numbers; C1 and S0 block nothing from above and stay at 1', () => {
      const all = sightlines(cls, geometry, camera, { ...DEFAULT_SIGHTLINES, occluderScope: 'all' });
      for (const id of [S1, B1, W1]) {
        expect(all.occlusion.get(id)).toBe(res.occlusion.get(id));
        expect(all.targetAlpha.get(id)).toBe(res.targetAlpha.get(id));
      }
      expect(all.occlusion.get(C1)).toBe(0);
      expect(all.targetAlpha.get(C1)).toBe(1);
      expect(all.targetAlpha.get(S0)).toBe(1);
      expect(res.targetAlpha.has(C1)).toBe(false); // scope near does not evaluate Far at all
    });

    it('alpha converges to the target within 0.02 after 20 steps at 0.2', () => {
      const state = createRenderState(model.elements.length);
      const floors = computeFloors(occluderSet(cls), model, DEFAULT_OVERRIDES);
      for (let i = 0; i < 20; i++) {
        smoothAlpha(state.alpha, res.targetAlpha, floors, NEAR_ONLY, 'opaque', cls);
      }
      expect(Math.abs(state.alpha[S1]! - res.targetAlpha.get(S1)!)).toBeLessThan(0.02);
      expect(state.alpha[D1]).toBe(1);
      expect(state.alpha[C1]).toBe(1);
      // Alpha moved monotonically from 1 towards the target: no overshoot.
      expect(state.alpha[S1]!).toBeGreaterThanOrEqual(res.targetAlpha.get(S1)!);
    });
  });
});
