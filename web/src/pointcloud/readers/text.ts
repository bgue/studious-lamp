// XYZ / PTS / TXT: one point per row, whitespace or comma separated.
//   x y z                      3 columns
//   x y z i                    4: intensity
//   x y z r g b                6: colour
//   x y z r g b i              7: colour and intensity (XYZ, TXT)
//   x y z i r g b              7: intensity then colour (PTS, as Leica / Cyclone write it)
// PTS files start with a line holding the point count; any non-numeric line (header, comment) is skipped.
// Colour scale is detected (0..1, 0..255, 0..65535).

import type { PointCloudData, ProgressFn } from '../types';
import { PointCloudError } from '../types';
import { PointBuilder } from './builder';
import { scanRows } from './rows';

export function readText(bytes: Uint8Array, name: string, format: 'xyz' | 'pts' | 'txt', onProgress?: ProgressFn): PointCloudData {
  let cols = -1;
  let builder: PointBuilder | null = null;
  let skippedShort = 0;
  let skippedText = 0;
  let countLine: number | null = null;
  let firstRow = true;
  let colorFirst = true; // true: r g b before intensity
  const guess = Math.max(1024, Math.min(5_000_000, Math.round(bytes.length / 28)));

  const make = (n: number): PointBuilder => {
    colorFirst = !(format === 'pts' && n === 7);
    return new PointBuilder({ color: n === 6 || n === 7, intensity: n === 4 || n === 7 }, guess);
  };

  scanRows(bytes, 0, bytes.length, {
    onRow: (v, n) => {
      if (firstRow) {
        firstRow = false;
        // a lone integer on the first row is a PTS point count
        if (n === 1) {
          countLine = v[0]!;
          return;
        }
      }
      if (n < 3) {
        skippedShort++;
        return;
      }
      if (cols < 0) {
        cols = n >= 7 ? 7 : n >= 6 ? 6 : n >= 4 ? (n === 5 ? 4 : n) : 3;
        builder = make(cols);
      }
      if (n < cols) {
        skippedShort++;
        return;
      }
      const i = builder!.add(v[0]!, v[1]!, v[2]!);
      if (i < 0) return;
      if (cols === 4) builder!.setIntensity(i, v[3]!);
      else if (cols === 6) builder!.setColor(i, v[3]!, v[4]!, v[5]!);
      else if (cols === 7) {
        if (colorFirst) {
          builder!.setColor(i, v[3]!, v[4]!, v[5]!);
          builder!.setIntensity(i, v[6]!);
        } else {
          builder!.setIntensity(i, v[3]!);
          builder!.setColor(i, v[4]!, v[5]!, v[6]!);
        }
      }
    },
    onOther: () => {
      skippedText++;
    },
    onProgress: (pos) => onProgress?.(pos / bytes.length, 'parse'),
  });
  if (!builder) throw new PointCloudError(`No points found in ${name}: expected rows of "x y z [r g b] [intensity]"`);
  const b = builder as PointBuilder;
  if (skippedText) b.warnings.push(`${skippedText} non-numeric line(s) skipped`);
  if (skippedShort) b.warnings.push(`${skippedShort} row(s) with too few columns skipped`);
  const cl = countLine as number | null;
  if (cl !== null && cl !== b.count) b.warnings.push(`header says ${cl} points, ${b.count} read`);
  return b.finish(name, format);
}
