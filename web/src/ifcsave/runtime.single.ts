// Single-file bundle: the save worker is inlined (`?worker&inline`). Same export as runtime.ts.
import SaveWorker from './saveWorker?worker&inline';

export function createSaveWorker(): Worker {
  return new SaveWorker();
}
