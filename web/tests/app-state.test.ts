// Non-DOM app state: XrayController driven by the box mock (same scene as the worked example).

import { describe, expect, it } from 'vitest';
import { Vector3 } from 'three';
import { FLAG_FOCUS, FLAG_HIDDEN, FLAG_PINNED, FLAG_SELECTED } from '../src/types';
import { createRenderState } from '../src/algo';
import { XrayController, defaultSettings } from '../src/controller';
import { makeScene } from './boxProvider';

const D1 = 0;
const D1_RISER = 1;
const S1 = 2;
const B1 = 3;
const W1 = 4;
const C1 = 5;
const S0 = 6;

function build() {
  const scene = makeScene(
    [
      { cls: 'IfcDuctSegment', box: [0, 0, -0.3, 8, 0.3, 0.3], storey: 1, name: 'D1' },
      { cls: 'IfcDuctSegment', box: [7.4, 0.3, -0.15, 8.0, 1.5, 0.15], storey: 1, name: 'D1 riser' },
      { cls: 'IfcSlab', box: [-1, 0.6, -3, 9, 0.85, 3], storey: 1, name: 'S1' },
      { cls: 'IfcBeam', box: [3.0, -0.8, -3, 3.4, -0.2, 3], storey: 1, name: 'B1' },
      { cls: 'IfcWall', box: [-1, -2.5, 0.85, 9, 0.6, 1.05], storey: 1, name: 'W1' },
      { cls: 'IfcColumn', box: [3.8, -2.5, 3.3, 4.2, 0.6, 3.7], storey: 1, name: 'C1' },
      { cls: 'IfcSlab', box: [-1, -3.45, -3, 9, -3.2, 3], storey: 0, name: 'S0' },
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
  const state = createRenderState(scene.model.elements.length);
  const ctl = new XrayController(scene.model, scene.geometry, state, defaultSettings());
  return { ...scene, state, ctl };
}

const ABOVE = new Vector3(4, 0.85 + 6, 0);
// Camera 1.5 m beyond the column C1 (z 3.3..3.7), on the line through the middle of the duct run.
const BEHIND_COLUMN = new Vector3(4, 0.15, 5);
const BELOW_SIDE = new Vector3(4, -0.5, 10); // nothing between this camera and the duct except air

describe('XrayController', () => {
  it('selecting the duct ghosts the slab towards its target and leaves the column opaque after 30 ticks', () => {
    const { ctl, state } = build();
    ctl.setSelection([D1]);
    ctl.updateSightlines(ABOVE);
    for (let i = 0; i < 30; i++) ctl.tick();

    const target = ctl.targets.get(S1)!;
    expect(target).toBeGreaterThanOrEqual(0.15);
    expect(target).toBeLessThanOrEqual(0.35);
    expect(Math.abs(state.alpha[S1]! - target)).toBeLessThan(0.01);
    expect(state.alpha[C1]).toBe(1);
    expect(state.alpha[S0]).toBe(1);
    expect(state.alpha[D1]).toBe(1);
    expect((state.flags[D1]! & FLAG_FOCUS) !== 0).toBe(true);
    expect((state.flags[D1_RISER]! & FLAG_FOCUS) !== 0).toBe(true);
    expect((state.flags[D1]! & FLAG_SELECTED) !== 0).toBe(true);
    expect(ctl.converged).toBe(true);
  });

  it('classification, buckets and stats are recorded', () => {
    const { ctl } = build();
    ctl.setSelection([D1]);
    ctl.updateSightlines(ABOVE);
    expect(ctl.bucketOf(S1)).toBe('host');
    expect(ctl.bucketOf(B1)).toBe('near');
    expect(ctl.bucketOf(C1)).toBe('far');
    expect(ctl.stats.buckets).toEqual({ focus: 2, host: 1, near: 2, far: 2 });
    expect(ctl.stats.classifyCount).toBe(1);
    expect(ctl.stats.classifyMs).toBeGreaterThanOrEqual(0);
    // 500-sample budget shared by two focus elements, 64 per object max: 128 rays.
    expect(ctl.stats.rays).toBe(128);
    expect(ctl.stats.sightlinesCount).toBe(1);
    const info = ctl.describe(S1)!;
    expect(info.bucket).toBe('host');
    expect(info.proximityWeight).toBe(1);
    expect(info.occlusion).toBeGreaterThan(0.5);
  });

  it('stops doing work once converged, and wakes up when the camera target changes', () => {
    const { ctl } = build();
    ctl.setSelection([D1]);
    ctl.updateSightlines(ABOVE);
    expect(ctl.settle()).toBeLessThan(60);
    expect(ctl.tick()).toBe(false);
    ctl.updateSightlines(BELOW_SIDE);
    expect(ctl.converged).toBe(false);
    expect(ctl.tick()).toBe(true);
  });

  it('moving the camera away from the slab fades it back up without jumping', () => {
    const { ctl, state } = build();
    ctl.setSelection([D1]);
    ctl.updateSightlines(ABOVE);
    ctl.settle();
    const low = state.alpha[S1]!;
    ctl.updateSightlines(new Vector3(4, 0.4, 20)); // level with the duct run, far to the side
    const target = ctl.targets.get(S1)!;
    expect(target).toBeGreaterThan(low + 0.1);
    ctl.tick();
    const step = state.alpha[S1]! - low;
    expect(step).toBeGreaterThan(0);
    expect(step).toBeLessThanOrEqual(0.2 * (target - low) + 1e-6); // one smoothing step, no jump
    ctl.settle();
    expect(state.alpha[S1]!).toBeCloseTo(target, 2);
  });

  it('clearing the selection returns everything to opaque, easing rather than popping', () => {
    const { ctl, state } = build();
    ctl.setSelection([D1]);
    ctl.updateSightlines(ABOVE);
    ctl.settle();
    const ghosted = state.alpha[S1]!;
    expect(ghosted).toBeLessThan(0.4);
    ctl.clearSelection();
    ctl.updateSightlines(ABOVE);
    ctl.tick();
    expect(state.alpha[S1]!).toBeGreaterThan(ghosted);
    expect(state.alpha[S1]!).toBeLessThan(1);
    ctl.settle();
    expect(state.alpha[S1]).toBe(1);
    expect(state.flags[D1]! & FLAG_FOCUS).toBe(0);
    expect(ctl.stats.buckets.focus).toBe(0);
  });

  it('selecting a non-focus-class element (a slab) makes it Focus: opaque, flagged, others become Context', () => {
    const { ctl, state } = build();
    ctl.setSelection([S1]);
    ctl.updateSightlines(ABOVE);
    ctl.settle();
    expect([...ctl.classification.focus]).toEqual([S1]);
    expect(state.alpha[S1]).toBe(1);
    expect((state.flags[S1]! & FLAG_FOCUS) !== 0).toBe(true);
    expect((state.flags[S1]! & FLAG_SELECTED) !== 0).toBe(true);
    // The duct passes through the slab; it is not in ctxClasses, so it is neither Focus nor Context.
    expect(ctl.bucketOf(D1)).toBe('none');
    expect(ctl.bucketOf(S0)).toBe('far');
  });

  it('pin floor keeps a pinned occluder at or above userPinFloor', () => {
    const { ctl, state } = build();
    ctl.setSelection([D1]);
    ctl.updateSightlines(ABOVE);
    ctl.settle();
    expect(state.alpha[S1]!).toBeLessThan(0.4);
    ctl.setSelection([S1]); // a selected slab is Focus, so pin it first, then go back to the duct
    ctl.pinSelected();
    ctl.setSelection([D1]);
    ctl.updateSightlines(ABOVE);
    ctl.settle();
    expect(state.alpha[S1]!).toBeGreaterThanOrEqual(ctl.settings.overrides.userPinFloor - 1e-3);
    expect((state.flags[S1]! & FLAG_PINNED) !== 0).toBe(true);
  });

  it('hide sets the hidden flag, and clearing pins/hides removes it', () => {
    const { ctl, state } = build();
    ctl.setSelection([D1]);
    ctl.updateSightlines(ABOVE);
    ctl.settle();
    ctl.setSelection([B1]);
    ctl.hideSelected();
    ctl.setSelection([D1]);
    ctl.updateSightlines(ABOVE);
    ctl.tick();
    expect((state.flags[B1]! & FLAG_HIDDEN) !== 0).toBe(true);
    ctl.clearPinsAndHides();
    ctl.tick();
    expect((state.flags[B1]! & FLAG_HIDDEN) !== 0).toBe(false);
  });

  it('column alpha 1 from above, but ghosts when it sits between the camera and the duct (scope all)', () => {
    const { ctl, state } = build();
    ctl.setSelection([D1]);
    ctl.updateSightlines(ABOVE);
    ctl.settle();
    expect(state.alpha[C1]).toBe(1);
    expect(ctl.bucketOf(C1)).toBe('far');

    ctl.updateSightlines(BEHIND_COLUMN);
    expect(ctl.describe(C1)!.occlusion).toBeGreaterThan(0.05);
    ctl.settle();
    expect(state.alpha[C1]!).toBeLessThan(0.9);
    // weighted by farWeight, never below the Far floor 1 + (alphaMin - 1) * farWeight
    expect(state.alpha[C1]!).toBeGreaterThanOrEqual(1 + (0.15 - 1) * 0.7 - 1e-6);
    const occ = ctl.describe(C1)!.occlusion;
    expect(ctl.targets.get(C1)!).toBeCloseTo(1 + (0.15 - 1) * (Math.sqrt(occ) * 0.7), 9);
    expect(ctl.converged).toBe(true);

    // back above: it eases back to opaque
    ctl.updateSightlines(ABOVE);
    ctl.settle();
    expect(state.alpha[C1]).toBeCloseTo(1, 2);
  });

  it('scope near keeps Far opaque from the same camera, and switching scope back and forth does not pop', () => {
    const { ctl, state } = build();
    ctl.settings.sightlines.occluderScope = 'near';
    ctl.setSelection([D1]);
    ctl.updateSightlines(BEHIND_COLUMN);
    ctl.settle();
    expect(state.alpha[C1]).toBe(1);
    expect(ctl.targets.has(C1)).toBe(false);

    ctl.settings.sightlines.occluderScope = 'all';
    ctl.updateSightlines(BEHIND_COLUMN);
    ctl.settle();
    const ghosted = state.alpha[C1]!;
    expect(ghosted).toBeLessThan(0.9);

    ctl.settings.sightlines.occluderScope = 'near';
    ctl.updateSightlines(BEHIND_COLUMN);
    ctl.tick();
    expect(state.alpha[C1]!).toBeGreaterThan(ghosted); // eases up
    expect(state.alpha[C1]!).toBeLessThan(1);
    ctl.settle();
    expect(state.alpha[C1]).toBe(1);
  });

  it('farWeight 0 leaves Far opaque; far mode hidden hides it instead of ghosting', () => {
    const { ctl, state } = build();
    ctl.settings.sightlines.farWeight = 0;
    ctl.setSelection([D1]);
    ctl.updateSightlines(BEHIND_COLUMN);
    ctl.settle();
    expect(state.alpha[C1]).toBe(1);

    ctl.settings.sightlines.farWeight = 0.7;
    ctl.settings.farMode = 'hidden';
    ctl.touch();
    ctl.updateSightlines(BEHIND_COLUMN);
    ctl.settle();
    expect(state.alpha[C1]).toBe(1);
    expect((state.flags[C1]! & FLAG_HIDDEN) !== 0).toBe(true);
  });

  it('a pinned Far element keeps its pin floor while it ghosts', () => {
    const { ctl, state } = build();
    ctl.setSelection([C1]);
    ctl.pinSelected();
    ctl.setSelection([D1]);
    ctl.updateSightlines(BEHIND_COLUMN);
    ctl.settle();
    expect(state.alpha[C1]!).toBeGreaterThanOrEqual(ctl.settings.overrides.userPinFloor - 1e-3);
  });

  it('far mode hidden flags far elements, opaque does not', () => {
    const { ctl, state } = build();
    ctl.setSelection([D1]);
    ctl.updateSightlines(ABOVE);
    ctl.tick();
    expect(state.flags[C1]! & FLAG_HIDDEN).toBe(0);
    ctl.settings.farMode = 'hidden';
    ctl.touch();
    ctl.tick();
    expect((state.flags[C1]! & FLAG_HIDDEN) !== 0).toBe(true);
    expect((state.flags[S0]! & FLAG_HIDDEN) !== 0).toBe(true);
    expect(state.flags[S1]! & FLAG_HIDDEN).toBe(0);
  });

  it('x-ray off: everything opaque, no focus flags; on again re-ghosts', () => {
    const { ctl, state } = build();
    ctl.setSelection([D1]);
    ctl.updateSightlines(ABOVE);
    ctl.settle();
    ctl.settings.xray = false;
    ctl.reclassify();
    expect(ctl.tick()).toBe(true);
    expect(state.alpha[S1]).toBe(1);
    expect(state.flags[D1]! & FLAG_FOCUS).toBe(0);
    expect((state.flags[D1]! & FLAG_SELECTED) !== 0).toBe(true);
    expect(ctl.tick()).toBe(false);
    ctl.settings.xray = true;
    ctl.reclassify();
    ctl.updateSightlines(ABOVE);
    ctl.settle();
    expect(state.alpha[S1]!).toBeLessThan(0.4);
  });

  it('tiers mode ranks beam above slab and ghosts the slab more than the beam', () => {
    const { ctl, state } = build();
    ctl.settings.tiersMode = true;
    ctl.setSelection([D1]);
    ctl.updateSightlines(ABOVE);
    ctl.settle();
    expect(ctl.tiered).not.toBeNull();
    expect(ctl.tiered!.rank.get(D1)).toBe(0);
    expect(ctl.tiered!.rank.get(B1)).toBe(1);
    expect(ctl.tiered!.rank.get(S1)).toBe(2);
    expect(state.alpha[S1]!).toBeLessThan(0.5);
    expect(state.alpha[C1]).toBe(1);
  });
});
