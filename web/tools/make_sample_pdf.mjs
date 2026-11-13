// Builds bench/fixtures/sample-sheet.pdf: a small two-page plan-like PDF for the sheets tests and smoke check.
//   node tools/make_sample_pdf.mjs [out.pdf]
// Page 1 and 2 are A4 landscape drawings made of lines (walls), a title block and some text. Page 1 also carries three
// annotations that are not ours: a Square by "Reviewer A", a FreeText and an Ink. They exercise the import of existing annotations.
// The file is deterministic (fixed dates), so it can be committed and rebuilt without a diff.
import { writeFileSync, mkdirSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { PDFDocument, PDFHexString, PDFNumber, PDFName, PDFString, StandardFonts, rgb } from 'pdf-lib';

const here = dirname(fileURLToPath(import.meta.url));
const out = resolve(process.argv[2] ?? resolve(here, '../bench/fixtures/sample-sheet.pdf'));

const doc = await PDFDocument.create();
doc.setTitle('Sample sheet set');
doc.setAuthor('X-ray sample');
doc.setProducer('X-ray sample generator');
doc.setCreator('tools/make_sample_pdf.mjs');
doc.setCreationDate(new Date(Date.UTC(2026, 0, 5, 9, 0, 0)));
doc.setModificationDate(new Date(Date.UTC(2026, 0, 5, 9, 0, 0)));
const fontMain = await doc.embedFont(StandardFonts.Helvetica);
const boldMain = await doc.embedFont(StandardFonts.HelveticaBold);
const font = fontMain;
const W = 842;
const H = 595;
const ink = rgb(0.1, 0.1, 0.12);

function plan(page, title, sheetNo, level, rooms, font = fontMain, bold = boldMain) {
  const line = (x1, y1, x2, y2, t = 1.2) => page.drawLine({ start: { x: x1, y: y1 }, end: { x: x2, y: y2 }, thickness: t, color: ink });
  // sheet border and title block
  page.drawRectangle({ x: 20, y: 20, width: W - 40, height: H - 40, borderWidth: 1.5, borderColor: ink });
  page.drawRectangle({ x: W - 260, y: 20, width: 240, height: 90, borderWidth: 1, borderColor: ink });
  line(W - 260, 65, W - 20, 65, 0.8);
  page.drawText(title, { x: W - 250, y: 82, size: 13, font: bold, color: ink });
  page.drawText(`Sheet ${sheetNo}   Scale 1:100   ${level}`, { x: W - 250, y: 42, size: 9, font, color: ink });
  page.drawText('Sample project  -  drawn by X-ray', { x: W - 250, y: 28, size: 7, font, color: ink });
  // outer walls
  const x0 = 80, y0 = 150, x1 = 600, y1 = 520;
  line(x0, y0, x1, y0, 3); line(x1, y0, x1, y1, 3); line(x1, y1, x0, y1, 3); line(x0, y1, x0, y0, 3);
  // inner walls with door gaps
  line(x0, 340, 250, 340, 2); line(290, 340, 420, 340, 2); line(460, 340, x1, 340, 2);
  line(300, y0, 300, 250, 2); line(300, 290, 300, 340, 2);
  line(420, 340, 420, 450, 2); line(420, 490, 420, y1, 2);
  // windows on the outer wall
  for (const wx of [140, 360, 520]) { line(wx, y1 - 3, wx + 50, y1 - 3, 0.8); line(wx, y1 + 3, wx + 50, y1 + 3, 0.8); }
  rooms.forEach(([label, x, y]) => page.drawText(label, { x, y, size: 11, font, color: ink }));
  // dimension line
  line(x0, 130, x1, 130, 0.6); line(x0, 125, x0, 135, 0.6); line(x1, 125, x1, 135, 0.6);
  page.drawText('6 000', { x: 320, y: 117, size: 8, font, color: ink });
}

const p1 = doc.addPage([W, H]);
plan(p1, 'Ground floor plan', 'A-101', 'Level 0', [['Entrance', 150, 240], ['Office', 140, 430], ['Meeting', 330, 430], ['Store', 480, 430], ['Hall', 340, 230], ['Plant room', 470, 230]]);
const p2 = doc.addPage([W, H]);
plan(p2, 'First floor plan', 'A-102', 'Level 1', [['Open plan', 200, 430], ['Terrace', 470, 430], ['Stair', 140, 240], ['WC', 340, 230], ['Server', 470, 230]]);

// Annotations that are not ours (page 1).
const ctx = doc.context;
const annots = ctx.obj([]);
p1.node.set(PDFName.of('Annots'), annots);
const add = (d) => annots.push(ctx.register(ctx.obj(d)));
const when = PDFString.of("D:20260105100000Z");
add({
  Type: 'Annot', Subtype: 'Square', Rect: [310, 395, 400, 450], C: [1, 0, 0], BS: { W: 2, S: 'S' }, F: 4,
  T: PDFHexString.fromText('Reviewer A'), Contents: PDFHexString.fromText('Check the clearance to the meeting room door'), M: when, NM: PDFString.of('foreign-square-1'),
});
add({
  Type: 'Annot', Subtype: 'FreeText', Rect: [440, 535, 590, 575], C: [0, 0.4, 0.8], F: 4, DA: PDFString.of('0 0.4 0.8 rg /Helv 11 Tf'),
  T: PDFHexString.fromText('Reviewer B'), Contents: PDFHexString.fromText('Verify the door width'), M: when, NM: PDFString.of('foreign-text-1'),
});
add({
  Type: 'Annot', Subtype: 'Ink', Rect: [100, 160, 200, 230], C: [0.1, 0.6, 0.2], BS: { W: 2.5, S: 'S' }, F: 4,
  InkList: [[105, 170, 125, 215, 145, 175, 165, 222, 190, 168]],
  T: PDFHexString.fromText('Reviewer A'), Contents: PDFHexString.fromText('Hand sketch of the new partition'), M: when, NM: PDFString.of('foreign-ink-1'),
});

const bytes = await doc.save({ useObjectStreams: false });
mkdirSync(dirname(out), { recursive: true });
writeFileSync(out, bytes);
console.log(`wrote ${out} (${bytes.length} bytes)`);

// ---------------------------------------------------------------- the geo-referenced sheet
// bench/fixtures/geo-sheet.pdf: one A4 landscape page of the same plan, scale 1:100, carrying an ISO 32000 geospatial viewport
// (/VP << /Measure << /Subtype /GEO /GPTS /LPTS /GCS >> >>) in the projected CRS EPSG:25832 (ETRS89 / UTM zone 32N), north up.
// Sheet point (0, 0) is easting 500100, northing 5400010; one point is 0.352778 m / 10 = 0.03527778 m on the ground (1:100). The
// GPTS are easting, northing pairs (a producer that writes projected coordinates); tests/sheets-placement-geo.test.ts has the
// IfcMapConversion that goes with it (Eastings 500000, Northings 5400000: the model origin is 100 m east and 10 m north of the
// sheet's lower left corner).
export const GEO_FIXTURE = { epsg: 25832, e0: 500100, n0: 5400010, metresPerPoint: (25.4 / 72 / 1000) * 100, width: W, height: H };
{
  const gdoc = await PDFDocument.create();
  gdoc.setTitle('Geo-referenced sample sheet');
  gdoc.setProducer('X-ray sample generator');
  gdoc.setCreator('tools/make_sample_pdf.mjs');
  gdoc.setCreationDate(new Date(Date.UTC(2026, 0, 5, 9, 0, 0)));
  gdoc.setModificationDate(new Date(Date.UTC(2026, 0, 5, 9, 0, 0)));
  const gf = await gdoc.embedFont(StandardFonts.Helvetica);
  const gb = await gdoc.embedFont(StandardFonts.HelveticaBold);
  const gp = gdoc.addPage([W, H]);
  plan(gp, 'Site plan, geo-referenced', 'G-001', 'Level 0', [['Entrance', 150, 240], ['Office', 140, 430]], gf, gb);
  const g = GEO_FIXTURE;
  const at = (x, y) => [g.e0 + x * g.metresPerPoint, g.n0 + y * g.metresPerPoint];
  const corners = [at(0, 0), at(W, 0), at(W, H), at(0, H)];
  const gctx = gdoc.context;
  const wkt = 'PROJCS["ETRS89 / UTM zone 32N",GEOGCS["ETRS89",DATUM["European_Terrestrial_Reference_System_1989",SPHEROID["GRS 1980",6378137,298.257222101]],PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]],PROJECTION["Transverse_Mercator"],PARAMETER["latitude_of_origin",0],PARAMETER["central_meridian",9],PARAMETER["scale_factor",0.9996],PARAMETER["false_easting",500000],PARAMETER["false_northing",0],UNIT["metre",1],AUTHORITY["EPSG","25832"]]';
  const measure = gctx.obj({
    Type: 'Measure', Subtype: 'GEO',
    GPTS: corners.flat().map((v) => PDFNumber.of(Math.round(v * 1000) / 1000)),
    LPTS: [0, 0, 1, 0, 1, 1, 0, 1],
    GCS: { Type: 'PROJCS', EPSG: g.epsg, WKT: PDFString.of(wkt) },
  });
  gp.node.set(PDFName.of('VP'), gctx.obj([{ Type: 'Viewport', BBox: [0, 0, W, H], Name: PDFString.of('Plan'), Measure: measure }]));
  const gbytes = await gdoc.save({ useObjectStreams: false });
  const gout = resolve(dirname(out), 'geo-sheet.pdf');
  writeFileSync(gout, gbytes);
  console.log(`wrote ${gout} (${gbytes.length} bytes)`);
}
