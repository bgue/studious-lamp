// The pure build stage of the IFC reader: RawModel[] -> glb bytes + xray-model/1 sidecar (CLI packager, parity reference) or
// -> merged arrays for MergedGeometry.fromArrays (the browser's direct path). No web-ifc, no three.js, so the import worker
// can run it. Conventions follow the converter (tools/ifc2glb.py, tools/glb_common.py): skipped classes, marker proxies,
// Z-up to Y-up, origin shift, storey assignment and fallback, hosts from voids and fills, ports, systems, federation and
// GlobalId dedupe. ifcImport.ts re-exports everything here.

import type { ElementRecord, Relations, StoreyRecord } from '../types';
import { computeEdges, EDGE_THRESHOLD_DEG } from './ifcEdges';
import { classColor, isMarker, isSkippedClass, smoothMesh } from './ifcShared';
import type { IfcProgress, RawElement, RawModel } from './ifcShared';
import type { MergedArrays } from './mergedArrays';

export const WEB_IFC_VERSION = '0.0.78';

export interface Sidecar {
  schema: 'xray-model/1';
  source: { files: string[]; converter: string; ifcSchema: string };
  units: 'm';
  originShift: [number, number, number];
  storeys: StoreyRecord[];
  elements: ElementRecord[];
  relations: Relations;
}

export interface BuildReport {
  /** elements dropped as duplicates of an earlier file's element (same GlobalId, same class and bounds) */
  duplicatesSkipped: number;
  /** GlobalId clashes with different geometry (the later element got a `~n` suffix) */
  renamed: number;
  /** elements dropped for a skipped class, a marker proxy or empty geometry */
  dropped: number;
  /** elements that got a storey from the elevation fallback */
  storeyFallback: number;
}

export interface BuiltData {
  glb: ArrayBuffer;
  sidecar: Sidecar;
  report: BuildReport;
}

const f4 = (x: number): number => Math.round(x * 1e4) / 1e4;
const round = (x: number, d: number): number => {
  const k = 10 ** d;
  return Math.round(x * k) / k;
};

interface Item {
  gid: string;
  expressId: number;
  ifcClass: string;
  name: string;
  storeyKey: number; // index into the merged storey list, or -1
  material: string;
  props?: Record<string, string | number | boolean>;
  color: [number, number, number, number];
  pos: Float32Array;
  nor: Float32Array;
  idx: Uint32Array;
  origin: [number, number, number];
  lo: [number, number, number];
  hi: [number, number, number];
  file: string;
  /** The reader's element: a consuming build drops its arrays once they are copied. */
  src: RawElement;
}

/** Everything `buildModelData` / `buildMergedData` need before geometry is written: merged element list and relations. */
interface Prepared {
  items: Item[];
  storeys: StoreyRecord[];
  shift: [number, number, number];
  voids: Array<[number, number]>;
  fills: Array<[number, number]>;
  hosts: Array<[number, number]>;
  openingsRaw: Array<{ expressId: number; host: number; bounds: number[] }>;
  ports: Array<[number, number]>;
  systems: Map<string, number[]>;
  report: BuildReport;
  files: string[];
  schemas: string[];
}

/** Steps shared by the glb path and the direct path: skip rules, welding fallback, dedupe, storeys, relations, origin shift. */
function prepare(raws: RawModel[]): Prepared {
  const report: BuildReport = { duplicatesSkipped: 0, renamed: 0, dropped: 0, storeyFallback: 0 };

  // ---- storeys of all files, merged by name and elevation within 1 cm, then sorted by elevation
  interface MStorey { name: string; elevation: number }
  const merged: MStorey[] = [];
  const findStorey = (list: MStorey[], name: string, elev: number): number =>
    list.findIndex((s) => s.name === name && Math.abs(s.elevation - elev) <= 0.01);
  for (const raw of raws) {
    for (const s of raw.storeys) {
      if (findStorey(merged, s.name, s.elevation) < 0) merged.push({ name: s.name, elevation: f4(s.elevation) });
    }
  }
  const order = merged.map((_, i) => i).sort((a, b) => merged[a]!.elevation - merged[b]!.elevation || (merged[a]!.name < merged[b]!.name ? -1 : merged[a]!.name > merged[b]!.name ? 1 : 0));
  const storeys: StoreyRecord[] = order.map((mi, i) => ({ id: i, name: merged[mi]!.name, elevation: merged[mi]!.elevation }));
  const finalIndex = (name: string, elev: number): number => findStorey(storeys, name, elev);

  // ---- elements
  const items: Item[] = [];
  const usedGids = new Set<string>();
  const seenGeom = new Map<string, string>(); // gid -> class + rounded bounds
  const voids: Array<[number, number]> = [];
  const fills: Array<[number, number]> = [];
  const hosts: Array<[number, number]> = [];
  const openingsRaw: Array<{ expressId: number; host: number; bounds: number[] }> = []; // IFC frame, absolute
  const ports: Array<[number, number]> = [];
  const portSeen = new Set<string>();
  const hostSeen = new Set<string>();
  const systems = new Map<string, number[]>();

  for (const raw of raws) {
    const origin = raw.origin ?? [0, 0, 0];
    const storeyIdx = new Map<number, number>(); // storey express id -> final storey id
    for (const s of raw.storeys) storeyIdx.set(s.expressId, finalIndex(s.name, s.elevation));
    const fileStoreys = [...new Set(raw.storeys.map((s) => storeyIdx.get(s.expressId)!))]
      .filter((i) => i >= 0)
      .sort((a, b) => storeys[a]!.elevation - storeys[b]!.elevation || (storeys[a]!.name < storeys[b]!.name ? -1 : 1));
    const eidByExpress = new Map<number, number>();

    const sorted = [...raw.elements].sort((a, b) => a.expressId - b.expressId);
    for (const el of sorted) {
      if (isSkippedClass(el.ifcClass) || isMarker(el.ifcClass, el.name)) { report.dropped++; continue; }
      let pos = el.positions;
      let nor = el.normals;
      let idx = el.indices;
      if (!nor || nor.length !== pos.length) {
        const sm = smoothMesh(pos, idx);
        pos = sm.positions; nor = sm.normals; idx = sm.indices;
      }
      if (idx.length < 3 || pos.length < 9) { report.dropped++; continue; }

      const lo: [number, number, number] = [Infinity, Infinity, Infinity];
      const hi: [number, number, number] = [-Infinity, -Infinity, -Infinity];
      for (let i = 0; i < pos.length; i += 3) {
        for (let k = 0; k < 3; k++) {
          const v = pos[i + k]! + origin[k]!;
          if (v < lo[k]!) lo[k] = v;
          if (v > hi[k]!) hi[k] = v;
        }
      }
      let gid = el.globalId;
      const sig = `${el.ifcClass}|${[...lo, ...hi].map((x) => round(x, 3)).join(',')}`;
      if (usedGids.has(gid)) {
        if (seenGeom.get(gid) === sig) { report.duplicatesSkipped++; continue; }
        gid = `${gid}~${items.length}`;
        report.renamed++;
      }
      usedGids.add(gid);
      seenGeom.set(gid, sig);

      let sk = el.storeyExpressId !== null ? (storeyIdx.get(el.storeyExpressId) ?? -1) : -1;
      if (sk < 0 && fileStoreys.length > 0) {
        // nearest storey at or below the element's lowest point, else the lowest storey
        const zmin = lo[2];
        let pick = fileStoreys[0]!;
        for (const s of fileStoreys) if (storeys[s]!.elevation <= zmin + 1e-6) pick = s;
        sk = pick;
        report.storeyFallback++;
      }
      eidByExpress.set(el.expressId, items.length);
      items.push({
        gid, expressId: el.expressId, ifcClass: el.ifcClass, name: el.name, storeyKey: sk, material: el.materialName, props: el.props,
        color: el.color ? [el.color[0], el.color[1], el.color[2], el.color[3]] : classColor(el.ifcClass),
        pos, nor, idx, origin: [origin[0], origin[1], origin[2]], lo, hi, file: raw.fileName, src: el,
      });
    }

    // ---- relations (express ids are only meaningful inside one file)
    const openHost = new Map<number, number>();
    for (const [h, o] of raw.voids) {
      const he = eidByExpress.get(h);
      if (he === undefined) continue;
      openHost.set(o, he);
      voids.push([he, o]);
    }
    for (const op of raw.openings ?? []) {
      const he = eidByExpress.get(op.host);
      if (he !== undefined) openingsRaw.push({ expressId: op.expressId, host: he, bounds: op.bounds });
    }
    for (const [o, f] of raw.fills) {
      const fe = eidByExpress.get(f);
      if (fe === undefined) continue;
      fills.push([o, fe]);
      const h = openHost.get(o);
      if (h !== undefined && fe !== h && !hostSeen.has(`${fe}:${h}`)) {
        hostSeen.add(`${fe}:${h}`);
        hosts.push([fe, h]);
      }
    }
    for (const [a, b] of raw.ports) {
      const ea = eidByExpress.get(a);
      const eb = eidByExpress.get(b);
      if (ea === undefined || eb === undefined || ea === eb) continue;
      const k = `${Math.min(ea, eb)}:${Math.max(ea, eb)}`;
      if (portSeen.has(k)) continue;
      portSeen.add(k);
      ports.push([Math.min(ea, eb), Math.max(ea, eb)]);
    }
    for (const sys of raw.systems) {
      const ids: number[] = [];
      for (const x of sys.elements) {
        const e = eidByExpress.get(x);
        if (e !== undefined) ids.push(e);
      }
      if (ids.length === 0) continue;
      let list = systems.get(sys.name);
      if (!list) systems.set(sys.name, (list = []));
      for (const i of ids) if (!list.includes(i)) list.push(i);
    }
  }

  if (items.length === 0) throw new Error('no exportable geometry found');

  // ---- origin shift: the overall bounds centre (IFC frame) becomes the origin
  const glo = [Infinity, Infinity, Infinity];
  const ghi = [-Infinity, -Infinity, -Infinity];
  for (const it of items) {
    for (let k = 0; k < 3; k++) {
      if (it.lo[k]! < glo[k]!) glo[k] = it.lo[k]!;
      if (it.hi[k]! > ghi[k]!) ghi[k] = it.hi[k]!;
    }
  }
  const shift: [number, number, number] = [round((glo[0]! + ghi[0]!) / 2, 6), round((glo[1]! + ghi[1]!) / 2, 6), round((glo[2]! + ghi[2]!) / 2, 6)];
  return {
    items, storeys, shift, voids, fills, hosts, openingsRaw, ports, systems, report,
    files: raws.map((r) => r.fileName), schemas: [...new Set(raws.map((r) => r.schema))],
  };
}

/**
 * Z up -> Y up by rotating vertex data (x, y, z) -> (x, z, -y), shift applied before the rotation. Writes `n` vertices at
 * `off` (a float offset, 3 per vertex) of `p` and `nn` and returns the element bounds in the glb frame (doubles).
 * The glb path and the direct path both go through this function, so they cannot differ.
 */
function placeItem(it: Item, shift: [number, number, number], p: Float32Array, nn: Float32Array, off: number): number[] {
  const n = it.pos.length / 3;
  const b = [Infinity, Infinity, Infinity, -Infinity, -Infinity, -Infinity];
  for (let v = 0; v < n; v++) {
    const x = it.pos[v * 3]! + it.origin[0] - shift[0];
    const y = it.pos[v * 3 + 1]! + it.origin[1] - shift[1];
    const z = it.pos[v * 3 + 2]! + it.origin[2] - shift[2];
    const o = off + v * 3;
    p[o] = x; p[o + 1] = z; p[o + 2] = -y;
    nn[o] = it.nor[v * 3]!; nn[o + 1] = it.nor[v * 3 + 2]!; nn[o + 2] = -it.nor[v * 3 + 1]!;
    if (x < b[0]!) b[0] = x;
    if (z < b[1]!) b[1] = z;
    if (-y < b[2]!) b[2] = -y;
    if (x > b[3]!) b[3] = x;
    if (z > b[4]!) b[4] = z;
    if (-y > b[5]!) b[5] = -y;
  }
  return b;
}

function elementRecord(it: Item, id: number, b: number[]): ElementRecord {
  return {
    id,
    globalId: it.gid,
    expressId: it.expressId,
    ifcClass: it.ifcClass,
    name: it.name,
    storey: it.storeyKey >= 0 ? it.storeyKey : null,
    material: it.material,
    color: [round(it.color[0], 4), round(it.color[1], 4), round(it.color[2], 4), round(it.color[3], 4)],
    bounds: b.map((x) => round(x, 5)) as ElementRecord['bounds'],
    file: it.file,
    ...(it.props ? { props: it.props } : {}),
  };
}

/** Sidecar relations, storeys and source info (everything but the element list). */
function sidecarHead(pr: Prepared): Omit<Sidecar, 'elements'> {
  const shift = pr.shift;
  // opening bounds: same shift and Y-up rotation as the elements; the key is omitted when the model has none
  const openings = pr.openingsRaw.map((o) => {
    const b = o.bounds;
    const x0 = b[0]! - shift[0], x1 = b[3]! - shift[0];
    const y0 = b[1]! - shift[1], y1 = b[4]! - shift[1];
    const z0 = b[2]! - shift[2], z1 = b[5]! - shift[2];
    return { expressId: o.expressId, host: o.host, bounds: [x0, z0, -y1, x1, z1, -y0].map((x) => round(x, 5)) as [number, number, number, number, number, number] };
  });
  return {
    schema: 'xray-model/1',
    source: {
      files: pr.files,
      converter: `web-ifc ${WEB_IFC_VERSION} (in-browser)`,
      ifcSchema: pr.schemas.join('+'),
    },
    units: 'm',
    originShift: shift,
    storeys: pr.storeys,
    relations: {
      voids: pr.voids, fills: pr.fills, hosts: pr.hosts, ports: pr.ports,
      systems: [...pr.systems].map(([name, els]) => ({ name, elements: els })),
      ...(openings.length > 0 ? { openings } : {}),
    },
  };
}

/**
 * RawModels (one per IFC file, in the order given) -> glb bytes and sidecar, the same data `ifc2glb.py` writes.
 * Throws when no element survives. This is the path of the CLI packager and the reference for `buildMergedData`.
 */
export function buildModelData(raws: RawModel[]): BuiltData {
  const pr = prepare(raws);
  const meshes: GlbMesh[] = [];
  const elements: ElementRecord[] = [];
  for (let i = 0; i < pr.items.length; i++) {
    const it = pr.items[i]!;
    const n = it.pos.length / 3;
    const p = new Float32Array(n * 3);
    const nn = new Float32Array(n * 3);
    const b = placeItem(it, pr.shift, p, nn, 0);
    meshes.push({ name: it.gid, id: i, ifcClass: it.ifcClass, positions: p, normals: nn, indices: it.idx });
    elements.push(elementRecord(it, i, b));
  }
  const sidecar: Sidecar = { ...sidecarHead(pr), elements };
  return { glb: writeGlb(meshes), sidecar, report: pr.report };
}

// ---------------------------------------------------------------- direct path (no glb)

export type EdgesOption = 'auto' | 'all' | 'none';
/** `edges: 'auto'` skips the edge geometry above this many elements. */
export const AUTO_EDGES_MAX_ELEMENTS = 50000;

export interface MergedBuildOptions {
  edges?: EdgesOption;
  /** Free each RawElement's arrays as soon as they are copied (the worker does; tests that reuse the RawModel do not). */
  consume?: boolean;
  onProgress?(p: IfcProgress): void;
  /** Called between steps; throw to stop. */
  check?(): void;
}

export interface MergedBuild {
  /** Sidecar without `elements` (those travel separately, see `records`). */
  head: Omit<Sidecar, 'elements'>;
  records: ElementRecord[];
  arrays: MergedArrays;
  report: BuildReport;
  edgesSkipped: boolean;
  timings: { prepareMs: number; mergeMs: number; edgesMs: number };
}

/**
 * RawModels -> merged arrays ready for `MergedGeometry.fromArrays`: the same vertices, indices, ranges and bounds that
 * glb bytes + `parseModel` end up with, without writing or parsing a glb, plus crease edges (`computeEdges`).
 */
export function buildMergedData(raws: RawModel[], opts: MergedBuildOptions = {}): MergedBuild {
  const t0 = performance.now();
  const pr = prepare(raws);
  const t1 = performance.now();
  const items = pr.items;
  const n = items.length;
  const progress = opts.onProgress;

  let vTotal = 0;
  let iTotal = 0;
  for (const it of items) {
    vTotal += it.pos.length / 3;
    iTotal += it.idx.length;
  }
  const position = new Float32Array(vTotal * 3);
  const normal = new Float32Array(vTotal * 3);
  const elementId = new Float32Array(vTotal);
  const index = new Uint32Array(iTotal);
  const ranges = new Uint32Array(n * 2);
  const vertexRanges = new Uint32Array(n * 2);
  const bounds = new Float32Array(n * 6);
  const records: ElementRecord[] = [];
  let vOff = 0;
  let iOff = 0;
  progress?.({ phase: 'merge', done: 0, total: n });
  let lastReport = performance.now();
  for (let i = 0; i < n; i++) {
    const it = items[i]!;
    const nv = it.pos.length / 3;
    const b = placeItem(it, pr.shift, position, normal, vOff * 3);
    for (let k = 0; k < 6; k++) bounds[i * 6 + k] = b[k]!;
    const idx = it.idx;
    for (let k = 0; k < idx.length; k++) index[iOff + k] = vOff + idx[k]!;
    elementId.fill(i, vOff, vOff + nv);
    vertexRanges[i * 2] = vOff; vertexRanges[i * 2 + 1] = nv;
    ranges[i * 2] = iOff; ranges[i * 2 + 1] = idx.length;
    records.push(elementRecord(it, i, b));
    vOff += nv;
    iOff += idx.length;
    if (opts.consume) {
      it.pos = EMPTY_F32; it.nor = EMPTY_F32; it.idx = EMPTY_U32;
      it.src.positions = EMPTY_F32; it.src.indices = EMPTY_U32;
      if (it.src.normals) it.src.normals = EMPTY_F32;
    }
    const now = performance.now();
    if (progress && now - lastReport > 100) {
      lastReport = now;
      progress({ phase: 'merge', done: i + 1, total: n });
      opts.check?.();
    }
  }
  progress?.({ phase: 'merge', done: n, total: n });
  const t2 = performance.now();

  const mode = opts.edges ?? 'auto';
  const edgesSkipped = mode === 'none' || (mode === 'auto' && n > AUTO_EDGES_MAX_ELEMENTS);
  const arrays: MergedArrays = {
    elementCount: n, position, normal, elementId, index, ranges, vertexRanges, bounds,
    edgePosition: new Float32Array(0), edgeElementId: new Float32Array(0), edgeRanges: new Uint32Array(n * 2),
  };
  if (edgesSkipped) {
    progress?.({ phase: 'edges', done: 0, total: n, skipped: mode === 'none' ? 'none' : 'auto' });
  } else {
    opts.check?.();
    progress?.({ phase: 'edges', done: 0, total: n });
    let last = performance.now();
    const e = computeEdges({ position, index, vertexRanges, ranges, elementCount: n }, EDGE_THRESHOLD_DEG, (done) => {
      const now = performance.now();
      if (progress && now - last > 100) { last = now; progress({ phase: 'edges', done, total: n }); opts.check?.(); }
    });
    arrays.edgePosition = e.position;
    arrays.edgeRanges = e.ranges;
    const ids = new Float32Array(e.position.length / 3);
    for (let i = 0; i < n; i++) ids.fill(i, e.ranges[i * 2]!, e.ranges[i * 2]! + e.ranges[i * 2 + 1]!);
    arrays.edgeElementId = ids;
    progress?.({ phase: 'edges', done: n, total: n });
  }
  const t3 = performance.now();
  return {
    head: sidecarHead(pr), records, arrays, report: pr.report, edgesSkipped,
    timings: { prepareMs: t1 - t0, mergeMs: t2 - t1, edgesMs: t3 - t2 },
  };
}

const EMPTY_F32 = new Float32Array(0);
const EMPTY_U32 = new Uint32Array(0);

// ---------------------------------------------------------------- glb writer (reference: tools/glb_common.py write_glb)

export interface GlbMesh {
  name: string;
  id: number;
  ifcClass: string;
  positions: Float32Array;
  normals: Float32Array;
  indices: Uint32Array;
}

/**
 * Hand-rolled glTF 2.0 binary: one node + mesh + primitive per entry, a single buffer, POSITION (with min/max),
 * NORMAL and uint32 indices; node.extras = { id, ifcClass }. Same layout as tools/glb_common.py.
 */
export function writeGlb(meshes: GlbMesh[]): ArrayBuffer {
  let binLen = 0;
  for (const m of meshes) binLen += m.positions.byteLength + m.normals.byteLength + m.indices.byteLength;
  const bin = new Uint8Array(binLen);
  const bufferViews: unknown[] = [];
  const accessors: unknown[] = [];
  const glMeshes: unknown[] = [];
  const nodes: unknown[] = [];
  let off = 0;
  const addView = (src: Float32Array | Uint32Array, target: number): number => {
    bin.set(new Uint8Array(src.buffer, src.byteOffset, src.byteLength), off);
    bufferViews.push({ buffer: 0, byteOffset: off, byteLength: src.byteLength, target });
    off += src.byteLength;
    return bufferViews.length - 1;
  };
  meshes.forEach((m, i) => {
    const bvP = addView(m.positions, 34962);
    const bvN = addView(m.normals, 34962);
    const bvI = addView(m.indices, 34963);
    const mn = [Infinity, Infinity, Infinity];
    const mx = [-Infinity, -Infinity, -Infinity];
    for (let v = 0; v < m.positions.length; v += 3) {
      for (let k = 0; k < 3; k++) {
        const x = m.positions[v + k]!;
        if (x < mn[k]!) mn[k] = x;
        if (x > mx[k]!) mx[k] = x;
      }
    }
    accessors.push({ bufferView: bvP, componentType: 5126, count: m.positions.length / 3, type: 'VEC3', min: mn, max: mx });
    const aP = accessors.length - 1;
    accessors.push({ bufferView: bvN, componentType: 5126, count: m.normals.length / 3, type: 'VEC3' });
    const aN = accessors.length - 1;
    accessors.push({ bufferView: bvI, componentType: 5125, count: m.indices.length, type: 'SCALAR' });
    const aI = accessors.length - 1;
    glMeshes.push({ name: m.name, primitives: [{ attributes: { POSITION: aP, NORMAL: aN }, indices: aI, mode: 4 }] });
    nodes.push({ name: m.name, mesh: i, extras: { id: m.id, ifcClass: m.ifcClass } });
  });
  const doc = {
    asset: { version: '2.0', generator: 'xray-ref ifcImport' },
    scene: 0,
    scenes: [{ name: 'xray', nodes: nodes.map((_, i) => i) }],
    nodes,
    meshes: glMeshes,
    accessors,
    bufferViews,
    buffers: [{ byteLength: binLen }],
  };
  let json = new TextEncoder().encode(JSON.stringify(doc));
  const jsonPad = (4 - (json.length % 4)) % 4;
  if (jsonPad) {
    const padded = new Uint8Array(json.length + jsonPad).fill(0x20);
    padded.set(json);
    json = padded;
  }
  const total = 12 + 8 + json.length + 8 + binLen;
  const out = new ArrayBuffer(total);
  const dv = new DataView(out);
  const u8 = new Uint8Array(out);
  dv.setUint32(0, 0x46546c67, true);
  dv.setUint32(4, 2, true);
  dv.setUint32(8, total, true);
  dv.setUint32(12, json.length, true);
  dv.setUint32(16, 0x4e4f534a, true);
  u8.set(json, 20);
  const binHead = 20 + json.length;
  dv.setUint32(binHead, binLen, true);
  dv.setUint32(binHead + 4, 0x004e4942, true);
  u8.set(bin, binHead + 8);
  return out;
}

