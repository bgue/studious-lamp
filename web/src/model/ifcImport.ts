// Open your own IFC files: RawModel[] -> LoadedModel, plus the worker orchestration around the web-ifc reader.
//
// Pipeline:  files --(worker, ifcRaw.ts: extract)--> RawModel per file --(build, pure TS)--> glb bytes + xray-model/1
// sidecar in memory --> parseModel(glb, sidecar) --> LoadedModel. There is deliberately one loader path: the result is
// exactly what tools/ifc2glb.py would have written to disk and loader.ts would have read. Conventions follow the
// converter (tools/ifc2glb.py, tools/glb_common.py): skipped classes, marker proxies, Z-up to Y-up, origin shift,
// storey assignment and fallback, hosts from voids and fills, ports, systems, federation and GlobalId dedupe.

import type { ElementRecord, Relations, StoreyRecord } from '../types';
import { parseModel } from './loader';
import type { LoadedModel } from './loader';
import { IFC_READER_AVAILABLE, createIfcWorker, getWasmSource, loadRawReader } from './ifcRuntime';
import type { WorkerIn, WorkerOut } from './ifcWorker';
import { classColor, isMarker, isSkippedClass, smoothMesh } from './ifcShared';
import type { IfcProgress, RawModel } from './ifcShared';

export type { IfcProgress, RawModel, RawElement, RawStorey } from './ifcShared';
export { IFC_READER_AVAILABLE } from './ifcRuntime';

export const WEB_IFC_VERSION = '0.0.78';

// ---------------------------------------------------------------- build (pure)

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
  color: [number, number, number, number];
  pos: Float32Array;
  nor: Float32Array;
  idx: Uint32Array;
  origin: [number, number, number];
  lo: [number, number, number];
  hi: [number, number, number];
  file: string;
}

/**
 * RawModels (one per IFC file, in the order given) -> glb bytes and sidecar, the same data `ifc2glb.py` writes.
 * Throws when no element survives.
 */
export function buildModelData(raws: RawModel[]): BuiltData {
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
        gid, expressId: el.expressId, ifcClass: el.ifcClass, name: el.name, storeyKey: sk, material: el.materialName,
        color: el.color ? [el.color[0], el.color[1], el.color[2], el.color[3]] : classColor(el.ifcClass),
        pos, nor, idx, origin: [origin[0], origin[1], origin[2]], lo, hi, file: raw.fileName,
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

  // ---- glb: Z up -> Y up by rotating vertex data (x, y, z) -> (x, z, -y), shift applied before the rotation
  const meshes: GlbMesh[] = [];
  const elements: ElementRecord[] = [];
  for (let i = 0; i < items.length; i++) {
    const it = items[i]!;
    const n = it.pos.length / 3;
    const p = new Float32Array(n * 3);
    const nn = new Float32Array(n * 3);
    const b = [Infinity, Infinity, Infinity, -Infinity, -Infinity, -Infinity];
    for (let v = 0; v < n; v++) {
      const x = it.pos[v * 3]! + it.origin[0] - shift[0];
      const y = it.pos[v * 3 + 1]! + it.origin[1] - shift[1];
      const z = it.pos[v * 3 + 2]! + it.origin[2] - shift[2];
      p[v * 3] = x; p[v * 3 + 1] = z; p[v * 3 + 2] = -y;
      nn[v * 3] = it.nor[v * 3]!; nn[v * 3 + 1] = it.nor[v * 3 + 2]!; nn[v * 3 + 2] = -it.nor[v * 3 + 1]!;
      if (x < b[0]!) b[0] = x;
      if (z < b[1]!) b[1] = z;
      if (-y < b[2]!) b[2] = -y;
      if (x > b[3]!) b[3] = x;
      if (z > b[4]!) b[4] = z;
      if (-y > b[5]!) b[5] = -y;
    }
    meshes.push({ name: it.gid, id: i, ifcClass: it.ifcClass, positions: p, normals: nn, indices: it.idx });
    elements.push({
      id: i,
      globalId: it.gid,
      expressId: it.expressId,
      ifcClass: it.ifcClass,
      name: it.name,
      storey: it.storeyKey >= 0 ? it.storeyKey : null,
      material: it.material,
      color: [round(it.color[0], 4), round(it.color[1], 4), round(it.color[2], 4), round(it.color[3], 4)],
      bounds: b.map((x) => round(x, 5)) as ElementRecord['bounds'],
      file: it.file,
    });
  }

  const schemas = [...new Set(raws.map((r) => r.schema))];
  const sidecar: Sidecar = {
    schema: 'xray-model/1',
    source: {
      files: raws.map((r) => r.fileName),
      converter: `web-ifc ${WEB_IFC_VERSION} (in-browser)`,
      ifcSchema: schemas.join('+'),
    },
    units: 'm',
    originShift: shift,
    storeys,
    elements,
    relations: { voids, fills, hosts, ports, systems: [...systems].map(([name, els]) => ({ name, elements: els })) },
  };
  return { glb: writeGlb(meshes), sidecar, report };
}

/** RawModel[] -> LoadedModel through the same loader the glb + sidecar files use. */
export async function build(raws: RawModel[]): Promise<LoadedModel> {
  const { glb, sidecar } = buildModelData(raws);
  return parseModel(glb, sidecar);
}

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

// ---------------------------------------------------------------- .ifczip

export function isZip(data: Uint8Array): boolean {
  return data.length > 4 && data[0] === 0x50 && data[1] === 0x4b && data[2] === 0x03 && data[3] === 0x04;
}

/** Contents of the first `.ifc` entry of a zip (stored or deflate). Uses the central directory, so data descriptors are fine. */
export async function unzipIfc(data: Uint8Array): Promise<{ name: string; bytes: Uint8Array }> {
  const dv = new DataView(data.buffer, data.byteOffset, data.byteLength);
  let eocd = -1;
  for (let i = data.length - 22; i >= Math.max(0, data.length - 65557); i--) {
    if (dv.getUint32(i, true) === 0x06054b50) { eocd = i; break; }
  }
  if (eocd < 0) throw new Error('not a valid zip archive');
  const count = dv.getUint16(eocd + 10, true);
  let p = dv.getUint32(eocd + 16, true);
  const dec = new TextDecoder();
  for (let n = 0; n < count; n++) {
    if (dv.getUint32(p, true) !== 0x02014b50) break;
    const method = dv.getUint16(p + 10, true);
    const csize = dv.getUint32(p + 20, true);
    const usize = dv.getUint32(p + 24, true);
    const nlen = dv.getUint16(p + 28, true);
    const xlen = dv.getUint16(p + 30, true);
    const clen = dv.getUint16(p + 32, true);
    const lho = dv.getUint32(p + 42, true);
    const name = dec.decode(data.subarray(p + 46, p + 46 + nlen));
    p += 46 + nlen + xlen + clen;
    if (!/\.ifc$/i.test(name)) continue;
    const lnlen = dv.getUint16(lho + 26, true);
    const lxlen = dv.getUint16(lho + 28, true);
    const start = lho + 30 + lnlen + lxlen;
    const comp = data.subarray(start, start + csize);
    if (method === 0) return { name, bytes: comp.slice() };
    if (method === 8) {
      const stream = new Blob([comp as BlobPart]).stream().pipeThrough(new DecompressionStream('deflate-raw'));
      const bytes = new Uint8Array(await new Response(stream).arrayBuffer());
      if (usize && bytes.length !== usize) throw new Error('zip entry is corrupt (size mismatch)');
      return { name, bytes };
    }
    throw new Error(`zip compression method ${method} is not supported`);
  }
  throw new Error('the zip archive contains no .ifc file');
}

// ---------------------------------------------------------------- orchestration

export interface IfcInput {
  name: string;
  data: ArrayBuffer;
}

export interface ImportOptions {
  onProgress?(p: IfcProgress): void;
  signal?: AbortSignal;
  /** Skip the worker (tests, and the fallback). */
  forceMainThread?: boolean;
}

export interface ImportResult {
  loaded: LoadedModel;
  mode: 'worker' | 'main';
  extractMs: number;
  buildMs: number;
  report: BuildReport;
  raws: Array<{ fileName: string; schema: string; elements: number; stats?: RawModel['stats'] }>;
}

export class ImportCancelled extends Error {
  constructor() {
    super('Load cancelled');
    this.name = 'ImportCancelled';
  }
}

export class IfcReaderUnavailable extends Error {
  constructor() {
    super('This build does not include the IFC reader');
    this.name = 'IfcReaderUnavailable';
  }
}

const nextTick = (): Promise<void> => new Promise((r) => setTimeout(r, 0));

export async function importIfc(inputs: IfcInput[], opts: ImportOptions = {}): Promise<ImportResult> {
  if (!IFC_READER_AVAILABLE) throw new IfcReaderUnavailable();
  const t0 = performance.now();
  let raws: RawModel[] | null = null;
  let mode: 'worker' | 'main' = 'worker';
  if (!opts.forceMainThread) {
    try {
      raws = await extractInWorker(inputs, opts);
    } catch (e) {
      if (!(e instanceof WorkerUnavailable)) throw e;
      console.info('[ifc-import] worker unavailable, reading on the main thread:', e.message);
    }
  }
  if (!raws) {
    mode = 'main';
    raws = await extractOnMainThread(inputs, opts);
  }
  const t1 = performance.now();
  opts.onProgress?.({ phase: 'build' });
  await nextTick(); // let the status text paint before the (synchronous) build
  if (opts.signal?.aborted) throw new ImportCancelled();
  const data = buildModelData(raws);
  const loaded = await parseModel(data.glb, data.sidecar);
  const t2 = performance.now();
  return {
    loaded, mode, extractMs: t1 - t0, buildMs: t2 - t1, report: data.report,
    raws: raws.map((r) => ({ fileName: r.fileName, schema: r.schema, elements: r.elements.length, stats: r.stats })),
  };
}

async function extractOnMainThread(inputs: IfcInput[], opts: ImportOptions): Promise<RawModel[]> {
  const reader = loadRawReader();
  if (!reader) throw new Error('Could not start the IFC reader worker, and this build has no main-thread reader');
  const mod = await reader;
  const api = await mod.createIfcApi(await getWasmSource());
  const out: RawModel[] = [];
  try {
    for (const inp of inputs) {
      if (opts.signal?.aborted) throw new ImportCancelled();
      try {
        out.push(await mod.extractIfc(api, new Uint8Array(inp.data), inp.name, {
          onProgress: opts.onProgress,
          cancelled: () => !!opts.signal?.aborted,
          yieldNow: nextTick,
        }));
      } catch (e) {
        if (e instanceof mod.IfcReadError && e.code === 'cancelled') throw new ImportCancelled();
        throw e;
      }
    }
  } finally {
    try { api.Dispose(); } catch { /* ignore */ }
  }
  return out;
}

class WorkerUnavailable extends Error {}

/**
 * One module worker with web-ifc initialised in it. `ready` settles once the wasm is up (or the worker could not start,
 * as a WorkerUnavailable). A reader serves one import and is then terminated, which hands the wasm heap back.
 */
class IfcReader {
  readonly ready: Promise<void>;
  private worker: Worker | null = null;
  private isReady = false;
  private dead = false;
  private pending: { resolve(r: RawModel): void; reject(e: Error): void; onProgress?(p: IfcProgress): void } | null = null;
  private resolveReady!: () => void;
  private rejectReady!: (e: Error) => void;
  private readonly initTimer: ReturnType<typeof setTimeout>;

  constructor() {
    this.ready = new Promise<void>((resolve, reject) => {
      this.resolveReady = resolve;
      this.rejectReady = reject;
    });
    this.ready.catch(() => undefined); // a pre-warmed reader may fail with nobody waiting
    this.initTimer = setTimeout(() => this.fail(new Error('The IFC reader did not start (timed out)')), 30000);
    void this.boot();
  }

  private async boot(): Promise<void> {
    let worker: Worker;
    try {
      worker = await createIfcWorker(); // throws when workers are unavailable
    } catch (e) {
      this.fail(new WorkerUnavailable(e instanceof Error ? e.message : String(e)));
      return;
    }
    if (this.dead) { worker.terminate(); return; }
    this.worker = worker;
    worker.onerror = (ev): void => {
      ev.preventDefault?.();
      const text = ev.message || 'worker failed to load';
      this.fail(this.isReady ? new Error(`IFC reader failed: ${text}`) : new WorkerUnavailable(text));
    };
    worker.onmessageerror = (): void => this.fail(new Error('IFC reader sent unreadable data'));
    worker.onmessage = (ev: MessageEvent<WorkerOut>): void => {
      const m = ev.data;
      if (m.type === 'ready') {
        this.isReady = true;
        clearTimeout(this.initTimer);
        this.resolveReady();
      } else if (m.type === 'progress') {
        this.pending?.onProgress?.(m.progress);
      } else if (m.type === 'done') {
        const p = this.pending;
        this.pending = null;
        p?.resolve(m.raw);
      } else if (m.type === 'error') {
        const p = this.pending;
        this.pending = null;
        const err = new Error(m.message);
        if (p) p.reject(err);
        else this.fail(err);
      }
    };
    try {
      worker.postMessage({ type: 'init', wasm: await getWasmSource() } satisfies WorkerIn);
    } catch (e) {
      this.fail(e instanceof Error ? e : new Error(String(e)));
    }
  }

  private fail(e: Error): void {
    if (this.dead) return;
    this.dead = true;
    clearTimeout(this.initTimer);
    this.worker?.terminate();
    if (!this.isReady) this.rejectReady(e);
    const p = this.pending;
    this.pending = null;
    p?.reject(e);
  }

  /** Hand one file to the worker (its buffer is transferred, not copied). */
  extract(id: number, input: IfcInput, onProgress?: (p: IfcProgress) => void): Promise<RawModel> {
    return new Promise<RawModel>((resolve, reject) => {
      if (this.dead || !this.worker) { reject(new Error('The IFC reader stopped')); return; }
      this.pending = { resolve, reject, onProgress };
      const msg: WorkerIn = { type: 'extract', id, fileName: input.name, data: input.data };
      this.worker.postMessage(msg, [input.data]);
    });
  }

  terminate(): void {
    if (this.dead) return;
    this.dead = true;
    clearTimeout(this.initTimer);
    this.worker?.terminate();
    if (!this.isReady) this.rejectReady(new ImportCancelled());
    const p = this.pending;
    this.pending = null;
    p?.reject(new ImportCancelled());
  }
}

let warm: IfcReader | null = null;
let warmTimer: ReturnType<typeof setTimeout> | undefined;

/**
 * Start the worker and the wasm before a file is chosen (the file dialog takes seconds, wasm start-up about one).
 * A warm reader that nobody uses is terminated after two minutes. Safe to call repeatedly; never throws.
 */
export function prewarmIfcReader(): void {
  if (!IFC_READER_AVAILABLE || warm) return;
  const r = new IfcReader();
  warm = r;
  r.ready.catch(() => { if (warm === r) warm = null; });
  warmTimer = setTimeout(() => { if (warm === r) { warm = null; r.terminate(); } }, 120000);
}

function takeReader(): IfcReader {
  if (warm) {
    const r = warm;
    warm = null;
    clearTimeout(warmTimer);
    return r;
  }
  return new IfcReader();
}

/** Reads every input in a module worker. Throws WorkerUnavailable only before any data was handed over. */
async function extractInWorker(inputs: IfcInput[], opts: ImportOptions): Promise<RawModel[]> {
  if (opts.signal?.aborted) throw new ImportCancelled();
  const reader = takeReader();
  const onAbort = (): void => reader.terminate();
  opts.signal?.addEventListener('abort', onAbort);
  try {
    await reader.ready; // rejects with WorkerUnavailable when the worker cannot start (nothing was transferred yet)
    const out: RawModel[] = [];
    for (let i = 0; i < inputs.length; i++) out.push(await reader.extract(i, inputs[i]!, opts.onProgress));
    return out;
  } finally {
    opts.signal?.removeEventListener('abort', onAbort);
    reader.terminate();
  }
}
