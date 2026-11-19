// Single-file bundle: no diff worker (it would be a second chunk). `runDiff` runs on the main thread, which is what a page opened from
// file: does anyway; the diff of a 50 k element model is well under a second. Same export as diffRuntime.ts.

import type { DiffWorkerLike } from './diffWorker';

export function createDiffWorker(): (DiffWorkerLike & { terminate(): void }) | null {
  return null;
}
