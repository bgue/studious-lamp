// Module worker around ifcRaw.ts: initialises web-ifc once, then extracts IFC files into RawModels, posting progress
// and transferring the typed arrays back. Protocol (all messages carry plain data):
//   main -> worker  { type: 'init', wasm }                        worker -> main  { type: 'ready' }
//   main -> worker  { type: 'extract', id, fileName, data }       worker -> main  { type: 'progress', id, progress }
//                                                                 worker -> main  { type: 'done', id, raw }
//                                                                 worker -> main  { type: 'error', id?, code, message }
// Cancellation is `worker.terminate()` from the main thread.
import type { IfcAPI } from 'web-ifc';
import { IfcReadError, createIfcApi, extractIfc, rawTransferables } from './ifcRaw';
import type { WasmSource } from './ifcRaw';
import type { IfcProgress, RawModel } from './ifcShared';

export type WorkerIn =
  | { type: 'init'; wasm: WasmSource }
  | { type: 'extract'; id: number; fileName: string; data: ArrayBuffer };

export type WorkerOut =
  | { type: 'ready' }
  | { type: 'progress'; id: number; progress: IfcProgress }
  | { type: 'done'; id: number; raw: RawModel }
  | { type: 'error'; id?: number; code: string; message: string };

interface Ctx {
  postMessage(message: unknown, transfer?: Transferable[]): void;
  onmessage: ((ev: MessageEvent<WorkerIn>) => void) | null;
}
const ctx = self as unknown as Ctx;
const post = (m: WorkerOut, transfer?: Transferable[]): void => ctx.postMessage(m, transfer);

let api: IfcAPI | null = null;

ctx.onmessage = async (ev) => {
  const msg = ev.data;
  try {
    if (msg.type === 'init') {
      api = await createIfcApi(msg.wasm);
      post({ type: 'ready' });
    } else if (msg.type === 'extract') {
      if (!api) throw new IfcReadError('The IFC reader is not initialised', 'wasm');
      const raw = await extractIfc(api, new Uint8Array(msg.data), msg.fileName, {
        onProgress: (progress) => post({ type: 'progress', id: msg.id, progress }),
      });
      post({ type: 'done', id: msg.id, raw }, rawTransferables(raw));
    }
  } catch (e) {
    const id = msg.type === 'extract' ? msg.id : undefined;
    if (e instanceof IfcReadError) post({ type: 'error', id, code: e.code, message: e.message });
    else {
      const text = e instanceof Error ? e.message : String(e);
      const oom = /memory|alloc|abort/i.test(text);
      post({
        type: 'error', id, code: oom ? 'memory' : 'invalid',
        message: oom ? 'The IFC file is too large for the browser to read (out of memory)' : `IFC reader failed: ${text}`,
      });
    }
  }
};
