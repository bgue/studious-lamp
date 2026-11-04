// Single-file bundle: the worker script is inlined into the JS (a Blob worker), so no extra chunk is emitted.
import CloudWorker from './worker?worker&inline';

export function createCloudWorker(): Worker {
  return new CloudWorker();
}
