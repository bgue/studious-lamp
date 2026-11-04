// `--no-ifc` single-file build: no IFC reader, no worker, no wasm. Same exports as ifcRuntime.ts.
import type { WasmSource } from './ifcRaw';

export const IFC_READER_AVAILABLE = false;

export function createIfcWorker(): Worker | Promise<Worker> {
  throw new Error('This build does not include the IFC reader');
}

export async function getWasmSource(): Promise<WasmSource> {
  throw new Error('This build does not include the IFC reader');
}

export function loadRawReader(): Promise<typeof import('./ifcRaw')> | null {
  return null;
}
