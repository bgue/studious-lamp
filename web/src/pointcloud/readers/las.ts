// LAS 1.0 to 1.4, uncompressed. Point data record formats 0 to 10 are read (position, intensity, classification and,
// for formats 2, 3, 5, 7, 8, 10, 16-bit RGB); waveform and extra bytes are skipped using the header's record length.
// LAZ (compressed) is rejected with a message pointing at PDAL / LAStools.

import type { PointCloudData, ProgressFn } from '../types';
import { PointCloudError } from '../types';
import { PointBuilder } from './builder';

export const LAZ_MESSAGE =
  'LAZ (compressed LAS) is not supported. Convert it to an uncompressed .las first, for example with PDAL ' +
  '("pdal translate in.laz out.las") or LAStools ("las2las -i in.laz -o out.las").';

/** Byte offset of the RGB triple within a point record, per format; -1 when the format has no colour. */
const RGB_OFFSET: Record<number, number> = { 2: 20, 3: 28, 5: 28, 7: 30, 8: 30, 10: 30 };
/** Minimum record length per format. */
const MIN_LEN: Record<number, number> = { 0: 20, 1: 28, 2: 26, 3: 34, 4: 57, 5: 63, 6: 30, 7: 36, 8: 38, 9: 59, 10: 67 };

export function isLas(bytes: Uint8Array): boolean {
  return bytes.length >= 4 && bytes[0] === 0x4c && bytes[1] === 0x41 && bytes[2] === 0x53 && bytes[3] === 0x46;
}

export function readLas(bytes: Uint8Array, name: string, onProgress?: ProgressFn): PointCloudData {
  if (!isLas(bytes)) throw new PointCloudError('LAS: missing "LASF" signature');
  if (bytes.length < 227) throw new PointCloudError('LAS: file is shorter than the 227 byte header');
  const dv = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const major = dv.getUint8(24);
  const minor = dv.getUint8(25);
  if (major !== 1 || minor > 4) throw new PointCloudError(`LAS: unsupported version ${major}.${minor}`);
  const headerSize = dv.getUint16(94, true);
  const dataOffset = dv.getUint32(96, true);
  const vlrCount = dv.getUint32(100, true);
  const rawFormat = dv.getUint8(104);
  const recLen = dv.getUint16(105, true);
  // LAZ marks compression with the top bit of the format byte; also look for the "laszip encoded" VLR.
  let laz = (rawFormat & 0x80) !== 0;
  if (!laz && vlrCount > 0) {
    let o = headerSize;
    for (let k = 0; k < vlrCount && o + 54 <= bytes.length; k++) {
      const user = new TextDecoder().decode(bytes.subarray(o + 2, o + 18)).replace(/\0.*$/, '');
      const rid = dv.getUint16(o + 18, true);
      const len = dv.getUint16(o + 20, true);
      if (user === 'laszip encoded' && rid === 22204) laz = true;
      o += 54 + len;
    }
  }
  if (laz) throw new PointCloudError(LAZ_MESSAGE);
  const fmt = rawFormat & 0x3f;
  if (!(fmt in MIN_LEN)) throw new PointCloudError(`LAS: unsupported point data record format ${fmt} (supported: 0 to 10)`);
  if (recLen < MIN_LEN[fmt]!) throw new PointCloudError(`LAS: point record length ${recLen} is too short for format ${fmt} (needs ${MIN_LEN[fmt]})`);
  let count = dv.getUint32(107, true);
  if (minor >= 4 && headerSize >= 375) {
    const big = Number(dv.getBigUint64(247, true));
    if (count === 0 || big > count) count = big;
  }
  const sx = dv.getFloat64(131, true), sy = dv.getFloat64(139, true), sz = dv.getFloat64(147, true);
  const ox = dv.getFloat64(155, true), oy = dv.getFloat64(163, true), oz = dv.getFloat64(171, true);
  if (!(sx > 0 && sy > 0 && sz > 0)) throw new PointCloudError('LAS: header scale factors must be positive');
  if (dataOffset < headerSize || dataOffset > bytes.length) throw new PointCloudError('LAS: offset to point data is outside the file');
  const avail = Math.floor((bytes.length - dataOffset) / recLen);
  let n = count;
  const warnings: string[] = [];
  if (n > avail) {
    warnings.push(`file is truncated: ${avail} of ${count} points present`);
    n = avail;
  }
  if (n === 0) throw new PointCloudError(`No points found in ${name}`);

  const rgbAt = RGB_OFFSET[fmt] ?? -1;
  const clsAt = fmt >= 6 ? 16 : 15;
  const builder = new PointBuilder({ color: rgbAt >= 0, intensity: true, classification: true }, n);
  builder.warnings.push(...warnings);
  for (let i = 0, o = dataOffset; i < n; i++, o += recLen) {
    // absolute coordinates in double; the builder subtracts the first point before storing Float32
    const k = builder.add(dv.getInt32(o, true) * sx + ox, dv.getInt32(o + 4, true) * sy + oy, dv.getInt32(o + 8, true) * sz + oz);
    if (k < 0) continue;
    builder.setIntensity(k, dv.getUint16(o + 12, true));
    builder.setClass(k, fmt >= 6 ? dv.getUint8(o + clsAt) : dv.getUint8(o + clsAt) & 31);
    if (rgbAt >= 0) builder.setColor(k, dv.getUint16(o + rgbAt, true), dv.getUint16(o + rgbAt + 2, true), dv.getUint16(o + rgbAt + 4, true));
    if ((i & 0xffff) === 0xffff) onProgress?.(i / n, 'parse');
  }
  return builder.finish(name, 'las');
}
