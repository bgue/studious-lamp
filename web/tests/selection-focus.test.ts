// Algorithm 1 L1 deviation: every selected element is Focus, whatever its class.
// ConnectedRun expansion still applies only to selected elements whose class is in focusClasses.

import { describe, expect, it } from 'vitest';
import { Vector3 } from 'three';
import { DEFAULT_CLASSIFICATION } from '../src/types';
import { classify, classifyTiers, createRenderState } from '../src/algo';
import { XrayController, defaultSettings } from '../src/controller';
import { makeScene } from './boxProvider';

// 0 furniture, 1 slab over it (0.2 m gap), 2 wall beside it, 3 distant slab, 4 duct, 5 duct joined by a port
const scene = () =>
  makeScene(
    [
      { cls: 'IfcFurniture', box: [0, 0, 0, 1, 0.5, 1], name: 'Chair' },
      { cls: 'IfcSlab', box: [-2, 0.7, -2, 3, 0.95, 3], name: 'Slab over' },
      { cls: 'IfcWall', box: [-2, 0, 1.2, 3, 2.5, 1.4], name: 'Wall beside' },
      { cls: 'IfcSlab', box: [-2, 40, -2, 3, 40.25, 3], name: 'Slab far' },
      { cls: 'IfcDuctSegment', box: [10, 0, 0, 12, 0.3, 0.3], name: 'Duct a' },
      { cls: 'IfcDuctSegment', box: [12, 0, 0, 14, 0.3, 0.3], name: 'Duct b' },
    ],
    { ports: [[4, 5]] },
  );

describe('selection always joins Focus', () => {
  it('selecting furniture yields Focus = {it}; the slab over it is Near', () => {
    const { model, geometry } = scene();
    const c = classify(model, geometry, [0], DEFAULT_CLASSIFICATION);
    expect([...c.focus]).toEqual([0]);
    expect(c.near.has(1)).toBe(true);
    expect(c.far.has(3)).toBe(true);
  });

  it('selecting a slab yields Focus = {slab}; a wall intersecting it is Host, other slabs are Context', () => {
    const { model, geometry } = scene();
    const c = classify(model, geometry, [1], DEFAULT_CLASSIFICATION);
    expect([...c.focus]).toEqual([1]);
    expect(c.host.has(2)).toBe(true); // wall [1.2..1.4] crosses the slab volume
    expect(c.proximityWeight.get(2)).toBe(1);
    expect(c.far.has(3)).toBe(true);
    expect(c.focus.has(3)).toBe(false);
  });

  it('a selected duct still expands along ports; a selected furniture next to it does not expand anything', () => {
    const { model, geometry } = scene();
    const c = classify(model, geometry, [4, 0], DEFAULT_CLASSIFICATION);
    expect([...c.focus].sort()).toEqual([0, 4, 5]);
    const c2 = classify(model, geometry, [0], DEFAULT_CLASSIFICATION);
    expect(c2.focus.has(4)).toBe(false);
  });

  it('ids outside the model are ignored', () => {
    const { model, geometry } = scene();
    const c = classify(model, geometry, [99, -1], DEFAULT_CLASSIFICATION);
    expect(c.focus.size).toBe(0);
  });

  it('the tiered classifier puts a selected element of any class into rank 0', () => {
    const { model, geometry } = scene();
    const tc = classifyTiers(model, geometry, [0], [['IfcDuctSegment'], ['IfcBeam'], ['IfcSlab', 'IfcWall']]);
    expect(tc.rank.get(0)).toBe(0);
    expect(tc.flat.focus.has(0)).toBe(true);
    expect(tc.rank.get(1)).toBe(2);
  });
});

describe('controller: selecting furniture or a slab gets the treatment', () => {
  const make = () => {
    const sc = scene();
    const state = createRenderState(sc.model.elements.length);
    const ctl = new XrayController(sc.model, sc.geometry, state, defaultSettings());
    return { ...sc, state, ctl };
  };

  it('the slab over a selected piece of furniture ghosts when the camera is above', () => {
    const { ctl, state } = make();
    ctl.setSelection([0]);
    ctl.updateSightlines(new Vector3(0.5, 8, 0.5));
    ctl.settle();
    expect(state.alpha[0]).toBe(1);
    expect(state.alpha[1]!).toBeLessThan(0.5);
    // from below the same slab does not block the view
    ctl.updateSightlines(new Vector3(0.5, -6, 0.5));
    ctl.settle();
    expect(state.alpha[1]!).toBeGreaterThan(0.8);
  });

  it('a selected slab is Focus and the wall through it is Host', () => {
    const { ctl, state } = make();
    ctl.setSelection([1]);
    ctl.updateSightlines(new Vector3(0.5, 8, 0.5));
    ctl.settle();
    expect(ctl.bucketOf(1)).toBe('focus');
    expect(ctl.bucketOf(2)).toBe('host');
    expect(state.alpha[1]).toBe(1);
  });
});
