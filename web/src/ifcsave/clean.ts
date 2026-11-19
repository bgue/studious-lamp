// The cleaned copy pipeline (design 2.3, 2.4), shared by the worker and the main-thread fallback. Pure over Blobs: no DOM, no WASM.
// The whole source is read into memory once (limit 1 GB), indexed, planned and written as chunks.

import type { ClassificationSchema } from '../classify/types';
import { emitAdditions } from './additions';
import { writePatched } from './patch';
import type { ElementSave, FileSavePlan, SaveOptions } from './plan';
import { planRemoval } from './removal';
import type { KeptElement, RemovalStats } from './removal';
import type { SaveProgress } from './run';
import { indexStep } from './stepIndex';

/** Sources above this are refused for a cleaned copy (plain Save IFC has no limit). */
export const CLEAN_LIMIT_BYTES = 1024 * 1024 * 1024;

export interface CleanCandidate {
  expressId: number;
  globalId: string;
  rules: string[];
  reasons: string[];
}

export interface CleanJob {
  /** Classification and review data of the elements of this file (cleanup marks are made here, from `candidates`). */
  plan: FileSavePlan;
  blob: Blob;
  /** The elements to remove: what cleanup hid (and, when asked, what the user hid by hand). */
  candidates: CleanCandidate[];
  removeHostsAnyway: boolean;
  /** Plain Save IFC of a file whose Xray lines lost their markers (design 1.4): nothing is removed but the old lines, and no note is written. */
  plain?: boolean;
}

export type CleanMode = 'plan' | 'write';

export interface CleanReport {
  fileName: string;
  outName: string;
  sourceBytes: number;
  schema: string;
  asked: number;
  removed: number;
  cascaded: number;
  /** Elements kept, with the reason and what cleanup said about them. */
  kept: Array<KeptElement & { globalId: string; rules: string[]; reasons: string[] }>;
  stats: RemovalStats;
  warnings: string[];
  /** An earlier Xray block was dropped and written again. */
  blockReplaced: boolean;
  /** Property sets and relations of Xray found without their markers (a file that went through another tool): removed. */
  foreignXrayLines: number;
}

export interface CleanedFile {
  report: CleanReport;
  /** Slices and chunks of the output, in order. Empty in `plan` mode. */
  parts: BlobPart[];
  bytes: number;
  /** Entity lines of the new block. */
  lines: number;
}

/** `Model.ifc` -> `Model.cleaned.ifc`. */
export function cleanedName(fileName: string): string {
  const stem = fileName.replace(/\.(ifc|ifczip)$/i, '').replace(/\.(xray|cleaned)$/i, '');
  return `${stem}.cleaned.ifc`;
}

export class CleanRefused extends Error {
  constructor(message: string, readonly code: string) {
    super(message);
    this.name = 'CleanRefused';
  }
}

export async function runClean(
  jobs: readonly CleanJob[], schema: ClassificationSchema, o: SaveOptions, mode: CleanMode,
  onProgress?: (p: SaveProgress) => void, cancelled?: () => boolean,
): Promise<CleanedFile[]> {
  const out: CleanedFile[] = [];
  const total = jobs.length;
  for (const [i, j] of jobs.entries()) {
    const file = j.plan.fileName;
    const check = (): void => { if (cancelled?.()) throw new Error('Save cancelled'); };
    check();
    if (j.blob.size > CLEAN_LIMIT_BYTES) throw new CleanRefused(`${file} is larger than 1 GB: a cleaned copy of a file this size is not supported. Plain Save IFC works on it.`, 'too-large');
    onProgress?.({ phase: 'read', file, done: i, total });
    let bytes: Uint8Array | null = new Uint8Array(await j.blob.arrayBuffer());
    check();
    onProgress?.({ phase: 'index', file, done: i, total });
    const ix = indexStep(bytes, (d, t) => onProgress?.({ phase: 'index', file, done: i + d / t, total }));
    check();
    onProgress?.({ phase: 'plan', file, done: i, total });
    const baseId = ix.block ? ix.block.base : ix.maxId;
    const rp = planRemoval(ix, bytes, j.candidates.map((c) => c.expressId), { removeHostsAnyway: j.removeHostsAnyway });
    const byId = new Map(j.candidates.map((c) => [c.expressId, c] as const));
    const kept = rp.kept.map((k) => {
      const c = byId.get(k.expressId);
      return { ...k, globalId: c?.globalId ?? '', rules: c?.rules ?? [], reasons: c?.reasons ?? [] };
    });
    const report: CleanReport = {
      fileName: file, outName: cleanedName(file), sourceBytes: j.blob.size, schema: j.plan.family,
      asked: j.candidates.length, removed: rp.removed.length, cascaded: rp.cascaded.length, kept, stats: rp.stats, warnings: rp.warnings,
      blockReplaced: !!ix.block, foreignXrayLines: ix.ourNamedRows.length,
    };
    if (mode === 'plan') {
      out.push({ report, parts: [], bytes: 0, lines: 0 });
      bytes = null;
      continue;
    }
    // the block: classification of what stays, marks on what was kept
    const base = baseId;
    const gone = new Set(rp.removed);
    const keptBy = new Map(rp.kept.map((k) => [k.expressId, k.because] as const));
    const elements: ElementSave[] = [];
    const seen = new Set<number>();
    for (const e of j.plan.elements) {
      if (gone.has(e.expressId)) continue;
      seen.add(e.expressId);
      const why = keptBy.get(e.expressId);
      const c = byId.get(e.expressId);
      elements.push(why !== undefined && c && o.includeCleanupMarks ? { ...e, cleanup: { rules: c.rules, reasons: c.reasons, keptBecause: why } } : { ...e });
    }
    if (o.includeCleanupMarks)
      for (const [id, why] of keptBy) {
        const c = byId.get(id);
        if (c && !seen.has(id)) elements.push({ expressId: id, globalId: c.globalId, cleanup: { rules: c.rules, reasons: c.reasons, keptBecause: why } });
      }
    elements.sort((a, b) => a.expressId - b.expressId);
    const plan: FileSavePlan = { ...j.plan, base, existingClassifications: j.plan.existingClassifications.filter((c) => c.id <= base), elements };
    onProgress?.({ phase: 'emit', file, done: i, total });
    const add = emitAdditions(plan, schema, o, j.plain ? undefined : `removed=${rp.removed.length} kept=${rp.kept.length}`);
    check();
    onProgress?.({ phase: 'write', file, done: i, total });
    const parts = writePatched(bytes, ix, rp, add.text);
    bytes = null;
    let size = 0;
    for (const p of parts) size += (p as Uint8Array).byteLength;
    out.push({ report, parts, bytes: size, lines: add.lines });
    onProgress?.({ phase: 'write', file, done: i + 1, total });
  }
  return out;
}
