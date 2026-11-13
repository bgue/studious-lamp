// The mapping between sheet sketch shapes (src/markup Markup, points in PDF user space) and PDF annotations, both ways. Pure:
// it produces and reads a plain AnnotSpec; src/sheets/pdfWrite.ts and pdfRead.ts move specs in and out of PDF files, and
// appearance.ts draws the appearance stream of a spec. Tested in tests/sheets-annot.test.ts.
//
//   cloud     /Polygon with /BE <</S /C /I 1>> and /IT /PolygonCloud     rectangle  /Square         ellipse   /Circle
//   line      /Line, /LE [/None /None]                                   arrow      /Line, /LE [/None /ClosedArrow]
//   polyline  /PolyLine                                                  polygon    /Polygon
//   pen       /Ink                                                       marker     /Ink, wide, /CA 0.5
//   text      /FreeText                                                  callout    /FreeText, /IT /FreeTextCallout, /CL
//   highlight box   /Square, filled, /CA 0.4
//
// Our own annotations carry a few private keys (/XrayKind, /XrayPts ...) so that a re-opened file gives back exactly the shape
// that was drawn. Without them (another tool edited the file, or the annotation is foreign) the shape is rebuilt from the
// standard keys alone: that is the same mapping read backwards.

import { boxSize } from '../bcf/annotate';
import { arrowHead, bounds, cloudOutline, rectCorners } from '../markup/geometry';
import { COLOURS, COLOUR_KEYS, newMarkup, strokePx } from '../markup/model';
import type { ColourKey, Markup, MarkupKind, Weight } from '../markup/model';
import { anchorGeometry, offsetFor, textLines } from './layout';
import { displayToUser, sheetUnit, userToDisplay } from './model';
import type { Sheet } from './model';

export const NM_PREFIX = 'xray-';
export const LAYER_NAME = 'X-ray markups';
export const DEFAULT_AUTHOR = 'X-ray';

export type Rgb = [number, number, number];
export type Rect4 = [number, number, number, number];
export type AnnotSubtype = 'Square' | 'Circle' | 'Line' | 'PolyLine' | 'Polygon' | 'Ink' | 'FreeText' | 'Highlight' | 'Text' | 'StrikeOut';

/** What the viewer needs to rebuild the exact markup (the private keys of our annotations). */
export interface XrayMeta {
  kind: MarkupKind;
  weight: Weight;
  colour: ColourKey;
  hex?: string;
  fill: boolean;
  number: number;
  /** The sketch the markup belongs to, and its title. */
  set: string;
  title: string;
  /** The shape points, flat user space (what the markup stores). */
  points?: number[];
  /** Text and callout: the anchor (user space) and the box offset (fractions of the page height). */
  anchor?: [number, number];
  offset?: [number, number];
}

export interface AnnotSpec {
  subtype: AnnotSubtype;
  /** /Rect, user space. */
  rect: Rect4;
  /** /RD: the border sits inside Rect by these (left, bottom, right, top). */
  rd?: Rect4;
  /** /C stroke colour (FreeText: the box colour). */
  color: Rgb;
  /** /IC interior colour. */
  interior?: Rgb;
  /** /BS /W, points. */
  width: number;
  /** /CA. */
  opacity?: number;
  /** /Contents. */
  contents: string;
  /** /T. */
  author: string;
  /** /NM. */
  name: string;
  /** /M, ISO time. */
  modified: string;
  vertices?: number[];
  /** /L of a Line. */
  line?: [number, number, number, number];
  /** /LE of a Line. */
  lineEnding?: [string, string];
  /** /InkList. */
  inkList?: number[][];
  /** /BE <</S /C /I 1>> and /IT /PolygonCloud. */
  cloud?: boolean;
  /** /IT. */
  intent?: string;
  /** /CL of a callout: the target first (the arrow head), then the box edge. */
  callout?: number[];
  /** /QuadPoints of a Highlight or StrikeOut (foreign annotations only). */
  quads?: number[];
  /** FreeText: the lines of text and their size in points. */
  textLines?: string[];
  fontSize?: number;
  /** Only ours. */
  xray?: XrayMeta;
}

// ---------------------------------------------------------------- small helpers

export function hexToRgb(hex: string): Rgb {
  const n = parseInt(hex.slice(1), 16);
  return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255];
}
export function rgbToHex(c: readonly [number, number, number]): string {
  const h = (v: number): string => Math.round(Math.min(1, Math.max(0, v)) * 255).toString(16).padStart(2, '0');
  return `#${h(c[0])}${h(c[1])}${h(c[2])}`;
}
const dist2 = (a: Rgb, b: Rgb): number => (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2;

/** The palette key a colour is (within a rounding step), or a custom `#rrggbb`. */
export function colourOf(c: Rgb): { colour: ColourKey; hex?: string } {
  let best: ColourKey = 'red';
  let bd = Infinity;
  for (const k of COLOUR_KEYS) {
    const d = dist2(c, hexToRgb(COLOURS[k]));
    if (d < bd) { bd = d; best = k; }
  }
  return bd < 3 * (1.5 / 255) ** 2 ? { colour: best } : { colour: best, hex: rgbToHex(c) };
}

const rnd = (v: number): number => Math.round(v * 1000) / 1000;

export function makeNm(setId: string, markupId: string): string {
  return `${NM_PREFIX}${setId}.${markupId}`;
}
export function parseNm(nm: string): { set: string; id: string } | null {
  const m = /^xray-([A-Za-z0-9_-]+)\.([A-Za-z0-9_-]+)$/.exec(nm);
  return m ? { set: m[1]!, id: m[2]! } : null;
}
export const isOwnNm = (nm: string | undefined | null): boolean => !!nm && nm.startsWith(NM_PREFIX);

/** The author written to /T: the name the user typed, else "X-ray". Never a stray reviewer name. */
export function authorFor(name: string | undefined): string {
  const t = (name ?? '').trim();
  return t && t.toLowerCase() !== 'unknown' ? t : DEFAULT_AUTHOR;
}

/** Stroke width in points of a markup on a sheet. */
export function widthPt(kind: MarkupKind, weight: Weight, sheet: Pick<Sheet, 'widthPt' | 'heightPt'>): number {
  return rnd(strokePx(kind, weight) * sheetUnit(sheet));
}
/** The weight whose stroke width is nearest to a width in points. */
export function weightFor(kind: MarkupKind, width: number, sheet: Pick<Sheet, 'widthPt' | 'heightPt'>): Weight {
  let best: Weight = 2;
  let bd = Infinity;
  for (const w of [1, 2, 3, 4] as Weight[]) {
    const d = Math.abs(widthPt(kind, w, sheet) - width);
    if (d < bd) { bd = d; best = w; }
  }
  return best;
}

export const HIGHLIGHT_ALPHA = 0.4;
export const MARKER_ALPHA = 0.5;
export const FILL_ALPHA = 0.16;

/** Wanted scallop length of a cloud, points. */
export function cloudArc(weight: Weight, sheet: Pick<Sheet, 'widthPt' | 'heightPt'>): number {
  return (11 + weight * 3) * sheetUnit(sheet);
}

function norm(r: ArrayLike<number>): Rect4 {
  return [Math.min(r[0]!, r[2]!), Math.min(r[1]!, r[3]!), Math.max(r[0]!, r[2]!), Math.max(r[1]!, r[3]!)];
}
function grow(r: Rect4, d: number): Rect4 {
  return [r[0] - d, r[1] - d, r[2] + d, r[3] + d];
}
function boundsRect(flat: ArrayLike<number>): Rect4 {
  const b = bounds(flat);
  return [b.x0, b.y0, b.x1, b.y1];
}

/** The scalloped outline of a cloud (user space points, flat): what a viewer draws from the /Polygon vertices. */
export function cloudPolyline(vertices: ArrayLike<number>, weight: Weight, sheet: Pick<Sheet, 'widthPt' | 'heightPt'>): number[] {
  return cloudOutline(vertices, { arc: cloudArc(weight, sheet) });
}

// ---------------------------------------------------------------- markup -> annotation

/** The annotation of a sheet markup, or null for a kind that has none. */
export function markupToSpec(m: Markup, sheet: Pick<Sheet, 'widthPt' | 'heightPt' | 'rotation' | 'box'>, o: { set: string; title: string; author?: string; date?: string }): AnnotSpec | null {
  const hex = m.hex ?? COLOURS[m.colour];
  const color = hexToRgb(hex);
  const w = widthPt(m.kind, m.weight, sheet);
  const meta: XrayMeta = { kind: m.kind, weight: m.weight, colour: m.colour, fill: m.fill, number: m.number, set: o.set, title: o.title };
  if (m.hex) meta.hex = m.hex;
  const base = {
    color, width: w, contents: m.text, author: authorFor(o.author ?? m.author), name: makeNm(o.set, m.id),
    modified: o.date ?? m.modified ?? m.created,
  };
  const P = (m.shape?.points ?? []).map((p) => [p[0], p[1]] as [number, number]);
  const flat = P.flatMap((p) => [p[0], p[1]]);
  const fillCol = m.fill ? color : undefined;
  if (m.kind === 'text' || m.kind === 'callout') {
    const g = anchorGeometry(m, sheet);
    if (!g || !m.anchor) return null;
    // The box rectangle in user space (the displayed rectangle turns with the page).
    const c1 = displayToUser(sheet, g.box.x, g.box.y);
    const c2 = displayToUser(sheet, g.box.x + g.box.w, g.box.y + g.box.h);
    const rect = norm([c1[0], c1[1], c2[0], c2[1]]);
    const anchor: [number, number] = [m.anchor.point[0], m.anchor.point[1]];
    const meta2: XrayMeta = { ...meta, anchor, ...(m.offset ? { offset: [m.offset[0], m.offset[1]] } : {}) };
    const spec: AnnotSpec = { ...base, subtype: 'FreeText', rect, textLines: g.lines, fontSize: g.size, xray: meta2 };
    if (m.kind === 'callout') {
      const e = displayToUser(sheet, g.edge[0], g.edge[1]);
      spec.intent = 'FreeTextCallout';
      // /CL runs from the target (where the arrow head sits) to the box.
      spec.callout = [rnd(anchor[0]), rnd(anchor[1]), rnd(e[0]), rnd(e[1])];
      spec.lineEnding = ['OpenArrow', 'None'];
      spec.rect = norm([Math.min(rect[0], anchor[0], e[0]), Math.min(rect[1], anchor[1], e[1]), Math.max(rect[2], anchor[0], e[0]), Math.max(rect[3], anchor[1], e[1])]);
      spec.rd = [rect[0] - spec.rect[0], rect[1] - spec.rect[1], spec.rect[2] - rect[2], spec.rect[3] - rect[3]];
    }
    return spec;
  }
  if (!P.length) return null;
  meta.points = flat;
  switch (m.kind) {
    case 'rect':
    case 'ellipse':
    case 'highlightBox': {
      if (P.length < 2) return null;
      const inner = norm([P[0]![0], P[0]![1], P[P.length - 1]![0], P[P.length - 1]![1]]);
      const hw = m.kind === 'highlightBox' ? 0 : w / 2;
      const spec: AnnotSpec = { ...base, subtype: m.kind === 'ellipse' ? 'Circle' : 'Square', rect: grow(inner, hw), rd: [hw, hw, hw, hw], xray: meta };
      if (m.kind === 'highlightBox') { spec.width = 0; spec.interior = color; spec.opacity = HIGHLIGHT_ALPHA; }
      else if (fillCol) spec.interior = fillCol;
      return spec;
    }
    case 'cloud': {
      const verts = P.length === 2 ? rectCorners(P[0]!, P[1]!) : flat;
      // Our own flat list is y up; rectCorners only orders the corners, which is fine in either orientation.
      const outline = cloudPolyline(verts, m.weight, sheet);
      const spec: AnnotSpec = { ...base, subtype: 'Polygon', rect: grow(boundsRect(outline), w / 2), vertices: verts.map(rnd), cloud: true, intent: 'PolygonCloud', xray: meta };
      if (fillCol) spec.interior = fillCol;
      return spec;
    }
    case 'polygon': {
      const spec: AnnotSpec = { ...base, subtype: 'Polygon', rect: grow(boundsRect(flat), w / 2), vertices: flat.map(rnd), xray: meta };
      if (fillCol) spec.interior = fillCol;
      return spec;
    }
    case 'polyline':
      return { ...base, subtype: 'PolyLine', rect: grow(boundsRect(flat), w / 2), vertices: flat.map(rnd), lineEnding: ['None', 'None'], xray: meta };
    case 'line':
    case 'arrow': {
      const a = P[P.length - 2] ?? P[0]!;
      const b = P[P.length - 1]!;
      const line: [number, number, number, number] = [rnd(a[0]), rnd(a[1]), rnd(b[0]), rnd(b[1])];
      const unit = sheetUnit(sheet);
      let r = boundsRect(line);
      if (m.kind === 'arrow') {
        const head = arrowHead(a[0], a[1], b[0], b[1], (10 + m.weight * 3) * unit, (4 + m.weight * 1.6) * unit);
        if (head) r = boundsRect([...line, ...head]);
      }
      const spec: AnnotSpec = { ...base, subtype: 'Line', rect: grow(r, w / 2), line, lineEnding: ['None', m.kind === 'arrow' ? 'ClosedArrow' : 'None'], xray: meta };
      if (m.kind === 'arrow') spec.interior = color;
      return spec;
    }
    case 'pen':
      return { ...base, subtype: 'Ink', rect: grow(boundsRect(flat), w / 2), inkList: [flat.map(rnd)], xray: meta };
    case 'highlight':
      return { ...base, subtype: 'Ink', rect: grow(boundsRect(flat), w / 2), inkList: [flat.map(rnd)], opacity: MARKER_ALPHA, xray: meta };
    default:
      return null;
  }
}

// ---------------------------------------------------------------- annotation -> markup

function pointsOfRect(r: Rect4): Array<[number, number]> {
  return [[r[0], r[1]], [r[2], r[3]]];
}
function pairs(flat: ArrayLike<number>): Array<[number, number]> {
  const out: Array<[number, number]> = [];
  for (let i = 0; i + 1 < flat.length; i += 2) out.push([flat[i]!, flat[i + 1]!]);
  return out;
}

export interface ReadOptions {
  /** Id for the new markup (ours keep the id in /NM). */
  id?: string;
  number?: number;
  /** The author of markups with no /T of their own. */
  author?: string;
}

/**
 * The markups of one annotation. Ours (`spec.xray`) give back the exact markup. Others are rebuilt from the standard keys: most
 * give one markup, an Ink with several strokes or a Highlight with several quads give one per stroke or quad.
 */
export function specToMarkups(spec: AnnotSpec, sheet: Pick<Sheet, 'widthPt' | 'heightPt' | 'rotation' | 'box'>, o: ReadOptions = {}): Markup[] {
  const author = spec.author || o.author || 'unknown';
  const common = (kind: MarkupKind, extra: Partial<Markup>): Markup => {
    const c = colourOf(spec.color);
    return newMarkup(kind, {
      ...(o.id ? { id: o.id } : {}), ...(o.number ? { number: o.number } : {}), author, text: spec.contents,
      colour: c.colour, ...(c.hex ? { hex: c.hex } : {}), weight: weightFor(kind, spec.width, sheet), fill: !!spec.interior && kind !== 'highlightBox' && kind !== 'arrow',
      created: spec.modified, ...extra,
    });
  };
  const shape = (pts: Array<[number, number]>): { shape: { points: Array<[number, number]>; depth: number } } => ({ shape: { points: pts, depth: 0 } });
  const x = spec.xray;
  if (x) {
    const kind = x.kind;
    const base: Partial<Markup> = { colour: x.colour, weight: x.weight, fill: x.fill, text: spec.contents, ...(x.hex ? { hex: x.hex } : {}) };
    const mk = (extra: Partial<Markup>): Markup => newMarkup(kind, { ...(o.id ? { id: o.id } : {}), number: x.number, author, created: spec.modified, ...base, ...extra });
    if (kind === 'text' || kind === 'callout') {
      let anchor = x.anchor;
      let offset = x.offset;
      if (!anchor) {
        const r = spec.rect;
        anchor = kind === 'callout' && spec.callout && spec.callout.length >= 4 ? [spec.callout[0]!, spec.callout[1]!] : [(r[0] + r[2]) / 2, (r[1] + r[3]) / 2];
      }
      if (!offset) {
        const A = userToDisplay(sheet, anchor[0], anchor[1]);
        const r = spec.rect;
        const c = userToDisplay(sheet, (r[0] + r[2]) / 2, (r[1] + r[3]) / 2);
        offset = offsetFor(sheet, A, c);
      }
      return [mk({ anchor: { kind: 'point', point: [anchor[0], anchor[1], 0] }, offset: [offset[0], offset[1]] })];
    }
    const pts = x.points && x.points.length >= 4 ? pairs(x.points) : null;
    if (pts) return [mk(shape(pts))];
    // Private keys without points: fall through to the standard keys with the kind they name.
  }
  switch (spec.subtype) {
    case 'Square': {
      const r = spec.rd ? norm([spec.rect[0] + spec.rd[0], spec.rect[1] + spec.rd[1], spec.rect[2] - spec.rd[2], spec.rect[3] - spec.rd[3]]) : spec.rect;
      const box = !!spec.interior && spec.opacity !== undefined && spec.opacity < 1 && spec.width <= 0.01;
      return [common(box ? 'highlightBox' : 'rect', shape(pointsOfRect(r)))];
    }
    case 'Circle': {
      const r = spec.rd ? norm([spec.rect[0] + spec.rd[0], spec.rect[1] + spec.rd[1], spec.rect[2] - spec.rd[2], spec.rect[3] - spec.rd[3]]) : spec.rect;
      return [common('ellipse', shape(pointsOfRect(r)))];
    }
    case 'Polygon': {
      const v = spec.vertices ?? [];
      if (v.length < 6) return [];
      return [common(spec.cloud ? 'cloud' : 'polygon', shape(pairs(v)))];
    }
    case 'PolyLine': {
      const v = spec.vertices ?? [];
      if (v.length < 4) return [];
      return [common('polyline', shape(pairs(v)))];
    }
    case 'Line': {
      const l = spec.line;
      if (!l) return [];
      const arrow = (spec.lineEnding ?? []).some((e) => /arrow/i.test(e));
      return [common(arrow ? 'arrow' : 'line', shape([[l[0], l[1]], [l[2], l[3]]]))];
    }
    case 'Ink': {
      const out: Markup[] = [];
      const marker = spec.opacity !== undefined && spec.opacity < 1 && spec.width >= 8;
      for (const stroke of spec.inkList ?? []) if (stroke.length >= 4) out.push(common(marker ? 'highlight' : 'pen', shape(pairs(stroke))));
      return out;
    }
    case 'FreeText': {
      const r = spec.rect;
      if (spec.intent === 'FreeTextCallout' && spec.callout && spec.callout.length >= 4) {
        const anchor: [number, number] = [spec.callout[0]!, spec.callout[1]!];
        const rr = spec.rd ? norm([r[0] + spec.rd[0], r[1] + spec.rd[1], r[2] - spec.rd[2], r[3] - spec.rd[3]]) : r;
        const A = userToDisplay(sheet, anchor[0], anchor[1]);
        const c = userToDisplay(sheet, (rr[0] + rr[2]) / 2, (rr[1] + rr[3]) / 2);
        return [common('callout', { anchor: { kind: 'point', point: [anchor[0], anchor[1], 0] }, offset: offsetFor(sheet, A, c) })];
      }
      const c: [number, number] = [(r[0] + r[2]) / 2, (r[1] + r[3]) / 2];
      return [common('text', { anchor: { kind: 'point', point: [c[0], c[1], 0] }, offset: [0, 0] })];
    }
    case 'Text': {
      const r = spec.rect;
      return [common('text', { anchor: { kind: 'point', point: [r[0], r[3], 0] }, offset: [0.03, -0.03] })];
    }
    case 'Highlight': {
      const out: Markup[] = [];
      const q = spec.quads ?? [];
      for (let i = 0; i + 7 < q.length; i += 8) {
        const b = boundsRect(q.slice(i, i + 8));
        out.push(common('highlightBox', shape(pointsOfRect(b))));
      }
      if (!out.length) out.push(common('highlightBox', shape(pointsOfRect(spec.rect))));
      return out;
    }
    case 'StrikeOut': {
      const out: Markup[] = [];
      const q = spec.quads ?? [];
      for (let i = 0; i + 7 < q.length; i += 8) {
        const b = boundsRect(q.slice(i, i + 8));
        const y = (b[1] + b[3]) / 2;
        out.push(common('line', shape([[b[0], y], [b[2], y]])));
      }
      if (!out.length) {
        const y = (spec.rect[1] + spec.rect[3]) / 2;
        out.push(common('line', shape([[spec.rect[0], y], [spec.rect[2], y]])));
      }
      return out;
    }
    default:
      return [];
  }
}

/** The text-box size in points of a text or callout (what the PDF box is), for tests and the export. */
export function textBoxSize(m: Markup, sheet: Pick<Sheet, 'widthPt' | 'heightPt'>): { w: number; h: number } {
  const b = boxSize(textLines(m), sheetUnit(sheet));
  return { w: b.w, h: b.h };
}
