// Algorithm 7: opacity floors from pins and hides.
//
// The viewpoint rules of the report (floor plate underfoot, exterior wall) are
// not implemented; `extraFloor` is the hook where they would plug in.

import {
  HIDDEN,
  type ElementId,
  type OverrideSettings,
  type SceneModel,
} from '../types';

export interface FloorContext {
  /** Extra floor for an element (e.g. a viewpoint rule). Combined with the others by max. */
  extraFloor?: (id: ElementId) => number;
  /**
   * Floor from the class styles (classStyles.floor, resolved per element). When it returns a
   * number it replaces overrides.categoryFloors[ifcClass] for that element, so
   * categoryFloors stays the fallback for classes without a style floor.
   */
  styleFloor?: (id: ElementId) => number | undefined;
}

/**
 * Floor per occluder. `HIDDEN` when the user hid it, otherwise the max of the
 * category floor (the class-style floor when the class has one), the project pin, the user pin floor (if pinned) and the
 * optional extra floor. Elements with no rule get 0.
 */
export function computeFloors(
  occluders: Iterable<ElementId>,
  model: SceneModel,
  overrides: OverrideSettings,
  context?: FloorContext,
): Map<ElementId, number> {
  const floors = new Map<ElementId, number>();
  for (const id of occluders) {
    if (overrides.userHides.has(id)) {
      floors.set(id, HIDDEN);
      continue;
    }
    const cls = model.elements[id]?.ifcClass;
    let floor = 0;
    const styleFloor = context?.styleFloor?.(id);
    if (styleFloor !== undefined) floor = Math.max(floor, styleFloor);
    else if (cls !== undefined) floor = Math.max(floor, overrides.categoryFloors[cls] ?? 0);
    floor = Math.max(floor, overrides.projectPins[id] ?? 0);
    if (overrides.userPins.has(id)) floor = Math.max(floor, overrides.userPinFloor);
    if (context?.extraFloor) floor = Math.max(floor, context.extraFloor(id));
    floors.set(id, Math.min(1, Math.max(0, floor)));
  }
  return floors;
}
