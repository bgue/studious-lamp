// Module worker around ifcRaw.ts and ifcBuild.ts: initialises web-ifc once, extracts IFC files, then merges them into the
// flat arrays the viewer draws (and the BVH over them) without ever handing the per-element data to the main thread.
// Protocol (all messages carry plain data; typed arrays travel as transferables):
//   main -> worker  { type: 'init', wasm }                              worker -> main  { type: 'ready' }
//   main -> worker  { type: 'extract', id, fileName, data, props? }     worker -> main  { type: 'progress', id, progress }
//                                                                       worker -> main  { type: 'extracted', id, summary }
//   main -> worker  { type: 'merge', edges, bvh }                       worker -> main  { type: 'records', from, records }  (chunks)
//                                                                       worker -> main  { type: 'merged', ... }
//                                                                       worker -> main  { type: 'error', id?, code, message }
// The RawModels stay inside the worker between 'extract' and 'merge'. After the last file, web-ifc is disposed before the
// merge so its heap is not held next to the merged arrays. Cancellation is `worker.terminate()` from the main thread.
import type { IfcAPI } from 'web-ifc';
import type { ElementRecord } from '../types';
import { buildMergedData } from './ifcBuild';
import type { BuildReport, EdgesOption, Sidecar } from './ifcBuild';
import { buildBvh } from './ifcBvh';
import type { PropsMode } from './ifcProps';
import { IfcReadError, createIfcApi, extractIfc } from './ifcRaw';
import type { WasmSource } from './ifcRaw';
import type { IfcProgress, RawModel } from './ifcShared';
import { mergedTransferables } from './mergedArrays';
import type { MergedArrays } from './mergedArrays';

export type WorkerIn =
  | { type: 'init'; wasm: WasmSource }
  | { type: 'extract'; id: number; fileName: string; data: ArrayBuffer; props?: PropsMode }
  | { type: 'merge'; edges: EdgesOption; bvh: boolean };

export interface ExtractSummary {
  fileName: string;
  schema: string;
  elements: number;
  stats?: RawModel['stats'];
  /** ms spent opening the file, meshing products and reading relations/properties */
  openMs: number;
  meshMs: number;
  relationsMs: number;
}

export interface MergeTimings {
  prepareMs: number;
  mergeMs: number;
  edgesMs: number;
  bvhMs: number;
  /** web-ifc heap release (dispose) before the merge */
  releaseMs: number;
}

export type WorkerOut =
  | { type: 'ready' }
  | { type: 'progress'; id: number; progress: IfcProgress }
  | { type: 'extracted'; id: number; summary: ExtractSummary }
  | { type: 'records'; from: number; records: ElementRecord[] }
  | {
    type: 'merged';
    /** JSON of the sidecar without elements: one string is much cheaper to hand over than 100k small relation arrays. */
    headJson: string;
    arrays: MergedArrays;
    report: BuildReport;
    edgesSkipped: boolean;
    bvhBuilt: boolean;
    timings: MergeTimings;
  }
  | { type: 'error'; id?: number; code: string; message: string };

/** Element records travel in messages of this many, so no single message takes long to deserialise on the main thread. */
export const RECORD_CHUNK = 2000;

interface Ctx {
  postMessage(message: unknown, transfer?: Transferable[]): void;
  onmessage: ((ev: MessageEvent<WorkerIn>) => void) | null;
}
const ctx = self as unknown as Ctx;
const post = (m: WorkerOut, transfer?: Transferable[]): void => ctx.postMessage(m, transfer);

let api: IfcAPI | null = null;
let raws: RawModel[] = [];

/** Hand web-ifc's wasm heap back: close what is open, drop the instance. */
function releaseApi(): number {
  const t = performance.now();
  if (api) {
    try { api.Dispose(); } catch { /* ignore */ }
    api = null;
  }
  return performance.now() - t;
}

ctx.onmessage = async (ev) => {
  const msg = ev.data;
  try {
    if (msg.type === 'init') {
      api = await createIfcApi(msg.wasm);
      post({ type: 'ready' });
    } else if (msg.type === 'extract') {
      if (!api) throw new IfcReadError('The IFC reader is not initialised', 'wasm');
      let tOpen = performance.now();
      let tMesh = 0;
      let tRel = 0;
      const raw = await extractIfc(api, new Uint8Array(msg.data), msg.fileName, {
        props: msg.props,
        onProgress: (progress) => {
          const now = performance.now();
          if (progress.phase === 'open') tOpen = now;
          else if (progress.phase === 'meshing' && progress.done === 0) tMesh = now;
          else if (progress.phase === 'relations') tRel = now;
          post({ type: 'progress', id: msg.id, progress });
        },
      });
      const t1 = performance.now();
      raws.push(raw);
      post({
        type: 'extracted', id: msg.id,
        summary: {
          fileName: raw.fileName, schema: raw.schema, elements: raw.elements.length, stats: raw.stats,
          openMs: (tMesh || t1) - tOpen, meshMs: (tRel || t1) - (tMesh || t1), relationsMs: t1 - (tRel || t1),
        },
      });
    } else if (msg.type === 'merge') {
      const releaseMs = releaseApi();
      const input = raws;
      raws = [];
      const built = buildMergedData(input, {
        edges: msg.edges,
        consume: true,
        onProgress: (progress) => post({ type: 'progress', id: -1, progress }), // buildMergedData throttles itself
      });
      input.length = 0;
      for (let i = 0; i < built.records.length; i += RECORD_CHUNK) {
        post({ type: 'records', from: i, records: built.records.slice(i, i + RECORD_CHUNK) });
      }
      built.records.length = 0;
      let bvhMs = 0;
      let bvhBuilt = false;
      if (msg.bvh && built.arrays.index.length > 0) {
        const t = performance.now();
        let lastPct = -1;
        post({ type: 'progress', id: -1, progress: { phase: 'bvh', percent: 0, triangles: built.arrays.index.length / 3 } });
        built.arrays.bvh = buildBvh(built.arrays, (f) => {
          const pct = Math.floor(f * 20) * 5;
          if (pct !== lastPct) {
            lastPct = pct;
            post({ type: 'progress', id: -1, progress: { phase: 'bvh', percent: pct, triangles: built.arrays.index.length / 3 } });
          }
        });
        bvhMs = performance.now() - t;
        bvhBuilt = true;
      }
      post({ type: 'progress', id: -1, progress: { phase: 'transfer' } });
      post({
        type: 'merged', headJson: JSON.stringify(built.head), arrays: built.arrays, report: built.report, edgesSkipped: built.edgesSkipped, bvhBuilt,
        timings: { ...built.timings, bvhMs, releaseMs },
      }, mergedTransferables(built.arrays));
    }
  } catch (e) {
    const id = msg.type === 'extract' ? msg.id : undefined;
    if (e instanceof IfcReadError) post({ type: 'error', id, code: e.code, message: e.message });
    else {
      const text = e instanceof Error ? e.message : String(e);
      const oom = /memory|alloc|abort/i.test(text);
      post({
        // 'reader': web-ifc's own error text; the loader shows a friendly line and logs this (ifcErrors.ts).
        type: 'error', id, code: oom ? 'memory' : 'reader',
        message: oom ? 'The IFC file is too large for the browser to read (out of memory)' : `IFC reader failed: ${text}`,
      });
    }
  }
};
