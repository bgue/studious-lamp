/* eslint-disable @typescript-eslint/no-explicit-any */
// Writing the sketches of a sheet into a copy of its PDF with pdf-lib: one Optional Content Group "X-ray markups", and real PDF
// annotations (src/sheets/annot.ts) that each point at it with /OC and carry an appearance stream (appearance.ts). The page
// content is not touched. A re-export removes the annotations of the earlier export (/NM starting "xray-") first, so they are
// never doubled. pdf-lib saves the whole file again (it has no incremental save); object streams are off so the result stays
// readable by simple tools. The library is passed in (it is loaded lazily, see pdfRuntime.ts); this module imports types only.

import type * as PdfLib from 'pdf-lib';
import { LAYER_NAME, isOwnNm, markupToSpec } from './annot';
import type { AnnotSpec } from './annot';
import { buildAppearance } from './appearance';
import type { MarkupSet } from '../markup/model';
import type { Sheet } from './model';

export interface PageExport {
  sheet: Sheet;
  /** The editable sketches drawn on the sheet. */
  sets: readonly MarkupSet[];
}

export interface WriteResult {
  bytes: Uint8Array;
  /** Annotations written, and earlier X-ray annotations removed. */
  added: number;
  removed: number;
  /** Annotation subtypes written, with counts. */
  subtypes: Record<string, number>;
}

type Lib = typeof PdfLib;

function textOf(lib: Lib, o: PdfLib.PDFObject | undefined): string | undefined {
  if (o instanceof lib.PDFString || o instanceof lib.PDFHexString) return o.decodeText();
  return undefined;
}

/** The OCG named LAYER_NAME, made when missing, and listed in /OCProperties (/OCGs, /D /Order, /D /ON). */
export function ensureLayer(lib: Lib, doc: PdfLib.PDFDocument): PdfLib.PDFRef {
  const { PDFName, PDFDict, PDFArray, PDFRef } = lib;
  const ctx = doc.context;
  const cat = doc.catalog;
  let ocp = cat.lookupMaybe(PDFName.of('OCProperties'), PDFDict);
  if (!ocp) {
    ocp = ctx.obj({});
    cat.set(PDFName.of('OCProperties'), ocp);
  }
  let ocgs = ocp.lookupMaybe(PDFName.of('OCGs'), PDFArray);
  if (!ocgs) {
    ocgs = ctx.obj([]);
    ocp.set(PDFName.of('OCGs'), ocgs);
  }
  let ref: PdfLib.PDFRef | undefined;
  for (let i = 0; i < ocgs.size(); i++) {
    const r = ocgs.get(i);
    const d = ctx.lookupMaybe(r, PDFDict);
    if (r instanceof PDFRef && d && textOf(lib, d.lookup(PDFName.of('Name'))) === LAYER_NAME) { ref = r; break; }
  }
  if (!ref) {
    ref = ctx.register(ctx.obj({
      Type: 'OCG',
      Name: lib.PDFString.of(LAYER_NAME),
      Intent: 'View',
      Usage: { View: { ViewState: 'ON' }, Print: { PrintState: 'ON' } },
    }));
    ocgs.push(ref);
  }
  let d = ocp.lookupMaybe(PDFName.of('D'), PDFDict);
  if (!d) {
    d = ctx.obj({});
    ocp.set(PDFName.of('D'), d);
  }
  const listed = (a: PdfLib.PDFArray): boolean => {
    for (let i = 0; i < a.size(); i++) { const x = a.get(i); if (x instanceof PDFRef && x.objectNumber === ref!.objectNumber) return true; }
    return false;
  };
  let order = d.lookupMaybe(PDFName.of('Order'), PDFArray);
  if (!order) {
    order = ctx.obj([]);
    d.set(PDFName.of('Order'), order);
  }
  if (!listed(order)) order.push(ref);
  let on = d.lookupMaybe(PDFName.of('ON'), PDFArray);
  if (!on) {
    on = ctx.obj([]);
    d.set(PDFName.of('ON'), on);
  }
  if (!listed(on)) on.push(ref);
  // Our layer is shown: take it out of /OFF when an earlier viewer switched it off and saved.
  const off = d.lookupMaybe(PDFName.of('OFF'), PDFArray);
  if (off) for (let i = off.size() - 1; i >= 0; i--) { const x = off.get(i); if (x instanceof PDFRef && x.objectNumber === ref.objectNumber) off.remove(i); }
  // Optional content needs PDF 1.5.
  const head = ctx.header.toString();
  const m = /%PDF-(\d)\.(\d)/.exec(head);
  if (m && (Number(m[1]) < 1 || (Number(m[1]) === 1 && Number(m[2]) < 5))) ctx.header = lib.PDFHeader.forVersion(1, 5);
  return ref;
}

/** Remove the annotations of an earlier X-ray export from a page; returns how many. */
export function removeOwn(lib: Lib, doc: PdfLib.PDFDocument, page: PdfLib.PDFPage): number {
  const { PDFName, PDFDict, PDFArray, PDFRef } = lib;
  const ctx = doc.context;
  const annots = page.node.lookupMaybe(PDFName.of('Annots'), PDFArray);
  if (!annots) return 0;
  let n = 0;
  for (let i = annots.size() - 1; i >= 0; i--) {
    const ref = annots.get(i);
    const d = ctx.lookupMaybe(ref, PDFDict);
    if (!d) continue;
    if (!isOwnNm(textOf(lib, d.lookup(PDFName.of('NM'))))) continue;
    annots.remove(i);
    const ap = d.lookupMaybe(PDFName.of('AP'), PDFDict);
    const nref = ap?.get(PDFName.of('N'));
    if (nref instanceof PDFRef) ctx.delete(nref);
    if (ref instanceof PDFRef) ctx.delete(ref);
    n++;
  }
  return n;
}

function num(a: readonly number[]): number[] {
  return a.map((v) => Math.round(v * 1000) / 1000);
}

/** The annotation dictionary of a spec (without the appearance). */
export function annotDict(lib: Lib, doc: PdfLib.PDFDocument, spec: AnnotSpec, ocg: PdfLib.PDFRef, pageRef: PdfLib.PDFRef): PdfLib.PDFDict {
  const { PDFHexString, PDFString, PDFName } = lib;
  const ctx = doc.context;
  const o: Record<string, any> = {
    Type: 'Annot',
    Subtype: spec.subtype,
    Rect: num(spec.rect),
    F: 4,
    C: num(spec.color),
    P: pageRef,
    OC: ocg,
    NM: PDFString.of(spec.name),
    T: PDFHexString.fromText(spec.author),
    Contents: PDFHexString.fromText(spec.contents),
    M: PDFString.fromDate(new Date(spec.modified)),
  };
  const borderless = spec.width <= 0.01;
  o['BS'] = { Type: 'Border', W: Math.round(spec.width * 1000) / 1000, S: 'S' };
  if (borderless) o['Border'] = [0, 0, 0];
  if (spec.opacity !== undefined) o['CA'] = spec.opacity;
  if (spec.interior) o['IC'] = num(spec.interior);
  if (spec.rd && (spec.subtype === 'Square' || spec.subtype === 'Circle' || spec.subtype === 'FreeText')) o['RD'] = num(spec.rd);
  if (spec.vertices && (spec.subtype === 'Polygon' || spec.subtype === 'PolyLine')) o['Vertices'] = num(spec.vertices);
  if (spec.subtype === 'Line' && spec.line) {
    o['L'] = num(spec.line);
    o['LE'] = (spec.lineEnding ?? ['None', 'None']).map((e) => PDFName.of(e));
  }
  if (spec.subtype === 'PolyLine') o['LE'] = (spec.lineEnding ?? ['None', 'None']).map((e) => PDFName.of(e));
  if (spec.subtype === 'Ink' && spec.inkList) o['InkList'] = spec.inkList.map((s) => num(s));
  if (spec.cloud) o['BE'] = { S: 'C', I: 1 };
  if (spec.intent) o['IT'] = spec.intent;
  if (spec.subtype === 'FreeText') {
    const size = Math.round((spec.fontSize ?? 12) * 100) / 100;
    o['DA'] = PDFString.of(`0.067 0.067 0.067 rg /Helv ${size} Tf`);
    o['Q'] = 0;
    if (spec.callout) {
      o['CL'] = num(spec.callout);
      o['LE'] = PDFName.of(spec.lineEnding?.[0] ?? 'OpenArrow');
    }
  }
  const x = spec.xray;
  if (x) {
    o['XrayKind'] = x.kind;
    o['XrayWeight'] = x.weight;
    o['XrayColour'] = x.colour;
    if (x.hex) o['XrayHex'] = PDFString.of(x.hex);
    o['XrayFill'] = x.fill ? lib.PDFBool.True : lib.PDFBool.False;
    o['XrayNumber'] = x.number;
    o['XraySet'] = PDFString.of(x.set);
    o['XrayTitle'] = PDFHexString.fromText(x.title);
    if (x.points) o['XrayPts'] = num(x.points);
    if (x.anchor) o['XrayAnchor'] = num(x.anchor);
    if (x.offset) o['XrayOffset'] = x.offset.map((v) => Math.round(v * 1e5) / 1e5);
  }
  return ctx.obj(o as never) as unknown as PdfLib.PDFDict;
}

/**
 * Write the sketches into a copy of the PDF. Pages are those of `pages`; every other page is left as it is (its X-ray
 * annotations, if any, are removed too when the page is listed with no sketches, so a deleted sketch leaves the file).
 */
export async function writeMarkedUp(lib: Lib, bytes: Uint8Array, pages: readonly PageExport[], o: { date?: Date } = {}): Promise<WriteResult> {
  const doc = await lib.PDFDocument.load(bytes, { updateMetadata: false });
  const ocg = ensureLayer(lib, doc);
  const ctx = doc.context;
  const date = (o.date ?? new Date()).toISOString();
  let added = 0;
  let removed = 0;
  const subtypes: Record<string, number> = {};
  let font: PdfLib.PDFFont | null = null;
  const docPages = doc.getPages();
  for (const pe of pages) {
    const page = docPages[pe.sheet.page - 1];
    if (!page) continue;
    removed += removeOwn(lib, doc, page);
    const annots = page.node.lookupMaybe(lib.PDFName.of('Annots'), lib.PDFArray) ?? (() => {
      const a = ctx.obj([]);
      page.node.set(lib.PDFName.of('Annots'), a);
      return a;
    })();
    for (const set of pe.sets) {
      if (set.readonly) continue;
      for (const m of set.markups) {
        const spec = markupToSpec(m, pe.sheet, { set: set.id, title: set.title, author: m.author || set.author, date: m.modified ?? date });
        if (!spec) continue;
        const ap = buildAppearance(spec, pe.sheet);
        const dict = annotDict(lib, doc, spec, ocg, page.ref);
        if (ap) {
          const res: Record<string, any> = {};
          if (Object.keys(ap.gs).length) res['ExtGState'] = Object.fromEntries(Object.entries(ap.gs).map(([k, v]) => [k, { Type: 'ExtGState', CA: v.CA, ca: v.ca, ...(v.BM ? { BM: v.BM } : {}) }]));
          if (ap.font) {
            font ??= doc.embedStandardFont(lib.StandardFonts.Helvetica);
            res['Font'] = { Helv: font.ref };
          }
          const stream = ctx.stream(ap.content, { Type: 'XObject', Subtype: 'Form', FormType: 1, BBox: ap.bbox.map((v) => Math.round(v * 1000) / 1000), Matrix: [1, 0, 0, 1, 0, 0], Resources: res });
          dict.set(lib.PDFName.of('AP'), ctx.obj({ N: ctx.register(stream) }));
        }
        annots.push(ctx.register(dict));
        added++;
        subtypes[spec.subtype] = (subtypes[spec.subtype] ?? 0) + 1;
      }
    }
  }
  const out = await doc.save({ useObjectStreams: false, addDefaultPage: false, updateFieldAppearances: false });
  return { bytes: out, added, removed, subtypes };
}
