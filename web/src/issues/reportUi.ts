// The "Export report" block of the Issues tab: page size, the Plan/Section option and the PDF and CSV buttons. It reports the list
// the segment shows now (status chip, search, this model). DOM only; the work is in reportRender.ts. The state outlives the panel's
// redraws (the panel is rebuilt on every change), so it lives here. Docs: docs-features/issues.md.

import { el } from '../ui/dom';
import { button, row } from '../tools/ui';
import type { IssuesController } from './controller';
import { issuesCsvOf, makeIssueReport } from './reportRender';
import type { ReportResult } from './reportRender';
import type { PageSize } from './reportPdf';

export const REPORT_PAGE_SIZES: readonly PageSize[] = ['A4', 'Letter'];

/** The options and the run state of the block. Both options are on by default. */
export const reportState = {
  page: 'A4' as PageSize,
  planSection: true,
  /** The block is expanded. */
  open: false,
  busy: false,
  message: '',
  /** The last finished report, for scripts and tests. */
  last: null as ReportResult | null,
};

function save(name: string, data: BlobPart, type: string): void {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([data], { type }));
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}

/** Make the PDF report of the current list and download it. */
export async function exportReportPdf(c: IssuesController, o: { page?: PageSize; planSection?: boolean; download?: boolean } = {}): Promise<ReportResult> {
  if (reportState.busy) throw new Error('A report is being made');
  reportState.busy = true;
  reportState.message = 'Making the report...';
  c.emit();
  try {
    const r = await makeIssueReport(c, {
      page: o.page ?? reportState.page,
      planSection: o.planSection ?? reportState.planSection,
      onProgress: (text) => { reportState.message = text; c.bcf.setStatus(text); },
    });
    reportState.last = r;
    if (o.download !== false) save(r.name, r.bytes as Uint8Array<ArrayBuffer>, 'application/pdf');
    reportState.message = `Report ready: ${r.issues} issue${r.issues === 1 ? '' : 's'}, ${r.pages} pages, ${(r.bytes.length / 1024).toFixed(0)} KB, ${(r.ms / 1000).toFixed(1)} s`;
    c.bcf.setStatus(reportState.message);
    return r;
  } catch (e) {
    reportState.message = e instanceof Error ? e.message : String(e);
    throw e;
  } finally {
    reportState.busy = false;
    c.emit();
  }
}

/** Download the CSV of the current list. */
export function exportReportCsv(c: IssuesController, o: { download?: boolean } = {}): { name: string; text: string; issues: number } {
  const r = issuesCsvOf(c);
  if (o.download !== false) save(r.name, `﻿${r.text}`, 'text/csv;charset=utf-8');
  reportState.message = `CSV ready: ${r.issues} issue${r.issues === 1 ? '' : 's'}`;
  c.bcf.setStatus(reportState.message);
  c.emit();
  return r;
}

/** The block for the issues list: a collapsed "Export report" with the options and the two buttons. */
export function buildReportBlock(c: IssuesController): HTMLElement {
  const box = el('details', 'is-other is-report', { 'data-report': '', 'data-help-key': 'Issues panel/Export report' });
  (box as HTMLDetailsElement).open = reportState.open || reportState.busy;
  box.addEventListener('toggle', () => { reportState.open = (box as HTMLDetailsElement).open; });
  box.appendChild(el('summary', undefined, undefined, 'Export report'));
  const n = c.visibleIssues().length;
  const sel = el('select', 'is-in', { 'aria-label': 'Page size', 'data-field': 'report-page' });
  for (const p of REPORT_PAGE_SIZES) sel.appendChild(el('option', undefined, { value: p }, p));
  sel.value = reportState.page;
  sel.addEventListener('change', () => { reportState.page = sel.value as PageSize; });
  const lab = el('label', 'is-lbl');
  lab.append(el('span', undefined, undefined, 'Page size'), sel);
  const cb = el('input', undefined, { type: 'checkbox', 'data-field': 'report-plan-section' }) as HTMLInputElement;
  cb.checked = reportState.planSection;
  cb.addEventListener('change', () => { reportState.planSection = cb.checked; });
  const cbl = el('label', 'is-meta');
  cbl.style.cssText = 'display:flex;gap:6px;align-items:center';
  cbl.append(cb, el('span', undefined, undefined, 'Plan/Section images'));
  cbl.title = 'Add a small Plan and a small Section for the issues whose sketch is tied to the model. They are rendered on the 3D view, which is put back afterwards.';
  const pdf = button(`PDF report (${n})`, () => { void exportReportPdf(c).catch(() => undefined); }, { primary: true, title: 'A PDF of the issues in the list below: a cover with the counts, then a page per issue with its fields, comments, snapshot and elements' });
  pdf.setAttribute('data-act', 'report-pdf');
  pdf.disabled = n === 0 || reportState.busy || !c.app.loaded;
  const csv = button(`CSV (${n})`, () => { exportReportCsv(c); }, { title: 'One row per issue, with a Comments column' });
  csv.setAttribute('data-act', 'report-csv');
  csv.disabled = n === 0;
  box.append(el('div', 'is-meta', undefined, 'Reports the issues of the list as it is filtered now.'), el('div', 'is-two', undefined), row(pdf, csv));
  box.querySelector('.is-two')!.append(lab, cbl);
  box.appendChild(el('div', 'is-status', { 'data-report-status': '' }, reportState.message));
  return box;
}
