// E57 reader. The fixtures in tests/fixtures/pointcloud were written by libE57Format (through pye57, see
// tests/fixtures/make_e57_fixtures.py) and e57-expected.json holds what libE57Format reads back from them, with the pose
// applied. Files with other packet layouts, page sizes and damage are derived from them here at runtime.

import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { detectFormat, isPointCloudName, parsePointCloud, POINTCLOUD_EXTENSIONS } from '../src/pointcloud/readers';
import { crc32c, readE57, readE57Xml } from '../src/pointcloud/readers/e57';
import { CloudSession } from '../src/pointcloud/session';
import type { PointCloudData } from '../src/pointcloud/types';
import { PointCloudError } from '../src/pointcloud/types';

const DIR = resolve(dirname(fileURLToPath(import.meta.url)), 'fixtures/pointcloud');
const load = (f: string): Uint8Array => new Uint8Array(readFileSync(resolve(DIR, f)));

interface Expected {
  count: number;
  records: number;
  scans: number;
  sum: number[];
  min: number[];
  max: number[];
  points: { i: number; xyz: number[]; rgb?: number[]; intensity?: number }[];
}
const EXPECTED = JSON.parse(readFileSync(resolve(DIR, 'e57-expected.json'), 'utf8')) as Record<string, Expected>;

const abs = (d: PointCloudData, i: number): [number, number, number] => [d.origin[0] + d.positions[i * 3]!, d.origin[1] + d.positions[i * 3 + 1]!, d.origin[2] + d.positions[i * 3 + 2]!];

/** Compare a cloud with libE57Format's reading. `tol` in metres (Float32 relative to the first point). */
function expectMatches(d: PointCloudData, ex: Expected, tol: number, colourTol = 0): void {
  expect(d.format).toBe('e57');
  expect(d.count).toBe(ex.count);
  for (const p of ex.points) {
    const a = abs(d, p.i);
    // Float32 relative to the first point: the rounding grows with the distance from it
    const far = Math.hypot(a[0] - d.origin[0], a[1] - d.origin[1], a[2] - d.origin[2]);
    for (let k = 0; k < 3; k++) expect(Math.abs(a[k]! - p.xyz[k]!)).toBeLessThanOrEqual(tol + far * 1.2e-7);
    if (p.rgb) for (let k = 0; k < 3; k++) expect(Math.abs(d.colors![p.i * 3 + k]! - p.rgb[k]!)).toBeLessThanOrEqual(colourTol);
    if (p.intensity !== undefined) expect(Math.abs(d.intensity![p.i]! - p.intensity)).toBeLessThanOrEqual(1e-6);
  }
  for (let k = 0; k < 3; k++) {
    expect(Math.abs(d.boundsMin[k]! - ex.min[k]!)).toBeLessThanOrEqual(1e-6);
    expect(Math.abs(d.boundsMax[k]! - ex.max[k]!)).toBeLessThanOrEqual(1e-6);
  }
  // the mean of every point, so the points between the sampled ones are covered too
  const sum: [number, number, number] = [0, 0, 0];
  for (let i = 0; i < d.count; i++) for (let k = 0; k < 3; k++) sum[k]! += d.positions[i * 3 + k]!;
  for (let k = 0; k < 3; k++) expect(Math.abs(d.origin[k]! + sum[k]! / d.count - ex.sum[k]! / ex.count)).toBeLessThanOrEqual(tol);
}

// ---------------------------------------------------------------- a small re-writer for derived files

function logical(bytes: Uint8Array, pageSize = 1024): Uint8Array {
  const pay = pageSize - 4;
  const out = new Uint8Array(Math.ceil(bytes.length / pageSize) * pay);
  for (let p = 0, o = 0; p < bytes.length; p += pageSize, o += pay) out.set(bytes.subarray(p, p + pay), o);
  return out;
}
const toLogical = (phys: number, ps = 1024): number => Math.floor(phys / ps) * (ps - 4) + (phys % ps);

/** The concatenated bytestreams of the first scan (data packets in order). */
function streamsOf(file: Uint8Array): { streams: Uint8Array[]; xml: string } {
  const xml = readE57Xml(file);
  const off = Number(/fileOffset="(\d+)"/.exec(xml)![1]);
  const L = logical(file);
  const dv = new DataView(L.buffer);
  const at = toLogical(off);
  const end = at + Number(dv.getBigUint64(at + 8, true));
  let q = toLogical(Number(dv.getBigUint64(at + 16, true)));
  const parts: number[][][] = [];
  while (q < end) {
    const len = dv.getUint16(q + 2, true) + 1;
    if (L[q] === 1) {
      const n = dv.getUint16(q + 4, true);
      let o = q + 6 + 2 * n;
      for (let k = 0; k < n; k++) {
        const bl = dv.getUint16(q + 6 + 2 * k, true);
        (parts[k] ??= []).push(Array.from(L.subarray(o, o + bl)));
        o += bl;
      }
    }
    q += len;
  }
  return { streams: parts.map((ps) => Uint8Array.from(ps.flat())), xml };
}

/** Write an E57 with the given XML (whose only scan has fileOffset 48) and bytestreams, cut into packets of
 *  `chunk(stream, packet)` bytes per stream; optionally with empty and index packets in between. */
function writeE57(xml: string, streams: Uint8Array[], opts: { pageSize?: number; chunk: (k: number, p: number) => number; extraPackets?: boolean }): Uint8Array {
  const ps = opts.pageSize ?? 1024;
  const pay = ps - 4;
  const toPhys = (l: number): number => Math.floor(l / pay) * ps + (l % pay);
  const packets: Uint8Array[] = [];
  const pos = streams.map(() => 0);
  for (let p = 0; pos.some((v, k) => v < streams[k]!.length); p++) {
    if (opts.extraPackets && p % 2 === 1) {
      const empty = new Uint8Array(8);
      empty[0] = 2;
      empty[2] = 7; // length - 1
      const index = new Uint8Array(16);
      index[2] = 15; // index packet, no entries
      packets.push(empty, index);
    }
    const lens = streams.map((s, k) => Math.min(opts.chunk(k, p), s.length - pos[k]!));
    const body = 6 + 2 * streams.length + lens.reduce((a, b) => a + b, 0);
    const total = Math.ceil(body / 4) * 4;
    const pk = new Uint8Array(total);
    const dv = new DataView(pk.buffer);
    pk[0] = 1;
    dv.setUint16(2, total - 1, true);
    dv.setUint16(4, streams.length, true);
    let o = 6 + 2 * streams.length;
    streams.forEach((s, k) => {
      dv.setUint16(6 + 2 * k, lens[k]!, true);
      pk.set(s.subarray(pos[k]!, pos[k]! + lens[k]!), o);
      o += lens[k]!;
      pos[k]! += lens[k]!;
    });
    packets.push(pk);
  }
  const xmlBytes = new TextEncoder().encode(xml);
  const secLen = 32 + packets.reduce((a, b) => a + b.length, 0);
  const L = new Uint8Array(48 + secLen + xmlBytes.length);
  const dv = new DataView(L.buffer);
  L[48] = 1;
  dv.setBigUint64(48 + 8, BigInt(secLen), true);
  dv.setBigUint64(48 + 16, BigInt(toPhys(80)), true);
  let o = 80;
  for (const p of packets) {
    L.set(p, o);
    o += p.length;
  }
  L.set(xmlBytes, o);
  const pages = Math.ceil(L.length / pay);
  L.set(new TextEncoder().encode('ASTM-E57'), 0);
  dv.setUint32(8, 1, true);
  dv.setBigUint64(16, BigInt(pages * ps), true);
  dv.setBigUint64(24, BigInt(toPhys(o)), true);
  dv.setBigUint64(32, BigInt(xmlBytes.length), true);
  dv.setBigUint64(40, BigInt(ps), true);
  const out = new Uint8Array(pages * ps);
  for (let p = 0; p < pages; p++) {
    out.set(L.subarray(p * pay, (p + 1) * pay), p * ps);
    const c = crc32c(out, p * ps, p * ps + pay);
    new DataView(out.buffer).setUint32(p * ps + pay, c, false);
  }
  return out;
}

// ---------------------------------------------------------------- reading libE57Format files

describe('E57 files written by libE57Format', () => {
  it('cartesian Float single (pye57 writer), georeferenced, colour and intensity', () => {
    const d = parsePointCloud(load('e57-cart-float.e57'), 'scan.e57');
    expectMatches(d, EXPECTED['e57-cart-float.e57']!, 2e-6);
    expect(d.warnings).toEqual([]);
    expect(d.colors).toBeDefined();
    // intensity normalised by intensityLimits (pye57 writes the data's own minimum and maximum)
    expect(d.intensityRange![0]).toBeCloseTo(0, 6);
    expect(d.intensityRange![1]).toBeCloseTo(1, 6);
    // double precision: the coordinates are around 2.6e6, the stored Float32 are small
    expect(d.origin[0]).toBeGreaterThan(2_600_000);
    expect(Math.max(...Array.from(d.positions, Math.abs))).toBeLessThan(25);
  });

  it('ScaledInteger, 16-bit colour, invalid states, several data packets, XML across pages', () => {
    const file = load('e57-cart-scaled.e57');
    const ex = EXPECTED['e57-cart-scaled.e57']!;
    const d = parsePointCloud(file, 'scaled.e57');
    expectMatches(d, ex, 2e-6, 1);
    expect(d.warnings).toEqual([]);
    expect(ex.records).toBe(12000);
    expect(d.count).toBe(10425); // states 1 (direction only) and 2 (invalid) are skipped
    // 1 mm quantisation survives the large offset exactly
    const a = abs(d, 0);
    expect(Math.abs(a[0] * 1000 - Math.round(a[0] * 1000))).toBeLessThan(1e-3);
    expect(d.intensityRange![1]).toBeLessThanOrEqual(1);
    // the XML starts mid page and spans six pages; its UTF-8 text is intact once the checksums are removed
    const xml = readE57Xml(file);
    expect(xml).toContain('Façade scan, Zürich – ' + 'Prüfung der Bauausführung ✓ '.repeat(90));
    expect(xml.trimEnd().endsWith('</e57Root>')).toBe(true);
    const dv = new DataView(file.buffer, file.byteOffset);
    expect(Number(dv.getBigUint64(24, true)) % 1024).not.toBe(0);
    expect(Number(dv.getBigUint64(32, true))).toBeGreaterThan(4 * 1020);
  });

  it('spherical coordinates with a pose, invalid states in a 64-bit Integer bytestream', () => {
    const d = parsePointCloud(load('e57-spherical.e57'), 's.e57');
    expectMatches(d, EXPECTED['e57-spherical.e57']!, 2e-6);
    expect(d.count).toBe(340);
    expect(d.colors).toBeUndefined();
  });

  it('two scans with their poses merged into one cloud (Float double and a 27 bit ScaledInteger)', () => {
    const d = parsePointCloud(load('e57-two-scans.e57'), 'two.e57');
    const ex = EXPECTED['e57-two-scans.e57']!;
    expect(ex.scans).toBe(2);
    expectMatches(d, ex, 2e-6);
    expect(d.count).toBe(150 + 200);
    // the first scan is turned 90 degrees about Z and moved to (100, 200, 3): its points sit around there
    const a = abs(d, 0);
    expect(Math.hypot(a[0] - 100, a[1] - 200)).toBeLessThan(5 * Math.SQRT2 + 1e-9);
  });

  it('every page checksum of the fixture files matches', () => {
    for (const f of Object.keys(EXPECTED)) expect(readE57(load(f), f, undefined, { checksums: 'all' }).warnings, f).toEqual([]);
  });

  it('runs through the session (format, counts, no classification)', () => {
    const s = new CloudSession();
    const file = load('e57-cart-scaled.e57');
    const info = s.load(file.slice().buffer, 'scaled.e57');
    expect(info.format).toBe('e57');
    expect(info.originalCount).toBe(10425);
    expect(info.hasColor).toBe(true);
    expect(info.hasIntensity).toBe(true);
    expect(info.hasClassification).toBe(false);
    expect(s.decimate(1000).shown.count).toBe(1000);
  });
});

describe('E57 files from other writers (libE57Format test data)', () => {
  it('the reference implementation\'s bunny (libe57.org example data): ScaledInteger, invalid state field', () => {
    const d = parsePointCloud(load('e57-ref-bunny-int32.e57'), 'bunnyInt32.e57');
    expectMatches(d, EXPECTED['e57-ref-bunny-int32.e57']!, 1e-7);
    expect(d.count).toBe(30571);
    expect(d.warnings).toEqual([]);
  });
  it('LAStools las2e57: no colorLimits (the 16-bit field bounds apply), extension elements, blobs, groupings', () => {
    const d = parsePointCloud(load('e57-las2e57-colour.e57'), 'ColourRepresentation.e57');
    expectMatches(d, EXPECTED['e57-las2e57-colour.e57']!, 1e-7);
    expect(d.count).toBe(153);
  });
});

describe('E57 detection', () => {
  it('by signature first, then by extension', () => {
    const file = load('e57-two-scans.e57');
    expect(detectFormat(file, 'scan.e57')).toBe('e57');
    expect(detectFormat(file, 'scan.bin')).toBe('e57');
    expect(detectFormat(file, 'scan.txt')).toBe('e57');
    expect(parsePointCloud(file, 'misnamed.xyz').count).toBe(350);
    expect(detectFormat(new TextEncoder().encode('1 2 3\n'), 'scan.e57')).toBe('e57');
    expect(() => parsePointCloud(new TextEncoder().encode('1 2 3\n'), 'scan.E57')).toThrow(/ASTM-E57/);
  });
  it('is an accepted extension for the file input and the drop handler', () => {
    expect(POINTCLOUD_EXTENSIONS).toContain('.e57');
    expect(isPointCloudName('Scan 2026-11-05.E57')).toBe(true);
  });
});

describe('E57 packet layouts', () => {
  const file = load('e57-cart-scaled.e57');
  const { streams, xml } = streamsOf(file);
  const ex = EXPECTED['e57-cart-scaled.e57']!;

  it('bytestreams cut at odd byte counts in every packet (values split across packets)', () => {
    expect(streams.length).toBe(8);
    const d = parsePointCloud(writeE57(xml, streams, { chunk: (k, p) => 333 + 97 * k + 13 * (p % 5) }), 'odd.e57');
    expectMatches(d, ex, 2e-6, 1);
    expect(d.warnings).toEqual([]);
  });

  it('streams that run far ahead of each other, one byte packets, empty and index packets', () => {
    const d = parsePointCloud(writeE57(xml, streams, { chunk: (k, p) => (k === 0 ? 20000 : k === 3 ? 1 + (p % 3) : 1500 + k), extraPackets: true }), 'ahead.e57');
    expectMatches(d, ex, 2e-6, 1);
  });

  it('page sizes other than 1024', () => {
    for (const pageSize of [128, 4096]) {
      const d = parsePointCloud(writeE57(xml, streams, { pageSize, chunk: () => 4000 }), 'p.e57');
      expectMatches(d, ex, 2e-6, 1);
      expect(d.warnings).toEqual([]);
    }
  });
});

describe('E57 checksums and damage', () => {
  it('CRC-32C matches the standard check value', () => {
    expect(crc32c(new TextEncoder().encode('123456789'))).toBe(0xe3069283);
    expect(crc32c(new Uint8Array(0))).toBe(0);
  });

  it('a flipped byte in the point data is a checksum warning, not a failure', () => {
    const file = load('e57-cart-scaled.e57').slice();
    file[50_000]! ^= 0x10;
    const d = parsePointCloud(file, 'flip.e57');
    expect(d.count).toBe(10425);
    expect(d.warnings.join(' ')).toMatch(/1 page checksum does not match \(first at byte 49152\)/);
    expect(readE57(file, 'flip.e57', undefined, { checksums: 'none' }).warnings).toEqual([]);
    expect(readE57(file, 'flip.e57', undefined, { checksums: 'meta' }).warnings).toEqual([]);
  });

  it('a damaged checksum is reported', () => {
    const file = load('e57-two-scans.e57').slice();
    file[1023]! ^= 1; // the checksum of page 0
    file[3 * 1024 + 1022]! ^= 1;
    expect(parsePointCloud(file, 'c.e57').warnings.join(' ')).toMatch(/2 page checksums do not match \(first at byte 0\)/);
  });

  it('a truncated binary section keeps the points read so far and says so', () => {
    const full = load('e57-cart-scaled.e57');
    // keep the XML (at the end) reachable by moving it: rebuild with the streams, then cut packets away instead
    const { streams, xml } = streamsOf(full);
    const file = writeE57(xml, streams, { chunk: () => 3000 });
    // cut the last data packets by declaring a shorter section: patch the section length (and its page's checksum)
    const short = file.slice();
    const dv = new DataView(short.buffer);
    dv.setBigUint64(48 + 8, 32n + 60_000n, true);
    dv.setUint32(1020, crc32c(short, 0, 1020), false);
    const d = parsePointCloud(short, 'short.e57');
    expect(d.count).toBeGreaterThan(1000);
    expect(d.count).toBeLessThan(10425);
    expect(d.warnings.join(' ')).toMatch(/ends early: [\d,]+ of 12,000 records present/);
  });

  it('a file cut short is an error when nothing can be read, a warning otherwise', () => {
    const full = load('e57-cart-scaled.e57');
    expect(() => parsePointCloud(full.subarray(0, 40), 'x.e57')).toThrow(/shorter than the 48 byte header/);
    // the XML is at the end of libE57Format files: cutting anything loses it
    expect(() => parsePointCloud(full.subarray(0, full.length - 1500), 'x.e57')).toThrow(/truncated \(the XML section is missing\)/);
    // only the padding after the XML lost: read, with a warning
    const d = parsePointCloud(full.subarray(0, full.length - 600), 'x.e57');
    expect(d.count).toBe(10425);
    expect(d.warnings.join(' ')).toMatch(/file is truncated: 162,?216 of 162,?816 bytes present/);
  });

  it('never hangs or throws anything but a PointCloudError on random damage', () => {
    const sources = Object.keys(EXPECTED).map(load);
    let seed = 12345;
    const rnd = (): number => ((seed = (seed * 1103515245 + 12345) >>> 0) / 2 ** 32);
    const t0 = performance.now();
    let read = 0;
    let errors = 0;
    for (let iter = 0; iter < 400; iter++) {
      const src = sources[iter % sources.length]!;
      let f = src.slice();
      const kind = iter % 4;
      if (kind === 0) f = f.subarray(0, Math.floor(rnd() * f.length));
      else {
        const n = kind === 1 ? 1 : 1 + Math.floor(rnd() * 40);
        for (let k = 0; k < n; k++) f[Math.floor(rnd() * f.length)] = Math.floor(rnd() * 256);
        if (kind === 3) f[Math.floor(rnd() * 48)] = Math.floor(rnd() * 256); // the header too
      }
      try {
        const d = parsePointCloud(f, 'fuzz.e57');
        expect(d.count).toBeGreaterThan(0);
        read++;
      } catch (e) {
        if (!(e instanceof PointCloudError)) throw new Error(`iteration ${iter}: ${(e as Error).stack}`);
        errors++;
      }
    }
    expect(read).toBeGreaterThan(0);
    expect(errors).toBeGreaterThan(0);
    expect(performance.now() - t0).toBeLessThan(20_000);
  });

  it('clear errors for non-point content', () => {
    const file = load('e57-cart-float.e57');
    const xml = readE57Xml(file);
    const { streams } = streamsOf(file);
    const noData = xml.replace(/<data3D type="Vector" allowHeterogeneousChildren="1">[\s\S]*<\/data3D>/, '<data3D type="Vector" allowHeterogeneousChildren="1"/>');
    expect(() => parsePointCloud(writeE57(noData, streams, { chunk: () => 1000 }), 'img.e57')).toThrow(/no 3D scans/);
    const badVersion = file.slice();
    badVersion[8] = 2;
    expect(() => parsePointCloud(badVersion, 'v.e57')).toThrow(/unsupported version 2\.0/);
    const codec = xml.replace(/<codecs type="Vector" allowHeterogeneousChildren="1">\s*<\/codecs>/, '<codecs type="Vector" allowHeterogeneousChildren="1"><vectorChild type="Structure"><zipCodec type="Structure"/></vectorChild></codecs>');
    expect(codec).not.toBe(xml);
    expect(() => parsePointCloud(writeE57(codec, streams, { chunk: () => 1000 }), 'z.e57')).toThrow(/codec "zipCodec"/);
  });
});

describe('E57 sample scan', () => {
  it('public/samples/building-scan.e57 holds the same points as building-scan.las', () => {
    const root = resolve(dirname(fileURLToPath(import.meta.url)), '../public/samples');
    const e = parsePointCloud(new Uint8Array(readFileSync(resolve(root, 'building-scan.e57'))), 'building-scan.e57');
    const l = parsePointCloud(new Uint8Array(readFileSync(resolve(root, 'building-scan.las'))), 'building-scan.las');
    expect(e.count).toBe(l.count);
    expect(e.warnings).toEqual([]);
    for (let k = 0; k < 3; k++) expect(Math.abs(e.origin[k]! - l.origin[k]!)).toBeLessThan(1e-9);
    let maxd = 0;
    for (let i = 0; i < e.positions.length; i++) maxd = Math.max(maxd, Math.abs(e.positions[i]! - l.positions[i]!));
    expect(maxd).toBeLessThan(1e-5);
    let colourDiff = 0;
    for (let i = 0; i < e.colors!.length; i++) if (e.colors![i] !== l.colors![i]) colourDiff++;
    expect(colourDiff).toBe(0);
    for (let i = 0; i < e.count; i += 997) expect(e.intensity![i]! * 65535).toBeCloseTo(l.intensity![i]!, 2);
  });
});
