// Pure pieces shared by the IFC reader (ifcRaw.ts, runs in the worker) and the model builder (ifcImport.ts):
// the neutral RawModel contract, the converter's conventions (skipped classes, colours) and crease smoothing.
// No web-ifc and no three.js imports, so the worker bundle stays small and tests need no WASM.
// Reference: tools/ifc2glb.py (SKIP_CLASSES, CLASS_COLORS, is_marker, smooth_mesh).

/** One physical element, geometry in the IFC frame (Z up, metres). */
export interface RawElement {
  expressId: number;
  globalId: string;
  ifcClass: string;
  name: string;
  /** Express id of the IfcBuildingStorey the element belongs to (containment, walking aggregates up), else null. */
  storeyExpressId: number | null;
  materialName: string;
  /** RGBA 0..1 from the IFC surface style; `null` when the file gives no style (the class default applies). */
  color: [number, number, number, number] | null;
  /** xyz per vertex, world coordinates minus `RawModel.origin`. */
  positions: Float32Array;
  /** Triangle list into `positions`. */
  indices: Uint32Array;
  /** Per-vertex normals (same length as `positions`). When present, `positions`/`indices` are already welded and
   *  crease-smoothed (extract does this off the main thread); when absent `build` runs `smoothMesh`. */
  normals?: Float32Array;
  /** Hover-info properties (see ifcProps.ts for the key format, ordering and caps). */
  props?: Record<string, string | number | boolean>;
}

export interface RawStorey {
  expressId: number;
  name: string;
  /** metres */
  elevation: number;
}

/** What `extract` produces for one IFC file. Relations are keyed by express ids of that file. */
export interface RawModel {
  fileName: string;
  /** IFC2X3, IFC4, IFC4X3_ADD2, ... */
  schema: string;
  /** Added to every position to get world IFC coordinates (keeps Float32 precise far from the origin). Default 0. */
  origin?: [number, number, number];
  elements: RawElement[];
  storeys: RawStorey[];
  /** [hostExpressId, openingExpressId] */
  voids: Array<[number, number]>;
  /** [openingExpressId, fillerExpressId] */
  fills: Array<[number, number]>;
  /**
   * Bounds of the opening elements that void an exported host: world IFC frame (Z up, metres), absolute
   * (not relative to `origin`), [minx, miny, minz, maxx, maxy, maxz]. Opening geometry itself is never exported.
   */
  openings?: Array<{ expressId: number; host: number; bounds: [number, number, number, number, number, number] }>;
  /** Element-level pairs [expressIdA, expressIdB], already resolved through the ports. */
  ports: Array<[number, number]>;
  /** Members are express ids of elements (already expanded through aggregates, as the converter does). */
  systems: Array<{ name: string; elements: number[] }>;
  /** Counts for status messages and tests. */
  stats?: { products: number; skippedClass: number; noGeometry: number; markers: number };
}

export type IfcProgress =
  | { phase: 'read'; file: string; bytes: number }
  | { phase: 'open'; file: string; bytes: number }
  | { phase: 'meshing'; file: string; done: number; total: number }
  | { phase: 'relations'; file: string }
  | { phase: 'build' };

// ---------------------------------------------------------------- converter conventions

/** Geometry of these classes is never exported (IfcOpeningElement also covers IfcOpeningStandardCase). */
export const SKIP_CLASSES: readonly string[] = [
  'IfcOpeningElement', 'IfcOpeningStandardCase', 'IfcSpace', 'IfcSite', 'IfcBuilding', 'IfcBuildingStorey',
  'IfcAnnotation', 'IfcSpatialZone', 'IfcExternalSpatialElement', 'IfcGrid', 'IfcVirtualElement',
];
const SKIP_SET = new Set(SKIP_CLASSES.map((c) => c.toLowerCase()));

export function isSkippedClass(ifcClass: string): boolean {
  return SKIP_SET.has(ifcClass.toLowerCase());
}

const MARKER_NAMES = new Set(['origin', 'geo-reference']);

/** buildingSMART Simple-Scene files carry 'origin' / 'geo-reference' proxy cubes in every file. */
export function isMarker(ifcClass: string, name: string): boolean {
  return ifcClass.toLowerCase() === 'ifcbuildingelementproxy' && MARKER_NAMES.has(name.trim().toLowerCase());
}

const CONCRETE: [number, number, number, number] = [0.62, 0.62, 0.62, 1];
const BLUE: [number, number, number, number] = [0.3, 0.6, 0.9, 1];
const GREEN: [number, number, number, number] = [0.2, 0.7, 0.4, 1];
const ORANGE: [number, number, number, number] = [0.9, 0.6, 0.2, 1];
export const DEFAULT_COLOR: [number, number, number, number] = [0.7, 0.7, 0.7, 1];

export const CLASS_COLORS: Record<string, [number, number, number, number]> = {
  IfcWall: CONCRETE, IfcWallStandardCase: CONCRETE, IfcSlab: CONCRETE, IfcBeam: CONCRETE, IfcColumn: CONCRETE,
  IfcFooting: CONCRETE,
  IfcDuctSegment: BLUE, IfcDuctFitting: BLUE,
  IfcPipeSegment: GREEN, IfcPipeFitting: GREEN,
  IfcCableCarrierSegment: ORANGE, IfcCableCarrierFitting: ORANGE,
};

export function classColor(ifcClass: string): [number, number, number, number] {
  return [...(CLASS_COLORS[ifcClass] ?? DEFAULT_COLOR)] as [number, number, number, number];
}

/** Groups that count as systems for `relations.systems` (the converter tests `is_a("IfcSystem")`, which includes subtypes). */
export const SYSTEM_CLASSES: readonly string[] = [
  'IfcSystem', 'IfcDistributionSystem', 'IfcDistributionCircuit', 'IfcBuildingSystem', 'IfcZone',
  'IfcElectricalCircuit', 'IfcStructuralAnalysisModel',
];

// ---------------------------------------------------------------- mesh smoothing

export interface SmoothMesh {
  positions: Float32Array;
  normals: Float32Array;
  indices: Uint32Array;
}

const WELD_SCALE = 1e4; // positions closer than 0.1 mm weld

/**
 * Port of `smooth_mesh` in tools/ifc2glb.py: weld vertices by position, drop degenerate triangles, then give every
 * corner the area-weighted mean normal of the faces at its vertex that lie within `creaseDeg` of the corner's own
 * face; vertices are split where the resulting normals differ (rounded to 4 decimals). Input may be unindexed
 * (web-ifc emits 3 vertices per triangle). Returns empty arrays when nothing survives.
 */
export function smoothMesh(pos: ArrayLike<number>, idx: ArrayLike<number>, creaseDeg = 30): SmoothMesh {
  const nv = Math.floor(pos.length / 3);
  const nt0 = Math.floor(idx.length / 3);
  const empty = (): SmoothMesh => ({ positions: new Float32Array(0), normals: new Float32Array(0), indices: new Uint32Array(0) });
  if (nv === 0 || nt0 === 0) return empty();

  // 1. weld by quantised position (open-addressing hash on three Int32)
  const qx = new Int32Array(nv);
  const qy = new Int32Array(nv);
  const qz = new Int32Array(nv);
  let cap = 16;
  while (cap < nv * 2) cap <<= 1;
  const table = new Int32Array(cap).fill(-1);
  const mask = cap - 1;
  const remap = new Int32Array(nv);
  const uniq: number[] = []; // original vertex index of each welded vertex
  for (let i = 0; i < nv; i++) {
    const a = Math.round(pos[i * 3]! * WELD_SCALE) | 0;
    const b = Math.round(pos[i * 3 + 1]! * WELD_SCALE) | 0;
    const c = Math.round(pos[i * 3 + 2]! * WELD_SCALE) | 0;
    qx[i] = a; qy[i] = b; qz[i] = c;
    let h = (Math.imul(a, 73856093) ^ Math.imul(b, 19349663) ^ Math.imul(c, 83492791)) & mask;
    for (;;) {
      const t = table[h]!;
      if (t < 0) {
        table[h] = i;
        remap[i] = uniq.length;
        uniq.push(i);
        break;
      }
      if (qx[t] === a && qy[t] === b && qz[t] === c) {
        remap[i] = remap[t]!;
        break;
      }
      h = (h + 1) & mask;
    }
  }
  const wn = uniq.length;
  const wp = new Float64Array(wn * 3);
  for (let k = 0; k < wn; k++) {
    const o = uniq[k]! * 3;
    wp[k * 3] = pos[o]!; wp[k * 3 + 1] = pos[o + 1]!; wp[k * 3 + 2] = pos[o + 2]!;
  }

  // 2. faces: keep non-degenerate, area-weighted normals
  const faces = new Int32Array(nt0 * 3);
  const cx: number[] = [];
  const cy: number[] = [];
  const cz: number[] = [];
  let nf = 0;
  for (let t = 0; t < nt0; t++) {
    const a = remap[idx[t * 3]!]!;
    const b = remap[idx[t * 3 + 1]!]!;
    const c = remap[idx[t * 3 + 2]!]!;
    if (a === b || b === c || a === c) continue;
    const ux = wp[b * 3]! - wp[a * 3]!, uy = wp[b * 3 + 1]! - wp[a * 3 + 1]!, uz = wp[b * 3 + 2]! - wp[a * 3 + 2]!;
    const vx = wp[c * 3]! - wp[a * 3]!, vy = wp[c * 3 + 1]! - wp[a * 3 + 1]!, vz = wp[c * 3 + 2]! - wp[a * 3 + 2]!;
    const nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
    if (Math.hypot(nx, ny, nz) <= 1e-14) continue;
    faces[nf * 3] = a; faces[nf * 3 + 1] = b; faces[nf * 3 + 2] = c;
    cx.push(nx); cy.push(ny); cz.push(nz);
    nf++;
  }
  if (nf === 0) return empty();
  const un = new Float64Array(nf * 3);
  for (let f = 0; f < nf; f++) {
    const l = Math.hypot(cx[f]!, cy[f]!, cz[f]!);
    un[f * 3] = cx[f]! / l; un[f * 3 + 1] = cy[f]! / l; un[f * 3 + 2] = cz[f]! / l;
  }

  // 3. vertex -> incident faces (CSR)
  const start = new Int32Array(wn + 1);
  for (let k = 0; k < nf * 3; k++) start[faces[k]! + 1]!++;
  for (let v = 0; v < wn; v++) start[v + 1]! += start[v]!;
  const fill = start.slice(0, wn);
  const inc = new Int32Array(nf * 3);
  for (let f = 0; f < nf; f++) for (let k = 0; k < 3; k++) inc[fill[faces[f * 3 + k]!]!++] = f;

  // 4. per-corner smoothed normal, split vertices where normals differ
  const cosT = Math.cos((creaseDeg * Math.PI) / 180);
  const outPos: number[] = [];
  const outNor: number[] = [];
  const outIdx = new Uint32Array(nf * 3);
  // for each welded vertex: list of [qnx,qny,qnz,newIndex] already created
  const created: Array<Array<[number, number, number, number]> | undefined> = new Array(wn);
  for (let f = 0; f < nf; f++) {
    const fx = un[f * 3]!, fy = un[f * 3 + 1]!, fz = un[f * 3 + 2]!;
    for (let k = 0; k < 3; k++) {
      const v = faces[f * 3 + k]!;
      let sx = 0, sy = 0, sz = 0;
      for (let q = start[v]!; q < start[v + 1]!; q++) {
        const g = inc[q]!;
        if (fx * un[g * 3]! + fy * un[g * 3 + 1]! + fz * un[g * 3 + 2]! >= cosT) {
          sx += cx[g]!; sy += cy[g]!; sz += cz[g]!;
        }
      }
      let l = Math.hypot(sx, sy, sz);
      if (l === 0) l = 1;
      const nx = sx / l, ny = sy / l, nz = sz / l;
      const kx = Math.round(nx * 1e4), ky = Math.round(ny * 1e4), kz = Math.round(nz * 1e4);
      let list = created[v];
      if (!list) list = created[v] = [];
      let hit = -1;
      for (const e of list) if (e[0] === kx && e[1] === ky && e[2] === kz) { hit = e[3]; break; }
      if (hit < 0) {
        hit = outPos.length / 3;
        outPos.push(wp[v * 3]!, wp[v * 3 + 1]!, wp[v * 3 + 2]!);
        outNor.push(nx, ny, nz);
        list.push([kx, ky, kz, hit]);
      }
      outIdx[f * 3 + k] = hit;
    }
  }
  return { positions: Float32Array.from(outPos), normals: Float32Array.from(outNor), indices: outIdx };
}
