// The issue report, the pure part: what a report says about the issues of the Issues tab (the report model), and the CSV of it. The
// PDF is laid out from the same model (reportPdf.ts); the pictures are rendered in the browser (reportRender.ts). No DOM, no
// three.js. Tested in tests/issues-report.test.ts. Docs: docs-features/issues.md.
//
// CSV: one file, one row per issue, with a Comments column that holds every comment ("author (date): text", one per line inside
// the cell). One file opens in a spreadsheet as it is; a second file of comments would have to be joined by hand.

import { annotationGuids } from '../bcf/sidecar';
import type { BcfTopic } from '../bcf/model';
import { toCsv } from '../tools/csv';
import type { CsvCell } from '../tools/csv';

export interface ReportTarget {
  globalId: string;
  /** Empty when the loaded model has no such element. */
  name: string;
  ifcClass: string;
}

export interface ReportComment {
  author: string;
  date: string;
  text: string;
}

export interface ReportIssue {
  guid: string;
  /** 1-based, in report order: the number on the cover and on the page. */
  number: number;
  title: string;
  status: string;
  open: boolean;
  priority: string;
  type: string;
  assignee: string;
  due: string;
  labels: string[];
  description: string;
  created: string;
  createdBy: string;
  modified: string;
  modifiedBy: string;
  comments: ReportComment[];
  targets: ReportTarget[];
  /** The sketch of the issue is tied to the model (so it has a Plan and a Section). Sheet issues are never tied. */
  tied: boolean;
  /** An issue made on a PDF drawing sheet: the sheet name, its file and page. */
  sheet: { name: string; docName: string; page: number } | null;
  /** The check an issue was raised from, when it was. */
  clash: { check: string; missing: boolean } | null;
}

export interface ReportModel {
  /** The model name the issues belong to. */
  modelName: string;
  projectName: string;
  /** When the report was made. */
  date: Date;
  /** The filter of the list the report was made from, in words ("All issues", "Open issues, search "pipe""). */
  filter: string;
  issues: ReportIssue[];
  counts: { total: number; open: number; closed: number; byStatus: Array<{ status: string; count: number; open: boolean }> };
}

export interface ReportSource {
  topics: readonly BcfTopic[];
  modelName: string;
  projectName?: string;
  filter: string;
  date: Date;
  /** Name and class of an element by GlobalId, or null when the model has none. */
  resolve(globalId: string): { name: string; ifcClass: string } | null;
  /** The status counts as open. */
  isOpen(status: string): boolean;
  /** The sketch of the issue is tied to the model. */
  tied(topic: BcfTopic): boolean;
}

/** The elements an issue points at: its check pair, the selection of its viewpoints, what its drawings are attached to, its pin. Each once. */
export function topicTargets(t: BcfTopic): string[] {
  const out = new Set<string>();
  if (t.clash) { out.add(t.clash.a); out.add(t.clash.b); }
  for (const v of t.viewpoints) {
    for (const c of v.data?.selection ?? []) if (c.ifcGuid) out.add(c.ifcGuid);
    for (const g of annotationGuids(v.annotations)) out.add(g);
  }
  if (t.pin?.elementGuid) out.add(t.pin.elementGuid);
  return [...out];
}

export function buildReportModel(src: ReportSource): ReportModel {
  const issues: ReportIssue[] = src.topics.map((t, i) => {
    const sheetVp = t.viewpoints.find((v) => v.sheet);
    return {
      guid: t.guid,
      number: i + 1,
      title: t.title,
      status: t.topicStatus,
      open: src.isOpen(t.topicStatus),
      priority: t.priority ?? '',
      type: t.topicType,
      assignee: t.assignedTo ?? '',
      due: (t.dueDate ?? '').slice(0, 10),
      labels: [...t.labels],
      description: t.description ?? '',
      created: t.creationDate,
      createdBy: t.creationAuthor,
      modified: t.modifiedDate ?? '',
      modifiedBy: t.modifiedAuthor ?? '',
      comments: t.comments.map((c) => ({ author: c.author || 'unknown', date: c.date, text: c.text })),
      targets: topicTargets(t).map((g) => {
        const r = src.resolve(g);
        return { globalId: g, name: r?.name ?? '', ifcClass: r?.ifcClass ?? '' };
      }),
      tied: !sheetVp && src.tied(t),
      sheet: sheetVp?.sheet ? { name: sheetVp.sheet.name, docName: sheetVp.sheet.docName, page: sheetVp.sheet.page } : null,
      clash: t.clash ? { check: t.clash.check, missing: !!t.clash.missing } : null,
    };
  });
  const by = new Map<string, { status: string; count: number; open: boolean }>();
  for (const i of issues) {
    const e = by.get(i.status) ?? { status: i.status, count: 0, open: i.open };
    e.count++;
    by.set(i.status, e);
  }
  const open = issues.filter((i) => i.open).length;
  return {
    modelName: src.modelName,
    projectName: src.projectName ?? '',
    date: src.date,
    filter: src.filter,
    issues,
    // Open statuses first, then by count.
    counts: { total: issues.length, open, closed: issues.length - open, byStatus: [...by.values()].sort((a, b) => Number(b.open) - Number(a.open) || b.count - a.count || a.status.localeCompare(b.status)) },
  };
}

/** The filter of the list in words. */
export function filterText(f: { status: 'all' | 'open' | 'closed'; query: string }): string {
  const s = f.status === 'all' ? 'All issues' : f.status === 'open' ? 'Open issues' : 'Closed issues';
  const q = f.query.trim();
  return q ? `${s}, search "${q}"` : s;
}

// ---------------------------------------------------------------- CSV

export const ISSUE_CSV_HEADER = [
  'Number', 'GUID', 'Title', 'Status', 'Priority', 'Type', 'Assigned to', 'Due date', 'Labels', 'Created', 'Created by', 'Modified', 'Modified by',
  'Description', 'Comment count', 'Comments', 'Elements', 'GlobalIds', 'Sheet', 'Sheet page', 'Raised from',
] as const;

export function commentText(c: ReportComment): string {
  return `${c.author} (${c.date}): ${c.text}`;
}

export function issueCsvRow(i: ReportIssue): CsvCell[] {
  return [
    i.number, i.guid, i.title, i.status, i.priority, i.type, i.assignee, i.due, i.labels.join('; '), i.created, i.createdBy, i.modified, i.modifiedBy,
    i.description, i.comments.length, i.comments.map(commentText).join('\n'),
    i.targets.map((t) => t.name || t.globalId).join('; '), i.targets.map((t) => t.globalId).join('; '),
    i.sheet?.name ?? '', i.sheet?.page ?? '', i.clash ? `${i.clash.check}${i.clash.missing ? ' (not found in latest run)' : ''}` : '',
  ];
}

/** The CSV text (RFC 4180, CRLF, formula guard as the other tools) of the report's issues. */
export function issuesCsv(m: ReportModel): string {
  return toCsv(ISSUE_CSV_HEADER, m.issues.map(issueCsvRow));
}

const slug = (s: string): string => s.replace(/\.[a-z0-9]+$/i, '').replace(/[^\w.-]+/g, '_').replace(/^_+|_+$/g, '') || 'model';
const stamp = (d: Date): string => {
  const p = (n: number): string => String(n).padStart(2, '0');
  return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}`;
};
export function reportFileName(modelName: string, date: Date, ext: 'pdf' | 'csv'): string {
  return `xray-issues-${slug(modelName)}-${stamp(date)}.${ext}`;
}
