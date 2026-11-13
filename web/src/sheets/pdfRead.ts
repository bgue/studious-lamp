// Reading a PDF: the pages (size, rotation, visible box) and the annotations on them. pdf.js reads the annotations that are
// not ours (getAnnotations: geometry, colour, border, author, contents). Ours (/NM starting "xray-") are read with pdf-lib,
// because pdf.js does not expose /NM and our private keys (/XrayKind ...), which give back the exact shape that was drawn.
// pdf.js lists our annotations too (same object numbers); they are left out of the foreign list. The libraries are passed in:
// they are loaded lazily (pdfRuntime.ts), this module imports types only.

import type * as PdfJs from 'pdfjs-dist';
import type * as PdfLib from 'pdf-lib';
import { isOwnNm } from './annot';
import type { AnnotSpec, AnnotSubtype, Rect4, Rgb, XrayMeta } from './annot';
import { cleanRotation } from './model';
import type { PageBox, Rotation } from './model';
import { COLOUR_KEYS } from '../markup/model';
import type { ColourKey, MarkupKind, Weight } from '../markup/model';

export interface PageInfo {
  /** 1-based. */
  page: number;
  widthPt: number;
  heightPt: number;
  rotation: Rotation;
  box: PageBox;
}

export const READ_SUBTYPES: readonly AnnotSubtype[] = ['Square', 'Circle', 'Line', 'PolyLine', 'Polygon', 'Ink', 'FreeText', 'Highlight', 'Text', 'StrikeOut'];
const isSubtype = (s: string): s is AnnotSubtype => (READ_SUBTYPES as readonly string[]).includes(s);

const KINDS: readonly MarkupKind[] = ['cloud', 'rect', 'ellipse', 'line', 'arrow', 'polyline', 'polygon', 'highlight', 'highlightBox', 'pen', 'text', 'callout'];

/** Open a PDF with pdf.js (a copy of the bytes: pdf.js takes the buffer it is given). */
export async function openPdf(libs: { pdfjs: typeof PdfJs; worker: PdfJs.PDFWorker }, bytes: Uint8Array): Promise<PdfJs.PDFDocumentProxy> {
  const task = libs.pdfjs.getDocument({
    data: new Uint8Array(bytes), worker: libs.worker, isEvalSupported: false, useSystemFonts: true, verbosity: 0, disableFontFace: false,
  } as never);
  return task.promise;
}

export async function pageInfos(pdf: PdfJs.PDFDocumentProxy): Promise<PageInfo[]> {
  const out: PageInfo[] = [];
  for (let i = 1; i <= pdf.numPages; i++) {
    const p = await pdf.getPage(i);
    const v = p.getViewport({ scale: 1 });
    const view = p.view as number[];
    out.push({
      page: i, widthPt: Math.round(v.width * 100) / 100, heightPt: Math.round(v.height * 100) / 100, rotation: cleanRotation(p.rotate),
      box: [view[0]!, view[1]!, view[2]!, view[3]!],
    });
    p.cleanup();
  }
  return out;
}

// ---------------------------------------------------------------- pdf.js annotations (foreign)

interface PdfJsAnnot {
  subtype?: string;
  id?: string;
  rect?: ArrayLike<number>;
  color?: ArrayLike<number> | null;
  borderStyle?: { width?: number } | null;
  contentsObj?: { str?: string } | null;
  titleObj?: { str?: string } | null;
  vertices?: ArrayLike<number> | null;
  lineCoordinates?: ArrayLike<number> | null;
  lineEndings?: string[] | null;
  inkLists?: ArrayLike<number>[] | null;
  quadPoints?: ArrayLike<number> | null;
  opacity?: number;
  it?: string;
  modificationDate?: string | null;
  creationDate?: string | null;
  annotationFlags?: number;
  defaultAppearanceData?: { fontSize?: number } | null;
}

/** "D:20240131093000+01'00'" to ISO; the time of day when unreadable. */
export function pdfDateToIso(s: string | null | undefined, fallback = new Date(0).toISOString()): string {
  const m = /^D:(\d{4})(\d{2})?(\d{2})?(\d{2})?(\d{2})?(\d{2})?(Z|[+-]\d{2}'?\d{2}'?)?/.exec(s ?? '');
  if (!m) return fallback;
  const [, y, mo = '01', d = '01', h = '00', mi = '00', se = '00', tz = 'Z'] = m;
  let off = 'Z';
  const t = /^([+-])(\d{2})'?(\d{2})/.exec(tz);
  if (t) off = `${t[1]}${t[2]}:${t[3]}`;
  const date = new Date(`${y}-${mo}-${d}T${h}:${mi}:${se}${off}`);
  return Number.isNaN(date.getTime()) ? fallback : date.toISOString();
}

const arr = (a: ArrayLike<number> | null | undefined): number[] => (a ? Array.from(a) : []);

/** A foreign annotation as read by pdf.js, or null for a kind we do not show (links, widgets, popups ...). */
export function specFromPdfjs(a: PdfJsAnnot, page: number, index: number): AnnotSpec | null {
  const st = a.subtype ?? '';
  if (!isSubtype(st)) return null;
  const flags = a.annotationFlags ?? 0;
  if (flags & 2 || flags & 32) return null; // hidden, no view
  const r = arr(a.rect);
  if (r.length < 4) return null;
  const c = a.color ? arr(a.color) : [];
  const color: Rgb = c.length >= 3 ? [c[0]! / 255, c[1]! / 255, c[2]! / 255] : st === 'Highlight' ? [1, 0.9, 0] : [0, 0, 0];
  const spec: AnnotSpec = {
    subtype: st,
    rect: [Math.min(r[0]!, r[2]!), Math.min(r[1]!, r[3]!), Math.max(r[0]!, r[2]!), Math.max(r[1]!, r[3]!)],
    color,
    width: a.borderStyle?.width !== undefined ? a.borderStyle.width : 1,
    contents: a.contentsObj?.str ?? '',
    author: a.titleObj?.str ?? '',
    name: `foreign-${page}-${index}`,
    modified: pdfDateToIso(a.modificationDate ?? a.creationDate),
  };
  if (a.opacity !== undefined && a.opacity < 1) spec.opacity = a.opacity;
  if (a.vertices) spec.vertices = arr(a.vertices);
  if (a.lineCoordinates && a.lineCoordinates.length >= 4) spec.line = arr(a.lineCoordinates).slice(0, 4) as [number, number, number, number];
  if (a.lineEndings && a.lineEndings.length >= 2) spec.lineEnding = [a.lineEndings[0]!, a.lineEndings[1]!];
  if (a.inkLists) spec.inkList = a.inkLists.map(arr);
  if (a.quadPoints) spec.quads = arr(a.quadPoints);
  if (a.it) spec.intent = a.it;
  if (a.it === 'PolygonCloud') spec.cloud = true;
  if (st === 'FreeText') spec.fontSize = a.defaultAppearanceData?.fontSize ?? 12;
  // A Line's coordinates from pdf.js are a normalised rectangle (direction lost); readForeign puts the real end points back.
  return spec;
}

/** Object number of a pdf.js annotation id ("23R" -> 23), or -1. */
export function objectNumberOf(id: string | undefined): number {
  const m = /^(\d+)R$/.exec(id ?? '');
  return m ? Number(m[1]) : -1;
}

// ---------------------------------------------------------------- pdf-lib annotations (ours)

type Lib = typeof PdfLib;

function text(lib: Lib, o: PdfLib.PDFObject | undefined): string | undefined {
  if (o instanceof lib.PDFString || o instanceof lib.PDFHexString) return o.decodeText();
  return undefined;
}
function nums(lib: Lib, o: PdfLib.PDFObject | undefined): number[] | undefined {
  if (!(o instanceof lib.PDFArray)) return undefined;
  const out: number[] = [];
  for (let i = 0; i < o.size(); i++) {
    const x = o.lookup(i);
    if (!(x instanceof lib.PDFNumber)) return undefined;
    out.push(x.asNumber());
  }
  return out;
}

/** One annotation dictionary as a spec (our private keys included when present). Null when it is not a subtype we read. */
export function specFromDict(lib: Lib, dict: PdfLib.PDFDict): AnnotSpec | null {
  const N = lib.PDFName.of;
  const nameOf = (k: string): string | undefined => { const v = dict.lookup(N(k)); return v instanceof lib.PDFName ? v.decodeText() : undefined; };
  const st = nameOf('Subtype') ?? '';
  if (!isSubtype(st)) return null;
  const rect = nums(lib, dict.lookup(N('Rect')));
  if (!rect || rect.length < 4) return null;
  const c = nums(lib, dict.lookup(N('C')));
  const ic = nums(lib, dict.lookup(N('IC')));
  const bs = dict.lookupMaybe(N('BS'), lib.PDFDict);
  const w = bs?.lookup(N('W'));
  const ca = dict.lookup(N('CA'));
  const spec: AnnotSpec = {
    subtype: st,
    rect: [Math.min(rect[0]!, rect[2]!), Math.min(rect[1]!, rect[3]!), Math.max(rect[0]!, rect[2]!), Math.max(rect[1]!, rect[3]!)],
    color: c && c.length >= 3 ? [c[0]!, c[1]!, c[2]!] : [0, 0, 0],
    width: w instanceof lib.PDFNumber ? w.asNumber() : 1,
    contents: text(lib, dict.lookup(N('Contents'))) ?? '',
    author: text(lib, dict.lookup(N('T'))) ?? '',
    name: text(lib, dict.lookup(N('NM'))) ?? '',
    modified: pdfDateToIso(text(lib, dict.lookup(N('M'))), new Date().toISOString()),
  };
  if (ic && ic.length >= 3) spec.interior = [ic[0]!, ic[1]!, ic[2]!];
  if (ca instanceof lib.PDFNumber) spec.opacity = ca.asNumber();
  const rd = nums(lib, dict.lookup(N('RD')));
  if (rd && rd.length >= 4) spec.rd = [rd[0]!, rd[1]!, rd[2]!, rd[3]!];
  const v = nums(lib, dict.lookup(N('Vertices')));
  if (v) spec.vertices = v;
  const l = nums(lib, dict.lookup(N('L')));
  if (l && l.length >= 4) spec.line = [l[0]!, l[1]!, l[2]!, l[3]!];
  const le = dict.lookup(N('LE'));
  if (le instanceof lib.PDFArray) {
    const a = le.lookup(0);
    const b = le.lookup(1);
    spec.lineEnding = [a instanceof lib.PDFName ? a.decodeText() : 'None', b instanceof lib.PDFName ? b.decodeText() : 'None'];
  } else if (le instanceof lib.PDFName) spec.lineEnding = [le.decodeText(), 'None'];
  const ink = dict.lookup(N('InkList'));
  if (ink instanceof lib.PDFArray) {
    const lists: number[][] = [];
    for (let i = 0; i < ink.size(); i++) { const s = nums(lib, ink.lookup(i)); if (s) lists.push(s); }
    spec.inkList = lists;
  }
  const be = dict.lookupMaybe(N('BE'), lib.PDFDict);
  const bes = be?.lookup(N('S'));
  if (bes instanceof lib.PDFName && bes.decodeText() === 'C') spec.cloud = true;
  const it = nameOf('IT');
  if (it) spec.intent = it;
  const cl = nums(lib, dict.lookup(N('CL')));
  if (cl && cl.length >= 4) spec.callout = cl;
  const q = nums(lib, dict.lookup(N('QuadPoints')));
  if (q) spec.quads = q;
  // Our private keys.
  const kind = nameOf('XrayKind');
  if (kind && (KINDS as readonly string[]).includes(kind)) {
    const colour = nameOf('XrayColour');
    const weight = dict.lookup(N('XrayWeight'));
    const meta: XrayMeta = {
      kind: kind as MarkupKind,
      weight: (weight instanceof lib.PDFNumber && [1, 2, 3, 4].includes(weight.asNumber()) ? weight.asNumber() : 2) as Weight,
      colour: (colour && (COLOUR_KEYS as readonly string[]).includes(colour) ? colour : 'red') as ColourKey,
      fill: dict.lookup(N('XrayFill')) === lib.PDFBool.True,
      number: (() => { const n = dict.lookup(N('XrayNumber')); return n instanceof lib.PDFNumber ? n.asNumber() : 0; })(),
      set: text(lib, dict.lookup(N('XraySet'))) ?? '',
      title: text(lib, dict.lookup(N('XrayTitle'))) ?? 'Sketch',
    };
    const hex = text(lib, dict.lookup(N('XrayHex')));
    if (hex && /^#[0-9a-fA-F]{6}$/.test(hex)) meta.hex = hex.toLowerCase();
    const pts = nums(lib, dict.lookup(N('XrayPts')));
    if (pts) meta.points = pts;
    const an = nums(lib, dict.lookup(N('XrayAnchor')));
    if (an && an.length >= 2) meta.anchor = [an[0]!, an[1]!];
    const of = nums(lib, dict.lookup(N('XrayOffset')));
    if (of && of.length >= 2) meta.offset = [of[0]!, of[1]!];
    spec.xray = meta;
  }
  return spec;
}

export interface OwnAnnot {
  /** 1-based page. */
  page: number;
  spec: AnnotSpec;
  /** The object number of the annotation (matches the pdf.js id "<n>R"). */
  objectNumber: number;
}

export interface LineGeometry {
  line: [number, number, number, number];
  lineEnding?: [string, string];
}

/**
 * Our annotations (/NM starting "xray-") on every page, read with pdf-lib, and the exact end points of every /Line (pdf.js only
 * reports a normalised rectangle for a line, which loses its direction).
 */
export async function readOwn(lib: Lib, bytes: Uint8Array): Promise<{ own: OwnAnnot[]; lines: Map<number, LineGeometry> }> {
  const doc = await lib.PDFDocument.load(bytes, { updateMetadata: false, throwOnInvalidObject: false });
  const own: OwnAnnot[] = [];
  const lines = new Map<number, LineGeometry>();
  const pages = doc.getPages();
  pages.forEach((page, i) => {
    const annots = page.node.lookupMaybe(lib.PDFName.of('Annots'), lib.PDFArray);
    if (!annots) return;
    for (let k = 0; k < annots.size(); k++) {
      const ref = annots.get(k);
      const d = doc.context.lookupMaybe(ref, lib.PDFDict);
      if (!d) continue;
      const objectNumber = ref instanceof lib.PDFRef ? ref.objectNumber : -1;
      const spec = specFromDict(lib, d);
      if (!spec) continue;
      if (isOwnNm(spec.name)) own.push({ page: i + 1, spec, objectNumber });
      else if (spec.subtype === 'Line' && spec.line && objectNumber >= 0) lines.set(objectNumber, { line: spec.line, ...(spec.lineEnding ? { lineEnding: spec.lineEnding } : {}) });
    }
  });
  return { own, lines };
}

export interface ForeignAnnot {
  page: number;
  spec: AnnotSpec;
}

/**
 * The annotations of every page that pdf.js can read, minus ours (`own` object numbers). Returns the foreign ones in page
 * order. `count` is the number of annotations of any kind the document has (links and widgets included), to decide whether
 * the pdf-lib pass for ours is worth running.
 */
export async function readForeign(pdf: PdfJs.PDFDocumentProxy, own: ReadonlySet<number> = new Set(), lines: ReadonlyMap<number, LineGeometry> = new Map()): Promise<{ annots: ForeignAnnot[]; count: number }> {
  const annots: ForeignAnnot[] = [];
  let count = 0;
  for (let i = 1; i <= pdf.numPages; i++) {
    const p = await pdf.getPage(i);
    const list = (await p.getAnnotations()) as PdfJsAnnot[];
    count += list.length;
    list.forEach((a, k) => {
      if (own.has(objectNumberOf(a.id))) return;
      const s = specFromPdfjs(a, i, k);
      if (!s) return;
      const g = s.subtype === 'Line' ? lines.get(objectNumberOf(a.id)) : undefined;
      if (g) { s.line = g.line; if (g.lineEnding) s.lineEnding = g.lineEnding; }
      annots.push({ page: i, spec: s });
    });
    p.cleanup();
  }
  return { annots, count };
}

/** Whether any page has an annotation of a kind we show: the cheap test before the pdf-lib pass. */
export async function hasMarkupAnnotations(pdf: PdfJs.PDFDocumentProxy): Promise<boolean> {
  for (let i = 1; i <= pdf.numPages; i++) {
    const p = await pdf.getPage(i);
    const list = (await p.getAnnotations()) as PdfJsAnnot[];
    p.cleanup();
    if (list.some((a) => isSubtype(a.subtype ?? ''))) return true;
  }
  return false;
}

export type { Rect4 };
