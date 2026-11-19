// How the save worker is delivered. Default (dev server, normal build): a separate module worker file.
// vite.single.config.ts swaps this module for runtime.single.ts (the worker inlined as a Blob worker).
export function createSaveWorker(): Worker {
  return new Worker(new URL('./saveWorker.ts', import.meta.url), { type: 'module' });
}
