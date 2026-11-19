// The diff in a worker (design 3.2, 5.2). `diffModels` is pure; this file only moves two snapshots across the thread boundary and
// back. Protocol:
//   main -> worker  { type: 'diff', id, base, head, options? }      worker -> main  { type: 'diff', id, diff } | { type: 'error', id, message }
// The typed arrays of a snapshot (guid sketch, bounds, sig) are transferred; use `snapshotTransferables`. `runDiff` is the entry that the
// app calls: it uses a worker when one is given and falls back to the main thread, so a build without workers still diffs.

import { diffModels } from './diff';
import type { ModelSnapshot, RevisionDiff, RevisionOptions } from './types';

export type DiffIn = { type: 'diff'; id: number; base: ModelSnapshot; head: ModelSnapshot; options?: Partial<RevisionOptions> };
export type DiffOut = { type: 'diff'; id: number; diff: RevisionDiff } | { type: 'error'; id: number; message: string };

/** What the worker does with one message. Exported so tests (and the fallback) run it without a Worker. */
export function handleDiffMessage(m: DiffIn): DiffOut {
  try {
    return { type: 'diff', id: m.id, diff: diffModels(m.base, m.head, m.options) };
  } catch (e) {
    return { type: 'error', id: m.id, message: e instanceof Error ? e.message : String(e) };
  }
}

/** The ArrayBuffers of a snapshot's typed arrays, for postMessage's transfer list. After the transfer the snapshot is unusable here. */
export function snapshotTransferables(s: ModelSnapshot): ArrayBuffer[] {
  return [s.guidSketch.buffer as ArrayBuffer, s.bounds.buffer as ArrayBuffer, s.sig.buffer as ArrayBuffer];
}

export interface DiffWorkerLike {
  postMessage(message: DiffIn, transfer?: Transferable[]): void;
  addEventListener(type: 'message', fn: (ev: { data: DiffOut }) => void): void;
  removeEventListener(type: 'message', fn: (ev: { data: DiffOut }) => void): void;
}

let seq = 0;

/**
 * Diff two snapshots. With a worker the snapshots are COPIED (structured clone) when `copy` is true, so the caller keeps using them,
 * and transferred otherwise (faster, the caller must not touch them again). Without a worker the diff runs here.
 */
export function runDiff(base: ModelSnapshot, head: ModelSnapshot, o: { options?: Partial<RevisionOptions>; worker?: DiffWorkerLike | null; transfer?: boolean } = {}): Promise<RevisionDiff> {
  const w = o.worker;
  if (!w) return Promise.resolve().then(() => { const r = handleDiffMessage({ type: 'diff', id: 0, base, head, ...(o.options ? { options: o.options } : {}) }); if (r.type === 'error') throw new Error(r.message); return r.diff; });
  const id = ++seq;
  return new Promise<RevisionDiff>((resolve, reject) => {
    const on = (ev: { data: DiffOut }): void => {
      if (ev.data.id !== id) return;
      w.removeEventListener('message', on);
      if (ev.data.type === 'error') reject(new Error(ev.data.message)); else resolve(ev.data.diff);
    };
    w.addEventListener('message', on);
    const transfer = o.transfer ? [...snapshotTransferables(base), ...snapshotTransferables(head)] : [];
    w.postMessage({ type: 'diff', id, base, head, ...(o.options ? { options: o.options } : {}) }, transfer);
  });
}

// ---- worker entry: installed only inside a dedicated worker scope, so importing this module elsewhere has no side effect
interface WorkerScope { postMessage(m: unknown): void; onmessage: ((ev: { data: DiffIn }) => void) | null }
const scope = globalThis as unknown as Partial<WorkerScope> & { document?: unknown; WorkerGlobalScope?: unknown };
if (typeof scope.document === 'undefined' && typeof scope.WorkerGlobalScope !== 'undefined' && typeof scope.postMessage === 'function') {
  (scope as WorkerScope).onmessage = (ev) => (scope as WorkerScope).postMessage(handleDiffMessage(ev.data));
}
