// Module worker around run.ts (design 1.8). Blobs cross the boundary by reference; the original is never read beyond its last 64 KB.
//   main -> worker  { type: 'save', jobs, schema, options }
//   worker -> main  { type: 'progress', progress }  then  { type: 'saved', files }  or  { type: 'error', message }
// Cancel is `worker.terminate()` from the main thread.
import type { ClassificationSchema } from '../classify/types';
import type { SaveOptions } from './plan';
import { runSave } from './run';
import type { SaveJob, SaveProgress, SavedFile } from './run';

export type SaveWorkerIn = { type: 'save'; jobs: SaveJob[]; schema: ClassificationSchema; options: SaveOptions };
export type SaveWorkerOut =
  | { type: 'progress'; progress: SaveProgress }
  | { type: 'saved'; files: SavedFile[] }
  | { type: 'error'; message: string; code?: string };

interface Ctx {
  postMessage(message: unknown): void;
  onmessage: ((ev: MessageEvent<SaveWorkerIn>) => void) | null;
}
const ctx = self as unknown as Ctx;
const post = (m: SaveWorkerOut): void => ctx.postMessage(m);

ctx.onmessage = async (ev) => {
  const msg = ev.data;
  if (msg.type !== 'save') return;
  try {
    const files = await runSave(msg.jobs, msg.schema, msg.options, (progress) => post({ type: 'progress', progress }));
    post({ type: 'saved', files });
  } catch (e) {
    post({ type: 'error', message: e instanceof Error ? e.message : String(e), code: (e as { code?: string })?.code });
  }
};
