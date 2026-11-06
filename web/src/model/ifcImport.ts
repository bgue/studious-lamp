// Open your own IFC files: RawModel[] -> LoadedModel, plus the worker orchestration around the web-ifc reader.
//
// Pipeline:  files --(worker, ifcRaw.ts: extract)--> RawModel per file --(build, pure TS)--> glb bytes + xray-model/1
// sidecar in memory --> parseModel(glb, sidecar) --> LoadedModel. There is deliberately one loader path: the result is
// exactly what tools/ifc2glb.py would have written to disk and loader.ts would have read. Conventions follow the
// converter (tools/ifc2glb.py, tools/glb_common.py): skipped classes, marker proxies, Z-up to Y-up, origin shift,
// storey assignment and fallback, hosts from voids and fills, ports, systems, federation and GlobalId dedupe.

import type { ElementRecord } from '../types';
import { assembleLoaded, normaliseRecord, parseModel } from './loader';
import type { LoadedModel } from './loader';
import { MergedGeometry } from './merged';
import { IFC_READER_AVAILABLE, createIfcWorker, getWasmSource, loadRawReader } from './ifcRuntime';
import type { ExtractSummary, MergeTimings, WorkerIn, WorkerOut } from './ifcWorker';
import { buildMergedData, buildModelData } from './ifcBuild';
import type { BuildReport, EdgesOption, Sidecar } from './ifcBuild';
import type { PropsMode } from './ifcProps';
import type { IfcProgress, RawElement, RawModel } from './ifcShared';
import type { MergedArrays } from './mergedArrays';

export type { IfcProgress, RawModel, RawElement, RawStorey } from './ifcShared';
export { IFC_READER_AVAILABLE } from './ifcRuntime';

export {
  AUTO_EDGES_MAX_ELEMENTS, WEB_IFC_VERSION, buildMergedData, buildModelData, writeGlb,
} from './ifcBuild';
export type { BuildReport, BuiltData, EdgesOption, GlbMesh, MergedBuild, MergedBuildOptions, Sidecar } from './ifcBuild';

/** RawModel[] -> LoadedModel through the same loader the glb + sidecar files use. */
export async function build(raws: RawModel[]): Promise<LoadedModel> {
  const { glb, sidecar } = buildModelData(raws);
  return parseModel(glb, sidecar);
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
  /** Edge geometry: `auto` (default) skips it above 50,000 elements, `all` always builds it, `none` never. */
  edges?: EdgesOption;
  /** Element properties to read: `common` (default) or `none` (faster, smaller; hover cards then show attributes only). */
  props?: Extract<PropsMode, 'common' | 'none'>;
  /** Build the BVH in the worker and install it (default true; ignored on the main-thread path). */
  bvh?: boolean;
  /** Reference path for tests: write glb bytes and load them with parseModel, as the CLI packager does. */
  viaGlb?: boolean;
}

/** Wall-clock milliseconds of each stage of the last import. Worker stages are measured inside the worker. */
export interface StageTimings {
  /** Reading the file(s) into memory is done by the caller (fileLoader adds it). */
  readMs: number;
  openMs: number;
  meshMs: number;
  relationsMs: number;
  /** web-ifc heap release before the merge */
  releaseMs: number;
  /** storeys, relations, dedupe, origin shift */
  prepareMs: number;
  mergeMs: number;
  edgesMs: number;
  bvhMs: number;
  /** from the worker's last message to the arrays being usable on the main thread (message delivery + wrapping) */
  handoffMs: number;
  /** Everything from the call to the model being ready on the main thread. */
  totalMs: number;
}

export interface ModelStats {
  elements: number;
  triangles: number;
  vertices: number;
  edgeSegments: number;
  edgesSkipped: boolean;
  /** `worker`: built off the main thread and installed; `lazy`: built on first use. */
  bvh: 'worker' | 'lazy';
  /** Typed-array bytes of the geometry buffers (position, normal, elementId, index, edges, BVH). */
  bufferBytes: number;
}

export interface ImportResult {
  loaded: LoadedModel;
  mode: 'worker' | 'main' | 'glb';
  extractMs: number;
  buildMs: number;
  report: BuildReport;
  raws: Array<{ fileName: string; schema: string; elements: number; stats?: RawModel['stats'] }>;
  timings: StageTimings;
  stats: ModelStats;
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

/** Bytes of the typed arrays behind a merged geometry. */
export function bufferBytes(a: MergedArrays): number {
  let n = a.position.byteLength + a.normal.byteLength + a.elementId.byteLength + a.index.byteLength + a.bounds.byteLength
    + a.ranges.byteLength + a.vertexRanges.byteLength + a.edgePosition.byteLength + a.edgeElementId.byteLength + a.edgeRanges.byteLength;
  if (a.bvh) {
    for (const r of a.bvh.roots) n += r.byteLength;
    n += a.bvh.indirectBuffer.byteLength;
  }
  return n;
}

const zeroTimings = (): StageTimings => ({
  readMs: 0, openMs: 0, meshMs: 0, relationsMs: 0, releaseMs: 0, prepareMs: 0, mergeMs: 0, edgesMs: 0, bvhMs: 0, handoffMs: 0, totalMs: 0,
});

function statsOf(a: MergedArrays, edgesSkipped: boolean, bvh: 'worker' | 'lazy'): ModelStats {
  return {
    elements: a.elementCount, triangles: a.index.length / 3, vertices: a.position.length / 3, edgeSegments: a.edgePosition.length / 6,
    edgesSkipped, bvh, bufferBytes: bufferBytes(a),
  };
}

export async function importIfc(inputs: IfcInput[], opts: ImportOptions = {}): Promise<ImportResult> {
  if (!IFC_READER_AVAILABLE) throw new IfcReaderUnavailable();
  const t0 = performance.now();
  const edges = opts.edges ?? 'auto';

  if (!opts.forceMainThread && !opts.viaGlb) {
    try {
      return await importInWorker(inputs, opts, t0);
    } catch (e) {
      if (!(e instanceof WorkerUnavailable)) throw e;
      console.info('[ifc-import] worker unavailable, reading on the main thread:', e.message);
    }
  }

  // Main-thread path: extract with event-loop yields, then build synchronously.
  const raws = await extractOnMainThread(inputs, opts);
  const t1 = performance.now();
  opts.onProgress?.({ phase: 'build' });
  await nextTick(); // let the status text paint before the (synchronous) build
  if (opts.signal?.aborted) throw new ImportCancelled();
  const summaries = raws.map((r) => ({ fileName: r.fileName, schema: r.schema, elements: r.elements.length, stats: r.stats }));
  const timings = zeroTimings();
  timings.meshMs = t1 - t0;
  if (opts.viaGlb) {
    const data = buildModelData(raws);
    const loaded = await parseModel(data.glb, data.sidecar);
    const t2 = performance.now();
    timings.mergeMs = t2 - t1;
    timings.totalMs = t2 - t0;
    return {
      loaded, mode: 'glb', extractMs: t1 - t0, buildMs: t2 - t1, report: data.report, raws: summaries, timings,
      stats: {
        elements: loaded.model.elements.length, triangles: loaded.geometry.geometry.getIndex()!.count / 3,
        vertices: loaded.geometry.geometry.getAttribute('position').count,
        edgeSegments: loaded.geometry.edges.getAttribute('position').count / 2, edgesSkipped: false, bvh: 'lazy', bufferBytes: 0,
      },
    };
  }
  const built = buildMergedData(raws, { edges, consume: true, onProgress: opts.onProgress, check: () => { if (opts.signal?.aborted) throw new ImportCancelled(); } });
  const loaded = wrap(built.head, built.records, built.arrays);
  const t2 = performance.now();
  Object.assign(timings, built.timings, { totalMs: t2 - t0 });
  return {
    loaded, mode: 'main', extractMs: t1 - t0, buildMs: t2 - t1, report: built.report, raws: summaries, timings,
    stats: statsOf(built.arrays, built.edgesSkipped, 'lazy'),
  };
}

/** Sidecar head + raw element records + merged arrays -> LoadedModel (what both direct paths end with). */
function wrap(head: Omit<Sidecar, 'elements'>, records: ElementRecord[], arrays: MergedArrays): LoadedModel {
  const elements = records.map(normaliseRecord);
  return assembleLoaded(head, elements, MergedGeometry.fromArrays(arrays));
}

async function importInWorker(inputs: IfcInput[], opts: ImportOptions, t0: number): Promise<ImportResult> {
  if (opts.signal?.aborted) throw new ImportCancelled();
  const reader = takeReader();
  const onAbort = (): void => reader.terminate();
  opts.signal?.addEventListener('abort', onAbort);
  try {
    await reader.ready; // rejects with WorkerUnavailable when the worker cannot start (nothing was transferred yet)
    const summaries: ExtractSummary[] = [];
    for (let i = 0; i < inputs.length; i++) summaries.push(await reader.extract(i, inputs[i]!, opts.props ?? 'common', opts.onProgress));
    const t1 = performance.now();
    const m = await reader.merge(opts.edges ?? 'auto', opts.bvh ?? true, opts.onProgress);
    opts.onProgress?.({ phase: 'upload', elements: m.elements.length });
    await nextTick(); // let the status text paint before the arrays are wrapped
    if (opts.signal?.aborted) throw new ImportCancelled();
    const geometry = MergedGeometry.fromArrays(m.arrays);
    await nextTick();
    const loaded = assembleLoaded(m.head, m.elements, geometry);
    const t3 = performance.now();
    const timings = zeroTimings();
    for (const s of summaries) { timings.openMs += s.openMs; timings.meshMs += s.meshMs; timings.relationsMs += s.relationsMs; }
    Object.assign(timings, m.timings, { handoffMs: t3 - m.lastWorkerMessageAt, totalMs: t3 - t0 });
    return {
      loaded, mode: 'worker', extractMs: t1 - t0, buildMs: t3 - t1, report: m.report,
      raws: summaries.map((s) => ({ fileName: s.fileName, schema: s.schema, elements: s.elements, stats: s.stats })), timings,
      stats: statsOf(m.arrays, m.edgesSkipped, m.bvhBuilt ? 'worker' : 'lazy'),
    };
  } finally {
    opts.signal?.removeEventListener('abort', onAbort);
    reader.terminate();
  }
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
          props: opts.props,
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

interface MergeOutcome {
  head: Omit<Sidecar, 'elements'>;
  elements: ElementRecord[];
  arrays: MergedArrays;
  report: BuildReport;
  edgesSkipped: boolean;
  bvhBuilt: boolean;
  timings: MergeTimings;
  lastWorkerMessageAt: number;
}

type Pending =
  | { kind: 'extract'; resolve(r: ExtractSummary): void; reject(e: Error): void; onProgress?(p: IfcProgress): void }
  | { kind: 'merge'; resolve(r: MergeOutcome): void; reject(e: Error): void; onProgress?(p: IfcProgress): void; elements: ElementRecord[] };

/**
 * One module worker with web-ifc initialised in it. `ready` settles once the wasm is up (or the worker could not start,
 * as a WorkerUnavailable). A reader serves one import and is then terminated, which hands the wasm heap back.
 */
class IfcReader {
  readonly ready: Promise<void>;
  private worker: Worker | null = null;
  private isReady = false;
  private dead = false;
  private pending: Pending | null = null;
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
      } else if (m.type === 'extracted') {
        const p = this.pending;
        if (p?.kind !== 'extract') return;
        this.pending = null;
        p.resolve(m.summary);
      } else if (m.type === 'records') {
        const p = this.pending;
        if (p?.kind === 'merge') for (let k = 0; k < m.records.length; k++) p.elements.push(normaliseRecord(m.records[k]!, m.from + k));
      } else if (m.type === 'merged') {
        const p = this.pending;
        if (p?.kind !== 'merge') return;
        this.pending = null;
        p.resolve({
          head: JSON.parse(m.headJson) as Omit<Sidecar, 'elements'>, elements: p.elements, arrays: m.arrays, report: m.report, edgesSkipped: m.edgesSkipped, bvhBuilt: m.bvhBuilt,
          timings: m.timings, lastWorkerMessageAt: performance.now(),
        });
      } else if (m.type === 'error') {
        const p = this.pending;
        this.pending = null;
        // Keep the code: the loader passes user-facing codes through and rewrites the others (ifcErrors.ts).
        const err = Object.assign(new Error(m.message), { code: m.code });
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

  /** Hand one file to the worker (its buffer is transferred, not copied). The RawModel stays in the worker. */
  extract(id: number, input: IfcInput, props: 'common' | 'none', onProgress?: (p: IfcProgress) => void): Promise<ExtractSummary> {
    return new Promise<ExtractSummary>((resolve, reject) => {
      if (this.dead || !this.worker) { reject(new Error('The IFC reader stopped')); return; }
      this.pending = { kind: 'extract', resolve, reject, onProgress };
      const msg: WorkerIn = { type: 'extract', id, fileName: input.name, data: input.data, props };
      this.worker.postMessage(msg, [input.data]);
    });
  }

  /** Merge everything extracted so far into flat arrays (and the BVH); element records arrive in chunks before the arrays. */
  merge(edges: EdgesOption, bvh: boolean, onProgress?: (p: IfcProgress) => void): Promise<MergeOutcome> {
    return new Promise<MergeOutcome>((resolve, reject) => {
      if (this.dead || !this.worker) { reject(new Error('The IFC reader stopped')); return; }
      this.pending = { kind: 'merge', resolve, reject, onProgress, elements: [] };
      this.worker.postMessage({ type: 'merge', edges, bvh } satisfies WorkerIn);
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
