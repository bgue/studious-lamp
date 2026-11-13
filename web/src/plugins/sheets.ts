// Sheets plugin: PDF drawing sheets next to the 3D model. Opening or dropping a PDF adds it as a sheet set (one sheet per page);
// the viewer covers the 3D canvas area with the page (the model stays loaded under it) and "Back to model" returns. Sketches on a
// sheet are markup sets with a sheet frame, drawn with the same toolbar. Export writes a marked-up copy of the PDF with the
// sketches as annotations on their own layer; opening a PDF reads the annotations it already has. The PDF libraries load only on
// first use (src/sheets/pdfRuntime.ts). This file wires the controller, the Sheets segment of the Issues panel, the file input,
// the actions and window.__xraySheets. Logic in src/sheets. Docs: docs-features/sheets.md.

import type { AppPlugin, ViewerApp } from '../app';
import { registerAction } from '../input/actions';
import { SheetsController } from '../sheets/controller';
import type { OpenReport } from '../sheets/controller';
import { sheetsPane } from '../sheets/ui';
import type { SheetViewer } from '../sheets/viewer';
import type { Sheet, SheetDoc } from '../sheets/model';
import type { ExportedFile } from '../markup/controller';
import type { Markup, MarkupKind, MarkupSet } from '../markup/model';
import { newMarkup } from '../markup/model';
import { markupController } from './markup';
import { bcfController } from './bcf';

declare global {
  interface Window {
    __xraySheets?: {
      /** Open a PDF as sheets (the same as the Open PDF button and a drop). */
      openFile(file: File | Blob): Promise<OpenReport>;
      /** The PDFs of the loaded model, and their pages. */
      docs(): SheetDoc[];
      sheets(docId?: string): Sheet[];
      /** Open a sheet in the viewer; close returns to the 3D view. */
      open(sheetId: string): boolean;
      close(): void;
      readonly openSheet: string | null;
      /** The viewer's zoom and picture state: scale (px per point), tx, ty, render counts. */
      view(): ReturnType<SheetViewer['state']> | null;
      zoomAt(x: number, y: number, k: number): void;
      fit(): void;
      /** Stage pixels to PDF user-space points, and back (the viewer's current transform). */
      toUser(x: number, y: number): [number, number] | null;
      toStage(ux: number, uy: number): [number, number] | null;
      /** The sketches on a sheet. */
      sketches(sheetId: string): MarkupSet[];
      newSketch(sheetId: string, title?: string): MarkupSet;
      /** Add a markup to a sketch from PDF user-space points (shapes) or an anchor (text, callout). */
      add(setId: string, spec: { kind: MarkupKind; points?: Array<[number, number]>; at?: [number, number]; text?: string; colour?: Markup['colour']; weight?: Markup['weight']; fill?: boolean }): Markup;
      copyToEditable(setId: string): MarkupSet | null;
      exportMarkedUp(docId: string, opts?: { download?: boolean }): Promise<ExportedFile & { added: number; removed: number; subtypes: Record<string, number> }>;
      raise(setId: string, opts?: { topic?: string }): Promise<string>;
      removeDoc(docId: string): Promise<void>;
      /** Wait for the saved record to be written. */
      save(): Promise<void>;
      readonly status: string;
      readonly persistent: boolean;
      readonly controller: SheetsController;
    };
  }
}

let ctl: SheetsController | null = null;

export function sheetsController(): SheetsController | null {
  return ctl;
}

export const sheetsPlugin: AppPlugin = {
  name: 'sheets',

  install(app: ViewerApp): void {
    const mk = markupController();
    const bcf = bcfController();
    const issues = window.__xrayIssues?.controller;
    if (!mk || !issues) return;
    const c = new SheetsController(app, mk, bcf ?? null);
    ctl = c;
    const stage = app.canvas.parentElement ?? document.body;

    // ---- the viewer: built on first use, in a chunk of its own
    let viewer: SheetViewer | null = null;
    let building: Promise<SheetViewer> | null = null;
    c.showViewer = (id) => {
      void (async () => {
        if (!viewer && id) {
          building ??= import('../sheets/viewer').then((m) => (viewer = new m.SheetViewer(c, stage)));
          await building;
        }
        await viewer?.show(id);
      })();
    };

    // ---- the file input (the Open PDF button, the action and scripts all use it)
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.pdf,application/pdf';
    input.multiple = true;
    input.style.display = 'none';
    input.setAttribute('data-sheets', 'open');
    input.addEventListener('change', () => {
      const files = Array.from(input.files ?? []);
      input.value = '';
      void (async () => { for (const f of files) await c.openFile(f); })();
    });
    document.body.appendChild(input);
    const pick = (): void => input.click();

    // ---- the Sheets segment of the Issues panel, the issue link
    const phone = (): boolean => !!window.matchMedia?.('(max-width: 700px)').matches;
    issues.sheetsPane = sheetsPane(c, issues, pick, () => { if (phone()) window.__xrayIssues?.close(); });
    issues.sheetRaise = (id, o) => c.raise(id, o);
    if (bcf) bcf.beforeExportAsync = () => c.refreshIssueViewpoints();
    c.onChange(() => issues.emit());
    void c.init();

    registerAction({ id: 'sheets.open', label: 'Sheets: open a PDF', group: 'Markup', keys: [], description: 'Open a PDF drawing as sheets (the model stays loaded)', run: () => { window.__xrayIssues?.open('sheets'); pick(); } });
    registerAction({ id: 'sheets.list', label: 'Sheets: open the Sheets segment', group: 'Panels', keys: [], description: 'Open the Issues tab on the Sheets segment', run: () => window.__xrayIssues?.open('sheets') });
    registerAction({ id: 'sheets.back', label: 'Sheets: back to the model', group: 'Markup', keys: [], description: 'Close the sheet view and return to the 3D model', run: () => c.close() });

    window.__xraySheets = {
      openFile: (f) => c.openFile(f),
      docs: () => c.store.docs.map((d) => ({ ...d })),
      sheets: (docId) => c.store.sheets.filter((s) => !docId || s.docId === docId).map((s) => ({ ...s })),
      open: (id) => c.open(id),
      close: () => c.close(),
      get openSheet() {
        return c.openId;
      },
      view: () => viewer?.state() ?? null,
      zoomAt: (x, y, k) => viewer?.zoomAt(x, y, k),
      fit: () => viewer?.fit(),
      toUser: (x, y) => (viewer?.sheet ? viewer.toUser(x, y) : null),
      toStage: (x, y) => (viewer?.sheet ? viewer.toStage(x, y) : null),
      sketches: (id) => c.sketchesOn(id).map((s) => JSON.parse(JSON.stringify(s)) as MarkupSet),
      newSketch: (id, t) => c.newSketch(id, t),
      add: (setId, spec) => {
        const set = mk.get(setId);
        if (!set) throw new Error(`No sketch ${setId}`);
        const author = mk.author.trim() || 'unknown';
        let m: Markup;
        if (spec.kind === 'text' || spec.kind === 'callout') {
          if (!spec.at) throw new Error('A text or callout needs `at`');
          m = newMarkup(spec.kind, { author, text: spec.text ?? '', anchor: { kind: 'point', point: [spec.at[0], spec.at[1], 0] }, offset: spec.kind === 'text' ? [0.05, -0.04] : [0.1, -0.09], ...(spec.colour ? { colour: spec.colour } : {}) });
        } else {
          if (!spec.points || spec.points.length < 2) throw new Error('A shape needs `points`');
          m = newMarkup(spec.kind, { author, text: spec.text ?? '', shape: { points: spec.points, depth: 0 }, attach: { kind: 'none' }, ...(spec.colour ? { colour: spec.colour } : {}), ...(spec.weight ? { weight: spec.weight } : {}), fill: spec.fill ?? false });
        }
        return mk.add(m, set);
      },
      copyToEditable: (id) => c.copyToEditable(id),
      exportMarkedUp: (docId, o) => (o?.download ? c.downloadMarkedUp(docId).then((f) => f as never) : c.exportMarkedUp(docId)),
      raise: (id, o) => c.raise(id, o),
      removeDoc: (id) => c.removeDoc(id),
      save: () => c.save(),
      get status() {
        return c.status;
      },
      get persistent() {
        return c.store.persistent;
      },
      get controller() {
        return c;
      },
    };
  },

  onModel(): void {
    ctl?.onModel();
  },
};
