import { describe, expect, it } from 'vitest';
import { PDFArray, PDFDict, PDFDocument, PDFName, PDFString } from 'pdf-lib';
import { ISSUE_CSV_HEADER, buildReportModel, commentText, filterText, issueCsvRow, issuesCsv, reportFileName, topicTargets } from '../src/issues/reportModel';
import type { ReportIssue, ReportModel } from '../src/issues/reportModel';
import { MAX_TARGETS, REPORT_PAGES, buildIssueReport, coverCapacity, ellipsize } from '../src/issues/reportPdf';
import type { IssueImages } from '../src/issues/reportPdf';
import type { ReportImage } from '../src/markup/report';
import type { BcfTopic } from '../src/bcf/model';
import { clashRef } from '../src/issues/clash';

const jpeg = (w: number, h: number): ReportImage => ({ bytes: new Uint8Array([0xff, 0xd8, 0xff, 0xc0, 0, 17, 8, h >> 8, h & 255, w >> 8, w & 255, 3, 1, 0x22, 0, 2, 0x11, 1, 3, 0x11, 1, 0xff, 0xd9]), width: w, height: h });
const text = (b: Uint8Array): string => Array.from(b, (c) => String.fromCharCode(c)).join('');
const G1 = '2O2Fr$t4X7Zf8NOew3FLOH';
const G2 = '3cUkl32yn9qRSPvBJVyWYp';

function topic(n: number, o: Partial<BcfTopic> = {}): BcfTopic {
  return {
    guid: `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`, topicType: 'Issue', topicStatus: n % 2 ? 'Open' : 'Closed', title: `Issue number ${n}`,
    labels: ['clash'], referenceLinks: [], creationDate: '2026-01-02T10:00:00.000Z', creationAuthor: 'Ana', headerFiles: [], documentReferences: [], relatedTopics: [],
    comments: [], viewpoints: [], ...o,
  };
}

const isOpen = (s: string): boolean => !/^(closed|resolved)$/i.test(s);
const resolve = (g: string): { name: string; ifcClass: string } | null => (g === G1 ? { name: 'Duct-12', ifcClass: 'IfcDuctSegment' } : g === G2 ? { name: 'Wall-3', ifcClass: 'IfcWall' } : null);

function model(topics: BcfTopic[], extra: Partial<Parameters<typeof buildReportModel>[0]> = {}): ReportModel {
  return buildReportModel({ topics, modelName: 'fzk-haus.ifc', projectName: 'Haus', filter: 'All issues', date: new Date(2026, 0, 5, 9, 30), resolve, isOpen, tied: () => false, ...extra });
}

describe('report model', () => {
  it('counts by status, open and closed', () => {
    const m = model([topic(1), topic(2), topic(3), topic(4, { topicStatus: 'In Progress' })]);
    expect(m.counts.total).toBe(4);
    expect(m.counts.open).toBe(3);
    expect(m.counts.closed).toBe(1);
    expect(m.counts.byStatus.map((s) => [s.status, s.count])).toEqual([['Open', 2], ['In Progress', 1], ['Closed', 1]]);
    expect(m.issues.map((i) => i.number)).toEqual([1, 2, 3, 4]);
  });

  it('names the target elements: the check pair, the selection, the annotations and the pin, once each', () => {
    const t = topic(1, {
      clash: clashRef('penetration', G2, G1),
      viewpoints: [{ guid: 'v1', data: { guid: 'v1', camera: null, selection: [{ ifcGuid: G1 }, { ifcGuid: 'unknownguid00000000000' }], visibility: null, coloring: [], clipping: [], lines: [] } }],
      pin: { position: [0, 0, 0], elementGuid: G2 },
    });
    expect(topicTargets(t)).toEqual([G1, G2, 'unknownguid00000000000']);
    const i = model([t]).issues[0]!;
    expect(i.targets).toEqual([
      { globalId: G1, name: 'Duct-12', ifcClass: 'IfcDuctSegment' },
      { globalId: G2, name: 'Wall-3', ifcClass: 'IfcWall' },
      { globalId: 'unknownguid00000000000', name: '', ifcClass: '' },
    ]);
    expect(i.clash).toEqual({ check: 'penetration', missing: false });
  });

  it('carries the comments with their authors, the sheet of a sheet issue and no Plan/Section for it', () => {
    const t = topic(1, {
      comments: [{ guid: 'c1', date: '2026-01-03T08:00:00.000Z', author: 'Ben', text: 'Looks wrong' }, { guid: 'c2', date: '2026-01-04T08:00:00.000Z', author: '', text: 'Fixed' }],
      viewpoints: [{ guid: 'v1', data: null, sheet: { sha256: 'x', page: 2, name: 'Plan, page 2', docName: 'plans.pdf', bounds: [0, 0, 1, 1] } }],
    });
    const i = model([t], { tied: () => true }).issues[0]!;
    expect(i.comments.map((c) => c.author)).toEqual(['Ben', 'unknown']);
    expect(i.sheet).toEqual({ name: 'Plan, page 2', docName: 'plans.pdf', page: 2 });
    expect(i.tied).toBe(false);
  });

  it('says the filter in words', () => {
    expect(filterText({ status: 'all', query: '' })).toBe('All issues');
    expect(filterText({ status: 'open', query: ' pipe ' })).toBe('Open issues, search "pipe"');
    expect(filterText({ status: 'closed', query: '' })).toBe('Closed issues');
  });

  it('names the files by model and time', () => {
    expect(reportFileName('Küche model.ifc', new Date(2026, 0, 5, 9, 30), 'pdf')).toBe('xray-issues-K_che_model-20260105-0930.pdf');
    expect(reportFileName('', new Date(2026, 0, 5, 9, 30), 'csv')).toBe('xray-issues-model-20260105-0930.csv');
  });
});

describe('issues CSV', () => {
  const issue = (o: Partial<ReportIssue> = {}): ReportIssue => ({ ...model([topic(1)]).issues[0]!, ...o });

  it('has the header and one row per issue, CRLF separated', () => {
    const csv = issuesCsv(model([topic(1), topic(2), topic(3)]));
    const lines = csv.split('\r\n');
    expect(lines[0]).toBe(ISSUE_CSV_HEADER.join(','));
    expect(lines.length).toBe(5); // header, 3 rows, trailing empty
    expect(lines[4]).toBe('');
  });

  it('quotes commas, quotes and line breaks, and doubles the quotes', () => {
    const row = issueCsvRow(issue({ title: 'Duct, "big" one', description: 'line 1\nline 2' }));
    expect(row[2]).toBe('Duct, "big" one');
    const csv = issuesCsv({ ...model([topic(1)]), issues: [issue({ title: 'Duct, "big" one', description: 'line 1\nline 2' })] });
    expect(csv).toContain('"Duct, ""big"" one"');
    expect(csv).toContain('"line 1\nline 2"');
  });

  it('guards a text that a spreadsheet would read as a formula', () => {
    const csv = issuesCsv({ ...model([topic(1)]), issues: [issue({ title: '=HYPERLINK("http://x")', assignee: '@ana', description: '-1+1' })] });
    expect(csv).toContain(`"'=HYPERLINK(""http://x"")"`);
    expect(csv).toContain(",'@ana,");
    expect(csv).toContain(",'-1+1,");
  });

  it('puts every comment with its author in one Comments column, and the count beside it', () => {
    const i = issue({ comments: [{ author: 'Ben', date: '2026-01-03', text: 'one, two' }, { author: 'Ana', date: '2026-01-04', text: 'three' }] });
    const row = issueCsvRow(i);
    const h = [...ISSUE_CSV_HEADER];
    expect(row[h.indexOf('Comment count')]).toBe(2);
    expect(row[h.indexOf('Comments')]).toBe('Ben (2026-01-03): one, two\nAna (2026-01-04): three');
    expect(commentText(i.comments[0]!)).toBe('Ben (2026-01-03): one, two');
    expect(row.length).toBe(ISSUE_CSV_HEADER.length);
  });

  it('lists labels, element names, GlobalIds and the raising check', () => {
    const t = topic(1, { labels: ['clash', 'penetration'], clash: { ...clashRef('penetration', G1, G2), missing: '2026-02-01T00:00:00.000Z' } });
    const row = issueCsvRow(model([t]).issues[0]!);
    const h = [...ISSUE_CSV_HEADER];
    expect(row[h.indexOf('Labels')]).toBe('clash; penetration');
    expect(row[h.indexOf('Elements')]).toBe('Duct-12; Wall-3');
    expect(row[h.indexOf('GlobalIds')]).toBe(`${G1}; ${G2}`);
    expect(row[h.indexOf('Raised from')]).toBe('penetration (not found in latest run)');
  });
});

// ---------------------------------------------------------------- PDF

async function open(bytes: Uint8Array): Promise<PDFDocument> {
  return PDFDocument.load(bytes);
}

function links(pdf: PDFDocument, pageIndex: number): Array<{ uri?: string; dest?: number }> {
  const page = pdf.getPage(pageIndex);
  const annots = page.node.Annots();
  const out: Array<{ uri?: string; dest?: number }> = [];
  if (!annots) return out;
  const pages = pdf.getPages();
  for (let i = 0; i < annots.size(); i++) {
    const a = annots.lookup(i, PDFDict);
    expect(a.get(PDFName.of('Subtype'))).toBe(PDFName.of('Link'));
    const act = a.lookup(PDFName.of('A'), PDFDict);
    const uri = act.get(PDFName.of('URI'));
    if (uri instanceof PDFString) { out.push({ uri: uri.decodeText() }); continue; }
    const d = act.lookup(PDFName.of('D'), PDFArray);
    const ref = d.get(0);
    out.push({ dest: pages.findIndex((p) => p.ref === ref) });
  }
  return out;
}

function build(n: number, o: { page?: 'A4' | 'Letter'; images?: boolean; comments?: number; mut?: (t: BcfTopic, i: number) => void } = {}): { bytes: Uint8Array; m: ReportModel } {
  const topics = Array.from({ length: n }, (_, k) => {
    const t = topic(k + 1, {
      description: 'The duct passes through the wall without an opening. '.repeat(3),
      assignedTo: 'Carla', dueDate: '2026-03-01', priority: k % 3 === 0 ? 'High' : 'Normal',
      comments: Array.from({ length: o.comments ?? 2 }, (_, c) => ({ guid: `c${k}-${c}`, date: '2026-01-03T08:00:00.000Z', author: c % 2 ? 'Ben Baumeister' : 'Åsa Örn', text: `Comment ${c + 1} about (the) duct \\ wall.` })),
      clash: clashRef('penetration', G1, G2),
    });
    o.mut?.(t, k);
    return t;
  });
  const m = model(topics, { tied: () => true });
  const images = new Map<string, IssueImages>();
  if (o.images !== false) for (const i of m.issues) images.set(i.guid, { snapshot: jpeg(1280, 720), plan: jpeg(640, 400), section: jpeg(640, 400) });
  return { bytes: buildIssueReport(m, images, { page: o.page ?? 'A4', author: 'Ana' }), m };
}

describe('issue report PDF', () => {
  it('is a cover and one page per issue, readable by pdf-lib', async () => {
    const { bytes } = build(5);
    const pdf = await open(bytes);
    expect(pdf.getPageCount()).toBe(1 + 5);
    const { width, height } = pdf.getPage(0).getSize();
    expect(width).toBeCloseTo(REPORT_PAGES.A4.w, 1);
    expect(height).toBeGreaterThan(width); // portrait
    expect(pdf.getTitle()).toBe('Issue report - fzk-haus.ifc');
    expect(pdf.getAuthor()).toBe('Ana');
  });

  it('writes Letter pages when asked', async () => {
    const pdf = await open(build(2, { page: 'Letter' }).bytes);
    expect(pdf.getPage(1).getSize()).toEqual({ width: 612, height: 792 });
  });

  it('links each cover row to the page of its issue, and each issue page back to the cover', async () => {
    const { bytes, m } = build(4);
    const pdf = await open(bytes);
    const cover = links(pdf, 0);
    expect(cover.length).toBe(4);
    expect(cover.map((l) => l.dest)).toEqual([1, 2, 3, 4]);
    for (let k = 1; k <= m.issues.length; k++) expect(links(pdf, k)).toEqual([{ dest: 0 }]);
  });

  it('links to the right pages when the list is long and the cover runs over several pages', async () => {
    const cap = coverCapacity(REPORT_PAGES.A4.h);
    const n = cap.first + cap.rest + 3;
    const { bytes } = build(n, { images: false, comments: 0 });
    const pdf = await open(bytes);
    const coverPages = 3;
    expect(pdf.getPageCount()).toBe(coverPages + n);
    const all = [0, 1, 2].flatMap((p) => links(pdf, p).map((l) => l.dest));
    expect(all.length).toBe(n);
    expect(all).toEqual(Array.from({ length: n }, (_, k) => coverPages + k));
    // the back link of the first issue page goes to the first cover page
    expect(links(pdf, coverPages)).toEqual([{ dest: 0 }]);
  });

  it('continues an issue with a long thread on further pages, and the next issue still starts where its link points', async () => {
    const { bytes } = build(2, { comments: 60, mut: (t, k) => { if (k === 1) t.comments.length = 1; } });
    const pdf = await open(bytes);
    expect(pdf.getPageCount()).toBeGreaterThan(3);
    const cover = links(pdf, 0);
    expect(cover[0]!.dest).toBe(1);
    expect(cover[1]!.dest).toBe(pdf.getPageCount() - 1);
  });

  it('has an outline entry for the cover and each issue', async () => {
    const { bytes } = build(3);
    const pdf = await open(bytes);
    const outlines = pdf.catalog.lookup(PDFName.of('Outlines'), PDFDict);
    expect(outlines.get(PDFName.of('Count'))?.toString()).toBe('4');
    const s = text(bytes);
    expect(s).toContain('(Cover)');
    expect(s).toContain('(2. Issue number 2)');
  });

  it('embeds the pictures: a snapshot, a Plan and a Section per issue, once per picture', () => {
    const { bytes } = build(3);
    const s = text(bytes);
    expect((s.match(/\/Subtype \/Image/g) ?? []).length).toBe(9);
    expect((s.match(/ Do Q/g) ?? []).length).toBe(9);
    const none = text(build(3, { images: false }).bytes);
    expect(none).not.toContain('/Subtype /Image');
  });

  it('writes the fields, the description, the comments with their authors and the elements', () => {
    const s = text(build(1).bytes);
    expect(s).toContain('(Issue report) Tj');
    expect(s).toContain('(fzk-haus.ifc) Tj');
    expect(s).toContain('Project: Haus');
    expect(s).toContain('Made 2026-01-05 09:30 by Ana');
    expect(s).toContain('Showing: All issues');
    expect(s).toContain('(Carla) Tj');
    expect(s).toContain('(2026-03-01) Tj');
    expect(s).toContain('The duct passes through the wall');
    expect(s).toContain('\\305sa \\326rn'); // Åsa Örn in WinAnsi octal escapes
    expect(s).toContain('Ben Baumeister');
    expect(s).toContain('Comment 1 about \\(the\\) duct \\\\ wall.');
    expect(s).toContain('(Duct-12) Tj');
    expect(s).toContain(`(${G1}) Tj`);
    expect(s).toContain('(Comments \\(2\\)) Tj');
    expect(s).toContain('(Views) Tj');
    expect(s).toContain('(Plan) Tj');
    expect(s).toContain('(Section) Tj');
  });

  it('names the sheet and its region for a sheet issue, with no Plan and Section', () => {
    const { bytes } = build(1, {
      mut: (t) => { t.viewpoints = [{ guid: 'v1', data: null, sheet: { sha256: 'x', page: 3, name: 'Level 2 plan', docName: 'plans.pdf', bounds: [0, 0, 10, 10] } }]; },
    });
    const s = text(bytes);
    expect(s).toContain('(Sheet) Tj');
    expect(s).toContain('Level 2 plan \\(plans.pdf\\), page 3');
  });

  it('puts "Page n of N" on every page', () => {
    const s = text(build(2).bytes);
    for (let k = 1; k <= 3; k++) expect(s).toContain(`(Page ${k} of 3) Tj`);
  });

  it('counts the elements beyond the list limit', () => {
    const many = Array.from({ length: MAX_TARGETS + 5 }, (_, i) => ({ guid: `g${String(i).padStart(3, '0')}`.padEnd(22, 'x') }));
    const s = text(build(1, { mut: (t) => { t.viewpoints = [{ guid: 'v1', data: { guid: 'v1', camera: null, selection: many.map((m) => ({ ifcGuid: m.guid })), visibility: null, coloring: [], clipping: [], lines: [] } }]; } }).bytes);
    expect(s).toContain(`Elements \\(${MAX_TARGETS + 5 + 2}\\)`); // plus the check pair
    expect(s).toContain('and 7 more');
  });

  it('handles an empty list', async () => {
    const m = model([]);
    const pdf = await open(buildIssueReport(m, new Map(), { page: 'A4' }));
    expect(pdf.getPageCount()).toBe(1);
    expect(text(buildIssueReport(m, new Map(), { page: 'A4' }))).toContain('No issue matches the filter.');
  });
});

describe('ellipsize', () => {
  it('keeps a short text and cuts a long one to the width', () => {
    expect(ellipsize('Short', 200, 9)).toBe('Short');
    const cut = ellipsize('A very long title that does not fit in a narrow column at all', 60, 9);
    expect(cut.endsWith('...')).toBe(true);
    expect(cut.length).toBeLessThan(30);
  });
});
