// Main-thread side of the save worker (design 1.8): start it, relay progress, cancel by terminating, and fall back to the
// main thread when no worker can start (the same way the importer does).

import type { ClassificationSchema } from '../classify/types';
import type { SaveOptions } from './plan';
import { runSave } from './run';
import type { SaveJob, SaveProgress, SavedFile } from './run';
import { runClean } from './clean';
import type { CleanJob, CleanMode } from './clean';
import { createSaveWorker } from './runtime';
import type { CleanedBlob, SaveWorkerIn, SaveWorkerOut } from './saveWorker';

export class SaveCancelled extends Error {
  constructor() {
    super('Save cancelled');
    this.name = 'SaveCancelled';
  }
}

export interface SaveRun {
  promise: Promise<{ files: SavedFile[]; mode: 'worker' | 'main' }>;
  cancel(): void;
}

function launch<T>(
  msg: SaveWorkerIn, direct: () => Promise<T>, pick: (m: SaveWorkerOut) => T | undefined,
  onProgress: ((p: SaveProgress) => void) | undefined, forceMain: boolean, isCancelled: () => boolean, markCancelled: () => void,
): { promise: Promise<{ value: T; mode: 'worker' | 'main' }>; cancel(): void } {
  let worker: Worker | null = null;
  let settle: ((e: Error) => void) | null = null;
  const promise = new Promise<{ value: T; mode: 'worker' | 'main' }>((resolve, reject) => {
    settle = reject;
    const main = (): void => {
      direct().then((value) => resolve({ value, mode: 'main' }), (e) => reject(isCancelled() ? new SaveCancelled() : e));
    };
    if (forceMain) { main(); return; }
    try {
      worker = createSaveWorker();
    } catch (e) {
      console.info('[ifc-save] worker unavailable, running on the main thread:', e instanceof Error ? e.message : String(e));
      main();
      return;
    }
    let got = false;
    worker.onmessage = (ev: MessageEvent<SaveWorkerOut>): void => {
      got = true;
      const m = ev.data;
      if (m.type === 'progress') { onProgress?.(m.progress); return; }
      worker?.terminate();
      worker = null;
      if (m.type === 'error') reject(Object.assign(new Error(m.message), { code: m.code }));
      else resolve({ value: pick(m) as T, mode: 'worker' });
    };
    worker.onerror = (ev): void => {
      ev.preventDefault?.();
      worker?.terminate();
      worker = null;
      if (!got && !isCancelled()) main(); // the worker script did not load: carry on here
      else reject(new Error(ev.message || 'The save worker failed'));
    };
    worker.postMessage(msg);
  });
  return {
    promise,
    cancel(): void {
      markCancelled();
      worker?.terminate();
      worker = null;
      settle?.(new SaveCancelled());
    },
  };
}

export function startSave(jobs: readonly SaveJob[], schema: ClassificationSchema, options: SaveOptions, onProgress?: (p: SaveProgress) => void, forceMain = false): SaveRun {
  let cancelled = false;
  const run = launch<SavedFile[]>(
    { type: 'save', jobs: jobs as SaveJob[], schema, options },
    () => runSave(jobs, schema, options, onProgress, () => cancelled),
    (m) => (m.type === 'saved' ? m.files : undefined),
    onProgress, forceMain, () => cancelled, () => { cancelled = true; },
  );
  return { promise: run.promise.then((r) => ({ files: r.value, mode: r.mode })), cancel: run.cancel };
}

export interface CleanRun {
  promise: Promise<{ files: CleanedBlob[]; mode: 'worker' | 'main' }>;
  cancel(): void;
}

/** Plan (`mode: 'plan'`, the report for the dialog) or write a cleaned copy. */
export function startClean(jobs: readonly CleanJob[], schema: ClassificationSchema, options: SaveOptions, mode: CleanMode, onProgress?: (p: SaveProgress) => void, forceMain = false): CleanRun {
  let cancelled = false;
  const run = launch<CleanedBlob[]>(
    { type: 'clean', jobs: jobs as CleanJob[], schema, options, mode },
    async () => (await runClean(jobs, schema, options, mode, onProgress, () => cancelled)).map((f) => ({ report: f.report, blob: mode === 'write' ? new Blob(f.parts, { type: 'application/x-step' }) : null, bytes: f.bytes, lines: f.lines })),
    (m) => (m.type === 'cleaned' ? m.files : undefined),
    onProgress, forceMain, () => cancelled, () => { cancelled = true; },
  );
  return { promise: run.promise.then((r) => ({ files: r.value, mode: r.mode })), cancel: run.cancel };
}
