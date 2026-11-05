// E57 (ASTM E2807): the format of terrestrial scanners and of most iPhone / iPad LiDAR apps.
//
// File layout: a 48 byte header ("ASTM-E57", version, filePhysicalLength, xmlPhysicalOffset, xmlLogicalLength,
// pageSize), then pages of `pageSize` bytes (1024 in practice), each ending with a CRC-32C of the page (big endian).
// Offsets in the header and the XML are PHYSICAL (checksums included); lengths are LOGICAL (checksums removed).
// The XML section describes the tree; /data3D holds the scans. Each scan's `points` is a CompressedVector: a prototype
// (one leaf per field, e.g. cartesianX/Y/Z, intensity, colorRed) and a binary section of data packets. Every packet has
// one buffer per field ("bytestream"); a field's values are bit packed LSB first and continue across packets.
//
// Read here: cartesian and spherical coordinates (Float single/double, ScaledInteger, Integer), cartesianInvalidState and
// sphericalInvalidState (non-zero points are skipped), intensity (normalised by intensityLimits), colour (normalised by
// colorLimits), isIntensityInvalid / isColorInvalid, the scan pose (quaternion + translation, applied in double) and
// several scans merged into one cloud. Only the default bitPackCodec exists in the standard, so only that is read.
// Not read: images2D, row/column grids beyond the points themselves, extensions. The XML is parsed with the DOM free
// reader of the BCF feature, so this runs in a Web Worker (no DOMParser there).

import { child, parseXml, XmlError } from '../../bcf/xml';
import type { XNode } from '../../bcf/xml';
import type { PointCloudData, ProgressFn } from '../types';
import { PointCloudError } from '../types';
import { PointBuilder } from './builder';

const SIGNATURE = 'ASTM-E57';
/** Scans merged beyond this count are reported (they are merged anyway). */
export const E57_MANY_SCANS = 100;

export function isE57(bytes: Uint8Array): boolean {
  if (bytes.length < 8) return false;
  for (let i = 0; i < 8; i++) if (bytes[i] !== SIGNATURE.charCodeAt(i)) return false;
  return true;
}

// ---------------------------------------------------------------- CRC-32C (Castagnoli), slicing by 8

let CRC_TABLE: Uint32Array | null = null;
function crcTable(): Uint32Array {
  if (CRC_TABLE) return CRC_TABLE;
  const t = new Uint32Array(256 * 8);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? (c >>> 1) ^ 0x82f63b78 : c >>> 1;
    t[n] = c >>> 0;
  }
  for (let n = 0; n < 256; n++) {
    let c = t[n]!;
    for (let k = 1; k < 8; k++) {
      c = (c >>> 8) ^ t[c & 0xff]!;
      t[k * 256 + n] = c >>> 0;
    }
  }
  return (CRC_TABLE = t);
}

export function crc32c(bytes: Uint8Array, start = 0, end = bytes.length): number {
  const t = crcTable();
  let c = 0xffffffff;
  let i = start;
  for (; i + 8 <= end; i += 8) {
    const a = (c ^ (bytes[i]! | (bytes[i + 1]! << 8) | (bytes[i + 2]! << 16) | (bytes[i + 3]! << 24))) >>> 0;
    c =
      t[7 * 256 + (a & 0xff)]! ^ t[6 * 256 + ((a >>> 8) & 0xff)]! ^ t[5 * 256 + ((a >>> 16) & 0xff)]! ^ t[4 * 256 + (a >>> 24)]! ^
      t[3 * 256 + bytes[i + 4]!]! ^ t[2 * 256 + bytes[i + 5]!]! ^ t[256 + bytes[i + 6]!]! ^ t[bytes[i + 7]!]!;
  }
  for (; i < end; i++) c = (c >>> 8) ^ t[(c ^ bytes[i]!) & 0xff]!;
  return (c ^ 0xffffffff) >>> 0;
}

// ---------------------------------------------------------------- paged file

class Truncated extends Error {}

/** Logical view of the paged file: checksums are skipped, reads that cross a page boundary are copied. */
class Paged {
  readonly payload: number;
  readonly logicalSize: number;
  private scratch = new Uint8Array(0);

  constructor(readonly bytes: Uint8Array, readonly pageSize: number) {
    this.payload = pageSize - 4;
    const full = Math.floor(bytes.length / pageSize);
    const rest = bytes.length - full * pageSize;
    this.logicalSize = full * this.payload + Math.min(rest, this.payload);
  }

  toLogical(physical: number, what: string): number {
    const inPage = physical % this.pageSize;
    if (!Number.isSafeInteger(physical) || physical < 0 || inPage >= this.payload) throw new PointCloudError(`E57: ${what} (${physical}) is not a valid physical offset`);
    return Math.floor(physical / this.pageSize) * this.payload + inPage;
  }

  /** `len` logical bytes from logical offset `at`. A view when they lie in one page, else a copy (into a reused scratch
   *  buffer unless `own`). Throws Truncated past the end of the file. */
  read(at: number, len: number, own = false): Uint8Array {
    if (at < 0 || at + len > this.logicalSize) throw new Truncated();
    const page = Math.floor(at / this.payload);
    const inPage = at - page * this.payload;
    const phys = page * this.pageSize + inPage;
    if (inPage + len <= this.payload) return this.bytes.subarray(phys, phys + len);
    let out: Uint8Array;
    if (own) out = new Uint8Array(len);
    else {
      if (this.scratch.length < len) this.scratch = new Uint8Array(Math.max(len, this.scratch.length * 2));
      out = this.scratch.subarray(0, len);
    }
    let o = 0;
    let p = page;
    let off = inPage;
    while (o < len) {
      const n = Math.min(len - o, this.payload - off);
      const s = p * this.pageSize + off;
      out.set(this.bytes.subarray(s, s + n), o);
      o += n;
      p++;
      off = 0;
    }
    return out;
  }

  /** Verify the checksums of the pages [first, last]; returns the bad page numbers. */
  verify(first: number, last: number): number[] {
    const bad: number[] = [];
    const b = this.bytes;
    for (let p = first; p <= last; p++) {
      const s = p * this.pageSize;
      if (s + this.pageSize > b.length) break;
      const e = s + this.payload;
      const stored = ((b[e]! << 24) | (b[e + 1]! << 16) | (b[e + 2]! << 8) | b[e + 3]!) >>> 0;
      if (crc32c(b, s, e) !== stored) bad.push(p);
    }
    return bad;
  }
}

// ---------------------------------------------------------------- XML helpers

const text = (n: XNode | undefined): string => (n ? n.text.trim() : '');

/** Numeric value of an Integer, ScaledInteger or Float element (empty text is 0, the E57 default). */
function numberOf(n: XNode | undefined): number | undefined {
  if (!n) return undefined;
  const t = text(n);
  const v = t === '' ? 0 : Number(t);
  if (!Number.isFinite(v)) return undefined;
  if (n.attrs.type === 'ScaledInteger') return v * attrNum(n, 'scale', 1) + attrNum(n, 'offset', 0);
  return v;
}

function attrNum(n: XNode, name: string, dflt: number): number {
  const a = n.attrs[name];
  if (a === undefined || a.trim() === '') return dflt;
  const v = Number(a);
  return Number.isFinite(v) ? v : dflt;
}

function attrBig(n: XNode, name: string, dflt: bigint): bigint {
  const a = n.attrs[name]?.trim();
  if (!a) return dflt;
  if (!/^[+-]?\d+$/.test(a)) throw new PointCloudError(`E57: ${n.name} has a non-integer ${name} "${a}"`);
  return BigInt(a);
}

// ---------------------------------------------------------------- fields and bit unpacking

type Kind = 'f32' | 'f64' | 'int' | 'big' | 'const';

interface Field {
  name: string;
  kind: Kind;
  bits: number;
  min: number;
  minBig: bigint;
  scale: number;
  offset: number;
  /** Element bounds for normalising (scaled), when meaningful. */
  lo?: number;
  hi?: number;
}

const INT64_MIN = -(1n << 63n);
const INT64_MAX = (1n << 63n) - 1n;

function fieldOf(n: XNode): Field {
  const type = n.attrs.type;
  if (type === 'Float') {
    const single = n.attrs.precision === 'single';
    const f: Field = { name: n.name, kind: single ? 'f32' : 'f64', bits: single ? 32 : 64, min: 0, minBig: 0n, scale: 1, offset: 0 };
    const lo = attrNum(n, 'minimum', NaN);
    const hi = attrNum(n, 'maximum', NaN);
    if (Number.isFinite(lo) && Number.isFinite(hi) && hi > lo && Math.abs(lo) < 1e30 && Math.abs(hi) < 1e30) {
      f.lo = lo;
      f.hi = hi;
    }
    return f;
  }
  if (type === 'Integer' || type === 'ScaledInteger') {
    const min = attrBig(n, 'minimum', INT64_MIN);
    const max = attrBig(n, 'maximum', INT64_MAX);
    if (max < min) throw new PointCloudError(`E57: ${n.name} has maximum < minimum`);
    const range = max - min + 1n;
    const bits = range <= 1n ? 0 : (range - 1n).toString(2).length; // ceil(log2(range))
    const scale = type === 'ScaledInteger' ? attrNum(n, 'scale', 1) : 1;
    const offset = type === 'ScaledInteger' ? attrNum(n, 'offset', 0) : 0;
    const minNum = Number(min);
    const big = bits > 52 || !Number.isSafeInteger(minNum) || !Number.isSafeInteger(Number(max));
    return {
      name: n.name, kind: bits === 0 ? 'const' : big ? 'big' : 'int', bits, min: minNum, minBig: min, scale, offset,
      lo: minNum * scale + offset, hi: Number(max) * scale + offset,
    };
  }
  throw new PointCloudError(`E57: prototype field ${n.name} has unsupported type "${type ?? '?'}"`);
}

/** One field's bytestream: decodes the packet buffers into a staging array of values (scaled, double). */
class Stream {
  vals: Float64Array;
  /** Values held in `vals` (from the shared staging start). */
  count = 0;
  /** Values decoded in total. */
  total = 0;
  private work = new Uint8Array(0);
  private dv = new DataView(new ArrayBuffer(0));
  /** Unconsumed tail bytes of the previous buffer and the bit offset into its first byte. */
  private carry = new Uint8Array(16);
  private carryLen = 0;
  private carryBit = 0;
  readonly constValue: number;

  constructor(readonly f: Field, readonly limit: number) {
    this.vals = new Float64Array(f.kind === 'const' ? 0 : 4096);
    this.constValue = f.kind === 'const' ? f.min * f.scale + f.offset : 0;
  }

  get done(): boolean {
    return this.f.kind === 'const' || this.total >= this.limit;
  }

  /** Decode a packet buffer of this stream. */
  push(chunk: Uint8Array): void {
    const f = this.f;
    if (f.kind === 'const' || this.total >= this.limit || chunk.length === 0) return;
    const len = this.carryLen + chunk.length;
    if (this.work.length < len + 8) {
      this.work = new Uint8Array(Math.max(len + 8, this.work.length * 2));
      this.dv = new DataView(this.work.buffer);
    }
    const w = this.work;
    if (this.carryLen) w.set(this.carry.subarray(0, this.carryLen), 0);
    w.set(chunk, this.carryLen);
    w.fill(0, len, len + 8); // reads past the end see zeros
    const bits = f.bits;
    let p = this.carryBit;
    const n = Math.min(Math.floor((len * 8 - p) / bits), this.limit - this.total);
    if (this.count + n > this.vals.length) {
      const g = new Float64Array(Math.max(this.count + n, this.vals.length * 2));
      g.set(this.vals.subarray(0, this.count));
      this.vals = g;
    }
    const out = this.vals;
    let o = this.count;
    const end = o + n;
    if (f.kind === 'f64') {
      const dv = this.dv;
      for (let b = p >>> 3; o < end; o++, b += 8) out[o] = dv.getFloat64(b, true);
      p += n * 64;
    } else if (f.kind === 'f32') {
      const dv = this.dv;
      for (let b = p >>> 3; o < end; o++, b += 4) out[o] = dv.getFloat32(b, true);
      p += n * 32;
    } else if (f.kind === 'int') {
      const min = f.min;
      const scale = f.scale;
      const offset = f.offset;
      const plain = scale === 1 && offset === 0;
      if (bits === 8 && (p & 7) === 0) {
        for (let b = p >>> 3; o < end; o++, b++) out[o] = plain ? w[b]! + min : (w[b]! + min) * scale + offset;
        p += n * 8;
      } else if (bits <= 25) {
        const mask = (1 << bits) - 1;
        for (; o < end; o++, p += bits) {
          const b = p >>> 3;
          const v = (((w[b]! | (w[b + 1]! << 8) | (w[b + 2]! << 16) | (w[b + 3]! << 24)) >>> (p & 7)) & mask) + min;
          out[o] = plain ? v : v * scale + offset;
        }
      } else {
        for (; o < end; o++, p += bits) {
          const b = p >>> 3;
          const s = p & 7;
          const lo = (w[b]! | (w[b + 1]! << 8) | (w[b + 2]! << 16) | (w[b + 3]! << 24)) >>> 0;
          const hi = (w[b + 4]! | (w[b + 5]! << 8) | (w[b + 6]! << 16) | (w[b + 7]! << 24)) >>> 0;
          let v: number;
          if (bits + s <= 32) v = bits === 32 ? lo : (lo >>> s) % 2 ** bits;
          else {
            const k = bits + s - 32; // bits taken from hi, at most 52 + 7 - 32 = 27
            v = (lo >>> s) + (hi % 2 ** k) * 2 ** (32 - s);
          }
          v += min;
          out[o] = plain ? v : v * scale + offset;
        }
      }
    } else {
      // more than 52 bits, or bounds outside the safe integer range: BigInt (rare: Integer fields without bounds)
      const minBig = f.minBig;
      const mask = (1n << BigInt(bits)) - 1n;
      for (; o < end; o++, p += bits) {
        const b = p >>> 3;
        let acc = 0n;
        const nb = ((p & 7) + bits + 7) >>> 3;
        for (let k = nb - 1; k >= 0; k--) acc = (acc << 8n) | BigInt(w[b + k] ?? 0);
        const v = Number(((acc >> BigInt(p & 7)) & mask) + minBig);
        out[o] = v * f.scale + f.offset;
      }
    }
    this.count = end;
    this.total += n;
    // keep the unconsumed tail
    const byte = p >>> 3;
    const rest = len - byte;
    if (this.total >= this.limit || rest <= 0) {
      this.carryLen = 0;
      this.carryBit = 0;
    } else {
      if (rest > this.carry.length) throw new PointCloudError(`E57: bytestream of ${f.name} is malformed`);
      this.carry.set(w.subarray(byte, len), 0);
      this.carryLen = rest;
      this.carryBit = p & 7;
    }
  }

  /** Drop the first `k` staged values. */
  shift(k: number): void {
    if (this.f.kind === 'const' || k <= 0) return;
    this.vals.copyWithin(0, k, this.count);
    this.count -= k;
  }
}

// ---------------------------------------------------------------- scans

interface Scan {
  name: string;
  fileOffset: number;
  records: number;
  fields: Field[];
  rot: [number, number, number, number] | null;
  trans: [number, number, number];
  intensity: [number, number] | null;
  color: [[number, number], [number, number], [number, number]] | null;
}

function leaves(n: XNode, out: XNode[]): void {
  for (const c of n.children) {
    const t = c.attrs.type;
    if (t === 'Structure') leaves(c, out);
    else if (t === 'Vector' || t === 'CompressedVector' || t === 'Blob' || t === 'String')
      throw new PointCloudError(`E57: prototype field ${c.name} of type ${t} is not supported`);
    else out.push(c);
  }
}

function limits(n: XNode | undefined, lo: string, hi: string): [number, number] | null {
  const a = numberOf(child(n, lo));
  const b = numberOf(child(n, hi));
  return a !== undefined && b !== undefined && b > a ? [a, b] : null;
}

function readScan(node: XNode, idx: number): Scan | string {
  const name = text(child(node, 'name')) || `scan ${idx + 1}`;
  const pts = child(node, 'points');
  if (!pts || pts.attrs.type !== 'CompressedVector') return `${name}: no points`;
  const proto = child(pts, 'prototype');
  if (!proto) throw new PointCloudError(`E57: ${name} has no prototype`);
  const codecs = child(pts, 'codecs');
  for (const c of codecs?.children ?? []) {
    const kids = c.attrs.type === 'Structure' ? c.children : [c];
    for (const k of kids) {
      if (k.name !== 'bitPackCodec' && k.name !== 'inputs')
        throw new PointCloudError(`E57: ${name} uses the codec "${k.name}"; only the standard bitPackCodec is supported`);
    }
  }
  const ls: XNode[] = [];
  leaves(proto, ls);
  const fields = ls.map(fieldOf);
  const fileOffset = Number(pts.attrs.fileOffset);
  const records = Number(pts.attrs.recordCount ?? '0');
  if (!Number.isSafeInteger(records) || records < 0) throw new PointCloudError(`E57: ${name} has an invalid recordCount`);
  if (records > 0 && (!Number.isSafeInteger(fileOffset) || fileOffset <= 0)) throw new PointCloudError(`E57: ${name} has an invalid fileOffset`);

  let rot: Scan['rot'] = null;
  const trans: Scan['trans'] = [0, 0, 0];
  const pose = child(node, 'pose');
  if (pose) {
    const r = child(pose, 'rotation');
    if (r) {
      const q = ['w', 'x', 'y', 'z'].map((k) => numberOf(child(r, k)) ?? 0) as [number, number, number, number];
      const len = Math.hypot(...q);
      if (len > 0 && !(q[0] === 1 && q[1] === 0 && q[2] === 0 && q[3] === 0)) rot = [q[0] / len, q[1] / len, q[2] / len, q[3] / len];
    }
    const t = child(pose, 'translation');
    if (t) ['x', 'y', 'z'].forEach((k, i) => (trans[i] = numberOf(child(t, k)) ?? 0));
  }
  const il = child(node, 'intensityLimits');
  const cl = child(node, 'colorLimits');
  const byName = (s: string): Field | undefined => fields.find((f) => f.name === s);
  const bounds = (f: Field | undefined, dflt: [number, number] | null): [number, number] | null =>
    f && f.lo !== undefined && f.hi !== undefined && f.hi > f.lo ? [f.lo, f.hi] : dflt;
  const intensity = limits(il, 'intensityMinimum', 'intensityMaximum') ?? bounds(byName('intensity'), null);
  const cdef = (c: string): [number, number] => {
    const f = byName(`color${c}`);
    return limits(cl, `color${c}Minimum`, `color${c}Maximum`) ?? bounds(f, f && (f.kind === 'f32' || f.kind === 'f64') ? [0, 1] : [0, 255])!;
  };
  const color = byName('colorRed') && byName('colorGreen') && byName('colorBlue') ? ([cdef('Red'), cdef('Green'), cdef('Blue')] as Scan['color']) : null;
  return { name, fileOffset, records, fields, rot, trans, intensity, color };
}

export interface E57Options {
  /** Page checksums to verify: 'all' (default), 'meta' (header and XML pages only) or 'none'. A mismatch is a warning. */
  checksums?: 'all' | 'meta' | 'none';
}

interface Opened {
  paged: Paged;
  pageSize: number;
  xml: string;
  warnings: string[];
  /** Pages whose checksum does not match. */
  bad: Set<number>;
  checkPages(first: number, last: number): void;
}

/** Header, paging and the XML section (checksums stripped, UTF-8 decoded). */
function openE57(bytes: Uint8Array, mode: 'all' | 'meta' | 'none'): Opened {
  if (!isE57(bytes)) throw new PointCloudError('E57: missing "ASTM-E57" signature');
  if (bytes.length < 48) throw new PointCloudError('E57: file is shorter than the 48 byte header');
  const dv = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const major = dv.getUint32(8, true);
  const minor = dv.getUint32(12, true);
  const u64 = (o: number): number => {
    const v = dv.getBigUint64(o, true);
    return v > BigInt(Number.MAX_SAFE_INTEGER) ? -1 : Number(v);
  };
  const physLen = u64(16);
  const xmlPhys = u64(24);
  const xmlLen = u64(32);
  const pageSize = u64(40);
  if (major !== 1) throw new PointCloudError(`E57: unsupported version ${major}.${minor} (1.x is supported)`);
  if (!(pageSize >= 64 && pageSize <= 1 << 24)) throw new PointCloudError(`E57: invalid page size ${pageSize}`);
  const warnings: string[] = [];
  if (physLen > bytes.length) warnings.push(`file is truncated: ${bytes.length} of ${physLen} bytes present`);
  const paged = new Paged(bytes, pageSize);
  // checksums: a mismatch is reported, not fatal (libE57Format would refuse the file)
  const bad = new Set<number>();
  const checkPages = (first: number, last: number): void => {
    if (mode !== 'none') for (const p of paged.verify(first, last)) bad.add(p);
  };
  if (xmlLen <= 0 || xmlPhys < 48) throw new PointCloudError('E57: the header has no valid XML section');
  const xmlAt = paged.toLogical(xmlPhys, 'XML offset');
  let xmlBytes: Uint8Array;
  try {
    xmlBytes = paged.read(xmlAt, xmlLen, true);
  } catch (e) {
    if (e instanceof Truncated) throw new PointCloudError('E57: file is truncated (the XML section is missing)');
    throw e;
  }
  checkPages(0, 0);
  checkPages(Math.floor(xmlAt / paged.payload), Math.floor((xmlAt + xmlLen - 1) / paged.payload));
  const xml = new TextDecoder('utf-8').decode(xmlBytes).replace(/\0+$/, '');
  return { paged, pageSize, xml, warnings, bad, checkPages: mode === 'all' ? checkPages : () => undefined };
}

/** The XML section of an E57 file as text (for inspection and tests). */
export function readE57Xml(bytes: Uint8Array): string {
  return openE57(bytes, 'none').xml;
}

export function readE57(bytes: Uint8Array, name: string, onProgress?: ProgressFn, opts: E57Options = {}): PointCloudData {
  const { paged, pageSize, xml, warnings, bad, checkPages } = openE57(bytes, opts.checksums ?? 'all');
  let root: XNode;
  try {
    root = parseXml(xml);
  } catch (e) {
    const why = e instanceof XmlError ? e.message : String(e);
    throw new PointCloudError(`E57: the XML section is malformed (${why})${bad.size ? '; page checksums do not match, the file is corrupt' : ''}`);
  }
  const data3D = child(root, 'data3D');
  const scanNodes = data3D ? data3D.children : [];
  if (!scanNodes.length) throw new PointCloudError(`E57: ${name} has no 3D scans (data3D is empty)${child(root, 'images2D')?.children.length ? '; it holds images only' : ''}`);
  const scans: Scan[] = [];
  scanNodes.forEach((n, i) => {
    const s = readScan(n, i);
    if (typeof s === 'string') warnings.push(s);
    else if (s.records > 0) scans.push(s);
  });

  if (!scans.length) throw new PointCloudError(`E57: ${name} has no points (${scanNodes.length > 1 ? 'all its scans are' : 'its scan is'} empty)`);
  const has = (s: Scan, f: string): boolean => s.fields.some((x) => x.name === f);
  const cart = (s: Scan): boolean => has(s, 'cartesianX') && has(s, 'cartesianY') && has(s, 'cartesianZ');
  const sph = (s: Scan): boolean => has(s, 'sphericalRange') && has(s, 'sphericalAzimuth') && has(s, 'sphericalElevation');
  const usable = scans.filter((s) => {
    if (cart(s) || sph(s)) return true;
    warnings.push(`${s.name}: no cartesian or spherical coordinates, skipped`);
    return false;
  });
  if (!usable.length) throw new PointCloudError(`E57: no scan in ${name} has point coordinates`);
  if (usable.length > E57_MANY_SCANS) warnings.push(`${usable.length} scans merged into one cloud`);
  const anyColor = usable.some((s) => s.color);
  const anyIntensity = usable.some((s) => has(s, 'intensity'));
  if (anyColor && usable.some((s) => !s.color)) warnings.push('some scans have no colour (drawn grey)');
  const totalRecords = usable.reduce((a, s) => a + s.records, 0);
  // capacity: the record count, bounded by what the file can hold (a corrupt count must not allocate gigabytes)
  const builder = new PointBuilder({ color: anyColor, intensity: anyIntensity }, Math.min(totalRecords, bytes.length * 2, 50_000_000));
  builder.warnings.push(...warnings);

  let doneRecords = 0;
  const errors: string[] = [];
  for (const s of usable) {
    try {
      readPoints(paged, s, builder, { cart: cart(s), color: anyColor, intensity: anyIntensity }, (k) => onProgress?.((doneRecords + k) / totalRecords, 'parse'), checkPages);
    } catch (e) {
      if (e instanceof PointCloudError) {
        errors.push(e.message);
        builder.warnings.push(e.message.replace(/^E57: /, ''));
      } else throw e;
    }
    doneRecords += s.records;
  }
  if (bad.size) {
    const first = Math.min(...bad);
    builder.warnings.push(`${bad.size} page checksum${bad.size > 1 ? 's do' : ' does'} not match (first at byte ${first * pageSize}); the file may be corrupt`);
  }
  if (builder.count === 0 && errors.length) throw new PointCloudError(errors[0]!);
  return builder.finish(name, 'e57');
}

/** Stream the binary section of one scan into the builder. Throws PointCloudError (after adding what it read) when the
 *  section is truncated or malformed. */
function readPoints(paged: Paged, s: Scan, builder: PointBuilder, want: { cart: boolean; color: boolean; intensity: boolean }, progress: (records: number) => void, verify: (first: number, last: number) => void): void {
  const at = paged.toLogical(s.fileOffset, `${s.name}: section offset`);
  let head: Uint8Array;
  try {
    head = paged.read(at, 32);
  } catch {
    throw new PointCloudError(`E57: file is truncated: ${s.name} is missing`);
  }
  const hv = new DataView(head.buffer, head.byteOffset, 32);
  if (head[0] !== 1) throw new PointCloudError(`E57: ${s.name}: bad compressed vector section header`);
  const secLen = Number(hv.getBigUint64(8, true));
  const dataPhys = Number(hv.getBigUint64(16, true));
  const secEnd = at + secLen;
  let q = paged.toLogical(dataPhys, `${s.name}: data offset`);
  verify(Math.floor(at / paged.payload), Math.floor(Math.min(secEnd, paged.logicalSize) / paged.payload));

  const fields = s.fields;
  const useCart = want.cart;
  const idx = (n: string): number => fields.findIndex((f) => f.name === n);
  const roles = useCart
    ? { a: idx('cartesianX'), b: idx('cartesianY'), c: idx('cartesianZ'), inv: idx('cartesianInvalidState') }
    : { a: idx('sphericalRange'), b: idx('sphericalAzimuth'), c: idx('sphericalElevation'), inv: idx('sphericalInvalidState') };
  const iI = want.intensity ? idx('intensity') : -1;
  const iIinv = idx('isIntensityInvalid');
  const iR = s.color ? idx('colorRed') : -1;
  const iG = s.color ? idx('colorGreen') : -1;
  const iB = s.color ? idx('colorBlue') : -1;
  const iCinv = idx('isColorInvalid');
  const wanted = [roles.a, roles.b, roles.c, roles.inv, iI, iIinv, iR, iG, iB, iCinv].filter((i) => i >= 0);
  const streams: (Stream | null)[] = fields.map((f, i) => (wanted.includes(i) ? new Stream(f, s.records) : null));
  const active = streams.filter((x): x is Stream => !!x && x.f.kind !== 'const');

  const pick = (i: number): Stream | null => (i >= 0 ? streams[i]! : null);
  const [sa, sb, sc, sinv, si, siinv, sr, sg, sbl, scinv] = [roles.a, roles.b, roles.c, roles.inv, iI, iIinv, iR, iG, iB, iCinv].map(pick);
  const hasColor = want.color;
  const [cr, cg, cb] = s.color ?? [[0, 1], [0, 1], [0, 1]];
  const ilo = s.intensity ? s.intensity[0] : 0;
  const irange = s.intensity ? s.intensity[1] - s.intensity[0] : 1;
  const rot = s.rot;
  const [tx, ty, tz] = s.trans;
  // rotation matrix of the unit quaternion
  let m00 = 1, m01 = 0, m02 = 0, m10 = 0, m11 = 1, m12 = 0, m20 = 0, m21 = 0, m22 = 1;
  if (rot) {
    const [w, x, y, z] = rot;
    m00 = 1 - 2 * (y * y + z * z); m01 = 2 * (x * y - w * z); m02 = 2 * (x * z + w * y);
    m10 = 2 * (x * y + w * z); m11 = 1 - 2 * (x * x + z * z); m12 = 2 * (y * z - w * x);
    m20 = 2 * (x * z - w * y); m21 = 2 * (y * z + w * x); m22 = 1 - 2 * (x * x + y * y);
  }

  let emitted = 0;
  const emit = (upto: number): void => {
    const n = upto - emitted;
    if (n <= 0) return;
    const va = sa!.vals, vb = sb!.vals, vc = sc!.vals;
    const ka = sa!.f.kind === 'const', kb = sb!.f.kind === 'const', kc = sc!.f.kind === 'const';
    const inv = sinv && sinv.f.kind !== 'const' ? sinv.vals : null;
    const invConst = sinv && sinv.f.kind === 'const' ? sinv.constValue : 0;
    if (invConst !== 0) {
      // every point of the scan is flagged invalid
    } else {
      for (let j = 0; j < n; j++) {
        if (inv && inv[j] !== 0) continue;
        let x = ka ? sa!.constValue : va[j]!;
        let y = kb ? sb!.constValue : vb[j]!;
        let z = kc ? sc!.constValue : vc[j]!;
        if (!useCart) {
          const r = x, az = y, el = z;
          const ce = Math.cos(el);
          x = r * ce * Math.cos(az);
          y = r * ce * Math.sin(az);
          z = r * Math.sin(el);
        }
        const k = builder.add(m00 * x + m01 * y + m02 * z + tx, m10 * x + m11 * y + m12 * z + ty, m20 * x + m21 * y + m22 * z + tz);
        if (k < 0) continue;
        if (si) {
          const bad = siinv ? (siinv.f.kind === 'const' ? siinv.constValue : siinv.vals[j]!) !== 0 : false;
          const v = si.f.kind === 'const' ? si.constValue : si.vals[j]!;
          builder.setIntensity(k, bad ? 0 : (v - ilo) / irange);
        }
        if (hasColor) {
          if (!sr) builder.setColor(k, 0.5, 0.5, 0.5);
          else {
            const bad = scinv ? (scinv.f.kind === 'const' ? scinv.constValue : scinv.vals[j]!) !== 0 : false;
            if (bad) builder.setColor(k, 0.5, 0.5, 0.5);
            else {
              const r = sr.f.kind === 'const' ? sr.constValue : sr.vals[j]!;
              const g = sg!.f.kind === 'const' ? sg!.constValue : sg!.vals[j]!;
              const b = sbl!.f.kind === 'const' ? sbl!.constValue : sbl!.vals[j]!;
              builder.setColor(k, clamp01((r - cr[0]) / (cr[1] - cr[0])), clamp01((g - cg[0]) / (cg[1] - cg[0])), clamp01((b - cb[0]) / (cb[1] - cb[0])));
            }
          }
        }
      }
    }
    for (const st of active) st.shift(n);
    emitted = upto;
  };
  const available = (): number => {
    let a = s.records;
    for (const st of active) if (st.total < a) a = st.total;
    return a;
  };

  const fail = (why: string): never => {
    emit(available());
    throw new PointCloudError(`E57: ${why}: ${builder.count.toLocaleString('en-US')} points read`);
  };

  let packets = 0;
  while (emitted < s.records && q < secEnd) {
    let ph: Uint8Array;
    try {
      ph = paged.read(q, 4);
    } catch {
      fail(`file is truncated in ${s.name}`);
    }
    const type = ph![0]!;
    const plen = (ph![2]! | (ph![3]! << 8)) + 1;
    if (type === 1) {
      let pk: Uint8Array;
      try {
        pk = paged.read(q, plen);
      } catch {
        fail(`file is truncated in ${s.name}`);
      }
      const pv = new DataView(pk!.buffer, pk!.byteOffset, pk!.byteLength);
      if (plen < 6) fail(`${s.name}: data packet too short`);
      const nStreams = pv.getUint16(4, true);
      if (nStreams !== fields.length) fail(`${s.name}: data packet has ${nStreams} bytestreams, the prototype ${fields.length} fields`);
      let o = 6 + 2 * nStreams;
      if (o > plen) fail(`${s.name}: malformed data packet`);
      for (let k = 0; k < nStreams; k++) {
        const bl = pv.getUint16(6 + 2 * k, true);
        if (o + bl > plen) fail(`${s.name}: bytestream buffers overrun the data packet`);
        const st = streams[k];
        if (st) st.push(pk!.subarray(o, o + bl));
        o += bl;
      }
      emit(available());
      if ((++packets & 15) === 0) progress(emitted);
    } else if (type !== 0 && type !== 2) {
      fail(`${s.name}: unknown packet type ${type}`);
    }
    // index (0) and empty (2) packets are skipped
    q += plen;
  }
  emit(available());
  if (emitted < s.records) {
    const missing = active.some((st) => st.total < s.records);
    if (missing) throw new PointCloudError(`E57: ${s.name} ends early: ${emitted.toLocaleString('en-US')} of ${s.records.toLocaleString('en-US')} records present`);
  }
}

const clamp01 = (v: number): number => (v < 0 ? 0 : v > 1 ? 1 : v);
