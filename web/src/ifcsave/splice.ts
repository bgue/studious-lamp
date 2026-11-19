// Find the insert point of the additions block and cut the new block into the original (design 1.4). Pure over Blob.

import { scanStep } from './stepScan';

export interface OldBlock {
  begin: number;
  /** Offset of the final ENDSEC: the old block runs from `begin` to here. */
  end: number;
  base: number;
}
export interface InsertPoint {
  /** Where the new block goes. With an old block this is its first byte. */
  cut: number;
  oldBlock?: OldBlock;
}

const TAIL = 64 * 1024;
const latin1 = new TextDecoder('latin1'); // one character per byte, so string offsets are byte offsets

/** Read the last 64 KB, find the final ENDSEC and an old block before it. Falls back to a full scan when the markers do not verify. */
export async function locateInsert(blob: Blob): Promise<InsertPoint> {
  const tailStart = Math.max(0, blob.size - TAIL);
  const tail = latin1.decode(await blob.slice(tailStart).arrayBuffer());
  const iso = tail.lastIndexOf('END-ISO-10303-21');
  const endsec = iso < 0 ? -1 : tail.lastIndexOf('ENDSEC;', iso);
  if (endsec >= 0) {
    const cut = tailStart + endsec;
    const before = tail.slice(0, endsec);
    const m = /\/\* XRAY-END bytes=(\d+) \*\/\s*$/.exec(before);
    if (!m) {
      if (!before.includes('XRAY-END') && !before.includes('XRAY-BEGIN')) return { cut };
    } else {
      const begin = tailStart + m.index - Number(m[1]);
      if (begin >= 0) {
        const probe = latin1.decode(await blob.slice(begin, begin + 200).arrayBuffer());
        const h = /^\/\* XRAY-BEGIN \S+ base=(\d+)/.exec(probe);
        if (h) return { cut: begin, oldBlock: { begin, end: cut, base: Number(h[1]) } };
      }
    }
  }
  // markers did not verify: the file was edited, or its tail is longer than the window
  const s = await scanStep(blob);
  if (s.dataEnd === null) throw new Error('Not a STEP file: no ENDSEC found.');
  if (s.block) return { cut: s.block.begin, oldBlock: s.block };
  return { cut: s.dataEnd };
}

/** The pieces of the output: original up to the cut, the block, the rest of the original. Nothing is read into memory. */
export function spliceParts(blob: Blob, at: InsertPoint, blockText: string): BlobPart[] {
  return [blob.slice(0, at.cut), blockText, blob.slice(at.oldBlock?.end ?? at.cut)];
}

export const splice = (blob: Blob, at: InsertPoint, blockText: string): Blob => new Blob(spliceParts(blob, at, blockText), { type: 'application/x-step' });
