// @vitest-environment node
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { beforeAll, describe, expect, it } from 'vitest';
import * as PdfLib from 'pdf-lib';
import { newMarkup } from '../src/markup/model';
import type { Markup, MarkupKind, MarkupSet } from '../src/markup/model';
import { LAYER_NAME, isOwnNm, specToMarkups } from '../src/sheets/annot';
import { openPdf, pageInfos, readForeign, readOwn } from '../src/sheets/pdfRead';
import { writeMarkedUp } from '../src/sheets/pdfWrite';
import { docIdOf, sha256Hex, sheetIdOf } from '../src/sheets/model';
import type { Sheet } from '../src/sheets/model';

const fixture = new Uint8Array(readFileSync(fileURLToPath(new URL('../bench/fixtures/sample-sheet.pdf', import.meta.url))));
let pdfjs: typeof import('pdfjs-dist');
let sheet1: Sheet;

beforeAll(async () => {
  pdfjs = (await import('pdfjs-dist/legacy/build/pdf.mjs')) as never;
  const doc = await openPdf({ pdfjs, worker: undefined as never }, fixture);
  const p = (await pageInfos(doc))[0]!;
  const docId = docIdOf(await sha256Hex(fixture));
  sheet1 = { id: sheetIdOf(docId, 1), docId, page: 1, name: 'Sample', widthPt: p.widthPt, heightPt: p.heightPt, rotation: p.rotation, box: p.box };
  await doc.destroy();
});

const shape = (pts: Array<[number, number]>) => ({ points: pts, depth: 0 });
function m(kind: MarkupKind, id: string, extra: Partial<Markup>): Markup {
  return newMarkup(kind, { id, number: 1, author: 'unknown', text: `${kind} text`, created: '2026-02-01T10:00:00.000Z', ...extra });
}
function sketch(): MarkupSet {
  const markups: Markup[] = [
    m('cloud', 'm1', { shape: shape([[100, 100], [300, 220]]) }),
    m('rect', 'm2', { shape: shape([[320, 100], [420, 180]]) }),
    m('ellipse', 'm3', { shape: shape([[320, 200], [420, 260]]) }),
    m('arrow', 'm4', { shape: shape([[450, 100], [560, 200]]) }),
    m('line', 'm5', { shape: shape([[450, 220], [560, 260]]) }),
    m('polyline', 'm6', { shape: shape([[100, 300], [150, 350], [200, 310]]) }),
    m('polygon', 'm7', { shape: shape([[250, 300], [330, 340], [290, 400]]) }),
    m('pen', 'm8', { shape: shape([[400, 300], [410, 320], [430, 310], [450, 340]]) }),
    m('text', 'm9', { text: 'Hello sheet', anchor: { kind: 'point', point: [500, 400, 0] }, offset: [0.05, -0.04] }),
    m('callout', 'm10', { text: 'See this', anchor: { kind: 'point', point: [200, 450, 0] }, offset: [0.1, -0.09] }),
    m('highlightBox', 'm11', { colour: 'yellow', shape: shape([[100, 480], [260, 520]]) }),
    m('highlight', 'm12', { colour: 'yellow', weight: 3, shape: shape([[300, 480], [350, 490], [400, 480]]) }),
  ];
  const now = '2026-02-01T10:00:00.000Z';
  return { id: 'sSketch1', title: 'Review', author: 'unknown', created: now, updated: now, markups, nextNumber: 13, frame: { kind: 'sheet', sheet: sheet1.id } } as unknown as MarkupSet;
}

async function load(bytes: Uint8Array): Promise<PdfLib.PDFDocument> {
  return PdfLib.PDFDocument.load(bytes, { updateMetadata: false });
}

function annotsOf(doc: PdfLib.PDFDocument, page = 0): PdfLib.PDFDict[] {
  const a = doc.getPages()[page]!.node.lookupMaybe(PdfLib.PDFName.of('Annots'), PdfLib.PDFArray);
  const out: PdfLib.PDFDict[] = [];
  for (let i = 0; a && i < a.size(); i++) out.push(doc.context.lookup(a.get(i), PdfLib.PDFDict));
  return out;
}
const nmOf = (d: PdfLib.PDFDict): string => (d.lookup(PdfLib.PDFName.of('NM')) as PdfLib.PDFString).decodeText();
const own = (doc: PdfLib.PDFDocument): PdfLib.PDFDict[] => annotsOf(doc).filter((d) => isOwnNm(nmOf(d)));
const name = (d: PdfLib.PDFDict, k: string): string => (d.lookup(PdfLib.PDFName.of(k)) as PdfLib.PDFName).decodeText();

describe('export: annotations on their own layer', () => {
  it('adds the layer to /OCProperties and every added annotation points at it', async () => {
    const r = await writeMarkedUp(PdfLib, fixture, [{ sheet: sheet1, sets: [sketch()] }]);
    expect(r.added).toBe(12);
    const doc = await load(r.bytes);
    const ocp = doc.catalog.lookup(PdfLib.PDFName.of('OCProperties'), PdfLib.PDFDict);
    const ocgs = ocp.lookup(PdfLib.PDFName.of('OCGs'), PdfLib.PDFArray);
    expect(ocgs.size()).toBe(1);
    const ocgRef = ocgs.get(0) as PdfLib.PDFRef;
    const ocg = doc.context.lookup(ocgRef, PdfLib.PDFDict);
    expect(name(ocg, 'Type')).toBe('OCG');
    expect((ocg.lookup(PdfLib.PDFName.of('Name')) as PdfLib.PDFString).decodeText()).toBe(LAYER_NAME);
    const d = ocp.lookup(PdfLib.PDFName.of('D'), PdfLib.PDFDict);
    for (const key of ['Order', 'ON']) {
      const a = d.lookup(PdfLib.PDFName.of(key), PdfLib.PDFArray);
      expect([...Array(a.size()).keys()].map((i) => (a.get(i) as PdfLib.PDFRef).objectNumber)).toContain(ocgRef.objectNumber);
    }
    const mine = own(doc);
    expect(mine).toHaveLength(12);
    for (const a of mine) {
      const oc = a.get(PdfLib.PDFName.of('OC')) as PdfLib.PDFRef;
      expect(oc.objectNumber).toBe(ocgRef.objectNumber);
      expect(a.lookup(PdfLib.PDFName.of('AP'), PdfLib.PDFDict).has(PdfLib.PDFName.of('N'))).toBe(true);
      expect((a.lookup(PdfLib.PDFName.of('T')) as PdfLib.PDFHexString).decodeText()).toBe('X-ray');
      expect(a.has(PdfLib.PDFName.of('C'))).toBe(true);
      expect(a.has(PdfLib.PDFName.of('BS'))).toBe(true);
      expect(a.has(PdfLib.PDFName.of('M'))).toBe(true);
      expect(a.has(PdfLib.PDFName.of('Contents'))).toBe(true);
    }
  });

  it('uses the subtype each tool maps to, with the cloud border effect and the callout line', async () => {
    const r = await writeMarkedUp(PdfLib, fixture, [{ sheet: sheet1, sets: [sketch()] }]);
    const doc = await load(r.bytes);
    const by = new Map(own(doc).map((a) => [nmOf(a).split('.')[1]!, a]));
    expect(r.subtypes).toEqual({ Polygon: 2, Square: 2, Circle: 1, Line: 2, PolyLine: 1, Ink: 2, FreeText: 2 });
    const cloud = by.get('m1')!;
    expect(name(cloud, 'Subtype')).toBe('Polygon');
    expect(name(cloud, 'IT')).toBe('PolygonCloud');
    const be = cloud.lookup(PdfLib.PDFName.of('BE'), PdfLib.PDFDict);
    expect(name(be, 'S')).toBe('C');
    expect((be.lookup(PdfLib.PDFName.of('I')) as PdfLib.PDFNumber).asNumber()).toBe(1);
    expect(by.get('m7')!.has(PdfLib.PDFName.of('BE'))).toBe(false);
    expect(name(by.get('m2')!, 'Subtype')).toBe('Square');
    expect(name(by.get('m3')!, 'Subtype')).toBe('Circle');
    const arrow = by.get('m4')!;
    expect(name(arrow, 'Subtype')).toBe('Line');
    const le = arrow.lookup(PdfLib.PDFName.of('LE'), PdfLib.PDFArray);
    expect((le.lookup(1) as PdfLib.PDFName).decodeText()).toBe('ClosedArrow');
    expect(name(by.get('m6')!, 'Subtype')).toBe('PolyLine');
    expect(name(by.get('m8')!, 'Subtype')).toBe('Ink');
    expect(name(by.get('m9')!, 'Subtype')).toBe('FreeText');
    const callout = by.get('m10')!;
    expect(name(callout, 'IT')).toBe('FreeTextCallout');
    expect(callout.lookup(PdfLib.PDFName.of('CL'), PdfLib.PDFArray).size()).toBe(4);
    const hl = by.get('m11')!;
    expect(name(hl, 'Subtype')).toBe('Square');
    expect((hl.lookup(PdfLib.PDFName.of('CA')) as PdfLib.PDFNumber).asNumber()).toBeLessThan(1);
  });

  it('leaves the page content and the annotations that are not ours as they were', async () => {
    const r = await writeMarkedUp(PdfLib, fixture, [{ sheet: sheet1, sets: [sketch()] }]);
    const before = await load(fixture);
    const after = await load(r.bytes);
    const stream = (d: PdfLib.PDFDocument): Uint8Array => {
      const c = d.getPages()[0]!.node.Contents() as PdfLib.PDFStream | PdfLib.PDFArray | undefined;
      const s = c instanceof PdfLib.PDFArray ? (d.context.lookup(c.get(0), PdfLib.PDFStream) as PdfLib.PDFStream) : (c as PdfLib.PDFStream);
      return (s as unknown as { getContents(): Uint8Array }).getContents();
    };
    expect(Array.from(stream(after))).toEqual(Array.from(stream(before)));
    const foreign = annotsOf(after).filter((a) => !isOwnNm(nmOf(a)));
    expect(foreign.map((a) => nmOf(a))).toEqual(['foreign-square-1', 'foreign-text-1', 'foreign-ink-1']);
    expect(after.getPageCount()).toBe(2);
  });

  it('replaces the earlier X-ray annotations on a second export instead of doubling them', async () => {
    const first = await writeMarkedUp(PdfLib, fixture, [{ sheet: sheet1, sets: [sketch()] }]);
    const set = sketch();
    set.markups = set.markups.slice(0, 5);
    const second = await writeMarkedUp(PdfLib, first.bytes, [{ sheet: sheet1, sets: [set] }]);
    expect(second.removed).toBe(12);
    expect(second.added).toBe(5);
    const doc = await load(second.bytes);
    expect(own(doc)).toHaveLength(5);
    expect(annotsOf(doc)).toHaveLength(5 + 3);
    const ocgs = doc.catalog.lookup(PdfLib.PDFName.of('OCProperties'), PdfLib.PDFDict).lookup(PdfLib.PDFName.of('OCGs'), PdfLib.PDFArray);
    expect(ocgs.size()).toBe(1);
    // exporting the same thing again gives the same set of annotations
    const third = await writeMarkedUp(PdfLib, second.bytes, [{ sheet: sheet1, sets: [set] }]);
    expect(own(await load(third.bytes))).toHaveLength(5);
    // a sheet with no sketches left is cleaned
    const cleared = await writeMarkedUp(PdfLib, third.bytes, [{ sheet: sheet1, sets: [] }]);
    expect(own(await load(cleared.bytes))).toHaveLength(0);
  });
});

describe('import', () => {
  it('rebuilds our own annotations as editable shapes (the export round-trips)', async () => {
    const set = sketch();
    const r = await writeMarkedUp(PdfLib, fixture, [{ sheet: sheet1, sets: [set] }]);
    const { own: found } = await readOwn(PdfLib, r.bytes);
    expect(found).toHaveLength(12);
    for (const o of found) {
      expect(o.page).toBe(1);
      const back = specToMarkups(o.spec, sheet1, { id: o.spec.name.split('.')[1]! })[0]!;
      const orig = set.markups.find((x) => x.id === back.id)!;
      expect(back.kind).toBe(orig.kind);
      expect(back.text).toBe(orig.text);
      expect(back.colour).toBe(orig.colour);
      expect(back.weight).toBe(orig.weight);
      if (orig.shape) expect(back.shape!.points).toEqual(orig.shape.points);
      if (orig.anchor) expect(back.anchor!.point[0]).toBeCloseTo(orig.anchor.point[0], 2);
      expect(o.spec.xray!.set).toBe('sSketch1');
      expect(o.spec.xray!.title).toBe('Review');
    }
  });

  it('reads the annotations that are not ours with pdf.js, read-only material with author and contents', async () => {
    const doc = await openPdf({ pdfjs, worker: undefined as never }, fixture);
    const { annots, count } = await readForeign(doc);
    expect(count).toBe(3);
    expect(annots.map((a) => a.spec.subtype).sort()).toEqual(['FreeText', 'Ink', 'Square']);
    const sq = annots.find((a) => a.spec.subtype === 'Square')!.spec;
    expect(sq.author).toBe('Reviewer A');
    expect(sq.contents).toContain('clearance');
    expect(sq.color).toEqual([1, 0, 0]);
    expect(sq.rect).toEqual([310, 395, 400, 450]);
    const marks = annots.flatMap((a) => specToMarkups(a.spec, sheet1, { number: 1 }));
    expect(marks.map((x) => x.kind).sort()).toEqual(['pen', 'rect', 'text']);
    expect(marks.find((x) => x.kind === 'rect')!.author).toBe('Reviewer A');
    expect(marks.find((x) => x.kind === 'pen')!.shape!.points).toHaveLength(5);
    await doc.destroy();
  });

  it('leaves our own annotations out of the foreign list and keeps the foreign ones when ours are present', async () => {
    const r = await writeMarkedUp(PdfLib, fixture, [{ sheet: sheet1, sets: [sketch()] }]);
    const { own: ours, lines } = await readOwn(PdfLib, r.bytes);
    const doc = await openPdf({ pdfjs, worker: undefined as never }, r.bytes);
    const { annots, count } = await readForeign(doc, new Set(ours.map((o) => o.objectNumber)), lines);
    expect(count).toBe(15);
    expect(annots).toHaveLength(3);
    await doc.destroy();
  });

  it('puts the end points of a foreign line back (pdf.js only reports its rectangle)', async () => {
    const lib = PdfLib;
    const pdf = await lib.PDFDocument.load(fixture);
    const ctx = pdf.context;
    const page = pdf.getPages()[1]!;
    const ref = ctx.register(ctx.obj({ Type: 'Annot', Subtype: 'Line', Rect: [100, 100, 300, 200], L: [100, 200, 300, 100], LE: ['None', 'OpenArrow'].map((e) => lib.PDFName.of(e)), C: [0, 0, 1], BS: { W: 2 }, F: 4 }));
    page.node.set(lib.PDFName.of('Annots'), ctx.obj([ref]));
    const bytes = await pdf.save({ useObjectStreams: false });
    const { own: o, lines } = await readOwn(lib, bytes);
    expect(o).toHaveLength(0);
    const doc = await openPdf({ pdfjs, worker: undefined as never }, bytes);
    const { annots } = await readForeign(doc, new Set(), lines);
    const line = annots.find((a) => a.spec.subtype === 'Line')!;
    expect(line.spec.line).toEqual([100, 200, 300, 100]);
    const back = specToMarkups(line.spec, sheet1)[0]!;
    expect(back.kind).toBe('arrow');
    expect(back.shape!.points).toEqual([[100, 200], [300, 100]]);
    await doc.destroy();
  });
});
