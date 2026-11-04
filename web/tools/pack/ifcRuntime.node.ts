// Stand-in for src/model/ifcRuntime.ts in the node reader bundle (the real one imports a vite-only `?url` asset).
// Nothing in the node path uses a worker; the wasm path is passed to createIfcApi directly.
import type { WasmSource } from '../../src/model/ifcRaw';

export const IFC_READER_AVAILABLE = true;

export function createIfcWorker(): Worker {
  throw new Error('no workers in node');
}

export async function getWasmSource(): Promise<WasmSource> {
  throw new Error('pass the wasm path to convertIfc');
}

export function loadRawReader(): null {
  return null;
}
