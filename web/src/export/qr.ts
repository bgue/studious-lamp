// A small QR code encoder (ISO/IEC 18004), dependency-free: byte mode, error correction level L or M, versions 1 to 40,
// automatic mask choice by the standard penalty rules. The structure follows Project Nayuki's QR Code generator (MIT
// licence), written anew here. Used to hand the viewer link to a phone or a headset ("Share link as QR").

export type Ecc = 'L' | 'M';

const ECC_PER_BLOCK: Record<Ecc, number[]> = {
  L: [-1, 7, 10, 15, 20, 26, 18, 20, 24, 30, 18, 20, 24, 26, 30, 22, 24, 28, 30, 28, 28, 28, 28, 30, 30, 26, 28, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30],
  M: [-1, 10, 16, 26, 18, 24, 16, 18, 22, 22, 26, 30, 22, 22, 24, 24, 28, 28, 26, 26, 26, 26, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28],
};
const NUM_BLOCKS: Record<Ecc, number[]> = {
  L: [-1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 4, 4, 4, 4, 4, 6, 6, 6, 6, 7, 8, 8, 9, 9, 10, 12, 12, 12, 13, 14, 15, 16, 17, 18, 19, 19, 20, 21, 22, 24, 25],
  M: [-1, 1, 1, 1, 2, 2, 4, 4, 4, 5, 5, 5, 8, 9, 9, 10, 10, 11, 13, 14, 16, 17, 17, 18, 20, 21, 23, 25, 26, 28, 29, 31, 33, 35, 37, 38, 40, 43, 45, 47, 49],
};
const FORMAT_BITS: Record<Ecc, number> = { L: 1, M: 0 };

export interface QrCode {
  version: number;
  size: number;
  ecc: Ecc;
  mask: number;
  /** modules[y][x], true = dark. */
  modules: boolean[][];
}

/** Bits of raw data modules (data and error correction) of a version. */
export function rawDataModules(ver: number): number {
  let r = (16 * ver + 128) * ver + 64;
  if (ver >= 2) {
    const n = Math.floor(ver / 7) + 2;
    r -= (25 * n - 10) * n - 55;
    if (ver >= 7) r -= 36;
  }
  return r;
}

/** Data codewords of a version and level. */
export function dataCodewords(ver: number, ecc: Ecc): number {
  return Math.floor(rawDataModules(ver) / 8) - ECC_PER_BLOCK[ecc][ver]! * NUM_BLOCKS[ecc][ver]!;
}

function gfMul(x: number, y: number): number {
  let z = 0;
  for (let i = 7; i >= 0; i--) {
    z = (z << 1) ^ ((z >>> 7) * 0x11d);
    z ^= ((y >>> i) & 1) * x;
  }
  return z & 0xff;
}

function rsDivisor(degree: number): number[] {
  const r = new Array<number>(degree).fill(0);
  r[degree - 1] = 1;
  let root = 1;
  for (let i = 0; i < degree; i++) {
    for (let j = 0; j < degree; j++) {
      r[j] = gfMul(r[j]!, root);
      if (j + 1 < degree) r[j]! ^= r[j + 1]!;
    }
    root = gfMul(root, 0x02);
  }
  return r;
}

/** Reed-Solomon remainder of `data` by the divisor (the error correction codewords). */
export function rsRemainder(data: readonly number[], divisor: readonly number[]): number[] {
  const r = new Array<number>(divisor.length).fill(0);
  for (const b of data) {
    const f = b ^ r.shift()!;
    r.push(0);
    for (let i = 0; i < divisor.length; i++) r[i]! ^= gfMul(divisor[i]!, f);
  }
  return r;
}

export function alignmentPositions(ver: number): number[] {
  if (ver === 1) return [];
  const n = Math.floor(ver / 7) + 2;
  const step = ver === 32 ? 26 : Math.ceil((ver * 4 + 4) / (n * 2 - 2)) * 2;
  const out = [6];
  for (let pos = ver * 4 + 17 - 7; out.length < n; pos -= step) out.splice(1, 0, pos);
  return out;
}

class Grid {
  readonly m: boolean[][];
  readonly fn: boolean[][];
  readonly size: number;
  constructor(size: number) {
    this.size = size;
    this.m = Array.from({ length: size }, () => new Array<boolean>(size).fill(false));
    this.fn = Array.from({ length: size }, () => new Array<boolean>(size).fill(false));
  }
  set(x: number, y: number, dark: boolean): void {
    this.m[y]![x] = dark;
    this.fn[y]![x] = true;
  }
}

function drawFunctionPatterns(g: Grid, ver: number): void {
  const n = g.size;
  for (let i = 0; i < n; i++) {
    g.set(6, i, i % 2 === 0);
    g.set(i, 6, i % 2 === 0);
  }
  const finder = (x: number, y: number): void => {
    for (let dy = -4; dy <= 4; dy++)
      for (let dx = -4; dx <= 4; dx++) {
        const d = Math.max(Math.abs(dx), Math.abs(dy));
        const xx = x + dx, yy = y + dy;
        if (xx >= 0 && xx < n && yy >= 0 && yy < n) g.set(xx, yy, d !== 2 && d !== 4);
      }
  };
  finder(3, 3);
  finder(n - 4, 3);
  finder(3, n - 4);
  const al = alignmentPositions(ver);
  const k = al.length;
  for (let i = 0; i < k; i++)
    for (let j = 0; j < k; j++) {
      if ((i === 0 && j === 0) || (i === 0 && j === k - 1) || (i === k - 1 && j === 0)) continue;
      for (let dy = -2; dy <= 2; dy++) for (let dx = -2; dx <= 2; dx++) g.set(al[i]! + dx, al[j]! + dy, Math.max(Math.abs(dx), Math.abs(dy)) !== 1);
    }
  drawFormat(g, 'L', 0); // reserve
  if (ver >= 7) {
    let rem = ver;
    for (let i = 0; i < 12; i++) rem = (rem << 1) ^ ((rem >>> 11) * 0x1f25);
    const bits = (ver << 12) | rem;
    for (let i = 0; i < 18; i++) {
      const b = ((bits >>> i) & 1) !== 0;
      const a = n - 11 + (i % 3);
      const c = Math.floor(i / 3);
      g.set(a, c, b);
      g.set(c, a, b);
    }
  }
}

/** The 15 format bits (level and mask, BCH protected and masked). */
export function formatBits(ecc: Ecc, mask: number): number {
  const data = (FORMAT_BITS[ecc] << 3) | mask;
  let rem = data;
  for (let i = 0; i < 10; i++) rem = (rem << 1) ^ ((rem >>> 9) * 0x537);
  return ((data << 10) | rem) ^ 0x5412;
}

function drawFormat(g: Grid, ecc: Ecc, mask: number): void {
  const bits = formatBits(ecc, mask);
  const bit = (i: number): boolean => ((bits >>> i) & 1) !== 0;
  const n = g.size;
  for (let i = 0; i <= 5; i++) g.set(8, i, bit(i));
  g.set(8, 7, bit(6));
  g.set(8, 8, bit(7));
  g.set(7, 8, bit(8));
  for (let i = 9; i < 15; i++) g.set(14 - i, 8, bit(i));
  for (let i = 0; i < 8; i++) g.set(n - 1 - i, 8, bit(i));
  for (let i = 8; i < 15; i++) g.set(8, n - 15 + i, bit(i));
  g.set(8, n - 8, true);
}

function interleave(data: number[], ver: number, ecc: Ecc): number[] {
  const nb = NUM_BLOCKS[ecc][ver]!;
  const eccLen = ECC_PER_BLOCK[ecc][ver]!;
  const raw = Math.floor(rawDataModules(ver) / 8);
  const nShort = nb - (raw % nb);
  const shortLen = Math.floor(raw / nb);
  const div = rsDivisor(eccLen);
  const blocks: number[][] = [];
  for (let i = 0, k = 0; i < nb; i++) {
    const dat = data.slice(k, k + shortLen - eccLen + (i < nShort ? 0 : 1));
    k += dat.length;
    const e = rsRemainder(dat, div);
    if (i < nShort) dat.push(0);
    blocks.push(dat.concat(e));
  }
  const out: number[] = [];
  for (let i = 0; i < blocks[0]!.length; i++)
    for (let j = 0; j < blocks.length; j++) if (i !== shortLen - eccLen || j >= nShort) out.push(blocks[j]![i]!);
  return out;
}

function drawCodewords(g: Grid, data: number[]): void {
  const n = g.size;
  let i = 0;
  for (let right = n - 1; right >= 1; right -= 2) {
    if (right === 6) right = 5;
    for (let v = 0; v < n; v++)
      for (let j = 0; j < 2; j++) {
        const x = right - j;
        const up = ((right + 1) & 2) === 0;
        const y = up ? n - 1 - v : v;
        if (!g.fn[y]![x] && i < data.length * 8) {
          g.m[y]![x] = ((data[i >>> 3]! >>> (7 - (i & 7))) & 1) !== 0;
          i++;
        }
      }
  }
}

const MASKS: Array<(x: number, y: number) => boolean> = [
  (x, y) => (x + y) % 2 === 0,
  (_x, y) => y % 2 === 0,
  (x) => x % 3 === 0,
  (x, y) => (x + y) % 3 === 0,
  (x, y) => (Math.floor(x / 3) + Math.floor(y / 2)) % 2 === 0,
  (x, y) => ((x * y) % 2) + ((x * y) % 3) === 0,
  (x, y) => (((x * y) % 2) + ((x * y) % 3)) % 2 === 0,
  (x, y) => (((x + y) % 2) + ((x * y) % 3)) % 2 === 0,
];

function applyMask(g: Grid, mask: number): void {
  const f = MASKS[mask]!;
  for (let y = 0; y < g.size; y++) for (let x = 0; x < g.size; x++) if (!g.fn[y]![x] && f(x, y)) g.m[y]![x] = !g.m[y]![x];
}

/** The standard penalty score of a finished symbol (lower is better). */
export function penalty(m: boolean[][]): number {
  const n = m.length;
  let score = 0;
  const addHist = (run: number, h: number[]): void => {
    if (h[0] === 0) run += n;
    h.pop();
    h.unshift(run);
  };
  const count = (h: number[]): number => {
    const k = h[1]!;
    const core = k > 0 && h[2] === k && h[3] === k * 3 && h[4] === k && h[5] === k;
    return (core && h[0]! >= k * 4 && h[6]! >= k ? 1 : 0) + (core && h[6]! >= k * 4 && h[0]! >= k ? 1 : 0);
  };
  const line = (get: (i: number) => boolean): void => {
    let color = false;
    let run = 0;
    const h = [0, 0, 0, 0, 0, 0, 0];
    for (let i = 0; i < n; i++) {
      if (get(i) === color) {
        run++;
        if (run === 5) score += 3;
        else if (run > 5) score++;
      } else {
        addHist(run, h);
        if (!color) score += count(h) * 40;
        color = get(i);
        run = 1;
      }
    }
    if (color) {
      addHist(run, h);
      run = 0;
    }
    run += n;
    addHist(run, h);
    score += count(h) * 40;
  };
  for (let y = 0; y < n; y++) line((x) => m[y]![x]!);
  for (let x = 0; x < n; x++) line((y) => m[y]![x]!);
  for (let y = 0; y < n - 1; y++)
    for (let x = 0; x < n - 1; x++) {
      const c = m[y]![x];
      if (c === m[y]![x + 1] && c === m[y + 1]![x] && c === m[y + 1]![x + 1]) score += 3;
    }
  let dark = 0;
  for (const r of m) for (const c of r) if (c) dark++;
  const total = n * n;
  score += (Math.ceil(Math.abs(dark * 20 - total * 10) / total) - 1) * 10;
  return score;
}

const utf8 = (s: string): number[] => Array.from(new TextEncoder().encode(s));

/** Encode text (UTF-8, byte mode). Picks the smallest version that fits; mask auto unless given. Throws when too long. */
export function encodeQr(text: string, ecc: Ecc = 'M', forceMask = -1, minVersion = 1): QrCode {
  const bytes = utf8(text);
  let ver = minVersion;
  for (; ver <= 40; ver++) {
    const cc = ver < 10 ? 8 : 16;
    if (4 + cc + bytes.length * 8 <= dataCodewords(ver, ecc) * 8) break;
  }
  if (ver > 40) throw new Error(`text too long for a QR code (${bytes.length} bytes)`);
  const cap = dataCodewords(ver, ecc) * 8;
  const bits: number[] = [];
  const put = (v: number, len: number): void => {
    for (let i = len - 1; i >= 0; i--) bits.push((v >>> i) & 1);
  };
  put(4, 4);
  put(bytes.length, ver < 10 ? 8 : 16);
  for (const b of bytes) put(b, 8);
  put(0, Math.min(4, cap - bits.length));
  put(0, (8 - (bits.length % 8)) % 8);
  const data: number[] = [];
  for (let i = 0; i < bits.length; i += 8) data.push(bits.slice(i, i + 8).reduce((a, b) => (a << 1) | b, 0));
  for (let pad = 0xec; data.length < cap / 8; pad ^= 0xec ^ 0x11) data.push(pad);
  const all = interleave(data, ver, ecc);
  const size = ver * 4 + 17;
  const build = (mask: number): Grid => {
    const g = new Grid(size);
    drawFunctionPatterns(g, ver);
    drawCodewords(g, all);
    applyMask(g, mask);
    drawFormat(g, ecc, mask);
    return g;
  };
  let best = forceMask;
  if (best < 0) {
    let low = Infinity;
    for (let k = 0; k < 8; k++) {
      const p = penalty(build(k).m);
      if (p < low) {
        low = p;
        best = k;
      }
    }
  }
  return { version: ver, size, ecc, mask: best, modules: build(best).m };
}

/** SVG of a code with a quiet zone of `border` modules (dark modules as one path). */
export function qrSvg(q: QrCode, border = 4, px = 4): string {
  const n = q.size + border * 2;
  let d = '';
  for (let y = 0; y < q.size; y++) for (let x = 0; x < q.size; x++) if (q.modules[y]![x]) d += `M${x + border} ${y + border}h1v1h-1z`;
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${n} ${n}" width="${n * px}" height="${n * px}" shape-rendering="crispEdges"><rect width="100%" height="100%" fill="#fff"/><path d="${d}" fill="#000"/></svg>`;
}
