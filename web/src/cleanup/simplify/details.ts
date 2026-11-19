// Remove small details: whole elements, or separable pieces of an element, below a size or volume threshold, with an
// IFC class filter (fasteners, screws, small fittings). Pure over element bounds.

import type { Bounds6 } from '../analysis';
import { boundsVolume, largestDimension } from '../analysis';

export interface DetailItem {
  id: number;
  ifcClass: string;
  bounds: Bounds6;
  /** Triangles; elements without triangles are skipped. */
  triangles?: number;
}

export interface DetailOptions {
  /** Metres: the largest bounds dimension is below this. 0 switches the size test off. */
  maxSize: number;
  /** m³: the bounds volume is below this. 0 switches the volume test off. */
  maxVolume: number;
  /** When not empty, only these classes are candidates. */
  classes: readonly string[];
  /** Also cut separable pieces (connected sub-meshes) smaller than maxSize out of larger elements. */
  subMeshes: boolean;
}

export const DETAIL_CLASSES = ['IfcFastener', 'IfcMechanicalFastener', 'IfcDiscreteAccessory'];

export function defaultDetailOptions(): DetailOptions {
  return { maxSize: 0.05, maxVolume: 0, classes: [], subMeshes: false };
}

export function isSmallDetail(it: DetailItem, o: DetailOptions): boolean {
  if (it.triangles !== undefined && it.triangles <= 0) return false;
  if (o.classes.length > 0 && !o.classes.includes(it.ifcClass)) return false;
  if (!(o.maxSize > 0) && !(o.maxVolume > 0)) return false;
  const b = it.bounds;
  if (!b.every(Number.isFinite)) return false;
  if (o.maxSize > 0 && largestDimension(b) < o.maxSize) return true;
  if (o.maxVolume > 0 && boundsVolume(b) < o.maxVolume) return true;
  return false;
}

/** Ids of the elements to remove, ascending. */
export function findSmallDetails(items: readonly DetailItem[], o: DetailOptions): number[] {
  const out: number[] = [];
  for (const it of items) if (isSmallDetail(it, o)) out.push(it.id);
  return out.sort((a, b) => a - b);
}
