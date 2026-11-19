// Main-thread side of the save worker (design 1.8): start it, relay progress, cancel by terminating, and fall back to the
// main thread when no worker can start (the same way the importer does).

import type { ClassificationSchema } from '../classify/types';
import type { SaveOptions } from './plan';
import { runSave } from './run';
import type { SaveJob, SaveProgress, SavedFile } from './run';
import { createSaveWorker } from './runtime';
import type { SaveWorkerOut } from './saveWorker';

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

export function startSave(jobs: readonly SaveJob[], schema: ClassificationSchema, options: SaveOptions, onProgress?: (p: SaveProgress) => void, forceMain = false): SaveRun {
  let cancelled = false;
  let worker: Worker | null = null;
  let settle: ((e: Error) => void) | null = null;
  const promise = new Promise<{ files: SavedFile[]; mode: 'worker' | 'main' }>((resolve, reject) => {
    settle = reject;
    const main = (): void => {
      runSave(jobs, schema, options, onProgress, () => cancelled).then((files) => resolve({ files, mode: 'main' }), (e) => reject(cancelled ? new SaveCancelled() : e));
    };
    if (forceMain) { main(); return; }
    try {
      worker = createSaveWorker();
    } catch (e) {
      console.info('[ifc-save] worker unavailable, saving on the main thread:', e instanceof Error ? e.message : String(e));
      main();
      return;
    }
    let got = false;
    worker.onmessage = (ev: MessageEvent<SaveWorkerOut>): void => {
      got = true;
      const m = ev.data;
      if (m.type === 'progress') onProgress?.(m.progress);
      else if (m.type === 'saved') { worker?.terminate(); worker = null; resolve({ files: m.files, mode: 'worker' }); }
      else { worker?.terminate(); worker = null; reject(Object.assign(new Error(m.message), { code: m.code })); }
    };
    worker.onerror = (ev): void => {
      ev.preventDefault?.();
      worker?.terminate();
      worker = null;
      if (!got && !cancelled) main(); // the worker script did not load: carry on here
      else reject(new Error(ev.message || 'The save worker failed'));
    };
    worker.postMessage({ type: 'save', jobs, schema, options });
  });
  return {
    promise,
    cancel(): void {
      cancelled = true;
      worker?.terminate();
      worker = null;
      settle?.(new SaveCancelled());
    },
  };
}
