// Builds bench/fixtures/sample-sheet.pdf: a small two-page plan-like PDF for the sheets tests and smoke check.
//   node tools/make_sample_pdf.mjs [out.pdf]
// Page 1 and 2 are A4 landscape drawings made of lines (walls), a title block and some text. Page 1 also carries three
// annotations that are not ours: a Square by "Reviewer A", a FreeText and an Ink. They exercise the import of existing annotations.
// The file is deterministic (fixed dates), so it can be committed and rebuilt without a diff.
import { writeFileSync, mkdirSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { PDFDocument, PDFHexString, PDFName, PDFString, StandardFonts, rgb } from 'pdf-lib';

const here = dirname(fileURLToPath(import.meta.url));
const out = resolve(process.argv[2] ?? resolve(here, '../bench/fixtures/sample-sheet.pdf'));

const doc = await PDFDocument.create();
doc.setTitle('Sample sheet set');
doc.setAuthor('X-ray sample');
doc.setProducer('X-ray sample generator');
doc.setCreator('tools/make_sample_pdf.mjs');
doc.setCreationDate(new Date(Date.UTC(2026, 0, 5, 9, 0, 0)));
doc.setModificationDate(new Date(Date.UTC(2026, 0, 5, 9, 0, 0)));
const font = await doc.embedFont(StandardFonts.Helvetica);
const bold = await doc.embedFont(StandardFonts.HelveticaBold);
const W = 842;
const H = 595;
const ink = rgb(0.1, 0.1, 0.12);

function plan(page, title, sheetNo, level, rooms) {
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
