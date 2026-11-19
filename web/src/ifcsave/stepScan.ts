// Streaming scan over a STEP file held in a Blob (design 1.3). 4 MB chunks, a byte state machine that honours strings and comments.
// It keeps only the first HEAD bytes of each statement, which is all the questions below need.

import { parseStatement } from './stepText';
import type { StepValue } from './stepText';

export interface ScannedClassification {
  id: number;
  name: string;
  edition: string | null;
}

export interface StepScan {
  /** FILE_SCHEMA, first name. Empty when the header has none. */
  schema: string;
  /** Largest express id in the file, our own block included. */
  maxExpressId: number;
  /** Offset of the final `ENDSEC;` (the insert point of a file without a block), or null when there is none. */
  dataEnd: number | null;
  /** Offset of `END-ISO-10303-21;`, or null. */
  endIso: number | null;
  /** An XRAY-BEGIN to XRAY-END block: `begin` is the offset of its first comment, `end` the offset of the final ENDSEC. */
  block?: { begin: number; end: number; base: number };
  /** OwnerHistory reference of the IfcProject. */
  ownerHistoryId: number | null;
  /** IfcClassification lines outside our block. */
  classifications: ScannedClassification[];
  /** GlobalId of each requested express id that was found. */
  guidOf: Map<number, string>;
  /** Express ids of property sets and relations named like ours, outside our block (a file that went through another tool). */
  ourNamedRoots: number[];
  statements: number;
}

export interface ScanOptions {
  wantGuids?: Iterable<number>;
  /** Property set names that count as ours (the relation names always start with "Xray"). Default: Xray_Review, Xray_Cleanup. */
  ourPsetNames?: readonly string[];
  chunkSize?: number;
}

const HEAD = 4096;
const dec = new TextDecoder();

const INTERESTING = ['IFCPROJECT', 'IFCCLASSIFICATION', 'IFCPROPERTYSET', 'IFCRELDEFINESBYPROPERTIES', 'IFCRELASSOCIATESCLASSIFICATION'];
/** Entity names that matter, by length, as bytes: a statement is only decoded when its name is one of these. */
const PATTERNS: Array<Array<[string, Uint8Array]> | undefined> = [];
for (const n of INTERESTING) (PATTERNS[n.length] ??= []).push([n, Uint8Array.from(n, (c) => c.charCodeAt(0))]);
const matchesAt = (a: Uint8Array, at: number, b: Uint8Array): boolean => {
  for (let i = 0; i < b.length; i++) {
    const c = a[at + i]!;
    if ((c >= 97 ? c - 32 : c) !== b[i]) return false;
  }
  return true;
};

const strAt = (a: StepValue[], i: number): string | null => (a[i]?.t === 'str' ? (a[i] as { v: string }).v : null);

export async function scanStep(blob: Blob, o: ScanOptions = {}): Promise<StepScan> {
  const chunk = o.chunkSize ?? 4 * 1024 * 1024;
  const want = new Set(o.wantGuids ?? []);
  const ours = new Set(o.ourPsetNames ?? ['Xray_Review', 'Xray_Cleanup']);
  const out: StepScan = { schema: '', maxExpressId: 0, dataEnd: null, endIso: null, ownerHistoryId: null, classifications: [], guidOf: new Map(), ourNamedRoots: [], statements: 0 };
  const wantSize = want.size;
  const classOffsets: number[] = [];
  const rootOffsets: Array<[number, number]> = [];
  let pending: { begin: number; base: number } | null = null;
  let block: { begin: number; base: number } | null = null;


  const endStatement = (buf: Uint8Array, s: number, e: number, base: number): void => {
    out.statements++;
    const n = Math.min(e, s + HEAD);
    // #id = TYPE ( ...
    let p = s;
    let id = -1;
    if (buf[p] === 35) {
      id = 0;
      p++;
      while (p < n && buf[p]! >= 48 && buf[p]! <= 57) id = id * 10 + buf[p++]! - 48;
      while (p < n && (buf[p] === 32 || buf[p] === 61 || buf[p]! < 32)) p++;
    }
    const t0 = p;
    while (p < n) {
      const c = buf[p]!;
      if ((c >= 65 && c <= 90) || (c >= 48 && c <= 57) || c === 95 || (c >= 97 && c <= 122)) p++;
      else break;
    }
    const len = p - t0;
    let type = '';
    if (id >= 0) {
      if (id > out.maxExpressId) out.maxExpressId = id;
      const pat = len < PATTERNS.length ? PATTERNS[len] : undefined;
      if (pat) for (const [name, bytes] of pat) if (matchesAt(buf, t0, bytes)) type = name;
    } else {
      type = String.fromCharCode(...buf.subarray(t0, p)).toUpperCase();
      if (type === 'ENDSEC') out.dataEnd = base + s;
      else if (type === 'END' && buf[s + 3] === 45) out.endIso = base + s;
    }
    const need = wantSize > 0 && id >= 0 && want.has(id);
    if (!need && type === '') return;
    let st;
    try {
      st = parseStatement(dec.decode(buf.subarray(s, n)), e - s > HEAD);
    } catch {
      return;
    }
    if (!st) return;
    const a = st.args;
    if (need) {
      const g = strAt(a, 0);
      if (g !== null) out.guidOf.set(id, g);
    }
    if (type === 'FILE_SCHEMA') {
      const l = a[0];
      if (l && l.t === 'list' && l.v[0]?.t === 'str') out.schema = l.v[0].v;
    } else if (type === 'IFCPROJECT') {
      const oh = a[1];
      if (oh && oh.t === 'ref') out.ownerHistoryId = oh.id;
    } else if (type === 'IFCCLASSIFICATION') {
      const name = strAt(a, 3);
      if (name !== null) {
        out.classifications.push({ id, name, edition: strAt(a, 1) });
        classOffsets.push(base + s);
      }
    } else if (type !== '' && id >= 0) {
      const name = strAt(a, 2);
      if (name !== null && (type === 'IFCPROPERTYSET' ? ours.has(name) : name.startsWith('Xray'))) rootOffsets.push([id, base + s]);
    }
  };

  /** Index just after the `*` `/` that closes a comment whose body starts at `from`, or -1. */
  const commentEnd = (buf: Uint8Array, from: number): number => {
    for (let k = from; k + 1 < buf.length; k++) if (buf[k] === 42 && buf[k + 1] === 47) return k + 2;
    return -1;
  };
  const onComment = (buf: Uint8Array, s: number, e: number, base: number): void => {
    const t = String.fromCharCode(...buf.subarray(s + 2, Math.min(e, s + 122))).trimStart();
    if (t.startsWith('XRAY-BEGIN')) {
      const m = /base=(\d+)/.exec(t);
      pending = { begin: base + s, base: m ? Number(m[1]) : 0 };
    } else if (t.startsWith('XRAY-END') && pending) {
      block = pending;
      pending = null;
    }
  };

  // The loop works on whole statements: an unfinished statement or comment at the end of a chunk is carried into the next chunk.
  let carry = new Uint8Array(0);
  let carryOff = 0;
  for (let off = 0; off < blob.size; off += chunk) {
    const fresh = new Uint8Array(await blob.slice(off, Math.min(blob.size, off + chunk)).arrayBuffer());
    let buf = fresh;
    let base = off;
    if (carry.length) {
      buf = new Uint8Array(carry.length + fresh.length);
      buf.set(carry);
      buf.set(fresh, carry.length);
      base = carryOff;
    }
    const n = buf.length;
    let i = 0;
    let keep = n;
    while (i < n) {
      const b = buf[i]!;
      if (b <= 32) {
        i++;
        continue;
      }
      if (b === 47) {
        if (i + 1 >= n) {
          keep = i;
          break;
        }
        if (buf[i + 1] === 42) {
          const e = commentEnd(buf, i + 2);
          if (e < 0) {
            keep = i;
            break;
          }
          onComment(buf, i, e, base);
          i = e;
        } else i++;
        continue;
      }
      let j = i;
      let done = false;
      while (j < n) {
        const c = buf[j]!;
        if (c === 59) {
          done = true;
          break;
        }
        if (c === 39) {
          j++;
          while (j < n && buf[j] !== 39) j++;
          if (j >= n) break;
          j++;
        } else if (c === 47 && j + 1 < n && buf[j + 1] === 42) {
          const e = commentEnd(buf, j + 2);
          if (e < 0) break;
          j = e;
        } else j++;
      }
      if (!done) {
        keep = i;
        break;
      }
      endStatement(buf, i, j + 1, base);
      i = j + 1;
    }
    carry = keep < n ? buf.slice(keep) : new Uint8Array(0);
    carryOff = base + keep;
  }

  const bk = block as { begin: number; base: number } | null;
  if (bk && out.dataEnd !== null && bk.begin < out.dataEnd) {
    out.block = { begin: bk.begin, end: out.dataEnd, base: bk.base };
    const cut = bk.begin;
    out.classifications = out.classifications.filter((_, i) => classOffsets[i]! < cut);
    out.ourNamedRoots = rootOffsets.filter(([, at]) => at < cut).map(([id]) => id);
  } else {
    out.ourNamedRoots = rootOffsets.map(([id]) => id);
  }
  return out;
}
