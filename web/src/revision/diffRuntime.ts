// Starts the diff worker (design 5.2). A page that cannot start one (a single-file build opened from file:, no Worker) gets null and
// the diff runs on the main thread: `runDiff` takes either. The diff of a 50 k element model is well under a second, so the fallback is fine.

import type { DiffWorkerLike } from './diffWorker';

export function createDiffWorker(): (DiffWorkerLike & { terminate(): void }) | null {
  try {
    if (typeof Worker === 'undefined' || (typeof document !== 'undefined' && document.URL.startsWith('file:'))) return null;
    return new Worker(new URL('./diffWorker.ts', import.meta.url), { type: 'module' }) as unknown as DiffWorkerLike & { terminate(): void };
  } catch {
    return null;
  }
}
