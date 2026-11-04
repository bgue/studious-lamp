// PCD (Point Cloud Library): ascii, binary and binary_compressed (LZF). Fields x y z, rgb / rgba (packed float or uint32),
// intensity. Points with NaN coordinates (organised clouds) are skipped.

import type { PointCloudData, ProgressFn } from '../types';
import { PointCloudError } from '../types';
import { PointBuilder } from './builder';
import { scanRows } from './rows';

/** LZF decompression as used by PCL's binary_compressed. */
export function lzfDecompress(src: Uint8Array, outLen: number): Uint8Array {
  const out = new Uint8Array(outLen);
  let i = 0;
  let o = 0;
  while (i < src.length) {
    const ctrl = src[i++]!;
    if (ctrl < 32) {
      const n = ctrl + 1;
      if (o + n > outLen || i + n > src.length) throw new PointCloudError('PCD: corrupt LZF data');
      out.set(src.subarray(i, i + n), o);
      i += n;
      o += n;
    } else {
      let len = ctrl >> 5;
      if (len === 7) len += src[i++]!;
      const ref = o - ((ctrl & 0x1f) << 8) - 1 - src[i++]!;
      len += 2;
      if (ref < 0 || o + len > outLen) throw new PointCloudError('PCD: corrupt LZF data');
      for (let k = 0; k < len; k++) out[o++] = out[ref + k]!;
    }
  }
  if (o !== outLen) throw new PointCloudError('PCD: LZF output size mismatch');
  return out;
}

interface Field {
  name: string;
  size: number;
  type: string;
  count: number;
}

function readValue(dv: DataView, o: number, type: string, size: number): number {
  if (type === 'F') return size === 4 ? dv.getFloat32(o, true) : dv.getFloat64(o, true);
  if (type === 'U') return size === 1 ? dv.getUint8(o) : size === 2 ? dv.getUint16(o, true) : dv.getUint32(o, true);
  return size === 1 ? dv.getInt8(o) : size === 2 ? dv.getInt16(o, true) : dv.getInt32(o, true);
}

const f32 = new Float32Array(1);
const u32 = new Uint32Array(f32.buffer);

export function readPcd(bytes: Uint8Array, name: string, onProgress?: ProgressFn): PointCloudData {
  let pos = 0;
  const hdr: Record<string, string[]> = {};
  let dataKind = '';
  while (pos < bytes.length) {
    let e = pos;
    while (e < bytes.length && bytes[e] !== 10) e++;
    const line = new TextDecoder().decode(bytes.subarray(pos, e)).replace(/\r$/, '').trim();
    pos = e + 1;
    if (!line || line.startsWith('#')) continue;
    const t = line.split(/\s+/);
    const key = (t[0] ?? '').toUpperCase();
    hdr[key] = t.slice(1);
    if (key === 'DATA') {
      dataKind = (t[1] ?? '').toLowerCase();
      break;
    }
  }
  const names = hdr['FIELDS'] ?? hdr['COLUMNS'];
  if (!names || !dataKind) throw new PointCloudError('PCD: header is incomplete (FIELDS or DATA missing)');
  const sizes = (hdr['SIZE'] ?? []).map(Number);
  const types = hdr['TYPE'] ?? [];
  const counts = (hdr['COUNT'] ?? names.map(() => '1')).map(Number);
  const fields: Field[] = names.map((n, i) => ({ name: n, size: sizes[i] ?? 4, type: (types[i] ?? 'F').toUpperCase(), count: counts[i] ?? 1 }));
  const total = Number(hdr['POINTS']?.[0] ?? Number(hdr['WIDTH']?.[0] ?? 0) * Number(hdr['HEIGHT']?.[0] ?? 1));
  const fi = (n: string): number => fields.findIndex((f) => f.name === n);
  const ix = fi('x'), iy = fi('y'), iz = fi('z');
  if (ix < 0 || iy < 0 || iz < 0) throw new PointCloudError('PCD: no x, y, z fields');
  const irgb = fields.findIndex((f) => f.name === 'rgb' || f.name === 'rgba');
  const iint = fi('intensity');
  const icls = fields.findIndex((f) => f.name === 'label' || f.name === 'classification');
  const builder = new PointBuilder({ color: irgb >= 0, intensity: iint >= 0, classification: icls >= 0 }, total || 1024);

  const put = (get: (k: number) => number): void => {
    const i = builder.add(get(ix), get(iy), get(iz));
    if (i < 0) return;
    if (irgb >= 0) {
      const f = fields[irgb]!;
      const raw = get(irgb);
      const bits = f.type === 'F' ? ((f32[0] = raw), u32[0]!) : raw >>> 0;
      builder.setColor(i, (bits >> 16) & 255, (bits >> 8) & 255, bits & 255);
    }
    if (iint >= 0) builder.setIntensity(i, get(iint));
    if (icls >= 0) builder.setClass(i, get(icls));
  };

  if (dataKind === 'ascii') {
    const need = fields.length;
    scanRows(bytes, pos, bytes.length, {
      onRow: (v, n) => {
        if (n < need) throw new PointCloudError(`PCD: row has ${n} values, expected ${need}`);
        // a field with COUNT > 1 spans several columns; only the first column of x y z / rgb matters here
        if (fields.every((f) => f.count === 1)) put((k) => v[k]!);
        else {
          let col = 0;
          const first = fields.map((f) => { const c = col; col += f.count; return c; });
          put((k) => v[first[k]!]!);
        }
      },
      onProgress: (p) => onProgress?.(p / bytes.length, 'parse'),
    });
  } else if (dataKind === 'binary' || dataKind === 'binary_compressed') {
    let data: Uint8Array;
    const rec = fields.reduce((s, f) => s + f.size * f.count, 0);
    let n: number;
    let columnar = false;
    if (dataKind === 'binary_compressed') {
      const dv0 = new DataView(bytes.buffer, bytes.byteOffset + pos, 8);
      const cSize = dv0.getUint32(0, true);
      const uSize = dv0.getUint32(4, true);
      data = lzfDecompress(bytes.subarray(pos + 8, pos + 8 + cSize), uSize);
      n = total || Math.floor(uSize / rec);
      columnar = true;
    } else {
      data = bytes.subarray(pos);
      n = Math.min(total || Infinity, Math.floor(data.length / rec));
      if (total && n < total) builder.warnings.push(`file is truncated: ${n} of ${total} points present`);
    }
    const dv = new DataView(data.buffer, data.byteOffset, data.byteLength);
    const offs: number[] = [];
    let o = 0;
    for (const f of fields) {
      offs.push(o);
      o += f.size * f.count * (columnar ? n : 1);
    }
    for (let r = 0; r < n; r++) {
      put((k) => {
        const f = fields[k]!;
        const at = columnar ? offs[k]! + r * f.size * f.count : r * rec + offs[k]!;
        return readValue(dv, at, f.type, f.size);
      });
      if ((r & 0xffff) === 0xffff) onProgress?.(r / n, 'parse');
    }
  } else throw new PointCloudError(`PCD: unsupported DATA kind "${dataKind}"`);
  return builder.finish(name, 'pcd');
}
