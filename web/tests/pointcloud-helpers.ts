// Fixture writers for the point cloud tests: small files generated from point lists.

export interface TestPoint {
  x: number;
  y: number;
  z: number;
  r?: number;
  g?: number;
  b?: number;
  i?: number;
  c?: number;
}

/** A deterministic set of points around a large offset (to prove precision handling). */
export function grid(n: number, base: [number, number, number] = [0, 0, 0]): TestPoint[] {
  const out: TestPoint[] = [];
  for (let k = 0; k < n; k++) {
    out.push({
      x: base[0] + (k % 10) * 0.125, y: base[1] + Math.floor(k / 10) * 0.25, z: base[2] + (k % 7) * 0.5,
      r: (k * 7) % 256, g: (k * 13) % 256, b: (k * 29) % 256, i: 100 + k, c: k % 3 === 0 ? 2 : 6,
    });
  }
  return out;
}

const enc = (s: string): Uint8Array => new TextEncoder().encode(s);

function concat(...parts: Uint8Array[]): Uint8Array {
  const out = new Uint8Array(parts.reduce((s, p) => s + p.length, 0));
  let o = 0;
  for (const p of parts) { out.set(p, o); o += p.length; }
  return out;
}

export function plyAscii(pts: TestPoint[], opts: { faces?: boolean } = {}): Uint8Array {
  let h = `ply\nformat ascii 1.0\ncomment test\nelement vertex ${pts.length}\nproperty double x\nproperty double y\nproperty double z\n` +
    'property uchar red\nproperty uchar green\nproperty uchar blue\nproperty float intensity\n';
  if (opts.faces) h += 'element face 1\nproperty list uchar int vertex_indices\n';
  h += 'end_header\n';
  let body = pts.map((p) => `${p.x} ${p.y} ${p.z} ${p.r} ${p.g} ${p.b} ${p.i}`).join('\n') + '\n';
  if (opts.faces) body += '3 0 1 2\n';
  return enc(h + body);
}

export function plyBinary(pts: TestPoint[], le: boolean, opts: { faces?: boolean; floatXyz?: boolean } = {}): Uint8Array {
  const xyz = opts.floatXyz ? 'float' : 'double';
  const h = `ply\nformat ${le ? 'binary_little_endian' : 'binary_big_endian'} 1.0\nelement vertex ${pts.length}\nproperty ${xyz} x\nproperty ${xyz} y\nproperty ${xyz} z\n` +
    'property uchar red\nproperty uchar green\nproperty uchar blue\nproperty float intensity\n' +
    (opts.faces ? 'element face 1\nproperty list uchar int vertex_indices\n' : '') + 'end_header\n';
  const rec = (opts.floatXyz ? 12 : 24) + 3 + 4;
  const body = new Uint8Array(rec * pts.length + (opts.faces ? 1 + 12 : 0));
  const dv = new DataView(body.buffer);
  let o = 0;
  for (const p of pts) {
    if (opts.floatXyz) { dv.setFloat32(o, p.x, le); dv.setFloat32(o + 4, p.y, le); dv.setFloat32(o + 8, p.z, le); o += 12; }
    else { dv.setFloat64(o, p.x, le); dv.setFloat64(o + 8, p.y, le); dv.setFloat64(o + 16, p.z, le); o += 24; }
    dv.setUint8(o++, p.r!); dv.setUint8(o++, p.g!); dv.setUint8(o++, p.b!);
    dv.setFloat32(o, p.i!, le); o += 4;
  }
  if (opts.faces) { dv.setUint8(o++, 3); dv.setInt32(o, 0, le); dv.setInt32(o + 4, 1, le); dv.setInt32(o + 8, 2, le); }
  return concat(enc(h), body);
}

const f32 = new Float32Array(1);
const u32 = new Uint32Array(f32.buffer);
export function packRgb(r: number, g: number, b: number): number {
  u32[0] = (r << 16) | (g << 8) | b;
  return f32[0]!;
}

function pcdHeader(n: number, data: string): string {
  return `# .PCD v0.7 - Point Cloud Data file format\nVERSION 0.7\nFIELDS x y z rgb intensity\nSIZE 4 4 4 4 4\nTYPE F F F F F\nCOUNT 1 1 1 1 1\nWIDTH ${n}\nHEIGHT 1\nVIEWPOINT 0 0 0 1 0 0 0\nPOINTS ${n}\nDATA ${data}\n`;
}

export function pcdAscii(pts: TestPoint[]): Uint8Array {
  return enc(pcdHeader(pts.length, 'ascii') + pts.map((p) => `${p.x} ${p.y} ${p.z} ${packRgb(p.r!, p.g!, p.b!)} ${p.i}`).join('\n') + '\n');
}

function pcdRows(pts: TestPoint[]): Float32Array {
  const a = new Float32Array(pts.length * 5);
  pts.forEach((p, k) => a.set([p.x, p.y, p.z, packRgb(p.r!, p.g!, p.b!), p.i!], k * 5));
  return a;
}

export function pcdBinary(pts: TestPoint[]): Uint8Array {
  return concat(enc(pcdHeader(pts.length, 'binary')), new Uint8Array(pcdRows(pts).buffer));
}

/** binary_compressed: column-major payload, compressed with literal-only LZF runs (a valid, if unambitious, stream). */
export function pcdCompressed(pts: TestPoint[]): Uint8Array {
  const rows = pcdRows(pts);
  const col = new Float32Array(rows.length);
  for (let f = 0; f < 5; f++) for (let k = 0; k < pts.length; k++) col[f * pts.length + k] = rows[k * 5 + f]!;
  const raw = new Uint8Array(col.buffer);
  const chunks: number[] = [];
  for (let i = 0; i < raw.length; i += 32) {
    const n = Math.min(32, raw.length - i);
    chunks.push(n - 1, ...raw.subarray(i, i + n));
  }
  const comp = Uint8Array.from(chunks);
  const sizes = new Uint8Array(8);
  new DataView(sizes.buffer).setUint32(0, comp.length, true);
  new DataView(sizes.buffer).setUint32(4, raw.length, true);
  return concat(enc(pcdHeader(pts.length, 'binary_compressed')), sizes, comp);
}

export interface LasOpts {
  format?: number;
  minor?: number;
  scale?: number;
  offset?: [number, number, number];
  recordExtra?: number;
  /** Set the LAZ bit in the format byte. */
  laz?: boolean;
  /** Write a "laszip encoded" VLR instead. */
  lazVlr?: boolean;
  /** Leave out the last k points but keep the header count. */
  truncate?: number;
  /** 1.4 only: put the count in the 64-bit field and zero the legacy one. */
  bigCount?: boolean;
  signature?: string;
}

const REC: Record<number, number> = { 0: 20, 1: 28, 2: 26, 3: 34, 6: 30, 7: 36, 8: 38 };
const RGB_AT: Record<number, number> = { 2: 20, 3: 28, 7: 30, 8: 30 };

export function las(pts: TestPoint[], o: LasOpts = {}): Uint8Array {
  const fmt = o.format ?? 2;
  const minor = o.minor ?? 2;
  const scale = o.scale ?? 0.001;
  const offset = o.offset ?? [0, 0, 0];
  const headerSize = minor >= 4 ? 375 : 227;
  const vlr = o.lazVlr ? 54 + 4 : 0;
  const rec = REC[fmt]! + (o.recordExtra ?? 0);
  const n = pts.length;
  const total = headerSize + vlr + rec * n;
  const b = new Uint8Array(total);
  const dv = new DataView(b.buffer);
  b.set(enc(o.signature ?? 'LASF'), 0);
  dv.setUint8(24, 1);
  dv.setUint8(25, minor);
  dv.setUint16(94, headerSize, true);
  dv.setUint32(96, headerSize + vlr, true);
  dv.setUint32(100, o.lazVlr ? 1 : 0, true);
  dv.setUint8(104, fmt | (o.laz ? 0x80 : 0));
  dv.setUint16(105, rec, true);
  dv.setUint32(107, o.bigCount ? 0 : n, true);
  if (minor >= 4) dv.setBigUint64(247, BigInt(n), true);
  dv.setFloat64(131, scale, true); dv.setFloat64(139, scale, true); dv.setFloat64(147, scale, true);
  dv.setFloat64(155, offset[0], true); dv.setFloat64(163, offset[1], true); dv.setFloat64(171, offset[2], true);
  if (o.lazVlr) {
    b.set(enc('laszip encoded'), headerSize + 2);
    dv.setUint16(headerSize + 18, 22204, true);
    dv.setUint16(headerSize + 20, 4, true);
  }
  let at = headerSize + vlr;
  for (const p of pts) {
    dv.setInt32(at, Math.round((p.x - offset[0]) / scale), true);
    dv.setInt32(at + 4, Math.round((p.y - offset[1]) / scale), true);
    dv.setInt32(at + 8, Math.round((p.z - offset[2]) / scale), true);
    dv.setUint16(at + 12, p.i ?? 0, true);
    if (fmt >= 6) dv.setUint8(at + 16, p.c ?? 0);
    else dv.setUint8(at + 15, (p.c ?? 0) | 0xe0); // top bits are flags (synthetic, withheld, key point): must be masked
    const rgb = RGB_AT[fmt];
    if (rgb !== undefined) {
      dv.setUint16(at + rgb, (p.r ?? 0) * 257, true);
      dv.setUint16(at + rgb + 2, (p.g ?? 0) * 257, true);
      dv.setUint16(at + rgb + 4, (p.b ?? 0) * 257, true);
    }
    at += rec;
  }
  return o.truncate ? b.subarray(0, total - o.truncate * rec) : b;
}
