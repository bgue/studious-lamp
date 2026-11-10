// The PDF report of markup sets: per set a clean view (page 1), the same view with the markups burned in and numbered
// (page 2), and the comment table (one or more pages); every page has a header and a footer, page 1 carries the "how to
// get back to this view" block, and the JSON of the sets is attached so dropping the PDF onto the viewer restores
// everything. Pure (images come in as JPEG bytes): tested in node, rendered by the markup controller in the browser.

import { PdfDocument, textWidth, wrapPdfText } from './pdf';
import type { PdfImage, PdfPage, Rgb } from './pdf';
import { COLOURS, KIND_LABEL, setCounts } from './model';
import type { MarkupSet, ModelIdentity } from './model';

export type PageSize = 'A4' | 'Letter';
/** Landscape page sizes in points. */
export const PAGE_SIZES: Record<PageSize, { w: number; h: number }> = { A4: { w: 841.89, h: 595.28 }, Letter: { w: 792, h: 612 } };

export interface ReportImage {
  bytes: Uint8Array;
  width: number;
  height: number;
}

export interface ReportSet {
  set: MarkupSet;
  /** The model view at the set's camera, without markups. */
  clean: ReportImage;
  /** The same view with the markups burned in and numbered. */
  marked: ReportImage;
  /** A share link of the view when it fits (http or https pages). */
  link?: string;
}

export interface ReportOptions {
  page: PageSize;
  model: ModelIdentity;
  projectName?: string;
  /** Who exports (the remembered author). */
  author: string;
  date: Date;
  /** The JSON document that is attached (bytes exactly as written). */
  json: Uint8Array;
  jsonName: string;
}

const INK: Rgb = [0.1, 0.1, 0.12];
const DIM: Rgb = [0.4, 0.42, 0.46];
const LINE: Rgb = [0.78, 0.8, 0.84];
const BAND: Rgb = [0.94, 0.95, 0.97];
const LINK: Rgb = [0.1, 0.35, 0.8];
const MARGIN = 36;

/** The box (points) that the picture of page 2 is fitted into: the largest picture of a page. */
export function pictureBox(page: PageSize): { x: number; y: number; w: number; h: number } {
  const { w: W, h: H } = PAGE_SIZES[page];
  const top = H - MARGIN - 58;
  return { x: MARGIN, y: MARGIN + 14, w: W - 2 * MARGIN, h: top - (MARGIN + 14) };
}

/** Pixels the picture of page 2 needs for `dpi` when the picture has the aspect w : h. */
export function pictureWidthFor(page: PageSize, aspectW: number, aspectH: number, dpi: number): number {
  const f = fitImage(aspectW, aspectH, pictureBox(page));
  return Math.round((f.w / 72) * dpi);
}

function rgb(hex: string): Rgb {
  const n = parseInt(hex.slice(1), 16);
  return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255];
}

export function formatDate(d: Date): string {
  const p = (n: number): string => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}
function shortDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : formatDate(d);
}

/** The "how to get back to this view" lines, as written in the PDF. */
export function howToLines(hasLink: boolean, jsonName: string): string[] {
  const lines = [
    '1. Open the same model in the X-ray viewer.',
    `2. Drop this PDF, or the file ${jsonName} that is attached to it, onto the viewer window. You can also use Open file in the Markup tool.`,
    '3. The viewer restores the camera, the section, the hidden and coloured elements and the markups.',
  ];
  if (hasLink) lines.push('You can also click the link below. It opens the view only; the markups come from the file.');
  return lines;
}

/** Fit an image of w x h inside a box, centred. */
export function fitImage(w: number, h: number, box: { x: number; y: number; w: number; h: number }): { x: number; y: number; w: number; h: number } {
  const s = Math.min(box.w / w, box.h / h);
  const iw = w * s;
  const ih = h * s;
  return { x: box.x + (box.w - iw) / 2, y: box.y + (box.h - ih) / 2, w: iw, h: ih };
}

interface Footer {
  page: PdfPage;
  label: string;
}

const COLS: Array<{ title: string; frac: number }> = [
  { title: 'No', frac: 0.04 },
  { title: 'Type', frac: 0.08 },
  { title: 'Text', frac: 0.19 },
  { title: 'Status', frac: 0.06 },
  { title: 'Author', frac: 0.14 },
  { title: 'Assigned to / due', frac: 0.1 },
  { title: 'Comments', frac: 0.39 },
];

export function buildReport(items: readonly ReportSet[], o: ReportOptions): Uint8Array {
  const doc = new PdfDocument();
  const size = PAGE_SIZES[o.page];
  const W = size.w;
  const H = size.h;
  const first = items[0]?.set;
  doc.info = {
    title: items.length === 1 ? `${first!.title} (markup)` : `${o.model.name} markup, ${items.length} sets`,
    author: o.author || undefined,
    subject: `Markup of ${o.model.name}`,
    creator: 'X-ray mode for BIM reference viewer',
    keywords: 'markup, BIM, xray-markup-set',
    created: o.date,
  };
  const footers: Footer[] = [];
  const images = new Map<ReportImage, PdfImage>();
  const img = (i: ReportImage): PdfImage => {
    let v = images.get(i);
    if (!v) { v = doc.addJpeg(i.bytes, { width: i.width, height: i.height }); images.set(i, v); }
    return v;
  };

  const header = (page: PdfPage, set: MarkupSet, sub: string): void => {
    const top = H - MARGIN;
    const model = o.projectName ? `${o.projectName}  |  ${o.model.name}` : o.model.name;
    const right = formatDate(o.date);
    page.text(MARGIN, top - 9, fit(model, W - 2 * MARGIN - textWidth(right, 8.5) - 12, 9, true), { size: 9, bold: true, color: DIM });
    page.text(W - MARGIN - textWidth(right, 8.5), top - 9, right, { size: 8.5, color: DIM });
    page.text(MARGIN, top - 30, fit(set.title, W - 2 * MARGIN, 16, true), { size: 16, bold: true, color: INK });
    const by = `${sub}   |   by ${o.author || set.author}   |   ${setCountsText(set)}`;
    page.text(MARGIN, top - 44, fit(by, W - 2 * MARGIN, 8.5), { size: 8.5, color: DIM });
    page.line(MARGIN, top - 51, W - MARGIN, top - 51, { width: 0.6, color: LINE });
  };
  const footer = (page: PdfPage, label: string): void => {
    page.line(MARGIN, MARGIN + 6, W - MARGIN, MARGIN + 6, { width: 0.6, color: LINE });
    footers.push({ page, label });
  };
  const IMG_TOP = H - MARGIN - 58;

  for (const it of items) {
    const set = it.set;
    const hasLink = !!it.link;
    const how = howToLines(hasLink, o.jsonName);
    const howW = W - 2 * MARGIN;

    // ---- page 1: clean view + how to get back
    {
      const p = doc.addPage(W, H);
      header(p, set, 'Model view, no markups');
      // The how-to block sits under the image.
      const wrapped = how.flatMap((l) => wrapPdfText(l, howW - 16, 8.5));
      const blockH = 14 + wrapped.length * 11 + (hasLink ? 14 : 0) + 8;
      const imgBox = { x: MARGIN, y: MARGIN + 14 + blockH, w: W - 2 * MARGIN, h: IMG_TOP - (MARGIN + 14 + blockH) };
      const r = fitImage(it.clean.width, it.clean.height, imgBox);
      p.rect(r.x - 0.5, r.y - 0.5, r.w + 1, r.h + 1, { stroke: LINE, lineWidth: 0.5 });
      p.image(img(it.clean), r.x, r.y, r.w, r.h);
      let y = MARGIN + 14 + blockH - 14;
      p.rect(MARGIN, MARGIN + 12, howW, blockH, { fill: BAND });
      p.text(MARGIN + 8, y, 'How to get back to this view', { size: 9.5, bold: true, color: INK });
      for (const l of wrapped) { y -= 11; p.text(MARGIN + 8, y, l, { size: 8.5, color: INK }); }
      if (hasLink) {
        y -= 14;
        const label = 'Open this view in the viewer (link)';
        p.text(MARGIN + 8, y, label, { size: 8.5, color: LINK });
        p.line(MARGIN + 8, y - 1.5, MARGIN + 8 + textWidth(label, 8.5), y - 1.5, { width: 0.5, color: LINK });
        p.link(MARGIN + 8, y - 3, textWidth(label, 8.5), 12, it.link!);
      }
      footer(p, `${set.title}, view without markups`);
    }

    // ---- page 2: markups burned in
    {
      const p = doc.addPage(W, H);
      header(p, set, 'Same view with the markups, numbered as in the table');
      const imgBox = pictureBox(o.page);
      const r = fitImage(it.marked.width, it.marked.height, imgBox);
      p.rect(r.x - 0.5, r.y - 0.5, r.w + 1, r.h + 1, { stroke: LINE, lineWidth: 0.5 });
      p.image(img(it.marked), r.x, r.y, r.w, r.h);
      footer(p, `${set.title}, markups`);
    }

    // ---- comment table
    table(doc, set, o, W, H, header, footer);
  }

  // Page numbers.
  const total = doc.pages.length;
  footers.forEach((f) => {
    const n = doc.pages.indexOf(f.page) + 1;
    const right = `Page ${n} of ${total}`;
    f.page.text(MARGIN, MARGIN - 6, fit(f.label, W - 2 * MARGIN - 80, 8), { size: 8, color: DIM });
    f.page.text(W - MARGIN - textWidth(right, 8), MARGIN - 6, right, { size: 8, color: DIM });
  });
  doc.attach(o.jsonName, o.json, 'application/json', 'X-ray markup set: drop it on the viewer to restore the view and the markups');
  return doc.build();
}

function setCountsText(s: MarkupSet): string {
  const c = setCounts(s);
  return `${c.total} markup${c.total === 1 ? '' : 's'}, ${c.open} open, ${c.resolved} resolved`;
}

/** Cut a one-line text to a width with an ellipsis. */
function fit(text: string, maxW: number, size: number, bold = false): string {
  const t = text.replace(/\s+/g, ' ');
  if (textWidth(t, size, bold) <= maxW) return t;
  let k = t.length;
  while (k > 1 && textWidth(`${t.slice(0, k)}...`, size, bold) > maxW) k--;
  return `${t.slice(0, k)}...`;
}

function table(
  doc: PdfDocument,
  set: MarkupSet,
  o: ReportOptions,
  W: number,
  H: number,
  header: (p: PdfPage, set: MarkupSet, sub: string) => void,
  footer: (p: PdfPage, label: string) => void,
): void {
  const FS = 8;
  const LH = 10.5;
  const PAD = 3;
  const tw = W - 2 * MARGIN;
  const cols = COLS.map((c) => ({ ...c, w: c.frac * tw }));
  const xs: number[] = [];
  let x = MARGIN;
  for (const c of cols) { xs.push(x); x += c.w; }
  const bottom = MARGIN + 16;
  let page: PdfPage | null = null;
  let y = 0;
  let pageNo = 0;

  const newPage = (): void => {
    pageNo++;
    page = doc.addPage(W, H);
    header(page, set, pageNo === 1 ? 'Comment table' : 'Comment table, continued');
    footer(page, `${set.title}, comment table`);
    y = H - MARGIN - 62;
    page.rect(MARGIN, y - 12, tw, 16, { fill: BAND });
    cols.forEach((c, i) => page!.text(xs[i]! + PAD, y - 7, c.title, { size: FS, bold: true, color: INK }));
    y -= 16;
  };
  newPage();

  if (!set.markups.length) {
    page!.text(MARGIN + PAD, y - 12, 'This set has no markups.', { size: 9, color: DIM });
    y -= 24;
  }

  for (const m of set.markups) {
    const text = wrapPdfText(m.text || '-', cols[2]!.w - 2 * PAD, FS);
    const type = [KIND_LABEL[m.kind]];
    const who = wrapPdfText(m.author, cols[4]!.w - 2 * PAD, FS);
    const asg = wrapPdfText([m.assignee ? m.assignee : '-', m.due ? `due ${m.due}` : ''].filter(Boolean).join('\n'), cols[5]!.w - 2 * PAD, FS);
    const comments = m.comments.flatMap((c, i) => {
      const head = `${c.author}, ${shortDate(c.date)}:`;
      return [...(i ? [''] : []), `${head} ${c.text}`].flatMap((l) => wrapPdfText(l, cols[6]!.w - 2 * PAD, FS));
    });
    const status = [m.status === 'resolved' ? 'Resolved' : 'Open'];
    const lines: string[][] = [[], type, text, status, who, asg, comments.length ? comments : ['-']];
    let from = 0;
    const rows = Math.max(...lines.map((l) => l.length), 1);
    while (from < rows) {
      const avail = Math.floor((y - bottom - PAD) / LH);
      if (avail < 2 && from < rows) { newPage(); continue; }
      const n = Math.min(rows - from, avail);
      const h = n * LH + 2 * PAD;
      const p = page!;
      if (from === 0) {
        const cx = xs[0]! + PAD + 7;
        p.circle(cx, y - PAD - 5, 7, { fill: rgb(COLOURS[m.colour]) });
        const label = String(m.number);
        p.text(cx - textWidth(label, 7.5, true) / 2, y - PAD - 7.6, label, { size: 7.5, bold: true, color: m.colour === 'yellow' ? [0.1, 0.1, 0.1] : [1, 1, 1] });
      }
      lines.forEach((col, ci) => {
        if (ci === 0) return;
        for (let k = 0; k < n; k++) {
          const t = col[from + k];
          if (t) p.text(xs[ci]! + PAD, y - PAD - 7.2 - k * LH, t, { size: FS, color: ci === 3 && m.status === 'resolved' ? [0.1, 0.5, 0.25] : INK });
        }
      });
      p.line(MARGIN, y - h, MARGIN + tw, y - h, { width: 0.4, color: LINE });
      y -= h;
      from += n;
      if (from < rows) newPage();
    }
  }
  void o;
}
