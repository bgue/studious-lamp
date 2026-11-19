// Module worker around run.ts (design 1.8). Blobs cross the boundary by reference; the original is never read beyond its last 64 KB.
//   main -> worker  { type: 'save', jobs, schema, options }   or  { type: 'clean', jobs, schema, options, mode }
//   worker -> main  { type: 'progress', progress }  then  { type: 'saved', files } / { type: 'cleaned', files }  or  { type: 'error', message }
// Cancel is `worker.terminate()` from the main thread.
import type { ClassificationSchema } from '../classify/types';
import type { SaveOptions } from './plan';
import { runClean } from './clean';
import type { CleanJob, CleanMode, CleanReport } from './clean';
import { runSave } from './run';
import type { SaveJob, SaveProgress, SavedFile } from './run';

/** A cleaned file as it crosses the worker boundary: the output is one Blob (passed by reference), not a list of chunks. */
export interface CleanedBlob {
  report: CleanReport;
  blob: Blob | null;
  bytes: number;
  lines: number;
}

export type SaveWorkerIn =
  | { type: 'save'; jobs: SaveJob[]; schema: ClassificationSchema; options: SaveOptions }
  | { type: 'clean'; jobs: CleanJob[]; schema: ClassificationSchema; options: SaveOptions; mode: CleanMode };
export type SaveWorkerOut =
  | { type: 'progress'; progress: SaveProgress }
  | { type: 'saved'; files: SavedFile[] }
  | { type: 'cleaned'; files: CleanedBlob[] }
  | { type: 'error'; message: string; code?: string };

interface Ctx {
  postMessage(message: unknown): void;
  onmessage: ((ev: MessageEvent<SaveWorkerIn>) => void) | null;
}
const ctx = self as unknown as Ctx;
const post = (m: SaveWorkerOut): void => ctx.postMessage(m);

ctx.onmessage = async (ev) => {
  const msg = ev.data;
  try {
    if (msg.type === 'clean') {
      const done = await runClean(msg.jobs, msg.schema, msg.options, msg.mode, (progress) => post({ type: 'progress', progress }));
      post({ type: 'cleaned', files: done.map((f) => ({ report: f.report, blob: msg.mode === 'write' ? new Blob(f.parts, { type: 'application/x-step' }) : null, bytes: f.bytes, lines: f.lines })) });
      return;
    }
    if (msg.type !== 'save') return;
    const files = await runSave(msg.jobs, msg.schema, msg.options, (progress) => post({ type: 'progress', progress }));
    post({ type: 'saved', files });
  } catch (e) {
    post({ type: 'error', message: e instanceof Error ? e.message : String(e), code: (e as { code?: string })?.code });
  }
};
