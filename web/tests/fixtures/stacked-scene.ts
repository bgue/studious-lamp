// Stacked-occluder fixture: a duct under three 250 mm slabs, 300 mm apart, camera straight above.
// Y is up. Shared by the algorithm tests and handed to the renderer work (OIT layer separation):
// `boxes` are the bounds in the glb frame, `model` is a SceneModel, `geometry` a box ray caster.

import { Vector3 } from 'three';
import type { SceneModel } from '../../src/types';
import { BoxGeometryProvider, makeScene, type BoxTuple } from '../boxProvider';

export const STACK_IDS = { duct: 0, bottom: 1, middle: 2, top: 3 } as const;

export interface StackedScene {
  model: SceneModel;
  geometry: BoxGeometryProvider;
  ids: typeof STACK_IDS;
  /** Element id -> [minx, miny, minz, maxx, maxy, maxz]. */
  boxes: Record<number, BoxTuple>;
  /** 3 m of Y above the top slab's upper face, over the duct's centre. */
  camera: Vector3;
}

export interface StackedSceneOptions {
  /**
   * Which slabs are Host of the duct through the hosts relation. Default: all three, so every slab
   * has proximity weight 1 and only the layer credit separates their alphas. A slab that is not
   * listed is Near or Far by distance (the middle and top slabs are Far with the default buffer).
   */
  hosts?: Array<'bottom' | 'middle' | 'top'>;
}

/** Slab thickness 0.25 m, gap between slab faces 0.30 m, lowest slab 0.5 m above the duct top (0.3). */
export function stackedBoxes(): Record<number, BoxTuple> {
  const slab = (y0: number): BoxTuple => [-3, y0, -3, 7, y0 + 0.25, 3];
  return {
    [STACK_IDS.duct]: [0, 0, -0.15, 4, 0.3, 0.15], // 0.6 x 0.3 section: buffer radius 0.6 m
    [STACK_IDS.bottom]: slab(0.5),
    [STACK_IDS.middle]: slab(1.05),
    [STACK_IDS.top]: slab(1.6),
  };
}

export function buildStackedScene(opts: StackedSceneOptions = {}): StackedScene {
  const boxes = stackedBoxes();
  const hosts = opts.hosts ?? ['bottom', 'middle', 'top'];
  const { model, geometry } = makeScene(
    [
      { cls: 'IfcDuctSegment', box: boxes[STACK_IDS.duct]!, name: 'Duct' },
      { cls: 'IfcSlab', box: boxes[STACK_IDS.bottom]!, name: 'Slab bottom' },
      { cls: 'IfcSlab', box: boxes[STACK_IDS.middle]!, name: 'Slab middle' },
      { cls: 'IfcSlab', box: boxes[STACK_IDS.top]!, name: 'Slab top' },
    ],
    { hosts: hosts.map((h) => [STACK_IDS.duct, STACK_IDS[h]] as [number, number]) },
  );
  const topY = boxes[STACK_IDS.top]![4]!;
  return { model, geometry, ids: STACK_IDS, boxes, camera: new Vector3(2, topY + 3, 0) };
}
