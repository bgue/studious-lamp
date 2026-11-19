// The PDF of the issue report, laid out from the report model with the hand-written writer (src/markup/pdf.ts). No DOM, no
// dependencies. Page 1 (and the pages after it when the list is long) is the cover: model, date, counts by status and a table
// of the issues, each row a link to the issue's page. Then one page per issue: title and fields, description, the snapshot, the
// Plan and Section when it has them, the elements, the sheet of a sheet issue, and the comments with their authors. An issue with
// a long thread continues on further pages. Tested in tests/issues-report.test.ts. Docs: docs-features/issues.md.

import { PdfDocument, textWidth, wrapPdfText } from '../markup/pdf';
import type { PdfImage, PdfPage, Rgb } from '../markup/pdf';
import { fitImage, formatDate } from '../markup/report';
import type { PageSize, ReportImage } from '../markup/report';
import type { ReportIssue, ReportModel } from './reportModel';

export type { PageSize };

/** Portrait page sizes in points. */
export const REPORT_PAGES: Record<PageSize, { w: number; h: number }> = { A4: { w: 595.28, h: 841.89 }, Letter: { w: 612, h: 792 } };

/** The pictures of one issue (JPEG bytes). */
export interface IssueImages {
  /** The snapshot of its view with the drawings, or of the sheet region. */
  snapshot?: ReportImage;
  plan?: ReportImage;
  section?: ReportImage;
}

export interface ReportPdfOptions {
  page: PageSize;
  /** Who made the report (the remembered author), for the Author field of the file. */
  author?: string;
}

const INK: Rgb = [0.1, 0.1, 0.12];
const DIM: Rgb = [0.4, 0.42, 0.46];
const LINE: Rgb = [0.78, 0.8, 0.84];
const BAND: Rgb = [0.94, 0.95, 0.97];
const LINK: Rgb = [0.1, 0.35, 0.8];
const OPEN: Rgb = [0.78, 0.5, 0.05];
const DONE: Rgb = [0.15, 0.55, 0.3];
const HIGH: Rgb = [0.75, 0.15, 0.15];
const MARGIN = 40;
const FOOT = 34;
/** Height of the row of pictures of an issue page. */
export const ROW_H = 190;
/** Elements listed per issue; the rest are counted. */
export const MAX_TARGETS = 24;

/** `text` cut with an ellipsis so that it fits `width` points. */
export function ellipsize(text: string, width: number, size: number, bold = false): string {
  const t = text.replace(/\s+/g, ' ').trim();
  if (textWidth(t, size, bold) <= width) return t;
  let k = t.length;
  while (k > 1 && textWidth(`${t.slice(0, k)}...`, size, bold) > width) k--;
  return `${t.slice(0, k).trimEnd()}...`;
}

/** The rows of the cover table that fit on a page of height `h`: the first page has the header block above the table. */
export function coverCapacity(h: number): { first: number; rest: number } {
  const row = 17;
  const first = Math.floor((h - MARGIN - 250 - FOOT - row) / row);
  const rest = Math.floor((h - MARGIN - 50 - FOOT - row) / row);
  return { first: Math.max(1, first), rest: Math.max(1, rest) };
}

class Flow {
  page!: PdfPage;
  y = 0;
  constructor(private readonly doc: PdfDocument, readonly W: number, readonly H: number, private readonly onNew: (p: PdfPage, cont: boolean) => number) {
    this.next(false);
  }
  next(cont: boolean): void {
    this.page = this.doc.addPage(this.W, this.H);
    this.y = this.onNew(this.page, cont);
  }
  /** Room for `h` points: a continuation page when there is not. */
  need(h: number): void {
    if (this.y - h < MARGIN + FOOT) this.next(true);
  }
  get left(): number {
    return MARGIN;
  }
  get width(): number {
    return this.W - 2 * MARGIN;
  }
}

function statusColour(i: Pick<ReportIssue, 'open' | 'status'>): Rgb {
  return i.open ? OPEN : DONE;
}

export function buildIssueReport(model: ReportModel, images: ReadonlyMap<string, IssueImages>, o: ReportPdfOptions): Uint8Array {
  const doc = new PdfDocument();
  const { w: W, h: H } = REPORT_PAGES[o.page];
  const when = formatDate(model.date);
  doc.info = {
    title: `Issue report - ${model.modelName}`,
    subject: model.filter,
    creator: 'X-ray mode for BIM reference viewer',
    created: model.date,
    ...(o.author ? { author: o.author } : {}),
  };

  // The JPEGs are registered once however many pages show them.
  const reg = new Map<ReportImage, PdfImage>();
  const image = (im: ReportImage): PdfImage => {
    let p = reg.get(im);
    if (!p) { p = doc.addJpeg(im.bytes, { width: im.width, height: im.height }); reg.set(im, p); }
    return p;
  };

  // ---------------------------------------------------------------- the cover
  const cap = coverCapacity(H);
  const coverRows: ReportIssue[][] = [];
  for (let i = 0; i < Math.max(1, model.issues.length); ) {
    const n = coverRows.length === 0 ? cap.first : cap.rest;
    coverRows.push(model.issues.slice(i, i + n));
    i += n;
  }
  const coverPages: PdfPage[] = [];
  const rowsOf: Array<{ page: PdfPage; y: number; issue: ReportIssue }> = [];
  const cols = [
    { title: '#', x: 0, w: 26 },
    { title: 'Title', x: 26, w: 0 }, // fills
    { title: 'Status', x: 0, w: 70 },
    { title: 'Priority', x: 0, w: 52 },
    { title: 'Assignee', x: 0, w: 78 },
    { title: 'Due', x: 0, w: 56 },
    { title: 'Page', x: 0, w: 30 },
  ];
  const tableW = W - 2 * MARGIN;
  cols[1]!.w = tableW - cols.reduce((a, c, k) => a + (k === 1 ? 0 : c.w), 0);
  let cx = 0;
  for (const c of cols) { c.x = cx; cx += c.w; }

  coverRows.forEach((rows, ci) => {
    const p = doc.addPage(W, H);
    coverPages.push(p);
    let y = H - MARGIN;
    if (ci === 0) {
      p.text(MARGIN, y - 20, 'Issue report', { size: 22, bold: true, color: INK });
      y -= 44;
      const m1 = ellipsize(model.modelName || 'Model', tableW, 13, true);
      p.text(MARGIN, y - 4, m1, { size: 13, bold: true, color: INK });
      y -= 20;
      if (model.projectName) { p.text(MARGIN, y - 2, ellipsize(`Project: ${model.projectName}`, tableW, 10), { size: 10, color: DIM }); y -= 15; }
      p.text(MARGIN, y - 2, `Made ${when}${o.author ? ` by ${o.author}` : ''}`, { size: 10, color: DIM });
      y -= 15;
      p.text(MARGIN, y - 2, ellipsize(`Showing: ${model.filter}`, tableW, 10), { size: 10, color: DIM });
      y -= 26;
      // Counts: total, open, closed, then a bar per status.
      p.text(MARGIN, y - 10, `${model.counts.total} issue${model.counts.total === 1 ? '' : 's'}`, { size: 14, bold: true, color: INK });
      p.text(MARGIN + 110, y - 10, `${model.counts.open} open`, { size: 11, bold: true, color: OPEN });
      p.text(MARGIN + 190, y - 10, `${model.counts.closed} closed`, { size: 11, bold: true, color: DONE });
      y -= 26;
      const max = Math.max(1, ...model.counts.byStatus.map((s) => s.count));
      for (const s of model.counts.byStatus.slice(0, 8)) {
        p.text(MARGIN, y - 8, ellipsize(s.status || 'No status', 110, 9), { size: 9, color: INK });
        const bw = ((tableW - 150) * s.count) / max;
        p.rect(MARGIN + 120, y - 9, Math.max(2, bw), 9, { fill: s.open ? OPEN : DONE });
        p.text(MARGIN + 126 + Math.max(2, bw), y - 8, String(s.count), { size: 9, bold: true, color: INK });
        y -= 14;
      }
      y -= 12;
    } else {
      p.text(MARGIN, y - 12, `Issues (continued)`, { size: 12, bold: true, color: INK });
      y -= 34;
    }
    // table head
    p.rect(MARGIN, y - 15, tableW, 15, { fill: BAND });
    for (const c of cols) p.text(MARGIN + c.x + 3, y - 11, c.title, { size: 8.5, bold: true, color: DIM });
    y -= 15;
    for (const i of rows) {
      const ry = y - 17;
      rowsOf.push({ page: p, y: ry, issue: i });
      const cell = (k: number, text: string, color: Rgb = INK, bold = false): void => p.text(MARGIN + cols[k]!.x + 3, ry + 5, ellipsize(text, cols[k]!.w - 6, 9, bold), { size: 9, bold, color });
      cell(0, String(i.number), DIM);
      cell(1, i.title, LINK);
      cell(2, i.status || '-', statusColour(i), true);
      cell(3, i.priority || '-', /high|critical|urgent|major/i.test(i.priority) ? HIGH : INK);
      cell(4, i.assignee || '-');
      cell(5, i.due || '-');
      p.line(MARGIN, ry, MARGIN + tableW, ry, { color: LINE, width: 0.4 });
      y = ry;
    }
    if (model.issues.length === 0) p.text(MARGIN + 3, y - 14, 'No issue matches the filter.', { size: 10, color: DIM });
  });

  // ---------------------------------------------------------------- the issue pages
  const firstPage = new Map<string, PdfPage>();
  for (const issue of model.issues) {
    const imgs = images.get(issue.guid) ?? {};
    const flow = new Flow(doc, W, H, (p, cont) => {
      let y = H - MARGIN;
      if (!cont) {
        firstPage.set(issue.guid, p);
        // The title band: number, wrapped title, the line of status, priority, assignee, due.
        const lines = wrapPdfText(issue.title || 'Untitled', W - 2 * MARGIN - 40, 15, true).slice(0, 3);
        const bh = 20 + lines.length * 19;
        p.rect(MARGIN - 8, y - bh, W - 2 * MARGIN + 16, bh, { fill: BAND });
        p.text(MARGIN, y - 15, `Issue ${issue.number}`, { size: 8.5, bold: true, color: DIM });
        const back = 'Back to the list';
        p.text(W - MARGIN - textWidth(back, 8.5), y - 15, back, { size: 8.5, color: LINK });
        p.linkToPage(W - MARGIN - textWidth(back, 8.5), y - 18, textWidth(back, 8.5), 12, coverPages[0]!);
        lines.forEach((l, k) => p.text(MARGIN, y - 33 - k * 19, l, { size: 15, bold: true, color: INK }));
        y -= bh + 12;
      } else {
        p.text(MARGIN, y - 10, ellipsize(`Issue ${issue.number}: ${issue.title} (continued)`, W - 2 * MARGIN, 9, true), { size: 9, bold: true, color: DIM });
        y -= 26;
      }
      return y;
    });
    const { left, width } = flow;

    const heading = (t: string): void => {
      flow.need(34);
      flow.page.text(left, flow.y - 10, t, { size: 10, bold: true, color: DIM });
      flow.page.line(left, flow.y - 14, left + width, flow.y - 14, { color: LINE, width: 0.5 });
      flow.y -= 24;
    };
    const paragraph = (t: string, size = 10, color: Rgb = INK, indent = 0): void => {
      for (const l of wrapPdfText(t, width - indent, size)) {
        flow.need(size + 4);
        flow.page.text(left + indent, flow.y - size, l, { size, color });
        flow.y -= size + 3.5;
      }
    };

    // fields, three columns
    const fields: Array<[string, string, Rgb?]> = [
      ['Status', issue.status || '-', statusColour(issue)],
      ['Priority', issue.priority || '-', /high|critical|urgent|major/i.test(issue.priority) ? HIGH : INK],
      ['Type', issue.type || '-'],
      ['Assigned to', issue.assignee || '-'],
      ['Due date', issue.due || '-'],
      ['Labels', issue.labels.join(', ') || '-'],
      ['Created', `${issue.createdBy || 'unknown'}, ${issue.created ? formatDate(new Date(issue.created)) : '-'}`],
      ['Last changed', issue.modified ? `${issue.modifiedBy || 'unknown'}, ${formatDate(new Date(issue.modified))}` : '-'],
    ];
    const colW = width / 3;
    for (let k = 0; k < fields.length; k += 3) {
      flow.need(30);
      for (let j = 0; j < 3; j++) {
        const f = fields[k + j];
        if (!f) continue;
        const x = left + j * colW;
        flow.page.text(x, flow.y - 8, f[0], { size: 8, color: DIM });
        flow.page.text(x, flow.y - 20, ellipsize(f[1], colW - 12, 10, f[0] === 'Status'), { size: 10, bold: f[0] === 'Status', color: f[2] ?? INK });
      }
      flow.y -= 28;
    }
    if (issue.clash) {
      paragraph(`Raised from a ${issue.clash.check} check${issue.clash.missing ? '. Not found in the latest run.' : '.'}`, 9, DIM);
      flow.y -= 6;
    }

    if (issue.description.trim()) {
      heading('Description');
      paragraph(issue.description);
      flow.y -= 4;
    }

    // pictures
    const place = (im: ReportImage, box: { x: number; y: number; w: number; h: number }): void => {
      const f = fitImage(im.width, im.height, box);
      flow.page.rect(f.x - 0.5, f.y - 0.5, f.w + 1, f.h + 1, { stroke: LINE, lineWidth: 0.5 });
      flow.page.image(image(im), f.x, f.y, f.w, f.h);
    };
    if (issue.sheet) {
      heading('Sheet');
      paragraph(`${issue.sheet.name} (${issue.sheet.docName}), page ${issue.sheet.page}`);
      flow.y -= 2;
    }
    if (imgs.snapshot || imgs.plan || imgs.section) {
      const side = !!(imgs.plan || imgs.section);
      heading(issue.sheet ? 'Region of the sheet' : side ? 'Views' : 'View');
      const rowH = ROW_H;
      const leftW = side ? Math.round(width * 0.58) : width;
      flow.need(rowH + 18);
      const top = flow.y;
      if (imgs.snapshot) {
        const f = fitImage(imgs.snapshot.width, imgs.snapshot.height, { x: 0, y: 0, w: leftW, h: rowH });
        place(imgs.snapshot, { x: left, y: top - f.h, w: f.w, h: f.h });
      }
      if (side) {
        // Plan above Section in the column right of the snapshot, each with its name under it.
        const x0 = left + leftW + 14;
        const bw = width - leftW - 14;
        const bh = (rowH - 2 * 11 - 8) / 2;
        const items: Array<[string, ReportImage | undefined]> = [['Plan', imgs.plan], ['Section', imgs.section]];
        items.forEach(([label, im], k) => {
          const oy = top - k * (bh + 11 + 8);
          if (!im) return;
          const f = fitImage(im.width, im.height, { x: 0, y: 0, w: bw, h: bh });
          place(im, { x: x0, y: oy - f.h, w: f.w, h: f.h });
          flow.page.text(x0, oy - f.h - 9, label, { size: 8, color: DIM });
        });
      }
      flow.y -= rowH + 12;
    }

    // elements
    if (issue.targets.length) {
      heading(`Elements (${issue.targets.length})`);
      const shown = issue.targets.slice(0, MAX_TARGETS);
      const w1 = width * 0.34;
      const w2 = width * 0.2;
      for (const t of shown) {
        flow.need(13);
        flow.page.text(left, flow.y - 9, ellipsize(t.name || '(not in this model)', w1 - 6, 8.5), { size: 8.5, color: INK });
        flow.page.text(left + w1, flow.y - 9, ellipsize(t.ifcClass.replace(/^Ifc/, '') || '-', w2 - 6, 8.5), { size: 8.5, color: DIM });
        flow.page.text(left + w1 + w2, flow.y - 9, t.globalId, { size: 8.5, color: DIM });
        flow.y -= 12;
      }
      if (issue.targets.length > shown.length) { paragraph(`and ${issue.targets.length - shown.length} more`, 8.5, DIM); }
      flow.y -= 6;
    }

    // comments
    if (issue.comments.length) {
      heading(`Comments (${issue.comments.length})`);
      for (const c of issue.comments) {
        flow.need(36);
        const d = c.date ? formatDate(new Date(c.date)) : '';
        flow.page.line(left, flow.y, left, flow.y - 12, { color: LINE, width: 1.5 });
        flow.page.text(left + 6, flow.y - 9, ellipsize(`${c.author}${d ? `, ${d}` : ''}`, width - 10, 8.5, true), { size: 8.5, bold: true, color: DIM });
        flow.y -= 14;
        paragraph(c.text || '(empty)', 10, INK, 6);
        flow.y -= 5;
      }
    }
  }

  // ---------------------------------------------------------------- links of the cover rows, bookmarks, footers
  for (const r of rowsOf) {
    const target = firstPage.get(r.issue.guid);
    if (!target) continue;
    r.page.linkToPage(MARGIN, r.y, tableW, 17, target);
    const n = doc.pages.indexOf(target) + 1;
    const lbl = String(n);
    r.page.text(MARGIN + cols[6]!.x + 3, r.y + 5, lbl, { size: 9, color: DIM });
  }
  doc.outline.push({ title: 'Cover', page: coverPages[0]! });
  for (const i of model.issues) {
    const p = firstPage.get(i.guid);
    if (p) doc.outline.push({ title: `${i.number}. ${i.title}`.slice(0, 120), page: p });
  }
  const total = doc.pages.length;
  doc.pages.forEach((p, k) => {
    p.line(MARGIN, FOOT, W - MARGIN, FOOT, { color: LINE, width: 0.4 });
    p.text(MARGIN, FOOT - 12, ellipsize(`Issue report, ${model.modelName}`, W - 2 * MARGIN - 80, 8), { size: 8, color: DIM });
    const t = `Page ${k + 1} of ${total}`;
    p.text(W - MARGIN - textWidth(t, 8), FOOT - 12, t, { size: 8, color: DIM });
  });
  return doc.build();
}
