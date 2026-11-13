// The appearance stream (/AP /N) of an annotation: the drawing a viewer shows when it does not synthesise one itself. Pure: it
// returns the content stream text, the bounding box and what the stream needs (a graphics state with an opacity, the font).
// The stream draws in page user space and its /BBox equals the annotation /Rect, so the form matrix is the identity.
// Tested in tests/sheets-annot.test.ts.

import { arrowHead } from '../markup/geometry';
import { FILL_ALPHA } from './annot';
import type { AnnotSpec, Rect4, Rgb } from './annot';
import type { Weight } from '../markup/model';
import { cloudPolyline } from './annot';
import type { Sheet } from './model';
import { sheetUnit } from './model';

export interface Appearance {
  bbox: Rect4;
  content: string;
  /** Needs /Resources /Font /Helv (Helvetica). */
  font: boolean;
  /** ExtGState entries by name: stroke alpha (CA), fill alpha (ca), blend mode. */
  gs: Record<string, { CA: number; ca: number; BM?: string }>;
}

const n = (v: number): string => {
  const s = (Math.round(v * 1000) / 1000).toString();
  return s === '-0' ? '0' : s;
};
const col = (c: Rgb): string => `${n(c[0])} ${n(c[1])} ${n(c[2])}`;

/** A PDF text string as hex, in WinAnsi: characters outside Latin-1 become "?". */
export function hexText(s: string): string {
  let out = '<';
  for (const ch of s) {
    const c = ch.codePointAt(0)!;
    out += (c > 255 || c < 32 ? 63 : c).toString(16).padStart(2, '0');
  }
  return `${out}>`;
}

function pathOf(flat: ArrayLike<number>, close: boolean): string {
  let s = '';
  for (let i = 0; i + 1 < flat.length; i += 2) s += `${n(flat[i]!)} ${n(flat[i + 1]!)} ${i === 0 ? 'm' : 'l'}\n`;
  return close ? `${s}h\n` : s;
}

function ellipsePath(r: Rect4): string {
  const k = 0.5522847498;
  const cx = (r[0] + r[2]) / 2;
  const cy = (r[1] + r[3]) / 2;
  const rx = (r[2] - r[0]) / 2;
  const ry = (r[3] - r[1]) / 2;
  const P = (x: number, y: number): string => `${n(x)} ${n(y)}`;
  return `${P(cx + rx, cy)} m\n` +
    `${P(cx + rx, cy + ry * k)} ${P(cx + rx * k, cy + ry)} ${P(cx, cy + ry)} c\n` +
    `${P(cx - rx * k, cy + ry)} ${P(cx - rx, cy + ry * k)} ${P(cx - rx, cy)} c\n` +
    `${P(cx - rx, cy - ry * k)} ${P(cx - rx * k, cy - ry)} ${P(cx, cy - ry)} c\n` +
    `${P(cx + rx * k, cy - ry)} ${P(cx + rx, cy - ry * k)} ${P(cx + rx, cy)} c\nh\n`;
}

/** The appearance of an annotation spec on a sheet; null for a subtype we draw no appearance for. */
export function buildAppearance(spec: AnnotSpec, sheet: Pick<Sheet, 'widthPt' | 'heightPt'>): Appearance | null {
  const unit = sheetUnit(sheet);
  const weight: Weight = spec.xray?.weight ?? 2;
  const gs: Appearance['gs'] = {};
  let out = 'q\n';
  const fillAlpha = spec.opacity ?? (spec.interior && spec.subtype !== 'Line' ? FILL_ALPHA : 1);
  const strokeAlpha = spec.opacity ?? 1;
  const highlight = spec.xray?.kind === 'highlightBox' || spec.xray?.kind === 'highlight';
  if (strokeAlpha < 1 || fillAlpha < 1 || highlight) {
    gs['GS0'] = { CA: strokeAlpha, ca: fillAlpha, ...(highlight ? { BM: 'Multiply' } : {}) };
    out += '/GS0 gs\n';
  }
  out += `${col(spec.color)} RG\n${n(spec.width)} w\n1 J\n1 j\n`;
  if (spec.interior) out += `${col(spec.interior)} rg\n`;
  const paint = (closed: boolean): string => {
    const fill = !!spec.interior && spec.subtype !== 'Line';
    if (spec.width <= 0.01) return fill ? 'f\n' : 'n\n';
    return closed ? (fill ? 'B\n' : 'S\n') : 'S\n';
  };
  let font = false;
  switch (spec.subtype) {
    case 'Square': {
      const rd = spec.rd ?? [0, 0, 0, 0];
      const r: Rect4 = [spec.rect[0] + rd[0], spec.rect[1] + rd[1], spec.rect[2] - rd[2], spec.rect[3] - rd[3]];
      out += `${n(r[0])} ${n(r[1])} ${n(r[2] - r[0])} ${n(r[3] - r[1])} re\n${paint(true)}`;
      break;
    }
    case 'Circle': {
      const rd = spec.rd ?? [0, 0, 0, 0];
      out += ellipsePath([spec.rect[0] + rd[0], spec.rect[1] + rd[1], spec.rect[2] - rd[2], spec.rect[3] - rd[3]]) + paint(true);
      break;
    }
    case 'Polygon': {
      const v = spec.vertices ?? [];
      const poly = spec.cloud ? cloudPolyline(v, weight, sheet) : v;
      out += pathOf(poly, true) + paint(true);
      break;
    }
    case 'PolyLine':
      out += pathOf(spec.vertices ?? [], false) + paint(false);
      break;
    case 'Line': {
      const l = spec.line;
      if (!l) return null;
      out += pathOf(l, false) + 'S\n';
      if ((spec.lineEnding?.[1] ?? 'None') !== 'None') {
        const head = arrowHead(l[0], l[1], l[2], l[3], (10 + weight * 3) * unit, (4 + weight * 1.6) * unit);
        if (head) {
          if (spec.interior) out += `${col(spec.interior)} rg\n`;
          out += `${pathOf(head, true)}${spec.interior ? 'f' : 'S'}\n`;
        }
      }
      break;
    }
    case 'Ink':
      for (const s of spec.inkList ?? []) out += pathOf(s, false) + 'S\n';
      break;
    case 'FreeText': {
      const rd = spec.rd ?? [0, 0, 0, 0];
      const r: Rect4 = [spec.rect[0] + rd[0], spec.rect[1] + rd[1], spec.rect[2] - rd[2], spec.rect[3] - rd[3]];
      if (spec.callout && spec.callout.length >= 4) {
        const c = spec.callout;
        out += pathOf(c, false) + 'S\n';
        const head = arrowHead(c[c.length - 2]!, c[c.length - 1]!, c[0]!, c[1]!, 8 * unit, 3.5 * unit);
        if (head) out += `${pathOf(head, true)}${col(spec.color)} rg\nf\n`;
      }
      out += `1 1 1 rg\n${n(r[0])} ${n(r[1])} ${n(r[2] - r[0])} ${n(r[3] - r[1])} re\nB\n`;
      const size = spec.fontSize ?? 12;
      const pad = size / 2;
      const lines = spec.textLines ?? [spec.contents];
      out += `0.067 0.067 0.067 rg\nBT\n/Helv ${n(size)} Tf\n`;
      lines.forEach((line, i) => {
        const y = r[3] - pad - size * 0.8 - i * size * 1.3;
        out += `1 0 0 1 ${n(r[0] + pad)} ${n(y)} Tm\n${hexText(line)} Tj\n`;
      });
      out += 'ET\n';
      font = true;
      break;
    }
    default:
      return null;
  }
  out += 'Q\n';
  return { bbox: spec.rect, content: out, font, gs };
}
