// Placement facet, the geometric part: is an element on the outside of the building, on its envelope, or inside it?
// Pure and framework-free: the viewer supplies a ray caster over the BVH it already has, tests supply a brute-force one.
// Design: docs/design/classification-facets.md section 5. User docs: docs-features/classify.md, "Facets".
//
// Frame: the viewer's, y up. Rays are horizontal (in the x-z plane).
//
//   - Envelope elements (walls, curtain walls, windows, doors): a ray from the element's middle along each face normal. One side
//     clear (nothing of the envelope set in the way) and the other blocked is BOUNDARY; both blocked is INT; both clear is EXT
//     (a free-standing wall). Three sample points along the element vote, so a window in the wall behind does not decide alone.
//     A wall whose face lies on the outline of its storey's plan is BOUNDARY even when a neighbouring wing blocks the ray.
//   - Roofs, and slabs at the top or bottom of the building: BOUNDARY. Other slabs: INT. Footings and piles: EXT (outside the envelope).
//   - Everything else: a point outside the plan outline of its storey is EXT; inside it, 8 horizontal rays against the envelope set:
//     none clear is INT, most clear is EXT, in between BOUNDARY with a low confidence.
//
// Cost: at most 8 rays per element, only against the envelope set; `probeAll` works in slices so the page stays responsive.

export type Box6 = readonly [number, number, number, number, number, number];
export type Exposure = 'EXT' | 'INT' | 'BOUNDARY';

/** Ray caster: the ids of the candidate elements whose surface the segment origin -> origin + dir * maxDistance crosses (any order; self is not excluded). */
export type RayHits = (origin: readonly [number, number, number], dir: readonly [number, number, number], maxDistance: number, candidates: ReadonlySet<number>) => Iterable<number>;

export interface PlacementElement {
  id: number;
  ifcClass: string;
  bounds: Box6;
  storey: number | null;
  predefinedType?: string;
}

export interface PlacementGeoOptions {
  elements: readonly PlacementElement[];
  castHits: RayHits;
  /** Fillers (doors, windows) hosted in a wall, by the wall's id: they do not count as blocking that wall's own rays. */
  hostedBy?: (id: number) => readonly number[];
  /** The wall hosting a filler, or undefined. A filler's rays ignore its host. */
  hostOf?: (id: number) => number | undefined;
  /** Unit normal of a planar element in plan, viewer axes (x, z), from the orientation measure. Absent: the shorter horizontal side of the box. */
  normalOf?: (id: number) => readonly [number, number] | null | undefined;
}

export interface PlacementGeo {
  exposure: Exposure;
  confidence: number;
  rationale: string;
}

const WALL = /^IfcWall|^IfcCurtainWall$/;
const ENVELOPE_CLASS = /^IfcWall|^IfcCurtainWall$|^IfcWindow$|^IfcDoor$|^IfcRoof$/;
/** Classes whose triangles can block a horizontal ray as part of the envelope. */
export const isEnvelopeClass = (c: string): boolean => ENVELOPE_CLASS.test(c);
const isFiller = (c: string): boolean => c === 'IfcWindow' || c === 'IfcDoor';
const isSlab = (c: string): boolean => /^IfcSlab/.test(c);
const isRoofLike = (e: PlacementElement): boolean => e.ifcClass === 'IfcRoof' || (isSlab(e.ifcClass) && /ROOF/i.test(e.predefinedType ?? ''));
const isFooting = (c: string): boolean => c === 'IfcFooting' || c === 'IfcPile' || c === 'IfcPileType';

const SAMPLES = [0.2, 0.5, 0.8] as const;
/** Heights of the sample points, as a fraction of the element's height (a gable wall has no wall at mid height at its ends). */
const LEVELS = [0.35, 0.65] as const;
const EIGHT: ReadonlyArray<readonly [number, number]> = Array.from({ length: 8 }, (_, k) => [Math.cos((k * Math.PI) / 4), Math.sin((k * Math.PI) / 4)] as const);

interface Outline {
  min: [number, number];
  max: [number, number];
}

export interface PlacementProbe {
  /** The exposure of one element, or null when it has no box. */
  probe(id: number): PlacementGeo | null;
  /** All the given ids (default: every element) in slices of about `sliceMs`; `yieldFn` is awaited between slices. Calls `onProgress(done, total)`. */
  probeAll(ids: readonly number[] | undefined, o?: { sliceMs?: number; yieldFn?: () => Promise<void>; signal?: AbortSignal; onProgress?: (done: number, total: number) => void }): Promise<Map<number, PlacementGeo>>;
  /** The building's box (envelope elements and slabs), viewer axes, or null when there is none. */
  readonly building: Box6 | null;
}

const empty = (b: Box6): boolean => !(b[3] >= b[0] && b[4] >= b[1] && b[5] >= b[2]) || ![...b].every(Number.isFinite);

/** Build a probe over the elements of a model. Cheap to create: one pass for the envelope set and the outlines. */
export function createPlacementProbe(o: PlacementGeoOptions): PlacementProbe {
  const byId = new Map<number, PlacementElement>();
  const envelope = new Set<number>();
  const outlines = new Map<number | null, Outline>();
  let bx0 = Infinity, by0 = Infinity, bz0 = Infinity, bx1 = -Infinity, by1 = -Infinity, bz1 = -Infinity;
  const grow = (key: number | null, b: Box6): void => {
    const cur = outlines.get(key);
    if (!cur) outlines.set(key, { min: [b[0], b[2]], max: [b[3], b[5]] });
    else { cur.min[0] = Math.min(cur.min[0], b[0]); cur.min[1] = Math.min(cur.min[1], b[2]); cur.max[0] = Math.max(cur.max[0], b[3]); cur.max[1] = Math.max(cur.max[1], b[5]); }
  };
  for (const e of o.elements) {
    if (empty(e.bounds)) continue;
    byId.set(e.id, e);
    const outlineMaker = isEnvelopeClass(e.ifcClass) || isSlab(e.ifcClass);
    if (isEnvelopeClass(e.ifcClass)) envelope.add(e.id);
    if (outlineMaker) {
      grow(e.storey, e.bounds);
      grow(-1, e.bounds);
      bx0 = Math.min(bx0, e.bounds[0]); by0 = Math.min(by0, e.bounds[1]); bz0 = Math.min(bz0, e.bounds[2]);
      bx1 = Math.max(bx1, e.bounds[3]); by1 = Math.max(by1, e.bounds[4]); bz1 = Math.max(bz1, e.bounds[5]);
    }
  }
  const building: Box6 | null = bx0 <= bx1 ? [bx0, by0, bz0, bx1, by1, bz1] : null;
  const diag = building ? Math.hypot(building[3] - building[0], building[5] - building[2]) + 1 : 0;
  const height = building ? building[4] - building[1] : 0;
  const tol = Math.max(0.3, diag * 0.002);

  // The rays: blocked when something of the envelope set (not self, not a hosted filler, not the host) is in the way.
  const blocked = (excl: ReadonlySet<number>, ox: number, oy: number, oz: number, dx: number, dz: number): boolean => {
    if (envelope.size === 0) return false;
    for (const id of o.castHits([ox, oy, oz], [dx, 0, dz], diag, envelope)) if (envelope.has(id) && !excl.has(id)) return true;
    return false;
  };

  const ignoreOf = (e: PlacementElement): Set<number> => {
    const s = new Set<number>([e.id]);
    for (const h of o.hostedBy?.(e.id) ?? []) s.add(h);
    const host = o.hostOf?.(e.id);
    if (host !== undefined) s.add(host);
    return s;
  };

  const outlineOf = (e: PlacementElement): Outline | undefined => outlines.get(e.storey) ?? outlines.get(-1);

  function probeEnvelopeElement(e: PlacementElement): PlacementGeo {
    const b = e.bounds;
    const sx = b[3] - b[0], sz = b[5] - b[2];
    let n = o.normalOf?.(e.id) ?? null;
    if (!n) n = sx <= sz ? [1, 0] : [0, 1];
    const nl = Math.hypot(n[0], n[1]) || 1;
    const nx = n[0] / nl, nz = n[1] / nl;
    // the long direction in plan, for the sample points
    const tx = -nz, tz = nx;
    const cx = (b[0] + b[3]) / 2, cz = (b[2] + b[5]) / 2;
    const half = Math.abs(tx) * (sx / 2) + Math.abs(tz) * (sz / 2);
    const cand = ignoreOf(e);
    let clearA = 0, clearB = 0;
    const h = b[4] - b[1];
    for (const f of SAMPLES) {
      const k = (f - 0.5) * 2 * half;
      const px = cx + tx * k, pz = cz + tz * k;
      for (const lv of LEVELS) {
        const py = b[1] + lv * h;
        if (!blocked(cand, px, py, pz, nx, nz)) clearA++;
        if (!blocked(cand, px, py, pz, -nx, -nz)) clearB++;
      }
    }
    const total = SAMPLES.length * LEVELS.length;
    const need = Math.ceil(total * 0.66);
    const a = clearA >= need, c = clearB >= need;
    if (a && c) return { exposure: 'EXT', confidence: 0.7, rationale: 'a clear ray on both faces: free-standing' };
    if (a !== c) return { exposure: 'BOUNDARY', confidence: clearA === total || clearB === total ? 0.85 : 0.7, rationale: 'a clear ray on one face and the building on the other' };
    // both faces blocked: a face on the outline of its storey's plan is still the envelope (a wing of an L-shaped plan blocks the ray)
    const ol = outlineOf(e);
    if (ol && WALL.test(e.ifcClass)) {
      const onX = Math.abs(nx) > Math.abs(nz);
      const near = onX ? Math.min(Math.abs(b[0] - ol.min[0]), Math.abs(b[3] - ol.max[0])) : Math.min(Math.abs(b[2] - ol.min[1]), Math.abs(b[5] - ol.max[1]));
      if (near <= tol) return { exposure: 'BOUNDARY', confidence: 0.65, rationale: 'on the outline of the storey plan, though a wing blocks the ray' };
    }
    return { exposure: 'INT', confidence: 0.8, rationale: 'both faces face the building' };
  }

  function probeOther(e: PlacementElement): PlacementGeo {
    const b = e.bounds;
    const cx = (b[0] + b[3]) / 2, cz = (b[2] + b[5]) / 2;
    const ol = outlineOf(e);
    if (!ol || envelope.size === 0) return { exposure: 'INT', confidence: 0.3, rationale: 'no envelope in the model to test against' };
    if (cx < ol.min[0] - tol || cx > ol.max[0] + tol || cz < ol.min[1] - tol || cz > ol.max[1] + tol) return { exposure: 'EXT', confidence: 0.9, rationale: 'outside the plan outline of the storey' };
    const cy = (b[1] + b[4]) / 2;
    const cand = new Set<number>([e.id]);
    let clear = 0;
    for (const [dx, dz] of EIGHT) if (!blocked(cand, cx, cy, cz, dx, dz)) clear++;
    if (clear === 0) return { exposure: 'INT', confidence: 0.85, rationale: 'no clear ray to the outside' };
    if (clear <= 2) return { exposure: 'INT', confidence: 0.6, rationale: `${clear} of 8 rays reach the outside` };
    if (clear >= 8) return { exposure: 'EXT', confidence: 0.8, rationale: 'every ray reaches the outside' };
    if (clear >= 6) return { exposure: 'EXT', confidence: 0.65, rationale: `${clear} of 8 rays reach the outside` };
    return { exposure: 'BOUNDARY', confidence: 0.5, rationale: `${clear} of 8 rays reach the outside: on or near the envelope` };
  }

  function probe(id: number): PlacementGeo | null {
    const e = byId.get(id);
    if (!e) return null;
    if (isFooting(e.ifcClass)) return { exposure: 'EXT', confidence: 0.6, rationale: 'a foundation lies outside the envelope' };
    if (building && (isRoofLike(e))) return { exposure: 'BOUNDARY', confidence: 0.9, rationale: 'a roof' };
    if (isSlab(e.ifcClass)) {
      if (!building) return { exposure: 'INT', confidence: 0.3, rationale: 'no building to compare with' };
      const slabTol = Math.max(0.4, height * 0.02);
      if (e.bounds[4] >= building[4] - slabTol && height > 1) return { exposure: 'BOUNDARY', confidence: 0.8, rationale: 'the top slab of the building' };
      if (e.bounds[1] <= building[1] + slabTol) return { exposure: 'BOUNDARY', confidence: 0.7, rationale: 'the lowest slab, on the ground' };
      return { exposure: 'INT', confidence: 0.7, rationale: 'an intermediate floor' };
    }
    if (isEnvelopeClass(e.ifcClass)) return probeEnvelopeElement(e);
    return probeOther(e);
  }

  return {
    probe,
    building,
    async probeAll(ids, p = {}) {
      const list = ids ?? [...byId.keys()];
      const out = new Map<number, PlacementGeo>();
      const slice = p.sliceMs ?? 12;
      const yieldFn = p.yieldFn ?? (() => new Promise<void>((r) => setTimeout(r, 0)));
      let t0 = Date.now();
      for (let i = 0; i < list.length; i++) {
        if (p.signal?.aborted) break;
        const r = probe(list[i]!);
        if (r) out.set(list[i]!, r);
        if (Date.now() - t0 >= slice) {
          p.onProgress?.(i + 1, list.length);
          await yieldFn();
          t0 = Date.now();
        }
      }
      p.onProgress?.(list.length, list.length);
      return out;
    },
  };
}

// ---------------------------------------------------------------- a brute-force ray caster, for tests and Node

export interface RayMesh {
  position: ArrayLike<number>;
  index?: ArrayLike<number> | null;
}

/** Möller-Trumbore over every triangle, both sides. Slow (linear in triangles): for tests and small models. The viewer uses the BVH instead. */
export function meshRayHits(meshOf: (id: number) => RayMesh | null | undefined): RayHits {
  return (origin, dir, maxDistance, candidates) => {
    const hit: number[] = [];
    const [ox, oy, oz] = origin, [dx, dy, dz] = dir;
    for (const id of candidates) {
      const m = meshOf(id);
      if (!m) continue;
      const pos = m.position, idx = m.index ?? null;
      const tris = idx ? Math.floor(idx.length / 3) : Math.floor(pos.length / 9);
      for (let t = 0; t < tris; t++) {
        const ia = idx ? idx[3 * t]! : 3 * t, ib = idx ? idx[3 * t + 1]! : 3 * t + 1, ic = idx ? idx[3 * t + 2]! : 3 * t + 2;
        const ax = pos[3 * ia]!, ay = pos[3 * ia + 1]!, az = pos[3 * ia + 2]!;
        const e1x = pos[3 * ib]! - ax, e1y = pos[3 * ib + 1]! - ay, e1z = pos[3 * ib + 2]! - az;
        const e2x = pos[3 * ic]! - ax, e2y = pos[3 * ic + 1]! - ay, e2z = pos[3 * ic + 2]! - az;
        const px = dy * e2z - dz * e2y, py = dz * e2x - dx * e2z, pz = dx * e2y - dy * e2x;
        const det = e1x * px + e1y * py + e1z * pz;
        if (Math.abs(det) < 1e-12) continue;
        const inv = 1 / det;
        const tx = ox - ax, ty = oy - ay, tz = oz - az;
        const u = (tx * px + ty * py + tz * pz) * inv;
        if (u < 0 || u > 1) continue;
        const qx = ty * e1z - tz * e1y, qy = tz * e1x - tx * e1z, qz = tx * e1y - ty * e1x;
        const v = (dx * qx + dy * qy + dz * qz) * inv;
        if (v < 0 || u + v > 1) continue;
        const d = (e2x * qx + e2y * qy + e2z * qz) * inv;
        if (d > 1e-6 && d <= maxDistance) { hit.push(id); break; }
      }
    }
    return hit;
  };
}
