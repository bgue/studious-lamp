// PLY: ascii, binary_little_endian and binary_big_endian. Vertex properties x y z, optional red green blue
// (also r g b, diffuse_*), intensity (also scalar_intensity) and classification (also class, label, scalar_classification).
// Faces and other elements are skipped. Positions are read as double and stored relative to the first point.

import type { PointCloudData, ProgressFn } from '../types';
import { PointCloudError } from '../types';
import { PointBuilder } from './builder';
import { scanRows } from './rows';

interface Prop {
  name: string;
  type: string; // scalar type, or the item type of a list
  list: string | null; // count type when a list
}
interface Element {
  name: string;
  count: number;
  props: Prop[];
}

const SIZE: Record<string, number> = {
  char: 1, int8: 1, uchar: 1, uint8: 1, short: 2, int16: 2, ushort: 2, uint16: 2, int: 4, int32: 4, uint: 4, uint32: 4,
  float: 4, float32: 4, double: 8, float64: 8,
};

function readScalar(dv: DataView, o: number, type: string, le: boolean): number {
  switch (type) {
    case 'char': case 'int8': return dv.getInt8(o);
    case 'uchar': case 'uint8': return dv.getUint8(o);
    case 'short': case 'int16': return dv.getInt16(o, le);
    case 'ushort': case 'uint16': return dv.getUint16(o, le);
    case 'int': case 'int32': return dv.getInt32(o, le);
    case 'uint': case 'uint32': return dv.getUint32(o, le);
    case 'float': case 'float32': return dv.getFloat32(o, le);
    case 'double': case 'float64': return dv.getFloat64(o, le);
    default: throw new PointCloudError(`PLY: unknown property type "${type}"`);
  }
}

const norm = (s: string): string => s.toLowerCase().replace(/^(scalar_|diffuse_)/, '');
const R = new Set(['red', 'r']);
const G = new Set(['green', 'g']);
const B = new Set(['blue', 'b']);
const INT = new Set(['intensity', 'i', 'reflectance']);
const CLS = new Set(['classification', 'class', 'label']);

export function readPly(bytes: Uint8Array, name: string, onProgress?: ProgressFn): PointCloudData {
  // header
  let headEnd = -1;
  const lim = Math.min(bytes.length, 1 << 20);
  for (let i = 0; i < lim - 9; i++) {
    if (bytes[i] === 101 && bytes[i + 1] === 110 && bytes[i + 2] === 100 && bytes[i + 3] === 95 && bytes[i + 4] === 104 && bytes[i + 5] === 101 && bytes[i + 6] === 97 && bytes[i + 7] === 100 && bytes[i + 8] === 101 && bytes[i + 9] === 114) {
      let j = i + 10;
      while (j < bytes.length && bytes[j] !== 10) j++;
      headEnd = j + 1;
      break;
    }
  }
  if (headEnd < 0) throw new PointCloudError('PLY: end_header not found');
  const header = new TextDecoder().decode(bytes.subarray(0, headEnd)).split(/\r?\n/);
  if (header[0]?.trim() !== 'ply') throw new PointCloudError('PLY: missing "ply" magic');
  let format = '';
  const elements: Element[] = [];
  for (const raw of header.slice(1)) {
    const t = raw.trim().split(/\s+/);
    if (t[0] === 'format') format = t[1] ?? '';
    else if (t[0] === 'element') elements.push({ name: t[1] ?? '', count: Number(t[2]), props: [] });
    else if (t[0] === 'property') {
      const el = elements[elements.length - 1];
      if (!el) throw new PointCloudError('PLY: property before element');
      if (t[1] === 'list') el.props.push({ name: t[4] ?? '', type: t[3] ?? '', list: t[2] ?? '' });
      else el.props.push({ name: t[2] ?? '', type: t[1] ?? '', list: null });
    }
  }
  if (format !== 'ascii' && format !== 'binary_little_endian' && format !== 'binary_big_endian') throw new PointCloudError(`PLY: unsupported format "${format}"`);
  const vertex = elements.find((e) => e.name === 'vertex');
  if (!vertex) throw new PointCloudError('PLY: no vertex element');
  const pi = (set: Set<string> | string): number => vertex.props.findIndex((p) => !p.list && (typeof set === 'string' ? p.name === set : set.has(norm(p.name))));
  const ix = pi('x'), iy = pi('y'), iz = pi('z');
  if (ix < 0 || iy < 0 || iz < 0) throw new PointCloudError('PLY: vertex has no x, y, z');
  const ir = pi(R), ig = pi(G), ib = pi(B);
  const ii = pi(INT), ic = pi(CLS);
  const hasColor = ir >= 0 && ig >= 0 && ib >= 0;
  const builder = new PointBuilder({ color: hasColor, intensity: ii >= 0, classification: ic >= 0 }, vertex.count);

  const put = (get: (k: number) => number): void => {
    const i = builder.add(get(ix), get(iy), get(iz));
    if (i < 0) return;
    if (hasColor) builder.setColor(i, get(ir), get(ig), get(ib));
    if (ii >= 0) builder.setIntensity(i, get(ii));
    if (ic >= 0) builder.setClass(i, get(ic));
  };

  if (format === 'ascii') {
    // elements before the vertex element would need skipping; ascii files list vertices first in practice
    let rowsToSkip = 0;
    for (const e of elements) {
      if (e === vertex) break;
      rowsToSkip += e.count;
    }
    let seen = 0;
    const need = Math.max(ix, iy, iz, ir, ig, ib, ii, ic) + 1;
    scanRows(bytes, headEnd, bytes.length, {
      onRow: (v, n) => {
        if (seen++ < rowsToSkip) return true;
        if (n < need) throw new PointCloudError(`PLY: vertex row ${seen - rowsToSkip} has ${n} values, expected at least ${need}`);
        put((k) => v[k]!);
        return seen - rowsToSkip < vertex.count; // false after the last vertex: faces are not read
      },
      onProgress: (pos) => onProgress?.(pos / bytes.length, 'parse'),
    });
  } else {
    const le = format === 'binary_little_endian';
    const dv = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    let o = headEnd;
    const skip = (e: Element): void => {
      if (e.props.every((p) => !p.list)) {
        let rec = 0;
        for (const p of e.props) rec += SIZE[p.type] ?? 0;
        o += rec * e.count;
        return;
      }
      for (let r = 0; r < e.count; r++) {
        for (const p of e.props) {
          if (p.list) {
            const n = readScalar(dv, o, p.list, le);
            o += SIZE[p.list]! + n * SIZE[p.type]!;
          } else o += SIZE[p.type]!;
        }
      }
    };
    for (const e of elements) {
      if (e === vertex) break;
      skip(e);
    }
    if (vertex.props.some((p) => p.list)) throw new PointCloudError('PLY: list properties on vertices are not supported');
    const offs: number[] = [];
    let rec = 0;
    for (const p of vertex.props) {
      if (!(p.type in SIZE)) throw new PointCloudError(`PLY: unknown property type "${p.type}"`);
      offs.push(rec);
      rec += SIZE[p.type]!;
    }
    const avail = Math.floor((bytes.length - o) / rec);
    const n = Math.min(vertex.count, avail);
    if (n < vertex.count) builder.warnings.push(`file is truncated: ${n} of ${vertex.count} vertices present`);
    const types = vertex.props.map((p) => p.type);
    let base = o;
    for (let r = 0; r < n; r++, base += rec) {
      put((k) => readScalar(dv, base + offs[k]!, types[k]!, le));
      if ((r & 0xffff) === 0xffff) onProgress?.(r / n, 'parse');
    }
  }
  if (builder.count < vertex.count && format === 'ascii') builder.warnings.push(`header says ${vertex.count} vertices, ${builder.count} read`);
  return builder.finish(name, 'ply');
}
