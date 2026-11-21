// Whole-file index of a STEP file (design 2.4): one row per entity line with its byte range, its class and its references, forward and
// inverse (CSR). One pass over the bytes, no string decoding except for the class name of the first line of each class.
// Pure: no DOM, no WASM. Rows are in file order; every reference in `fwd` / `inv` is a ROW, not an express id.

export interface StepIndex {
  count: number;
  /** Express id per row. */
  id: Uint32Array;
  /** Byte offset of the `#` of each statement. */
  offset: Float64Array;
  /** Statement length in bytes, `#id=...;` (the semicolon included). */
  length: Uint32Array;
  /** Index into `typeNames`. 0 is the empty name (a complex entity instance). */
  type: Uint16Array;
  /** Upper-case class names. */
  typeNames: string[];
  /** Forward references of row r: `fwd[fwdStart[r] .. fwdStart[r + 1])`, rows, in text order (duplicates kept, unknown ids dropped). */
  fwdStart: Uint32Array;
  fwd: Uint32Array;
  /** Referrers of row r: `inv[invStart[r] .. invStart[r + 1])`, rows in file order. */
  invStart: Uint32Array;
  inv: Uint32Array;
  /** Largest express id. */
  maxId: number;
  /** Offset of the final `ENDSEC;`, or null. */
  dataEnd: number | null;
  /** Offset of `END-ISO-10303-21;`, or null. */
  endIso: number | null;
  /** The XRAY-BEGIN to XRAY-END block of an earlier save: `begin` is the first byte of its first comment, `end` the offset of the final ENDSEC. */
  block?: { begin: number; end: number; base: number };
  /** Rows of property sets and relations named like ours that stand outside our block (a file that went through another tool). */
  ourNamedRows: number[];
  /** Row of an express id, or -1. */
  rowOf(expressId: number): number;
  /** Class name of a row. */
  typeOf(row: number): string;
}

const TAB = 9, LF = 10, CR = 13, SP = 32, QUOTE = 39, HASH = 35, SEMI = 59, SLASH = 47, STAR = 42, PAREN = 40, COMMA = 44;
const isDigit = (c: number): boolean => c >= 48 && c <= 57;
const isTypeChar = (c: number): boolean => (c >= 65 && c <= 90) || (c >= 97 && c <= 122) || (c >= 48 && c <= 57) || c === 95;

function grow32(a: Uint32Array, n: number): Uint32Array<ArrayBuffer> {
  const b = new Uint32Array(n);
  b.set(a);
  return b;
}

const ASCII = (s: string): number[] => Array.from(s, (c) => c.charCodeAt(0));
const PSET_NAMES = ['Xray_Review', 'Xray_Cleanup', 'Xray_4D'].map((n) => ASCII(`'${n}'`));
const XRAY_PREFIX = ASCII("'Xray");
const at = (b: Uint8Array, i: number, pat: number[]): boolean => {
  if (i + pat.length > b.length) return false;
  for (let k = 0; k < pat.length; k++) if (b[i + k] !== pat[k]) return false;
  return true;
};

/**
 * Index `bytes`. `onProgress(done, total)` is called about every 8 MB. Entity lines must start with `#`; anything else (header, `ENDSEC;`)
 * is not a row. Comments between statements are skipped; the XRAY-BEGIN / XRAY-END comments of an earlier block are noted.
 */
export function indexStep(bytes: Uint8Array, onProgress?: (done: number, total: number) => void): StepIndex {
  const n = bytes.length;
  let cap = Math.max(1024, Math.floor(n / 48));
  let id = new Uint32Array(cap);
  let offset = new Float64Array(cap);
  let length = new Uint32Array(cap);
  let type = new Uint16Array(cap);
  let fwdStart = new Uint32Array(cap + 1);
  let refCap = Math.max(4096, Math.floor(n / 8));
  let refs = new Uint32Array(refCap); // express ids during the pass
  let nref = 0;
  let count = 0;
  let maxId = 0;
  let dataEnd: number | null = null;
  let endIso: number | null = null;
  const typeNames: string[] = [''];
  const typeByHash = new Map<number, number[]>();
  const kindOfType: number[] = [0]; // 1 property set, 2 relationship
  const oursRows: Array<[number, number]> = [];
  let pendingBegin: { begin: number; base: number } | null = null;
  let block: { begin: number; base: number } | null = null;

  const typeIndex = (s: number, e: number): number => {
    let h = 2166136261 ^ (e - s);
    for (let k = s; k < e; k++) {
      let c = bytes[k]!;
      if (c >= 97) c -= 32;
      h = Math.imul(h ^ c, 16777619);
    }
    const list = typeByHash.get(h);
    if (list) {
      for (const t of list) {
        const name = typeNames[t]!;
        if (name.length !== e - s) continue;
        let same = true;
        for (let k = 0; k < name.length; k++) {
          let c = bytes[s + k]!;
          if (c >= 97) c -= 32;
          if (c !== name.charCodeAt(k)) { same = false; break; }
        }
        if (same) return t;
      }
    }
    let name = '';
    for (let k = s; k < e; k++) name += String.fromCharCode(bytes[k]! >= 97 ? bytes[k]! - 32 : bytes[k]!);
    const t = typeNames.length;
    typeNames.push(name);
    kindOfType.push(name === 'IFCPROPERTYSET' ? 1 : name.startsWith('IFCREL') ? 2 : 0);
    if (list) list.push(t);
    else typeByHash.set(h, [t]);
    return t;
  };

  let i = 0;
  let nextReport = 8 * 1024 * 1024;
  while (i < n) {
    const c = bytes[i]!;
    if (c <= SP) { i++; continue; }
    if (c === SLASH && bytes[i + 1] === STAR) {
      let e = i + 2;
      while (e + 1 < n && !(bytes[e] === STAR && bytes[e + 1] === SLASH)) e++;
      // a marker comment: `/* XRAY-BEGIN fmt base=N ... */`
      if (bytes[i + 3] === 88 || bytes[i + 2] === 88) {
        let s = i + 2;
        while (s < e && bytes[s] === SP) s++;
        if (at(bytes, s, ASCII('XRAY-BEGIN'))) {
          let t = '';
          for (let k = s; k < Math.min(e, s + 120); k++) t += String.fromCharCode(bytes[k]!);
          const m = /base=(\d+)/.exec(t);
          pendingBegin = { begin: i, base: m ? Number(m[1]) : 0 };
        } else if (at(bytes, s, ASCII('XRAY-END')) && pendingBegin) {
          block = pendingBegin;
          pendingBegin = null;
        }
      }
      i = e + 2;
      continue;
    }
    const start = i;
    if (c !== HASH) {
      // header statement, ENDSEC;, END-ISO-10303-21;
      let j = i;
      while (j < n && bytes[j] !== SEMI) {
        if (bytes[j] === QUOTE) { j++; while (j < n && bytes[j] !== QUOTE) j++; }
        j++;
      }
      if (at(bytes, start, ASCII('ENDSEC'))) dataEnd = start;
      else if (at(bytes, start, ASCII('END-ISO'))) endIso = start;
      i = j + 1;
      continue;
    }
    // #id = TYPE ( ... ) ;
    let p = i + 1;
    let eid = 0;
    while (p < n && isDigit(bytes[p]!)) eid = eid * 10 + bytes[p++]! - 48;
    while (p < n && (bytes[p] === SP || bytes[p] === TAB || bytes[p] === LF || bytes[p] === CR)) p++;
    if (bytes[p] === 61) p++;
    while (p < n && bytes[p]! <= SP) p++;
    const t0 = p;
    while (p < n && isTypeChar(bytes[p]!)) p++;
    const tIdx = p > t0 ? typeIndex(t0, p) : 0;
    if (count + 1 >= cap) {
      cap = Math.floor(cap * 1.6) + 16;
      id = grow32(id, cap);
      const o2 = new Float64Array(cap); o2.set(offset); offset = o2;
      length = grow32(length, cap);
      const t2 = new Uint16Array(cap); t2.set(type); type = t2;
      fwdStart = grow32(fwdStart, cap + 1);
    }
    fwdStart[count] = nref;
    // the body: references outside strings and comments, up to the semicolon
    let j = p;
    while (j < n) {
      const b = bytes[j]!;
      if (b === SEMI) break;
      if (b === HASH) {
        let k = j + 1;
        let v = 0;
        while (k < n && isDigit(bytes[k]!)) v = v * 10 + bytes[k++]! - 48;
        if (k > j + 1) {
          if (nref === refCap) {
            refCap = Math.floor(refCap * 1.5);
            refs = grow32(refs, refCap);
          }
          refs[nref++] = v;
        }
        j = k;
      } else if (b === QUOTE) {
        j++;
        while (j < n && bytes[j] !== QUOTE) j++;
        j++;
      } else if (b === SLASH && bytes[j + 1] === STAR) {
        j += 2;
        while (j + 1 < n && !(bytes[j] === STAR && bytes[j + 1] === SLASH)) j++;
        j += 2;
      } else j++;
    }
    id[count] = eid;
    offset[count] = start;
    length[count] = Math.min(n, j + 1) - start;
    type[count] = tIdx;
    if (eid > maxId) maxId = eid;
    const kind = kindOfType[tIdx]!;
    if (kind !== 0) {
      // the third argument (Name): GlobalId, OwnerHistory, Name
      let q = p;
      while (q < j && bytes[q] !== PAREN) q++;
      q++;
      let commas = 0;
      while (q < j && commas < 2) {
        const b = bytes[q]!;
        if (b === QUOTE) { q++; while (q < j && bytes[q] !== QUOTE) q++; }
        else if (b === COMMA) commas++;
        q++;
      }
      if (commas === 2) {
        while (q < j && bytes[q] === SP) q++;
        if (kind === 1 ? PSET_NAMES.some((pat) => at(bytes, q, pat)) : at(bytes, q, XRAY_PREFIX)) oursRows.push([count, start]);
      }
    }
    count++;
    i = j + 1;
    if (i >= nextReport) {
      nextReport = i + 8 * 1024 * 1024;
      onProgress?.(i, n);
    }
  }
  fwdStart[count] = nref;

  // express id -> row
  const rowById = new Uint32Array(maxId + 1);
  for (let r = 0; r < count; r++) rowById[id[r]!] = r + 1;
  // convert references to rows, dropping ids that do not exist; count referrers meanwhile
  const invCount = new Uint32Array(count + 1);
  let w = 0;
  for (let r = 0; r < count; r++) {
    const a = fwdStart[r]!;
    const b = fwdStart[r + 1]!;
    fwdStart[r] = w;
    for (let k = a; k < b; k++) {
      const v = refs[k]!;
      const row = v <= maxId ? rowById[v]! : 0;
      if (row === 0) continue;
      refs[w++] = row - 1;
      invCount[row - 1]!++;
    }
  }
  fwdStart[count] = w;
  const fwd = refs.slice(0, w);
  refs = new Uint32Array(0);
  const invStart = new Uint32Array(count + 1);
  let acc = 0;
  for (let r = 0; r < count; r++) {
    invStart[r] = acc;
    acc += invCount[r]!;
  }
  invStart[count] = acc;
  const inv = new Uint32Array(acc);
  const fill = invCount; // reuse as the write cursor
  for (let r = 0; r < count; r++) fill[r] = invStart[r]!;
  for (let r = 0; r < count; r++) {
    for (let k = fwdStart[r]!; k < fwdStart[r + 1]!; k++) {
      const t = fwd[k]!;
      inv[fill[t]!++] = r;
    }
  }

  const out: StepIndex = {
    count,
    id: id.subarray(0, count),
    offset: offset.subarray(0, count),
    length: length.subarray(0, count),
    type: type.subarray(0, count),
    typeNames,
    fwdStart: fwdStart.subarray(0, count + 1),
    fwd,
    invStart,
    inv,
    maxId,
    dataEnd,
    endIso,
    ourNamedRows: [],
    rowOf: (e) => (e >= 0 && e <= maxId ? rowById[e]! - 1 : -1),
    typeOf: (r) => typeNames[type[r]!]!,
  };
  const bk = block as { begin: number; base: number } | null;
  if (bk && dataEnd !== null && bk.begin < dataEnd) {
    out.block = { begin: bk.begin, end: dataEnd, base: bk.base };
    out.ourNamedRows = oursRows.filter(([, off]) => off < bk.begin).map(([r]) => r);
  } else out.ourNamedRows = oursRows.map(([r]) => r);
  onProgress?.(n, n);
  return out;
}
