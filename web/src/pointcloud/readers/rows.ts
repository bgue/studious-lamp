// Fast scanner for numeric text rows over a byte array. Tokens are separated by spaces, tabs, commas or semicolons.

export interface RowScan {
  /** Called for each all-numeric row with the values in `vals[0..n)`. Return false to stop. */
  onRow(vals: Float64Array, n: number): boolean | void;
  /** Called for a row that is not all numeric (header, comment, text). Absent: such rows throw. */
  onOther?(line: string, lineNo: number): void;
  /** Progress callback with the byte position. */
  onProgress?(pos: number): void;
}

const MAX_COLS = 64;

/** Parse one number at bytes[i..end). Returns NaN when the token is not a number. Sets `endPos`. */
let endPos = 0;
function parseNum(b: Uint8Array, i: number, end: number): number {
  const start = i;
  let neg = false;
  let c = b[i]!;
  if (c === 45) { neg = true; i++; } else if (c === 43) i++;
  let mant = 0;
  let digits = 0;
  let exp10 = 0;
  c = b[i]!;
  while (i < end && c >= 48 && c <= 57) {
    mant = mant * 10 + (c - 48);
    digits++;
    c = b[++i]!;
  }
  if (i < end && c === 46) {
    c = b[++i]!;
    while (i < end && c >= 48 && c <= 57) {
      mant = mant * 10 + (c - 48);
      exp10--;
      digits++;
      c = b[++i]!;
    }
  }
  if (digits === 0) {
    endPos = start;
    return NaN;
  }
  if (i < end && (c === 101 || c === 69)) {
    let j = i + 1;
    let eneg = false;
    c = b[j]!;
    if (c === 45) { eneg = true; j++; } else if (c === 43) j++;
    let e = 0;
    let ed = 0;
    c = b[j]!;
    while (j < end && c >= 48 && c <= 57) {
      e = e * 10 + (c - 48);
      ed++;
      c = b[++j]!;
    }
    if (ed > 0) {
      exp10 += eneg ? -e : e;
      i = j;
    }
  }
  endPos = i;
  // digits beyond 15 lose exactness in `mant`; fall back to the engine parser for long mantissas
  if (digits > 15) return Number(new TextDecoder().decode(b.subarray(start, i)));
  const v = exp10 === 0 ? mant : exp10 < 0 ? (exp10 >= -22 ? mant / 10 ** -exp10 : mant * 10 ** exp10) : mant * 10 ** exp10;
  return neg ? -v : v;
}

const isSep = (c: number): boolean => c === 32 || c === 9 || c === 44 || c === 59;

/** Scan rows from `start`. Returns the number of numeric rows delivered. */
export function scanRows(b: Uint8Array, start: number, end: number, scan: RowScan): number {
  const vals = new Float64Array(MAX_COLS);
  let rows = 0;
  let lineNo = 0;
  let i = start;
  let nextProgress = start + (1 << 20);
  while (i < end) {
    // one line
    let eol = i;
    while (eol < end && b[eol] !== 10 && b[eol] !== 13) eol++;
    lineNo++;
    let n = 0;
    let ok = true;
    let p = i;
    while (p < eol) {
      while (p < eol && isSep(b[p]!)) p++;
      if (p >= eol) break;
      if (n >= MAX_COLS) break;
      const v = parseNum(b, p, eol);
      const q = endPos;
      if (Number.isNaN(v) || (q < eol && !isSep(b[q]!))) {
        // a token that is not a plain number: nan / inf spelled out, or text
        let t = p;
        while (t < eol && !isSep(b[t]!)) t++;
        const word = new TextDecoder().decode(b.subarray(p, t)).toLowerCase();
        if (word === 'nan' || word === '-nan' || word === '+nan') vals[n++] = NaN;
        else if (word === 'inf' || word === '+inf' || word === 'infinity') vals[n++] = Infinity;
        else if (word === '-inf' || word === '-infinity') vals[n++] = -Infinity;
        else { ok = false; break; }
        p = t;
        continue;
      }
      vals[n++] = v;
      p = q;
    }
    if (n === 0 && ok) {
      // blank line
    } else if (ok) {
      if (scan.onRow(vals, n) === false) {
        rows++;
        break;
      }
      rows++;
    } else if (scan.onOther) {
      scan.onOther(new TextDecoder().decode(b.subarray(i, Math.min(eol, i + 200))), lineNo);
    } else {
      throw new Error(`Line ${lineNo} is not numeric: "${new TextDecoder().decode(b.subarray(i, Math.min(eol, i + 60)))}"`);
    }
    // skip the line break (LF, CR or CRLF)
    if (eol < end && b[eol] === 13 && b[eol + 1] === 10) eol++;
    i = eol + 1;
    if (scan.onProgress && i >= nextProgress) {
      scan.onProgress(i);
      nextProgress = i + (1 << 20);
    }
  }
  return rows;
}
