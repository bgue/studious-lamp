// Small SceneModel builder for the sidebar tests (no geometry needed).
import type { ElementRecord, SceneModel } from '../src/types';

export interface Spec {
  cls: string;
  name?: string;
  storey: number | null;
  material?: string;
}

export function modelOf(
  specs: Spec[],
  storeys: Array<{ id: number; name: string; elevation: number }>,
  systems: Array<{ name: string; elements: number[] }> = [],
): SceneModel {
  const elements: ElementRecord[] = specs.map((s, id) => ({
    id,
    globalId: `G${id}`,
    ifcClass: s.cls,
    name: s.name,
    storey: s.storey,
    material: s.material,
    color: [0.7, 0.7, 0.7, 1],
    bounds: [id, 0, 0, id + 1, 1, 1],
  }));
  return {
    schema: 'xray-model/1',
    units: 'm',
    originShift: [0, 0, 0],
    storeys,
    elements,
    relations: { voids: [], fills: [], hosts: [], ports: [], systems },
    byGlobalId: new Map(elements.map((e) => [e.globalId, e.id])),
  };
}
