// How the point cloud worker is delivered. Default (dev server, normal build): a separate module file.
// vite.single.config.ts swaps this module for workerRuntime.single.ts, which inlines the worker as a Blob worker.
export function createCloudWorker(): Worker {
  return new Worker(new URL('./worker.ts', import.meta.url), { type: 'module' });
}
