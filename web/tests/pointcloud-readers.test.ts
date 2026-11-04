import { describe, expect, it } from 'vitest';
import { parsePointCloud, detectFormat, isPointCloudName, LAZ_MESSAGE } from '../src/pointcloud/readers';
import { lzfDecompress } from '../src/pointcloud/readers/pcd';
import type { PointCloudData } from '../src/pointcloud/types';
import { grid, las, packRgb, pcdAscii, pcdBinary, pcdCompressed, plyAscii, plyBinary } from './pointcloud-helpers';
import type { TestPoint } from './pointcloud-helpers';

const enc = (s: string): Uint8Array => new TextEncoder().encode(s);
/** Absolute position of point i (origin + relative). */
const abs = (d: PointCloudData, i: number): [number, number, number] => [d.origin[0] + d.positions[i * 3]!, d.origin[1] + d.positions[i * 3 + 1]!, d.origin[2] + d.positions[i * 3 + 2]!];

function expectPoints(d: PointCloudData, pts: TestPoint[], tol: number, opts: { colour?: boolean; intensity?: boolean } = {}): void {
  expect(d.count).toBe(pts.length);
  pts.forEach((p, i) => {
    const a = abs(d, i);
    expect(Math.abs(a[0] - p.x)).toBeLessThanOrEqual(tol);
    expect(Math.abs(a[1] - p.y)).toBeLessThanOrEqual(tol);
    expect(Math.abs(a[2] - p.z)).toBeLessThanOrEqual(tol);
    if (opts.colour !== false) {
      expect(d.colors![i * 3]).toBe(p.r);
      expect(d.colors![i * 3 + 1]).toBe(p.g);
      expect(d.colors![i * 3 + 2]).toBe(p.b);
    }
    if (opts.intensity !== false && d.intensity) expect(d.intensity[i]).toBe(p.i);
  });
}

describe('PLY', () => {
  // 1e6 offsets: Float32 alone would lose the centimetres
  const pts = grid(40, [1_234_567.123, 7_654_321.456, 89.5]);
  it('reads ascii with colour and intensity, skipping faces', () => {
    const d = parsePointCloud(plyAscii(pts, { faces: true }), 'a.ply');
    expect(d.format).toBe('ply');
    expectPoints(d, pts, 1e-6);
    expect(d.intensityRange).toEqual([100, 139]);
  });
  it('reads binary little endian (double) with faces after the vertices', () => {
    expectPoints(parsePointCloud(plyBinary(pts, true, { faces: true }), 'a.ply'), pts, 1e-9);
  });
  it('reads binary big endian', () => {
    expectPoints(parsePointCloud(plyBinary(pts, false), 'a.ply'), pts, 1e-9);
  });
  it('keeps precision: positions are relative to a double origin, so Float32 holds millimetres', () => {
    const d = parsePointCloud(plyBinary(pts, true), 'a.ply');
    expect(d.origin[0]).toBeCloseTo(1_234_567.123, 6);
    expect(Math.max(...d.positions)).toBeLessThan(20);
    expect(d.boundsMin[0]).toBeCloseTo(1_234_567.123, 6);
  });
  it('reads float coordinates', () => {
    const small = grid(10, [3.5, 4.5, 1]);
    expectPoints(parsePointCloud(plyBinary(small, true, { floatXyz: true }), 'a.ply'), small, 1e-6);
  });
  it('maps r/g/b, scalar_intensity and class names, and works without colour', () => {
    const txt = 'ply\nformat ascii 1.0\nelement vertex 2\nproperty float x\nproperty float y\nproperty float z\nproperty float scalar_Intensity\nproperty uchar class\nend_header\n0 0 0 0.5 6\n1 2 3 0.75 2\n';
    const d = parsePointCloud(enc(txt), 'a.ply');
    expect(d.colors).toBeUndefined();
    expect(Array.from(d.intensity!)).toEqual([0.5, 0.75]);
    expect(Array.from(d.classification!)).toEqual([6, 2]);
  });
  it('reports a truncated binary file instead of failing', () => {
    const b = plyBinary(grid(20), true);
    const d = parsePointCloud(b.subarray(0, b.length - 31 * 3), 'a.ply');
    expect(d.count).toBeLessThan(20);
    expect(d.warnings.join(' ')).toMatch(/truncated/);
  });
  it('rejects bad headers', () => {
    expect(() => parsePointCloud(enc('ply\nformat ascii 1.0\nelement vertex 1\nproperty float x\n'), 'a.ply')).toThrow(/end_header/);
    expect(() => parsePointCloud(enc('ply\nformat ascii 1.0\nelement face 1\nend_header\n'), 'a.ply')).toThrow(/vertex/);
    expect(() => parsePointCloud(enc('ply\nformat ascii 1.0\nelement vertex 1\nproperty float x\nend_header\n1\n'), 'a.ply')).toThrow(/x, y, z/);
  });
});

describe('PCD', () => {
  const pts = grid(33, [10.5, -4.25, 2]);
  // rgb is a packed float and x y z are Float32 in the file: tolerance is Float32 rounding
  it('reads ascii', () => expectPoints(parsePointCloud(pcdAscii(pts), 'a.pcd'), pts, 1e-4));
  it('reads binary', () => expectPoints(parsePointCloud(pcdBinary(pts), 'a.pcd'), pts, 1e-4));
  it('reads binary_compressed (LZF, column major)', () => expectPoints(parsePointCloud(pcdCompressed(pts), 'a.pcd'), pts, 1e-4));
  it('LZF back references', () => {
    // literal "abc", then a back reference of length 4 (code 2, plus 2) at distance 3: "abcabca"
    const out = lzfDecompress(Uint8Array.from([2, 97, 98, 99, 2 << 5, 2]), 7);
    expect(new TextDecoder().decode(out)).toBe('abcabca');
  });
  it('unpacks rgb and skips NaN points', () => {
    const txt = '# .PCD v0.7\nVERSION 0.7\nFIELDS x y z rgb\nSIZE 4 4 4 4\nTYPE F F F F\nCOUNT 1 1 1 1\nWIDTH 2\nHEIGHT 1\nPOINTS 2\nDATA ascii\n' +
      `nan nan nan ${packRgb(1, 2, 3)}\n1 2 3 ${packRgb(255, 128, 0)}\n`;
    const d = parsePointCloud(enc(txt), 'a.pcd');
    expect(d.count).toBe(1);
    expect(Array.from(d.colors!)).toEqual([255, 128, 0]);
  });
  it('rejects an incomplete header', () => {
    expect(() => parsePointCloud(enc('# .PCD v0.7\nVERSION 0.7\nFIELDS x y z\n'), 'a.pcd')).toThrow(/header/);
  });
});

describe('XYZ / PTS / TXT', () => {
  it('reads x y z', () => {
    const d = parsePointCloud(enc('1 2 3\n4 5 6\n'), 'a.xyz');
    expect(d.count).toBe(2);
    expect(d.colors).toBeUndefined();
    expect(abs(d, 1)).toEqual([4, 5, 6]);
  });
  it('reads comma separated rows, CRLF, comments and exponents', () => {
    const d = parsePointCloud(enc('# comment\r\n1.5,-2e1,+3.25E-1\r\n\r\n// another\r\n 0.5 , 1 , 2 \r\n'), 'a.txt');
    expect(d.count).toBe(2);
    expect(abs(d, 0)).toEqual([1.5, -20, 0.325]);
    expect(d.warnings.join(' ')).toMatch(/non-numeric/);
  });
  it('reads x y z r g b with 0..255 colour', () => {
    const d = parsePointCloud(enc('0 0 0 255 0 128\n1 1 1 10 20 30\n'), 'a.xyz');
    expect(Array.from(d.colors!)).toEqual([255, 0, 128, 10, 20, 30]);
  });
  it('detects 0..1 colour', () => {
    const d = parsePointCloud(enc('0 0 0 1 0 0.5\n1 1 1 0 0 0\n'), 'a.xyz');
    expect(Array.from(d.colors!.subarray(0, 3))).toEqual([255, 0, 128]);
  });
  it('reads x y z i (intensity)', () => {
    const d = parsePointCloud(enc('0 0 0 7\n1 1 1 9\n'), 'a.xyz');
    expect(Array.from(d.intensity!)).toEqual([7, 9]);
  });
  it('reads x y z r g b i for xyz and x y z i r g b for pts, after the count line', () => {
    const xyz = parsePointCloud(enc('0 0 0 10 20 30 99\n'), 'a.xyz');
    expect(Array.from(xyz.colors!)).toEqual([10, 20, 30]);
    expect(xyz.intensity![0]).toBe(99);
    const pts = parsePointCloud(enc('2\n0 0 0 -500 10 20 30\n1 1 1 -400 40 50 60\n'), 'a.pts');
    expect(pts.format).toBe('pts');
    expect(pts.count).toBe(2);
    expect(Array.from(pts.intensity!)).toEqual([-500, -400]);
    expect(Array.from(pts.colors!)).toEqual([10, 20, 30, 40, 50, 60]);
    expect(pts.warnings).toEqual([]);
  });
  it('warns when the PTS count disagrees', () => {
    expect(parsePointCloud(enc('5\n0 0 0\n1 1 1\n'), 'a.pts').warnings.join(' ')).toMatch(/header says 5/);
  });
  it('fails on a file without points', () => {
    expect(() => parsePointCloud(enc('hello\nworld\n'), 'a.txt')).toThrow(/No points/);
    expect(() => parsePointCloud(new Uint8Array(0), 'a.xyz')).toThrow(/empty/);
  });
  it('parses long mantissas exactly', () => {
    const d = parsePointCloud(enc('1234567.1234567891 0 0\n'), 'a.xyz');
    expect(abs(d, 0)[0]).toBeCloseTo(1234567.1234567891, 9);
  });
});

describe('LAS', () => {
  const pts = grid(25, [500_000.123, 4_200_000.456, 12.5]);
  const q = 0.001 / 2 + 1e-9;
  it('reads format 2 with 16-bit colour scaled to 8 bit, intensity and classification', () => {
    const d = parsePointCloud(las(pts, { format: 2, offset: [500_000, 4_200_000, 0] }), 'a.las');
    expect(d.format).toBe('las');
    expectPoints(d, pts, q);
    expect(Array.from(d.classification!.subarray(0, 3))).toEqual([2, 6, 6]); // flag bits (0xe0) masked off for format 2
  });
  it('reads formats 0, 1, 3', () => {
    for (const format of [0, 1, 3]) {
      const d = parsePointCloud(las(pts, { format, offset: [500_000, 4_200_000, 0] }), 'a.las');
      expectPoints(d, pts, q, { colour: format === 3 });
      expect(d.colors !== undefined).toBe(format === 3);
    }
  });
  it('reads formats 6, 7, 8 (LAS 1.4, classification in its own byte)', () => {
    for (const format of [6, 7, 8]) {
      const d = parsePointCloud(las(pts, { format, minor: 4, offset: [500_000, 4_200_000, 0] }), 'a.las');
      expectPoints(d, pts, q, { colour: format > 6 });
      expect(Array.from(d.classification!.subarray(0, 2))).toEqual([2, 6]);
    }
  });
  it('reads LAS 1.4 with the 64-bit point count and a record longer than the format (extra bytes)', () => {
    const d = parsePointCloud(las(pts, { format: 6, minor: 4, bigCount: true, recordExtra: 6, offset: [500_000, 4_200_000, 0] }), 'a.las');
    expectPoints(d, pts, q, { colour: false });
  });
  it('applies scale and offset', () => {
    const p = [{ x: 100.5, y: 200.25, z: 3.125 }];
    const d = parsePointCloud(las(p, { format: 0, scale: 0.0125, offset: [90, 190, 0] }), 'a.las');
    expect(abs(d, 0)).toEqual([100.5, 200.25, 3.125]);
  });
  it('keeps colour that is stored as 8 bit in the 16-bit field', () => {
    const b = las([{ x: 0, y: 0, z: 0, r: 0, g: 0, b: 0 }, { x: 1, y: 1, z: 1 }], { format: 2 });
    const dv = new DataView(b.buffer, b.byteOffset);
    dv.setUint16(227 + 20, 200, true); dv.setUint16(227 + 22, 100, true); dv.setUint16(227 + 24, 50, true);
    const d = parsePointCloud(b, 'a.las');
    expect(Array.from(d.colors!.subarray(0, 3))).toEqual([200, 100, 50]);
  });
  it('reads a truncated file as far as it goes and says so', () => {
    const d = parsePointCloud(las(pts, { truncate: 5 }), 'a.las');
    expect(d.count).toBe(20);
    expect(d.warnings.join(' ')).toMatch(/truncated: 20 of 25/);
  });
  it('rejects header problems', () => {
    expect(() => parsePointCloud(las(pts, { signature: 'LASX' }), 'a.las')).toThrow(/LASF/);
    expect(() => parsePointCloud(las(pts).subarray(0, 100), 'a.las')).toThrow(/header/);
    expect(() => parsePointCloud(las(pts, { scale: 0 }), 'a.las')).toThrow(/scale/);
    expect(() => parsePointCloud(las(pts, { minor: 4 }).map((v, i) => (i === 25 ? 5 : v)), 'a.las')).toThrow(/version 1\.5/);
    const badFmt = las(pts);
    badFmt[104] = 12;
    expect(() => parsePointCloud(badFmt, 'a.las')).toThrow(/format 12/);
    const shortRec = las(pts);
    new DataView(shortRec.buffer, shortRec.byteOffset).setUint16(105, 20, true);
    expect(() => parsePointCloud(shortRec, 'a.las')).toThrow(/too short/);
    expect(() => parsePointCloud(las([]), 'a.las')).toThrow(/No points/);
  });
  it('rejects LAZ with a message suggesting PDAL or LAStools', () => {
    for (const bytes of [las(pts, { laz: true }), las(pts, { lazVlr: true })]) {
      expect(() => parsePointCloud(bytes, 'a.las')).toThrow(/PDAL/);
      expect(() => parsePointCloud(bytes, 'a.las')).toThrow(/LAStools/);
    }
    expect(() => parsePointCloud(las(pts), 'scan.laz')).toThrow(LAZ_MESSAGE);
  });
});

describe('format detection', () => {
  it('sniffs magic bytes before trusting the extension', () => {
    expect(detectFormat(las(grid(2)), 'x.txt')).toBe('las');
    expect(detectFormat(plyAscii(grid(2)), 'x.txt')).toBe('ply');
    expect(detectFormat(pcdAscii(grid(2)), 'x.txt')).toBe('pcd');
    expect(detectFormat(enc('1 2 3'), 'x.pts')).toBe('pts');
    expect(detectFormat(enc('1 2 3'), 'x.csv')).toBe('txt');
  });
  it('recognises drop extensions', () => {
    for (const n of ['a.PLY', 'a.pcd', 'a.xyz', 'a.pts', 'a.txt', 'a.las', 'a.laz']) expect(isPointCloudName(n)).toBe(true);
    for (const n of ['a.ifc', 'a.glb', 'a.bcf', 'a.json', 'las']) expect(isPointCloudName(n)).toBe(false);
  });
});
