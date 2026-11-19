// Scripting for the issue report and for raising issues from checks: window.__xrayIssueReport and window.__xrayClash. The buttons are
// in the Issues tab (src/issues/reportUi.ts) and in the penetrations and clearance drawers (src/issues/clashUi.ts); this file only gives
// scripts and the smoke tests the same calls. Installs after the issues plugin. Docs: docs-features/issues.md.

import type { AppPlugin } from '../app';
import type { ClashCheck, ClashCounts } from '../issues/clash';
import { countsOf } from '../issues/clash';
import { clashSource, closeNotFound, previewClashes, raiseClashes } from '../issues/clashRaise';
import type { ClashReport } from '../issues/clashRaise';
import { clashConfig, issuesController } from '../issues/clashUi';
import { exportReportCsv, exportReportPdf, reportState } from '../issues/reportUi';
import { reportModelOf } from '../issues/reportRender';
import type { ReportResult } from '../issues/reportRender';
import type { ReportModel } from '../issues/reportModel';
import type { PageSize } from '../issues/reportPdf';

declare global {
  interface Window {
    __xrayIssueReport?: {
      /** Make the PDF of the Issues tab's current list; `download: false` only returns it. */
      pdf(o?: { page?: PageSize; planSection?: boolean; download?: boolean }): Promise<ReportResult>;
      /** The CSV text of the current list; `download: false` only returns it. */
      csv(o?: { download?: boolean }): { name: string; text: string; issues: number };
      /** The report model of the current list. */
      model(): ReportModel;
      readonly options: { page: PageSize; planSection: boolean; busy: boolean };
      setOptions(o: { page?: PageSize; planSection?: boolean }): void;
    };
    __xrayClash?: {
      /** The batch limit above which raising asks first (200). */
      config: { maxBatch: number };
      /** What raising would do now: counts of new, already raised and not found; null when the check has not run. */
      preview(check: ClashCheck): ClashCounts | null;
      raise(check: ClashCheck, o?: { limit?: number }): Promise<ClashReport>;
      /** Close the issues of the check that the latest run does not report any more. */
      close(check: ClashCheck): number;
    };
  }
}

export const issueToolsPlugin: AppPlugin = {
  name: 'issueTools',

  install(): void {
    const ctl = (): NonNullable<ReturnType<typeof issuesController>> => {
      const c = issuesController();
      if (!c) throw new Error('The Issues panel is not available');
      return c;
    };
    window.__xrayIssueReport = {
      pdf: (o) => exportReportPdf(ctl(), o),
      csv: (o) => exportReportCsv(ctl(), o),
      model: () => reportModelOf(ctl()),
      get options() { return { page: reportState.page, planSection: reportState.planSection, busy: reportState.busy }; },
      setOptions(o) {
        if (o.page) reportState.page = o.page;
        if (typeof o.planSection === 'boolean') reportState.planSection = o.planSection;
        ctl().emit();
      },
    };
    window.__xrayClash = {
      config: clashConfig,
      preview(check) {
        const src = clashSource(check);
        const plan = src ? previewClashes(ctl(), src) : null;
        return plan ? countsOf(plan) : null;
      },
      raise(check, o) {
        const src = clashSource(check);
        if (!src) throw new Error(`No ${check} check`);
        return raiseClashes(ctl(), src, o?.limit !== undefined ? { limit: o.limit } : {});
      },
      close(check) {
        const src = clashSource(check);
        return src ? closeNotFound(ctl(), src) : 0;
      },
    };
  },
};
