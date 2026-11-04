// Algorithm 1 (static classification) with Algorithm 3 (coarse-to-fine filtering).
//
// Line numbers in the comments (L1..L10) refer to the numbered lines of the
// report's Algorithm 1 listing.

import type { Box3 } from 'three';
import {
  DEFAULT_CLASSIFICATION,
  type Classification,
  type ClassificationSettings,
  type ElementId,
  type GeometryProvider,
  type SceneModel,
} from '../types';

/** Euclidean distance between two AABBs (0 when they touch or overlap). Algorithm 3, coarse stage. */
export function boxDistance(a: Box3, b: Box3): number {
  const dx = Math.max(0, a.min.x - b.max.x, b.min.x - a.max.x);
  const dy = Math.max(0, a.min.y - b.max.y, b.min.y - a.max.y);
  const dz = Math.max(0, a.min.z - b.max.z, b.min.z - a.max.z);
  return Math.sqrt(dx * dx + dy * dy + dz * dz);
}

/** Second-largest extent of the bounds: the largest is the run length, the next is the cross section. */
export function crossSection(b: Box3): number {
  const x = b.max.x - b.min.x;
  const y = b.max.y - b.min.y;
  const z = b.max.z - b.min.z;
  const max = Math.max(x, y, z);
  const min = Math.min(x, y, z);
  return x + y + z - max - min;
}

/** L4: bufferRadius(f) = clamp(bufferBase + bufferScale * crossSection(f), bufferLo, bufferHi). */
export function bufferRadius(b: Box3, s: ClassificationSettings): number {
  const r = s.bufferBase + s.bufferScale * crossSection(b);
  return Math.min(s.bufferHi, Math.max(s.bufferLo, r));
}

/** Smoothstep ease used for the Near falloff: 3d^2 - 2d^3. */
export function ease(d: number): number {
  const c = Math.min(1, Math.max(0, d));
  return 3 * c * c - 2 * c * c * c;
}

/**
 * L1 (connected run): selected elements in focusClasses plus their connected run.
 * `classify` additionally adds every selected element regardless of class.
 *
 * Traversal follows relations.ports transitively, and adds every member of any
 * system that contains a selected (seed) element. Everything added is
 * restricted to `focusClasses`; the walk does not pass through elements of
 * other classes (an air handling unit does not join two separate runs).
 */
export function connectedRun(
  model: SceneModel,
  selection: Iterable<ElementId>,
  focusClasses: ReadonlySet<string>,
): Set<ElementId> {
  const elements = model.elements;
  const inFocusClass = (id: ElementId): boolean => {
    const e = elements[id];
    return e !== undefined && focusClasses.has(e.ifcClass);
  };

  const run = new Set<ElementId>();
  const queue: ElementId[] = [];
  const add = (id: ElementId): void => {
    if (!run.has(id) && inFocusClass(id)) {
      run.add(id);
      queue.push(id);
    }
  };

  const seeds: ElementId[] = [];
  for (const id of selection) if (inFocusClass(id)) seeds.push(id);
  for (const id of seeds) add(id);
  if (seeds.length === 0) return run;

  // Systems containing a seed contribute all their focus-class members.
  const seedSet = new Set(seeds);
  for (const sys of model.relations.systems) {
    if (sys.elements.some((id) => seedSet.has(id))) for (const id of sys.elements) add(id);
  }

  // Ports adjacency, transitive.
  const adj = new Map<ElementId, ElementId[]>();
  for (const [a, b] of model.relations.ports) {
    let la = adj.get(a);
    if (!la) adj.set(a, (la = []));
    la.push(b);
    let lb = adj.get(b);
    if (!lb) adj.set(b, (lb = []));
    lb.push(a);
  }
  for (let i = 0; i < queue.length; i++) {
    const next = adj.get(queue[i]!);
    if (next) for (const n of next) add(n);
  }
  return run;
}

/** Add every valid selected id to `focus`, whatever its class. */
export function addSelected(model: SceneModel, selection: Iterable<ElementId>, focus: Set<ElementId>): void {
  for (const id of selection) if (model.elements[id] !== undefined) focus.add(id);
}

/** Position of each storey id when ordered by elevation, so that "adjacent" survives gaps in ids. */
function storeyRanks(model: SceneModel): Map<number, number> {
  const sorted = [...model.storeys].sort((a, b) => a.elevation - b.elevation || a.id - b.id);
  const m = new Map<number, number>();
  sorted.forEach((s, i) => m.set(s.id, i));
  return m;
}

/**
 * Algorithm 1 from a precomputed Focus set (L2..L10). Used directly by the
 * tier classifier, where Focus is "everything ranked above".
 */
export function classifyFromFocus(
  model: SceneModel,
  geometry: GeometryProvider,
  focus: ReadonlySet<ElementId>,
  settings: ClassificationSettings = DEFAULT_CLASSIFICATION,
): Classification {
  const result: Classification = {
    focus: new Set(focus),
    host: new Set(),
    near: new Set(),
    far: new Set(),
    proximityWeight: new Map(),
    bufferRadius: new Map(),
  };
  if (focus.size === 0) return result;

  const fIds = [...focus];
  const fBox = fIds.map((id) => geometry.bounds(id));
  const fRadius = fBox.map((b) => bufferRadius(b, settings));
  fIds.forEach((id, i) => result.bufferRadius.set(id, fRadius[i]!));

  // L2: Context = ctx classes, not Focus, within storeyBand of a Focus storey.
  const ranks = storeyRanks(model);
  const rankOf = (storey: number): number => ranks.get(storey) ?? storey;
  const focusStoreys = new Set<number>();
  for (const id of fIds) {
    const st = model.elements[id]?.storey;
    if (st !== null && st !== undefined) focusStoreys.add(rankOf(st));
  }
  const useStoreyFilter = focusStoreys.size > 0;
  const ctxClasses = new Set(settings.ctxClasses);

  // hosts relation: filler -> set of hosts
  const hostsOf = new Map<ElementId, Set<ElementId>>();
  for (const [filler, host] of model.relations.hosts) {
    let s = hostsOf.get(filler);
    if (!s) hostsOf.set(filler, (s = new Set()));
    s.add(host);
  }

  for (const c of model.elements) {
    if (focus.has(c.id) || !ctxClasses.has(c.ifcClass)) continue;
    if (useStoreyFilter && c.storey !== null) {
      const cr = rankOf(c.storey);
      let ok = false;
      for (const fr of focusStoreys) {
        if (Math.abs(cr - fr) <= settings.storeyBand) {
          ok = true;
          break;
        }
      }
      if (!ok) continue;
    }

    const cBox = geometry.bounds(c.id);
    let isHost = false;
    let bestRatio = Infinity; // min over f of surfaceDistance / bufferRadius(f)
    for (let i = 0; i < fIds.length; i++) {
      const f = fIds[i]!;
      const gap = boxDistance(fBox[i]!, cBox); // Algorithm 3: coarse AABB stage
      // L3: Host by relation, else (fallback) bounds overlap and mesh intersection.
      if (hostsOf.get(f)?.has(c.id)) {
        isHost = true;
        break;
      }
      if (gap === 0 && geometry.intersects(f, c.id)) {
        isHost = true;
        break;
      }
      // L4: Near candidate, only if the AABB gap is inside the buffer (mesh stage).
      const r = fRadius[i]!;
      if (gap <= r) {
        const sd = geometry.surfaceDistance(f, c.id);
        if (sd <= r) bestRatio = Math.min(bestRatio, r > 0 ? sd / r : 0);
      }
    }

    if (isHost) {
      result.host.add(c.id);
      result.proximityWeight.set(c.id, 1); // L6-7
    } else if (bestRatio !== Infinity) {
      result.near.add(c.id);
      result.proximityWeight.set(c.id, 1 - ease(bestRatio)); // L8-10
    } else {
      result.far.add(c.id); // L5
    }
  }
  return result;
}

/**
 * L1: Focus = every selected element, whatever its class (explicit selection is intent; this
 * deviates from the report, which drops selected elements outside focusClasses), plus the
 * connected run of the selected elements whose class is in focusClasses (ports and systems).
 * Context then excludes the whole Focus set, so selecting a slab makes the other slabs and walls
 * Context.
 */
export function classify(
  model: SceneModel,
  geometry: GeometryProvider,
  selection: Iterable<ElementId>,
  settings: ClassificationSettings = DEFAULT_CLASSIFICATION,
): Classification {
  const sel = [...selection];
  const focus = connectedRun(model, sel, new Set(settings.focusClasses));
  addSelected(model, sel, focus);
  return classifyFromFocus(model, geometry, focus, settings);
}
