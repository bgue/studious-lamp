// Write the patched file (design 2.4): the original bytes in order, without the deleted lines, with rewritten lines in place, and the new
// block just before the final ENDSEC. The output is a list of chunks (about 4 MB each), so a Blob can be made from it without one huge buffer.

import { latin1Encode } from './removal';
import type { RemovalPlan } from './removal';
import type { StepIndex } from './stepIndex';

const CHUNK = 4 * 1024 * 1024;

export function writePatched(bytes: Uint8Array, ix: StepIndex, plan: RemovalPlan, blockText: string): BlobPart[] {
  const parts: BlobPart[] = [];
  let buf = new Uint8Array(CHUNK);
  let used = 0;
  const flush = (): void => {
    if (used === 0) return;
    parts.push(used === buf.length ? buf : buf.slice(0, used));
    buf = new Uint8Array(CHUNK);
    used = 0;
  };
  const put = (src: Uint8Array, from = 0, to = src.length): void => {
    while (from < to) {
      const take = Math.min(to - from, buf.length - used);
      buf.set(src.subarray(from, from + take), used);
      used += take;
      from += take;
      if (used === buf.length) flush();
    }
  };

  const insertAt = ix.block ? ix.block.begin : ix.dataEnd ?? bytes.length;
  const tailFrom = ix.block ? ix.block.end : insertAt;
  let cursor = 0;
  for (let r = 0; r < ix.count; r++) {
    const off = ix.offset[r]!;
    if (off >= insertAt) break;
    const del = plan.deleted[r] === 1;
    const text = del ? undefined : plan.rewrite.get(ix.id[r]!);
    if (!del && text === undefined) continue;
    put(bytes, cursor, off);
    cursor = off + ix.length[r]!;
    if (del) {
      // the line break after a deleted statement goes with it
      if (bytes[cursor] === 13 && bytes[cursor + 1] === 10) cursor += 2;
      else if (bytes[cursor] === 10 || bytes[cursor] === 13) cursor += 1;
    } else put(latin1Encode(text!));
  }
  put(bytes, cursor, insertAt);
  if (blockText) put(latin1Encode(blockText));
  put(bytes, tailFrom, bytes.length);
  flush();
  return parts;
}
