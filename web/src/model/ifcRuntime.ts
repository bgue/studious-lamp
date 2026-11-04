// How the IFC reader is delivered. This is the default (dev server and normal build): the worker is a separate module
// file and the wasm is a URL served next to the app. vite.single.config.ts swaps this module for ifcRuntime.single.ts
// (worker and wasm embedded in the HTML) or ifcRuntime.none.ts (`--no-ifc`: no reader at all).
import wasmUrl from 'web-ifc/web-ifc.wasm?url';
import type { WasmSource } from './ifcRaw';

export const IFC_READER_AVAILABLE = true;

/** Start the module worker (throws when workers are unavailable). */
export function createIfcWorker(): Worker | Promise<Worker> {
  return new Worker(new URL('./ifcWorker.ts', import.meta.url), { type: 'module' });
}

/** Where the worker (or the main-thread fallback) finds the wasm. */
export async function getWasmSource(): Promise<WasmSource> {
  return { url: new URL(wasmUrl, location.href).href };
}

/** The reader itself, for the main-thread fallback. null when this build cannot offer one. */
export function loadRawReader(): Promise<typeof import('./ifcRaw')> | null {
  return import('./ifcRaw');
}
