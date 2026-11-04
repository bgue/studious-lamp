// Single-file bundle with the IFC reader. Both heavy parts travel gzipped + base64 in the HTML (written by
// tools/build-single-file.mjs) and are inflated with DecompressionStream at run time:
//   window.__xrayIfcWorkerGz  the worker script (a classic script, built by vite from ifcWorker.ts) -> Blob worker
//   window.__xrayIfcWasm      web-ifc.wasm, handed to the worker, which serves it to web-ifc through a Blob URL
// Same exports as ifcRuntime.ts.
import workerFileUrl from './ifcWorker?worker&url';
import type { WasmSource } from './ifcRaw';

declare global {
  interface Window {
    /** gzip + base64 of the worker script. */
    __xrayIfcWorkerGz?: string;
    /** gzip + base64 of web-ifc.wasm (plain base64 when __xrayIfcWasmEnc is not 'gzip'). */
    __xrayIfcWasm?: string;
    __xrayIfcWasmEnc?: string;
    /** Where vite put the worker file (unused at run time; the side effect keeps the import, so vite emits the file). */
    __xrayIfcWorkerFile?: string;
  }
}

window.__xrayIfcWorkerFile = workerFileUrl;

export const IFC_READER_AVAILABLE = true;

async function inflate(b64: string): Promise<Uint8Array> {
  const bin = atob(b64);
  const packed = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) packed[i] = bin.charCodeAt(i);
  if (typeof DecompressionStream === 'undefined') throw new Error('This browser cannot unpack the embedded IFC reader (no DecompressionStream)');
  const stream = new Blob([packed as BlobPart]).stream().pipeThrough(new DecompressionStream('gzip'));
  return new Uint8Array(await new Response(stream).arrayBuffer());
}

export async function createIfcWorker(): Promise<Worker> {
  const gz = window.__xrayIfcWorkerGz;
  if (!gz) throw new Error('The embedded IFC worker is missing from this page');
  const code = await inflate(gz);
  const url = URL.createObjectURL(new Blob([code as BlobPart], { type: 'text/javascript' }));
  try {
    return new Worker(url);
  } finally {
    // the worker keeps running after its script URL is revoked
    setTimeout(() => URL.revokeObjectURL(url), 10000);
  }
}

export async function getWasmSource(): Promise<WasmSource> {
  const b64 = window.__xrayIfcWasm;
  if (!b64) throw new Error('The embedded IFC wasm is missing from this page');
  if (window.__xrayIfcWasmEnc === 'gzip') return { bytes: await inflate(b64) };
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return { bytes };
}

// The reader code is only inside the worker; a second copy for a main-thread fallback would add its whole size again.
export function loadRawReader(): Promise<typeof import('./ifcRaw')> | null {
  return null;
}
