// The retained source of a loaded IFC (design 1.3). The user's File (or a Blob of unzipped / embedded bytes) stays in memory as a
// disk-backed handle; the facts the writer needs were captured at import. A source is never serialised: not in params, links, views,
// presets or packed pages. Pure apart from Blob reads (works in node).

import type { LoadedModel } from '../model/loader';
import type { SaveInfo } from '../model/ifcShared';
import type { IfcSourceInfo } from './plan';
import { scanStep } from './stepScan';

export type { SaveInfo };

export interface IfcSource extends IfcSourceInfo {
  /** The user's File, or a Blob of the unzipped / embedded bytes. */
  blob: Blob;
}

/** Sources of the model on screen, set by fileLoader after the import (or by an attach). */
export const sourcesOf = new WeakMap<LoadedModel, IfcSource[]>();

/** Duplicate elements the federation dropped (they exist only in the first file): their twin in a later file gets no data. */
export const duplicatesOf = new WeakMap<LoadedModel, number>();

export function makeSource(fileName: string, blob: Blob, schema: string, info: SaveInfo | undefined): IfcSource {
  return {
    fileName,
    blob,
    schema,
    maxExpressId: info?.maxExpressId ?? 0,
    ownerHistoryId: info?.ownerHistoryId ?? null,
    classifications: info?.classifications ?? [],
    blockBase: info?.blockBase ?? null,
  };
}

const latin1 = new TextDecoder('latin1');
const TAIL = 64 * 1024;

/**
 * `base=` of the XRAY-BEGIN marker of a file that carries our block, read from the last 64 KB the way `locateInsert` does;
 * null when the file has none (or the markers do not verify: `locateInsert` then scans at save time).
 */
export function tailBlockBase(bytes: Uint8Array): number | null {
  const start = Math.max(0, bytes.length - TAIL);
  const tail = latin1.decode(bytes.subarray(start));
  const iso = tail.lastIndexOf('END-ISO-10303-21');
  const endsec = iso < 0 ? -1 : tail.lastIndexOf('ENDSEC;', iso);
  if (endsec < 0) return null;
  const m = /\/\* XRAY-END bytes=(\d+) \*\/\s*$/.exec(tail.slice(0, endsec));
  if (!m) return null;
  const begin = start + m.index - Number(m[1]);
  if (begin < 0) return null;
  const h = /^\/\* XRAY-BEGIN \S+ base=(\d+)/.exec(latin1.decode(bytes.subarray(begin, begin + 200)));
  return h ? Number(h[1]) : null;
}

/** Every IfcClassification of our own old block has an id above its base: they are not the file's own systems. */
export const ownClassifications = <T extends { id: number }>(list: readonly T[], blockBase: number | null): T[] => (blockBase === null ? [...list] : list.filter((c) => c.id <= blockBase));

export interface AttachCheck {
  ok: boolean;
  /** Records whose (expressId -> GlobalId) pair was found in the file. */
  matched: number;
  total: number;
  fraction: number;
  info?: SaveInfo;
  schema?: string;
}

/** Minimum share of the records that must be found in a file picked to be the source (design 1.3). */
export const ATTACH_MIN_FRACTION = 0.99;

/**
 * Is `blob` the file the records came from? Streams the file once (`stepScan`) and compares the `(expressId -> GlobalId)` pairs.
 * An old block of ours inside the file is fine: its lines have ids above `base` and no element has one of those.
 */
export async function checkAttach(blob: Blob, records: ReadonlyArray<{ expressId?: number; globalId: string; file?: string }>, fileName?: string): Promise<AttachCheck> {
  const mine = records.filter((r) => r.expressId !== undefined && (fileName === undefined || r.file === undefined || r.file === fileName));
  const scan = await scanStep(blob, { wantGuids: mine.map((r) => r.expressId!) });
  let matched = 0;
  for (const r of mine) {
    const g = scan.guidOf.get(r.expressId!);
    // a federation suffixes a GlobalId clash with ~n: compare without it
    if (g !== undefined && (g === r.globalId || g === r.globalId.replace(/~\d+$/, ''))) matched++;
  }
  const fraction = mine.length === 0 ? 0 : matched / mine.length;
  const base = scan.block?.base ?? null;
  return {
    ok: mine.length > 0 && fraction >= ATTACH_MIN_FRACTION,
    matched, total: mine.length, fraction,
    schema: scan.schema,
    info: { maxExpressId: scan.maxExpressId, ownerHistoryId: scan.ownerHistoryId, classifications: ownClassifications(scan.classifications, base), blockBase: base },
  };
}
