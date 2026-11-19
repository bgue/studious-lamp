// The save pipeline over Blobs, shared by the worker and the main-thread fallback (design 1.8). Pure: no DOM, no WASM.
// Each source is read only at its last 64 KB (locateInsert); the output is slices of the source plus the new block.

import type { ClassificationSchema } from '../classify/types';
import { emitAdditions } from './additions';
import type { FileSavePlan, SaveOptions } from './plan';
import { locateInsert, spliceParts } from './splice';

export interface SaveJob {
  plan: FileSavePlan;
  blob: Blob;
}

export type SavePhase = 'locate' | 'emit' | 'splice';
export interface SaveProgress {
  phase: SavePhase;
  file: string;
  done: number;
  total: number;
}

export interface SavedFile {
  fileName: string;
  /** Name of the output: `<stem>.xray.ifc`. */
  outName: string;
  /** Slices of the original and the new block, in order. `new Blob(parts)` is the file. */
  parts: BlobPart[];
  /** Entity lines written (the markers not counted). */
  lines: number;
  /** Elements that carry data. */
  elements: number;
  /** Size of the output file. */
  bytes: number;
  /** An earlier Xray block of the file was replaced. */
  replaced: boolean;
}

/** `Model.ifc` -> `Model.xray.ifc`; a name that already ends `.xray.ifc` keeps it (so a re-saved file gets the same name). */
export function outputName(fileName: string): string {
  const stem = fileName.replace(/\.(ifc|ifczip)$/i, '').replace(/\.xray$/i, '');
  return `${stem}.xray.ifc`;
}

export async function runSave(
  jobs: readonly SaveJob[], schema: ClassificationSchema, o: SaveOptions,
  onProgress?: (p: SaveProgress) => void, cancelled?: () => boolean,
): Promise<SavedFile[]> {
  const out: SavedFile[] = [];
  const total = jobs.length;
  for (const [i, j] of jobs.entries()) {
    if (cancelled?.()) throw new Error('Save cancelled');
    const file = j.plan.fileName;
    onProgress?.({ phase: 'locate', file, done: i, total });
    const at = await locateInsert(j.blob);
    // The old block (ours) decides where the new ids start; it also holds its own classification lines.
    const base = at.oldBlock ? at.oldBlock.base : j.plan.base;
    const plan: FileSavePlan = { ...j.plan, base, existingClassifications: j.plan.existingClassifications.filter((c) => c.id <= base) };
    onProgress?.({ phase: 'emit', file, done: i, total });
    const add = emitAdditions(plan, schema, o);
    onProgress?.({ phase: 'splice', file, done: i, total });
    const parts = spliceParts(j.blob, at, add.text);
    const kept = j.blob.size - (at.oldBlock ? at.oldBlock.end - at.oldBlock.begin : 0);
    out.push({
      fileName: file, outName: outputName(file), parts, lines: add.lines, elements: plan.elements.length,
      bytes: kept + new TextEncoder().encode(add.text).length, replaced: !!at.oldBlock,
    });
    onProgress?.({ phase: 'splice', file, done: i + 1, total });
  }
  return out;
}
